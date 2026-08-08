"""Fase 2 — costruzione SeasonPack per il torneo (2024-25, 2025-26).

- ref_price (riferimento mercato dei bot C): media pct aste estive reali ->
  wayback/500 -> FVM/1000 -> minimo da quotazione. ref_price_sd dallo spread
  reale tra aste (calibrazione C su dati veri).
- exp_points: Marcel (stesso valore che usa B: nessun senno di poi).
- a_price_list: VORP sui punti Marcel.
- votes_by_g: fantavoti reali per giornata (sv esclusi).
Output: data/packs/pack_{stagione}.pkl + report calibrazione.
"""
from __future__ import annotations

import json
import pickle
import sys
import warnings
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))
PROC = ROOT / "data" / "processed"
PACKS = ROOT / "data" / "packs"
PACKS.mkdir(parents=True, exist_ok=True)

warnings.filterwarnings("ignore")

from f1_make_predictions import marcel_values  # noqa: E402
from fantabot.models import Player  # noqa: E402
from fantabot.modeling import vorp_prices  # noqa: E402
from fantabot.tournament import SeasonPack  # noqa: E402

SEASONS = ["2024-25", "2025-26"]
BUDGET = 500
QUOTAS = {"P": 3, "D": 8, "C": 8, "A": 6}


def build_pack(season: str) -> SeasonPack:
    df = pd.read_parquet(PROC / f"players_{season}.parquet")
    votes = pd.read_parquet(PROC / f"votes_{season}.parquet")
    preds = json.loads((PROC / f"b_predictions_{season}.json").read_text("utf-8"))

    # riferimento mercato: gerarchia di fonti
    mean_est = df["target_mean_pct_all_estiva"].astype(float)
    n_est = df["target_n_obs_all_estiva"].fillna(0).astype(float)
    wb = df["target_wayback_p500_10sq"].astype(float) / BUDGET
    fvm = df["fvm"].astype(float) / 1000.0
    qt_floor = df["qt_i"].fillna(1).astype(float) / 1000.0
    ref = mean_est.where(n_est >= 2)
    ref = ref.fillna(wb).fillna(fvm.where(fvm > 0)).fillna(qt_floor)
    ref = ref.clip(lower=0.002)
    sd = df["target_std_pct_all_estiva"].astype(float).where(n_est >= 3)

    # Correzione bias di selezione: le medie osservate sono condizionate
    # all'acquisto. I top vengono comprati in ogni asta (bias ~0), la coda solo
    # quando qualcuno li apprezza (media condizionata >> valore atteso).
    # Prob. d'acquisto ~ rank nel ruolo (slot totali = quota x 10 squadre),
    # poi normalizzazione globale: la somma dei prezzi attesi DEVE fare ~10
    # budget (250 acquisti assorbono esattamente 10 x 500 crediti).
    raw_sum = float(ref.sum())
    sold_prob = pd.Series(0.0, index=ref.index)
    for role, quota in QUOTAS.items():
        m = df["ruolo"] == role
        slots = quota * 10
        rank = ref[m].rank(ascending=False, method="first")
        prob = ((slots * 2.0 - rank) / slots).clip(0.03, 1.0)
        sold_prob[m] = prob
    ref = ref * sold_prob + 0.002 * (1 - sold_prob)
    # Tilt progressivo: il vero vincolo e' che in ogni asta la somma dei prezzi
    # fa esattamente 10 budget. Le medie cross-lega lo violano (leghe diverse
    # strapagano giocatori diversi: l'eccesso sta in fascia media/bassa, non
    # sui top comprati cari ovunque). Quindi: top K0 intoccabili, shrink
    # lineare nel rank oltre K0, pendenza risolta per somma = 10.
    K0, FLOOR = 25, 0.03
    order = ref.sort_values(ascending=False).index
    rank = pd.Series(np.arange(1, len(ref) + 1), index=order)

    def total(slope: float) -> float:
        f = (1.0 - slope * (rank - K0).clip(lower=0)).clip(FLOOR, 1.0)
        return float((ref.loc[order] * f).sum())

    lo, hi = 0.0, 1.0
    for _ in range(60):
        mid = (lo + hi) / 2
        if total(mid) > 10.0:
            lo = mid
        else:
            hi = mid
    slope = (lo + hi) / 2
    factors = (1.0 - slope * (rank - K0).clip(lower=0)).clip(FLOOR, 1.0)
    ref = (ref.loc[order] * factors).reindex(ref.index).clip(lower=0.002)
    sd = (sd.loc[order] * factors).reindex(sd.index)
    print(f"  calibrazione: somma grezza {raw_sum:.2f} -> tilt slope {slope:.5f} "
          f"-> tot {float(ref.sum()):.2f} (top{K0} intatti)")

    values = marcel_values(season, df)
    players: dict[str, Player] = {}
    for i, row in df.iterrows():
        mid = str(row["master_id"])
        players[mid] = Player(
            player_id=mid, name=str(row["nome"]), role=str(row["ruolo"]),
            team=str(row["squadra"]), ref_price=float(ref.iloc[i]),
            ref_price_sd=float(sd.iloc[i]) if pd.notna(sd.iloc[i]) else 0.0,
            exp_points=float(values.iloc[i]),
        )

    base = df[["master_id", "ruolo"]].copy()
    base["master_id"] = base["master_id"].astype(str)
    base["exp_points"] = values.values
    vp = vorp_prices(base, QUOTAS, 10, BUDGET)
    a_list = dict(zip(vp["master_id"].astype(str), vp["prezzo_equo"].astype(float)))

    votes = votes[votes["sv"].fillna(0) == 0] if "sv" in votes.columns else votes
    votes = votes.copy()
    votes["master_id"] = votes["master_id"].astype(str)
    votes_by_g, voti_by_g = [], []
    for g in range(1, 39):
        sub = votes[votes["giornata"] == g]
        votes_by_g.append(dict(zip(sub["master_id"], sub["fantavoto"].astype(float))))
        pure = sub[sub["voto"].notna()] if "voto" in sub.columns else sub.iloc[0:0]
        voti_by_g.append(dict(zip(pure["master_id"], pure["voto"].astype(float))))

    pack = SeasonPack(season=season, players=players, votes_by_g=votes_by_g,
                      quotas=QUOTAS, budget=BUDGET,
                      b_predictions={str(k): v for k, v in preds.items()},
                      a_price_list=a_list,
                      voti_by_g=voti_by_g,
                      use_mod_difesa=True)
    # sanity
    tot_ref = sum(p.ref_price for p in players.values())
    n_cal = sum(1 for p in players.values() if p.ref_price_sd > 0)
    top = sorted(players.values(), key=lambda p: -p.ref_price)[:5]
    print(f"{season}: {len(players)} giocatori | somma ref {tot_ref:.2f} budget "
          f"(atteso ~10) | sd reale su {n_cal} | voti g1-38: "
          f"{sum(len(v) for v in votes_by_g)} righe")
    for p in top:
        print(f"   ref top: {p.name:20s} {p.role} {p.ref_price*BUDGET:.0f}cr "
              f"(sd {p.ref_price_sd*BUDGET:.0f})")
    return pack


if __name__ == "__main__":
    for s in SEASONS:
        pack = build_pack(s)
        with open(PACKS / f"pack_{s}.pkl", "wb") as f:
            pickle.dump(pack, f)
    print("Pack salvati in data/packs/")
