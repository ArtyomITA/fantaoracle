# Livello 0 — diario dei fix, 6 settembre 2026

Fix a costo zero della sintesi delle architetture (`reports/ARCHITETTURE_2.0.md`,
sezione 2). Regola seguita: un fix per volta, ognuno con una misura fatta prima
di toccare il codice, tenuto solo se la misura lo sostiene. Ogni numero qui
sotto e' riproducibile con gli script citati; gli esiti grezzi stanno in
`data/livello0/`.

Stato di partenza (fine sessione precedente): piano 2026/27 con P(1°) 39%,
validazione 2024/25 2953 punti e 2025/26 2882 punti.

---

## 1. Prezzi contaminati dal campionato in corso

**Il problema.** Il modello prezzo veniva addestrato, per la stagione 2025/26,
su un listino di fantacalcio-online catturato l'11 aprile 2026: un prezzo
scritto quando tre quarti del campionato erano gia' giocati. Lo stesso listino
alimentava il `ref_price`, cioe' quanto i bot avversari credono valga ogni
giocatore nelle aste simulate, e quindi anche il metro con cui si giudica il
piano.

**Prova 1** (esito in `data/livello0/prova_wayback_vs_estiva.json`):
confrontando quel listino con i prezzi delle aste estive reali sulle stagioni
in cui esistono entrambi, non e' la stessa cosa. Correlazione di rango 0.72-0.84,
errore medio 8-14 crediti, e soprattutto un errore che cambia segno per fascia:
il listino paga 14-17 crediti chi all'asta vera va a 2, e sottopaga di 8-23 i
giocatori sopra i 40.

**Prova 2** (`scripts/indagine/prova_target_prezzo.py`): addestrando lo stesso
modello, con le stesse feature e lo stesso test (aste estive vere), una volta
sul target d'asta e una volta sul listino:

| test = aste estive vere | train su aste | train su listino |
|---|---|---|
| errore medio 2023/24 | 5.96 | 11.95 |
| errore medio 2024/25 | 6.43 | 16.39 |
| errore sotto i 15 crediti (2024/25) | 3.46 | 16.78 |
| correlazione di rango 2024/25 | 0.808 | 0.753 |

**Cosa ho cambiato.**
- `scripts/f1_train_price.py`: tabella `PRICE_SOURCES` con la fonte, la data e
  la validita' di ogni stagione. Il target ammesso e' solo un prezzo noto prima
  dell'asta: aste estive reali per 2021/22, 2023/24 e 2024/25; il listino del
  1° settembre 2026 per la stagione corrente; **niente** per il 2025/26, che
  quindi esce dal training del prezzo. Rimosso anche il run di valutazione R3,
  che misurava contro quel listino.
- `scripts/f2_build_packs.py`: il `ref_price` usa solo fonti pre-asta. Dove
  mancano, la quotazione del listone viene **tradotta** in prezzo con una curva
  monotona stimata sulle aste delle stagioni precedenti (la quotazione ordina
  bene, correlazione 0.80-0.85, ma vive su un'altra scala: 1-41 contro 1-184
  crediti; dividerla per una costante dimezzava il mercato).

**Effetto misurato.** Somma dei prezzi predetti sul listone 2026/27 da 5551 a
4332 crediti, con la fascia sotto i 15 crediti che scende da 4.4 a 2.6 di media:
spariti i prezzi gonfiati che il listino di gennaio aveva insegnato. Sul
benchmark 2025/26 gli archetipi avversari, che prima compravano con prezzi
sballati, ora sono competitivi (da 2630 a 2874 punti) e il piano passa da
vincere il 9% delle volte al 28%.

---

## 2. Effetto squadra nel Monte Carlo

Verificato: `TEAM_SHOCK_SD` in `src/fantabot/montecarlo.py` vale 0.25, il
valore misurato al netto del rumore campionario. Nessuna modifica.

---

## 3. Nuovi arrivati: premio di prezzo e mescolanza con la FVM

**Premio di prezzo** (`scripts/indagine/prova_premio_nuovi.py`, 1019 righe di
aste estive vere). A parita' di quotazione e ruolo i nuovi costano **+18.6%**
(intervallo 95%: da +4.8% a +34.2%): il premio esiste. Ma:

- sui soli giocatori cari, dove la correzione veniva applicata, e' +7.8% con
  intervallo da -4.4% a +21.6%: indistinguibile da zero, 46 casi in tre stagioni;
- applicare +20% sopra la previsione peggiora la previsione stessa: errore
  medio sui nuovi da 3.78 a 4.38 nel 2023/24, e nel 2024/25 il guadagno c'e'
  solo con +10% e sparisce a +20%. Segno incoerente fra le due stagioni.

**Correzione del 6/9, secondo giro di verifiche** (`scripts/indagine/audit_coda_nuovi.py`).
Due delle motivazioni che avevo scritto erano deboli e vanno sostituite:

- avevo dedotto il "doppio conteggio" dalla sola presenza del flag "nuovo in
  Serie A" fra le feature. L'ablation dice che non basta: togliendo il flag i
  nuovi si spostano di +0.65 crediti nel 2023/24 (il modello lo usava) e di
  -0.32 nel 2024/25 (non lo usava). La rimozione resta giustificata dalla
  misura diretta qui sopra, non da questo argomento;
- avevo giustificato la rimozione della coda allargata con la dispersione del
  prezzo fra aste diverse (0.636 contro 0.626). Quella misura dice quanto le
  leghe sono in disaccordo, non quanto sbaglia il modello. La misura giusta e'
  la copertura dell'intervallo fuori campione, e dice una cosa diversa ma
  compatibile con la decisione: **i nuovi sono i meglio coperti, non i peggio**
  (copertura 0.39 e 0.42 contro 0.25 e 0.16 dei vecchi nelle due stagioni),
  quindi allargare la banda solo a loro era il contrario di quel che serviva.

  Ne emerge pero' un problema piu' grande, che riguarda tutti: **la banda
  q10-q90 del prezzo copre fra il 16% e il 42% invece dell'80%**, e allargarla
  migliora il pinball sul q90 per tutti, soprattutto per i vecchi (da 3.19 a
  1.32 nel 2023/24, da 2.51 a 1.90 nel 2024/25). Vedi "Punti sospesi".

**Cosa ho cambiato.** Rimossi da `src/fantabot/market_adjust.py` sia il
moltiplicatore 1.20 sia l'allargamento della coda. L'incertezza piu' alta dei
nuovi resta dove e' misurata davvero, cioe' sui punti attesi (Monte Carlo e
bot avversari).

**Premio per provenienza (top-5, rientri dall'Italia, leghe minori): NON
implementato.** Nel repository non esiste una colonna di provenienza per le
stagioni passate, e il campione utile sarebbe di 46 nuovi cari divisi in
quattro o cinque categorie. Le percentuali del rapporto (+10/+18% dalle top-5,
-27/-34% per i rientri) venivano per meta' dal listino contaminato di cui al
punto 1: vanno rifatte da zero prima di poterle usare. Vedi "Punti sospesi".

**Mescolanza modello + FVM sui nuovi cari: NON implementata.** Misurata sui
nuovi con quotazione almeno 8: nel 2024/25 il modello da solo fa 0.889 di
correlazione contro 0.831 della mescolanza a meta', nel 2025/26 e' il contrario
(0.701 contro 0.755). Peggiora una stagione su due, quindi non passa la regola.
Il guadagno riportato nel rapporto era su un modello valore precedente, prima
delle modifiche di ieri.

---

## 4. Disponibilita' con memoria

**Il problema.** Nel Monte Carlo ogni giornata era un lancio di moneta
indipendente: un giocatore fermo da un mese aveva la stessa probabilita' di
giocare di uno in campo da dieci turni.

**Prova** (`scripts/indagine/prova_hazard_presenze.py`). Gli scostamenti sono
stimati sul logit del tasso individuale, quindi **al netto** della differenza
fra titolari e riserve: quello che resta e' vera memoria dello stato. Su 57.925
giocatore-giornata (2021/22, 2023/24, 2024/25):

| stato alla vigilia | presenze osservate | attese dal solo tasso | scostamento |
|---|---|---|---|
| in campo da 1 turno | 0.638 | 0.535 | +0.425 |
| in campo da 2 | 0.749 | 0.601 | +0.683 |
| in campo da 3 o piu' | 0.844 | 0.740 | +0.641 |
| fuori da 1 turno | 0.473 | 0.533 | -0.240 |
| fuori da 2 | 0.322 | 0.442 | -0.508 |
| fuori da 3-4 | 0.212 | 0.358 | -0.732 |
| fuori da 5 o piu' | 0.083 | 0.202 | -1.031 |

Verifica sulla stagione 2025/26, mai vista in stima: Brier da 0.1636 a 0.1427
(**-12.8%**), migliora in tutti gli stati.

**Cosa ho cambiato.** In `src/fantabot/montecarlo.py` la disponibilita' e' una
catena con memoria della durata. Il livello base di ogni giocatore viene
**tarato** perche' la quota di giornate giocate resti quella prevista (verifica:
obiettivo 0.20/0.50/0.80/0.95, catena 0.2000/0.5000/0.8000/0.9500): la memoria
cambia la forma delle assenze, non quante sono. Le assenze ora arrivano a
blocchi di 2.75 giornate contro le 2.00 di una moneta senza memoria, e il dato
reale misurato nel rapporto e' 2.68.

**Limite dichiarato.** I dati dicono solo se il giocatore ha preso voto, non
perche': infortunio, squalifica, panchina e pochi minuti stanno insieme. E' un
modello della presenza a voto, non dell'infortunio, ed e' scritto nel codice.

---

## 5. Scenari comuni nella scelta dell'obiettivo

**Il problema.** `f12` sceglieva l'obiettivo confrontando otto candidate
ognuna su stagioni simulate diverse: buona parte della differenza fra loro era
sorteggio.

**Cosa ho cambiato** (`src/fantabot/montecarlo.py`):
- i numeri casuali sono indicizzati per giocatore e per squadra invece che
  estratti in sequenza: lo stesso giocatore vive la stessa stagione in
  qualunque rosa compaia (verificato: due chiamate con generatori diversi e
  stesso indice danno risultati identici);
- avversari e calendario sono gli stessi per tutte le candidate;
- la candidata vincente viene **rigiocata su scenari mai usati per sceglierla**,
  e il valore riportato e' quello, con il suo intervallo.

**Effetto misurato.** Confrontando due rose che differiscono di un solo
attaccante, l'errore standard della differenza passa da 21.5 a 5.5 punti
stagione (**-74%**).

---

## 6. Registro dei rilanci nel Copilota

`scripts/f10_copilot.py` salvava solo le aggiudicazioni. Aggiunti:

- `POST /copilot/bid` registra un rilancio osservato al tavolo con orario,
  lotto, squadra e importo; non tocca rose ne' budget, perche' il lotto e'
  ancora aperto;
- `POST /copilot/undo_bid` cancella l'ultimo rilancio;
- `GET /copilot/state` espone quanti sono e gli ultimi quindici;
- ogni riga porta il campo `fonte`, oggi sempre "osservato": i rilanci
  registrati sono solo quelli davvero pronunciati, mai simulati o dedotti;
- i ledger scritti prima di questa modifica si riaprono senza errori (il
  registro parte vuoto).

Nell'interfaccia (`viz/copilot.html`), sotto il prezzo del giocatore al banco:
una riga "CHI HA RILANCIATO?" con un bottone per squadra che segna il rilancio
all'importo corrente, il conto dei rilanci gia' registrati su quel lotto, e un
pulsante per annullare l'ultimo.

Provato davvero, non solo sugli endpoint: copilota avviato su una porta di
prova, interfaccia aperta nel browser, giocatore portato al banco, due rilanci
registrati da due squadre diverse a importi diversi (1 e 21). L'interfaccia
mostra "2 su questo lotto" e "annulla rilancio: Malen · Ale 1"; i due rilanci
finiscono nel ledger con lo stesso numero di lotto e nell'ordine giusto;
fermando e riavviando il copilota con la ripresa dal ledger i due rilanci ci
sono ancora; l'annulla ne toglie uno solo. Anche i ledger scritti prima di
questa modifica si riaprono senza errori.

---

## 7. Formazioni: niente conoscenza anticipata

**Il problema.** Entrambi i simulatori sceglievano gli undici passando
l'elenco di chi avrebbe preso voto **quella** giornata: informazione del futuro.

**Prova.** Otto rose casuali sulla stagione 2025/26 con voti reali, formazione
scelta sapendo chi gioca contro formazione scelta con l'ultima giornata nota:
sapere il futuro rende **-35 punti stagione** in media (deviazione 17), perche'
l'euristica mandava in campo il disponibile scarso invece del titolare che
sarebbe stato sostituito da un cambio.

**Cosa ho cambiato.** In `src/fantabot/season/simulate.py` la disponibilita' e'
quella della giornata precedente; in `src/fantabot/montecarlo.py` e' lo stato
della catena alla vigilia. Nessuno dei due guarda piu' avanti.

---

## 8. Budget non speso e soglia di spesa

**Il problema segnalato.** Nella validazione 2025/26 il piano risultava
costare 399 crediti su 500: 101 crediti che a fine asta valgono zero.

**Diagnosi** (`scripts/indagine/diagnosi_budget.py`), nell'ordine:

1. *prezzi*: il piano viene costruito sui prezzi che il modello prevede
   (le sue stime) e veniva **contato** ai prezzi di mercato. Sono due numeri
   diversi della stessa rosa: alle proprie stime impegnava gia' 494 crediti su
   500, cioe' il 98.8%. Il "399" era la stessa rosa valutata con prezzi
   diversi, non budget lasciato in cassa;
2. *vincoli*: togliendo la quota d'attacco il risultato non cambia;
3. *candidati*: con i crediti che avanzano non esiste nessuno scambio che
   aumenti il valore della rosa;
4. *risolutore*: ottimo dichiarato, identico con 10 e con 60 secondi di tempo.

**Cosa ho cambiato comunque.** Una soglia esplicita e configurabile
(`MIN_SPEND_FRAC` in `src/fantabot/rules.py`, oggi 0.95 cioe' 475 crediti su
500) come vincolo del piano iniziale in `optimize_roster`, usata da `f12` e
`f13`. Tiene sempre da parte un credito per ogni slot ancora da riempire, cosi'
la rosa resta completabile, e **non tocca l'asta viva**: ad asta iniziata il
budget e' quello residuo e forzare la spesa vorrebbe dire alzare le offerte
senza motivo. Se nessuna rosa raggiunge la soglia, `f13` si ferma con un
messaggio esplicito invece di consegnare un piano che non la rispetta.

**Confronto fra tre piani** (`scripts/indagine/confronto_piani_budget.py`,
stagione 2025/26, stessi prezzi, stessi scenari, stessi avversari, stesso
calendario; i due attaccanti di prima fascia sono scelti col prezzo di mercato
atteso, non col rendimento poi realizzato):

| piano | impegnato | al mercato | attacco | punti | P(1°) banco | P(1°) verifica |
|---|---|---|---|---|---|---|
| libero (com'era) | 494 | 356 | 122 | 3219 | 69.0% ± 4.6% | 59.0% ± 4.9% |
| con soglia 475-500 | 494 | 356 | 122 | 3219 | 69.0% ± 4.6% | 59.0% ± 4.9% |
| due attaccanti di prima fascia | 500 | 398 | 268 | 3187 | 56.0% ± 5.0% | 55.0% ± 5.0% |

Qui la soglia non cambia il piano perche' era gia' rispettata sui prezzi di
costruzione. Imporre due attaccanti di prima fascia costa 13 punti percentuali
di probabilita' di vittoria sul banco di confronto e 4 sulla verifica
indipendente: e' la risposta misurata alla domanda "servono i top in attacco".

**Dove la soglia cambia le cose davvero** e' il piano costruito direttamente
ai prezzi di mercato, cioe' la variante che nel benchmark 2025/26 costava 399
crediti. Con la soglia attiva:

| piano al mercato, 2025/26 | prima | dopo |
|---|---|---|
| costo | 399 | 489 |
| punti sui voti reali | 2937 | 2946 |
| vittorie contro gli archetipi | 23.7% | 69.3% |
| posizione media | 2.63 | 1.41 |
| attacco | Yildiz, Pellegrino, Davis | Thuram, Douvikas, Yildiz |

I 90 crediti in piu' comprano Thuram e spostano la posizione media di piu' di
un posto. Era la correzione giusta da chiedere.

Nota tecnica emersa: imponendo i due attaccanti piu' cari la quota d'attacco
dell'obiettivo (al massimo il 50% del budget) diventa impossibile da
rispettare, perche' i due da soli costano 294 crediti. Per quel confronto la
quota e' stata rilassata, ed e' scritto nello script.

---

## Risultato complessivo

Piano 2026/27 (`f12`, 100 scenari): obiettivo con peso 0.5 sull'incertezza e
35-50% del budget in attacco, modulo 3-5-2. P(1°) in selezione 59%, **su
scenari mai usati per sceglierlo 53% ± 5%** (intervallo 95%: 43-63%).

**Il 39% di partenza e il 53% di adesso non sono confrontabili**: vengono da
banchi diversi (nel frattempo sono cambiati disponibilita', numeri casuali,
formazione ed effetto squadra). Il confronto onesto e' far giocare le due
ROSE sullo stesso banco corretto
(`scripts/indagine/rerun_appaiato_baseline.py`):

| rosa | costo al mercato | punti | P(1°) banco | P(1°) verifica |
|---|---|---|---|---|
| quella scelta il 5/9, prima dei fix | 445 | 3130 | 16.0% ± 3.7% | 24.0% ± 4.3% |
| quella scelta oggi | 495 | 3227 | 54.0% ± 5.0% | 51.0% ± 5.0% |

Differenza sulla verifica indipendente: **+27 punti percentuali**, errore
standard 6.6%. Parte del guadagno viene dal fatto che la rosa di oggi impegna
50 crediti in piu'.

Validazione sui voti reali:

| | inizio sessione | ora |
|---|---|---|
| 2024/25 (prezzi osservati per il 90% dei crediti), punti | 2953 | 2972 |
| 2024/25, vittorie | 81% | 96.7% |
| 2025/26 (diagnostica, 0% prezzi osservati), punti | 2882 | 2937 |
| 2025/26, vittorie | 9% | 23.7% |

Il confronto fra le prime candidate di `f12` resta dentro l'incertezza: 59%,
58% e 55% con un errore standard di 5 punti sono la stessa cosa.

I P(1°) degli archetipi sono ora calcolati nello stesso tavolo da dieci in cui
gioca il piano (prima erano un torneo a nove che escludeva il piano, quindi su
un'altra scala): sommati al piano fanno circa 1, come deve essere.

Piu' varianza non e' garanzia di vittoria: nella tabella di `f12` le candidate
con deviazione piu' alta a giornata non sono sempre davanti, e il peso
sull'incertezza scelto (0.5) e' intermedio.

---

## Punti sospesi (richiedono una decisione, non li ho forzati)

1. **Stagione 2025/26 senza prezzi d'asta: e' solo diagnostica.** Non esiste
   alcuna rilevazione fatta prima dell'asta: le aste reali di quella stagione
   non sono state raccolte e i listini disponibili sono di dicembre, aprile e
   agosto successivi. Copertura misurata dei prezzi osservati nella rosa del
   piano:

   | stagione | giocatori del piano con prezzo d'asta osservato | crediti coperti |
   |---|---|---|
   | 2024/25 | 20 su 25 (80%) | 446 su 498 (90%) |
   | 2025/26 | 0 su 25 (0%) | 0 su 489 (0%) |

   Quindi **il 2024/25 e' la validazione, il 2025/26 e' diagnostica**: i suoi
   numeri dicono come si comporta il modello, non quanto vale un piano a
   prezzi veri. Opzioni: cercare le aste 2025/26 (il forum da cui vengono le
   altre pubblica le edizioni con ritardo), oppure tenerlo come tale.

1-bis. **Copertura degli intervalli di prezzo, per tutti.** La banda q10-q90
   copre fra il 16% e il 42% invece dell'80% dichiarato, e i vecchi stanno
   peggio dei nuovi. Allargarla migliorerebbe il pinball in modo netto
   (q90: da 3.19 a 1.32 nel 2023/24, da 2.51 a 1.90 nel 2024/25). E' una
   ricalibrazione del modello prezzo, non un fix a costo zero: non l'ho
   applicata.
2. **Premio per provenienza: rinviato** su indicazione. Servirebbe una colonna
   di provenienza per le stagioni passate (ricavabile dai trasferimenti
   Transfermarkt, che pero' non riportano la lega di partenza: va costruita una
   mappa club-lega) e comunque il campione resta di ~46 nuovi cari.
3. **Crediti non spesi: risolto**, vedi la sezione 8. Il piano impegnava gia'
   il 98.8% del budget ai prezzi con cui viene costruito; la soglia esplicita
   e' comunque stata aggiunta e sul piano costruito ai prezzi di mercato porta
   la spesa da 399 a 489 crediti e le vittorie dal 23.7% al 69.3%.
4. **File `config/league.yaml`**: risolto. Non e' letto da nessuno script e
   conteneva due valori sbagliati (fascia 7.0 del modificatore a +6 invece di
   +5, crediti di gennaio 50 invece di 100), ora corretti. In testa al file ora
   c'e' scritto quale file governa davvero ogni regola
   (`src/fantabot/rules.py` per rosa, budget, sostituzioni, modificatore e
   soglia di spesa; `src/fantabot/season/lineup.py` per le soglie dei gol e i
   moduli; `scripts/f2_build_packs.py` per quote e budget dei pack) e che in
   caso di disaccordo vale il codice.
5. **File `nul` nella radice del progetto** (12 KB): spazzatura di un
   reindirizzamento Windows sbagliato. Irrilevante, lasciato dov'e'.

## Regole della lega, verificate nel codice

`src/fantabot/rules.py`: rosa 3 portieri, 8 difensori, 8 centrocampisti, 6
attaccanti; 500 crediti; 3 sostituzioni; porta inviolata +1; modificatore
difesa con fasce 6, 6.25, 6.5, 6.75 e 7 che valgono +1, +2, +3, +4 e +5.
`src/fantabot/season/lineup.py`: primo gol a 66 punti, uno in piu' ogni 6.
Nessun bonus per gol vittoria o pareggio. Tutto corrisponde a quanto indicato.
