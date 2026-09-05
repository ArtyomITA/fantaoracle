# FantaOracle — ottimizzazioni del modello attuale e architetture 2.0

Data: 5 settembre 2026. Risultato del workflow a 21 agenti (4 audit
indipendenti, 4 proposte di architettura, 12 giudici che hanno verificato ogni
affermazione sul repo, 1 sintesi). Materiale grezzo:
`reports/ARCHITETTURE_workflow_result.json` e
`reports/ARCHITETTURE_raw_journal.md`.

Tutti i numeri qui sotto sono misurati sui dati del progetto (backtest
leave-future-out su 2024/25 e 2025/26, listone 2026/27, 216 aste reali) o
verificati dal vivo sulle fonti il 4 settembre 2026. Dove un numero e' una
stima non misurata lo dico.

---

## 0. Da dove prendiamo i dati: stato verificato

| Fonte | Stato al 4/9/2026 | Cosa serve |
|---|---|---|
| fantacalcio.it (listone, voti, probabili, indisponibili, rigoristi) | OK, gia' in pipeline | Wayback degli snapshot pre-asta 2019-2025 per avere rigorista/indisponibile anche nelle stagioni di train |
| fanta.soccer (quotazioni per giornata) | OK | usare solo la g01 come feature pre-asta (oltre = leakage) |
| fantacalcio-online (prezzi live 2026/27) | OK, 302 giocatori prezzati | 108 nuovi senza prezzo live: stimarlo da fvm/qt/tm con premio nuovi |
| Understat Serie A | **endpoint cambiati a dicembre 2025**: l'HTML non embedda piu' i dati, lo scraper fallback e' rotto | riscrivere `download_understat.py` su `getLeagueData/getPlayerData/getTeamData`, salvare l'id Understat per un match stabile |
| Understat top-5 (EPL, LaLiga, Bundesliga, Ligue 1, RFPL) 2020-2026 | verificato scaricabile con `understatapi` (17.797 righe) | copre ~45-50% dei crediti dei nuovi; quasi nessuno dei nuovi da Serie B |
| Transfermarkt (kader 2026, infortuni, storico infortuni, rigoristi per stagione, cambi allenatore) | 4-5 pagine .it senza Cloudflare | scraper leggero 1 req/2 s; risolve il cold start (eta', valore, club precedente) |
| FBref | Cloudflare 403 | non serve: nessuna metrica FBref mappa su bonus fantacalcio non gia' coperti da Understat+TM; export manuale Serie B una volta l'anno se proprio |
| Sofascore / WhoScored / Fotmob | API non ufficiali, tutte bloccate | non dipendere; al massimo estrazione una tantum via browser |
| football-data.co.uk 2026/27 | quote + xG per partita, gratis | forza squadra e difficolta' calendario per riparazione e simulazione per giornata |
| openfootball (calendario 2026/27) | gratis, 380 partite | calendario per il Monte Carlo per giornata |

Cosa NON vale la pena integrare (misurato sui residui del modello valore):
xGChain/xGBuildup (~0), bonus attesi da xG per attaccanti (|corr| < 0.10 col
residuo: la fantamedia storica li incorpora gia'), stats del campionato
estero come feature libera nel CatBoost (rho nuovi +0.00/+0.03: la FVM le
incorpora gia').

### I nuovi in Serie A: come valutarli

Listone 2026/27: 152 nuovi (26%), circa 11% dei crediti di mercato, 8 sopra
20 crediti, 108 senza prezzo live (tra cui Woltemade, quotazione 23).

Il bug principale trovato dall'audit: nel backtest i nuovi hanno eta' e
valore Transfermarkt (perche' il match TM viene fatto a posteriori, con le
presenze in Serie A), nel live 2026/27 mancano al 77-82%. Il modello vede
"eta' NaN + tm NaN" solo sui nuovi live e li sottostima di 25-40 punti (10-20%
del loro valore). Fix: scraper kader TM 2026 delle 20 squadre + match senza il
vincolo delle presenze IT1 (in corso, vedi Lista 1, punto 1).

Le stats estere (Understat top-5) NON migliorano il backtest come feature
ML: vanno usate come prior esplicito e trasparente solo per i nuovi cari
(prezzo >= 10 cr o fvm >= 30):

    E[pts] = pres_att x (base_ruolo + 3 x G90_est x k_lega + 1 x A90_est x k_lega)

con shrinkage verso il modello tabulare con peso min_est / (min_est + 1500),
e coefficienti di conversione prudenti verso la Serie A: PL 1.05, LaLiga
1.00, Ligue 1 0.95, Bundesliga 0.90, Eredivisie/Primeira/Belgio/Championship
0.75, Super Lig/RFPL 0.70, Serie B 0.65, MLS/Sudamerica/Arabia 0.60. Nel
copilota va mostrato "nel campionato X: minuti, gol, xG90" accanto al valore,
con etichetta "NUOVO: stima incerta".

Il mercato paga i nuovi +18-20% a punto rispetto ai vecchi a parita' di
valore: il q50 dei nuovi cari va alzato (bias prezzo da -18.5 a circa -8
crediti) e la sigma nel Monte Carlo e nei bot C va allargata.

---

## LISTA 1 — Ottimizzazioni del modello attuale, in ordine di incidenza

### 1. Cold start dei nuovi (in corso)

Effetto misurato: elimina il bias di -25/-40 punti su ~110 nuovi; MAE nuovi
>= 15 cr da 44/51 a 37/45; prezzo nuovi cari da -18.5 a circa -8 crediti.
E' il fix col miglior rapporto impatto/costo (2-3 ore) e tocca le 6-8
decisioni d'asta da 20-110 crediti dove si regala o si strapaga.

Cosa: scraper kader TM 2026 (player_id, DOB, ruolo, valore, nazionalita', club
di provenienza) → colonna `provenienza` {IT1_rientro_prestito, IT2,
top5_estero, altro_estero, giovane_senza_minuti} al posto del flag binario;
match_tm senza vincolo IT1 anche nel backtest; q50 nuovi x1.2 per fvm >= 30 e
q90 += 0.5 q50; sigma_shift floor 0.6 e sigma_play 0.18 per i nuovi nel Monte
Carlo; bot C sigma x1.5 sui nuovi; rigenerare players_2026-27 e predizioni.

### 2. Titolarita' e presenze: il vero collo di bottiglia

Le presenze sono l'80-100% dell'errore del modello valore (MAE presenze
4.6-6.1 partite, moltiplicativo sui punti). Pre-asta si comprime poco, ma
l'asta e' DOPO 2-3 giornate e quelle giornate sono informazione fortissima:

| | 0/3 presenze | 1-2/3 | 3/3 |
|---|---|---|---|
| P(titolare 25+ partite) | 0.05-0.07 | 0.28-0.30 | 0.53-0.60 |

Oggi `market_adjust` usa un'euristica (1 / 0.85 / 0.60) che sul listone fa
MAE 37.1-37.4: peggio del modello senza aggiustamento. Addestrare le presenze
g1-3 come feature (leave-future-out sui punti delle giornate 4-38) da':
MAE 32.8 → 31.6 (2024/25) e 32.9 → 31.0 (2025/26), rho .833 → .859, fascia
rosterabile -1.4/-1.8 MAE.

Cosa: feature `pres_g1_3`, `min_g1_3` (da TM appearances), `pct_titolarita`
dalle probabili, anche per le stagioni di train (Wayback probabili di
settembre); modello presenze separato (hurdle CatBoost) con injury-proneness
da TM (partite perse per infortunio ultime 3 stagioni, giorni out) e
`rientro atteso` strutturato al posto del parser testuale.

### 3. Modello valore: TabPFN al posto di CatBoost + calibrazione per ruolo

Misurato con lo stesso protocollo conformale gia' usato per il prezzo:
TabPFN-2 batte il CatBoost valore di -3.1 MAE e +0.03 rho (2024/25), -1.6 MAE
e +0.01 rho (2025/26); sulla fascia rosterabile -2.7 / -0.5. Lo stacking
non aggiunge. Costo in codice: zero, `fit_predict_tabpfn` esiste gia'.

Calibrazione: il bias varia per ruolo (spread 15 punti tra reparti), per
eta' e per squadra. Su una rosa da 25 uno spread di 15 punti per giocatore tra
reparti sposta ~100 punti di stagione nell'allocazione MILP. Cosa:
calibrazione monotona su OOF pooled + offset per ruolo, feature `cambio_sq`
(squadra del listone diversa dall'anno prima; oggi c'e' solo il flag
nuovo_in_serie_a), eta' come spline per ruolo, forza squadra relativa;
verificare bias per ruolo entro ±5. Effetto: -1.5/-2.4 MAE sulla fascia
rosterabile, bias top da +16/+9 a ~+5.

### 4. Incertezza per giocatore e correlazione di squadra nel Monte Carlo

Oggi value_up = value + 0.674 x 43 per tutti: la coda alta e' sottostimata
(P(reale > value_up) = 0.36-0.42 invece di 0.25) e la varianza vera e'
eteroschedastica (50 nella fascia 50-150, di piu' sui 200+). L'ottimizzatore
con lam > 0 premia l'upside in modo uniforme, cioe' sbagliato.

Cosa: quantili nativi TabPFN (q10..q90) con conformal per ruolo x fascia di
valore; value_up = q75 vero; sigma per giocatore = (q90-q10)/2.56 passata
al Monte Carlo al posto della costante. In piu' un random effect
squadra x giornata (sd ≈ 0.55 sul voto puro, 13-20% della varianza, misurato
sui voti 2024/25 e 2025/26): 20 righe in `montecarlo.py`, ma cambia il
giudizio sulle difese intere (modificatore) e sul rischio comune dei
compagni di squadra, che oggi il bootstrap indipendente ignora.

### Extra, a costo zero (dati gia' in casa)

Minuti/90 e trend ultime 10 giornate (+0.01-0.03 rho su C e P), amm/90 ed
esp/90 con malus atteso esplicito, cambio allenatore da games.csv.gz (-5/-15
punti medi con varianza maggiore: utile per q10/q90), team xGA/xpts per i
portieri (+0.02-0.05 rho su 18-20 titolari), rigorista designato storico da
Wayback (+4.7/+8.1 punti/stagione per il primo rigorista, ≈ +2-3 crediti di
prezzo giusto). Cumulato realistico: +0.03-0.06 rho sul valore (da 0.82), con
guadagno maggiore sulle code (value_up, q10/q90) e sul modello presenze.

### Prezzo: il target e' ambiguo

Copertura q10-q90 misurata 35-37% invece di 80%, fascia media 5-40 crediti
sottostimata 3-4x, top-50 bias +11. Ma le due fonti (aste reali GE vs
fantacalcio-online) divergono proprio sulla fascia media: prima di
ricalibrare va deciso il target per la lega dell'utente. Proposta: usare
componenti/crediti/modificatore/periodo come FEATURE invece di filtro (il
campione sale da 2-23 a 130+ aste/stagione) e, se esistono aste passate
della lega, calibrare su quelle.

---

## TimesFM-3 e TabPFN: stessa funzione? No, sono ortogonali

- **TabPFN** (e CatBoost) sono modelli cross-sectional: una riga per giocatore
  e stagione, imparano TRA giocatori. Sono i modelli pre-asta di prezzo,
  punti e presenze, e del cold start (i 139 giocatori del listone 2026/27
  senza alcuna serie storica vivono solo qui).
- **TimesFM-3** e' un foundation model di serie temporali: impara DENTRO il
  giocatore, lungo le giornate. Puo' servire solo dove esiste una serie con
  segnale.

Misurato sui nostri voti (2021-2026, 1.279 giocatori): l'autocorrelazione
lag-1 del fantavoto entro giocatore-stagione e' -0.05, cioe' rumore bianco
attorno alla media del giocatore. Decomposizione della varianza (2024/25):
media giocatore 17%, effetto squadra x giornata 13% (ex post), residuo 70%.
Nessun modello di serie temporali puo' battere "media giocatore + covariata
squadra" di piu' di qualche punto percentuale sul fantavoto per giornata.
Inoltre la serie e' quasi discreta (42 valori unici, il 6.0 e' il 32%) e
corta (mediana 23 voti/stagione): TimesFM e' pre-addestrato su serie lunghe
e lisce.

Dove invece c'e' segnale: la DISPONIBILITA'. ACF 0.65 sulla serie presenze;
uno shrink in-season semplice (k=20, ultime 5 giornate) porta il Brier da
0.243 a 0.137 (-44%) rispetto al prior pre-asta, e il valore residuo di
stagione migliora del 3-7% man mano che la stagione avanza.

Verdetto:
1. Pre-asta: TimesFM non puo' migliorare il modello attuale. Non usarlo.
2. In-season (copilota dopo la g3, riparazione, modalita' Sedia): l'unica
   cosa spendibile subito e' lo shrink presenze k=20 + ultime 5 giornate,
   senza foundation model.
3. Esperimento post-asta, con gate go/no-go: TimesFM-3 zero-shot
   (`pip install 'timesfm[torch]==3.0.1'`, pesi HF 1.32 GB non gated, venv
   separato; la GTX 1080 Pascal e' al limite con CUDA 12.6, prevedere CPU)
   sulla serie MINUTI/presenza per giornata, multivariata [minuti, fantavoto,
   voto] con calendario come covariata futura, backtest rolling-origin
   2024/25 e 2025/26 con tagli a g 0/3/5/10/19/28. Confronto con TabPFN-TS-3
   e Chronos-2 (entrambi Apache). GO solo se batte lo shrink k=20 sul Brier
   delle presenze di almeno il 5%. Se GO, le traiettorie per giornata
   sostituiscono `p_play` e `shift` costanti in `PlayerDist`.
4. Mai per il prezzo (una osservazione per stagione non e' una serie).
5. L'unico altro uso sensato, suggerito dalla sintesi: serie a livello di
   SQUADRA (xG, xGA, ppda, npxGD per giornata, 20 squadre x 38 x 7 stagioni,
   molto meno rumorose del fantavoto) con covariate future note (avversario,
   casa, forza della stagione prima, turno europeo) per ottenere traiettorie
   di forza squadra per giornata. Alimentano P(porta inviolata), gol attesi
   di squadra e il random effect squadra x giornata del simulatore. Anche
   qui gate CRPS -5% contro media mobile + Elo; se fallisce, il random
   effect a 20 righe fa lo stesso lavoro.

---

## LISTA 2 — Tre architetture 2.0

Quattro proposte indipendenti, ognuna giudicata da tre giudici (accuratezza,
ingegneria, scetticismo) che hanno verificato le affermazioni sul repo.
Punteggi 1-10 pesati su guadagno atteso, fattibilita' in 3 mesi, dati
disponibili, rischio basso, novita'.

| Proposta | Media giudici |
|---|---|
| B. SCOUT (Claude scout documentale) | 5.33 |
| A. Cubo Posteriore (generativo gerarchico) | 5.23 |
| C. TAVOLO (agente d'asta con modello dei rivali) | 4.63 |
| D. Traiettorie (TimesFM x TabPFN) | 4.32 |

Nessuna proposta supera 6: tutte hanno un pezzo che oggi non e' validabile
sui dati che esistono. La sintesi ha quindi RIDISEGNATO le tre migliori in
versione "innestabile" sul codice attuale, con un esperimento decisivo e
un gate numerico ciascuna (vedi Raccomandazione).

### A. "Cubo Posteriore" — modello generativo gerarchico bayesiano giocatore x giornata

Idea: invertire l'ordine. Un modello generativo del fantavoto per giornata
come somma delle componenti reali (voto puro Student-t + 3 gol + assist -
0.5 amm + rigori + porta inviolata), ognuna con un processo gerarchico in
numpyro: livello latente del giocatore shrinkato verso squadra/ruolo/eta' e
verso una media da covariate (fvm, qt, log tm, xG90 estero x k_lega), quindi
cold start risolto per costruzione; disponibilita' come HMM sano/out con
hazard per eta'/ruolo; effetto squadra x giornata condiviso dai compagni. Il
posteriore e' un "cubo" di 2000 stagioni simulate, e la rosa viene
ottimizzata DIRETTAMENTE su P(1o posto) (CVaR/scenari), con scenari di
ottimizzazione e valutazione disgiunti.

Giudizi: 5.45 / 5.55 / 4.7. Cosa regge: l'effetto squadra x giornata e'
misurabile (~20% della varianza del voto puro) ed e' l'unica parte con
evidenza numerica; la diagnosi del Monte Carlo attuale (floor sigma uguale
per tutti, nessuna correlazione) e' corretta. Cosa non regge: i dati
per-partita (minuti, xG per giornata) non esistono nel repo e dipendono da
uno scraper Understat da riscrivere; il compute e' sottostimato di 10-40x
(oltre 10k parametri, HMM da marginalizzare, JAX GPU non nativo su Windows);
non tocca le due cause misurate del crollo 2025/26 (prezzo e cold start).

### B. "SCOUT" — Claude come scout documentale, TabFM per i numeri, agente al tavolo con ragionamento decomposto

Idea: il modello numerico e' cieco esattamente dove il mercato informato
vince (nuovi, gerarchie, ruolo tattico vs ruolo listone, allenatori,
rigoristi, hype). Claude NON predice punti: fa estrazione strutturata e
grounded da documenti DATATI (probabili, guide asta, kader TM, Understat
estero, notizie) in un Dossier JSON per giocatore (p_titolare, minuti
q10/q50/q90, rigorista, ruolo tattico, rischio infortunio) con citazioni.
Un retriever locale (bge-m3 su GPU + BM25) con filtro hard
`doc_date <= auction_date` (anti-leakage strutturale) alimenta lo scout e un
indice di "comparables" (~600 nuovi 2019-2025 con esito reale) per il prior
k-NN dei nuovi cari. Il Dossier entra come feature con shrinkage nel
valore/prezzo, alimenta un bot C "informato" per tornei piu' realistici, e un
agente al tavolo che ragiona per componenti (valore, prezzo, piano, rivale).
Loop settimanale di auto-valutazione (Brier di p_titolare contro le
presenze reali) durante la stagione.

Esperimento decisivo: test titolarita' grounded su 2024/25 e 2025/26, modalita'
DOCS vs NO-DOCS (se NO-DOCS >= DOCS il backtest e' contaminato e conta solo la
valutazione prospettica 2026/27). Costo stimato ~$70 di API per 1.340
giocatori.

Giudizi: media 5.33, la piu' alta. Cosa regge: la diagnosi (titolarita' e
nuovi sono l'errore piu' grande, e i documenti contengono quell'informazione).
Cosa non regge: "prova impossibile" nel backtest (Claude conosce gli esiti
2024/25 e 2025/26, anche i campi numerici possono ancorarsi al ricordo:
l'unica validazione e' prospettica, con risultati a maggio 2027); potenza
nulla sui nuovi cari (n≈40, errore standard su rho 0.15); le tre variabili
con piu' segnale (titolarita', rigorista, indisponibili) sono GIA' tabelle
strutturate scaricate dal sito, quindi il contributo marginale specifico
dell'LLM e' incerto; scope fuori scala per 3 mesi.

### C. "TAVOLO" — agente d'asta appreso con modello di popolazione degli avversari

Idea: separare tre cose che B fonde in regole fisse. (1) Chi ho davanti: un
modello generativo di tavoli umani fittato per inferenza simulativa
(ABC-SMC/NPE) sulle 216 aste reali (56 esatte 10x500: spesa 0.977±0.043 del
monte crediti, top player 0.41±0.07 del budget, quote A/C/D/P 50/26/16/8%,
CV del prezzo per fascia 0.74/0.59/0.36/0.22/0.20), aggiornato online per
ogni rivale dai suoi rilanci (particle filter su budget strategy,
allocazione, tifo, aggressivita'). (2) Quanto vale davvero ogni rilancio:
utilita' terminale = P(1o posto) della rosa contro le 9 rose che escono
dall'asta. (3) La policy: prima un Planner Monte Carlo (rollout
sull'OPM, griglia dei cap, shortlist delle nomination) sopra il B attuale,
poi una policy addestrata su milioni di aste in un FastAuction numba (target
≤50 ms/asta, parita' bit-a-bit col motore attuale su seed fissi).

Difetti di B che questo corregge, misurati: copertura in-asta degli
intervalli 63%/42% contro 80% nominale; 85 crediti medi non spesi nel
2024/25 (a fine asta valgono zero); nel 2025/26 46% contro A+ con le gemme
vere perse quasi sempre.

Giudizi: media 4.63. Cosa non regge: l'OPM non e' identificabile (le 216
aste hanno solo prezzi finali, nessuna colonna squadra, nessun ordine di
chiamata certo, e 39 su 56 aste 10x500 sono di periodo 2-3, cioe'
riparazione); in simulazione nessun rivale e' informato (i bot C sono
prezzo di riferimento x rumore lognormale), quindi la policy non puo'
imparare a "seguire chi ha ragione"; il motore attuale fa 1.3-12.5 s per
asta e la parita' bit-a-bit in numba e' un lavoro a se'; l'effetto marginale
di un singolo rilancio e' ~0.1 punti percentuali di P(win), sotto la
rilevabilita' con meno di 1000 repliche.

### D. "Traiettorie" — TimesFM-3 per giornata x TabPFN-3 cross-section x conformal (scartata)

Giudizi: 4.1 / 4.8. Il pilastro (TimesFM sulle serie per giornata) non ha
segnale da estrarre (vedi sezione TimesFM); i 2/3 del guadagno promesso
vengono da fix che non richiedono foundation model; le serie per-partita
multi-lega (25k chiamate a endpoint cambiati) sono 2-3 settimane di lavoro a
rischio blocco. Le tre idee buone che contiene (righe d'asta grezze come
contesto TabPFN con la configurazione della lega come colonne, conformal per
ruolo x fascia, correlazione di squadra nel simulatore) sono gia' assorbite
nella Lista 1 e nelle architetture A e B.

---

## Le tre architetture ridisegnate dalla sintesi (versione innestabile)

### A. "Cubo" — simulatore congiunto a componenti + portafoglio su P(1o)

Generare 2000 stagioni intere giocatore x giornata dalle componenti reali
(voto puro, gol, assist, ammonizioni/espulsioni, rigori, porta inviolata
dai gol subiti di squadra) con modelli Poisson-Gamma chiusi (Marcel
bayesiano per componente, NIENTE MCMC), shock squadra x giornata condiviso e
incertezza epistemica per giocatore. Presenze come mixture titolarita' +
infortunio con durata negativa binomiale stimata sui buchi storici. Prior dei
nuovi = regressione su fvm, qt, log tm, xG estero x k_lega con varianza
stimata. Il cubo (float16, 90-180 MB) e' consumato da ottimizzatore, bot B,
copilota e riparazione con gli stessi numeri casuali; la rosa massimizza
P(1o) esatta contro avversari valutati sullo stesso cubo (seed MILP + ricerca
locale a scambi), con scenari di ottimizzazione e valutazione disgiunti. Il
prezzo-ombra del credito (dP_win/dbudget) e il valore marginale di ogni
giocatore diventano i cap d'asta.

Perche' batte l'attuale: code grasse corrette (doppietta +6, espulsione),
correlazione portiere + 3 difensori sulla porta inviolata gratis, sigma per
giocatore invece del floor 0.35, una sola distribuzione per tutti i
consumatori, obiettivo giusto (P(1o) tra 10).

Esperimento decisivo: backtest 2024/25 e 2025/26 con fantavoti reali,
coverage/PIT per giornata e per stagione (target 0.75-0.85) del cubo contro
`montecarlo.py`; poi torneo appaiato (stessi seed, stesso pack, tavolo duro)
rosa-P(1o) contro rosa-choose_objective, 500 repliche con intervallo
bootstrap. Gate: coverage nel target E P(win) non peggiore.

Roadmap: M1 panel dai voti raw + generatore per componente + shock squadra +
sigma per giocatore (drop-in su montecarlo.py); M2 cubo + predizioni 2.0
(q10/q50/q90, P(>=200 punti), sigma dai draw) + ottimizzatore su P(1o); M3
prezzo-ombra nel bot B e nel copilota, backtest con report separato
nuovi/vecchi, aggiornamento in-season del cubo per la riparazione.

### B. "Tavolo" — planner Monte Carlo in-asta + utilita' P(1o) (senza RL, senza OPM)

Al martelletto ogni cap viene scelto simulando il resto dell'asta (50-200
rollout) con bot C campionati da un prior largo sulle 12 aste estive 10x500
pulite, valutando le rose finali con P(1o) H2H vettorizzata sul cubo. I
rivali sono descritti da feature contabili (budget residuo per reparto, slot
scoperti, crediti in stanza quando arrivera' il mio target), non da un
particle filter. Motore ~10x piu' veloce (niente replan MILP nel loop,
prezzi-ombra precalcolati), griglia dei cap {q50, q75, q90, q90+ombra},
endgame a programmazione dinamica esatta sugli ultimi 3-4 slot (residui a
zero), nomination con "pressione di necessita'", modello dei rivali a
posteriori dopo ~25 lotti dal ledger. Logging rilancio-per-rilancio dell'asta
reale del copilota: l'unico dato che manca davvero.

Gate: torneo appaiato 500-1000 aste, planner contro B attuale, +3 punti
percentuali di P(1o) sul tavolo duro con intervallo bootstrap.

### C. "Scout" — Claude estrattore documentale con loop prospettico

Claude non predice punti: estrae da documenti DATATI (probabili, guide,
Transfermarkt, notizie; retriever locale con filtro hard
`doc_date <= auction_date`) un Dossier JSON per giocatore (ruolo tattico,
gerarchia nel reparto, rigorista/piazzati, rischio cessione, hype, comparabili
k-NN calcolati dal codice) che entra nel modello tabulare come prior
shrinkato con peso appreso; ogni campo senza citazione e' NaN. Sonnet per i
delta settimanali, Opus in batch per il full run (~$17 per 600 giocatori).
Loop settimanale: Brier di p_titolare contro lo schierato, MAE minuti,
precisione rigorista, coverage; ricalibrazione pesi solo su dati 2026/27.
Claude resta fuori dal loop di rilancio (spiegazioni precomputate sui top 300).

Esperimento decisivo, solo prospettico: Dossier congelato al 1/9 per i 300
giocatori piu' cari; a G10, G19, G38 confrontare Brier, MAE minuti e rho
punti con e senza Dossier contro il modello con sole tabelle strutturate.
Gate: Brier -0.03 e MAE presenze -1.0 oltre le tabelle.

---

## Raccomandazione (una sola)

**A "Cubo"**, costruita per innesti sopra `montecarlo.py`, preceduta dalle
ottimizzazioni 1 e 2 della Lista 1 (che ne sono le fondamenta: cold start
TM e presenze/sigma per giocatore) e con l'utilita' P(1o) H2H del bot B come
primo consumatore.

Perche': e' l'unica delle tre validabile ORA sui dati che esistono (voti raw
con tutte le componenti per giornata, 59.950 righe, 5 stagioni) con metriche
ad alta potenza (coverage e PIT su migliaia di giocatore-giornate, MAE
presenze con errore standard 0.25), senza dipendere da scraping incerto, da
LLM non identificabili nel backtest o da dati sui rivali che non esistono.
Corregge insieme le tre falle misurate (livello dei nuovi, presenze e code
lunghe, incertezza scalibrata con coverage 0.37-0.42) e rende coerenti
ottimizzatore, bot e copilota su una sola distribuzione.

B "Tavolo" e C "Scout" restano estensioni: B ha il rischio piu' basso ma un
guadagno di pochi punti percentuali, non misurabile finche' la distribuzione a
monte e' scalibrata; C va avviata solo come raccolta prospettica (corpus
datato + Dossier congelato al 1/9) per avere un giudizio nel 2027, non come
architettura portante. TimesFM: no-go come pilastro, esperimento confinato a
squadra e minuti dopo la riparazione dello scraper Understat.

Sequenza operativa:

1. **Questa settimana, prima dell'asta**: Lista 1 punto 1 (cold start, in
   corso) e punto 2 nella versione veloce (presenze g1-3 come feature, sigma
   per giocatore dai quantili, sigma x1.5 sui nuovi, random effect squadra x
   giornata nel Monte Carlo). Rerun f12 e validazione f13 su 2025/26.
2. **Settembre-ottobre**: Lista 1 punti 3 e 4 (TabPFN valore + calibrazione
   per ruolo; scraper Understat sui nuovi endpoint + prior estero
   trasparente). Corpus datato per C (costo quasi zero, serve solo a
   giudicare nel 2027).
3. **Ottobre-dicembre**: Cubo M1-M3 con i gate sopra. Poi Tavolo M1.

Ogni fase ha un esperimento decisivo pre-registrato e un gate numerico; se
il gate non passa, la fase successiva non parte.

---

## Stato implementazione (5 settembre 2026, ore 03:30)

Fatto nella notte, gia' nel pack 2026/27:

1. **Cold start** (Lista 1, punto 1): `scripts/scrape_tm_kader.py` +
   `scripts/f0b_match_tm_kader.py` (rosa Transfermarkt 2026 delle 20 squadre,
   583 giocatori, match 523/587 del listone e 138/152 nuovi), patch in
   `f0b_build_outputs.py` che riempie solo i NaN. Nuovi: eta' NaN 77% → 5%,
   valore TM NaN 82% → 6%; stagioni passate invariate. Valore dei nuovi
   +9.3 punti in media (vecchi 0.0), coerente con la sottostima misurata.
2. **Premio hype** sul prezzo dei nuovi cari senza prezzo live (q50 x1.2 se
   FVM >= 30, q90 + 0.5 q50) in `market_adjust.py`, con flag `nuovo` nelle
   predizioni.
3. **Incertezza dei nuovi** nel Monte Carlo (sigma di stima floor 0.6,
   sigma disponibilita' 0.18) e nei bot C (sigma x1.5): `montecarlo.py`,
   `bot_c.py`, campo `Player.nuovo`.
4. **Shock squadra x giornata** condiviso dai compagni (sd 0.55) nel Monte
   Carlo: e' il pezzo del "Cubo" a costo zero.

Effetto sul piano 2026/27 (f12, 100 simulazioni): obiettivo lam 0, attacco
35-50%, modulo 3-4-3, P(1o) 35% contro archetipi 7-29%; in attacco entrano
Ramos G. e Varela G. (nuovi, prima invisibili al modello). Validazione sui
voti reali 2025/26 (f13): piano a prezzi di mercato 499 crediti, 76.8 punti a
giornata, vittoria 60% contro archetipi <= 1%: invariata, nessuna regressione.

Per usare il pack nuovo: riavviare il Copilota dal menu.

Da fare prima dell'asta (Lista 1, punto 2 veloce): presenze g1-3 come feature
addestrata al posto dell'euristica di titolarita'.
