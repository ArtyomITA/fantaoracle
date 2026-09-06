"""Harness di backtest del modello VALORE (leave-future-out).

Usa le funzioni REALI di scripts/f1_make_predictions.py (catboost_values,
_season_points_frame, TARGETS): ogni modifica al modello viene misurata qui
senza duplicare codice.

Protocollo: 2024-25 con train 2021-22+2023-24; 2025-26 con train
2021-22+2023-24+2024-25. Target = punti stagione (fantavoto + 1 porta
inviolata, sv esclusi) e presenze; i punti reali sono quelli di TUTTA la
stagione anche quando il modello vede le prime K giornate (value = punti
gia' fatti + resto predetto), cosi' le varianti sono confrontabili.

Uso: python scripts/indagine/backtest_valore.py --tag baseline [--k 2]
Output: stampa + data/indagine/backtest_valore_{tag}.json
        + data/indagine/pred_valore_{tag}_{stagione}.csv (predizioni per riga)
"""
from __future__ import annotations

import argparse
import inspect
import json
import sys
import time
import warnings
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))
OUT = ROOT / "data" / "indagine"
OUT.mkdir(parents=True, exist_ok=True)
warnings.filterwarnings("ignore")

import f1_make_predictions as f1  # noqa: E402
from f1_train_price import FEATURES_NUM, load_season  # noqa: E402

TEST_SEASONS = ["2024-25", "2025-26"]
LIVE_SEASON = "2026-27"
ROLES = ["P", "D", "C", "A"]
ROSTER_MIN = 50.0     # fascia rosterabile: value PREDETTO >= 50
FASCE = [60.0, 150.0]  # fasce di valore predetto per le metriche dei quantili
FASCE_NOMI = ["<60", "60-150", ">150"]


def _rho(a, b) -> float:
    from scipy.stats import spearmanr
    if len(a) < 3:
        return float("nan")
    return float(spearmanr(a, b).statistic)


def _kw_k(fn, k: int) -> dict:
    """Passa k solo se la funzione lo accetta (baseline pre-patch non lo ha)."""
    return {"k": k} if "k" in inspect.signature(fn).parameters else {}


def truth_frame(season: str, k: int) -> pd.DataFrame:
    kw = _kw_k(f1._season_points_frame, k)
    df = f1._season_points_frame(season, **kw)
    df["master_id"] = df["master_id"].astype(str)
    return df


def metrics(df: pd.DataFrame, k: int) -> dict:
    """df: value, value_up, pres, points, pres_true, ruolo, nuovo, (q10,q90),
    (pts_gk, pres_gk)."""
    y, v = df["points"].to_numpy(float), df["value"].to_numpy(float)
    err = v - y
    m = {
        "n": int(len(df)),
        "mae": float(np.mean(np.abs(err))),
        "bias": float(np.mean(err)),
        "rho": _rho(y, v),
        "mae_pres": float(np.mean(np.abs(df["pres"] - df["pres_true"]))),
        "bias_pres": float(np.mean(df["pres"] - df["pres_true"])),
    }
    ro = df[df["value"] >= ROSTER_MIN]
    m["roster_n"] = int(len(ro))
    m["roster_mae"] = float(np.mean(np.abs(ro["value"] - ro["points"])))
    m["roster_bias"] = float(np.mean(ro["value"] - ro["points"]))
    m["roster_rho"] = _rho(ro["points"], ro["value"])
    for r in ROLES:
        s = df[df["ruolo"] == r]
        m[f"mae_{r}"] = float(np.mean(np.abs(s["value"] - s["points"])))
        m[f"bias_{r}"] = float(np.mean(s["value"] - s["points"]))
        m[f"rho_{r}"] = _rho(s["points"], s["value"])
    nu = df[df["nuovo"] == 1]
    m["nuovi_n"] = int(len(nu))
    m["nuovi_mae"] = float(np.mean(np.abs(nu["value"] - nu["points"])))
    m["nuovi_bias"] = float(np.mean(nu["value"] - nu["points"]))
    m["nuovi_rho"] = _rho(nu["points"], nu["value"])
    m["p_real_gt_value_up"] = float(np.mean(df["points"] > df["value_up"]))
    for r in ROLES:
        s = df[df["ruolo"] == r]
        m[f"p_real_gt_value_up_{r}"] = float(np.mean(s["points"] > s["value_up"]))
    # quantili per giocatore (stage S3): coverage q10-q90 e P(reale<q10)
    # per ruolo e per fascia di valore predetto
    lo = "value_q10" if "value_q10" in df.columns else ("q10" if "q10" in df.columns else None)
    hi = "value_q90" if "value_q90" in df.columns else ("q90" if "q90" in df.columns else None)
    if lo and hi:
        cov = (df["points"] >= df[lo]) & (df["points"] <= df[hi])
        m["coverage_q10_q90"] = float(cov.mean())
        m["p_real_lt_q10"] = float(np.mean(df["points"] < df[lo]))
        m["p_real_gt_q90"] = float(np.mean(df["points"] > df[hi]))
        for r in ROLES:
            mr = df["ruolo"] == r
            m[f"coverage_q10_q90_{r}"] = float(cov[mr].mean())
            m[f"p_real_lt_q10_{r}"] = float(np.mean(df.loc[mr, "points"] < df.loc[mr, lo]))
        fas = np.digitize(df["value"].to_numpy(float), FASCE)
        for i, nome in enumerate(FASCE_NOMI):
            mf = fas == i
            m[f"coverage_q10_q90_f{nome}"] = float(cov[mf].mean()) if mf.any() else float("nan")
            m[f"p_real_gt_value_up_f{nome}"] = (float(np.mean(df.loc[mf, "points"] > df.loc[mf, "value_up"]))
                                                if mf.any() else float("nan"))
            m[f"n_f{nome}"] = int(mf.sum())
        if "sigma" in df.columns:
            m["sigma_media"] = float(df["sigma"].mean())
    # metriche sul "resto" (giornate K+1..38): per la variante con K giornate
    # viste coincidono con quelle sopra; per il baseline tolgono i punti gia'
    # fatti dalla predizione di stagione intera.
    if k > 0 and "pts_gk" in df.columns:
        yr = df["points"] - df["pts_gk"]
        vr = df["value"] - df["pts_gk"]
        m["resto_mae"] = float(np.mean(np.abs(vr - yr)))
        m["resto_rho"] = _rho(yr, vr)
    return m


def nan_rates(cols: list[str], te: pd.DataFrame, live: pd.DataFrame) -> dict:
    """Tasso di NaN delle feature nel test del backtest e nel listone live."""
    out = {}
    for c in cols:
        a = float(te[c].isna().mean()) if c in te.columns else float("nan")
        b = float(live[c].isna().mean()) if c in live.columns else float("nan")
        out[c] = {"test": round(a, 3), "live": round(b, 3)}
    return out


def run(tag: str, k: int, seasons: list[str], model_k: int | None = None,
        model: str | None = None, role_calib: bool | None = None,
        extra: list[str] | None = None) -> dict:
    """k: giornate note (feature *_gk nel test, metriche sul resto);
    model_k: K passato al modello (default k; 0 = modello di stagione intera
    che non vede le giornate, per confrontare sullo stesso resto);
    model / role_calib: regressore del resto e offset per ruolo (default =
    costanti VALUE_MODEL / ROLE_CALIB di f1_make_predictions)."""
    model_k = k if model_k is None else model_k
    if extra is not None:
        # stage S4: feature extra del solo modello valore in prova (in
        # aggiunta a FEATS_EXTRA di f1; xmat_valore legge la costante a runtime)
        f1.FEATS_EXTRA = list(dict.fromkeys(list(f1.FEATS_EXTRA) + list(extra)))
    res = {"tag": tag, "k": k, "model_k": model_k, "model": model,
           "role_calib": role_calib, "feats_extra": list(getattr(f1, "FEATS_EXTRA", [])),
           "seasons": {}}
    kw = _kw_k(f1.catboost_values, model_k)
    sig = inspect.signature(f1.catboost_values).parameters
    if model is not None and "model" in sig:
        kw["model"] = model
    if role_calib is not None and "role_calib" in sig:
        kw["role_calib"] = role_calib
    live = truth_frame(LIVE_SEASON, k) if hasattr(f1, "gk_features") else load_season(LIVE_SEASON)
    for season in seasons:
        t0 = time.time()
        train_ss = f1.TARGETS[season]
        te = truth_frame(season, k).reset_index(drop=True)
        te_model = (te.drop(columns=[c for c in te.columns if c.endswith("_gk")])
                    if model_k != k else te)
        vals = f1.catboost_values(season, train_ss, te_model, **kw)
        df = te[["master_id", "nome", "ruolo", "nuovo_in_serie_a"]].copy()
        df["nuovo"] = df["nuovo_in_serie_a"].fillna(0).astype(int)
        for c in vals.columns:
            df[c] = vals[c].to_numpy(float)
        df["points"] = te["points"].to_numpy(float)
        df["pres_true"] = te["pres"].to_numpy(float)
        for c in ("pts_gk", "pres_gk", "fm_gk"):
            if c in te.columns:
                df[c] = te[c].to_numpy(float)
        m = metrics(df, k)
        m["secondi"] = round(time.time() - t0, 1)
        extra = ([c for c in te.columns if c.endswith("_gk")]
                 + [c for c in getattr(f1, "FEATS_EXTRA", []) if c in te.columns])
        m["nan_rate"] = nan_rates(extra, te, live)
        res["seasons"][season] = m
        df.to_csv(OUT / f"pred_valore_{tag}_{season}.csv", index=False, encoding="utf-8")
        print(f"\n== {season} (train {train_ss}, K={k}, K modello={model_k}) [{tag}] {m['secondi']}s")
        print(f"  tutti      n={m['n']}  MAE {m['mae']:.2f}  bias {m['bias']:+.2f}  rho {m['rho']:.4f}"
              f"  | presenze MAE {m['mae_pres']:.2f} bias {m['bias_pres']:+.2f}")
        print(f"  value>=50  n={m['roster_n']}  MAE {m['roster_mae']:.2f}  bias {m['roster_bias']:+.2f}"
              f"  rho {m['roster_rho']:.4f}")
        print("  per ruolo  " + "  ".join(f"{r}: MAE {m[f'mae_{r}']:.1f} bias {m[f'bias_{r}']:+.1f}"
                                          f" rho {m[f'rho_{r}']:.3f}" for r in ROLES))
        print(f"  nuovi      n={m['nuovi_n']}  MAE {m['nuovi_mae']:.2f}  bias {m['nuovi_bias']:+.2f}"
              f"  rho {m['nuovi_rho']:.4f}")
        line = f"  P(reale>value_up) {m['p_real_gt_value_up']:.3f}"
        if "coverage_q10_q90" in m:
            line += f"  coverage q10-q90 {m['coverage_q10_q90']:.3f}"
        if "resto_mae" in m:
            line += f"  | resto g{k + 1}-38: MAE {m['resto_mae']:.2f} rho {m['resto_rho']:.4f}"
        print(line)
        print("  P(reale>value_up) per ruolo: "
              + "  ".join(f"{r} {m[f'p_real_gt_value_up_{r}']:.3f}" for r in ROLES))
        if "coverage_q10_q90" in m:
            print("  coverage q10-q90 per ruolo:  "
                  + "  ".join(f"{r} {m[f'coverage_q10_q90_{r}']:.3f}" for r in ROLES)
                  + f"  | P(reale<q10) per ruolo: "
                  + "  ".join(f"{r} {m[f'p_real_lt_q10_{r}']:.3f}" for r in ROLES))
            print("  per fascia (n / coverage / P(>value_up)): "
                  + "  ".join(f"{nome}: {m[f'n_f{nome}']} / {m[f'coverage_q10_q90_f{nome}']:.3f}"
                              f" / {m[f'p_real_gt_value_up_f{nome}']:.3f}" for nome in FASCE_NOMI)
                  + (f"  | sigma media {m['sigma_media']:.1f}" if "sigma_media" in m else ""))
        if extra:
            print("  NaN feature (test vs listone 2026-27): "
                  + ", ".join(f"{c} {v['test']:.2f}/{v['live']:.2f}" for c, v in m["nan_rate"].items()))
    path = OUT / f"backtest_valore_{tag}.json"
    path.write_text(json.dumps(res, indent=1), encoding="utf-8")
    print(f"\nsalvato {path.relative_to(ROOT)}")
    return res


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tag", default="baseline")
    ap.add_argument("--k", type=int, default=0, help="giornate gia' giocate all'asta")
    ap.add_argument("--seasons", nargs="*", default=TEST_SEASONS)
    ap.add_argument("--model-k", type=int, default=None,
                    help="K visto dal modello (default = --k; 0 = stagione intera)")
    ap.add_argument("--model", default=None, choices=["catboost", "tabpfn", "blend"],
                    help="regressore del resto (default VALUE_MODEL di f1)")
    ap.add_argument("--role-calib", type=int, default=None, choices=[0, 1],
                    help="offset per ruolo dall'OOF (default ROLE_CALIB di f1)")
    ap.add_argument("--extra", nargs="*", default=None,
                    help="feature extra (colonne dei players_*.parquet) aggiunte a FEATS_EXTRA")
    a = ap.parse_args()
    rc = None if a.role_calib is None else bool(a.role_calib)
    run(a.tag, a.k, a.seasons, a.model_k, a.model, rc, a.extra)


if __name__ == "__main__":
    main()
