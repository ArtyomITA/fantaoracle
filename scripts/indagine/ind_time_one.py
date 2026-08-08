# -*- coding: utf-8 -*-
import pickle
import sys
import time

sys.path.insert(0, r"src")
sys.path.insert(0, r"scripts\indagine")
from ind_rerun_auctions import run_auction, TABLE, verify  # noqa: E402
from pathlib import Path

comp = Path(r"data\tournament_mod\2024-25\main_1B_2A_7C")
with open(comp / "_pack.pkl", "rb") as f:
    pack = pickle.load(f)
t0 = time.time()
rows = run_auction(pack, TABLE, 10_000)
t1 = time.time()
print(f"1 asta: {t1-t0:.1f}s, {len(rows)} acquisti")
verify("2024-25", comp, rows, 0)
