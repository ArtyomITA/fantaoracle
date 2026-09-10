# Caccia ai difetti — lente INTERFACCIA (viz/copilot.html) in asta vera

Data: 10/09/2026. Sola lettura sul progetto. Server di prova sulla porta 8794
con ledger nello scratchpad (`ledger_repro_8794.json`), spento a fine lavoro.
Prova della pagina VERA (`file:///viz/copilot.html?live=http://127.0.0.1:8794`)
in Chrome headless via playwright (`channel="chrome"`; i browser scaricati di
playwright non ci sono, Chrome di sistema sì).

Metodo: il file HTML è stato letto per intero (1567 righe, di cui il JS da riga
650); ogni rilievo è stato poi ripetuto sulla pagina reale collegata al server
di prova. Gli script `repro_ui_1..8.py` sono autonomi: avviano il Copilota se
non è già in ascolto sulla 8794, aprono la pagina in Chrome, e escono 1 se il
difetto c'è, 0 se non c'è, 2 se la prova è inconcludente (Chrome assente).

## Esito degli script

| script | difetto | esito |
|---|---|---|
| repro_ui_1.py | ricerca cieca agli accenti | exit 1 |
| repro_ui_2.py | nessun avviso di indisponibilità al banco | exit 1 |
| repro_ui_3.py | martelletto sotto la piega | exit 1 |
| repro_ui_4.py | piani stantii dopo ANNULLA | exit 1 |
| repro_ui_5.py | Invio sceglie il valore più alto | exit 1 |
| repro_ui_6.py | griglie ricostruite ogni 2 s | exit 1 |
| repro_ui_7.py | escluso non registrabile dalla UI | exit 1 |
| repro_ui_8.py | rilancio fallito in silenzio | exit 1 |

---

## 1. La ricerca è cieca agli accenti (alta)

`scripts/f10_copilot.py:663` filtra con `text in p.name.lower()`: nessuna
normalizzazione Unicode. Nel pack 2026-27 diciassette nomi hanno un accento
(Soulè ROM, Konè M. ROM, Kessiè ATA, Dodò FIO, Laurientè SAS, Bernabè PAR,
Tourè E./I., Lucumì, Zè Pedro, Cissè A., Traorè Hj., Candè, Montipò, Dembelè A.,
Calò, Konè I.).

Output di `repro_ui_1.py`:

```
senza accento={'soule': [], 'dodo': [], 'kessie': [], 'kone': ['Kone B.']}
con accento={'Soulè': ['Soulè'], 'Dodò': ['Dodò'], 'Kessiè': ['Kessiè'],
             'Konè': ['Konè M.', 'Konè I.']}
```

Nella pagina reale, digitando `soule` la lista dice «nessuno nel listino
residuo con questi filtri»: identico a un giocatore già venduto o a un errore
di battitura. Il caso peggiore è `kone`: trova **Kone B.** (COM) e non Konè M.
(ROM); con Invio (riga 946) va al banco l'omonimo sbagliato.

Fix: normalizzare entrambi i lati con
`unicodedata.normalize("NFKD", s).encode("ascii","ignore")` nel confronto di
`/copilot/players` (una riga, `scripts/f10_copilot.py:663`). Rischio: la
ricerca diventa un po' più larga (chi cerca «Cisse» trova anche «Cissè»), che è
esattamente quello che serve; nessun effetto su prezzi, consigli o registro.

## 2. Al banco non compare l'indisponibilità (alta)

`data/copilot/eleggibilita_2026-27.json` marca **54** giocatori indisponibili e
`/copilot/advice` restituisce il campo `indisponibile` con il testo della
fonte. `viz/copilot.html` non lo usa mai: `grep -n "indisponibil" viz/copilot.html`
trova solo la riga 792, che è il riepilogo di provenienza («indisponibili oggi
54 (restano comprabili)»). Né `renderLot` né `renderAdvice` (righe 1157-1237)
mostrano nulla per il giocatore al banco.

I primi indisponibili per valore del modello:

```
249.7 McTominay  C NAP  aritmia, fermo dall'1 settembre
232.9 Santos A.  A NAP
224.7 Locatelli  C JUV  rottura ...
221.7 Zaniolo    C UDI
215.5 Orsolini   C BOL
194.9 Meret      P NAP
209.1 Gaetano    C ATA  squalificato 4a giornata
```

`repro_ui_2.py` porta McTominay al banco nella pagina vera e cerca nel pannello
le parole «indisponib», «infortun», «squalific» e le prime parole della nota:
nessuna presente. Il pannello mostra q10 63 · q50 72 · q90 87 · valore 250 e
«AL MASSIMO 38», come per un giocatore sanissimo.

Fix: in `renderAdvice` (dopo riga 1227) aggiungere, quando `a.indisponibile`,
un chip rosso nel blocco `lotChips` con `a.indisponibile.testo` in `title`, e
la stessa marcatura nelle righe della ricerca. Rischio: nessuno sul calcolo;
solo rendering. Attenzione a non trasformarlo in un veto: gli indisponibili
restano comprabili, il tetto lo decide il modello.

## 3. Il martelletto sta sotto la piega, e il tavolo esce dallo schermo (alta)

Misure sulla pagina reale con un giocatore al banco (`repro_ui_3.py` e prova a
tre larghezze), coordinate in px dal bordo alto della finestra:

| viewport | advice | griglia rilanci | griglia martelletto | scrollWidth / clientWidth |
|---|---|---|---|---|
| 1366x768 | 637-754 | 796-1050 | **1135-1389** | 1401 / 1366 |
| 1536x864 | 637-754 | 796-1050 | **1135-1389** | 1571 / 1536 |
| 1920x1080 | 637-754 | 796-1050 | **1135-1389** | 1955 / 1920 |

La posizione non dipende dalla finestra: la colonna AL BANCO è alta ~1390 px
sempre. Su un portatile 1366x768 servono ~620 px di scorrimento per arrivare a
«AGGIUDICATO A…», e mentre si è scorsi in basso il campo del prezzo (571-622) e
il consiglio non si vedono più. Anche su 1920x1080, con la barra del browser, i
bottoni del martelletto restano sotto il bordo.

In più la pagina ha **sempre** una barra orizzontale: gli indicatori di slot
delle squadre (`.slot-group`/`.sq`, colonna IL TAVOLO larga fissa 330 px,
`viz/copilot.html:108`) sforano di 35 px. Gli ultimi tre quadratini del reparto
A di ogni avversario sono fuori pagina.

Fix minimo per stasera: rendere la colonna AL BANCO scorrevole per conto suo
(`.col:first-child{max-height:calc(100vh - 70px); overflow-y:auto}`) e spostare
la griglia del martelletto sopra la griglia dei rilanci, oppure ridurre
`.hammer-grid` a due colonne compatte; per il tavolo, `flex-wrap` sugli slot o
colonna 360 px. Rischio: tocca solo il CSS, ma cambia la posizione dei bottoni
a cui si è abituati: se si applica, va provato una volta prima dell'asta.

## 4. Dopo ANNULLA il pannello piani mostra numeri di uno stato che non esiste (media)

`hammer()` (riga 1324) svuota `PI.dati` **e** riscrive il riquadro con «lo
stato è cambiato: ricalcola i piani». `undo()` (riga 1367) svuota `PI.dati` ma
non tocca il DOM, e `renderPiani` esce subito se `PI.dati` è nullo: resta a
schermo, identico, il piano calcolato prima.

Il controllo che avrebbe dovuto dirlo è morto: a riga 1089 `const vecchio = ...`
viene calcolato e mai usato (unico riferimento nel file, verificato con grep).

`repro_ui_4.py`, sulla pagina reale: acquisto McTominay a 60 per la mia
squadra, calcolo i piani, poi ANNULLA dall'interfaccia.

```
testo identico prima/dopo=True, avviso presente=False, PI.dati=None,
budget del piano ancora a schermo=440 mentre il budget vero e' 500
```

A schermo resta «costo previsto 439.9 / 440» con la rosa che comprende un
giocatore che non è più mio.

Fix: in `undo()`, accanto a `PI.dati = null`, la stessa riga che c'è in
`hammer()`:
`const b=$("piOut"); if(b) b.innerHTML = '<div class="tick-empty">lo stato è cambiato: ricalcola i piani</div>';`
Rischio: nessuno; è la strada già percorsa dal martelletto.

## 5. Invio nella ricerca sceglie il valore più alto, non la corrispondenza migliore (media)

Il server ordina per `value` decrescente (`scripts/f10_copilot.py:664`), la UI
prende `C.results[0]` all'Invio (riga 946) senza chiedere niente.

```
risultati=['Martinez L./A', 'Martinez Jo./P']
Invio porta al banco 'Martinez L./A' (il primo per valore)
```

Se al banco sale il portiere Martinez Jo. e si digita «martinez» + Invio, al
banco arriva Lautaro. Il nome è scritto grande, ma il passo successivo (prezzo,
martelletto) non chiede conferma: basta non guardare per registrare un acquisto
di un altro giocatore, con budget e rosa dell'avversario sbagliati.

Fix: all'Invio selezionare solo se c'è un risultato unico, oppure se il primo
ha lo stesso ruolo della pillola attiva; altrimenti evidenziare e chiedere un
secondo Invio. Rischio: un tasto in più quando i risultati sono ambigui;
rallenta di mezzo secondo i casi ambigui, non gli altri.

## 6. Le griglie dei bottoni si ricostruiscono ogni 2 secondi (media)

`onState` chiama `renderTeams` a ogni poll, anche quando non è cambiato niente,
e `renderTeams` finisce con `if(C.sel) renderHammerGrid();` (riga 1473).
`renderHammerGrid` riscrive `innerHTML`: i bottoni sono nodi nuovi ogni 2 s.

```
eventi invariati=True, stesso nodo dopo 5 s=False, nodo ancora nel documento=False
```

Conseguenza (osservata nel codice, non provata con un mouse vero): un click che
comincia prima del refresh e finisce dopo non produce alcun evento `click`,
perché il nodo del `mousedown` non è più nel documento — il martelletto non
viene registrato e non appare nessun avviso. Stessa cosa per la griglia dei
rilanci e per il popover della rosa avversaria, che si riposiziona mentre lo si
legge.

Fix: in `onState` chiamare `renderTeams` solo quando cambia qualcosa
(`changed || st.n_bids !== C.lastBids`), oppure in `renderHammerGrid`
aggiornare solo testo e `disabled` dei bottoni esistenti quando il numero di
squadre non cambia. Rischio: se si sbaglia la condizione, i budget nel tavolo
smettono di aggiornarsi; la seconda strada (aggiornare in loco) è più sicura.

## 7. Un giocatore escluso dal filtro non è registrabile dall'interfaccia (media)

`/copilot/players` cerca in `pool()` con `solo_eleggibili=True`: i 63 marcati
fuori Serie A non compaiono mai nella ricerca, nei piani, nelle nomination. Il
martelletto invece li accetta apposta (`pool(solo_eleggibili=False)`), ma
dall'interfaccia non c'è nessun modo di portarli al banco.

```
ricerca UI di 'Delli Carri' -> 0 risultati («nessuno nel listino residuo»)
POST /copilot/hammer -> ok=True, nota="questo giocatore risulta fuori dalla
Serie A secondo il listone: registrato perche' l'asta reale comanda..."
```

Se stasera anche un solo escluso viene messo all'asta (la lista viene da un
listone del 9/9, non è infallibile), l'acquisto non si può registrare: da lì in
poi il budget di quell'avversario è sbagliato per tutta l'asta, e con esso ogni
consiglio che dipende da quanto possono ancora spendere gli altri.

Fix: quando la ricerca non trova nulla, ripetere la stessa query con
`solo_eleggibili=False` (o un parametro `includi_esclusi=1`) e mostrare le
righe trovate in grigio con l'etichetta «fuori lista — registrabile». Rischio:
un fuori lista può finire per sbaglio fra i selezionabili; va tenuto separato e
scritto, e il consiglio continua a dire «nessuna offerta».

## 8. Il rilancio fallito non lo dice nessuno (bassa)

`registraRilancio` (righe 1275-1286) ha `try { ... } finally { C.busy = false; }`
senza `catch`; il pulsante «annulla rilancio» (riga 1271) non controlla nemmeno
`d.ok`. Simulando la caduta della rete al momento del click:

```
toast='' testo='' ; eccezione non gestita=['TypeError: Failed to fetch'] ; C.busy=False
```

Nessun avviso: chi registra crede di aver segnato il rilancio. Impatto limitato
(i rilanci non muovono budget né rose, sono solo telemetria), ma il registro
esportato risulta incompleto.

Fix: aggiungere `catch(e){ toast("server non raggiungibile", "err"); }` nelle
due funzioni, come già fa `hammer()`. Rischio: nullo.

---

## Scartati (visti, non riportati)

- `/copilot/advice` con `price=0`: `if q.get("price")` è falso per "0", il
  server tratta lo zero come «nessun prezzo» e non confronta mai; la UI può
  mandare 0 svuotando il campo. Effetto pratico nullo (a 0 il consiglio è
  comunque «rilancia»).
- `/copilot/players` tronca a 80 righe lato server, la UI ne mostra 40 e scrive
  «…e altri N»: con i soli filtri ruolo/squadra quel N è sbagliato per difetto.
- Se la richiesta del consiglio fallisce, il riquadro resta al 55% di opacità
  con il consiglio del prezzo precedente; l'etichetta dice «al prezzo N», quindi
  non mente, ma si legge male di fretta.
- «q90 · tetto» chiama tetto il q90, mentre il tetto operativo è
  `max consigliato` (numero diverso, più in basso nella stessa scheda).
- Il martelletto non chiede conferma (un click registra); mitigato da ANNULLA,
  che invece è armato in due tempi.
- `api()` non guarda `res.ok`: le risposte 400 del server portano comunque JSON
  con `err`, e i chiamanti principali lo controllano.
- Dopo il martelletto i rilanci del lotto chiuso restano in `last_bids`: il
  bottone «annulla rilancio» continua a proporre una riga di un lotto finito.
- Le due griglie (rilanci e martelletto) hanno la stessa classe `.hbt`, gli
  stessi dieci nomi e lo stesso aspetto, a 340 px di distanza: cliccare quella
  sbagliata registra un rilancio invece dell'aggiudicazione, e l'unica
  differenza è un toast di 2,6 secondi.
- Il popover della rosa avversaria viene ricalcolato e riposizionato a ogni
  poll (stesso `renderTeams` del rilievo 6).
- `caricaProvenienza` gira una volta sola al caricamento: se il server parte
  dopo la pagina, il riquadro resta «provenienza non disponibile» per sempre
  (dichiarato, non ingannevole).

## Comandi usati

```
python scripts/f10_copilot.py 2026-27 --porta 8794 --ledger <scratchpad>/ledger_repro_8794.json
python repro_ui_1.py … repro_ui_8.py     # tutti exit 1
```

Nessun processo lasciato in vita; nessun file del progetto modificato o creato
(eccetto `data/copilot/prove/ledger_w1_8794.json`, la prova prevista dal
mandato, scritta dalla prima sessione di prova).
