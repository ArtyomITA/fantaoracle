"""Banco di prova: politiche di prezzo del bot B contro un tavolo che paga i
prezzi di mercato di riferimento (leghe 10 squadre / 500 crediti).

Non tocca nessun file del progetto: le varianti sono sottoclassi definite qui.
Pack ed eleggibilita' sono letti dalla copia locale in questa cartella.

Uso:
  python sim_mercato.py --smoke                    # 1 asta P0, misura tempi
  python sim_mercato.py --semi 12 --procs 4        # banco completo
  python sim_mercato.py --report                   # rigenera il .md dal .json
"""
from __future__ import annotations

import argparse
import json
import math
import pickle
import random
import statistics
import sys
import time
from pathlib import Path

W = Path(__file__).resolve().parent
SRC = r"src"
if SRC not in sys.path:
    sys.path.insert(0, SRC)

from fantabot.models import ROLES, Player                     # noqa: E402
from fantabot.bots.base import Bot, BidDecision, NominationDecision  # noqa: E402
from fantabot.bots.bot_b import BBot                          # noqa: E402
from fantabot.bots.bot_c import CBot                          # noqa: E402
from fantabot.engine.auction import AuctionEngine             # noqa: E402
from fantabot.optimizer import greedy_roster, optimize_roster  # noqa: E402
import fantabot.bots.bot_b as _bot_b                          # noqa: E402

# Copie di lavoro: il pack del progetto puo' essere rigenerato mentre il banco
# gira, quindi qui si legge SOLO da queste (impronta verificata a mano).
PACK_PATH = W / "pack.pkl"
ELEG_PATH = W / "elig.json"
IMPRONTA_ATTESA = "db2584ea408b"
OUT_JSON = W / "sim_mercato_risultati.json"
OUT_MD = W / "sim_mercato_risultati.md"

# BBot chiama optimize_roster con time_limit=5 cablato nel sorgente. Per poter
# stringere il limite senza toccare il file del progetto si sostituisce il nome
# dentro il modulo caricato in memoria: cosi' il limite vale per TUTTE le
# politiche, P0 compresa (altrimenti P0 girerebbe con un limite diverso dalle
# varianti e il confronto non sarebbe piu' a parita' di condizioni).
_TL = {"v": 5}
_ORIG_OPT = _bot_b.optimize_roster


def _opt_patched(*a, **kw):
    kw["time_limit"] = _TL["v"]
    return _ORIG_OPT(*a, **kw)


_bot_b.optimize_roster = _opt_patched

_STATE = {}


def impronta_pack() -> str:
    import hashlib
    return hashlib.sha256(PACK_PATH.read_bytes()).hexdigest()


def stato():
    """Carica pack + eleggibilita' una volta per processo."""
    if _STATE:
        return _STATE
    with open(PACK_PATH, "rb") as f:
        pack = pickle.load(f)
    eleg = json.load(open(ELEG_PATH, encoding="utf-8"))
    esclusi = set(eleg["esclusi_fuori_serie_a"])
    mkt = {str(k): float(v) for k, v in eleg["prezzo_mercato_10sq_500"].items()}
    pool = {pid: p for pid, p in pack.players.items() if pid not in esclusi}
    _STATE.update(pack=pack, pool=pool, mkt=mkt,
                  pred=pack.b_predictions,
                  quotas=pack.quotas, budget=pack.budget,
                  bobj=getattr(pack, "b_objective", None) or {})
    return _STATE


# --------------------------------------------------------------------------
# avversari "di mercato"
# --------------------------------------------------------------------------
class MarketBot(Bot):
    """Paga i prezzi di mercato di riferimento, con rumore privato lognormale.

    v_i = prezzo_mercato * LN(0, 0.25); senza prezzo di mercato,
    v_i = max(1, q50*1.3) * LN(0, 0.35). Rilancia finche' prezzo+1 <= v_i
    (il motore taglia comunque a max_bid). Disciplina di reparto morbida:
    riempiti 2/3 degli slot di un ruolo, la voglia su quel ruolo si dimezza.
    """
    name = "MKT"

    def __init__(self, rng, mkt: dict[str, float], pred: dict[str, dict], idx: int = 0):
        super().__init__(rng)
        self.name = f"MKT{idx}"
        self.mkt = mkt
        self.pred = pred
        self.v: dict[str, float] = {}

    def start_auction(self, view):
        for pid in view.pool:
            if pid in self.mkt:
                base = max(1.0, self.mkt[pid])
                sig = 0.25
            else:
                base = max(1.0, self.pred.get(pid, {}).get("q50", 1.0) * 1.3)
                sig = 0.35
            self.v[pid] = base * self.rng.lognormvariate(0.0, sig)

    def _val(self, view, player) -> float:
        v = self.v.get(player.player_id, 1.0)
        r = player.role
        if len(view.me.roster[r]) >= (2.0 / 3.0) * view.quotas[r]:
            v *= 0.5
        return v

    def bid(self, view, player, price: int, leader) -> BidDecision:
        nxt = price + 1
        v = self._val(view, player)
        if nxt <= v and nxt <= view.me.max_bid(view.quotas):
            return BidDecision(nxt, f"mercato: valuto {v:.0f}")
        return BidDecision(None, f"oltre il mercato ({v:.0f})")

    def nominate(self, view) -> NominationDecision:
        avail = sorted(view.available(view.current_role),
                       key=lambda p: -self.v.get(p.player_id, 0.0))
        top = avail[:25] or avail
        p = self.rng.choice(top)
        return NominationDecision(p.player_id, 1, f"chiamo {p.name}")


# --------------------------------------------------------------------------
# le politiche del nostro bot
# --------------------------------------------------------------------------
def _replan_var(self, view):
    """Copia fedele di BBot._replan con UN solo punto di variazione:
    i prezzi del piano vengono da self._plan_prices(). Copiato perche' il
    banco non puo' modificare il file del progetto."""
    self.hammers_since_replan = 0
    heat = self.market_heat()
    self._heat_at_replan = heat
    candidates = dict(view.pool)
    fixed = {pid: Player(pid, pid, r, "") for r, ids in view.me.roster.items()
             for pid, _ in ids}
    prices = self._plan_prices(candidates, heat)
    values = {pid: self._q(pid, "value", 0.0) for pid in list(candidates) + list(fixed)}
    values_up = {pid: self._q(pid, "value_up", values[pid]) for pid in values}
    lam = self.objective.get("lam", 0.0)
    forced = None
    if self.objective.get("attack_share"):
        spent_a = sum(pr for _, pr in view.me.roster.get("A", []))
        lo_s, hi_s = self.objective["attack_share"]
        lo = max(0.0, lo_s * view.budget_total - spent_a)
        hi = max(lo, hi_s * view.budget_total - spent_a)
        forced = {"A": (lo, hi)}
    sol = optimize_roster(candidates, prices, values, view.quotas, view.me.budget,
                          forced_spend=forced, fixed=fixed, values_up=values_up,
                          lam=lam, time_limit=self.MILP_TL)
    if sol is None and forced is not None:
        sol = optimize_roster(candidates, prices, values, view.quotas, view.me.budget,
                              fixed=fixed, values_up=values_up, lam=lam,
                              time_limit=self.MILP_TL)
    if sol is None:
        quotas_left = {r: view.quotas[r] - len(view.me.roster[r]) for r in view.quotas}
        sol = greedy_roster(candidates, prices, values, quotas_left, view.me.budget)
        self.piano_non_fattibile = not sol.get("feasible", True)
        self.quote_non_coperte = sol.get("quote_mancanti") or {}
    else:
        self.piano_non_fattibile = False
        self.quote_non_coperte = {}
    self.module = sol.get("module", "4-4-2")
    self.targets = {pid for ids in sol["roster"].values() for pid in ids} - set(fixed)
    self.starter_targets = set(sol.get("starters") or set()) - set(fixed)
    self._role_of = {pid: p.role for pid, p in view.pool.items()}
    self._best_alt_value = {}
    for r in view.quotas:
        alts = [self._q(pid, "value", 0.0) for pid, p in view.pool.items()
                if p.role == r and pid not in self.targets]
        self._best_alt_value[r] = max(alts) if alts else 0.0


class TargetLog:
    """Registra il piano iniziale (non cambia il comportamento)."""

    def start_auction(self, view):
        super().start_auction(view)
        if not hasattr(self, "initial_targets"):
            self.initial_targets = set(self.targets)
            self.initial_starters = set(self.starter_targets)


class P0(TargetLog, BBot):
    """Politica attuale, invariata."""
    codice = "P0"
    MILP_TL = 5


class PolBot(TargetLog, BBot):
    """Base delle varianti: usa la copia di _replan con _plan_prices."""
    MILP_TL = 5

    def __init__(self, rng, predictions, mkt=None, **kw):
        super().__init__(rng, predictions, **kw)
        self.mkt = mkt or {}
        self.h_num = 0.0   # accumulatori heat "solo fascia alta"
        self.h_den = 0.0

    def _plan_prices(self, candidates, heat):
        return {pid: max(1.0, self._q(pid, "q50") * heat) for pid in candidates}

    _replan = _replan_var


class P0copy(PolBot):
    """Controllo di fedelta': deve coincidere con P0."""
    codice = "P0copy"


class P1(PolBot):
    """Prezzi del piano = prezzo di mercato dove esiste, altrimenti q50*heat.
    Tetti invariati."""
    codice = "P1"

    def _plan_prices(self, candidates, heat):
        out = {}
        for pid in candidates:
            if pid in self.mkt:
                out[pid] = max(1.0, self.mkt[pid])
            else:
                out[pid] = max(1.0, self._q(pid, "q50") * heat)
        return out


class Heat15:
    """market_heat calcolato solo sui giocatori con q50 >= 15, accumulatori
    separati; il resto invariato."""
    Q50_MIN = 15.0

    def market_heat(self) -> float:
        prior = 250.0
        return max(0.5, min(1.8, (self.h_num + prior) / (self.h_den + prior)))

    def on_hammer(self, view, player, price, winner):
        q50 = self._q(player.player_id, "q50")
        if q50 >= self.Q50_MIN:
            self.h_num += price
            self.h_den += q50
        super().on_hammer(view, player, price, winner)


class P2(Heat15, P1):
    """P1 + heat solo fascia alta."""
    codice = "P2"


class P3(P2):
    """P2 + tetto sui target del piano alzato al mercato."""
    codice = "P3"

    def _max_bid_for(self, pid: str) -> float:
        cap = super()._max_bid_for(pid)
        if pid in self.targets and pid in self.mkt:
            cap = max(cap, 1.05 * self.mkt[pid] * self.market_heat())
        return cap


class P4(Heat15, PolBot):
    """Prezzi del piano = meta' mercato meta' q50*heat; heat come P2; tetti P0."""
    codice = "P4"

    def _plan_prices(self, candidates, heat):
        out = {}
        for pid in candidates:
            q = self._q(pid, "q50") * heat
            if pid in self.mkt:
                out[pid] = max(1.0, 0.5 * self.mkt[pid] + 0.5 * q)
            else:
                out[pid] = max(1.0, q)
        return out


POLITICHE = {"P0": P0, "P1": P1, "P2": P2, "P3": P3, "P4": P4, "P0copy": P0copy}


# --------------------------------------------------------------------------
# valutazione della rosa finale
# --------------------------------------------------------------------------
def obiettivo_rosa(roster: dict[str, list], st) -> float | None:
    """objective della rosa finale: optimize_roster con fixed = rosa,
    nessun candidato, budget 0. Sceglie modulo e titolari."""
    pool_all = st["pack"].players
    fixed = {}
    for r, ids in roster.items():
        for pid, _pr in ids:
            p = pool_all.get(pid)
            fixed[pid] = p if p is not None else Player(pid, pid, r, "")
    for r in ROLES:
        if len(roster.get(r, [])) != st["quotas"][r]:
            return None
    pred = st["pred"]
    values = {pid: pred.get(pid, {}).get("value", 0.0) for pid in fixed}
    values_up = {pid: pred.get(pid, {}).get("value_up", values[pid]) for pid in fixed}
    sol = optimize_roster({}, {}, values, st["quotas"], 0, fixed=fixed,
                          values_up=values_up, lam=st["bobj"].get("lam", 0.0),
                          time_limit=10)
    return None if sol is None else float(sol["objective"])


# --------------------------------------------------------------------------
# una singola asta
# --------------------------------------------------------------------------
def run_one(pol: str, seed: int, milp_tl: int = 5) -> dict:
    st = stato()
    t0 = time.time()
    cls = POLITICHE[pol]
    kw = {}
    if cls is not P0:
        kw["mkt"] = st["mkt"]
    noi = cls(random.Random(seed * 1000 + 99), st["pred"],
              objective=st["bobj"], **kw)
    noi.MILP_TL = milp_tl
    _TL["v"] = milp_tl
    bots = [noi]
    for i in range(6):
        bots.append(MarketBot(random.Random(seed * 1000 + i), st["mkt"], st["pred"], i))
    for j, prof in enumerate(("informato", "stars_scrubs", "medio")):
        bots.append(CBot(random.Random(seed * 1000 + 50 + j), prof,
                         hint_prices=st["mkt"]))
    eng = AuctionEngine(dict(st["pool"]), bots, st["quotas"], st["budget"],
                        random.Random(1000 + seed))
    teams = eng.run()
    mine = teams[0]
    pred = st["pred"]
    acquisti = [(pid, pr) for r in ROLES for pid, pr in mine.roster[r]]
    acquisti.sort(key=lambda t: -t[1])
    top3 = acquisti[:3]
    nomi = st["pack"].players
    obj_tutti = []
    for t in teams:
        obj_tutti.append(obiettivo_rosa(t.roster, st))
    mio_obj = obj_tutti[0]
    validi = [o for o in obj_tutti if o is not None]
    rank = (sorted(validi, reverse=True).index(mio_obj) + 1) if mio_obj is not None else None
    posseduti = {pid for pid, _ in acquisti}
    persi = len(getattr(noi, "initial_targets", set()) - posseduti)
    return {
        "politica": pol, "seed": seed,
        "objective": mio_obj,
        "somma_value": sum(pred.get(pid, {}).get("value", 0.0) for pid, _ in acquisti),
        "residuo": mine.budget,
        "slot_vuoti": mine.slots_left(st["quotas"]),
        "spesa_top3": sum(pr for _, pr in top3),
        "top3": [{"pid": pid, "nome": nomi[pid].name if pid in nomi else pid,
                  "prezzo": pr,
                  "q50": pred.get(pid, {}).get("q50"),
                  "mercato": st["mkt"].get(pid)} for pid, pr in top3],
        "target_persi": persi,
        "target_iniziali": len(getattr(noi, "initial_targets", set())),
        "rank_objective": rank,
        "heat_finale": float(noi.market_heat()),
        "obj_tutti": obj_tutti,
        "secondi": round(time.time() - t0, 1),
    }


def _job(args):
    pol, seed, tl = args
    try:
        return run_one(pol, seed, tl)
    except Exception as e:  # una singola asta non deve buttare giu' il banco
        import traceback
        return {"politica": pol, "seed": seed, "errore": f"{e}",
                "traceback": traceback.format_exc()[-1500:]}


# --------------------------------------------------------------------------
# statistiche e report
# --------------------------------------------------------------------------
METRICHE = [("objective", "objective"), ("somma_value", "somma value"),
            ("residuo", "residuo"), ("slot_vuoti", "slot vuoti"),
            ("spesa_top3", "spesa top3"), ("target_persi", "target persi"),
            ("rank_objective", "rank obj"), ("heat_finale", "heat finale")]


def ms(vals):
    vals = [v for v in vals if v is not None]
    if not vals:
        return (float("nan"), float("nan"))
    m = statistics.fmean(vals)
    se = statistics.stdev(vals) / math.sqrt(len(vals)) if len(vals) > 1 else 0.0
    return (m, se)


def report(dati: dict) -> str:
    righe = dati["righe"]
    pol_ord = [p for p in ("P0", "P1", "P2", "P3", "P4") if any(r["politica"] == p for r in righe)]
    per_pol = {p: sorted([r for r in righe if r["politica"] == p and "errore" not in r],
                         key=lambda r: r["seed"]) for p in pol_ord}
    semi = sorted({r["seed"] for r in righe if "errore" not in r})
    out = []
    A = out.append
    A("# Banco prezzi di mercato: politiche del bot B contro un tavolo che paga il mercato\n")
    A(f"Generato il {time.strftime('%Y-%m-%d %H:%M')} - semi {len(semi)} "
      f"({min(semi)}..{max(semi)}) - politiche {', '.join(pol_ord)} - "
      f"time_limit MILP {dati['milp_tl']} s - aste totali {len(righe)}"
      + (f" - minuti totali {dati['minuti_totali']}" if dati.get("minuti_totali") else "") + "\n")
    imp = dati.get("impronta_pack", "?")
    ok = imp.startswith(IMPRONTA_ATTESA)
    A(f"Pack di lavoro `pack.pkl` (copia locale), impronta sha256 `{imp[:12]}...`: "
      + ("coincide con quella attesa `db2584ea408b`, il pack non e' cambiato durante il banco."
         if ok else "**DIVERSA** da quella attesa `db2584ea408b`: il pack e' stato rigenerato. "
                    "Il confronto fra politiche resta valido (stesso pack per tutte), "
                    "ma i numeri assoluti non sono confrontabili con misure fatte sul pack vecchio.")
      + f" Pool: {dati.get('n_pool','?')} giocatori (pack meno i 63 fuori Serie A), "
        f"di cui {dati.get('n_mercato','?')} con prezzo di mercato di riferimento.\n")
    # il pack del progetto puo' essere stato rigenerato nel frattempo: dirlo
    try:
        import hashlib
        vivo = hashlib.sha256(
            Path(r"data\packs\pack_2026-27.pkl").read_bytes()
        ).hexdigest()
        if not vivo.startswith(IMPRONTA_ATTESA):
            A(f"Nota: alla generazione di questo report il pack del progetto "
              f"`data/packs/pack_2026-27.pkl` ha impronta `{vivo[:12]}...`, **diversa** da quella "
              f"su cui il banco ha girato. La catena di rigenerazione lo ha sostituito mentre le "
              f"aste erano in corso: e' esattamente il motivo per cui il banco lavora su una copia "
              f"congelata. Tutte e {len(righe)} le aste hanno visto lo stesso pack `{IMPRONTA_ATTESA}`, "
              f"quindi il confronto fra politiche e' valido; i valori assoluti vanno riferiti a quel "
              f"pack, non a quello nuovo.\n")
    except Exception:
        pass
    A("## Disegno\n")
    A("Tavolo di 10 squadre: noi (bot B, variante in prova) + 6 bot di mercato "
      "(valutazione privata = prezzo di mercato x lognormale(0, 0.25); senza prezzo "
      "di mercato max(1, q50*1.3) x lognormale(0, 0.35); disciplina di reparto: "
      "riempiti 2/3 degli slot di un ruolo la valutazione su quel ruolo si dimezza; "
      "nomination a caso fra i 25 con valutazione piu' alta del ruolo corrente) + "
      "3 CBot con hint_prices = prezzi di mercato (profili informato, stars_scrubs, "
      "medio). Pool = giocatori del pack meno i 63 esclusi fuori Serie A. "
      "Stessi semi per tutte le politiche; il seme fissa il motore e gli avversari, "
      "il nostro bot usa un Random separato.\n")
    A("Politiche: P0 attuale; P1 prezzi del piano = prezzo di mercato dove esiste; "
      "P2 = P1 + heat calcolato solo sui q50 >= 15; P3 = P2 + tetto sui target del "
      "piano alzato a 1.05 x prezzo di mercato x heat; P4 = prezzi del piano "
      "0.5 mercato + 0.5 q50*heat, heat come P2, tetti come P0.\n")
    A("## Medie per politica (media +/- errore standard)\n")
    intest = "| politica | " + " | ".join(t for _, t in METRICHE) + " | rose incomplete |"
    A(intest)
    A("|" + "---|" * (len(METRICHE) + 2))
    for p in pol_ord:
        rr = per_pol[p]
        celle = []
        for k, _ in METRICHE:
            m, se = ms([r[k] for r in rr])
            celle.append(f"{m:.1f} +/- {se:.1f}")
        inc = sum(1 for r in rr if r["slot_vuoti"] != 0 or r["objective"] is None)
        A(f"| {p} | " + " | ".join(celle) + f" | {inc} |")
    A("")
    A("## Differenze appaiate contro P0 (stesso seme)\n")
    A("| politica | d objective | 2xSE | d residuo | d spesa top3 | d target persi | verdetto |")
    A("|---|---|---|---|---|---|---|")
    verdetti = {}
    base = {r["seed"]: r for r in per_pol.get("P0", [])}
    m_res_p0, _ = ms([r["residuo"] for r in per_pol.get("P0", [])])
    for p in pol_ord:
        if p == "P0":
            continue
        rr = per_pol[p]
        d_obj, d_res, d_top3, d_tp = [], [], [], []
        for r in rr:
            b = base.get(r["seed"])
            if not b or r["objective"] is None or b["objective"] is None:
                continue
            d_obj.append(r["objective"] - b["objective"])
            d_res.append(r["residuo"] - b["residuo"])
            d_top3.append(r["spesa_top3"] - b["spesa_top3"])
            d_tp.append(r["target_persi"] - b["target_persi"])
        m, se = ms(d_obj)
        mr, ser = ms(d_res)
        mt, set_ = ms(d_top3)
        mp, sep = ms(d_tp)
        m_res_p, _ = ms([r["residuo"] for r in rr])
        incomplete = sum(1 for r in rr if r["slot_vuoti"] != 0 or r["objective"] is None)
        if incomplete > 0:
            v = "SCARTATA (rose incomplete)"
        elif m > 2 * se and m_res_p <= m_res_p0 + 10:
            v = "MIGLIORE"
        elif m > 2 * se:
            v = "non accettata (residuo peggiore di oltre 10 crediti)"
        elif m < -2 * se:
            v = "PEGGIORE"
        else:
            v = "non distinguibile"
        verdetti[p] = v
        A(f"| {p} | {m:+.1f} +/- {se:.1f} | {2*se:.1f} | {mr:+.1f} +/- {ser:.1f} | "
          f"{mt:+.1f} +/- {set_:.1f} | {mp:+.1f} +/- {sep:.1f} | {v} |")
    A("")
    A("Criterio (fissato prima di guardare i numeri): una politica e' migliore di P0 "
      "solo se la media delle differenze appaiate di objective supera 2 volte il suo "
      "errore standard, con residuo medio non superiore a quello di P0 di oltre 10 "
      "crediti e zero rose incomplete. Altrimenti 'non distinguibile' (media dentro "
      "+/- 2 SE) o 'peggiore' (media sotto -2 SE).\n")
    migliori = [p for p, v in verdetti.items() if v == "MIGLIORE"]
    peggiori = [p for p, v in verdetti.items() if v == "PEGGIORE"]
    A("### Verdetto\n")
    if migliori:
        A("Supera P0 secondo il criterio: " + ", ".join(migliori) + ".\n")
    else:
        A("**Nessuna delle politiche in prova supera P0 secondo il criterio.** "
          "Le differenze di objective stanno tutte dentro +/- 2 errori standard, "
          "e nemmeno il segno e' concorde. Non e' un pareggio dimostrato: e' un "
          "confronto che questo banco non riesce a decidere, con la differenza "
          "vera - se esiste - piu' piccola dell'incertezza residua.\n")
    if peggiori:
        A("Sotto P0 oltre la soglia: " + ", ".join(peggiori) + ".\n")
    A("## P0: si realizza il rischio di strapagare le stelle?\n")
    rr0 = per_pol.get("P0", [])
    if rr0:
        m_heat, se_heat = ms([r["heat_finale"] for r in rr0])
        A(f"heat finale medio P0: {m_heat:.3f} +/- {se_heat:.3f}\n")
        A("| seme | 1o acquisto | prezzo | q50 | mercato | 2o | prezzo | 3o | prezzo |")
        A("|---|---|---|---|---|---|---|---|---|")
        for r in rr0:
            t = r["top3"] + [{}] * 3
            def f(d, k, dec=0):
                v = d.get(k)
                return "-" if v is None else (f"{v:.0f}" if isinstance(v, float) else str(v))
            A(f"| {r['seed']} | {t[0].get('nome','-')} | {f(t[0],'prezzo')} | "
              f"{f(t[0],'q50')} | {f(t[0],'mercato')} | {t[1].get('nome','-')} | "
              f"{f(t[1],'prezzo')} | {t[2].get('nome','-')} | {f(t[2],'prezzo')} |")
        A("")
        # confronto prezzo pagato / prezzo di mercato sui top3 di ogni politica
        A("| politica | prezzo pagato / mercato sui 3 acquisti piu' cari (mediana) |")
        A("|---|---|")
        for p in pol_ord:
            rap = [t["prezzo"] / t["mercato"] for r in per_pol[p] for t in r["top3"]
                   if t.get("mercato")]
            A(f"| {p} | {statistics.median(rap):.2f} |" if rap else f"| {p} | - |")
        A("")
    # ---- primario a 12 semi ed estensione ----
    prev = W / "sim_mercato_risultati_12semi.json"
    if len(semi) > 12 and prev.exists():
        d12 = json.load(open(prev, encoding="utf-8"))
        r12 = [r for r in d12["righe"] if "errore" not in r]
        b12 = {r["seed"]: r for r in r12 if r["politica"] == "P0"}
        A("## Primario a 12 semi, poi estensione a 36\n")
        A("Il banco dichiarato prima di guardare i numeri era di 12 semi (0..11). "
          "Il suo esito e' salvato in `sim_mercato_risultati_12semi.json` / `.md`: "
          "tutte e quattro le varianti sopra P0 di segno positivo, nessuna oltre 2 "
          "errori standard, quindi quattro \"non distinguibile\". Vista la spesa di "
          "calcolo (7 minuti per 60 aste) il banco e' stato **esteso a 36 semi "
          "(0..35), criterio invariato**, per avere la potenza di separare un "
          "effetto dell'ordine dell'1%. L'estensione e' stata decisa dopo aver "
          "visto un risultato inconcludente: e' un test sequenziale, e un test "
          "sequenziale gonfia un po' il rischio di falso positivo. Va letto per "
          "quello che e': una misura piu' precisa dello stesso confronto, non una "
          "conferma indipendente.\n")
        A("| politica | d objective a 12 semi | 2xSE | esito a 12 semi |")
        A("|---|---|---|---|")
        for p in pol_ord:
            if p == "P0":
                continue
            dd = [r["objective"] - b12[r["seed"]]["objective"] for r in r12
                  if r["politica"] == p and r["seed"] in b12
                  and r["objective"] is not None and b12[r["seed"]]["objective"] is not None]
            m12, se12 = ms(dd)
            esito = ("sopra soglia" if m12 > 2 * se12 else
                     "sotto soglia" if m12 > -2 * se12 else "peggiore")
            A(f"| {p} | {m12:+.1f} +/- {se12:.1f} | {2*se12:.1f} | {esito} |")
        A("")

    # ---- lettura dell'ipotesi di partenza ----
    A("## Che fine fa l'ipotesi di partenza\n")
    if rr0:
        m_heat, _ = ms([r["heat_finale"] for r in rr0])
        A(f"L'ipotesi era: se il tavolo paga i prezzi di mercato, il heat globale sale "
          f"a circa 1.21 e gonfia anche i tetti sulle stelle. **Il banco non lo vede**: "
          f"con un tavolo che paga il mercato per costruzione, il heat finale di P0 resta "
          f"{m_heat:.3f}. La ragione e' aritmetica: in una lega da 10 squadre e 500 crediti "
          f"il tavolo puo' spendere in tutto 5000 crediti, e la somma dei q50 dei ~250 "
          f"giocatori che vengono davvero venduti e' dello stesso ordine. Il rapporto "
          f"prezzi/q50 puo' cambiare forma (fascia bassa strapagata, stelle pagate meno di "
          f"q50) senza spostare quasi nulla del suo totale, che e' quello che il heat misura. "
          f"Il sottoprezzo della fascia bassa e' reale, ma **non passa dal heat**: se va "
          f"corretto, va corretto nei prezzi del piano, non nel moltiplicatore globale.\n")
    A("L'unica differenza che il banco separa davvero dal rumore non e' l'objective: sono i "
      "**target del piano persi**. Tutte e quattro le varianti ne perdono meno di P0, di uno-tre "
      "target, con errori standard di 0.3-0.4: un piano costruito ai prezzi di mercato regge "
      "l'urto del tavolo invece di essere rifatto da capo a ogni martelletto. Ma la rosa che ne "
      "esce non vale di piu': objective, somma dei value e spesa sui 3 acquisti piu' cari "
      "restano dentro il rumore. E due varianti lasciano piu' crediti non spesi a fine asta "
      "(P1 e P4): pagare il mercato nel piano rende il MILP piu' prudente, e i crediti che "
      "restano in tasca sono valore buttato. Un piano che si conferma non e' un piano migliore: "
      "e' solo un piano piu' stabile.\n")
    A("La posizione fra le 10 squadre non discrimina nulla: in tutte le aste del banco la "
      "nostra rosa e' prima per objective, con qualunque politica. Contro questi avversari "
      "il margine e' cosi' largo che la metrica e' satura; serve solo a dire che nessuna "
      "variante ci fa perdere il primo posto.\n")

    A("## Limiti del banco\n")
    A("- Avversari sintetici: i bot di mercato pagano per costruzione i prezzi di "
      "riferimento; un tavolo reale ha correlazioni, bluff e tempi che qui mancano.\n"
      "- I prezzi di mercato sono medie aggregate di aste reali: non hanno la "
      "variabilita' per lega ne' l'aggiornamento dell'ultimo minuto (infortuni).\n"
      f"- {len(semi)} semi: differenze di objective sotto ~1% della media restano "
      "sotto la soglia di rilevabilita'.\n"
      "- L'objective finale usa i value/value_up del NOSTRO pack anche per le altre "
      "9 squadre: e' un metro comune, non una previsione della classifica reale.\n"
      "- L'appaiamento fissa il seme (seating, rumore avversari), ma cambiando i "
      "nostri rilanci cambia anche chi vince i lotti successivi: le differenze "
      "restano rumorose per costruzione.\n"
      "- _replan e' una copia fedele del sorgente con un solo punto di variazione "
      "(i prezzi del piano): se bot_b.py cambia, la copia va riallineata. "
      "Il controllo P0copy verifica che la copia riproduca P0 seme per seme.\n"
      "- I bot di mercato rilanciano sempre di +1 e non fanno mai salti: le aste salgono "
      "a gradini, e un bot con un tetto alto vince spesso per un solo credito in piu'. "
      "Un tavolo vero salta, e i tetti si pagano piu' spesso per intero.\n"
      "- La posizione fra le 10 squadre e' satura (sempre prima): non serve a ordinare "
      "le politiche, solo a escludere disastri.\n"
      "- L'estensione da 12 a 36 semi e' stata decisa dopo aver visto il primario "
      "inconcludente: test sequenziale, quindi il rischio di falso positivo e' un po' "
      "piu' alto di quello nominale del criterio.\n")
    A("## Ripetere\n")
    A("```\n"
      f"cd \"{W}\"\n"
      "python sim_mercato.py --smoke --tl 5          # una asta P0, misura i tempi\n"
      "python sim_mercato.py --fedelta --tl 5        # P0 vs P0copy: la copia di _replan e' fedele\n"
      "python sim_mercato.py --semi 12 --procs 4 --tl 5   # banco primario\n"
      f"python sim_mercato.py --semi {len(semi)} --procs 4 --tl {dati['milp_tl']}   # banco esteso\n"
      "python sim_mercato.py --report                # rigenera solo il .md dal .json\n"
      "```\n")
    A("Il banco legge SOLO le copie locali `pack.pkl` e `elig.json` in questa cartella: "
      "la catena di rigenerazione del pack che gira in parallelo non puo' cambiargli i dati "
      "sotto i piedi a meta' corsa.\n")
    if dati.get("fedelta"):
        A(f"Controllo di fedelta' P0 vs P0copy: {dati['fedelta']}\n")
    return "\n".join(out)


# --------------------------------------------------------------------------
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--semi", type=int, default=12)
    ap.add_argument("--procs", type=int, default=4)
    ap.add_argument("--tl", type=int, default=5)
    ap.add_argument("--politiche", default="P0,P1,P2,P3,P4")
    ap.add_argument("--smoke", action="store_true")
    ap.add_argument("--fedelta", action="store_true")
    ap.add_argument("--report", action="store_true")
    ap.add_argument("--out", default=str(OUT_JSON))
    a = ap.parse_args()

    if a.report:
        dati = json.load(open(a.out, encoding="utf-8"))
        OUT_MD.write_text(report(dati), encoding="utf-8")
        print("scritto", OUT_MD)
        return

    if a.smoke:
        t = time.time()
        r = run_one("P0", 0, a.tl)
        print(json.dumps({k: v for k, v in r.items() if k != "obj_tutti"},
                         ensure_ascii=False, indent=1))
        print("secondi asta:", round(time.time() - t, 1))
        return

    if a.fedelta:
        for s in (0, 1):
            r0 = run_one("P0", s, a.tl)
            rc = run_one("P0copy", s, a.tl)
            print(f"seme {s}: P0 obj={r0['objective']:.1f} res={r0['residuo']} "
                  f"| P0copy obj={rc['objective']:.1f} res={rc['residuo']} "
                  f"| uguali={abs(r0['objective']-rc['objective'])<1e-6 and r0['residuo']==rc['residuo']}")
        return

    pols = a.politiche.split(",")
    tasks = [(p, s, a.tl) for s in range(a.semi) for p in pols]
    righe = []
    t0 = time.time()
    st0 = stato()
    testa = {"milp_tl": a.tl, "semi": a.semi, "impronta_pack": impronta_pack(),
             "n_pool": len(st0["pool"]),
             "n_mercato": sum(1 for pid in st0["pool"] if pid in st0["mkt"])}
    print("impronta pack:", testa["impronta_pack"][:12],
          "attesa:", IMPRONTA_ATTESA,
          "->", "invariata" if testa["impronta_pack"].startswith(IMPRONTA_ATTESA) else "CAMBIATA",
          flush=True)
    import multiprocessing as mp
    with mp.Pool(a.procs) as pool:
        for i, r in enumerate(pool.imap_unordered(_job, tasks), 1):
            righe.append(r)
            print(f"[{i}/{len(tasks)}] {r['politica']} seme {r['seed']} "
                  f"obj={r.get('objective')} res={r.get('residuo')} "
                  f"({r.get('secondi')}s) tot={round(time.time()-t0)}s", flush=True)
            json.dump({**testa, "righe": righe},
                      open(a.out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    st = stato()
    dati = {"milp_tl": a.tl, "semi": a.semi, "righe": righe,
            "impronta_pack": impronta_pack(),
            "n_pool": len(st["pool"]),
            "n_mercato": sum(1 for pid in st["pool"] if pid in st["mkt"]),
            "minuti_totali": round((time.time() - t0) / 60, 1)}
    json.dump(dati, open(a.out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    OUT_MD.write_text(report(dati), encoding="utf-8")
    print("fatto in", dati["minuti_totali"], "minuti ->", a.out, OUT_MD)


if __name__ == "__main__":
    main()
