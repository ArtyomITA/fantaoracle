"""Prove sul produttore di presenze per origine.

Sono prove sui **dati veri**: leggono `data/processed` in sola lettura e non
scrivono nulla. Se i dati non ci sono, si saltano — non si finge di averle
fatte.
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pandas as pd
import pytest

RADICE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RADICE / "src"))
sys.path.insert(0, str(RADICE / "scripts"))

from fantabot.tabellino import origine as org  # noqa: E402

PROC = RADICE / "data" / "processed"
STAGIONE = "2024-25"
servono = [PROC / "l2_partite.parquet", PROC / f"votes_{STAGIONE}.parquet",
           PROC / f"players_{STAGIONE}.parquet"]
pytestmark = pytest.mark.skipif(
    not all(p.exists() for p in servono),
    reason="servono i dati processati della stagione 2024-25")


def _modulo():
    spec = importlib.util.spec_from_file_location(
        "l1_presenze_per_origine",
        RADICE / "scripts" / "l1_presenze_per_origine.py")
    m = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = m
    spec.loader.exec_module(m)
    return m


def test_l_origine_estiva_non_vede_nessuna_giornata():
    m = _modulo()
    k, diag = m.giornate_concluse(STAGIONE, "2024-08-16")
    assert k == 0
    assert diag["partite"]["osservate"] == 0
    assert diag["partite"]["residue"] == 380


def test_un_origine_a_stagione_iniziata_vede_solo_il_passato():
    m = _modulo()
    k, diag = m.giornate_concluse(STAGIONE, "2024-10-01")
    assert k == 6, f"giornate concluse al 1/10/2024: {k}"
    assert diag["partite"]["osservate"] == 60
    assert diag["partite"]["residue"] == 320
    assert diag["partite"]["osservate"] + diag["partite"]["residue"] == 380


def test_origini_diverse_danno_orizzonti_diversi():
    """Il passato pertinente cambia la previsione: se non cambiasse, l'origine
    non conterebbe niente."""
    m = _modulo()
    k0, d0 = m.giornate_concluse(STAGIONE, "2024-08-16")
    k1, d1 = m.giornate_concluse(STAGIONE, "2024-12-01")
    assert k1 > k0
    assert d1["partite"]["residue"] < d0["partite"]["residue"]


def test_a_fine_stagione_non_c_e_orizzonte():
    m = _modulo()
    _, diag = m.giornate_concluse(STAGIONE, "2025-07-01")
    assert diag["partite"]["residue"] == 0
    with pytest.raises(org.ContrattoViolato):
        org.orizzonte(diag["partite"]["residue"])


def test_le_feature_della_stagione_target_non_anticipano_il_futuro():
    """Il controllo di non fuga sulle sole feature che guardano la stagione da
    predire: a origine estiva devono essere vuote, a K giornate non possono
    valere piu' di K."""
    import f1_make_predictions as F
    gk0 = F.gk_features(STAGIONE, 0)
    assert float(pd.Series(gk0["pres_gk"]).fillna(0).sum()) == 0.0, (
        "a K=0 le presenze gia' fatte devono essere zero: qualunque valore "
        "sarebbe informazione della stagione da predire")
    gk6 = F.gk_features(STAGIONE, 6)
    v = pd.Series(gk6["pres_gk"]).dropna()
    assert len(v) > 0
    assert float(v.max()) <= 6.0, (
        f"con sei giornate qualcuno risulta presente {v.max()} volte")


def test_il_target_e_il_resto_non_la_stagione_intera():
    import f1_make_predictions as F
    te = F._season_points_frame(STAGIONE, 6)
    assert "pres_resto" in te.columns
    assert (te["pres_resto"] <= te["pres"] + 1e-9).all()
    assert (te["pres"] - te["pres_resto"] - te["pres_gk"]).abs().max() < 1e-9


def test_le_feature_escluse_sono_quelle_con_la_prova():
    m = _modulo()
    assert set(m.POSTERIORI) == {"fvm", "quot_fs_sett"}
    for nome in m.POSTERIORI + m.RICOSTRUITE:
        stato, prova = m.PROVE_INGRESSI[nome]
        assert prova.strip(), f"{nome} escluso senza motivo scritto"


def test_il_manifesto_rifiuta_un_ingresso_posteriore():
    """Se qualcuno riammettesse `fvm`, il manifesto non si costruisce."""
    m = _modulo()
    ing = m.costruisci_ingressi_dichiarati(["fvm", "eta"], {"fvm", "eta"})
    nomi = {i.nome: i.stato for i in ing}
    assert nomi["fvm"] == org.POSTERIORE
    with pytest.raises(org.ContrattoViolato, match="posteriori"):
        org.ManifestoOrigine(
            stagione=STAGIONE, origine="2024-08-16", universo=[1],
            calendario_osservate=0, calendario_residue=380,
            calendario_rinviate_senza_data=0, etichette_dal=None,
            etichette_fino_a="2024-08-15", ingressi=ing,
            modello="presenze_catboost", versione_modello="x",
            impronte={}, provenienza_temporale="prova")
