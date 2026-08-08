"""Stagione simulata: rose -> 38 giornate coi fantavoti reali -> classifiche.

Due classifiche:
- punti totali (somma fantapunti stagione);
- campionato H2H: calendario round-robin tra le 10 squadre ripetuto su 38
  giornate, gol via soglie 66+6, 3/1/0; ripetuto con N calendari casuali
  per lavare via la fortuna del sorteggio.
"""
from __future__ import annotations

import itertools
import random
from dataclasses import dataclass, field

from .lineup import BASELINE, goals_from_points, pick_lineup, score_giornata


@dataclass
class SeasonResult:
    total_points: dict[str, float]
    h2h_tables: list[dict[str, int]]                 # una classifica (punti lega) per calendario
    giornata_scores: dict[str, list[float]] = field(default_factory=dict)

    def h2h_avg_rank(self) -> dict[str, float]:
        ranks: dict[str, list[int]] = {}
        for table in self.h2h_tables:
            orderd = sorted(table.items(),
                            key=lambda kv: (-kv[1], -self.total_points[kv[0]]))
            for pos, (team, _) in enumerate(orderd, start=1):
                ranks.setdefault(team, []).append(pos)
        return {t: sum(r) / len(r) for t, r in ranks.items()}

    def h2h_win_rate(self) -> dict[str, float]:
        wins: dict[str, int] = {}
        for table in self.h2h_tables:
            best = max(table.items(),
                       key=lambda kv: (kv[1], self.total_points[kv[0]]))
            wins[best[0]] = wins.get(best[0], 0) + 1
        return {t: wins.get(t, 0) / len(self.h2h_tables)
                for t in self.total_points}


def round_robin(teams: list[str], rng: random.Random) -> list[list[tuple[str, str]]]:
    """Calendario berger per n squadre (n pari): n-1 giornate."""
    ts = teams[:]
    rng.shuffle(ts)
    n = len(ts)
    rounds = []
    for _ in range(n - 1):
        rounds.append([(ts[i], ts[n - 1 - i]) for i in range(n // 2)])
        ts.insert(1, ts.pop())
    return rounds


def simulate_season(rosters: dict[str, dict[str, list[str]]],
                    votes_by_g: list[dict[str, float]],
                    n_calendars: int = 100,
                    max_subs: int = 3,
                    seed: int = 0,
                    voti_by_g: list[dict[str, float]] | None = None,
                    use_mod_difesa: bool = False) -> SeasonResult:
    """rosters: team_id -> {ruolo -> [player_id]};
    votes_by_g: lista di 38 dict player_id -> fantavoto;
    voti_by_g: voti PURI per giornata (necessari se use_mod_difesa)."""
    rng = random.Random(seed)
    teams = sorted(rosters)
    giornata_scores: dict[str, list[float]] = {t: [] for t in teams}
    form_sum: dict[str, float] = {}
    form_n: dict[str, int] = {}
    fvoto_sum: dict[str, float] = {}
    fvoto_n: dict[str, int] = {}

    for g, votes in enumerate(votes_by_g):
        voti_puri = voti_by_g[g] if voti_by_g else None
        form = {pid: form_sum[pid] / form_n[pid] for pid in form_sum}
        form_voto = {pid: fvoto_sum[pid] / fvoto_n[pid] for pid in fvoto_sum}
        # disponibilita' nota prima della formazione (infortuni/squalifiche):
        # nel backtest = chi ha giocato davvero quella giornata; identica per
        # tutte le squadre, quindi il confronto resta pulito
        available = set(votes.keys())
        for t in teams:
            _, starters, bench = pick_lineup(rosters[t], form, form_voto,
                                             use_mod_difesa, available)
            pts, _ = score_giornata(starters, bench, votes, max_subs,
                                    voti_puri, use_mod_difesa)
            giornata_scores[t].append(pts)
        for pid, fv in votes.items():   # la forma si aggiorna DOPO la giornata
            form_sum[pid] = form_sum.get(pid, 0.0) + fv
            form_n[pid] = form_n.get(pid, 0) + 1
        if voti_puri:
            for pid, vv in voti_puri.items():
                fvoto_sum[pid] = fvoto_sum.get(pid, 0.0) + vv
                fvoto_n[pid] = fvoto_n.get(pid, 0) + 1

    total = {t: sum(v) for t, v in giornata_scores.items()}
    n_g = len(votes_by_g)
    h2h_tables = []
    for _ in range(n_calendars):
        rounds = round_robin(teams, rng)
        table = {t: 0 for t in teams}
        for g in range(n_g):
            for home, away in rounds[g % len(rounds)]:
                gh = goals_from_points(giornata_scores[home][g])
                ga = goals_from_points(giornata_scores[away][g])
                if gh > ga:
                    table[home] += 3
                elif ga > gh:
                    table[away] += 3
                else:
                    table[home] += 1
                    table[away] += 1
        h2h_tables.append(table)
    return SeasonResult(total, h2h_tables, giornata_scores)
