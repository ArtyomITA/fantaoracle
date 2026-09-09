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
