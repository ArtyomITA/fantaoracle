"""Smoke test B: predizioni sintetiche quasi-perfette -> B deve dominare.

Nel mondo sintetico i voti derivano dal ref_price, quindi dare a B quantili
centrati sul ref equivale a un modello ottimo: se B non vince QUI, la policy
e' rotta. (Il test vero, con predizioni imperfette, arriva coi dati reali.)

Esegui:  python tests/smoke_bot_b.py
"""
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from smoke_auction import synth_pool  # noqa: E402
from smoke_season import synth_votes  # noqa: E402
import fantabot.tournament as T  # noqa: E402
from fantabot.bots import BBot  # noqa: E402


def make_predictions(pool, budget, rng):
    pred = {}
    for pid, p in pool.items():
        q50 = max(1.0, p.ref_price * budget * rng.lognormvariate(0, 0.10))
        pred[pid] = {"q10": q50 * 0.75, "q50": q50, "q90": q50 * 1.30,
                     "value": p.exp_points}
    return pred


if __name__ == "__main__":
    pool = synth_pool(random.Random(1))
    votes = synth_votes({pid: p.ref_price for pid, p in pool.items()}, seed=2)
    pack = T.SeasonPack(season="synth", players=pool, votes_by_g=votes,
                        b_predictions=make_predictions(pool, 500, random.Random(99)))
    spec = ["B", "A", "A+", "C:stars_scrubs", "C:semitop", "C:tifoso",
            "C:ancorato", "C:panic", "C:tirchio", "C:enforcer"]
    out = Path(__file__).parents[1] / "data" / "smoke_bot_b"
    summary = T.run_tournament(pack, spec, n_replicas=12, out_dir=out,
                               n_calendars=50, workers=6, save_logs_every=6)
    print(f"{'bot':16s} {'win':>6s} {'rank':>6s} {'pts vs tavolo':>14s} {'residuo':>8s}")
    for k, v in sorted(summary["bots"].items(), key=lambda kv: kv[1]["avg_rank"]):
        print(f"{k:16s} {v['win_rate']:6.1%} {v['avg_rank']:6.2f} "
              f"{v['pts_vs_table_mean']:+14.1f} {v['avg_leftover']:8.1f}")
