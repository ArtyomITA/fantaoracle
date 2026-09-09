"""Prove sulla costruzione degli ingressi C2 e sul controfattuale.

Il difetto che queste prove sorvegliano: il controfattuale confrontava le
**somme** degli ingressi, e una somma non vede uno scambio fra giocatori. Una
prova che non distingue `{1: 0,9; 2: 0,1}` da `{1: 0,1; 2: 0,9}` non prova che
il futuro non sia entrato.
"""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

RADICE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RADICE / "src"))


def _carica(nome: str):
    spec = importlib.util.spec_from_file_location(
        nome, RADICE / "scripts" / f"{nome}.py")
    modulo = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = modulo
    spec.loader.exec_module(modulo)
    return modulo


pilota = _carica("l2_pilota_c2")
contro = _carica("l2_controfattuale_c2")


# --------------------------------------------------------------- differenze
def test_uno_scambio_fra_giocatori_e_visibile():
    """Il difetto riprodotto: la somma non lo vede, il confronto per id si'."""
    a = {"bersaglio": {1: 0.9, 2: 0.1}}
    b = {"bersaglio": {1: 0.1, 2: 0.9}}
    assert sum(a["bersaglio"].values()) == sum(b["bersaglio"].values()), (
        "il caso non e' quello giusto: le somme devono coincidere")
    d = contro.differenze(a, b)
    assert "bersaglio" in d, "lo scambio e' passato inosservato"
    assert d["bersaglio"]["voci_diverse"] == 2


def test_nessuna_differenza_quando_e_uguale():
    a = {"x": {1: 0.5}, "y": [1, 2, 3], "n": 7}
    assert contro.differenze(a, dict(a)) == {}


def test_le_liste_confrontano_gli_elementi_non_la_lunghezza():
    d = contro.differenze({"u": [1, 2, 3]}, {"u": [1, 2, 4]})
    assert d["u"]["voci_diverse"] == 2      # il 3 esce, il 4 entra
    assert d["u"]["lunghezza_prima"] == d["u"]["lunghezza_dopo"] == 3


# ------------------------------------------------------- perturbazioni vere
def _universo_finto(n=12):
    ruoli = ["P", "D", "C", "A"]
    squadre = ["Alfa", "Beta", "Gamma"]
    ruolo = {i: ruoli[i % 4] for i in range(1, n + 1)}
    squadra = {i: squadre[i % 3] for i in range(1, n + 1)}
    return (None, ruolo, squadra, None)


def test_ruotare_le_etichette_delle_squadre_non_cambia_la_partizione():
    """Perche' la vecchia perturbazione era inerte, e non per colpa dei dati.

    Ruotando i nomi, tutti i giocatori della squadra X finiscono insieme in Y:
    le celle `(squadra, ruolo)` restano le stesse. Il rimescolamento invece le
    cambia davvero.
    """
    u = _universo_finto()
    _, _, squadra, _ = u
    ruotata = {}
    nomi = sorted(set(squadra.values()))
    giro = {s: nomi[(i + 1) % len(nomi)] for i, s in enumerate(nomi)}
    for k, v in squadra.items():
        ruotata[k] = giro[v]

    def partizione(m):
        fuori = {}
        for k, v in m.items():
            fuori.setdefault(v, set()).add(k)
        return sorted(map(sorted, fuori.values()))

    assert partizione(squadra) == partizione(ruotata), (
        "la rotazione dovrebbe conservare i gruppi")
    _, _, mescolata, _ = contro._universo_con_squadre_mescolate(u)
    assert partizione(squadra) != partizione(mescolata), (
        "il rimescolamento deve cambiare i gruppi, altrimenti il controllo "
        "positivo non ha potenza")


def test_l_universo_ridotto_toglie_davvero_giocatori():
    u = _universo_finto(12)
    _, ruolo, squadra, _ = contro._universo_ridotto(u, quanti=4)
    assert len(ruolo) == 8 and len(squadra) == 8


def test_la_copertura_delle_predizioni_conta_solo_chi_ha_pres(tmp_path,
                                                              monkeypatch):
    dati = {"1": {"pres": 20.0}, "2": {"pres": None}, "3": {"altro": 1},
            "4": {"pres": 5.0}}
    (tmp_path / "b_predictions_2024-25.json").write_text(
        json.dumps(dati), encoding="utf-8")
    monkeypatch.setattr(contro, "PROC", tmp_path)
    cop = contro.copertura_predizioni("2024-25", [1, 2, 3, 4, 5])
    assert cop["universo"] == 5
    assert cop["con_previsione"] == 2      # solo 1 e 4
    assert cop["senza_previsione"] == 3
    assert cop["prior_attivo"] is True


def test_copertura_totale_spegne_il_prior(tmp_path, monkeypatch):
    """Il fatto misurato sul 2024-25: 679 su 679, quindi il bersaglio grezzo
    non tocca ne' la storia dei voti ne' la mappa dei ruoli."""
    (tmp_path / "b_predictions_2024-25.json").write_text(
        json.dumps({str(i): {"pres": 10.0} for i in range(1, 6)}),
        encoding="utf-8")
    monkeypatch.setattr(contro, "PROC", tmp_path)
    cop = contro.copertura_predizioni("2024-25", list(range(1, 6)))
    assert cop["prior_attivo"] is False


# ------------------------------------------------------------- IngressiC2
def test_ingressi_rifiuta_campi_mancanti():
    with pytest.raises(TypeError, match="mancanti"):
        pilota.IngressiC2(cutoff=None, stagione="2024-25")


def test_ingressi_rifiuta_campi_sconosciuti():
    completo = {c: None for c in pilota.IngressiC2.CAMPI}
    with pytest.raises(TypeError, match="sconosciuti"):
        pilota.IngressiC2(**completo, spurio=1)


# ------------------------------------------- il produttore, su dati sintetici
def _panel_finto(cutoff="2024-08-17", n=12, giornate=3):
    righe = []
    ruoli = ["P", "D", "C", "A"]
    squadre = ["Alfa", "Beta", "Gamma"]
    prima = pd.Timestamp(cutoff) - pd.Timedelta(days=30)
    dopo = pd.Timestamp(cutoff) + pd.Timedelta(days=30)
    for quando, stagione in ((prima, "2023-24"), (dopo, "2024-25")):
        for g in range(1, giornate + 1):
            for i in range(1, n + 1):
                righe.append({
                    "master_id": i, "data": quando + pd.Timedelta(days=g),
                    "stagione": stagione, "giornata": g,
                    "squadra_alla_data": squadre[i % 3], "ruolo": ruoli[i % 4],
                    "stato_voto": "con_voto" if i % 3 else "senza_voto",
                    "stato_convocazione": "convocato", "fantavoto": 6.0})
    return pd.DataFrame(righe)


def _predizioni_finte(cartella: Path, n=12, stagione="2024-25"):
    cartella.mkdir(parents=True, exist_ok=True)
    (cartella / f"b_predictions_{stagione}.json").write_text(
        json.dumps({str(i): {"pres": float(38 - i)} for i in range(1, n + 1)}),
        encoding="utf-8")
    return cartella


def test_il_produttore_usa_solo_le_righe_anteriori_al_cutoff(tmp_path):
    """Il controllo negativo, in piccolo: alterare il futuro non muove niente."""
    P = _panel_finto()
    proc = _predizioni_finte(tmp_path / "processed")
    u = _universo_finto()
    comune = dict(stagione="2024-25", cutoff="2024-08-17", proc=proc,
                  universo=u, n_squadre=1)
    base = pilota.costruisci_ingressi(P, **comune).vettori()

    futuro = P.copy()
    md = futuro.data >= pd.Timestamp("2024-08-17")
    futuro.loc[md, "stato_voto"] = "nessuna_riga"
    futuro.loc[md, "ruolo"] = "A"
    futuro.loc[md, "fantavoto"] = 99.0
    assert int(md.sum()) > 0, "il caso non altera niente"
    assert contro.differenze(base, pilota.costruisci_ingressi(
        futuro, **comune).vettori()) == {}


def test_il_produttore_reagisce_al_passato_pertinente(tmp_path):
    """Il controllo positivo: se non reagisse, il negativo non proverebbe niente."""
    P = _panel_finto()
    proc = _predizioni_finte(tmp_path / "processed")
    comune = dict(stagione="2024-25", cutoff="2024-08-17", proc=proc,
                  universo=_universo_finto(), n_squadre=1)
    base = pilota.costruisci_ingressi(P, **comune).vettori()
    passato = P.copy()
    mp = passato.data < pd.Timestamp("2024-08-17")
    passato.loc[mp, "stato_voto"] = "nessuna_riga"
    d = contro.differenze(base, pilota.costruisci_ingressi(
        passato, **comune).vettori())
    assert "somme_ruolo" in d or "quota_ruolo" in d, (
        f"il passato non muove niente: la prova non ha potenza. Mosse: {sorted(d)}")


def test_il_bersaglio_grezzo_segue_il_file_delle_predizioni(tmp_path):
    P = _panel_finto()
    proc = _predizioni_finte(tmp_path / "processed")
    comune = dict(stagione="2024-25", cutoff="2024-08-17", proc=proc,
                  universo=_universo_finto(), n_squadre=1)
    base = pilota.costruisci_ingressi(P, **comune).vettori()
    altro = tmp_path / "altro"
    altro.mkdir()
    (altro / "b_predictions_2024-25.json").write_text(
        json.dumps({str(i): {"pres": float(i)} for i in range(1, 13)}),
        encoding="utf-8")
    d = contro.differenze(base, pilota.costruisci_ingressi(
        P, **{**comune, "proc": altro}).vettori())
    assert d["bersaglio_grezzo"]["voci_diverse"] > 0


def test_i_vettori_sono_per_identificativo_non_per_somma(tmp_path):
    P = _panel_finto()
    proc = _predizioni_finte(tmp_path / "processed")
    v = pilota.costruisci_ingressi(
        P, stagione="2024-25", cutoff="2024-08-17", proc=proc,
        universo=_universo_finto(), n_squadre=1).vettori()
    assert isinstance(v["bersaglio_grezzo"], dict)
    assert all(isinstance(k, int) for k in v["bersaglio_grezzo"])
    assert set(v["bersaglio_grezzo"]) == set(v["universo"])
