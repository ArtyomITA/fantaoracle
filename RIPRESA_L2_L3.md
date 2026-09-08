# Punto di ripresa — Livello 2 rivalutato e Livello 3

Scritto il 7 settembre 2026, 22:35, su richiesta di pausa. Serve a riprendere
esattamente da qui. Niente è in sospeso a metà: quello che è stato scritto su
disco è coerente, e quello che è sbagliato è elencato sotto con il suo nome.

Regole della sessione (restano valide alla ripresa): criteri scritti **prima**
degli esperimenti in `reports/CRITERI_L2_L3.md`; un test fallito non si risolve
indebolendo il test; una soglia non si sposta dopo aver visto i risultati; il
comportamento predefinito del Copilota, i pack operativi e il mirror GitHub non
si toccano.

---

## 1. Che cosa è stato fatto e regge

| lavoro | esito | prova |
|---|---|---|
| panel: `club_id`, appartenenza, stati di convocazione | fatto | 32 casi in `tests/test_l2_panel.py`; identità 2026-27 dal 79,2% al 98,6%; zero titolari con `eleggibile == False` in tutte e cinque le stagioni |
| contratto temporale (`stato_partita`) | fatto | 380 partite per stagione a 9 date di decisione provate; le due partite del 7/9/2026 restano `da_giocare` a `as_of 2026-09-11` |
| procedura unica del modello di partita | fatto | banco e cubo con la stessa configurazione, scarto 0,000 gol di intensità (era 0,219, 16,69%) |
| invarianti fisiche del generatore | fatto e **verificato da revisore indipendente** | 0 minuti senza portiere su 28.000 squadra-partita; 117.064 eventi, 0 fuori intervallo; 2.420 espulsi, 0 sostituiti; 32.174 righe s.v., tutte con minuti > 0 |
| `gol_subiti` nel cubo, bonus porta inviolata una volta sola | fatto e **verificato** | 27.999 su 28.000 squadra-partita con somma dei gol subiti dai portieri uguale ai gol dell'avversaria; equivalenza del punteggio su quattro percorsi indipendenti, identici a meno di 1e-9 |
| verdetto appaiato del banco (F7) | fatto | `data/l2/banco_verdetto_*.csv`; ~50 numeri riverificati uno per uno dal revisore, tutti coincidono |
| esperimento G1 (calibrazione dei gol) | concluso, esito **inconcludente** | `data/l2/g1/`, 25 test in `tests/test_g1_calibrazione.py` |
| 157 test | passano | `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python -m pytest tests -q` |

**Verdetto del Livello 2, che resta valido**: il cubo batte `B` ma perde contro
`B'` (stesso simulatore con le presenze del modello valore), su CRPS e Brier, in
entrambe le stagioni, otto intervalli su otto che escludono lo zero. Non
promosso. Il vantaggio su `B` viene dalle presenze, non dal meccanismo.

---

## 2. Che cosa è sbagliato e va corretto — in ordine

Tre revisori indipendenti in sola lettura hanno controllato il lavoro. Questi
sono i loro riscontri confermati, non ipotesi.

### 2.1 Il braccio L3 del confronto d'asta misura due cose insieme — **il più grave**

`BotL3._ancora_al_piano` (in `src/fantabot/bots/bot_l3.py`) sostituisce
`self.targets` dopo il replan, e così **butta via la soluzione MILP e con essa
il pavimento di spesa `min_spend`** che `BBotCoerente` aveva imposto. Misurato
dal revisore su 50 replan: il costo dei target scende in mediana al **89,2%**
di quello pianificato dal MILP, a ogni ripianificazione.

Conseguenza: il braccio `L3` differisce da `B+` per il piano **e** per la
perdita del pavimento di spesa. La differenza −0,0625 su P(1° posto) è reale
come numero, ma **non è attribuibile alla selezione del Livello 3**.
`reports/LIVELLO3.md` §5 va corretto su questo punto.

**Correzione progettata, non ancora scritta**: invece di sostituire i target,
dare ai giocatori del piano un bonus di valore dentro la chiamata a
`optimize_roster`, così il MILP li sceglie quando sono comprabili e la
soluzione conserva `min_spend`, le quote e il budget. Serve un solo punto di
aggancio in `BBotCoerente._replan` (il dizionario `values`).

### 2.2 La diagnosi scritta su perché L3 perde è sbagliata

`bot_l3.py:175-176` conta come «piano perso» ogni giocatore uscito da
`view.pool`, ma il motore rimuove dal pool **anche i giocatori che compriamo
noi**. Il revisore ha rigiocato la replica 0 con una sonda: dei 20 «persi», 10
erano **in rosa nostra**. A fine asta L3 possiede 10-13 dei 25 del piano, non 3.

Va spezzato in due contatori distinti (`piano_ai_rivali`, `piano_miei`) e la
frase di `reports/LIVELLO3.md` §5 riscritta con i numeri veri.

### 2.3 I numeri della coda dei gol in `CRITERI_L2_L3.md` §7.6 sono sbagliati

Errore mio di misura: avevo preso `v[1]` da `cubo.risultati`, cioè **solo i gol
della squadra in trasferta**, metà campione letto come intero. Valori corretti,
misurati dal revisore sul cubo salvato (impronta `9c3a76fb1145`):

| quantità | scritto in §7.6 | vero |
|---|---|---|
| media gol | 1,4337 | **1,42604** |
| varianza | 2,1556 | **2,09318** |
| P(0 gol) | 30,39 % | **30,536 %** |
| P(>= 6 gol) | 1,829 % | **1,6036 %** |
| numerosità | «14.000 squadra-partita» | **28.000** (14.000 sono le *partite*) |
| osservato | «3 stagioni» | **8 stagioni**, 2019-20…2026-27 |

Il fatto sostanziale **regge**: intervalli di Clopper-Pearson disgiunti, la coda
del cubo resta 3,4 volte quella osservata. Ma la tabella cita l'impronta del
cubo salvato e non ne riproduce i numeri: va riscritta.

### 2.4 Due test su cinque in `tests/test_bot_l3_piano.py` girano a vuoto

Provato dal revisore con un mutation test: togliendo la guardia di budget da
`_ancora_al_piano`, tutti e cinque i test continuano a passare.

- `test_i_target_restano_dentro_le_quote_e_il_budget`: la parte quote funziona;
  l'assert sul budget è infalsificabile con quella fixture (spesa massima
  possibile 60 su 100) e per giunta controlla `q50` senza `heat`, mentre il
  codice usa `q50 * heat`.
- `test_senza_piano_il_comportamento_resta_quello_di_b_piu`: confronta
  `BotL3(piano=None)` con un altro `BotL3(piano=None)`, non con `BBotCoerente`.

Vanno riscritti perché possano fallire. **Non vanno cancellati.**

### 2.5 Anticipazione in `src/fantabot/tabellino/appartenenza.py`

`costruisci()` non accetta una data limite e `_spell_da_comparse` comprime le
comparse in un intervallo `[prima, ultima+1)`: l'appartenenza a una data viene
affermata usando comparse **posteriori**. Righe dichiarate `eleggibile` che
dipendono da prove posteriori alla data di decisione: **420** su 19.429
(2023-24), **738** su 20.131 (2024-25), **38** su 19.162 (2025-26). Scarto
massimo 1.010 giorni. `eleggibile` è il denominatore delle propensioni.

Il revisore dichiara che la sua è una **stima per difetto**: non ha potuto
rieseguire la catena di risoluzione senza modificare il modulo.

**Correzione progettata**: aggiungere agli intervalli una colonna `prova_al` =
data della prova più tarda necessaria ad affermarli (per i periodi da comparse è
`al`; per un trasferimento intermedio è `dal`; per l'intervallo iniziale è la
data del primo trasferimento), propagarla in `risolvi_molti`/`verifica_molti`,
scriverla nel panel come `eleggibile_prova_al`, e filtrare in
`partecipazione._maschera_eleggibili` con `eleggibile == True and
eleggibile_prova_al < as_of`. Così un solo panel serve tutti gli `as_of`.

**Ambiguità dichiarata, da decidere prima di scrivere il codice**: il contratto
§7.1 dice «tesserato per quel club a quella data», non «ricostruito con sole
prove anteriori alla decisione». Le due letture sono entrambe difendibili. La
seconda è quella che la direttiva §6.1 chiede.

### 2.6 Artefatti stale: cubo 2024-25 e `banco_partita`

`data/l2/banco_partita.json` registra come ingresso l'impronta `81585ec4` di
`l2_partite.parquet`; il file oggi è `f725c558`. Il cubo 2024-25 non è stato
rigenerato dopo il rifacimento del panel delle 20:50. Le sezioni §4.1, §5 e §6
di `reports/LIVELLO2.md` riportano numeri che non coincidono con gli artefatti
salvati (esempio: «+5,9% di gol di stagione» contro il **+7,58%** del file; 10
coefficienti del voto su 11 divergono; 10 scostamenti di convocazione su 10).

Vanno **rigenerati**, non riscritti a mano:

```bash
python scripts/l2_banco_partita.py --boot 2000
```
```bash
python scripts/l2_genera_cubo.py 2024-25 --sims 30
```

Poi §4.1, §5 e §6 si riscrivono sui nuovi artefatti.

### 2.7 Minori, verificati, non urgenti

- §3.2 di `LIVELLO2.md` descrive ancora gli stati **prima** della correzione
  (`non_in_rosa` 9.258), dentro un capitolo che dichiara il contratto
  realizzato. Contraddizione interna.
- §4.1 dice «bootstrap 2000 ripetizioni»: gli intervalli mostrati vengono da
  `banco_partita.json` con `boot: 1000`. Una copia a 2000 esiste in
  `data/l3/fix/configurazione/dopo_boot2000/`. Le conclusioni non cambiano.
- §4.1 dice «coincidono alla quarta cifra»: per il candidato F coincidono alla
  seconda (scarto fino a 1,9e-3).
- §5.2 dice «assist 63,7% dei gol su azione»: l'artefatto dice **71,2%**.
- `scripts/l2_banco_confronto.py:80` calcola le propensioni di `A`/`B`/`B'` con
  denominatore **tutte** le righe, senza filtro `eleggibile`, contro il
  contratto §7.1. Direzione dell'effetto: attenua, non spiega, la sovrastima
  delle presenze.
- `calendario_berger(10, 35)` non è un andata-e-ritorno: 40 coppie si
  incontrano 4 volte e 5 coppie 3 volte. Identico nei quattro bracci, quindi
  non asimmetrico, ma la docstring lo descrive male. `NOI` è sempre l'indice 9.
- `conta["fuori_piano"]` è irraggiungibile per costruzione; `budget_tempo_s`
  non è mai letto. Entrambi compaiono nel rapporto del bot come se misurassero
  qualcosa.
- `generatore.py:359-362` tronca a zero e rinormalizza invece di scartare
  l'estrazione non ammissibile (89 su 1.000 nel 2024-25). Già dichiarato in
  §7.6b; entrambe le letture danno lo stesso verdetto per G1.
- Commento obsoleto in `scripts/l3_confronto_asta.py:166-175`: dice che il cubo
  non porta i gol subiti. Ora li porta.

---

## 3. Che cosa è finito durante la pausa

**Esperimento A1** — due grandi attaccanti, provati come politica di spesa.
Concluso: 22 repliche, 66 aste su 66, 896 secondi. Artefatti in
`data/l3/asta/a1_due_attaccanti_2026-27.{csv,json}`, esito registrato in
`CRITERI_L2_L3.md` §3.9b.

| trattamento | quota d'attacco | P(1°) | spesa | attaccanti fra i 10 più cari | differenza |
|---|---|---|---|---|---|
| riferimento | 0,35-0,50 | 0,0909 | 461,7 | 0,95 | — |
| B-attacco | 0,50-0,65 | 0,0852 | 452,5 | 1,32 | −0,0057 [−0,0455; +0,0318] inconcludente |
| B-due-punte | 0,60-0,75 | 0,0318 | 441,8 | 1,50 | −0,0591 [−0,1000; −0,0239] **peggiore** |

Il vincolo è stato eseguito davvero (B-due-punte porta a casa almeno un
attaccante di prima fascia in tutte e 22 le repliche) e va peggio: perde in 16
repliche su 22. A quota 0,50-0,65 l'esito è inconcludente.

Due avvertenze su questo esito: il riferimento realizzato è **B+**, non `B`
congelato come diceva §3.9 (lo script usa `BBotCoerente` in tutti i bracci); e
il banco è il cubo, che §7 di `LIVELLO2.md` dichiara non promosso.

**Non è toccato dalle correzioni della sezione 2**: usa `BBotCoerente`, non
`BotL3`.

Nient'altro è in esecuzione. Nessun file è a metà scrittura.

---

## 4. La coda di lavoro, nell'ordine giusto

1. **Correggere `BotL3`** (§2.1 e §2.2): bonus di valore al piano dentro il
   MILP invece della sostituzione dei target; contatori `piano_ai_rivali` e
   `piano_miei` separati.
2. **Riscrivere i due test vacui** (§2.4) perché possano fallire, e aggiungere
   un test che il pavimento di spesa sopravviva all'ancoraggio.
3. **Rieseguire il confronto d'asta** con il bot corretto (22 repliche, ~21
   minuti) e riscrivere `reports/LIVELLO3.md` §5 con la diagnosi vera.
4. **Correggere `CRITERI_L2_L3.md` §7.6** con i numeri veri della coda (§2.3).
5. **Rigenerare `banco_partita` e il cubo 2024-25** (§2.6), poi riscrivere
   `LIVELLO2.md` §4.1, §5, §6 sui nuovi artefatti.
6. **Decidere l'ambiguità di §2.5**, poi correggere `appartenenza.py`,
   rigenerare i panel e tutto ciò che ne dipende (cubo 2026-27 compreso, quindi
   anche il confronto d'asta va rifatto dopo).
7. Correzioni minori di §2.7.
8. Istantanea di chiusura, aggiornamento di `INDICE.md` e `HANDOFF_SESSIONE.md`.

**Nota sull'ordine**: il punto 6 invalida gli artefatti prodotti ai punti 3 e 5.
Se si vuole evitare di rifare due volte il confronto d'asta, conviene decidere
prima il punto 6 ed eseguirlo, e solo dopo rieseguire i confronti.

---

## 5. Decisioni che aspettano il committente

1. **`eleggibile` ricostruito con quali prove** (§2.5): solo quelle anteriori
   alla data di decisione, oppure tutte quelle note oggi? La prima è più severa
   e costa una rigenerazione completa; la seconda va scritta nel contratto.
2. **`quot_fs_sett`**: nessuno snapshot fanta.soccer è anteriore all'inizio del
   campionato — il più antico ha la **stessa data** della prima giornata in
   tutte e cinque le stagioni, e non è deducibile se sia stato rilevato prima o
   dopo le partite di quel giorno. La correzione promessa nel report non è
   applicabile come descritta; il massimo ottenibile è passare da g02/g03 a g01.
   Serve la risposta della fonte sull'ora di rilevazione.
3. **Semantica della porta inviolata**: la regola scritta dice «+1 al portiere
   che gioca senza subire gol», ma non dice se il riferimento è il portiere o la
   squadra. Nel cubo 137 bonus su 8.758 vanno a portieri di squadre che hanno
   subito gol dopo la loro uscita. I tre percorsi di punteggio concordano fra
   loro; nessuno sa se concordano con la lega.
4. **Modalità delle sostituzioni** e **passo delle fasce gol**: già in sospeso
   dalla sessione precedente, mai confermati.

---

## 6. Come ripartire

```bash
python scripts/l3_manifesto.py --mostra
```

Il manifesto di sessione (`data/l3/MANIFESTO.json`) porta fasi, blocchi e
decisioni con la loro prova. Questo documento è il suo indice leggibile.
