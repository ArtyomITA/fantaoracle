"""Manifesto della sessione: stato delle fasi, decisioni, blocchi, artefatti.

Serve a rendere il lavoro riprendibile da una sessione nuova senza dipendere
dalla cache del runtime. Solo il coordinatore lo aggiorna; gli agenti scrivono
nelle proprie cartelle.

Che cosa registra, per ogni voce:

  fase          identificativo della fase (F0..F10)
  stato         avviata / conclusa / bloccata / inconcludente
  quando        data e ora
  ingressi      percorsi con impronta SHA-256 dei file che determinano il
                risultato (istantanea, pack, panel, cubo)
  comandi       comandi eseguiti, con parametri e semi
  uscite        artefatti prodotti, con impronta
  note          testo libero: decisioni, motivi, alternative scartate
  blocchi       problemi che sospendono un ramo, con la prova

Uso:
  python scripts/l3_manifesto.py --fase F1 --stato conclusa \
      --nota "tre audit finiti" --uscita data/l3/audit/dati/RAPPORTO.md
  python scripts/l3_manifesto.py --mostra
  python scripts/l3_manifesto.py --blocco F7 "descrizione" --prova "comando/output"
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEST = ROOT / "data" / "l3"
FILE = DEST / "MANIFESTO.json"
SESSIONE = "wf_l3_20260907"


def impronta(p: Path) -> str | None:
    if not p.exists() or not p.is_file():
        return None
    h = hashlib.sha256()
    with p.open("rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()[:16]


def carica() -> dict:
    if FILE.exists():
        return json.loads(FILE.read_text("utf-8"))
    return {"sessione": SESSIONE, "creato": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "voci": [], "blocchi": [], "decisioni": []}


def salva(m: dict) -> None:
    DEST.mkdir(parents=True, exist_ok=True)
    FILE.write_text(json.dumps(m, indent=1, ensure_ascii=False), encoding="utf-8")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--fase")
    ap.add_argument("--stato", choices=["avviata", "conclusa", "parziale",
                                        "bloccata", "inconcludente"])
    ap.add_argument("--nota", default="")
    ap.add_argument("--comando", action="append", default=[])
    ap.add_argument("--ingresso", action="append", default=[])
    ap.add_argument("--uscita", action="append", default=[])
    ap.add_argument("--istantanea", default=None)
    ap.add_argument("--blocco", nargs=2, metavar=("FASE", "TESTO"))
    ap.add_argument("--prova", default="")
    ap.add_argument("--decisione", nargs=2, metavar=("SCELTA", "MOTIVO"))
    ap.add_argument("--alternativa", default="")
    ap.add_argument("--mostra", action="store_true")
    a = ap.parse_args()

    m = carica()
    if a.mostra:
        print(f"sessione {m['sessione']}, creata {m['creato']}")
        for v in m["voci"]:
            print(f"  {v['fase']:4s} {v['stato']:14s} {v['quando']}  {v['nota'][:70]}")
        if m["blocchi"]:
            print("\nBLOCCHI:")
            for b in m["blocchi"]:
                print(f"  {b['fase']}: {b['testo']}\n     prova: {b['prova'][:120]}")
        if m["decisioni"]:
            print("\nDECISIONI:")
            for d in m["decisioni"]:
                print(f"  {d['quando']} {d['scelta']} — {d['motivo'][:90]}")
        return 0

    if a.blocco:
        m["blocchi"].append({"fase": a.blocco[0], "testo": a.blocco[1],
                             "prova": a.prova,
                             "quando": time.strftime("%Y-%m-%dT%H:%M:%S")})
    if a.decisione:
        m["decisioni"].append({"scelta": a.decisione[0], "motivo": a.decisione[1],
                               "alternativa_scartata": a.alternativa,
                               "quando": time.strftime("%Y-%m-%dT%H:%M:%S")})
    if a.fase and a.stato:
        m["voci"].append({
            "fase": a.fase, "stato": a.stato,
            "quando": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "nota": a.nota,
            "istantanea": a.istantanea,
            "comandi": a.comando,
            "ingressi": {p: impronta(ROOT / p) for p in a.ingresso},
            "uscite": {p: impronta(ROOT / p) for p in a.uscita},
        })
    salva(m)
    print(f"manifesto aggiornato: {len(m['voci'])} voci, {len(m['blocchi'])} blocchi, "
          f"{len(m['decisioni'])} decisioni")
    return 0


if __name__ == "__main__":
    sys.exit(main())
