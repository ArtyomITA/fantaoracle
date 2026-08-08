# -*- coding: utf-8 -*-
"""Esplora fantacalcio.it quotazioni senza login: la tabella e' nell'HTML anonimo?"""
import time, re, sys
import requests
from bs4 import BeautifulSoup

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
    "Accept-Language": "it-IT,it;q=0.9,en;q=0.8",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}

url = sys.argv[1] if len(sys.argv) > 1 else "https://www.fantacalcio.it/quotazioni-fantacalcio/2024-25"
r = requests.get(url, headers=HEADERS, timeout=60)
print("status:", r.status_code, "final url:", r.url, "len:", len(r.text))

soup = BeautifulSoup(r.text, "lxml")
tables = soup.find_all("table")
print("n. <table>:", len(tables))
for i, t in enumerate(tables):
    rows = t.find_all("tr")
    print(f"  table[{i}]: {len(rows)} righe, classi={t.get('class')}")
    for tr in rows[:4]:
        cells = [" ".join(td.get_text().split())[:20] for td in tr.find_all(["th", "td"])]
        print("   ", cells)

# cerca dati inline in JS (application/json, __NEXT_DATA__, ecc.)
for s in soup.find_all("script"):
    st = s.string or ""
    if len(st) > 500 and any(k in st for k in ["quotazion", "prezzo", "Qt", "fvm", "FVM", "players", "giocator"]):
        print("\nSCRIPT candidato, primi 400 char:")
        print(st[:400])
        break

# cerca nomi giocatori noti nell'HTML grezzo
for name in ["Lautaro", "Vlahovic", "Maignan", "Kean"]:
    cnt = r.text.count(name)
    print(f"occorrenze {name!r} nell'HTML: {cnt}")

# link a export excel/csv
for a in soup.find_all("a", href=True):
    h = a["href"]
    if any(k in h.lower() for k in ["xls", "excel", "csv", "export", "download"]):
        print("LINK export:", h, "|", " ".join(a.get_text().split())[:40])
