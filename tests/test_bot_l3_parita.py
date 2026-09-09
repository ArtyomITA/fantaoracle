"""Parita' dei bracci d'asta L3, sullo stesso flusso di eventi.

Realizza il progetto scritto in `data/l3/audit2/livello3/RAPPORTO.md` §4.4.
L'affermazione da provare e' questa: con l'intervento del Livello 3
disattivato, `BotL3` deve riprodurre `BBotCoerente` **martelletto per
martelletto** — stesse nomination, stessi rilanci, stessi prezzi, stesso stato
interno a ogni aggiudicazione, stessi massimi di offerta, stesse chiamate al
solutore. Controllare che i metodi vengano chiamati non prova niente: il test
precedente confrontava `BotL3(piano=None)` con un altro `BotL3(piano=None)`.

Il mondo e' quello vero dell'esperimento: pack 2026-27 (587 giocatori, quote
3/8/8/6, budget 500), i nove avversari dichiarati in `scripts/l3_confronto_asta.py`,
seme 20260907, nostro seggio 0. Sono cinque aste complete, circa dodici secondi
l'una: e' il prezzo di una prova che puo' davvero fallire.

Che cosa si confronta, per ogni asta:

* la sequenza ordinata di tutti gli eventi pubblici del motore, come tuple
  `(tipo, squadra, giocatore, importo)`;
* a ogni martelletto: target, titolari, modulo, `market_heat()` a sei cifre,
  `hammers_since_replan`, budget e rosa per ruolo;
* ogni chiamata a `optimize_roster`, con `min_spend`, `forced_spend`, budget e
  cardinalita' di `candidates` e `fixed`;
* ogni valore restituito da `_max_bid_for`, nell'ordine in cui e' stato
  chiesto: e' li' che si vedrebbe la perdita dei titolari anche quando l'esito
  dell'asta non cambia.

Le varianti coperte sono quelle elencate nel progetto: quelle che devono
coincidere con B+ e quelle che devono divergere. Una prova di divergenza che
passa perche' il trattamento e' vuoto non prova niente, quindi ogni test di
divergenza controlla prima che il trattamento sia stato davvero applicato.

## I tetti, dall'8 settembre 2026

`BotL3` verifica la chiave di validita' di un tetto prima di usarlo, quindi un
numero nudo `player_id -> float` non entra piu' e un record calcolato su un
altro stato d'asta nemmeno. Le prove qui sotto costruiscono i tetti in due modi
diversi, e la differenza fra i due e' un risultato, non un dettaglio di
fixture:

* **congelati**: i record si costruiscono una volta sola all'avvio, sullo stato
  iniziale (rose vuote, budget pieno, pool intero). E' esattamente quello che
  fa `scripts/l3_tetti.py`. Dal primo martelletto in poi non sono piu' validi,
  quindi il braccio L3+I **coincide** con L3 e i ripieghi sono contati con
  ragione `stato_cambiato`. Il test lo pretende invece di lasciarlo implicito:
  nel run gia' eseguito quella coincidenza c'era (differenza esattamente zero
  in tutte e 22 le repliche) e nessuno sapeva dire perche'.
* **vivi**: una sonda rigenera la chiave del record allo stato corrente prima
  di ogni offerta, cioe' finge un oracolo che ricalcolasse la curva a ogni
  martelletto. Non e' praticabile in produzione (una ventina di secondi per
  giocatore) e non e' una misura di P(1 posto): serve solo a far passare la
  verifica e a provare che, quando un tetto **e'** valido, agisce davvero.
* **vivi con identita' scambiata**: gli stessi record vivi, con dentro il nome
  del giocatore successivo. Prova, sulle chiamate vere del motore, il difetto
  dell'8 settembre 2026: un tetto che parla di un altro giocatore non deve
  agire, e l'asta deve tornare identica a quella senza tetti.

Ogni record porta l'identita' del proprio giocatore (`giocatore`): senza, il
consumatore respinge con `senza_identita`.
"""
from __future__ import annotations

import json
import pickle
import random
import sys
from pathlib import Path

import pytest

RADICE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RADICE / "src"))
sys.path.insert(0, str(RADICE / "scripts"))

from fantabot.bots.bot_l3 import BBotCoerente, BotL3    # noqa: E402
from fantabot.engine.auction import AuctionEngine       # noqa: E402
from fantabot.models import ROLES                       # noqa: E402

SEME = 20260907
SEGGIO = 0
PACK = RADICE / "data" / "packs" / "pack_2026-27.pkl"
PIANO_JSON = RADICE / "data" / "l3" / "pilota" / "rosa_migliore.json"

pytestmark = pytest.mark.skipif(
    not (PACK.exists() and PIANO_JSON.exists()),
    reason=f"servono {PACK} e {PIANO_JSON}: la parita' si prova sul mondo vero")


# ------------------------------------------------------------------ sonde
class Sonda:
    """Registra lo stato interno senza cambiarlo.

    Ogni metodo chiama prima quello vero e poi annota: se la sonda cambiasse
    l'ordine delle operazioni misurerebbe se stessa."""

    def __init__(self, *a, **k):
        super().__init__(*a, **k)
        self.stati: list[tuple] = []
        self.tetti_chiesti: list[str] = []
        self.cap: list[tuple[str, float]] = []
        self.ricalcoli: list[dict] = []
        self.conte: list[dict] = []

    def on_hammer(self, view, player, price, winner):
        super().on_hammer(view, player, price, winner)
        self.stati.append((
            tuple(sorted(self.targets)),
            tuple(sorted(self.starter_targets)),
            self.module,
            round(self.market_heat(), 6),
            self.hammers_since_replan,
            view.me.budget,
            tuple(tuple(sorted(view.me.roster[r])) for r in ROLES),
        ))
        if hasattr(self, "conta"):
            self.conte.append(dict(self.conta))

    def _max_bid_for(self, pid):
        self.tetti_chiesti.append(pid)
        v = super()._max_bid_for(pid)
        self.cap.append((pid, round(float(v), 9)))
        return v

    def _registra_ricalcolo(self, view, ctx, tentativo):
        super()._registra_ricalcolo(view, ctx, tentativo)
        self.ricalcoli.append({**self.ultimo_ricalcolo,
                               "forzati": tuple(sorted(ctx["forzati"])),
                               "target": tuple(sorted(self.targets))})


class SondaBPiu(Sonda, BBotCoerente):
    pass


class SondaL3(Sonda, BotL3):
    pass


# Componenti della chiave che l'asta non osserva. Qui sono etichette: queste
# prove non toccano il cubo, e la verifica della chiave ha il suo file
# (`tests/test_bot_l3_tetti.py`). Devono solo essere le stesse nel record e nel
# contesto dichiarato al bot, altrimenti ogni tetto viene respinto.
CONTESTO_TETTI = {
    "cubo": {"impronta": "cubo-di-prova-parita", "forma": None},
    "esperimento": {"scenari": [0], "n_scenari": 1, "repliche": 4, "seme": SEME,
                    "giornate": None, "impronta_calendario": None,
                    "completamento": "assegnazione_per_priorita"},
    "regole": {"quote": {"P": 3, "D": 8, "C": 8, "A": 6}, "budget": 500},
}


class ConTetti:
    """Sonda che fabbrica i record dei tetti, congelati o vivi.

    `tetti_vivi = False` riproduce il file congelato di `scripts/l3_tetti.py`:
    un solo stato d'asta, quello iniziale. `tetti_vivi = True` rigenera la
    chiave prima di ogni offerta, cioe' finge un oracolo che ricalcolasse la
    curva a ogni martelletto. In entrambi i casi il *numero* e' finto (1
    credito): quello che si misura e' se il tetto entra, non quanto vale."""

    pid_con_tetto: tuple = ()
    tetto_finto: float = 1.0
    tetti_vivi: bool = False
    # identita' scritta nel record. Normalmente e' quella del giocatore sotto
    # cui il record viene riposto; `scambia_identita` la sposta di uno per
    # provare, sulle chiamate vere dell'asta, che un record che parla di un
    # altro giocatore non entra.
    scambia_identita: bool = False

    def __init__(self, *a, **k):
        super().__init__(*a, **k)
        self.esiti_di_validita: list[str] = []

    def _rigenera_tetti(self, view):
        chiave = self.chiave_stato_corrente(view)
        elenco = list(self.pid_con_tetto)
        self.tetti = {}
        for i, pid in enumerate(elenco):
            # l'identita' del record e' obbligatoria: senza, il consumatore
            # respinge con `senza_identita` (difetto dell'8 settembre 2026,
            # un record di A0 riposto sotto la chiave A1 veniva accettato)
            ident = (elenco[(i + 1) % len(elenco)] if self.scambia_identita
                     else pid)
            self.tetti[pid] = {
                "giocatore": ident,
                "tetto_economico": self.tetto_finto, "stato": "verificato",
                "completamento": {"tipo": "assegnazione_per_priorita"},
                "massimo_legale": chiave["massimo_legale"],
                "chiave_validita": {"stato_decisionale": chiave,
                                    **CONTESTO_TETTI}}

    def start_auction(self, view):
        self._rigenera_tetti(view)
        super().start_auction(view)

    def bid(self, view, player, price, leader):
        if self.tetti_vivi:
            self._rigenera_tetti(view)
        if player.player_id in self.tetti:
            # senza questa traccia una prova di divergenza potrebbe passare
            # perche' i record non erano validi, non per il confine che vuole
            # misurare
            self.esiti_di_validita.append(
                self._tetto_validato(player.player_id, view)[1])
        return super().bid(view, player, price, leader)


class SondaL3ConTetti(ConTetti, Sonda, BotL3):
    pass


# ------------------------------------------------------------------ mondo
def _pack():
    with open(PACK, "rb") as f:
        return pickle.load(f)


def _piano() -> dict:
    d = json.loads(PIANO_JSON.read_text(encoding="utf-8"))
    return {str(pid): {"titolare": False}
            for r in d.get("rosa", {}) for pid in d["rosa"][r]}


def _gioca(costruisci):
    """Un'asta completa con il nostro bot al seggio 0 e i nove avversari veri."""
    import l3_confronto_asta as CA
    import fantabot.bots.bot_l3 as M

    pack = _pack()
    chiamate: list[tuple] = []
    vero = M.optimize_roster

    def spia(candidates, prices, values, quotas, budget, **kw):
        chiamate.append((kw.get("min_spend"), _congela(kw.get("forced_spend")),
                         round(float(budget), 6), len(candidates),
                         len(kw.get("fixed") or {})))
        return vero(candidates, prices, values, quotas, budget, **kw)

    rng = random.Random(SEME)
    specs = list(CA.AVVERSARI)
    bots, j = [], 0
    for i in range(10):
        if i == SEGGIO:
            bots.append(costruisci(random.Random(SEME * 1000 + i), pack))
        else:
            bots.append(CA.fai_avversario(specs[j], random.Random(SEME * 1000 + i),
                                          pack))
            j += 1
    eng = AuctionEngine(dict(pack.players), bots, pack.quotas, pack.budget, rng)
    M.optimize_roster = spia
    try:
        squadre = eng.run()
    finally:
        M.optimize_roster = vero
    return {"impronta": _impronta(eng), "bot": bots[SEGGIO], "motore": eng,
            "squadra": squadre[SEGGIO], "chiamate": chiamate, "pack": pack}


def _congela(forced):
    if not forced:
        return None
    return tuple(sorted((r, round(lo, 6), round(hi, 6))
                        for r, (lo, hi) in forced.items()))


def _impronta(eng):
    """Sequenza confrontabile degli eventi pubblici del motore."""
    out = []
    for e in eng.events:
        p = e.payload
        if e.kind == "nomination":
            out.append(("N", p["team"], p["player_id"], p["opening"]))
        elif e.kind == "bid":
            out.append(("B", p["team"], p["player_id"], p["amount"]))
        elif e.kind == "hammer":
            out.append(("H", p["team"], p["player_id"], p["price"]))
    return out


_CACHE: dict[str, dict] = {}


def _giocatori_di_controllo() -> tuple:
    """Giocatori che B+ ha davvero fra i target al primo martelletto.

    Servono a rendere la prova di parita' pericolosa: se il tetto per
    indifferenza agisse anche fuori dal piano, un tetto da 1 credito su questi
    lo farebbe esplodere."""
    b = _run("B+")
    return tuple(b["bot"].stati[0][0])


def _con_tetti(rng, pred, obj, piano, pid_con_tetto, vivi: bool,
               scambia: bool = False):
    bot = SondaL3ConTetti(rng, pred, piano=piano, tetti=None, objective=obj,
                          usa_indifferenza=True,
                          contesto_tetti=CONTESTO_TETTI)
    bot.pid_con_tetto = tuple(pid_con_tetto)
    bot.tetti_vivi = vivi
    bot.scambia_identita = scambia
    return bot


def _run(nome: str) -> dict:
    if nome in _CACHE:
        return _CACHE[nome]

    def costruisci(rng, pack):
        obj = getattr(pack, "b_objective", None)
        pred = pack.b_predictions
        if nome == "B+":
            return SondaBPiu(rng, pred, objective=obj)
        if nome == "L3_spento":
            return SondaL3(rng, pred, piano=None, tetti=None, objective=obj,
                           usa_indifferenza=False)
        if nome == "L3_spento_con_tetti":
            return _con_tetti(rng, pred, obj, None, _giocatori_di_controllo(),
                              vivi=True)
        if nome == "L3_piano":
            return SondaL3(rng, pred, piano=_piano(), tetti=None,
                           objective=obj, usa_indifferenza=False)
        if nome == "L3_piano_tetti_congelati":
            piano = _piano()
            return _con_tetti(rng, pred, obj, piano, tuple(piano), vivi=False)
        if nome == "L3_piano_tetti_vivi":
            piano = _piano()
            return _con_tetti(rng, pred, obj, piano, tuple(piano), vivi=True)
        if nome == "L3_piano_tetti_vivi_identita_scambiata":
            piano = _piano()
            return _con_tetti(rng, pred, obj, piano, tuple(piano), vivi=True,
                              scambia=True)
        raise ValueError(nome)

    _CACHE[nome] = _gioca(costruisci)
    return _CACHE[nome]


def _primo_scarto(a, b, etichetta):
    if a == b:
        return None
    for k in range(min(len(a), len(b))):
        if a[k] != b[k]:
            return f"{etichetta}: divergono al passo {k}: {a[k]} contro {b[k]}"
    return f"{etichetta}: lunghezze diverse, {len(a)} contro {len(b)}"


def _uguali(x, y, etichetta):
    msg = _primo_scarto(x, y, etichetta)
    assert msg is None, msg


# ------------------------------------------------------------------ parita'
def test_il_mondo_di_prova_e_quello_dell_esperimento():
    """Se il mondo cambia, i test qui sotto non parlano piu' dell'esperimento."""
    b = _run("B+")
    assert len(b["pack"].players) == 587
    assert dict(b["pack"].quotas) == {"P": 3, "D": 8, "C": 8, "A": 6}
    assert b["pack"].budget == 500
    assert len(b["impronta"]) > 2000, len(b["impronta"])
    assert len(b["bot"].stati) == 250, len(b["bot"].stati)


def test_parita_martelletto_per_martelletto_con_intervento_spento():
    a, b = _run("B+"), _run("L3_spento")
    _uguali(a["impronta"], b["impronta"], "eventi del motore")
    _uguali(a["bot"].stati, b["bot"].stati, "stato interno a ogni martelletto")
    _uguali(a["bot"].cap, b["bot"].cap, "massimi di offerta")
    _uguali(a["chiamate"], b["chiamate"], "chiamate a optimize_roster")
    assert a["squadra"].budget == b["squadra"].budget
    assert ({r: sorted(a["squadra"].roster[r]) for r in ROLES}
            == {r: sorted(b["squadra"].roster[r]) for r in ROLES})


def test_i_tetti_non_agiscono_quando_il_piano_e_vuoto():
    """Con `piano` vuoto il tetto per indifferenza non deve mai entrare.

    Il test controlla anche di essere pericoloso su due fronti: i tetti valgono
    1 credito e stanno su giocatori che il bot ha davvero fra i target, e sono
    **vivi**, cioe' passerebbero la verifica di validita'. Con tetti congelati
    la prova sarebbe vacua: verrebbero respinti comunque e il confine del piano
    non sarebbe piu' quello che li ferma."""
    giocatori = _giocatori_di_controllo()
    assert giocatori, "senza tetti il test non proverebbe niente"
    a, c = _run("B+"), _run("L3_spento_con_tetti")
    toccati = set(c["bot"].tetti_chiesti) & set(giocatori)
    assert toccati, ("nessun giocatore con tetto e' mai passato da "
                     "_max_bid_for: il test sarebbe vacuo")
    assert "valido" in c["bot"].esiti_di_validita, (
        "nessun record era valido: a fermare i tetti non e' stato il confine "
        "del piano ma la verifica, e il test non prova quello che dice")
    assert c["bot"].conta["offerte_con_tetto_indifferenza"] == 0
    assert c["bot"].conta["tetti_respinti"] == 0, (
        "fuori dal piano un tetto non si chiede nemmeno: non e' un ripiego")
    _uguali(a["impronta"], c["impronta"], "eventi del motore")
    _uguali(a["bot"].cap, c["bot"].cap, "massimi di offerta")
    _uguali(a["bot"].stati, c["bot"].stati, "stato interno a ogni martelletto")


# --------------------------------------------------------------- divergenze
def test_il_piano_cambia_davvero_l_asta():
    """Il braccio L3 deve differire da B+, e differire *per il piano*.

    Le prime tre verifiche sono sul meccanismo e valgono per costruzione: gli
    obbligati devono uscire dal solutore dentro i target, altrimenti il piano
    non e' stato imposto. L'ultima e' sull'esito e potrebbe cambiare con i
    dati: se cambia va spiegata, non tolta."""
    a, d = _run("B+"), _run("L3_piano")
    assert d["bot"].conta["ricalcoli_con_piano"] > 0
    assert d["impronta"] != a["impronta"], (
        "il piano non ha cambiato nulla: il braccio L3 non e' un trattamento")

    forzati_totali = sum(len(r["forzati"]) for r in d["bot"].ricalcoli)
    assert forzati_totali > 0, "nessun giocatore del piano e' mai stato imposto"
    for i, r in enumerate(d["bot"].ricalcoli):
        assert set(r["forzati"]) <= set(r["target"]), (
            f"ricalcolo {i}: gli obbligati non sono finiti nei target, "
            f"mancano {sorted(set(r['forzati']) - set(r['target']))}")

    piano = set(_piano())
    prezzo_a = {pid: pr for pid, tid, pr in a["motore"].sold
                if tid == a["squadra"].team_id}
    crediti_a = sum(prezzo_a.get(pid, 0) for pid in piano)
    crediti_d = d["bot"].conta["crediti_sul_piano"]
    assert crediti_d > crediti_a, (
        f"L3 impegna sul piano {crediti_d} crediti, B+ ne impegna {crediti_a}: "
        "inseguire il piano non sta cambiando dove finiscono i soldi")


def test_il_piano_non_fa_sparire_il_pavimento_di_spesa():
    """Il difetto piu' grave: l'ancoraggio scartava la soluzione del MILP e con
    essa `min_spend`. Misurato prima: costo dei target dopo/prima 0,891 in
    mediana su 51 ancoraggi. Adesso il pavimento e' imposto dal solutore, e
    ogni ricalcolo del braccio L3 lo deve rispettare come quello di B+."""
    a, d = _run("B+"), _run("L3_piano")
    for nome, r in (("B+", a), ("L3", d)):
        ric = r["bot"].ricalcoli
        assert ric, f"{nome}: nessun ricalcolo registrato"
        con_soglia = [x for x in ric if x["pavimento_rispettato"] is not None]
        assert con_soglia, (
            f"{nome}: il pavimento non e' mai stato applicabile, "
            "il test non proverebbe niente")
        rotti = [x for x in con_soglia if x["pavimento_rispettato"] is not True]
        assert not rotti, f"{nome}: {len(rotti)} ricalcoli sotto il pavimento, "\
                          f"primo {rotti[0]}"
        assert r["bot"].conta_milp["pavimento_violato"] == 0
        # contabilita' dei ripieghi: ogni ricalcolo deve stare in una casella
        # sola, altrimenti «quante volte il pavimento e' stato impossibile» non
        # e' un numero leggibile
        c = r["bot"].conta_milp
        totale = sum(c[k] for k in ("soglia_e_attacco", "solo_soglia",
                                    "solo_attacco", "nessun_vincolo", "greedy"))
        assert totale == len(r["bot"].ricalcoli), (nome, c)


def test_i_tetti_vivi_cambiano_l_asta_quando_il_piano_c_e():
    """Se i tetti sono vuoti o mai validi la divergenza non puo' esistere: il
    test lo dice invece di passare in silenzio."""
    d, e = _run("L3_piano"), _run("L3_piano_tetti_vivi")
    assert e["bot"].tetti, "nessun tetto: il braccio L3+I coincide con L3"
    assert e["bot"].conta["offerte_con_tetto_indifferenza"] > 0, (
        "i tetti non sono mai stati usati: la divergenza non e' misurabile")
    assert e["impronta"] != d["impronta"]


def test_i_tetti_congelati_non_sopravvivono_al_primo_martelletto():
    """Il risultato principale della correzione, scritto come prova.

    I tetti del progetto sono calcolati su un solo stato d'asta (rose vuote,
    budget 500, pool intero) e usati per tutta l'asta. Dal primo martelletto in
    poi quello stato non esiste piu': ogni tetto viene respinto per
    `stato_cambiato`, il braccio L3+I coincide con L3 e la ragione e' scritta
    nel rapporto invece di restare un mistero.

    Nel run gia' eseguito la coincidenza c'era (differenza esattamente zero in
    tutte e 22 le repliche) ma per un altro motivo: il file dichiarava 25 tetti
    `inconcludente` e `l3_confronto_asta.py` ne ammetteva zero, quindi il
    dizionario passato al bot era vuoto. Qui i tetti ci sono, sono ammessi, e a
    fermarli e' la verifica di validita'."""
    d, f = _run("L3_piano"), _run("L3_piano_tetti_congelati")
    bot = f["bot"]
    assert bot.tetti, "nessun tetto: la prova sarebbe vacua"
    assert bot.esiti_di_validita, (
        "nessun giocatore con tetto e' mai stato all'asta: prova vacua")
    assert bot.esiti_di_validita.count("valido") == 0, (
        "un tetto congelato e' stato accettato a stato cambiato")
    assert bot.conta["offerte_con_tetto_indifferenza"] == 0
    assert bot.conta["tetti_respinti"] > 0, (
        "nessun tetto e' mai stato chiesto: il ripiego non e' misurato")
    assert bot.ripieghi_per_ragione.get("stato_cambiato", 0) > 0, (
        f"ripieghi per ragione: {bot.ripieghi_per_ragione}")
    assert (sum(bot.ripieghi_per_ragione.values())
            == bot.conta["tetti_respinti"])
    # coincidenza col braccio senza tetti, ed e' una conseguenza della
    # verifica, non un caso
    _uguali(d["impronta"], f["impronta"], "eventi del motore")
    _uguali(d["bot"].cap, f["bot"].cap, "massimi di offerta")


# --------------------------------------------------------------- contatori
def test_i_contatori_del_piano_riconciliano_col_ledger():
    """I cinque contatori devono chiudere lotto per lotto col ledger d'asta.

    Il vecchio `piano_perso` contava ogni giocatore uscito da `view.pool`, ma
    il motore toglie dal pool anche i nostri acquisti: nella replica misurata
    dall'audit dei 20 «persi» dieci erano in rosa nostra."""
    d = _run("L3_piano")
    bot, eng, mia = d["bot"], d["motore"], d["squadra"]
    piano = set(_piano())
    miei = {pid for r in ROLES for pid, _ in mia.roster[r]}
    prezzo = {pid: pr for pid, _, pr in eng.sold}
    proprietario = {pid: tid for pid, tid, _ in eng.sold}
    c = bot.conta

    attesi_miei = piano & miei
    attesi_rivali = {p for p in piano
                     if p in proprietario and proprietario[p] != mia.team_id}
    attesi_liberi = piano & set(eng.pool)

    assert c["piano_miei_prima"] == 0, "asta partita da zero: nessuno gia' nostro"
    assert c["piano_miei_dopo"] == len(attesi_miei), c
    assert c["piano_ai_rivali"] == len(attesi_rivali), c
    assert c["piano_disponibili"] == len(attesi_liberi), c
    assert c["piano_non_classificati"] == 0, c
    assert c["crediti_sul_piano"] == sum(prezzo[p] for p in attesi_miei), c
    assert c["crediti_persi_sul_piano"] == sum(prezzo[p] for p in attesi_rivali), c
    assert c["piano_scartati_dal_ricalcolo"] <= c["piano_disponibili"], c

    # la distinzione che il vecchio contatore non faceva
    assert attesi_miei, "in questa asta L3 non compra niente del piano: "\
                        "il difetto non sarebbe osservabile"
    fuori_dal_pool = len(piano) - len(attesi_liberi)
    assert c["piano_ai_rivali"] < fuori_dal_pool, (
        f"«uscito dal pool» {fuori_dal_pool} non e' «perso» "
        f"{c['piano_ai_rivali']}")


def test_l_invariante_dei_contatori_regge_a_ogni_martelletto():
    d = _run("L3_piano")
    piano = len(_piano())
    for i, c in enumerate(d["bot"].conte):
        somma = (c["piano_miei_prima"] + c["piano_miei_dopo"]
                 + c["piano_ai_rivali"] + c["piano_disponibili"]
                 + c["piano_non_classificati"])
        assert somma == piano - c["piano_fuori_asta"], (
            f"martelletto {i}: {somma} contro {piano - c['piano_fuori_asta']}, "
            f"{c}")
        assert c["piano_non_classificati"] == 0, i
        assert c["piano_scartati_dal_ricalcolo"] <= c["piano_disponibili"], i


def test_un_tetto_di_un_altro_giocatore_non_agisce_in_asta():
    """Difetto dell'8 settembre 2026, provato sulle chiamate vere del motore.

    I record sono **vivi** — la chiave e' rigenerata a ogni offerta, quindi lo
    stato combacia sempre — e cambia una cosa sola: l'identita' scritta dentro
    e' quella del giocatore successivo dell'elenco. Prima della correzione il
    consumatore leggeva solo la chiave del dizionario, e la chiave di validita'
    descrive lo stato del mondo, che e' identico per tutti: un tetto finito
    sotto il nome sbagliato agiva sul giocatore sbagliato.

    Il confronto e' con il braccio senza tetti: l'asta deve tornare quella,
    martelletto per martelletto."""
    d = _run("L3_piano")
    g = _run("L3_piano_tetti_vivi_identita_scambiata")
    bot = g["bot"]
    assert bot.tetti, "nessun tetto: prova vacua"
    assert bot.esiti_di_validita, "nessun tetto e' mai stato all'asta"
    assert bot.esiti_di_validita.count("valido") == 0
    assert bot.conta["offerte_con_tetto_indifferenza"] == 0
    assert bot.ripieghi_per_ragione.get("identita_diversa", 0) > 0, (
        f"ripieghi per ragione: {bot.ripieghi_per_ragione}")
    _uguali(d["impronta"], g["impronta"], "eventi del motore")
    _uguali(d["bot"].cap, g["bot"].cap, "massimi di offerta")
    # e la prova non e' vacua: con l'identita' giusta gli stessi record
    # agiscono davvero
    e = _run("L3_piano_tetti_vivi")
    assert e["bot"].conta["offerte_con_tetto_indifferenza"] > 0
    assert e["impronta"] != g["impronta"]
