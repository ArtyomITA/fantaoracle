"""Modalita' Sedia — server asta live: 9 bot + il tuo seggio.

Il motore d'asta gira in un thread; quando tocca all'umano (chiamata o
rilancio) si blocca su una coda e aspetta l'input HTTP dal browser.

Avvio:  python scripts/f6_live_auction.py [stagione=2025-26] [--no-b] [--porta 8765]
Poi apri il teatro: http://localhost:8899/viz/replay.html?live=http://localhost:8765

API (JSON, CORS aperto su localhost):
  GET  /state            -> {seq, phase, awaiting, me, hint, finished}
  GET  /events?since=N   -> eventi con seq > N (stesso schema del replay)
  GET  /players?role=&q= -> giocatori disponibili (per la chiamata)
  POST /action           -> {"type":"bid","amount":N} | {"type":"pass"}
                            | {"type":"nominate","player_id":ID,"opening":N}
                            | {"type":"auto"}  (decide il suggeritore)
"""
from __future__ import annotations

import json
import pickle
import queue
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import random  # noqa: E402

from fantabot.bots.base import AuctionView, BidDecision, Bot, NominationDecision  # noqa: E402
from fantabot.engine import AuctionEngine  # noqa: E402
from fantabot.models import ROLES  # noqa: E402
from fantabot.season.detail import season_detail  # noqa: E402
from fantabot.tournament import make_bot  # noqa: E402

# ----------------------------------------------------------------- stato
LOCK = threading.Lock()
STATE = {
    "awaiting": None,      # None | {"type":"nomination"|"bid", ...}
    "finished": False,
    "log_path": None,
    "season": None,        # dettaglio stagione post-asta (json)
}
ACTIONS: "queue.Queue[dict]" = queue.Queue()
ENGINE: AuctionEngine | None = None
PACK = None
HUMAN_TEAM_ID = None


def hint_for(pid: str, price: int | None = None) -> dict:
    """Suggerimento stile-B dal pack (q50/q90/value + heat live)."""
    pred = PACK.b_predictions.get(pid, {})
    heat_num = heat_den = 0.0
    if ENGINE:
        for e in ENGINE.events:
            if e.kind == "hammer":
                q50 = PACK.b_predictions.get(e.payload["player_id"], {}).get("q50", 0)
                if q50 > 10:
                    heat_num += e.payload["price"]
                    heat_den += q50
    heat = max(0.5, min(1.8, heat_num / heat_den)) if heat_den > 30 else 1.0
    q50, q90 = pred.get("q50", 1.0), pred.get("q90", 2.0)
    return {
        "q50": round(q50, 1), "q90": round(q90, 1),
        "value": round(pred.get("value", 0.0), 0),
        "heat": round(heat, 2),
        "max_consigliato": round(q90 * heat, 1),
        "giudizio": ("sotto la mediana, prendilo" if price is not None and price < q50 * heat
                     else "zona alta, occhio" if price is not None and price < q90 * heat
                     else "oltre il massimo consigliato" if price is not None
                     else ""),
    }


class HumanBot(Bot):
    name = "TU"

    def nominate(self, view: AuctionView) -> NominationDecision:
        avail = {p.player_id: {"id": p.player_id, "nome": p.name,
                               "squadra": p.team,
                               "hint": hint_for(p.player_id)}
                 for p in view.available(view.current_role)}
        with LOCK:
            STATE["awaiting"] = {
                "type": "nomination", "role": view.current_role,
                "budget": view.me.budget,
                "max_bid": view.me.max_bid(view.quotas),
            }
        while True:
            a = ACTIONS.get()
            if a["type"] == "auto":
                best = max(avail.values(), key=lambda x: x["hint"]["value"])
                pid, opening = best["id"], 1
            elif a["type"] == "nominate" and a.get("player_id") in avail:
                pid = a["player_id"]
                opening = max(1, min(int(a.get("opening", 1)),
                                     view.me.max_bid(view.quotas)))
            else:
                continue  # azione non valida in questo stato: aspetta ancora
            with LOCK:
                STATE["awaiting"] = None
            return NominationDecision(pid, opening, "chiamata umana")

    def bid(self, view: AuctionView, player, price: int, leader) -> BidDecision:
        h = hint_for(player.player_id, price)
        with LOCK:
            STATE["awaiting"] = {
                "type": "bid", "player_id": player.player_id,
                "player": player.name, "role": player.role,
                "price": price, "min_next": price + 1,
                "leader": leader, "budget": view.me.budget,
                "max_bid": view.me.max_bid(view.quotas),
                "slots_left_role": view.me.slots_left(view.quotas, player.role),
                "hint": h,
            }
        while True:
            a = ACTIONS.get()
            if a["type"] == "pass":
                dec = BidDecision(None, "passo")
            elif a["type"] == "bid":
                amt = int(a.get("amount", price + 1))
                if amt < price + 1:
                    continue
                dec = BidDecision(min(amt, view.me.max_bid(view.quotas)),
                                  "rilancio umano")
            elif a["type"] == "auto":
                cap = h["max_consigliato"]
                if price + 1 <= cap:
                    # salto verso il cap: meno giri di rilancio
                    jump = price + max(1, int((cap - price) * 0.6))
                    dec = BidDecision(min(jump, int(cap)), f"auto: sotto {cap}")
                else:
                    dec = BidDecision(None, "auto: passo")
            else:
                continue
            with LOCK:
                STATE["awaiting"] = None
            return dec


# ----------------------------------------------------------------- http
class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):  # silenzia il log per non sporcare il terminale
        pass

    def _send(self, obj, code=200):
        body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self):
        self._send({})

    def do_GET(self):
        u = urlparse(self.path)
        q = parse_qs(u.query)
        if u.path == "/state":
            me = None
            if ENGINE:
                for t in ENGINE.teams:
                    if t.team_id == HUMAN_TEAM_ID:
                        me = {"team_id": t.team_id, "budget": t.budget,
                              "roster": t.roster}
            with LOCK:
                self._send({"seq": ENGINE._seq if ENGINE else 0,
                            "awaiting": STATE["awaiting"],
                            "finished": STATE["finished"],
                            "log_path": STATE["log_path"], "me": me})
        elif u.path == "/events":
            since = int(q.get("since", ["0"])[0])
            evs = [e.to_dict() for e in (ENGINE.events if ENGINE else [])
                   if e.seq > since]
            self._send(evs[:500])
        elif u.path == "/season":
            with LOCK:
                self._send(STATE["season"] or {"pronta": False})
        elif u.path == "/players":
            role = q.get("role", [None])[0]
            text = (q.get("q", [""])[0] or "").lower()
            team_f = q.get("squadra", [None])[0]
            out = []
            if ENGINE:
                for p in ENGINE.pool.values():
                    if role and p.role != role:
                        continue
                    if team_f and p.team != team_f:
                        continue
                    if text and text not in p.name.lower():
                        continue
                    out.append({"id": p.player_id, "nome": p.name,
                                "ruolo": p.role, "squadra": p.team,
                                "media_mercato": round(p.ref_price * PACK.budget, 1),
                                "hint": hint_for(p.player_id)})
            out.sort(key=lambda x: -x["hint"]["value"])
            self._send(out[:60])
        elif u.path == "/squadre":
            teams = sorted({p.team for p in (ENGINE.pool.values() if ENGINE else [])})
            self._send(teams)
        else:
            self._send({"err": "not found"}, 404)

    def do_POST(self):
        if urlparse(self.path).path != "/action":
            return self._send({"err": "not found"}, 404)
        n = int(self.headers.get("Content-Length", 0))
        try:
            a = json.loads(self.rfile.read(n) or b"{}")
        except json.JSONDecodeError:
            return self._send({"err": "bad json"}, 400)
        with LOCK:
            waiting = STATE["awaiting"] is not None
        if not waiting:
            return self._send({"ok": False, "err": "non e' il tuo turno"})
        ACTIONS.put(a)
        self._send({"ok": True})


def run_auction(season: str, include_b: bool, seed: int):
    global ENGINE, HUMAN_TEAM_ID
    rng = random.Random(seed)
    specs = (["B"] if include_b else ["C:medio"]) + \
        ["A", "A+", "C:stars_scrubs", "C:semitop", "C:tifoso",
         "C:ancorato", "C:panic", "C:enforcer"]
    bots = [HumanBot(random.Random(seed))]
    bots += [make_bot(s, random.Random(seed * 977 + i), PACK)
             for i, s in enumerate(specs)]
    ENGINE = AuctionEngine(dict(PACK.players), bots, PACK.quotas, PACK.budget,
                           rng)
    HUMAN_TEAM_ID = ENGINE.teams[0].team_id
    ENGINE.run()
    out = ROOT / "data" / "live_logs" / f"live_{int(time.time())}.jsonl"
    ENGINE.write_log(out)
    if not PACK.votes_by_g:
        with LOCK:
            STATE["finished"] = True
            STATE["log_path"] = str(out)
            STATE["season"] = {"non_disponibile": True,
                               "motivo": "pack demo senza voti: rigenera i "
                                         "dati per la stagione (DATA.md)"}
        print(f"\nAsta finita (demo, niente stagione). Log: {out}")
        return
    # stagione post-asta: campionato raccontato giornata per giornata
    key = {}
    seen: dict[str, int] = {}
    for t in ENGINE.teams:
        n = seen.get(t.bot_name, 0)
        seen[t.bot_name] = n + 1
        key[t.team_id] = t.bot_name if n == 0 else f"{t.bot_name}#{n+1}"
    rosters = {key[t.team_id]: {r: [pid for pid, _ in t.roster[r]]
                                for r in ROLES} for t in ENGINE.teams}
    names = {pid: p.name for pid, p in PACK.players.items()}
    detail = season_detail(rosters, PACK.votes_by_g, names,
                           voti_by_g=PACK.voti_by_g,
                           use_mod_difesa=PACK.use_mod_difesa,
                           cal_seed=seed)
    detail["team_of_human"] = key[HUMAN_TEAM_ID]
    season_path = out.with_name(out.stem + "_season.json")
    season_path.write_text(json.dumps(detail, ensure_ascii=False),
                           encoding="utf-8")
    with LOCK:
        STATE["finished"] = True
        STATE["log_path"] = str(out)
        STATE["season"] = detail
    print(f"\nAsta finita. Log: {out}\nStagione: {season_path}")


if __name__ == "__main__":
    args = [a for a in sys.argv[1:]]
    season = next((a for a in args if a[0].isdigit()), "2025-26")
    include_b = "--no-b" not in args
    porta = int(args[args.index("--porta") + 1]) if "--porta" in args else 8765
    seed = int(time.time()) % 100000
    pkl = ROOT / "data" / "packs" / f"pack_{season}.pkl"
    demo = ROOT / "demo" / f"pack_{season}_demo.json"
    if pkl.exists():
        with open(pkl, "rb") as f:
            PACK = pickle.load(f)
    elif demo.exists():
        # pack demo pubblico: solo derivati (niente voti) -> l'asta funziona,
        # la stagione post-asta viene saltata (vedi DATA.md per rigenerare)
        from fantabot.models import Player
        from fantabot.tournament import SeasonPack
        d = json.loads(demo.read_text(encoding="utf-8"))
        PACK = SeasonPack(
            season=d["season"],
            players={p["id"]: Player(p["id"], p["name"], p["role"], p["team"],
                                     p["ref_price"], p["ref_price_sd"],
                                     p["exp_points"]) for p in d["players"]},
            votes_by_g=[], quotas=d["quotas"], budget=d["budget"],
            b_predictions=d["b_predictions"], a_price_list=d["a_price_list"],
            voti_by_g=None, use_mod_difesa=d["use_mod_difesa"])
        print("Pack DEMO (senza voti): asta ok, stagione post-asta disattivata.")
    else:
        raise SystemExit(f"Nessun pack per {season}: ne' {pkl} ne' {demo}")
    t = threading.Thread(target=run_auction, args=(season, include_b, seed),
                         daemon=True)
    t.start()
    print(f"Asta live {season} — tavolo: TU + {'B + ' if include_b else ''}"
          f"2 ragionieri + 6 profili. Server su http://localhost:{porta}")
    print(f"Apri: http://localhost:8899/viz/replay.html?live=http://localhost:{porta}")
    ThreadingHTTPServer(("127.0.0.1", porta), Handler).serve_forever()
