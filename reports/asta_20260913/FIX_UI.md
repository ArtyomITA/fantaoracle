# FIX UI — pagina del Copilota per l'asta del 13/9

File toccato: `viz/copilot.html` (unico). Nuovi: `reports/asta_20260913/ui_prova.py`,
questo rapporto, e lo stub di prova in
`C:\Users\ADMINI~1\AppData\Local\Temp\claude\E--claudecode-pesante\5ff20539-b495-4ac4-bed4-79eabbf8a8b7\scratchpad\w11\U\stub.py`.

Tutto additivo. Ogni campo nuovo del contratto e' letto con `num`/`d0`/`d1`
(righe 1041-1051): se il Copilota non lo manda si scrive «—», mai un NaN, mai
un'eccezione. Provato davvero contro un server senza i campi (vedi PROVE).

---

## Cosa e' cambiato, riga per riga

### Foglio di stile — blocco nuovo in fondo, righe 727-829
Commento di testata alle righe 727-733. Dentro:
- `header{position:sticky; top:0; z-index:60}` (737) — «puoi spendere ora» non
  sparisce scorrendo. Conseguenza obbligata: `#tavolo{top:76px; max-height:calc(100vh - 88px)}`
  (740), altrimenti il pannello appiccicato finiva sotto i numeri di testata.
- `.hstat.spend` (741-744), `.plan-stats` a cinque colonne (746-749),
  `.pt td.sp` in rosso e `.sforo` (751-752).
- `.res-row` con la colonna gol (755-756), `.mk.bmb` (757), `.ord-pills`/`.op` (758-769).
- `.q.gol`, `.chip.bomber`, `#lotMeta`, `#advice .adv-line/.adv-scar/.adv-conf/.adv-motivo` (771-789).
- `#scarsita` e `.sc-*` (790-802), `#golRosa` e `.gr-*` (804-826), `.team-row .head .tgol` (827-828).

### U1 — «PUOI SPENDERE ORA»
- Riquadro nuovo in testata: riga **841** (`#hSpendibileBox` / `#hSpendibile`),
  riempito in `renderHeader` righe **1182-1191** da `state.spendibile.max_ora`.
  Il `title` porta crediti e slot.
- Quinto riquadro in `#planStats`: `renderPlan` righe **2260-2266** (calcolo di
  `altri`) e **2273-2274** (riquadro «su un solo giocatore, tenendo 1 per gli
  altri N slot»). Senza `spendibile` il numero e' «—» e N viene dagli slot
  liberi del piano.
- `#lotMeta` spostato SOPRA `#advice` (riga **1884**, prima stava dopo i motivi)
  e ridotto a «max legale · slot liberi R» (`renderAdvice`, righe **2057-2061**).
  Quel che portava prima (calore, concorrenti) non e' perso: sta nel riquadro
  del consiglio.

### U2 — banco e consiglio
- `adviceExtra(a)`, righe **1583-1623**, chiamata da `renderAdvice` riga **2055**.
  Produce, nell'ordine:
  - `spendibili N · cap bot N · indifferenza N|«in calcolo…»|«n/a» · calore reparto ×N`;
  - riga scarsita' `N bomber per M squadre con slot e cassa · quota Q`, arancio
    da 0,5, rossa da 0,8 con «SCARSO: vai fino a {max_consigliato}»;
  - `con lui a P: V pt · G gol | senza: V pt · G gol` (solo se il server manda
    tutti e due i rami);
  - «possono superarti…» / «nessuno puo' superarti» (veniva da `#lotMeta`);
  - `motivo_tetto` in piccolo.
  Il numero grande resta `max_consigliato`: `adviceView` non e' stato toccato.
- Richiesta silenziosa mentre l'indifferenza si calcola: `requestAdvice(delay, silenzioso)`,
  righe **1523-1545**; nuovo timer `C.indTimer` (riga 1060) azzerato anche in
  `clearLot` (riga 1508). Con `stato_indifferenza == "in_calcolo"` la pagina
  richiede lo stesso giocatore allo stesso prezzo ogni 2 s **senza** il velo
  grigio e senza l'animazione: nessuno sfarfallio (provato, vedi PROVE).
- `.qrow`: riquadro «gol 25 · 26» alla riga **1867**, riempito in
  `renderInfoBanco` righe **1974-1981** con `gol_tot_2025 · gol_tot_2026`;
  distintivo «⚽ BOMBER» sotto l'etichetta e chip «⚽ bomber» accanto al nome.

### U3 — lista dei risultati
- Colonna gol (`gol_tot_2025`, «ND» se manca) righe **1432-1434**; distintivo ⚽ fra i
  marcatori, riga **1417**.
- Pillole «ordina: valore | gol | misto» dentro `#rolePills`, righe **868-873**;
  logica alle righe **1356-1406** (`ORDINA`, `ordinaDefault`, `riordinaRisultati`,
  `renderOrdPills`), ascoltatore righe **1479-1488**. Criteri identici al contratto B.
  La scelta sta in `localStorage["ordinaLista"]`; senza scelta esplicita il
  reparto comanda (A e C → gol, altrimenti valore). Con del testo nel campo di
  ricerca l'ordine resta quello di pertinenza del nome, come prima.

### U4 — pannello GOL IN ROSA
- Pannello nuovo `#golRosa` nella colonna destra, SOPRA ULTIMI ACQUISTI: righe
  **954-957**. Codice: `GR`, `caricaGolRosa`, `renderGolRosa`, righe **2585-2632**;
  si ricarica quando cambia `n_events` (o `my_index`), righe **1127-1128**.
- Dieci righe «pos · nome · tot 2025 (di cui N rig) · A/C · 2026», barra
  proporzionale al massimo, la mia riga con classe `.mia` (bordo giallo), il
  pedice «N senza storico Serie A» dove `senza_dato > 0`, e in fondo la media
  della lega. Senza la rotta: «questo Copilota non manda ancora i gol in rosa».

### U5 — riga SCARSITA'
- `<div id="scarsita" hidden>` sotto il pannello del banco, riga **885**;
  `renderScarsita`, righe **2634-2659**, chiamata da `onState` (riga 1122).
- «ATTACCO: N bomber per M squadre in gara — STRETTO/OK» e lo stesso per il
  centrocampo, piu' i primi tre bomber con gol e q50. STRETTO quando
  `rapporto < 1` (in mancanza del campo: `bomber_pool < squadre_in_gara`).
  Senza `state.scarsita` il riquadro resta nascosto: niente rumore.

### U6 — IL MIO PIANO
- Colonna «speso finora» in rosso (foglio di stile riga 752).
- Riga «⚠ hai sforato {reparto} di {n} crediti» quando speso > previsto × 1,25 e
  previsto > 0: `renderPlan`, righe **2280-2298**.

### U7 — rigoristi e tavolo
- `pieghevole("rigoristi", "rigBody", true)` riga **2723** (aperto di default;
  chi l'aveva gia' chiuso a mano se lo ritrova come l'aveva lasciato, la scelta
  vive in `localStorage`).
- `teams[i].gol_2025` accanto al nome nel TAVOLO, riga **2492**, e dentro la
  firma del tavolo (riga **2463**) perche' il ridisegno scatti quando cambia.

### U8 — ordine dei ruoli casuale
Cercate in tutta la pagina le formule che davano per scontato P→D→C→A
(«prima i portieri», «si comincia dai…», «P, D, C, A»): **nessuna**.
`ROLE_ORDER` resta solo un ordine di presentazione delle colonne e delle
tabelle, non una previsione di chiamata. «CHI CHIAMO?» chiede il ruolo, non lo
impone.

---

## Prove — `reports/asta_20260913/ui_prova.py`

Chrome headless 1366×768, tre bersagli in una passata sola:

| bersaglio | porta | cos'e' |
|---|---|---|
| `stub` | 8794 | `w11/U/stub.py --scarso`: risposte vere dell'evento 190 (w10/A3) piu' i campi nuovi del contratto, con il caso di scarsita' del prototipo A2 (T1) |
| `vecchio` | 8796 | lo stesso stub con `--vecchio`: i campi nuovi tolti e `/copilot/gol_rosa` in 404 |
| `vero` | 8795 | `scripts/f10_copilot.py --resume data/copilot/prove/U_1.json` (copia TRONCATA a 190 acquisti del ledger del 10/9; l'originale non e' stato aperto in scrittura) |

Comando: `python reports/asta_20260913/ui_prova.py` (dalla radice).

**Esito: 47 prove, 0 fallite.**

Le prove chieste, una per una:
- `#hSpendibile` == `spendibile.max_ora` → **311** su stub e su server vero; «—» sul vecchio.
- `#advice` per Malen a 150 contiene «spendibili» e il numero `max_consigliato`
  (302 sullo stub, 244 sul server vero, 260 sul vecchio). OK su tutti e tre.
- `#advice.getBoundingClientRect().bottom` con Malen al banco: **656** (stub),
  **654** (vero), **549** (vecchio) — sotto 768. Vale con la pagina come la
  lascia `assicuraMartelletto`, che porta la scheda AL BANCO in cima appena si
  sceglie un giocatore: e' il comportamento gia' esistente, non e' cambiato.
- `#golRosa` ha 10 righe e una sola con classe `.mia`: OK su stub e su vero.
- Pillole: in modalita' «gol» con ruolo A il primo e' **Martinez L., 17 gol**
  (≥ 14) mentre per valore il primo e' Malen: l'ordine cambia davvero.
- Nessun errore in console (escluso il 404 dell'icona, e sul bersaglio
  «vecchio» il 404 atteso di `/copilot/gol_rosa`), nessuna eccezione di pagina,
  nessun «NaN»/«undefined»/«[object Object]» nel testo, su tutti e tre.
- Contro un Copilota senza i campi nuovi: tutto «—», riga scarsita' nascosta,
  colonna gol «ND», pannello dei gol con l'avviso. Nessuna eccezione.

Prova in piu', non chiesta ma utile: mentre `stato_indifferenza` e' «in_calcolo»
il riquadro del consiglio **non prende mai** la classe `wait` (0 giri col velo
grigio su entrambi i bersagli con i campi nuovi): il numero compare da solo.
Sul server vero l'indifferenza e' arrivata in **2 s**.

Immagini in `w11/U/`:
`ui_stub_banco.png` (il caso T1: tetto 302, riga rossa «SCARSO»),
`ui_stub.png`, `ui_stub_intera.png`,
`ui_vecchio_banco.png` (tutto «—»), `ui_vecchio.png`, `ui_vecchio_intera.png`,
`ui_vero_banco.png`, `ui_vero.png`, `ui_vero_intera.png`.

Server fermati alla fine dallo stesso script (`finally`); verificato che sulle
porte 8794/8795/8796 non resta niente in ascolto. Mai toccate 8770 e 8899, mai
aperti i ledger veri se non in lettura.

---

## Cosa ho visto del server vero (non e' roba mia, ma serve saperlo)

Alle 13/9 il Copilota vero **ha gia'** `state.spendibile`, `state.scarsita`,
`teams[].gol_2025`, `/copilot/gol_rosa`, i campi gol nei `player_info` e i campi
nuovi di `/copilot/advice`: la pagina li ha mostrati tutti senza ripieghi.

Due numeri da far vedere al fixer del server, letti dalla pagina sullo stato a
190 eventi (10/9):

1. **La riga di scarsita' dice «11 bomber per 9 squadre in gara — OK».** Con
   `bomber_rimasti = 11` e `squadre_contendenti + 1 = 10`, `quota_scarsita` va a
   zero e il premio di scarsita' non scatta: per Malen `max_consigliato` (244)
   e' esattamente il prezzo di indifferenza, senza nessuna aggiunta. Il
   prototipo A2 (T1) partiva invece da **1** bomber rimasto e arrivava a 302.
   La differenza sta quasi tutta nel secondo ramo di `e_bomber`: con tre sole
   giornate del 2026, `gol_tot_2026 / pres_2026 * 38 >= 10` promuove a bomber
   chiunque abbia segnato una volta in tre partite. Vale la pena guardarlo prima
   di stasera: e' il ramo che decide se il tetto sale o no.
2. `scarsita.C` risponde «0 bomber per 0 squadre in gara»: a 190 eventi i
   centrocampi sono tutti pieni, quindi e' giusto — ma la pagina scrive «OK» in
   verde anche quando la gara non c'e' proprio. Se al fixer del server sembra
   meglio, basta che `squadre_in_gara == 0` arrivi con `rapporto: null` e la
   riga si puo' spegnere; oggi non la spengo perche' il contratto non lo dice.

Nessuna delle due e' una modifica alla UI: sono osservazioni.

---

## Ripristino
`viz/copilot.html` originale sta in `data/_backup_fable_20260913/copilot.html`:
per tornare indietro basta ricopiarlo.
