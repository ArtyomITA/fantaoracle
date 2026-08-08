"""Modello VALORE baseline: "Marcel" adattato al fantacalcio.

Proiezione dei fantapunti stagionali da storico multi-stagione:
- fantamedia delle ultime 3 stagioni pesata (5/4/3) e pesata per presenze;
- regressione verso la media di ruolo proporzionale a quanto poco ha giocato;
- proiezione presenze = miscela presenze recenti / cap 34;
- punti attesi = fantamedia proiettata x presenze proiettate.

Input: votes long-format (master_id, stagione, fantavoto per giornata) gia'
filtrato senza S.V. Tutto rigorosamente pre-cutoff: il chiamante passa solo
le stagioni precedenti l'asta.
"""
from __future__ import annotations

import pandas as pd

SEASON_WEIGHTS = (5.0, 4.0, 3.0)      # stagione -1, -2, -3
REGRESSION_GAMES = 15.0               # peso della "palla di regressione" al ruolo
MAX_GAMES = 34.0


def role_baselines(votes: pd.DataFrame, registry: pd.DataFrame) -> dict[str, float]:
    """Fantamedia media di ruolo (pool rosterabile) nelle stagioni date."""
    v = votes.merge(registry[["master_id", "ruolo"]].drop_duplicates("master_id"),
                    on="master_id", how="left")
    return v.groupby("ruolo")["fantavoto"].mean().to_dict()


def project_players(votes_prev: pd.DataFrame, registry: pd.DataFrame,
                    seasons_desc: list[str]) -> pd.DataFrame:
    """votes_prev: voti delle (max 3) stagioni precedenti; seasons_desc:
    le stesse ordinate dalla piu' recente. Ritorna master_id, fm_proj,
    games_proj, exp_points."""
    base = role_baselines(votes_prev, registry)
    rows = []
    reg = registry[["master_id", "ruolo"]].drop_duplicates("master_id")
    grouped = votes_prev.groupby(["master_id", "stagione"])["fantavoto"] \
                        .agg(["mean", "count"]).reset_index()
    for mid, g in grouped.groupby("master_id"):
        num = den = 0.0
        games_w = games_n = 0.0
        for i, s in enumerate(seasons_desc[:3]):
            row = g[g["stagione"] == s]
            if row.empty:
                continue
            fm, n = float(row["mean"].iloc[0]), float(row["count"].iloc[0])
            w = SEASON_WEIGHTS[i] * n
            num += fm * w
            den += w
            games_w += SEASON_WEIGHTS[i] * n
            games_n += SEASON_WEIGHTS[i]
        if den == 0:
            continue
        ruolo = reg.loc[reg["master_id"] == mid, "ruolo"]
        rb = base.get(ruolo.iloc[0] if not ruolo.empty else None, 6.0)
        fm_proj = (num + rb * REGRESSION_GAMES) / (den + REGRESSION_GAMES)
        games_recent = games_w / games_n if games_n else 0.0
        games_proj = min(MAX_GAMES, 0.75 * games_recent + 0.25 * MAX_GAMES * 0.5)
        rows.append({"master_id": mid, "fm_proj": fm_proj,
                     "games_proj": games_proj,
                     "exp_points": fm_proj * games_proj})
    return pd.DataFrame(rows)
