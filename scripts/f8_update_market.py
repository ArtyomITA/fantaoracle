"""Aggiornamento mercato 2026/27 — "al minuto".

Un comando scarica tutto cio' che serve per la stagione corrente e ne
congela una copia datata (archivio locale NON volatile in data/snapshots/):

  1. listone fantacalcio.it 2026-27 (QI/QA/FVM, player_id)
  2. quotazioni fanta.soccer per giornata (ultime disponibili)
  3. voti fantacalcio.it 2026-27 (giornate gia' giocate)
  4. Understat 2026 (xG stagione in corso)
  5. prezzi medi asta 2026/27 (fantacalcio-online live, con flag fallback)
  6. mercato fantacalcio.it: probabili formazioni (% titolarita'),
     indisponibili (infortuni/squalifiche/rientri), rigoristi

Uso:  python scripts/f8_update_market.py [--skip voti,understat,...] [--solo prezzi]
Ogni passo e' indipendente: un fallimento non blocca gli altri.
"""
from __future__ import annotations

import importlib
import shutil
import sys
import time
import traceback
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
RAW = ROOT / "data" / "raw"
sys.path.insert(0, str(SCRIPTS))

SEASON = "2026-27"          # convenzione fantacalcio.it / voti
SEASON_FS = "2026-2027"     # convenzione fanta.soccer
SEASON_US = "2026"          # convenzione understat
DATE_TAG = datetime.now().strftime("%Y%m%d")
SNAP = ROOT / "data" / "snapshots" / DATE_TAG


def snapshot(path: Path):
    """Copia datata: la fonte live puo' sovrascriversi, la nostra no."""
    if path and Path(path).exists():
        SNAP.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, SNAP / Path(path).name)


def step_listone():
    m = importlib.import_module("scrape_fantacalcioit")
    df = m.scrape_season(SEASON)
    if df is None or df.empty:
        raise RuntimeError("listone vuoto")
    out = RAW / "quotazioni" / f"fantacalcioit_{SEASON}.csv"
    df.to_csv(out, index=False, encoding="utf-8", lineterminator="\n")
    snapshot(out)
    return f"{len(df)} giocatori -> {out.name}"


def step_fantasoccer():
    m = importlib.import_module("download_fantasoccer")
    giornate, date_map = m.parse_season_page(SEASON_FS)
    if not giornate:
        raise RuntimeError("nessuna giornata disponibile")
    got = []
    for g in giornate:
        res = m.download_giornata(SEASON_FS, g)
        got.append(f"g{g}:{res}")
        time.sleep(1.0)
        snapshot(RAW / "quotazioni" / f"fantasoccer_{SEASON}_g{g:02d}.csv")
    # aggiorna la mappa date (append idempotente)
    import pandas as pd
    dates_path = RAW / "quotazioni" / "fantasoccer_date_rilevazioni.csv"
    old = pd.read_csv(dates_path) if dates_path.exists() else pd.DataFrame(
        columns=["stagione", "giornata", "data_rilevazione"])
    new = pd.DataFrame([{"stagione": SEASON, "giornata": g, "data_rilevazione": d}
                        for g, d in date_map.items()])
    allv = pd.concat([old[old.stagione != SEASON], new], ignore_index=True)
    allv.to_csv(dates_path, index=False, encoding="utf-8", lineterminator="\n")
    return " ".join(got) + f" | date: {date_map}"


def step_voti():
    m = importlib.import_module("scrape_voti_fantacalcio")
    import os
    csv_path = os.path.join(m.OUT_DIR, f"voti_{SEASON}.csv")
    done = m.done_giornate(csv_path)
    added = []
    for gw in range(1, 39):
        if gw in done:
            continue
        html = m.fetch(m.BASE_URL.format(season=SEASON, gw=gw))
        if html is None:
            break
        rows, anomalies = m.parse_page(html, SEASON, gw)
        # giornata non ancora giocata: pagina senza tabelle voti -> stop
        if not rows or any("solo" in a for a in anomalies):
            break
        m.append_rows(csv_path, rows)
        added.append(gw)
        time.sleep(1.5)
    snapshot(Path(csv_path))
    return f"giornate presenti {sorted(done | set(added))} (nuove: {added})"


def step_understat():
    m = importlib.import_module("download_understat")
    try:
        players, teams = m.get_season_data_via_library(SEASON_US)
    except Exception:
        players, teams = m.get_season_data_via_html(SEASON_US)
    p_path, n = m.write_players_csv(players, SEASON_US)
    t_path, nt = m.write_teams_csv(teams, SEASON_US)
    snapshot(p_path)
    snapshot(t_path)
    return f"{n} giocatori, {nt} squadre"


def step_prezzi_live():
    m = importlib.import_module("scrape_prezzi_live")
    out = m.scrape_live(RAW / "wayback_prices", DATE_TAG)
    snapshot(out)
    return f"-> {Path(out).name}"


def step_mercato():
    m = importlib.import_module("scrape_mercato_fantacalcioit")
    outs = m.scrape_mercato(RAW / "mercato", DATE_TAG)
    for p in outs.values():
        snapshot(Path(p))
    return ", ".join(f"{k}: {Path(v).name}" for k, v in outs.items())


STEPS = [
    ("listone", step_listone),
    ("fantasoccer", step_fantasoccer),
    ("voti", step_voti),
    ("understat", step_understat),
    ("prezzi", step_prezzi_live),
    ("mercato", step_mercato),
]


def run(skip: set[str] = frozenset(), only: set[str] | None = None) -> dict:
    results = {}
    for name, fn in STEPS:
        if name in skip or (only and name not in only):
            continue
        t0 = time.time()
        print(f"[{name}] ...", flush=True)
        try:
            msg = fn()
            results[name] = ("ok", msg)
            print(f"[{name}] OK {msg} ({time.time()-t0:.0f}s)", flush=True)
        except ModuleNotFoundError as e:
            results[name] = ("skip", f"modulo mancante: {e.name}")
            print(f"[{name}] SKIP modulo mancante: {e.name}", flush=True)
        except Exception as e:
            results[name] = ("fail", f"{type(e).__name__}: {e}")
            print(f"[{name}] FALLITO {type(e).__name__}: {e}", flush=True)
            traceback.print_exc(limit=2)
    (SNAP / "_esito.txt").parent.mkdir(parents=True, exist_ok=True)
    with open(SNAP / "_esito.txt", "a", encoding="utf-8") as f:
        f.write(f"{datetime.now():%Y-%m-%d %H:%M} "
                + " | ".join(f"{k}={v[0]}" for k, v in results.items()) + "\n")
    return results


if __name__ == "__main__":
    args = sys.argv[1:]
    skip = set(args[args.index("--skip") + 1].split(",")) if "--skip" in args else set()
    only = set(args[args.index("--solo") + 1].split(",")) if "--solo" in args else None
    run(skip, only)
