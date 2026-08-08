# -*- coding: utf-8 -*-
"""Costruisce aste_reali_tidy.csv + REPORT.md dai file GruppoEsperti (principali + extra)."""
import json
import os
from collections import Counter

import pandas as pd

from ge_parser import parse_file

OUT_DIR = r"data\raw\gruppoesperti"
EXTRA_DIR = os.path.join(OUT_DIR, "extra")
CSV_PATH = os.path.join(OUT_DIR, "aste_reali_tidy.csv")

# (path, source_file label)
MAIN_FILES = [
    (r"E:\claudecode pesante\fonti_prezzi\gruppoesperti_prezzi_aste_reali_2024-25.xlsx",
     "gruppoesperti_prezzi_aste_reali_2024-25.xlsx"),
    (r"E:\claudecode pesante\fonti_prezzi\gruppoesperti_prezzi_aste_reali_2021-22circa.xlsx",
     "gruppoesperti_prezzi_aste_reali_2021-22circa.xlsx"),
]
# file extra con foglio 'Aste Concluse' popolato (da ge_scan_extra.py)
EXTRA_FILES = [
    "1Uxv42LC7d68Y1ZLQ48Hh1ud74kJocO-lTom39eJFB_w.xlsx",
    "1MeKG7yjCemQ1SFoi7RWmhni-iBMtYdPf9FtfdDQWZ5I.xlsx",
    "1J4tILPqyErS5Ccpr0Dy-595D2PgubYxlPaqfX8-pjYw.xlsx",
]

SEASON_MARKERS = {
    "2021-22": ["VIDAL", "OSPINA", "STRAKOSHA", "MERTENS", "INSIGNE", "KESSIE"],
    "2022-23": ["KIM", "ONANA", "BROZOVIC", "IBRAHIMOVIC", "SKRINIAR", "DZEKO"],
    "2023-24": ["GIROUD", "IMMOBILE", "ZIRKZEE", "GUDMUNDSSON", "RETEGUI", "THURAM"],
    "2024-25": ["DOVBYK", "MORATA", "LUKAKU", "THURAM", "RETEGUI", "PULISIC"],
    "2025-26": ["MODRIC", "DE BRUYNE", "DAVID", "OPENDA", "IMMOBILE", "DZEKO"],
}


def season_scores(rows):
    names = {str(r["player_raw"]).strip().upper() for r in rows}
    return {s: sum(1 for m in mk if m in names) for s, mk in SEASON_MARKERS.items()}


def auction_fingerprints(rows):
    """fingerprint per (source_file, auction_id) → per dup-check fra file."""
    fps = {}
    for r in rows:
        key = (r["source_file"], r["auction_id"])
        fps.setdefault(key, {"comp": r["componenti"], "cred": r["crediti_tot"], "players": []})
        fps[key]["players"].append((str(r["player_raw"]).upper(), r["prezzo"]))
    out = {}
    for key, d in fps.items():
        out[key] = (d["comp"], d["cred"], tuple(sorted(d["players"])))
    return out


def main():
    all_rows = []
    per_file = {}  # label -> (stats, rows)

    for path, label in MAIN_FILES:
        rows, stats = parse_file(path, label)
        all_rows.extend(rows)
        per_file[label] = (stats, rows)
        print(f"{label}: aste={stats['populated_auctions']} righe={len(rows)}")

    for fname in EXTRA_FILES:
        path = os.path.join(EXTRA_DIR, fname)
        label = "extra/" + fname
        rows, stats = parse_file(path, label)
        all_rows.extend(rows)
        per_file[label] = (stats, rows)
        print(f"{label}: aste={stats['populated_auctions']} righe={len(rows)}")

    df = pd.DataFrame(all_rows, columns=[
        "source_file", "auction_id", "componenti", "crediti_tot", "modificatore",
        "periodo", "ruolo", "player_raw", "prezzo", "pct_budget"])
    df.to_csv(CSV_PATH, index=False, encoding="utf-8", lineterminator="\n")
    print(f"\nCSV scritto: {CSV_PATH} ({len(df)} righe)")

    # ---- dup-check fra file (stessa asta caricata in piu' spreadsheet) ----
    fps = auction_fingerprints(all_rows)
    by_fp = {}
    for key, fp in fps.items():
        by_fp.setdefault(fp, []).append(key)
    dups = {fp: keys for fp, keys in by_fp.items() if len(keys) > 1}
    cross_dups = [keys for keys in dups.values()
                  if len({k[0] for k in keys}) > 1]
    intra_dups = [keys for keys in dups.values()
                  if len({k[0] for k in keys}) == 1]
    print(f"aste duplicate identiche fra file diversi: {len(cross_dups)}")
    print(f"aste duplicate identiche dentro lo stesso file: {len(intra_dups)}")
    for keys in cross_dups[:20]:
        print("  ", keys)

    # ---- statistiche per il report ----
    report = {}
    report["dups_cross"] = cross_dups
    report["dups_intra"] = intra_dups
    report["files"] = {}
    for label, (stats, rows) in per_file.items():
        aucs = stats["auction_meta"]  # (id, comp, cred, mod, per, n_righe)
        combo = Counter((a[1], a[2]) for a in aucs)
        target = [a for a in aucs if a[1] == 10 and a[2] == 500]
        near = [a for a in aucs if a[1] == 10 and a[2] is not None and 400 <= a[2] <= 600]
        report["files"][label] = {
            "aste": stats["populated_auctions"],
            "righe": len(rows),
            "righe_senza_prezzo": stats["rows_no_price"],
            "blocchi_vuoti": stats["empty_blocks"],
            "ancore": stats["anchors"],
            "combo": {f"{c[0]}x{c[1]}": n for c, n in sorted(combo.items(), key=lambda x: -x[1])},
            "target_10x500": len(target),
            "near_10x400_600": len(near),
            "season_scores": season_scores(rows),
        }
    # target sul totale
    all_aucs = [(label, a) for label, (st, _) in per_file.items() for a in st["auction_meta"]]
    report["tot_aste"] = len(all_aucs)
    report["tot_righe"] = len(df)
    report["tot_target_10x500"] = sum(1 for _, a in all_aucs if a[1] == 10 and a[2] == 500)
    report["tot_near"] = sum(1 for _, a in all_aucs
                             if a[1] == 10 and a[2] is not None and 400 <= a[2] <= 600)
    combo_all = Counter((a[1], a[2]) for _, a in all_aucs)
    report["combo_all"] = {f"{c[0]}x{c[1]}": n for c, n in sorted(combo_all.items(), key=lambda x: -x[1])}

    with open(os.path.join(OUT_DIR, "build_stats.json"), "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2, default=str)
    print("\nStats salvate in build_stats.json")
    print("combo (componenti x crediti) totale:", report["combo_all"])
    print("aste target 10x500:", report["tot_target_10x500"],
          "| near 10x400-600:", report["tot_near"])
    for label, d in report["files"].items():
        print(f"\n{label}: aste={d['aste']} righe={d['righe']} target={d['target_10x500']} "
              f"season={d['season_scores']}")


if __name__ == "__main__":
    main()
