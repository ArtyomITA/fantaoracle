# F — ispezione visiva e d'uso di viz/copilot.html (dopo il pannello rigoristi)

Server: `scripts/f10_copilot.py 2026-27 --porta 8794 --ledger data/copilot/prove/ledger_w7_fe.json`.
Chrome di sistema (`channel="chrome"`), headless, due larghezze: 1366x768 e 1920x1080.
Percorso: pagina vuota -> tavolo -> banco (normale / indisponibile / fuori lista / escluso)
-> 30 martelletti misti -> piani -> rigoristi -> popover di una rosa -> server giu' -> ripresa.
Backup prima delle modifiche: `data/_backup_fable_20260910/pre_rigoristi/copilot_pre_F.html`.

Copione: `scratchpad/w7/fe_ispezione.py`. Controprova: `scratchpad/w7/fe_dopo_correzioni.py`.
Esiti grezzi: `fe_esiti_1366.json`, `fe_esiti_1920.json`, `fe_correzioni.json`.

## Screenshot (24: 12 stati x 2 larghezze)

`fe_<stato>_<larghezza>.png` in `scratchpad/w7`, con
`<stato>` = vuota, tavolo, banco_normale, banco_indisponibile, banco_fuorilista,
banco_escluso, dopo30, piani, rigoristi, popover, server_giu, ripresa.
Giocatori usati: normale Malen (ROM, A), indisponibile McTominay (NAP, C, infortunio),
fuori lista Azon (con «anche fuori lista ed esclusi»), escluso a mano Calhanoglu (INT, C).
Martelletti: 30 su 30 andati a VENDUTO, `n_events` = 30 su entrambe le corse.
Rigoristi: 20 righe rese in pagina.
Controprova: `fe_corr_ticker_1366.png`, `fe_corr_ticker_1920.png`, `fe_corr_banner_1920.png`.

## Tabella dei difetti

| stato | larghezza | difetto | gravita' | corretto |
|---|---|---|---|---|
| tutti gli stati | 1366 e 1920 | pillola di ruolo attiva «tutti»: testo `var(--crust)` #11111b su `var(--surface0)` #313244, contrasto **1,49** (le altre pillole prendono il fondo colorato solo dopo un click, la «tutti» iniziale no) | media | si |
| rigoristi, piani, dopo30 (pagina scorsa) | 1366 e 1920 | `#tavolo` e' `position:sticky` ed e' piu' alto dello schermo (10 squadre): incollandosi in fondo alla colonna copre per intero il pannello **ULTIMI ACQUISTI**. Misurato a 1920: `#tavolo` [-357, 586], ticker [286, 586], `scrollY` 748. A 1366 il ticker non e' mai visibile | alta | si |
| server_giu | 1366 e 1920 | `#downBanner` a `top:12px` cade dentro l'intestazione: copre la pillola LIVE/«SERVER GIU'» e il riquadro «2026-27 STAGIONE» | media | si |
| tavolo, banco_*, dopo30, ... | 1366 e 1920 | `.trow .star.no` (il «·» delle riserve in ROSA TARGET) `var(--surface1)` #45475a su `var(--base)`, contrasto **1,92** | bassa | si |
| rigoristi (dopo «non lo voglio nel piano») | 1366 e 1920 | etichetta ambigua: un rigorista **escluso a mano** compare marcato «fuori lista» (Calhanoglu · INT). `stato_rigorista()` in `scripts/f10_copilot.py` accorpa `ELEGGIBILITA["esclusi"]` e `STATE["esclusi_manuali"]` nella stessa stringa | bassa | no — logica del server, fuori dal mandato di F |
| server_giu | 1366 e 1920 | console: `Failed to load resource: net::ERR_CONNECTION_REFUSED` mentre il server e' spento | — | no — atteso, e' il guasto simulato |
| vuota | 1366 e 1920 | «BUDGET A TESTA 500» senza unita' (crediti); stessa cosa per «se lo compro a [88]» nei piani | bassa | no — non tocco testi senza necessita' a 1 ora dall'asta |

### Controlli passati (nessun difetto)

| controllo | esito |
|---|---|
| scorrimento orizzontale (`scrollWidth > clientWidth`) | mai, in nessuno dei 12 stati, a 1366 e a 1920 |
| elementi fuori dalla colonna (`rect.right > .col.right`) | nessuno |
| elementi oltre il bordo destro del viewport | nessuno |
| testo troncato senza puntini | nessuno (i due casi visti — `.ind-box .src` e `#advice .sub` — sono `-webkit-line-clamp` voluti; `.fork .bar` non ha testo) |
| pannelli sovrapposti nella stessa colonna | solo il caso `#tavolo`/ticker qui sopra |
| griglia del martelletto sotto la piega a 1366 con giocatore al banco | mai: la scheda si porta in vista da sola, la griglia finisce a y ~707 su 768 |
| budget coerente fra IL TAVOLO e la griglia del martelletto | coerente in tutti gli stati (es. dopo30: Io 389 in testata, in IL MIO PIANO, in IL TAVOLO e nel martelletto) |
| console senza errori negli stati con il server vivo | pulita |
| rigoristi: barrato + nome del compratore, primo disponibile in verde grassetto, «mio» in giallo | reso corretto (vedi `fe_rigoristi_1366.png`) |

Falso allarme del copione, non della pagina: «banner non sparito dopo la ripresa (40 s)».
`wait_for_selector("#downBanner.hidden")` aspetta un elemento *visibile*, ma `.hidden` e'
`display:none`: la condizione non poteva avverarsi. Lo screenshot `fe_ripresa_*.png` mostra
il banner gia' sparito e la pillola LIVE tornata verde.

## Modifiche a viz/copilot.html, riga per riga

Solo CSS, nessuna logica. Backup: `data/_backup_fable_20260910/pre_rigoristi/copilot_pre_F.html`.

| riga | prima | dopo |
|---|---|---|
| 146 | `.rp.on{color:var(--crust);}` | `.rp.on{color:var(--crust); background:var(--subtext0);}` |
| 423 | `.trow .star.no{color:var(--surface1);}` | `.trow .star.no{color:var(--overlay0);}` |
| 435-437 | `#tavolo{position:sticky; top:12px;}` | commento di due righe + `#tavolo{position:sticky; top:12px; max-height:calc(100vh - 24px); overflow-y:auto;}` |
| 576-577 | `position:fixed; top:12px; left:50%; ...` dentro `#downBanner` | commento di una riga + `position:fixed; top:72px; left:50%; ...` |

## Controprova dopo le correzioni

| misura | prima | dopo |
|---|---|---|
| contrasto della pillola «tutti» attiva | 1,49 | **8,42** (1366 e 1920) |
| ULTIMI ACQUISTI coperto da IL TAVOLO | si | **no**: 1366 `#tavolo` [77, 821], ticker [835, 988]; 1920 `#tavolo` [77, 1020], ticker [1034, 1187] |
| banner del server giu' sopra l'intestazione | si (top 12, fondo intestazione 61) | **no**: banner top 72, fondo intestazione 61 |

## Prove di non regressione (tutte dopo le correzioni)

| prova | esito |
|---|---|
| `scratchpad/w1/repro_ui_2.py` | exit 0 |
| `scratchpad/w1/repro_ui_3.py` | exit 0 |
| `scratchpad/w1/repro_ui_6.py` | exit 0 |
| `scratchpad/w2/repro_ui_nuovi_C.py` | exit 0 |

Nota: `repro_ui_2/3/6.py` stanno in `scratchpad/w1`, non in `w2` (in `w2` ci sono solo
`repro_ui_5_bis`, `7_bis` e i `repro_ui_nuovi_*`).

## Chiusura

Server 8794 fermato, `data/copilot/prove/ledger_w7_fe.lock` rimosso, porta libera
(`/copilot/state` non risponde piu'). Ledger veri `data/copilot/ledger_*.json` non toccati.
