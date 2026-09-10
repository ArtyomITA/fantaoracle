# B — Asta intera dalla pagina vera (250 lotti, con guasti)

Data 10/9/2026. Copilota `scripts/f10_copilot.py` 2026-27, porta 8794, ledger di prova
`data/copilot/prove/ledger_w6_asta.json`. Pagina `viz/copilot.html?live=http://127.0.0.1:8794`
in Chrome di sistema (Playwright, `channel="chrome"`, headless, viewport 1366x768).
Ogni azione d'asta passa DALLA PAGINA (ricerca digitata, click sulla riga, casella prezzo,
martelletto, U-U, «non lo voglio nel piano», «calcola», «esporta»); l'API serve solo come
strumento di controllo (`/copilot/state`, `/copilot/plan`, `/copilot/players`).

Script: `scratchpad/w6/asta_intera.py` — `python asta_intera.py [--lotti 250] [--limite-min 40]`.
Registro per lotto: `scratchpad/w6/asta_intera_log.jsonl`. Esiti e anomalie in
`scratchpad/w6/asta_intera_esiti.json`. Schermate `asta_lotto_050/100/150/200/250.png` e
`asta_finale.png`. Export scaricato dalla pagina: `scratchpad/w6/export_pagina.json`.
Prima corsa (con due inciampi dello script di prova, poi corretti) archiviata in
`scratchpad/w6/corsa1/`.

## Esito: nessun difetto del Copilota

Corsa buona (`corsa_250.txt`, EXIT=0, 0 anomalie): 250 lotti in **2,8 minuti**, ordine
P 30 · D 80 · C 80 · A 60, chiamante a rotazione sulle 10 squadre.

| verifica | esito |
|---|---|
| rosa di Io completa | **3/8/8/6** |
| budget di Io | **4** (mai negativo) |
| budget finali delle 10 squadre | 4, 50, 124, 142, 8, 70, 64, 180, 262, 262 — nessuno negativo |
| rose delle 10 squadre | tutte 3/8/8/6, nessun reparto oltre quota |
| eventi nel ledger | **250** (`ledger_w6_asta.json`), 250 anche nell'export |
| pagina contro `/copilot/state` (budget + conteggi rosa) | coincidono a **tutti i 250 lotti** (0 divergenze) |
| console del browser | 1 sola voce, durante l'uccisione voluta del server (vedi O2) |

Tempi misurati lotto per lotto (250 campioni):

| tempo | mediana | p95 | massimo | limite | fuori limite |
|---|---|---|---|---|---|
| ricerca (digitazione -> riga in lista) | 0,33 s | 0,35 s | 0,48 s | — | — |
| consiglio (click sulla riga -> `C.advice`) | 0,05 s | 0,06 s | **0,16 s** | 1,5 s | 0 |
| martelletto -> «VENDUTO» | 0,10 s | 0,36 s | **0,76 s** | 3 s | 0 |
| piani («calcola» -> schede) | — | — | **1,7 s** (lotto 70), 0,9 s (lotto 150) | 25 s | 0 |

## Guasti provati, tutti superati

- **Undo doppio dopo il lotto 60**: `U` `U` da tastiera (fuoco fuori dalle caselle),
  `n_events` 60 -> 59; riacquisto dalla pagina dello stesso giocatore, stessa squadra,
  stesso prezzo -> 60. Nessuno stato incoerente.
- **Esclusione e riammissione**: dopo il lotto 100 «✕ non lo voglio nel piano» su un target
  attaccante (Ramos G.), presente in `esclusi_manuali`; dopo il lotto 110 riammesso dalla
  pagina (ricerca con «anche fuori lista ed esclusi», poi «↩ riammetti»), sparito da
  `esclusi_manuali`.
- **Server ucciso e ripreso**: dopo il lotto 150 `taskkill /F /T /PID`, riavvio con
  `--resume` sullo stesso ledger, `pg.reload()`. `n_events` 150 -> 150, budget e rose
  identici, pagina ricaricata coincidente con il server.
- **Fuori lista**: 2 acquisti registrati con la casella «anche fuori lista ed esclusi»
  (lotto 25 Piana -> Marco 1 cr; lotto 115 Anjorin -> Paolo 2 cr): il consiglio dice
  «FUORI SERIE A (listone)», il martelletto registra lo stesso e il budget resta giusto.
- **Furti dei target di piano**: **12** target del piano finiti agli avversari (richiesti >= 6),
  di cui 7 forzati (lotti 40, 55, 90, 120, 140, 175, 191). Bomber di riferimento del piano
  all'arrivo del blocco A: **Malen, tetto consigliato 168, comprato da Sara a 178** (sopra il
  tetto). Il Copilota ha continuato a proporre alternative senza incoerenze (schede dei piani
  ricalcolate a metà D e metà C: 7 e 6 alternative).
- **Export**: il download dalla pagina è partito anche in headless
  (`asta_2026-27_2026-09-10143552.json`, 587 KB, salvato come `export_pagina.json`).
  Dichiara il pack — `bundle.pack = pack_2026-27.pkl`, impronta `71ec262b4bdf…`, 594 giocatori —
  e le fonti — `fonti.acquisito = 2026-09-09T22:35:18Z`, `pool 531`,
  `fuori_serie_a_esclusi 63`, `indisponibili 54`, `semantica_prezzo`. Contiene 250 acquisti,
  10 squadre, listino di 594 righe.

## Osservazioni (nessuna bloccante, nessuna alta)

- **O1 — bassa. `/copilot/players` tronca a 80 righe per valore: i fuori lista non compaiono
  filtrando solo per ruolo.** Riproduzione: `GET /copilot/players?role=C&tutti=1` senza `q`
  restituisce le 80 di maggior valore, e nessun fuori lista è fra quelle; in pagina, con la
  casella «anche fuori lista ed esclusi» spuntata e il solo filtro di ruolo, il fuori lista non
  si vede. Digitando il nome (o anche una sola lettera) compare. Effetto pratico: chi cerca un
  fuori lista scorrendo il ruolo non lo trova. Nello script serve la scansione per lettera
  (`trova_fuori_lista`).
- **O2 — bassa (attesa). Un errore di console mentre il server è morto**:
  `Failed to load resource: net::ERR_CONNECTION_REFUSED`, al lotto 151, cioè fra il
  `taskkill` e il riavvio. È la richiesta di `poll()`; la pagina mostra «SERVER GIÙ» e si
  riprende da sola. Nessun `pageerror`, nessun errore JS in tutta la corsa.
- **O3 — bassa. Dopo un'uccisione brutale resta il file `ledger_w6_asta.lock` sul disco**
  (l'`atexit` non gira). La ripresa con `--resume` funziona lo stesso perché il PID nel lock è
  morto e il controllo lo ignora. Da sapere solo per la pulizia a mano.
- **O4 — bassa. La ROSA TARGET tiene target con tetto 0 in reparti già completi.** Ai lotti
  55, 90, 140, 175 il target del piano scelto dava `azione = "nessuna offerta"`, `tetto 0`
  (reparto di Io pieno): il piano continua a elencarlo, il banco dice giustamente di non
  offrire. Coerente, ma la lista dei target mostra righe non più azionabili.
- **Inciampi dello script di prova, non del Copilota** (prima corsa, `corsa1/`): due lotti su
  250 (25 e 159) persi con `ElementHandle.click: Element is not attached to the DOM` — la lista
  dei risultati si ridisegna fra `wait_for_selector` e il click. Corretto usando il selettore
  (click con ripetizione) invece dell'handle. Nella corsa buona non si è ripetuto.

## Scostamento dichiarato dal copione

Il prezzo dell'avversario è casuale, >= 60 % della mediana e <= massimo legale, **ma limitato a
1,4 x mediana**. Con il sorteggio uniforme fino al massimo legale (prima corsa di prova) i
portieri di riserva andavano a 378-471 crediti, le casse si svuotavano nel primo blocco e i
restanti 220 lotti finivano tutti a 1 credito: niente furti sopra il tetto, niente pressione sui
consigli. Il vincolo del copione (>= 60 % della mediana, <= massimo legale) resta rispettato.

## Pulizia

Server di prova fermato (`taskkill /F /T`), `ledger_w6_asta.lock` rimosso, porta 8794 libera
(`URLError` sulla `/copilot/state`). Ledger veri `data/copilot/ledger_1788290734.json` e
`ledger_1788548783.json` intatti (mtime 1/9 e 4/9). Nessun push, nessun pack rigenerato,
nessun codice del prodotto modificato.
