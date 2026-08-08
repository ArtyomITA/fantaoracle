# -*- coding: utf-8 -*-
"""Indagine: da dove viene il vantaggio di B, e dove B perde.
Usa: rose ricostruite (ind_rerun_auctions), replicas.jsonl, pack (votes_by_g,
b_predictions, ref_price).
Output: stampa tutte le tabelle + salva CSV intermedi in data/processed/indagine.
"""
import json
import pickle
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, r"src")

BASE = Path(r".")
IND = BASE / "data" / "processed" / "indagine"
SEASONS = ["2024-25", "2025-26"]
BUDGET = 500

pd.set_option("display.width", 200)
pd.set_option("display.max_columns", 40)


def load_pack(season):
    with open(BASE / "data" / "tournament_mod" / season / "main_1B_2A_7C" / "_pack.pkl", "rb") as f:
        return pickle.load(f)


def player_frame(pack):
    """DataFrame per giocatore: nome, ruolo, team, ref_credits, pred(q10/q50/q90/value), pts reali."""
    real = {}
    for g in pack.votes_by_g:
        for pid, fv in g.items():
            real[pid] = real.get(pid, 0.0) + fv
    presenze = {}
    for g in pack.votes_by_g:
        for pid in g:
            presenze[pid] = presenze.get(pid, 0) + 1
    rows = []
    for pid, pl in pack.players.items():
        pr = (pack.b_predictions or {}).get(pid, {})
        rows.append({
            "player_id": pid, "name": pl.name, "role": pl.role, "team": pl.team,
            "ref_credits": pl.ref_price * BUDGET,
            "exp_points": pl.exp_points,
            "q10": pr.get("q10", np.nan), "q50": pr.get("q50", np.nan),
            "q90": pr.get("q90", np.nan), "value": pr.get("value", np.nan),
            "real_pts": real.get(pid, 0.0), "presenze": presenze.get(pid, 0),
        })
    return pd.DataFrame(rows).set_index("player_id")


def load_replicas(season):
    rows = []
    with open(BASE / "data" / "tournament_mod" / season / "main_1B_2A_7C" / "replicas.jsonl",
              encoding="utf-8") as f:
        for line in f:
            r = json.loads(line)
            for bot, v in r["teams"].items():
                rows.append({"seed": r["seed"], "bot": bot, **v})
    return pd.DataFrame(rows)


def main():
    out_lines = []

    def p(*a):
        s = " ".join(str(x) for x in a)
        print(s, flush=True)
        out_lines.append(s)

    packs = {s: load_pack(s) for s in SEASONS}
    pf = {s: player_frame(packs[s]) for s in SEASONS}
    rosters = {s: pd.read_csv(IND / f"rosters_{s}.csv",
                              dtype={"player_id": str}) for s in SEASONS}
    reps = {s: load_replicas(s) for s in SEASONS}

    # ================= Q1: curva punti-per-credito + decomposizione =================
    p("\n" + "=" * 90)
    p("Q1. PUNTI REALI DELLA ROSA vs PREZZO PAGATO (150 repliche, per bot)")
    p("=" * 90)
    q1_tables = {}
    for s in SEASONS:
        df = rosters[s].join(pf[s][["real_pts", "ref_credits"]], on="player_id")
        g = df.groupby(["seed", "bot"]).agg(
            roster_pts=("real_pts", "sum"),
            spent=("price", "sum"),
            ref_sum=("ref_credits", "sum"),
            n=("price", "size"),
        ).reset_index()
        agg = g.groupby("bot").agg(
            pts=("roster_pts", "mean"), spent=("spent", "mean"),
            ref_sum=("ref_sum", "mean")).round(1)
        agg["pts_per_credito"] = (agg["pts"] / agg["spent"]).round(3)
        # decomposizione moltiplicativa: pts/spent = (pts/ref_sum) * (ref_sum/spent)
        agg["value_pick (pts/ref)"] = (agg["pts"] / agg["ref_sum"]).round(3)
        agg["discipline (ref/spent)"] = (agg["ref_sum"] / agg["spent"]).round(3)
        agg = agg.sort_values("pts_per_credito", ascending=False)
        q1_tables[s] = agg
        p(f"\n--- {s} (media su 150 repliche; pts = somma fantavoti reali della rosa; "
          f"ref_sum = valore di mercato della rosa in crediti) ---")
        p(agg.to_string())
        # vantaggio B decomposto vs media degli altri (additivo, log)
        b = agg.loc["B"]
        others = agg.drop("B")
        m = others.mean()
        tot_log = np.log(b["pts_per_credito"]) - np.log(m["pts_per_credito"])
        vp_log = np.log(b["value_pick (pts/ref)"]) - np.log(m["value_pick (pts/ref)"])
        di_log = np.log(b["discipline (ref/spent)"]) - np.log(m["discipline (ref/spent)"])
        p(f"[{s}] vantaggio B in pts/credito vs media altri: "
          f"{(b['pts_per_credito']/m['pts_per_credito']-1)*100:+.1f}% -> "
          f"quota value-pick {vp_log/tot_log*100:.0f}%, "
          f"quota price-discipline {di_log/tot_log*100:.0f}%")

    # ================= Q2: i 10 acquisti piu' frequenti di B =================
    p("\n" + "=" * 90)
    p("Q2. TOP-10 GIOCATORI PIU' COMPRATI DA B (150 repliche)")
    p("=" * 90)
    for s in SEASONS:
        rb = rosters[s][rosters[s]["bot"] == "B"]
        freq = rb.groupby("player_id").agg(
            n=("seed", "nunique"), prezzo_medio=("price", "mean")).reset_index()
        freq = freq.join(pf[s], on="player_id").sort_values(
            ["n", "prezzo_medio"], ascending=[False, False])
        top = freq.head(10).copy()
        top["freq_%"] = (top["n"] / 150 * 100).round(0).astype(int)
        top["prezzo_medio"] = top["prezzo_medio"].round(1)
        top["ref_credits"] = top["ref_credits"].round(1)
        cols = ["name", "role", "team", "freq_%", "prezzo_medio", "ref_credits",
                "q50", "value", "real_pts", "presenze"]
        p(f"\n--- {s} (value = punti predetti dal CatBoost di B; q50 = prezzo predetto) ---")
        p(top[cols].to_string(index=False))
        top.to_csv(IND / f"q2_top10_B_{s}.csv", index=False)
        # leakage check: rank del value predetto vs rank pts reali per i top10
        merged = pf[s][pf[s]["presenze"] > 0]
        merged = merged.dropna(subset=["value"])
        merged = merged.assign(
            rk_val=merged["value"].rank(ascending=False),
            rk_real=merged["real_pts"].rank(ascending=False),
            rk_ref=merged["ref_credits"].rank(ascending=False))
        chk = merged.loc[[i for i in top.dropna(subset=["value"])["player_id"]
                          if i in merged.index]]
        p(f"[{s}] leakage-check top10: rank medio per value {chk['rk_val'].mean():.0f}, "
          f"per pts reali {chk['rk_real'].mean():.0f}, per ref_price {chk['rk_ref'].mean():.0f} "
          f"(su {len(merged)} giocatori con voti)")

    # ================= Q3: repliche perse da B (2025-26) =================
    p("\n" + "=" * 90)
    p("Q3. REPLICHE PERSE DA B - 2025-26 main")
    p("=" * 90)
    for s in SEASONS:
        r = reps[s]
        # vincitore replica = bot con h2h_win_rate massimo
        win = r.loc[r.groupby("seed")["h2h_win_rate"].idxmax()][["seed", "bot"]]
        win = win.rename(columns={"bot": "winner"})
        r = r.merge(win, on="seed")
        b_won_seeds = set(win[win["winner"] == "B"]["seed"])
        p(f"\n[{s}] B vince (argmax win_rate) {len(b_won_seeds)}/150 repliche "
          f"({len(b_won_seeds)/150*100:.0f}%)")
        if s != "2025-26":
            continue
        lost = r[~r["seed"].isin(b_won_seeds)]
        p("chi vince nelle repliche perse da B:")
        p(lost[lost["bot"] == lost["winner"]].groupby("bot")["seed"].count()
          .sort_values(ascending=False).to_string())

        # confronto B vinte vs perse (livello replica)
        df = rosters[s].join(pf[s][["real_pts", "ref_credits", "q50"]], on="player_id")
        gb = df[df["bot"] == "B"].groupby("seed").agg(
            roster_pts=("real_pts", "sum"),
            q50_sum=("q50", "sum"))
        bb = r[r["bot"] == "B"].set_index("seed").join(gb)
        bb["won"] = bb.index.isin(b_won_seeds)
        cmp_ = bb.groupby("won")[["total_points", "roster_pts", "spent", "leftover",
                                  "q50_sum", "h2h_win_rate"]].mean().round(1)
        p("\nB nelle repliche vinte vs perse (medie):")
        p(cmp_.to_string())
        # inflazione pagata da B: prezzo pagato / q50 dei suoi acquisti (>3 crediti)
        dfb = df[(df["bot"] == "B") & (df["q50"] > 3)].copy()
        dfb["won"] = dfb["seed"].isin(b_won_seeds)
        infl = dfb.groupby("won").apply(
            lambda x: (x["price"].sum() / x["q50"].sum()), include_groups=False).round(3)
        p("\nB paga/q50 (acquisti con q50>3) vinte vs perse: " + infl.to_string())

        # punti del vincitore vs punti B nelle perse
        wrow = r[r["bot"] == r["winner"]][["seed", "total_points", "h2h_win_rate"]]
        wrow = wrow.rename(columns={"total_points": "pts_winner",
                                    "h2h_win_rate": "wr_winner"})
        bl = bb[~bb["won"]].join(wrow.set_index("seed"))
        p(f"\nrepliche perse: pts B {bl['total_points'].mean():.0f} vs pts vincitore "
          f"{bl['pts_winner'].mean():.0f} (delta {(bl['pts_winner']-bl['total_points']).mean():+.0f}); "
          f"B ha comunque piu' punti del vincitore nel "
          f"{(bl['total_points'] > bl['pts_winner']).mean()*100:.0f}% delle perse; "
          f"win_rate medio vincitore {bl['wr_winner'].mean():.2f}")

        # nelle perse: giocatori chiave del vincitore che B non ha
        rw = rosters[s].merge(win, on="seed")
        rw_l = rw[(rw["bot"] == rw["winner"]) & (~rw["seed"].isin(b_won_seeds))]
        rb_l = rosters[s][(rosters[s]["bot"] == "B")
                          & (~rosters[s]["seed"].isin(b_won_seeds))]
        b_has = rb_l.groupby("seed")["player_id"].apply(set).to_dict()
        rw_l = rw_l[[pid not in b_has.get(seed, set())
                     for seed, pid in zip(rw_l["seed"], rw_l["player_id"])]]
        keyp = rw_l.groupby("player_id").agg(
            n=("seed", "nunique"), prezzo=("price", "mean")).reset_index()
        keyp = keyp.join(pf[s][["name", "role", "real_pts", "ref_credits", "q50", "value"]],
                         on="player_id")
        keyp["pts_x_n"] = keyp["n"] * keyp["real_pts"]
        keyp = keyp.sort_values("pts_x_n", ascending=False).head(15)
        keyp[["prezzo", "real_pts", "ref_credits"]] = keyp[
            ["prezzo", "real_pts", "ref_credits"]].round(1)
        p(f"\ngiocatori del VINCITORE (non in mano a B) nelle {150-len(b_won_seeds)} perse, "
          "per n x pts reali:")
        p(keyp[["name", "role", "n", "prezzo", "q50", "value", "real_pts"]]
          .to_string(index=False))

        # i top-10 target di B: li possiede piu' spesso nelle vinte che nelle perse?
        rb_all = rosters[s][rosters[s]["bot"] == "B"]
        top10 = rb_all.groupby("player_id")["seed"].nunique().nlargest(10).index
        own = rb_all[rb_all["player_id"].isin(top10)].copy()
        own["won"] = own["seed"].isin(b_won_seeds)
        tt = own.groupby(["player_id", "won"]).agg(
            n=("seed", "nunique"), prezzo=("price", "mean")).reset_index()
        tt = tt.join(pf[s][["name", "real_pts"]], on="player_id")
        n_won, n_lost = len(b_won_seeds), 150 - len(b_won_seeds)
        tt["quota"] = np.where(tt["won"], tt["n"] / n_won, tt["n"] / n_lost)
        piv = tt.pivot_table(index="name", columns="won",
                             values=["quota", "prezzo"]).round(2)
        p("\ntop-10 target di B: quota possesso e prezzo medio, vinte (True) vs perse (False):")
        p(piv.to_string())

    # ================= Q4: rho modello-mercato e punti->win =================
    p("\n" + "=" * 90)
    p("Q4. RHO MODELLO vs MERCATO; PUNTI ROSA -> WIN RATE")
    p("=" * 90)
    from scipy.stats import spearmanr, pearsonr
    for s in SEASONS:
        m = pf[s].dropna(subset=["value"])
        m = m[m["ref_credits"] >= 1]  # pool d'asta rilevante
        rho_mod = spearmanr(m["value"], m["real_pts"])[0]
        rho_mkt = spearmanr(m["ref_credits"], m["real_pts"])[0]
        # anche solo sui giocatori >= 5 crediti (dove si gioca l'asta)
        m5 = m[m["ref_credits"] >= 5]
        rho_mod5 = spearmanr(m5["value"], m5["real_pts"])[0]
        rho_mkt5 = spearmanr(m5["ref_credits"], m5["real_pts"])[0]
        p(f"\n[{s}] spearman(value_B, pts reali) = {rho_mod:.2f} | "
          f"spearman(ref_price, pts reali) = {rho_mkt:.2f}   (n={len(m)})")
        p(f"[{s}] solo ref>=5cr: modello {rho_mod5:.2f} vs mercato {rho_mkt5:.2f} (n={len(m5)})")

    # correlazione punti rosa -> win rate (pooled per bot-replica) e margine B
    pooled = []
    for s in SEASONS:
        r = reps[s]
        rho_p = pearsonr(r["total_points"], r["h2h_win_rate"])[0]
        rho_s = spearmanr(r["total_points"], r["h2h_win_rate"])[0]
        # a livello bot (10 punti)
        botlev = r.groupby("bot")[["total_points", "h2h_win_rate"]].mean()
        rho_bot = pearsonr(botlev["total_points"], botlev["h2h_win_rate"])[0]
        # margine B vs miglior altro per replica
        piv = r.pivot(index="seed", columns="bot", values="total_points")
        margin = piv["B"] - piv.drop(columns="B").max(axis=1)
        wr = r[r["bot"] == "B"].set_index("seed")["h2h_win_rate"]
        pooled.append(pd.DataFrame({"season": s, "margin": margin, "wr": wr}))
        # quanto spesso il team con piu' punti vince l'h2h (argmax)
        wmax = r.loc[r.groupby("seed")["h2h_win_rate"].idxmax()].set_index("seed")["bot"]
        pmax = piv.idxmax(axis=1)
        p(f"\n[{s}] corr(total_points, h2h_win_rate): pearson {rho_p:.2f} "
          f"(spearman {rho_s:.2f}) su 1500 bot-repliche; a livello bot (n=10) {rho_bot:.2f}")
        p(f"[{s}] il team con piu' punti-rosa vince l'h2h nel {(wmax==pmax).mean()*100:.0f}% "
          f"delle repliche")
        p(f"[{s}] margine B vs miglior rivale: media {margin.mean():+.0f} pts "
          f"(mediana {margin.median():+.0f}), quota repliche con margine>0: "
          f"{(margin>0).mean()*100:.0f}%; win_rate medio B {wr.mean():.3f}")

    allm = pd.concat(pooled)
    # curva margine -> win rate (bin comuni alle due stagioni)
    bins = [-400, -150, -100, -50, -25, 0, 25, 50, 100, 150, 400]
    allm["bin"] = pd.cut(allm["margin"], bins)
    curve = allm.groupby("bin", observed=True).agg(
        wr=("wr", "mean"), n=("wr", "size")).round(3)
    p("\ncurva margine punti (B - miglior rivale) -> win rate h2h (2 stagioni pooled):")
    p(curve.to_string())
    # con la curva 2025-26 stimata sui margini 2024-25 e viceversa
    for s_fit, s_app in [("2025-26", "2024-25"), ("2024-25", "2025-26")]:
        fit = allm[allm["season"] == s_fit]
        app = allm[allm["season"] == s_app]
        cm = fit.groupby("bin", observed=True)["wr"].mean()
        pred = app["bin"].map(cm).astype(float)
        p(f"win rate {s_app} previsto applicando la curva margine->win di {s_fit}: "
          f"{pred.mean():.3f} (reale {app['wr'].mean():.3f})")

    # ============ EXTRA: margine RAW vs margine LINEUP + possesso top-value ============
    p("\n" + "=" * 90)
    p("EXTRA. MARGINE RAW (somma fantavoti rosa) vs MARGINE LINEUP (total_points) - 150 repliche")
    p("=" * 90)
    for s in SEASONS:
        df = rosters[s].join(pf[s][["real_pts"]], on="player_id")
        raw = df.groupby(["seed", "bot"])["real_pts"].sum().unstack()
        lin = reps[s].pivot(index="seed", columns="bot", values="total_points")
        mr = raw["B"] - raw.drop(columns="B").max(axis=1)
        ml = lin["B"] - lin.drop(columns="B").max(axis=1)
        p(f"[{s}] margine B: RAW {mr.mean():+.0f} (>0 nel {(mr>0).mean()*100:.0f}%) | "
          f"LINEUP {ml.mean():+.0f} (>0 nel {(ml>0).mean()*100:.0f}%)")
        p(f"[{s}] B raw {raw['B'].mean():.0f} vs miglior rivale raw "
          f"{raw.drop(columns='B').max(axis=1).mean():.0f}; "
          f"raw medio per bot: " +
          ", ".join(f"{b}={raw[b].mean():.0f}" for b in raw.columns))
        # conversione raw -> lineup per bot
        conv = (lin.mean() / raw.mean()).sort_values(ascending=False).round(3)
        p(f"[{s}] conversione lineup/raw per bot: " + conv.to_string().replace("\n", " | "))
        # quota dei top-25 per value posseduta da B
        top25 = set(pf[s].nlargest(25, "value").index)
        rb = rosters[s][rosters[s]["bot"] == "B"]
        share = rb[rb["player_id"].isin(top25)].groupby("seed")["player_id"].nunique()
        share = share.reindex(raw.index, fill_value=0)
        p(f"[{s}] top-25 per value in mano a B: media {share.mean():.1f}/25 per replica")
        # prezzo pagato da B vs q50 e vs ref (tutti gli acquisti B, q50>3)
        dfb = rosters[s][rosters[s]["bot"] == "B"].join(
            pf[s][["q50", "ref_credits", "real_pts"]], on="player_id")
        d3 = dfb[dfb["q50"] > 3]
        p(f"[{s}] B: paga/q50 = {d3['price'].sum()/d3['q50'].sum():.3f}, "
          f"paga/ref = {d3['price'].sum()/d3['ref_credits'].sum():.3f} (acquisti q50>3)")
        # e per gli ALTRI bot: paga/ref complessivo
        dfo = rosters[s][rosters[s]["bot"] != "B"].join(
            pf[s][["ref_credits", "q50"]], on="player_id")
        o3 = dfo[dfo["ref_credits"] > 3]
        p(f"[{s}] rivali: paga/ref = {o3['price'].sum()/o3['ref_credits'].sum():.3f} "
          f"(acquisti ref>3)")

    (IND / "analisi_output.txt").write_text("\n".join(out_lines), encoding="utf-8")
    p(f"\noutput salvato in {IND / 'analisi_output.txt'}")


if __name__ == "__main__":
    main()
