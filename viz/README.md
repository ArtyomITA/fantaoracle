# FantaOracle — Teatro dell'asta (`viz/`)

Webapp autosufficienti (vanilla JS + CSS inline, zero dipendenze/CDN, tema "notturno da
stadio": Catppuccin Mocha + verde campo + oro martelletto):

- **`index.html`** — il menu, in ordine di utilità: **1) Asta vera (Copilota)**, 2) Allenati
  contro i bot (Sedia), 3) Replay, 4) Aggiorna mercato. Una riga di spiegazione sotto ogni
  titolo. Se la pagina gira dentro **FantaOracle App** (`python scripts/fantaoracle_app.py`,
  o `FantaOracle.bat`) i bottoni AVVIA/RIPRENDI/ferma lanciano davvero i server; su un server
  statico semplice resta il piano B col comando da copiare.
- **`copilot.html`** — il **Copilota dell'asta VERA** coi tuoi amici (nessun bot: tu registri
  i martelletti, l'oracolo consiglia). Vedi sotto.
- **`replay.html`** — il teatro con **tre anime**: il replay di un'asta simulata, la
  **Modalità Sedia** (asta live con te al tavolo contro 9 bot) e il **viewer della
  stagione** post-asta. La scena è la stessa: palco col giocatore chiamato sotto al
  riflettore, prezzo che pulsa oro, splash a tutto palco al cambio ruolo, ticker dei
  rilanci con i "pensieri" dei bot, tavolo delle 10 squadre con budget a gradiente e slot
  rosa (click su una riga → popover "rosa finora" per ruolo con stemmi, crediti pagati,
  subtotali e residuo, aggiornato live; chiusura con ✕/Esc/click fuori), sparkline
  dell'inflazione e riepilogo finale con le rose complete. Bottone ⌂ per tornare al menu.

## Il menu (`index.html`) dentro FantaOracle App

```
python scripts/fantaoracle_app.py --porta 8899      # oppure doppio click su FantaOracle.bat
# → http://localhost:8899/viz/index.html
```

- **Card 1 · 🏟️ ASTA VERA — Copilota** (grande, tutta la riga): probe di
  `GET /copilot/state` sulla porta scelta (default 8770, riprovato ogni 3s).
  - nessun copilota acceso → select stagione (default: la più recente tra `seasons` di
    `/launcher/status`) + **🏟️ AVVIA l'asta vera** (`POST /launcher/start
    {mode:"copilot"}`, poi salto diretto in `copilot.html`); se `/launcher/interrotte` ha
    ledger del copilota compare **⏪ RIPRENDI l'ultima asta vera** con nomi, acquisti e
    data (`{mode:"copilot", resume:"latest"}`).
  - copilota acceso → badge "tavolo attivo — N al tavolo, M acquisti", **ENTRA**,
    "🆕 NUOVA ASTA VERA" con conferma inline (riclicca entro 3s) e "⏹ ferma" per i processi
    avviati da qui (anche lui con conferma).
- **Card 2 · 🪑 Allenati — Sedia**: come prima (stagione, "senza bot B", AVVIA/NUOVA
  ASTA/ferma) più **⏪ RIPRENDI asta interrotta** quando `/launcher/interrotte` ha log
  Sedia senza stagione salvata accanto (`{mode:"sedia", resume:"latest"}`).
- **Card 3 · ▶ Replay**: lista dei log raggiungibili + drag&drop di un `.jsonl`.
- **Card 4 · 🔄 Aggiorna mercato**: **AGGIORNA ORA** → `POST /launcher/refresh` (lancia
  `scripts/f11_refresh_all.py`, minuti); polling ogni 3s di `GET /launcher/refresh_status`
  → badge (in corso / dati aggiornati / errori / mai eseguito), "ultimo aggiornamento:
  gg/mm hh:mm · esito", ultime 12 righe di log in un box monospace.
- Le card si ri-renderizzano solo quando cambia davvero qualcosa (niente select che si
  chiudono da sole mentre scegli).

## Copilota dell'asta vera (`copilot.html?live=http://localhost:8770`)

Server: `python scripts/f10_copilot.py 2025-26 --porta 8770` (o dal menu). Tutto lo stato
vive sul server, che scrive ogni evento in `data/copilot/ledger_<ts>.json`: chiudi, riapri,
ricarica la pagina e riprendi esattamente da lì (badge **salvato ✓ ledger_….json** in
header, lampeggia a ogni acquisto). Polling `/copilot/state` ogni 2s; server giù → banner
rosso non bloccante e pill "SERVER GIÙ", riprova da solo.

- **Setup** (finché `names` è vuoto): numero partecipanti (2–14, stepper), un campo nome
  per riga con il radio **IO** che marca la tua squadra (riga evidenziata oro), budget a
  testa, **CONFERMA** (`POST /copilot/setup`). Nomi/budget ricordati in localStorage per la
  prossima volta. "⚙ tavolo" in header riapre il setup solo prima del primo acquisto.
- **SINISTRA · AL BANCO**: ricerca (nome, debounce 200ms) + pill ruolo P/D/C/A + select
  squadra (stemmi CLUB_STYLE come nel teatro); righe con ruolo, stemma, q50, valore; il
  primo risultato è bordato (Invio lo seleziona). Selezionato → card: nome, stemma grande,
  chip "★ titolare di piano / nel piano · panchina / fuori piano", q10-q50-q90 + valore,
  forchetta q10–q90 con tacca bianca al prezzo attuale, motivi mercato (se presenti), slot
  liberi, tua offerta massima legale, calore, max consigliato, affare sotto.
  **Prezzo attuale** (campo grande, −1/+1/+5/+10) e sotto il **CONSIGLIO** grande e colorato
  ricalcolato a ogni cambio (debounce 200ms su `/copilot/advice`):
  - 🟢 **RILANCIA fino a X** (nel piano, sotto il max consigliato; mostra il costo-ombra);
  - 🟡 **BARGAIN sotto X** (fuori piano ma conviene);
  - 🔴 **LASCIALO** (fuori piano / oltre il max) e **NON PUOI RILANCIARE** (oltre l'offerta
    massima legale);
  - grigio **MAX 1–5 CREDITI** / **REPARTO PIENO**.
  **AGGIUDICATO A…**: griglia di bottoni coi partecipanti (tu in oro; budget e max
  offerta sotto il nome; disabilitati se il reparto è pieno) → `POST /copilot/hammer` al
  prezzo attuale, flash verde "🔨 VENDUTO", riga del tavolo che lampeggia, banco che si
  svuota e focus di nuovo sulla ricerca. Errori del server (reparto pieno, oltre il max
  legale) in toast rosso. **↶ ANNULLA ultimo** sempre visibile sotto il banco (mostra
  giocatore → squadra · prezzo): primo click arma, secondo entro 3s conferma
  (`POST /copilot/undo`).
- **CENTRO · IL MIO PIANO**: crediti residui, slot da riempire per ruolo, costo atteso del
  piano, calore mercato; barra costo atteso vs budget (rossa se sfora, con "+N oltre
  budget"); **CHI CHIAMO?** con bottoni P/D/C/A → `/copilot/nominate`: card 🎣 **ESCA**
  (peach) o 🧱 **RIEMPITIVO** (teal) con giocatore, apertura, motivo e "→ AL BANCO";
  **ROSA TARGET** per ruolo da `/copilot/plan` (★ titolare, prezzo atteso, ≤ max
  consigliato), si ricalcola a ogni acquisto; click su una riga → al banco.
- **DESTRA · IL TAVOLO**: tutti i partecipanti con budget a gradiente, offerta massima
  legale, mini griglia slot P/D/C/A (tooltip col giocatore); tu evidenziato "TU"; click →
  popover rosa per ruolo (stemmi, q50, prezzo pagato, subtotali, speso/max/residuo),
  aggiornato live. **ULTIMI ACQUISTI**: ticker degli ultimi 15 martelletti (dal campo
  `last_events` di `/copilot/state`).
- **Scorciatoie**: `/` ricerca · `Invio` primo risultato · `+`/`−` prezzo ±1 (anche nel
  campo prezzo) · `U` annulla ultimo (due volte) · `Esc` chiude popover / svuota il banco.

## Modalità replay (`replay.html?log=…`)

- **Doppio click** su `replay.html` (funziona da `file://`) e poi **drag&drop** del log
  `.jsonl` sulla pagina, oppure bottone "Scegli file…".
- **Da server statico** (consigliato, abilita anche la querystring):

  ```
  cd <cartella-del-progetto>
  python -m http.server 8899
  # menu:   http://localhost:8899/viz/index.html
  # teatro: http://localhost:8899/viz/replay.html?log=../data/sample_logs/smoke_seed0.jsonl
  ```

  - `?log=percorso` — fetch relativo del log (da `file://` il fetch è bloccato dal browser:
    usare drag&drop).
  - `&at=N` — si posiziona all'evento N in pausa (deep-link / debug). Senza `at` il replay
    parte da solo a 4x.

Controlli: play/pausa (spazio), step singolo avanti/indietro (←/→), velocità 1x/4x/16x/64x,
scrubber con tacche ai cambi di ruolo, "Fine ⇥" (End) per il riepilogo, Home per ricominciare.

## Modalità Sedia — asta live (`replay.html?live=…`)

Tu al tavolo, 9 bot intorno. Serve il server d'asta (un processo = un'asta; riavviarlo
per ripartire):

```
cd <cartella-del-progetto>
python scripts/f6_live_auction.py 2025-26 --porta 8766
# → http://localhost:8899/viz/replay.html?live=http://localhost:8766
#   (o dal menu: viz/index.html → card Sedia, porta 8766)
```

- La pagina fa polling di `/state` + `/events` ogni ~300ms e alimenta la stessa scena del
  replay in tempo reale (scrubber/velocità nascosti, badge **LIVE** in header, squadra
  umana "TU" evidenziata al tavolo). Server giù → banner d'errore non bloccante, riprova
  da solo; a riconnessione recupera l'arretrato in blocco.
- Quando tocca a te compare la **barra azioni** ancorata in basso:
  - **rilancio**: prezzo corrente, chi comanda, bottoni `+1` / `+5` / importo custom /
    `NON LO VOGLIO` / `PASSO` / `AUTO` (il suggeritore decide), disabilitati oltre
    l'offerta massima; pannello consiglio richiudibile (mediana q50, tetto q90, valore,
    max consigliato, heat mercato, giudizio). Scorciatoie: `R` = +1, `P` = passo.
    `NON LO VOGLIO` = full pass: da lì al martelletto di QUEL giocatore la UI passa da
    sola (mini-pill "passo automatico su … ✕" in basso a destra per annullare).
  - **chiamata**: ruolo del blocco, ricerca live sui disponibili (debounce 250ms),
    filtro per squadra (da `GET /squadre`, con fallback dai risultati se il server è
    vecchio), ordinamento valore / mediana lega / media mercato (media aste reali —
    nascosto se il server non la espone), righe con stemma+sigla, click per
    selezionare, prezzo d'apertura (default 1) e `CHIAMA`, oppure `AUTO`.
- Stemmi club stilizzati (cerchio con sigla sui colori sociali, mappa hardcoded, zero
  immagini esterne) sul palco accanto al nome, nel selettore di chiamata e nelle
  formazioni del viewer stagione; cache `player_id→squadra` progressiva (prefetch da
  `/squadre` + localStorage) — per i giocatori venduti prima di un reload lo stemma può
  mancare (il log eventi non porta il club).

## Viewer stagione (post-asta, solo live)

A martelletti finiti il server simula il campionato (38 giornate coi fantavoti reali) e
il riepilogo mostra "**Vai alla stagione →**" (con auto-switch dopo qualche secondo):

- classifica finale (punti, V-N-P, gol fatti/subiti, fantapunti) con podio colorato e
  squadra umana evidenziata + sparkline SVG della tua posizione nelle 38 giornate;
- navigazione giornate 1–38 (frecce, salto diretto, ←/→ da tastiera): 5 card scontro con
  gol convertiti e fantapunti; click su una card → **due mini-campi SVG affiancati e
  specchiati** coi giocatori disposti secondo il modulo: gettone con iniziali sui colori
  del club, nome corto e fantavoto in badge a fasce (rosso &lt;6, grigio 6–6.5, verde
  6.5–8, oro &gt;8), subentrati con anello ↷, assenti come gettoni spenti a bordo campo;
  modulo, bonus modificatore difesa e cambi nel titolo del pannello;
- "⟲ Riepilogo asta" per tornare alle rose.

## Formato log (JSONL, un evento per riga)

| kind | campi principali |
|---|---|
| `auction_start` | `seating` (ordine tavolo), `bots` (`bots[i]` = bot di `seating[i]`), `budget`, `quotas` |
| `phase_start` | `role` (P→D→C→A) |
| `nomination` | `team`, `bot`, `player_id`, `player`, `role`, `opening`, `thought` |
| `bid` | `team`, `bot`, `player_id`, `amount`, `thought` |
| `hammer` | `team`, `bot`, `player_id`, `player`, `role`, `price`, `budget_left` |
| `auction_end` | `teams[]` con `budget_left` e `roster` per ruolo `[[player_id, prezzo], …]` |

Gli eventi vengono riordinati per `seq` al caricamento. Lo scrubber **ricostruisce sempre lo
stato da zero** (`buildState`, ~0,15 ms per 2500 eventi): impossibile corrompere lo stato
andando avanti/indietro.

## Dove agganciare le cose

- **Copilota** — `copilot.html`: `poll()`/`onState()` (polling stato + rilevamento cambi
  via `n_events`), `adviceView(a)` (mappa il testo `consiglio` del server → colore/titolo
  del box: se cambia la frase lato server, si aggiorna lì), `renderLot()`/`renderAdvice()`,
  `hammer()`/`undo()` (arm-confirm), `renderPlan()`, `renderTeams()`/`updateTeamPopover()`,
  `renderTicker()` (usa `last_events` di `/copilot/state`, aggiunto in `f10_copilot.py`).
- **Menu / launcher** — `index.html`: banner `LAUNCHER` (probe una tantum di
  `/launcher/status` + `/launcher/interrotte`), sezioni `1 · ASTA VERA` (`probeCopilot`,
  `renderCopilot`, `cpStart`), `2 · SEDIA` (`probeLive`, `renderSedia`, `doStart(port,
  resume)`), `4 · AGGIORNA MERCATO` (`pollRefresh`, `renderRefresh`).
- **Prezzo di riferimento per i badge AFFARE/STRAPAGATO** — funzione `referencePrice(lot)`
  in `replay.html` (cerca il banner `PREZZO DI RIFERIMENTO`). Oggi placeholder
  `apertura × 2.5`; quando avremo il listino vero basta sostituire il corpo della funzione
  (es. lookup `{player_id: prezzo}`), `dealBadge()` resta invariata.
- **Modalità Sedia (live)** — banner `SORGENTE EVENTI` / `MODALITÀ SEDIA` in `replay.html`:
  `LiveEventSource` (stessa interfaccia di `ArrayEventSource` + `send()` → `POST /action`),
  `startLive()`/`livePoll()`/`liveDrain()` per polling e drenaggio eventi,
  `updateHumanBar()`/`buildHumanBar()` per la barra azioni. Il turno umano NON è un evento
  del log: arriva da `GET /state` (campo `awaiting`). Server: `scripts/f6_live_auction.py`.
- **Viewer stagione** — banner `VIEWER STAGIONE`: `fetchSeason()` (`GET /season`),
  `openSeason()`/`buildSeasonSkeleton()`/`renderSeasonDay()`; ordinamento classifica in
  `seasonOrder()` (punti → fantapunti → differenza reti).
- **Metrica sparkline** — media mobile (finestra 12 aggiudicazioni) di
  `prezzo pagato / apertura`; documentata nel tooltip ⓘ, costante `INFL_WINDOW`.

## Note

- Desktop-first, larghezza minima 1280 px.
- In un tab in background i browser rallentano i timer: il replay prosegue ma a ~1 evento/s.
- Nel menu, i probe verso porte spente (es. Sedia su :8765 quando non c'è) producono in
  console il normale `net::ERR_CONNECTION_REFUSED` del browser: non è un errore della pagina.
