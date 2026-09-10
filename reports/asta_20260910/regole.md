# Regolamento della lega contro il codice — verifica in sola lettura

Data: 10 settembre 2026. Nessun file del progetto è stato modificato. Le prove
eseguite stanno in questa stessa cartella:

- `ispeziona_pack.py` — carica `data/packs/pack_2026-27.pkl` e stampa quote,
  budget, campi di `Player`, campi delle predizioni, mancanti/zero per ruolo;
- `prova_regole.py` — 35 casi sulle soglie gol, sulle fasce del modificatore,
  sulla condizione «almeno 4 difensori» e sul bonus porta inviolata: **35/35**;
- `prova_cs_pack.py` — confronta i fantavoti del pack con
  `data/processed/votes_2026-27.parquet` per contare quante volte il +1 della
  porta inviolata è stato applicato;
- `prova_copilot_ctx.py` — importa `scripts/f10_copilot.py` senza avviare il
  server (nessun ledger: `LEDGER_PATH` resta `None`, quindi `save()` non
  scrive), ricostruisce l'oracolo e confronta il piano del bot con quello di
  `piani.py`.

Le etichette usate sotto: **RIPRODOTTO** = comando eseguito ed esito visto;
**OSSERVATO NEL CODICE** = letto, non eseguito; **IPOTESI** = deduzione.

## 1. Dove vive ogni regola, e se i numeri coincidono

| regola | valore di lega | dove sta nel codice | valore nel codice | coerente |
|---|---|---|---|---|
| rosa 3P/8D/8C/6A | `{"P":3,"D":8,"C":8,"A":6}` | `src/fantabot/rules.py:16`; `src/fantabot/tournament.py:33`; `scripts/f2_build_packs.py:44`; `scripts/f10_copilot.py:53` (poi sovrascritto da `PACK.quotas` alla riga 858); `scripts/f1_train_price.py:199`; `config/league.yaml:16-20`; pack | identico ovunque; `pack.quotas = {'P': 3, 'D': 8, 'C': 8, 'A': 6}` | sì |
| budget 500 | 500 crediti | `rules.py:17`; `tournament.py:34`; `f2_build_packs.py:43`; `f1_make_predictions.py:38`; `f10_copilot.py:52` (sovrascritto da `PACK.budget` alla riga 859); `livello3/valutatore.py:51`; `league.yaml:15` | 500 ovunque; `pack.budget = 500` | sì |
| 3 cambi | max 3 sostituzioni | `rules.py:18` (`MAX_SUBS = 3`), usato da `montecarlo.py:251`, `valutatore.py:52`, `tabellino/punteggio.py:103`; default letterale `3` in `season/lineup.py:66`, `season/detail.py:22`, `season/simulate.py:58` | 3 ovunque | sì (ma tre firme non importano `MAX_SUBS`) |
| soglie gol 66, poi +1 ogni 6 | 66 → 1 gol, +1 ogni 6 | `season/lineup.py:100-103` (`threshold=66, step=6`), `valutatore.py:53-54` (`soglia_gol=66`, `passo_gol=6`), `livello3/esatto.py:66-67` (`_gol_da_punti`, formula identica), `league.yaml:26-27` | 66 e 6 ovunque; `rules.py` **non** contiene queste due costanti | sì |
| fasce modificatore 6/6.25/6.5/6.75/7 → +1..+5 | tabella della lega | `rules.py:14` `MOD_DIFESA_TABLE`, letta da `season/lineup.py:18`, `valutatore.py:43`; `league.yaml:29-34`; copia identica in `scripts/indagine/diagnosi_rosa.py:73` | `[(7.0,5),(6.75,4),(6.5,3),(6.25,2),(6.0,1)]` | sì |
| modificatore solo con modulo ≥ 4 difensori | media voti puri portiere + 3 migliori difensori | `lineup.py:50-56` (scelta del modulo), `lineup.py:88-96` (punteggio), `detail.py:80-88`, `valutatore.py:171-174` via `score_giornata` | condizione `len(starters["D"]) >= 4` e `len(counted["D"]) >= 4`, media su portiere + 3 migliori | sì |
| porta inviolata +1 al portiere | +1 se ha giocato e non ha subito gol | `rules.py:15` `CLEAN_SHEET_BONUS`, `rules.py:29-46` (`clean_sheets`, `apply_clean_sheet`); `tabellino/punteggio.py:87-96`; `valutatore.py:64,165-168`; applicato al pack in `f2_build_packs.py:190-194`; applicato al bersaglio del modello in `f1_make_predictions.py:87-101` | +1.0 una sola volta per ogni via | sì |
| moduli ammessi (7) | 3-4-3, 3-5-2, 4-3-3, 4-4-2, 4-5-1, 5-3-2, 5-4-1 | `season/lineup.py:11-12` (tuple), `optimizer.py:18-20` (dizionario), `league.yaml:24` | insiemi identici (verificato) | sì |
| asta a rotazione, ruoli P→D→C→A, prezzo minimo 1, rilancio minimo 1 | | `src/fantabot/engine/auction.py:29-31` (`role_order = ROLES`, `min_price=1`, `min_increment=1`), blocchi di ruolo nella `run()`, `assert player.role == role` nel lotto; `models.py:6` `ROLES = ("P","D","C","A")`; `league.yaml:38-42` | identico | sì |
| 10 squadre | 10 partecipanti | `f2_build_packs.py:130` (`slots = quota * 10`) e `:177` (`vorp_prices(..., 10, BUDGET)`), `f1_train_price.py:199`, `league.yaml:14` | 10 | sì, ma il numero è cablato nella costruzione dei prezzi (vedi divergenze) |

Ricerca dei numeri cablati fuori da `rules.py` (`66`, `6.25`, `6.75`,
`"P": 3`, `500`): tutte le occorrenze trovate portano il valore giusto. Le
uniche righe con `6.25`/`6.75` fuori da `rules.py` sono `league.yaml` e
`scripts/indagine/diagnosi_rosa.py:73`, che riscrive la stessa tabella.
`66` compare in `lineup.py:100`, `valutatore.py:53`, `esatto.py:28,36`,
`league.yaml:26` e in commenti. Nessun valore discordante. RIPRODOTTO per le
tabelle e le soglie (`prova_regole.py`, 35/35).

## 2. Il pack 2026-27

`data/packs/pack_2026-27.pkl`, impronta `db2584ea408bb12b…` (coincide con
quella dichiarata nel contesto). RIPRODOTTO con `ispeziona_pack.py`:

- `pack.quotas = {'P': 3, 'D': 8, 'C': 8, 'A': 6}` (somma 25), `pack.budget = 500`,
  `pack.use_mod_difesa = True`, 587 giocatori, 587 predizioni, 38 giornate di
  voti e 38 di voti puri;
- `pack.b_objective = {'lam': 0.5, 'attack_share': (0.35, 0.5), 'p_win': 0.59,
  'verifica': {'p_win': 0.53, 'ic95': [0.432, 0.628], 'n_sims': 100}, 'table': [...]}`;
- campi di `Player`: `player_id, name, role, team, ref_price, ref_price_sd,
  exp_points, nuovo` (esempio: `Player(player_id='5585', name='Malen', role='A',
  team='ROM', ref_price=0.30212, ref_price_sd=0.0, exp_points=153.75, nuovo=False)`);
- chiavi di una predizione: `k, motivi, nuovo, pres, pres_gk, pts_gk, q10, q50,
  q90, sigma, value, value_modello, value_up, value_q10, value_q25, value_q75,
  value_q90`; `k = 2` per tutti (l'asta cade dopo 2 giornate reali);
- giocatori per ruolo: P 73, D 210, C 201, A 103;
- **mancanti o zero**: `value`, `value_up`, `q10`, `q50`, `q90`: zero mancanti e
  zero valori nulli in tutti i ruoli. `pres = 0` per 13 giocatori (A 6, C 3,
  P 4); `sigma = 0` per 2 difensori. Nessun campo assente;
- intervalli di `value`: P 4.0 / 9.9 / 210.7 (min/mediana/max), D 5.2 / 109.8 /
  248.6, C 4.3 / 140.7 / 262.9, A 3.2 / 127.0 / 305.2;
- somma dei `q50` = 5952.1 crediti; somma dei `ref_price` × 500 = 5304.5
  crediti (il vincolo di calibrazione è 10 × 500 = 5000 sui soli ref_price,
  ottenuto prima della correzione del bias di selezione).

## 3. Come nasce il `value` che il MILP massimizza

Catena, OSSERVATA NEL CODICE e verificata nei numeri dove indicato:

1. `scripts/f1_make_predictions.py:87-101` (`_season_votes`) legge i voti reali,
   scarta gli `sv` e **aggiunge +1 al fantavoto dei portieri con porta
   inviolata**: la regola della lega entra qui, nel bersaglio del modello.
2. `f1_make_predictions.py:125-144` (`_season_points_frame`) somma quei
   fantavoti per giocatore e separa `pts_gk` (giornate 1..K) da `points_resto`
   (giornate K+1..38).
3. `f1_make_predictions.py:251-376` (`catboost_values`) predice il **resto di
   stagione** con il blend TabPFN/CatBoost, ricalibra linearmente su fold in
   avanti, e restituisce `value = pts_gk + resto`, `value_up = value_q75`,
   `pres = pres_gk + pres_resto`, `sigma = (q90-q10)/2.56`.
4. `scripts/f2_build_packs.py:195-200` mette quelle predizioni nel pack come
   `b_predictions`, insieme a `quotas`, `budget` e `use_mod_difesa=True`.
5. Nel Copilota, `scripts/f10_copilot.py:460-468` costruisce il contesto dei
   piani con `valori = predizione["value"]`, `valori_up = predizione["value_up"]`,
   `lam` dall'obiettivo del pack, quote e budget residuo; `src/fantabot/piani.py`
   chiama `optimize_roster`.
6. `src/fantabot/optimizer.py:61-68` massimizza
   `Σ v_i · (0.30 · x_i + 0.70 · s_i)` con `v_i = value + lam · (value_up − value)`
   e `lam = 0.5`, sotto i vincoli di quota per ruolo, un solo modulo fra i sette
   e budget (`optimizer.py:70-90`).

Che cosa **è** dunque `value`: i **fantapunti di stagione attesi del singolo
giocatore** su 38 giornate (unità: fantapunti sommati, non media per partita),
di cui i primi 2 sono punti reali già realizzati (`k = 2`), con dentro il
punteggio della fonte (`tabellino/punteggio.py:63-69`) **più** il bonus porta
inviolata per i portieri. Le presenze attese sono dentro implicitamente: il
totale stagionale è già presenze × resa, e `pres` è pubblicato a parte.

Che cosa **non** contiene:

- il **modificatore difesa**: nessun modulo della catena valore/prezzo/MILP lo
  nomina (nessuna occorrenza di `mod_difesa` in `f1_make_predictions.py`,
  `f2_build_packs.py`, `optimizer.py`, `piani.py`, `bots/bot_b.py`). Il
  modificatore entra solo nella simulazione (`season/lineup.py`,
  `season/detail.py`, `montecarlo.py`, `livello3/valutatore.py`);
- la selezione degli **undici titolari** e la panchina: nel MILP entrano come
  peso `bench_weight = 0.30` (`optimizer.py:21`) e vincolo di modulo, non nel
  valore del giocatore. Il Monte Carlo degli avversari archetipo usa invece
  0.35 (`montecarlo.py:333`);
- le **sostituzioni** (3 cambi), le **fasce gol**, il calendario, la classifica.

Conseguenza: il numero che ordina i piani non è una previsione di fantapunti di
squadra. La somma grezza dei 25 valori vale 5617.0, l'obiettivo davvero
massimizzato 3642.2 (RIPRODOTTO, `prova_copilot_ctx.py`), mentre il Monte Carlo
stima ~3268 fantapunti di stagione per la rosa scelta (`pack.b_objective`,
riga `mean_pts` della combinazione vincente). Sono tre metri diversi, e solo il
secondo è quello con cui `piani.py` confronta le alternative — che è ciò che
`piani.py:20-28` dichiara.

## 4. Il modificatore difesa nel simulatore

RIPRODOTTO (`prova_regole.py`): con undici schierati e tutti i voti presenti,

- modulo con 3 difensori (3-5-2): totale 70.0 = somma dei voti, **nessun**
  bonus;
- modulo con 4 difensori e media (7+7+7+7)/4 = 7.0: totale 76.0, cioè +5;
- modulo con 4 difensori ma uno senza voto e senza riserva disponibile: nessun
  bonus (il codice richiede 4 difensori effettivamente valutati);
- modulo con 5 difensori (voti 7,7,7,5,5 e portiere 6): bonus +4, cioè media
  (6+7+7+7)/4 = 6.75 → la funzione prende davvero i **3 migliori** difensori,
  non i primi tre.

Il punto di applicazione è unico: `season/lineup.py:88-96` (`score_giornata`),
richiamato da `season/simulate.py:89`, `montecarlo.py:251`,
`livello3/valutatore.py:173`, `tabellino/punteggio.py:115`.
`season/detail.py:80-88` ne è la copia per il racconto giornata per giornata,
con la stessa condizione. In `pick_lineup` (`lineup.py:50-56`) il modificatore
entra solo come stima per scegliere il modulo, e la stima è volutamente
prudente (`media_att - 0.1`, dichiarato nel commento).

## 5. Il bonus porta inviolata è applicato una volta sola

- Il punteggio della fonte non lo contiene: `tabellino/punteggio.py:63-69`
  (`fantavoto`) ha solo `- gol_subiti` per i portieri. Il bonus è aggiunto da
  `bonus_porta_inviolata` (`:87-91`) e sommato una volta in `punti_lega`
  (`:94-96`), che è ciò che `punteggio_squadra` passa a `score_giornata`
  (`:111-116`). `score_giornata` non lo tocca mai.
- Nel pack: `f2_build_packs.py:190-194` chiama `apply_clean_sheet` una volta
  sola sui fantavoti per giornata. RIPRODOTTO (`prova_cs_pack.py`): il pack
  2026-27 differisce dal parquet dei voti in **13 righe**, tutte di portieri,
  tutte esattamente `+1`, tutte corrispondenti a una coppia (portiere,
  giornata) presente nell'insieme `clean_sheets` (13 clean sheet trovati);
  nessun clean sheet è rimasto senza bonus. Inoltre, per i 21 portieri con
  presenze nelle prime 2 giornate, `pts_gk` coincide con la somma dei fantavoti
  del pack (0 discordanze): il bonus è dentro il `value`, una volta sola.
- Nel Monte Carlo: `montecarlo.py` campiona i fantavoti dai pack delle stagioni
  precedenti (`scripts/f12_choose_objective.py:36-46`), che li contengono già
  con il +1; `score_giornata` non lo riapplica. Nessuna doppia somma.
- Nel valutatore del Livello 3: `valutatore.py:165-168` lo aggiunge una volta
  al fantavoto del cubo, e `:144-150` si ferma con un errore se il cubo non
  porta i gol subiti, invece di ignorare la regola in silenzio.

Nessun percorso che sommi il bonus due volte è stato trovato.

## 6. Ordine dei ruoli in asta

Il motore d'asta simulata rispetta il regolamento: `engine/auction.py:29-31`
usa `role_order = ROLES = ("P","D","C","A")`, `min_price = 1`,
`min_increment = 1`; la `run()` apre un blocco per ruolo e lo chiude quando
nessuno ha più slot in quel ruolo; il lotto verifica con un `assert` che il
giocatore chiamato appartenga al blocco aperto; la chiamata gira a rotazione
saltando solo chi ha il reparto pieno.

Il Copilota **non** impone né assume un ordine: registra qualunque martelletto
(`f10_copilot.py:699-772`, che controlla solo slot di ruolo e massimo legale) e
consiglia sul giocatore che gli si indica. Due assunzioni implicite, comunque,
esistono:

- `GET /copilot/nominate` usa `role = "A"` se il parametro manca
  (`f10_copilot.py:658`). La UI passa sempre il ruolo (`viz/copilot.html:1429`),
  quindi il default non morde da lì;
- `piani.scegli_bomber` (`piani.py:109-118`) costruisce ogni alternativa
  imponendo **un attaccante** titolare. Durante i blocchi P, D e C le
  alternative restano quindi ancorate al reparto che si comprerà per ultimo.
  È un vincolo dichiarato (`piani.py:195-198`), non un errore di regolamento.

## 7. Divergenze da segnalare

1. **Due piani diversi nella stessa schermata.** `BBot._replan`
   (`bots/bot_b.py:102-112`) applica la quota d'attacco dell'obiettivo
   (`attack_share = (0.35, 0.50)` → fra 175 e 250 crediti in attacco);
   `contesto_piani` (`f10_copilot.py:464-468`) costruisce il `Contesto` senza
   `forced_spend`, quindi `piani.py` risolve **senza** quel vincolo.
   RIPRODOTTO (`prova_copilot_ctx.py`, MILP con `time_limit=20`, stato a zero
   acquisti): il piano di `piani.py` costa 500.0 con 93.0 crediti in attacco
   (18.6 % del budget) e obiettivo 3642.2; il piano del bot costa 499.1 con
   191.4 in attacco e obiettivo 3624.4; **12 giocatori su 25 sono diversi**.
   La UI mostra entrambi: `/copilot/plan` (piano del bot, riga 1379 di
   `copilot.html`) e `/copilot/piani` (riga 1066). I max bid del banco
   (`/copilot/advice`) vengono dal bot, quindi seguono il primo.
2. **`min_spend` non arriva mai ai piani del Copilota.** `contesto_piani` legge
   `obiettivo.get("min_spend")`, ma `pack.b_objective` non ha quella chiave
   (chiavi presenti: `lam`, `attack_share`, `p_win`, `verifica`, `table`):
   `ctx.min_spend` risulta `None` (RIPRODOTTO). La soglia
   `MIN_SPEND_FRAC = 0.95` di `rules.py:26` è applicata solo in
   `montecarlo.py:371`, cioè in `f12_choose_objective`, che `RIPRESA_ASTA.md`
   dichiara fuori dalla catena di aggiornamento. Oggi non morde (il piano
   spende comunque 500.0 su 500), ma il vincolo dichiarato non è attivo.
3. **Il modificatore difesa non entra nel piano.** Il `value` massimizzato è
   individuale; il modificatore vale fino a +5 per giornata (fino a ~190 punti
   di stagione a squadra) e non compare in nessun ingresso del MILP. Il piano
   non distingue quindi una difesa da media voto alta da una equivalente in soli
   fantapunti individuali. Il modificatore incide solo sulla scelta di
   `(lam, attack_share)` fatta dal Monte Carlo. IPOTESI sull'effetto pratico:
   sottopeso sistematico di portieri e difensori con voto puro alto e pochi
   bonus; non misurato qui.
4. **Costanti duplicate invece che importate.** `MAX_SUBS` non è usato nelle
   firme di `lineup.py:66`, `detail.py:22`, `simulate.py:58` (tutte con `3`
   letterale); le soglie gol non stanno in `rules.py` ma come default in
   `lineup.py:100` e in `valutatore.py:53-54`, con una seconda implementazione
   identica in `esatto.py:66-67`; quote e budget sono riscritti in
   `tournament.py:33-34`, `f2_build_packs.py:43-44`, `f10_copilot.py:52-53`,
   `f1_train_price.py:199`; i moduli esistono in due forme (`lineup.py:11` e
   `optimizer.py:18`). Oggi tutti i valori coincidono (verificato), ma cambiare
   `rules.py` da solo non li cambierebbe. `config/league.yaml` è allineato in
   ogni voce (verificato a runtime) e dichiara già di non essere la fonte.
5. **Numero di squadre cablato a 10 nella costruzione dei prezzi**
   (`f2_build_packs.py:130,177`, `f1_train_price.py:199`), mentre
   `/copilot/setup` accetta qualunque numero di nomi ≥ 2
   (`f10_copilot.py:239-241`) e qualunque budget ≥ somma delle quote
   (`:245-254`). Con un tavolo diverso da 10 squadre, o con un budget diverso da
   500, i `q50`/`ref_price` del pack resterebbero tarati sul mercato 10×500
   senza che nulla lo segnali. Per l'asta di stasera (10 squadre, 500 crediti)
   la condizione è rispettata.
6. **Pack demo con modificatore dichiarato e voti puri assenti.**
   `scripts/f6_live_auction.py:375` costruisce il pack demo con
   `voti_by_g=None, use_mod_difesa=d["use_mod_difesa"]`: se quel flag è vero, il
   modificatore risulterebbe attivo ma non calcolabile
   (`score_giornata` lo salta quando `voti_puri is None`). In quella via la
   stagione post-asta è comunque disattivata, quindi non morde. OSSERVATO NEL
   CODICE.
