"""La distribuzione dei gol deve essere valida lungo tutto il percorso.

I quattro test gia' presenti in `test_l2_partita.py` controllano la matrice a
intensita' **fisse** e con `rho` scelto dentro l'intervallo ammissibile. Questo
file controlla il percorso che il progetto usa davvero:

    stima  ->  campiona_parametri  ->  intensita' della partita  ->
    matrice_risultato  ->  riparazione del generatore  ->  campionamento  ->
    valutazione (coda, log-score)

Il difetto che questi test fissano: i quattro percorsi non sono equivalenti.
`campiona_parametri` estrae da una normale non vincolata, l'ammissibilita' di
`rho` viene verificata solo sul punto stimato, il generatore ripara con
`np.maximum(P, 0)` e rinormalizza, e la valutazione della coda usa le marginali
Poisson **intere**. Il caso di riferimento e' quello riprodotto in
`data/l2/r3/riproduzione.json`: modello 2024-25, cutoff 2024-08-16, seme
20260908, dove 13 campioni su 200 hanno `rho` non ammissibile per almeno una
partita e 194 combinazioni partita-campione su 76.000 producono celle negative.

Il caso di riferimento richiede il parquet delle partite: se manca, i test che
lo usano vengono saltati e restano quelli su parametri sintetici, che il
difetto lo riproducono lo stesso.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pytest
from scipy.stats import poisson

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from fantabot.tabellino.partita import (          # noqa: E402
    MAX_GOL, MAX_GOL_LIMITE, TOL_SUPPORTO, campiona_risultati,
    matrice_risultato, pmf_risultato, rho_ammissibile, rho_effettivo, stima,
    supporto_necessario, tau,
)

PARQUET = ROOT / "data" / "processed" / "l2_partite.parquet"

# caso riprodotto dal committente e da `data/l2/r3/r3_riproduci.py`
STAGIONE = "2024-25"
AS_OF = "2024-08-16"
SEME = 20260908
# bastano le prime otto estrazioni: la 1 e la 3 sono gia' non ammissibili
# (elenco completo dei campioni cattivi in data/l2/r3/verifica_non_ammissibili.csv:
# 1, 3, 33, 39, 40, 61, 79, 145, 152, 153, 168, 195, 196)
N_ESTRAZIONI = 8

_cache: dict = {}


def _caso_reale():
    """(modello, casa, trasferta) del caso riprodotto. Costruito una volta."""
    if "caso" in _cache:
        return _cache["caso"]
    if not PARQUET.exists():
        pytest.skip(f"manca {PARQUET}")
    import pandas as pd
    from fantabot.tabellino import configurazione as cfg
    part = pd.read_parquet(PARQUET)
    part["data"] = pd.to_datetime(part["data"])
    cal = part[part.stagione == STAGIONE]
    mp, _, _ = cfg.costruisci_modello_partita(
        part, AS_OF, squadre=None, stagione_bersaglio=STAGIONE,
        con_incertezza=True, percorsi_ingresso=[], etichetta="test R3")
    _cache["caso"] = (mp, cal.casa.values, cal.trasferta.values)
    return _cache["caso"]


def _estrazioni(n: int = N_ESTRAZIONI):
    mp, casa, tra = _caso_reale()
    copie = mp.campiona_parametri(np.random.default_rng(SEME), n)
    return mp, casa, tra, copie


def _riparazione_del_generatore(P: np.ndarray) -> np.ndarray:
    """Esattamente cio' che fa `generatore.genera` prima di campionare."""
    piatta = np.maximum(P.ravel(), 0.0)
    return (piatta / piatta.sum()).reshape(P.shape)


def _poisson_troncata(lam: float, k_max: int) -> np.ndarray:
    p = poisson.pmf(np.arange(k_max + 1), lam)
    return p / p.sum()


# --------------------------------------------------------------------------
# 1. il punto stimato
# --------------------------------------------------------------------------

def test_punto_stimato_ammissibile_su_tutte_le_partite():
    """Al punto stimato `rho` deve stare dentro l'intervallo di OGNI partita.

    Serve a separare le due cose: se questo test passa e quelli sulle
    estrazioni falliscono, il difetto non e' nella stima ma nel campionamento
    dei parametri. Nel caso riprodotto passa: `rho` = -0,0605 contro un
    intervallo [-0,25; 0,2783] e `tau_non_valido` = 0.
    """
    mp, casa, tra = _caso_reale()
    lam, mu = mp.intensita(casa, tra)
    cattive = 0
    for i in range(len(lam)):
        basso, alto = rho_ammissibile(lam[i], mu[i])
        if not (basso < mp.rho < alto):
            cattive += 1
    assert cattive == 0, f"{cattive} partite non ammissibili al punto stimato"
    assert mp.diagnostica["tau_non_valido"] == 0


# --------------------------------------------------------------------------
# 2. tutte le estrazioni del caso riprodotto
# --------------------------------------------------------------------------

def test_ogni_estrazione_da_una_matrice_non_negativa():
    """Nessuna cella negativa su NESSUNA estrazione e NESSUNA partita.

    E' il difetto principale: la verifica di ammissibilita' viene fatta solo
    sul punto stimato, mentre le partite simulate usano i parametri estratti.
    Sul caso riprodotto 194 combinazioni partita-campione su 76.000 danno celle
    negative, con massa negativa fino a 2,93e-4.
    """
    mp, casa, tra, copie = _estrazioni()
    peggio = 0.0
    quante = 0
    for c in copie:
        lam, mu = c.intensita(casa, tra)
        for i in range(len(lam)):
            P = matrice_risultato(float(lam[i]), float(mu[i]), c.rho)
            if P.min() < 0:
                quante += 1
                peggio = max(peggio, float(-P[P < 0].sum()))
    assert quante == 0, (
        f"{quante} combinazioni partita-estrazione con celle negative, "
        f"massa negativa massima {peggio:.3e}")


def test_ogni_estrazione_conserva_le_marginali_dopo_la_riparazione():
    """Le marginali della distribuzione DAVVERO campionata restano Poisson.

    §14.2 del protocollo rivendica che le marginali coincidono con la Poisson
    troncata entro 1,5e-16. La verifica che lo sosteneva era a intensita'
    fisse; qui il bersaglio e' la matrice riparata dal generatore sui parametri
    estratti. Misurato sul caso riprodotto: lo scarto massimo del clipping vale
    2,94e-4, mediana 3,40e-6.
    """
    mp, casa, tra, copie = _estrazioni()
    peggio = 0.0
    for c in copie:
        lam, mu = c.intensita(casa, tra)
        for i in range(len(lam)):
            P = matrice_risultato(float(lam[i]), float(mu[i]), c.rho)
            Q = _riparazione_del_generatore(P)
            k_max = Q.shape[0] - 1
            sx = np.abs(Q.sum(1) - _poisson_troncata(float(lam[i]), k_max)).max()
            sy = np.abs(Q.sum(0) - _poisson_troncata(float(mu[i]), k_max)).max()
            peggio = max(peggio, float(sx), float(sy))
    assert peggio < 1e-12, (
        f"le marginali della distribuzione campionata si scostano dalla "
        f"Poisson troncata di {peggio:.3e}")


def test_massa_fuori_dal_supporto_limitata_su_ogni_estrazione():
    """Il supporto deve contenere la distribuzione, non tagliarla.

    Sul caso riprodotto 131 combinazioni su 76.000 hanno intensita' oltre
    dodici gol attesi: con `MAX_GOL = 12` fisso la massa buttata via arriva a
    0,83 al 99,9-esimo percentile e a 1,0 all'intensita' massima (46,70). Una
    distribuzione cosi' non e' quella dichiarata: e' quasi una massa puntuale
    sul risultato 12-12.
    """
    mp, casa, tra, copie = _estrazioni()
    peggio = 0.0
    for c in copie:
        lam, mu = c.intensita(casa, tra)
        for i in range(len(lam)):
            P = matrice_risultato(float(lam[i]), float(mu[i]), c.rho)
            k_max = P.shape[0] - 1
            fuori = 1.0 - (poisson.cdf(k_max, float(lam[i]))
                           * poisson.cdf(k_max, float(mu[i])))
            peggio = max(peggio, float(fuori))
    assert peggio < 1e-9, (
        f"massa fuori dal supporto fino a {peggio:.3e} sulle estrazioni")


# --------------------------------------------------------------------------
# 3. casi estremi, a parametri dichiarati
# --------------------------------------------------------------------------

@pytest.mark.parametrize("lam,mu,rho", [
    (1.4, 1.2, -0.06),          # regime operativo
    (6.0, 3.0, -0.05),          # gia' presente in test_l2_partita
    (13.3, 10.0, -0.06),        # mediana delle combinazioni non ammissibili
    (46.7, 38.5, -0.06),        # intensita' massima del caso riprodotto
    (2.0, 2.0, 0.30),           # rho oltre il limite superiore 1/(lam*mu)=0,25
    (1.0, 1.0, -1.5),           # rho oltre il limite inferiore -1
    (0.2, 0.2, 0.99),           # intensita' minime, rho vicino a 1
])
def test_casi_estremi_distribuzione_valida(lam, mu, rho):
    """Positivita', normalizzazione e marginali anche fuori dal regime.

    Sono i punti in cui il percorso reale finisce quando l'incertezza sui
    parametri e' grande: se la funzione non li regge, non regge il percorso.
    """
    P = matrice_risultato(lam, mu, rho)
    assert P.min() >= 0.0, f"cella negativa {P.min():.3e}"
    assert abs(P.sum() - 1.0) < 1e-12
    k_max = P.shape[0] - 1
    sx = np.abs(P.sum(1) - _poisson_troncata(lam, k_max)).max()
    sy = np.abs(P.sum(0) - _poisson_troncata(mu, k_max)).max()
    assert sx < 1e-12 and sy < 1e-12, (sx, sy)
    fuori = 1.0 - poisson.cdf(k_max, lam) * poisson.cdf(k_max, mu)
    assert fuori < 1e-9, f"massa fuori dal supporto {fuori:.3e}"


# --------------------------------------------------------------------------
# 4. accordo fra calcolo analitico e distribuzione realmente campionata
# --------------------------------------------------------------------------

@pytest.mark.parametrize("lam,mu", [(1.4, 1.2), (3.0, 1.2), (6.0, 3.0)])
def test_campionato_coincide_con_analitico(lam, mu):
    """La frequenza empirica di `campiona_risultati` segue la matrice.

    Il campionamento avviene per inversione della cumulativa sulla matrice
    appiattita: se la matrice e' valida, le frequenze devono coincidere entro
    l'errore Monte Carlo. Il test guarda anche la coda a sei gol, che e' la
    quantita' su cui il progetto sta decidendo.
    """
    rho = -0.06
    n = 200_000
    rng = np.random.default_rng(7)
    u = rng.random((n, 1))
    ris = campiona_risultati(np.array([lam]), np.array([mu]), rho, rng, u=u)
    gc = ris[:, 0, 0].astype(int)
    gt = ris[:, 0, 1].astype(int)
    P = matrice_risultato(lam, mu, rho)
    k_max = P.shape[0] - 1
    att_x = P.sum(1)
    oss_x = np.bincount(np.minimum(gc, k_max), minlength=k_max + 1) / n
    # tre errori standard binomiali, piu' un margine per le celle rare
    es = 3 * np.sqrt(np.maximum(att_x, 1e-9) * (1 - att_x) / n) + 1e-4
    assert np.all(np.abs(oss_x - att_x) < es), np.max(np.abs(oss_x - att_x) - es)
    coda_oss = float((gc >= 6).mean())
    coda_att = float(att_x[6:].sum())
    assert abs(coda_oss - coda_att) < 3 * np.sqrt(
        coda_att * (1 - coda_att) / n) + 1e-5, (coda_oss, coda_att)


# --------------------------------------------------------------------------
# 5. la dipendenza di Dixon-Coles resta quella prevista
# --------------------------------------------------------------------------

@pytest.mark.parametrize("lam,mu,rho", [
    (1.4, 1.2, -0.06), (1.4, 1.2, 0.10), (2.2, 0.9, -0.15), (0.8, 0.8, 0.3),
])
def test_dipendenza_dixon_coles_conservata(lam, mu, rho):
    """Le quattro celle basse portano esattamente il fattore `tau`.

    La verifica e' contro il prodotto delle marginali della MATRICE, non contro
    la Poisson intera: cosi' misura la dipendenza e non il troncamento. E' la
    proprieta' che distingue Dixon-Coles da due Poisson indipendenti, e deve
    sopravvivere a qualunque riparazione della matrice.
    """
    P = matrice_risultato(lam, mu, rho)
    px = P.sum(1)
    py = P.sum(0)
    for (x, y) in ((0, 0), (0, 1), (1, 0), (1, 1)):
        atteso = px[x] * py[y] * float(tau(x, y, lam, mu, rho))
        assert abs(P[x, y] - atteso) < 1e-12 * max(1.0, atteso), (
            f"cella ({x},{y}): {P[x, y]:.12e} contro {atteso:.12e}")
    # fuori dalle quattro celle la congiunta e' il prodotto delle marginali
    assert abs(P[3, 2] - px[3] * py[2]) < 1e-12


# --------------------------------------------------------------------------
# 6. log-score: un risultato fuori supporto ha una definizione
# --------------------------------------------------------------------------

def test_log_score_fuori_supporto_non_finisce_nell_ultima_cella():
    """Un risultato oltre il supporto non prende la probabilita' di `max_gol`.

    Il codice attuale fa `x = min(gol, P.shape[0] - 1)`: un 14-2 riceve la
    probabilita' esatta del 12-2, che non e' ne' P(14,2) ne' P(X >= 12, Y = 2).
    E' una cella senza definizione probabilistica, e rende il log-score non
    monotono nei gol.
    """
    rng = np.random.default_rng(11)
    n_sq = 8
    squadre = [f"S{i}" for i in range(n_sq)]
    h = rng.integers(0, n_sq, 400)
    a = (h + 1 + rng.integers(0, n_sq - 1, 400)) % n_sq
    m = stima([squadre[i] for i in h], [squadre[i] for i in a],
              rng.poisson(1.5, 400), rng.poisson(1.2, 400),
              squadre=squadre, lam_pen=1.0)
    casa = [squadre[0]] * 3
    via = [squadre[1]] * 3
    s = m.log_score_risultato(casa, via, [MAX_GOL, MAX_GOL + 1, MAX_GOL + 3],
                              [2, 2, 2])
    assert s[1] > s[0] + 1e-6, (
        "il risultato oltre il supporto ha la stessa probabilita' del "
        f"troncamento: {s[0]:.6f} contro {s[1]:.6f}")
    assert s[2] > s[1] + 1e-6, "log-score non monotono nei gol"


def test_log_score_coincide_con_la_forma_chiusa():
    """Il punteggio e' `-log` della legge di Dixon-Coles intera, non altro."""
    rng = np.random.default_rng(12)
    n_sq = 6
    squadre = [f"T{i}" for i in range(n_sq)]
    h = rng.integers(0, n_sq, 300)
    a = (h + 1 + rng.integers(0, n_sq - 1, 300)) % n_sq
    m = stima([squadre[i] for i in h], [squadre[i] for i in a],
              rng.poisson(1.6, 300), rng.poisson(1.3, 300),
              squadre=squadre, lam_pen=1.0)
    casa = [squadre[0], squadre[1], squadre[2]]
    via = [squadre[3], squadre[4], squadre[5]]
    gc, gt = [0, 2, 5], [1, 2, 0]
    lam, mu = m.intensita(casa, via)
    atteso = np.array([
        -np.log(float(pmf_risultato(float(lam[i]), float(mu[i]), m.rho,
                                    gc[i], gt[i])))
        for i in range(3)])
    assert np.allclose(m.log_score_risultato(casa, via, gc, gt), atteso,
                       atol=1e-15)


# --------------------------------------------------------------------------
# 7. niente riparazioni silenziose: sono contate ed esposte
# --------------------------------------------------------------------------

def test_il_registro_conta_le_proiezioni_di_rho():
    """Ogni proiezione di `rho` finisce nel registro, con il suo scarto.

    Sul caso riprodotto sono 194 combinazioni su 76.000, scarto massimo 0,1231.
    Qui bastano le prime otto estrazioni; il conteggio deve coincidere con
    quello che `controlla_partite` dichiara estrazione per estrazione.
    """
    mp, casa, tra = _caso_reale()
    copie = mp.campiona_parametri(np.random.default_rng(SEME), N_ESTRAZIONI,
                                  partite=(casa, tra))
    atteso = sum(int(c.diagnostica["partite_non_ammissibili"]) for c in copie)
    assert atteso > 0, "il caso di riferimento non ha piu' estrazioni cattive"
    registro: dict = {}
    for c in copie:
        lam, mu = c.intensita(casa, tra)
        for i in range(len(lam)):
            matrice_risultato(float(lam[i]), float(mu[i]), c.rho,
                              registro=registro)
    assert registro["chiamate"] == N_ESTRAZIONI * len(casa)
    assert registro.get("rho_proiettato", 0) == atteso
    assert registro.get("celle_negative", 0) == 0
    assert registro["rho_scarto_massimo"] > 0
    assert registro["massa_fuori_supporto_massima"] < 1e-9


def test_ogni_estrazione_e_controllata_sulle_partite_da_simulare():
    """`campiona_parametri(partite=...)` verifica l'estrazione, non il punto.

    E' il controllo che mancava: il punto stimato e' ammissibile su tutte le
    380 partite, e nonostante questo alcune estrazioni non lo sono.
    """
    mp, casa, tra = _caso_reale()
    copie = mp.campiona_parametri(np.random.default_rng(SEME), N_ESTRAZIONI,
                                  partite=(casa, tra))
    cattive = [i for i, c in enumerate(copie)
               if not c.diagnostica["rho_dentro_ammissibile"]]
    assert cattive, "nessuna estrazione cattiva: il caso non e' quello atteso"
    for c in copie:
        d = c.diagnostica
        assert d["partite_controllate"] == len(casa)
        assert d["intensita_massima"] > 0
        assert d["supporto_necessario_massimo"] >= MAX_GOL
        # il conteggio deve coincidere con il ricalcolo diretto
        lam, mu = c.intensita(casa, tra)
        diretto = sum(1 for i in range(len(lam))
                      if rho_effettivo(float(lam[i]), float(mu[i]), c.rho)[1] > 0)
        assert d["partite_non_ammissibili"] == diretto


def test_campiona_risultati_non_ripara_in_silenzio():
    """Nessuna cella negativa da riparare, e il registro lo dichiara."""
    registro: dict = {}
    rng = np.random.default_rng(3)
    lam = np.array([1.5, 6.0, 13.3])
    mu = np.array([1.2, 3.0, 10.0])
    ris = campiona_risultati(lam, mu, -0.06, rng, n_sims=500,
                             registro=registro)
    assert registro.get("celle_negative", 0) == 0
    assert registro["chiamate"] == 3
    # i gol estratti stanno dentro il supporto scelto per quella partita
    for i in range(3):
        k = supporto_necessario(float(lam[i]), float(mu[i]))
        assert ris[:, i, :].max() <= k


# --------------------------------------------------------------------------
# 8. stesso contratto probabilistico fra campionamento e valutazione
# --------------------------------------------------------------------------

@pytest.mark.parametrize("lam,mu", [
    (1.45, 1.22), (3.0, 1.2), (6.0, 3.0), (16.3, 10.0), (46.7, 38.5),
])
def test_coda_della_matrice_uguale_alla_coda_poisson_intera(lam, mu):
    """La coda che il progetto misura e quella che campiona sono la stessa.

    `scripts/l2_coda_storica.py` calcola `P(G >= 6)` con la Poisson **intera**,
    mentre il generatore campiona dalla matrice. Prima della correzione i due
    bersagli differivano: sul caso riprodotto la coda media analitica valeva
    0,01485703999 e quella della matrice riparata 0,01479708829, con uno
    scarto per partita fino a 0,01073. Il supporto adattivo li riallinea entro
    la tolleranza dichiarata.
    """
    P = matrice_risultato(lam, mu, -0.06)
    for soglia in (4, 6, 8):
        assert abs(float(P.sum(1)[soglia:].sum())
                   - float(poisson.sf(soglia - 1, lam))) < 1e-11
        assert abs(float(P.sum(0)[soglia:].sum())
                   - float(poisson.sf(soglia - 1, mu))) < 1e-11


def test_la_proiezione_di_rho_non_abbassa_la_coda():
    """La riparazione non e' un modo mascherato di far scendere la coda.

    La coda e' una quantita' marginale e le marginali non dipendono da `rho`:
    proiettare `rho` la lascia identica. Se una correzione futura abbassasse la
    coda, non potrebbe essere questa.
    """
    lam, mu = 13.3, 10.0
    base = matrice_risultato(lam, mu, 0.0)
    for rho in (-0.06, 0.5, -3.0, 12.0):
        P = matrice_risultato(lam, mu, rho)
        assert np.max(np.abs(P.sum(1) - base.sum(1))) < 1e-14
        assert np.max(np.abs(P.sum(0) - base.sum(0))) < 1e-14


# --------------------------------------------------------------------------
# 9. il supporto adattivo
# --------------------------------------------------------------------------

@pytest.mark.parametrize("m", [0.05, 0.5, 1.45, 4.0, 16.3, 46.7, 120.0])
def test_supporto_necessario_rispetta_la_tolleranza(m):
    """`P(G > K) < TOL_SUPPORTO`, e `K` non e' piu' grande del necessario."""
    k = supporto_necessario(m, m)
    assert k >= MAX_GOL
    assert float(poisson.sf(k, m)) < TOL_SUPPORTO
    if k > MAX_GOL:
        assert float(poisson.sf(k - 1, m)) >= TOL_SUPPORTO


def test_supporto_oltre_il_tetto_viene_dichiarato():
    """Se il tetto non basta, il registro lo dice invece di tacere."""
    registro: dict = {}
    matrice_risultato(600.0, 600.0, 0.0, registro=registro)
    assert registro["supporto_massimo"] == MAX_GOL_LIMITE
    assert registro.get("supporto_insufficiente", 0) == 1
    assert registro["massa_fuori_supporto_massima"] > TOL_SUPPORTO


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
