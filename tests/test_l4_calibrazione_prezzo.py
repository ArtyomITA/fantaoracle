"""Prove sulle funzioni pure di scripts/l4_calibrazione_prezzo.py.

Nessun modello, nessun file d'asta letto o scritto: solo aritmetica.
Esecuzione:
  set PYTEST_DISABLE_PLUGIN_AUTOLOAD=1
  python -m pytest tests/test_l4_calibrazione_prezzo.py -q -p no:cacheprovider
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from l4_calibrazione_prezzo import (  # noqa: E402
    ETICHETTE_FASCE,
    RUOLI,
    applica_delta,
    copertura,
    fascia_di,
    pinball,
    punteggi_conformal,
    shrink_delta,
    stima_delta_celle,
)


# ---------------------------------------------------------------- fasce
def test_fascia_bordi_esatti():
    """I bordi 3, 8, 15, 30, 60 appartengono alla fascia superiore."""
    assert list(fascia_di([0.0, 2.999, 3.0, 7.99, 8.0, 14.9, 15.0,
                           29.9, 30.0, 59.9, 60.0, 500.0])) == \
        [0, 0, 1, 1, 2, 2, 3, 3, 4, 4, 5, 5]


def test_fascia_numero_etichette():
    assert len(ETICHETTE_FASCE) == 6
    assert max(fascia_di([1e9])) < len(ETICHETTE_FASCE)


# ---------------------------------------------------------------- punteggi
def test_punteggi_dentro_e_fuori():
    """s < 0 dentro l'intervallo, s > 0 fuori, e vale il lato piu' violato."""
    s = punteggi_conformal(y=[5.0, 0.0, 20.0], q10=[1.0, 1.0, 1.0], q90=[10.0, 10.0, 10.0])
    assert s[0] == pytest.approx(-4.0)   # dentro: distanza dal bordo piu' vicino
    assert s[1] == pytest.approx(1.0)    # sotto q10 di 1
    assert s[2] == pytest.approx(10.0)   # sopra q90 di 10


def test_punteggio_zero_sul_bordo():
    assert punteggi_conformal([1.0], [1.0], [10.0])[0] == pytest.approx(0.0)


# ---------------------------------------------------------------- shrink
def test_shrink_cella_vuota_da_globale():
    assert shrink_delta(d_cella=99.0, n_cella=0, d_globale=2.0) == pytest.approx(2.0)


def test_shrink_n_uguale_a_n0_e_media_semplice():
    assert shrink_delta(1.0, 30, 3.0, n0=30) == pytest.approx(2.0)


def test_shrink_monotono_e_tende_alla_cella():
    """Piu' osservazioni nella cella, piu' il delta si avvicina a quello di cella."""
    vals = [shrink_delta(10.0, n, 0.0, n0=30) for n in (0, 10, 30, 300, 30000)]
    assert vals == sorted(vals)
    assert vals[0] == pytest.approx(0.0)
    assert vals[-1] == pytest.approx(10.0, abs=0.02)


def test_shrink_formula_esplicita():
    assert shrink_delta(4.0, 10, 1.0, n0=30) == pytest.approx((10 * 4.0 + 30 * 1.0) / 40)


# ---------------------------------------------------------------- copertura
def test_copertura_estremi_inclusi():
    assert copertura([1.0, 5.0, 10.0], [1.0] * 3, [10.0] * 3) == pytest.approx(1.0)


def test_copertura_frazione():
    y = [0.0, 2.0, 3.0, 99.0]
    assert copertura(y, [1.0] * 4, [10.0] * 4) == pytest.approx(0.5)


def test_copertura_vuota_e_nan():
    assert np.isnan(copertura([], [], []))


# ---------------------------------------------------------------- pinball
def test_pinball_zero_se_quantili_esatti():
    """Se q10 = q90 = y la perdita e' nulla."""
    y = np.array([1.0, 2.0, 3.0])
    assert pinball(y, y, y) == pytest.approx(0.0)


def test_pinball_positivo_e_pesi_asimmetrici():
    """Livello 0,1: sottostimare costa 0,1 per unita', sovrastimare 0,9."""
    sotto = pinball([1.0], [0.0], [1.0])   # q10 sotto di 1 -> 0,1*1
    sopra = pinball([1.0], [2.0], [1.0])   # q10 sopra di 1 -> 0,9*1
    assert sotto == pytest.approx(0.1)
    assert sopra == pytest.approx(0.9)


# ---------------------------------------------------------------- stima + applicazione
def _campione():
    rng = np.random.RandomState(0)
    n = 400
    ruolo = np.array(RUOLI)[rng.randint(0, 4, n)]
    q50 = rng.uniform(0.5, 80.0, n)
    fascia = fascia_di(q50)
    return ruolo, fascia, rng


def test_delta_globale_e_quantile_dei_punteggi():
    _r, _f, rng = _campione()
    s = rng.normal(0, 1, 500)
    ruolo = np.array(["P"] * 500)
    fascia = np.zeros(500, dtype=int)
    _delta, d_glob, _n = stima_delta_celle(ruolo, fascia, s)
    assert d_glob == pytest.approx(float(np.quantile(s, 0.80)))


def test_delta_copre_tutte_le_24_celle():
    ruolo, fascia, rng = _campione()
    s = rng.normal(0, 1, len(ruolo))
    delta, _g, enne = stima_delta_celle(ruolo, fascia, s)
    assert len(delta) == 24 == len(enne)
    assert set(delta) == {(r, f) for r in RUOLI for f in range(6)}


def test_delta_di_cella_vuota_uguale_al_globale():
    ruolo = np.array(["P"] * 50)
    fascia = np.zeros(50, dtype=int)
    s = np.linspace(-1, 1, 50)
    delta, d_glob, enne = stima_delta_celle(ruolo, fascia, s)
    assert enne[("A", 5)] == 0
    assert delta[("A", 5)] == pytest.approx(d_glob)


def test_applica_delta_allarga_e_non_scende_sotto_il_minimo():
    q10 = np.array([0.01, 0.10])
    q90 = np.array([0.05, 0.20])
    ruolo = np.array(["P", "D"])
    fascia = np.array([0, 1])
    delta = {("P", 0): 0.5, ("D", 1): 0.02}
    n10, n90 = applica_delta(q10, q90, ruolo, fascia, delta, d_globale=0.0)
    assert n10[0] == pytest.approx(0.001)          # clip sul minimo
    assert n90[0] == pytest.approx(0.55)
    assert n10[1] == pytest.approx(0.08)
    assert n90[1] == pytest.approx(0.22)


def test_applica_delta_negativo_stringe():
    n10, n90 = applica_delta([0.10], [0.30], ["C"], [2],
                             {("C", 2): -0.05}, d_globale=0.0)
    assert n10[0] == pytest.approx(0.15)
    assert n90[0] == pytest.approx(0.25)


def test_calibrazione_raggiunge_il_nominale_in_campione():
    """Coerenza interna: delta stimati e applicati sullo stesso insieme
    portano la copertura vicino al nominale 0,80 (non e' una validazione:
    e' la prova che lo stimatore fa quel che dice)."""
    rng = np.random.RandomState(7)
    n = 600
    ruolo = np.array(RUOLI)[rng.randint(0, 4, n)]
    centro = rng.uniform(0.0, 0.2, n)
    fascia = fascia_di(centro * 500)
    q10 = centro - 0.001     # intervallo volutamente troppo stretto
    q90 = centro + 0.001
    # errore continuo: senza continuita' il quantile dei punteggi e' degenere
    y = centro + rng.normal(0.0, 0.01, n)
    s = punteggi_conformal(y, q10, q90)
    delta, d_glob, _n = stima_delta_celle(ruolo, fascia, s)
    n10, n90 = applica_delta(q10, q90, ruolo, fascia, delta, d_glob)
    assert copertura(y, q10, q90) < 0.6
    assert 0.70 <= copertura(y, n10, n90) <= 0.90
