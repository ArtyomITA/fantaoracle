# C — revisione finale prima dell'asta (10/9/2026, 16:15-17:05)

VERDETTO: VIA LIBERA. Nessun fallimento. Le sole differenze di file sono le tre ammesse dal compito A;
i diff riguardano solo l'indicatore «chi puo' superarti»; suite e prove del Copilota verdi (unico rosso
preesistente e fuori dal Copilota); 3 campioni su 3 RIPRODOTTI; macchina pulita.

## 1. Impronte — 26 voci di w4/impronte_asta.json

Ricalcolo sha256 su fantabot.

| esito | voci |
|---|---|
| UGUALE | 23 |
| DIVERSO | 3: `scripts/f10_copilot.py`, `viz/copilot.html`, `tests/test_copilot_asta.py` |
| MANCANTE | 0 |

Le tre differenze sono esattamente quelle ammesse (compito A). Nessuna differenza estranea → nessun FALLIMENTO.

Ledger veri intatti:
- `data/copilot/ledger_1788290734.json` ee4d7e819b854348a1196e4b180ac43d7f58081f44234e591f36eab9fa2dde3e (uguale a w4)
- `data/copilot/ledger_1788548783.json` 198e1b9b99bc8933147700e3eb895cabc4d8935e6db9a33d3af7fd1431049e37 (uguale a w4)

Impronte aggiornate: `w6\nuove_impronte_asta.json` (26 voci). Nuove:
- scripts/f10_copilot.py 3e2d3539f8bb4ca116e935e2d96a31181193d862736bcd3d74972995fa1962d0
- viz/copilot.html 6ca182754f5960a2f5a0dad776aae0a6ce61675214be32792203528c4527d919
- tests/test_copilot_asta.py 344424872c5e6d724dce92454b9e1ed4b55ca4fa3a9d4a3b68b216ff6b61fc12

Ricontrollo a fine lavoro: 0 scostamenti (nessuna prova ha toccato i file del prodotto).

## 2. Diff contro data/_backup_fable_20260910/pre_indicatore/

Copie in `w6\rev_diff_f10.patch` e `w6\rev_diff_html.patch`.

### scripts/f10_copilot.py — 86 righe di patch, 37 righe aggiunte, 5 righe sostituite, 5 hunk
1. `@@ -431,+455` nuova funzione `concorrenti_sopra(v, ruolo, tetto)` (24 righe, docstring compresa): conta gli
   avversari con `slots_left(...) > 0` e `max_bid(...) >= tetto+1`, ritorna `concorrenti_sopra_tetto`,
   `concorrenti_nomi` (primi 5 per max_bid decrescente), `concorrenti_max`; tetto <= 0 → 0/[]/0.
2. `@@ -455` dict `fuori`: i tre campi a 0/[]/0 + 2 righe di commento.
3. `@@ -491` uscita obbligo: `**concorrenti_sopra(v, ruolo, max_legale)`.
4. `@@ -519` uscita normale: `**concorrenti_sopra(v, ruolo, tetto)`.
5. `@@ -567` `plan()`: `dec = decisione_operativa(pid, None)`, `cap = dec["max_consigliato"]`, i tre campi
   propagati nella riga di target.

Nessuna riga estranea: tutte e cinque le zone toccano solo l'indicatore. Politica, tetti e azioni invariati
(`max_consigliato` e `azione` restano calcolati come prima).

### viz/copilot.html — 2 hunk, 11 righe aggiunte, 2 sostituite
1. `renderAdvice`: riga meta «possono superarti: N (nomi)» in `var(--peach)`, ramo alternativo
   «nessuno puo' superarti» in `var(--green)` quando N = 0 e `max_consigliato > 0`.
2. `renderPlan`: `<sup>` arancione col conteggio dentro lo `<span class="mx">` esistente, `title` = nomi.

Nessuna colonna nuova, griglia `.trow` invariata, nessuna riga estranea.

## 3. Prove del Copilota

| prova | esito | atteso | ok |
|---|---|---|---|
| pytest tests/test_copilot_asta.py tests/test_rettifica_indisponibili.py -q -p no:cacheprovider | `18 passed, 1 skipped, 24276 warnings in 7.95s` | verde | si |
| — di cui test_copilot_asta.py | `11 passed, 1 skipped` (skip preesistente `test_senza_previsione_registrabili`) | | si |
| — di cui test_rettifica_indisponibili.py | `7 passed` | | si |
| — nuovo test dell'indicatore (`-k concorrenti`) | `1 passed, 11 deselected` | | si |
| verifica_f1f2.py | `32/32 verificati`, EXIT=0 | 32/32 | si |
| verifica_f5bis.py | `23/23 verificati`, EXIT=0 | 23/23 | si |
| verifica_f5_asta.py | `24/24 verificati`, EXIT=0 | 24/24 | si |
| verifica_f6.py (server 8791, ledger data/copilot/prove/ledger_w6_rev.json) | `25/25 verificati`, EXIT=0 | 25/25 | si |

Server 8791: PID 30940 fermato, `ledger_w6_rev.lock` rimosso, porta 0 LISTENING.

## 4. Suite completa

Comando: `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTHONIOENCODING=utf-8 python -m pytest tests -q -p no:cacheprovider`
(cwd fantabot). Uscita in `w6\suite_tests.txt`.

Riga finale esatta:

```
1 failed, 661 passed, 2 skipped, 5 xfailed, 633756 warnings in 267.27s (0:04:27)
```

Confronto con le 15:00 (1 failed, 660 passed, 2 skipped, 5 xfailed): +1 passed = il nuovo
`test_concorrenti_sopra_tetto` aggiunto da A. Nessun nuovo rosso.

Attribuzione del rosso: `tests/test_bot_l3_parita.py::test_il_piano_cambia_davvero_l_asta`
— `AssertionError: L3 impegna sul piano 121 crediti, B+ ne impegna 146 ... assert 121 > 146`
(tests\test_bot_l3_parita.py:448). Preesistente (stesso singolo rosso delle 15:00), riguarda il braccio di
ricerca L3 contro B+, non tocca `f10_copilot.py` ne' `viz/copilot.html`: nessuna relazione con A o B.
Skip: 2 (uno e' `test_senza_previsione_registrabili` del Copilota, preesistente). xfailed: 5, invariati.

ATTENZIONE (nota d'ambiente, non un difetto del prodotto): `python -m pytest -q` dalla radice, cioe' senza
l'argomento `tests`, finisce a `37 errors during collection` — pytest raccoglie anche la copia dell'albero
sotto `data\istantanee\20260906_2102\file\`, che mette la propria `src` in `sys.path` e nasconde
`fantabot.bots.bot_l3` e `fantabot.tabellino` (`import file mismatch` su
`scripts/test_download_fantasoccer.py`). La suite va lanciata come sopra, con `tests`.

## 5. Campioni riesguiti (server di prova 8794, ledger data/copilot/prove/ledger_w6_camp.json)

Script `w6\campioni.py`, esiti `w6\campioni_esiti.json`. Lega 10x500, quote 3/8/8/6, io = 0.

| campione | origine | osservato ora | esito |
|---|---|---|---|
| C1 indicatore a tavolo vuoto su Malen (id 5585) | A | `concorrenti_sopra_tetto=9`, nomi `['Marco','Luca','Giulia','Andrea','Sara']`, `concorrenti_max=476`, `max_consigliato=174` | RIPRODOTTO |
| C2 anomalia «480 non registrabile» | A | POST /copilot/hammer price 480 → HTTP 400 `Giulia: 480 supera il massimo legale 476 (restano 25 slot)`; price 476 → HTTP 200, budget squadra 3 = 24, max_bid = 1 | RIPRODOTTO |
| C3 export dichiara pack e fonti | B | impronta `71ec262b4bdfa1925851184ac23566b909ff7006d53e9f5badc83097c64fb2f3`, pack `pack_2026-27.pkl`, fonti `2026-09-09T22:35:18`, `listino_consultabile` 594 righe, 11 ms | RIPRODOTTO |

3 / 3 RIPRODOTTI. Server 8794: PID 8832 fermato, `ledger_w6_camp.lock` rimosso, porta 0 LISTENING.

## 6. Stato finale della macchina

- Processi python di fantabot vivi: NESSUNO (restano solo `teams_scribe\mcp_server.py` e i proxy MCP, estranei).
- Porte 8770 / 8791 / 8794 / 8899: 0 LISTENING ciascuna.
- `data/copilot/prove/`: 0 file `.lock`.
- `.pytest_cache`: 0 (tutte le corse con `-p no:cacheprovider`).
- `data/copilot/` contiene: `ledger_1788290734.json`, `ledger_1788548783.json`, `eleggibilita_2026-27.json`,
  `note_esperto_2026-27.json`, `listino_offline_2026-27.html`, `formazione_2026-27_G4.md`, cartella `prove/`.
  Nessun altro ledger fuori posto → nessun FALLIMENTO.
- Nessun file del progetto modificato da C (verificato col ricalcolo delle 26 impronte a fine lavoro).

## File di questo compito

- `w6\nuove_impronte_asta.json`
- `w6\C_revisione.md`
- `w6\rev_diff_f10.patch`, `w6\rev_diff_html.patch`
- `w6\suite_tests.txt` (corsa buona), `w6\suite_completa.txt` (corsa dalla radice, con i 37 errori di raccolta)
- `w6\campioni.py`, `w6\campioni_esiti.json`
- `w6\srv_rev_8791.log`, `w6\srv_camp_8794.log`
- prove: `data/copilot/prove/ledger_w6_rev.json`, `data/copilot/prove/ledger_w6_camp.json` (+ copie `.buono.json`)
