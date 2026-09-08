"""La probabilita' di scendere in campo dipende da quanto dura l'assenza?

Nel Monte Carlo ogni giornata e' un lancio di moneta indipendente con la stessa
probabilita' per tutta la stagione. Nei dati le presenze arrivano invece a
blocchi. La domanda e' se quei blocchi siano solo ETEROGENEITA' fra giocatori
(il titolare gioca sempre, la riserva quasi mai: due monete diverse, ognuna
comunque senza memoria) oppure vera dipendenza dalla durata dello stato.

Qui si separano le due cose: la correzione viene stimata SUL LOGIT del tasso
individuale, cosi' l'eterogeneita' e' gia' scontata. Poi si valida fuori
campione (stagione mai vista) contro la moneta a probabilita' costante.

Attenzione a cosa e' osservabile: i dati dicono solo se il giocatore ha preso
voto in quella giornata. Un mancato voto puo' essere infortunio, squalifica,
panchina o pochi minuti: qui si modella la PRESENZA A VOTO, non l'infortunio.

Uso: python scripts/indagine/prova_hazard_presenze.py
Output: data/livello0/prova_hazard_presenze.json
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
PROC = ROOT / "data" / "processed"
GIORNATE = 38
TRAIN = ["2021-22", "2023-24", "2024-25"]
TEST = "2025-26"
# stati: presente da 1, 2, 3+ giornate; assente da 1, 2, 3-4, 5+ giornate
STATI = ["P1", "P2", "P3+", "A1", "A2", "A3-4", "A5+"]


def matrice_presenze(season: str) -> pd.DataFrame:
    """righe = giocatore, colonne = giornata, valori 1/0 (ha preso voto)."""
    v = pd.read_parquet(PROC / f"votes_{season}.parquet")
    if "sv" in v.columns:
        v = v[v["sv"].fillna(0) == 0]
    v = v.copy()
    v["master_id"] = v["master_id"].astype(str)
    m = (v.assign(x=1).pivot_table(index="master_id", columns="giornata", values="x",
                                   aggfunc="max")
         .reindex(columns=range(1, GIORNATE + 1)).fillna(0.0))
    return m


def stato_di(storia: np.ndarray) -> str | None:
    """Stato alla vigilia della giornata, dalla sequenza delle precedenti."""
    if len(storia) == 0:
        return None
    ultimo = storia[-1]
    run = 1
    while run < len(storia) and storia[-1 - run] == ultimo:
        run += 1
    if ultimo == 1:
        return "P1" if run == 1 else ("P2" if run == 2 else "P3+")
    return {1: "A1", 2: "A2"}.get(run, "A3-4" if run <= 4 else "A5+")


def logit(p):
    p = np.clip(p, 1e-4, 1 - 1e-4)
    return np.log(p / (1 - p))


def raccogli(seasons: list[str], min_start: int = 3):
    """(stato, tasso individuale della stagione, esito) per ogni giocatore-giornata."""
    righe = []
    for s in seasons:
        m = matrice_presenze(s)
        tassi = m.mean(axis=1)
        for pid, riga in m.iterrows():
            x = riga.to_numpy()
            p_i = float(tassi[pid])
            if p_i <= 0.02 or p_i >= 0.98:      # senza variabilita' non informano
                continue
            for g in range(min_start, GIORNATE):
                st = stato_di(x[max(0, g - 6):g])
                if st is None:
                    continue
                righe.append((st, p_i, float(x[g])))
    return pd.DataFrame(righe, columns=["stato", "p_i", "y"])


def stima_offset(df: pd.DataFrame) -> dict:
    """Offset sul logit per stato, a parita' di tasso individuale."""
    out = {}
    for st in STATI:
        d = df[df["stato"] == st]
        if len(d) < 100:
            out[st] = 0.0
            continue
        # media empirica dell'esito meno media attesa dal solo tasso individuale
        p_att = d["p_i"].to_numpy()
        oss = d["y"].mean()
        att = p_att.mean()
        out[st] = round(float(logit(oss) - logit(att)), 4)
    return out


def brier(p: np.ndarray, y: np.ndarray) -> float:
    return float(np.mean((p - y) ** 2))


def main():
    tr = raccogli(TRAIN)
    off = stima_offset(tr)
    print(f"Train {TRAIN}: {len(tr)} giocatore-giornata")
    print("\nOffset sul logit per stato (a parita' di tasso individuale):")
    for st in STATI:
        d = tr[tr["stato"] == st]
        if len(d):
            print(f"  {st:5s} n={len(d):6d} osservato {d.y.mean():.3f} "
                  f"atteso dal tasso {d.p_i.mean():.3f} -> offset {off[st]:+.3f}")

    te = raccogli([TEST])
    p_cost = te["p_i"].to_numpy()
    p_haz = 1 / (1 + np.exp(-(logit(p_cost) + te["stato"].map(off).to_numpy())))
    y = te["y"].to_numpy()
    b0, b1 = brier(p_cost, y), brier(p_haz, y)
    print(f"\nTest {TEST}: {len(te)} giocatore-giornata")
    print(f"  Brier probabilita' costante {b0:.4f}")
    print(f"  Brier con stato            {b1:.4f}  ({(b1-b0)/b0:+.1%})")
    per_stato = {}
    for st in STATI:
        m = (te["stato"] == st).to_numpy()
        if m.sum() < 50:
            continue
        per_stato[st] = {"n": int(m.sum()), "brier_costante": round(brier(p_cost[m], y[m]), 4),
                         "brier_stato": round(brier(p_haz[m], y[m]), 4)}
        print(f"    {st:5s} n={m.sum():6d} {per_stato[st]['brier_costante']:.4f} -> "
              f"{per_stato[st]['brier_stato']:.4f}")
    out = {"offset": off, "n_train": len(tr), "n_test": len(te),
           "brier_costante": round(b0, 4), "brier_stato": round(b1, 4),
           "delta_pct": round((b1 - b0) / b0, 4), "per_stato": per_stato}
    (ROOT / "data" / "livello0").mkdir(exist_ok=True)
    (ROOT / "data" / "livello0" / "prova_hazard_presenze.json").write_text(
        json.dumps(out, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main()
