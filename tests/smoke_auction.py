"""Smoke test motore d'asta: pool sintetico, 10 bot, invarianti.

Esegui:  python tests/smoke_auction.py
"""
import random
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from fantabot.models import Player, ROLES
from fantabot.engine import AuctionEngine
from fantabot.bots import ABot, CBot

QUOTAS = {"P": 3, "D": 8, "C": 8, "A": 6}
BUDGET = 500
N_TEAMS = 10

# distribuzione ref_price sintetica per ruolo: (n giocatori, quota reparto,
# cap del top in % budget — stile prezzi reali: top attaccante ~36-38%)
POOL_SPEC = {
    "P": (60, 0.09, 0.10),
    "D": (180, 0.14, 0.16),
    "C": (180, 0.25, 0.28),
    "A": (120, 0.52, 0.38),
}


def synth_pool(rng: random.Random) -> dict[str, Player]:
    """Il valore totale del pool deve valere ~N_TEAMS budget interi:
    250 giocatori comprati assorbono 10 x 500 crediti."""
    players = {}
    teams = [f"SQ{i}" for i in range(20)]
    for role, (n, role_share, top_cap) in POOL_SPEC.items():
        w = [1 / (i + 1) ** 1.0 for i in range(n)]
        target_total = role_share * N_TEAMS   # somma quote reparto su tutto il pool
        # normalizza con cap sul top: ridistribuisci l'eccesso sulla coda
        shares = [x / sum(w) * target_total for x in w]
        for _ in range(20):
            excess = sum(max(0.0, s - top_cap) for s in shares)
            if excess < 1e-9:
                break
            shares = [min(s, top_cap) for s in shares]
            room = [max(0.0, top_cap - s) for s in shares]
            room_tot = sum(room)
            shares = [s + excess * r / room_tot for s, r in zip(shares, room)]
        for i in range(n):
            pid = f"{role}{i:03d}"
            players[pid] = Player(
                player_id=pid, name=f"{role}_giocatore_{i:03d}", role=role,
                team=rng.choice(teams), ref_price=shares[i],
                exp_points=shares[i] * 500 + rng.uniform(-5, 5),
            )
    return players


def run_once(seed: int, log_path: str | None = None):
    rng = random.Random(seed)
    pool = synth_pool(rng)
    profiles = ["stars_scrubs", "semitop", "tifoso", "ancorato", "panic",
                "tirchio", "enforcer", "medio"]
    bots = [ABot(random.Random(seed + 1)), ABot(random.Random(seed + 2), flexible=True)]
    for i, prof in enumerate(profiles):
        fav = f"SQ{i}" if prof == "tifoso" else None
        bots.append(CBot(random.Random(seed + 10 + i), prof, fav_team=fav))
    eng = AuctionEngine(pool, bots, QUOTAS, BUDGET, rng)
    teams = eng.run()

    # --- invarianti ---
    for t in teams:
        assert t.budget >= 0, f"{t.bot_name}: budget negativo {t.budget}"
        for r in ROLES:
            assert len(t.roster[r]) == QUOTAS[r], \
                f"{t.bot_name}: {r} = {len(t.roster[r])}/{QUOTAS[r]}"
        spent = sum(pr for r in ROLES for _, pr in t.roster[r])
        assert spent + t.budget == BUDGET, f"{t.bot_name}: conti non tornano"
    all_ids = [pid for t in teams for r in ROLES for pid, _ in t.roster[r]]
    assert len(all_ids) == len(set(all_ids)) == sum(QUOTAS.values()) * N_TEAMS

    if log_path:
        eng.write_log(log_path)
    return teams, eng


if __name__ == "__main__":
    stats = Counter()
    leftover = []
    top_prices = []
    for seed in range(20):
        teams, eng = run_once(seed, log_path=None if seed else
                              str(Path(__file__).parents[1] / "data" / "sample_logs" / "smoke_seed0.jsonl"))
        for t in teams:
            leftover.append(t.budget)
            stats[t.bot_name] += sum(pr for r in ROLES for _, pr in t.roster[r])
        hammers = [e.payload for e in eng.events if e.kind == "hammer"]
        top_prices.append(max(h["price"] for h in hammers))
    n_events = len(eng.events)
    print(f"OK 20 aste. Eventi ultima asta: {n_events}")
    print(f"Crediti residui: media {sum(leftover)/len(leftover):.1f}, max {max(leftover)}")
    print(f"Prezzo top per asta: media {sum(top_prices)/len(top_prices):.0f}, "
          f"min {min(top_prices)}, max {max(top_prices)}")
    print("Spesa media per bot (su 20 aste):")
    for name, tot in sorted(stats.items()):
        print(f"  {name:16s} {tot/20:6.1f}")
