# L4 — trasferibilita' della calibrazione per segmento degli intervalli di prezzo

Esecuzione 10/9/2026, 13:03-13:20. Criterio scritto **prima** dei numeri in
`scratchpad/w5/criteri_prima_L4.md` (§7.3 di `reports/livelli_20260910/L4.md`,
ricopiato senza modifiche). Nessuna soglia mossa dopo.

Etichette: **RIPRODOTTO** = eseguito e visto qui; **OSSERVATO NEL CODICE** =
letto, non eseguito; **IPOTESI** = deduzione dichiarata.

Nessun file congelato toccato. Niente scritto in `data/processed`, `data/packs`,
`data/copilot`, `reports/`. `reports/f1_price_eval.json` resta al 6/8/2026
(`Aug 6 03:54`, verificato dopo il passo 1). File nuovi solo:
`scripts/l4_calibrazione_prezzo.py`, `tests/test_l4_calibrazione_prezzo.py`.

Due scritture collaterali da dichiarare:

1. `catboost_info/` nella radice del progetto (`catboost_training.json`,
   `learn_error.tsv`, `time_left.tsv`, `tmp/`) e' stata **riscritta alle 13:11**
   dal passo 1: e' il log che CatBoost scrive nella cartella di lavoro. La
   cartella esisteva gia' dal 1/9/2026 20:52 e non e' un artefatto d'asta ne'
   un file congelato; nessun dato del progetto e' stato alterato.
2. Verifica delle impronte di `impronte_w5.json` fatta alle 13:20: 33 file
   controllati, **2 differenti** — `scripts/f0b_build_outputs.py` e
   `scripts/l2_pilota_c2.py`. **Non sono di questo compito** (mai aperti in
   scrittura qui, non compaiono in nessun comando eseguito): risultano
   modificati intorno alle 13:0x, presumibilmente da un altro agente in
   parallelo. Segnalato perche' il revisore lo vedra'.

---

## 1. Che cosa e' stato fatto

Passo 2 (sonda) **e** passo 1 (riadattamento), entrambi eseguiti.

| passo | comando | durata |
|---|---|---|
| 1 | `python <w5>/f1_train_price_pergruppo.py` (copia di `scripts/f1_train_price.py`, uscita dirottata in `w5`) | **~3 min** (stimati 10-20 in L4.md) |
| 1b (controllo) | `python <w5>/f1_train_price_perriga.py` (stesso file, split conformal originale per riga) | ~3 min |
| 2 | `python scripts/l4_calibrazione_prezzo.py --out <w5> [--pred-dir …] [--tag …]` | 3 x < 5 s |
| test | `python -m pytest tests/test_l4_calibrazione_prezzo.py -q -p no:cacheprovider` | 2,0 s, **19 passati** |

### 1.1 Scostamento dichiarato dal disegno: «per asta» non e' realizzabile

Il disegno chiedeva la divisione fit/calibrazione **per asta**. OSSERVATO NEL
CODICE: il train di `f1_train_price.py` e' `players_{stagione}.parquet`, una
riga per giocatore-stagione, con bersaglio `target_mean_pct_all_estiva`, cioe'
**gia' mediato su piu' aste** (`f1_train_price.py:88-93`). L'asta non e'
un'unita' presente nel train: ricostruirla vuol dire cambiare il bersaglio
(una riga per asta-giocatore da `aste_reali_clean.csv`), cioe' un modello
diverso, non una divisione diversa.

Unita' piu' fine effettivamente disponibile: **il giocatore** (`master_id`), che
compare in piu' stagioni del train (R2 = 2021-22 + 2023-24). E' quella la
contaminazione reale che `with_conformal` produce oggi mescolando le righe con
`RandomState(13)`. Il passo 1 divide per `master_id`: nessun giocatore sta in
fit e in calibrazione insieme. Il resto del file e' identico all'originale.

---

## 2. Le tre configurazioni misurate (tutte RIPRODOTTO)

Delta stimati **solo su 2023-24**, applicati a **2024-25** (mai usato per
stimare). Test = 255 righe con bersaglio (`n_obs >= 2`).

| # | predizioni di partenza | cop. prima | cop. dopo | pinball prima → dopo | ampiezza mediana prima → dopo |
|---|---|---:|---:|---|---|
| **A** | `data/processed/pred_ens_tab_cat_*.csv` del 6/8 (**sonda**) | 0,7176 | **0,7922** | 0,005502 → 0,005417 (**−1,54 %**) | 10,92 → 13,10 cr (**+19,96 %**) |
| **B** | rigenerate col codice del 6/9, split conformal **per riga** (originale) | 0,6745 | **0,7725** | 0,005501 → 0,005414 (−1,58 %) | 10,70 → 13,48 cr (**+25,98 %**) |
| **C** | rigenerate col codice del 6/9, split **per giocatore** (disegno L4) | 0,7608 | **0,8863** | 0,005393 → 0,005468 (**+1,39 %**) | 11,94 → 16,44 cr (**+37,69 %**) |

La riga **C** e' la validazione richiesta (passo 1 + passo 2). A e B sono
contorno: A e' la sonda sulle predizioni vecchie, B isola l'effetto del solo
riadattamento a parita' di split.

Controllo di direzione inversa (criterio 5), stima su 2024-25 → prova su 2023-24:

| # | cop. prima | cop. dopo | pinball prima → dopo |
|---|---:|---:|---|
| A | 0,7530 | 0,7887 | 0,005736 → 0,005580 (−2,72 %) |
| B | 0,7530 | 0,7976 | 0,005736 → 0,005601 (−2,35 %) |
| C | 0,6756 | 0,7262 | 0,005934 → 0,005846 (**−1,48 %**) |

---

## 3. Verdetto secondo il criterio scritto prima

Applicato alla configurazione **C**.

| # | criterio | valore | esito |
|---|---|---|---|
| 1 | copertura globale 2024-25 in **[0,75; 0,85]** | **0,8863** | **FALLITO** (sovracopre) |
| 2 | nessuna cella con `n >= 30` sotto 0,60 | 2 celle con `n >= 30`: D·[3,8) `n=39` → 0,897; C·[3,8) `n=33` → 0,848 | passato |
| 3 | pinball non peggiore entro **1 %** relativo | +1,39 % | **FALLITO** |
| 4 | ampiezza mediana entro **+25 %** | +37,69 % | **FALLITO** |
| 5 | segno coerente sulle due stagioni | pinball −1,48 % sull'altra direzione | passato |

**VERDETTO: la calibrazione per segmento NON si adotta.** Tre criteri su cinque
falliti. Non «quasi»: non adottata. L'intervallo di prezzo resta com'e' e va
etichettato **non calibrato** nell'interfaccia, come previsto da L4.md §7.3.

### 3.1 Conclusione ritrattata, lasciata leggibile

La **sola sonda** (configurazione A, predizioni del 6/8) passava **tutti e
cinque** i criteri: 0,7922 in banda, pinball −1,54 %, ampiezza +19,96 %, nessuna
cella `n >= 30` sotto 0,60 (min 0,721), direzione inversa coerente. Se il passo 1
non fosse stato eseguito, il rapporto avrebbe detto «adottabile». **Ritrattato
dal passo 1**: con le predizioni prodotte dal codice attuale e la divisione per
giocatore, la stessa correzione sovracopre e allarga troppo. Chi ritratta: la
configurazione C di §2, misurata dallo stesso script, stesso criterio, stesse
soglie.

Anche la configurazione B (solo riadattamento, split invariato) fallisce, per un
soffio, il criterio 4: +25,98 % contro il limite +25 %.

---

## 4. Perche' fallisce: la base di partenza non e' stabile

RIPRODOTTO. La copertura di `ens_tab_cat` sul 2024-25 **prima** di qualunque
calibrazione vale 0,6745 / 0,7176 / 0,7608 nelle tre configurazioni, cioe' una
escursione di **0,086** dovuta a sole differenze di implementazione (data della
rigenerazione, split del conformal), non a scelte di modello. Sull'altra
stagione l'ordine si inverte (2023-24: 0,7530 / 0,7530 / 0,6756).

Scarto fra le predizioni del 6/8 e quelle rigenerate a parita' di split (B):
mediana +0,002 cr su `q10`, ma **massimo 16,2 cr**; `q90` mediana −0,179 cr,
massimo 4,9 cr. Le predizioni salvate **non** sono riproducibili esattamente
(CatBoost/TabPFN + numero di thread), quindi ogni numero di copertura porta un
rumore di rigenerazione oltre a quello campionario.

Rumore campionario, per confronto: con `n = 255` e copertura vera 0,80, la
deviazione standard binomiale e' **0,025**; la banda di accettazione
[0,75; 0,85] e' larga ±2 deviazioni standard. Il delta globale stimato vale
1,42 cr (A) e 2,31 cr (C): la correzione da stimare e' dello stesso ordine
della differenza fra due riesecuzioni. **IPOTESI** (dichiarata tale): con questo
campione nessuna calibrazione degli intervalli e' distinguibile dal rumore di
rigenerazione; per stabilirlo servirebbe rendere deterministica la catena e
ripetere, cosa non fatta qui.

---

## 5. Tabella per cella — configurazione C (2023-24 → 2024-25)

Copertura prima e dopo, ampiezza mediana in crediti. 22 celle non vuote su 24.

| ruolo | fascia | n | cop. prima | cop. dopo | amp. prima | amp. dopo |
|---|---|---:|---:|---:|---:|---:|
| P | [0,3) | 9 | 0,889 | 0,889 | 3,6 | 5,0 |
| P | [3,8) | 6 | 0,667 | 0,833 | 9,6 | 13,1 |
| P | [8,15) | 3 | 1,000 | 1,000 | 13,6 | 17,6 |
| P | [15,30) | 5 | 0,600 | 0,800 | 20,5 | 25,6 |
| P | [30,60) | 6 | 1,000 | 1,000 | 21,0 | 26,9 |
| D | [0,3) | 3 | 1,000 | 1,000 | 4,9 | 5,8 |
| D | [3,8) | **39** | 0,744 | 0,897 | 8,5 | 10,4 |
| D | [8,15) | 26 | 0,731 | 0,923 | 12,8 | 18,0 |
| D | [15,30) | 8 | 1,000 | 1,000 | 16,5 | 20,7 |
| D | [30,60) | 7 | 0,714 | 0,714 | 19,0 | 24,1 |
| C | [0,3) | 17 | 0,882 | 0,941 | 4,7 | 6,4 |
| C | [3,8) | **33** | 0,697 | 0,848 | 8,3 | 11,0 |
| C | [8,15) | 10 | 0,700 | 0,900 | 13,7 | 20,2 |
| C | [15,30) | 10 | 1,000 | 1,000 | 20,0 | 28,4 |
| C | [30,60) | 10 | 0,800 | 0,800 | 21,2 | 29,7 |
| C | [60+] | 3 | 0,333 | 0,667 | 52,0 | 56,6 |
| A | [0,3) | 3 | 1,000 | 1,000 | 3,9 | 5,6 |
| A | [3,8) | 13 | 0,769 | 0,846 | 11,1 | 13,6 |
| A | [8,15) | 13 | 0,462 | 0,846 | 12,7 | 17,5 |
| A | [15,30) | 9 | 0,778 | 0,889 | 24,6 | 31,9 |
| A | [30,60) | 6 | 0,500 | 0,667 | 29,7 | 38,0 |
| A | [60+] | 16 | 0,812 | 0,938 | 92,3 | 109,0 |

Aggregato per fascia (C): [0,3) 32 righe 0,906→0,938 · [3,8) 91 0,725→0,868 ·
[8,15) 52 0,673→0,904 · [15,30) 32 0,875→0,938 · [30,60) 29 0,759→0,793 ·
[60+] 19 0,737→0,895.

Solo **2 celle su 24** hanno `n >= 30` nella stagione di prova, e nella stagione
di **stima** (2023-24) solo 2 celle superano 30 osservazioni (D·[0,3) `n=49`,
D·[3,8) `n=41`): lo shrink con `n0 = 30` riporta quasi tutte le celle verso il
delta globale (2,308 cr), quindi la calibrazione «per segmento» in pratica e'
una calibrazione quasi globale con qualche cella spostata. I delta di cella
stimati vanno da +0,78 cr (D·[0,3), `n=49`) a +8,36 cr (A·[60+], `n=9`); tutti
**positivi**, cioe' l'intervallo si allarga ovunque: e' esattamente il modo di
«coprire allargando» che il criterio 4 esclude.

---

## 6. Tabella per cella — configurazione A (sonda, predizioni del 6/8)

Lasciata per confronto con L4.md §5.1, i cui numeri «prima» sono riprodotti
cifra per cifra (2024-25: globale 0,7176 vs 0,718 dichiarato; pinball 0,005502
vs 0,00550; fasce [0,3) 0,871 · [3,8) 0,684 · [8,15) 0,588 · [15,30) 0,867 ·
[30,60) 0,704 · [60+] 0,762 — identiche).

Dopo la calibrazione (A): [0,3) 0,903 · [3,8) 0,747 · [8,15) **0,745** (era
0,588, la cella peggiore di L4.md) · [15,30) 0,867 · [30,60) 0,815 · [60+] 0,810.
Celle `n >= 30`: D·[3,8) 0,721→0,721; C·[3,8) 0,606→0,758.

File completi: `l4_celle_*.csv`, `l4_fasce_*.csv`,
`l4_calibrazione_risultati*.json` in `w5` (suffisso vuoto = A, `_perriga` = B,
`_passo1` = C).

---

## 7. Prove automatiche

`tests/test_l4_calibrazione_prezzo.py`, 19 prove sulle sole funzioni pure
(fasce, punteggi conformal, shrink, copertura, pinball, applicazione dei delta),
nessun modello e nessun file d'asta: 1,99 s, **19 passate**.

Una prova e' stata **corretta dopo un fallimento**, e va dichiarato:
`test_calibrazione_raggiunge_il_nominale_in_campione` costruiva un campione con
errori a due soli valori (dentro/fuori di una quantita' fissa); su punteggi
degeneri il quantile 0,80 copre il 99 % e l'asserzione `<= 0,90` falliva. La
soglia **non e' stata toccata**: e' stato reso continuo l'errore del campione
(rumore gaussiano), che e' l'ipotesi sotto cui il quantile empirico ha il
significato dichiarato. Il campione era sbagliato, non la soglia.

---

## 8. Che cosa resta non deciso

- **Se gli intervalli siano correggibili con dati migliori**: non stabilito. Qui
  e' stabilito solo che con questo campione (255 e 336 righe, 2 celle su 24 con
  `n >= 30`) e con una catena non riproducibile a livello di 0,04 di copertura,
  la correzione per segmento fallisce i criteri.
- **Copertura sul martelletto individuale** (variante (b) di L4.md §7.2): non
  misurata, per tempo. Secondo `reports/LIVELLO4.md` §6.4 la dispersione e' ~3,46
  volte maggiore, quindi la copertura vera in asta e' **inferiore** a tutti i
  numeri qui riportati — IPOTESI riportata da quel report, non verificata qui.
- **Perche' la copertura di partenza cambi di 0,086 fra riesecuzioni**: separato
  in due contributi (data di rigenerazione: A vs B, −0,043; split per giocatore:
  B vs C, +0,086) ma non spiegato oltre.
