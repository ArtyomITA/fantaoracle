"""Sceglie l'obiettivo di B con il Monte Carlo: P(vincere), non punti attesi.

Per la stagione data: distribuzioni per giocatore dalle 2 stagioni
precedenti (voti reali), prezzi = q50 (gia' misti col mercato per la
stagione corrente), avversari = archetipi a prezzo di mercato. Prova
lam x quota attacco, salva in pack.b_objective la combinazione migliore e
stampa la tabella. Uso: python scripts/f12_choose_objective.py [stagione] [--sims 150]
"""
from __future__ import annotations

import pickle
import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
PACKS = ROOT / "data" / "packs"

from fantabot.montecarlo import build_dists, choose_objective  # noqa: E402

ORDER = ["2024-25", "2025-26", "2026-27"]


def load(season):
    with open(PACKS / f"pack_{season}.pkl", "rb") as f:
        return pickle.load(f)


def main():
    args = sys.argv[1:]
    season = next((a for a in args if a[0].isdigit()), "2026-27")
    n_sims = int(args[args.index("--sims") + 1]) if "--sims" in args else 150
    pack = load(season)
    prev = [s for s in ORDER if s < season][-2:]
    hist_votes, hist_voti = [], []
    for s in prev:
        try:
            pp = load(s)
            hist_votes.append(pp.votes_by_g)
            hist_voti.append(pp.voti_by_g or [])
        except FileNotFoundError:
            pass
    if not hist_votes:
        raise SystemExit("servono pack delle stagioni precedenti per le distribuzioni")
    dists = build_dists(pack.players, pack.b_predictions, hist_votes, hist_voti)
    prices = {pid: max(1.0, float(pack.b_predictions.get(pid, {}).get("q50", 1.0)))
              for pid in pack.players}
    ref = {pid: max(1.0, p.ref_price * pack.budget) for pid, p in pack.players.items()}
    res = choose_objective(pack.players, pack.b_predictions, prices, ref, dists,
                           pack.quotas, pack.budget, seed=1, n_sims=n_sims)
    print(f"avversari archetipo P(1o): {res['opponents_p_win']}")
    print(f"{'lam':>4} {'attacco':>11} {'modulo':>6} {'costo':>6} {'punti':>6} {'sd':>5} {'P(win)':>7}")
    for r in res["table"]:
        print(f"{r['lam']:4.1f} {str(r['attack_share']):>11} {r['module']:>6} {r['cost']:6.0f} "
              f"{r['mean_pts']:6.0f} {r['sd_g']:5.2f} {r['p_win']:7.1%}")
    best = res["best"]
    names = {r: [pack.players[p].name for p in best["roster"][r]] for r in "PDCA"}
    print(f"\nMIGLIORE: lam {best['lam']}, attacco {best['attack_share']}, modulo {best['module']}, "
          f"P(win) {best['p_win']:.1%}")
    for r in "PDCA":
        print(f"  {r}: {names[r]}")
    pack.b_objective = {"lam": best["lam"], "attack_share": best["attack_share"],
                        "p_win": best["p_win"], "table": [
                            {k: v for k, v in row.items() if k != "roster"} for row in res["table"]]}
    with open(PACKS / f"pack_{season}.pkl", "wb") as f:
        pickle.dump(pack, f)
    print("obiettivo salvato nel pack")


if __name__ == "__main__":
    main()
