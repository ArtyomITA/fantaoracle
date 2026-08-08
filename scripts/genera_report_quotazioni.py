# -*- coding: utf-8 -*-
"""Genera REPORT.md in data/raw/quotazioni/ con inventario dinamico dei file scaricati."""
import glob, os
import pandas as pd

OUT = r"data\raw\quotazioni"
SEASONS = ["2020-21", "2021-22", "2022-23", "2023-24", "2024-25", "2025-26"]

# inventario fanta.soccer
fs_lines = []
fs_tot_files = 0
fs_tot_rows = 0
for s in SEASONS:
    files = sorted(glob.glob(os.path.join(OUT, f"fantasoccer_{s}_g*.csv")))
    gs = sorted(int(os.path.basename(f).split("_g")[1][:2]) for f in files)
    rows = sum(len(pd.read_csv(f)) for f in files)
    fs_tot_files += len(files)
    fs_tot_rows += rows
    missing = sorted(set(range(1, 39)) - set(gs))
    gtxt = "1-38 complete" if not missing else f"{gs}" if len(gs) <= 10 else f"{len(gs)}/38 (mancanti: {missing})"
    fs_lines.append(f"| {s} | {len(files)}/38 | {gtxt} | {rows} |")

# inventario fantacalcio.it
fc_lines = []
fc_tot_rows = 0
for s in SEASONS:
    p = os.path.join(OUT, f"fantacalcioit_{s}.csv")
    if os.path.exists(p):
        df = pd.read_csv(p, dtype=str)
        fvm = "si" if (df.fvm_classic.fillna("-") != "-").any() else "no (colonna a '-')"
        fc_tot_rows += len(df)
        fc_lines.append(f"| {s} | {len(df)} | {fvm} |")
    else:
        fc_lines.append(f"| {s} | MANCANTE | - |")

# date settembre
d = pd.read_csv(os.path.join(OUT, "fantasoccer_date_rilevazioni.csv"))
d["dt"] = pd.to_datetime(d.data_rilevazione, format="%d/%m/%Y")
sept_lines = []
for s in SEASONS:
    grp = d[d.stagione == s]
    if grp.empty:
        continue
    year = int(s[:4])
    sept = grp[grp.dt >= pd.Timestamp(year=year, month=9, day=1)].sort_values("dt")
    first = sept.iloc[0]
    g1 = grp[grp.giornata == 1].data_rilevazione.iloc[0]
    sept_lines.append(f"| {s} | g{int(first.giornata)} ({first.data_rilevazione}) | g1 ({g1}) |")

xls_count = len(glob.glob(os.path.join(OUT, "xls_originali", "*.xls")))

report = f"""# REPORT — Quotazioni ufficiali storiche 2020/21 -> 2025/26

Data generazione: 2026-08-06. Output dir: `data\\raw\\quotazioni\\`
Script in `scripts\\`: `download_fantasoccer.py` (tutte le giornate),
`download_fantasoccer_minimo.py` (giornate minime + date), `scrape_fantacalcioit.py`, `genera_report_quotazioni.py`.

## Fonte 1: fanta.soccer (archivio quotazioni per giornata)

**Meccanismo**: export Excel gratuito, senza account, URL diretto:
`https://www.fanta.soccer/ArchivioQuotazioni/QuotazioniExcel.aspx?lang=it&serie=A&stagione={{YYYY-YYYY}}&giornata={{N}}`
(N = 1..38; la pagina stagione `https://www.fanta.soccer/it/archivioquotazioni/A/{{YYYY-YYYY}}/` elenca le giornate con la data di rilevazione).
Il file servito e' un vero **.xls** (BIFF/OLE2) nonostante il content-type dichiari xlsx; nome es. `Quotazioni_1a_Serie A.xls`.

**File salvati**:
- CSV convertiti (UTF-8, virgola, header): `fantasoccer_{{stagione}}_g{{NN}}.csv`
- .xls originali in `xls_originali\\` ({xls_count} file)
- mappa giornata->data: `fantasoccer_date_rilevazioni.csv` (colonne: `stagione,giornata,data_rilevazione`; {len(d)} righe = 38 x 6 stagioni)

**Schema colonne** (identico per tutte le stagioni/giornate):
`Codice` (id giocatore fanta.soccer, int), `Cognome`, `Nome` (iniziale puntata, spesso vuoto), `Squadra`, `Ruolo` (P/D/C/A Classic), `Giornata` (int), `Quotazione` (int).

**Copertura scaricata**:

| Stagione | Giornate | Dettaglio | Righe totali |
|---|---|---|---|
{chr(10).join(fs_lines)}

Totale: {fs_tot_files} file CSV, {fs_tot_rows} righe.

**Snapshot d'asta (prima rilevazione post-mercato estivo, inizio settembre)** — da `fantasoccer_date_rilevazioni.csv`:

| Stagione | Prima rilevazione >= 1 set | Quotazioni iniziali |
|---|---|---|
{chr(10).join(sept_lines)}

Nota 2020-21: stagione partita tardi causa COVID, la g1 (19/09/2020) e' gia' essa stessa lo snapshot post-mercato.

## Fonte 2: fantacalcio.it (senza login)

**Meccanismo**: pagina `https://www.fantacalcio.it/quotazioni-fantacalcio/{{YYYY-YY}}` — la tabella completa (~700 giocatori)
**e' presente nell'HTML anonimo**, niente login ne' JS necessari. Scrapata con requests+BeautifulSoup.
L'export Excel ufficiale (`/api/v1/Excel/prices/{{seasonId}}/1`, seasonId 15=2020-21 ... 20=2025-26) **richiede login (HTTP 401)** -> non usato, come da regola NO login.

**File salvati**: `fantacalcioit_{{stagione}}.csv` (UTF-8, virgola, header).

**Schema colonne**:
`player_id` (id fantacalcio.it, dall'URL scheda giocatore), `nome`, `squadra` (sigla 3 lettere),
`ruolo_classic` (P/D/C/A), `ruolo_mantra` (POR/DC/DD/DS/E/M/C/W/T/A/PC, anche multipli tipo "W;A"),
`qt_i_classic` (Qt.I), `qt_a_classic` (Qt.A), `fvm_classic` (FVM/1000),
`qt_i_mantra`, `qt_a_mantra`, `fvm_mantra`.

**Copertura**:

| Stagione | Righe | FVM disponibile |
|---|---|---|
{chr(10).join(fc_lines)}

Totale: {fc_tot_rows} righe su 6 file.

## Differenze tra le fonti

- **fanta.soccer**: UNA sola colonna `Quotazione` per giocatore/giornata — NON riporta Qt.I/Qt.A/FVM.
  E' la quotazione corrente alla data di rilevazione della giornata. Il valore aggiunto e' la **serie storica per giornata** (38 snapshot/stagione).
- **fantacalcio.it**: riporta Qt.I (iniziale), Qt.A (attuale) e FVM (Fanta Valore di Mercato /1000), sia Classic che Mantra,
  ma UN solo snapshot per stagione. Per le stagioni archiviate Qt.A e' il valore all'ultimo aggiornamento della stagione (fine campionato).
  **FVM assente** (colonna a "-") per 2020-21 e 2021-22; presente dal 2022-23 in poi.
- Scale non identiche: fantacalcio.it e' la fonte "ufficiale" delle leghe (Qt.I usata come base d'asta);
  fanta.soccer usa un proprio listino (valori simili ma non sovrapponibili 1:1).
- Id giocatore diversi tra le fonti (`Codice` fanta.soccer vs `player_id` fantacalcio.it): il name-matching andra' fatto
  su cognome+squadra (fase 0b).

## Problemi / note

- Export Excel fantacalcio.it dietro login (401): documentato, saltato. La tabella HTML anonima e' pero' completa.
- I file fanta.soccer sono .xls reali con estensione/MIME incoerenti: letti con xlrd, convertiti in CSV.
- Righe per giornata variabili (536-687): fanta.soccer include/esclude giocatori man mano che entrano/escono dalle rose.
- Nessuna fonte irraggiungibile; nessun 429/503 incontrato durante i download.
"""

# nota dinamica se il download completo e' ancora in corso
if fs_tot_files < 228:
    report += f"""- ATTENZIONE: al momento della generazione di questo report il download completo per-giornata era ancora in corso
  in background ({fs_tot_files}/228 file): le giornate minime richieste (1-4, 19, 38) sono garantite per TUTTE le stagioni,
  le restanti si stanno riempiendo progressivamente (rilanciare `python genera_report_quotazioni.py` per aggiornare la tabella).
"""

with open(os.path.join(OUT, "REPORT.md"), "w", encoding="utf-8", newline="\n") as f:
    f.write(report)
print(f"REPORT.md scritto. fantasoccer files={fs_tot_files} rows={fs_tot_rows}; fantacalcioit rows={fc_tot_rows}")
