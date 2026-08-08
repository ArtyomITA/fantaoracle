# -*- coding: utf-8 -*-
"""
Scarica statistiche xG Serie A da Understat, stagioni 2019 (=2019/20) -> 2025 (=2025/26).

Strategia:
  1. Prova con la libreria `understatapi` (pip install --user understatapi).
  2. Fallback: fetch diretto di https://understat.com/league/Serie_A/{season}
     e parsing regex del JSON embedded (playersData / teamsData), che sta
     nell'HTML come JSON.parse('<stringa con escape \\xNN>').

Output (UTF-8, separatore virgola, header):
  data/raw/understat/understat_players_{season}.csv
  data/raw/understat/understat_teams_{season}.csv
"""
import codecs
import json
import re
import sys
import time
import random
import csv
from pathlib import Path

import requests

OUT_DIR = Path(r"data\raw\understat")
SEASONS = ["2019", "2020", "2021", "2022", "2023", "2024", "2025"]
LEAGUE = "Serie_A"

HEADERS = {
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                   "AppleWebKit/537.36 (KHTML, like Gecko) "
                   "Chrome/126.0.0.0 Safari/537.36"),
    "Accept-Language": "en-US,en;q=0.9,it;q=0.8",
}

PLAYER_COLS = ["player_name", "team", "position", "minutes", "games",
               "goals", "assists", "xG", "xA", "npxG", "shots", "key_passes"]
TEAM_COLS = ["team", "matches", "xG", "xGA", "npxG", "npxGA", "punti",
             "goals_scored", "goals_conceded", "xpts"]


def polite_sleep():
    time.sleep(random.uniform(1.0, 3.0))


def fetch_html_with_retry(url, max_tries=5):
    delay = 5.0
    for attempt in range(1, max_tries + 1):
        try:
            r = requests.get(url, headers=HEADERS, timeout=30)
            if r.status_code in (429, 503):
                print(f"    HTTP {r.status_code}, retry in {delay:.0f}s "
                      f"(tentativo {attempt}/{max_tries})")
                time.sleep(delay)
                delay *= 2
                continue
            r.raise_for_status()
            return r.text
        except requests.RequestException as e:
            if attempt == max_tries:
                raise
            print(f"    errore rete: {e}; retry in {delay:.0f}s")
            time.sleep(delay)
            delay *= 2
    raise RuntimeError(f"impossibile scaricare {url}")


def extract_embedded_json(html, var_name):
    """Estrae il JSON da: var <var_name> = JSON.parse('...');"""
    m = re.search(var_name + r"\s*=\s*JSON\.parse\('(.*?)'\)", html, re.S)
    if not m:
        raise ValueError(f"variabile {var_name} non trovata nell'HTML")
    raw = m.group(1)
    decoded = codecs.decode(raw.encode("utf-8"), "unicode_escape")
    # unicode_escape decodifica byte-per-byte: ripara i caratteri non-ASCII
    decoded = decoded.encode("latin-1").decode("utf-8")
    return json.loads(decoded)


def get_season_data_via_library(season):
    from understatapi import UnderstatClient
    with UnderstatClient() as u:
        league = u.league(league=LEAGUE)
        players = league.get_player_data(season=season)
        polite_sleep()
        teams = league.get_team_data(season=season)
    return players, teams


def get_season_data_via_html(season):
    url = f"https://understat.com/league/{LEAGUE}/{season}"
    html = fetch_html_with_retry(url)
    players = extract_embedded_json(html, "playersData")
    teams = extract_embedded_json(html, "teamsData")
    return players, teams


def write_players_csv(players, season):
    path = OUT_DIR / f"understat_players_{season}.csv"
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(PLAYER_COLS)
        for p in players:
            w.writerow([
                p.get("player_name", ""),
                p.get("team_title", ""),
                p.get("position", ""),
                p.get("time", ""),          # minuti giocati
                p.get("games", ""),
                p.get("goals", ""),
                p.get("assists", ""),
                round(float(p.get("xG", 0)), 3),
                round(float(p.get("xA", 0)), 3),
                round(float(p.get("npxG", 0)), 3),
                p.get("shots", ""),
                p.get("key_passes", ""),
            ])
    return path, len(players)


def write_teams_csv(teams, season):
    """teams: dict team_id -> {id, title, history: [match, ...]}"""
    path = OUT_DIR / f"understat_teams_{season}.csv"
    rows = []
    for tid, t in teams.items():
        hist = t.get("history", [])
        row = {
            "team": t.get("title", ""),
            "matches": len(hist),
            "xG": round(sum(float(h["xG"]) for h in hist), 3),
            "xGA": round(sum(float(h["xGA"]) for h in hist), 3),
            "npxG": round(sum(float(h["npxG"]) for h in hist), 3),
            "npxGA": round(sum(float(h["npxGA"]) for h in hist), 3),
            "punti": sum(int(h["pts"]) for h in hist),
            "goals_scored": sum(int(h["scored"]) for h in hist),
            "goals_conceded": sum(int(h["missed"]) for h in hist),
            "xpts": round(sum(float(h["xpts"]) for h in hist), 3),
        }
        rows.append(row)
    rows.sort(key=lambda r: (-r["punti"], r["team"]))
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=TEAM_COLS)
        w.writeheader()
        w.writerows(rows)
    return path, len(rows)


def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    results = []
    for i, season in enumerate(SEASONS):
        if i > 0:
            polite_sleep()
        print(f"[{season}] stagione {season}/{int(season) % 100 + 1:02d} ...")
        players = teams = None
        try:
            players, teams = get_season_data_via_library(season)
            source = "understatapi"
        except Exception as e:
            print(f"    understatapi fallita ({type(e).__name__}: {e}); "
                  f"fallback parsing HTML")
            polite_sleep()
            try:
                players, teams = get_season_data_via_html(season)
                source = "html-regex"
            except Exception as e2:
                print(f"    FALLBACK FALLITO: {type(e2).__name__}: {e2}")
                results.append((season, "FAILED", 0, 0, str(e2)))
                continue
        p_path, n_players = write_players_csv(players, season)
        t_path, n_teams = write_teams_csv(teams, season)
        print(f"    OK ({source}): {n_players} giocatori, {n_teams} squadre")
        results.append((season, source, n_players, n_teams, ""))

    print("\n=== RIEPILOGO ===")
    for season, source, np_, nt, err in results:
        status = f"{np_} players / {nt} teams via {source}" if source != "FAILED" \
            else f"FAILED: {err}"
        print(f"  {season}: {status}")
    failed = [r for r in results if r[1] == "FAILED"]
    sys.exit(1 if len(failed) == len(SEASONS) else 0)


if __name__ == "__main__":
    main()
