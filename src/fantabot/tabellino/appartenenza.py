"""Appartenenza di un giocatore a un club a una data precisa.

## Perche' questo modulo esiste

Il panel del Livello 2 aveva bisogno di rispondere a una sola domanda:
«a questa data, questo giocatore era tesserato per questo club?». Prima non lo
faceva. La funzione `_in_rosa()` di `scripts/l2_costruisci_panel.py` provava a
rispondere guardando se il giocatore compariva fra i convocati di quel club
nella stessa **meta' di stagione** (`giornata > 19`), e falliva per due motivi
indipendenti, entrambi dimostrati:

1. la colonna `club_id` non arrivava mai fino a quella funzione, quindi la
   guardia in testa restituiva `False` su tutte le 124.184 righe dei cinque
   panel prodotti;
2. anche se fosse arrivata, la meta' di stagione **non e' una partizione
   temporale**: nello storico 41 partite su 3.040 (1,35%) distano piu' di tre
   giorni dalla mediana delle date della loro giornata, con casi fino a 185
   giorni, e in 19 casi una giornata si accavalla con la successiva. Le
   giornate 19 e 20 del 2021-22 contengono partite giocate ad aprile e maggio
   2022, cioe' dopo il mercato di gennaio. Qualunque criterio basato sulla
   giornata e' sbagliato per costruzione.

Per questo qui si ragiona **solo per date**. La giornata non compare mai.

## Che cosa costruisce

Una tabella di intervalli `(tm_player_id, club_id, dal, al, fonte)`: dal giorno
`dal` compreso al giorno `al` escluso, quel giocatore risultava tesserato per
quel club. Gli intervalli vengono da tre fonti, nell'ordine di solidita' fissato
dal contratto degli stati (`reports/CRITERI_L2_L3.md`, sezione 7.1):

  `trasferimenti`   la successione dei trasferimenti Transfermarkt
                    (`transfermarkt_transfers.csv`). E' l'unica fonte che dia
                    il **giorno esatto** del passaggio: le altre due sanno solo
                    dire fra quali due date il passaggio e' avvenuto.

                    Qui c'era scritto anche «quindi l'unica che risolva i casi
                    di gennaio», ed era falso sul file presente. Misurato
                    sull'intero file (audit 2, F8): 58.549 righe, tutte con
                    data valida, dal 2020-06-01 al 2025-09-30, distribuite sui
                    soli mesi 6 (9.560), 7 (32.250), 8 (11.272) e 9 (5.467).
                    **Zero trasferimenti di gennaio**, in nessuna delle sei
                    stagioni: il file copre solo le finestre estive. I casi di
                    gennaio li risolve soltanto l'inviluppo delle comparse.

                    Conseguenza dichiarata, non corretta qui: la ragione
                    scritta a suo tempo per dare a questa fonte la priorita'
                    piu' alta non regge sul file che abbiamo. La priorita'
                    **non e' stata cambiata**, perche' cambiarla richiede una
                    misura che la giustifichi e quella misura non e' stata
                    fatta. Resta comunque vero che, dove il file copre, il
                    giorno esatto lo da' solo lui.
  `formazioni`      le comparse a referto in `game_lineups.csv.gz` incrociate
                    con la data della partita in `games.csv.gz`, per **tutte**
                    le competizioni e non solo la Serie A. Una comparsa e'
                    un'osservazione diretta: quel giorno quel giocatore era di
                    quel club, punto.
  `listone`         `kader_2026.csv`, la rosa dichiarata per la stagione in
                    corso, con la data di ingresso in rosa (`in_rosa_da`).
                    Serve al 2026-27, che Transfermarkt non copre piu'.

## Ordine di risoluzione, e perche' non e' esattamente quello del contratto

Il contratto elenca le fonti «in ordine di solidita'»: trasferimenti, poi
formazioni, poi listone. Quell'ordine vale per la **ricostruzione degli
intervalli**: la successione dei trasferimenti e' piu' precisa dell'inviluppo
delle comparse, che sa solo dire «fra la prima e l'ultima volta che l'ho visto
giocare per quel club».

C'e' pero' un caso in cui la comparsa vince, ed e' quello in cui la data della
domanda coincide **esattamente** con la data di una comparsa. Li' non stiamo
piu' interpolando: stiamo leggendo un referto. Il compito stesso lo dice
(«dalla successione dei trasferimenti, **validata contro le comparse**»): la
validazione ha senso solo se, quando le due fonti si contraddicono, la prova
diretta prevale. Senza questa regola un titolare a referto potrebbe risultare
non eleggibile perche' la tabella dei trasferimenti e' incompleta o ha un
anello rotto, il che e' assurdo.

La fonte dichiarata resta comunque una delle quattro ammesse dal contratto: una
comparsa esatta viene etichettata `formazioni`, come l'inviluppo. Il numero di
volte in cui la comparsa ha smentito i trasferimenti e' riportato nella
diagnostica (`contraddizioni_trasferimenti_formazioni`), non nascosto.

## Orizzonte dei trasferimenti

`transfermarkt_transfers.csv` contiene trasferimenti fino al 2025-09-30
(misurato: `transfer_date.max()`). Oltre quella data il file non e' informativo:
non contiene i trasferimenti successivi, quindi tenere aperto l'ultimo
intervallo equivarrebbe ad affermare «e' ancora li'» senza prova. Per questo
ogni intervallo dei trasferimenti viene troncato all'orizzonte del file e oltre
l'orizzonte questa fonte non da' alcun verdetto: si passa alle comparse (che
arrivano al 2026-07-04) e poi al listone.

Sotto censura temporale (vedi sotto) l'orizzonte **non** e' quello del file: e'
il massimo fra le sole date ammesse. Il 2025-09-30 e' una proprieta' dello
scarico fatto nell'agosto 2026, non un'affermazione su un giocatore, e usarlo a
una data passata significherebbe dire «non risulta nessun trasferimento
successivo, quindi era ancora li'», che e' esattamente il ragionamento vietato.

## Censura temporale: il parametro `as_of`

`costruisci(as_of=...)` filtra le prove **prima** di risolvere i conflitti e di
costruire gli intervalli. Filtrare il risultato finale non basterebbe: una prova
futura ha gia' cambiato la priorita' fra le fonti, i bordi degli intervalli e i
ripieghi. L'audit lo ha quantificato rieseguendo la catena su tutte le 26.790
righe non a referto delle tre stagioni (F3): 1.706 (2023-24), 2.518 (2024-25) e
160 (2025-26) righe **passerebbero** un filtro a valle e cambierebbero comunque
esito sotto censura piena, tutte da `si` a `ignoto`, tutte da intervalli dei
trasferimenti troncati all'orizzonte globale.

La decisione e' scritta in `reports/PROTOCOLLO_v2.md` §9.1 (censura piena) e non
va rimessa in discussione qui.

Che cosa filtra, con `as_of` **esclusivo** (`data < as_of`):

  comparse         quelle con `data < as_of`. Una comparsa del giorno stesso
                   non e' disponibile a chi decide quel giorno: il referto
                   esiste a partita finita.
  trasferimenti    quelli con `transfer_date < as_of`; l'orizzonte viene
                   ricalcolato sul massimo dei soli ammessi.
  listone          entra solo se la data del suo scatto e' anteriore ad
                   `as_of` (vedi `DATA_SCATTO_LISTONE`).

Con `as_of=None` non c'e' nessuna censura: e' il comportamento storico, che
resta disponibile **per la descrizione storica** — «com'e' andata davvero» — e
che **non** va usato per costruire le informazioni di un backtest o di una
decisione datata. Il predefinito e' `None` proprio per non cambiare in silenzio
il comportamento di chi gia' chiama questa funzione.

Due conseguenze misurate della censura piena, dichiarate qui perche' chi legge
un `ignoto` deve sapere da dove viene.

1. **La fonte `trasferimenti` diventa muta quasi ovunque.** L'orizzonte ammesso
   e' l'ultima data di trasferimento anteriore ad `as_of`, e il file ha solo
   finestre estive: a `as_of = 2024-02-15` l'orizzonte censurato e' il
   2023-09-29 (139 giorni prima), a `as_of = 2024-04-20` e' 204 giorni prima.
   Da ottobre in poi questa fonte non da' piu' nessun verdetto (F8).
2. **Da `as_of` in avanti nessuna fonte risponde piu', ed e' strutturale.**
   Ogni fonte di questo modulo e' un intervallo il cui bordo destro e' fissato
   dall'ultima prova disponibile: un periodo da comparse finisce all'ultima
   comparsa ammessa piu' un giorno, gli intervalli dei trasferimenti sono
   troncati all'orizzonte ammesso piu' un giorno, e il listone censurato non
   c'e'. Tutti e tre i bordi cadono al piu' tardi su `as_of`, quindi
   `max(al) <= as_of` e nessuna interrogazione a una data `>= as_of` puo'
   ricevere risposta. Misurato con `as_of = 2024-08-17`: 10.129 intervalli
   costruiti (5.773 `spell`, 4.356 `trasferimenti`) e `max(al) = 2024-08-17`
   esatto.

   Non e' un difetto dell'implementazione: e' la regola «la mancanza di una
   comparsa altrove non e' prova di permanenza» portata alla sua conseguenza.
   Per affermare qualcosa su una data **futura** serve una fonte che faccia
   un'affermazione a termine — il listone di quella stagione — e non
   l'estrapolazione di un'osservazione passata.

Quanto costa, misurato sui tre panel con `as_of` all'inizio di stagione
(2023-08-19, 2024-08-17, 2025-08-23; nessuna riga di panel e' anteriore a quelle
date, e 278 / 264 / 263 righe cadono esattamente su di esse):

| stagione | righe | esiti prima (si / no / ignoto) | esiti dopo | cambiano |
|---|---:|---|---|---:|
| 2023-24 | 25.232 | 19.429 / 2.834 / 2.969 | tutte `ignoto` | 22.263 (88,2%) |
| 2024-25 | 25.802 | 20.131 / 2.913 / 2.758 | tutte `ignoto` | 23.044 (89,3%) |
| 2025-26 | 25.194 | 19.162 / 2.412 / 3.620 | tutte `ignoto` | 21.574 (85,6%) |

Nessuna transizione produce un `no`: le uniche osservate sono `si -> ignoto` e
`no -> ignoto`. La tabella censurata **non** e' vuota — a `as_of = 2024-08-17`,
interrogata al 16 agosto 2024 su 648 giocatori, risponde 409 `si`, 99 `no` e
140 `ignoto` — ma non sa dire nulla dal giorno della decisione in poi, che e'
esattamente cio' che serve a un backtest.

La via d'uscita e' quella scritta in `reports/PROTOCOLLO_v2.md` §9.2: l'universo
dei convocabili a una data e' il **listone della stagione**, informazione
pubblica prima dell'asta, che qui esiste solo per il 2026-27 (`kader_2026.csv`).
I listoni delle stagioni storiche stanno altrove
(`data/raw/quotazioni/fantacalcioit_*.csv`) e collegarli e' un lavoro di fonte,
non di censura: non e' stato fatto qui.

`ignoto` non e' `no`: una riga ignota esce dal denominatore, non ci entra come
negativo. Questo modulo, censurato, produce ignoranza — non negazioni.

## Anelli rotti nella catena

Fra due trasferimenti consecutivi dello stesso giocatore ci sono due
affermazioni sullo stesso intervallo: il `to_club_id` del trasferimento
precedente e il `from_club_id` di quello successivo. Su 3.717 coppie
consecutive dei giocatori che ci interessano, 3.137 concordano e 580 no (15,6%:
prestiti, rientri non registrati, doppi passaggi nello stesso giorno). Quando
non concordano l'intervallo viene marcato **ambiguo** e i trasferimenti non
danno verdetto su di esso: si scende alla fonte successiva. Scegliere in
silenzio una delle due affermazioni sarebbe esattamente il difetto che questo
modulo deve eliminare.

## Risposte ammesse

`verifica()` risponde `si`, `no` oppure `ignoto`, mai un booleano:

  `si`      esiste una prova che a quella data era tesserato per quel club;
  `no`      esiste una prova che a quella data era tesserato per un club
            **diverso**;
  `ignoto`  nessuna fonte copre quella data. Non e' un'assenza: e'
            un'ignoranza, e come tale non deve finire in nessun denominatore.

Uso tipico:

    from fantabot.tabellino import appartenenza

    # descrizione storica: tutte le prove note oggi
    t = appartenenza.costruisci()
    t.verifica(tm_player_id=883349, club_id=5, data="2024-08-17")
    # -> ("si", "formazioni")

    # informazione disponibile a chi decide il 17 agosto 2024, e nulla di piu'
    d = appartenenza.costruisci(as_of="2024-08-17")
    d.verifica(tm_player_id=883349, club_id=5, data="2024-08-17")
    # -> ("ignoto", "ignota")

Le due righe sopra sono lo stesso giocatore, lo stesso club e lo stesso giorno,
e danno due risposte diverse: il `si` della prima poggia su una comparsa del 31
agosto 2024, quattordici giorni dopo la domanda (audit 2, F2, caso 1). Con la
censura quella prova non esiste ancora, e la risposta onesta e' `ignoto`.
Censurando al 18 agosto — cioe' ammettendo tutto fino al 17 compreso — la
risposta diventa ("no", "trasferimenti"), club 41107: il trasferimento del 1
luglio 2024, che nella tabella storica era stato cancellato proprio da quella
comparsa di agosto.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[3]
RAW = ROOT / "data" / "raw"
PROC = ROOT / "data" / "processed"
DL = RAW / "transfermarkt" / "_download"

# risposte
SI = "si"
NO = "no"
IGNOTO = "ignoto"

# fonti ammesse dal contratto degli stati, sezione 7.1
FONTE_TRASFERIMENTI = "trasferimenti"
FONTE_FORMAZIONI = "formazioni"
FONTE_LISTONE = "listone"

# Confidenza di una risposta. `prova` significa che la data interrogata cade
# dentro il tratto sostenuto da un'osservazione o da un documento; `inferenza`
# significa che cade nel prolungamento in avanti dell'ultima prova disponibile,
# cioe' che stiamo assumendo la continuita' dell'appartenenza. Le due cose non
# vanno mescolate: la seconda e' una previsione, per quanto ragionevole.
PROVA = "prova"
INFERENZA = "inferenza"
FONTE_IGNOTA = "ignota"

# ordine di risoluzione: la comparsa esatta e' un'osservazione diretta e viene
# prima; poi gli intervalli dei trasferimenti; poi l'inviluppo delle comparse;
# poi la rosa dichiarata. Il nome della fonte riportata resta uno dei quattro
# ammessi (una comparsa, esatta o interpolata, si chiama `formazioni`).
_PRIORITA = ["comparsa", "trasferimenti", "spell", "listone"]
_FONTE_DI = {
    "comparsa": FONTE_FORMAZIONI,
    "trasferimenti": FONTE_TRASFERIMENTI,
    "spell": FONTE_FORMAZIONI,
    "listone": FONTE_LISTONE,
}

# data oltre la quale nessuna fonte a intervalli viene estrapolata. Serve solo
# a dare un estremo destro finito agli intervalli aperti, cosi' che il confronto
# `data < al` sia sempre definito.
_LONTANO = pd.Timestamp("2100-01-01")

# apertura del mercato della stagione in corso: e' il limite sinistro entro cui
# la fotografia della rosa (`kader_2026.csv`) puo' essere considerata valida.
INIZIO_STAGIONE_CORRENTE = pd.Timestamp("2026-07-01")

# Data dello scatto di `kader_2026.csv`, cioe' il giorno in cui quella rosa e'
# stata scaricata e da cui la sua affermazione diventa disponibile.
#
# Il file NON contiene questa data: non ha nessuna colonna di scaricamento
# (audit 2, F9). L'unica traccia locale e' la data di modifica del file, che
# l'8 settembre 2026 valeva 2026-09-05 03:20:04. La costante e' dichiarata qui
# invece di essere dedotta a ogni chiamata da `stat()` per due ragioni:
# copiare o ripristinare il file cambierebbe `st_mtime` senza che lo scatto sia
# cambiato, e una data che decide quali righe entrano in un backtest deve stare
# scritta dove la si puo' leggere e contestare.
#
# Limite dichiarato: la data di modifica e' un limite **superiore** allo scatto
# vero (il file non puo' essere stato scritto prima di essere stato scaricato),
# non lo scatto stesso. Se lo scarico fosse avvenuto giorni prima della
# scrittura, questa costante e' troppo tarda e la censura risulta piu' severa
# del necessario: sbaglia dalla parte prudente. Chi conosce la data vera la
# passa a `costruisci(data_scatto_listone=...)`.
DATA_SCATTO_LISTONE = pd.Timestamp("2026-09-05")

# cache di processo delle tabelle costruite, e cache separata delle fonti
# grezze. La seconda esiste perche' due `as_of` diversi producono due tabelle
# diverse ma leggono gli stessi 125 MB di `game_lineups.csv.gz`: senza di essa
# ogni data limite pagherebbe di nuovo i 6,7 secondi della lettura completa.
_CACHE: dict[str, "TabellaAppartenenza"] = {}
_CACHE_FONTI: dict[str, dict] = {}


def _impronta_file() -> str:
    """Impronta delle fonti: percorso, dimensione e istante di modifica.

    Non e' un'impronta del contenuto. Calcolare SHA-256 su
    `game_lineups.csv.gz` (125 MB) a ogni chiamata costerebbe quasi quanto
    rileggerlo, e questa impronta serve solo a impedire che la cache **di
    processo** restituisca una tabella costruita su file diversi. Un file
    riscritto con la stessa dimensione e lo stesso `mtime` al nanosecondo non
    verrebbe distinto: e' il limite, ed e' dichiarato.
    """
    pezzi = []
    for f in [PROC / "_match" / "map_tm.csv",
              PROC / "_match" / "map_tm_kader_2026.csv",
              RAW / "transfermarkt" / "kader_2026.csv",
              RAW / "transfermarkt" / "transfermarkt_transfers.csv",
              DL / "game_lineups.csv.gz",
              DL / "games.csv.gz"]:
        if f.exists():
            s = f.stat()
            pezzi.append(f"{f}|{s.st_size}|{s.st_mtime_ns}")
        else:
            pezzi.append(f"{f}|assente")
    return hashlib.sha256("\n".join(pezzi).encode("utf-8")).hexdigest()[:32]


def _impronta_ids(ids: set[int]) -> str:
    """Impronta dell'insieme degli identificativi richiesti.

    La chiave precedente era `str(sorted(ids)[:1] + [len(ids)])`, cioe' il
    minimo e la cardinalita': due insiemi diversi con lo stesso minimo e la
    stessa cardinalita' ricevevano la stessa tabella (audit 2, F1b).
    """
    v = np.fromiter(sorted(int(i) for i in ids), dtype="int64",
                    count=len(ids))
    return hashlib.sha256(v.tobytes()).hexdigest()[:32]


# --------------------------------------------------------------------------
# lettura delle fonti
# --------------------------------------------------------------------------

def _identita_note() -> set[int]:
    """Tutti i `tm_player_id` che ci interessano: quelli del listone storico e
    quelli della rosa 2026-27.

    Filtrare subito serve solo a non tenere in memoria 3,18 milioni di righe di
    formazioni quando ce ne servono 307 mila.
    """
    ids: set[int] = set()
    for f, col in [(PROC / "_match" / "map_tm.csv", "tm_player_id"),
                   (PROC / "_match" / "map_tm_kader_2026.csv", "tm_player_id"),
                   (RAW / "transfermarkt" / "kader_2026.csv", "tm_player_id")]:
        if f.exists():
            d = pd.read_csv(f, usecols=[col])
            ids |= set(d[col].dropna().astype("int64"))
    return ids


def _comparse(ids: set[int]) -> pd.DataFrame:
    """(tm_player_id, data, club_id) da tutte le competizioni.

    `game_lineups` da' il club a referto ma non la data; la data sta in
    `games`. L'unione e' sul solo `game_id`, che in `games` e' unico, quindi non
    puo' moltiplicare le righe: lo verifichiamo comunque, perche' un merge che
    cambia cardinalita' in silenzio e' il modo piu' comune di falsare una
    misura.
    """
    fl = DL / "game_lineups.csv.gz"
    fg = DL / "games.csv.gz"
    if not fl.exists() or not fg.exists():
        return pd.DataFrame(columns=["tm_player_id", "data", "club_id"])
    g = pd.read_csv(fg, compression="gzip", low_memory=False,
                    usecols=["game_id", "date"])
    if g.game_id.duplicated().any():
        raise RuntimeError("games.csv.gz: game_id non univoco, l'unione con le "
                           "formazioni moltiplicherebbe le righe")
    g["data"] = pd.to_datetime(g["date"], errors="coerce")
    lu = pd.read_csv(fl, compression="gzip", low_memory=False,
                     usecols=["game_id", "player_id", "club_id"])
    lu = lu[lu.player_id.isin(ids)]
    prima = len(lu)
    c = lu.merge(g[["game_id", "data"]], on="game_id", how="left")
    if len(c) != prima:
        raise RuntimeError(f"comparse: l'unione con games ha cambiato le righe "
                           f"({prima} -> {len(c)})")
    c = c.rename(columns={"player_id": "tm_player_id"})
    c = c.dropna(subset=["data"])[["tm_player_id", "data", "club_id"]]
    c["tm_player_id"] = c["tm_player_id"].astype("int64")
    c["club_id"] = c["club_id"].astype("int64")
    return c.drop_duplicates().sort_values(["tm_player_id", "data"])


def _spell_da_comparse(c: pd.DataFrame, estendi_fino=None) -> pd.DataFrame:
    """Comprime le comparse in periodi contigui per club.

    Un giocatore che gioca per il club A dal 20 agosto al 22 dicembre e poi per
    il club B dal 12 gennaio in poi produce due periodi. Dentro un periodo
    l'appartenenza e' certa: fra la prima e l'ultima comparsa per quel club non
    puo' essere stato altrove (altrimenti ci sarebbe una comparsa per un terzo
    club in mezzo, e il periodo si spezzerebbe li').

    Il buco fra due periodi resta scoperto di proposito: la data del passaggio
    sta da qualche parte dentro il buco e le comparse non sanno dire dove. A
    risolverlo sono i trasferimenti, che hanno priorita' piu' alta.

    `estendi_fino` prolunga **solo l'ultimo periodo di ogni giocatore** fino a
    quella data. Serve sotto censura temporale: chi decide il 17 agosto sa che
    il giocatore ha giocato per quel club fino a maggio, e per rispondere alla
    domanda «di chi e' il 25 agosto?» deve estendere in avanti. L'estensione
    **non e' una prova** ed e' segnata come tale: `prova_al` resta al bordo
    sostenuto dall'ultima comparsa, e chi interroga la tabella oltre quella data
    riceve `confidenza = "inferenza"`.
    """
    if c.empty:
        return pd.DataFrame(columns=["tm_player_id", "club_id", "dal", "al"])
    d = c.sort_values(["tm_player_id", "data"]).reset_index(drop=True)
    cambio = ((d.tm_player_id != d.tm_player_id.shift())
              | (d.club_id != d.club_id.shift()))
    d["blocco"] = cambio.cumsum()
    s = d.groupby("blocco").agg(tm_player_id=("tm_player_id", "first"),
                                club_id=("club_id", "first"),
                                dal=("data", "min"),
                                al=("data", "max"))
    # `al` e' l'ultima comparsa: rendiamo l'intervallo semiaperto aggiungendo un
    # giorno, cosi' la stessa convenzione [dal, al) vale per tutte le fonti.
    s["al"] = s["al"] + pd.Timedelta(days=1)
    # `prova_al` e' il bordo destro sostenuto da una prova diretta: oltre di
    # esso l'affermazione «era ancora li'» e' un'inferenza, non un'osservazione.
    s["prova_al"] = s["al"]
    s = s.reset_index(drop=True)
    if estendi_fino is not None:
        # solo l'ultimo periodo di ogni giocatore si estende: quelli in mezzo
        # sono gia' chiusi dal periodo successivo, che e' una prova.
        ultimo = s.groupby("tm_player_id")["al"].transform("max") == s["al"]
        oltre = ultimo & (s["al"] < pd.Timestamp(estendi_fino))
        s.loc[oltre, "al"] = pd.Timestamp(estendi_fino)
    return s


def _leggi_trasferimenti(ids: set[int]) -> pd.DataFrame:
    """Righe di `transfermarkt_transfers.csv` per i giocatori che ci
    interessano, con la data gia' convertita e ordinate per (giocatore, data).

    Separata dalla costruzione degli intervalli perche' la censura temporale
    agisce **qui**, sulle righe, e non a valle: un trasferimento futuro cambia
    l'ambiguita' dell'intervallo precedente, il suo bordo destro e l'orizzonte.
    """
    # Fonte canonica: l'estratto ANNUALE, prodotto da `scripts/l2_trasferimenti.py`
    # dal grezzo `_download/transfers.csv.gz`. Il vecchio
    # `transfermarkt_transfers.csv` e' un estratto **estivo** (tm_process.py
    # filtra mesi 6-9): usarlo qui significava non vedere nessun movimento di
    # gennaio, e da quella mancanza si era dedotto, sbagliando, che la fonte non
    # conoscesse l'inverno. Misura: l'annuale ha 114.150 righe fra il 2019 e il
    # 2027, di cui 31.624 fra gennaio e febbraio su 15.716 giocatori, e contiene
    # tutte le righe dell'estivo (verificato: zero assenti).
    f = RAW / "transfermarkt" / "transfermarkt_transfers_annuale.csv"
    if not f.exists():
        # ripiego dichiarato: senza l'annuale si torna all'estivo, ma chi legge
        # deve sapere che i movimenti invernali non ci sono
        f = RAW / "transfermarkt" / "transfermarkt_transfers.csv"
    if not f.exists():
        return pd.DataFrame(columns=["player_id", "data", "transfer_season",
                                     "from_club_id", "to_club_id"])
    t = pd.read_csv(f, usecols=["player_id", "transfer_date", "transfer_season",
                                "from_club_id", "to_club_id"])
    t = t[t.player_id.isin(ids)].copy()
    t["data"] = pd.to_datetime(t["transfer_date"], errors="coerce")
    t = t.dropna(subset=["data", "from_club_id", "to_club_id"])
    t.attrs["fonte"] = f.name
    return t.sort_values(["player_id", "data"]).reset_index(drop=True)


def _intervalli_trasferimenti(ids: set[int]) -> tuple[pd.DataFrame, pd.Timestamp, dict]:
    """Come `_intervalli_trasferimenti_da`, leggendo il file da se'.

    Firma conservata: gli script dell'audit 2 la richiamano cosi'.
    """
    return _intervalli_trasferimenti_da(_leggi_trasferimenti(ids))


def _intervalli_trasferimenti_da(
        t: pd.DataFrame,
        estendi_fino=None) -> tuple[pd.DataFrame, pd.Timestamp, dict]:
    """Intervalli dalla successione dei trasferimenti, con gli anelli rotti
    marcati ambigui invece che risolti a caso.

    Per ogni giocatore, ordinati i trasferimenti per data:

      - prima del primo trasferimento vale `from_club_id` del primo, ma **solo
        a partire dal 1 luglio della stagione del trasferimento**: un
        trasferimento dice da dove il giocatore arriva, non da quanto tempo ci
        stava. Estrapolare all'indietro senza limite e' esattamente cio' che
        rende falsa questa fonte: misurato, l'intervallo iniziale illimitato
        contraddice il referto nel 48,9% delle comparse che copre (56.490 su
        115.469), contro il 5,8% degli intervalli fra due trasferimenti;
      - fra il trasferimento i e il successivo vale `to_club_id` del
        trasferimento i;
      - l'intervallo e' ambiguo se `to_club_id[i] != from_club_id[i+1]`, perche'
        le due affermazioni sullo stesso periodo non coincidono.

    Tutti gli intervalli vengono troncati all'orizzonte, che e' il massimo
    delle date **presenti in `t`**: se `t` e' gia' stato censurato a una data
    limite, l'orizzonte si accorcia con esso. E' il punto in cui la censura
    piena si distingue da un filtro a valle (audit 2, F3).
    """
    vuoto = pd.DataFrame(columns=["tm_player_id", "club_id", "dal", "al", "ambiguo"])
    if not len(t):
        return vuoto, pd.Timestamp("1900-01-01"), {"trasferimenti_righe": 0}
    t = t.sort_values(["player_id", "data"]).reset_index(drop=True).copy()
    orizzonte = t["data"].max()

    t["from_club_id"] = t["from_club_id"].astype("int64")
    t["to_club_id"] = t["to_club_id"].astype("int64")
    # club affermato dal trasferimento precedente dello stesso giocatore
    stesso = t.player_id == t.player_id.shift()
    prec_to = t["to_club_id"].shift()

    righe = []
    # intervallo iniziale: dal 1 luglio della stagione del trasferimento fino al
    # trasferimento stesso. `transfer_season` ha la forma "19/20": i primi due
    # caratteri sono l'anno di inizio.
    primi = t[~stesso].copy()
    anno = pd.to_numeric(primi["transfer_season"].astype(str).str.slice(0, 2),
                         errors="coerce") + 2000
    inizio = pd.to_datetime(anno.astype("Int64").astype(str) + "-07-01",
                            errors="coerce")
    # se la stagione non e' leggibile ripiego su un anno prima del trasferimento:
    # e' comunque un limite, non un'estrapolazione illimitata
    inizio = inizio.fillna(primi["data"] - pd.Timedelta(days=365))
    # e non puo' mai partire dopo il trasferimento
    inizio = inizio.where(inizio < primi["data"], primi["data"] - pd.Timedelta(days=1))
    righe.append(pd.DataFrame({
        "tm_player_id": primi.player_id.astype("int64"),
        "club_id": primi.from_club_id,
        "dal": inizio.to_numpy(),
        "al": primi.data,
        "ambiguo": False,
    }))
    # intervalli successivi: da un trasferimento al seguente (o all'orizzonte)
    prossima_data = t["data"].shift(-1)
    prossimo_stesso = t.player_id == t.player_id.shift(-1)
    prossimo_from = t["from_club_id"].shift(-1)
    fine = prossima_data.where(prossimo_stesso, _LONTANO)
    ambiguo = prossimo_stesso & (t["to_club_id"] != prossimo_from)
    righe.append(pd.DataFrame({
        "tm_player_id": t.player_id.astype("int64"),
        "club_id": t.to_club_id,
        "dal": t.data,
        "al": fine,
        "ambiguo": ambiguo.fillna(False),
    }))
    iv = pd.concat(righe, ignore_index=True)
    # tronco all'orizzonte: oltre, il file non sa nulla. `prova_al` conserva
    # quel bordo anche quando l'intervallo viene poi esteso in avanti.
    iv["al"] = iv["al"].clip(upper=orizzonte + pd.Timedelta(days=1))
    iv = iv[iv["dal"] < iv["al"]].copy()
    iv["prova_al"] = iv["al"]
    if estendi_fino is not None:
        # Un trasferimento dice «da questo giorno e' di quel club». Quella
        # affermazione vale in avanti finche' un'altra prova non la smentisce:
        # e' inferenza dal passato, non informazione futura. Senza questa
        # estensione, sotto censura ogni intervallo si chiude sull'ultima prova
        # ammessa e nessuna domanda posteriore alla decisione riceve risposta —
        # misurato: il panel passa a 100% `ignoto` in tutte e tre le stagioni.
        # Si estende solo l'ultimo intervallo di ogni giocatore, cioe' quello
        # che nessun trasferimento successivo ha gia' chiuso.
        limite = pd.Timestamp(estendi_fino)
        ultimo = iv.groupby("tm_player_id")["al"].transform("max") == iv["al"]
        oltre = ultimo & (iv["al"] < limite)
        iv.loc[oltre, "al"] = limite

    coppie = int(stesso.sum())
    concordi = int((stesso & (prec_to == t["from_club_id"])).sum())
    diagnostica = {
        "trasferimenti_righe": int(len(t)),
        "trasferimenti_giocatori": int(t.player_id.nunique()),
        "orizzonte_trasferimenti": str(orizzonte.date()),
        "catena_coppie_consecutive": coppie,
        "catena_concordi": concordi,
        "catena_rotte": coppie - concordi,
        "intervalli_trasferimenti": int(len(iv)),
        "intervalli_ambigui": int(iv.ambiguo.sum()),
        # tenuto solo come misura: due trasferimenti nello stesso giorno non
        # rompono la costruzione (l'intervallo fra i due e' vuoto e viene
        # scartato dal filtro `dal < al`), ma vanno contati
        "trasferimenti_stesso_giorno": int(
            (t.groupby(["player_id", "data"]).size() > 1).sum()),
    }
    return iv, orizzonte, diagnostica


def _valida_contro_comparse(iv: pd.DataFrame,
                            comparse: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    """Scarta gli intervalli dei trasferimenti smentiti da un referto.

    Un intervallo afferma «dal giorno X al giorno Y questo giocatore era di
    questo club». Se dentro quella finestra il giocatore risulta a referto per
    un club diverso, l'affermazione e' falsa: prestiti non registrati, rientri
    mancanti, doppi passaggi. L'intervallo viene tolto **per intero**, non
    accorciato: non sappiamo dove sia il confine vero, e inventarlo sarebbe di
    nuovo un'interpretazione scelta in silenzio. Le date coperte da un referto
    restano comunque risolte, perche' la comparsa esatta e i periodi contigui
    hanno una loro voce.

    Ritorna gli intervalli superstiti e le misure della validazione.
    """
    if iv.empty or comparse.empty:
        return iv, {"validazione_intervalli_esaminati": int(len(iv)),
                    "validazione_intervalli_smentiti": 0}
    a = iv.reset_index(drop=True).copy()
    a["_iv"] = np.arange(len(a))
    j = comparse.merge(a[["_iv", "tm_player_id", "club_id", "dal", "al"]],
                       on="tm_player_id", how="inner", suffixes=("_oss", "_iv"))
    dentro = (j["data"] >= j["dal"]) & (j["data"] < j["al"])
    j = j[dentro]
    smentiti = set(j.loc[j["club_id_oss"] != j["club_id_iv"], "_iv"])
    confermati = set(j["_iv"]) - smentiti
    fuori = a[~a["_iv"].isin(smentiti)].drop(columns=["_iv"])
    return fuori.reset_index(drop=True), {
        "validazione_intervalli_esaminati": int(len(a)),
        "validazione_intervalli_con_referto": int(j["_iv"].nunique()),
        "validazione_intervalli_confermati": int(len(confermati)),
        "validazione_intervalli_smentiti": int(len(smentiti)),
        "validazione_comparse_dentro_intervalli": int(len(j)),
        "validazione_comparse_discordi": int(
            (j["club_id_oss"] != j["club_id_iv"]).sum()),
    }


def _intervalli_listone(as_of: pd.Timestamp | None = None,
                        data_scatto: pd.Timestamp | None = None
                        ) -> tuple[pd.DataFrame, pd.DataFrame, dict]:
    """Rosa dichiarata per la stagione in corso, con la data di ingresso.

    `kader_2026.csv` e' una fotografia scattata il giorno dello scaricamento:
    dice chi c'e' **adesso** e da quando (`in_rosa_da`).

    Due avvertenze governano la costruzione.

    1. La fotografia vale **solo per la stagione in corso**. `in_rosa_da` puo'
       risalire a molti anni prima e non registra i prestiti nel frattempo:
       Hermoso risulta «in rosa alla Roma dal 02/09/2024», ma nel febbraio 2025
       giocava a referto per il Leverkusen. Estendere la fotografia
       all'indietro produrrebbe affermazioni false su stagioni che altre fonti
       coprono meglio. Per questo ogni intervallo parte dal 1 luglio 2026,
       apertura del mercato della stagione 2026-27.
    2. Prima di `in_rosa_da`, dentro la stagione in corso, la stessa fonte
       afferma che il giocatore **non** era ancora di quel club. E' una prova di
       non appartenenza, e viene restituita a parte: serve a distinguere «non
       c'era» da «non lo so», che e' tutto il punto di questo lavoro.

    L'estremo destro resta aperto: per le partite ancora da giocare la rosa
    attuale e' la migliore informazione disponibile. Non basta comunque da sola
    a rendere una riga eleggibile, perche' l'eleggibilita' richiede anche che la
    partita abbia formazioni note (contratto, sezione 7.1).

    Censura temporale. Questa fonte e' una fotografia con una sola data, quella
    del suo scatto: o e' gia' stata scattata alla data limite, e allora vale per
    intero, o non lo e', e allora non esiste ancora nessuna delle sue
    affermazioni — comprese quelle di **non** appartenenza. Non si puo'
    censurarla riga per riga come le altre due, perche' `in_rosa_da` e' un
    contenuto della fotografia, non la data in cui il contenuto e' diventato
    pubblico. Quando lo scatto non e' anteriore ad `as_of`, la fonte esce
    intera e cio' che resta e' `ignoto`, mai `no`.

    Ritorna (appartenenze, non_appartenenze, diagnostica).
    """
    vuoto = pd.DataFrame(columns=["tm_player_id", "club_id", "dal", "al"])
    scatto = DATA_SCATTO_LISTONE if data_scatto is None else pd.Timestamp(data_scatto)
    f = RAW / "transfermarkt" / "kader_2026.csv"
    if not f.exists():
        return vuoto, vuoto, {"listone_righe": 0,
                              "listone_data_scatto": str(scatto.date()),
                              "listone_ammesso": False,
                              "listone_righe_ammesse": 0,
                              "listone_righe_scartate": 0}
    k = pd.read_csv(f, usecols=["tm_club_id", "tm_player_id", "in_rosa_da"])
    if as_of is not None and not (scatto < pd.Timestamp(as_of)):
        return vuoto, vuoto, {
            "listone_righe": int(len(k)),
            "listone_data_scatto": str(scatto.date()),
            "listone_ammesso": False,
            "listone_righe_ammesse": 0,
            "listone_righe_scartate": int(len(k)),
            "listone_intervalli": 0,
            "listone_intervalli_non_appartenenza": 0,
        }
    k = k.dropna(subset=["tm_club_id", "tm_player_id"])
    ingresso = pd.to_datetime(k["in_rosa_da"], format="%d/%m/%Y", errors="coerce")
    base = pd.DataFrame({
        "tm_player_id": k.tm_player_id.astype("int64").to_numpy(),
        "club_id": k.tm_club_id.astype("int64").to_numpy(),
        "ingresso": ingresso.to_numpy(),
    })
    # senza data di ingresso l'intervallo non e' costruibile: la riga esce
    base = base.dropna(subset=["ingresso"])
    si = pd.DataFrame({
        "tm_player_id": base.tm_player_id,
        "club_id": base.club_id,
        "dal": base.ingresso.clip(lower=INIZIO_STAGIONE_CORRENTE),
        "al": _LONTANO,
    })
    no = pd.DataFrame({
        "tm_player_id": base.tm_player_id,
        "club_id": base.club_id,
        "dal": INIZIO_STAGIONE_CORRENTE,
        "al": base.ingresso,
    })
    no = no[no["dal"] < no["al"]]
    return si, no.reset_index(drop=True), {
        "listone_righe": int(len(k)),
        "listone_senza_data_ingresso": int(ingresso.isna().sum()),
        "listone_intervalli": int(len(si)),
        "listone_intervalli_non_appartenenza": int(len(no)),
        "listone_data_scatto": str(scatto.date()),
        "listone_ammesso": True,
        "listone_righe_ammesse": int(len(k)),
        "listone_righe_scartate": 0,
    }


# --------------------------------------------------------------------------
# tabella
# --------------------------------------------------------------------------

def _cerca_intervallo(iv: pd.DataFrame, tm: pd.Series,
                      data: pd.Series) -> pd.Series:
    """Per ogni interrogazione (giocatore, data) restituisce il `club_id`
    dell'intervallo che la contiene, oppure <NA>.

    Si usa `merge_asof` per prendere l'ultimo intervallo iniziato non dopo la
    data, e poi si verifica che la data sia effettivamente prima della fine.
    Gli intervalli di una stessa fonte non si sovrappongono per costruzione,
    quindi «l'ultimo iniziato» e' anche l'unico candidato.
    """
    vuoto = pd.Series(pd.NA, index=data.index, dtype="Int64")
    if iv.empty:
        return vuoto
    q = pd.DataFrame({"tm_player_id": tm.astype("Int64"), "data": data})
    q["_ord"] = np.arange(len(q))
    valide = q.dropna(subset=["tm_player_id", "data"]).copy()
    if valide.empty:
        return vuoto
    valide["tm_player_id"] = valide["tm_player_id"].astype("int64")
    # `merge_asof` pretende chiavi temporali della stessa risoluzione: le fonti
    # arrivano chi in secondi chi in nanosecondi, quindi si uniformano qui
    valide["data"] = valide["data"].astype("datetime64[ns]")
    valide = valide.sort_values("data")
    base = iv.copy()
    base["dal"] = base["dal"].astype("datetime64[ns]")
    base["al"] = base["al"].astype("datetime64[ns]")
    base = base.sort_values("dal")
    colonne = ["tm_player_id", "club_id", "dal", "al"]
    if "prova_al" in base.columns:
        base["prova_al"] = base["prova_al"].astype("datetime64[ns]")
        colonne.append("prova_al")
    r = pd.merge_asof(valide, base[colonne],
                      left_on="data", right_on="dal", by="tm_player_id",
                      direction="backward")
    dentro = r["al"].notna() & (r["data"] < r["al"])
    out = vuoto.copy()
    idx = r.loc[dentro, "_ord"].to_numpy()
    out.iloc[idx] = r.loc[dentro, "club_id"].astype("Int64").to_numpy()
    # confidenza: `prova` se la data cade dentro il tratto sostenuto da una
    # prova diretta, `inferenza` se cade nel prolungamento in avanti. Chi non
    # espone `prova_al` (le fonti che non si estendono) risponde sempre `prova`.
    conf = pd.Series(pd.NA, index=data.index, dtype=object)
    if len(idx):
        if "prova_al" in r.columns:
            entro = (r.loc[dentro, "prova_al"].isna()
                     | (r.loc[dentro, "data"] < r.loc[dentro, "prova_al"]))
            conf.iloc[idx] = np.where(entro.to_numpy(), PROVA, INFERENZA)
        else:
            conf.iloc[idx] = PROVA
    out.attrs["confidenza"] = conf
    return out


@dataclass
class TabellaAppartenenza:
    """Tutte le fonti gia' lette e compresse in intervalli, pronte da
    interrogare."""

    intervalli: pd.DataFrame          # (tm_player_id, club_id, dal, al, fonte)
    comparse: pd.DataFrame            # (tm_player_id, data, club_id)
    orizzonte_trasferimenti: pd.Timestamp
    # intervalli in cui una fonte afferma esplicitamente la NON appartenenza a
    # quel club: (tm_player_id, club_id, dal, al). Serve a rispondere `no` anche
    # quando non sappiamo dove il giocatore fosse davvero.
    non_appartenenza: pd.DataFrame = field(
        default_factory=lambda: pd.DataFrame(
            columns=["tm_player_id", "club_id", "dal", "al"]))
    diagnostica: dict = field(default_factory=dict)
    # data limite informativa con cui la tabella e' stata costruita, oppure
    # None se non c'e' stata censura. Chi riceve una tabella deve poter sapere
    # che cosa le e' stato permesso di vedere, senza rileggere la diagnostica.
    as_of: pd.Timestamp | None = None

    # ------------------------------------------------------------------
    def _per_fonte(self, chiave: str) -> pd.DataFrame:
        return self.intervalli[self.intervalli.origine == chiave]

    def club_alla_data(self, tm_player_id, data) -> tuple[int | None, str]:
        """Club per cui il giocatore era tesserato a quella data, e la fonte."""
        r = self.risolvi_molti(pd.Series([tm_player_id]),
                               pd.Series([pd.to_datetime(data)]))
        c = r["club_id_alla_data"].iloc[0]
        return (None if pd.isna(c) else int(c)), r["fonte"].iloc[0]

    def verifica(self, tm_player_id, club_id, data) -> tuple[str, str]:
        """«A questa data, questo giocatore era tesserato per questo club?»

        Ritorna (`si` | `no` | `ignoto`, fonte).
        """
        r = self.verifica_molti(pd.Series([tm_player_id]),
                                pd.Series([club_id]),
                                pd.Series([pd.to_datetime(data)]))
        return r["esito"].iloc[0], r["fonte"].iloc[0]

    # ------------------------------------------------------------------
    def risolvi_molti(self, tm_player_id: pd.Series,
                      data: pd.Series) -> pd.DataFrame:
        """Versione vettoriale: per ogni riga, il club alla data e la fonte.

        Le fonti si applicano in ordine di priorita' e ciascuna riempie solo le
        righe ancora scoperte: nessuna fonte piu' debole puo' sovrascrivere una
        piu' forte.
        """
        idx = tm_player_id.index
        tm = pd.Series(tm_player_id, index=idx).astype("Int64")
        dt = pd.to_datetime(pd.Series(data, index=idx), errors="coerce")
        club = pd.Series(pd.NA, index=idx, dtype="Int64")
        fonte = pd.Series(FONTE_IGNOTA, index=idx, dtype=object)
        conf = pd.Series(pd.NA, index=idx, dtype=object)

        # 1. comparsa esatta: osservazione diretta, batte tutto
        if not self.comparse.empty:
            q = pd.DataFrame({"tm_player_id": tm, "data": dt.dt.normalize()})
            c = self.comparse.rename(columns={"club_id": "_c"}).copy()
            c["tm_player_id"] = c["tm_player_id"].astype("Int64")
            prima = len(q)
            r = q.merge(c, on=["tm_player_id", "data"], how="left")
            if len(r) != prima:
                raise RuntimeError(f"comparse: chiave (tm_player_id, data) non "
                                   f"univoca, l'unione ha cambiato le righe "
                                   f"({prima} -> {len(r)})")
            r.index = idx
            trovato = r["_c"].notna()
            club = club.mask(trovato, r["_c"].astype("Int64"))
            fonte = fonte.mask(trovato, _FONTE_DI["comparsa"])
            # una comparsa esatta e' l'osservazione di quel giorno: mai inferenza
            conf = conf.mask(trovato, PROVA)

        # 2..4. intervalli, in ordine di priorita'
        for chiave in _PRIORITA[1:]:
            scoperte = club.isna()
            if not scoperte.any():
                break
            iv = self._per_fonte(chiave)
            if iv.empty:
                continue
            trovato = _cerca_intervallo(iv, tm[scoperte], dt[scoperte])
            ok = trovato.notna()
            if ok.any():
                club.loc[trovato.index[ok]] = trovato[ok]
                fonte.loc[trovato.index[ok]] = _FONTE_DI[chiave]
                c = trovato.attrs.get("confidenza")
                if c is not None:
                    conf.loc[trovato.index[ok]] = c[ok]
        return pd.DataFrame({"club_id_alla_data": club, "fonte": fonte,
                             "confidenza": conf}, index=idx)

    def verifica_molti(self, tm_player_id: pd.Series, club_id: pd.Series,
                       data: pd.Series) -> pd.DataFrame:
        """Versione vettoriale di `verifica()`.

        Colonne restituite: `esito` (`si`/`no`/`ignoto`), `fonte`,
        `club_id_alla_data`, `confidenza` (`prova`/`inferenza`/nullo).

        `confidenza` dice se la risposta poggia su una prova che copre quella
        data oppure sul prolungamento in avanti dell'ultima prova disponibile.
        Chi stima una propensione deve poter separare i due casi: un'inferenza
        di continuita' non e' un'osservazione.
        """
        idx = tm_player_id.index
        r = self.risolvi_molti(tm_player_id, data)
        chiesto = pd.Series(club_id, index=idx).astype("Int64")
        noto = r["club_id_alla_data"].notna() & chiesto.notna()
        esito = pd.Series(IGNOTO, index=idx, dtype=object)
        esito = esito.mask(noto & (r["club_id_alla_data"] == chiesto), SI)
        esito = esito.mask(noto & (r["club_id_alla_data"] != chiesto), NO)
        fonte = r["fonte"].where(noto, FONTE_IGNOTA)

        # non appartenenza dichiarata: vale solo dove nessuna fonte positiva ha
        # gia' risposto. Non puo' contraddire una risposta `si`, perche' quella
        # viene da una prova piu' forte; puo' pero' trasformare un `ignoto` in
        # un `no`, che e' informazione vera e non un'assenza inventata.
        if len(self.non_appartenenza):
            aperte = esito == IGNOTO
            if aperte.any():
                dt = pd.to_datetime(pd.Series(data, index=idx), errors="coerce")
                tm = pd.Series(tm_player_id, index=idx).astype("Int64")
                negato = _cerca_intervallo(self.non_appartenenza,
                                           tm[aperte], dt[aperte])
                colpite = negato.notna() & (negato == chiesto[aperte])
                if colpite.any():
                    bersagli = negato.index[colpite.fillna(False)]
                    esito.loc[bersagli] = NO
                    fonte.loc[bersagli] = FONTE_LISTONE
        return pd.DataFrame({"esito": esito, "fonte": fonte,
                             "club_id_alla_data": r["club_id_alla_data"],
                             "confidenza": r["confidenza"]},
                            index=idx)


# --------------------------------------------------------------------------
# costruzione
# --------------------------------------------------------------------------

def costruisci(ids: set[int] | None = None, *,
               as_of=None,
               estendi_fino=None,
               usa_cache: bool = True,
               data_scatto_listone=None) -> TabellaAppartenenza:
    """Legge le tre fonti e costruisce la tabella degli intervalli.

    Parametri
    ---------
    ids
        identificativi Transfermarkt da tenere. `None` significa «quelli
        dedotti da `_identita_note()`».
    as_of
        data limite informativa, stringa `AAAA-MM-GG` o `Timestamp`, **esclusa**
        (`data < as_of`). Filtra le prove *prima* di risolvere i conflitti e di
        costruire gli intervalli: comparse e trasferimenti anteriori, orizzonte
        dei trasferimenti ricalcolato sui soli ammessi, listone solo se lo
        scatto e' anteriore.

        `as_of=None` (predefinito) significa **nessuna censura**: la tabella usa
        tutte le prove note oggi. E' il comportamento storico e resta
        disponibile per la descrizione storica — «com'e' andata» — ma **non**
        per costruire le informazioni di un backtest o di una decisione datata,
        perche' contiene prove che a quella data non esistevano.
    usa_cache
        tiene il risultato in una cache di processo. La chiave comprende
        `as_of`, l'insieme degli `ids` e l'impronta dei file sorgente: due
        `as_of` diversi non condividono mai una voce.
    data_scatto_listone
        data in cui `kader_2026.csv` e' stato scaricato. Il file non la
        contiene: senza questo parametro vale `DATA_SCATTO_LISTONE`, dichiarata
        nel modulo con la sua provenienza e il suo limite. Non e' dedotta in
        silenzio a ogni chiamata.

    La lettura di `game_lineups.csv.gz` (125 MB compressi, 3,18 milioni di
    righe) e' la parte lenta, misurata 6,7 secondi: per questo le fonti grezze
    hanno una cache propria, cosi' che chiedere piu' date limite sullo stesso
    insieme di identificativi la paghi una volta sola.
    """
    as_of_ts = None if as_of is None else pd.Timestamp(as_of)
    scatto = (DATA_SCATTO_LISTONE if data_scatto_listone is None
              else pd.Timestamp(data_scatto_listone))

    if ids is None:
        ids = _identita_note()
    est_ts = None if estendi_fino is None else pd.Timestamp(estendi_fino)
    if est_ts is not None and as_of_ts is not None and est_ts < as_of_ts:
        raise ValueError(
            f"estendi_fino ({est_ts.date()}) e' anteriore ad as_of "
            f"({as_of_ts.date()}): un'estensione all'indietro non ha senso")
    chiave = "|".join([_impronta_ids(ids),
                       "-" if as_of_ts is None else as_of_ts.isoformat(),
                       "-" if est_ts is None else est_ts.isoformat(),
                       scatto.isoformat(),
                       _impronta_file()])
    if usa_cache and chiave in _CACHE:
        return _CACHE[chiave]

    diagnostica: dict = {"identita_richieste": len(ids),
                         "as_of": None if as_of_ts is None
                         else str(as_of_ts.date())}
    estendi_fino = est_ts

    chiave_fonti = "|".join([_impronta_ids(ids), _impronta_file()])
    if chiave_fonti in _CACHE_FONTI:
        grezze = _CACHE_FONTI[chiave_fonti]
    else:
        grezze = {"comparse": _comparse(ids),
                  "trasferimenti": _leggi_trasferimenti(ids)}
        _CACHE_FONTI[chiave_fonti] = grezze

    # --- censura delle prove, prima di qualunque risoluzione ---------------
    comparse = grezze["comparse"]
    trasf = grezze["trasferimenti"]
    comparse_totali, trasf_totali = int(len(comparse)), int(len(trasf))
    if as_of_ts is not None:
        comparse = comparse[comparse["data"] < as_of_ts]
        trasf = trasf[trasf["data"] < as_of_ts]
    comparse = comparse.copy()
    trasf = trasf.copy()
    diagnostica["prove_ammesse"] = {
        "comparse": int(len(comparse)), "trasferimenti": int(len(trasf))}
    diagnostica["prove_scartate"] = {
        "comparse": comparse_totali - int(len(comparse)),
        "trasferimenti": trasf_totali - int(len(trasf))}

    diagnostica["comparse_righe"] = int(len(comparse))
    diagnostica["comparse_giocatori"] = int(comparse.tm_player_id.nunique()) \
        if len(comparse) else 0
    if len(comparse):
        diagnostica["comparse_data_min"] = str(comparse.data.min().date())
        diagnostica["comparse_data_max"] = str(comparse.data.max().date())
        # se un giocatore risultasse a referto per due club lo stesso giorno la
        # regola «la comparsa esatta batte tutto» sarebbe ambigua: va misurato
        doppi = comparse.groupby(["tm_player_id", "data"])["club_id"].nunique()
        diagnostica["comparse_stesso_giorno_due_club"] = int((doppi > 1).sum())
        if diagnostica["comparse_stesso_giorno_due_club"]:
            # tolgo le date ambigue: una prova che si contraddice non e' prova
            amb = doppi[doppi > 1].index
            comparse = comparse[~pd.MultiIndex.from_frame(
                comparse[["tm_player_id", "data"]]).isin(amb)]

    # `estendi_fino`: fin dove le affermazioni valgono in avanti.
    #
    # Senza estensione, ogni intervallo si chiude sull'ultima prova ammessa e
    # sotto censura nessuna domanda posteriore alla decisione riceve risposta:
    # misurato, il panel passa al 100% `ignoto` in tutte e tre le stagioni.
    # Ma un trasferimento del primo luglio dice «da quel giorno e' di quel
    # club», e quell'affermazione vale in avanti finche' un'altra prova non la
    # smentisce. E' inferenza dal passato, non informazione futura, e va
    # distinta dalla prova diretta invece che soppressa: `prova_al` conserva il
    # bordo sostenuto da una prova, e chi interroga oltre riceve
    # `confidenza = "inferenza"`.
    #
    # L'orizzonte dell'estensione e' un parametro dichiarato, non una costante
    # scelta perche' fa tornare i conti: chi costruisce la tabella dice fin
    # dove e' disposto a estrapolare, e quel valore finisce nella diagnostica.
    diagnostica["estendi_fino"] = (None if estendi_fino is None
                                   else str(pd.Timestamp(estendi_fino).date()))
    tr, orizzonte, dtr = _intervalli_trasferimenti_da(trasf, estendi_fino)
    diagnostica.update(dtr)
    diagnostica["fonte_trasferimenti"] = trasf.attrs.get("fonte", "ignota")
    diagnostica["orizzonte_effettivo"] = str(orizzonte.date())
    spell = _spell_da_comparse(comparse, estendi_fino)
    diagnostica["spell_intervalli"] = int(len(spell))
    lis, lis_no, dli = _intervalli_listone(as_of=as_of_ts, data_scatto=scatto)
    diagnostica.update(dli)
    diagnostica["prove_ammesse"]["listone"] = dli.get("listone_righe_ammesse", 0)
    diagnostica["prove_scartate"]["listone"] = dli.get("listone_righe_scartate", 0)

    # validazione della fonte piu' solida contro l'osservazione diretta
    tr_validi, dval = _valida_contro_comparse(
        tr[~tr.ambiguo][["tm_player_id", "club_id", "dal", "al", "prova_al"]],
        comparse)
    diagnostica.update(dval)

    pezzi = []
    if len(tr_validi):
        pezzi.append(tr_validi.assign(origine="trasferimenti")[
            ["tm_player_id", "club_id", "dal", "al", "prova_al", "origine"]])
    if len(spell):
        pezzi.append(spell.assign(origine="spell"))
    if len(lis):
        # Il listone dichiara la rosa alla data dello scatto. Da quel giorno in
        # avanti l'affermazione e' inferenza di continuita', non osservazione:
        # `prova_al` si ferma allo scatto piu' un giorno.
        pezzi.append(lis.assign(origine="listone",
                                prova_al=scatto + pd.Timedelta(days=1)))
    iv = (pd.concat(pezzi, ignore_index=True) if pezzi else
          pd.DataFrame(columns=["tm_player_id", "club_id", "dal", "al", "origine"]))
    if len(iv):
        iv["tm_player_id"] = iv["tm_player_id"].astype("int64")
        iv["club_id"] = iv["club_id"].astype("int64")
        iv["fonte"] = iv["origine"].map(_FONTE_DI)

    # ultima data su cui la tabella puo' affermare qualcosa. Sotto censura vale
    # al piu' `as_of`, perche' ogni fonte qui dentro chiude il proprio bordo
    # destro sull'ultima prova disponibile: chi interroga oltre riceve `ignoto`
    # e deve saperlo prima, non dedurlo dai risultati vuoti.
    diagnostica["data_massima_risolvibile"] = (
        str(iv["al"].max().date()) if len(iv) else None)

    if len(lis_no):
        lis_no = lis_no.copy()
        lis_no["tm_player_id"] = lis_no["tm_player_id"].astype("int64")
        lis_no["club_id"] = lis_no["club_id"].astype("int64")
    t = TabellaAppartenenza(intervalli=iv, comparse=comparse,
                            orizzonte_trasferimenti=orizzonte,
                            non_appartenenza=lis_no,
                            diagnostica=diagnostica,
                            as_of=as_of_ts)

    # controllo residuo: dopo lo scarto, quante comparse restano in disaccordo
    # con l'intervallo che le copre? Deve essere zero, perche' ogni intervallo
    # smentito e' stato tolto. Se non lo fosse, la validazione avrebbe un buco.
    if len(comparse) and len(tr_validi):
        prev = _cerca_intervallo(tr_validi,
                                 comparse.tm_player_id.reset_index(drop=True),
                                 comparse.data.reset_index(drop=True))
        osservato = comparse.club_id.reset_index(drop=True)
        confrontabili = prev.notna()
        diagnostica["controllo_comparse_confrontate"] = int(confrontabili.sum())
        diagnostica["contraddizioni_trasferimenti_formazioni"] = int(
            (confrontabili & (prev != osservato)).sum())

    if usa_cache:
        _CACHE[chiave] = t
    return t


def scrivi_diagnostica(t: TabellaAppartenenza, destinazione: Path) -> None:
    """Salva la diagnostica in JSON, per poterla citare in un rapporto."""
    destinazione.parent.mkdir(parents=True, exist_ok=True)
    destinazione.write_text(json.dumps(t.diagnostica, indent=1, default=str),
                            encoding="utf-8")
