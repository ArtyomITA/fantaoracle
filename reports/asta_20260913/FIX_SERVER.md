# FIX SERVER — tetto, gol, bonus di lega (13/9/2026)

Progetto `fantabot`. Interventi additivi sul Copilota
d'asta: nessuna politica del bot rimossa, nessun file fuori dall'elenco
concordato toccato, `viz/copilot.html` NON toccato (lo fa l'agente UI).

File modificati:

| file | che cosa |
|---|---|
| `src/fantabot/rules.py` | costanti `BONUS_GOL_FONTE = 3.0`, `BONUS_GOL_LEGA = 5.0` |
| `scripts/f10_copilot.py` | bonus gol, gol in `player_info`, calore per ruolo, bomber, prezzo di indifferenza, tetto nuovo, `/copilot/gol_rosa`, campi nuovi in `/copilot/state` e `/copilot/advice`, `ordina=` in `/copilot/players`, quota d'attacco sul residuo |
| `src/fantabot/bots/bot_b.py` | solo `_replan`: quota d'attacco sul budget residuo (voce I) |
| `src/fantabot/piani.py` | solo `piano_al_prezzo`: parametro additivo `calcola_riferimento` |
| `tests/test_copilot_tetto.py` | nuovo, 12 prove sullo stato vero del 10/9 |
| `reports/asta_20260913/replay_tetto.py` + `replay_tetto.md` | replay lotto per lotto |

---

## 1. Che cosa cambia, difetto per difetto

### D1 — il tetto non sapeva niente di cassa, slot, scarsita'
`decisione_operativa` (f10) continua a chiedere al bot il suo tetto per
bisezione — quella politica non si tocca — e poi lo usa come **pavimento**:

```
tetto = min(max_spendibile, max(cap_bot, round(p_ind + s * (max_spendibile - p_ind))))
```

`tetto_scarsita(...)` e' una funzione **pura** (f10), provata sugli otto casi
del prototipo dell'audit. Il ramo «obbligo di completare» resta il primo e
ritorna sempre il massimo legale.

### D2 — il calore era uno solo per tutto il mercato
Nuove `calore_ruolo(R)` / `calore_per_ruolo()`: prezzi battuti su q50 **dentro
il ruolo**, prior 60 crediti verso 1.0, limiti 0.5-2.0, e **1.0 quando in quel
ruolo non e' stato battuto niente** (mai il calore globale di un altro blocco).
`BBot.market_heat()` non e' stata toccata: il calore per ruolo e' privato al
Copilota (`cap_col_calore`), quindi la parita' con L3 regge.
Effetto misurato all'evento 190: calore A **1.0** contro lo 0.667 globale, e
il tetto del bot su Malen passa da 116-122 a **182**.

### D3 — l'obbligo contava le teste
Restano `liberi_ruolo` (il ramo obbligo, invariato) e in piu' `bomber_nel_pool`,
che conta chi **fa gol davvero**: e' quello che entra nella scarsita'.

### D4 — `attack_share` sul budget totale
`contesto_piani` (f10) e `BBot._replan` (bot_b) ora calcolano il tetto della
quota d'attacco sul **residuo**: se non restano slot fuori dall'attacco, hi =
tutta la cassa; altrimenti hi = min(quota storica, residuo - slot altrove).
Prova diretta sul server di prova, stato ev190: il piano di riferimento spende
**315.1** in attacco (prima non poteva superare 250) e
`/copilot/piano_prezzo?player_id=5585&prezzo=275` risponde `ok` **senza**
`vincolo_attacco_rilassato`. Le due funzioni sono identiche e
`test_piani_riferimento_uguale_al_piano_del_bot` le confronta: verde.

### D5/D6 — i gol non arrivavano ai consigli
`campi_gol` guadagna `gol_tot_2025` / `gol_tot_2026` (gol **piu' rigori**:
nella fonte sono due colonne, e contare solo la prima toglie 3 gol a Malen e 11
alla rosa dell'utente). `player_info` ora include tutti i campi gol, `bomber`,
`gol_attesi`, `bonus_gol_lega`: quindi li hanno `/copilot/players`,
`/copilot/advice`, `/copilot/plan`, `/copilot/state.teams[].roster` e l'export.
`/copilot/players` accetta `ordina=value|gol|misto`.
`/copilot/state` porta `spendibile`, `calore_per_ruolo`, `scarsita` e i gol per
squadra; nuovo endpoint `/copilot/gol_rosa`.

### D7 — il prezzo di indifferenza costa secondi
`prezzo_indifferenza(pid, foto)` risponde **subito** (`in_calcolo`) e lancia un
thread demone fuori dal lock: riferimento = miglior piano **senza di lui**
(`pn._risolvi(banned={pid})`), poi bisezione con `piano_al_prezzo`
(`calcola_riferimento=False`, il piano libero non si ricalcola dieci volte),
al massimo 10 MILP da 2 s, semaforo a 2 solutori. Cache
`INDIFF_CACHE[(versione_stato(), pid)]`, svuotata a ogni martelletto, undo o
esclusione. Pre-riscaldamento dei primi 3 bomber del pool, ma **solo quando
non c'e' gia' un calcolo in corso**: prima il giocatore al banco, che aspettava
11 secondi mentre tre pre-riscaldamenti gli rubavano il solutore; adesso
**2,1 s** (misurato sul server di prova, porta 8792).

### D8 — il bonus gol di lega
`applica_bonus_gol` (f10, dentro `prepara_pack`, dopo `costruisci_gol` e prima
della rettifica indisponibili) aggiunge `(5 - 3) * gol_attesi` a `value`,
`value_modello`, `value_up` e ai quantili di valore. I **prezzi non si
toccano**. `PACK.b_predictions` resta il dato del modello: il bonus vive nella
copia `PRED_ATTIVE`. Riga stampata all'avvio:

```
bonus gol lega (+5 contro +3 della fonte): P 0 rettificati, +0.0 medio,
D 69 rettificati, +3.3 medio, C 110 rettificati, +5.5 medio, A 64 rettificati, +10.5 medio
```

Esempi: Malen 300.2 -> **333.8** (16,8 gol attesi), Martinez L. 267.2 -> 302.6,
Hojlund 237.6 -> 260.4, Adopo (1 gol) 199.7 -> 201.4, chi non ha storico +0 e
`gol_attesi: null` (mai zero al posto di «non lo so»).

---

## 2. Due scostamenti dal contratto, con la prova

**(a) `e_bomber`, passo 2026-27.** Il contratto dice
`pres_2026 >= 2 e gol_2026/pres_2026*38 >= SOGLIA`. Preso alla lettera, con tre
giornate giocate **un** gol proietta 12,7 gol stagionali: all'evento 190
sarebbero «bomber» **27 attaccanti su 86**, Osmajic e Ramos G. compresi, che in
Serie A non hanno mai segnato. Con 27 bomber la quota di scarsita' e' 0 sempre
e il premio non scatta mai; peggio, Osmajic riceverebbe il trattamento da
bomber e il suo tetto salirebbe (la prova 3 chiede <= 10).
Aggiunta: `MIN_GOL_2026_BOMBER = 3`, cioe' il passo 2026 chiede anche tre gol
gia' fatti. Conteggio all'evento 190: **11** invece di 27; Osmajic e Ramos G.
restano fuori, Raimondo (4 gol in 3 giornate) entra.

**(b) `bomber_rimasti` = sostituti, non categoria.** Il compito si aspettava
«fra 5 e 12» all'evento 190 (il conteggio largo: 11, esposto come
`bomber_pool_ruolo` sia in `advice` sia in `state.scarsita.A.bomber_pool`). Ma
la scarsita' che decide quanto pagare **un** giocatore si misura sui suoi
sostituti: sopra i 14 gol di Malen ne restavano **tre**. Col conteggio largo la
quota resta 0 in ogni istante dell'asta vera (11 bomber contro 6 compratori) e
il premio non scatta mai — proprio la sera in cui il tavolo si scannava per due
nomi; il caso T1 del prototipo, del resto, si chiama «Malen unico bomber».
`bomber_rimasti` e' quindi il numero di bomber **con almeno i suoi gol**, e la
formula `quota = (contendenti + 1 - bomber_rimasti) / (contendenti + 1)` resta
vera **sui campi che l'API pubblica**. Prova: `replay_tetto.md`, dove col
conteggio largo il tetto arrivava al prezzo in **0** dei 4 lotti citati e con
questo in **3**.

Terzo aggiustamento minore, sempre dichiarato: per chi **non** e' bomber il
prezzo di indifferenza non si calcola affatto (`stato_indifferenza:
"non_applicabile"`) e il tetto resta `cap_bot`. E' il comportamento dei casi T6
e T7 del prototipo, che passano `prezzo_indifferenza = 0`, ed e' cio' che tiene
Osmajic a 4 crediti invece che al suo prezzo di indifferenza da MILP.

---

## 3. Esiti delle prove

Comandi eseguiti dalla radice, `PYTHONPATH=src PYTEST_DISABLE_PLUGIN_AUTOLOAD=1
python -m pytest ... -p no:cacheprovider -q`.

| prova | esito |
|---|---|
| `tests/test_copilot_tetto.py` (nuovo, 12 test) | **12 passed** |
| `tests/test_copilot_asta.py` (esistenti, non indeboliti) | **13 passed, 1 skipped** |
| le due insieme | `25 passed, 1 skipped in 13.52s` |
| `tests/test_bot_l3_piano.py` | **14 passed** |
| `tests/test_bot_l3_parita.py` + `tests/test_bot_l3_tetti.py` | `1 failed, 49 passed in 89.46s` |

L'unico rosso e' `test_bot_l3_parita.py::test_il_piano_cambia_davvero_l_asta`
(`L3 impegna sul piano 105 crediti, B+ ne impegna 180`). **Non e' mio**:
rimettendo `data/_backup_fable_20260913/bot_b.py` al posto del file nuovo la
prova fallisce con gli stessi identici numeri (105 contro 180). Era gia' rossa
il 10/9 ed e' fuori scopo.

Numeri chiave delle prove nuove (stato ricostruito dal ledger vero
`data/copilot/ledger_1789058317.json`, mai modificato):

- Malen, evento 190, offerta 274: `max_spendibile` 311, `calore_ruolo` 1.0,
  `cap_bot` **182** (era 116), `bomber_pool_ruolo` 11, `bomber_rimasti` 3,
  `squadre_contendenti` 5, prima risposta in **15 ms** con
  `stato_indifferenza: "in_calcolo"`; dopo il poll `prezzo_indifferenza` **244**
  e `max_consigliato` **278** (dal server, con la stessa offerta al banco),
  `con_lui {prezzo 278, gol_2025 18}` contro `senza_di_lui {gol_2025 24}`.
- Osmajic (205 di valore, zero minuti in Serie A): `max_consigliato` **4**.
- Giocatore senza previsione: `max_consigliato` <= 5.
- Hojlund, subito prima del suo martelletto: `max_consigliato` **219** (era
  102, pagato 200).
- Fine asta (2 crediti, 2 slot): nessun crash, tetto 1 su 1 spendibile.
- `/copilot/gol_rosa` sul ledger completo: TonyDaMilano **74** gol 2025-26
  (28 dagli attaccanti), 1° su 10, `senza_dato` 3 con i nomi; Nightmare fc 40,
  10°; as tavolato 38 gol dagli attaccanti. Sui gol 2026-27 la stessa rosa e'
  **ultima** con 3: i due numeri vanno letti insieme.
- Tempi in processo sul ledger completo: `/copilot/state` 4,4 ms,
  `/copilot/players?role=A` 0,4 ms, `/copilot/gol_rosa` 0,7 ms,
  `/copilot/advice` 15 ms. Dal server HTTP: state 62 ms, advice 36 ms,
  `/copilot/piani?quanti=2` 357 ms.

### Server di prova
Porte 8791 e 8792, ledger `data/copilot/prove/S_1.json` (copia del ledger vero
troncata ai primi 190 eventi). Provati dal vivo: `state`, `advice` (con poll
fino a `pronto`), `players?ordina=gol`, `gol_rosa`, `plan`, `piani`,
`piano_prezzo`, `hammer` + `undo`. **Entrambi i server sono stati fermati** e
il ledger vero non e' mai stato aperto in scrittura.

### Replay
`reports/asta_20260913/replay_tetto.py` -> `replay_tetto.md`: 28 attaccanti
battuti a 40 crediti o piu'.

- il tetto arriva al prezzo del tavolo in **8** casi su 28 (prima
  praticamente mai sui lotti grossi);
- sui quattro lotti della diagnosi **3 su 4**: Malen 289 >= 275,
  Martinez L. 300 >= 255, Hojlund 219 >= 200; **Ramos G. 201 contro 205**, a
  quattro crediti;
- **nessun tetto sopra il massimo spendibile** (0 su 28), che era il vincolo
  duro.

---

## 4. Cosa resta aperto

1. **Ramos G. (205) resta fuori di 4 crediti.** Non e' un bomber per la fonte:
   in Serie A non ha mai giocato, quindi nessun premio di scarsita'. Il suo 201
   viene tutto dal calore di ruolo. Per prenderlo servirebbe una misura di
   «bomber atteso» che non sia il campionato italiano dell'anno scorso (gol nei
   campionati esteri), e nel progetto quel dato non c'e'.
2. **Raimondo esce a 251 ed e' andato a 80.** Il prezzo di indifferenza lo
   promuove perche' il MILP lo ama (valore alto, prezzo previsto basso) ed e'
   bomber per il passo 2026. E' un tetto, non un'offerta: non fa perdere
   crediti da solo, ma va guardato all'asta.
3. **La quota di scarsita' e' 0 su quasi tutti i lotti.** Quello che alza il
   tetto oggi sono il calore di ruolo e il prezzo di indifferenza; la scarsita'
   entra solo sui pochissimi nomi di testa. Va bene cosi' fino a prova
   contraria, ma e' il pezzo meno esercitato dai dati veri.
4. **`gol_attesi` e' un proxy dichiarato**, non un modello di gol: tasso
   dell'anno scorso sulle presenze previste, tetto +20%, e per chi ha solo il
   2026-27 il tasso di tre giornate scontato del 30%. Malen prende 16,8 gol
   attesi: generoso.
5. **Il bonus gol vive solo nel Copilota.** La catena a monte
   (`f0b_build_outputs` scarta le colonne dei gol dal parquet) continua a
   produrre `value` con +3 per gol: se un giorno si vuole il bonus dentro il
   modello, va rifatta li' — fuori dai file che potevo toccare.
6. **`test_bot_l3_parita.py::test_il_piano_cambia_davvero_l_asta`** resta rossa,
   come era prima di questo lavoro (verificato col file di backup).
