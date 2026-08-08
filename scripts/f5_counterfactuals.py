"""Indagine sul 98% — esperimenti controfattuali (2024-25, tavolo principale).

E1  B-market : B con valore = punti impliciti nel prezzo di mercato
              (regressione lineare punti~ref sulle stagioni di train).
              Se vince ancora tanto -> l'edge e' policy/disciplina.
              Se crolla -> l'edge e' il modello valore CatBoost.
E2  C-informati : 7 avversari "informato" (mercato + hint VORP fantamedia).
              Mercato collettivamente piu' intelligente: quanto scende B?
E3  entrambe le stagioni per confronto simmetrico.

Uso: python f5_counterfactuals.py [n_repliche=100]
"""
from __future__ import annotations

import copy
import json
import pickle
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
PROC = ROOT / "data" / "processed"

from fantabot.tournament import run_tournament  # noqa: E402

C7 = ["C:stars_scrubs", "C:semitop", "C:tifoso", "C:ancorato",
      "C:panic", "C:tirchio", "C:enforcer"]
TRAIN = {"2024-25": ["2021-22", "2023-24"],
         "2025-26": ["2021-22", "2023-24", "2024-25"]}


def market_implied_values(pack, season: str) -> dict[str, float]:
    """Punti impliciti nel prezzo: fit lineare punti~ref sulle stagioni di
    train, applicato al ref della stagione target (niente hindsight)."""
    rows = []
    for s in TRAIN[season]:
        players = pd.read_parquet(PROC / f"players_{s}.parquet")
        v = pd.read_parquet(PROC / f"votes_{s}.parquet")
        if "sv" in v.columns:
            v = v[v["sv"].fillna(0) == 0]
        pts = v.groupby("master_id")["fantavoto"].sum()
        ref = players["target_mean_pct_all_estiva"].astype(float).fillna(
            players["target_wayback_p500_10sq"].astype(float) / 500).fillna(
            players["fvm"].astype(float) / 1000)
        for mid, r in zip(players["master_id"], ref):
            if pd.notna(r):
                rows.append((r, float(pts.get(mid, 0.0))))
    df = pd.DataFrame(rows, columns=["ref", "pts"])
    slope, intercept = np.polyfit(df["ref"], df["pts"], 1)
    return {pid: max(0.0, intercept + slope * p.ref_price)
            for pid, p in pack.players.items()}


def run_experiment(name, pack, spec, n, out_root):
    out = ROOT / "data" / out_root / pack.season / name
    if (out / "summary.json").exists():
        s = json.loads((out / "summary.json").read_text("utf-8"))
        print(f"  {name}: gia' fatto", flush=True)
        return s
    s = run_tournament(pack, spec, n_replicas=n, out_dir=out,
                       n_calendars=100, workers=8, save_logs_every=50)
    b = s["bots"].get("B")
    print(f"  {name}: B win {b['win_rate']:.1%} rank {b['avg_rank']:.2f} "
          f"pts {b['pts_vs_table_mean']:+.1f} residuo {b['avg_leftover']:.0f}",
          flush=True)
    return s


if __name__ == "__main__":
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 100
    t0 = time.time()
    for season in ["2024-25", "2025-26"]:
        with open(ROOT / "data" / "packs" / f"pack_{season}.pkl", "rb") as f:
            pack = pickle.load(f)
        print(f"=== {season} ===", flush=True)

        # E1: B col valore implicito del mercato
        pack_e1 = copy.deepcopy(pack)
        mkt = market_implied_values(pack, season)
        for pid, d in pack_e1.b_predictions.items():
            d["value"] = round(mkt.get(pid, 0.0), 1)
        run_experiment("E1_B_market", pack_e1, ["B", "A", "A+"] + C7, n,
                       "counterfactuals")

        # E2: avversari tutti informati
        run_experiment("E2_C_informati", pack,
                       ["B", "A", "A+"] + ["C:informato"] * 7, n,
                       "counterfactuals")
    print(f"[{time.time()-t0:.0f}s] fatto")
