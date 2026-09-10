"""Genera il bookmarklet del ponte FantaAsta e la pagina viz/ponte.html.

Il ponte (viz/ponte_fantaasta.js) deve girare DENTRO la scheda di FantaAsta
Live. Incollarlo ogni volta nella console e' scomodo, quindi lo si impacchetta
in un preferito: `javascript:(function(){...})()` con il sorgente URL-encoded.
La pagina viz/ponte.html - servita dal menu su http://localhost:8899 - contiene
il link da trascinare nella barra dei preferiti, un campo per la porta del
Copilota (rigenera il link) e una prova di connessione.

Uso:  python scripts/ponte_bookmarklet.py [--porta 8770]
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from urllib.parse import quote

RADICE = Path(__file__).resolve().parent.parent
SORGENTE = RADICE / "viz" / "ponte_fantaasta.js"
PAGINA = RADICE / "viz" / "ponte.html"
PORTA_DEFAULT = 8770


def bookmarklet(js: str, porta: int = PORTA_DEFAULT) -> str:
    """Sorgente del ponte -> URL `javascript:` pronto per un preferito.

    Il prefisso fissa la porta del Copilota; il resto e' il file cosi' com'e'
    (e' gia' una IIFE). Si codifica tutto: i preferiti non sopportano `%`,
    spazi e ritorni a capo non codificati.
    """
    corpo = "window.PONTE_COPILOTA='http://127.0.0.1:%d';%s" % (int(porta), js)
    return "javascript:(function(){%s})()" % quote(corpo, safe="")


PAGINA_HTML = """<!doctype html>
<html lang="it">
<head>
<meta charset="utf-8">
<title>Ponte FantaAsta -> Copilota</title>
<style>
 body {{ font: 15px/1.5 system-ui, Arial, sans-serif; margin: 0; padding: 24px;
        background: #10151f; color: #e8f0ff; }}
 .wrap {{ max-width: 780px; margin: 0 auto; }}
 h1 {{ font-size: 22px; margin: 0 0 4px; }}
 p.sub {{ color: #9fb3d1; margin: 0 0 20px; }}
 .card {{ background: #182233; border: 1px solid #24334c; border-radius: 10px;
         padding: 16px 18px; margin-bottom: 16px; }}
 a.bm {{ display: inline-block; background: #2ea043; color: #fff; text-decoration: none;
        font-weight: 700; padding: 10px 18px; border-radius: 8px; cursor: grab; }}
 input {{ background: #0e1626; color: #e8f0ff; border: 1px solid #2b3b57;
         border-radius: 6px; padding: 6px 8px; font: inherit; width: 90px; }}
 button {{ background: #1f6feb; color: #fff; border: 0; border-radius: 6px;
          padding: 7px 14px; font: inherit; cursor: pointer; }}
 ol {{ padding-left: 22px; }}
 li {{ margin-bottom: 8px; }}
 code {{ background: #0e1626; padding: 1px 5px; border-radius: 4px; }}
 #esito {{ margin-top: 10px; white-space: pre-line; font-size: 13px; color: #9fb3d1; }}
 .ko {{ color: #ff7b72; }} .ok {{ color: #7ee787; }}
</style>
</head>
<body>
<div class="wrap">
<h1>Ponte FantaAsta -&gt; Copilota</h1>
<p class="sub">Ogni assegnazione fatta su FantaAsta Live finisce nel Copilota da sola.</p>

<div class="card">
  <p>Porta del Copilota: <input id="porta" type="number" value="{porta}"> &nbsp;
     <button id="prova">prova connessione</button></p>
  <p><b>Trascina questo link nella barra dei preferiti di Chrome:</b></p>
  <p><a class="bm" id="bm" href="{href}">PONTE FantaAsta</a></p>
  <div id="esito"></div>
</div>

<div class="card">
<b>Come si usa</b>
<ol>
<li>Avvia il <b>Copilota</b> dal menu e fai il setup con <b>GLI STESSI NOMI</b> delle
    squadre di FantaAsta (stesso ordine se possibile: senza corrispondenza di nome
    il ponte abbina per posizione).</li>
<li>Apri la scheda di <b>FantaAsta Live</b> e clicca il preferito <b>PONTE FantaAsta</b>
    (in alternativa apri F12 &rarr; Console e incolla il contenuto di
    <code>viz/ponte_fantaasta.js</code>).</li>
<li>Al prompt di Chrome <b>"consentire l'accesso alla rete locale"</b> clicca
    <b>Consenti</b>. Se il prompt non compare e il riquadro in basso a destra dice
    <b>ERRORE</b>: apri <code>chrome://flags/#local-network-access-check</code>,
    metti <b>Disabled</b> e riavvia Chrome.</li>
<li>Dopo ogni <b>ricaricamento</b> della pagina di FantaAsta il preferito va
    <b>ricliccato</b>: le assegnazioni gia' inviate sono ricordate, quindi niente
    doppioni.</li>
</ol>
<p>In basso a destra su FantaAsta compare un riquadro:
   <code>PONTE: N assegnazioni inviate - ultimo giro hh:mm:ss - OK/ERRORE</code>.
   Per lo stato completo, in console: <code>window.PONTE.stato()</code>;
   per fermarlo: <code>window.PONTE.ferma()</code>.</p>
</div>
</div>

<script>
const JS = {js_json};
function costruisci(porta) {{
  return "javascript:(function(){{" +
    encodeURIComponent("window.PONTE_COPILOTA='http://127.0.0.1:" + porta + "';" + JS) +
    "}})()";
}}
const campo = document.getElementById("porta");
const link = document.getElementById("bm");
const esito = document.getElementById("esito");
function aggiorna() {{
  const p = parseInt(campo.value, 10) || {porta};
  link.href = costruisci(p);
  esito.textContent = "";
}}
campo.addEventListener("input", aggiorna);
document.getElementById("prova").addEventListener("click", async () => {{
  const p = parseInt(campo.value, 10) || {porta};
  esito.className = ""; esito.textContent = "prova su 127.0.0.1:" + p + "...";
  try {{
    const r = await fetch("http://127.0.0.1:" + p + "/copilot/state");
    const d = await r.json();
    const n = (d.names || []);
    esito.className = n.length ? "ok" : "ko";
    esito.textContent = n.length
      ? "Copilota vivo su " + p + " - " + n.length + " squadre: " + n.join(", ")
      : "Copilota vivo su " + p + " ma il tavolo non e' configurato: fai il setup.";
  }} catch (e) {{
    esito.className = "ko";
    esito.textContent = "nessuna risposta su 127.0.0.1:" + p +
      " - il Copilota e' avviato su quella porta? (" + e.message + ")";
  }}
}});
aggiorna();
</script>
</body>
</html>
"""


def scrivi_pagina(porta: int = PORTA_DEFAULT) -> Path:
    js = SORGENTE.read_text(encoding="utf-8")
    PAGINA.write_text(
        PAGINA_HTML.format(porta=int(porta), href=bookmarklet(js, porta),
                           js_json=json.dumps(js)),
        encoding="utf-8")
    return PAGINA


if __name__ == "__main__":
    argv = sys.argv[1:]
    porta = int(argv[argv.index("--porta") + 1]) if "--porta" in argv else PORTA_DEFAULT
    js = SORGENTE.read_text(encoding="utf-8")
    bm = bookmarklet(js, porta)
    p = scrivi_pagina(porta)
    print(f"sorgente: {SORGENTE} ({len(js)} caratteri)")
    print(f"bookmarklet: {len(bm)} caratteri, porta {porta}")
    print(f"pagina: {p}  ->  http://localhost:8899/viz/ponte.html")
