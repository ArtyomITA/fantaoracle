"""Contabilita' e proprieta' dei giocatori nel completamento del Livello 3.

Questi test fissano le regole che l'asta impone e che il completamento
surrogato deve rispettare per restare una rappresentazione onesta di essa:

1. **un acquisto concluso e' immutabile.** In asta non esiste la rivendita:
   chi e' stato battuto resta della squadra che lo ha preso, per tutti i rami
   della simulazione e per tutte le squadre, la nostra e quelle avversarie.
2. **nessun credito nasce dal nulla.** Il budget residuo di una squadra piu'
   quanto ha speso nella simulazione deve dare esattamente il budget da cui
   e' partita: il ledger d'asta, non un ricalcolo a prezzi di listino.
3. **un giocatore sta in una squadra sola**, e nessuno sparisce dal mondo:
   chi era posseduto resta posseduto, chi era sul mercato o e' comprato o e'
   ancora sul mercato.
4. **il bersaglio del prezzo di indifferenza non puo' uscire dalla nostra
   rosa nel ramo "compro"**: se esce, quel ramo non contiene piu' l'acquisto
   di cui si sta misurando il valore e la differenza misurata e' di un'altra
   decisione.
5. **il massimo legalmente offribile e' un vincolo**, distinto dal tetto
   economico: il primo dice che cosa si puo' offrire senza restare senza
   crediti per i posti ancora vuoti, il secondo fin dove conviene salire.

I casi minimi qui sotto sono quelli riprodotti dall'audit dell'8 settembre
2026 (`data/l3/audit2/livello3/RAPPORTO.md`, sezione 1 e `01_contabilita.py`).
Sul codice precedente alla correzione questi test falliscono; e' il motivo per
cui esistono.
"""
from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from fantabot.livello3 import indifferenza as I   # noqa: E402
from fantabot.livello3 import valutatore as V     # noqa: E402
from fantabot.models import Player                # noqa: E402


def _g(pid, ruolo="P"):
    return Player(str(pid), f"G{pid}", ruolo, "X")


# --------------------------------------------------------------------------
# 1. il caso minimo dell'incarico: la rivendita che in asta non esiste
# --------------------------------------------------------------------------

def test_giocatore_gia_posseduto_non_viene_rivenduto():
    """Caso 1 dell'audit, riprodotto alla lettera.

    Rosa gia' completa con il giocatore 1, 10 crediti residui, prezzo previsto
    del giocatore 1 pari a 90; il giocatore 2 costa 100 e vale di piu'. Il
    codice precedente rimborsava il giocatore 1 al suo prezzo *previsto* (90),
    faceva scendere il costo netto del 2 a 10 e lo scambio rientrava nei
    crediti residui: rosa `{'P': [2]}` e budget 0.

    In asta quello scambio non e' possibile: nessuno ricompra il giocatore 1.
    """
    regole = V.Regole(quote={"P": 1}, budget=100,
                      applica_bonus_porta_inviolata=False)
    pool = {1: _g(1), 2: _g(2)}
    prezzi = {1: 90.0, 2: 100.0}
    valori = {1: 100.0, 2: 200.0}

    rosa, budget, presi = I.completa_rosa(
        {"P": [1]}, 10.0, {2}, pool, prezzi, valori, regole)

    assert rosa["P"] == [1], (
        f"il giocatore 1 era gia' nostro e non poteva uscire: rosa {rosa}")
    assert budget == pytest.approx(10.0), (
        f"nessuno ha comprato niente, il budget non poteva cambiare: {budget}")
    assert presi == [], f"nessun acquisto era possibile: {presi}"


def test_la_rivendita_non_passa_neanche_da_completa_asta():
    """Lo stesso divieto, ma attraverso il completamento di tutta la lega.

    Qui il difetto si vede anche come sparizione: nel codice precedente il
    giocatore scartato tornava in un insieme `disponibili` *locale* che non
    usciva dalla funzione, quindi non tornava sul mercato e non finiva in
    nessuna rosa (caso 3 dell'audit: 35 giocatori su 120 spariti sullo stato
    d'asta vero)."""
    regole = V.Regole(quote={"P": 1}, budget=100,
                      applica_bonus_porta_inviolata=False)
    pool = {i: _g(i) for i in (1, 2, 3, 4)}
    prezzi = {1: 90.0, 2: 100.0, 3: 80.0, 4: 100.0}
    valori = {1: 100.0, 2: 200.0, 3: 50.0, 4: 300.0}
    stato = I.StatoAsta(
        nostra={"P": [1]}, nostro_budget=10.0,
        avversari={"AVV01": {"rosa": {"P": [3]}, "budget": 30.0}},
        disponibili={2, 4}, regole=regole)

    rose = I.completa_asta(stato, pool, prezzi, valori, replica=0, seme=1)

    assert rose["NOI"]["P"] == [1], f"nostro acquisto concluso perso: {rose}"
    assert rose["AVV01"]["P"] == [3], f"acquisto avversario perso: {rose}"
    assegnati = [pid for r in rose.values() for v in r.values() for pid in v]
    assert sorted(assegnati) == [1, 3], (
        f"le rose erano gia' piene: nessun altro acquisto era possibile, "
        f"trovati {sorted(assegnati)}")


# --------------------------------------------------------------------------
# 2. nessun credito creato dal nulla
# --------------------------------------------------------------------------

def test_il_budget_non_scende_mai_sotto_zero():
    """Caso 5 dell'audit: tre posti da riempire e zero crediti.

    Il ciclo di riempimento a 1 credito non guardava la capienza e chiudeva
    con un budget di -3,0. Una squadra non puo' spendere crediti che non ha:
    l'esito corretto e' una rosa incompleta *dichiarata*, non un budget
    negativo."""
    regole = V.Regole(quote={"P": 3}, budget=100,
                      applica_bonus_porta_inviolata=False)
    pool = {i: _g(i) for i in (1, 2, 3)}
    prezzi = {i: 1.0 for i in (1, 2, 3)}
    valori = {i: 10.0 for i in (1, 2, 3)}

    rosa, budget, presi = I.completa_rosa(
        {"P": []}, 0.0, {1, 2, 3}, pool, prezzi, valori, regole, migliora=False)

    assert budget >= 0.0, f"budget negativo: {budget} (spesa creata dal nulla)"
    assert len(presi) == 0, (
        f"con zero crediti non si compra nessuno, presi {presi}")
    assert len(rosa["P"]) == 0


def test_somma_di_speso_e_residuo_invariante_su_una_rosa():
    """Il ledger chiude: budget residuo + speso = budget di partenza.

    La verifica ha bisogno del prezzo *addebitato* per ciascun acquisto della
    simulazione, che il modulo deve esporre: senza, la contabilita' non e'
    controllabile da fuori e i difetti (a) e (b) dell'audit restano invisibili.
    """
    regole = V.Regole(quote={"P": 1, "D": 2}, budget=100,
                      applica_bonus_porta_inviolata=False)
    pool = {1: _g(1, "P"), 2: _g(2, "P")}
    for i in (3, 4, 5, 6):
        pool[i] = _g(i, "D")
    prezzi = {1: 40.0, 2: 30.0, 3: 20.0, 4: 15.0, 5: 9.0, 6: 3.0}
    valori = {1: 90.0, 2: 60.0, 3: 70.0, 4: 50.0, 5: 40.0, 6: 10.0}

    esito = I.completa_rosa_surrogata(
        {"P": [], "D": []}, 60.0, set(pool), pool, prezzi, valori, regole)

    speso = sum(esito.pagati.values())
    assert esito.budget == pytest.approx(60.0 - speso), (
        f"residuo {esito.budget}, speso {speso}, partenza 60.0")
    assert esito.budget >= 0.0
    assert set(esito.pagati) == set(esito.presi)
    for pid, pagato in esito.pagati.items():
        assert pagato >= 1.0, f"{pid} pagato {pagato}: sotto il minimo d'asta"
        assert pagato <= max(1.0, prezzi[pid]) + 1e-9, (
            f"{pid} pagato {pagato} sopra il prezzo previsto {prezzi[pid]}")


def test_somma_di_speso_e_residuo_invariante_su_tutta_la_lega():
    """La stessa invariante, per ogni squadra, lungo l'intero completamento.

    E' la forma che l'audit chiedeva e che il codice precedente violava in
    entrambe le direzioni: rimborsi al prezzo previsto creavano crediti (+90
    nel caso minimo) e il riempimento a 1 credito ne distruggeva."""
    pool, prezzi, valori, _ = _mondo(seme=21)
    stato = _stato_parziale(pool, prezzi)
    partenza = dict({"NOI": stato.nostro_budget},
                    **{k: v["budget"] for k, v in stato.avversari.items()})

    esito = I.completa_asta_surrogata(stato, pool, prezzi, valori,
                                      replica=0, seme=3)

    for nome, budget0 in partenza.items():
        speso = sum(esito.pagati[nome].values())
        assert esito.budget[nome] == pytest.approx(budget0 - speso), (
            f"{nome}: residuo {esito.budget[nome]}, speso {speso}, "
            f"partenza {budget0}")
        assert esito.budget[nome] >= 0.0, f"{nome} in rosso"
    problemi = I.verifica_contabilita(esito, stato, prezzi)
    assert problemi == [], problemi


# --------------------------------------------------------------------------
# 3. un giocatore, una squadra; e nessuno sparisce
# --------------------------------------------------------------------------

QUOTE = {"P": 1, "D": 4, "C": 4, "A": 2}


@dataclass
class CuboFinto:
    giocatori: list
    fantavoto: np.ndarray
    voto: np.ndarray
    gioca: np.ndarray


def _mondo(seme=0, n_scenari=12, n_giornate=4, n_squadre=4):
    """Pool appena sufficiente per `n_squadre` rose complete, piu' riserve."""
    rng = np.random.default_rng(seme)
    pool, prezzi, valori = {}, {}, {}
    n = 1
    for ruolo, quanti in QUOTE.items():
        for _ in range(quanti * n_squadre + 2):
            pid = n
            n += 1
            pool[pid] = Player(str(pid), f"G{pid}", ruolo, f"T{pid % 4}")
            valori[pid] = float(rng.uniform(20, 100))
            prezzi[pid] = float(max(1, round(valori[pid] / 5)))
    tutti = sorted(pool)
    ix = {p: i for i, p in enumerate(tutti)}
    F = np.zeros((n_scenari, n_giornate, len(tutti)), dtype=np.float32)
    for pid in tutti:
        base = 4.5 + 3.0 * (valori[pid] - 20) / 80.0
        for s in range(n_scenari):
            F[s, :, ix[pid]] = base + rng.normal(0, 0.6)
    return pool, prezzi, valori, CuboFinto(tutti, F, F.copy(),
                                           np.ones(F.shape, dtype=bool))


def _stato_parziale(pool, prezzi, n_avversari=3, budget=120):
    """Stato a meta' asta: ogni squadra ha gia' concluso qualche acquisto.

    Gli acquisti conclusi sono scelti fra i piu' cari del listino e i budget
    residui sono stretti: e' la configurazione in cui il vecchio
    `_spendi_il_resto` aveva convenienza a "rivenderli"."""
    regole = V.Regole(quote=QUOTE, budget=budget, usa_mod_difesa=False,
                      applica_bonus_porta_inviolata=False)
    per_ruolo = {r: sorted([p for p in pool if pool[p].role == r],
                           key=lambda p: -prezzi[p]) for r in QUOTE}
    nostra = {"P": [per_ruolo["P"][0]], "D": [per_ruolo["D"][0]],
              "C": [], "A": []}
    avversari = {}
    for i in range(n_avversari):
        avversari[f"AVV{i + 1:02d}"] = {
            "rosa": {"P": [per_ruolo["P"][i + 1]],
                     "D": [per_ruolo["D"][i + 1]], "C": [], "A": []},
            "budget": float(budget) - 30.0}
    presi = {p for r in nostra.values() for p in r}
    presi |= {p for v in avversari.values() for r in v["rosa"].values()
              for p in r}
    return I.StatoAsta(nostra=nostra, nostro_budget=float(budget) - 40.0,
                       avversari=avversari,
                       disponibili=set(pool) - presi, regole=regole)


def test_nessun_giocatore_in_due_squadre_e_nessuno_sparisce():
    """Conservazione: chi era posseduto resta posseduto dalla stessa squadra,
    chi era sul mercato o viene comprato da una sola squadra o resta sul
    mercato. Nessun giocatore puo' uscire dalla contabilita'."""
    pool, prezzi, valori, _ = _mondo(seme=22)
    stato = _stato_parziale(pool, prezzi)
    conclusi = {"NOI": {p for r in stato.nostra.values() for p in r}}
    for nome, v in stato.avversari.items():
        conclusi[nome] = {p for r in v["rosa"].values() for p in r}

    esito = I.completa_asta_surrogata(stato, pool, prezzi, valori,
                                      replica=1, seme=5)

    proprietario = {}
    for nome, rosa in esito.rose.items():
        for ruolo, ids in rosa.items():
            assert len(ids) <= QUOTE[ruolo], (nome, ruolo, ids)
            for pid in ids:
                assert pid not in proprietario, (
                    f"{pid} in {proprietario.get(pid)} e in {nome}")
                proprietario[pid] = nome
                assert pool[pid].role == ruolo
    for nome, ids in conclusi.items():
        mancanti = ids - {p for r in esito.rose[nome].values() for p in r}
        assert not mancanti, f"{nome} ha perso acquisti conclusi: {mancanti}"
    inizio = set(stato.disponibili) | {p for s in conclusi.values() for p in s}
    fine = set(proprietario) | set(esito.disponibili)
    assert inizio == fine, (
        f"spariti {sorted(inizio - fine)}, comparsi {sorted(fine - inizio)}")


def test_uno_stato_con_doppia_proprieta_viene_rifiutato():
    """Caso 8 dell'audit: `StatoAsta.verifica()` rilevava la doppia proprieta'
    ma nessuno la chiamava, e il completamento girava lo stesso."""
    regole = V.Regole(quote={"P": 1}, budget=100,
                      applica_bonus_porta_inviolata=False)
    pool = {1: _g(1), 2: _g(2)}
    stato = I.StatoAsta(
        nostra={"P": [1]}, nostro_budget=10.0,
        avversari={"AVV01": {"rosa": {"P": [1]}, "budget": 100.0}},
        disponibili={2}, regole=regole)
    assert stato.verifica(), "la fixture doveva essere incoerente"
    with pytest.raises(ValueError, match="stato d'asta incoerente"):
        I.completa_asta(stato, pool, {1: 5.0, 2: 5.0}, {1: 10.0, 2: 20.0},
                        replica=0, seme=1)


# --------------------------------------------------------------------------
# 4. il bersaglio del prezzo di indifferenza resta nostro nel ramo "compro"
# --------------------------------------------------------------------------

def test_il_bersaglio_comprato_non_esce_dalla_nostra_rosa():
    """Caso 4 dell'audit, ricostruito come lo costruisce `delta_a_prezzo`:
    compriamo il giocatore 1 a 30 crediti e completiamo. Se il completamento
    lo scarta, il ramo "compro" misura una decisione diversa da quella
    dichiarata."""
    regole = V.Regole(quote={"P": 1}, budget=100,
                      applica_bonus_porta_inviolata=False)
    pool = {1: _g(1), 2: _g(2)}
    prezzi = {1: 30.0, 2: 100.0}
    valori = {1: 100.0, 2: 200.0}
    s1 = I.StatoAsta(nostra={"P": [1]}, nostro_budget=70.0, avversari={},
                     disponibili={2}, regole=regole)

    rose = I.completa_asta(s1, pool, prezzi, valori, replica=0, seme=1)

    assert 1 in rose["NOI"]["P"], (
        f"il bersaglio e' uscito dal ramo 'compro': {rose['NOI']}")


def test_il_bersaglio_resta_nostro_lungo_tutte_le_repliche():
    """Lo stesso vincolo attraverso `delta_a_prezzo`, che e' il punto in cui
    il difetto avrebbe effetto sulla misura."""
    pool, prezzi, valori, cubo = _mondo(seme=23, n_scenari=10)
    stato = _stato_parziale(pool, prezzi)
    ruolo = "A"
    g = max((p for p in stato.disponibili if pool[p].role == ruolo),
            key=lambda p: valori[p])
    cache = I.Cache(cubo, stato.regole)
    cal = V.calendario_berger(4, 4, seme=0)

    c = I.delta_a_prezzo(g, 12, stato, pool, prezzi, valori, cache, cal,
                         list(range(10)), 3, 4)

    assert c.bersaglio_sempre_nostro, (
        "il bersaglio e' uscito dalla nostra rosa in almeno una replica")
    assert g not in c.alternative


# --------------------------------------------------------------------------
# 5. gli acquisti degli avversari sono immutabili quanto i nostri
# --------------------------------------------------------------------------

def test_gli_acquisti_degli_avversari_sono_immutabili():
    """Sullo stato d'asta vero l'audit ha misurato 26,3 crediti di rimborso
    per avversario e 3,84 giocatori persi a testa per completamento: piu' che
    per noi (6,1 e 0,60). Il vincolo e' lo stesso per tutti."""
    pool, prezzi, valori, _ = _mondo(seme=24)
    stato = _stato_parziale(pool, prezzi)
    prima = {nome: {r: list(v) for r, v in dati["rosa"].items()}
             for nome, dati in stato.avversari.items()}

    esito = I.completa_asta_surrogata(stato, pool, prezzi, valori,
                                      replica=2, seme=9)

    for nome, rosa0 in prima.items():
        for ruolo, ids in rosa0.items():
            dopo = esito.rose[nome][ruolo]
            assert ids == dopo[:len(ids)], (
                f"{nome}/{ruolo}: conclusi {ids}, dopo il completamento {dopo}")
    # e lo stato in ingresso non e' stato mutato dalla chiamata
    for nome, rosa0 in prima.items():
        assert stato.avversari[nome]["rosa"] == rosa0


# --------------------------------------------------------------------------
# 6. il massimo legalmente offribile resta vincolante e distinto dal tetto
# --------------------------------------------------------------------------

def test_il_massimo_legale_viene_dal_ledger_ed_e_vincolante():
    """Il massimo offribile lascia un credito per ogni altro posto vuoto e si
    calcola sul budget residuo del ledger, non su un ricalcolo a listino."""
    pool, prezzi, valori, _ = _mondo(seme=25)
    stato = _stato_parziale(pool, prezzi)
    vuoti = sum(stato.posti_liberi(stato.nostra).values())
    atteso = int(max(0, stato.nostro_budget - max(0, vuoti - 1)))
    assert stato.max_legale(stato.nostra, stato.nostro_budget) == atteso

    esito = I.completa_asta_surrogata(stato, pool, prezzi, valori,
                                      replica=0, seme=2)
    for nome, pagati in esito.pagati.items():
        assert all(p >= 1.0 for p in pagati.values())
        assert esito.budget[nome] >= 0.0, nome


def test_nessun_acquisto_supera_il_massimo_offribile_nel_momento_in_cui_avviene():
    """Il vincolo va rispettato acquisto per acquisto, non solo alla fine: con
    due posti ancora vuoti e 10 crediti, il massimo offribile e' 9."""
    regole = V.Regole(quote={"P": 2}, budget=100,
                      applica_bonus_porta_inviolata=False)
    pool = {1: _g(1), 2: _g(2)}
    prezzi = {1: 10.0, 2: 1.0}
    valori = {1: 500.0, 2: 1.0}

    esito = I.completa_rosa_surrogata({"P": []}, 10.0, {1, 2}, pool, prezzi,
                                      valori, regole, migliora=False)

    assert esito.budget >= 0.0
    assert esito.pagati.get(1) != 10.0, (
        "10 crediti su 2 posti: il massimo offribile sul primo era 9")


def test_il_tetto_economico_resta_distinto_dal_massimo_legale():
    pool, prezzi, valori, cubo = _mondo(seme=26, n_scenari=10)
    stato = _stato_parziale(pool, prezzi)
    g = max((p for p in stato.disponibili if pool[p].role == "A"),
            key=lambda p: valori[p])
    cal = V.calendario_berger(4, 4, seme=0)

    out = I.curva(g, stato, pool, prezzi, valori, cubo, cal, list(range(10)),
                  prezzi_da_provare=[5, 15], repliche=2, seme=1)

    assert out["massimo_legale"] == stato.max_legale(stato.nostra,
                                                     stato.nostro_budget)
    assert out["tetto_economico"] <= out["massimo_legale"]
    assert out["massimo_legale"] != out["tetto_economico"] or \
        out["stato"] == "inconcludente"


# --------------------------------------------------------------------------
# 7. il completamento e' dichiarato per quello che e'
# --------------------------------------------------------------------------

def test_il_risultato_dichiara_che_il_completamento_e_un_surrogato():
    """L'audit ha misurato che il completamento non e' un'asta competitiva ma
    un'assegnazione per priorita', una rosa intera alla volta (sezione 2 del
    rapporto). Chi legge il risultato deve saperlo dal risultato stesso."""
    pool, prezzi, valori, cubo = _mondo(seme=27, n_scenari=10)
    stato = _stato_parziale(pool, prezzi)
    g = max((p for p in stato.disponibili if pool[p].role == "A"),
            key=lambda p: valori[p])
    cal = V.calendario_berger(4, 4, seme=0)

    out = I.curva(g, stato, pool, prezzi, valori, cubo, cal, list(range(10)),
                  prezzi_da_provare=[5], repliche=2, seme=1)

    comp = out["completamento"]
    assert "surrogato" in comp["nome"].lower()
    assert comp["tipo"] == "assegnazione_per_priorita"
    assert comp["asta_competitiva"] is False
    # gli esiti che prima erano nascosti sono ora numeri nel risultato
    assert "riempitivi_a_un_credito" in comp
    assert "posti_insoluti" in comp
    assert "rose_incomplete" in comp
    # il comportamento degli avversari e' dichiarato
    assert comp["avversari"]["criteri"], comp["avversari"]
    assert "ramo_passo" in comp["avversari"]
    # e lo scarto misurato dal motore vero e' riportato con la sua fonte
    assert comp["scarto_dal_motore"]["fonte"]


def test_gli_esiti_insoluti_sono_restituiti_non_sollevati():
    """Mercato insufficiente (caso 10 dell'audit): prima l'eccezione risaliva
    fino a `scripts/l3_tetti.py` e interrompeva l'intero giro dei tetti."""
    regole = V.Regole(quote={"P": 2}, budget=100,
                      applica_bonus_porta_inviolata=False)
    pool = {1: _g(1)}

    esito = I.completa_rosa_surrogata({"P": []}, 100.0, {1}, pool,
                                      {1: 1.0}, {1: 1.0}, regole)

    assert esito.insoluti == {"P": 1}, esito.insoluti
    assert esito.rosa["P"] == [1]
    assert esito.budget >= 0.0


def test_i_riempitivi_a_un_credito_sono_contati():
    """Caso 7 dell'audit: due giocatori quotati 300 finivano in rosa a 1
    credito. Il riempitivo resta (senza, la rosa non si chiude) ma smette di
    essere invisibile: e' contato e dichiarato."""
    regole = V.Regole(quote={"P": 2}, budget=100,
                      applica_bonus_porta_inviolata=False)
    pool = {1: _g(1), 2: _g(2)}
    prezzi = {1: 300.0, 2: 300.0}
    valori = {1: 500.0, 2: 400.0}

    esito = I.completa_rosa_surrogata({"P": []}, 10.0, {1, 2}, pool, prezzi,
                                      valori, regole, migliora=False)

    assert len(esito.riempitivi_a_un_credito) == len(esito.presi)
    assert esito.budget == pytest.approx(10.0 - len(esito.presi))
    assert esito.budget >= 0.0


# --------------------------------------------------------------------------
# 8. chiave di validita' del tetto
# --------------------------------------------------------------------------

def test_la_curva_espone_una_chiave_di_validita():
    pool, prezzi, valori, cubo = _mondo(seme=28, n_scenari=10)
    stato = _stato_parziale(pool, prezzi)
    g = max((p for p in stato.disponibili if pool[p].role == "A"),
            key=lambda p: valori[p])
    cal = V.calendario_berger(4, 4, seme=0)

    out = I.curva(g, stato, pool, prezzi, valori, cubo, cal, list(range(10)),
                  prezzi_da_provare=[5], repliche=2, seme=1)

    k = out["chiave_validita"]
    assert isinstance(k["impronta"], str) and len(k["impronta"]) >= 12
    assert k["stato_decisionale"]["nostro_budget"] == stato.nostro_budget
    assert k["stato_decisionale"]["massimo_legale"] == out["massimo_legale"]
    assert k["cubo"]["impronta"]
    assert k["esperimento"]["scenari"] == list(range(10))
    assert k["esperimento"]["repliche"] == 2
    # ricalcolabile da chi la consuma, senza rifare la curva
    atteso = I.chiave_di_validita(stato, pool, prezzi, valori, cubo,
                                  list(range(10)), 2, 1, cal)
    assert atteso["impronta"] == k["impronta"]


def test_la_chiave_di_validita_cambia_quando_cambia_lo_stato():
    """Un tetto calcolato da uno stato d'asta non e' valido dopo che lo stato
    e' cambiato: budget, rosa e mercato residuo devono entrare nella chiave.
    L'audit ha misurato il costo del congelamento: per Malen il tetto passa da
    110 (`inconcludente`) allo stato iniziale a 220 (`verificato`) a meta'
    asta, un fattore 2 sullo stesso giocatore e lo stesso file."""
    pool, prezzi, valori, cubo = _mondo(seme=29, n_scenari=10)
    stato = _stato_parziale(pool, prezzi)
    cal = V.calendario_berger(4, 4, seme=0)
    base = I.chiave_di_validita(stato, pool, prezzi, valori, cubo,
                                list(range(10)), 4, 1, cal)

    assert I.chiave_di_validita(stato, pool, prezzi, valori, cubo,
                                list(range(10)), 4, 1, cal)["impronta"] == \
        base["impronta"], "chiave non deterministica"

    varianti = {}
    s = I.StatoAsta(nostra={r: list(v) for r, v in stato.nostra.items()},
                    nostro_budget=stato.nostro_budget - 1.0,
                    avversari=stato.avversari,
                    disponibili=set(stato.disponibili), regole=stato.regole)
    varianti["budget"] = s

    nostra2 = {r: list(v) for r, v in stato.nostra.items()}
    nuovo = sorted(p for p in stato.disponibili if pool[p].role == "C")[0]
    nostra2["C"] = nostra2["C"] + [nuovo]
    varianti["rosa"] = I.StatoAsta(
        nostra=nostra2, nostro_budget=stato.nostro_budget,
        avversari=stato.avversari,
        disponibili=set(stato.disponibili) - {nuovo}, regole=stato.regole)

    venduto = sorted(stato.disponibili)[0]
    avv2 = {k: {"rosa": {kk: list(vv) for kk, vv in v["rosa"].items()},
                "budget": v["budget"]} for k, v in stato.avversari.items()}
    primo = sorted(avv2)[0]
    avv2[primo]["rosa"][pool[venduto].role] = (
        list(avv2[primo]["rosa"][pool[venduto].role]) + [venduto])
    avv2[primo]["budget"] -= 5.0
    varianti["avversari_e_mercato"] = I.StatoAsta(
        nostra=stato.nostra, nostro_budget=stato.nostro_budget,
        avversari=avv2, disponibili=set(stato.disponibili) - {venduto},
        regole=stato.regole)

    for nome, sv in varianti.items():
        k = I.chiave_di_validita(sv, pool, prezzi, valori, cubo,
                                 list(range(10)), 4, 1, cal)
        assert k["impronta"] != base["impronta"], (
            f"la chiave non si accorge del cambiamento: {nome}")

    # e le costanti dell'esperimento contano quanto lo stato
    assert I.chiave_di_validita(stato, pool, prezzi, valori, cubo,
                                list(range(9)), 4, 1, cal)["impronta"] != \
        base["impronta"]
    assert I.chiave_di_validita(stato, pool, prezzi, valori, cubo,
                                list(range(10)), 8, 1, cal)["impronta"] != \
        base["impronta"]
    prezzi2 = dict(prezzi)
    prezzi2[sorted(prezzi2)[0]] += 1.0
    assert I.chiave_di_validita(stato, pool, prezzi2, valori, cubo,
                                list(range(10)), 4, 1, cal)["impronta"] != \
        base["impronta"]
    cubo2 = CuboFinto(cubo.giocatori, cubo.fantavoto.copy(), cubo.voto,
                      cubo.gioca)
    cubo2.fantavoto[0, 0, 0] += 1.0
    assert I.chiave_di_validita(stato, pool, prezzi, valori, cubo2,
                                list(range(10)), 4, 1, cal)["impronta"] != \
        base["impronta"]


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
