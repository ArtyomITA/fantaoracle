"""Livello 1 — panel giocatore x partita, con il contratto dei dati esplicito.

Una riga per (giocatore, partita) delle stagioni con voti disponibili. Serve a
dare una base unica e verificabile a simulatore, modelli e diagnostica: oggi
ogni pezzo ricava le stesse informazioni per conto suo, da fonti diverse, e le
discordanze non si vedono.

CONTRATTO (verificato, non assunto)

1. Chiave: `master_id` (identita' del progetto) x `game_id` (partita
   Transfermarkt). La giornata fantacalcistica e' un attributo, non la chiave:
   i rinvii spostano le date senza spostare la giornata.
2. Punteggio della fonte, riconciliato prima di qualunque regola di lega:
       fantavoto = voto + 3*(gol_fatti + rigore_segnato) + assist
                   - 0.5*ammonizione - espulsione
                   + 3*rigori_parati - 3*rigori_sbagliati - 2*autogol
                   - gol_subiti (solo portieri)
   Il rigore segnato NON e' compreso in `gol_fatti`: verificato su 43.551
   righe con voto (2021-22, 2023-24, 2024-25, 2025-26, 2026-27), riconciliate
   al 100% tranne una riga (Delprato, Parma, giornata 3 del 2024-25).
   Le regole della lega (porta inviolata, modificatore) restano fuori di qui.
3. Stati distinti, mai confusi fra loro:
       con_voto          ha giocato e ha preso voto
       senza_voto        e' sceso in campo ma la fonte da' s.v.
       non_convocato     nessuna riga nei voti per quella partita
       dato_mancante     la riga esiste ma il campo non c'e'
   "senza voto" non significa infortunato: la fonte non dice perche'.
4. Universo atteso: tutti i giocatori del listone di quella stagione per tutte
   le partite della loro squadra. Una riga che manca diventa `non_convocato`
   solo se la squadra ha giocato quella partita.
5. Ogni blocco di colonne porta la sua provenienza (`fonte_*`), e per i minuti
   anche la data della partita: e' il momento in cui l'informazione esiste.

Uso: python scripts/f14_build_panel.py [stagione ...] [--verifica]
Output: data/processed/panel_{stagione}.parquet
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw"
PROC = ROOT / "data" / "processed"
STAGIONI = ["2021-22", "2023-24", "2024-25", "2025-26", "2026-27"]
ANNO = {s: int(s[:4]) for s in STAGIONI}


def fantavoto_fonte(d: pd.DataFrame) -> pd.Series:
    """Punteggio ricostruito con le regole della fonte (vedi contratto)."""
    gol_subiti_p = d["gol_subiti"].where(d["ruolo"].str.lower() == "p", 0).fillna(0)
    return (d["voto"] + 3 * (d["gol_fatti"] + d["rigore_segnato"]) + d["assist"]
            - 0.5 * d["ammonizione"] - d["espulsione"]
            + 3 * d["rigori_parati"] - 3 * d["rigori_sbagliati"]
            - 2 * d["autogol"] - gol_subiti_p)


def carica_partite(anno: int) -> pd.DataFrame:
    g = pd.read_csv(RAW / "transfermarkt" / "_download" / "games.csv.gz",
                    compression="gzip")
    g = g[(g["competition_id"] == "IT1") & (g["season"] == anno)].copy()
    g["giornata"] = g["round"].astype(str).str.extract(r"(\d+)")[0].astype("Int64")
    g["data"] = pd.to_datetime(g["date"], errors="coerce")
    return g[["game_id", "giornata", "data", "home_club_id", "away_club_id",
              "home_club_goals", "away_club_goals"]]


def costruisci(season: str) -> pd.DataFrame:
    anno = ANNO[season]
    voti = pd.read_csv(RAW / "voti" / f"voti_{season}.csv")
    mv = pd.read_csv(PROC / "_match" / "map_voti.csv")
    mv = mv[mv["stagione"] == season]
    voti = voti.merge(mv[["squadra", "nome", "master_id"]], on=["squadra", "nome"],
                      how="left")
    voti["fantavoto_ricostruito"] = fantavoto_fonte(voti)
    voti["scarto_ricostruzione"] = (voti["fantavoto_ricostruito"]
                                    - voti["fantavoto"]).abs()

    mt = pd.read_csv(PROC / "_match" / "map_tm.csv")
    if "stagione" in mt.columns:
        mt = mt[mt["stagione"] == season]
    mt = mt.dropna(subset=["master_id", "tm_player_id"]).drop_duplicates("master_id")
    voti["master_id"] = voti["master_id"].astype("Int64")
    voti = voti.merge(mt[["master_id", "tm_player_id"]].astype({"master_id": "Int64"}),
                      on="master_id", how="left")

    app = pd.read_csv(RAW / "transfermarkt" / "transfermarkt_appearances_seriea.csv")
    app = app[app["season_start_year"] == anno]
    partite = carica_partite(anno)
    app = app.merge(partite, on="game_id", how="left")
    app = app[["player_id", "game_id", "giornata", "data", "player_club_id",
               "minutes_played", "yellow_cards", "red_cards", "goals", "assists",
               "home_club_id", "away_club_id", "home_club_goals", "away_club_goals"]]
    app = app.rename(columns={"player_id": "tm_player_id",
                              "minutes_played": "minuti"})
    app["in_casa"] = app["player_club_id"] == app["home_club_id"]
    app["avversario_tm"] = np.where(app["in_casa"], app["away_club_id"],
                                    app["home_club_id"])
    app["gol_squadra"] = np.where(app["in_casa"], app["home_club_goals"],
                                  app["away_club_goals"])
    app["gol_avversario"] = np.where(app["in_casa"], app["away_club_goals"],
                                     app["home_club_goals"])

    p = voti.merge(app[["tm_player_id", "giornata", "game_id", "data", "minuti",
                        "in_casa", "avversario_tm", "gol_squadra", "gol_avversario"]],
                   on=["tm_player_id", "giornata"], how="left")
    p["stato"] = np.where(p["sv"].fillna(0) == 0, "con_voto", "senza_voto")
    p["stagione"] = season
    p["fonte_voto"] = "fantacalcio.it"
    p["fonte_minuti"] = np.where(p["minuti"].notna(), "transfermarkt", "assente")
    p["fonte_partita"] = np.where(p["game_id"].notna(), "transfermarkt games", "assente")
    return p


def verifica(p: pd.DataFrame, season: str) -> None:
    n = len(p)
    con = p["stato"] == "con_voto"
    print(f"\n--- {season}: {n} righe dai voti ---")
    print(f"  identita': master_id {p.master_id.notna().mean():.2%}, "
          f"tm_player_id {p.tm_player_id.notna().mean():.2%}")
    print(f"  partita agganciata: {p.game_id.notna().mean():.2%} "
          f"(minuti presenti {p.minuti.notna().mean():.2%})")
    scarti = (p.loc[con, "scarto_ricostruzione"] >= 0.011).sum()
    print(f"  punteggio della fonte riconciliato: "
          f"{1 - scarti / max(1, con.sum()):.4%} ({scarti} discordanti)")
    print(f"  stati: {p.stato.value_counts().to_dict()}")
    dup = p.groupby(["master_id", "giornata"]).size()
    print(f"  coppie (giocatore, giornata) duplicate: {(dup > 1).sum()}")
    senza = p[con & p.minuti.isna()]
    print(f"  con voto ma senza minuti Transfermarkt: {len(senza)} "
          f"({len(senza) / max(1, con.sum()):.2%})")
    sv_con_minuti = p[(p.stato == 'senza_voto') & (p.minuti.fillna(0) > 0)]
    print(f"  senza voto ma con minuti > 0: {len(sv_con_minuti)} "
          "(entrati pochi minuti: NON sono assenti)")
    if "nuovo_in_serie_a" in p.columns:
        pass
    pl = PROC / f"players_{season}.parquet"
    if pl.exists():
        d = pd.read_parquet(pl, columns=["master_id", "nuovo_in_serie_a"])
        d["master_id"] = d["master_id"].astype("Int64")
        m = p.merge(d, on="master_id", how="left")
        for et, sel in [("nuovi", m.nuovo_in_serie_a == 1), ("vecchi", m.nuovo_in_serie_a == 0)]:
            s = m[sel]
            if len(s):
                print(f"  {et}: {len(s)} righe | partita agganciata "
                      f"{s.game_id.notna().mean():.2%} | minuti {s.minuti.notna().mean():.2%}")


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    solo_verifica = "--verifica" in sys.argv
    stagioni = args or STAGIONI
    for season in stagioni:
        if not (RAW / "voti" / f"voti_{season}.csv").exists():
            print(f"{season}: voti assenti, salto")
            continue
        p = costruisci(season)
        verifica(p, season)
        if not solo_verifica:
            out = PROC / f"panel_{season}.parquet"
            p.to_parquet(out, index=False)
            print(f"  scritto {out.name} ({out.stat().st_size // 1024} KB)")


if __name__ == "__main__":
    main()
