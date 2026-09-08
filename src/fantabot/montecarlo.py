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
import zlib
from dataclasses import dataclass

import numpy as np

from .models import ROLES, Player
from .optimizer import optimize_roster
from .rules import MAX_SUBS, MIN_SPEND_FRAC
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


# Effetto squadra x giornata sul voto puro: varianza ~0.07 al netto del rumore
# campionario, cioe' sd ~0.25 (misurato sui voti raw 2021-2026; il primo
# valore 0.55 era la sd lorda, 4 volte troppo grande in varianza). Senza, i
# compagni di squadra sono indipendenti e una difesa intera (modificatore,
# porta inviolata) sembra meno rischiosa e meno redditizia di quanto sia.
TEAM_SHOCK_SD = 0.25
# nuovi in Serie A: stima piu' incerta (cold start), floor piu' alto
NUOVO_SIGMA_SHIFT_MIN = 0.6
NUOVO_SIGMA_PLAY = 0.18

# Disponibilita' con memoria: chi e' fuori da piu' giornate ha meno probabilita'
# di rientrare alla prossima, e chi gioca da settimane e' piu' probabile che
# giochi ancora. Gli scostamenti qui sotto sono sul LOGIT del tasso individuale
# del giocatore, quindi al netto dell'eterogeneita' fra titolari e riserve
# (misurati su 57.925 giocatore-giornata delle stagioni 2021-22, 2023-24 e
# 2024-25 da scripts/indagine/prova_hazard_presenze.py; verifica fuori campione
# sul 2025-26: Brier 0.1636 -> 0.1427, -12.8%, migliora in tutti gli stati).
# NB: i dati dicono solo se il giocatore ha preso voto, non perche': infortunio,
# squalifica, panchina e pochi minuti stanno insieme. E' un modello della
# presenza a voto, non dell'infortunio.
MAX_RUN = 8
OFFSET_PRESENTE = [0.425, 0.683] + [0.641] * (MAX_RUN - 2)   # run 1, 2, 3+
OFFSET_ASSENTE = [-0.240, -0.508, -0.732, -0.732] + [-1.031] * (MAX_RUN - 4)


def _offset(presente: bool, run: int) -> float:
    tab = OFFSET_PRESENTE if presente else OFFSET_ASSENTE
    return tab[min(run, MAX_RUN) - 1]


def _stazionaria(base_logit: float) -> float:
    """Quota di giornate giocate dalla catena a memoria, dato il logit base."""
    n = MAX_RUN * 2                      # (presente, run) e (assente, run)
    T = np.zeros((n, n))
    for i in range(n):
        presente = i < MAX_RUN
        run = (i % MAX_RUN) + 1
        p = 1.0 / (1.0 + np.exp(-(base_logit + _offset(presente, run))))
        j_gioca = 0 if not presente else min(run, MAX_RUN - 1)
        j_fermo = MAX_RUN if presente else MAX_RUN + min(run, MAX_RUN - 1)
        T[i, j_gioca] += p
        T[i, j_fermo] += 1.0 - p
    v = np.full(n, 1.0 / n)
    for _ in range(400):
        v = v @ T
    return float(v[:MAX_RUN].sum())


def _calibra_logit(p_target: float) -> float:
    """Logit base che fa giocare il giocatore, in media, p_target delle
    giornate: senza questa taratura la memoria sposterebbe le presenze attese."""
    lo, hi = -8.0, 8.0
    for _ in range(40):
        mid = (lo + hi) / 2
        if _stazionaria(mid) < p_target:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2


_CACHE_LOGIT: dict[int, float] = {}


def logit_base(p_target: float) -> float:
    chiave = int(round(min(0.97, max(0.03, p_target)) * 200))
    if chiave not in _CACHE_LOGIT:
        _CACHE_LOGIT[chiave] = _calibra_logit(chiave / 200)
    return _CACHE_LOGIT[chiave]


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
        # incertezza di stima per giocatore: pr["sigma"] = (q90 - q10) / 2.56
        # dei quantili conformalizzati (stage S3), sul RESTO di stagione
        # (38 - k giornate); in mancanza, dai quantili impliciti in value_up
        # (q75 - q50 = 0.674 sigma per una normale). Convertita in punti per
        # giornata con gli stessi clamp; floor prudente
        k = int(pr.get("k", 0) or 0)
        sig = pr.get("sigma")
        if sig is not None and float(sig) > 0:
            sigma_season = float(sig)
        else:
            vup = float(pr.get("value_up", 0.0) or 0.0)
            sigma_season = (vup - value) / 0.674 if vup > value else 40.0
        # la simulazione gioca tutte le 38 giornate (anche le K gia' fatte),
        # quindi la sigma di stagione va spalmata su 38, non su 38-k: altrimenti
        # l'incertezza per giornata e' gonfiata di 38/(38-k)
        sigma_shift = float(min(1.5, max(0.35, sigma_season / (p_play * GIORNATE))))
        sigma_play = 0.10
        if bool(pr.get("nuovo", False)) or getattr(p, "nuovo", False):
            sigma_shift = max(sigma_shift, NUOVO_SIGMA_SHIFT_MIN)
            sigma_play = NUOVO_SIGMA_PLAY
        dists[pid] = PlayerDist(p.role, p_play, fv, v, shift, sigma_shift, sigma_play,
                                team=str(getattr(p, "team", "") or ""))
    return dists


def _rng_di(seed: int, chiave: str) -> np.random.Generator:
    """Generatore legato a una chiave testuale (giocatore o squadra): due rose
    diverse vedono lo stesso giocatore con gli stessi numeri casuali."""
    return np.random.default_rng([seed, zlib.crc32(chiave.encode("utf-8"))])


def simulate_roster(roster: dict[str, list[str]], dists: dict[str, PlayerDist],
                    n_sims: int, rng: random.Random, use_mod: bool = True,
                    seed_scenari: int | None = None) -> np.ndarray:
    """Ritorna array (n_sims, 38) di punteggi giornata della rosa.

    Con `seed_scenari` i numeri casuali sono indicizzati per giocatore e per
    squadra invece che estratti in sequenza: la stessa scena (chi gioca, che
    voto prende, come va la sua squadra quel turno) si ripete identica in
    qualunque rosa compaia. Serve per confrontare due rose sulle STESSE
    stagioni simulate: la differenza fra loro non porta piu' il rumore comune."""
    comune = seed_scenari is not None
    nprng = np.random.default_rng(rng.randrange(1 << 30))
    out = np.zeros((n_sims, GIORNATE))
    ids = [pid for r in ROLES for pid in roster[r]]
    teams = sorted({dists[pid].team for pid in ids})
    team_ix = {t: i for i, t in enumerate(teams)}
    if comune:
        # tabelle (n_sims x 38) per giocatore e per squadra, riproducibili
        u_gioca, u_camp, eps_pl, u_play, shock_sq = {}, {}, {}, {}, {}
        for pid in ids:
            g = _rng_di(seed_scenari, pid)
            u_gioca[pid] = g.random((n_sims, GIORNATE))
            u_camp[pid] = g.random((n_sims, GIORNATE))
            eps_pl[pid] = g.standard_normal(n_sims)
            u_play[pid] = g.standard_normal(n_sims)
        for t in teams:
            shock_sq[t] = _rng_di(seed_scenari, "SQ:" + t).standard_normal((n_sims, GIORNATE))
    for s in range(n_sims):
        form: dict[str, float] = {}
        form_v: dict[str, float] = {}
        fsum, fn, vsum = {}, {}, {}
        # "verita'" della stagione simulata: la stima puo' sbagliare, e sbaglia
        # nella stessa direzione per tutte le 38 giornate
        if comune:
            eps = {pid: float(eps_pl[pid][s] * dists[pid].sigma_shift) for pid in ids}
            pplay = {pid: float(min(0.97, max(0.05, dists[pid].p_play
                                              + u_play[pid][s] * dists[pid].sigma_play)))
                     for pid in ids}
        else:
            eps = {pid: nprng.normal(0.0, dists[pid].sigma_shift) for pid in ids}
            pplay = {pid: float(min(0.97, max(0.05, nprng.normal(dists[pid].p_play,
                                                                 dists[pid].sigma_play))))
                     for pid in ids}
        # disponibilita' con memoria: logit tarato perche' la media resti pplay
        base = {pid: logit_base(pplay[pid]) for pid in ids}
        stato = {pid: ((u_gioca[pid][s, 0] if comune else nprng.random()) < pplay[pid], 1)
                 for pid in ids}
        for g in range(GIORNATE):
            votes, voti = {}, {}
            # shock squadra x giornata: stessa partita, stessa sorte per i compagni
            if comune:
                shock = np.array([shock_sq[t][s, g] * TEAM_SHOCK_SD for t in teams])
            else:
                shock = nprng.normal(0.0, TEAM_SHOCK_SD, size=len(teams))
            # chi risultava disponibile alla vigilia: e' l'informazione che si
            # ha prima di schierare (non chi prendera' voto oggi)
            attesi = {pid for pid in ids if stato[pid][0]}
            for pid in ids:
                d = dists[pid]
                era_presente, run = stato[pid]
                p_ora = 1.0 / (1.0 + np.exp(-(base[pid] + _offset(era_presente, run))))
                gioca = (u_gioca[pid][s, g] if comune else nprng.random()) < p_ora
                stato[pid] = (gioca, run + 1 if gioca == era_presente else 1)
                if gioca:
                    k = (int(u_camp[pid][s, g] * len(d.samples_fv)) if comune
                         else nprng.integers(len(d.samples_fv)))
                    ts = float(shock[team_ix[d.team]])
                    votes[pid] = float(d.samples_fv[k] + d.shift + eps[pid] + ts)
                    voti[pid] = float(d.samples_v[k] + (d.shift + eps[pid]) * 0.4 + ts)
            _, starters, bench = pick_lineup(roster, form, form_v, use_mod, attesi)
            pts, _ = score_giornata(starters, bench, votes, MAX_SUBS, voti, use_mod)
            out[s, g] = pts
            for pid, fv in votes.items():
                fsum[pid] = fsum.get(pid, 0.0) + fv
                fn[pid] = fn.get(pid, 0) + 1
                vsum[pid] = vsum.get(pid, 0.0) + voti[pid]
                form[pid] = fsum[pid] / fn[pid]
                form_v[pid] = vsum[pid] / fn[pid]
    return out


def calendari(n_squadre: int, n_sims: int, seed: int) -> list[list[int]]:
    """Ordini di accoppiamento, uno per scenario, uguali per tutte le rose
    confrontate: cosi' due candidate incontrano gli stessi avversari negli
    stessi turni e la differenza fra loro non dipende dal sorteggio."""
    r = random.Random(seed)
    out = []
    for _ in range(n_sims):
        ordine = list(range(n_squadre))
        r.shuffle(ordine)
        out.append(ordine)
    return out


def p_first(cand: np.ndarray, opps: list[np.ndarray], rng: random.Random,
            cal: list[list[int]] | None = None) -> float:
    """P(1o posto) del candidato contro gli avversari, calendario Berger,
    3/1/0 sui gol da fasce. Con `cal` il calendario e' comune fra i confronti."""
    n = len(opps) + 1
    wins = 0
    for s in range(cand.shape[0]):
        scores = [cand[s]] + [o[s % o.shape[0]] for o in opps]
        if cal is not None:
            order = list(cal[s % len(cal)])
        else:
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
    archetipi, ritorna la migliore per P(1o) + tabella completa.

    Tutte le candidate vengono giocate sulle STESSE stagioni simulate, contro
    gli STESSI avversari e con lo STESSO calendario (scenari indicizzati per
    giocatore, non estratti in sequenza): il confronto fra due obiettivi non
    porta piu' il rumore comune. La candidata vincente viene poi rigiocata su
    scenari MAI usati per sceglierla, cosi' il P(1o) che si riporta non e'
    gonfiato dall'aver selezionato il fortunato."""
    rng = random.Random(seed)
    seed_scelta = seed * 1000 + 1
    seed_verifica = seed * 1000 + 2
    opps = archetype_rosters(players, ref_credits, quotas, budget, rng, preds=preds)
    opp_scores = [simulate_roster(o, dists, n_sims, rng, seed_scenari=seed_scelta)
                  for o in opps]
    cal = calendari(len(opps) + 1, n_sims, seed_scelta)
    values = {pid: float(preds.get(pid, {}).get("value", 0.0)) for pid in players}
    values_up = {pid: float(preds.get(pid, {}).get("value_up", values[pid])) for pid in players}
    rows, seen = [], set()
    for lam in lams:
        for lo, hi in shares:
            # piano iniziale: impegna quasi tutto il budget (i crediti lasciati
            # in cassa a fine asta valgono zero)
            sol = optimize_roster(players, prices, values, quotas, budget,
                                  forced_spend={"A": (lo * budget, hi * budget)},
                                  values_up=values_up, lam=lam,
                                  min_spend=MIN_SPEND_FRAC * budget)
            if sol is None:      # con questa quota d'attacco la soglia non si raggiunge
                continue
            key = tuple(sorted(pid for r in ROLES for pid in sol["roster"][r]))
            if key in seen:
                continue
            seen.add(key)
            sc = simulate_roster(sol["roster"], dists, n_sims, rng, seed_scenari=seed_scelta)
            pw = p_first(sc, opp_scores, rng, cal=cal)
            rows.append({"lam": lam, "attack_share": (lo, hi), "module": sol["module"],
                         "cost": round(sol["cost"], 1), "mean_pts": round(float(sc.sum(1).mean()), 1),
                         "sd_g": round(float(sc.std()), 2), "p_win": round(pw, 3),
                         "roster": sol["roster"]})
    rows.sort(key=lambda r: -r["p_win"])
    # P(1o) degli archetipi nello STESSO tavolo da 10 in cui gioca il piano:
    # ogni archetipo contro gli altri otto piu' il piano scelto. Calcolarli in
    # un tavolo da 9 senza il piano dava numeri non confrontabili con il suo
    # (in nove la probabilita' a priori e' 1/9, in dieci 1/10).
    if rows:
        sc_best = simulate_roster(rows[0]["roster"], dists, n_sims, rng,
                                  seed_scenari=seed_scelta)
        opp_p = [p_first(o, [x for j, x in enumerate(opp_scores) if j != i] + [sc_best],
                         rng, cal=cal)
                 for i, o in enumerate(opp_scores)]
    else:
        cal_opp = calendari(len(opp_scores), n_sims, seed_scelta)
        opp_p = [p_first(o, [x for j, x in enumerate(opp_scores) if j != i], rng, cal=cal_opp)
                 for i, o in enumerate(opp_scores)]
    verifica = None
    if rows:
        opp_v = [simulate_roster(o, dists, n_sims, rng, seed_scenari=seed_verifica)
                 for o in opps]
        cal_v = calendari(len(opps) + 1, n_sims, seed_verifica)
        sc_v = simulate_roster(rows[0]["roster"], dists, n_sims, rng,
                               seed_scenari=seed_verifica)
        pw_v = p_first(sc_v, opp_v, rng, cal=cal_v)
        # errore standard binomiale su n_sims scenari indipendenti
        se = float(np.sqrt(max(pw_v * (1 - pw_v), 1e-9) / n_sims))
        verifica = {"p_win": round(pw_v, 3), "se": round(se, 3),
                    "ic95": [round(max(0.0, pw_v - 1.96 * se), 3),
                             round(min(1.0, pw_v + 1.96 * se), 3)],
                    "n_sims": n_sims}
    return {"best": rows[0] if rows else None, "table": rows,
            "opponents_p_win": [round(x, 3) for x in opp_p],
            "verifica_fuori_scelta": verifica}
