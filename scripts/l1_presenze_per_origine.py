"""Previsioni di presenza **per origine temporale**, con manifesto verificabile.

## Perche' non basta rigenerare `b_predictions`

`b_predictions_{stagione}.json` ha tre difetti che nessuna rigenerazione
toglie:

1. **un solo file per stagione**, sovrascritto: due origini diverse non
   possono coesistere, e la precedente e' persa (`f1_make_predictions.py`
   scrive su un percorso fisso);
2. **nessuna data**: l'unica traccia dell'origine e' il campo `k` dentro il
   json, cioe' un *numero di giornata*, non un istante;
3. **feature posteriori al cutoff**. Misurato: togliendo `fvm` e
   `quot_fs_sett` l'errore assoluto medio del modello passa da 5,5688 a
   8,1259 presenze sul 2024-25 (+2,5571, es 0,0150) e da 6,0 a 8,3 sul
   2025-26. `fvm` da solo vale +1,78 presenze.

Questo script produce l'artefatto che manca: **una previsione per origine**,
con un manifesto che dichiara stagione, istante, universo, partite osservate e
residue, periodo delle etichette, feature ammesse e loro prova, impronte.

## Che cosa fa, e a che prezzo

Esegue **solo** il modello delle presenze: `f1_make_predictions` calcola prima
l'ensemble del prezzo, i quantili conformalizzati e la calibrazione, e nessuna
di quelle cose serve a una previsione di disponibilita'. Qui si riusano le sue
funzioni di costruzione dei dati e si addestra il solo `CatBoostRegressor` su
`pres_resto`.

Questa separazione non e' nuova: `scripts/l2_valuta_pres.py:469`
(`rifai_presenze`) fa gia' lo stesso con gli stessi iperparametri. Quello che
manca li' e' il contratto: manifesto per origine, feature con la prova della
loro disponibilita', artefatti distinti che non si sovrascrivono.

`--feature ammesse` (per difetto) esclude le feature la cui disponibilita'
all'origine non e' dimostrata. `--feature tutte` riproduce il comportamento
attuale: serve al confronto, e il manifesto lo dichiara **non utilizzabile
operativamente**.

## Il limite che resta, dichiarato

`votes_{stagione}.parquet` non ha date: la granularita' temporale disponibile
per le presenze gia' realizzate e' la **giornata**. Le partite anticipate di
una giornata a cavallo dell'origine esistono, ma non sono separabili da qui;
questo script le **scarta** invece di indovinarle, contandole fra le residue.
E' conservativo: la previsione usa meno informazione di quella realmente
disponibile, non di piu'.
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

from fantabot.tabellino import esecuzione as esec              # noqa: E402
from fantabot.tabellino import origine as org                  # noqa: E402

PROC = ROOT / "data" / "processed"
OUT = ROOT / "data" / "l1" / "presenze"

# La classificazione viene dalle prove in `l1_ablazione_presenze.py` e
# dall'audit del 9 settembre. Ogni voce dice **come si sa**.
PROVE_INGRESSI = {
    "fvm": (org.POSTERIORE,
            "nei listoni archiviati e' un valore di fine stagione: rho di "
            "rango con la quotazione a fine campionato 0,900 sul 2024-25 "
            "contro 0,708 con quella iniziale; nel listone fresco 2026-27 le "
            "due coincidono (0,920 e 0,941). Dato `fvm`, `qt_i` non porta piu' "
            "informazione sulle presenze (parziale ~0,00)"),
    # Post-cutoff quando l'origine e' l'asta estiva (`k = 0`), che e' il caso
    # dei backtest 2024-25 e 2025-26. Per il 2026-27 il file di predizioni
    # porta `k = 2`, e lo snapshot di giornata 3 contiene informazione fino
    # alla giornata 2: li' la feature sarebbe ammissibile. Resta esclusa
    # perche' il modello si addestra sulle stagioni dove la fuga c'e'.
    "quot_fs_sett": (org.POSTERIORE,
                     "snapshot fanta.soccer di giornata 2 o 3 della stagione "
                     "da predire: per il 2024-25 la giornata 3, rilevata il "
                     "30/08/2024, contro la prima giornata del 17-19/08. Con "
                     "un'origine a stagione iniziata e uno snapshot non "
                     "posteriore, tornerebbe ammissibile"),
    "cambio_squadra": (org.RICOSTRUITO,
                       "calcolata sulla squadra dello snapshot, che per le "
                       "stagioni archiviate e' post-campionato. Peso "
                       "misurato: +0,03 presenze di MAE, dentro il rumore"),
    "team_prev_xg": (org.RICOSTRUITO,
                     "agganciata alla stessa squadra dello snapshot. Peso "
                     "misurato: +0,01 presenze di MAE"),
    "tm_value_log": (org.DISPONIBILE,
                     "da `tm_value_eur` al 1/9: sul 2024-25 nessuna "
                     "valutazione risulta posteriore alla prima giornata"),
}
POSTERIORI = [k for k, (s, _) in PROVE_INGRESSI.items() if s == org.POSTERIORE]
RICOSTRUITE = [k for k, (s, _) in PROVE_INGRESSI.items() if s == org.RICOSTRUITO]


def giornate_concluse(stagione: str, origine) -> tuple[int, dict]:
    """Giornate le cui partite sono **tutte** anteriori all'origine.

    Il conteggio e' per giornata e non per partita perche' i voti non hanno
    date: una giornata a cavallo si scarta per intero. La diagnostica dice
    quante partite si perdono cosi', cosi' che il costo sia visibile.
    """
    part = pd.read_parquet(PROC / "l2_partite.parquet")
    part = part[part.stagione == stagione].copy()
    if part.empty:
        raise org.ContrattoViolato(f"nessuna partita per {stagione}")
    m = org.stato_partite(part, origine)
    per_g = m.groupby("giornata").stato_rispetto_origine.agg(
        tutte_prima=lambda s: bool((s == org.OSSERVATA).all()),
        osservate=lambda s: int((s == org.OSSERVATA).sum()),
        totale="size")
    concluse = sorted(g for g, r in per_g.iterrows() if r.tutte_prima)
    k = max(concluse) if concluse else 0
    if concluse and set(concluse) != set(range(1, k + 1)):
        # una giornata rinviata in mezzo: si prende il prefisso pieno
        k = 0
        for g in range(1, max(concluse) + 1):
            if g in concluse:
                k = g
            else:
                break
    a_cavallo = per_g[(~per_g.tutte_prima) & (per_g.osservate > 0)]
    conteggi = org.partite_residue(part, origine)
    diag = {
        "giornate_interamente_concluse": int(k),
        "giornate_a_cavallo": [int(g) for g in a_cavallo.index],
        "partite_anticipate_scartate": int(a_cavallo.osservate.sum()),
        "partite": conteggi,
        "nota": ("le partite anticipate di una giornata a cavallo sono "
                 "informazione realmente disponibile all'origine, ma i voti "
                 "non hanno date e non si possono separare: sono scartate, "
                 "non indovinate. La previsione usa meno informazione del "
                 "vero, mai di piu'.")}
    return int(k), diag


def costruisci_ingressi_dichiarati(colonne, ammesse) -> list:
    """Un `Ingresso` per ogni feature, con la prova o l'assenza di prova."""
    fuori = []
    for c in colonne:
        stato, prova = PROVE_INGRESSI.get(c, (None, ""))
        if stato is None:
            stato = org.DISPONIBILE
            prova = ("feature del listone o della stagione precedente: il "
                     "suo valore e' determinato prima dell'inizio della "
                     "stagione da predire")
        if c not in ammesse:
            # esclusa: non entra nel manifesto come ingresso usato
            continue
        fuori.append(org.Ingresso(nome=c, stato=stato, prova=prova,
                                  fonte="players_{stagione}.parquet"))
    return fuori


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("stagione", nargs="?", default="2024-25")
    ap.add_argument("--origine", default=None,
                    help="data della decisione (ISO). Per difetto il giorno "
                         "prima della prima partita della stagione")
    ap.add_argument("--feature", choices=["ammesse", "tutte"],
                    default="ammesse",
                    help="`ammesse` esclude le feature posteriori all'origine "
                         "e quelle solo ricostruite; `tutte` riproduce il "
                         "comportamento attuale, e il manifesto lo dichiara "
                         "non utilizzabile operativamente")
    ap.add_argument("--semi", type=int, default=3,
                    help="ripetizioni del fit: la previsione e' la media, e "
                         "lo scarto fra semi finisce nell'artefatto")
    ap.add_argument("--fuori", default=None)
    a = ap.parse_args()

    import f1_make_predictions as F
    from catboost import CatBoostRegressor

    part = pd.read_parquet(PROC / "l2_partite.parquet")
    part["data"] = pd.to_datetime(part["data"])
    cal = part[part.stagione == a.stagione]
    if cal.empty:
        print(f"stagione {a.stagione} assente da l2_partite.parquet")
        return 2
    origine = (pd.Timestamp(a.origine) if a.origine
               else cal.data.min() - pd.Timedelta(days=1))

    k, diag_cal = giornate_concluse(a.stagione, origine)
    residue = diag_cal["partite"]["residue"]
    print(f"stagione {a.stagione}, origine {origine.date()}")
    print(f"  giornate interamente concluse: {k}; partite osservate "
          f"{diag_cal['partite']['osservate']}, residue {residue}, "
          f"rinviate senza data {diag_cal['partite']['rinviate_senza_data']}")
    if diag_cal["partite_anticipate_scartate"]:
        print(f"  scartate {diag_cal['partite_anticipate_scartate']} partite "
              f"anticipate delle giornate {diag_cal['giornate_a_cavallo']}: i "
              "voti non hanno date")
    if residue == 0:
        print("  zero partite residue: non c'e' niente da prevedere. "
              "Un orizzonte di una giornata sarebbe inventato.")
        return 3

    stagioni_train = F.TARGETS[a.stagione]
    frames = {s: F._season_points_frame(s, k) for s in stagioni_train}
    tr = pd.concat(frames.values(), ignore_index=True)
    te = F._season_points_frame(a.stagione, k)
    Xtr, Xte = F.xmat_valore(tr), F.xmat_valore(te)
    tutte = list(Xtr.columns)
    escluse = (POSTERIORI + RICOSTRUITE) if a.feature == "ammesse" else []
    colonne = [c for c in tutte if c not in escluse]
    print(f"  feature: {len(colonne)} su {len(tutte)}"
          + (f", escluse {[c for c in tutte if c in escluse]}"
             if escluse else " (TUTTE: include ingressi non databili)"))

    previsioni = []
    for i in range(a.semi):
        m = CatBoostRegressor(iterations=500, learning_rate=0.05, depth=4,
                              l2_leaf_reg=6, random_seed=7 + i, verbose=False)
        m.fit(Xtr[colonne], tr["pres_resto"])
        previsioni.append(np.clip(
            np.asarray(m.predict(Xte[colonne]), dtype=float),
            0.0, float(F.GIORNATE - k)))
    P = np.vstack(previsioni)
    media, scarto = P.mean(axis=0), P.std(axis=0, ddof=1 if a.semi > 1 else 0)

    ids = [int(x) for x in te.master_id]
    gk = te.get("pres_gk", pd.Series(np.zeros(len(te)))).astype(float).to_numpy()
    # l'orizzonte e' quello vero: `orizzonte` rifiuta lo zero
    orizzonte_giornate = org.orizzonte(F.GIORNATE - k)

    ingressi = costruisci_ingressi_dichiarati(tutte, set(colonne))
    manifesto = org.ManifestoOrigine(
        stagione=a.stagione, origine=str(origine.date()), universo=ids,
        calendario_osservate=diag_cal["partite"]["osservate"],
        calendario_residue=residue,
        calendario_rinviate_senza_data=diag_cal["partite"]["rinviate_senza_data"],
        etichette_dal=None,
        etichette_fino_a=str((origine - pd.Timedelta(days=1)).date()),
        ingressi=ingressi, modello="presenze_catboost",
        versione_modello=f"pres-{a.feature}-k{k}",
        impronte=esec.impronte_ingressi(
            percorsi=[PROC / f"players_{s}.parquet" for s in
                      list(stagioni_train) + [a.stagione]]
            + [PROC / "l2_partite.parquet"],
            moduli=["fantabot.tabellino.origine"]),
        provenienza_temporale=json.dumps(diag_cal, ensure_ascii=False),
        note=("previsione del RESTO di stagione: presenze a voto nelle "
              f"{orizzonte_giornate} giornate ancora da giocare. Le presenze "
              "gia' realizzate stanno a parte in `presenze_gia_fatte`."))

    fuori = Path(a.fuori) if a.fuori else (OUT / manifesto.identificativo())
    fuori.mkdir(parents=True, exist_ok=True)
    tab = pd.DataFrame({
        "master_id": ids, "presenze_residue_attese": media,
        "scarto_fra_semi": scarto, "presenze_gia_fatte": gk,
        "orizzonte_giornate": orizzonte_giornate})
    tab.to_csv(fuori / "presenze_per_origine.csv", index=False)
    manifesto.scrivi(fuori)
    (fuori / "diagnostica.json").write_text(json.dumps({
        "semi": a.semi, "feature_usate": colonne, "feature_escluse": escluse,
        "scarto_fra_semi_medio": float(scarto.mean()),
        "presenze_residue_attese_somma": float(media.sum()),
        "calendario": diag_cal}, ensure_ascii=False, indent=2),
        encoding="utf-8")

    print(f"  previsione: somma {media.sum():.1f} presenze residue su "
          f"{len(ids)} giocatori, scarto medio fra semi {scarto.mean():.3f}")
    print(f"  utilizzabile operativamente: "
          f"{manifesto.utilizzabile_operativamente}")
    for stato, nomi in manifesto.ingressi_per_stato().items():
        if stato != org.DISPONIBILE:
            print(f"    {stato}: {nomi}")
    print(f"  scritto in {fuori}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
