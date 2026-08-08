"""Sanity replica singola col modificatore difesa attivo."""
import pickle
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from fantabot.tournament import run_replica  # noqa: E402

if __name__ == "__main__":
    with open(ROOT / "data" / "packs" / "pack_2024-25.pkl", "rb") as f:
        pack = pickle.load(f)
    print(f"voti_by_g g1: {len(pack.voti_by_g[0])} voti puri | mod: {pack.use_mod_difesa}")
    spec = ["B", "A", "A+", "C:stars_scrubs", "C:semitop", "C:tifoso",
            "C:ancorato", "C:panic", "C:tirchio", "C:enforcer"]
    r = run_replica(pack, spec, seed=555, n_calendars=30)
    for k, v in sorted(r["teams"].items(), key=lambda kv: kv[1]["h2h_avg_rank"]):
        print(f"{k:16s} punti {v['total_points']:7.1f} rank {v['h2h_avg_rank']:.2f} "
              f"residuo {v['leftover']}")
