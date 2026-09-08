"""Un tetto di indifferenza si usa solo dopo aver verificato che vale ancora.

Difetto misurato dall'audit indipendente dell'8 settembre 2026
(`data/l3/audit2/livello3/RAPPORTO.md` §7): `BotL3._max_bid_for` restituiva
`float(self.tetti[pid])` senza nessun controllo. I tetti erano un dizionario
congelato, costruito da `scripts/l3_tetti.py` su **un solo** `StatoAsta` (rose
vuote, budget 500, tutto il pool disponibile) e passato tale e quale a ogni
replica. Sulla stessa asta, alla fotografia dei 120 lotti venduti, la curva di
Malen ricalcolata dava tetto economico 220 con stato `verificato` contro 110
con stato `inconcludente` dello stato iniziale: un fattore 2 sullo stesso file.
Il massimo legale nel frattempo era sceso da 476 a 371.

`indifferenza.curva()` salva la chiave di validita' del suo risultato
(`chiave_validita`), ma nessuno la controllava: salvarla non impedisce di usare
un tetto scaduto.

Che cosa provano questi test, uno per riga:

* budget diverso, tetto respinto;
* acquisto di un rivale diverso, tetto respinto (due varianti: l'acquisto
  completo, che sposta pool e ledger insieme, e la sola rosa del rivale, che
  isola `impronta_avversari`);
* impronta del cubo (o scenari, semi, regole) diversa, tetto respinto;
* stato identico, tetto riutilizzato;
* il tetto economico non supera mai il massimo legalmente offribile;
* stato `inconcludente`, completamento non ammesso, chiave assente o vista
  assente: tetto respinto e ripiego contato con la sua ragione.

**Come i record di prova sono costruiti, e perche' non e' circolare.** La
chiave attesa e' ricalcolata qui da `_chiave_stato_di_prova`, che e' una
seconda implementazione della normalizzazione, scritta a mano in questo file e
indipendente da quella del bot. Due test la incollano alle altre due:
`test_la_chiave_del_bot_coincide_con_quella_scritta_a_mano` la confronta con
`BotL3.chiave_stato_corrente`, e
`test_la_chiave_del_bot_coincide_con_quella_di_indifferenza` la confronta con
`indifferenza.chiave_di_validita`, cioe' con il produttore vero. Il secondo
salta se quel modulo non e' importabile o se la sua firma e' cambiata: e' una
dipendenza dichiarata, non un test da spegnere.

I test non chiamano `start_auction`: il MILP non c'entra con la validita' di un
tetto, e tenerlo fuori rende la prova veloce e insensibile al solutore.
"""
from __future__ import annotations

import hashlib
import json
import random
import sys
from pathlib import Path

import pytest

RADICE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RADICE / "src"))

from fantabot.bots.base import AuctionView              # noqa: E402
from fantabot.bots.bot_l3 import BBotCoerente, BotL3    # noqa: E402
from fantabot.models import Player, TeamState           # noqa: E402

QUOTE = {"P": 1, "D": 2, "C": 2, "A": 1}
BUDGET = 100
RUOLI = ("P", "D", "C", "A")
INDICI = range(4)


# ------------------------------------------------------------------- mondo
def _valore(k: int) -> float:
    return 100.0 - 10.0 * k


def _q50(k: int) -> float:
    return 4.0 + 3.0 * k


def _pool(esclusi=()) -> dict:
    pool = {}
    for ruolo in RUOLI:
        for k in INDICI:
            pid = f"{ruolo}{k}"
            if pid in esclusi:
                continue
            pool[pid] = Player(pid, pid, ruolo, f"sq{k}", ref_price=0.05,
                               exp_points=_valore(k))
    return pool


def _predizioni() -> dict:
    return {f"{r}{k}": {"value": _valore(k), "value_up": _valore(k) + 10.0,
                        "q50": _q50(k), "q90": _q50(k) * 1.8,
                        "q10": _q50(k) * 0.6, "pres": 30.0}
            for r in RUOLI for k in INDICI}


def _rivale(team_id: str, budget: int = BUDGET, roster=None) -> TeamState:
    return TeamState(team_id, "avversario", budget,
                     roster or {r: [] for r in RUOLI})


def _vista(pool=None, roster=None, budget=BUDGET, venduti=None,
           altri=None) -> AuctionView:
    me = TeamState("T0", "L3", budget, roster or {r: [] for r in RUOLI})
    return AuctionView(me=me, others=list(altri if altri is not None
                                          else [_rivale("T1"), _rivale("T2")]),
                       quotas=QUOTE, budget_total=BUDGET, current_role="A",
                       pool=_pool() if pool is None else pool,
                       sold=list(venduti or []))


# ------------------------------- la chiave, riscritta a mano per il confronto
def _sha(testo: str, n: int = 12) -> str:
    return hashlib.sha256(testo.encode("utf-8")).hexdigest()[:n]


def _chiave_stato_di_prova(view: AuctionView) -> dict:
    """Seconda implementazione della parte osservabile della chiave.

    Scritta a mano, con le stesse formule di `indifferenza.chiave_di_validita`
    ma senza importare niente dal bot: se il bot cambiasse la normalizzazione
    per far passare un test, questa resterebbe ferma e il confronto fallirebbe.
    """
    quote = view.quotas
    rosa = {r: sorted(str(pid) for pid, _ in view.me.roster.get(r, []))
            for r in quote}
    liberi = {r: quote[r] - len(view.me.roster.get(r, [])) for r in quote}
    vuoti = sum(liberi.values())
    avversari = {t.team_id: {
        "rosa": {r: sorted(str(pid) for pid, _ in t.roster.get(r, []))
                 for r in quote},
        "budget": round(float(t.budget), 6)} for t in view.others}
    return {
        "nostro_budget": float(view.me.budget),
        "nostra_rosa": rosa,
        "posti_liberi": liberi,
        "massimo_legale": int(max(0, view.me.budget - max(0, vuoti - 1))),
        "n_disponibili": len(view.pool),
        "impronta_disponibili": _sha("|".join(sorted(map(str, view.pool))), 12),
        "impronta_avversari": _sha(json.dumps(avversari, sort_keys=True), 12),
    }


CONTESTO = {
    "cubo": {"impronta": "cubo-2026-27-aaaa", "forma": [40, 35, 587]},
    "esperimento": {"scenari": [0, 1, 2], "n_scenari": 3, "repliche": 8,
                    "seme": 20260907, "giornate": None,
                    "impronta_calendario": "cal-abc123",
                    "completamento": "assegnazione_per_priorita"},
    "regole": {"quote": dict(QUOTE), "budget": BUDGET, "max_cambi": 3,
               "soglia_gol": 66, "passo_gol": 6, "usa_mod_difesa": True,
               "applica_bonus_porta_inviolata": True, "punti": [3, 1, 0],
               "spareggio": ["punti", "fantapunti_totali"],
               "parita_finale": "condivisa"},
}

COMPLETAMENTO = {"nome": "completamento surrogato per priorita'",
                 "tipo": "assegnazione_per_priorita",
                 "asta_competitiva": False}


def _record(view: AuctionView, tetto: float, stato: str = "verificato",
            contesto: dict | None = None, completamento: dict | None = None,
            chiave: dict | None = None, massimo_legale=None) -> dict:
    """Un risultato di `curva()` ridotto ai campi che il consumatore legge."""
    ctx = CONTESTO if contesto is None else contesto
    corrente = _chiave_stato_di_prova(view)
    piena = {"stato_decisionale": corrente, **{k: v for k, v in ctx.items()}}
    piena["impronta"] = _sha(json.dumps(piena, sort_keys=True, default=str), 16)
    return {
        "giocatore": "ignoto",
        "tetto_economico": tetto,
        "massimo_legale": (corrente["massimo_legale"] if massimo_legale is None
                           else massimo_legale),
        "stato": stato,
        "completamento": (COMPLETAMENTO if completamento is None
                          else completamento),
        "chiave_validita": piena if chiave is None else chiave,
    }


def _bot(piano=(), tetti=None, contesto=CONTESTO, usa_indifferenza=True):
    return BotL3(random.Random(0), _predizioni(),
                 piano={pid: {"titolare": False} for pid in piano},
                 tetti=tetti, usa_indifferenza=usa_indifferenza,
                 contesto_tetti=contesto)


def _tetto_di_b(pid: str) -> float:
    """Il ripiego atteso: il massimo di offerta di B+, senza nessun piano."""
    return BBotCoerente(random.Random(0), _predizioni())._max_bid_for(pid)


def _chiedi(bot: BotL3, view: AuctionView, pid: str) -> float:
    bot._vista = view
    return bot._max_bid_for(pid)


# =========================================================== stato identico
def test_stato_identico_il_tetto_viene_riutilizzato():
    """Il caso positivo: senza questo, respingere tutto passerebbe i test."""
    view = _vista()
    pid = "A0"
    bot = _bot(piano=(pid,), tetti={pid: _record(view, 33.0)})
    assert _chiedi(bot, view, pid) == 33.0
    assert bot.conta["offerte_con_tetto_indifferenza"] == 1
    assert bot.conta["offerte_con_tetto_di_b"] == 0
    assert bot.conta["tetti_respinti"] == 0
    assert bot.ripieghi_per_ragione == {}
    assert _tetto_di_b(pid) != 33.0, "il tetto coincide col ripiego: prova vuota"


# ================================================================== budget
def test_budget_cambiato_il_tetto_e_respinto():
    """Ogni credito speso cambia il costo-opportunita' di tutti gli altri."""
    prima = _vista(budget=100)
    dopo = _vista(budget=71)
    pid = "A0"
    bot = _bot(piano=(pid,), tetti={pid: _record(prima, 33.0)})
    assert _chiedi(bot, dopo, pid) == pytest.approx(_tetto_di_b(pid))
    assert bot.conta["offerte_con_tetto_indifferenza"] == 0
    assert bot.conta["offerte_con_tetto_di_b"] == 1
    assert bot.ripieghi_per_ragione == {"stato_cambiato": 1}
    assert bot.ultimo_ripiego["giocatore"] == pid
    assert bot.ultimo_ripiego["ragione"] == "stato_cambiato"


def test_la_nostra_rosa_cambiata_respinge_il_tetto():
    """Un nostro acquisto sposta budget, posti liberi e massimo legale."""
    prima = _vista()
    dopo = _vista(roster={"P": [("P1", 12)], "D": [], "C": [], "A": []},
                  budget=88, venduti=[("P1", "T0", 12)],
                  pool=_pool(esclusi=("P1",)))
    pid = "A0"
    bot = _bot(piano=(pid,), tetti={pid: _record(prima, 33.0)})
    assert _chiedi(bot, dopo, pid) == pytest.approx(_tetto_di_b(pid))
    assert bot.ripieghi_per_ragione == {"stato_cambiato": 1}


# ================================================================= rivali
def test_un_acquisto_di_un_rivale_respinge_il_tetto():
    """Il caso realistico: il giocatore esce dal pool e entra in una rosa."""
    prima = _vista()
    dopo = _vista(pool=_pool(esclusi=("D0",)),
                  venduti=[("D0", "T1", 9)],
                  altri=[_rivale("T1", budget=91,
                                 roster={"P": [], "D": [("D0", 9)],
                                         "C": [], "A": []}),
                         _rivale("T2")])
    pid = "A0"
    bot = _bot(piano=(pid,), tetti={pid: _record(prima, 33.0)})
    assert _chiedi(bot, dopo, pid) == pytest.approx(_tetto_di_b(pid))
    assert bot.ripieghi_per_ragione == {"stato_cambiato": 1}


def test_la_sola_rosa_di_un_rivale_basta_a_respingere_il_tetto():
    """Isola `impronta_avversari`: pool, ledger e nostro stato restano fermi.

    Serve a impedire che il confronto passi solo grazie a `impronta_disponibili`:
    le rose e i budget dei rivali entrano nel ramo PASSO del calcolo e nel
    completamento di tutte le squadre, quindi cambiarli cambia il tetto."""
    prima = _vista()
    dopo = _vista(altri=[_rivale("T1", budget=91,
                                 roster={"P": [], "D": [("Dx", 9)],
                                         "C": [], "A": []}),
                         _rivale("T2")])
    assert prima.pool.keys() == dopo.pool.keys()
    assert prima.me.budget == dopo.me.budget
    pid = "A0"
    bot = _bot(piano=(pid,), tetti={pid: _record(prima, 33.0)})
    assert _chiedi(bot, dopo, pid) == pytest.approx(_tetto_di_b(pid))
    assert bot.ripieghi_per_ragione == {"stato_cambiato": 1}


def test_un_giocatore_disponibile_in_meno_respinge_il_tetto():
    prima = _vista()
    dopo = _vista(pool=_pool(esclusi=("C3",)))
    pid = "A0"
    bot = _bot(piano=(pid,), tetti={pid: _record(prima, 33.0)})
    assert _chiedi(bot, dopo, pid) == pytest.approx(_tetto_di_b(pid))
    assert bot.ripieghi_per_ragione == {"stato_cambiato": 1}


# ======================================== modello, scenari, semi, regole
def test_impronta_del_cubo_diversa_il_tetto_e_respinto():
    """Un tetto calcolato su un altro cubo non parla di questo mondo."""
    view = _vista()
    pid = "A0"
    altro = {**CONTESTO, "cubo": {"impronta": "cubo-altro-bbbb",
                                  "forma": [40, 35, 587]}}
    bot = _bot(piano=(pid,), tetti={pid: _record(view, 33.0, contesto=altro)})
    assert _chiedi(bot, view, pid) == pytest.approx(_tetto_di_b(pid))
    assert bot.ripieghi_per_ragione == {"contesto_diverso": 1}


def test_scenari_o_seme_diversi_respingono_il_tetto():
    view = _vista()
    pid = "A0"
    for campo, valore in (("scenari", [0, 1, 2, 3]), ("n_scenari", 4),
                          ("repliche", 4), ("seme", 1),
                          ("completamento", "motore_asta")):
        altro = {**CONTESTO,
                 "esperimento": {**CONTESTO["esperimento"], campo: valore}}
        bot = _bot(piano=(pid,),
                   tetti={pid: _record(view, 33.0, contesto=altro)})
        assert _chiedi(bot, view, pid) == pytest.approx(_tetto_di_b(pid)), campo
        assert bot.ripieghi_per_ragione == {"contesto_diverso": 1}, campo


def test_regole_diverse_respingono_il_tetto():
    view = _vista()
    pid = "A0"
    altro = {**CONTESTO,
             "regole": {**CONTESTO["regole"], "usa_mod_difesa": False}}
    bot = _bot(piano=(pid,), tetti={pid: _record(view, 33.0, contesto=altro)})
    assert _chiedi(bot, view, pid) == pytest.approx(_tetto_di_b(pid))
    assert bot.ripieghi_per_ragione == {"contesto_diverso": 1}


def test_senza_contesto_dichiarato_nessun_tetto_e_valido():
    """Degrado in sicurezza: se il consumatore non sa su che mondo gira, le
    componenti non osservabili dall'asta (cubo, scenari, seme, regole) non sono
    verificabili e il tetto non entra."""
    view = _vista()
    pid = "A0"
    bot = _bot(piano=(pid,), tetti={pid: _record(view, 33.0)}, contesto=None)
    assert _chiedi(bot, view, pid) == pytest.approx(_tetto_di_b(pid))
    assert bot.ripieghi_per_ragione == {"senza_contesto": 1}


def test_contesto_incompleto_nessun_tetto_e_valido():
    view = _vista()
    pid = "A0"
    parziale = {"cubo": CONTESTO["cubo"]}
    bot = _bot(piano=(pid,), tetti={pid: _record(view, 33.0)},
               contesto=parziale)
    assert _chiedi(bot, view, pid) == pytest.approx(_tetto_di_b(pid))
    assert bot.ripieghi_per_ragione == {"contesto_incompleto": 1}


# ==================================================== massimo legale d'asta
def test_il_tetto_economico_non_supera_mai_il_massimo_legale():
    """Due quantita' distinte, e la legale vince sempre.

    Il record e' costruito apposta incoerente: tetto economico 500 su uno stato
    in cui il massimo offribile e' 95. `curva()` non dovrebbe produrne di
    simili (scarta i prezzi sopra il tetto legale), ma il consumatore non si
    fida del produttore."""
    view = _vista()
    pid = "A0"
    legale = view.me.budget - (sum(QUOTE.values()) - 1)
    assert legale == 95
    bot = _bot(piano=(pid,), tetti={pid: _record(view, 500.0)})
    assert _chiedi(bot, view, pid) == float(legale)
    assert bot.conta["offerte_con_tetto_indifferenza"] == 1
    assert bot.conta["tetto_limitato_dal_massimo_legale"] == 1


def test_il_massimo_legale_scende_con_la_rosa_e_il_tetto_lo_segue():
    """Stesso tetto, stato aggiornato e chiave rifatta: il cap segue lo stato.

    Con un portiere gia' comprato restano 5 posti: il massimo legale e'
    `budget - 4`."""
    view = _vista(roster={"P": [("P1", 12)], "D": [], "C": [], "A": []},
                  budget=40, venduti=[("P1", "T0", 12)],
                  pool=_pool(esclusi=("P1",)))
    pid = "A0"
    assert _chiave_stato_di_prova(view)["massimo_legale"] == 36
    bot = _bot(piano=(pid,), tetti={pid: _record(view, 500.0)})
    assert _chiedi(bot, view, pid) == 36.0
    assert bot.conta["tetto_limitato_dal_massimo_legale"] == 1


# ============================================ stato del confronto e ripieghi
def test_un_tetto_inconcludente_non_viene_usato_e_il_ripiego_e_contato():
    """Il file gia' salvato dichiara `{verificato: 0, approssimato: 0,
    inconcludente: 25}`: se questi entrassero, il braccio userebbe 25 numeri il
    cui intervallo di confidenza attraversa lo zero a ogni prezzo provato."""
    view = _vista()
    pid = "A0"
    bot = _bot(piano=(pid,),
               tetti={pid: _record(view, 33.0, stato="inconcludente")})
    assert _chiedi(bot, view, pid) == pytest.approx(_tetto_di_b(pid))
    assert bot.conta["offerte_con_tetto_indifferenza"] == 0
    assert bot.conta["offerte_con_tetto_di_b"] == 1
    assert bot.conta["tetti_respinti"] == 1
    assert bot.ripieghi_per_ragione == {"stato_non_ammesso": 1}
    assert bot.ultimo_ripiego["stato"] == "inconcludente"


def test_lo_stato_approssimato_e_ammesso():
    """`l3_confronto_asta.py` ammette `verificato` e `approssimato`: la
    verifica di validita' non cambia quella soglia di ammissione."""
    view = _vista()
    pid = "A0"
    bot = _bot(piano=(pid,),
               tetti={pid: _record(view, 33.0, stato="approssimato")})
    assert _chiedi(bot, view, pid) == 33.0


def test_un_completamento_non_ammesso_non_produce_un_tetto():
    view = _vista()
    pid = "A0"
    esterno = {"nome": "completatore esterno: mio", "tipo": "esterno",
               "asta_competitiva": None}
    bot = _bot(piano=(pid,),
               tetti={pid: _record(view, 33.0, completamento=esterno)})
    assert _chiedi(bot, view, pid) == pytest.approx(_tetto_di_b(pid))
    assert bot.ripieghi_per_ragione == {"completamento_non_ammesso": 1}


def test_un_completamento_non_dichiarato_non_produce_un_tetto():
    view = _vista()
    pid = "A0"
    rec = _record(view, 33.0)
    del rec["completamento"]
    bot = _bot(piano=(pid,), tetti={pid: rec})
    assert _chiedi(bot, view, pid) == pytest.approx(_tetto_di_b(pid))
    assert bot.ripieghi_per_ragione == {"completamento_non_ammesso": 1}


def test_un_tetto_senza_chiave_non_viene_usato():
    """La forma vecchia `player_id -> float` non porta nessuna chiave, quindi
    non e' verificabile: e' quella che `l3_confronto_asta.py` costruisce oggi."""
    view = _vista()
    pid = "A0"
    bot = _bot(piano=(pid,), tetti={pid: 999.0})
    assert _chiedi(bot, view, pid) == pytest.approx(_tetto_di_b(pid))
    assert _chiedi(bot, view, pid) != 999.0
    assert bot.ripieghi_per_ragione == {"senza_chiave": 2}


def test_una_chiave_non_interpretabile_non_viene_usata():
    view = _vista()
    pid = "A0"
    for chiave in ("una stringa", 7, [], {"stato_decisionale": "non un dict"}):
        bot = _bot(piano=(pid,),
                   tetti={pid: _record(view, 33.0, chiave=chiave)})
        assert _chiedi(bot, view, pid) == pytest.approx(_tetto_di_b(pid)), chiave
        assert bot.conta["tetti_respinti"] == 1, chiave


def test_un_tetto_non_numerico_non_viene_usato():
    view = _vista()
    pid = "A0"
    for valore in ("33", None, float("nan"), float("inf"), True):
        rec = _record(view, 33.0)
        rec["tetto_economico"] = valore
        bot = _bot(piano=(pid,), tetti={pid: rec})
        assert _chiedi(bot, view, pid) == pytest.approx(_tetto_di_b(pid)), valore
        assert bot.ripieghi_per_ragione == {"tetto_non_numerico": 1}, valore


def test_un_record_incoerente_col_proprio_massimo_legale_e_respinto():
    """Il record dichiara un massimo legale che non e' quello dello stato che
    la sua stessa chiave descrive: e' malformato, non scaduto."""
    view = _vista()
    pid = "A0"
    bot = _bot(piano=(pid,),
               tetti={pid: _record(view, 33.0, massimo_legale=476)})
    assert _chiedi(bot, view, pid) == pytest.approx(_tetto_di_b(pid))
    assert bot.ripieghi_per_ragione == {"record_incoerente": 1}


def test_senza_vista_dello_stato_nessun_tetto_e_valido():
    """Se il bot non ha ancora visto il tavolo non puo' verificare niente."""
    view = _vista()
    pid = "A0"
    bot = _bot(piano=(pid,), tetti={pid: _record(view, 33.0)})
    assert bot._vista is None
    assert bot._max_bid_for(pid) == pytest.approx(_tetto_di_b(pid))
    assert bot.ripieghi_per_ragione == {"senza_vista": 1}


def test_il_reparto_pieno_toglie_senso_al_tetto():
    """`delta_a_prezzo` solleva `ValueError` quando il ruolo e' pieno: il
    consumatore non puo' restituire un numero dove il produttore si ferma."""
    view = _vista(roster={"P": [("P1", 10)], "D": [], "C": [], "A": []},
                  budget=90, venduti=[("P1", "T0", 10)],
                  pool=_pool(esclusi=("P1",)))
    pid = "P0"
    bot = _bot(piano=(pid,), tetti={pid: _record(view, 33.0)})
    assert _chiedi(bot, view, pid) == pytest.approx(_tetto_di_b(pid))
    assert bot.ripieghi_per_ragione == {"reparto_pieno": 1}


def test_un_giocatore_gia_venduto_non_ha_piu_tetto():
    view = _vista(pool=_pool(esclusi=("A0",)), venduti=[("A0", "T1", 9)],
                  altri=[_rivale("T1", budget=91,
                                 roster={"P": [], "D": [], "C": [],
                                         "A": [("A0", 9)]}),
                         _rivale("T2")])
    pid = "A0"
    bot = _bot(piano=(pid,), tetti={pid: _record(view, 33.0)})
    assert _chiedi(bot, view, pid) == pytest.approx(_tetto_di_b(pid))
    assert bot.ripieghi_per_ragione == {"gia_venduto": 1}


# ================================================== confini gia' esistenti
def test_il_tetto_resta_riservato_ai_giocatori_del_piano():
    """Confine gia' provato in `test_bot_l3_piano.py`, ricontrollato qui con un
    record valido: se un tetto valido agisse fuori dal piano, il braccio di
    controllo `piano=None` non sarebbe piu' un controllo."""
    view = _vista()
    dentro, fuori = "A0", "D0"
    bot = _bot(piano=(dentro,), tetti={dentro: _record(view, 33.0),
                                       fuori: _record(view, 1.0)})
    assert _chiedi(bot, view, dentro) == 33.0
    assert _chiedi(bot, view, fuori) == pytest.approx(_tetto_di_b(fuori))
    assert bot.conta["offerte_con_tetto_indifferenza"] == 1
    assert bot.conta["offerte_con_tetto_di_b"] == 1
    assert bot.conta["tetti_respinti"] == 0, (
        "un giocatore fuori piano non e' un tetto respinto: non e' stato "
        "nemmeno chiesto")


def test_con_indifferenza_spenta_i_massimi_sono_quelli_di_b_piu():
    """Parita' del braccio di controllo: la verifica non deve spostare nulla
    quando il trattamento e' spento, nemmeno di un centesimo."""
    view = _vista()
    riferimento = BBotCoerente(random.Random(0), _predizioni())
    bot = _bot(piano=tuple(view.pool), usa_indifferenza=False,
               tetti={pid: _record(view, 1.0) for pid in view.pool})
    bot._vista = view
    for pid in sorted(view.pool):
        assert bot._max_bid_for(pid) == riferimento._max_bid_for(pid), pid
    assert bot.conta["offerte_con_tetto_indifferenza"] == 0
    assert bot.conta["tetti_respinti"] == 0
    assert bot.ripieghi_per_ragione == {}


def test_la_vista_arriva_dal_percorso_vero_del_motore():
    """`bid()` e' l'unico punto da cui `_max_bid_for` viene chiamato in asta:
    se la vista non arrivasse di li', in asta ogni tetto sarebbe respinto per
    `senza_vista` e la verifica non proverebbe niente sul mondo vero."""
    view = _vista()
    pid = "A0"
    bot = _bot(piano=(pid,), tetti={pid: _record(view, 33.0)})
    bot.targets = {pid}
    bot.starter_targets = set()
    bot._role_of = {p: pl.role for p, pl in view.pool.items()}
    bot._best_alt_value = {r: 0.0 for r in QUOTE}
    decisione = bot.bid(view, view.pool[pid], 3, "T1")
    assert bot._vista is view
    assert decisione.amount == 4, decisione
    assert bot.conta["offerte_con_tetto_indifferenza"] == 1


# ============================================== aderenza fra le tre chiavi
def test_la_chiave_del_bot_coincide_con_quella_scritta_a_mano():
    """Il bot e questo file devono normalizzare lo stato allo stesso modo."""
    viste = [
        _vista(),
        _vista(budget=1),
        _vista(roster={"P": [("P1", 12)], "D": [("D2", 3)], "C": [], "A": []},
               budget=85, pool=_pool(esclusi=("P1", "D2"))),
        _vista(altri=[_rivale("T1", budget=17,
                              roster={"P": [("P3", 5)], "D": [], "C": [],
                                      "A": []})]),
        _vista(altri=[]),
    ]
    bot = _bot()
    for i, view in enumerate(viste):
        assert bot.chiave_stato_corrente(view) == _chiave_stato_di_prova(view), i


def test_la_chiave_del_bot_coincide_con_quella_di_indifferenza():
    """Aderenza al produttore vero: `indifferenza.chiave_di_validita`.

    Salta se il modulo non e' importabile o se la sua firma e' cambiata — e'
    una dipendenza dichiarata fra due file di proprieta' diversa, non una
    verifica da spegnere. Se invece il modulo c'e' e la forma della chiave e'
    cambiata, questo test **fallisce**: e' il segnale che il consumatore va
    aggiornato."""
    ind = pytest.importorskip("fantabot.livello3.indifferenza")
    from fantabot.livello3.valutatore import Regole

    view = _vista(roster={"P": [("P1", 12)], "D": [("D2", 3)], "C": [],
                          "A": []},
                  budget=85, pool=_pool(esclusi=("P1", "D2")),
                  altri=[_rivale("T1", budget=17,
                                 roster={"P": [("P3", 5)], "D": [], "C": [],
                                         "A": []}),
                         _rivale("T2")])
    regole = Regole(quote=dict(QUOTE), budget=BUDGET)
    stato = ind.StatoAsta(
        nostra={r: [pid for pid, _ in view.me.roster[r]] for r in QUOTE},
        nostro_budget=float(view.me.budget),
        avversari={t.team_id: {
            "rosa": {r: [pid for pid, _ in t.roster[r]] for r in QUOTE},
            "budget": float(t.budget)} for t in view.others},
        disponibili=set(view.pool),
        regole=regole)

    class _CuboFinto:
        impronta = "cubo-2026-27-aaaa"
        fantavoto = None

    try:
        piena = ind.chiave_di_validita(stato, dict(view.pool), {}, {},
                                       _CuboFinto(), [0, 1, 2], 8, 20260907,
                                       None, None)
    except TypeError as e:                     # firma cambiata: dipendenza
        pytest.skip(f"chiave_di_validita ha un'altra firma: {e}")
    assert piena["stato_decisionale"] == _chiave_stato_di_prova(view), (
        "la forma della chiave prodotta da indifferenza.py non e' piu' quella "
        "che bot_l3.py sa verificare")
    bot = _bot()
    assert bot.chiave_stato_corrente(view) == piena["stato_decisionale"]


# =================================================================== report
def test_il_rapporto_espone_i_ripieghi_con_la_loro_ragione():
    """Il numero di ripieghi e' un risultato dell'esperimento: se il tetto per
    indifferenza vale solo in una frazione dei lotti, la differenza misurata e'
    quella di un sistema che per il resto si comporta come B."""
    view, dopo = _vista(), _vista(budget=71)
    pid = "A0"
    bot = _bot(piano=(pid,), tetti={pid: _record(view, 33.0)})
    _chiedi(bot, view, pid)
    _chiedi(bot, dopo, pid)
    r = bot.rapporto()
    assert r["offerte_con_tetto_indifferenza"] == 1
    assert r["offerte_con_tetto_di_b"] == 1
    assert r["tetti_respinti"] == 1
    assert r["ripieghi_per_ragione"] == {"stato_cambiato": 1}
    assert r["quota_offerte_con_tetto_indifferenza"] == 0.5
    assert r["ultimo_ripiego"]["ragione"] == "stato_cambiato"
    # il rapporto non deve condividere gli oggetti interni
    r["ripieghi_per_ragione"]["stato_cambiato"] = 99
    assert bot.ripieghi_per_ragione == {"stato_cambiato": 1}
