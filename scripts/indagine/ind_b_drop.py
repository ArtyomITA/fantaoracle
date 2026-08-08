# -*- coding: utf-8 -*-
"""Perche' i punti RAW di B crollano nel 2025-26? Decomposizione per ruolo e fascia."""
import sys

sys.path.insert(0, r"scripts\indagine")
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from ind_analisi import IND, SEASONS, load_pack, load_replicas, player_frame  # noqa: E402

pd.set_option("display.width", 220)

for s in SEASONS:
    pf = player_frame(load_pack(s))
    ro = pd.read_csv(IND / f"rosters_{s}.csv", dtype={"player_id": str})
    b = ro[ro["bot"] == "B"].drop(columns=["role"]).join(pf, on="player_id")
    print(f"\n===== {s} : B, medie per replica =====")
    per_role = b.groupby(["seed", "role"]).agg(
        pts=("real_pts", "sum"), spent=("price", "sum"), n=("price", "size"),
        pres=("presenze", "mean")).groupby("role").mean().round(1)
    print(per_role.to_string())
    tot = b.groupby("seed").agg(pts=("real_pts", "sum"), spent=("price", "sum"),
                                pres=("presenze", "mean"))
    print(f"TOT: pts {tot['pts'].mean():.0f}, spesi {tot['spent'].mean():.0f}, "
          f"presenze medie/giocatore {tot['pres'].mean():.1f}")
    # fascia di prezzo pagato
    b["fascia"] = pd.cut(b["price"], [0, 1, 5, 20, 50, 100, 500],
                         labels=["1", "2-5", "6-20", "21-50", "51-100", "100+"])
    fas = b.groupby(["seed", "fascia"], observed=False).agg(
        pts=("real_pts", "sum"), n=("price", "size"), spent=("price", "sum"))
    fas = fas.groupby("fascia", observed=False).mean().round(1)
    print("per fascia di prezzo pagato:")
    print(fas.to_string())
    # i 25 slot: quanti danno <50 pts reali (buchi)?
    b["flop"] = b["real_pts"] < 50
    print(f"acquisti con <50 pts reali: {b.groupby('seed')['flop'].sum().mean():.1f} su 25 "
          f"a replica; con 0 presenze: "
          f"{b.groupby('seed').apply(lambda x: (x['presenze']==0).sum(), include_groups=False).mean():.1f}")
    # confronto con il miglior rivale della stagione (per raw pts): chi e'?
    allr = ro.join(pf[["real_pts"]], on="player_id")
    raw = allr.groupby(["seed", "bot"])["real_pts"].sum().unstack()
    best = raw.drop(columns="B").mean().idxmax()
    rb = ro[ro["bot"] == best].drop(columns=["role"]).join(pf, on="player_id")
    rb["fascia"] = pd.cut(rb["price"], [0, 1, 5, 20, 50, 100, 500],
                          labels=["1", "2-5", "6-20", "21-50", "51-100", "100+"])
    fas2 = rb.groupby(["seed", "fascia"], observed=False).agg(
        pts=("real_pts", "sum"), n=("price", "size"), spent=("price", "sum"))
    fas2 = fas2.groupby("fascia", observed=False).mean().round(1)
    print(f"confronto: miglior rivale raw = {best}; sue fasce:")
    print(fas2.to_string())
