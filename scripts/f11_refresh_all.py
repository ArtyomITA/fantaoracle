"""Aggiornamento della stagione corrente, con arresto sui fallimenti.

Catena: f8 (scarica) -> f0b (registry, matching, parquet) -> f1 (predizioni)
-> f9 (aggiustamento mercato) -> f2 (pack) -> demo.

## Che cosa e' cambiato, e perche'

Tre difetti riprodotti prima dell'asta del 10 settembre:

1. **un passo fallito non fermava i discendenti**: `f8` falliva e `f2_pack`
   costruiva comunque il pack, con ingressi vecchi o parziali. Ora ogni passo
   dichiara le proprie dipendenze e i suoi discendenti vengono saltati;
2. **`--da f0b` eseguiva zero passi e dichiarava `ok`**: nessun passo si chiama
   `f0b`, si chiamano `f0b_registry`, `f0b_match`, `f0b_outputs`. Un selettore
   che non corrisponde a niente adesso e' un errore, e gli alias documentati
   sono espliciti;
3. **l'esito negativo non diventava exit code non zero**: chi invocava il
   refresh da uno script non poteva accorgersene.

E la promessa della vecchia docstring — «se uno fallisce, il pack precedente
resta valido» — non era garantita: `f2_pack` sovrascriveva il pack prima che
i passi successivi finissero. Ora il pack corrente viene messo al riparo prima
di cominciare e ripristinato se la catena non arriva in fondo.

Uso:
    python scripts/f11_refresh_all.py                # tutta la catena
    python scripts/f11_refresh_all.py --solo f8
    python scripts/f11_refresh_all.py --da f0b_registry
    python scripts/f11_refresh_all.py --elenca       # i nomi dei passi
    python scripts/f11_refresh_all.py --prova        # non esegue niente

Uscita: 0 se tutti i passi richiesti sono riusciti e il pack e' verificato,
diverso da zero altrimenti.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import pickle
import shutil
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
# senza questo `pickle.load` del pack non trova `fantabot.*`, e la verifica
# fallirebbe sempre dichiarando il pack illeggibile
sys.path.insert(0, str(ROOT / "src"))
SCRIPTS = ROOT / "scripts"
LOG_DIR = ROOT / "data" / "refresh"
LOG_DIR.mkdir(parents=True, exist_ok=True)
LOG = LOG_DIR / "last.log"
STATUS = LOG_DIR / "status.txt"
PACKS = ROOT / "data" / "packs"
SEASON = "2026-27"

# Ogni passo dichiara da chi dipende. Un passo i cui antenati non sono tutti
# riusciti non viene eseguito: e' la differenza fra un aggiornamento parziale
# dichiarato e un pack costruito su ingressi vecchi senza dirlo.
#
# `indispensabile=False` significa che il passo puo' fallire senza fermare la
# catena — l'ultimo dato valido resta buono, e la limitazione viene scritta nel
# rapporto del run.
STEPS = [
    {"nome": "f8", "cmd": ["f8_update_market.py"], "dipende": [],
     "indispensabile": True,
     "descrizione": "scarica listone, probabili, indisponibili, prezzi"},
    {"nome": "f0b_registry", "cmd": ["f0b_build_registry.py"], "dipende": ["f8"],
     "indispensabile": True, "descrizione": "registro delle identita'"},
    {"nome": "f0b_match", "cmd": ["f0b_match.py"], "dipende": ["f0b_registry"],
     "indispensabile": True, "descrizione": "collegamento fra fonti"},
    {"nome": "f0b_outputs", "cmd": ["f0b_build_outputs.py"], "dipende": ["f0b_match"],
     "indispensabile": True, "descrizione": "parquet dei giocatori"},
    {"nome": "f1_pred", "cmd": ["f1_make_predictions.py", SEASON],
     "dipende": ["f0b_outputs"], "indispensabile": True,
     "descrizione": "prezzi, valore, presenze"},
    {"nome": "f9_market", "cmd": ["f9_apply_market.py", SEASON],
     "dipende": ["f1_pred"], "indispensabile": False,
     "descrizione": "aggiustamento sui prezzi di mercato osservati"},
    {"nome": "f2_pack", "cmd": ["f2_build_packs.py", SEASON],
     "dipende": ["f1_pred"], "indispensabile": True,
     "descrizione": "pack operativo"},
    {"nome": "f7_demo", "cmd": ["f7_export_demo_pack.py", SEASON],
     "dipende": ["f2_pack"], "indispensabile": False,
     "descrizione": "pack ridotto per la demo"},
]
NOMI = [s["nome"] for s in STEPS]

# Alias documentati: `--da f0b` significava «dal blocco f0b», ma nessun passo
# si chiama cosi'. Invece di eseguire zero passi e dire `ok`, si traduce.
ALIAS = {"f0b": "f0b_registry", "f1": "f1_pred", "f9": "f9_market",
         "f2": "f2_pack", "f7": "f7_demo", "pack": "f2_pack"}

# `f12_choose_objective` non e' piu' nella catena: sceglie un obiettivo tramite
# confronti contestati, e non e' una dipendenza per usare il Copilota. Si lancia
# a mano quando lo si vuole davvero.


def risolvi(nome: str | None, che_cosa: str) -> str | None:
    if nome is None:
        return None
    if nome in NOMI:
        return nome
    if nome in ALIAS:
        print(f"  «{nome}» e' un alias di «{ALIAS[nome]}»")
        return ALIAS[nome]
    raise SystemExit(
        f"{che_cosa} «{nome}» non esiste. Passi: {', '.join(NOMI)}. "
        f"Alias: {', '.join(f'{k}={v}' for k, v in ALIAS.items())}")


def log(msg: str, cartella: Path | None = None):
    line = f"[{datetime.now():%H:%M:%S}] {msg}"
    print(line, flush=True)
    for dest in [LOG] + ([cartella / "log.txt"] if cartella else []):
        with open(dest, "a", encoding="utf-8") as f:
            f.write(line + "\n")


def impronta(percorso: Path) -> str | None:
    if not percorso.exists():
        return None
    return hashlib.sha256(percorso.read_bytes()).hexdigest()


def verifica_pack(percorso: Path) -> tuple[bool, dict]:
    """Un pack diventa corrente solo se si rilegge e ha quello che serve."""
    d = {"percorso": str(percorso), "esiste": percorso.exists()}
    if not percorso.exists():
        return False, {**d, "motivo": "il file non esiste"}
    try:
        with open(percorso, "rb") as f:
            pack = pickle.load(f)
    except Exception as exc:                                    # noqa: BLE001
        return False, {**d, "motivo": f"non rileggibile: {exc}"}
    giocatori = getattr(pack, "players", {}) or {}
    pred = getattr(pack, "b_predictions", {}) or {}
    quote = getattr(pack, "quotas", {}) or {}
    d.update(giocatori=len(giocatori), predizioni=len(pred), quote=dict(quote),
             budget=getattr(pack, "budget", None),
             impronta=impronta(percorso), byte=percorso.stat().st_size)
    if len(giocatori) < 300:
        return False, {**d, "motivo": f"solo {len(giocatori)} giocatori"}
    if not pred:
        return False, {**d, "motivo": "nessuna predizione"}
    senza = [p for p in giocatori if p not in pred]
    d["giocatori_senza_predizione"] = len(senza)
    if len(senza) > len(giocatori) * 0.1:
        return False, {**d, "motivo": f"{len(senza)} giocatori senza predizione"}
    if set(quote) != {"P", "D", "C", "A"}:
        return False, {**d, "motivo": f"quote inattese: {quote}"}
    return True, {**d, "motivo": "verificato"}


def scrivi_riferimento(corsa: str, pack: Path, diagnostica: dict,
                       limitazioni: list) -> Path:
    """Il puntatore al bundle corrente, sostituito atomicamente."""
    rif = PACKS / "CORRENTE.json"
    payload = {
        "run": corsa, "pack": pack.name, "stagione": SEASON,
        "aggiornato": datetime.now().isoformat(timespec="seconds"),
        "impronta": diagnostica.get("impronta"),
        "giocatori": diagnostica.get("giocatori"),
        "limitazioni": limitazioni,
        "nota": ("questo riferimento si aggiorna solo dopo che il pack e' "
                 "stato riletto e verificato. Una sessione d'asta gia' aperta "
                 "conserva il bundle con cui e' partita.")}
    tmp = rif.with_suffix(f".tmp{os.getpid()}")
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(json.dumps(payload, ensure_ascii=False, indent=1))
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, rif)
    return rif


def main() -> int:
    ap = argparse.ArgumentParser(add_help=True)
    ap.add_argument("--solo", default=None)
    ap.add_argument("--da", default=None)
    ap.add_argument("--elenca", action="store_true")
    ap.add_argument("--prova", action="store_true",
                    help="mostra i passi che eseguirebbe, senza eseguirli")
    a, ignoti = ap.parse_known_args()
    if ignoti:
        raise SystemExit(f"opzioni sconosciute: {ignoti}. "
                         "Un'opzione non riconosciuta non e' un successo.")
    if a.elenca:
        for s in STEPS:
            marca = "" if s["indispensabile"] else "  (opzionale)"
            print(f"  {s['nome']:14s} {s['descrizione']}{marca}"
                  f"   dipende da: {s['dipende'] or '-'}")
        return 0

    solo = risolvi(a.solo, "--solo")
    da = risolvi(a.da, "--da")
    if solo and da:
        raise SystemExit("--solo e --da non si usano insieme")

    corsa = f"{datetime.now():%Y%m%dT%H%M%S}_{os.getpid():05d}"
    cartella = LOG_DIR / f"run_{corsa}"
    cartella.mkdir(parents=True, exist_ok=True)
    LOG.write_text("", encoding="utf-8")
    STATUS.write_text("running", encoding="utf-8")

    da_eseguire = []
    partito = da is None
    for s in STEPS:
        if solo:
            if s["nome"] == solo:
                da_eseguire.append(s)
            continue
        if not partito:
            if s["nome"] == da:
                partito = True
            else:
                continue
        da_eseguire.append(s)
    if not da_eseguire:
        STATUS.write_text("errori", encoding="utf-8")
        raise SystemExit("nessun passo da eseguire: controlla --solo/--da")

    log(f"=== refresh {SEASON}, run {corsa} ===", cartella)
    log(f"  passi: {', '.join(s['nome'] for s in da_eseguire)}", cartella)
    if a.prova:
        log("  prova: nessun passo eseguito", cartella)
        STATUS.write_text("prova", encoding="utf-8")
        return 0

    if (solo or da) and da != NOMI[0]:
        log("  ATTENZIONE: ripartenza parziale. Gli ingressi dei passi saltati "
            "vengono da un aggiornamento precedente: il risultato e' un misto, "
            "e il riferimento corrente non verra' spostato.", cartella)

    pack = PACKS / f"pack_{SEASON}.pkl"
    riparo = cartella / f"pack_{SEASON}.precedente.pkl"
    impronta_prima = impronta(pack)
    if pack.exists():
        shutil.copy2(pack, riparo)
        log(f"  pack precedente messo al riparo in {riparo.name} "
            f"(impronta {impronta_prima[:16]})", cartella)

    env = dict(os.environ)
    env.update(TABPFN_DISABLE_TELEMETRY="1", TABPFN_ALLOW_CPU_LARGE_DATASET="1",
               PYTHONIOENCODING="utf-8", REFRESH_RUN=corsa)

    esiti: dict[str, str] = {}
    limitazioni: list[str] = []
    for s in da_eseguire:
        nome = s["nome"]
        rotti = [d for d in s["dipende"] if esiti.get(d) == "fallito"]
        saltati = [d for d in s["dipende"] if esiti.get(d) == "saltato"]
        if rotti or saltati:
            esiti[nome] = "saltato"
            log(f"[{nome}] SALTATO: dipende da {rotti + saltati}", cartella)
            continue
        t0 = time.time()
        log(f"[{nome}] ...", cartella)
        cmd = [sys.executable, str(SCRIPTS / s["cmd"][0]), *s["cmd"][1:]]
        p = subprocess.run(cmd, cwd=str(ROOT), capture_output=True, text=True,
                           env=env, encoding="utf-8", errors="replace")
        coda = "\n".join((p.stdout or "").strip().splitlines()[-6:])
        (cartella / f"{nome}.out.txt").write_text(
            (p.stdout or "") + "\n--- stderr ---\n" + (p.stderr or ""),
            encoding="utf-8")
        if p.returncode == 0:
            esiti[nome] = "ok"
            log(f"[{nome}] OK ({time.time() - t0:.0f}s)\n{coda}", cartella)
        else:
            esiti[nome] = "fallito"
            err = "\n".join((p.stderr or "").strip().splitlines()[-8:])
            log(f"[{nome}] FALLITO codice {p.returncode} "
                f"({time.time() - t0:.0f}s)\n{coda}\n{err}", cartella)
            if not s["indispensabile"]:
                limitazioni.append(
                    f"{nome} fallito ({s['descrizione']}): si usa l'ultimo "
                    "dato valido precedente")

    falliti = [n for n, e in esiti.items() if e == "fallito"]
    saltati = [n for n, e in esiti.items() if e == "saltato"]
    indispensabili_rotti = [n for n in falliti
                            if next(s for s in STEPS if s["nome"] == n)["indispensabile"]]

    ok_pack, diag = verifica_pack(pack)
    completo = (not indispensabili_rotti and not saltati and solo is None
                and da is None)

    if indispensabili_rotti or saltati:
        if riparo.exists() and impronta(pack) != impronta_prima:
            shutil.copy2(riparo, pack)
            log(f"  pack ripristinato dalla copia al riparo: un "
                f"aggiornamento interrotto non diventa corrente", cartella)
        STATUS.write_text("errori", encoding="utf-8")
    elif completo and ok_pack:
        rif = scrivi_riferimento(corsa, pack, diag, limitazioni)
        log(f"  bundle verificato e reso corrente: {rif.name} "
            f"({diag['giocatori']} giocatori)", cartella)
        STATUS.write_text("ok" if not limitazioni else "ok con limitazioni",
                          encoding="utf-8")
    else:
        STATUS.write_text("parziale", encoding="utf-8")

    (cartella / "esito.json").write_text(json.dumps({
        "run": corsa, "stagione": SEASON, "passi": esiti,
        "falliti": falliti, "saltati": saltati,
        "indispensabili_rotti": indispensabili_rotti,
        "limitazioni": limitazioni, "pack": diag, "pack_verificato": ok_pack,
        "catena_completa": completo,
        "impronta_pack_prima": impronta_prima,
        "riferimento_spostato": bool(completo and ok_pack),
    }, ensure_ascii=False, indent=1), encoding="utf-8")

    for n in limitazioni:
        log(f"  limitazione: {n}", cartella)
    log(f"=== fine: {len(falliti)} falliti, {len(saltati)} saltati; "
        f"pack {'verificato' if ok_pack else 'NON verificato: ' + diag['motivo']}"
        f" ===", cartella)
    log(f"  dettaglio in {cartella}", cartella)

    if indispensabili_rotti or saltati:
        return 2
    if not ok_pack:
        return 3
    if falliti:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
