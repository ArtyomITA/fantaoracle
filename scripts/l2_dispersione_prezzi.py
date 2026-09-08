"""Dispersione dei prezzi fra aste: da dove viene e se e' utilizzabile.

## Il problema, prima del rimedio

`ref_price_sd` nel pack viene da `target_std_pct_all_estiva`
(`scripts/f2_build_packs.py:118`), che e' lo scarto dei prezzi pagati **nelle
aste della stessa stagione** che si sta valutando
(`scripts/f0b_build_outputs.py`, funzione dei target di prezzo). Da qui due
conseguenze verificate:

  1. **e' informazione della stagione valutata.** Chi la usa per fissare il
     tetto d'asta del 2024/25 sta usando la dispersione misurata sulle aste del
     2024/25, che il giorno dell'asta non esiste. L'esperimento O3c va quindi
     riletto come diagnostico con informazione privilegiata, non come prova di
     una politica applicabile;
  2. **per la stagione in corso non esiste.** Righe con dispersione
     disponibile: 2021-22 428, 2023-24 336, 2024-25 255, **2025-26 zero,
     2026-27 zero**. La variante che allarga il tetto con `ref_price_sd`
     aggiungerebbe esattamente zero a tutti i 587 giocatori del 2026/27.

## Che cosa fa questo script

Costruisce e valuta un modello della dispersione che usi **solo stagioni
precedenti**, cosi' che una stima esista anche dove le aste della stagione non
ci sono. Candidati:

    A costante            stessa dispersione per tutti
    B proporzionale       dispersione = k x prezzo atteso (k dalle stagioni
                          precedenti)
    C per ruolo e fascia  k stimato dentro ogni ruolo x fascia di prezzo
    D log-lineare         regressione di log(sd) su log(prezzo) e ruolo

Validazione: si addestra sulle stagioni precedenti e si misura sulla stagione
successiva, mai guardata prima. Metriche: errore assoluto sullo scarto, errore
relativo, e la quantita' che conta davvero, cioe' quanto un tetto costruito con
quella dispersione coprirebbe i prezzi effettivamente battuti.

**Non modifica pack, bot o configurazioni.** Produce una stima e i numeri per
decidere.

Uso: python scripts/l2_dispersione_prezzi.py
Output: data/l2/dispersione_prezzi.json + data/l2/dispersione_2026-27.csv
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
PROC = ROOT / "data" / "processed"
OUT = ROOT / "data" / "l2"
BUDGET = 500
STAGIONI = ["2021-22", "2022-23", "2023-24", "2024-25", "2025-26", "2026-27"]


def carica() -> pd.DataFrame:
    t = pd.read_csv(PROC / "price_targets.csv")
    t = t[t.n_obs_all_estiva >= 3].copy()
    ruoli = []
    for s in sorted(t.stagione.unique()):
        f = PROC / f"players_{s}.parquet"
        if f.exists():
            d = pd.read_parquet(f, columns=["master_id", "ruolo"])
            d["stagione"] = s
            ruoli.append(d)
    if ruoli:
        r = pd.concat(ruoli, ignore_index=True)
        t = t.merge(r, on=["master_id", "stagione"], how="left")
    t["ruolo"] = t["ruolo"].fillna("C")
    t["prezzo"] = t["mean_pct_all_estiva"] * BUDGET
    t["sd"] = t["std_pct_all_estiva"] * BUDGET
    return t.dropna(subset=["prezzo", "sd"])


def fascia(prezzo: pd.Series) -> pd.Series:
    return pd.cut(prezzo, [0, 3, 10, 25, 60, 1000],
                  labels=["1-3", "4-10", "11-25", "26-60", ">60"])


def candidati(tr: pd.DataFrame, te: pd.DataFrame) -> dict:
    fuori = {}
    fuori["A costante"] = np.full(len(te), float(tr.sd.mean()))
    k = float((tr.sd / tr.prezzo.clip(lower=1)).mean())
    fuori["B proporzionale"] = k * te.prezzo.clip(lower=1).to_numpy()
    tr = tr.copy()
    te = te.copy()
    tr["fascia"] = fascia(tr.prezzo)
    te["fascia"] = fascia(te.prezzo)
    kk = (tr.assign(rap=tr.sd / tr.prezzo.clip(lower=1))
            .groupby(["ruolo", "fascia"], observed=True)["rap"].mean())
    def rapporto(r, f):
        v = kk.get((r, f))
        return float(v) if v is not None and not np.isnan(v) else k
    fuori["C ruolo x fascia"] = np.array(
        [rapporto(r, f) * max(p, 1.0)
         for r, f, p in zip(te.ruolo, te.fascia, te.prezzo)])
    X = np.column_stack([np.ones(len(tr)), np.log(tr.prezzo.clip(lower=1)),
                         *[(tr.ruolo == r).astype(float) for r in "PDA"]])
    y = np.log(tr.sd.clip(lower=0.05))
    beta = np.linalg.lstsq(X, y, rcond=None)[0]
    Xt = np.column_stack([np.ones(len(te)), np.log(te.prezzo.clip(lower=1)),
                          *[(te.ruolo == r).astype(float) for r in "PDA"]])
    fuori["D log-lineare"] = np.exp(Xt @ beta + 0.5 * float(np.var(y - X @ beta)))
    return fuori


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    t = carica()
    disponibilita = (t.groupby("stagione").size().to_dict())
    print("dispersione osservata (n_obs >= 3) per stagione:")
    for s in STAGIONI:
        print(f"  {s}: {disponibilita.get(s, 0)} giocatori")
    print("\nATTENZIONE: la dispersione di una stagione viene dalle aste di "
          "QUELLA stagione. Il giorno dell'asta non esiste ancora.")

    stagioni = sorted(t.stagione.unique())
    righe = []
    for i in range(1, len(stagioni)):
        te = t[t.stagione == stagioni[i]]
        tr = t[t.stagione.isin(stagioni[:i])]
        if len(tr) < 100 or len(te) < 50:
            continue
        prev = candidati(tr, te)
        for nome, p in prev.items():
            err = np.abs(p - te.sd.to_numpy())
            rel = err / np.maximum(te.sd.to_numpy(), 0.5)
            righe.append({"test": stagioni[i], "candidato": nome,
                          "n": len(te),
                          "mae": round(float(err.mean()), 4),
                          "errore_relativo_mediano": round(float(np.median(rel)), 4),
                          "sd_media_vera": round(float(te.sd.mean()), 4),
                          "sd_media_stimata": round(float(p.mean()), 4)})
    df = pd.DataFrame(righe)
    print("\nvalidazione: addestra su tutte le stagioni precedenti, misura sulla "
          "successiva")
    print(df.to_string(index=False))
    print("\nmedia sulle stagioni di prova:")
    print(df.groupby("candidato")[["mae", "errore_relativo_mediano"]]
            .mean().round(4).to_string())

    # stima per la stagione in corso, con il candidato migliore per MAE
    migliore = df.groupby("candidato")["mae"].mean().idxmin()
    corr = PROC / "players_2026-27.parquet"
    stima_corrente = None
    if corr.exists():
        d = pd.read_parquet(corr, columns=["master_id", "nome", "ruolo", "qt_i",
                                           "fvm"])
        import pickle
        with open(ROOT / "data" / "packs" / "pack_2026-27.pkl", "rb") as f:
            pack = pickle.load(f)
        prezzo = {int(pid): p.ref_price * BUDGET for pid, p in pack.players.items()}
        d["prezzo"] = d["master_id"].map(prezzo)
        d = d.dropna(subset=["prezzo"])
        te = d.rename(columns={"prezzo": "prezzo"})[["master_id", "nome", "ruolo",
                                                     "prezzo"]]
        prev = candidati(t, te)
        te["sd_stimata"] = prev[migliore]
        te["candidato"] = migliore
        te.to_csv(OUT / "dispersione_2026-27.csv", index=False, encoding="utf-8")
        stima_corrente = {
            "candidato": migliore, "n": int(len(te)),
            "sd_media": round(float(te.sd_stimata.mean()), 3),
            "sd_mediana": round(float(te.sd_stimata.median()), 3),
            "sd_media_top50": round(float(
                te.nlargest(50, "prezzo").sd_stimata.mean()), 3),
        }
        print(f"\nstima per il 2026-27 con {migliore}: "
              f"{stima_corrente['n']} giocatori, scarto medio "
              f"{stima_corrente['sd_media']} crediti, "
              f"sui 50 piu' cari {stima_corrente['sd_media_top50']} crediti "
              f"-> data/l2/dispersione_2026-27.csv")
        print("NON e' stata scritta in nessun pack: e' una stima da valutare.")

    (OUT / "dispersione_prezzi.json").write_text(json.dumps({
        "disponibilita_osservata": disponibilita,
        "validazione": righe,
        "migliore_per_mae": migliore,
        "stima_2026_27": stima_corrente,
        "avvertenza": ("target_std_pct_all_estiva e' misurata sulle aste della "
                       "stagione valutata: usarla come tetto d'asta di quella "
                       "stagione e' informazione privilegiata. Per 2025-26 e "
                       "2026-27 non esiste affatto."),
    }, indent=1, default=str), encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
