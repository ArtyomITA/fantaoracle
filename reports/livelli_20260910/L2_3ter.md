# COMPITO D (L2) — par.3ter: il cubo alimentato dal bersaglio onesto

Eseguito il 10/9/2026 dalle 13:00, ora limite 15:30. Marche: **RIPRODOTTO**
(comando eseguito oggi, con esito), **OSSERVATO NEL CODICE** (letto, con riga),
**IPOTESI**.

Criteri scritti **prima** dei numeri:
`…/scratchpad/w5/criteri_prima_L2.md` — corpo alle 13:15 (copia integrale del
criterio di `reports/livelli_20260910/L2.md` §6), nota sul budget alle 13:10 e
fissazione della squadra alle 13:10, entrambe anteriori a qualsiasi numero
della prova.

## Sommario

| voce | esito |
|---|---|
| passo 1 — `--bersaglio` nel pilota, predefinito invariato | fatto, provato |
| passo 2 — adattatore `bersaglio_origine` | fatto, provato |
| passo 3 — controfattuale sul produttore corrente | **superato**, exit 0 |
| prove del cubo | **371 passate, 1 saltata** (erano 360 + 1: +11 nuove) |
| prova decisiva §3ter, budget pieno | **NON SUPERATA: il cubo peggiora**, `d = +0,03459`, `es 0,00206`, `|t| = 16,83` contro soglia 2,776 |
| prova decisiva, coppia ridotta (conservata) | stesso verso, `d = +0,04615`, `|t| = 23,02` |
| marca «ridotto» | **no** sul verdetto finale; sì sulla coppia di §4.3 |

---

## 0. File toccati, e l'unico che il revisore sorveglia

| file | prima | dopo | perché |
|---|---|---|---|
| `scripts/l2_pilota_c2.py` | `e688e36901b3fa86` | `3d0a3351b0647e56` | passo 1 del compito: argomento `bersaglio` e opzione `--bersaglio` |
| `src/fantabot/tabellino/bersaglio_origine.py` | non esisteva | `3db769810e60376e` | passo 2: adattatore |
| `tests/test_l2_bersaglio_origine.py` | non esisteva | `fa4f283d512396d6` | prove del passo 2 |
| `tests/test_l2_ingressi_c2.py` | — | modificato | due casi nuovi del passo 1 |

**Da dichiarare al revisore, non da nascondere.**
`C:\…\scratchpad\w5\impronte_w5.json` contiene 33 voci, due delle quali **non**
compaiono nella lista di file congelati scritta nel mio compito:
`scripts/l2_pilota_c2.py` e `scripts/f0b_build_outputs.py`.

- `scripts/l2_pilota_c2.py`: modificato **da me**, perché il compito me lo
  ordina per nome (passo 1: «aggiungi a `costruisci_ingressi` un argomento
  opzionale … e l'opzione `--bersaglio`»). Copia del file com'era prima:
  `…/scratchpad/w5/ripristino/scripts__l2_pilota_c2.py`. Ripristinabile in un
  comando. Il comportamento predefinito è invariato e provato (§1).
- `scripts/f0b_build_outputs.py`: **non l'ho aperto né toccato** in nessun
  momento. Differisce dalla registrata `c3128c849ff4ccf7`, e differisce
  **due volte in modo diverso**: `ebafcebf223047fd` alle 13:12,
  `d972ee4b5ff7fbc0` alle 14:51, con `mtime` 2026-09-10 13:11:09 al primo
  controllo. RIPRODOTTO. Qualcun altro la sta riscrivendo mentre lavoro; lo
  segnalo perché il revisore non attribuisca la differenza a questo compito.

Nessun altro file dell'elenco differisce: 31 su 33 coincidono, RIPRODOTTO
ricalcolando lo sha256 di ciascuno alle 13:12 e di nuovo alle 14:51.

Uscite del pilota: gli artefatti finiscono in `data/l2/prove/2024-25__3TER_*`
perché è **quello che lo script fa per contratto** (`esec.apri(OUT, …,
prova=True)`, `scripts/l2_pilota_c2.py:417`) e cambiarlo avrebbe richiesto di
modificare il produttore più di quanto il compito chieda. Tutto il resto — log,
analisi, controfattuale, criteri, rapporto — sta in `…/scratchpad/w5/`.

---

## 1. Passo 1 — l'opzione `--bersaglio` (fatto)

OSSERVATO NEL CODICE, poi RIPRODOTTO.

- `costruisci_ingressi` ha due argomenti nuovi, entrambi con valore
  predefinito `None`: `bersaglio` (percorso del CSV per origine) e
  `cartella_bersaglio` (dove scrivere il JSON convertito).
- Con `bersaglio=None` la riga che costruisce il bersaglio è **la stessa di
  prima**: `presenze.costruisci(proc / f"b_predictions_{stagione}.json", …)`.
- `--bersaglio` aggiunto alla riga di comando; il piano registra
  `bersaglio` e `fonte_bersaglio` (`b_predictions` oppure
  `presenze_per_origine`), e il CSV entra fra le `impronte_ingressi`. Era
  esattamente il difetto che `L2.md` §2.3 segnala per il cubo: l'ingresso
  principale cambiava senza lasciare traccia.
- Il JSON dell'artefatto porta ora `bersaglio_ingresso` con la diagnostica
  della provenienza.

**Prove.** RIPRODOTTO:

```
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTHONIOENCODING=utf-8 PYTHONPATH=src \
  OMP_NUM_THREADS=3 python -m pytest tests/test_l2_*.py -q -p no:cacheprovider
371 passed, 1 skipped, 1 warning in 115.97s (0:01:55)
```

Erano **361 raccolte** (360 passate + 1 saltata) il 10/9 secondo `L2.md` §1;
ora sono **372 raccolte** (371 passate + 1 saltata): **+11**, cioè 9 casi nuovi
in `tests/test_l2_bersaglio_origine.py` e 2 in `tests/test_l2_ingressi_c2.py`.
Nessuna prova preesistente è stata cambiata o indebolita.

I due casi nuovi del passo 1 sono quelli che `L2.md` §7.1 chiede:
`test_senza_l_opzione_gli_ingressi_sono_identici_a_prima` confronta
`IngressiC2.vettori()` elemento per elemento con `contro.differenze` e chiede
anche l'uguaglianza stretta dei dizionari;
`test_con_l_opzione_cambia_il_bersaglio_e_non_l_universo` chiede
`bersaglio_grezzo` mosso, `universo` fermo, e il valore atteso `1/38` per il
primo giocatore del CSV finto.

---

## 2. Passo 2 — l'adattatore (fatto)

Modulo nuovo `src/fantabot/tabellino/bersaglio_origine.py`, tre funzioni:
`carica` (contratto del CSV), `adatta` (conversione, con diagnostica),
`costruisci_da_origine` (`presenze.costruisci` alimentata dal CSV).

La conversione, dichiarata in un posto solo:

- `pres` = `presenze_gia_fatte + presenze_residue_attese` — perché
  `presenze.costruisci` sottrae poi le presenze già fatte
  (`src/fantabot/tabellino/presenze.py:154-157`);
- `giornate_residue` = `orizzonte_giornate`, per giocatore;
- `presenze_gia_fatte` = `presenze_gia_fatte`, per giocatore.

Quindi la probabilità che ne esce è `presenze_residue_attese /
orizzonte_giornate`, e le presenze già fatte **non** la gonfiano. È il punto
dove l'unità di misura si sbaglia, e la prova
`test_confondere_le_unita_darebbe_un_altro_numero` fa vedere il numero
sbagliato accanto a quello giusto: passando le sole residue come `pres`, il
giocatore di prova varrebbe 0,1 invece di 0,5.

Le 9 prove nuove: probabilità calcolate a mano (0,5 su stagione intera, 0,5 a
stagione iniziata, troncamento di 25/20 a 1, zero tenuto come informazione),
somma dichiarata uguale a somma ottenuta, assente mandato al prior di ruolo e
**non** a zero, colonna mancante / orizzonte nullo / id ripetuti / file assente
rifiutati, e un caso che legge l'artefatto vero su disco.

---

## 3. Passo 3 — controfattuale sul produttore corrente (superato)

RIPRODOTTO alle 13:07-13:08:

```
PYTHONIOENCODING=utf-8 PYTHONPATH=src OMP_NUM_THREADS=3 \
python scripts/l2_controfattuale_c2.py 2024-25 \
  --fuori "…/scratchpad/w5/c2_controfattuale_2024-25.json"
```

**exit code 0**, stampa finale `PASSATO`. Contro il criterio scritto prima:

| criterio (scritto prima) | esito |
|---|---|
| `"passato": true` | `true` |
| `"dipendenze_senza_potenza": {}` | `{}` |
| `impronta_produttore` = impronta del file su disco | `3d0a3351b0647e56` = `3d0a3351b0647e56` |

Il controllo negativo regge: 50 996 righe posteriori al cutoff alterate,
**nessuna differenza**. I sei controlli positivi muovono tutti qualcosa; in
particolare «ruoli ruotati P→D→C→A→P» muove `bersaglio_obiettivo`,
`mappa_ruoli`, `parametri`, `squadre_scelte`.

Conseguenza sul documento: il terzo limite di `RIPRESA.md` §3bis — «`bersaglio`
e `squadre` non si muovono nemmeno perturbando i ruoli anteriori» — è
**smentito sul produttore corrente**, non più solo su un artefatto prodotto da
uno script cambiato dodici secondi dopo (`L2.md` §3). La smentita del 9
settembre resta leggibile accanto a questa, che la conferma.

Nota RIPRODOTTA dalla stampa: `679/679` giocatori coperti da
`b_predictions_2024-25.json`, quindi nel braccio di riferimento il prior di
ruolo non si attiva mai. Con il bersaglio per origine la copertura è
identica: 679 su 679 (RIPRODOTTO, `per_fonte: {'previsione': 679,
'prior_ruolo': 0, 'assente': 0}`).

---

### 3.1 Che cosa sono le «presenze realizzate»

RIPRODOTTO, perché il confronto abbia un'unità dichiarata: nel panel del
2024-25 ogni giocatore ha **esattamente 38 righe** (min 38, mediana 38, max
38). Quindi `osservato_riferimento` — la colonna che il pilota calcola come
media di `stato_voto == "con_voto"` — è **presenze a voto realizzate / 38**, ed
è confrontabile riga per riga con un bersaglio che è una probabilità per
giornata su un orizzonte di 38 giornate (`orizzonti_distinti: [38]`
nell'artefatto per origine). Sulla Fiorentina il tasso realizzato medio è
0,5346, con estremi 0,0 e 1,0.

---

## 4. Prova decisiva — coppia ridotta (RIPRODOTTA)

Due corse appaiate, avviate 13:11, finite 13:43 e 13:44, entrambe **exit code
0**. Squadra fissata a mano in entrambe (`--squadre Fiorentina`, 30 parametri),
stessi semi di verifica.

```
python scripts/l2_pilota_c2.py 2024-25 --cutoff 2024-08-17 --squadre Fiorentina \
  [--bersaglio data/l1/presenze/2024-25__origine20240816__a6a7eb010299/presenze_per_origine.csv] \
  --iterazioni 120 --sims 4 --sims-monitoraggio 6 --sims-verifica 12 --semi-verifica 5
```

**Ridotto, dichiarato prima**: 120 iterazioni invece di 200, `sims 4` invece di
6, `sims-verifica 12` invece di 16. `semi-verifica 5` invariato, perché la
soglia 2,776 dipende da quello.

Costo: 1658,8 s di ottimizzazione (246 valutazioni) col bersaglio onesto,
1642,3 s col bersaglio `b_predictions`; 66 s di modelli ciascuna.

### 4.1 I due bracci del criterio, contro le presenze realizzate

Braccio A = `bersaglio onesto da solo` (deterministico, non dipende dal seme).
Braccio B = `cubo alimentato dal bersaglio onesto`, cioè `C2`, il θ calibrato.
`d = MAE_cubo − MAE_bersaglio`; **d positivo = il cubo peggiora**.

| seme | bersaglio onesto | cubo C1 (θ=0) | cubo C2 (θ calibrato) | d = C2 − bersaglio |
|---|---|---|---|---|
| 20365638 | 0,3027 | 0,3726 | 0,3471 | +0,04442 |
| 20470367 | 0,3027 | 0,3708 | 0,3455 | +0,04289 |
| 20575096 | 0,3027 | 0,3706 | 0,3512 | +0,04852 |
| 20679825 | 0,3027 | 0,3808 | 0,3555 | +0,05283 |
| 20784554 | 0,3027 | 0,3678 | 0,3447 | +0,04208 |
| **media** | **0,3027** | **0,3725** | **0,3488** | **+0,04615** |

Differenze appaiate, cinque semi, quattro gradi di libertà:

| confronto | d medio | es(d) | \|t\| | soglia 2,776 | verso |
|---|---|---|---|---|---|
| C2 − bersaglio onesto | +0,04615 | 0,00200 | 23,02 | superata | **contro il cubo** |
| C1 − bersaglio onesto | +0,06988 | 0,00220 | 31,80 | superata | contro il cubo |
| C2 − C1 (contesto) | −0,02373 | 0,00116 | 20,49 | superata | a favore di θ |

### 4.2 Il braccio di riferimento con `b_predictions` (contesto)

| confronto | MAE / d | es(d) | \|t\| | verso |
|---|---|---|---|---|
| bersaglio `b_predictions` da solo | 0,2081 | — | — | — |
| cubo C1 | 0,2685 | — | — | — |
| cubo C2 | 0,2606 | — | — | — |
| C2 − bersaglio | +0,05256 | 0,00277 | 18,98 | contro il cubo |
| C1 − bersaglio | +0,06038 | 0,00221 | 27,30 | contro il cubo |
| C2 − C1 | −0,00782 | 0,00119 | 6,59 | a favore di θ |

### 4.3 Verdetto della coppia ridotta

**NON SUPERATO, e nella direzione contraria: il cubo peggiora.** Il criterio
D.5, scritto prima, dice esattamente che cosa fare in questo caso: «si scrive
che peggiora, e non si compensa con un'altra misura». Il cubo alimentato dal
bersaglio onesto sta **+0,046 di errore assoluto medio più lontano** dalle
presenze realizzate del bersaglio onesto lasciato solo, con `|t| = 23,0` contro
una soglia di 2,776. Lo stesso accade con il bersaglio contaminato
(`+0,053`, `|t| = 19,0`).

Due cose vanno dette accanto, senza che compensino il verdetto:

1. la calibrazione **funziona come meccanismo**: `θ` avvicina il cubo alle
   presenze realizzate in entrambe le corse (`−0,0237` e `−0,0078`, entrambe
   oltre soglia). Non basta: il divario da colmare è circa il doppio del
   guadagno ottenuto in 120 iterazioni;
2. il bersaglio onesto è **più lontano dalle presenze realizzate** del
   bersaglio contaminato (0,3027 contro 0,2081). È quello che il §3ter si
   aspettava — togliere `fvm` e `quot_fs_sett` peggiora la previsione — e non è
   una soglia: i quattro numeri pubblicati restano riferimenti di contesto,
   come impone il criterio D.7.

Marca dichiarata su **questa coppia**: **ridotto**. La riduzione toglie
iterazioni al braccio «cubo», cioè lavora **contro** il cubo. IPOTESI scritta
qui prima di eseguire la corsa piena, e lasciata leggibile: con 200 iterazioni
il divario si accorcerebbe ma non si chiuderebbe. §4.4 la mette alla prova.

Le corse sono state eseguite **in parallelo** sulla stessa macchina, con altri
agenti attivi: il tempo di orologio non è una misura pulita del costo, i
conteggi di valutazione sì.

## 4.4 Corsa piena col bersaglio onesto — RIPRODOTTA, **non ridotta**

Avviata 13:45, finita 14:50, **exit code 0**. Budget pieno di `L2.md` §6:

```
python scripts/l2_pilota_c2.py 2024-25 --cutoff 2024-08-17 --squadre Fiorentina \
  --bersaglio data/l1/presenze/2024-25__origine20240816__a6a7eb010299/presenze_per_origine.csv \
  --iterazioni 200 --sims 6 --sims-monitoraggio 10 --sims-verifica 16 --semi-verifica 5
```

200 iterazioni, 406 valutazioni di ottimizzazione + 32 di monitoraggio,
**3632,1 s**; modelli in 35,4 s. Artefatto:
`data/l2/prove/2024-25__3TER_ONESTO_PIENO__839b6bc75c47`.

| seme | bersaglio onesto | cubo C1 (θ=0) | cubo C2 (θ calibrato) | d = C2 − bersaglio |
|---|---|---|---|---|
| 20365638 | 0,3027 | 0,3728 | 0,3365 | +0,03386 |
| 20470367 | 0,3027 | 0,3700 | 0,3387 | +0,03605 |
| 20575096 | 0,3027 | 0,3716 | 0,3327 | +0,03008 |
| 20679825 | 0,3027 | 0,3803 | 0,3444 | +0,04170 |
| 20784554 | 0,3027 | 0,3674 | 0,3339 | +0,03128 |
| **media** | **0,3027** | **0,3724** | **0,3372** | **+0,03459** |

| confronto | d medio | es(d) | \|t\| | soglia 2,776 | verso |
|---|---|---|---|---|---|
| **C2 − bersaglio onesto** | **+0,03459** | **0,00206** | **16,83** | **superata** | **contro il cubo** |
| C1 − bersaglio onesto | +0,06976 | 0,00216 | 32,30 | superata | contro il cubo |
| C2 − C1 (contesto) | −0,03516 | 0,00130 | 27,10 | superata | a favore di θ |

---

## 4.5 VERDETTO

**NON SUPERATO.** Il cubo, alimentato dal bersaglio onesto, resta **più lontano
dalle presenze realizzate** del bersaglio onesto lasciato solo: `d = +0,03459`,
`es(d) = 0,00206`, `|t| = 16,83` contro la soglia 2,776 fissata prima. Il segno
è contro il cubo e l'intervallo esclude lo zero, quindi vale il punto D.5 del
criterio: si scrive che peggiora, e non lo si compensa con un'altra misura.

Il verdetto **non è ridotto**: viene dalla corsa a budget pieno (200 iterazioni,
`sims 6`, `sims-verifica 16`, 5 semi), cioè esattamente il comando che `L2.md`
§6 descrive, salvo la squadra fissata a mano e l'origine del 16 agosto.

**La conclusione ridotta di §4.3 resta scritta e non viene cancellata**: diceva
la stessa cosa con `d = +0,04615`, `|t| = 23,02`. Raddoppiare le iterazioni ha
accorciato il divario da +0,046 a +0,035, cioè di circa un quarto, senza
chiuderlo. L'IPOTESI che avevo dichiarato in §4.3 — «si accorcia ma non si
chiude» — è ora RIPRODOTTA a 200 iterazioni, e resta un'ipotesi per ogni
budget più grande di 200: non ho misurato oltre.

Quel che è dimostrato a favore del meccanismo, e va detto senza che compensi il
verdetto: `θ` funziona e la sua efficacia cresce col budget — `C2 − C1` vale
−0,0237 a 120 iterazioni e −0,0352 a 200, entrambi ben oltre soglia. Il cubo
calibrato è molto meglio del cubo non calibrato; è comunque peggio del
bersaglio da solo.

---

## 5. Che cosa questa prova NON decide

Copiato da `L2.md` §6 e non ampliato: non decide se il cubo serva, decide se la
calibrazione delle marginali abbia senso a ingressi puliti. Restano fuori le
dipendenze fra compagni, la durata delle assenze e le decisioni d'asta — cioè i
tre luoghi dove il report del 9/9 sostiene che il cubo dovrebbe guadagnare.

Limiti specifici di questa esecuzione, tutti dichiarati:

1. **30 giocatori, una squadra, una stagione.** Fiorentina, 2024-25. Fissata a
   mano in entrambe le corse perché il criterio automatico ordina per somma dei
   bersagli dei portieri, e con due bersagli diversi avrebbe scelto squadre
   diverse, rendendo i bracci non appaiati.
2. **L'origine è il 16 agosto 2024, il cutoff del pilota è il 17.** Un giorno di
   scarto, dichiarato in `L2.md` §6 e non risolto: l'artefatto per origine
   esisteva già su disco e rigenerarlo non rientrava nel tempo.
3. **L'artefatto per origine è a 3 semi, non 5** (`diagnostica.json`:
   `"semi": 3`, scarto medio fra semi 0,798 presenze). Il compito prevedeva
   `--semi 5` solo nel caso in cui l'artefatto mancasse; non mancava, e non è
   stato rigenerato.
4. **Il bersaglio onesto copre 679 su 679**, quindi il prior di ruolo non entra
   e il confronto non è disturbato da ripieghi.
5. **`osservato_riferimento` è diagnostico per costruzione**: non entra
   nell'obiettivo, nel bersaglio né nella scelta delle squadre. Entra solo qui,
   nella misura finale, che è ciò che la prova chiede.

---

## 6. Suite intera del progetto (fuori dal perimetro, ma va detto)

RIPRODOTTO alle 13:16-13:22:

```
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTHONIOENCODING=utf-8 PYTHONPATH=src \
  OMP_NUM_THREADS=1 python -m pytest tests -q -p no:cacheprovider
1 failed, 660 passed, 2 skipped, 5 xfailed in 364.34s
```

L'unico fallimento è `tests/test_bot_l3_parita.py::test_il_piano_cambia_davvero_l_asta`.
OSSERVATO NEL CODICE: quel file importa `fantabot.bots.bot_l3`,
`fantabot.engine.auction`, `fantabot.models` e `l3_confronto_asta`; **non**
importa niente di quello che ho toccato (`scripts/l2_pilota_c2.py`,
`src/fantabot/tabellino/bersaglio_origine.py`). È materia del Livello 3 e di un
altro compito in corso. Non l'ho toccato e non l'ho indebolito; lo segnalo
perché non resti invisibile.

---

## 7. Che cosa ho eseguito, e che cosa no

Eseguito: la suite `tests/test_l2_*.py` (371 passate, 1 saltata), la suite
intera (1 fallita fuori perimetro), `scripts/l2_controfattuale_c2.py` (exit 0),
una corsa di fumo del pilota, due corse appaiate del pilota ridotte, una corsa
piena col bersaglio onesto.

Le prove del cubo sono state rieseguite alla fine, dopo tutte le corse:
**371 passate, 1 saltata, 78,76 s** (RIPRODOTTO alle 14:53).

### Artefatti

In `…/scratchpad/w5/`: `criteri_prima_L2.md`, `L2_3ter.md` (questo),
`c2_controfattuale_2024-25.json`, `log_controfattuale.txt`,
`log_pilota_3ter.txt` (braccio onesto ridotto), `log_pilota_3ter_bpred.txt`,
`log_pilota_3ter_pieno.txt` (braccio onesto pieno), `log_pytest_l2.txt`,
`analisi_3ter.py`, `analisi_3ter.json`,
`ripristino/scripts__l2_pilota_c2.py`.

In `data/l2/prove/`, perché lo script ci scrive per contratto:
`2024-25__3TER_ONESTO_PIENO__839b6bc75c47` (la corsa del verdetto),
`2024-25__3TER_ONESTO__4c1b19c48752`, `2024-25__3TER_BPRED__9d6498e01b5b`,
`2024-25__FUMO__9c22e29edfea` (corsa di fumo da 1 iterazione, tenuta perché il
suo log è la fonte della stima di costo scritta nei criteri).

Non eseguito: `scripts/l2_banco_confronto.py`, `scripts/l2_genera_cubo.py`, il
passo 4 di `L2.md` §7 (impronta dello script dentro `coincidenza_col_candidato`
in `scripts/l2_verifica_c2.py`) e il passo 5 (impronta del bersaglio nel
rapporto del cubo, con rigenerazione del cubo 2026-27, che `L2.md` dichiara «da
non fare prima dell'asta»). Nessun file del percorso d'asta è stato letto per
scriverlo né modificato.
