"""Il piano del Livello 3 entra nel MILP come vincolo, non dopo di esso.

Difetto misurato prima della correzione (`data/l3/audit2/livello3/RAPPORTO.md`
§4.3, 51 ancoraggi di un'asta intera): `_ancora_al_piano` girava dopo
`BBotCoerente._replan` e riscriveva `self.targets`, buttando via la soluzione
del MILP e con essa il pavimento di spesa `min_spend`. Il costo previsto dei
target scendeva in mediana allo 0,891 di quello pianificato e i titolari da 6 a
4. Adesso i giocatori del piano ancora in vendita vanno in `fixed` dentro
`optimize_roster`, con budget e soglia compensati del loro prezzo previsto:
quote, budget, quota d'attacco e pavimento restano imposti dal solutore.

Nota sulla fixture, che prima era il vero difetto di questi test.
Le quote usate fino all'8 settembre 2026 erano `{P:1, D:2, C:2, A:1}`. Con solo
due difensori in rosa il vincolo dei titolari di `optimize_roster`
(`somma s_i per ruolo == slot del modulo`, e ogni modulo vuole almeno tre
difensori) e' **insoddisfacibile**: tutti e quattro i tentativi del MILP
tornavano `None` e ogni prova finiva nel ripiego `greedy_roster`, che ignora
`min_spend` e non produce titolari. Nessuno di quei test toccava il MILP. Le
quote di qui sotto (`{P:2, D:5, C:5, A:3}`) ammettono il modulo 4-4-2, quindi
il solutore risolve davvero e il pavimento di spesa e' esigibile.

Il listino ha tre fasce, e servono tutte e tre:

* `utili` (indici 0-7), valore decrescente e prezzo crescente: sono quelli che
  il MILP compra;
* `scarto` (indice 8), prezzo basso e valore basso: il MILP non li prende mai,
  quindi un piano fatto di scarti e' un trattamento davvero diverso dal piano
  di B+, e il test lo verifica invece di darlo per scontato;
* `riempitivo` (indici 9-14), prezzo previsto 1 credito: senza una fascia da un
  credito la guardia «tieni un credito per ogni posto vuoto» non basterebbe a
  garantire che il MILP resti fattibile, e il test misurerebbe la fixture
  invece del codice.
"""
import random
import sys
from pathlib import Path

RADICE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RADICE / "src"))

from fantabot.bots.base import AuctionView              # noqa: E402
from fantabot.bots.bot_l3 import BBotCoerente, BotL3    # noqa: E402
from fantabot.models import Player, TeamState           # noqa: E402

# 15 slot, modulo 4-4-2 ammissibile (1+4+4+2 titolari dentro le quote)
QUOTE = {"P": 2, "D": 5, "C": 5, "A": 3}
BUDGET = 200
UTILI = 8            # indici 0..7
SCARTO = 8           # indice 8
RIEMPITIVI = range(9, 15)

# soglia del pavimento con `min_spend_frac` predefinito (0,95): 190, che
# `optimize_roster` taglia a `budget - (slot da riempire - 1)` = 200 - 14 = 186
SOGLIA_ATTESA = 186.0


def _valore(k: int) -> float:
    if k == SCARTO:
        return 20.0
    if k in RIEMPITIVI:
        return 5.0
    return 100.0 - 5.0 * k


def _q50(k: int) -> float:
    if k == SCARTO:
        return 2.0
    if k in RIEMPITIVI:
        return 0.5          # `max(1.0, q50 * heat)` lo porta a 1 credito
    return 2.0 + 4.0 * k


def _indici():
    return list(range(UTILI)) + [SCARTO] + list(RIEMPITIVI)


def _pool(esclusi=()):
    pool = {}
    for ruolo in ("P", "D", "C", "A"):
        for k in _indici():
            pid = f"{ruolo}{k}"
            if pid in esclusi:
                continue
            pool[pid] = Player(pid, pid, ruolo, f"sq{k}", ref_price=0.05,
                               exp_points=_valore(k))
    return pool


def _predizioni():
    return {f"{r}{k}": {"value": _valore(k), "value_up": _valore(k) + 10.0,
                        "q50": _q50(k), "q90": _q50(k) * 1.8,
                        "q10": _q50(k) * 0.6, "pres": 30.0}
            for r in ("P", "D", "C", "A") for k in _indici()}


def _vista(pool, roster=None, budget=BUDGET, venduti=None):
    me = TeamState("T0", "L3", budget,
                   roster or {r: [] for r in ("P", "D", "C", "A")})
    return AuctionView(me=me, others=[], quotas=QUOTE, budget_total=BUDGET,
                       current_role="A", pool=pool, sold=list(venduti or []))


def _costo(bot, pids, heat=1.0):
    return sum(max(1.0, bot._q(pid, "q50") * heat) for pid in pids)


def _piano(pids):
    return {pid: {"titolare": False} for pid in pids}


def _bot(pool, piano=None, tetti=None, usa_indifferenza=False):
    return BotL3(random.Random(0), _predizioni(), piano=_piano(piano or ()),
                 tetti=tetti, usa_indifferenza=usa_indifferenza,
                 contesto_tetti=CONTESTO_TETTI)


# Componenti della chiave di validita' che l'asta non osserva: qui sono
# etichette, perche' questi test non toccano il cubo. La verifica della chiave
# ha il suo file, `tests/test_bot_l3_tetti.py`.
CONTESTO_TETTI = {
    "cubo": {"impronta": "cubo-di-prova", "forma": None},
    "esperimento": {"scenari": [0], "n_scenari": 1, "repliche": 4, "seme": 0,
                    "giornate": None, "impronta_calendario": None,
                    "completamento": "assegnazione_per_priorita"},
    "regole": {"quote": dict(QUOTE), "budget": BUDGET},
}


def _record_tetto(view, giocatore: str, tetto: float,
                  stato: str = "verificato") -> dict:
    """Un risultato di `curva()` valido per lo stato `view` e per `giocatore`.

    La chiave osservabile viene da `BotL3.chiave_stato_corrente`, cioe' dal
    consumatore stesso: qui va bene perche' l'oggetto del test e' il confine
    del piano, non la verifica della chiave. La verifica e' provata contro una
    seconda implementazione scritta a mano e contro
    `indifferenza.chiave_di_validita` in `tests/test_bot_l3_tetti.py`.

    `giocatore` e' obbligatorio dall'8 settembre 2026: un record che non
    dichiara di chi parla non e' verificabile, e uno che dichiara un altro
    giocatore non deve agire su questo."""
    sonda = BotL3(random.Random(0), _predizioni())
    return {"giocatore": giocatore, "tetto_economico": tetto, "stato": stato,
            "completamento": {"tipo": "assegnazione_per_priorita"},
            "chiave_validita": {
                "stato_decisionale": sonda.chiave_stato_corrente(view),
                **CONTESTO_TETTI}}


def _b_piu(min_spend_frac=None):
    kw = {} if min_spend_frac is None else {"min_spend_frac": min_spend_frac}
    return BBotCoerente(random.Random(0), _predizioni(), **kw)


# giocatori che il MILP non sceglie mai: valore 20 contro 65-100 allo stesso
# prezzo o meno. Un piano fatto di questi e' un trattamento distinguibile.
PIANO_FUORI_DAL_MILP = ("P8", "D8", "C8", "A8")
# 15 giocatori cari: 354 crediti previsti contro 200 di budget. Serve a provare
# il troncamento, non il caso normale.
PIANO_TROPPO_CARO = ("P6", "P7", "D3", "D4", "D5", "D6", "D7",
                     "C3", "C4", "C5", "C6", "C7", "A5", "A6", "A7")
# 15 riempitivi da 1 credito: riempiono tutti gli slot e costano 15 crediti in
# tutto, quindi rendono il pavimento (186) irraggiungibile. E' il caso in cui
# piano e vincolo economico si contendono gli stessi posti.
PIANO_TROPPO_ECONOMICO = ("P9", "P10", "D9", "D10", "D11", "D12", "D13",
                          "C9", "C10", "C11", "C12", "C13", "A9", "A10", "A11")


# --------------------------------------------------------------- selezione
def test_il_piano_sopravvive_alla_ripianificazione():
    """I giocatori del piano restano target dopo il ricalcolo.

    Il test si autoverifica: prima controlla che B+ da solo **non** li
    scegliesse, altrimenti non starebbe misurando niente."""
    riferimento = _b_piu()
    riferimento.start_auction(_vista(_pool()))
    assert not set(PIANO_FUORI_DAL_MILP) & riferimento.targets, (
        "fixture inutile: B+ sceglie gia' giocatori del piano da solo, "
        f"target {sorted(riferimento.targets)}")

    pool = _pool()
    bot = _bot(pool, piano=PIANO_FUORI_DAL_MILP)
    vista = _vista(pool)
    bot.start_auction(vista)
    assert set(PIANO_FUORI_DAL_MILP) <= bot.targets
    bot._replan(vista)                       # e' qui che il piano spariva
    rimasti = set(PIANO_FUORI_DAL_MILP) & set(bot.targets)
    assert rimasti == set(PIANO_FUORI_DAL_MILP), (
        f"il piano non sopravvive: restano {sorted(rimasti)}")


def test_i_giocatori_del_piano_gia_venduti_non_bloccano_i_posti():
    """Chi non e' piu' nel pool esce dal piano e il posto si riempie."""
    pool = _pool(esclusi={"A8"})              # l'attaccante del piano e' venduto
    bot = _bot(pool, piano=PIANO_FUORI_DAL_MILP)
    vista = _vista(pool)
    bot.start_auction(vista)
    bot._replan(vista)
    attaccanti = [pid for pid in bot.targets if pid.startswith("A")]
    assert len(attaccanti) == QUOTE["A"]
    assert "A8" not in bot.targets
    assert bot.conta["piano_forzati_nel_milp"] == len(PIANO_FUORI_DAL_MILP) - 1


def test_i_target_restano_dentro_le_quote_e_il_budget():
    """Un piano che non ci sta viene troncato prima del solutore, non buttato.

    Riscritto: la versione precedente confrontava una spesa massima possibile
    di 60 con un budget di 100 (assert infalsificabile) e usava `q50` senza
    `heat`, mentre il codice ragiona su `q50 * heat`. Qui il piano costa 354
    crediti contro 200 di budget, quindi la guardia serve davvero: senza di
    essa il MILP diventerebbe infattibile e il piano verrebbe abbandonato tutto
    in una volta invece che troncato."""
    pool = _pool()
    bot = _bot(pool, piano=PIANO_TROPPO_CARO)
    vista = _vista(pool)
    bot.start_auction(vista)
    bot._replan(vista)
    heat = bot.market_heat()

    for ruolo, quanti in QUOTE.items():
        n = len([pid for pid in bot.targets if pid.startswith(ruolo)])
        assert n == quanti, f"{ruolo}: {n} target per {quanti} posti"

    forzati = set(PIANO_TROPPO_CARO) & set(bot.targets)
    assert bot.conta["piano_scartato_per_infattibilita"] == 0, (
        "il piano e' stato abbandonato invece che troncato")
    assert forzati, "nessun giocatore del piano e' entrato nei target"
    assert len(forzati) == bot.conta["piano_forzati_nel_milp"]
    assert bot.conta["piano_troncati_dal_vincolo"] == (
        len(PIANO_TROPPO_CARO) - len(forzati))

    # la guardia: il costo previsto dei forzati piu' un credito per ogni altro
    # posto ancora vuoto deve stare nel budget
    vuoti_dopo = sum(QUOTE.values()) - len(forzati)
    assert _costo(bot, forzati, heat) + vuoti_dopo <= BUDGET
    # e la soluzione completa resta comunque dentro il budget
    assert _costo(bot, bot.targets, heat) <= BUDGET


def test_il_pavimento_di_spesa_sopravvive_al_piano():
    """Il vincolo economico di B+ vale anche nel braccio L3.

    Prima della correzione l'ancoraggio girava dopo il MILP e riempiva i posti
    liberi con i target rimasti in ordine di valore, cioe' con i piu'
    economici: il costo previsto crollava sotto la soglia. La fixture si
    controlla da sola confrontando lo stesso bot con `min_spend_frac = 0`: se
    il pavimento non fosse un vincolo attivo i due costi coinciderebbero."""
    senza = _b_piu(min_spend_frac=0.0)
    senza.start_auction(_vista(_pool()))
    costo_senza = _costo(senza, senza.targets)
    assert costo_senza < SOGLIA_ATTESA, (
        f"fixture inutile: senza pavimento si spende gia' {costo_senza}")

    riferimento = _b_piu()
    riferimento.start_auction(_vista(_pool()))
    costo_b = _costo(riferimento, riferimento.targets)
    assert costo_b + 1e-6 >= SOGLIA_ATTESA, (
        f"B+ non rispetta il pavimento: {costo_b} < {SOGLIA_ATTESA}")

    pool = _pool()
    bot = _bot(pool, piano=PIANO_FUORI_DAL_MILP)
    vista = _vista(pool)
    bot.start_auction(vista)
    bot._replan(vista)
    costo_l3 = _costo(bot, bot.targets, bot.market_heat())
    assert costo_l3 + 1e-6 >= SOGLIA_ATTESA, (
        f"il piano ha fatto sparire il pavimento: {costo_l3} < {SOGLIA_ATTESA}")

    r = bot.ultimo_ricalcolo
    assert r["tentativo"] in ("soglia_e_attacco", "solo_soglia"), r
    assert r["pavimento_rispettato"] is True, r
    assert r["costo_previsto"] + 1e-6 >= r["soglia_effettiva"], r
    assert bot.conta_milp["pavimento_violato"] == 0


def test_il_pavimento_viene_prima_del_piano():
    """Quando i due si contendono i posti, cede il piano.

    Il piano di 15 riempitivi occupa tutti gli slot e costa 15 crediti: con
    tutti obbligati la soglia di 186 sarebbe irraggiungibile e il MILP
    ripiegherebbe su una soluzione senza pavimento, cioe' il braccio L3
    tornerebbe a differire da B+ anche sull'economia. La regola dichiarata e'
    l'opposto: si cedono giocatori del piano, dal meno prezioso, finche' la
    soglia torna raggiungibile.

    Non e' un caso di laboratorio: il piano vero dell'11 settembre costa 499,9
    crediti su 500 e occupa tutti e 25 gli slot, quindi ogni giocatore perso
    apre esattamente questo conflitto — misurato, 30 ricalcoli su 53 senza
    pavimento prima di questa regola."""
    pool = _pool()
    bot = _bot(pool, piano=PIANO_TROPPO_ECONOMICO)
    vista = _vista(pool)
    bot.start_auction(vista)
    bot._replan(vista)

    assert bot.conta["piano_ceduto_al_pavimento"] > 0, (
        "nessuna cessione: il piano ha avuto la precedenza sul pavimento")
    assert bot.conta["piano_forzati_nel_milp"] > 0, (
        "ceduto tutto il piano: la cessione deve essere il minimo necessario")
    r = bot.ultimo_ricalcolo
    assert r["tentativo"] in ("soglia_e_attacco", "solo_soglia"), r
    costo = _costo(bot, bot.targets, bot.market_heat())
    assert costo + 1e-6 >= SOGLIA_ATTESA, (
        f"pavimento perso per fare posto al piano: {costo} < {SOGLIA_ATTESA}")


def test_senza_piano_il_comportamento_resta_quello_di_b_piu():
    """Il braccio di controllo deve essere B+, non un altro L3.

    Riscritto: la versione precedente confrontava `BotL3(piano=None)` con un
    altro `BotL3(piano=None)`, quindi non poteva rilevare nessuna differenza
    fra le due classi. La parita' vera, martelletto per martelletto su un'asta
    intera, sta in `tests/test_bot_l3_parita.py`; qui si controlla lo stato
    dopo un ricalcolo, compresi i massimi di offerta."""
    pool_a, pool_b = _pool(), _pool()
    riferimento = _b_piu()
    riferimento.start_auction(_vista(pool_a))
    variante = BotL3(random.Random(0), _predizioni(), piano=None,
                     tetti={"D0": 1.0, "C0": 1.0}, usa_indifferenza=True)
    variante.start_auction(_vista(pool_b))

    assert variante.targets == riferimento.targets
    assert variante.starter_targets == riferimento.starter_targets
    assert variante.module == riferimento.module
    assert variante._best_alt_value == riferimento._best_alt_value
    # anche i massimi di offerta, che sono il punto in cui i tetti potrebbero
    # entrare di soppiatto
    for pid in sorted(pool_a):
        assert variante._max_bid_for(pid) == riferimento._max_bid_for(pid), pid


def test_il_tetto_di_indifferenza_vale_solo_sui_giocatori_del_piano():
    """Un tetto su un giocatore fuori piano non deve agire.

    I tetti sono calcolati prima dell'asta per i giocatori del piano; se
    agissero su qualunque target il braccio di controllo `piano=None` non
    sarebbe piu' un controllo.

    Aggiornato all'8 settembre 2026: i tetti sono record di
    `indifferenza.curva()` verificati contro lo stato d'asta, non piu' numeri
    nudi. Il test e' piu' stringente di prima, non meno: **entrambi** i record
    qui sono validi per lo stato corrente, quindi quello fuori piano viene
    ignorato per il confine e non perche' sarebbe stato respinto comunque.
    Che una forma vecchia `player_id -> float` non entri e' provato a parte in
    `tests/test_bot_l3_tetti.py::test_un_tetto_senza_chiave_non_viene_usato`."""
    pool = _pool()
    vista = _vista(pool)
    fuori, dentro = "D1", "D8"
    bot = _bot(pool, piano=(dentro,), usa_indifferenza=True)
    bot.tetti = {fuori: _record_tetto(vista, fuori, 1.0),
                 dentro: _record_tetto(vista, dentro, 1.0)}
    bot.start_auction(vista)
    riferimento = _b_piu()
    riferimento.start_auction(_vista(_pool()))

    assert bot._max_bid_for(dentro) == 1.0
    assert bot._max_bid_for(fuori) == riferimento._max_bid_for(fuori)
    assert bot.conta["offerte_con_tetto_indifferenza"] == 1
    assert bot.conta["offerte_con_tetto_di_b"] == 1
    assert bot.conta["tetti_respinti"] == 0, (
        "un tetto valido e' stato respinto: il test non starebbe piu' "
        "misurando il confine del piano")
    # il record fuori piano era valido: se lo fosse stato per caso, il confine
    # non sarebbe provato
    assert bot._tetto_validato(fuori, vista)[1] == "valido"


# --------------------------------------------------------------- contatori
def test_i_contatori_non_chiamano_perso_cio_che_abbiamo_comprato_noi():
    """`piano_perso` sommava tre cose diverse; qui sono cinque, disgiunte.

    Il motore toglie dal pool anche i giocatori che compriamo noi
    (`auction.py:185`), quindi «uscito dal pool» non vuol dire «perso». Nella
    replica 0 dell'audit dei 20 «persi» dieci erano in rosa nostra."""
    piano = ("P0", "D0", "D1", "C0", "C1", "A0")
    pool = _pool()
    bot = _bot(pool, piano=piano)
    bot.start_auction(_vista(pool))

    # due del piano li compriamo noi, uno se lo prende un rivale, tre restano
    pool_dopo = _pool(esclusi={"D0", "C0", "A0"})
    roster = {"P": [], "D": [("D0", 12)], "C": [("C0", 9)], "A": []}
    venduti = [("D0", "T0", 12), ("C0", "T0", 9), ("A0", "T9", 7)]
    vista = _vista(pool_dopo, roster=roster, budget=BUDGET - 21,
                   venduti=venduti)
    bot._replan(vista)
    c = bot.conta

    assert c["piano_miei_dopo"] == 2, c
    assert c["piano_miei_prima"] == 0, c
    assert c["piano_ai_rivali"] == 1, c
    assert c["piano_disponibili"] == 3, c
    assert c["piano_non_classificati"] == 0, c
    assert c["piano_fuori_asta"] == 0, c
    somma = (c["piano_miei_prima"] + c["piano_miei_dopo"] + c["piano_ai_rivali"]
             + c["piano_disponibili"] + c["piano_non_classificati"])
    assert somma == len(piano) - c["piano_fuori_asta"], c
    assert c["crediti_sul_piano"] == 21, c
    assert c["crediti_persi_sul_piano"] == 7, c
    # i tre usciti dal pool erano il vecchio `piano_perso`: due su tre nostri
    assert c["piano_ai_rivali"] != 3


def test_i_giocatori_del_piano_fuori_dall_asta_non_falsano_l_invariante():
    """Un identificativo del piano che nell'asta non c'e' proprio va dichiarato
    a parte, non contato come perso."""
    pool = _pool()
    piano = ("P0", "D0", "SCONOSCIUTO")
    bot = _bot(pool, piano=piano)
    bot.start_auction(_vista(pool))
    c = bot.conta
    assert c["piano_fuori_asta"] == 1, c
    assert c["piano_disponibili"] == 2, c
    assert c["piano_non_classificati"] == 0, c


# -------------------------------------------------- target irraggiungibili
def test_quando_il_piano_esce_tutto_dall_asta_il_braccio_torna_a_b_piu():
    """Nessun giocatore del piano e' piu' in vendita: non c'e' piu' niente da
    forzare e il ricalcolo deve ridare esattamente il contesto di B+.

    E' il caso limite di «i target diventano irraggiungibili»: il trattamento
    si spegne da solo, senza fallback e senza contatori di infattibilita'."""
    pool = _pool(esclusi=set(PIANO_FUORI_DAL_MILP))
    bot = _bot(pool, piano=PIANO_FUORI_DAL_MILP)
    vista = _vista(pool)
    bot.start_auction(vista)
    riferimento = _b_piu()
    riferimento.start_auction(_vista(_pool(esclusi=set(PIANO_FUORI_DAL_MILP))))

    assert bot.targets == riferimento.targets
    assert bot.starter_targets == riferimento.starter_targets
    assert bot.conta["piano_forzati_nel_milp"] == 0
    assert bot.conta["piano_troncati_dal_vincolo"] == 0
    assert bot.conta["piano_scartato_per_infattibilita"] == 0
    assert bot.conta["ricalcoli_con_piano"] == 1
    assert bot.ultimo_ricalcolo["costo_forzati"] == 0.0
    # i quattro del piano non sono ne' nostri ne' dei rivali: fuori dall'asta
    assert bot.conta["piano_fuori_asta"] == len(PIANO_FUORI_DAL_MILP)


def test_quando_il_budget_non_basta_nessun_giocatore_del_piano_e_forzato():
    """Con 20 crediti e 15 posti da riempire nessuno del piano ci sta.

    La guardia «tieni un credito per ogni altro posto vuoto» li scarta tutti,
    e il troncamento e' contato: e' l'altro modo in cui i target diventano
    irraggiungibili, per prezzo invece che per disponibilita'."""
    pool = _pool()
    bot = _bot(pool, piano=PIANO_TROPPO_CARO)
    vista = _vista(pool, budget=20)
    bot.start_auction(vista)
    assert bot.conta["piano_forzati_nel_milp"] == 0
    assert bot.conta["piano_troncati_dal_vincolo"] == len(PIANO_TROPPO_CARO)
    assert bot.conta["piano_scartato_per_infattibilita"] == 0
    # il ripiego del solutore, qualunque sia, resta dichiarato e contato una
    # volta sola
    c = bot.conta_milp
    totale = sum(c[k] for k in ("soglia_e_attacco", "solo_soglia",
                                "solo_attacco", "nessun_vincolo", "greedy"))
    assert totale == 1, c


def test_un_piano_che_rende_il_milp_infattibile_e_dichiarato_e_contato():
    """Il fallback del fallback: si abbandona il piano, non i vincoli.

    L'infattibilita' viene forzata a mano — `optimize_roster` restituisce
    `None` ogni volta che riceve acquisti obbligati — perche' con i due tagli
    di `_forzati_ammissibili` un piano che la produca davvero e' raro. Quello
    che il test misura e' il ramo `_ripiego`: contesto ricostruito senza
    obbligati, soluzione trovata comunque, e il caso registrato invece che
    subito in silenzio."""
    import fantabot.bots.bot_l3 as M
    pool = _pool()
    bot = _bot(pool, piano=PIANO_FUORI_DAL_MILP)
    vista = _vista(pool)
    vero = M.optimize_roster
    posseduti = 0                     # rosa vuota: `fixed` = soli obbligati

    def solo_senza_obbligati(candidates, prices, values, quotas, budget, **kw):
        if len(kw.get("fixed") or {}) > posseduti:
            return None
        return vero(candidates, prices, values, quotas, budget, **kw)

    M.optimize_roster = solo_senza_obbligati
    try:
        bot.start_auction(vista)
    finally:
        M.optimize_roster = vero

    assert bot.conta["piano_scartato_per_infattibilita"] == 1
    assert bot.conta["piano_forzati_nel_milp"] == 0
    assert bot.conta["piano_ceduto_al_pavimento"] == 0
    assert bot.conta["piano_troncati_dal_vincolo"] == len(PIANO_FUORI_DAL_MILP)
    assert bot.ultimo_ricalcolo["tentativo"] != "greedy", (
        "abbandonare il piano deve bastare: il greedy e' l'ultima spiaggia")
    assert bot.ultimo_ricalcolo["costo_forzati"] == 0.0
    assert bot.ultimo_ricalcolo["pavimento_rispettato"] is not False
    riferimento = _b_piu()
    riferimento.start_auction(_vista(_pool()))
    assert bot.targets == riferimento.targets, (
        "abbandonato il piano, il contesto deve essere quello di B+")


def test_i_contatori_morti_non_compaiono_nel_rapporto():
    """`fuori_piano` era irraggiungibile e `budget_tempo_s` non era mai letto:
    non devono restare nel rapporto come se misurassero qualcosa."""
    bot = _bot(_pool(), piano=PIANO_FUORI_DAL_MILP)
    r = bot.rapporto()
    assert "fuori_piano" not in r
    assert "budget_tempo_s" not in r
    assert "tempo_speso_s" not in r
    assert not hasattr(bot, "budget_tempo_s")
    assert "offerte_con_tetto_di_b" in r
    assert "quota_offerte_con_tetto_indifferenza" in r


def test_un_tetto_valido_ma_di_un_altro_giocatore_non_agisce():
    """Il confine del piano non e' l'unico: anche dentro il piano, un record
    deve parlare del giocatore su cui viene usato.

    Qui il record e' valido in tutto il resto — stessa chiave, stesso stato,
    stesso completamento — e cambia solo l'identita' dichiarata. Prima della
    correzione dell'8 settembre 2026 il consumatore non la leggeva e il tetto
    entrava lo stesso."""
    pool = _pool()
    vista = _vista(pool)
    dentro, altro = "D8", "C8"
    bot = _bot(pool, piano=(dentro,), usa_indifferenza=True)
    bot.tetti = {dentro: _record_tetto(vista, altro, 1.0)}
    bot.start_auction(vista)
    riferimento = _b_piu()
    riferimento.start_auction(_vista(_pool()))
    assert bot._max_bid_for(dentro) == riferimento._max_bid_for(dentro)
    assert bot.conta["offerte_con_tetto_indifferenza"] == 0
    assert bot.ripieghi_per_ragione == {"identita_diversa": 1}
    # e con l'identita' giusta lo stesso record agisce: la prova non e' vuota
    bot2 = _bot(pool, piano=(dentro,), usa_indifferenza=True)
    bot2.tetti = {dentro: _record_tetto(vista, dentro, 1.0)}
    bot2.start_auction(vista)
    assert bot2._max_bid_for(dentro) == 1.0
