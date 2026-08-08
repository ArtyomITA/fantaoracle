"""Fase 1 — gara modelli PREZZO (target: % budget in asta estiva).

Protocollo leave-future-out:
  R1: train 2021-22            -> test 2023-24
  R2: train 2021-22 + 2023-24  -> test 2024-25
  R3: train 21+23+24           -> test 2025-26 (target = wayback p500_10sq/500)

Modelli: Ridge, CatBoost MultiQuantile, TabPFN (quantili nativi), VORP (Marcel).
Output: reports/f1_price_eval.md + data/processed/pred_{modello}_{stagione}.csv
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
PROC = ROOT / "data" / "processed"
REPORTS = ROOT / "reports"
REPORTS.mkdir(exist_ok=True)

from fantabot.modeling import project_players, vorp_prices  # noqa: E402

warnings.filterwarnings("ignore")

FEATURES_NUM = [
    "qt_i", "fvm", "quot_fs_sett", "eta", "tm_value_log",
    "nuovo_in_serie_a", "squadra_neopromossa",
    "prev1_fantamedia", "prev1_media_voto", "prev1_presenze", "prev1_gol",
    "prev1_assist", "prev1_rig_segnati", "prev1_ammonizioni",
    "prev2_fantamedia", "prev2_presenze", "prev2_gol", "prev2_assist",
    "prev3_fantamedia", "prev3_presenze", "prev3_gol",
    "us_prev_xg", "us_prev_xa", "us_prev_npxg", "us_prev_shots",
    "us_prev_minutes", "us_prev_xg90", "team_prev_xg",
    "ruolo_ord",
]
ROLE_ORD = {"P": 0, "D": 1, "C": 2, "A": 3}
QUANTILES = [0.1, 0.5, 0.9]
RUNS = [
    ("R1", ["2021-22"], "2023-24"),
    ("R2", ["2021-22", "2023-24"], "2024-25"),
    ("R3", ["2021-22", "2023-24", "2024-25"], "2025-26"),
]


def load_season(season: str) -> pd.DataFrame:
    df = pd.read_parquet(PROC / f"players_{season}.parquet")
    df["stagione"] = season
    df["tm_value_log"] = np.log1p(df["tm_value_eur"].astype(float))
    df["ruolo_ord"] = df["ruolo"].map(ROLE_ORD)
    for c in ("nuovo_in_serie_a", "squadra_neopromossa"):
        df[c] = df[c].astype(float)
    # target: estive tutte le config (campione grande); 2025-26 solo wayback
    if season == "2025-26":
        df["y"] = df["target_wayback_p500_10sq"].astype(float) / 500.0
        df["y_w"] = 1.0
    else:
        df["y"] = df["target_mean_pct_all_estiva"].astype(float)
        df["y_w"] = np.sqrt(df["target_n_obs_all_estiva"].fillna(0).astype(float))
        df.loc[df["target_n_obs_all_estiva"].fillna(0) < 2, "y"] = np.nan
    return df


def xmat(df: pd.DataFrame) -> pd.DataFrame:
    return df[FEATURES_NUM].astype(float)


# ---------------- modelli ----------------
def fit_predict_ridge(tr, te):
    from sklearn.compose import TransformedTargetRegressor
    from sklearn.impute import SimpleImputer
    from sklearn.linear_model import Ridge
    from sklearn.pipeline import make_pipeline
    from sklearn.preprocessing import StandardScaler
    pipe = make_pipeline(SimpleImputer(strategy="median"), StandardScaler(),
                         Ridge(alpha=3.0))
    pipe.fit(xmat(tr), tr["y"], ridge__sample_weight=tr["y_w"])
    q50 = np.clip(pipe.predict(xmat(te)), 0.002, 0.60)
    resid = tr["y"] - np.clip(pipe.predict(xmat(tr)), 0.002, 0.60)
    lo, hi = np.quantile(resid, 0.1), np.quantile(resid, 0.9)
    return {"q10": np.clip(q50 + lo, 0.002, None), "q50": q50, "q90": q50 + hi}


def fit_predict_catboost(tr, te):
    from catboost import CatBoostRegressor
    m = CatBoostRegressor(
        loss_function="MultiQuantile:alpha=0.1,0.5,0.9",
        iterations=800, learning_rate=0.03, depth=5,
        l2_leaf_reg=6, random_seed=7, verbose=False)
    m.fit(xmat(tr), tr["y"], sample_weight=tr["y_w"])
    p = m.predict(xmat(te))
    p = np.clip(p, 0.002, 0.60)
    p.sort(axis=1)   # quantile crossing guard
    return {"q10": p[:, 0], "q50": p[:, 1], "q90": p[:, 2]}


def fit_predict_tabpfn(tr, te):
    # TabPFN-2 (Apache 2.0): l'unico checkpoint scaricabile senza account
    from tabpfn import TabPFNRegressor
    m = TabPFNRegressor(device="cpu", random_state=7,
                        model_path="tabpfn-v2-regressor.ckpt",
                        ignore_pretraining_limits=True)
    Xtr = xmat(tr).to_numpy(dtype=np.float32)
    Xte = xmat(te).to_numpy(dtype=np.float32)
    m.fit(Xtr, tr["y"].to_numpy(dtype=np.float32))
    try:
        qs = m.predict(Xte, output_type="quantiles", quantiles=QUANTILES)
        q10, q50, q90 = [np.asarray(q, dtype=float).ravel() for q in qs]
    except (TypeError, ValueError):
        q50 = np.asarray(m.predict(Xte), dtype=float).ravel()
        q10, q90 = q50 * 0.7, q50 * 1.35
    q10, q50, q90 = (np.clip(q, 0.002, 0.60) for q in (q10, q50, q90))
    stack = np.sort(np.vstack([q10, q50, q90]), axis=0)
    return {"q10": stack[0], "q50": stack[1], "q90": stack[2]}


def with_conformal(fit_fn, tr, te, rng_seed=13, target_cov=0.80):
    """Split-conformal (CQR): 80% fit, 20% calibrazione -> allarga [q10,q90]
    del delta necessario a coprire target_cov sul calibration set."""
    idx = np.arange(len(tr))
    rs = np.random.RandomState(rng_seed)
    rs.shuffle(idx)
    n_cal = max(30, int(0.2 * len(tr)))
    cal_idx, fit_idx = idx[:n_cal], idx[n_cal:]
    tr_fit = tr.iloc[fit_idx].reset_index(drop=True)
    tr_cal = tr.iloc[cal_idx].reset_index(drop=True)
    p_cal = fit_fn(tr_fit, tr_cal)
    y_cal = tr_cal["y"].to_numpy(dtype=float)
    scores = np.maximum(p_cal["q10"] - y_cal, y_cal - p_cal["q90"])
    delta = float(np.quantile(scores, target_cov))
    p_te = fit_fn(tr, te)   # fit finale su tutto il train
    p_te["q10"] = np.clip(p_te["q10"] - max(0.0, delta), 0.001, None)
    p_te["q90"] = p_te["q90"] + max(0.0, delta)
    return p_te


def fit_predict_vorp(tr, te, season: str):
    """Baseline formula: Marcel -> VORP -> pct. Ignora il train set."""
    votes_prev, seasons_desc = [], []
    all_votes = {s: pd.read_parquet(PROC / f"votes_{s}.parquet")
                 for s in ["2021-22", "2022-23", "2023-24", "2024-25"]}
    order = ["2021-22", "2022-23", "2023-24", "2024-25", "2025-26"]
    prev = [s for s in order if s < season][-3:]
    for s in reversed(prev):
        if s in all_votes:
            v = all_votes[s].copy()
            v["stagione"] = s
            votes_prev.append(v)
            seasons_desc.append(s)
    if not votes_prev:
        return None
    votes = pd.concat(votes_prev, ignore_index=True)
    if "sv" in votes.columns:
        votes = votes[votes["sv"].fillna(0) == 0]
    reg = te[["master_id", "ruolo"]].copy()
    proj = project_players(votes, reg, seasons_desc)
    base = te[["master_id", "ruolo"]].merge(proj, on="master_id", how="left")
    base["exp_points"] = base["exp_points"].fillna(0.0)
    pr = vorp_prices(base, {"P": 3, "D": 8, "C": 8, "A": 6}, 10, 500)
    out = te[["master_id"]].merge(pr, on="master_id", how="left")
    q50 = (out["prezzo_equo"].fillna(1.0) / 500.0).to_numpy()
    return {"q10": q50 * 0.7, "q50": q50, "q90": q50 * 1.35}


# ---------------- metriche ----------------
def evaluate(y, w, preds) -> dict:
    from scipy.stats import spearmanr
    mask = ~np.isnan(y)
    y, w = y[mask], w[mask]
    q10, q50, q90 = (preds[k][mask] for k in ("q10", "q50", "q90"))
    top = np.argsort(-y)[:50]
    pinball = 0.0
    for q, a in ((q10, 0.1), (q90, 0.9)):
        d = y - q
        pinball += np.mean(np.maximum(a * d, (a - 1) * d))
    return {
        "n": int(mask.sum()),
        "spearman": round(float(spearmanr(y, q50).statistic), 4),
        "mae_pct": round(float(np.mean(np.abs(y - q50))), 5),
        "mae_top50_crediti": round(float(np.mean(np.abs(y[top] - q50[top])) * 500), 1),
        "coverage_q10_q90": round(float(np.mean((y >= q10) & (y <= q90))), 3),
        "pinball": round(float(pinball), 5),
    }


def main():
    seasons = {s: load_season(s) for s in
               ["2021-22", "2023-24", "2024-25", "2025-26"]}
    results = {}
    for run, train_ss, test_s in RUNS:
        tr = pd.concat([seasons[s] for s in train_ss], ignore_index=True)
        tr = tr[~tr["y"].isna()].reset_index(drop=True)
        te = seasons[test_s].reset_index(drop=True)
        y = te["y"].to_numpy(dtype=float)
        w = te["y_w"].to_numpy(dtype=float)
        print(f"\n=== {run}: train {train_ss} ({len(tr)} righe) -> test {test_s} "
              f"({int((~np.isnan(y)).sum())} con target) ===")
        season_preds = {}
        for name, fn in [("ridge", lambda a, b: with_conformal(fit_predict_ridge, a, b)),
                         ("catboost", lambda a, b: with_conformal(fit_predict_catboost, a, b)),
                         ("tabpfn", lambda a, b: with_conformal(fit_predict_tabpfn, a, b)),
                         ("vorp", lambda a, b: fit_predict_vorp(a, b, test_s))]:
            try:
                preds = fn(tr, te)
            except Exception as e:
                print(f"  {name:9s} ERRORE: {e}")
                continue
            if preds is None:
                print(f"  {name:9s} n/d")
                continue
            season_preds[name] = preds
        if "tabpfn" in season_preds and "catboost" in season_preds:
            season_preds["ens_tab_cat"] = {
                k: (np.asarray(season_preds["tabpfn"][k], dtype=float)
                    + np.asarray(season_preds["catboost"][k], dtype=float)) / 2
                for k in ("q10", "q50", "q90")}
        for name, preds in season_preds.items():
            m = evaluate(y, w, {k: np.asarray(v, dtype=float)
                                for k, v in preds.items()})
            results[f"{run}/{name}"] = m
            print(f"  {name:11s} rho={m['spearman']:.3f}  MAE={m['mae_pct']*500:.1f}cr  "
                  f"MAEtop50={m['mae_top50_crediti']:.1f}cr  "
                  f"cov={m['coverage_q10_q90']:.0%}  pin={m['pinball']:.5f}")
            out = te[["master_id", "nome", "ruolo"]].copy()
            for k in ("q10", "q50", "q90"):
                out[k] = np.asarray(preds[k], dtype=float)
            out.to_csv(PROC / f"pred_{name}_{test_s}.csv", index=False)
    (REPORTS / "f1_price_eval.json").write_text(
        json.dumps(results, indent=2), encoding="utf-8")
    print(f"\nSalvato reports/f1_price_eval.json + pred_*.csv")


if __name__ == "__main__":
    main()
