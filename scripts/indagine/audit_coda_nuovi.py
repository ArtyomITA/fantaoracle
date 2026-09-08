"""Verifica delle due decisioni prese sui nuovi arrivati nel prezzo.

Erano state motivate con due misure deboli: la dispersione del prezzo fra aste
diverse (che dice quanto le leghe sono in disaccordo, non quanto il modello
sbaglia) e la presenza del flag "nuovo" fra le feature (che non prova da sola
che il modello lo usi). Qui si controllano con le misure giuste, tutte fuori
campione, sul target d'asta autentico:

  A) COPERTURA e PINBALL degli intervalli q10-q90 per nuovi e vecchi, per
     fascia di prezzo: se sui nuovi la banda fosse davvero troppo stretta, la
     copertura sarebbe sotto quella dei vecchi e allargarla ridurrebbe il
     pinball. Si prova anche la coda che era stata rimossa (q90 + 0.5 q50).
  B) ABLATION: lo stesso modello con e senza il flag `nuovo_in_serie_a`, e i
     residui sui nuovi nei due casi. Se togliendo il flag i nuovi vengono
     sottostimati, il modello lo stava usando: correggere a valle sarebbe
     contarlo due volte.

Uso: python scripts/indagine/audit_coda_nuovi.py
Output: data/livello0/audit_coda_nuovi.json
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

from f1_train_price import FEATURES_NUM, load_season, with_conformal  # noqa: E402

BUDGET = 500
PROVE = [(["2021-22"], "2023-24"), (["2021-22", "2023-24"], "2024-25")]


def pinball(pred: np.ndarray, vero: np.ndarray, q: float) -> float:
    d = vero - pred
    return float(np.mean(np.maximum(q * d, (q - 1) * d)))


def quantili_catboost(tr, te, feats):
    from catboost import CatBoostRegressor
    m = CatBoostRegressor(iterations=600, learning_rate=0.05, depth=5, l2_leaf_reg=6,
                          loss_function="MultiQuantile:alpha=0.1,0.5,0.9",
                          random_seed=7, verbose=False)
    m.fit(tr[feats].astype(float), tr["y"])
    p = np.asarray(m.predict(te[feats].astype(float)), dtype=float)
    return {"q10": p[:, 0], "q50": p[:, 1], "q90": p[:, 2]}


def main():
    out = {}
    for train_ss, test_s in PROVE:
        tr = pd.concat([load_season(s) for s in train_ss], ignore_index=True)
        tr = tr[~tr["y"].isna()].reset_index(drop=True)
        te = load_season(test_s).reset_index(drop=True)
        y = te["y"].to_numpy(dtype=float) * BUDGET
        nuovo = (te["nuovo_in_serie_a"] == 1).to_numpy()
        ok = ~np.isnan(y)
        p = quantili_catboost(tr, te, FEATURES_NUM)
        q10, q50, q90 = (p[k] * BUDGET for k in ("q10", "q50", "q90"))
        q90_largo = q90 + 0.5 * q50          # la coda che era stata rimossa

        print(f"\n=== test {test_s} (target: aste estive reali) ===")
        print("A) copertura dell'intervallo q10-q90 e pinball sul q90")
        res_a = {}
        for et, m in [("nuovi", ok & nuovo), ("vecchi", ok & ~nuovo)]:
            cop = float(np.mean((y[m] >= q10[m]) & (y[m] <= q90[m])))
            pb = pinball(q90[m], y[m], 0.9)
            pb_l = pinball(q90_largo[m], y[m], 0.9)
            cop_l = float(np.mean((y[m] >= q10[m]) & (y[m] <= q90_largo[m])))
            print(f"   {et:7s} n={m.sum():4d} copertura {cop:.2f} (con coda allargata "
                  f"{cop_l:.2f}) | pinball q90 {pb:.2f} -> allargata {pb_l:.2f}")
            res_a[et] = {"n": int(m.sum()), "copertura": round(cop, 3),
                         "copertura_allargata": round(cop_l, 3),
                         "pinball_q90": round(pb, 3), "pinball_q90_allargato": round(pb_l, 3)}
        for lo, hi, nome in [(0, 10, "sotto 10cr"), (10, 40, "10-40cr"), (40, 999, "oltre 40cr")]:
            m = ok & (y >= lo) & (y < hi)
            if m.sum() < 15:
                continue
            mn, mv = m & nuovo, m & ~nuovo
            if mn.sum() < 5:
                continue
            print(f"   fascia {nome:11s} nuovi n={mn.sum():3d} copertura "
                  f"{np.mean((y[mn] >= q10[mn]) & (y[mn] <= q90[mn])):.2f} | "
                  f"vecchi n={mv.sum():3d} copertura "
                  f"{np.mean((y[mv] >= q10[mv]) & (y[mv] <= q90[mv])):.2f}")

        print("B) ablation del flag `nuovo_in_serie_a`")
        senza = [f for f in FEATURES_NUM if f != "nuovo_in_serie_a"]
        p2 = quantili_catboost(tr, te, senza)
        q50_2 = p2["q50"] * BUDGET
        res_b = {}
        for et, m in [("nuovi", ok & nuovo), ("vecchi", ok & ~nuovo)]:
            b1, b2 = float(np.mean(q50[m] - y[m])), float(np.mean(q50_2[m] - y[m]))
            e1, e2 = float(np.mean(np.abs(q50[m] - y[m]))), float(np.mean(np.abs(q50_2[m] - y[m])))
            print(f"   {et:7s} con flag: scarto {b1:+6.2f} errore {e1:5.2f} | "
                  f"senza flag: scarto {b2:+6.2f} errore {e2:5.2f}")
            res_b[et] = {"bias_con": round(b1, 2), "bias_senza": round(b2, 2),
                         "mae_con": round(e1, 2), "mae_senza": round(e2, 2)}
        delta = res_b["nuovi"]["bias_con"] - res_b["nuovi"]["bias_senza"]
        print(f"   -> togliendo il flag i nuovi si spostano di {-delta:+.2f} crediti: "
              f"{'il modello lo usa' if abs(delta) > 0.5 else 'il modello non lo usa'}")
        out[test_s] = {"coperture": res_a, "ablation": res_b, "delta_flag": round(delta, 2)}
    d = ROOT / "data" / "livello0"
    d.mkdir(exist_ok=True)
    (d / "audit_coda_nuovi.json").write_text(json.dumps(out, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main()
