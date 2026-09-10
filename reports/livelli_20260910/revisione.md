# Revisione (compito E) — 10/9/2026, dopo L1_contratto, L2_3ter, L3_banco_117, L4_calibrazione

Lavorato dalle 14:55 alle 15:22. Ora limite 15:30: rispettata, nulla troncato.
Criteri scritti PRIMA di ogni numero: `…/scratchpad/w5/criteri_prima_revisione.md`
(ore 14:56, prima del primo ricalcolo di impronta).

Marche: **RIPRODOTTO** (comando eseguito ora, esito riportato),
**OSSERVATO NEL CODICE** (letto, con riga), **NON VERIFICABILE**.

Sola lettura sul progetto tranne: `data/copilot/prove/ledger_w5_8791*.json`
(imposti dal compito, cartella `prove/` fuori dal congelamento) e la rimozione
dei due `.lock` in `data/copilot/prove/` (imposta dal compito).

---

## 1. Impronte del percorso d'asta congelato

RIPRODOTTO — ricalcolo sha256 delle 33 voci di `scratchpad/w5/impronte_w5.json`.

```
voci 33   diverse 2   mancanti 0
DIV scripts/f0b_build_outputs.py  c3128c849ff4 -> d972ee4b5ff7  mtime 2026-09-10 13:20:07  30102 byte
DIV scripts/l2_pilota_c2.py       e688e36901b3 -> 3d0a3351b064  mtime 2026-09-10 13:06:42  34138 byte
```

**ESITO: nessun FALLIMENTO.** Le 31 voci del percorso d'asta congelato (script
d'asta, `src/fantabot/*`, `viz/*`, `FantaOracle.bat`, `data/packs/*`,
`data/copilot/*` fuori da `prove/`, `data/processed/players_*.parquet`,
`data/processed/b_predictions_2026-27*.json`, `tests/test_copilot_asta.py`,
`tests/test_rettifica_indisponibili.py`) hanno l'impronta dichiarata.
Le 2 divergenti sono esattamente le due ammesse.

### 1.1 `scripts/f0b_build_outputs.py` (compito L1_contratto) — **ADDITIVO**

Copia di riferimento trovata: `data/istantanee/20260906_2102/file/scripts/f0b_build_outputs.py`.
Il suo sha256 è `c3128c849ff4ccf7…` = **esattamente** l'impronta di riferimento
di `impronte_w5.json`, quindi il diff è per intero il lavoro di oggi, senza code
di modifiche anteriori.

```
diff -u istantanea -> corrente : 93 righe di diff, 33 aggiunte, 6 rimosse
```

Le 6 righe "rimosse" sono 6 righe **riscritte**, e sono tutte della stessa forma:

| riga | prima | dopo |
|---|---|---|
| ~136 | `aste.to_csv(PROC / "aste_reali_clean.csv"…)` | `OUT_DIR / …` |
| ~197 | `pt.to_csv(PROC / "price_targets.csv"…)` | `OUT_DIR / …` |
| ~208 | `return pd.read_csv(PROC / "price_targets.csv")` | `OUT_DIR / …` |
| ~227 | `out.to_parquet(PROC / f"votes_{s}.parquet"…)` | `OUT_DIR / …` |
| ~516 | `out.to_parquet(PROC / f"players_{s}.parquet"…)` | `OUT_DIR / …` |
| ~525 | `def main():` | `def main(argv=None):` |

con `OUT_DIR = PROC` come predefinito (riga 25) e `OUT_DIR` riassegnato solo se
si passa `--out`. Le **letture** restano tutte da `PROC` (`reg = pd.read_csv(PROC / "registry.csv")`).
Le 33 aggiunte sono: il blocco `OUT_DIR`, la funzione `scrivi_contratto_players(s)`
avvolta in `try/except Exception` che stampa e prosegue, la sua unica chiamata
dopo `out.to_parquet` (riga 517), e il parsing di `--out`.

**GIUDIZIO: additivo come richiesto.** Nessuna riga eliminata, nessun
comportamento preesistente alterato quando lo script è invocato senza argomenti
(cammino predefinito identico byte per byte nelle destinazioni di scrittura).
Prova indipendente a valle: i `players_*.parquet` e i `b_predictions_2026-27*.json`
in `impronte_w5.json` sono **immutati** (§1), cioè la modifica non ha riscritto
i prodotti.

### 1.2 `scripts/l2_pilota_c2.py` (compito L2_3ter) — **ADDITIVO** (verifica più debole)

**NON VERIFICABILE per diff**: nessuna copia dell'originale su disco
(`data/_backup_fable_20260910/` non ne contiene una, nessuna istantanea la
contiene, `find . -name "l2_pilota_c2*"` restituisce solo il file corrente).
Progetto non git. **Non si può fare la differenza riga per riga**: quel che segue
è OSSERVATO NEL CODICE, non un diff.

Modifiche leggibili nel file (657 righe):

| riga | contenuto | natura |
|---|---|---|
| 82 | `from fantabot.tabellino import bersaglio_origine as bo` | import nuovo |
| 232-233 | `costruisci_ingressi(…, bersaglio: Path\|str = None, cartella_bersaglio: Path = None)` | due parametri nuovi, entrambi con predefinito `None` |
| 240-247 | docstring: «Se resta `None` il comportamento e' quello di sempre» | dichiarazione |
| 259-266 | `if bersaglio is None:` → chiamata preesistente `presenze.costruisci(proc / f"b_predictions_{stagione}.json", …)`; `else:` → `bo.costruisci_da_origine(…)` | la vecchia chiamata è **conservata** dentro il ramo `None`; il ramo `else` è nuovo |
| 402-406 | `ap.add_argument("--bersaglio", default=None, …)` | opzione nuova, predefinito `None` |
| 431-432 | chiavi `"bersaglio"` e `"fonte_bersaglio"` nel piano | campi nuovi nel JSON di corsa |
| 438 | `+ ([Path(a.bersaglio)] if a.bersaglio else [])` in `impronte_ingressi` | additivo, vuoto senza l'opzione |
| 448-449, 462-463 | passaggio dei due parametri e riga di stampa della fonte | additivo |

Le occorrenze `--modo-bersaglio` / `--peso-bersaglio` (righe 392, 398) sono
**preesistenti**, non vanno confuse con `--bersaglio`.

**GIUDIZIO: additivo per comportamento.** Senza `--bersaglio` la catena percorre
la chiamata di sempre. Limite dichiarato: non si può escludere una modifica
silenziosa altrove nel file, perché manca la copia di riferimento.

**Segnalazione di metodo, per la prossima volta**: chi tocca un file sorvegliato
ne salvi una copia in `data/_backup_fable_20260910/` prima di scriverci. È la
stessa lacuna già segnalata a mezzogiorno per `tests/test_bot_l3_parita.py`, e
si è ripetuta.

---

## 2. Prove del Copilota — tutte RIPRODOTTE, tutti gli attesi centrati

| prova | esito | atteso |
|---|---|---|
| `pytest tests/test_copilot_asta.py tests/test_rettifica_indisponibili.py -q -p no:cacheprovider` | `17 passed, 1 skipped, 11518 warnings in 4.61s` — exit 0 | nessun rosso (rif. 12:10: 17+1) |
| `verifica_f1f2.py` | **32/32 verificati**, exit 0 | 32/32 |
| `verifica_f5bis.py` | **23/23 verificati**, exit 0 | 23/23 |
| `verifica_f5_asta.py` | **24/24 verificati**, exit 0 | 24/24 |
| `verifica_f6.py` (server 8791) | **25/25 verificati**, exit 0 | 25/25 |

Server di prova F6:

```
python scripts/f10_copilot.py 2026-27 --porta 8791 --ledger "data/copilot/prove/ledger_w5_8791.json"
```

- `GET http://127.0.0.1:8791/copilot/state` → **200** al primo tentativo;
  `{"season": "2026-27", "budget": 500, "quotas": {"P":3,"D":8,"C":8,"A":6}, "n_events": 0…}`;
- `netstat -ano | grep :8791` durante la corsa → `TCP 127.0.0.1:8791 LISTENING 12852`;
- fermato con `taskkill //PID 12852 //F` → «OPERAZIONE RIUSCITA»;
- dopo lo stop: **nessun socket LISTENING su 8791** (solo `TIME_WAIT`, che scadono
  da soli). Porta libera;
- `.lock` rimosso: `data/copilot/prove/ledger_w5_8791.lock` **e** il residuo
  `ledger_w1_8791.lock` (di stamattina, 06:06). Dopo: `nessun .lock residuo`;
- l'export di F6 dichiara la provenienza attesa: `fonti 2026-09-09T22:35`,
  `pack 71ec262b4bdf` — il pack congelato, invariato. 594 righe di listino,
  379 con prezzo di mercato, 54 indisponibili.

**Il percorso d'asta funziona.** Nessuno dei quattro compiti del pomeriggio lo ha
scalfito.

---

## 3. Suite completa

```
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTHONIOENCODING=utf-8 OMP_NUM_THREADS=3 \
  python -m pytest tests -q -p no:cacheprovider -W ignore
```

**Riga finale esatta:**

```
1 failed, 660 passed, 2 skipped, 5 xfailed in 265.92s (0:04:25)
```

Log: `…/scratchpad/w5/suite_E.log`.

### 3.1 Confronto con le 12:10

| | 12:10 | ora | differenza |
|---|---|---|---|
| falliti | 1 | **1** | = |
| passati | 597 | **660** | **+63** |
| saltati | 2 | 2 | = |
| xfail | 5 | 5 | = |
| raccolti | 605 | 668 | +63 |

Ricostruzione del +63, quadra **esattamente** (RIPRODOTTO, riesecuzione per file):

| file | prove | compito |
|---|---|---|
| `tests/test_l1_contratto_players.py` (nuovo) | **33 passed in 7.46s** | L1_contratto |
| `tests/test_l4_calibrazione_prezzo.py` (nuovo) | **19 passed in 1.57s** | L4_calibrazione |
| `tests/test_l2_bersaglio_origine.py` (nuovo) + `tests/test_l2_ingressi_c2.py` (modificato, +2 casi) | **24 passed in 3.69s** insieme, di cui 9 nel file nuovo e 15 in quello modificato (erano 13) | L2_3ter |
| totale | 33 + 19 + 9 + 2 = **63** | |

Nessun `xfail` nuovo, nessuno `skip` nuovo: nessuna prova è stata messa a tacere
per far quadrare i conti.

### 3.2 Attribuzione del rosso

Un solo rosso, lo stesso di mezzogiorno:

```
FAILED tests/test_bot_l3_parita.py::test_il_piano_cambia_davvero_l_asta
tests\test_bot_l3_parita.py:448: AssertionError
E   AssertionError: L3 impegna sul piano 121 crediti, B+ ne impegna 146:
E   inseguire il piano non sta cambiando dove finiscono i soldi
E   assert 121 > 146
```

Stessi numeri (121 contro 146) delle 12:10 e di stamattina.
**Attribuzione: nessuno dei quattro compiti del pomeriggio.** È il difetto noto
del braccio L3, già registrato in `STATO_LIVELLI_20260910.md`; il file
`tests/test_bot_l3_parita.py` non è stato toccato dopo le 13:00 (§6).
**Nessuna regressione introdotta oggi pomeriggio.**

---

## 4. f11 e sintassi

RIPRODOTTO.

| controllo | comando | esito |
|---|---|---|
| f11 vivo | `python scripts/f11_refresh_all.py --elenca` | **exit 0**, elenco stampato (`f9_market`, `f2_pack`, `f7_demo` con le loro dipendenze) |
| sintassi f0b | `python -c "import ast; ast.parse(open('scripts/f0b_build_outputs.py',encoding='utf-8').read())"` | **exit 0**, `sintassi OK` |

Entrambi i criteri di §4 dei criteri scritti prima: SODDISFATTI.

---

## 5. Controlli a campione — tre per compito, 12 su 12 RIPRODOTTI

### L1_contratto

| # | affermazione | verifica | esito |
|---|---|---|---|
| 1 | «33 prove verdi» | `pytest tests/test_l1_contratto_players.py -q` | **RIPRODOTTO** — `33 passed in 7.46s` |
| 2 | «aggancio ADDITIVO in `f0b_build_outputs.py`, diff minimo contro `data/istantanee/20260906_2102`» | diff eseguito ora; hash dell'istantanea = impronta di riferimento | **RIPRODOTTO** — 33 aggiunte, 6 righe riscritte, tutte `PROC`→`OUT_DIR` (con `OUT_DIR = PROC`) più `def main(argv=None)`. Vedi §1.1 |
| 3 | «i contratti sono scritti, i parquet non toccati» | `ls` + ricalcolo impronte | **RIPRODOTTO** — `players_2024-25.contratto.json` 42289 B, `players_2025-26.contratto.json` 42289 B, `players_2026-27.contratto.json` 42083 B (tutti 13:20:46); i tre `players_*.parquet` di `impronte_w5.json` hanno impronta **identica** |

### L2_3ter

| # | affermazione | verifica | esito |
|---|---|---|---|
| 1 | «`d = +0,03459`, `es 0,00206`, `\|t\| = 16,83`» | ricalcolo dai 5 semi in `scratchpad/w5/analisi_3ter.json` (`ONESTO_PIENO.per_seme[*].d_C2_meno_bersaglio`) | **RIPRODOTTO** — `n 5  media 0.03459  es 0.00206  \|t\| 16.83`, cifra per cifra |
| 2 | «`l2_pilota_c2.py`: passo 1, `--bersaglio`, predefinito invariato» | lettura righe 82, 232-233, 259-266, 402-406, 431-432 | **OSSERVATO NEL CODICE** — additivo, ramo `if bersaglio is None` conserva la chiamata di sempre. Vedi §1.2 |
| 3 | «prove nuove del passo 1 e del passo 2 verdi» | `pytest tests/test_l2_bersaglio_origine.py tests/test_l2_ingressi_c2.py -q` | **RIPRODOTTO** — `24 passed in 3.69s` (9 + 15) |

Nota: l'affermazione «prove del cubo 371 passate, 1 saltata» **non** è stata
riverificata singolarmente (tempo); è però compresa nel totale della suite di §3,
dove nulla è rosso fuori da `test_bot_l3_parita.py`.

### L3_banco_117

| # | affermazione | verifica | esito |
|---|---|---|---|
| 1 | «POOL n=132: L3−B = −0,02273, sd 0,15981, IC95 [−0,05019, +0,00418], semiampiezza 0,02719, vinte 52 / pari 17 / peggio 63» | rieseguito `scratchpad/w5/analisi_pool.py` sui due CSV di backup | **RIPRODOTTO** — riga per riga identica |
| 2 | «i due blocchi: A −0,01818 sd 0,16086; B −0,02727 sd 0,15985» | stesso comando | **RIPRODOTTO** — `A n=66 L3-B=-0.01818 sd=0.16086 IC95 [-0.05720, +0.01894]`; `B n=66 L3-B=-0.02727 sd=0.15985 IC95 [-0.06477, +0.01288]` |
| 3 | «rimesso il blocco A come uscita corrente; nessun tetto caricato» | lettura di `data/l3/asta/confronto_asta_2026-27.json` e conteggio righe del CSV | **RIPRODOTTO** — `repliche 66`, `scenari 40`, `seme 20260907`, `tetti {'file': None, 'caricato': False}`; CSV 133 righe = intestazione + **132 aste** |

Il verdetto di L3 resta **INCONCLUDENTE** come dichiarato: l'IC95 del pool
contiene lo zero. Il revisore conferma che il rapporto **non** scrive
«equivalenti» e che la soglia di precisione 0,030 era scritta prima
(`criteri_prima_L3.md`, 13:10) — l'emendamento del disegno (2×66 invece di 117)
è datato nello stesso file, prima di ogni numero.

### L4_calibrazione

| # | affermazione | verifica | esito |
|---|---|---|---|
| 1 | «copertura globale 2024-25 = 0,8863 (fuori dalla banda [0,75; 0,85])» | lettura di `scratchpad/w5/l4_calibrazione_risultati_passo1.json` (configurazione C) | **RIPRODOTTO** — coperture `['0.7608', '0.8863', '0.6756', '0.7262']`: la calibrata è 0,8863 |
| 2 | «pinball peggiore di +1,39 %» | stesso file: base 0,005393 → calibrato 0,005468 | **RIPRODOTTO** — (0,005468−0,005393)/0,005393 = **+1,391 %** |
| 3 | «ampiezza mediana +37,69 %» | stesso file: 11,94 → 16,44 crediti | **RIPRODOTTO** — (16,44−11,94)/11,94 = **+37,69 %** |

In più (non richiesto, gratis): la conclusione **ritrattata** è leggibile accanto
a chi l'ha ritrattata (`L4_calibrazione.md` §3.1): la sonda A dava 0,7922 e
passava tutti e cinque i criteri, e i suoi numeri sono ancora nel file
`l4_calibrazione_risultati.json` (`['0.7176','0.7922','0.753','0.7887']`),
non cancellati. Rispetta la regola.

**12 controlli su 12 RIPRODOTTI. Nessun NON RIPRODOTTO.**

---

## 6. File del progetto toccati dopo le 13:00

`find . -newermt "2026-09-10 13:00:00"` (esclusi `__pycache__` e `.pyc`).

| ora | file | compito | coerente? |
|---|---|---|---|
| 13:05:40 | `src/fantabot/tabellino/bersaglio_origine.py` (6630 B, nuovo) | **L2_3ter** passo 2 | sì |
| 13:06:42 | `scripts/l2_pilota_c2.py` (34138 B, **modificato**) | **L2_3ter** passo 1 | sì — ammesso; additivo (§1.2), ma senza copia di riferimento |
| 13:07:14 | `tests/test_l4_calibrazione_prezzo.py` (6412 B, nuovo) | **L4_calibrazione** | sì |
| 13:07:19 | `tests/test_l2_bersaglio_origine.py` (6187 B, nuovo) | **L2_3ter** | sì |
| 13:07:33 | `tests/test_l2_ingressi_c2.py` (11353 B, **modificato**) | **L2_3ter**, due casi nuovi | sì — 15 `def test_` ora, tutte verdi, nessun `xfail`/`skip` aggiunto |
| 13:08:01 | `scripts/l4_calibrazione_prezzo.py` (10872 B, nuovo) | **L4_calibrazione** | sì |
| 13:08:56 – 14:50:38 | `data/l2/prove/2024-25__{FUMO,3TER_BPRED,3TER_ONESTO,3TER_ONESTO_PIENO}__*/` (4 corse: `bersaglio_origine.json`, `c2_pilota_*.json`, `c2_repliche_*.parquet`, `c2_dettaglio/storia_*.csv`, `esecuzione.json`) | **L2_3ter** | sì — uscite di prova, cartella di lavoro |
| 13:11:44 | `catboost_info/{time_left.tsv, learn_error.tsv, catboost_training.json, learn/events.out.tfevents, tmp/}` | **L2_3ter**, effetto collaterale del fit (CatBoost scrive nel cwd) | sì — traccia di lavoro, non un prodotto; **residuo da ripulire in un momento di calma** (non rimosso: non è né `.pytest_cache` né un `.lock`, e il compito mi vieta altro) |
| 13:12:04 | `tests/test_l1_contratto_players.py` (7674 B, nuovo) | **L1_contratto** | sì |
| 13:14:59 | `src/fantabot/contratto_players.py` (31286 B, nuovo) | **L1_contratto** | sì |
| 13:20:07 | `scripts/f0b_build_outputs.py` (30102 B, **modificato**) | **L1_contratto** | sì — ammesso; additivo, diff verificato (§1.1) |
| 13:20:46 | `data/processed/players_{2024-25,2025-26,2026-27}.contratto.json` | **L1_contratto** | sì — file **nuovi** accanto ai parquet; i parquet restano intatti |
| 13:04:45 / 13:46:15 / 13:46:31 / 14:19:06-26 | `data/_backup_fable_20260910/l3/run_{1200,A_seme20260907,B_seme20260973}/confronto_asta_2026-27.{csv,json}` | **L3_banco_117** | sì — backup prima di scrivere, come chiesto |
| 13:46:15 | `data/l3/asta/confronto_asta_2026-27.{csv,json}` (83497 / 690 B) | **L3_banco_117** passo finale (blocco A rimesso come uscita corrente) | sì — non è file congelato |
| 14:58:18 | `data/copilot/prove/ledger_w5_8791.json`, `.buono.json` | **E (revisore)**, server di prova F6 | sì — `prove/` fuori dal congelamento, imposto dal compito |

**Nessun file estraneo ai quattro compiti più il revisore.**
**Nessun file del percorso d'asta congelato toccato** oltre alle due voci ammesse.
`tests/test_bot_l3_parita.py`, toccato stamattina alle 11:46, **non** è stato
ritoccato dopo le 13:00.

### 6.1 Cache e lock

| oggetto | stato | azione |
|---|---|---|
| `.pytest_cache` nel progetto | **assente** | nessuna da rimuovere; nessuna corsa del pomeriggio l'ha ricreata (tutte con `-p no:cacheprovider`) |
| `data/copilot/prove/ledger_w5_8791.lock` | presente dopo il `taskkill` | **RIMOSSO** |
| `data/copilot/prove/ledger_w1_8791.lock` (residuo delle 06:06) | presente | **RIMOSSO** |
| `catboost_info/` | residuo di lavoro di L2_3ter | **segnalato, non rimosso** (fuori dal mandato di pulizia) |

Dopo: `nessun .lock residuo`, `nessuna .pytest_cache`.

---

## 7. Sintesi

1. **Percorso d'asta intatto**: 31/31 voci congelate identiche; le uniche 2
   divergenze sono le due ammesse.
2. **Le due modifiche ammesse sono additive**: `f0b_build_outputs.py` provato con
   diff contro un'istantanea la cui impronta coincide con quella di riferimento;
   `l2_pilota_c2.py` solo per lettura, perché la copia di riferimento non esiste
   — limite dichiarato, non aggirato.
3. **Copilota verificato end-to-end**: 32/32, 23/23, 24/24, 25/25, tutti gli
   attesi centrati; `17 passed, 1 skipped` sulle due prove congelate; porta 8791
   rilasciata e lock ripuliti.
4. **Suite**: `1 failed, 660 passed, 2 skipped, 5 xfailed in 265.92s (0:04:25)`.
   +63 passati rispetto alle 12:10, ricostruiti esattamente (33 + 19 + 9 + 2).
   Un solo rosso, quello noto di `tests/test_bot_l3_parita.py` (`assert 121 > 146`),
   **non attribuibile a nessuno dei quattro compiti del pomeriggio**.
   Nessuna regressione.
5. **f11 vivo (exit 0), sintassi di f0b valida.**
6. **12 campioni su 12 RIPRODOTTI**, nessuna discrepanza numerica in nessuno dei
   quattro rapporti.
7. **Due segnalazioni, nessun fallimento**:
   (a) manca ancora la copia di riferimento prima di modificare un file
   sorvegliato — è la seconda volta oggi (`test_bot_l3_parita.py` a mezzogiorno,
   `l2_pilota_c2.py` ora); (b) `catboost_info/` continua a sporcare la radice del
   progetto quando gira un fit.
