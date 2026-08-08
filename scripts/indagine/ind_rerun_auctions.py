# -*- coding: utf-8 -*-
"""Ri-esegue le 150 aste (deterministiche dato il seed) per 2024-25 e 2025-26 main
e salva le rose complete (bot, player_id, prezzo) in CSV.
Verifica il determinismo confrontando i seed loggati (10000/10025/...) con i log salvati.
Parallelo su piu' processi; riprende da dove era rimasto (un file per seed)."""
import json
import pickle
import random
import sys
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

sys.path.insert(0, r"src")
from fantabot.engine import AuctionEngine          # noqa: E402
from fantabot.models import ROLES                  # noqa: E402
from fantabot.tournament import make_bot           # noqa: E402

BASE = Path(r"data\tournament_mod")
OUT = Path(r"data\processed\indagine")

TABLE = ["B", "A", "A+", "C:stars_scrubs", "C:semitop", "C:tifoso",
         "C:ancorato", "C:panic", "C:tirchio", "C:enforcer"]

_PACK = None
_SEASON = None


def run_auction(pack, table_spec, seed):
    rng = random.Random(seed)
    bots = [make_bot(s, random.Random(seed * 1000 + i), pack)
            for i, s in enumerate(table_spec)]
    eng = AuctionEngine(dict(pack.players), bots, pack.quotas, pack.budget, rng)
    teams = eng.run()
    key, seen = {}, {}
    for t in teams:
        n = seen.get(t.bot_name, 0)
        seen[t.bot_name] = n + 1
        key[t.team_id] = t.bot_name if n == 0 else f"{t.bot_name}#{n+1}"
    rows = []
    for t in teams:
        for r in ROLES:
            for pid, price in t.roster[r]:
                rows.append((seed, key[t.team_id], r, pid, price))
    return rows


def verify(season, comp_dir, rows_seed, replica_idx):
    log = comp_dir / "logs" / f"replica_{replica_idx:04d}.jsonl"
    if not log.exists():
        return True
    hammers = []
    with open(log, encoding="utf-8") as f:
        for line in f:
            e = json.loads(line)
            if e.get("kind") == "hammer":
                hammers.append((e["bot"], e["player_id"], e["price"]))
    mine = [(b, pid, pr) for (_s, b, _r, pid, pr) in rows_seed]
    ok = sorted(hammers) == sorted(mine)
    print(f"[{season}] verifica replica {replica_idx} (seed {10000+replica_idx}): "
          f"{'OK' if ok else 'MISMATCH'}", flush=True)
    return ok


def _init(season):
    global _PACK, _SEASON
    _SEASON = season
    with open(BASE / season / "main_1B_2A_7C" / "_pack.pkl", "rb") as f:
        _PACK = pickle.load(f)


def _job(seed):
    part = OUT / "parts" / f"{_SEASON}_{seed}.csv"
    if part.exists() and part.stat().st_size > 0:
        return seed, "skip"
    rows = run_auction(_PACK, TABLE, seed)
    tmp = part.with_suffix(".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        for seed_, bot, role, pid, price in rows:
            f.write(f"{seed_},{bot},{role},{pid},{price}\n")
    tmp.replace(part)
    return seed, "done"


def main():
    (OUT / "parts").mkdir(parents=True, exist_ok=True)
    for season in ["2024-25", "2025-26"]:
        comp = BASE / season / "main_1B_2A_7C"
        seeds = [10_000 + i for i in range(150)]
        done = 0
        with ProcessPoolExecutor(max_workers=6, initializer=_init,
                                 initargs=(season,)) as ex:
            for seed, st in ex.map(_job, seeds):
                done += 1
                if done % 5 == 0 or done == 150:
                    print(f"[{season}] {done}/150 (ultimo seed {seed} {st})", flush=True)
        # concatena + verifica contro i log salvati
        all_rows = []
        for seed in seeds:
            part = OUT / "parts" / f"{season}_{seed}.csv"
            with open(part, encoding="utf-8") as f:
                for line in f:
                    s, bot, role, pid, price = line.rstrip("\n").split(",")
                    all_rows.append((int(s), bot, role, pid, int(price)))
        ok_all = True
        for idx in [0, 25, 50, 75, 100, 125]:
            rows_seed = [r for r in all_rows if r[0] == 10_000 + idx]
            ok_all &= verify(season, comp, rows_seed, idx)
        out = OUT / f"rosters_{season}.csv"
        with open(out, "w", encoding="utf-8") as f:
            f.write("seed,bot,role,player_id,price\n")
            for seed, bot, role, pid, price in all_rows:
                f.write(f"{seed},{bot},{role},{pid},{price}\n")
        print(f"[{season}] {'VERIFICA OK' if ok_all else 'VERIFICA FALLITA'} - "
              f"scritte {len(all_rows)} righe -> {out}", flush=True)


if __name__ == "__main__":
    main()
