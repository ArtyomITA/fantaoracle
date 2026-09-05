# FantaOracle 2.0 — architetture di secondo livello (spiegate)

Data: 6 settembre 2026. Risultato del workflow a 22 agenti: 7 architetti con angoli obbligati (niente LLM al centro, niente TimesFM sul fantavoto), 14 giudici che hanno verificato ogni affermazione sul repo (lenti: accuratezza/novita' e fattibilita'/dati), 1 sintesi. Proposte grezze complete in `reports/ARCHITETTURE2_raw_architetti.md`, giudizi in `reports/ARCHITETTURE2_workflow_result.json`.

## Punteggi dei giudici (media delle due lenti, scala 1-10)

| # | Proposta | Media |
|---|---|---|
| 1 | TABELLINO — simulatore generativo del tabellino di partita (score → eventi → voto) con priori TabPFN, disponibilità semi-Markov e rosa ottimizzata direttamente su P(1º) | 6.95 |
| 2 | FILTRO — stato latente giocatore/squadra con aggiornamento coniugato (Kalman a passi annuali + HMM di disponibilita' a durata), senza foundation model | 6.85 |
| 3 | FantaOracle PONTE — equivalenze tra leghe per i nuovi (transfer learning gerarchico multi-lega + depth chart + comparables conformali + modello del premio di provenienza) | 6.50 |
| 4 | ORGANIGRAMMA — depth chart probabilistico per squadra (modulo → posti → assegnazione Plackett-Luce con utilita' TabPFN, infortuni come rimozione dal grafo) | 6.30 |
| 5 | FantaICL — "Contesto Vivo": foundation model tabulari in-context su righe grezze, con il tavolo d'asta e la stagione in corso dentro il contesto | 6.20 |
| 6 | FantaOracle 2.0 "PORTAFOGLIO" — la rosa come portafoglio robusto sotto errore di stima correlato | 6.12 |
| 7 | FantaOracle 3.0 «DUALE» — asta come inferenza sul valore comune + controllo contabile del tavolo (prezzi duali, shading di Milgrom-Weber, endgame DP, nomination come design dell'informazione, equilibrio EGTA) | 5.75 |

Pesi: guadagno atteso 0.30, profondita' tecnica 0.25, novita' 0.15, fattibilita' con i dati 0.20, chiarezza 0.10.

---

# FantaOracle — Sintesi finale delle architetture (giudicate e verificate sui dati)

Premessa di metodo. Sette proposte, ognuna valutata da due giudici che hanno rifatto le misure sui file del repo. Qui tengo sei architetture (una è la fusione di due), ne scarto una come architettura tenendone la scoperta più importante, e per ogni numero dico se è **misurato** (e da chi, su cosa) o **stima**. Contesto vincolante: oggi è il 5/9/2026, l'asta è a giorni; nessuna di queste si costruisce prima dell'asta, quindi ogni sezione distingue "fix a costo zero da fare subito" da "architettura da costruire per la riparazione di gennaio e il 2027".

Tre fatti verificati dai giudici che cambiano il quadro rispetto ai report precedenti:

1. **La copertura 80% del modello VALORE è già 0.74-0.79** (misurata dal giudice su `data/indagine/pred_valore_baseline_2024-25/2025-26.csv`). Lo 0.37-0.42 che tutti i report citano è la copertura del **PREZZO** contro il wayback, e il "0.36-0.42" del valore è P(reale > q75) invece di 0.25 (coda alta). Chi promette "copertura da 0.4 a 0.8 sul valore" promette qualcosa che c'è già.
2. **`target_wayback_p500_10sq` è un prezzo in-stagione** (snapshot 14/2/2025 e 11/4/2026, da `data/raw/wayback_prices/chosen.txt`), non pre-asta. Serve da target del modello prezzo 2025/26, da `ref_price` dei bot C e da "mercato" nei controfattuali: tutto ciò che lo usa come "cosa sapeva il tavolo a settembre" ha senno di poi. Emerso verificando DUALE.
3. **`TEAM_SHOCK_SD = 0.55` in `montecarlo.py` è 4 volte troppo grande in varianza**: l'effetto squadra × giornata sul voto puro misurato vale sd ≈ 0.25-0.26 (var 0.07, giudici di TABELLINO e FILTRO su voti raw 2021-26). Fix da una riga.

---

## 1. Le architetture, spiegate

### A. TABELLINO — simulare la partita, poi il tabellino, poi il voto

**Cos'è.** Oggi il simulatore pesca per ogni giocatore un fantavoto dalla sua storia e aggiunge un rumore di squadra scritto a mano: 25 dadi quasi indipendenti. Ma nel fantacalcio gli eventi arrivano insieme: se l'Inter vince 3-0, Sommer prende +1, i tre difensori prendono 6.5+ (e scatta il modificatore), Lautaro probabilmente segna. TABELLINO simula prima il **risultato** di ogni partita del calendario (modello Dixon-Coles, quello dei bookmaker), poi decide chi ha giocato e quanti minuti, poi divide i gol della squadra tra i giocatori in campo come una torta (chi prende una fetta la toglie ai compagni), poi assegna il voto puro **dato** quel tabellino (chi segna riceve +0.9 di voto oltre al +3). Il fantavoto è calcolato con le regole della lega, non estratto. Esempio: "pago 25 il quarto difensore dell'Inter o 8 il titolare del Cagliari?" — il simulatore risponde con quanto cambia la P(1°) comprandolo a quel prezzo, perché sa che la difesa Inter è correlata con Sommer e col modificatore. Esempio 2: Falcone/Okoye "portieri da parate" — il simulatore vede che il Lecce prende 1.6 gol a partita e porta inviolata nel 20% dei casi, contro 45% di una big; la differenza di punti stagione viene dalla struttura, non da un coefficiente (l'ordine "10-15 punti" resta una stima non misurata).

**Pezzi tecnici.**
- *Panel giocatore × giornata con minuti*: join `voti_*.csv` (5 stagioni, 22 componenti) × `transfermarkt_appearances_seriea.csv` (81.643 righe, minuti per partita 2019-25) × `games.csv.gz` (380 partite/stagione 2012-25, risultato, modulo, allenatore, colonna `round`). Copertura del join misurata dal giudice: **99.4% delle righe con voto 2024/25**, gol concordi 99.9%. Attenzione: 432 righe hanno `rigore_segnato=1` e `gol_fatti=0` (fantacalcio.it non sempre include il rigore nei gol) — va normalizzato nel panel.
- *Modello partita*: gol casa ~ Poisson(exp(h + att_i − def_j)), correzione Dixon-Coles per i punteggi bassi, prior per squadra da xGA Understat stagione precedente (corr con quota porte inviolate −0.60, gol subiti +0.69 su 102 squadre-stagioni) e valore rosa TM; aggiornamento in-season con decadimento temporale. Output: risultato per scenario, P(porta inviolata) per partita. Validazione: Brier P(cs) < 0.19 vs 0.205 del tasso base 0.288; RPS sull'1X2.
- *Voto puro condizionato agli eventi*: v = μ_i + β·gol + γ·assist + κ·(gf−gs) + η·cs + u_squadra + ε. Coefficienti misurati e **stabili per stagione** (giudici): 1 gol +0.88/+1.01, 2+ gol +1.5/+1.9, assist +0.5/+0.6, portiere cs +0.16, ≥3 subiti −0.29; ε ~ N(0, 0.45²) (Student-t ν=12.6: gaussiana basta). Test decisivo fatto dal giudice: correlazione del voto tra due difensori della stessa squadra-giornata 0.305 → 0.134 tolto risultato ed eventi; portiere-difensore 0.148 → **0.014**. Il risultato è davvero il fattore comune per il modificatore; tra difensori resta un residuo (sd ~0.2) da stimare, non da fissare a occhio.
- *Ripartizione gol*: Multinomial(gol squadra, pesi ∝ minuti × tasso Gamma per giocatore). Prior del tasso da TabPFN sulle covariate del listone, aggiornamento coniugato con i minuti come esposizione. Correlazione negativa tra compagni gratis. Assist: Bernoulli per gol (non multinomiale libera, altrimenti assist > gol).
- *Cubo con numeri casuali comuni*: 2000 stagioni × 587 giocatori × 38 giornate in float16 (~90 MB), RNG counter-based per (scenario, partita) e (scenario, giocatore). Stesse partite per tutte le rose.
- *Harness*: PIT randomizzato per componente (Czado-Gneiting-Held 2009), CRPS per giornata, correlazione compagni predetta vs realizzata, gate pre-registrati; conformalizzazione CQR dei quantili del cubo per ruolo × fascia se il PIT non è piatto.

**Perché batte il modello attuale.** Misurato: il legame voto-bonus è il 31% della varianza del fantavoto (var 2.345 = voto 0.364 + bonus 1.253 + 2·cov 0.727, riprodotto dai giudici); la media di squadra-giornata è spiegata al 65-78% dal risultato (R² 0.649-0.78 a seconda del filtro; residuo sd 0.15-0.175 contro floor campionario 0.13-0.15). Il simulatore attuale usa shock 0.55 (sbagliato) e campioni appaiati per i vecchi (quindi la covarianza voto-bonus **c'è già** nel bootstrap: il proponente sbagliava a dirla ignorata). Il guadagno vero: correlazioni P+3D giuste per costruzione, code (doppiette, rigori, espulsioni) e incertezza per giocatore invece di floor uguali per tutti, un solo oggetto per bot/copilota/riparazione. Stima onesta: rho valore +0.00/+0.02 (il livello resta TabPFN/CatBoost), CRPS giornata −0/−3% (il fantavoto per giornata è rumore bianco, lag-1 −0.05), win-rate torneo +0/+10 pp con IC ±3.

**Cosa c'è di nuovo.** Dixon & Coles 1997, Karlis-Ntzoufras 2003, Baio-Blangiardo 2010 per il risultato; Hunter-Vielma-Zaman 2016 e Haugh-Singal 2021 per P(vincere) in fantasy; CRN e SAA (Kleywegt et al. 2002). Il giudice ha segnalato che la catena "risultato → ripartizione gol tra giocatori → punti fantasy → ottimizzazione" è già il design di **AIrsenal** (Alan Turing Institute, FPL) e di Matthews-Ramchurn-Chalkiadakis (AAAI 2012). Nuovo davvero: il **voto del giudice umano regredito sul tabellino** (FPL non ha un voto), la correlazione P+3D per il modificatore, TabPFN usato come prior di tassi Poisson poi aggiornati coniugatamente, P(1°) in H2H a fasce gol con differenze appaiate su CRN, prezzo di indifferenza dP(1°)/dprezzo.

**Cosa serve.** Dati: tutto in casa e verificato (voti, TM minuti, games, Understat squadre, mappe id al 93-99%). Da scaricare: calendario 2026/27 (openfootball). Non esistono: minuti in Serie B/estero per 134/152 nuovi (restano sul prior). Hardware: CPU (numpy/scipy/CBC); torch installato è **CPU-only** (`cuda=False`), TabPFN su 587 righe gira comunque. Tempo: il proponente dice 9-12 settimane-persona, i giudici **12-16** (vettorizzare `pick_lineup`/`score_giornata` per 2000 scenari, EM, harness a 6 componenti × 4 ruoli).

**Rischio principale.** "Onesto ma invisibile": intervalli calibrati e correlazioni giuste senza che P(1°) nel torneo si muova oltre il rumore. Secondo: il prior TabPFN usa prev1-3 come covariate e poi il coniugato aggiorna con gli stessi gol storici → doppio conteggio, posteriore troppo stretta (usare solo covariate non storiche nel prior, o la predittiva TabPFN come posteriore).

**Esperimento che decide.** Leave-future-out 2024/25 e 2025/26 (fit solo su stagioni precedenti, rigorista dell'anno prima). Gate: PIT piatto per componente; correlazione predetta vs realizzata dei punti stagione tra P+3D della stessa squadra entro ±0.1; Brier P(1°) predetta vs realizzata su 30 rose candidate; copertura 80% separata vecchi/nuovi **≥ quella attuale (0.74-0.79)** e coda alta P(y>q75) da 0.30-0.43 a 0.22-0.30. Poi torneo appaiato 500 repliche × 2 stagioni, ablation 2×2 (cubo vs montecarlo.py) × (ottimizzatore P(1°) vs choose_objective).

---

### B. FILTRO — livello costante, disponibilità con memoria

**Cos'è.** Il bot ha un numero per giocatore e una probabilità di presenza piatta su 38 giornate. I dati dicono che sono due cose diverse. (1) Il **livello** (quanto vale quando gioca) **non cambia dentro la stagione**: la media del ritorno differisce dall'andata esattamente quanto il caso (varianza in eccesso −0.005, riprodotta dal giudice su 1.349 giocatore-stagioni, tutti i ruoli). Quindi l'aggiornamento dopo K giornate è una formula: stima = prior + n/(n+k) × (media osservata − prior), con k per ruolo ≈ 13-20 partite per A/C/D e 40-55 per i portieri (il k dei portieri è fragile: 64 coppie). Frattesi che parte 7.5 dopo 3 giornate vale +5 punti sulla stagione, non +50: **non inseguire la forma**. (2) La **disponibilità** ha memoria oltre il primo ordine: P(gioca | ha giocato le ultime due) 0.835, P(gioca | assente-poi-giocato) 0.639, P(gioca | giocato-poi-assente) 0.468, P(gioca | assente due volte) 0.146 (riprodotto). Le assenze sono sovradisperse (media run 2.68, varianza 10.3 contro 4.5 geometrica) e la probabilità di rientro **cala** con la durata (0.52 dopo 1 giornata, 0.20 dopo 8). Hien con rientro stimato 5/10 parte "fuori" fino alla g6. Decisione a gennaio: Zaccagni pagato 43, livello 6.05, stato rotazione 60%, valore residuo 62 (35-90); lo svincolato altrui vale 80 residui a 25 crediti dei +100: il bot propone lo svincolo coi numeri.

**Pezzi tecnici.**
- *Prior d'asta → (media, varianza) del livello*: dal TabPFN a quantili sul fantavoto medio condizionato a giocare. Attenzione (giudice): `mu0 = value/pres` dalle b_predictions è pessimo (RMSE 1.14-2.11 contro 0.44 con fantamedia anno prima shrinkata): il prior va costruito sul target giusto.
- *Aggiornamento del livello*: Normal-Normal per ruolo con k misurato; componenti a conteggio Gamma-Poisson sui minuti (esposizione = minuti/90 dal panel TM).
- *Disponibilità*: la versione **minima che i giudici hanno verificato battere**: catena a hazard dipendente dalla durata della run (presente/assente × lunghezza, hazard empirici 2021-24, nessun EM, ~20 righe). Brier sulle 5 giornate successive **0.16-0.19** contro Markov primo ordine 0.20-0.21 e prior 0.19-0.21 (giudice, 2024/25 e 2025/26); oracolo che conosce il tasso vero 0.14-0.16. L'HMM a 4 stati fase-type con covariate proposto sopra guadagna al massimo 1-2 punti di Brier in più e non è identificabile senza lo storico infortuni (non nel repo).
- *Stato di squadra*: forza attacco/difesa Gamma-Poisson coniugata (prior xGA), shock giornata i.i.d. (sd 0.30 sul voto medio, lag-1 −0.035; **sottraendo il rumore campionario ≈ 0.25**) sottratto prima di aggiornare il giocatore. `games.csv.gz` ha avversario e casa per tutte le stagioni di train: il proponente era pessimista.
- *Regola di scambio/svincolo*: accetta X per Y se P(1° | rosa−X+Y) − P(1° | rosa) > 0 sugli **stessi draw** (differenza appaiata, errore ~10× più piccolo).

**Perché batte il modello attuale.** Misurato (proponente, riprodotto): Brier presenza resto-stagione prior 0.243 → beta-binomiale k=10 0.232 (g3) / 0.217 (g19); RMSE media resto-stagione −2/−7% con k=20. Stima: MAE presenze pre-asta con stato iniziale da probabili/indisponibili da 4.6-6.1 a 4.0-5.0 (nessun supporto: lo snapshot 1/9 è già usato da market_adjust); P(1°) sul ritorno con riparazione +3/+6 pp (nessuna misura). Onestà del proponente: sul livello il guadagno in-season è piccolo per costruzione; il valore è nella disponibilità e nella coerenza.

**Cosa c'è di nuovo.** Il "Kalman a passi annuali con q=0" è, come dice il giudice, uno shrinkage Normal-Normal rinominato (Tango/Marcel, Efron-Morris); Glickman-Stern 1998 e Koopman-Lit 2015 per gli stati di squadra. Nuovo: la **misura** che il livello non deriva (che disegna il modello), la memoria del secondo ordine e l'hazard decrescente come giustificazione di una catena a durata, la regola di scambio appaiata. La versione ridisegnata del "Cubo" nel journal aveva già Poisson-Gamma chiusi, NegBin sui buchi, cubo float16, prezzo-ombra: qui l'aggiunta vera è piccola ma verificata.

**Cosa serve.** In casa: voti 5 stagioni, TM minuti, games, Understat squadre, kader 2026, snapshot 1/9. Falso nel repo: `target_n_obs_tardiva` è 0 e `target_mean_pct_tardiva` NaN per tutti i 663 giocatori 2025/26 — il modello prezzo di gennaio (C6) **non ha target**; il "periodo" delle aste reali cambia significato per stagione (2021-22 periodo 2 = 16.121 righe, periodo 3 = 0). `replicas.jsonl` contiene seed e riepiloghi, non rose (rigenerabili dai seed). CPU, 5-7 settimane-persona se si tiene la catena a hazard; C3 (HMM) è la parte lunga e va tagliata.

**Rischio principale.** Vendere come "forma" un guadagno del 2-7%: delude. Va comunicato come regola decisionale ("non inseguire la partenza a razzo, i portieri restano ancorati").

**Esperimento che decide.** Rolling-origin 2024/25 e 2025/26 tagli g3/g5/g10/g19, solo dati ≤ taglio. Gate onesti (riscritti dai giudici): sulle 5 giornate successive battere la catena a hazard (0.16-0.19) di ≥1 punto di Brier e migliorare la log-verosimiglianza; copertura 80% del valore residuo 0.75-0.85 (mai misurata prima); riparazione simulata +100 crediti su rose rigenerate dai seed, B-posteriore vs B-prior appaiati, +3 pp con IC che esclude 0.

---

### C. GERARCHIA — chi prende il posto quando manca il titolare (ORGANIGRAMMA ridotto)

**Cos'è.** Un allenatore non sceglie i giocatori uno per uno: sceglie un modulo e riempie i posti. Se stimo Bisseck (24 presenze) e Stones (14) separatamente, la somma del reparto può fare 4 posti o 2.5. La proposta originale voleva un modello di scelta a capacità fissa (Plackett-Luce per posto). I giudici hanno misurato il tetto: **rinormalizzando le presenze predette con i totali REALI di reparto (oracolo) la MAE scende da 5.6-6.5 a 5.2-6.1, cioè −0.47 gare (−8%)**, non i −15/−20% promessi; con i totali dalla media di lega il 2024/25 peggiora. L'errore sta nella ripartizione dentro il reparto, che il modello attuale già ordina bene (rank correlation 0.75 entro squadra-reparto). Ciò che invece **regge ed è nuovo per il repo**: quando un titolare abituale manca, il posto va al primo backup per minuti nelle 10 gare precedenti nel **60-68%** dei casi (riprodotto su 3.9-4.0k episodi; 0.60 escludendo i rientri; tasso base 0.36; top-2 backup 0.90). Quindi le presenze di titolare e vice sono **anticorrelate** e il Monte Carlo attuale (Bernoulli indipendenti) non lo sa: una coppia titolare+vice dello stesso posto vale più della somma, e "se ho Bastoni, Bisseck vale +X crediti" è calcolabile.

**Pezzi tecnici.**
- *Matrice di sostituzione R[i,j] = P(j titolare | i assente) − P(j titolare)*, stimata direttamente dal panel TM per squadra-reparto, senza Plackett-Luce. Va nel cubo come struttura di correlazione delle presenze.
- *Pannello squadra × partita × giocatore* costruito con `game_lineups` + `game_events` della stessa fonte dcaribou (flag titolare, posizione per gara, minuto di sostituzione): elimina lo slot latente, l'EM/Sinkhorn e il proxy "minuti ≥46" che fallisce nel 31% dei club-partita (solo il 69% ha esattamente 11 titolari col proxy).
- *Feature di contesto di reparto* per TabPFN/CatBoost presenze: concorrenti eleggibili per slot, forza media, nuovo arrivo con fee (38-51% dei minuti di reparto vanno ai nuovi arrivati, misurato 2020-25).
- *Offset di conservazione* per squadra-reparto come post-processing, gated: nel 2025/26 pred/reale era 0.876 (44% celle < 0.85), ma nel 2024/25 0.958 — era un bias di quell'anno, non un difetto strutturale.
- *Cap contingenti alla rosa*: valore marginale del backup dato il titolare posseduto, dagli scenari del cubo.

**Perché batte il modello attuale.** Misurato: primo backup 0.60-0.68 vs base 0.36. Stima: guadagno pre-asta sulle presenze 0.2-0.5 gare (tetto oracolo −0.47); il guadagno vero sta nelle correlazioni e nei cap contingenti, **non misurato** (il test "rosa con 3 difensori della stessa squadra sotto correlazione strutturale vs indipendenza" era fattibile e non è stato fatto). Il gate post-g3 proposto (Brier −0.02 rispetto a 0.137) è impossibile: l'oracolo a tasso costante fa 0.132.

**Cosa c'è di nuovo.** Plackett-Luce/McFadden, Sinkhorn: noti. Lineup prediction e "expected minutes" FPL esistono senza vincolo di capacità. Nuovo: l'handcuff del fantasy NFL formalizzato come prezzo-ombra contingente e la matrice di sostituzione dentro un simulatore fantasy.

**Cosa serve.** Match TM↔listone è **93-99%** (98-100% su qt≥5), non 68% come temeva il proponente. Da scaricare: `game_lineups`/`game_events`. Problema vero: la fonte TM ha **sospeso gli aggiornamenti da luglio 2026**: per il 2026/27 minuti e moduli vanno presi altrove. CPU; versione ridotta 1-2 settimane (contro 5-7 dell'originale).

**Rischio principale.** Con 8D/8C e 3 cambi a giornata il valore assicurativo del vice potrebbe essere piccolo: va misurato nel torneo appaiato prima di costruire altro.

**Esperimento che decide.** Nel cubo: stessa rosa con e senza R[i,j], giornate a 11 schierati e P(1°) appaiata; test delle coppie titolare+vice vs rosa senza copertura; conservazione ±5% nel 90% delle celle come metrica permanente.

---

### D. NUOVI — premio di provenienza, comparables, blend con FVM (PONTE ridotto)

**Cos'è.** Un quarto del listone non ha mai giocato in Serie A. La proposta originale voleva "tradurre" le statistiche estere tra leghe (le Major League Equivalencies del baseball) con un modello gerarchico su tutte le transizioni tra 6 leghe. **I dati la smontano**: matchati 261/885 nuovi alle stats Understat estere, l'npxG90 estero ha correlazione **0.066** coi punti in Serie A (parziale sulla FVM −0.09); le transizioni sono 901-920 non "migliaia" (193 verso la Serie A, ~40/anno); nel leave-one-season-out gli effetti lega non migliorano l'RMSE (0.541-0.602 con shrinkage semplice vs 0.535-0.608 con effetti lega); il min_share non si trasferisce (corr 0.20). Coerente con l'audit del journal (stats estere: rho nuovi +0.00/+0.03). Quello che invece **regge su due fonti indipendenti** è il premio di provenienza: a parità di punti e ruolo, gli importati dalle top-5 costano +9.7% (wayback, n=142, se 0.057) / +17.5% (aste GE 10x500 estive, n=36, se 0.16), i rientri dall'Italia **−34% / −27%**, le leghe secondarie −16/−29%; punti reali per credito nella fascia 10-20: rientri IT1 11.6 vs top-5 6.9. E il fix a costo zero: rank-blend 50/50 modello+FVM sui nuovi cari dà rho **0.816/0.714** contro 0.789/0.614 del modello e 0.726/0.724 della FVM — raggiunge da solo il gate che PONTE si era dato. Esempio: Woltemade (Juve, da Newcastle, FVM 160) sarà pagato sopra il valore: esca da chiamare presto; un rientro dal prestito o Kevin Carlos/Adams: mirino.

**Pezzi tecnici.**
- *Premio per provenienza* come categoria con interazioni (provenienza × log TM × log FVM) e effetto casuale per asta, al posto del moltiplicatore uniforme ×1.2 di market_adjust; da rifare a parità di FVM (ex ante) e non di punti realizzati. Output: hype_gap con intervallo, etichette ESCA/MIRINO. La "mezza-vita del premio" non è stimabile: fanta.soccer ha 38 snapshot/stagione solo fino al 2022/23, poi 26, 6, 6.
- *Conformal pesata per shift di popolazione* (Tibshirani et al. 2019) + Mondrian provenienza × ruolo × fascia + localizzazione con i vicini nello spazio `get_embeddings` di TabPFN 8.2 (verificato esistente): copertura sui nuovi garantita per costruzione; k-NN sulle colonne grezze è pessimo (rho 0.45/0.39).
- *Depth chart per slot* (non softmax sul reparto: i concorrenti di un reparto da 3-4 slot giocano insieme) per le presenze dei nuovi, dove min_share estero non aiuta.
- *Pannello multi-lega* solo come contesto per il copilota ("a Newcastle: 0.45 npxG90 in 1.800 minuti"), non come modello.

**Perché batte il modello attuale.** Misurato: FVM ordina i nuovi meglio del modello (0.848 vs 0.818; sui cari 0.724 vs 0.614 nel 2025/26); bias −15.5 sui top-5 (n=48). Stima: P(1°) +1/+3 pp (i nuovi sono l'11% dei crediti, 6-8 decisioni da 20-110 crediti), sotto la rilevabilità; la metrica giusta è punti/credito sui nuovi comprati e numero di zavorre.

**Cosa c'è di nuovo.** MLE di Bill James, ZiPS, CIES: mai per il fantacalcio, ma qui non funzionano. Nuovo e verificato: il premio quantificato per provenienza (auction theory su aste sequenziali con budget, Benoit-Krishna 2001, non lo modella), la conformal pesata con metrica appresa da un foundation model tabulare per il cold start.

**Cosa serve.** Tutto in casa (aste GE, wayback, kader con club precedente per 138/152, valuations con lega). Understat top-5 scaricabile (17.797 righe già nello scratchpad) ma serve solo come contesto. Serie B non esiste (FBref 403). Ridotto: 1-2 settimane; il blend FVM è mezza giornata.

**Rischio principale.** Potenza: 44-48 nuovi cari per stagione, se(rho) ≈ 0.11: ogni delta sotto 0.10 è rumore. E il tifoso juventino paga Woltemade comunque.

**Esperimento che decide.** Confronto a tre (attuale / FVM / nuovo) sui nuovi qt≥8 pooled 2023-26; copertura condizionale ≥0.65 per provenienza; premio riprodotto out-of-sample con lo stesso segno; torneo appaiato con punti reali/credito sui nuovi comprati da B.

---

### E. TAVOLO — prezzo pooled, forchette per fascia, tetti con garanzia (da FantaICL e DUALE)

**Cos'è.** Oggi il modello prezzo impara da 12 aste "uguali alla nostra" (10 squadre, 500 crediti, estive: 7+4+1) e dal wayback contaminato; al tavolo applica un termometro scalare con bound [0.8, 1.6]. Tre cose verificate. (1) Mettere la **configurazione della lega come colonne** (componenti, crediti, modificatore, periodo, fonte) invece che come filtro spiega il **12.4%** della varianza residua dei prezzi in log e porta il campione da 12 a **216 aste** (139+54+23; il proponente contava 139 perché `auction_id` riparte per stagione). (2) La dispersione tra aste dello stesso giocatore dipende dalla fascia: sd log **0.95 sotto i 10 crediti vs 0.34 sopra gli 80**: un delta conformal unico è sbagliato per costruzione. (3) Il "contesto vivo" (i lotti già battuti che insegnano al modello il calore del tavolo) vale molto meno del promesso: tolta la configurazione, l'effetto asta residuo è il 3.4% (asta × ruolo 8.2%); con una baseline che conosce la configurazione, 40-80 lotti rivelati danno **−0.8/−1.8% di MAE log**, non −5/−6%. Ma la contabilità sì: i crediti sono conservati, quindi la spesa totale in attacco è prevedibile dalla fase P/D/C con errore **2.7-4%** invece del 15% (rho −0.96/−0.98 su 15-46 tavoli). Esempio: Malen (Roma, qt 34, mezza stagione): il prezzo lo legge da come, in 216 aste, sono stati pagati attaccanti con quel TM e quella FVM in leghe a 10 con modificatore; se i primi attaccanti sono andati cari, il tetto sale via ACI di qualche credito, non per un termometro.

**Pezzi tecnici.**
- *Prezzo pooled*: target log(prezzo × 500 / crediti_tot), configurazione come colonne, su CatBoost/TabPFN-feature esistenti (48k righe), ablazione contro il filtro 10x500. Attenzione al target: aste GE estive (periodo 0/1) per il backtest, live 1/9 per il 2026/27, **mai wayback**.
- *Mondrian conformal* per ruolo × 3-4 fasce (non 32 gruppi con mediana 13 righe), calibrazione out-of-season. Nota: sul test R2 contro aste GE la copertura è già 0.72-0.86; il crollo 0.35 è su R3 contro wayback (target mismatch), non colpa dello split.
- *ACI al tavolo* (Gibbs & Candès 2021): α_{t+1} = α_t + γ(α − err_t) sui quantili del lotto; 5-20 righe, garanzia asintotica; da validare sulle 12-16 aste 10x500 estive rigiocate in 20 permutazioni (l'ordine di chiamata non esiste nei dati GE: le righe sono impaginate P,D,C,A).
- *Prezzi duali della rosa*: rilassamento LP del MILP di `optimizer.py` → μ (punti per credito marginale) e λ_r (valore ombra dello slot); tetto come punto fisso [E(V) − λ_r]/μ = p, decomposizione leggibile nel copilota. ~100 righe. Da misurare la stabilità dei duali tra martelletti (i duali di un MILP rilassato con binari di modulo possono saltare); finché non è misurata, μ e λ dal drop-off attuale.
- *Vincolo contabile della fase A* come tetto di spesa sugli attaccanti.
- *Log rilancio-per-rilancio* nel copilota (chi, quanto, quando passa): oggi il ledger salva solo i martelletti; è l'unico dato che manca a tutto il livello in-asta e costa mezza giornata.

**Perché batte il modello attuale.** Misurato: 12.4% varianza da configurazione; contabilità 4% vs 15%; sd per fascia. Stima: MAE top-50 da 13 a 10-11 crediti; copertura in-asta da 63/42% a ≥75%. Onestà: il "calore per ruolo con covarianza" (A-C −0.48, D-P +0.72) non regge su 15 tavoli puliti (A-C −0.11, D-P +0.29, se ~0.3).

**Cosa c'è di nuovo.** Pooling con covariate è regressione gerarchica standard; ACI su un'asta al martelletto per i cap di rilancio è, per quanto ne sanno i giudici, inedito; il protocollo leave-one-auction-out sequenziale con permutazioni e baseline "config nota" è un metro nuovo per il repo; TAC/RoxyBot (Wellman et al.) avevano già "previsione distribuzionale + offerta al valore marginale", qui si aggiunge il vincolo contabile.

**Cosa serve.** Tutto in casa. Non serve TabPFN v2.5 (checkpoint assente, licenza da verificare; su CPU 1000 righe × 300 colonne = 376 s: il contesto di 12-15k righe è ore). 2-3 settimane.

**Rischio principale.** Zero aste storiche della lega dell'utente: l'ACI non corregge nulla finché non arrivano 20-30 lotti; il target GE vs wayback diverge nella fascia 5-40 (20.4 vs 9.0 nel bucket 15-25).

**Esperimento che decide.** Leave-future-out prezzo con configurazione-come-colonne vs filtro: pinball, copertura per fascia ≥0.75, MAE top-50 ≤11; aste 10x500 estive rigiocate: copertura cumulata per lotto con e senza ACI; torneo appaiato con B che usa i duali: gate non-peggioramento.

---

### F. BANCO — numeri casuali comuni, test di selezione, P(1°) esatta (PORTAFOGLIO ridotto + C5 di TABELLINO)

**Cos'è.** L'ottimizzatore compra gli errori: i giocatori scelti dalla MILP rendono meno di quanto promesso rispetto ai loro pari (**gap −24.9 punti/giocatore nel 2024/25 e −18.5 nel 2025/26**, riprodotto dai giudici su `pred_valore_presenze_gk_*.csv` + pack). Ma i giudici hanno trovato **dove** sta: gli 11 titolari rendono quel che il modello dice (residuo +1.5 / −0.3); il gap è nella panchina (~−20/giocatore) e nel fatto che il modello sottostima i cheap (residuo per quartile di value +34/+14/+15/−4 nel 2024/25; +33/+35/+15/−1 nel 2025/26). La "correzione per edge" della proposta è un confondimento col livello del value: sui rosterabili (ref≥3) una regressione a 2 parametri (pendenza 0.79) fa lo stesso lavoro. Il "blocco squadra" (tau) con l'ICC corretto per il rumore campionario è **0 nel 2024/25** e 0.08-0.15 nel 2025/26 (trainato da Verona +92, Cremonese +73): non identificabile su 2 stagioni. Quel che resta, ed è infrastruttura obbligatoria per qualsiasi verdetto sotto i 3 pp: un banco appaiato. Oggi f12 sceglie l'obiettivo con 150 simulazioni **non appaiate** (ogni candidata riceve un rng diverso, `choose_objective` riga 228): SE su P(1°) 2.9-3.7 pp. Con 1000 scenari a numeri casuali comuni: 1-1.5 pp. E DIAGNOSI_ROSA mostra che +100 punti attesi non spostano P(1°) (34% vs 34%): l'obiettivo giusto non è E[punti]+λ·upside.

**Pezzi tecnici.**
- *Simulatore vettorizzato*: tensore (scenari × giocatori × 38), una rosa = selezione di colonne + lineup vettoriale; scenari di ottimizzazione e di valutazione **disgiunti** (maledizione del vincitore al livello del MC).
- *Test di selezione* come metrica permanente in `backtest_valore.py`: residuo della rosa MILP (titolari e panchina separati) vs pari con ref≥5.
- *Ricalibrazione della mediana sui rosterabili* (pendenza 0.79 + intercetta, o isotonica ristretta a ref≥3) e peso panchina non piatto (oggi 0.30 in `optimizer.py`).
- *Ottimizzatore P(1°)*: MILP seed → SAA su 200 scenari con **indicatori binari per scenario** (max Σ z_s, score_s ≥ M_s − M(1−z_s); il giudice ha smontato la CVaR α=0.3 di TABELLINO: alza la media del peggior 30%, cioè le sconfitte nette, senza toccare P(1°)) → ricerca locale a scambi con P(1°) esatta appaiata. Avversari: 3 famiglie (bot C, archetipi, rose informate), max-min.
- *Prezzo di indifferenza* p*_i = max prezzo tale che ΔP(1°) ≥ λ·p, con λ = dP(1°)/dbudget dalla curva P(1°)(B) misurata **sui voti reali**, non sull'obiettivo MILP (che nel 2025/26 inverte la concavità: titolari reali 2548/2582/2637 a 400/500/600).
- *Sigma per giocatore* al Monte Carlo al posto della costante 0.674×43; la sd del residuo per fascia è instabile tra stagioni (20/45/51 vs 59/46/34), quindi conformal per ruolo × fascia, non CatBoost quantile su 370 righe.
- *Lineup consapevole dell'avversario* solo come funzione piccola del copilota: la leva di varianza di una lineup è ~0.7 di sd (11 giocatori con sd A 2.1/C 1.4/D 1.1), cioè +0.02 di utilità a partita; il +15% della proposta era tra sd 5 e sd 11, irraggiungibile.
- *Guardia prudenziale*: max 3 per squadra in rosa, dichiarata come prudenza, non come parametro stimato.

**Perché batte il modello attuale.** Misurato: gap di selezione; SE 2.9-3.7 vs 1-1.5 pp; f12 senza CRN. Stima: P(1°) +0/+2 pp dalla ricalibrazione (lo shrink lineare grezzo lascia la rosa reale 2025/26 invariata a 5650 punti: la media da sola non muove la decisione), il resto viene dall'obiettivo P(1°) e non è misurato.

**Cosa c'è di nuovo.** Smith-Winkler 2006 (optimizer's curse), Michaud, Black-Litterman; Bertsimas-Sim, Delage-Ye; Haugh-Singal 2021: tutti citati e corretti, ma il DRO con blocco squadra non è identificabile qui. CRN, scenari disgiunti, dP_win/dbudget erano già nel journal (righe 449-480). Nuovo: il test di selezione come metrica di accettazione e la scoperta che il gap vive nella panchina; SAA con indicatori per P(1°) H2H a fasce.

**Cosa serve.** Tutto in casa. `players_2022-23.parquet` non esiste, quindi la terza stagione di residui OOF è debole. CPU; 2-3 settimane (il simulatore vettorizzato è condiviso con TABELLINO).

**Rischio principale.** Kappa/λ scelti su griglia con MC rumoroso: selezione per caso; riportare la curva intera e usare scenari disgiunti.

**Esperimento che decide.** Gate A: gap di selezione < 8 punti/giocatore su 2 stagioni con ricalibrazione; rosa P(1°)-SAA vs rosa choose_objective, 1000 scenari appaiati + replay sui voti reali, ΔP(1°) ≥ +3 pp con IC 90% > 0 in una stagione e ≥ −1 nell'altra.

---

## 2. Come si combinano

Le sei non sono alternative: sono strati di un solo stack, e il fatto che tre proposte indipendenti (TABELLINO, FILTRO, ORGANIGRAMMA) siano convergite sullo stesso panel TM e sulla stessa disponibilità a durata è il segnale più forte del giro. Ordine per costo/guadagno e per dipendenze:

**Livello 0 — fix a costo zero, prima dell'asta (2-3 giorni).**
- Sostituire il wayback con le aste GE estive (backtest) e il live 1/9 (2026/27) ovunque: target prezzo, `ref_price` dei bot C, controfattuali. Rifare `f1_price_eval` R3.
- `TEAM_SHOCK_SD` 0.55 → 0.25 in `montecarlo.py`.
- Rank-blend 50/50 modello+FVM sui nuovi cari.
- Premio per provenienza (top-5 +10-18%, IT1 −27-34%) al posto del ×1.2 uniforme in market_adjust; etichette ESCA/MIRINO nel copilota.
- Catena a hazard dipendente dalla durata (20 righe) al posto di p_play costante nel Monte Carlo; stato iniziale da indisponibili/rientro_stima.
- Regola "non inseguire la forma" con k per ruolo nel copilota post-g3.
- Log rilancio-per-rilancio nel copilota.
- CRN in f12 (20 righe) e test di selezione nel harness.
Gate: nessuno di questi deve peggiorare rho valore (0.82) o il win-rate 2025/26 nel torneo appaiato.

**Livello 1 — panel e banco (settimane 1-4).** Panel giocatore × giornata con minuti TM (join 99.4%) + `game_lineups`; simulatore vettorizzato con scenari disgiunti; harness PIT/CRPS/copertura/correlazione compagni applicato **prima al modello attuale** (baseline vera: copertura 0.74-0.79, coda alta 0.30-0.43). Gate: parità statistica col montecarlo attuale a seed fissi; SE appaiata < 1/3 della non appaiata.

**Livello 2 — cubo TABELLINO (settimane 4-12).** Dixon-Coles con prior xGA; ripartizione multinomiale gol / Bernoulli assist; voto condizionato agli eventi; disponibilità a durata (livello 0) + matrice di sostituzione R[i,j] (GERARCHIA); prior TabPFN solo su covariate non storiche + coniugato sui minuti. Gate pre-registrati: PIT piatto per componente/ruolo; Brier P(cs) < 0.19; correlazione P+3D predetta vs realizzata ±0.1; copertura 80% ≥ 0.75 su vecchi E nuovi; coda alta in [0.22, 0.30]; Brier P(gioca) 5 giornate ≤ catena hazard (0.16-0.19); MAE presenze non peggiore.

**Livello 3 — ottimizzatore P(1°) e prezzo di indifferenza (settimane 12-15).** SAA con indicatori + ricerca locale appaiata; λ dalla curva P(1°)(B) sui voti reali; p*_i come cap del bot B. Gate: ΔP(1°) ≥ +3 pp appaiata con IC 90% > 0 in una stagione e non peggiore nell'altra; ablation 2×2 per attribuire il guadagno all'asse "cubo".

**Livello 4 — prezzo pooled + Mondrian + ACI + duali (in parallelo, 2-3 settimane).** Indipendente dal cubo: gate copertura per fascia ≥ 0.75, MAE top-50 ≤ 11, copertura in-asta ≥ 75% entro 40 lotti.

**Livello 5 — in-season e riparazione (gennaio).** Aggiornamenti coniugati (livello, tassi, forze squadra con decadimento), rigenerazione cubo giornate 20-38 (~1 min), regola di scambio/svincolo appaiata, conformal pesata sui nuovi di gennaio. Gate: punti reali giornate 20-38 rosa riparata vs non riparata, primo dato quantitativo sulla riparazione.

Lo stack risultante ha **un solo oggetto sorgente** (il cubo) consumato da valore, Monte Carlo, ottimizzatore, bot, copilota, riparazione, e **un solo metro** (banco appaiato con gate pre-registrati). Il modello prezzo resta il collo di bottiglia del 2025/26 e va fatto in parallelo, non dopo.

---

## 3. Cosa NON fare e perché

- **DUALE come architettura.** Il pilastro "il mercato segnala il 96% dei breakout" e "MAE 35.7 → 32.3 senza senno di poi" è costruito sul wayback di febbraio/aprile: con le aste estive vere la correlazione sorpresa-residuo scende da 0.445 a **0.152**, i breakout segnalati dal 97% al 62%, la correzione da −2.9 a −0.4 di MAE. La "asimmetria breakout/flop" è base rate (la sorpresa è >0 per l'87-93% del listone perché q50 è sistematicamente basso). La DP di endgame ha 6.6·10^10 stati, non 10^5. Milgrom-Weber richiede la funzione segnale→rilancio del rivale, non identificabile. Salvati: la scoperta wayback, i duali LP, la contabilità della fase A, il log rilanci, l'EGTA come protocollo di robustezza.
- **Effetti lega stimati (PONTE C2) e traduzione del min_share.** npxG90 estero rho 0.066, LOSO senza guadagno, corr min_share 0.20. Tre settimane su un segnale che non c'è.
- **Contesto vivo di TabPFN al tavolo e pannello grezzo di 456 colonne (FantaICL).** Effetto asta residuo 3-8% della varianza, −1/−2% MAE; le 456 colonne aggiungono ~1% di informazione oltre gli aggregati (MAE presenze 8.06 → 8.01); compute su CPU ore per fit, checkpoint v2.5 assente. TabPFN resta dov'è: prior/feature-model sulle aggregate (dove batte CatBoost: MAE 30.7 vs 33.8, +0.03 rho), quantili nativi, embeddings per i comparables.
- **CVaR α=0.3 come surrogato di P(1°).** Ottimizza le sconfitte nette. Usare SAA con indicatori binari.
- **Semi-Markov a 3 stati / HMM a 4 stati fase-type con covariate.** Senza storico infortuni (non nel repo) I1/I2 non sono identificabili; il margine oltre la catena a hazard è 1-2 punti di Brier; l'età conta poco (misurato). Il gate "Brier resto-stagione ≤0.21 a g3" è irraggiungibile (memoria geometrica 0.237, oracolo 0.163).
- **Plackett-Luce con slot latente e EM/Sinkhorn.** `game_lineups` esiste; il proxy sui minuti fallisce nel 31% delle partite; il tetto del vincolo di capacità è −0.47 gare con totali perfetti.
- **Blocco di errore comune per squadra (tau) e correzione per edge.** tau = 0 nel 2024/25; l'edge è il livello del value sotto altro nome.
- **Modello del prezzo di gennaio come modello autonomo.** Target tardivo inesistente nel parquet, periodo ambiguo per stagione, zero storico della lega.
- **Mezza-vita del premio sui nuovi.** Servono 38 snapshot fanta.soccer/stagione; dal 2023/24 ce ne sono 26, 6, 6.
- **Valore d'opzione della panchina e lineup a varianza nel MILP.** Leva ~0.02 di utilità a partita, sotto il rumore MC.
- **TimesFM sul fantavoto, LLM come pezzo centrale.** Già esclusi; il fantavoto per giornata è rumore bianco e nessun componente qui ha bisogno di un LLM (al massimo per leggere il tipo di infortunio in `indisponibili.csv`).

---

## 4. La mia raccomandazione

**Costruire il cubo TABELLINO come unica sorgente del sistema, con dentro la disponibilità a durata di FILTRO e la matrice di sostituzione di GERARCHIA, misurato dal banco appaiato con P(1°) via SAA, e portare in parallelo il prezzo pooled con Mondrian e ACI — dopo aver fatto, questa settimana, i fix a costo zero del livello 0.**

Perché questa e non un'altra. È l'unica delle sette in cui i giudici hanno **riprodotto quasi tutte le misure** (varianza voto/bonus, R² del risultato, coefficienti evento→voto stabili per stagione, correlazione P-D 0.148 → 0.014 tolto il risultato, join minuti al 99.4%) e in cui la struttura risolve insieme le tre cose che il simulatore attuale sbaglia — correlazioni tra compagni (shock 4× troppo grande e senza segno), varianza per giocatore (floor uguali per tutti) e presenze (98% dell'errore, oggi p_play costante) — con un solo oggetto che serve asta, copilota, riparazione e formazione. I dati sono tutti in casa e verificati; il compute è CPU; non c'è MCMC né LLM. Il guadagno atteso sul livello è dichiaratamente ~0 (rho 0.82 resta di TabPFN/CatBoost) e sul torneo è una stima (+0/+10 pp, IC ±3): per questo il gate non è "vinci di più" ma "PIT piatto, correlazione compagni giusta, Brier P(gioca) non peggiore della catena a hazard, e ablation che attribuisce il guadagno all'asse cubo"; se passa solo la calibrazione, il cubo vale comunque come fonte di b_predictions, σ e cap, e si scarta l'ottimizzatore.

Due condizioni oneste. Primo: 12-16 settimane-persona, quindi il bersaglio è la riparazione di gennaio e l'asta 2027, non quella di settimana prossima — per quella valgono i fix del livello 0, che da soli correggono tre errori verificati (wayback, shock 0.55, ×1.2 uniforme sui nuovi) e aggiungono due segnali misurati (blend FVM, catena a hazard). Secondo: il modello prezzo è metà del crollo 2025/26 e TABELLINO non lo tocca; il livello 4 va fatto in parallelo, non rimandato.