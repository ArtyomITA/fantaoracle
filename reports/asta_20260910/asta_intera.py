# -*- coding: utf-8 -*-
"""Asta intera giocata DALLA PAGINA vera (viz/copilot.html) con guasti.

250 lotti (P30, D80, C80, A60), chiamata a rotazione, controlli a ogni lotto:
pagina contro /copilot/state, console pulita, tempi (consiglio < 1,5 s,
martelletto->VENDUTO < 3 s, piani < 25 s), nessun budget negativo, nessun
reparto oltre quota. Guasti previsti: undo doppio dopo il lotto 60, esclusione
e riammissione (100/110), uccisione del server e ripresa dopo il 150.

Uso: python asta_intera.py [--lotti 250|150] [--limite-min 40]
"""
import argparse, json, math, os, random, subprocess, sys, time
import urllib.error, urllib.parse, urllib.request

PROG = r"fantabot"
PORT = 8794
BASE = "http://127.0.0.1:%d" % PORT
LEDGER_REL = r"data/copilot/prove/ledger_w6_asta.json"
LEDGER = os.path.join(PROG, "data", "copilot", "prove", "ledger_w6_asta.json")
LOCK = LEDGER[:-5] + ".lock"     # `Path.with_suffix(".lock")` del server
W6 = os.path.dirname(os.path.abspath(__file__))
LOG = os.path.join(W6, "asta_intera_log.jsonl")
PAGINA = ("file:///" + urllib.parse.quote(
    os.path.join(PROG, "viz", "copilot.html").replace("\\", "/")) + "?live=" + BASE)
NOMI = ["Io", "Marco", "Luca", "Giulia", "Andrea", "Sara",
        "Paolo", "Chiara", "Davide", "Elena"]
RUOLI = ["P", "D", "C", "A"]
QUOTE = {"P": 3, "D": 8, "C": 8, "A": 6}

for _f in (sys.stdout, sys.stderr):
    try:
        _f.reconfigure(errors="replace", encoding="utf-8")
    except Exception:
        pass

ERRORI = []          # console + pageerror
ANOMALIE = []        # difetti trovati
random.seed(20260910)


def anomalia(grav, titolo, ripro, osservato):
    ANOMALIE.append({"gravita": grav, "titolo": titolo,
                     "riproduzione": ripro, "osservato": osservato})
    print("  ANOMALIA[%s] %s | %s | %s" % (grav, titolo, ripro, osservato))


# ------------------------------------------------------------ http di controllo
def get(path, **q):
    u = BASE + path + ("?" + urllib.parse.urlencode(q) if q else "")
    return json.load(urllib.request.urlopen(u, timeout=180))


def post(path, body):
    r = urllib.request.Request(BASE + path, data=json.dumps(body).encode("utf-8"),
                               headers={"Content-Type": "application/json"}, method="POST")
    try:
        return json.load(urllib.request.urlopen(r, timeout=180))
    except urllib.error.HTTPError as e:
        return json.loads(e.read().decode("utf-8"))


def vivo():
    try:
        urllib.request.urlopen(BASE + "/copilot/state", timeout=2).read()
        return True
    except Exception:
        return False


def avvia(resume=False):
    """Avvia il server di prova; ritorna il Popen."""
    if vivo():
        print("INCONCLUDENTE: la porta %d e' gia' occupata da un altro Copilota" % PORT)
        sys.exit(2)
    args = [sys.executable, "scripts/f10_copilot.py", "2026-27", "--porta", str(PORT),
            "--resume" if resume else "--ledger", LEDGER_REL]
    out = open(os.path.join(W6, "srv_%s.log" % ("resume" if resume else "nuovo")), "ab")
    p = subprocess.Popen(args, cwd=PROG, stdout=out, stderr=subprocess.STDOUT)
    for _ in range(120):
        time.sleep(1)
        if vivo():
            return p
        if p.poll() is not None:
            break
    print("INCONCLUDENTE: server non partito (resume=%s)" % resume)
    sys.exit(2)


def ferma(p):
    if p is None:
        return
    subprocess.run(["taskkill", "/F", "/T", "/PID", str(p.pid)],
                   capture_output=True)
    try:
        p.wait(timeout=10)
    except Exception:
        pass


def senza_accenti(s):
    import unicodedata
    return "".join(ch for ch in unicodedata.normalize("NFKD", str(s).lower())
                   if not unicodedata.combining(ch))


# ------------------------------------------------------------ pagina
def apri(pw, w=1366, h=768):
    b = pw.chromium.launch(headless=True, channel="chrome")
    ctx = b.new_context(viewport={"width": w, "height": h}, accept_downloads=True)
    pg = ctx.new_page()
    pg.on("console", lambda m: ERRORI.append("[console] " + m.text) if m.type == "error" else None)
    pg.on("pageerror", lambda e: ERRORI.append("[pageerror] " + str(e)))
    pg.goto(PAGINA)
    pg.wait_for_function("() => typeof C !== 'undefined' && !!C.state", timeout=60000)
    return b, pg


def setup_da_pagina(pg):
    """Compila il pannello del tavolo: 10 nomi, Io = 0, budget 500."""
    pg.wait_for_selector("#setup:not(.hidden)", timeout=20000)
    pg.fill("#nPart", "10")
    pg.dispatch_event("#nPart", "change")
    pg.wait_for_function("() => document.querySelectorAll('#names input[type=text]').length === 10",
                         timeout=10000)
    for i, n in enumerate(NOMI):
        pg.fill("#names input[type=text] >> nth=%d" % i, n)
    pg.check("#names input[type=radio] >> nth=0")
    pg.fill("#budgetIn", "500")
    pg.click("#btnConfirm")
    pg.wait_for_function("() => C.state && C.state.names && C.state.names.length === 10",
                         timeout=20000)


def stato_pagina(pg):
    return pg.evaluate("""() => [...document.querySelectorAll('#teamRows .team-row')].map(r => ({
        ti: +r.dataset.ti,
        budget: +r.querySelector('.credits').textContent.trim(),
        slots: [...r.querySelectorAll('.slot-group')].map(
            g => [...g.querySelectorAll('.sq')].filter(s => s.style.background).length)}))""")


def confronta(pg, st, tentativi=8):
    """La pagina deve mostrare gli stessi budget e le stesse rose del server."""
    atteso = [{"ti": t["index"], "budget": t["budget"],
               "slots": [len(t["roster"][r]) for r in RUOLI]} for t in st["teams"]]
    vis = None
    for _ in range(tentativi):
        vis = stato_pagina(pg)
        if vis == atteso:
            return True, None
        pg.wait_for_timeout(400)
    return False, {"pagina": vis, "server": atteso}


def cerca_e_seleziona(pg, pid, nome, tutti=False):
    """Digita il nome senza accenti e sceglie la riga giusta. Ritorna
    (t_ricerca, t_consiglio) oppure solleva RuntimeError."""
    if pg.is_checked("#tuttiChk") != tutti:
        pg.set_checked("#tuttiChk", tutti)
        pg.wait_for_timeout(300)
    testo = senza_accenti(nome)
    chiavi = [testo, testo.split()[-1] if " " in testo else testo]
    sel = '.res-row[data-id="%s"]' % pid
    t0 = time.time()
    trovato = False
    for k in chiavi:
        pg.fill("#q", k)
        try:
            pg.wait_for_selector(sel, timeout=6000)
            trovato = True
            break
        except Exception:
            trovato = False
    if not trovato:
        raise RuntimeError("non trovato in ricerca: %s (%s)" % (nome, pid))
    t_ric = time.time() - t0
    t1 = time.time()
    # la lista si ridisegna a ogni giro di ricerca: il click va rifatto sul
    # selettore (non su un ElementHandle vecchio) se la riga si stacca
    ultimo = None
    for _ in range(3):
        try:
            pg.click(sel, timeout=8000)
            ultimo = None
            break
        except Exception as exc:
            ultimo = exc
            pg.wait_for_timeout(400)
    if ultimo is not None:
        raise RuntimeError("riga non cliccabile: %s (%s): %s" % (nome, pid, str(ultimo)[:80]))
    pg.wait_for_function("(pid) => C.advice && C.advice.id === pid", arg=pid, timeout=20000)
    return t_ric, time.time() - t1


def consiglio(pg):
    return pg.evaluate("() => C.advice")


def prezzo(pg, v):
    pg.fill("#priceIn", str(int(v)))
    pg.wait_for_function("(v) => C.price === v", arg=int(v), timeout=5000)


def martella(pg, ti):
    """Click sul martelletto; ritorna (secondi fino a VENDUTO, testo toast)."""
    pg.evaluate("() => { document.getElementById('soldFlash').innerHTML = ''; }")
    t0 = time.time()
    try:
        pg.click('#hammerGrid .hbt[data-ti="%d"]' % ti, timeout=8000)
    except Exception as exc:
        return time.time() - t0, "martelletto non cliccabile: " + str(exc)[:140]
    try:
        pg.wait_for_function(
            "() => (document.getElementById('soldFlash').textContent || '').includes('VENDUTO')",
            timeout=12000)
        return time.time() - t0, None
    except Exception:
        txt = pg.evaluate("""() => [...document.querySelectorAll('.toast, #toasts *')]
            .map(t => t.textContent).join(' | ').slice(0, 200)""")
        return time.time() - t0, txt or "nessun VENDUTO"


def piani(pg, etichetta):
    t0 = time.time()
    pg.click("#piBtn")
    try:
        pg.wait_for_function("() => PI.dati && !PI.caricando", timeout=120000)
    except Exception:
        anomalia("alta", "piani non calcolati", etichetta, "PI.dati vuoto dopo 120 s")
        return None
    dt = time.time() - t0
    schede = pg.evaluate("() => document.querySelectorAll('#piOut [data-pi]').length")
    if schede > 1:
        pg.evaluate("() => document.querySelectorAll('#piOut [data-pi]')[1].click()")
        pg.wait_for_timeout(400)
    testo = pg.evaluate("() => document.getElementById('piOut').textContent.slice(0, 300)")
    if dt > 25:
        anomalia("alta", "piani oltre 25 s", etichetta, "%.1f s" % dt)
    print("  piani %s: %.1f s, %d schede" % (etichetta, dt, schede))
    return {"secondi": round(dt, 2), "schede": schede, "testo": testo}


# ------------------------------------------------------------ scelte d'asta
def pool_ruolo(ruolo, tutti=False):
    q = {"role": ruolo}
    if tutti:
        q["tutti"] = 1
    return get("/copilot/players", **q)


def trova_fuori_lista(ruolo):
    """Un fuori lista del ruolo, ancora nel pool.

    `/copilot/players` tronca a 80 righe ordinate per valore: i fuori lista
    hanno valore basso e non entrano nella lista del ruolo. Si scandisce per
    lettera, che filtra prima del taglio.
    """
    visti = set()
    for lettera in "abcdefghijklmnopqrstuvwxyz":
        for r in get("/copilot/players", role=ruolo, q=lettera, tutti=1):
            if r["id"] in visti:
                continue
            visti.add(r["id"])
            if r.get("fuori_lista"):
                return r
    return None


def liberi(st, ti, ruolo):
    t = st["teams"][ti]
    return QUOTE[ruolo] - len(t["roster"][ruolo])


def max_legale(st, ti):
    return int(st["teams"][ti]["max_bid"])


def scegli_avversario(st, ruolo, prezzo_min=1, escluso_io=True):
    cand = [t["index"] for t in st["teams"]
            if (not escluso_io or t["index"] != 0)
            and liberi(st, t["index"], ruolo) > 0 and max_legale(st, t["index"]) >= prezzo_min]
    if not cand:
        cand = [t["index"] for t in st["teams"]
                if (not escluso_io or t["index"] != 0) and liberi(st, t["index"], ruolo) > 0]
    return random.choice(cand) if cand else None


# ------------------------------------------------------------ corsa
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--lotti", type=int, default=250)
    ap.add_argument("--limite-min", type=float, default=40.0)
    a = ap.parse_args()

    # tavolo nuovo: ledger di prova ripulito
    for p in (LEDGER, LOCK, LEDGER.replace(".json", ".buono.json")):
        if os.path.exists(p):
            os.remove(p)
    if os.path.exists(LOG):
        os.remove(LOG)

    quote_lotti = {"P": 30, "D": 80, "C": 80, "A": 60}
    if a.lotti != 250:
        k = a.lotti / 250.0
        quote_lotti = {r: int(round(n * k)) for r, n in quote_lotti.items()}
    piano_lotti = []
    for r in RUOLI:
        piano_lotti += [r] * quote_lotti[r]
    totale = len(piano_lotti)
    tagli = {"medioD": quote_lotti["P"] + quote_lotti["D"] // 2,
             "medioC": quote_lotti["P"] + quote_lotti["D"] + quote_lotti["C"] // 2,
             "undo": 60, "escl": 100, "riamm": 110, "kill": 150}
    lotti_tutti = {25, quote_lotti["P"] + quote_lotti["D"] + 5}   # con «anche fuori lista»
    lotti_furto = {40, 55, 90, 120, 140, 175}
    primo_A = quote_lotti["P"] + quote_lotti["D"] + quote_lotti["C"] + 1

    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("INCONCLUDENTE: playwright non installato")
        sys.exit(2)

    proc = avvia(resume=False)
    esiti = {"lotti": 0, "furti": 0, "furti_forzati": 0, "fuori_lista": 0,
             "piani": [], "ridotto": a.lotti != 250, "bomber": None}
    t_inizio = time.time()
    attesi = [0]        # acquisti attesi nel registro (lista: la si aggiorna dentro)
    escluso_pid = None
    ultimo = None
    fp = open(LOG, "a", encoding="utf-8")

    with sync_playwright() as pw:
        b, pg = apri(pw)
        setup_da_pagina(pg)
        st = get("/copilot/state")
        if st["names"] != NOMI or st["budget"] != 500 or st["my_index"] != 0:
            anomalia("bloccante", "setup non applicato", "pannello tavolo",
                     json.dumps({"names": st["names"], "budget": st["budget"]})[:200])
        plan = get("/copilot/plan")

        for i, ruolo in enumerate(piano_lotti, start=1):
            rec = {"lotto": i, "ruolo": ruolo, "chiamante": (i - 1) % 10}
            st = get("/copilot/state")
            rimasti_blocco = sum(1 for r in piano_lotti[i - 1:] if r == ruolo)
            io_liberi = liberi(st, 0, ruolo)

            # ---- scelta del giocatore
            usa_tutti = i in lotti_tutti
            forza_furto = (i in lotti_furto) or (i == primo_A)
            cand = None
            if usa_tutti:
                cand = trova_fuori_lista(ruolo)
                if cand is None:
                    usa_tutti = False
            if cand is None and forza_furto:
                tgt = plan.get("target", {}).get(ruolo) or []
                if i == primo_A:
                    tgt = sorted(tgt, key=lambda x: -(x.get("prezzo_atteso") or 0))
                vivi = {p["id"] for p in pool_ruolo(ruolo)}
                tgt = [t for t in tgt if t["id"] in vivi]
                cand = tgt[0] if tgt else None
            if cand is None:
                p40 = pool_ruolo(ruolo)[:40]
                if not p40:
                    anomalia("bloccante", "pool vuoto", "lotto %d ruolo %s" % (i, ruolo), "0 candidati")
                    break
                cand = random.choice(p40)
            pid, nome = cand["id"], cand["nome"]
            rec.update({"id": pid, "nome": nome, "tutti": usa_tutti, "furto_forzato": forza_furto})

            # ---- ricerca, selezione, consiglio
            try:
                t_ric, t_adv = cerca_e_seleziona(pg, pid, nome, tutti=usa_tutti)
            except Exception as exc:
                anomalia("alta", "giocatore non selezionabile dalla pagina",
                         "lotto %d, %s (%s)" % (i, nome, pid), str(exc)[:160])
                rec["errore"] = str(exc)[:160]
                fp.write(json.dumps(rec, ensure_ascii=False) + "\n")
                continue
            adv = consiglio(pg) or {}
            azione = str(adv.get("azione") or "")
            tetto = int(adv.get("max_consigliato") or 0)
            q50 = float(adv.get("q50") or 0)
            rec.update({"azione": azione, "tetto": tetto, "q50": round(q50, 1),
                        "t_ricerca": round(t_ric, 2), "t_consiglio": round(t_adv, 2),
                        "concorrenti_sopra": adv.get("concorrenti_sopra_tetto")})
            if t_adv > 1.5:
                anomalia("alta", "consiglio oltre 1,5 s",
                         "lotto %d, %s" % (i, nome), "%.2f s" % t_adv)
            if tetto > max_legale(st, 0):
                anomalia("alta", "consiglio impossibile: tetto oltre il massimo legale",
                         "lotto %d, %s" % (i, nome),
                         "tetto %d, max legale Io %d" % (tetto, max_legale(st, 0)))

            # ---- chi compra e a quanto
            soglia = int(math.ceil(0.6 * q50)) if q50 else 1
            deve_io = io_liberi > 0 and rimasti_blocco <= io_liberi
            io_compra = False
            if not forza_furto and not usa_tutti:
                if deve_io:
                    io_compra = True
                elif azione == "rilancia" and tetto >= 1 and io_liberi > 0 and random.random() < 0.60:
                    io_compra = True
            if io_compra:
                ti = 0
                px = max(1, min(tetto if tetto >= 1 else 1, max_legale(st, 0)))
            else:
                base = max(1, tetto + 1) if forza_furto else max(1, soglia)
                ti = scegli_avversario(st, ruolo, prezzo_min=base)
                if ti is None:
                    ti = 0
                    px = max(1, min(tetto or 1, max_legale(st, 0)))
                    io_compra = True
                else:
                    mx = max_legale(st, ti)
                    # prezzo casuale >= 60% della mediana e <= massimo legale,
                    # ma tenuto a un tetto plausibile (1,4 x mediana): un
                    # sorteggio uniforme fino al massimo legale svuota le casse
                    # al primo blocco e il resto dell'asta va tutto a 1 credito
                    plaus = max(base, int(math.ceil(1.4 * q50)) if q50 else base, 2)
                    hi = min(mx, max(base, plaus))
                    lo = min(base, hi)
                    px = random.randint(lo, hi) if hi > lo else hi
            rec.update({"compratore": ti, "prezzo": px, "io": io_compra})

            # ---- martelletto
            prezzo(pg, px)
            t_mar, errmar = martella(pg, ti)
            rec["t_martello"] = round(t_mar, 2)
            if errmar is not None:
                anomalia("bloccante", "martelletto senza VENDUTO",
                         "lotto %d, %s -> %s a %d" % (i, nome, NOMI[ti], px), errmar[:180])
                rec["errore_martello"] = errmar[:180]
                fp.write(json.dumps(rec, ensure_ascii=False) + "\n")
                continue
            if t_mar > 3:
                anomalia("alta", "martelletto oltre 3 s",
                         "lotto %d, %s" % (i, nome), "%.2f s" % t_mar)
            if usa_tutti:
                esiti["fuori_lista"] += 1
            in_piano = any(t["id"] == pid for t in (plan.get("target", {}).get(ruolo) or []))
            if in_piano and not io_compra:
                esiti["furti"] += 1
                if forza_furto:
                    esiti["furti_forzati"] += 1
                if i == primo_A:
                    esiti["bomber"] = {"nome": nome, "prezzo": px, "tetto": tetto}
            ultimo = {"id": pid, "nome": nome, "ti": ti, "px": px, "tutti": usa_tutti}

            # ---- controlli
            st2 = get("/copilot/state")
            ok, diff = confronta(pg, st2)
            rec["pagina_ok"] = ok
            if not ok:
                anomalia("bloccante", "pagina e server non coincidono",
                         "lotto %d, dopo %s -> %s" % (i, nome, NOMI[ti]),
                         json.dumps(diff, ensure_ascii=False)[:300])
            for t in st2["teams"]:
                if t["budget"] < 0:
                    anomalia("bloccante", "budget negativo", "lotto %d, %s" % (i, t["name"]),
                             str(t["budget"]))
                for r in RUOLI:
                    if len(t["roster"][r]) > QUOTE[r]:
                        anomalia("bloccante", "reparto oltre quota",
                                 "lotto %d, %s %s" % (i, t["name"], r),
                                 "%d su %d" % (len(t["roster"][r]), QUOTE[r]))
            attesi[0] += 1
            if st2["n_events"] != attesi[0]:
                anomalia("bloccante", "acquisto perso o doppio",
                         "lotto %d, %s -> %s" % (i, nome, NOMI[ti]),
                         "n_events %d, attesi %d" % (st2["n_events"], attesi[0]))
                attesi[0] = st2["n_events"]
            nuovi = [e for e in ERRORI if "favicon" not in e.lower()]
            rec["console"] = len(nuovi)
            esiti["lotti"] += 1
            fp.write(json.dumps(rec, ensure_ascii=False) + "\n")
            fp.flush()
            if i % 10 == 0:
                print("lotto %d/%d %s %s -> %s %d cr (%.1f min)"
                      % (i, totale, ruolo, nome, NOMI[ti], px, (time.time() - t_inizio) / 60))
            if i % 50 == 0:
                pg.screenshot(path=os.path.join(W6, "asta_lotto_%03d.png" % i))

            # ---- guasti previsti
            if i == tagli["medioD"]:
                esiti["piani"].append(("meta D", piani(pg, "meta' blocco D (lotto %d)" % i)))
            if i == tagli["medioC"]:
                esiti["piani"].append(("meta C", piani(pg, "meta' blocco C (lotto %d)" % i)))
            if i == tagli["undo"] and ultimo:
                n0 = get("/copilot/state")["n_events"]
                pg.evaluate("() => document.activeElement && document.activeElement.blur()")
                pg.keyboard.press("u")
                pg.wait_for_timeout(250)
                pg.keyboard.press("u")
                pg.wait_for_function("(n) => C.state && C.state.n_events === n - 1",
                                     arg=n0, timeout=15000)
                n1 = get("/copilot/state")["n_events"]
                if n1 != n0 - 1:
                    anomalia("bloccante", "U-U non annulla", "dopo il lotto 60",
                             "n_events %d -> %d" % (n0, n1))
                cerca_e_seleziona(pg, ultimo["id"], ultimo["nome"], tutti=ultimo["tutti"])
                prezzo(pg, ultimo["px"])
                t_m, err = martella(pg, ultimo["ti"])
                if err:
                    anomalia("bloccante", "riacquisto dopo undo fallito",
                             "dopo il lotto 60, %s" % ultimo["nome"], err[:160])
                n2 = get("/copilot/state")["n_events"]
                attesi[0] = n2
                print("  undo+riacquisto: %d -> %d -> %d" % (n0, n1, n2))
                rec_u = {"lotto": i, "evento": "undo_riacquisto",
                         "n_events": [n0, n1, n2], "t_martello": round(t_m, 2)}
                fp.write(json.dumps(rec_u, ensure_ascii=False) + "\n")
            if i == tagli["escl"]:
                plan = get("/copilot/plan")
                tgt = (plan.get("target", {}).get("A") or [])
                vivi = {p["id"] for p in pool_ruolo("A")}
                tgt = [t for t in tgt if t["id"] in vivi]
                if tgt:
                    escluso_pid = tgt[0]["id"]
                    cerca_e_seleziona(pg, escluso_pid, tgt[0]["nome"])
                    pg.click("#btnEscludi")
                    pg.wait_for_timeout(1500)
                    esc_ok = any(x["id"] == escluso_pid
                                 for x in get("/copilot/state")["esclusi_manuali"])
                    if not esc_ok:
                        anomalia("alta", "esclusione dal piano non registrata",
                                 "dopo il lotto 100, %s" % tgt[0]["nome"], "non in esclusi_manuali")
                    print("  escluso dal piano: %s" % tgt[0]["nome"])
            if i == tagli["riamm"] and escluso_pid:
                info = get("/copilot/players", q="", role="A", tutti=1)
                nm = next((p["nome"] for p in info if p["id"] == escluso_pid), None)
                if nm:
                    cerca_e_seleziona(pg, escluso_pid, nm, tutti=True)
                    pg.click("#btnEscludi")
                    pg.wait_for_timeout(1500)
                    anc = any(x["id"] == escluso_pid
                              for x in get("/copilot/state")["esclusi_manuali"])
                    if anc:
                        anomalia("alta", "riammissione nel piano non registrata",
                                 "dopo il lotto 110, %s" % nm, "ancora in esclusi_manuali")
                    else:
                        print("  riammesso nel piano: %s" % nm)
                    pg.set_checked("#tuttiChk", False)
            if i == tagli["kill"]:
                prima = get("/copilot/state")
                ferma(proc)
                time.sleep(1.5)
                lock = LOCK
                proc = None
                try:
                    proc = avvia(resume=True)
                except SystemExit:
                    if os.path.exists(lock):
                        os.remove(lock)
                        anomalia("media", "lock rimasto dopo l'uccisione del server",
                                 "dopo il lotto 150", "ripresa possibile solo togliendo %s" % lock)
                        proc = avvia(resume=True)
                    else:
                        raise
                pg.reload()
                pg.wait_for_function("() => typeof C !== 'undefined' && C.state && C.state.names.length === 10",
                                     timeout=60000)
                dopo = get("/copilot/state")
                uguale = (prima["n_events"] == dopo["n_events"]
                          and [t["budget"] for t in prima["teams"]] == [t["budget"] for t in dopo["teams"]]
                          and [[len(t["roster"][r]) for r in RUOLI] for t in prima["teams"]]
                          == [[len(t["roster"][r]) for r in RUOLI] for t in dopo["teams"]])
                ok2, diff2 = confronta(pg, dopo)
                if not uguale:
                    anomalia("bloccante", "stato non coincide dopo la ripresa",
                             "kill + --resume dopo il lotto 150",
                             "prima n_events=%d, dopo=%d" % (prima["n_events"], dopo["n_events"]))
                if not ok2:
                    anomalia("bloccante", "pagina ricaricata non coincide col server",
                             "dopo la ripresa", json.dumps(diff2, ensure_ascii=False)[:300])
                print("  ripresa: n_events %d -> %d, pagina ok=%s"
                      % (prima["n_events"], dopo["n_events"], ok2))
                fp.write(json.dumps({"lotto": i, "evento": "kill_resume",
                                     "n_events": [prima["n_events"], dopo["n_events"]],
                                     "stato_uguale": uguale, "pagina_ok": ok2},
                                    ensure_ascii=False) + "\n")

            # ---- il piano cambia con lo stato: si rilegge ogni 20 lotti
            if i % 20 == 0:
                plan = get("/copilot/plan")
            if (time.time() - t_inizio) / 60 > a.limite_min + 15:
                anomalia("media", "corsa troppo lunga: interrotta",
                         "lotto %d" % i, "%.1f min" % ((time.time() - t_inizio) / 60))
                break

        # ---- export dalla pagina
        export = {"da": None}
        try:
            with pg.expect_download(timeout=20000) as d:
                pg.click("#expBtn")
            f = d.value
            export = {"da": "pagina", "file": f.suggested_filename}
            try:
                f.save_as(os.path.join(W6, "export_pagina.json"))
                export["salvato"] = True
            except Exception as exc:
                export["salvato"] = False
                export["nota"] = str(exc)[:120]
        except Exception as exc:
            j = get("/copilot/export")
            with open(os.path.join(W6, "export_api.json"), "w", encoding="utf-8") as g:
                json.dump(j, g, ensure_ascii=False, indent=1)
            export = {"da": "api", "nota": "download non partito in headless: %s" % str(exc)[:100],
                      "chiavi": sorted(j.keys())[:20],
                      "pack": (j.get("bundle") or {}).get("pack") if isinstance(j.get("bundle"), dict) else j.get("pack"),
                      "fonti": bool(j.get("fonti") or j.get("nota"))}
        esiti["export"] = export
        pg.screenshot(path=os.path.join(W6, "asta_finale.png"))
        b.close()

    # ---- verdetti finali
    st = get("/copilot/state")
    io = st["teams"][0]
    esiti["finale"] = {
        "n_events": st["n_events"],
        "rosa_io": {r: len(io["roster"][r]) for r in RUOLI},
        "budget_io": io["budget"],
        "budget_tutti": [t["budget"] for t in st["teams"]],
        "rose_tutti": [[len(t["roster"][r]) for r in RUOLI] for t in st["teams"]],
        "minuti": round((time.time() - t_inizio) / 60, 1),
        "console": [e for e in ERRORI if "favicon" not in e.lower()][:10],
        "furti": esiti["furti"], "fuori_lista": esiti["fuori_lista"],
        "bomber": esiti["bomber"],
    }
    with open(os.path.join(W6, "asta_intera_esiti.json"), "w", encoding="utf-8") as g:
        json.dump({"esiti": esiti, "anomalie": ANOMALIE}, g, ensure_ascii=False, indent=1)
    fp.write(json.dumps({"evento": "fine", "esiti": esiti["finale"]}, ensure_ascii=False) + "\n")
    fp.close()
    print(json.dumps(esiti["finale"], ensure_ascii=False, indent=1))
    print("anomalie: %d" % len(ANOMALIE))

    ferma(proc)
    time.sleep(1)
    if os.path.exists(LOCK):
        os.remove(LOCK)
    print("porta libera: %s" % (not vivo()))
    sys.exit(1 if any(x["gravita"] in ("bloccante", "alta") for x in ANOMALIE) else 0)


if __name__ == "__main__":
    main()
