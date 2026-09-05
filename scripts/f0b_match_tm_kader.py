# -*- coding: utf-8 -*-
"""Join rosa Transfermarkt 2026/27 (kader_2026.csv) -> listone 2026-27 (registry).

Fix audit: i nuovi in Serie A non hanno presenze IT1 nel dump TM, quindi match_tm
(f0b_match) non li conferma -> eta'/valore NaN. Qui il match e' cognome
normalizzato + squadra (+ iniziale se ambiguo) con le guardie di f0b_lib
(P vs movimento strutturale: indici separati; conflitto squadra/ruolo; eta').

Output:
  data/processed/_match/map_tm_kader_2026.csv
      master_id, tm_player_id, date_of_birth, market_value_eur, club_precedente, ...
  data/processed/_match/unmatched_tm_kader_2026.csv
      non-match nelle due direzioni con i 3 candidati

Uso: python scripts/f0b_match_tm_kader.py
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
from rapidfuzz import fuzz

sys.path.insert(0, str(Path(__file__).parent))
from f0b_lib import (MATCH_DIR, PROC, RAW, SeasonIndex, match_given_surname,  # noqa: E402
                     norm, pick_best_per_master, split_registry_name)
from scrape_tm_kader import club_sigla  # noqa: E402

STAGIONE = "2026-27"
YEAR = 2026
KADER = RAW / "transfermarkt" / f"kader_{YEAR}.csv"
OUT = MATCH_DIR / f"map_tm_kader_{YEAR}.csv"
OUT_UNM = MATCH_DIR / f"unmatched_tm_kader_{YEAR}.csv"
SEPT1 = pd.Timestamp(YEAR, 9, 1)
ETA_MIN, ETA_MAX = 15.0, 45.0


# lettere senza decomposizione NFKD (norm le trasformerebbe in spazio): Højlund -> HOJLUND
TRANSLIT = str.maketrans({"ø": "o", "Ø": "O", "đ": "d", "Đ": "D", "ł": "l", "Ł": "L",
                          "ß": "ss", "æ": "ae", "Æ": "AE", "œ": "oe", "Œ": "OE",
                          "ı": "i", "ħ": "h", "þ": "th", "ð": "d", "Ð": "D"})


def split_tm_name(nome: str):
    """'Filip Stankovic' -> ('FILIP', ['STANKOVIC']); 'Dodo' -> ('', ['DODO'])."""
    toks = norm(str(nome).translate(TRANSLIT)).split()
    if len(toks) > 1:
        return toks[0], toks[1:]
    return "", toks


def match_row(idx: SeasonIndex, given, surn, sigla, prev_sigla):
    """Pass 1: con squadra TM. Pass 2 (solo se fallisce): senza squadra, accettato
    solo se la squadra registry e' il club precedente TM (trasferimento dopo il
    listone) o se il cognome e' unico nel listone con iniziale compatibile."""
    m = match_given_surname(idx, given, surn, sigla=sigla)
    if m["master_id"] is not None:
        return m
    m1 = m
    m2 = match_given_surname(idx, given, surn, sigla=None)
    if m2["master_id"] is None:
        return m1
    full, sq, ru, _ = m2["candidates"][0]
    cand = next(r for r in idx.rows if r["master_id"] == m2["master_id"])
    ini_tm = given[:1]
    ini_ok = (not cand["initial"]) or (not ini_tm) or cand["initial"].startswith(ini_tm)
    if prev_sigla and sq == prev_sigla and ini_ok:
        m2["method"] += "|noteam_prev"
        return m2
    if len(idx.by_surname.get(cand["surname"], [])) == 1 and ini_ok and cand["initial"]:
        m2["method"] += "|noteam_unique"
        return m2
    m1["method"] = f"rejected_noteam:{m2['method']}"
    m1["candidates"] = m2["candidates"]
    return m1


def main():
    MATCH_DIR.mkdir(parents=True, exist_ok=True)
    reg = pd.read_csv(PROC / "registry.csv")
    reg = reg[reg.stagione == STAGIONE].copy()
    kad = pd.read_csv(KADER)
    idx_p = SeasonIndex(reg[reg.ruolo == "P"], STAGIONE)
    idx_m = SeasonIndex(reg[reg.ruolo != "P"], STAGIONE)
    idx_all = SeasonIndex(reg, STAGIONE)

    out, unm = [], []
    for r in kad.itertuples(index=False):
        given, surn = split_tm_name(r.nome_completo)
        idx = {"P": idx_p, "": idx_all}.get(r.ruolo, idx_m)
        prev_sigla = club_sigla(str(r.club_precedente), int(r.club_precedente_id)
                                if pd.notna(r.club_precedente_id) else -1)
        m = match_row(idx, given, surn, r.squadra, prev_sigla)
        ctx = f"sq={r.squadra} ruolo_tm={r.ruolo_tm} dob={r.date_of_birth}"
        if m["master_id"] is None:
            unm.append(_unm("tm->registry", r.nome_completo, r.tm_player_id, ctx,
                            m["method"], m["candidates"]))
            continue
        dob = pd.to_datetime(r.date_of_birth, errors="coerce")
        eta = (SEPT1 - dob).days / 365.25 if pd.notna(dob) else float("nan")
        if pd.notna(eta) and not (ETA_MIN < eta < ETA_MAX):
            unm.append(_unm("tm->registry", r.nome_completo, r.tm_player_id, ctx,
                            f"rejected_age:{eta:.1f}", m["candidates"]))
            continue
        out.append(dict(master_id=int(m["master_id"]), tm_player_id=int(r.tm_player_id),
                        date_of_birth=r.date_of_birth, market_value_eur=r.market_value_eur,
                        club_precedente=r.club_precedente, da_club=r.da_club, movimento_tm=r.movimento_tm,
                        nome_tm=r.nome_completo, squadra_tm=r.squadra, ruolo_tm=r.ruolo_tm,
                        nazionalita=r.nazionalita, method=m["method"]))
    df = pd.DataFrame(out)

    # un master <- piu' righe TM: vince la qualita' del match, pari merito fuori
    dupm = df[df.master_id.duplicated(keep=False)]
    if len(dupm):
        df, n_tie = pick_best_per_master(df)
        for mid, g in dupm.groupby("master_id"):
            if mid not in set(df.master_id):
                for x in g.itertuples(index=False):
                    unm.append(_unm("tm->registry", x.nome_tm, x.tm_player_id,
                                    f"sq={x.squadra_tm}", "rejected_dup_master(tie)",
                                    [(str(mid), "", "", 0)]))
        print(f"master con piu' righe TM: {dupm.master_id.nunique()} (pari merito scartati: {n_tie})")
    df = df.merge(reg[["master_id", "nome", "squadra", "ruolo"]], on="master_id", how="left")

    # registry -> tm: listone senza match, con i 3 candidati kader piu' simili
    kad["ln_tm"] = kad.nome_completo.map(lambda s: " ".join(split_tm_name(s)[1]))
    matched = set(df.master_id)
    for r in reg.itertuples(index=False):
        if r.master_id in matched:
            continue
        surname, ini = split_registry_name(r.nome)
        pool = kad[kad.ruolo.eq("P") == (r.ruolo == "P")].copy()
        sc = pool.assign(score=pool.ln_tm.map(lambda x: fuzz.ratio(surname, x))
                         + 5 * (pool.squadra == r.squadra)).nlargest(3, "score")
        unm.append(_unm("registry->tm", r.nome, r.master_id, f"sq={r.squadra} ruolo={r.ruolo}",
                        "no_match",
                        [(x.nome_completo, x.squadra, x.ruolo, round(x.score)) for x in sc.itertuples()]))

    cols = ["master_id", "tm_player_id", "date_of_birth", "market_value_eur", "club_precedente",
            "da_club", "movimento_tm", "nome", "nome_tm", "squadra", "squadra_tm", "ruolo", "ruolo_tm",
            "nazionalita", "method"]
    df = df[cols].sort_values(["squadra", "nome"])
    assert df.master_id.is_unique and df.tm_player_id.is_unique
    df.to_csv(OUT, index=False, encoding="utf-8")
    pd.DataFrame(unm).to_csv(OUT_UNM, index=False, encoding="utf-8")

    # --- report
    n = len(reg)
    print(f"kader {YEAR}: {len(kad)} giocatori TM | match {len(df)}/{n} listone {STAGIONE} "
          f"({len(df)/n*100:.1f}%) | TM senza master: {len(kad)-len(df)}")
    pp = PROC / f"players_{STAGIONE}.parquet"
    if pp.exists():
        pl = pd.read_parquet(pp, columns=["master_id", "nuovo_in_serie_a", "eta", "tm_value_eur"])
        nuovi = pl[pl.nuovo_in_serie_a == 1]
        ok = nuovi.master_id.isin(df.master_id).sum()
        print(f"nuovi in Serie A: match {ok}/{len(nuovi)} ({ok/len(nuovi)*100:.1f}%) | "
              f"di cui con eta' NaN nel parquet attuale: "
              f"{(nuovi.eta.isna() & nuovi.master_id.isin(df.master_id)).sum()}/{nuovi.eta.isna().sum()}")
    print("metodi:", df.method.str.split("+").str[0].str.split("|").str[-1].value_counts().to_dict())
    nt = df[df.method.str.contains("noteam")]
    if len(nt):
        print(f"pass 2 senza squadra ({len(nt)}):")
        for x in nt.itertuples(index=False):
            print(f"   {x.nome:22s} {x.squadra} <- {x.nome_tm:24s} {x.squadra_tm} "
                  f"prec={x.club_precedente} [{x.method}]")
    print(f"-> {OUT.name}, {OUT_UNM.name} ({len(unm)} righe)")


def _unm(direzione, chiave, key_id, contesto, esito, cands):
    c = list(cands)[:3] + [("", "", "", "")] * 3
    row = dict(direzione=direzione, chiave=chiave, id=key_id, contesto=contesto, esito=esito)
    for i in range(3):
        full, sq, ru, sc = c[i]
        row[f"cand{i+1}"] = f"{full} ({sq} {ru}) [{sc}]" if full else ""
    return row


if __name__ == "__main__":
    main()
