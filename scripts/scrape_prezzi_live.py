# -*- coding: utf-8 -*-
"""
Scraper della tabella "stima prezzi asta" live di fantacalcio-online.com.

URL: https://www.fantacalcio-online.com/it/asta-fantacalcio-stima-prezzi

Struttura riga (<tr>):
  - td.player-pos  > span.tag.role.label-N   (N: 1=P, 2=D, 3/4=C, 5/6=A)
  - td.team-name
  - td.player-name > span.text-bold (COGNOME) + span.text-muted|hidden-xl-down (Nome)
                     + eventuale span.fco-etichetta--ferma  "2025/2026"  (prezzo = media asta 2025/26)
                     + eventuale span.fco-etichetta--attesa "Nuovo"      (nuovo in A: nessuna media)
  - 7 td.vote-col-no in ordine: kap, p350_8sq, p350_10sq, p500_8sq, p500_10sq, mv, presenze

Colonna `stagione_prezzo`:
  "2026-27"  nessuna etichetta   -> media dell'asta 2026/27
  "2025-26"  etichetta "2025/2026" -> fallback: media dell'asta 2025/26
  "nuovo"    etichetta "Nuovo"   -> arrivato in A nel 2026/27, nessun prezzo medio (celle vuote)

Le regex/mappe di parsing sono riusate da `wayback_parse.py` (stessa cartella).
Output: out_dir/html/live_{date_tag}.html  e  out_dir/prezzi_2026-27_live_{date_tag}.csv
"""
from __future__ import annotations

import csv
import html as htmllib
import random
import re
import sys
import time
from collections import Counter
from datetime import date
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent))
from wayback_parse import LABEL_TO_ROLE, RE_CELL, RE_ROLE, RE_ROLE_LABEL, RE_TEAM, cell_value  # noqa: E402

URL = "https://www.fantacalcio-online.com/it/asta-fantacalcio-stima-prezzi"
DEFAULT_OUT_DIR = Path(r"data\raw\wayback_prices")

HEADERS = {
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                   "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"),
    "Accept-Language": "it-IT,it;q=0.9,en;q=0.8",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}

COLUMNS = ["ruolo", "squadra", "nome", "kap", "p350_8sq", "p350_10sq",
           "p500_8sq", "p500_10sq", "mv", "presenze", "stagione_prezzo"]

RE_ROW = re.compile(r"<tr[^>]*>(.*?)</tr>", re.S)
# il nome proprio sta in span.text-muted (layout 2026) o span.hidden-xl-down (layout wayback)
RE_NAME = re.compile(
    r'<td class="player-name">\s*<span class="text-bold">([^<]*)</span>\s*'
    r'(?:<span class="(?:text-muted|hidden-xl-down)">([^<]*)</span>)?', re.S)
RE_ETICHETTA = re.compile(r'fco-etichetta--(\w+)"[^>]*>\s*([^<]*?)\s*<', re.S)
RE_DATA_AGG = re.compile(r"dati al\s*(\d{2}/\d{2}/\d{4})")

ETICHETTA_TO_STAGIONE = {"ferma": "2025-26", "attesa": "nuovo"}


def fetch_html(url: str, max_retries: int = 5, timeout: int = 45) -> str:
    """Scarica una pagina con pausa 1-3 s e retry esponenziale su 429/503."""
    for attempt in range(1, max_retries + 1):
        time.sleep(random.uniform(1.0, 3.0))
        try:
            r = requests.get(url, headers=HEADERS, timeout=timeout)
        except requests.RequestException as exc:
            if attempt == max_retries:
                raise
            print(f"  [retry {attempt}] errore rete: {exc}")
            time.sleep(5 * attempt)
            continue
        if r.status_code in (429, 503):
            wait = 10 * attempt
            print(f"  [retry {attempt}] HTTP {r.status_code}, attendo {wait}s")
            time.sleep(wait)
            continue
        r.raise_for_status()
        r.encoding = r.apparent_encoding or "utf-8"
        return r.text
    raise RuntimeError(f"troppi tentativi falliti per {url}")


def to_number(txt: str | None) -> str:
    """Normalizza una cella numerica: virgola -> punto, stringa vuota se assente."""
    if not txt:
        return ""
    txt = htmllib.unescape(txt).strip().replace(",", ".")
    return txt if re.match(r"^-?\d+(\.\d+)?$", txt) else ""


def parse_row(block: str) -> dict | None:
    """Estrae una riga giocatore dal contenuto di un <tr>; None se non e' una riga dati."""
    nm = RE_NAME.search(block)
    if not nm:
        return None
    surname = htmllib.unescape(nm.group(1)).strip()
    given = htmllib.unescape(nm.group(2) or "").strip()
    nome = (surname + (" " + given if given else "")).strip()

    lbl = RE_ROLE_LABEL.search(block)
    if lbl and lbl.group(1) in LABEL_TO_ROLE:
        ruolo = LABEL_TO_ROLE[lbl.group(1)]
    else:
        rm = RE_ROLE.search(block)
        ruolo = rm.group(1).strip() if rm else ""

    tm = RE_TEAM.search(block)
    squadra = htmllib.unescape(tm.group(1)).strip() if tm else ""

    cells = [to_number(cell_value(c)) for c in RE_CELL.findall(block)]
    cells += [""] * (7 - len(cells))

    et = RE_ETICHETTA.search(block)
    stagione = ETICHETTA_TO_STAGIONE.get(et.group(1), et.group(2).strip()) if et else "2026-27"

    return {
        "ruolo": ruolo, "squadra": squadra, "nome": nome,
        "kap": cells[0], "p350_8sq": cells[1], "p350_10sq": cells[2],
        "p500_8sq": cells[3], "p500_10sq": cells[4], "mv": cells[5], "presenze": cells[6],
        "stagione_prezzo": stagione,
    }


def parse_html(text: str) -> tuple[list[dict], str]:
    """Ritorna (righe, data_aggiornamento 'gg/mm/aaaa' o '')."""
    rows = [r for r in (parse_row(b) for b in RE_ROW.findall(text)) if r]
    m = RE_DATA_AGG.search(text)
    return rows, (m.group(1) if m else "")


def scrape_live(out_dir: Path, date_tag: str) -> Path:
    """Scarica la pagina, salva l'HTML grezzo e scrive il CSV; ritorna il path del CSV."""
    out_dir = Path(out_dir)
    html_dir = out_dir / "html"
    html_dir.mkdir(parents=True, exist_ok=True)

    print(f"GET {URL}")
    text = fetch_html(URL)
    html_path = html_dir / f"live_{date_tag}.html"
    html_path.write_text(text, encoding="utf-8")

    rows, aggiornato = parse_html(text)
    csv_path = out_dir / f"prezzi_2026-27_live_{date_tag}.csv"
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=COLUMNS)
        w.writeheader()
        w.writerows(rows)

    cnt = Counter(r["stagione_prezzo"] for r in rows)
    print(f"righe: {len(rows)}  dati al: {aggiornato or '?'}  stagione_prezzo: {dict(cnt)}")
    print(f"scritto {csv_path}")
    return csv_path


if __name__ == "__main__":
    tag = date.today().strftime("%Y%m%d")
    scrape_live(DEFAULT_OUT_DIR, tag)
