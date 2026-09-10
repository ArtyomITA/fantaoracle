# Caccia ai difetti — lente PERSISTENZA, RIPRESA, CONCORRENZA

Copilota FantaOracle, `fantabot`, sola lettura sul progetto.
Porta di prova usata: 8793. Ledger di prova: `data/copilot/prove/ledger_w1_8793_*.json`.
Data: 10/09/2026. Python 3.12, Windows 11. Nessun processo lasciato vivo (verificato
con `Get-CimInstance Win32_Process -Filter "Name='python.exe'"` a fine lavoro).

Script di riproduzione (tutti autonomi, avviano e fermano da soli il server che
serve loro; escono 1 se il difetto c'è, 0 se non c'è):

```
C:\Users\ADMINI~1\AppData\Local\Temp\claude\E--claudecode-pesante\5ff20539-b495-4ac4-bed4-79eabbf8a8b7\scratchpad\w1\repro_persistenza_1.py … _7.py
```

Esito dell'esecuzione in sequenza (registrata in `esiti_repro.txt`): 7 su 7 escono 1.

| # | difetto | tipo | gravità | exit |
|---|---------|------|---------|------|
| 1 | ripresa/avvio su porta già occupata: il Copilota "ripreso" è sordo | riprodotto | alta | 1 |
| 2 | due Copiloti sullo stesso ledger: l'ultimo che salva cancella gli acquisti dell'altro | riprodotto | alta | 1 |
| 3 | `/copilot/setup` dopo gli acquisti: budget negativo, "io" spostato, asta bloccata | riprodotto | alta | 1 |
| 4 | un lock solo per tutto: il martelletto aspetta il MILP dei piani | riprodotto | media | 1 |
| 5 | "RIPRENDI l'ultima" sceglie solo per mtime: riapre la sessione vuota | riprodotto | media | 1 |
| 6 | Copilota orfano ingovernabile: `⏹ ferma` non lo ferma più | riprodotto | media | 1 |
| 7 | ripresa dalla copia `.buono` senza dirlo: sparisce un acquisto | riprodotto | bassa | 1 |

---

## 1. Ripresa/avvio su porta già occupata: il Copilota "ripreso" è sordo

`scripts/fantaoracle_app.py:164`

```python
if old is None and probe_auction(porta, 0.5) is not None:
```

`probe_auction` (righe 60-66) usa `path="/state"` di default. Il Copilota non ha
`/state` (ha `/copilot/state`) e risponde **404**, quindi `urlopen` solleva
`HTTPError`, il `except Exception` lo inghiotte, la funzione torna `None` e la
guardia "porta già occupata" **non scatta mai contro un Copilota**.

Verificato a mano:

```
$ curl -s -o /dev/null -w "%{http_code}\n" http://127.0.0.1:8793/state
404
```

Poi `http.server.HTTPServer.allow_reuse_address = 1`: su Windows un **secondo
bind sulla stessa porta riesce**, e tutte le connessioni continuano ad andare al
primo processo. Provato in isolamento (`bind2.py`):

```
bind1 ok, allow_reuse_address = 1
bind2 OK -> due server sulla stessa porta
risposte: {'UNO': 20}          # 20 richieste su 20 al PRIMO server
```

Infine il ciclo d'attesa di `/launcher/start` (righe 199-208) interroga
`/copilot/state`, riceve risposta **dal processo vecchio** e conclude
`{"ok": true, "resumed": true}` — l'ordine dei controlli mette la sonda prima di
`proc.poll()`, quindi anche un figlio morto passerebbe per avviato.

Catena completa riprodotta (`repro_persistenza_1.py`):

```
probe_auction(8793, '/state')                 = None
guardia vede la porta occupata               = False
secondo processo ancora vivo sulla porta     = True
l'app direbbe ok/avviata                     = True
/copilot/state serve la sessione             = ['VECCHIA', 'x1', 'x2']
ledger VECCHIA: 1 -> 2 acquisti
ledger RIPRESA: 0 -> 0 acquisti
```

Il martelletto registrato dopo la "ripresa riuscita" finisce nel ledger della
sessione vecchia; il ledger che si voleva riprendere resta a zero.

In asta: se l'app viene riavviata (o il Copilota è stato acceso a mano),
`CHILDREN` è vuoto, `🆕 NUOVA ASTA VERA` non riesce a chiudere il processo vecchio,
ne aggiunge uno sordo e manda il browser sull'asta di prima dicendo che è nuova.
Con `⏹ ferma` si uccide poi il processo sordo, lasciando vivo quello vero.

**Fix proposto** (una riga più una): in `fantaoracle_app.py` la sonda di
occupazione deve usare il percorso della modalità —
`probe_path = "/copilot/state" if mode == "copilot" else "/state"` calcolato
*prima* della riga 164 e passato a `probe_auction(porta, 0.5, probe_path)`; e nel
ciclo 199-208 controllare `proc.poll()` **prima** della sonda, così una porta
occupata da un estraneo non passa per avvio riuscito.
**Rischio del fix**: se un Copilota nostro resta appeso, l'avvio ora viene
rifiutato invece di sembrare riuscito — serve dire all'utente di chiudere quel
processo (comportamento nuovo, ma esplicito).

---

## 2. Due Copiloti sullo stesso ledger: l'ultimo che salva cancella l'altro

`scripts/f10_copilot.py:136-164` (`save`) serializza tutto lo `STATE` in memoria e
sostituisce il file. Non rilegge il file, non confronta una versione, non prende
nessun lock. `carica_ledger` (182-199) apre qualunque ledger, anche uno già aperto
da un altro processo.

Riprodotto con due istanze indipendenti del modulo (STATE e LEDGER_PATH separati,
come due processi) sullo stesso file — `repro_persistenza_2.py`:

```
seconda ripresa rifiutata          = False
ledger dopo il salvataggio di A    = [5, 11]
ledger dopo il salvataggio di B    = [5, 30]
acquisto della sessione A perso    = True
copia .buono.json                  = [5, 11]
```

Come ci si arriva davvero: `resume: "latest"` sceglie il ledger con l'mtime più
recente (difetto 5), che è proprio quello che una sessione **ancora viva** tocca a
ogni martelletto. Basta aprire una seconda finestra su un'altra porta per avere
due processi che si sovrascrivono a vicenda: gli acquisti registrati sull'uno
spariscono al primo salvataggio dell'altro.

**Fix proposto**: all'apertura del ledger scrivere accanto un `<ledger>.lock` con
pid e ora (`open(..., "x")`), rifiutare l'avvio se esiste ed è di un processo
vivo, cancellarlo alla chiusura; in alternativa, minimo indispensabile, tenere in
`STATE` un contatore `revisione` e in `save()` rileggere il file e rifiutare la
scrittura se la revisione su disco è più alta di quella in memoria.
**Rischio del fix**: un lock rimasto dopo un crash blocca la ripresa legittima —
serve la via d'uscita ("il lock è di un processo che non esiste più: procedo").

---

## 3. `/copilot/setup` dopo gli acquisti: budget negativo e "io" spostato

`scripts/f10_copilot.py:232-268` (`stato_valido`) controlla, degli acquisti già
registrati, solo due cose: che l'indice di squadra esista ancora (righe 256-261) e
che la quota del ruolo non sia zero (262-266). L'unico controllo sul budget è
`sum(quote.values()) > budget` (riga 251), cioè 25 > budget: non guarda quanto è
già stato speso. E `my_index` può cambiare liberamente.

Riprodotto (`repro_persistenza_4.py`), 20 acquisti a 20 crediti già registrati:

```
esito setup(budget=30, my_index=4)  = {'ok': True, 'squadre': 10, 'io': 4}
budget residui negativi             = [-10, -10, -10, -10, -10, -10, -10, -10, -10, -10]
max_bid negativi                    = [-32, ...]
ledger su disco: budget=30 my_index=4
martelletto successivo              = {'ok': False, 'err': 's0: 1 supera il massimo legale -32 (restano 23 slot)'}
```

Da quel momento l'asta è ferma: ogni martelletto viene rifiutato, e la UI mostra
`max -32` accanto a ogni squadra. Lo stato sbagliato è già su disco (`save()`,
riga 695), quindi resta anche dopo una ripresa. La rosa che il Copilota chiama
"la mia" è diventata quella di un altro partecipante, e tutti i consigli
(`view_for_me`) ne seguono.

Raggiungibilità: `viz/copilot.html` nasconde il pulsante setup quando
`n_events > 0`, ma la decisione arriva dal polling (fino a 2 s di ritardo) e da una
scheda aperta prima del primo acquisto; l'endpoint accetta comunque. Anche il caso
"riscrivo i nomi per correggere un refuso" è pericoloso: i nomi vengono
riassegnati per posizione, quindi un ordine diverso sposta le rose già comprate
sulle persone sbagliate senza un errore.

**Fix proposto**: in `stato_valido`, dopo aver ricostruito le squadre con gli
eventi, rifiutare se una qualsiasi ha `budget - speso < slot_rimasti` — e
rifiutare il cambio di `my_index` o dell'ordine dei nomi quando `events` non è
vuoto (messaggio: "ci sono già acquisti: apri una sessione nuova").
**Rischio del fix**: si perde la possibilità di correggere un refuso nei nomi a
metà asta; conviene permettere la sola rinomina posizione per posizione (stessa
lunghezza, stesso indice) e vietare il resto.

---

## 4. Un lock solo per tutto: il martelletto aspetta il MILP dei piani

`scripts/f10_copilot.py:546` e `:678`: `do_GET` e `do_POST` avvolgono **l'intero
corpo** (calcolo *e* scrittura sul socket) in `with LOCK`, un unico lock globale.
Il server è `ThreadingHTTPServer`, quindi i thread ci sono ma sono serializzati.
`/copilot/piani` chiama il MILP: `src/fantabot/piani.py` ha
`SECONDI_MASSIMI = 20.0` e ogni `_risolvi` ha `time_limit=5`.

Misurato (`repro_persistenza_3.py`, tavolo a 10 squadre, 40 acquisti):

```
/copilot/piani?quanti=8        = 1.40 s (tiene il LOCK)
martelletto a server tranquillo= 0.255 s
GET /copilot/state in coda     = 1.50 s
martelletto in coda            = 1.50 s  esito=True
```

Misure indipendenti dello stesso endpoint a stati diversi: 2.05 s a 0 acquisti,
2.53 s a 60 acquisti, 1.24 s a 200 acquisti. `/copilot/piano_prezzo` risolve **due**
MILP (`piani.py:236-237`), quindi vale il doppio del caso peggiore.

Due conseguenze in asta:

1. si clicca sulla squadra che si è aggiudicata il giocatore e non succede niente
   per uno-tre secondi (fino a 25 s nel caso limite consentito dai due tetti di
   tempo);
2. il polling della pagina (`viz/copilot.html:727`, `AbortController` a 2500 ms)
   va in timeout e accende il banner **"SERVER GIÙ"** mentre il server sta
   benissimo — e l'utente non sa se il martelletto è passato.

**Fix proposto**: togliere il lavoro pesante da sotto il lock — in
`piani_alternativi`/`piano_prezzo` costruire il `Contesto` sotto `LOCK`, poi
rilasciarlo e risolvere il MILP fuori, riprendendolo solo per leggere/scrivere
`PIANI_CACHE` (la chiave `ctx.chiave()` già serve a scartare un risultato calcolato
su uno stato superato). In subordine, abbassare `time_limit`/`SECONDI_MASSIMI` per
il percorso interattivo.
**Rischio del fix**: un piano calcolato su uno stato vecchio non deve tornare come
attuale — va scartato confrontando `ctx.chiave()` prima di metterlo in cache, non
solo dopo.

---

## 5. "RIPRENDI l'ultima asta vera" sceglie solo per data di modifica

`scripts/fantaoracle_app.py:170-175`

```python
ledgers = sorted(sessioni_copilota(), key=lambda p: p.stat().st_mtime, reverse=True)
resume_path = ledgers[0]
```

Nessun controllo sul contenuto. Riprodotto in una cartella finta
(`repro_persistenza_5.py`, non tocca il progetto):

```
candidati (piu' recente per primo) = ['ledger_1788600000.json', 'ledger_1788548783.json']
acquisti per file                  = {'ledger_1788600000.json': 0, 'ledger_1788548783.json': 40}
scelto da resume='latest'          = ledger_1788600000.json (0 acquisti)
```

Basta aver premuto `🏟️ AVVIA l'asta vera` invece di `⏪ RIPRENDI` e aver scritto i
nomi (il primo `save()` crea il file) perché un ledger vuoto diventi il più
recente. C'è anche uno scarto fra quello che il menu mostra e quello che l'app
apre: la scheda di anteprima viene da `/launcher/interrotte` (righe 112-120,
calcolata al giro di polling precedente) mentre `/launcher/start` **ricalcola** la
lista al momento dell'avvio; se nel frattempo un'altra sessione ha toccato il suo
ledger, si riprende un file diverso da quello mostrato — ed è la via naturale al
difetto 2.

**Fix proposto**: passare dal menu il **percorso esplicito** che è stato mostrato
(`resume: cpResume.file` invece di `"latest"`), e in `/launcher/start` scartare i
ledger con `events` vuoto quando esiste un candidato con acquisti.
**Rischio del fix**: se il file mostrato è stato spostato o cancellato nel
frattempo, l'avvio fallisce con "log non trovato" invece di ripiegare da solo —
va detto chiaramente nel messaggio.

---

## 6. Copilota orfano ingovernabile

`scripts/fantaoracle_app.py`: `CHILDREN` è un dict in RAM (riga 49); il figlio
nasce con `DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP` (righe 188-193) e
sopravvive alla morte dell'app; `/launcher/stop` (227-238) cerca il processo
**solo** in `CHILDREN`; il `finally` di riga 251 termina solo i figli conosciuti, e
non viene eseguito affatto se l'app viene uccisa. Il pulsante `⏹ ferma` del menu
compare solo per i figli nostri (`viz/index.html:572`, `ourChildAlive`).

Riprodotto (`repro_persistenza_6.py`): Copilota vivo sulla porta, app appena
ricaricata:

```
CHILDREN dopo il riavvio dell'app    = {}
risposta di /launcher/stop           = {'ok': False, 'err': 'nessuna asta nostra su quella porta'}
pulsante di stop mostrato dal menu   = False
Copilota ancora in ascolto su 8793  = True
```

Da lì in poi non c'è nessun modo, dal menu, di fermare quel processo; e siccome
neanche la guardia "porta occupata" lo vede (difetto 1), ogni avvio successivo
aggiunge un processo sordo sulla stessa porta.

**Fix proposto**: scrivere accanto a ogni figlio un file
`data/live_logs/child_<porta>.json` con pid, modalità e ledger, rileggerlo
all'avvio dell'app per ripopolare `CHILDREN`, e in `/launcher/stop` accettare anche
un pid ritrovato lì (verificando che sia davvero un `f10_copilot.py`).
**Rischio del fix**: un pid riciclato dal sistema operativo porterebbe a uccidere
un processo innocente — va controllata la riga di comando prima di terminare.

---

## 7. Ripresa dalla copia `.buono` senza dirlo: sparisce un acquisto

`carica_ledger` (`f10_copilot.py:182-199`) ripiega su `<ledger>.buono.json`, che per
costruzione (`save`, righe 149-158) è il contenuto **precedente** all'ultimo
salvataggio: un acquisto in meno. L'unico avviso è un `print` su stdout, che
avviando dal menu finisce in `data/live_logs/server_<porta>.log`. Né
`/copilot/state`, né `/copilot/bundle`, né `/copilot/export` hanno un campo che dica
che si sta lavorando su una copia arretrata.

Riprodotto (`repro_persistenza_7.py`), ledger principale troncato a metà scrittura
e `.buono` valido con un acquisto in meno:

```
acquisti dopo la ripresa            = 2 (erano 3)
prezzi in rosa                      = [5, 40]
campi dell'API che avvisano         = nessuno
```

Probabilità bassa — il file principale viene sostituito con `os.replace`, che su
Windows è atomico, quindi un troncamento richiede un guasto esterno — ma la
conseguenza è un'aggiudicazione mancante che nessuno segnala: budget e rosa di una
squadra risultano sbagliati per tutta la serata.

Nota collaterale sulla stessa funzione: la copia `.buono.json` viene scritta con
`write_text` (riga 154), **non** atomicamente, e viene riscritta a ogni
salvataggio; è l'unico file del meccanismo che può restare troncato per una
chiusura brusca. Non è fatale finché il principale è integro.

**Fix proposto**: in `carica_ledger` restituire anche l'informazione su quale
candidato è stato usato e conservarla in `STATE["ripreso_da_copia"]`, esponendola
in `/copilot/state` perché la pagina possa dire "attenzione: ripreso dalla copia di
sicurezza, l'ultima aggiudicazione potrebbe mancare".
**Rischio del fix**: nessuno funzionale; solo un campo in più nello stato, da
aggiungere anche al ledger salvato o da ripulire alla prima scrittura, altrimenti
l'avviso resta appiccicato per sempre.

---

## Controlli fatti che NON hanno trovato niente

- **La ripresa non cambia i consigli.** Sospetto: durante la sessione l'oracolo è
  aggiornato in modo incrementale (`ADVISOR.on_hammer`, riga 755), alla ripresa è
  ricostruito da zero (`rebuild_advisor`, riga 898); se le due strade divergessero,
  lo stesso registro darebbe tetti diversi dopo un riavvio. Verificato con
  `controllo_ripresa_tetti.py` su 32 acquisti e 20 giocatori campione:
  `campioni con consiglio diverso = 0/20`, heat 0.5 = 0.5, `costo_atteso_piano`
  373.3 = 373.3. **Nessun difetto**: la ripresa è deterministica.
- **`--resume` di un ledger senza `bids`** → `setdefault` alla riga 880, riprende
  correttamente (2 acquisti, tavolo intatto).
- **`--resume` di un ledger senza `bundle`** → registra l'impronta corrente e
  riparte.
- **`undo` dopo la ripresa** → funziona, e la ritrasmissione con lo stesso
  `richiesta_id` risponde `{"ok": true, "duplicato": true}` senza togliere un
  secondo acquisto (`undo_fatti` è dentro `STATE`, quindi sopravvive al riavvio).
- **Doppio POST simultaneo** → il lock globale serializza tutto: nessuna
  corruzione di `STATE` né del ledger. Il prezzo di quella scelta è il difetto 4.
- **Doppio clic senza `richiesta_id`** → la UI ne mette sempre uno
  (`viz/copilot.html:1315`, id + squadra + prezzo + `Date.now()` + random), quindi
  la collisione non è raggiungibile dal browser.

## Scartati (visti, non riportati come rilievi)

- `richiesta_id` riusato per un **giocatore diverso** viene trattato come duplicato
  e l'acquisto è scartato in silenzio (`f10_copilot.py:705-712`): impossibile dalla
  UI, che genera un id nuovo a ogni clic.
- Stagione dedotta dal primo argomento che comincia per cifra
  (`f10_copilot.py:844`): `python scripts/f10_copilot.py --porta 8793 --ledger x.json`
  dà `nessun pack per 8793`. Fallimento rumoroso, e sia il menu sia `GUIDA_ASTA.md`
  passano sempre la stagione per prima.
- `--resume` come ultimo argomento → `IndexError: list index out of range`
  (riga 861). Rumoroso, solo da riga di comando scritta a mano.
- `--resume` non applica `stato_valido`: un ledger con `my_index` o `team_index`
  fuori intervallo fa morire l'avvio con un `IndexError` nudo invece del messaggio
  chiaro riservato ai giocatori sconosciuti; un ledger con `names: []` e acquisti
  riparte mostrando la schermata di setup. Nessuno di questi ledger può nascere dal
  Copilota stesso.
- `/copilot/advice?price=abc` chiude la connessione senza risposta (`int()` non
  protetto, riga 638): la UI normalizza sempre il prezzo a un intero ≥ 1
  (`copilot.html:970`), quindi non è raggiungibile.
- `/copilot/bid` non ha `richiesta_id`: un doppio clic registra due rilanci. Non
  tocca rose né budget; si annulla con `undo_bid`.
- `undo` toglie l'ultimo evento del registro, non quello mostrato nel pulsante, che
  può essere vecchio fino a 2 s (polling): serve una seconda scheda o due persone
  che registrano insieme perché diverga.
- `/copilot/bid` fa cambiare `versione_stato()` senza cambiare i piani: la cache
  resta corretta, ma il numero suggerisce il contrario.
- La copia `.buono.json` è scritta con `write_text` non atomico (riga 154): è
  l'unico file troncabile del meccanismo, ma non è quello da cui si riprende.
- `/launcher/start` esegue `terminate()` e `Popen` fuori dal lock (righe 154-196):
  due avvii simultanei sulla stessa porta lasciano un processo non tracciato. Serve
  un doppio clic vero sul pulsante, che il menu già disarma con `LN.cp.starting`.
