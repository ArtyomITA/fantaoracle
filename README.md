# 🔮 FantaOracle

**Il sistema che fa l'asta del fantacalcio al posto tuo — e ti dimostra perché funziona.**

Predice quanto costerà ogni giocatore con una forchetta d'incertezza, costruisce la rosa ottima col tuo budget, ricalcola tutto a ogni martelletto, e poi rigioca stagioni intere coi voti veri per misurare quanto vale davvero.

*In sviluppo attivo: il Livello 3 e la nuova valutazione sono in corso.*

---

## Perché è un problema difficile

Un'asta di fantacalcio sembra un problema di ottimizzazione. Non lo è.

I prezzi non sono dati: si formano mentre giochi, contro nove persone che hanno le loro idee. Il budget è un vincolo duro e irreversibile — un rilancio di troppo al terzo giocatore ti toglie il centrocampo. E l'obiettivo non è «massimizzare i punti attesi»: è **arrivare primo in un campionato a scontri diretti**, dove le fasce gol trasformano 66 punti in un gol e 71 in due, e dove una rosa più forte in media può vincere meno spesso di una più esplosiva.

FantaOracle affronta tutti e tre i pezzi.

## Che cosa fa

**Predice i prezzi.** Ensemble TabPFN-2 + CatBoost addestrato su **225 aste reali** crowdsourced e sugli storici delle piattaforme dal 2018. Non un numero: quantili conformali q10/q50/q90, perché sapere che un giocatore «costa 40» è inutile se la forchetta vera è 25-70.

**Predice i punti.** CatBoost sui punti di stagione. Questo è il motore del vantaggio, ed è misurato: correlazione **0,83-0,85** con i punti realmente fatti, contro **0,48-0,57** del prezzo di mercato. Il controfattuale lo conferma — lo stesso bot, con il valore di mercato al posto del suo, crolla sotto il caso.

**Costruisce la rosa.** MILP a due livelli (titolari e panchina) con modulo libero, prezzo-ombra sui ruoli, e ripianificazione completa a ogni martelletto: quando perdi un obiettivo, il piano si riscrive prima della chiamata successiva.

**Simula il mondo, non un modello del mondo.** Un generatore di stagioni che parte dal risultato della partita (Dixon-Coles con prior xG), decide chi scende in campo e per quanti minuti, distribuisce gol, assist e cartellini rispettando chi era davvero in campo in quel minuto, e solo alla fine calcola il voto. Undici in campo, un portiere sempre, espulsi che non vengono sostituiti, sostituzioni che seguono le regole.

**Si mette alla prova.** Aste complete contro avversari che si comportano come persone — otto profili calibrati su aste vere: il tifoso, il panic buyer, il tirchio, chi si fissa su un nome. Poi la stagione rigiocata coi fantavoti reali, formazioni, cambi, modificatore di difesa, campionato H2H su cento calendari.

## I numeri

| | |
|---|---|
| Correlazione del modello valore coi punti veri | **0,83-0,85** (mercato: 0,48-0,57) |
| Vittorie nei tornei simulati, 150 repliche | **75-91 %** (caso puro: 10 %) |
| Errore sulle presenze del generatore di stagioni | **0,4-0,7 %** |
| Test automatici | **271** |

I tornei sono contro i nostri bot: è il banco su cui il sistema è stato costruito, e contro persone vere ci si aspetta meno. Ogni numero qui sopra è riproducibile con un comando, e il comando sta nel report che lo contiene.

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

Tre livelli, uno sopra l'altro:

| livello | che cosa aggiunge |
|---|---|
| **0-1** | dati, modelli di prezzo e valore, motore d'asta, bot, torneo |
| **2** | generatore di stagioni fisicamente coerente — chi gioca, chi segna, chi prende voto |
| **3** | scelta della rosa che massimizza la probabilità di **arrivare primo**, e prezzo di indifferenza per ogni giocatore |

Il Livello 3 è la parte in costruzione: risponde alla domanda «fino a che prezzo mi conviene questo giocatore, considerando che comprarlo mi toglie i crediti per gli altri».

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

## Struttura

```
src/fantabot/
  engine/      motore d'asta a eventi, con registro JSONL
  bots/        A (baseline), B (il nostro), C (otto profili umani)
  season/      formazioni, sostituzioni, punteggio di lega, campionato H2H
  tabellino/   generatore di stagioni: partita, partecipazione, eventi, voto
  livello3/    valutatore, ricerca su candidate, MILP esatto, indifferenza
scripts/       pipeline dei dati, banchi, esperimenti
tests/         271 test
reports/       ogni conclusione con la sua prova
viz/           replay, Sedia, Copilota
```

## Licenza e dati

Codice sotto licenza MIT. I dati grezzi non sono ridistribuiti: si scaricano da fonti terze e si rigenerano in locale con gli script della pipeline. Provenienza e dettagli in [`DATA.md`](DATA.md).

Progetto personale, costruito per una lega di amici.
