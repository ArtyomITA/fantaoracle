# -*- coding: utf-8 -*-
"""Test del parser sui due file principali + controllo incrociato con verifica manuale."""
from ge_parser import parse_file

FILES = [
    (r"E:\claudecode pesante\fonti_prezzi\gruppoesperti_prezzi_aste_reali_2024-25.xlsx",
     "gruppoesperti_prezzi_aste_reali_2024-25.xlsx"),
    (r"E:\claudecode pesante\fonti_prezzi\gruppoesperti_prezzi_aste_reali_2021-22circa.xlsx",
     "gruppoesperti_prezzi_aste_reali_2021-22circa.xlsx"),
]

for path, label in FILES:
    rows, stats = parse_file(path, label)
    print("=" * 70)
    print(label)
    print("ancore:", stats["anchors"], "| aste popolate:", stats["populated_auctions"],
          "| blocchi vuoti:", stats["empty_blocks"], "| righe senza prezzo:", stats["rows_no_price"])
    print("righe totali:", len(rows))
    print("prime 3 aste:", stats["auction_meta"][:3])
    print("ultime 2 aste:", stats["auction_meta"][-2:])
    # cross-check asta 2
    a2 = [r for r in rows if r["auction_id"] == 2]
    from collections import Counter
    print("asta 2: righe per ruolo:", Counter(r["ruolo"] for r in a2),
          "| comp:", a2[0]["componenti"], "| cred:", a2[0]["crediti_tot"],
          "| mod:", repr(a2[0]["modificatore"]), "| per:", a2[0]["periodo"])
    print("asta 2 esempio riga:", a2[0])
    # sanity: pct_budget
    bad_pct = [r for r in rows if r["pct_budget"] is not None and not (0 <= r["pct_budget"] <= 1)]
    print("righe con pct_budget fuori [0,1]:", len(bad_pct), bad_pct[:3])
    # prezzi anomali
    neg = [r for r in rows if isinstance(r["prezzo"], (int, float)) and r["prezzo"] < 0]
    print("prezzi negativi:", len(neg), neg[:3])
