"""Prove del modulo che riduce il valore atteso degli indisponibili."""
from __future__ import annotations

import datetime as dt
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from fantabot.rettifica_indisponibili import (giornate_perse, prossima_giornata,
                                              rettifica_valori)

# calendario finto: una giornata a settimana dal 22 agosto, 38 giornate
CAL = {g: dt.date(2026, 8, 22) + dt.timedelta(days=7 * (g - 1)) for g in range(1, 39)}
OGGI = dt.date(2026, 9, 10)          # fra la 3a (5/9) e la 4a (12/9)


def test_prossima_giornata():
    assert prossima_giornata(CAL, OGGI) == 4
    assert prossima_giornata(CAL, dt.date(2026, 8, 22)) == 1


def test_rientro_a_data_conta_le_giornate_prima():
    perse, come = giornate_perse({"rientro_stima": "2026-10-05", "testo": ""}, CAL, OGGI)
    # giornate 4 (12/9), 5 (19/9), 6 (26/9), 7 (3/10) iniziano prima del 5/10
    assert perse == 4 and come == "rientro 2026-10-05"


def test_rientro_a_gennaio_e_meta_stagione():
    perse, _ = giornate_perse({"rientro_stima": "2027-01", "testo": "lungo stop"}, CAL, OGGI)
    assert 15 <= perse <= 18


def test_stima_sospetta_usa_il_testo():
    voce = {"rientro_stima": "G1", "stima_sospetta": True,
            "testo": "Stop di circa 25 giorni, recuperabile dalla fine di settembre"}
    perse, come = giornate_perse(voce, CAL, OGGI)
    assert come.startswith("dal testo") and 2 <= perse <= 3


def test_da_valutare_vale_una_giornata():
    perse, come = giornate_perse({"rientro_stima": None, "testo": "Da valutare in settimana."},
                                 CAL, OGGI)
    assert perse == 1


def test_squalifica_una_giornata():
    perse, come = giornate_perse({"tipo": "squalifica", "rientro_stima": "G4",
                                  "testo": "squalificato nella 4a giornata"}, CAL, OGGI)
    assert perse == 1 and come == "squalifica"


def test_rettifica_proporzionale_e_dichiarata():
    pred = {"a": {"value": 200.0, "value_up": 240.0, "q50": 10.0},
            "b": {"value": 100.0, "q50": 5.0}}
    ind = {"a": {"rientro_stima": "2027-01", "testo": "lungo stop"}}
    nuove, rett = rettifica_valori(pred, ind, CAL, OGGI)
    assert "a" in rett and "b" not in rett
    r = rett["a"]
    f = (r["su"] - r["giornate_perse"]) / r["su"]
    assert 0.4 <= f <= 0.6 and abs(r["fattore"] - f) < 1e-3
    assert abs(nuove["a"]["value"] - 200.0 * f) < 1e-6
    assert abs(nuove["a"]["value_up"] - 240.0 * f) < 1e-6
    assert nuove["a"]["q50"] == 10.0                # i prezzi non si toccano
    assert nuove["a"]["value_originale"] == 200.0
    assert pred["a"]["value"] == 200.0             # l'originale resta intatto
