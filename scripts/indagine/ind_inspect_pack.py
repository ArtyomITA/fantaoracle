# -*- coding: utf-8 -*-
import pickle
import sys

sys.path.insert(0, r"src")

for season in ["2024-25", "2025-26"]:
    p = rf"data\tournament_mod\{season}\main_1B_2A_7C\_pack.pkl"
    with open(p, "rb") as f:
        pack = pickle.load(f)
    print("=", season, "players:", len(pack.players), "giornate:", len(pack.votes_by_g),
          "b_pred:", len(pack.b_predictions or {}), "mod_difesa:", pack.use_mod_difesa)
    pid, pl = next(iter(pack.players.items()))
    print("  sample player:", pid, pl)
    k, v = next(iter(pack.b_predictions.items()))
    print("  sample b_pred:", k, v)
    tot = {}
    for g in pack.votes_by_g:
        for pid2, fv in g.items():
            tot[pid2] = tot.get(pid2, 0.0) + fv
    import statistics
    print("  players con voti:", len(tot), "max season pts:",
          sorted(tot.values())[-3:], "median:", statistics.median(tot.values()))
