"""Copia FantaOracle su una chiavetta (o in una cartella) pronta per un altro PC.

Diverso da `prepara_bundle_asta.py`: qui non si passa da GitHub. Si copia il
progetto intero — codice, pagine, report, pack, eleggibilita', note, voti,
mercato, registri delle aste gia' fatte — cosi' sull'altro computer non si
riscrive niente. Restano fuori solo le cose pesanti o inutili all'asta: gli
ambienti virtuali, le cache, il profilo Chrome del ponte, le istantanee e i
dati grezzi di Transfermarkt/Wayback, i backup, i tornei dei livelli.

Nella copia finisce anche `AVVIA_SU_PORTATILE.bat`: sul portatile basta un
doppio click (crea `.venv`, installa i pacchetti, prova il Copilota, apre il
menu). Serve solo Python 3.11+ gia' installato.

Uso:
    python scripts/prepara_chiavetta.py F:\\FantaOracle      # sulla chiavetta F:
    python scripts/prepara_chiavetta.py                     # cartella accanto al progetto
    python scripts/prepara_chiavetta.py F:\\FantaOracle --tutto   # anche le cartelle pesanti
"""
from __future__ import annotations

import datetime as dt
import fnmatch
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# Cartelle escluse ovunque (nome esatto).
ESCLUDI_OVUNQUE = {".venv", ".git", "__pycache__", ".pytest_cache", ".claude",
                   "catboost_info", ".ipynb_checkpoints", "html"}

# Percorsi (relativi alla radice, con /) esclusi salvo --tutto: pesanti o
# estranei all'asta. I registri delle aste vere in data/copilot restano.
ESCLUDI_PESANTI = [
    "data/chrome_asta", "data/istantanee", "data/_backup_*", "data/_cestino_*",
    "data/baseline_*", "data/l2", "data/l3", "data/counterfactuals",
    "data/indagine", "data/tournament*", "data/live_logs", "data/sample_logs",
    "data/raw/transfermarkt", "data/raw/wayback_prices", "data/raw/gruppoesperti",
    "data/raw/understat", "data/refresh",
]

LEGGIMI = """FantaOracle sulla chiavetta — copiata il {data}

1. Copia questa cartella sul portatile (per esempio sul Desktop): il .venv
   e i registri dell'asta e' meglio che stiano sul disco, non sulla chiavetta.
2. Serve Python 3.11 o piu' recente: https://www.python.org/downloads/
   (spunta «Add python.exe to PATH» durante l'installazione).
3. Doppio click su AVVIA_SU_PORTATILE.bat: crea l'ambiente, installa i
   pacchetti (pandas, numpy, PuLP, psutil), prova il Copilota e apre il menu.
   La prima volta ci mette qualche minuto (scarica i pacchetti); le volte
   dopo basta FantaOracle.bat.
4. Menu: http://localhost:8899/viz/index.html -> ASTA VERA -> Copilota.
   Guida all'asta: GUIDA_ASTA.md. Installazione: INSTALLA.md.

Dentro c'e' tutto quello che serve all'asta: codice, pack {stagione},
eleggibilita', note dell'esperto, voti, mercato, registri delle aste fatte.
Fuori: profilo Chrome del ponte, istantanee, dati grezzi pesanti, backup.
"""


def escluso(rel: str, nome: str, tutto: bool) -> bool:
    if nome in ESCLUDI_OVUNQUE:
        return True
    if tutto:
        return False
    return any(fnmatch.fnmatch(rel, m) for m in ESCLUDI_PESANTI)


def copia(sorgente: Path, destinazione: Path, tutto: bool) -> tuple[int, int]:
    file_copiati = 0
    byte = 0
    for p in sorgente.rglob("*"):
        rel = p.relative_to(sorgente).as_posix()
        parti = rel.split("/")
        # una cartella esclusa taglia tutto il suo sottoalbero
        if any(escluso("/".join(parti[:i + 1]), parti[i], tutto)
               for i in range(len(parti))):
            continue
        if p.is_dir():
            (destinazione / rel).mkdir(parents=True, exist_ok=True)
            continue
        if p.suffix in (".pyc", ".pyo") or p.name.endswith("~"):
            continue
        dest = destinazione / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        # non ricopiare quello che c'e' gia' identico: la chiavetta e' lenta
        if dest.exists() and dest.stat().st_size == p.stat().st_size \
                and int(dest.stat().st_mtime) >= int(p.stat().st_mtime):
            continue
        shutil.copy2(p, dest)
        file_copiati += 1
        byte += p.stat().st_size
    return file_copiati, byte


def stagione_corrente() -> str:
    import json
    f = ROOT / "data" / "packs" / "CORRENTE.json"
    try:
        d = json.loads(f.read_text(encoding="utf-8"))
        return str(d.get("stagione") or d.get("season") or "?")
    except (OSError, ValueError):
        return "?"


def main() -> int:
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    tutto = "--tutto" in sys.argv
    dest = Path(args[0]) if args else \
        ROOT.parent / f"FantaOracle_chiavetta_{dt.date.today():%Y%m%d}"
    if dest.resolve() == ROOT.resolve() or ROOT.resolve() in dest.resolve().parents:
        print("la destinazione non puo' stare dentro il progetto")
        return 1
    dest.mkdir(parents=True, exist_ok=True)
    print(f"copio {ROOT} -> {dest} ({'tutto' if tutto else 'solo il necessario'})")
    n, byte = copia(ROOT, dest, tutto)
    (dest / "LEGGIMI_CHIAVETTA.txt").write_text(
        LEGGIMI.format(data=dt.date.today().isoformat(), stagione=stagione_corrente()),
        encoding="utf-8")
    for f in ("AVVIA_SU_PORTATILE.bat", "installa.py", "requirements-asta.txt",
              "FantaOracle.bat"):
        if not (dest / f).exists():
            print(f"  ATTENZIONE: manca {f} nella copia")
    # la copia non deve portarsi dietro il lock di un Copilota acceso qui
    for lock in (dest / "data" / "copilot").glob("*.lock"):
        lock.unlink()
    tot = sum(p.stat().st_size for p in dest.rglob("*") if p.is_file())
    print(f"copiati {n} file ({byte / 1e6:.0f} MB nuovi); la cartella pesa "
          f"{tot / 1e6:.0f} MB")
    print("sul portatile: copia la cartella sul disco, poi doppio click su "
          "AVVIA_SU_PORTATILE.bat")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
