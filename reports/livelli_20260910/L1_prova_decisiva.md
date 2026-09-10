# L1 — prova decisiva: bersaglio onesto delle presenze contro regola banale

Disegno e criterio: `reports/livelli_20260910/L1.md` §8. Criterio ricopiato in
`scratchpad/w4/criteri_prima_B.md` **prima** di eseguire. Nessun file del
progetto scritto, modificato o cancellato.

## Disegno eseguito

- Stagione **2025-26**, origine **2025-08-22** (giorno prima della prima
  partita), giornate interamente concluse **K = 0**, partite residue **380**.
- Braccio A (onesto): `scripts/l1_presenze_per_origine.py 2025-26 --feature
  ammesse --semi 5`; **32 feature su 36**, escluse `fvm`, `quot_fs_sett`,
  `team_prev_xg`, `cambio_squadra`; manifesto «utilizzabile operativamente:
  True»; scarto medio fra semi 0,496 presenze.
- Braccio B (banale): `prev1_presenze` di `players_2025-26.parquet`, NaN -> 0
  (**268 giocatori su 663**, cioe' chi non era in Serie A l'anno prima).
- Vero: presenze a voto in `votes_2025-26.parquet` (`sv == 0`), 38 giornate,
  assenti dal file = 0 presenze. Universo **663 giocatori**, somma vera 10.778.

## Comandi (RIPRODOTTO)

```
PYTHONIOENCODING=utf-8 OMP_NUM_THREADS=4 python scripts/l1_presenze_per_origine.py \
  2025-26 --feature ammesse --semi 5 --fuori "<w4>/pres_2025-26_estiva"
→ giornate concluse 0; osservate 0, residue 380; feature 32/36;
  somma 11016.2 presenze residue su 663 giocatori; scarto fra semi 0.496;
  utilizzabile operativamente: True

PYTHONIOENCODING=utf-8 OMP_NUM_THREADS=4 python "<w4>/confronto_banale.py"
```

Durata complessiva sotto i 2 minuti.

## Numeri

| braccio | MAE (presenze su 38 giornate) | rho di rango | somma prevista |
|---|---:|---:|---:|
| onesto (32 feature, 5 semi) | **7,9291** | **0,6172** | 11.016,2 |
| banale (`prev1_presenze`, NaN->0) | **10,0694** | **0,4435** | 8.572,0 |
| osservato | — | — | 10.778 |

Guadagni: MAE **+2,1403** (serve >= 0,50), rho **+0,1737** (serve >= 0,05).

## Verdetto

**SUPERATO**: entrambe le condizioni del criterio scritto prima sono
soddisfatte (2,1403 >= 0,50 e 0,1737 >= 0,05). Il bersaglio onesto delle
presenze batte la regola banale sul 2025-26, stagione non usata per scegliere
l'elenco delle feature escluse (quello viene dal 2024-25).

## Limiti dichiarati (non cambiano il verdetto, ma vanno letti insieme)

1. La regola banale e' penalizzata per costruzione: **268 su 663** (40,4 %)
   hanno `prev1_presenze` NaN e ricevono 0, e la sua somma prevista e' 8.572
   contro 10.778 osservate (-20,5 %). Il braccio onesto sbaglia in eccesso di
   poco (11.016,2, +2,2 %). Il margine misurato e' quindi in parte il prezzo
   della copertura, non solo dell'accuratezza. Il criterio era scritto prima e
   non si tocca; questo e' un limite del disegno del §8, non del risultato.
2. Il valore assoluto resta alto: MAE 7,93 presenze su 38 giornate. Il numero
   contaminato pubblicato altrove (5,52-5,62 dal banco) non e' confrontabile
   con questo.
3. Prova singola, una stagione, un seme di modello per braccio moltiplicato per
   5 ripetizioni: nessuna barra d'errore sul confronto fra bracci e' stata
   calcolata (il criterio non la chiedeva).
4. Resta non fatto tutto il resto di L1.md §6: contratto temporale su
   `players_*.parquet`, collegamento del bersaglio per origine a
   `partecipazione.stima`, dichiarazione delle fonti del giorno.

## Artefatti (tutti nello scratchpad, niente nel progetto)

- `<w4>/pres_2025-26_estiva/` — `presenze_per_origine.csv`, manifesto,
  `diagnostica.json`
- `<w4>/confronto_banale.py` — script di confronto
- `<w4>/L1_prova_decisiva.json` — numeri e verdetto in forma leggibile a macchina
- `<w4>/l1_run.log` — registro della corsa
