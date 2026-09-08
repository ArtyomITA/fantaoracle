"""Il valutatore del Livello 3, verificato su campionati calcolabili a mano.

Prima di fidarsi di una P(1 posto) stimata su duecento scenari, il valutatore
deve dare la risposta giusta su casi in cui la risposta si conosce.
"""
from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from fantabot.livello3 import valutatore as V   # noqa: E402


@dataclass
class CuboFinto:
    """Cubo minimo con la stessa interfaccia di `tabellino.generatore.Cubo`."""
    giocatori: list
    fantavoto: np.ndarray
    voto: np.ndarray
    gioca: np.ndarray


def _quote_11():
    return {"P": 1, "D": 4, "C": 4, "A": 2}


def _cubo(valori: dict, n_scenari: int, n_giornate: int, giocatori: list):
    """`valori[pid]` = fantavoto costante di quel giocatore in ogni giornata."""
    ix = {p: i for i, p in enumerate(giocatori)}
    F = np.zeros((n_scenari, n_giornate, len(giocatori)), dtype=np.float32)
    for p, v in valori.items():
        F[:, :, ix[p]] = v
    return CuboFinto(giocatori=list(giocatori), fantavoto=F, voto=F.copy(),
                     gioca=np.ones(F.shape, dtype=bool))


def _rosa(prefisso: str, base: int):
    """Undici giocatori con identificativi distinti, nei ruoli richiesti."""
    n = base
    r = {}
    for ruolo, quanti in _quote_11().items():
        r[ruolo] = list(range(n, n + quanti))
        n += quanti
    return r


def test_punteggio_giornata_calcolato_a_mano():
    """Undici giocatori, tutti a voto, nessuna panchina: il punteggio della
    giornata e' la somma esatta dei fantavoti."""
    rosa = _rosa("A", 100)
    ids = [p for r in rosa for p in rosa[r]]
    valori = {p: 6.0 for p in ids}
    valori[ids[0]] = 8.5                       # il portiere prende 8,5
    atteso = 10 * 6.0 + 8.5
    cubo = _cubo(valori, 1, 3, ids)
    regole = V.Regole(quote=_quote_11(), usa_mod_difesa=False,
                      applica_bonus_porta_inviolata=False)
    p = V.punteggi_rosa(rosa, cubo, {p: i for i, p in enumerate(ids)}, 0, regole)
    assert np.allclose(p, atteso), (p, atteso)


def test_gol_da_fasce_sui_confini():
    """66 punti = 1 gol; 71,5 = 1; 72 = 2. I confini sono quelli della lega."""
    from fantabot.season.lineup import goals_from_points
    assert goals_from_points(65.5) == 0
    assert goals_from_points(66.0) == 1
    assert goals_from_points(71.5) == 1
    assert goals_from_points(72.0) == 2
    assert goals_from_points(78.0) == 3


def test_campionato_a_due_squadre_calcolabile():
    """Due squadre, due giornate. Punteggi noti, gol noti, classifica nota."""
    ra = _rosa("A", 100)
    rb = _rosa("B", 200)
    ids = [p for r in ra for p in ra[r]] + [p for r in rb for p in rb[r]]
    # A: 11 x 6,5 = 71,5 punti -> 1 gol. B: 11 x 6,0 = 66,0 -> 1 gol. Pareggio.
    valori = {p: 6.5 for p in ids if p < 200}
    valori.update({p: 6.0 for p in ids if p >= 200})
    cubo = _cubo(valori, 1, 2, ids)
    regole = V.Regole(quote=_quote_11(), usa_mod_difesa=False,
                      applica_bonus_porta_inviolata=False)
    cal = [[(0, 1)], [(1, 0)]]
    e = V.valuta(cubo, {"A": ra, "B": rb}, regole, calendario=cal)
    assert np.allclose(e.punteggi[0, 0], 71.5)
    assert np.allclose(e.punteggi[0, 1], 66.0)
    assert (e.gol[0] == 1).all()
    # due pareggi: 2 punti a testa
    assert np.allclose(e.punti_lega[0], [2.0, 2.0])
    # fantapunti totali: A 143, B 132 -> A prima per lo spareggio
    assert list(e.posizione[0]) == [1, 2]
    assert np.allclose(e.vittoria[0], [1.0, 0.0])


def test_parita_totale_vittoria_condivisa():
    """Due squadre identiche su tutti i criteri: mezza vittoria a testa.

    Nessun ordine alfabetico e nessun indice decide chi vince."""
    ra = _rosa("A", 100)
    rb = _rosa("B", 200)
    ids = [p for r in ra for p in ra[r]] + [p for r in rb for p in rb[r]]
    valori = {p: 6.0 for p in ids}
    cubo = _cubo(valori, 1, 2, ids)
    regole = V.Regole(quote=_quote_11(), usa_mod_difesa=False,
                      applica_bonus_porta_inviolata=False)
    e = V.valuta(cubo, {"A": ra, "B": rb}, regole, calendario=[[(0, 1)], [(1, 0)]])
    assert list(e.posizione[0]) == [1, 1]
    assert np.allclose(e.vittoria[0], [0.5, 0.5])
    assert e.diagnostica["scenari_con_parita_al_primo"] == 1
    # con "nessuno" la vittoria non viene assegnata a nessuna
    regole2 = V.Regole(quote=_quote_11(), usa_mod_difesa=False,
                       applica_bonus_porta_inviolata=False,
                       parita_finale="nessuno")
    e2 = V.valuta(cubo, {"A": ra, "B": rb}, regole2,
                  calendario=[[(0, 1)], [(1, 0)]])
    assert np.allclose(e2.vittoria[0], [0.0, 0.0])


def test_invarianza_all_ordine_delle_squadre():
    """Rinominare o riordinare le squadre non cambia i punteggi."""
    rose = {nome: _rosa(nome, 100 + 100 * i)
            for i, nome in enumerate(["Zeta", "Alfa", "Mu", "Beta"])}
    ids = [p for r in rose.values() for k in r for p in r[k]]
    rng = np.random.default_rng(1)
    valori = {p: float(rng.choice([5.0, 6.0, 6.5, 7.0])) for p in ids}
    cubo = _cubo(valori, 2, 4, ids)
    regole = V.Regole(quote=_quote_11(), usa_mod_difesa=False,
                      applica_bonus_porta_inviolata=False)
    cal = V.calendario_berger(4, 4, seme=3)
    e1 = V.valuta(cubo, rose, regole, calendario=cal)
    # stesso insieme, ordine di inserimento diverso
    rose2 = {k: rose[k] for k in ["Mu", "Beta", "Zeta", "Alfa"]}
    e2 = V.valuta(cubo, rose2, regole, calendario=cal)
    assert e1.squadre == e2.squadre        # ordinate internamente
    assert np.allclose(e1.punteggi, e2.punteggi)
    assert np.allclose(e1.vittoria, e2.vittoria)


def test_punteggi_non_dipendono_da_quante_rose_si_valutano():
    """Il punteggio di una rosa e' lo stesso da sola o in mezzo ad altre.

    E' la condizione per confrontare candidate: se valutarne otto invece di due
    cambiasse i punteggi, la differenza misurata non sarebbe la loro."""
    rose = {nome: _rosa(nome, 100 + 100 * i)
            for i, nome in enumerate(["A", "B", "C", "D"])}
    ids = [p for r in rose.values() for k in r for p in r[k]]
    rng = np.random.default_rng(2)
    valori = {p: float(rng.uniform(4, 9)) for p in ids}
    cubo = _cubo(valori, 3, 5, ids)
    regole = V.Regole(quote=_quote_11(), usa_mod_difesa=False,
                      applica_bonus_porta_inviolata=False)
    ix = {p: i for i, p in enumerate(ids)}
    da_sola = V.punteggi_rosa(rose["A"], cubo, ix, 0, regole)
    e = V.valuta(cubo, rose, regole, calendario=V.calendario_berger(4, 5, 0))
    assert np.allclose(e.punteggi[0, e.squadre.index("A")], da_sola)


def test_esclusivita_dei_giocatori():
    """Lo stesso giocatore in due squadre della lega e' un errore, non un
    dettaglio: la proprieta' e' esclusiva."""
    ra = _rosa("A", 100)
    rb = _rosa("B", 200)
    rb["A"] = list(ra["A"])                 # due attaccanti condivisi
    ids = sorted({p for r in (ra, rb) for k in r for p in r[k]})
    cubo = _cubo({p: 6.0 for p in ids}, 1, 2, ids)
    regole = V.Regole(quote=_quote_11(), usa_mod_difesa=False,
                      applica_bonus_porta_inviolata=False)
    with pytest.raises(ValueError, match="due squadre"):
        V.valuta(cubo, {"A": ra, "B": rb}, regole,
                 calendario=[[(0, 1)], [(1, 0)]])


def test_rosa_incompleta_rifiutata():
    ra = _rosa("A", 100)
    rb = _rosa("B", 200)
    rb["D"] = rb["D"][:-1]
    ids = [p for r in (ra, rb) for k in r for p in r[k]]
    cubo = _cubo({p: 6.0 for p in ids}, 1, 2, ids)
    regole = V.Regole(quote=_quote_11(), usa_mod_difesa=False,
                      applica_bonus_porta_inviolata=False)
    with pytest.raises(ValueError, match="attesi"):
        V.valuta(cubo, {"A": ra, "B": rb}, regole,
                 calendario=[[(0, 1)], [(1, 0)]])


def test_nessuna_anticipazione_nella_formazione():
    """Permutare gli esiti FUTURI non cambia le decisioni gia' prese.

    Si costruiscono due cubi identici fino alla giornata k e diversi dopo: i
    punteggi delle giornate fino a k devono coincidere."""
    rosa = _rosa("A", 100)
    ids = [p for r in rosa for p in rosa[r]]
    # rosa piu' ampia, cosi' la scelta degli undici conta davvero
    rosa["D"] = rosa["D"] + [900, 901]
    rosa["C"] = rosa["C"] + [902, 903]
    ids = [p for r in rosa for p in rosa[r]]
    rng = np.random.default_rng(4)
    F1 = rng.uniform(3, 10, (1, 6, len(ids))).astype(np.float32)
    F2 = F1.copy()
    F2[:, 3:, :] = rng.uniform(3, 10, (1, 3, len(ids)))   # cambia solo il futuro
    ix = {p: i for i, p in enumerate(ids)}
    quote = {"P": 1, "D": 6, "C": 6, "A": 2}
    regole = V.Regole(quote=quote, usa_mod_difesa=False,
                      applica_bonus_porta_inviolata=False)
    a = V.punteggi_rosa(rosa, CuboFinto(ids, F1, F1.copy(),
                                        np.ones(F1.shape, bool)), ix, 0, regole)
    b = V.punteggi_rosa(rosa, CuboFinto(ids, F2, F2.copy(),
                                        np.ones(F2.shape, bool)), ix, 0, regole)
    assert np.allclose(a[:3], b[:3]), (a[:3], b[:3])
    assert not np.allclose(a[3:], b[3:])


def test_calendario_completo_e_bilanciato():
    """Ogni squadra gioca una volta per giornata, e in 18 giornate incontra
    ogni avversaria due volte, una per campo."""
    cal = V.calendario_berger(10, 18, seme=7)
    from collections import Counter
    for g, turno in enumerate(cal):
        coinvolte = [x for coppia in turno for x in coppia]
        assert len(turno) == 5
        assert sorted(coinvolte) == list(range(10)), g
    ordinati = Counter(tuple(c) for turno in cal for c in turno)
    assert all(v == 1 for v in ordinati.values()), "accoppiamento ripetuto"
    non_ordinati = Counter(tuple(sorted(c)) for turno in cal for c in turno)
    assert all(v == 2 for v in non_ordinati.values())


def test_differenza_appaiata_riconosce_il_nulla():
    """Confrontare una valutazione con se stessa da' differenza zero."""
    rose = {n: _rosa(n, 100 + 100 * i) for i, n in enumerate(["A", "B"])}
    ids = [p for r in rose.values() for k in r for p in r[k]]
    rng = np.random.default_rng(5)
    F = rng.uniform(4, 9, (30, 4, len(ids))).astype(np.float32)
    cubo = CuboFinto(ids, F, F.copy(), np.ones(F.shape, bool))
    regole = V.Regole(quote=_quote_11(), usa_mod_difesa=False,
                      applica_bonus_porta_inviolata=False)
    e = V.valuta(cubo, rose, regole, calendario=V.calendario_berger(2, 4, 0))
    d = V.differenza_appaiata(e, e, "A")
    assert d["differenza"] == 0.0
    assert not d["esclude_zero"]


def test_stato_iniziale_non_inventato():
    """Senza stato iniziale si parte da zero, e il risultato lo dichiara."""
    rose = {n: _rosa(n, 100 + 100 * i) for i, n in enumerate(["A", "B"])}
    ids = [p for r in rose.values() for k in r for p in r[k]]
    cubo = _cubo({p: 6.0 for p in ids}, 1, 2, ids)
    regole = V.Regole(quote=_quote_11(), usa_mod_difesa=False,
                      applica_bonus_porta_inviolata=False)
    e = V.valuta(cubo, rose, regole, calendario=[[(0, 1)], [(1, 0)]])
    assert e.diagnostica["stato_iniziale"] is False
    e2 = V.valuta(cubo, rose, regole, calendario=[[(0, 1)], [(1, 0)]],
                  stato_iniziale={"punti": {0: 9.0}})
    assert e2.punti_lega[0, 0] == e.punti_lega[0, 0] + 9.0
    assert e2.diagnostica["stato_iniziale"] is True


def test_calendario_dichiarato_e_segnalato():
    """Se il calendario della lega non viene fornito, il risultato dice che e'
    un banco dichiarato, non la lega reale."""
    rose = {n: _rosa(n, 100 + 100 * i) for i, n in enumerate(["A", "B"])}
    ids = [p for r in rose.values() for k in r for p in r[k]]
    cubo = _cubo({p: 6.0 for p in ids}, 1, 2, ids)
    regole = V.Regole(quote=_quote_11(), usa_mod_difesa=False,
                      applica_bonus_porta_inviolata=False)
    e = V.valuta(cubo, rose, regole, seme_calendario=11)
    assert e.diagnostica["calendario_dichiarato"] is True
    assert e.diagnostica["seme_calendario"] == 11


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
