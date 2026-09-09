# Proposta: calibrazione congiunta delle presenze nel cubo

**Stato: proposta. Implementazione ferma.** Serve una decisione prima di
scrivere codice, perché cambia il significato del braccio `C1` e il modo in cui
il generatore usa un'informazione esterna.

## Il problema, misurato

`reports/CICLO_20260909.md` §4. In breve, sul 2024-25, 12 scenari × 3 semi,
errore Monte Carlo 0,0098:

- il bersaglio del modello valore stima la presenza a voto per giocatore con un
  errore assoluto medio di **0,1453** contro l'osservato;
- passandolo per il cubo l'errore diventa **0,1749**, cioè **+20 %**;
- senza bersaglio il cubo sta a **0,2530**, quindi il bersaglio serve: il
  problema non è che venga ignorato, è che venga deformato.

Tre canali, tutti quantificati:

1. **conversione scalare per ruolo con troncamento** — 138 giocatori su 679
   chiedono una convocazione oltre 1 (massimo 2,4), 49 sotto 0,02: 27,5 %
   dell'universo ha un bersaglio non rappresentabile;
2. **allocazione degli undici** — scarti di segno opposto fra ruoli: difensori
   +0,0716, attaccanti −0,0274, sette volte l'errore Monte Carlo;
3. **regressione verso il centro** — chi è chiesto a metà riceve +0,0797.

I bersagli **non** sono fisicamente incompatibili: in media chiedono 13,23
presenze per squadra-giornata contro 14,10 osservate, e solo 6 squadre su 20
superano la media osservata. Il problema non è che si chieda l'impossibile.

## Perché non basta aggiustare la conversione

La conversione attuale è

    convocazione_voluta = clip(p_voto_richiesta / quota_media_di_ruolo, 0.02, 0.98)

Sostituire la quota media di ruolo con una quota per giocatore toglierebbe il
troncamento, ma non toccherebbe i canali 2 e 3: l'allocazione degli undici
resta un vincolo che redistribuisce, e nessuna scelta della propensione
individuale garantisce che le marginali simulate coincidano con quelle chieste.
Il vincolo è **congiunto sulla squadra**, la conversione è **individuale**.

Per lo stesso motivo non basta un fattore correttivo per ruolo applicato a
posteriori: sposterebbe le medie di ruolo lasciando gli errori individuali.

## La proposta

Trattare il problema per quello che è: trovare le propensioni di convocazione
e titolarità che, **date le regole di allocazione del generatore**, producono
le presenze a voto marginali richieste.

### Forma

Per ogni squadra, cercare il vettore di propensioni `θ` che minimizza

    Σ_i  w_i · ( P_sim(voto_i | θ) − p_voto_richiesta_i )²

dove `P_sim(· | θ)` è la presenza a voto marginale che il generatore produce
con quelle propensioni, e `w_i` un peso da dichiarare (uniforme come primo
tentativo). Il vincolo degli undici titolari e delle sostituzioni non entra
come vincolo esplicito: è già dentro `P_sim`, perché è il generatore stesso a
imporlo. È questo che rende la calibrazione **congiunta** e non individuale.

### Come si calcola senza rendere il fit proibitivo

`P_sim` non ha forma chiusa, ma:

- è monotona in ciascuna componente di `θ` a parità delle altre (alzare la
  propensione di un giocatore non può ridurre la sua presenza attesa), il che
  rende praticabile un'iterazione a punto fisso:
  `θ_i ← θ_i + η · (p_richiesta_i − P_sim_i)`;
- si stima con lo stesso generatore, a pochi scenari, perché serve solo la
  marginale: 12 scenari danno già un errore Monte Carlo di 0,0098, e
  l'iterazione tollera rumore;
- il calcolo è per squadra, quindi venti problemi da ~34 giocatori invece di
  uno da 679.

Costo stimato: dieci iterazioni × 12 scenari ≈ due minuti per stagione, contro
i 13 secondi di una generazione singola. Da misurare, non da assumere.

### Criteri di accettazione, da fissare PRIMA

1. l'errore assoluto medio della presenza simulata contro il **bersaglio**
   scende sotto 0,05 (oggi 0,1207);
2. lo scarto per ruolo rientra entro due errori Monte Carlo (oggi il peggiore è
   sette);
3. l'errore contro l'**osservato** non peggiora rispetto al bersaglio grezzo
   (0,1453): se la calibrazione avvicina al bersaglio ma allontana dal vero,
   il bersaglio è sbagliato e il problema è a monte;
4. le correlazioni fra compagni e la distribuzione del modificatore non
   peggiorano: sono la ragione per cui il cubo esiste, e non si baratta
   realismo fisico per punteggio marginale senza dirlo;
5. il costo resta sotto cinque minuti per stagione.

Il criterio 3 è quello che può far fallire la proposta, ed è messo lì apposta.

## Le decisioni che servono prima di implementare

1. **Il cubo deve inseguire il bersaglio?** Il bersaglio viene da un altro
   modello. Calibrare il cubo su di esso lo rende un ricampionatore di quel
   modello con vincoli fisici. È una scelta di architettura, non un dettaglio:
   se il bersaglio è più accurato del cubo sulle presenze — e lo è — la domanda
   «a che cosa serve il cubo» va risposta esplicitamente. La risposta
   plausibile è «alle dipendenze fra compagni e alla distribuzione dei punti di
   rosa», ed è verificabile, ma non l'ho verificata.
2. **Quale peso `w_i`.** Uniforme tratta un portiere di riserva come un
   titolare. Pesare per minuti attesi cambia il risultato.
3. **Che cosa fare quando il bersaglio manca** (fonte `prior_ruolo`): calibrare
   anche quelli significa inseguire un prior.

Nessuna di queste è mia da decidere.

## Che cosa NON propongo

- di togliere il troncamento senza sostituire la conversione: sposterebbe il
  problema sulla sigmoide;
- di calibrare sui risultati della stagione valutata: sarebbe guardare l'esito;
- di cambiare il verdetto del banco. Finché questa proposta non è implementata
  e verificata, `C1` resta come è, e il suo risultato resta quello pubblicato.


---

# Revisione della proposta — 9 settembre 2026

Il secondo audit ha smontato quattro punti di quella qui sopra. Li correggo
invece di riscriverla, così resta leggibile che cosa avevo assunto senza prova.

## 1. La monotonicità non è dimostrata, e non basterebbe

Avevo scritto che `P_sim` è monotona in ciascuna componente di `θ` «a parità
delle altre», e ne avevo dedotto la praticabilità di un'iterazione a punto
fisso. **Non è dimostrato** per il generatore completo: alzare la propensione
di un giocatore gli fa togliere posto ai compagni attraverso la selezione degli
undici, quindi l'effetto sugli altri è negativo e sull'interessato non
necessariamente positivo in presenza dei vincoli di modulo.

E anche se lo fosse: la monotonicità **individuale** non garantisce la
convergenza di un aggiornamento **simultaneo** di tutte le componenti. Sono due
affermazioni diverse e avevo usato la prima per giustificare la seconda.

L'iterazione a punto fisso è quindi ritirata.

## 2. Avvicinarsi al bersaglio e allontanarsi dall'osservato non identifica una causa

Avevo scritto, come criterio di accettazione numero 3, che se la calibrazione
avvicina al bersaglio ma allontana dal vero «il bersaglio è sbagliato e il
problema è a monte». **È falso in generale.** Contano la direzione del
residuo, i vincoli, il campionamento e l'errore Monte Carlo.

Controesempio scalare: osservato 0,4, bersaglio 0,5, simulazione vecchia 0,3,
nuova 0,65. La distanza dal bersaglio scende da 0,2 a 0,15, quella
dall'osservato sale da 0,1 a 0,25. Non c'è nessuna causa unica identificata: è
un semplice scavalcamento.

Il criterio resta come **segnale da guardare**, non come inferenza.

## 3. Il costo è una stima, non una misura

«Dieci iterazioni × 12 scenari ≈ due minuti per stagione» era un conto a
tavolino. Va misurato, ed è misurato nel pilota.

## 4. Il metodo

Un solo metodo, scelto e dichiarato: **SPSA** (Spall, *An Overview of the
Simultaneous Perturbation Method for Efficient Optimization*, JHU/APL Technical
Digest 19(4), 1998), letto alla fonte.

Perché questo. Il gradiente non è disponibile e ogni valutazione
dell'obiettivo è una simulazione rumorosa. SPSA stima il gradiente con **due
sole misure della funzione obiettivo per iterazione, indipendentemente dalla
dimensione** — la fonte lo dice in apertura — mentre una differenza finita
coordinata per coordinata ne richiede 2p. Con p ≈ 34 parametri per squadra la
differenza è di un fattore diciassette.

Dalla fonte, e rispettate nel pilota:

- sequenze di guadagno `a_k = a/(A+k)^α` e `c_k = c/k^γ`; la scelta è
  «critica per le prestazioni»;
- perturbazione **Bernoulli ±1**, che la fonte chiama «semplice (e
  teoricamente valida)»; uniforme e normale **non sono ammesse** dalle
  condizioni di regolarità, perché hanno momenti inversi infiniti. Questo
  esclude la scelta più ovvia, ed è il motivo per cui è scritto qui;
- la convergenza è dimostrata in senso quasi certo **sotto condizioni** su
  guadagni, distribuzione della perturbazione e relazione statistica fra
  perturbazione e misure. Quelle condizioni non le ho verificate per il nostro
  obiettivo, e non lo pretendo: SPSA qui è una **ricerca locale con un budget
  fissato**, non una garanzia di ottimo;
- la minimizzazione **globale** con SPSA richiede una variante diversa
  (Chin), che non uso.

## 5. Il bersaglio compatibile, definito

Non si chiama «impossibile» un bersaglio perché la conversione per ruolo lo
tronca. Ma un vincolo congiunto esiste, e va scritto.

Misurato sul 2024-25, per squadra × ruolo, con l'osservato aggregato per
**appartenenza alla data della partita**:

| ruolo | richiesto | simulato C1 | osservato |
|---|---:|---:|---:|
| P | 1,072 | 1,007 | 1,008 |
| D | 4,756 | 5,611 | 5,170 |
| C | 4,714 | 4,877 | 5,132 |
| A | 2,688 | 2,508 | 2,787 |

Il caso dei portieri della Fiorentina: richiesto **1,53684**, simulato
**1,01096**, osservato **1,000**. Il generatore ha ragione e il bersaglio no.
Non è un limite del processo di sostituzione: è che due portieri della stessa
squadra non prendono voto nella stessa giornata quasi mai, e la previsione ne
attribuisce a entrambi una quota alta.

Sui difensori il quadro è rovesciato: il **generatore** eccede (5,611 contro
5,170) mentre il bersaglio difetta (4,756). Sbagliano tutti e due, in direzioni
opposte. Questo da solo smentisce una lettura semplice del tipo «il bersaglio è
sempre meglio del cubo».

**Definizione operativa del bersaglio compatibile**, dichiarata prima del
pilota: dentro ogni (squadra, ruolo) si conservano le **proporzioni relative**
del bersaglio grezzo — che è l'informazione marginale che vogliamo tenere — e
si fissa la **somma** al numero medio di voti per squadra-giornata di quel
ruolo, stimato sulle **stagioni ammesse al fit**, mai su quella valutata.

    b_compatibile[i] = b_grezzo[i] * S[ruolo] / somma dei b_grezzo in (squadra, ruolo)

Non è l'unica scelta possibile ed è discutibile; è dichiarata prima, e il
pilota riporta la distanza sia dal bersaglio grezzo sia da quello compatibile.

## 6. Il piano del pilota, fissato prima

| voce | valore |
|---|---|
| parametri | uno scostamento additivo sul logit di convocazione per giocatore, solo per le squadre scelte |
| obiettivo | `Σ w_i (P_voto_sim(i) − b_compatibile[i])² + λ‖θ‖²`, `w` uniformi, `λ` dichiarato |
| valutazioni massime | 30 iterazioni SPSA = 61 simulazioni |
| arresto anticipato | nessun miglioramento oltre l'1 % per 5 iterazioni consecutive |
| semi | comuni durante l'ottimizzazione, **separati** per la verifica del candidato congelato |
| squadre | tre, scelte per criteri diagnostici dichiarati |
| dati | solo quelli ammessi al fit; nessuna calibrazione sugli esiti della stagione valutata |

Nessun aumento del calcolo se il candidato non vince. Se l'esito è negativo o
inconcludente si conserva e ci si ferma.
