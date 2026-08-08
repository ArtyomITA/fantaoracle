# -*- coding: utf-8 -*-
"""
Indagine: realismo delle aste simulate (torneo bot) vs aste reali.

- Reali: data/processed/aste_reali_clean.csv
  filtro: componenti==10, crediti_tot 400-600, asta_anomala==0, periodo<=1 (estive, cfr AUDIT.md:
  periodo 0-1 = estive, 2-3 possono includere riparazioni). Sensitivity: tutti i periodi.
- Simulate: hammer nei log data/tournament_mod/2024-25/main_1B_2A_7C/logs/*.jsonl (pct = price/500)
  + secondario data/tournament/2024-25/main_1B_2A_7C/logs/*.jsonl.

Output: stampa a console + reports/indagine/realismo_aste.md
"""
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import ks_2samp

ROOT = Path(r".")
CSV = ROOT / "data" / "processed" / "aste_reali_clean.csv"
SIM_MOD = ROOT / "data" / "tournament_mod" / "2024-25" / "main_1B_2A_7C" / "logs"
SIM_NOMOD = ROOT / "data" / "tournament" / "2024-25" / "main_1B_2A_7C" / "logs"
OUT = ROOT / "reports" / "indagine" / "realismo_aste.md"

BANDS = [(1, 10), (11, 30), (31, 60), (61, 120), (121, 250)]
ROLES = ["P", "D", "C", "A"]


def gini(x):
    x = np.sort(np.asarray(x, dtype=float))
    n = len(x)
    if n == 0 or x.sum() == 0:
        return np.nan
    cum = np.cumsum(x)
    return float((n + 1 - 2 * (cum / cum[-1]).sum()) / n)


def auction_frames_real(df):
    """lista di DataFrame (uno per asta) con colonne pct, ruolo."""
    out = []
    for (_, _), g in df.groupby(["source_file", "auction_id"]):
        out.append(pd.DataFrame({"pct": g["pct_budget"].values, "ruolo": g["ruolo"].values}))
    return out


def auction_frames_sim(logdir):
    out = []
    for f in sorted(logdir.glob("replica_*.jsonl")):
        prices, roles = [], []
        names = []
        with open(f, encoding="utf-8") as fh:
            for line in fh:
                e = json.loads(line)
                if e.get("kind") == "hammer":
                    prices.append(e["price"] / 500.0)
                    roles.append(e["role"])
                    names.append(e["player"])
        out.append(pd.DataFrame({"pct": prices, "ruolo": roles, "player": names}))
    return out


def rank_curve(frames, max_rank=250):
    """matrice aste x rank (pct ordinato desc), media per rank."""
    mat = np.full((len(frames), max_rank), np.nan)
    for i, fr in enumerate(frames):
        v = np.sort(fr["pct"].values)[::-1][:max_rank]
        mat[i, : len(v)] = v
    return np.nanmean(mat, axis=0), mat


def band_values(frames, lo, hi):
    vals = []
    for fr in frames:
        v = np.sort(fr["pct"].values)[::-1]
        vals.extend(v[lo - 1 : min(hi, len(v))])
    return np.array(vals)


def role_shares(frames):
    rows = []
    for fr in frames:
        tot = fr["pct"].sum()
        rows.append({r: fr.loc[fr["ruolo"] == r, "pct"].sum() / tot for r in ROLES})
    return pd.DataFrame(rows)


def summarize(frames, label):
    curve, mat = rank_curve(frames)
    top1 = mat[:, 0]
    g = [gini(fr["pct"].values) for fr in frames]
    top10_share = []
    spent_ratio = []
    for fr in frames:
        v = np.sort(fr["pct"].values)[::-1]
        top10_share.append(v[:10].sum() / v.sum())
        spent_ratio.append(fr["pct"].sum() / 10.0)  # 10 squadre, pct e' quota del budget di UNA squadra
    return {
        "label": label,
        "n_auctions": len(frames),
        "curve": curve,
        "top1_mean": float(np.nanmean(top1)),
        "top1_min": float(np.nanmin(top1)),
        "top1_max": float(np.nanmax(top1)),
        "gini_mean": float(np.nanmean(g)),
        "top10_share_mean": float(np.nanmean(top10_share)),
        "spent_ratio_mean": float(np.nanmean(spent_ratio)),
        "roles": role_shares(frames).mean(),
    }


def main():
    df = pd.read_csv(CSV)
    base = df[(df.componenti == 10) & (df.crediti_tot.between(400, 600)) & (df.asta_anomala == 0)]
    real_est = base[base.periodo <= 1]  # estive (periodo 0-1, cfr AUDIT.md)
    real_all = base

    fr_real = auction_frames_real(real_est)
    fr_real_all = auction_frames_real(real_all)
    fr_mod = auction_frames_sim(SIM_MOD)
    fr_nomod = auction_frames_sim(SIM_NOMOD)

    s_real = summarize(fr_real, "REALI estive (per<=1, 10 part, 400-600cr)")
    s_real_all = summarize(fr_real_all, "REALI tutti i periodi")
    s_mod = summarize(fr_mod, "SIM tournament_mod main 2024-25")
    s_nomod = summarize(fr_nomod, "SIM tournament (no mod) main 2024-25")

    lines = []
    p = lines.append
    p("# Indagine: realismo aste simulate vs reali")
    p("")
    p(f"Reali filtrate: componenti==10, crediti 400-600, asta_anomala==0. "
      f"Estive = periodo<=1 (AUDIT.md: periodo 2-3 possono includere riparazioni invernali).")
    p(f"- Aste reali estive: {s_real['n_auctions']} (tutti i periodi: {s_real_all['n_auctions']})")
    p(f"- Repliche sim mod: {s_mod['n_auctions']}, no-mod: {s_nomod['n_auctions']} "
      f"(budget 500, 10 bot, quote 3P/8D/8C/6A, 250 hammer each)")
    p("")

    p("## 1-2. Curva prezzo-rank (pct budget medio per rank)")
    p("")
    p("| rank | reali estive | reali tutte | sim mod | sim no-mod |")
    p("|---|---|---|---|---|")
    for rk in [1, 2, 3, 5, 10, 15, 20, 30, 40, 60, 80, 120, 160, 200, 250]:
        row = [f"{s['curve'][rk-1]:.4f}" if rk - 1 < len(s["curve"]) and not np.isnan(s["curve"][rk-1]) else "-"
               for s in (s_real, s_real_all, s_mod, s_nomod)]
        p(f"| {rk} | " + " | ".join(row) + " |")
    p("")

    p("### KS test per banda di rank (reali estive vs sim)")
    p("")
    p("| banda | media reali | media sim_mod | KS mod | p mod | media sim_nomod | KS nomod | p nomod |")
    p("|---|---|---|---|---|---|---|---|")
    ks_rows = []
    for lo, hi in BANDS:
        vr = band_values(fr_real, lo, hi)
        vm = band_values(fr_mod, lo, hi)
        vn = band_values(fr_nomod, lo, hi)
        ks_m = ks_2samp(vr, vm)
        ks_n = ks_2samp(vr, vn)
        ks_rows.append((lo, hi, vr.mean(), vm.mean(), ks_m, vn.mean(), ks_n))
        p(f"| {lo}-{hi} | {vr.mean():.4f} | {vm.mean():.4f} | {ks_m.statistic:.3f} | "
          f"{ks_m.pvalue:.2e} | {vn.mean():.4f} | {ks_n.statistic:.3f} | {ks_n.pvalue:.2e} |")
    p("")

    p("## Top price e concentrazione")
    p("")
    p("| metrica | reali estive | reali tutte | sim mod | sim no-mod |")
    p("|---|---|---|---|---|")
    for key, name in [("top1_mean", "top1 pct medio"), ("top1_min", "top1 min"),
                      ("top1_max", "top1 max"), ("gini_mean", "Gini prezzi (media per asta)"),
                      ("top10_share_mean", "quota spesa top-10 giocatori"),
                      ("spent_ratio_mean", "spesa totale / budget totale")]:
        p(f"| {name} | " + " | ".join(f"{s[key]:.4f}" for s in (s_real, s_real_all, s_mod, s_nomod)) + " |")
    p("")

    p("## 3. Spesa per ruolo (% della spesa totale, media per asta)")
    p("")
    p("| ruolo | reali estive | reali tutte | sim mod | sim no-mod |")
    p("|---|---|---|---|---|")
    for r in ROLES:
        p(f"| {r} | " + " | ".join(f"{s['roles'][r]*100:.1f}%" for s in (s_real, s_real_all, s_mod, s_nomod)) + " |")
    p("")

    p("Nota: i log di tournament_mod e tournament sono byte-identici (md5 verificato): il "
      "modificatore incide solo sul punteggio stagionale, non sull'asta. Aste sim uniche = 6.")
    p("")

    # chi compra le fasce di rank nel sim
    import collections
    band_bot = collections.defaultdict(collections.Counter)
    for fdir in [SIM_MOD]:
        for f in sorted(fdir.glob("replica_*.jsonl")):
            hams = [json.loads(l) for l in open(f, encoding="utf-8")]
            hams = [e for e in hams if e.get("kind") == "hammer"]
            hams.sort(key=lambda e: -e["price"])
            for i, e in enumerate(hams, 1):
                band = ("1-3" if i <= 3 else "4-10" if i <= 10 else "11-30" if i <= 30
                        else "31-60" if i <= 60 else "61+")
                band_bot[band][e["bot"]] += 1
    p("## Chi compra le fasce di rank (sim, 6 repliche)")
    p("")
    for b in ["1-3", "4-10", "11-30", "31-60"]:
        p(f"- rank {b}: " + ", ".join(f"{k} {v}" for k, v in band_bot[b].most_common()))
    p("")

    # top players nel sim per contesto
    allsim = pd.concat(fr_mod)
    topsim = allsim.groupby("player")["pct"].agg(["mean", "max", "count"]).sort_values("mean", ascending=False).head(12)
    p("## Top giocatori sim (mod), pct medio sulle 6 repliche")
    p("")
    p(topsim.to_markdown())
    p("")

    # top1 per replica sim
    p("Top1 per replica (mod): " + ", ".join(
        f"{fr.sort_values('pct', ascending=False).iloc[0]['player']} {fr['pct'].max():.3f}" for fr in fr_mod))
    p("")

    p("## 4. Verdetto")
    p("")
    p(f"Complessivamente le aste simulate sono in un range credibile: spesa/budget "
      f"{s_mod['spent_ratio_mean']:.3f} vs {s_real['spent_ratio_mean']:.3f} reale, Gini "
      f"{s_mod['gini_mean']:.3f} vs {s_real['gini_mean']:.3f}, fascia 31-120 quasi sovrapposta. "
      f"Ci si puo' fidare del torneo per confronti relativi tra bot, MA ci sono 3 distorsioni "
      f"sistematiche:")
    p("")
    p(f"1. **Top 1-3 TROPPO CARI** (non troppo economici): top1 sim {s_mod['top1_mean']:.3f} "
      f"(range {s_mod['top1_min']:.2f}-{s_mod['top1_max']:.2f}) vs reale estive "
      f"{s_real['top1_mean']:.3f} (Lautaro reale ~0.35-0.40). Il minimo sim (0.41) supera quasi "
      f"il massimo reale (0.42). Comprati SOLO da bot C (18/18 top-3): stars_scrubs, panic, "
      f"ancorato, tifoso si rilanciano a vicenda.")
    p("2. **Fascia 11-30 troppo economica**: 0.110 sim vs 0.120 reale, KS 0.301 (il piu' alto). "
      "E' l'altra faccia del punto 1: i C bruciano il budget sui top-3 e ai semitop restano meno "
      "crediti. Sistemare il tetto sui top corregge in gran parte anche questa.")
    p("3. **Coda 121-250 troppo economica**: 0.0047 vs 0.0063 (sim collassa a 1 credito, gli "
      "umani pagano 2-4 crediti anche in fondo). Minore, ma KS significativo.")
    p("")
    p("Ruoli: sim sotto-spende in Attacco (42.3% vs 45.2% reale estive) e sovra-spende in "
      "C (+2.3pp) e D (+1pp).")
    p("")
    p("**Manopole bot C da toccare**: (a) cap/haircut sul rilancio dei profili aggressivi "
      "(stars_scrubs, panic, ancorato) sopra ~0.35-0.40 del budget per singolo giocatore — "
      "target: top1 medio ~0.36, max ~0.42; (b) ridistribuire il budget-per-ruolo dei profili C "
      "spostando ~3pp da C/D verso A; (c) opzionale, floor di 2-3 crediti sulle chiamate di coda "
      "per i profili non-tirchio.")
    p("")
    p("Caveat: aste reali estive filtrate = 16 (periodo<=1; 11 del 2021-22), quindi il "
      "confronto a livello di singolo giocatore 2024-25 non e' possibile, solo per fasce di rank. "
      "Con tutti i periodi (n=55, incluse riparazioni) il top1 reale sale a 0.416 e il gap si "
      "riduce, ma le riparazioni non sono il target giusto.")
    p("")

    text = "\n".join(lines)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(text, encoding="utf-8")
    print(text)
    print(f"\nScritto: {OUT}")


if __name__ == "__main__":
    main()
