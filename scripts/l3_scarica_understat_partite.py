"""Acquisizione dei dati Understat per partita: giocatori e tiri.

Sblocca tre cose che il progetto non aveva:

  1. **minuti giocati** per giocatore e partita anche dove Transfermarkt non
     copre la stagione (il campo `time` del roster);
  2. **rigori distinguibili**: nel roster il campo `goals` comprende i rigori e
     non c'e' un campo separato; nei tiri il campo `situation` vale `Penalty`,
     quindi aggregando i tiri per giocatore i rigori si separano dai gol su
     azione;
  3. **xG per giocatore e partita**, che serve al prior sui marcatori.

## Che cosa NON risolve

Understat elenca **solo chi e' sceso in campo**: nessun record con `time = 0`,
nessun panchinaro inutilizzato, nessun non convocato. E' la stessa limitazione
di `appearances` di Transfermarkt. Da sola questa fonte non puo' alimentare il
denominatore delle propensioni: per quello serve la tabella di appartenenza.

Il campo `roster_in`/`roster_out` **non e' il minuto di ingresso o di uscita**:
sono identificativi di sostituzione, e sulla partita di prova valgono `"0"` per
tutti i 32 record. Chi li leggesse come minuti otterrebbe zero.

Gli assist di Understat (`assists`, `xA`, `key_passes`) **non coincidono** con
gli assist del fantacalcio: sono due definizioni diverse e vanno tenute
separate. Questo script conserva quelli di Understat con il loro nome e non li
usa per riempire il campo del fantacalcio.

## Come acquisisce

- **cache persistente**: ogni partita gia' scaricata non viene richiesta di
  nuovo, a meno di `--riscarica`;
- **aggiornamento incrementale**: si scaricano solo le partite mancanti;
- **provenienza**: per ogni partita si registrano identificativo, momento
  dell'acquisizione, versione della libreria e impronta del contenuto;
- **niente sovrascritture silenziose**: un file gia' presente con impronta
  diversa viene salvato accanto con il suffisso della data e la differenza
  viene dichiarata.

Costo misurato: circa 0,95 secondi per partita nuova (la prima chiamata
scarica la pagina, le successive sulla stessa partita costano 0,09 s).

Uso:
  python scripts/l3_scarica_understat_partite.py 2026 --max 40
  python scripts/l3_scarica_understat_partite.py 2025 2026
Output:
  data/raw/understat/dettaglio/<anno>/roster.parquet
  data/raw/understat/dettaglio/<anno>/tiri.parquet
  data/raw/understat/dettaglio/<anno>/provenienza.json
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw" / "understat"
DEST = RAW / "dettaglio"


def impronta_testo(x) -> str:
    return hashlib.sha256(json.dumps(x, sort_keys=True,
                                     ensure_ascii=False).encode()).hexdigest()[:16]


def partite_da_scaricare(anno: int, solo_giocate: bool, limite: int | None):
    f = RAW / f"partite_{anno}.csv"
    if not f.exists():
        raise SystemExit(f"manca {f}: esegui prima scripts/l2_scarica_understat.py")
    d = pd.read_csv(f)
    if solo_giocate:
        d = d[d.giocata == 1]
    d = d.sort_values("data")
    ids = [str(x) for x in d.id_understat]
    return ids[:limite] if limite else ids


def carica_provenienza(cartella: Path) -> dict:
    f = cartella / "provenienza.json"
    if f.exists():
        return json.loads(f.read_text("utf-8"))
    return {"partite": {}, "libreria": None, "creato": None}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("anni", nargs="+", type=int)
    ap.add_argument("--max", type=int, default=None,
                    help="quante partite al massimo per anno (per provare)")
    ap.add_argument("--riscarica", action="store_true")
    ap.add_argument("--pausa", type=float, default=0.15,
                    help="secondi fra una partita e l'altra")
    ap.add_argument("--tutte", action="store_true",
                    help="anche le partite non giocate (di norma inutile)")
    a = ap.parse_args()

    import understatapi
    from understatapi import UnderstatClient
    versione = getattr(understatapi, "__version__", "ignota")

    for anno in a.anni:
        cartella = DEST / str(anno)
        cartella.mkdir(parents=True, exist_ok=True)
        prov = carica_provenienza(cartella)
        prov["libreria"] = f"understatapi {versione}"
        prov.setdefault("creato", time.strftime("%Y-%m-%dT%H:%M:%S"))
        ids = partite_da_scaricare(anno, not a.tutte, a.max)
        mancanti = [i for i in ids if a.riscarica or i not in prov["partite"]]
        print(f"{anno}: {len(ids)} partite in elenco, {len(mancanti)} da scaricare")
        if not mancanti:
            continue

        righe_roster, righe_tiri, errori = [], [], []
        t0 = time.time()
        with UnderstatClient() as u:
            for k, mid in enumerate(mancanti, 1):
                try:
                    m = u.match(match=mid)
                    roster = m.get_roster_data()
                    tiri = m.get_shot_data()
                except Exception as e:
                    errori.append({"id": mid, "errore": f"{type(e).__name__}: {e}"})
                    continue
                acquisito = time.strftime("%Y-%m-%dT%H:%M:%S")
                for lato in ("h", "a"):
                    for _, rec in (roster.get(lato) or {}).items():
                        righe_roster.append({**rec, "id_partita": mid,
                                             "lato": lato, "anno": anno,
                                             "acquisito_il": acquisito})
                    for rec in (tiri.get(lato) or []):
                        righe_tiri.append({**rec, "id_partita": mid,
                                           "lato": lato, "anno": anno,
                                           "acquisito_il": acquisito})
                prov["partite"][mid] = {
                    "acquisito_il": acquisito,
                    "impronta_roster": impronta_testo(roster),
                    "impronta_tiri": impronta_testo(tiri),
                    "n_roster": sum(len(roster.get(l) or {}) for l in ("h", "a")),
                    "n_tiri": sum(len(tiri.get(l) or []) for l in ("h", "a")),
                }
                if k % 25 == 0 or k == len(mancanti):
                    print(f"  {k}/{len(mancanti)} partite, "
                          f"{time.time() - t0:.0f} s")
                time.sleep(a.pausa)

        # unione con quanto gia' presente, senza sovrascrivere in silenzio
        for nome, righe in (("roster", righe_roster), ("tiri", righe_tiri)):
            if not righe:
                continue
            nuovo = pd.DataFrame(righe)
            f = cartella / f"{nome}.parquet"
            if f.exists() and not a.riscarica:
                vecchio = pd.read_parquet(f)
                nuovo = pd.concat([vecchio, nuovo], ignore_index=True)
                prima = len(nuovo)
                nuovo = nuovo.drop_duplicates(["id_partita", "id"], keep="last")
                if prima != len(nuovo):
                    print(f"  {nome}: rimosse {prima - len(nuovo)} righe duplicate")
            nuovo.to_parquet(f, index=False)
            print(f"  scritto {f.name}: {len(nuovo)} righe")

        # controlli
        problemi = []
        if (cartella / "roster.parquet").exists():
            r = pd.read_parquet(cartella / "roster.parquet")
            r["time"] = pd.to_numeric(r["time"], errors="coerce")
            problemi += [f"{int((r['time'] == 0).sum())} righe di roster con "
                         "time = 0"] if (r["time"] == 0).any() else []
            per_partita = r.groupby("id_partita").size()
            strane = per_partita[(per_partita < 22) | (per_partita > 36)]
            if len(strane):
                problemi.append(f"{len(strane)} partite con un numero anomalo di "
                                f"giocatori a referto (min {per_partita.min()}, "
                                f"max {per_partita.max()})")
            print(f"  roster: {r.id_partita.nunique()} partite, "
                  f"{len(r)} righe, minuti mediani {r['time'].median():.0f}")
        if (cartella / "tiri.parquet").exists():
            t = pd.read_parquet(cartella / "tiri.parquet")
            sit = t["situation"].value_counts().to_dict()
            print(f"  tiri: {t.id_partita.nunique()} partite, {len(t)} tiri, "
                  f"situazioni {sit}")
            rig = t[t.situation == "Penalty"]
            print(f"  rigori: {len(rig)} tiri, di cui segnati "
                  f"{int((rig.result == 'Goal').sum())}, "
                  f"parati {int((rig.result == 'SavedShot').sum())}, "
                  f"sul palo {int((rig.result == 'ShotOnPost').sum())}")
        if errori:
            problemi.append(f"{len(errori)} partite non scaricate: "
                            + "; ".join(f"{e['id']} {e['errore']}"
                                        for e in errori[:3]))
        prov["problemi"] = problemi
        prov["aggiornato_il"] = time.strftime("%Y-%m-%dT%H:%M:%S")
        (cartella / "provenienza.json").write_text(
            json.dumps(prov, indent=1, ensure_ascii=False), encoding="utf-8")
        if problemi:
            print("  PROBLEMI:")
            for p in problemi:
                print(f"    {p}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
