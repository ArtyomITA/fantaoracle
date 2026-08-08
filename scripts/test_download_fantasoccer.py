# -*- coding: utf-8 -*-
"""Test: scarica una giornata da fanta.soccer e ispeziona il file. Controlla anche date rilevazioni."""
import time, re
import requests
from bs4 import BeautifulSoup

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
    "Accept-Language": "it-IT,it;q=0.9,en;q=0.8",
}

url = "https://www.fanta.soccer/ArchivioQuotazioni/QuotazioniExcel.aspx?lang=it&serie=A&stagione=2023-2024&giornata=1"
r = requests.get(url, headers=HEADERS, timeout=60)
print("status:", r.status_code)
print("content-type:", r.headers.get("Content-Type"))
print("content-disposition:", r.headers.get("Content-Disposition"))
print("len bytes:", len(r.content))
print("first bytes:", r.content[:80])

out = r"data\raw\quotazioni\_test_g1.bin"
with open(out, "wb") as f:
    f.write(r.content)

time.sleep(2)

# season page: estrai la tabella giornata -> data rilevazione
r2 = requests.get("https://www.fanta.soccer/it/archivioquotazioni/A/2023-2024/", headers=HEADERS, timeout=60)
soup = BeautifulSoup(r2.text, "lxml")
text = soup.get_text(" ", strip=True)
# cerca pattern tipo "giornata X" con date
m = re.findall(r"(\d{1,2}\s+\w+\s+\d{4}|giornata\s*\d+|Giornata\s*\d+|\d{2}/\d{2}/\d{4})", text)
print("\npattern date/giornate nella pagina stagione (primi 60):")
print(m[:60])
