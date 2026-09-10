# Compito B — L4 (tre prove minime) + L1 (prova decisiva)

10/9/2026. Percorso d'asta **non toccato**: 26 impronte su 26 di
`scratchpad/w4/impronte_asta.json` verificate identiche a fine lavoro
(RIPRODOTTO, sha256). Nessun server, nessun addestramento di prezzo/valore,
nessun push.

Etichette: **RIPRODOTTO** = comando eseguito ora; **OSSERVATO NEL CODICE** =
letto con riga; **IPOTESI** = dichiarata come tale.
Criteri di accettazione scritti prima dei numeri in
`scratchpad/w4/criteri_prima_B.md`.

---

## Parte 1 — L4, tre prove minime (solo test)

File creati, tutti nuovi, nessun file esistente modificato:

- `tests\test_l4_contratto_prezzo.py`
- `tests\test_l4_non_anticipazione_prezzo.py`
- `tests\test_l4_copertura_registrata.py`

### Comando ed esito (RIPRODOTTO)

```
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTHONIOENCODING=utf-8 OMP_NUM_THREADS=4 \
  python -m pytest tests/test_l4_*.py -q -p no:cacheprovider
```

Riga finale: **`10 passed, 5 xfailed in 4.36s`** (15 prove, zero skip, zero
fallimenti; pytest 9.1.1, Python 3.12.6). Suite intera dopo l'aggiunta:
**605 prove collezionate** (`pytest tests/ -q --collect-only`), 15 sono queste.

### (a) `tests/test_l4_contratto_prezzo.py` — 7 prove, 2 xfail

Legge `data/packs/CORRENTE.json` -> `pack_2026-27.pkl` (594 giocatori),
`data/processed/market_adjust_2026-27.csv` (594 righe) e i prezzi live
selezionati **con la stessa regola di `scripts/f9_apply_market.py:129-141**
(file piu' recente della stagione in `map_wayback.csv`:
`prezzi_2026-27_live_20260910.csv`, 369 prezzi > 0).

| prova | esito | numeri |
|---|---|---|
| `test_ordinamento_quantili` | **XFAIL(strict)** | 3 violazioni su 594: 7533 Happonen (1,0 / 0,84 / 1,79), 7048 De Marzi (1,0 / 0,92 / 1,88), 543 Padelli (1,0 / 0,86 / 2,04) |
| `test_q50_almeno_un_credito` | **XFAIL(strict)** | stessi 3 portieri, q50 0,84 / 0,86 / 0,92 < 1 |
| `test_peso_mercato_dichiarato` | passa | `w_mkt` letto dalla firma di `market_adjust.adjust_predictions` (0.6), non copiato a mano |
| `test_identita_miscela` | passa | 369 giocatori, scarto massimo **2,8e-14** contro la tolleranza 0,01 |
| `test_senza_mercato_q50_resta_del_modello` | passa | 225 giocatori, scarto massimo **0,0** |
| `test_pack_copia_il_q50_miscelato` | passa | 0 scarti su 594 (pack = `round(q50_adj, 2)`) |
| `test_nessun_campo_mancante_o_nan` | passa | 0 su 594 × 7 campi (`q10,q50,q90,value,value_up,pres,sigma`) |

I due xfail portano nel `reason` il motivo, i tre nomi e i tre valori, e il
rimando a `src/fantabot/market_adjust.py:184` (`max(1.0, q10 + delta)` senza
riordino dopo la miscela; correzione prevista dopo l'asta). `strict=True`:
appena il difetto e' corretto le due prove passano, l'xfail diventa rosso e va
tolto. **Nessuna asserzione indebolita**: la seconda proprieta' (`q50 >= 1`)
rompe sugli stessi tre portieri e resta un'asserzione piena, marcata a parte.

### (b) `tests/test_l4_non_anticipazione_prezzo.py` — 5 prove, 2 xfail

`scripts/f1_train_price.py` viene **letto con `ast`**, non importato: nessun
effetto collaterale (l'import eseguirebbe `REPORTS.mkdir`). Fonti:
`PRICE_SOURCES`, `RUNS`, `config/league.yaml` (`seasons.<s>.auction_date`),
`data/processed/_match/map_wayback.csv` (date dai nomi dei file).

| prova | esito | numeri |
|---|---|---|
| `test_fonte_dichiarata_precede_asta` | passa | 1 sola stagione controllabile: 2024-25, fonte `2024-08` < asta `2024-09-01` |
| `test_bersaglio_backtest_non_e_un_listino` | passa | R1 2023-24 e R2 2024-25 hanno `kind == "estiva"` |
| `test_stagione_bersaglio_fuori_dal_train` | passa | R1 train [2021-22] -> 2023-24; R2 train [2021-22, 2023-24] -> 2024-25 |
| `test_data_asta_dichiarata_per_ogni_stagione` | **XFAIL(strict)** | `auction_date` presente solo per 2024-25 e 2025-26; **mancano 2021-22, 2023-24, 2026-27** (3 su 4 delle stagioni che servono) |
| `test_listini_anteriori_alla_propria_asta` | **XFAIL(strict)** | **6 listini su 6** posteriori: 2024-25 (asta 1/9/2024) ha 4/10/2024, 14/2/2025, 16/6/2025; 2025-26 (asta 2/9/2025) ha 12/12/2025, 11/4/2026, 6/8/2026 |

L'asserzione richiesta dal compito — «la fonte del bersaglio deve precedere
l'asta» — **non e' verificabile oggi per 2021-22 e 2023-24**: la data d'asta non
esiste nel progetto. Questo e' il primo xfail, ed e' il difetto vero. Il secondo
xfail congela con i numeri il fatto di L4.md §2.3(f): nessuna stagione passata
ha un listino pre-asta, quindi il peso `w_mkt = 0,6` non e' falsificabile fuori
tempo con questo archivio. Nessuna soglia allentata.

### (c) `tests/test_l4_copertura_registrata.py` — 3 prove, 1 xfail

Ricalcolo dalle predizioni salvate `data/processed/pred_ens_tab_cat_{2023-24,
2024-25}.csv` (file del 6/8/2026) e dal bersaglio `target_mean_pct_all_estiva`
con `target_n_obs_all_estiva >= 2` di `players_{stagione}.parquet`, con le
formule identiche a `scripts/f1_train_price.py:evaluate` (aggancio per
`master_id`, `validate="one_to_one"`).

Tolleranze dichiarate **prima**: `n` esatto, copertura 0,005, pinball 0,0002,
`mae_pct` 0,0002.

| chiave | metrica | registrato | ricalcolato | scarto |
|---|---|---:|---:|---:|
| R1/ens_tab_cat (2023-24) | n | 336 | 336 | 0 |
| | copertura [q10,q90] | 0,753 | 0,753 | 0,000 |
| | pinball | 0,00574 | 0,00574 | 0,00000 |
| | mae_pct | 0,01229 | 0,01229 | 0,00000 |
| R2/ens_tab_cat (2024-25) | n | 255 | 255 | 0 |
| | copertura [q10,q90] | 0,718 | 0,718 | 0,000 |
| | pinball | 0,00550 | 0,00550 | 0,00000 |
| | mae_pct | 0,01132 | 0,01132 | 0,00000 |

(`spearman` coincide pure: 0,8047 e 0,8245.) Il json **e'** riproducibile dalle
predizioni su disco: la deriva silenziosa non c'e'.

Terza prova, `test_json_allineato_ai_run_del_codice`: **XFAIL(strict)** —
`reports/f1_price_eval.json` (6/8/2026) contiene ancora i 5 record `R3/*`
(n = 509, test 2025-26) che `scripts/f1_train_price.py:56-59` dichiara rimossi
il 6/9/2026. Il disallineamento e' **dichiarato dalla prova**, non nascosto in
un assert addomesticato; l'artefatto va rigenerato dopo l'asta o rinominato
storico.

Nota: nessuna prova di questo file e' finita in `skip` — i file di predizione
esistono tutti.

### Che cosa NON ho fatto (per progetto)

- Nessun cambio di comportamento: `market_adjust.py`, `f9_apply_market.py`,
  `f4_eleggibilita.py`, i pack e i json **non sono stati toccati**.
- Non ho scritto la prova su «una sola fonte per il prezzo di mercato» (36
  scarti oltre 0,5 crediti fra `map_wayback` ed `eleggibilita`, L4.md §2.3b):
  il compito chiedeva i passi 1, 4 e 5 di L4.md, e quel controllo appartiene al
  passo 3, che tocca file congelati.
- Non ho rigenerato `reports/f1_price_eval.json` (richiede
  `scripts/f1_train_price.py`, cioe' addestramento: vietato).

---

## Parte 2 — L1, prova decisiva

Rapporto per esteso: `scratchpad/w4/L1_prova_decisiva.md`; numeri a macchina in
`scratchpad/w4/L1_prova_decisiva.json`. **Nessun file del progetto scritto.**

Criterio (scritto prima, da L1.md §8): superato solo se **entrambe**
MAE(onesto) <= MAE(banale) − 0,50 **e** rho(onesto) >= rho(banale) + 0,05.

Comandi (RIPRODOTTO, `OMP_NUM_THREADS=4`, insieme sotto i 2 minuti):

```
python scripts/l1_presenze_per_origine.py 2025-26 --feature ammesse --semi 5 \
  --fuori "<w4>/pres_2025-26_estiva"
→ origine 2025-08-22, K=0, residue 380, feature 32/36 (escluse fvm,
  quot_fs_sett, team_prev_xg, cambio_squadra), somma 11016.2 su 663 giocatori,
  scarto fra semi 0.496, utilizzabile operativamente: True
python "<w4>/confronto_banale.py"
```

| braccio | MAE (presenze/38 giornate) | rho di rango | somma prevista |
|---|---:|---:|---:|
| onesto | **7,9291** | **0,6172** | 11.016,2 |
| banale (`prev1_presenze`, NaN->0) | **10,0694** | **0,4435** | 8.572,0 |
| osservato | — | — | 10.778 |

Guadagni: MAE **+2,1403** (soglia 0,50), rho **+0,1737** (soglia 0,05).

**VERDETTO: SUPERATO.** Entrambe le condizioni soddisfatte, sul 2025-26, che
non e' la stagione da cui viene l'elenco delle feature escluse.

Limite dichiarato, non correttivo del verdetto: la regola banale e' penalizzata
per costruzione, **268 su 663** (40,4 %) hanno `prev1_presenze` NaN e prendono 0,
e la sua somma e' 8.572 contro 10.778 osservate (−20,5 %); il braccio onesto
sbaglia in eccesso del +2,2 %. Il criterio era scritto prima e non e' stato
toccato.

---

## Riepilogo per l'orchestratore

- L4 passa da «zero prove automatiche sul prezzo» a **15 prove**, di cui **5
  xfail strict** che fotografano cinque difetti reali con nomi e numeri; nessun
  file congelato modificato.
- Il fatto nuovo di questa sessione: `reports/f1_price_eval.json` **e'
  riproducibile alla quinta cifra** dalle predizioni salvate (L4.md lo dava
  come «da rigenerare, oggi fallirebbe subito»): quello che e' rotto non sono i
  numeri, e' l'elenco dei run (R3 rimosso dal codice, ancora nel json).
- Secondo fatto nuovo: la non anticipazione del prezzo non e' **verificabile**
  per 2021-22, 2023-24 e 2026-27 perche' `config/league.yaml` non dichiara la
  loro `auction_date`. Costo della correzione: tre righe di configurazione.
- L1 ramo presenze: bersaglio onesto **batte** la regola banale con margine
  ampio su entrambe le misure. Restano non fatti i punti 2-4 di L1.md §6.
