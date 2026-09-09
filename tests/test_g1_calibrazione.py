"""Proprieta' che l'esperimento G1 deve avere, non numeri che tornano per caso.

Ogni test qui fissa un punto in cui l'esperimento potrebbe mentire senza
accorgersene:

  test_gradiente_per_osservazione_somma_al_totale
      il gradiente per osservazione e' riscritto a mano a partire dalle
      formule di `_neg_loglik_e_gradiente`. Se la riscrittura fosse sbagliata,
      la matrice J sarebbe sbagliata e T2 sarebbe una covarianza inventata che
      nessuno distinguerebbe da quella giusta guardando i risultati.

  test_sandwich_con_pesi_unitari
      con pesi tutti pari a 1 la sandwich pesata deve ridursi a quella
      classica `H^-1 (somma_i g_i g_i^T) H^-1`. E' il caso limite in cui il
      valore atteso e' noto in letteratura.

  test_punteggio_logaritmico_caso_a_mano / test_rps_caso_a_mano
      su una congiunta 3 x 3 scritta a mano il punteggio logaritmico, il RPS,
      il Brier e il PIT hanno un valore calcolabile a penna. Fissarlo qui
      impedisce che una convenzione (RPS diviso o no per J-1, porta inviolata
      letta sulla marginale sbagliata) cambi in silenzio.

  test_t1_coincide_con_campiona_parametri
      T1 deve essere il comportamento attuale, non una sua imitazione: con le
      stesse normali standard le estrazioni devono coincidere esattamente.
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import numpy as np
import pytest

RADICE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RADICE / "src"))

from fantabot.tabellino.partita import (          # noqa: E402
    _neg_loglik_e_gradiente, pesi_decadimento, stima,
)


def _carica_script():
    """Carica `scripts/g1_calibrazione_gol.py` come modulo, senza eseguirlo."""
    percorso = RADICE / "scripts" / "g1_calibrazione_gol.py"
    spec = importlib.util.spec_from_file_location("g1_calibrazione_gol", percorso)
    modulo = importlib.util.module_from_spec(spec)
    sys.modules["g1_calibrazione_gol"] = modulo
    spec.loader.exec_module(modulo)
    return modulo


G1 = _carica_script()


# --------------------------------------------------------------------------
# dati finti riproducibili
# --------------------------------------------------------------------------

def _campionato_finto(n_squadre=6, n_partite=90, seme=7):
    """Calendario finto con forze note: serve solo a dare numeri plausibili."""
    rng = np.random.default_rng(seme)
    squadre = [f"S{i}" for i in range(n_squadre)]
    h = rng.integers(0, n_squadre, n_partite)
    a = (h + 1 + rng.integers(0, n_squadre - 1, n_partite)) % n_squadre
    att = rng.normal(0, 0.3, n_squadre)
    dif = rng.normal(0, 0.3, n_squadre)
    lam = np.exp(0.25 + 0.2 + att[h] - dif[a])
    mu = np.exp(0.25 + att[a] - dif[h])
    x = rng.poisson(lam).astype(float)
    y = rng.poisson(mu).astype(float)
    w = rng.uniform(0.2, 1.0, n_partite)
    return squadre, h, a, x, y, w


def _theta_finto(n, usa_dc, seme=11):
    rng = np.random.default_rng(seme)
    k = 2 * n + 2 + (1 if usa_dc else 0)
    th = rng.normal(0, 0.2, k)
    th[2 * n] = 0.3          # mu
    th[2 * n + 1] = 0.2      # vantaggio casa
    if usa_dc:
        th[-1] = -0.05       # rho piccolo: tau resta positivo
    return th


# --------------------------------------------------------------------------
# 1. gradiente per osservazione
# --------------------------------------------------------------------------

@pytest.mark.parametrize("usa_dc", [True, False])
def test_gradiente_per_osservazione_somma_al_totale(usa_dc):
    """`somma_i w_i g_i` deve fare il gradiente totale, penalizzazione esclusa.

    Il confronto non avviene all'ottimo ma in un punto qualsiasi: l'identita'
    e' algebrica, non una proprieta' del massimo, e volerla solo all'ottimo
    nasconderebbe un errore nei termini che li' si annullano."""
    squadre, h, a, x, y, w = _campionato_finto()
    n = len(squadre)
    th = _theta_finto(n, usa_dc)
    prior_att = np.zeros(n)
    prior_dif = np.zeros(n)

    esito = G1.verifica_gradiente(th, h, a, x, y, w, n, usa_dc, prior_att,
                                  prior_dif, lam_pen=0.0)
    assert esito["scarto_lam_pen_zero"] < 1e-6
    assert esito["scarto_penalizzazione_tolta"] < 1e-6
    # il gradiente non e' zero: il test sarebbe vuoto se lo fosse
    assert esito["norma_gradiente_totale"] > 1e-3


@pytest.mark.parametrize("usa_dc", [True, False])
def test_gradiente_per_osservazione_con_penalizzazione_e_prior(usa_dc):
    """Stessa identita' con penalizzazione viva e prior diversi da zero.

    Il termine di penalizzazione non e' per osservazione: qui si controlla che
    toglierlo analiticamente riporti esattamente alla somma dei contributi."""
    squadre, h, a, x, y, w = _campionato_finto()
    n = len(squadre)
    th = _theta_finto(n, usa_dc)
    rng = np.random.default_rng(3)
    prior_att = rng.normal(0, 0.1, n)
    prior_dif = rng.normal(0, 0.1, n)

    esito = G1.verifica_gradiente(th, h, a, x, y, w, n, usa_dc, prior_att,
                                  prior_dif, lam_pen=2.0)
    assert esito["scarto_penalizzazione_tolta"] < 1e-6
    assert esito["scarto_lam_pen_zero"] < 1e-6


def test_gradiente_per_osservazione_e_davvero_per_osservazione():
    """Il contributo della partita i deve dipendere solo dalla partita i.

    Cambiare il risultato di una sola partita non puo' toccare le righe delle
    altre. Senza questo controllo un errore di indicizzazione (per esempio
    `np.add.at` su tutta la matrice) passerebbe il test sulla somma."""
    squadre, h, a, x, y, w = _campionato_finto()
    n = len(squadre)
    th = _theta_finto(n, True)
    S = G1.gradienti_per_osservazione(th, h, a, x, y, n, True)
    x2 = x.copy()
    x2[0] = x2[0] + 3
    S2 = G1.gradienti_per_osservazione(th, h, a, x2, y, n, True)
    assert not np.allclose(S[0], S2[0])
    assert np.allclose(S[1:], S2[1:], atol=0, rtol=0)


# --------------------------------------------------------------------------
# 2. sandwich
# --------------------------------------------------------------------------

def test_sandwich_con_pesi_unitari():
    """Pesi tutti pari a 1: J = S^T S e la sandwich e' quella classica."""
    squadre, h, a, x, y, _ = _campionato_finto()
    n = len(squadre)
    th = _theta_finto(n, True)
    S = G1.gradienti_per_osservazione(th, h, a, x, y, n, True)
    w = np.ones(len(x))

    J = G1.matrice_j(S, w)
    assert np.allclose(J, S.T @ S, atol=1e-12)

    modello = stima(np.array(squadre)[h], np.array(squadre)[a], x, y,
                    squadre=squadre, pesi=w, lam_pen=2.0, usa_dc=True,
                    con_incertezza=True)
    H_inv = modello._hess_inv
    atteso = H_inv @ (S.T @ S) @ H_inv
    ottenuto = G1.covarianza_sandwich(H_inv, J)
    assert np.allclose(ottenuto, 0.5 * (atteso + atteso.T), atol=1e-12)


def test_matrice_j_pesata_uguale_alla_somma_esplicita():
    """Con pesi generici J deve fare `somma_i w_i^2 g_i g_i^T`, termine a termine."""
    squadre, h, a, x, y, w = _campionato_finto()
    n = len(squadre)
    th = _theta_finto(n, True)
    S = G1.gradienti_per_osservazione(th, h, a, x, y, n, True)
    atteso = np.zeros((S.shape[1], S.shape[1]))
    for i in range(S.shape[0]):
        atteso += (w[i] ** 2) * np.outer(S[i], S[i])
    assert np.allclose(G1.matrice_j(S, w), atteso, atol=1e-10)


def test_sandwich_e_semidefinita_positiva():
    """H^-1 J H^-1 e' una forma B J B^T con B simmetrica: mai autovalori negativi."""
    squadre, h, a, x, y, w = _campionato_finto()
    n = len(squadre)
    modello = stima(np.array(squadre)[h], np.array(squadre)[a], x, y,
                    squadre=squadre, pesi=w, lam_pen=2.0, usa_dc=True,
                    con_incertezza=True)
    S = G1.gradienti_per_osservazione(modello._theta, h, a, x, y, n, True)
    C = G1.covarianza_sandwich(modello._hess_inv, G1.matrice_j(S, w))
    assert np.min(np.linalg.eigvalsh(C)) > -1e-10


# --------------------------------------------------------------------------
# 3. caso costruito a mano
# --------------------------------------------------------------------------

def _caso_a_mano():
    """Una sola partita, congiunta 3 x 3 scritta a mano, risultato osservato 1-0.

        P(x, y)      y=0    y=1    y=2
          x=0        0,5    0,2    0,0
          x=1        0,1    0,1    0,0
          x=2        0,1    0,0    0,0

    Somma 1. Marginale casa (0,7; 0,2; 0,1), marginale trasferta (0,7; 0,3; 0)."""
    P = np.array([[[0.5, 0.2, 0.0],
                   [0.1, 0.1, 0.0],
                   [0.1, 0.0, 0.0]]])
    return P, np.array([1]), np.array([0])


def test_punteggio_logaritmico_caso_a_mano():
    P, gc, gt = _caso_a_mano()
    assert P.sum() == pytest.approx(1.0, abs=1e-15)
    ls = G1.punteggio_logaritmico(P, gc, gt)
    assert ls[0] == pytest.approx(-np.log(0.1), abs=1e-12)
    assert ls[0] == pytest.approx(2.302585092994046, abs=1e-12)


def test_rps_caso_a_mano():
    P, gc, gt = _caso_a_mano()
    mc, mv = G1.marginali(P)
    assert np.allclose(mc[0], [0.7, 0.2, 0.1])
    assert np.allclose(mv[0], [0.7, 0.3, 0.0])
    # casa: osservato 1, F = (0,7; 0,9), O = (0; 1) -> 0,49 + 0,01
    assert G1.rps(mc, gc)[0] == pytest.approx(0.50, abs=1e-12)
    # trasferta: osservato 0, F = (0,7; 1,0), O = (1; 1) -> 0,09 + 0
    assert G1.rps(mv, gt)[0] == pytest.approx(0.09, abs=1e-12)


def test_brier_porta_inviolata_caso_a_mano():
    """La porta inviolata di casa si legge sulla marginale della trasferta."""
    P, gc, gt = _caso_a_mano()
    mc, mv = G1.marginali(P)
    br_casa, br_via = G1.brier_porta_inviolata(mc, mv, gc, gt)
    assert br_casa[0] == pytest.approx((0.7 - 1.0) ** 2, abs=1e-12)   # 0-0 subiti
    assert br_via[0] == pytest.approx((0.7 - 0.0) ** 2, abs=1e-12)    # 1 gol subito


def test_pit_randomizzato_caso_a_mano():
    P, gc, gt = _caso_a_mano()
    mc, mv = G1.marginali(P)
    assert G1.pit_randomizzato(mc, gc, np.array([0.5]))[0] == pytest.approx(0.8, abs=1e-12)
    assert G1.pit_randomizzato(mv, gt, np.array([0.25]))[0] == pytest.approx(0.175, abs=1e-12)


def test_pit_randomizzato_e_uniforme_sotto_il_modello_vero():
    """Sanita': se i dati vengono dalla marginale usata, il PIT e' uniforme."""
    import math

    from scipy.stats import kstest
    rng = np.random.default_rng(5)
    lam = 1.4
    k = np.arange(13)
    p = np.exp(-lam) * lam ** k / np.array([float(math.factorial(i)) for i in k])
    p = p / p.sum()
    n = 4000
    osservati = rng.choice(k, size=n, p=p)
    marg = np.tile(p, (n, 1))
    pit = G1.pit_randomizzato(marg, osservati, rng.random(n))
    assert kstest(pit, "uniform").pvalue > 0.01


def test_punteggio_logaritmico_coincide_con_quello_del_modello():
    """Con una sola estrazione la mistura e' il modello — sullo stesso supporto.

    Dopo la correzione della distribuzione campionata (R3), i due percorsi
    hanno bersagli **dichiaratamente diversi**:

    - `ModelloPartita.log_score_risultato` valuta la legge di Dixon-Coles
      **intera**, cosi' un 14-2 riceve la sua probabilita' vera invece di
      quella del 12-2;
    - `G1.mistura` costruisce la matrice **troncata** al supporto scelto, e la
      rinormalizza.

    Confrontarli con la matrice a `MAX_GOL = 12` misura la massa buttata dal
    troncamento, non un difetto. Qui il confronto e' a supporto largo, dove i
    due bersagli convergono; lo scarto a supporto stretto viene misurato nel
    test successivo invece di essere assorbito da una tolleranza piu' larga.
    """
    squadre, h, a, x, y, w = _campionato_finto()
    casa = np.array(squadre)[h]
    via = np.array(squadre)[a]
    modello = stima(casa, via, x, y, squadre=squadre, pesi=w, lam_pen=2.0,
                    usa_dc=True)
    P = G1.mistura([modello], casa, via, max_gol=60)
    nostro = G1.punteggio_logaritmico(P, x.astype(int), y.astype(int))
    loro = modello.log_score_risultato(casa, via, x, y)
    assert np.allclose(nostro, loro, atol=1e-9), (
        f"scarto massimo {np.max(np.abs(nostro - loro)):.2e} a supporto 60: "
        "i due percorsi non valutano la stessa legge")


def test_quanto_costa_il_troncamento_sul_punteggio_logaritmico():
    """La massa buttata dal troncamento ha un prezzo, e va misurato.

    Con `MAX_GOL = 12` la matrice perde la coda oltre dodici gol. Sul
    logaritmo l'effetto e' piu' grande che sulla probabilita': va conosciuto,
    perche' e' la differenza fra il bersaglio del campionatore e quello della
    valutazione.
    """
    squadre, h, a, x, y, w = _campionato_finto()
    casa = np.array(squadre)[h]
    via = np.array(squadre)[a]
    modello = stima(casa, via, x, y, squadre=squadre, pesi=w, lam_pen=2.0,
                    usa_dc=True)
    intero = modello.log_score_risultato(casa, via, x, y)
    stretto = G1.punteggio_logaritmico(
        G1.mistura([modello], casa, via, max_gol=12),
        x.astype(int), y.astype(int))
    scarto = float(np.max(np.abs(stretto - intero)))
    # misurato: dell'ordine di 1e-5 sui logaritmi, cioe' il troncamento sposta
    # il punteggio di molto meno di qualunque differenza fra modelli che ci
    # interessi, ma non e' zero e non va scambiato per tale
    assert scarto < 1e-3, f"il troncamento sposta il log-score di {scarto:.2e}"
    assert scarto > 0, "il troncamento non costa nulla: sospetto"


def test_misture_coincidono_quando_tutte_le_estrazioni_sono_ammissibili():
    """Se nessuna estrazione e' da rigettare le due gestioni sono lo stesso numero.

    Serve a garantire che la gestione «generatore» (troncamento a zero e
    rinormalizzazione) non sposti nulla nel caso normale: se lo facesse, il
    confronto fra le due letture misurerebbe un artefatto invece della
    differenza vera."""
    squadre, h, a, x, y, w = _campionato_finto()
    casa = np.array(squadre)[h]
    via = np.array(squadre)[a]
    modello = stima(casa, via, x, y, squadre=squadre, pesi=w, lam_pen=2.0,
                    usa_dc=True)
    P_gen, P_esc, n_amm = G1.misture([modello], [True], casa, via)
    assert n_amm == 1
    assert np.allclose(P_gen, P_esc, atol=1e-12)
    assert np.allclose(P_gen, G1.mistura([modello], casa, via), atol=1e-12)


def test_misture_escludono_solo_nella_gestione_esclusione():
    """Con un'estrazione marcata non ammissibile le due misture divergono."""
    squadre, h, a, x, y, w = _campionato_finto()
    casa = np.array(squadre)[h]
    via = np.array(squadre)[a]
    modello = stima(casa, via, x, y, squadre=squadre, pesi=w, lam_pen=2.0,
                    usa_dc=True)
    alterato = modello._da_theta(modello._theta.copy())
    alterato.mu = modello.mu + 0.8          # intensita' molto piu' alte
    P_gen, P_esc, n_amm = G1.misture([modello, alterato], [True, False],
                                     casa, via)
    assert n_amm == 1
    assert np.allclose(P_esc, G1.mistura([modello], casa, via), atol=1e-12)
    assert not np.allclose(P_gen, P_esc, atol=1e-6)
    # entrambe restano distribuzioni: somma 1 per partita, nessuna cella negativa
    for P in (P_gen, P_esc):
        assert P.min() >= -1e-15
        assert np.allclose(P.reshape(len(P), -1).sum(axis=1), 1.0, atol=1e-12)


# --------------------------------------------------------------------------
# 4. T1 e' il comportamento attuale, non una sua imitazione
# --------------------------------------------------------------------------

def test_t1_coincide_con_campiona_parametri():
    """Stesse normali standard, stesse forze estratte, fino all'ultimo bit."""
    squadre, h, a, x, y, w = _campionato_finto()
    modello = stima(np.array(squadre)[h], np.array(squadre)[a], x, y,
                    squadre=squadre, pesi=w, lam_pen=2.0, usa_dc=True,
                    con_incertezza=True)
    k = len(modello._theta)
    n_estrazioni = 25
    Z = np.random.default_rng(123).standard_normal((n_estrazioni, k))
    nostri, _ = G1.campiona_con_covarianza(modello, modello._hess_inv, Z)
    loro = modello.campiona_parametri(np.random.default_rng(123), n_estrazioni)
    assert len(nostri) == len(loro) == n_estrazioni
    for m1, m2 in zip(nostri, loro):
        assert np.array_equal(m1.att, m2.att)
        assert np.array_equal(m1.dif, m2.dif)
        assert m1.mu == m2.mu and m1.casa == m2.casa and m1.rho == m2.rho


def test_covarianza_diversa_da_estrazioni_diverse():
    """T2 non puo' coincidere con T1 per distrazione: la covarianza e' un'altra."""
    squadre, h, a, x, y, w = _campionato_finto()
    n = len(squadre)
    modello = stima(np.array(squadre)[h], np.array(squadre)[a], x, y,
                    squadre=squadre, pesi=w, lam_pen=2.0, usa_dc=True,
                    con_incertezza=True)
    S = G1.gradienti_per_osservazione(modello._theta, h, a, x, y, n, True)
    cov2 = G1.covarianza_sandwich(modello._hess_inv, G1.matrice_j(S, w))
    Z = np.random.default_rng(1).standard_normal((5, len(modello._theta)))
    t1, _ = G1.campiona_con_covarianza(modello, modello._hess_inv, Z)
    t2, _ = G1.campiona_con_covarianza(modello, cov2, Z)
    assert not np.allclose(t1[0].att, t2[0].att)


# --------------------------------------------------------------------------
# 5. bootstrap e regola di decisione
# --------------------------------------------------------------------------

def test_bootstrap_appaiato_riconosce_una_differenza_costante():
    d = np.full(200, 0.05)
    indici = np.random.default_rng(2).integers(0, 200, size=(500, 200))
    r = G1.bootstrap_appaiato(d, indici)
    assert r["differenza_media"] == pytest.approx(0.05)
    assert not r["contiene_zero"]


def test_bootstrap_appaiato_riconosce_il_rumore():
    d = np.random.default_rng(4).normal(0, 1, 300)
    indici = np.random.default_rng(2).integers(0, 300, size=(2000, 300))
    r = G1.bootstrap_appaiato(d, indici)
    assert r["contiene_zero"]


def test_verdetto_inconcludente_se_il_migliore_cambia_stagione():
    import pandas as pd
    metriche = pd.DataFrame([
        {"stagione": "A", "trattamento": "T1", "log_score_medio": 1.0},
        {"stagione": "A", "trattamento": "T2", "log_score_medio": 2.0},
        {"stagione": "B", "trattamento": "T1", "log_score_medio": 2.0},
        {"stagione": "B", "trattamento": "T2", "log_score_medio": 1.0},
    ])
    confronti = pd.DataFrame([
        {"stagione": "A", "A": "T1", "B": "T2", "contiene_zero": False,
         "ic_basso": -1.0, "ic_alto": -0.5},
        {"stagione": "B", "A": "T1", "B": "T2", "contiene_zero": False,
         "ic_basso": 0.5, "ic_alto": 1.0},
    ])
    v = G1.verdetto(metriche, confronti)
    assert v["esito"] == "inconcludente" and v["resta"] == "T1"


def test_verdetto_inconcludente_se_lintervallo_contiene_zero():
    import pandas as pd
    metriche = pd.DataFrame([
        {"stagione": "A", "trattamento": "T1", "log_score_medio": 2.0},
        {"stagione": "A", "trattamento": "T2", "log_score_medio": 1.0},
        {"stagione": "B", "trattamento": "T1", "log_score_medio": 2.0},
        {"stagione": "B", "trattamento": "T2", "log_score_medio": 1.0},
    ])
    confronti = pd.DataFrame([
        {"stagione": "A", "A": "T1", "B": "T2", "contiene_zero": False,
         "ic_basso": 0.5, "ic_alto": 1.0},
        {"stagione": "B", "A": "T1", "B": "T2", "contiene_zero": True,
         "ic_basso": -0.1, "ic_alto": 1.0},
    ])
    v = G1.verdetto(metriche, confronti)
    assert v["esito"] == "inconcludente" and v["resta"] == "T1"


def test_verdetto_dichiara_il_vincitore_solo_se_entrambi_i_criteri_reggono():
    import pandas as pd
    metriche = pd.DataFrame([
        {"stagione": "A", "trattamento": "T1", "log_score_medio": 2.0},
        {"stagione": "A", "trattamento": "T2", "log_score_medio": 1.0},
        {"stagione": "B", "trattamento": "T1", "log_score_medio": 2.0},
        {"stagione": "B", "trattamento": "T2", "log_score_medio": 1.0},
    ])
    confronti = pd.DataFrame([
        {"stagione": "A", "A": "T1", "B": "T2", "contiene_zero": False,
         "ic_basso": 0.5, "ic_alto": 1.0},
        {"stagione": "B", "A": "T1", "B": "T2", "contiene_zero": False,
         "ic_basso": 0.5, "ic_alto": 1.0},
    ])
    v = G1.verdetto(metriche, confronti)
    assert v["esito"] == "vincitore" and v["vincitore"] == "T2"


# --------------------------------------------------------------------------
# 6. disciplina temporale
# --------------------------------------------------------------------------

def test_data_limite_e_il_giorno_prima_della_prima_giornata():
    import pandas as pd
    partite = pd.DataFrame({
        "stagione": ["X", "X", "Y"],
        "data": pd.to_datetime(["2024-08-17", "2024-08-25", "2025-08-23"]),
    })
    assert G1.data_limite_stagione(partite, "X") == "2024-08-16"
    assert G1.data_limite_stagione(partite, "Y") == "2025-08-22"


def test_intervallo_binomiale_contiene_la_frequenza():
    basso, alto = G1.intervallo_binomiale(200, 760)
    assert basso < 200 / 760 < alto
    assert G1.intervallo_binomiale(0, 100)[0] == 0.0
    assert G1.intervallo_binomiale(100, 100)[1] == 1.0
