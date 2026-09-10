# Punto di ripresa tecnico — Copilota per l'asta del 10 settembre 2026

Aggiornato alle 07:00 del 10/9. Riguarda **solo** la consegna operativa per
l'asta delle 19:30. La ricerca sui cinque livelli: [`RIPRESA.md`](RIPRESA.md)
e [`reports/STATO_LIVELLI_20260910.md`](reports/STATO_LIVELLI_20260910.md).
Guida d'uso: [`GUIDA_ASTA.md`](GUIDA_ASTA.md).

## Che cosa è stato corretto nella notte, con la prova

| difetto | correzione | prova |
|---|---|---|
| server di prova scrivevano fra le sessioni vere | `--ledger PATH` | prove in `data/copilot/prove/` |
| il «riferimento» dei piani non era il piano del bot (`forced_spend` mancante: attacco 93 contro 191) | `contesto_piani` passa la quota attacco; `piani._risolvi` ripiega e lo dichiara | `test_piani_riferimento_uguale_al_piano_del_bot` |
| ricerca cieca agli accenti (17 nomi) e ordinata per valore | `senza_accenti`, ordine per pertinenza, `tutti=1` | `test_ricerca_senza_accenti`, `..._pertinenza_e_tutti` |
| `/copilot/advice?price=abc` chiudeva la connessione; GET/POST malformati idem | `do_GET`/`do_POST` avvolti, 400/500 JSON | `test_get_malformati_rispondono_400` |
| infortunati a valore pieno; nessun avviso in pagina | `rettifica_indisponibili` (attiva solo se il pack è più vecchio delle fonti: oggi no, f9 li applica già) + chip in pagina | `test_rettifica_indisponibili.py` (7), `test_indisponibili_valore_rettificato_e_dichiarato` |
| attivi del listone assenti dal pack non registrabili | giocatori senza previsione creati in memoria | `test_senza_previsione_registrabili` (oggi salta: col pack nuovo sono 0) |
| nessun modo di togliere un nome dal piano | `POST /copilot/escludi`, persistito nel ledger, bottone in scheda | `test_escludi_dal_piano`, provato in pagina |
| tetto cieco all'obbligo di completare la rosa | se i comprabili del ruolo bastano appena, tetto = massimo legale | `test_obbligo_di_completare` |
| setup rifatto a metà asta mandava le casse sotto zero | `stato_valido` controlla speso + slot | `test_setup_non_scende_sotto_lo_speso` |
| il MILP dei piani teneva il lock per secondi | `piani_alternativi` calcola fuori dal lock, flag `superato` | prova f6 25/25 |
| porta occupata scoperta dopo il caricamento del pack; due Copiloti sullo stesso ledger | bind prima del pack; `.lock` con PID (`psutil`) | avvio con porta occupata esce con messaggio |
| il menu non vedeva un Copilota già acceso | `probe_auction` prova anche `/copilot/state` | letto nel codice |
| `max_bid = budget + 1` a rosa piena; `piano_prezzo` «ok» su venduti; piani con A pieno | 0 a rosa piena; 400; solo il riferimento con nota | prove f5bis/f6 |
| UI: martelletto sotto la piega, griglie ricostruite ogni 2 s, piani stantii dopo ANNULLA, rilanci silenziosi, Invio sull'omonimo sbagliato | `viz/copilot.html` riscritto in quelle parti (+448/−77) | 14 script Playwright in `scratchpad/w2`, tutti exit 0; percorso completo nel browser dal menu |

## Aggiunta delle 16:50: indicatore «possono superarti» e asta intera dalla pagina

- `decisione_operativa` e `/copilot/plan` restituiscono `concorrenti_sopra_tetto`,
  `concorrenti_nomi`, `concorrenti_max` (avversari con slot libero nel ruolo e
  massimo legale ≥ tetto + 1); la pagina li mostra al banco e nella ROSA TARGET.
  Solo informazione: tetti e azioni invariati (diff: 5 blocchi in f10, 2 in
  copilot.html; backup in `data/_backup_fable_20260910/pre_indicatore/`).
- Asta intera di 250 lotti giocata **dalla pagina** (Playwright, 1366×768):
  12 target rubati dagli avversari, Malen a Sara sopra il tetto, U-U e
  riacquisto, escludi/riammetti, server ucciso al lotto 150 e ripreso, export;
  pagina e server coincidenti a tutti i 250 lotti; consiglio max 0,16 s,
  martelletto max 0,76 s, piani ≤ 1,7 s; rosa finale 3/8/8/6. Script:
  `reports/asta_20260910/asta_intera.py`. Nessun difetto bloccante; quattro
  rilievi bassi in `reports/asta_20260910/B_asta_intera.md`.
- Revisione finale: prove 32/32, 23/23, 24/24, 25/25; suite 661 passati, 2
  saltati, 5 xfail, 1 rosso (esito L3, preesistente); macchina pulita.

## Aggiunte delle 17:35

- Pannello **RIGORISTI** dinamico (`/copilot/rigoristi`, 20 squadre, 120 nomi
  agganciati su 120) e 4 correzioni CSS dall'ispezione visiva (24 screenshot,
  due larghezze); `scripts/asta_registra.py` per registrare da riga di comando.
- Dati delle 17:00 portati nel pack con f9+f2 (obiettivo ricopiato, confronto
  8/8, impronta `2303dcbf9de8`); indisponibili 56 nel file di eleggibilità;
  note esperto con il mercato di oggi (fantacalcio-online: Malen 205, Lautaro
  184) e i rigoristi Sky.
- 31 rose candidate simulate (40 + 200 scenari): **nessuna batte il
  riferimento** oltre il rumore; «due bomber» costa 35-58 punti; escludere i
  quattro giudicati male dall'esperto costa ~50 punti; comprare ai prezzi di
  mercato invece che ai q50 costa 38-60. Rapporto in
  `reports/asta_20260910/rose_candidate.md`.
- Revisore: 32/32, 23/23, 24/24, 25/25; asta di 120 lotti dalla pagina senza
  anomalie; macchina pulita.

## Verifiche eseguite (riprodotte, non dichiarate)

| prova | esito |
|---|---|
| riverifica delle prove della sessione precedente (agenti indipendenti) | 32/32, 16/16, 23/23, 24/24, 25/25 |
| stesse prove sul codice corretto e sul pack nuovo | 32/32, 23/23, 24/24, 25/25 |
| suite (`PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python -m pytest tests -q`) | ore 12:10: **597 passati, 2 saltati, 5 xfail dichiarati, 1 rosso** (asserzione d'esito L3 `test_il_piano_cambia_davvero_l_asta`, spiegata in `reports/livelli_20260910/L3_banco.md`; non riguarda il Copilota). Revisore: 26 impronte del percorso d'asta identiche |
| percorso nel browser dal menu: avvio, tavolo, ricerca «calo», consiglio, martelletto a 12, piani, annulla con `U`, escludi/riammetti Colombo, Malen a Marco per 190, spegnimento, RIPRENDI dal menu | stato identico dopo la ripresa, console pulita (due `ERR_CONNECTION_REFUSED` del menu durante il riavvio, attesi) |
| simulazione di politiche di prezzo (36 semi, 180 aste appaiate, avversari che pagano il mercato) | nessuna variante batte quella attuale; il heat finale resta 0,997 ± 0,002 |

## Pack

- rigenerato alle 06:21 con `f11_refresh_all.py`: K = 3, 594 giocatori,
  impronta `71ec262b4bdf` (dopo f12);
- `b_objective`: il pack rigenerato ne usciva **senza** (f12 non è nella
  catena); prima copiato dal 6/9, poi ricalcolato alle 07:20 con f12 (100
  simulazioni): stessa configurazione (lam 0,5, attacco 35-50 %, 3-4-3),
  P(1°) 0,56 in scelta e 0,57 ± 0,05 in verifica. Impronta finale `71ec262b4bdf`;
- confronto col pack del 6/9: 8/8 controlli; spostamenti mediani di q50 nulli,
  di valore −0,1…−1,6 per ruolo; i più grandi vengono da infortuni e
  titolarità (Locatelli 225 → 128, McKennie 198 → 109, Dimarco 249 → 183);
- piano iniziale: 3-4-3, Malen 145 (tetto 174), attacco 221, costo 499,7;
  alternative Ramos G., Laurienté, Martinez L., Hojlund entro l'1,1 %;
- backup del pack del 6/9 e dei file toccati in `data/_backup_fable_20260910/`.

## Che cosa NON è stato fatto, e perché

- **Cubo non rigenerato**: non autorizzato e non necessario all'asta; resta
  stale (vedi STATO_LIVELLI).
- **Politica di prezzo invariata**: la simulazione non ha trovato una variante
  migliore secondo il criterio scritto prima.
- Rilievi lasciati aperti: il menu non usa sempre la porta digitata (con 8770
  non serve); «RIPRENDI l'ultima» sceglie per data di modifica; un Copilota
  orfano non si ferma dal menu; 37 dei 379 prezzi di mercato del bundle sono
  del 2025-26; tre portieri con q10 > q50 dopo la miscela.
- Le due asserzioni L3 cadute **non** sono state indebolite.

## Comandi

```bash
python scripts/f10_copilot.py 2026-27 --porta 8770
```

```bash
python scripts/f14_listino_offline.py 2026-27
```

```bash
python scripts/f4_eleggibilita.py
```

```bash
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python -m pytest tests -q -p no:cacheprovider
```
