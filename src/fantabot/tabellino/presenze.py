"""Adattatore delle presenze: una sola strada dalla previsione al generatore.

## I tre difetti che chiude

Misurati sul banco prima della correzione.

**Universo troncato.** L'aggiornamento con `pres` scorreva `storia_pres`, che
contiene solo i giocatori con voti precedenti. Chi non aveva storia finiva in
`genera_per_giocatore` con `p_play = 0.5` anche avendo una previsione valida:
**264 giocatori** nel 2024-25 e **219** nel 2025-26. La somma delle probabilità
previste che venivano buttate vale 70,33 e 56,10; il ripiego che le sostituiva
vale 132,0 e 109,5. Sono somme di probabilità in ingresso, non una misura
dell'errore finale.

**Zero scambiato per assente.** Il filtro era `if q and q.get("pres")`, che in
Python è falso anche per `0.0`. Una previsione di zero presenze è
un'informazione — quel giocatore non giocherà — e veniva scartata come dato
mancante: **38 previsioni** nel 2024-25 e **29** nel 2025-26.

**Cold start nel cubo.** `partecipazione.stima` salta il bersaglio quando il
giocatore non è in `prop_conv`. Misurato sul 2026-27: **136 giocatori su 587**
saltati. Il braccio `C1` quindi non risolveva il cold start, lo spostava.

## Che cosa fa

Costruisce, per l'**universo completo della decisione**, un bersaglio di
presenza a voto per giocatore, dichiarando per ciascuno da dove viene:

- `previsione` — il modello valore ha una previsione, zero compreso;
- `prior_ruolo` — nessuna previsione: si usa il tasso del ruolo, calcolato
  sulle sole informazioni ammesse;
- `assente` — il giocatore non è nell'universo.

E tiene separati i due ripieghi che prima erano uno solo: **manca la previsione
delle presenze** è una cosa, **manca lo storico degli eventi** (gol, voti) è
un'altra. L'assenza di storico può richiedere un prior per gli eventi; non
autorizza a buttare via una previsione disponibile delle presenze.

## Che cosa NON fa

Non converte la presenza a voto in convocazione: quella traduzione la fa
`partecipazione.stima`, che conosce la catena. E non promette che il bersaglio
sia raggiunto: l'allocazione è accoppiata fra compagni, undici titolari restano
undici, e lo scarto fra richiesto e ottenuto va **misurato sull'esito del
generatore**, non sul valore appena assegnato.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import pandas as pd

GIORNATE = 38

FONTE_PREVISIONE = "previsione"
FONTE_PRIOR_RUOLO = "prior_ruolo"
FONTE_ASSENTE = "assente"


@dataclass
class Bersagli:
    """I bersagli di presenza a voto, con la provenienza di ciascuno."""

    per_giocatore: dict = field(default_factory=dict)     # pid -> probabilita'
    fonte: dict = field(default_factory=dict)             # pid -> fonte
    orizzonte: dict = field(default_factory=dict)         # pid -> giornate residue
    diagnostica: dict = field(default_factory=dict)

    def __len__(self) -> int:
        return len(self.per_giocatore)

    def solo_previsti(self) -> dict:
        return {p: v for p, v in self.per_giocatore.items()
                if self.fonte.get(p) == FONTE_PREVISIONE}


def _prior_per_ruolo(storia_voti: pd.DataFrame | None,
                     ruolo: dict) -> dict:
    """Tasso di presenza a voto per ruolo, dalle informazioni ammesse.

    Serve ai giocatori senza previsione. Non è un valore inventato: è quello
    che il ruolo faceva nei dati che il fit può vedere. Se non ci sono dati,
    resta `None` e il chiamante decide — non si sostituisce un numero di
    comodo.
    """
    if storia_voti is None or storia_voti.empty:
        return {}
    d = storia_voti.copy()
    d["ruolo"] = d["master_id"].map(ruolo)
    con = d.groupby(["ruolo", "master_id"]).size().rename("righe")
    voti = (d[d.stato_voto == "con_voto"].groupby(["ruolo", "master_id"])
            .size().rename("voti"))
    t = pd.concat([con, voti], axis=1).fillna(0.0)
    t["quota"] = t["voti"] / t["righe"].clip(lower=1)
    return {r: float(g["quota"].mean()) for r, g in t.groupby(level=0)}


def costruisci(percorso_predizioni: Path, universo, ruolo: dict, *,
               storia_voti: pd.DataFrame | None = None,
               giornate_residue: int | dict = GIORNATE,
               presenze_gia_fatte: dict | None = None,
               con_prior: bool = True) -> Bersagli:
    """Bersagli di presenza a voto per l'universo completo.

    Parametri
    ---------
    percorso_predizioni
        `b_predictions_{stagione}.json`. Il campo `pres` è **somma** di
        `pres_gk` (presenze già realizzate nelle prime K giornate) e delle
        presenze previste per il resto. Quindi `pres / 38` è il tasso corretto
        solo per una stagione interamente futura: dopo K turni serve il
        contratto del residuo, e lo si passa con `giornate_residue` e
        `presenze_gia_fatte`.
    universo
        gli identificativi che devono avere un bersaglio, cioè tutti quelli su
        cui il generatore lavorerà. Passare solo chi ha storia era il difetto.
    giornate_residue
        numero di giornate ancora da valutare, o una mappa per giocatore quando
        i rinvii lo rendono diverso fra squadre.
    presenze_gia_fatte
        presenze a voto già realizzate, da sottrarre a `pres` quando si valuta
        il residuo.
    """
    universo = list(universo)
    pr = {}
    if Path(percorso_predizioni).exists():
        crudo = json.loads(Path(percorso_predizioni).read_text("utf-8"))
        for k, v in crudo.items():
            if not isinstance(v, dict):
                continue
            try:
                pr[int(k)] = v
            except (TypeError, ValueError):
                pr[k] = v

    prior = _prior_per_ruolo(storia_voti, ruolo) if con_prior else {}
    prior_medio = (float(np.mean(list(prior.values()))) if prior else None)

    fuori, fonti, orizzonti = {}, {}, {}
    conta = {FONTE_PREVISIONE: 0, FONTE_PRIOR_RUOLO: 0, FONTE_ASSENTE: 0}
    zeri, negativi, oltre_uno, senza_prior = 0, 0, 0, 0

    for pid in universo:
        q = pr.get(pid)
        residue = (giornate_residue.get(pid, GIORNATE)
                   if isinstance(giornate_residue, dict) else giornate_residue)
        residue = max(int(residue), 1)
        orizzonti[pid] = residue
        v = q.get("pres") if isinstance(q, dict) else None
        if v is not None:
            # `pres` comprende le presenze gia' fatte: per il residuo vanno
            # sottratte, e il denominatore sono le giornate ancora da valutare
            fatte = float((presenze_gia_fatte or {}).get(pid, 0.0))
            resto = float(v) - fatte
            if resto < 0:
                negativi += 1
                resto = 0.0
            p = resto / residue
            if float(v) == 0.0:
                # una previsione di zero e' un'informazione, non un dato
                # mancante: il filtro `if q.get("pres")` la scartava
                zeri += 1
            if p > 1.0:
                oltre_uno += 1
                p = 1.0
            fuori[pid] = float(p)
            fonti[pid] = FONTE_PREVISIONE
            conta[FONTE_PREVISIONE] += 1
            continue
        r = ruolo.get(pid)
        base = prior.get(r, prior_medio)
        if base is None:
            senza_prior += 1
            fonti[pid] = FONTE_ASSENTE
            conta[FONTE_ASSENTE] += 1
            continue
        fuori[pid] = float(base)
        fonti[pid] = FONTE_PRIOR_RUOLO
        conta[FONTE_PRIOR_RUOLO] += 1

    diag = {
        "universo": len(universo),
        "con_bersaglio": len(fuori),
        "per_fonte": conta,
        "previsioni_zero_tenute": zeri,
        "residuo_negativo_azzerato": negativi,
        "probabilita_oltre_uno_troncate": oltre_uno,
        "senza_prior_ne_previsione": senza_prior,
        "prior_per_ruolo": {k: round(v, 4) for k, v in prior.items()},
        "giornate_residue": (giornate_residue
                             if not isinstance(giornate_residue, dict)
                             else "per giocatore"),
        "somma_probabilita": round(float(sum(fuori.values())), 4),
        "nota_unita": (
            "`pres` e' la somma delle presenze gia' realizzate e di quelle "
            "previste per il resto della stagione. Diviso per 38 e' coerente "
            "solo con una stagione interamente futura; dopo K turni servono "
            "`presenze_gia_fatte` e `giornate_residue`."),
        "nota_limite": (
            "questi sono bersagli in ingresso. Lo scarto fra bersaglio e "
            "presenza a voto effettivamente prodotta dal generatore non si "
            "misura qui: dipende dai vincoli di undici titolari e dalle "
            "sostituzioni, e va misurato sull'esito."),
    }
    return Bersagli(per_giocatore=fuori, fonte=fonti, orizzonte=orizzonti,
                    diagnostica=diag)


def copertura(bersagli: Bersagli, ruolo: dict, nuovi: set | None = None
              ) -> pd.DataFrame:
    """Tabella della copertura per ruolo e per nuovi contro veterani.

    Il totale delle presenze vicino al vero non basta: gli stessi totali
    possono nascondere giocatori completamente sbagliati. Questa tabella serve
    a guardare dentro il totale.
    """
    righe = []
    nuovi = nuovi or set()
    for pid, fonte in bersagli.fonte.items():
        righe.append({
            "master_id": pid,
            "ruolo": ruolo.get(pid, "?"),
            "fonte": fonte,
            "nuovo": pid in nuovi,
            "bersaglio": bersagli.per_giocatore.get(pid),
        })
    d = pd.DataFrame(righe)
    if d.empty:
        return d
    return (d.groupby(["ruolo", "nuovo", "fonte"])
             .agg(giocatori=("master_id", "size"),
                  bersaglio_medio=("bersaglio", "mean"))
             .reset_index())
