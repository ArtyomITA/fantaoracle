"""VORP -> crediti: la formula classica, usata dal bot A e come baseline
del modello prezzo.

replacement di ruolo = valore del miglior giocatore che a fine asta prendi
a 1 credito ~ il (quota_ruolo x n_squadre + 1)-esimo per punti attesi.
Prezzo equo = quota proporzionale del monte crediti spendibile sopra il
replacement.
"""
from __future__ import annotations

import pandas as pd

from ..models import ROLES


def vorp_prices(players: pd.DataFrame, quotas: dict[str, int],
                n_teams: int, budget: int) -> pd.DataFrame:
    """players: master_id, ruolo, exp_points. Ritorna master_id, vorp,
    prezzo_equo (in crediti, >= 1)."""
    total_slots = sum(quotas.values()) * n_teams
    spendable = n_teams * budget - total_slots  # 1 credito obbligato per slot
    df = players.copy()
    df["vorp"] = 0.0
    for r in ROLES:
        sub = df[df["ruolo"] == r].sort_values("exp_points", ascending=False)
        cut = quotas[r] * n_teams
        if len(sub) > cut:
            replacement = float(sub["exp_points"].iloc[cut])
        else:
            replacement = float(sub["exp_points"].min() if len(sub) else 0.0)
        df.loc[df["ruolo"] == r, "vorp"] = (df.loc[df["ruolo"] == r, "exp_points"]
                                            - replacement).clip(lower=0.0)
    pos = df["vorp"].sum()
    df["prezzo_equo"] = 1.0 + (df["vorp"] / pos * spendable if pos > 0 else 0.0)
    return df[["master_id", "vorp", "prezzo_equo"]]
