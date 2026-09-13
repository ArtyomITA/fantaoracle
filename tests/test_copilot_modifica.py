"""Prove su `/copilot/evento_modifica`: correggere un lotto qualsiasi.

Il 10/9 uno spostamento del lotto 42 e' costato 81 annullamenti e 82
martelletti, perche' la sola correzione disponibile era `undo`, che toglie
dalla coda. Stasera l'utente inserisce tutto a mano: la correzione di un
acquisto a meta' lista deve costare una richiesta sola.

Lo stato non e' inventato: si ricostruisce dall'asta VERA del 10/9/2026
(`data/copilot/ledger_1789058317.json`) troncata ai primi 100 eventi. Il
ledger vero non viene mai toccato: si copia in una cartella temporanea, e il
Copilota salva li'.

NOTA sui numeri del compito: il compito descrive il lotto 42 come «Tavares N.
5620, team 0 -> team 5». Nel ledger vero l'evento 42 e' Tavares N. (5620) ma
appartiene alla squadra **5** (Nightmare fc), che ai 100 eventi ha la difesa
PIENA (8 su 8), mentre la 0 ne ha 7. Il verso utile e' quindi l'opposto:
5 -> 0. Cosi' la squadra che libera lo slot e' la 5, ed e' li' che il
martelletto successivo (Stones) puo' entrare.
"""
from __future__ import annotations

import datetime
import importlib.util
import io
import json
import shutil
import sys
import tempfile
from collections import Counter
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
PACK = ROOT / "data" / "packs" / "pack_2026-27.pkl"
LEDGER = ROOT / "data" / "copilot" / "ledger_1789058317.json"

pytestmark = pytest.mark.skipif(not (PACK.exists() and LEDGER.exists()),
                                reason="pack 2026-27 o ledger del 10/9 assenti")

QUANTI = 100                 # il ledger vero, troncato
EV_TAVARES, ID_TAVARES = 42, "5620"
ID_STONES = "2514"           # difensore mai battuto nei primi 100 lotti


@pytest.fixture(scope="module")
def cop():
    sys.path.insert(0, str(ROOT / "src"))
    spec = importlib.util.spec_from_file_location(
        "cop_modifica_test", ROOT / "scripts" / "f10_copilot.py")
    c = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = c
    spec.loader.exec_module(c)
    c.PACK = c.load_pack("2026-27")
    c.ELEGGIBILITA = c.carica_eleggibilita("2026-27")
    c.prepara_pack("2026-27", oggi=datetime.date(2026, 9, 10))
    with tempfile.TemporaryDirectory(prefix="cop_mod_") as tmp:
        copia = Path(tmp) / "ledger_prova.json"
        shutil.copyfile(LEDGER, copia)          # mai l'originale
        c.LEDGER_PATH = copia
        c._LEDGER = json.loads(LEDGER.read_text(encoding="utf-8"))
        yield c


@pytest.fixture(autouse=True)
def stato(cop):
    """Ogni prova riparte dai primi 100 eventi dell'asta vera."""
    led = cop._LEDGER
    cop.STATE.update({"season": "2026-27", "names": list(led["names"]),
                      "my_index": led["my_index"], "budget": led["budget"],
                      "quotas": dict(led["quotas"]),
                      "events": [dict(e) for e in led["events"][:QUANTI]],
                      "bids": [], "esclusi_manuali": [],
                      "modifiche": [], "modifiche_fatte": [], "undo_fatti": []})
    cop.PIANI_CACHE.clear()
    cop.INDIFF_CACHE.clear()
    cop.rebuild_advisor()
    return cop


def _get(c, path):
    h = c.Handler.__new__(c.Handler)
    h.path = path
    cap = {}
    h._send = lambda obj, code=200: cap.update(body=obj, code=code)
    h.do_GET()
    return cap


def _post(c, path, body):
    h = c.Handler.__new__(c.Handler)
    blob = json.dumps(body).encode()
    h.path, h.headers, h.rfile = path, {"Content-Length": str(len(blob))}, io.BytesIO(blob)
    cap = {}
    h._send = lambda obj, code=200: cap.update(body=obj, code=code)
    h.do_POST()
    return cap


def foto(c) -> list[dict]:
    """Cassa e reparti di ogni squadra, contati a mano dagli eventi."""
    fuori = []
    for i in range(len(c.STATE["names"])):
        miei = [e for e in c.STATE["events"] if e["team_index"] == i]
        ruoli = Counter(c.PACK.players[e["player_id"]].role for e in miei)
        fuori.append({"speso": sum(e["price"] for e in miei),
                      "cassa": c.STATE["budget"] - sum(e["price"] for e in miei),
                      "n": len(miei), "ruoli": dict(ruoli)})
    return fuori


# --------------------------------------------------- (a) spostare il lotto 42
def test_a_spostare_il_lotto_42_di_squadra(cop):
    prima = foto(cop)
    assert cop.STATE["events"][EV_TAVARES]["player_id"] == ID_TAVARES
    assert cop.STATE["events"][EV_TAVARES]["team_index"] == 5
    assert prima[5]["ruoli"]["D"] == 8 and prima[0]["ruoli"]["D"] == 7
    prezzo = cop.STATE["events"][EV_TAVARES]["price"]

    r = _post(cop, "/copilot/evento_modifica",
              {"indice": EV_TAVARES, "team_index": 0})
    assert r["code"] == 200 and r["body"]["ok"] is True, r["body"]
    assert r["body"]["n_events"] == QUANTI          # non si perde una riga
    assert r["body"]["prima"]["team_index"] == 5
    assert r["body"]["dopo"]["team_index"] == 0
    assert r["body"]["dopo"]["price"] == prezzo     # il prezzo non si tocca

    dopo = foto(cop)
    assert dopo[5]["ruoli"]["D"] == 7 and dopo[0]["ruoli"]["D"] == 8
    assert dopo[5]["cassa"] == prima[5]["cassa"] + prezzo
    assert dopo[0]["cassa"] == prima[0]["cassa"] - prezzo
    # e le altre otto squadre non si accorgono di niente
    for i in (1, 2, 3, 4, 6, 7, 8, 9):
        assert dopo[i] == prima[i], i

    # lo stesso lo dicono le rose ricostruite dal server, non solo il conto
    st = _get(cop, "/copilot/state")["body"]
    ids0 = {g["id"] for g in st["teams"][0]["roster"]["D"]}
    ids5 = {g["id"] for g in st["teams"][5]["roster"]["D"]}
    assert ID_TAVARES in ids0 and ID_TAVARES not in ids5
    assert st["teams"][0]["budget"] == dopo[0]["cassa"]
    assert st["teams"][5]["budget"] == dopo[5]["cassa"]
    # la riga corretta e' indirizzabile: indice e richiesta_id in rosa
    riga = next(g for g in st["teams"][0]["roster"]["D"] if g["id"] == ID_TAVARES)
    assert riga["indice"] == EV_TAVARES
    assert riga["richiesta_id"] == cop._LEDGER["events"][EV_TAVARES]["richiesta_id"]

    # la modifica e' a verbale e su disco
    assert len(cop.STATE["modifiche"]) == 1
    voce = cop.STATE["modifiche"][0]
    assert voce["indice"] == EV_TAVARES
    assert voce["prima"]["team_index"] == 5 and voce["dopo"]["team_index"] == 0
    salvato = json.loads(cop.LEDGER_PATH.read_text(encoding="utf-8"))
    assert salvato["events"][EV_TAVARES]["team_index"] == 0
    # le cache dello stato vecchio non possono riapparire come attuali
    assert not cop.PIANI_CACHE and not cop.INDIFF_CACHE


# ------------------------------- (b) lo slot liberato accetta un martelletto
def test_b_dopo_lo_spostamento_lo_slot_liberato_accetta_il_martelletto(cop):
    # prima: la difesa della 5 e' piena e Stones viene rifiutato
    rifiuto = _post(cop, "/copilot/hammer",
                    {"player_id": ID_STONES, "team_index": 5, "price": 2,
                     "richiesta_id": "prova-stones-pieno"})
    assert rifiuto["code"] == 400 and rifiuto["body"]["ok"] is False
    assert "reparto D pieno" in rifiuto["body"]["err"]

    assert _post(cop, "/copilot/evento_modifica",
                 {"indice": EV_TAVARES, "team_index": 0})["body"]["ok"]

    ok = _post(cop, "/copilot/hammer",
               {"player_id": ID_STONES, "team_index": 5, "price": 2,
                "richiesta_id": "prova-stones-ok"})
    assert ok["code"] == 200 and ok["body"]["ok"] is True, ok["body"]
    assert ok["body"]["n_events"] == QUANTI + 1
    assert foto(cop)[5]["ruoli"]["D"] == 8


# ---------------------------------------------- (c) cambiare solo il prezzo
def test_c_cambiare_solo_il_prezzo(cop):
    idx = 10
    prima_ev = dict(cop.STATE["events"][idx])
    ti = prima_ev["team_index"]
    prima_conto = foto(cop)[ti]
    cassa_prima = prima_conto["cassa"]
    prima_reparti, prima_n = dict(prima_conto["ruoli"]), prima_conto["n"]
    nuovo = prima_ev["price"] + 37

    r = _post(cop, "/copilot/evento_modifica", {"indice": idx, "price": nuovo})
    assert r["code"] == 200 and r["body"]["ok"] is True, r["body"]
    assert r["body"]["n_events"] == QUANTI
    ev = cop.STATE["events"][idx]
    assert ev["price"] == nuovo
    assert ev["team_index"] == prima_ev["team_index"]     # la squadra non cambia
    assert ev["player_id"] == prima_ev["player_id"]
    dopo = foto(cop)
    assert dopo[ti]["cassa"] == cassa_prima - 37
    # cambia una cifra sola: reparti e numero di acquisti restano quelli
    assert dopo[ti]["ruoli"] == prima_reparti
    assert dopo[ti]["n"] == prima_n


# -------------------------------- (d) rimuovere un evento in mezzo alla lista
def test_d_rimuovere_un_evento_a_meta_lista(cop):
    idx = 50
    ev = dict(cop.STATE["events"][idx])
    pid, ti, prezzo = ev["player_id"], ev["team_index"], ev["price"]
    assert pid not in cop.pool(solo_eleggibili=False)     # ora e' venduto
    cassa_prima = foto(cop)[ti]["cassa"]

    r = _post(cop, "/copilot/evento_modifica", {"indice": idx, "rimuovi": True})
    assert r["code"] == 200 and r["body"]["ok"] is True, r["body"]
    assert r["body"]["n_events"] == QUANTI - 1
    assert r["body"]["dopo"] is None
    assert r["body"]["prima"]["player_id"] == pid
    assert len(cop.STATE["events"]) == QUANTI - 1
    assert pid in cop.pool(solo_eleggibili=False)         # torna comprabile
    assert foto(cop)[ti]["cassa"] == cassa_prima + prezzo
    # gli eventi dopo scalano di uno, e l'elenco lo dice
    elenco = _get(cop, "/copilot/eventi")["body"]
    assert len(elenco) == QUANTI - 1
    assert elenco[idx]["player_id"] == cop._LEDGER["events"][idx + 1]["player_id"]


# ------------------------------------------------ (e) una modifica illegale
def test_e_modifica_illegale_rifiutata_e_stato_invariato(cop):
    prima = foto(cop)
    eventi_prima = [dict(e) for e in cop.STATE["events"]]
    assert prima[1]["ruoli"]["D"] == 8                    # ammolly ha la difesa piena

    r = _post(cop, "/copilot/evento_modifica",
              {"indice": EV_TAVARES, "team_index": 1})
    assert r["code"] == 400 and r["body"]["ok"] is False
    assert "reparto D" in r["body"]["err"], r["body"]["err"]
    assert cop.STATE["events"] == eventi_prima
    assert foto(cop) == prima
    assert not cop.STATE["modifiche"]

    # un prezzo oltre la cassa e' altrettanto illegale
    r = _post(cop, "/copilot/evento_modifica", {"indice": EV_TAVARES, "price": 999})
    assert r["code"] == 400 and r["body"]["ok"] is False
    assert cop.STATE["events"] == eventi_prima

    # e cosi' un prezzo che non e' un credito intero, o una squadra inesistente
    assert _post(cop, "/copilot/evento_modifica",
                 {"indice": EV_TAVARES, "price": 0})["code"] == 400
    assert _post(cop, "/copilot/evento_modifica",
                 {"indice": EV_TAVARES, "team_index": 99})["code"] == 400
    assert _post(cop, "/copilot/evento_modifica",
                 {"indice": 9999, "price": 3})["code"] == 400
    # senza dire cosa cambiare non si fa niente
    assert _post(cop, "/copilot/evento_modifica", {"indice": 3})["code"] == 400
    # e senza dire quale riga, nemmeno
    assert _post(cop, "/copilot/evento_modifica", {"price": 3})["code"] == 400
    assert cop.STATE["events"] == eventi_prima


# ---------------------------------------------------------- (f) idempotenza
def test_f_stessa_richiesta_due_volte_un_effetto_solo(cop):
    idx = 12
    prima = dict(cop.STATE["events"][idx])
    corpo = {"indice": idx, "price": prima["price"] + 5,
             "richiesta_id_modifica": "mod-uno"}

    r1 = _post(cop, "/copilot/evento_modifica", corpo)
    assert r1["code"] == 200 and r1["body"]["ok"] is True
    assert not r1["body"].get("duplicato")
    stato_dopo = [dict(e) for e in cop.STATE["events"]]

    r2 = _post(cop, "/copilot/evento_modifica", corpo)
    assert r2["code"] == 200 and r2["body"]["ok"] is True
    assert r2["body"]["duplicato"] is True
    assert cop.STATE["events"] == stato_dopo         # nessun secondo +5
    assert len(cop.STATE["modifiche"]) == 1
    assert cop.STATE["events"][idx]["price"] == prima["price"] + 5


def test_f2_indirizzare_per_richiesta_id(cop):
    """La riga si indica anche col `richiesta_id` del martelletto originale."""
    rid = cop.STATE["events"][EV_TAVARES]["richiesta_id"]
    r = _post(cop, "/copilot/evento_modifica",
              {"richiesta_id": rid, "team_index": 0})
    assert r["code"] == 200 and r["body"]["ok"] is True, r["body"]
    assert r["body"]["indice"] == EV_TAVARES
    assert cop.STATE["events"][EV_TAVARES]["team_index"] == 0
    # un richiesta_id che non esiste non indovina una riga a caso
    r = _post(cop, "/copilot/evento_modifica",
              {"richiesta_id": "non-esiste", "team_index": 0})
    assert r["code"] == 400 and "richiesta_id" in r["body"]["err"]


# ------------------------------------------------------- (g) /copilot/eventi
def test_g_elenco_completo_degli_acquisti(cop):
    elenco = _get(cop, "/copilot/eventi")
    assert elenco["code"] == 200
    righe = elenco["body"]
    assert len(righe) == QUANTI == len(cop.STATE["events"])
    assert [r["indice"] for r in righe] == list(range(QUANTI))
    for r, e in zip(righe, cop.STATE["events"]):
        p = cop.PACK.players[e["player_id"]]
        assert r["player_id"] == e["player_id"]
        assert r["nome"] == p.name and r["ruolo"] == p.role
        assert r["squadra"] == p.team                     # il club
        assert r["team_index"] == e["team_index"]
        assert r["acquirente"] == cop.STATE["names"][e["team_index"]]
        assert r["prezzo"] == e["price"]
        assert r["ts"] == e.get("ts")
        assert r["richiesta_id"] == e.get("richiesta_id")
    # l'ultimo tratto e' lo stesso che `last_events` mostra, con lo stesso indice
    st = _get(cop, "/copilot/state")["body"]
    assert [x["indice"] for x in st["last_events"]] == list(range(QUANTI - 15, QUANTI))
    assert st["last_events"][-1]["id"] == righe[-1]["player_id"]


def test_h_undo_dopo_una_modifica_resta_coerente(cop):
    """Le due strade non si pestano i piedi: `undo` toglie sempre l'ultima."""
    assert _post(cop, "/copilot/evento_modifica",
                 {"indice": EV_TAVARES, "team_index": 0})["body"]["ok"]
    ultimo = dict(cop.STATE["events"][-1])
    r = _post(cop, "/copilot/undo", {"richiesta_id": "undo-dopo-modifica"})
    assert r["body"]["ok"] and r["body"]["n_events"] == QUANTI - 1
    assert r["body"]["annullato"]["player_id"] == ultimo["player_id"]
    assert cop.STATE["events"][EV_TAVARES]["team_index"] == 0
