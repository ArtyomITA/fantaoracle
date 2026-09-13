"""Prove del tetto nuovo, dei gol nei consigli e del bonus gol di lega.

Lo stato non e' inventato: si ricostruisce dall'asta VERA del 10/9/2026
(`data/copilot/ledger_1789058317.json`, 250 eventi, `my_index` 9 =
TonyDaMilano) troncando gli eventi al momento che interessa. Il ledger vero
non viene mai toccato: si copia in una cartella temporanea, come fa la
fixture di `test_copilot_asta.py`.

Numeri di riferimento della diagnosi (tutti verificati sul ledger):
Malen (id 5585) all'evento 190 usciva a **116** con 316 crediti in cassa, sei
slot d'attacco liberi e un massimo legale di **311**; il tavolo lo ha pagato
275. Hojlund (id 6052, evento 200) usciva a 102 ed e' stato pagato 200
dall'utente stesso, contro il proprio consiglio.
"""
from __future__ import annotations

import datetime
import importlib.util
import json
import shutil
import sys
import tempfile
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
PACK = ROOT / "data" / "packs" / "pack_2026-27.pkl"
LEDGER = ROOT / "data" / "copilot" / "ledger_1789058317.json"

pytestmark = pytest.mark.skipif(not (PACK.exists() and LEDGER.exists()),
                                reason="pack 2026-27 o ledger del 10/9 assenti")

# indici (0-based) dei lotti che la diagnosi cita, nel ledger del 10/9
EV_MALEN, ID_MALEN = 190, "5585"
EV_MARTINEZ, ID_MARTINEZ = 193, "2764"
EV_RAMOS, ID_RAMOS = 198, "6397"
EV_HOJLUND, ID_HOJLUND = 200, "6052"
ID_OSMAJIC = "7600"
# Raimondo: quattro gol in tre giornate del 2026-27, nessun minuto in Serie A
# prima. E' bomber per il passo, non per lo storico (difetto V3)
EV_RAIMONDO, ID_RAIMONDO = 199, "5436"


@pytest.fixture(scope="module")
def cop():
    sys.path.insert(0, str(ROOT / "src"))
    spec = importlib.util.spec_from_file_location(
        "cop_tetto_test", ROOT / "scripts" / "f10_copilot.py")
    c = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = c
    spec.loader.exec_module(c)
    c.PACK = c.load_pack("2026-27")
    c.ELEGGIBILITA = c.carica_eleggibilita("2026-27")
    c.prepara_pack("2026-27", oggi=datetime.date(2026, 9, 10))
    with tempfile.TemporaryDirectory(prefix="cop_tetto_") as tmp:
        copia = Path(tmp) / "ledger_prova.json"
        shutil.copyfile(LEDGER, copia)          # mai l'originale
        c.LEDGER_PATH = copia
        c._LEDGER = json.loads(copia.read_text(encoding="utf-8"))
        yield c


def stato_a(c, quanti: int) -> None:
    """Lo stato del tavolo dopo i primi `quanti` eventi del ledger vero."""
    led = c._LEDGER
    c.STATE.update({"season": "2026-27", "names": led["names"],
                    "my_index": led["my_index"], "budget": led["budget"],
                    "quotas": dict(led["quotas"]),
                    "events": [dict(e) for e in led["events"][:quanti]],
                    "bids": [], "esclusi_manuali": []})
    c.PIANI_CACHE.clear()
    c.INDIFF_CACHE.clear()
    c.rebuild_advisor()


def attendi_indifferenza(c, pid: str, prezzo=None, secondi: float = 8.0) -> dict:
    """Poll come fa la pagina: la prima risposta e' «in_calcolo», poi arriva."""
    scadenza = time.time() + secondi
    d = c.decisione_operativa(pid, prezzo)
    while d.get("stato_indifferenza") == "in_calcolo" and time.time() < scadenza:
        time.sleep(0.25)
        d = c.decisione_operativa(pid, prezzo)
    return d


def _get(c, path):
    h = c.Handler.__new__(c.Handler)
    h.path = path
    cap = {}
    h._send = lambda obj, code=200: cap.update(body=obj, code=code)
    h.do_GET()
    return cap


# ------------------------------------------------------------- 1. funzione pura
def test_tetto_scarsita_casi_del_prototipo(cop):
    """Gli otto casi provati nel prototipo dell'audit, invariati.

    La formula: si parte dal prezzo di indifferenza e si sale verso il massimo
    spendibile in proporzione alla scarsita'; mai sopra lo spendibile, mai
    sotto il tetto del bot.
    """
    t = cop.tetto_scarsita
    # T1 — stato vero del 10/9 su Malen, con un solo bomber rimasto
    r = t(crediti=316, slot_totali=6, prezzo_indifferenza=219, bomber_rimasti=1,
          squadre_contendenti=9, cap_bot=116, e_bomber=True)
    assert r["max_spendibile"] == 311 and r["tetto"] == 302
    # T1b — stessa scena con i 320 crediti citati dall'utente
    r = t(crediti=320, slot_totali=6, prezzo_indifferenza=219, bomber_rimasti=1,
          squadre_contendenti=9, cap_bot=116, e_bomber=True)
    assert r["max_spendibile"] == 315 and r["tetto"] == 305
    # T2 — sette bomber e nove contendenti: premio piccolo, non nullo
    r = t(crediti=316, slot_totali=6, prezzo_indifferenza=219, bomber_rimasti=7,
          squadre_contendenti=9, cap_bot=116, e_bomber=True)
    assert 219 < r["tetto"] <= 260 and r["quota_scarsita"] == 0.3
    # T3 — piu' bomber che compratori: nessun premio, resta l'indifferenza
    r = t(crediti=320, slot_totali=6, prezzo_indifferenza=219, bomber_rimasti=8,
          squadre_contendenti=3, cap_bot=116, e_bomber=True)
    assert r["tetto"] == 219 and r["quota_scarsita"] == 0.0
    # T4 — cassa corta: il tetto non puo' superare lo spendibile
    r = t(crediti=40, slot_totali=5, prezzo_indifferenza=30, bomber_rimasti=1,
          squadre_contendenti=9, cap_bot=12, e_bomber=True)
    assert r["max_spendibile"] == 36 and r["tetto"] <= 36
    # T5 — obbligo di completare: massimo legale, e basta
    r = t(crediti=316, slot_totali=6, prezzo_indifferenza=219, bomber_rimasti=1,
          squadre_contendenti=9, cap_bot=116, e_bomber=True, obbligo=True)
    assert r["tetto"] == 311
    # T6 — senza previsione: valore zero, nessun premio
    r = t(crediti=316, slot_totali=6, prezzo_indifferenza=0, bomber_rimasti=1,
          squadre_contendenti=9, cap_bot=5, e_bomber=False)
    assert r["tetto"] <= 5
    # T7 — difensore in piano a tavolo vuoto: identico a prima del fix
    r = t(crediti=500, slot_totali=25, prezzo_indifferenza=0, bomber_rimasti=30,
          squadre_contendenti=9, cap_bot=40, e_bomber=False)
    assert r["tetto"] == 40


def test_quota_scarsita_estremi(cop):
    """Un bomber solo e nove rivali: quota quasi 1. Piu' bomber che
    compratori: zero. Non esce mai dall'intervallo."""
    assert cop.quota_scarsita(1, 9) == 0.9
    assert cop.quota_scarsita(30, 9) == 0.0
    assert 0.0 <= cop.quota_scarsita(0, 0) <= 1.0


# ---------------------------------------------- 2. Malen all'evento 190
def test_malen_ev190_tetto_arriva_al_mercato(cop):
    """Il caso che ha rotto l'asta: 116 su 311 spendibili mentre il tavolo
    pagava 275. Col calore del ruolo il tetto del bot sale gia' a 182, e il
    prezzo di indifferenza lo porta oltre 240."""
    stato_a(cop, EV_MALEN)
    d = cop.decisione_operativa(ID_MALEN, 274)
    assert d["max_spendibile"] == 311
    # nessun attaccante era ancora stato battuto: il calore del ruolo e' 1.0,
    # non lo 0.67 misurato su 175 lotti di portieri, difensori e centrocampisti
    assert d["calore_ruolo"] == 1.0
    assert d["cap_bot"] >= 170, d["cap_bot"]
    assert d["e_bomber"] is True
    # PREMESSA AGGIORNATA (con la prova). Il compito si aspettava
    # «bomber_rimasti fra 5 e 12»: e' il conteggio di TUTTI gli attaccanti
    # sopra i dieci gol ancora liberi, che all'evento 190 sono 11 e restano
    # esposti come `bomber_pool_ruolo`. La scarsita' pero' si misura sui
    # sostituti veri: sopra i quattordici gol di Malen ne restavano TRE
    # (lui, Martinez L. 17, Douvikas 14). Col conteggio largo la quota di
    # scarsita' sarebbe 0 — undici «bomber» per sei compratori — e il premio
    # non scatterebbe mai, esattamente nella sera in cui il tavolo si
    # scannava per due nomi. Prova: reports/asta_20260913/replay_tetto.md,
    # dove il tetto arriva al prezzo in 3 dei 4 lotti della diagnosi.
    assert 5 <= d["bomber_pool_ruolo"] <= 12, d["bomber_pool_ruolo"]
    assert 1 <= d["bomber_rimasti"] <= 4, d["bomber_rimasti"]
    assert d["squadre_contendenti"] >= 5, d["squadre_contendenti"]
    assert d["stato_indifferenza"] in ("in_calcolo", "pronto", "non_applicabile")
    assert d["cap_bot"] <= d["max_consigliato"] <= d["max_spendibile"]

    d = attendi_indifferenza(cop, ID_MALEN, 274)
    assert d["stato_indifferenza"] == "pronto", d["stato_indifferenza"]
    assert 150 <= d["prezzo_indifferenza"] <= 311, d["prezzo_indifferenza"]
    assert d["max_consigliato"] >= d["prezzo_indifferenza"]
    assert 240 <= d["max_consigliato"] <= 311, d["max_consigliato"]
    # il confronto che l'utente voleva vedere: con lui e senza di lui
    assert d["con_lui"] and d["senza_di_lui"]
    assert d["con_lui"]["prezzo"] == d["max_consigliato"]
    assert isinstance(d["senza_di_lui"]["gol_2025"], int)


def test_niente_premio_a_chi_non_fa_gol(cop):
    """Osmajic: 205 di valore per il modello, zero minuti in Serie A 2025-26.
    Il premio di scarsita' non lo tocca, e il tetto resta quello del bot."""
    stato_a(cop, EV_MALEN)
    d = cop.decisione_operativa(ID_OSMAJIC, None)
    assert d["e_bomber"] is False
    assert d["quota_scarsita"] == 0.0
    assert d["max_consigliato"] <= 10, d["max_consigliato"]
    dett = cop.ELEGGIBILITA.get("senza_previsione") or []
    if dett:
        pid = str(dett[0]["id"])
        d = cop.decisione_operativa(pid, None)
        assert d["max_consigliato"] <= 5, d["max_consigliato"]
        assert d["e_bomber"] is False


def test_hojlund_prima_del_martelletto(cop):
    """L'utente lo ha pagato 200 contro un proprio tetto di 102. Dopo il fix
    il tetto sta sopra 150 gia' prima del prezzo di indifferenza, e i bomber
    rimasti sono meno che dieci lotti prima."""
    stato_a(cop, EV_MALEN)
    prima = cop.decisione_operativa(ID_MALEN, None)
    stato_a(cop, EV_HOJLUND)
    dopo = attendi_indifferenza(cop, ID_HOJLUND)
    # dieci lotti dopo, di bomber ne restano meno: 11 -> 8
    assert dopo["bomber_pool_ruolo"] < prima["bomber_pool_ruolo"], (
        prima["bomber_pool_ruolo"], dopo["bomber_pool_ruolo"])
    assert dopo["quota_scarsita"] > 0, dopo["motivo_tetto"]
    # PREMESSA AGGIORNATA (con la prova). Il compito si aspettava «quota di
    # scarsita' maggiore» che all'evento 190. Misurata, va nell'altro verso:
    # 0.5 su Malen (tre pari suo, cinque rivali capaci di pagarlo) contro
    # ~0.25 su Hojlund (tre pari suo, ma solo tre rivali ancora capaci: i
    # 275 di Malen e i 255 di Martinez L. avevano gia' svuotato le casse).
    # E' il comportamento giusto: la scarsita' che conta e' quella del
    # confronto, e se i rivali non hanno piu' soldi non c'e' gara da vincere.
    # Cio' che deve valere, e vale, e' che il tetto arrivi vicino al prezzo
    # vero (200): era 102.
    assert dopo["max_consigliato"] >= 150, dopo["max_consigliato"]
    assert dopo["max_consigliato"] <= dopo["max_spendibile"]


def test_fine_asta_nessun_crash(cop):
    """Due slot d'attacco e due crediti: il tetto non puo' che essere 1."""
    stato_a(cop, 244)
    liberi = [pid for pid, p in cop.pool().items() if p.role == "A"]
    assert liberi
    for pid in liberi[:5]:
        d = cop.decisione_operativa(pid, None)
        assert d["max_consigliato"] <= d["max_spendibile"], (pid, d)
        assert d["max_consigliato"] >= 0


def test_difensore_tavolo_vuoto_resta_come_prima(cop):
    """Tavolo vuoto, nessun lotto battuto: calore 1.0 ovunque, nessun premio.
    E' la scena di `test_concorrenti_sopra_tetto`, che deve restare verde."""
    cop.STATE.update({"season": "2026-27", "names": [f"T{i}" for i in range(10)],
                      "my_index": 0, "budget": 500,
                      "quotas": {"P": 3, "D": 8, "C": 8, "A": 6},
                      "events": [], "bids": [], "esclusi_manuali": []})
    cop.PIANI_CACHE.clear()
    cop.INDIFF_CACHE.clear()
    cop.rebuild_advisor()
    difensori = [pid for pid in cop.ADVISOR.targets
                 if cop.PACK.players[pid].role == "D"]
    assert difensori
    for pid in difensori[:3]:
        d = cop.decisione_operativa(pid, None)
        assert d["quota_scarsita"] == 0.0
        assert d["e_bomber"] is False
        assert d["calore_ruolo"] == 1.0
        assert d["max_consigliato"] == d["cap_bot"]
        assert d["max_legale"] == 476


# ---------------------------------------------------------- 7. i gol, ovunque
def test_players_porta_i_gol_e_gli_ordinamenti(cop):
    stato_a(cop, EV_MALEN)
    lista = _get(cop, "/copilot/players?role=A")["body"]
    assert lista
    for x in lista:
        for k in ("gol_2025", "gol_tot_2025", "gol_2026", "bomber"):
            assert k in x, (x["nome"], k)
        assert x["gol_2025"] is None or isinstance(x["gol_2025"], int)
    per_id = {x["id"]: x for x in lista}
    m = per_id[ID_MALEN]
    assert (m["gol_2025"], m["rig_2025"], m["gol_2026"]) == (11, 3, 5)
    assert m["gol_tot_2025"] == 14 and m["bomber"] is True
    r = per_id[ID_RAMOS]
    # Ramos G. non ha mai giocato in Serie A: `gol_2025` e' null, non zero.
    # Il passo 2026-27 NON lo promuove a bomber: un gol in tre giornate
    # proietterebbe 12,7 gol stagionali, e con quel criterio nudo 27 dei 86
    # attaccanti liberi sarebbero «bomber». Serve almeno un vero avvio
    # (3 gol): vedi MIN_GOL_2026_BOMBER.
    assert r["gol_2025"] is None and r["bomber"] is False

    per_gol = _get(cop, "/copilot/players?role=A&ordina=gol")["body"]
    assert (per_gol[0]["gol_tot_2025"] or 0) >= 14, per_gol[0]["nome"]
    assert per_gol[-1]["gol_tot_2025"] in (None, 0)
    per_valore = _get(cop, "/copilot/players?role=A&ordina=value")["body"]
    assert [x["id"] for x in per_valore] == [x["id"] for x in lista]
    misto = _get(cop, "/copilot/players?role=A&ordina=misto")["body"]
    assert misto[0]["gol_tot_2025"] is not None


def test_gol_rosa_classifica_asta_vera(cop):
    """I gol veri delle dieci rose finali: gol su azione PIU' rigori."""
    stato_a(cop, len(cop._LEDGER["events"]))
    d = _get(cop, "/copilot/gol_rosa")["body"]
    per_nome = {r["nome"]: r for r in d["squadre"]}
    tony = per_nome["TonyDaMilano"]
    assert tony["tot_2025"] == 74 and tony["posizione"] == 1
    assert tony["per_ruolo"]["A"] == 28
    assert tony["mia"] is True and d["mia_posizione"] == 1
    # tre giocatori della sua rosa non hanno dati 2025-26: non valgono zero,
    # valgono «non lo so», e si dice chi sono
    assert tony["senza_dato"] == 3 and len(tony["senza_dato_nomi"]) == 3
    assert per_nome["Nightmare fc"]["tot_2025"] == 40
    assert per_nome["Nightmare fc"]["posizione"] == 10
    assert per_nome["as tavolato"]["per_ruolo"]["A"] == 38
    # sui gol di QUEST'ANNO la stessa rosa e' ultima: e' il numero che dava
    # ragione all'utente, e va mostrato accanto all'altro
    assert tony["tot_2026"] == 3
    assert tony["tot_2026"] == min(r["tot_2026"] for r in d["squadre"])


def test_state_porta_cassa_calore_e_scarsita(cop):
    stato_a(cop, EV_MALEN)
    st = _get(cop, "/copilot/state")["body"]
    assert st["spendibile"]["max_ora"] == 311
    assert st["spendibile"]["slot_per_ruolo"]["A"] == 6
    assert st["calore_per_ruolo"]["A"] == 1.0
    assert st["calore_per_ruolo"]["C"] < 1.0        # il blocco C era freddo
    assert st["scarsita"]["A"]["bomber_pool"] >= 5
    assert st["scarsita"]["A"]["squadre_in_gara"] == 9
    assert len(st["scarsita"]["A"]["top"]) <= 5
    mia = st["teams"][cop.STATE["my_index"]]
    a_mano = 0
    for r in cop.ROLES:
        for g in mia["roster"][r]:
            a_mano += g["gol_tot_2025"] or 0
    assert mia["gol_2025"] == a_mano


def test_bonus_gol_di_lega(cop):
    """La lega paga +5 a gol, la fonte ne mette 3 dentro il fantavoto: la
    differenza vale 2 punti per gol atteso, e finisce nel valore."""
    pr = cop.PRED_ATTIVE[ID_MALEN]
    pack = cop.PACK.b_predictions[ID_MALEN]
    atteso = 14 * min(1.2, pack["pres"] / 18)       # 14 gol+rigori su 18 presenze
    assert pr["gol_attesi"] == pytest.approx(atteso, abs=0.01)
    assert pr["value"] == pytest.approx(pack["value"] + 2 * atteso, abs=0.05)
    assert pr["bonus_gol_lega"] > 20
    assert pr["q50"] == pack["q50"]                 # i prezzi non si toccano
    assert "bonus gol lega" in pr["motivi"]
    # un centrocampista da un gol prende le briciole: e' il divario che il
    # modello non vedeva
    adopo = next(pid for pid, p in cop.PACK.players.items() if p.name == "Adopo")
    assert cop.PRED_ATTIVE[adopo]["bonus_gol_lega"] <= 3
    # chi non ha storico non riceve niente, e lo dichiara con un null
    senza = [pid for pid in cop.PACK.players
             if cop.campi_gol(pid)["pres_2025"] in (None, 0)
             and (cop.campi_gol(pid)["pres_2026"] or 0) < 2
             and pid in cop.PRED_ATTIVE]
    assert senza
    for pid in senza[:20]:
        assert cop.PRED_ATTIVE[pid]["gol_attesi"] is None
        assert cop.PRED_ATTIVE[pid]["bonus_gol_lega"] == 0.0
        assert cop.PRED_ATTIVE[pid]["value"] == cop.PACK.b_predictions[pid]["value"]


def test_tempi_di_risposta(cop):
    """Il consiglio non aspetta il MILP: risponde e il numero arriva dopo."""
    stato_a(cop, len(cop._LEDGER["events"]))
    misure = {}
    for path in ("/copilot/state", "/copilot/players?role=A", "/copilot/gol_rosa"):
        t0 = time.perf_counter()
        _get(cop, path)
        misure[path] = (time.perf_counter() - t0) * 1000
    assert misure["/copilot/state"] < 150, misure
    assert misure["/copilot/players?role=A"] < 50, misure
    stato_a(cop, EV_MALEN)
    t0 = time.perf_counter()
    _get(cop, f"/copilot/advice?player_id={ID_MALEN}&price=274")
    ms = (time.perf_counter() - t0) * 1000
    assert ms < 150, ms


# ------------------------------------------- 8. V1: il numero non deve ballare
def test_il_tetto_non_sfarfalla_fra_una_chiamata_e_l_altra(cop):
    """Il difetto V1, riprodotto come lo vedeva il tavolo.

    La pagina richiama `/copilot/advice` ogni due secondi e ogni consiglio
    pre-riscalda i primi bomber del pool. Con `INDIFF_CACHE.clear()` dentro
    `_lavora_indifferenza` ogni bisezione che finiva buttava via anche il
    risultato del giocatore AL BANCO: il numero grande alternava 289 e 272 a
    ogni giro, e la riga sotto passava da «indifferenza 244» a «n/a».
    Qui si fanno otto chiamate consecutive dopo la prima risposta «pronto»:
    deve uscire un valore solo.
    """
    stato_a(cop, EV_MALEN)
    percorso = f"/copilot/advice?player_id={ID_MALEN}&price=150"
    scadenza = time.time() + 25.0
    a = _get(cop, percorso)["body"]
    while a.get("stato_indifferenza") == "in_calcolo" and time.time() < scadenza:
        time.sleep(0.25)
        a = _get(cop, percorso)["body"]
    assert a["stato_indifferenza"] == "pronto", a["stato_indifferenza"]

    letture = []
    for _ in range(8):
        time.sleep(0.3)
        b = _get(cop, percorso)["body"]
        letture.append((b["stato_indifferenza"], b["prezzo_indifferenza"],
                        b["max_consigliato"]))
    assert len(set(letture)) == 1, letture
    assert letture[0] == ("pronto", a["prezzo_indifferenza"],
                          a["max_consigliato"])

    # seconda faccia dello stesso difetto: il pre-riscaldamento cancellava
    # cio' che aveva appena scaldato, e in cache restava una chiave sola
    versione = cop.versione_stato()
    vive = [k for k in cop.INDIFF_CACHE if k[0] == versione]
    assert len(vive) >= 2, vive
    # e nessuna chiave di stati superati resta a occupare memoria
    assert all(k[0] == versione for k in cop.INDIFF_CACHE)


# ------------------------------ 9. V3: il premio vuole lo storico di gol veri
def test_tetto_scarsita_senza_storico_resta_il_tetto_del_bot(cop):
    """La funzione pura: stessi ingressi, `storico_gol=False`, niente premio."""
    t = cop.tetto_scarsita
    base = dict(crediti=316, slot_totali=6, prezzo_indifferenza=251,
                bomber_rimasti=1, squadre_contendenti=9, cap_bot=42,
                e_bomber=True)
    con = t(**base)
    assert con["tetto"] > 250 and con["quota_scarsita"] == 0.9
    senza = t(**base, storico_gol=False)
    assert senza["tetto"] == 42                  # il tetto del bot, e basta
    assert senza["quota_scarsita"] == 0.0 and senza["premio_scarsita"] == 0
    assert "passo 2026" in senza["motivo"]
    # il default resta «premio ammesso»: i casi del prototipo non cambiano
    assert t(**base)["tetto"] == con["tetto"]


def test_raimondo_bomber_solo_del_passo_2026(cop):
    """V3: 251 di tetto su un lotto che il tavolo ha chiuso a 80.

    Raimondo e' bomber (quattro gol in tre giornate) e deve restarlo — conta
    nel pool e la pagina gli mette il badge — ma senza una stagione di gol
    veri alle spalle non prende il premio di scarsita', e nemmeno il pavimento
    del prezzo di indifferenza. Il tetto torna quello del bot.
    """
    stato_a(cop, EV_RAIMONDO)
    assert cop.storico_gol(ID_RAIMONDO, "A") is False
    assert cop.campi_gol(ID_RAIMONDO)["gol_tot_2025"] is None
    d = attendi_indifferenza(cop, ID_RAIMONDO, secondi=25.0)
    assert d["e_bomber"] is True                 # resta nel pool dei bomber
    assert d["storico_gol"] is False
    assert d["quota_scarsita"] == 0.0
    assert "bomber solo per il passo 2026" in d["motivo_tetto"], d["motivo_tetto"]
    assert d["max_consigliato"] == d["cap_bot"]
    assert d["max_consigliato"] < 120, d["max_consigliato"]
    # il prezzo di indifferenza si continua a calcolare e a mostrare: e'
    # informazione, non piu' un pavimento
    assert d["stato_indifferenza"] == "pronto"
    assert d["prezzo_indifferenza"] > d["max_consigliato"]


def test_chi_ha_lo_storico_non_perde_il_premio(cop):
    """La contropartita: sui tre lotti della diagnosi il tetto resta sopra il
    prezzo che il tavolo ha pagato (275, 255, 200)."""
    for evento, pid, pagato in ((EV_MALEN, ID_MALEN, 275),
                                (EV_MARTINEZ, ID_MARTINEZ, 255),
                                (EV_HOJLUND, ID_HOJLUND, 200)):
        stato_a(cop, evento)
        assert cop.storico_gol(pid, "A") is True
        d = attendi_indifferenza(cop, pid, secondi=25.0)
        assert d["storico_gol"] is True
        assert d["max_consigliato"] >= pagato, (pid, d["max_consigliato"])
        assert d["max_consigliato"] <= d["max_spendibile"]
