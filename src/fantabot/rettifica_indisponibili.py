"""Rettifica del valore atteso per chi oggi e' indisponibile.

## Il problema

Il pack e' costruito con i dati di una certa data; gli infortuni arrivano
dopo. Il 10 settembre 2026 il piano iniziale del Copilota conteneva Locatelli
(rottura del menisco, rientro a gennaio) a 12 crediti: il modello non poteva
saperlo, il bundle delle fonti si'. Comprare all'asta un giocatore fermo per
meta' stagione a prezzo pieno e' l'errore che questo modulo evita.

## Che cosa fa

Per ogni indisponibile stima le **giornate che perdera'** e riduce il valore
in proporzione: `valore * (giornate_restanti - perse) / giornate_restanti`.
Il valore del pack e' una somma di punti sul resto della stagione, quindi la
proporzione e' la correzione naturale, non un parametro scelto a mano.

La stima delle giornate perse viene, in ordine:

1. da una data di rientro (`rientro_stima` in forma `AAAA-MM-GG` o `AAAA-MM`),
   contando le giornate del calendario che iniziano prima di quella data;
2. da una giornata (`G5` = torna disponibile per la quinta): le giornate fra
   la prossima e quella;
3. dal testo, quando la stima manca o e' marcata inaffidabile: mesi citati
   («gennaio», «dicembre», ...) o parole che indicano uno stop lungo
   («crociato», «lungo stop», «girone d'andata»); se non c'e' niente di
   tutto questo, una giornata sola — «da valutare» vuol dire quasi sempre
   il turno successivo.

Le squalifiche contano una giornata (o quelle indicate dal testo).

## Che cosa NON fa

Non tocca i prezzi (q10/q50/q90): il mercato puo' sgonfiare un infortunato
piu' o meno di cosi', e quello resta un dato del tavolo. Non toglie nessuno
dal pool: il giocatore resta comprabile e consigliabile secondo il valore
rettificato. Ogni rettifica e' dichiarata con il motivo e la stima usata.
"""
from __future__ import annotations

import datetime as dt
import re
from pathlib import Path

MESI = {"gennaio": 1, "febbraio": 2, "marzo": 3, "aprile": 4, "maggio": 5,
        "giugno": 6, "luglio": 7, "agosto": 8, "settembre": 9, "ottobre": 10,
        "novembre": 11, "dicembre": 12}
# parole che, senza una data, indicano uno stop di mesi
STOP_LUNGO = ("crociato", "lungo stop", "girone d'andata", "buona parte",
              "tibia", "perone", "achille", "operato", "operazione",
              "intervento")
GIORNATE_STOP_LUNGO = 12


def carica_calendario(percorso: Path) -> dict[int, dt.date]:
    """giornata -> data della prima partita di quella giornata."""
    import csv
    prima: dict[int, dt.date] = {}
    with open(percorso, newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            try:
                g = int(r["giornata"])
                d = dt.date.fromisoformat(str(r["data"])[:10])
            except (KeyError, ValueError, TypeError):
                continue
            if g not in prima or d < prima[g]:
                prima[g] = d
    return prima


def prossima_giornata(calendario: dict[int, dt.date], oggi: dt.date) -> int:
    future = [g for g, d in calendario.items() if d >= oggi]
    return min(future) if future else max(calendario) + 1


def _data_da_stima(stima: str) -> dt.date | None:
    s = str(stima).strip()
    m = re.fullmatch(r"(\d{4})-(\d{2})-(\d{2})", s)
    if m:
        return dt.date(int(m[1]), int(m[2]), int(m[3]))
    m = re.fullmatch(r"(\d{4})-(\d{2})", s)
    if m:
        return dt.date(int(m[1]), int(m[2]), 1)
    return None


def _data_dal_testo(testo: str, oggi: dt.date) -> dt.date | None:
    t = testo.lower()
    trovate = []
    for nome, mese in MESI.items():
        if re.search(rf"\b{nome}\b", t):
            anno = oggi.year if mese >= oggi.month else oggi.year + 1
            trovate.append(dt.date(anno, mese, 1))
    # «fine ottobre», «seconda meta' di settembre»: si sposta in avanti
    if not trovate:
        return None
    d = max(trovate)
    if re.search(r"fine|seconda met", t):
        d = d + dt.timedelta(days=20)
    elif re.search(r"met[aà]\b", t):
        d = d + dt.timedelta(days=14)
    return d


def giornate_perse(voce: dict, calendario: dict[int, dt.date], oggi: dt.date,
                   ultima_giornata: int = 38) -> tuple[int, str]:
    """Quante giornate, a partire dalla prossima, il giocatore salta.

    Ritorna (giornate, come_stimato)."""
    prossima = prossima_giornata(calendario, oggi)
    restanti = ultima_giornata - prossima + 1
    stima = voce.get("rientro_stima")
    sospetta = bool(voce.get("stima_sospetta"))
    testo = str(voce.get("testo") or "")

    def da_data(d: dt.date) -> int:
        perse = sum(1 for g, data in calendario.items()
                    if g >= prossima and data < d)
        return max(0, min(restanti, perse))

    if stima and not sospetta:
        d = _data_da_stima(stima)
        if d is not None:
            return da_data(d), f"rientro {stima}"
        m = re.fullmatch(r"G(\d+)", str(stima).strip())
        if m:
            g = int(m[1])
            if g > prossima:
                return min(restanti, g - prossima), f"rientro alla {stima}"
    if str(voce.get("tipo", "")).startswith("squal"):
        m = re.search(r"(\d+)\s*giornat", testo.lower())
        return (min(restanti, int(m[1])) if m else 1), "squalifica"
    d = _data_dal_testo(testo, oggi)
    if d is not None:
        return da_data(d), f"dal testo: rientro {d.isoformat()}"
    if any(p in testo.lower() for p in STOP_LUNGO):
        return min(restanti, GIORNATE_STOP_LUNGO), "dal testo: stop lungo"
    return 1, "dal testo: prossimo turno"


def rettifica_valori(pred: dict, indisponibili: dict, calendario: dict[int, dt.date],
                     oggi: dt.date, ultima_giornata: int = 38) -> tuple[dict, dict]:
    """Copia delle predizioni con `value` e `value_up` ridotti per gli
    indisponibili. Ritorna (predizioni, rettifiche) dove `rettifiche` dice per
    ogni giocatore quante giornate, come stimate, e il fattore applicato."""
    prossima = prossima_giornata(calendario, oggi)
    restanti = max(1, ultima_giornata - prossima + 1)
    nuove = {pid: dict(v) for pid, v in pred.items()}
    rettifiche = {}
    for pid, voce in (indisponibili or {}).items():
        if pid not in nuove:
            continue
        perse, come = giornate_perse(voce, calendario, oggi, ultima_giornata)
        if perse <= 0:
            continue
        fattore = (restanti - perse) / restanti
        v = nuove[pid]
        originale = float(v.get("value", 0.0) or 0.0)
        for campo in ("value", "value_up", "value_modello", "value_q10",
                      "value_q25", "value_q75", "value_q90"):
            if v.get(campo) is not None:
                v[campo] = float(v[campo]) * fattore
        v["value_originale"] = originale
        v["rettifica"] = {"giornate_perse": perse, "su": restanti,
                          "fattore": round(fattore, 3), "stima": come,
                          "tipo": voce.get("tipo")}
        rettifiche[pid] = v["rettifica"]
    return nuove, rettifiche
