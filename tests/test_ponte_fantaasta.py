"""Prove sul ponte FantaAsta: bookmarklet, pagina, invarianti del sorgente js.

Non c'e' un motore JavaScript in questo ambiente, quindi il comportamento del
ponte si prova con Playwright (scratchpad w8/asta10_ponte.py). Qui si controlla
cio' che si puo' controllare da Python: il bookmarklet e' valido e riporta al
sorgente, la pagina contiene il link, e il sorgente rispetta i vincoli
dell'app FantaAsta (console.log e' disabilita: solo console.warn).
"""
import re
import sys
from pathlib import Path
from urllib.parse import unquote

RADICE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RADICE / "scripts"))

import ponte_bookmarklet as pb   # noqa: E402

SORGENTE = (RADICE / "viz" / "ponte_fantaasta.js").read_text(encoding="utf-8")


def test_bookmarklet_e_valido_e_decodifica_al_sorgente():
    bm = pb.bookmarklet(SORGENTE, 8770)
    assert bm.startswith("javascript:(function(){")
    assert bm.endswith("})()")
    assert " " not in bm and "\n" not in bm       # un preferito e' una riga sola
    dentro = unquote(bm[len("javascript:(function(){"):-len("})()")])
    assert dentro.startswith("window.PONTE_COPILOTA='http://127.0.0.1:8770';")
    assert dentro.endswith(SORGENTE)


def test_bookmarklet_porta_scelta():
    assert "127.0.0.1%3A8792" in pb.bookmarklet(SORGENTE, 8792)


def test_pagina_contiene_link_e_istruzioni():
    pagina = pb.scrivi_pagina(8770)
    html = pagina.read_text(encoding="utf-8")
    assert 'id="bm"' in html and 'href="javascript:(function(){' in html
    assert "PONTE FantaAsta" in html
    assert "prova connessione" in html
    assert "local-network-access-check" in html
    assert "/copilot/state" in html
    # il sorgente e' incorporato per rigenerare il link quando cambia la porta
    assert "PONTE_COPILOTA" in html


def test_sorgente_usa_solo_console_warn():
    # l'app stampa "[APP] CONSOLE DISABLED": console.log non arriva a nessuno
    assert "console.log(" not in SORGENTE      # citarlo in un commento va bene
    assert "console.warn" in SORGENTE


def test_sorgente_gestisce_i_casi_duri():
    for atteso in ("released", "svincolato", "assegnazione modificata",
                   "inesistente", "non raggiungibile", "PONTE_INVIATI_",
                   "/copilot/undo", "/copilot/hammer", "richiesta_id"):
        assert atteso in SORGENTE, atteso
    assert re.search(r"stato:\s*\(\)\s*=>", SORGENTE)          # window.PONTE.stato()
    assert "position:fixed" in SORGENTE and "width:240px" in SORGENTE   # riquadro
