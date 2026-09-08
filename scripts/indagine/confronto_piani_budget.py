"""Tre piani a confronto sullo stesso banco: libero, a budget quasi pieno, e
con due attaccanti di prima fascia imposti.

Le tre rose vengono costruite con gli stessi prezzi e giocate sulle stesse
stagioni simulate, contro gli stessi avversari e con lo stesso calendario:
la differenza fra loro non porta il rumore comune. Il numero riportato alla
fine viene da scenari MAI usati per costruirle.

I "due attaccanti di prima fascia" sono scelti con informazioni note prima
dell'asta (prezzo di mercato atteso), non con il rendimento poi realizzato.

Uso: python scripts/indagine/confronto_piani_budget.py [stagione=2026-27] [--sims 100]
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
from fantabot.optimizer import optimize_roster  # noqa: E402
from fantabot.rules import MIN_SPEND_FRAC  # noqa: E402

ORDINE = ["2021-22", "2023-24", "2024-25", "2025-26", "2026-27"]


def carica(season):
    with open(ROOT / "data" / "packs" / f"pack_{season}.pkl", "rb") as f:
        return pickle.load(f)


def piano_con_top_attaccanti(players, prezzi, valori, quotas, budget, ref,
                             forced, vup, lam, n_top=2):
    """Impone i due attaccanti piu' cari del mercato, poi completa la rosa."""
    att = sorted((p for p in players if players[p].role == "A"),
                 key=lambda p: -ref[p])[:n_top]
    speso = sum(prezzi[p] for p in att)
    resto = {pid: p for pid, p in players.items() if pid not in att}
    q2 = dict(quotas)
    q2["A"] = quotas["A"] - n_top
    # niente quota d'attacco: questo piano la decide da se' comprando i due
    # nomi piu' cari, e il tetto della quota li escluderebbe per costruzione
    sol = optimize_roster(resto, prezzi, valori, q2, budget - speso,
                          values_up=vup, lam=lam)
    if sol is None:
        return None, att
    sol["roster"]["A"] = list(att) + sol["roster"]["A"]
    sol["cost"] = sol["cost"] + speso
    return sol, att


def descrivi(nome, roster, ref, players, sc, prezzi):
    spesa = {r: sum(prezzi[p] for p in roster[r]) for r in ROLES}
    mkt = sum(ref[p] for r in ROLES for p in roster[r])
    att = sorted(roster["A"], key=lambda p: -prezzi[p])[:3]
    print(f"  {nome:22s} impegnato {sum(spesa.values()):5.0f} (al mercato {mkt:5.0f}) | "
          f"P {spesa['P']:4.0f} D {spesa['D']:4.0f} C {spesa['C']:4.0f} A {spesa['A']:4.0f} | "
          f"punti {sc.sum(1).mean():6.0f}")
    print(f"    attacco: {[f'{players[p].name} {ref[p]:.0f}cr' for p in att]}")


def main():
    args = sys.argv[1:]
    season = next((a for a in args if a[0].isdigit()), "2026-27")
    n_sims = int(args[args.index("--sims") + 1]) if "--sims" in args else 100
    pack = carica(season)
    preds = pack.b_predictions
    obj = getattr(pack, "b_objective", None) or {}
    lam = obj.get("lam", 0.0)
    forced = None
    if obj.get("attack_share"):
        lo, hi = obj["attack_share"]
        forced = {"A": (lo * pack.budget, hi * pack.budget)}
    ref = {pid: max(1.0, p.ref_price * pack.budget) for pid, p in pack.players.items()}
    prezzi = {pid: max(1.0, float(preds.get(pid, {}).get("q50", 1.0))) for pid in pack.players}
    val = {pid: float(preds.get(pid, {}).get("value", 0.0)) for pid in pack.players}
    vup = {pid: float(preds.get(pid, {}).get("value_up", val[pid])) for pid in pack.players}
    soglia = MIN_SPEND_FRAC * pack.budget

    piani = {}
    a = optimize_roster(pack.players, prezzi, val, pack.quotas, pack.budget,
                        forced_spend=forced, values_up=vup, lam=lam)
    if a:
        piani["libero (com'era)"] = a
    b = optimize_roster(pack.players, prezzi, val, pack.quotas, pack.budget,
                        forced_spend=forced, values_up=vup, lam=lam, min_spend=soglia)
    if b is None:
        print(f"BLOCCO: nessuna rosa rispetta la soglia di spesa {soglia:.0f} crediti")
        return
    piani[f"soglia {soglia:.0f}-{pack.budget}"] = b
    c, att = piano_con_top_attaccanti(pack.players, prezzi, val, pack.quotas,
                                      pack.budget, ref, forced, vup, lam)
    if c:
        piani["due top attaccanti"] = c
    else:
        print(f"BLOCCO: con {[pack.players[p].name for p in att]} imposti non "
              f"esiste rosa valida")

    # stesso banco per tutti: stessi scenari, stessi avversari, stesso calendario
    prev = [s for s in ORDINE if s < season][-2:]
    hv, hp = [], []
    for s in prev:
        try:
            pp = carica(s)
            hv.append(pp.votes_by_g)
            hp.append(pp.voti_by_g or [])
        except FileNotFoundError:
            pass
    dists = build_dists(pack.players, preds, hv, hp)
    rng = random.Random(1)
    opps = archetype_rosters(pack.players, ref, pack.quotas, pack.budget, rng, preds=preds)
    out = {}
    for etichetta, seed in [("banco di confronto", 4001), ("verifica indipendente", 4002)]:
        opp_sc = [simulate_roster(o, dists, n_sims, rng, seed_scenari=seed) for o in opps]
        cal = calendari(len(opps) + 1, n_sims, seed)
        print(f"\n=== {etichetta} ({n_sims} scenari, stessi avversari e calendario) ===")
        for nome, sol in piani.items():
            sc = simulate_roster(sol["roster"], dists, n_sims, rng, seed_scenari=seed)
            pw = p_first(sc, opp_sc, rng, cal=cal)
            se = float(np.sqrt(max(pw * (1 - pw), 1e-9) / n_sims))
            descrivi(nome, sol["roster"], ref, pack.players, sc, prezzi)
            print(f"    P(1o) {pw:.1%} +- {se:.1%}  (IC95 {max(0, pw-1.96*se):.1%}"
                  f"..{min(1, pw+1.96*se):.1%})")
            out.setdefault(nome, {})[etichetta] = {
                "p_win": round(pw, 3), "se": round(se, 3),
                "costo_mercato": round(sum(ref[p] for r in ROLES for p in sol["roster"][r]), 1),
                "costo_stime": round(sum(prezzi[p] for r in ROLES for p in sol["roster"][r]), 1),
                "punti_medi": round(float(sc.sum(1).mean()), 1)}
    d = ROOT / "data" / "livello0"
    d.mkdir(exist_ok=True)
    (d / f"confronto_piani_{season}.json").write_text(
        json.dumps(out, indent=1, ensure_ascii=False), encoding="utf-8")


if __name__ == "__main__":
    main()
