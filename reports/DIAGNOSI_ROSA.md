# Diagnosi: perché la rosa proposta era "piatta" — e cosa cambia

Data: 4 settembre 2026. Innesco: la rosa target 2026/27 (Mandas/Falcone/Okoye; Dimarco + difesa forte; Zaccagni/Frattesi/Politano/Taylor; Colombo/Pellegrino/Laurienté/Santos) giudicata non competitiva dall'utente.

## Evidenze misurate

1. **Compressione del modello valore.** CatBoost addestrato sulla somma dei fantavoti stagionali regredisce verso la media: nel backtest 2025/26 il decile migliore vale 232 punti reali contro 196 predetti, i top-25 242 contro 204 (−16%), gli attaccanti top-8 251 contro 200 (−20%); i decili peggiori sono sovrastimati del 38%. Con valori così schiacciati il rapporto punti/credito dei campioni crolla e l'ottimizzatore compra 25 titolari economici.
2. **Obiettivo sbagliato per il formato.** L'ottimizzatore massimizzava i punti attesi, ma il campionato testa a testa con fasce gol (66, +6) premia i picchi. Test sui voti reali 2025/26 con le regole della lega (modificatore 7→+5, porta inviolata +1): la rosa STELLE fa 2783 punti (sd per giornata 8.3) e vince il 34% dei campionati; la rosa PIANO B fa 2892 punti (sd 6.5) e vince... il 34%. Cento punti di media in più non comprano nulla. In più la rosa B costava 586 crediti a prezzi di mercato: non era nemmeno acquistabile.
3. **Benchmark troppo facile.** Il torneo dove B vinceva l'80-90% era contro bot che comprano a prezzo di mercato con rumore senza ottimizzare. Contro rose costruite bene è alla pari.
4. **Regole non esatte.** Fascia 7 valeva +6 invece di +5 e mancava il +1 porta inviolata: per questo i portieri scelti erano quelli delle squadre deboli (voti alti da parate, poche porte inviolate: Okoye 10 e Falcone 9 clean sheet contro 18-19 dei migliori, circa −9 punti a stagione).

La ricerca esterna conferma la parte "difensiva" della logica (attaccanti meno prevedibili: 33% di conferma della fascia top; costo per punto 1.06 in attacco contro 0.72 in difesa; modificatore difesa +38/57 punti a stagione) ma anche gli errori concreti: Zaccagni (fantamedia 6.00 su 26 presenze nel 2025/26) pagato 43, Mandas senza presenze nel 2025/26, zero upside in attacco.

## Cosa è stato cambiato

- `src/fantabot/rules.py`: regole della lega in un punto solo (fasce, clean sheet dai gol subiti reali, 3 cambi). Usate dal simulatore, dai pack e dal target del modello valore.
- `src/fantabot/optimizer.py`: il MILP sceglie il modulo (7 classic) invece di assumere il 4-4-2; i giocatori già posseduti sono fissati a prezzo zero; l'obiettivo può includere l'upside (`lam`) e un vincolo di spesa sull'attacco.
- `scripts/f1_make_predictions.py`: modello valore a quantili (mediana e q75) più modello presenze; la mediana è ricalibrata con regressione isotonica su predizioni out-of-fold, che corregge la compressione misurata.
- `src/fantabot/montecarlo.py` + `scripts/f12_choose_objective.py`: le rose candidate vengono giocate centinaia di volte contro archetipi realistici a prezzo di mercato e si sceglie la combinazione (upside, quota attacco) che massimizza la probabilità di arrivare primi. Include il rumore di stima per simulazione: senza, l'ottimizzatore vinceva il 100% delle volte per costruzione.
- `BBot`/Copilota: usano l'obiettivo scelto dal Monte Carlo nei ricalcoli al tavolo.

## Criterio di accettazione

Sui voti reali 2025/26 e 2024/25, a 500 crediti di mercato, la nuova rosa deve avere probabilità di vittoria almeno pari a STELLE e GUIDA (test archetipi) e costare al massimo 500.
