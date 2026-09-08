"""Prova del percorso dei dati per il banco del Livello 2.

Il banco dichiarava di confrontare il cubo e il vecchio simulatore «a parità di
presenze». Non era vero: in `scripts/l2_banco_confronto.py` il braccio `B'`
riceve le presenze del modello valore attraverso `storia_pres`, mentre il cubo
`C` è costruito con `pa.stima(Ppre)`, e quelle predizioni non gli arrivano
lungo quel percorso. Il verdetto costruito su quell'etichetta è invalidato
(vedi `reports/PROTOCOLLO_v2.md` §3).

La regola scritta nel protocollo: **perturbare l'input delle presenze deve
cambiare i bracci che dichiarano di usarlo, e non gli altri.** Un braccio che
non reagisce alla perturbazione non stava usando quell'informazione.

Questi test realizzano quella regola. Sono scritti perché possano fallire: il
test sul cubo con presenze esterne fallisce finché `partecipazione.stima` non
accetta un bersaglio di presenza, ed è quello il punto.
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


def _tasso_presenza_voto(mod, panel):
    """Tasso di presenza a voto che il modello attribuisce a ogni giocatore.

    Non è la probabilità di convocazione: la catena passa da convocazione a
    titolarità a ingresso a voto. Qui si legge quello che il modello espone,
    che è il punto in cui un bersaglio esterno dovrebbe entrare.
    """
    return dict(mod.prop_convocato)


def test_il_panel_finto_e_utilizzabile():
    """Guardia: se la fixture non regge, gli altri test non dicono niente."""
    panel = _panel_finto()
    mod = pa.stima(panel, as_of="2025-06-30", min_partite=2)
    assert len(mod.prop_convocato) == 44
    assert mod.moduli, "nessun modulo osservato: la fixture non è legale"
    assert all(0.0 <= v <= 1.0 for v in mod.prop_convocato.values())


def test_il_modello_ignora_un_bersaglio_che_non_sa_ricevere():
    """Stato attuale, fissato come prova: non esiste un modo di passare al
    cubo le presenze del modello valore.

    Questo test **documenta il difetto**. Quando `stima` accetterà un
    bersaglio, va sostituito dal test successivo, che oggi fallisce.
    """
    panel = _panel_finto()
    with pytest.raises(TypeError):
        pa.stima(panel, as_of="2025-06-30", bersaglio_presenza={0: 0.9})


@pytest.mark.xfail(reason="`partecipazione.stima` non accetta ancora un "
                          "bersaglio di presenza: è il difetto da correggere",
                   strict=True)
def test_un_bersaglio_esterno_cambia_le_propensioni_del_cubo():
    """Quando il cubo riceve le presenze del modello valore, le sue
    propensioni devono cambiare — e cambiare nella direzione del bersaglio."""
    panel = _panel_finto()
    base = pa.stima(panel, as_of="2025-06-30", min_partite=2)
    bersaglio = {pid: 0.05 for pid in list(base.prop_convocato)[:10]}
    alto = pa.stima(panel, as_of="2025-06-30", min_partite=2,
                    bersaglio_presenza=bersaglio)
    for pid in bersaglio:
        assert alto.prop_convocato[pid] < base.prop_convocato[pid], (
            f"giocatore {pid}: bersaglio 0,05 ma la propensione non scende")
    intatti = [pid for pid in base.prop_convocato if pid not in bersaglio]
    for pid in intatti:
        assert alto.prop_convocato[pid] == pytest.approx(
            base.prop_convocato[pid]), (
            f"giocatore {pid} non ha bersaglio ma la sua propensione è cambiata")


@pytest.mark.xfail(reason="il banco fattoriale non esiste ancora",
                   strict=True)
def test_la_perturbazione_delle_presenze_tocca_solo_i_bracci_che_le_usano():
    """La prova di percorso richiesta dal protocollo §3.1.

    Con lo stesso seme e la stessa storia, cambiare `pres` deve cambiare i
    generatori che dichiarano di usarlo (`GEN-B1`, `GEN-C1`) e lasciare
    identici quelli che non lo usano (`GEN-A`, `GEN-B`).
    """
    from fantabot.tabellino import banco_fattoriale as bf   # noqa: F401
    raise AssertionError("da scrivere insieme al banco fattoriale")
