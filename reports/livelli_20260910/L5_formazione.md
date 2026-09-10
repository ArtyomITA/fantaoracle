# L5 / Compito A — scripts/f17_formazione.py (consiglio di formazione di giornata)

Data 10/9/2026. Nessun file congelato toccato. Nessun server, nessun push,
nessun training. Comandi con `PYTHONIOENCODING=utf-8 OMP_NUM_THREADS=4`;
pytest con `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1`.

## Criteri di accettazione (scritti PRIMA di eseguire)

- A1 modulo scelto fra i sette di `src/fantabot/season/lineup.py:11-12`;
- A2 esattamente 11 titolari, conteggi per ruolo = modulo (P sempre 1);
- A3 un indisponibile non e' titolare se il suo reparto ha un'alternativa
  disponibile; resta titolare (con avviso stampato) se il reparto non basta;
- A4 panchina senza doppioni, disgiunta dai titolari, titolari+panchina = rosa;
- A5 stessa uscita a parita' di ingressi (anche cambiando l'ordine della rosa);
- A6 giornata senza righe nelle probabili -> errore che nomina giornata e file;
- A7 comando vero sul ledger di prova: uscita 0 e markdown scritto.
- Nessun criterio sul punteggio: una giornata sola non valida nulla.

## File creati

- `scripts\f17_formazione.py`
- `tests\test_f17_formazione.py`
- `data\copilot\formazione_2026-27_G4.md` (uscita, 2843 byte)

Nessun file esistente modificato.

## Derivazione del punteggio atteso — OSSERVATO NEL CODICE, non inventata

Da `src/fantabot/montecarlo.py:115` `build_dists` (stessa funzione che alimenta
il Monte Carlo d'asta, chiamata come in `scripts/f12_choose_objective.py:36-46`
con i pack delle due stagioni precedenti):

- `p_play = pres/38` tagliato in [0.05, 0.97] (`:145-146`);
- `mean_needed = value/(p_play*38)` se `value > 0`, altrimenti `fv.mean()` (`:147`);
- `shift = clamp(mean_needed - fv.mean(), -2, +2)` (`:148-149`);
- fantavoto simulato `samples_fv[k] + shift + eps + shock` (`:246`), `eps` e
  `shock` a media zero -> **atteso quando gioca = `samples_fv.mean() + shift`**;
- voto puro simulato `samples_v[k] + (shift+eps)*0.4 + shock` (`:247`) ->
  **voto puro atteso = `samples_v.mean() + 0.4*shift`** (serve solo al mod. difesa).

Punteggio atteso di schieramento = `p_gioca * (samples_fv.mean() + shift)`, con
`p_gioca = pct_titolarita/100`, azzerata se il giocatore e' negli
`indisponibili` di `data/copilot/eleggibilita_2026-27.json` (infortunio o
squalifica) o se non compare nelle probabili della giornata (nessuna prova che
scenda in campo: non si inventa una probabilita').

## Scelta del modulo e modificatore difesa

`pick_lineup(roster, form, form_voto, use_mod_difesa=True, available)` con
`form` = punteggio atteso di schieramento: il modulo scelto e' quello che
massimizza la somma degli undici. Il modificatore difesa **e' gia' esposto**
da `lineup.py:50-56` dentro `pick_lineup` (richiede >= 4 difensori, sconta
mezzo gradino), quindi si usa quello; niente aggiunte. Limite dichiarato: in
`pick_lineup` il modificatore usa i voti puri attesi NON pesati per la
probabilita' di giocare — comportamento del motore congelato, non modificato.

Panchina ordinata per ruolo e punteggio decrescente, indisponibili in fondo.
Contano i primi nomi per reparto perche' `score_giornata` (`lineup.py:65-97`)
sostituisce un titolare senza voto con la prima riserva **dello stesso ruolo**
con voto, al massimo 3 cambi in tutto: spiegato dentro il markdown prodotto.

## Prove — RIPRODOTTO

`PYTHONIOENCODING=utf-8 OMP_NUM_THREADS=4 PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python -m pytest tests/test_f17_formazione.py -q`
-> `9 passed in 1.82s`. Copre A1..A6 su rosa sintetica 25 (3P/8D/8C/6A) senza
pack e senza rete, piu' ledger sintetico in tmp_path e rosa insufficiente.

Comando vero (A7):
`python scripts/f17_formazione.py --ledger data/copilot/prove/ledger_w1_8793.json`
-> `exit=0`, scritto `data/copilot/formazione_2026-27_G4.md`. Ledger di prova,
mai i ledger in `data/copilot/` diretti. Rosa mia in quel ledger: 20 giocatori
(3P/8D/8C/1A), quindi l'unico attaccante forza i moduli a 1 punta.

Prime 30 righe dell'uscita:

```
# Formazione consigliata — 2026-27, giornata 4

Modulo **4-5-1**, somma dei punteggi attesi degli undici: **69.23**.

- probabili: `probabili_20260910.csv`
- pack: `pack_2026-27.pkl`
- punteggio atteso schierato = probabilita' di giocare (titolarita'/100, 0 se indisponibile o assente dalle probabili) x punteggio atteso per giornata quando gioca (derivazione `build_dists` di `src/fantabot/montecarlo.py`).

## Titolari

| giocatore | ruolo | squadra | avversario | titolarita' | stato | atteso se gioca | atteso schierato | note |
|---|---|---|---|---|---|---|---|---|
| Maignan | P | MIL | Lazio (trasferta) | 90% | titolare | 5.76 | 5.18 | - |
| Theate | D | BOL | Napoli (trasferta) | 90% | titolare | 7.17 | 6.45 | - |
| Kalulu | D | JUV | Sassuolo (trasferta) | 90% | titolare | 6.80 | 6.12 | - |
| Kamara H. | D | UDI | Inter (trasferta) | 90% | titolare | 6.55 | 5.90 | - |
| Lucumì | D | JUV | Sassuolo (trasferta) | 80% | titolare | 6.49 | 5.20 | - |
| Calhanoglu | C | INT | Udinese (casa) | 90% | titolare | 9.22 | 8.30 | - |
| Conceicao | C | JUV | Sassuolo (trasferta) | 90% | titolare | 7.63 | 6.87 | - |
| Bernardeschi | C | BOL | Napoli (trasferta) | 90% | titolare | 7.18 | 6.46 | - |
| Zambo Anguissa | C | NAP | Bologna (casa) | 90% | titolare | 7.00 | 6.30 | - |
| Ferguson | C | BOL | Napoli (trasferta) | 90% | titolare | 6.70 | 6.03 | - |
| Martinez L. | A | INT | Udinese (casa) | 75% | titolare | 8.56 | 6.42 | - |

## Panchina (ordine dei cambi)

I cambi automatici sono al massimo **3** e valgono solo dentro lo stesso ruolo: se un titolare non prende voto entra la **prima** riserva del suo ruolo che ha voto, scorrendo la lista in quest'ordine (`score_giornata`, `src/fantabot/season/lineup.py`). Contano quindi i primi nomi di ogni reparto.

| giocatore | ruolo | squadra | avversario | titolarita' | stato | atteso se gioca | atteso schierato | note |
|---|---|---|---|---|---|---|---|---|
| Muric | P | SAS | Juventus (casa) | 90% | titolare | 5.64 | 5.08 | - |
```

Determinismo sul comando vero: due esecuzioni con `--out` diverso ->
`diff -q` IDENTICI (RIPRODOTTO).

Errore chiaro (RIPRODOTTO):
- `--giornata 7`: `nessuna riga per la giornata 7 in ...\probabili_20260910.csv (giornate presenti: [4])`;
- ledger con 1 solo giocatore (`ledger_w1_8791.json`): `exit=1`,
  `rosa insufficiente per qualunque modulo [(3, 4, 3), ...]: {'P': 0, 'D': 0, 'C': 0, 'A': 1}`.

## Verdetti (criterio prima, numeri dopo)

- A1 A2: PASSATO. Modulo 4-5-1 in `MODULES`; 11 titolari, 1P/4D/5C/1A.
- A3: PASSATO nelle prove sintetiche (indisponibile D0 fuori con alternativa;
  P0 indisponibile resta titolare senza alternativa). Sul ledger vero nessun
  indisponibile e' capitato nella rosa: il caso non e' stato esercitato dai
  dati reali — dichiarato, non spacciato per prova.
- A4: PASSATO. 20 = 11 + 9, nessun doppione.
- A5: PASSATO. 9 prove + diff identico su due esecuzioni reali.
- A6: PASSATO. Messaggio con giornata e percorso del file.
- A7: PASSATO. `exit=0`, markdown 2843 byte.
- Qualita' del consiglio: NON VALUTATA. Una giornata sola non misura niente;
  servirebbero i voti della g4 (dal 14/9) per un confronto, e non e' stato
  fatto. «Inconcludente» non diventa «buono».

## Cosa NON e' stato fatto

- nessun confronto con i voti reali della giornata 4 (non ancora pubblicati);
- nessuna modifica a `scripts/f4_eleggibilita.py` (`GIORNATA_CORRENTE = 4`
  resta cablato: e' il passo P3 di L5, fuori compito);
- ballottaggi: `pct_ballottaggio` letta e mostrata come nota, non usata per
  correggere `pct_titolarita` (nessuna regola scritta per farlo);
- nessuna integrazione con `viz/` o con il Copilota.
