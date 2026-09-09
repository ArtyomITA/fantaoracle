# Livello 4 — prezzi. Fase 8A: unità di osservazione e inventario delle aste reali

Data: 8 settembre 2026. Prodotto da `scripts/l4_inventario_aste.py`.
Regole applicate: `reports/PROTOCOLLO_v2.md` (stato di ogni conclusione §1, unità
inferenziale §3.3, tracciabilità degli artefatti §6, condizioni di arresto §8).

Questo documento è il **contratto dei dati** su cui poggia tutto il Livello 4.
Definisce che cosa sia «un'asta», quante ne abbiamo davvero, che cosa ciascuna
ci dice, che cosa non ci dirà mai, e quali sono i due bersagli che il modello
dei prezzi può ragionevolmente inseguire.

## 0. Riproduzione

```
cd "fantabot"
set PYTHONPATH=src
python scripts/l4_inventario_aste.py --outdir data/l4 --boot 1000 --seed 20260908
```

Costo misurato: 76 secondi, picco di RSS **0,190 GB** (processo singolo).

Input e impronte (SHA-256):

| file | ruolo | sha256 |
|---|---|---|
| `data/raw/gruppoesperti/aste_reali_tidy.csv` | unico input sostanziale | `d3ec7d0b063a7…62d663` |
| `data/raw/gruppoesperti/build_stats.json` | riscontro sul parser di origine | `72cea675b3cd6…36359452` |
| `data/processed/_match/map_ge.csv` | **solo** controllo di sensibilità sull'identità del giocatore | `2438a6a1e690f…5b921a94` |

Artefatti prodotti, tutti in `data/l4/`:

| file | contenuto |
|---|---|
| `l4_inventario_aste.csv` | 245 righe, una per (`source_file`, `auction_id`), con chiave globale, configurazione, copertura ruoli |
| `l4_aste_uniche.csv` | 216 righe, una per asta reale (versione canonica del cluster) |
| `l4_coppie_sospette.csv` | tutte le coppie con sovrapposizione di prezzi ≥ 0,20 oppure di nomi ≥ 0,80 |
| `l4_prezzi_per_giocatore.csv` | 1.705 righe (stagione, ruolo, giocatore): numero di aste, media, sd, min, max, CV |
| `l4_inventario.json` | tutte le misure di questo report, i parametri, le impronte degli input |

Lo script non modifica nulla fuori da `data/l4/`. La pipeline prezzi esistente
(`scripts/f0b_*`, `scripts/f1_*`) non è stata toccata; dove servirebbe un
cambiamento, è dichiarato come dipendenza in §9.

---

## 1. Il risultato che viene per primo

**L'identità dell'asta è ricostruibile a livello di evento, non a livello di
lotto.** Le due metà di questa frase hanno conseguenze opposte e vanno lette
insieme.

Ricostruibile: esiste una chiave di contenuto che separa le aste in modo netto,
con un **intervallo completamente vuoto** fra le sovrapposizioni delle copie
(≥ 0,816) e quelle delle aste distinte (≤ 0,28). Su 29.890 coppie possibili,
**zero** cadono fra 0,30 e 0,80. La partizione non dipende dalla soglia scelta:
qualunque valore in quell'intervallo produce le stesse **216 aste reali**.
Stato: **riprodotta**.

Non ricostruibile: la tabella tidy **non contiene** ordine dei lotti,
proprietari, né marche temporali. Verificato sulle 10 colonne effettive. Ne
segue che un'asta reale, per noi, è un **insieme non ordinato e anonimo di
coppie (giocatore, prezzo)** con la sua configurazione di lega. Non è una
sequenza di eventi. Questo è un **limite duro per la fase 8D**: senza l'ordine
dei lotti un replay reale non è possibile, e ogni permutazione dell'ordine è un
esperimento sintetico, da chiamare così. Stato: **riprodotta**.

---

## 2. L'unità di osservazione

### 2.1 Le tre numerosità, riconciliate

Il committente aveva letto tre numeri, tutti confermati sull'input corrente:

| lettura | valore | verificato |
|---|---:|---|
| righe della tabella tidy | 55.678 | sì |
| valori distinti di `auction_id` | 140 | sì |
| coppie distinte (`source_file`, `auction_id`) | 245 | sì |

E un vecchio report parlava di «216 aste». **Il numero 216 è riconciliato**, e
non va preso a scatola chiusa: è il numero di cluster di contenuto ottenuto
deduplicando le 245 aste di file. Coincide con quello prodotto da
`scripts/f0b_build_outputs.py` (misurato: `data/processed/aste_reali_clean.csv`
contiene 48.624 righe e 216 gruppi), e questo lavoro lo riottiene con una
procedura indipendente e con la giustificazione che a quel numero mancava.

La catena completa è:

```
245 aste di file
 -20 copie identiche (13 gruppi, impronta esatta)            -> 225 impronte distinte
  -9 versioni quasi identiche (sovrapposizione 0,816-0,985)  -> 216 aste reali
```

### 2.2 `auction_id` non è un identificativo globale — misurato

`auction_id` è un progressivo interno al file: ogni file parte da 1 e arriva al
proprio conteggio (1-140, 1-55, 1-24, 1-15, 1-11). Di conseguenza **55 dei 140
valori compaiono in più di un file**, e un valore compare fino a **5 file**
diversi. Da solo non identifica niente.

### 2.3 La coppia (file, `auction_id`) è un'unità coerente — misurato

Perché la coppia possa fare da unità, la configurazione deve esserne una
funzione. Verificato su tutte e 245: il numero di aste con più di un valore per
`componenti`, `crediti_tot`, `modificatore`, `periodo` è **0** in tutti e
quattro i casi. La coppia è quindi l'unità **così com'è scritta**; resta da
capire quante coppie siano lo stesso evento.

### 2.4 L'elenco dei giocatori non identifica l'asta — misurato

Questa è la misura che motiva la componente decisiva della chiave. Se si prova
a identificare l'asta con l'insieme dei suoi giocatori (ruolo + nome, senza
prezzo), si trovano **6.527 coppie** di aste che condividono almeno l'80 % dei
giocatori pur essendo eventi diversi (sovrapposizione di prezzi sotto 0,30).
È ovvio a posteriori — le leghe pescano tutte dallo stesso listone — ma è il
tipo di ovvietà che va misurata prima di scartare un'alternativa:
l'istogramma delle sovrapposizioni sui soli nomi è continuo e non ha nessun
intervallo vuoto, quindi non esiste nessuna soglia difendibile su quel campo.

### 2.5 I prezzi identificano, e con un margine enorme

Misura usata: per ogni coppia di aste, |A ∩ B| / min(|A|, |B|) sugli insiemi di
triple (ruolo, nome normalizzato, prezzo). Il minimo al denominatore e non
l'unione, perché una versione **parziale** della stessa asta deve risultare
molto sovrapposta a quella completa: con l'unione una copia a metà darebbe 0,5
e sfuggirebbe.

Distribuzione su 29.890 coppie:

| intervallo | coppie |
|---|---:|
| [0,00 – 0,10) | 26.359 |
| [0,10 – 0,20) | 3.477 |
| [0,20 – 0,30) | 13 |
| **[0,30 – 0,80)** | **0** |
| [0,80 – 0,90) | 6 |
| [0,90 – 0,95) | 6 |
| [0,95 – 1,00] | 29 |

Massimo sotto l'intervallo vuoto: **0,280**. Minimo sopra: **0,816**. Le due
popolazioni non si toccano.

### 2.6 La chiave adottata

> **Chiave dell'asta reale.** Due aste di file appartengono allo stesso evento
> se la sovrapposizione dei loro insiemi di triple (ruolo, nome normalizzato,
> prezzo), normalizzata sul minimo delle due cardinalità, è ≥ **0,70**. Le
> aste reali sono le componenti connesse della relazione (chiusura transitiva).
> L'identificativo `asta_uid` è la coppia (`source_file`, `auction_id`) della
> versione **più completa** del cluster; a parità di righe, la coppia minima in
> ordine lessicografico.

Ogni componente della chiave ha la sua misura, non un'intuizione:

| componente | perché c'è | misura |
|---|---|---|
| prezzo nella tripla | senza, non c'è nessuna soglia difendibile | 6.527 coppie con ≥ 80 % di nomi in comune ma eventi diversi |
| min al denominatore | intercetta le versioni parziali | la coppia più debole (0,816) ha 250 e 250 righe; con l'unione al denominatore le coppie a cardinalità diversa scenderebbero sotto soglia |
| soglia 0,70 | cade nell'intervallo vuoto | 0 coppie fra 0,30 e 0,80 |
| chiusura transitiva | i cluster hanno fino a 3 versioni | 12 cluster da 3, 5 da 2, 199 singoli |
| versione più completa | non buttare righe | recupera 2 aste a quote esatte 3/8/8/6 rispetto alla scelta lessicografica |

**Sensibilità della soglia**, misurata: il numero di aste reali resta 216 per
ogni soglia da 0,30 a 0,80; sale a 217 a 0,85, 220 a 0,90, 223 a 0,95, 225 a
1,00. Il valore 0,70 non è calibrato sui risultati: è il centro dell'intervallo
in cui il risultato non cambia.

---

## 3. Duplicati e versioni — quantificati, non rimossi in silenzio

### 3.1 Che cosa si trova

| fenomeno | quantità |
|---|---|
| copie con impronta identica (configurazione + insieme di triple) | 13 gruppi, **20 aste in eccesso** |
| versioni quasi identiche unite dalla soglia | 14 coppie non identiche, **9 aste in eccesso** |
| coppie unite in tutto | 41 (di cui **3 dentro lo stesso file**) |
| cluster con più di una versione | 17 |
| righe ripetute dentro la stessa asta (stesso ruolo + nome) | **298 coppie (asta, giocatore)** su 27 aste |

### 3.2 Rettifica al report della fonte

`data/raw/gruppoesperti/REPORT.md` scrive: «Nessun duplicato interno ai singoli
file», e `build_stats.json` registra `dups_intra: []`. **È vero solo per le
impronte esatte.** Con la misura di sovrapposizione emergono **3 coppie di
quasi-duplicati dentro lo stesso file**:

| file | aste | sovrapposizione prezzi | configurazione |
|---|---|---:|---|
| `extra/1MeKG7…` | 27 ~ 33 | 0,985 | 8×250 |
| `extra/1J4t…` | 12 ~ 21 | 0,935 | 10×1000 |
| `gruppoesperti_…2021-22circa` | 125 ~ 138 | 0,816 | **10×500** |

L'ultima è dentro lo strato che ci interessa di più.

### 3.3 Effetto misurato della regola di deduplica

Sui 17 cluster con più versioni:

- **174 giocatori** compaiono nell'unione delle versioni ma non nella versione
  canonica. Le versioni sono trascrizioni **parziali**, non contraddittorie.
- Fra i giocatori presenti in almeno due versioni, il prezzo è **discorde in 25
  casi su 3.891 (0,64 %)**.

Perciò la regola adottata **non fonde** le versioni: dove due versioni si
contraddicono non esiste un criterio per decidere quale sia giusta, e la
fusione produrrebbe un'asta mai avvenuta. Costo dichiarato della scelta: 174
acquisti non entrano nel dataset.

### 3.4 L'unico accostamento ambiguo, con la sua diagnosi

I 25 disaccordi non sono sparsi. Ripartiti per cluster:

| cluster | disaccordi per ruolo |
|---|---|
| `extra/1J4t…#3` | D: 1 |
| `extra/1J4t…#12` | D: 1 |
| `extra/1MeKG7…#27` | A: 2 |
| **`gruppoesperti_…2021-22circa#125`** (con `#138`) | **P: 21** |

Nell'ultimo caso le due aste hanno 250 righe ciascuna, stessa configurazione
10×500, stesso modificatore `M`, ma `periodo` diverso (1 contro 2). Le 204
triple identiche riguardano difensori, centrocampisti e attaccanti; **tutte e
21 le differenze sono portieri**. Che due aste realmente distinte producano 204
prezzi identici è implausibile; che la sezione portieri sia stata reinserita o
corretta è la lettura naturale. Il punto rilevante è che **non sappiamo quale
delle due colonne portieri sia quella buona**, e la regola ne sceglie una per
un criterio di ordinamento, non per una prova.

Trattamento dichiarato: le due restano unite (`asta_uid` = `…#125`), e la coppia
è segnata come l'unico accostamento con un'ambiguità sostanziale. Chi lavorerà
sui portieri in 8B/8C deve saperlo. L'alternativa — tenerle separate — darebbe
217 aste e duplicherebbe i 204 lotti a prezzo identico (201 dei quali fuori dal ruolo P); è la ragione per cui
non è stata scelta, ed è la stessa cosa che la riga «0,85 → 217» della tabella
di sensibilità mostra.

### 3.5 Righe ripetute dentro l'asta

298 coppie (asta, giocatore) hanno più di una riga, su 27 aste. Di queste, 41
hanno prezzi identici e **257 hanno prezzi diversi**, con scarto relativo
mediano **0,63** — cioè il prezzo alto è quasi il doppio del basso. Non sono
due martelletti dello stesso giocatore nella stessa asta: sono trascrizioni
corrotte. Nelle misure dei bersagli (§6) è tenuta la **prima** occorrenza, e la
scelta è arbitraria; le 27 aste coinvolte sono identificabili in
`l4_inventario_aste.csv` con `n_lotti != n_giocatori_distinti` (32 aste
canoniche su 216) e vanno considerate sospette.

---

## 4. Inventario delle 216 aste reali

### 4.1 Stagione

| stagione | aste | come è stabilita |
|---|---:|---|
| 2021-22 | 139 | marcatore di rosa **per file**, non per asta |
| 2023-24 | 54 | idem |
| 2024-25 | 23 | idem |
| 2022-23 | **0** | assente |
| 2025-26 | **0** | assente |
| 2026-27 (la nostra) | **0** | per definizione |

Limite dichiarato: la stagione è attribuita al **file**, non all'asta, dai
marcatori di rosa annotati in `data/raw/gruppoesperti/REPORT.md`, e ripresa da
`scripts/f0b_match.py`. Nessuna asta porta con sé una data. Un file può
contenere aste di stagioni diverse e questo controllo non è stato fatto da
nessuno; le aste con `periodo` alto potrebbero essere riparazioni invernali.
Stato: **assunzione ereditata, non verificata in questa fase**.

### 4.2 Periodo

| `periodo` | aste |
|---:|---:|
| 0 | 69 |
| 1 | 21 |
| 2 | 88 |
| 3 | 38 |

`periodo` è una cella numerica letta verbatim dal foglio sotto l'etichetta
`PERIODO` (`scripts/ge_parser.py`, riga 102). **La sua semantica non è
documentata da nessuna parte.** La lettura «0 = asta estiva, valori più alti =
più a ridosso o dopo l'inizio del campionato» è un'interpretazione scritta in
`REPORT.md`, non una prova. Che 2021-22 non abbia nessun `periodo` 3 e 2023-24
ne abbia 28 su 54 suggerisce che la scala non sia nemmeno usata allo stesso
modo fra file.

**Conseguenza operativa:** la richiesta «pre-campionato o dopo K giornate» **non
è soddisfacibile**. Possiamo distinguere quattro classi ordinali senza sapere a
che cosa corrispondano, e non possiamo tradurle in un numero di giornate.
Questo è un blocco che dipende dal committente o dal thread del forum, non una
cosa che si risolve leggendo meglio il file. Stato: **bloccata**.

### 4.3 Configurazione

Modificatore, sulle 216: `N` 86, `+1M` 56, `M` 55, vuoto 15, `+1` 4. La
semantica dei quattro codici non è documentata; l'unica lettura che si può
azzardare senza inventare è che `N` significhi «nessun modificatore» e gli
altri tre qualcosa di attivo, il che dà **115 aste con modificatore attivo** e
15 senza informazione (tutte del file 2024-25). Anche questa è
**un'assunzione**: `+1M` contro `M` contro `+1` non è decidibile con i dati
presenti.

Le dieci configurazioni (partecipanti × crediti) più frequenti:

| configurazione | aste |
|---|---:|
| **10×500** | **56** |
| 8×500 | 49 |
| 8×1000 | 28 |
| 10×1000 | 22 |
| 10×300 | 14 |
| 6×1000 | 5 |
| 10×250 | 4 |
| 12×1000 | 4 |
| 8×300 | 4 |
| 12×500 | 3 |

Coda lunga: altre 20 configurazioni con 1-2 aste ciascuna (30 in tutto). Partecipanti: 10
(102 aste), 8 (94), 12 (10), 6 (10). Crediti: 500 (110), 1000 (59), 300 (20),
800 (6), 250 (7), e altri otto valori residui (13 in tutto).

### 4.4 Lotti e copertura dei ruoli

Numero di lotti per asta: mediana 239,5; quartili 200 e 250; minimo 150,
massimo 320.

Nessuna asta ha un ruolo completamente assente. Le quote per partecipante hanno
mediana esattamente 3 / 8 / 8 / 6 in tutti e quattro i ruoli, con code in
entrambe le direzioni (portieri da 0,875 a 5,7 per partecipante).

Rispetto all'atteso 25 lotti per partecipante:

| | aste |
|---|---:|
| lotti esattamente pari all'atteso | 121 |
| meno dell'atteso (mediana 2,5 lotti mancanti, fino a 50) | 66 |
| più dell'atteso (mediana 25 lotti in più, fino a 50) | 29 |

Le 29 aste con lotti in eccesso sono con ogni probabilità aste con un
`componenti` sbagliato inserito a mano, non aste con rose gonfiate: 25 lotti in
più sono esattamente una rosa.

**Le quote non sono una colonna.** `3/8/8/6` non è mai scritto da nessuna parte:
si può solo verificare a posteriori che i conteggi dei ruoli lo rispettino. Il
conteggio dice **119 aste su 216**, ma questa cifra è **confusa con la
completezza della trascrizione**: un'asta trascritta a metà non può mai esibire
le quote esatte. Fra le 121 aste con conteggio completo, 119 hanno 3/8/8/6.
Detto correttamente: **fra le aste per cui la domanda è ponibile, quasi tutte
(119/121) usano 3/8/8/6**; per le altre 95 non lo sappiamo.

### 4.5 Contabilità della spesa

Rapporto fra spesa totale e budget teorico (partecipanti × crediti): mediana
0,976; decimo percentile 0,899; massimo 1,379. **22 aste spendono più del
budget** e 12 superano il 110 %. Sono errori di trascrizione o di `componenti`,
non aste vere: nessun regolamento permette di sfondare il budget. La colonna
`spesa_su_budget` è in `l4_aste_uniche.csv` per filtrarle.

Prezzi a zero: 55 righe su 5 aste (assegnazioni d'ufficio o svincoli), non
filtrate.

### 4.6 Che cosa manca, e per quante aste

| informazione | disponibile per | mancante per |
|---|---|---|
| partecipanti, crediti totali | 216 / 216 | 0 |
| modificatore (codice grezzo) | 201 / 216 | 15 |
| modificatore (semantica) | **0 / 216** | 216 — codici non documentati |
| periodo (codice ordinale) | 216 / 216 | 0 |
| periodo (in giornate o data) | **0 / 216** | 216 — semantica ignota |
| stagione | 216 / 216, ma stimata **per file** | attribuzione per asta mai verificata |
| quote di rosa | **0 / 216** come colonna; inferibili per 121 | 95 |
| numero di lotti | 216 / 216 | 0, ma 95 non tornano con l'atteso |
| copertura dei ruoli | 216 / 216 | 0 |
| ordine dei lotti | **0 / 216** | 216 |
| proprietari / squadre acquirenti | **0 / 216** | 216 |
| marche temporali | **0 / 216** | 216 |

---

## 5. Che cosa non c'è — verificato

Le colonne effettive della tabella tidy sono dieci: `source_file`,
`auction_id`, `componenti`, `crediti_tot`, `modificatore`, `periodo`, `ruolo`,
`player_raw`, `prezzo`, `pct_budget`. Cercando nei nomi di colonna le radici di
ordine (`ordine`, `order`, `lotto`, `seq`, `turno`, `chiamata`, `numero`, …),
di proprietà (`squadra`, `team`, `owner`, `acquirente`, `partecipante`,
`manager`, …) e di tempo (`data`, `date`, `ora`, `timestamp`, `orario`, …), le
corrispondenze sono **zero in tutti e tre i casi**. La segnalazione del
committente è confermata.

Conseguenze, da scrivere accanto a ogni risultato che ne dipenda:

1. **Fase 8D (adattamento durante l'asta): nessun replay reale è possibile.**
   Non sappiamo in che ordine i lotti sono stati battuti. Qualunque simulazione
   di un'asta storica deve inventare un ordine, e quindi è un **esperimento
   sintetico** condizionato a quell'ordine, non una riproduzione. Le
   permutazioni dell'ordine dei lotti misurano la sensibilità di una politica a
   un'ipotesi, non la sua prestazione storica.
2. **Nessun vincolo di rosa verificabile.** Senza proprietari non si può
   controllare che ogni squadra abbia rispettato budget e quote, né studiare la
   dinamica «chi ha ancora crediti». La contabilità è possibile solo in
   aggregato (§4.5), ed è lì che si vedono le 22 aste che sfondano il budget.
3. **Nessuna informazione temporale interna all'asta.** Non si può separare la
   fase iniziale dai saldi finali, che è esattamente il fenomeno che 8D dovrebbe
   sfruttare.
4. **Nessuna data assoluta.** Per il vincolo di informazione temporale del
   Protocollo v2 §2 (le sei date da tenere separate) queste aste portano solo
   una stagione stimata per file. Una data di decisione per asta **non esiste**.

---

## 6. I due bersagli sono davvero due

### 6.1 Definizioni

- **Martelletto individuale** — il prezzo che *quella* squadra ha pagato per
  *quel* giocatore in *quella* asta. È un'osservazione singola, non ripetibile.
- **Prezzo medio fra aste** — la media dei martelletti dello stesso giocatore,
  nella stessa stagione, su tutte le aste disponibili con una configurazione
  comparabile. È una stima di una tendenza centrale, e la sua incertezza si
  riduce con il numero di aste.

Sono grandezze diverse con dispersione diversa, e confonderle produce intervalli
di previsione sbagliati per un fattore misurabile.

### 6.2 Scomposizione della varianza

Universo: le 216 aste canoniche, una riga per (asta, giocatore), identità del
giocatore = (stagione, ruolo, nome normalizzato), limitatamente ai giocatori
visti in **almeno due aste**. Procedura: media generale, media del giocatore,
livello dell'asta calcolato come media dentro l'asta dei residui dal giocatore,
residuo. I termini incrociati sono riportati invece di essere assunti nulli.

Strato omogeneo **10×500** — 56 aste, 1.111 giocatori, 13.626 osservazioni,
variabile `pct_budget`:

| componente | quota della varianza |
|---|---:|
| identità del giocatore | **89,8 %** |
| livello dell'asta | 0,11 % |
| idiosincratico (giocatore × asta) | **10,0 %** |
| termini incrociati | 0,0 % |

Su tutte le configurazioni (216 aste, 48.332 osservazioni), sempre su
`pct_budget`: giocatore 84,9 %, livello dell'asta 0,82 %, idiosincratico
14,3 %. Su `log(1+prezzo)` e tutte le configurazioni: giocatore 72,7 %, livello
dell'asta **6,3 %**, idiosincratico 21,1 %.

Il livello dell'asta è quasi nullo su `pct_budget` **per una ragione
strutturale, non per assenza del fenomeno**: la somma dei `pct_budget` dentro
un'asta è quasi fissata dal budget (mediana 0,976, §4.5), quindi non esiste
un'«asta inflazionata» in termini relativi. Il 6,3 % che compare su
`log(prezzo)` a configurazioni miste è l'effetto di budget e partecipanti
diversi, non di aste più o meno generose. Chi userà `pct_budget` deve sapere che
sta lavorando con una variabile a somma quasi costante: è un vincolo, non una
comodità.

### 6.3 Dispersione entro asta e fra aste — la domanda va riformulata

L'incarico chiedeva «quanto la dispersione fra aste supera quella entro asta».
**Nella lettura letterale la domanda non è ponibile**, e questa è la prima cosa
da dire: dentro una singola asta ogni giocatore compare al massimo una volta,
quindi la dispersione entro asta *a giocatore fisso* è zero per costruzione, non
per misura. L'unica traccia empirica sono le 257 righe ripetute con prezzi
discordi (§3.5), che sono errori di trascrizione e valgono al massimo come
limite superiore di quanto la fonte sia rumorosa (scarto relativo mediano 0,63).

Le due quantità che si possono misurare e confrontare, nello strato 10×500,
sono:

| quantità | mediana (`pct_budget`) | in crediti su 500 |
|---|---:|---:|
| dispersione **trasversale entro asta** (fra giocatori, dentro la stessa asta) | 0,0623 | 31,2 |
| dispersione **fra aste** dello stesso giocatore | 0,00765 | 3,8 |

Rapporto: **0,123**. Cioè, contrariamente a quanto la formulazione lasciava
attendere, la dispersione fra aste **non supera** quella entro asta: vale circa
un ottavo. È il risultato atteso se il mercato è largamente d'accordo su quanto
vale ciascun giocatore, ed è coerente con l'89,8 % di varianza spiegata
dall'identità del giocatore. Ma «un ottavo» non è «trascurabile»: sono i 3,8
crediti mediani che decidono se il martelletto lo prendi tu o l'avversario.

### 6.4 I numeri operativi

Strato 10×500, 1.111 giocatori-stagione visti in almeno due aste, mediana di 8
aste per giocatore (quartili 5 e 23, massimo 26).

| quantità, in crediti su budget 500 | mediana | q75 | q90 | max |
|---|---:|---:|---:|---:|
| **sd del martelletto individuale** attorno alla media del giocatore | **3,8** | 7,2 | 13,5 | 97,6 |
| **errore standard della media** fra aste | **1,1** | 2,1 | 3,9 | 69,0 |
| rapporto fra le due | **3,46** | 4,80 | 5,00 | 5,10 |

Il rapporto mediano 3,46 è, come dev'essere, circa √(numero di aste). **Un
intervallo costruito sul prezzo medio è circa tre volte e mezza più stretto di
quello corretto per il singolo martelletto.** Usare il primo dove serve il
secondo è il modo più diretto di sottostimare il rischio d'asta.

Dispersione per fascia di prezzo (stesso strato):

| fascia (media del giocatore) | giocatori | prezzo medio | sd martelletto (mediana) | CV mediano |
|---|---:|---:|---:|---:|
| 0-1 | 144 | 1,0 | 0,0 | 0,00 |
| 2-5 | 436 | 2,7 | 2,0 | 0,77 |
| 6-15 | 248 | 9,0 | 5,3 | 0,65 |
| 16-40 | 164 | 24,0 | 8,1 | 0,37 |
| 41-100 | 83 | 57,7 | 14,9 | 0,26 |
| > 100 | 36 | 142,6 | 32,4 | 0,24 |

La sd cresce con il livello ma il **CV cala**: i giocatori costosi sono, in
proporzione, i più prevedibili. In valore assoluto no: un attaccante da 143
crediti oscilla di ±32 crediti fra un'asta e l'altra, cioè più del 6 % del
budget totale di una squadra.

### 6.5 Quale bersaglio per che cosa

| uso | bersaglio | perché |
|---|---|---|
| stima del valore di listino, confronti fra giocatori, ranking | **prezzo medio fra aste** | è la quantità che il campione stima con precisione crescente; è quella con cui si costruisce un listino |
| prezzo massimo da offrire, decisione sul singolo lotto, rischio di perdere il giocatore | **martelletto individuale** | è quello che accade davvero, e la sua dispersione è ~3,5 volte quella della media |
| calibrazione degli intervalli e ogni misura di copertura | **martelletto individuale** | un intervallo tarato sulla media avrebbe copertura nominale ma reale molto più bassa |
| simulazione d'asta, avversari, contesa | **martelletto individuale**, campionato dalla sua distribuzione | usare la media produrrebbe aste deterministiche e sottostimerebbe la contesa |

### 6.6 Controllo di sensibilità sull'identità del giocatore

La normalizzazione dei nomi è conservativa e non risolve i refusi del foglio
(`mikitarian`, `sczesny`): può **separare** lo stesso giocatore in più chiavi,
mai unirne due diversi. Riscontro su `map_ge.csv`: **zero** chiavi normalizzate
uniscono `master_id` diversi (nessuna falsa unione), ma **192 `master_id` hanno
più di un nome normalizzato** (frammentazione reale).

Rifacendo la misura chiave dello strato 10×500 con `master_id` al posto del nome
(copertura 99,94 %, 1.063 giocatori invece di 1.111):

| | chiave sul nome | chiave su `master_id` |
|---|---:|---:|
| quota di varianza del giocatore | 0,8984 | 0,8977 |
| quota idiosincratica | 0,1005 | 0,1011 |
| sd fra aste, mediana (`pct_budget`) | 0,00765 | 0,00746 |

Le conclusioni di §6.2-6.4 non dipendono dalla scelta della chiave.

---

## 7. La configurazione della nostra lega

Dichiarata dal committente: **10 partecipanti, 500 crediti, 3P/8D/8C/6A,
modificatore di difesa attivo**.

Quante aste dell'inventario la hanno? Dipende da quanti dei quattro requisiti si
pretendono, e il numero crolla in fretta:

| requisito cumulativo | aste |
|---|---:|
| 10 partecipanti e 500 crediti | **56** |
| … e conteggio dei ruoli compatibile con 3/8/8/6 | **27** |
| … e modificatore non `N` | **10** |
| … e `periodo` = 0 (la lettura «pre-campionato», non provata) | **3** |

Le 56 si distribuiscono in 26 (2021-22), 24 (2023-24), 6 (2024-25); per periodo:
12 / 5 / 21 / 18. Il loro modificatore: `+1M` 21, `N` 16, `M` 13, vuoto 5,
`+1` 1.

Va letto con attenzione. Il passaggio da 56 a 27 **non** dice che 29 aste usino
quote diverse: dice che solo 28 delle 56 hanno un conteggio di lotti completo, e
27 di quelle 28 rispettano 3/8/8/6. Il requisito sulle quote e la completezza
della trascrizione sono la stessa misura, e non sono separabili con questi dati.
Il passaggio da 27 a 10 dipende dalla semantica non documentata dei codici del
modificatore; quello da 10 a 3 dalla semantica non documentata di `periodo`.

**Le 3 aste dell'ultima riga non sono una base utilizzabile per niente.** Il
numero da tenere è 56, con i requisiti mancanti dichiarati come tali.

### 7.1 Il rapporto prezzo/budget non è stabile fra configurazioni — misurato

Il modo comodo di riusare le altre 160 aste sarebbe assumere che `pct_budget`
sia confrontabile fra configurazioni. **Misurato, non lo è.**

Stimatore entro-giocatore, a effetto fisso (stagione, ruolo, giocatore), sui
soli prezzi ≥ 1, su 48.224 osservazioni e 1.370 giocatori identificanti (quelli
visti in più di una configurazione):

```
log(prezzo) = beta_cr * log(crediti_tot) + beta_co * log(componenti)
              + effetto fisso (giocatore, stagione) + errore
```

| coefficiente | stima | IC 95 % (bootstrap su 1.000 repliche, ricampionando le **aste**) |
|---|---:|---|
| `beta_cr` (crediti) | **0,701** | [0,623 – 0,796] |
| `beta_co` (partecipanti) | 1,415 | [1,217 – 1,629] |

Con la proporzionalità esatta `beta_cr` varrebbe 1,000, e `pct_budget` sarebbe
invariante. L'intervallo **esclude 1,000**. Interpretazione diretta:
raddoppiando il budget i prezzi si moltiplicano per 2^0,70 ≈ 1,62, non per 2;
quindi in una lega da 1000 crediti lo stesso giocatore costa **una frazione più
piccola** del budget che in una da 500. Trasportare `pct_budget` da 8×1000 a
10×500 senza correzione introduce una distorsione sistematica.

Controllo: aggiungendo indicatrici di `periodo` il coefficiente resta 0,693,
quindi la stima non è guidata dalla composizione per periodo.

**Come va letto.** È un'**associazione descrittiva a giocatore-stagione fisso**,
non un'elasticità causale. Le leghe con budget diverso possono differire per
cose che questa tabella non osserva (esperienza dei partecipanti, regole di
rosa, provenienza dal forum), e l'unità di ricampionamento è l'asta perché le
righe della stessa asta non sono indipendenti (Protocollo v2 §3.3). Non chiamare
questo numero un fattore di conversione validato: è la prova che la conversione
ingenua è sbagliata, e la misura di quanto.

Stato: **riprodotta** come associazione; **non promossa** a regola di
normalizzazione — servirebbe un modello di trasporto stimato e validato, che è
lavoro della fase successiva.

---

## 8. Limiti e blocchi

**Blocchi** — richiedono una decisione del committente o una fonte che non
abbiamo. Non vanno risolti inventando una convenzione.

1. **Semantica di `periodo`.** Quattro classi ordinali senza mappa verso date o
   giornate. Impedisce di dire quali aste siano pre-campionato, che è il caso
   che ci interessa.
2. **Semantica del modificatore.** `N`, `M`, `+1M`, `+1` e vuoto: 5 codici, 0
   definizioni. Impedisce di selezionare le aste con modificatore di difesa.
3. **Quote di rosa.** Mai registrate. Inferibili solo per le 121 aste a
   trascrizione completa, e in modo confuso con la completezza stessa.
4. **Regole private della nostra lega** oltre a quelle dichiarate (bonus porta
   inviolata, sostituzioni, spareggi): fuori dal perimetro di questa fase, ma
   entrano appena si passa da un prezzo a un'utilità.

**Limiti** — misurati, dichiarati, non risolvibili con questo input.

5. Nessun ordine dei lotti, nessun proprietario, nessuna marca temporale (§5).
6. La stagione è attribuita al file, non all'asta, e non è mai stata verificata
   per asta. 2022-23 e 2025-26 sono completamente assenti; la stagione bersaglio
   2026-27 non ha e non può avere aste.
7. 22 aste spendono più del budget teorico, 12 oltre il 110 %: la fonte è
   crowdsourced e contiene errori di trascrizione non correggibili.
8. 32 aste canoniche contengono lo stesso giocatore su più righe con prezzi
   diversi; la scelta della prima occorrenza è arbitraria.
9. Un accostamento (`…2021-22circa#125` con `#138`) è ambiguo proprio sui
   portieri (§3.4).
10. 174 acquisti presenti in versioni non canoniche sono esclusi per non fondere
    versioni che si contraddicono.
11. Il campione è auto-selezionato: sono le aste che qualcuno ha voluto caricare
    su un foglio pubblico. Non c'è motivo di credere che sia rappresentativo
    delle leghe italiane, e non lo si chiami campione casuale.

---

## 9. Dipendenze dichiarate — modifiche fuori dal perimetro di questa fase

Non eseguite. Sono osservazioni sulla pipeline esistente, che questa fase non
possiede.

1. `scripts/f0b_build_outputs.py` sceglie la versione canonica del cluster con
   `sort(key=lambda it: (-it["n"], it["f"] != PREF_KEEP, it["f"], it["a"]))` e
   confronta ogni candidato con i già tenuti: il risultato coincide con le 216
   di qui sul conteggio. Non è stato verificato che coincida **asta per asta**
   nella scelta della versione, né che il suo `NEAR_DUP_OVERLAP = 0.70` fosse
   giustificato dall'intervallo vuoto misurato qui (a giudicare dal commento nel
   codice, la soglia era stata scelta senza questa misura). Prima di riusare
   `aste_reali_clean.csv` in L4 andrebbe fatto un confronto uno a uno con
   `data/l4/l4_aste_uniche.csv`.
2. `data/raw/gruppoesperti/REPORT.md` e `build_stats.json` affermano che non
   esistono duplicati interni ai singoli file: vero per le impronte esatte,
   falso per i quasi-duplicati (§3.2). L'affermazione andrebbe corretta alla
   fonte, non qui.
3. Il campo `periodo` e i codici del modificatore andrebbero recuperati dal
   thread del forum d'origine (`t=181911`, citato in `REPORT.md`). È l'unica via
   per sbloccare §8.1 e §8.2.

---

## 10. Che cosa può costruirci sopra la fase successiva

Fatti utilizzabili da 8B in avanti, con il loro stato:

| fatto | valore | stato |
|---|---|---|
| aste reali disponibili | 216, in `data/l4/l4_aste_uniche.csv` | riprodotta |
| aste nella configurazione 10×500 | 56 | riprodotta |
| unità di osservazione | (asta reale, giocatore) → un martelletto | riprodotta |
| unità di ricampionamento per ogni intervallo | l'**asta**, mai la riga | regola, da Protocollo v2 §3.3 |
| quota di varianza spiegata dal giocatore, 10×500 | 89,8 % | riprodotta |
| dispersione residua del martelletto | mediana 3,8 crediti su 500, fino a 32 nella fascia alta | riprodotta |
| rapporto sd(martelletto) / errore standard della media | 3,46 mediano | riprodotta |
| `pct_budget` trasferibile fra budget diversi | **no**, `beta_cr` = 0,70 con IC [0,62 – 0,80] | riprodotta come associazione |
| replay d'asta storico | **impossibile**, manca l'ordine dei lotti | riprodotta |

Il modello dei prezzi ha davanti 216 osservazioni di lega, non 55.678: le righe
sono 55.678 ma sono annidate in 216 aste, e ogni intervallo che tratti le righe
come indipendenti sarà troppo stretto. Il numero di aste, non di righe, è ciò
che limita quanto si può concludere.
