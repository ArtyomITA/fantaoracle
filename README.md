# 🔮 FantaOracle

**Il sistema che fa l'asta del fantacalcio al posto tuo — e ti dimostra perché funziona.**

Predice quanto costerà ogni giocatore con una forchetta d'incertezza, costruisce la rosa ottima col tuo budget, ricalcola tutto a ogni martelletto, e poi rigioca stagioni intere coi voti veri per misurare quanto vale davvero.

*In sviluppo attivo: il Livello 3 e la valutazione a origini mobili sono in corso.*

---

## Perché è un problema difficile

Un'asta di fantacalcio sembra un problema di ottimizzazione. Non lo è.

I prezzi non sono dati: si formano mentre giochi, contro nove persone che hanno le loro idee. Il budget è un vincolo duro e irreversibile — un rilancio di troppo al terzo giocatore ti toglie il centrocampo. E l'obiettivo non è «massimizzare i punti attesi»: è **arrivare primo in un campionato a scontri diretti**, dove le fasce gol trasformano 66 punti in un gol e 71 in due, e dove una rosa più forte in media può vincere meno spesso di una più esplosiva.

FantaOracle affronta tutti e tre i pezzi.

## Che cosa fa

**Predice i prezzi.** Ensemble TabPFN-2 + CatBoost addestrato su **225 aste reali** crowdsourced e sugli storici delle piattaforme dal 2018. Non un numero: q10/q50/q90 con *conformalized quantile regression* — i quantili grezzi si allargano su un insieme di calibrazione tenuto fuori dall'addestramento, con una guardia contro l'incrocio dei quantili. Sapere che un giocatore «costa 40» è inutile se la forchetta vera è 25-70.

**Predice i punti.** CatBoost sui punti di stagione. Questo è il motore del vantaggio, ed è misurato: correlazione **0,83-0,85** con i punti realmente fatti, contro **0,48-0,57** del prezzo di mercato. Il controfattuale lo conferma — lo stesso bot, con il valore di mercato al posto del suo, crolla sotto il caso.

**Costruisce la rosa.** Programmazione lineare intera a due livelli (titolari e panchina) con modulo libero, prezzo-ombra sui ruoli, risolta con PuLP; e ripianificazione completa a ogni martelletto: quando perdi un obiettivo, il piano si riscrive prima della chiamata successiva.

**Simula il mondo, non un modello del mondo.** Un generatore di stagioni che parte dal risultato della partita — Poisson bivariata con la correzione di **Dixon-Coles**, prior sugli xG di Understat, decadimento temporale esponenziale dei pesi — decide chi scende in campo e per quanti minuti, distribuisce gol, assist e cartellini rispettando chi era davvero in campo in quel minuto, e solo alla fine calcola il voto. Undici in campo, un portiere sempre, espulsi che non vengono sostituiti, sostituzioni che seguono le regole.

**Si mette alla prova.** Aste complete contro avversari che si comportano come persone — otto profili calibrati su aste vere: il tifoso, il panic buyer, il tirchio, chi si fissa su un nome. Poi la stagione rigiocata coi fantavoti reali, formazioni, cambi, modificatore di difesa, campionato H2H su cento calendari.

### Sotto il cofano

Qualche pezzo che vale la pena nominare, perché è dove stanno le decisioni non ovvie.

**Il risultato della partita.** La correzione di Dixon-Coles moltiplica le celle basse della Poisson bivariata — 0-0, 1-0, 0-1, 1-1 — per un fattore `τ` che dipende da un solo parametro `ρ`. `ρ` non è libero: `τ` deve restare positivo su tutte e quattro le celle, e l'intervallo ammissibile dipende dalle intensità di *quella* partita. Quando lo scenario ne estrae uno fuori intervallo, il valore viene **proiettato** sull'intervallo e il fatto viene contato, invece di ritagliare le probabilità negative a zero e rinormalizzare — che sposterebbe le marginali senza dirlo. Il supporto della matrice dei risultati è adattivo, non un massimo fisso: con intensità alte un tetto a dodici gol lascia fuori una massa che non è trascurabile.

**Chi viene convocato.** Una catena di Markov a due stati per giocatore, con memoria: chi è stato convocato tende a esserlo di nuovo. Una catena con memoria **non conserva** il tasso medio che le si dà in ingresso — passa più tempo negli stati in cui entra più spesso — quindi il logit di base viene calcolato invertendo numericamente la catena, in modo che la sua **distribuzione stazionaria** dia esattamente la propensione voluta.

**La dipendenza fra compagni.** Un solo shock di squadra imporrebbe la stessa correlazione fra tutte le coppie di ruoli, e i dati dicono altro: fra difensori la correlazione è circa il triplo di quella fra portiere e difensori. Il residuo del voto si scompone in shock di squadra, shock di reparto ed errore individuale, e i tre pesi si calibrano sulle correlazioni osservate nei dati ammessi al fit.

**Le regole della lega sono fuori dal modello.** Il fantavoto della fonte non contiene il bonus della porta inviolata, che dipende da quanti gol ha subito il portiere *mentre era in porta*: il generatore conserva quel conteggio per giocatore, così il punteggio di lega si calcola a valle invece di essere perso.

## I numeri

| | |
|---|---|
| Correlazione del modello valore coi punti veri | **0,83-0,85** (mercato: 0,48-0,57) |
| Vittorie nei tornei simulati, 150 repliche | **75-91 %** (caso puro: 10 %) |
| Errore sulle presenze del generatore, aggregato di squadra | **0,4-0,7 %** |
| Errore sulle presenze, giocatore per giocatore | **0,175** di probabilità |
| Test automatici | **491** |

I tornei sono contro i nostri bot: è il banco su cui il sistema è stato costruito, e contro persone vere ci si aspetta meno. Ogni numero qui sopra è riproducibile con un comando, e il comando sta nel report che lo contiene.

Le due righe sulle presenze misurano cose diverse, e la distanza fra loro è il genere di cosa che questo progetto tiene d'occhio: il generatore azzecca quante persone giocano in una squadra, e sbaglia molto più spesso **quali**.

## Come si misura

Un simulatore che si giudica da solo dice sempre di funzionare. La parte meno visibile del progetto è l'impianto che serve a non farlo.

**Tre viste del tempo, tenute separate.** Ogni riga di dati esiste in tre versioni: quella *osservativa*, che sa tutto quello che sappiamo oggi; quella *al fit*, che vede solo le prove esistenti al giorno dell'addestramento; quella *alla decisione*, che vede solo quello che si sapeva al momento della scelta. Il cutoff è nel nome del file e nei metadati accanto, e chi legge un panel dichiara quale vista gli serve: se gliene passi un'altra, si rifiuta invece di lavorare sui dati sbagliati.

Il criterio è la **data dell'evento**, non il numero di giornata. Un recupero giocato a febbraio appartiene alla nona giornata ma a novembre non esisteva ancora, e chi decide a novembre non può vederlo.

**Il confronto è fattoriale.** Chiedersi «il generatore nuovo è meglio del vecchio» non è una domanda ben posta se i due ricevono informazioni diverse. Il banco confronta quattro bracci — due meccanismi × due livelli di informazione sulle presenze — così il contributo del meccanismo si separa da quello dell'informazione, e l'interazione fra i due si misura invece di restare implicita.

**Gli intervalli tengono conto delle dipendenze.** Le righe della stessa partita condividono il risultato, quelle dello stesso giocatore condividono la storia, e le due dimensioni **si incrociano** invece di essere annidate: trattarle come indipendenti dà intervalli da due a quattro volte troppo stretti. La varianza è *two-way cluster-robust* nella forma di Cameron e Miller — `V = V_partita + V_giocatore − V_intersezione`, dove l'intersezione è la singola riga, cioè proprio la varianza che il metodo ingenuo calcolava — con valori critici di Student sui gradi di libertà della dimensione con meno grappoli. Accanto a ogni stima si pubblica anche l'errore standard del metodo ingenuo, così si vede quanto la dipendenza pesava.

**Le metriche sono quelle giuste per una previsione probabilistica.** CRPS sul punteggio del giocatore-giornata, punteggio di Brier sulla presenza a voto, PIT randomizzato per gli esiti discreti — senza la randomizzazione l'istogramma sembra deforme anche con un modello perfetto.

**Il rumore di simulazione si misura, non si spera.** Ogni confronto gira con più semi di scenario, e l'errore Monte Carlo compare accanto all'intervallo: senza, un intervallo stretto e una differenza vera hanno lo stesso aspetto. I punteggi vengono riportati sia nella forma empirica sia in quella *equa* di Ferro, che toglie la penalizzazione che un ensemble di dimensione finita subisce solo per essere finito. La correzione è la dispersione di ensemble divisa per `m − 1`, e **non si cancella nelle differenze**: dipende dall'ensemble, quindi si annulla solo se i due bracci hanno la stessa dispersione. Per questo la dispersione media per braccio è una colonna pubblicata.

**I risultati per osservazione restano su disco**, con l'identità di giocatore, partita e data. Serve a rifare un'inferenza a cui non si era pensato prima senza rigenerare niente: l'interazione del fattoriale è nata così, e si ricalcola in secondi invece che in mezz'ora.

## Come è fatto

```
  DATI                          MODELLI                      DECISIONE
  ────                          ───────                      ─────────
  aste reali (225)              prezzo: TabPFN-2 +           MILP titolari + panchina
  quotazioni 2018-2026          CatBoost, quantili           con prezzo-ombra
  voti, 5 stagioni              conformali                   e ripianificazione a
  xG Understat                                               ogni martelletto
  formazioni ed eventi          valore: CatBoost sui                 │
  Transfermarkt                 punti di stagione                    ▼
        │                              │                     MOTORE D'ASTA
        └──────────────┬───────────────┘                     chiamata a giro,
                       ▼                                     rilanci, vincoli,
              GENERATORE DI STAGIONI                         registro con i
              risultato della partita,                       «pensieri» dei bot
              partecipazione, eventi,                                │
              voto puro, punteggio                                   ▼
                       │                                     STAGIONE E CAMPIONATO
                       └─────────────────────────────────────  formazioni, cambi,
                                                                modificatore, H2H
```

Quattro livelli, uno sopra l'altro:

| livello | che cosa aggiunge |
|---|---|
| **0-1** | dati, modelli di prezzo e valore, motore d'asta, bot, torneo |
| **2** | generatore di stagioni fisicamente coerente — chi gioca, chi segna, chi prende voto |
| **3** | scelta della rosa che massimizza la probabilità di **arrivare primo**, e prezzo di indifferenza per ogni giocatore |
| **4** | prezzi dalle aste reali: identità di ogni asta, duplicati, e la distinzione fra il prezzo di un singolo martelletto e il prezzo medio fra aste |

Il Livello 3 è la parte in costruzione: risponde alla domanda «fino a che prezzo mi conviene questo giocatore, considerando che comprarlo mi toglie i crediti per gli altri».

Il Livello 2 non è promosso, e la ragione è misurata. A parità di informazione sulle presenze il generatore di stagioni **perde** contro un simulatore molto più semplice, per giocatore: l'informazione sulle presenze pesa tre volte tanto il meccanismo che le usa, e l'interazione fra i due fattori dice che il generatore ne trae *meno*. Il generatore resta perché fa una cosa che l'altro non fa — scenari congiunti coerenti, dipendenze fra compagni, sostituzioni, distribuzione dei punti di una rosa intera — ma quella cosa va misurata con metriche congiunte, non con un punteggio marginale su ogni giocatore preso da solo, e quella misura non c'è ancora.

Il candidato che dovrebbe chiudere il divario è una calibrazione congiunta del generatore verso bersagli di presenza compatibili con i suoi vincoli, cercata con **SPSA** — due sole valutazioni per iterazione qualunque sia il numero di parametri, che con un obiettivo simulato e costoso è la differenza fra fattibile e no. Il primo pilota è inconcludente per una ragione misurata: la varianza dell'obiettivo è dominata dal seme e non dal numero di scenari, quindi il gradiente stimato è rumore. Il seguito sta in [`RIPRESA.md`](RIPRESA.md).

## Provalo

La demo funziona senza i dati originali (esclusi perché scaricati da fonti terze — vedi [`DATA.md`](DATA.md)):

```bash
pip install -r requirements.txt
python scripts/fantaoracle_app.py
```

Tre modi per guardarlo lavorare:

- **Replay** — un'asta simulata come un teatro, con i pensieri di ogni bot a ogni rilancio: perché ha rilanciato, quanto era disposto a pagare, cosa ha ricalcolato dopo averlo perso.
- **Sedia** — ti siedi tu al tavolo, contro i bot.
- **Copilota** — l'assistente per l'asta vera: consiglio a ogni chiamata, piano aggiornato, budget residuo, tetto massimo per giocatore.

## Come è tenuto insieme

Tre regole di metodo, applicate anche quando fanno perdere tempo. Sono la ragione per cui i numeri qui sopra si possono citare:

1. **Prima la causa riprodotta, poi la correzione, poi la misura.** Un test che fallisce non si risolve indebolendo il test.
2. **I criteri si scrivono prima dell'esperimento.** Una soglia non si sposta dopo aver visto i risultati.
3. **Un esito inconcludente resta inconcludente.** Non diventa equivalenza, e non diventa una promozione.

Ogni conclusione nei report porta il suo stato e il comando che la riproduce. Quando una verifica successiva ne ribalta una, la correzione viene scritta accanto all'originale invece di riscrivere la storia: [`reports/PROTOCOLLO_v2.md`](reports/PROTOCOLLO_v2.md).

Perché queste regole reggano servono due contratti scritti nel codice, non nelle intenzioni.

**Ogni esecuzione ha la sua cartella.** Nome, istante, identificativo, e dentro un manifesto con la configurazione, i semi, gli scenari e le impronte di tutto quello che è entrato — i dati letti e anche i moduli che li hanno interpretati, perché due esecuzioni con lo stesso script e un generatore diverso non sono la stessa esecuzione. Le prove esplorative scrivono sotto una radice separata dai risultati, una destinazione occupata viene rifiutata invece di sovrascritta, e il riferimento «corrente» si sposta solo dopo una verifica passata.

**Un artefatto si verifica rileggendolo.** Il verificatore ricostruisce i risultati dai dati conservati e li confronta con quelli pubblicati, e pretende schema completo, chiavi coincidenti, stessa cardinalità, stessi metadati e almeno un confronto effettivamente fatto. Un valore legittimamente non stimabile è ammesso; confonderlo con un valore perso no. Se un ingresso, un output, un seme o un identificativo non sono più quelli dichiarati, la verifica fallisce e lo dice.

Per gli artefatti più vecchi di questi contratti la risposta onesta è «provenienza incompleta», e il verificatore la stampa: un'impronta calcolata oggi identifica dei byte, non certifica l'esperimento che li ha prodotti.

## Struttura

```
src/fantabot/
  engine/      motore d'asta a eventi, con registro JSONL
  bots/        A (baseline), B (il nostro), C (otto profili umani)
  season/      formazioni, sostituzioni, punteggio di lega, campionato H2H
  tabellino/   generatore di stagioni: partita, partecipazione, eventi, voto
               contratto (viste temporali), presenze, inferenza, esecuzione
  livello3/    valutatore, ricerca su candidate, MILP esatto, indifferenza
scripts/       pipeline dei dati, banchi, esperimenti
tests/         491 test
reports/       ogni conclusione con la sua prova
viz/           replay, Sedia, Copilota
```

## Licenza e dati

Codice sotto licenza MIT. I dati grezzi non sono ridistribuiti: si scaricano da fonti terze e si rigenerano in locale con gli script della pipeline. Provenienza e dettagli in [`DATA.md`](DATA.md).

Progetto personale, costruito per una lega di amici.
