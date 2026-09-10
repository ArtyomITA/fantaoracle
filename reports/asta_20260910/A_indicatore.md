# A — indicatore «chi puo' superarti» (10/9/2026, 16:12-16:28)

Solo informazione. Nessun cambio di politica: il tetto (`max_consigliato`) e le
azioni restano identici, i tre campi sono aggiunti al dizionario.

## Backup
`data/_backup_fable_20260910/pre_indicatore/f10_copilot.py` e `copilot.html`
(copie pre-modifica, cartella nuova).

## Modifiche

### scripts/f10_copilot.py (+31 righe, -4)
- **434-456 nuova `concorrenti_sopra(v, ruolo, tetto)`**: conta gli avversari in
  `v.others` con `slots_left(v.quotas, ruolo) > 0` e `max_bid(v.quotas) >= tetto+1`;
  ritorna `concorrenti_sopra_tetto`, `concorrenti_nomi` (max 5, ordinati per
  max_bid decrescente, presi da `t.bot_name`, cioe' `STATE["names"]` nello stesso
  ordine), `concorrenti_max`. Con `tetto <= 0` -> 0 / [] / 0.
- **479-486 dict `fuori`**: i tre campi a 0/[]/0. Coprono TUTTE le uscite con
  tetto 0: fuori lista, escluso manuale, gia' venduto, rosa completa, reparto
  pieno, cassa insufficiente, e il ramo «non offrire» (tetto 0).
- **519-522 uscita obbligo**: `**concorrenti_sopra(v, ruolo, max_legale)`.
- **548-551 uscita normale**: `**concorrenti_sopra(v, ruolo, tetto)`.
- **597-610 `plan()`**: `dec = decisione_operativa(pid, None)` (prima solo `cap`),
  i tre campi propagati nella riga di target.

Diff completo: `diff_f10.patch`.

### viz/copilot.html (+9 righe, -2)
- **renderAdvice, riga meta (1548-1552)**: dopo «affare sotto» aggiunge
  `possono superarti: N (nomi)` in `var(--peach)` se N > 0; `nessuno puo'
  superarti` in `var(--green)` se N = 0 e `max_consigliato > 0`; niente se il
  tetto e' 0.
- **renderPlan, riga target (1762-1765)**: dentro `<span class="mx">` un `<sup>`
  arancione col conteggio e `title="possono superarti: <nomi>"`. Nessuna colonna
  nuova: la griglia `.trow` non cambia.

Diff completo: `diff_html.patch`.

### tests/test_copilot_asta.py (+61 righe)
Nuovo `test_concorrenti_sopra_tetto`: tavolo vuoto (10x500, 3/8/8/6, max legale
476) -> un target con tetto t >= 1 e t+1 <= 476 ha `concorrenti_sopra_tetto == 9`,
5 nomi, `concorrenti_max == 476`; poi via `_post` hammer le squadre 1 e 2 riempiono
il reparto del target (quotas[ruolo] acquisti da 1 cr ciascuna) e la squadra 3
spende 476 -> conteggio 6 (le tre squadre spariscono dai nomi) e il piano
propaga lo stesso numero; undo di tutti gli acquisti -> di nuovo 9.
Nota: 476 e non 480 perche' 480 supera il massimo legale a tavolo vuoto
(500 - 24 slot) e `/copilot/hammer` lo rifiuta con 400.

## Esiti

| prova | esito |
|---|---|
| `pytest tests/test_copilot_asta.py -q` (PYTEST_DISABLE_PLUGIN_AUTOLOAD=1, -p no:cacheprovider) | **11 passed, 1 skipped** in 8.80s — lo skip e' preesistente (`test_senza_previsione_registrabili`: «nessun attivo senza previsione») |
| `verifica_f1f2.py` | **32/32 verificati** |
| `verifica_f5bis.py` | **23/23 verificati** |
| `verifica_f5_asta.py` | **24/24 verificati** |
| UI Chrome headless (`repro_ui_indicatore.py`, server 8794, ledger `data/copilot/prove/ledger_w6_ind.json`) | **difetto assente**, exit 0 |
| UI ramo N=0 (`repro_ui_indicatore_verde.py`) | «nessuno puo' superarti» in `rgb(166, 227, 161)` = `--green` |

Osservato in pagina (Malen, pid 5585, prezzo 1, tavolo vuoto di 10):
`slot liberi A: 6 | tua offerta max legale: 476 | calore mercato: x1.00 |
max consigliato: 174 | affare sotto: 74 | possono superarti: 9 (Marco, Luca,
Giulia, Andrea, Sara)`, colore `rgb(250, 179, 135)` = `--peach`.
ROSA TARGET: `<sup>` con testo `9`, title `possono superarti: Marco, Luca,
Giulia, Andrea, Sara`. Console: **nessun errore** (`errori=[]`).

Schermate: `indicatore.png` (pagina), `indicatore_riga.png` (riga meta),
`indicatore_verde.png`, `indicatore_riga_verde.png`.

## Pulizia
Server 8794 fermato (`netstat ... :8794 LISTENING` = 0), `ledger_w6_ind.lock`
rimosso, restano solo `data/copilot/prove/ledger_w6_ind.json` e `.buono.json`.
Ledger veri `data/copilot/ledger_*.json` non toccati. Nessun push, nessuna
rigenerazione del pack.

## Script
- `repro_ui_indicatore.py` (prova UI, exit 0/1/2)
- `repro_ui_indicatore_verde.py` (variante ramo N = 0)
