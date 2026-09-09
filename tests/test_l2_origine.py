"""Prove sul contratto delle previsioni per origine temporale.

Ogni prova qui corrisponde a un errore già commesso nel progetto: il filtro per
giornata invece che per data, l'orizzonte finto quando non restano partite, la
feature dichiarata disponibile senza prova, il file per stagione che si
sovrascrive.
"""
from __future__ import annotations

import json

import pandas as pd
import pytest

from fantabot.tabellino import origine as org


def _calendario():
    return pd.DataFrame([
        # giornata 1: due partite giocate, una rinviata senza data
        {"giornata": 1, "partita": "A-B", "data": "2024-08-18"},
        {"giornata": 1, "partita": "C-D", "data": "2024-08-18"},
        {"giornata": 1, "partita": "E-F", "data": None},
        # giornata 2: una giocata, una da giocare — la giornata e' a cavallo
        {"giornata": 2, "partita": "B-C", "data": "2024-08-25"},
        {"giornata": 2, "partita": "D-E", "data": "2024-09-03"},
        # giornata 3: tutta futura
        {"giornata": 3, "partita": "A-C", "data": "2024-09-10"},
    ])


# ------------------------------------------------------- stato delle partite
def test_il_confine_e_la_data_non_la_giornata():
    """Il difetto: filtrare per numero di giornata sposta di lato le partite
    di una giornata giocata in parte."""
    m = org.stato_partite(_calendario(), "2024-09-01")
    g2 = m[m.giornata == 2]
    assert set(g2.stato_rispetto_origine) == {org.OSSERVATA, org.RESIDUA}, (
        "la giornata 2 e' a cavallo dell'origine: filtrando per giornata "
        "sarebbe tutta da una parte sola")


def test_una_partita_senza_data_non_e_ne_osservata_ne_residua():
    m = org.stato_partite(_calendario(), "2024-09-01")
    riga = m[m.partita == "E-F"].iloc[0]
    assert riga.stato_rispetto_origine == org.RINVIATA_SENZA_DATA


def test_le_rinviate_si_contano_a_parte():
    c = org.partite_residue(_calendario(), "2024-09-01")
    assert c == {"osservate": 3, "residue": 2, "rinviate_senza_data": 1}
    assert c["osservate"] + c["residue"] != len(_calendario()), (
        "se tornassero tutte in uno dei due gruppi, la rinviata sarebbe stata "
        "data per giocata o per giocabile senza dirlo")


def test_il_conteggio_per_chiave():
    c = org.partite_residue(_calendario(), "2024-09-01", per="giornata")
    assert c[1]["osservate"] == 2 and c[1]["rinviate_senza_data"] == 1
    assert c[2] == {"osservate": 1, "residue": 1, "rinviate_senza_data": 0}
    assert c[3]["residue"] == 1


def test_senza_colonna_data_ci_si_ferma():
    senza = _calendario().drop(columns=["data"])
    with pytest.raises(org.ContrattoViolato, match="data"):
        org.stato_partite(senza, "2024-09-01")


# ------------------------------------------------------------- orizzonte
def test_zero_partite_residue_non_diventa_un_turno_finto():
    """Alzare l'orizzonte a 1 per non dividere per zero fabbrica un turno."""
    with pytest.raises(org.ContrattoViolato, match="zero partite residue"):
        org.orizzonte(0)


def test_il_turno_finto_si_puo_chiedere_ma_va_chiesto():
    assert org.orizzonte(0, minimo_finto=True) == 1
    assert org.orizzonte(7) == 7


def test_residue_negative_sono_un_errore():
    with pytest.raises(org.ContrattoViolato):
        org.orizzonte(-1)


# -------------------------------------------------------------- ingressi
def test_disponibile_senza_prova_e_rifiutato():
    with pytest.raises(org.ContrattoViolato, match="senza prova"):
        org.Ingresso(nome="quot_fs_sett", stato=org.DISPONIBILE)


def test_disponibile_con_prova_passa():
    i = org.Ingresso(nome="voti_storici", stato=org.DISPONIBILE,
                     prova="righe del panel con data < origine, verificato in "
                           "test_il_produttore_usa_solo_le_righe_anteriori",
                     fonte="l2_panel.parquet")
    assert i.utilizzabile()


def test_ricostruito_e_non_verificabile_non_sono_utilizzabili():
    a = org.Ingresso(nome="x", stato=org.RICOSTRUITO, prova="ricostruito oggi")
    b = org.Ingresso(nome="y", stato=org.NON_VERIFICABILE)
    assert not a.utilizzabile() and not b.utilizzabile()


def test_stato_sconosciuto_rifiutato():
    with pytest.raises(org.ContrattoViolato, match="sconosciuto"):
        org.Ingresso(nome="x", stato="quasi_disponibile")


# -------------------------------------------------------------- manifesto
def _manifesto(**cambi):
    base = dict(
        stagione="2024-25", origine="2024-09-01", universo=[1, 2, 3],
        calendario_osservate=3, calendario_residue=2,
        calendario_rinviate_senza_data=1,
        etichette_dal="2021-08-01", etichette_fino_a="2024-08-31",
        ingressi=[org.Ingresso(nome="voti", stato=org.DISPONIBILE,
                               prova="panel con data < origine")],
        modello="presenze", versione_modello="v1",
        impronte={"panel": "abc123"},
        provenienza_temporale="date effettive del calendario")
    base.update(cambi)
    return org.ManifestoOrigine(**base)


def test_le_etichette_non_possono_superare_l_origine():
    with pytest.raises(org.ContrattoViolato, match="oltre l'origine"):
        _manifesto(etichette_fino_a="2024-09-15")


def test_un_ingresso_posteriore_invalida_il_manifesto():
    with pytest.raises(org.ContrattoViolato, match="posteriori"):
        _manifesto(ingressi=[org.Ingresso(nome="quot_fs_sett",
                                          stato=org.POSTERIORE)])


def test_universo_vuoto_rifiutato():
    with pytest.raises(org.ContrattoViolato, match="universo"):
        _manifesto(universo=[])


def test_operativo_solo_se_ogni_ingresso_e_dimostrato():
    assert _manifesto().utilizzabile_operativamente
    misto = _manifesto(ingressi=[
        org.Ingresso(nome="voti", stato=org.DISPONIBILE, prova="panel"),
        org.Ingresso(nome="quot_fs_sett", stato=org.RICOSTRUITO,
                     prova="ricavata oggi dal file corrente, senza storia")])
    assert not misto.utilizzabile_operativamente, (
        "un ingresso ricostruito non rende operativa la previsione: la rende "
        "un esperimento retrospettivo dichiarato")
    assert misto.ingressi_per_stato()[org.RICOSTRUITO] == ["quot_fs_sett"]


def test_l_identificativo_separa_le_origini():
    """Il difetto: un solo file per stagione, sovrascritto a ogni rigenerazione."""
    a = _manifesto(origine="2024-09-01", etichette_fino_a="2024-08-31")
    b = _manifesto(origine="2024-10-01", etichette_fino_a="2024-09-30")
    assert a.identificativo() != b.identificativo()
    assert "origine20240901" in a.identificativo()


def test_l_identificativo_cambia_col_modello():
    a = _manifesto(versione_modello="v1")
    b = _manifesto(versione_modello="v2")
    assert a.identificativo() != b.identificativo()


def test_scrittura_e_rilettura(tmp_path):
    m = _manifesto()
    p = m.scrivi(tmp_path)
    letto = org.leggi_manifesto(p)
    assert letto["stagione"] == "2024-25"
    assert letto["utilizzabile_operativamente"] is True
    assert letto["identificativo"] == m.identificativo()


def test_manifesto_incompleto_rifiutato(tmp_path):
    p = tmp_path / "manifesto_origine.json"
    p.write_text(json.dumps({"stagione": "2024-25"}), encoding="utf-8")
    with pytest.raises(org.ContrattoViolato, match="incompleto"):
        org.leggi_manifesto(p)
