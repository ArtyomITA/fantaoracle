"""Prepara il pacchetto dei dati che servono al Copilota su un altro PC.

Il repository pubblico non contiene la cartella `data/`: dentro ci sono dati
scaricati da fonti terze (voti, probabili, rigoristi) che non sono
ridistribuibili, e i registri delle aste vere. Per usare il Copilota su un
altro computer servono pero' alcuni di quei file: questo script li raccoglie
in uno zip da portare a mano (chiavetta, drive privato), che `installa.py`
scompatta al posto giusto.

Dentro finisce il minimo indispensabile per l'asta di una stagione:

- il pack della stagione e `CORRENTE.json` (previsioni, prezzi, obiettivo);
- eleggibilita' e note dell'esperto (`data/copilot/`);
- i voti delle ultime due stagioni e la mappa dei nomi (per i gol veri);
- i file di mercato (rigoristi, probabili, indisponibili) piu' recenti.

Restano fuori: i registri delle aste vere (`ledger_*.json`), i backup, il
profilo Chrome dell'asta, gli html grezzi.

Uso:
    python scripts/prepara_bundle_asta.py                 # stagione corrente
    python scripts/prepara_bundle_asta.py 2026-27 --out E:\\bundle.zip
"""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def stagione_corrente() -> str:
    f = ROOT / "data" / "packs" / "CORRENTE.json"
    if f.exists():
        try:
            d = json.loads(f.read_text(encoding="utf-8"))
            if d.get("stagione") or d.get("season"):
                return str(d.get("stagione") or d.get("season"))
        except (OSError, json.JSONDecodeError):
            pass
    oggi = dt.date.today()
    anno = oggi.year if oggi.month >= 7 else oggi.year - 1
    return f"{anno}-{str(anno + 1)[-2:]}"


def stagione_precedente(stagione: str) -> str:
    a = int(stagione[:4]) - 1
    return f"{a}-{str(a + 1)[-2:]}"


def file_del_bundle(stagione: str) -> list[Path]:
    """Elenco esplicito: si aggiunge a mano, cosi' niente finisce nello zip
    per distrazione."""
    prec = stagione_precedente(stagione)
    voluti = [
        ROOT / "data" / "packs" / f"pack_{stagione}.pkl",
        ROOT / "data" / "packs" / "CORRENTE.json",
        ROOT / "data" / "copilot" / f"eleggibilita_{stagione}.json",
        ROOT / "data" / "copilot" / f"note_esperto_{stagione}.json",
        ROOT / "data" / "raw" / "voti" / f"voti_{stagione}.csv",
        ROOT / "data" / "raw" / "voti" / f"voti_{prec}.csv",
        ROOT / "data" / "processed" / "_match" / "map_voti.csv",
        ROOT / "data" / "raw" / "calendario" / f"calendario_{stagione}.csv",
    ]
    mercato = ROOT / "data" / "raw" / "mercato"
    if mercato.exists():
        # solo l'ultimo file di ogni tipo: il Copilota legge il piu' recente
        for prefisso in ("rigoristi_", "probabili_", "probabili_note_",
                         "indisponibili_"):
            file = sorted(p for p in mercato.glob(f"{prefisso}*.csv")
                          if p.name[len(prefisso):len(prefisso) + 1].isdigit())
            if file:
                voluti.append(file[-1])
    return voluti


def main() -> int:
    args = sys.argv[1:]
    stagione = next((a for a in args if a[:1].isdigit() and "-" in a), None) \
        or stagione_corrente()
    out = Path(args[args.index("--out") + 1]) if "--out" in args else \
        ROOT.parent / f"bundle_asta_{stagione}_{dt.date.today():%Y%m%d}.zip"
    voluti = file_del_bundle(stagione)
    presenti = [p for p in voluti if p.exists()]
    mancanti = [p for p in voluti if not p.exists()]
    obbligatori = {f"pack_{stagione}.pkl", f"eleggibilita_{stagione}.json"}
    persi = [p for p in mancanti if p.name in obbligatori]
    if persi:
        print("mancano file obbligatori, niente bundle:")
        for p in persi:
            print("  ", p.relative_to(ROOT))
        return 1
    manifesto = {"stagione": stagione,
                 "creato": dt.datetime.now().isoformat(timespec="seconds"),
                 "file": []}
    out.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        for p in presenti:
            rel = p.relative_to(ROOT).as_posix()
            z.write(p, rel)
            manifesto["file"].append({
                "percorso": rel, "byte": p.stat().st_size,
                "sha256": hashlib.sha256(p.read_bytes()).hexdigest()})
        z.writestr("MANIFESTO_bundle.json",
                   json.dumps(manifesto, ensure_ascii=False, indent=1))
    print(f"bundle {stagione}: {len(presenti)} file, "
          f"{out.stat().st_size / 1e6:.1f} MB -> {out}")
    for p in presenti:
        print("  +", p.relative_to(ROOT).as_posix())
    for p in mancanti:
        print("  - (assente, facoltativo)", p.relative_to(ROOT).as_posix())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
