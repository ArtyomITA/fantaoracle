"""Prove sulla procedura unica di costruzione del modello di partita.

Che cosa fissano questi test, in ordine di importanza:

  1. **Identita'** (criterio 3.3 di `reports/CRITERI_L2_L3.md`): a parita' di
     dati, data limite e configurazione, due costruzioni successive danno
     intensita' che coincidono entro 1e-9 e la stessa impronta. E' la proprieta'
     per cui banco e generatore possono dichiararsi d'accordo.
  2. **Sensibilita' dell'impronta**: cambiare un iperparametro cambia
     l'impronta. Un'impronta che non cambiasse sarebbe peggio che non averla:
     certificherebbe un'uguaglianza falsa.
  3. **Filtro temporale**: nessuna informazione a partire dalla data limite
     entra nell'addestramento, e una partita con calcio d'inizio anteriore ma
     senza risultato resta fuori. Il codice deve comportarsi allo stesso modo
     con e senza la colonna `stato_partita`, che sta per essere aggiunta.
  4. **Ammissibilita'**: `verifica_ammissibilita` riconosce un `rho` fuori
     dall'intervallo e misura la massa di coda troncata.

I dati sono sintetici e piccoli, cosi' i test restano veloci; c'e' in fondo una
prova sui dati veri, che viene saltata se il parquet non e' disponibile.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from fantabot.tabellino import configurazione as cfg          # noqa: E402
from fantabot.tabellino.partita import stima                   # noqa: E402

SQUADRE = ["Alfa", "Beta", "Gamma", "Delta", "Epsilon", "Zeta", "Eta", "Theta"]
STAGIONI = ["2020-21", "2021-22", "2022-23"]


def campionato(seed: int = 7) -> pd.DataFrame:
    """Tre stagioni sintetiche di girone doppio fra otto squadre.

    Le forze sono fisse e i gol estratti da Poisson con un generatore a seme
    fissato: il campionato e' lo stesso a ogni esecuzione, quindi i test non
    dipendono dal caso."""
    rng = np.random.default_rng(seed)
    forza = {s: 0.25 * (i - 3.5) / 3.5 for i, s in enumerate(SQUADRE)}
    righe = []
    for k, st in enumerate(STAGIONI):
        giorno = np.datetime64(f"{2020 + k}-09-01")
        n = 0
        for casa in SQUADRE:
            for via in SQUADRE:
                if casa == via:
                    continue
                lam = float(np.exp(0.15 + 0.15 + forza[casa] - forza[via]))
                mu = float(np.exp(0.15 + forza[via] - forza[casa]))
                gc = int(rng.poisson(lam))
                gt = int(rng.poisson(mu))
                righe.append({
                    "stagione": st,
                    "giornata": n // 4 + 1,
                    "data": pd.Timestamp(giorno + np.timedelta64(3 * (n // 4), "D")),
                    "casa": casa, "trasferta": via,
                    "gol_casa": float(gc), "gol_trasferta": float(gt),
                    "xg_casa": float(gc) * 0.9 + 0.1 * lam,
                    "xg_trasferta": float(gt) * 0.9 + 0.1 * mu,
                    "giocata": 1,
                })
                n += 1
    return pd.DataFrame(righe)


AS_OF = "2022-09-01"          # inizio della terza stagione


# --------------------------------------------------------------------------
# 1. identita'
# --------------------------------------------------------------------------

def test_due_costruzioni_identiche():
    """Stessi ingressi due volte: intensita' entro 1e-9 e stessa impronta."""
    d = campionato()
    m1, c1, i1 = cfg.costruisci_modello_partita(d, AS_OF)
    m2, c2, i2 = cfg.costruisci_modello_partita(d, AS_OF)
    te = d[d.stagione == "2022-23"]
    l1 = np.concatenate(m1.intensita(te.casa.values, te.trasferta.values))
    l2 = np.concatenate(m2.intensita(te.casa.values, te.trasferta.values))
    assert np.max(np.abs(l1 - l2)) < 1e-9
    assert i1 == i2
    assert c1.a_dizionario() == c2.a_dizionario()


def test_ordine_delle_righe_sposta_meno_di_1e_9():
    """Le stesse partite in ordine diverso: intensita' entro la tolleranza.

    La somma in virgola mobile non e' associativa, quindi rimescolare le righe
    muove l'ottimo dell'ultimo bit e con lui i prior, che sono anch'essi stimati.
    Misurato: 4,4e-16 sul campionato sintetico, 1,8e-11 sui dati veri del
    2026-27 — sotto la tolleranza di 1e-9 del criterio 3.3, ma **non zero**.

    Conseguenza dichiarata: l'impronta lega il percorso numerico esatto, ordine
    delle righe compreso, e puo' quindi differire fra due tabelle con le stesse
    partite in ordine diverso. L'impronta del solo *contenuto* (`impronta_tabella`)
    e' invece indipendente dall'ordine, ed e' quella da confrontare per dire se
    due esecuzioni hanno visto gli stessi dati."""
    d = campionato()
    mescolato = d.sample(frac=1.0, random_state=3).reset_index(drop=True)
    m1, c1, _ = cfg.costruisci_modello_partita(d, AS_OF)
    m2, c2, _ = cfg.costruisci_modello_partita(mescolato, AS_OF)
    te = d[d.stagione == "2022-23"]
    l1 = np.concatenate(m1.intensita(te.casa.values, te.trasferta.values))
    l2 = np.concatenate(m2.intensita(te.casa.values, te.trasferta.values))
    assert np.max(np.abs(l1 - l2)) < 1e-9
    assert c1.iperparametri == c2.iperparametri
    assert (c1.impronte_ingressi["addestramento"]
            == c2.impronte_ingressi["addestramento"])


def test_configurazione_serializzabile_e_ricostruibile():
    d = campionato()
    _, conf, impronta = cfg.costruisci_modello_partita(d, AS_OF)
    import json
    testo = json.dumps(conf.a_dizionario(), sort_keys=True)
    rifatta = cfg.ConfigurazionePartita.da_dizionario(json.loads(testo))
    assert rifatta.impronta() == impronta


# --------------------------------------------------------------------------
# 2. sensibilita' dell'impronta
# --------------------------------------------------------------------------

def test_impronta_cambia_con_un_iperparametro():
    d = campionato()
    _, _, i1 = cfg.costruisci_modello_partita(
        d, AS_OF, cfg.Iperparametri(xi=0.0015, lam_pen=2.0))
    _, _, i2 = cfg.costruisci_modello_partita(
        d, AS_OF, cfg.Iperparametri(xi=0.003, lam_pen=2.0))
    _, _, i3 = cfg.costruisci_modello_partita(
        d, AS_OF, cfg.Iperparametri(xi=0.0015, lam_pen=5.0))
    _, _, i4 = cfg.costruisci_modello_partita(
        d, AS_OF, cfg.Iperparametri(xi=0.0015, lam_pen=2.0, prior_xg=False))
    assert len({i1, i2, i3, i4}) == 4


def test_impronta_cambia_con_i_dati():
    """Un gol diverso in una partita di addestramento cambia l'impronta."""
    d = campionato()
    _, _, i1 = cfg.costruisci_modello_partita(
        d, AS_OF, cfg.Iperparametri(xi=0.0015, lam_pen=2.0))
    d2 = d.copy()
    d2.loc[0, "gol_casa"] = d2.loc[0, "gol_casa"] + 1
    _, _, i2 = cfg.costruisci_modello_partita(
        d2, AS_OF, cfg.Iperparametri(xi=0.0015, lam_pen=2.0))
    assert i1 != i2


def test_impronta_tabella_indipendente_dall_ordine():
    d = campionato()
    a = cfg.impronta_tabella(d)
    b = cfg.impronta_tabella(d.sample(frac=1.0, random_state=11))
    assert a == b
    d2 = d.copy()
    d2.loc[5, "gol_trasferta"] = d2.loc[5, "gol_trasferta"] + 1
    assert cfg.impronta_tabella(d2) != a


# --------------------------------------------------------------------------
# 3. filtro temporale
# --------------------------------------------------------------------------

def test_nessuna_partita_dalla_data_limite_in_poi():
    d = campionato()
    tr, filtro = cfg.partite_di_addestramento(d, AS_OF)
    assert len(tr) > 0
    assert tr.data.max() < pd.Timestamp(AS_OF)
    assert filtro["colonna_stato"] == "giocata"


def test_partita_iniziata_senza_risultato_resta_fuori():
    """Il difetto 0.2 dei criteri: data anteriore ma risultato assente.

    Con `giocata` e con `stato_partita` il comportamento deve essere lo stesso:
    quella partita non entra nell'addestramento."""
    d = campionato()
    d.loc[0, ["gol_casa", "gol_trasferta"]] = [np.nan, np.nan]
    d.loc[0, "giocata"] = 0
    tr_senza, f1 = cfg.partite_di_addestramento(d, AS_OF)

    d2 = d.copy()
    d2["stato_partita"] = "conclusa"
    d2.loc[0, "stato_partita"] = "da_giocare"
    tr_con, f2 = cfg.partite_di_addestramento(d2, AS_OF)

    assert f1["colonna_stato"] == "giocata"
    assert f2["colonna_stato"] == "stato_partita"
    assert len(tr_senza) == len(tr_con)
    assert cfg.impronta_tabella(tr_senza, ["stagione", "data", "casa",
                                           "trasferta", "gol_casa",
                                           "gol_trasferta"]) == \
        cfg.impronta_tabella(tr_con, ["stagione", "data", "casa", "trasferta",
                                      "gol_casa", "gol_trasferta"])


def test_stato_partita_senza_voti_entra_lo_stesso():
    """`senza_voti` significa «giocata, voti non ancora acquisiti».

    Al modello di partita servono i gol, non i voti: quella partita e'
    informazione disponibile e deve entrare."""
    d = campionato()
    d["stato_partita"] = "conclusa"
    d.loc[3, "stato_partita"] = "senza_voti"
    tr, _ = cfg.partite_di_addestramento(d, AS_OF)
    prima = d[d.data < pd.Timestamp(AS_OF)]
    assert len(tr) == len(prima)


def test_stagione_di_validazione_e_quella_precedente():
    d = campionato()
    _, conf, _ = cfg.costruisci_modello_partita(d, AS_OF)
    assert conf.diagnostica["stagione_bersaglio"] == "2022-23"
    assert conf.origine_iperparametri["stagione_di_validazione"] == "2021-22"
    # nessuna partita della stagione bersaglio nell'addestramento
    assert conf.n_partite_addestramento == 2 * len(SQUADRE) * (len(SQUADRE) - 1)


def test_iperparametri_forniti_saltano_la_ricerca():
    d = campionato()
    _, conf, _ = cfg.costruisci_modello_partita(
        d, AS_OF, {"xi": 0.004, "lam_pen": 1.5})
    assert conf.origine_iperparametri["modo"] == "forniti"
    assert conf.iperparametri["xi"] == 0.004
    assert conf.iperparametri["lam_pen"] == 1.5


# --------------------------------------------------------------------------
# 4. ammissibilita'
# --------------------------------------------------------------------------

def test_verifica_ammissibilita_sul_modello_stimato():
    d = campionato()
    mod, conf, _ = cfg.costruisci_modello_partita(d, AS_OF)
    te = d[d.stagione == "2022-23"]
    v = cfg.verifica_ammissibilita(mod, te.casa.values, te.trasferta.values)
    assert v["ammissibile"]
    assert v["celle_tau_non_positive"] == 0
    assert v["tau_minimo"] > 0
    assert v["massa_coda_massima"] < 1e-3
    assert v["n_partite"] == len(te)


def test_verifica_ammissibilita_riconosce_rho_fuori_intervallo():
    """Un `rho` messo a mano oltre il bordo deve essere dichiarato inammissibile.

    E' il caso che `campiona_parametri` puo' produrre: estrae `rho` dalla
    normale approssimata senza vincoli, mentre la stima lo teneva dentro
    [-0,4; 0,4] e l'ammissibilita' dipende dalle intensita'."""
    d = campionato()
    mod, _, _ = cfg.costruisci_modello_partita(d, AS_OF)
    te = d[d.stagione == "2022-23"]
    lam, mu = mod.intensita(te.casa.values, te.trasferta.values)
    from fantabot.tabellino.partita import rho_ammissibile
    _, alto = rho_ammissibile(lam, mu)
    mod.rho = float(alto) + 0.01
    v = cfg.verifica_ammissibilita(mod, te.casa.values, te.trasferta.values)
    assert not v["ammissibile"]
    assert v["celle_tau_non_positive"] > 0
    assert v["tau_minimo"] <= 0


def test_massa_di_coda_cresce_con_le_intensita():
    """La coda troncata a MAX_GOL deve essere misurata, non supposta."""
    poca = cfg._massa_troncata(np.array([1.3]), np.array([1.1]), 12)
    tanta = cfg._massa_troncata(np.array([6.0]), np.array([6.0]), 12)
    assert poca[0] < 1e-7 < tanta[0]


def test_verifica_campioni_conta_i_rigetti():
    d = campionato()
    mod, _, _ = cfg.costruisci_modello_partita(
        d, AS_OF, cfg.Iperparametri(xi=0.0015, lam_pen=2.0),
        con_incertezza=True)
    te = d[d.stagione == "2022-23"]
    rng = np.random.default_rng(1234)
    r = cfg.verifica_campioni(mod, te.casa.values, te.trasferta.values, rng, 25)
    assert r["n_estrazioni"] == 25
    assert r["n_rigetti"] == len(r["indici_rigettati"])
    assert r["margine_rho_minimo"] <= r["margine_rho_medio"]
    # l'estrazione muove rho: se non lo muovesse non ci sarebbe niente da
    # verificare e questo test non proverebbe nulla
    assert r["rho_max"] > r["rho_min"]


# --------------------------------------------------------------------------
# 5. prova sui dati veri (saltata se mancano)
# --------------------------------------------------------------------------

PARTITE = ROOT / "data" / "processed" / "l2_partite.parquet"


@pytest.mark.skipif(not PARTITE.exists(), reason="parquet delle partite assente")
def test_identita_sui_dati_veri():
    """Criterio 3.3 sui dati che il cubo usa davvero: 2026-27, as_of 2026-09-11."""
    d = pd.read_parquet(PARTITE)
    m1, c1, i1 = cfg.costruisci_modello_partita(
        d, "2026-09-11", percorsi_ingresso=[PARTITE])
    m2, c2, i2 = cfg.costruisci_modello_partita(
        d, "2026-09-11", percorsi_ingresso=[PARTITE])
    cal = d[d.stagione == "2026-27"]
    l1 = np.concatenate(m1.intensita(cal.casa.values, cal.trasferta.values))
    l2 = np.concatenate(m2.intensita(cal.casa.values, cal.trasferta.values))
    assert np.max(np.abs(l1 - l2)) < 1e-9
    assert i1 == i2
    assert c1.diagnostica["ammissibilita"]["ammissibile"]
