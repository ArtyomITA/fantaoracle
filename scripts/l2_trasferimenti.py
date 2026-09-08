"""Fonte canonica dei trasferimenti per il Livello 2, con copertura annuale.

## Perché esiste

`data/raw/transfermarkt/transfermarkt_transfers.csv` è un **estratto estivo**:
`scripts/tm_process.py` righe 84-86 filtra `transfer_date` agli anni 2020-2025 e
ai mesi 6-9. Il filtro è dichiarato nel docstring di quello script ed è
appropriato per l'uso che aveva. Non lo è per la ricostruzione
dell'appartenenza, che ha bisogno anche dei movimenti di gennaio.

Misurato sul grezzo `_download/transfers.csv.gz`: 175.165 righe, tutte con data
valida, dal 1993-07-01 al 2030-06-30, di cui **34.920 a gennaio** e 9.559 a
febbraio. Nel periodo 2020-2026: 101.504 righe, 28.613 fra gennaio e febbraio.
L'affermazione «la fonte non conosce gennaio», scritta in `PROTOCOLLO_v2.md`
§9.1 sulla base dell'estratto, era sbagliata ed è rettificata in §10.1.

## Che cosa fa

Rilegge il grezzo e scrive una fonte annuale, senza toccare gli altri dataset
che `tm_process.py` produce (rilanciarlo li riscriverebbe tutti). L'estratto
estivo resta dov'è: ha ancora i suoi consumatori e non va cancellato.

Conserva **tutti** i movimenti dei giocatori che ci interessano, compresi
prestiti, rientri, passaggi all'estero e movimenti fuori dalle finestre
ordinarie. Il perimetro non è «trasferimenti fra squadre di Serie A»: un
giocatore che lascia la Serie A esce dalle rose, e quel movimento è
informazione necessaria quanto un arrivo.

## Che cosa NON fa

Non inventa un ordine quando due movimenti dello stesso giocatore cadono lo
stesso giorno: li conserva entrambi e li marca, perché sia chi li consuma a
decidere che farne. Non deduce una data di disponibilità: Transfermarkt
pubblica un trasferimento dopo che è avvenuto, ma non dice quando lo ha
pubblicato, e questo è un limite dichiarato, non un dato.

Uso:
    python scripts/l2_trasferimenti.py --da 2019 --a 2027
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw" / "transfermarkt"
GREZZO = RAW / "_download" / "transfers.csv.gz"
USCITA = RAW / "transfermarkt_transfers_annuale.csv"
DIAGNOSTICA = RAW / "transfermarkt_transfers_annuale.json"

COLONNE = ["player_id", "transfer_date", "transfer_season", "from_club_id",
           "to_club_id", "from_club_name", "to_club_name", "transfer_fee",
           "market_value_in_eur", "player_name"]


def identita_note() -> set[int]:
    """Gli identificativi Transfermarkt che compaiono nelle nostre mappe.

    Stessa logica di `fantabot.tabellino.appartenenza._identita_note`, ripetuta
    qui per non importare il modulo che questo script serve a rifornire.
    """
    ids: set[int] = set()
    proc = ROOT / "data" / "processed"
    for percorso, colonna in [
            (proc / "_match" / "map_tm.csv", "tm_player_id"),
            (proc / "_match" / "map_tm_kader_2026.csv", "tm_player_id"),
            (RAW / "kader_2026.csv", "tm_player_id")]:
        if not percorso.exists():
            continue
        d = pd.read_csv(percorso, usecols=lambda c: c == colonna)
        if colonna in d:
            ids |= set(pd.to_numeric(d[colonna], errors="coerce")
                       .dropna().astype(int))
    return ids


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--da", type=int, default=2019,
                    help="primo anno tenuto (compreso)")
    ap.add_argument("--a", type=int, default=2027,
                    help="ultimo anno tenuto (compreso)")
    ap.add_argument("--tutti-i-giocatori", action="store_true",
                    help="non restringere agli identificativi delle nostre mappe")
    a = ap.parse_args()

    if not GREZZO.exists():
        print(f"BLOCCO: manca {GREZZO}")
        return 1

    g = pd.read_csv(GREZZO, low_memory=False, parse_dates=["transfer_date"])
    n_grezzo = len(g)
    senza_data = int(g["transfer_date"].isna().sum())
    g = g.dropna(subset=["transfer_date"]).copy()

    ids = set() if a.tutti_i_giocatori else identita_note()
    if ids:
        g_ids = g[g["player_id"].isin(ids)].copy()
    else:
        g_ids = g.copy()

    anno = g_ids["transfer_date"].dt.year
    dentro = anno.between(a.da, a.a)
    fuori_anni = g_ids[~dentro]
    d = g_ids[dentro].copy()

    # movimenti dello stesso giocatore nello stesso giorno: non si inventa un
    # ordine. Si contano, si marcano e si lasciano al consumatore.
    conta = d.groupby(["player_id", "transfer_date"]).transform("size")
    d["stesso_giorno"] = conta > 1
    doppi = int(d["stesso_giorno"].sum())

    # duplicati esatti: stessa riga ripetuta, si tiene una copia sola
    prima = len(d)
    d = d.drop_duplicates(subset=["player_id", "transfer_date", "from_club_id",
                                  "to_club_id"])
    duplicati_esatti = prima - len(d)

    d = d.sort_values(["player_id", "transfer_date"]).reset_index(drop=True)
    fuori = d[COLONNE + ["stesso_giorno"]].copy()
    fuori["transfer_date"] = fuori["transfer_date"].dt.date
    fuori.to_csv(USCITA, index=False, encoding="utf-8")

    per_mese = d["transfer_date"].dt.month.value_counts().sort_index()
    per_anno = d["transfer_date"].dt.year.value_counts().sort_index()
    invernali = d[d["transfer_date"].dt.month.isin([1, 2])]

    # copertura: quali mesi del periodo richiesto non hanno nessun movimento?
    attesi = pd.period_range(f"{a.da}-01", f"{a.a}-12", freq="M")
    presenti = set(d["transfer_date"].dt.to_period("M"))
    mancanti = [str(p) for p in attesi if p not in presenti]

    diag = {
        "grezzo": str(GREZZO),
        "grezzo_righe": int(n_grezzo),
        "grezzo_senza_data": senza_data,
        "grezzo_data_min": str(g["transfer_date"].min().date()),
        "grezzo_data_max": str(g["transfer_date"].max().date()),
        "identita_richieste": len(ids) if ids else None,
        "righe_dei_nostri_giocatori": int(len(g_ids)),
        "anni_tenuti": [a.da, a.a],
        "scartate_fuori_anni": int(len(fuori_anni)),
        "righe_uscita": int(len(fuori)),
        "duplicati_esatti_rimossi": duplicati_esatti,
        "movimenti_stesso_giorno": doppi,
        "per_mese": {int(k): int(v) for k, v in per_mese.items()},
        "per_anno": {int(k): int(v) for k, v in per_anno.items()},
        "invernali_gennaio_febbraio": int(len(invernali)),
        "invernali_giocatori": int(invernali["player_id"].nunique()),
        "mesi_senza_movimenti": mancanti,
        "ultimo_movimento": str(d["transfer_date"].max().date()),
        "limite_dichiarato": (
            "il file non porta la data di pubblicazione del trasferimento: "
            "Transfermarkt registra l'evento, non il momento in cui e' "
            "diventato pubblico. Chi usa questa fonte con una data limite "
            "informativa sta assumendo che un trasferimento sia noto dal "
            "giorno in cui avviene, che e' una convenzione conservativa solo "
            "in un verso."),
    }
    DIAGNOSTICA.write_text(json.dumps(diag, indent=1), encoding="utf-8")

    print(f"grezzo: {n_grezzo:,} righe, {senza_data} senza data, "
          f"da {diag['grezzo_data_min']} a {diag['grezzo_data_max']}")
    if ids:
        print(f"nostri giocatori: {len(ids):,} identita, "
              f"{len(g_ids):,} righe")
    print(f"anni {a.da}-{a.a}: {len(fuori):,} righe "
          f"({duplicati_esatti} duplicati esatti rimossi, "
          f"{doppi} movimenti nello stesso giorno marcati)")
    print(f"per mese: {diag['per_mese']}")
    print(f"gennaio-febbraio: {len(invernali):,} righe, "
          f"{invernali['player_id'].nunique():,} giocatori")
    if mancanti:
        print(f"mesi senza nessun movimento: {len(mancanti)} "
              f"({', '.join(mancanti[:6])}{'...' if len(mancanti) > 6 else ''})")
    print(f"scritto {USCITA}")
    print(f"scritto {DIAGNOSTICA}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
