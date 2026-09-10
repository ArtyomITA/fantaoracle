# Punto di ripresa corrente — FantaOracle

**Aggiornato il 9 settembre 2026, dopo l'audit sull'avanzamento dei
livelli.** Il fatto nuovo che conta e' in §3ter: due feature del modello
delle presenze contengono l'esito, e questo vizia il confronto su cui si
reggeva la lettura del ramo. Questo è il
puntatore corrente per il lavoro sui livelli; per l'asta vera il punto di
ripresa è `RIPRESA_ASTA.md` e la guida operativa è `GUIDA_ASTA.md`.

Regole della sessione che restano valide: criteri scritti **prima** degli
esperimenti; un test fallito non si risolve indebolendo il test; una soglia non
si sposta dopo aver visto i risultati; pack operativi, Copilota, bot
predefinito e mirror GitHub non si toccano; niente push senza permesso.

---

## 1. Dove siamo

| fase | stato | dove leggerlo |
|---|---|---|
| R1 contratto temporale | conclusa | `reports/PROTOCOLLO_v2.md` §16.1 |
| R2 adattatore delle presenze | conclusa | §16.2 |
| R3 distribuzione campionata | conclusa | §16.3 |
| R4 inferenza del fattoriale | conclusa e verificata | §18, §19, §20 |
| ciclo del 9/9: correzioni ai difetti riprodotti | concluso | `reports/CICLO_20260909.md` |
| pilota C2 (calibrazione delle presenze) | **eseguito, candidato non promosso** | §3bis, `reports/PIANO_C2_20260909.md` |
| progressivo | **percorso verificato, esperimento non concluso** | `CICLO_20260909.md` §2, §5 |
| L3, L4 | **sospesi** | — |

Suite, comando completo — servono tutti e tre i pezzi:

```bash
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTHONIOENCODING=utf-8 PYTHONPATH=src python -m pytest tests/ -q
```

La suite: **562 passati, 1 saltato**. Servono tutti e tre i pezzi del comando —
senza `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1` un plugin di terze parti esplode
all'autoload perche' manca `pkg_resources`.

Senza `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1` un plugin di terze parti (`fugue_test`)
esplode all'autoload perché manca `pkg_resources`; senza `PYTHONPATH=src` e
senza il target `tests/` la collezione fallisce con 28 errori. Non è un problema
del progetto, ma il comando va scritto per intero.

---

## 2. Il risultato corrente del banco

A informazione comparabile **il cubo perde**. Non è un margine incerto: gli
intervalli two-way escludono lo zero su entrambe le stagioni, entrambe le
misure, entrambi i punteggi.

| confronto | 2024-25 | 2025-26 |
|---|---:|---:|
| `C1 − I1`, CRPS empirico | +0,097268 | +0,050467 |
| `C1 − I1`, CRPS equo | +0,105028 | +0,058438 |
| interazione, CRPS empirico | +0,160866 | +0,071504 |

L'interazione positiva significa: **il cubo trae meno dalle presenze del
modello** di quanto ne tragga il simulatore per giocatore.

Il Livello 2 resta **non promosso**.

### Comandi che li riproducono

```bash
PYTHONPATH=src python scripts/l2_banco_confronto.py 2024-25 --sims 30 --semi 8
PYTHONPATH=src python scripts/l2_banco_confronto.py 2025-26 --sims 30 --semi 8
PYTHONPATH=src python scripts/l2_inferenza_banco.py --verifica
```

Il terzo comando rifà l'inferenza dalle sole osservazioni conservate, senza
rigenerare: scarto massimo `0,00e+00`.

### Artefatti, con impronte

| sha256[:16] | file |
|---|---|
| `8c05747139050052` | `data/l2/banco_verdetto_2024-25.csv` |
| `8225b4d811ea0aa4` | `data/l2/banco_verdetto_2025-26.csv` |
| `e4d52aebeebab653` | `data/l2/banco_osservazioni_2024-25.parquet` |
| `96e72925fb5459d8` | `data/l2/banco_osservazioni_2025-26.parquet` |
| `6165d893f5739e8a` | `data/l2/banco_semi_2024-25.json` |
| `1f5f420600985ad0` | `data/l2/banco_semi_2025-26.json` |

**Provenienza incompleta**, dichiarata: sono stati scritti prima del contratto
delle esecuzioni e non portano un identificativo di esecuzione. Le impronte
identificano i byte, non certificano l'esperimento. Si chiuderebbe solo
rigenerandoli, che è un'esecuzione lunga e non autorizzata in questo ciclo.

---

## 3. Che cosa è cambiato il 9 settembre

Dettaglio in `reports/CICLO_20260909.md`. In breve:

- **verificatore**: 12 alterazioni che davano `RIPRODOTTO` ed exit 0 adesso
  falliscono. Prove scritte prima della correzione;
- **destinazioni**: ogni esecuzione ha la sua cartella, le prove hanno una
  radice separata, una destinazione occupata è rifiutata, la scrittura è
  atomica, il puntatore `corrente` si aggiorna solo dopo una verifica passata;
- **progressivo**: la prima origine viene davvero rigenerata (prima il
  controllo era una tautologia, e la correzione dichiarata nella sessione
  precedente non era mai stata scritta su disco); finestre per data effettiva;
  filtro del panel in un punto solo — ma il tempo entra anche da
  `costruisci_modello_partita` e `partite_di_addestramento`, e adesso e'
  dichiarato; campionamento proporzionale alle finestre; previsioni conservate;
- **affermazioni statistiche**: gli scenari sono incorrelati (verificato
  empiricamente), il rumore è ricampionabile, e c'è un emendamento prospettico
  sulla precisione computazionale che non tocca i verdetti pubblicati;
- **diagnosi delle presenze**: il bersaglio ha errore assoluto medio 0,1453
  contro l'osservato, il cubo lo porta a **0,1749**, mentre senza bersaglio sta
  a 0,2530. I tre numeri sono nel blocco `contro_osservato` di
  `presenze_diagnosi_2024-25.json`, marcato come **diagnostico**: usa la
  stagione valutata e non entra in nessun fit;
- **revisione indipendente**: 16 rilievi, tutti accolti — 11 corretti nel codice
  con 15 prove nuove, 5 nel testo. Elenco in `reports/CICLO_20260909.md`
  §Revisione.

---

## 3bis. Il pilota C2, e che cosa autorizza a dire

Il pilota risponde a una sola domanda: **spostare i parametri delle presenze
riduce la distanza fra le presenze simulate e un bersaglio costruito solo con
informazione anteriore al cutoff?** La risposta e' si', con margine ampio
rispetto all'errore delle differenze appaiate.

| contro | MAE C1 | MAE C2 | d medio | es(d) |
|---|---:|---:|---:|---:|
| bersaglio grezzo | 0,1729 | 0,1028 | **-0,07014** | 0,00203 |
| bersaglio obiettivo | 0,1733 | 0,1058 | **-0,06756** | 0,00206 |
| osservato (diagnostico) | 0,2693 | 0,2541 | **-0,01519** | 0,00121 |

Cinque semi di verifica, gli stessi per i due bracci, zero NaN. Il guadagno
contro l'osservato **non** e' una traslazione costante: la migliore traslazione
di C1 ne recupera solo `-0,00364` su `-0,01519`. Questo dice che *quella*
famiglia di spiegazioni non basta — non identifica una quota causale per
giocatore, perche' possono contribuire ruoli, struttura e la non linearita'
della MAE. Il «76 % per giocatore» del primo resoconto e' ritirato.

Invarianti fisici: zero problemi di coerenza in sei repliche. Le correlazioni
fra compagni restano entro un errore standard, il che **non** dimostra non
inferiorita': nessun margine di equivalenza e' stato dichiarato, e la media su
venti squadre diluisce un cambiamento che riguarda una sola squadra
calibrata.

**Non autorizza a promuovere.** Tre limiti, tutti misurati:

1. il bersaglio nasce da `b_predictions`, l'ingresso che i report stessi
   dichiarano **non databile**. Avvicinarsi al bersaglio non e' una prova
   indipendente di avvicinarsi alla realta';
2. **il confronto «il bersaglio grezzo e' piu' vicino al vero del cubo» era
   viziato**, e va ritirato: quel bersaglio aveva visto l'esito. Vedi §3ter.
   Con un bersaglio costruito senza le feature contaminate l'errore contro
   l'osservato sale da 0,1453 a 0,2136. Resta vero, e per altre ragioni, che
   il valore del cubo va cercato dove il cubo lavora — dipendenze, durata
   delle assenze, punteggi di rosa, decisioni — e non limando la MAE delle
   presenze;
3. il controfattuale temporale ha potenza su tre grandezze su cinque:
   `bersaglio` e `squadre` non si muovono nemmeno perturbando i ruoli
   anteriori. `scripts/l2_controfattuale_c2.py` lo dichiara da se'.

Il candidato e' congelato, `||theta||` 2,2777, monitoraggio 0,04664 -> 0,02738
in 200 iterazioni (5.484 s). Non e' stato scritto in nessun pack.

### Il difetto che cambia la lettura del piano

`calibra_guadagno` usava `A = 1` e `spsa` `A = massimo/10 = 20`: il primo passo
in theta non valeva lo 0,20 dichiarato nel piano congelato ma **0,0486**. Il
log lo mostra: `a = 40.80 (primo passo voluto 0.2)`.

Non e' un dettaglio. Con `A` reso coerente, `passo_voluto = 0,20` fa
**divergere** SPSA sulla funzione con ottimo noto e il candidato migliore resta
il punto di partenza. Le corse funzionavano *perche'* il passo effettivo era
quattro volte piu' piccolo. La costante e' ora `PASSO_VOLUTO = 0.05`, cioe' il
valore che il pilota applicava davvero: **la correzione allinea il codice a
quello che faceva, non sposta il punto di lavoro**, quindi i numeri qui sopra
restano validi. La frase del piano che diceva 0,20 no.

### Revisione indipendente: 19 rilievi, tutti accolti

Undici corretti nel codice, tre nei test (due dei quali passavano per il motivo
sbagliato), il resto nel testo. Elenco e ritrattazioni in
`reports/CICLO_20260909.md` §Revisione. Le tre che pesano di piu':

- «30 iterazioni -> 0,008428, `||theta||` 1,45» **non e' riproducibile**: con
  quella configurazione il candidato e' theta = 0 e la perdita resta 0,010000;
- la tabella «30/60/200/600 iterazioni» confrontava **quattro ottimizzatori**,
  non quattro budget, perche' `A` dipende da `massimo`;
- «con p ~ 30 servono circa duecento iterazioni» era un'**estrapolazione**: a
  `A` fisso la crescita non e' proporzionale a p (2,4x da p=10 a p=103, poi
  7,6x da p=103 a p=300).

---

## 3ter. Due feature del bersaglio contengono l'esito

Misurato il 9 settembre, riproducibile con
`scripts/l1_ablazione_presenze.py` e `scripts/l1_confronto_bersagli.py`.

Il bersaglio del cubo viene da un CatBoost su 36 feature ereditate in blocco
dal modello del prezzo. Due non sono disponibili alla data dell'asta:

- **`fvm`**: nei listoni archiviati e' un valore di **fine stagione**. Rho di
  rango con la quotazione di fine campionato 0,900 sul 2024-25, contro 0,708
  con quella iniziale; nel listone fresco 2026-27 le due coincidono (0,920 e
  0,941). Dato `fvm`, la quotazione iniziale non porta piu' informazione sulle
  presenze (parziale ~0,00); dato `qt_i`, `fvm` ne porta 0,65-0,67;
- **`quot_fs_sett`**: snapshot fanta.soccer di giornata 2 o 3 della stagione da
  predire. Per il 2024-25 e' la giornata 3, rilevata il 30/08/2024, contro la
  prima giornata del 17-19/08 e un cutoff dichiarato al 17/08.

Peso misurato, cinque semi, differenza appaiata:

| stagione | MAE con tutte | senza le non databili | differenza | es |
|---|---:|---:|---:|---:|
| 2024-25 | 5,5688 | 8,1259 | **+2,5571** | 0,0150 |
| 2025-26 | ~6,0 | ~8,3 | **+2,2890** | 0,0165 |

`fvm` da solo vale +1,78 presenze, `quot_fs_sett` +0,62; le altre due candidate
(`team_prev_xg`, `cambio_squadra`) sono rumore.

Contro le presenze realizzate, per giocatore-giornata: bersaglio attuale
**0,1453**, bersaglio per origine con le sole feature ammesse **0,2136**,
somme 264,6 e 280,4 contro le 281,9 vere. Il bersaglio onesto e' meno accurato
per giocatore e piu' corretto in aggregato.

**Anche il cubo eredita la contaminazione**: `partecipazione.stima` riceve lo
stesso bersaglio. Nessuno dei numeri pubblicati finora sul confronto
bersaglio/cubo e' pulito, e il confronto onesto non e' ancora stato fatto.

### Che cosa esiste adesso

- `src/fantabot/tabellino/origine.py` — contratto delle previsioni per origine:
  stagione, istante, universo, partite osservate e residue, periodo delle
  etichette, ingressi con la prova della loro disponibilita', impronte. Rifiuta
  un manifesto con ingressi posteriori all'origine, etichette oltre l'origine,
  o zero partite residue con orizzonte finto;
- `scripts/l1_presenze_per_origine.py` — produce le previsioni per origine,
  eseguendo il **solo** modello delle presenze. Due origini diverse danno due
  cartelle diverse che coesistono: nessun pack e' toccato;
- `partecipazione.stato_all_origine` e `generatore.genera(stato_iniziale=...)`
  — la catena di convocazione parte da dove le cose stanno, invece che da un
  sorteggio. Chi non ha storia resta ignoto ed e' ancora estratto; nessuna
  causa e' attribuita alle assenze.

**Limite dichiarato**: `votes_*.parquet` non ha date. La granularita' per le
presenze gia' realizzate e' la giornata, e le partite anticipate di una
giornata a cavallo sono scartate invece che indovinate.

---

## 4. Da dove ripartire, in ordine

1. **Rifare il confronto bersaglio/cubo con ingressi puliti.** E' il passo che
   scioglie il nodo: dare a `partecipazione.stima` il bersaglio per origine
   invece di `b_predictions`, e rimisurare C1 e C2. Finche' non e' fatto,
   nessuna delle due parti del confronto e' pulita. Costo: una corsa del
   pilota, circa 90 minuti.
2. **Decidere se ricostruire `fvm` in versione iniziale.** La fonte distingue
   `Qt.I` da `Qt.A`, ma per `fvm` non dichiara quale sia. Se esiste un
   archivio del listone al momento dell'asta, il ramo si riapre con una
   feature in piu'; se non esiste, `fvm` resta fuori. Non e' una decisione mia:
   riguarda quali dati vale la pena cercare.
3. **Implementare lo snapshot g01 per `quot_fs_sett`.** `PROTOCOLLO_v2.md`
   §9.3 lo aveva gia' deciso e non e' mai stato fatto: `fs_snapshot.json` punta
   a giornata 2 o 3. Con g01 la feature tornerebbe ammissibile, al costo di
   perdere copertura.
4. **Simulare solo il futuro.** Lo stato all'origine c'e'; `genera` continua a
   ciclare su tutto il calendario. Serve un orizzonte che parta dall'origine e
   conservi i risultati gia' acquisiti.
5. **L4 avanza per conto suo**, e non dipende dal cubo. Il nodo la' e' diverso:
   il target del modello prezzo si regge su 88 aste su 216, di cui **5** per il
   2024-25, e la stagione 2025-26 ha **zero** prezzi osservati. Prima di
   modelli nuovi serve sapere se quel campione basta.
6. **L3 resta fermo su un difetto noto**: i tetti non hanno mai funzionato
   end-to-end (0 usabili su 25 nell'unico file su disco) e il disegno li
   calcola da un solo stato iniziale, cosi' che il bot li respinga dopo il
   primo martelletto. I difetti 1-3 sono stati corretti l'8 settembre, ma
   nessun esperimento e' stato rigiocato: i numeri L3 pubblicati vengono
   ancora dal bot difettoso.

### Comandi che riprendono da qui

```bash
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTHONIOENCODING=utf-8 PYTHONPATH=src python -m pytest tests/ -q
```

```bash
PYTHONPATH=src python scripts/l1_ablazione_presenze.py 2024-25 --per-feature
```

```bash
PYTHONPATH=src python scripts/l1_presenze_per_origine.py 2024-25 --origine 2024-10-01
```

```bash
PYTHONPATH=src python scripts/l1_confronto_bersagli.py
```

### Prove piccole, per ricominciare senza impegnarsi

```bash
PYTHONPATH=src python scripts/l2_controfattuale_c2.py 2024-25
PYTHONPATH=src python scripts/l2_pilota_c2.py 2024-25 --iterazioni 3 --sims 2
```

Entrambe scrivono sotto `data/l2/prove/`, che e' una radice separata da quella
dei risultati: non possono toccare niente di pubblicato.

---

## 5. Che cosa NON è vero, e va detto

- **«Non c'è differenza» non è «sono equivalenti».** Nessun margine di
  equivalenza è stato dichiarato, e non è mio da dichiarare.
- **La diagnosi delle presenze non dimostra da sola perché `C1` perda.** Mostra
  un meccanismo misurato e coerente; non ha isolato il contributo delle altre
  componenti.
- **Il refit a origini mobili non è una previsione progressiva operativa**:
  è un confronto fra due refit incondizionati, e i bracci si chiamano così.
- **Il ciclo del 9 settembre non ha prodotto nessun risultato nuovo sul
  merito**: ha corretto strumenti e misurato un meccanismo. Il verdetto del
  banco è quello di R4, invariato.
- **Il puntatore `corrente` esiste ma non è collegato**: nessuno script chiama
  `promuovi_a_corrente`, e sul disco non ci sono né `data/l2/corrente` né
  `data/l2/esecuzioni`. Gli artefatti correnti stanno ancora ai nomi piatti.
- **Il controllo della prima finestra, sul percorso reale, è un test di
  determinismo del generatore**, non del contratto temporale: confronta
  `genera(X, s)` con `genera(X, s)`. La prova che può fallire usa un generatore
  alterato, ed è a un livello più debole.
- **Il pilota C2 non dimostra che il cubo migliori le presenze rispetto alla
  realta'**: dimostra che si avvicina a un bersaglio che e' gia' piu' vicino
  alla realta' di lui, e che nasce da un ingresso non databile.
- **«Il primo passo vale 0,20»**: falso, valeva 0,0486. Il piano congelato lo
  dichiarava male, e l'errore e' stato scoperto solo dalla revisione.
- **«La varianza e' dominata dal seme»**: ritirata gia' nel ciclo precedente,
  non e' mai stata dimostrata. La causa misurata del pilota fallito e' il
  **budget**, non il rumore.
- **«Il bersaglio grezzo e' piu' accurato del cubo»**: ritirata. Lo era perche'
  aveva visto l'esito. E il cubo eredita lo stesso ingresso, quindi neanche il
  suo numero e' pulito.
- **Il produttore per origine non risolve la temporalita' del progetto**:
  copre il modello delle presenze. `players_*.parquet` non ha un contratto
  temporale, e le 32 feature ammesse lo sono per semantica del campo, non per
  prova di data.
- **Lo stato all'origine non e' una previsione operativa**: il generatore
  continua a risimulare tutto il calendario. E' un ingresso pronto, non un
  percorso completo.
