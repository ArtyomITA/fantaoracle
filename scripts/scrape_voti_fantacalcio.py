# -*- coding: utf-8 -*-
"""
Scrape voti+fantavoti per giornata da fantacalcio.it (HTML anonimo, nessun login).

URL pattern: https://www.fantacalcio.it/voti-fantacalcio-serie-a/{stagione}/{giornata}
  es. /voti-fantacalcio-serie-a/2021-22/38

Struttura pagina: 20 tabelle (una per squadra), thead con nome squadra
(itemprop="name"), righe giocatore con:
  - span.role data-value = p|d|c|a|all
  - a.player-name > span = nome
  - 3 "pill" (voto+fantavoto) in ordine: Redazione Fantacalcio, Statistico, Italia
  - classi yellow-card / red-card sullo span del voto = ammonito/espulso
  - 8 span bonus/malus con title (Gol segnati, Gol subiti, Autoreti, Rigori
    segnati, Rigori sbagliati, Rigori parati, Assist, Player of the match)
  - data-value "55" = S.V. (senza voto)

Checkpoint: un CSV per stagione, append giornata per giornata; al riavvio
le giornate gia' presenti nel CSV vengono saltate.
"""
import csv
import os
import random
import re
import sys
import time

import requests

OUT_DIR = r"data\raw\voti"
LOG_PATH = os.path.join(OUT_DIR, "_scrape_log.txt")

SEASONS = ["2021-22", "2022-23", "2023-24", "2024-25", "2025-26"]
GIORNATE = range(1, 39)

BASE_URL = "https://www.fantacalcio.it/voti-fantacalcio-serie-a/{season}/{gw}"

HEADERS = {
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                   "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"),
    "Accept-Language": "it-IT,it;q=0.9,en;q=0.8",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}

COLUMNS = [
    "stagione", "giornata", "squadra", "nome", "ruolo",
    "voto", "fantavoto",
    "gol_fatti", "gol_subiti", "assist",
    "ammonizione", "espulsione",
    "rigori_parati", "rigori_sbagliati", "rigore_segnato", "autogol",
    "potm", "sv",
    "voto_statistico", "fantavoto_statistico", "voto_italia", "fantavoto_italia",
]

BONUS_MAP = {
    "Gol segnati": "gol_fatti",
    "Gol subiti": "gol_subiti",
    "Autoreti": "autogol",
    "Rigori segnati": "rigore_segnato",
    "Rigori sbagliati": "rigori_sbagliati",
    "Rigori parati": "rigori_parati",
    "Assist": "assist",
    "Player of the match": "potm",
}

RE_TABLE = re.compile(r"<thead>(.*?)</thead>\s*<tbody>(.*?)</tbody>", re.S)
RE_TEAM_NAME = re.compile(r'itemprop="name"\s+content="([^"]+)"')
RE_ROW = re.compile(r"<tr>(.*?)</tr>", re.S)
RE_ROLE = re.compile(r'class="role"\s+data-value="([^"]*)"')
RE_NAME = re.compile(r'class="player-name[^"]*"[^>]*>.*?<span>([^<]+)</span>', re.S)
RE_PILL = re.compile(
    r'<div class="pill">\s*'
    r'<span class="player-grade\s*([a-z-]*)"\s+data-value="([^"]*)"></span>\s*'
    r'<span class="player-fanta-grade"\s+data-value="([^"]*)"></span>',
    re.S,
)
RE_BONUS = re.compile(
    r'class="player-bonus cell (?:bonus|malus)"\s+data-value="([^"]*)"\s+title="([^"]*)"')
RE_TITLE = re.compile(r"<title>([^<]*)</title>")


def log(msg):
    line = time.strftime("[%H:%M:%S] ") + msg
    print(line, flush=True)
    with open(LOG_PATH, "a", encoding="utf-8") as f:
        f.write(line + "\n")


def num(v):
    """'5,5' -> '5.5'; '55' (S.V.) gestito a monte."""
    v = (v or "").strip()
    return v.replace(",", ".")


def fetch(url, max_retries=5):
    delay = 5.0
    for attempt in range(1, max_retries + 1):
        try:
            r = requests.get(url, headers=HEADERS, timeout=45)
        except requests.RequestException as e:
            log(f"  errore rete ({e.__class__.__name__}) tentativo {attempt}, attendo {delay:.0f}s")
            time.sleep(delay)
            delay *= 2
            continue
        if r.status_code == 200:
            return r.text
        if r.status_code in (429, 503, 502, 500, 504):
            log(f"  HTTP {r.status_code} tentativo {attempt}, backoff {delay:.0f}s")
            time.sleep(delay)
            delay *= 2
            continue
        log(f"  HTTP {r.status_code} definitivo per {url}")
        return None
    log(f"  troppi tentativi falliti per {url}")
    return None


def parse_page(html, season, gw):
    """Ritorna (rows, anomalie:list[str])."""
    rows = []
    anomalies = []

    m = RE_TITLE.search(html)
    title = m.group(1) if m else ""
    # verifica che la pagina sia davvero della giornata/stagione richiesta
    season_h = season.replace("-", "/20") if False else season[:4] + "/" + season[5:]
    if f"{gw} giornata" not in title or season_h not in title:
        anomalies.append(f"titolo inatteso: '{title.strip()}' (atteso gw {gw}, stagione {season_h})")

    for thead, tbody in RE_TABLE.findall(html):
        if "Voto e Fantavoto" not in thead:
            continue  # altre tabelle (classifica ecc.)
        tm = RE_TEAM_NAME.search(thead)
        team = tm.group(1).strip() if tm else "?"

        for tr in RE_ROW.findall(tbody):
            rm = RE_ROLE.search(tr)
            nm = RE_NAME.search(tr)
            if not rm or not nm:
                continue
            role = rm.group(1).strip()
            name = nm.group(1).strip()

            pills = RE_PILL.findall(tr)  # [(cardcls, voto, fantavoto) x3]
            if not pills:
                continue
            # ordine: 0=Redazione Fantacalcio, 1=Statistico, 2=Italia
            def pv(i):
                if i < len(pills):
                    return pills[i][1].strip(), pills[i][2].strip()
                return "", ""

            v_red, fv_red = pv(0)
            v_sta, fv_sta = pv(1)
            v_ita, fv_ita = pv(2)

            sv = 1 if v_red == "55" else 0

            def clean(v):
                return "" if v in ("", "55") else num(v)

            yellow = any("yellow-card" in p[0] for p in pills)
            red = any("red-card" in p[0] for p in pills)

            row = {
                "stagione": season,
                "giornata": gw,
                "squadra": team,
                "nome": name,
                "ruolo": role,
                "voto": clean(v_red),
                "fantavoto": clean(fv_red),
                "gol_fatti": "0", "gol_subiti": "0", "assist": "0",
                "ammonizione": 1 if yellow else 0,
                "espulsione": 1 if red else 0,
                "rigori_parati": "0", "rigori_sbagliati": "0",
                "rigore_segnato": "0", "autogol": "0", "potm": "0",
                "sv": sv,
                "voto_statistico": clean(v_sta),
                "fantavoto_statistico": clean(fv_sta),
                "voto_italia": clean(v_ita),
                "fantavoto_italia": clean(fv_ita),
            }
            for val, tit in RE_BONUS.findall(tr):
                col = BONUS_MAP.get(tit.strip())
                if col:
                    row[col] = num(val)
            rows.append(row)

    n_teams = len({r["squadra"] for r in rows})
    if n_teams < 20:
        anomalies.append(f"solo {n_teams} squadre trovate")
    if len(rows) < 250:
        anomalies.append(f"solo {len(rows)} righe giocatore")
    return rows, anomalies


def done_giornate(csv_path):
    if not os.path.exists(csv_path):
        return set()
    done = set()
    with open(csv_path, encoding="utf-8", newline="") as f:
        for row in csv.DictReader(f):
            try:
                done.add(int(row["giornata"]))
            except (KeyError, ValueError):
                pass
    return done


def append_rows(csv_path, rows):
    new_file = not os.path.exists(csv_path)
    with open(csv_path, "a", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=COLUMNS)
        if new_file:
            w.writeheader()
        w.writerows(rows)


def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    seasons = sys.argv[1:] or SEASONS
    for season in seasons:
        csv_path = os.path.join(OUT_DIR, f"voti_{season}.csv")
        done = done_giornate(csv_path)
        todo = [g for g in GIORNATE if g not in done]
        log(f"=== stagione {season}: {len(done)} giornate gia' presenti, {len(todo)} da scaricare")
        for gw in todo:
            url = BASE_URL.format(season=season, gw=gw)
            html = fetch(url)
            if html is None:
                log(f"  {season} gw {gw}: FALLITA, proseguo")
                continue
            rows, anomalies = parse_page(html, season, gw)
            for a in anomalies:
                log(f"  {season} gw {gw}: ANOMALIA: {a}")
            if rows:
                append_rows(csv_path, rows)
                nsv = sum(r["sv"] for r in rows)
                log(f"  {season} gw {gw}: {len(rows)} righe ({nsv} S.V.)")
            else:
                log(f"  {season} gw {gw}: 0 righe, NON salvata")
            time.sleep(random.uniform(1.2, 2.2))
    log("=== FINITO ===")


if __name__ == "__main__":
    main()
