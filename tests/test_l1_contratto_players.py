"""Prove sul contratto temporale di `players_*.parquet`.

Leggono i dati veri in sola lettura e costruiscono il contratto in memoria; le
prove sui file `*.contratto.json` su disco si saltano se il file non c'e' —
non si finge di averle fatte.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd
import pytest

RADICE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RADICE / "src"))

from fantabot.contratto_players import (  # noqa: E402
    costruisci_contratto, origine_stagione, peggiore)
from fantabot.tabellino.origine import (  # noqa: E402
    DISPONIBILE, NON_VERIFICABILE, POSTERIORE, RICOSTRUITO, STATI_INGRESSO,
    ContrattoViolato, Ingresso)

PROC = RADICE / "data" / "processed"
STAGIONI = ["2024-25", "2025-26", "2026-27"]
pytestmark = pytest.mark.skipif(
    not (PROC / "l2_partite.parquet").exists()
    or not all((PROC / f"players_{s}.parquet").exists() for s in STAGIONI),
    reason="servono l2_partite.parquet e i players_*.parquet delle tre stagioni")


def _contratto(stagione, k=None):
    return costruisci_contratto(stagione, k=k)


# ------------------------------------------------------------------ copertura
@pytest.mark.parametrize("stagione", STAGIONI)
def test_copre_tutte_le_colonne(stagione):
    """Nessuna colonna del parquet resta senza voce, nessuna voce inventata."""
    df = pd.read_parquet(PROC / f"players_{stagione}.parquet")
    c = _contratto(stagione)
    nomi = [v["nome"] for v in c["colonne"]]
    assert nomi == list(df.columns), (
        f"{stagione}: mancano {set(df.columns) - set(nomi)}, "
        f"in piu' {set(nomi) - set(df.columns)}")
    assert len(nomi) == len(set(nomi)), f"{stagione}: colonne duplicate"
    assert c["n_colonne"] == len(df.columns)
    assert c["righe"] == len(df)


@pytest.mark.parametrize("stagione", STAGIONI)
def test_stati_fra_i_quattro_ammessi(stagione):
    c = _contratto(stagione)
    fuori = {v["nome"]: v["stato"] for v in c["colonne"]
             if v["stato"] not in STATI_INGRESSO}
    assert not fuori, f"{stagione}: stati sconosciuti {fuori}"


@pytest.mark.parametrize("stagione", STAGIONI)
def test_nessuna_disponibile_senza_prova(stagione):
    """Regola di `origine.py`: disponibile senza prova non e' un contratto."""
    c = _contratto(stagione)
    mute = [v["nome"] for v in c["colonne"]
            if v["stato"] == DISPONIBILE and not (v["prova"] or "").strip()]
    assert not mute, f"{stagione}: disponibili senza prova {mute}"
    # e la costruzione dell'Ingresso deve accettarle tutte
    for v in c["colonne"]:
        Ingresso(nome=v["nome"], stato=v["stato"], prova=v["prova"] or "")


def test_ingresso_rifiuta_disponibile_senza_prova():
    """La guardia esiste davvero: se sparisse, la prova sopra sarebbe vuota."""
    with pytest.raises(ContrattoViolato):
        Ingresso(nome="finta", stato=DISPONIBILE, prova="   ")


# ------------------------------------------------------------------ caso noto
def test_fvm_e_quot_fs_posteriori_nel_backtest_k0():
    """2024-25 con k=0: l'origine e' il 17/8/2024, prima della giornata 1.

    `fvm` viene da un listone senza storia acquisito nel 2026; `quot_fs_sett`
    dallo snapshot fanta.soccer di giornata 3 (30/8/2024). Entrambi posteriori.
    """
    c = _contratto("2024-25", k=0)
    assert c["origine"] == "2024-08-17", c["origine"]
    stati = {v["nome"]: v["stato"] for v in c["colonne"]}
    assert stati["fvm"] == POSTERIORE
    assert stati["quot_fs_sett"] == POSTERIORE


def test_2025_26_k0_stesso_esito():
    c = _contratto("2025-26", k=0)
    stati = {v["nome"]: v["stato"] for v in c["colonne"]}
    assert stati["fvm"] == POSTERIORE
    assert stati["quot_fs_sett"] == POSTERIORE


def test_2026_27_con_k3_lo_snapshot_e_ammissibile():
    """Con k=3 l'origine e' l'11/9/2026 e lo snapshot del 4/9 la precede.

    E' il punto in cui il contratto DEVE dipendere da stagione e k: la stessa
    colonna e' posteriore nei backtest e disponibile qui.
    """
    c = _contratto("2026-27", k=3)
    assert c["origine"] == "2026-09-11", c["origine"]
    stati = {v["nome"]: v["stato"] for v in c["colonne"]}
    assert stati["quot_fs_sett"] == DISPONIBILE
    fs = c["date_fonte"]["snapshot_fantasoccer"]
    assert fs["data_rilevazione"] == "2026-09-04"


def test_k_cambia_lo_stato_a_parita_di_stagione():
    """Prova di dipendenza da k, senza guardare altro: k=0 vs k=3 sul 2026-27."""
    k0 = {v["nome"]: v["stato"] for v in _contratto("2026-27", k=0)["colonne"]}
    k3 = {v["nome"]: v["stato"] for v in _contratto("2026-27", k=3)["colonne"]}
    assert k0["quot_fs_sett"] == POSTERIORE
    assert k3["quot_fs_sett"] == DISPONIBILE


# ------------------------------------------------------------------ coerenza
@pytest.mark.parametrize("stagione", STAGIONI)
def test_target_sono_etichette_posteriori(stagione):
    """Le colonne `target_*` sono l'esito d'asta della stagione: mai ingressi."""
    c = _contratto(stagione)
    for v in c["colonne"]:
        if v["nome"].startswith("target_"):
            assert v["stato"] == POSTERIORE, v["nome"]
            assert v["ruolo"] == "etichetta", v["nome"]


@pytest.mark.parametrize("stagione", STAGIONI)
def test_stato_derivato_non_migliore_delle_dipendenze(stagione):
    """Una colonna non puo' essere piu' pulita di cio' da cui dipende."""
    c = _contratto(stagione)
    stati = {v["nome"]: v["stato"] for v in c["colonne"]}
    for v in c["colonne"]:
        for d in v["dipende_da"]:
            assert v["stato"] == peggiore(v["stato"], stati[d]), (
                f"{stagione}: {v['nome']} ({v['stato']}) piu' pulita della "
                f"dipendenza {d} ({stati[d]})")


@pytest.mark.parametrize("stagione", STAGIONI)
def test_origine_non_oltre_la_data_asta_dichiarata(stagione):
    c = _contratto(stagione)
    asta = c["data_asta_dichiarata"]
    if asta is None:
        assert c["avviso_data_asta"], (
            "stagione senza auction_date: il contratto deve dichiararlo")
    else:
        assert c["origine"] <= asta


@pytest.mark.parametrize("stagione", STAGIONI)
def test_origine_precede_la_giornata_k_piu_1(stagione):
    """L'origine non puo' cadere dentro giornate non ancora dichiarate osservate."""
    c = _contratto(stagione)
    p = pd.read_parquet(PROC / "l2_partite.parquet")
    d = p[(p.stagione == stagione) & (p.giornata == c["k"] + 1)]["data"]
    assert c["origine"] <= pd.to_datetime(d).min().date().isoformat()


@pytest.mark.parametrize("stagione", STAGIONI)
def test_impronte_e_versione_presenti(stagione):
    c = _contratto(stagione)
    assert c["versione_codice"]["scripts/f0b_build_outputs.py"]
    assert c["impronte"][f"data/processed/players_{stagione}.parquet"]
    assert c["as_of"]
    assert c["impronta"] and len(c["impronta"]) == 64


def test_origine_stagione_senza_auction_date_lo_dichiara():
    """2026-27 non ha `auction_date` in config/league.yaml: va detto, non finto."""
    o = origine_stagione("2026-27", 3)
    assert o["data_asta_dichiarata"] is None
    assert "auction_date" in (o["avviso"] or "")


# ------------------------------------------------------------------ su disco
@pytest.mark.parametrize("stagione", STAGIONI)
def test_file_su_disco_coerente_col_parquet(stagione):
    f = PROC / f"players_{stagione}.contratto.json"
    if not f.exists():
        pytest.skip(f"{f.name} non ancora scritto")
    c = json.loads(f.read_text(encoding="utf-8"))
    df = pd.read_parquet(PROC / f"players_{stagione}.parquet")
    assert [v["nome"] for v in c["colonne"]] == list(df.columns)
    assert all(v["stato"] in STATI_INGRESSO for v in c["colonne"])
    assert c["stagione"] == stagione
