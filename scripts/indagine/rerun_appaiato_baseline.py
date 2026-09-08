"""Confronto onesto fra la rosa di partenza e quella attuale.

Il 39% di P(1o) misurato all'inizio e il 53% di adesso vengono da due banchi
diversi: nel frattempo sono cambiati la disponibilita' (memoria della durata),
i numeri casuali (indicizzati per giocatore), la formazione (niente futuro) e
l'effetto squadra. Confrontare quei due numeri non dice nulla.

Qui le due ROSE, quella di partenza e quella scelta oggi, vengono giocate sullo
STESSO banco corretto: stessi scenari, stessi avversari, stesso calendario. E
poi rigiocate su scenari mai usati.

Uso: python scripts/indagine/rerun_appaiato_baseline.py [--sims 100]
"""
from __future__ import annotations

import json
import pickle
import random
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from fantabot.models import ROLES  # noqa: E402
from fantabot.montecarlo import (archetype_rosters, build_dists, calendari,  # noqa: E402
                                 p_first, simulate_roster)

# rosa scelta il 5/9 prima dei fix (da data/baseline_20260905/chain_coldstart_0327.log)
ROSA_PARTENZA = {
    "P": ["Mandas", "Okoye", "Falcone"],
    "D": ["Wesley", "Solet", "Ostigard", "Vasquez", "Valeri", "Obert", "Tavares N.", "Gallo"],
    "C": ["Zaccagni", "Atta", "Ekkelenkamp", "Frattesi", "Adopo", "Coulibaly L.",
          "Ellertsson", "Pierotti"],
    "A": ["Ramos G.", "Laurientè", "Pellegrino M.", "Colombo", "Varela G.", "Kvernadze"],
}


def per_nome(players):
    d = {}
    for pid, p in players.items():
        d.setdefault((p.name, p.role), pid)
    return d


def main():
    args = sys.argv[1:]
    n_sims = int(args[args.index("--sims") + 1]) if "--sims" in args else 100
    pack = pickle.load(open(ROOT / "data" / "packs" / "pack_2026-27.pkl", "rb"))
    idx = per_nome(pack.players)
    partenza, mancanti = {}, []
    for r, nomi in ROSA_PARTENZA.items():
        partenza[r] = []
        for n in nomi:
            pid = idx.get((n, r))
            if pid is None:
                mancanti.append(f"{n} ({r})")
            else:
                partenza[r].append(pid)
    if mancanti:
        print(f"BLOCCO: non trovo nel listone {mancanti}")
        return
    obj = getattr(pack, "b_objective", None) or {}
    attuale = obj.get("roster")
    if attuale is None:
        from fantabot.optimizer import optimize_roster
        from fantabot.rules import MIN_SPEND_FRAC
        preds = pack.b_predictions
        prezzi = {p: max(1.0, float(preds.get(p, {}).get("q50", 1.0))) for p in pack.players}
        val = {p: float(preds.get(p, {}).get("value", 0.0)) for p in pack.players}
        vup = {p: float(preds.get(p, {}).get("value_up", val[p])) for p in pack.players}
        lo, hi = obj.get("attack_share", (0.35, 0.5))
        sol = optimize_roster(pack.players, prezzi, val, pack.quotas, pack.budget,
                              forced_spend={"A": (lo * pack.budget, hi * pack.budget)},
                              values_up=vup, lam=obj.get("lam", 0.0),
                              min_spend=MIN_SPEND_FRAC * pack.budget)
        attuale = sol["roster"]

    prev = pickle.load(open(ROOT / "data" / "packs" / "pack_2025-26.pkl", "rb"))
    dists = build_dists(pack.players, pack.b_predictions, [prev.votes_by_g],
                        [prev.voti_by_g or []])
    ref = {pid: max(1.0, p.ref_price * pack.budget) for pid, p in pack.players.items()}
    rng = random.Random(1)
    opps = archetype_rosters(pack.players, ref, pack.quotas, pack.budget, rng,
                             preds=pack.b_predictions)
    out = {}
    for etichetta, seed in [("banco di confronto", 7001), ("verifica indipendente", 7002)]:
        opp_sc = [simulate_roster(o, dists, n_sims, rng, seed_scenari=seed) for o in opps]
        cal = calendari(len(opps) + 1, n_sims, seed)
        print(f"\n=== {etichetta} ({n_sims} scenari, stessi avversari e calendario) ===")
        for nome, ro in [("rosa di partenza (5/9)", partenza), ("rosa di oggi", attuale)]:
            sc = simulate_roster(ro, dists, n_sims, rng, seed_scenari=seed)
            pw = p_first(sc, opp_sc, rng, cal=cal)
            se = float(np.sqrt(max(pw * (1 - pw), 1e-9) / n_sims))
            costo = sum(ref[p] for r in ROLES for p in ro[r])
            print(f"  {nome:24s} costo mercato {costo:5.0f} | punti {sc.sum(1).mean():6.0f} | "
                  f"P(1o) {pw:.1%} +- {se:.1%}")
            out.setdefault(nome, {})[etichetta] = {"p_win": round(pw, 3), "se": round(se, 3),
                                                   "punti": round(float(sc.sum(1).mean()), 1)}
    a = out["rosa di oggi"]["verifica indipendente"]["p_win"]
    b = out["rosa di partenza (5/9)"]["verifica indipendente"]["p_win"]
    se = np.sqrt(out["rosa di oggi"]["verifica indipendente"]["se"] ** 2
                 + out["rosa di partenza (5/9)"]["verifica indipendente"]["se"] ** 2)
    print(f"\ndifferenza sulla verifica: {a - b:+.1%} (errore standard non appaiato {se:.1%})")
    d = ROOT / "data" / "livello0"
    d.mkdir(exist_ok=True)
    (d / "rerun_appaiato.json").write_text(json.dumps(out, indent=1, ensure_ascii=False),
                                           encoding="utf-8")


if __name__ == "__main__":
    main()
