# -*- coding: utf-8 -*-
"""Genera il REPORT.md richiesto dal task nella cartella di output wayback_prices."""

CONTENT = """# REPORT — Storico prezzi asta fantacalcio-online.com via Wayback Machine

Data esecuzione: 2026-08-06. Script in `scripts\\` (`wayback_cdx.py`, `wayback_cdx_domain.py`, `wayback_cdx_perurl.py`, `wayback_download.py`, `wayback_parse.py`, `wayback_validate.py`).

## Scoperta chiave

La pagina live `/it/asta-fantacalcio-stima-prezzi` ha snapshot **solo dal 2024-05-19 in poi** (6 snapshot totali, nessuno per le stagioni vecchie). Per andare indietro sono servite due fonti alternative trovate con ricerca CDX domain-wide (`filter=urlkey:.*asta.*` e `.*prezzi.*` su tutto il dominio, 513+16 URL unici, salvati in `snapshots_cdx_domain.json`):

1. **Mirror `s7.fantacalcio-online.com`** — copia identica del sito con 2 snapshot della pagina stima-prezzi: 2021-05-18 (stagione 2020/21) e 2022-01-26 (stagione 2021/22), **schema completo a 4 colonne prezzo, nessuna cella bloccata**.
2. **Pagine per-stagione `/it/serie-a/{stagione}/asta-fantacalcio-prezzi-acquisto`** — esistono dal 2018-2019 in poi. Schema diverso: solo la colonna `8 (350 K.)` è libera; `10 (350K)`, `12 (350K)` e `Tot.(%)` sono bloccate server-side ("Registrati per visualizzare") → per queste stagioni si recupera **solo p350_8sq**.

Nessuna pagina prezzi esiste per stagioni precedenti il 2018/19 (né sul dominio principale né su forum/blog/s7): **2018/19 è il limite storico assoluto**.

## File CSV prodotti (UTF-8, separatore virgola, header)

Schema target: `ruolo,squadra,nome,kap,p350_8sq,p350_10sq,p500_8sq,p500_10sq,mv,presenze`

| File | Stagione | Righe | Con prezzo | Colonne prezzo compilate | Fonte snapshot |
|---|---|---|---|---|---|
| `prezzi_2018-19_20210623032233.csv` | 2018/19 | 641 | **194** | solo p350_8sq | s7, pagina per-stagione, 23/6/2021 |
| `prezzi_2019-20_20200215065824.csv` | 2019/20 | 668 | **399** | solo p350_8sq | www, pagina per-stagione, 15/2/2020 (completa, arriva fino a CR7) |
| `prezzi_2020-21_20210518002802.csv` | 2020/21 | 648 | **535** | tutte e 4 (382/494/370/508) | s7, stima-prezzi, 18/5/2021 |
| `prezzi_2021-22_20220126223034.csv` | 2021/22 | 663 | **562** | tutte e 4 (342/519/381/534) | s7, stima-prezzi, 26/1/2022 |
| `prezzi_2021-22_20220524131004.csv` | 2021/22 (secondario) | 644 | 303 | solo p350_8sq | www, pagina per-stagione, 24/5/2022 (stato fine stagione) |
| `prezzi_2022-23_20240123141420.csv` | 2022/23 | 668 | **386** | solo p350_8sq | www, pagina per-stagione, 23/1/2024 (completa) |
| `prezzi_2024-25_20250214053906.csv` | 2024/25 | 688 | **541** | tutte e 4 (354/493/325/474) | www, stima-prezzi, 14/2/2025 |
| `prezzi_2024-25_20250616102603.csv` | 2024/25 (secondario) | 690 | 497 | tutte e 4 (335/442/317/464) | www, stima-prezzi, 16/6/2025 |
| `prezzi_2025-26_20260411054907.csv` | 2025/26 | 649 | **480** | tutte e 4 (330/429/329/457) | www, stima-prezzi, 11/4/2026 |

Confronto con fonti_prezzi/ esistenti: **2024/25: 541 > 331 note** (+210); **2025/26: 480 > 334 note** (+146). Per 2023/24 nessun miglioramento trovato (per-stagione 23/1/2024 = 423 righe solo-p350_8 < 433 note a schema pieno → non emesso).

Stagione identificata dal set squadre (match 20/20 per tutti i file). `mv` e `presenze` sono vuote in TUTTI gli snapshot (celle vuote nell'HTML, coerente con i CSV già in fonti_prezzi). Righe senza prezzo mantenute (coerente con schema esistente). Squadre includono anche "Estero"/"Serie Minori" per giocatori usciti dalla Serie A al momento dello snapshot (es. Kvaratskhelia "Estero" nello snapshot feb-2025: squadra = squadra alla data snapshot, non alla data d'asta).

## Snapshot enumerati / scelti / scartati

Elenco completo in `snapshots_cdx.json` (per-URL, 15 URL interrogati) e `snapshots_cdx_domain.json` (ricerca domain-wide). Sintesi decisioni:

| Stagione | Candidati testati (ts → righe con prezzo) | Scelto | Motivo scarto altri |
|---|---|---|---|
| 2018/19 | s7 20200928→154, s7 20210119→188, s7 20210411→187, s7 20210623→**194**, www 20210725→186, www 20250616→79, www 20251118→76 | s7 20210623 | decadimento dati nei più tardi; nessuno snapshot in-stagione esiste (unico 20190422 = HTTP 500) |
| 2019/20 | www 20200215→**399** (completa), www 20200804→359 (troncata 1MB), s7 20200928→207 (decaduta) | www 20200215 | troncamento/decadimento |
| 2020/21 | stima s7 20210518→**535** (4 col), per-stagione www 20201204→374 (1 col) | s7 20210518 | schema più ricco e più tardo |
| 2021/22 | stima s7 20220126→**562** (4 col), per-stagione 20220524→303, 20230330→258 | s7 20220126 + secondario 20220524 | 20230330 decaduta |
| 2022/23 | s7 20221203→337, www 20230330→329, www 20230603→306 (troncata), www 20240123→**386** (completa) | www 20240123 | nessuno snapshot stima-prezzi esiste per questa stagione |
| 2023/24 | per-stagione 20240123→423, 20240722→340 (troncata) | nessuno | non batte le 433 righe già note (stima 20240519 in fonti_prezzi) |
| 2024/25 | stima 20250214→**541**, stima 20250616→497, per-stagione 20250113→339, 20250326→336 | stima 20250214 + secondario 20250616 | per-stagione ridondanti |
| 2025/26 | stima 20260411→**480**, per-stagione 20260209→351 | stima 20260411 | — |

## Schema reale per layout

- **Layout "stima"** (pagina stima-prezzi, 2021→2026 invariato): `RT | Squadra | Nome | Kap. | 350K (8) | 350K (10) | 500K (8) | 500K (10) | M.V. | Pres.` → mappa 1:1 sullo schema target.
- **Layout "per-stagione"** (2018-2019→2025-2026 invariato): `RT | Squadra | Nome | Kap. | 8 (350 K.) | 10 (350 K.) | 12 (350 K.) | Tot. (%) | M.V. | Pres.` — solo `8 (350 K.)` in chiaro, le altre 3 colonne bloccate con icona `fantaicon-locked` → nel CSV: `p350_8sq` compilata, `p350_10sq/p500_8sq/p500_10sq` vuote. La colonna `12 squadre` non esiste nello schema target e comunque è bloccata.
- **Ruoli**: fino al 2025 span `tag role label-N` con lettera dentro (1=P, 2=D, 3=C, 5=A). Dallo snapshot apr-2026 (e in parte già dic-2025): numerazione nuova 1=P, 2=D, 4=C (mostrato "T"!), 6=A (span vuoto). Il parser mappa dal numero label, non dalla lettera → ruoli completi anche nel file 2025-26 (a differenza del CSV dic-2025 in fonti_prezzi che ha ruoli vuoti).

## Problemi e limiti

1. **Troncamento 1MB**: molte catture Wayback delle pagine per-stagione sono tagliate esattamente a 1.048.576 byte (limite del crawler). Le righe sono ordinate per Kap crescente → il taglio elimina i TOP player. File colpiti tra gli scelti: solo `prezzi_2018-19` (si ferma a Kap ~20, mancano CR7/Higuain/Icardi/Piatek ecc.). Gli altri file scelti sono completi (verificato: ultima riga = top player della stagione).
2. **Decadimento dati sul sito**: le pagine per-stagione ricalcolano contro il listino corrente — i giocatori usciti dalla Serie A vengono azzerati (kap=0, prezzo vuoto) nelle catture successive. Per questo lo snapshot migliore per 2018/19 è del 2021 (194 prezzi) mentre quelli 2025 ne hanno solo 76-79, e per 2019/20 il migliore è feb-2020 in-stagione. Per 2018/19 il danno è doppio (troncamento + decadimento): i top player sono irrecuperabili da qualunque snapshot esistente.
3. **2022/23 senza schema completo**: nessuno snapshot stima-prezzi esiste tra ott-2022 e lug-2023 (buco tra s7 gen-2022 e www mag-2024) → solo p350_8sq per quella stagione.
4. **Duplicato**: "RADUNOVIC Boris / Serie Minori" appare 2 volte nei file 2024/25 (duplicato genuino del sito, righe senza prezzo).
5. **Separatore**: questi CSV usano la virgola (come da specifica task); i CSV già in `fonti_prezzi/` usano il punto e virgola — attenzione in fase di merge.
6. **Rate limit archive.org**: qualche timeout/504 sull'API CDX, risolti con retry+backoff. Download effettuati con flag `id_` (contenuto originale senza toolbar Wayback), pause 6-9s.
7. La dicitura "aggiornato al" delle pagine per-stagione mostra la data di cattura (campo dinamico), non la data reale di ultimo aggiornamento dati.

## File di supporto

- `snapshots_cdx.json` — elenco completo snapshot per i 15 URL candidati (con digest, status, length).
- `snapshots_cdx_domain.json` — 520 URL unici asta/prezzi trovati sul dominio.
- `chosen.txt` — mapping file HTML → stagione usato dall'emissione.
- `html/` — 27 snapshot HTML grezzi scaricati (inclusi i candidati scartati, per riproducibilità).
"""

with open(r"data\raw\wayback_prices\REPORT.md", "w", encoding="utf-8") as f:
    f.write(CONTENT)
print("REPORT.md written,", len(CONTENT), "chars")
