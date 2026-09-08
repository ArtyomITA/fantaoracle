# Criteri di accettazione — congelati prima di produrre i nuovi confronti

7 settembre 2026, sera. Scritto **prima** di eseguire qualunque nuovo
esperimento di questa sessione. Qualsiasi modifica successiva a questo file
deve essere datata e motivata, e i risultati prodotti prima della modifica
restano leggibili con i criteri di allora.

Identificativo di sessione: `wf_l3_20260907`.
Istantanea di partenza di questa sessione: vedi `MANIFESTO.json` in
`data/l3/` (creata dopo questo documento).

---

## 0. Riscontri riprodotti prima di toccare il codice

Verificati sullo stato attuale, non accettati sulla parola.

### 0.1 `club_id` perso, appartenenza alla rosa falsa

`scripts/l2_costruisci_panel.py::_in_rosa()` legge `P["club_id"]`, ma quella
colonna **non esiste** nel panel prodotto: il primo `if` restituisce `False`
per tutte le righe.

| stagione | righe | colonna `club_id` | `in_rosa_nel_periodo=True` | titolari | titolari con `in_rosa=False` | `non_in_rosa` |
|---|---|---|---|---|---|---|
| 2024-25 | 25.802 | assente | 0 | 8.324 | **8.324** | 9.258 |
| 2025-26 | 25.194 | assente | 0 | 8.217 | **8.217** | 8.585 |
| 2026-27 | 22.306 | assente | 0 | 0 | 0 | 0 |

Un titolare non può essere fuori rosa. Le 9.258 righe `non_in_rosa` del
2024/25 **non sono verificate**: quel ramo dello `np.select` non è mai stato
raggiunto dalla condizione che doveva governarlo.

Conseguenza a valle: `partecipazione.stima()` e `_offset_da_panel()` usano
`in_lista = not in (non_in_rosa, fuori_lista)`. Con `non_in_rosa` assegnato da
una condizione degenere, propensioni e scostamenti della catena sono stimati
su un denominatore sbagliato.

### 0.2 Partite non concluse trattate come concluse

`scripts/l2_genera_cubo.py` divide passato e futuro con `data < as_of`.

Con `as_of = 2026-09-11`: 30 partite hanno data anteriore, ma solo **28**
hanno un risultato. Due partite del 7 settembre risultano non giocate:

| giornata | data | casa | trasferta | `giocata` |
|---|---|---|---|---|
| 3 | 2026-09-07 | Cagliari | Lecce | 0 |
| 3 | 2026-09-07 | Udinese | Lazio | 0 |

`--solo-future` le esclude dal futuro senza possederne il risultato: spariscono
dalla simulazione. Nessuna partita può sparire.

---

## 1. Tre verifiche distinte

### 1.1 Correttezza — tolleranza zero

Un fallimento qui blocca il ramo dipendente. Non si "compensa" con una
metrica migliore altrove.

- nessuna anticipazione: la formazione vede solo informazione anteriore alla
  sua consegna, anche negli scenari futuri;
- nessuna partita persa né contata due volte fra passato, futuro e recuperi;
- nessuna rosa illegale: quote per ruolo, budget, riserva minima, esclusività
  dei giocatori fra le squadre della stessa lega;
- nessuna contraddizione fisica non dichiarata: undici in campo salvo
  espulsione dichiarata, un portiere in campo per tutta la partita, eventi
  attribuiti a chi era in campo in quel minuto, tabellino riconciliato col
  risultato;
- ogni regola della lega applicata **esattamente una volta** lungo tutto il
  percorso, identica per osservato e simulato;
- identità fra configurazione valutata nel banco e configurazione generata.

### 1.2 Qualità predittiva

- confronto con una baseline pertinente dichiarata prima;
- differenza appaiata con intervallo al 95%, che rispetti la dipendenza
  (giocatori della stessa partita, calendari della stessa asta);
- **margine di non inferiorità zero**: un intervallo che attraversa lo zero
  non dimostra equivalenza, e non autorizza a dire "non peggiora";
- un esito inconcludente resta inconcludente e viene chiamato così;
- errore Monte Carlo e incertezza sui dati reali riportati separatamente.

### 1.3 Utilità d'asta

Metrica primaria: **P(1° posto)** nel banco dichiarato, come differenza
appaiata rispetto al confronto.

Metriche secondarie, riportate ma non decisive: fantapunti, spesa, residuo,
acquisti per reparto, target persi, inferiorità numerica, frequenza delle
decisioni dichiarate incerte.

**La spesa non è un obiettivo.** Non è autorizzato alcuno scambio fra
probabilità di vittoria e crediti spesi. Un residuo alto va spiegato con una
causa misurata, non corretto forzando la spesa.

---

## 2. Come si dichiara un risultato

Ogni risultato importante porta: configurazione, data limite informativa,
campione, confronto, intervallo, file di prova, stato di applicazione
(`applicato` / `sperimentale` / `inconcludente` / `bloccato`).

Vietato:

- spostare una soglia dopo aver visto i risultati;
- indebolire un test per farlo passare;
- selezionare le stagioni, le aste o gli avversari favorevoli;
- chiamare "ottimo globale" il risultato di un MILP che genera una candidata;
- chiamare "pipeline di produzione" un adattatore che ne reimplementa una parte;
- presentare migliaia di calendari della stessa asta come migliaia di aste.

---

## 3. Criteri specifici, fissati ora

### 3.1 Panel (F4)

Accettato se, per ogni stagione con formazioni disponibili:

- zero righe con `stato_convocazione = titolare` e appartenenza al club
  negata;
- lo stato `non_in_rosa` è assegnato solo con una prova di appartenenza
  (o non appartenenza) al club a quella data; in mancanza di prova lo stato è
  `ignoto`;
- il denominatore delle propensioni comprende solo le giornate in cui il
  giocatore era eleggibile per quel club, secondo un criterio scritto;
- un giocatore trasferito non accumula assenze nel club di partenza dopo la
  data del trasferimento;
- i test di §6 passano.

### 3.2 Contratto temporale (F4)

Accettato se:

- ogni partita ha stato esplicito fra `conclusa` / `da_giocare` /
  `rinviata` / `senza_voti`;
- la somma delle partite passate e future è sempre uguale al totale della
  stagione, per ogni data di decisione provata;
- una partita con calcio d'inizio anteriore alla decisione ma senza risultato
  resta nel futuro e viene dichiarata come "richiede aggiornamento prima
  dell'uso";
- il generatore ordina gli eventi per data e ora effettive, non per giornata.

### 3.3 Modello di partita (F5)

Accettato se benchmark e generatore costruiscono il modello con **la stessa
procedura**: a parità di dati, cutoff e configurazione, le intensità coincidono
entro 1e-9. Registrato con hash della configurazione.

### 3.4 Cubo (F6)

Accettato se, su 200 partite generate verificate:

- zero violazioni di coerenza del tabellino;
- un portiere in campo in ogni minuto di ogni partita;
- ogni rigore parato ha il rigore sbagliato corrispondente, con tiratore e
  portiere in campo a quel minuto;
- minuti ed eventi conservati anche per chi prende s.v.;
- bonus porta inviolata applicato esattamente una volta.

### 3.5 Livello 3 (F8)

Il valutatore è accettato se riproduce, su campionati piccoli calcolabili a
mano, punteggi, gol da fasce, classifica e vincitore con spareggi espliciti.

La formulazione esatta è accettata se, su istanze piccole, coincide con
l'enumerazione completa.

La ricerca su candidate si chiama **"ricerca su candidate per l'obiettivo
SAA"**. Non è ottimo globale.

Il prezzo di indifferenza è accettato se: i due rami condividono lo stesso
campione di condizioni esterne, nessun giocatore compare in due squadre, il
massimo legale e la riserva minima sono rispettati, e lo stato restituito
(`verificato` / `approssimato` / `inconcludente`) riflette l'ampiezza
dell'intervallo sulla differenza.

### 3.6 Confronto d'asta (F9)

Quattro trattamenti, mondi separati, sedie bilanciate, famiglie di avversari
dichiarate prima. Nessuna selezione a posteriori del tavolo.

Il criterio di promozione è: differenza appaiata di P(1°) **positiva con
intervallo al 95% che esclude lo zero**, su tutte le stagioni e le famiglie
riportate. Sotto questa condizione il risultato è sperimentale.

---

## 4. Che cosa NON viene toccato

Copilota, pack operativi, comportamento predefinito dei bot, mirror GitHub.
Ogni nuova strategia è raggiungibile solo con un'opzione esplicita.
Nessuna prova o dato preesistente viene cancellato.

---

## 7. Contratto degli stati — congelato il 7 settembre 2026, sera

Scritto dopo gli audit di F1 e prima di qualunque correzione. Ogni modulo che
tocca il panel o il generatore deve usare esattamente questi nomi e questi
significati. Cambiarli richiede una nuova voce datata in questo file.

### 7.1 Panel: colonne e valori ammessi

| colonna | valori | significato |
|---|---|---|
| `club_id_alla_data` | intero, oppure nullo | club per cui il giocatore era tesserato **alla data della partita**. Nullo = non ricostruibile |
| `fonte_appartenenza` | `trasferimenti`, `formazioni`, `listone`, `ignota` | da dove viene `club_id_alla_data`, in ordine di solidità |
| `eleggibile` | `True`, `False`, nullo | `True` solo se: tesserato per quel club a quella data **e** la partita ha formazioni note. `False` se e' dimostrato che era di un altro club. Nullo quando manca la prova |
| `stato_convocazione` | `titolare`, `panchina_entrato`, `panchina_non_entrato`, `escluso`, `ignoto` | `escluso` = eleggibile, partita con formazioni note, non convocato. **`non_in_rosa` sparisce**: non era uno stato del giocatore ma un'affermazione non provata |
| `stato_voto` | `con_voto`, `senza_voto`, `nessuna_riga` | invariato |

**Regola del denominatore.** Ogni propensione (convocazione, titolarita',
presenza a voto) si calcola solo sulle righe con `eleggibile == True`. Le righe
con `eleggibile` nullo non stanno ne' al numeratore ne' al denominatore: non
sono un'assenza, sono un'ignoranza.

**Regola della finestra.** L'appartenenza si valuta sulla **data** della
partita, mai sulla giornata. Nello storico 41 partite su 3.040 (1,35%) distano
piu' di tre giorni dalla mediana della loro giornata, con casi fino a 185
giorni, e in 19 casi una giornata si accavalla con la successiva: la meta' di
stagione non e' una partizione temporale.

### 7.2 Partite: stato esplicito

| colonna | valori | significato |
|---|---|---|
| `stato_partita` | `conclusa`, `da_giocare`, `rinviata`, `senza_voti` | `conclusa` = risultato disponibile; `da_giocare` = calcio d'inizio non ancora avvenuto o risultato non disponibile; `rinviata` = data effettiva oltre tre giorni dalla mediana della giornata; `senza_voti` = conclusa ma i voti non sono ancora stati acquisiti |
| `data_evento` | data e ora | calcio d'inizio effettivo se noto, altrimenti quello previsto |
| `data_disponibilita_risultato` | data, oppure nullo | quando il risultato e' diventato disponibile; nullo se non ricostruibile |
| `provvisorio` | 0/1 | invariato: data e orario possono ancora cambiare |

**Regola del taglio temporale.** Passato e futuro si separano su
`stato_partita`, non sulla sola data. Una partita con calcio d'inizio anteriore
alla decisione ma senza risultato **resta nel futuro** e viene dichiarata come
«richiede aggiornamento prima dell'uso». La somma delle partite passate e
future deve sempre fare il totale della stagione, per ogni data provata.

### 7.3 Modello di partita: una sola procedura

Benchmark e generatore costruiscono il modello con la stessa funzione, che
riceve dati, data limite e iperparametri e restituisce il modello piu'
un'impronta della configurazione. A parita' di ingressi le intensita' devono
coincidere entro 1e-9. Misurato prima della correzione: scarto medio sulle
intensita' 0,218 gol (16,6%) fra il modello del banco e quello del cubo.

### 7.4 Generatore: invarianti fisiche

1. **Un portiere in campo in ogni minuto di ogni partita.** Misurato prima
   della correzione: 37,0% delle squadra-partita ha minuti senza portiere,
   in media 8,0 minuti, fino a 85.
2. **Il cambio del portiere e' distinto dai cambi di movimento** e non entra
   nella stessa estrazione.
3. **Un espulso non puo' essere sostituito** e la squadra prosegue in dieci.
   Misurato prima: 107 espulsi su 182 giocano 90 minuti, 54 su 182 risultano
   sostituiti dopo l'espulsione.
4. **Ogni evento cade dentro l'intervallo di presenza del giocatore.**
   Misurato prima: 2,10% dei gol assegnato a chi era gia' uscito.
5. **I gol subiti da un portiere sono quelli avvenuti mentre era in porta.**
   Misurato prima: eccesso di 0,152 gol subiti per portiere a voto; in 33
   squadra-partita su 2.100 due portieri prendono entrambi tutti i gol.
6. **Rigore parato e rigore sbagliato sono lo stesso evento visto dai due
   lati** e si generano insieme.
7. **Minuti ed eventi si conservano anche per chi prende s.v.**

### 7.5 Banco: regole applicate una volta sola

Il bonus porta inviolata va applicato esattamente una volta lungo il percorso,
identico per osservato e simulato. Misurato prima della correzione: nel banco
non viene applicato in nessun punto, per 0,297 punti a giornata per rosa
(10,38 su 35 giornate).

### 7.6 Distribuzione dei gol: criterio scritto PRIMA dell'esperimento

Riscontro che apre la questione (misurato il 2026-09-07, cubo 2026-27,
impronta `9c3a76fb1145`, 40 scenari, 14.000 squadra-partita generate):

| quantita' | osservato (3 stagioni, 5.376 squadra-partita) | cubo attuale | punto stimato senza incertezza |
|---|---|---|---|
| media gol | 1,3663 | 1,4337 | 1,3310 |
| varianza | 1,4278 | 2,1556 | 1,6132 |
| P(0 gol) | 26,23 % | 30,39 % | 29,56 % |
| P(>= 6 gol) | 0,465 % | 1,829 % | 0,766 % |
| massimo | 8 | 12 | 11 |

Causa misurata, non congetturata: con `xi = 0,008` il peso totale
dell'addestramento vale **94,41** su 2.688 partite, per **57 parametri**
(2 x 27 squadre piu' intercetta, vantaggio casa, rho). L'inversa dell'hessiana
pesata da' percio' una deviazione standard sulle forze pari al **42 % di
lambda**, con lambda fino a **10,49 gol attesi** in una singola partita.

Questo confronto NON e' appaiato (osservato = tre stagioni miste, simulato =
calendario 2026-27) e da solo non basta a bocciare nulla. Serve un esperimento
fuori campione, i cui criteri si fissano qui, prima di eseguirlo.

> **RETTIFICA, 7 settembre ore 22:30.** I numeri della colonna «cubo attuale»
> della tabella qui sopra sono **sbagliati**: erano stati calcolati leggendo
> solo `v[1]` da `cubo.risultati`, cioè i gol della sola squadra in trasferta,
> metà campione preso per l'intero. Valori corretti, misurati sul cubo salvato
> (stessa impronta `9c3a76fb1145`): media **1,42604**, varianza **2,09318**,
> P(0 gol) **30,536 %**, P(>= 6 gol) **1,6036 %**, massimo 12, su **28.000**
> squadra-partita (14.000 sono le *partite*). Anche l'etichetta della colonna
> osservata è sbagliata: le 2.688 partite vengono da **otto** stagioni
> (2019-20…2026-27), non da tre. Il fatto sostanziale regge: gli intervalli di
> Clopper-Pearson restano disgiunti e la coda del cubo è **3,4 volte** quella
> osservata. L'esperimento G1 sotto è stato eseguito su dati e trattamenti
> corretti e non è toccato da questa rettifica.

**Esperimento G1 — calibrazione della distribuzione dei gol fuori campione.**

Stagioni bersaglio: 2024-25 e 2025-26. Data limite: il giorno prima della
prima giornata della stagione bersaglio. Nessuna informazione della stagione
bersaglio entra nel modello. Ogni trattamento vede le stesse partite e gli
stessi numeri casuali comuni.

Trattamenti (dichiarati prima, nessuna aggiunta dopo aver visto i risultati):

- **T0 punto stimato**: `con_incertezza = False`. Nessuna dispersione sui
  parametri.
- **T1 hessiana** (comportamento attuale): forze estratte dalla normale con
  covarianza pari all'inversa dell'hessiana della verosimiglianza **pesata e
  penalizzata**.
- **T2 sandwich**: stessa media, covarianza `H^-1 J H^-1` con
  `J = somma_i w_i^2 g_i g_i^T` (stimatore robusto per verosimiglianza pesata).
  Con pesi minori di 1 la somma dei quadrati e' minore della somma dei pesi,
  quindi T2 e' atteso piu' stretto di T1. L'attesa non e' il criterio.

Misure, tutte fuori campione, sulle sole partite effettivamente giocate della
stagione bersaglio:

1. **Punteggio logaritmico** medio del risultato osservato sotto la
   distribuzione congiunta prevista (proprio; Gneiting-Raftery 2007). Misura
   primaria.
2. **RPS** sul numero di gol di ciascuna squadra (proprio, ordinale).
3. **Brier** sulla porta inviolata (evento della lega).
4. **Calibrazione della coda**: P(>= 6 gol) e P(0 gol) previste contro le
   frequenze osservate, con intervallo binomiale al 95 % sull'osservato.
5. **PIT randomizzato** sul numero di gol, con test di uniformita'.

**Regola di decisione, fissata ora:**

- Vince il trattamento con punteggio logaritmico medio migliore su
  **entrambe** le stagioni, con differenza appaiata per partita il cui
  intervallo bootstrap al 95 % **non contiene lo zero**.
- Se i due criteri non concordano fra le stagioni, oppure l'intervallo
  contiene lo zero, l'esito e' **inconcludente** e resta il comportamento
  attuale T1. Un esito inconcludente non autorizza a cambiare il default.
- Le misure 3-5 sono descrittive: non ribaltano da sole la misura primaria,
  ma un trattamento che vince la misura primaria e peggiora la calibrazione
  della coda va dichiarato tale nel report.
- Margine di non inferiorita' zero, come per il resto della sessione.

**Cosa NON e' autorizzato da questo esperimento**: cambiare `xi` dopo aver
visto questi numeri. `xi = 0,008` e' stato scelto dalla griglia con il
criterio gia' registrato; ritoccarlo qui sarebbe spostare una soglia dopo il
risultato. Se G1 mostra che il problema e' `xi` e non la covarianza, il fatto
si dichiara e si apre un esperimento separato con la sua griglia.

### 3.7 Banco del Livello 2 (F7): verdetto statistico

**Dichiarazione di onesta' temporale.** Quando questa sezione viene scritta, le
medie del banco corretto sono gia' state osservate (tabelle
`banco_confronto_2024-25.csv` e `banco_confronto_2025-26.csv`, bonus porta
inviolata applicato una volta sola, modello di partita dalla procedura unica).
Quello che NON e' ancora stato calcolato, e che questa sezione vincola, e' il
verdetto appaiato con intervallo: differenze per osservazione e intervalli
bootstrap. La regola qui sotto vale per quel calcolo e non si tocca dopo averlo
visto.

Due confronti distinti, come richiesto:

1. **Meccanismi a informazione comparabile**: `C cubo TABELLINO` contro
   `B' vecchio + presenze del modello`. Entrambi vedono le presenze stimate
   dallo stesso modello: la differenza che resta e' quella del meccanismo.
2. **Sistemi completi**: `C cubo TABELLINO` contro `B vecchio simulatore`, ognuno
   con l'informazione che usa davvero in produzione.

Misure appaiate, sulle stesse coppie (giocatore, giornata) campionate una volta
sola e usate identiche da tutti i generatori:

- **CRPS** sul punteggio di lega del giocatore-giornata (piu' basso e' meglio);
- **Brier** sulla presenza, su tutte le coppie giocatore-giornata.

Per ciascun confronto e ciascuna misura: differenza appaiata media e intervallo
bootstrap al 95% con almeno 2.000 ricampionamenti delle coppie.

**Regola di promozione, fissata prima del calcolo:**

- `C` e' dichiarato **migliore** su una misura solo se la differenza appaiata e'
  a suo favore con intervallo che **esclude lo zero**, in **entrambe** le
  stagioni 2024-25 e 2025-26.
- Un intervallo che attraversa lo zero e' **inconcludente**, non equivalenza.
  Margine di non inferiorita' zero.
- Se `C` perde una misura con intervallo che esclude lo zero, il fatto si
  dichiara nel report con quel nome, e non si compensa con un'altra misura.
- Le quantita' di realismo (presenze per giornata, correlazioni fra compagni,
  punti per rosa, gol per rosa) sono **descrittive**: si riportano come
  distanza dalla riga `VERO`, non entrano nella regola di promozione, e non
  possono da sole promuovere `C`.
- Esito che non soddisfa la regola: il Livello 2 resta **sperimentale** e il
  comportamento predefinito non cambia.

**Limite dichiarato del verdetto 3.7**, scritto prima del calcolo. Il
ricampionamento bootstrap e' sulle coppie (giocatore, giornata) a scenari
fissati: il rumore Monte Carlo dovuto al numero finito di scenari di ciascun
generatore non viene ricampionato ed entra nei valori come se fosse un dato.
La prova `tests/test_l2_verdetto.py::test_il_bootstrap_non_vede_il_rumore_monte_carlo`
mostra il caso limite: due bracci senza alcun vantaggio sistematico, con rumore
indipendente di 0,02 su 4.000 coppie, danno un intervallo che esclude lo zero.
Percio': gli intervalli di 3.7 misurano l'incertezza sul campione di coppie, non
l'incertezza totale, e un intervallo stretto non dimostra da solo che la
differenza sopravvive a un altro insieme di scenari. Le differenze si leggono
insieme alla loro grandezza, e un verdetto favorevole con differenza minuscola
va dichiarato come tale.

### 3.8 Uso dei tetti di indifferenza nel trattamento L3+I (F9)

Scritto prima di eseguire il confronto a 22 repliche, dopo aver corretto due
difetti che rendevano i trattamenti indistinguibili (vedi `LIVELLO3.md`).

`curva()` restituisce uno stato del confronto per ciascun giocatore:
`verificato`, `approssimato` o `inconcludente`. Regola d'uso, fissata qui:

- il tetto entra in asta **solo** con stato `verificato` o `approssimato`;
- con stato `inconcludente` il bot ripiega sul tetto di B e conta il ripiego;
- il numero di lotti decisi col tetto di indifferenza e il numero di ripieghi
  sono **risultati dell'esperimento** e vanno riportati: se il tetto vale in
  pochi lotti, la differenza misurata e' quella di un sistema che per il resto
  si comporta come B, e va detto con quelle parole;
- se **nessun** giocatore del piano ottiene uno stato utilizzabile, il
  trattamento L3+I coincide con L3 per costruzione. Non e' un difetto del
  codice ma un esito: si dichiara e non si presenta come confronto fra due
  politiche diverse.

I tetti si calcolano una volta sola, prima delle repliche, dallo stato d'asta
iniziale (nulla comprato, tutti disponibili). Dipendono dal cubo e dal piano,
non dalla replica: ricalcolarli per replica non cambierebbe il valore e
moltiplicherebbe il costo.

### 7.6b Esito di G1, registrato dopo l'esperimento

Eseguito con `scripts/g1_calibrazione_gol.py`, artefatti in `data/l2/g1/`.
Date limite 2024-08-16 e 2025-08-22 (giorno prima della prima giornata), zero
partite della stagione bersaglio in addestramento, 1.000 estrazioni di
parametri, 5.000 ricampionamenti bootstrap appaiati per partita.

**Verdetto secondo la regola di 7.6: inconcludente. Resta T1.**

Il migliore sulla misura primaria e' T0 in entrambe le stagioni, ma il
confronto T0 - T2 nel 2025-26 vale -0,001029 con IC95 [-0,002357; +0,000435],
che contiene lo zero. La regola chiede che il vincitore batta gli altri su
entrambe le stagioni con intervallo che esclude lo zero: non succede.

Fatti che la regola non trasforma in azione, e che vanno detti lo stesso:

- **T1, il comportamento attuale, e' il peggiore dei tre in tutte e quattro le
  combinazioni stagione-avversario, sempre con intervallo che esclude lo zero.**
  Log score medio 2024-25: T0 2,765191, T1 2,818606, T2 2,767311. 2025-26:
  T0 2,794735, T1 2,803389, T2 2,795764.
- **Coda (misura 4)**: 2024-25, 760 squadra-partita, P(>= 6 gol) osservata
  0,003947 con intervallo Clopper-Pearson [0,000815; 0,011492]. T0 0,005545 e
  T2 0,006030 stanno dentro; **T1 0,018282 sta fuori**. Varianza dei gol per
  squadra-partita: osservata 1,298161, T0 1,518439, **T1 2,399595**, T2
  1,548800.
- **P(0 gol) 2025-26**: osservata 0,321053 [0,287951; 0,355550]; T0 0,287796 e'
  **fuori** di poco, T1 0,291576 e T2 0,288664 dentro. Come chiede 7.6: T0 vince
  la primaria e peggiora questa calibrazione di coda. Dichiarato.
- **PIT (misura 5)**: nel 2025-26 il test di uniformita' rifiuta per tutti e tre
  (p = 0,0238 / 0,0236 / 0,0255). E' un problema del modello di partita, non
  della covarianza.
- **Gli iperparametri di queste due stagioni non sono quelli del caso estremo
  di 7.6**: qui `xi = 0,0015`, peso totale 614,39 e 625,01 per 63 e 65
  parametri. G1 quindi **non** e' evidenza su `xi`, e `xi` non e' stato toccato.
- **Verifica obbligatoria del gradiente per osservazione**: scarto massimo
  1,2457e-13 e 1,3572e-14 contro la tolleranza 1e-6.
- **Difetto trovato di passaggio, non corretto qui**: `generatore.py:344-358`
  tronca a zero e rinormalizza le probabilita' negative invece di scartare
  l'estrazione non ammissibile, come `configurazione.py` documenta che si
  dovrebbe fare. Misurato: 89 estrazioni su 1.000 non ammissibili nel 2024-25
  (margine rho minimo -0,1582), 10 su 1.000 nel 2025-26. Entrambe le letture
  sono state calcolate e **danno lo stesso verdetto**.

Cambiare il predefinito adesso, dopo aver visto che T1 e' dominato, sarebbe
spostare la regola dopo il risultato. Serve un esperimento nuovo con il suo
criterio scritto prima.

### 3.9 Due grandi attaccanti: criterio scritto prima dell'esperimento

Il committente chiede che la strategia "comprare due grandi attaccanti" sia
**realmente esplorata**, senza diventare un vincolo imposto a prescindere dai
prezzi. Fin qui è stata provata solo dentro la ricerca su candidate
(`strategie_predefinite`, famiglia "due punte di prima fascia", quota d'attacco
0,60-0,75), e la ricerca su candidate è la parte del sistema che il confronto
d'asta ha appena dichiarato perdente (§3.6, LIVELLO3.md §5). Provarla solo lì
significherebbe misurarla dentro una politica che non funziona.

**Esperimento A1.** Confronto d'asta appaiato, stesso disegno di F9: mondi
separati, 22 repliche, 40 scenari, stessi nove avversari, sedie che ruotano,
stesso seme. Tre trattamenti:

- **B** congelato, come oggi (riferimento);
- **B-attacco**: lo stesso bot, con la sola quota di spesa in attacco portata a
  0,50-0,65;
- **B-due-punte**: quota di spesa in attacco 0,60-0,75.

Si cambia **una cosa sola** rispetto a B: la quota d'attacco nell'obiettivo.
Nessun'altra differenza. È una approssimazione dichiarata di "due grandi
attaccanti" attraverso la spesa, non attraverso l'identità dei giocatori: il
bot resta libero di comprare i nomi che i prezzi giustificano.

Misura primaria: differenza appaiata di P(1° posto) rispetto a B, con
intervallo bootstrap al 95% per replica. Secondarie, descrittive: spesa,
residuo, punti per giornata, gol per giornata, e quanti attaccanti fra i primi
dieci per prezzo di listino la rosa contiene.

**Regola di decisione, fissata ora:**

- una variante è **migliore** solo con differenza positiva e intervallo che
  esclude lo zero; margine di non inferiorità zero;
- una variante è **peggiore** se la differenza è negativa e l'intervallo
  esclude lo zero, e va dichiarata tale con quel nome;
- intervallo che attraversa lo zero: **inconcludente**, e non autorizza a
  raccomandare né a sconsigliare la strategia;
- l'esito vale per **questo** banco e per questi prezzi: una strategia che
  dipende dai prezzi non si promuove una volta per sempre.

### 3.9b Esito di A1, con una rettifica al criterio

**Rettifica prima dei risultati, non dopo.** §3.9 dichiarava come riferimento
«**B** congelato, come oggi». Lo script realizzato (`scripts/a1_due_attaccanti.py`)
usa invece `BBotCoerente` in tutti e tre i bracci, quindi il riferimento
effettivo è **B+**, il bot con la ripianificazione allineata al piano offline.
La prova: il braccio di riferimento dà P(1°) 0,0909 e spesa media 461,73, cioè
esattamente i valori di B+ nel confronto d'asta F9. Questo **non** rompe il
confronto — fra i tre bracci cambia una cosa sola, la quota di spesa in attacco
— ma il nome scritto nel criterio era sbagliato e va detto.

Esito, 22 repliche appaiate, 66 aste su 66, 896 secondi:

| trattamento | quota d'attacco | P(1°) | spesa | in attacco | attaccanti fra i 10 più cari | differenza dal riferimento |
|---|---|---|---|---|---|---|
| riferimento (B+) | 0,35-0,50 | 0,0909 | 461,7 | 207,7 (44,8 %) | 0,95 | — |
| B-attacco | 0,50-0,65 | 0,0852 | 452,5 | 248,0 (54,7 %) | 1,32 | −0,0057 [−0,0455; +0,0318] **inconcludente** |
| B-due-punte | 0,60-0,75 | 0,0318 | 441,8 | 269,7 (60,7 %) | 1,50 | −0,0591 [−0,1000; −0,0239] **PEGGIORE** |

Su 22 repliche: B-attacco batte il riferimento in 7, pareggia in 4, perde in 11;
B-due-punte batte in 5, pareggia in 1, **perde in 16**.

Il vincolo fa quello che deve: B-due-punte porta a casa **almeno un** attaccante
fra i dieci più cari in tutte e 22 le repliche (minimo 1, media 1,50), contro
una media di 0,95 del riferimento. La strategia è stata davvero eseguita, non
aggirata. E va peggio.

**Lettura, con i suoi limiti dichiarati.** In questo banco e a questi prezzi,
spingere la spesa in attacco fino al 60-75 % del budget **riduce** la
probabilità di arrivare primi, con intervallo che esclude lo zero. Al 50-65 %
l'esito è inconcludente: l'intervallo [−0,046; +0,032] non permette di dire né
che aiuta né che danneggia. Come scritto in §3.9, l'esito vale per questo banco
e per questi prezzi: una strategia che dipende dai prezzi non si promuove né si
condanna una volta per sempre. E il banco è il cubo, che il §7 di `LIVELLO2.md`
dichiara non promosso.
