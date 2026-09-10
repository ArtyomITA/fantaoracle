# Caccia ai difetti — lente: correttezza di CONSIGLI, TETTI e BUDGET

Sessione di sola lettura sul progetto `fantabot`. Nessun file del
progetto è stato modificato, creato o cancellato. Tutte le prove girano in memoria: il
modulo `scripts/f10_copilot.py` viene caricato per percorso con `importlib`, `PACK` e
`ELEGGIBILITA` sono quelli veri (`data/packs/pack_2026-27.pkl`, 587 giocatori;
`data/copilot/eleggibilita_2026-27.json`, 63 fuori Serie A e 54 indisponibili), il
`LEDGER_PATH` sta in una cartella temporanea e le richieste HTTP passano da un
`Handler` finto. **Il server sulla porta 8792 non è mai stato avviato: non serviva.**
Nessun processo lasciato vivo.

File esaminati: `scripts/f10_copilot.py` (913 righe, tutto), `src/fantabot/piani.py`,
`src/fantabot/optimizer.py`, `src/fantabot/bots/bot_b.py` (il bot che il Copilota
interroga: `ADVISOR = BBot(...)` a riga 275-276), `src/fantabot/models.py`,
`viz/copilot.html` (solo per capire che cosa arriva davvero all'occhio).

## Prove riproducibili

Otto script autonomi, ciascuno esce con 1 se il difetto c'è e 0 se non c'è, e stampa
`atteso` / `osservato`:

| # | script | esito |
|---|--------|-------|
| 1 | `repro_consigli_1.py` | EXIT=1 |
| 2 | `repro_consigli_2.py` | EXIT=1 |
| 3 | `repro_consigli_3.py` | EXIT=1 |
| 4 | `repro_consigli_4.py` | EXIT=1 |
| 5 | `repro_consigli_5.py` | EXIT=1 |
| 6 | `repro_consigli_6.py` | EXIT=1 |
| 7 | `repro_consigli_7.py` | EXIT=1 |
| 8 | `repro_consigli_8.py` | EXIT=1 |

Comando usato per tutti (da `fantabot`):

```
python "C:\Users\ADMINI~1\AppData\Local\Temp\claude\E--claudecode-pesante\5ff20539-b495-4ac4-bed4-79eabbf8a8b7\scratchpad\w1\repro_consigli_<n>.py"
```

---

## 1. ALTA — il piano che vedi non è il piano che calcola i tetti

`contesto_piani()` (f10_copilot.py:447-468) costruisce il MILP dei piani **senza**
`forced_spend`, mentre `BBot._replan` (bot_b.py, blocco `if self.objective.get("attack_share")`)
lo passa sempre: l'obiettivo scelto dal Monte Carlo è
`{'lam': 0.5, 'attack_share': (0.35, 0.5), ...}`, cioè fra 175 e 250 crediti di attacco su
500. Il pannello `/copilot/piani` mostra quindi una rosa costruita con un vincolo in meno,
e `/copilot/advice` dà i tetti su un'altra rosa. Il docstring di `contesto_piani` dichiara
il contrario: «Gli stessi ingressi con cui il bot ripianifica: nessuna seconda politica».

Stato iniziale, 10 squadre, 500 crediti, nessun acquisto:

```
forced_spend di contesto_piani = None | attack_share del bot = (0.35, 0.5)
spesa attacco nel piano mostrato = 93.0        (il vincolo del bot chiede >= 175)
6 giocatori nel piano mostrato ma fuori dai target, 6 target fuori dal piano mostrato

[Malen]     NON e' nella rosa mostrata, advice dice: NEL PIANO (titolare): rilancia fino a 167
[Kalulu]    NON e' nella rosa mostrata, advice dice: NEL PIANO (titolare): rilancia fino a 26
[Laurientè] e' nella rosa mostrata (titolare=True), advice dice: fuori piano: rilancia al massimo fino a 15
[Dimarco]   e' nella rosa mostrata (titolare=True), advice dice: fuori piano: rilancia al massimo fino a 35
```

Malen è il caso che costa di più: la scheda al banco lo dà titolare del piano con tetto
**167 crediti**, il pannello dei piani non lo contiene affatto e propone Laurientè come
bomber di riferimento — che al banco riceve un cartello giallo «AL MASSIMO 15».

Controprova (stessa `Contesto`, aggiunto solo `forced_spend={"A": (175, 250)}`):

```
SENZA forced_spend: |piano ^ targets| = 19   spesa A  93.0
CON   forced_spend: |piano ^ targets| = 25   spesa A 191.4
```

Con il vincolo le due rose coincidono al 100%. La causa è isolata.

**Fix**: in `contesto_piani()` calcolare `forced_spend` come fa `BBot._replan`
(`lo = max(0, 0.35*budget_totale - speso_A)`, `hi = max(lo, 0.5*budget_totale - speso_A)`)
e passarlo alla `Contesto`; se il MILP vincolato non è fattibile, ritentare senza, come già
fa il bot. Rischio: i piani alternativi diventano più costosi in attacco e possono
risultare «non fattibile» in stati stretti; è però lo stesso vincolo con cui vengono
calcolati i tetti, quindi il rischio è di veder comparire l'infattibilità, non di
introdurne una nuova.

## 2. ALTA — il tetto non sa che la rosa va completata

`decisione_operativa` (f10_copilot.py:306-381) tronca il tetto del bot con il solo limite
legale `max_bid`. Non considera mai il caso opposto: quando i giocatori ancora comprabili
per un ruolo sono meno o quanti gli slot da riempire, quel giocatore **va preso a
qualunque prezzo fino al massimo legale**, perché l'alternativa è chiudere l'asta con la
rosa incompleta.

Scenario ricostruito (io con 24/25 slot pieni, 1 slot A, un solo attaccante ancora libero
in tutto il pool, 476 crediti in cassa):

```
attaccanti liberi: ['De Martis']
azione=lascia  max_consigliato=1  max_legale=476
motivo: oltre il massimo 1: target: q50 2, mi spingo a 1
il giocatore e' fra i target del piano: True
```

Il giocatore è nel piano (il MILP lo mette in rosa perché non ha scelta) ma il tetto resta
1, perché `_max_bid_for` guarda solo `q90 * heat`. Basta un rilancio a 2 di un avversario e
il cartello diventa rosso «LASCIALO oltre 1». Stessa cosa con 2 slot e 2 attaccanti
(budget 40, `max_legale` 39, tetto 1 su entrambi). Nell'ultima fase dell'asta, quando tutti
rincorrono i riempitivi, è la situazione normale, non un caso limite.

**Fix**: in `decisione_operativa`, dopo la bisezione, se
`len([p in pool con ruolo r]) <= slot_ruolo` allora `tetto = max_legale` (con motivo
«ultimo/i disponibile/i del reparto: la rosa va completata»). Rischio: se il conteggio del
pool è più largo di quello vero (giocatori che nessuno chiamerà), il tetto passa da 1 a
tutta la cassa: va applicato solo a `slot_ruolo >= numero di candidati residui`, mai come
regola generale.

## 3. ALTA — `/copilot/setup` rifatto a metà asta manda la cassa sotto zero

`stato_valido` (f10_copilot.py:232-266) controlla nomi, indice, quote e il minimo legale
`sum(quote) > budget`, ma non confronta il budget nuovo con quello **già speso** dagli
eventi che tiene. Il corpo del POST conserva `events` (`candidato = {**STATE, ...}`), quindi
un secondo setup — per correggere un nome, per esempio — con il budget sbagliato passa e
viene salvato su disco.

```
cassa 100 -> -300, max_bid -323
consiglio: azione=nessuna offerta max_consigliato=0 max_legale=-323
stato scritto su disco: True
```

Da quel momento il Copilota risponde «cassa insufficiente» su chiunque, e il ledger contiene
uno stato illegale.

**Fix**: in `stato_valido`, dopo aver ricostruito le quote, calcolare per ogni squadra la
spesa degli eventi e rifiutare con 400 se `spesa > budget - (slot_residui)`; in generale,
rifiutare qualunque cambio di `budget`/`quotas` quando `events` non è vuoto. Rischio:
nessuno per l'uso normale (il setup si fa a tavolo vuoto); toglie la possibilità di
correggere il budget dopo il primo martelletto, che oggi però produce solo stati rotti.

## 4. MEDIA — `piano_prezzo` risponde «ok» anche quando il vincolo non è stato applicato

`piani.piano_al_prezzo` (piani.py:221-259) impone il giocatore con `required={pid}`, ma
`optimize_roster` applica `required` solo `if pid in allp` (optimizer.py:100-101). Se il
giocatore è già stato aggiudicato ad altri, o è fuori lista, non è fra i candidati: il
vincolo cade in silenzio e torna una rosa **senza di lui**, etichettata `stato: ok` con il
prezzo ipotetico chiesto. L'endpoint controlla solo `pid in PACK.players`
(f10_copilot.py, ramo `/copilot/piano_prezzo`).

```
Milik venduto a T3 per 30 -> code=200 stato=ok in_rosa=False prezzo_ipotetico=50.0 costo_previsto=459.8
Zielinski gia' mio        -> stato=ok prezzo_ipotetico=400.0 riga: prezzo_atteso 0.0, gia_mio True
```

Nel secondo caso il prezzo ipotetico viene ignorato perché il giocatore sta in `fissati` a
costo zero: «se lo prendo a 400» mostra una rosa che spende 400 crediti altrove.

**Fix**: nell'endpoint `/copilot/piano_prezzo`, prima di chiamare, rispondere 400 con
«già aggiudicato» se `pid not in pool(solo_eleggibili=False)`, «fuori lista» se
`pid in ELEGGIBILITA["esclusi"]`, «è già tuo» se è nel mio roster. Rischio: nullo, è un
controllo in più su un percorso che oggi mente.

## 5. MEDIA — infortunati e squalificati pesano a valore pieno e il consiglio tace

Le fonti dichiarano 54 indisponibili e il Copilota li tiene nel pool per scelta dichiarata
(«non toglie gli infortunati — restano comprabili»). Ma il valore usato dal MILP e dai
tetti è quello di un giocatore sano, e la frase che arriva al tavolo non nomina mai lo
stato: `decisione_operativa` mette `indisponibile` in un campo a parte,
`adviceView` in `viz/copilot.html` (righe 1006-1033) usa solo `azione`, `max_consigliato` e
`motivo`, e `player_info` — quello che alimenta la ricerca giocatori — il campo non ce l'ha
proprio.

```
indisponibili dichiarati dalle fonti: 54
14 indisponibili consigliati sopra 5 crediti senza una parola nel testo
  McTominay  max 38  in_piano=False  :: fuori piano: rilancia al massimo fino a 38
  Yildiz     max 35  in_piano=False  :: fuori piano: rilancia al massimo fino a 35
  Solet      max 25  in_piano=True   :: NEL PIANO (titolare): rilancia fino a 25
  Locatelli  max 13  in_piano=True   :: NEL PIANO (panchina): rilancia fino a 13
indisponibili dentro i 25 del piano: ['Locatelli', 'Solet', 'Varela G.']
```

Tre dei 25 del piano iniziale sono fermi. Nessuna riga della scheda al banco lo dice.

**Fix minimo (stasera)**: in `advice`, se `d["indisponibile"]`, anteporre al `consiglio` e
al `motivo` la parola dello stato, per esempio
`out["consiglio"] = f"[{indisp['tipo'].upper()}] " + out["consiglio"]`; l'alternativa più
invasiva (scontare il `value`) cambierebbe il modello a poche ore dall'asta. Rischio del
fix minimo: nullo sui numeri, cambia solo il testo.

## 6. MEDIA — GET malformati fanno esplodere il gestore, senza risposta

`do_GET` fa `int(q["price"])` senza protezione (f10_copilot.py:638) e `nominate` indicizza
`quotas[role]` con quello che arriva dalla query (f10_copilot.py:512-515). L'eccezione esce
da `do_GET`: il client non riceve nessun JSON, la connessione viene chiusa dal
`socketserver`, e il pannello resta muto (l'`api()` della UI finisce nel `catch`).

```
/copilot/advice?player_id=133&price=abc -> ValueError: invalid literal for int() with base 10: 'abc'
/copilot/advice?player_id=133&price=3.5 -> ValueError: invalid literal for int() with base 10: '3.5'
/copilot/nominate?role=X                -> KeyError: 'X'
```

**Fix**: avvolgere la lettura di `price` in `try/except (TypeError, ValueError)` con
`return self._send({"err": "prezzo non valido"}, 400)`, e in `nominate` respingere un ruolo
non in `ROLES`. Rischio: nullo.

## 7. BASSA — `max_bid` mostrato = budget + 1 per una squadra con la rosa piena

`TeamState.max_bid` (models.py:36-39) fa `budget - (slots_left - 1)`: con 0 slot liberi
diventa `budget + 1`. `/copilot/state` lo pubblica così com'è per ogni squadra
(f10_copilot.py:625), e la tabella del tavolo attribuisce potere d'acquisto a chi non può
più comprare.

```
nome=T1 budget=250 max_bid=251 slot_liberi=0
```

Il martelletto è comunque protetto dal controllo sul reparto pieno
(`T1: reparto A pieno`), quindi il danno è di lettura, non di registro. Conta perché il
numero serve proprio a decidere quanto rilanciare contro quella squadra.

**Fix**: `return 0 if self.slots_left(quotas) <= 0 else self.budget - (slots_left-1)*min_price`,
oppure `max(0, ...)` nel solo punto della UI. Rischio: `max_bid` è usato anche in
`decisione_operativa` e nella validazione del martelletto, ma entrambi hanno già una
guardia su `slots_left <= 0` prima di arrivarci; va comunque rilanciata la suite
(`tests/`) perché la funzione è condivisa con il simulatore.

## 8. BASSA — piani alternativi impossibili quando il reparto A è pieno

`scegli_bomber` (piani.py:109-118) filtra i candidati solo per prezzo e per «non è già
mio», non per slot liberi nel ruolo. Con il reparto A completo tutte le alternative
tornano «non fattibile» con un motivo che incolpa la rosa.

```
slot A liberi = 0 -> 3 alternative prodotte, 3 non fattibili
  Malen in rosa e titolare    -> nessuna rosa legale con questo vincolo
  Ramos G. in rosa e titolare -> nessuna rosa legale con questo vincolo
```

Chi legge pensa che manchino i crediti.

**Fix**: in `costruisci_piani`, se `quote["A"] - (attaccanti in ctx.fissati) <= 0`, non
generare alternative e dichiarare «reparto A già completo». Rischio: nullo.

---

## Verifiche fatte che NON hanno trovato difetti (risultati negativi, utili quanto gli altri)

- **Il tetto non supera mai `budget - (slot residui - 1)`.** Su 250 giocatori estratti a
  caso in uno stato di metà asta (mio budget 275, 20 slot, `max_bid` 256): 0 violazioni.
  `decisione_operativa` limita la bisezione a `max_legale` e `plan()` usa lo stesso numero.
- **La bisezione converge e coincide con la forza bruta.** Per ogni giocatore con azione
  diversa da «nessuna offerta» è stato calcolato il massimo per scansione lineare da 1 a
  `max_legale`: 0 differenze, e l'accettazione del bot è risultata monotona in tutti i casi
  provati (le tre soglie di `BBot.bid` — guardia anti-zavorra a 5 crediti, tetto del target,
  tetto del bargain — sono tutte soglie superiori). Il ciclo `while basso < alto` con
  `mezzo = (basso+alto+1)//2` termina sempre su interi.
- **Il consiglio è monotono nel prezzo.** 40 giocatori × prezzi da 0 a 59: una volta
  «lascia», mai più «rilancia».
- **I piani rispettano i miei acquisti e quelli degli altri.** 4 scenari con 6 miei
  acquisti e 150 venduti agli altri: 0 giocatori venduti dentro un piano, 0 miei giocatori
  mancanti, 0 piani che sforano il budget residuo (costi 357.8–427.9 contro budget
  358–428).
- **Nessun crash né rifiuto in un'asta intera simulata.** 190 martelletti attraverso
  l'`Handler` (10 squadre), consiglio richiesto prima di ogni mio lotto: 0 errori,
  0 tetti oltre il legale, 0 target già venduti mostrati nel piano (il replan scatta appena
  un target viene battuto), 8.4 s totali.
- **Tempi compatibili con l'asta dal vivo** (tutte le rotte tengono il `LOCK` globale):
  `/copilot/plan` 0.01 s, `/copilot/piani?quanti=8` 1.95 s, `/copilot/piano_prezzo` 0.61 s,
  un singolo MILP 0.19 s. Il tetto interno di `piani.SECONDI_MASSIMI = 20` non è mai stato
  raggiunto.
- **Unità di misura coerenti.** Nel MILP i prezzi sono crediti (`max(1, q50 * heat)`) e i
  valori sono fantapunti (`value`, con `lam * (value_up - value)`); il vincolo di bilancio
  usa solo i primi, l'obiettivo solo i secondi. `Player.ref_price` (frazione di budget) non
  entra da nessuna parte nel Copilota. Il `prezzo_mercato` del bundle resta un campo a
  parte e non viene mai sommato o confrontato con i quantili.

## Cose viste e non riportate come difetti

- `contesto_piani` passa `min_spend=obiettivo.get("min_spend")`, ma `PACK.b_objective` non
  ha quella chiave: il pavimento di spesa è **sempre `None`**, `MIN_SPEND_FRAC = 0.95` non
  entra mai nei piani del Copilota. Effetto misurato: nullo a inizio asta (il piano di
  riferimento costa 500.0 su 500) e a metà (274.6 su 275), perché l'obiettivo satura da solo
  il budget quando conviene. Con pochi slot e molta cassa il piano lascia crediti fermi
  (478 di budget, 3 slot, piano da 184.2) — ma è la risposta corretta del modello: comprare
  più caro non aggiunge valore. Codice morto, non difetto.
- La guardia anti-zavorra `MIN_VALUE_OVER_5CR = 130` tappa a 5 crediti chiunque valga meno,
  anche con `q50` alto: è una politica dichiarata e misurata (indagine 2025-26), non un bug.
- I `max_consigliato` dei 25 target di `/copilot/plan`, sommati, superano il budget: sono
  tetti indipendenti «se lo compro adesso», non un piano di spesa. La UI mostra accanto
  budget e costo atteso del piano.
- `scegli_bomber` accetta candidati con prezzo fino a tutto il budget senza tenere un
  credito per gli altri slot: il MILP li scarta comunque, l'effetto è solo qualche
  alternativa «non fattibile» in più.
- `/copilot/advice?price=0` viene interpretato come prezzo 0 (non come «nessuna offerta»)
  perché la stringa "0" è vera: comportamento corretto, l'ho verificato per escluderlo.
- `/copilot/undo_bid` toglie sempre l'ultimo rilancio, anche se appartiene a un lotto
  diverso da quello aperto: fuori dalla mia lente (registro rilanci, non consigli).
