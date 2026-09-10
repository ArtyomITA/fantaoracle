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

# Cartella di uscita: PROC salvo `--out` (aggiunta additiva del 10/9/2026 per
# poter rigenerare in una cartella temporanea e confrontare le impronte senza
# toccare i file correnti). Le LETTURE restano sempre da PROC.
OUT_DIR = PROC

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
    aste.to_csv(OUT_DIR / "aste_reali_clean.csv", index=False, encoding="utf-8")
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
    pt.to_csv(OUT_DIR / "price_targets.csv", index=False, encoding="utf-8")
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
    return pd.read_csv(OUT_DIR / "price_targets.csv")


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
        out.to_parquet(OUT_DIR / f"votes_{s}.parquet", index=False)
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
        ammonizioni=("ammonizione", "sum"), espulsioni=("espulsione", "sum"))
    # stage S4: presenze con voto nelle ultime 10 giornate (trend di fine stagione)
    last10 = (played[played.giornata >= 29].groupby("master_id").size()
              .rename("pres_last10"))
    out = agg.join(bonus, how="outer").join(last10, how="left")
    out["pres_last10"] = out["pres_last10"].fillna(0).astype(float)
    return out


# ------------------------------------------------------------------ stage S4
# feature a costo zero dai dati gia' in casa (voti raw, TM appearances,
# understat squadre). Tutte dalla stagione PRECEDENTE (o 3 precedenti pesate):
# nessuna informazione della stagione stessa.
NEW_FEATS = [
    "tm_prev_min_per_app", "tm_prev_share90", "prev1_pres_last10",   # (a) minuti/trend
    "amm_pp_w", "esp_pp_w", "squal_att",                              # (b) disciplina
    "team_prev_xga", "team_prev_xpts", "team_prev_cs",                # (d) squadra
    "rig_tirati_prev1", "rigorista_1_prev",                           # (e) rigorista
]
DISC_W = (3.0, 2.0, 1.0)   # pesi prev1/prev2/prev3 per le medie disciplinari
GIORNATE = 38


def tm_minutes_by_season():
    """{season_start_year: DataFrame indice player_id (minuti totali, presenze
    con minuti > 0, min_per_app, share90 = minuti / (38*90))} dalle
    appearances Serie A di Transfermarkt."""
    ap = pd.read_csv(RAW / "transfermarkt" / "transfermarkt_appearances_seriea.csv")
    ap = ap[ap.competition_id == "IT1"]
    out = {}
    for y, d in ap.groupby("season_start_year"):
        g = d.groupby("player_id").agg(minuti=("minutes_played", "sum"),
                                       app=("minutes_played", lambda x: int((x > 0).sum())))
        g["min_per_app"] = np.where(g.app > 0, g.minuti / g.app.clip(lower=1), np.nan)
        g["share90"] = g.minuti / (GIORNATE * 90.0)
        g.index = g.index.astype(float)   # tm_player_id nei players e' float (NaN)
        out[int(y)] = g
    return out


def team_clean_sheets(voti_matched, team_map):
    """{sigla: n giornate con portiere a 0 gol subiti} nella stagione (voti
    raw: righe dei portieri con sv=0 e gol_subiti=0)."""
    v = voti_matched
    gk = v[(v.ruolo.str.lower() == "p") & (v.sv == 0) & (v.gol_subiti.fillna(0) == 0)]
    cs = gk.groupby("squadra")["giornata"].nunique()
    return {team_map[t]: int(n) for t, n in cs.items() if t in team_map}


def rigoristi(voti_matched, team_map):
    """{master_id: 1/0} = primo tiratore di rigori della propria squadra nella
    stagione (rigori tirati = segnati + sbagliati, massimo di squadra, almeno 1).
    Squadra = quella con piu' righe voto del giocatore."""
    v = voti_matched.copy()
    v["rig_tirati"] = v.rigore_segnato.fillna(0) + v.rigori_sbagliati.fillna(0)
    tir = v.groupby("master_id")["rig_tirati"].sum()
    team = v.groupby("master_id")["squadra"].agg(lambda x: x.mode().iloc[0]).map(team_map)
    df = pd.DataFrame({"tir": tir, "team": team})
    tmax = df.groupby("team")["tir"].transform("max")
    df["rig1"] = ((df.tir >= 1) & (df.tir >= tmax)).astype(float)
    return dict(zip(df.index, df.rig1))


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

    # stage S4: minuti TM per stagione, porte inviolate di squadra e primo
    # rigorista per stagione (dai voti raw, nomi squadra -> sigla via team_maps)
    tm_by_year = tm_minutes_by_season()
    team_maps = json.load(open(MATCH_DIR / "team_maps.json", encoding="utf-8"))
    cs_by_season = {s: team_clean_sheets(v, team_maps.get(s, {}))
                    for s, v in votes_hist.items()}
    rig_by_season = {s: rigoristi(v, team_maps.get(s, {})) for s, v in votes_hist.items()}

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
        # fix audit nuovi in Serie A: il dump TM conferma il match solo con presenze
        # IT1, quindi i nuovi arrivi restano NaN. Per la stagione corrente riempie i
        # soli NaN dalla rosa TM scaricata (scrape_tm_kader + f0b_match_tm_kader):
        # eta' da DOB al 1/9, valore di mercato attuale. Stagioni passate: nessun file.
        kp = MATCH_DIR / f"map_tm_kader_{y}.csv"
        if kp.exists():
            k = pd.read_csv(kp).drop_duplicates("master_id")
            k_dob = pd.to_datetime(k.date_of_birth, errors="coerce")
            k_eta = dict(zip(k.master_id, ((sept1 - k_dob).dt.days / 365.25).round(2)))
            k_val = dict(zip(k.master_id, k.market_value_eur))
            k_id = dict(zip(k.master_id, k.tm_player_id))
            f_eta = base.eta.isna() & base.master_id.isin(k_eta)
            f_val = base.tm_value_eur.isna() & base.master_id.isin(k_val)
            f_id = base.tm_player_id.isna() & base.master_id.isin(k_id)
            base.loc[f_eta, "eta"] = base.loc[f_eta, "master_id"].map(k_eta)
            base.loc[f_val, "tm_value_eur"] = base.loc[f_val, "master_id"].map(k_val)
            base.loc[f_id, "tm_player_id"] = base.loc[f_id, "master_id"].map(k_id)
            print(f"  rosa TM {y} ({kp.name}): eta' riempita {f_eta.sum()} | "
                  f"tm_value riempito {f_val.sum()}")

        # --- flag
        prevs = prev_seasons(s, 3)
        known = [p for p in prevs if p in presence]
        prev_ids = set().union(*[presence[p] for p in known]) if known else set()
        base["nuovo_in_serie_a"] = (~base.master_id.isin(prev_ids)).astype(int)
        p1 = prevs[0]
        prev_teams = teams_by_season.get(p1, set())
        base["squadra_neopromossa"] = (~base.squadra_listone.isin(prev_teams)).astype(int)
        # cambio_squadra: squadra all'asta diversa da quella del listone della
        # stagione precedente (registry); NaN se assente dal listone precedente
        r1 = reg[reg.stagione == p1]
        sq_prev = base.master_id.map(dict(zip(r1.master_id, r1.squadra)))
        base["cambio_squadra"] = np.where(sq_prev.isna(), np.nan,
                                          (base.squadra != sq_prev).astype(float))

        # --- storico voti: 3 stagioni precedenti
        for i, p in enumerate(prevs, start=1):
            st = stats_by_season.get(p)
            cols = ["fantamedia", "media_voto", "presenze", "gol", "assist",
                    "rig_segnati", "rig_sbagliati", "ammonizioni",
                    "espulsioni", "pres_last10"]   # ultime due: stage S4
            if st is None:
                for c in cols:
                    base[f"prev{i}_{c}"] = np.nan
            else:
                st2 = st[cols].rename(columns={c: f"prev{i}_{c}" for c in cols})
                base = base.merge(st2, left_on="master_id", right_index=True, how="left")

        # --- stage S4 (a) minuti TM stagione precedente + trend ultime 10 giornate
        tmp_ = tm_by_year.get(y - 1)
        if tmp_ is not None:
            base["tm_prev_min_per_app"] = base.tm_player_id.map(tmp_["min_per_app"])
            base["tm_prev_share90"] = base.tm_player_id.map(tmp_["share90"])
        else:
            base["tm_prev_min_per_app"] = np.nan
            base["tm_prev_share90"] = np.nan
        # prev1_pres_last10 gia' nel merge sopra (NaN se assente dai voti prev1)

        # --- stage S4 (b) disciplina: ammonizioni/espulsioni per presenza su 3
        # stagioni pesate (3/2/1, stagioni mancanti escluse) e squalifiche attese
        # su 38 presenze (1 per espulsione, 1 ogni 5 ammonizioni)
        num_a = np.zeros(len(base)); num_e = np.zeros(len(base)); den = np.zeros(len(base))
        for i, w in enumerate(DISC_W, start=1):
            pres_i = base[f"prev{i}_presenze"].astype(float)
            ok = pres_i.notna()
            den += np.where(ok, w * pres_i.fillna(0), 0.0)
            num_a += np.where(ok, w * base[f"prev{i}_ammonizioni"].astype(float).fillna(0), 0.0)
            num_e += np.where(ok, w * base[f"prev{i}_espulsioni"].astype(float).fillna(0), 0.0)
        base["amm_pp_w"] = np.where(den > 0, num_a / np.where(den > 0, den, 1), np.nan)
        base["esp_pp_w"] = np.where(den > 0, num_e / np.where(den > 0, den, 1), np.nan)
        base["squal_att"] = GIORNATE * (base.esp_pp_w + base.amm_pp_w / 5.0)

        # --- stage S4 (e) rigorista storico (stagione precedente)
        base["rig_tirati_prev1"] = base.prev1_rig_segnati + base.prev1_rig_sbagliati
        rg = rig_by_season.get(p1)
        base["rigorista_1_prev"] = (base.master_id.map(rg) if rg is not None
                                    else np.nan)

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
        # stage S4 (d): xGA e xPts della squadra corrente nella stagione
        # precedente + porte inviolate reali (dai voti raw); NaN per le
        # neopromosse, come team_prev_xg
        txga = dict(zip(ut.team, ut.xGA))
        txp = dict(zip(ut.team, ut.xpts))
        base["team_prev_xga"] = base.squadra.map(
            lambda sg: txga.get(SIGLA_TO_UNDERSTAT.get(sg, ""), np.nan))
        base["team_prev_xpts"] = base.squadra.map(
            lambda sg: txp.get(SIGLA_TO_UNDERSTAT.get(sg, ""), np.nan))
        cs_prev = cs_by_season.get(p1, {})
        base["team_prev_cs"] = base.squadra.map(lambda sg: cs_prev.get(sg, np.nan))

        # --- target (gerarchia fix round 1: estive 10x500 / estive all / tardive / wayback)
        t = pt[pt.stagione == s].drop(columns=["stagione"])
        t = t.rename(columns={c: f"target_{c}" for c in t.columns if c != "master_id"})
        base = base.merge(t, on="master_id", how="left")
        for c in ["target_n_obs_10x500_estiva", "target_n_obs_all_estiva",
                  "target_n_obs_tardiva"]:
            base[c] = base[c].fillna(0).astype(int)

        out_cols = (["master_id", "nome", "ruolo", "squadra", "squadra_listone",
                     "squadra_fonte", "qt_i", "fvm", "quot_fs_sett", "eta",
                     "tm_value_eur", "nuovo_in_serie_a", "squadra_neopromossa",
                     "cambio_squadra"]
                    + [f"prev{i}_{c}" for i in (1, 2, 3)
                       for c in ["fantamedia", "media_voto", "presenze", "gol", "assist",
                                 "rig_segnati", "rig_sbagliati", "ammonizioni"]]
                    + ["us_prev_xg", "us_prev_xa", "us_prev_npxg", "us_prev_shots",
                       "us_prev_minutes", "us_prev_xg90", "team_prev_xg"]
                    + [f"target_{p}_{sfx}" for sfx in ["10x500_estiva", "all_estiva", "tardiva"]
                       for p in ["n_obs", "mean_pct", "std_pct"]]
                    + ["target_wayback_p500_10sq"]
                    + NEW_FEATS)
        out = base[out_cols]
        assert out.master_id.is_unique
        out.to_parquet(OUT_DIR / f"players_{s}.parquet", index=False)
        scrivi_contratto_players(s)
        print(f"players_{s}.parquet: {len(out)} righe | squadra da fanta.soccer: "
              f"{(out.squadra_fonte=='fantasoccer').sum()} | eta' nota: {out.eta.notna().sum()} | "
              f"target est. 10x500: {(out.target_n_obs_10x500_estiva>0).sum()} | "
              f"target est. all>=3: {(out.target_n_obs_all_estiva>=3).sum()} | "
              f"target wayback: {out.target_wayback_p500_10sq.notna().sum()}")


def scrivi_contratto_players(s):
    """Aggancio additivo (10/9/2026): scrive il contratto temporale delle colonne
    accanto al parquet. Non deve MAI fermare la catena: qualunque errore viene
    stampato e ignorato."""
    try:
        sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
        from fantabot.contratto_players import scrivi_contratto
        p = scrivi_contratto(s, parquet=OUT_DIR / f"players_{s}.parquet",
                             cartella=OUT_DIR)
        print(f"  contratto: {p.name}")
    except Exception as e:  # noqa: BLE001
        print(f"  contratto NON scritto per {s}: {type(e).__name__}: {e}")


def main(argv=None):
    global OUT_DIR
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=None,
                    help="cartella di uscita alternativa (default data/processed)")
    a = ap.parse_args(argv)
    if a.out:
        OUT_DIR = Path(a.out)
        OUT_DIR.mkdir(parents=True, exist_ok=True)
        print(f"uscita in {OUT_DIR}")
    reg = pd.read_csv(PROC / "registry.csv")
    aste = build_aste(reg)
    pt = build_price_targets(aste, reg)
    votes_hist = build_votes(reg)
    build_players(reg, pt, votes_hist)


if __name__ == "__main__":
    main()
