# Indagine: da dove viene il vantaggio di B, e dove B perde

**Dati**: rose complete di TUTTE le 150 repliche x 2 stagioni (`main_1B_2A_7C`, tournament_mod), ricostruite ri-eseguendo le aste con gli stessi seed (motore deterministico; verifica esatta hammer-per-hammer sui 12 log salvati: 12/12 OK). Punti reali = somma fantavoti da `votes_by_g` del pack. Script in `scripts/indagine/`, CSV intermedi in `data/processed/indagine/`.

Glossario: `value` = punti stagionali predetti dal CatBoost di B; `q50` = prezzo predetto (crediti); `ref` = prezzo di riferimento mercato (ref_price x 500); `raw` = somma fantavoti reali dei 25 acquistati; `lineup` = total_points della simulazione stagione (11 titolari, mod difesa) usato dall'H2H.

---

## Q1. Punti-per-credito per bot e decomposizione del vantaggio

Media su 150 repliche (pts raw / crediti spesi):

| 2024-25 | pts | spesi | pts/cr | | 2025-26 | pts | spesi | pts/cr |
|---|---|---|---|---|---|---|---|---|
| **B** | **4983** | 415 | **11.99** | | A-flessibile | **4211** | 435 | **9.69** |
| A-flessibile | 3815 | 420 | 9.08 | | **B** | 4000 | 462 | 8.66 |
| A-rigido | 3797 | 500 | 7.59 | | C-stars_scrubs | 3953 | 487 | 8.13 |
| C-stars_scrubs | 3672 | 498 | 7.37 | | A-rigido | 3919 | 500 | 7.84 |
| media C | ~3406 | ~499 | ~6.9 | | media C | ~3606 | ~491 | ~7.3 |

Decomposizione esatta (log, vs media geometrica dei 9 rivali): `pts/spesi = (pts/ref_rosa) x (ref_rosa/spesi)` = value-pick x price-discipline.

- **2024-25: vantaggio +66% in pts/credito = 55% value-pick + 45% price-discipline.** B compra 503 crediti di valore-mercato pagandoli 415 (paga/ref 0.82 vs 0.93 dei rivali) e quei crediti rendono 9.9 pts/cr-ref vs 5.3-6.7 dei C.
- **2025-26: vantaggio +13% = 40% value-pick + 60% discipline.** Il value-pick edge e' quasi evaporato (8.2 pts/cr-ref vs 6.9-7.4 dei C); resta solo la disciplina (paga/ref 0.95 vs 0.96). A-flessibile supera B su entrambe le curve.

## Q2. Le "gemme" di B (frequenza su 150 repliche)

**2024-25** — top-10: Angelino (99%, pagato 2.8, ref 2.1, real **240**), Fazzini (99%, 1.0, ref 1, real 139), Ederson (99%, 20.8, ref 19, real 233), Ndoye (99%, 1.0, real 213), Martin (96%, 1.5, real 227), Milinkovic-Savic P (94%, 24.4, ref 4.6, real 201), Bellanova (90%, 25.4, real 219), Di Lorenzo (87%, 47.3, real 235), Zortea (81%, 1.4, real 231), De Roon (77%, 1.0, real 235). Pattern: **titolari fissi (35-38 presenze) prezzati 1-3 crediti dal mercato**. In media 8.6 acquisti da 1 credito = 1657 pts raw a replica.

**Leakage-check: nessuna assurdita'.** Il value sbaglia in entrambe le direzioni (Fazzini 228 predetto vs 139 reale; Angelino 186 vs 240; Dallinga 180 vs 147; Soule' 234 vs 162); rank medio dei top-10: 36 per value, 61 per punti reali, 227 per ref. E' il pattern "titolare sicuro sottoprezzato", non una copia del futuro. (La prova definitiva resta il controllo del train set pre-asta, fuori da questi dati.)

**2025-26** — meta' gemme vere: Kalulu (99%, pagato 11, real 235), Solet (97%, 8.6, real 217), Vlasic (95%, 22, real 246), Pavlovic (89%, 8.5, real 225), Maignan (85%, 41, real 200). **Meta' zavorra comprata CONTRO il proprio modello**: Bailey (100%, value 98 -> real 28), Tavares (100%, value 128 -> 127 ma 22 presenze), Jashari (95%, value 95 -> 69), Estupinan (91%, value 87 -> 80), Calhanoglu (87%, pagato 50, real 168), e in attacco Lukaku (88/150, pagato 48, **value 39.5 -> real 9.5**), Gimenez (88, value 94 -> 83), Lookman (70, value 100 -> 64). B mette in rosa 2.0 giocatori sotto 50 pts reali a replica (0.5 nel 2024).

## Q3. Le 79 repliche perse nel 2025-26 (B vince 71/150 = 47%)

- **Chi vince**: A-flessibile 25, C-stars_scrubs 22, C-semitop 14, C-ancorato 13, altri 5.
- **Non e' questione di prezzi pagati**: B nelle perse paga MENO (paga/q50 0.589 vs 0.646 nelle vinte); possesso e prezzo dei suoi top-10 target quasi identici (es. Calhanoglu 87% vs 86%, ~50 crediti in entrambe).
- **E' la varianza della sua rosa + la rosa del vincitore**: B raw 3890 nelle perse vs 4122 nelle vinte; lineup 2567 vs 2712. Il vincitore fa 2637 (+70 su B); nel 14% delle perse B ha piu' punti del vincitore (rumore calendari h2h).
- **I giocatori chiave del vincitore che B non ha mai**: Krstovic (nel vincitore in 25/79 perse; B lo possiede 1/150), Da Cunha (23; B 2/150), Adams (25; B 0), Lauriente' (19; B 15), Bonny (25; B 0), Falcone (24; B 0), Palestra (17; B 0), Douvikas (15; B **6/150 nonostante value 241, il suo miglior attaccante predetto**). Sono i breakout di fascia 3-33 crediti. A-flessibile li ha quasi sempre: Adams 149/150, Bonny 149, Krstovic 143, Da Cunha 133, Falcone 132.
- **Meccanismo**: il modello prezzo di B e' scalibrato nel 2025-26. Sottostima i breakout (Douvikas q50 12 vs ref 21.5, Da Cunha 11 vs 18, Bonny 2 vs 20, Adams 15 vs 23) -> i cap d'offerta (q50x1.1 / q90) restano sotto le offerte dei rivali -> B li perde sempre. Sovrastima i nomi in declino (Lukaku q50 96 vs ref 43, Gimenez 71, Lookman 95) -> per B sembrano bargain -> li vince lui. In piu' i q10 gonfiati sul low-cost fanno scattare la bargain-rule sulla spazzatura: 38% degli acquisti di B nel 2025 arriva da bid "bargain" (31% nel 2024, dai log).

## Q4. Il divario rho spiega 98% -> 46%? NO da solo — conta il margine punti

- rho spearman(value, real): **0.83 (2024) / 0.85 (2025)**; rho(ref, real): **0.48 / 0.57** (pool completo). In fascia alta (ref>=5cr) il divario si ALLARGA: 0.68 vs 0.25 (2024), 0.72 vs **-0.02** (2025). Quindi il ranking del modello non e' peggiorato e il mercato in fascia alta e' persino piu' cieco: il rho NON spiega il crollo.
- Cio' che lo spiega al 100% e' il **margine lineup di B sul miglior rivale**: +214 pts (>0 nel 99% delle repliche) nel 2024 -> **+10 pts (>0 nel 54%)** nel 2025. Il team con piu' punti-rosa vince l'h2h nel 100%/86% dei casi; corr(points, win) pooled 0.67/0.60. La curva pooled margine->win riproduce i win rate osservati: atteso 0.974 vs reale 0.982 (2024), **atteso 0.471 vs reale 0.463 (2025)**. Win rate = f(margine), fine della storia.
- Il margine crolla perche' crolla il RAW: margine raw +980 (2024) -> **-301** (2025). B da 4983 a 4000 (-983: attacco -561 con presenze medie 17.2/giocatore, gemme da 1 credito da 8.6 slot/1657 pts a 3.5/434); il miglior rivale (A-fless) da 4003 a 4300. B resta a 46% solo grazie alla migliore conversione raw->lineup (0.659 vs 0.607 di A-fless, che spalma i suoi 4211 raw su troppi giocatori che non schiera).
- Perche' il rho alto non basta: il rho e' ranking sull'intero pool; il margine dipende da (a) quanti punti extra il pool offre nelle fasce che B riesce a comprare, (b) dalla calibrazione dei PREZZI (q50) che decide che cosa B vince davvero al tavolo. Nel 2025 (a) l'attacco era un campo minato che il value model vedeva (Lukaku 39, Gimenez 94) ma i 6 slot A vanno riempiti comunque, e (b) i cap sbagliati hanno regalato i breakout ai rivali e i flop a B.

## Azioni concrete

1. **Ricalibrare il modello prezzo 2025-26** (q50/q10): errore sistematico paga/q50 = 0.61 in entrambe le stagioni, ma nel 2025 e' distorto per segmento (alto sui nomi, basso sui breakout). E' il collo di bottiglia, non il CatBoost dei punti.
2. **Bloccare gli acquisti con value < ~130**: mai spendere >5 crediti su giocatori che il proprio modello considera flop (Lukaku 48 crediti per value 39.5 e' indifendibile); meglio 1-credito ad alte presenze.
3. **Bargain-rule con q10 credibili** (cap = min(q10, ref x k)): oggi compra junk per colpa dei q10 gonfiati.
4. **Rubare la pagina ad A-flessibile**: lista VORP presence-weighted in fascia 6-30 crediti (Adams/Bonny/Krstovic/Da Cunha/Falcone). Con un rho di appena 0.42 fa 4211 raw: e' li' che vive il valore del 2025.
