# Indagine: realismo aste simulate vs reali

Reali filtrate: componenti==10, crediti 400-600, asta_anomala==0. Estive = periodo<=1 (AUDIT.md: periodo 2-3 possono includere riparazioni invernali).
- Aste reali estive: 16 (tutti i periodi: 55)
- Repliche sim mod: 6, no-mod: 6 (budget 500, 10 bot, quote 3P/8D/8C/6A, 250 hammer each)

## 1-2. Curva prezzo-rank (pct budget medio per rank)

| rank | reali estive | reali tutte | sim mod | sim no-mod |
|---|---|---|---|---|
| 1 | 0.3568 | 0.4158 | 0.4457 | 0.4457 |
| 2 | 0.3299 | 0.3775 | 0.4143 | 0.4143 |
| 3 | 0.3010 | 0.3430 | 0.3527 | 0.3527 |
| 5 | 0.2508 | 0.2951 | 0.2510 | 0.2510 |
| 10 | 0.1676 | 0.1892 | 0.1700 | 0.1700 |
| 15 | 0.1375 | 0.1434 | 0.1280 | 0.1280 |
| 20 | 0.1171 | 0.1179 | 0.1037 | 0.1037 |
| 30 | 0.0923 | 0.0885 | 0.0860 | 0.0860 |
| 40 | 0.0739 | 0.0705 | 0.0737 | 0.0737 |
| 60 | 0.0499 | 0.0470 | 0.0543 | 0.0543 |
| 80 | 0.0355 | 0.0330 | 0.0387 | 0.0387 |
| 120 | 0.0191 | 0.0175 | 0.0173 | 0.0173 |
| 160 | 0.0080 | 0.0076 | 0.0047 | 0.0047 |
| 200 | 0.0024 | 0.0023 | 0.0020 | 0.0020 |
| 250 | 0.0020 | 0.0020 | 0.0020 | 0.0020 |

### KS test per banda di rank (reali estive vs sim)

| banda | media reali | media sim_mod | KS mod | p mod | media sim_nomod | KS nomod | p nomod |
|---|---|---|---|---|---|---|---|
| 1-10 | 0.2516 | 0.2747 | 0.204 | 4.58e-02 | 0.2747 | 0.204 | 4.58e-02 |
| 11-30 | 0.1201 | 0.1103 | 0.301 | 1.78e-07 | 0.1103 | 0.301 | 1.78e-07 |
| 31-60 | 0.0674 | 0.0686 | 0.144 | 8.07e-03 | 0.0686 | 0.144 | 8.07e-03 |
| 61-120 | 0.0315 | 0.0329 | 0.138 | 8.11e-05 | 0.0329 | 0.138 | 8.11e-05 |
| 121-250 | 0.0063 | 0.0047 | 0.125 | 3.44e-08 | 0.0047 | 0.125 | 3.44e-08 |

## Top price e concentrazione

| metrica | reali estive | reali tutte | sim mod | sim no-mod |
|---|---|---|---|---|
| top1 pct medio | 0.3568 | 0.4158 | 0.4457 | 0.4457 |
| top1 min | 0.2460 | 0.2460 | 0.4100 | 0.4100 |
| top1 max | 0.4240 | 0.5700 | 0.4840 | 0.4840 |
| Gini prezzi (media per asta) | 0.6392 | 0.6611 | 0.6611 | 0.6611 |
| quota spesa top-10 giocatori | 0.2615 | 0.2956 | 0.2861 | 0.2861 |
| spesa totale / budget totale | 0.9637 | 0.9745 | 0.9599 | 0.9599 |

## 3. Spesa per ruolo (% della spesa totale, media per asta)

| ruolo | reali estive | reali tutte | sim mod | sim no-mod |
|---|---|---|---|---|
| P | 9.1% | 8.4% | 8.7% | 8.7% |
| D | 18.4% | 16.0% | 19.4% | 19.4% |
| C | 27.3% | 25.4% | 29.6% | 29.6% |
| A | 45.2% | 50.2% | 42.3% | 42.3% |

Nota: i log di tournament_mod e tournament sono byte-identici (md5 verificato): il modificatore incide solo sul punteggio stagionale, non sull'asta. Aste sim uniche = 6.

## Chi compra le fasce di rank (sim, 6 repliche)

- rank 1-3: C-stars_scrubs 5, C-panic 4, C-ancorato 4, C-tifoso 3, C-tirchio 1, C-enforcer 1
- rank 4-10: C-semitop 8, C-enforcer 8, C-tirchio 7, C-panic 5, C-tifoso 5, C-stars_scrubs 4, C-ancorato 3, B 2
- rank 11-30: C-stars_scrubs 18, C-ancorato 17, C-panic 16, A-rigido 13, B 12, C-enforcer 11, C-tirchio 11, C-semitop 10, C-tifoso 10, A-flessibile 2
- rank 31-60: A-rigido 45, A-flessibile 25, C-tifoso 18, C-enforcer 17, C-semitop 16, C-tirchio 15, B 15, C-ancorato 14, C-panic 8, C-stars_scrubs 7

## Top giocatori sim (mod), pct medio sulle 6 repliche

| player        |     mean |   max |   count |
|:--------------|---------:|------:|--------:|
| Martinez L.   | 0.438    | 0.484 |       6 |
| Lukaku        | 0.385667 | 0.482 |       6 |
| Dovbyk        | 0.303    | 0.446 |       6 |
| Vlahovic      | 0.283    | 0.376 |       6 |
| Thuram        | 0.247333 | 0.366 |       6 |
| Kvaratskhelia | 0.202    | 0.234 |       6 |
| Osimhen       | 0.189667 | 0.252 |       6 |
| Leao          | 0.185    | 0.242 |       6 |
| Pulisic       | 0.168    | 0.206 |       6 |
| Gimenez       | 0.156667 | 0.31  |       6 |
| Kolo Muani    | 0.152333 | 0.25  |       6 |
| Dybala        | 0.151667 | 0.422 |       6 |

Top1 per replica (mod): Lukaku 0.482, Martinez L. 0.484, Dovbyk 0.410, Martinez L. 0.442, Martinez L. 0.424, Martinez L. 0.432

## 4. Verdetto

Complessivamente le aste simulate sono in un range credibile: spesa/budget 0.960 vs 0.964 reale, Gini 0.661 vs 0.639, fascia 31-120 quasi sovrapposta. Ci si puo' fidare del torneo per confronti relativi tra bot, MA ci sono 3 distorsioni sistematiche:

1. **Top 1-3 TROPPO CARI** (non troppo economici): top1 sim 0.446 (range 0.41-0.48) vs reale estive 0.357 (Lautaro reale ~0.35-0.40). Il minimo sim (0.41) supera quasi il massimo reale (0.42). Comprati SOLO da bot C (18/18 top-3): stars_scrubs, panic, ancorato, tifoso si rilanciano a vicenda.
2. **Fascia 11-30 troppo economica**: 0.110 sim vs 0.120 reale, KS 0.301 (il piu' alto). E' l'altra faccia del punto 1: i C bruciano il budget sui top-3 e ai semitop restano meno crediti. Sistemare il tetto sui top corregge in gran parte anche questa.
3. **Coda 121-250 troppo economica**: 0.0047 vs 0.0063 (sim collassa a 1 credito, gli umani pagano 2-4 crediti anche in fondo). Minore, ma KS significativo.

Ruoli: sim sotto-spende in Attacco (42.3% vs 45.2% reale estive) e sovra-spende in C (+2.3pp) e D (+1pp).

**Manopole bot C da toccare**: (a) cap/haircut sul rilancio dei profili aggressivi (stars_scrubs, panic, ancorato) sopra ~0.35-0.40 del budget per singolo giocatore — target: top1 medio ~0.36, max ~0.42; (b) ridistribuire il budget-per-ruolo dei profili C spostando ~3pp da C/D verso A; (c) opzionale, floor di 2-3 crediti sulle chiamate di coda per i profili non-tirchio.

Caveat: aste reali estive filtrate = 16 (periodo<=1; 11 del 2021-22), quindi il confronto a livello di singolo giocatore 2024-25 non e' possibile, solo per fasce di rank. Con tutti i periodi (n=55, incluse riparazioni) il top1 reale sale a 0.416 e il gap si riduce, ma le riparazioni non sono il target giusto.
