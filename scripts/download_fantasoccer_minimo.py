# -*- coding: utf-8 -*-
"""Run mirato: garantisce le giornate minime richieste (1,2,3,4,19,38) per ogni stagione
+ scrive subito fantasoccer_date_rilevazioni.csv. Idempotente: salta i file gia' presenti
(il download completo in background salta a sua volta i file creati qui)."""
import sys, time, random
sys.path.insert(0, r"scripts")
import os
import pandas as pd
from download_fantasoccer import SEASONS, label, parse_season_page, download_giornata, OUT

TARGET = [1, 2, 3, 4, 19, 38]
dates_rows = []
for season in SEASONS:
    lab = label(season)
    giornate, date_map = parse_season_page(season)
    if giornate is None:
        print(f"{season}: pagina irraggiungibile", flush=True)
        continue
    for g in sorted(date_map):
        dates_rows.append({"stagione": lab, "giornata": g, "data_rilevazione": date_map[g]})
    for g in TARGET:
        if g not in giornate:
            print(f"{season} g{g}: non disponibile sul sito", flush=True)
            continue
        res = download_giornata(season, g)
        print(f"{season} g{g:02d}: {res}", flush=True)
        if res != "skip":
            time.sleep(random.uniform(1, 2.5))
    time.sleep(random.uniform(1, 2))

if dates_rows:
    pd.DataFrame(dates_rows).to_csv(os.path.join(OUT, "fantasoccer_date_rilevazioni.csv"),
                                    index=False, encoding="utf-8", lineterminator="\n")
    print("date_rilevazioni salvate:", len(dates_rows), "righe", flush=True)
