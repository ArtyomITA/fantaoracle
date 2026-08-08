# -*- coding: utf-8 -*-
"""Fase 0b — costruisce data/processed/registry.csv (spina dorsale giocatori).

master_id = player_id fantacalcio.it (stabile tra stagioni).
Formato lungo: una riga per (master_id, stagione) con nome, squadra, ruolo, Qt.I, FVM.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from f0b_lib import PROC, load_registry  # noqa: E402


def main():
    PROC.mkdir(parents=True, exist_ok=True)
    reg = load_registry()
    # sanity: id stabile -> stesso giocatore: controlla che il nome resti simile
    n_masters = reg.master_id.nunique()
    per_season = reg.groupby("stagione").size()
    dup = reg.duplicated(["master_id", "stagione"]).sum()
    assert dup == 0, f"{dup} duplicati (master_id, stagione)"
    reg.to_csv(PROC / "registry.csv", index=False, encoding="utf-8")
    print(f"registry.csv: {len(reg)} righe, {n_masters} giocatori unici")
    print(per_season.to_string())
    # quante stagioni per giocatore (distribuzione)
    print("stagioni per master:", reg.groupby("master_id").size().value_counts().sort_index().to_dict())


if __name__ == "__main__":
    main()
