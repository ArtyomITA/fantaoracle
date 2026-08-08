"""Fase 3-4 — IL TORNEO: B vs A vs C sulle stagioni 2024-25 e 2025-26.

Composizioni: principale 1B+2A+7C (150 repliche), sensibilita' 1B+9C e
1B+4A+5C (50 repliche). Ogni replica: asta completa + stagione coi fantavoti
reali (100 calendari H2H). Output: data/tournament/{stagione}/{comp}/ +
reports/VERDETTO.md
"""
from __future__ import annotations

import pickle
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from fantabot.tournament import run_tournament  # noqa: E402
from fantabot.verdict import write_verdict  # noqa: E402

C7 = ["C:stars_scrubs", "C:semitop", "C:tifoso", "C:ancorato",
      "C:panic", "C:tirchio", "C:enforcer"]
COMPS = {
    "main_1B_2A_7C": (["B", "A", "A+"] + C7, 150),
    "sens_1B_9C": (["B"] + C7 + ["C:medio", "C:stars_scrubs"], 50),
    "sens_1B_4A_5C": (["B", "A", "A+", "A", "A+"] + C7[:5], 50),
}
SEASONS = ["2024-25", "2025-26"]

if __name__ == "__main__":
    # argomento opzionale: nome della cartella risultati (default "tournament")
    out_root = sys.argv[1] if len(sys.argv) > 1 else "tournament"
    t0 = time.time()
    for season in SEASONS:
        with open(ROOT / "data" / "packs" / f"pack_{season}.pkl", "rb") as f:
            pack = pickle.load(f)
        for comp_name, (spec, n) in COMPS.items():
            out = ROOT / "data" / out_root / season / comp_name
            if (out / "summary.json").exists():
                print(f"[{time.time()-t0:7.0f}s] {season} {comp_name}: "
                      f"gia' completo, salto", flush=True)
                continue
            print(f"[{time.time()-t0:7.0f}s] {season} {comp_name}: "
                  f"{n} repliche...", flush=True)
            s = run_tournament(pack, spec, n_replicas=n, out_dir=out,
                               n_calendars=100, workers=8, save_logs_every=25)
            b = s["bots"].get("B")
            if b:
                print(f"    B: win {b['win_rate']:.1%}  rank {b['avg_rank']:.2f}  "
                      f"pts vs tavolo {b['pts_vs_table_mean']:+.1f}  "
                      f"residuo {b['avg_leftover']:.0f}", flush=True)
    md = write_verdict(ROOT / "data" / out_root,
                       ROOT / "reports" / f"VERDETTO_{out_root}.md")
    print(f"\n[{time.time()-t0:.0f}s] VERDETTO scritto in reports/VERDETTO_{out_root}.md")
