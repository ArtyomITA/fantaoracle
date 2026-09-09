"""Il percorso vero di un tetto: produttore, file, script di confronto, asta.

## I due difetti che questo file impedisce di ripetere

**Identita' del tetto.** Un record con `giocatore = "A0"` riposto sotto la
chiave `"A1"` veniva accettato: `_tetto_validato("A1", view)` rispondeva
`(17.0, "valido")`. La chiave di validita' descrive lo stato del mondo ed e'
identica per tutti i giocatori calcolati dallo stesso `StatoAsta`, quindi
nessuna delle altre verifiche poteva accorgersene. Adesso l'identita' e'
scritta nel record in forma canonica, il produttore si ferma se `curva()`
risponde su un altro giocatore, il caricatore scarta i record sotto la chiave
sbagliata e il consumatore respinge con ragione `identita_diversa`.

**Formato incompatibile.** `scripts/l3_tetti.py` serializzava solo `nome`,
`ruolo`, `mercato`, `tetto_economico`, `massimo_legale`, `stato`, `secondi` e
`curva`: niente identita', niente chiave di validita', niente completamento.
`scripts/l3_confronto_asta.py` poi convertiva il record in
`float(tetto_economico)`. Il bot nuovo respinge un numero nudo con ragione
`senza_chiave`, quindi il percorso reale produttore -> file -> asta non
funzionava: il braccio L3+I si comportava come L3 e nessun numero lo diceva.

## Perche' i metodi isolati non bastavano

`tests/test_bot_l3_tetti.py` prova la verifica di validita' costruendo i record
a mano: se il produttore scrive un altro formato, quei test passano lo stesso.
Qui il record lo produce `indifferenza.curva()`, lo serializza
`l3_tetti.record_tetto`, lo rilegge `l3_confronto_asta.carica_tetti`, lo riceve
`l3_confronto_asta.fai_nostro` e la decisione la prende `AuctionEngine` vero,
martelletto per martelletto.

## Il mondo di prova, e perche' e' piccolo ma non finto

Quattro squadre, quote `{P:1, D:4, C:4, A:3}` (dodici posti, moduli reali
ammissibili), budget 40, sessanta giocatori, un cubo sintetico di quattro
scenari per sei giornate. Il cubo e' costruito in modo che un portiere valga
molto piu' di chiunque altro: senza un vantaggio grande la curva di
indifferenza non produrrebbe nessun prezzo con intervallo sopra lo zero, lo
stato sarebbe `inconcludente` e la prova positiva non esisterebbe. Il numero
del tetto non e' un risultato sperimentale: qui si misura se il percorso
trasporta il record, non quanto vale il giocatore.

Tutto il resto e' il codice vero: `indifferenza.curva`, i due script,
`BotL3`, `AuctionEngine`.
"""
from __future__ import annotations

import json
import random
import sys
import types
from pathlib import Path

import numpy as np
import pytest

RADICE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RADICE / "src"))
sys.path.insert(0, str(RADICE / "scripts"))

import l3_confronto_asta as CA                          # noqa: E402
import l3_tetti as PT                                   # noqa: E402
from fantabot.bots.base import (                        # noqa: E402
    BidDecision, Bot, NominationDecision)
from fantabot.engine.auction import AuctionEngine       # noqa: E402
from fantabot.livello3 import indifferenza as I         # noqa: E402
from fantabot.livello3 import valutatore as V           # noqa: E402
from fantabot.models import Player                      # noqa: E402

QUOTE = {"P": 1, "D": 4, "C": 4, "A": 3}
BUDGET = 40
RUOLI = ("P", "D", "C", "A")
PER_RUOLO = {"P": 6, "D": 20, "C": 20, "A": 14}
STELLA = "P0"              # il portiere che vale molto piu' degli altri
SECONDO = "D0"             # nel piano, ma all'asta arriva dopo il primo lotto
N_SQUADRE = 4
SEME = 1                   # con questo seme il primo chiamante non siamo noi
NOSTRO_SEGGIO = 0
SCENARI = [0, 1, 2, 3]
REPLICHE = 4
GRIGLIA = [1, 2, 4, 8, 16, 24]
CAP_RIVALE = 18            # quanto un rivale e' disposto a pagare per la stella
CAP_SECONDO = 3            # e per il secondo bersaglio, in un lotto successivo


# ------------------------------------------------------------------- mondo
def _ids() -> list[str]:
    return [f"{r}{k}" for r in RUOLI for k in range(PER_RUOLO[r])]


class CuboFinto:
    """Le sole cose che il valutatore legge da un cubo."""


def _cubo(n_scen: int = 4, n_gior: int = 6, seme: int = 7) -> CuboFinto:
    """Due giocatori molto piu' forti degli altri.

    Servono due bersagli con un tetto utilizzabile: uno nel primo lotto, dove
    lo stato d'asta e' ancora quello del calcolo, e uno in un blocco
    successivo, dove non lo e' piu'. Con un vantaggio piccolo la curva resta
    `inconcludente` (misurato: con +6 e +8 su `D0` nessun prezzo ha intervallo
    sopra lo zero) e la prova sull'invalidazione non esisterebbe."""
    giocatori = _ids()
    rng = np.random.default_rng(seme)
    fv = rng.normal(6.0, 1.0, (n_scen, n_gior, len(giocatori)))
    fv[:, :, giocatori.index(STELLA)] += 12.0
    fv[:, :, giocatori.index(SECONDO)] += 10.0
    c = CuboFinto()
    c.giocatori = list(giocatori)
    c.fantavoto = fv
    c.voto = np.clip(fv, 4.0, 8.0)
    c.gioca = np.ones((n_scen, n_gior, len(giocatori)), dtype=bool)
    c.impronta = "cubo-sintetico-percorso-tetti"
    return c


def _pool() -> dict:
    out = {}
    for r in RUOLI:
        for k in range(PER_RUOLO[r]):
            pid = f"{r}{k}"
            out[pid] = Player(pid, pid, r, f"sq{k % 4}", ref_price=0.02,
                              exp_points=100.0 - k)
    return out


def _listini(pool: dict) -> tuple[dict, dict]:
    prezzi = {pid: 2.0 for pid in pool}
    prezzi[STELLA] = 6.0
    valori = {pid: float(p.exp_points) for pid, p in pool.items()}
    valori[STELLA] = 400.0
    return prezzi, valori


def _regole() -> V.Regole:
    return V.Regole(quote=dict(QUOTE), budget=BUDGET,
                    applica_bonus_porta_inviolata=False)


def _predizioni(prezzi: dict, valori: dict) -> dict:
    return {pid: {"q50": prezzi[pid], "q90": prezzi[pid] * 1.8,
                  "q10": prezzi[pid] * 0.6, "value": valori[pid],
                  "value_up": valori[pid]} for pid in prezzi}


def _pack_finto(prezzi: dict, valori: dict):
    """Quello che `l3_confronto_asta.fai_nostro` legge da un pack."""
    return types.SimpleNamespace(b_predictions=_predizioni(prezzi, valori),
                                 b_objective=None)


# ------------------------------------------------------- avversari al tavolo
class RivaleDeciso(Bot):
    """Chiama la stella per prima e rilancia fino a un tetto dichiarato.

    Serve a rendere la decisione osservabile: se nessuno rilanciasse, il
    massimo di offerta del nostro bot non deciderebbe niente e la prova non
    distinguerebbe il tetto per indifferenza dal tetto di B."""

    name = "rivale"

    def __init__(self, rng, cap_stella: int = 0, cap_secondo: int = 0):
        super().__init__(rng)
        self.cap_stella = int(cap_stella)
        self.cap_secondo = int(cap_secondo)

    def nominate(self, view) -> NominationDecision:
        disponibili = sorted(view.available(view.current_role),
                             key=lambda p: p.player_id)
        for p in disponibili:
            if p.player_id == STELLA:
                return NominationDecision(p.player_id, 1, "chiamo la stella")
        return NominationDecision(disponibili[0].player_id, 1, "riempio")

    def bid(self, view, player, price, leader) -> BidDecision:
        cap = {STELLA: self.cap_stella, SECONDO: self.cap_secondo}.get(
            player.player_id, 0)
        if price + 1 <= cap:
            return BidDecision(price + 1, f"rilancio fino a {cap}")
        return BidDecision(None, "passo")


# ------------------------------------------------- produttore -> file (vero)
def _scrivi_tetti(percorso: Path, bersagli=(STELLA, SECONDO), **modifiche):
    """Esegue il produttore vero e serializza con `l3_tetti`.

    `modifiche` permette di alterare il file DOPO che il produttore l'ha
    costruito, per provare i casi malformati senza inventare un formato."""
    pool = _pool()
    prezzi, valori = _listini(pool)
    regole = _regole()
    cubo = _cubo()
    avversari = {f"T{i}": {"rosa": {r: [] for r in QUOTE},
                           "budget": float(BUDGET)}
                 for i in range(N_SQUADRE) if i != NOSTRO_SEGGIO}
    stato = I.StatoAsta(nostra={r: [] for r in QUOTE},
                        nostro_budget=float(BUDGET), avversari=avversari,
                        disponibili=set(pool), regole=regole)
    cal = V.calendario_berger(N_SQUADRE, cubo.fantavoto.shape[1], seme=SEME)
    records, contesto = {}, None
    for g in bersagli:
        c = I.curva(g, stato, pool, prezzi, valori, cubo, cal, SCENARI,
                    prezzi_da_provare=GRIGLIA, repliche=REPLICHE, seme=SEME)
        rec = PT.record_tetto(g, c, pool[g].name, pool[g].role,
                              int(prezzi[g]), 0.1)
        records[PT.identita_canonica(g)] = rec
        contesto = contesto or PT.contesto_di(rec)
    riassunto = PT.costruisci_riassunto(
        records, contesto,
        {"stagione": "prova", "seme": SEME, "scenari": len(SCENARI),
         "repliche": REPLICHE, "squadre": N_SQUADRE,
         "seggio": NOSTRO_SEGGIO})
    for chiave, valore in modifiche.items():
        riassunto[chiave] = valore
    percorso.write_text(json.dumps(riassunto, indent=1, default=str),
                        encoding="utf-8")
    return riassunto


# --------------------------------------------------------- l'asta, per davvero
def _gioca(tetti=None, contesto=None, piano=(STELLA, SECONDO)):
    """Un'asta completa col motore vero, il nostro bot al seggio 0."""
    pool = _pool()
    prezzi, valori = _listini(pool)
    pack = _pack_finto(prezzi, valori)
    piano_d = {pid: {"titolare": False} for pid in piano}
    bots = []
    for i in range(N_SQUADRE):
        if i == NOSTRO_SEGGIO:
            bots.append(CA.fai_nostro("L3+I" if tetti else "L3",
                                      random.Random(SEME * 1000 + i), pack,
                                      piano_d, tetti, contesto))
        else:
            # un solo rivale spinge, e su due giocatori: sulla stella fino al
            # suo tetto (li' decide il nostro massimo di offerta), e sul
            # secondo bersaglio quanto basta a farci interrogare dopo che il
            # tavolo e' cambiato
            bots.append(RivaleDeciso(random.Random(SEME * 1000 + i),
                                     cap_stella=CAP_RIVALE if i == 1 else 0,
                                     cap_secondo=CAP_SECONDO if i == 1 else 0))
    rng = random.Random(SEME)
    eng = AuctionEngine(dict(pool), bots, dict(QUOTE), BUDGET, rng)
    squadre = eng.run()
    return {"motore": eng, "bot": bots[NOSTRO_SEGGIO],
            "squadra": squadre[NOSTRO_SEGGIO],
            "vincitore_stella": next(tid for pid, tid, _ in eng.sold
                                     if pid == STELLA),
            "prezzo_stella": next(pr for pid, _, pr in eng.sold
                                  if pid == STELLA)}


@pytest.fixture(scope="module")
def file_tetti(tmp_path_factory) -> Path:
    percorso = tmp_path_factory.mktemp("tetti") / "tetti_prova.json"
    _scrivi_tetti(percorso)
    return percorso


@pytest.fixture(scope="module")
def caricati(file_tetti) -> dict:
    return CA.carica_tetti(file_tetti)


# ============================================ il mondo di prova e' utilizzabile
def test_il_produttore_trova_un_tetto_utilizzabile(caricati):
    """Se la curva fosse `inconcludente` su tutti i bersagli, ogni prova
    positiva di questo file sarebbe vacua: il tetto non entrerebbe per lo
    stato del confronto e non per il percorso."""
    assert caricati["tetti"], "nessun tetto usabile: le prove sarebbero vuote"
    rec = caricati["tetti"][STELLA]
    assert rec["stato"] in ("verificato", "approssimato"), rec["stato"]
    assert rec["tetto_economico"] > 0


def test_il_primo_lotto_non_e_chiamato_da_noi():
    """La prova positiva vive nel primo lotto, l'unico istante in cui lo stato
    d'asta e' ancora quello da cui i tetti sono stati calcolati. Se chiamassimo
    noi, nessuno ci chiederebbe di rilanciare e `_max_bid_for` non verrebbe mai
    interrogato a stato intatto."""
    rng = random.Random(SEME)
    seggi = list(range(N_SQUADRE))
    rng.shuffle(seggi)
    assert seggi[0] != NOSTRO_SEGGIO, seggi


# ================================================== il percorso, da capo a fondo
def test_il_file_del_produttore_porta_identita_chiave_e_completamento(file_tetti):
    """I tre campi che la serializzazione precedente perdeva."""
    d = json.loads(file_tetti.read_text("utf-8"))
    assert set(d["contesto"]) == set(PT.BLOCCHI_CONTESTO)
    for chiave, rec in d["tetti"].items():
        assert rec["giocatore"] == chiave
        assert "stato_decisionale" in rec["chiave_validita"]
        assert rec["completamento"]["tipo"] == "assegnazione_per_priorita"
        assert rec["completamento_etichetta"] == (
            "surrogato (assegnazione_per_priorita)")
        assert "stima_tetto" in rec, (
            "la stima puntuale va conservata e tenuta distinta dal tetto")


def test_il_tetto_arriva_al_bot_e_decide_in_asta(caricati):
    """La condizione d'arresto: uscita del produttore -> file -> caricamento
    dello script di confronto -> bot -> decisione del motore d'asta."""
    res = _gioca(caricati["tetti"], caricati["contesto"])
    bot = res["bot"]
    assert bot.conta["offerte_con_tetto_indifferenza"] > 0, (
        f"nessun tetto usato in asta: {bot.ripieghi_per_ragione}")
    assert res["vincitore_stella"] == res["squadra"].team_id
    assert res["prezzo_stella"] >= CAP_RIVALE, (
        "il rivale non ha spinto fino al suo tetto: la decisione non dipende "
        "dal nostro massimo di offerta e la prova non distingue niente")


def test_senza_tetti_la_stella_la_perde(caricati):
    """Il controllo che rende la prova precedente non vuota: con il tetto di B
    il nostro bot si ferma prima e il rivale porta via la stella. Se anche qui
    vincessimo, il tetto per indifferenza non starebbe decidendo nulla."""
    con = _gioca(caricati["tetti"], caricati["contesto"])
    senza = _gioca(None, None)
    assert senza["vincitore_stella"] != senza["squadra"].team_id
    assert con["vincitore_stella"] != senza["vincitore_stella"]
    assert senza["prezzo_stella"] <= CAP_RIVALE


def test_il_formato_vecchio_non_arriva_al_bot(caricati, tmp_path):
    """Regressione del difetto B, con le righe che c'erano davvero.

    Serializzazione di `l3_tetti.py` (righe 96-102 della versione precedente) e
    caricamento di `l3_confronto_asta.py` (righe 232-238): il record perde
    chiave, identita' e completamento, poi diventa un `float`. Il bot lo
    respinge per `senza_chiave` e l'asta e' quella senza tetti."""
    vecchio = {}
    for pid, rec in caricati["tetti"].items():
        vecchio[pid] = {"nome": rec["nome"], "ruolo": rec["ruolo"],
                        "mercato": rec["mercato"],
                        "tetto_economico": rec["tetto_economico"],
                        "massimo_legale": rec["massimo_legale"],
                        "stato": rec["stato"], "secondi": rec["secondi"],
                        "curva": rec["curva"]}
    usabili = {"verificato", "approssimato"}
    tetti_float = {str(pid): float(v["tetto_economico"])
                   for pid, v in vecchio.items()
                   if v.get("stato") in usabili and v.get("tetto_economico")}
    assert tetti_float, "la fixture non riproduce il formato vecchio"
    res = _gioca(tetti_float, caricati["contesto"])
    bot = res["bot"]
    assert bot.conta["offerte_con_tetto_indifferenza"] == 0
    assert bot.ripieghi_per_ragione.get("senza_chiave", 0) > 0
    assert res["vincitore_stella"] != res["squadra"].team_id, (
        "col formato vecchio la stella dovrebbe sfuggirci come senza tetti")


# ======================================= invalidazione dopo il primo martelletto
def test_dopo_il_primo_martelletto_i_tetti_congelati_non_valgono_piu(caricati):
    """I tetti sono calcolati su un solo stato d'asta. Appena il tavolo cambia
    (un acquisto nostro, uno di un rivale, un budget diverso) la chiave non
    combacia piu' e il bot ripiega, contando la ragione."""
    res = _gioca(caricati["tetti"], caricati["contesto"])
    bot = res["bot"]
    assert bot.ripieghi_per_ragione.get("stato_cambiato", 0) > 0, (
        f"nessun ripiego per stato cambiato: {bot.ripieghi_per_ragione}")
    assert sum(bot.ripieghi_per_ragione.values()) == bot.conta["tetti_respinti"]
    rapporto = bot.rapporto()
    assert rapporto["ripieghi_per_ragione"] == bot.ripieghi_per_ragione
    assert rapporto["ultimo_ripiego"]["ragione"] in bot.ripieghi_per_ragione
    assert rapporto["completamenti_ammessi"] == [
        "surrogato (assegnazione_per_priorita)"]


def test_un_contesto_diverso_ferma_tutti_i_tetti_in_asta(caricati):
    """Modello, scenari, seme, regole e listini non sono osservabili dall'asta:
    arrivano dal file. Se il mondo dichiarato non e' quello del record, nessun
    tetto entra — nemmeno nel primo lotto, dove lo stato coinciderebbe."""
    altro = json.loads(json.dumps(caricati["contesto"]))
    altro["cubo"]["impronta"] = "un-altro-cubo"
    res = _gioca(caricati["tetti"], altro)
    bot = res["bot"]
    assert bot.conta["offerte_con_tetto_indifferenza"] == 0
    assert bot.ripieghi_per_ragione.get("contesto_diverso", 0) > 0


def test_senza_contesto_il_caricatore_lo_dichiara(tmp_path):
    """Un file senza il blocco `contesto` non e' utilizzabile, e il motivo si
    legge: senza, il bot respingerebbe tutto per `senza_contesto` e sembrerebbe
    un problema di stato."""
    percorso = tmp_path / "senza_contesto.json"
    d = _scrivi_tetti(percorso)
    del d["contesto"]
    percorso.write_text(json.dumps(d, indent=1, default=str), encoding="utf-8")
    fuori = CA.carica_tetti(percorso)
    assert fuori["contesto"] is None
    assert "contesto" in fuori["diagnostica"]["contesto_mancante"]
    res = _gioca(fuori["tetti"], fuori["contesto"])
    assert res["bot"].ripieghi_per_ragione.get("senza_contesto", 0) > 0


# ================================================== identita' lungo il percorso
def test_il_produttore_si_ferma_se_la_curva_parla_di_un_altro_giocatore():
    """Difetto A alla sorgente: un record che non parla del proprio bersaglio
    non deve nemmeno essere scritto."""
    finto = {"giocatore": "A0", "tetto_economico": 17, "stato": "verificato",
             "chiave_validita": {}, "completamento": {"tipo": "x"}}
    with pytest.raises(ValueError, match="A0"):
        PT.record_tetto("A1", finto, "A1", "A", 3, 0.1)


def test_il_riassunto_si_ferma_se_la_chiave_non_e_l_identita(file_tetti):
    """Difetto A alla serializzazione: la chiave del dizionario e il campo
    `giocatore` devono essere lo stesso identificativo canonico."""
    d = json.loads(file_tetti.read_text("utf-8"))
    rec = dict(d["tetti"][STELLA])
    with pytest.raises(ValueError, match="chiave"):
        PT.costruisci_riassunto({SECONDO: rec}, d["contesto"], {})


def test_il_caricatore_scarta_un_record_sotto_la_chiave_sbagliata(file_tetti,
                                                                 tmp_path):
    """Difetto A al caricamento: se un file malformato arriva comunque, lo
    scarto e' contato con la sua ragione invece di essere passato al bot."""
    d = json.loads(file_tetti.read_text("utf-8"))
    rec = json.loads(json.dumps(d["tetti"][STELLA]))
    d["tetti"] = {SECONDO: rec}
    percorso = tmp_path / "identita_sbagliata.json"
    percorso.write_text(json.dumps(d, indent=1, default=str), encoding="utf-8")
    fuori = CA.carica_tetti(percorso)
    assert fuori["tetti"] == {}
    assert fuori["diagnostica"]["identita_diversa"] == 1


def test_il_bot_respinge_un_record_sotto_la_chiave_sbagliata(caricati):
    """Difetto A al consumo, sulle chiamate vere dell'asta: anche saltando il
    caricatore, il bot non usa un tetto che parla di un altro giocatore."""
    scambiati = {SECONDO: caricati["tetti"][STELLA],
                 STELLA: caricati["tetti"][SECONDO]}
    res = _gioca(scambiati, caricati["contesto"])
    bot = res["bot"]
    assert bot.conta["offerte_con_tetto_indifferenza"] == 0
    assert bot.ripieghi_per_ragione.get("identita_diversa", 0) > 0
    assert res["vincitore_stella"] != res["squadra"].team_id


# ============================================ zero valido contro dato mancante
def test_il_caricatore_tiene_lo_zero_e_scarta_il_dato_mancante(file_tetti,
                                                              tmp_path):
    """`if v.get("tetto_economico")` trattava 0 come assente. Sono due cose
    diverse: zero con uno stato ammesso significa «non rilanciare», l'assenza
    del campo significa che non si sa."""
    d = json.loads(file_tetti.read_text("utf-8"))
    zero = json.loads(json.dumps(d["tetti"][STELLA]))
    zero["tetto_economico"] = 0
    zero.pop("classificazione", None)
    mancante = json.loads(json.dumps(d["tetti"][SECONDO]))
    mancante["stato"] = "verificato"
    mancante["tetto_economico"] = None
    d["tetti"] = {STELLA: zero, SECONDO: mancante}
    percorso = tmp_path / "zero_e_mancante.json"
    percorso.write_text(json.dumps(d, indent=1, default=str), encoding="utf-8")
    fuori = CA.carica_tetti(percorso)
    assert set(fuori["tetti"]) == {STELLA}
    assert fuori["diagnostica"]["tetto_zero"] == 1
    assert fuori["diagnostica"]["dato_mancante"] == 1


def test_uno_zero_valido_ferma_l_offerta_in_asta(file_tetti, tmp_path):
    """Lo zero non e' un ripiego: entra come massimo di offerta e il bot passa.
    Senza distinguerlo dal dato mancante il bot userebbe il tetto di B e
    rilancerebbe."""
    d = json.loads(file_tetti.read_text("utf-8"))
    zero = json.loads(json.dumps(d["tetti"][STELLA]))
    zero["tetto_economico"] = 0
    zero.pop("classificazione", None)
    d["tetti"] = {STELLA: zero}
    percorso = tmp_path / "zero.json"
    percorso.write_text(json.dumps(d, indent=1, default=str), encoding="utf-8")
    fuori = CA.carica_tetti(percorso)
    res = _gioca(fuori["tetti"], fuori["contesto"])
    bot = res["bot"]
    assert bot.conta["offerte_con_tetto_indifferenza"] > 0
    assert res["vincitore_stella"] != res["squadra"].team_id
    assert res["prezzo_stella"] <= 2, (
        "con tetto zero il bot non deve rilanciare nemmeno di un credito")


# ============================== stima puntuale contro record senza supporto
def test_il_caricatore_non_promuove_la_stima_a_tetto(file_tetti, tmp_path):
    """`classifica_curva` espone `stima_tetto` (massimo dei delta positivi,
    distorto verso l'alto) e `tetto_supportato` (intervallo sopra lo zero).
    Un record inconcludente ha una stima ma nessun tetto: la stima non entra."""
    d = json.loads(file_tetti.read_text("utf-8"))
    rec = json.loads(json.dumps(d["tetti"][STELLA]))
    rec["stato"] = "inconcludente"
    rec["stima_tetto"] = 24
    rec["tetto_economico"] = 0
    rec["classificazione"] = {**rec.get("classificazione", {}),
                              "tetto_supportato": None, "stima_tetto": 24}
    d["tetti"] = {STELLA: rec}
    percorso = tmp_path / "inconcludente.json"
    percorso.write_text(json.dumps(d, indent=1, default=str), encoding="utf-8")
    fuori = CA.carica_tetti(percorso)
    assert fuori["tetti"] == {}, "un record inconcludente non e' un tetto"
    assert fuori["diagnostica"]["per_stato"]["inconcludente"] == 1


def test_la_classificazione_del_produttore_espone_i_prezzi_per_esito(file_tetti):
    """La classificazione va letta, non reinventata: il file porta le liste
    che distinguono un prezzo sostenuto da uno inconcludente."""
    d = json.loads(file_tetti.read_text("utf-8"))
    cl = d["tetti"][STELLA]["classificazione"]
    for campo in ("stima_tetto", "tetto_supportato",
                  "prezzi_vantaggio_supportato",
                  "prezzi_svantaggio_supportato", "prezzi_inconcludenti"):
        assert campo in cl, campo
    assert d["tetti"][STELLA]["tetto_economico"] == (cl["tetto_supportato"] or 0)


# ============================================================ contabilita'
def test_le_offerte_col_tetto_di_b_e_col_tetto_di_indifferenza_sono_disgiunte(
        caricati):
    """I due contatori partizionano le chiamate a `_max_bid_for`: se si
    sovrapponessero, la quota d'uso del tetto non sarebbe leggibile."""
    res = _gioca(caricati["tetti"], caricati["contesto"])
    bot = res["bot"]
    r = bot.rapporto()
    totale = (r["offerte_con_tetto_indifferenza"] + r["offerte_con_tetto_di_b"])
    assert totale > 0
    assert r["quota_offerte_con_tetto_indifferenza"] == pytest.approx(
        r["offerte_con_tetto_indifferenza"] / totale)
    assert r["tetti_respinti"] == sum(r["ripieghi_per_ragione"].values())
    assert r["tetti_respinti"] <= r["offerte_con_tetto_di_b"]


def test_i_contatori_del_piano_reggono_col_ledger(caricati):
    """Fix precedente da conservare: le cinque categorie sono disgiunte e
    chiudono col ledger del motore."""
    res = _gioca(caricati["tetti"], caricati["contesto"])
    bot, eng = res["bot"], res["motore"]
    c = bot.conta
    somma = (c["piano_miei_prima"] + c["piano_miei_dopo"] + c["piano_ai_rivali"]
             + c["piano_disponibili"] + c["piano_non_classificati"])
    assert somma == len(bot.piano) - c["piano_fuori_asta"]
    assert c["piano_non_classificati"] == 0
    miei = {pid for r in QUOTE for pid, _ in res["squadra"].roster[r]}
    proprietario = {pid: tid for pid, tid, _ in eng.sold}
    attesi_rivali = {p for p in bot.piano
                     if proprietario.get(p) not in (None,
                                                    res["squadra"].team_id)}
    assert c["piano_miei_dopo"] == len(set(bot.piano) & miei)
    assert c["piano_ai_rivali"] == len(attesi_rivali)


def test_il_pavimento_di_spesa_resta_imposto_dal_solutore(caricati):
    """Fix precedente da conservare: ogni ricalcolo che usa la soglia la
    rispetta, e nessun tetto la scavalca."""
    res = _gioca(caricati["tetti"], caricati["contesto"])
    ultimo = res["bot"].ultimo_ricalcolo
    assert ultimo, "nessun ricalcolo registrato"
    assert res["bot"].conta_milp["pavimento_violato"] == 0
    if ultimo["pavimento_rispettato"] is not None:
        assert ultimo["pavimento_rispettato"] is True, ultimo


# ================================================ lo stato del file gia' salvato
FILE_SALVATO = RADICE / "data" / "l3" / "asta" / "tetti_2026-27.json"


@pytest.mark.skipif(not FILE_SALVATO.exists(),
                    reason=f"serve {FILE_SALVATO}")
def test_il_file_dei_tetti_gia_salvato_e_stale_e_lo_dice():
    """Il file prodotto il 7 settembre 2026 e' nel formato vecchio.

    Non viene toccato: e' la prova datata del run precedente (25 tetti su 25
    `inconcludente`). Sotto il formato nuovo non e' utilizzabile, e questo test
    fissa **perche'**: nessun record dichiara la propria identita' e il file non
    porta il blocco `contesto`. Serve il produttore corretto per rifarlo; finche'
    non lo si rifa', il braccio L3+I coincide con L3 e la ragione e' scritta."""
    fuori = CA.carica_tetti(FILE_SALVATO)
    d = fuori["diagnostica"]
    assert fuori["tetti"] == {}
    assert fuori["contesto"] is None
    assert d["senza_identita"] == d["letti"] > 0
    assert d["contesto_mancante"]


def test_il_caricatore_distingue_identita_assente_da_identita_diversa(
        file_tetti, tmp_path):
    """Due diagnosi diverse per due difetti diversi: il formato vecchio non
    scriveva `giocatore`, il difetto A lo scriveva sbagliato."""
    d = json.loads(file_tetti.read_text("utf-8"))
    senza = json.loads(json.dumps(d["tetti"][STELLA]))
    del senza["giocatore"]
    diverso = json.loads(json.dumps(d["tetti"][SECONDO]))
    diverso["giocatore"] = "non-esiste"
    d["tetti"] = {STELLA: senza, SECONDO: diverso}
    percorso = tmp_path / "identita.json"
    percorso.write_text(json.dumps(d, indent=1, default=str), encoding="utf-8")
    diag = CA.carica_tetti(percorso)["diagnostica"]
    assert diag["senza_identita"] == 1
    assert diag["identita_diversa"] == 1
    assert diag["usabili"] == 0


def test_un_listino_diverso_ferma_i_tetti(caricati):
    """Il completamento surrogato paga il prezzo previsto: se il listino si
    sposta (per esempio perche' `market_heat` lo riscala) il tetto calcolato
    prima non parla piu' dello stesso esperimento. Il blocco `listini` entra
    nel contesto proprio per questo, e il produttore lo dichiara."""
    assert "listini" in caricati["contesto"]
    altro = json.loads(json.dumps(caricati["contesto"]))
    altro["listini"]["impronta"] = "un-altro-listino"
    res = _gioca(caricati["tetti"], altro)
    bot = res["bot"]
    assert bot.conta["offerte_con_tetto_indifferenza"] == 0
    assert bot.ripieghi_per_ragione.get("contesto_diverso", 0) > 0
