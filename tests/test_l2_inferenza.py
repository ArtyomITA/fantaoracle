"""Prove dell'inferenza del banco: dipendenze incrociate e ensemble finiti.

Il difetto che questi test chiudono, dichiarato in `reports/PROTOCOLLO_v2.md`
§3.3 e §15.2: il verdetto del banco ricampionava le righe (giocatore, giornata)
come indipendenti, mentre le righe della stessa partita condividono il
risultato e quelle dello stesso giocatore condividono la storia. Misurato dal
ramo di ricerca su un disegno con la geometria del banco, l'intervallo nominale
al 95 % copriva il vero valore il **50,7 %** delle volte.

I parametri dei disegni simulati qui sotto sono dichiarati **prima**
dell'esecuzione e non sono stati spostati dopo aver visto i risultati.
"""
import sys
from pathlib import Path

import numpy as np
import pytest
from scipy import stats

RADICE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RADICE / "src"))

from fantabot.tabellino import inferenza as inf            # noqa: E402


# --------------------------------------------------------------------------
# disegno incrociato di riferimento
# --------------------------------------------------------------------------

def _griglia(a=40, b=50, sd_a=0.30, sd_b=0.20, sd_e=1.00, seme=0):
    """Disegno a componenti note, incrociato come partita per giocatore.

    `d[i, j] = alfa_i + beta_j + errore`, con `i` la prima dimensione di
    grappolo e `j` la seconda. La varianza vera della media e' in forma
    chiusa: `sd_a^2/a + sd_b^2/b + sd_e^2/(a*b)`.
    """
    rng = np.random.default_rng(seme)
    alfa = rng.normal(0, sd_a, a)
    beta = rng.normal(0, sd_b, b)
    e = rng.normal(0, sd_e, (a, b))
    d = alfa[:, None] + beta[None, :] + e
    id_1 = np.repeat(np.arange(a), b)
    id_2 = np.tile(np.arange(b), a)
    return d.ravel(), id_1, id_2


def _varianza_vera(a=40, b=50, sd_a=0.30, sd_b=0.20, sd_e=1.00):
    return sd_a ** 2 / a + sd_b ** 2 / b + sd_e ** 2 / (a * b)


def test_con_grappoli_tutti_singoletti_torna_l_errore_standard_classico():
    """Guardia sulla formula: se ogni riga e' un grappolo in entrambe le
    dimensioni, `V_2way` deve ridursi alla varianza campionaria della media.

    E' il caso in cui la correzione non ha niente da correggere. Se questo test
    fallisce, la formula e' sbagliata a prescindere dai grappoli veri."""
    rng = np.random.default_rng(7)
    d = rng.normal(0, 1.0, 500)
    ids = np.arange(500)
    iv = inf.intervallo_two_way(d, ids, ids + 10_000)
    atteso = float(d.std(ddof=1) / np.sqrt(d.size))
    assert iv.ammissibile
    assert iv.errore_standard == pytest.approx(atteso, rel=1e-12)


def test_l_errore_standard_two_way_ritrova_quello_vero():
    """Su un disegno a componenti note, il two-way deve stare vicino al vero
    mentre il metodo sulle righe deve stare molto sotto."""
    vero = np.sqrt(_varianza_vera())
    two_way, righe = [], []
    for s in range(60):
        d, i1, i2 = _griglia(seme=s)
        iv = inf.intervallo_two_way(d, i1, i2)
        two_way.append(iv.errore_standard)
        righe.append(iv.diagnostica["errori_standard"]["righe_indipendenti"])
    r_two = float(np.mean(two_way)) / vero
    r_righe = float(np.mean(righe)) / vero
    assert 0.85 <= r_two <= 1.15, f"two-way fuori bersaglio: {r_two:.3f}"
    assert r_righe < 0.5, (
        f"il metodo sulle righe non risulta troppo stretto ({r_righe:.3f}): "
        "il disegno di prova non ha dipendenza, il test non dice niente")


def test_la_copertura_del_two_way_e_vicina_al_nominale_quella_sulle_righe_no():
    """La prova che conta: quante volte l'intervallo contiene il vero valore.

    Il vero valore della media e' zero per costruzione. Soglie dichiarate
    prima: il two-way deve coprire almeno l'88 %, il metodo sulle righe deve
    stare sotto il 75 % — se le coprisse entrambe la correzione sarebbe inutile.
    """
    dentro_two, dentro_righe = 0, 0
    prove = 200
    t_righe = stats.t.ppf(0.975, 40 * 50 - 1)
    for s in range(prove):
        d, i1, i2 = _griglia(seme=1000 + s)
        iv = inf.intervallo_two_way(d, i1, i2)
        dentro_two += int(iv.ic_basso <= 0.0 <= iv.ic_alto)
        es_r = iv.diagnostica["errori_standard"]["righe_indipendenti"]
        dentro_righe += int(abs(iv.differenza) <= t_righe * es_r)
    c_two, c_righe = dentro_two / prove, dentro_righe / prove
    assert c_two >= 0.88, f"copertura two-way {c_two:.3f}"
    assert c_righe < 0.75, f"copertura righe {c_righe:.3f}"


def test_una_varianza_non_ammissibile_e_dichiarata_non_aggiustata():
    """`V_2way` non e' garantita semidefinita positiva (Cameron & Miller, eq.
    21). Quando esce negativa il risultato va segnalato, non sostituito in
    silenzio con un one-way: qui il disegno a scacchiera annulla le somme per
    grappolo in entrambe le dimensioni e rende `V` negativa per costruzione."""
    a, b = 20, 30
    i = np.repeat(np.arange(a), b)
    j = np.tile(np.arange(b), a)
    d = ((-1.0) ** (i + j))
    iv = inf.intervallo_two_way(d, i, j)
    assert not iv.ammissibile
    assert iv.diagnostica["componenti"]["V"] < 0
    assert np.isnan(iv.ic_basso) and np.isnan(iv.ic_alto)
    assert not iv.esclude_zero
    assert inf.esito_confronto(iv, None) == "varianza non ammissibile"


def test_con_meno_di_due_grappoli_l_inferenza_si_ferma():
    """Con una sola partita (o un solo giocatore) non c'e' inferenza in quella
    dimensione, e non si ripiega sull'altra: e' lo stesso motivo per cui i
    verdetti si fanno una stagione per volta invece di trattare le due stagioni
    come due grappoli."""
    d = np.random.default_rng(3).normal(size=100)
    with pytest.raises(ValueError, match="meno di due grappoli"):
        inf.intervallo_two_way(d, np.zeros(100, int), np.arange(100))


def test_il_bootstrap_a_grappoli_riproduce_il_one_way_analitico():
    """Controllo di indicizzazione: le due strade devono coincidere entro
    l'errore del bootstrap. Se non coincidono, il ricampionamento sta prendendo
    righe sbagliate."""
    d, i1, _ = _griglia(a=40, b=50, seme=11)
    iv = inf.intervallo_two_way(d, i1, np.arange(d.size))
    analitico = iv.diagnostica["errori_standard"]["one_way_1"]
    boot = inf.bootstrap_grappoli(d, i1, seme=5, repliche=400)
    assert boot["es"] == pytest.approx(analitico, rel=0.12)


def test_rho_intra_ritrova_una_correlazione_dichiarata():
    """La correlazione dentro grappolo si misura, non si assume piccola."""
    rng = np.random.default_rng(4)
    a, b = 200, 20
    sd_a, sd_e = 0.5, 1.0
    rho_vero = sd_a ** 2 / (sd_a ** 2 + sd_e ** 2)
    d = (rng.normal(0, sd_a, a)[:, None] + rng.normal(0, sd_e, (a, b))).ravel()
    ids = np.repeat(np.arange(a), b)
    assert inf.rho_intra(d, ids) == pytest.approx(rho_vero, abs=0.05)


# --------------------------------------------------------------------------
# punteggi equi
# --------------------------------------------------------------------------

def _crps_normale(mu, sigma, y):
    """CRPS in forma chiusa per una normale (Gneiting-Raftery)."""
    z = (y - mu) / sigma
    return float(sigma * (z * (2 * stats.norm.cdf(z) - 1)
                          + 2 * stats.norm.pdf(z) - 1 / np.sqrt(np.pi)))


def test_l_identita_fra_empirico_ed_equo_e_esatta():
    """`CRPS_emp - CRPS_equo = dispersione / (m - 1)`: costa zero, perche' il
    banco calcola gia' entrambi i termini."""
    rng = np.random.default_rng(9)
    for m in (5, 12, 30):
        x = rng.normal(6.0, 1.3, m)
        y = 6.9
        disp = inf.dispersione_crps(x)
        emp = float(np.mean(np.abs(x - y))) - disp
        equo = inf.crps_equo(emp, disp, m)
        assert float(emp - equo) == pytest.approx(disp / (m - 1), rel=1e-12)


def test_il_crps_empirico_e_distorto_verso_l_alto_e_l_equo_no():
    """La distorsione vale `E|X-X'| / (2m)` ed e' positiva: il punteggio
    empirico penalizza un ensemble per il solo fatto di essere finito."""
    rng = np.random.default_rng(20260908)
    m, mu, sigma, y, n = 12, 6.0, 1.3, 6.9, 40_000
    x = rng.normal(mu, sigma, (n, m))
    a = np.abs(x - y).mean(axis=1)
    xs = np.sort(x, axis=1)
    pesi = 2 * np.arange(1, m + 1) - m - 1
    disp = (xs * pesi).sum(axis=1) / (m * m)
    emp = a - disp
    equo = emp - disp / (m - 1)
    vero = _crps_normale(mu, sigma, y)
    es = float(equo.std(ddof=1) / np.sqrt(n))
    distorsione_prevista = 2 * sigma / np.sqrt(np.pi) / (2 * m)  # E|X-X'|/(2m)
    assert float(emp.mean()) - vero == pytest.approx(distorsione_prevista,
                                                     rel=0.05)
    assert abs(float(equo.mean()) - vero) < 4 * es, (
        f"il punteggio equo e' distorto: {float(equo.mean()):.6f} contro "
        f"{vero:.6f}, errore standard {es:.6f}")


def test_il_brier_equo_e_non_distorto():
    """`E[(p_hat - y)^2] = (p - y)^2 + p(1-p)/m`; la correzione di Ferro toglie
    esattamente il secondo termine."""
    rng = np.random.default_rng(4041)
    m, p, q, n = 30, 0.55, 0.62, 300_000
    i = rng.binomial(m, p, n)
    p_hat = i / m
    emp = (p_hat - q) ** 2
    equo = inf.brier_equo(p_hat, q, m)
    bersaglio = (p - q) ** 2 + q * (1 - q)   # y e' bernoulliana con media q
    # qui l'esito e' fisso a `q`, quindi il bersaglio del solo termine
    # quadratico e' (p - q)^2
    bersaglio_quadratico = (p - q) ** 2
    assert float(emp.mean()) - bersaglio_quadratico == pytest.approx(
        p * (1 - p) / m, rel=0.05)
    es = float(equo.std(ddof=1) / np.sqrt(n))
    assert abs(float(equo.mean()) - bersaglio_quadratico) < 4 * es
    # con l'esito tenuto fisso a `q` il termine di varianza dell'esito non
    # entra: il bersaglio completo `bersaglio` vale di piu' di quello
    # quadratico, ed e' scritto qui per non confondere le due quantita'
    assert bersaglio > bersaglio_quadratico


def test_la_correzione_equa_non_si_cancella_nelle_differenze():
    """Il punto che rende la correzione non cosmetica: si annulla se e solo se
    i due bracci hanno la stessa dispersione media di ensemble.

    Con `m = 30` il segno di un confronto si ribalta quando il divario di
    dispersione supera `|Delta| * 29`."""
    rng = np.random.default_rng(77)
    m, n = 30, 5_000
    y = rng.normal(6.0, 1.0, n)
    stretto = rng.normal(6.0, 0.55, (n, m))    # sottodisperso
    largo = rng.normal(6.0, 1.35, (n, m))      # ben disperso

    def punteggi(x):
        a = np.abs(x - y[:, None]).mean(axis=1)
        xs = np.sort(x, axis=1)
        pesi = 2 * np.arange(1, m + 1) - m - 1
        disp = (xs * pesi).sum(axis=1) / (m * m)
        return a - disp, disp

    e1, d1 = punteggi(stretto)
    e2, d2 = punteggi(largo)
    delta_emp = float((e1 - e2).mean())
    delta_equo = float((inf.crps_equo(e1, d1, m)
                        - inf.crps_equo(e2, d2, m)).mean())
    spostamento = delta_equo - delta_emp
    previsto = -float((d1 - d2).mean()) / (m - 1)
    assert spostamento == pytest.approx(previsto, rel=1e-12)
    assert abs(spostamento) > 1e-4, (
        "con dispersioni cosi' diverse la correzione deve spostare la "
        "differenza in modo visibile, altrimenti il test non prova nulla")


def test_a_dispersione_uguale_la_correzione_sparisce_dalla_differenza():
    """Controllo opposto: se i due bracci hanno la stessa dispersione, equo ed
    empirico danno la stessa differenza. Serve a escludere che il test
    precedente stia misurando un artefatto."""
    rng = np.random.default_rng(78)
    m, n = 30, 5_000
    y = rng.normal(6.0, 1.0, n)
    a1 = rng.normal(6.0, 1.0, (n, m))
    a2 = rng.normal(6.4, 1.0, (n, m))

    def punteggi(x):
        a = np.abs(x - y[:, None]).mean(axis=1)
        xs = np.sort(x, axis=1)
        pesi = 2 * np.arange(1, m + 1) - m - 1
        disp = (xs * pesi).sum(axis=1) / (m * m)
        return a - disp, disp

    e1, d1 = punteggi(a1)
    e2, d2 = punteggi(a2)
    delta_emp = float((e1 - e2).mean())
    delta_equo = float((inf.crps_equo(e1, d1, m)
                        - inf.crps_equo(e2, d2, m)).mean())
    assert abs(delta_equo - delta_emp) < 5e-4


# --------------------------------------------------------------------------
# rumore Monte Carlo
# --------------------------------------------------------------------------

def test_con_un_solo_seme_il_rumore_monte_carlo_non_e_misurabile():
    """Una sola esecuzione non puo' misurare la propria varianza: dichiararlo
    e' l'unica risposta onesta."""
    r = inf.rumore_monte_carlo([0.05])
    assert r["repliche"] == 1
    assert not r["soddisfatto"]
    assert np.isnan(r["es_mc"])


def test_il_requisito_sul_rumore_e_una_soglia_dichiarata_prima():
    """`es_mc <= |differenza| / 10`, con il numero di repliche necessarie
    quando non e' soddisfatto."""
    forte = inf.rumore_monte_carlo([0.500, 0.502, 0.498, 0.501,
                                    0.499, 0.503, 0.497, 0.500])
    assert forte["soddisfatto"]
    debole = inf.rumore_monte_carlo([0.003, -0.004, 0.010, -0.002,
                                     0.007, -0.008, 0.001, 0.006])
    assert not debole["soddisfatto"]
    assert debole["repliche_necessarie"] > 8


def test_una_differenza_dominata_dal_rumore_non_e_inconcludente():
    """Distinzione che il protocollo impone: «non misurabile con le risorse
    disponibili» non e' «inconcludente», e nessuna delle due e' «equivalenti»."""
    d, i1, i2 = _griglia(seme=99)
    iv = inf.intervallo_two_way(d, i1, i2)
    mc_rumoroso = inf.rumore_monte_carlo([0.003, -0.004, 0.010, -0.002,
                                          0.007, -0.008, 0.001, 0.006])
    assert inf.esito_confronto(iv, mc_rumoroso) == \
        "non misurabile con le risorse disponibili"


def test_contenere_lo_zero_non_diventa_equivalenza():
    """Senza una tolleranza dichiarata prima, «l'intervallo contiene lo zero»
    resta «differenza non rilevabile»: chiamarla equivalenza sarebbe la mossa
    vietata dal protocollo."""
    rng = np.random.default_rng(12)
    d = rng.normal(0.0, 1.0, 2000)
    ids1 = np.repeat(np.arange(40), 50)
    ids2 = np.tile(np.arange(50), 40)
    iv = inf.intervallo_two_way(d, ids1, ids2)
    mc_buono = inf.rumore_monte_carlo([0.5, 0.5, 0.5, 0.5])
    esito = inf.esito_confronto(iv, mc_buono,
                                {"negativa": "C1 migliore",
                                 "positiva": "I1 migliore"})
    assert esito in {"differenza non rilevabile", "C1 migliore", "I1 migliore"}
    if not iv.esclude_zero:
        assert esito == "differenza non rilevabile"
    assert "equival" not in esito


# --------------------------------------------------------------------------
# rilievi della verifica avversariale di R4
# --------------------------------------------------------------------------

def test_l_errore_standard_one_way_e_zero_non_nan_quando_i_grappoli_si_annullano():
    """Se dentro ogni grappolo i residui si annullano, l'errore standard di
    quella dimensione e' **zero**, e zero e' informativo: dice che dentro
    grappolo non resta niente. Restituire NaN cancellava la diagnosi proprio
    dove serviva di piu'."""
    a, b = 20, 30
    i = np.repeat(np.arange(a), b)
    j = np.tile(np.arange(b), a)
    d = ((-1.0) ** (i + j))
    iv = inf.intervallo_two_way(d, i, j)
    es = iv.diagnostica["errori_standard"]
    assert es["one_way_1"] == pytest.approx(0.0, abs=1e-12)
    assert es["one_way_2"] == pytest.approx(0.0, abs=1e-12)
    assert not np.isnan(es["one_way_1"])


def test_celle_ripetute_fermano_la_stima_invece_di_falsarla():
    """La formula sottrae la varianza sulle righe perche' l'intersezione dei
    due grappoli **e'** la singola riga. Se una cella comparisse due volte
    l'intersezione sarebbe piu' grossa, e il terzo termine sarebbe quello
    sbagliato: senza guardia usciva un numero plausibile e muto."""
    d = np.random.default_rng(1).normal(size=8)
    id_1 = np.array([0, 0, 1, 1, 2, 2, 3, 3])
    id_2 = np.array([0, 0, 1, 1, 2, 2, 3, 3])   # (id_1, id_2) ripetuta
    with pytest.raises(ValueError, match="non e' unica per riga"):
        inf.intervallo_two_way(d, id_1, id_2)
    # chi sa quello che fa puo' disattivarla, ma deve dirlo
    iv = inf.intervallo_two_way(d, id_1, id_2, verifica_celle_uniche=False)
    assert iv.n == 8


def test_senza_semi_l_esito_dichiara_che_il_rumore_non_e_misurato():
    """Con un solo seme il rumore Monte Carlo non e' stato guardato. L'etichetta
    deve dirlo, altrimenti «C1 migliore» si legge come se il rumore fosse stato
    misurato e trovato piccolo."""
    d, i1, i2 = _griglia(seme=42)
    d = d - 5.0                      # differenza grande, intervallo lontano da zero
    iv = inf.intervallo_two_way(d, i1, i2)
    assert iv.esclude_zero
    esito = inf.esito_confronto(iv, None, {"negativa": "C1 migliore"})
    assert esito.startswith("C1 migliore")
    assert inf.SENZA_MISURA in esito
    # con i semi misurati e il requisito soddisfatto, la coda sparisce
    mc = inf.rumore_monte_carlo([-5.0, -5.001, -4.999, -5.0002])
    assert inf.esito_confronto(iv, mc, {"negativa": "C1 migliore"}) == \
        "C1 migliore"


# --------------------------------------------------------------------------
# FASE 3: le ipotesi verificate invece che postulate
# --------------------------------------------------------------------------

def test_gli_scenari_del_generatore_sono_incorrelati():
    """L'ipotesi di Ferro, verificata sul percorso reale.

    Avevo scritto che gli scenari, condividendo lo stesso fit, sarebbero
    positivamente correlati, e quindi che la correzione equa fosse un limite
    inferiore. Non segue: condizionatamente a un fit fissato le estrazioni
    possono essere indipendenti, e qui lo sono, perche' `rng_di` lega il flusso
    allo scenario.

    Soglie dichiarate prima: la correlazione media deve stare entro 3 errori
    standard da zero, e la deviazione standard delle correlazioni entro il 20 %
    di quella attesa sotto indipendenza."""
    from fantabot.tabellino.generatore import rng_di
    S, N = 120, 200
    X = np.array([rng_di(20260907, s, "forze").standard_normal(N)
                  for s in range(S)])
    C = np.corrcoef(X)
    fuori = C[~np.eye(S, dtype=bool)]
    attesa = 1.0 / np.sqrt(N)
    es_media = attesa / np.sqrt(len(fuori))
    assert abs(float(fuori.mean())) < 3 * es_media, (
        f"correlazione media fra scenari {fuori.mean():+.5f}: non e' zero")
    assert abs(float(fuori.std()) - attesa) < 0.2 * attesa, (
        f"dispersione delle correlazioni {fuori.std():.5f} contro {attesa:.5f} "
        "attesa sotto indipendenza")


def test_il_criterio_in_vigore_degenera_vicino_allo_zero():
    """Il difetto misurato del criterio `es_mc <= |differenza| / 10`: quando la
    differenza tende a zero la soglia tende a zero, e nessuna quantita' di semi
    la soddisfa. Va conservato perche' i verdetti pubblicati sono stati letti
    con quello, ma il difetto va scritto, non nascosto."""
    quasi_nulla = [1e-6, -1e-6, 2e-6, -2e-6, 1e-6, -1e-6, 0.0, 1e-6]
    r = inf.rumore_monte_carlo(quasi_nulla)
    assert not r["soddisfatto"]
    assert r["repliche_necessarie"] > 1000, (
        "con differenza quasi nulla il criterio deve chiedere un numero "
        "proibitivo di repliche: e' il difetto da dichiarare")


def test_l_emendamento_prospettico_non_degenera():
    """Il criterio prospettico confronta il rumore con l'incertezza
    campionaria, non con l'effetto: una differenza nulla ma stimata con
    precisione lo soddisfa."""
    quasi_nulla = [1e-6, -1e-6, 2e-6, -2e-6, 1e-6, -1e-6, 0.0, 1e-6]
    r = inf.rumore_monte_carlo(quasi_nulla, es_campionario=0.03)
    assert r["soddisfatto_prospettico"], (
        "il criterio prospettico deve essere soddisfacibile anche a effetto "
        "nullo, altrimenti non corregge niente")
    assert r["quota_varianza_aggiunta"] < 0.01
    # e deve restare esigente quando il rumore e' davvero grande
    rumoroso = inf.rumore_monte_carlo([0.5, -0.4, 0.6, -0.3],
                                      es_campionario=0.03)
    assert not rumoroso["soddisfatto_prospettico"]


def test_l_emendamento_non_cambia_il_criterio_in_vigore():
    """L'emendamento e' prospettico: aggiunge campi, non riscrive l'esito dei
    verdetti gia' pubblicati."""
    serie = [0.10, 0.11, 0.09, 0.10]
    senza = inf.rumore_monte_carlo(serie)
    con = inf.rumore_monte_carlo(serie, es_campionario=0.02)
    assert con["soddisfatto"] == senza["soddisfatto"]
    assert con["es_mc"] == senza["es_mc"]
    assert "soddisfatto_prospettico" in con
    assert "soddisfatto_prospettico" not in senza
