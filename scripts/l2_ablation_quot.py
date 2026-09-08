"""Ablazione di `quot_fs_sett` sulla pipeline vera, non su un modello di ricerca.

## Perche' si rifa'

La prova precedente aveva usato un CatBoost non pesato senza conformal, con
quattro semi. La produzione e' un'altra cosa: ensemble TabPFN + CatBoost, pesi
`y_w = sqrt(n aste)`, correzione conformal split (CQR). Un vantaggio misurato
sul primo non dice niente sul secondo. Qui l'ablazione usa la pipeline
effettiva, con gli stessi split, gli stessi pesi e la stessa calibrazione, e
conserva le predizioni.

## Un problema temporale che resta comunque

`quot_fs_sett` e' la quotazione fanta.soccer allo snapshot piu' vicino al 1
settembre. `data/processed/_match/fs_snapshot.json` dice quale giornata e':
2 per il 2021-22, 3 per il 2023-24, il 2024-25 e il 2026-27.

Il bersaglio delle stagioni di addestramento e' invece il prezzo delle aste
`periodo <= 1`, cioe' aste tenute PRIMA del campionato o a ridosso della prima
giornata. Quindi in quelle stagioni la variabile e' misurata **dopo** il
bersaglio: incorpora due o tre giornate che chi partecipava all'asta non aveva
visto. Non e' un problema per l'inferenza sul 2026/27 (l'asta di quest'anno e'
dopo la terza giornata, quindi la quotazione esiste davvero), ma lo e' per la
relazione stimata: il modello impara un legame piu' forte del vero.

Questa ablazione misura quanto pesa la variabile. La correzione del disallineamento
temporale serve comunque, qualunque sia l'esito.

Uso: python scripts/l2_ablation_quot.py [--semi 5]
Output: data/l2/ablation_quot.json + predizioni per run e variante
"""
from __future__ import annotations

import argparse
import json
import sys
import time
import warnings
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))
OUT = ROOT / "data" / "l2"
warnings.filterwarnings("ignore")

import f1_train_price as f1  # noqa: E402

RUNS = [("R1", ["2021-22"], "2023-24"),
        ("R2", ["2021-22", "2023-24"], "2024-25")]


def ensemble(tr, te, seme):
    t = f1.with_conformal(f1.fit_predict_tabpfn, tr, te, rng_seed=seme)
    c = f1.with_conformal(f1.fit_predict_catboost, tr, te, rng_seed=seme)
    return {k: (np.asarray(t[k], float) + np.asarray(c[k], float)) / 2
            for k in ("q10", "q50", "q90")}


def bootstrap_diff(a, b, n_boot=4000, seme=11):
    rng = np.random.default_rng(seme)
    d = np.asarray(a, float) - np.asarray(b, float)
    idx = rng.integers(0, len(d), (n_boot, len(d)))
    m = d[idx].mean(1)
    return float(d.mean()), (float(np.percentile(m, 2.5)),
                             float(np.percentile(m, 97.5)))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--semi", type=int, default=5)
    a = ap.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    originali = list(f1.FEATURES_NUM)
    print("snapshot fanta.soccer usato per quot_fs_sett (giornata):")
    snap = json.loads((ROOT / "data/processed/_match/fs_snapshot.json")
                      .read_text("utf-8"))
    for k, v in snap.items():
        print(f"  {k}: giornata {v[0]}")
    print("bersaglio delle stagioni di addestramento: aste periodo <= 1 "
          "(pre-campionato o prima giornata)")

    stagioni = {s: f1.load_season(s) for s in
                ["2021-22", "2023-24", "2024-25"]}
    righe, dettaglio = [], {}
    for run, train_ss, test_s in RUNS:
        tr = pd.concat([stagioni[s] for s in train_ss], ignore_index=True)
        tr = tr[tr["y"].notna()].reset_index(drop=True)
        te = stagioni[test_s].reset_index(drop=True)
        y = te["y"].to_numpy(float)
        w = te["y_w"].to_numpy(float)
        print(f"\n=== {run}: train {train_ss} ({len(tr)} righe) -> test "
              f"{test_s} ({int(np.isfinite(y).sum())} con prezzo)")
        for variante, feats in (("con quot_fs_sett", originali),
                                ("senza quot_fs_sett",
                                 [f for f in originali if f != "quot_fs_sett"])):
            f1.FEATURES_NUM = list(feats)
            per_seme = []
            t0 = time.time()
            for seme in range(13, 13 + a.semi):
                p = ensemble(tr, te, seme)
                m = f1.evaluate(y, w, p)
                m["seme"] = seme
                per_seme.append(m)
                np.savez(OUT / f"ablation_{run}_{variante.split()[0]}_{seme}.npz",
                         **{k: p[k] for k in ("q10", "q50", "q90")},
                         master_id=te["master_id"].to_numpy())
            med = {k: float(np.mean([x[k] for x in per_seme]))
                   for k in ("spearman", "mae_pct", "mae_top50_crediti",
                             "coverage_q10_q90", "pinball")}
            med.update({"run": run, "variante": variante, "semi": a.semi,
                        "secondi": round(time.time() - t0, 1),
                        "n_feature": len(feats)})
            righe.append(med)
            dettaglio[f"{run}|{variante}"] = per_seme
            print(f"  {variante:20s} MAE {med['mae_pct'] * 500:6.3f} crediti | "
                  f"top50 {med['mae_top50_crediti']:6.2f} | rho "
                  f"{med['spearman']:.4f} | copertura "
                  f"{med['coverage_q10_q90']:.3f} | pinball {med['pinball']:.5f} "
                  f"({med['secondi']:.0f} s)")
        # differenza appaiata sui residui, stesso seme e stesso test
        con = np.mean([np.load(OUT / f"ablation_{run}_con_{s}.npz")["q50"]
                       for s in range(13, 13 + a.semi)], axis=0)
        senza = np.mean([np.load(OUT / f"ablation_{run}_senza_{s}.npz")["q50"]
                         for s in range(13, 13 + a.semi)], axis=0)
        mask = np.isfinite(y)
        e_con = np.abs(y[mask] - con[mask])
        e_senza = np.abs(y[mask] - senza[mask])
        d, ic = bootstrap_diff(e_senza, e_con)
        print(f"  differenza appaiata (senza - con) sull'errore assoluto: "
              f"{d * 500:+.3f} crediti, IC95 [{ic[0] * 500:+.3f}, {ic[1] * 500:+.3f}]")
        print("  (negativo = togliere la variabile migliora)")
        dettaglio[f"{run}|differenza"] = {
            "media_crediti": round(d * 500, 4),
            "ic95_crediti": [round(ic[0] * 500, 4), round(ic[1] * 500, 4)],
            "n": int(mask.sum())}
    f1.FEATURES_NUM = originali
    df = pd.DataFrame(righe)
    df.to_csv(OUT / "ablation_quot.csv", index=False)
    (OUT / "ablation_quot.json").write_text(
        json.dumps({"riepilogo": righe, "dettaglio": dettaglio,
                    "snapshot_fanta_soccer": snap}, indent=1, default=str),
        encoding="utf-8")
    print("\n" + df.to_string(index=False))
    print(f"\nscritto {OUT / 'ablation_quot.csv'} e le predizioni per seme")
    return 0


if __name__ == "__main__":
    sys.exit(main())
