"""Adattatore dal bersaglio per origine (Livello 1) al bersaglio del cubo.

## Perche' esiste

`scripts/l1_presenze_per_origine.py` scrive un CSV con le colonne
`master_id`, `presenze_residue_attese`, `scarto_fra_semi`,
`presenze_gia_fatte`, `orizzonte_giornate`: e' una previsione del **resto** di
stagione, fatta con le sole feature disponibili alla data di origine.

`fantabot.tabellino.presenze.costruisci` vuole invece un JSON
`id -> {"pres": ...}` dove `pres` e' la **somma** delle presenze gia' fatte e
di quelle previste, piu' `giornate_residue` e `presenze_gia_fatte` passati a
parte. Sono due unita' di misura diverse, e il punto in cui in passato si e'
sbagliata l'unita' e' esattamente questo: la docstring di `presenze.costruisci`
lo dichiara alle righe 108-115.

Qui la conversione sta in un posto solo, dichiarata e provata.

## Che cosa fa

`presenze / orizzonte` e' la probabilita' per giornata che `presenze.costruisci`
ricostruisce da sola: questo modulo non la calcola, si limita a fornire i tre
ingressi coerenti fra loro:

- `pres` = `presenze_gia_fatte + presenze_residue_attese`;
- `giornate_residue` = `orizzonte_giornate`, per giocatore;
- `presenze_gia_fatte` = `presenze_gia_fatte`, per giocatore.

## Che cosa NON fa

Non inventa un bersaglio per chi non e' nel CSV: quel giocatore non compare nel
JSON, e `presenze.costruisci` lo manda al prior di ruolo, che e' un ripiego
dichiarato e non uno zero silenzioso.
"""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from . import presenze

COLONNE_RICHIESTE = ("master_id", "presenze_residue_attese",
                     "presenze_gia_fatte", "orizzonte_giornate")


def carica(percorso_csv: Path) -> pd.DataFrame:
    """Legge il CSV per origine e rifiuta ogni scostamento dal contratto.

    Un CSV con una colonna mancante non e' un caso da rattoppare con un valore
    di riserva: sarebbe un'unita' di misura assunta invece che letta.
    """
    percorso_csv = Path(percorso_csv)
    if not percorso_csv.exists():
        raise FileNotFoundError(f"bersaglio per origine assente: {percorso_csv}")
    d = pd.read_csv(percorso_csv)
    mancanti = [c for c in COLONNE_RICHIESTE if c not in d.columns]
    if mancanti:
        raise ValueError(
            f"{percorso_csv}: colonne mancanti {mancanti}. Attese "
            f"{list(COLONNE_RICHIESTE)}, trovate {list(d.columns)}")
    if d.empty:
        raise ValueError(f"{percorso_csv}: nessuna riga")
    if (d["orizzonte_giornate"].astype(float) <= 0).any():
        raise ValueError(
            f"{percorso_csv}: orizzonte_giornate deve essere positivo, "
            "un orizzonte nullo renderebbe la probabilita' non definita")
    d = d.copy()
    d["master_id"] = d["master_id"].astype(int)
    if d["master_id"].duplicated().any():
        doppi = sorted(d.loc[d["master_id"].duplicated(), "master_id"])[:5]
        raise ValueError(f"{percorso_csv}: identificativi ripetuti, es. {doppi}")
    return d


def adatta(percorso_csv: Path, destinazione_json: Path | None = None) -> dict:
    """Converte il CSV nel formato che `presenze.costruisci` accetta.

    Restituisce un dizionario con le tre chiavi che servono al chiamante:
    `predizioni` (`id -> {"pres": somma}`), `giornate_residue`,
    `presenze_gia_fatte`, piu' `diagnostica`. Se `destinazione_json` e' dato,
    ci scrive `predizioni`, cosi' che il percorso possa essere passato a
    `presenze.costruisci`, che vuole un file.
    """
    d = carica(percorso_csv)
    predizioni, residue, fatte = {}, {}, {}
    for r in d.itertuples(index=False):
        pid = int(r.master_id)
        gia = float(r.presenze_gia_fatte)
        resto = float(r.presenze_residue_attese)
        predizioni[pid] = {"pres": gia + resto}
        residue[pid] = int(r.orizzonte_giornate)
        fatte[pid] = gia
    diag = {
        "sorgente": str(Path(percorso_csv)),
        "giocatori": len(predizioni),
        "somma_presenze_residue_attese": round(
            float(d["presenze_residue_attese"].sum()), 6),
        "somma_presenze_gia_fatte": round(
            float(d["presenze_gia_fatte"].sum()), 6),
        "somma_pres_dichiarata": round(
            float(sum(v["pres"] for v in predizioni.values())), 6),
        "orizzonti_distinti": sorted({int(x) for x in residue.values()}),
        "nota_unita": (
            "`pres` e' somma di presenze gia' fatte e residue attese, come "
            "vuole `presenze.costruisci`; `giornate_residue` e' l'orizzonte "
            "del CSV, quindi la probabilita' ricostruita e' "
            "presenze_residue_attese / orizzonte_giornate."),
    }
    if destinazione_json is not None:
        destinazione_json = Path(destinazione_json)
        destinazione_json.parent.mkdir(parents=True, exist_ok=True)
        destinazione_json.write_text(
            json.dumps({str(k): v for k, v in predizioni.items()},
                       ensure_ascii=False),
            encoding="utf-8")
        diag["destinazione"] = str(destinazione_json)
    return {"predizioni": predizioni, "giornate_residue": residue,
            "presenze_gia_fatte": fatte, "diagnostica": diag}


def costruisci_da_origine(percorso_csv: Path, universo, ruolo: dict, *,
                          storia_voti: pd.DataFrame | None = None,
                          con_prior: bool = True,
                          cartella_lavoro: Path | None = None
                          ) -> presenze.Bersagli:
    """`presenze.costruisci` alimentata dal bersaglio per origine.

    L'unica strada: chi vuole il bersaglio onesto passa di qui, e ottiene un
    `Bersagli` identico per tipo a quello costruito da `b_predictions`, con la
    diagnostica dell'adattatore aggiunta sotto `bersaglio_origine`.
    """
    convertito = adatta(percorso_csv, None)
    cartella = Path(cartella_lavoro) if cartella_lavoro is not None else None
    if cartella is None:
        import tempfile
        cartella = Path(tempfile.mkdtemp(prefix="bersaglio_origine_"))
    cartella.mkdir(parents=True, exist_ok=True)
    percorso_json = cartella / "bersaglio_origine.json"
    percorso_json.write_text(
        json.dumps({str(k): v for k, v in convertito["predizioni"].items()},
                   ensure_ascii=False), encoding="utf-8")
    b = presenze.costruisci(
        percorso_json, universo, ruolo, storia_voti=storia_voti,
        giornate_residue=convertito["giornate_residue"],
        presenze_gia_fatte=convertito["presenze_gia_fatte"],
        con_prior=con_prior)
    b.diagnostica = dict(b.diagnostica)
    b.diagnostica["bersaglio_origine"] = convertito["diagnostica"]
    return b
