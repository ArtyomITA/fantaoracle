"""
Processa i csv.gz di transfermarkt-datasets (dcaribou, via bucket R2 pubblico)
e produce i 4 CSV filtrati per FantaBot.

Filtri:
- appearances: competition_id == IT1, date >= 2019-07-01 (stagioni 2019/20 -> 2025/26+)
- set giocatori "Serie A": chi ha almeno una presenza IT1 dal 2019-07-01
  UNIONE chi milita ATTUALMENTE in un club di Serie A (current_club_domestic_competition_id == IT1,
  cattura i nuovi acquisti estate 2026 senza presenze IT1)
- player_valuations: storico completo, filtrato al set giocatori Serie A
- players: anagrafica filtrata al set giocatori Serie A
- transfers: finestre estive (giu-set) 2020..2025, mondiale (nessun filtro club)
"""
import pandas as pd

DL = r"data\raw\transfermarkt\_download"
OUT = r"data\raw\transfermarkt"

# ---------- appearances ----------
app = pd.read_csv(rf"{DL}\appearances.csv.gz", low_memory=False, parse_dates=["date"])
print(f"appearances mondiale: {len(app):,} righe")

# stagione autoritativa dalla tabella games (regola mese>=7 fallirebbe sul
# finale COVID della 2019/20 giocato a lug-ago 2020)
games = pd.read_csv(rf"{DL}\games.csv.gz", low_memory=False, usecols=["game_id", "season", "competition_id"])
game_season = games.set_index("game_id")["season"]

app_it1 = app[app["competition_id"] == "IT1"].copy()
app_it1["season_start_year"] = app_it1["game_id"].map(game_season)
missing_season = app_it1["season_start_year"].isna().sum()
if missing_season:
    print(f"ATTENZIONE: {missing_season} presenze senza season in games -> fallback su data")
    fb = app_it1["season_start_year"].isna()
    app_it1.loc[fb, "season_start_year"] = app_it1.loc[fb, "date"].apply(
        lambda d: d.year if d.month >= 7 else d.year - 1
    )
app_it1["season_start_year"] = app_it1["season_start_year"].astype(int)
app_it1 = app_it1[app_it1["season_start_year"] >= 2019]
app_it1 = app_it1.sort_values(["date", "game_id", "player_id"])
print(f"appearances IT1 2019+: {len(app_it1):,} righe, stagioni {sorted(app_it1['season_start_year'].unique())}")
print(f"date range: {app_it1['date'].min().date()} -> {app_it1['date'].max().date()}")

ids_app = set(app_it1["player_id"].unique())
print(f"giocatori con presenze IT1 2019+: {len(ids_app):,}")

# ---------- players ----------
players = pd.read_csv(rf"{DL}\players.csv.gz", low_memory=False)
print(f"\nplayers mondiale: {len(players):,} righe")

# current_club_domestic_competition_id == IT1 da solo include anche ritirati il cui
# ultimo club era in Serie A (es. Klose/Lazio): serve anche last_season recente
ids_current_it1 = set(
    players.loc[
        (players["current_club_domestic_competition_id"] == "IT1")
        & (players["last_season"] >= 2025),
        "player_id",
    ]
)
print(f"giocatori attualmente in club IT1: {len(ids_current_it1):,}")

seriea_ids = ids_app | ids_current_it1
print(f"set Serie A (unione): {len(seriea_ids):,}")

players_out = players[players["player_id"].isin(seriea_ids)].copy()
# data nascita: solo la parte data (nel sorgente e' 'YYYY-MM-DD 00:00:00')
players_out["date_of_birth"] = pd.to_datetime(players_out["date_of_birth"], errors="coerce").dt.date
players_out["contract_expiration_date"] = pd.to_datetime(
    players_out["contract_expiration_date"], errors="coerce"
).dt.date
players_out = players_out.sort_values("player_id")
print(f"players filtrati: {len(players_out):,} righe")

# ---------- player_valuations ----------
val = pd.read_csv(rf"{DL}\player_valuations.csv.gz", low_memory=False, parse_dates=["date"])
print(f"\nvaluations mondiale: {len(val):,} righe")
val_out = val[val["player_id"].isin(seriea_ids)].copy()
val_out["date"] = val_out["date"].dt.date
val_out = val_out.sort_values(["player_id", "date"])
print(f"valuations filtrate (storico completo, giocatori Serie A): {len(val_out):,} righe")

# ---------- transfers ----------
tr = pd.read_csv(rf"{DL}\transfers.csv.gz", low_memory=False, parse_dates=["transfer_date"])
print(f"\ntransfers mondiale: {len(tr):,} righe")
mask = (
    tr["transfer_date"].dt.year.between(2020, 2025)
    & tr["transfer_date"].dt.month.between(6, 9)
)
tr_out = tr[mask].copy()
tr_out["transfer_date"] = tr_out["transfer_date"].dt.date
tr_out = tr_out.sort_values(["transfer_date", "player_id"])
print(f"transfers estati (giu-set) 2020-2025: {len(tr_out):,} righe")
per_anno = tr_out.groupby(pd.to_datetime(tr_out["transfer_date"]).dt.year).size()
print(per_anno.to_string())

# ---------- export ----------
exports = {
    "transfermarkt_players.csv": players_out,
    "transfermarkt_valuations_seriea.csv": val_out,
    "transfermarkt_transfers.csv": tr_out,
    "transfermarkt_appearances_seriea.csv": app_it1.assign(date=app_it1["date"].dt.date),
}
print()
for fname, df in exports.items():
    path = rf"{OUT}\{fname}"
    df.to_csv(path, index=False, encoding="utf-8")
    print(f"scritto {fname}: {len(df):,} righe, {len(df.columns)} colonne")
