# -*- coding: utf-8 -*-
"""Fase 0b — name matching di tutte le fonti sul registry (per stagione).

Output in data/processed/_match/:
  map_voti.csv, map_fantasoccer.csv, map_wayback.csv, map_ge.csv,
  map_understat.csv, map_tm.csv, team_maps.json
e data/processed/unmatched_report.csv (ogni non-match/ambiguo con top-3 candidati).
"""
import json
import sys
from collections import defaultdict
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).parent))
from f0b_lib import (RAW, FONTI, PROC, MATCH_DIR, SEASONS, VOTI_SEASONS, norm,  # noqa: E402
                     split_registry_name, parse_wayback_name, parse_ge_name,
                     match_given_surname, load_registry, season_indexes,
                     SeasonIndex, UnmatchedLog, derive_team_map, apply_alias,
                     method_quality)

LOG = UnmatchedLog()

# stagione stimata per file GE (da gruppoesperti/REPORT.md)
GE_FILE_SEASON = {
    "gruppoesperti_prezzi_aste_reali_2024-25.xlsx": "2024-25",
    "gruppoesperti_prezzi_aste_reali_2021-22circa.xlsx": "2021-22",
    "extra/1Uxv42LC7d68Y1ZLQ48Hh1ud74kJocO-lTom39eJFB_w.xlsx": "2024-25",
    "extra/1MeKG7yjCemQ1SFoi7RWmhni-iBMtYdPf9FtfdDQWZ5I.xlsx": "2023-24",
    "extra/1J4tILPqyErS5Ccpr0Dy-595D2PgubYxlPaqfX8-pjYw.xlsx": "2024-25",
}

# file wayback/fonti_prezzi per stagione: (path, sep) in ordine di priorita'
WAYBACK_FILES = {
    "2020-21": [(RAW / "wayback_prices/prezzi_2020-21_20210518002802.csv", ",")],
    "2021-22": [(RAW / "wayback_prices/prezzi_2021-22_20220126223034.csv", ",")],
    "2022-23": [(RAW / "wayback_prices/prezzi_2022-23_20240123141420.csv", ",")],
    "2023-24": [(FONTI / "wayback_20240519_stagione2023-24.csv", ";")],
    "2024-25": [(RAW / "wayback_prices/prezzi_2024-25_20250214053906.csv", ","),
                 (RAW / "wayback_prices/prezzi_2024-25_20250616102603.csv", ","),
                 (FONTI / "wayback_20241004_stagione2024-25.csv", ";")],
    "2025-26": [(RAW / "wayback_prices/prezzi_2025-26_20260411054907.csv", ","),
                 (FONTI / "wayback_20251212_stagione2025-26_congelata.csv", ";"),
                 (FONTI / "fantacalcio-online_live_2026-08-06_stagione2025-26.csv", ";")],
}

# snapshot fanta.soccer di inizio settembre per i players_{stagione}
FS_SNAPSHOT = {}  # riempito in main leggendo fantasoccer_date_rilevazioni.csv


def read_semicolon_csv(path):
    df = pd.read_csv(path, sep=";", encoding="utf-8-sig")
    for c in ["kap", "p350_8sq", "p350_10sq", "p500_8sq", "p500_10sq"]:
        if c in df.columns and df[c].dtype == object:
            df[c] = pd.to_numeric(df[c].astype(str).str.replace(",", "."), errors="coerce")
    return df


# ------------------------------------------------------------------ VOTI
def match_voti(idx_by_season):
    out = []
    team_maps = {}
    for s in VOTI_SEASONS:
        idx = idx_by_season[s]
        voti = pd.read_csv(RAW / "voti" / f"voti_{s}.csv")
        uniq = voti[["squadra", "nome", "ruolo"]].drop_duplicates()
        pairs = []
        parsed = {}
        for r in uniq.itertuples(index=False):
            surname, ini = split_registry_name(r.nome)
            parsed[(r.squadra, r.nome)] = (surname, ini)
            pairs.append((r.squadra, surname, ini))
        tmap = derive_team_map(pairs, idx)
        team_maps[s] = tmap
        season_rows = []
        for r in uniq.itertuples(index=False):
            surname, ini = parsed[(r.squadra, r.nome)]
            sigla = tmap.get(r.squadra)
            role = str(r.ruolo).upper()
            m = idx.match(surname, src_ini=ini, role=role, sigla=sigla)
            if m["master_id"] is None and not ini and len(surname.split()) > 1:
                # forme 'Nome Cognome' (es. 'Rafael Leao' quando il listone ha 'Leao')
                toks = surname.split()
                m2 = match_given_surname(idx, toks[0], toks[1:], role=role, sigla=sigla)
                if m2["master_id"] is not None:
                    m = m2
            if m["master_id"] is None and not m["method"].startswith("rejected"):
                # senza filtro ruolo (ruoli possono differire tra voti e listone? raro)
                # NON se il match col ruolo era stato rifiutato per conflitto (fix round 1)
                m3 = idx.match(surname, src_ini=ini, sigla=sigla)
                if m3["master_id"] is not None:
                    # guardia P residua: il retry senza ruolo non puo' fondere P e movimento
                    cand_role = m3["candidates"][0][2]
                    if (role == "P") == (cand_role == "P"):
                        m = m3
            season_rows.append(dict(stagione=s, squadra=r.squadra, nome=r.nome,
                                    ruolo=role, master_id=m["master_id"], method=m["method"],
                                    candidates=m["candidates"]))
        # guardia multi-nome (fix round 1, audit Difetto 4): nella stessa stagione lo
        # stesso master non puo' arrivare da due NOMI diversi dei voti (Terracciano vs
        # Terracciano F., Ricci S. vs Basso Ricci): vince il nome col match migliore.
        d = pd.DataFrame(season_rows)
        matched = d[d.master_id.notna()]
        n_rej_multi = 0
        for mid, g in matched.groupby("master_id"):
            if g.nome.nunique() <= 1:
                continue
            qual = {i: method_quality(g.at[i, "method"]) for i in g.index}
            best_i = max(qual, key=qual.get)
            best_q, best_nome = qual[best_i], g.at[best_i, "nome"]
            tie_other = [i for i in g.index
                         if g.at[i, "nome"] != best_nome and qual[i] == best_q]
            losers = (list(g.index) if tie_other  # pari merito fra nomi diversi: tutti fuori
                      else [i for i in g.index if g.at[i, "nome"] != best_nome])
            for i in losers:
                d.loc[i, "master_id"] = None
                d.loc[i, "method"] = "rejected_multi_nome"
                n_rej_multi += 1
        n_ok = 0
        for r in d.itertuples(index=False):
            if r.master_id is None or pd.isna(r.master_id):
                LOG.add("voti", s, r.nome, f"squadra={r.squadra} ruolo={r.ruolo}",
                        r.method, r.candidates)
            else:
                n_ok += 1
            out.append(dict(stagione=s, squadra=r.squadra, nome=r.nome,
                            master_id=r.master_id, method=r.method))
        extra = f", {n_rej_multi} rifiutati multi-nome" if n_rej_multi else ""
        print(f"voti {s}: {n_ok}/{len(uniq)} match ({n_ok/len(uniq)*100:.1f}%){extra}")
    return pd.DataFrame(out), team_maps


# ------------------------------------------------------------------ FANTA.SOCCER
def match_fantasoccer(idx_by_season, seasons_giornate):
    out = []
    for s, gg in seasons_giornate.items():
        idx = idx_by_season[s]
        for g in gg:
            path = RAW / "quotazioni" / f"fantasoccer_{s}_g{g:02d}.csv"
            if not path.exists():
                print(f"fantasoccer {s} g{g}: FILE MANCANTE")
                continue
            fs = pd.read_csv(path)
            pairs = []
            for r in fs.itertuples(index=False):
                surname = norm(r.Cognome)
                ini = norm(r.Nome)[:1] if pd.notna(r.Nome) else ""
                pairs.append((r.Squadra, surname, ini))
            tmap = derive_team_map(pairs, idx)
            n_ok = 0
            for r in fs.itertuples(index=False):
                surname = norm(r.Cognome)
                ini = norm(r.Nome)[:1] if pd.notna(r.Nome) else ""
                sigla = tmap.get(r.Squadra)
                role = str(r.Ruolo).upper()
                m = idx.match(surname, src_ini=ini, role=role, sigla=sigla)
                if m["master_id"] is None and len(surname.split()) > 1:
                    # fanta.soccer mette 'Nome Cognome' nel campo Cognome per molti stranieri
                    toks = surname.split()
                    m2 = match_given_surname(idx, toks[0], toks[1:], role=role, sigla=sigla)
                    if m2["master_id"] is not None:
                        m = m2
                if m["master_id"] is None:
                    LOG.add("fantasoccer", s, f"{r.Cognome} {r.Nome}",
                            f"squadra={r.Squadra} ruolo={r.Ruolo} g={g}",
                            m["method"], m["candidates"])
                else:
                    n_ok += 1
                out.append(dict(stagione=s, giornata=g, codice=r.Codice,
                                cognome=r.Cognome, nome_ini=r.Nome, squadra=r.Squadra,
                                ruolo=r.Ruolo, quotazione=r.Quotazione,
                                master_id=m["master_id"], method=m["method"]))
            print(f"fantasoccer {s} g{g}: {n_ok}/{len(fs)} match ({n_ok/len(fs)*100:.1f}%)")
    return pd.DataFrame(out)


# ------------------------------------------------------------------ WAYBACK
def match_wayback(idx_by_season):
    out = []
    for s, files in WAYBACK_FILES.items():
        if s not in idx_by_season:
            continue
        idx = idx_by_season[s]
        for prio, (path, sep) in enumerate(files):
            if not path.exists():
                print(f"wayback {s}: manca {path}")
                continue
            df = read_semicolon_csv(path) if sep == ";" else pd.read_csv(path)
            pairs = []
            parsed = {}
            for r in df.itertuples(index=False):
                surname, ini = parse_wayback_name(r.nome)
                parsed[r.nome] = (surname, ini)
                if r.squadra not in ("Estero", "Serie Minori"):
                    pairs.append((r.squadra, surname, ini))
            tmap = derive_team_map(pairs, idx)
            n_ok = 0
            for r in df.itertuples(index=False):
                surname, ini = parsed[r.nome]
                sigla = tmap.get(r.squadra)
                role = str(r.ruolo).upper() if pd.notna(r.ruolo) and str(r.ruolo).strip() else None
                m = idx.match(surname, src_ini=ini, role=role, sigla=sigla)
                if m["master_id"] is None:
                    # i senza-prezzo fuori listone non ci interessano: log solo se ha un prezzo
                    has_price = any(pd.notna(getattr(r, c)) for c in
                                    ["p350_8sq", "p350_10sq", "p500_8sq", "p500_10sq"])
                    if has_price:
                        LOG.add("wayback", s, r.nome, f"file={path.name} squadra={r.squadra}",
                                m["method"], m["candidates"])
                else:
                    n_ok += 1
                out.append(dict(stagione=s, file=path.name, prio=prio, nome=r.nome,
                                squadra=r.squadra,
                                p350_8sq=getattr(r, "p350_8sq", None),
                                p350_10sq=getattr(r, "p350_10sq", None),
                                p500_8sq=getattr(r, "p500_8sq", None),
                                p500_10sq=getattr(r, "p500_10sq", None),
                                master_id=m["master_id"], method=m["method"]))
            print(f"wayback {s} {path.name}: {n_ok}/{len(df)} match ({n_ok/len(df)*100:.1f}%)")
    return pd.DataFrame(out)


# ------------------------------------------------------------------ GRUPPOESPERTI
def match_ge(idx_by_season):
    aste = pd.read_csv(RAW / "gruppoesperti" / "aste_reali_tidy.csv")
    aste["stagione"] = aste["source_file"].map(GE_FILE_SEASON)
    uniq = aste[["stagione", "ruolo", "player_raw"]].drop_duplicates()
    out = []
    n_ok = tot = 0
    per_season = defaultdict(lambda: [0, 0])
    for r in uniq.itertuples(index=False):
        idx = idx_by_season[r.stagione]
        s_full = norm(r.player_raw)
        toks = s_full.split()
        surname, ini = parse_ge_name(r.player_raw)
        # varianti di parsing, in ordine di affidabilita'
        variants = [(surname, ini)]
        if s_full != surname:
            variants.append((s_full, ""))
        if len(toks) > 1 and 1 < len(toks[-1]) <= 3:
            variants.append((" ".join(toks[:-1]), toks[-1]))  # iniziale multi-lettera 'martinez lu'
        m = None
        any_rejected = False
        for sn, i2 in variants:
            m = idx.match(sn, src_ini=i2, role=r.ruolo)
            if m["master_id"] is not None:
                break
            any_rejected = any_rejected or m["method"].startswith("rejected")
        if m["master_id"] is None and len(toks) > 1:
            # forma 'nome cognome' (es. 'dany mota', 'luis alberto')
            m2 = match_given_surname(idx, toks[0], toks[1:], role=r.ruolo)
            if m2["master_id"] is not None:
                m = m2
        if m["master_id"] is None and not any_rejected:
            # senza vincolo di ruolo (alcune aste marcano ruoli diversi dal listone).
            # fix round 1: NON se un match col ruolo era stato rifiutato per conflitto
            # (es. DE VRIES ruolo C non deve ricadere su De Vrij D), e mai P<->movimento.
            m3 = idx.match(surname, src_ini=ini)
            if m3["master_id"] is not None:
                cand_role = m3["candidates"][0][2]
                if (str(r.ruolo).upper() == "P") == (cand_role == "P"):
                    m = dict(m3, method=m3["method"] + "_norole")
        tot += 1
        per_season[r.stagione][1] += 1
        if m["master_id"] is None:
            LOG.add("gruppoesperti", r.stagione, r.player_raw, f"ruolo={r.ruolo}",
                    m["method"], m["candidates"])
        else:
            n_ok += 1
            per_season[r.stagione][0] += 1
        out.append(dict(stagione=r.stagione, ruolo=r.ruolo, player_raw=r.player_raw,
                        master_id=m["master_id"], method=m["method"]))
    for s, (ok, t) in sorted(per_season.items()):
        print(f"ge {s}: {ok}/{t} nomi unici match ({ok/t*100:.1f}%)")
    return pd.DataFrame(out)


# ------------------------------------------------------------------ UNDERSTAT
def match_understat(idx_by_season, reg):
    # understat season Y = stagione 'Y-(Y+1)'; servono 2020..2025 (feature) + 2019 (presenza)
    out = []
    global_idx = SeasonIndex(
        reg.sort_values("stagione").drop_duplicates("master_id", keep="last"), "global")
    for y in range(2019, 2026):
        s = f"{y}-{str(y+1)[-2:]}"
        idx = idx_by_season.get(s, global_idx)
        df = pd.read_csv(RAW / "understat" / f"understat_players_{y}.csv")
        n_ok = 0
        for r in df.itertuples(index=False):
            toks = norm(r.player_name).split()
            given = toks[0] if len(toks) > 1 else ""
            surn_toks = toks[1:] if len(toks) > 1 else toks
            m = match_given_surname(idx, given, surn_toks)
            if m["master_id"] is None:
                LOG.add("understat", s, r.player_name, f"team={r.team}",
                        m["method"], m["candidates"])
            else:
                n_ok += 1
            out.append(dict(understat_season=y, stagione=s, player_name=r.player_name,
                            master_id=m["master_id"], method=m["method"]))
        print(f"understat {y} ({s}): {n_ok}/{len(df)} match ({n_ok/len(df)*100:.1f}%)")
    return pd.DataFrame(out)


# ------------------------------------------------------------------ TRANSFERMARKT
TM_POS_TO_ROLE = {"Goalkeeper": "P", "Defender": "D", "Midfield": "C", "Attack": "A"}


def match_tm(reg):
    tm = pd.read_csv(RAW / "transfermarkt" / "transfermarkt_players.csv")
    tm["ln_norm"] = tm["last_name"].map(norm)
    tm["fn_norm"] = tm["first_name"].map(norm)
    tm["full_norm"] = tm["name"].map(norm)
    by_ln = defaultdict(list)
    for i, r in tm.iterrows():
        by_ln[r.ln_norm].append(r)
    app = pd.read_csv(RAW / "transfermarkt" / "transfermarkt_appearances_seriea.csv",
                      usecols=["player_id", "season_start_year"])
    tm_seasons = app.groupby("player_id")["season_start_year"].agg(set).to_dict()
    # master-level: ultima riga registry per master + insieme ruoli + stagioni
    last = reg.sort_values("stagione").drop_duplicates("master_id", keep="last")
    roles = reg.groupby("master_id")["ruolo"].agg(set)
    m_seasons = reg.groupby("master_id")["stagione"].agg(
        lambda ss: set(int(s[:4]) for s in ss))
    out = []
    n_ok = 0
    for r in last.itertuples(index=False):
        surname, ini = split_registry_name(r.nome)
        surname = apply_alias(surname)
        ini_c = ini.replace(" ", "")
        cands = list(by_ln.get(surname, []))
        method = "ln_exact"
        if not cands:
            # cognomi composti / nomi d'arte: subset di token sul nome completo TM
            stoks = set(t for t in surname.split() if len(t) >= 3)
            if stoks:
                cands = [pd.Series(row._asdict()) for row in tm.itertuples(index=False)
                         if stoks <= set(row.full_norm.split())]
                method = "full_subset"
        if not cands:
            # TM a volte tronca il cognome composto ('Jens Stryger'): prova i singoli token
            seen = {}
            for t in surname.split():
                if len(t) >= 4:
                    for c in by_ln.get(t, []):
                        seen[c.player_id] = c
            if len(seen) == 1:
                cands = list(seen.values())
                method = "ln_token"
        if not cands:
            from rapidfuzz import fuzz
            scored = sorted(((fuzz.ratio(surname, ln), ln) for ln in by_ln), reverse=True)[:3]
            if scored and scored[0][0] >= 90:
                cands = list(by_ln[scored[0][1]])
                method = "ln_fuzzy"
        if len(cands) > 1 and ini_c:
            f = [c for c in cands if str(c.fn_norm).replace(" ", "").startswith(ini_c)
                 or ini_c.startswith(str(c.fn_norm).replace(" ", "")[:1] or "#")]
            if len(f) >= 1:
                # prima i match con prefisso pieno dell'iniziale
                full_pref = [c for c in f if str(c.fn_norm).replace(" ", "").startswith(ini_c)]
                cands = full_pref or f
        if len(cands) > 1:
            rl = roles.get(r.master_id, set())
            f = [c for c in cands if TM_POS_TO_ROLE.get(c.position) in rl]
            if len(f) >= 1:
                cands = f
        if len(cands) > 1:
            # disambigua con le presenze IT1: il candidato deve aver giocato
            # in una delle stagioni in cui il master e' a listone
            ms = m_seasons.get(r.master_id, set())
            f = [c for c in cands if tm_seasons.get(c.player_id, set()) & ms]
            if len(f) == 1:
                cands = f
                method += "+appearances"
        if len(cands) > 1 and not ini:
            recent = max(c.last_season for c in cands)
            f = [c for c in cands if c.last_season == recent]
            if len(f) == 1:
                cands = f
                method += "+recent"
        if len(cands) == 1:
            c = cands[0]
            # guardia eta' (fix round 1, audit Difetto 6): il candidato TM deve avere
            # un'eta' plausibile in TUTTE le stagioni a listone del master (Bleve 1995
            # matchato al Bleve 2008 -> eta' 15.2: rifiutato, meglio NaN che sbagliato).
            dob = pd.to_datetime(c.date_of_birth, errors="coerce")
            ms = m_seasons.get(r.master_id, set())
            if pd.notna(dob) and ms:
                ages = [(pd.Timestamp(yy, 9, 1) - dob).days / 365.25 for yy in ms]
                amin, amax = min(ages), max(ages)
                # eta' impossibile -> rifiuto; eta' da wonderkid (<16.5) -> ok solo se
                # il candidato TM ha presenze Serie A in una stagione a listone del
                # master (Camarda/Amey veri passano, Bleve 2008/Cisse' 2006 no).
                bad = amin < 14.5 or amax > 44
                if not bad and amin < 16.5:
                    bad = not (tm_seasons.get(c.player_id, set()) & ms)
                if bad:
                    LOG.add("transfermarkt", r.stagione, r.nome,
                            f"sq={r.squadra} ruolo={r.ruolo} eta_min={amin:.1f}",
                            "rejected_age_bound",
                            [(c.full_norm, str(c.date_of_birth), str(c.position)[:1], 0)])
                    continue
            out.append(dict(master_id=r.master_id, nome=r.nome, tm_player_id=int(c.player_id),
                            date_of_birth=c.date_of_birth, method=method))
            n_ok += 1
        else:
            LOG.add("transfermarkt", r.stagione, r.nome, f"sq={r.squadra} ruolo={r.ruolo}",
                    "ambiguous" if cands else "no_surname",
                    [(c.full_norm, str(c.last_season), str(c.position)[:1], 100)
                     for c in cands[:3]])
    df = pd.DataFrame(out)
    # guardia tm_player_id condiviso (fix round 1): lo stesso giocatore TM non puo'
    # essere l'eta' di due master diversi (Arena / Arena A.): tiene il master la cui
    # iniziale e' compatibile col nome TM, gli altri diventano unmatched.
    from rapidfuzz import fuzz as _fuzz
    fn_by_id = dict(zip(tm.player_id, tm.fn_norm))
    ln_by_id = dict(zip(tm.player_id, tm.ln_norm))
    drop_idx = []
    for tmid, g in df[df.tm_player_id.duplicated(keep=False)].groupby("tm_player_id"):
        fn = str(fn_by_id.get(tmid, "")).replace(" ", "")
        ln = str(ln_by_id.get(tmid, ""))
        scored = []
        for i in g.index:
            surname, ini = split_registry_name(df.at[i, "nome"])
            ini_c = ini.replace(" ", "")
            # iniziale: +1 se combacia col nome TM, -1 se confligge, 0 se assente;
            # a pari iniziale vince il cognome piu' simile al cognome TM
            # (Chiesa vs Chiesa M. -> Federico Chiesa; Musacchio vs Mustacchio;
            #  McTominay vs Scott)
            ini_sc = 0 if not ini_c else (1 if fn.startswith(ini_c) else -1)
            scored.append((i, (ini_sc, _fuzz.ratio(surname, ln))))
        scored.sort(key=lambda t: t[1], reverse=True)
        if scored[0][1] > scored[1][1]:
            losers = [i for i, _ in scored[1:]]
        else:  # pari merito: irrisolvibile, fuori tutti
            losers = [i for i, _ in scored]
        drop_idx.extend(losers)
        for i in losers:
            LOG.add("transfermarkt", "tutte", df.at[i, "nome"],
                    f"tm_player_id={tmid} conteso", "rejected_dup_tm_id",
                    [(str(fn_by_id.get(tmid, "")), str(tmid), "", 0)])
    if drop_idx:
        print(f"transfermarkt: {len(drop_idx)} master rimossi per tm_player_id conteso")
        df = df.drop(index=drop_idx)
        n_ok = len(df)
    print(f"transfermarkt: {n_ok}/{len(last)} master match ({n_ok/len(last)*100:.1f}%)")
    return df


def main():
    MATCH_DIR.mkdir(parents=True, exist_ok=True)
    reg = load_registry()
    idx_by_season = season_indexes(reg)

    # snapshot inizio settembre: giornata con data rilevazione piu' vicina al 1/9
    dates = pd.read_csv(RAW / "quotazioni" / "fantasoccer_date_rilevazioni.csv")
    dates["dt"] = pd.to_datetime(dates["data_rilevazione"], format="%d/%m/%Y")
    fs_seasons = {}
    for s in ["2021-22", "2023-24", "2024-25", "2025-26"]:
        d = dates[dates.stagione == s].copy()
        sept1 = pd.Timestamp(int("20" + s[:2]) if False else int(s[:4]), 9, 1)
        # solo giornate con file scaricato
        d = d[d.giornata.map(lambda g: (RAW / "quotazioni" / f"fantasoccer_{s}_g{int(g):02d}.csv").exists())]
        d["dist"] = (d.dt - sept1).abs()
        best = d.sort_values("dist").iloc[0]
        fs_seasons[s] = [int(best.giornata)]
        print(f"snapshot fanta.soccer {s}: g{int(best.giornata)} ({best.data_rilevazione})")

    mv, team_maps = match_voti(idx_by_season)
    mfs = match_fantasoccer(idx_by_season, fs_seasons)
    mw = match_wayback(idx_by_season)
    mg = match_ge(idx_by_season)
    mu = match_understat(idx_by_season, reg)
    mt = match_tm(reg)

    mv.to_csv(MATCH_DIR / "map_voti.csv", index=False, encoding="utf-8")
    mfs.to_csv(MATCH_DIR / "map_fantasoccer.csv", index=False, encoding="utf-8")
    mw.to_csv(MATCH_DIR / "map_wayback.csv", index=False, encoding="utf-8")
    mg.to_csv(MATCH_DIR / "map_ge.csv", index=False, encoding="utf-8")
    mu.to_csv(MATCH_DIR / "map_understat.csv", index=False, encoding="utf-8")
    mt.to_csv(MATCH_DIR / "map_tm.csv", index=False, encoding="utf-8")
    with open(MATCH_DIR / "team_maps.json", "w", encoding="utf-8") as f:
        json.dump(team_maps, f, ensure_ascii=False, indent=1)
    with open(MATCH_DIR / "fs_snapshot.json", "w", encoding="utf-8") as f:
        json.dump(fs_seasons, f)

    rep = LOG.to_df()
    rep.to_csv(PROC / "unmatched_report.csv", index=False, encoding="utf-8")
    print(f"\nunmatched_report.csv: {len(rep)} righe")
    if len(rep):
        print(rep.groupby(["fonte", "esito"]).size().to_string())


if __name__ == "__main__":
    main()
