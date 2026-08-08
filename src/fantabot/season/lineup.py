"""Lineup engine per la stagione simulata — identico per tutte le squadre.

Politica senza senno di poi: i titolari si scelgono con la fantamedia mobile
dei voti REALI fino alla giornata precedente (baseline 6.0 per chi non ha
ancora voti). Poi la giornata si calcola coi fantavoti reali: titolare senza
voto -> subentra la prima riserva dello stesso ruolo con voto (max N cambi).
Slot rimasti scoperti valgono 0 (stessa regola per tutti).
"""
from __future__ import annotations

MODULES = [(3, 4, 3), (3, 5, 2), (4, 3, 3), (4, 4, 2), (4, 5, 1),
           (5, 3, 2), (5, 4, 1)]
BASELINE = 6.0
BASELINE_VOTO = 5.9

# modificatore difesa (default Leghe Fantacalcio): media voti PURI di
# portiere + 3 migliori difensori, richiede modulo con almeno 4 difensori
MOD_DIFESA_TABLE = [(7.0, 6), (6.75, 4), (6.5, 3), (6.25, 2), (6.0, 1)]


def mod_difesa_bonus(media: float, table=MOD_DIFESA_TABLE) -> int:
    for soglia, bonus in table:
        if media >= soglia:
            return bonus
    return 0


def pick_lineup(roster: dict[str, list[str]], form: dict[str, float],
                form_voto: dict[str, float] | None = None,
                use_mod_difesa: bool = False,
                available: set[str] | None = None):
    """roster: ruolo -> [player_id]; form: player_id -> fantamedia mobile;
    form_voto: media voto puro mobile (per stimare il modificatore);
    available: chi e' disponibile QUESTA giornata (infortunati/squalificati
    noti prima della formazione, come le probabili) — i disponibili vengono
    schierati per primi, gli indisponibili scivolano in fondo (titolari solo
    se il reparto non basta, caso raro: "a volte capita di giocare in meno").
    Ritorna (modulo, titolari per ruolo, panchina ordinata per ruolo)."""
    def rank_key(pid):
        unavailable = 1 if (available is not None and pid not in available) else 0
        return (unavailable, -form.get(pid, BASELINE))
    ranked = {r: sorted(roster[r], key=rank_key) for r in roster}
    best, best_score = None, -1.0
    for d, c, a in MODULES:
        need = {"P": 1, "D": d, "C": c, "A": a}
        if any(len(ranked[r]) < n for r, n in need.items()):
            continue
        score = sum(form.get(pid, BASELINE)
                    for r, n in need.items() for pid in ranked[r][:n])
        if use_mod_difesa and d >= 4 and form_voto is not None:
            gk = ranked["P"][0]
            dvs = sorted((form_voto.get(pid, BASELINE_VOTO)
                          for pid in ranked["D"][:d]), reverse=True)[:3]
            media_att = (form_voto.get(gk, BASELINE_VOTO) + sum(dvs)) / (1 + len(dvs))
            # stima prudente: la media attesa oscilla, sconta mezzo gradino
            score += mod_difesa_bonus(media_att - 0.1)
        if score > best_score:
            best_score = score
            best = need
    starters = {r: ranked[r][:n] for r, n in best.items()}
    bench = {r: ranked[r][best[r]:] for r in best}
    return best, starters, bench


def score_giornata(starters: dict[str, list[str]], bench: dict[str, list[str]],
                   votes: dict[str, float], max_subs: int = 3,
                   voti_puri: dict[str, float] | None = None,
                   use_mod_difesa: bool = False) -> tuple[float, int]:
    """votes: player_id -> fantavoto della giornata (assente = non giocato);
    voti_puri: player_id -> voto puro (per il modificatore difesa).
    Ritorna (totale squadra, cambi usati)."""
    total, subs_used = 0.0, 0
    counted: dict[str, list[str]] = {r: [] for r in starters}
    for role, ids in starters.items():
        bench_iter = iter(bench.get(role, []))
        for pid in ids:
            if pid in votes:
                total += votes[pid]
                counted[role].append(pid)
                continue
            if subs_used < max_subs:
                for bpid in bench_iter:
                    if bpid in votes:
                        total += votes[bpid]
                        counted[role].append(bpid)
                        subs_used += 1
                        break
    if (use_mod_difesa and voti_puri is not None
            and len(starters.get("D", [])) >= 4
            and counted["P"] and len(counted["D"]) >= 4):
        gk_v = voti_puri.get(counted["P"][0])
        dvs = sorted((voti_puri[pid] for pid in counted["D"]
                      if pid in voti_puri), reverse=True)[:3]
        if gk_v is not None and len(dvs) == 3:
            media = (gk_v + sum(dvs)) / 4
            total += mod_difesa_bonus(media)
    return total, subs_used


def goals_from_points(points: float, threshold: int = 66, step: int = 6) -> int:
    if points < threshold:
        return 0
    return int((points - threshold) // step) + 1
