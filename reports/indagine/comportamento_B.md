# Indagine: comportamento di B al tavolo

Fonti: `data/tournament_mod/{2024-25,2025-26}/main_1B_2A_7C` — 6 log di replica per stagione (1.500 lotti/stagione), `replicas.jsonl` (150 repliche/stagione), pack `data/packs/pack_{stagione}.pkl`.
Script: `scripts/indagine/indagine_comportamento_B.py` + `_extra.py`. ref_price del pack e' frazione del budget: convertito in crediti con x500.

## Q1 — Selettivita'

B rilancia su una **minoranza** dei lotti, come da design:

| Stagione | Lotti con >=1 rilancio di B | % | Rilanci totali | Media rilanci/lotto attivo |
|---|---|---|---|---|
| 2024-25 | 358 / 1.500 | **23,9%** | 1.063 | 2,97 |
| 2025-26 | 436 / 1.500 | **29,1%** | 1.253 | 2,87 |

Distribuzione rilanci per lotto attivo (2024-25): 1 rilancio 135, 2 → 81, 3 → 34, 4 → 40, 5 → 20, 6+ → 48 (coda max 19).
2025-26: 1 → 178, 2 → 105, 3 → 50, 4 → 28, 5 → 16, 6+ → 59 (coda max 28).
~60% dei lotti attivi si chiude con 1-2 rilanci di B (sonda bargain); le code lunghe (>=6 rilanci) sono il 13-14% dei lotti attivi = i veri target.

## Q2 — Nomination: drain vs riempitivi

I "thought" distinguono nettamente: `"fatevi male voi"` = drain, `"chiamo X basso"` = riempitivo.

| Stagione | Nomination B | Drain | Riempitivi | Drain comprati da B stesso | Riempitivi comprati da B |
|---|---|---|---|---|---|
| 2024-25 | 143 | 90 (**62,9%**) | 53 (37,1%) | 19/90 (21%) | 50/53 (94%) |
| 2025-26 | 118 | 107 (**90,7%**) | 11 (9,3%) | 41/107 (38%) | 11/11 (100%) |

Efficacia del drain (lotto aggiudicato sopra ref_price):

| | Drain sopra ref | Baseline tutti i lotti | Baseline lotti ref>=20 |
|---|---|---|---|
| 2024-25 | **62,2%** (56/90) | 33,3% | 41,2% |
| 2025-26 | **50,5%** (54/107) | 37,3% | 42,8% |

I drain (ref mediana 17-22 crediti) vengono pagati sopra ref piu' spesso della media anche a parita' di fascia (+21 punti nel 2024-25, +8 nel 2025-26): la tattica funziona, ma di meno nel 2025-26 — e li' il drain diventa piu' spesso un acquisto opportunistico (B si tiene il giocatore nel 38% dei casi se il prezzo resta basso). Premio medio prezzo/ref sui drain: 3,17x nel 2024-25 (mediana 1,19x — media gonfiata da ref piccoli), 1,11x nel 2025-26 (mediana 1,01x).

## Q3 — Spesa per ruolo vs guide

% del budget 500 (media 6 repliche loggate); tra parentesi la quota sullo SPESO effettivo:

| Ruolo | Guide | 2024-25 | 2025-26 |
|---|---|---|---|
| P | 6-9% | 5,5% (7,5%) | **13,7%** (14,6%) |
| D | 12-16%+mod | **15,9%** (21,7%) | **20,2%** (21,5%) |
| C | 24-30% | 15,7% (21,4%) | 16,4% (17,5%) |
| A | 50-64% | 36,3% (49,5%) | 43,6% (46,5%) |
| Speso tot | 100% | 367/500 (73%) | 469/500 (94%) |

- **Si', con modificatore attivo B sposta sulla difesa**: 15,9-20,2% del 500 (21,5-21,7% dello speso), sopra il tetto guide 16% in entrambe le stagioni una volta normalizzato sullo speso.
- Il centrocampo e' strutturalmente sotto-pesato rispetto alle guide (16-21% vs 24-30): B compra C solo a sconto.
- L'attacco in % del 500 sembra basso, ma sullo speso e' 46-50%, appena sotto il range guide: la differenza e' quasi tutta budget non speso, non una scelta di ruolo.
- Anomalia P 2025-26: 13,7% del 500, ben sopra le guide (portieri di fascia pagati pieni).

## Q4 — Perche' 85 di residuo nel 2024-25 e 38 nel 2025-26

Leftover B su 150 repliche: 2024-25 media **85**, mediana 83, IQR 35-126; 2025-26 media **38**, mediana 16, IQR 0-66.

Ipotesi "i prezzi crollano sotto i q50 e B compra tutto sotto cap" **confermata per il 2024-25**, con un pezzo in piu' per il 2025-26:

- Acquisti di B, prezzo pagato / q50: 2024-25 mediana **0,36x** (media 0,50x); 2025-26 mediana **0,47x** (media 0,59x). In entrambe le stagioni B compra sotto q50 nell'81-85% dei casi, ma nel 2024-25 lo sconto e' molto piu' profondo.
- Mercato (hammer con q50>10): sotto il q50 di B nel **64,1%** dei lotti nel 2024-25, 59,4% nel 2025-26; sotto q10 26,5% vs 35,1%.
- Il vero discriminante e' la coda alta: hammer sopra q90 **10,5%** nel 2024-25 vs **23,0%** nel 2025-26. Nel 2025-26 il tavolo strapaga i big piu' del doppio delle volte: B per vincere i target deve avvicinarsi ai suoi cap e brucia il budget (speso medio 469/500 vs 367/500; rapporto speso/somma-q50 della rosa 0,53-0,77 vs 0,45-0,63).
- In sintesi: nel 2024-25 i cap di B non sono quasi mai vincolanti (compra 25 slot a saldo e avanza ~85); nel 2025-26 il mercato dei big e' caldo, i cap diventano vincolanti e il residuo scende a ~38 (mediana 16, un quarto delle repliche chiude a 0).

## Q5 — Calibrazione in-asta (copertura [q10,q90] sui hammer con q50>10)

| Stagione | Dentro [q10,q90] | Sotto q10 | Sopra q90 |
|---|---|---|---|
| 2024-25 | **63,1%** (367/582) | 26,5% | 10,5% |
| 2025-26 | **42,0%** (287/684) | 35,1% | 23,0% |

Contro un nominale 80%, la copertura empirica al tavolo e' 63% (2024-25) e 42% (2025-26): gli intervalli di B sono **troppo stretti per i prezzi che emergono in questo tavolo**. Nel 2024-25 l'errore e' quasi tutto verso il basso (mercato deflazionato dai 7 C); nel 2025-26 sbaglia in entrambe le direzioni (35% crolli sotto q10, 23% fiammate sopra q90). Nota: e' una misura del tavolo simulato (1B+2A+7C), non della calibrazione sulle aste reali.
