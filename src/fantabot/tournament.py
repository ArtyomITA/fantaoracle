"""Torneo: N repliche di (asta -> stagione) per una composizione di tavolo.

Uso tipico (dopo Fase 0b, quando esistono i SeasonPack reali):
    pack = load_pack("2024-25")
    spec = ["B", "A", "A+", "C:stars_scrubs", "C:semitop", "C:tifoso",
            "C:ancorato", "C:panic", "C:tirchio", "C:enforcer"]
    summary = run_tournament(pack, spec, n_replicas=200, out_dir=...)

Il seggio "B" e' un factory pluggabile: finche' la pipeline di Fase 1 non
esiste, `make_bot` solleva errore se richiesto B senza factory registrata.
"""
from __future__ import annotations

import json
import random
from concurrent.futures import ProcessPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path

from .bots import ABot, BBot, CBot
from .bots.base import Bot
from .engine import AuctionEngine
from .models import ROLES, Player
from .season import simulate_season


@dataclass
class SeasonPack:
    """Tutto cio' che serve per giocare una stagione passata."""
    season: str
    players: dict[str, Player]                 # pool d'asta con ref_price/sd/exp_points
    votes_by_g: list[dict[str, float]]         # 38 dict player_id -> fantavoto
    quotas: dict[str, int] = field(default_factory=lambda: {"P": 3, "D": 8, "C": 8, "A": 6})
    budget: int = 500
    # predizioni della pipeline B (Fase 1): player_id -> {q10,q50,q90,value}.
    # Stanno nel pack (e non in un global) perche' devono viaggiare verso i
    # worker process del torneo.
    b_predictions: dict[str, dict] | None = None
    # lista prezzi VORP per il bot A (player_id -> crediti equi)
    a_price_list: dict[str, float] | None = None
    # voti PURI per giornata + flag modificatore difesa (lega dell'utente: SI)
    voti_by_g: list[dict[str, float]] | None = None
    use_mod_difesa: bool = False


def make_bot(spec: str, rng: random.Random, pack: SeasonPack) -> Bot:
    if spec == "A":
        return ABot(rng, price_list=pack.a_price_list)
    if spec == "A+":
        return ABot(rng, price_list=pack.a_price_list, flexible=True)
    if spec.startswith("C:"):
        prof = spec.split(":", 1)[1]
        fav = None
        if prof == "tifoso":
            fav = rng.choice(sorted({p.team for p in pack.players.values()}))
        hint = pack.a_price_list if prof == "informato" else None
        return CBot(rng, prof, fav_team=fav, hint_prices=hint)
    if spec == "B":
        if pack.b_predictions is None:
            raise RuntimeError("Seggio B richiesto ma pack.b_predictions mancante")
        return BBot(rng, pack.b_predictions)
    raise ValueError(f"spec bot sconosciuta: {spec}")


def run_replica(pack: SeasonPack, table_spec: list[str], seed: int,
                log_path: str | None = None, n_calendars: int = 100) -> dict:
    rng = random.Random(seed)
    bots = [make_bot(s, random.Random(seed * 1000 + i), pack)
            for i, s in enumerate(table_spec)]
    eng = AuctionEngine(dict(pack.players), bots, pack.quotas, pack.budget,
                        rng)
    teams = eng.run()
    if log_path:
        eng.write_log(log_path)

    key = {}  # bot_name univoco per seggio (se due seggi hanno lo stesso nome, suffisso)
    seen: dict[str, int] = {}
    for t in teams:
        n = seen.get(t.bot_name, 0)
        seen[t.bot_name] = n + 1
        key[t.team_id] = t.bot_name if n == 0 else f"{t.bot_name}#{n+1}"

    rosters = {key[t.team_id]: {r: [pid for pid, _ in t.roster[r]] for r in ROLES}
               for t in teams}
    res = simulate_season(rosters, pack.votes_by_g,
                          n_calendars=n_calendars, seed=seed + 7,
                          voti_by_g=pack.voti_by_g,
                          use_mod_difesa=pack.use_mod_difesa)
    win = res.h2h_win_rate()
    rank = res.h2h_avg_rank()
    out = {"seed": seed, "table": table_spec, "teams": {}}
    for t in teams:
        k = key[t.team_id]
        out["teams"][k] = {
            "spec": table_spec[int(t.team_id[1:])],
            "spent": pack.budget - t.budget,
            "leftover": t.budget,
            "total_points": round(res.total_points[k], 1),
            "h2h_win_rate": round(win[k], 4),
            "h2h_avg_rank": round(rank[k], 3),
        }
    return out


_WORKER_PACK: SeasonPack | None = None


def _init_worker(pack_path: str):
    """Il pack si carica UNA volta per worker (non si serializza per job)."""
    global _WORKER_PACK
    import pickle
    with open(pack_path, "rb") as f:
        _WORKER_PACK = pickle.load(f)


def _replica_star(args):
    return run_replica(_WORKER_PACK, *args)


def run_tournament(pack: SeasonPack, table_spec: list[str], n_replicas: int,
                   out_dir: str | Path, n_calendars: int = 100,
                   workers: int = 8, save_logs_every: int = 50) -> dict:
    import pickle
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    pack_path = out / "_pack.pkl"
    with open(pack_path, "wb") as f:
        pickle.dump(pack, f)
    jobs = []
    for i in range(n_replicas):
        log = str(out / "logs" / f"replica_{i:04d}.jsonl") if i % save_logs_every == 0 else None
        jobs.append((table_spec, 10_000 + i, log, n_calendars))
    results = []
    with ProcessPoolExecutor(max_workers=workers, initializer=_init_worker,
                             initargs=(str(pack_path),)) as ex:
        for r in ex.map(_replica_star, jobs, chunksize=4):
            results.append(r)
    with open(out / "replicas.jsonl", "w", encoding="utf-8") as f:
        for r in results:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    # aggregazione per bot-key
    agg: dict[str, dict[str, list[float]]] = {}
    for r in results:
        pts_mean = sum(v["total_points"] for v in r["teams"].values()) / len(r["teams"])
        for k, v in r["teams"].items():
            a = agg.setdefault(k, {"win": [], "rank": [], "pts_vs_table": [],
                                   "leftover": [], "points": []})
            a["win"].append(v["h2h_win_rate"])
            a["rank"].append(v["h2h_avg_rank"])
            a["pts_vs_table"].append(v["total_points"] - pts_mean)
            a["leftover"].append(v["leftover"])
            a["points"].append(v["total_points"])
    summary = {
        "season": pack.season, "table": table_spec, "n_replicas": n_replicas,
        "bots": {k: {
            "win_rate": round(sum(a["win"]) / len(a["win"]), 4),
            "avg_rank": round(sum(a["rank"]) / len(a["rank"]), 3),
            "pts_vs_table_mean": round(sum(a["pts_vs_table"]) / len(a["pts_vs_table"]), 1),
            "pct_above_table_mean": round(
                sum(1 for x in a["pts_vs_table"] if x > 0) / len(a["pts_vs_table"]), 3),
            "avg_leftover": round(sum(a["leftover"]) / len(a["leftover"]), 1),
            "avg_points": round(sum(a["points"]) / len(a["points"]), 1),
        } for k, a in agg.items()},
    }
    with open(out / "summary.json", "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)
    return summary
