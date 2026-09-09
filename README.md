# 🔮 FantaOracle

**Il sistema che fa l'asta del fantacalcio al posto tuo — e ti dimostra perché funziona.**

Predice quanto costerà ogni giocatore con una forchetta d'incertezza, costruisce la rosa ottima col tuo budget, ricalcola tutto a ogni martelletto, e poi rigioca stagioni intere coi voti veri per misurare quanto vale davvero.

*In sviluppo attivo: il Livello 3 e la valutazione a origini mobili sono in corso.*

---

## Perché è difficile

Un'asta di fantacalcio sembra un problema di ottimizzazione. Non lo è. I prezzi si formano mentre giochi, contro nove persone. Il budget è un vincolo duro e irreversibile. E l'obiettivo non è massimizzare i punti attesi: è **arrivare primo in un campionato H2H**, dove le fasce gol trasformano 66 punti in un gol e 71 in due, e una rosa più forte in media può vincere meno spesso di una più esplosiva.

## Che cosa fa

| | |
|---|---|
| **Prezzi** | ensemble TabPFN-2 + CatBoost su **216 aste reali** e storici dal 2018. Non un numero: q10/q50/q90 con *conformalized quantile regression*, calibrata fuori campione, con guardia contro l'incrocio dei quantili |
| **Valore** | CatBoost sui punti di stagione. Correlazione **0,83-0,85** coi punti veri contro **0,48-0,57** del prezzo di mercato — e il controfattuale conferma: lo stesso bot col valore di mercato crolla sotto il caso |
| **Rosa** | programmazione lineare intera a due livelli (titolari, panchina), modulo libero, prezzo-ombra sui ruoli, PuLP. Ripianificazione completa a ogni martelletto |
| **Mondo** | generatore di stagioni: risultato → partecipazione → eventi → voto puro → punteggio di lega |
| **Banco** | otto profili d'asta calibrati su aste vere, stagione rigiocata coi fantavoti reali, modificatore di difesa, campionato H2H su cento calendari |

### Sotto il cofano

| pezzo | come è fatto |
|---|---|
| risultato della partita | Poisson bivariata con correzione **Dixon-Coles**, prior sugli **xG** Understat, decadimento esponenziale dei pesi (`ξ`) |
| il parametro `ρ` | non è libero: `τ` deve restare positivo sulle quattro celle basse, e l'intervallo dipende dalle intensità di *quella* partita. Fuori intervallo si **proietta** e si conta, invece di ritagliare a zero e rinormalizzare — che sposterebbe le marginali in silenzio |
| supporto della matrice | adattivo, non un tetto fisso: a intensità alte un massimo di dodici gol lascia fuori massa non trascurabile |
| convocazione | catena di Markov a due stati con memoria. Una catena con memoria non conserva il tasso in ingresso, quindi il logit di base si ottiene invertendola perché la **distribuzione stazionaria** dia la propensione voluta |
| stato iniziale della catena | a stagione iniziata non si sorteggia: stato e striscia in corso si leggono dalle sole righe anteriori all'origine, con la stessa definizione usata per stimare gli scostamenti. Chi non ha storia resta **ignoto** ed è ancora estratto — l'incertezza si conserva invece di essere sostituita da un valore inventato |
| dipendenza fra compagni | scomposizione shock di squadra + shock di reparto + errore individuale: uno shock unico imporrebbe la stessa correlazione fra tutte le coppie di ruoli, e fra difensori è il triplo che fra portiere e difensori |
| punteggio di lega | il fantavoto della fonte non contiene la porta inviolata: il generatore conserva i gol subiti dal portiere **mentre era in porta**, così il bonus si calcola a valle invece di perdersi |

## I numeri

| | |
|---|---|
| Correlazione del modello valore coi punti veri | **0,83-0,85** (mercato: 0,48-0,57) |
| Vittorie nei tornei simulati, 150 repliche | **75-91 %** (caso puro: 10 %) |
| Errore sulle presenze, aggregato di squadra | **0,4-0,7 %** |
| Errore sulle presenze, giocatore per giocatore | **0,175** di probabilità |
| Costo della disciplina temporale sulle presenze | **+2,56** presenze di errore assoluto medio |
| Test automatici | **562** |

I tornei sono contro i nostri bot: è il banco su cui il sistema è stato costruito, e contro persone vere ci si aspetta meno. Le prime due righe sulle presenze misurano cose diverse, e la distanza fra loro è il punto: il generatore azzecca **quanti** giocano, sbaglia molto più spesso **quali**.

La terza è il prezzo della disciplina temporale, e non è piccolo. Togliendo dal modello delle presenze le feature la cui disponibilità alla data dell'asta non è dimostrata, l'errore passa da 5,57 a 8,13 presenze. Due sole ne portano quasi tutto: una quotazione che nei listoni archiviati è di **fine** stagione, e un'istantanea settimanale rilevata dopo la prima giornata. Un modello che le usa sembra più bravo di quanto sarà il giorno dell'asta.

Ogni numero è riproducibile, e il comando sta nel report che lo contiene.

## Come si misura

Un simulatore che si giudica da solo dice sempre di funzionare.

| | |
|---|---|
| **tre viste del tempo** | *osservativa*, *al fit*, *alla decisione*. Il cutoff sta nel nome del file e nei metadati; chi legge dichiara quale vista gli serve e le altre vengono rifiutate |
| **origini mobili** | ogni previsione dichiara il proprio istante e vive in un artefatto separato: stagione, universo, partite osservate e residue, periodo delle etichette, impronte. Un file per stagione che si sovrascrive non è una previsione datata, è l'ultima che è passata di lì (*time series cross-validation*, Hyndman e Athanasopoulos) |
| **ogni feature porta la prova** | non basta che un valore esista prima dell'asta: bisogna sapere *come lo si sa*. Ogni ingresso è marcato «disponibile alla decisione» — con la prova —, «ricostruito a posteriori» o «non verificabile», e chi non ha prova non entra in una previsione operativa. Rigenerare un file oggi non retrodata quello che contiene |
| **data, non giornata** | un recupero giocato a febbraio appartiene alla nona giornata, ma a novembre non esisteva |
| **disegno fattoriale** | quattro bracci, due meccanismi × due livelli di informazione sulle presenze, più l'**interazione**: senza, il contributo del meccanismo e quello dell'informazione restano confusi |
| **intervalli** | varianza *two-way cluster-robust* di Cameron e Miller, `V = V_partita + V_giocatore − V_intersezione`, con l'intersezione uguale alla singola riga — cioè proprio quello che il metodo ingenuo calcolava. Ignorare la dipendenza dava intervalli 2-4 volte troppo stretti |
| **metriche** | CRPS sul punteggio, Brier sulla presenza a voto, PIT **randomizzato** per gli esiti discreti |
| **punteggi equi** | correzione di Ferro, `dispersione/(m−1)`: toglie la penalizzazione che un ensemble subisce per essere finito. Non si cancella nelle differenze, quindi la dispersione media per braccio è una colonna pubblicata |
| **rumore Monte Carlo** | misurato con semi ripetuti e stampato accanto all'intervallo: senza, un intervallo stretto e una differenza vera hanno lo stesso aspetto |
| **osservazioni conservate** | per riga, con identità di giocatore, partita e data: un'inferenza non prevista si rifà in secondi invece che in mezz'ora |

## Come è fatto

```
  DATI                          MODELLI                      DECISIONE
  ────                          ───────                      ─────────
  aste reali (216)              prezzo: TabPFN-2 +           MILP titolari + panchina
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

| livello | che cosa aggiunge | stato |
|---|---|---|
| **0-1** | dati, modelli di prezzo e valore, motore d'asta, bot, torneo | in uso |
| **2** | generatore di stagioni fisicamente coerente | **non promosso** |
| **3** | rosa che massimizza P(primo posto), prezzo di indifferenza per giocatore | in costruzione |
| **4** | prezzi dalle aste reali: identità di ogni asta, duplicati, martelletto singolo contro prezzo medio | in corso |
| **5** | stagione in corso: stato aggiornato all'origine, scambi, svincoli, riparazione di gennaio | da costruire |

Il Livello 3 risponde alla domanda «fino a che prezzo mi conviene questo giocatore, sapendo che comprarlo mi toglie i crediti per gli altri».

Il Livello 2 non è promosso. A parità di informazione sulle presenze il generatore **perde** contro un simulatore per giocatore molto più semplice, e l'interazione del fattoriale dice che ne trae *meno*. Resta perché fa quello che l'altro non fa — scenari congiunti, dipendenze fra compagni, sostituzioni, distribuzione dei punti di una rosa intera — e proprio lì va misurato: con metriche multivariate sensibili alla struttura congiunta (*variogram score*, Scheuerer e Hamill), non con un punteggio marginale su un giocatore alla volta.

Il candidato per chiudere il divario è una calibrazione congiunta verso bersagli compatibili, cercata con **SPSA** (Spall): due valutazioni per iterazione a qualunque dimensione, perturbazione **Bernoulli ±1**, guadagni `a_k = a/(A+k)^0,602` e `c_k = c/k^0,101`, col guadagno tarato perché il primo passo valga quello che dichiara. Il candidato esiste e migliora le sue metriche di molte decine di errori standard — ma su trenta giocatori di una squadra, e verso un bersaglio che eredita informazione posteriore al cutoff. Prima di chiedersi se il cubo serve, va rifatto il confronto con ingressi puliti. Seguito in [`RIPRESA.md`](RIPRESA.md).

## Provalo

La demo funziona senza i dati originali (esclusi perché scaricati da fonti terze — vedi [`DATA.md`](DATA.md)):

```bash
pip install -r requirements.txt
python scripts/fantaoracle_app.py
```

- **Replay** — un'asta come un teatro, coi pensieri di ogni bot a ogni rilancio: perché ha rilanciato, quanto era disposto a pagare, cosa ha ricalcolato dopo aver perso.
- **Sedia** — ti siedi tu al tavolo, contro i bot.
- **Copilota** — l'assistente per l'asta vera: consiglio a ogni chiamata, piano aggiornato, budget residuo, tetto per giocatore.

## Come è tenuto insieme

Tre regole di metodo, applicate anche quando fanno perdere tempo:

1. **Prima la causa riprodotta, poi la correzione, poi la misura.** Un test che fallisce non si risolve indebolendo il test.
2. **I criteri si scrivono prima dell'esperimento.** Una soglia non si sposta dopo aver visto i risultati.
3. **Un esito inconcludente resta inconcludente.** Non diventa equivalenza, e non diventa una promozione.

Quando una verifica ribalta una conclusione, la correzione va scritta accanto all'originale invece di riscrivere la storia: [`reports/PROTOCOLLO_v2.md`](reports/PROTOCOLLO_v2.md).

Due contratti fanno reggere le regole:

**Ogni esecuzione ha la sua cartella**, con un manifesto che porta configurazione, semi, scenari e impronte degli ingressi — dati **e moduli**, perché due esecuzioni con lo stesso script e un generatore diverso non sono la stessa esecuzione. Le prove esplorative scrivono sotto una radice separata, una destinazione occupata viene rifiutata, e il riferimento «corrente» si sposta solo dopo una verifica passata.

**Un artefatto si verifica rileggendolo.** Il verificatore ricostruisce i risultati dai dati conservati e pretende schema, chiavi coincidenti, cardinalità, metadati e almeno un confronto fatto davvero. Un valore non stimabile è ammesso; confonderlo con un valore perso no. Per gli artefatti anteriori ai contratti stampa «provenienza incompleta»: un'impronta calcolata oggi identifica byte, non certifica l'esperimento che li ha prodotti.

## Struttura

```
src/fantabot/
  engine/      motore d'asta a eventi, con registro JSONL
  bots/        A (baseline), B (il nostro), C (otto profili umani)
  season/      formazioni, sostituzioni, punteggio di lega, campionato H2H
  tabellino/   generatore: partita, partecipazione, eventi, voto
               contratto (viste temporali), origine (previsioni datate),
               presenze, calibrazione SPSA, inferenza, esecuzione
  livello3/    valutatore, ricerca su candidate, MILP esatto, indifferenza
scripts/       pipeline dei dati, banchi, esperimenti
tests/         562 test
reports/       ogni conclusione con la sua prova
viz/           replay, Sedia, Copilota
```

## Licenza e dati

Codice sotto licenza MIT. I dati grezzi non sono ridistribuiti: si scaricano da fonti terze e si rigenerano in locale con gli script della pipeline. Provenienza e dettagli in [`DATA.md`](DATA.md).

Progetto personale, costruito per una lega di amici.
