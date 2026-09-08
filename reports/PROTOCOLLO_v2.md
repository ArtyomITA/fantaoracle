# Protocollo v2 — ripresa dell'8 settembre 2026

Questo documento è **successivo** ai risultati prodotti il 7 settembre e li
revisiona sapendo come sono andati. Dove cambia una regola, lo dice
esplicitamente: una revisione metodologica presa dopo aver visto i risultati
non è un criterio preregistrato, e va letta per quello che è.

`CRITERI_L2_L3.md` resta valido dove non è contraddetto qui. Le sue sezioni
numerate non vengono riscritte a posteriori: le correzioni ai numeri sbagliati
sono già segnate come rettifiche in testa alle sezioni interessate.

---

## 1. Stato di ogni conclusione

Ogni affermazione del progetto porta uno di questi stati. Nessun numero entra
in un report senza il suo stato.

| stato | significato |
|---|---|
| **riprodotta** | misurata sullo stato corrente del codice e dei dati |
| **storica** | vera quando è stata misurata, su artefatti oggi superati; si conserva come risultato datato |
| **invalidata** | contraddetta da una misura successiva |
| **sperimentale** | implementazione verificata su casi controllati, non validata per la lega reale |
| **inconcludente** | l'esperimento non distingue le alternative; non è equivalenza |
| **bloccata** | dipende da un'informazione o da una decisione che non abbiamo |

### 1.1 Stato al momento della ripresa

| conclusione | stato | nota |
|---|---|---|
| panel: `club_id`, stati di convocazione, zero titolari non eleggibili | **riprodotta** | ma l'eleggibilità contiene anticipazione (§2), quindi il panel va rifatto |
| contratto temporale: 380 partite per stagione a 9 date di decisione | **riprodotta** | verificata da revisore indipendente |
| procedura unica del modello di partita, scarto 0,000 | **riprodotta** | |
| invarianti fisiche del generatore | **riprodotta** | verificate da revisore su 28.000 squadra-partita |
| bonus porta inviolata applicato una volta sola | **riprodotta** | equivalenza su quattro percorsi, entro 1e-9 |
| verdetto del banco L2: cubo peggiore di `B'` a informazione comparabile | **invalidata** | il disegno non realizzava la parità dichiarata (§3) |
| G1: incertezza dei gol, esito inconcludente | **storica** | il risultato resta; la sua regola di decisione è rivista (§5) |
| coda dei gol del cubo, numeri di §7.6 | **invalidata** | misura su metà campione; valori corretti già rettificati |
| confronto d'asta: L3 peggiora P(1°) di 0,0625 | **invalidata** come attribuzione causale, **storica** come numero | il braccio L3 portava due modifiche insieme |
| A1: quota d'attacco 0,60-0,75 peggiore | **storica** | banco non promosso, riferimento B+ e non B, e "due bomber" non è una quota di spesa (§7) |
| `quot_fs_sett`: nessuno snapshot anteriore al campionato | **riprodotta** | conseguenza operativa in §4 |
| tetti di indifferenza: 25 su 25 inconcludenti | **riprodotta** come fatto, **bloccata** come diagnosi | causa non ancora separata |

---

## 2. Informazione temporale — regola operativa

Per ogni decisione storica valgono **solo** le informazioni disponibili entro
il momento di quella decisione. «Ricostruire con quello che sappiamo oggi»
descrive la storia; non costruisce un backtest.

Sei date distinte, da tenere separate in ogni tabella e in ogni funzione:

1. data dell'evento;
2. data di pubblicazione o disponibilità della fonte;
3. data di acquisizione locale;
4. data della decisione;
5. data prevista dell'asta;
6. periodo futuro valutato.

Una data d'asta futura non autorizza a conoscere oggi informazioni che saranno
pubblicate entro quella data. Il cubo per l'asta dell'11 settembre si costruisce
con ciò che è disponibile alla data in cui lo si costruisce, non all'11.

**Feature e bersagli non hanno lo stesso vincolo.** Un risultato storico può
essere il bersaglio di un addestramento se era già noto al momento del fit; il
vincolo pre-decisione riguarda le informazioni usate **per prendere quella
decisione**, non pretende che un risultato fosse noto prima della sua partita.

---

## 3. Il banco L2 misura qualcosa di diverso da quello che dichiara

Riscontro riprodotto sul codice: in `scripts/l2_banco_confronto.py` il braccio
`B'` riceve le presenze del modello valore attraverso `storia_pres`, mentre il
cubo `C` è costruito con `pa.stima(Ppre)`, `ev.stima(Ppre)` e
`vt.stima(Ppre, ...)` — quelle predizioni **non gli arrivano** lungo quel
percorso.

Quindi «C contro B′ a parità di presenze» non descrive l'esperimento che è
stato eseguito, e il verdetto costruito su quella etichetta è **invalidato**.
Non basta correggere la didascalia: va corretto il disegno.

### 3.1 Disegno fattoriale

Quattro celle, dove tecnicamente compatibile:

| | informazione storica | predizioni lecite del modello |
|---|---|---|
| **meccanismo precedente** | B con storia | B′ con predizioni |
| **cubo** | C con storia | C′ con predizioni |

Uguali per tutte e quattro: universo, data limite, punteggio, periodo valutato,
bersagli informativi delle presenze.

**Avvertenza fisica.** «Stesse presenze» non può significare imporre al cubo
maschere indipendenti che violino gli undici in campo, i minuti o le
sostituzioni. Se le probabilità esterne sono incompatibili con i vincoli
fisici, l'incompatibilità va **misurata** e l'eventuale proiezione verso valori
realizzabili va dichiarata, non nascosta.

**Prova sul percorso dei dati**, obbligatoria prima di leggere qualunque
risultato: perturbare l'input delle presenze deve cambiare i bracci che
dichiarano di usarlo e **non** gli altri. Un braccio che non reagisce alla
perturbazione non stava usando quell'informazione.

### 3.2 Nomi

La stessa lettera ha indicato sistemi diversi in report diversi. Da qui in poi:

| identificativo | che cos'è |
|---|---|
| `GEN-A`, `GEN-B`, `GEN-B1`, `GEN-C`, `GEN-C1` | generatori del banco L2 |
| `BOT-B`, `BOT-B+`, `BOT-L3`, `BOT-L3I` | bot d'asta |
| `SYS-*` | varianti complete (bot più generatore più pack) |

`GEN-B` non è `BOT-B`. Nel banco, `GEN-B` è una meccanica generativa
reimplementata: **non** è la pipeline operativa. Chiamare «produzione» una
reimplementazione simile richiede prima una verifica di parità, che non è
ancora stata fatta.

### 3.3 Unità inferenziale

Il bootstrap sulle singole righe giocatore-giornata tratta come indipendenti
osservazioni che condividono partita, squadra e storia del giocatore. Gli otto
intervalli del verdetto precedente sono costruiti così e **non** sostengono
l'affermazione causale «tutto il vantaggio viene dalle presenze».

Prima di rieseguire, l'unità inferenziale va dichiarata:

- differenze appaiate sulle stesse osservazioni;
- ricampionamento che conservi le dipendenze pertinenti, con il metodo motivato
  (blocchi per partita, per squadra-giornata o per giocatore, secondo la
  dipendenza che conta);
- errore Monte Carlo separato dall'incertezza sui dati osservati.

Per le aste: calendari e scenari della stessa asta non sono aste indipendenti.
Un intervallo fra repliche condizionato a un cubo fisso è un intervallo
condizionato, e va scritto così.

---

## 4. `quot_fs_sett`

Una rilevazione datata come la prima giornata non è automaticamente
pre-campionato. Serve una prova verificabile dell'orario e della semantica; il
nome del file e il numero di giornata non sono prove.

Se la disponibilità pre-asta resta indimostrabile:

- la variabile **esce** dalla variante storica dichiarata rigorosamente
  pre-asta, e la pipeline interessata viene ricostruita di conseguenza;
- la configurazione precedente resta come confronto **diagnostico**, con quel
  nome;
- l'esclusione **non** si chiama miglioramento predittivo dimostrato;
- per l'uso live valgono solo le osservazioni disponibili alla vera data
  decisionale.

Sostituire g03 con g01 e dichiarare risolto il problema non è una correzione.
Addestrare senza la feature e poi fare inferenza con la feature non è ammesso,
salvo un modello progettato e validato proprio per quella situazione.

---

## 5. Revisione della regola di G1 — dichiarata come successiva

La regola scritta in §7.6 sapeva dichiarare un vincitore, non un dominato: con
T0 migliore su entrambe le stagioni ma T0 − T2 che contiene lo zero nel
2025-26, l'esito è stato «inconcludente, resta T1» pur essendo T1 il peggiore
dei tre in tutte e quattro le combinazioni, sempre con intervallo che esclude
lo zero.

Conservare il predefinito quando è dominato da entrambi i candidati non è una
conclusione difendibile. **Questa revisione è successiva all'osservazione dei
risultati e va letta come tale**: non trasforma G1 in un esperimento
preregistrato vincente, e il risultato originale resta agli atti con il suo
esito.

Regola per la fase nuova:

- **T0** (punto stimato) è il riferimento sperimentale semplice;
- **T2** (sandwich, o la correzione che la ricerca metodologica indicherà)
  resta un candidato;
- **T1** (inversa dell'hessiana, il comportamento attuale) deve giustificare di
  nuovo il proprio impiego: non lo recupera l'indistinguibilità fra gli altri
  due;
- se T0 e T2 risultano indistinguibili, si dichiara, e si sceglie fra loro con
  un criterio scritto prima — non si torna a T1 per inerzia.

---

## 6. Tracciabilità degli artefatti

Ogni artefatto prodotto da qui in avanti deve contenere o referenziare:

- impronte dei genitori;
- versione del codice;
- configurazione;
- data limite informativa e periodo previsto;
- seme;
- schema e convenzioni di punteggio.

Un artefatto **non** si accetta perché ha un nome recente: si accetta se i suoi
genitori sono quelli attuali. Un artefatto con genitori diversi da quelli
correnti è **stale** e va etichettato, non letto.

Le tabelle dei report si generano dai risultati correnti. Nessun coefficiente o
percentuale si corregge a mano per farlo coincidere con il racconto.

### 6.1 Ordine di rigenerazione, per dipendenza

1. appartenenze e panel;
2. tabelle partita e aggregati;
3. predizioni interessate;
4. modelli e calibrazioni;
5. cubi;
6. banchi;
7. metriche e report.

Non si lancia un confronto costoso su un cubo che verrà invalidato subito dopo.

---

## 7. Regole della lega: assunzioni, non conferme

Nessuna conferma dell'utente viene inventata. Per proseguire, queste
impostazioni restano in uso **etichettate come assunzioni**: budget, quote,
sostituzioni, soglia e passo dei gol, modificatore, spareggi.

**Bonus porta inviolata**: assunzione sperimentale = il riferimento è il
**singolo portiere** con punteggio valido e zero gol subiti. Esiste un
chiarimento pubblico coerente con questa lettura
([Fantacalcio.it, 22 ottobre 2013](https://www.fantacalcio.it/news/redazionali/22_10_2013/torino-inter-chiarimenti-sul-fantavoto-di-handanovic-177606)),
che però non certifica il regolamento privato di questa lega.

Da controllare come casi distinti, perché **non** sono sinonimi: «minuti
giocati», «voto puro valido», «fantavoto valido». Casi: s.v., voto d'ufficio,
espulsione, sostituzione.

Le regole private non confermate impediscono una validazione definitiva **per
la lega reale**; non impediscono la correzione del codice né esperimenti
dichiaratamente condizionati a queste assunzioni.

---

## 8. Condizioni di arresto di un ramo

Un ramo si ferma, e il blocco si registra, se:

- gli input temporali non sono ammissibili;
- gli artefatti sono incompatibili;
- ci sono violazioni fisiche o contabili;
- il trattamento eseguito è diverso da quello dichiarato;
- la verifica è contaminata;
- un'assunzione decisiva non è risolta.

Gli altri rami proseguono.

---

## 9. Decisioni prese dopo la prima ondata di audit

Tre audit indipendenti in sola lettura hanno consegnato l'8 settembre
(`data/l3/audit2/`). Queste sono le decisioni che ne discendono, con la ragione
per cui sono decidibili senza chiedere all'utente.

### 9.1 L'orizzonte del file dei trasferimenti non è una prova

L'audit ha quantificato il bivio: se l'orizzonte globale di
`transfermarkt_transfers.csv` (2025-09-30, cioè la data dell'ultimo
trasferimento scaricato) vale come prova disponibile a una data passata, il
filtro a valle basta; se non vale, lascia passare 1.706 / 2.518 / 160 righe.

**Non vale.** L'orizzonte è una proprietà dello scarico, non un'affermazione
sul giocatore: dire «non risulta nessun trasferimento successivo, quindi era
ancora lì» è esattamente il ragionamento che la direttiva vieta — la mancanza
di una comparsa altrove non è prova di permanenza. Si adotta la **censura
piena**: le prove si filtrano prima di risolvere i conflitti e costruire gli
intervalli, orizzonte incluso.

Conseguenza dichiarata: da ottobre in poi, sotto una data di decisione onesta,
la fonte `trasferimenti` non dà più nessun verdetto, perché il file non contiene
trasferimenti di gennaio (F8: 58.549 righe, solo i mesi 6-9, zero a gennaio).
La priorità delle fonti va riscritta di conseguenza: la ragione scritta nel
modulo — «l'unica che risolva i casi di gennaio» — è falsa sul file presente.

### 9.2 Il denominatore delle propensioni viene dal listone, non dalle comparse

Il problema misurato: le righe che portano l'informazione «era disponibile e non
è stato convocato» sono le `escluso`, e sono esattamente quelle che
l'anticipazione crea. Togliendole, il denominatore converge sui soli giocatori
visti in campo (dall'84% al 99%) e `prop_convocato` media sale da 0,84 a 0,98.
Correggere l'anticipazione con un filtro, e basta, **aggrava** la sovrastima.

La via d'uscita non è statistica ma di fonte: l'universo dei convocabili a una
certa data è il **listone della stagione**, che è informazione pubblica
disponibile prima dell'asta. Esiste per tutte le stagioni che ci servono
(`data/raw/quotazioni/fantacalcioit_*.csv`: 675, 664, 679, 663 e 587 righe con
squadra e ruolo).

Regola: una riga entra nel denominatore se il giocatore è nel listone di quella
stagione per quella squadra, e nessuna prova **disponibile alla data della
decisione** lo colloca altrove. Chi non è nel listone non entra; chi è nel
listone e non è stato convocato entra, ed è il caso che porta l'informazione.

Limite dichiarato: il listone è una fotografia di inizio stagione e non
riflette i movimenti di gennaio. Per una data di decisione pre-campionato —
che è il nostro caso — questo non introduce anticipazione; per una data
infrastagionale servirebbe un listone aggiornato a quella data, che non
abbiamo.

### 9.3 `quot_fs_sett`: sbloccato, con prova di contenuto

L'audit ha trovato la prova che mancava, e non è un'etichetta: la variazione di
quotazione fra due snapshot consecutivi reagisce al rendimento della giornata
**precedente** allo snapshot di arrivo. Correlazione media 0,783 con la
giornata N contro 0,057 con la N+1, su 37 giornate su 37 nel 2021-22, e
0,833 contro 0,101 sulla prima giornata; ripetuto su tutte le stagioni con
snapshot sufficienti, senza eccezioni.

Quindi lo snapshot g01 **non contiene** i risultati della prima giornata ed è
utilizzabile come quotazione d'asta. Resta ignota l'ora dell'orologio, che per
questo uso non serve.

Conseguenza operativa: la selezione «snapshot più vicino al 1 settembre»
(`f0b_match.py`) va sostituita con «l'ultimo snapshot il cui contenuto è
anteriore alla data di decisione», che per un'asta pre-campionato è g01. Non è
la sostituzione di g03 con g01 per comodità: è la regola che ora ha una prova.
La ricostruzione della pipeline prezzi che ne consegue va misurata come
confronto appaiato, e il risultato **non** si chiama miglioramento predittivo
finché non lo è.

### 9.4 I tetti di indifferenza: il disegno era condannato in partenza

Misurato dall'audit: con 4 repliche e una deviazione standard per replica di
circa 0,13, il disegno rende rilevabile solo un effetto |Δ| ≥ 0,127 su
P(1° posto). Il P(1° posto) di base del nostro bot vale 0,094: si chiedeva a un
singolo giocatore di spostare la probabilità di vittoria di più di quanto essa
valga in tutto. L'esito «25 tetti su 25 inconcludenti» era garantito prima di
vedere i dati.

Costo misurato per concludere davvero: 1,09 secondi per coppia
(replica, prezzo); circa 26 repliche per rilevare Δ = 0,05 (circa un'ora),
circa 162 per Δ = 0,02 (circa sei ore). **La soglia di significatività non si
tocca**: si sceglie l'effetto minimo che interessa e si paga il calcolo, oppure
si dichiara che non si conclude.

### 9.2b Il listone da solo non basta: serve anche la finestra temporale

Misurato dopo aver scritto §9.2, e la corregge.

Il panel parte già dal listone: ogni riga è (giocatore del listone, partita
della sua squadra). Quindi «è nel listone per quella squadra» è vero per
costruzione su tutte le righe, e la regola di §9.2, presa alla lettera,
riporterebbe nel denominatore tutte le righe con appartenenza ignota:
**+15,3 %, +13,7 % e +18,5 %** rispetto al denominatore attuale nelle tre
stagioni.

Ma non tutte quelle righe meritano di rientrare. Un giocatore ceduto a gennaio
resta nel listone del vecchio club, e le sue partite successive
accumulerebbero assenze fittizie — lo stesso difetto, con il segno opposto. La
prova della cessione invernale **non esiste nel nostro file**: F8 dell'audit
mostra che `transfermarkt_transfers.csv` non contiene un solo trasferimento di
gennaio.

Regola adottata, con il suo costo misurato: il denominatore delle propensioni
usa **le sole giornate del girone d'andata** (fino alla 19ª), dove il listone
di inizio stagione è ancora una prova valida senza bisogno di informazione
futura, e dentro quella finestra ammette le righe la cui appartenenza non è
smentita da una prova disponibile alla data.

| stagione | denominatore attuale | righe con voto | denominatore andata + listone | righe con voto |
|---|---:|---:|---:|---:|
| 2021-22 | 19.545 | 53,8 % | 11.674 | 45,8 % |
| 2023-24 | 19.429 | 55,0 % | 11.239 | 48,0 % |
| 2024-25 | 20.131 | 52,9 % | 11.310 | 47,4 % |
| 2025-26 | 19.162 | 55,2 % | 11.140 | 48,5 % |
| **totale** | **78.267** | | **45.363 (58 %)** | |

Si perde il 42 % delle righe. In cambio la quota di righe con presenza a voto
**scende** (dal 53-55 % al 46-49 %): il denominatore contiene più casi di
«convocabile che non ha giocato», che è esattamente l'informazione che serve e
che il filtro sull'anticipazione, da solo, avrebbe distrutto.

Limite dichiarato: le propensioni stimate descrivono il girone d'andata. Se la
disponibilità cambia sistematicamente fra andata e ritorno, questa stima è
distorta per il ritorno. È un limite noto, non misurato, e va scritto accanto ai
risultati finché non lo si misura.

---

## 10. Rettifiche del 8 settembre — le vecchie conclusioni restano, con il loro errore accanto

Ogni voce qui sotto corregge un'affermazione scritta prima in questo stesso
documento o nel manifesto. La versione originale non viene cancellata: si legge
insieme alla rettifica.

### 10.1 «I trasferimenti invernali non esistono nella fonte» → falso

**Scritto in §9.1**, sulla base di F8 dell'audit: «`transfermarkt_transfers.csv`
non contiene un solo trasferimento di gennaio (58.549 righe, solo i mesi 6-9)».

**Vero**: quel file è un **estratto** prodotto da `scripts/tm_process.py`, che
filtra per anni 2020-2025 e mesi 6-9. Il grezzo
`data/raw/transfermarkt/_download/transfers.csv.gz` ha **175.165 righe**, tutte
con data valida, dal 1993 al 2030, di cui **34.920 a gennaio** e **9.559 a
febbraio**; nel periodo 2020-2026 sono 101.504 righe con 28.613 fra gennaio e
febbraio.

L'audit ha misurato l'estratto e ha descritto correttamente l'estratto. La
conclusione tratta — «la fonte non conosce gennaio» — non segue. Con essa cade
anche la conseguenza scritta in §9.1 («da ottobre in poi la fonte non dà più
nessun verdetto»): dipendeva dal filtro, non dai dati.

### 10.2 «Il taglio alla giornata 19 risolve il denominatore» → non dimostrato

**Scritto in §9.2b**: denominatore dalle sole giornate del girone d'andata,
«dove il listone di inizio stagione è ancora una prova valida».

**Vero**: il taglio per numero di giornata non corrisponde a una data. Nei
panel, la giornata 19 arriva al **7 gennaio** nel 2023-24, al **27 febbraio**
nel 2024-25 e al **15 gennaio** nel 2025-26 — nel 2024-25 include
Bologna-Milan della giornata 9, recuperata il 27 febbraio. Il taglio non
delimita un periodo privo di mercato invernale, e con i trasferimenti annuali
recuperati (§10.1) il problema che voleva aggirare si affronta direttamente.

Il taglio **non viene adottato**. Se servirà una sensibilità su un periodo più
corto si userà una data effettiva, con la sua ragione, e non la si chiamerà
«priva di trasferimenti».

### 10.3 «g01 è provato dalla correlazione» → indizio forte, più evidenza semantica

**Scritto in §9.3**: la prova di contenuto (correlazione 0,783 con la giornata
N contro 0,057 con la N+1) rende g01 «utilizzabile».

**Vero**: quella correlazione è coerente con un aggiornamento ritardato ed è un
indizio forte, ma da sola non esclude revisioni, aggiunte o altri
aggiornamenti dello stesso file. Esiste però evidenza semantica dalla fonte:
nell'archivio Fanta.Soccer il collegamento «Quotazioni iniziali» punta a
`QuotazioniExcel.aspx` con `giornata=1`, cioè la fonte stessa chiama g01 la
quotazione iniziale.

I tre livelli di evidenza restano distinti e vanno dichiarati per ogni uso:
(1) la fonte dichiara «iniziali»; (2) il file è stato conservato prima del
cutoff; (3) inferenza statistica sul contenuto. Oggi abbiamo (1) e (3), non (2).

### 10.4 «La sovradispersione è fra scenari, non dentro» → diagnosi non identificata

**Scritto** nel manifesto (voce R1) e ripetuto in chat: «lo scenario meno
disperso è già calibrato: la sovradispersione è fra scenari».

**Vero**: la variazione fra scenari contiene **anche** il rumore delle partite,
non solo l'incertezza sui parametri. Una singola realizzazione favorevole non è
una verifica di calibrazione: con 700 squadra-partita per scenario, il minimo
su 40 scenari è una statistica d'ordine, e il suo valore basso è atteso anche
sotto un modello ben calibrato. La diagnosi non è identificata con quel calcolo.

Rettifica anche del rapporto fra errori standard: dal JSON, il rapporto fra
l'errore standard per scenario e quello binomiale ingenuo sullo stesso campione
vale circa **1,62**, non 6. Il «6 volte più largo» detto in chat confrontava
grandezze diverse e non è sostenuto.

### 10.5 «I tetti erano condannati in partenza» → disegno poco preciso, impossibilità non dimostrata

**Scritto in §9.4**: «l'esito inconcludente era garantito prima di vedere i
dati».

**Vero**: `1,96 × sd / √n` è la semiampiezza approssimata di un intervallo
normale, non un'analisi di potenza; con quattro repliche quella
approssimazione è a sua volta fragile. E il valore di P(1° posto) di base non
limita l'ampiezza del miglioramento ottenibile. Resta vero che il disegno era
**poco preciso**; «impossibile concludere» è più forte di quanto misurato.

Prima di comprare precisione con altre repliche vanno fatte le cose che costano
meno: correggere il controfattuale, sfruttare appaiamento e cache lecite,
stimare la variabilità su pochi casi rappresentativi, e definire l'effetto
pratico che interessa con la sua regola di arresto.

---

## 11. Le tre viste, e dove serve davvero la censura (F2)

Realizzate in `scripts/l2_costruisci_panel.py` e
`src/fantabot/tabellino/appartenenza.py`. Misurate sul 2024-25.

### 11.1 Che cosa risponde ciascuna vista

| vista | domanda | come è costruita |
|---|---|---|
| **osservativa** | «di chi era, per quel che oggi sappiamo?» | tutte le prove note, comprese quelle successive alla partita |
| **informativa alla decisione** | «di chi risultava, per chi decideva a quella data?» | prove filtrate **prima** di risolvere i conflitti; `as_of` esclusivo |
| **stato futuro previsto** | «che cosa assumiamo dopo il cutoff?» | prolungamento in avanti dell'ultima prova, segnato `confidenza = inferenza` |

La terza non è un oggetto separato: è la parte della seconda che cade oltre
l'ultima prova, e si legge dalla colonna `confidenza_dec`. Tenere le tre cose
in un unico oggetto era il difetto che azzerava il panel.

### 11.2 Quanta informazione futura usava la vista unica

2024-25, 25.802 righe, data di decisione 2024-08-16 (il giorno prima della
prima partita), estensione fino al 2025-05-25:

| | `si` | `no` | `ignoto` |
|---|---:|---:|---:|
| osservativa | 20.230 | 3.656 | 1.916 |
| informativa | 17.840 | 6.207 | 1.755 |

**7.316 righe divergono** (28,4 %): 4.294 da `si` a `no` (giocatori arrivati
dopo la data di decisione), 1.989 da `no` a `si` (giocatori che a quella data
risultavano lì e sono poi partiti), 382 da `si` a `ignoto`, 300 e 297 dai due
`ignoto`. Nella vista informativa **tutte** le 24.047 risposte non nulle sono
`inferenza`: le partite stanno tutte dopo il cutoff, quindi nessuna prova le
copre direttamente. È corretto, ed è il motivo per cui l'etichetta serve.

### 11.3 Dove la censura serve davvero — e dove no

Questo chiude il problema che sembrava insolubile (il denominatore che si
riduceva ai soli giocatori visti in campo).

Il vincolo è sulle informazioni usate **per prendere una decisione**, non sulle
osservazioni usate per stimare. Una stagione **conclusa prima del fit** può
fornire osservazioni per tutta la sua durata: quando si addestra a settembre
2026, i trasferimenti di gennaio 2024 sono fatti noti, non informazione futura.

Ne segue:

- le stagioni storiche di addestramento usano la **vista osservativa**, intera,
  senza perdita di righe e senza nessun taglio a metà stagione;
- la **vista informativa** serve per la stagione bersaglio, dove la decisione è
  adesso e le sue partite sono ancora da giocare;
- il taglio alla giornata 19, già rettificato in §10.2, non serve più a niente:
  era un rimedio a un problema mal posto.

Resta vero e va verificato caso per caso che nessuna feature costruita per una
decisione datata legga oltre il proprio cutoff: è quello che i test di
integrazione devono coprire.

### 11.4 Distinta completa, misurata sulla fonte

`formazioni_note` era «almeno un `tipo` non nullo nella partita», calcolato sul
panel già ristretto all'universo fantacalcistico: un solo giocatore agganciato
bastava a dichiarare nota la distinta, e su quella base tutti gli altri
diventavano «esclusi».

Ora la completezza si misura su `game_lineups.csv.gz`, per la coppia (partita,
club), prima di ogni filtro: 162.234 squadra-partita, di cui **161.554
(99,58 %) con 11 titolari**, 671 con un numero fra 1 e 10, 4 senza. Solo
`completa` autorizza a dire «era disponibile e non è stato convocato»; una
distinta parziale produce `ignoto`, che è un'osservazione incompleta e non una
prova di esclusione.

---

## 12. La coda dei gol, scomposta con un disegno che identifica le sorgenti

`scripts/l2_diagnosi_coda.py`, artefatto `data/l2/diagnosi_coda_2026-27.json`.
24 campioni di parametri × 24 realizzazioni dello stesso calendario = 576
stagioni simulate, 350 partite ciascuna.

Il disegno serve a separare quello che la misura precedente aveva confuso: nel
cubo ogni scenario è **un campione di parametri seguito da una sola
realizzazione**, quindi la dispersione fra scenari somma le due sorgenti e non
le distingue.

### 12.1 Da dove viene la variabilità

| statistica | media | sd a parametri fissi | sd fra campioni di parametri | quota dovuta ai parametri |
|---|---:|---:|---:|---:|
| P(≥ 6 gol) | 0,01586 | 0,00426 | 0,00636 | **69,0 %** |
| media dei gol | 1,41610 | 0,04377 | 0,11608 | 87,6 % |
| varianza dei gol | 2,04602 | 0,15545 | 0,30784 | 79,7 % |
| P(0 gol) | 0,30512 | 0,01519 | 0,02764 | 76,8 % |

L'incertezza sui parametri domina, ma **non è tutta la storia**.

### 12.2 Quanto dell'eccesso spiega l'incertezza, e quanto no

| | P(≥ 6 gol) |
|---|---:|
| modello con incertezza sui parametri | 0,01586 |
| modello al punto stimato, senza incertezza | **0,00833** |
| osservato, tutte le stagioni disponibili | 0,00465 |
| osservato, ultime tre stagioni concluse | 0,00307 |

L'incertezza sui parametri raddoppia la coda, da 0,83 % a 1,59 %. Ma il punto
stimato, **senza nessuna incertezza**, resta a 0,83 % contro lo 0,465 %
osservato: quasi il doppio. Quindi l'incertezza dei parametri spiega grosso
modo metà dell'eccesso, e l'altra metà resta nella specificazione del modello
di partita. Correggere solo la covarianza non basterebbe.

### 12.3 Dove cade l'osservato

Frazione di repliche del modello con coda **non superiore** a quella osservata:
**0,0156** rispetto a tutte le stagioni disponibili, **0,0087** rispetto alle
ultime tre concluse. Il modello produce quasi sempre code più grasse del vero.

Questo sostituisce l'affermazione precedente («lo scenario meno disperso è già
calibrato, quindi la sovradispersione è tutta fra scenari»), che era una
statistica d'ordine letta come una verifica di calibrazione ed è rettificata in
§10.4.
