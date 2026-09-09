"""Prova del percorso dei dati per il banco del Livello 2.

Il banco dichiarava di confrontare il cubo e il vecchio simulatore «a parità di
presenze». Non era vero: in `scripts/l2_banco_confronto.py` il braccio `B'`
riceve le presenze del modello valore attraverso `storia_pres`, mentre il cubo
`C` è costruito con `pa.stima(Ppre)`, e quelle predizioni non gli arrivano
lungo quel percorso. Il verdetto costruito su quell'etichetta è invalidato
(vedi `reports/PROTOCOLLO_v2.md` §3).

La regola scritta nel protocollo: **perturbare l'input delle presenze deve
cambiare i bracci che dichiarano di usarlo, e non gli altri.**

Attenzione a come si legge questa regola sul cubo. L'allocazione dei posti è
accoppiata fra compagni: gli undici titolari sono undici, e alzare la
propensione di un giocatore riduce lo spazio per gli altri del suo reparto.
Quindi non si può pretendere che gli altri giocatori abbiano output identici —
sarebbe pretendere che il modello ignori i propri vincoli. Quello che deve
restare invariato è **l'input esogeno non modificato** e i **bracci che quel
segnale non lo usano**.
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

RADICE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RADICE / "src"))

from fantabot.tabellino import partecipazione as pa      # noqa: E402

GIORNATE = 38


def _panel_finto(n_giocatori=44, n_giornate=12, seme=0):
    """Panel minimo con le colonne che `partecipazione.stima` richiede.

    Due squadre, undici titolari e undici di panchina ciascuna, in modo che i
    moduli osservati siano legali e la catena di convocazione abbia dati.
    """
    rng = np.random.default_rng(seme)
    ruoli = (["P"] * 2 + ["D"] * 8 + ["C"] * 8 + ["A"] * 4) * 2
    squadre = ["Alfa"] * 22 + ["Beta"] * 22
    # undici titolari per squadra in modulo 3-4-3: un portiere, tre difensori,
    # quattro centrocampisti, tre attaccanti. Gli indici sono quelli dentro la
    # squadra, cioe' `i % 22`.
    TITOLARI = {0} | {2, 3, 4} | {10, 11, 12, 13} | {18, 19, 20}
    righe = []
    for g in range(1, n_giornate + 1):
        for i in range(n_giocatori):
            r = ruoli[i]
            sq = squadre[i]
            titolare = (i % 22) in TITOLARI
            gioca = titolare or rng.random() < 0.25
            stato = ("titolare" if titolare
                     else ("panchina_entrato" if gioca else "panchina_non_entrato"))
            righe.append({
                "master_id": i,
                "stagione": "2024-25",
                "giornata": g,
                "data": pd.Timestamp("2024-08-17") + pd.Timedelta(days=7 * g),
                "squadra_alla_data": sq,
                "ruolo": r,
                "stato_convocazione": stato,
                "stato_voto": "con_voto" if gioca else "nessuna_riga",
                "eleggibile": True,
                "minuti": 90 if titolare else (20 if gioca else 0),
                "fantavoto": 6.0,
                "voto": 6.0,
            })
    return pd.DataFrame(righe)


def test_il_panel_finto_e_utilizzabile():
    """Guardia: se la fixture non regge, gli altri test non dicono niente."""
    panel = _panel_finto()
    mod = pa.stima(panel, as_of="2025-06-30", min_partite=2)
    assert len(mod.prop_convocato) == 44
    assert mod.moduli, "nessun modulo osservato: la fixture non è legale"
    assert all(0.0 <= v <= 1.0 for v in mod.prop_convocato.values())


def test_un_bersaglio_esterno_abbassa_le_propensioni_dei_giocatori_bersagliati():
    """Il cubo deve poter ricevere le presenze del modello valore.

    Senza questa interfaccia il braccio `C1` del banco fattoriale non esiste, e
    il confronto «a parità di presenze» non è realizzabile.
    """
    panel = _panel_finto()
    base = pa.stima(panel, as_of="2025-06-30", min_partite=2)
    scelti = list(base.prop_convocato)[:10]
    bersaglio = {pid: 0.05 for pid in scelti}
    basso = pa.stima(panel, as_of="2025-06-30", min_partite=2,
                     bersaglio_presenza=bersaglio)
    for pid in scelti:
        assert basso.prop_convocato[pid] < base.prop_convocato[pid], (
            f"giocatore {pid}: bersaglio 0,05 ma la propensione non scende "
            f"({base.prop_convocato[pid]:.4f} → {basso.prop_convocato[pid]:.4f})")


def test_un_bersaglio_alto_alza_le_propensioni():
    """Controllo di direzione opposto: se scendesse in entrambi i casi, il
    collegamento starebbe facendo qualcosa di diverso da quel che dice."""
    panel = _panel_finto()
    base = pa.stima(panel, as_of="2025-06-30", min_partite=2)
    # un giocatore di panchina, che ha propensione bassa nel panel
    scelti = [pid for pid in base.prop_convocato
              if base.prop_convocato[pid] < 0.5][:5]
    if not scelti:
        pytest.skip("nessun giocatore con propensione bassa nella fixture")
    alto = pa.stima(panel, as_of="2025-06-30", min_partite=2,
                    bersaglio_presenza={pid: 0.95 for pid in scelti})
    for pid in scelti:
        assert alto.prop_convocato[pid] > base.prop_convocato[pid], (
            f"giocatore {pid}: bersaglio 0,95 ma la propensione non sale")


def test_il_bersaglio_non_tocca_l_input_dei_giocatori_non_bersagliati():
    """Quello che deve restare invariato è l'**input**, non l'esito simulato.

    L'allocazione dei posti è accoppiata: undici titolari restano undici, e
    alzare un giocatore toglie spazio ai compagni. Pretendere output identici
    per gli altri sarebbe pretendere che il modello ignori i suoi vincoli.
    Qui si verifica che la propensione stimata dal panel, per chi non ha
    bersaglio, non venga toccata dal collegamento.
    """
    panel = _panel_finto()
    base = pa.stima(panel, as_of="2025-06-30", min_partite=2)
    scelti = list(base.prop_convocato)[:10]
    con = pa.stima(panel, as_of="2025-06-30", min_partite=2,
                   bersaglio_presenza={pid: 0.05 for pid in scelti})
    intatti = [pid for pid in base.prop_convocato if pid not in scelti]
    for pid in intatti:
        assert con.prop_convocato[pid] == pytest.approx(
            base.prop_convocato[pid]), (
            f"giocatore {pid} non ha bersaglio ma la sua propensione è cambiata")


def test_peso_zero_lascia_tutto_come_prima():
    """`peso_bersaglio = 0` deve ridare esattamente il modello senza bersaglio:
    è il braccio di controllo del confronto fattoriale."""
    panel = _panel_finto()
    base = pa.stima(panel, as_of="2025-06-30", min_partite=2)
    zero = pa.stima(panel, as_of="2025-06-30", min_partite=2,
                    bersaglio_presenza={pid: 0.05
                                        for pid in list(base.prop_convocato)[:10]},
                    peso_bersaglio=0.0)
    for pid in base.prop_convocato:
        assert zero.prop_convocato[pid] == pytest.approx(
            base.prop_convocato[pid]), f"peso zero ha cambiato il giocatore {pid}"


def test_la_traduzione_da_presenza_a_voto_a_convocazione_e_dichiarata():
    """Il bersaglio è una presenza a voto, la propensione è di convocazione.

    Le due cose non sono la stessa: la catena passa da convocazione a
    titolarità a ingresso a voto. La conversione deve esserci ed essere
    documentata nella diagnostica, non nascosta in un'assegnazione diretta.
    """
    panel = _panel_finto()
    mod = pa.stima(panel, as_of="2025-06-30", min_partite=2,
                   bersaglio_presenza={0: 0.4, 1: 0.4})
    d = mod.diagnostica.get("bersaglio_presenza")
    assert d is not None, "la diagnostica non dichiara il bersaglio"
    assert d["applicati"] == 2
    assert d["quota_voto_per_ruolo"], "manca la quota di conversione per ruolo"
    # con una quota di conversione minore di 1, la convocazione richiesta deve
    # essere maggiore della presenza a voto voluta
    assert mod.prop_convocato[0] > 0.4


def test_un_giocatore_senza_storia_ma_col_ruolo_viene_iniziato():
    """Il cold start si risolve, non si salta.

    Prima un bersaglio su un giocatore assente dal panel veniva scartato:
    misurato sul 2026-27, 136 su 587. Con il ruolo si sa quale quota di
    conversione applicare, quindi il giocatore si puo' inizializzare, e il
    fatto che sia stato iniziato cosi' viene contato.
    """
    panel = _panel_finto()
    mod = pa.stima(panel, as_of="2025-06-30", min_partite=2,
                   bersaglio_presenza={0: 0.4, 99999: 0.9},
                   ruolo_esterno={99999: "A"})
    d = mod.diagnostica["bersaglio_presenza"]
    assert d["iniziati_senza_storia"] == 1
    assert d["saltati_senza_ruolo"] == 0
    assert 99999 in mod.prop_convocato
    assert mod.ruolo.get(99999) == "A"


def test_senza_ruolo_ne_storia_il_bersaglio_e_saltato_e_contato():
    """L'unico caso in cui saltare e' onesto: non si sa nemmeno che ruolo ha,
    quindi non si puo' scegliere la quota di conversione."""
    panel = _panel_finto()
    mod = pa.stima(panel, as_of="2025-06-30", min_partite=2,
                   bersaglio_presenza={0: 0.4, 99999: 0.9})
    d = mod.diagnostica["bersaglio_presenza"]
    assert d["saltati_senza_ruolo"] == 1
    assert 99999 not in mod.prop_convocato
