"""Adattatore delle presenze: universo completo, zero valido, cold start.

Difetti riprodotti prima della correzione, sul banco:

- l'aggiornamento scorreva solo i giocatori con voti precedenti: **264**
  ignorati nel 2024-25 e **219** nel 2025-26, con somma delle probabilità
  previste 70,33 e 56,10 sostituita da un ripiego di 0,5 ciascuno (132,0 e
  109,5);
- il filtro `if q and q.get("pres")` scartava anche le previsioni di **zero**:
  38 nel 2024-25, 29 nel 2025-26;
- `partecipazione.stima` salta il bersaglio per chi non è in `prop_conv`: 136
  giocatori su 587 nel 2026-27.
"""
import json
import sys
from pathlib import Path

import pandas as pd
import pytest

RADICE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RADICE / "src"))

from fantabot.tabellino import presenze as pz            # noqa: E402


@pytest.fixture
def predizioni(tmp_path):
    """Quattro giocatori: uno normale, uno a zero, uno alto, uno assente."""
    d = {
        "1": {"pres": 30.0, "value": 100.0},
        "2": {"pres": 0.0, "value": 5.0},        # zero: informazione, non buco
        "3": {"pres": 37.0, "value": 200.0},
        # il 4 non c'è: dovrà ricevere un prior, non essere saltato
    }
    p = tmp_path / "b_predictions_prova.json"
    p.write_text(json.dumps(d), encoding="utf-8")
    return p


@pytest.fixture
def storia():
    """Storia minima per il prior di ruolo: due giocatori per ruolo."""
    righe = []
    for pid, r, voti in [(10, "P", 8), (11, "P", 2),
                         (12, "A", 6), (13, "A", 4)]:
        for i in range(10):
            righe.append({"master_id": pid, "ruolo": r,
                          "stato_voto": "con_voto" if i < voti else "nessuna_riga"})
    return pd.DataFrame(righe)


RUOLI = {1: "A", 2: "A", 3: "P", 4: "A", 10: "P", 11: "P", 12: "A", 13: "A"}


def test_l_universo_completo_riceve_un_bersaglio(predizioni, storia):
    """Nessun giocatore dell'universo resta senza: era il difetto principale."""
    b = pz.costruisci(predizioni, [1, 2, 3, 4], RUOLI, storia_voti=storia)
    assert set(b.per_giocatore) == {1, 2, 3, 4}
    assert b.diagnostica["universo"] == 4
    assert b.diagnostica["con_bersaglio"] == 4


def test_una_previsione_di_zero_e_tenuta_non_scartata(predizioni, storia):
    """`if q.get("pres")` è falso per 0.0: quel filtro buttava informazione."""
    b = pz.costruisci(predizioni, [1, 2, 3], RUOLI, storia_voti=storia)
    assert b.per_giocatore[2] == 0.0
    assert b.fonte[2] == pz.FONTE_PREVISIONE
    assert b.diagnostica["previsioni_zero_tenute"] == 1


def test_chi_non_ha_previsione_riceve_un_prior_dichiarato(predizioni, storia):
    """Non 0,5 fisso: il tasso del ruolo, calcolato sui dati ammessi."""
    b = pz.costruisci(predizioni, [1, 4], RUOLI, storia_voti=storia)
    assert b.fonte[4] == pz.FONTE_PRIOR_RUOLO
    # gli attaccanti della storia hanno 6 e 4 voti su 10: prior 0,5
    assert b.per_giocatore[4] == pytest.approx(0.5, abs=1e-9)
    assert b.diagnostica["prior_per_ruolo"]["A"] == pytest.approx(0.5, abs=1e-9)


def test_senza_storia_non_si_inventa_un_prior(predizioni):
    """Quando non c'è niente su cui basarsi, il giocatore è dichiarato assente
    invece di ricevere un numero di comodo."""
    b = pz.costruisci(predizioni, [1, 4], RUOLI, storia_voti=None)
    assert 4 not in b.per_giocatore
    assert b.fonte[4] == pz.FONTE_ASSENTE
    assert b.diagnostica["senza_prior_ne_previsione"] == 1


def test_la_divisione_e_per_38_solo_a_stagione_intera(predizioni, storia):
    """`pres` è la somma di presenze fatte e previste per il resto."""
    b = pz.costruisci(predizioni, [1], RUOLI, storia_voti=storia)
    assert b.per_giocatore[1] == pytest.approx(30.0 / 38, abs=1e-9)


def test_dopo_k_turni_serve_il_contratto_del_residuo(predizioni, storia):
    """Con 6 presenze già fatte e 19 giornate residue, il tasso del resto è
    (30 - 6) / 19, non 30 / 38."""
    b = pz.costruisci(predizioni, [1], RUOLI, storia_voti=storia,
                      giornate_residue=19, presenze_gia_fatte={1: 6.0})
    assert b.per_giocatore[1] == pytest.approx(24.0 / 19, abs=1e-9) or \
        b.per_giocatore[1] == 1.0
    # 24/19 supera 1: va troncato e contato, non lasciato passare
    assert b.per_giocatore[1] <= 1.0
    assert b.diagnostica["probabilita_oltre_uno_troncate"] == 1


def test_un_residuo_negativo_e_azzerato_e_contato(predizioni, storia):
    """Se le presenze già fatte superano la previsione totale, il resto è zero:
    non un numero negativo che poi diventa una probabilità assurda."""
    b = pz.costruisci(predizioni, [1], RUOLI, storia_voti=storia,
                      giornate_residue=10, presenze_gia_fatte={1: 35.0})
    assert b.per_giocatore[1] == 0.0
    assert b.diagnostica["residuo_negativo_azzerato"] == 1


def test_le_giornate_residue_possono_variare_per_giocatore(predizioni, storia):
    """I rinvii rendono il numero di partite ancora da giocare diverso fra
    squadre: il contratto deve poterlo esprimere."""
    b = pz.costruisci(predizioni, [1, 3], RUOLI, storia_voti=storia,
                      giornate_residue={1: 19, 3: 20},
                      presenze_gia_fatte={1: 15.0, 3: 18.0})
    assert b.orizzonte[1] == 19 and b.orizzonte[3] == 20
    assert b.per_giocatore[1] == pytest.approx(15.0 / 19, abs=1e-9)
    assert b.per_giocatore[3] == pytest.approx(19.0 / 20, abs=1e-9)


def test_la_provenienza_di_ogni_bersaglio_e_dichiarata(predizioni, storia):
    b = pz.costruisci(predizioni, [1, 2, 3, 4], RUOLI, storia_voti=storia)
    assert b.diagnostica["per_fonte"][pz.FONTE_PREVISIONE] == 3
    assert b.diagnostica["per_fonte"][pz.FONTE_PRIOR_RUOLO] == 1
    assert set(b.fonte.values()) <= {pz.FONTE_PREVISIONE, pz.FONTE_PRIOR_RUOLO,
                                     pz.FONTE_ASSENTE}


def test_la_copertura_si_legge_per_ruolo_e_per_nuovi(predizioni, storia):
    """Il totale vicino al vero non basta: gli stessi totali possono nascondere
    giocatori completamente sbagliati."""
    b = pz.costruisci(predizioni, [1, 2, 3, 4], RUOLI, storia_voti=storia)
    t = pz.copertura(b, RUOLI, nuovi={4})
    assert not t.empty
    assert set(t.columns) >= {"ruolo", "nuovo", "fonte", "giocatori"}
    nuovi = t[t.nuovo]
    assert len(nuovi) == 1 and nuovi.iloc[0]["fonte"] == pz.FONTE_PRIOR_RUOLO


def test_solo_previsti_separa_le_due_fonti(predizioni, storia):
    """Chi vuole solo i bersagli che vengono da una previsione deve poterlo
    chiedere: mescolare previsione e prior in un unico dizionario nasconde
    quanto si sta inventando."""
    b = pz.costruisci(predizioni, [1, 2, 3, 4], RUOLI, storia_voti=storia)
    assert set(b.solo_previsti()) == {1, 2, 3}
