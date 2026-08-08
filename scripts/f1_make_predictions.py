"""Fase 1 finale — predizioni B per le stagioni del torneo.

Per ogni stagione target: TabPFN-2 conformalizzato allenato SOLO sulle
stagioni precedenti -> q10/q50/q90 in crediti (budget 500) per TUTTI i
giocatori del listone + valore (Marcel exp_points).
Output: data/processed/b_predictions_{stagione}.json
"""
from __future__ import annotations

import json
import sys
import warnings
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))
PROC = ROOT / "data" / "processed"

warnings.filterwarnings("ignore")

from f1_train_price import (fit_predict_catboost, fit_predict_tabpfn,  # noqa: E402
                            load_season, with_conformal)
from fantabot.modeling import project_players  # noqa: E402

TARGETS = {
    "2024-25": ["2021-22", "2023-24"],
    "2025-26": ["2021-22", "2023-24", "2024-25"],
}
BUDGET = 500


def catboost_values(season: str, train_ss: list[str], te: pd.DataFrame) -> pd.Series:
    """Modello valore vincente (sfida f1_value_challenge: rho 0.82 vs 0.41
    del Marcel): CatBoost su feature pre-asta -> punti totali stagione.
    Train solo su stagioni PRECEDENTI la stagione target."""
    from catboost import CatBoostRegressor
    from f1_train_price import load_season, xmat
    frames = []
    for s in train_ss:
        df = load_season(s)
        v = pd.read_parquet(PROC / f"votes_{s}.parquet")
        if "sv" in v.columns:
            v = v[v["sv"].fillna(0) == 0]
        pts = v.groupby("master_id")["fantavoto"].sum()
        df["points"] = df["master_id"].map(pts).fillna(0.0)
        frames.append(df)
    tr = pd.concat(frames, ignore_index=True)
    m = CatBoostRegressor(iterations=700, learning_rate=0.04, depth=5,
                          l2_leaf_reg=6, random_seed=7, verbose=False)
    m.fit(xmat(tr), tr["points"])
    pred = np.clip(np.asarray(m.predict(xmat(te)), dtype=float), 0.0, None)
    return pd.Series(pred, index=te.index)


def marcel_values(season: str, te: pd.DataFrame) -> pd.Series:
    order = ["2021-22", "2022-23", "2023-24", "2024-25", "2025-26"]
    prev = [s for s in order if s < season][-3:]
    frames = []
    for s in prev:
        p = PROC / f"votes_{s}.parquet"
        if p.exists():
            v = pd.read_parquet(p)
            if "sv" in v.columns:
                v = v[v["sv"].fillna(0) == 0]
            v = v.copy()
            v["stagione"] = s
            frames.append(v)
    votes = pd.concat(frames, ignore_index=True)
    proj = project_players(votes, te[["master_id", "ruolo"]], list(reversed(prev)))
    out = te[["master_id"]].merge(proj, on="master_id", how="left")
    # nuovi senza storico: valore prudente dal rank di quotazione
    fallback = 5.9 * 20 + (te["qt_i"].fillna(1).astype(float) - 1) * 2.0
    return out["exp_points"].fillna(pd.Series(fallback.values)).astype(float)


def main():
    for season, train_ss in TARGETS.items():
        seasons = {s: load_season(s) for s in train_ss + [season]}
        tr = pd.concat([seasons[s] for s in train_ss], ignore_index=True)
        tr = tr[~tr["y"].isna()].reset_index(drop=True)
        te = seasons[season].reset_index(drop=True)
        # ensemble TabPFN+CatBoost (fix indagine: piu' robusto tra annate del
        # TabPFN solo — il 2025-26 ha punito la calibrazione singola)
        p_tab = with_conformal(fit_predict_tabpfn, tr, te)
        p_cat = with_conformal(fit_predict_catboost, tr, te)
        preds = {k: (np.asarray(p_tab[k], dtype=float)
                     + np.asarray(p_cat[k], dtype=float)) / 2
                 for k in ("q10", "q50", "q90")}
        values = catboost_values(season, train_ss, te)
        out = {}
        for i, row in te.iterrows():
            out[str(row["master_id"])] = {
                "q10": round(float(preds["q10"][i]) * BUDGET, 2),
                "q50": round(float(preds["q50"][i]) * BUDGET, 2),
                "q90": round(float(preds["q90"][i]) * BUDGET, 2),
                "value": round(float(values.iloc[i]), 1),
            }
        path = PROC / f"b_predictions_{season}.json"
        path.write_text(json.dumps(out), encoding="utf-8")
        top = te.assign(q50=preds["q50"] * BUDGET).nlargest(8, "q50")
        print(f"{season}: {len(out)} predizioni -> {path.name}")
        for _, r in top.iterrows():
            print(f"   {r['nome']:22s} {r['ruolo']}  q50={r['q50']:.0f}")


if __name__ == "__main__":
    main()
