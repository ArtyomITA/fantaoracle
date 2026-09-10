"""Prove di regressione sul Copilota d'asta (`scripts/f10_copilot.py`).

Il modulo si carica per percorso, come fa il menu, e lavora su un ledger in
una cartella temporanea: nessuna sessione vera viene toccata. Le prove
richiedono il pack 2026-27 e il file di eleggibilita'; se mancano vengono
saltate, non falsificate.
"""
from __future__ import annotations

import importlib.util
import io
import json
import sys
import tempfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
PACK = ROOT / "data" / "packs" / "pack_2026-27.pkl"

pytestmark = pytest.mark.skipif(not PACK.exists(), reason="pack 2026-27 assente")


@pytest.fixture(scope="module")
def cop():
    sys.path.insert(0, str(ROOT / "src"))
    spec = importlib.util.spec_from_file_location(
        "cop_test", ROOT / "scripts" / "f10_copilot.py")
    c = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = c
    spec.loader.exec_module(c)
    c.PACK = c.load_pack("2026-27")
    c.ELEGGIBILITA = c.carica_eleggibilita("2026-27")
    c.prepara_pack("2026-27", oggi=__import__("datetime").date(2026, 9, 10))
    with tempfile.TemporaryDirectory(prefix="cop_test_") as tmp:
        c.LEDGER_PATH = Path(tmp) / "ledger.json"
        c.STATE.update({"season": "2026-27",
                        "names": [f"T{i}" for i in range(10)], "my_index": 0,
                        "budget": 500, "quotas": {"P": 3, "D": 8, "C": 8, "A": 6},
                        "events": [], "bids": []})
        c.rebuild_advisor()
        yield c


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


def test_ricerca_senza_accenti(cop):
    assert cop.senza_accenti("Calò") == "calo"
    assert cop.senza_accenti("Laurientè") == "lauriente"
    accentati = [p for p in cop.PACK.players.values()
                 if any(ord(ch) > 127 for ch in p.name)]
    if not accentati:
        pytest.skip("nessun nome accentato nel pack")
    p = accentati[0]
    piatto = cop.senza_accenti(p.name)
    r = _get(cop, f"/copilot/players?q={piatto}")
    assert r["code"] == 200
    assert any(x["id"] == p.player_id for x in r["body"]), \
        f"«{piatto}» non trova {p.name}"


def test_piani_riferimento_uguale_al_piano_del_bot(cop):
    """Il «riferimento» dei piani alternativi e' la rosa che il banco consiglia:
    stesso MILP, stessi vincoli, compresa la quota di spesa in attacco."""
    cop.PIANI_CACHE.clear()
    r = cop.piani_alternativi(2)
    assert r["stato"] == "ok"
    rif = r["piani"][0]
    ids = {x["id"] for ids in rif["rosa"].values() for x in ids}
    assert ids == set(cop.ADVISOR.targets), (
        f"solo nel riferimento: {sorted(ids - set(cop.ADVISOR.targets))}; "
        f"solo nel bot: {sorted(set(cop.ADVISOR.targets) - ids)}")
    assert not rif.get("vincolo_attacco_rilassato")


def test_advice_prezzo_non_numerico_risponde_400(cop):
    pid = next(iter(cop.PACK.players))
    r = _get(cop, f"/copilot/advice?player_id={pid}&price=abc")
    assert r["code"] == 400
    assert "prezzo" in r["body"]["err"]
    r = _get(cop, f"/copilot/advice?player_id={pid}&price=10.5")
    assert r["code"] == 400
    r = _get(cop, f"/copilot/advice?player_id={pid}&price=10")
    assert r["code"] == 200 and r["body"]["azione"]


def test_tetto_mai_oltre_il_massimo_legale(cop):
    top = _get(cop, "/copilot/players?role=A")["body"][:5]
    for p in top:
        d = cop.decisione_operativa(p["id"], None)
        assert d["max_consigliato"] <= d["max_legale"]


def test_indisponibili_valore_rettificato_e_dichiarato(cop):
    """Chi e' fermo per mesi vale meno per il piano, e lo si dice.

    Se il pack e' piu' recente delle fonti, gli infortuni sono gia' dentro
    (f9_apply_market) e qui NON si rettifica: contare due volte e' l'errore."""
    if not cop.RETTIFICHE:
        assert "gia' dentro il pack" in cop.RETTIFICA_MOTIVO, cop.RETTIFICA_MOTIVO
        # e il pack lo dimostra: un infortunio lungo ha presenze attese basse
        lunghi = [pid for pid, v in cop.ELEGGIBILITA["indisponibili"].items()
                  if str(v.get("rientro_stima") or "").startswith("2027")
                  and pid in cop.PACK.b_predictions]
        assert lunghi
        assert cop.PACK.b_predictions[lunghi[0]].get("pres", 99) < 25
        return
    lunghi = [pid for pid, r in cop.RETTIFICHE.items() if r["giornate_perse"] >= 10]
    assert lunghi, "nessun infortunio lungo riconosciuto"
    pid = lunghi[0]
    info = cop.player_info(pid)
    assert info["value"] < info["value_originale"]
    assert info["rettifica"]["fattore"] < 0.75
    # i prezzi non si toccano
    assert info["q50"] == cop.PACK.b_predictions[pid]["q50"]
    # il bot usa il valore rettificato
    assert cop.ADVISOR._q(pid, "value") == info["value"]


def test_senza_previsione_registrabili(cop):
    dett = cop.ELEGGIBILITA.get("senza_previsione") or []
    if not dett:
        pytest.skip("nessun attivo senza previsione")
    pid = str(dett[0]["id"])
    assert pid in cop.PACK.players
    d = cop.decisione_operativa(pid, None)
    assert d["max_consigliato"] <= 5
    r = _post(cop, "/copilot/hammer", {"player_id": pid, "team_index": 3, "price": 2,
                                       "richiesta_id": "sp1"})
    assert r["body"]["ok"] is True
    _post(cop, "/copilot/undo", {"richiesta_id": "usp1"})


def test_escludi_dal_piano(cop):
    cop.PIANI_CACHE.clear()
    target = next(iter(cop.ADVISOR.targets))
    r = _post(cop, "/copilot/escludi", {"player_id": target, "escluso": True})
    assert r["body"]["ok"] and target not in cop.ADVISOR.targets
    assert target not in cop.pool()
    d = cop.decisione_operativa(target, None)
    assert d["azione"] == "nessuna offerta" and d.get("escluso_manuale")
    st = _get(cop, "/copilot/state")["body"]
    assert any(x["id"] == target for x in st["esclusi_manuali"])
    r = _post(cop, "/copilot/escludi", {"player_id": target, "escluso": False})
    assert r["body"]["ok"] and target in cop.pool()


def test_ricerca_per_pertinenza_e_tutti(cop):
    r = _get(cop, "/copilot/players?q=martinez")["body"]
    nomi = [x["nome"] for x in r]
    if len(nomi) >= 2:
        assert all(cop.senza_accenti(n).startswith("martinez") for n in nomi)
    r = _get(cop, "/copilot/players?q=martinez%20j")["body"]
    if r:
        assert r[0]["nome"].lower().startswith("martinez j")
    fuori = next(iter(cop.ELEGGIBILITA["esclusi"]))
    nome = cop.senza_accenti(cop.PACK.players[fuori].name)[:6]
    senza = {x["id"] for x in _get(cop, f"/copilot/players?q={nome}")["body"]}
    con = {x["id"] for x in _get(cop, f"/copilot/players?q={nome}&tutti=1")["body"]}
    assert fuori not in senza and fuori in con


def test_setup_non_scende_sotto_lo_speso(cop):
    pid = next(iter(cop.ADVISOR.targets))
    _post(cop, "/copilot/hammer", {"player_id": pid, "team_index": 2, "price": 60,
                                   "richiesta_id": "st1"})
    r = _post(cop, "/copilot/setup", {"names": cop.STATE["names"], "my_index": 0,
                                      "budget": 70})
    assert r["code"] == 400 and "insufficiente" in r["body"]["err"]
    _post(cop, "/copilot/undo", {"richiesta_id": "ust1"})


def test_get_malformati_rispondono_400(cop):
    r = _get(cop, "/copilot/nominate?role=X")
    assert r["code"] == 400
    r = _get(cop, "/copilot/piani?quanti=abc")
    assert r["code"] == 400


def test_obbligo_di_completare(cop):
    """Un solo portiere comprabile e tre slot P liberi: si prende fino al massimo legale."""
    portieri = [pid for pid, p in cop.pool().items() if p.role == "P"]
    tenuto = portieri[0]
    # gli altri portieri escono dal pool dei consigli come esclusi manuali
    cop.STATE["esclusi_manuali"] = portieri[1:]
    cop.PIANI_CACHE.clear()
    cop.rebuild_advisor()
    try:
        d = cop.decisione_operativa(tenuto, None)
    finally:
        cop.STATE["esclusi_manuali"] = []
        cop.rebuild_advisor()
    assert d.get("obbligo") is True and d["azione"] == "rilancia"
    assert d["max_consigliato"] == d["max_legale"]


def test_concorrenti_sopra_tetto(cop):
    """Indicatore «chi puo' superarti»: solo informazione, conta gli avversari
    che hanno ancora slot in quel ruolo e cassa per offrire tetto + 1."""
    quotas = cop.STATE["quotas"]
    scelti = [pid for pid in cop.ADVISOR.targets
              if cop.PACK.players[pid].role == "P"] or \
        [pid for pid in cop.ADVISOR.targets
         if cop.decisione_operativa(pid, None)["max_consigliato"] >= 1]
    assert scelti, "nessun target utilizzabile"
    target = scelti[0]
    ruolo = cop.PACK.players[target].role
    d = cop.decisione_operativa(target, None)
    tetto = d["max_consigliato"]
    assert tetto >= 1
    # tavolo vuoto: ogni avversario puo' offrire fino a 476 (500 - 24 slot)
    assert d["max_legale"] == 476
    if tetto + 1 <= 476:
        assert d["concorrenti_sopra_tetto"] == 9
        assert len(d["concorrenti_nomi"]) == 5
        assert d["concorrenti_max"] == 476
    else:
        pytest.skip(f"tetto {tetto} oltre il massimo degli avversari")

    # due avversari riempiono il reparto, un terzo spende tutto il legale
    riempitivi = [pid for pid, p in cop.pool().items()
                  if p.role == ruolo and pid != target]
    n = quotas[ruolo]
    assert len(riempitivi) >= 2 * n + 1
    altro = next(pid for pid, p in cop.pool().items() if p.role != ruolo)
    fatti = []
    try:
        for k, pid in enumerate(riempitivi[:n]):
            r = _post(cop, "/copilot/hammer", {"player_id": pid, "team_index": 1,
                                               "price": 1, "richiesta_id": f"cs{k}"})
            assert r["body"]["ok"] is True, r["body"]
            fatti.append(pid)
        for k, pid in enumerate(riempitivi[n:2 * n]):
            r = _post(cop, "/copilot/hammer", {"player_id": pid, "team_index": 2,
                                               "price": 1, "richiesta_id": f"cs1{k}"})
            assert r["body"]["ok"] is True, r["body"]
            fatti.append(pid)
        r = _post(cop, "/copilot/hammer", {"player_id": altro, "team_index": 3,
                                           "price": 476, "richiesta_id": "cs_ricco"})
        assert r["body"]["ok"] is True, r["body"]
        fatti.append(altro)
        d2 = cop.decisione_operativa(target, None)
        tetto2 = d2["max_consigliato"]
        assert 1 <= tetto2 + 1 <= 476, tetto2
        assert d2["concorrenti_sopra_tetto"] == 6, d2["concorrenti_nomi"]
        assert cop.STATE["names"][1] not in d2["concorrenti_nomi"]
        assert cop.STATE["names"][3] not in d2["concorrenti_nomi"]
        # il piano propaga gli stessi campi
        riga = next((x for r_ in cop.ROLES for x in cop.plan()["target"][r_]
                     if x["id"] == target), None)
        if riga is not None:
            assert riga["concorrenti_sopra_tetto"] == d2["concorrenti_sopra_tetto"]
    finally:
        for k in range(len(fatti)):
            _post(cop, "/copilot/undo", {"richiesta_id": f"ucs{k}"})
    assert all(pid in cop.pool() for pid in fatti)
    assert cop.decisione_operativa(target, None)["concorrenti_sopra_tetto"] == 9


def test_rigoristi_stato_segue_il_martelletto(cop):
    """Il pannello rigoristi e' un calcolo sullo stato, non una lista fissa:
    il primo disponibile scende di posto appena il primo viene aggiudicato,
    e risale con l'undo."""
    r = _get(cop, "/copilot/rigoristi")
    assert r["code"] == 200
    d = r["body"]
    assert len(d["squadre"]) == 20, [s["squadra_codice"] for s in d["squadre"]]
    assert not d["non_agganciati"], d["non_agganciati"]
    for sq in d["squadre"]:
        assert sq["primo_disponibile"], f"{sq['squadra_codice']}: nessun rigorista libero"
        assert sq["primo_disponibile_punizioni"], \
            f"{sq['squadra_codice']}: nessun battitore di punizioni libero"
    ata = next(s for s in d["squadre"] if s["squadra_codice"] == "ATA")
    primo, secondo = ata["rigoristi"][0], ata["rigoristi"][1]
    assert primo["stato"] == "disponibile" and secondo["stato"] == "disponibile"
    assert ata["primo_disponibile"] == primo["player_id"]

    r = _post(cop, "/copilot/hammer", {"player_id": primo["player_id"],
                                       "team_index": 1, "price": 30,
                                       "richiesta_id": "rig1"})
    assert r["body"]["ok"] is True, r["body"]
    try:
        ata2 = next(s for s in _get(cop, "/copilot/rigoristi")["body"]["squadre"]
                    if s["squadra_codice"] == "ATA")
        assert ata2["rigoristi"][0]["stato"] == f"venduto a {cop.STATE['names'][1]}"
        assert ata2["primo_disponibile"] == secondo["player_id"]
    finally:
        _post(cop, "/copilot/undo", {"richiesta_id": "urig1"})
    ata3 = next(s for s in _get(cop, "/copilot/rigoristi")["body"]["squadre"]
                if s["squadra_codice"] == "ATA")
    assert ata3["rigoristi"][0]["stato"] == "disponibile"
    assert ata3["primo_disponibile"] == primo["player_id"]


def test_rigoristi_per_ruolo_con_i_gol_veri(cop):
    """Vista per reparto e gol dalle pagelle: Malen 5 gol nel 2026 e 11 nel
    2025, Martinez L. 17 nel 2025. Sono numeri di fonte, non del modello."""
    d = _get(cop, "/copilot/rigoristi")["body"]
    pr = d["per_ruolo"]
    assert set(pr) == {"P", "D", "C", "A"}
    tutti = [v for lst in pr.values() for v in lst]
    assert tutti, "nessun rigorista nella vista per ruolo"
    for v in tutti:                                   # campi sempre presenti
        for k in ("ordine", "squadra", "stato", "primo_disponibile_della_squadra",
                  "gol_2026", "rig_2026", "rigsb_2026", "pres_2026",
                  "gol_2025", "rig_2025", "rigsb_2025", "pres_2025", "assist_2025"):
            assert k in v, (v["nome"], k)
    per_id = {str(v["player_id"]): v for v in tutti}
    assert per_id["5585"]["gol_2026"] == 5, per_id["5585"]
    assert per_id["5585"]["gol_2025"] == 11, per_id["5585"]
    assert per_id["2764"]["gol_2025"] == 17, per_id["2764"]
    # ordine dentro il reparto: gol 2025 decrescente
    for lst in pr.values():
        g = [v["gol_2025"] or 0 for v in lst]
        assert g == sorted(g, reverse=True), g
    # gli stessi campi anche nella vista per squadra
    roma = next(s for s in d["squadre"] if s["squadra_codice"] == "ROM")
    assert roma["rigoristi"][0]["gol_2025"] == 11
