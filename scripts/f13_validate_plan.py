"""Validazione onesta del piano B sui voti REALI di una stagione passata.

Costruisce il piano con l'obiettivo scelto (pack.b_objective), lo prezza al
MERCATO (ref_price, non alle stime del modello), e lo gioca contro gli
archetipi STELLE / GUIDA / MEDIO a 500 crediti reali, con le regole della
lega (modificatore, porta inviolata, 3 cambi), 300 calendari H2H.

Uso: python scripts/f13_validate_plan.py [stagione=2025-26]
Criterio: P(win) del piano >= archetipi e costo di mercato <= 500.
"""
from __future__ import annotations

import pickle
import random
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from fantabot.models import ROLES  # noqa: E402
from fantabot.montecarlo import archetype_rosters  # noqa: E402
from fantabot.optimizer import optimize_roster  # noqa: E402
from fantabot.season.simulate import simulate_season  # noqa: E402


def main():
    season = sys.argv[1] if len(sys.argv) > 1 else "2025-26"
    with open(ROOT / "data" / "packs" / f"pack_{season}.pkl", "rb") as f:
        pack = pickle.load(f)
    preds = pack.b_predictions
    obj = getattr(pack, "b_objective", None) or {}
    ref = {pid: max(1.0, p.ref_price * pack.budget) for pid, p in pack.players.items()}
    # prezzi che B si aspetta di pagare: q50 (per la stagione corrente gia'
    # misti col mercato); il COSTO REALE del piano e' al ref di mercato
    prices = {pid: max(1.0, float(preds.get(pid, {}).get("q50", 1.0))) for pid in pack.players}
    values = {pid: float(preds.get(pid, {}).get("value", 0.0)) for pid in pack.players}
    values_up = {pid: float(preds.get(pid, {}).get("value_up", values[pid])) for pid in pack.players}
    forced = None
    if obj.get("attack_share"):
        lo, hi = obj["attack_share"]
        forced = {"A": (lo * pack.budget, hi * pack.budget)}
    plan = optimize_roster(pack.players, prices, values, pack.quotas, pack.budget,
                           forced_spend=forced, values_up=values_up,
                           lam=obj.get("lam", 0.0))
    # variante "onesta": stesso obiettivo ma prezzi = MERCATO (cio' che pagheresti davvero)
    plan_mkt = optimize_roster(pack.players, ref, values, pack.quotas, pack.budget,
                               forced_spend=forced, values_up=values_up,
                               lam=obj.get("lam", 0.0))
    rng = random.Random(7)
    opps = archetype_rosters(pack.players, ref, pack.quotas, pack.budget, rng, n=6, preds=preds)
    rosters = {"PIANO_B(q50)": plan["roster"], "PIANO_B(mercato)": plan_mkt["roster"]}
    for i, o in enumerate(opps):
        rosters[["STELLE", "GUIDA", "MEDIO"][i % 3] + str(i // 3 + 1)] = o
    res = simulate_season(rosters, pack.votes_by_g, n_calendars=300, seed=3,
                          voti_by_g=pack.voti_by_g, use_mod_difesa=True)
    win, rank = res.h2h_win_rate(), res.h2h_avg_rank()
    print(f"stagione {season} | obiettivo {obj.get('lam', 0)} / attacco {obj.get('attack_share')} "
          f"| modulo piano {plan['module']}")
    for k, ro in rosters.items():
        cost = sum(ref[p] for r in ROLES for p in ro[r])
        sc = np.array(res.giornata_scores[k])
        att = [pack.players[p].name for p in ro["A"][:3]]
        print(f"  {k:18s} costo mercato {cost:4.0f} | punti {res.total_points[k]:5.0f} "
              f"| media {sc.mean():5.1f} sd {sc.std():4.1f} | win {win[k]:5.1%} rank {rank[k]:.2f} | A: {att}")


if __name__ == "__main__":
    main()
