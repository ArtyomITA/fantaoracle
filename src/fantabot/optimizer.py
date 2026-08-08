"""Ottimizzatore rosa: MILP (PuLP/CBC) + euristica greedy veloce.

Il MILP e' il replanner di B: max punti attesi con vincoli budget e slot,
giocatori gia' posseduti bloccati, venduti esclusi. Con ~600 variabili CBC
risolve in decine di ms; durante l'asta B lo rilancia solo sugli eventi
rilevanti e usa il greedy tra un replan e l'altro.
"""
from __future__ import annotations

import pulp

from .models import ROLES, Player


# slot da titolare per ruolo su un modulo "medio" (4-4-2): la stagione premia
# i migliori 11 per giornata, non la somma dei 25; la panchina vale una
# frazione (subentri con max 3 cambi + rotazioni)
STARTER_SLOTS = {"P": 1, "D": 4, "C": 4, "A": 2}
BENCH_WEIGHT = 0.30


def optimize_roster(candidates: dict[str, Player],
                    prices: dict[str, float],
                    values: dict[str, float],
                    quotas: dict[str, int],
                    budget: float,
                    forced_spend: dict[str, tuple[float, float]] | None = None,
                    starters_owned: dict[str, int] | None = None,
                    time_limit: int = 10) -> dict | None:
    """candidates: pool ancora disponibile (esclusi venduti e gia' posseduti).
    quotas/budget: SLOT RESIDUI e CREDITI RESIDUI (il chiamante scala i suoi
    acquisti prima di chiamare). prices: prezzo atteso; values: punti attesi.
    forced_spend: ruolo -> (min, max) spesa, per generare scenari diversi.
    starters_owned: slot da titolare gia' coperti dai giocatori posseduti
    (il chiamante li stima, es. contando i suoi acquisti forti per ruolo).

    Obiettivo a due livelli: gli s_i "titolari" pesano pieno, il resto della
    rosa pesa BENCH_WEIGHT. Tutto lineare, CBC lo mangia in decine di ms.
    Ritorna {"roster", "starters", "value", "cost"} o None."""
    starters_owned = starters_owned or {}
    prob = pulp.LpProblem("rosa", pulp.LpMaximize)
    x = {pid: pulp.LpVariable(f"x_{pid}", cat="Binary") for pid in candidates}
    s = {pid: pulp.LpVariable(f"s_{pid}", cat="Binary") for pid in candidates}
    prob += pulp.lpSum(
        values.get(pid, 0.0) * (BENCH_WEIGHT * x[pid] + (1 - BENCH_WEIGHT) * s[pid])
        for pid in candidates)
    prob += pulp.lpSum(prices.get(pid, 1.0) * x[pid] for pid in candidates) <= budget
    by_role: dict[str, list[str]] = {r: [] for r in ROLES}
    for pid, p in candidates.items():
        by_role[p.role].append(pid)
    for r in ROLES:
        prob += pulp.lpSum(x[pid] for pid in by_role[r]) == quotas[r]
        starter_need = max(0, STARTER_SLOTS[r] - starters_owned.get(r, 0))
        prob += pulp.lpSum(s[pid] for pid in by_role[r]) == min(starter_need, quotas[r])
        if forced_spend and r in forced_spend:
            lo, hi = forced_spend[r]
            role_cost = pulp.lpSum(prices.get(pid, 1.0) * x[pid] for pid in by_role[r])
            prob += role_cost >= lo
            prob += role_cost <= hi
    for pid in candidates:
        prob += s[pid] <= x[pid]
    status = prob.solve(pulp.PULP_CBC_CMD(msg=0, timeLimit=time_limit))
    if pulp.LpStatus[status] != "Optimal":
        return None
    chosen = [pid for pid in candidates if x[pid].value() and x[pid].value() > 0.5]
    starters = [pid for pid in candidates if s[pid].value() and s[pid].value() > 0.5]
    return {
        "roster": {r: [pid for pid in chosen if candidates[pid].role == r] for r in ROLES},
        "starters": set(starters),
        "value": sum(values.get(pid, 0.0) for pid in chosen),
        "cost": sum(prices.get(pid, 1.0) for pid in chosen),
    }


def greedy_roster(candidates: dict[str, Player], prices: dict[str, float],
                  values: dict[str, float], quotas: dict[str, int],
                  budget: float) -> dict:
    """Riempimento veloce per efficienza valore/prezzo, usato tra due replan.
    Non ottimo ma sempre fattibile: garantisce slot pieni nel budget."""
    remaining = dict(quotas)
    chosen: list[str] = []
    spend = 0.0
    ranked = sorted(candidates.values(),
                    key=lambda p: -(values.get(p.player_id, 0.0)
                                    / max(1.0, prices.get(p.player_id, 1.0))))
    # prima passata: efficienza; seconda: completa con i piu' economici
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
            "value": sum(values.get(pid, 0.0) for pid in chosen),
            "cost": spend}
