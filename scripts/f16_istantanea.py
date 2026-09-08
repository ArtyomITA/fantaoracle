"""Istantanea verificabile del progetto: archivio per impronta + manifesto.

Il progetto non e' sotto controllo di versione, quindi non esiste un modo nativo
per dire "questo risultato viene da QUESTO codice e da QUESTI dati". Questa
istantanea lo fa: conserva davvero i byte di ogni input che determina un
risultato, li indirizza con la loro impronta SHA-256 e registra ambiente,
comando, parametri e data limite dell'informazione.

## Che cosa e' cambiato rispetto alla versione precedente (7/9/2026)

La versione precedente aveva quattro difetti che la rendevano inutilizzabile
come prova di riproducibilita':

1. trattava `data/raw` come "immutabile per conto suo" e ne salvava solo
   l'impronta. Falso: gli aggiornatori (`f8_update_market.py`,
   `scrape_mercato_fantacalcioit.py`, i download Transfermarkt) sovrascrivono
   il grezzo. Senza i byte, un'impronta che non corrisponde piu' a niente non
   permette di riprodurre nulla;
2. l'identificativo era al minuto e la cartella veniva creata con
   `exist_ok=True`: due istantanee nello stesso minuto si sovrascrivevano a
   vicenda;
3. copiava solo CSV e GZ del grezzo, lasciando fuori l'HTML e il JSON che
   servono alla provenienza (probabili formazioni, listoni, prezzi live);
4. non verificava che i file copiati corrispondessero alle impronte, ne' che
   non cambiassero durante la cattura.

## Come funziona adesso

- **Archivio per impronta.** Ogni file entra in
  `data/istantanee/_archivio/<primi 2 caratteri>/<impronta>` una volta sola.
  Istantanee diverse che condividono un file condividono i byte: la prima
  costa circa 170 MB, le successive solo il delta.
- **Identificativo univoco.** `AAAAMMGG_HHMMSS_<8 caratteri dell'impronta del
  manifesto>`. Se la cartella esiste gia', lo script si ferma invece di
  sovrascrivere.
- **Doppia verifica.** Ogni file viene letto due volte: una per l'impronta,
  una dopo l'archiviazione. Alla fine si ricontrolla che la sorgente non sia
  cambiata durante la cattura. Le discordanze finiscono nel manifesto sotto
  `instabili` e fanno terminare lo script con codice 1.
- **Perimetro completo.** Codice, configurazione, test, pack, predizioni,
  mappe di identita', voti, panel, e tutto `data/raw` (compresi HTML e JSON).
  Restano fuori solo cache, output di torneo, il vecchio archivio e i file
  temporanei: sono derivati, non input.
- **Ripristino.** `--ripristina <id> <cartella>` riscrive l'albero dei file
  di quell'istantanea partendo dall'archivio, verificando ogni impronta.

## Uso

    python scripts/f16_istantanea.py --verifica
    python scripts/f16_istantanea.py --crea --nota "prima dei fix del livello 2"
    python scripts/f16_istantanea.py --elenco
    python scripts/f16_istantanea.py --ripristina 20260907_101500_ab12cd34 /tmp/x

Le impronte da sole non bastano a riprodurre un esperimento: servono anche i
semi casuali e i parametri, che vanno registrati con `--nota` o nel file di
note dell'esperimento.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEST = ROOT / "data" / "istantanee"
ARCHIVIO = DEST / "_archivio"

# Cartelle il cui contenuto e' input di un risultato: vanno conservate per byte.
CARTELLE = [
    "src", "scripts", "config", "tests", "viz",
    "reports",             # criteri congelati e report: sono prove, non commenti
    "data/raw",            # grezzo: NON immutabile, gli aggiornatori lo riscrivono
    "data/packs",
    "data/processed",
    "data/l2",             # risultati degli esperimenti del Livello 2
    "data/l3",             # risultati degli esperimenti del Livello 3
]
# File singoli alla radice.
FILE_RADICE = ["requirements.txt", "README.md", "HANDOFF_SESSIONE.md",
               "PIANO.md", "ASTA_VERA.md", "FantaOracle.bat"]
# Derivati o rumore: fuori dal perimetro.
ESCLUSI_PARTE = ("__pycache__", ".pytest_cache", "catboost_info",
                 "data/istantanee", "data/tournament", "data/tournament_fix",
                 "data/tournament_mod", "data/_cestino", "node_modules", ".git")
ESCLUSI_SUFFISSO = (".pyc", ".pyo", ".tmp", ".lock")


def impronta(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as f:
        for blocco in iter(lambda: f.read(1 << 20), b""):
            h.update(blocco)
    return h.hexdigest()


def escluso(rel: str) -> bool:
    return (any(x in rel for x in ESCLUSI_PARTE)
            or rel.endswith(ESCLUSI_SUFFISSO))


def elenca() -> list[Path]:
    fuori = []
    for d in CARTELLE:
        base = ROOT / d
        if not base.exists():
            continue
        for p in base.rglob("*"):
            if p.is_file():
                rel = str(p.relative_to(ROOT)).replace("\\", "/")
                if not escluso(rel):
                    fuori.append(p)
    for f in FILE_RADICE:
        p = ROOT / f
        if p.is_file():
            fuori.append(p)
    return sorted(fuori)


def raccogli() -> dict[str, dict]:
    """Impronta e metadati di ogni file del perimetro."""
    voci = {}
    for p in elenca():
        rel = str(p.relative_to(ROOT)).replace("\\", "/")
        st = p.stat()
        voci[rel] = {"impronta": impronta(p), "byte": st.st_size,
                     "modificato": time.strftime("%Y-%m-%dT%H:%M:%S",
                                                 time.localtime(st.st_mtime))}
    return voci


def ambiente(argv: list[str]) -> dict:
    try:
        pacchetti = subprocess.run([sys.executable, "-m", "pip", "freeze"],
                                   capture_output=True, text=True,
                                   timeout=180).stdout.splitlines()
    except Exception as e:                                    # pragma: no cover
        pacchetti = [f"non disponibile: {e}"]
    return {"python": sys.version.split()[0],
            "eseguibile": sys.executable,
            "piattaforma": sys.platform,
            "cartella": str(ROOT),
            "comando": " ".join(argv),
            "pacchetti": pacchetti}


def archivia(rel: str, imp: str) -> tuple[bool, str | None]:
    """Copia il file nell'archivio per impronta. Ritorna (nuovo, errore)."""
    dst = ARCHIVIO / imp[:2] / imp
    if dst.exists():
        return False, None
    dst.parent.mkdir(parents=True, exist_ok=True)
    tmp = dst.with_suffix(".parziale")
    shutil.copy2(ROOT / rel, tmp)
    ricontrollo = impronta(tmp)
    if ricontrollo != imp:
        tmp.unlink(missing_ok=True)
        return False, f"impronta cambiata durante la copia: {ricontrollo}"
    os.replace(tmp, dst)
    return True, None


def istantanee() -> list[Path]:
    if not DEST.exists():
        return []
    return sorted(d for d in DEST.iterdir()
                  if d.is_dir() and not d.name.startswith("_")
                  and (d / "manifesto.json").exists())


def ultima() -> Path | None:
    tutte = istantanee()
    return tutte[-1] if tutte else None


def carica(d: Path) -> dict:
    return json.loads((d / "manifesto.json").read_text("utf-8"))


def confronta(voci: dict[str, dict]) -> None:
    prec = ultima()
    if prec is None:
        # compatibilita' col vecchio formato, che scriveva impronte.json
        vecchie = sorted(d for d in DEST.iterdir()
                         if d.is_dir() and (d / "impronte.json").exists()) if DEST.exists() else []
        if not vecchie:
            print("\nnessuna istantanea precedente con cui confrontare")
            return
        prec = vecchie[-1]
        vecchio = json.loads((prec / "impronte.json").read_text("utf-8"))["file"]
    else:
        vecchio = carica(prec)["file"]
    nuovi = sorted(set(voci) - set(vecchio))
    spariti = sorted(set(vecchio) - set(voci))
    cambiati = sorted(k for k in set(voci) & set(vecchio)
                      if voci[k]["impronta"] != vecchio[k]["impronta"])
    print(f"\nconfronto con {prec.name}: {len(cambiati)} cambiati, "
          f"{len(nuovi)} nuovi, {len(spariti)} spariti")
    for et, lista in (("cambiato", cambiati), ("nuovo", nuovi), ("sparito", spariti)):
        for k in lista[:25]:
            print(f"  {et:9s} {k}")
        if len(lista) > 25:
            print(f"  ... e altri {len(lista) - 25} {et}")


def crea(nota: str, as_of: str | None) -> int:
    inizio = time.time()
    voci = raccogli()
    byte_tot = sum(v["byte"] for v in voci.values())
    print(f"perimetro: {len(voci)} file, {byte_tot / 1048576:.1f} MB")
    confronta(voci)

    firma = hashlib.sha256(
        "".join(f"{k}:{v['impronta']}" for k, v in sorted(voci.items()))
        .encode()).hexdigest()
    nome = f"{time.strftime('%Y%m%d_%H%M%S')}_{firma[:8]}"
    out = DEST / nome
    if out.exists():
        print(f"ERRORE: {out} esiste gia'. Non sovrascrivo.", file=sys.stderr)
        return 1
    out.mkdir(parents=True)

    nuovi = 0
    instabili = {}
    for rel, v in voci.items():
        fresco, errore = archivia(rel, v["impronta"])
        nuovi += int(fresco)
        if errore:
            instabili[rel] = errore

    # seconda verifica: la sorgente non deve essere cambiata durante la cattura
    for rel, v in voci.items():
        p = ROOT / rel
        if not p.exists():
            instabili[rel] = "sparito durante la cattura"
        elif p.stat().st_size != v["byte"] or impronta(p) != v["impronta"]:
            instabili[rel] = "modificato durante la cattura"

    manifesto = {
        "id": nome,
        "creata": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "durata_s": round(time.time() - inizio, 1),
        "firma_perimetro": firma,
        "nota": nota,
        "as_of": as_of,
        "n_file": len(voci),
        "byte_totali": byte_tot,
        "nuovi_in_archivio": nuovi,
        "instabili": instabili,
        "ambiente": ambiente(sys.argv),
        "file": voci,
        "avvertenza": ("le impronte identificano codice e dati; per riprodurre "
                       "servono anche semi casuali e parametri, da registrare "
                       "nella nota dell'esperimento"),
    }
    (out / "manifesto.json").write_text(json.dumps(manifesto, indent=1),
                                        encoding="utf-8")
    peso = sum(f.stat().st_size for f in ARCHIVIO.rglob("*") if f.is_file())
    print(f"\nscritta {out.name}: {len(voci)} file, {nuovi} nuovi in archivio "
          f"(archivio totale {peso / 1048576:.1f} MB)")
    if instabili:
        print(f"ATTENZIONE: {len(instabili)} file instabili durante la cattura:",
              file=sys.stderr)
        for k, e in list(instabili.items())[:10]:
            print(f"  {k}: {e}", file=sys.stderr)
        return 1
    return 0


def ripristina(ident: str, dove: Path) -> int:
    d = DEST / ident
    if not (d / "manifesto.json").exists():
        print(f"ERRORE: istantanea {ident} inesistente", file=sys.stderr)
        return 1
    m = carica(d)
    dove.mkdir(parents=True, exist_ok=True)
    guasti = 0
    for rel, v in m["file"].items():
        src = ARCHIVIO / v["impronta"][:2] / v["impronta"]
        if not src.exists():
            print(f"  MANCA in archivio: {rel}", file=sys.stderr)
            guasti += 1
            continue
        dst = dove / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)
        if impronta(dst) != v["impronta"]:
            print(f"  IMPRONTA SBAGLIATA: {rel}", file=sys.stderr)
            guasti += 1
    print(f"ripristinati {len(m['file']) - guasti}/{len(m['file'])} file in {dove}")
    return 1 if guasti else 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--crea", action="store_true")
    ap.add_argument("--verifica", action="store_true")
    ap.add_argument("--elenco", action="store_true")
    ap.add_argument("--ripristina", nargs=2, metavar=("ID", "CARTELLA"))
    ap.add_argument("--nota", default="")
    ap.add_argument("--as-of", default=None,
                    help="data limite dell'informazione contenuta (AAAA-MM-GG)")
    a = ap.parse_args()

    if a.elenco:
        for d in istantanee():
            m = carica(d)
            print(f"{m['id']}  {m['n_file']:5d} file  "
                  f"{m['byte_totali'] / 1048576:7.1f} MB  {m.get('nota', '')}")
        return 0
    if a.ripristina:
        return ripristina(a.ripristina[0], Path(a.ripristina[1]))
    if a.crea:
        return crea(a.nota, a.as_of)
    voci = raccogli()
    print(f"perimetro: {len(voci)} file, "
          f"{sum(v['byte'] for v in voci.values()) / 1048576:.1f} MB")
    confronta(voci)
    print("\n(sola lettura: usa --crea per scrivere l'istantanea)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
