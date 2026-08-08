# -*- coding: utf-8 -*-
"""Ispeziona struttura riga fantacalcio.it + testa API Excel anonima + trova season id per stagione."""
import time, re
import requests
from bs4 import BeautifulSoup

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
    "Accept-Language": "it-IT,it;q=0.9,en;q=0.8",
}
S = requests.Session(); S.headers.update(HEADERS)

# 1) struttura di una riga completa
r = S.get("https://www.fantacalcio.it/quotazioni-fantacalcio/2024-25", timeout=60)
soup = BeautifulSoup(r.text, "lxml")
table = soup.find("table")
rows = table.find_all("tr")
print("HEADER ROW HTML (troncato):")
print(str(rows[0])[:1500])
print("\nDATA ROW HTML (Retegui, troncato):")
print(str(rows[1])[:2500])

# 2) link export per varie stagioni: pattern /api/v1/Excel/prices/{id}/{x}
print("\n--- season id per stagione ---")
for season in ["2020-21", "2021-22", "2022-23", "2023-24", "2024-25", "2025-26"]:
    time.sleep(1.5)
    rr = S.get(f"https://www.fantacalcio.it/quotazioni-fantacalcio/{season}", timeout=60)
    m = re.search(r"/api/v1/Excel/prices/(\d+)/(\d+)", rr.text)
    ntab = rr.text.count("<tr")
    print(f"{season}: status={rr.status_code} url_finale={rr.url} export={'/api/v1/Excel/prices/'+m.group(1)+'/'+m.group(2) if m else 'NON TROVATO'} righe_tr~{ntab}")

# 3) test API excel anonima
time.sleep(1.5)
rr = S.get("https://www.fantacalcio.it/api/v1/Excel/prices/19/1", timeout=60)
print("\nAPI Excel: status", rr.status_code, "ctype", rr.headers.get("Content-Type"),
      "disp", rr.headers.get("Content-Disposition"), "len", len(rr.content))
print("primi byte:", rr.content[:60])
open(r"data\raw\quotazioni\_test_fcit.bin", "wb").write(rr.content)
