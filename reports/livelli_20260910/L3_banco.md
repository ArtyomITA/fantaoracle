# L3 — cubo riallineato e banco appaiato rigiocato (10 settembre 2026)

Compito C (L2/L3). Sola misura: **nessuna attivazione nel Copilota**, nessun
file del percorso d'asta congelato toccato.

Marche: **RIPRODOTTO** (comando eseguito oggi, esito riportato), **OSSERVATO NEL
CODICE** (letto in un file, con riga), **IPOTESI** (dedotto, non provato).

---

## 0. Criteri di accettazione, scritti prima dei numeri

Congelati in `reports/CRITERI_L2_L3.md` §3.6 (righe 182-190) e ripresi da
`reports/livelli_20260910/L3.md` §6. Nessuno è stato inventato qui.

**Cubo (passo 2).**
- C1: il cubo nuovo contiene **tutti i 594** identificativi del pack corrente
  (`data/packs/pack_2026-27.pkl`, sha256 `71ec262b4bdf…`), zero mancanti.
- C2: mondo simulato invariato rispetto all'8/9 per struttura: 35 giornate
  future (4…38), 40 scenari.
- C3: durata sotto i 30 minuti.

**Guardia del mondo (passo 3).**
- C4: `tests/test_bot_l3_parita.py::test_il_mondo_di_prova_e_quello_dell_esperimento`
  verde sul mondo nuovo, con il cambio spiegato nel docstring e il numero
  vecchio (587) conservato con la sua data.
- C5: l'asserzione d'esito (crediti sul piano, L3 contro B+) **non** si tocca:
  o passa, o resta rossa e la si spiega con i numeri.

**Banco appaiato (passo 4).**
- C6 — validità della corsa, da controllare **per prima**: tutte le aste
  concluse (zero righe con `errore`), **zero** repliche scartate per «giocatori
  fuori dal cubo», zero per «rose illegali», `piano_non_classificati` = 0 e
  `pavimento_violato` = 0. Se una cade, la corsa non produce verdetto.
- C7 — promozione di L3: differenza appaiata di P(1°) (L3 − B) **positiva** con
  IC95 che **esclude lo zero**.
- C8 — bocciatura: IC95 interamente **negativo**.
- C9 — inconcludente: IC95 che contiene lo zero. Si scrive «inconcludente» e si
  riporta la semiampiezza; non si scrive «equivalenti» e non si sposta la
  soglia.
- C10 — precisione: se la semiampiezza supera **0,030** il disegno è dichiarato
  insufficiente per l'effetto cercato, qualunque sia il segno.

---

## 1. Backup (passo 1)

RIPRODOTTO. Cartella nuova `data/_backup_fable_20260910/`:

| copia | origine | data dell'originale |
|---|---|---|
| `l2/cubo_2026-27.pkl` | `data/l2/cubo_2026-27.pkl` | 8/9 23:15, 12.547.108 byte |
| `l2/cubo_rapporto_2026-27.json` | `data/l2/cubo_rapporto_2026-27.json` | 8/9 23:38, 22.561 byte |
| `l3/confronto_asta_2026-27.csv` | `data/l3/asta/…` | 7/9 22:13, 13.247 byte |
| `l3/confronto_asta_2026-27.json` | `data/l3/asta/…` | 7/9 22:13, 952 byte |
| `l3/tetti_2026-27.json` | `data/l3/asta/…` | 7/9 21:52, 24.441 byte |

Copia fatta **prima** di ogni scrittura: `scripts/l2_genera_cubo.py` sovrascrive
cubo e rapporto, `scripts/l3_confronto_asta.py:407,439` sovrascrive i due file
del 7/9.

---

## 2. Cubo rigenerato (passo 2)

### 2.1 Parametri: da dove vengono, e una discrepanza trovata sul disco

Il compito chiede di ricavare i valori del run dell'8/9 da
`data/l2/cubo_rapporto_*.json`. RIPRODOTTO, e va detto subito che **il rapporto
sul disco non descriveva il cubo sul disco**:

- `data/l2/cubo_2026-27.pkl` (8/9 23:15) porta `fantavoto` di forma
  **(40, 35, 587)**, `as_of 2026-09-11`, `seme 20260907`;
- `data/l2/cubo_rapporto_2026-27.json` (8/9 23:38) dichiara **`sims = 4`**.

OSSERVATO NEL CODICE (`scripts/l2_genera_cubo.py:465-472`): il rapporto si
scrive **sempre**, il `.pkl` solo con `--salva`. Una corsa successiva a 4
scenari, lanciata senza `--salva`, ha quindi riscritto il rapporto lasciando in
piedi il cubo a 40 scenari. Nessun log sul disco corrisponde al cubo delle
23:15 (i log `log_cubo_f1.txt` 21:45 e `log_cubo_f4.txt` 22:19 sono corse
diverse, 40 scenari e altre impronte di configurazione).

Parametri usati oggi, e la loro fonte:

| opzione | valore | fonte |
|---|---|---|
| `--as-of` | `2026-09-10` | imposto dal compito (il vecchio era `2026-09-11`; vedi §2.2: stesso mondo) |
| `--sims` | `40` | dalla **forma del pkl** dell'8/9, non dal rapporto (che dice 4 e appartiene a un'altra corsa) |
| `--seme` | `20260907` | `pkl["seme"]` e `rapporto["seme"]` |
| `--solo-future` | sì | `rapporto["solo_future"] = true` |
| `--rose-da` | `listone` | `rapporto["universo"]["rose_da"]` |
| `--data-fit` | `2026-09-08` | `rapporto["data_fit"]` |
| `--bersaglio-presenze` | sì | `rapporto["bersaglio_presenze"] = true` |
| `--salva` | sì | serve il `.pkl` per il banco |

IPOTESI dichiarata: che il cubo delle 23:15 avesse `--data-fit` e
`--bersaglio-presenze` non è provabile (il pkl non li registra); sono i valori
dell'unico registro parametrico esistente, il rapporto.

Comando eseguito:

```
PYTHONIOENCODING=utf-8 PYTHONPATH=src OMP_NUM_THREADS=4 \
python scripts/l2_genera_cubo.py 2026-27 --as-of 2026-09-10 --sims 40 \
  --seme 20260907 --solo-future --rose-da listone --data-fit 2026-09-08 \
  --bersaglio-presenze --salva
```

### 2.2 Esito

RIPRODOTTO, log in `…/scratchpad/w4/log_cubo_20260910.txt`, uscita 0.

- **Durata: 7 min 0 s** (11:41:58 → 11:48:58), di cui `stima completata in
  105,3 s` e `cubo generato in 37,6 s`. **C3 soddisfatto** (limite 30 min).
- `universo da 'squadra_listone': 594 giocatori, 20 squadre`; `rose: 20
  squadre, 594 giocatori`.
- `bersaglio presenze: 594/594 (594 da previsione, 0 da prior di ruolo, 0
  senza), 11 previsioni zero tenute`; `presenze applicate: 594, di cui 140
  iniziati senza storia`.
- Cubo nuovo: `fantavoto` **(40, 35, 594)**, `as_of 2026-09-10`, `seme
  20260907`, 16.040.125 byte, sha256 `ea7d3a53ad9124be…`, scritto 10/9 11:48.
- **C1 soddisfatto**: `pack − cubo = 0`, `cubo − pack = 0`. I sette
  identificativi che mancavano (795, 2169, 6047, 6319, 7626, 7627, 7628) ci
  sono tutti. RIPRODOTTO confrontando gli insiemi in memoria.
- **C2 soddisfatto**: `calendario: 380 partite totali, 30 gia' giocate alla
  data limite, 350 da generare`, 35 giornate (4…38), 40 scenari — identico
  all'8/9.
- `coerenza dei tabellini (prime 20 partite del primo scenario): 0 problemi`.

Perché `--as-of 2026-09-10` non cambia il mondo rispetto a `2026-09-11`:
RIPRODOTTO sul calendario — la giornata 3 si chiude il 7/9 e la 4 apre l'11/9,
quindi fra il 10 e l'11 settembre non cade nessuna partita: 30 giocate e 350 da
generare in entrambi i casi, e `Ppre` (dati con `data < as_of`) è lo stesso
insieme.

### 2.3 Un limite del cubo nuovo, dichiarato

Il cubo è riallineato **sull'universo**, non sugli ingressi di stima. Con
`--data-fit 2026-09-08` il panel caricato è la vista al fit dell'8/9, e il
rapporto nuovo continua a registrare per il 2026-27 le fonti
`voti cafd8667fce11d00` e `listone bfdab5a98fc0fe44`, mentre i file su disco
oggi valgono `c0ccb3bf1a882976` (voti, 10/9 06:03) e `2d53a2e5ed0a10fa`
(listone, 10/9 06:04). L'universo, invece, viene da
`contratto.costruisci_universo` che legge il listone corrente: da lì i 594.

Conseguenza da non nascondere: **stima sui dati dell'8/9, universo del 10/9**.
Per allineare anche la stima servirebbe ricostruire i panel
`l2_panel_*__fit20260908` sulle fonti di stanotte, che è un altro passo, non
richiesto qui e non eseguito. Il bersaglio `b_predictions_2026-27.json`
(`574ef31a58e195bc`, 10/9 06:20) è invece quello nuovo, ed è letto direttamente
da `scripts/l2_genera_cubo.py:91`: quindi il cubo mescola un bersaglio del 10/9
con un panel dell'8/9. Resta vero il difetto già registrato in
`reports/livelli_20260910/L2.md` §2.3: il rapporto del cubo **non** registra
l'impronta del proprio bersaglio, quindi nessun controllo automatico se ne
accorge.

---

## 3. Guardia del mondo e asserzione d'esito (passo 3)

### 3.1 Che cosa ho cambiato, e che cosa no

Unico file del progetto modificato: **`tests/test_bot_l3_parita.py`**. Due
punti, nessun altro.

1. Riga 356 (ora 375): `assert len(b["pack"].players) == 587` →
   `assert len(b["pack"].players) == 594`, con un commento in linea che porta
   le due date (`594 dal 10/9/2026 (pack 71ec262b4bdf…); era 587 dal 7/9
   all'8/9/2026`) e un docstring nuovo che spiega il cambio di mondo: pack
   rigenerato dalla catena `f11_refresh_all` il 10/9 alle 06:25, 587 in comune
   più i sette nuovi, cubo rigenerato lo stesso giorno sugli stessi 594. Il
   docstring dichiara anche che **non è un allentamento**: la guardia resta
   un'uguaglianza esatta e tornerà rossa al prossimo cambio di pack.
2. Docstring del modulo, riga 11: «pack 2026-27 (587 giocatori…)» → «594
   giocatori dal 10 settembre 2026, erano 587 il 7-8 settembre 2026», con il
   rimando alla guardia.

**Non toccata** l'asserzione d'esito di `test_il_piano_cambia_davvero_l_asta`
(riga 424 dell'originale): `assert crediti_d > crediti_a`. Nessuna asserzione
indebolita, nessun `xfail` aggiunto.

### 3.2 Esito della riesecuzione

RIPRODOTTO, `…/scratchpad/w4/log_pytest_parita.txt`:

```
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTHONIOENCODING=utf-8 PYTHONPATH=src \
  OMP_NUM_THREADS=4 python -m pytest tests/test_bot_l3_parita.py -q
1 failed, 9 passed, 549796 warnings in 86.55s (0:01:26)
```

- **C4 soddisfatto**: `test_il_mondo_di_prova_e_quello_dell_esperimento` è
  **verde**. Le altre otto prove del file restano verdi: parità martelletto per
  martelletto, tetti congelati, identità scambiata, contatori riconciliati.
- **C5**: `test_il_piano_cambia_davvero_l_asta` resta **rossa**, alla riga 448
  (era 424 prima delle mie righe di docstring):

```
AssertionError: L3 impegna sul piano 121 crediti, B+ ne impegna 146:
inseguire il piano non sta cambiando dove finiscono i soldi
assert 121 > 146
```

Le prime tre asserzioni della stessa prova (ricalcoli con piano > 0, impronta
diversa da B+, forzati ⊆ target) passano: **il meccanismo regge**, cade solo
l'esito.

### 3.3 Perché resta rossa: i numeri

RIPRODOTTO con `…/scratchpad/w4/diag_crediti_piano.py`, che rigioca le stesse
due aste della prova (seme 20260907, seggio 0, piano di 25 giocatori) e
scompone la spesa:

| | B+ | L3 |
|---|---|---|
| rosa | 25 giocatori, 457 crediti, residuo 43 | 25 giocatori, 455 crediti, residuo 45 |
| **del piano comprati da noi** | **6** | **9** |
| **crediti spesi su di loro** | **146** | **121** |
| crediti per giocatore del piano | 24,3 | 13,4 |
| del piano finiti ai rivali | 13 (479 crediti spesi dai rivali) | 13 (483) |

Dettaglio dei prezzi (pid: prezzo, chi lo prende):

- B+ compra `5995` a 49, `2848` a 35, `6956` a 22, `4976` a 22, `5862` a 10,
  `6482` a 8 → 146.
- L3 compra `5995` a 47, `4976` a 21, `6956` a **15**, `5620` a 10, `5862` a
  10, `6684` a 9, `6482` a 7, `6415` a **1**, `7274` a **1** → 121.

La lettura: nel mondo nuovo **L3 prende più giocatori del piano (9 contro 6) e
li paga meno**. Due movimenti opposti si sommano:

1. L3 perde l'unico pezzo caro che B+ per caso si aggiudica (`2848`: B+ lo
   prende a 35, nell'asta di L3 va a un rivale a 38) e paga meno `6956`
   (15 contro 22);
2. L3 aggiunge quattro acquisti a prezzo basso che B+ non fa affatto (`5620`
   10, `6684` 9, `6415` 1, `7274` 1).

L'asserzione misura **crediti**, non **giocatori**: nel mondo dell'8/9 le due
grandezze si muovevano insieme, nel pack del 10/9 no. Il piano
`data/l3/pilota/rosa_migliore.json` è del 7/9 e i prezzi del pack sono quelli
del mercato live del 10/9 (`f9_apply_market`): gli stessi 25 nomi oggi si
comprano con meno crediti, e la parte del piano che costava molto se la portano
i rivali.

**Nessuna modifica all'asserzione.** Non è stata tolta né indebolita né marcata
`xfail`: resta rossa e questa è la sua spiegazione, come il docstring stesso
prescriveva («se cambia va spiegata, non tolta»). Chi vorrà renderla di nuovo
utile dovrà decidere prima che cosa deve misurare — i crediti o il numero di
giocatori del piano — e scriverlo, non aggiustare il numero dopo.

---

## 4. Banco appaiato (passo 4)

### 4.1 Comando e scelta del disegno

```
PYTHONIOENCODING=utf-8 PYTHONPATH=src OMP_NUM_THREADS=4 python -u \
scripts/l3_confronto_asta.py --stagione 2026-27 --repliche 22 --scenari 40 \
  --seme 20260907 --trattamenti B L3 --piano data/l3/pilota/rosa_migliore.json
```

Repliche (22), scenari (40), seme (20260907) e i nove avversari sono quelli del
run del 7/9 — RIPRODOTTO da `data/_backup_fable_20260910/l3/confronto_asta_2026-27.json`
(`repliche 22, scenari 40, seme 20260907`).

**Dimezzamento dichiarato.** Il 7/9 i trattamenti erano quattro
(`B`, `B+`, `L3`, `L3+I`), cioè **88 aste**; qui ne ho giocate **44**, i due
del confronto che il criterio riguarda. Motivo: il tetto dei 30 minuti per
comando con CPU condivisa fra tre agenti. La stima del 7/9 (14,1 s per asta)
avrebbe dato 21 minuti sulle 88, ma un solo sforamento avrebbe fatto perdere
tutta la corsa, perché lo script scrive CSV e JSON **solo alla fine**
(`scripts/l3_confronto_asta.py:407,439`). Misura effettiva di oggi: **13,3 s
per asta**, cioè 88 aste sarebbero costate ~19,5 minuti. Il braccio `L3+I` non
era comunque giocabile in modo informativo: il file dei tetti è del 7/9 e
`carica_tetti` ne dichiara `usabili 0` (`reports/livelli_20260910/L3.md` §2.3);
il JSON di oggi lo conferma con `"tetti": {"file": null, "caricato": false}`.

### 4.2 Validità della corsa (criterio C6, controllato per primo)

RIPRODOTTO dal log e dal CSV:

```
tempo totale 587 s, 44/44 aste riuscite
```

| controllo | esito |
|---|---|
| aste concluse | **44 su 44**, zero righe con `errore` nel CSV |
| repliche scartate per «giocatori fuori dal cubo» | **0** (col cubo dell'8/9 sarebbero state tutte: L3.md §3.2) |
| repliche scartate per «rose illegali» | **0** (`V.verifica_rose` gira su entrambi i bracci) |
| `piano_non_classificati` | **0** su tutte le 22 aste L3 |
| `pavimento_violato` | **0** su tutte le 22 aste L3 (`milp.pavimento_violato`) |
| `parita_al_primo` | 0 in entrambi i bracci |

Un limite da dichiarare, non uno zero misurato: per il braccio **B** il CSV
porta `rapporto_bot = {}`. OSSERVATO NEL CODICE
(`scripts/l3_confronto_asta.py:258`): il rapporto si chiede con
`nostro.rapporto() if hasattr(nostro, "rapporto") else {}`, e `BBot` congelato
non espone `rapporto()`. Quindi `piano_non_classificati` e `pavimento_violato`
per B sono **non misurati**, non zero. Per B valgono i due controlli esterni:
asta conclusa e rose legali.

**C6 soddisfatto** per quanto è misurabile; la lacuna su B è dichiarata qui e
non trasformata in un successo.

### 4.3 Tabella dei trattamenti (44 aste, 22 repliche appaiate)

| grandezza | B | L3 |
|---|---|---|
| P(1°) medio | **0,1898** | **0,1602** |
| errore standard medio di P(1°) per asta | 0,0567 | 0,0529 |
| punti di stagione medi | 2497,1 | 2495,8 |
| punti a giornata | 71,345 | 71,310 |
| gol a giornata | 1,4570 | 1,4563 |
| speso medio | 372,9 | 422,3 |
| residuo medio | 127,1 | 77,7 |
| secondi per asta | 11,45 | 15,26 |

Diagnostica del piano, braccio L3 (somma su 22 aste → media per asta):

| contatore | somma | per asta |
|---|---|---|
| `crediti_sul_piano` | 2718 | 123,55 |
| `piano_miei_dopo` | 166 | 7,55 |
| `piano_ai_rivali` | 319 | 14,50 |
| `piano_disponibili` | 65 | 2,95 |
| `piano_scartati_dal_ricalcolo` | 65 | 2,95 |
| `piano_troncati_dal_vincolo` | 72 | 3,27 |
| `piano_scartato_per_infattibilita` | 141 | 6,41 |
| `ricalcoli_con_piano` | 1147 | 52,14 |
| `piano_non_classificati` | 0 | 0 |

Il trattamento è davvero applicato (52 ricalcoli con piano per asta, 7,55
giocatori del piano in rosa) e non fa sparire la contabilità
(`piano_non_classificati` 0, `pavimento_violato` 0).

### 4.4 Differenza appaiata e verdetto

RIPRODOTTO (bootstrap 4000 sulla media delle differenze per replica, come fa
lo script alle righe 421-433):

| confronto | differenza | IC95 | semiampiezza | esclude lo zero |
|---|---|---|---|---|
| **L3 − B** | **−0,02955** | **[−0,10000, +0,03185]** | **0,06592** | **no** |

Scarto delle differenze appaiate: `sd = 0,16487` su 22 repliche. Repliche
vinte da L3: **9**; pari: **3**; peggio: **10**.

**VERDETTO — INCONCLUDENTE (criterio C9).** L'intervallo al 95 % contiene lo
zero: L3 **non è promosso** (C7 non soddisfatto: la differenza non è positiva
con IC che esclude lo zero) e **non è bocciato** (C8 non soddisfatto: l'IC non
è interamente negativo). Non scrivo «equivalenti»: scrivo inconcludente, e
riporto la semiampiezza ottenuta, **0,06592**.

**VERDETTO SULLA PRECISIONE — DISEGNO INSUFFICIENTE (criterio C10).** La
semiampiezza 0,06592 supera la soglia 0,030 fissata prima. Con lo scarto
misurato oggi (0,16487) servirebbero **117 repliche** per una semiampiezza di
0,030, contro le 22 giocate: 234 aste, circa 52 minuti a 13,3 s per asta, cioè
due comandi. Questo vale qualunque sia il segno, e va detto prima di qualsiasi
lettura del segno.

### 4.5 Confronto col run del 7 settembre, senza forzature

| | 7/9 (bot difettoso, cubo 587, pack vecchio) | 10/9 (bot corretto 8/9, cubo 594, pack 71ec262b4bdf) |
|---|---|---|
| L3 − B | −0,0625 | −0,02955 |
| IC95 | [−0,11480, −0,01929] | [−0,10000, +0,03185] |
| esito secondo il criterio | bocciatura | **inconcludente** |
| P(1°) B | 0,0943 | 0,1898 |
| P(1°) L3 | 0,0318 | 0,1602 |
| speso B / L3 | 429,6 / 370,7 | 372,9 / 422,3 |
| sd della differenza appaiata | 0,11896 | 0,16487 |

Che cosa si può dire: **la bocciatura del 7/9 non si riproduce** nel mondo
nuovo. Che cosa **non** si può dire: che L3 e B siano equivalenti, o che L3 sia
migliorato. Fra i due run cambiano insieme tre cose — le correzioni del bot
dell'8/9, il pack del 10/9, il cubo rigenerato oggi — quindi la differenza fra
−0,0625 e −0,0296 non è attribuibile a nessuna di esse in particolare. E il
disegno di oggi non ha la precisione per un verdetto: due punti che rendono
questo confronto una descrizione, non una spiegazione.

Va anche notato che il livello assoluto di P(1°) è quasi raddoppiato per
entrambi i bracci (0,0943 → 0,1898 per B): il banco non è lo stesso banco, ed è
un'altra ragione per non leggere le due differenze come misure della stessa
quantità.

### 4.6 Dove sono le uscite

- Nuove: `data/l3/asta/confronto_asta_2026-27.csv` (44 righe) e
  `…/confronto_asta_2026-27.json`, scritti dallo script il 10/9 alle 11:59.
- Quelle del 7/9 22:13 **non** sono state perse: copiate prima in
  `data/_backup_fable_20260910/l3/`.
- Log completo della corsa: `…/scratchpad/w4/log_banco_20260910.txt`.

---

## 5. Il Copilota

**Nessun tetto e nessuna politica L3 entra nel Copilota.**

RIPRODOTTO oggi:
`grep -rn "livello3|bot_l3|BotL3|BBotCoerente|tetti" --include=*.py
scripts/f10_copilot.py scripts/fantaoracle_app.py src/fantabot/bots/bot_b.py
src/fantabot/optimizer.py src/fantabot/piani.py` restituisce **una sola riga**,
`src/fantabot/piani.py:140`, che è prosa in un commento («alzano i tetti per
farle entrare») e non un uso: nessun `import`, nessuna lettura di
`data/l3/asta/tetti_2026-27.json`, nessun riferimento a `BotL3`.
`grep -rn "cubo|tabellino" --include=*.py scripts/f10_copilot.py
scripts/fantaoracle_app.py`: **zero righe**.

L'asta di stasera gira su `data/packs/pack_2026-27.pkl` con `BBot`; il cubo e i
tetti restano fuori. Il cubo rigenerato oggi serve solo al banco di misura.

---

## 6. Che cosa NON ho fatto

- Nessuna attivazione nel Copilota, nessun file dell'elenco congelato toccato.
  RIPRODOTTO: `find scripts src tests viz data/packs data/copilot -newermt
  "2026-09-10 11:35"` elenca `tests/test_bot_l3_parita.py` (mio) più
  `scripts/f17_formazione.py`, `tests/test_f17_formazione.py`,
  `tests/test_l4_*.py`, `data/copilot/formazione_2026-27_G4.md`, che
  appartengono agli altri due agenti in corso, non a questo compito.
- Nessun file sotto `scripts/` o `src/` modificato.
- Nessuna asserzione indebolita, nessun `xfail` aggiunto, nessun seme scartato,
  nessuna soglia spostata dopo aver visto i numeri.
- Nessun training, nessun server, nessun push. `OMP_NUM_THREADS=4` su ogni
  comando; `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1` sul pytest.
- RIPRODOTTO a fine lavoro: le **26** impronte di
  `…/scratchpad/w4/impronte_asta.json` sono ricalcolate e **coincidono tutte**
  con i file su disco. `data/l3/asta/tetti_2026-27.json` è ancora quello del
  7/9 21:52 (24.441 byte), non rigenerato.
- Non ho rigenerato i tetti (`scripts/l3_tetti.py`, 319,1 s): il braccio L3+I
  non è stato giocato, quindi non servivano.
- Non ho ricostruito i panel `l2_panel_*__fit20260908` sulle fonti di stanotte
  (§2.3): il cubo resta stimato sui dati dell'8/9.

---

## 7. Comandi eseguiti, con esito

| comando | esito |
|---|---|
| `python scripts/l2_genera_cubo.py 2026-27 --as-of 2026-09-10 --sims 40 --seme 20260907 --solo-future --rose-da listone --data-fit 2026-09-08 --bersaglio-presenze --salva` | uscita 0, **420 s** (11:41:58→11:48:58); cubo (40, 35, **594**), 0 problemi di coerenza |
| `python -m pytest tests/test_bot_l3_parita.py -q` (con `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1`) | **1 failed, 9 passed** in 86,55 s |
| `python -u scripts/l3_confronto_asta.py --stagione 2026-27 --repliche 22 --scenari 40 --seme 20260907 --trattamenti B L3 --piano data/l3/pilota/rosa_migliore.json` | uscita 0, **587 s**, **44/44 aste riuscite** |
| `…/scratchpad/w4/analisi_banco.py` (sola lettura del CSV/JSON) | validità e IC95 riportati in §4.2-4.4 |
| `…/scratchpad/w4/diag_crediti_piano.py` (rigioca le due aste del test) | scomposizione di §3.3 |

Tutti con `PYTHONIOENCODING=utf-8`, `PYTHONPATH=src`, `OMP_NUM_THREADS=4`.
Nessun comando ha superato i 30 minuti; il più lungo è il banco, 9 min 47 s.

---

## 8. Riepilogo dei verdetti

| criterio | esito |
|---|---|
| C1 — cubo copre i 594 del pack | **soddisfatto** (0 mancanti) |
| C2 — mondo invariato (35 giornate, 40 scenari) | **soddisfatto** |
| C3 — cubo sotto 30 minuti | **soddisfatto** (7 min 0 s) |
| C4 — guardia del mondo verde e spiegata | **soddisfatto** |
| C5 — asserzione d'esito non toccata | **rispettato**: resta **rossa**, spiegata in §3.3 (121 crediti su 9 giocatori contro 146 su 6) |
| C6 — validità della corsa | **soddisfatto** per quanto misurabile; `rapporto_bot` vuoto per B è una lacuna dichiarata |
| C7 — promozione di L3 | **non soddisfatto** |
| C8 — bocciatura di L3 | **non soddisfatto** |
| C9 — inconcludente | **è questo il verdetto**: L3 − B = −0,02955, IC95 [−0,10000, +0,03185], semiampiezza 0,06592 |
| C10 — precisione | **non soddisfatto**: 0,06592 > 0,030 → disegno insufficiente; servirebbero 117 repliche |

**Nessun tetto e nessuna politica L3 entra nel Copilota.**
