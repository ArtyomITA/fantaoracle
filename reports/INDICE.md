# Indice dei risultati — aggiornato 7 settembre 2026

Stato di ogni report e di ogni artefatto. Serve a non rileggere numeri
superati: molti report contengono conclusioni corrette al momento in cui sono
stati scritti e smentite dopo.

Legenda dello stato:

- **corrente** — vale oggi, prodotto con il codice attuale
- **superato** — conteneva numeri poi smentiti da una verifica successiva
- **diagnostico** — utile a capire, non a decidere (per esempio senza prezzi
  d'asta osservati)
- **non riproducibile** — prodotto con codice o dati non piu' ricostruibili

## Report

| File | Stato | Note |
|---|---|---|
| `LIVELLO2.md` | **corrente** | correzioni, dati nuovi, cubo TABELLINO implementato e misurato, verdetto appaiato del banco (§7: il cubo perde contro B' a informazione comparabile), residui, limiti |
| `LIVELLO3.md` | **corrente** | valutatore, ricerca su candidate, formulazione esatta, prezzo di indifferenza; i due difetti che rendevano identici i trattamenti del confronto d'asta |
| `CRITERI_L2_L3.md` | **corrente** | criteri congelati PRIMA degli esperimenti: contratto degli stati (§7), verdetto del banco (§3.7), tetti di indifferenza (§3.8), calibrazione dei gol (§7.6 e esito §7.6b) |
| `INDAGINE_LIVELLO2.md` | **superato**, con rettifiche in testa | il modello provato non conteneva Dixon-Coles e non aveva l'intercetta; la media della riga E era una scelta a posteriori; la metrica non poteva vedere la correzione. Verdetto rovesciato in `LIVELLO2.md` §4 |
| `LIVELLO0_E_1.md` | corrente per il Livello 0, **superato** per il panel | il panel descritto li' non realizzava il contratto: rifatto in `scripts/l2_costruisci_panel.py`, vedi `LIVELLO2.md` §3 |
| `INDAGINE_PUNTI_APERTI.md` | corrente salvo la cassa | la parte sulla dispersione dei prezzi e' superata: `ref_price_sd` e' informazione della stagione valutata e per il 2026/27 non esiste (`LIVELLO2.md` §8.1) |
| `INDICE.md` | corrente | questo file |
| `_archivio/CHECK_O3_O4.md` | corrente per O4, **superato** per O3 | i numeri di O3 sono stati rifatti dopo la correzione dell'anticipazione; O3c va riletto come diagnostico con informazione privilegiata |
| `_archivio/CHECK_20260906.md` | **superato** | la copertura "16-42%" misurava un modello che non gira in produzione |
| `_archivio/LIVELLO0.md` | **superato in parte** | validi i fix descritti; superate le conclusioni su copertura degli intervalli, doppio conteggio del premio ai nuovi e budget |
| `ARCHITETTURE_2.0.md` | corrente come proposta | il Livello 2 e' ora implementato in forma sperimentale; i numeri della proposta restano stime dei giudici, non misure |
| `ARCHITETTURE_E_OTTIMIZZAZIONI.md` | corrente per la Lista 1, superato dove cita la copertura | |
| `_archivio/ARCHITETTURE_raw_journal.md`, `_archivio/ARCHITETTURE2_raw_architetti.md` | materiale grezzo | esiti degli agenti, non conclusioni |
| `_archivio/REPORT_FINALE.md`, `_archivio/VERDETTO*.md`, `DIAGNOSI_ROSA.md`, `_archivio/RAGIONAMENTI_UMANI.md` | **non riproducibili** | prodotti ad agosto con codice precedente a tutte le correzioni di settembre; da leggere come storia |

## Artefatti

| Percorso | Stato | Note |
|---|---|---|
| `data/packs/pack_*.pkl` | corrente | cio' che leggono bot e Copilota. **Non toccati** dal Livello 2 |
| `data/processed/l2_partite.parquet` | **corrente** | 3040 partite, 8 stagioni, giornata + risultato + xG + provenienza |
| `data/processed/l2_panel_*.parquet` | **corrente** | panel giocatore x partita con universo atteso, cinque stati di convocazione, provenienza |
| `data/processed/panel_*.parquet` | **superato** | prodotto da `f14_build_panel.py`, che non realizzava il contratto |
| `data/raw/calendario/2026-27/` | **corrente** | pagine grezze del calendario con impronte + CSV verificato |
| `data/raw/understat/partite_*.csv` | **corrente** | risultati e xG per partita, 2019-2026 |
| `data/raw/transfermarkt/_download/game_lineups.csv.gz`, `game_events.csv.gz` | **corrente** | formazioni ed eventi storici (2013-2025 e 2012-2025) |
| `data/l2/` | **corrente** | banchi, previsioni conservate, cubo salvato, dispersione, ablazione |
| `data/l2/banco_verdetto_*.csv` | **corrente** | differenze appaiate con intervallo dei quattro generatori (criteri §3.7) |
| `data/l2/g1/` | **corrente** | esperimento G1 sulla calibrazione della distribuzione dei gol: esito inconcludente, resta il comportamento attuale |
| `data/l3/` | **corrente** | manifesto della sessione, pilota, tetti di indifferenza, confronto d'asta |
| `_archivio/` | **archivio** | i report qui sopra marcati superati o non riproducibili sono stati spostati in `reports/_archivio/` il 10 settembre. Nessuna cancellazione: `_archivio/LEGGIMI.md` dice di ognuno perché è lì |
| `data/istantanee/_archivio/` | **corrente** | archivio per impronta: contiene i byte, non solo le impronte |
| `data/istantanee/20260907_014307_e6b11750/` | **corrente** | stato congelato prima dei fix del 7/9 |
| `data/istantanee/20260906_2102/` | archivio | formato vecchio (solo impronte per il grezzo) |
| `data/baseline_20260905/` | archivio | stato precedente ai fix di settembre |
| `data/livello0/` | corrente | prove del Livello 0 e dei check |
| `data/tournament_fix/`, `data/sample_logs/` | archivio, in uso | replay del menu |
| `data/tournament/`, `data/tournament_mod/`, `data/counterfactuals/` | **non riproducibili** | prodotti col codice di agosto |
| `data/live_logs/` | corrente | partite di allenamento contro bot, non aste reali |
| `data/copilot/ledger_*.json` | diagnostico | prove di digitazione, non aste vere |
| `data/_cestino_20260906/` | eliminabile | `nul` e output rigenerabili, spostati il 6/9 e non cancellati |

## Come rifare le misure

| Cosa | Comando |
|---|---|
| istantanea, elenco, ripristino | `python scripts/f16_istantanea.py [--crea\|--elenco\|--ripristina ID DIR]` |
| calendario della stagione in corso | `python scripts/l2_scarica_calendario.py 2026-27` |
| risultati e xG per partita | `python scripts/l2_scarica_understat.py 2019 ... 2026 --riscontro 2026-27` |
| tabella unica delle partite | `python scripts/l2_prepara_partite.py` |
| panel giocatore x partita | `python scripts/l2_costruisci_panel.py [--verifica]` |
| modello di partita, fuori campione | `python scripts/l2_banco_partita.py --boot 2000` |
| fedelta' del cubo | `python scripts/l2_genera_cubo.py 2024-25 --sims 30` |
| cubo per l'asta (solo giornate future) | `python scripts/l2_genera_cubo.py 2026-27 --as-of 2026-09-11 --solo-future --salva` |
| quattro generatori a confronto, con verdetto | `python scripts/l2_banco_confronto.py 2024-25 --sims 30` |
| calibrazione della distribuzione dei gol (G1) | `python scripts/g1_calibrazione_gol.py` |
| tetti di indifferenza del piano | `python scripts/l3_tetti.py --piano data/l3/pilota/rosa_migliore.json` |
| pilota del Livello 3 | `python scripts/l3_pilota.py --stagione 2026-27` |
| confronto d'asta a quattro trattamenti | `python scripts/l3_confronto_asta.py --repliche 22 --scenari 40 --piano data/l3/pilota/rosa_migliore.json --tetti data/l3/asta/tetti_2026-27.json` |
| dispersione dei prezzi | `python scripts/l2_dispersione_prezzi.py` |
| ablazione di `quot_fs_sett` | `python scripts/l2_ablation_quot.py --semi 5` |
| tutti i test | `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python -m pytest tests/ -q` |
| modello valore, fuori campione | `python scripts/indagine/backtest_valore.py --tag X --k 2` |
| baseline del banco vecchio | `python scripts/f15_banco.py` |
| cassa e obiettivi persi in asta | `python scripts/indagine/check_o3_cassa.py --aste 20` |
| combinazione dei quantili di prezzo | `python scripts/indagine/check_o4_quantili.py` |
| confronto sintetico del piano | `python scripts/f13_validate_plan.py 2025-26` |

## 10 settembre 2026 — notte pre-asta (Fable)
- `STATO_LIVELLI_20260910.md` — corrente: cinque colonne dopo la rigenerazione del pack; due prove L3 rosse spiegate.
- `livelli_20260910/L1..L5.md` — corrente: un rapporto per livello (agenti in sola lettura), criteri scritti prima.
- `asta_20260910/` — diagnostico: caccia ai difetti del Copilota (consigli, dati, persistenza, UI), regole vs codice, simulazione politiche prezzo (36 semi), rapporto UI, screenshot 1366x768, script del confronto pack.
