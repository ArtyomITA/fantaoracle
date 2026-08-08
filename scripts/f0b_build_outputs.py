# -*- coding: utf-8 -*-
"""Fase 0b — output finali in data/processed:
  aste_reali_clean.csv, price_targets.csv,
  players_{stagione}.parquet (2021-22, 2023-24, 2024-25, 2025-26),
  votes_{stagione}.parquet (2021-22 ... 2025-26).

Anti-leakage: nei players_* lo storico viene SOLO da stagioni precedenti;
le colonne target_ sono separate e sono l'unica informazione della stagione stessa
(oltre a Qt.I/FVM/quotazioni di inizio settembre, note al giorno dell'asta).
"""
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent))
from f0b_lib import (RAW, PROC, MATCH_DIR, PLAYERS_SEASONS, VOTI_SEASONS,  # noqa: E402
                     norm, pick_best_per_master)

PREF_KEEP = "extra/1J4tILPqyErS5Ccpr0Dy-595D2PgubYxlPaqfX8-pjYw.xlsx"

# soglie fix round 1
NEAR_DUP_OVERLAP = 0.70   # frazione righe (giocatore, prezzo) identiche -> stessa asta
ANOMALA_RATIO = 1.10      # spesa/budget teorico oltre cui l'asta e' inaffidabile
ETA_MIN, ETA_MAX = 15.0, 45.0

SIGLA_TO_UNDERSTAT = {
    "ATA": "Atalanta", "BEN": "Benevento", "BOL": "Bologna", "BRE": "Brescia",
    "CAG": "Cagliari", "COM": "Como", "CRE": "Cremonese", "CRO": "Crotone",
    "EMP": "Empoli", "FIO": "Fiorentina", "FRO": "Frosinone", "GEN": "Genoa",
    "INT": "Inter", "JUV": "Juventus", "LAZ": "Lazio", "LEC": "Lecce",
    "MIL": "AC Milan", "MON": "Monza", "NAP": "Napoli", "PAR": "Parma Calcio 1913",
    "PIS": "Pisa", "ROM": "Roma", "SAL": "Salernitana", "SAM": "Sampdoria",
    "SAS": "Sassuolo", "SPA": "SPAL 2013", "SPE": "Spezia", "TOR": "Torino",
    "UDI": "Udinese", "VEN": "Venezia", "VER": "Verona",
}


def prev_seasons(s, k=3):
    y = int(s[:4])
    return [f"{y-i}-{str(y-i+1)[-2:]}" for i in range(1, k + 1)]


# ------------------------------------------------------------------ aste
def near_dup_auctions(aste):
    """Fix round 1 (audit Difetto 3): coppie di aste della stessa stagione e stessa
    configurazione (componenti, crediti) con overlap righe (giocatore, prezzo) >
    NEAR_DUP_OVERLAP = stessa asta ricopiata. Tiene la copia piu' completa (a pari
    righe: la copia PREF_KEEP, poi ordine file). Ritorna il set (source_file, auction_id)
    da eliminare."""
    infos = []
    for (f, a), d in aste.groupby(["source_file", "auction_id"]):
        infos.append(dict(f=f, a=a, key=(d.stagione.iloc[0], int(d.componenti.iloc[0]),
                                         int(d.crediti_tot.iloc[0])),
                          n=len(d), rows=set(zip(d.player_raw.map(norm), d.prezzo))))
    drop = set()
    bykey = {}
    for it in infos:
        bykey.setdefault(it["key"], []).append(it)
    for key, group in bykey.items():
        group.sort(key=lambda it: (-it["n"], it["f"] != PREF_KEEP, it["f"], it["a"]))
        kept = []
        for it in group:
            dup_of = next((k for k in kept
                           if len(it["rows"] & k["rows"]) /
                           max(1, min(len(it["rows"]), len(k["rows"]))) > NEAR_DUP_OVERLAP),
                          None)
            if dup_of is not None:
                drop.add((it["f"], it["a"]))
                print(f"  near-dup: {it['f']}#{it['a']} ({it['n']}r) ~ "
                      f"{dup_of['f']}#{dup_of['a']} ({dup_of['n']}r) "
                      f"[{key[0]} {key[1]}x{key[2]}] -> eliminata la prima")
            else:
                kept.append(it)
    return drop


def build_aste(reg):
    aste = pd.read_csv(RAW / "gruppoesperti" / "aste_reali_tidy.csv")
    from f0b_match import GE_FILE_SEASON
    aste["stagione"] = aste["source_file"].map(GE_FILE_SEASON)

    # 1) dedup esatto (fingerprint da build_stats.json)
    stats = json.load(open(RAW / "gruppoesperti" / "build_stats.json", encoding="utf-8"))
    drop = set()
    for group in stats["dups_cross"]:
        entries = [(f, a) for f, a in group]
        keep = next((e for e in entries if e[0] == PREF_KEEP), entries[0])
        for e in entries:
            if e != keep:
                drop.add(tuple(e))
    n_exact = len(drop)
    key = list(zip(aste.source_file, aste.auction_id))
    aste = aste[[k not in drop for k in key]].copy()

    # 2) dedup a soglia (fix round 1, audit Difetto 3)
    ndrop = near_dup_auctions(aste)
    key = list(zip(aste.source_file, aste.auction_id))
    aste = aste[[k not in ndrop for k in key]].copy()

    # 3) spesa/budget per asta (calcolata PRIMA del collasso: le righe doppie sono
    #    l'evidenza della trascrizione corrotta) -> flag asta_anomala (Difetto 5)
    sp = aste.groupby(["source_file", "auction_id"])["prezzo"].sum()
    teor = aste.groupby(["source_file", "auction_id"]).agg(
        comp=("componenti", "first"), cred=("crediti_tot", "first"))
    ratio = (sp / (teor.comp * teor.cred)).rename("spesa_ratio")
    aste = aste.merge(ratio.reset_index(), on=["source_file", "auction_id"], how="left")
    aste["asta_anomala"] = (aste.spesa_ratio > ANOMALA_RATIO).astype(int)

    # 4) match master + collasso acquisti doppi intra-asta (Difetto 5): una riga per
    #    (asta, master), tenuto il PRIMO prezzo, acquisti_doppi = n righe originali.
    mg = pd.read_csv(MATCH_DIR / "map_ge.csv")
    aste = aste.merge(mg[["stagione", "ruolo", "player_raw", "master_id"]],
                      on=["stagione", "ruolo", "player_raw"], how="left")
    grp = ["source_file", "auction_id", "master_id"]
    m = aste.master_id.notna()
    aste["acquisti_doppi"] = 1
    aste.loc[m, "acquisti_doppi"] = aste[m].groupby(grp)["prezzo"].transform("size").astype(int)
    dup_rows = int((aste.loc[m].duplicated(grp, keep="first")).sum())
    aste = aste[~(m & aste.duplicated(grp, keep="first"))].copy()

    name_map = dict(zip(zip(reg.master_id, reg.stagione), reg.nome))
    aste["nome"] = [name_map.get((mm, s)) if pd.notna(mm) else None
                    for mm, s in zip(aste.master_id, aste.stagione)]
    cols = ["source_file", "auction_id", "stagione", "componenti", "crediti_tot",
            "modificatore", "periodo", "ruolo", "player_raw", "master_id", "nome",
            "prezzo", "pct_budget", "acquisti_doppi", "spesa_ratio", "asta_anomala"]
    aste = aste[cols]
    aste.to_csv(PROC / "aste_reali_clean.csv", index=False, encoding="utf-8")
    n_aste = aste.groupby(["source_file", "auction_id"]).ngroups
    n_anom = aste[aste.asta_anomala == 1].groupby(["source_file", "auction_id"]).ngroups
    matched = aste.master_id.notna().mean()
    print(f"aste_reali_clean: {len(aste)} righe, {n_aste} aste uniche "
          f"(dedup {n_exact} esatte + {len(ndrop)} near-dup), "
          f"{dup_rows} righe doppie intra-asta collassate, "
          f"{n_anom} aste anomale (spesa>{ANOMALA_RATIO:.2f}x), "
          f"master_id su {matched*100:.1f}% righe")
    return aste


def build_price_targets(aste, reg):
    """Fix round 1 (audit Difetto 2): target separati per periodo d'asta.

    Semantica `periodo` (verificata sui trasferimenti reali, cfr. FASE0B_REPORT sez. 8):
    0 = asta estiva pre-campionato, 1 = a ridosso della 1a giornata, 2-3 = asta tenuta
    DOPO l'avvio del campionato (settembre/autunno; incorporano informazione post-1/9,
    es. Osimhen 2024-25 a 1-3 crediti dopo la cessione del 6/9). NON sono riparazioni
    di gennaio: i ceduti a gennaio (Kvaratskhelia 2024-25, Vlahovic/Kulusevski 2021-22,
    Dragusin 2023-24) compaiono a prezzo pieno anche nelle aste periodo 2-3.

    Gerarchia target (il modello scegliera'/blendera' in Fase 1):
      (a) *_10x500_estiva : periodo<=1, 10 squadre, 400-600 crediti (campione piccolo!)
      (b) *_all_estiva    : periodo<=1, tutte le configurazioni, pct_budget normalizzato
      (c) *_tardiva       : periodo>=2, tutte le configurazioni (contaminati post-avvio)
      (d) wayback_p500_10sq : prezzo stimato fantacalcio-online (0 -> NaN)
    Escluse le aste con asta_anomala=1 (spesa > 1.10x budget teorico)."""
    a = aste[aste.master_id.notna() & (aste.asta_anomala == 0)].copy()
    a["master_id"] = a.master_id.astype(int)
    est = a[a.periodo <= 1]
    tard = a[a.periodo >= 2]
    e10 = est[(est.componenti == 10) & (est.crediti_tot.between(400, 600))]

    def agg(df, suffix):
        return df.groupby(["master_id", "stagione"])["pct_budget"].agg(
            **{f"n_obs_{suffix}": "count", f"mean_pct_{suffix}": "mean",
               f"std_pct_{suffix}": "std"})

    pt = (agg(est, "all_estiva")
          .join(agg(e10, "10x500_estiva"), how="outer")
          .join(agg(tard, "tardiva"), how="outer")
          .reset_index())

    # wayback p500_10sq: primo valore non nullo in ordine di priorita' file; 0 -> NaN
    mw = pd.read_csv(MATCH_DIR / "map_wayback.csv")
    mw = mw[mw.master_id.notna() & mw.p500_10sq.notna() & (mw.p500_10sq > 0)].copy()
    mw["master_id"] = mw.master_id.astype(int)
    mw = (mw.sort_values("prio").drop_duplicates(["stagione", "master_id"], keep="first")
            [["master_id", "stagione", "p500_10sq"]]
            .rename(columns={"p500_10sq": "wayback_p500_10sq"}))
    pt = pt.merge(mw, on=["master_id", "stagione"], how="outer")
    ncols = ["n_obs_10x500_estiva", "n_obs_all_estiva", "n_obs_tardiva"]
    for c in ncols:
        pt[c] = pt[c].fillna(0).astype(int)
    pt = pt.sort_values(["stagione", "master_id"])
    cols = (["master_id", "stagione"]
            + [f"{p}_{s}" for s in ["10x500_estiva", "all_estiva", "tardiva"]
               for p in ["n_obs", "mean_pct", "std_pct"]]
            + ["wayback_p500_10sq"])
    pt = pt[cols]
    pt.to_csv(PROC / "price_targets.csv", index=False, encoding="utf-8")
    print(f"price_targets: {len(pt)} righe (master, stagione)")
    n_aste_est10 = e10.groupby(["source_file", "auction_id"]).ngroups
    print(f"  aste estive 10x(400-600) totali: {n_aste_est10}")
    print(pt.groupby("stagione").agg(
        n=("master_id", "count"),
        est_10x500=("n_obs_10x500_estiva", lambda x: (x > 0).sum()),
        est_all3=("n_obs_all_estiva", lambda x: (x >= 3).sum()),
        tardive3=("n_obs_tardiva", lambda x: (x >= 3).sum()),
        wayback=("wayback_p500_10sq", lambda x: x.notna().sum())).to_string())
    # rilettura dal CSV: i target nei players_* devono essere IDENTICI al file
    return pd.read_csv(PROC / "price_targets.csv")


# ------------------------------------------------------------------ votes
def build_votes(reg):
    mv = pd.read_csv(MATCH_DIR / "map_voti.csv")
    all_hist = {}
    for s in VOTI_SEASONS:
        v = pd.read_csv(RAW / "voti" / f"voti_{s}.csv")
        v = v.merge(mv[mv.stagione == s][["squadra", "nome", "master_id"]],
                    on=["squadra", "nome"], how="left")
        matched = v[v.master_id.notna()].copy()
        matched["master_id"] = matched.master_id.astype(int)
        out = matched[["master_id", "giornata", "voto", "fantavoto", "sv"]].copy()
        out["voto"] = pd.to_numeric(out.voto, errors="coerce")
        out["fantavoto"] = pd.to_numeric(out.fantavoto, errors="coerce")
        out["sv"] = out.sv.astype(int)
        # dedup difensivo (stesso master due volte nella stessa giornata: non atteso)
        out = out.drop_duplicates(["master_id", "giornata"], keep="first")
        out.to_parquet(PROC / f"votes_{s}.parquet", index=False)
        pct = len(matched) / len(v) * 100
        print(f"votes_{s}.parquet: {len(out)} righe ({pct:.1f}% delle righe voti matchate)")
        all_hist[s] = matched  # righe voti complete matchate, per lo storico players
    return all_hist


# ------------------------------------------------------------------ players
def season_stats(voti_matched):
    """aggregati per master su una stagione di voti (gia' matchati)."""
    v = voti_matched.copy()
    for c in ["voto", "fantavoto"]:
        v[c] = pd.to_numeric(v[c], errors="coerce")
    played = v[v.sv == 0]
    agg = played.groupby("master_id").agg(
        fantamedia=("fantavoto", "mean"), media_voto=("voto", "mean"),
        presenze=("fantavoto", "count"))
    bonus = v.groupby("master_id").agg(
        gol=("gol_fatti", "sum"), assist=("assist", "sum"),
        rig_segnati=("rigore_segnato", "sum"), rig_sbagliati=("rigori_sbagliati", "sum"),
        ammonizioni=("ammonizione", "sum"))
    return agg.join(bonus, how="outer")


def build_players(reg, pt, votes_hist):
    fs_snap = json.load(open(MATCH_DIR / "fs_snapshot.json", encoding="utf-8"))
    mfs = pd.read_csv(MATCH_DIR / "map_fantasoccer.csv")
    mu = pd.read_csv(MATCH_DIR / "map_understat.csv")
    mtm = pd.read_csv(MATCH_DIR / "map_tm.csv")
    vals = pd.read_csv(RAW / "transfermarkt" / "transfermarkt_valuations_seriea.csv",
                       parse_dates=["date"])

    # presenza per stagione (per flag nuovo_in_serie_a)
    presence = {s: set(v.master_id.unique()) for s, v in votes_hist.items()}
    for y in (2019, 2020):  # stagioni pre-voti coperte da understat
        s = f"{y}-{str(y+1)[-2:]}"
        us = pd.read_csv(RAW / "understat" / f"understat_players_{y}.csv")
        m = mu[(mu.understat_season == y) & mu.master_id.notna()]
        mm = dict(zip(m.player_name, m.master_id))
        ids = {int(mm[p]) for p, mins in zip(us.player_name, us.minutes)
               if p in mm and mins > 0}
        presence[s] = ids

    # squadre per stagione (per flag neopromossa)
    teams_by_season = reg.groupby("stagione")["squadra"].agg(set).to_dict()

    stats_by_season = {s: season_stats(v) for s, v in votes_hist.items()}

    for s in PLAYERS_SEASONS:
        y = int(s[:4])
        sept1 = pd.Timestamp(y, 9, 1)
        base = reg[reg.stagione == s].copy().rename(columns={"squadra": "squadra_listone"})

        # --- squadra alla data d'asta: snapshot fanta.soccer inizio settembre
        g = fs_snap[s][0]
        fs = mfs[(mfs.stagione == s) & (mfs.giornata == g) & mfs.master_id.notna()].copy()
        fs["master_id"] = fs.master_id.astype(int)
        # mappa nome squadra fanta.soccer -> sigla, via co-occorrenza col registry
        tmp = fs.merge(base[["master_id", "squadra_listone"]], on="master_id")
        fsmap = (tmp.groupby(["squadra", "squadra_listone"]).size().reset_index(name="n")
                    .sort_values("n", ascending=False).drop_duplicates("squadra"))
        fs_team = dict(zip(fsmap.squadra, fsmap.squadra_listone))
        # fix round 1 (audit Difetto 1): mai keep-first arbitrario quando piu' righe
        # fanta.soccer puntano allo stesso master: vince il match di qualita' migliore
        # (conferma squadra > ruolo > metodo esatto); a pari merito nessuna riga.
        fs, n_tie = pick_best_per_master(fs)
        if n_tie:
            print(f"  fanta.soccer {s}: {n_tie} master scartati per pari merito")
        fs["squadra_fs"] = fs.squadra.map(fs_team)
        base = base.merge(fs[["master_id", "squadra_fs", "quotazione"]],
                          on="master_id", how="left")
        base["squadra"] = base.squadra_fs.fillna(base.squadra_listone)
        base["squadra_fonte"] = np.where(base.squadra_fs.notna(), "fantasoccer", "fantacalcioit")
        base = base.rename(columns={"quotazione": "quot_fs_sett"})

        # --- eta' e valore transfermarkt <= 1 settembre
        base = base.merge(mtm[["master_id", "tm_player_id", "date_of_birth"]],
                          on="master_id", how="left")
        dob = pd.to_datetime(base.date_of_birth, errors="coerce")
        base["eta"] = ((sept1 - dob).dt.days / 365.25).round(2)
        # guardia sanity (fix round 1, audit Difetto 6): eta' fuori (15, 45) = match TM
        # su omonimo -> NaN (gia' quasi tutti intercettati a monte in match_tm)
        bad_age = (base.eta <= ETA_MIN) | (base.eta >= ETA_MAX)
        if bad_age.any():
            print(f"  eta' fuori range in {s}: {base.loc[bad_age, 'nome'].tolist()} -> NaN")
            base.loc[bad_age, ["eta", "tm_player_id"]] = np.nan  # tm_value seguira' NaN
        v = vals[vals.date <= sept1].sort_values("date").drop_duplicates("player_id", keep="last")
        vmap = dict(zip(v.player_id, v.market_value_in_eur))
        base["tm_value_eur"] = base.tm_player_id.map(vmap)

        # --- flag
        prevs = prev_seasons(s, 3)
        known = [p for p in prevs if p in presence]
        prev_ids = set().union(*[presence[p] for p in known]) if known else set()
        base["nuovo_in_serie_a"] = (~base.master_id.isin(prev_ids)).astype(int)
        p1 = prevs[0]
        prev_teams = teams_by_season.get(p1, set())
        base["squadra_neopromossa"] = (~base.squadra_listone.isin(prev_teams)).astype(int)

        # --- storico voti: 3 stagioni precedenti
        for i, p in enumerate(prevs, start=1):
            st = stats_by_season.get(p)
            cols = ["fantamedia", "media_voto", "presenze", "gol", "assist",
                    "rig_segnati", "rig_sbagliati", "ammonizioni"]
            if st is None:
                for c in cols:
                    base[f"prev{i}_{c}"] = np.nan
            else:
                st2 = st.rename(columns={c: f"prev{i}_{c}" for c in cols})
                base = base.merge(st2, left_on="master_id", right_index=True, how="left")

        # --- understat stagione precedente
        uy = y - 1
        us = pd.read_csv(RAW / "understat" / f"understat_players_{uy}.csv")
        m = mu[(mu.understat_season == uy) & mu.master_id.notna()].copy()
        us = us.merge(m[["player_name", "master_id"]], on="player_name", how="inner")
        us["master_id"] = us.master_id.astype(int)
        us = us.sort_values("minutes", ascending=False).drop_duplicates("master_id")
        us["us_prev_xg90"] = np.where(us.minutes > 0, us.xG / us.minutes * 90, np.nan)
        us = us.rename(columns={"xG": "us_prev_xg", "xA": "us_prev_xa",
                                "npxG": "us_prev_npxg", "shots": "us_prev_shots",
                                "minutes": "us_prev_minutes"})
        base = base.merge(us[["master_id", "us_prev_xg", "us_prev_xa", "us_prev_npxg",
                              "us_prev_shots", "us_prev_minutes", "us_prev_xg90"]],
                          on="master_id", how="left")

        # --- xG squadra (squadra corrente, stagione precedente)
        ut = pd.read_csv(RAW / "understat" / f"understat_teams_{uy}.csv")
        txg = dict(zip(ut.team, ut.xG))
        base["team_prev_xg"] = base.squadra.map(
            lambda sg: txg.get(SIGLA_TO_UNDERSTAT.get(sg, ""), np.nan))

        # --- target (gerarchia fix round 1: estive 10x500 / estive all / tardive / wayback)
        t = pt[pt.stagione == s].drop(columns=["stagione"])
        t = t.rename(columns={c: f"target_{c}" for c in t.columns if c != "master_id"})
        base = base.merge(t, on="master_id", how="left")
        for c in ["target_n_obs_10x500_estiva", "target_n_obs_all_estiva",
                  "target_n_obs_tardiva"]:
            base[c] = base[c].fillna(0).astype(int)

        out_cols = (["master_id", "nome", "ruolo", "squadra", "squadra_listone",
                     "squadra_fonte", "qt_i", "fvm", "quot_fs_sett", "eta",
                     "tm_value_eur", "nuovo_in_serie_a", "squadra_neopromossa"]
                    + [f"prev{i}_{c}" for i in (1, 2, 3)
                       for c in ["fantamedia", "media_voto", "presenze", "gol", "assist",
                                 "rig_segnati", "rig_sbagliati", "ammonizioni"]]
                    + ["us_prev_xg", "us_prev_xa", "us_prev_npxg", "us_prev_shots",
                       "us_prev_minutes", "us_prev_xg90", "team_prev_xg"]
                    + [f"target_{p}_{sfx}" for sfx in ["10x500_estiva", "all_estiva", "tardiva"]
                       for p in ["n_obs", "mean_pct", "std_pct"]]
                    + ["target_wayback_p500_10sq"])
        out = base[out_cols]
        assert out.master_id.is_unique
        out.to_parquet(PROC / f"players_{s}.parquet", index=False)
        print(f"players_{s}.parquet: {len(out)} righe | squadra da fanta.soccer: "
              f"{(out.squadra_fonte=='fantasoccer').sum()} | eta' nota: {out.eta.notna().sum()} | "
              f"target est. 10x500: {(out.target_n_obs_10x500_estiva>0).sum()} | "
              f"target est. all>=3: {(out.target_n_obs_all_estiva>=3).sum()} | "
              f"target wayback: {out.target_wayback_p500_10sq.notna().sum()}")


def main():
    reg = pd.read_csv(PROC / "registry.csv")
    aste = build_aste(reg)
    pt = build_price_targets(aste, reg)
    votes_hist = build_votes(reg)
    build_players(reg, pt, votes_hist)


if __name__ == "__main__":
    main()
