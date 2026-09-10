"""Controllo del Chrome dedicato all'asta (aperto con --remote-debugging-port=9222).

Uso:
    python scripts/asta_chrome.py stato            # scheda, titolo, utente FantaAsta, picks, ponte
    python scripts/asta_chrome.py inietta [porta]  # inietta il ponte verso il Copilota (default 8770)
    python scripts/asta_chrome.py picks            # elenca i picks di FantaAsta
    python scripts/asta_chrome.py console          # ultimi messaggi warning/error della pagina (10 s)
    python scripts/asta_chrome.py js "<codice>"    # esegue JavaScript nella scheda FantaAsta

Si collega via CDP (Playwright connect_over_cdp), non apre finestre. Il Chrome va
avviato con: chrome.exe --user-data-dir=... --remote-debugging-port=9222
--disable-features=LocalNetworkAccessChecks,PrivateNetworkAccessChecks
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

sys.stdout.reconfigure(encoding="utf-8")
ROOT = Path(__file__).resolve().parents[1]
CDP = "http://127.0.0.1:9222"
KEY = "FANTA-ASTA-2025-LIVE"


def pagina_fantaasta(browser):
    for ctx in browser.contexts:
        for pg in ctx.pages:
            if "fanta-asta-live" in pg.url:
                return pg
    return None


def main() -> int:
    cmd = sys.argv[1] if len(sys.argv) > 1 else "stato"
    with sync_playwright() as p:
        b = p.chromium.connect_over_cdp(CDP)
        pg = pagina_fantaasta(b)
        if pg is None:
            print("nessuna scheda FantaAsta nel Chrome dedicato:", [q.url[:60] for c in b.contexts for q in c.pages])
            return 1
        if cmd == "stato":
            print("scheda:", pg.url, "|", pg.title())
            d = pg.evaluate(f"() => {{ const r = localStorage.getItem('{KEY}'); if(!r) return null; const d = JSON.parse(r); return Object.entries(d._users||{{}}).map(([k,u]) => ({{uid:k, started:u.started, squadre:(u.teams||[]).map(t=>t.name), picks:(u.picks||[]).length, giocatori:(u.players||[]).length}})); }}")
            print("utenti FantaAsta:", json.dumps(d, ensure_ascii=False))
            print("ponte:", pg.evaluate("() => window.PONTE ? (window.PONTE.stato ? window.PONTE.stato() : {attivo: window.PONTE.attivo}) : null"))
        elif cmd == "inietta":
            porta = sys.argv[2] if len(sys.argv) > 2 else "8770"
            pg.evaluate(f"window.PONTE_COPILOTA = 'http://127.0.0.1:{porta}'")
            pg.evaluate((ROOT / "viz" / "ponte_fantaasta.js").read_text(encoding="utf-8"))
            time.sleep(2.5)
            print("ponte:", json.dumps(pg.evaluate("() => window.PONTE && window.PONTE.stato ? window.PONTE.stato() : null"), ensure_ascii=False)[:600])
        elif cmd == "picks":
            d = pg.evaluate(f"() => {{ const d = JSON.parse(localStorage.getItem('{KEY}')||'{{}}'); const us = Object.values(d._users||{{}}); const u = us.find(x=>x.started) || us[0]; if(!u) return null; const nome = id => ((u.players||[]).find(p=>String(p.id)===String(id))||{{}}).name || ('#'+id); return {{squadre:(u.teams||[]).map(t=>[t.id,t.name]), picks:(u.picks||[]).map(p=>[p.index, nome(p.playerId), p.playerId, (u.teams||[]).find(t=>t.id===p.teamId)?.name, p.cost, !!p.released])}}; }}")
            print(json.dumps(d, ensure_ascii=False, indent=0)[:4000])
        elif cmd == "console":
            righe = []
            pg.on("console", lambda m: righe.append(f"{m.type}: {m.text[:200]}") if m.type in ("warning", "error") else None)
            time.sleep(10)
            print("\n".join(righe[-30:]) or "(niente)")
        elif cmd == "js":
            print(json.dumps(pg.evaluate(sys.argv[2]), ensure_ascii=False)[:3000])
        else:
            print(__doc__)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
