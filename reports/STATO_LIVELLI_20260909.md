# Stato dei cinque livelli — 9 settembre 2026

Cinque colonne, non una percentuale. Ogni casella dice **come si sa**.

- **implementato**: il codice esiste ed esegue;
- **verificato**: esistono prove che falliscono se il codice si rompe;
- **validato**: il risultato regge a un confronto con criteri fissati prima;
- **collegato**: un consumatore reale lo usa;
- **operativo**: è quello che gira quando si prende una decisione vera.

| livello | implementato | verificato | validato | collegato | operativo |
|---|---|---|---|---|---|
| **1 — dati e banco** | sì | sì, 562 prove | **parziale** | sì | sì |
| **2 — cubo TABELLINO** | sì | sì | **no** | no | no |
| **3 — P(1°) e tetti** | sì | sì, 165 prove L3 | **no** | no | no |
| **4 — prezzi** | parziale | **no**, zero prove | **no** | sì (il pack legge i prezzi) | sì |
| **5 — stagione in corso** | **no** | — | — | — | no |

## Livello 1 — dati e banco

**Implementato e collegato.** Il panel ha un contratto temporale con
`as_of_decisione`, e le prove lo sorvegliano.

**Validato solo in parte, e il buco è nuovo.** Il contratto temporale copre
`l2_panel_*`; **non** copre `players_*.parquet`, da cui vengono le feature dei
modelli. Due di quelle feature contengono l'esito della stagione da predire
(§Quinto ciclo di `CICLO_20260909.md`): `fvm` e `quot_fs_sett`.

**Novità di oggi**: `src/fantabot/tabellino/origine.py` e
`scripts/l1_presenze_per_origine.py` producono previsioni per origine con
manifesto verificabile. Non sostituiscono ancora `b_predictions`.

**Il prossimo passo**: dare il bersaglio per origine in ingresso a
`partecipazione.stima` e rifare il confronto.

## Livello 2 — cubo TABELLINO

**Implementato e verificato.** Il pilota C2 gira, il controfattuale temporale
esercita il produttore vero e passa, la verifica del candidato controlla che
gli ingressi coincidano prima di applicare `theta`.

**Non validato.** Il candidato migliora le metriche conservate — differenze
appaiate a molte decine di errori standard — ma su **30 giocatori di una
squadra, una stagione**, e verso un bersaglio che eredita informazione
posteriore al cutoff. Il vantaggio va misurato dove il cubo lavora: dipendenze,
durata delle assenze, punteggi di rosa, decisioni d'asta.

**Non collegato, non operativo**: `theta` non è in nessun pack, e nessun
consumatore lo legge.

## Livello 3 — P(1°) e tetti

**Implementato e verificato** come codice: 165 prove passano, e tre dei quattro
difetti dichiarati sono stati corretti l'8 settembre (piano sovrascritto dal
replan, pavimento di spesa, contatori dei target persi).

**Non validato, e il motivo è preciso.** Il quarto difetto è ancora vero: dei
25 tetti nell'unico file su disco, **zero sono usabili**, e il disegno li
calcola tutti da un solo stato iniziale, così che il bot li respinga dopo il
primo martelletto. E nessun esperimento è stato rigiocato dopo le correzioni:
i numeri L3 pubblicati vengono dal bot difettoso.

`P(1°)` è calcolata con calendario, fasce gol e classifica: il nome è
appropriato. Ma il bot d'asta massimizza `value`, non `P(1°)`.

## Livello 4 — prezzi

**Collegato e operativo** — è quello che gira oggi — ma **non verificato**:
zero prove automatiche su tutto il livello.

**Il nodo non è il cubo**, ed è il motivo per cui questo livello non va
sospeso insieme a L2. È il campione:

- 216 aste reali, ma il target che il modello usa poggia su **88**, di cui
  **5** per il 2024-25;
- copertura 2024-25: 255 giocatori su 679 con la soglia usata dal modello;
- copertura **2025-26: zero**, in tutti e tre i canali;
- nessuna delle 216 aste chiude a budget esatto; 22 sopra il budget;
- la semantica di `modificatore` è ignota (cinque codici, 27 aste senza
  valore); quella di `periodo` **è documentata** in
  `data/raw/gruppoesperti/REPORT.md:18` — `0` è l'asta estiva, i valori più
  alti sono più a ridosso o dopo l'inizio del campionato;
- nessun ordine dei lotti, nessuna marca temporale nel file consumato: un
  replay storico non è ricostruibile da lì, e fingerlo sarebbe inventare dati.
  Esistono però fogli grezzi per squadra in `data/raw/gruppoesperti/extra/`,
  con una colonna per partecipante: i proprietari dei lotti ci sono, non sono
  stati portati nel tidy. E lì risultano anche aste 2022-23, che il tidy non
  contiene. Prima di dichiarare un dato assente conviene guardare i fogli non
  parsati.

Mondrian esiste solo sul valore, ACI solo su dati sintetici.

## Livello 5 — stagione in corso

**Non implementato come percorso operativo.** Esiste l'aggiornamento dei dati;
scambi, svincoli e riparazione sono zero righe di codice, e `league.yaml`
dichiara `repair_auction: false`.

**Passo fatto oggi**: `generatore.genera` accetta uno `stato_iniziale`, e
`partecipazione.stato_all_origine` lo ricava dalle sole righe anteriori.
Il generatore continua però a ciclare su tutto il calendario: simulare **solo**
il futuro è il pezzo che manca.

## Interfaccia

`scripts/f10_copilot.py:342` legge `data/packs/pack_{season}.pkl`. Il pack non
ha versione, non ha manifesto, non ha validazione: i consumatori usano
`getattr` con valori di riserva. Acquisto, undo, ricalcolo e ripresa esistono,
ma **solo per l'asta**.

Un motore approvato non diventa operativo perché esiste su disco: serve un
contratto versionato fra artefatto, contesto di lega, stato d'asta e motore.

## Che cosa non è vero, e va detto

- **Nessun livello è «finito»**. L1 è il più avanzato e ha appena rivelato una
  fuga temporale nelle feature.
- **Il 99 % contro i bot attuali** segnala un effetto soffitto, non superiorità
  contro persone competenti.
- **Il cubo non è dimostrato inutile**: è dimostrato non ancora utile *dove è
  stato misurato*. Marginale e distribuzione congiunta sono oggetti diversi.
- **Nessuna stima di giorni o percentuali di completamento**: non ci sono
  dati per farla.
