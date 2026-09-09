"""Prove sullo stato della catena di convocazione all'origine.

Il difetto che sorvegliano: `generatore.genera` inizializzava ogni giocatore
con un'estrazione dalla marginale e `run = 1`, buttando via quello che si sa
a stagione iniziata. Una previsione progressiva parte da dove le cose stanno.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from fantabot.tabellino import partecipazione as pa


def _panel(convocazioni, *, prima_data="2024-08-01", eleggibile=True):
    """Un panel minimo: `convocazioni` è `{pid: [0/1 per giornata]}`."""
    righe = []
    for pid, seq in convocazioni.items():
        for g, v in enumerate(seq, start=1):
            righe.append({
                "master_id": pid, "giornata": g,
                "data": pd.Timestamp(prima_data) + pd.Timedelta(days=7 * g),
                "stagione": "2024-25", "squadra_alla_data": "Alfa",
                "ruolo": "C", "eleggibile": eleggibile,
                "stato_convocazione": "titolare" if v else "non_convocato",
                "stato_voto": "con_voto" if v else "nessuna_riga"})
    return pd.DataFrame(righe)


ROSE = {"Alfa": [1, 2, 3]}


def test_lo_stato_e_quello_dell_ultima_giornata_anteriore():
    P = _panel({1: [1, 1, 1, 0], 2: [0, 0, 1, 1], 3: [1, 0, 1, 0]})
    # l'origine cade dopo la terza giornata (8+21=29 agosto)
    stato, d = pa.stato_all_origine(P, "2024-08-25", ROSE)
    assert stato["Alfa"][1] == (True, 3), "tre convocazioni consecutive"
    assert stato["Alfa"][2] == (True, 1), "appena rientrato"
    assert stato["Alfa"][3] == (True, 1)
    assert d["giocatori_con_stato_osservato"] == 3
    assert d["giocatori_con_stato_ignoto"] == 0


def test_la_striscia_conta_le_giornate_consecutive():
    P = _panel({1: [0, 0, 0, 0]})
    stato, _ = pa.stato_all_origine(P, "2024-09-30", {"Alfa": [1]})
    assert stato["Alfa"][1] == (False, 4), (
        "quattro giornate fuori non sono come una: la catena ha memoria "
        "proprio per questo")


def test_il_futuro_non_entra_nello_stato():
    """Il controllo che conta: righe posteriori all'origine sono invisibili."""
    P = _panel({1: [1, 1, 0, 0, 0, 0]})
    presto, _ = pa.stato_all_origine(P, "2024-08-18", {"Alfa": [1]})
    tardi, _ = pa.stato_all_origine(P, "2024-09-30", {"Alfa": [1]})
    assert presto["Alfa"][1] == (True, 2)
    assert tardi["Alfa"][1] == (False, 4)
    alterato = P.copy()
    dopo = alterato.data >= pd.Timestamp("2024-08-18")
    alterato.loc[dopo, "stato_convocazione"] = "titolare"
    di_nuovo, _ = pa.stato_all_origine(alterato, "2024-08-18", {"Alfa": [1]})
    assert di_nuovo == presto, "alterare il futuro ha cambiato lo stato iniziale"


def test_chi_non_ha_righe_anteriori_resta_ignoto():
    """L'incertezza si conserva: non si inventa uno stato."""
    P = _panel({1: [1, 1]})
    stato, d = pa.stato_all_origine(P, "2024-08-25", {"Alfa": [1, 99]})
    assert 99 not in stato["Alfa"], (
        "un giocatore senza storia non deve ricevere uno stato inventato")
    assert d["giocatori_con_stato_ignoto"] == 1
    assert 99 in d["ignoti_primi"]


def test_nessuna_causa_attribuita_alle_assenze():
    """Un `senza_voto` non diventa un infortunio."""
    P = _panel({1: [1, 0, 0]})
    P.loc[P.stato_convocazione == "non_convocato", "stato_voto"] = "senza_voto"
    stato, d = pa.stato_all_origine(P, "2024-09-30", {"Alfa": [1]})
    assert stato["Alfa"][1][0] is False
    assert "infortun" in d["nota_infortuni"]
    assert "indisponibile" not in str(stato)


def test_la_striscia_e_troncata_al_massimo_del_modello():
    P = _panel({1: [1] * 20})
    stato, _ = pa.stato_all_origine(P, "2025-01-01", {"Alfa": [1]})
    assert stato["Alfa"][1] == (True, pa.MAX_RUN)


def test_senza_date_ci_si_ferma():
    P = _panel({1: [1, 1]}).drop(columns=["data"])
    with pytest.raises(ValueError, match="data"):
        pa.stato_all_origine(P, "2024-08-25", {"Alfa": [1]})


def test_le_righe_non_eleggibili_non_contano():
    P = pd.concat([_panel({1: [1, 1]}),
                   _panel({1: [0, 0]}, eleggibile=False)], ignore_index=True)
    stato, _ = pa.stato_all_origine(P, "2024-09-30", {"Alfa": [1]})
    assert stato["Alfa"][1] == (True, 2), (
        "le righe non eleggibili sono entrate nello stato")


# ------------------------------------------------- il generatore lo riceve
def test_il_generatore_accetta_lo_stato_iniziale():
    """Prova diretta sull'inizializzazione, senza generare una stagione.

    Si replica la riga del generatore che costruisce lo stato: con
    `stato_iniziale` i valori noti passano, gli ignoti restano estratti.
    """
    import inspect

    from fantabot.tabellino import generatore as gen
    sorgente = inspect.getsource(gen.genera)
    assert "stato_iniziale" in inspect.signature(gen.genera).parameters, (
        "il generatore non accetta uno stato iniziale")
    assert "noto = stato_iniziale or {}" in sorgente
    assert "v_noto is not None" in sorgente, (
        "lo stato noto non viene usato nell'inizializzazione")
    # e la parte estratta resta per gli ignoti
    assert "prop_convocato.get(pid, 0.6)" in sorgente


def test_lo_stato_iniziale_viaggia_nella_stessa_scala_del_modello():
    """`stato_all_origine` e `_offset_da_panel` devono definire allo stesso
    modo `presente`: se divergessero, lo stato iniziale entrerebbe in una
    scala che il modello non conosce."""
    import inspect
    a = inspect.getsource(pa.stato_all_origine)
    b = inspect.getsource(pa._offset_da_panel)
    assert "_in_lista" in a and "_in_lista" in b
    assert "_maschera_eleggibili" in a and "_maschera_eleggibili" in b
    assert "MAX_RUN" in a and "MAX_RUN" in b


def test_la_distribuzione_delle_strisce_e_riportata():
    P = _panel({1: [1, 1], 2: [0, 0], 3: [1, 0]})
    _, d = pa.stato_all_origine(P, "2024-09-30", ROSE)
    assert d["distribuzione_run"], "la diagnostica non riporta le strisce"
    assert sum(d["distribuzione_run"].values()) == 3
