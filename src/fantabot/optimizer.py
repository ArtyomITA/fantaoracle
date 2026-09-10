"""Ottimizzatore rosa: MILP (PuLP/CBC) con scelta del modulo + greedy.

Modello lineare:
  x_i in {0,1}  acquisto (i posseduti sono fissati a 1 con prezzo 0)
  s_i in {0,1}  titolare, s_i <= x_i
  m_k in {0,1}  modulo scelto (uno solo tra i 7 classic)
  per ruolo: somma s_i = somma_k m_k * slot_k(ruolo)
Obiettivo: somma v_i * (w_b x_i + (1 - w_b) s_i), con v_i = valore atteso
(+ lam * upside se fornito): la stagione premia gli 11 migliori per giornata,
la panchina vale una frazione. CBC risolve in decine di ms.
"""
from __future__ import annotations

import pulp

from .models import ROLES, Player

MODULES = {"3-4-3": (3, 4, 3), "3-5-2": (3, 5, 2), "4-3-3": (4, 3, 3),
           "4-4-2": (4, 4, 2), "4-5-1": (4, 5, 1), "5-3-2": (5, 3, 2),
           "5-4-1": (5, 4, 1)}
BENCH_WEIGHT = 0.30
STARTER_SLOTS = {"P": 1, "D": 4, "C": 4, "A": 2}   # retrocompatibilita'


def optimize_roster(candidates: dict[str, Player],
                    prices: dict[str, float],
                    values: dict[str, float],
                    quotas: dict[str, int],
                    budget: float,
                    forced_spend: dict[str, tuple[float, float]] | None = None,
                    fixed: dict[str, Player] | None = None,
                    values_up: dict[str, float] | None = None,
                    lam: float = 0.0,
                    bench_weight: float = BENCH_WEIGHT,
                    time_limit: int = 10,
                    starters_owned=None,
                    min_spend: float | None = None,
                    required: set | None = None,
                    banned: set | None = None,
                    required_starters: set | None = None) -> dict | None:
    """candidates: pool disponibile (venduti esclusi). fixed: giocatori gia'
    posseduti (x=1, prezzo 0). quotas = quote PIENE della rosa; budget =
    crediti residui. forced_spend: ruolo -> (min, max) spesa sui soli acquisti.
    values_up/lam: v_i = value + lam * (value_up - value).

    `required`: giocatori che la rosa DEVE comprare, al loro prezzo pieno —
    non vanno in `fixed`, che li metterebbe a costo zero come se fossero gia'
    nostri. `banned`: giocatori da escludere. `required_starters`: obbligo di
    titolarita' nel modulo scelto.

    Ritorna `{"roster", "starters", "module", "value", "objective", "cost"}`
    oppure `None` se non esiste una rosa ammissibile.

    `value` e' la somma grezza dei valori dei 25; `objective` e' il valore
    della funzione **davvero massimizzata**, che pesa titolari e panchina in
    modo diverso e include `lam`. Ordinare due piani col primo numero mentre
    il solutore ottimizza il secondo significa confrontarli con un metro che
    non e' quello usato per costruirli."""
    fixed = fixed or {}
    allp = {**candidates, **fixed}
    v = {pid: values.get(pid, 0.0) for pid in allp}
    if values_up and lam:
        v = {pid: v[pid] + lam * (values_up.get(pid, v[pid]) - v[pid]) for pid in allp}
    prob = pulp.LpProblem("rosa", pulp.LpMaximize)
    x = {pid: pulp.LpVariable(f"x_{pid}", cat="Binary") for pid in allp}
    s = {pid: pulp.LpVariable(f"s_{pid}", cat="Binary") for pid in allp}
    m = {k: pulp.LpVariable("m_" + k.replace("-", "_"), cat="Binary") for k in MODULES}
    prob += pulp.lpSum(v[pid] * (bench_weight * x[pid] + (1 - bench_weight) * s[pid])
                       for pid in allp)
    cost = {pid: (0.0 if pid in fixed else max(1.0, prices.get(pid, 1.0))) for pid in allp}
    prob += pulp.lpSum(cost[pid] * x[pid] for pid in candidates) <= budget
    if min_spend:
        # soglia di spesa: si tiene comunque un credito per ogni slot ancora da
        # riempire, cosi' la rosa resta completabile
        slot_da_riempire = sum(quotas[r] for r in ROLES) - len(fixed)
        soglia = min(float(min_spend), budget - max(0, slot_da_riempire - 1))
        if soglia > 0:
            prob += pulp.lpSum(cost[pid] * x[pid] for pid in candidates) >= soglia
    prob += pulp.lpSum(m.values()) == 1
    by_role: dict[str, list[str]] = {r: [] for r in ROLES}
    for pid, p in allp.items():
        by_role[p.role].append(pid)
    slot_of = {"P": {k: 1 for k in MODULES},
               "D": {k: d for k, (d, c, a) in MODULES.items()},
               "C": {k: c for k, (d, c, a) in MODULES.items()},
               "A": {k: a for k, (d, c, a) in MODULES.items()}}
    for r in ROLES:
        prob += pulp.lpSum(x[pid] for pid in by_role[r]) == quotas[r]
        prob += pulp.lpSum(s[pid] for pid in by_role[r]) == \
            pulp.lpSum(m[k] * slot_of[r][k] for k in MODULES)
        if forced_spend and r in forced_spend:
            lo, hi = forced_spend[r]
            role_cost = pulp.lpSum(cost[pid] * x[pid] for pid in by_role[r] if pid in candidates)
            prob += role_cost >= lo
            prob += role_cost <= hi
    for pid in allp:
        prob += s[pid] <= x[pid]
    for pid in fixed:
        prob += x[pid] == 1
    for pid in (required or ()):
        if pid in allp:
            prob += x[pid] == 1
    for pid in (banned or ()):
        if pid in allp:
            prob += x[pid] == 0
    for pid in (required_starters or ()):
        if pid in allp:
            prob += s[pid] == 1
    status = prob.solve(pulp.PULP_CBC_CMD(msg=0, timeLimit=time_limit))
    if pulp.LpStatus[status] != "Optimal":
        return None
    chosen = [pid for pid in allp if x[pid].value() and x[pid].value() > 0.5]
    starters = {pid for pid in allp if s[pid].value() and s[pid].value() > 0.5}
    module = next(k for k in MODULES if m[k].value() and m[k].value() > 0.5)
    # il valore della funzione DAVVERO massimizzata, ricalcolato dalla
    # soluzione: e' il numero con cui due piani si confrontano
    obiettivo = sum(v[pid] * (bench_weight + (1 - bench_weight)
                              * (1.0 if pid in starters else 0.0))
                    for pid in chosen)
    return {
        "roster": {r: [pid for pid in chosen if allp[pid].role == r] for r in ROLES},
        "starters": starters, "module": module,
        "value": sum(values.get(pid, 0.0) for pid in chosen),
        "objective": obiettivo,
        "objective_from_solver": pulp.value(prob.objective),
        "cost": sum(cost[pid] for pid in chosen),
        "feasible": True,
    }


def greedy_roster(candidates: dict[str, Player], prices: dict[str, float],
                  values: dict[str, float], quotas: dict[str, int],
                  budget: float) -> dict:
    """Riempimento veloce per efficienza valore/prezzo (fallback).

    ## Il difetto corretto

    Il secondo ciclo — quello che completava le quote rimaste — **non
    ricontrollava il budget**. Con budget 5, un solo slot d'attacco e un
    candidato da 10, restituiva una rosa da 10 crediti: illegale, e presentata
    come valida. Prova salvata: `prova_greedy_budget.json`.

    Adesso il completamento rispetta il budget come il primo ciclo. Se non
    esiste un completamento sostenibile ai prezzi usati, il risultato porta
    `feasible: False` e le quote mancanti: **non fattibile** e' una risposta,
    una rosa illegale no.
    """
    remaining = dict(quotas)
    chosen: list[str] = []
    spend = 0.0

    def sostenibile(pid: str) -> bool:
        """Comprarlo lascia almeno un credito per ogni slot che resta?"""
        costo = max(1.0, prices.get(pid, 1.0))
        slot_dopo = sum(remaining.values()) - 1
        return spend + costo + slot_dopo <= budget

    ranked = sorted(candidates.values(),
                    key=lambda p: -(values.get(p.player_id, 0.0)
                                    / max(1.0, prices.get(p.player_id, 1.0))))
    for p in ranked:
        if remaining[p.role] <= 0 or not sostenibile(p.player_id):
            continue
        chosen.append(p.player_id)
        remaining[p.role] -= 1
        spend += max(1.0, prices.get(p.player_id, 1.0))
    # completamento: prima i piu' economici, e SEMPRE dentro il budget
    for p in sorted(candidates.values(), key=lambda p: prices.get(p.player_id, 1.0)):
        if p.player_id in chosen or remaining[p.role] <= 0:
            continue
        if not sostenibile(p.player_id):
            continue
        chosen.append(p.player_id)
        remaining[p.role] -= 1
        spend += max(1.0, prices.get(p.player_id, 1.0))

    mancanti = {r: n for r, n in remaining.items() if n > 0}
    return {"roster": {r: [pid for pid in chosen if candidates[pid].role == r]
                       for r in ROLES},
            "starters": set(), "module": "4-4-2",
            "value": sum(values.get(pid, 0.0) for pid in chosen),
            "objective": None,        # il greedy non ottimizza quella funzione
            "cost": spend,
            "feasible": not mancanti,
            "quote_mancanti": mancanti,
            "nota": ("" if not mancanti else
                     f"nessun completamento sostenibile con budget {budget}: "
                     f"restano {mancanti}. Una rosa incompleta e' un esito, "
                     "non un errore da nascondere.")}
