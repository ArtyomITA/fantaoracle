# B — revisione del ponte (10/9/2026, chiuso 18:39, PARZIALE)

## 1. Riesecuzione asta10_ponte.py — NON CONCLUSA
Avviata 18:27 (server prova 8792, ledger data/copilot/prove/ledger_w8_rev.json).
Alle 18:39 il Copilota di prova era a n_events 20 su 62 previsti: ritmo ~2 assegnazioni/min,
fine stimata oltre le 19:00, cioe' oltre il limite. Interrotta per lasciare la macchina pulita
prima dell'asta. Nessuna discrepanza osservata nei 20 eventi (squadre mappate tutte e 10:
Io, Marco, Luca, Giulia, Andrea, Sara, Paolo, Chiara, Davide, Elena).
NON confermati in questa sessione i numeri di A (43/44, ritardo 0,62 s): restano quelli di A.

## 2. Revisione di viz/ponte_fantaasta.js (225 righe, letto per intero)
Nessun difetto bloccante. Rilievi:
- due schede FantaAsta aperte: entrambe leggono lo stesso localStorage e possono mandare lo
  stesso pick due volte. Innocuo: il Copilota deduplica per richiesta_id
  (risposta {"ok": true, "duplicato": true, "n_events": invariato}) — verificato in
  verifica_f1f2.py caso F2.3. Consiglio comunque una sola scheda.
- localStorage pieno: salva() ingoia l'errore di quota (catch vuoto). Effetto: dopo un
  ricarico i rid perduti vengono rimandati (innocui per la dedup), ma un'assegnazione
  annullata in FantaAsta non verrebbe piu' annullata nel Copilota. Rischio remoto
  (PONTE_INVIATI_ ~100 byte per pick, ~30 KB su 300 pick, quota 5 MB). Non modificato.
- undo di un pick non ultimo: gia' gestito — niente undo, avviso "annullala a mano",
  l'indice viene bloccato finche' non si usa window.PONTE.sblocca(<index>).
- squadra non mappata: avviso a ogni giro, pick saltato, nessun invio sbagliato.
- id non nel pack: risposta "inesistente" -> avviso "registralo a mano nel Copilota", pick
  marcato errore e non ritentato.
- costo 0 o mancante: Math.max(1, Math.round(cost||1)) -> 1, mai 0.
- fetch fallito (prompt «Local Network Access» negato, Copilota spento): catch -> riquadro
  ERRORE in rosso, avviso, break del giro e nuovo tentativo dopo 1,5 s, senza perdere pick.
Nessuna modifica al js: viz/ponte_fantaasta.js resta identico alla versione di A
(backup comunque in scratchpad\w8\ponte_pre.js).

## 3. Bookmarklet e pagina
python scripts/ponte_bookmarklet.py rigenerato: viz/ponte.html 36400 byte,
bookmarklet 20407 caratteri, porta 8770.
Menu gia' acceso (curl 8899/launcher/status -> {"launcher": true}); NON avviato ne' fermato.
Playwright su http://127.0.0.1:8899/viz/ponte.html: titolo "Ponte FantaAsta -> Copilota",
1 link javascript: (testo "PONTE FantaAsta", href 19339 caratteri), pagina 169 parole.
Schermata: scratchpad\w8\ponte_html.png.

## 4. Impronte
- viz/copilot.html 597b3f8a... COINCIDE
- data/packs/pack_2026-27.pkl 2303dcbf... COINCIDE
- data/copilot/eleggibilita_2026-27.json 4f8b435c... COINCIDE
- scripts/f10_copilot.py 21694ea8... DIVERSO da w4 (a2e1bccf...). diff contro
  data/_backup_fable_20260910/f10_pre_pna.py (sha256 a2e1bccf..., = impronta w4): unica
  differenza, 5 righe aggiunte dopo la 898, gli header CORS
  "Access-Control-Allow-Methods: GET, POST, OPTIONS" e
  "Access-Control-Allow-Private-Network: true" piu' 3 righe di commento. Ammesso.

## 5. Prove Copilota
- pytest tests/test_copilot_asta.py -q: 12 passed, 1 skipped in 14.25s
- verifica_f1f2.py: 32/32 verificati
- verifica_f5bis.py: 23/23 verificati
- verifica_f6.py (server 8791, ledger prove/ledger_w8_rev6.json): 25/25 verificati

## 6. Macchina
Server di prova 8791 e 8792 fermati, lock rimossi, porte 8791/8792/8794 libere, nessun
processo di prova vivo. Ledger veri in data/copilot/ledger_*.json mai toccati.

## Istruzioni per stasera (verificate)
1. Menu gia' acceso su 8899; Copilota vero sulla 8770 dal menu (non toccare 8770/8899).
2. In Chrome apri http://127.0.0.1:8899/viz/ponte.html e trascina il link "PONTE FantaAsta"
   nella barra dei preferiti.
3. Apri https://fanta-asta-live.fantacalcio.it/#/main, crea/carica le 10 squadre con gli
   stessi nomi del setup del Copilota, poi clicca il preferito "PONTE FantaAsta".
4. Chrome chiede l'accesso alla rete locale: clicca «Consenti». In basso a destra compare il
   riquadro PONTE. Se dice ERRORE in rosso, ricarica la pagina e riclicca il preferito.
5. Una sola scheda FantaAsta. Il riquadro deve dire "N assegnazioni inviate" e "OK".
6. Se annulli un'assegnazione in FantaAsta: se e' l'ultima, il ponte annulla anche nel
   Copilota; se non e' l'ultima, il riquadro va in ERRORE e devi annullare a mano nel
   Copilota, poi in console (F12) window.PONTE.sblocca(<indice del pick>).
7. Se un giocatore non e' nel pack, il ponte avvisa: registralo a mano nel Copilota.
8. Comandi utili in console: window.PONTE.stato(), window.PONTE.ferma(), window.PONTE.rimappa().
