"""Smoke test stagione: asta sintetica -> 38 giornate sintetiche -> classifiche.

Esegui:  python tests/smoke_season.py
"""
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from smoke_auction import run_once, QUOTAS  # noqa: E402
from fantabot.models import ROLES  # noqa: E402
from fantabot.season import simulate_season  # noqa: E402


def synth_votes(pool_ids_by_skill: dict[str, float], seed: int):
    """38 giornate: presenza ~75% (piu' alta per i top), fantavoto ~ N(mu, 2.2)
    con mu legato allo skill (ref_price)."""
    rng = random.Random(seed)
    votes_by_g = []
    for _ in range(38):
        votes = {}
        for pid, skill in pool_ids_by_skill.items():
            p_play = min(0.92, 0.55 + skill * 2.5)
            if rng.random() < p_play:
                mu = 5.6 + skill * 14        # top (~0.38) -> mu ~ 10.9
                votes[pid] = round(rng.gauss(mu, 2.2) * 2) / 2
        votes_by_g.append(votes)
    return votes_by_g


if __name__ == "__main__":
    teams, eng = run_once(seed=7)
    rosters = {}
    for t in teams:
        rosters[t.bot_name] = {r: [pid for pid, _ in t.roster[r]] for r in ROLES}

    # skill dal ref_price del pool originale (l'engine ha consumato il pool)
    pool = {}
    for e in eng.events:
        if e.kind == "hammer":
            pool[e.payload["player_id"]] = None
    import smoke_auction
    full_pool = smoke_auction.synth_pool(random.Random(7))
    skills = {pid: p.ref_price for pid, p in full_pool.items()}

    votes = synth_votes(skills, seed=42)
    res = simulate_season(rosters, votes, n_calendars=100, seed=1)

    print("Classifica punti totali:")
    for t, pts in sorted(res.total_points.items(), key=lambda kv: -kv[1]):
        print(f"  {t:16s} {pts:8.1f}")
    print("\nWin rate H2H (100 calendari):")
    for t, wr in sorted(res.h2h_win_rate().items(), key=lambda kv: -kv[1]):
        print(f"  {t:16s} {wr:5.0%}   rank medio {res.h2h_avg_rank()[t]:.2f}")
