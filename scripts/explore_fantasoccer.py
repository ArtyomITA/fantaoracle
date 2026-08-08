# -*- coding: utf-8 -*-
"""Esplora la struttura di fanta.soccer archivio quotazioni."""
import time, random, sys
import requests
from bs4 import BeautifulSoup

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
    "Accept-Language": "it-IT,it;q=0.9,en;q=0.8",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}

def fetch(url):
    for attempt in range(4):
        try:
            r = requests.get(url, headers=HEADERS, timeout=30)
            if r.status_code in (429, 503):
                wait = 5 * (2 ** attempt)
                print(f"  {r.status_code} -> retry in {wait}s", flush=True)
                time.sleep(wait)
                continue
            return r
        except requests.RequestException as e:
            print(f"  errore: {e}, retry", flush=True)
            time.sleep(5 * (attempt + 1))
    return None

def show_links(url, label):
    print(f"\n===== {label}: {url}")
    r = fetch(url)
    if r is None:
        print("  IRRAGGIUNGIBILE")
        return
    print(f"  status={r.status_code} len={len(r.text)}")
    soup = BeautifulSoup(r.text, "lxml")
    seen = set()
    for a in soup.find_all("a", href=True):
        h = a["href"]
        txt = " ".join(a.get_text().split())[:60]
        if ("archivioquotazioni" in h or "xls" in h.lower() or "excel" in h.lower()
                or "export" in h.lower() or "download" in h.lower()):
            key = (h, txt)
            if key not in seen:
                seen.add(key)
                print(f"  LINK: {h!r}  testo={txt!r}")
    # also look for forms / buttons
    for f in soup.find_all("form"):
        print(f"  FORM action={f.get('action')!r} method={f.get('method')!r}")
        for inp in f.find_all(["input", "select", "button"]):
            print(f"    {inp.name} name={inp.get('name')!r} value={str(inp.get('value'))[:40]!r} type={inp.get('type')!r}")

if __name__ == "__main__":
    show_links("https://www.fanta.soccer/it/archivioquotazioni/", "archivio root")
    time.sleep(random.uniform(1, 3))
    show_links("https://www.fanta.soccer/it/archivioquotazioni/A/2023-2024/", "stagione 2023-2024")
