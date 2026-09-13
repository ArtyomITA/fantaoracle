# FIX Z — server e correzioni, 13/9/2026

Agente Z. Porte usate: **8791, 8792** (fermate a fine prova). Mai 8770, mai
8899. I tre ledger veri in `data/copilot/` non sono stati toccati: le prove
girano su copie troncate in `data/copilot/prove/Z_1.json` (190 eventi) e
`Z_2.json` (100 eventi). Nessuna modifica a pack, parquet, f0b/f1/f2/f9/f12,
`viz/ponte_fantaasta.js`, `viz/asta.html`, `viz/index.html`,
`scripts/fantaoracle_app.py`.

Scratch:
`C:\Users\ADMINI~1\AppData\Local\Temp\claude\E--claudecode-pesante\5ff20539-b495-4ac4-bed4-79eabbf8a8b7\scratchpad\w12\Z\`

---

## Z1 — il tetto sul banco non sfarfalla piu' (V1, grave)

**Dove**: `scripts/f10_copilot.py`, `_lavora_indifferenza` e
`scalda_indifferenza`.

Il difetto: a fine bisezione il codice faceva `INDIFF_CACHE.clear()` e poi
riscriveva la sola chiave appena calcolata. Ogni calcolo che finiva buttava
via i risultati di **tutti gli altri giocatori dello stesso stato**, compreso
quello al banco; e siccome `advice()` chiama `scalda_indifferenza("A", 3)` a
ogni richiesta, la pagina alternava «pronto 289» e «in calcolo 272» ogni due
secondi.

Correzione:

* si potano **solo** le chiavi di versione diversa da quella corrente, mai le
  vive (`for chiave in [k for k in INDIFF_CACHE if k[0] != corrente]`);
* `scalda_indifferenza` scatta la versione una volta sola, salta chi e' gia'
  in cache **o gia' in `INDIFF_IN_CORSO`**, e accende **un** calcolo per giro
  (il secondo posto del semaforo resta al giocatore al banco).

**Prova sul server vero** (porta 8791, `--resume data/copilot/prove/Z_1.json`,
190 eventi; 16 `GET /copilot/advice?player_id=5585&price=150` a due secondi
l'una):

```
 0 in_calcolo   ind None  tetto 272   (82 ms)
 1 pronto       ind 244   tetto 289   (18 ms)
 2..15 pronto   ind 244   tetto 289   (3-19 ms)
distinti dopo la prima pronta: {('pronto', 244, 289)}
```

Prima: `289 / 272` alternati per tutte e 16 le chiamate (misura del
verificatore). Ora: **un solo valore su 15 letture**.

Test aggiunto: `tests/test_copilot_tetto.py::test_il_tetto_non_sfarfalla_fra_una_chiamata_e_l_altra`
(in-process, 8 chiamate consecutive dopo la prima «pronto», un valore solo;
piu' il controllo che in cache restino almeno **2** chiavi vive della versione
corrente e nessuna di versioni superate — la seconda faccia dello stesso
difetto, per cui il pre-riscaldamento cancellava cio' che aveva scaldato).

---

## Z2 — il premio di scarsita' vuole lo storico di gol (V3)

**Dove**: `scripts/f10_copilot.py`: nuova `storico_gol(pid, ruolo)`,
`tetto_scarsita(..., storico_gol=True)`, `decisione_operativa`,
`_lavora_indifferenza` (la foto porta `storico_gol`).

Regola nuova, in una riga: **il premio di scarsita' e il pavimento del prezzo
di indifferenza si applicano solo a chi ha gia' fatto gol da bomber in Serie
A**, cioe' `gol_tot_2025 >= SOGLIA_GOL[ruolo]` (10 per A, 6 per C). Chi e'
bomber per il solo passo del 2026-27 (tre giornate proiettate su trentotto)
**resta `e_bomber=True`** — conta nel pool, tiene il badge in UI — ma prende
`quota_scarsita = 0`, `premio_scarsita = 0`, e il tetto torna quello del bot.
`motivo_tetto` lo dichiara: «bomber solo per il passo 2026: nessun premio di
scarsita'. Resta il tetto del bot N, su M spendibili (pareggia a P)».

Il prezzo di indifferenza si continua a calcolare e a mostrare: e'
informazione utile («oltre questa cifra il piano senza di lui vale uguale»),
non piu' un pavimento per chi ha tre giornate di curriculum.

Campo nuovo, additivo, in `/copilot/advice` e in `tetto_scarsita`:
`storico_gol` (bool).

**Replay** (`PYTHONPATH=src python reports/asta_20260913/replay_tetto.py`,
28 attaccanti battuti a 40+):

| lotto | pagato | tetto prima | tetto dopo |
|---|---|---|---|
| Malen (ev 190) | 275 | 289 | **289** (>= pagato) |
| Martinez L. (ev 193) | 255 | 300 | **300** (>= pagato) |
| Hojlund (ev 200) | 200 | 219 | **219** (>= pagato) |
| Raimondo (ev 199) | 80 | 251 | **42** (< 120) |
| gli altri 24 | — | — | invariati |

Tetti sopra il massimo spendibile: **0**. «Arriva al prezzo» 7 su 28 (era 8:
l'unico perso e' Raimondo, pagato 80 con un tetto vecchio di 251).

Simeone (11 gol) e Davis K. (10) **hanno** lo storico e restano come prima
(57 su 63 e 49 su 63): la regola chiesta li lascia dov'erano, e i tre lotti
da difendere non si toccano.

`reports/asta_20260913/replay_tetto.md` rigenerato dallo script, piu' una
sezione «Nota sulla correzione V3» che spiega cosa e' cambiato.

Test aggiunti in `tests/test_copilot_tetto.py`:
`test_tetto_scarsita_senza_storico_resta_il_tetto_del_bot` (funzione pura),
`test_raimondo_bomber_solo_del_passo_2026`,
`test_chi_ha_lo_storico_non_perde_il_premio` (Malen 275, Martinez L. 255,
Hojlund 200).

---

## Z3 — la riga «con lui / senza di lui» non sembra piu' una smentita (V2)

**Dove**: `viz/copilot.html`, una riga sola in `adviceExtra` (nient'altro nel
file).

Prima: `con lui a 289: 4685 pt · 18 gol | senza: 5243 pt · 24 gol`, letta
sotto un «RILANCIA fino a 289». Ora:

```
senza di lui il miglior piano fa 5243 pt · 24 gol in attacco · pareggi a 244;
oltre paghi la scarsità
```

Il confronto al tetto era corretto ma spaventava: al tetto il piano con lui
vale meno per costruzione, perche' il tetto e' un limite e non un prezzo
consigliato. La riga nuova dice il numero che serve a decidere (quanto vale la
rosa senza di lui) e dove sta il pareggio.

---

## Z4 — un test non scrive piu' in `viz/` (V5)

**Dove**: `tests/test_ponte_fantaasta.py::test_pagina_contiene_link_e_istruzioni`.

`pb.scrivi_pagina(8770)` riscriveva `viz/ponte.html` a ogni passata di pytest.
Ora la destinazione si sposta in `tmp_path` con `monkeypatch.setattr(pb,
"PAGINA", ...)`: **nessuna asserzione indebolita** (sono le stesse sette di
prima, piu' il controllo che il file finisca davvero nella cartella
temporanea).

Verificato: `viz/ponte.html` resta a mtime `2026-09-13 15:11:40`, 36 550 byte,
prima e dopo `pytest tests/test_ponte_fantaasta.py` (5 passed).

---

## Z5 — `POST /copilot/evento_modifica`: correggere QUALSIASI lotto

Il 10/9 spostare il lotto 42 e' costato 81 annullamenti e 82 martelletti,
perche' la sola correzione era `undo`, che toglie dalla coda.

### Contratto

`POST /copilot/evento_modifica`

```json
{"indice": 42, "team_index": 0, "price": 12, "rimuovi": false,
 "richiesta_id_modifica": "cli-mod-42-1789..."}
```

* la riga si indirizza con `indice` (posizione in `STATE["events"]`) **oppure**
  con `richiesta_id` (quello del martelletto originale; dev'essere unico);
* `team_index`, `price`, `rimuovi` sono tutti facoltativi, ma almeno uno serve;
* `richiesta_id_modifica` rende la richiesta ripetibile: la seconda volta
  torna `{"ok": true, "duplicato": true}` senza secondo effetto (stessa
  meccanica di `undo_fatti`, in `STATE["modifiche_fatte"]`).

Risposta: `{ok: true, indice, prima, dopo, n_events}`; `dopo` e' `null` se la
riga e' stata tolta. In caso di rifiuto: **400** `{ok: false, err: motivo}`.

### Come valida

Tutto sotto `LOCK`. Si costruisce la lista **candidata** e la si valida per
intero con la nuova `valida_eventi(candidata)`, che replica `teams()` sulla
candidata invece che sullo stato corrente. Rifiuta se: prezzo non intero o
sotto 1, `team_index` inesistente, giocatore sconosciuto o aggiudicato due
volte, un reparto oltre la quota, una cassa negativa, o una squadra che non
potrebbe piu' riempire gli slot che le restano a un credito l'uno (stesso
criterio di `stato_valido`). Se e' valida: `STATE["events"] = candidata`,
`STATE["modifiche"].append({ts, indice, prima, dopo})`, `save()` (con rollback
se il disco fallisce), `PIANI_CACHE` e `INDIFF_CACHE` svuotate,
`rebuild_advisor()`.

### Aggiunte additive intorno

* `GET /copilot/eventi` -> lista completa: `indice`, `player_id`, `nome`,
  `ruolo`, `squadra` (il club, come ovunque in questa API), `team_index`,
  `acquirente` (la squadra di fantacalcio), `prezzo`, `ts`, `richiesta_id`.
* `/copilot/state`: `last_events[i]` e ogni riga di `teams[i].roster[R]` hanno
  ora `indice` e `richiesta_id`, cosi' la pagina puo' indirizzare la modifica
  da un clic sulla rosa. `last_events` prima aveva
  `id/nome/team_index/price/ts` (verificato): i due campi si aggiungono, non
  sostituiscono niente.

### Prove

`tests/test_copilot_modifica.py`, **9 test verdi**, su copia del ledger vero
troncata a 100 eventi (mai l'originale):

| caso | esito |
|---|---|
| (a) evento 42 (Tavares N. 5620) cambia squadra | D 8->7 di chi lo perde, 7->8 di chi lo prende, casse ±12, `n_events` 100 invariato, rose e budget di `/copilot/state` coerenti, modifica a verbale e su disco, cache svuotate |
| (b) hammer di Stones (2514) a 2 sullo slot liberato | prima **400** «reparto D pieno», dopo la modifica **200 ok**, `n_events` 101 |
| (c) solo il prezzo (indice 10, +37) | cassa -37, squadra e reparti invariati |
| (d) rimozione a meta' lista (indice 50) | `n_events` 99, giocatore di nuovo nel pool, cassa restituita, gli indici successivi scalano |
| (e) modifica illegale | **400** e stato bit per bit invariato: reparto pieno, prezzo 999 oltre cassa, prezzo 0, squadra 99, indice 9999, «niente da modificare», «quale riga?» |
| (f) stessa `richiesta_id_modifica` due volte | seconda risposta `duplicato: true`, nessun secondo effetto, una sola voce in `modifiche` |
| (f2) indirizzare per `richiesta_id` | trova l'indice 42; un id inesistente -> 400 |
| (g) `/copilot/eventi` | 100 voci, indici 0..99 crescenti, campi coerenti con `last_events` |
| (h) `undo` dopo una modifica | toglie sempre l'ultimo, la correzione resta |

**Nota sui numeri del compito**: l'evento 42 del ledger vero e' Tavares N.
(5620) ma appartiene alla squadra **5** (Nightmare fc), non alla 0; ai 100
eventi la 5 ha la difesa piena (8) e la 0 ne ha 7. Il verso utile e' quindi
`5 -> 0`, e il martelletto successivo (Stones) entra sulla **5**, che e' quella
che ha liberato lo slot. Il resto della prova e' quello chiesto.

---

## Z6 — `asta_registra.py`: correggere da terminale

Comandi nuovi, nello stile del file:

```bash
python scripts/asta_registra.py --elenco                    # indici di tutti gli acquisti
python scripts/asta_registra.py --modifica "42 > Nightmare : 12"
python scripts/asta_registra.py --rimuovi 42
```

Dopo l'indice le due parti sono facoltative: `"42 > Nightmare"` sposta e basta,
`"42 : 12"` cambia solo la cifra. `--elenco` e' stato aggiunto perche' senza
di lui l'indice, da terminale, non si vede da nessuna parte (`--stato` mostra
gli ultimi cinque acquisti, e il lotto da correggere quasi mai e' fra gli
ultimi cinque).

Prova sul server 8792 (100 eventi):

```
  OK Tavares N. (D LAZ) indice 42: Nightmare fc 12 -> Ac Mignottingham Forest 12
  RIFIUTATO Solet (D UDI) indice 43 -> Ac Mignottingham Forest: il reparto D
            andrebbe a 9 su 8 (400)
  OK Tavares N. (D LAZ) indice 42: Ac Mignottingham Forest 12 -> ... 20
  TOLTO Tavares N. (D LAZ) indice 42: era di Ac Mignottingham Forest a 20.
        Acquisti: 99
```

**Difetto trovato e corretto durante la prova**: l'identificativo di
idempotenza era `cli-mod-{indice}-{int(time.time())}`. Due correzioni sulla
stessa riga nello stesso secondo (cambia il prezzo, poi toglila) avevano lo
stesso identificativo e la seconda tornava indietro come «duplicato» senza
fare niente — riprodotto: `--rimuovi 42` rispondeva «Acquisti: 100». Ora si
usa `time.time_ns()`.

`GUIDA_ASTA.md`, sezione «Registrare dal terminale»: tre righe di comandi piu'
la spiegazione delle parti facoltative e di cosa il server rifiuta.

---

## Prove finali

| cosa | comando | esito |
|---|---|---|
| test | `PYTHONPATH=src PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python -m pytest tests/test_copilot_asta.py tests/test_copilot_tetto.py tests/test_copilot_modifica.py tests/test_ponte_fantaasta.py -p no:cacheprovider -q` | **43 passed, 1 skipped**, 25,4 s |
| vicini di casa | `... pytest tests/test_bot_l3_tetti.py tests/test_l3_indifferenza.py ...` | 55 passed, 2,7 s |
| replay | `PYTHONPATH=src python reports/asta_20260913/replay_tetto.py` | 28 lotti, 7 arrivano, **0 tetti sopra lo spendibile**, Raimondo 42, Malen/Martinez L./Hojlund invariati |
| stabilita' del tetto | server 8791, 16 advice a 2 s | **1 solo valore** dopo la prima risposta pronta (era 289/272 alternati) |
| endpoint di modifica | server 8792 + `asta_registra.py` | sposta, cambia prezzo, rimuove, rifiuta l'illegale |

L'unico skip e' quello pre-esistente
(`tests/test_copilot_asta.py:141: nessun attivo senza previsione`).

Server fermati: **8791, 8792** (verificato: nessun processo `f10_copilot`
residuo, lock `Z_1.lock`/`Z_2.lock` rimossi). Ledger di prova lasciati in
`data/copilot/prove/Z_1.json` e `Z_2.json`; i tre ledger veri hanno mtime
invariato.

---

## File toccati

| file | cosa |
|---|---|
| `scripts/f10_copilot.py` | Z1 (potatura per versione, pre-riscaldamento), Z2 (`storico_gol`, `tetto_scarsita`), Z5 (`valida_eventi`, `indice_eventi`, `POST /copilot/evento_modifica`, `GET /copilot/eventi`, `indice`+`richiesta_id` in `/copilot/state`) |
| `viz/copilot.html` | Z3, la sola riga del confronto in `adviceExtra` |
| `tests/test_copilot_tetto.py` | 4 test nuovi (Z1, Z2) |
| `tests/test_copilot_modifica.py` | nuovo, 9 test (Z5) |
| `tests/test_ponte_fantaasta.py` | Z4, `tmp_path` + `monkeypatch` |
| `scripts/asta_registra.py` | Z6, `--elenco`, `--modifica`, `--rimuovi` |
| `GUIDA_ASTA.md` | Z6, sezione «Registrare dal terminale» |
| `reports/asta_20260913/replay_tetto.md` | rigenerato + nota V3 |
| `reports/asta_20260913/FIX_Z.md` | questo |
