"""Fase 1 finale — predizioni B per le stagioni del torneo.

Per ogni stagione target, allenato SOLO sulle stagioni precedenti:
- prezzo: ensemble TabPFN-2 + CatBoost conformalizzato -> q10/q50/q90 in
  crediti (budget 500) per TUTTI i giocatori del listone;
- valore: punti di stagione (catboost_values: prime K giornate reali +
  resto predetto dal blend TabPFN/CatBoost, quantili conformalizzati),
  presenze e sigma per giocatore.
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
GIORNATE = 38
# feature dalle prime K giornate della stagione (asta DOPO K giornate):
# presenze con voto, media fantavoto (NaN se 0 presenze), punti gia' fatti
FEATS_GK = ["pres_gk", "fm_gk", "pts_gk"]
# regressore dei punti del resto di stagione: "catboost", "tabpfn" o "blend"
# (BLEND_W TabPFN + (1-BLEND_W) CatBoost). Scelto col backtest
# (scripts/indagine/backtest_valore.py --model ...), stage S2: blend batte
# CatBoost di -1.8/-1.0 MAE e +.026/+.007 rho (2024-25 / 2025-26) ed e' piu'
# stabile del TabPFN solo. Costo: ~3-10 min CPU per fit TabPFN (cache su disco).
VALUE_MODEL = "blend"
BLEND_W = 0.7
# offset di calibrazione per ruolo sull'OOF (shrink n/(n+ROLE_SHRINK_N) verso 0).
# Misurato nello stage S2: gli offset per ruolo stimati sull'OOF NON si
# trasferiscono alla stagione successiva (bias 2025-26 da -11.5 a -14.4, MAE
# +0.6): resta spento.
ROLE_CALIB = False
ROLE_SHRINK_N = 100
TABPFN_CACHE = ROOT / "data" / "indagine" / "tabpfn_cache"
# feature del SOLO modello valore oltre a quelle del prezzo (FEATURES_NUM),
# tutte da f0b_build_outputs:
# - cambio_squadra = squadra all'asta diversa dal listone dell'anno prima
#   (NaN se assente dal listone precedente);
# - stage S4, minuti e trend della stagione precedente: tm_prev_min_per_app
#   (minuti per presenza, TM appearances), tm_prev_share90 (minuti / 38*90),
#   prev1_pres_last10 (presenze con voto nelle ultime 10 giornate). Misurate
#   col blend (tag s4b_a): MAE -0.11/-0.07, fascia value>=50 -0.10/-0.19,
#   nuovi -0.08/-0.23 (2024-25 / 2025-26), rho invariata. Gli altri gruppi
#   provati (disciplina amm/esp per presenza, xGA/xPts/porte inviolate di
#   squadra, rigorista storico) peggiorano una delle due stagioni: restano
#   nei parquet ma fuori dal modello.
FEATS_EXTRA = ["cambio_squadra", "tm_prev_min_per_app", "tm_prev_share90",
               "prev1_pres_last10"]
# quantili del resto di stagione (stage S3): nativi TabPFN (o CatBoost
# MultiQuantile col modello catboost), poi conformalizzati per livello sull'OOF
# per ruolo x fascia di valore predetto (shrink verso il ruolo se n < CQ_N_MIN).
QUANTILI = [0.10, 0.25, 0.50, 0.75, 0.90]
FASCE_VALORE = [60.0, 150.0]      # <60, 60-150, >150 punti di stagione
CQ_N_MIN = 40
# Calibrazione (media e quantili) su fold "in avanti": la stagione s viene
# predetta dalle sole stagioni PRECEDENTI con storico voti (come all'asta
# vera). Il leave-one-season-out classico predice il 2023-24 col 2024-25 e
# ha bias di segno opposto (+11 contro -9 in avanti): la media OOF si
# annulla e la sottostima dell'anno dopo non viene corretta. Con True:
# 2025-26 calibrato sul fold 2024-25, 2026-27 sui fold 2024-25 e 2025-26
# (predizioni gia' in cache); 2024-25 resta senza calibrazione.
CALIB_FORWARD = True


def _season_votes(s: str) -> pd.DataFrame:
    """Voti della stagione (sv esclusi) con +1 porta inviolata sul fantavoto."""
    from fantabot.rules import clean_sheets
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
    return v


def giornate_giocate(s: str) -> int:
    """K della stagione: ultima giornata con voti (0 se il file manca)."""
    p = PROC / f"votes_{s}.parquet"
    if not p.exists():
        return 0
    v = pd.read_parquet(p, columns=["giornata"])
    return int(v["giornata"].max()) if len(v) else 0


def gk_features(s: str, k: int, votes: pd.DataFrame | None = None) -> pd.DataFrame:
    """pres_gk / fm_gk / pts_gk dalle SOLE giornate 1..K (nessun leakage
    oltre K). Indice master_id (str); chi non ha voti ha 0 presenze/punti e
    fm_gk NaN."""
    if votes is None:
        votes = _season_votes(s)
    g = votes[votes["giornata"] <= k].groupby("master_id")["fantavoto"]
    out = pd.DataFrame({"pres_gk": g.size().astype(float), "fm_gk": g.mean(),
                        "pts_gk": g.sum()})
    return out


def _season_points_frame(s: str, k: int = 0) -> pd.DataFrame:
    """Feature pre-asta + target: punti stagione (con +1 porta inviolata,
    regola della lega) e presenze. Con k > 0 aggiunge le feature delle prime
    K giornate e i target sul "resto" (giornate K+1..38)."""
    from f1_train_price import load_season
    df = load_season(s)
    v = _season_votes(s)
    pts = v.groupby("master_id")["fantavoto"].sum()
    pres = v.groupby("master_id").size()
    mid = df["master_id"].astype(str)
    df["points"] = mid.map(pts).fillna(0.0)
    df["pres"] = mid.map(pres).fillna(0.0).astype(float)
    gk = gk_features(s, k, v)
    for c in FEATS_GK:
        df[c] = mid.map(gk[c])
    df["pres_gk"] = df["pres_gk"].fillna(0.0)
    df["pts_gk"] = df["pts_gk"].fillna(0.0)
    df["points_resto"] = df["points"] - df["pts_gk"]
    df["pres_resto"] = df["pres"] - df["pres_gk"]
    return df


def xmat_valore(df: pd.DataFrame) -> pd.DataFrame:
    """Feature del modello valore: quelle del prezzo + prime K giornate."""
    from f1_train_price import xmat
    x = xmat(df)
    for c in FEATS_EXTRA + FEATS_GK:
        x[c] = df[c].astype(float) if c in df.columns else np.nan
    return x


def _tabpfn_regress(Xtr: np.ndarray, ytr: np.ndarray, Xte: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """TabPFN-2 (stesso checkpoint del prezzo) come regressore: ritorna
    (media, quantili QUANTILI per riga, shape (n, 5)) dallo stesso forward.
    Su CPU un fit costa ~3 minuti: le predizioni vengono salvate in
    data/indagine/tabpfn_cache/ con chiave = hash di (Xtr, ytr, Xte), cosi'
    lo stesso fit non viene mai ripetuto (feature diverse = chiave diversa)."""
    import hashlib
    h = hashlib.sha1()
    for arr in (Xtr, ytr, Xte):
        h.update(np.ascontiguousarray(arr, dtype=np.float32).tobytes())
        h.update(str(arr.shape).encode())
    TABPFN_CACHE.mkdir(parents=True, exist_ok=True)
    path = TABPFN_CACHE / f"{h.hexdigest()[:20]}_q.npz"
    if path.exists():
        z = np.load(path)
        return z["mean"], z["q"]
    from tabpfn import TabPFNRegressor
    m = TabPFNRegressor(device="cpu", random_state=7,
                        model_path="tabpfn-v2-regressor.ckpt",
                        ignore_pretraining_limits=True)
    m.fit(Xtr.astype(np.float32), ytr.astype(np.float32))
    out = m.predict(Xte.astype(np.float32), output_type="main", quantiles=QUANTILI)
    p = np.asarray(out["mean"], dtype=float).ravel()
    q = np.column_stack([np.asarray(x, dtype=float).ravel() for x in out["quantiles"]])
    np.savez(path, mean=p, q=q)
    return p, q


def _resto_predictor(model: str):
    """fit+predict del resto di stagione: 'catboost', 'tabpfn' o 'blend'
    (0.7 TabPFN + 0.3 CatBoost). Ritorna f(df_train, df_test) -> (media,
    quantili QUANTILI shape (n, 5)). Col blend i quantili sono quelli TabPFN
    traslati sulla media del blend; col catboost vengono da MultiQuantile."""
    from catboost import CatBoostRegressor

    def cat(df, te):
        m = CatBoostRegressor(iterations=700, learning_rate=0.04, depth=5,
                              l2_leaf_reg=6, random_seed=7, verbose=False)
        m.fit(xmat_valore(df), df["points_resto"])
        return np.asarray(m.predict(xmat_valore(te)), dtype=float)

    def cat_q(df, te):
        alphas = ",".join(str(a) for a in QUANTILI)
        m = CatBoostRegressor(iterations=700, learning_rate=0.04, depth=5,
                              l2_leaf_reg=6, random_seed=7, verbose=False,
                              loss_function=f"MultiQuantile:alpha={alphas}")
        m.fit(xmat_valore(df), df["points_resto"])
        return np.sort(np.asarray(m.predict(xmat_valore(te)), dtype=float), axis=1)

    def tab(df, te):
        return _tabpfn_regress(xmat_valore(df).to_numpy(np.float32),
                               df["points_resto"].to_numpy(np.float32),
                               xmat_valore(te).to_numpy(np.float32))

    if model == "catboost":
        return lambda df, te: (cat(df, te), cat_q(df, te))
    if model == "tabpfn":
        return tab
    if model == "blend":
        def blend(df, te):
            pt, qt = tab(df, te)
            p = BLEND_W * pt + (1.0 - BLEND_W) * cat(df, te)
            return p, qt + (p - pt)[:, None]
        return blend
    raise ValueError(f"modello valore sconosciuto: {model}")


def _fascia(value: np.ndarray) -> np.ndarray:
    """Indice di fascia (0, 1, 2) del valore predetto di stagione."""
    return np.digitize(np.asarray(value, dtype=float), FASCE_VALORE)


def _conformal_deltas(y: np.ndarray, q: np.ndarray, ruolo: np.ndarray,
                      fascia: np.ndarray) -> dict:
    """Correzione additiva per livello di quantile, per ruolo x fascia:
    delta = quantile_alpha(y - q_alpha) nel gruppo, con shrink lineare
    n/CQ_N_MIN verso il delta del ruolo (a sua volta verso il globale)."""
    def dq(mask):
        return np.array([np.quantile(y[mask] - q[mask, j], a) for j, a in enumerate(QUANTILI)])

    def shrink(d_grp, n, d_parent):
        w = min(1.0, n / CQ_N_MIN)
        return w * d_grp + (1.0 - w) * d_parent

    glob = dq(np.ones(len(y), dtype=bool))
    out = {}
    for r in ("P", "D", "C", "A"):
        mr = ruolo == r
        d_r = shrink(dq(mr), int(mr.sum()), glob) if mr.any() else glob
        for f in range(len(FASCE_VALORE) + 1):
            m = mr & (fascia == f)
            out[(r, f)] = shrink(dq(m), int(m.sum()), d_r) if m.any() else d_r
    return out


def catboost_values(season: str, train_ss: list[str], te: pd.DataFrame,
                    k: int = 0, model: str | None = None,
                    role_calib: bool | None = None) -> pd.DataFrame:
    """Modello valore sui punti del RESTO di stagione (giornate K+1..38;
    regressore = VALUE_MODEL: catboost, tabpfn o blend) + modello presenze
    CatBoost, con le prime K giornate come feature (pres_gk, fm_gk, pts_gk)
    sia nel train sia nel test. La mediana viene ricalibrata linearmente su
    predizioni out-of-fold (leave-one-season-out fra le stagioni di train),
    con offset per ruolo opzionale (ROLE_CALIB) stimato sullo stesso OOF.
    Output: value = pts_gk reali + resto predetto, pres = pres_gk + resto,
    value_q10/q25/q75/q90 = pts_gk + quantili del resto (nativi del
    regressore, conformalizzati per ruolo x fascia sull'OOF), value_up =
    value_q75, sigma = (q90 - q10) / 2.56.
    Con k=0 e' il modello di stagione intera. Se te non ha le colonne *_gk
    vengono calcolate dai voti della stagione (giornate <= k).
    Ritorna DataFrame (value, value_up, pres, pts_gk, pres_gk) allineato a te.index."""
    from catboost import CatBoostRegressor
    model = VALUE_MODEL if model is None else model
    role_calib = ROLE_CALIB if role_calib is None else role_calib
    xmat = xmat_valore
    fp = _resto_predictor(model)
    frames = {s: _season_points_frame(s, k) for s in train_ss}
    tr = pd.concat(frames.values(), ignore_index=True)
    if any(c not in te.columns for c in FEATS_GK):
        te = te.copy()
        gk = gk_features(season, k)
        mid = te["master_id"].astype(str)
        for c in FEATS_GK:
            te[c] = mid.map(gk[c])
        te["pres_gk"] = te["pres_gk"].fillna(0.0)
        te["pts_gk"] = te["pts_gk"].fillna(0.0)

    # Calibrazione LINEARE (real ~ a + b*pred) su predizioni out-of-fold delle
    # sole stagioni con storico voti completo (il 2021-22 non ce l'ha: senza
    # questo filtro la calibrazione impara spazzatura). La regressione alla
    # media comprime i top del 15-20% e gonfia la coda: lo stretch lo corregge.
    if CALIB_FORWARD:
        calib = [s for s in train_ss if s >= "2023-24"
                 and any(t >= "2023-24" and t < s for t in train_ss)]
        folds = {s: [t for t in train_ss if t < s] for s in calib}
    else:
        calib = [s for s in train_ss if s >= "2023-24"]
        calib = calib if len(calib) >= 2 else []
        folds = {s: [t for t in train_ss if t != s] for s in calib}
    oof_pred, oof_true, oof_role, oof_q, oof_gk = [], [], [], [], []
    if calib:
        for s in calib:
            rest = pd.concat([frames[t] for t in folds[s]], ignore_index=True)
            p_s, q_s = fp(rest, frames[s])
            oof_pred.append(p_s)
            oof_q.append(q_s)
            oof_true.append(frames[s]["points_resto"].to_numpy())
            oof_role.append(frames[s]["ruolo"].to_numpy())
            oof_gk.append(frames[s]["pts_gk"].to_numpy(dtype=float))
    off = {r: 0.0 for r in ("P", "D", "C", "A")}
    deltas = None
    if oof_pred:
        xp, yt = np.concatenate(oof_pred), np.concatenate(oof_true)
        b, a = np.polyfit(xp, yt, 1)
        b = float(min(1.6, max(1.0, b)))
        a = float(np.mean(yt - b * xp))     # intercetta coerente col b vincolato
        res = yt - (a + b * xp)
        sigma = float(np.std(res))
        # conformal dei quantili (stessa trasformazione lineare della media)
        # per ruolo x fascia del valore predetto OOF
        q_oof = a + b * np.concatenate(oof_q)
        fas = _fascia(np.concatenate(oof_gk) + np.clip(a + b * xp, 0.0, None))
        deltas = _conformal_deltas(yt, q_oof, np.concatenate(oof_role), fas)
        if role_calib:
            # offset per ruolo = scarto della media del residuo OOF nel ruolo
            # dalla media globale (la calibrazione lineare resta quella
            # globale, l'offset redistribuisce solo fra reparti), con shrink
            # verso 0: n / (n + ROLE_SHRINK_N). I portieri (n piccolo)
            # restano vicini al globale.
            rr = np.concatenate(oof_role)
            res_c = res - res.mean()
            for r in off:
                n = int((rr == r).sum())
                if n:
                    off[r] = float(res_c[rr == r].mean() * n / (n + ROLE_SHRINK_N))
            print("   offset per ruolo (OOF): " + " ".join(f"{r}={v:+.1f}" for r, v in off.items()))
    else:
        # default: nessuno stretch. Il backtest OOF (2023-24..2025-26) da'
        # b=1.00: condizionando sulla PREDIZIONE il modello e' gia' calibrato;
        # la "compressione" vista per decile di reale e' regressione alla media
        # nell'altro verso, non un bias da correggere.
        a, b, sigma = 0.0, 1.00, 43.0
    raw, raw_q = fp(tr, te)
    pts_gk = te["pts_gk"].to_numpy(dtype=float)
    pres_gk = te["pres_gk"].to_numpy(dtype=float)
    off_te = te["ruolo"].map(off).fillna(0.0).to_numpy(dtype=float)
    resto = np.clip(a + b * raw + off_te, 0.0, None)
    value = pts_gk + resto
    # quantili del resto: trasformazione lineare + conformal per ruolo x
    # fascia (se OOF disponibile), ordinati per riga e non negativi
    if deltas is not None:
        q_te = a + b * raw_q + off_te[:, None]
        fas_te = _fascia(value)
        ruoli = te["ruolo"].to_numpy()
        d = np.vstack([deltas.get((r, int(f)), np.zeros(len(QUANTILI)))
                       for r, f in zip(ruoli, fas_te)])
        q_te = q_te + d
    else:
        # senza fold di calibrazione i quantili nativi non sono verificabili
        # (misurato sul 2024-25: P(reale>q75) 0.32, coverage 0.73): si usa la
        # normale di default (sigma 43) come prima dello stage S3
        from scipy.stats import norm
        q_te = resto[:, None] + sigma * norm.ppf(QUANTILI)[None, :]
    q_te = np.sort(np.clip(q_te, 0.0, None), axis=1)
    vq = {f"value_q{int(round(a_ * 100))}": pts_gk + q_te[:, j] for j, a_ in enumerate(QUANTILI)}
    value_up = vq["value_q75"]               # q75 calibrato (prima: value + 0.674 sigma)
    sigma_i = (vq["value_q90"] - vq["value_q10"]) / 2.56
    mp = CatBoostRegressor(iterations=500, learning_rate=0.05, depth=4,
                           l2_leaf_reg=6, random_seed=7, verbose=False)
    mp.fit(xmat(tr), tr["pres_resto"])
    pres_resto = np.clip(np.asarray(mp.predict(xmat(te)), dtype=float), 0.0, GIORNATE - k)
    pres = pres_gk + pres_resto
    print(f"   calibrazione valore (K={k}): a={a:.1f} b={b:.2f} sigma={sigma:.0f} "
          f"(stagioni OOF {calib if oof_pred else 'default'})")
    out = {"value": value, "value_up": value_up, "pres": pres,
           "pts_gk": pts_gk, "pres_gk": pres_gk,
           "value_q10": vq["value_q10"], "value_q25": vq["value_q25"],
           "value_q75": vq["value_q75"], "value_q90": vq["value_q90"],
           "sigma": sigma_i}
    return pd.DataFrame(out, index=te.index)


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
    args = sys.argv[1:]
    wanted = [a for a in args if a in TARGETS]
    # --k N: giornate gia' giocate all'asta (feature + target sul resto).
    # Default: stagione corrente = giornate presenti nei voti; stagioni del
    # torneo (asta simulata pre-campionato) = 0.
    k_arg = int(args[args.index("--k") + 1]) if "--k" in args else None
    for season, train_ss in TARGETS.items():
        if wanted and season not in wanted:
            continue
        k = k_arg if k_arg is not None else (giornate_giocate(season) if season == "2026-27" else 0)
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
        values = catboost_values(season, train_ss, te, k=k)
        print(f"   giornate gia' giocate K={k}")
        out = {}
        for i, row in te.iterrows():
            out[str(row["master_id"])] = {
                "q10": round(float(preds["q10"][i]) * BUDGET, 2),
                "q50": round(float(preds["q50"][i]) * BUDGET, 2),
                "q90": round(float(preds["q90"][i]) * BUDGET, 2),
                "value": round(float(values["value"].iloc[i]), 1),
                "value_up": round(float(values["value_up"].iloc[i]), 1),
                "pres": round(float(values["pres"].iloc[i]), 1),
                "pts_gk": round(float(values["pts_gk"].iloc[i]), 1),
                "pres_gk": round(float(values["pres_gk"].iloc[i]), 1),
                "value_q10": round(float(values["value_q10"].iloc[i]), 1),
                "value_q25": round(float(values["value_q25"].iloc[i]), 1),
                "value_q75": round(float(values["value_q75"].iloc[i]), 1),
                "value_q90": round(float(values["value_q90"].iloc[i]), 1),
                "sigma": round(float(values["sigma"].iloc[i]), 1),
                "k": k,
            }
        path = PROC / f"b_predictions_{season}.json"
        path.write_text(json.dumps(out), encoding="utf-8")
        top = te.assign(q50=preds["q50"] * BUDGET).nlargest(8, "q50")
        print(f"{season}: {len(out)} predizioni -> {path.name}")
        for _, r in top.iterrows():
            print(f"   {r['nome']:22s} {r['ruolo']}  q50={r['q50']:.0f}")


if __name__ == "__main__":
    main()
