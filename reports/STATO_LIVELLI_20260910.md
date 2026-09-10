# Stato dei cinque livelli — 10 settembre 2026, ore 07:00

Aggiorna [`STATO_LIVELLI_20260909.md`](STATO_LIVELLI_20260909.md) dopo la notte
di preparazione dell'asta. Stesse cinque colonne, stessa regola: ogni casella
dice **come si sa**. I cinque rapporti completi, uno per livello, stanno in
[`livelli_20260910/`](livelli_20260910/) (agenti in sola lettura, criteri
scritti prima dei numeri, comandi eseguiti riportati con l'esito esatto).

| livello | implementato | verificato | validato | collegato | operativo |
|---|---|---|---|---|---|
| **1 — dati e banco** | sì | **parziale** (11 prove L1, non 562) | **parziale** | sì | sì |
| **2 — cubo TABELLINO** | sì | sì (360 prove + 1 saltata) | no | no | no |
| **3 — P(1°) e tetti** | sì | **parziale** (163 verdi, 2 rosse) | no | no | no |
| **4 — prezzi** | parziale | **no** (zero prove) | no | sì | sì |
| **5 — stagione in corso** | parziale | parziale | no | no | parziale |

## Che cosa è cambiato stanotte, e che cosa lo dimostra

- **Pack rigenerato** (`data/refresh/last.log`, 06:03-06:21): 594 giocatori,
  K = 3 (giornata 3 giocata il 4-7/9), voti/listone/probabili/indisponibili/
  rigoristi/prezzi live del 10/9. Confronto col pack del 6/9: 8/8 controlli
  (`scratchpad/w1/confronta_pack.py`). Il pack usciva **senza
  `b_objective`** (f12 non è nella catena): copiato dal pack del 6/9 e
  dichiarato in `CORRENTE.json`.
- **Copilota corretto** (vedi `RIPRESA_ASTA.md`): prove 32/32, 23/23, 24/24,
  25/25 riprodotte sul codice e sul pack nuovi; suite finale **577 passati,
  2 saltati, 2 falliti**, con `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1`.
- **Le due prove rosse sono di L3** (`tests/test_bot_l3_parita.py:356` e
  `:424`): la guardia del mondo dice `594 == 587` e l'asserzione d'esito
  «L3 impegna sul piano più di B+» ora dà 121 contro 146. Non sono state
  toccate: il cubo (`data/l2/cubo_2026-27.pkl`, 8/9, 587 giocatori) è
  disallineato dal pack nuovo, e l'esperimento L3 **oggi non è rigiocabile**
  (cinque repliche su cinque scartate perché una rosa contiene uno dei sette
  giocatori assenti dal cubo). Va riallineato l'universo, non il test.
- **Il cubo 2026-27 è stale** anche rispetto ai voti e al listone
  (impronte diverse), e il rapporto del cubo non registra l'impronta di
  `b_predictions`: l'ingresso principale è cambiato senza che niente se ne
  accorgesse.

## Correzioni al quadro del 9/9

- «L1 verificato: sì, 562 prove» attribuiva a L1 l'intera suite: L1 ha 11 prove.
- «`fvm` e `quot_fs_sett` contengono l'esito della stagione» vale per i
  backtest (k = 0) e **non** per il 2026-27 (k = 3, snapshot fanta.soccer del
  4/9): la distinzione c'era in `CICLO_20260909.md`, non nel quadro.
- Il q50 pubblicato è già **mercato al 60 %** (`market_adjust.py:181`, identità
  verificata su 369 giocatori): il «prezzo di mercato» in scheda non è un
  secondo parere indipendente. Il peso 0,6 non è mai stato misurato, e con
  questo archivio non è misurabile (i listini delle stagioni con aste reali
  sono tutti posteriori all'asta).
- Tre portieri con q10 > q50 dopo la miscela: la traslazione non preserva
  l'ordine dei quantili (una riga in `market_adjust.py:184`).

## Per livello: mancanza principale e prova decisiva

**L1.** Nessun contratto temporale su `players_*.parquet` (66 colonne senza
stato dichiarato); il bersaglio delle presenze è addestrato su stagioni con
`fvm`/`quot_fs_sett` posteriori (ablazione riprodotta: +2,5571 MAE, es 0,0150);
le fonti del giorno usate da `f9_apply_market` non sono tracciate
nell'artefatto. **Prova decisiva**: bersaglio onesto contro regola banale
(`prev1_presenze`) sul 2025-26, origine estiva, 5 semi; criterio scritto prima:
MAE(onesto) ≤ MAE(banale) − 0,50 e rho ≥ rho(banale) + 0,05. Costo 2-5 minuti.

**L2.** Nessuna misura dove il cubo lavora (durata delle assenze, dipendenze
fra compagni con soglia, rose vere); il pilota non ha un punto di aggancio
per un bersaglio alternativo (`costruisci_ingressi` fissa il percorso); formati
incompatibili fra l'artefatto per origine (CSV) e `presenze.costruisci`
(JSON); il controfattuale non è stato rieseguito dopo le modifiche del 9/9.
**Prova decisiva**: il §3ter di `RIPRESA.md` con ingressi puliti da entrambe le
parti, differenze appaiate seme per seme sulle presenze realizzate; costo
95-105 minuti di CPU.

**L3.** Quarto difetto ancora vero nel produttore (`scripts/l3_tetti.py:236`:
un solo stato iniziale per tutte le curve) e il file dei tetti è inservibile
già prima del primo martelletto (`usabili: 0, letti: 25, senza_identita: 25`);
P(1°) non entra mai al martelletto; nessun esperimento rigiocato dopo l'8/9.
**Prova decisiva**: banco appaiato B contro L3-selezione senza tetti, stessi
semi e sedie, criterio già congelato in `CRITERI_L2_L3.md:187-189`; 10-11
minuti — ma prima va riallineato l'universo pack/cubo.

**L4.** Zero prove automatiche; campione del bersaglio 88 aste (una del
2024-25, zero 2025-26); `with_conformal` divide per riga invece che per asta;
`ref_price_sd = 0` per tutti; due fonti di prezzo di mercato in circolazione
(live 10/9 nel q50, bundle 9/9 in scheda). **Prove minime proposte**: contratto
sul prezzo pubblicato (ordine dei quantili, identità della miscela), non
anticipazione della fonte, copertura registrata. **Prova decisiva**:
trasferibilità della calibrazione per segmento (fascia × ruolo, conformal
split per asta), criterio in blocco: copertura globale in [0,75, 0,85],
nessuna cella con n ≥ 30 sotto 0,60, pinball non peggiore.

**L5.** L'aggiornamento settimanale gira (fatto stanotte) ma con due punti
manuali (`GIORNATA_CORRENTE` cablata in `f4`, f12 fuori catena); il consiglio
di formazione ha il motore (`season/lineup.py`) e gli ingressi (probabili con
`player_id`) ma **nessun consumatore**; scambi, svincoli e riparazione di
gennaio: zero righe, e `league.yaml` non è letto da nessuno. **Prova
decisiva**: il secondo giro settimanale, dopo la 4ª giornata (dal 14/9),
con cinque condizioni scritte prima (exit 0, k = 4 per tutti, ecc.).

## Ordine consigliato dopo l'asta

1. Riallineare pack e cubo (rigenerare il cubo sui 594, o limitare il pool)
   e spiegare — non togliere — le due asserzioni L3 cadute.
2. Il pezzo più corto di L5: `f17_formazione.py`, undici nomi per la giornata
   dalle rose vere del ledger e dalle probabili.
3. Le tre prove minime di L4 e la riga sull'ordine dei quantili.
4. Contratto temporale su `players_*.parquet` e prova decisiva di L1.
5. Solo dopo, il §3ter del cubo.

Nessuna percentuale di completamento: non ci sono dati per farla.

## Aggiornamento ore 12:20 — lavori di contorno (fuori dal percorso d'asta)

Quattro agenti (tre lavori + un revisore); rapporti in `livelli_20260910/`
(`L5_formazione.md`, `B_L4_L1.md`, `L1_prova_decisiva.md`, `L3_banco.md`,
`revisione.md`). Percorso d'asta: **26 impronte su 26 identiche**; prove del
Copilota 32/32, 23/23, 24/24, 25/25 rieseguite dal revisore; suite
**597 passati, 2 saltati, 5 xfail dichiarati, 1 rosso**.

- **L5**: `scripts/f17_formazione.py` (+9 prove) — consiglio di formazione per
  giornata dalle rose vere del ledger, probabili con `player_id`,
  indisponibili e pack; motore `season/lineup.py` non riscritto. Qualità del
  consiglio **non valutata** (voti della G4 non ancora usciti).
- **L4**: tre file di prova (15 prove: 10 verdi, 5 `xfail(strict=True)` che
  documentano difetti veri: tre portieri con q10 > q50, `auction_date`
  mancante per tre stagioni, listini wayback tutti posteriori all'asta,
  `f1_price_eval.json` con R3 che il codice non ha più). Identità della
  miscela di mercato verificata (369 giocatori, scarto 2,8e-14).
- **L1**: prova decisiva **superata** sul 2025-26 (origine estiva, 5 semi):
  bersaglio onesto MAE 7,929 e rho 0,617 contro regola banale 10,069 e 0,444
  (criterio: −0,50 e +0,05). Una sola stagione, nessuna barra d'errore.
- **L2/L3**: cubo rigenerato sui 594 (7 minuti, 40 scenari × 35 giornate);
  guardia del mondo portata a 594 con la storia nel docstring; banco appaiato
  B contro L3 (44 aste, 22 repliche): **inconcludente** — L3 − B = −0,030,
  IC95 [−0,100, +0,032], semiampiezza 0,066 contro 0,030 richiesta (servono
  ~117 repliche). La bocciatura del 7/9 non si riproduce; non si scrive
  «equivalenti». L'asserzione d'esito resta rossa e spiegata (L3 impegna
  121 crediti sul piano contro 146 di B+, prendendo 9 giocatori a 13,4 l'uno
  contro 6 a 24,3). **Nessun tetto e nessuna politica L3 nel Copilota.**

## Aggiornamento ore 15:10 — quattro lavori di profondità (fuori dal percorso d'asta)

Rapporti in `livelli_20260910/*_1500.md` e `revisione_1500.md`. Percorso
d'asta: 26 impronte su 26 identiche (ricontrollate anche dall'orchestratore);
prove Copilota 32/32, 23/23, 24/24, 25/25; suite **660 passati, 2 saltati,
5 xfail, 1 rosso** (sempre l'esito L3, invariato; +63 prove nuove, nessuna
tolta o marcata).

- **L3 (banco appaiato)**: 117 repliche in un solo run superavano i 45 minuti;
  disegno emendato prima dei numeri in due blocchi da 66 (semi 20260907 e
  20260973), 264 aste tutte concluse. Pool: L3 − B = **−0,0227**, IC95
  [−0,050, +0,004], semiampiezza 0,027 (obiettivo 0,030 raggiunto). Verdetto:
  **inconcludente**, con il lato positivo quasi chiuso: un vantaggio di L3
  sopra +0,004 di P(1°) è fuori dall'intervallo. Non si scrive «equivalenti».
- **L1 (contratto temporale)**: `src/fantabot/contratto_players.py` +
  aggancio additivo in `f0b_build_outputs.py` (parquet rigenerati e identici
  per impronta, 5/5); contratti scritti per 2024-25, 2025-26, 2026-27, 66/66
  colonne classificate con prova; `fvm`/`quot_fs_sett` posteriori con k = 0,
  disponibili nel 2026-27 (k = 3). 33 prove nuove.
- **L4 (calibrazione per segmento)**: la sonda sulle predizioni del 6/8
  passava tutti e cinque i criteri; il riadattamento con divisione per
  giocatore (per asta impossibile: il train è già mediato) la **ritratta**:
  copertura 0,886 (sopra la banda), pinball +1,39 %, ampiezza +37,7 %. **Non
  adottata**; 2 celle su 24 con n ≥ 30, quindi «per segmento» è in pratica
  globale. Risultato ritrattato lasciato accanto a chi lo ritratta.
- **L2 (§3ter con bersaglio onesto)**: `--bersaglio` nel pilota (predefinito
  invariato, 371 prove verdi), adattatore CSV→JSON, controfattuale rieseguito
  (passato). Prova decisiva a budget pieno: il cubo calibrato ha MAE sulle
  presenze realizzate **peggiore** del bersaglio onesto da solo (+0,0346,
  es 0,0021, |t| 16,8); theta funziona come meccanismo (C2 meglio di C1) ma
  resta sotto il bersaglio. **Non superato**, nello stesso verso del 9/9.

Conseguenza per l'ordine dei lavori: il cubo non è dimostrato utile nemmeno
con ingressi puliti sulle marginali; la misura va spostata dove il cubo
lavora davvero (dipendenze, durata assenze, rose) o il livello va ridimensionato.
