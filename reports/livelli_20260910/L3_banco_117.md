# L3 — banco appaiato B contro L3, corsa ad alta precisione del 10 settembre 2026 (pomeriggio)

Compito A (L3). Sola misura: **nessuna attivazione nel Copilota**, nessun file
del percorso d'asta congelato toccato, nessun file sotto `scripts/`, `src/`,
`tests/` modificato.

Marche: **RIPRODOTTO** (comando eseguito oggi, esito riportato), **OSSERVATO NEL
CODICE** (letto in un file, con riga), **IPOTESI** (dedotto, non provato).

Criteri di accettazione congelati **prima** dei numeri in
`…/scratchpad/w5/criteri_prima_L3.md` (scritti alle 13:10, con l'emendamento del
disegno alle 13:10, prima di qualsiasi aggregato). Il criterio di verdetto non è
inventato qui: viene da `reports/CRITERI_L2_L3.md` §3.6 (righe 182-190), ripreso
da `reports/livelli_20260910/L3.md` §6 e da `L3_banco.md` §0.

---

## 0. Che cosa doveva decidere questa corsa, e come è finita

Il run delle 12:00 (22 repliche, 44 aste) dava L3 − B = **−0,02955**, IC95
**[−0,10000, +0,03185]**, semiampiezza **0,06592**: inconcludente, e disegno
dichiarato insufficiente perché 0,06592 > 0,030. La stessa analisi stimava in
**117 repliche** il campione necessario per una semiampiezza di 0,030.

**Esito. La precisione richiesta è stata raggiunta — semiampiezza 0,02719 ≤
0,030 su 132 repliche appaiate — e il verdetto è INCONCLUDENTE: L3 − B =
−0,02273, IC95 [−0,05019, +0,00418]. L3 non è promosso (l'intervallo non è
positivo) e non è bocciato (l'intervallo non è interamente negativo). Non scrivo
«equivalenti».**

---

## 1. Backup, fatto prima di ogni scrittura (passo 1)

RIPRODOTTO. Lo script sovrascrive `data/l3/asta/confronto_asta_2026-27.{csv,json}`
(`scripts/l3_confronto_asta.py:407,439`), quindi le uscite del run delle 12:00
sono state copiate **prima** del lancio:

| copia | origine | data | md5 |
|---|---|---|---|
| `data/_backup_fable_20260910/l3/run_1200/confronto_asta_2026-27.csv` | `data/l3/asta/…` | 10/9 11:59, 27.907 byte | `38978ff7865b3170395ee29dc0a6426f` |
| `data/_backup_fable_20260910/l3/run_1200/confronto_asta_2026-27.json` | `data/l3/asta/…` | 10/9 11:59, 692 byte | `8ca61c5ef2f50eaf49d6abd0950c8dd8` |

Le copie del 7/9 22:13 restano dove erano (`data/_backup_fable_20260910/l3/`),
non toccate.

---

## 2. Il disegno: perché 117 repliche in un comando solo non erano eseguibili

RIPRODOTTO. Primo tentativo, lanciato alle 13:05 con gli argomenti del run delle
12:00 letti dal suo JSON (`scenari 40`, `seme 20260907`, `trattamenti B L3`,
`piano data/l3/pilota/rosa_migliore.json`, nessun file di tetti perché il JSON
delle 12:00 porta `"tetti": {"file": null, "caricato": false}`) e `--repliche 117`:

```
PYTHONIOENCODING=utf-8 PYTHONPATH=src OMP_NUM_THREADS=3 python -u \
scripts/l3_confronto_asta.py --stagione 2026-27 --repliche 117 --scenari 40 \
  --seme 20260907 --trattamenti B L3 --piano data/l3/pilota/rosa_migliore.json
```

Ritmo misurato sulle prime 12 aste: **16,17 s/asta** (alle 12:00 erano 13,3 s,
con un agente in meno sulla CPU). 117 repliche = **234 aste** ≈ **63 minuti**,
oltre il tetto dei 45 minuti per comando. Il tentativo è stato **fermato alle
13:08 dopo 12 aste**; il suo log resta in
`…/scratchpad/w5/log_banco_117_fermato.txt`.

Il ripiego «tieni le prime k repliche leggendole dal log», previsto al §5 dei
criteri, è **inutilizzabile per un verdetto** e va detto: il log riga per riga
(`scripts/l3_confronto_asta.py:394-396`) porta P(1), speso e punti a giornata, ma
**non** porta `rapporto_bot`, quindi `piano_non_classificati` e
`pavimento_violato` — due controlli di validità obbligatori — non sarebbero
verificabili. Il CSV, che li porta, è scritto **solo a fine corsa**. Un verdetto
senza i suoi controlli di validità non si scrive.

Disegno adottato (scritto nei criteri §5-bis alle 13:10, prima di ogni
aggregato): due blocchi appaiati, ciascuno sotto i 45 minuti, verdetto sul
**pool**.

| blocco | seme | repliche | aste | calendario del banco |
|---|---|---|---|---|
| **A** | 20260907 | 66 | 132 | lo stesso del run 12:00 e del 7/9 |
| **B** | 20260973 (= 20260907 + 66) | 66 | 132 | **un altro** calendario |

OSSERVATO NEL CODICE, `scripts/l3_confronto_asta.py:298`:
`cal = V.calendario_berger(10, n_g, seme=a.seme)` — il calendario della lega
dipende dal seme, quindi il blocco B è un **secondo banco**, non la continuazione
del primo. I semi di replica dei due blocchi sono disgiunti
(`seme = a.seme + rep`, `:352`), le sedie ruotano allo stesso modo
(`seggio = rep % 10`, `:353`); avversari, pack, cubo e piano sono gli stessi.

Conseguenza dichiarata, non nascosta: **il pool stima la differenza appaiata
media su due calendari**, non su uno. È una quantità leggermente diversa da
quella delle 12:00. Per questo il rapporto riporta sempre tutti e tre i numeri —
blocco A, blocco B, pool — con l'ordine di lettura fissato prima, e nessuno dei
tre scelto dopo aver visto quale conveniva.

---

## 3. Validità delle corse (criterio V1-V5, controllato per primo)

RIPRODOTTO dai due CSV e dai due log.

| controllo | blocco A | blocco B |
|---|---|---|
| aste concluse | **132 su 132**, zero righe con `errore` | **132 su 132**, zero righe con `errore` |
| repliche scartate per «giocatori fuori dal cubo» | **0** | **0** |
| repliche scartate per «rose illegali» | **0** | **0** |
| `piano_non_classificati` (braccio L3) | **0** su 66 aste | **0** su 66 aste |
| `pavimento_violato` (braccio L3) | **0** su 66 aste | **0** su 66 aste |
| `offerte_con_tetto_indifferenza` | 0 (nessun tetto caricato, come dichiarato) | 0 |

**V1-V5 soddisfatti** per quanto è misurabile. Lacuna dichiarata, la stessa delle
12:00: per il braccio **B** il CSV porta `rapporto_bot = {}` — OSSERVATO NEL
CODICE, `scripts/l3_confronto_asta.py:258`
(`nostro.rapporto() if hasattr(nostro, "rapporto") else {}`), e `BBot` congelato
non espone `rapporto()`. Quindi per B `piano_non_classificati` e
`pavimento_violato` sono **non misurati**, non zero; lo zero che l'analisi somma
per B è assenza di dato, non una misura. Per B valgono i due controlli esterni:
asta conclusa e rose legali (`V.verifica_rose` gira su entrambi i bracci,
`:374-379`).

---

## 4. Tabella dei trattamenti

Blocco A (66 repliche, 132 aste), blocco B (66 repliche, 132 aste), pool (132
repliche, 264 aste; medie semplici dei due blocchi, che hanno la stessa
numerosità).

| grandezza | B — blocco A | L3 — blocco A | B — blocco B | L3 — blocco B | **B — pool** | **L3 — pool** |
|---|---|---|---|---|---|---|
| P(1°) medio | 0,1739 | 0,1557 | 0,1667 | 0,1394 | **0,1703** | **0,1475** |
| errore standard medio di P(1°) per asta | 0,0548 | 0,0521 | 0,0545 | 0,0468 | 0,0547 | 0,0495 |
| punti di stagione medi | 2493,9 | 2488,2 | 2494,3 | 2487,2 | 2494,1 | 2487,7 |
| punti a giornata | 71,253 | 71,091 | 71,267 | 71,064 | 71,260 | 71,077 |
| gol a giornata | 1,4418 | 1,4253 | 1,4405 | 1,4148 | 1,4412 | 1,4201 |
| speso medio | 370,7 | 417,1 | 366,7 | 407,9 | 368,7 | 412,5 |
| residuo medio | 129,3 | 82,9 | 133,3 | 92,1 | 131,3 | 87,5 |
| secondi per asta | 13,76 | 18,70 | 12,48 | 16,94 | 13,12 | 17,82 |

Diagnostica del piano, braccio L3 (somma → media per asta):

| contatore | blocco A (66) | blocco B (66) | pool per asta |
|---|---|---|---|
| `crediti_sul_piano` | 8081 → 122,44 | 8998 → 136,33 | **129,39** |
| `piano_miei_dopo` | 500 → 7,58 | 507 → 7,68 | **7,63** |
| `piano_ai_rivali` | 959 → 14,53 | 950 → 14,39 | **14,46** |
| `piano_disponibili` | 191 → 2,89 | 193 → 2,92 | **2,91** |
| `ricalcoli_con_piano` | 3497 → 52,98 | 3432 → 52,00 | **52,49** |
| `piano_non_classificati` | 0 | 0 | **0** |
| `pavimento_violato` | 0 | 0 | **0** |

Il trattamento è davvero applicato (52 ricalcoli con piano per asta, 7,6
giocatori del piano in rosa) e la contabilità resta chiusa. I valori per asta
coincidono con quelli delle 12:00 (123,55 / 7,55 / 14,50 / 2,95 / 52,14): il
braccio L3 si comporta allo stesso modo su un campione sei volte più grande.

Costante in tutti i blocchi: **L3 spende di più e tiene meno residuo** (pool
412,5 contro 368,7 di B, cioè +43,8 crediti) e ottiene **meno** punti a giornata
(71,077 contro 71,260, cioè −0,18).

---

## 5. Differenza appaiata e IC95

Stima fissata prima (criteri §4) e identica a quella dello script
(`scripts/l3_confronto_asta.py:421-433`): differenza replica per replica,
bootstrap **4000** sulla media, percentili 2,5 e 97,5, seme 20260907. Nessuna
replica esclusa.

| campione | n repliche | L3 − B | sd delle differenze | IC95 | semiampiezza | esclude lo zero |
|---|---|---|---|---|---|---|
| blocco A | 66 | −0,01818 | 0,16086 | [−0,05720, +0,01894] | 0,03807 | no |
| blocco B | 66 | −0,02727 | 0,15985 | [−0,06477, +0,01288] | 0,03883 | no |
| **pool A+B** | **132** | **−0,02273** | **0,15981** | **[−0,05019, +0,00418]** | **0,02719** | **no** |

Repliche vinte da L3 / pari / peggio: blocco A **29 / 9 / 28**; blocco B
**23 / 8 / 35**; pool **52 / 17 / 63**.

I due blocchi concordano: le due differenze (−0,018 e −0,027) stanno bene dentro
l'intervallo l'una dell'altra, e le `sd` sono praticamente identiche (0,16086 e
0,15985), cioè il secondo calendario non cambia la variabilità.

---

## 6. Verdetto, secondo il criterio scritto prima

| criterio (congelato) | esito |
|---|---|
| V1-V5 — validità della corsa | **soddisfatti** (§3); unica lacuna dichiarata: `rapporto_bot` vuoto per B |
| promozione — differenza positiva con IC95 che esclude lo zero | **non soddisfatto**: la differenza è negativa e l'IC contiene lo zero |
| bocciatura — IC95 interamente negativo | **non soddisfatto**: il limite superiore è **+0,00418** |
| inconcludente — IC95 che contiene lo zero | **è questo il verdetto** |
| precisione — semiampiezza ≤ 0,030 | **soddisfatto per la prima volta**: **0,02719** sul pool (0,06592 alle 12:00, 0,03807 e 0,03883 sui blocchi presi da soli) |

**VERDETTO: INCONCLUDENTE, con il disegno finalmente abbastanza preciso.** Va
letto per quello che dice e per quello che non dice:

- che cosa **si può** dire: con 132 repliche appaiate, un vantaggio di L3
  maggiore di **+0,004** di P(1°) è fuori dall'intervallo, e così un danno
  maggiore di **−0,050**. Il centro della stima resta **negativo** (−0,023) e lo
  è in tutti e tre i campioni misurati oggi, come lo era alle 12:00 (−0,030) e il
  7/9 (−0,063);
- che cosa **non** si può dire: che L3 e B siano equivalenti. L'intervallo
  contiene lo zero, non lo dimostra; contiene anche −0,05, che è un peggioramento
  reale. «Inconcludente» resta «inconcludente»;
- il criterio non è stato spostato: la soglia 0,030 era scritta prima ed è
  soddisfatta; il criterio del segno era scritto prima e non è soddisfatto in
  nessuna delle due direzioni.

Stima di campione per il futuro, dagli stessi dati (**IPOTESI** quanto
all'estrapolazione, non quanto ai fattori): con `sd = 0,15981`,
`n = (1,96 × 0,15981 / 0,030)² ≈ 109` repliche per una semiampiezza di 0,030 —
coerente con le 117 stimate alle 12:00 su `sd = 0,16487`. Per **bocciare** L3,
cioè per un IC interamente sotto lo zero attorno a una differenza di −0,023,
servirebbe una semiampiezza sotto 0,0227, cioè
`n = (1,96 × 0,15981 / 0,02273)² ≈ **190 repliche**` (380 aste, ≈ 1 h 38 min al
ritmo medio di oggi, 15,47 s per asta). Non è un risultato ottenuto: è quanto
costerebbe ottenerlo.

---

## 7. Confronto con il 7/9 e con le 12:00

| | 7/9 22:13 | 10/9 12:00 | 10/9 blocco A | 10/9 pool A+B |
|---|---|---|---|---|
| bot | difettoso (pre-8/9) | corretto 8/9 | corretto 8/9 | corretto 8/9 |
| cubo / pack | 587 / vecchio | 594 / `71ec262b4bdf…` | 594 / `71ec262b4bdf…` | 594 / `71ec262b4bdf…` |
| repliche | 22 | 22 | 66 | 132 |
| L3 − B | −0,0625 | −0,02955 | −0,01818 | **−0,02273** |
| IC95 | [−0,11480, −0,01929] | [−0,10000, +0,03185] | [−0,05720, +0,01894] | **[−0,05019, +0,00418]** |
| semiampiezza | 0,0478 (sd 0,11896) | 0,06592 | 0,03807 | **0,02719** |
| esito secondo il criterio | bocciatura | inconcludente | inconcludente | **inconcludente** |
| P(1°) B / L3 | 0,0943 / 0,0318 | 0,1898 / 0,1602 | 0,1739 / 0,1557 | 0,1703 / 0,1475 |
| speso B / L3 | 429,6 / 370,7 | 372,9 / 422,3 | 370,7 / 417,1 | 368,7 / 412,5 |

Due precisazioni che impediscono di leggere questa tabella come una serie di
misure indipendenti:

1. **Il blocco A contiene il run delle 12:00.** RIPRODOTTO: unendo i due CSV
   sulle 44 righe comuni (22 repliche × 2 trattamenti), `p1` e `speso`
   coincidono **esattamente** (scarto massimo 0,0 e 0) e i seggi combaciano. Il
   banco è deterministico dato il seme: le 22 repliche delle 12:00 sono le prime
   22 del blocco A, non un campione a parte. Il passaggio da −0,02955 a −0,01818
   è quindi l'effetto delle **44 repliche aggiunte**, non una seconda misura
   della stessa cosa. È anche una prova di riproducibilità del percorso: stesso
   comando, stesso seme, stessi numeri.
2. **La bocciatura del 7/9 non si riproduce**, e resta vero quanto già scritto
   in `L3_banco.md` §4.5: fra il 7/9 e oggi cambiano insieme tre cose (le
   correzioni del bot dell'8/9, il pack del 10/9, il cubo rigenerato il 10/9),
   quindi la differenza fra −0,0625 e −0,0227 non è attribuibile a nessuna di
   esse in particolare. Il livello assoluto di P(1°) è quasi raddoppiato per
   entrambi i bracci: non è lo stesso banco.

Che cosa aggiunge questa corsa rispetto alle 12:00: alle 12:00 il verdetto era
inconcludente **e** il disegno insufficiente, quindi il numero non pesava nulla.
Oggi il disegno è sufficiente per la soglia scritta prima, e il verdetto resta
inconcludente: è un'informazione nuova, perché adesso l'intervallo esclude
qualunque miglioramento apprezzabile di L3 (limite superiore +0,004).

---

## 8. Differenze per famiglia di avversari e per seggio

**Le famiglie non sono un fattore incrociabile in questo disegno, e il CSV non le
porta.** OSSERVATO NEL CODICE, `scripts/l3_confronto_asta.py:66-67`: la lista
`AVVERSARI` è costante — `A`, `C:stars_scrubs`, `C:informato`, `C:semitop`,
`C:medio`, `C:panic`, `C:ancorato`, `C:tirchio`, `C:tifoso` — e **tutti e nove
siedono in ogni asta**. Non esistono repliche «contro la famiglia top» da
confrontare con repliche «contro la famiglia valore»: c'è una sola composizione
del tavolo. Le colonne del CSV sono
`replica, trattamento, seggio, p1, p1_se, punti_stagione, punti_giornata,
gol_giornata, speso, residuo, parita_al_primo, rapporto_bot, secondi`: nessuna
colonna di famiglia. Il criterio §3.6 chiede la promozione «su tutte le stagioni
e le famiglie riportate»: qui la famiglia è una sola combinazione, e questo
limita l'estensione del verdetto, in entrambe le direzioni.

L'unico fattore di disegno che varia fra repliche è il **seggio** (`rep % 10`).
Scomposizione sul pool (RIPRODOTTO, `…/scratchpad/w5/analisi_seggi.py` e
`analisi_pool.py`):

| seggio | repliche | media L3 − B | sd |
|---|---|---|---|
| 0 | 14 | −0,06250 | 0,13824 |
| 1 | 14 | −0,01250 | 0,17146 |
| 2 | 14 | −0,01786 | 0,16567 |
| 3 | 14 | −0,00714 | 0,10982 |
| 4 | 14 | −0,01786 | 0,18974 |
| 5 | 14 | −0,05179 | 0,18643 |
| 6 | 12 | −0,12292 | 0,21858 |
| 7 | 12 | +0,03958 | 0,14595 |
| 8 | 12 | −0,00625 | 0,10667 |
| 9 | 12 | +0,03750 | 0,11407 |

Da leggere come descrizione, non come effetto: con 12-14 repliche per seggio e
`sd` fra 0,11 e 0,22, la semiampiezza per singolo seggio vale 0,06-0,12, cioè
più grande di quasi tutte le differenze in tabella. Sette seggi su dieci hanno
segno negativo; nessuna cella ha un intervallo che escluda lo zero, e nessuna
soglia per-seggio era stata scritta prima. **Non promuovo nessun seggio a
spiegazione.**

---

## 9. Il Copilota

**Nessun tetto e nessuna politica L3 entra nel Copilota.**

Il file dei tetti `data/l3/asta/tetti_2026-27.json` è ancora quello del 7/9
21:52 (24.441 byte) e non è stato usato: entrambi i blocchi sono stati giocati
senza `--tetti`, e i due JSON prodotti oggi portano
`"tetti": {"file": null, "caricato": false}`. Il braccio `L3+I` non è stato
giocato — con `usabili 0` misurerebbe zero per costruzione
(`reports/livelli_20260910/L3.md` §2.3).

L'asta di stasera gira sul Copilota con `BBot` e
`data/packs/pack_2026-27.pkl`; cubo, piano e tetti restano fuori. Il banco
misurato qui è solo un banco di misura.

---

## 10. Che cosa ho eseguito, con esito

| comando | esito |
|---|---|
| copia delle uscite 12:00 in `data/_backup_fable_20260910/l3/run_1200/` | fatta prima di ogni lancio, md5 verificati |
| `python -u scripts/l3_confronto_asta.py --stagione 2026-27 --repliche 117 --scenari 40 --seme 20260907 --trattamenti B L3 --piano data/l3/pilota/rosa_migliore.json` | **fermato alle 13:08 dopo 12 aste** (16,17 s/asta → 63 min stimati, oltre il tetto di 45 min). Log `log_banco_117_fermato.txt` |
| lo stesso comando con `--repliche 66` (blocco A) | uscita 0, **2143 s** (35 min 43 s), **132/132 aste riuscite**. Log `log_banco_117.txt` |
| lo stesso comando con `--repliche 66 --seme 20260973` (blocco B) | uscita 0, **1942 s** (32 min 22 s), **132/132 aste riuscite**. Log `log_banco_B_seme20260973.txt` |
| `…/scratchpad/w4/analisi_banco.py` sui due CSV (sola lettura) | validità e diagnostica di §3-§4 |
| `…/scratchpad/w5/analisi_pool.py` sui due CSV (sola lettura) | differenze appaiate e IC95 di §5, `pool_differenze.csv` |
| `…/scratchpad/w5/analisi_seggi.py` (sola lettura) | scomposizione per seggio di §8 |
| verifica di riproducibilità 12:00 ⊂ blocco A | 44 righe comuni, scarto massimo su `p1` **0,0**, su `speso` **0** |

Tutti con `PYTHONIOENCODING=utf-8`, `PYTHONPATH=src`, `OMP_NUM_THREADS=3`.
Nessun comando ha superato i 45 minuti; il più lungo è il blocco A, 35 min 43 s.

Uscite su disco a fine lavoro:

- `data/l3/asta/confronto_asta_2026-27.{csv,json}` = **blocco A** (banco
  dichiarato, seme 20260907), rimesso lì come uscita corrente come previsto dai
  criteri §5-bis; md5 del CSV `281886191746aef55fda7abb86d46b99`;
- `data/_backup_fable_20260910/l3/run_A_seme20260907/` = blocco A;
- `data/_backup_fable_20260910/l3/run_B_seme20260973/` = blocco B (83.508 byte);
- `data/_backup_fable_20260910/l3/run_1200/` = run delle 12:00;
- `data/_backup_fable_20260910/l3/` = run del 7/9 22:13 e tetti del 7/9 21:52,
  intatti.

---

## 11. Che cosa NON ho fatto

- Nessun file sotto `scripts/`, `src/`, `tests/` creato o modificato.
  RIPRODOTTO: `find scripts src tests -newermt "2026-09-10 13:00" -type f` elenca
  `scripts/f0b_build_outputs.py` (13:20:07), `scripts/l2_pilota_c2.py`
  (13:06:42), `scripts/l4_calibrazione_prezzo.py`,
  `src/fantabot/contratto_players.py`,
  `src/fantabot/tabellino/bersaglio_origine.py`,
  `tests/test_l1_contratto_players.py`, `tests/test_l2_bersaglio_origine.py`,
  `tests/test_l2_ingressi_c2.py`, `tests/test_l4_calibrazione_prezzo.py` più i
  `__pycache__`: **appartengono agli altri agenti in corso (L1, L2, L4), non a
  questo compito**. Il controllo delle 33 impronte di
  `…/scratchpad/w5/impronte_w5.json` segnala infatti **due** divergenze, e sono
  quelle due: `scripts/f0b_build_outputs.py` e `scripts/l2_pilota_c2.py`. Gli
  altri 31 file, compresi tutti quelli del percorso d'asta congelato
  (`f10_copilot.py`, `fantaoracle_app.py`, `bot_b.py`, `optimizer.py`,
  `piani.py`, `models.py`, `rules.py`, `viz/*`, `FantaOracle.bat`,
  `data/packs/*`, `data/copilot/*`, `data/processed/*`,
  `tests/test_copilot_asta.py`, `tests/test_rettifica_indisponibili.py`),
  **coincidono**.
- Nessuna attivazione nel Copilota, nessun tetto rigenerato, nessun braccio
  `L3+I` giocato.
- Nessuna asserzione indebolita, nessun `xfail`, nessuna replica scartata,
  nessuna soglia spostata dopo aver visto i numeri; l'emendamento al disegno è
  datato 13:10 e riguarda **come raccogliere le repliche**, non quale soglia
  applicare.
- Nessun training, nessun server (porte 8770 e 8899 mai usate), nessun push.
- Non ho aggiunto un terzo blocco: la soglia di precisione era già soddisfatta e
  il tempo restante serviva al rapporto.

---

**Nessun tetto e nessuna politica L3 entra nel Copilota.**
