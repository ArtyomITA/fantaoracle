# R — pannello RIGORISTI dinamico

Fatto, verificato. 10/9/2026 17:2x.

## Fonte

`data/raw/mercato/rigoristi_20260910.csv` (il piu' recente; l'altro e' `rigoristi_20260901.csv`).
20 squadre, colonne `squadra,rigorista_1..3,punizioni_1..3`.
**Non agganciati: 0** (120 nomi su 120 mappati a un `player_id` del pack).

Aggancio: stessa logica di `scripts/f9_apply_market.py` — mappa `SIGLE` nome intero -> codice
(`Atalanta` -> `ATA`), chiave di cognome (`surname_key`: «Martinez L.» -> «MARTINEZ», toglie
l'iniziale <= 2 caratteri), candidati per (cognome, squadra) e in mancanza per solo cognome,
disambigua col nome completo normalizzato. Unica differenza: l'indice e' costruito su
`PACK.players` invece che su `registry.csv`, perche' l'id che serve al Copilota e' quello del pack
(= master_id = id fantacalcio.it). `norm` e' importata da `fantabot.market_adjust`, non ricopiata.

## Modifiche

### `scripts/f10_copilot.py` (+148 righe, 0 tolte)

| blocco | righe nuove | cosa |
|---|---|---|
| `@@ -21,9 +21,12` | 3 | riga di documentazione dell'endpoint + `import csv` |
| `@@ -46,6 +49,7` | 1 | `from fantabot.market_adjust import norm as norm_mercato` |
| `@@ -170,6 +174,7` | 1 | `costruisci_rigoristi()` in coda a `prepara_pack` |
| `@@ -192,6 +197,147` | 141 | `SIGLE_MERCATO`, `COLONNE_RIGORI/PUNIZIONI`, `RIGORISTI`, `RIGORISTI_FONTE`, `_chiave_cognome`, `costruisci_rigoristi`, `stato_rigorista`, `rigoristi_ora` |
| `@@ -941,6 +1087,8` | 2 | ramo `elif u.path == "/copilot/rigoristi": self._send(rigoristi_ora())` in `_get` |

Diff completo: `w7/f10.diff`.

`RIGORISTI` (costruita una volta, al caricamento) tiene solo la lista e l'ordine:
`[{"squadra_codice","squadra_nome","rigoristi":[{nome,player_id}],"punizioni":[...]}]`.
Lo stato NON e' precalcolato: `rigoristi_ora()` lo ricava a ogni richiesta da `STATE["events"]`,
`STATE["my_index"]`, `ELEGGIBILITA` e `STATE["esclusi_manuali"]`, quindi cambia a ogni martelletto
e torna indietro con l'undo.

`GET /copilot/rigoristi` ->
```
{"data":"2026-09-10","file":"rigoristi_20260910.csv","non_agganciati":[],
 "squadre":[{"squadra_codice":"ATA","squadra_nome":"Atalanta",
   "rigoristi":[{"nome":"Scamacca","player_id":"2137","stato":"disponibile",
                 "ruolo":"A","squadra":"ATA","agganciato":true}, ... 3 voci],
   "primo_disponibile":"2137",
   "punizioni":[... 3 voci], "primo_disponibile_punizioni":"..."} ... 20 righe]}
```
Precedenza dello stato: venduto (`"mio"` se `team_index == my_index`, altrimenti
`"venduto a <nome squadra>"`) > `"fuori lista"` (esclusi della fonte, esclusi a mano, nome non
agganciato) > `"indisponibile"` > `"disponibile"`.
`primo_disponibile` = primo dell'ordine con stato esattamente `"disponibile"` (quindi un
indisponibile viene saltato), altrimenti `null`.

### `viz/copilot.html` (+89 righe, 0 tolte)

| blocco | righe nuove | cosa |
|---|---|---|
| `@@ -587,6 +587,22` | 16 | CSS `#rigOut`, `.rig-row`, `.rig-n` (`.libero` verde grassetto, `.venduto` barrato, `.mio` giallo, `.grigio`), `.rig-legend` |
| `@@ -664,6 +680,11` | 5 | `<section class="panel" id="rigoristi"><h3>RIGORISTI</h3>` subito sotto «PIANI CON BOMBER DIVERSI», + legenda |
| `@@ -837,6 +858,9` | 3 | in `onState`: `rigSig = n_events + "/" + esclusi_manuali.length`, ricarica solo se cambia |
| `@@ -1778,6 +1802,71` | 65 | `RIG`, `caricaRigoristi`, `classeRigorista`, `marcatoreRigorista`, `renderRigoristi`, listener di click su `#rigOut` |

Diff completo: `w7/copilot.diff`.

Riga: codice squadra + i tre rigoristi nell'ordine della fonte. Marcatori: nome della squadra che
l'ha comprato accanto al barrato, `mio`, `⚠` per l'indisponibile, `fuori lista` / `non in lista`.
Click sul nome -> `GET /copilot/advice?player_id=..&price=1` -> `selectPlayer(a, 1)`: il giocatore
va al banco con i suoi dati veri. Le punizioni sono nell'endpoint ma non nel pannello (la specifica
UI chiede i tre rigoristi per riga).

### `tests/test_copilot_asta.py` (+35 righe, 0 tolte)

`test_rigoristi_stato_segue_il_martelletto`: 20 squadre, 0 non agganciati, `primo_disponibile` e
`primo_disponibile_punizioni` non nulli a tavolo vuoto per tutte e 20; hammer di ATA/rigorista_1
(Scamacca 2137) a `team_index 1` -> stato `"venduto a T1"` e `primo_disponibile` = Krstovic (6435);
undo -> torna Scamacca, stato `"disponibile"`.

## Prove eseguite

| comando | esito |
|---|---|
| `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python -m pytest tests/test_copilot_asta.py -q -p no:cacheprovider` | **12 passed, 1 skipped** (13 raccolti; erano 12 raccolti = 11 passed + 1 skip) |
| `python scratchpad/verifica_f1f2.py` | **32/32** |
| `python scratchpad/verifica_f5bis.py` | **23/23** |
| `python scratchpad/verifica_f5_asta.py` | **24/24** |
| `python w7/verifica_rigoristi_ui.py` (Chrome headless 1366x768, server 8794, ledger `data/copilot/prove/ledger_w7_rig.json`) | **11/11** |

Pagina vera (11/11): 20 righe disegnate, tre nomi per riga, ogni squadra con un primo disponibile
in verde, testata «— fonte del 2026-09-10»; click su «Scamacca» lo porta al banco; martelletto
dalla pagina a Marco per 30 -> `Scamacca` barrato (`text-decoration-line: line-through`) con
«Marco» accanto, `Krstovic` diventa verde grassetto, endpoint coerente
(`primo_disponibile 6435`, `stato "venduto a Marco"`); **console senza errori**.

Artefatti: `w7/rigoristi.png`, `w7/rigoristi_dopo_hammer.png`, `w7/srv_rig.log`,
`w7/verifica_rigoristi_ui.py`, `w7/proto_rig.py`, `w7/*.diff`.

Server 8794 fermato, `.lock` rimosso, nessun processo in LISTENING su 8794.

## Note

- Stato dei rigoristi_1 a tavolo vuoto (dal pack + fonti del 10/9): 18 su 20 `disponibile`;
  `indisponibile` per BOL Orsolini, LEC Geubbels (per queste due il primo disponibile e' il
  secondo, Bernardeschi e Stulic). Nessun rigorista_1 fuori lista.
- `import` di `fantabot.market_adjust` porta dentro pandas: **+1,0 s all'avvio** del Copilota
  (misurato). Scelto per non ricopiare `norm` e non farla divergere da f9.
- File veri `data/copilot/ledger_*.json` non toccati; nessun push, nessuna rigenerazione del pack.
- Backup pre-modifica: `data/_backup_fable_20260910/pre_rigoristi/{f10_copilot.py,copilot.html,test_copilot_asta.py}`.
