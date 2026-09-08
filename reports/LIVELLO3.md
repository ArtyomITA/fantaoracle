# Livello 3 — scelta della rosa e prezzo di indifferenza per P(primo posto)

7 settembre 2026. Documento operativo. Criteri e contratto degli stati:
[CRITERI_L2_L3.md](CRITERI_L2_L3.md), congelati prima di produrre questi
numeri.

**Niente è stato attivato.** Copilota, pack operativi, bot A/B/C e
ottimizzatore non sono stati toccati nel loro comportamento. Il Livello 3 vive
in `src/fantabot/livello3/` e in `scripts/l3_*.py`, e si prova con comandi
espliciti.

---

## 1. L'obiettivo, scritto per intero

Per una decisione o politica `a`, uno stato d'asta `S` e uno scenario `ω`:

    W(a, S, ω) = 1 se la nostra squadra termina prima secondo le regole della
                 lega; 0 altrimenti

    P̂1(a | S) = media di W(a, S, ω) sugli scenari di ottimizzazione

La catena che porta da una decisione a `W` è: acquisti → rose esclusive →
formazioni lecite → sostituzioni → bonus e modificatore → gol da fasce →
calendario testa a testa → classifica.

Massimizzare i fantapunti totali, o l'upside, o il rendimento sopra gli
avversari, può generare candidate utili. **Non è lo stesso obiettivo**, e il
Livello 3 non fa finta che lo sia.

### 1.1 I pari merito non li decide l'ordine alfabetico

Se dopo tutti i criteri di spareggio più squadre restano prime, la vittoria è
**condivisa**: ciascuna riceve 1/k. È l'unico trattamento che non inventa un
vincitore. Chi vuole un'altra convenzione la dichiara in
`Regole.parita_finale`; l'alternativa implementata è `nessuno` (la vittoria
non viene assegnata). Il numero di scenari finiti a pari merito viene sempre
riportato.

### 1.2 Che cosa resta fisso e che cosa varia

Fisso: il calendario già noto, i risultati già osservati, i punti già
realizzati. **Non** si assegnano retroattivamente a una rosa comprata oggi i
punti di giornate a cui non partecipava.

Varia: la stagione calcistica (dal cubo), il completamento dell'asta, il
comportamento degli avversari, l'incertezza sui parametri del modello di
partita (propagata estraendo le forze una volta per scenario).

**Il calendario della nostra lega non è noto.** Viene generato da un seme
dichiarato, e ogni risultato porta `calendario_dichiarato = True`: è un
confronto condizionato a un banco, non la probabilità di vincere la lega
reale. Se il calendario e la classifica di partenza vengono forniti, il
valutatore li usa (`stato_iniziale`); non li inventa.

---

## 2. I tre componenti

### 2.1 Valutatore degli scenari — `src/fantabot/livello3/valutatore.py`

Riceve cubo, rose esclusive, regole, calendario e stato iniziale. Restituisce
punteggi per giornata, gol da fasce, punti di lega, posizione e quota di
vittoria.

Proprietà fissate da 13 test (`tests/test_l3_valutatore.py`), tutti superati:

| test | che cosa fissa |
|---|---|
| `test_punteggio_giornata_calcolato_a_mano` | undici giocatori a voto, nessuna panchina: il punteggio è la somma esatta dei fantavoti |
| `test_gol_da_fasce_sui_confini` | 65,5 → 0 gol; 66,0 → 1; 71,5 → 1; 72,0 → 2; 78,0 → 3 |
| `test_campionato_a_due_squadre_calcolabile` | due giornate, punteggi 71,5 e 66,0, un gol a testa, due pareggi, 2 punti a testa, prima chi ha più fantapunti |
| `test_parita_totale_vittoria_condivisa` | due squadre identiche: mezza vittoria a testa, e zero con la convenzione `nessuno` |
| `test_invarianza_all_ordine_delle_squadre` | riordinare le squadre non cambia punteggi né vittorie |
| `test_punteggi_non_dipendono_da_quante_rose_si_valutano` | il punteggio di una rosa è lo stesso da sola o in mezzo ad altre |
| `test_esclusivita_dei_giocatori` | lo stesso giocatore in due squadre della lega è un errore, non un dettaglio |
| `test_rosa_incompleta_rifiutata` | quote per ruolo verificate prima di valutare |
| `test_nessuna_anticipazione_nella_formazione` | permutare gli esiti futuri non cambia i punteggi delle giornate già decise |
| `test_calendario_completo_e_bilanciato` | 10 squadre, 18 giornate: 5 partite per giornata, ogni coppia due volte una per campo |
| `test_differenza_appaiata_riconosce_il_nulla` | confrontare una valutazione con sé stessa dà differenza zero |
| `test_stato_iniziale_non_inventato` | senza stato iniziale si parte da zero, e il risultato lo dichiara |
| `test_calendario_dichiarato_e_segnalato` | il banco dichiarato è marcato come tale |

### 2.2 Ricerca — `src/fantabot/livello3/ricerca.py`

Si chiama **ricerca su candidate per l'obiettivo SAA**. Non è ottimo globale, e
il modulo lo dice nella prima riga della sua documentazione.

Quattro passaggi: generazione di rose ammissibili con obiettivi diversi (il
MILP esistente con pesi e vincoli variati), scambi locali iterativi valutati
con l'obiettivo vero, scelta sugli scenari di ricerca, verifica su scenari mai
usati per scegliere.

Le famiglie esplorate comprendono esplicitamente **due punte di prima fascia**
(quota di spesa in attacco 60-75%), l'alternativa con una sola punta forte, la
difesa da modificatore e due gradi di profondità della panchina. La quota
d'attacco è un intervallo di spesa, non l'obbligo di comprare due nomi: se i
prezzi non lo giustificano, vince un'altra candidata.

**Gli avversari si costruiscono dal pool che resta dopo la nostra rosa.**
Nell'asta vera un giocatore sta in una squadra sola, e chi compriamo noi non
lo compra nessun altro.

#### Tre difetti trovati e corretti durante l'implementazione

| difetto | come si è visto | correzione |
|---|---|---|
| gli avversari greedy non rispettavano il budget | AVV01 costava **1452 crediti su 500** e vinceva il 100% degli scenari | riserva di un credito per posto vuoto, prezzo pagato tracciato per giocatore, controllo finale che il costo non superi il budget |
| la riserva sbagliava di un credito | costo 501 su 500 | la riserva si calcola con il giocatore già dentro la rosa: i posti che restano sono quelli, e ognuno costa almeno un credito |
| gli avversari greedy erano deboli | la nostra rosa faceva 70,1 punti a giornata contro 52-65, e vinceva il 90% | avversari costruiti con lo stesso MILP che usiamo noi, con obiettivi diversi e rumore sulle valutazioni: 9 avversari in 2,3 s, punti a giornata 61-70 contro i nostri 70,1 |

Sette test in `tests/test_l3_ricerca.py`, tutti superati. Il più severo:
su un'istanza con **150 rose legali** enumerate tutte, la ricerca locale
partita dalla rosa peggiore raggiunge il massimo enumerato.

### 2.3 Formulazione esatta — `src/fantabot/livello3/esatto.py`

Serve a due cose: verificare la ricerca dove il massimo si può calcolare, e
mostrare **dove** il problema smette di essere lineare invece di dirlo a
parole.

La formulazione è esatta sotto tre ipotesi, controllate dal codice prima di
risolvere:

1. la rosa coincide con la formazione (le quote sommano a undici e tutti
   prendono voto): senza, il punteggio dipende dalla scelta non anticipativa
   degli undici, che non è rappresentabile con variabili di acquisto;
2. gli avversari sono fissati: le loro rose non dipendono da cosa compriamo;
3. gli scenari sono un campione finito dato.

I gol da fasce diventano lineari perché l'avversario è fissato: «facciamo
almeno k gol» è la condizione `P ≥ 66 + 6(k−1)`, una sola soglia. Servono due
indicatori per giornata e scenario, con un big-M pari all'intervallo dei
punteggi possibili, e un indicatore per scenario sul primo posto.

Sei test in `tests/test_l3_esatto.py`, tutti superati. Il decisivo:
**la formulazione dà lo stesso ottimo dell'enumerazione completa**, e la rosa
che trova vale davvero quel numero quando la si valuta a parte.

Dove smette di funzionare, con i numeri: con 200 scenari e 38 giornate i
binari degli esiti sono 15.200, più quelli della rosa. Non è la dimensione a
renderlo impraticabile: sono le ipotesi 1 e 2, che nell'asta vera non valgono.

### 2.4 Prezzo di indifferenza — `src/fantabot/livello3/indifferenza.py`

    Δ(i, p, S) = P1(compro i a p e completo l'asta) − P1(passo e completo l'asta)

Entrambi i rami arrivano a rose complete e legali per tutte le squadre, con
budget aggiornati, posti e ruoli rimanenti, giocatori ancora sul mercato,
alternative acquistabili, e — nel ramo «passo» — il giocatore comprato da un
avversario, quindi non più disponibile per nessuno.

Le condizioni esterne sono le stesse nei due rami, replica per replica:
stesso ordine di completamento, stesso rumore, stessi scenari, stesso
calendario. La differenza è appaiata.

**Nessuna ricerca binaria.** `Δ` non è garantito monotono nel prezzo: crediti
e acquisti sono discreti. Il modulo valuta tutti i prezzi interi della griglia
richiesta, restituisce la curva intera e conta i cambi di segno.

#### Il difetto che rendeva il confronto vuoto

Nel primo giro sui dati veri la differenza era **identica a ogni prezzo**:
+0,0125 a 22, 38, 53 e 68 crediti. Causa: il completamento sceglieva i
giocatori col miglior rapporto fra valore e prezzo, si fermava intorno ai 200
crediti e lasciava il resto in cassa. Da quel momento il budget non vincolava
più niente, e pagare 22 o 68 non cambiava nulla.

Corretto: il completamento ora **spende i crediti che avanzano**, sostituendo
il giocatore più debole con il migliore che il residuo permette, finché
migliora. Dopo la correzione la curva varia davvero:

| giocatore | 22 cr | 38 cr | 53 cr | 68 cr |
|---|---|---|---|---|
| De Ketelaere | +0,0250 | +0,0375 | +0,0250 | **−0,0250** |

I crediti che restano a fine asta valgono zero: tenerli non è prudenza, è
valore buttato. Durante l'asta valgono quanto le occasioni che restano, ed è
esattamente quello che questa procedura misura.

Undici test in `tests/test_l3_indifferenza.py`, tutti superati, fra cui: un
fuoriclasse a 1 credito deve convenire; il prezzo oltre il massimo legale è
rifiutato; un giocatore già venduto è rifiutato; i due rami producono rose
diverse; la memoria evita di ricalcolare.

---

## 3. Costi misurati

Pilota su dati veri (`scripts/l3_pilota.py`, cubo 2026-27 da 40 scenari × 35
giornate × 587 giocatori, 11,2 MB su disco, 7,1 MB in memoria):

| operazione | tempo |
|---|---|
| caricamento di pack e cubo | 1,5 s |
| MILP per una candidata | 0,5 s |
| valutazione di una candidata (10 scenari, 9 avversari MILP) | 5,8 s |
| valutazione di una candidata (20 scenari) | 6,7 s |
| ricerca su 6 candidate (20 ricerca + 20 verifica) | 46,7 s |
| una curva di indifferenza (4 prezzi, 4 repliche, 20 scenari) | 21-58 s |
| un'asta completa a 10 bot + valutazione su 20 scenari | 10-12 s |

Memoria di picco del pilota: 36,8 MB.

Da questi numeri si dimensionano gli esperimenti: una curva di indifferenza per
ogni giocatore del piano costa minuti, non secondi. Per l'uso in asta serve il
precalcolo, e il bot conta e riporta quante volte ha davvero usato il tetto per
indifferenza e quante volte è ripiegato sul tetto del bot B.

---

## 4. Un'incoerenza trovata nel bot attuale

`montecarlo.choose_objective` costruisce il piano con
`min_spend = MIN_SPEND_FRAC × budget` (riga 371) e `f13_validate_plan.py` lo
valida con la stessa soglia (righe 62-65). **`bot_b.py` non contiene nessuna
occorrenza di `min_spend`**: la sua `_replan` chiama `optimize_roster` senza
quella soglia.

Il bot ripianifica dopo ogni proprio acquisto, dopo ogni target perso e ogni
dieci martelletti. Quindi, dal primo replanning in avanti, segue un piano
diverso da quello che è stato scelto e validato — e quel piano non ha nessun
motivo di impegnare il budget.

Non è una scelta di politica: è un'incoerenza fra due parti dello stesso
sistema, ed è un candidato serio come causa del residuo di cassa.

La variante corretta è implementata in `bot_l3.BBotCoerente` ed è uno dei
quattro trattamenti del confronto d'asta. **Non è stata promossa**: il bot B
resta quello che è finché la misura non dice il contrario.

---

## 4-bis. Prima misura del residuo di cassa, e quanto serve per misurarlo

Confronto appaiato B contro B+ (la variante con la soglia di spesa coerente),
10 repliche, sedie ruotate, nove avversari dichiarati prima, 40 scenari:

| | P(1 posto) | punti a giornata | speso | residuo |
|---|---|---|---|---|
| B congelato | 0,0675 | 66,90 | 423,1 | **76,9** |
| B coerente | 0,0700 | 66,91 | 452,1 | **47,9** |

Differenza appaiata di P(1 posto): **+0,0025, intervallo 95% [−0,0275,
+0,0275]**: attraversa lo zero, **inconcludente**.

Lettura onesta: la soglia coerente **riduce il residuo di 29 crediti** — il
meccanismo del residuo e' identificato e chiuso — ma su dieci repliche **non
sposta in modo misurabile la probabilita' di arrivare primi**. Spendere quei
crediti non compra vittorie in questo banco; non le perde nemmeno.

Quanto servirebbe per concludere: lo scarto della differenza appaiata misurato
e' 0.0478. Per un intervallo di semiampiezza 0,02 servono
22 repliche, circa
8 minuti per coppia di trattamenti. E'
alla portata, e il confronto finale va fatto a quella numerosita'.

Due avvertenze che non vanno perse: questi numeri vengono dal cubo **prima**
delle correzioni, e P(1 posto) e' sotto 0,1 per entrambi, cioe' sotto la quota
a priori di un tavolo a dieci. In questo banco il bot non batte gli avversari:
e' un fatto da spiegare, non da nascondere.

---

## 4-ter. Il confronto d'asta misurava zero, e perché

Il confronto a quattro trattamenti (`scripts/l3_confronto_asta.py`) girava
già, ma su due repliche di prova B+, L3 e L3+I compravano **la stessa identica
rosa**: speso 419 e 434 crediti uguali al credito, stessi punti per giornata.
Un confronto che non distingue i trattamenti non misura niente, e la media di
quei numeri sarebbe stata pubblicabile senza che nulla la contraddicesse.

Due difetti distinti, entrambi trovati leggendo il rapporto del bot e non i
risultati:

**Il piano del Livello 3 non sopravviveva alla ripianificazione.**
`BotL3.start_auction` metteva i giocatori del piano nei target, ma
`BBotCoerente._replan` — che parte dopo ogni acquisto, ogni target perso e ogni
dieci martelletti — li sostituiva con la soluzione MILP. Dopo pochi lotti il
piano era sparito e il bot era `B+`. La prova: `fuori_piano` valeva 0 e
`ripiego_q90` 177, cioè il bot valutava solo i propri target, e quei target
erano quelli del MILP.

Correzione: `BotL3._replan` ripianifica come prima, poi **riàncora al piano**
(`_ancora_al_piano`). I giocatori del piano ancora in vendita rientrano nei
target per primi, i posti che avanzano si riempiono con la soluzione MILP
appena calcolata. Il conto rispetta le quote residue e tiene un credito per
ogni posto che resterebbe vuoto: un piano che non entra nel budget rimasto
viene troncato, non forzato. I test in `tests/test_bot_l3_piano.py` fallivano
prima della correzione e passano dopo.

**I tetti di indifferenza non venivano mai passati.** `main` chiamava
`gioca_asta(pack, tr, seme, seggio, piano, None)`: l'ultimo argomento sono i
tetti, e valeva `None` sempre. Il rapporto del bot lo diceva a chiare lettere,
`giocatori_con_tetto: 0`. L3+I era L3.

Correzione: `scripts/l3_tetti.py` calcola le curve una volta sola prima delle
repliche (dipendono dal cubo e dal piano, non dalla replica) e
`l3_confronto_asta.py` le carica con `--tetti`.

### E il risultato di quel calcolo è un esito, non un successo

Venticinque giocatori del piano, venticinque curve, **venticinque stati
`inconcludente`**: nessun prezzo della griglia ha una differenza il cui
intervallo al 95% escluda lo zero. La regola d'uso, scritta prima in
[CRITERI_L2_L3.md](CRITERI_L2_L3.md) §3.8, dice che con stato `inconcludente`
il tetto non entra in asta.

Quindi **L3+I coincide con L3 per costruzione**, e la differenza fra i due
trattamenti sarà zero. Non perché le due politiche si equivalgano: perché la
seconda non si è potuta applicare in nessun lotto. Presentare quello zero come
"nessuna differenza fra le politiche" sarebbe falso.

Con 20 scenari e 4 repliche per prezzo, la risoluzione della differenza è di
circa 0,05 di probabilità: gli effetti che stiamo cercando sono più piccoli.
Servono più scenari per replica, non una soglia più permissiva.


---

## 5. Il confronto d'asta: che cosa dicono 22 repliche

`scripts/l3_confronto_asta.py --repliche 22 --scenari 40`, cubo 2026-27
corretto (con i gol subiti dei portieri, quindi col bonus porta inviolata),
piano dalla ricerca su candidate, tetti dal prezzo di indifferenza. Quattro
trattamenti in mondi separati, stessi nove avversari, stesso seme, sedie che
ruotano fra le repliche. 88 aste su 88 riuscite, 1.244 secondi.

Il numero di repliche non è stato scelto guardando i risultati: viene dalla
misura di potenza fatta prima (deviazione standard 0,0478 sulla differenza
appaiata, semiampiezza voluta 0,02, 22 repliche).

| trattamento | P(1° posto) | punti/giornata | speso | residuo | differenza rispetto a B |
|---|---|---|---|---|---|
| **B** congelato | 0,0943 | 68,61 | 429,6 | 70,4 | — |
| **B+** coerente | 0,0909 | 68,69 | 461,7 | 38,3 | −0,0034 [−0,0216; +0,0125] **inconcludente** |
| **L3** selezione | 0,0318 | 67,22 | 370,7 | 129,3 | −0,0625 [−0,1148; −0,0193] **esclude lo zero** |
| **L3+I** con tetti | 0,0318 | 67,22 | 370,7 | 129,3 | −0,0625 [−0,1136; −0,0182] **esclude lo zero** |

> **AVVERTENZA, aggiunta dopo la revisione indipendente del 7 settembre, ore
> 22:30.** Il numero −0,0625 è riprodotto e corretto, ma **l'attribuzione
> causale qui sotto non regge**: il braccio L3 differisce da B+ per due cose
> insieme, non per una. `BotL3._ancora_al_piano` sostituisce i target del MILP e
> con essi butta via il pavimento di spesa `min_spend`, riducendo del 15% la
> spesa pianificata a ogni ripianificazione. E il contatore `piano_perso`
> include anche i giocatori del piano **comprati da noi**: dei 20 «persi» della
> replica 0, dieci erano in rosa nostra, e a fine asta L3 ne possiede 10-13 su
> 25, non 3. Quindi le due frasi «il Livello 3 peggiora la probabilità di
> arrivare primi» e «non riesce a comprare il piano» **non sono sostenute**
> dall'esperimento come costruito. Il dettaglio, la correzione progettata e la
> coda di lavoro stanno in [RIPRESA_L2_L3.md](../RIPRESA_L2_L3.md) §2.1 e §2.2.
> Il resto dell'esperimento è stato verificato e regge: aritmetica di P(1°),
> conversione delle chiavi, simmetria dei mondi, bootstrap.

### Il risultato, detto senza attenuazioni

**Il Livello 3 peggiora la probabilità di arrivare primi.** La differenza è
−0,0625, l'intervallo al 95% esclude lo zero, e il criterio scritto prima
([CRITERI_L2_L3.md](CRITERI_L2_L3.md) §3.6) chiedeva una differenza **positiva**
con intervallo che escludesse lo zero per promuoverlo. È il contrario. Su 22
repliche L3 batte B in 4, pareggia in 6, perde in 12.

**L3+I è identico a L3**, e non perché le due politiche si equivalgano: nessuno
dei 25 tetti di indifferenza aveva uno stato utilizzabile (§4-ter), quindi il
prezzo di indifferenza non ha deciso nemmeno un lotto. `tetto_indifferenza: 0`
in tutte le 22 repliche.

**B+ resta inconcludente** sulla probabilità, come nella misura precedente:
−0,0034 con intervallo [−0,0216; +0,0125]. Sul residuo di cassa fa quello che
prometteva: da 70,4 a 38,3 crediti medi, e il minimo speso sale da 307 a 414.
Spendere di più non ha però comprato probabilità misurabile.

### Perché il Livello 3 perde: la causa è misurata, non congetturata

Il rapporto del bot dice che, delle 25 posizioni del piano, ne perde in media
**21,73** (minimo 20, massimo 23): gli avversari comprano i giocatori del piano
prima di lui, o a prezzi che lui non rilancia. Quello che resta è un piano
monco, e il bot finisce l'asta con **129,3 crediti in mano** contro i 70,4 di B
e i 38,3 di B+ — cioè il difetto che questa sessione doveva ridurre, peggiorato.

La ragione è strutturale, e riguarda l'obiettivo, non l'implementazione: **la
ricerca su candidate sceglie la rosa ai prezzi q50, come se fossero prezzi di
listino da pagare.** In asta i prezzi si formano per competizione: un piano che
costa 499,86 crediti a q50 non è comprabile quando nove avversari rilanciano
sugli stessi nomi. Il piano ha P(1°) 0,40 nella verifica su scenari mai usati e
0,032 in asta: il divario non è rumore, è la distanza fra "questa rosa vince"
e "questa rosa è ottenibile".

Il prossimo passo naturale è un obiettivo che tenga conto della distribuzione
dei prezzi d'asta e della concorrenza, non del solo q50 — ma è un lavoro nuovo,
con un criterio da scrivere prima, non una taratura di questo.

### Stato delle fasi

| fase | stato |
|---|---|
| valutatore, ricerca, formulazione esatta, prezzo di indifferenza | implementati e verificati su casi controllati |
| correzioni del panel e del contratto temporale | fatte, verificate da test |
| procedura unica del modello di partita | fatta, scarto 0,000 fra banco e cubo |
| invarianti fisiche del generatore | fatte, verificate da test che fallivano prima |
| banco del Livello 2 corretto | fatto: il cubo **non** è promosso (LIVELLO2.md §7) |
| confronto d'asta a quattro trattamenti | fatto: il Livello 3 **peggiora** P(1°) |
| calibrazione della distribuzione dei gol (G1) | esito inconcludente, resta il comportamento attuale |

**Il Livello 3 resta un'implementazione sperimentale verificata su casi
controllati. Non è una strategia validata per l'asta, e questi numeri dicono
che oggi non va usato per scegliere una rosa.** Il comportamento predefinito
del Copilota non è stato cambiato.
