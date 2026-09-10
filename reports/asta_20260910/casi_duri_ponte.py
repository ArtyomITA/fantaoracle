"""Casi duri del ponte su stato FantaAsta sintetico (nessuna app Angular che
riscrive localStorage sotto i piedi): annullamento, svincolo, cambio di costo,
giocatore fuori pack, Copilota irraggiungibile. Copilota vero su 8795.
Pagina servita da un http.server locale su 8796 (origine http -> nessun LNA)."""
import functools
import http.server
import json
import socketserver
import threading
import time
import urllib.request
from playwright.sync_api import sync_playwright

COP = "http://127.0.0.1:8795"
PORTA_PAG = 8796
KEY = "FANTA-ASTA-2025-LIVE"
NOMI = ["Io", "Marco", "Luca"]
PONTE = open(r"viz\ponte_fantaasta.js", encoding="utf-8").read()
# id veri del pack (fantacalcio.it): Malen 5585 + due qualsiasi presi dal pack
IDS = None


def cop(path, body=None):
    req = urllib.request.Request(COP + path, data=json.dumps(body).encode() if body else None,
                                 headers={"Content-Type": "application/json"},
                                 method="POST" if body else "GET")
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode("utf-8"))


class H(http.server.SimpleHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200); self.send_header("Content-Type", "text/html"); self.end_headers()
        self.wfile.write(b"<html><body>pagina di prova ponte</body></html>")

    def log_message(self, *a):
        pass


srv = socketserver.TCPServer(("127.0.0.1", PORTA_PAG), H)
threading.Thread(target=srv.serve_forever, daemon=True).start()

st = cop("/copilot/state")
pool = cop("/copilot/players?role=A")[:6]
ids = [str(p["id"]) for p in pool[:3]]
print("setup:", cop("/copilot/setup", {"names": NOMI, "my_index": 0, "budget": 500}))
print("giocatori di prova:", [(p["id"], p["nome"]) for p in pool[:3]])

STATO = {"_users": {"-1": {"started": True,
                           "teams": [{"id": 0, "name": "Io"}, {"id": 1, "name": "Marco"}, {"id": 2, "name": "Luca"}],
                           "picks": [],
                           "players": [{"id": int(i), "name": "Giocatore %s" % i} for i in ids] +
                                      [{"id": 999999, "name": "Fantasma"}]}},
         "version": 1}


def scrivi(pg, picks):
    d = json.loads(json.dumps(STATO))
    d["_users"]["-1"]["picks"] = picks
    pg.evaluate("(s) => localStorage.setItem('%s', JSON.stringify(s))" % KEY, d)


def attendi(cond, limite=8.0):
    t0 = time.time()
    while time.time() - t0 < limite:
        s = cop("/copilot/state")
        if cond(s):
            return True, s, time.time() - t0
        time.sleep(0.2)
    return False, cop("/copilot/state"), time.time() - t0


esiti = []
with sync_playwright() as p:
    b = p.chromium.launch(channel="chrome", headless=True)
    pg = b.new_page()
    pg.on("console", lambda m: None)
    avvisi = []
    pg.on("console", lambda m: avvisi.append(m.text[:180]) if m.type == "warning" else None)
    pg.goto("http://127.0.0.1:%d/" % PORTA_PAG)
    scrivi(pg, [])
    pg.evaluate("window.PONTE_COPILOTA = '%s'" % COP)
    pg.evaluate(PONTE)

    # 1) tre assegnazioni normali
    picks = [{"index": 0, "teamId": 0, "playerId": int(ids[0]), "value": 10, "cost": 10},
             {"index": 1, "teamId": 1, "playerId": int(ids[1]), "value": 20, "cost": 20},
             {"index": 2, "teamId": 2, "playerId": int(ids[2]), "value": 30, "cost": 30}]
    scrivi(pg, picks)
    ok, s, dt = attendi(lambda s: s["n_events"] == 3)
    esiti.append(("3 assegnazioni inviate", ok, "%.1fs" % dt))

    # 2) annullamento dell'ultima (pick sparito)
    scrivi(pg, picks[:2])
    ok, s, dt = attendi(lambda s: s["n_events"] == 2)
    esiti.append(("annullamento ultima -> undo", ok, "%.1fs" % dt))

    # 3) svincolo dell'ultima (released:true)
    scrivi(pg, [picks[0], dict(picks[1], released=True)])
    ok, s, dt = attendi(lambda s: s["n_events"] == 1)
    esiti.append(("svincolo (released) -> undo", ok, "%.1fs" % dt))

    # 4) cambio di costo sull'ultima assegnazione viva -> undo + reinvio
    scrivi(pg, [dict(picks[0], cost=77, value=77)])
    ok, s, dt = attendi(lambda s: s["n_events"] == 1 and
                        any(x["prezzo"] == 77 for t in s["teams"] for r in "PDCA" for x in t["roster"][r]))
    esiti.append(("cambio costo 10 -> 77 (undo + reinvio)", ok, "%.1fs" % dt))

    # 5) cambio di squadra sull'ultima
    scrivi(pg, [dict(picks[0], cost=77, value=77, teamId=2)])
    ok, s, dt = attendi(lambda s: any(x["prezzo"] == 77 for x in
                                      [y for r in "PDCA" for y in s["teams"][2]["roster"][r]]))
    esiti.append(("cambio squadra Io -> Luca", ok, "%.1fs" % dt))

    # 6) giocatore fuori dal pack: avviso col nome, nessun ritentativo
    scrivi(pg, [dict(picks[0], cost=77, value=77, teamId=2),
                {"index": 1, "teamId": 0, "playerId": 999999, "value": 5, "cost": 5}])
    time.sleep(5)
    inesistente = [a for a in avvisi if "Fantasma" in a]
    esiti.append(("giocatore fuori pack -> avviso col nome", bool(inesistente),
                  inesistente[0][:90] if inesistente else "nessun avviso"))
    n_prima = cop("/copilot/state")["n_events"]
    time.sleep(4)
    esiti.append(("nessun ritentativo sul fuori pack", cop("/copilot/state")["n_events"] == n_prima, ""))

    # 7) annullamento non in coda (il primo di due) -> avviso, niente undo
    scrivi(pg, [dict(picks[0], cost=77, value=77, teamId=2),
                {"index": 2, "teamId": 1, "playerId": int(ids[1]), "value": 20, "cost": 20}])
    ok, s, dt = attendi(lambda s: s["n_events"] == 2)
    scrivi(pg, [{"index": 2, "teamId": 1, "playerId": int(ids[1]), "value": 20, "cost": 20}])
    time.sleep(5)
    fuori_coda = [a for a in avvisi if "non e' l'ultima" in a]
    esiti.append(("annullamento fuori coda -> avviso, niente undo",
                  bool(fuori_coda) and cop("/copilot/state")["n_events"] == 2,
                  fuori_coda[0][:90] if fuori_coda else "nessun avviso"))

    stato = pg.evaluate("() => window.PONTE.stato()")
    riquadro = pg.evaluate("() => document.getElementById('ponte-fantaoracle-box').innerText")
    print("\nriquadro:", riquadro.replace("\n", " | "))
    print("errori registrati:", [e["msg"][:70] for e in stato["errori"]][-6:])
    b.close()
srv.shutdown()

print("\n=== CASI DURI ===")
for nome, ok, extra in esiti:
    print("%-42s %s  %s" % (nome, "OK " if ok else "KO ", extra))
print("falliti: %d/%d" % (sum(1 for _, ok, _ in esiti if not ok), len(esiti)))
