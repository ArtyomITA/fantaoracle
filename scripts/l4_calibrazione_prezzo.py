"""L4 — calibrazione per segmento degli intervalli di prezzo (Mondrian conformal).

Sola lettura sul progetto: legge `data/processed/pred_ens_tab_cat_{stagione}.csv`
e `data/processed/players_{stagione}.parquet`, scrive SOLO nella cartella di
uscita passata con `--out` (per difetto lo scratchpad w5). Non tocca nessun
artefatto d'asta.

Disegno (fissato in criteri_prima_L4.md, prima di guardare i numeri):
  - celle: fascia di q50 in crediti [0,3) [3,8) [8,15) [15,30) [30,60) [60+]
    per ruolo P/D/C/A = 24 celle;
  - punteggi conformal s = max(q10 - y, y - q90) (correzione incrementale
    sopra il delta globale gia' applicato da `f1_train_price.with_conformal`);
  - delta di cella = quantile 0,80 di s nella cella, con shrink verso il delta
    globale: d = (n_c*d_c + n0*d_glob) / (n_c + n0), n0 = 30;
  - applicazione: q10' = q10 - d, q90' = q90 + d (d negativo stringe);
  - protocollo fuori tempo: delta stimati su una stagione, applicati all'altra.

Uso:
  set PYTHONIOENCODING=utf-8
  python scripts/l4_calibrazione_prezzo.py --out <cartella>
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
PROC = ROOT / "data" / "processed"

# fasce di q50 in CREDITI (bordi superiori esclusi); 6 fasce, indici 0..5
FASCE_CREDITI = [3.0, 8.0, 15.0, 30.0, 60.0]
ETICHETTE_FASCE = ["[0,3)", "[3,8)", "[8,15)", "[15,30)", "[30,60)", "[60+]"]
RUOLI = ("P", "D", "C", "A")
COPERTURA_NOMINALE = 0.80
N0_SHRINK = 30.0
BUDGET_CREDITI = 500.0   # y e q* sono frazioni di budget: *500 = crediti


# ---------------------------------------------------------------- funzioni pure
def fascia_di(q50_crediti) -> np.ndarray:
    """Indice di fascia (0..5) del q50 espresso in crediti."""
    return np.digitize(np.asarray(q50_crediti, dtype=float), FASCE_CREDITI)


def punteggi_conformal(y, q10, q90) -> np.ndarray:
    """s = max(q10 - y, y - q90): positivo fuori intervallo, negativo dentro."""
    y = np.asarray(y, dtype=float)
    return np.maximum(np.asarray(q10, dtype=float) - y,
                      y - np.asarray(q90, dtype=float))


def shrink_delta(d_cella: float, n_cella: int, d_globale: float,
                 n0: float = N0_SHRINK) -> float:
    """Media pesata fra delta di cella e delta globale: n0 osservazioni
    fittizie a favore del globale. n_cella = 0 -> delta globale."""
    n = float(n_cella)
    if n <= 0:
        return float(d_globale)
    return float((n * float(d_cella) + n0 * float(d_globale)) / (n + n0))


def copertura(y, q10, q90) -> float:
    """Frazione di y dentro [q10, q90]."""
    y = np.asarray(y, dtype=float)
    dentro = (y >= np.asarray(q10, dtype=float)) & (y <= np.asarray(q90, dtype=float))
    return float(np.mean(dentro)) if len(y) else float("nan")


def pinball(y, q10, q90) -> float:
    """Somma delle pinball loss ai livelli 0,1 e 0,9 (come f1_train_price.evaluate)."""
    y = np.asarray(y, dtype=float)
    tot = 0.0
    for q, a in ((np.asarray(q10, dtype=float), 0.1),
                 (np.asarray(q90, dtype=float), 0.9)):
        d = y - q
        tot += float(np.mean(np.maximum(a * d, (a - 1.0) * d)))
    return tot


def stima_delta_celle(ruolo, fascia, s, cop_nominale: float = COPERTURA_NOMINALE,
                      n0: float = N0_SHRINK) -> tuple[dict, float, dict]:
    """Delta per cella (ruolo, fascia) con shrink verso il delta globale.
    Ritorna (delta_per_cella, delta_globale, n_per_cella)."""
    ruolo = np.asarray(ruolo)
    fascia = np.asarray(fascia, dtype=int)
    s = np.asarray(s, dtype=float)
    d_glob = float(np.quantile(s, cop_nominale)) if len(s) else 0.0
    delta, enne = {}, {}
    for r in RUOLI:
        for f in range(len(FASCE_CREDITI) + 1):
            m = (ruolo == r) & (fascia == f)
            n = int(m.sum())
            enne[(r, f)] = n
            d_c = float(np.quantile(s[m], cop_nominale)) if n > 0 else d_glob
            delta[(r, f)] = shrink_delta(d_c, n, d_glob, n0)
    return delta, d_glob, enne


def applica_delta(q10, q90, ruolo, fascia, delta: dict, d_globale: float,
                  minimo_q10: float = 0.001):
    """q10' = q10 - d, q90' = q90 + d con d della cella (globale se assente)."""
    q10 = np.asarray(q10, dtype=float).copy()
    q90 = np.asarray(q90, dtype=float).copy()
    ruolo = np.asarray(ruolo)
    fascia = np.asarray(fascia, dtype=int)
    d = np.array([delta.get((r, int(f)), d_globale) for r, f in zip(ruolo, fascia)],
                 dtype=float)
    return np.maximum(q10 - d, minimo_q10), q90 + d


# ---------------------------------------------------------------- dati
def carica_stagione(stagione: str, modello: str = "ens_tab_cat",
                    dir_pred: Path | None = None) -> pd.DataFrame:
    """Predizioni salvate + bersaglio d'asta (target_mean_pct_all_estiva, n>=2).
    `dir_pred` permette di leggere predizioni rigenerate fuori dal progetto.
    Ritorna solo le righe con bersaglio valido."""
    pred = pd.read_csv((dir_pred or PROC) / f"pred_{modello}_{stagione}.csv")
    pl = pd.read_parquet(PROC / f"players_{stagione}.parquet",
                         columns=["master_id", "target_mean_pct_all_estiva",
                                  "target_n_obs_all_estiva"])
    df = pred.merge(pl, on="master_id", how="left")
    y = df["target_mean_pct_all_estiva"].astype(float)
    n = df["target_n_obs_all_estiva"].fillna(0).astype(float)
    df["y"] = y.where(n >= 2)
    df = df[~df["y"].isna()].reset_index(drop=True)
    df["fascia"] = fascia_di(df["q50"].to_numpy(dtype=float) * BUDGET_CREDITI)
    return df


def metriche(df: pd.DataFrame, q10, q90) -> dict:
    y = df["y"].to_numpy(dtype=float)
    amp = (np.asarray(q90, dtype=float) - np.asarray(q10, dtype=float)) * BUDGET_CREDITI
    return {
        "n": int(len(df)),
        "copertura": round(copertura(y, q10, q90), 4),
        "pinball": round(pinball(y, q10, q90), 6),
        "ampiezza_mediana_cr": round(float(np.median(amp)), 2),
    }


def tabella_celle(df: pd.DataFrame, q10a, q90a, q10b, q90b) -> pd.DataFrame:
    y = df["y"].to_numpy(dtype=float)
    righe = []
    for r in RUOLI:
        for f in range(len(FASCE_CREDITI) + 1):
            m = ((df["ruolo"].to_numpy() == r) & (df["fascia"].to_numpy() == f))
            n = int(m.sum())
            if n == 0:
                continue
            righe.append({
                "ruolo": r, "fascia": ETICHETTE_FASCE[f], "n": n,
                "cop_prima": round(copertura(y[m], np.asarray(q10a)[m], np.asarray(q90a)[m]), 3),
                "cop_dopo": round(copertura(y[m], np.asarray(q10b)[m], np.asarray(q90b)[m]), 3),
                "amp_prima_cr": round(float(np.median(
                    (np.asarray(q90a)[m] - np.asarray(q10a)[m]) * BUDGET_CREDITI)), 1),
                "amp_dopo_cr": round(float(np.median(
                    (np.asarray(q90b)[m] - np.asarray(q10b)[m]) * BUDGET_CREDITI)), 1),
            })
    return pd.DataFrame(righe)


def tabella_fasce(df: pd.DataFrame, q10a, q90a, q10b, q90b) -> pd.DataFrame:
    y = df["y"].to_numpy(dtype=float)
    righe = []
    for f in range(len(FASCE_CREDITI) + 1):
        m = df["fascia"].to_numpy() == f
        n = int(m.sum())
        if n == 0:
            continue
        righe.append({
            "fascia": ETICHETTE_FASCE[f], "n": n,
            "cop_prima": round(copertura(y[m], np.asarray(q10a)[m], np.asarray(q90a)[m]), 3),
            "cop_dopo": round(copertura(y[m], np.asarray(q10b)[m], np.asarray(q90b)[m]), 3),
        })
    return pd.DataFrame(righe)


def esperimento(stagione_stima: str, stagione_prova: str, modello: str,
                n0: float = N0_SHRINK, dir_pred: Path | None = None) -> dict:
    """Stima i delta su `stagione_stima`, li applica a `stagione_prova`."""
    dst = carica_stagione(stagione_stima, modello, dir_pred)
    dpr = carica_stagione(stagione_prova, modello, dir_pred)
    s = punteggi_conformal(dst["y"], dst["q10"], dst["q90"])
    delta, d_glob, enne = stima_delta_celle(dst["ruolo"].to_numpy(),
                                            dst["fascia"].to_numpy(), s, n0=n0)
    q10b, q90b = applica_delta(dpr["q10"], dpr["q90"], dpr["ruolo"].to_numpy(),
                               dpr["fascia"].to_numpy(), delta, d_glob)
    prima = metriche(dpr, dpr["q10"].to_numpy(dtype=float), dpr["q90"].to_numpy(dtype=float))
    dopo = metriche(dpr, q10b, q90b)
    return {
        "stagione_stima": stagione_stima,
        "stagione_prova": stagione_prova,
        "delta_globale_cr": round(d_glob * BUDGET_CREDITI, 3),
        "delta_celle_cr": {f"{r}|{ETICHETTE_FASCE[f]}": round(v * BUDGET_CREDITI, 3)
                           for (r, f), v in delta.items()},
        "n_celle_stima": {f"{r}|{ETICHETTE_FASCE[f]}": v for (r, f), v in enne.items()},
        "prima": prima, "dopo": dopo,
        "_tab_celle": tabella_celle(dpr, dpr["q10"], dpr["q90"], q10b, q90b),
        "_tab_fasce": tabella_fasce(dpr, dpr["q10"], dpr["q90"], q10b, q90b),
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(Path.home() / "l4_out"),
                    help="cartella di uscita (mai data/processed)")
    ap.add_argument("--modello", default="ens_tab_cat")
    ap.add_argument("--n0", type=float, default=N0_SHRINK)
    ap.add_argument("--pred-dir", default=None,
                    help="cartella delle predizioni (per difetto data/processed)")
    ap.add_argument("--tag", default="", help="suffisso dei file di uscita")
    a = ap.parse_args()
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    assert "processed" not in out.parts and "packs" not in out.parts, \
        "uscita vietata dentro data/processed o data/packs"

    ris = {}
    for stima, prova in (("2023-24", "2024-25"), ("2024-25", "2023-24")):
        e = esperimento(stima, prova, a.modello, n0=a.n0,
                        dir_pred=Path(a.pred_dir) if a.pred_dir else None)
        chiave = f"{stima}->{prova}"
        e["_tab_celle"].to_csv(out / f"l4_celle_{stima}_su_{prova}{a.tag}.csv", index=False)
        e["_tab_fasce"].to_csv(out / f"l4_fasce_{stima}_su_{prova}{a.tag}.csv", index=False)
        stampabile = {k: v for k, v in e.items() if not k.startswith("_")}
        ris[chiave] = stampabile
        print(f"=== {chiave}: prima {e['prima']}  dopo {e['dopo']}")
        print(e["_tab_fasce"].to_string(index=False))
    (out / f"l4_calibrazione_risultati{a.tag}.json").write_text(
        json.dumps(ris, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nscritto in {out}")


if __name__ == "__main__":
    main()
