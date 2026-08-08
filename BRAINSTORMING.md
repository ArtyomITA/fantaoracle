# FantaBot — Brainstorming predittore asta Fantacalcio 2026/27

> Documento di analisi pre-progetto. Nessuna decisione presa, nessun codice: tre metodologie a confronto, inventario dati, ruolo di Claude, limiti di realismo. Basato su ricerca web massiva (6 agenti, ~150 fonti, agosto 2026).

---

## 1. Il contesto in breve (cosa ha confermato la ricerca)

**La vostra lega** (da confermare, vedi §8): Classic, budget 500 crediti, asta a chiamata (uno nomina un giocatore, si rilancia, l'ultimo che rilancia se lo aggiudica; se nessuno rilancia va al chiamante a 1), ruoli in ordine P→D→C→A oppure ordine casuale, niente Mantra. Rosa standard Classic: 25 giocatori = 3P / 8D / 8C / 6A.

**Tempistiche 2026/27**: listone ufficiale Fantacalcio.it uscito il **4 agosto 2026**; Serie A al via il **22-23 agosto 2026**; mercato chiude l'**1 settembre** → la maggior parte delle aste si fa tra fine agosto e i primi di settembre. L'asta di riparazione cade a gennaio 2027 (svincoli + asta sui liberi, crediti da svincolo tipicamente 50% del pagato, 100% se ceduto all'estero).

**Vincolo strutturale dell'asta** che ogni tool deve rispettare: offerta massima = crediti residui − (slot vuoti − 1), perché ogni slot costa minimo 1 credito.

**Numeri di ancoraggio budget** (consenso guide italiane, lega 8-10 squadre a 500):
- Portieri 6-9% (30-45 cr), Difesa 12-16% (60-80; fino a 25% se modificatore difesa attivo), Centrocampo 24-30% (120-150), Attacco 50-64% (250-320).
- Regola pratica: "arrivare agli attaccanti con almeno 280-300 crediti".
- Costo medio per slot ≈ 20 crediti (500/25).

**Il numero più importante trovato in tutta la ricerca** (fantacalcio.dev, backtest su 3 stagioni): la fascia top costruita con fantamedia si conferma solo ~50% delle volte. Per ruolo: centrocampisti 62%, difensori 54%, **attaccanti 33%, portieri 33%** (praticamente lancio di moneta). Gli esperti (Goal.com ecc.) non fanno meglio. Conclusione onesta: **nessun modello predice bene la fascia alta**; il vantaggio competitivo reale sta in (a) prezzi disciplinati, (b) tracking dell'inflazione live, (c) valore sopra il replacement, (d) non fare gli errori classici — non nella sfera di cristallo.

**Errori classici documentati** (Sky, guide italiane) che il bot deve prevenire: panic buy sul primo attaccante rimasto, risparmio eccessivo scoperto a fine asta, price enforcing su ruoli scoperti, crediti residui non spesi (valore zero), "gratitudine" verso i giocatori dell'anno scorso, fidarsi dei neopromossi.

**Dinamiche d'asta empiriche** (sfruttabili): il primo top chiamato per ruolo va spesso *sotto* prezzo (cautela iniziale), i successivi si ancorano al suo prezzo e salgono; giocatori nominati prima del loro rank vanno sopra il valore medio il 75% delle volte; l'inflazione = (crediti residui in stanza) / (valore di listino residuo) e va tracciata in tempo reale.

---

## 2. Inventario dati (cosa esiste davvero, verificato)

### Target possibile: il prezzo d'asta
| Fonte | Cosa dà | Accesso |
|---|---|---|
| **Le vostre 2 aste passate** | Prezzi reali della VOSTRA lega, con gli STESSI avversari | Da fornire tu (formato da capire: export Leghe? Excel? foto?) |
| **Fantacalcio-Online "Stima prezzi asta"** | Prezzi medi REALI pagati nelle aste della piattaforma, filtri per 8/10 squadre e budget 350/500, URL per stagione (storico dal ~2018/19) | Web, scrapabile, gratis |
| **FantaMaster PMA** | Prezzo medio in % del budget (normalizzato!), da migliaia di leghe, filtro per dimensione lega e modificatore | Tool web gratuito, non scaricabile → trascrizione/scraping |
| **Fantacalcio.it media acquisti** | Prezzi medi per budget/partecipanti | Solo app mobile "Guida per l'Asta Perfetta", nessun export ⚠ |
| **FVM ufficiale** (FantaValore di Mercato) | Stima redazionale del prezzo d'asta atteso, base 1000 crediti | Export Excel dal listone, storico 2015/16→oggi |

Nota: "MetaRday" non esiste nei risultati di ricerca (probabile nome storpiato — candidati: Fantametric, Fantaculo, FantaLab). Da chiarire. In ogni caso i surrogati sopra coprono il buco.

### Feature (input del modello)
- **Quotazioni ufficiali** Qt.I / Qt.A / FVM: export Excel da fantacalcio.it/quotazioni-fantacalcio, dropdown stagioni dal 2015/16. Storico completo gratis.
- **Voti e fantavoti per giornata**: fantacalcio.it/voti-fantacalcio-serie-a, stesse ~11 stagioni, pulsante export; PianetaFanta arriva fino al 2002.
- **Statistiche avanzate**: Understat (xG/xA dal 2014/15, libreria Python `understatapi`), FBref, Transfermarkt via `dcaribou/transfermarkt-datasets` (aggiornato settimanalmente: 520k+ valutazioni di mercato storiche, 1.8M presenze, trasferimenti).
- **Titolarità**: nessun archivio storico di % titolarità esiste → proxy = minuti/presenze da FBref. Per il 2026/27 corrente: SOS Fanta probabili formazioni con % schierabilità.
- **Nuovi acquisti estate 2026**: tabelloni Sky/Goal + statistiche del campionato di provenienza (Understat copre i top-5 campionati) + valore Transfermarkt.
- **Consensus esperti 2026/27** (già online ora): fasce SOS Fanta (in FantaLab), guida Goal.com, consigli Fantacalcio.it/FantaMaster, rigoristi.

### Repo da cui rubare pattern (non da dipendere)
- `uPeppe/fantabeto` — reti bayesiane sul fantavoto, gestione rookie con stats dei campionati esteri (pattern cold-start).
- `piopy/fantacalcio-py` — scraper Fantacalciopedia + indice di convenienza.
- `giodavoli/fantacalcio-optimization` — MILP proprio sul fantacalcio (450 cr titolari + 50 panchina).
- `Lollitor/ml-fantacalcio-2024-2025` — predizione gol/assist → prezzo massimo oggettivo.

### Il dato mancante che nessuno ha
Nessun dataset pronto "prezzi d'asta multi-stagione + feature". **Va costruito**: è il lavoro vero della fase dati, ed è anche il motivo per cui nessun tool italiano fa vera predizione ML del prezzo (fanno solo medie empiriche o valori redazionali). Spazio libero.

---

## 3. Il problema, scomposto bene

Quattro sotto-problemi distinti — confonderli è l'errore di design classico:

1. **VALORE**: quanti fantapunti porterà il giocatore? (proiezione rendimento)
2. **PREZZO**: quanto verrà pagato all'asta? (predizione mercato — cosa faranno gli ALTRI)
3. **PORTAFOGLIO**: quale combinazione di 25 giocatori massimizza i punti con 500 crediti? (ottimizzazione vincolata)
4. **ESECUZIONE**: cosa faccio quando l'asta devia dal piano? (replanning live, inflazione, nomination)

L'oro sta nello **scarto tra 1 e 2**: comprare valore che il mercato sottoprezza. Il punto 3 senza il 4 è inutile (il piano salta sempre — "non andrà mai come sperate"); il 4 è dove si vince davvero, e guarda caso è il "nice to have" che avevi in mente: la ricerca dice che non solo è fattibile, è il pezzo più importante.

---

## 4. Proposta A — "Il Ragioniere": statistica classica + valore sopra il replacement

*Filosofia: niente ML sul prezzo, formule trasparenti, robustezza massima. È il metodo dei tool USA maturi (FantasyPros, Razzball).*

**Pipeline**
1. Proiezione punti stagionali per giocatore: fantamedia pesata multi-stagione con regressione verso la media (metodo "Marcel") + aggiustamenti manuali/Claude, corretta per titolarità attesa e rigori.
2. **VORP**: valore = punti proiettati − punti del "replacement" di ruolo (il miglior giocatore che a fine asta prendi a 1 credito; con 8-10 squadre il replacement è il ~30° difensore preso, ecc.).
3. Conversione in crediti: `prezzo_equo_i = VORP_i / Σ VORP_positivi × (budget_lega_totale − 1×slot_totali)`. Con 8 squadre × 500 = 4000 crediti in stanza.
4. Prezzo di mercato atteso = media ponderata di FVM/2 (FVM è su base 1000), medie Fantacalcio-Online per leghe a 500, e i prezzi delle vostre 2 aste passate riscalati.
5. Lista d'asta: per ogni giocatore → prezzo equo, prezzo di mercato atteso, **max bid**, tier. Compri dove equo > mercato.
6. Live: foglio con inflazione = crediti residui stanza / listino residuo; i max bid si moltiplicano per l'inflazione.

**Pro**: spiegabile al 100%, zero rischio overfitting (con ~500-1000 osservazioni il rischio è reale), implementabile in giorni, degrada bene se i dati fanno schifo.
**Contro**: non impara dalle vostre aste (usa solo medie), non gestisce bene i nuovi acquisti (serve comunque giudizio), niente incertezza quantificata, il VORP dipende dalla proiezione punti che resta il pezzo debole (~50% sulla fascia alta).

---

## 5. Proposta B — "L'Ibrido": TabPFN distribuzionale + Claude come valutatore strutturato ⭐ consigliata

*Filosofia: due modelli separati (valore e prezzo), foundation model tabulare per il regime small-data, Claude fonde il qualitativo nel quantitativo. È il pattern IBM Watson/ESPN (arXiv 2111.02874) adattato al fantacalcio.*

**Perché TabPFN e non XGBoost**: il vostro dataset è esattamente il regime dove i tabular foundation model dominano. TabArena (NeurIPS 2025): sui dataset ≤10k righe i TFM battono i GBDT anche tunati; TabPFN-2.5 ha il 100% di win rate contro XGBoost default sotto le 10k righe. Con ~500-1500 righe siete nel cuore del suo territorio. Bonus enormi per questo caso d'uso:
- **Output distribuzionale nativo**: `predict(X, output_type="quantiles")` → per ogni giocatore ottieni P10/P50/P90 del prezzo in un forward pass. "Lautaro: mediana 180, ma 20% di probabilità che superi 220" è esattamente il formato che serve a un'asta.
- Zero tuning, zero encoding, missing gestiti nativamente → meno codice, meno overfitting.
- **Gira sulla tua GTX 1080** (README ufficiale: "even older GPUs with ~8GB VRAM work well"; niente flash attention su Pascal ma con 500 righe gira perfino su CPU in secondi).
- Licenza: uso personale non commerciale ok anche per 2.5/3; alternative con licenza pulita: TabPFN-2 (Apache 2.0), TabICL v2 (open, ora con regressione), Google TabFM (giugno 2026, zero-shot, pesi non-commercial — da provare come confronto, è la "novità Google" che citavi).
- Baseline obbligatoria comunque: **CatBoost** (categoriche native + `RMSEWithUncertainty`). L'ensemble TabPFN+CatBoost batte i singoli (risultato TabArena). Se CatBoost pareggia TabPFN, teniamo il più semplice.

**Modello PREZZO** (il cuore). Una riga = (giocatore, asta, stagione). Target: **prezzo in % del budget** (normalizzato — così le 2 stagioni vostre + le medie piattaforma convivono anche se i budget differiscono). Feature: Qt.I, FVM, fantamedia 1-2-3 anni, presenze, gol/assist/rigori, xG/90, età, squadra (fascia), ruolo, nuovo-in-Serie-A flag, prezzo pagato l'anno prima nella VOSTRA lega, media piattaforme, **punteggi Claude** (sotto). Training: vostre 2 aste + prezzi medi Fantacalcio-Online multi-stagione (righe "lega media" pesate meno). Validazione: leave-one-season-out (train 2024/25 → predici 2025/26, mai il contrario).

**Modello VALORE**: proiezione fantamedia/punti col medesimo stack (o anche solo Marcel pesato, come in A — da decidere su backtest). Serve per il MILP e per l'edge = valore − prezzo previsto.

**Claude come valutatore (io), 3 ruoli precisi e misurabili**:
1. **Feature qualitative pre-asta** (pattern FeatLLM/IBM): per ogni giocatore rilevante genero scores strutturati su scala fissa — titolarità attesa 0-100, rischio infortunio, hype mediatico (il mercato sovrapaga l'hype!), upgrade/downgrade squadra-allenatore, rigorista sì/no/forse. Diventano colonne del dataset. Automatizzabile: batch su listone + guide asta 2026/27 come contesto.
2. **Cold start nuovi acquisti**: per chi non ha storico Serie A (es. arrivi estate 2026), stimo l'equivalente fantacalcistico da stats del campionato di provenienza + contesto squadra → il modello li tratta come tutti gli altri. È il buco dichiarato di ogni tool esistente.
3. **Revisione finale**: il modello sputa la lista, io la rileggo e segnalo assurdità con motivazione (il tuo "rivalorate poi da te in un secondo momento"). Ogni override è tracciato → a fine asta si misura chi aveva ragione, modello o me.
   - Calibrazione onesta: prima di fidarci, **mini-backtest** — genero i punteggi qualitativi "alla cieca" per la stagione 2024/25 (fingendo di essere ad agosto 2024) e verifichiamo se migliorano la predizione dei prezzi della vostra asta 2024. Se non aggiungono nulla, peso zero.

**Ottimizzatore**: MILP con PuLP/CBC — max Σ punti attesi, vincoli: Σ prezzo_previsto ≤ 500, 3P/8D/8C/6A. Con 500 giocatori si risolve in <1 secondo → si può rilanciare in continuazione. Output pre-asta: non UNA rosa ma **3-5 rose scenario** (es. "top attacco", "modificatore difesa", "equilibrata semitop") con per ognuna: obiettivi primari + alternative per slot + max bid per giocatore. La strategia "semitop" merita attenzione: i super-top sono sistematicamente sovraprezzati, i semitop prezzano vicino al valore (ExpectedFanta + il dato 33% attaccanti la supportano).

**Esecuzione live** (il tuo nice-to-have, promosso a componente chiave): interfaccia minimale dove durante l'asta segni ogni aggiudicazione (giocatore, prezzo, chi). Il tool tiene: crediti e **max bid di ogni avversario**, fattore inflazione, scarcity per ruolo/fascia, e a ogni acquisto **ri-esegue il MILP** con lo stato corrente → "hai perso Leao? con quei 40 crediti le migliori alternative ora sono X (max 35), Y (max 28); sposta 10 sul centrocampo". È esattamente il paper Maniezzo 2022 (Università di Bologna — unico paper al mondo su questo, 1 citazione: nicchia scoperta) + il pattern dei tool USA (FantasyPros inflation tracking, FanDraft max-bid per squadra).

**Pro**: usa davvero le vostre aste; incertezza quantificata (quantili → max bid sensati); gestisce i nuovi; Claude integrato in modo misurabile, non vibes; il live re-planner è il vero vantaggio competitivo il giorno dell'asta.
**Contro**: più lavoro (dataset da costruire, 3-4 componenti); TabPFN su ~500 righe con tante feature va comunque validato contro CatBoost e contro la Proposta A (che vive dentro B come baseline); rischio di fidarsi dei quantili su un campione piccolo.

---

## 6. Proposta C — "Il Simulatore": asta Monte Carlo multi-agente

*Filosofia: non predire il prezzo puntuale — simulare l'asta intera migliaia di volte e ragionare su distribuzioni.*

**Pipeline**: 7-9 bot avversari a regole, ognuno con: valutazioni private = prezzo di mercato previsto × rumore lognormale, allocazione budget per ruolo campionata dai profili reali (dalle vostre 2 aste si stimano i "caratteri": chi spende tutto sui top, chi fa il tirchio…), regola max-bid rigorosa. Si simula l'asta a chiamata completa 10.000 volte. Output: distribuzione dei prezzi finali per giocatore (con inflazione emergente!), probabilità di riuscire a chiudere ogni rosa-scenario della Proposta B, stress test delle strategie di nomination ("chiamare presto i top che non vuoi" — verificabile in silico).

**Cosa dice la letteratura**: MARL/MCTS "seri" per aste simultanee esistono (arXiv 2407.11715) ma non scalano a 25 slot × 500 giocatori e sono overkill dichiarato; il valore pratico è nelle **distribuzioni di prezzo emergenti** e nello stress-test, non nella policy ottima. Il paper Maniezzo conferma: spazio d'azione esponenziale → euristiche adattive, non RL esatto. Sulla tua domanda "rete neurale con backprop": per la predizione prezzo su 500-1000 righe una rete addestrata da zero è dominata sia dai GBDT che dai TFM (dati troppo pochi); per l'asta come gioco, il RL end-to-end è ricerca aperta — sconsigliato come via principale, interessante come esperimento dopo.

**Pro**: risponde alla domanda giusta ("che probabilità ho di portare a casa QUESTA rosa?"), cattura l'inflazione endogena che nessuna regressione vede, riusa i profili psicologici dei tuoi avversari reali (stessi amici ogni anno = modellabili!), niente da "allenare".
**Contro**: da solo non basta (gli servono i prezzi previsti di B come input), la qualità dipende da quanto sono realistici i bot, facile innamorarsi della simulazione e perdere tempo sul realismo dei dettagli.

---

## 7. Raccomandazione

**B come spina dorsale, A dentro B come baseline obbligatoria, C come modulo di validazione sopra B.** Non sono alternative, sono strati:

```
DATI (scraper listone+voti+medie piattaforme + vostre 2 aste)
  → VALORE (Marcel/CatBoost)          → PREZZO (TabPFN quantile vs CatBoost vs formula A)
  → punteggi qualitativi Claude (calibrati con backtest)
  → MILP multi-scenario (3-5 rose target, max bid)
  → [opz.] Simulatore Monte Carlo (probabilità di successo per scenario)
  → LIVE TOOL asta (tracking rivali, inflazione, re-run MILP a ogni acquisto)
```

Ordine di valore per il giorno dell'asta (se il tempo stringe): live tool con max bid disciplinati > lista prezzi/tier ben fatta > modello ML sofisticato > simulatore. Un modello mediocre + esecuzione disciplinata batte un modello perfetto + panic buy.

**Aspettative oneste**: il tetto di prevedibilità della fascia alta è ~50% (33% per gli attaccanti). Il bot non ti dirà chi farà 30 gol; ti impedirà di pagare 280 un attaccante da 220, ti farà notare che il mercato ignora un semitop da 25 crediti, e ti terrà i conti quando all'asta sale l'adrenalina. È così che si vince, ed è coerente col fatto che due anni fa ti è andata meglio dell'anno scorso: la varianza è enorme, il metodo serve a spostare la media.

---

## 8. Cosa serve da te (prima di qualsiasi piano)

1. **Le 2 aste passate**: in che formato le hai? (export/screenshot dall'app Leghe, Excel del banditore, foto?) Campi ideali: giocatore, prezzo, chi l'ha comprato; oro puro se c'è anche l'ordine di chiamata. Se l'asta era gestita su Leghe Fantacalcio, l'archivio lega dovrebbe avere le rose coi prezzi.
2. **Regolamento esatto lega 2026/27**: quanti partecipanti? "5 riserve" = rosa da 11+5=16 o rosa standard da 25? (cambia TUTTO: slot, replacement, budget per slot). Modificatore difesa attivo? Bonus custom (assist da fermo, porta imbattuta)? Ordine di chiamata come deciso?
3. **"MetaRday"**: nome esatto del sito/app che intendevi (non esiste nulla con quel nome — Fantametric? FantaLab? Fantaculo?).
4. Budget davvero 500 per tutti e stesse persone degli anni scorsi? (se sì, i profili avversari di C diventano molto più affidabili)

## 9. Fonti chiave
- Benchmark prevedibilità: https://fantacalcio.dev/report/fasce-oneste-2026-27
- Paper asta live: Maniezzo & Aspee Encina 2022, SN Oper. Res. Forum, DOI 10.1007/s43069-022-00160-w
- Pattern LLM+ML: IBM/ESPN arXiv 2111.02874 · FeatLLM arXiv 2404.09491
- TabPFN: https://github.com/PriorLabs/TabPFN · TabArena arXiv 2506.16791 · TabICL v2 · Google TabFM (research.google blog, 30/6/2026)
- Prezzi medi reali: https://www.fantacalcio-online.com/it/asta-fantacalcio-stima-prezzi · FantaMaster PMA · quotazioni storiche: fantacalcio.it/quotazioni-fantacalcio (export Excel, 2015/16→)
- Strategia/inflazione: SOS Fanta divisione budget · FantasyPros inflation · ExpectedFanta semitop
