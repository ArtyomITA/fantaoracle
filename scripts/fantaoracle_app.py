"""FantaOracle App — un processo solo: serve la webapp E lancia le aste.

Serve i file statici dalla radice del progetto (viz/, demo/, data/...) e
espone un mini-launcher per la modalita' Sedia, cosi' il bottone AVVIA del
menu funziona davvero:

  GET  /launcher/status          -> {"launcher": true, "children": [...]}
  POST /launcher/start           -> {"season", "porta", "no_b"} lancia
                                    scripts/f6_live_auction.py (uccide
                                    l'eventuale asta precedente su quella
                                    porta) e risponde {"ok": true, ...}
  POST /launcher/stop            -> {"porta"} ferma l'asta

Avvio:  python scripts/fantaoracle_app.py [--porta 8899]
Poi apri http://localhost:8899/viz/index.html (o usa FantaOracle.bat).
"""
from __future__ import annotations

import json
import subprocess
import sys
import threading
import time
import urllib.request
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

from datetime import datetime

ROOT = Path(__file__).resolve().parents[1]

def sessioni_copilota():
    """I ledger riprendibili, senza le copie di sicurezza.

    `glob("ledger_*.json")` prendeva anche `ledger_123.buono.json`, la copia
    che il Copilota tiene per poter riprendere da un salvataggio interrotto:
    comparivano come sessioni distinte, ed erano la stessa asta due volte.
    """
    cartella = ROOT / "data" / "copilot"
    if not cartella.exists():
        return []
    return [p for p in cartella.glob("ledger_*.json")
            if ".buono" not in p.name and ".tmp" not in p.name]

F6 = ROOT / "scripts" / "f6_live_auction.py"

CHILDREN: dict[int, subprocess.Popen] = {}
CHILD_MODE: dict[int, str] = {}
REFRESH: subprocess.Popen | None = None
LOCK = threading.Lock()


def child_alive(porta: int) -> bool:
    p = CHILDREN.get(porta)
    return p is not None and p.poll() is None


def probe_auction(porta: int, timeout: float = 1.0, path: str = "/state") -> dict | None:
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{porta}{path}",
                                    timeout=timeout) as r:
            return json.loads(r.read())
    except Exception:
        return None


class Handler(SimpleHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def _json(self, obj, code=200):
        body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        path = urlparse(self.path).path
        if path == "/launcher/status":
            with LOCK:
                kids = [{"porta": p, "alive": child_alive(p),
                         "mode": CHILD_MODE.get(p, "sedia")}
                        for p in sorted(CHILDREN)]
            return self._json({"launcher": True, "children": kids,
                               "seasons": sorted(
                                   {p.stem.replace("pack_", "").replace("_demo", "")
                                    for d in (ROOT / "data" / "packs", ROOT / "demo")
                                    if d.exists() for p in d.glob("pack_*")})})
        if path == "/launcher/refresh_status":
            st = ROOT / "data" / "refresh" / "status.txt"
            lg = ROOT / "data" / "refresh" / "last.log"
            running = REFRESH is not None and REFRESH.poll() is None
            return self._json({
                "running": running,
                "status": st.read_text(encoding="utf-8").strip() if st.exists() else "mai eseguito",
                "log": "\n".join(lg.read_text(encoding="utf-8").splitlines()[-40:]) if lg.exists() else "",
                "ultimo": datetime.fromtimestamp(lg.stat().st_mtime).strftime("%d/%m %H:%M") if lg.exists() else None,
            })
        if path == "/launcher/interrotte":
            # aste (Sedia) e aste vere (Copilota) riprendibili
            out = {"sedia": [], "copilot": []}
            for lg in sorted((ROOT / "data" / "live_logs").glob("live_*.jsonl"),
                             key=lambda p: p.stat().st_mtime, reverse=True)[:10]:
                if not lg.with_name(lg.stem + "_season.json").exists():
                    out["sedia"].append({"file": lg.name,
                                         "quando": datetime.fromtimestamp(lg.stat().st_mtime).strftime("%d/%m %H:%M"),
                                         "eventi": sum(1 for _ in open(lg, encoding="utf-8"))})
            for lg in sorted(sessioni_copilota(),
                             key=lambda p: p.stat().st_mtime, reverse=True)[:10]:
                try:
                    d = json.loads(lg.read_text(encoding="utf-8"))
                    out["copilot"].append({"file": lg.name, "nomi": d.get("names", []),
                                           "acquisti": len(d.get("events", [])),
                                           "quando": datetime.fromtimestamp(lg.stat().st_mtime).strftime("%d/%m %H:%M")})
                except Exception:
                    pass
            return self._json(out)
        return super().do_GET()

    def do_POST(self):
        path = urlparse(self.path).path
        n = int(self.headers.get("Content-Length", 0))
        try:
            body = json.loads(self.rfile.read(n) or b"{}")
        except json.JSONDecodeError:
            return self._json({"ok": False, "err": "bad json"}, 400)

        if path == "/launcher/start":
            season = str(body.get("season", "2025-26"))
            porta = int(body.get("porta", 8765))
            no_b = bool(body.get("no_b", False))
            resume = body.get("resume")   # None | "latest" | percorso log
            mode = str(body.get("mode", "sedia"))   # "sedia" (bot) | "copilot" (asta vera)
            resume_path = None
            if resume == "latest" and mode != "copilot":
                logs = sorted((ROOT / "data" / "live_logs").glob("live_*.jsonl"),
                              key=lambda p: p.stat().st_mtime, reverse=True)
                # interrotta = senza stagione salvata accanto
                for lg in logs:
                    if not lg.with_name(lg.stem + "_season.json").exists():
                        resume_path = lg
                        break
                if resume_path is None:
                    return self._json({"ok": False,
                                       "err": "nessuna asta interrotta da riprendere"})
            elif resume and resume != "latest":   # "latest" del copilota si risolve sotto
                resume_path = Path(resume)
                if not resume_path.exists():
                    return self._json({"ok": False, "err": "log non trovato"})
            with LOCK:
                old = CHILDREN.pop(porta, None)
            if old and old.poll() is None:
                old.terminate()
                try:
                    old.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    old.kill()
            # se la porta e' occupata da un processo NON nostro, non uccidiamo
            # alla cieca: segnaliamo e basta
            # un Copilota risponde su /copilot/state, non su /state: prima la
            # guardia non lo vedeva e avviava un secondo processo sulla stessa
            # porta, che moriva, mentre il menu dichiarava «avviato»
            if old is None and (probe_auction(porta, 0.5) is not None
                                or probe_auction(porta, 0.5, path="/copilot/state") is not None):
                return self._json({"ok": False,
                                   "err": f"porta {porta} gia' occupata da un "
                                          f"altro processo: fermalo o cambia porta"})
            if mode == "copilot":
                script = ROOT / "scripts" / "f10_copilot.py"
                if resume == "latest":
                    ledgers = sorted(sessioni_copilota(),
                                     key=lambda p: p.stat().st_mtime, reverse=True)
                    if not ledgers:
                        return self._json({"ok": False, "err": "nessuna asta vera da riprendere"})
                    resume_path = ledgers[0]
                cmd = [sys.executable, str(script), season, "--porta", str(porta)]
            else:
                cmd = [sys.executable, str(F6), season, "--porta", str(porta)]
                if no_b:
                    cmd.append("--no-b")
            if resume_path is not None:
                cmd += ["--resume", str(resume_path)]
            # figlio COMPLETAMENTE indipendente: sopravvive alla morte
            # dell'app (DETACHED) e lascia traccia degli errori su file
            logdir = ROOT / "data" / "live_logs"
            logdir.mkdir(parents=True, exist_ok=True)
            errlog = open(logdir / f"server_{porta}.log", "a", encoding="utf-8")
            flags = (getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
                     | getattr(subprocess, "DETACHED_PROCESS", 0))
            proc = subprocess.Popen(
                cmd, cwd=str(ROOT),
                stdout=errlog, stderr=subprocess.STDOUT,
                creationflags=flags)
            with LOCK:
                CHILDREN[porta] = proc
                CHILD_MODE[porta] = mode
            # aspetta che l'asta risponda (max ~8s: carica il pack)
            probe_path = "/copilot/state" if mode == "copilot" else "/state"
            for _ in range(16):
                time.sleep(0.5)
                if probe_auction(porta, path=probe_path) is not None:
                    return self._json({"ok": True, "porta": porta, "mode": mode,
                                       "season": season, "no_b": no_b,
                                       "resumed": resume_path is not None})
                if proc.poll() is not None:
                    return self._json({"ok": False,
                                       "err": "l'asta si e' chiusa subito: "
                                              "controlla pack/stagione"})
            return self._json({"ok": False, "err": "timeout avvio asta"})

        if path == "/launcher/refresh":
            global REFRESH
            if REFRESH is not None and REFRESH.poll() is None:
                return self._json({"ok": False, "err": "aggiornamento gia' in corso"})
            cmd = [sys.executable, str(ROOT / "scripts" / "f11_refresh_all.py")]
            if body.get("solo"):
                cmd += ["--solo", str(body["solo"])]
            logdir = ROOT / "data" / "refresh"
            logdir.mkdir(parents=True, exist_ok=True)
            REFRESH = subprocess.Popen(
                cmd, cwd=str(ROOT),
                stdout=open(logdir / "stdout.log", "a", encoding="utf-8"),
                stderr=subprocess.STDOUT,
                creationflags=getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0))
            return self._json({"ok": True})

        if path == "/launcher/stop":
            porta = int(body.get("porta", 8765))
            with LOCK:
                proc = CHILDREN.pop(porta, None)
            if proc and proc.poll() is None:
                proc.terminate()
                try:
                    proc.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    proc.kill()
                return self._json({"ok": True})
            return self._json({"ok": False, "err": "nessuna asta nostra su quella porta"})

        return self._json({"ok": False, "err": "not found"}, 404)


if __name__ == "__main__":
    args = sys.argv[1:]
    porta = int(args[args.index("--porta") + 1]) if "--porta" in args else 8899
    handler = partial(Handler, directory=str(ROOT))
    print(f"FantaOracle App su http://localhost:{porta}/viz/index.html "
          f"(radice: {ROOT})")
    try:
        ThreadingHTTPServer(("127.0.0.1", porta), handler).serve_forever()
    finally:
        for p in CHILDREN.values():
            if p.poll() is None:
                p.terminate()
