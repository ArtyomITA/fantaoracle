"""Validazione del premio di prezzo sui nuovi arrivati in Serie A.

Nel codice c'e' una costante `HYPE_NUOVI = 1.20` (il q50 dei nuovi cari viene
alzato del 20%). Veniva da una misura fatta sui listini di fantacalcio-online
catturati a campionato in corso, che sappiamo gonfiare la fascia bassa di
+8/+17 crediti: se i nuovi si concentrano in fascia bassa, quel "premio" puo'
essere un artefatto della fonte.

Qui si rimisura sulle ASTE ESTIVE REALI (periodo <= 1), le uniche note prima
dell'asta, con due controlli:
  A) a parita' di quotazione iniziale e ruolo (cio' che il mercato vede)
  B) a parita' di punti realizzati e ruolo (quanto ha reso davvero)

Uso: python scripts/indagine/prova_premio_nuovi.py
Output: data/livello0/prova_premio_nuovi.json
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
PROC = ROOT / "data" / "processed"
warnings.filterwarnings("ignore")

STAGIONI = ["2021-22", "2023-24", "2024-25"]   # le sole con aste estive raccolte
BUDGET = 500


def punti_reali(season: str) -> pd.Series:
    from fantabot.rules import clean_sheets
    v = pd.read_parquet(PROC / f"votes_{season}.parquet")
    if "sv" in v.columns:
        v = v[v["sv"].fillna(0) == 0]
    v = v.copy()
    v["master_id"] = v["master_id"].astype(str)
    try:
        cs = clean_sheets(ROOT, season)
        v["fantavoto"] = v["fantavoto"] + [1.0 if (m, g) in cs else 0.0
                                           for m, g in zip(v["master_id"], v["giornata"])]
    except FileNotFoundError:
        pass
    return v.groupby("master_id")["fantavoto"].sum()


def carica() -> pd.DataFrame:
    righe = []
    for s in STAGIONI:
        d = pd.read_parquet(PROC / f"players_{s}.parquet")
        n = d["target_n_obs_all_estiva"].fillna(0).astype(float)
        prezzo = d["target_mean_pct_all_estiva"].astype(float) * BUDGET
        pts = d["master_id"].astype(str).map(punti_reali(s))
        m = (n >= 2) & prezzo.notna() & (prezzo > 0) & d["qt_i"].notna()
        righe.append(pd.DataFrame({
            "stagione": s, "nome": d.loc[m, "nome"], "ruolo": d.loc[m, "ruolo"],
            "qt": d.loc[m, "qt_i"].astype(float), "fvm": d.loc[m, "fvm"].astype(float),
            "prezzo": prezzo[m], "nuovo": d.loc[m, "nuovo_in_serie_a"].astype(int),
            "punti": pts[m].fillna(0.0), "n_aste": n[m]}))
    return pd.concat(righe, ignore_index=True)


def ols(X: np.ndarray, y: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Minimi quadrati con errori standard classici."""
    beta, *_ = np.linalg.lstsq(X, y, rcond=None)
    resid = y - X @ beta
    dof = max(1, len(y) - X.shape[1])
    s2 = float(resid @ resid) / dof
    cov = s2 * np.linalg.pinv(X.T @ X)
    return beta, np.sqrt(np.diag(cov))


def stima(df: pd.DataFrame, controllo: str, etichetta: str) -> dict:
    d = df[df[controllo] > 0].copy()
    y = np.log(d["prezzo"].to_numpy())
    cols = [np.ones(len(d)), np.log(d[controllo].to_numpy())]
    nomi = ["cost", f"log_{controllo}"]
    for r in ["D", "C", "A"]:
        cols.append((d["ruolo"] == r).astype(float).to_numpy())
        nomi.append(f"ruolo_{r}")
    for s in STAGIONI[1:]:
        cols.append((d["stagione"] == s).astype(float).to_numpy())
        nomi.append(f"st_{s}")
    cols.append(d["nuovo"].to_numpy(dtype=float))
    nomi.append("nuovo")
    beta, se = ols(np.column_stack(cols), y)
    i = nomi.index("nuovo")
    premio = float(np.exp(beta[i]) - 1)
    lo = float(np.exp(beta[i] - 1.96 * se[i]) - 1)
    hi = float(np.exp(beta[i] + 1.96 * se[i]) - 1)
    print(f"  {etichetta}: premio nuovi {premio:+.1%} "
          f"(IC95 {lo:+.1%}..{hi:+.1%}), n={len(d)} di cui nuovi {int(d.nuovo.sum())}")
    return {"premio": round(premio, 4), "ic_lo": round(lo, 4), "ic_hi": round(hi, 4),
            "n": int(len(d)), "n_nuovi": int(d["nuovo"].sum())}


def main():
    df = carica()
    out = {"n_totale": len(df), "n_nuovi": int(df["nuovo"].sum())}
    print(f"Aste estive reali {STAGIONI}: {len(df)} righe, {int(df.nuovo.sum())} nuovi\n")
    print("Premio di prezzo dei nuovi (regressione log-log, controlli ruolo e stagione):")
    out["a_parita_quotazione"] = stima(df, "qt", "A) a parita' di quotazione")
    d2 = df[df["punti"] > 0]
    out["a_parita_punti"] = stima(d2, "punti", "B) a parita' di punti realizzati")
    print("\nSolo giocatori cari (prezzo reale >= 10 crediti):")
    cari = df[df["prezzo"] >= 10]
    out["cari_quotazione"] = stima(cari, "qt", "A) cari, a parita' di quotazione")
    print("\nPrezzo medio per fascia di quotazione, nuovi vs vecchi:")
    df["fascia_qt"] = pd.cut(df["qt"], [0, 5, 10, 20, 50],
                             labels=["1-5", "6-10", "11-20", "21+"])
    tab = df.groupby(["fascia_qt", "nuovo"], observed=True)["prezzo"].agg(["size", "median"])
    print(tab.round(1).to_string())
    out["tabella_fasce"] = {f"{k[0]}_{'nuovo' if k[1] else 'vecchio'}":
                            {"n": int(v["size"]), "prezzo_mediano": round(float(v["median"]), 1)}
                            for k, v in tab.iterrows()}
    (ROOT / "data" / "livello0").mkdir(exist_ok=True)
    (ROOT / "data" / "livello0" / "prova_premio_nuovi.json").write_text(
        json.dumps(out, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main()
