# Rose candidate (compito S)

- 31 rose simulate, 40 scenari ciascuna, scenari e calendario COMUNI (seme 1001), 9 avversari archetipo.
- Ordinamento: punti medi a stagione. P(1) riportato ma NON usato per ordinare (errore standard ~8 punti percentuali con 40 scenari).
- `serio` = differenza di punti medi rispetto a R01 entro 1 errore standard appaiato o migliore (criterio scritto prima, `criteri_prima_S.md`).

| # | rosa | nota | modulo | costo q50 | att% | value | indisp | note neg | punti medi | sd | diff vs R01 | +-SE | serio | P(1) | +-SE | bomber |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | R25 | bench_weight 0.45 (modulo non forzabile: ripiego) | 3-4-3 | 500 | 44% | 5544 | 2 | 4 | 3210 | 76 | +11 | 8 | si | 57% | 8% | Malen |
| 2 | R15 | escluso/i Zaccagni | 3-4-3 | 500 | 44% | 5542 | 1 | 3 | 3203 | 78 | +4 | 8 | si | 60% | 8% | Malen |
| 3 | R01 | riferimento: lam 0.5, attacco 35-50% | 3-4-3 | 500 | 44% | 5524 | 1 | 4 | 3199 | 71 | +0 | 0 | si | 52% | 8% | Malen |
| 4 | R04 | bomber imposto Raimondo | 3-4-3 | 500 | 44% | 5524 | 1 | 4 | 3199 | 71 | +0 | 0 | si | 52% | 8% | Malen |
| 5 | R06 | bomber imposto Colombo | 3-4-3 | 500 | 44% | 5524 | 1 | 4 | 3199 | 71 | +0 | 0 | si | 52% | 8% | Malen |
| 6 | R11 | lam 1 (tutto peso all'upside) | 3-4-3 | 500 | 44% | 5524 | 1 | 4 | 3199 | 71 | +0 | 0 | si | 52% | 8% | Malen |
| 7 | R20 | portiere titolare imposto Mandas | 3-4-3 | 500 | 44% | 5524 | 1 | 4 | 3199 | 71 | +0 | 0 | si | 52% | 8% | Malen |
| 8 | R24 | bench_weight 0.15 (modulo non forzabile: ripiego) | 3-4-3 | 500 | 44% | 5524 | 1 | 4 | 3199 | 71 | +0 | 0 | si | 52% | 8% | Malen |
| 9 | R27 | bench_weight 0.45 + lam 1 | 3-4-3 | 500 | 44% | 5524 | 1 | 4 | 3199 | 71 | +0 | 0 | si | 52% | 8% | Malen |
| 10 | R22 | portiere titolare imposto Vicario | 3-4-3 | 500 | 43% | 5488 | 1 | 4 | 3199 | 94 | -0 | 11 | si | 50% | 8% | Malen |
| 11 | R10 | lam 0 (nessun peso all'upside) | 3-4-3 | 500 | 43% | 5528 | 1 | 4 | 3194 | 69 | -6 | 8 | si | 45% | 8% | Malen |
| 12 | R26 | bench_weight 0.15 + lam 0 | 3-4-3 | 500 | 43% | 5528 | 1 | 4 | 3194 | 69 | -6 | 8 | si | 45% | 8% | Malen |
| 13 | R09 | attacco 50-65% | 3-4-3 | 500 | 50% | 5478 | 1 | 4 | 3191 | 89 | -9 | 13 | si | 48% | 8% | Malen |
| 14 | R05 | bomber imposto De Ketelaere | 3-4-3 | 500 | 49% | 5503 | 1 | 4 | 3184 | 83 | -16 | 10 | no | 45% | 8% | Malen |
| 15 | R12 | escluso/i Colombo | 3-4-3 | 500 | 45% | 5504 | 1 | 3 | 3183 | 87 | -17 | 9 | no | 48% | 8% | Malen |
| 16 | R02 | bomber imposto Ramos G. | 3-4-3 | 499 | 38% | 5569 | 1 | 4 | 3182 | 82 | -18 | 10 | no | 45% | 8% | Ramos G. |
| 17 | R14 | escluso/i Vlasic | 3-4-3 | 500 | 44% | 5533 | 1 | 3 | 3180 | 68 | -20 | 7 | no | 38% | 8% | Malen |
| 18 | R07 | bomber imposto Laurientè | 3-4-3 | 500 | 47% | 5534 | 1 | 4 | 3179 | 81 | -20 | 10 | no | 48% | 8% | Malen |
| 19 | R13 | escluso/i Raimondo | 3-4-3 | 500 | 45% | 5487 | 1 | 4 | 3177 | 86 | -22 | 9 | no | 40% | 8% | Malen |
| 20 | R23 | portiere titolare imposto Maignan | 3-4-3 | 500 | 43% | 5494 | 2 | 4 | 3177 | 85 | -22 | 12 | no | 45% | 8% | Malen |
| 21 | R08 | attacco 20-35% | 3-4-3 | 498 | 26% | 5628 | 1 | 4 | 3176 | 84 | -23 | 10 | no | 42% | 8% | Raimondo |
| 22 | R30 | prezzi di mercato, nessun vincolo, lam 1 | 3-4-3 | 432 | 25% | 5413 | 1 | 4 | 3173 | 100 | -26 | 11 | no | 42% | 8% | Raimondo |
| 23 | R03 | bomber imposto Martinez L. | 3-4-3 | 500 | 44% | 5504 | 1 | 4 | 3164 | 75 | -36 | 6 | no | 38% | 8% | Martinez L. |
| 24 | R29 | prezzi di mercato, nessun vincolo d'attacco | 3-4-3 | 420 | 25% | 5549 | 1 | 4 | 3162 | 78 | -37 | 9 | no | 42% | 8% | Raimondo |
| 25 | R19 | due bomber Malen + Kolo Muani (attacco 35-80%) | 3-4-3 | 500 | 59% | 5315 | 1 | 2 | 3159 | 107 | -40 | 16 | no | 40% | 8% | Malen |
| 26 | R17 | due bomber Malen + Ramos G. (attacco 35-80%) | 3-4-3 | 500 | 61% | 5290 | 0 | 2 | 3159 | 96 | -40 | 16 | no | 40% | 8% | Malen |
| 27 | R21 | portiere titolare imposto Svilar | 3-4-3 | 500 | 38% | 5505 | 1 | 4 | 3157 | 79 | -42 | 8 | no | 38% | 8% | Ramos G. |
| 28 | R15T | escluso/i Colombo, Raimondo, Vlasic, Zaccagni | 3-4-3 | 499 | 50% | 5476 | 1 | 1 | 3148 | 86 | -51 | 8 | no | 30% | 7% | Malen |
| 29 | R18 | due bomber Malen + Hojlund (attacco 35-80%) | 3-4-3 | 500 | 59% | 5322 | 1 | 3 | 3142 | 95 | -58 | 15 | no | 30% | 7% | Malen |
| 30 | R16 | due bomber Malen + Martinez L. (attacco 35-80%) | 3-4-3 | 500 | 67% | 5214 | 0 | 1 | 3141 | 98 | -58 | 16 | no | 38% | 8% | Malen |
| 31 | R28 | prezzi di mercato, attacco 35-50% | 3-4-3 | 431 | 34% | 5497 | 1 | 4 | 3138 | 88 | -62 | 12 | no | 25% | 7% | Raimondo |

## Titolari (tutte le rose, ordine della tabella)

- **R25** (3-4-3): Mandas(P) | Kalulu(D) | Solet(D) | Valeri(D) | Zaccagni(C) | Vlasic(C) | Ekkelenkamp(C) | Frattesi(C) | Malen(A) | Raimondo(A) | Colombo(A)
- **R15** (3-4-3): Mandas(P) | Kalulu(D) | Pavlovic(D) | Solet(D) | Ederson D.S.(C) | Vlasic(C) | Ekkelenkamp(C) | Frattesi(C) | Malen(A) | Raimondo(A) | Colombo(A)
- **R01** (3-4-3): Mandas(P) | Kalulu(D) | Pavlovic(D) | Solet(D) | Zaccagni(C) | Vlasic(C) | Ekkelenkamp(C) | Frattesi(C) | Malen(A) | Raimondo(A) | Colombo(A)
- **R04** (3-4-3): Mandas(P) | Kalulu(D) | Pavlovic(D) | Solet(D) | Zaccagni(C) | Vlasic(C) | Ekkelenkamp(C) | Frattesi(C) | Malen(A) | Raimondo(A) | Colombo(A)
- **R06** (3-4-3): Mandas(P) | Kalulu(D) | Pavlovic(D) | Solet(D) | Zaccagni(C) | Vlasic(C) | Ekkelenkamp(C) | Frattesi(C) | Malen(A) | Raimondo(A) | Colombo(A)
- **R11** (3-4-3): Mandas(P) | Kalulu(D) | Pavlovic(D) | Solet(D) | Zaccagni(C) | Vlasic(C) | Ekkelenkamp(C) | Frattesi(C) | Malen(A) | Raimondo(A) | Colombo(A)
- **R20** (3-4-3): Mandas(P) | Kalulu(D) | Pavlovic(D) | Solet(D) | Zaccagni(C) | Vlasic(C) | Ekkelenkamp(C) | Frattesi(C) | Malen(A) | Raimondo(A) | Colombo(A)
- **R24** (3-4-3): Mandas(P) | Kalulu(D) | Pavlovic(D) | Solet(D) | Zaccagni(C) | Vlasic(C) | Ekkelenkamp(C) | Frattesi(C) | Malen(A) | Raimondo(A) | Colombo(A)
- **R27** (3-4-3): Mandas(P) | Kalulu(D) | Pavlovic(D) | Solet(D) | Zaccagni(C) | Vlasic(C) | Ekkelenkamp(C) | Frattesi(C) | Malen(A) | Raimondo(A) | Colombo(A)
- **R22** (3-4-3): Vicario(P) | Kalulu(D) | Solet(D) | Valeri(D) | Zaccagni(C) | Vlasic(C) | Ekkelenkamp(C) | Frattesi(C) | Malen(A) | Raimondo(A) | Colombo(A)
- **R10** (3-4-3): Mandas(P) | Kalulu(D) | Pavlovic(D) | Solet(D) | Zaccagni(C) | Vlasic(C) | Ekkelenkamp(C) | Frattesi(C) | Malen(A) | Raimondo(A) | Colombo(A)
- **R26** (3-4-3): Mandas(P) | Kalulu(D) | Pavlovic(D) | Solet(D) | Zaccagni(C) | Vlasic(C) | Ekkelenkamp(C) | Frattesi(C) | Malen(A) | Raimondo(A) | Colombo(A)
- **R09** (3-4-3): Mandas(P) | Kalulu(D) | Solet(D) | Valeri(D) | Zaccagni(C) | Vlasic(C) | Ekkelenkamp(C) | Frattesi(C) | Malen(A) | Raimondo(A) | Colombo(A)
- **R05** (3-4-3): Mandas(P) | Kalulu(D) | Solet(D) | Valeri(D) | Zaccagni(C) | Vlasic(C) | Ekkelenkamp(C) | Frattesi(C) | Malen(A) | De Ketelaere(A) | Raimondo(A)
- **R12** (3-4-3): Mandas(P) | Kalulu(D) | Pavlovic(D) | Solet(D) | Zaccagni(C) | Vlasic(C) | Ekkelenkamp(C) | Frattesi(C) | Malen(A) | Laurientè(A) | Raimondo(A)
- **R02** (3-4-3): Mandas(P) | Kalulu(D) | Pavlovic(D) | Solet(D) | Zaccagni(C) | Vlasic(C) | Ekkelenkamp(C) | Frattesi(C) | Ramos G.(A) | Raimondo(A) | Colombo(A)
- **R14** (3-4-3): Mandas(P) | Kalulu(D) | Pavlovic(D) | Solet(D) | Zaccagni(C) | Ederson D.S.(C) | Ekkelenkamp(C) | Frattesi(C) | Malen(A) | Raimondo(A) | Colombo(A)
- **R07** (3-4-3): Mandas(P) | Kalulu(D) | Solet(D) | Valeri(D) | Zaccagni(C) | Vlasic(C) | Ekkelenkamp(C) | Frattesi(C) | Malen(A) | Laurientè(A) | Raimondo(A)
- **R13** (3-4-3): Mandas(P) | Kalulu(D) | Pavlovic(D) | Solet(D) | Zaccagni(C) | Vlasic(C) | Ekkelenkamp(C) | Frattesi(C) | Malen(A) | Laurientè(A) | Colombo(A)
- **R23** (3-4-3): Maignan(P) | Kalulu(D) | Solet(D) | Valeri(D) | Zaccagni(C) | Vlasic(C) | Ekkelenkamp(C) | Frattesi(C) | Malen(A) | Raimondo(A) | Colombo(A)
- **R08** (3-4-3): Mandas(P) | Kalulu(D) | Pavlovic(D) | Solet(D) | Calhanoglu(C) | Zaccagni(C) | Vlasic(C) | Frattesi(C) | De Ketelaere(A) | Raimondo(A) | Colombo(A)
- **R30** (3-4-3): Mandas(P) | Kalulu(D) | Pavlovic(D) | Solet(D) | Calhanoglu(C) | Zaccagni(C) | Vlasic(C) | Frattesi(C) | Laurientè(A) | Raimondo(A) | Colombo(A)
- **R03** (3-4-3): Mandas(P) | Kalulu(D) | Pavlovic(D) | Solet(D) | Zaccagni(C) | Vlasic(C) | Ekkelenkamp(C) | Frattesi(C) | Martinez L.(A) | Raimondo(A) | Colombo(A)
- **R29** (3-4-3): Mandas(P) | Kalulu(D) | Pavlovic(D) | Solet(D) | Zaccagni(C) | Vlasic(C) | Ekkelenkamp(C) | Frattesi(C) | Laurientè(A) | Raimondo(A) | Colombo(A)
- **R19** (3-4-3): Mandas(P) | Solet(D) | Valeri(D) | De Winter(D) | Zaccagni(C) | Ekkelenkamp(C) | Frattesi(C) | Calò(C) | Malen(A) | Kolo Muani(A) | Raimondo(A)
- **R17** (3-4-3): Mandas(P) | Kalulu(D) | Valeri(D) | De Winter(D) | Zaccagni(C) | Ekkelenkamp(C) | Frattesi(C) | Calò(C) | Malen(A) | Ramos G.(A) | Raimondo(A)
- **R21** (3-4-3): Svilar(P) | Kalulu(D) | Pavlovic(D) | Solet(D) | Zaccagni(C) | Vlasic(C) | Ekkelenkamp(C) | Frattesi(C) | Ramos G.(A) | Raimondo(A) | Colombo(A)
- **R15T** (3-4-3): Mandas(P) | Kalulu(D) | Pavlovic(D) | Solet(D) | Ederson D.S.(C) | Ekkelenkamp(C) | Frattesi(C) | Calò(C) | Malen(A) | De Ketelaere(A) | Laurientè(A)
- **R18** (3-4-3): Mandas(P) | Solet(D) | Valeri(D) | De Winter(D) | Zaccagni(C) | Ekkelenkamp(C) | Frattesi(C) | Calò(C) | Malen(A) | Hojlund(A) | Raimondo(A)
- **R16** (3-4-3): Mandas(P) | Vasquez(D) | Valeri(D) | De Winter(D) | Ederson D.S.(C) | Ekkelenkamp(C) | Frattesi(C) | Calò(C) | Malen(A) | Martinez L.(A) | Raimondo(A)
- **R28** (3-4-3): Mandas(P) | Kalulu(D) | Pavlovic(D) | Solet(D) | Zaccagni(C) | Vlasic(C) | Ekkelenkamp(C) | Frattesi(C) | De Ketelaere(A) | Raimondo(A) | Colombo(A)

## Le 5 migliori per punti medi, reparto per reparto

Rose DIVERSE fra loro: chi ha gli stessi 25 di una gia' scritta (colonna `duplicato_di`) non si ripete.

### R25 - bench_weight 0.45 (modulo non forzabile: ripiego)
modulo 3-4-3, costo q50 500 (P 39 / D 85 / C 155 / A 221), value 5544, indisponibili 2, note negative 4, punti 3210 +- 12, P(1) 57% +- 8%

- Portieri: Caprile, Mandas, Falcone
- Difensori: Kalulu, Solet, Vasquez, Valeri, Obert, Bracaglia, Zè Pedro, De Winter
- Centrocampisti: Zaccagni, Vlasic, Ekkelenkamp, Frattesi, Volpato, Fazzini, Calò, Pierotti
- Attaccanti: Malen, Raimondo, Colombo, Tourè E., Yeboah J., Kvernadze

### R15 - escluso/i Zaccagni
modulo 3-4-3, costo q50 500 (P 38 / D 99 / C 141 / A 221), value 5542, indisponibili 1, note negative 3, punti 3203 +- 12, P(1) 60% +- 8%

- Portieri: Mandas, Okoye, Falcone
- Difensori: Kalulu, Pavlovic, Solet, Vasquez, Valeri, Obert, Zè Pedro, De Winter
- Centrocampisti: Ederson D.S., Vlasic, Ekkelenkamp, Frattesi, Cristante, Fazzini, Calò, Pierotti
- Attaccanti: Malen, Raimondo, Colombo, Tourè E., Yeboah J., Kvernadze

### R01 - riferimento: lam 0.5, attacco 35-50%
modulo 3-4-3, costo q50 500 (P 39 / D 88 / C 152 / A 221), value 5524, indisponibili 1, note negative 4, punti 3199 +- 11, P(1) 52% +- 8%

- Portieri: Caprile, Mandas, Falcone
- Difensori: Kalulu, Pavlovic, Solet, Obert, Bracaglia, Zè Pedro, Veiga D., De Winter
- Centrocampisti: Zaccagni, Vlasic, Ekkelenkamp, Frattesi, Fazzini, Calò, Coulibaly L., Pierotti
- Attaccanti: Malen, Raimondo, Colombo, Tourè E., Yeboah J., Kvernadze

### R22 - portiere titolare imposto Vicario
modulo 3-4-3, costo q50 500 (P 64 / D 68 / C 152 / A 216), value 5488, indisponibili 1, note negative 4, punti 3199 +- 15, P(1) 50% +- 8%

- Portieri: Vicario, Mandas, Falcone
- Difensori: Kalulu, Solet, Valeri, Obert, Zè Pedro, Calvani, De Winter, Troilo
- Centrocampisti: Zaccagni, Vlasic, Ekkelenkamp, Frattesi, Fazzini, Calò, Coulibaly L., Pierotti
- Attaccanti: Malen, Raimondo, Colombo, Tourè E., Osmajic, Kvernadze

### R10 - lam 0 (nessun peso all'upside)
modulo 3-4-3, costo q50 500 (P 39 / D 89 / C 156 / A 216), value 5528, indisponibili 1, note negative 4, punti 3194 +- 11, P(1) 45% +- 8%

- Portieri: Caprile, Mandas, Falcone
- Difensori: Kalulu, Pavlovic, Solet, Valeri, Obert, Zè Pedro, Calvani, De Winter
- Centrocampisti: Zaccagni, Vlasic, Ekkelenkamp, Frattesi, Cristante, Fazzini, Calò, Pierotti
- Attaccanti: Malen, Raimondo, Colombo, Tourè E., Osmajic, Kvernadze


## Controllo su scenari nuovi (seme 1002, 200 scenari)

Stesse rose, scenari mai usati sopra e quattro volte piu' numerosi. Una differenza che cambia segno qui era rumore.

| rosa | diff vs R01 (40 sc.) | diff vs R01 (200 sc.) | +-SE | serio a 200 |
|---|---|---|---|---|
| R25 | +11 | -1 | 3 | si |
| R15 | +4 | -17 | 4 | no |
| R01 | +0 | +0 | 0 | si |
| R04 | +0 | +0 | 0 | si |
| R06 | +0 | +0 | 0 | si |
| R11 | +0 | +0 | 0 | si |
| R20 | +0 | +0 | 0 | si |
| R24 | +0 | +0 | 0 | si |
| R27 | +0 | +0 | 0 | si |
| R22 | -0 | -14 | 5 | no |
| R10 | -6 | -10 | 4 | no |
| R26 | -6 | -10 | 4 | no |
| R09 | -9 | +1 | 5 | si |
| R05 | -16 | +2 | 4 | si |
| R12 | -17 | -12 | 4 | no |
| R02 | -18 | -36 | 5 | no |
| R14 | -20 | -26 | 3 | no |
| R07 | -20 | -21 | 4 | no |
| R13 | -22 | -7 | 4 | no |
| R23 | -22 | -19 | 4 | no |
| R08 | -23 | -17 | 6 | no |
| R30 | -26 | -38 | 6 | no |
| R03 | -36 | -41 | 4 | no |
| R29 | -37 | -58 | 5 | no |
| R19 | -40 | -38 | 7 | no |
| R17 | -40 | -15 | 7 | no |
| R21 | -42 | -42 | 5 | no |
| R15T | -51 | -48 | 4 | no |
| R18 | -58 | -50 | 6 | no |
| R16 | -58 | -35 | 8 | no |
| R28 | -62 | -60 | 6 | no |

Tempo totale 28s.
