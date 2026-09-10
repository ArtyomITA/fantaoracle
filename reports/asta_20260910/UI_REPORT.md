# viz/copilot.html — lavoro per l'asta vera del 10/9/2026, ore 19:30

File toccato: **solo** `viz\copilot.html`
(1567 → 1938 righe; 448 righe aggiunte, 77 tolte).
Copia prima del lavoro: `data\_backup_fable_20260910\copilot.html`.
Server non toccato. Nessun altro file del progetto modificato.

## Che cosa è cambiato (funzioni e righe del file nuovo)

### CSS
| righe | cosa |
|---|---|
| 106-110 | `.team-row .slots{flex-wrap:wrap}` + `.slot-group{min-width:0}` → **fine della barra orizzontale**: con quote 3/8/8/6 i quadratini sforavano la colonna da 330 px |
| 176-205 | forchetta **compatta** (`.qrow/.q/.fork/.motivi/.meta` più bassi), `.q.val .n s` per il valore barrato |
| 207-236 | `.ind-box`, `.rett`, `.mkt`, `.esperto`, chip `ind/fuori/nopred/escl`, `.lot-act` |
| 238-247 | `.sez-rilanci`, `.riltog`, `.rilbody[hidden]` |
| 249-257 | marcatori `.mk` nei risultati, `.res-row.armato`, `.tutti-row` |
| 259-272 | `.escl-list/.escl-row`, `#copiaBanner`, `.trow .ico` |
| 288-320 | prezzo, `#advice`, `.hammer-title`, `.hammer-grid`, `.hbt` accorciati; `.results` 236→184 px |

### HTML
`#copiaBanner` (dopo `<header>`), casella `#tuttiChk` nella ricerca, `#sessOut` nel
riquadro DATI DI QUESTA SESSIONE, barra di aiuto: «↑↓ scegli · Invio conferma».

### JS
| righe | funzione | cosa |
|---|---|---|
| 829-834 | `onState` | chiama `renderCopiaBanner` e `renderSessione` |
| 909-918 | `renderCopiaBanner` (nuova) | **G**: banner giallo persistente `ripreso_da_copia` |
| 920-940 | `renderSessione` (nuova) | **H**: «valore ridotto per N indisponibili» + lista esclusi con «riammetti» |
| 1033-1127 | `scheduleSearch/doSearch/marcatori/renderResults` + tasti | **B**: `tutti=1`, marcatori IND/FUORI/ESCL/NO PREV, ↑↓ e Invio in due tempi |
| 1172-1213 | `adviceView` | **A(6)**: `escluso_manuale` → grigio «ESCLUSO DA TE»; `fuori_lista` → rosso; `obbligo` → verde «DEVI PRENDERLO fino a N» |
| 1243-1330 | `renderPiani` | tolta la variabile morta `vecchio`; usa `superato` → «superato: ricalcola», mostra `nota_vincolo` e `vincolo_attacco_rilassato`; guardia se non ci sono piani |
| 1332-1417 | `renderLot` | **C**: nuovo ordine (intestazione, indisponibilità, forchetta, rettifica/mercato/esperto, prezzo, consiglio, AGGIUDICATO A + griglia, azioni, motivi/meta, rilanci ripiegati) |
| 1419-1427 | `renderRilTog` (nuova) | apre/chiude «rilanci osservati» (restano nel DOM, solo nascosti) |
| 1429-1490 | `infoBanco/indispDi/renderInfoBanco` (nuove) | **A(1)-(4)**: chip arancione + testo fonte, riga «valore ridotto…», valore originale barrato, «mercato 10 sq./500 … riferimento, non tetto», riquadro «l'esperto (4/9)», chip «senza previsione» e «FUORI SERIE A (listone)»; `indisponibile` gestito sia stringa (players) sia oggetto (advice) |
| 1492-1512 | `escludiGiocatore` (nuova) | **A(5)**: POST `/copilot/escludi`, poi advice + poll + plan + invalidazione piani |
| 1514-1520 | `invalidaPiani` (nuova) | **D**: usata da `hammer`, `undo` ed escludi/riammetti |
| 1522-1534 | `assicuraMartelletto` (nuova) | **C**: `scrollIntoView` del pannello `#lot` solo se la griglia non è tutta in vista; non scorre se il fuoco è nella ricerca |
| 1536-1552 | `renderAdvice` | delega chip e riquadri a `renderInfoBanco`, richiama `assicuraMartelletto` |
| 1564-1611 | `firmaSquadre/renderBidGrid/renderBidTitle/renderUndoBid` | **E**: ricostruzione solo se cambia la firma, testi in loco; **F**: `catch` + `d.ok` su annulla rilancio |
| 1613-1624 | `registraRilancio` | **F**: `catch` con toast |
| 1632-1654 | `renderHammerGrid` | **E**: stessa firma, aggiornamento in loco di budget/max/`disabled` |
| 1732-1799 | `renderPlan` | **I**: ⚠ (title = testo dell'indisponibilità) e 💬 (title = nota dell'esperto) accanto ai nomi |
| 1801-1851 | `firmaTavolo/renderTeams` | **E**: righe del tavolo ricostruite solo al cambio di firma |
| 1858-1866 | `updateTeamPopover` | popover riscritto e riposizionato solo se la rosa mostrata cambia |

## Prove (Chrome headless di sistema, 1366x768, server di prova sulla 8794)

| script | che cosa prova | exit |
|---|---|---|
| `w1\repro_ui_2.py` | indisponibilità al banco | 0 |
| `w1\repro_ui_3.py` | martelletto sopra la piega | 0 |
| `w1\repro_ui_4.py` | piani invalidati dopo ANNULLA | 0 |
| `w1\repro_ui_6.py` | griglie stabili (stesso nodo dopo 5 s) | 0 |
| `w1\repro_ui_8.py` | rilancio fallito → toast | 0 |
| `w2\repro_ui_5_bis.py` (sostituisce `w1\repro_ui_5.py`) | Invio in due tempi con omonimi, frecce | 0 |
| `w2\repro_ui_7_bis.py` (sostituisce `w1\repro_ui_7.py`) | fuori lista cercabile e registrabile | 0 |
| `w2\repro_ui_nuovi_A5.py` | escludi/riammetti dal banco | 0 |
| `w2\repro_ui_nuovi_A6.py` | obbligo verde «DEVI PRENDERLO fino a N» | 0 |
| `w2\repro_ui_nuovi_B.py` | marcatori nella ricerca + ricerca in vista dopo il martelletto | 0 |
| `w2\repro_ui_nuovi_C.py` | misure a 1366x768 + ordine della scheda | 0 |
| `w2\repro_ui_nuovi_D.py` | piani invalidati (undo, escludi, riammetti) + `superato` + `vecchio` sparita | 0 |
| `w2\repro_ui_nuovi_G.py` | banner «ripreso dalla copia» (server dedicato sulla 8795) | 0 |
| `w2\repro_ui_nuovi_J.py` | console pulita in tutto il percorso | 0 |

Impalcatura comune: `w2\_com.py`. Uscite salvate in `w2\out_*.txt`, riepilogo in `w2\esiti.txt`.

### Due script di w1 sostituiti, e perché
- **`repro_ui_5.py`**: leggeva `C.sel.nome` subito dopo il primo Invio. Nel disegno
  nuovo, con più omonimi il primo Invio **non** sceglie (evidenzia), quindi lo script
  vecchio muore con `TypeError` invece di dare un esito. `repro_ui_5_bis.py` prova la
  regola nuova: primo Invio evidenzia, secondo conferma, ↓ passa all'omonimo.
- **`repro_ui_7.py`**: provava solo l'API (`/copilot/players` senza `tutti=1` continua,
  per disegno del server, a non mostrare i fuori lista), quindi non poteva uscire 0
  con nessuna modifica alla pagina. `repro_ui_7_bis.py` prova l'interfaccia: casella
  «anche fuori lista ed esclusi» → il giocatore si trova, si porta al banco marcato,
  i bottoni del martelletto sono attivi.

### Misure (repro_ui_nuovi_C, viewport 1366x768, McTominay al banco)
```
hammerGrid top=518 bottom=725 (viewport 768)   → tutta visibile, anche dopo 5 s di poll
scrollWidth/clientWidth: 1366/1366 a vuoto e con giocatore al banco
ordine: prezzo 627 < consiglio 679 < titolo 782 < griglia 807 < rilanci 1133
rilanci ripiegati=True, bottoni rilancio comunque nel DOM=True
```

### Console (repro_ui_nuovi_J)
Percorso: ricerca (frecce + doppio Invio), prezzo, rilancio e annulla rilancio,
selezione dalla rosa target, martelletto, ANNULLA, piani (calcolo, seconda scheda,
«se lo compro a»), escludi/riammetti, popover rosa avversaria, «chi chiamo», export.
**Zero errori di console** (`errori=[]`).

Immagini: `w2\ui_1366.png` (giocatore al banco), `w2\ui_piani.png` (pannello piani).

## Cose non fatte, e perché
- **Nessuna modifica al server** (era vietato). Due conseguenze restano lato server e
  non lato pagina: `/copilot/players` senza `tutti=1` continua a nascondere i fuori
  lista (la pagina ora offre la casella), e il conteggio «…e altri N» resta quello
  delle 80 righe che il server manda.
- **Chip «senza previsione»**: il codice c'è e la prova lo verifica, ma il bundle
  `data\copilot\eleggibilita_2026-27.json` è stato **rigenerato alle 06:25 da un altro
  processo** e adesso ha `attivi_senza_previsione = []`; il Copilota in memoria ne
  aveva ancora 7 (avviato prima). Se stasera il server riparte con il bundle nuovo,
  quei marcatori semplicemente non compariranno: non è un difetto della pagina.
  `repro_ui_nuovi_B.py` in quel caso non pretende il marcatore.
- **`vincolo_attacco_rilassato`**: mostrato quando il piano scelto lo dichiara, ma non
  provato end-to-end (sul pack corrente nessun piano lo alza).
- **`superato` dei piani**: provato facendo renderizzare `PI.dati` con il flag (la
  corsa vera fra calcolo e martelletto non è riproducibile a comando).
- **Invio**: cambia di poco il gesto abituale — con **un solo** risultato va dritto al
  banco come prima; con più risultati serve un secondo Invio (o ↓ e Invio). È l'unico
  modo per far uscire 0 la prova 5 senza registrare l'omonimo sbagliato.
- **Rosa target**: i nomi restano tagliati (colonne strette del pannello centrale, come
  prima); le icone ⚠/💬 hanno il testo nel `title`.

## Pulizia
Ledger di prova `data\copilot\prove\ledger_ui_8794.json` riportato a zero acquisti,
zero rilanci, zero esclusi. Server della 8794 fermato a fine lavoro; la 8795 usata
solo dalla prova G, che spegne il suo server da sola.
