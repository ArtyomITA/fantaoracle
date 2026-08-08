"""Smoke test torneo: 20 repliche col pool sintetico, tavolo senza B.

Esegui:  python tests/smoke_tournament.py
"""
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from smoke_auction import synth_pool  # noqa: E402
from smoke_season import synth_votes  # noqa: E402
from fantabot.tournament import SeasonPack, run_tournament  # noqa: E402

if __name__ == "__main__":
    pool = synth_pool(random.Random(1))
    votes = synth_votes({pid: p.ref_price for pid, p in pool.items()}, seed=2)
    pack = SeasonPack(season="synth", players=pool, votes_by_g=votes)
    spec = ["A", "A+", "C:stars_scrubs", "C:semitop", "C:tifoso",
            "C:ancorato", "C:panic", "C:tirchio", "C:enforcer", "C:medio"]
    out = Path(__file__).parents[1] / "data" / "smoke_tournament"
    summary = run_tournament(pack, spec, n_replicas=20, out_dir=out,
                             n_calendars=50, workers=6, save_logs_every=10)
    print(f"{'bot':16s} {'win':>6s} {'rank':>6s} {'pts vs tavolo':>14s} {'residuo':>8s}")
    for k, v in sorted(summary["bots"].items(), key=lambda kv: kv[1]["avg_rank"]):
        print(f"{k:16s} {v['win_rate']:6.1%} {v['avg_rank']:6.2f} "
              f"{v['pts_vs_table_mean']:+14.1f} {v['avg_leftover']:8.1f}")
