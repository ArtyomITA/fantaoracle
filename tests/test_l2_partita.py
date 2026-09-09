"""Proprieta' che il modello di partita deve avere, non solo numeri che tornano.

Ogni test qui nasce da un difetto trovato in una versione precedente:

  test_recupero_sintetico          la parametrizzazione senza intercetta
                                   costringeva i gol in trasferta vicino a 1
  test_invarianza_rinomina         la penalizzazione sulle prime n-1 squadre
                                   rendeva il risultato dipendente dall'ordine
  test_dixon_coles_preserva_...    il Brier sulla porta inviolata era usato per
                                   giudicare la correzione di Dixon e Coles,
                                   che sulle marginali non ha alcun effetto
  test_gradiente_analitico         il gradiente scritto a mano deve coincidere
                                   con quello numerico, altrimenti la stima
                                   converge in un punto sbagliato senza dirlo
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from fantabot.tabellino.partita import (          # noqa: E402
    MAX_GOL, ModelloPartita, _neg_loglik_e_gradiente, campiona_risultati,
    matrice_risultato, pesi_decadimento, stima, tau,
)


def _campionato_sintetico(rng, n_squadre=20, giri=2, mu=0.35, casa=0.20,
                          att=None, dif=None):
    """Genera un campionato completo da parametri noti."""
    squadre = [f"S{i:02d}" for i in range(n_squadre)]
    if att is None:
        att = np.zeros(n_squadre)
    if dif is None:
        dif = np.zeros(n_squadre)
    ch, ct, gc, gt = [], [], [], []
    for _ in range(giri):
        for i in range(n_squadre):
            for j in range(n_squadre):
                if i == j:
                    continue
                lam = np.exp(mu + casa + att[i] - dif[j])
                m = np.exp(mu + att[j] - dif[i])
                ch.append(squadre[i])
                ct.append(squadre[j])
                gc.append(rng.poisson(lam))
                gt.append(rng.poisson(m))
    return squadre, np.array(ch), np.array(ct), np.array(gc), np.array(gt)


def test_recupero_sintetico_squadre_equivalenti():
    """Con squadre tutte uguali il modello deve ritrovare il livello dei gol.

    E' il controllo che smaschera la parametrizzazione senza intercetta: quella
    stimava circa 1,00 gol in trasferta contro 1,59 osservati.
    """
    rng = np.random.default_rng(11)
    # mu tale che i gol in trasferta siano circa 1,59: exp(mu) = 1.59
    mu_vero = float(np.log(1.59))
    squadre, ch, ct, gc, gt = _campionato_sintetico(rng, mu=mu_vero, casa=0.0)
    osservata = gt.mean()
    m = stima(ch, ct, gc, gt, squadre=squadre, usa_dc=False, lam_pen=2.0)
    stimata = m.diagnostica["gol_ospite_medi_stimati"]
    assert m.convergenza
    assert abs(osservata - 1.59) < 0.06, f"campione anomalo: {osservata}"
    assert abs(stimata - osservata) < 0.05, (
        f"livello dei gol non recuperato: osservati {osservata:.4f}, "
        f"stimati {stimata:.4f}")


def test_recupero_forze_note():
    """Attacco, difesa e vantaggio del campo devono essere recuperabili."""
    rng = np.random.default_rng(7)
    n = 20
    att = np.linspace(-0.35, 0.35, n)
    dif = np.linspace(0.30, -0.30, n)
    att -= att.mean()
    dif -= dif.mean()
    squadre, ch, ct, gc, gt = _campionato_sintetico(
        rng, n_squadre=n, giri=3, mu=0.30, casa=0.22, att=att, dif=dif)
    m = stima(ch, ct, gc, gt, squadre=squadre, usa_dc=False, lam_pen=0.5)
    assert m.convergenza
    assert abs(m.casa - 0.22) < 0.06
    assert np.corrcoef(m.att, att)[0, 1] > 0.9
    assert np.corrcoef(m.dif, dif)[0, 1] > 0.9
    # la penalizzazione contrae: la pendenza deve stare fra 0,6 e 1,1
    pend = float(np.polyfit(att, m.att, 1)[0])
    assert 0.6 < pend < 1.1, pend


def test_invarianza_rinomina():
    """Rinominare e riordinare le squadre non deve cambiare le stime.

    La penalizzazione che colpiva solo le prime n-1 squadre lasciava l'ultima
    di fatto libera: bastava riordinare l'elenco per ottenere numeri diversi.
    """
    rng = np.random.default_rng(3)
    n = 20
    att = rng.normal(0, 0.25, n)
    dif = rng.normal(0, 0.25, n)
    squadre, ch, ct, gc, gt = _campionato_sintetico(
        rng, n_squadre=n, giri=2, att=att - att.mean(), dif=dif - dif.mean())
    m1 = stima(ch, ct, gc, gt, squadre=squadre, usa_dc=True, lam_pen=2.0)
    # stessa partita, elenco squadre invertito
    m2 = stima(ch, ct, gc, gt, squadre=list(reversed(squadre)), usa_dc=True,
               lam_pen=2.0)
    ix1, ix2 = m1.indice(), m2.indice()
    a1 = np.array([m1.att[ix1[s]] for s in squadre])
    a2 = np.array([m2.att[ix2[s]] for s in squadre])
    d1 = np.array([m1.dif[ix1[s]] for s in squadre])
    d2 = np.array([m2.dif[ix2[s]] for s in squadre])
    assert np.max(np.abs(a1 - a2)) < 1e-3, np.max(np.abs(a1 - a2))
    assert np.max(np.abs(d1 - d2)) < 1e-3
    assert abs(m1.mu - m2.mu) < 1e-4
    assert abs(m1.casa - m2.casa) < 1e-4


def test_dixon_coles_preserva_marginali():
    """La correzione DC non cambia P(gol = 0) di nessuna delle due squadre.

    Conseguenza operativa: il Brier sulla porta inviolata da' lo STESSO numero
    con e senza correzione. Non e' una metrica adatta a giudicarla.
    """
    for lam, mu_, rho in [(1.6, 1.1, -0.08), (0.9, 2.1, 0.05), (1.2, 1.2, -0.15)]:
        P0 = matrice_risultato(lam, mu_, 0.0)
        P1 = matrice_risultato(lam, mu_, rho)
        assert abs(P0.sum() - 1) < 1e-9 and abs(P1.sum() - 1) < 1e-9
        # marginali identiche
        assert np.max(np.abs(P0.sum(1) - P1.sum(1))) < 1e-12
        assert np.max(np.abs(P0.sum(0) - P1.sum(0))) < 1e-12
        # ma la congiunta cambia davvero
        assert np.max(np.abs(P0 - P1)) > 1e-4
        # nessuna probabilita' negativa nell'intervallo ammissibile
        assert P1.min() >= 0


def test_le_marginali_sono_poisson_non_solo_uguali_fra_loro():
    """Il confronto fra `rho` e `rho = 0` non basta a provare l'invarianza.

    Difetto trovato dal ramo di ricerca: le due matrici condividono lo stesso
    trattamento della coda troncata, quindi un errore in quel trattamento e'
    invisibile a un confronto fra loro. La versione precedente riversava
    `1 - somma` sulla cella `(max_gol, max_gol)`, e cosi' la coda tagliata di
    una squadra gonfiava la marginale dell'altra: scarto relativo su
    `P(G >= 6)` di +1,2e-6 alle intensita' operative, ma +9,6% a
    `(6,00; 3,00)` e +23,3% a `(8,00; 4,00)`.

    Qui il confronto e' contro la Poisson troncata e rinormalizzata, che e' il
    bersaglio vero, e i casi estremi ci sono apposta.
    """
    from scipy.stats import poisson
    casi = [(1.6, 1.1, -0.08), (0.9, 2.1, 0.05), (1.2, 1.2, -0.15),
            (3.0, 1.2, -0.07), (6.0, 3.0, -0.05), (8.0, 4.0, -0.03)]
    for lam, mu_, rho in casi:
        P = matrice_risultato(lam, mu_, rho)
        k = np.arange(P.shape[0])
        att_x = poisson.pmf(k, lam)
        att_x = att_x / att_x.sum()
        att_y = poisson.pmf(k, mu_)
        att_y = att_y / att_y.sum()
        sx = float(np.max(np.abs(P.sum(1) - att_x)))
        sy = float(np.max(np.abs(P.sum(0) - att_y)))
        assert sx < 1e-12, (
            f"lam {lam}, mu {mu_}: la marginale di casa si scosta dalla "
            f"Poisson troncata di {sx:.2e}")
        assert sy < 1e-12, (
            f"lam {lam}, mu {mu_}: la marginale ospite si scosta di {sy:.2e}")


def test_la_coda_analitica_coincide_con_la_matrice():
    """`P(G >= k)` ha forma chiusa: la matrice deve darne lo stesso valore.

    Serve a poter calcolare la coda senza simulare, che e' quello che fa
    `scripts/l2_coda_storica.py`. Se questa identita' cade, quella misura
    misura un'altra cosa.

    Il bersaglio e' la Poisson **troncata al supporto della matrice e
    rinormalizzata**. Da quando il supporto e' adattivo (`TOL_SUPPORTO`), la
    Poisson troncata e quella intera coincidono entro la tolleranza dichiarata,
    quindi il limite qui sotto e' molto piu' stretto di prima: con `max_gol`
    fisso a dodici lo scarto relativo valeva 1,8e-4 a `lambda` 3,0 con soglia
    6 e 1,3e-3 con soglia 8, e non passerebbe.
    """
    from scipy.stats import poisson
    for lam, mu_, rho in [(1.4, 1.23, -0.0711), (2.2, 0.9, -0.0711),
                          (3.0, 1.2, -0.05), (6.0, 3.0, -0.05),
                          (16.3, 10.0, -0.02), (46.7, 38.5, -0.002)]:
        P = matrice_risultato(lam, mu_, rho)
        k = np.arange(P.shape[0])
        att = poisson.pmf(k, lam)
        att = att / att.sum()
        for soglia in (4, 6, 8):
            dalla_matrice = float(P.sum(1)[k >= soglia].sum())
            troncata = float(att[k >= soglia].sum())
            assert abs(dalla_matrice - troncata) < 1e-12, (
                f"lam {lam}, soglia {soglia}: matrice {dalla_matrice:.12f} "
                f"contro Poisson troncata {troncata:.12f}")
            # Il troncamento sposta la coda, e quanto dipende dal supporto.
            # Con il supporto adattivo lo scarto e' dell'ordine di
            # TOL_SUPPORTO / P(G >= soglia): il limite e' assoluto sulla
            # probabilita', non relativo, cosi' non si allenta sulle code rare.
            intera = float(poisson.sf(soglia - 1, lam))
            assert abs(troncata - intera) < 1e-11, (
                f"lam {lam}, soglia {soglia}: il troncamento a {P.shape[0] - 1} "
                f"gol sposta la coda di {abs(troncata - intera):.2e}")


def test_matrice_probabilita_valide():
    """Probabilita' non negative e somma a 1 anche in casi estremi.

    La seconda meta' estrae `rho` **fuori** dall'intervallo ammissibile, che e'
    il caso che `campiona_parametri` produce davvero: la matrice deve restare
    una distribuzione, non diventarlo dopo un `np.maximum(P, 0)` a valle.
    """
    rng = np.random.default_rng(5)
    for _ in range(200):
        lam = float(rng.uniform(0.2, 4.0))
        mu_ = float(rng.uniform(0.2, 4.0))
        alto = min(1.0, 1.0 / (lam * mu_))
        basso = -min(1.0 / lam, 1.0 / mu_)
        rho = float(rng.uniform(basso * 0.9, alto * 0.9))
        P = matrice_risultato(lam, mu_, rho)
        assert P.min() >= 0.0, (lam, mu_, rho, P.min())
        assert abs(P.sum() - 1) < 1e-12
    for _ in range(200):
        lam = float(rng.uniform(0.2, 40.0))
        mu_ = float(rng.uniform(0.2, 40.0))
        rho = float(rng.uniform(-2.0, 2.0))       # quasi sempre non ammissibile
        P = matrice_risultato(lam, mu_, rho)
        assert P.min() >= 0.0, (lam, mu_, rho, P.min())
        assert abs(P.sum() - 1) < 1e-12


def test_gradiente_analitico():
    """Il gradiente scritto a mano coincide con quello numerico."""
    rng = np.random.default_rng(2)
    n = 8
    h = rng.integers(0, n, 120)
    a = (h + 1 + rng.integers(0, n - 1, 120)) % n
    x = rng.poisson(1.5, 120).astype(float)
    y = rng.poisson(1.2, 120).astype(float)
    w = rng.uniform(0.5, 1.0, 120)
    pa = np.zeros(n)
    pd_ = np.zeros(n)
    th = rng.normal(0, 0.2, 2 * n + 3)
    args = (h, a, x, y, w, n, 1.5, True, pa, pd_)
    f0, g = _neg_loglik_e_gradiente(th, *args)
    eps = 1e-6
    for i in range(len(th)):
        p, m = th.copy(), th.copy()
        p[i] += eps
        m[i] -= eps
        num = (_neg_loglik_e_gradiente(p, *args)[0]
               - _neg_loglik_e_gradiente(m, *args)[0]) / (2 * eps)
        assert abs(num - g[i]) < 1e-4 * max(1.0, abs(num)), (i, num, g[i])


def test_pesi_decadimento_usano_giorni_reali():
    """Due partite alla stessa giornata ma a 40 giorni di distanza (recupero)
    devono avere pesi diversi."""
    date = np.array(["2025-08-24", "2025-10-03"], dtype="datetime64[D]")
    w = pesi_decadimento(date, "2026-01-01", xi=0.005)
    assert w[1] > w[0]
    assert abs(w[0] / w[1] - np.exp(-0.005 * 40)) < 1e-9


def test_campionamento_riproducibile_e_calibrato():
    """Con numeri casuali dati, il campionamento e' deterministico; e le medie
    dei gol estratti coincidono con le intensita'."""
    rng = np.random.default_rng(1)
    lam = np.array([1.5, 0.8, 2.2])
    mu_ = np.array([1.1, 1.7, 0.6])
    u = rng.random((20000, 3))
    a = campiona_risultati(lam, mu_, -0.06, rng, u=u)
    b = campiona_risultati(lam, mu_, -0.06, rng, u=u)
    assert np.array_equal(a, b)
    assert np.max(np.abs(a[:, :, 0].mean(0) - lam)) < 0.05
    assert np.max(np.abs(a[:, :, 1].mean(0) - mu_)) < 0.05


def test_incertezza_forze_non_degenere():
    """Le forze campionate devono variare, e restare centrate sulla stima."""
    rng = np.random.default_rng(4)
    squadre, ch, ct, gc, gt = _campionato_sintetico(rng, n_squadre=10, giri=2)
    m = stima(ch, ct, gc, gt, squadre=squadre, usa_dc=False, lam_pen=2.0,
              con_incertezza=True)
    copie = m.campiona_parametri(rng, n=200)
    A = np.array([c.att for c in copie])
    assert A.std(0).min() > 1e-3, "incertezza nulla sulle forze"
    assert np.max(np.abs(A.mean(0) - m.att)) < 3 * A.std(0).max()


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
