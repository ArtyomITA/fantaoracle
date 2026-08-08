# -*- coding: utf-8 -*-
"""Parse fantacalcio-online.com price tables (Wayback snapshots) into the target CSV schema.

Target schema: ruolo,squadra,nome,kap,p350_8sq,p350_10sq,p500_8sq,p500_10sq,mv,presenze

Two layouts:
  A "stima"  : Kap | 350K(8) | 350K(10) | 500K(8) | 500K(10) | M.V. | Pres.   (4 price cols)
  B "season" : Kap | 8(350K) | 10(350K)* | 12(350K)* | Tot%* | M.V. | Pres.   (*locked -> empty)

Usage:
  python wayback_parse.py --analyze          # parse all html, print stats only
  python wayback_parse.py --emit             # write chosen CSVs (see CHOSEN at bottom)
"""
import csv
import html as htmllib
import os
import re
import sys
from collections import Counter

HTML_DIR = r"data\raw\wayback_prices\html"
OUT_DIR = r"data\raw\wayback_prices"

SEASON_TEAMS = {
    "2018-19": {"atalanta", "bologna", "cagliari", "chievo", "empoli", "fiorentina", "frosinone",
                "genoa", "inter", "juventus", "lazio", "milan", "napoli", "parma", "roma",
                "sampdoria", "sassuolo", "spal", "torino", "udinese"},
    "2019-20": {"atalanta", "bologna", "brescia", "cagliari", "fiorentina", "genoa", "inter",
                "juventus", "lazio", "lecce", "milan", "napoli", "parma", "roma", "sampdoria",
                "sassuolo", "spal", "torino", "udinese", "verona"},
    "2020-21": {"atalanta", "benevento", "bologna", "cagliari", "crotone", "fiorentina", "genoa",
                "inter", "juventus", "lazio", "milan", "napoli", "parma", "roma", "sampdoria",
                "sassuolo", "spezia", "torino", "udinese", "verona"},
    "2021-22": {"atalanta", "bologna", "cagliari", "empoli", "fiorentina", "genoa", "inter",
                "juventus", "lazio", "milan", "napoli", "roma", "salernitana", "sampdoria",
                "sassuolo", "spezia", "torino", "udinese", "venezia", "verona"},
    "2022-23": {"atalanta", "bologna", "cremonese", "empoli", "fiorentina", "inter", "juventus",
                "lazio", "lecce", "milan", "monza", "napoli", "roma", "salernitana", "sampdoria",
                "sassuolo", "spezia", "torino", "udinese", "verona"},
    "2023-24": {"atalanta", "bologna", "cagliari", "empoli", "fiorentina", "frosinone", "genoa",
                "inter", "juventus", "lazio", "lecce", "milan", "monza", "napoli", "roma",
                "salernitana", "sassuolo", "torino", "udinese", "verona"},
    "2024-25": {"atalanta", "bologna", "cagliari", "como", "empoli", "fiorentina", "genoa",
                "inter", "juventus", "lazio", "lecce", "milan", "monza", "napoli", "parma",
                "roma", "torino", "udinese", "venezia", "verona"},
    "2025-26": {"atalanta", "bologna", "cagliari", "como", "cremonese", "fiorentina", "genoa",
                "inter", "juventus", "lazio", "lecce", "milan", "napoli", "parma", "pisa",
                "roma", "sassuolo", "torino", "udinese", "verona"},
}

NON_SERIE_A = {"estero", "serie minori", "svincolato", "svincolati", "ritirato", ""}

RE_ROW = re.compile(r"<tr>(.*?)</tr>", re.S)
RE_ROLE = re.compile(r'class="tag role[^"]*"\s*>\s*([A-Z]?)\s*<', re.S)
RE_ROLE_LABEL = re.compile(r'class="tag role label-(\d+)')
# era 2019-2025: 1=P 2=D 3=C 5=A ; era 2026+: 1=P 2=D 4=C (mostrato 'T') 6=A (span vuoto)
LABEL_TO_ROLE = {"1": "P", "2": "D", "3": "C", "4": "C", "5": "A", "6": "A"}
RE_TEAM = re.compile(r'<td class="team-name">([^<]*)</td>')
RE_NAME = re.compile(
    r'<td class="player-name"><span class="text-bold">([^<]*)</span>\s*'
    r'(?:<span class="hidden-xl-down">([^<]*)</span>)?', re.S)
RE_CELL = re.compile(r'<td class="vote-col-no">(.*?)</td>', re.S)


def norm_team(t):
    t = htmllib.unescape(t).strip().lower()
    t = t.replace("hellas verona", "verona").replace("h. verona", "verona")
    return t


def cell_value(raw):
    if "fantaicon-locked" in raw:
        return None  # locked
    txt = re.sub(r"<[^>]+>", "", raw).strip()
    return txt


def parse_file(path):
    with open(path, encoding="utf-8", errors="replace") as f:
        text = f.read()

    # layout detection from thead
    if "500K (8)" in text:
        layout = "stima"
    elif "8 (350 K.)" in text:
        layout = "season"
    else:
        layout = "unknown"

    m = re.search(r"aggiornato al\s*</?strong>?\s*([0-9]{2}-[0-9]{2}-[0-9]{4})", text)
    if not m:
        m = re.search(r"aggiornato al ([0-9]{2}-[0-9]{2}-[0-9]{4})", text)
    updated = m.group(1) if m else ""

    rows = []
    for rm in RE_ROW.finditer(text):
        block = rm.group(1)
        nm = RE_NAME.search(block)
        if not nm:
            continue
        surname = htmllib.unescape(nm.group(1)).strip()
        given = htmllib.unescape(nm.group(2) or "").strip()
        name = (surname + (" " + given if given else "")).strip()
        lbl_m = RE_ROLE_LABEL.search(block)
        if lbl_m and lbl_m.group(1) in LABEL_TO_ROLE:
            role = LABEL_TO_ROLE[lbl_m.group(1)]
        else:
            role_m = RE_ROLE.search(block)
            role = role_m.group(1).strip() if role_m else ""
        team_m = RE_TEAM.search(block)
        team = htmllib.unescape(team_m.group(1)).strip() if team_m else ""
        cells = [cell_value(c) for c in RE_CELL.findall(block)]
        rows.append({"role": role, "team": team, "name": name, "cells": cells})

    return layout, updated, rows


def to_schema(layout, row):
    c = row["cells"]

    def g(i):
        if i >= len(c) or c[i] is None:
            return ""
        return c[i]

    if layout == "stima":
        # kap, p350_8, p350_10, p500_8, p500_10, mv, pres
        return [row["role"], row["team"], row["name"], g(0), g(1), g(2), g(3), g(4), g(5), g(6)]
    else:  # season
        # kap, p350_8, p350_10(locked), p350_12(locked), tot%(locked), mv, pres
        return [row["role"], row["team"], row["name"], g(0), g(1), "", "", "", g(5), g(6)]


def detect_season(rows):
    teams = {norm_team(r["team"]) for r in rows} - NON_SERIE_A
    best, best_score = None, -1
    for season, sset in SEASON_TEAMS.items():
        score = len(teams & sset)
        if score > best_score:
            best, best_score = season, score
    return best, best_score, sorted(teams)


def price_count(layout, rows):
    """rows with at least one numeric price"""
    n = 0
    for r in rows:
        c = r["cells"]
        idxs = range(1, 5) if layout == "stima" else [1]
        for i in idxs:
            if i < len(c) and c[i] and re.match(r"^\d", c[i]):
                n += 1
                break
    return n


def analyze():
    files = sorted(os.listdir(HTML_DIR))
    print(f"{'file':<72} {'layout':<7} {'season':<8} {'rows':>5} {'w/price':>7}  updated")
    results = {}
    for fn in files:
        if not fn.endswith(".html"):
            continue
        layout, updated, rows = parse_file(os.path.join(HTML_DIR, fn))
        season, score, teams = detect_season(rows)
        np = price_count(layout, rows)
        results[fn] = (layout, season, score, len(rows), np, updated)
        print(f"{fn[:72]:<72} {layout:<7} {season}({score:>2}) {len(rows):>5} {np:>7}  {updated}")
    return results


def emit(chosen):
    header = ["ruolo", "squadra", "nome", "kap", "p350_8sq", "p350_10sq",
              "p500_8sq", "p500_10sq", "mv", "presenze"]
    for fn, season in chosen:
        path = os.path.join(HTML_DIR, fn)
        layout, updated, rows = parse_file(path)
        ts = fn.split("_")[0]
        out = os.path.join(OUT_DIR, f"prezzi_{season}_{ts}.csv")
        with open(out, "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(header)
            for r in rows:
                w.writerow(to_schema(layout, r))
        print(f"wrote {out} ({len(rows)} rows, layout={layout}, updated={updated})")


if __name__ == "__main__":
    if "--emit" in sys.argv:
        # (file, season) pairs filled after analysis
        CHOSEN = []
        chosen_file = os.path.join(OUT_DIR, "chosen.txt")
        if os.path.exists(chosen_file):
            with open(chosen_file, encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith("#"):
                        fn, season = line.split("\t")
                        CHOSEN.append((fn, season))
        emit(CHOSEN)
    else:
        analyze()
