# FIX_G — pagina nuova dell'asta (`viz/asta.html`), 13/9/2026

Agente G. Scritto un file nuovo, toccati solo i tre file consentiti.
Server di prova sulle porte **8794, 8795, 8796**, tutti fermati a fine lavoro.
Mai usate 8770 e 8899. I tre ledger veri di `data/copilot/` non sono stati
aperti in scrittura: si e' lavorato su copie (`data/copilot/prove/G_1.json`,
troncata a 190 acquisti, e `G_2.json`, vuota).

---

## Cosa c'e' adesso

`viz/asta.html` (un solo file, zero dipendenze, stessa API di
`viz/copilot.html`, stesso parametro `?live=`).

**Notte da stadio**: fondo verde campo con le linee di gesso in SVG a bassa
opacita' (cerchio di centrocampo, meta' campo, aree, bandierine), luce dei
riflettori in alto, strisce del taglio dell'erba appena percettibili. Palette
richiesta: campo `#1c6b34`/`#0f3d1f`, gesso `#f4f4ef`, oro `#f2c14e`, rosso
`#d7263d`, azzurro `#4cc9f0`. Ruoli come FantaAsta: **P giallo, D blu, C
verde, A rosso**, in pillole rotonde con la lettera. I numeri che contano
(crediti, PUOI SPENDERE ORA, TETTO, prezzo) sono in monospace con l'alone
luminoso del tabellone.

### Il flusso della serata (cinque tasti)

1. **cerca** — campo grande sempre a fuoco, typeahead su
   `/copilot/players?q=..&tutti=1`; ogni risultato mostra ruolo, nome,
   squadra, gol 25·26, q50, `⚽` se e' bomber e la nota dell'esperto su una
   riga. `↑ ↓` scorrono, **Invio** porta al banco il primo (o l'evidenziato).
2. **al banco** — card grande (q10/q50/q90, valore, gol 25·26, mercato,
   indisponibilita', nota dell'esperto per intero nel titolo) e, accanto,
   **CONSIGLIO** con il **TETTO in cifre da 56 px**, l'azione
   (RILANCIA / LASCIALO / DEVI PRENDERLO / AL MASSIMO / NON OFFRIRE, presa dal
   campo `azione`, mai dal testo), la riga
   «spendibili · indifferenza · cap bot · calore reparto», la riga scarsita'
   colorata (arancio da 0,5, rosso da 0,8 con il grido «SCARSO: puoi
   spingerti a N»), chi puo' superarti, `con lui / senza di lui` e
   `motivo_tetto`. Il consiglio si richiede a ogni cambio di prezzo e **ogni
   2 s finche' `stato_indifferenza == "in_calcolo"`**, in silenzio: il numero
   grande non sfarfalla.
3. **prezzo** — campo enorme con `−1 +1 +5 +10` e i tasti `+` e `−`.
   **Invio** nel campo del prezzo lo conferma e libera la tastiera.
4. **squadra** — le dieci **maglie** (SVG colorato, dieci colori fissi per
   indice) con **il numero 1…9 e 0 stampato sopra**: si sceglie col tasto o
   col click. Ogni maglia porta nome, crediti in oro, i pallini degli slot
   P/D/C/A, i gol in rosa e l'ultimo acquisto. La mia ha il marchio **IO**.
   Le squadre che non possono (reparto pieno, o cassa sotto il prezzo) sono
   spente **con il motivo scritto sotto** («attaccanti al completo»,
   «puo' al massimo 45»).
5. **AGGIUDICA** — bottone grande col martelletto (**Invio** quando prezzo e
   maglia ci sono): `POST /copilot/hammer` con `richiesta_id` univoco,
   colpo di martelletto animato, la maglia lampeggia verde, e se e' la mia
   parte il **GOOOL** a tutto schermo. Poi il fuoco torna alla ricerca.

**ANNULLA ULTIMO**: tasto `U` (a ricerca vuota) o bottone, armato — due colpi
entro 3 s, `POST /copilot/undo` con `richiesta_id`.

**CORREGGI QUALSIASI LOTTO**: si clicca un acquisto nel tabellone «ultimi
acquisti», in «tutti gli acquisti» o dentro la rosa di una maglia; si apre un
pannello con le dieci maglie, il prezzo e **TOGLI IL LOTTO**, e si conferma
con `POST /copilot/evento_modifica` (`indice` o `richiesta_id`, piu'
`richiesta_id_modifica`). **Degrado elegante**: se l'endpoint manca (404) o
gli acquisti non portano `indice`/`richiesta_id`, i bottoni restano spenti e
la pagina scrive «aggiorna il Copilota», con il rimedio del momento
(annulla l'ultimo e ribattilo). Alla prova di oggi il Copilota **ha gia'**
`/copilot/eventi` e `/copilot/evento_modifica`, e lo spostamento da una
maglia all'altra funziona.

**Altro**: setup del tavolo a dieci nomi con «IO» e crediti (il numero a
sinistra di ogni riga e' il tasto che sceglie quella squadra durante l'asta);
«sono io» dal bottoncino `io?` sulla maglia; **GOL IN ROSA** come classifica
di campionato (posizione, maglia, nome, barra, gol, media della lega);
**ULTIMI ACQUISTI** come tabellone; **IL MIO PIANO** ridotto (speso contro
previsto per reparto, slot, avviso di sforamento); **RIGORISTI ancora liberi**
per ruolo (solo `stato == "disponibile"`, click = va al banco); **TUTTI GLI
ACQUISTI** da `GET /copilot/eventi`, con ripiego sulle rose se manca;
pallino verde/rosso del collegamento e banner «server giu'»; `Esc` chiude
tutto.

Ogni campo che il server non manda diventa `—`: nelle prove **nessun NaN,
nessun undefined, nessuna eccezione in console**. In `localStorage` finiscono
solo i nomi del tavolo come comodita' del setup; niente di cui la serata
abbia bisogno.

---

## File toccati

| file | cosa |
|---|---|
| `viz/asta.html` | **nuovo**, 1 767 righe: tutta la pagina |
| `viz/index.html` | 3 punti (solo `Edit`): il bottone verde grande diventa **«🏟️ ASTA (pagina nuova)»** e apre `asta.html?live=<url>`; sotto resta **«📋 pagina classica (copilot)»** su `copilot.html?live=<url>`; dopo l'avvio/ripresa del Copilota `cpStart` porta su `asta.html` |
| `reports/asta_20260913/ui_asta_prova.py` | **nuovo**: le prove Playwright |
| `reports/asta_20260913/FIX_G.md` | **nuovo**: questo rapporto |

Non toccati: `scripts/f10_copilot.py`, `viz/copilot.html`, `tests/`, pack,
parquet, `f0b/f1/f2/f9/f12`, `viz/ponte_fantaasta.js`.

---

## Prove

```
PYTHONPATH=src python reports/asta_20260913/ui_asta_prova.py
-> VERDETTO: 58 prove, 0 fallite
```

Chrome headless 1366x768, contro due server veri avviati e fermati dallo
script: **8794** con `--resume data/copilot/prove/G_1.json` (copia troncata a
190 acquisti) e **8795** con `--resume data/copilot/prove/G_2.json` (vuota,
per il setup).

| gruppo | esito |
|---|---|
| setup: pannello da solo a tavolo vuoto, 10 nomi, «io» la decima, 500 crediti, 10 maglie, una sola marcata IO | 8 su 8 |
| testata: `PUOI SPENDERE ORA` == `state.spendibile.max_ora` (311), 10 maglie | OK |
| 1366x768 a banco vuoto: nessuno scorrimento orizzontale; ricerca, banco, consiglio, maglie, AGGIUDICA, annulla, gol in rosa, ultimi acquisti tutti sopra la piega | 9 su 9 |
| tabellone completo: 190 lotti da `/copilot/eventi`, prezzi numerici | OK |
| ricerca «malen» → Invio → **Malen al banco**, ricerca svuotata | OK |
| TETTO numerico (272 al primo colpo, 289 quando arriva l'indifferenza) uguale al `max_consigliato` del server, indifferenza consegnata in 2 s, riga «spendibili» presente | 5 su 5 |
| prezzo 150 → Invio → **tasto «5»** → la quinta maglia (MoreiraDiFame) si accende e AGGIUDICA e' pronto | 3 su 3 |
| **col banco pieno** (il caso vero): banco, consiglio, maglie e AGGIUDICA ancora sopra la piega, nessuno scorrimento orizzontale | 5 su 5 |
| Invio = martelletto: Malen nella quinta maglia a **150**, crediti **335 → 185**, acquisti **190 → 191**, Malen in cima al tabellone, la maglia mostra i crediti nuovi, il banco si svuota, il fuoco torna alla ricerca | 8 su 8 |
| correggi: il pannello si apre da un acquisto, ha le dieci maglie, **sposta Malen dalla quinta alla sesta** (`/copilot/evento_modifica`) | 3 su 3 |
| `U` due volte: il primo arma, il secondo annulla (**191 → 190**) | 2 su 2 |
| 1920x1080: nessuno scorrimento orizzontale, ricerca/maglie/AGGIUDICA sopra la piega | 4 su 4 |
| nessun NaN/undefined a schermo, nessuna eccezione di pagina, console senza errori | 3 su 3 |

### Immagini (scratch `w12/G/`)

| file | cosa mostra |
|---|---|
| `G_setup.png` | il setup delle dieci squadre, con il numero-tasto accanto a ogni nome |
| `G_tavolo_nuovo.png` | il tavolo appena apparecchiato (dieci maglie, nessun acquisto) |
| `G_banco_malen.png` | **Malen al banco** a 150, tetto 289, quinta maglia scelta, AGGIUDICA pronto |
| `G_dopo_martelletto.png` | subito dopo il martelletto: banco vuoto, Malen in cima al tabellone, crediti aggiornati |
| `G_correggi.png` | il pannello «correggi Malen»: dieci maglie, prezzo, togli il lotto |
| `G_1920.png` | la stessa pagina a 1920x1080 |
| `G_fine.png`, `G_pagina_intera.png` | la pagina a fine prova, viewport e pagina intera |

---

## Difetti trovati e corretti mentre si provava

* **G1 — le maglie mangiavano mezzo schermo.** L'SVG della maglia veniva
  disegnato senza la classe `mg` a cui puntava il CSS, quindi si allargava a
  tutta la card (90 px invece di 38) e, con un giocatore al banco, AGGIUDICA
  finiva sotto la piega a 1366x768. Corretto prendendo l'SVG come figlio
  diretto (`.mag > svg`) e aggiunta la rete di sicurezza: la colonna di mezzo
  ha `max-height: calc(100vh - 70px)` e **e' il consiglio a scorrere dentro il
  suo riquadro**, mai il martelletto a scendere.
* **G2 — prezzi «—» in «tutti gli acquisti».** `/copilot/eventi` parla la
  lingua del ledger (`player_id`, `prezzo`), il resto della pagina usa `id` e
  `price`. Ora si traduce in un punto solo.
* **G3 — l'avviso copriva il martelletto.** Il messaggio in basso al centro
  finiva sopra AGGIUDICA (e in alto sopra il numero grande del tetto):
  spostato nell'angolo in basso a destra.
* **G4 — il tabellone «ultimi acquisti» sforava di 17 px** a 1366x768:
  tetto d'altezza a 228 px, cosi' l'ultimo acquisto — quello che si corregge —
  resta sempre visibile.

## Da sapere prima di sedersi

* **L'ordine dei tasti e' prezzo → maglia**, come il flusso numerato: appena
  un nome va al banco il fuoco e' nel campo del prezzo (li' le cifre scrivono
  il prezzo), Invio lo conferma e libera la tastiera, e da quel momento
  `1…0` scelgono la maglia e Invio batte. Le maglie restano cliccabili in
  qualunque momento, anche mentre si scrive il prezzo.
* **`U` annulla solo a ricerca vuota**: se si sta scrivendo un nome la lettera
  va nel campo, come deve. La ricerca funziona per pezzi di nome («alen»
  trova Malen), quindi anche i nomi che cominciano per U si trovano.
* Il consiglio dice **fin dove puoi spingerti, non quanto devi offrire**: la
  riga `con lui / senza di lui` e' calcolata al tetto ed e' normale che a quel
  prezzo il piano senza di lui sembri migliore (difetto V2 del rapporto di
  verifica, non introdotto qui).
* La pagina classica resta a un click, in alto a destra («pagina classica») e
  nel menu: stessi endpoint, stessa sessione, stesso ledger.
