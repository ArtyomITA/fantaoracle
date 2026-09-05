"""Monte Carlo di stagione: da E[punti] a P(vincere il campionato).

Il campionato H2H con fasce gol (66, +6) premia i picchi, non la media: la
rosa "piatta" con +100 punti attesi non vince piu' di quella con i big.
Qui ogni rosa candidata viene giocata N volte contro avversari realistici
(archetipi a prezzo di mercato), giornata per giornata con le regole della
lega, e si misura P(1o posto). L'ottimizzatore sceglie l'obiettivo (peso
dell'upside, quota attacco) che massimizza quella probabilita'.

Distribuzioni per giocatore: campioni (voto, fantavoto) dalle sue giornate
reali delle stagioni precedenti, traslati perche' la media stagionale
coincida con la predizione (value) e la disponibilita' con `pres`.
"""
from __future__ import annotations

import random
from dataclasses import dataclass

import numpy as np

from .models import ROLES, Player
from .optimizer import optimize_roster
from .rules import MAX_SUBS
from .season.lineup import goals_from_points, pick_lineup, score_giornata

GIORNATE = 38


@dataclass
class PlayerDist:
    role: str
    p_play: float               # probabilita' di avere voto in una giornata
    samples_fv: np.ndarray      # fantavoti storici (condizionati a giocare)
    samples_v: np.ndarray       # voti puri appaiati
    shift: float                # traslazione per centrare la media predetta
    sigma_shift: float = 0.6    # incertezza della STIMA (per giornata): estratta
                                # una volta per simulazione. Senza, l'ottimizzatore
                                # "vince" per costruzione (maledizione del vincitore)
    sigma_play: float = 0.10    # incertezza sulla disponibilita'
    team: str = ""              # squadra: shock condiviso squadra x giornata


# Effetto squadra x giornata sul voto: misurato sui voti 2024/25 e 2025/26,
# sd ~0.55 (13-20% della varianza del voto puro). Senza, i compagni di squadra
# sono indipendenti e una difesa intera (modificatore, porta inviolata) sembra
# meno rischiosa e meno redditizia di quanto sia.
TEAM_SHOCK_SD = 0.55
# nuovi in Serie A: stima piu' incerta (cold start), floor piu' alto
NUOVO_SIGMA_SHIFT_MIN = 0.6
NUOVO_SIGMA_PLAY = 0.18


def build_dists(players: dict[str, Player], preds: dict[str, dict],
                hist_votes: list[list[dict[str, float]]],
                hist_voti: list[list[dict[str, float]]]) -> dict[str, PlayerDist]:
    """hist_votes/hist_voti: liste (stagioni precedenti) di liste per giornata."""
    by_role_fv = {r: [] for r in ROLES}
    by_role_v = {r: [] for r in ROLES}
    raw: dict[str, tuple[list, list]] = {}
    for season_v, season_p in zip(hist_votes, hist_voti):
        for g, d in enumerate(season_v):
            pv = season_p[g] if g < len(season_p) else {}
            for pid, fv in d.items():
                if pid in players:
                    raw.setdefault(pid, ([], []))
                    raw[pid][0].append(fv)
                    raw[pid][1].append(pv.get(pid, fv))
                    by_role_fv[players[pid].role].append(fv)
                    by_role_v[players[pid].role].append(pv.get(pid, fv))
    dists = {}
    for pid, p in players.items():
        pr = preds.get(pid, {})
        value = float(pr.get("value", 0.0))
        pres = float(pr.get("pres", 0.0)) if pr.get("pres") is not None else None
        fv, v = raw.get(pid, ([], []))
        if len(fv) < 8:
            fv, v = by_role_fv[p.role], by_role_v[p.role]
            hist_rate = 0.7
        else:
            hist_rate = min(1.0, len(raw[pid][0]) / (GIORNATE * max(1, len(hist_votes))))
        fv = np.asarray(fv, dtype=float)
        v = np.asarray(v, dtype=float)
        p_play = pres / GIORNATE if pres is not None and pres > 0 else hist_rate
        p_play = float(min(0.97, max(0.05, p_play)))
        mean_needed = value / (p_play * GIORNATE) if value > 0 else fv.mean()
        shift = float(mean_needed - fv.mean())
        shift = max(-2.0, min(2.0, shift))
        # incertezza di stima dai quantili del modello (q75 - q50 = 0.674 sigma
        # per una normale), convertita in punti per giornata; floor prudente
        vup = float(pr.get("value_up", 0.0) or 0.0)
        sigma_season = (vup - value) / 0.674 if vup > value else 40.0
        sigma_shift = float(min(1.5, max(0.35, sigma_season / (p_play * GIORNATE))))
        sigma_play = 0.10
        if bool(pr.get("nuovo", False)) or getattr(p, "nuovo", False):
            sigma_shift = max(sigma_shift, NUOVO_SIGMA_SHIFT_MIN)
            sigma_play = NUOVO_SIGMA_PLAY
        dists[pid] = PlayerDist(p.role, p_play, fv, v, shift, sigma_shift, sigma_play,
                                team=str(getattr(p, "team", "") or ""))
    return dists


def simulate_roster(roster: dict[str, list[str]], dists: dict[str, PlayerDist],
                    n_sims: int, rng: random.Random, use_mod: bool = True) -> np.ndarray:
    """Ritorna array (n_sims, 38) di punteggi giornata della rosa."""
    nprng = np.random.default_rng(rng.randrange(1 << 30))
    out = np.zeros((n_sims, GIORNATE))
    ids = [pid for r in ROLES for pid in roster[r]]
    teams = sorted({dists[pid].team for pid in ids})
    team_ix = {t: i for i, t in enumerate(teams)}
    for s in range(n_sims):
        form: dict[str, float] = {}
        form_v: dict[str, float] = {}
        fsum, fn, vsum = {}, {}, {}
        # "verita'" della stagione simulata: la stima puo' sbagliare, e sbaglia
        # nella stessa direzione per tutte le 38 giornate
        eps = {pid: nprng.normal(0.0, dists[pid].sigma_shift) for pid in ids}
        pplay = {pid: float(min(0.97, max(0.05, nprng.normal(dists[pid].p_play,
                                                              dists[pid].sigma_play))))
                 for pid in ids}
        for g in range(GIORNATE):
            votes, voti = {}, {}
            # shock squadra x giornata: stessa partita, stessa sorte per i compagni
            shock = nprng.normal(0.0, TEAM_SHOCK_SD, size=len(teams))
            for pid in ids:
                d = dists[pid]
                if nprng.random() < pplay[pid]:
                    k = nprng.integers(len(d.samples_fv))
                    ts = float(shock[team_ix[d.team]])
                    votes[pid] = float(d.samples_fv[k] + d.shift + eps[pid] + ts)
                    voti[pid] = float(d.samples_v[k] + (d.shift + eps[pid]) * 0.4 + ts)
            _, starters, bench = pick_lineup(roster, form, form_v, use_mod, set(votes))
            pts, _ = score_giornata(starters, bench, votes, MAX_SUBS, voti, use_mod)
            out[s, g] = pts
            for pid, fv in votes.items():
                fsum[pid] = fsum.get(pid, 0.0) + fv
                fn[pid] = fn.get(pid, 0) + 1
                vsum[pid] = vsum.get(pid, 0.0) + voti[pid]
                form[pid] = fsum[pid] / fn[pid]
                form_v[pid] = vsum[pid] / fn[pid]
    return out


def p_first(cand: np.ndarray, opps: list[np.ndarray], rng: random.Random) -> float:
    """P(1o posto) del candidato contro gli avversari, calendario Berger
    casuale per simulazione, 3/1/0 sui gol da fasce."""
    n = len(opps) + 1
    wins = 0
    for s in range(cand.shape[0]):
        scores = [cand[s]] + [o[s % o.shape[0]] for o in opps]
        order = list(range(n))
        rng.shuffle(order)
        table = [0] * n
        rounds = []
        ts = order[:]
        for _ in range(n - 1):
            rounds.append([(ts[i], ts[n - 1 - i]) for i in range(n // 2)])
            ts.insert(1, ts.pop())
        for g in range(GIORNATE):
            for a, b in rounds[g % len(rounds)]:
                ga, gb = goals_from_points(scores[a][g]), goals_from_points(scores[b][g])
                if ga > gb:
                    table[a] += 3
                elif gb > ga:
                    table[b] += 3
                else:
                    table[a] += 1
                    table[b] += 1
        tot = [float(np.sum(sc)) for sc in scores]
        best = max(range(n), key=lambda i: (table[i], tot[i]))
        wins += 1 if best == 0 else 0
    return wins / cand.shape[0]


def archetype_rosters(players: dict[str, Player], ref_credits: dict[str, float],
                      quotas: dict[str, int], budget: int, rng: random.Random,
                      n: int = 9, preds: dict[str, dict] | None = None
                      ) -> list[dict[str, list[str]]]:
    """Avversari FORTI e realistici: rose ottime secondo il MERCATO (valore =
    prezzo medio reale con rumore ±12%, prezzi = mercato), con tre profili di
    spesa in attacco: stelle (60-72%), guida (45-58%), equilibrio (32-45%).
    E' quello che ottiene un amico bravo che compra al prezzo giusto: se il
    piano B non batte questi, non batte nessuno."""
    shares = [(0.60, 0.72), (0.45, 0.58), (0.32, 0.45)]
    rosters = []
    for i in range(n):
        lo, hi = shares[i % len(shares)]
        # valore "umano": prezzo di mercato con rumore + titolarita' attesa
        # (un titolare da 1 credito vale piu' di un ragazzo a 0 presenze)
        vals = {}
        for pid in players:
            pres = float((preds or {}).get(pid, {}).get("pres", 0.0) or 0.0)
            vals[pid] = ref_credits[pid] * rng.uniform(0.88, 1.12) + 6.0 * (pres / 38.0)
        sol = optimize_roster(players, ref_credits, vals, quotas, budget,
                              forced_spend={"A": (lo * budget, hi * budget)},
                              bench_weight=0.35, time_limit=8)
        if sol is None:
            sol = optimize_roster(players, ref_credits, vals, quotas, budget,
                                  bench_weight=0.35, time_limit=8)
        rosters.append(sol["roster"])
    return rosters


def choose_objective(players: dict[str, Player], preds: dict[str, dict],
                     prices: dict[str, float], ref_credits: dict[str, float],
                     dists: dict[str, PlayerDist], quotas: dict[str, int],
                     budget: int, seed: int = 0, n_sims: int = 150,
                     lams=(0.0, 0.5, 1.0), shares=((0.20, 0.35), (0.35, 0.50), (0.50, 0.65))
                     ) -> dict:
    """Genera candidate (MILP con lam x quota attacco), le gioca contro gli
    archetipi, ritorna la migliore per P(1o) + tabella completa."""
    rng = random.Random(seed)
    opps = archetype_rosters(players, ref_credits, quotas, budget, rng, preds=preds)
    opp_scores = [simulate_roster(o, dists, n_sims, rng) for o in opps]
    values = {pid: float(preds.get(pid, {}).get("value", 0.0)) for pid in players}
    values_up = {pid: float(preds.get(pid, {}).get("value_up", values[pid])) for pid in players}
    rows, seen = [], set()
    for lam in lams:
        for lo, hi in shares:
            sol = optimize_roster(players, prices, values, quotas, budget,
                                  forced_spend={"A": (lo * budget, hi * budget)},
                                  values_up=values_up, lam=lam)
            if sol is None:
                continue
            key = tuple(sorted(pid for r in ROLES for pid in sol["roster"][r]))
            if key in seen:
                continue
            seen.add(key)
            sc = simulate_roster(sol["roster"], dists, n_sims, rng)
            pw = p_first(sc, opp_scores, rng)
            rows.append({"lam": lam, "attack_share": (lo, hi), "module": sol["module"],
                         "cost": round(sol["cost"], 1), "mean_pts": round(float(sc.sum(1).mean()), 1),
                         "sd_g": round(float(sc.std()), 2), "p_win": round(pw, 3),
                         "roster": sol["roster"]})
    rows.sort(key=lambda r: -r["p_win"])
    opp_p = [p_first(o, [x for j, x in enumerate(opp_scores) if j != i], rng)
             for i, o in enumerate(opp_scores)]
    return {"best": rows[0] if rows else None, "table": rows,
            "opponents_p_win": [round(x, 3) for x in opp_p]}
