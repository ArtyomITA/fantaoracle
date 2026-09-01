"""Copilota — l'asta VERA con gli amici: tu registri, l'oracolo consiglia.

Nessun bot al tavolo: i partecipanti sono le persone reali della tua lega.
Registri ogni aggiudicazione (chi, chi, quanto) e per ogni giocatore che sale
al banco chiedi il consiglio: max bid per la TUA rosa, se e' un bargain,
piano rosa aggiornato (MILP), chi chiamare al tuo turno. Ogni evento e'
salvato subito su disco (data/copilot/ledger_*.json): chiudi, riapri,
riprendi.

Avvio:  python scripts/f10_copilot.py [stagione=2026-27] [--porta 8770] [--resume ledger.json]

API (JSON, CORS aperto):
  GET  /copilot/state                 -> tavolo, rose, budget, pool residuo, config
  POST /copilot/setup                 -> {"names":[...], "my_index":0, "budget":500}
  POST /copilot/hammer                -> {"player_id":..,"team_index":..,"price":..}
  POST /copilot/undo                  -> annulla l'ultima aggiudicazione
  GET  /copilot/advice?player_id=&price=   -> consiglio sul giocatore al banco
  GET  /copilot/plan                  -> rosa target corrente + max bid per target
  GET  /copilot/nominate?role=        -> chi chiamare ora (esca o riempitivo)
  GET  /copilot/players?role=&q=&squadra=  -> ricerca nel pool residuo
"""
from __future__ import annotations

import json
import pickle
import random
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from fantabot.bots.base import AuctionView  # noqa: E402
from fantabot.bots.bot_b import BBot  # noqa: E402
from fantabot.models import ROLES, TeamState  # noqa: E402

LOCK = threading.Lock()
PACK = None
LEDGER_PATH: Path | None = None
STATE = {
    "season": None, "names": [], "my_index": 0, "budget": 500,
    "quotas": {"P": 3, "D": 8, "C": 8, "A": 6},
    "events": [],            # [{"player_id","team_index","price","ts"}]
}
ADVISOR: BBot | None = None


# ------------------------------------------------------------ stato tavolo
def teams() -> list[TeamState]:
    ts = [TeamState(team_id=f"T{i}", bot_name=n, budget=STATE["budget"])
          for i, n in enumerate(STATE["names"])]
    for e in STATE["events"]:
        t = ts[e["team_index"]]
        p = PACK.players[e["player_id"]]
        t.roster[p.role].append((e["player_id"], e["price"]))
        t.budget -= e["price"]
    return ts


def pool() -> dict:
    sold = {e["player_id"] for e in STATE["events"]}
    return {pid: p for pid, p in PACK.players.items() if pid not in sold}


def view_for_me(role: str = "A") -> AuctionView:
    ts = teams()
    me = ts[STATE["my_index"]]
    return AuctionView(
        me=me, others=[t for i, t in enumerate(ts) if i != STATE["my_index"]],
        quotas=STATE["quotas"], budget_total=STATE["budget"], current_role=role,
        pool=pool(),
        sold=[(e["player_id"], f"T{e['team_index']}", e["price"]) for e in STATE["events"]],
    )


def save():
    if LEDGER_PATH is None:
        return
    LEDGER_PATH.parent.mkdir(parents=True, exist_ok=True)
    LEDGER_PATH.write_text(json.dumps(STATE, ensure_ascii=False, indent=1),
                           encoding="utf-8")


def rebuild_advisor():
    """Ricostruisce l'oracolo dallo stato: replan + calore mercato dai
    prezzi gia' battuti (stessa logica del bot B in asta simulata)."""
    global ADVISOR
    ADVISOR = BBot(random.Random(1), PACK.b_predictions)
    for e in STATE["events"]:
        q50 = ADVISOR._q(e["player_id"], "q50")
        if q50 > 3:
            ADVISOR.infl_num += e["price"]
            ADVISOR.infl_den += q50
    if STATE["names"]:
        ADVISOR._replan(view_for_me())


def player_info(pid: str) -> dict:
    p = PACK.players[pid]
    pr = PACK.b_predictions.get(pid, {})
    return {"id": pid, "nome": p.name, "ruolo": p.role, "squadra": p.team,
            "q10": pr.get("q10"), "q50": pr.get("q50"), "q90": pr.get("q90"),
            "value": pr.get("value"), "motivi": pr.get("motivi", "")}


# ------------------------------------------------------------ consigli
def advice(pid: str, price: int | None) -> dict:
    if ADVISOR is None or not STATE["names"]:
        return {"err": "tavolo non configurato"}
    v = view_for_me(PACK.players[pid].role)
    info = player_info(pid)
    heat = ADVISOR.market_heat()
    is_target = pid in ADVISOR.targets
    is_starter = pid in ADVISOR.starter_targets
    cap = ADVISOR._max_bid_for(pid) if is_target else None
    bargain_cap = min(ADVISOR._q(pid, "q10"), ADVISOR._q(pid, "q50") * 0.6) * heat * 0.9
    value = ADVISOR._q(pid, "value", 0.0)
    slots_left = v.me.slots_left(v.quotas, PACK.players[pid].role)
    max_legal = v.me.max_bid(v.quotas)
    out = {
        **info, "heat": round(heat, 2), "in_piano": is_target,
        "titolare_di_piano": is_starter,
        "max_consigliato": round(min(cap, max_legal), 1) if cap else None,
        "bargain_sotto": round(bargain_cap, 1),
        "slot_liberi_ruolo": slots_left, "offerta_massima_legale": max_legal,
        "prezzo_ombra": round(ADVISOR._dropoff_credits(pid), 1) if is_target else None,
    }
    if slots_left <= 0:
        out["consiglio"] = "reparto pieno: passa"
    elif is_target:
        lim = out["max_consigliato"]
        if price is None or price + 1 <= lim:
            out["consiglio"] = f"NEL PIANO ({'titolare' if is_starter else 'panchina'}): rilancia fino a {lim:.0f}"
        else:
            out["consiglio"] = f"oltre il massimo {lim:.0f}: lascialo, ho alternative"
    elif value >= ADVISOR.MIN_VALUE_OVER_5CR * 0.7 and (price is None or price + 1 <= bargain_cap):
        out["consiglio"] = f"BARGAIN: fuori piano ma sotto {bargain_cap:.0f} vale prenderlo"
    elif value < ADVISOR.MIN_VALUE_OVER_5CR:
        out["consiglio"] = "valore basso: al massimo 1-5 crediti"
    else:
        out["consiglio"] = "non in piano: lascia che paghino gli altri"
    return out


def plan() -> dict:
    if ADVISOR is None or not STATE["names"]:
        return {"err": "tavolo non configurato"}
    v = view_for_me()
    by_role = {r: [] for r in ROLES}
    tot = 0.0
    for pid in ADVISOR.targets:
        p = PACK.players.get(pid)
        if p is None:
            continue
        cap = ADVISOR._max_bid_for(pid)
        q50 = ADVISOR._q(pid, "q50") * ADVISOR.market_heat()
        tot += q50
        by_role[p.role].append({**player_info(pid), "titolare": pid in ADVISOR.starter_targets,
                                "prezzo_atteso": round(q50, 1),
                                "max_consigliato": round(cap, 1)})
    for r in ROLES:
        by_role[r].sort(key=lambda x: -(x["value"] or 0))
    me = v.me
    return {"heat": round(ADVISOR.market_heat(), 2), "budget": me.budget,
            "slot_liberi": {r: me.slots_left(v.quotas, r) for r in ROLES},
            "costo_atteso_piano": round(tot, 1), "target": by_role}


def nominate(role: str) -> dict:
    if ADVISOR is None or not STATE["names"]:
        return {"err": "tavolo non configurato"}
    v = view_for_me(role)
    if v.me.slots_left(v.quotas, role) <= 0:
        return {"consiglio": "reparto pieno", "esca": None, "riempitivo": None}
    d = ADVISOR.nominate(v)
    p = PACK.players[d.player_id]
    kind = "esca" if "fatevi male" in d.thought else "riempitivo"
    return {"consiglio": d.thought, "tipo": kind, "giocatore": player_info(p.player_id),
            "apertura": d.opening_bid}


# ------------------------------------------------------------ http
class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):
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
        q = {k: v[0] for k, v in parse_qs(u.query).items()}
        with LOCK:
            if u.path == "/copilot/state":
                ts = teams() if STATE["names"] else []
                self._send({
                    "season": STATE["season"], "names": STATE["names"],
                    "my_index": STATE["my_index"], "budget": STATE["budget"],
                    "quotas": STATE["quotas"], "n_events": len(STATE["events"]),
                    "ledger": str(LEDGER_PATH) if LEDGER_PATH else None,
                    "teams": [{"index": i, "name": t.bot_name, "budget": t.budget,
                               "max_bid": t.max_bid(STATE["quotas"]),
                               "roster": {r: [{**player_info(pid), "prezzo": pr}
                                              for pid, pr in t.roster[r]] for r in ROLES}}
                              for i, t in enumerate(ts)],
                    "pool_size": len(pool()),
                    "heat": round(ADVISOR.market_heat(), 2) if ADVISOR else 1.0,
                    # ultimi acquisti in ordine cronologico (ticker + label undo)
                    "last_events": [{**player_info(e["player_id"]), "team_index": e["team_index"],
                                     "price": e["price"], "ts": e.get("ts")}
                                    for e in STATE["events"][-15:]],
                })
            elif u.path == "/copilot/advice":
                pid = q.get("player_id")
                price = int(q["price"]) if q.get("price") else None
                self._send(advice(pid, price) if pid in PACK.players else {"err": "id sconosciuto"})
            elif u.path == "/copilot/plan":
                self._send(plan())
            elif u.path == "/copilot/nominate":
                self._send(nominate(q.get("role", "A")))
            elif u.path == "/copilot/players":
                role, text, sq = q.get("role"), (q.get("q") or "").lower(), q.get("squadra")
                out = [player_info(pid) for pid, p in pool().items()
                       if (not role or p.role == role) and (not sq or p.team == sq)
                       and (not text or text in p.name.lower())]
                out.sort(key=lambda x: -(x["value"] or 0))
                self._send(out[:80])
            elif u.path == "/copilot/squadre":
                self._send(sorted({p.team for p in PACK.players.values()}))
            else:
                self._send({"err": "not found"}, 404)

    def do_POST(self):
        u = urlparse(self.path)
        n = int(self.headers.get("Content-Length", 0))
        try:
            body = json.loads(self.rfile.read(n) or b"{}")
        except json.JSONDecodeError:
            return self._send({"ok": False, "err": "bad json"}, 400)
        with LOCK:
            if u.path == "/copilot/setup":
                names = [str(x).strip() for x in body.get("names", []) if str(x).strip()]
                if len(names) < 2:
                    return self._send({"ok": False, "err": "servono almeno 2 partecipanti"})
                STATE["names"] = names
                STATE["my_index"] = int(body.get("my_index", 0))
                STATE["budget"] = int(body.get("budget", 500))
                if body.get("quotas"):
                    STATE["quotas"] = {k: int(v) for k, v in body["quotas"].items()}
                save()
                rebuild_advisor()
                return self._send({"ok": True})
            if u.path == "/copilot/hammer":
                pid, ti, price = body.get("player_id"), body.get("team_index"), body.get("price")
                if pid not in pool():
                    return self._send({"ok": False, "err": "giocatore non disponibile"})
                ti, price = int(ti), int(price)
                ts = teams()
                if not (0 <= ti < len(ts)):
                    return self._send({"ok": False, "err": "squadra inesistente"})
                p = PACK.players[pid]
                if ts[ti].slots_left(STATE["quotas"], p.role) <= 0:
                    return self._send({"ok": False, "err": f"{ts[ti].bot_name}: reparto {p.role} pieno"})
                if price > ts[ti].max_bid(STATE["quotas"]):
                    return self._send({"ok": False, "err": f"{ts[ti].bot_name}: supera l'offerta massima legale"})
                STATE["events"].append({"player_id": pid, "team_index": ti,
                                        "price": price, "ts": time.time()})
                save()
                if ADVISOR is not None:
                    ADVISOR.on_hammer(view_for_me(p.role), p, price, f"T{ti}")
                return self._send({"ok": True, "n_events": len(STATE["events"])})
            if u.path == "/copilot/undo":
                if STATE["events"]:
                    STATE["events"].pop()
                    save()
                    rebuild_advisor()
                return self._send({"ok": True, "n_events": len(STATE["events"])})
        self._send({"ok": False, "err": "not found"}, 404)


def load_pack(season: str):
    pkl = ROOT / "data" / "packs" / f"pack_{season}.pkl"
    if pkl.exists():
        with open(pkl, "rb") as f:
            return pickle.load(f)
    demo = ROOT / "demo" / f"pack_{season}_demo.json"
    if demo.exists():
        from fantabot.models import Player
        from fantabot.tournament import SeasonPack
        d = json.loads(demo.read_text(encoding="utf-8"))
        return SeasonPack(season=d["season"],
                          players={p["id"]: Player(p["id"], p["name"], p["role"], p["team"],
                                                   p["ref_price"], p["ref_price_sd"], p["exp_points"])
                                   for p in d["players"]},
                          votes_by_g=[], quotas=d["quotas"], budget=d["budget"],
                          b_predictions=d["b_predictions"], a_price_list=d["a_price_list"])
    raise SystemExit(f"nessun pack per {season}")


if __name__ == "__main__":
    args = sys.argv[1:]
    season = next((a for a in args if a[0].isdigit()), "2026-27")
    porta = int(args[args.index("--porta") + 1]) if "--porta" in args else 8770
    PACK = load_pack(season)
    STATE["season"] = season
    STATE["quotas"] = dict(PACK.quotas)
    STATE["budget"] = PACK.budget
    if "--resume" in args:
        LEDGER_PATH = Path(args[args.index("--resume") + 1])
        STATE.update(json.loads(LEDGER_PATH.read_text(encoding="utf-8")))
        rebuild_advisor()
        print(f"Ripreso ledger {LEDGER_PATH.name}: {len(STATE['events'])} acquisti")
    else:
        LEDGER_PATH = ROOT / "data" / "copilot" / f"ledger_{int(time.time())}.json"
    print(f"Copilota {season} su http://localhost:{porta} — ledger {LEDGER_PATH}")
    ThreadingHTTPServer(("127.0.0.1", porta), Handler).serve_forever()
