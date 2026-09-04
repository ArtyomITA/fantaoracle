"""Diagnosi rosa B: compressione del modello valore, quota attacco,
test archetipi (stelle vs equilibrio vs piano B) sui voti reali 2025-26
con le regole della lega utente (modificatore 7->+5, porta inviolata +1)."""
import json, sys, pickle, random
from pathlib import Path
import numpy as np, pandas as pd
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
PROC = ROOT / "data" / "processed"
from fantabot.season.lineup import pick_lineup, score_giornata, goals_from_points
from fantabot.optimizer import optimize_roster, STARTER_SLOTS
QUOTAS = {"P": 3, "D": 8, "C": 8, "A": 6}

def season_points(s):
    v = pd.read_parquet(PROC / f"votes_{s}.parquet"); v = v[v.sv.fillna(0) == 0]
    return v.groupby("master_id")["fantavoto"].agg(["sum", "count", "mean"])

print("=== 1. COMPRESSIONE MODELLO VALORE (predetto vs reale) ===")
for s in ["2024-25", "2025-26"]:
    pred = json.load(open(PROC / f"b_predictions_{s}.json", encoding="utf-8"))
    act = season_points(s)
    reg = pd.read_csv(PROC / "registry.csv"); reg = reg[reg.stagione == s]
    df = pd.DataFrame([{"mid": int(k), "pred": v["value"], "q50": v["q50"]} for k, v in pred.items()])
    df = df.merge(act, left_on="mid", right_index=True, how="inner").merge(
        reg[["master_id", "nome", "ruolo"]], left_on="mid", right_on="master_id")
    df = df[df["count"] >= 5]
    df["dec"] = pd.qcut(df["sum"].rank(method="first"), 10, labels=False)
    g = df.groupby("dec").agg(reale=("sum", "mean"), pred=("pred", "mean"), n=("sum", "size"))
    print(f"\n{s}: decili per punti REALI (10 = migliori)")
    print(g.round(0).to_string())
    top = df.nlargest(25, "sum")
    print(f"  top25 reali: reale medio {top['sum'].mean():.0f}, predetto medio {top['pred'].mean():.0f}, "
          f"rapporto {top['pred'].mean()/top['sum'].mean():.2f}")
    ptop = df.nlargest(25, "pred")
    print(f"  top25 predetti: predetto medio {ptop['pred'].mean():.0f}, reale medio {ptop['sum'].mean():.0f}")
    for r in "PDCA":
        d = df[df.ruolo == r]; t = d.nlargest(8, "sum")
        print(f"  {r}: top8 reali {t['sum'].mean():.0f} vs pred {t['pred'].mean():.0f} | "
              f"fm reale top8 {t['mean'].mean():.2f}")

print("\n=== 2. PIANO B 2026-27: spesa per ruolo e STARTER_SLOTS ===")
with open(ROOT / "data/packs/pack_2026-27.pkl", "rb") as f: pack = pickle.load(f)
pred = pack.b_predictions
prices = {pid: max(1.0, p["q50"]) for pid, p in pred.items()}
values = {pid: p["value"] for pid, p in pred.items()}
def plan(slots, tag):
    import fantabot.optimizer as O
    old = dict(O.STARTER_SLOTS); O.STARTER_SLOTS.update(slots)
    sol = optimize_roster(pack.players, prices, values, QUOTAS, 500)
    O.STARTER_SLOTS.update(old)
    spend = {r: sum(prices[p] for p in sol["roster"][r]) for r in "PDCA"}
    names = {r: [f"{pack.players[p].name}({prices[p]:.0f})" for p in sol["roster"][r]][:4] for r in "PDCA"}
    print(f"  {tag}: spesa P{spend['P']:.0f} D{spend['D']:.0f} C{spend['C']:.0f} A{spend['A']:.0f} "
          f"(A={spend['A']/500:.0%}) valore {sol['value']:.0f}")
    print(f"     A: {names['A']} | D: {names['D'][:3]}")
    return sol
plan({}, "attuale 4-4-2 (1/4/4/2)")
plan({"D": 4, "C": 3, "A": 3}, "4-3-3 (1/4/3/3)")
plan({"D": 3, "C": 4, "A": 3}, "3-4-3 (1/3/4/3)")

print("\n=== 3. ARCHETIPI su voti REALI 2025-26 (regole lega: mod 7->+5, porta inviolata +1) ===")
with open(ROOT / "data/packs/pack_2025-26.pkl", "rb") as f: p25 = pickle.load(f)
raw = pd.read_csv(ROOT / "data/raw/voti/voti_2025-26.csv")
mv = pd.read_csv(PROC / "_match/map_voti.csv"); mv = mv[mv.stagione == "2025-26"]
raw = raw.merge(mv[["squadra", "nome", "master_id"]], on=["squadra", "nome"], how="left")
raw = raw[raw.master_id.notna()]; raw["master_id"] = raw.master_id.astype(int).astype(str)
cs = raw[(raw.ruolo.str.lower() == "p") & (raw.sv == 0) & (raw.gol_subiti.fillna(0) == 0)]
clean = {(r.master_id, int(r.giornata)) for r in cs.itertuples(index=False)}
votes_by_g = []
for g, d in enumerate(p25.votes_by_g, start=1):
    votes_by_g.append({pid: fv + (1.0 if (pid, g) in clean else 0.0) for pid, fv in d.items()})
import fantabot.season.lineup as L
L.MOD_DIFESA_TABLE = [(7.0, 5), (6.75, 4), (6.5, 3), (6.25, 2), (6.0, 1)]
ref = {pid: max(1.0, pl.ref_price * 500) for pid, pl in p25.players.items()}
by_role = {r: sorted([pid for pid, pl in p25.players.items() if pl.role == r], key=lambda x: -ref[x]) for r in "PDCA"}
actual = season_points("2025-26")

def build(spend_share, n_top):
    """spend_share: quota budget per ruolo; n_top: quanti top per ruolo comprare al prezzo
    di mercato, resto a 1 credito (scrubs = i migliori economici per punti reali? NO:
    scelti per ref, senza senno di poi)."""
    roster = {}
    for r in "PDCA":
        budget = 500 * spend_share[r]; chosen = []; spent = 0
        for pid in by_role[r]:
            if len(chosen) >= n_top[r]: break
            if spent + ref[pid] <= budget - (QUOTAS[r] - len(chosen) - 1):
                chosen.append(pid); spent += ref[pid]
        cheap = [pid for pid in by_role[r] if pid not in chosen and ref[pid] <= 2][:QUOTAS[r]-len(chosen)]
        roster[r] = chosen + cheap
    return roster
stelle = build({"P": .06, "D": .10, "C": .20, "A": .64}, {"P": 1, "D": 2, "C": 3, "A": 3})
guida = build({"P": .07, "D": .16, "C": .27, "A": .50}, {"P": 2, "D": 5, "C": 5, "A": 4})
pb = optimize_roster(p25.players, {pid: max(1.0, p["q50"]) for pid, p in p25.b_predictions.items()},
                     {pid: p["value"] for pid, p in p25.b_predictions.items()}, QUOTAS, 500)["roster"]
rosters = {"STELLE": stelle, "GUIDA": guida, "PIANO_B": pb}
for k, ro in rosters.items():
    cost = sum(ref[p] for r in "PDCA" for p in ro[r])
    print(f"  {k}: costo {cost:.0f} | A: {[p25.players[p].name for p in ro['A'][:4]]}")
from fantabot.season.simulate import simulate_season
res = simulate_season(rosters, votes_by_g, n_calendars=200, voti_by_g=p25.voti_by_g, use_mod_difesa=True)
for k in rosters:
    print(f"  {k}: punti {res.total_points[k]:.0f} | win H2H {res.h2h_win_rate()[k]:.0%} | "
          f"media giornata {res.total_points[k]/38:.1f}")
# senza senno di poi sulla disponibilita'? gia' inclusa. Ora: varianza per giornata
for k in rosters:
    sc = np.array(res.giornata_scores[k]); print(f"  {k}: sd giornata {sc.std():.1f}, giornate >=72: {(sc>=72).sum()}, >=78: {(sc>=78).sum()}")
