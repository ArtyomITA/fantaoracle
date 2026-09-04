"""Regole esatte della lega dell'utente, in un posto solo.

- modificatore difesa: media voti puri portiere + 3 migliori difensori,
  modulo con almeno 4 difensori; fasce 6/6.25/6.5/6.75/7 -> +1/+2/+3/+4/+5
- bonus porta inviolata +1 al portiere (gol subiti = 0, ha giocato)
- 3 cambi, soglie gol 66 e +6, rosa 3P/8D/8C/6A, 500 crediti
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd

MOD_DIFESA_TABLE = [(7.0, 5), (6.75, 4), (6.5, 3), (6.25, 2), (6.0, 1)]
CLEAN_SHEET_BONUS = 1.0
QUOTAS = {"P": 3, "D": 8, "C": 8, "A": 6}
BUDGET = 500
MAX_SUBS = 3


def clean_sheets(root: Path, season: str) -> set[tuple[str, int]]:
    """(master_id, giornata) in cui il portiere ha giocato senza subire gol.
    Fonte: voti grezzi fantacalcio.it (gol_subiti) + mappa nomi 0b."""
    raw = pd.read_csv(root / "data" / "raw" / "voti" / f"voti_{season}.csv")
    mv = pd.read_csv(root / "data" / "processed" / "_match" / "map_voti.csv")
    mv = mv[mv.stagione == season]
    raw = raw.merge(mv[["squadra", "nome", "master_id"]], on=["squadra", "nome"], how="left")
    raw = raw[raw.master_id.notna() & (raw.ruolo.str.lower() == "p")
              & (raw.sv.fillna(0) == 0) & (raw.gol_subiti.fillna(0) == 0)]
    return {(str(int(r.master_id)), int(r.giornata)) for r in raw.itertuples(index=False)}


def apply_clean_sheet(votes_by_g: list[dict[str, float]],
                      cs: set[tuple[str, int]]) -> list[dict[str, float]]:
    out = []
    for g, d in enumerate(votes_by_g, start=1):
        out.append({pid: fv + (CLEAN_SHEET_BONUS if (pid, g) in cs else 0.0)
                    for pid, fv in d.items()})
    return out
