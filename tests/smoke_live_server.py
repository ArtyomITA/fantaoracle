"""Smoke E2E server live: gioca un'asta intera col pilota automatico.

Prerequisito: server avviato (python scripts/f6_live_auction.py 2025-26).
Esegui:      python tests/smoke_live_server.py
"""
import json
import time
import urllib.request

BASE = "http://localhost:8765"


def get(path):
    with urllib.request.urlopen(BASE + path, timeout=10) as r:
        return json.loads(r.read())


def post(path, obj):
    req = urllib.request.Request(
        BASE + path, json.dumps(obj).encode(), {"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=10) as r:
        return json.loads(r.read())


if __name__ == "__main__":
    t0 = time.time()
    actions = 0
    last_seq = 0
    while True:
        s = get("/state")
        if s["finished"]:
            break
        if s["awaiting"]:
            post("/action", {"type": "auto"})
            actions += 1
        else:
            time.sleep(0.05)
        if time.time() - t0 > 1500:
            raise SystemExit("TIMEOUT: asta non finita in 25 minuti")
        last_seq = s["seq"]
    season = get("/season")
    ev = get(f"/events?since={max(0, last_seq-5)}")
    me = get("/state")["me"]
    print(f"OK: asta finita in {time.time()-t0:.0f}s, {actions} azioni auto")
    print(f"    budget residuo umano: {me['budget']}, rosa: "
          f"{ {r: len(v) for r, v in me['roster'].items()} }")
    print(f"    stagione: {len(season['giornate'])} giornate, "
          f"umano = {season['team_of_human']}")
    final = season["classifica_finale"]
    for t, row in sorted(final.items(), key=lambda kv: -kv[1]["pts"]):
        print(f"    {t:16s} {row['pts']:3d} pt  gf {row['gf']:3d}  "
              f"fanta {row['fanta']:7.1f}")
