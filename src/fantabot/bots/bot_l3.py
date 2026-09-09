"""Bot del Livello 3: piano scelto per P(primo posto), tetto per indifferenza.

Non sostituisce il bot B. E' una variante **selezionabile**, costruita per
poter misurare la differenza fra quattro modi di fare la stessa asta:

    1. B congelato                    il bot attuale, senza toccare niente
    2. B con i fix di correttezza     stesso bot, ma la ripianificazione in
                                      asta usa la stessa soglia di spesa del
                                      piano scelto offline
    3. nuova selezione della rosa     il piano viene dalla ricerca su candidate
                                      per l'obiettivo SAA (Livello 3)
    4. nuova selezione + indifferenza il tetto d'asta viene dal confronto fra
                                      comprare e passare, non dal q90

## Il fix di correttezza del punto 2, con la prova

`montecarlo.choose_objective` costruisce il piano con
`min_spend=MIN_SPEND_FRAC * budget` (riga 371) e `f13_validate_plan.py` lo
valida con la stessa soglia (righe 62-65). `bot_b.py` **non contiene nessuna
occorrenza di `min_spend`**: la sua `_replan` chiama `optimize_roster` senza
quella soglia. Quindi appena il bot ripianifica — cosa che fa dopo ogni
acquisto, ogni target perso e ogni dieci martelletti — segue un piano diverso
da quello scelto e validato, e quel piano non ha nessun motivo di impegnare il
budget. Non e' una scelta di politica: e' un'incoerenza fra due parti dello
stesso sistema.

## Le dimensioni del trattamento, tenute distinte

Un braccio d'asta che cambia due cose insieme non e' attribuibile. Qui le
dimensioni restano separate e dichiarate una per una; fra B+ e L3 cambia
**solo** la prima.

    obiettivo di selezione   B+: MILP su `value` (con `lam` e `attack_share`).
                             L3: gli stessi vincoli, piu' l'obbligo di
                             comprare i giocatori del piano offline ancora in
                             vendita che ci stanno dentro.
    vincoli economici        identici: budget residuo, quote piene,
                             `attack_share`, pavimento di spesa
                             `MIN_SPEND_FRAC` sul piano. Il pavimento vale per
                             B+ **e** per L3, e quando i due entrano in
                             conflitto **cede il piano, non il pavimento**
                             (vedi `_forzati_ammissibili`): l'economia e' la
                             cornice comune ai bracci, il piano e' il
                             trattamento.
    frequenza del ricalcolo  identica: dopo ogni proprio acquisto, ogni target
                             perso, ogni `replan_every` martelletti, o se
                             `market_heat` si sposta di 0,08.
    massimi di offerta       identici (`q90 + peso_ombra * ombra` per i
                             titolari, `max(q50 * 1,10, 2)` per gli altri),
                             salvo il tetto per indifferenza del braccio 4, che
                             si applica **solo ai giocatori del piano**.
    ordine di chiamata       identico: `start_auction -> _replan`. Non c'e'
                             piu' nessun passo che parla dopo il MILP.
    completamento            nessuno in nessun braccio: riempie il motore.
    fallback                 dichiarati e contati, vedi `conta_milp`.

## Perche' i target non si sostituiscono piu' dopo il MILP (difetto corretto)

Fino all'8 settembre 2026 `_ancora_al_piano` girava **dopo** `_replan` e
riscriveva `self.targets` con i giocatori del piano piu' i residui del MILP.
Cosi' facendo buttava via la soluzione del MILP e con essa il pavimento di
spesa che `BBotCoerente` aveva appena imposto: misurato su 51 ancoraggi di
un'asta intera, il costo previsto dei target scendeva in mediana allo 0,891 di
quello pianificato (minimo 0,410, massimo 1,002), e i titolari passavano in
mediana da 6 a 4, cioe' altrettanti massimi di offerta scendevano da
`q90 + ombra` a `max(q50 * 1,10, 2)`. Il braccio L3 differiva da B+ per la
selezione **e** per l'economia, quindi la differenza di -0,0625 su P(1 posto)
non era attribuibile alla selezione del Livello 3.

La correzione non aggiunge nessun peso libero. I giocatori del piano ancora in
vendita entrano nel MILP come **acquisti obbligati**: vanno in `fixed` (dove il
solutore li vincola a `x = 1`) e il loro prezzo previsto viene tolto dal budget
e dalla soglia passati a `optimize_roster`. La compensazione e' esatta perche'
`optimize_roster` assegna costo 0 ai giocatori in `fixed` e somma il vincolo di
budget sui soli `candidates`: forzare un giocatore da 8 crediti e passare
`budget - 8`, `min_spend - 8` da' lo stesso insieme ammissibile che si
otterrebbe con un vincolo `x = 1` a prezzo pieno. Cosi' il pavimento di spesa,
le quote, il budget e `attack_share` restano imposti dal solutore, e i titolari
tornano a essere quelli che il MILP sceglie.

L'alternativa proposta in `RIPRESA_L2_L3.md` §2.1 — un bonus di valore ai
giocatori del piano dentro `values` — e' stata scartata: sarebbe una nuova
euristica con un peso arbitrario da tarare, e il suo effetto dipenderebbe dalla
scala di `value`. Il vincolo duro non ha parametri.

Quando il piano non ci sta (posti di ruolo gia' pieni, oppure budget residuo
insufficiente) i giocatori in eccedenza vengono **troncati prima** di chiamare
il solutore, in ordine di `value` decrescente, con il pareggio risolto
sull'identificativo per essere deterministici fra processi diversi. Il
troncamento e' contato in `piano_troncati_dal_vincolo`. Un secondo taglio cede
altri giocatori del piano finche' il pavimento di spesa torna raggiungibile
(`piano_ceduto_al_pavimento`). Se anche cosi' il MILP resta infattibile, il
piano viene abbandonato per quel ricalcolo e si torna al contesto di B+: e'
contato in `piano_scartato_per_infattibilita`.

## Il pavimento riguarda il piano, non la spesa realizzata

`MIN_SPEND_FRAC = 0,95` vincola la **soluzione del MILP**, non i crediti che
l'asta ci fara' davvero spendere: anche B+ chiude a 419 crediti su 500 nella
replica 0. Inoltre `optimize_roster` abbassa da sola la soglia a
`budget - (slot ancora da riempire - 1)` per non rendere la rosa incompletabile.
`ultimo_ricalcolo` riporta, per l'ultimo ricalcolo, la soglia chiesta, quella
effettivamente applicata dopo quel taglio, il costo previsto dei target e quale
dei quattro tentativi ha risolto; `conta_milp` li conta tutti dall'inizio.
Quando il pavimento e' impossibile il tentativo che risolve e' `solo_attacco` o
`nessun_vincolo`, ed e' li' che lo si legge.

## Il tetto per indifferenza, e perche' non puo' essere esatto in asta

Il tetto giusto e' il piu' alto prezzo per cui comprare aumenta la probabilita'
di arrivare primi rispetto a passare. Calcolarlo richiede di completare l'asta
molte volte da entrambi i rami: nel pilota costa una ventina di secondi per
giocatore. In un'asta con 250 lotti non e' praticabile lotto per lotto.

Quindi: si precalcola per i giocatori del piano prima dell'asta, e quando per
un giocatore del piano il tetto non c'e' **o non e' piu' valido** si ripiega
sul tetto del bot B **registrando il ripiego con la sua ragione**. Il numero di
ripieghi e' un risultato dell'esperimento, non un dettaglio: se il tetto per
indifferenza vale solo nel 20% dei lotti, la differenza misurata e' quella di
un sistema che per l'80% si comporta come B. Il tetto si applica **solo ai
giocatori del piano**, perche' solo per loro e' stato calcolato: senza questa
restrizione un tetto potrebbe agire su un target del MILP anche con `piano`
vuoto, e il braccio di controllo non sarebbe piu' un controllo.

## Il tetto deve parlare del giocatore per cui viene usato

Difetto misurato l'8 settembre 2026, dopo la correzione precedente: un record
con `giocatore = "A0"` messo sotto la chiave `"A1"` veniva accettato, e
`_tetto_validato("A1", view)` restituiva `(17.0, "valido")`. Il consumatore si
fidava della chiave del dizionario e non leggeva mai l'identita' scritta dentro
il record; la fixture positiva dei test scriveva `"giocatore": "ignoto"`,
quindi nemmeno i test potevano accorgersene.

La chiave di validita' descrive lo **stato del mondo**, non il bersaglio: e' la
stessa per tutti i giocatori calcolati dallo stesso `StatoAsta`. Nessuna delle
sue componenti cambia se il record finisce sotto un altro nome. L'unica difesa
e' l'identita' scritta nel record, e va confrontata in forma canonica
(`identita_canonica`) perche' il cubo usa interi e il motore d'asta stringhe:
`6482` e `"6482"` sono lo stesso giocatore, `"A0"` e `"A1"` no. Un record senza
identita' e' respinto con ragione `senza_identita`, uno con identita' diversa
dalla chiave con `identita_diversa`.

## Il tetto economico non e' la stima puntuale

`indifferenza.classifica_curva` espone due numeri diversi e li chiama con nomi
diversi: `stima_tetto` e' il piu' alto prezzo con differenza media positiva,
scelto come massimo su k punti e quindi distorto verso l'alto;
`tetto_supportato` e' il piu' alto prezzo il cui intervallo sta interamente
sopra lo zero, ed e' `None` quando nessuno lo e'. `curva()` espone come
`tetto_economico` il secondo, o 0 se manca.

Il consumatore legge **solo** `tetto_economico`. Se il record porta anche il
blocco `classificazione`, il consumatore controlla che i due numeri siano
coerenti (`tetto_economico == tetto_supportato or 0`) e respinge come
`record_incoerente` un file in cui non lo sono — e' il caso del file gia'
salvato `data/l3/asta/tetti_2026-27.json`, prodotto da una versione precedente
di `curva()`, dove Mandas porta `tetto_economico = 19` con stato
`inconcludente`.

Uno zero non e' un dato mancante: `tetto_economico = 0` con uno stato ammesso
e' l'affermazione «nessun prezzo provato conviene», e produce un massimo di
offerta pari a zero, cioe' un passo. Un record senza il campo, o con il campo
nullo, non dice niente e viene respinto (`tetto_non_numerico`).

## Un tetto si verifica prima di usarlo

Difetto misurato dall'audit indipendente dell'8 settembre 2026
(`data/l3/audit2/livello3/RAPPORTO.md` §7): `_max_bid_for` restituiva
`float(self.tetti[pid])` senza nessun controllo. I tetti erano un dizionario
congelato — `scripts/l3_tetti.py` costruisce **un solo** `StatoAsta` (rose
vuote, budget 500, tutto il pool disponibile) e calcola tutte le curve da li' —
e `curva()` salva bensi' la sua `chiave_validita`, ma salvare una chiave non
impedisce di usare un tetto scaduto: nessuno la leggeva.

Quanto conta, misurato dall'audit sulla stessa asta: alla fotografia dei 120
lotti venduti la curva di Malen ricalcolata da' tetto economico **220** con
stato `verificato`, contro **110** con stato `inconcludente` dello stato
iniziale. Stesso giocatore, stesso file, un fattore 2. Il massimo legale nel
frattempo era sceso da 476 a 371.

Un tetto e' per costruzione una funzione dello stato d'asta completo, e ogni
martelletto puo' invalidarlo. Il consumatore verifica due gruppi di componenti.

**Osservabili dall'asta**, ricalcolate da `AuctionView` in
`chiave_stato_corrente()` con le stesse formule di
`indifferenza.chiave_di_validita`: nostro budget, nostra rosa, posti liberi per
ruolo, massimo legale, numero e impronta dei giocatori ancora disponibili,
impronta di rose e budget di tutti gli avversari (entrano nel ramo PASSO del
calcolo, che sceglie fra gli avversari capienti, e nel completamento di ogni
squadra).

**Non osservabili dall'asta**: impronta del cubo, scenari, repliche, seme,
calendario, tipo di completamento, regole della lega, e — se il produttore lo
dichiara — l'impronta dei listini. Il bot in asta non ha il cubo in mano,
quindi queste arrivano da `contesto_tetti`, che il chiamante dichiara alla
costruzione nella stessa forma della chiave, gia' in tipi JSON. Se
`contesto_tetti` manca o non porta i blocchi `cubo`, `esperimento` e `regole`,
**nessun tetto e' valido**: senza sapere su quale mondo si sta giocando quelle
componenti non sono verificabili, e un tetto non verificabile non entra.

Le regole del consumo, in ordine:

    altro giocatore         il record non dichiara la propria identita', o ne
                            dichiara una diversa dalla chiave sotto cui e'
                            stato riposto -> `senza_identita`,
                            `identita_diversa`
    obsoleto                lo stato decisionale corrente differisce da quello
                            che la chiave descrive -> ripiego `stato_cambiato`
    inconcludente           `stato` fuori da `stati_ammessi` (`verificato` e
                            `approssimato`, gli stessi che ammette
                            `l3_confronto_asta.py`) -> `stato_non_ammesso`
    completamento non
    ammesso                 `completamento.tipo` fuori da
                            `completamenti_ammessi`, o blocco assente ->
                            `completamento_non_ammesso`
    non verificabile        chiave assente o illeggibile, contesto assente o
                            incompleto, vista dello stato non ancora arrivata
                            -> `senza_chiave`, `senza_contesto`,
                            `contesto_incompleto`, `senza_vista`
    malformato              il record contraddice se stesso: massimo legale
                            diverso da quello della propria chiave, oppure
                            `tetto_economico` diverso dal `tetto_supportato`
                            della propria classificazione -> `record_incoerente`
    privo di senso          giocatore gia' venduto, o nostro reparto pieno
                            (`delta_a_prezzo` solleva `ValueError` in quel
                            caso: il consumatore non puo' restituire un numero
                            dove il produttore si ferma)

In tutti questi casi il bot **ripiega** sul tetto di B e conta il ripiego per
ragione in `ripieghi_per_ragione`. Non inventa un tetto: quando la verifica
fallisce non esiste nessun numero di indifferenza da usare.

La forma vecchia dei tetti, `player_id -> float`, non porta nessuna chiave e
quindi non e' verificabile: viene respinta con ragione `senza_chiave`. Il
consumatore accetta il risultato di `curva()` intero, cioe' un dizionario con
almeno `tetto_economico`, `stato`, `completamento` e `chiave_validita`.

## Tetto economico e massimo legale sono due quantita' distinte

Il tetto economico e' una stima: il prezzo oltre il quale comprare smette di
convenire. Il massimo legalmente offribile e' un vincolo d'asta: crediti meno
un credito per ogni altro posto ancora vuoto. Non sono la stessa cosa e non si
sommano: quando il tetto validato supera il massimo legale corrente **vince il
massimo legale**, e il morso e' contato in
`tetto_limitato_dal_massimo_legale`. `curva()` non dovrebbe produrre tetti
sopra il proprio tetto legale (scarta i prezzi che lo superano), ma il
consumatore non si fida del produttore: il vincolo si riapplica sullo stato in
cui l'offerta viene fatta davvero.

## Contatori: che cosa contano, misurato sul ledger

`piano_perso` contava `len(piano) - len(vivi)` con `vivi` i giocatori del piano
ancora in `view.pool`. Ma `auction.py:185` toglie dal pool **anche i giocatori
che compriamo noi**: nella replica 0 dei 20 «persi» dieci erano in rosa nostra.
Quel contatore e' stato sostituito da cinque categorie disgiunte, ricalcolate
dal ledger `view.sold` a ogni martelletto (ricalcolate, non incrementate, cosi'
l'invariante e' controllabile in ogni istante):

    piano_miei_prima     del piano, gia' nostri prima del primo ricalcolo
    piano_miei_dopo      del piano, comprati da noi dopo
    piano_ai_rivali      del piano, comprati dai rivali
    piano_disponibili    del piano, ancora in vendita
    piano_scartati_dal_ricalcolo   sottoinsieme del precedente: in vendita ma
                                   fuori dai target dopo l'ultimo ricalcolo

Invariante: le prime quattro sommano a `len(piano) - piano_fuori_asta`, dove
`piano_fuori_asta` sono i giocatori del piano che non compaiono nell'asta
(ne' nel pool, ne' nel ledger, ne' in rosa) al momento dell'avvio.
`piano_non_classificati` deve restare 0 e serve solo a far fallire il test se
l'invariante si rompe. Le categorie sono misurate sul **piano iniziale**, che
non cambia mai durante l'asta: nessun nome puo' essere contato due volte
perche' non esistono versioni successive del piano.

`crediti_sul_piano` e `crediti_persi_sul_piano` sono i prezzi battuti sui
giocatori del piano, rispettivamente da noi e dai rivali (nella replica
misurata: 96 crediti su 307 spesi).

## Contatori morti, rimossi

`fuori_piano` era irraggiungibile per costruzione: `_max_bid_for` e' chiamato
solo da `bot_b.py:139`, dentro `if pid in self.targets`. Misurato: 0 chiamate
fuori dai target in un'asta intera e 0 in tutte le 22 repliche gia' salvate.
`budget_tempo_s` era assegnato e mai letto in nessun punto del progetto, e la
docstring di classe descriveva un ripiego per tempo che non esisteva; con esso
sono spariti `tempo_speso` e l'involucro `bid()` che lo misurava (0,003 secondi
in tutta l'asta). `ripiego_q90` e' diventato `offerte_con_tetto_di_b`: conta
offerte, non giocatori, e per i non titolari il tetto non e' il q90.
"""
from __future__ import annotations

import hashlib
import json
import math

from ..models import ROLES, Player
from ..optimizer import greedy_roster, optimize_roster
from ..rules import MIN_SPEND_FRAC
from .base import AuctionView
from .bot_b import BBot

# Stati del confronto che producono un tetto utilizzabile. Sono gli stessi che
# `scripts/l3_confronto_asta.py` ammette: `inconcludente` significa che
# l'intervallo di confidenza attraversa lo zero a ogni prezzo provato, cioe'
# che il numero non distingue comprare da passare.
STATI_AMMESSI = ("verificato", "approssimato")

# Con quale procedura le rose su cui la curva e' stata misurata sono state
# completate. `assegnazione_per_priorita` e' un **surrogato**: non e' una
# continuazione competitiva dell'asta, assegna le rose per priorita' pagando
# il prezzo previsto. E' quello con cui i tetti del progetto sono stati
# prodotti; il suo scarto dal motore vero e' quantificato in
# `indifferenza.SCARTO_DAL_MOTORE`. Un completamento diverso e non dichiarato
# non e' confrontabile e viene respinto.
COMPLETAMENTI_AMMESSI = ("assegnazione_per_priorita",)

# Come il completamento ammesso va nominato ovunque il suo risultato venga
# esposto: chi legge un tetto deve sapere che dietro non c'e' un'asta.
ETICHETTA_COMPLETAMENTI = {
    "assegnazione_per_priorita": "surrogato (assegnazione_per_priorita)",
}


def etichetta_completamento(tipo: str) -> str:
    """Nome da mostrare per un tipo di completamento."""
    return ETICHETTA_COMPLETAMENTI.get(tipo, str(tipo))


# Blocchi della chiave che l'asta non puo' osservare da sola: senza di loro
# dichiarati dal chiamante non c'e' niente da confrontare.
BLOCCHI_CONTESTO_OBBLIGATORI = ("cubo", "esperimento", "regole")


def identita_canonica(giocatore) -> str:
    """Forma testuale unica dell'identificativo di un giocatore.

    Il cubo indicizza con interi (`6482`), il motore d'asta con stringhe
    (`"6482"`), il JSON dei tetti con chiavi di dizionario, che sono sempre
    stringhe. Senza una forma sola lo stesso giocatore ha piu' nomi, e il
    confronto fra la chiave di un dizionario e l'identita' scritta nel record
    diventa una lotteria fra `6482 == "6482"` (falso) e `"6482" == "6482"`
    (vero).

    I booleani sono rifiutati anche se `int` li accetterebbe (`True` vale 1), e
    i float pure: `6482.0` sarebbe ambiguo appena qualcuno lo scrive con un
    altro numero di decimali. Chi ha un identificativo di un altro tipo lo
    converte prima, dichiarando come."""
    if giocatore is None or isinstance(giocatore, bool):
        raise ValueError(f"identificativo non ammesso: {giocatore!r}")
    if isinstance(giocatore, int):
        return str(giocatore)
    if isinstance(giocatore, str):
        testo = giocatore.strip()
        if not testo:
            raise ValueError("identificativo vuoto")
        return testo
    raise ValueError(f"identificativo non ammesso: {giocatore!r}")


def _identita(giocatore):
    """Come `identita_canonica`, ma restituisce `None` invece di sollevare.

    Il consumatore di un tetto non puo' esplodere su un file malformato: deve
    respingere il record e contare il ripiego con la sua ragione."""
    try:
        return identita_canonica(giocatore)
    except ValueError:
        return None


def _sha(testo: str, n: int = 12) -> str:
    return hashlib.sha256(testo.encode("utf-8")).hexdigest()[:n]


def _canonico(x) -> str:
    """Forma testuale confrontabile. Tuple e liste danno lo stesso risultato,
    cosi' un contesto letto da JSON combacia con uno scritto a mano."""
    return json.dumps(x, sort_keys=True, default=str)


def _numero_finito(x) -> bool:
    return (isinstance(x, (int, float)) and not isinstance(x, bool)
            and math.isfinite(float(x)))


class BBotCoerente(BBot):
    """Bot B con la ripianificazione allineata al piano scelto offline.

    Unica differenza rispetto a `BBot`: `_replan` passa `min_spend`, la stessa
    soglia usata da `montecarlo.choose_objective` e da `f13_validate_plan`.
    Serve a separare l'effetto di quell'incoerenza da tutto il resto.

    Il ricalcolo e' scomposto in tre pezzi (`_contesto_milp`, `_risolvi_milp`,
    `_applica_soluzione`) perche' il Livello 3 possa cambiare **solo** il primo
    senza duplicare il resto: la sequenza di chiamate a `optimize_roster` e i
    valori che ne escono restano quelli di prima."""

    name = "B+"

    def __init__(self, rng, predictions, replan_every: int = 10,
                 objective: dict | None = None, peso_ombra: float = 0.5,
                 min_spend_frac: float = MIN_SPEND_FRAC):
        super().__init__(rng, predictions, replan_every, objective, peso_ombra)
        self.min_spend_frac = float(min_spend_frac)
        # quale dei quattro tentativi ha risolto, dall'inizio dell'asta: e' il
        # registro dei casi in cui il pavimento di spesa (o la quota d'attacco)
        # e' risultato impossibile e quale ripiego e' stato scelto.
        self.conta_milp = {"soglia_e_attacco": 0, "solo_soglia": 0,
                           "solo_attacco": 0, "nessun_vincolo": 0,
                           "greedy": 0, "pavimento_violato": 0}
        self.ultimo_ricalcolo: dict = {}

    # ---------- ricalcolo, in tre pezzi separabili ----------
    def _contesto_milp(self, view: AuctionView, heat: float) -> dict:
        """Tutti gli ingressi del MILP in un dizionario, prima di risolvere.

        `posseduti` sono i giocatori gia' in rosa (costo 0, `x = 1`), `forzati`
        gli eventuali acquisti obbligati: qui e' sempre vuoto, il Livello 3 lo
        riempie. `fixed` e' l'unione, cioe' quello che va al solutore."""
        candidates = dict(view.pool)
        posseduti = {pid: Player(pid, pid, r, "")
                     for r, ids in view.me.roster.items() for pid, _ in ids}
        prices = {pid: max(1.0, self._q(pid, "q50") * heat) for pid in candidates}
        values = {pid: self._q(pid, "value", 0.0)
                  for pid in list(candidates) + list(posseduti)}
        values_up = {pid: self._q(pid, "value_up", values[pid]) for pid in values}
        forced = None
        if self.objective.get("attack_share"):
            spent_a = sum(pr for _, pr in view.me.roster.get("A", []))
            lo_s, hi_s = self.objective["attack_share"]
            lo = max(0.0, lo_s * view.budget_total - spent_a)
            hi = max(lo, hi_s * view.budget_total - spent_a)
            forced = {"A": (lo, hi)}
        # la soglia si applica al budget ANCORA da spendere: quello gia' speso
        # e' fuori discussione, e i posti gia' riempiti non tornano sul mercato
        speso = view.budget_total - view.me.budget
        soglia = max(0.0, self.min_spend_frac * view.budget_total - speso)
        return {"candidates": candidates, "posseduti": posseduti,
                "forzati": {}, "fixed": dict(posseduti),
                "prices": prices, "values": values, "values_up": values_up,
                "forced": forced, "soglia": soglia,
                "soglia_richiesta": soglia, "costo_forzati": 0.0,
                "budget": view.me.budget}

    def _risolvi_milp(self, view: AuctionView, ctx: dict):
        """I quattro tentativi, in ordine: si molla `attack_share` prima della
        soglia di spesa. Ritorna (soluzione, nome del tentativo)."""
        lam = self.objective.get("lam", 0.0)
        tentativi = (
            ("soglia_e_attacco", {"forced_spend": ctx["forced"],
                                  "min_spend": ctx["soglia"]}),
            ("solo_soglia", {"forced_spend": None, "min_spend": ctx["soglia"]}),
            ("solo_attacco", {"forced_spend": ctx["forced"], "min_spend": None}),
            ("nessun_vincolo", {"forced_spend": None, "min_spend": None}),
        )
        for nome, kw in tentativi:
            sol = optimize_roster(ctx["candidates"], ctx["prices"], ctx["values"],
                                  view.quotas, ctx["budget"], fixed=ctx["fixed"],
                                  values_up=ctx["values_up"], lam=lam,
                                  time_limit=5, **kw)
            if sol is not None:
                return sol, nome
        return None, None

    def _ripiego(self, view: AuctionView, heat: float, ctx: dict):
        """Ultimo tentativo prima del greedy. B+ non ne ha: solo il Livello 3,
        che qui rinuncia agli acquisti obbligati."""
        return ctx, None, None

    def _soglia_effettiva(self, view: AuctionView, ctx: dict) -> float:
        """La soglia che `optimize_roster` applica davvero, sul totale.

        Replica il taglio interno del solutore (`soglia = min(min_spend,
        budget - max(0, slot_da_riempire - 1))`, con `slot_da_riempire =
        quote piene - len(fixed)`) e ci riaggiunge il costo degli acquisti
        obbligati, che nel solutore vale 0 perche' sono in `fixed`. Serve a
        rendere il pavimento verificabile da fuori: senza questa riga un test
        sul pavimento dovrebbe indovinare il taglio."""
        if not ctx["soglia"]:
            return ctx["costo_forzati"]
        slot_da_riempire = sum(view.quotas[r] for r in ROLES) - len(ctx["fixed"])
        tagliata = min(float(ctx["soglia"]),
                       ctx["budget"] - max(0, slot_da_riempire - 1))
        return ctx["costo_forzati"] + max(0.0, tagliata)

    def _applica_soluzione(self, view: AuctionView, sol: dict, ctx: dict):
        """Dalla soluzione ai target. Si sottraggono i **posseduti**, non tutto
        `fixed`: gli acquisti obbligati del Livello 3 sono target a tutti gli
        effetti, e i loro titolari sono quelli che ha scelto il MILP."""
        posseduti = ctx["posseduti"]
        self.module = sol.get("module", "4-4-2")
        self.targets = ({pid for ids in sol["roster"].values() for pid in ids}
                        - set(posseduti))
        self.starter_targets = set(sol.get("starters") or set()) - set(posseduti)
        # per il prezzo-ombra: miglior valore di ruolo FUORI piano
        self._role_of = {pid: p.role for pid, p in view.pool.items()}
        self._best_alt_value = {}
        for r in view.quotas:
            alts = [self._q(pid, "value", 0.0) for pid, p in view.pool.items()
                    if p.role == r and pid not in self.targets]
            self._best_alt_value[r] = max(alts) if alts else 0.0

    def _replan(self, view: AuctionView):
        self.hammers_since_replan = 0
        heat = self.market_heat()
        self._heat_at_replan = heat
        ctx = self._contesto_milp(view, heat)
        sol, tentativo = self._risolvi_milp(view, ctx)
        if sol is None:
            ctx, sol, tentativo = self._ripiego(view, heat, ctx)
        if sol is None:
            quotas_left = {r: view.quotas[r] - len(view.me.roster[r])
                           for r in view.quotas}
            sol = greedy_roster(ctx["candidates"], ctx["prices"], ctx["values"],
                                quotas_left, view.me.budget)
            tentativo = "greedy"
        self.conta_milp[tentativo] += 1
        self._applica_soluzione(view, sol, ctx)
        self._registra_ricalcolo(view, ctx, tentativo)

    def _registra_ricalcolo(self, view: AuctionView, ctx: dict, tentativo: str):
        """Diagnostica dell'ultimo ricalcolo, con il pavimento verificabile.

        `costo_previsto` e' quanto il piano appena calcolato prevede di
        spendere ai prezzi correnti (i posseduti valgono 0: sono gia' pagati).
        `pavimento_rispettato` confronta quel costo con la soglia effettiva; e'
        significativo solo quando il tentativo che ha risolto usava la soglia,
        e resta `None` altrimenti."""
        costo = sum(ctx["prices"].get(pid, 1.0) for pid in self.targets)
        eff = self._soglia_effettiva(view, ctx)
        con_soglia = tentativo in ("soglia_e_attacco", "solo_soglia")
        ok = (costo + 1e-6 >= eff) if con_soglia else None
        if ok is False:
            self.conta_milp["pavimento_violato"] += 1
        self.ultimo_ricalcolo = {
            "tentativo": tentativo,
            "soglia_richiesta": round(ctx["soglia_richiesta"], 6),
            "soglia_effettiva": round(eff, 6),
            "costo_previsto": round(costo, 6),
            "costo_forzati": round(ctx["costo_forzati"], 6),
            "budget_residuo": view.me.budget,
            "pavimento_rispettato": ok,
        }

    def rapporto(self) -> dict:
        return {"milp": dict(self.conta_milp),
                "ultimo_ricalcolo": dict(self.ultimo_ricalcolo)}


class BotL3(BBotCoerente):
    """Piano dalla ricerca del Livello 3; tetto dal prezzo di indifferenza.

    `piano` e' l'insieme dei giocatori scelti prima dell'asta dalla ricerca su
    candidate, nella forma `player_id -> {...}`. I giocatori del piano ancora
    in vendita entrano nel MILP come acquisti obbligati, quindi la soluzione
    che ne esce rispetta gia' quote, budget, `attack_share` e pavimento di
    spesa: non c'e' nessun passo che riscrive i target dopo il solutore.

    Che il piano entri come acquisto forzato e' una **scelta di politica, non
    una prova di ottimalita' su P(1 posto)**: corregge la contabilita' (quote,
    budget, `attack_share` e pavimento di spesa tornano imposti dal solutore,
    che prima l'ancoraggio scavalcava) e rende il braccio attribuibile a una
    dimensione sola, ma nessuna misura qui dimostra che obbligare il piano
    massimizzi la probabilita' di arrivare primi. Il MILP e' esatto sul
    problema che gli si passa; il problema che gli si passa e' una scelta, e
    l'obiettivo del MILP (`value` con `lam` e `attack_share`) non e' P(1
    posto). Non chiamare esatto l'intero comportamento perche' una sua
    sottoparte usa una MILP.

    `tetti` e' una mappa giocatore -> risultato di `indifferenza.curva()`,
    usata solo per i giocatori del piano e solo se `usa_indifferenza`. Ogni
    tetto viene **verificato** contro lo stato d'asta corrente prima dell'uso
    (vedi la docstring del modulo); quando manca, non e' valido o non e'
    verificabile si usa il tetto di B e si conta il ripiego con la sua ragione.

    `contesto_tetti` dichiara le componenti della chiave che l'asta non puo'
    osservare — `cubo`, `esperimento`, `regole`, ed eventualmente `listini` —
    nella stessa forma che `indifferenza.chiave_di_validita` produce e in tipi
    JSON. Senza di esso nessun tetto e' valido."""

    name = "L3"

    def __init__(self, rng, predictions, piano: dict | None = None,
                 tetti: dict | None = None, replan_every: int = 10,
                 objective: dict | None = None, peso_ombra: float = 0.5,
                 min_spend_frac: float = MIN_SPEND_FRAC,
                 usa_indifferenza: bool = True,
                 contesto_tetti: dict | None = None,
                 stati_ammessi: tuple = STATI_AMMESSI,
                 completamenti_ammessi: tuple = COMPLETAMENTI_AMMESSI):
        super().__init__(rng, predictions, replan_every, objective, peso_ombra,
                         min_spend_frac)
        self.piano = dict(piano or {})
        self.tetti = dict(tetti or {})
        self.usa_indifferenza = bool(usa_indifferenza)
        self.contesto_tetti = dict(contesto_tetti) if contesto_tetti else {}
        self.stati_ammessi = tuple(stati_ammessi)
        self.completamenti_ammessi = tuple(completamenti_ammessi)
        # ultima vista del tavolo, l'unico stato su cui si puo' verificare un
        # tetto. Resta `None` finche' il motore non chiama il bot: un tetto
        # chiesto prima non e' verificabile e viene respinto.
        self._vista: AuctionView | None = None
        # ripieghi per ragione: il denominatore dell'esperimento. Fuori da
        # `self.conta` perche' quel dizionario e' piatto e viene copiato con
        # `dict(...)` dalle sonde: un sotto-dizionario verrebbe condiviso per
        # riferimento e tutte le fotografie mostrerebbero l'ultimo valore.
        self.ripieghi_per_ragione: dict[str, int] = {}
        self.ultimo_ripiego: dict = {}
        self.conta = {
            # offerte: contano chiamate a `_max_bid_for`, non giocatori
            "offerte_con_tetto_indifferenza": 0,
            "offerte_con_tetto_di_b": 0,
            # tetti chiesti per un giocatore del piano e non usati: e' il
            # numero di ripieghi, la somma di `ripieghi_per_ragione`
            "tetti_respinti": 0,
            # quante volte il massimo legale ha morso sul tetto economico
            "tetto_limitato_dal_massimo_legale": 0,
            # ricalcoli
            "ricalcoli_con_piano": 0,
            "piano_forzati_nel_milp": 0,        # ultimo ricalcolo
            "piano_troncati_dal_vincolo": 0,    # ultimo ricalcolo
            "piano_ceduto_al_pavimento": 0,     # ultimo ricalcolo
            "piano_ceduto_al_pavimento_totale": 0,   # cumulativo
            "piano_scartato_per_infattibilita": 0,   # cumulativo
            # riconciliazione col ledger, ricalcolata a ogni martelletto
            "piano_fuori_asta": 0,
            "piano_miei_prima": 0,
            "piano_miei_dopo": 0,
            "piano_ai_rivali": 0,
            "piano_disponibili": 0,
            "piano_scartati_dal_ricalcolo": 0,
            "piano_non_classificati": 0,
            "crediti_sul_piano": 0,
            "crediti_persi_sul_piano": 0,
        }
        # universo di riconciliazione: fissato all'avvio dell'asta, cosi' i
        # giocatori del piano che nell'asta non ci sono proprio non falsano
        # l'invariante. Senza `start_auction` (prove unitarie) vale il piano.
        self._piano_noto = set(self.piano)
        self._vendite_al_via = 0

    # ---------- avvio ----------
    def start_auction(self, view: AuctionView):
        self._vista = view
        self._marca_inizio(view)
        super().start_auction(view)

    def _marca_inizio(self, view: AuctionView):
        venduti = {pid for pid, _, _ in view.sold}
        miei = {pid for ids in view.me.roster.values() for pid, _ in ids}
        self._piano_noto = {pid for pid in self.piano
                            if pid in view.pool or pid in venduti or pid in miei}
        self.conta["piano_fuori_asta"] = len(self.piano) - len(self._piano_noto)
        # martelletti gia' battuti quando entriamo: separa i giocatori del piano
        # che erano gia' nostri da quelli comprati dopo il primo ricalcolo
        self._vendite_al_via = len(view.sold)

    # ---------- selezione: il piano entra come vincolo, non come punteggio ----
    def _forzati_ammissibili(self, view: AuctionView, ctx: dict) -> list[str]:
        """I giocatori del piano ancora in vendita che ci stanno davvero.

        Due tagli, in quest'ordine, entrambi dal fondo della lista ordinata per
        `(-value, player_id)` — il pareggio sull'identificativo evita che
        l'ordine dipenda dall'hash delle stringhe, che cambia fra processi.

        1. **quote e budget**: si tengono i piu' preziosi finche' c'e' un posto
           di ruolo libero e finche' resta un credito per ogni altro posto
           ancora vuoto. Senza questo taglio il MILP diventerebbe infattibile e
           il piano verrebbe abbandonato tutto insieme.
        2. **pavimento di spesa**: i vincoli economici vengono **prima** del
           piano. Se il piano occupa tanti posti da rendere irraggiungibile la
           soglia, si cedono giocatori del piano — dal meno prezioso — finche'
           la soglia torna raggiungibile, e si conta quanti se ne sono ceduti.

        Perche' il secondo taglio esiste, misurato. Il piano dell'11 settembre
        costa 499,9 crediti su 500 al `q50`, cioe' impegna tutti e 25 gli slot
        e tutto il budget. Appena un rivale ne porta via un pezzo, i crediti
        restano ma i posti liberi per spenderli no: senza questo taglio il
        pavimento risultava impossibile in **30 ricalcoli su 53** di un'asta
        intera e il braccio L3 finiva con 144 crediti in cassa (spesa 356
        contro 419 di B+). Sarebbe stato di nuovo un braccio che differisce da
        B+ per due cose insieme, cioe' il difetto che questa correzione doveva
        togliere."""
        vivi = sorted([pid for pid in self.piano if pid in view.pool],
                      key=lambda p: (-self._q(p, "value", 0.0), p))
        residue = {r: view.quotas[r] - len(view.me.roster[r]) for r in view.quotas}
        scelti: list[str] = []
        costo = 0.0
        for pid in vivi:
            r = view.pool[pid].role
            if residue.get(r, 0) <= 0:
                continue
            vuoti_dopo = sum(residue.values()) - 1
            if costo + ctx["prices"][pid] + vuoti_dopo > view.me.budget:
                continue
            scelti.append(pid)
            costo += ctx["prices"][pid]
            residue[r] -= 1
        troncati = len(vivi) - len(scelti)
        ceduti = 0
        while scelti and not self._pavimento_raggiungibile(view, ctx, scelti):
            scelti.pop()          # la lista e' ordinata per valore decrescente
            ceduti += 1
        self.conta["piano_forzati_nel_milp"] = len(scelti)
        self.conta["piano_troncati_dal_vincolo"] = troncati
        self.conta["piano_ceduto_al_pavimento"] = ceduti
        self.conta["piano_ceduto_al_pavimento_totale"] += ceduti
        return scelti

    def _pavimento_raggiungibile(self, view: AuctionView, ctx: dict,
                                 forzati: list[str]) -> bool:
        """La soglia di spesa e' ancora raggiungibile con questi obbligati?

        Limite superiore esatto della spesa pianificabile: costo degli
        obbligati piu' i prezzi piu' alti disponibili nei posti che restano,
        il tutto tagliato dal budget. Ignora il vincolo del modulo, che non
        tocca i costi, quindi e' un limite superiore vero: se sta sotto la
        soglia il pavimento e' **dimostrabilmente** impossibile e non ha senso
        chiamare il solutore per scoprirlo. Il confronto usa la soglia gia'
        tagliata come la taglia `optimize_roster`."""
        soglia = ctx["soglia_richiesta"]
        if soglia <= 0:
            return True
        prezzi = ctx["prices"]
        costo = sum(prezzi[pid] for pid in forzati)
        budget_eff = view.me.budget - costo
        liberi = {r: view.quotas[r] - len(view.me.roster[r]) for r in view.quotas}
        for pid in forzati:
            liberi[view.pool[pid].role] -= 1
        slot_da_riempire = (sum(view.quotas[r] for r in ROLES)
                            - len(ctx["posseduti"]) - len(forzati))
        tagliata = min(soglia - costo,
                       budget_eff - max(0, slot_da_riempire - 1))
        if tagliata <= 0:
            return True
        esclusi = set(forzati)
        massimo = 0.0
        for r, n in liberi.items():
            if n <= 0:
                continue
            presi = 0
            for prezzo, pid in ctx["prezzi_per_ruolo"][r]:
                if pid in esclusi:
                    continue
                massimo += prezzo
                presi += 1
                if presi >= n:
                    break
        return min(massimo, budget_eff) + 1e-9 >= tagliata

    def _contesto_milp(self, view: AuctionView, heat: float) -> dict:
        ctx = super()._contesto_milp(view, heat)
        if not self.piano:
            return ctx
        self.conta["ricalcoli_con_piano"] += 1
        # prezzi disponibili per ruolo, dal piu' caro: servono al limite
        # superiore di spesa che decide se il pavimento e' ancora raggiungibile
        per_ruolo: dict[str, list] = {r: [] for r in view.quotas}
        for pid, p in view.pool.items():
            per_ruolo.setdefault(p.role, []).append((ctx["prices"][pid], pid))
        for r in per_ruolo:
            per_ruolo[r].sort(key=lambda t: (-t[0], t[1]))
        ctx["prezzi_per_ruolo"] = per_ruolo
        forzati = self._forzati_ammissibili(view, ctx)
        if not forzati:
            return ctx
        costo = sum(ctx["prices"][pid] for pid in forzati)
        # `optimize_roster` mette a costo 0 tutto quello che sta in `fixed` e
        # somma il vincolo di budget sui soli `candidates`: togliendo `costo`
        # dal budget e dalla soglia si ottiene esattamente il problema con
        # quei giocatori vincolati a `x = 1` al loro prezzo pieno.
        ctx["forzati"] = {pid: view.pool[pid] for pid in forzati}
        ctx["fixed"] = {**ctx["posseduti"], **ctx["forzati"]}
        ctx["costo_forzati"] = costo
        ctx["budget"] = max(0.0, view.me.budget - costo)
        ctx["soglia"] = max(0.0, ctx["soglia"] - costo)
        if ctx["forced"] is not None:
            # stessa compensazione sulla quota d'attacco: il costo degli
            # attaccanti obbligati non compare piu' nella somma del solutore
            costo_a = sum(ctx["prices"][pid] for pid in forzati
                          if view.pool[pid].role == "A")
            lo, hi = ctx["forced"]["A"]
            lo = max(0.0, lo - costo_a)
            ctx["forced"] = {"A": (lo, max(lo, hi - costo_a))}
        return ctx

    def _ripiego(self, view: AuctionView, heat: float, ctx: dict):
        """Se il piano rende il MILP infattibile lo si abbandona, e si dice."""
        if not ctx["forzati"]:
            return ctx, None, None
        self.conta["piano_scartato_per_infattibilita"] += 1
        self.conta["piano_forzati_nel_milp"] = 0
        self.conta["piano_ceduto_al_pavimento"] = 0
        self.conta["piano_troncati_dal_vincolo"] = len(
            [pid for pid in self.piano if pid in view.pool])
        base = BBotCoerente._contesto_milp(self, view, heat)
        sol, tentativo = self._risolvi_milp(view, base)
        return base, sol, tentativo

    def _replan(self, view: AuctionView):
        self._vista = view
        super()._replan(view)
        self._riconcilia(view)

    # ---------- massimi di offerta ----------
    def bid(self, view: AuctionView, player: Player, price: int, leader):
        """Solo per registrare la vista: la decisione resta quella di B.

        `_max_bid_for` non riceve la vista (firma di `bot_b.py:139`) ma un
        tetto si verifica soltanto contro uno stato d'asta. Qui si annota lo
        stato e si delega senza toccare nulla: la parita' con B+ a intervento
        spento resta martelletto per martelletto."""
        self._vista = view
        return super().bid(view, player, price, leader)

    def chiave_stato_corrente(self, view: AuctionView) -> dict:
        """La parte osservabile della chiave di validita', dallo stato attuale.

        Stesse formule e stessi nomi di
        `indifferenza.chiave_di_validita`, blocco `stato_decisionale`: e' il
        lato consumatore di quel contratto, e
        `tests/test_bot_l3_tetti.py::test_la_chiave_del_bot_coincide_con_quella_di_indifferenza`
        lo tiene incollato al produttore. Gli avversari sono identificati dal
        loro `team_id`: chi calcola i tetti deve costruire `StatoAsta.avversari`
        con le stesse chiavi, altrimenti l'impronta non combacia mai e ogni
        tetto viene respinto (degrado in sicurezza, non uso silenzioso)."""
        quote = view.quotas
        rosa = {r: sorted(str(pid) for pid, _ in view.me.roster.get(r, []))
                for r in quote}
        liberi = {r: quote[r] - len(view.me.roster.get(r, [])) for r in quote}
        avversari = {t.team_id: {
            "rosa": {r: sorted(str(pid) for pid, _ in t.roster.get(r, []))
                     for r in quote},
            "budget": round(float(t.budget), 6)} for t in view.others}
        return {
            "nostro_budget": float(view.me.budget),
            "nostra_rosa": rosa,
            "posti_liberi": liberi,
            "massimo_legale": self._massimo_legale(view),
            "n_disponibili": len(view.pool),
            "impronta_disponibili": _sha(
                "|".join(sorted(map(str, view.pool))), 12),
            "impronta_avversari": _sha(_canonico(avversari), 12),
        }

    def _massimo_legale(self, view: AuctionView) -> int:
        """Massimo offribile: crediti meno un credito per ogni altro posto
        vuoto. Stessa formula di `TeamState.max_bid` e di
        `StatoAsta.max_legale`, con lo stesso taglio a zero della seconda."""
        vuoti = sum(view.quotas[r] - len(view.me.roster.get(r, []))
                    for r in view.quotas)
        return int(max(0, view.me.budget - max(0, vuoti - 1)))

    def _tetto_validato(self, pid: str, view: AuctionView | None):
        """`(tetto, "valido")` se il tetto vale ancora, `(None, ragione)` se no.

        L'ordine dei controlli va dal piu' economico al piu' specifico, e ogni
        uscita porta la ragione che verra' contata: sono quelle che rendono
        leggibile «quanto spesso il braccio L3+I si e' comportato come B»."""
        if view is None:
            return None, "senza_vista"
        rec = self.tetti.get(pid)
        if rec is None:
            # `_max_bid_for` filtra gia' su `pid in self.tetti`: questa uscita
            # serve ai chiamanti esterni (le sonde dei test la usano per
            # chiedere «questo record sarebbe valido?»)
            return None, "assente"
        if isinstance(rec, (int, float)) and not isinstance(rec, bool):
            # forma vecchia `player_id -> float`: nessuna chiave, nessuna
            # verifica possibile
            return None, "senza_chiave"
        if not isinstance(rec, dict):
            return None, "non_interpretabile"
        # identita': la chiave del dizionario non e' una prova. Un record e'
        # una funzione di UN giocatore, e la chiave di validita' descrive lo
        # stato del mondo, che e' identico per tutti: se il record finisse
        # sotto un altro nome nessuna delle altre verifiche se ne accorgerebbe.
        atteso_id = _identita(pid)
        dichiarata = _identita(rec.get("giocatore"))
        if dichiarata is None:
            return None, "senza_identita"
        if atteso_id is None or dichiarata != atteso_id:
            return None, "identita_diversa"
        tetto = rec.get("tetto_economico")
        if not _numero_finito(tetto):
            return None, "tetto_non_numerico"
        # il numero usato come cap e' `tetto_economico`, cioe' il prezzo il cui
        # intervallo esclude lo zero. `stima_tetto` e' un'altra quantita' (il
        # massimo dei delta positivi, distorto verso l'alto) e non entra mai.
        # Se il record porta la classificazione, i due devono combaciare.
        classificazione = rec.get("classificazione")
        if isinstance(classificazione, dict) and (
                "tetto_supportato" in classificazione):
            supportato = classificazione.get("tetto_supportato")
            if float(tetto) != float(supportato or 0):
                return None, "record_incoerente"
        if rec.get("stato") not in self.stati_ammessi:
            return None, "stato_non_ammesso"
        completamento = rec.get("completamento")
        if (not isinstance(completamento, dict)
                or completamento.get("tipo") not in self.completamenti_ammessi):
            return None, "completamento_non_ammesso"
        chiave = rec.get("chiave_validita")
        if not isinstance(chiave, dict):
            return None, "senza_chiave"
        if not self.contesto_tetti:
            return None, "senza_contesto"
        for blocco in BLOCCHI_CONTESTO_OBBLIGATORI:
            if blocco not in self.contesto_tetti:
                return None, "contesto_incompleto"
        for blocco, atteso in self.contesto_tetti.items():
            if _canonico(chiave.get(blocco)) != _canonico(atteso):
                return None, "contesto_diverso"
        dichiarato = chiave.get("stato_decisionale")
        if not isinstance(dichiarato, dict):
            return None, "chiave_incompleta"
        if pid not in view.pool:
            return None, "gia_venduto"
        ruolo = view.pool[pid].role
        if view.quotas.get(ruolo, 0) - len(view.me.roster.get(ruolo, [])) <= 0:
            # il reparto e' pieno: il giocatore non e' piu' comprabile e il
            # produttore stesso (`delta_a_prezzo`) solleva `ValueError` qui
            return None, "reparto_pieno"
        legale_dichiarato = rec.get("massimo_legale")
        if (legale_dichiarato is not None
                and _canonico(legale_dichiarato)
                != _canonico(dichiarato.get("massimo_legale"))):
            # il record contraddice la propria chiave: malformato, non scaduto
            return None, "record_incoerente"
        if _canonico(dichiarato) != _canonico(self.chiave_stato_corrente(view)):
            return None, "stato_cambiato"
        return float(tetto), "valido"

    def _registra_ripiego(self, pid: str, ragione: str, view) -> None:
        self.conta["tetti_respinti"] += 1
        self.ripieghi_per_ragione[ragione] = (
            self.ripieghi_per_ragione.get(ragione, 0) + 1)
        rec = self.tetti.get(pid)
        self.ultimo_ripiego = {
            "giocatore": pid,
            "ragione": ragione,
            "stato": rec.get("stato") if isinstance(rec, dict) else None,
            "budget_residuo": None if view is None else view.me.budget,
            "massimo_legale": (None if view is None
                               else self._massimo_legale(view)),
        }

    def _max_bid_for(self, pid: str) -> float:
        if self.usa_indifferenza and pid in self.piano and pid in self.tetti:
            tetto, ragione = self._tetto_validato(pid, self._vista)
            if tetto is not None:
                # il tetto economico e' una stima, il massimo legale un vincolo
                # d'asta: restano distinti e vince sempre il secondo
                legale = float(self._massimo_legale(self._vista))
                if tetto > legale:
                    self.conta["tetto_limitato_dal_massimo_legale"] += 1
                    tetto = legale
                self.conta["offerte_con_tetto_indifferenza"] += 1
                return tetto
            self._registra_ripiego(pid, ragione, self._vista)
        self.conta["offerte_con_tetto_di_b"] += 1
        return super()._max_bid_for(pid)

    # ---------- riconciliazione col ledger ----------
    def on_hammer(self, view: AuctionView, player: Player, price: int, winner):
        self._vista = view
        super().on_hammer(view, player, price, winner)
        self._riconcilia(view)

    def _riconcilia(self, view: AuctionView):
        """Dove sta ogni giocatore del piano iniziale, adesso.

        Ricalcolo completo, non incremento: l'invariante
        `miei_prima + miei_dopo + ai_rivali + disponibili + non_classificati
        == len(piano) - piano_fuori_asta` deve valere a ogni martelletto, e un
        contatore incrementale non permetterebbe di controllarlo."""
        if not self.piano:
            return
        indice, prezzo, proprietario = {}, {}, {}
        for i, (pid, tid, pr) in enumerate(view.sold):
            indice[pid] = i
            prezzo[pid] = pr
            proprietario[pid] = tid
        miei = {pid for ids in view.me.roster.values() for pid, _ in ids}
        c = self.conta
        for k in ("piano_miei_prima", "piano_miei_dopo", "piano_ai_rivali",
                  "piano_disponibili", "piano_scartati_dal_ricalcolo",
                  "piano_non_classificati", "crediti_sul_piano",
                  "crediti_persi_sul_piano"):
            c[k] = 0
        for pid in self._piano_noto:
            if pid in miei:
                if indice.get(pid, -1) < self._vendite_al_via:
                    c["piano_miei_prima"] += 1
                else:
                    c["piano_miei_dopo"] += 1
                c["crediti_sul_piano"] += prezzo.get(pid, 0)
            elif pid in proprietario:
                c["piano_ai_rivali"] += 1
                c["crediti_persi_sul_piano"] += prezzo.get(pid, 0)
            elif pid in view.pool:
                c["piano_disponibili"] += 1
                if pid not in self.targets:
                    c["piano_scartati_dal_ricalcolo"] += 1
            else:
                c["piano_non_classificati"] += 1

    def rapporto(self) -> dict:
        # denominatore: OFFERTE, cioe' chiamate a `_max_bid_for`, non lotti ne'
        # giocatori. Il nome lo dice per non farlo leggere come un tasso di uso.
        tot = (self.conta["offerte_con_tetto_indifferenza"]
               + self.conta["offerte_con_tetto_di_b"])
        return {**self.conta,
                "quota_offerte_con_tetto_indifferenza":
                    (self.conta["offerte_con_tetto_indifferenza"] / tot
                     if tot else 0.0),
                "giocatori_nel_piano": len(self.piano),
                "giocatori_con_tetto": len(self.tetti),
                # perche' i tetti non sono entrati: senza questo, «il braccio
                # L3+I coincide con L3» resterebbe senza spiegazione, che e'
                # esattamente com'e' andato il run gia' eseguito
                "ripieghi_per_ragione": dict(self.ripieghi_per_ragione),
                "ultimo_ripiego": dict(self.ultimo_ripiego),
                "contesto_tetti_dichiarato": sorted(self.contesto_tetti),
                # come si chiama la procedura che ha prodotto le rose su cui i
                # tetti sono stati misurati: e' un surrogato, non un'asta
                "completamenti_ammessi": [etichetta_completamento(t)
                                          for t in self.completamenti_ammessi],
                "milp": dict(self.conta_milp),
                "ultimo_ricalcolo": dict(self.ultimo_ricalcolo)}
