# L1 — contratto temporale su `players_*.parquet` (compito B)

Etichetta `L1_contratto`. Criteri di accettazione scritti **prima** in
`scratchpad/w5/criteri_prima_L1_contratto.md`. Sessione del 10/9/2026,
13:00-13:30. Convenzioni: **RIPRODOTTO** = eseguito ora con esito riportato;
**OSSERVATO NEL CODICE** = letto in un file, con riga; **IPOTESI** = non provato.

## 1. Che cosa e' stato fatto

| # | cosa | dove |
|---|---|---|
| 1 | classificazione delle 66 colonne per stato di origine, con prova | tabella al §5 |
| 2 | modulo nuovo che costruisce e scrive il contratto | `src/fantabot/contratto_players.py` (674 righe) |
| 2b | aggancio ADDITIVO dopo la scrittura del parquet, protetto da try/except | `scripts/f0b_build_outputs.py:517` (+ `--out`, `OUT_DIR`, `scrivi_contratto_players`) |
| 3 | prova che il parquet non cambia: rigenerazione in cartella temporanea e confronto sha256 | §3, cinque stagioni **UGUALI** |
| 4 | prove automatiche | `tests/test_l1_contratto_players.py`, 33 prove, RIPRODOTTO `33 passed` |
| 5 | contratti scritti per le tre stagioni | `data/processed/players_{2024-25,2025-26,2026-27}.contratto.json` |

Le 66 colonne sono **tutte chiuse**: nessuna resta `non_verificabile` per
mancanza di tempo.

## 2. L'origine dipende da stagione e k — definizione usata

    origine(stagione, k) = min( auction_date dichiarata in config/league.yaml,
                                data della prima partita della giornata k+1 )

Il minimo, e non la sola data d'asta: un backtest a `k=0` dichiara di non aver
osservato nessuna giornata, quindi un ingresso datato dopo la prima partita
contraddice quella dichiarazione anche se l'asta reale fu piu' tardi. Nel
2024-25 la data d'asta dichiarata e' il **1/9/2024**
(`config/league.yaml:45`) ma la giornata 1 si e' giocata il **17-19/8/2024**:
origine **2024-08-17**.

| stagione | k | origine | come | data d'asta dichiarata |
|---|---|---|---|---|
| 2024-25 | 0 (da `b_predictions_2024-25.json`) | **2024-08-17** | min(asta, prima partita g1) | 2024-09-01 (`config/league.yaml:45`) |
| 2025-26 | 0 (da `b_predictions_2025-26.json`) | **2025-08-23** | min(asta, prima partita g1) | 2025-09-02 (`config/league.yaml:47`) |
| 2026-27 | 3 (da `b_predictions_2026-27.json`) | **2026-09-11** | prima partita g4 | **nessuna**: `config/league.yaml` non dichiara `seasons."2026-27".auction_date` |

Per il 2026-27 il contratto porta `data_asta_dichiarata: null` e
`avviso_data_asta` esplicito: la verifica contro la data d'asta reale (stasera,
10/9/2026 19:30) **non e' possibile da configurazione** e non e' stata
inventata; l'origine viene dal calendario, `data/processed/l2_partite.parquet`.
Rimedio a costo zero, non applicato perche' `config/league.yaml` non e' nel mio
compito: aggiungere `"2026-27": auction_date: "2026-09-10"`.

### Il caso noto, riprodotto

`fvm` e `quot_fs_sett` sono **`posteriore_all_origine`** per 2024-25 e 2025-26
con k=0, e **`disponibile_alla_decisione`** per 2026-27 con k=3. Prova
automatica: `test_fvm_e_quot_fs_posteriori_nel_backtest_k0`,
`test_2026_27_con_k3_lo_snapshot_e_ammissibile`,
`test_k_cambia_lo_stato_a_parita_di_stagione` (stessa stagione, k=0 vs k=3:
`quot_fs_sett` passa da POSTERIORE a DISPONIBILE).

## 3. Il parquet non cambia — impronte

RIPRODOTTO: `python scripts/f0b_build_outputs.py --out <w5>/rigen`
(uscita 0, ~2 min, log in `scratchpad/w5/rigen.log`), poi `sha256sum`.

| file | corrente | rigenerato | esito |
|---|---|---|---|
| `players_2021-22.parquet` | `f5010763a14c6ef3…` | `f5010763a14c6ef3…` | **uguale** |
| `players_2023-24.parquet` | `dba537226b4b53cb…` | `dba537226b4b53cb…` | **uguale** |
| `players_2024-25.parquet` | `700a9b471e21780a…` | `700a9b471e21780a…` | **uguale** |
| `players_2025-26.parquet` | `14cd69bb86969491…` | `14cd69bb86969491…` | **uguale** |
| `players_2026-27.parquet` | `2d53a2e5ed0a10fa…` | `2d53a2e5ed0a10fa…` | **uguale** |
| `aste_reali_clean.csv` | `202822d6ed963c40…` | uguale | uguale |
| `price_targets.csv` | `7bca4931acd2919f…` | uguale | uguale |
| `votes_2024-25.parquet` | `9c24ee16140cf49d…` | uguale | uguale |
| `votes_2026-27.parquet` | `5cc3f6d1fbd67cd3…` | uguale | uguale |

Le impronte 2021-22/2023-24/2024-25/2025-26 coincidono anche con quelle
registrate in `data/istantanee/20260906_2102/impronte.json` e citate in
`reports/livelli_20260910/L1.md` §4; `2d53a2e5ed0a10fa` e' quella del 10/9
citata nello stesso paragrafo. **Criterio 5 superato: cinque su cinque.**

Aggancio non bloccante — RIPRODOTTO forzando l'errore:

```
python -c "import sys;sys.path.insert(0,'scripts');import f0b_build_outputs as m;m.scrivi_contratto_players('1999-00')"
→ contratto NON scritto per 1999-00: FileNotFoundError: manca …players_1999-00.parquet
→ "dopo: la catena prosegue"
```

## 4. Prove

RIPRODOTTO, con `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 -p no:cacheprovider`:

```
python -m pytest tests/test_l1_contratto_players.py -q      → 33 passed
python -m pytest tests/test_l1_contratto_players.py \
       tests/test_l1_presenze_per_origine.py \
       tests/test_non_anticipazione.py -q                    → 44 passed in 6.40s
```

La suite intera (`python -m pytest tests/ -q`, 581+33 prove) e' stata lanciata in
sottofondo alle 13:14: l'esito e' riportato in fondo al rapporto (§10). Nessuna
prova esistente importa `f0b_build_outputs.py` (grep su `tests/`: solo il file
nuovo), quindi la modifica additiva non ha lettori fra le prove.

Le 33 prove nuove coprono: copertura esatta delle colonne del parquet (3
stagioni), stati fra i quattro ammessi, nessuna `disponibile` senza prova (e la
guardia di `Ingresso` verificata viva con un caso che deve fallire), il caso
noto `fvm`/`quot_fs_sett`, la dipendenza da k, `target_*` sempre etichette
posteriori, nessuno stato derivato piu' pulito delle sue dipendenze, origine mai
oltre la data d'asta dichiarata ne' dentro la giornata k+1, presenza di
impronte/versione, e la coerenza dei tre file su disco col rispettivo parquet.

## 5. Le 66 colonne

DISP = `disponibile_alla_decisione`, RICO = `ricostruzione_retrospettiva`,
POST = `posteriore_all_origine`, NONV = `non_verificabile`. Nessuna colonna
NONV nelle tre stagioni. La prova per esteso (data della fonte, motivo,
dipendenze) e' dentro ogni `players_{s}.contratto.json`, campo `colonne[].prova`.

| # | colonna | ruolo | 24-25 k0 | 25-26 k0 | 26-27 k3 | fonte (2024-25) | codice |
|---|---|---|---|---|---|---|---|
| 1 | `master_id` | iden | DISP | DISP | DISP | quotazioni/fantacalcioit_2024-25.csv | f0b_lib.py:load_registry |
| 2 | `nome` | iden | DISP | DISP | DISP | quotazioni/fantacalcioit_2024-25.csv | f0b_lib.py:load_registry |
| 3 | `ruolo` | iden | DISP | DISP | DISP | quotazioni/fantacalcioit_2024-25.csv | f0b_lib.py:load_registry |
| 4 | `squadra` | feat | RICO | RICO | DISP | quotazioni/fantasoccer_2024-25_g03.csv | f0b_build_outputs.py:358-365 |
| 5 | `squadra_listone` | feat | RICO | RICO | DISP | quotazioni/fantacalcioit_2024-25.csv | f0b_build_outputs.py:345 |
| 6 | `squadra_fonte` | iden | RICO | RICO | DISP | quotazioni/fantasoccer_2024-25_g03.csv | f0b_build_outputs.py:366 |
| 7 | `qt_i` | feat | RICO | RICO | DISP | quotazioni/fantacalcioit_2024-25.csv | f0b_lib.py:load_registry |
| 8 | `fvm` | feat | POST | POST | DISP | quotazioni/fantacalcioit_2024-25.csv | f0b_lib.py:load_registry |
| 9 | `quot_fs_sett` | feat | POST | POST | DISP | quotazioni/fantasoccer_2024-25_g03.csv | f0b_build_outputs.py:367 |
| 10 | `eta` | feat | DISP | DISP | DISP | _match/map_tm.csv | f0b_build_outputs.py:370-379,386-402 |
| 11 | `tm_value_eur` | feat | DISP | DISP | DISP | transfermarkt/transfermarkt_valuations_seriea.csv | f0b_build_outputs.py:376-402 |
| 12 | `nuovo_in_serie_a` | feat | DISP | DISP | DISP | voti/voti_2023-24.csv | f0b_build_outputs.py:407 |
| 13 | `squadra_neopromossa` | feat | RICO | RICO | DISP | quotazioni/fantacalcioit_2024-25.csv | f0b_build_outputs.py:408-410 |
| 14 | `cambio_squadra` | feat | RICO | RICO | DISP | quotazioni/fantasoccer_2024-25_g03.csv | f0b_build_outputs.py:413-416 |
| 15 | `prev1_fantamedia` | feat | DISP | DISP | DISP | voti/voti_2023-24.csv | f0b_build_outputs.py:421-429 |
| 16 | `prev1_media_voto` | feat | DISP | DISP | DISP | voti/voti_2023-24.csv | f0b_build_outputs.py:421-429 |
| 17 | `prev1_presenze` | feat | DISP | DISP | DISP | voti/voti_2023-24.csv | f0b_build_outputs.py:421-429 |
| 18 | `prev1_gol` | feat | DISP | DISP | DISP | voti/voti_2023-24.csv | f0b_build_outputs.py:421-429 |
| 19 | `prev1_assist` | feat | DISP | DISP | DISP | voti/voti_2023-24.csv | f0b_build_outputs.py:421-429 |
| 20 | `prev1_rig_segnati` | feat | DISP | DISP | DISP | voti/voti_2023-24.csv | f0b_build_outputs.py:421-429 |
| 21 | `prev1_rig_sbagliati` | feat | DISP | DISP | DISP | voti/voti_2023-24.csv | f0b_build_outputs.py:421-429 |
| 22 | `prev1_ammonizioni` | feat | DISP | DISP | DISP | voti/voti_2023-24.csv | f0b_build_outputs.py:421-429 |
| 23 | `prev2_fantamedia` | feat | DISP | DISP | DISP | voti/voti_2022-23.csv | f0b_build_outputs.py:421-429 |
| 24 | `prev2_media_voto` | feat | DISP | DISP | DISP | voti/voti_2022-23.csv | f0b_build_outputs.py:421-429 |
| 25 | `prev2_presenze` | feat | DISP | DISP | DISP | voti/voti_2022-23.csv | f0b_build_outputs.py:421-429 |
| 26 | `prev2_gol` | feat | DISP | DISP | DISP | voti/voti_2022-23.csv | f0b_build_outputs.py:421-429 |
| 27 | `prev2_assist` | feat | DISP | DISP | DISP | voti/voti_2022-23.csv | f0b_build_outputs.py:421-429 |
| 28 | `prev2_rig_segnati` | feat | DISP | DISP | DISP | voti/voti_2022-23.csv | f0b_build_outputs.py:421-429 |
| 29 | `prev2_rig_sbagliati` | feat | DISP | DISP | DISP | voti/voti_2022-23.csv | f0b_build_outputs.py:421-429 |
| 30 | `prev2_ammonizioni` | feat | DISP | DISP | DISP | voti/voti_2022-23.csv | f0b_build_outputs.py:421-429 |
| 31 | `prev3_fantamedia` | feat | DISP | DISP | DISP | voti/voti_2021-22.csv | f0b_build_outputs.py:421-429 |
| 32 | `prev3_media_voto` | feat | DISP | DISP | DISP | voti/voti_2021-22.csv | f0b_build_outputs.py:421-429 |
| 33 | `prev3_presenze` | feat | DISP | DISP | DISP | voti/voti_2021-22.csv | f0b_build_outputs.py:421-429 |
| 34 | `prev3_gol` | feat | DISP | DISP | DISP | voti/voti_2021-22.csv | f0b_build_outputs.py:421-429 |
| 35 | `prev3_assist` | feat | DISP | DISP | DISP | voti/voti_2021-22.csv | f0b_build_outputs.py:421-429 |
| 36 | `prev3_rig_segnati` | feat | DISP | DISP | DISP | voti/voti_2021-22.csv | f0b_build_outputs.py:421-429 |
| 37 | `prev3_rig_sbagliati` | feat | DISP | DISP | DISP | voti/voti_2021-22.csv | f0b_build_outputs.py:421-429 |
| 38 | `prev3_ammonizioni` | feat | DISP | DISP | DISP | voti/voti_2021-22.csv | f0b_build_outputs.py:421-429 |
| 39 | `us_prev_xg` | feat | DISP | DISP | DISP | understat/understat_players_2023.csv | f0b_build_outputs.py:461-473 |
| 40 | `us_prev_xa` | feat | DISP | DISP | DISP | understat/understat_players_2023.csv | f0b_build_outputs.py:461-473 |
| 41 | `us_prev_npxg` | feat | DISP | DISP | DISP | understat/understat_players_2023.csv | f0b_build_outputs.py:461-473 |
| 42 | `us_prev_shots` | feat | DISP | DISP | DISP | understat/understat_players_2023.csv | f0b_build_outputs.py:461-473 |
| 43 | `us_prev_minutes` | feat | DISP | DISP | DISP | understat/understat_players_2023.csv | f0b_build_outputs.py:461-473 |
| 44 | `us_prev_xg90` | feat | DISP | DISP | DISP | understat/understat_players_2023.csv | f0b_build_outputs.py:461-473 |
| 45 | `team_prev_xg` | feat | RICO | RICO | DISP | understat/understat_teams_2023.csv | f0b_build_outputs.py:479-484 |
| 46 | `target_n_obs_10x500_estiva` | etic | POST | POST | POST | gruppoesperti/aste_reali_tidy.csv | f0b_build_outputs.py:143-205 |
| 47 | `target_mean_pct_10x500_estiva` | etic | POST | POST | POST | gruppoesperti/aste_reali_tidy.csv | f0b_build_outputs.py:143-205 |
| 48 | `target_std_pct_10x500_estiva` | etic | POST | POST | POST | gruppoesperti/aste_reali_tidy.csv | f0b_build_outputs.py:143-205 |
| 49 | `target_n_obs_all_estiva` | etic | POST | POST | POST | gruppoesperti/aste_reali_tidy.csv | f0b_build_outputs.py:143-205 |
| 50 | `target_mean_pct_all_estiva` | etic | POST | POST | POST | gruppoesperti/aste_reali_tidy.csv | f0b_build_outputs.py:143-205 |
| 51 | `target_std_pct_all_estiva` | etic | POST | POST | POST | gruppoesperti/aste_reali_tidy.csv | f0b_build_outputs.py:143-205 |
| 52 | `target_n_obs_tardiva` | etic | POST | POST | POST | gruppoesperti/aste_reali_tidy.csv | f0b_build_outputs.py:143-205 |
| 53 | `target_mean_pct_tardiva` | etic | POST | POST | POST | gruppoesperti/aste_reali_tidy.csv | f0b_build_outputs.py:143-205 |
| 54 | `target_std_pct_tardiva` | etic | POST | POST | POST | gruppoesperti/aste_reali_tidy.csv | f0b_build_outputs.py:143-205 |
| 55 | `target_wayback_p500_10sq` | etic | POST | POST | POST | _match/map_wayback.csv | f0b_build_outputs.py:182-187 |
| 56 | `tm_prev_min_per_app` | feat | DISP | DISP | DISP | transfermarkt/transfermarkt_appearances_seriea.csv | f0b_build_outputs.py:432-440 |
| 57 | `tm_prev_share90` | feat | DISP | DISP | DISP | transfermarkt/transfermarkt_appearances_seriea.csv | f0b_build_outputs.py:432-440 |
| 58 | `prev1_pres_last10` | feat | DISP | DISP | DISP | voti/voti_2023-24.csv | f0b_build_outputs.py:249-251 |
| 59 | `amm_pp_w` | feat | DISP | DISP | DISP | voti/voti_2023-24.csv | f0b_build_outputs.py:445-453 |
| 60 | `esp_pp_w` | feat | DISP | DISP | DISP | voti/voti_2023-24.csv | f0b_build_outputs.py:445-453 |
| 61 | `squal_att` | feat | DISP | DISP | DISP | voti/voti_2023-24.csv | f0b_build_outputs.py:445-453 |
| 62 | `team_prev_xga` | feat | RICO | RICO | DISP | understat/understat_teams_2023.csv | f0b_build_outputs.py:485-490 |
| 63 | `team_prev_xpts` | feat | RICO | RICO | DISP | understat/understat_teams_2023.csv | f0b_build_outputs.py:485-490 |
| 64 | `team_prev_cs` | feat | RICO | RICO | DISP | voti/voti_2023-24.csv | f0b_build_outputs.py:491 |
| 65 | `rig_tirati_prev1` | feat | DISP | DISP | DISP | voti/voti_2023-24.csv | f0b_build_outputs.py:456 |
| 66 | `rigorista_1_prev` | feat | DISP | DISP | DISP | voti/voti_2023-24.csv | f0b_build_outputs.py:458-459 |
Conteggi: 2024-25 e 2025-26 → 44 DISP / 10 RICO / 12 POST; 2026-27 → 56 DISP /
0 RICO / 10 POST (le sole `target_*`).

### Le date che decidono gli stati (dal contratto, campo `date_fonte`)

| fonte | 2024-25 | 2025-26 | 2026-27 |
|---|---|---|---|
| listone fantacalcio.it (acquisizione) | 2026-08-06 | 2026-08-06 | **2026-09-10** |
| snapshot fanta.soccer (giornata / rilevazione) | g3 / **2024-08-30** | g2 / **2025-08-29** | g3 / **2026-09-04** |
| valutazioni TM, massima usata (`date <= 1/9`) | 2024-07-19 | 2025-07-01 | 2026-06-11 |
| rosa TM (`map_tm_kader_{y}.csv`) | assente | assente | 2026-09-05 |
| fine stagione precedente (calendario) | 2024-06-02 | 2025-05-25 | 2026-05-24 |
| aste GruppoEsperti (etichette) | 2026-08-06 | 2026-08-06 | 2026-08-06 |

Tre conseguenze, tutte OSSERVATE NEL CODICE + dai file:

1. **`tm_value_eur` e' pulita, e ora con una prova numerica**: il filtro
   `vals[vals.date <= sept1]` (`scripts/f0b_build_outputs.py:380`) lascia come
   valutazione piu' tarda il 19/7/2024 (2024-25), l'1/7/2025 e l'11/6/2026 —
   tutte anteriori all'origine. Conferma la riga «nessuna valutazione risulta
   posteriore alla prima giornata» di `scripts/l1_presenze_per_origine.py`, che
   finora era un'affermazione senza numero nel contratto.
2. **Il blocco squadra e' ricostruito, non posteriore**: `squadra`,
   `squadra_fonte`, `squadra_listone`, `qt_i`, `squadra_neopromossa`,
   `cambio_squadra`, `team_prev_xg/xga/xpts/cs` sono RICO nei backtest. Sono
   fatti di rosa e quotazioni iniziali letti da file senza storia: la loro
   versione al momento dell'origine non e' ricostruibile, ma non contengono
   l'esito della stagione. `origine.py` prevede esattamente questo caso
   («esiste solo in una versione corrente senza storia → `ricostruzione_retrospettiva`»).
   Nota sul confronto: per lo snapshot fanta.soccer il contratto usa la **piu'
   tarda** fra rilevazione dichiarata e acquisizione, quindi per le stagioni
   archiviate decide l'acquisizione (6/8/2026); per il 2026-27 decide la
   rilevazione (4/9/2026), acquisito l'1/9.
3. **`fvm` e' un'altra cosa**: e' il valore di mercato *corrente* del listone,
   cambia in corso di stagione, e sul 2024-25 correla di rango 0,900 con la
   quotazione di fine campionato contro 0,708 con quella iniziale
   (`scripts/l1_presenze_per_origine.py:66-99`). POST, non RICO.

### Impronte registrate nel contratto

Ogni contratto porta `impronte` (sha256 di tutte le fonti piu' parquet,
`registry.csv`, `price_targets.csv`, `l2_partite.parquet`) e `versione_codice`
(impronta di `scripts/f0b_build_outputs.py` = `d972ee4b5ff7fbc0…` e del modulo
stesso). Controprova di coerenza col contratto del pannello: l'impronta di
`data/raw/voti/voti_2024-25.csv` calcolata qui, `ce9581ac61006cd3…`, e' la
stessa registrata come fonte `voti` in `l2_panel_2024-25.contratto.json`, e
quella di `players_2026-27.parquet`, `2d53a2e5ed0a10fa…`, e' quella citata in
`reports/livelli_20260910/L1.md` §4.

## 6. Divergenze dichiarate rispetto a quanto gia' scritto nel progetto

| voce | `scripts/l1_presenze_per_origine.py` (PROVE_INGRESSI) | questo contratto | perche' |
|---|---|---|---|
| `cambio_squadra`, `team_prev_xg` | RICOSTRUITO | RICOSTRUITO (backtest), DISPONIBILE per 2026-27 k=3 | stesso stato dove il confronto e' lo stesso; per il 2026-27 lo snapshot del 4/9 precede l'origine dell'11/9 |
| `tm_value_log` | DISPONIBILE, prova a parole | `tm_value_eur` DISPONIBILE con la data massima effettiva | la prova ora e' un numero letto dal file |
| `qt_i` | non classificata | RICOSTRUITO (backtest) / DISPONIBILE (2026-27) | quotazione iniziale letta da un file senza storia |
| `target_*` | non classificate | POSTERIORE, ruolo `etichetta` | sono l'esito d'asta della stagione: bersagli, mai ingressi |

Nessuna conclusione precedente e' stata ritrattata: le cinque voci di
`PROVE_INGRESSI` restano leggibili nel loro file e concordano.

## 7. Limiti dichiarati

- **IPOTESI (non provata)**: per il listone fantacalcio.it, per le aste
  GruppoEsperti e per `map_wayback.csv` la data usata e' l'**mtime** del file su
  questa macchina, cioe' la data di acquisizione locale, non una data di
  pubblicazione. Se un file fosse stato copiato, l'mtime sarebbe piu' recente
  del dato: il contratto sbaglierebbe verso il **pessimismo** (dichiarerebbe
  posteriore un dato disponibile), mai verso l'ottimismo. Per il fanta.soccer
  la data e' invece dichiarata dalla fonte
  (`data/raw/quotazioni/fantasoccer_date_rilevazioni.csv`) e il contratto usa la
  **piu' tarda** fra rilevazione e acquisizione.
- Il contratto **classifica**, non filtra: nessun modello e' stato cambiato.
  Oggi `scripts/f1_train_price.py` continua a leggere il parquet intero. Il
  passo successivo (fuori dal mio compito) e' una prova che fallisca se una
  colonna POST entra fra le feature ammesse di un fit dichiarato a un'origine.
- `config/league.yaml` non dichiara `auction_date` per 2021-22, 2023-24 e
  **2026-27**: per la stagione in corso l'origine viene dal calendario. Il file
  di configurazione non e' stato toccato.
- I contratti per 2021-22 e 2023-24 **non** sono stati scritti in
  `data/processed` (il compito chiedeva le tre stagioni); l'aggancio in
  `f0b_build_outputs.py` li scrivera' alla prossima rigenerazione della catena.
  Nella prova del §3 sono stati prodotti nella cartella temporanea senza errori,
  e li' si vede il caso `non_verificabile` funzionare: 2021-22 (origine
  2021-08-21) ha **32 colonne NONV** perche' non esiste alcun file voti per
  2020-21/2019-20/2018-19 — i blocchi `prev1/2/3_*` sono interamente NaN, non
  c'e' informazione da datare; 2023-24 ne ha **11** (`prev3_*` piu' i tre
  disciplinari pesati che dipendono dal blocco piu' vecchio).

## 8. File toccati

| file | cosa |
|---|---|
| `src/fantabot/contratto_players.py` | **nuovo** |
| `tests/test_l1_contratto_players.py` | **nuovo**, 33 prove |
| `scripts/f0b_build_outputs.py` | **modificato, additivo**: `OUT_DIR` (le letture restano da `PROC`), `--out`, `scrivi_contratto_players()`, una riga di chiamata dopo `out.to_parquet` (riga 517) |
| `data/processed/players_2024-25.contratto.json` | **nuovo** (42 KB) |
| `data/processed/players_2025-26.contratto.json` | **nuovo** |
| `data/processed/players_2026-27.contratto.json` | **nuovo** |

Nessun file del **percorso d'asta congelato** e' stato toccato. Verifica delle 33
impronte di `scratchpad/w5/impronte_w5.json`: **due differenze, nessuna delle
due nel percorso congelato**:

- `scripts/f0b_build_outputs.py` `c3128c849ff4ccf7…` → `d972ee4b5ff7fbc0…`: **mia**,
  prevista dal compito (modifica additiva, fuori dal percorso congelato). Il
  `diff -u` contro la copia in `data/istantanee/20260906_2102/file/` mostra
  **cinque punti**: il blocco `OUT_DIR = PROC`, quattro sostituzioni `PROC` →
  `OUT_DIR` sulle sole SCRITTURE (piu' la rilettura di `price_targets.csv`), la
  riga `scrivi_contratto_players(s)` dopo `out.to_parquet`, la funzione di
  aggancio e `main(argv=None)` con `--out`. Fine riga **CRLF preservato**: una
  prima versione lo aveva convertito a LF e la conversione e' stata annullata,
  cosi' il diff resta solo il contenuto;
- `scripts/l2_pilota_c2.py` `e688e36901b3fa86…` → `3d0a3351b0647e56…`: **non mia**
  — non l'ho aperto ne' scritto; e' di un altro agente in parallelo. Lo segnalo
  perche' il revisore lo trovera'.

Tutti gli altri 31 file (`f10_copilot.py`, `fantaoracle_app.py`,
`f4_eleggibilita.py`, `f14_listino_offline.py`, `f11_refresh_all.py`,
`f9_apply_market.py`, `f2_build_packs.py`, `piani.py`, `optimizer.py`,
`bot_b.py`, `base.py`, `models.py`, `rettifica_indisponibili.py`,
`market_adjust.py`, `rules.py`, pack, `players_*.parquet`,
`b_predictions_*`, le due prove) sono **identici**.

## 9. Riepilogo in una riga

Le 66 colonne di `players_*.parquet` hanno ora uno stato di origine con prova,
dipendente da stagione e da k: 44 disponibili, 10 ricostruite e 12 posteriori
nei backtest a k=0 (fra cui `fvm` e `quot_fs_sett`), 56 disponibili e 10
posteriori — le sole etichette — per il 2026-27 a k=3; il parquet e' invariato
bit a bit su cinque stagioni.

## 10. Suite intera — esito e una prova rossa che NON e' mia

RIPRODOTTO (lanciata 13:14, finita 13:20):

```
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 OMP_NUM_THREADS=3 python -m pytest tests/ -q -p no:cacheprovider
→ 1 failed, 660 passed, 2 skipped, 5 xfailed in 360.95s
FAILED tests/test_bot_l3_parita.py::test_il_piano_cambia_davvero_l_asta
```

Le 660 verdi comprendono le 33 nuove (581 collezionate il 9/9 + 33 mie ≈ 614; la
differenza sono le prove aggiunte oggi dagli altri agenti).

**La prova rossa non e' causata da questo compito**, e non e' stata toccata:

- messaggio: `L3 impegna sul piano 121 crediti, B+ ne impegna 146` —
  `tests/test_bot_l3_parita.py:448`, RIPRODOTTO da sola in 37 s;
- quel file importa `fantabot.bots.bot_l3`, `fantabot.engine.auction`,
  `fantabot.models`: **non** importa `contratto_players`, **non** importa
  `f0b_build_outputs`, e non legge `players_*.parquet` ne' i `*.contratto.json`;
- il file di prova e' stato modificato oggi alle **11:46** e
  `src/fantabot/bots/bot_l3.py` l'8/9 alle 22:07: e' il perimetro di un altro
  agente (L3), non il mio;
- non l'ho indebolita ne' saltata: la lascio rossa e la segnalo. IPOTESI, non
  verificata: appartiene al lavoro L3 in corso in un'altra sessione.
