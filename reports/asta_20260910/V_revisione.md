# V — revisione finale (dopo R, F, S)

Eseguita 2026-09-10, 17:21-17:55. Nessun file del progetto modificato: solo letture,
prove e artefatti sotto `scratchpad/w7`.

## 1. Impronte e diff

`scratchpad/w7/nuove_impronte_asta.json` — sha256 delle stesse 26 voci di
`scratchpad/w4/impronte_asta.json`. Nessuna voce mancante.

| esito | voci |
|---|---|
| identiche | 23 |
| diverse | 3: `scripts/f10_copilot.py`, `viz/copilot.html`, `tests/test_copilot_asta.py` |

Tutte e tre sono fra le differenze ammesse. In particolare restano **identici**
`data/copilot/ledger_1788290734.json`, `data/copilot/ledger_1788548783.json`,
`data/packs/pack_2026-27.pkl`, `data/copilot/eleggibilita_2026-27.json`,
`data/copilot/note_esperto_2026-27.json`, `src/fantabot/*`, gli altri script.

Nuove impronte dei tre file cambiati:

| file | sha256 (nuovo) |
|---|---|
| scripts/f10_copilot.py | `a2e1bccfed79c5e9f804d1247e87349d493108a65fc3126fd3b5e27718289c1c` |
| viz/copilot.html | `597b3f8ae80e6f15b887e7c871d54057d5c37db5101ec8b0c0327f321cc64536` |
| tests/test_copilot_asta.py | `89c357d1cb17aab2a8ceb90b023bb7caad98778980f2016aeed2dd0013e017c4` |

### Diff contro `data/_backup_fable_20260910/pre_rigoristi/`

| diff | file | righe | hunk | contenuto |
|---|---|---|---|---|
| `V_f10.diff` | f10_copilot.py vs backup | +148 / -0 | 5 | solo rigoristi (R) |
| `V_copilot_totale.diff` | copilot.html vs `copilot.html` (pre-R) | +96 / -4 | 8 | 4 hunk rigoristi (R) + 4 hunk CSS (F) |
| `V_copilot_soloF.diff` | copilot.html vs `copilot_pre_F.html` | +7 / -4 | 4 | solo CSS/commenti (F) |
| `V_test.diff` | test_copilot_asta.py vs backup | +35 / -0 | 1 | un test nuovo |

Contenuto verificato riga per riga:

- **f10**: docstring dell'endpoint, `import csv`, `from fantabot.market_adjust import norm as norm_mercato`,
  chiamata `costruisci_rigoristi()` in coda a `prepara_pack`, blocco nuovo
  `SIGLE_MERCATO / COLONNE_* / RIGORISTI / _chiave_cognome / costruisci_rigoristi /
  stato_rigorista / rigoristi_ora`, rotta `GET /copilot/rigoristi`. **Nessuna riga rimossa**,
  nessuna funzione preesistente toccata.
- **copilot.html (R)**: blocco CSS `#rigOut/.rig-*`, `<section class="panel" id="rigoristi">`
  dopo «PIANI CON BOMBER DIVERSI», 3 righe in `onState` (firma `n_events/esclusi_manuali`),
  blocco JS `RIG / caricaRigoristi / classeRigorista / marcatoreRigorista / renderRigoristi`
  + listener di click. Nessuna rimozione.
- **copilot.html (F)**: 4 sole regole CSS — `.rp.on` (+`background`), `.trow .star.no`
  (`--surface1` -> `--overlay0`), `#tavolo` (+`max-height:calc(100vh - 24px); overflow-y:auto`),
  `#downBanner` (`top:12px` -> `top:72px`), piu' 3 righe di commento. Nessuna logica.
- **test**: solo `test_rigoristi_stato_segue_il_martelletto`.

**Verdetto 1: conforme.** Le differenze sono solo rigoristi (R) e CSS/testo (F).

## 2. Prove

| prova | atteso | osservato |
|---|---|---|
| `pytest tests/test_copilot_asta.py tests/test_rettifica_indisponibili.py -q -p no:cacheprovider` | verde | **19 passed, 1 skipped** in 7,05 s (13 + 7 raccolti; skip preesistente `test_senza_previsione_registrabili`) |
| `verifica_f1f2.py` | 32/32 | **32/32**, exit 0 |
| `verifica_f5bis.py` | 23/23 | **23/23**, exit 0 |
| `verifica_f5_asta.py` | 24/24 | **24/24**, exit 0 |
| `verifica_f6.py` (server 8791, `data/copilot/prove/ledger_w7_rev.json`) | 25/25 | **25/25**, exit 0 |

Server 8791 fermato, `ledger_w7_rev.lock` rimosso, porta verificata libera.
Log: `scratchpad/w7/srv_rev_8791.log`.

## 3. Asta intera rigiocata dalla pagina (stress)

Copia di `scratchpad/w6/asta_intera.py` in `scratchpad/w7/asta_stress.py`, identica salvo
ledger (`data/copilot/prove/ledger_w7_stress.json`) e nome del log — il ledger nell'originale
e' scritto nel sorgente e lo script del compito W6 non e' un file di progetto.

Comando: `python asta_stress.py --lotti 120` (server 8794 avviato dallo script).

| misura | esito |
|---|---|
| EXIT | **0** |
| anomalie | **0** |
| lotti | 119 (120 riscalato sulle quote P/D/C/A: 14/38/38/29) |
| `n_events` finale | 119, pagina e `/copilot/state` coincidenti a ogni lotto |
| console del browser | vuota (`"console": []`) |
| rosa mia | P 3, D 8, C 8, A 6 — quote esatte, budget 166 |
| furti forzati / fuori lista | 7 / 2 |
| piani a meta' blocco | D 1,2 s (7 schede), C 1,0 s (5 schede) |
| durata | 1,3 min |
| porta 8794 dopo la corsa | libera (lo script la controlla e la libera) |

Esito grezzo: `scratchpad/w7/asta_stress_out.txt`, `asta_stress_log.jsonl`.

**Verdetto 3: conforme**, con la riserva sotto (i guasti oltre il lotto 150 non vengono raggiunti).

## 4. Campioni rieseguiti

### R — `scratchpad/w7/V_campioni_R.py` (in-process, nessun server), 3/3

| campione | esito | osservato |
|---|---|---|
| `/copilot/rigoristi`: 20 squadre, 0 non agganciati | **RIPRODOTTO** | 20 squadre, 60 rigoristi + 60 punizioni, 0 non agganciati, fonte `rigoristi_20260910.csv` |
| BOL e LEC: `rigorista_1` indisponibile, primo disponibile = il secondo | **RIPRODOTTO** | BOL Orsolini `indisponibile` -> Bernardeschi; LEC Geubbels `indisponibile` -> Stulic |
| hammer ATA `rigorista_1` a un avversario, poi undo | **RIPRODOTTO** | Scamacca (2137) -> `venduto a T1`, `primo_disponibile` = 6435 (Krstovic); dopo undo torna `disponibile` e primo = 2137 |

### F — `scratchpad/w7/fe_dopo_correzioni.py` rieseguito, 3/3

| campione | atteso dal rapporto F | osservato |
|---|---|---|
| contrasto della pillola «tutti» attiva | 8,42 | **8,42** a 1366 e a 1920 |
| ULTIMI ACQUISTI coperto da IL TAVOLO | no; 1366 tavolo [77,821] ticker [835,988]; 1920 tavolo [77,1020] ticker [1034,1187] | **identico**, `coperto:false` a entrambe |
| banner «server giu'» sopra l'intestazione | no; banner top 72, fondo intestazione 61 | **72 / 61, `copre:false`** |

### S — `scratchpad/w7/V_campioni_S.py` (solo R01 e R25, stessi semi: SEED 1, `seed_scenari` 1001, 40 scenari), 3/3

| campione | atteso dal rapporto S | osservato |
|---|---|---|
| R01: punti medi 3199, sd 71, costo q50 500, 3-4-3, titolari | come in tabella | media **3199,3**, sd **71,1**, costo **500**, modulo **3-4-3**, titolari identici (Mandas, Kalulu, Pavlovic, Solet, Zaccagni, Vlasic, Ekkelenkamp, Frattesi, Malen, Raimondo, Colombo) |
| R25: punti medi 3210, diff +11, SE appaiato 8, «serio» si | come in tabella | media **3210,3**, diff **+11,0**, SE **7,8**, serio **si** |
| scenari comuni: il punteggio non dipende dallo stato di `rng` | implicito nel metodo | **confermato**: stessa rosa con `Random(1)` e `Random(999)` -> differenza massima 0,000000 (quindi il riuso della cache e l'ordine delle rose non alterano i punti medi; `rng` entra solo in `p_first`) |

## 5. Stato della macchina

| controllo | esito |
|---|---|
| processi python di fantabot | **nessuno** (restano solo `teams_scribe/mcp_server.py`, i proxy `mcp-proxy-for-aws` e un `deploy.py`, estranei al progetto) |
| porte 8770 / 8791 / 8794 / 8899 | **tutte libere** (nessun LISTENING, nessuna risposta HTTP) |
| `.lock` in `data/copilot/prove/` | **nessuno** |
| `.pytest_cache` sotto il progetto | **nessuna** |
| ledger in `data/copilot/` | **solo** `ledger_1788290734.json` e `ledger_1788548783.json`, sha256 invariati |

## 6. Verdetto finale

**Le tre consegne (R, F, S) sono verificate e coerenti con i rapporti.** Nessuna regressione:
20 prove automatiche verdi, 104 controlli delle quattro verifiche (32+23+24+25), un'asta di 119
lotti giocata dalla pagina senza anomalie e con console pulita. Nessun file fuori dai tre ammessi
e' cambiato; i ledger veri sono intatti.

Restano aperte le anomalie minori elencate sotto: nessuna e' bloccante per l'asta delle 19:30.

## 7. Anomalie aperte (nessuna bloccante)

| # | anomalia | gravita' | dettaglio |
|---|---|---|---|
| 1 | `python -m pytest` senza percorsi espliciti non raccoglie piu' | media | il backup `data/_backup_fable_20260910/pre_rigoristi/test_copilot_asta.py` sta dentro l'albero, il progetto non ha `pytest.ini`/`pyproject.toml` con `testpaths`, e nella cartella di backup e' rimasto `__pycache__/test_copilot_asta.cpython-312-pytest-9.1.1.pyc`. Riprodotto: `pytest tests/test_copilot_asta.py data/_backup_fable_20260910/pre_rigoristi/test_copilot_asta.py --collect-only` -> `import file mismatch ... Interrupted: 1 error during collection`. Non toccato (V non modifica file del progetto). Rimedio in 10 s: rinominare il backup in `test_copilot_asta.py.bak` e cancellare quel `__pycache__` |
| 2 | lo stress a `--lotti 120` non arriva ai guasti oltre il lotto 150 | bassa | `asta_intera.py` prevede uccisione del server e ripresa dopo il lotto 150 e altri guasti fino al 175: con 119 lotti restano provati solo undo doppio (60) ed esclusione/riammissione (100/110). La ripresa dopo caduta resta coperta da `fe_ispezione.py` (stati `server_giu`/`ripresa`) e da `verifica_f1f2.py` |
| 3 | un rigorista escluso a mano e' marcato «fuori lista» | bassa | gia' segnalata da F: `stato_rigorista()` accorpa `ELEGGIBILITA["esclusi"]` e `STATE["esclusi_manuali"]` nella stessa stringa. Etichetta, non comportamento |
| 4 | battitori di punizioni non mostrati in pagina | bassa | gia' segnalata da R: l'endpoint restituisce `punizioni` e `primo_disponibile_punizioni`, il pannello mostra solo i tre rigoristi |
| 5 | avvio del Copilota piu' lento di ~1,2 s | bassa | misurato ora: `import fantabot.market_adjust` costa **1,25 s** (tira dentro pandas). Prezzo pagato una volta all'avvio, non durante l'asta |
