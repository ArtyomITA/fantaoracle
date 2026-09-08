"""Confronto sintetico del piano B sui voti REALI di una stagione passata.

Costruisce il piano con l'obiettivo scelto (pack.b_objective), lo prezza al
MERCATO (ref_price, non alle stime del modello), e lo gioca contro gli
archetipi STELLE / GUIDA / MEDIO a 500 crediti reali, con le regole della
lega (modificatore, porta inviolata, 3 cambi), 300 calendari H2H.

## Che cosa NON e' (leggere prima di citarne i numeri)

Il tavolo qui e' di **otto squadre** (due varianti del piano piu' sei
archetipi), non di dieci, e soprattutto le rose sono generate **in modo
indipendente**: lo stesso giocatore puo' stare in piu' squadre insieme. In
un'asta vera ogni calciatore appartiene a una sola squadra, e questo cambia sia
i punteggi sia la classifica.

Quindi la colonna `quota_vittorie` **non e' la probabilita' di vincere la lega
a dieci**. E' la quota di calendari in cui quella rosa arriva prima in un
confronto sintetico a otto con proprieta' non esclusiva. Serve a ordinare
varianti dello stesso piano, non a promettere un risultato.

Uso: python scripts/f13_validate_plan.py [stagione=2025-26]
Criterio: la quota di vittorie del piano non deve stare sotto quella degli
archetipi, e il costo di mercato non deve superare 500.
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
from fantabot.rules import MIN_SPEND_FRAC  # noqa: E402
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
    # piano iniziale: deve impegnare quasi tutto il budget (i crediti che
    # restano in cassa a fine asta valgono zero)
    soglia = MIN_SPEND_FRAC * pack.budget
    plan = optimize_roster(pack.players, prices, values, pack.quotas, pack.budget,
                           forced_spend=forced, values_up=values_up,
                           lam=obj.get("lam", 0.0), min_spend=soglia)
    # variante "onesta": stesso obiettivo ma prezzi = MERCATO (cio' che pagheresti davvero)
    plan_mkt = optimize_roster(pack.players, ref, values, pack.quotas, pack.budget,
                               forced_spend=forced, values_up=values_up,
                               lam=obj.get("lam", 0.0), min_spend=soglia)
    if plan is None or plan_mkt is None:
        raise SystemExit(f"BLOCCO: nessuna rosa impegna almeno {soglia:.0f} crediti "
                         f"rispettando quote e quota d'attacco")
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
    print(f"CONFRONTO SINTETICO a {len(rosters)} squadre, rose generate in modo "
          "indipendente (lo stesso giocatore puo' stare in piu' squadre).")
    print("La quota di vittorie NON e' la probabilita' di vincere la lega a "
          "dieci con proprieta' esclusiva.")
    condivisi = {}
    for k, ro in rosters.items():
        for r in ROLES:
            for pid in ro[r]:
                condivisi[pid] = condivisi.get(pid, 0) + 1
    doppi = sum(1 for v in condivisi.values() if v > 1)
    print(f"  giocatori presenti in piu' di una rosa: {doppi} su "
          f"{len(condivisi)}")
    for k, ro in rosters.items():
        cost = sum(ref[p] for r in ROLES for p in ro[r])
        sc = np.array(res.giornata_scores[k])
        att = [pack.players[p].name for p in ro["A"][:3]]
        print(f"  {k:18s} costo mercato {cost:4.0f} | punti {res.total_points[k]:5.0f} "
              f"| media {sc.mean():5.1f} sd {sc.std():4.1f} | quota vittorie "
              f"{win[k]:5.1%} rank {rank[k]:.2f} | A: {att}")


if __name__ == "__main__":
    main()
