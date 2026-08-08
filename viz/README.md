# FantaOracle — Teatro dell'asta (`viz/`)

Webapp autosufficienti (vanilla JS + CSS inline, zero dipendenze/CDN, tema "notturno da
stadio": Catppuccin Mocha + verde campo + oro martelletto):

- **`index.html`** — il menu: wordmark 🔮, probe del server live (badge "tavolo attivo",
  porta custom, re-probe ogni 3s), lista dei log raggiungibili, drag&drop di un log che
  si apre direttamente nel teatro, CTA stagione quando l'asta risulta conclusa. Se la
  pagina gira dentro **FantaOracle App** (`python scripts/fantaoracle_app.py`) la card
  Sedia mostra il flusso a bottoni: stagione (2025-26/2024-25), toggle "senza bot B",
  **🚀 AVVIA NUOVA ASTA** (spinner → tavolo attivo → ENTRA), "🔁 NUOVA ASTA" con
  conferma inline quando un tavolo è già acceso e "⏹ ferma" per le aste avviate da qui;
  su un server statico semplice resta il piano B col comando + COPIA.
- **`replay.html`** — il teatro con **tre anime**: il replay di un'asta simulata, la
  **Modalità Sedia** (asta live con te al tavolo contro 9 bot) e il **viewer della
  stagione** post-asta. La scena è la stessa: palco col giocatore chiamato sotto al
  riflettore, prezzo che pulsa oro, splash a tutto palco al cambio ruolo, ticker dei
  rilanci con i "pensieri" dei bot, tavolo delle 10 squadre con budget a gradiente e slot
  rosa (click su una riga → popover "rosa finora" per ruolo con stemmi, crediti pagati,
  subtotali e residuo, aggiornato live; chiusura con ✕/Esc/click fuori), sparkline
  dell'inflazione e riepilogo finale con le rose complete. Bottone ⌂ per tornare al menu.

## Modalità replay (`?log=…`)

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

## Modalità Sedia — asta live (`?live=…`)

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
