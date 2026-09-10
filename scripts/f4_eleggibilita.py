"""Chi si puo' davvero comprare stasera: il filtro di eleggibilita' del pool.

## Il difetto che questo file chiude

Il vecchio scraper del listone perdeva il marcatore `.out-of-game`. Risultato:
i 63 giocatori che la fonte dichiara «Non gioca piu' in Serie A» sono tutti
dentro i 587 del pack operativo, e possono comparire fra i consigli e nel
piano. Comprarne uno all'asta e' un errore che non si annulla.

## Che cosa fa, e che cosa NON fa

Costruisce un file di eleggibilita' a partire dal bundle di fonti verificate.
**Non tocca il pack, non cancella niente dallo storico, non modifica i ledger
esistenti**: le aste gia' giocate restano leggibili con i loro identificativi.
Il filtro vale per il pool della nuova asta.

Distingue tre condizioni che non vanno confuse:

- **fuori Serie A**: la fonte dice che il giocatore non gioca piu' nel
  campionato. Non e' un infortunio, ed e' definitivo per questa stagione;
- **indisponibile**: infortunio o squalifica noti oggi. E' uno stato che
  cambia, e un giocatore indisponibile resta comprabile — puo' rientrare, e
  in certe leghe conserva valore di svincolo;
- **assente dal pack**: il modello non ha una previsione per lui. Non e' un
  divieto: e' un limite di copertura, e va detto invece di nasconderlo.

Uso:
    python scripts/f4_eleggibilita.py --bundle <cartella> [--prova]
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import pickle
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
PACKS = ROOT / "data" / "packs"
FUORI = ROOT / "data" / "copilot"
BUNDLE_PREDEFINITO = Path(
    r"C:\Users\Administrator\Documents\Codex\2026-09-06"
    r"\computer-plugin-computer-use-openai-bundled\fonti_preasta\20260909T223517Z")


def leggi(percorso: Path) -> list[dict]:
    with open(percorso, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def impronta(percorso: Path) -> str:
    return hashlib.sha256(percorso.read_bytes()).hexdigest()


def vero(x) -> bool:
    return str(x).strip().lower() in ("true", "1", "si", "sì", "yes")


def costruisci(bundle: Path, stagione: str = "2026-27") -> dict:
    parsed = bundle / "parsed"
    completo = leggi(parsed / f"listone_{stagione}_completo.csv")
    attivi = leggi(parsed / f"listone_{stagione}_attivi.csv")
    indisp = leggi(parsed / "indisponibili.csv")
    identita = leggi(parsed / "prezzi_identita.csv")

    id_completo = {r["player_id"] for r in completo}
    id_attivi = {r["player_id"] for r in attivi}
    fuori_serie_a = {r["player_id"]: (r.get("fuori_serie_a_nota") or "").strip()
                     for r in completo if vero(r.get("fuori_serie_a"))}

    # coerenza interna del bundle, prima di fidarsene
    incoerenti = sorted(set(fuori_serie_a) & id_attivi)
    mancanti = sorted(id_completo - id_attivi - set(fuori_serie_a))

    pack_file = PACKS / f"pack_{stagione}.pkl"
    with open(pack_file, "rb") as f:
        pack = pickle.load(f)
    id_pack = set(pack.players)

    # Indisponibili: stato sportivo, separato dall'eleggibilita'.
    #
    # `rientro_stima` NON e' una data di rientro. Il parser la deduce dal testo,
    # e sbaglia in modo dimostrato: per Zaniolo (2766) il testo dice «nella 1a
    # giornata contro il Como e' uscito dal campo... Stop di circa 25 giorni,
    # recuperabile dalla fine di settembre», e la stima risulta `G1` — la
    # giornata dell'INFORTUNIO letta come giornata di rientro.
    #
    # Qui si conserva il testo intero della fonte e si marca la stima come
    # sospetta quando cita una giornata gia' giocata. Un rientro dedotto non
    # diventa una scadenza.
    GIORNATA_CORRENTE = 4      # le probabili del bundle sono della 4a
    indisponibili = {}
    for r in indisp:
        pid = (r.get("player_id") or "").strip()
        if not pid:
            continue
        stima = (r.get("rientro_stima") or "").strip() or None
        testo = (r.get("dettaglio") or "").strip()
        sospetta = None
        if stima and stima.upper().startswith("G"):
            try:
                g = int(stima[1:])
                if g <= GIORNATA_CORRENTE:
                    sospetta = (f"la stima dice {stima}, cioe' una giornata "
                                f"gia' giocata: quasi certamente il parser ha "
                                f"letto la giornata dell'evento, non quella "
                                f"del rientro")
            except ValueError:
                sospetta = f"formato non riconosciuto: {stima}"
        indisponibili[pid] = {
            "tipo": (r.get("tipo") or "").strip(),
            "testo": testo,
            "rientro_atteso_fonte": (r.get("rientro_atteso") or "").strip(),
            "rientro_stima": stima,
            "rientro_e_euristica": True,
            "stima_sospetta": sospetta,
        }

    prezzi = {}
    for r in identita:
        pid = (r.get("player_id") or "").strip()
        valore = (r.get("p500_10sq") or "").strip()
        if pid and valore:
            try:
                prezzi[pid] = float(valore)
            except ValueError:
                pass

    per_ruolo = {}
    for r in attivi:
        per_ruolo[r["ruolo_classic"]] = per_ruolo.get(r["ruolo_classic"], 0) + 1

    acquistabili = sorted(id_attivi & id_pack)
    return {
        "stagione": stagione,
        "bundle": str(bundle),
        "bundle_acquisito": (completo[0].get("acquired_at_utc") if completo
                             else None),
        "costruito_il": datetime.now().isoformat(timespec="seconds"),
        "impronte_fonti": {
            f.name: impronta(f) for f in sorted(parsed.glob("*.csv"))},
        "pack": {"file": pack_file.name, "impronta": impronta(pack_file),
                 "giocatori": len(id_pack)},
        "conteggi": {
            "listone_completo": len(id_completo),
            "listone_attivi": len(id_attivi),
            "fuori_serie_a": len(fuori_serie_a),
            "attivi_nel_pack": len(acquistabili),
            "attivi_non_nel_pack": len(id_attivi - id_pack),
            "fuori_serie_a_nel_pack": len(set(fuori_serie_a) & id_pack),
            "nel_pack_ma_non_nel_listone": len(id_pack - id_completo),
            "attivi_per_ruolo": per_ruolo,
            "indisponibili": len(indisponibili),
            "indisponibili_acquistabili": len(set(indisponibili) & set(acquistabili)),
            "con_prezzo_di_mercato": len(set(prezzi) & set(acquistabili)),
        },
        "coerenza_bundle": {
            "marcati_fuori_ma_anche_attivi": incoerenti,
            "nel_completo_ma_ne_attivi_ne_fuori": mancanti,
        },
        "acquistabili": acquistabili,
        "esclusi_fuori_serie_a": sorted(fuori_serie_a),
        "note_fuori_serie_a": fuori_serie_a,
        "attivi_senza_previsione": sorted(id_attivi - id_pack),
        # chi e' nel listone ma non nel pack: il Copilota deve poterlo
        # registrare al martelletto (un avversario puo' comprarlo), quindi
        # servono nome, ruolo e squadra, non solo l'identificativo
        "attivi_senza_previsione_dettagli": [
            {"id": r["player_id"], "nome": r.get("nome", ""),
             "ruolo": r.get("ruolo_classic", ""), "squadra": r.get("squadra", ""),
             "quotazione": r.get("qt_a_classic")}
            for r in attivi if r["player_id"] in (id_attivi - id_pack)],
        "indisponibili": indisponibili,
        "prezzo_mercato_10sq_500": prezzi,
        "semantica_prezzo": (
            "colonna «10 sq. / 500» del fornitore: AGGREGA leghe da 9-11 "
            "squadre e 440-560 crediti, con almeno tre aste per cella. Non e' "
            "un campione di sole leghe da 10 e 500, non e' un prezzo "
            "garantito e non e' un tetto conveniente. E' un riferimento di "
            "mercato, separato dalla previsione del modello."),
        "conteggio_stime_sospette": sum(
            1 for x in indisponibili.values() if x["stima_sospetta"]),
        "nota_indisponibili": (
            "stato sportivo, non eleggibilita': un indisponibile resta "
            "acquistabile. `rientro_stima` e' un'euristica del parser, non un "
            "comunicato medico: senza data dell'evento nella fonte, ricalcolarla "
            "a ogni lettura sposterebbe il rientro in avanti da sola."),
        "nota_perimetro": (
            "questo filtro vale per il pool della NUOVA asta. Non cancella "
            "nessun identificativo dallo storico, dai ledger o dai pack: le "
            "aste gia' giocate restano leggibili come sono."),
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--bundle", default=str(BUNDLE_PREDEFINITO))
    ap.add_argument("--stagione", default="2026-27")
    ap.add_argument("--prova", action="store_true")
    a = ap.parse_args()

    bundle = Path(a.bundle)
    if not (bundle / "parsed").exists():
        print(f"bundle senza cartella parsed: {bundle}")
        return 2
    d = costruisci(bundle, a.stagione)
    c = d["conteggi"]
    print(f"bundle {bundle.name}, acquisito {d['bundle_acquisito']}")
    print(f"  listone: {c['listone_completo']} totali, {c['listone_attivi']} "
          f"attivi, {c['fuori_serie_a']} fuori Serie A")
    print(f"  fuori Serie A che sono nel pack: {c['fuori_serie_a_nel_pack']} "
          "(sarebbero consigliabili senza questo filtro)")
    print(f"  pool acquistabile: {c['attivi_nel_pack']} "
          f"({c['attivi_per_ruolo']})")
    print(f"  attivi senza previsione nel pack: {c['attivi_non_nel_pack']} "
          f"-> {d['attivi_senza_previsione'][:8]}")
    print(f"  nel pack ma fuori dal listone: {c['nel_pack_ma_non_nel_listone']}")
    print(f"  indisponibili oggi: {c['indisponibili']}, di cui "
          f"{c['indisponibili_acquistabili']} nel pool (restano comprabili)")
    print(f"  con prezzo di mercato: {c['con_prezzo_di_mercato']} su "
          f"{c['attivi_nel_pack']}")
    for k, v in d["coerenza_bundle"].items():
        if v:
            print(f"  ATTENZIONE {k}: {len(v)} -> {v[:5]}")

    if a.prova:
        print("  prova: niente scritto")
        return 0
    FUORI.mkdir(parents=True, exist_ok=True)
    dest = FUORI / f"eleggibilita_{a.stagione}.json"
    tmp = dest.with_suffix(f".tmp{os.getpid()}")
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(json.dumps(d, ensure_ascii=False, indent=1))
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, dest)
    print(f"  scritto {dest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
