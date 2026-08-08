# -*- coding: utf-8 -*-
"""Q4 parte 1: rho modello vs mercato + punti->win dalle replicas.jsonl (senza rose)."""
import sys

sys.path.insert(0, r"scripts\indagine")
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from scipy.stats import pearsonr, spearmanr  # noqa: E402

from ind_analisi import SEASONS, load_pack, load_replicas, player_frame  # noqa: E402

for s in SEASONS:
    pf = player_frame(load_pack(s))
    m = pf.dropna(subset=["value"])
    m = m[m["ref_credits"] >= 1]
    print(f"\n[{s}] n={len(m)} (pool ref>=1cr)")
    for lab, col in [("modello (value)", "value"), ("mercato (ref_price)", "ref_credits"),
                     ("exp_points", "exp_points")]:
        rs = spearmanr(m[col], m["real_pts"])[0]
        rp = pearsonr(m[col], m["real_pts"])[0]
        print(f"  {lab:22s} spearman {rs:.3f}  pearson {rp:.3f}")
    m5 = m[m["ref_credits"] >= 5]
    print(f"  -- solo ref>=5cr (n={len(m5)}): modello sp "
          f"{spearmanr(m5['value'], m5['real_pts'])[0]:.3f}, mercato sp "
          f"{spearmanr(m5['ref_credits'], m5['real_pts'])[0]:.3f}")

    r = load_replicas(s)
    rho_p = pearsonr(r["total_points"], r["h2h_win_rate"])[0]
    piv = r.pivot(index="seed", columns="bot", values="total_points")
    margin = piv["B"] - piv.drop(columns="B").max(axis=1)
    wr = r[r["bot"] == "B"].set_index("seed")["h2h_win_rate"]
    wmax = r.loc[r.groupby("seed")["h2h_win_rate"].idxmax()].set_index("seed")["bot"]
    pmax = piv.idxmax(axis=1)
    print(f"  corr(points, win) pooled {rho_p:.3f}; max-points vince h2h "
          f"{(wmax == pmax).mean()*100:.0f}%; margine B medio {margin.mean():+.0f} "
          f"(med {margin.median():+.0f}), margine>0 nel {(margin > 0).mean()*100:.0f}%, "
          f"wr medio B {wr.mean():.3f}")
