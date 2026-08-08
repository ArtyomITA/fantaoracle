# -*- coding: utf-8 -*-
"""Quality check on emitted prezzi_*.csv files."""
import glob
import os
import pandas as pd

OUT_DIR = r"data\raw\wayback_prices"

for path in sorted(glob.glob(os.path.join(OUT_DIR, "prezzi_*.csv"))):
    df = pd.read_csv(path, dtype=str)
    n = len(df)
    price_cols = ["p350_8sq", "p350_10sq", "p500_8sq", "p500_10sq"]
    has_price = df[price_cols].notna().any(axis=1).sum()
    per_col = {c: int(df[c].notna().sum()) for c in price_cols}
    roles = df["ruolo"].fillna("?").value_counts().to_dict()
    teams = df["squadra"].nunique()
    empty_role = int((df["ruolo"].isna() | (df["ruolo"] == "")).sum())
    empty_name = int((df["nome"].isna() | (df["nome"] == "")).sum())
    dup = int(df.duplicated(subset=["squadra", "nome"]).sum())
    # top 3 by p350_8sq numeric
    d2 = df.copy()
    d2["p"] = pd.to_numeric(d2["p350_8sq"], errors="coerce")
    top = d2.nlargest(3, "p")[["nome", "squadra", "p"]].values.tolist()
    mv_n = int(pd.to_numeric(df["mv"], errors="coerce").notna().sum())
    pres_n = int(pd.to_numeric(df["presenze"], errors="coerce").notna().sum())
    print(f"{os.path.basename(path)}")
    print(f"  rows={n} con_prezzo={has_price} per_col={per_col} mv={mv_n} pres={pres_n}")
    print(f"  ruoli={roles} ruolo_vuoto={empty_role} nome_vuoto={empty_name} dup={dup} squadre={teams}")
    print(f"  top p350_8: {top}")
