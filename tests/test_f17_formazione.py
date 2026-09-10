"""Prove di scripts/f17_formazione.py su rosa sintetica (niente rete, niente pack).

Criteri fissati PRIMA di guardare qualunque numero:
A1 modulo scelto fra i sette di lineup.py;
A2 esattamente 11 titolari, con i conteggi del modulo;
A3 un indisponibile non e' titolare se il suo reparto offre un'alternativa
   disponibile; resta titolare (con avviso) se il reparto non basta;
A4 panchina senza doppioni e disgiunta dai titolari; rosa = titolari+panchina;
A5 due esecuzioni sugli stessi ingressi danno la stessa uscita;
A6 giornata senza righe nelle probabili -> errore chiaro che nomina giornata e file.
Nessun criterio sul punteggio: una giornata sola non valida niente.
"""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

_spec = importlib.util.spec_from_file_location(
    "f17_formazione", ROOT / "scripts" / "f17_formazione.py")
f17 = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(f17)

from fantabot.season.lineup import MODULES  # noqa: E402

QUOTE = {"P": 3, "D": 8, "C": 8, "A": 6}


def rosa_sintetica():
    """25 giocatori: 3 P, 8 D, 8 C, 6 A, punteggi attesi decrescenti."""
    anagrafe, attesi, rosa = {}, {}, []
    for ruolo, n in QUOTE.items():
        for i in range(n):
            pid = f"{ruolo}{i}"
            rosa.append(pid)
            anagrafe[pid] = {"nome": f"{ruolo}iocatore{i}", "ruolo": ruolo,
                             "squadra": f"SQ{i}"}
            attesi[pid] = {"fv": 9.0 - i * 0.5, "voto": 6.5 - i * 0.2}
    return rosa, anagrafe, attesi


def probabili_sintetiche(rosa, pct=90.0):
    return {pid: {"squadra": "SQA", "avversario": "SQB", "casa": True,
                  "nome": pid, "ruolo": pid[0], "pct": pct,
                  "stato": "titolare", "ballottaggio_con": ""}
            for pid in rosa}


def calcola(rosa, anagrafe, attesi, probabili, indisponibili):
    righe = f17.righe_giocatori(rosa, anagrafe, attesi, probabili, indisponibili)
    modulo, titolari, panchina = f17.scegli_formazione(righe)
    return righe, modulo, titolari, panchina


def test_modulo_valido_e_undici_titolari():
    rosa, anagrafe, attesi = rosa_sintetica()
    _, modulo, titolari, _ = calcola(rosa, anagrafe, attesi,
                                     probabili_sintetiche(rosa), {})
    assert (modulo["D"], modulo["C"], modulo["A"]) in MODULES        # A1
    assert modulo["P"] == 1
    assert sum(len(v) for v in titolari.values()) == 11              # A2
    for ruolo, n in modulo.items():
        assert len(titolari[ruolo]) == n


def test_panchina_senza_doppioni():
    rosa, anagrafe, attesi = rosa_sintetica()
    _, modulo, titolari, panchina = calcola(rosa, anagrafe, attesi,
                                            probabili_sintetiche(rosa), {})
    in_campo = [p for r in "PDCA" for p in titolari[r]]
    in_panca = [p for r in "PDCA" for p in panchina[r]]
    assert len(set(in_panca)) == len(in_panca)                       # A4
    assert not set(in_campo) & set(in_panca)
    assert sorted(in_campo + in_panca) == sorted(rosa)
    assert len(in_panca) == len(rosa) - 11


def test_indisponibile_esce_se_esiste_alternativa():
    rosa, anagrafe, attesi = rosa_sintetica()
    # D0 e' il difensore migliore: indisponibile, il reparto ha 7 alternative
    ind = {"D0": {"tipo": "infortunio", "testo": "lesione"}}
    righe, modulo, titolari, panchina = calcola(
        rosa, anagrafe, attesi, probabili_sintetiche(rosa), ind)
    assert "D0" not in titolari["D"]                                 # A3
    assert panchina["D"][-1] == "D0"                                 # in fondo
    assert next(x for x in righe if x["pid"] == "D0")["p_gioca"] == 0.0


def test_indisponibile_resta_se_reparto_non_basta():
    """Con un solo portiere indisponibile, lo schieramento avviene lo stesso:
    e' il comportamento del motore ('a volte capita di giocare in meno')."""
    rosa, anagrafe, attesi = rosa_sintetica()
    rosa = [p for p in rosa if p not in ("P1", "P2")]
    ind = {"P0": {"tipo": "squalifica", "testo": "squalificato"}}
    _, _, titolari, _ = calcola(rosa, anagrafe, attesi,
                                probabili_sintetiche(rosa), ind)
    assert titolari["P"] == ["P0"]                                   # A3 (2a meta')


def test_assente_dalle_probabili_vale_zero():
    rosa, anagrafe, attesi = rosa_sintetica()
    prob = probabili_sintetiche(rosa)
    del prob["A0"]
    righe, _, titolari, _ = calcola(rosa, anagrafe, attesi, prob, {})
    riga = next(x for x in righe if x["pid"] == "A0")
    assert riga["p_gioca"] == 0.0 and riga["punteggio"] == 0.0
    assert "A0" not in titolari["A"]


def test_deterministico():
    rosa, anagrafe, attesi = rosa_sintetica()
    prob = probabili_sintetiche(rosa)
    a = calcola(rosa, anagrafe, attesi, prob, {})[1:]
    b = calcola(list(reversed(rosa)), anagrafe, attesi, prob, {})[1:]
    assert a == b                                                    # A5


def test_giornata_senza_probabili_errore_chiaro(tmp_path):
    csvp = tmp_path / "probabili_20260910.csv"
    csvp.write_text(
        "giornata,squadra,avversario,casa,nome,ruolo,pct_titolarita,stato,"
        "lista,ballottaggio_con,pct_ballottaggio,player_id\n"
        "4,Venezia,Fiorentina,1,Tizio,p,90,titolare,titolari,,,6248\n",
        encoding="utf-8")
    with pytest.raises(SystemExit) as e:
        f17.leggi_probabili(csvp, 7)
    msg = str(e.value)
    assert "giornata 7" in msg and "probabili_20260910.csv" in msg     # A6
    assert "[4]" in msg


def test_ledger_sintetico(tmp_path):
    led = tmp_path / "ledger_finto.json"
    led.write_text(json.dumps({
        "season": "2026-27", "names": ["Io", "Tu"], "my_index": 0,
        "events": [{"player_id": "P0", "team_index": 0, "price": 10},
                   {"player_id": "D0", "team_index": 1, "price": 5},
                   {"player_id": "P0", "team_index": 0, "price": 10}]}),
        encoding="utf-8")
    stagione, rosa = f17.leggi_ledger(led)
    assert stagione == "2026-27" and rosa == ["P0"]


def test_rosa_insufficiente_errore_chiaro():
    anagrafe = {"P0": {"nome": "P0", "ruolo": "P", "squadra": "SQ"}}
    attesi = {"P0": {"fv": 6.0, "voto": 6.0}}
    righe = f17.righe_giocatori(["P0"], anagrafe, attesi,
                                probabili_sintetiche(["P0"]), {})
    with pytest.raises(SystemExit) as e:
        f17.scegli_formazione(righe)
    assert "rosa insufficiente" in str(e.value)
