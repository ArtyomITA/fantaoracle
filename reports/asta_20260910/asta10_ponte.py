"""Prova decisiva del ponte: asta a 10 squadre su FantaAsta Live headless
contro il Copilota vero su 8792. 60+ assegnazioni, annullamento dopo la 20a,
ricaricamento a meta' con reiniezione, confronto continuo FantaAsta <-> Copilota."""
import json
import sys
import time
import urllib.request
from playwright.sync_api import sync_playwright

sys.stdout.reconfigure(encoding="utf-8")
OUT = r"C:\Users\ADMINI~1\AppData\Local\Temp\claude\E--claudecode-pesante\5ff20539-b495-4ac4-bed4-79eabbf8a8b7\scratchpad\w8"
COP = "http://127.0.0.1:8792"
KEY = "FANTA-ASTA-2025-LIVE"
NOMI = ["Io", "Marco", "Luca", "Giulia", "Andrea", "Sara", "Paolo", "Chiara", "Davide", "Elena"]
BUDGET = 1000                     # come FantaAsta, cosi' i budget si confrontano
PONTE = open(r"viz\ponte_fantaasta.js", encoding="utf-8").read()
ARGS = ["--disable-features=LocalNetworkAccessChecks,PrivateNetworkAccessChecks,"
        "PrivateNetworkAccessRespectPreflightResults", "--allow-insecure-localhost"]
RUOLI = ["gk"] * 10 + ["def"] * 20 + ["mid"] * 20 + ["atk"] * 12   # 62 assegnazioni
console, anomalie, ritardi = [], [], []


def cop(path, body=None):
    req = urllib.request.Request(COP + path, data=json.dumps(body).encode() if body else None,
                                 headers={"Content-Type": "application/json"},
                                 method="POST" if body else "GET")
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode("utf-8"))


def chiudi_modale(pg, preferiti):
    m = pg.locator("nz-modal-container:visible")
    if not m.count():
        return None
    btns = m.first.locator("button")
    nomi = [b.inner_text().strip() for b in btns.all()]
    for pref in preferiti:
        for i, n in enumerate(nomi):
            if n.lower().startswith(pref.lower()):
                btns.nth(i).click(); time.sleep(1.0); return n
    return None


def stato_fa(pg):
    raw = pg.evaluate("() => localStorage.getItem('%s')" % KEY)
    d = json.loads(raw)
    us = list(d["_users"].values())
    return next((u for u in us if u.get("started")), us[0])


def inietta(pg):
    pg.evaluate("window.PONTE_COPILOTA = '%s'" % COP)
    pg.evaluate(PONTE)


def attesi_fa(u, nomi_cop):
    """picks vivi di FantaAsta tradotti in (player_id, team_index, prezzo)."""
    mappa = {}
    for pos, t in enumerate(u.get("teams", [])):
        nome = (t.get("name") or "").strip().lower()
        idx = next((i for i, n in enumerate(nomi_cop) if n.strip().lower() == nome), None)
        mappa[t["id"]] = idx if idx is not None else pos
    out = []
    for p in sorted([x for x in u.get("picks", []) if not x.get("released")], key=lambda x: x["index"]):
        out.append((str(p["playerId"]), mappa[p["teamId"]], max(1, int(round(p.get("cost") or 1)))))
    return out


def acquisti_cop(st):
    out = []
    for t in st["teams"]:
        for r in "PDCA":
            for x in t["roster"][r]:
                out.append((str(x["id"]), t["index"], int(x["prezzo"])))
    return out


with sync_playwright() as p:
    print("setup Copilota:", cop("/copilot/setup", {"names": NOMI, "my_index": 0, "budget": BUDGET}))
    b = p.chromium.launch(channel="chrome", headless=True, args=ARGS)
    pg = b.new_page(viewport={"width": 1500, "height": 900})
    pg.on("console", lambda m: console.append("%s: %s" % (m.type, m.text[:200])))
    pg.goto("https://fanta-asta-live.fantacalcio.it/#/main", wait_until="networkidle", timeout=90000)
    time.sleep(3)

    # --- 10 squadre -----------------------------------------------------------
    for i in range(10):
        pg.get_by_text("Aggiungi", exact=False).first.click(timeout=8000); time.sleep(0.45)
    u = stato_fa(pg)
    print("squadre create:", len(u.get("teams", [])))

    # --- rinomina: prima si prova dall'interfaccia, poi da localStorage --------
    rinomina_ui = False
    try:
        card = pg.locator("ui-team-card").first
        if card.count():
            card.click(timeout=3000); time.sleep(1.0)
            ins = pg.locator("input:visible")
            print("click sulla squadra -> input visibili:", ins.count(),
                  "bottoni:", [x.inner_text().strip()[:22] for x in pg.locator("button:visible").all()][:16])
            if ins.count():
                ins.first.fill(NOMI[0]); time.sleep(0.4)
                chiudi_modale(pg, ("Conferma", "Salva", "OK"))
                rinomina_ui = (stato_fa(pg)["teams"][0].get("name") or "") == NOMI[0]
    except Exception as exc:
        print("rinomina dall'interfaccia non riuscita:", str(exc)[:140])
    print("rinomina dall'interfaccia:", rinomina_ui)
    pg.evaluate("""(nomi) => {
        const K = 'FANTA-ASTA-2025-LIVE';
        const d = JSON.parse(localStorage.getItem(K));
        for (const uid in d._users) {
          const u = d._users[uid];
          if (Array.isArray(u.teams)) u.teams.forEach((t, i) => { if (nomi[i]) t.name = nomi[i]; });
        }
        localStorage.setItem(K, JSON.stringify(d));
    }""", NOMI)
    pg.reload(wait_until="networkidle"); time.sleep(3)
    u = stato_fa(pg)
    print("nomi squadre:", [t.get("name") for t in u["teams"]])

    # --- INIZIA + lista Serie A ----------------------------------------------
    pg.get_by_text("INIZIA", exact=True).first.click(timeout=8000); time.sleep(2)
    chiudi_modale(pg, ("Serie A",)); time.sleep(4)
    u = stato_fa(pg)
    print("started:", u.get("started"), "giocatori in lista:", len(u.get("players", [])))
    print("options.bids:", json.dumps(u.get("options", {}).get("bids", {}))[:300])

    inietta(pg); time.sleep(2.5)
    print("console ponte:", [c for c in console if "PONTE" in c][-3:])

    # --- catalogo: i piu' economici per ruolo (cost = FVM = value del pick) ---
    players = u["players"]
    per_ruolo = {}
    for x in players:
        z = (x.get("zone") or {}).get("classic")
        if z:
            per_ruolo.setdefault(z, []).append(x)
    fvm = lambda x: ((x.get("marketValues") or [x.get("price") or 1])[0]) or 1
    for z in per_ruolo:
        per_ruolo[z].sort(key=lambda x: (fvm(x), x.get("name") or ""))
    print("per ruolo:", {z: len(v) for z, v in per_ruolo.items()})

    usati = set()
    cerca = pg.locator("input[placeholder='Cerca...']").first

    def pesca(ruolo):
        for x in per_ruolo.get(ruolo, []):
            if x["id"] not in usati:
                usati.add(x["id"]); return x
        return None

    def assegna(x):
        cerca.fill(""); time.sleep(0.12)
        cerca.fill(x["name"]); time.sleep(0.55)
        pg.locator("ui-player-row", has_text=x["name"]).first.click(timeout=6000)
        time.sleep(0.25)
        t0 = time.time()
        pg.get_by_role("button", name="PICK!").first.click(timeout=8000)
        return t0

    def attendi(n_atteso, t0, limite=15.0):
        while time.time() - t0 < limite:
            st = cop("/copilot/state")
            if st["n_events"] >= n_atteso:
                return time.time() - t0, st
            time.sleep(0.2)
        return None, cop("/copilot/state")

    fatti, scarti = 0, 0
    esito_undo, esito_reload = "non provato", "non provato"
    t_inizio = time.time()
    for i, ruolo in enumerate(RUOLI):
        x = pesca(ruolo)
        if x is None:
            anomalie.append("finiti i giocatori di ruolo %s al pick %d" % (ruolo, i + 1)); break
        try:
            t0 = assegna(x)
        except Exception as exc:
            anomalie.append("pick %d (%s) fallito nell'interfaccia: %s" % (i + 1, x["name"], str(exc)[:140]))
            pg.keyboard.press("Escape"); time.sleep(0.4); continue
        fatti += 1
        rit, st = attendi(fatti - scarti, t0)
        if rit is None:
            anomalie.append("pick %d (%s id %s): non comparso nel Copilota entro 15 s (n_events=%s)"
                            % (fatti, x["name"], x["id"], st["n_events"]))
        else:
            ritardi.append(rit)
        if fatti % 10 == 0:
            uu = stato_fa(pg)
            a, c = sorted(attesi_fa(uu, st["names"])), sorted(acquisti_cop(st))
            print("  %d pick | n_events=%s | ritardo medio %.2fs | diff %d"
                  % (fatti, st["n_events"], sum(ritardi) / max(1, len(ritardi)), len(set(a) ^ set(c))))

        # --- dopo la 20a: annullamento dell'ultima assegnazione ---------------
        if fatti == 20 and esito_undo == "non provato":
            n_prima = cop("/copilot/state")["n_events"]
            fatto_ui = False
            try:
                pg.set_default_timeout(4000)
                pg.get_by_text("Assegnazioni", exact=True).first.click(timeout=4000); time.sleep(1.2)
                bottoni = [t.inner_text().strip()[:28] for t in pg.locator("button:visible").all()]
                print("Assegnazioni -> bottoni:", bottoni[:30], flush=True)
                pg.screenshot(path=OUT + r"sta10_assegnazioni.png")
                for lab in ("Cancella Assegnazione", "Cancella", "Elimina"):
                    btn = pg.get_by_role("button", name=lab)
                    if btn.count():
                        btn.first.click(force=True, timeout=4000); time.sleep(1.0)
                        chiudi_modale(pg, ("Conferma", "OK", "Si", "Cancella", "Elimina"))
                        fatto_ui = True; esito_undo = "interfaccia: bottone «%s» in Assegnazioni" % lab
                        break
            except Exception as exc:
                print("annullamento dall'interfaccia fallito:", str(exc)[:160], flush=True)
            finally:
                pg.set_default_timeout(30000)
            if not fatto_ui:
                # ripiego: si toglie l'ultimo pick da localStorage (per il ponte
                # e' identico a un annullamento fatto dall'app)
                pg.evaluate("""() => {
                    const K = 'FANTA-ASTA-2025-LIVE';
                    const d = JSON.parse(localStorage.getItem(K));
                    for (const uid in d._users) {
                      const u = d._users[uid];
                      if (Array.isArray(u.picks) && u.picks.length) u.picks.pop();
                    }
                    localStorage.setItem(K, JSON.stringify(d));
                }""")
                esito_undo = "ripiego: pick tolto da localStorage (interfaccia non collaborativa in headless)"
            scarti += 1
            t0 = time.time()
            ok = False
            while time.time() - t0 < 15:
                if cop("/copilot/state")["n_events"] == n_prima - 1:
                    ok = True; break
                time.sleep(0.3)
            print("annullamento:", esito_undo, "-> undo nel Copilota:", ok,
                  "(%.1fs)" % (time.time() - t0))
            if not ok:
                anomalie.append("annullamento non propagato: n_events resta %s"
                                % cop("/copilot/state")["n_events"])
            # torna alla lista calciatori
            try:
                pg.get_by_text("Lista Calciatori", exact=True).first.click(timeout=5000); time.sleep(1.2)
                cerca = pg.locator("input[placeholder='Cerca...']").first
            except Exception as exc:
                print("ritorno alla lista:", str(exc)[:100])

        # --- a meta': ricaricamento e reiniezione ----------------------------
        if fatti == 31 and esito_reload == "non provato":
            n_prima = cop("/copilot/state")["n_events"]
            pg.reload(wait_until="networkidle"); time.sleep(4)
            inietta(pg); time.sleep(5)
            n_dopo = cop("/copilot/state")["n_events"]
            esito_reload = "n_events %d -> %d" % (n_prima, n_dopo)
            print("ricaricamento + reiniezione:", esito_reload)
            if n_dopo != n_prima:
                anomalie.append("dopo il ricaricamento gli eventi sono cambiati: %s" % esito_reload)
            cerca = pg.locator("input[placeholder='Cerca...']").first

    durata = time.time() - t_inizio
    time.sleep(3)
    u = stato_fa(pg)
    st = cop("/copilot/state")
    a, c = attesi_fa(u, st["names"]), acquisti_cop(st)
    solo_fa = sorted(set(a) - set(c))
    solo_cop = sorted(set(c) - set(a))
    print("\n=== CONFRONTO ===")
    print("picks vivi in FantaAsta: %d | acquisti nel Copilota: %d" % (len(a), len(c)))
    print("solo in FantaAsta:", solo_fa[:10])
    print("solo nel Copilota:", solo_cop[:10])
    nomi_fa = {str(x["id"]): x["name"] for x in u["players"]}
    print("\n%-4s %-22s %-10s %6s %6s" % ("#", "giocatore", "squadra", "FA", "COP"))
    dettaglio = {}
    for pid, ti, pr in c:
        dettaglio[(pid, ti)] = pr
    for n, (pid, ti, pr) in enumerate(a[:70], 1):
        print("%-4d %-22s %-10s %6d %6s" % (n, nomi_fa.get(pid, pid)[:22], st["names"][ti], pr,
                                            dettaglio.get((pid, ti), "MANCA")))
    print("\nbudget per squadra (FantaAsta / Copilota):")
    bud_fa = {t["id"]: t.get("currentBudget") for t in u["teams"]}
    for i, t in enumerate(st["teams"]):
        fa_t = next((x for x in u["teams"] if (x.get("name") or "").strip().lower() == t["name"].strip().lower()), None)
        speso_fa = (BUDGET - bud_fa[fa_t["id"]]) if fa_t and bud_fa.get(fa_t["id"]) is not None else None
        speso_cop = BUDGET - t["budget"]
        stella = "" if speso_fa == speso_cop else "   <-- DIVERSO"
        print("  %-8s speso FA %-6s speso COP %-6s%s" % (t["name"], speso_fa, speso_cop, stella))
        if speso_fa != speso_cop:
            anomalie.append("budget diverso per %s: FA %s, Copilota %s" % (t["name"], speso_fa, speso_cop))

    print("\nassegnazioni fatte: %d, annullate: %d, durata %.0f s" % (fatti, scarti, durata))
    if ritardi:
        print("ritardo pick -> Copilota: medio %.2fs, min %.2fs, max %.2fs"
              % (sum(ritardi) / len(ritardi), min(ritardi), max(ritardi)))
    print("annullamento:", esito_undo)
    print("ricaricamento:", esito_reload)
    stato_ponte = pg.evaluate("() => window.PONTE ? window.PONTE.stato() : null")
    print("PONTE.stato(): inviati=%s errori=%s"
          % (len(stato_ponte["inviati"]) if stato_ponte else None,
             (stato_ponte or {}).get("errori", [])[-6:]))
    print("riquadro:", pg.evaluate("() => { const d = document.getElementById('ponte-fantaoracle-box'); return d ? d.innerText : null; }"))
    print("discrepanze totali: %d" % (len(solo_fa) + len(solo_cop)))
    print("ANOMALIE:", json.dumps(anomalie, ensure_ascii=False, indent=1) if anomalie else "nessuna")
    print("ultimi avvisi console PONTE:", [c2 for c2 in console if "PONTE" in c2][-8:])
    pg.screenshot(path=OUT + r"\asta10_fine.png", full_page=False)
    b.close()
