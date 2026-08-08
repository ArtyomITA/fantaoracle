# -*- coding: utf-8 -*-
"""
Scarica archivio quotazioni fanta.soccer per stagioni 2020/21 -> 2025/26.
- Parsa la pagina stagione per ottenere giornate disponibili + data rilevazione.
- Scarica l'export Excel (.xls) per ogni giornata, valida, converte in CSV UTF-8.
- Output: data/raw/quotazioni/fantasoccer_{stagione}_g{NN}.csv
          data/raw/quotazioni/xls_originali/fantasoccer_{stagione}_g{NN}.xls
          data/raw/quotazioni/fantasoccer_date_rilevazioni.csv
"""
import io, os, re, time, random, sys, csv
import requests
import pandas as pd
from bs4 import BeautifulSoup

BASE = "https://www.fanta.soccer"
OUT = r"data\raw\quotazioni"
XLS_DIR = os.path.join(OUT, "xls_originali")
os.makedirs(XLS_DIR, exist_ok=True)

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
    "Accept-Language": "it-IT,it;q=0.9,en;q=0.8",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Referer": "https://www.fanta.soccer/it/archivioquotazioni/",
}

SEASONS = ["2020-2021", "2021-2022", "2022-2023", "2023-2024", "2024-2025", "2025-2026"]

def label(season):  # "2020-2021" -> "2020-21"
    a, b = season.split("-")
    return f"{a}-{b[2:]}"

session = requests.Session()
session.headers.update(HEADERS)

def fetch(url, binary=False):
    for attempt in range(5):
        try:
            r = session.get(url, timeout=60)
            if r.status_code in (429, 503):
                wait = 5 * (2 ** attempt)
                print(f"    HTTP {r.status_code} -> attendo {wait}s", flush=True)
                time.sleep(wait)
                continue
            if r.status_code != 200:
                print(f"    HTTP {r.status_code} su {url}", flush=True)
                return None
            return r
        except requests.RequestException as e:
            wait = 5 * (attempt + 1)
            print(f"    errore rete: {e} -> retry in {wait}s", flush=True)
            time.sleep(wait)
    return None

def parse_season_page(season):
    """Ritorna dict giornata -> data rilevazione (stringa dd/mm/yyyy) e lista giornate con link."""
    url = f"{BASE}/it/archivioquotazioni/A/{season}/"
    r = fetch(url)
    if r is None:
        return None, None
    soup = BeautifulSoup(r.text, "lxml")
    giornate = set()
    for a in soup.find_all("a", href=True):
        m = re.search(r"QuotazioniExcel\.aspx\?lang=it&serie=A&stagione=" + season + r"&giornata=(\d+)", a["href"])
        if m:
            giornate.add(int(m.group(1)))
    # mappa giornata->data dal testo pagina
    text = soup.get_text(" ", strip=True)
    date_map = {}
    for m in re.finditer(r"Giornata\s+(\d+)\s+(\d{2}/\d{2}/\d{4})", text):
        date_map[int(m.group(1))] = m.group(2)
    return sorted(giornate), date_map

def download_giornata(season, g):
    lab = label(season)
    xls_path = os.path.join(XLS_DIR, f"fantasoccer_{lab}_g{g:02d}.xls")
    csv_path = os.path.join(OUT, f"fantasoccer_{lab}_g{g:02d}.csv")
    if os.path.exists(csv_path) and os.path.getsize(csv_path) > 1000:
        return "skip"
    url = f"{BASE}/ArchivioQuotazioni/QuotazioniExcel.aspx?lang=it&serie=A&stagione={season}&giornata={g}"
    r = fetch(url, binary=True)
    if r is None:
        return "fail_net"
    content = r.content
    if not content.startswith(b"\xd0\xcf\x11\xe0"):  # OLE2 magic
        return "fail_notxls"
    try:
        df = pd.read_excel(io.BytesIO(content), engine="xlrd")
    except Exception as e:
        return f"fail_parse:{e}"
    if len(df) < 100:  # una giornata seria ha ~600 giocatori
        return f"fail_rows:{len(df)}"
    with open(xls_path, "wb") as f:
        f.write(content)
    df.to_csv(csv_path, index=False, encoding="utf-8", lineterminator="\n")
    return f"ok:{len(df)}"

def main():
    dates_rows = []
    summary = {}
    for season in SEASONS:
        lab = label(season)
        print(f"\n=== Stagione {season} ===", flush=True)
        giornate, date_map = parse_season_page(season)
        if giornate is None:
            print("  pagina stagione irraggiungibile, provo comunque 1..38", flush=True)
            giornate, date_map = list(range(1, 39)), {}
        if not giornate:
            print("  NESSUNA giornata trovata nella pagina (stagione assente?)", flush=True)
            summary[lab] = "no_giornate"
            continue
        print(f"  giornate disponibili: {len(giornate)} ({min(giornate)}-{max(giornate)})", flush=True)
        for g in sorted(date_map):
            dates_rows.append({"stagione": lab, "giornata": g, "data_rilevazione": date_map[g]})
        ok = failed = skipped = 0
        for g in giornate:
            res = download_giornata(season, g)
            if res == "skip":
                skipped += 1
            elif res.startswith("ok"):
                ok += 1
                print(f"  g{g:02d}: {res}", flush=True)
                time.sleep(random.uniform(1, 3))
            else:
                failed += 1
                print(f"  g{g:02d}: FALLITO {res}", flush=True)
                time.sleep(random.uniform(1, 3))
        summary[lab] = f"ok={ok} skip={skipped} fail={failed}"
        time.sleep(random.uniform(1, 3))
    # salva mappa date
    if dates_rows:
        pd.DataFrame(dates_rows).to_csv(os.path.join(OUT, "fantasoccer_date_rilevazioni.csv"),
                                        index=False, encoding="utf-8", lineterminator="\n")
    print("\n=== RIEPILOGO ===")
    for k, v in summary.items():
        print(f"  {k}: {v}")

if __name__ == "__main__":
    main()
