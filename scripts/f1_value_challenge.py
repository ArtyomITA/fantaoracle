"""Sfida modello VALORE: Marcel vs CatBoost (target = punti totali stagione).

Train: 2023-24 (feature pre-asta -> punti reali 2023-24)
Test:  2024-25 e (train 23+24) 2025-26.
"""
from __future__ import annotations

import sys
import warnings
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import spearmanr

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))
PROC = ROOT / "data" / "processed"
warnings.filterwarnings("ignore")

from f1_train_price import FEATURES_NUM, load_season, xmat  # noqa: E402
from f1_make_predictions import marcel_values  # noqa: E402


def season_points(season: str) -> pd.Series:
    v = pd.read_parquet(PROC / f"votes_{season}.parquet")
    if "sv" in v.columns:
        v = v[v["sv"].fillna(0) == 0]
    return v.groupby("master_id")["fantavoto"].sum()


def with_points(season: str) -> pd.DataFrame:
    df = load_season(season)
    pts = season_points(season)
    df["points"] = df["master_id"].map(pts).fillna(0.0)
    return df


def main():
    from catboost import CatBoostRegressor
    runs = [("V1", ["2023-24"], "2024-25"),
            ("V2", ["2023-24", "2024-25"], "2025-26")]
    for run, train_ss, test_s in runs:
        tr = pd.concat([with_points(s) for s in train_ss], ignore_index=True)
        te = with_points(test_s)
        m = CatBoostRegressor(iterations=700, learning_rate=0.04, depth=5,
                              l2_leaf_reg=6, random_seed=7, verbose=False)
        m.fit(xmat(tr), tr["points"])
        cb = np.asarray(m.predict(xmat(te)), dtype=float)
        marcel = marcel_values(test_s, te).to_numpy()
        y = te["points"].to_numpy()
        mask = y > 0
        print(f"{run} test {test_s} ({mask.sum()} con punti): "
              f"CatBoost rho={spearmanr(cb[mask], y[mask]).statistic:.3f}  "
              f"Marcel rho={spearmanr(marcel[mask], y[mask]).statistic:.3f}  "
              f"mix50 rho={spearmanr((cb[mask]*0.5 + marcel[mask]*0.5), y[mask]).statistic:.3f}")


if __name__ == "__main__":
    main()
