"""Esporta il pack demo per la pubblicazione: SOLO derivati nostri.

Dentro: anagrafica giocatori (fatti pubblici), prezzi di riferimento
calibrati (statistiche aggregate e trasformate dal nostro pipeline),
predizioni dei modelli (output nostri), lista VORP.
FUORI: voti per giornata (dati di terzi) -> la stagione simulata richiede
la rigenerazione locale dei dati (vedi DATA.md).

Uso: python scripts/f7_export_demo_pack.py [stagione=2025-26]
"""
import json
import pickle
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

season = sys.argv[1] if len(sys.argv) > 1 else "2025-26"
with open(ROOT / "data" / "packs" / f"pack_{season}.pkl", "rb") as f:
    pack = pickle.load(f)

out = {
    "season": pack.season,
    "budget": pack.budget,
    "quotas": pack.quotas,
    "use_mod_difesa": pack.use_mod_difesa,
    "players": [
        {"id": p.player_id, "name": p.name, "role": p.role, "team": p.team,
         "ref_price": round(p.ref_price, 6),
         "ref_price_sd": round(p.ref_price_sd, 6),
         "exp_points": round(p.exp_points, 1)}
        for p in pack.players.values()
    ],
    "b_predictions": pack.b_predictions,
    "a_price_list": {k: round(v, 2) for k, v in (pack.a_price_list or {}).items()},
}
dest = ROOT / "demo" / f"pack_{season}_demo.json"
dest.parent.mkdir(exist_ok=True)
dest.write_text(json.dumps(out, ensure_ascii=False), encoding="utf-8")
print(f"{dest} ({dest.stat().st_size/1024:.0f} KB, {len(out['players'])} giocatori)")
