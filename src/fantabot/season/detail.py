"""Dettaglio stagione per il viewer: giornata per giornata, scontri e voti.

Un calendario "ufficiale" (round robin, seed dato) raccontato per intero:
per ogni giornata i 5 scontri con gol e punteggi, e per ogni squadra la
formazione schierata con il fantavoto di ciascun giocatore (chi ha giocato,
chi e' subentrato, chi e' rimasto a 0), modulo e bonus modificatore.
"""
from __future__ import annotations

import random

from .lineup import (BASELINE, BASELINE_VOTO, goals_from_points,
                     mod_difesa_bonus, pick_lineup)
from .simulate import round_robin


def season_detail(rosters: dict[str, dict[str, list[str]]],
                  votes_by_g: list[dict[str, float]],
                  names: dict[str, str],
                  voti_by_g: list[dict[str, float]] | None = None,
                  use_mod_difesa: bool = False,
                  max_subs: int = 3,
                  cal_seed: int = 0) -> dict:
    teams = sorted(rosters)
    rounds = round_robin(teams, random.Random(cal_seed))
    form_sum: dict[str, float] = {}
    form_n: dict[str, int] = {}
    fvoto_sum: dict[str, float] = {}
    fvoto_n: dict[str, int] = {}
    table = {t: {"pts": 0, "w": 0, "d": 0, "l": 0, "gf": 0, "gs": 0,
                 "fanta": 0.0} for t in teams}
    giornate = []

    for g, votes in enumerate(votes_by_g):
        voti_puri = voti_by_g[g] if voti_by_g else None
        form = {pid: form_sum[pid] / form_n[pid] for pid in form_sum}
        form_voto = {pid: fvoto_sum[pid] / fvoto_n[pid] for pid in fvoto_sum}
        available = set(votes.keys())
        team_detail = {}
        for t in teams:
            module, starters, bench = pick_lineup(
                rosters[t], form, form_voto, use_mod_difesa, available)
            total, subs_used = 0.0, 0
            counted: dict[str, list[str]] = {r: [] for r in starters}
            lineup_rows = []
            for role, ids in starters.items():
                bench_iter = iter(bench.get(role, []))
                for pid in ids:
                    if pid in votes:
                        total += votes[pid]
                        counted[role].append(pid)
                        lineup_rows.append({
                            "pid": pid, "nome": names.get(pid, pid),
                            "ruolo": role, "fv": votes[pid], "stato": "tit"})
                        continue
                    subbed = False
                    if subs_used < max_subs:
                        for bpid in bench_iter:
                            if bpid in votes:
                                total += votes[bpid]
                                counted[role].append(bpid)
                                subs_used += 1
                                lineup_rows.append({
                                    "pid": bpid, "nome": names.get(bpid, bpid),
                                    "ruolo": role, "fv": votes[bpid],
                                    "stato": "sub",
                                    "per": names.get(pid, pid)})
                                subbed = True
                                break
                    if not subbed:
                        lineup_rows.append({
                            "pid": pid, "nome": names.get(pid, pid),
                            "ruolo": role, "fv": None, "stato": "assente"})
            mod_bonus = 0
            if (use_mod_difesa and voti_puri is not None
                    and len(starters.get("D", [])) >= 4
                    and counted["P"] and len(counted["D"]) >= 4):
                gk_v = voti_puri.get(counted["P"][0])
                dvs = sorted((voti_puri[pid] for pid in counted["D"]
                              if pid in voti_puri), reverse=True)[:3]
                if gk_v is not None and len(dvs) == 3:
                    mod_bonus = mod_difesa_bonus((gk_v + sum(dvs)) / 4)
                    total += mod_bonus
            team_detail[t] = {
                "modulo": f"{starters and len(starters['D'])}-"
                          f"{len(starters['C'])}-{len(starters['A'])}",
                "totale": round(total, 1), "mod_difesa": mod_bonus,
                "cambi": subs_used, "formazione": lineup_rows,
            }
        matches = []
        for home, away in rounds[g % len(rounds)]:
            th, ta = team_detail[home]["totale"], team_detail[away]["totale"]
            gh, ga = goals_from_points(th), goals_from_points(ta)
            matches.append({"casa": home, "fuori": away,
                            "pt_casa": th, "pt_fuori": ta,
                            "gol_casa": gh, "gol_fuori": ga})
            for t, gf, gs in ((home, gh, ga), (away, ga, gh)):
                table[t]["gf"] += gf
                table[t]["gs"] += gs
                table[t]["fanta"] += team_detail[t]["totale"]
            if gh > ga:
                table[home]["pts"] += 3
                table[home]["w"] += 1
                table[away]["l"] += 1
            elif ga > gh:
                table[away]["pts"] += 3
                table[away]["w"] += 1
                table[home]["l"] += 1
            else:
                table[home]["pts"] += 1
                table[away]["pts"] += 1
                table[home]["d"] += 1
                table[away]["d"] += 1
        giornate.append({"giornata": g + 1, "scontri": matches,
                         "squadre": team_detail,
                         "classifica": {t: dict(v) for t, v in table.items()}})
        for pid, fv in votes.items():
            form_sum[pid] = form_sum.get(pid, 0.0) + fv
            form_n[pid] = form_n.get(pid, 0) + 1
        if voti_puri:
            for pid, vv in voti_puri.items():
                fvoto_sum[pid] = fvoto_sum.get(pid, 0.0) + vv
                fvoto_n[pid] = fvoto_n.get(pid, 0) + 1

    return {"teams": teams, "giornate": giornate,
            "classifica_finale": table}
