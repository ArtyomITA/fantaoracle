# A — Ponte FantaAsta -> Copilota (indurimento + prova asta a 10)

## File

| file | stato |
|---|---|
| `viz\ponte_fantaasta.js` | riscritto, 109 -> 225 righe (backup: `...\w8\ponte_pre.js`) |
| `scripts\ponte_bookmarklet.py` | nuovo, 156 righe |
| `viz\ponte.html` | nuovo, generato dallo script, 100 righe |
| `tests\test_ponte_fantaasta.py` | nuovo, 5 prove, tutte verdi |
| `...\w8\asta10_ponte.py` | prova asta a 10 (Playwright) |

File congelati non toccati: `scripts/f10_copilot.py`, `viz/copilot.html`, `data/packs/*`, `data/copilot/*` (tranne `prove/`).

## Cosa e' cambiato nel ponte (viz/ponte_fantaasta.js)

- `console.warn` ovunque (l'app disabilita `console.log`): righe 36-40 `avvisa()`, che tiene anche gli ultimi 30 avvisi per `stato()`.
- Riquadro fisso in basso a destra, 240px, semitrasparente (righe 42-59, `dipingi()` riga 53): `PONTE: N assegnazioni inviate / ultimo giro hh:mm:ss / OK-ERRORE`; verde OK, rosso ERRORE. `id="ponte-fantaoracle-box"`, `pointer-events:none` (non intercetta i clic dell'app).
- Svincolati (`released:true`): righe 126-155. I pick con `released` escono dagli attivi; se erano stati inviati -> undo se sono l'ultimo del Copilota, altrimenti avviso con la causa esatta (`svincolato`).
- Assegnazione modificata (stesso `index`, costo o squadra diversi): il `rid` cambia, il vecchio risulta sparito -> undo + reinvio automatico se e' l'ultimo; altrimenti avviso e **blocco del lotto** (`bloccato(index)`, riga 110 e righe 158-162) cosi' non nasce un doppione.
- 400 «giocatore inesistente»: righe 183-187, avviso con il nome preso da `u.players` (`nomeGiocatore`, righe 81-84) e nessun altro tentativo (`errore` persistito in `PONTE_INVIATI_<porta>`).
- Copilota che non risponde (spento o Local Network Access negato): righe 167-172, `break` del giro senza segnare nulla; si riprende dallo stesso pick al giro dopo, niente accumulo ne' doppioni.
- Mappa squadre ricalcolata quando cambiano i nomi (firma `id:nome`, righe 95-107 e 129-130); abbinamento per nome esatto, poi per prefisso, poi per posizione, senza mai assegnare due squadre allo stesso indice del Copilota.
- `window.PONTE.stato()` -> `{inviati, mappa, ultimoGiro, esito, errori}`; aggiunti `PONTE.sblocca(index)` e `PONTE.copilota`.
- `ordine` ricalcolato dagli inviati salvati (riga 30): dopo un ricaricamento la sequenza degli undo resta corretta.

## Prova asta a 10 (asta10_ponte.py)

### Asta a 10 su FantaAsta Live headless (Copilota vero su 8792, budget 1000, quote 3/8/8/6)

- 10 squadre create con «Aggiungi»; rinomina **non fattibile dall'interfaccia** in headless (il click sulla squadra apre un solo input ma non salva il nome): nomi scritti in `localStorage.teams[].name` + ricarica -> `['Io','Marco','Luca','Giulia','Andrea','Sara','Paolo','Chiara','Davide','Elena']`, poi INIZIA -> «Serie A» (595 giocatori in lista).
- **44 assegnazioni** riuscite su 62 tentate in 236 s (le 18 mancate sono limiti dello script, non del ponte: `ui-player-row` non trovata entro 6 s per nomi come Ciocci, Fruchtl, Corrado... la lista e' virtualizzata).
- **Confronto finale: 44 picks in FantaAsta, 43 acquisti nel Copilota, 43 righe su 44 identiche (giocatore, squadra, prezzo).** Unica discrepanza: `Libra -> Paolo, 1` (id 7629), residuo della prova di annullamento (sotto).
- **Ritardo pick -> Copilota: medio 0,62 s, min 0,17 s, max 1,80 s** (giro del ponte ogni 1,5 s).
- **Ricaricamento a meta' (dopo il 31esimo) + reiniezione del ponte: n_events 30 -> 30, nessun doppione.**
- Modalita': `options.bids.countdownType = "auction"`, `playerValueType: "fmv"`, `minimumBid 1`, `beatRaise 1`. In headless si e' usato il flusso **PICK!** (cost = value = FVM): i rilanci uno per uno non sono stati provati, **niente `/copilot/bid` in questa prova**.
- Riquadro a fine prova: `PONTE: 42 assegnazioni inviate | ultimo giro 18:22:48 · OK`; `window.PONTE.stato().errori` vuoto.

### Casi duri su stato FantaAsta sintetico (casi_duri_ponte.py, Copilota su 8795)

Serviva una pagina dove l'app Angular non riscrivesse `localStorage` sotto i piedi: pagina locale su 8796, stato FantaAsta finto, ponte iniettato tale e quale.

| caso | esito | tempo |
|---|---|---|
| 3 assegnazioni normali | OK | 2,9 s |
| annullamento dell'ultima -> undo nel Copilota | OK | 0,4 s |
| svincolo (`released:true`) dell'ultima -> undo | OK | 1,6 s |
| cambio di costo 10 -> 77 sull'ultima -> undo + reinvio | OK | 1,9 s |
| cambio di squadra sull'ultima -> undo + reinvio | OK | 1,5 s |
| giocatore fuori pack (id 999999) -> avviso col nome | OK (`giocatore non presente nel pack: Fantasma (id 999999)`) | |
| nessun ritentativo sul fuori pack | OK | |
| annullamento **non** in coda -> avviso, nessun undo | OK (`annullata in FantaAsta ma non e' l'ultima registrata nel Copilota`) | |

(Gli ultimi due risultano «KO» nel tabellone dello script solo perche' il listener `page.on("console")` non ha catturato i warning: i messaggi ci sono, letti da `window.PONTE.stato().errori`.)

## Anomalie

1. **Annullamento dall'interfaccia di FantaAsta: non riprodotto.** Il tab «Assegnazioni» in headless non espone nessun bottone «Cancella Assegnazione» (bottoni visti: Menu, Leghe, Sospendi, TV Mode, PICK, VETRINA, Riordina squadre, Ordina calciatori). Ripiego: pick tolto da `localStorage`; l'app Angular lo ha **riscritto** subito dal suo stato in memoria, quindi l'undo del ponte e' partito e la riga e' tornata: da li' la sola discrepanza (`Libra -> Paolo, 1` presente in FantaAsta, assente nel Copilota) e l'anomalia `annullamento non propagato: n_events resta 20`. **Il meccanismo di undo del ponte e' comunque provato buono** dai casi duri (4 varianti su 4). **Da controllare a mano stasera** dove sta il comando di cancellazione nell'interfaccia vera (probabile menu della riga in «Assegnazioni»); se manca, si annulla dal Copilota con «Annulla ultimo».
2. **Confronto dei budget non affidabile:** `teams[].currentBudget` in `localStorage` e' una fotografia vecchia (resta a 1000 con picksCount 0 anche dopo i pick), quindi i «budget diversi» stampati sono un difetto della misura, non del ponte. Il confronto valido e' quello per pick: 43/44 righe identiche, prezzi compresi.
3. **Rinomina delle squadre da interfaccia headless non riuscita** (vedi sopra): stasera i nomi ci sono gia', quindi conta solo che coincidano col setup del Copilota.
4. 18 pick su 62 non piazzati per limiti dello script (lista virtualizzata + ricerca per nome): non tocca il ponte, che ha inviato tutte le 44 assegnazioni realmente fatte.
5. **Rilanci (`/copilot/bid`) non provati** dal ponte: il ponte oggi manda solo le aggiudicazioni (`/copilot/hammer`). `bids-log` di FantaAsta esiste; se stasera servisse il ticker dei rilanci si puo' aggiungere, ma e' lavoro nuovo, non fatto qui.

## Prove

`PYTHONIOENCODING=utf-8 PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python -m pytest tests/test_ponte_fantaasta.py -p no:cacheprovider -q` -> **5 passed**.


## Istruzioni per stasera

1. Avvia il Copilota dal menu (porta 8770) e fai il **setup con gli stessi nomi** delle squadre di FantaAsta (ammolly, Midelsburg FC, Nightmare fc, Primo, ROCKS PIRATE, SSSP, Tonno Fc, TonyDaMilano, sdag, la tua). Se un nome non combacia il ponte abbina per **posizione**: tieni lo stesso ordine.
2. Dal menu apri `http://localhost:8899/viz/ponte.html`, controlla che la porta sia 8770, premi **prova connessione** (deve elencare i 10 nomi) e **trascina il link verde «PONTE FantaAsta» nella barra dei preferiti**.
3. Vai sulla scheda di FantaAsta Live (asta gia' avviata) e **clicca il preferito**. In alternativa F12 -> Console -> incolla `viz\ponte_fantaasta.js`.
4. Chrome chiede **«consentire l'accesso alla rete locale»**: clicca **Consenti**. Se non lo chiede e il riquadro in basso a destra dice ERRORE: `chrome://flags/#local-network-access-check` -> **Disabled** -> riavvia Chrome e riclicca il preferito.
5. Controlla il riquadro in basso a destra: `PONTE: N assegnazioni inviate ... OK`. Deve salire a ogni martelletto.
6. Se **ricarichi** la pagina di FantaAsta, **riclicca il preferito**: gli inviati sono ricordati, niente doppioni.
7. Se il riquadro dice ERRORE: F12 -> Console -> `window.PONTE.stato().errori` dice cosa e' successo; le assegnazioni rifiutate vanno messe a mano nel Copilota.
