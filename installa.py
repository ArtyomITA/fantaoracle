"""Mette in piedi FantaOracle su un computer nuovo, per usare il Copilota all'asta.

Cosa fa, in ordine:

1. controlla la versione di Python (serve 3.11 o piu' recente);
2. crea l'ambiente virtuale `.venv` nella cartella del progetto e ci installa
   i pacchetti di `requirements-asta.txt` (il minimo per il Copilota: pandas,
   numpy, PuLP, psutil; il modello non si riaddestra qui);
3. scompatta il bundle dei dati (`bundle_asta_<stagione>_<data>.zip`, creato
   sull'altro PC con `scripts/prepara_bundle_asta.py`) dentro `data/`:
   il repository pubblico non lo contiene, perche' dentro ci sono dati di
   fonti terze;
4. verifica che i file necessari ci siano;
5. prova di fumo: avvia il Copilota su una porta di prova, chiede
   `/copilot/state`, lo spegne.

Alla fine stampa come si avvia il menu. Si puo' rilanciare quante volte si
vuole: non rifa' quello che c'e' gia'.

Uso (dalla cartella del progetto, con il Python di sistema):
    python installa.py --bundle "C:\\percorso\\bundle_asta_2026-27_20260913.zip"
    python installa.py                      # senza bundle: solo ambiente e verifica
    python installa.py --playwright         # in piu' Chrome per il ponte FantaAsta
    python installa.py --senza-prova        # salta la prova di fumo
    python installa.py --porta-prova 8795   # porta diversa per la prova
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
import urllib.request
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent
VENV = ROOT / ".venv"
PORTA_PROVA = 8791          # --porta-prova N per cambiarla


def python_venv() -> Path:
    if os.name == "nt":
        return VENV / "Scripts" / "python.exe"
    return VENV / "bin" / "python"


def passo(titolo: str) -> None:
    print(f"\n== {titolo}")


def esegui(cmd: list[str], **kw) -> subprocess.CompletedProcess:
    print("   $", " ".join(str(c) for c in cmd))
    return subprocess.run(cmd, check=False, **kw)


def controlla_python() -> bool:
    passo("Python")
    v = sys.version_info
    print(f"   trovato Python {v.major}.{v.minor}.{v.micro} ({sys.executable})")
    if v < (3, 11):
        print("   serve Python 3.11 o piu' recente: https://www.python.org/downloads/")
        return False
    return True


def prepara_venv(con_playwright: bool) -> bool:
    passo("ambiente virtuale .venv")
    py = python_venv()
    if not py.exists():
        r = esegui([sys.executable, "-m", "venv", str(VENV)])
        if r.returncode != 0 or not py.exists():
            print("   creazione di .venv fallita")
            return False
    else:
        print("   .venv c'e' gia'")
    esegui([str(py), "-m", "pip", "install", "--upgrade", "pip", "--quiet"])
    req = ROOT / "requirements-asta.txt"
    r = esegui([str(py), "-m", "pip", "install", "-r", str(req)])
    if r.returncode != 0:
        print("   installazione dei pacchetti fallita: controlla la connessione "
              "e rilancia")
        return False
    if con_playwright:
        esegui([str(py), "-m", "pip", "install", "playwright"])
        esegui([str(py), "-m", "playwright", "install", "chromium"])
    return True


def scompatta_bundle(percorso: Path) -> bool:
    passo(f"bundle dati: {percorso}")
    if not percorso.exists():
        print("   file non trovato")
        return False
    with zipfile.ZipFile(percorso) as z:
        nomi = z.namelist()
        # il bundle contiene solo percorsi relativi sotto data/: qualunque
        # altra cosa (percorsi assoluti, "..") si rifiuta prima di scrivere
        for n in nomi:
            if n.startswith(("/", "\\")) or ".." in n.split("/"):
                print(f"   percorso sospetto nello zip, mi fermo: {n}")
                return False
            if not (n.startswith("data/") or n == "MANIFESTO_bundle.json"):
                print(f"   voce inattesa nello zip, mi fermo: {n}")
                return False
        z.extractall(ROOT)
        try:
            man = json.loads(z.read("MANIFESTO_bundle.json").decode("utf-8"))
            print(f"   stagione {man.get('stagione')}, creato {man.get('creato')}, "
                  f"{len(man.get('file', []))} file")
        except (KeyError, ValueError):
            print(f"   {len(nomi)} voci scompattate (senza manifesto)")
    return True


def stagione_corrente() -> str | None:
    f = ROOT / "data" / "packs" / "CORRENTE.json"
    if not f.exists():
        return None
    try:
        d = json.loads(f.read_text(encoding="utf-8"))
        # CORRENTE.json chiama la stagione "stagione"; "season" e' il nome
        # nel pack e nel ledger
        return str(d.get("stagione") or d.get("season") or "")
    except (OSError, json.JSONDecodeError):
        return None


def verifica_dati() -> tuple[bool, str | None]:
    passo("file dati")
    stagione = stagione_corrente()
    if not stagione:
        print("   manca data/packs/CORRENTE.json: senza bundle il Copilota non parte")
        return False, None
    obbligatori = [
        ROOT / "data" / "packs" / f"pack_{stagione}.pkl",
        ROOT / "data" / "copilot" / f"eleggibilita_{stagione}.json",
    ]
    utili = [
        ROOT / "data" / "copilot" / f"note_esperto_{stagione}.json",
        ROOT / "data" / "raw" / "voti" / f"voti_{stagione}.csv",
        ROOT / "data" / "processed" / "_match" / "map_voti.csv",
    ]
    ok = True
    for p in obbligatori:
        c = p.exists()
        ok &= c
        print(f"   {'ok ' if c else 'MANCA'} {p.relative_to(ROOT)}")
    for p in utili:
        print(f"   {'ok ' if p.exists() else '--  (facoltativo, assente)'} "
              f"{p.relative_to(ROOT)}")
    (ROOT / "data" / "copilot" / "prove").mkdir(parents=True, exist_ok=True)
    return ok, stagione


def prova_di_fumo(stagione: str, porta: int = PORTA_PROVA) -> bool:
    passo(f"prova di fumo: Copilota su porta {porta}")
    py = python_venv()
    ledger = ROOT / "data" / "copilot" / "prove" / "installa_prova.json"
    for f in (ledger, ledger.with_suffix(".lock")):
        if f.exists():
            f.unlink()
    cmd = [str(py), str(ROOT / "scripts" / "f10_copilot.py"), stagione,
           "--porta", str(porta), "--ledger", str(ledger)]
    print("   $", " ".join(cmd))
    # l'uscita va su file, non su un pipe: un pipe pieno bloccherebbe il
    # figlio prima ancora che risponda
    log = ledger.with_suffix(".log")
    flog = log.open("w", encoding="utf-8", errors="replace")
    proc = subprocess.Popen(cmd, cwd=str(ROOT), stdout=flog,
                            stderr=subprocess.STDOUT)
    esito = False
    t0 = time.time()
    try:
        while time.time() - t0 < 120:
            if proc.poll() is not None:
                break
            try:
                with urllib.request.urlopen(
                        f"http://127.0.0.1:{porta}/copilot/state",
                        timeout=2) as r:
                    d = json.loads(r.read().decode("utf-8"))
                if "pool_size" in d or "teams" in d:
                    print(f"   il Copilota risponde dopo {time.time() - t0:.0f} s "
                          f"(pool {d.get('pool_size', '?')} giocatori)")
                    esito = True
                    break
            except Exception:
                time.sleep(1.0)
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait()
        flog.close()
        if not esito:
            print("   il Copilota non ha risposto. Ultime righe del log:")
            try:
                for riga in log.read_text(encoding="utf-8", errors="replace").splitlines()[-25:]:
                    print("     ", riga)
            except OSError:
                pass
        for f in (ledger, ledger.with_suffix(".lock"), log):
            if f.exists():
                try:
                    f.unlink()
                except OSError:
                    pass
    return esito


def main() -> int:
    args = sys.argv[1:]
    bundle = Path(args[args.index("--bundle") + 1]) if "--bundle" in args else None
    if bundle is None:
        # comodita': uno zip del bundle messo accanto a installa.py si prende da solo
        trovati = sorted(ROOT.glob("bundle_asta_*.zip")) + \
            sorted(ROOT.parent.glob("bundle_asta_*.zip"))
        if trovati:
            bundle = trovati[-1]
            print(f"bundle trovato accanto al progetto: {bundle}")
    if not controlla_python():
        return 1
    if not prepara_venv("--playwright" in args):
        return 1
    if bundle is not None and not scompatta_bundle(bundle):
        return 1
    ok, stagione = verifica_dati()
    if not ok:
        print("\nmancano i dati: crea il bundle sull'altro PC con "
              "`python scripts/prepara_bundle_asta.py` e rilancia con --bundle")
        return 1
    porta = int(args[args.index("--porta-prova") + 1]) if "--porta-prova" in args         else PORTA_PROVA
    if "--senza-prova" not in args and not prova_di_fumo(stagione or "", porta):
        return 1
    py = python_venv()
    passo("fatto")
    print("   avvio del menu:  FantaOracle.bat   (oppure)")
    print(f"   {py} scripts/fantaoracle_app.py --porta 8899")
    print("   poi apri http://localhost:8899/viz/index.html -> ASTA VERA -> "
          "Copilota. Guida: GUIDA_ASTA.md")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
