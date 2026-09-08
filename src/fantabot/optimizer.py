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
                    min_spend: float | None = None) -> dict | None:
    """candidates: pool disponibile (venduti esclusi). fixed: giocatori gia'
    posseduti (x=1, prezzo 0). quotas = quote PIENE della rosa; budget =
    crediti residui. forced_spend: ruolo -> (min, max) spesa sui soli acquisti.
    values_up/lam: v_i = value + lam * (value_up - value).
    Ritorna {"roster", "starters", "module", "value", "cost"} o None."""
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
    status = prob.solve(pulp.PULP_CBC_CMD(msg=0, timeLimit=time_limit))
    if pulp.LpStatus[status] != "Optimal":
        return None
    chosen = [pid for pid in allp if x[pid].value() and x[pid].value() > 0.5]
    starters = {pid for pid in allp if s[pid].value() and s[pid].value() > 0.5}
    module = next(k for k in MODULES if m[k].value() and m[k].value() > 0.5)
    return {
        "roster": {r: [pid for pid in chosen if allp[pid].role == r] for r in ROLES},
        "starters": starters, "module": module,
        "value": sum(values.get(pid, 0.0) for pid in chosen),
        "cost": sum(cost[pid] for pid in chosen),
    }


def greedy_roster(candidates: dict[str, Player], prices: dict[str, float],
                  values: dict[str, float], quotas: dict[str, int],
                  budget: float) -> dict:
    """Riempimento veloce per efficienza valore/prezzo (fallback)."""
    remaining = dict(quotas)
    chosen: list[str] = []
    spend = 0.0
    ranked = sorted(candidates.values(),
                    key=lambda p: -(values.get(p.player_id, 0.0)
                                    / max(1.0, prices.get(p.player_id, 1.0))))
    for p in ranked:
        if remaining[p.role] <= 0:
            continue
        cost = max(1.0, prices.get(p.player_id, 1.0))
        slots_after = sum(remaining.values()) - 1
        if spend + cost + slots_after > budget:
            continue
        chosen.append(p.player_id)
        remaining[p.role] -= 1
        spend += cost
    for p in sorted(candidates.values(), key=lambda p: prices.get(p.player_id, 1.0)):
        if p.player_id in chosen or remaining[p.role] <= 0:
            continue
        chosen.append(p.player_id)
        remaining[p.role] -= 1
        spend += max(1.0, prices.get(p.player_id, 1.0))
    return {"roster": {r: [pid for pid in chosen if candidates[pid].role == r]
                       for r in ROLES},
            "starters": set(), "module": "4-4-2",
            "value": sum(values.get(pid, 0.0) for pid in chosen),
            "cost": spend}
