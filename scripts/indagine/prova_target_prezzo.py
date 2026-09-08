"""Prova appaiata: il target wayback nel training danneggia il modello prezzo?

Gli snapshot "wayback" di fantacalcio-online sono stime di listino catturate a
campionato in corso (gennaio-giugno), non prezzi di aste estive. Qui si misura
l'effetto di addestrare su quel target invece che sulle aste reali estive, a
parita' di tutto il resto: stesso test set (aste estive autentiche), stesse
feature, stesso modello, stessi seed.

  A) train con target ASTE ESTIVE della stagione di train
  B) train con target WAYBACK della stessa stagione (stesse righe)

Uso: python scripts/indagine/prova_target_prezzo.py
Output: data/livello0/prova_target_prezzo.json
"""
from __future__ import annotations

import json
import sys
import warnings
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))
warnings.filterwarnings("ignore")

from f1_train_price import load_season, xmat  # noqa: E402

BUDGET = 500


def target_estiva(df: pd.DataFrame) -> pd.Series:
    y = df["target_mean_pct_all_estiva"].astype(float)
    return y.where(df["target_n_obs_all_estiva"].fillna(0).astype(float) >= 2)


def target_wayback(df: pd.DataFrame) -> pd.Series:
    return df["target_wayback_p500_10sq"].astype(float) / BUDGET


def fit_catboost(tr: pd.DataFrame, y: np.ndarray, te: pd.DataFrame) -> np.ndarray:
    from catboost import CatBoostRegressor
    m = CatBoostRegressor(iterations=600, learning_rate=0.05, depth=5,
                          l2_leaf_reg=6, random_seed=7, verbose=False)
    m.fit(xmat(tr), y)
    return np.asarray(m.predict(xmat(te)), dtype=float)


def metriche(pred: np.ndarray, vero: np.ndarray) -> dict:
    p, v = pred * BUDGET, vero * BUDGET
    ok = ~np.isnan(v)
    p, v = p[ok], v[ok]
    top = np.argsort(-v)[:50]
    return {
        "n": int(ok.sum()),
        "mae": round(float(np.abs(p - v).mean()), 2),
        "bias": round(float((p - v).mean()), 2),
        "rho": round(float(pd.Series(p).corr(pd.Series(v), method="spearman")), 4),
        "mae_top50": round(float(np.abs(p[top] - v[top]).mean()), 2),
        "bias_top50": round(float((p[top] - v[top]).mean()), 2),
        "mae_sotto15": round(float(np.abs(p[v < 15] - v[v < 15]).mean()), 2),
        "bias_sotto15": round(float((p[v < 15] - v[v < 15]).mean()), 2),
    }


def main():
    prove = [
        ("train 2021-22 -> test 2023-24", ["2021-22"], "2023-24"),
        ("train 2021-22+2023-24 -> test 2024-25", ["2021-22", "2023-24"], "2024-25"),
    ]
    seasons = {s: load_season(s) for s in ["2021-22", "2023-24", "2024-25"]}
    out = {}
    for nome, train_ss, test_s in prove:
        te = seasons[test_s].reset_index(drop=True)
        y_te = target_estiva(te).to_numpy(dtype=float)   # verita': aste estive vere
        res = {}
        for etichetta, fn in [("estiva", target_estiva), ("wayback", target_wayback)]:
            tr = pd.concat([seasons[s] for s in train_ss], ignore_index=True)
            y_tr = fn(tr).to_numpy(dtype=float)
            ok = ~np.isnan(y_tr)
            pred = fit_catboost(tr[ok].reset_index(drop=True), y_tr[ok], te)
            res[etichetta] = metriche(pred, y_te) | {"n_train": int(ok.sum())}
        print(f"\n=== {nome} (test: aste estive autentiche) ===")
        for k in ("n_train", "n", "mae", "bias", "rho", "mae_top50", "bias_top50",
                  "mae_sotto15", "bias_sotto15"):
            print(f"  {k:14s} train estiva {res['estiva'][k]:>9} | "
                  f"train wayback {res['wayback'][k]:>9}")
        out[nome] = res
    (ROOT / "data" / "livello0").mkdir(exist_ok=True)
    (ROOT / "data" / "livello0" / "prova_target_prezzo.json").write_text(
        json.dumps(out, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main()
