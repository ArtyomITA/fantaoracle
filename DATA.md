# Politica dati — cosa c'è nel repo e cosa devi rigenerare tu

Questo progetto impara da dati pubblici raccolti dal web (voti, quotazioni,
prezzi d'asta). **Quei dati grezzi NON sono nel repository**: appartengono
alle fonti (fantacalcio.it, fanta.soccer, GruppoEsperti, fantacalcio-online,
Understat, Transfermarkt) e non vanno ridistribuiti. Nel repo trovi il codice
per raccoglierli in autonomia, per uso personale.

## Cosa È incluso (derivati nostri)

| Cosa | Dove | Perché è ok |
|---|---|---|
| Pack demo per stagione | `demo/pack_*_demo.json` | Anagrafiche (fatti) + prezzi di riferimento CALIBRATI (statistiche aggregate e trasformate dal nostro pipeline) + predizioni dei NOSTRI modelli |
| Log di aste simulate | `demo/logs/*.jsonl` | Generati dal nostro motore: solo nomi (fatti) e prezzi inventati dai bot |
| Codice completo | `src/`, `scripts/`, `viz/` | Nostro |
| Report e analisi | `reports/`, `PIANO.md` | Nostre analisi (le quantificazioni citano le fonti) |

## Cosa NON è incluso (e come rigenerarlo)

Voti per giornata, quotazioni storiche, prezzi grezzi, xG, valori di mercato,
aste reali crowdsourced → cartelle `data/raw/` e `data/processed/`, ignorate
da git. Per ricostruirle:

1. `scripts/` contiene gli scraper/downloader usati (prefissi: `wayback_*`,
   `scrape_voti_*`, `download_*`, `ge_*`, `tm_*`) — leggi i commenti, rispetta
   i rate limit e i termini delle fonti. Uso personale.
2. Poi il pipeline di integrazione: `f0b_build_registry.py` → `f0b_match.py`
   → `f0b_build_outputs.py` (registry, matching nomi, parquet finali).
3. Poi modelli e pack: `f1_train_price.py`, `f1_make_predictions.py`,
   `f2_build_packs.py`.

## Cosa funziona SENZA rigenerare nulla

- **Replay del teatro**: `viz/replay.html?log=../demo/logs/asta_2025-26_esempio.jsonl`
- **Modalità Sedia** (giochi tu contro i 9 bot): `python scripts/f6_live_auction.py 2025-26`
  → usa automaticamente il pack demo. L'asta è completa; la **stagione
  post-asta** invece richiede i voti → resta disattivata finché non
  rigeneri i dati (il server lo dice all'avvio).
- Tornei/backtest completi: richiedono i dati rigenerati.

## Nota sui pesi dei modelli

Il modello prezzo usa TabPFN (Prior Labs): i pesi NON sono nostri e non sono
nel repo — la libreria `tabpfn` li scarica da sola alla prima esecuzione
(checkpoint v2, licenza Apache 2.0). Il modello valore (CatBoost) si riallena
in minuti dai dati rigenerati; le sue USCITE per le stagioni di test sono
già nel pack demo.
