"""Quanto pesa, sul modello delle presenze, l'informazione posteriore al cutoff.

## Perche' questa misura

Il bersaglio del cubo (`b_predictions`) viene da un CatBoost che predice
`pres_resto` su 36 feature ereditate in blocco dal modello del prezzo. Almeno
due di quelle feature non sono disponibili alla data dell'asta:

- **`fvm`**: nei listoni delle stagioni archiviate e' un valore di **fine
  stagione**. Prova di contenuto, calcolata qui: nel 2024-25 la correlazione di
  rango fra `fvm` e `qt_a` (quotazione a fine campionato) vale 0,900 contro
  0,708 con `qt_i` (iniziale); nel listone fresco 2026-27, dove il campionato
  non e' finito, le due coincidono quasi (0,920 e 0,941). E dato `fvm`, la
  quotazione iniziale non porta piu' nessuna informazione sulle presenze —
  correlazione parziale su ranghi ~0,00 — mentre dato `qt_i`, `fvm` ne porta
  0,65-0,67.
- **`quot_fs_sett`**: viene dallo snapshot fanta.soccer di giornata 2 o 3
  della stagione da predire. Per il 2024-25 e' la giornata 3, rilevata il
  30/08/2024, contro una prima giornata giocata il 17-19/08: due giornate del
  target sono gia' dentro la feature.

Questo script misura la differenza fra il modello com'e' e lo stesso modello
senza le feature non databili, a parita' di tutto il resto. Non e' una
proposta: e' la misura che serve prima di decidere.

## Che cosa NON misura

Non dice quale sia il modello giusto, e non tara nulla. Confronta due insiemi
di feature con lo stesso regressore, lo stesso train e lo stesso test.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

PROC = ROOT / "data" / "processed"
OUT = ROOT / "data" / "l1"

# Feature la cui disponibilita' alla data dell'asta NON e' dimostrata.
# `tm_value_log` deriva da `tm_value_eur` al 1/9: sul 2024-25 nessuna
# valutazione risulta posteriore alla giornata 1, quindi resta fuori
# dall'elenco ma va guardata quando cambia la fonte.
POSTERIORI_AL_CUTOFF = ["fvm", "quot_fs_sett", "cambio_squadra",
                        "team_prev_xg"]


def presenze_osservate(stagione: str) -> pd.Series:
    """Presenze a voto realizzate: `sv == 0` sulle righe dei voti."""
    v = pd.read_parquet(PROC / f"votes_{stagione}.parquet")
    return v[v.sv == 0].groupby("master_id").size().rename("pres_vere")


def prova_fvm(stagioni) -> dict:
    """La prova di contenuto su `fvm`, ricalcolata a ogni esecuzione."""
    from scipy.stats import rankdata
    fuori = {}
    for st in stagioni:
        f = ROOT / "data" / "raw" / "quotazioni" / f"fantacalcioit_{st}.csv"
        if not f.exists():
            continue
        d = pd.read_csv(f)
        col = {n: [c for c in d.columns if c.startswith(n) and "classic" in c]
               for n in ("qt_i", "qt_a", "fvm")}
        if not all(col.values()):
            continue
        qi, qa, fv = (col["qt_i"][0], col["qt_a"][0], col["fvm"][0])
        s = d[[qi, qa, fv]].apply(pd.to_numeric, errors="coerce").dropna()
        if len(s) < 50:
            continue
        fuori[st] = {
            "n": int(len(s)),
            "rho_fvm_qt_iniziale": round(float(
                s[fv].corr(s[qi], method="spearman")), 4),
            "rho_fvm_qt_attuale": round(float(
                s[fv].corr(s[qa], method="spearman")), 4),
            "quota_qt_a_uguale_qt_i": round(float((s[qa] == s[qi]).mean()), 4)}
        pres = presenze_osservate(st)
        pl = pd.read_parquet(PROC / f"players_{st}.parquet")
        m = pl.merge(pres, on="master_id", how="left").fillna({"pres_vere": 0})
        m = (m[["fvm", "qt_i", "pres_vere"]]
             .apply(pd.to_numeric, errors="coerce").dropna())
        if len(m) > 50:
            def par(x, y, z):
                x, y, z = (rankdata(m[c]) for c in (x, y, z))
                r = lambda a, b: float(np.corrcoef(a, b)[0, 1])  # noqa: E731
                rxy, rxz, ryz = r(x, y), r(x, z), r(y, z)
                return (rxy - rxz * ryz) / np.sqrt((1 - rxz**2) * (1 - ryz**2))
            fuori[st]["parziale_fvm_presenze_dato_qt_i"] = round(
                par("fvm", "pres_vere", "qt_i"), 4)
            fuori[st]["parziale_qt_i_presenze_dato_fvm"] = round(
                par("qt_i", "pres_vere", "fvm"), 4)
    return fuori


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("stagione", nargs="?", default="2024-25")
    ap.add_argument("--k", type=int, default=0,
                    help="giornate gia' giocate all'origine. 0 = asta estiva")
    ap.add_argument("--semi", type=int, default=5,
                    help="semi del regressore: l'incertezza del fit non e' "
                         "zero, e una differenza va letta contro di essa")
    ap.add_argument("--per-feature", action="store_true",
                    help="toglie una feature per volta: serve a sapere quale "
                         "pesa, non a scegliere un modello")
    ap.add_argument("--fuori", default=None)
    a = ap.parse_args()

    import f1_make_predictions as F
    from catboost import CatBoostRegressor

    stagioni_train = F.TARGETS[a.stagione]
    print(f"stagione {a.stagione}, K={a.k}, train {stagioni_train}")

    frames = {s: F._season_points_frame(s, a.k) for s in stagioni_train}
    tr = pd.concat(frames.values(), ignore_index=True)
    te = F._season_points_frame(a.stagione, a.k)
    Xtr, Xte = F.xmat_valore(tr), F.xmat_valore(te)
    tutte = list(Xtr.columns)
    ammesse = [c for c in tutte if c not in POSTERIORI_AL_CUTOFF]
    tolte = [c for c in tutte if c in POSTERIORI_AL_CUTOFF]
    print(f"  feature: {len(tutte)} in tutto, {len(ammesse)} ammesse, "
          f"tolte {tolte}")

    vere = presenze_osservate(a.stagione)
    te = te.copy()
    te["pres_vere"] = te.master_id.map(vere).fillna(0.0)
    # con K giornate gia' giocate, il target del modello e' il RESTO
    te["resto_vero"] = te["pres_vere"] - te.get("pres_gk", 0.0)

    bracci = [("tutte", tutte), ("solo_ammesse", ammesse)]
    if a.per_feature:
        for c in tolte:
            bracci.append((f"senza_{c}", [x for x in tutte if x != c]))

    risultati = {}
    for nome, colonne in bracci:
        per_seme = []
        for i in range(a.semi):
            m = CatBoostRegressor(iterations=500, learning_rate=0.05, depth=4,
                                  l2_leaf_reg=6, random_seed=7 + i,
                                  verbose=False)
            m.fit(Xtr[colonne], tr["pres_resto"])
            p = np.clip(np.asarray(m.predict(Xte[colonne]), dtype=float),
                        0.0, F.GIORNATE - a.k)
            err = np.abs(p - te.resto_vero.to_numpy())
            per_seme.append({
                "mae": float(np.mean(err)),
                "rho": float(pd.Series(p).corr(te.resto_vero.reset_index(
                    drop=True), method="spearman")),
                "predizioni": p})
        mae = np.array([x["mae"] for x in per_seme])
        rho = np.array([x["rho"] for x in per_seme])
        risultati[nome] = {
            "feature": len(colonne), "semi": a.semi,
            "mae_medio": float(mae.mean()),
            "mae_es": float(mae.std(ddof=1) / np.sqrt(len(mae)))
                       if len(mae) > 1 else float("nan"),
            "rho_medio": float(rho.mean()),
            "rho_es": float(rho.std(ddof=1) / np.sqrt(len(rho)))
                       if len(rho) > 1 else float("nan"),
            "_p": np.mean([x["predizioni"] for x in per_seme], axis=0),
            "_mae_per_seme": [float(x) for x in mae]}
        print(f"  {nome:14s} MAE {risultati[nome]['mae_medio']:.4f} "
              f"± {risultati[nome]['mae_es']:.4f}   "
              f"rho {risultati[nome]['rho_medio']:.4f} "
              f"± {risultati[nome]['rho_es']:.4f}")

    # differenza appaiata PER SEME: i due bracci vedono gli stessi semi, e
    # l'unita' e' la differenza entro coppia, non la differenza fra due medie
    d = (np.array(risultati["solo_ammesse"]["_mae_per_seme"])
         - np.array(risultati["tutte"]["_mae_per_seme"]))
    d_medio = float(d.mean())
    d_es = (float(d.std(ddof=1) / np.sqrt(len(d))) if len(d) > 1
            else float("nan"))
    fra = float(np.corrcoef(risultati["tutte"]["_p"],
                            risultati["solo_ammesse"]["_p"])[0, 1])
    print(f"\n  differenza MAE (ammesse meno tutte): {d_medio:+.4f} presenze, "
          f"es {d_es:.4f}")
    print(f"  correlazione fra le due previsioni: {fra:.4f}")

    if a.per_feature:
        print("\n  una feature per volta (differenza di MAE rispetto a tutte):")
        base = np.array(risultati["tutte"]["_mae_per_seme"])
        for c in tolte:
            dd = np.array(risultati[f"senza_{c}"]["_mae_per_seme"]) - base
            es = (float(dd.std(ddof=1) / np.sqrt(len(dd))) if len(dd) > 1
                  else float("nan"))
            print(f"    senza {c:16s} {float(dd.mean()):+7.4f} presenze, "
                  f"es {es:.4f}")

    prova = prova_fvm(list(dict.fromkeys(stagioni_train + [a.stagione])))
    print("\n  prova di contenuto su `fvm` (rho di rango):")
    for st, v in prova.items():
        print(f"    {st}: con qt_iniziale {v['rho_fvm_qt_iniziale']:.3f}, "
              f"con qt_attuale {v['rho_fvm_qt_attuale']:.3f}"
              + (f", parziale su presenze dato qt_i "
                 f"{v['parziale_fvm_presenze_dato_qt_i']:.3f}"
                 if "parziale_fvm_presenze_dato_qt_i" in v else ""))

    fuori = Path(a.fuori) if a.fuori else (
        OUT / f"ablazione_presenze_{a.stagione}_k{a.k}.json")
    fuori.parent.mkdir(parents=True, exist_ok=True)
    fuori.write_text(json.dumps({
        "stagione": a.stagione, "k": a.k, "train": stagioni_train,
        "feature_tolte": tolte, "feature_totali": len(tutte),
        "risultati": {k: {kk: vv for kk, vv in v.items() if kk != "_p"}
                      for k, v in risultati.items() if True}
                     if False else {k: {kk: vv for kk, vv in v.items()
                                        if not kk.startswith("_")}
                                    for k, v in risultati.items()},
        "differenza_mae_ammesse_meno_tutte": d_medio,
        "es_differenza_appaiata": d_es,
        "correlazione_fra_le_due_previsioni": fra,
        "prova_contenuto_fvm": prova,
        "nota": (
            "il confronto e' fra due insiemi di feature con lo stesso "
            "regressore, lo stesso train e lo stesso test. Una differenza "
            "piccola NON dimostra che le feature tolte fossero innocue: "
            "dimostra che il modello sa arrivare a un errore simile senza di "
            "loro su QUESTA stagione. E una differenza a favore di `tutte` "
            "non e' un merito: e' il vantaggio di aver visto l'esito."),
        "nota_target": (
            "il bersaglio e' `pres_resto`, cioe' le presenze a voto delle "
            "giornate K+1..38. Con K=0 e' la stagione intera.")},
        ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n  scritto in {fuori}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
