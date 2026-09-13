# VERIFICA2 — verificatore W, 13/9/2026

Verifica indipendente del lavoro di Z (server + tetto + evento_modifica) e di G
(pagina nuova `viz/asta.html`). Sola lettura sul progetto: gli unici file scritti
sono questo, le copie di prova `data/copilot/prove/W_*.json` e le immagini in
`w12/W/`. Porte usate: 8797, 8798, 8799, tutte fermate alla fine.

## VERDETTO: PRONTO CON RISERVE

Tutto quello che serve stasera funziona e regge le prove: test verdi, tetto
stabile, correzione di qualsiasi lotto, pagina nuova senza errori. Le tre
riserve sono di leggibilita' e di forma, nessuna blocca l'asta.

---

## 1. Test

```
PYTHONPATH=src PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python -m pytest \
  tests/test_copilot_asta.py tests/test_copilot_tetto.py \
  tests/test_copilot_modifica.py tests/test_ponte_fantaasta.py \
  tests/test_bot_l3_tetti.py -p no:cacheprovider -q
```

**83 passed, 1 skipped in 31,32 s.** L'unico skip e' pre-esistente:
`tests/test_copilot_asta.py:141 «nessun attivo senza previsione»`.

`viz/ponte.html` **non viene piu' riscritto**: mtime 1789305100 prima della
corsa, 1789305100 dopo. Il test usa `monkeypatch.setattr(pb, "PAGINA", tmp_path
/ "ponte.html")` (`tests/test_ponte_fantaasta.py:41`). Anche i tre ledger veri
hanno mtime invariato dopo i test.

## 2. Stabilita' del tetto (V1) e replay

Server mio su **8797**, `--resume data/copilot/prove/W_1.json` (copia del ledger
vero troncata a 190 acquisti).

16 GET `/copilot/advice?player_id=5585&price=150` a 2 s di distanza:

| | valore |
|---|---|
| chiamate «pronto» | 16 su 16 |
| `prezzo_indifferenza` distinti | **1** (244) |
| `max_consigliato` distinti | **1** (289) |
| tempi | 3–75 ms |

Su cache fredda (server appena riavviato) la prima risposta e' `in_calcolo` con
tetto 272 (cap del bot), poi a 2,0 s arriva 289 e non cambia piu': **nessuno
sfarfallio**.

Replay: `PYTHONPATH=src python reports/asta_20260913/replay_tetto.py`

```
arriva al prezzo: 7/28; dei quattro citati 3/4; tetti oltre lo spendibile: 0
```

| giocatore | pagato | tetto nuovo | esito |
|---|---|---|---|
| Malen | 275 | **289** | >= pagato, ok |
| Martinez L. | 255 | **300** | >= pagato, ok |
| Hojlund | 200 | **219** | >= pagato, ok |
| Raimondo | 80 | **42** | < 120, ok (era 251 col premio di scarsita' indebito) |

Tetti sopra il massimo spendibile: **0**.

## 3. `POST /copilot/evento_modifica` e `asta_registra.py`

Con 190 acquisti tutti i reparti D sono pieni, quindi lo spostamento del lotto
42 descritto nel compito («da team 0 a 5») non e' eseguibile su quel tavolo: il
server lo rifiuta con `«Ac Mignottingham Forest: il reparto D andrebbe a 9 su
8»` e lo stato resta identico (giusto). La scena e' stata riprodotta su una
seconda copia troncata a 100 acquisti (`W_3.json`, server 8798), dove il lotto
42 e' Tavares N. (D, Nightmare fc, 12).

| prova | esito |
|---|---|
| sposta il lotto 42 (team 5 -> 0) | 200 ok; casse 417/408 -> 405/420; D 7/8 -> 8/7 |
| stesso `richiesta_id_modifica`, squadra diversa | 200 `{"duplicato": true}`, stato invariato: **idempotente** |
| hammer Stones 2514 sullo slot liberato (team 5, 2 cr) | 200 ok, 101 acquisti, cassa 420 -> 418 |
| cambio del solo prezzo (lotto 10, 2 -> 5) | 200 ok, squadra invariata |
| rimozione a meta' lista (lotto 7, De Gea, 9 cr a team 5) | 200 ok, 101 -> 100 acquisti, cassa 418 -> 427 (attesa 427) |
| prezzo 0 | 400 «importo 0: il minimo e' 1» |
| squadra 99 | 400 «squadra 99 inesistente: ce ne sono 10» |
| indice 9999 | 400 (messaggio fuorviante, vedi difetto D2) |
| nessun campo da cambiare | 400 «niente da modificare…» |
| senza indice ne' richiesta_id | 400 «serve «indice» oppure «richiesta_id»…» |
| `richiesta_id` inesistente | 400 «0 acquisti corrispondenti, ne serve esattamente uno» |
| prezzo 100000 | 400 «Tonno Fc: spenderebbe 100060 crediti su 500» |
| stato dopo i sette rifiuti | invariato (stessi acquisti, stesse casse) |
| indirizzo per `richiesta_id` (`fa-0-5841-0-40`, Svilar 0 -> 5) | 200 ok |
| undo dopo le modifiche | 200 ok, toglie Stones, 100 -> 99 |

`GET /copilot/eventi` restituisce 99 righe con `indice` progressivo senza buchi.
**Casse ricalcolate a mano dal registro = casse del server a ogni passo** (10
squadre, 500 crediti, `budget = 500 - somma dei prezzi`); lo stesso vale per gli
`indice` in `/copilot/state`: `last_events` 15 su 15 coerenti,
`teams[i].roster` 99 voci su 99 coerenti.

`scripts/asta_registra.py` contro 8798:

| comando | esito |
|---|---|
| `--elenco` | 99 acquisti numerati, nomi e prezzi giusti |
| `--modifica "0 > Ac"` | `OK Svilar (P ROM) indice 0: Nightmare fc 40 -> Ac Mignottingham Forest 40` |
| `--modifica "1 : 9"` | solo prezzo, 7 -> 9 |
| `--modifica "0 > TonyDa : 44"` | squadra + prezzo insieme |
| `--modifica "1 > Tonno"` (P pieno) | `RIFIUTATO … il reparto P andrebbe a 4 su 3 (400)` |
| `--rimuovi 0` | `TOLTO Svilar … era di TonyDaMilano a 44. Acquisti: 97` |

## 4. Pagina nuova `viz/asta.html`

**Suite di G sulle mie porte.** Copia dello script in scratch con
`PORTA_VERO, PORTA_VUOTO = 8798, 8799` e ledger `W_ui1.json` (190 acquisti) /
`W_ui2.json` (vuoto): **58 prove, 0 fallite**, Chrome headless 1366x768 e
1920x1080.

**Flusso rifatto a mano da me** su tavolo vuoto (8799), 21 prove, 1 fallita
(solo il font, difetto D1):

| prova | esito |
|---|---|
| il pannello di setup si apre da solo con ledger vuoto | ok |
| 10 nomi, «io» il decimo, 500 crediti, 10 maglie | ok (`my_index` 9, budget 500) |
| ricerca «malen» + Invio -> al banco | ok |
| prezzo 33 + Invio, tasto «3», Invio | Malen a Dinamo Divano per 33: 1 acquisto sul server |
| cassa della terza maglia | 500 -> 467, letta anche sulla maglia |
| tabellone | mostra «A 33 Malen ROM Dinamo Divano» |
| correggi dal tabellone -> settima maglia | `/copilot/eventi` dice `team_index 6`, casse t2 500 / t6 467 |
| U due volte | 1 -> 0 acquisti |
| tetto sul banco = `/copilot/advice` | 272 (in calcolo) -> **289** a 2,0 s, uguale a `max_consigliato` |
| scorrimento orizzontale a 1366 e 1920 | nessuno (`scrollWidth` = `innerWidth`) |
| NaN / undefined / null / [object Object] a schermo | nessuno |
| eccezioni di pagina, errori in console | nessuno |
| «sono io» | cambia `my_index` sul server (9 -> 0), rimesso a posto dopo |

**Polling** (12 s a riposo, 10 s col banco pieno, misurato sulle richieste di
rete): `/copilot/state` **0,5 req/s**, `/copilot/advice` **0,1 req/s**, tutto il
resto zero. Sotto il limite di 2 req/s per endpoint. La ripetizione
dell'advice ogni 2 s scatta solo finche' `stato_indifferenza == "in_calcolo"`
(`viz/asta.html:1002-1003`) e si ferma da sola: nella prova a freddo una sola
ripetizione.

**Leggibilita'.** I numeri che contano sono grandi: TETTO 56 px, nome al banco
27 px (`viz/asta.html:160`), q50 20 px, gli altri numeri 17 px. Sotto i 14 px ci
sono solo le etichettine maiuscole e i testi di contorno — vedi difetto D1.
Contrasto ricalcolato componendo davvero gli sfondi semitrasparenti: nessun
testo invisibile, il peggiore e' 3,29:1.

Immagini (Chrome headless 1366x768):

* setup: `C:\Users\ADMINI~1\AppData\Local\Temp\claude\E--claudecode-pesante\5ff20539-b495-4ac4-bed4-79eabbf8a8b7\scratchpad\w12\W\W_setup.png`
* banco (Malen, tetto 289): `…\w12\W\W_banco.png`
* dopo il martelletto: `…\w12\W\W_dopo_martelletto.png`
* pannello correggi: `…\w12\W\W_correggi.png`
* in piu': `W_menu.png` (menu), `W_fine.png`, piu' le 8 della suite di G
  (`G_setup.png`, `G_banco_malen.png`, `G_dopo_martelletto.png`,
  `G_correggi.png`, `G_tavolo_nuovo.png`, `G_1920.png`, `G_fine.png`,
  `G_pagina_intera.png`), tutte nella stessa cartella.

## 5. Menu

`viz/index.html` con il Copilota vivo su 8798 mostra due bottoni:

```
🏟️ ASTA (pagina nuova)      -> asta.html?live=http%3A%2F%2Flocalhost%3A8798
📋 pagina classica (copilot) -> copilot.html?live=http%3A%2F%2Flocalhost%3A8798
```

`cpStart` (`viz/index.html:641`) porta su `asta.html` dopo l'avvio. Nessuna
eccezione di pagina. `viz/copilot.html` caricata contro 8798 funziona ancora
(testata «311 PUOI SPENDERE ORA · 190 ACQUISTI», console pulita): la riserva
regge.

`scripts/fantaoracle_app.py` **non modificato**: mtime 1789012918 (10/9).
`viz/ponte_fantaasta.js` non toccato: mtime 1789058493.

## 6. Pulizia

* Server 8797, 8798, 8799 fermati. `netstat` finale: **nessun listener** su
  8770, 8899 e 8790-8799.
* Ledger veri con mtime identico a prima della verifica:
  `ledger_1788290734.json` 1788290972, `ledger_1788548783.json` 1788548789,
  `ledger_1789058317.json` 1789082212.
* Copie di prova create da me: `data/copilot/prove/W_1.json` (190),
  `W_2.json` (vuoto), `W_3.json` (100), `W_ui1.json` (190), `W_ui2.json`
  (vuoto), piu' i `.buono.json` e i `.lock` che il server scrive da solo.

---

## Difetti

| # | file:riga | cosa | gravita' |
|---|---|---|---|
| D1 | `viz/asta.html:87,163,175,198,226,280,283,289` | Etichette e testi di contorno a 8–11,5 px con contrasto 3,29–4,35:1 (sotto il 4,5:1 di WCAG AA): `.tv .l` 8,5 px «i miei crediti / puoi spendere ora / tetto al banco», `.b-num .c .l` 8 px «q10 q50 q90 valore», `.mag .pie` / `.rosa-b` / `.io-b` 8 px, `.chip` 9,5 px, `#consiglio .et` 9,5 px, `COLLEGATO` 11 px (3,29:1), i nomi squadra del tabellone 10,5 px. I numeri sono grandi e leggibili, le parole intorno no: al buio e di corsa si legge male. 540 dei 565 testi visibili stanno sotto i 14 px, quasi tutti nelle 190 righe del tabellone. | bassa (leggibilita', non blocca) |
| D2 | `scripts/f10_copilot.py:2127` (messaggio da `:655`) | Indice di riga fuori intervallo su `/copilot/evento_modifica`: `{"indice": 9999}` risponde 400 con «**squadra** 9999 inesistente: ce ne sono **100**», cioe' parla di squadre quando il numero sbagliato e' la riga del registro, e il 100 e' il numero di acquisti. Il rifiuto e' corretto, il messaggio manda fuori strada chi corregge al volo dal terminale. Servirebbe un `indice_valido` con l'etichetta giusta (o un messaggio suo per la riga). | bassa (solo forma) |
| D3 | `reports/asta_20260913/replay_tetto.py:166` | `USCITA.write_text(...)` riscrive `replay_tetto.md` per intero. Rilanciando lo script — come chiedeva questa verifica — la sezione «Nota sulla correzione V3» che Z aveva aggiunto a mano (citata in `FIX_Z.md:286`) e' **sparita**: nel file ora resta solo la «Nota sui numeri della diagnosi» generata dal template. Da rimettere a mano, o da spostare dentro lo script. Segnalo che l'ho causato io eseguendo il replay come da compito. | bassa (documentazione) |

## Cose da sapere prima di sedersi

1. **Il tetto al banco ci mette 2 secondi.** Appena porti un nome al banco il
   numero grande e' il cap del bot (Malen: 272); a 2,0 s il thread di sfondo
   consegna il prezzo di indifferenza e il numero sale al valore vero (289) e li'
   resta. Non battere nel primo secondo se il tetto conta.
2. **Il tetto e' un limite, non un'offerta.** 289 vuol dire «fin qui puoi
   spingerti», non «offri 289».
3. **Correggere non serve piu' annullare.** Qualsiasi lotto si corregge dal
   tabellone (o con `--modifica`/`--rimuovi` da terminale) e il server rifiuta
   in blocco le correzioni che sfonderebbero reparti o casse, senza toccare
   niente.
