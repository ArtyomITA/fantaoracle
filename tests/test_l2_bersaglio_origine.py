"""Prove sull'adattatore dal bersaglio per origine al bersaglio del cubo.

Il difetto che queste prove sorvegliano e' l'unita' di misura: il CSV per
origine dichiara le presenze **residue** su un orizzonte esplicito,
`presenze.costruisci` vuole la **somma** delle presenze piu' l'orizzonte a
parte. Chi confonde le due cose ottiene un bersaglio silenziosamente sbagliato,
e nessun controllo se ne accorge.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd
import pytest

RADICE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RADICE / "src"))

from fantabot.tabellino import bersaglio_origine as bo      # noqa: E402
from fantabot.tabellino import presenze                     # noqa: E402


def _csv(tmp_path: Path, righe) -> Path:
    p = tmp_path / "presenze_per_origine.csv"
    pd.DataFrame(righe).to_csv(p, index=False)
    return p


RIGHE = [
    # meta' delle giornate, stagione tutta futura: 19 / 38 = 0,5
    {"master_id": 1, "presenze_residue_attese": 19.0, "scarto_fra_semi": 0.1,
     "presenze_gia_fatte": 0.0, "orizzonte_giornate": 38},
    # a stagione iniziata: 10 residue su 20 giornate = 0,5, e le 8 gia' fatte
    # NON devono entrare nella probabilita'
    {"master_id": 2, "presenze_residue_attese": 10.0, "scarto_fra_semi": 0.2,
     "presenze_gia_fatte": 8.0, "orizzonte_giornate": 20},
    # richiesta impossibile: 25 su 20 giornate, si tronca a 1
    {"master_id": 3, "presenze_residue_attese": 25.0, "scarto_fra_semi": 0.3,
     "presenze_gia_fatte": 0.0, "orizzonte_giornate": 20},
    # zero e' un'informazione, non un dato mancante
    {"master_id": 4, "presenze_residue_attese": 0.0, "scarto_fra_semi": 0.0,
     "presenze_gia_fatte": 3.0, "orizzonte_giornate": 20},
]


def _storia() -> pd.DataFrame:
    """Storia sufficiente a far esistere un prior di ruolo non nullo."""
    righe = []
    for pid, quanti_voti in ((1, 8), (2, 6), (3, 4), (4, 2)):
        for k in range(10):
            righe.append({"master_id": pid,
                          "stato_voto": "con_voto" if k < quanti_voti
                          else "senza_voto"})
    return pd.DataFrame(righe)


RUOLO = {1: "P", 2: "D", 3: "C", 4: "A", 9: "D"}


# ------------------------------------------------------------- conversione
def test_la_somma_dichiarata_e_quella_ottenuta(tmp_path):
    c = bo.adatta(_csv(tmp_path, RIGHE), tmp_path / "fuori.json")
    d = c["diagnostica"]
    atteso = sum(r["presenze_residue_attese"] + r["presenze_gia_fatte"]
                 for r in RIGHE)
    assert d["somma_pres_dichiarata"] == pytest.approx(atteso)
    assert (d["somma_presenze_residue_attese"] + d["somma_presenze_gia_fatte"]
            == pytest.approx(d["somma_pres_dichiarata"]))
    scritto = json.loads((tmp_path / "fuori.json").read_text("utf-8"))
    assert scritto["2"]["pres"] == pytest.approx(18.0)      # 10 + 8
    assert c["giornate_residue"][2] == 20
    assert c["presenze_gia_fatte"][2] == pytest.approx(8.0)


def test_le_probabilita_sono_quelle_calcolate_a_mano(tmp_path):
    b = bo.costruisci_da_origine(_csv(tmp_path, RIGHE), [1, 2, 3, 4], RUOLO,
                                 storia_voti=_storia(),
                                 cartella_lavoro=tmp_path / "lavoro")
    assert b.per_giocatore[1] == pytest.approx(19.0 / 38)     # 0,5
    assert b.per_giocatore[2] == pytest.approx(10.0 / 20)     # 0,5, non 18/20
    assert b.per_giocatore[3] == pytest.approx(1.0)           # 25/20 troncato
    assert b.per_giocatore[4] == pytest.approx(0.0)           # zero tenuto
    assert all(f == presenze.FONTE_PREVISIONE for f in b.fonte.values())
    assert b.orizzonte[2] == 20
    assert b.diagnostica["bersaglio_origine"]["giocatori"] == 4


def test_confondere_le_unita_darebbe_un_altro_numero(tmp_path):
    """Controllo positivo: se l'adattatore passasse le sole residue come
    `pres`, il giocatore 2 varrebbe 0,1 invece di 0,5. La prova sopra non
    proverebbe niente senza questo confronto."""
    sbagliato = tmp_path / "sbagliato.json"
    sbagliato.write_text(json.dumps({"2": {"pres": 10.0}}), encoding="utf-8")
    b = presenze.costruisci(sbagliato, [2], RUOLO, storia_voti=_storia(),
                            presenze_gia_fatte={2: 8.0}, giornate_residue={2: 20})
    assert b.per_giocatore[2] == pytest.approx(0.1)
    assert b.per_giocatore[2] != pytest.approx(0.5)


def test_un_assente_finisce_nel_prior_di_ruolo_non_a_zero(tmp_path):
    b = bo.costruisci_da_origine(_csv(tmp_path, RIGHE), [1, 2, 3, 4, 9], RUOLO,
                                 storia_voti=_storia(),
                                 cartella_lavoro=tmp_path / "lavoro")
    assert b.fonte[9] == presenze.FONTE_PRIOR_RUOLO
    assert b.per_giocatore[9] > 0.0, "un assente azzerato e' il difetto"
    assert b.diagnostica["per_fonte"][presenze.FONTE_PRIOR_RUOLO] == 1


# ------------------------------------------------------------- il contratto
def test_una_colonna_mancante_e_un_errore_non_un_ripiego(tmp_path):
    righe = [{k: v for k, v in r.items() if k != "orizzonte_giornate"}
             for r in RIGHE]
    with pytest.raises(ValueError, match="colonne mancanti"):
        bo.carica(_csv(tmp_path, righe))


def test_orizzonte_nullo_rifiutato(tmp_path):
    righe = [dict(RIGHE[0], orizzonte_giornate=0)]
    with pytest.raises(ValueError, match="orizzonte_giornate"):
        bo.carica(_csv(tmp_path, righe))


def test_identificativi_ripetuti_rifiutati(tmp_path):
    with pytest.raises(ValueError, match="ripetuti"):
        bo.carica(_csv(tmp_path, RIGHE + [dict(RIGHE[0])]))


def test_file_assente_dichiarato(tmp_path):
    with pytest.raises(FileNotFoundError):
        bo.carica(tmp_path / "non_c_e.csv")


def test_l_artefatto_vero_rispetta_il_contratto():
    """Sul CSV per origine davvero su disco, se c'e': il contratto non e' una
    congettura sui nomi delle colonne."""
    c = RADICE / "data" / "l1" / "presenze"
    trovati = sorted(c.glob("2024-25__origine*/presenze_per_origine.csv"))
    if not trovati:
        pytest.skip("nessun artefatto per origine su disco")
    d = bo.carica(trovati[0])
    assert len(d) > 0
    assert (d["orizzonte_giornate"] > 0).all()
