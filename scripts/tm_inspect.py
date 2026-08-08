"""Ispezione rapida degli schemi dei csv.gz scaricati da transfermarkt-datasets (R2)."""
import pandas as pd

DL = r"data\raw\transfermarkt\_download"

for name in ["players", "player_valuations", "transfers", "appearances"]:
    path = rf"{DL}\{name}.csv.gz"
    df = pd.read_csv(path, nrows=5000, low_memory=False)
    print(f"===== {name} =====")
    print("cols:", list(df.columns))
    print(df.head(3).to_string())
    print()
