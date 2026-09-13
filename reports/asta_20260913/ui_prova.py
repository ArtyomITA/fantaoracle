# -*- coding: utf-8 -*-
"""Prove della pagina del Copilota (viz/copilot.html) dopo i cambiamenti del 13/9.

Tre bersagli:
  * lo STUB (scratchpad w11/U/stub.py --scarso), che risponde con i campi nuovi
    del contratto e col caso di scarsita' del prototipo A2: qui si verifica che
    la pagina li mostri;
  * lo stesso stub con --vecchio, che i campi nuovi NON li ha: qui si verifica
    che la pagina scriva «—», senza NaN e senza eccezioni;
  * il server VERO (scripts/f10_copilot.py ripreso da una copia troncata del
    ledger del 10/9, porta 8795): la prova vera e propria.

Chrome headless 1366x768. Le immagini finiscono in w11/U/.

Uso: python ui_prova.py [--stub] [--vecchio] [--vero]   (senza argomenti: tutti)
"""
import json, os, re, subprocess, sys, time, urllib.request
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
           r"\scratchpad\w11\U")
STUB = os.path.join(SCRATCH, "stub.py")
PORTA_STUB, PORTA_VECCHIO, PORTA_VERO = 8794, 8796, 8795
LEDGER_VERO = "data/copilot/prove/U_1.json"          # copia troncata, mai l'originale
LEDGER_FONTE = os.path.join(ROOT, "data", "copilot", "ledger_1789058317.json")
EVENTI = 190                                          # lo stato su cui e' fatta la diagnosi

ESITI = []


def esito(nome, ok, dettaglio=""):
    ESITI.append((nome, bool(ok), dettaglio))
    print("  [%s] %s%s" % ("OK " if ok else "NO ", nome, (" — " + dettaglio) if dettaglio else ""))


def attendi(porta, secondi=60):
    fine = time.time() + secondi
    while time.time() < fine:
        try:
            urllib.request.urlopen("http://127.0.0.1:%d/copilot/state" % porta, timeout=3).read()
            return True
        except Exception:
            time.sleep(0.5)
    return False


def prepara_ledger():
    """Copia TRONCATA del ledger vero del 10/9: l'originale non si tocca."""
    with open(LEDGER_FONTE, encoding="utf-8") as f:
        d = json.load(f)
    d["events"] = d.get("events", [])[:EVENTI]
    d["bids"] = []
    fuori = os.path.join(ROOT, LEDGER_VERO.replace("/", os.sep))
    os.makedirs(os.path.dirname(fuori), exist_ok=True)
    with open(fuori, "w", encoding="utf-8") as f:
        json.dump(d, f, ensure_ascii=False)
    for coda in (".lock",):
        p = fuori[:-5] + coda
        if os.path.exists(p):
            os.remove(p)
    return len(d["events"])


def api(porta, rotta):
    with urllib.request.urlopen("http://127.0.0.1:%d%s" % (porta, rotta), timeout=30) as r:
        return json.loads(r.read().decode("utf-8"))


# --------------------------------------------------------------- una passata
def indirizzo(porta, statica):
    """Il Copilota vero non serve i file: la pagina si apre da disco, come fa
    asta_intera.py; lo stub invece serve anche viz/, come il menu."""
    live = "http://127.0.0.1:%d" % porta
    if statica:
        return "%s/viz/copilot.html?live=%s" % (live, live)
    return ("file:///" + quote(os.path.join(ROOT, "viz", "copilot.html").replace("\\", "/"))
            + "?live=" + live)


def passata(pg, porta, etichetta, campi_nuovi, statica=True):
    print("\n=== %s (porta %d) ===" % (etichetta, porta))
    errori, pagina_rotta = [], []
    def console(m):
        if m.type != "error":
            return
        dove = (m.location or {}).get("url", "")
        if "favicon" in dove or "favicon" in m.text:      # il 404 dell'icona non e' un difetto
            return
        if not campi_nuovi and "gol_rosa" in dove:
            return          # il Copilota vecchio non ha la rotta: e' il caso che si sta provando
        errori.append(("%s @ %s" % (m.text, dove))[:220])
    pg.on("console", console)
    pg.on("pageerror", lambda e: pagina_rotta.append(str(e)[:300]))
    pg.goto(indirizzo(porta, statica), wait_until="domcontentloaded", timeout=60000)
    pg.wait_for_selector("#livePillTxt:has-text('LIVE')", timeout=30000)
    pg.wait_for_timeout(2500)

    st = api(porta, "/copilot/state")
    atteso = str((st.get("spendibile") or {}).get("max_ora", "—")) if campi_nuovi else "—"
    letto = pg.inner_text("#hSpendibile").strip()
    esito("%s · #hSpendibile == spendibile.max_ora" % etichetta,
          letto == atteso, "letto %r, atteso %r" % (letto, atteso))

    # ---- Malen al banco a 150
    pg.fill("#q", "Malen")
    pg.wait_for_timeout(700)
    righe = pg.locator("#results .res-row")
    if righe.count():
        righe.first.click()
        pg.wait_for_timeout(600)
        pg.fill("#priceIn", "150")
        pg.wait_for_timeout(1200)
        # il prezzo di indifferenza arriva al giro dopo: la pagina richiede da sola
        pg.wait_for_timeout(3000)
        adv = pg.inner_text("#advice")
        a = api(porta, "/copilot/advice?player_id=5585&price=150")
        mx = a.get("max_consigliato")
        esito("%s · #advice contiene «spendibili»" % etichetta, "spendibili" in adv,
              adv.replace("\n", " | ")[:160])
        esito("%s · #advice contiene max_consigliato (%s)" % (etichetta, mx),
              mx is not None and str(mx) in adv)
        if campi_nuovi:
            # il prezzo di indifferenza e' un MILP in sfondo: puo' metterci
            # decine di secondi. La pagina lo richiede da sola ogni 2 s e non
            # deve sfarfallare (niente classe «wait» sul riquadro).
            t0, sfarfallio = time.time(), 0
            while "in calcolo" in adv and time.time() - t0 < 45:
                pg.wait_for_timeout(500)
                if "wait" in (pg.get_attribute("#advice", "class") or "").split():
                    sfarfallio += 1
                adv = pg.inner_text("#advice")
            esito("%s · indifferenza consegnata in %.0f s (non resta «in calcolo…»)"
                  % (etichetta, time.time() - t0), "in calcolo" not in adv,
                  adv.replace("\n", " | ")[:200])
            esito("%s · il riquadro non sfarfalla mentre aspetta" % etichetta,
                  sfarfallio == 0, "giri col velo grigio: %d" % sfarfallio)
        else:
            esito("%s · campi mancanti scritti «—»" % etichetta, "—" in adv,
                  adv.replace("\n", " | ")[:160])
        pg.screenshot(path=os.path.join(SCRATCH, "ui_%s_banco.png" % etichetta))
        bottom = pg.eval_on_selector("#advice", "e => e.getBoundingClientRect().bottom")
        esito("%s · #advice sopra la piega (bottom %.0f < 768)" % (etichetta, bottom),
              bottom < 768)
        esito("%s · #lotMeta sopra #advice" % etichetta,
              pg.eval_on_selector("#lotMeta", "e => e.getBoundingClientRect().bottom")
              <= pg.eval_on_selector("#advice", "e => e.getBoundingClientRect().top") + 1)
    else:
        esito("%s · Malen nei risultati" % etichetta, False, "nessuna riga")

    # ---- GOL IN ROSA
    n = pg.locator("#golRosa .gr-row").count()
    mie = pg.locator("#golRosa .gr-row.mia").count()
    if campi_nuovi:
        esito("%s · #golRosa ha 10 righe" % etichetta, n == 10, "righe %d" % n)
        esito("%s · la mia riga e' evidenziata (.mia)" % etichetta, mie == 1, "righe .mia %d" % mie)
    else:
        testo = pg.inner_text("#golRosa")
        esito("%s · #golRosa degrada con un avviso" % etichetta,
              n == 0 and "non manda ancora" in testo, testo.replace("\n", " ")[:120])

    # ---- pillole dell'ordinamento
    pg.fill("#q", "")
    pg.click("#rolePills .rp[data-role='A']")
    pg.wait_for_timeout(900)
    pg.click("#ordPills .op[data-ord='valore']")
    pg.wait_for_timeout(300)
    primo_val = pg.locator("#results .res-row .pn").first.inner_text().strip()
    pg.click("#ordPills .op[data-ord='gol']")
    pg.wait_for_timeout(300)
    primo_gol = pg.locator("#results .res-row .pn").first.inner_text().strip()
    gol_primo = pg.locator("#results .res-row .num.gol b").first.inner_text().strip()
    if campi_nuovi:
        esito("%s · «gol» mette davanti un bomber (>= 14)" % etichetta,
              gol_primo.isdigit() and int(gol_primo) >= 14,
              "primo per gol %s (%s gol), primo per valore %s" % (primo_gol, gol_primo, primo_val))
        esito("%s · le pillole cambiano davvero l'ordine" % etichetta, primo_gol != primo_val)
        pg.click("#ordPills .op[data-ord='misto']")
        pg.wait_for_timeout(300)
        esito("%s · pillola «misto» non rompe la lista" % etichetta,
              pg.locator("#results .res-row").count() > 0)
    else:
        esito("%s · colonna gol scrive ND senza dato" % etichetta, gol_primo == "ND",
              "letto %r" % gol_primo)

    # ---- riga scarsita'
    testo_sc = pg.inner_text("#scarsita") if pg.locator("#scarsita").count() else ""
    if campi_nuovi:
        esito("%s · riga SCARSITA' con ATTACCO e verdetto" % etichetta,
              "ATTACCO" in testo_sc and ("STRETTO" in testo_sc or "OK" in testo_sc),
              testo_sc.replace("\n", " ")[:140])
    else:
        esito("%s · riga SCARSITA' nascosta senza dati" % etichetta,
              not pg.locator("#scarsita").is_visible())

    # ---- RIGORISTI aperto di default
    esito("%s · pannello RIGORISTI aperto" % etichetta, pg.locator("#rigBody").is_visible())

    # ---- niente NaN, niente undefined, console pulita
    corpo = pg.inner_text("body")
    brutti = [w for w in ("NaN", "undefined", "[object Object]") if w in corpo]
    esito("%s · nessun NaN/undefined nel testo" % etichetta, not brutti, ", ".join(brutti))
    esito("%s · nessuna eccezione di pagina" % etichetta, not pagina_rotta, " | ".join(pagina_rotta))
    esito("%s · console senza errori" % etichetta, not errori, " | ".join(errori[:3]))

    img = os.path.join(SCRATCH, "ui_%s.png" % etichetta)
    pg.screenshot(path=img, full_page=False)
    print("  immagine: %s" % img)
    img2 = os.path.join(SCRATCH, "ui_%s_intera.png" % etichetta)
    pg.screenshot(path=img2, full_page=True)
    print("  immagine intera: %s" % img2)


def main():
    quali = ([a for a in sys.argv[1:] if a in ("--stub", "--vecchio", "--vero")]
             or ["--stub", "--vecchio", "--vero"])
    procs = []
    try:
        if "--stub" in quali:
            procs.append(("stub", subprocess.Popen(
                [sys.executable, STUB, str(PORTA_STUB), "--scarso"], cwd=SCRATCH,
                stdout=open(os.path.join(SCRATCH, "stub.log"), "w"),
                stderr=subprocess.STDOUT)))
            if not attendi(PORTA_STUB):
                print("stub non risponde"); return 2
        if "--vecchio" in quali:
            procs.append(("vecchio", subprocess.Popen(
                [sys.executable, STUB, str(PORTA_VECCHIO), "--vecchio"], cwd=SCRATCH,
                stdout=open(os.path.join(SCRATCH, "stub_vecchio.log"), "w"),
                stderr=subprocess.STDOUT)))
            if not attendi(PORTA_VECCHIO):
                print("stub «vecchio» non risponde"); return 2
        if "--vero" in quali:
            n = prepara_ledger()
            print("ledger di prova: %s (%d acquisti)" % (LEDGER_VERO, n))
            procs.append(("vero", subprocess.Popen(
                # `--resume` sulla COPIA troncata: il server scrive solo li',
                # il ledger vero dell'asta del 10/9 non si tocca
                [sys.executable, "scripts/f10_copilot.py", "2026-27",
                 "--porta", str(PORTA_VERO), "--resume", LEDGER_VERO], cwd=ROOT,
                stdout=open(os.path.join(SCRATCH, "server_vero.log"), "w"),
                stderr=subprocess.STDOUT)))
            if not attendi(PORTA_VERO, 240):
                print("server vero non risponde: vedi w11/U/server_vero.log")
                quali = [q for q in quali if q != "--vero"]

        with sync_playwright() as p:
            b = p.chromium.launch(channel="chrome", headless=True)
            ctx = b.new_context(viewport={"width": 1366, "height": 768})
            if "--stub" in quali:
                pg = ctx.new_page(); passata(pg, PORTA_STUB, "stub", True); pg.close()
            if "--vecchio" in quali:
                pg = ctx.new_page()
                pg.context.clear_cookies()
                passata(pg, PORTA_VECCHIO, "vecchio", False)
                pg.close()
            if "--vero" in quali:
                pg = ctx.new_page()
                vero = api(PORTA_VERO, "/copilot/state")
                nuovi = "spendibile" in vero
                print("il server vero manda i campi nuovi:", nuovi)
                passata(pg, PORTA_VERO, "vero", nuovi, statica=False)
                pg.close()
                if not nuovi:
                    manca = [c for c in ("spendibile", "calore_per_ruolo", "scarsita")
                             if c not in vero]
                    print("\nMANCANO ancora nel server vero (/copilot/state): " + ", ".join(manca))
                    a = api(PORTA_VERO, "/copilot/advice?player_id=5585&price=150")
                    mancaA = [c for c in ("max_spendibile", "calore_ruolo", "cap_bot",
                                          "prezzo_indifferenza", "stato_indifferenza",
                                          "e_bomber", "bomber_rimasti", "squadre_contendenti",
                                          "quota_scarsita", "motivo_tetto", "con_lui",
                                          "senza_di_lui") if c not in a]
                    print("MANCANO in /copilot/advice: " + ", ".join(mancaA))
                    try:
                        api(PORTA_VERO, "/copilot/gol_rosa")
                        print("/copilot/gol_rosa: c'e'")
                    except Exception as e:
                        print("/copilot/gol_rosa: manca (%s)" % e)
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
