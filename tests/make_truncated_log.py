"""Crea un log troncato (simula crash a meta' asta) per testare la ripresa."""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
src = ROOT / "data" / "live_logs" / (sys.argv[1] if len(sys.argv) > 1
                                     else "live_1786203653.jsonl")
lines = src.read_text(encoding="utf-8").splitlines()
hams = [i for i, l in enumerate(lines) if json.loads(l).get("kind") == "hammer"]
cut_idx = hams[len(hams) * 3 // 5]
out = ROOT / "data" / "live_logs" / "test_troncata.jsonl"
out.write_text("\n".join(lines[:cut_idx + 1]) + "\n", encoding="utf-8")
e = json.loads(lines[cut_idx])
print(f"troncato al martelletto {len(hams)*3//5}/{len(hams)}: "
      f"{e['player']} ({e['role']}) a {e['price']} -> {out.name}")
