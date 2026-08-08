# FantaOracle 🔮 — il modello che legge l'asta

*(EN: a machine-learning oracle for Italian fantasy football auctions — price + value models, MILP roster optimizer, live re-planning at the table, realistic opponent bots, full-season backtests on real votes, and a playable auction arena.)*

Un modello che impara da **centinaia di aste vere** e da 5 stagioni di voti, e all'asta del fantacalcio **vince il 75-91% dei campionati simulati** contro avversari realistici — poi ti lascia sedere al tavolo a sfidarlo. Predice quanto costerà ogni giocatore (con forchetta di incertezza), quanti punti farà, costruisce la rosa ottima e **ricalcola la strategia a ogni martelletto**. Config di riferimento: **10 partecipanti, 500 crediti, rosa 3P/8D/8C/6A, modificatore difesa, lineup 11 con max 3 cambi, soglie gol 66+6** (tutto in `config/league.yaml`).

## ⚡ Prova subito (demo inclusa, zero dati da scaricare)

```bash
pip install -r requirements.txt
# 1) GUARDA un'asta simulata: servi la cartella e apri il replay
python -m http.server 8899
# → http://localhost:8899/viz/replay.html?log=../demo/logs/asta_2025-26_esempio.jsonl

# 2) GIOCA tu contro i 9 bot (asta completa, pack demo incluso)
python scripts/f6_live_auction.py 2025-26
# → http://localhost:8899/viz/replay.html?live=http://localhost:8765
```

I dati grezzi (voti, quotazioni, prezzi reali) **non sono nel repo** e si rigenerano in locale con gli script inclusi: **leggi [DATA.md](DATA.md)** — spiega cosa è incluso (i derivati dei nostri modelli), cosa no e perché, e cosa cambia (la stagione post-asta richiede i voti).

---

## 1. Cosa fa, in una frase

Impara dai prezzi di **aste vere** (225 aste reali crowdsourced + storici piattaforme) e dai **voti di 5 stagioni**, predice quanto costerà ogni giocatore e quanti punti farà, costruisce la rosa ottima col budget, e **al tavolo ricalcola tutto a ogni martelletto** — poi dimostra di funzionare vincendo campionati simulati su stagioni realmente accadute.

## 2. Risultati (torneo finale, modelli aggiornati, modificatore attivo)

Win rate di B su 150 repliche (asta completa + stagione coi fantavoti veri + campionato H2H su 100 calendari; caso puro = 10%):

| Tavolo | 2024/25 | 2025/26 |
|---|---|---|
| B + 2 ragionieri + 7 profili umani | **90.4%** | **80.5%** |
| B + 9 profili umani | 83.2% | 75.6% |
| B + 4 ragionieri + 5 profili | 77.5% | 91.5% |

**Da dove viene il vantaggio** (misurato, non dichiarato): il modello valore vede i punti futuri meglio del mercato (correlazione 0.83-0.85 contro 0.48-0.57). Il controfattuale lo prova: B col valore "di mercato" al posto del suo crolla all'8.8% — sotto il caso. MILP e disciplina sono il sistema di consegna; il motore è il modello valore. Contro amici veri: aspettarsi 35-60%, annate d'oro sopra.

## 3. Architettura

```
DATI (data/raw → data/processed)          MODELLI (Fase 1)
  aste reali GruppoEsperti 225              PREZZO: TabPFN-2 + CatBoost ensemble,
  prezzi piattaforme 2018/19→25/26                  quantili q10/q50/q90 conformali
  voti+bonus 5 stagioni (59.306 righe)      VALORE: CatBoost → punti stagione
  quotazioni ufficiali Qt.I/FVM                     (rho 0.82 vs 0.41 del metodo classico)
  xG Understat, Transfermarkt
        │                                        │
        ▼                                        ▼
  MOTORE D'ASTA (src/fantabot/engine)  ←  BOT (src/fantabot/bots)
  chiamata a giro P→D→C→A, rilanci,        B: MILP titolari/panchina + quantili
  vincolo crediti/slot, event log             + prezzo-ombra + replanning live
  JSONL con "pensieri"                     A: ragioniere VORP (baseline onesta)
        │                                  C: 8 profili umani calibrati su aste vere
        ▼
  STAGIONE (src/fantabot/season)          INTERFACCE (viz/replay.html)
  38 giornate coi fantavoti reali,          TEATRO: replay animato di ogni asta
  lineup solo tra disponibili,              SEDIA: giochi tu contro i 9 bot
  modificatore difesa, H2H                  STAGIONE: scontri e voti giornata per giornata
```

## 4. I tre bot

**B — l'oracolo** (il modello forte). Pre-asta: modello prezzo distribuzionale (per ogni giocatore: mediana attesa e forchetta q10-q90, calibrata sulle aste reali) + modello valore + MILP che ottimizza titolari a peso pieno e panchina al 30%. Al tavolo: misura il "calore" del mercato confrontando i prezzi battuti con le proprie stime, ricalcola il piano a ogni evento rilevante, max bid = quantile alto + prezzo-ombra (quanto perdo se ripiego sull'alternativa), guardie anti-zavorra (mai >5 crediti su valore basso), caccia ai bargain veri, nomination-esca per drenare i budget altrui (efficacia misurata: +21 punti sul farli strapagare).

**A — il ragioniere** (baseline). Il metodo classico fatto bene: proiezione fantamedia → VORP → conversione crediti, lista rigida; variante "flessibile" con correzione inflazione. Lasciato volutamente com'è: è il metro per misurare se l'ML paga.

**C — gli amici** (avversari realistici). 8 profili dai pattern documentati: stars&scrubs, semitop, tifoso (+30% sui suoi), ancorato ai prezzi visti, panic buyer, tirchio, enforcer che alza per farti male, medio. Rumore calibrato sullo spread osservato dello stesso giocatore tra aste reali; tetto umano sul singolo (0.36-0.42 del budget, dalle aste vere); giocatore feticcio. Realismo verificato: curva prezzi-rank simulata vs 16 aste reali estive 10×500 sovrapposta dal rank 5 in giù, spesa e concentrazione fedeli.

## 5. I dati (tutti verificati, tutti gratis)

- **Aste reali**: forum GruppoEsperti "Progetto Prezzi Asta" — 225 aste complete deduplicate (2021/22, 2023/24, 2024/25), 51.113 acquisti con prezzo; 61 esattamente 10 squadre × 500.
- **Prezzi medi storici**: medie d'acquisto per configurazione di lega da archivi web pubblici, stagioni 2018/19 → 2025/26, inclusa la configurazione 10 squadre/500 crediti.
- **Voti**: fantacalcio.it, 5 stagioni × 38 giornate complete, voto+fantavoto+bonus dettagliati.
- **Quotazioni**: Qt.I/Qt.A/FVM ufficiali 2020/21→2025/26 + fanta.soccer per OGNI giornata (snapshot d'asta di inizio settembre).
- **Avanzate**: xG/xA Understat 7 stagioni, valori di mercato e anagrafiche Transfermarkt.
- Qualità garantita da **doppio audit avversariale** (round 1 trovò Lautaro corrotto da un omonimo e aste di riparazione dentro il target; round 2: PASS su tutto).

## 6. Validazione dei modelli (protocollo leave-future-out, zero senno di poi)

Allenato SOLO su stagioni precedenti, testato sulla successiva:
- Prezzo (test 2024/25): correlazione di rango 0.84, errore medio 13 crediti sui 50 più costosi, copertura forchetta 86%. VORP classico: 0.35. 
- Valore (test 2024/25 e 2025/26): rho 0.82 coi punti reali totali — contro 0.41 del metodo fantamedia classico e 0.45-0.55 del prezzo di mercato.
- Tetto di realismo noto (fonte fantacalcio.dev): la fascia top si conferma ~50% — il vantaggio sta nell'ordinamento e nei prezzi, non nell'indovinare i campioni.

## 7. Come si usa

Prerequisiti: Python 3.12 + `pip install -r requirements.txt`; per la webapp basta un server statico dalla radice del repo (`python -m http.server 8899`).

**Guardare un'asta simulata (replay)**
```bash
# apri nel browser:
# http://localhost:8899/viz/replay.html?log=../demo/logs/asta_2025-26_esempio.jsonl
```
Palco col giocatore chiamato, ticker dei rilanci col "pensiero" di ogni bot, barre budget, inflazione, scrubber, velocità 1-64x, riepilogo finale con le 10 rose.

**Giocare TU (modalità Sedia)**
```bash
python scripts/f6_live_auction.py 2025-26
```
poi apri `http://localhost:8899/viz/replay.html?live=http://localhost:8765`. Tavolo: tu + B + 2 ragionieri + 6 profili (`--no-b` per togliere B; `--porta N` se la 8765 è occupata da un run precedente — un processo = un'asta). L'asta si ferma quando tocca a te, senza timeout. Comandi: **+1 / +5 / importo / PASSO / NON LO VOGLIO** (passo automatico su quel giocatore fino al martelletto) / **AUTO** (delega singola); scorciatoie R e P; pannello suggerimenti richiudibile (mediana, tetto q90, max consigliato, termometro mercato, giudizio). Chiamata con ricerca, stemmi, filtro per squadra e ordinamento per valore/mediana/media aste reali.

**A fine asta: la stagione.** Coi dati rigenerati (vedi DATA.md), si simulano le 38 giornate coi fantavoti veri: classifica finale con la tua posizione, navigazione giornata per giornata, 5 scontri con punteggi e gol, click su uno scontro → le due formazioni coi voti di ognuno (subentri, assenti, bonus modificatore evidenziato), sparkline del tuo andamento. Col solo pack demo la stagione è disattivata (l'asta resta completa).

**Rilanciare i tornei / rigenerare tutto** (richiede i dati ricostruiti, vedi DATA.md)
```bash
python scripts/f1_train_price.py        # gara modelli prezzo con metriche
python scripts/f1_make_predictions.py   # predizioni B per stagione
python scripts/f2_build_packs.py        # pack stagione (ref mercato calibrato)
python scripts/f3_run_tournament.py NOME_CARTELLA   # torneo completo, riprendibile
python scripts/f5_counterfactuals.py    # esperimenti controfattuali
```

## 8. Documenti

- `PIANO.md` — il piano completo (con §11-bis riparazione, §11-ter agenda miglioramenti, §11-quater modulo statisticamente migliore)
- `BRAINSTORMING.md` — le 3 metodologie a confronto (origine del progetto)
- `reports/REPORT_FINALE.md` — verdetto + indagine sul 98% + fix list
- `reports/RAGIONAMENTI_UMANI.md` — 28 pattern dei fantallenatori veri (quantificati, con fonti) mappati su bot/feature/riparazione
- `reports/indagine/` — mining: comportamento di B, realismo aste, origine del vantaggio
- `reports/VERDETTO_*.md` — tabelle dei tre tornei (senza modificatore / con / coi fix)
- `DATA.md` — politica dati: cosa è incluso, cosa rigenerare e come
- `viz/README.md` — le tre modalità della webapp

## 9. Mappa del repository

```
fantabot/
├── config/league.yaml           # regole della lega (10×500, 3/8/8/6, modificatore...)
├── src/fantabot/
│   ├── engine/auction.py        # motore d'asta a eventi
│   ├── bots/                    # base + A + B + C
│   ├── season/                  # lineup, simulazione, dettaglio giornate
│   ├── modeling/                # Marcel, VORP
│   ├── optimizer.py             # MILP titolari/panchina (PuLP/CBC)
│   ├── tournament.py            # repliche parallele + aggregazione
│   └── verdict.py               # report verdetto
├── scripts/                     # f0b_* dati, f1_* modelli, f2 pack, f3 torneo,
│                                # f5 controfattuali, f6 asta live, indagine/
├── data/
│   ├── raw/ processed/ packs/   # dati grezzi → integrati → pack per stagione
│   ├── tournament*/             # risultati tornei (replicas, logs, summary)
│   └── live_logs/               # le TUE aste giocate (+ stagione json)
├── viz/replay.html              # teatro: replay + Sedia + stagione (un file)
├── reports/                     # tutti i documenti
└── tests/                       # smoke test (asta, stagione, torneo, live)
```

## 10. Onestà e limiti (letti prima di fidarsi)

1. Gli avversari C sono calibrati sulle ASTE reali ma non leggono le notizie: contro umani informati il vantaggio si riduce (per questo la forchetta realistica è 35-60%, non 80-90%).
2. I top 1-3 delle aste simulate costavano +25% del reale; corretto col tetto umano, ma i prezzi assoluti dei primissimi vanno letti con prudenza.
3. Il backtest usa il senno del "chi ha giocato davvero" per la disponibilità di formazione (identico per tutti — confronto pulito, punteggi assoluti leggermente ottimisti).
4. Le mie valutazioni qualitative (Claude) NON sono nei modelli del backtest: conosco l'esito di quelle stagioni, sarebbe barare. Entrano solo in avanti, sull'asta 2026/27.
5. Predire la fascia alta resta ~50%: il bot vince di disciplina, replacement e prezzi — non di profezie.

## 11. Roadmap

- **Asta reale 2026/27** (la ragione di tutto): pack sul listone uscito il 4/8, predizioni fresche, feature umane (rigoristi, infortuni al 1/9, titolarità), B2 coi giudizi Claude, e la Sedia come sparring in attesa dell'asta vera — dove il live tool ti fa da co-pilota.
- **Modulo riparazione** (progettato in PIANO §11-bis, ~1 giornata): svincoli, +50 crediti, asta di gennaio — saremo i primi a quantificare quanto incide davvero.
- Miglioramenti B in coda: modello titolarità dedicato, rollout Monte Carlo in-asta, valore distribuzionale con vincolo di varianza.
