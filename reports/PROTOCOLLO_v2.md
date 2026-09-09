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

---

## 13. Il disegno fattoriale, realizzato — e che cosa dice

`scripts/l2_banco_confronto.py`, artefatti `data/l2/banco_confronto_*.csv` e
`banco_verdetto_*.csv`. Quattro bracci, 30 scenari, stagioni 2024-25 e 2025-26.

Il braccio che mancava è `C1`: il cubo che riceve **le stesse presenze** del
modello valore che riceveva `I1`. Senza di lui il confronto «a parità di
presenze» non era realizzabile, e il verdetto costruito su quell'etichetta era
invalidato (§3). Il collegamento passa da `partecipazione.stima(...,
bersaglio_presenza=...)`, che traduce la presenza a voto attesa in una
propensione di convocazione dividendo per la quota osservata di convocati che
prendono voto, per ruolo — non la sostituisce.

### 13.1 I quattro confronti

CRPS, differenza appaiata; negativo è a favore del primo termine.

> **SUPERATA, E CON UN SEGNO ROVESCIATO.** Questa tabella è stata prodotta
> prima delle correzioni R1-R3, con intervalli che trattavano le righe come
> indipendenti. Rifatta in R4, la riga `C1 − I1` **cambia segno e smette di
> contenere lo zero**: da −0,0031 e −0,0188 «indistinguibili» a **+0,0973 e
> +0,0505, cioè `C1` peggiore**. Non è una riverniciatura dell'incertezza: il
> punto stimato è dall'altra parte. La lettura 2 qui sotto è **falsa** allo
> stato attuale; è tenuta a vista perché il percorso resti leggibile. I numeri
> correnti sono in §19.

| fattore | 2024-25 | 2025-26 |
|---|---|---|
| **meccanismo**, a informazione storica (C0 − I0) | −0,0652 [−0,100; −0,032] | −0,0368 [−0,070; −0,004] |
| **meccanismo**, con le presenze del modello (C1 − I1) | −0,0031 [−0,036; +0,027] | −0,0188 [−0,050; +0,010] |
| **informazione**, meccanismo per giocatore (I1 − I0) | −0,1840 [−0,210; −0,159] | −0,2107 [−0,237; −0,183] |
| **informazione**, meccanismo cubo (C1 − C0) | −0,1219 [−0,144; −0,100] | −0,1926 [−0,217; −0,169] |

Tre letture, in ordine di importanza:

1. **L'informazione pesa molto più del meccanismo.** Dare le presenze del
   modello valore vale fra 0,12 e 0,21 di CRPS; cambiare meccanismo vale fra
   0,00 e 0,07. Il confronto precedente misurava soprattutto la prima cosa
   credendo di misurare la seconda.
2. ~~**A informazione comparabile i due meccanismi sono indistinguibili** sul
   CRPS in entrambe le stagioni: gli intervalli attraversano lo zero. Non è
   equivalenza dimostrata, è assenza di differenza rilevabile con questo
   disegno.~~ **Rovesciata da R4**: a informazione comparabile il cubo è
   *peggiore*, e l'intervallo esclude lo zero in entrambe le stagioni. Vedi
   §19.
3. **A informazione storica il cubo vince**, su entrambe le stagioni e su
   entrambe le misure. È il caso in cui i due meccanismi partono dagli stessi
   dati grezzi.

L'interazione è visibile: il cubo trae dall'informazione meno di quanto ne
tragga il simulatore per giocatore (−0,122 contro −0,184 nel 2024-25), perché
partiva già molto più vicino al vero sulle presenze.

### 13.2 Il realismo, che le metriche predittive non catturano

| | presenze per giornata | gol per rosa | corr. fra difensori |
|---|---:|---:|---:|
| **vero 2024-25** | **281,9** | **0,216** | **0,311** |
| I0 per giocatore, storia | 362,3 | 0,472 | 0,161 |
| I1 per giocatore, presenze del modello | 331,6 | 0,400 | 0,162 |
| C0 cubo, storia | 284,0 | 0,187 | 0,296 |
| **C1 cubo, presenze del modello** | **282,6** | 0,236 | **0,300** |

Nel 2025-26 lo stesso quadro: vero 283,6 presenze, `C1` 283,1, `I1` 312,9.

`C1` ha il CRPS più basso del banco (1,4529 e 1,4433) **e** le presenze più
vicine al vero (errore 0,25 % e 0,18 %) **e** le correlazioni fra compagni più
vicine. Il simulatore per giocatore, anche con le stesse presenze, continua a
generare il 17 % e il 10 % di presenze in più del vero e correlazioni fra
difensori dimezzate.

### 13.3 Che cosa questo non dice

- Non dice che il cubo è **promosso**: il verdetto è che a informazione
  comparabile la differenza predittiva non è rilevabile, mentre il realismo
  fisico è nettamente migliore. La promozione richiede una decisione su quale
  delle due cose conti, e quella decisione non è stata presa.
- Gli intervalli sono condizionati agli scenari: il ricampionamento è sulle
  coppie (giocatore, giornata), non sul rumore Monte Carlo dei generatori né
  sulla dipendenza fra giocatori della stessa partita.
- Le stagioni 2024-25 e 2025-26 sono state consultate molte volte: sono
  validazione riusata, non un test incontaminato.

---

## 14. La coda dei gol, rifatta su calendari storici — e che cosa cambia

`scripts/l2_coda_storica.py`, artefatti `data/l2/coda_storica.{csv,json}`.

### 14.1 Perché la misura precedente non poteva concludere

`l2_diagnosi_coda.py` confrontava repliche del calendario **2026-27** con
l'osservato di **altre** stagioni: squadre diverse, numerosità diversa,
calendario diverso. La scomposizione della varianza che ne usciva descriveva
qualcosa, ma non identificava la causa dell'eccesso, e la conclusione «metà
dell'eccesso resta nella specificazione» (§12.2) non ne seguiva.

Qui il confronto è omogeneo: stagione conclusa, modello stimato con dati
anteriori al suo inizio, **stesso calendario** che è stato giocato, stesse
partite ed entrambe le squadre.

### 14.2 Il calcolo è in forma chiusa

Il ramo di ricerca ha stabilito, con fonte e verifica numerica, che la
correzione di Dixon-Coles conserva le marginali — la congiunta è di famiglia
Sarmanov e l'invarianza segue da `E[q(X)] = 0` sotto Poisson, per **ogni** rho:
l'ammissibilità serve alla positività, non all'invarianza. Quindi
`P(G >= k | lambda)` si calcola senza simulare, e la coda prevista non porta
rumore Monte Carlo.

Difetto trovato e corretto lungo la strada: `matrice_risultato` scaricava la
massa troncata sulla cella `(12, 12)`, e così la coda tagliata di una squadra
gonfiava la marginale dell'altra. Alle intensità operative valeva +1,2e-6 in
termini relativi — non è la causa della coda grassa — ma arrivava a +9,6 % a
`(6,00; 3,00)` e +23,3 % a `(8,00; 4,00)`. Ora la massa si rinormalizza in
proporzione, e le marginali coincidono con la Poisson troncata entro 1,5e-16.
Il test che avrebbe dovuto accorgersene confrontava `rho` contro `rho = 0`,
cioè due matrici con lo stesso rattoppo: è stato sostituito con un confronto
contro il bersaglio vero.

### 14.3 Il risultato

P(≥ 6 gol per squadra-partita), previsione contro osservato sullo stesso
calendario:

| stagione | osservata | punto stimato | hessiana (attuale) | decadimento dimezzato |
|---|---:|---:|---:|---:|
| 2023-24 | 0,2632 % [0,032; 0,947] | 0,3964 % | 0,7889 % | 0,4775 % |
| 2024-25 | 0,3947 % [0,082; 1,149] | 0,5544 % | **1,4857 %** | 0,5581 % |
| 2025-26 | 0,2632 % [0,032; 0,947] | 0,5498 % | 0,8441 % | 0,5737 % |

Rapporto previsto su osservato: **1,40-2,09** al punto stimato, **3,00-3,76**
con l'incertezza dall'hessiana, 1,41-2,18 col decadimento dimezzato.

Il punto stimato cade **dentro** l'intervallo Clopper-Pearson dell'osservato su
tutte e tre le stagioni; il trattamento attuale ne esce nel 2024-25.

Lettura: l'eccesso della coda viene dal **trattamento dell'incertezza sui
parametri**, non dalla specificazione del modello. Questo corregge §12.2, che
attribuiva metà dell'eccesso alla specificazione sulla base di un confronto non
omogeneo.

Il decadimento dimezzato non aggiunge nulla al punto stimato: cambia `xi` da
0,0015 a 0,0008 e la coda resta 0,5581 % contro 0,5544 %. Non è la quantità di
campione effettivo a produrre la coda.

### 14.4 Che cosa questo **non** dice

- Non dice che l'incertezza sui parametri vada tolta: un modello senza
  incertezza sottostima la propria fallibilità, e la coda non è l'unica
  quantità che conta.
- Non dice quale trattamento dell'incertezza sia corretto. Dice che quello
  attuale produce una coda incompatibile con l'osservato in una stagione su
  tre, il che è una ragione per cercarne uno migliore, non una scelta già
  fatta.
- Tre stagioni sono tre osservazioni. Gli intervalli dell'osservato sono larghi
  (0,03-1,15 % nel 2023-24) proprio perché una stagione contiene poche partite
  con sei o più gol: rispettivamente 2, 3 e 2 su 760.

---

## 15. Rettifiche del percorso 1-4, prima di proseguire

Le sezioni 11-14 restano agli atti come **risultati del percorso precedente**,
con validità da riesaminare dopo le correzioni di questa sezione. I loro numeri
non vengono cancellati: vengono etichettati.

### 15.1 «C1 migliore su tutte le misure» era falso

Scritto in chat e implicito in §13.2. I controesempi sono nel CSV che avevo
davanti:

| | gol per rosa 2025-26 | scarto dal vero | Brier 2024-25 |
|---|---:|---:|---:|
| vero | 0,2237 | — | — |
| I1 per giocatore, presenze del modello | 0,2713 | **0,0476** | **0,2204** |
| C1 cubo, presenze del modello | 0,2779 | 0,0542 | 0,2208 |

Nel 2025-26 `I1` è più vicino al vero sui gol per rosa; nel 2024-25 ha il Brier
più basso. Erano valori puntuali senza intervallo, e li ho letti come criterio
soddisfatto. Da qui in avanti la distinzione è obbligatoria: **valore puntuale
migliore**, **differenza incerta**, **criterio soddisfatto** sono tre cose
diverse.

### 15.2 Che cosa è collegato e che cosa no

| affermazione delle fasi 1-4 | stato dopo la verifica |
|---|---|
| il braccio `C1` esiste | **vero nel banco**, ma `l2_genera_cubo.py:234` chiama ancora `pa.stima(Ppre)` senza bersagli: il generatore ordinario non lo produce |
| l'eleggibilità al fit è collegata al denominatore | **vero come colonna**, ma il consumatore non impone né verifica quale fit: `l2_panel_qualita.json` riporta `data_fit = 2026-09-08` per **tutte e cinque** le stagioni |
| il fattoriale usa le previsioni delle presenze | **parziale**: l'aggiornamento scorre solo i giocatori con voti storici (§R2) |
| gli intervalli del verdetto | **non** incorporano le dipendenze dichiarate in §3.3: il codice stesso dichiara di ignorarle |
| la coda: «l'eccesso viene dall'incertezza, non dalla specificazione» | **troppo forte**. Il confronto mostra che aggiungere l'incertezza alza la coda prevista; non dimostra che il punto stimato sia calibrato. I rapporti punto su osservato restano 1,40-2,09, e gli eventi osservati sono 2, 3 e 2 nelle tre stagioni |

«Dentro l'intervallo di Clopper-Pearson» non identifica una causa: le
probabilità differiscono per partita, la dipendenza non è trattata, e con due o
tre eventi osservati l'intervallo è largo quasi quanto lo spazio dei valori
possibili.

### 15.3 Il cutoff storico non è imposto dal consumatore

`data_fit` è un parametro dello script che costruisce il panel, e il suo
predefinito è **oggi**. Un panel costruito oggi porta `data_fit = 2026-09-08`
per la stagione 2021-22: se qualcuno lo usasse per un fit datato 2024, starebbe
consumando prove del 2026 senza che nulla glielo impedisca.

Il consumatore deve ricevere il cutoff, chiedere la vista corrispondente,
verificarne i metadati e **rifiutare** una vista incompatibile. Finché non lo
fa, la colonna `eleggibile_fit` è una promessa non mantenuta.

---

## 16. R1-R3: che cosa è stato collegato, e che cosa la correzione ha rivelato

### 16.1 Il contratto temporale, imposto dal consumatore

`src/fantabot/tabellino/contratto.py`, nuovo. Il cutoff entra nel **nome del
file** (`l2_panel_2024-25__fit20260908.parquet`) e nei metadati accanto; i
consumatori chiedono la vista che gli serve, ne verificano i metadati e
**rifiutano** quelle incompatibili, registrando che cosa hanno consumato.

Prova che attraversa il consumatore reale: chiedendo al generatore del cubo un
fit del 2024-08-16 su panel costruiti al 2026-09-08, alza
`ContrattoIncompatibile` invece di usarli. È il caso del backtest 2024 su panel
del 2026, chiuso.

L'universo e le rose ora si costruiscono con una funzione condivisa: prima il
banco usava `squadra` e il generatore `squadra_listone`, quindi i due
lavoravano su rose diverse e il confronto fra i loro generatori non era a
parità di universo. La scelta della colonna è un parametro dichiarato, e la
diagnostica riporta quanti giocatori differiscono (6 nel 2026-27, 30 nel
2024-25). **`squadra_listone` non è una certificazione temporale**: è la
squadra che il listone dichiarava quando è stato costruito, e chi la usa per
una decisione datata deve verificare quale fotografia rappresenta.

### 16.2 Le presenze, per l'universo completo

`src/fantabot/tabellino/presenze.py`, nuovo, condiviso fra banco e generatore.

Tre difetti riprodotti e chiusi:

| difetto | prima | dopo |
|---|---|---|
| universo troncato ai giocatori con storia | 264 ignorati nel 2024-25, 219 nel 2025-26 (somma delle probabilità previste 70,33 e 56,10, sostituita da un ripiego di 0,5 ciascuno: 132,0 e 109,5) | universo completo |
| `if q.get("pres")` scarta lo zero | 38 previsioni buttate nel 2024-25, 29 nel 2025-26 | tenute e contate |
| cold start: bersaglio saltato per chi non è in `prop_conv` | 136 su 587 nel 2026-27 | 136 **iniziati**, 0 saltati |

L'adattatore dichiara per ogni giocatore da dove viene il bersaglio
(`previsione`, `prior_ruolo`, `assente`) e tiene separati i due ripieghi che
prima erano uno solo: manca la previsione delle presenze è una cosa, manca lo
storico degli eventi è un'altra.

Il contratto dell'orizzonte è esplicito: `pres` è la somma delle presenze già
realizzate e di quelle previste per il resto, quindi `pres / 38` vale solo per
una stagione interamente futura; dopo K turni servono `presenze_gia_fatte` e
`giornate_residue`, che possono variare per giocatore quando i rinvii lo
rendono diverso fra squadre.

Il braccio `C1` è ora producibile dal **generatore ordinario**, non solo dentro
il banco: `l2_genera_cubo.py --bersaglio-presenze`, modalità sperimentale
esplicita che non cambia il comportamento predefinito.

### 16.3 La distribuzione campionata, e la rettifica di §14.2

Riprodotti tutti e sei i numeri del difetto: intensità massima **46,704**, 13
campioni su 200 con ρ non ammissibile, 194 combinazioni partita-campione su
76.000, coda analitica 0,0148570 contro 0,0147971 della matrice realmente
campionata, scarto massimo per partita 0,01073.

**Rettifica di §14.2.** L'identità delle marginali era misurata a intensità
fisse con ρ ammissibile. A romperla non è il troncamento — la rinormalizzazione
la conserva esattamente per ogni supporto ≥ 1, perché `q(y)` è diverso da zero
solo in 0 e 1 — ma il **clipping** `np.maximum(P, 0)` sulle estrazioni non
ammissibili: allontana le marginali dalla Poisson troncata fino a 2,9e-4.

Strategia scelta dopo verifica, non per comodità: **proiezione di ρ**
sull'intervallo ammissibile della singola partita, contata ed esposta. Rigetto
e riestrazione **rifiutati** con la ragione misurata: le combinazioni non
ammissibili hanno intensità mediana 11,23 contro 1,62 di tutte, quindi
rigettarle toglierebbe proprio le estrazioni più grasse — la mossa vietata.

Supporto adattivo al posto di `MAX_GOL = 12` fisso: 131 combinazioni su 76.000
avevano intensità oltre 12, e a λ ≈ 16 la massa fuori supporto valeva 0,83, cioè
la matrice diventava quasi una massa puntuale sul 12-12. Ora la massa fuori
resta sotto 1,9e-12.

**La correzione non abbassa la coda.** La coda realmente campionata **sale** da
0,014797 a 0,014857 per allinearsi a quella dichiarata: la coda è marginale e
le marginali non dipendono da ρ. L'eccesso rispetto all'osservato resta intero.

### 16.4 Che cosa resta aperto

- l'inferenza del fattoriale non è ancora rifatta con il ricampionamento che
  rispetta le dipendenze (R4);
- i risultati di §13 sono stati prodotti prima di tutte queste correzioni: vanno
  rifatti prima di essere citati di nuovo;
- «l'eccesso viene dall'incertezza, non dalla specificazione» (§14.3) resta
  **troppo forte**: il confronto mostra che aggiungere l'incertezza alza la coda
  prevista, non che il punto stimato sia calibrato.

---

## 17. Due errori scoperti mentre si chiudeva R4

Vanno scritti prima dei risultati, perché uno dei due dice che alcune cose che
sembravano fatte non lo erano.

### 17.1 Il banco non partiva più: `NameError: lst`

Durante R1 la lettura separata del listone (`lst = pd.read_parquet(...)`) è
stata sostituita dalla costruzione condivisa dell'universo
(`contratto.costruisci_universo`), perché banco e generatore lavoravano su rose
diverse. In quella sostituzione una riga più avanti è rimasta scoperta:

```python
rose_prova = rose_di_prova(lst, a.rose, a.seme)   # `lst` non esisteva più
```

Il banco cadeva con `NameError` **prima di produrre qualsiasi numero**.

**Che cosa invalida.** Niente di pubblicato: i verdetti in §13 sono precedenti
a R1 e non passano da questa riga. Ma smentisce una cosa che avevo scritto come
fatta: che le correzioni R1 e R2 fossero verificate «sui consumatori reali».
Erano verificate dai test unitari e dal generatore del cubo, **non** da
un'esecuzione del banco: il banco non è mai stato eseguito fra R1 e oggi, e se
lo fosse stato l'errore sarebbe uscito subito. La copertura dei consumatori
reali per il banco vale da adesso, non da R1.

**Correzione.** Le rose di prova ora si costruiscono dall'universo condiviso,
che è anche più coerente della lettura separata: pescano dagli stessi giocatori
su cui lavorano tutti i bracci.

**Perché non era stato visto.** Nessun test esegue `main()`: i test del banco
importano il modulo e provano le funzioni. Un errore che vive solo dentro
`main` non lo vedono. Non ho aggiunto un test che esegua `main` per intero —
costa un'esecuzione completa — quindi il rischio resta, e resta dichiarato.

### 17.2 Una prova di fumo ha sovrascritto un artefatto, e ho sbagliato due volte

La prima esecuzione del banco corretto è stata fatta con `--sims 4 --semi 2`
per vedere se il codice reggeva. Quattro scenari non sono un verdetto, ma lo
script scrive comunque `data/l2/banco_verdetto_2024-25.csv`, che conteneva il
verdetto pubblicato (1284 byte, sha256 `e5f7ad49243875b1`). È stato
sovrascritto. Poco dopo la rigenerazione a otto semi ha sovrascritto anche
quello del 2025-26.

**Il primo errore è la sovrascrittura.** Il banco scrive sempre sugli stessi
nomi, quindi qualunque esecuzione — anche esplorativa a quattro scenari —
sostituisce l'ultima.

**Il secondo errore è il rimedio che avevo scelto.** Ho ricostruito il
contenuto da `data/l2/r4_ricerca/r4_soglie_risultati.json` e ho scritto che
l'originale era perduto. Non lo era: il progetto tiene un archivio a contenuto
indirizzato in `data/istantanee/_archivio/`, e **tutti e due gli originali
erano lì per intero**. Li ho ripristinati in `data/l2/archivio/` verificando
che le impronte coincidano con quelle registrate dal ramo di ricerca. Le
ricostruzioni restano accanto agli originali solo perché il racconto
dell'errore resti verificabile.

**Che cosa invalida.** Nessun risultato. Invalida due frasi che avevo scritto:
«non è ricostruibile» a proposito del 2024-25, e «l'originale di quella
stagione non è stato toccato» a proposito del 2025-26 — vero quando l'ho
scritto, falso mezz'ora dopo. Entrambe corrette in
`data/l2/archivio/LEGGIMI.md`.

**La lezione operativa**, che vale più delle due frasi: prima di dichiarare
perduto un artefatto, cercarlo per impronta nell'archivio a contenuto
indirizzato. È lì apposta.

---

## 18. R4: l'inferenza del fattoriale, rifatta

Il metodo viene dal ramo di ricerca, `data/l2/r4_ricerca/RAPPORTO.md`, che ha
letto per intero Cameron & Miller (2015) e Ferro (2013) e ha verificato ogni
formula numericamente prima di consegnarla. Qui si scrive che cosa è entrato
nel codice e che cosa quel codice adesso sostiene.

### 18.1 L'intervallo: two-way cluster-robust su (partita, giocatore)

Il verdetto precedente ricampionava le righe come indipendenti. Non lo sono, e
le due dimensioni della dipendenza **si incrociano**: un giocatore compare in
38 partite, e una partita raccoglie tutti i giocatori delle due rose che
l'universo contiene — nel campione del Brier sono 67,9 righe per partita in
media, non i ventidue scesi in campo. Non essendo annidate, non
basta scegliere la più grossolana; serve la varianza two-way di Cameron &
Miller, equazione (21).

Il punto che cambia la lettura del vecchio metodo: l'intersezione fra i due
grappoli è la **singola riga**, quindi la varianza sulle righe non è una stima
sbagliata di quella giusta — è uno dei tre addendi, quello che va **sottratto**.

Misurato in simulazione su un disegno con la geometria del banco, 600 repliche,
correlazioni dichiarate prima di eseguire:

| errore standard | copertura, n = 25 802 (Brier) | copertura, n = 6 000 (CRPS) |
|---|---:|---:|
| righe indipendenti (metodo precedente) | **50,7 %** | **76,2 %** |
| one-way su partita | 84,2 % | 89,5 % |
| **two-way** | **92,8 %** | **93,7 %** |

Le due colonne sono i due campioni che il banco usa davvero, e vanno lette
insieme: il 50,7 % è il caso peggiore, non il caso unico. Metà dei verdetti
sono CRPS sul sottocampione, dove il metodo precedente copriva il 76,2 %.

L'errore standard sulle righe resta in tabella come **diagnosi**: il suo
rapporto con il two-way dice quanto la dipendenza conti in questi dati. Non è
un'alternativa fra cui scegliere.

Restano fuori dall'intervallo, dichiarati: l'incertezza dell'adattamento del
modello (un solo cubo, una sola stima), la variazione fra stagioni (con due
stagioni i grappoli sono due, e con G = 2 il wild cluster bootstrap dà
`p ≥ 1/2`: i verdetti si producono **una stagione per volta**), e il riuso
della validazione.

### 18.2 Il punteggio: empirico ed equo, entrambi

Il CRPS empirico con `m` scenari è distorto verso l'alto di `E|X−X'| / (2m)`:
penalizza un ensemble per il solo fatto di essere finito, e **premia la
sottodispersione**. Il punteggio equo di Ferro toglie la distorsione in forma
chiusa; la correzione è la dispersione di ensemble divisa per `m − 1`, sia per
il CRPS sia per il Brier.

La correzione **non si cancella nelle differenze**, perché dipende
dall'ensemble: si annulla se e solo se i due bracci hanno la stessa dispersione
media. Con `m = 30` il segno si ribalta quando il divario di dispersione supera
`|Δ| · 29`; per il confronto `C1 − I1` del 2024-25 bastavano 0,090. Per questo
la **dispersione media per braccio** è ora una colonna del banco: senza, quel
controllo nessuno lo può fare.

I due punteggi rispondono a due domande diverse — quanto vale l'ensemble a 30
membri, quanto vale il generatore da cui è estratto — e la scelta fra loro è
**sostanziale**. Non la faccio io: il banco riporta entrambi, e ogni confronto
compare due volte.

Limite dichiarato: la correzione equa è dimostrata per membri incorrelati a
coppie; i nostri scenari condividono lo stesso adattamento, quindi sono
positivamente correlati e la correzione necessaria sarebbe **più grande**
(Ferro, equazione 6). Quella standard è un limite inferiore.

### 18.3 Il rumore Monte Carlo: misurato, non ricampionato

Lo scenario non è una partizione delle righe — il punteggio di ogni riga è
funzione di tutti gli `m` scenari — quindi non esiste un bootstrap a grappoli
sugli scenari. L'unica via è ripetere con `R` semi e misurare la deviazione
standard fra le repliche. `R = 8` semi a `m = 30` costano quanto una sola
esecuzione a 240 scenari, e in più **misurano** ciò che una sola esecuzione non
può misurare.

L'adattamento dei modelli sta fuori dal ciclo sui semi e non cambia: varia solo
l'estrazione degli scenari. È quello che serve per isolare il rumore, ed è
anche il limite della misura.

Il requisito è `es_monte_carlo ≤ |Δ| / 10`, convenzione dichiarata prima di
eseguire. Quando non è soddisfatto l'esito è **«non misurabile con le risorse
disponibili»**, che non è «inconcludente» e non è «equivalente».

### 18.4 Le tre etichette che prima erano una sola

| esito | che cosa dice |
|---|---|
| `varianza non ammissibile` | `V_2way ≤ 0`: la stima non è utilizzabile e non viene sostituita da un one-way |
| `non misurabile con le risorse disponibili` | il rumore di simulazione domina la differenza |
| `differenza non rilevabile` | l'intervallo contiene lo zero |

Nessuna delle tre è «equivalenti». Diventerebbe equivalenza solo contro una
tolleranza dichiarata prima, e quella tolleranza **non è mia da fissare**:
resta un blocco aperto, insieme alla scelta fra i due bersagli di §18.2.

---

## 19. R4: i risultati, e un verdetto che cambia segno

Prodotti da `scripts/l2_banco_confronto.py` con 30 scenari e **8 semi**
(equivalente a 240 scenari, più la misura del rumore che una sola esecuzione
non può fare), inferenza two-way su (partita, giocatore), una stagione per
volta. Artefatti: `data/l2/banco_verdetto_{stagione}.csv`,
`banco_osservazioni_{stagione}.parquet`, `banco_semi_{stagione}.json`.

CRPS, differenza appaiata; negativo è a favore del primo termine.

### 19.1 I quattro confronti e l'interazione

| fattore | 2024-25 empirico | 2024-25 equo | 2025-26 empirico | 2025-26 equo |
|---|---:|---:|---:|---:|
| meccanismo, informazione storica (C0 − I0) | −0,0636 [−0,124; −0,003] | −0,0506 [−0,111; +0,010] | −0,0210 [−0,083; +0,041] | −0,0078 [−0,070; +0,054] |
| **meccanismo, presenze del modello (C1 − I1)** | **+0,0973 [+0,059; +0,135]** | **+0,1050 [+0,067; +0,143]** | **+0,0505 [+0,014; +0,087]** | **+0,0584 [+0,022; +0,095]** |
| informazione, per giocatore (I1 − I0) | −0,4002 [−0,456; −0,344] | −0,3907 [−0,446; −0,335] | −0,3874 [−0,450; −0,324] | −0,3793 [−0,442; −0,317] |
| informazione, cubo (C1 − C0) | −0,2393 [−0,292; −0,186] | −0,2350 [−0,288; −0,182] | −0,3159 [−0,376; −0,256] | −0,3131 [−0,373; −0,253] |
| **interazione** | **+0,1609 [+0,104; +0,218]** | **+0,1556 [+0,099; +0,212]** | **+0,0715 [+0,015; +0,128]** | **+0,0662 [+0,009; +0,123]** |

### 19.2 Che cosa è cambiato, e perché

**A informazione comparabile il cubo perde.** Era la riga «inconcludente» del
verdetto precedente (−0,0031 e −0,0188, intervalli che attraversavano lo zero).
Adesso è **+0,097 e +0,051, con l'intervallo lontano dallo zero**, sul CRPS e
sul Brier, in entrambe le stagioni, con il punteggio empirico e con quello equo.
Il punto stimato è dall'altra parte: non è una riverniciatura dell'incertezza.

La ragione è R2, e non è un caso fortunato: prima l'adattatore delle presenze
copriva solo i giocatori con storia, quindi il braccio `I1` riceveva la
previsione per una parte dell'universo e `p = 0,5` per **264 giocatori nel
2024-25 e 219 nel 2025-26**. Correggendo l'adattatore è migliorato **il braccio
avversario**. Il confronto precedente non misurava il meccanismo: misurava un
handicap dato al simulatore per giocatore.

**L'interazione è misurabile e ha un segno.** `(C1 − I1) − (C0 − I0)` vale
+0,161 e +0,072 sul CRPS, con intervalli che escludono lo zero in entrambe le
stagioni e su entrambi i punteggi: **il cubo trae meno dalle presenze del
modello di quanto ne tragga il simulatore per giocatore**. È la quantità che il
disegno a due confronti non poteva vedere, e spiega perché i due meccanismi si
scambiano di posto passando da un'informazione all'altra.

**Il vantaggio a informazione storica si è assottigliato.** Era «il cubo vince
su entrambe le stagioni e su entrambe le misure». Adesso: nel 2024-25 il CRPS
empirico esclude lo zero per un soffio (−0,0636, estremo superiore −0,003) e
quello equo non lo esclude più; nel 2025-26 il rumore Monte Carlo domina la
differenza. Sul Brier non è rilevabile in nessuna delle due.

**L'informazione continua a pesare molto più del meccanismo**, e più di prima:
da 0,32 a 0,40 di CRPS contro 0,01-0,10.

### 19.3 Quanto contava la dipendenza

Il rapporto fra l'errore standard two-way e quello del metodo precedente sta fra
**1,72 e 4,05** sulle venti righe del verdetto. Gli intervalli pubblicati in §13
erano da due a quattro volte troppo stretti. Non è una correzione cosmetica: la
riga `C0 − I0` del 2024-25 esclude lo zero con il metodo two-way solo per
0,003, e con il metodo vecchio sembrava larghissimamente esclusa.

### 19.4 Dove il punteggio scelto cambia il verdetto

Due righe cambiano esito passando dall'empirico all'equo:

- `C0 − I0`, CRPS 2024-25: empirico «C0 migliore», equo «differenza non
  rilevabile»;
- `C0 − I0`, Brier 2025-26: empirico «differenza non rilevabile», equo «non
  misurabile con le risorse disponibili».

È il caso che la ricerca prevedeva: la correzione equa dipende dalla dispersione
di ensemble, che fra i bracci non è uguale. La scelta fra i due bersagli —
valutare l'ensemble a 30 membri o stimare il generatore — è **sostanziale** e
resta aperta: entrambe le colonne sono pubblicate.

### 19.5 Riproducibilità, verificata

`scripts/l2_inferenza_banco.py --verifica` rifà l'inferenza dalle sole
osservazioni conservate e ottiene il verdetto pubblicato con scarto massimo
**0,00e+00** su differenza, estremi, errori standard e rumore Monte Carlo, in
entrambe le stagioni. Serve anche a un'altra cosa: le correzioni ai rilievi
della verifica (§20) sono state applicate **dopo** l'esecuzione, e questa
riproduzione con il codice corretto mostra che non spostano nessun numero.

### 19.6 Che cosa questi numeri NON dicono

- **Nulla sul 2026-27**, che è la stagione dell'asta. Le due stagioni misurate
  sono validazione già consultata molte volte (§13.3): l'intervallo corregge il
  campionamento, non la selezione.
- **Nulla sull'incertezza dell'adattamento.** Un solo cubo, una sola stima. §14
  mostra che il trattamento di quell'incertezza cambia risultati di un fattore
  2-3.
- **Nulla di causale.** «Il cubo trae meno dalle presenze» descrive il segno di
  un contrasto, non il meccanismo che lo produce.
- **Nessuna equivalenza.** Dove l'intervallo contiene lo zero, la lettura è
  «differenza non rilevabile con questo disegno». Diventerebbe equivalenza solo
  contro una tolleranza dichiarata prima, che nessuno ha dichiarato.
- **Nessuna promozione.** Il cubo resta non promosso, e adesso con una ragione
  in più.

---

## 20. La verifica di R4, e perché il suo esito non va preso alla lettera

Il codice di R4 è stato passato a una verifica avversariale a tre lenti
indipendenti — le formule contro le fonti, il cablaggio dentro il banco, le
affermazioni scritte contro le prove — e ogni rilievo è passato da un
confutatore separato. Ventisei rilievi grezzi, **zero confermati**.

Quello zero non è un risultato: è un difetto del disegno della verifica. Ai
confutatori avevo dato la regola «in caso di dubbio, confuta», per non far
passare rilievi falsi. Con quel prior hanno scartato anche i rilievi veri,
rispondendo a fianco della questione: al rilievo «il controllo dell'interazione
è una tautologia» il confutatore ha risposto che il protocollo non lo pubblicizza
— che è vero e irrilevante, perché a mentire era il commento nel codice.

Ho quindi riletto i ventisei grezzi e deciso io. Otto erano veri, e sono
corretti:

| rilievo | correzione |
|---|---|
| il controllo dell'interazione confrontava due scritture algebricamente identiche: non poteva fallire | sostituito con l'unico controllo che a valle ha senso (le quattro lunghezze), e il commento adesso dice che cosa garantisce davvero l'appaiamento |
| con un solo seme l'esito poteva dire «C1 migliore» senza che il rumore Monte Carlo fosse mai misurato | l'etichetta porta scritto «(rumore Monte Carlo non misurato)» |
| la logica delle etichette era scritta due volte, e i test provavano la copia che il banco non esegue | una sola stesura, `inferenza.esito_confronto`, usata dal banco |
| l'errore standard one-way usciva NaN dove la risposta giusta è zero | zero, che è informativo: dice che dentro grappolo non resta niente |
| `intervallo_two_way` assume che la cella (partita, giocatore) sia unica per riga, senza dirlo né sorvegliarlo | ipotesi dichiarata e sorvegliata; si può disattivare la guardia, ma va scritto |
| `rho_intra` assume grappoli bilanciati | limite dichiarato nel docstring |
| il controllo della prima finestra in `l2_progressivo.py` confrontava un oggetto con sé stesso | la prima origine viene rigenerata, così il controllo può fallire |
| la copertura «50,7 %» era il caso peggiore presentato come l'unico | §18.1 riporta entrambi i campioni: 50,7 % sul Brier, 76,2 % sul CRPS |

Più due correzioni ai fatti: la geometria del grappolo partita (67,9 righe in
media, non ventidue) e l'incidente dell'artefatto (§17.2), dove i confutatori
hanno avuto ragione loro e io torto — gli originali erano nell'archivio a
contenuto indirizzato.

**Un rilievo vero che NON ho corretto**, e la ragione. La soglia del rumore
Monte Carlo è `es_mc ≤ |Δ| / 10`: quando `Δ` tende a zero la soglia tende a
zero, quindi un confronto genuinamente nullo finisce etichettato «non
misurabile con le risorse disponibili» invece di «differenza non rilevabile».
È un effetto reale, e si vede nel 2025-26 su `C0 − I0`. Non l'ho cambiata
perché **la soglia era dichiarata prima di eseguire**, nella regola operativa
del ramo di ricerca, e spostarla adesso — dopo aver visto quali righe finiscono
da che parte — è esattamente la mossa che questo protocollo vieta. Chi legge
quella etichetta guardi anche `es_monte_carlo` e `ic_basso`/`ic_alto`: se
l'intervallo contiene lo zero **e** il rumore è dello stesso ordine della
differenza, le due letture coincidono nella sostanza e divergono solo nel nome.
