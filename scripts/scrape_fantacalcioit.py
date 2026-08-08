# -*- coding: utf-8 -*-
"""
Scrapa quotazioni fantacalcio.it (HTML anonimo, no login) per stagioni 2020-21 -> 2025-26.
Output: data/raw/quotazioni/fantacalcioit_{stagione}.csv
Colonne: player_id, nome, squadra, ruolo_classic, ruolo_mantra,
         qt_i_classic, qt_a_classic, fvm_classic, qt_i_mantra, qt_a_mantra, fvm_mantra
NB: l'export Excel /api/v1/Excel/prices/{id}/1 richiede login (401) -> non usato.
"""
import os, re, time, random
import requests
import pandas as pd
from bs4 import BeautifulSoup

OUT = r"data\raw\quotazioni"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
    "Accept-Language": "it-IT,it;q=0.9,en;q=0.8",
}
SEASONS = ["2020-21", "2021-22", "2022-23", "2023-24", "2024-25", "2025-26"]

S = requests.Session()
S.headers.update(HEADERS)

def fetch(url):
    for attempt in range(5):
        try:
            r = S.get(url, timeout=60)
            if r.status_code in (429, 503):
                wait = 5 * (2 ** attempt)
                print(f"  HTTP {r.status_code} -> attendo {wait}s", flush=True)
                time.sleep(wait)
                continue
            return r
        except requests.RequestException as e:
            print(f"  errore rete {e} -> retry", flush=True)
            time.sleep(5 * (attempt + 1))
    return None

def num(cell):
    t = " ".join(cell.get_text().split()) if cell else ""
    return t if t else ""

def scrape_season(season):
    url = f"https://www.fantacalcio.it/quotazioni-fantacalcio/{season}"
    r = fetch(url)
    if r is None or r.status_code != 200:
        print(f"  FALLITO: status {r.status_code if r else 'rete'}", flush=True)
        return None
    soup = BeautifulSoup(r.text, "lxml")
    table = soup.find("table", class_="pills-table")
    if table is None:
        print("  tabella non trovata", flush=True)
        return None
    rows = []
    for tr in table.find_all("tr", class_="player-row"):
        link = tr.find("a", class_="player-link")
        name = " ".join(link.get_text().split()) if link else ""
        pid = ""
        if link and link.get("href"):
            m = re.search(r"/(\d+)/\d{4}-\d{2}$", link["href"]) or re.search(r"/(\d+)$", link["href"].rstrip("/"))
            if m:
                pid = m.group(1)
        cells = {td.get("data-col-key"): td for td in tr.find_all("td") if td.get("data-col-key")}
        rows.append({
            "player_id": pid,
            "nome": name,
            "squadra": num(cells.get("sq")),
            "ruolo_classic": (tr.get("data-filter-role-classic") or "").upper(),
            "ruolo_mantra": (tr.get("data-filter-role-mantra") or "").upper(),
            "qt_i_classic": num(cells.get("c_qi")),
            "qt_a_classic": num(cells.get("c_qa")),
            "fvm_classic": num(cells.get("c_fvm")),
            "qt_i_mantra": num(cells.get("m_qi")),
            "qt_a_mantra": num(cells.get("m_qa")),
            "fvm_mantra": num(cells.get("m_fvm")),
        })
    return pd.DataFrame(rows)

def main():
    for season in SEASONS:
        print(f"=== {season} ===", flush=True)
        df = scrape_season(season)
        if df is None or df.empty:
            print("  NESSUN DATO", flush=True)
        else:
            path = os.path.join(OUT, f"fantacalcioit_{season}.csv")
            df.to_csv(path, index=False, encoding="utf-8", lineterminator="\n")
            print(f"  salvate {len(df)} righe -> {path}", flush=True)
        time.sleep(random.uniform(1.5, 3))

if __name__ == "__main__":
    main()
