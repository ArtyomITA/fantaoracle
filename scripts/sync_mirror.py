"""Sincronizza il mirror pubblico dal progetto di lavoro.

Il progetto di lavoro (`fantabot/`) contiene dati scrappati da fonti terze, che
non sono ridistribuibili, e percorsi assoluti della macchina su cui gira. Il
mirror pubblico (`fantabot-github/`) contiene solo il codice, i report e i
dati derivati da noi, con percorsi relativi.

Questo script rende quella copia ripetibile invece che manuale:

- copia solo le cartelle e i file dichiarati in `DA_COPIARE`;
- salta bytecode, cache e tutto quello che elenca `ESCLUSI`;
- riscrive i percorsi assoluti in percorsi relativi alla radice del repo;
- rifiuta di copiare un file che contenga qualcosa che somiglia a una
  credenziale, invece di pubblicarlo e accorgersene dopo.

Uso:
    python scripts/sync_mirror.py --prova      # dice cosa farebbe
    python scripts/sync_mirror.py
"""
from __future__ import annotations

import argparse
import re
import shutil
import sys
from pathlib import Path

RADICE = Path(__file__).resolve().parents[1]
MIRROR = RADICE.parent / "fantabot-github"

# Cartelle e file che vanno nel mirror. Tutto il resto non ci va: l'elenco è
# esplicito di proposito, così aggiungere una cartella al progetto non la
# pubblica per distrazione.
DA_COPIARE = [
    "src", "scripts", "tests", "config", "viz", "reports",
    "requirements.txt", "LICENSE",
    "README.md", "DATA.md", "PIANO.md", "BRAINSTORMING.md",
    "RIPRESA.md", "RIPRESA_ASTA.md", "GUIDA_ASTA.md", "FantaOracle.bat",
]

# `HANDOFF_SESSIONE.md` resta fuori: contiene i nomi degli account usati per il
# push e istruzioni operative che riguardano solo la macchina di sviluppo.
ESCLUSI_ESPLICITI = {"HANDOFF_SESSIONE.md"}

# `_1500.md`: copie byte-identiche dei rapporti dei livelli prodotte da un
# secondo giro di agenti; il mirror tiene una sola versione.
ESCLUSI = re.compile(
    r"(__pycache__|\.pyc$|\.pyo$|\.pytest_cache|\.ipynb_checkpoints"
    r"|\.parquet$|\.pkl$|\.csv\.gz$|\.xls$|\.xlsx$|~$|_1500\.md$)")

# Percorsi assoluti da riscrivere. L'ordine conta: prima il più lungo. Le
# prime due forme hanno il backslash raddoppiato: compaiono dentro le stringhe
# di documentazione che alcuni script generano.
SOSTITUZIONI = [
    ("E:" + "\\\\" + "claudecode pesante" + "\\\\" + "fantabot" + "\\\\", ""),
    ("E:" + "\\\\" + "claudecode pesante" + "\\\\", ""),
    (r"fantabot" + "\\", ""),
    (r"E:\claudecode pesante" + "\\", ""),
    ("", ""),
    ("", ""),
    (r"fantabot", "."),
    ("fantabot", "."),
]

# Quello che non deve mai finire in un repo pubblico. Non è una garanzia: è un
# freno che ferma i casi ovvi prima del commit.
CREDENZIALI = re.compile(
    r"(api[_-]?key\s*[:=]\s*['\"][^'\"]{8,}"
    r"|api[_-]?secret|bearer\s+[A-Za-z0-9._-]{20,}"
    r"|ghp_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,}"
    r"|sk-[A-Za-z0-9]{20,}|AKIA[0-9A-Z]{16}"
    r"|password\s*[:=]\s*['\"][^'\"]{4,}"
    r"|-----BEGIN [A-Z ]*PRIVATE KEY-----)",
    re.IGNORECASE)

TESTUALI = {".py", ".md", ".txt", ".json", ".html", ".css", ".js", ".bat",
            ".yml", ".yaml", ".cfg", ".toml"}


def file_da_copiare() -> list[Path]:
    fuori = []
    for voce in DA_COPIARE:
        p = RADICE / voce
        if not p.exists():
            print(f"  manca, salto: {voce}")
            continue
        if p.is_file():
            fuori.append(p)
            continue
        for f in p.rglob("*"):
            if f.is_file() and not ESCLUSI.search(str(f)):
                fuori.append(f)
    return [f for f in fuori if f.name not in ESCLUSI_ESPLICITI]


def riscrivi(testo: str) -> tuple[str, int]:
    n = 0
    for prima, dopo in SOSTITUZIONI:
        if prima in testo:
            n += testo.count(prima)
            testo = testo.replace(prima, dopo)
    return testo, n


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--prova", action="store_true",
                    help="elenca senza copiare")
    a = ap.parse_args()

    if not MIRROR.exists():
        print(f"BLOCCO: il mirror non esiste in {MIRROR}")
        return 1

    file = file_da_copiare()
    print(f"{len(file)} file da copiare in {MIRROR}")

    sospetti, copiati, riscritti, invariati = [], 0, 0, 0
    for f in file:
        rel = f.relative_to(RADICE)
        dest = MIRROR / rel
        if f.suffix.lower() in TESTUALI:
            try:
                testo = f.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                testo = None
            if testo is not None:
                m = CREDENZIALI.search(testo)
                if m:
                    sospetti.append((rel, m.group(0)[:60]))
                    continue
                nuovo, n = riscrivi(testo)
                if a.prova:
                    if n:
                        riscritti += 1
                    continue
                dest.parent.mkdir(parents=True, exist_ok=True)
                vecchio = (dest.read_text(encoding="utf-8")
                           if dest.exists() else None)
                if vecchio == nuovo:
                    invariati += 1
                else:
                    dest.write_text(nuovo, encoding="utf-8")
                    copiati += 1
                if n:
                    riscritti += 1
                continue
        if a.prova:
            continue
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(f, dest)
        copiati += 1

    if sospetti:
        print("\nBLOCCO: possibili credenziali, file NON copiati:")
        for rel, frammento in sospetti:
            print(f"  {rel}: {frammento}")
        return 2

    if a.prova:
        print(f"prova: {len(file)} file, {riscritti} con percorsi da riscrivere")
        return 0
    print(f"copiati o aggiornati {copiati}, invariati {invariati}, "
          f"con percorsi riscritti {riscritti}")
    print("nessuna credenziale trovata nei file testuali")
    return 0


if __name__ == "__main__":
    sys.exit(main())

# NOTA sul README: il README pubblicato e' stato riscritto direttamente nel
# mirror (settembre 2026) e per un periodo la copia nel progetto e' rimasta
# indietro. Un sync l'avrebbe riportata indietro anche online. Le due copie
# sono state riallineate: se in futuro divergono di nuovo, la versione buona e'
# quella pubblicata, non quella del progetto.
