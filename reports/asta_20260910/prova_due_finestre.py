"""Due finestre: FantaAsta headless (con il ponte) e la PAGINA del Copilota servita dal
menu (8899) collegata a un Copilota di prova su 8793. Dopo ogni pick in FantaAsta la
pagina del Copilota deve mostrare l'acquisto entro 3 s."""
import json, sys, time, urllib.request
from playwright.sync_api import sync_playwright
sys.stdout.reconfigure(encoding="utf-8")
OUT = r"C:\Users\ADMINI~1\AppData\Local\Temp\claude\E--claudecode-pesante\5ff20539-b495-4ac4-bed4-79eabbf8a8b7\scratchpad\w8"
COP = "http://127.0.0.1:8793"
PONTE = open(r"viz\ponte_fantaasta.js", encoding="utf-8").read()
NOMI = ["Io", "Marco", "Luca", "Giulia", "Andrea", "Sara", "Paolo", "Chiara", "Davide", "Elena"]

def cop(path, body=None):
    req = urllib.request.Request(COP + path, data=json.dumps(body).encode() if body else None,
                                 headers={"Content-Type": "application/json"}, method="POST" if body else "GET")
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.loads(r.read().decode("utf-8"))

def chiudi_modale(pg, preferiti):
    m = pg.locator("nz-modal-container:visible")
    if not m.count(): return None
    btns = m.first.locator("button"); nomi = [b.inner_text().strip() for b in btns.all()]
    for pref in preferiti:
        for i, n in enumerate(nomi):
            if n.lower().startswith(pref.lower()):
                btns.nth(i).click(); time.sleep(1.2); return n

print("setup:", cop("/copilot/setup", {"names": NOMI, "my_index": 0, "budget": 500}))
with sync_playwright() as p:
    b = p.chromium.launch(channel="chrome", headless=True, args=["--disable-features=LocalNetworkAccessChecks,PrivateNetworkAccessChecks,PrivateNetworkAccessRespectPreflightResults"])
    fa = b.new_page(viewport={"width": 1366, "height": 768})
    fa.goto("https://fanta-asta-live.fantacalcio.it/#/main", wait_until="networkidle", timeout=60000); time.sleep(3)
    for i in range(4):
        fa.get_by_text("Aggiungi", exact=False).first.click(timeout=5000); time.sleep(0.7)
    fa.get_by_text("INIZIA", exact=True).first.click(timeout=5000); time.sleep(2)
    chiudi_modale(fa, ("Serie A",)); time.sleep(3)
    fa.evaluate("window.PONTE_COPILOTA = '%s'" % COP); fa.evaluate(PONTE); time.sleep(1)
    # seconda finestra: la pagina del Copilota dal menu
    ui = b.new_page(viewport={"width": 1366, "height": 768})
    errs = []
    ui.on("pageerror", lambda e: errs.append(str(e)[:200]))
    ui.goto("http://localhost:8899/viz/copilot.html?live=" + COP, wait_until="networkidle", timeout=60000); time.sleep(3)
    print("pagina Copilota:", ui.inner_text("body").replace("\n", " | ")[:200])
    ritardi = []
    for nome in ("Malen", "Martinez L.", "Hojlund", "Paz N.", "Dimarco"):
        fa.locator("ui-player-row", has_text=nome).first.click(timeout=8000); time.sleep(0.8)
        t0 = time.time()
        fa.get_by_role("button", name="PICK!").first.click(timeout=5000)
        visto = None
        for _ in range(40):
            time.sleep(0.25)
            txt = ui.inner_text("body")
            if nome in txt.split("ULTIMI ACQUISTI")[-1]:
                visto = time.time() - t0; break
        ritardi.append((nome, visto))
        print(f"  pick {nome}: nella pagina del Copilota dopo {visto and round(visto, 2)} s")
    st = cop("/copilot/state")
    print("Copilota API:", [(t["name"], t["budget"], [x["nome"] for r in "PDCA" for x in t["roster"][r]]) for t in st["teams"] if t["budget"] != 500])
    tav = ui.inner_text("body").split("IL TAVOLO")[-1][:300].replace("\n", " ")
    print("IL TAVOLO nella pagina:", tav)
    fa.screenshot(path=OUT + r"\due_fantaasta.png"); ui.screenshot(path=OUT + r"\due_copilota.png")
    print("errori pagina Copilota:", errs)
    print("VERDETTO:", "OK" if all(v is not None and v < 3 for _, v in ritardi) else "NON OK", ritardi)
    b.close()
