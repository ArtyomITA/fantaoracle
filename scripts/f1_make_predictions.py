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
    # stagione corrente: tutto lo storico disponibile
    "2026-27": ["2021-22", "2023-24", "2024-25", "2025-26"],
}
BUDGET = 500


def _season_points_frame(s: str) -> pd.DataFrame:
    """Feature pre-asta + target: punti stagione (con +1 porta inviolata,
    regola della lega) e presenze."""
    from f1_train_price import load_season
    from fantabot.rules import clean_sheets
    df = load_season(s)
    v = pd.read_parquet(PROC / f"votes_{s}.parquet")
    if "sv" in v.columns:
        v = v[v["sv"].fillna(0) == 0]
    v = v.copy()
    v["master_id"] = v["master_id"].astype(str)
    try:
        cs = clean_sheets(ROOT, s)
        v["fantavoto"] = v["fantavoto"] + [1.0 if (m, g) in cs else 0.0
                                           for m, g in zip(v["master_id"], v["giornata"])]
    except FileNotFoundError:
        pass
    pts = v.groupby("master_id")["fantavoto"].sum()
    pres = v.groupby("master_id").size()
    df["points"] = df["master_id"].astype(str).map(pts).fillna(0.0)
    df["pres"] = df["master_id"].astype(str).map(pres).fillna(0.0)
    return df


def catboost_values(season: str, train_ss: list[str], te: pd.DataFrame) -> pd.DataFrame:
    """Modello valore: CatBoost quantile (mediana e q75 dei punti stagione) +
    modello presenze. La mediana viene RICALIBRATA con regressione isotonica
    su predizioni out-of-fold (leave-one-season-out fra le stagioni di train):
    corregge la compressione (top -16/-20%, coda +38%) misurata nel backtest.
    Ritorna DataFrame (value, value_up, pres) allineato a te.index."""
    from catboost import CatBoostRegressor
    from f1_train_price import xmat
    frames = {s: _season_points_frame(s) for s in train_ss}
    tr = pd.concat(frames.values(), ignore_index=True)

    def fit(df):
        m = CatBoostRegressor(iterations=700, learning_rate=0.04, depth=5,
                              l2_leaf_reg=6, random_seed=7, verbose=False)
        m.fit(xmat(df), df["points"])
        return m

    # Calibrazione LINEARE (real ~ a + b*pred) su predizioni out-of-fold delle
    # sole stagioni con storico voti completo (il 2021-22 non ce l'ha: senza
    # questo filtro la calibrazione impara spazzatura). La regressione alla
    # media comprime i top del 15-20% e gonfia la coda: lo stretch lo corregge.
    calib = [s for s in train_ss if s >= "2023-24"]
    oof_pred, oof_true = [], []
    if len(calib) >= 2:
        for s in calib:
            rest = pd.concat([frames[t] for t in train_ss if t != s], ignore_index=True)
            p = np.asarray(fit(rest).predict(xmat(frames[s])), dtype=float)
            oof_pred.append(p)
            oof_true.append(frames[s]["points"].to_numpy())
    if oof_pred:
        xp, yt = np.concatenate(oof_pred), np.concatenate(oof_true)
        b, a = np.polyfit(xp, yt, 1)
        b = float(min(1.6, max(1.0, b)))
        a = float(a)
        sigma = float(np.std(yt - (a + b * xp)))
    else:
        # default: nessuno stretch. Il backtest OOF (2023-24..2025-26) da'
        # b=1.00: condizionando sulla PREDIZIONE il modello e' gia' calibrato;
        # la "compressione" vista per decile di reale e' regressione alla media
        # nell'altro verso, non un bias da correggere.
        a, b, sigma = 0.0, 1.00, 43.0
    m = fit(tr)
    raw = np.asarray(m.predict(xmat(te)), dtype=float)
    value = np.clip(a + b * raw, 0.0, None)
    value_up = value + 0.674 * sigma       # q75 di una normale attorno alla stima
    mp = CatBoostRegressor(iterations=500, learning_rate=0.05, depth=4,
                           l2_leaf_reg=6, random_seed=7, verbose=False)
    mp.fit(xmat(tr), tr["pres"])
    pres = np.clip(np.asarray(mp.predict(xmat(te)), dtype=float), 0.0, 38.0)
    print(f"   calibrazione valore: a={a:.1f} b={b:.2f} sigma={sigma:.0f} "
          f"(stagioni OOF {calib if oof_pred else 'default'})")
    return pd.DataFrame({"value": value, "value_up": value_up, "pres": pres}, index=te.index)


def marcel_values(season: str, te: pd.DataFrame) -> pd.Series:
    order = ["2021-22", "2022-23", "2023-24", "2024-25", "2025-26", "2026-27"]
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
    wanted = [a for a in sys.argv[1:] if a in TARGETS]
    for season, train_ss in TARGETS.items():
        if wanted and season not in wanted:
            continue
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
                "value": round(float(values["value"].iloc[i]), 1),
                "value_up": round(float(values["value_up"].iloc[i]), 1),
                "pres": round(float(values["pres"].iloc[i]), 1),
            }
        path = PROC / f"b_predictions_{season}.json"
        path.write_text(json.dumps(out), encoding="utf-8")
        top = te.assign(q50=preds["q50"] * BUDGET).nlargest(8, "q50")
        print(f"{season}: {len(out)} predizioni -> {path.name}")
        for _, r in top.iterrows():
            print(f"   {r['nome']:22s} {r['ruolo']}  q50={r['q50']:.0f}")


if __name__ == "__main__":
    main()
