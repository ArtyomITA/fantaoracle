"""La formulazione esatta contro l'enumerazione completa.

Se il programma lineare misto-intero e l'enumerazione di tutte le rose legali
non danno lo stesso ottimo, uno dei due e' sbagliato. Su istanze piccole si
puo' sapere quale.
"""
from __future__ import annotations

import itertools
import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from fantabot.livello3 import esatto as E        # noqa: E402
from fantabot.livello3.valutatore import Regole  # noqa: E402

QUOTE = {"P": 1, "D": 4, "C": 4, "A": 2}


def _istanza(seme=0, n_scen=12, n_gior=4, extra=2):
    """Pool appena piu' grande di una rosa: le combinazioni si enumerano tutte."""
    rng = np.random.default_rng(seme)
    giocatori, ruoli, prezzi = [], {}, {}
    n = 1
    for r, q in QUOTE.items():
        for _ in range(q + extra):
            giocatori.append(n)
            ruoli[n] = r
            prezzi[n] = float(rng.integers(1, 25))
            n += 1
    punti = rng.uniform(2.0, 12.0, (n_scen, n_gior, len(giocatori)))
    gol_avv = rng.integers(0, 3, (n_scen, n_gior))
    # punti di lega dell'avversario: 3 per ogni giornata in cui segna almeno 1
    punti_avv = np.array([int(sum(3 if g > 0 else 1 for g in gol_avv[w]))
                          for w in range(n_scen)], dtype=float)
    # fantapunti totali dell'avversario, per lo spareggio: un numero plausibile
    # e non degenere, cosi' il pareggio di punti si decide davvero
    tot_avv = np.array([float(60.0 * n_gior + 5.0 * w % 37) for w in range(n_scen)])
    return giocatori, ruoli, prezzi, punti, gol_avv, punti_avv, tot_avv


def _enumera(giocatori, ruoli, prezzi, punti, regole, gol_avv, punti_avv, tot_avv):
    per_ruolo = {r: [p for p in giocatori if ruoli[p] == r] for r in regole.quote}
    migliore, arg = -1.0, None
    n = 0
    for combo in itertools.product(*[itertools.combinations(per_ruolo[r],
                                                            regole.quote[r])
                                     for r in regole.quote]):
        rosa = {r: list(c) for r, c in zip(regole.quote, combo)}
        costo = sum(max(1.0, prezzi[p]) for r in rosa for p in rosa[r])
        if costo > regole.budget:
            continue
        n += 1
        p1 = E.p_primo_diretta(rosa, punti, giocatori, regole, gol_avv,
                               punti_avv, tot_avv)
        if p1 > migliore:
            migliore, arg = p1, rosa
    return migliore, arg, n


def test_formulazione_esatta_coincide_con_enumerazione():
    giocatori, ruoli, prezzi, punti, gol_avv, punti_avv, tot_avv = _istanza(seme=3)
    regole = Regole(quote=QUOTE, budget=120, usa_mod_difesa=False)
    atteso, rosa_att, n = _enumera(giocatori, ruoli, prezzi, punti, regole,
                                   gol_avv, punti_avv, tot_avv)
    assert n > 20, f"istanza troppo piccola: solo {n} rose legali"
    out = E.risolvi(punti, giocatori, ruoli, prezzi, regole, gol_avv, punti_avv,
                    tot_avv, tempo_limite=120)
    assert out["ottimo"], out["stato"]
    assert out["p1"] == pytest.approx(atteso, abs=1e-9), (
        f"MILP {out['p1']:.4f} contro enumerazione {atteso:.4f} su {n} rose; "
        f"rosa MILP {out['rosa']}, rosa enumerata {rosa_att}")
    # la rosa trovata dal MILP deve valere davvero quel numero
    controllo = E.p_primo_diretta(out["rosa"], punti, giocatori, regole,
                                  gol_avv, punti_avv, tot_avv)
    assert controllo == pytest.approx(out["p1"], abs=1e-9)


def test_la_rosa_del_milp_e_legale():
    giocatori, ruoli, prezzi, punti, gol_avv, punti_avv, tot_avv = _istanza(seme=5)
    regole = Regole(quote=QUOTE, budget=100, usa_mod_difesa=False)
    out = E.risolvi(punti, giocatori, ruoli, prezzi, regole, gol_avv, punti_avv,
                    tot_avv, tempo_limite=120)
    assert out["ottimo"], out["stato"]
    for r, q in QUOTE.items():
        assert len(out["rosa"][r]) == q
        for pid in out["rosa"][r]:
            assert ruoli[pid] == r
    costo = sum(max(1.0, prezzi[pid]) for r in out["rosa"] for pid in out["rosa"][r])
    assert costo <= regole.budget + 1e-9


def test_giocatori_posseduti_restano_dentro():
    giocatori, ruoli, prezzi, punti, gol_avv, punti_avv, tot_avv = _istanza(seme=7)
    regole = Regole(quote=QUOTE, budget=140, usa_mod_difesa=False)
    obbligati = [giocatori[0], giocatori[3]]
    out = E.risolvi(punti, giocatori, ruoli, prezzi, regole, gol_avv, punti_avv,
                    tot_avv, tempo_limite=120, posseduti=obbligati)
    assert out["ottimo"], out["stato"]
    dentro = {pid for r in out["rosa"] for pid in out["rosa"][r]}
    for pid in obbligati:
        assert pid in dentro


def test_le_ipotesi_vengono_controllate_prima():
    """Se la rosa e' piu' grande della formazione, la formulazione non e'
    esatta e deve dirlo invece di risolvere lo stesso."""
    giocatori, ruoli, prezzi, punti, gol_avv, punti_avv, tot_avv = _istanza(seme=9)
    regole = Regole(quote={"P": 2, "D": 4, "C": 4, "A": 2}, budget=200,
                    usa_mod_difesa=False)
    out = E.risolvi(punti, giocatori, ruoli, prezzi, regole, gol_avv, punti_avv,
                    tot_avv)
    assert out["stato"] == "ipotesi_non_soddisfatte"
    assert any("non a 11" in p for p in out["problemi"])


def test_budget_impossibile_e_dichiarato():
    giocatori, ruoli, prezzi, punti, gol_avv, punti_avv, tot_avv = _istanza(seme=11)
    regole = Regole(quote=QUOTE, budget=5, usa_mod_difesa=False)
    out = E.risolvi(punti, giocatori, ruoli, prezzi, regole, gol_avv, punti_avv,
                    tot_avv, tempo_limite=30)
    assert not out["ottimo"] or out["stato"] != "Optimal"


def test_dimensione_del_problema_e_riportata():
    (giocatori, ruoli, prezzi, punti, gol_avv, punti_avv,
     tot_avv) = _istanza(seme=13, n_scen=6, n_gior=3)
    regole = Regole(quote=QUOTE, budget=120, usa_mod_difesa=False)
    out = E.risolvi(punti, giocatori, ruoli, prezzi, regole, gol_avv, punti_avv,
                    tot_avv, tempo_limite=60)
    assert out["n_binari"] == len(giocatori) + 2 * 6 * 3 + 5 * 6
    assert out["n_vincoli"] > 0
    assert out["tempo_limite_s"] == 60


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))


def test_soglia_per_zero_gol_e_un_errore_non_un_numero_enorme():
    """«almeno zero gol» e' sempre vero: non ha una soglia.

    Restituire qui un numero molto negativo lo faceva entrare nel big-M come
    valore assoluto, e con un avversario a zero gol il big-M superava il
    miliardo."""
    with pytest.raises(ValueError, match="sempre vera"):
        E._soglia_per_gol(0, 66, 6)
    assert E._soglia_per_gol(1, 66, 6) == 66
    assert E._soglia_per_gol(2, 66, 6) == 72


def test_lo_spareggio_sui_fantapunti_e_applicato():
    """Pari punti di lega, piu' fantapunti: si arriva primi lo stesso.

    Il commento del modulo lo prometteva e il codice non lo faceva; siccome
    programma lineare e calcolo diretto sbagliavano allo stesso modo, il
    confronto fra i due non se ne accorgeva."""
    giocatori = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11]
    ruoli = {}
    for pid, r in zip(giocatori, ["P"] + ["D"] * 4 + ["C"] * 4 + ["A"] * 2):
        ruoli[pid] = r
    # una sola giornata, un solo scenario: 11 x 6,0 = 66 punti -> 1 gol
    punti = np.full((1, 1, 11), 6.0)
    gol_avv = np.array([[1]])            # anche l'avversario fa 1 gol: pareggio
    punti_avv = np.array([1.0])          # 1 punto di lega a testa
    regole = Regole(quote={"P": 1, "D": 4, "C": 4, "A": 2}, budget=100,
                    usa_mod_difesa=False)
    rosa = {"P": [1], "D": [2, 3, 4, 5], "C": [6, 7, 8, 9], "A": [10, 11]}
    # con meno fantapunti dell'avversario non si arriva primi
    assert E.p_primo_diretta(rosa, punti, giocatori, regole, gol_avv, punti_avv,
                             np.array([100.0])) == 0.0
    # con piu' fantapunti si'
    assert E.p_primo_diretta(rosa, punti, giocatori, regole, gol_avv, punti_avv,
                             np.array([50.0])) == 1.0
