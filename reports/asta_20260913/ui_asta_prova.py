# -*- coding: utf-8 -*-
"""Prove della pagina nuova dell'asta (viz/asta.html), 13/9/2026.

Due bersagli, tutti e due il server VERO (scripts/f10_copilot.py) avviato da
qui e fermato alla fine:

  * porta 8794, `--resume` su una COPIA TRONCATA a 190 acquisti del ledger del
    10/9 (`data/copilot/prove/G_1.json`): e' il tavolo a meta' asta su cui si
    prova tutto il flusso di assegnazione;
  * porta 8795, `--resume` su un ledger VUOTO (`data/copilot/prove/G_2.json`):
    serve solo per il setup delle dieci squadre.

I ledger veri di `data/copilot/` non si toccano mai.

Chrome headless 1366x768. Le immagini finiscono nello scratch w12/G/.

Uso: python reports/asta_20260913/ui_asta_prova.py [--vero] [--vuoto]
     (senza argomenti: tutte e due)
"""
import json, os, subprocess, sys, time, urllib.request
from urllib.parse import quote
from playwright.sync_api import sync_playwright

for _f in (sys.stdout, sys.stderr):
    try:
        _f.reconfigure(errors="replace", encoding="utf-8")
    except Exception:
        pass

ROOT = r"fantabot"
SCRATCH = (r"C:\Users\ADMINI~1\AppData\Local\Temp\claude"
           r"\E--claudecode-pesante\5ff20539-b495-4ac4-bed4-79eabbf8a8b7"
           r"\scratchpad\w12\G")
PORTA_VERO, PORTA_VUOTO = 8794, 8795
LEDGER_VERO = "data/copilot/prove/G_1.json"      # copia troncata, mai l'originale
LEDGER_VUOTO = "data/copilot/prove/G_2.json"
LEDGER_FONTE = os.path.join(ROOT, "data", "copilot", "ledger_1789058317.json")
EVENTI = 190
MALEN = "5585"
SQUADRA_PROVA = 4        # la quinta maglia: il tasto «5»

ESITI = []


def esito(nome, ok, dettaglio=""):
    ESITI.append((nome, bool(ok), dettaglio))
    print("  [%s] %s%s" % ("OK " if ok else "NO ", nome, (" - " + dettaglio) if dettaglio else ""))


def attendi(porta, secondi=240):
    fine = time.time() + secondi
    while time.time() < fine:
        try:
            urllib.request.urlopen("http://127.0.0.1:%d/copilot/state" % porta, timeout=3).read()
            return True
        except Exception:
            time.sleep(0.5)
    return False


def api(porta, rotta):
    with urllib.request.urlopen("http://127.0.0.1:%d%s" % (porta, rotta), timeout=60) as r:
        return json.loads(r.read().decode("utf-8"))


def prepara_ledger(quanti, dove):
    """Copia del ledger vero, troncata: l'originale resta intatto."""
    with open(LEDGER_FONTE, encoding="utf-8") as f:
        d = json.load(f)
    d["events"] = d.get("events", [])[:quanti]
    d["bids"] = []
    if quanti == 0:
        d["names"] = []
        d["my_index"] = 0
        d["esclusi_manuali"] = []
    fuori = os.path.join(ROOT, dove.replace("/", os.sep))
    os.makedirs(os.path.dirname(fuori), exist_ok=True)
    with open(fuori, "w", encoding="utf-8") as f:
        json.dump(d, f, ensure_ascii=False)
    p = fuori[:-5] + ".lock"
    if os.path.exists(p):
        os.remove(p)
    return len(d["events"])


def indirizzo(porta):
    """Il Copilota non serve i file statici: la pagina si apre da disco, come
    fa reports/asta_20260913/ui_prova.py per il server vero."""
    return ("file:///" + quote(os.path.join(ROOT, "viz", "asta.html").replace("\\", "/"))
            + "?live=" + ("http://127.0.0.1:%d" % porta))


def spia(pg, errori, rotta):
    def console(m):
        if m.type != "error":
            return
        dove = (m.location or {}).get("url", "")
        if "favicon" in dove or "favicon" in m.text:
            return
        if "/copilot/eventi" in dove or "/copilot/eventi" in m.text:
            return            # il 404 e' il caso di degrado che si sta provando
        errori.append(("%s @ %s" % (m.text, dove))[:220])
    pg.on("console", console)
    pg.on("pageerror", lambda e: rotta.append(str(e)[:300]))


def foto(pg, nome):
    p = os.path.join(SCRATCH, nome)
    pg.screenshot(path=p, full_page=False)
    print("     immagine: %s" % p)
    return p


# ------------------------------------------------------------------ il vuoto
def prova_vuoto(pg):
    print("\n=== SETUP su tavolo vuoto (porta %d) ===" % PORTA_VUOTO)
    errori, rotta = [], []
    spia(pg, errori, rotta)
    pg.goto(indirizzo(PORTA_VUOTO), wait_until="domcontentloaded", timeout=60000)
    pg.wait_for_selector("#setup:not([hidden])", timeout=30000)
    esito("setup - il pannello si apre da solo a tavolo vuoto", True)
    caselle = pg.locator("#nomi input[type=text]")
    esito("setup - dieci righe di nome", caselle.count() == 10, "righe %d" % caselle.count())
    for i in range(10):
        caselle.nth(i).fill("Prova%d" % i)
    pg.fill("#budgetIn", "500")
    # il pallino e' nascosto dal CSS: si clicca l'etichetta «IO», come fa l'utente
    pg.click('#nomi .nrow[data-i="9"] .melbl')
    pg.wait_for_timeout(200)
    foto(pg, "G_setup.png")
    pg.click("#btnConferma")
    pg.wait_for_selector("#setup", state="hidden", timeout=30000)
    pg.wait_for_timeout(2500)
    st = api(PORTA_VUOTO, "/copilot/state")
    esito("setup - dieci squadre sul server", len(st.get("names") or []) == 10,
          ", ".join(st.get("names") or [])[:80])
    esito("setup - «io» e' la decima", st.get("my_index") == 9, "my_index %s" % st.get("my_index"))
    esito("setup - 500 crediti", st.get("budget") == 500, "budget %s" % st.get("budget"))
    n = pg.locator("#maglie .mag").count()
    esito("setup - dieci maglie disegnate", n == 10, "maglie %d" % n)
    tuo = pg.locator("#maglie .mag .tuo").count()
    esito("setup - una sola maglia marcata IO", tuo == 1, "marcate %d" % tuo)
    foto(pg, "G_tavolo_nuovo.png")
    esito("setup - nessuna eccezione di pagina", not rotta, " | ".join(rotta))
    esito("setup - console senza errori", not errori, " | ".join(errori[:3]))


# ------------------------------------------------------------------- il vero
def prova_vero(pg):
    print("\n=== ASTA a meta' strada (porta %d, %d acquisti) ===" % (PORTA_VERO, EVENTI))
    errori, rotta = [], []
    spia(pg, errori, rotta)
    pg.goto(indirizzo(PORTA_VERO), wait_until="domcontentloaded", timeout=60000)
    pg.wait_for_selector("#collegaTxt:has-text('COLLEGATO')", timeout=30000)
    pg.wait_for_timeout(2200)

    st = api(PORTA_VERO, "/copilot/state")
    atteso = str((st.get("spendibile") or {}).get("max_ora", "-"))
    esito("testata - PUOI SPENDERE ORA == spendibile.max_ora",
          pg.inner_text("#tvOra").strip() == atteso,
          "letto %r, atteso %r" % (pg.inner_text("#tvOra").strip(), atteso))
    esito("testata - dieci maglie", pg.locator("#maglie .mag").count() == 10)

    # ---- 1366x768: niente barra orizzontale, il necessario sopra la piega
    largh = pg.evaluate("() => [document.documentElement.scrollWidth, window.innerWidth]")
    esito("1366x768 - nessuno scorrimento orizzontale", largh[0] <= largh[1] + 1,
          "scrollWidth %d, finestra %d" % (largh[0], largh[1]))
    for sel, nome in (("#q", "ricerca"), ("#banco", "al banco"), ("#consiglio", "consiglio"),
                      ("#maglie", "le dieci maglie"), ("#btnAggiudica", "AGGIUDICA"),
                      ("#btnUndo", "annulla ultimo"), ("#classifica", "gol in rosa"),
                      ("#tabellone", "ultimi acquisti")):
        r = pg.eval_on_selector(sel, "e => e.getBoundingClientRect()")
        esito("1366x768 - %s visibile senza scorrere" % nome,
              r["bottom"] <= 768 and r["top"] >= 0 and r["height"] > 0,
              "top %.0f bottom %.0f" % (r["top"], r["bottom"]))

    # ---- tabellone completo: i prezzi devono essere numeri, non «—»
    righe_tutte = pg.locator("#tuttiAcq .acq")
    esito("tutti gli acquisti - il tabellone completo e' pieno", righe_tutte.count() >= 100,
          "righe %d, %s" % (righe_tutte.count(), pg.inner_text("#acqDx")))
    prezzi = [righe_tutte.nth(i).locator(".pr").inner_text().strip() for i in range(min(8, righe_tutte.count()))]
    esito("tutti gli acquisti - i prezzi sono numeri", all(p.isdigit() for p in prezzi),
          ", ".join(prezzi))

    # ---- ricerca «malen» -> Invio -> AL BANCO
    pg.click("#q")
    pg.fill("#q", "malen")
    pg.wait_for_selector("#risultati .ris", timeout=15000)
    esito("ricerca - «malen» trova qualcuno", pg.locator("#risultati .ris").count() >= 1,
          pg.inner_text("#risultati").replace("\n", " | ")[:90])
    pg.press("#q", "Enter")
    pg.wait_for_timeout(900)
    banco = pg.inner_text("#banco")
    esito("banco - al banco c'e' Malen", "Malen" in banco, banco.replace("\n", " | ")[:110])
    esito("banco - la ricerca si e' svuotata", pg.input_value("#q") == "")

    # il prezzo di indifferenza e' un MILP di sfondo: la pagina lo richiede da
    # sola ogni 2 s, il numero grande non deve restare vuoto
    t0 = time.time()
    tetto = pg.inner_text("#tvTetto").strip()
    while (not tetto.isdigit()) and time.time() - t0 < 30:
        pg.wait_for_timeout(500)
        tetto = pg.inner_text("#tvTetto").strip()
    a = api(PORTA_VERO, "/copilot/advice?player_id=%s&price=1" % MALEN)
    esito("banco - TETTO e' un numero (%s)" % tetto, tetto.isdigit(),
          "server: max_consigliato %s" % a.get("max_consigliato"))
    grande = pg.inner_text("#consiglio .cons-tetto .n").strip()
    esito("banco - il numero grande e' il tetto del server", grande == tetto,
          "grande %r, testata %r" % (grande, tetto))
    t1 = time.time()
    testo = pg.inner_text("#consiglio")
    while "in calcolo" in testo and time.time() - t1 < 45:
        pg.wait_for_timeout(500)
        testo = pg.inner_text("#consiglio")
    esito("banco - indifferenza consegnata in %.0f s" % (time.time() - t1),
          "in calcolo" not in testo, testo.replace("\n", " | ")[:150])
    esito("banco - il riquadro dice «spendibili»", "spendibili" in testo)

    # ---- prezzo 150 -> Invio, poi il tasto della maglia
    pg.click("#prezzo")
    pg.fill("#prezzo", "150")
    pg.press("#prezzo", "Enter")
    pg.wait_for_timeout(700)
    esito("prezzo - il campo dice 150", pg.input_value("#prezzo") == "150")
    pg.keyboard.press("5")
    pg.wait_for_timeout(400)
    scelta = pg.inner_text("#magliaScelta").strip()
    nome5 = st["names"][SQUADRA_PROVA]
    esito("tasto 5 - la quinta maglia e' scelta", nome5 in scelta, "letto %r" % scelta)
    esito("tasto 5 - la maglia si accende",
          pg.locator('#maglie .mag[data-ti="%d"].scelta' % SQUADRA_PROVA).count() == 1)
    esito("AGGIUDICA - il bottone e' pronto", not pg.locator("#btnAggiudica").is_disabled(),
          pg.inner_text("#btnAggiudica").replace("\n", " ")[:80])
    # la prova che conta: con un giocatore al banco il consiglio si allunga e
    # non deve spingere il martelletto sotto la piega
    for sel, nome in (("#banco", "al banco"), ("#consiglio", "consiglio"),
                      ("#maglie", "le dieci maglie"), ("#btnAggiudica", "AGGIUDICA")):
        r = pg.eval_on_selector(sel, "e => e.getBoundingClientRect()")
        esito("col banco pieno - %s ancora sopra la piega" % nome,
              r["bottom"] <= 768 and r["top"] >= 0 and r["height"] > 0,
              "top %.0f bottom %.0f" % (r["top"], r["bottom"]))
    largh2 = pg.evaluate("() => [document.documentElement.scrollWidth, window.innerWidth]")
    esito("col banco pieno - nessuno scorrimento orizzontale", largh2[0] <= largh2[1] + 1,
          "scrollWidth %d" % largh2[0])
    foto(pg, "G_banco_malen.png")

    prima = api(PORTA_VERO, "/copilot/state")
    cassa_prima = prima["teams"][SQUADRA_PROVA]["budget"]

    # ---- Invio = martelletto
    pg.keyboard.press("Enter")
    pg.wait_for_timeout(2600)
    dopo = api(PORTA_VERO, "/copilot/state")
    rosa = dopo["teams"][SQUADRA_PROVA]["roster"].get("A", [])
    riga = [p for p in rosa if str(p.get("id")) == MALEN]
    esito("martelletto - Malen e' nella quinta maglia", bool(riga),
          "attacco: " + ", ".join("%s %s" % (p["nome"], p["prezzo"]) for p in rosa))
    esito("martelletto - prezzo 150", bool(riga) and riga[0].get("prezzo") == 150,
          "prezzo %s" % (riga[0].get("prezzo") if riga else "-"))
    esito("martelletto - crediti scesi di 150",
          dopo["teams"][SQUADRA_PROVA]["budget"] == cassa_prima - 150,
          "%s -> %s" % (cassa_prima, dopo["teams"][SQUADRA_PROVA]["budget"]))
    esito("martelletto - un acquisto in piu'", dopo["n_events"] == prima["n_events"] + 1,
          "%s -> %s" % (prima["n_events"], dopo["n_events"]))
    pg.wait_for_timeout(1200)
    tab = pg.inner_text("#tabellone")
    esito("tabellone - Malen in cima agli ultimi acquisti",
          "Malen" in tab.split("\n")[0] or "Malen" in tab[:120], tab.replace("\n", " | ")[:110])
    magl = pg.inner_text('#maglie .mag[data-ti="%d"]' % SQUADRA_PROVA)
    esito("maglia - la quinta mostra i crediti aggiornati",
          str(cassa_prima - 150) in magl, magl.replace("\n", " | ")[:90])
    esito("dopo il martelletto - il banco si e' svuotato",
          "Nessuno al banco" in pg.inner_text("#banco"))
    esito("dopo il martelletto - il fuoco e' tornato alla ricerca",
          pg.evaluate("() => document.activeElement && document.activeElement.id") == "q")
    foto(pg, "G_dopo_martelletto.png")

    # ---- correggi: pannello e degrado quando manca l'endpoint
    ha_eventi = True
    try:
        api(PORTA_VERO, "/copilot/eventi")
    except Exception:
        ha_eventi = False
    print("     il server ha /copilot/eventi:", ha_eventi)
    pg.locator("#tabellone .acq").first.click()
    pg.wait_for_selector("#correggi:not([hidden])", timeout=10000)
    corpo = pg.inner_text("#corrCorpo")
    esito("correggi - il pannello si apre cliccando un acquisto", "correggi" in corpo.lower(),
          corpo.replace("\n", " | ")[:110])
    esito("correggi - ci sono le dieci maglie", pg.locator("#corrCorpo .corr-m").count() == 10)
    foto(pg, "G_correggi.png")
    if ha_eventi:
        # sposta l'acquisto dalla quinta alla sesta maglia e ricontrolla
        pg.click('#corrCorpo .corr-m[data-cti="%d"]' % (SQUADRA_PROVA + 1))
        pg.click("#corrOk")
        pg.wait_for_timeout(2500)
        d2 = api(PORTA_VERO, "/copilot/state")
        sesta = [p for p in d2["teams"][SQUADRA_PROVA + 1]["roster"].get("A", [])
                 if str(p.get("id")) == MALEN]
        quinta = [p for p in d2["teams"][SQUADRA_PROVA]["roster"].get("A", [])
                  if str(p.get("id")) == MALEN]
        esito("correggi - Malen spostato alla sesta maglia", bool(sesta) and not quinta,
              "sesta %d, quinta %d" % (len(sesta), len(quinta)))
    else:
        spento = pg.locator("#corrOk").is_disabled() and pg.locator("#corrVia").is_disabled()
        esito("correggi - senza l'endpoint i bottoni sono spenti", spento)
        esito("correggi - e la pagina spiega perche'",
              "evento_modifica" in corpo and "aggiorna il Copilota" in corpo,
              corpo.replace("\n", " | ")[:160])
        pg.keyboard.press("Escape")
        pg.wait_for_timeout(300)
        esito("correggi - Esc chiude il pannello", pg.locator("#correggi").is_hidden())

    # ---- U due volte: si annulla
    pg.click("body", position={"x": 700, "y": 740})
    pg.wait_for_timeout(200)
    n_prima = api(PORTA_VERO, "/copilot/state")["n_events"]
    pg.keyboard.press("u")
    pg.wait_for_timeout(400)
    esito("annulla - il primo U arma il bottone",
          "confermi" in pg.inner_text("#btnUndo").lower(),
          pg.inner_text("#btnUndo").replace("\n", " ")[:90])
    pg.keyboard.press("u")
    pg.wait_for_timeout(2600)
    n_dopo = api(PORTA_VERO, "/copilot/state")["n_events"]
    esito("annulla - il secondo U toglie l'ultimo acquisto", n_dopo == n_prima - 1,
          "%s -> %s" % (n_prima, n_dopo))

    # ---- la pagina deve reggere anche uno schermo grande
    pg.set_viewport_size({"width": 1920, "height": 1080})
    pg.wait_for_timeout(600)
    l3 = pg.evaluate("() => [document.documentElement.scrollWidth, window.innerWidth]")
    esito("1920x1080 - nessuno scorrimento orizzontale", l3[0] <= l3[1] + 1, "scrollWidth %d" % l3[0])
    for sel, nome in (("#q", "ricerca"), ("#maglie", "le dieci maglie"), ("#btnAggiudica", "AGGIUDICA")):
        r = pg.eval_on_selector(sel, "e => e.getBoundingClientRect()")
        esito("1920x1080 - %s sopra la piega" % nome, r["bottom"] <= 1080 and r["height"] > 0,
              "bottom %.0f" % r["bottom"])
    foto(pg, "G_1920.png")
    pg.set_viewport_size({"width": 1366, "height": 768})
    pg.wait_for_timeout(400)

    # ---- niente NaN, niente undefined, console pulita
    pg.wait_for_timeout(1200)
    testo_pagina = pg.inner_text("body")
    brutti = [w for w in ("NaN", "undefined", "[object Object]") if w in testo_pagina]
    esito("nessun NaN/undefined a schermo", not brutti, ", ".join(brutti))
    esito("nessuna eccezione di pagina", not rotta, " | ".join(rotta))
    esito("console senza errori", not errori, " | ".join(errori[:3]))
    foto(pg, "G_fine.png")
    p = os.path.join(SCRATCH, "G_pagina_intera.png")
    pg.screenshot(path=p, full_page=True)
    print("     immagine intera: %s" % p)


def main():
    quali = ([a for a in sys.argv[1:] if a in ("--vero", "--vuoto")] or ["--vero", "--vuoto"])
    os.makedirs(SCRATCH, exist_ok=True)
    procs = []
    try:
        if "--vero" in quali:
            n = prepara_ledger(EVENTI, LEDGER_VERO)
            print("ledger di prova: %s (%d acquisti)" % (LEDGER_VERO, n))
            procs.append(("vero", subprocess.Popen(
                [sys.executable, "scripts/f10_copilot.py", "2026-27",
                 "--porta", str(PORTA_VERO), "--resume", LEDGER_VERO], cwd=ROOT,
                stdout=open(os.path.join(SCRATCH, "srv_vero.log"), "w"),
                stderr=subprocess.STDOUT)))
            if not attendi(PORTA_VERO):
                print("il server vero non risponde: vedi w12/G/srv_vero.log")
                return 2
        if "--vuoto" in quali:
            prepara_ledger(0, LEDGER_VUOTO)
            procs.append(("vuoto", subprocess.Popen(
                [sys.executable, "scripts/f10_copilot.py", "2026-27",
                 "--porta", str(PORTA_VUOTO), "--resume", LEDGER_VUOTO], cwd=ROOT,
                stdout=open(os.path.join(SCRATCH, "srv_vuoto.log"), "w"),
                stderr=subprocess.STDOUT)))
            if not attendi(PORTA_VUOTO):
                print("il server vuoto non risponde: vedi w12/G/srv_vuoto.log")
                return 2

        with sync_playwright() as p:
            b = p.chromium.launch(channel="chrome", headless=True)
            ctx = b.new_context(viewport={"width": 1366, "height": 768})
            if "--vuoto" in quali:
                pg = ctx.new_page(); prova_vuoto(pg); pg.close()
            if "--vero" in quali:
                pg = ctx.new_page(); prova_vero(pg); pg.close()
            ctx.close(); b.close()
    finally:
        for nome, pr in procs:
            pr.terminate()
            try:
                pr.wait(timeout=10)
            except Exception:
                pr.kill()
            print("fermato il server %s" % nome)

    ko = [n for n, ok, _ in ESITI if not ok]
    print("\nVERDETTO: %d prove, %d fallite%s"
          % (len(ESITI), len(ko), (" -> " + "; ".join(ko)) if ko else ""))
    return 1 if ko else 0


if __name__ == "__main__":
    raise SystemExit(main())
