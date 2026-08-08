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

ROOT = Path(__file__).resolve().parents[1]
F6 = ROOT / "scripts" / "f6_live_auction.py"

CHILDREN: dict[int, subprocess.Popen] = {}
LOCK = threading.Lock()


def child_alive(porta: int) -> bool:
    p = CHILDREN.get(porta)
    return p is not None and p.poll() is None


def probe_auction(porta: int, timeout: float = 1.0) -> dict | None:
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{porta}/state",
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
        if urlparse(self.path).path == "/launcher/status":
            with LOCK:
                kids = [{"porta": p, "alive": child_alive(p)}
                        for p in sorted(CHILDREN)]
            return self._json({"launcher": True, "children": kids})
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
            resume_path = None
            if resume == "latest":
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
            elif resume:
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
            if old is None and probe_auction(porta, 0.5) is not None:
                return self._json({"ok": False,
                                   "err": f"porta {porta} gia' occupata da un "
                                          f"altro processo: fermalo o cambia porta"})
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
            # aspetta che l'asta risponda (max ~8s: carica il pack)
            for _ in range(16):
                time.sleep(0.5)
                if probe_auction(porta) is not None:
                    return self._json({"ok": True, "porta": porta,
                                       "season": season, "no_b": no_b})
                if proc.poll() is not None:
                    return self._json({"ok": False,
                                       "err": "l'asta si e' chiusa subito: "
                                              "controlla pack/stagione"})
            return self._json({"ok": False, "err": "timeout avvio asta"})

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
