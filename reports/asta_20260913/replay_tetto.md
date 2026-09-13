# Replay del tetto — asta del 10/9/2026

Generato da `reports/asta_20260913/replay_tetto.py` il 2026-09-13T15:55:38.
Ledger letto in sola lettura: `data/copilot/ledger_1789058317.json` (250 eventi, io = TonyDaMilano).

Attaccanti battuti a 40 crediti o piu': 28. Il tetto nuovo arriva al prezzo del tavolo in **7** casi su 28; sui quattro lotti della diagnosi (Malen, Martinez L., Ramos G., Hojlund) in **3** su 4.
Tetti sopra il massimo spendibile: **0** (deve essere 0).

«cap bot prima» e' il tetto che il bot produce da solo, col calore globale del mercato: e' la colonna che la sera del 10/9 diceva 116 per Malen. «cap bot dopo» e' lo stesso tetto riletto col calore del RUOLO. «indiff.» e' il prezzo di indifferenza (bisezione MILP sul piano con lui contro il miglior piano senza di lui).

| ev | giocatore | vincitore | prezzo | crediti | slot A | cap bot prima | cap bot dopo | indiff. | bomber | contend. | quota | tetto | arriva? |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 190 | Malen | Nightmare fc | 275 | 316 | 6 | 122 | 182 | 244 | 3 | 8 | 0.667 | **289** | SI |
| 192 | Kolo Muani | AS oreca | 60 | 316 | 6 | 38 | 74 | None | 0 | 8 | 0.0 | **74** | SI |
| 193 | Martinez L. | MoreiraDiFame | 255 | 316 | 6 | 127 | 209 | 231 | 1 | 6 | 0.857 | **300** | SI |
| 194 | De Ketelaere | SSSP | 41 | 316 | 6 | 31 | 55 | None | 0 | 9 | 0.0 | **55** | SI |
| 195 | Dybala | SSSP | 137 | 316 | 6 | 21 | 36 | None | 0 | 9 | 0.0 | **36** | no |
| 196 | Laurientè | ammolly | 52 | 316 | 6 | 26 | 48 | None | 0 | 9 | 0.0 | **48** | no |
| 198 | Ramos G. | Ac Mignottingham Forest | 205 | 316 | 6 | 110 | 201 | None | 0 | 5 | 0.0 | **201** | no |
| 199 | Raimondo | Tonno Fc | 80 | 316 | 6 | 23 | 42 | 251 | 8 | 2 | 0.0 | **42** | no |
| 200 | Hojlund (mio) | TonyDaMilano | 200 | 316 | 6 | 102 | 191 | 188 | 3 | 3 | 0.25 | **219** | SI |
| 201 | Thuram | as tavolato | 146 | 116 | 5 | 45 | 84 | 0 | 2 | 9 | 0.8 | **90** | no |
| 202 | Kean | ROCKS PIRATE | 80 | 116 | 5 | 39 | 71 | None | 0 | 9 | 0.0 | **71** | no |
| 203 | Douvikas | ammolly | 140 | 116 | 5 | 30 | 52 | 0 | 1 | 9 | 0.9 | **101** | no |
| 205 | Woltemade (mio) | TonyDaMilano | 50 | 116 | 5 | 34 | 60 | None | 0 | 9 | 0.0 | **60** | SI |
| 206 | Diao | Tonno Fc | 90 | 66 | 4 | 13 | 22 | None | 0 | 9 | 0.0 | **22** | no |
| 207 | Soulè | SSSP | 46 | 66 | 4 | 36 | 62 | None | 0 | 8 | 0.0 | **62** | SI |
| 208 | Davis K. | ROCKS PIRATE | 74 | 66 | 4 | 24 | 41 | 29 | 4 | 9 | 0.6 | **49** | no |
| 209 | Pinamonti | as tavolato | 61 | 66 | 4 | 15 | 25 | None | 0 | 9 | 0.0 | **25** | no |
| 211 | Esposito F.P. | Ac Mignottingham Forest | 66 | 66 | 4 | 24 | 40 | None | 0 | 9 | 0.0 | **40** | no |
| 212 | Scamacca | AS oreca | 60 | 66 | 4 | 28 | 46 | 1 | 3 | 9 | 0.7 | **46** | no |
| 213 | Dovbyk | ammolly | 42 | 66 | 4 | 13 | 21 | None | 0 | 9 | 0.0 | **21** | no |
| 215 | Simeone (mio) | TonyDaMilano | 63 | 66 | 4 | 17 | 27 | 3 | 1 | 9 | 0.9 | **57** | no |
| 216 | Berardi | ROCKS PIRATE | 127 | 3 | 3 | 1 | 1 | None | 0 | 9 | 0.0 | **1** | no |
| 218 | Piccoli | as tavolato | 41 | 3 | 3 | 1 | 1 | None | 0 | 9 | 0.0 | **1** | no |
| 219 | Castro S. | Nightmare fc | 40 | 3 | 3 | 1 | 1 | None | 0 | 9 | 0.0 | **1** | no |
| 220 | Colombo | AS oreca | 47 | 3 | 3 | 1 | 1 | None | 0 | 9 | 0.0 | **1** | no |
| 226 | Yildiz | Ac Mignottingham Forest | 61 | 3 | 3 | 1 | 1 | None | 1 | 9 | 0.9 | **1** | no |
| 229 | Yeboah J. | SSSP | 56 | 3 | 3 | 1 | 1 | None | 0 | 9 | 0.0 | **1** | no |
| 230 | Raspadori | AS oreca | 47 | 3 | 3 | 1 | 1 | None | 0 | 9 | 0.0 | **1** | no |

## Nota sui numeri della diagnosi

L'audit del 12/9 misurava, sul codice di allora, 116 per Malen, 123 per Martinez L. e 102 per Hojlund. Qui la colonna «cap bot prima» puo' differire: il bonus gol di lega (+5 contro +3 della fonte) ha cambiato i valori del piano, e la quota di spesa in attacco ora si misura sul budget residuo invece che su quello totale. Il confronto che conta e' fra le due colonne di questa tabella, calcolate lo stesso giorno sullo stesso stato.