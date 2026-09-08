"""O4 — come combinare i quantili dei due modelli di prezzo (solo misura).

Confronta tre modi di mettere insieme TabPFN e CatBoost, tutti fuori campione:

  A) ENSEMBLE ATTUALE   media dei quantili dei due modelli, ognuno gia'
                        conformalizzato per conto suo (quello in produzione)
  B) INVILUPPO          minimo dei due q10 e massimo dei due q90 (banda che
                        contiene entrambe le bande)
  C) ENSEMBLE CALIBRATO prima si media, poi si applica la correzione conformal
                        all'ensemble gia' formato

Separazione temporale: il train e' fatto di stagioni precedenti, la
calibrazione esce dal train (mai dal test) e il test e' la stagione successiva,
mai guardata per scegliere nulla. La mediana q50 e' identica in tutti e tre i
casi per costruzione: si controlla che sia davvero cosi'.

Il target e' il prezzo MEDIO fra le aste di quella stagione, non il singolo
martelletto della nostra lega: la copertura qui misurata riguarda la media di
lega. Per una singola asta va aggiunta la dispersione fra leghe, che non e'
compresa in questi intervalli.

Nessuna garanzia teorica dell'80%: la correzione conformal e' stimata su un
modello addestrato sull'80% del train e applicata a un modello riaddestrato
sul 100%, e calibrazione e test non sono scambiabili (sono stagioni diverse).
Va letta come correzione empirica.

Uso: python scripts/indagine/check_o4_quantili.py
Output: data/livello0/check_o4_quantili.json
"""
from __future__ import annotations

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
warnings.filterwarnings("ignore")

from f1_train_price import (fit_predict_catboost, fit_predict_tabpfn,  # noqa: E402
                            load_season, with_conformal)

BUDGET = 500
PROVE = [(["2021-22"], "2023-24"), (["2021-22", "2023-24"], "2024-25")]
TARGET_COV = 0.80


def pinball(pred, vero, q):
    d = vero - pred
    return float(np.mean(np.maximum(q * d, (q - 1) * d)))


def conformal_su_ensemble(tr, te, rng_seed=13):
    """Come `with_conformal`, ma applicato all'ensemble gia' formato: si
    divide il train in fit e calibrazione, si costruisce l'ensemble sul solo
    pezzo di fit, si misura di quanto va allargato sulla calibrazione, poi si
    rifa' l'ensemble su tutto il train e si allarga di quel delta."""
    idx = np.arange(len(tr))
    rs = np.random.RandomState(rng_seed)
    rs.shuffle(idx)
    n_cal = max(30, int(0.2 * len(tr)))
    cal_idx, fit_idx = idx[:n_cal], idx[n_cal:]
    tr_fit = tr.iloc[fit_idx].reset_index(drop=True)
    tr_cal = tr.iloc[cal_idx].reset_index(drop=True)

    def ens(a, b):
        t, c = fit_predict_tabpfn(a, b), fit_predict_catboost(a, b)
        return {k: (np.asarray(t[k], float) + np.asarray(c[k], float)) / 2
                for k in ("q10", "q50", "q90")}

    p_cal = ens(tr_fit, tr_cal)
    y_cal = tr_cal["y"].to_numpy(dtype=float)
    scores = np.maximum(p_cal["q10"] - y_cal, y_cal - p_cal["q90"])
    delta = float(np.quantile(scores, TARGET_COV))
    p_te = ens(tr, te)
    p_te["q10"] = np.clip(p_te["q10"] - max(0.0, delta), 0.001, None)
    p_te["q90"] = p_te["q90"] + max(0.0, delta)
    return p_te


def misura(nome, p, y, ok, nuovo):
    q10, q50, q90 = (np.asarray(p[k], float) * BUDGET for k in ("q10", "q50", "q90"))
    r = {"nome": nome,
         "copertura": round(float(np.mean((y[ok] >= q10[ok]) & (y[ok] <= q90[ok]))), 3),
         "sotto_q10": round(float(np.mean(y[ok] < q10[ok])), 3),
         "sopra_q90": round(float(np.mean(y[ok] > q90[ok])), 3),
         "pinball_q10": round(pinball(q10[ok], y[ok], 0.1), 3),
         "pinball_q90": round(pinball(q90[ok], y[ok], 0.9), 3),
         "ampiezza_mediana": round(float(np.median(q90[ok] - q10[ok])), 2),
         "q50_mae": round(float(np.mean(np.abs(q50[ok] - y[ok]))), 3),
         "cop_nuovi": round(float(np.mean((y[ok & nuovo] >= q10[ok & nuovo])
                                          & (y[ok & nuovo] <= q90[ok & nuovo]))), 3),
         "cop_vecchi": round(float(np.mean((y[ok & ~nuovo] >= q10[ok & ~nuovo])
                                           & (y[ok & ~nuovo] <= q90[ok & ~nuovo]))), 3)}
    n = int(ok.sum())
    r["se_copertura"] = round(float(np.sqrt(max(r["copertura"] * (1 - r["copertura"]), 1e-9) / n)), 3)
    print(f"   {nome:24s} cop {r['copertura']:.2f} +-{r['se_copertura']:.2f} "
          f"(sotto q10 {r['sotto_q10']:.2f} / sopra q90 {r['sopra_q90']:.2f}) | "
          f"nuovi {r['cop_nuovi']:.2f} vecchi {r['cop_vecchi']:.2f} | "
          f"pinball {r['pinball_q10']:.2f}/{r['pinball_q90']:.2f} | "
          f"ampiezza {r['ampiezza_mediana']:5.1f}cr | q50 MAE {r['q50_mae']:.2f}")
    return r


def main():
    out = {}
    for train_ss, test_s in PROVE:
        tr = pd.concat([load_season(s) for s in train_ss], ignore_index=True)
        tr = tr[~tr["y"].isna()].reset_index(drop=True)
        te = load_season(test_s).reset_index(drop=True)
        y = te["y"].to_numpy(dtype=float) * BUDGET
        ok = ~np.isnan(y)
        nuovo = (te["nuovo_in_serie_a"] == 1).to_numpy()
        t0 = time.time()
        pt = with_conformal(fit_predict_tabpfn, tr, te)
        pc = with_conformal(fit_predict_catboost, tr, te)
        att = {k: (np.asarray(pt[k], float) + np.asarray(pc[k], float)) / 2
               for k in ("q10", "q50", "q90")}
        inv = {"q10": np.minimum(pt["q10"], pc["q10"]),
               "q50": att["q50"],
               "q90": np.maximum(pt["q90"], pc["q90"])}
        cal = conformal_su_ensemble(tr, te)
        print(f"\n=== test {test_s}: n={int(ok.sum())} (nuovi {int((ok & nuovo).sum())}), "
              f"train {train_ss} {len(tr)} righe, {time.time() - t0:.0f}s ===")
        righe = [misura("A ensemble attuale", att, y, ok, nuovo),
                 misura("B inviluppo min/max", inv, y, ok, nuovo),
                 misura("C ensemble calibrato", cal, y, ok, nuovo),
                 misura("  (TabPFN da solo)", pt, y, ok, nuovo),
                 misura("  (CatBoost da solo)", pc, y, ok, nuovo)]
        q50_uguali = bool(np.allclose(att["q50"], inv["q50"]))
        print(f"   q50 identica fra A e B: {q50_uguali} | "
              f"q50 di C diversa (ensemble rifatto): "
              f"{float(np.max(np.abs(np.asarray(cal['q50']) - np.asarray(att['q50']))) * BUDGET):.2f} cr max")
        out[test_s] = {"n": int(ok.sum()), "n_nuovi": int((ok & nuovo).sum()),
                       "righe": righe, "q50_identica_A_B": q50_uguali}
    d = ROOT / "data" / "livello0"
    d.mkdir(exist_ok=True)
    (d / "check_o4_quantili.json").write_text(json.dumps(out, indent=1, ensure_ascii=False),
                                              encoding="utf-8")
    print(f"\nsalvato in {d / 'check_o4_quantili.json'}")


if __name__ == "__main__":
    main()
