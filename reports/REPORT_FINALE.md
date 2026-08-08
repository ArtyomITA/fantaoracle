# FantaBot — Report finale: verdetto, indagine sul 98%, miglioramenti

> 7-8 agosto 2026. Torneo su stagioni reali 2024/25 e 2025/26, asta il giorno dopo la chiusura del mercato, regole della lega: 10 partecipanti, 500 crediti, 3P/8D/8C/6A, **modificatore difesa attivo**, lineup 11 con max 3 cambi, soglie gol 66+6.

## 1. Verdetto ufficiale (con modificatore difesa — il vostro formato)

Win rate di B = quota di repliche in cui vince il campionato H2H (100 calendari per replica). Baseline casuale a 10 squadre: 10%.

| Composizione tavolo | 2024/25 | 2025/26 |
|---|---|---|
| 1B + 2A + 7C (principale, 150 repliche) | **98.2%** | **46.3%** |
| 1B + 9C (50 repliche) | 97.4% | 38.4% |
| 1B + 4A + 5C (50 repliche) | 93.3% | 72.5% |

Senza modificatore (ablazione): 98.3 / 96.7 / 93.0 e 27.9 / 25.8 / 48.9. **Il modificatore AIUTA B** (+18pp sul 2025/26 principale): il suo modello prezza bene i difensori da voto alto e sposta correttamente la spesa sulla difesa (21.7% dello speso vs tetto guide 16%).

**Criterio dichiarato superato in tutte le 6 configurazioni.** Aspettativa realistica contro umani veri: zona 35-60%, con annate d'oro sopra il 90% quando il mercato sottovaluta sistematicamente (2024/25) — su un tavolo dove il caso vale 10%.

## 2. Indagine sul "98% strano" — risolta

### Controfattuali
- **E1 — B col valore implicito nel mercato** (al posto del suo CatBoost): crolla a **8.8%** (2024/25) e **5.5%** (2025/26), sotto il caso. → MILP, quantili, disciplina da soli valgono ZERO. **L'edge è al 100% il modello valore** (rho 0.83-0.85 coi punti reali vs 0.48-0.57 del mercato; sui giocatori ≥5 crediti il divario si allarga: 0.68-0.72 vs 0.25/-0.02).
- **E2 — avversari tutti "informati"** (mercato + euristica fantamedia): B sale a 99.3%/92.3%. L'euristica classica è PEGGIORE del mercato puro: il mercato è già l'aggregato dell'intelligenza collettiva; renderlo più prevedibile aiuta B.

### Perché 98% in un anno e 46% nell'altro
Ricostruite le rose di tutte le 300 repliche (ri-esecuzione deterministica verificata):
- 2024/25: B fa **11.99 punti/credito vs 6.3-9.1** dei rivali (+66%) = 55% scelte migliori + 45% prezzi migliori (paga 0.82× il riferimento vs 0.93 dei rivali). Gemme: titolari veri a 1-3 crediti che il mercato ignorava (Angelino 2.8cr → 240 punti reali, comprato nel 99% delle repliche; Ndoye, De Roon, Martin, Zortea). 8.6 acquisti da 1 credito = 1657 punti/replica.
- 2025/26: **A-flessibile fa più punti/credito di B** (9.69 vs 8.66); B tiene il 46% solo per la migliore conversione rosa→lineup. Causa radice: **modello prezzo scalibrato su quell'anno** — q50 sottostima i breakout (Douvikas q50 12 vs mercato 21.5 → B sempre superato sulle gemme vere: Krstovic 1/150 repliche, Adams e Bonny 0/150, che A-flessibile ha quasi sempre) e sovrastima i nomi in caduta (Lukaku q50 96 vs mercato 43 → B compra i flop: Bailey e Lukaku zavorra nell'88-100% delle repliche). La regola bargain compra spazzatura (q10 gonfiati: 38% degli acquisti).
- La meccanica torna al decimale: la curva margine-lineup → win rate prevede 97.4%/47.1% vs osservato 98.2%/46.3%.

### Leakage check
Il valore sbaglia in entrambe le direzioni (Fazzini predetto 228 → 139 reale; Angelino 186 → 240) e il rank-test sui top10 dà value 36 vs real 61: nessuna evidenza di contaminazione. Protocollo: feature audit-passed, train solo su stagioni precedenti.

### Realismo delle aste simulate (vs 16 aste reali estive 10×500)
Fascia media e spesa complessiva fedeli (spesa/budget 0.960 vs 0.964, Gini 0.661 vs 0.639, curva sovrapposta dal rank 5 in giù). **Distorsione al vertice: i top 1-3 simulati costano +25%** (0.446 vs 0.357 del budget) — colpa dei profili C aggressivi senza tetto; di conseguenza fascia 11-30 troppo economica (KS p=1.8e-7). Comprati solo da bot C (18/18). Correzioni identificate: cap per-giocatore ~0.36-0.40 nei profili aggressivi, +3pp budget C dall'area C/D verso l'attacco. Nota: il torneo resta valido per il CONFRONTO tra bot (distorsione simmetrica), ma i prezzi assoluti dei top vanno letti col -25%.

### Comportamento di B al tavolo (conferme)
Rilancia sul 24-29% dei lotti (selettivo come da design); nomination-esca efficaci (drenati strapagati nel 62% vs 41% di fascia comparabile); residui alti nel 2024/25 (85 medi) perché il mercato crollava sotto i suoi cap (paga 0.36× q50 mediano); copertura in-asta dei suoi intervalli 63%/42% vs 80% nominale → **quantili troppo stretti al tavolo** (i bound del market-heat [0.8, 1.6] vanno allargati in basso e la conformal va rifatta sulla distribuzione per-tavolo).

## 3. Miglioramenti (motivati dai numeri)

### B — in ordine di ROI atteso
1. **Ricalibrare il modello prezzo** (il colpevole del 2025/26): conformal per-stagione più larga, bound heat [0.5, 1.8], target ensemble estive+wayback; obiettivo copertura ≥75% al tavolo. *(dal mining: paga/q50 0.61 sistematico)*
2. **Guardie anti-zavorra**: mai >5 crediti con valore basso; cap bargain = min(q10, ref×0.8). *(Bailey/Lukaku 2025/26)*
3. **Modello titolarità dedicato** — collo di bottiglia universale (nostro mining + letteratura + guide umane). Feature: minuti 3 stagioni, età, concorrenti di ruolo, probabili formazioni pre-asta.
4. **Max bid da prezzo-ombra MILP** (drop-off verso l'alternativa) al posto di q90 fisso.
5. **Rollout Monte Carlo in-asta** (C dentro B — additivo, spegnibile a flag): P(chiudo la rosa target | pago X).
6. Feature umane dal censimento (reports/RAGIONAMENTI_UMANI.md): rigorista, infortunio/CdA alla data d'asta, delta fantamedia yoy, coppia portieri nel MILP.
7. B2 con giudizi Claude: SOLO prospettico 2026/27 (contaminazione backtest).

### C — fedeltà, non forza
Cap top price 0.36-0.40; +3pp budget verso attacco; feticcio per-bot; sunk-cost alla riparazione; sigma per fascia rifittata sulle 61 aste reali.

### A — resta il baseline onesto
Solo normalizzazione lista al budget. Nota: A-flessibile si è rivelato fortissimo nel 2025/26 (9.69 punti/credito) — VORP + inflazione è un avversario serio, tenerlo com'è rende il torneo credibile.

## 4. Prossimi passi proposti
1. Fix calibrazione prezzo B + guardie (miglioramento 1-2) → ri-torneo → misurare il recupero sul 2025/26.
2. Modulo riparazione (PIANO §11-bis) coi comportamenti umani censiti → primo dato quantitativo mai prodotto su "quanto incide la riparazione".
3. Preparazione asta reale 2026/27: predizioni sul listone uscito il 4/8, feature umane, B2 con i miei giudizi, modalità Sedia per esercitarti contro i bot.
