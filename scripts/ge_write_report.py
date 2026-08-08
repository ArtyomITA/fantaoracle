# -*- coding: utf-8 -*-
"""Emette REPORT.md (documentazione del dataset) nella cartella di output."""
import os

OUT = r"data\raw\gruppoesperti"

REPORT = r"""# REPORT — Estrazione aste reali GruppoEsperti ("Progetto Prezzi Asta")

Data: 2026-08-06. Script in `scripts\` (`ge_parser.py` = parser riusabile; `ge_build_tidy.py` = build CSV+stats; `ge_download_extra.py` = download sheet extra; `ge_inspect*.py`, `ge_scan*.py`, `ge_verify_blocks.py`, `ge_test_parser.py` = ispezione/verifica).

## Output principale

`aste_reali_tidy.csv` — **55.678 righe giocatore-asta**, **245 aste**, 5 file sorgente. UTF-8, separatore virgola, header.

Schema colonne:

| colonna | tipo | note |
|---|---|---|
| source_file | str | nome file sorgente (prefisso `extra/` per gli sheet scaricati) |
| auction_id | int | progressivo per file (coincide con l'etichetta "ASTA n" del foglio) |
| componenti | int | partecipanti alla lega (6-12) |
| crediti_tot | int | budget della lega (250-1200) |
| modificatore | str | 'N', 'M', '+1M', '+1', vuoto (27 aste senza valore) |
| periodo | int | 0-3 (0 = asta estiva; valori piu' alti = piu' a ridosso/dopo l'inizio campionato; distribuzione per asta: 0=79, 1=23, 2=102, 3=41) |
| ruolo | str | P/D/C/A |
| player_raw | str | nome cosi' com'e' nel foglio (spesso lowercase, refusi inclusi, es. `mikitarian`) |
| prezzo | int | crediti pagati (min 0, max 630) |
| pct_budget | float | prezzo/crediti_tot, frazione 0-1, 6 decimali |

Nota: il foglio contiene anche una colonna col nome normalizzato (via foglio `Trascodifica`); non esportata — il name matching si fara' centralmente in Fase 0b. `pct_budget` e' ricalcolato, non copiato dalla colonna `%` del foglio.

## Layout scoperto (verificato a mano su blocchi 1, 2, 11, 140)

Foglio dati grezzi `Aste Concluse`, **blocchi impilati verticalmente** (non in bande di colonne — quelle sono nei fogli aggregati PORTIERI/DIFENSORI/... che contengono solo le %): 200 blocchi pre-formattati da 110 righe, tutti a colonna 1. Ancora = etichetta `COMPONENTI` (riga r): `ASTA n` a r-1, `PERIODO` r+1, `MODIFICATORE` r+2, `CREDITI TOT` r+3, valori 2 colonne a destra; intestazioni ruolo a r+6 (PORTIERI col 1, DIFENSORI col 7, CENTROCAMPISTI col 13, ATTACCANTI col 19); giocatori da r+7. Per sezione-ruolo con base c0: numero=c0, nome=c0+1, crediti=c0+2, %=c0+3, nome normalizzato=c0+4. Il parser scopre le ancore programmaticamente e delimita i blocchi con l'ancora successiva (non assume il passo 110).

## Aste e righe per file

| source_file | aste | righe | stagione stimata | aste 10 comp x 500 cr |
|---|---|---|---|---|
| gruppoesperti_prezzi_aste_reali_2024-25.xlsx | 11 | 2.535 | 2024/25 (Dovbyk, Morata, Lukaku-Napoli) | 2 |
| gruppoesperti_prezzi_aste_reali_2021-22circa.xlsx | 140 | 31.000 | 2021/22 (Vidal, Ospina, Mertens, Insigne, Kessie, CR7 a 630) | 27 |
| extra/1Uxv42LC7d68Y1ZLQ48Hh1ud74kJocO-lTom39eJFB_w.xlsx | 15 | 3.507 | 2024/25 (Dovbyk) | 2 |
| extra/1MeKG7yjCemQ1SFoi7RWmhni-iBMtYdPf9FtfdDQWZ5I.xlsx | 55 | 12.983 | **2023/24** (Giroud, Immobile, Zirkzee, Retegui; niente Dovbyk) | 24 |
| extra/1J4tILPqyErS5Ccpr0Dy-595D2PgubYxlPaqfX8-pjYw.xlsx | 24 | 5.653 | 2024/25 (Dovbyk) | 6 |
| **Totale** | **245** | **55.678** | | **61** |

Il README di fonti_prezzi marcava `1MeKG7...` come "template vuoto" e `1J4t...` come "vuoto": **note stale, contengono rispettivamente 55 e 24 aste** (le 55 del 2023/24 sono la copertura migliore di quella stagione). Il file "2021-22circa" ha 140 aste, non 125 come annotato.

## Distribuzione (componenti x crediti_tot), 245 aste totali

`10x500: 61 | 8x500: 59 | 8x1000: 31 | 10x1000: 24 | 10x300: 19 | 12x500: 5 | 6x1000: 5 | 10x250: 4 | 12x1000: 4 | 8x300: 4 | 8x800: 3 | 8x250: 3 | coda lunga (1-2 ciascuna): 6x600, 10x700, 6x500, 10x800, 10x600, 8x380, 8x450, 8x1200, 12x800, 8x700, 8x350, 8x400, 6x300, 8x600, 8x650, 12x300, 10x400, 12x250`

**Configurazione target (~10 partecipanti / ~500 crediti): 61 aste esatte 10x500** (~15.250 righe), 64 allargando a 10 componenti con 400-600 crediti. E' la combinazione piu' frequente del dataset. Target per stagione: 27 (2021/22), 24 (2023/24), 10 (2024/25, ma vedi duplicati sotto).

## Duplicati fra file (stessa asta caricata su piu' spreadsheet)

13 aste compaiono identiche (fingerprint: componenti+crediti+insieme giocatore/prezzo) in piu' file, tutte della stagione 2024/25:
- aste 1-7 del file principale 2024-25 = aste 1-7 di `1Uxv42...` = aste 1-7 di `1J4t...` (triplicate);
- aste 8-13 di `1Uxv42...` = aste 8-13 di `1J4t...` (duplicate).

`1J4t...` (24 aste) e' un superset di `1Uxv42...` (15 aste); il principale 2024-25 condivide solo le prime 7. **Aste uniche reali: 225** (245 - 20 copie). Nessun duplicato interno ai singoli file. In Fase 0b deduplicare con lo stesso fingerprint tenendo p.es. `1J4t` + le aste 8-11 del principale 2024-25.

## Download sheet extra (14 ID dal README)

Salvati in `extra\` (11 ok, log in `extra\download_log.json`):

- **Con dati d'asta in formato template** (parsati nel CSV): `1Uxv42...`, `1MeKG7...`, `1J4t...`.
- **Falliti (3)**: `17nJSWuLgeJbKXUZdzLVnFrDyUh5h7E-NBDbCqR5aUek` (HTTP 410, eliminato); `1jmMPIJjVGgfpbH1yRt0YGGgYZUrIH0T8UvvBdAdvjqQ` (HTTP 410); `1WCI4B2W_IJyykN2jCjiCMyDe4mOjs25ZcS2C3TM8pSs` (non-nativo, HTTP 404 anche via `drive.usercontent.google.com` e `uc?export=download&confirm=t`: file rimosso da Drive). Non recuperabili senza nuovo link dal thread del forum.
- **Scaricati ma NON in formato template** (dati d'asta grezzi per-squadra, una colonna per partecipante, senza metadati lega — non parsabili con lo stesso codice; possibile integrazione manuale futura):
  - `1STf54UI3M7qPTG1xo-ZcoKa3zmH_d5BEEiqR5jsmqnc` — "Asta 500 8 Partecipanti", era Handanovic/Onana-Inter (~2021/22), 8 rose con prezzi.
  - `1NWhc0N5hVrKKMjPbLzEiNKRz3PbClFzGmSJ0R7sjEd8` — "fut league", 6+ rose con prezzi (era Kim/Bremer-Torino, ~2021/22-2022/23).
  - `1NcS1jKQGU0yO1hydtFQonO0YJ-yUpVXbapwYBzI8P6A` — 9 fogli, piu' leghe (fantaball, FUT LEAGUE, mantra multiruolo...), rose con prezzi.
  - `19V3e-54FTPMIjOez_f3XsM7ce39x4RaaJWVyR5Gp3NA`, `1stdSoivNLfLclpldTApwbQaxZeIEU65Wz_wot42vUy4` — rose per squadra con prezzi (~2022/23: Kim, Erlic, Monza in A).
  - `1w_EFGFlnfw9fSpnVCUvsaLygHV_IxePSi5tbTXRY13U`, `1WB6W3_JoO8pnFtCBwHDEiEQPdKWQNQmMJBDcPkTzEtc` — "TutteLeRose", export rose Leghe (data download 08-09/202x), con modificatore.
  - `11lb2kwrvyXQFff5Am6Z6MbIDQ5C4mRthemmaJnbo_Tg` — lega multi-divisione (Serie A/B/Pro + riparazioni), formato proprio.

## Problemi / caveat

1. **File principale 2024-25 povero**: solo 11 aste (7 duplicate negli extra). La stagione 2024/25 netta vale ~28 aste uniche. 2022/23 e 2025/26 restano scoperte (gli sheet 410/404 erano i candidati; ricontrollare il thread forum `t=181911` a fine agosto 2026 per l'edizione 2025-26).
2. **Stagione stimata per file, non per asta** (marker di rosa). Le aste con `periodo` 2-3 possono includere riparazioni invernali con rose leggermente diverse.
3. **Rose incomplete/anomale**: 110 aste su 245 hanno n. righe != componenti*25 (di solito poche righe in meno; a volte rose extra, es. asta 6 di `1J4t` con 239 righe su 200 attese: possibile `componenti` errato inserito dall'utente). Dati crowdsourced: attendersi rumore.
4. **6 righe con nome ma senza prezzo** scartate (4 nel 2021-22, 1 in `1MeKG7`, 1 in `1J4t`).
5. **Nomi sporchi**: `player_raw` mantiene case misto, refusi (`mikitarian`, `sczesny`), suffissi disambiguanti (`VASQUEZ D.`, `ZAPATA D`). Name matching rimandato a Fase 0b (i fogli `Trascodifica` interni possono aiutare).
6. **Prezzo 0 presente** (assegnazioni d'ufficio/svincoli): non filtrato.
7. `modificatore` non normalizzato ('M' vs '+1M' vs '+1' vs 'N' vs vuoto: semantica del forum non documentata nei fogli).

## File prodotti

- `data\raw\gruppoesperti\aste_reali_tidy.csv` (55.678 righe dati + header)
- `data\raw\gruppoesperti\build_stats.json` (statistiche machine-readable, inclusi i duplicati)
- `data\raw\gruppoesperti\extra\*.xlsx` (11 file) + `download_log.json`
- `data\raw\gruppoesperti\REPORT.md` (questo file)
"""

if __name__ == "__main__":
    path = os.path.join(OUT, "REPORT.md")
    with open(path, "w", encoding="utf-8") as f:
        f.write(REPORT)
    print("scritto", path, len(REPORT), "caratteri")
