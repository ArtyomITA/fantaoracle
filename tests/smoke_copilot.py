"""Smoke Copilota: setup tavolo reale, registra acquisti, chiedi consigli.
Prerequisito: python scripts/f10_copilot.py 2025-26 --porta 8770
"""
import json
import sys
import urllib.request

BASE = f"http://localhost:{sys.argv[1] if len(sys.argv) > 1 else '8770'}"


def get(path):
    with urllib.request.urlopen(BASE + path, timeout=30) as r:
        return json.loads(r.read())


def post(path, obj):
    req = urllib.request.Request(BASE + path, json.dumps(obj).encode(),
                                 {"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.loads(r.read())


if __name__ == "__main__":
    names = ["IO", "Marco", "Luca", "Gigi", "Pippo", "Ale", "Fede", "Teo", "Nico", "Sam"]
    print("setup:", post("/copilot/setup", {"names": names, "my_index": 0, "budget": 500}))
    top = get("/copilot/players?role=A")[:3]
    print("top A:", [(p["nome"], p["q50"], p["value"]) for p in top])
    pid = top[0]["id"]
    a = get(f"/copilot/advice?player_id={pid}&price=120")
    print("advice su", a["nome"], "a 120:", a["consiglio"], "| max", a["max_consigliato"], "| piano:", a["in_piano"])
    print("hammer:", post("/copilot/hammer", {"player_id": pid, "team_index": 3, "price": 150}))
    a2 = get(f"/copilot/advice?player_id={top[1]['id']}&price=100")
    print("advice su", a2["nome"], "dopo il martelletto:", a2["consiglio"], "| heat", a2["heat"])
    print("nominate A:", get("/copilot/nominate?role=A")["consiglio"])
    pl = get("/copilot/plan")
    print("piano: budget", pl["budget"], "| costo atteso", pl["costo_atteso_piano"],
          "| A target:", [(x["nome"], x["max_consigliato"]) for x in pl["target"]["A"][:3]])
    print("undo:", post("/copilot/undo", {}))
    st = get("/copilot/state")
    print("state: eventi", st["n_events"], "| pool", st["pool_size"], "| ledger", st["ledger"])
