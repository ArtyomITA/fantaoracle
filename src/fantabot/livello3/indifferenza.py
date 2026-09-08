"""Prezzo di indifferenza: fino a quanto conviene salire su un giocatore.

## La domanda, scritta per intero

Per il giocatore `i`, lo stato d'asta `S` e un prezzo intero `p`:

    Delta(i, p, S) = P1(lo compro a p e poi completo l'asta)
                   - P1(lo lascio andare e poi completo l'asta)

Il prezzo di indifferenza e' il piu' alto `p` per cui `Delta` e' ancora
positivo. Non e' il q90 del modello prezzo, non e' il q90 piu' una
dispersione, e non e' una conversione di punti in crediti: e' la differenza
fra due mondi completi.

## Che cosa deve contenere ciascun ramo

Tutti e due i rami arrivano a **rose complete e legali per tutte le squadre**:

  - il nostro budget aggiornato, i posti e i ruoli che restano;
  - i giocatori ancora sul mercato, e le alternative che potremmo comprare al
    posto suo;
  - nel ramo "passo", il giocatore lo compra qualcun altro (o resta invenduto),
    quindi non e' piu' disponibile per nessuno;
  - le decisioni d'asta successive, nostre e altrui;
  - il completamento legale: quote per ruolo, budget, un credito di riserva per
    ogni posto ancora vuoto.

## Il completamento e' un SURROGATO, e va letto per quello che e'

Il completamento implementato qui **non e' un'asta competitiva**: e' una
procedura di assegnazione per priorita', una rosa intera alla volta, con
prezzo esogeno pari al prezzo previsto. Non esiste il lotto, non esiste il
rilancio, non esiste il martelletto, e nessuno paga un credito piu' del
previsto. L'audit dell'8 settembre 2026
(`data/l3/audit2/livello3/RAPPORTO.md`, sezione 2) ha misurato lo scarto dal
motore d'asta vero: la squadra servita per prima ottiene il valore piu' alto
in 15 mondi su 20; il surrogato satura il budget (60,0 su 60) mentre il
motore spende in media 42,1 su 60; la dispersione dei valori fra squadre e'
114,5 contro 190,2 — il surrogato livella, l'asta vera separa.

Per questo il nome canonico delle funzioni e' `*_surrogata`, e ogni risultato
esposto porta il blocco `completamento` con il tipo, i conteggi e lo scarto
dichiarato. `completa_rosa` e `completa_asta` restano come alias compatibili.
Il gancio per sostituirlo con il motore d'asta vero e' il parametro
`completatore` di `delta_a_prezzo` e `curva`: sostituirlo e' un lavoro a se',
non una variante di questo modulo.

## Contabilita': il ledger d'asta e' la verita'

Regole non negoziabili, fissate da `tests/test_l3_contabilita.py`:

  - **un acquisto concluso e' immutabile.** Chi e' gia' stato battuto resta
    della squadra che lo ha preso, nostra o avversaria che sia. In asta non
    esiste la rivendita, quindi il completamento non puo' inventarne una;
  - **il budget parte dal ledger reale.** `nostro_budget` e i budget degli
    avversari sono i residui veri, non un ricalcolo a prezzi di listino;
  - **nessun rimborso implicito, mai.** Le uniche restituzioni ammesse sono
    quelle degli acquisti **soltanto pianificati** dentro la stessa
    simulazione, e valgono esattamente il prezzo addebitato in quella
    simulazione: la somma di speso e residuo resta invariante;
  - **nel ramo "compro" il bersaglio resta nostro fino alla fine**, perche' e'
    un acquisto concluso come gli altri.

La distinzione fra le due categorie e' esplicita anche nei nomi: `conclusi`
sono gli acquisti del ledger, `pagati` (e `presi`) sono i candidati
pianificati dal completamento della simulazione corrente. Scambiare fra
candidati provvisori e' lecito ed e' cio' che rende il confronto informativo;
scambiare fra acquisti conclusi non lo e'.

## Esiti, non eccezioni

Un reparto che non si riempie e una squadra senza crediti sono **esiti**:
finiscono in `insoluti` e nel blocco `completamento` del risultato. Prima
sollevavano `ValueError` e un solo giocatore non completabile interrompeva
l'intero giro dei tetti invece di essere marcato come non valutabile.

## Sulla monotonia

`Delta` non e' garantito monotono nel prezzo: crediti e acquisti sono discreti,
e spendere un credito in piu' puo' far saltare un'alternativa piu' avanti. Per
questo il modulo **non fa ricerca binaria**: valuta tutti i prezzi interi della
griglia richiesta e restituisce la curva intera. Se la curva cambia segno piu'
di una volta, lo dichiara.

## Che cosa restituisce

Per ogni prezzo: la differenza media, il suo intervallo, e l'esito che quel
solo intervallo sostiene. Alla fine: prezzo di mercato previsto, massimo
legale, il blocco `classificazione`, le alternative sacrificate e uno stato
complessivo fra `verificato`, `approssimato` e `inconcludente`. Quando il
confronto e' incerto, il modulo lo dice invece di dare una cifra precisa che
non ha.

Due numeri diversi, con due nomi diversi, perche' rispondono a due domande
diverse:

  - `stima_tetto` e' il piu' alto prezzo con differenza media positiva. E' una
    stima puntuale scelta come massimo su k prezzi provati, quindi distorta
    verso l'alto: l'audit ha misurato su Zaccagni un passaggio da +0,1250 con
    4 repliche a +0,0234 con 32 sullo stesso punto, un fattore 5,3;
  - `tetto_economico` e' il piu' alto prezzo il cui intervallo sta interamente
    sopra lo zero. Vale per quel prezzo e per nessun altro; se non esiste vale
    0 e lo stato e' `inconcludente`.

La classificazione tiene separati cinque esiti: la stima puntuale, i prezzi
con vantaggio supportato, quelli con svantaggio supportato, la regione
inconcludente (intervallo che contiene lo zero) e l'intervallo per il punto di
indifferenza — o, quando i dati non lo delimitano, il motivo per cui non e'
calcolabile.

**Nessun punto certifica il suo vicino.** Prima della revisione dell'8
settembre 2026 lo stato del confronto guardava i punti a distanza <= 1 crediti
dal tetto stimato: con delta +0,01 e intervallo [-0,10; +0,10] a prezzo 2 e
delta -0,01 con [-0,02; -0,005] a prezzo 3, il risultato era
`tetto_economico = 2` con stato `verificato`. Il fatto negativo su 3 riguarda
il prezzo 3 e non risolve l'incertezza sul prezzo 2. Ora ogni prezzo porta il
proprio esito, in tutte e due le direzioni.

**Selezione su piu' prezzi.** Il tetto e' il massimo su k confronti, e un
intervallo al 95 % per singolo confronto non copre quella scelta. Quando i
confronti portano i delta per replica, gli intervalli della classificazione
sono ricalcolati con livello per confronto `0,05 / k`: piu' severo del 95 %,
mai meno. La soglia di famiglia resta 0,05 e non si tocca. Quando i delta per
replica mancano, il ricalcolo non e' possibile e il risultato lo dichiara.

In piu', ogni curva porta la sua **chiave di validita'**: un tetto e' una
funzione dello stato d'asta da cui e' stato calcolato, e non vale piu' quando
quello stato cambia. La chiave comprende lo stato decisionale (budget, rosa,
posti liberi, mercato residuo, rose e budget avversari), l'impronta del cubo e
le costanti dell'esperimento (scenari, repliche, seme, calendario, regole,
prezzi e valori). Chi consuma un tetto confronta la chiave con lo stato in cui
si trova e si accorge che e' scaduto. La misura del costo del congelamento e'
dell'audit: per Malen il tetto passa da 110 (`inconcludente`) allo stato
iniziale a 220 (`verificato`) a meta' asta, sullo stesso file.
"""
from __future__ import annotations

import hashlib
import json
import zlib
from dataclasses import dataclass, field

import numpy as np

from .valutatore import Regole, valuta
from .valutatore import punteggi_rosa as _punteggi_rosa


# --------------------------------------------------------------------------
# che cosa e' il completamento, dichiarato una volta sola e riportato ovunque
# --------------------------------------------------------------------------

# Numeri dell'audit indipendente dell'8 settembre 2026, non rimisurati qui:
# servono a chi legge un tetto per sapere di quanto il banco su cui e' stato
# calcolato si discosta dal motore d'asta vero.
SCARTO_DAL_MOTORE = {
    "fonte": ("data/l3/audit2/livello3/RAPPORTO.md, sezione 2 "
              "(audit indipendente dell'8 settembre 2026); numeri riportati, "
              "non rimisurati da questo modulo"),
    "vantaggio_del_primo_servito": "valore piu' alto in 15 mondi su 20",
    "lotti_a_un_credito": {
        "motore_asta_2026_27": 0.236,
        "surrogato_listino_vero": 0.0,
    },
    "prezzo_pagato_su_prezzo_previsto": {
        "motore_media": 0.818, "motore_mediana": 1.0, "surrogato": 1.0,
    },
    "spesa_per_squadra_caso_piccolo_budget_60": {
        "motore_media": 42.1, "motore_min": 13, "motore_max": 60,
        "surrogato_media": 60.0,
    },
    "dispersione_dei_valori_fra_squadre_caso_piccolo": {
        "motore": 190.2, "surrogato": 114.5,
    },
}

COMPLETAMENTO_SURROGATO = {
    "nome": "completamento surrogato per priorita'",
    "tipo": "assegnazione_per_priorita",
    "asta_competitiva": False,
    "prezzo": "esogeno: si paga il prezzo previsto, mai uno di piu'",
    "granularita": "una rosa intera alla volta, in ordine estratto dalla replica",
    "scarto_dal_motore": SCARTO_DAL_MOTORE,
}

CRITERI_AVVERSARI = ("valore_su_prezzo", "prezzo", "valore")


# --------------------------------------------------------------------------
# stato dell'asta
# --------------------------------------------------------------------------

@dataclass
class StatoAsta:
    """Fotografia dell'asta in un istante, con tutto quello che serve a
    completarla da li' in avanti.

    `nostra` e le rose in `avversari` sono il **ledger degli acquisti
    conclusi**: sono immutabili per chiunque simuli il seguito. I budget sono
    i residui veri di quel ledger."""
    nostra: dict                  # ruolo -> [master_id] gia' comprati
    nostro_budget: float
    avversari: dict               # nome -> {"rosa": {...}, "budget": float}
    disponibili: set              # master_id ancora sul mercato
    regole: Regole

    def posti_liberi(self, rosa: dict) -> dict:
        return {r: self.regole.quote[r] - len(rosa.get(r, []))
                for r in self.regole.quote}

    def max_legale(self, rosa: dict, budget: float) -> int:
        """Massimo offribile lasciando un credito per ogni altro posto vuoto."""
        vuoti = sum(self.posti_liberi(rosa).values())
        return int(max(0, budget - max(0, vuoti - 1)))

    def rose(self) -> dict:
        """Ledger completo: nome squadra -> rosa degli acquisti conclusi."""
        out = {"NOI": self.nostra}
        for nome, dati in self.avversari.items():
            out[nome] = dati["rosa"]
        return out

    def budget(self) -> dict:
        """Ledger dei crediti residui, nome squadra -> budget."""
        out = {"NOI": float(self.nostro_budget)}
        for nome, dati in self.avversari.items():
            out[nome] = float(dati["budget"])
        return out

    def verifica(self) -> list:
        problemi = []
        presi = {}
        for nome, rosa in [("NOI", self.nostra)] + [
                (k, v["rosa"]) for k, v in self.avversari.items()]:
            for r in rosa:
                for pid in rosa[r]:
                    if pid in presi:
                        problemi.append(f"{pid} in {presi[pid]} e in {nome}")
                    presi[pid] = nome
                    if pid in self.disponibili:
                        problemi.append(f"{pid} e' di {nome} ma risulta ancora "
                                        "sul mercato")
        return problemi

    def assicura_coerenza(self) -> None:
        """Rifiuta uno stato in cui un giocatore appartiene a due squadre o e'
        posseduto e sul mercato insieme.

        Prima nessuno chiamava `verifica()` in produzione (unica occorrenza:
        un test), e uno stato incoerente veniva completato in silenzio
        producendo due possessi dello stesso giocatore."""
        problemi = self.verifica()
        if problemi:
            raise ValueError("stato d'asta incoerente: " + "; ".join(problemi))


# --------------------------------------------------------------------------
# completamento surrogato dell'asta
# --------------------------------------------------------------------------

def _rumore_di(pid, rumore, ix: dict) -> float:
    """Perturbazione associata a un giocatore.

    `rumore` puo' essere un dizionario `master_id -> float` (forma canonica:
    la perturbazione segue il giocatore, quindi resta la stessa nei due rami
    del confronto anche quando l'insieme dei disponibili cambia di un
    elemento) oppure un array indicizzato per posizione, accettato per
    compatibilita' con i chiamanti piu' vecchi."""
    if rumore is None:
        return 0.0
    if isinstance(rumore, dict):
        return float(rumore.get(pid, 0.0))
    if not len(rumore):
        return 0.0
    return float(rumore[ix.get(pid, 0) % len(rumore)])


def _ordina(disponibili, ruolo, pool, valori, prezzi, criterio, rumore=None,
            ix: dict | None = None):
    """Candidati di un ruolo, ordinati secondo il criterio dichiarato.

    Il rumore entra **dentro** il criterio, non lo sostituisce. Prima veniva
    applicato riordinando l'intera lista su `valore*(1+rumore)/prezzo`, e in
    `completa_asta` il rumore c'e' sempre: il parametro `criterio` non aveva
    quindi alcun effetto e tutti gli avversari completavano come noi, mentre
    il codice dichiarava tre criteri distinti (caso 6 dell'audit: 2 rose
    distinte senza rumore, 1 con rumore)."""
    ix = ix or {}
    ids = [pid for pid in disponibili if pool[pid].role == ruolo]
    if criterio == "valore_su_prezzo":
        def k(pid):
            v = valori.get(pid, 0.0) * (1.0 + _rumore_di(pid, rumore, ix))
            return -(v / max(prezzi.get(pid, 1.0), 1.0))
    elif criterio == "prezzo":
        def k(pid):
            return -(max(prezzi.get(pid, 1.0), 1.0)
                     * (1.0 + _rumore_di(pid, rumore, ix)))
    else:
        def k(pid):
            return -(valori.get(pid, 0.0) * (1.0 + _rumore_di(pid, rumore, ix)))
    ids.sort(key=lambda pid: (k(pid), str(pid)))
    return ids


def _massimo_offribile(budget: float, posti_vuoti_dopo: int) -> float:
    """Quanto si puo' offrire ora lasciando un credito per ogni altro posto.

    E' la stessa regola di `StatoAsta.max_legale`, scritta una volta sola
    perche' valga identica nel completamento e nel controllo del prezzo."""
    return budget - max(0, posti_vuoti_dopo)


@dataclass
class EsitoRosa:
    """Esito del completamento surrogato di una singola rosa.

    Separa quello che il ledger ha gia' deciso da quello che la simulazione ha
    solo ipotizzato:

      - `conclusi`  acquisti d'asta gia' battuti, immutabili;
      - `pagati`    candidati pianificati in questa simulazione, con il prezzo
                    addebitato: sono gli unici scambiabili, e l'unico rimborso
                    ammesso e' esattamente il prezzo qui registrato."""
    rosa: dict
    budget: float
    budget_iniziale: float
    conclusi: dict
    pagati: dict
    presi: list
    riempitivi_a_un_credito: list
    scartati: list
    insoluti: dict
    criterio: str

    @property
    def speso(self) -> float:
        return float(sum(self.pagati.values()))

    @property
    def completa(self) -> bool:
        return not self.insoluti


def completa_rosa_surrogata(rosa: dict, budget: float, disponibili: set,
                            pool: dict, prezzi: dict, valori: dict,
                            regole: Regole,
                            criterio: str = "valore_su_prezzo",
                            rumore=None, migliora: bool = True,
                            riempimento_a_un_credito: bool = True) -> EsitoRosa:
    """Riempie i posti vuoti con quello che resta, restando legale, e poi
    **spende i crediti che avanzano** sui soli acquisti pianificati.

    Il secondo passaggio non e' un dettaglio. Senza, il completamento sceglie
    i giocatori col miglior rapporto fra valore e prezzo, si ferma intorno ai
    200 crediti e lascia il resto in cassa: da quel momento il budget non
    vincola piu' niente e il prezzo di indifferenza esce identico a ogni
    prezzo, perche' pagare 22 o 68 non cambia nulla. Misurato nel primo giro:
    differenza +0,0125 identica a 22, 38, 53 e 68 crediti.

    Con il miglioramento, ogni credito speso su un giocatore toglie qualcosa a
    un altro posto: e' quello che rende il confronto informativo. Il
    miglioramento agisce **solo sui candidati pianificati qui**: la rosa in
    ingresso e' il ledger d'asta e non si tocca.

    `rumore` (per giocatore) sposta un poco l'ordine: serve a rappresentare
    che l'asta non segue una graduatoria perfetta."""
    conclusi = {r: list(rosa.get(r, [])) for r in regole.quote}
    lavoro = {r: list(rosa.get(r, [])) for r in regole.quote}
    liberi = set(disponibili)
    ix = {pid: i for i, pid in enumerate(sorted(liberi))}
    pagati: dict = {}
    presi: list = []
    riempitivi: list = []
    insoluti: dict = {}

    def vuoti_totali() -> int:
        return sum(regole.quote[r] - len(lavoro[r]) for r in regole.quote)

    ordine_ruoli = sorted(regole.quote,
                          key=lambda r: -(regole.quote[r] - len(lavoro[r])))
    for ruolo in ordine_ruoli:
        if regole.quote[ruolo] - len(lavoro[ruolo]) <= 0:
            continue
        for pid in _ordina(liberi, ruolo, pool, valori, prezzi, criterio,
                           rumore, ix):
            if regole.quote[ruolo] - len(lavoro[ruolo]) <= 0:
                break
            prezzo = max(1.0, float(prezzi.get(pid, 1.0)))
            if prezzo > _massimo_offribile(budget, vuoti_totali() - 1):
                continue
            lavoro[ruolo].append(pid)
            liberi.discard(pid)
            budget -= prezzo
            pagati[pid] = prezzo
            presi.append(pid)
        # Ripiego: quello che resta si prende a 1 credito. Non deriva da
        # nessuna regola d'asta (nel motore vero un lotto va a 1 credito
        # quando nessuno rilancia sull'apertura, ed e' una regola scritta):
        # e' un riempitivo, quindi viene contato e dichiarato nel risultato.
        # La capienza pero' vale anche qui: prima non c'era nessun controllo e
        # una rosa poteva chiudere con budget -3,0 (caso 5 dell'audit).
        if riempimento_a_un_credito:
            for pid in _ordina(liberi, ruolo, pool, valori, prezzi, criterio,
                               rumore, ix):
                if regole.quote[ruolo] - len(lavoro[ruolo]) <= 0:
                    break
                if 1.0 > _massimo_offribile(budget, vuoti_totali() - 1):
                    break
                lavoro[ruolo].append(pid)
                liberi.discard(pid)
                budget -= 1.0
                pagati[pid] = 1.0
                presi.append(pid)
                riempitivi.append(pid)
        mancano = regole.quote[ruolo] - len(lavoro[ruolo])
        if mancano > 0:
            # Esito, non eccezione: un reparto che non si chiude va riportato
            # a chi legge, non fatto risalire fino allo script dei tetti.
            insoluti[ruolo] = mancano

    scartati: list = []
    if migliora:
        budget, scartati = _migliora_i_pianificati(
            lavoro, budget, liberi, pool, prezzi, valori, regole,
            pagati, presi, riempitivi)
    return EsitoRosa(rosa=lavoro, budget=budget, budget_iniziale=float(budget)
                     + float(sum(pagati.values())),
                     conclusi=conclusi, pagati=pagati, presi=presi,
                     riempitivi_a_un_credito=riempitivi, scartati=scartati,
                     insoluti=insoluti, criterio=criterio)


def completa_rosa(rosa: dict, budget: float, disponibili: set, pool: dict,
                  prezzi: dict, valori: dict, regole: Regole,
                  criterio: str = "valore_su_prezzo",
                  rumore=None, migliora: bool = True) -> tuple:
    """Alias compatibile di `completa_rosa_surrogata`.

    Ritorna `(rosa completata, budget residuo, giocatori presi)`. `presi`
    contiene solo i candidati sopravvissuti all'ottimizzazione: chi e' stato
    scartato non e' mai uscito dal mercato del chiamante, quindi non va
    rimesso a mano (prima tornava in un insieme locale che non usciva dalla
    funzione, e spariva dal mondo)."""
    e = completa_rosa_surrogata(rosa, budget, disponibili, pool, prezzi,
                                valori, regole, criterio, rumore, migliora)
    return e.rosa, e.budget, list(e.presi)


def _migliora_i_pianificati(rosa: dict, budget: float, liberi: set, pool: dict,
                            prezzi: dict, valori: dict, regole: Regole,
                            pagati: dict, presi: list, riempitivi: list,
                            max_passi: int = 40) -> tuple:
    """Sostituisce il piu' debole fra i **candidati pianificati** con il
    migliore che i crediti residui permettono, finche' migliora.

    I crediti che restano a fine asta valgono zero: tenerli non e' prudenza, e'
    valore buttato. Durante l'asta valgono quanto le occasioni che restano, ed
    e' esattamente quello che questa procedura misura.

    Due vincoli che prima non c'erano, e la cui assenza inventava una
    rivendita che in asta non esiste:

      - si scambiano solo i giocatori **pianificati in questa simulazione**;
        gli acquisti conclusi del ledger non sono in `pagati` e restano dove
        sono (caso 1 dell'audit: rosa `{'P': [1]}` con 10 crediti diventava
        `{'P': [2]}` con 0);
      - il rimborso e' il prezzo **addebitato qui**, non il prezzo previsto
        dal modello: cosi' la somma di speso e residuo resta invariante (caso
        2: un giocatore pagato 1 credito e quotato 90 veniva rimborsato 90,
        cioe' 90 crediti creati dal nulla)."""
    scartati: list = []
    for _ in range(max_passi):
        if budget < 1:
            break
        migliore = None
        for ruolo in regole.quote:
            dentro = sorted((pid for pid in rosa[ruolo] if pid in pagati),
                            key=lambda pid: valori.get(pid, 0.0))
            if not dentro:
                continue
            debole = dentro[0]
            rimborso = float(pagati[debole])
            for pid in liberi:
                pl = pool.get(pid)
                if pl is None or pl.role != ruolo:
                    continue
                prezzo = max(1.0, float(prezzi.get(pid, 1.0)))
                costo = prezzo - rimborso
                if costo > budget:
                    continue
                guadagno = valori.get(pid, 0.0) - valori.get(debole, 0.0)
                if guadagno <= 0:
                    continue
                if migliore is None or guadagno > migliore[0]:
                    migliore = (guadagno, ruolo, debole, pid, costo, prezzo)
        if migliore is None:
            break
        _, ruolo, debole, entrante, costo, prezzo = migliore
        rosa[ruolo] = [entrante if x == debole else x for x in rosa[ruolo]]
        liberi.discard(entrante)
        liberi.add(debole)
        del pagati[debole]
        pagati[entrante] = prezzo
        presi[:] = [pid for pid in presi if pid != debole] + [entrante]
        if debole in riempitivi:
            riempitivi.remove(debole)
        scartati.append(debole)
        budget -= costo
    return budget, scartati


@dataclass
class EsitoAstaSurrogata:
    """Esito del completamento surrogato di tutta la lega.

    Porta il mercato residuo e la contabilita' per squadra, cosi' che le
    invarianti si possano controllare da fuori invece di doverle dedurre."""
    rose: dict
    budget: dict
    budget_iniziale: dict
    conclusi: dict
    pagati: dict
    presi: dict
    riempitivi_a_un_credito: dict
    scartati: dict
    insoluti: dict
    disponibili: set
    ordine: list
    criteri: dict

    def diagnostica(self) -> dict:
        """Riassunto dichiarabile in un risultato esposto."""
        return {
            "riempitivi_a_un_credito": sum(
                len(v) for v in self.riempitivi_a_un_credito.values()),
            "posti_insoluti": sum(sum(v.values())
                                  for v in self.insoluti.values()),
            "rose_incomplete": sum(1 for v in self.insoluti.values() if v),
            "scambi_fra_candidati": sum(len(v) for v in self.scartati.values()),
            "speso": {k: round(float(sum(v.values())), 4)
                      for k, v in self.pagati.items()},
            "residuo": {k: round(float(v), 4) for k, v in self.budget.items()},
            "mercato_residuo": len(self.disponibili),
        }


def completa_asta_surrogata(stato: StatoAsta, pool: dict, prezzi: dict,
                            valori: dict, replica: int, seme: int,
                            criterio_nostro: str = "valore_su_prezzo",
                            criteri_avversari: tuple = CRITERI_AVVERSARI,
                            controlla: bool = True) -> EsitoAstaSurrogata:
    """Completa tutte le rose dallo stato dato, con la procedura surrogata.

    L'ordine in cui le squadre completano dipende dalla replica: e' una delle
    condizioni esterne che i due rami devono condividere. E' anche il motivo
    per cui questo non e' un'asta: chi viene servito per primo vede il pool
    intero e riempie tutta la rosa prima che il secondo cominci.

    Il rumore e' estratto **per giocatore** e non per posizione nell'insieme
    dei disponibili: cosi' resta lo stesso nei due rami del confronto anche
    quando la nostra rosa cambia di un elemento. Con l'indicizzazione
    posizionale precedente l'appaiamento fra i rami era incompleto
    (correlazione 0,674-0,808 misurata dall'audit)."""
    if controlla:
        stato.assicura_coerenza()
    rng = np.random.default_rng([seme, replica])
    disponibili = set(stato.disponibili)
    nomi = ["NOI"] + sorted(stato.avversari)
    ordine = [nomi[k] for k in rng.permutation(len(nomi))]
    tutti = sorted(pool)
    rumore = {pid: float(x)
              for pid, x in zip(tutti, rng.normal(0, 0.15, max(len(tutti), 1)))}

    rose = {nome: {r: list(v) for r, v in rosa.items()}
            for nome, rosa in stato.rose().items()}
    budget = stato.budget()
    criteri = {}
    for k, nome in enumerate(nomi):
        criteri[nome] = (criterio_nostro if nome == "NOI"
                         else criteri_avversari[k % len(criteri_avversari)])

    esiti = {}
    for nome in ordine:
        e = completa_rosa_surrogata(rose[nome], budget[nome], disponibili,
                                    pool, prezzi, valori, stato.regole,
                                    criteri[nome], rumore)
        esiti[nome] = e
        rose[nome] = e.rosa
        budget[nome] = e.budget
        disponibili -= set(e.presi)
    return EsitoAstaSurrogata(
        rose=rose, budget=budget,
        budget_iniziale=stato.budget(),
        conclusi={n: e.conclusi for n, e in esiti.items()},
        pagati={n: dict(e.pagati) for n, e in esiti.items()},
        presi={n: list(e.presi) for n, e in esiti.items()},
        riempitivi_a_un_credito={n: list(e.riempitivi_a_un_credito)
                                 for n, e in esiti.items()},
        scartati={n: list(e.scartati) for n, e in esiti.items()},
        insoluti={n: dict(e.insoluti) for n, e in esiti.items()},
        disponibili=disponibili, ordine=ordine, criteri=criteri)


def completa_asta(stato: StatoAsta, pool: dict, prezzi: dict, valori: dict,
                  replica: int, seme: int,
                  criterio_nostro: str = "valore_su_prezzo",
                  criteri_avversari: tuple = CRITERI_AVVERSARI) -> dict:
    """Alias compatibile: ritorna solo `nome -> rosa completa`."""
    return completa_asta_surrogata(stato, pool, prezzi, valori, replica, seme,
                                   criterio_nostro, criteri_avversari).rose


def verifica_contabilita(esito: EsitoAstaSurrogata, stato: StatoAsta,
                         prezzi: dict | None = None) -> list:
    """Controlla le invarianti contabili di un completamento e le riporta.

    Ritorna la lista dei problemi trovati, vuota se tutto chiude. E' la forma
    controllabile da fuori delle regole scritte in testa al modulo: ledger
    chiuso, acquisti conclusi immutabili, un giocatore in una squadra sola,
    nessuno sparito dal mondo, quote rispettate."""
    problemi = []
    quote = stato.regole.quote
    proprietario = {}
    for nome, rosa in esito.rose.items():
        speso = float(sum(esito.pagati.get(nome, {}).values()))
        b0 = float(esito.budget_iniziale[nome])
        if abs((b0 - speso) - float(esito.budget[nome])) > 1e-6:
            problemi.append(
                f"{nome}: residuo {esito.budget[nome]} != {b0} - {speso}")
        if esito.budget[nome] < -1e-9:
            problemi.append(f"{nome}: budget negativo {esito.budget[nome]}")
        for pid, pagato in esito.pagati.get(nome, {}).items():
            if pagato < 1.0 - 1e-9:
                problemi.append(f"{nome}: {pid} pagato {pagato} sotto 1 credito")
            if prezzi is not None and pagato > max(1.0, float(
                    prezzi.get(pid, 1.0))) + 1e-9:
                problemi.append(
                    f"{nome}: {pid} pagato {pagato} sopra il prezzo previsto "
                    f"{prezzi.get(pid)}")
        for ruolo, ids in rosa.items():
            if len(ids) > quote.get(ruolo, 0):
                problemi.append(f"{nome}/{ruolo}: {len(ids)} su {quote[ruolo]}")
            for pid in ids:
                if pid in proprietario:
                    problemi.append(
                        f"{pid} in {proprietario[pid]} e in {nome}")
                proprietario[pid] = nome
        conclusi = {pid for v in esito.conclusi[nome].values() for pid in v}
        dentro = {pid for v in rosa.values() for pid in v}
        persi = conclusi - dentro
        if persi:
            problemi.append(f"{nome}: acquisti conclusi usciti dalla rosa "
                            f"{sorted(persi)}")
    inizio = set(stato.disponibili) | {
        pid for rosa in stato.rose().values() for v in rosa.values()
        for pid in v}
    fine = set(proprietario) | set(esito.disponibili)
    if inizio - fine:
        problemi.append(f"giocatori spariti dal mondo: {sorted(inizio - fine)}")
    if fine - inizio:
        problemi.append(f"giocatori comparsi dal nulla: {sorted(fine - inizio)}")
    return problemi


# --------------------------------------------------------------------------
# valutazione con memoria
# --------------------------------------------------------------------------

class Cache:
    """Punteggi per rosa e scenario, calcolati una volta sola.

    Fra due prezzi vicini la rosa completata spesso non cambia: senza memoria
    si rifarebbe lo stesso calcolo decine di volte."""

    def __init__(self, cubo, regole: Regole):
        self.cubo = cubo
        self.regole = regole
        self.indice = {pid: i for i, pid in enumerate(cubo.giocatori)}
        self._m = {}
        self.colpi = 0
        self.calcoli = 0

    @staticmethod
    def firma(rosa: dict) -> tuple:
        return tuple(sorted((r, tuple(sorted(map(str, v))))
                            for r, v in rosa.items()))

    def punteggi(self, rosa: dict, scenari, giornate=None) -> np.ndarray:
        f = (self.firma(rosa), tuple(scenari),
             None if giornate is None else tuple(giornate))
        if f in self._m:
            self.colpi += 1
            return self._m[f]
        self.calcoli += 1
        out = np.array([_punteggi_rosa(rosa, self.cubo, self.indice, s,
                                       self.regole, giornate)
                        for s in scenari])
        self._m[f] = out
        return out


def p_primo_da_punteggi(punteggi: dict, calendario, regole: Regole,
                        stato_iniziale=None) -> dict:
    """Da {nome: (n_scenari, n_giornate)} alla quota di vittoria per squadra."""
    from .valutatore import classifica
    from ..season.lineup import goals_from_points
    nomi = sorted(punteggi)
    P = np.stack([punteggi[n] for n in nomi], axis=1)     # (scen, squadre, gior)
    G = np.vectorize(lambda x: goals_from_points(x, regole.soglia_gol,
                                                 regole.passo_gol))(P)
    vitt = np.zeros((P.shape[0], len(nomi)))
    for s in range(P.shape[0]):
        _, _, v = classifica(G[s], P[s], calendario, regole, stato_iniziale)
        vitt[s] = v
    return {n: vitt[:, i] for i, n in enumerate(nomi)}


# --------------------------------------------------------------------------
# chiave di validita' di un tetto
# --------------------------------------------------------------------------

def _sha(testo: str, n: int = 16) -> str:
    return hashlib.sha256(testo.encode("utf-8")).hexdigest()[:n]


def _impronta_cubo(cubo) -> str:
    """Impronta del contenuto del cubo, memorizzata sull'oggetto.

    Un tetto calcolato su un cubo non vale su un altro: l'impronta e' la parte
    della chiave di validita' che lo rende verificabile. Se il cubo ne porta
    gia' una (`impronta`), quella vince."""
    dichiarata = getattr(cubo, "impronta", None)
    if isinstance(dichiarata, str) and dichiarata:
        return dichiarata
    memoria = getattr(cubo, "_impronta_indifferenza", None)
    if isinstance(memoria, str) and memoria:
        return memoria
    h = hashlib.sha256()
    h.update(repr([str(p) for p in getattr(cubo, "giocatori", [])]
                  ).encode("utf-8"))
    for campo in ("fantavoto", "voto", "gioca", "gol_subiti"):
        a = getattr(cubo, campo, None)
        if a is None:
            h.update(b"|none")
            continue
        a = np.ascontiguousarray(a)
        h.update(f"|{campo}:{a.shape}:{a.dtype}".encode("utf-8"))
        h.update(a.tobytes())
    out = h.hexdigest()[:16]
    try:
        setattr(cubo, "_impronta_indifferenza", out)
    except Exception:                     # cubo immutabile: si ricalcola
        pass
    return out


def _impronta_listini(pool: dict, prezzi: dict, valori: dict) -> str:
    """Impronta di prezzi e valori usati.

    Entra nella chiave perche' il completamento surrogato paga il prezzo
    previsto: se il listino si sposta (per esempio perche' `market_heat` lo
    riscala) il tetto calcolato prima non e' piu' lo stesso oggetto."""
    righe = [f"{pid}:{round(float(prezzi.get(pid, 0.0)), 6)}:"
             f"{round(float(valori.get(pid, 0.0)), 6)}"
             for pid in sorted(pool, key=str)]
    return _sha("|".join(righe), 12)


def chiave_di_validita(stato: StatoAsta, pool: dict, prezzi: dict,
                       valori: dict, cubo, scenari: list, repliche: int,
                       seme: int, calendario=None, giornate=None,
                       extra: dict | None = None) -> dict:
    """Identifica lo stato del mondo da cui un tetto e' stato calcolato.

    Un tetto e' per costruzione una funzione dello stato d'asta completo, e
    smette di valere appena quello stato cambia: a ogni nostro acquisto
    (cambiano budget, posti liberi e massimo legale), a ogni acquisto altrui
    che tocca il ruolo o le alternative, quando il nostro reparto si riempie,
    quando il listino si sposta, quando il giocatore stesso e' gia' stato
    venduto.

    Chi consuma un tetto ricalcola questa chiave sullo stato in cui si trova e
    confronta l'impronta: se differisce, il tetto e' scaduto. Il consumo non e'
    implementato qui, e questo modulo non decide che cosa farne."""
    nostra = {r: sorted(map(str, stato.nostra.get(r, [])))
              for r in stato.regole.quote}
    avversari = {nome: {"rosa": {r: sorted(map(str, dati["rosa"].get(r, [])))
                                 for r in stato.regole.quote},
                        "budget": round(float(dati["budget"]), 6)}
                 for nome, dati in sorted(stato.avversari.items())}
    componenti = {
        "stato_decisionale": {
            "nostro_budget": float(stato.nostro_budget),
            "nostra_rosa": nostra,
            "posti_liberi": stato.posti_liberi(stato.nostra),
            "massimo_legale": stato.max_legale(stato.nostra,
                                               stato.nostro_budget),
            "n_disponibili": len(stato.disponibili),
            "impronta_disponibili": _sha(
                "|".join(sorted(map(str, stato.disponibili))), 12),
            "impronta_avversari": _sha(json.dumps(avversari, sort_keys=True),
                                       12),
        },
        "cubo": {
            "impronta": _impronta_cubo(cubo),
            "forma": list(getattr(cubo, "fantavoto").shape)
            if getattr(cubo, "fantavoto", None) is not None else None,
        },
        "listini": {"impronta": _impronta_listini(pool, prezzi, valori),
                    "n_giocatori": len(pool)},
        "esperimento": {
            "scenari": list(scenari),
            "n_scenari": len(list(scenari)),
            "repliche": int(repliche),
            "seme": int(seme),
            "giornate": None if giornate is None else list(giornate),
            "impronta_calendario": (None if calendario is None
                                    else _sha(repr(calendario), 12)),
            "completamento": COMPLETAMENTO_SURROGATO["tipo"],
        },
        "regole": {
            "quote": dict(stato.regole.quote),
            "budget": stato.regole.budget,
            "max_cambi": stato.regole.max_cambi,
            "soglia_gol": stato.regole.soglia_gol,
            "passo_gol": stato.regole.passo_gol,
            "usa_mod_difesa": stato.regole.usa_mod_difesa,
            "applica_bonus_porta_inviolata":
                stato.regole.applica_bonus_porta_inviolata,
            "punti": list(stato.regole.punti),
            "spareggio": list(stato.regole.spareggio),
            "parita_finale": stato.regole.parita_finale,
        },
    }
    if extra:
        componenti["extra"] = extra
    componenti["impronta"] = _sha(
        json.dumps(componenti, sort_keys=True, default=str), 16)
    componenti["avvertenza"] = (
        "un tetto vale solo per lo stato d'asta che questa chiave descrive: "
        "ricalcolare la chiave sullo stato corrente e confrontare l'impronta "
        "prima di usarlo")
    return componenti


# --------------------------------------------------------------------------
# la differenza
# --------------------------------------------------------------------------

@dataclass
class Confronto:
    prezzo: int
    delta: float
    ic95: tuple
    p1_compro: float
    p1_passo: float
    n_repliche: int
    alternative: list = field(default_factory=list)
    bersaglio_sempre_nostro: bool = True
    diagnostica: dict = field(default_factory=dict)
    # I delta replica per replica restano nel confronto perche' l'intervallo
    # al 95 % per singolo confronto non e' l'unico che serve: il tetto e' il
    # massimo su k prezzi, e per leggerlo a livello di famiglia l'intervallo
    # va ricalcolato a un livello per confronto piu' stretto. Senza i dati
    # grezzi quel ricalcolo non e' possibile e va dichiarato mancante.
    delta_per_replica: tuple = ()


# Livello dichiarato dell'esperimento. Sta qui come costante e non come
# parametro perche' non e' una manopola: spostarlo dopo aver visto i risultati
# cambierebbe l'esito senza cambiare i dati. La correzione per il numero di
# prezzi provati (piu' sotto) rende il livello per confronto piu' severo, mai
# meno: la soglia di famiglia resta 0,05.
ALFA = 0.05

# Ricampionamenti del bootstrap percentile. Era gia' 4000 prima di questa
# revisione: il numero resta lo stesso perche' cambiarlo cambierebbe gli
# intervalli gia' salvati in `data/l3/asta/tetti_2026-27.json`.
N_BOOTSTRAP = 4000


def _ic_bootstrap(d, seme: int, alfa: float = ALFA,
                  n: int = N_BOOTSTRAP) -> tuple:
    """Intervallo percentile bootstrap sulla media dei delta per replica.

    Con `alfa = 0,05` riproduce esattamente l'intervallo che questo modulo
    calcolava prima (stessa sequenza casuale, stessi percentili 2,5 e 97,5):
    gli intervalli gia' salvati non cambiano.

    Con una sola replica l'intervallo non esiste e si restituisce `nan`: e'
    un esito, non un intervallo largo. Va detto che con quattro repliche
    l'intervallo percentile e' grossolano — la coda e' fatta di pochi valori
    distinti — e a livelli piu' stretti lo diventa di piu': l'audit dell'8
    settembre ha misurato una deviazione standard per replica intorno a 0,13
    sui bersagli provati, e `1,96 x sd / sqrt(n)` e' una semiampiezza
    approssimata, non un'analisi di potenza."""
    d = np.asarray(d, dtype=float)
    if d.size <= 1:
        return (float("nan"), float("nan"))
    rng = np.random.default_rng(seme + 1)
    idx = rng.integers(0, d.size, (n, d.size))
    medie = d[idx].mean(1)
    return (float(np.percentile(medie, 100.0 * alfa / 2.0)),
            float(np.percentile(medie, 100.0 * (1.0 - alfa / 2.0))))


def _accumula(diag: dict, esito: EsitoAstaSurrogata, ramo: str) -> None:
    d = esito.diagnostica()
    for chiave in ("riempitivi_a_un_credito", "posti_insoluti",
                   "rose_incomplete", "scambi_fra_candidati"):
        diag[chiave] = diag.get(chiave, 0) + d[chiave]
    diag.setdefault("criteri_avversari", esito.criteri)
    diag[f"completamenti_{ramo}"] = diag.get(f"completamenti_{ramo}", 0) + 1


def delta_a_prezzo(giocatore, prezzo: int, stato: StatoAsta, pool: dict,
                   prezzi: dict, valori: dict, cache: Cache, calendario,
                   scenari: list, repliche: int, seme: int,
                   giornate=None, stato_iniziale=None,
                   completatore=None) -> Confronto:
    """Differenza di P(primo) fra comprare a `prezzo` e lasciar perdere.

    Le condizioni esterne (ordine di completamento, rumore, scenari) sono le
    stesse nei due rami, replica per replica.

    Nel ramo "compro" il giocatore entra fra gli **acquisti conclusi**: da li'
    in avanti e' immutabile come tutti gli altri, e il completamento non puo'
    piu' scartarlo. Se potesse, quel ramo non conterrebbe l'acquisto di cui si
    sta misurando il valore (caso 4 dell'audit).

    `completatore` e' il gancio per sostituire il completamento surrogato con
    il motore d'asta vero: una callable
    `(stato, pool, prezzi, valori, replica, seme) -> EsitoAstaSurrogata`."""
    completatore = completatore or completa_asta_surrogata
    regole = stato.regole
    ruolo = pool[giocatore].role
    if giocatore not in stato.disponibili:
        raise ValueError(f"{giocatore} non e' piu' sul mercato")
    if len(stato.nostra.get(ruolo, [])) >= regole.quote[ruolo]:
        raise ValueError(f"reparto {ruolo} gia' pieno: non possiamo comprarlo")
    tetto = stato.max_legale(stato.nostra, stato.nostro_budget)
    if prezzo > tetto:
        raise ValueError(f"prezzo {prezzo} oltre il massimo legale {tetto}")

    d_compro, d_passo = [], []
    alternative = []
    diag: dict = {"passo_invenduto": 0, "passo_a_un_avversario": 0}
    bersaglio_sempre_nostro = True
    for r in range(repliche):
        # ramo COMPRO: l'acquisto e' concluso, quindi entra nel ledger
        s1 = StatoAsta(
            nostra={k: (list(v) + [giocatore] if k == ruolo else list(v))
                    for k, v in stato.nostra.items()},
            nostro_budget=stato.nostro_budget - prezzo,
            avversari={k: {"rosa": {kk: list(vv) for kk, vv in v["rosa"].items()},
                           "budget": v["budget"]}
                       for k, v in stato.avversari.items()},
            disponibili=set(stato.disponibili) - {giocatore},
            regole=regole)
        e1 = completatore(s1, pool, prezzi, valori, r, seme)
        rose1 = e1.rose
        _accumula(diag, e1, "compro")
        if giocatore not in {pid for v in rose1["NOI"].values() for pid in v}:
            bersaglio_sempre_nostro = False
        # ramo PASSO: il giocatore lo prende un avversario, scelto dalla stessa
        # replica; se nessuno ha posto e budget, resta invenduto
        rng = np.random.default_rng([seme, r, zlib.crc32(str(giocatore).encode())])
        candidati_avv = [k for k, v in stato.avversari.items()
                         if len(v["rosa"].get(ruolo, [])) < regole.quote[ruolo]
                         and v["budget"] >= prezzo + max(
                             0, sum(regole.quote[x] - len(v["rosa"].get(x, []))
                                    for x in regole.quote) - 1)]
        avversari2 = {k: {"rosa": {kk: list(vv) for kk, vv in v["rosa"].items()},
                          "budget": v["budget"]}
                      for k, v in stato.avversari.items()}
        if candidati_avv:
            scelto = candidati_avv[int(rng.integers(len(candidati_avv)))]
            avversari2[scelto]["rosa"][ruolo] = (
                list(avversari2[scelto]["rosa"].get(ruolo, [])) + [giocatore])
            avversari2[scelto]["budget"] -= prezzo
            diag["passo_a_un_avversario"] += 1
        else:
            # Nessun avversario capiente: il giocatore esce comunque dal
            # mercato. E' l'assunzione dichiarata del ramo "passo" ("lo compra
            # un altro oppure resta invenduto"), e va contata perche' toglie
            # un giocatore al mercato senza che nessuno lo paghi.
            diag["passo_invenduto"] += 1
        s2 = StatoAsta(
            nostra={k: list(v) for k, v in stato.nostra.items()},
            nostro_budget=stato.nostro_budget,
            avversari=avversari2,
            disponibili=set(stato.disponibili) - {giocatore},
            regole=regole)
        e2 = completatore(s2, pool, prezzi, valori, r, seme)
        rose2 = e2.rose
        _accumula(diag, e2, "passo")
        if r == 0:
            nostri1 = {pid for k in rose1["NOI"] for pid in rose1["NOI"][k]}
            nostri2 = {pid for k in rose2["NOI"] for pid in rose2["NOI"][k]}
            alternative = sorted(nostri2 - nostri1)

        for rose, dove in ((rose1, d_compro), (rose2, d_passo)):
            punt = {n: cache.punteggi(rose[n], scenari, giornate) for n in rose}
            v = p_primo_da_punteggi(punt, calendario, regole, stato_iniziale)
            dove.append(v["NOI"].mean())

    a = np.array(d_compro)
    b = np.array(d_passo)
    d = a - b
    ic = _ic_bootstrap(d, seme)
    return Confronto(prezzo=prezzo, delta=float(d.mean()), ic95=ic,
                     p1_compro=float(a.mean()), p1_passo=float(b.mean()),
                     n_repliche=len(d), alternative=alternative,
                     bersaglio_sempre_nostro=bersaglio_sempre_nostro,
                     diagnostica=diag,
                     delta_per_replica=tuple(float(x) for x in d))


def _esito_di(ic) -> str:
    """Che cosa un singolo intervallo sostiene, sul suo prezzo e su nessun altro.

    Quattro esiti, mutuamente esclusivi:

      - `vantaggio_supportato`: l'intervallo sta interamente sopra lo zero;
      - `svantaggio_supportato`: interamente sotto;
      - `inconcludente`: contiene lo zero (estremo a 0,0 compreso: toccare lo
        zero non e' escluderlo — nei 121 punti dei tetti salvati 114 hanno un
        estremo esattamente a 0,0);
      - `intervallo_non_calcolabile`: con una sola replica l'intervallo non
        esiste, e il delta puntuale da solo non sostiene niente.
    """
    lo, hi = float(ic[0]), float(ic[1])
    if np.isnan(lo) or np.isnan(hi):
        return "intervallo_non_calcolabile"
    if lo > 0.0:
        return "vantaggio_supportato"
    if hi < 0.0:
        return "svantaggio_supportato"
    return "inconcludente"


# Riferimento misurato dall'audit, riportato dentro il risultato perche' chi
# legge una stima puntuale sappia di che ordine e' la distorsione da selezione:
# Zaccagni al prezzo 28 passa da +0,1250 (4 repliche, punto migliore su 5) a
# +0,0234 (32 repliche, stesso punto), un fattore 5,3. E' il valore osservato
# su un bersaglio, non un fattore di correzione da applicare.
DISTORSIONE_DA_SELEZIONE = (
    "la stima puntuale e' il massimo su k prezzi provati, quindi distorta "
    "verso l'alto: l'audit dell'8 settembre 2026 ha misurato su Zaccagni "
    "(prezzo 28) un passaggio da +0,1250 con 4 repliche a +0,0234 con 32, "
    "un fattore 5,3 sullo stesso punto. Numero riportato, non una correzione "
    "applicata qui")


def classifica_curva(punti: list, tetto_legale: int, seme: int = 0,
                     alfa: float = ALFA) -> dict:
    """Separa, prezzo per prezzo, quello che i dati sostengono da quello che no.

    Il difetto che questa funzione sostituisce: lo stato del confronto veniva
    deciso guardando i punti a distanza <= 1 crediti dal tetto stimato, e un
    prezzo il cui intervallo esclude lo zero certificava il suo vicino, che
    non lo esclude. Con delta +0,01 e intervallo [-0,10; +0,10] a prezzo 2 e
    delta -0,01 con [-0,02; -0,005] a prezzo 3, il risultato era
    `tetto_economico = 2`, stato `verificato`: la certezza del punto 3 veniva
    attribuita al punto 2. Un risultato negativo su 3 dice qualcosa su 3.

    Qui ogni prezzo porta il proprio esito e il tetto restituito e' un prezzo
    che ha il proprio intervallo interamente sopra lo zero. Sono cose diverse,
    e hanno nomi diversi:

      - `stima_tetto`: il piu' alto prezzo con delta medio positivo. E' una
        stima puntuale scelta come massimo su k punti, quindi distorta verso
        l'alto (vedi `DISTORSIONE_DA_SELEZIONE`);
      - `tetto_supportato`: il piu' alto prezzo con vantaggio supportato. Se
        non esiste, e' `None` e non c'e' nessun tetto da usare;
      - le tre liste di prezzi (vantaggio, svantaggio, inconcludenti) piu'
        quelli senza intervallo;
      - `intervallo_indifferenza`: fra l'ultimo prezzo con vantaggio
        supportato e il primo, piu' alto, con svantaggio supportato. Se manca
        uno dei due lati non e' calcolabile, e il motivo lo dice.

    **Selezione su piu' prezzi.** Il tetto e' il massimo su k confronti: un
    intervallo al 95 % per singolo confronto non copre quella scelta. Quando i
    punti portano i delta per replica, gli intervalli usati per la
    classificazione sono ricalcolati con livello per confronto `alfa / k`
    (Bonferroni), che e' piu' severo del 95 %, mai meno: la soglia di famiglia
    resta quella dichiarata. Gli esiti per singolo confronto restano nel
    risultato, sotto `selezione`, cosi' i due livelli si leggono separati.
    Quando i delta per replica non ci sono, il ricalcolo non e' possibile e
    l'assenza di controllo e' dichiarata invece di essere taciuta.

    **Griglia rada.** Il tetto vero puo' stare fra due prezzi provati: la
    risoluzione e' la distanza dal prezzo provato successivo, riportata in
    `griglia`. Nei tetti del 2026-27 la griglia aveva passo mediano 4 e massimo
    41 (Malen: 82, 110, 138, 179, 220), cioe' una risoluzione di +-20 crediti.

    **Pareggi.** Un delta esattamente 0 non e' uno svantaggio: nei 121 punti
    salvati 26 sono esattamente 0 per la granularita' della misura (0,0125 con
    4 repliche e 20 scenari). Sono contati a parte e non contribuiscono ai
    cambi di segno.

    **Curve non monotone.** Uno svantaggio supportato a un prezzo piu' basso
    di un vantaggio supportato e' una incoerenza rispetto all'idea di un unico
    punto di svolta: viene dichiarata, e lo stato non puo' essere
    `verificato`. Lo stesso vale per un prezzo inconcludente sotto il tetto:
    non e' una contraddizione, e' un buco, ed e' dichiarato come tale.
    """
    ordinati = sorted(punti, key=lambda c: c.prezzo)
    prezzi_provati = [int(c.prezzo) for c in ordinati]
    k = len(ordinati)

    # Intervalli a livello di famiglia, se i dati grezzi ci sono per tutti i
    # punti. Un controllo applicato solo ad alcuni non sarebbe un controllo.
    repliche = [tuple(getattr(c, "delta_per_replica", ()) or ())
                for c in ordinati]
    puo_correggere = k > 0 and all(len(r) > 1 for r in repliche)
    alfa_confronto = alfa / k if (puo_correggere and k > 1) else alfa
    if puo_correggere:
        ic_usati = [_ic_bootstrap(np.asarray(r, dtype=float), seme,
                                  alfa_confronto)
                    for r in repliche]
        controllo = "bonferroni_su_bootstrap" if k > 1 else "non_necessario_k_1"
    else:
        ic_usati = [tuple(c.ic95) for c in ordinati]
        controllo = ("assente: i confronti non portano i delta per replica, "
                     "quindi gli intervalli restano quelli per singolo "
                     "confronto mentre il tetto e' il massimo su "
                     f"{k} prezzi provati")

    esiti = [_esito_di(ic) for ic in ic_usati]
    per_confronto = [_esito_di(tuple(c.ic95)) for c in ordinati]

    def _prezzi(quali: str, sorgente: list) -> list:
        return [p for p, e in zip(prezzi_provati, sorgente) if e == quali]

    vantaggio = _prezzi("vantaggio_supportato", esiti)
    svantaggio = _prezzi("svantaggio_supportato", esiti)
    incerti = _prezzi("inconcludente", esiti)
    senza_intervallo = _prezzi("intervallo_non_calcolabile", esiti)
    pareggi = [int(c.prezzo) for c in ordinati if c.delta == 0.0]

    positivi = [int(c.prezzo) for c in ordinati if c.delta > 0.0]
    stima_tetto = max(positivi) if positivi else 0
    tetto_supportato = max(vantaggio) if vantaggio else None

    # Cambi di segno sui soli delta non nulli: un pareggio non e' un cambio di
    # direzione, e contarlo come negativo (come faceva il codice precedente)
    # inventa una non monotonia che i dati non mostrano.
    segni = [1 if c.delta > 0 else -1 for c in ordinati if c.delta != 0.0]
    cambi = sum(1 for i in range(1, len(segni)) if segni[i] != segni[i - 1])

    if tetto_supportato is None:
        coerenza = "nessun_supporto"
    elif any(p < tetto_supportato for p in svantaggio):
        coerenza = "non_monotona"
    else:
        coerenza = "coerente"
    buchi = ([p for p, e in zip(prezzi_provati, esiti)
              if p < tetto_supportato and e != "vantaggio_supportato"]
             if tetto_supportato is not None else [])

    sopra = [p for p in svantaggio
             if tetto_supportato is not None and p > tetto_supportato]
    if tetto_supportato is not None and sopra:
        intervallo = [tetto_supportato, min(sopra)]
        motivo = ("il punto di indifferenza sta fra l'ultimo prezzo con "
                  "vantaggio supportato e il primo con svantaggio supportato; "
                  "dentro l'intervallo la griglia non e' stata provata")
    elif tetto_supportato is not None:
        intervallo = None
        motivo = (f"lato alto non delimitato: sopra {tetto_supportato} nessun "
                  f"prezzo provato mostra svantaggio supportato (griglia fino "
                  f"a {max(prezzi_provati)}, massimo legale {tetto_legale})")
    elif svantaggio:
        intervallo = None
        motivo = ("nessun prezzo con vantaggio supportato: il punto di "
                  "indifferenza, se esiste, sta sotto il minimo provato "
                  f"({min(prezzi_provati)}) e questa griglia non lo delimita")
    else:
        intervallo = None
        motivo = ("nessun intervallo esclude lo zero: i dati non delimitano "
                  "il punto di indifferenza da nessuno dei due lati")

    successivi = [p for p in prezzi_provati
                  if tetto_supportato is not None and p > tetto_supportato]
    risoluzione = (min(successivi) - tetto_supportato) if successivi else None
    passi = [b - a for a, b in zip(prezzi_provati, prezzi_provati[1:])]

    if tetto_supportato is None:
        stato = "inconcludente"
    elif coerenza == "coerente" and not buchi and intervallo is not None:
        stato = "verificato"
    else:
        stato = "approssimato"

    return {
        "stato": stato,
        "stima_tetto": stima_tetto,
        "tetto_supportato": tetto_supportato,
        "prezzi_vantaggio_supportato": vantaggio,
        "prezzi_svantaggio_supportato": svantaggio,
        "prezzi_inconcludenti": incerti,
        "prezzi_senza_intervallo": senza_intervallo,
        "prezzi_pareggio_puntuale": pareggi,
        "intervallo_indifferenza": intervallo,
        "intervallo_indifferenza_motivo": motivo,
        "coerenza": coerenza,
        "buchi_sotto_il_tetto": buchi,
        "cambi_di_segno": cambi,
        "griglia": {
            "prezzi": prezzi_provati,
            "passo_minimo": min(passi) if passi else None,
            "passo_massimo": max(passi) if passi else None,
            "risoluzione_tetto": risoluzione,
            "nota": ("il tetto vero puo' stare fra due prezzi provati: la "
                     "risoluzione e' la distanza dal prezzo provato "
                     "successivo, e sopra l'ultimo prezzo provato la griglia "
                     "non dice niente"),
        },
        "selezione": {
            "n_prezzi_provati": k,
            "controllo_molteplicita": controllo,
            "livello_famiglia": alfa,
            "livello_per_confronto": alfa_confronto,
            "vantaggio_supportato_per_confronto":
                _prezzi("vantaggio_supportato", per_confronto),
            "svantaggio_supportato_per_confronto":
                _prezzi("svantaggio_supportato", per_confronto),
            "distorsione_nota": DISTORSIONE_DA_SELEZIONE,
        },
        "esiti_per_prezzo": dict(zip(prezzi_provati, esiti)),
        "ic_usati": {p: [round(ic[0], 5), round(ic[1], 5)]
                     for p, ic in zip(prezzi_provati, ic_usati)},
    }


def curva(giocatore, stato: StatoAsta, pool: dict, prezzi: dict, valori: dict,
          cubo, calendario, scenari: list, prezzi_da_provare=None,
          repliche: int = 8, seme: int = 0, giornate=None,
          stato_iniziale=None, completatore=None) -> dict:
    """Delta per ogni prezzo intero richiesto, senza assumere monotonia.

    Ritorna la curva completa, il tetto economico, lo stato del confronto, la
    dichiarazione di che cosa e' il completamento usato e la chiave di
    validita' dello stato d'asta da cui tutto questo e' stato calcolato."""
    regole = stato.regole
    cache = Cache(cubo, regole)
    tetto_legale = stato.max_legale(stato.nostra, stato.nostro_budget)
    mercato = int(round(max(1.0, prezzi.get(giocatore, 1.0))))
    if prezzi_da_provare is None:
        lo = max(1, int(mercato * 0.5))
        hi = min(tetto_legale, max(mercato * 2, mercato + 10))
        passo = max(1, (hi - lo) // 10)
        prezzi_da_provare = list(range(lo, hi + 1, passo))
    chiave = chiave_di_validita(stato, pool, prezzi, valori, cubo, scenari,
                                repliche, seme, calendario, giornate)
    punti = []
    for p in prezzi_da_provare:
        if p > tetto_legale:
            continue
        punti.append(delta_a_prezzo(giocatore, int(p), stato, pool, prezzi,
                                    valori, cache, calendario, scenari,
                                    repliche, seme, giornate, stato_iniziale,
                                    completatore))
    if not punti:
        return {"stato": "inconcludente", "motivo": "nessun prezzo ammissibile",
                "tetto_legale": tetto_legale, "massimo_legale": tetto_legale,
                "tetto_economico": 0, "stima_tetto": 0,
                "chiave_validita": chiave,
                "completamento": _blocco_completamento([], completatore)}

    cl = classifica_curva(punti, tetto_legale, seme)
    stato_conf = cl["stato"]
    # Il numero esposto come `tetto_economico` e' un prezzo il cui intervallo
    # sta interamente sopra lo zero, non il massimo dei delta positivi: chi lo
    # usa come cap sta usando un prezzo sostenuto dai dati su se' stesso. Se
    # nessuno lo e', vale 0 e lo stato e' `inconcludente` — chi consuma il
    # file dei tetti scarta gia' oggi sia lo stato inconcludente sia il tetto
    # nullo. La vecchia definizione resta esposta come `stima_tetto`.
    tetto_economico = cl["tetto_supportato"] or 0
    cambi = cl["cambi_di_segno"]
    ic_usati = cl["ic_usati"]
    esiti = cl["esiti_per_prezzo"]
    return {
        "giocatore": giocatore,
        "prezzo_mercato_previsto": mercato,
        "massimo_legale": tetto_legale,
        "tetto_economico": tetto_economico,
        "stima_tetto": cl["stima_tetto"],
        "stato": stato_conf,
        "cambi_di_segno": cambi,
        "classificazione": cl,
        "curva": [{"prezzo": c.prezzo, "delta": round(c.delta, 5),
                   "ic95": [round(c.ic95[0], 5), round(c.ic95[1], 5)],
                   "ic_usato": ic_usati[int(c.prezzo)],
                   "esito": esiti[int(c.prezzo)],
                   "p1_compro": round(c.p1_compro, 5),
                   "p1_passo": round(c.p1_passo, 5)} for c in punti],
        "alternative_sacrificate": punti[0].alternative[:10],
        "repliche": repliche,
        "scenari": len(scenari),
        "cache": {"colpi": cache.colpi, "calcoli": cache.calcoli},
        "bersaglio_sempre_nostro": all(c.bersaglio_sempre_nostro
                                       for c in punti),
        "completamento": _blocco_completamento(punti, completatore),
        "chiave_validita": chiave,
        "avvertenza": ("'tetto_economico' e' il piu' alto prezzo provato il "
                       "cui intervallo sta interamente sopra lo zero: vale "
                       "per quel prezzo e non certifica i suoi vicini. "
                       "'stima_tetto' e' un'altra cosa: il piu' alto prezzo "
                       "con differenza media positiva, scelto come massimo su "
                       "k punti e quindi distorto verso l'alto. Se lo stato e' "
                       "'inconcludente' nessun prezzo provato esclude lo zero "
                       "e non c'e' nessun cap da usare. Il massimo legale e' "
                       "un vincolo d'asta, il tetto una stima: non sono la "
                       "stessa cosa. Il risultato vale solo per lo stato "
                       "d'asta descritto in 'chiave_validita'"),
    }


def _blocco_completamento(punti: list, completatore=None) -> dict:
    """Che cosa ha prodotto le rose su cui la curva e' stata misurata.

    Sta in ogni risultato esposto perche' il numero non si legga come se
    venisse da un'asta: viene da un surrogato, con lo scarto misurato che
    l'audit ha quantificato."""
    fuori = dict(COMPLETAMENTO_SURROGATO)
    if completatore is not None and completatore is not completa_asta_surrogata:
        fuori = {"nome": f"completatore esterno: "
                         f"{getattr(completatore, '__name__', repr(completatore))}",
                 "tipo": "esterno", "asta_competitiva": None,
                 "scarto_dal_motore": {"fonte": "non dichiarato dal chiamante"}}
    somma = {"riempitivi_a_un_credito": 0, "posti_insoluti": 0,
             "rose_incomplete": 0, "scambi_fra_candidati": 0,
             "passo_invenduto": 0, "passo_a_un_avversario": 0}
    criteri = {}
    for c in punti:
        for k in somma:
            somma[k] += int(c.diagnostica.get(k, 0))
        criteri = c.diagnostica.get("criteri_avversari", criteri) or criteri
    fuori.update(somma)
    fuori["avversari"] = {
        "criteri": {k: v for k, v in criteri.items() if k != "NOI"},
        "criterio_nostro": criteri.get("NOI", "valore_su_prezzo"),
        "completano_con_la_stessa_procedura": True,
        "ramo_passo": ("il giocatore va a un avversario capiente estratto "
                       "uniformemente, che paga il prezzo previsto; se nessuno "
                       "e' capiente resta invenduto ed esce dal mercato"),
    }
    fuori["nota_riempitivi"] = (
        "gli acquisti a 1 credito del completamento sono un riempitivo, non "
        "una regola d'asta: sono contati qui e la loro capienza e' verificata, "
        "ma non derivano dal fatto che nessuno abbia rilanciato sull'apertura")
    return fuori
