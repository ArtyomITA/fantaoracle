"""Aggiornamento completo "al minuto" della stagione corrente (2026-27).

Catena: f8 (scarica tutto) -> f0b (registry, matching, parquet)
        -> f1_make_predictions (solo stagione corrente)
        -> f9 (aggiustamento mercato) -> f2 (pack) -> demo pack.
Log in data/refresh/last.log (letto dal menu). Ogni passo isolato: se uno
fallisce, il pack precedente resta valido.

Uso: python scripts/f11_refresh_all.py [--solo f8] [--da f0b]
"""
from __future__ import annotations

import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
LOG_DIR = ROOT / "data" / "refresh"
LOG_DIR.mkdir(parents=True, exist_ok=True)
LOG = LOG_DIR / "last.log"
STATUS = LOG_DIR / "status.txt"
SEASON = "2026-27"

STEPS = [
    ("f8", [sys.executable, str(SCRIPTS / "f8_update_market.py")]),
    ("f0b_registry", [sys.executable, str(SCRIPTS / "f0b_build_registry.py")]),
    ("f0b_match", [sys.executable, str(SCRIPTS / "f0b_match.py")]),
    ("f0b_outputs", [sys.executable, str(SCRIPTS / "f0b_build_outputs.py")]),
    ("f1_pred", [sys.executable, str(SCRIPTS / "f1_make_predictions.py"), SEASON]),
    ("f9_market", [sys.executable, str(SCRIPTS / "f9_apply_market.py"), SEASON]),
    ("f2_pack", [sys.executable, str(SCRIPTS / "f2_build_packs.py"), SEASON]),
    ("f7_demo", [sys.executable, str(SCRIPTS / "f7_export_demo_pack.py"), SEASON]),
]


def log(msg: str):
    line = f"[{datetime.now():%H:%M:%S}] {msg}"
    print(line, flush=True)
    with open(LOG, "a", encoding="utf-8") as f:
        f.write(line + "\n")


def main():
    args = sys.argv[1:]
    only = args[args.index("--solo") + 1] if "--solo" in args else None
    start_from = args[args.index("--da") + 1] if "--da" in args else None
    LOG.write_text("", encoding="utf-8")
    STATUS.write_text("running", encoding="utf-8")
    log(f"=== refresh {SEASON} avviato ===")
    import os
    env = dict(os.environ)
    env.update(TABPFN_DISABLE_TELEMETRY="1", TABPFN_ALLOW_CPU_LARGE_DATASET="1",
               PYTHONIOENCODING="utf-8")
    started = start_from is None
    ok_all = True
    for name, cmd in STEPS:
        if only and name != only:
            continue
        if not started:
            if name == start_from:
                started = True
            else:
                continue
        t0 = time.time()
        log(f"[{name}] ...")
        p = subprocess.run(cmd, cwd=str(ROOT), capture_output=True, text=True,
                           env=env, encoding="utf-8", errors="replace")
        tail = "\n".join((p.stdout or "").strip().splitlines()[-6:])
        if p.returncode == 0:
            log(f"[{name}] OK ({time.time()-t0:.0f}s)\n{tail}")
        else:
            ok_all = False
            err = "\n".join((p.stderr or "").strip().splitlines()[-8:])
            log(f"[{name}] FALLITO ({time.time()-t0:.0f}s)\n{tail}\n{err}")
    STATUS.write_text("ok" if ok_all else "errori", encoding="utf-8")
    log(f"=== fine: {'tutto ok' if ok_all else 'con errori'} ===")


if __name__ == "__main__":
    main()
