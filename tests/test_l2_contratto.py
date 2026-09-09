"""Il contratto temporale deve essere imposto dal consumatore, non solo scritto.

Difetti che questi test impediscono, tutti riprodotti prima della correzione:

- `l2_panel_qualita.json` riportava `data_fit = 2026-09-08` per tutte e cinque
  le stagioni, perché il predefinito dello script che costruisce il panel è
  «oggi». Un fit datato 2024 avrebbe letto quei panel senza accorgersene;
- il cutoff viveva solo nel JSON di qualità: il parquet non lo portava, e i
  consumatori leggevano il parquet;
- un unico `l2_panel_{stagione}.parquet` cambiava significato a seconda
  dell'ultimo comando eseguito;
- il banco caricava i panel con `glob("l2_panel_*.parquet")`, che con i file
  indicizzati per cutoff avrebbe raccolto ogni variante dello stesso panel.
"""
import json
import sys
from pathlib import Path

import pandas as pd
import pytest

RADICE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RADICE / "src"))

from fantabot.tabellino import contratto as ct           # noqa: E402

PROC = RADICE / "data" / "processed"


def _panel_finto(tmp_path, stagione="2024-25", data_fit="2024-08-16",
                 righe=10) -> Path:
    d = pd.DataFrame({
        "master_id": range(righe),
        "stagione": [stagione] * righe,
        "data": pd.date_range("2024-08-17", periods=righe, freq="7D"),
        "eleggibile_fit": [True] * righe,
    })
    percorso = tmp_path / ct.nome_panel(stagione, data_fit)
    d.to_parquet(percorso, index=False)
    ct.scrivi(percorso, ct.ContrattoPanel(
        stagione=stagione, data_fit=data_fit,
        as_of_decisione="2024-08-16", estendi_fino="2025-05-26",
        righe=righe, colonne=sorted(d.columns.tolist())))
    return percorso


# ------------------------------------------------- il cutoff entra nel nome
def test_il_nome_del_file_porta_il_cutoff():
    """Due fit diversi non possono sovrascriversi."""
    a = ct.nome_panel("2024-25", "2024-08-16")
    b = ct.nome_panel("2024-25", "2026-09-08")
    assert a != b
    assert "20240816" in a and "20260908" in b
    # senza cutoff resta il nome storico, che indica la vista osservativa
    assert ct.nome_panel("2024-25") == "l2_panel_2024-25.parquet"


def test_il_contratto_si_scrive_e_si_rilegge(tmp_path):
    p = _panel_finto(tmp_path)
    c = ct.leggi(p)
    assert c is not None
    assert c.data_fit == "2024-08-16"
    assert c.stagione == "2024-25"
    assert c.impronta()


# ------------------------------------------------------- il consumatore rifiuta
def test_un_fit_piu_tardo_viene_rifiutato(tmp_path):
    """Il caso del backtest 2024 su panel costruiti nel 2026.

    Il panel con fit più tardo contiene prove che al cutoff chiesto non
    esistevano: va rifiutato, non usato.
    """
    _panel_finto(tmp_path, data_fit="2026-09-08")
    with pytest.raises(ct.ContrattoIncompatibile, match="successivo"):
        # il file per il fit chiesto non c'è, ma quello generico esiste con un
        # fit diverso: la ricerca lo trova e lo rifiuta
        percorso = tmp_path / ct.nome_panel("2024-25", "2026-09-08")
        ct.verifica(ct.leggi(percorso), percorso, stagione="2024-25",
                    data_fit="2024-08-16")


def test_un_fit_anteriore_viene_rifiutato_e_dichiarato(tmp_path):
    """Un panel più conservativo non è quello che abbiamo chiesto.

    Non contiene prove che al cutoff chiesto erano disponibili: usarlo sarebbe
    un'altra cosa da quella dichiarata, e la differenza va vista.
    """
    percorso = _panel_finto(tmp_path, data_fit="2024-01-01")
    with pytest.raises(ct.ContrattoIncompatibile, match="anteriore"):
        ct.verifica(ct.leggi(percorso), percorso, stagione="2024-25",
                    data_fit="2024-08-16")


def test_un_panel_senza_contratto_viene_rifiutato_se_si_chiede_un_cutoff(tmp_path):
    d = pd.DataFrame({"master_id": [1], "data": [pd.Timestamp("2024-08-17")]})
    percorso = tmp_path / "l2_panel_2024-25.parquet"
    d.to_parquet(percorso, index=False)
    with pytest.raises(ct.ContrattoIncompatibile, match="non porta un contratto"):
        ct.verifica(None, percorso, stagione="2024-25", data_fit="2024-08-16")


def test_un_panel_senza_contratto_va_bene_per_la_vista_osservativa(tmp_path):
    """Chi chiede esplicitamente la vista storica non ha bisogno del cutoff."""
    percorso = tmp_path / "l2_panel_2024-25.parquet"
    c = ct.verifica(None, percorso, stagione="2024-25", data_fit=None,
                    esigi_vista_al_fit=False)
    assert c.data_fit is None


def test_una_versione_diversa_della_trasformazione_viene_rifiutata(tmp_path):
    percorso = _panel_finto(tmp_path)
    c = ct.leggi(percorso)
    c.versione = "vecchia.0"
    with pytest.raises(ct.ContrattoIncompatibile, match="versione"):
        ct.verifica(c, percorso, stagione="2024-25", data_fit="2024-08-16")


def test_la_stagione_sbagliata_viene_rifiutata(tmp_path):
    percorso = _panel_finto(tmp_path)
    with pytest.raises(ct.ContrattoIncompatibile, match="stagione"):
        ct.verifica(ct.leggi(percorso), percorso, stagione="2025-26",
                    data_fit="2024-08-16")


# --------------------------------------------------------- caricamento multiplo
def test_il_caricamento_multiplo_non_duplica_le_varianti(tmp_path):
    """Il glob raccoglieva ogni variante dello stesso panel.

    Con due file per la stessa stagione e cutoff diversi, un glob avrebbe
    concatenato entrambi e raddoppiato le righe.
    """
    _panel_finto(tmp_path, stagione="2024-25", data_fit="2024-08-16", righe=10)
    _panel_finto(tmp_path, stagione="2024-25", data_fit="2026-09-08", righe=10)
    P, contratti = ct.carica_panel_multi(tmp_path, ["2024-25"],
                                         data_fit="2024-08-16")
    assert len(P) == 10, "il caricamento ha preso più di una variante"
    assert contratti["2024-25"]["data_fit"] == "2024-08-16"


def test_il_caricamento_multiplo_registra_cosa_ha_consumato(tmp_path):
    """Chi consuma deve poter dire su quali dati ha lavorato."""
    _panel_finto(tmp_path, stagione="2024-25", data_fit="2024-08-16")
    _panel_finto(tmp_path, stagione="2025-26", data_fit="2024-08-16")
    _, contratti = ct.carica_panel_multi(tmp_path, ["2024-25", "2025-26"],
                                         data_fit="2024-08-16")
    assert set(contratti) == {"2024-25", "2025-26"}
    for c in contratti.values():
        assert c["impronta"] and c["chiave"]


def test_una_stagione_mancante_col_cutoff_chiesto_e_un_errore(tmp_path):
    _panel_finto(tmp_path, stagione="2024-25", data_fit="2024-08-16")
    with pytest.raises(ct.ContrattoIncompatibile, match="manca"):
        ct.carica_panel_multi(tmp_path, ["2024-25", "2025-26"],
                              data_fit="2024-08-16")


# --------------------------------------------- il panel vero porta il contratto
def test_i_panel_del_progetto_portano_il_contratto():
    """Guardia di integrazione: i panel veri devono avere i metadati."""
    trovati = sorted(PROC.glob("l2_panel_*.parquet"))
    if not trovati:
        pytest.skip("nessun panel costruito")
    senza = [p.name for p in trovati if ct.leggi(p) is None]
    assert not senza, f"panel senza contratto temporale: {senza}"


def test_il_json_di_qualita_e_il_contratto_concordano():
    """Se i due dicono cose diverse, uno dei due sta mentendo."""
    q = PROC / "l2_panel_qualita.json"
    if not q.exists():
        pytest.skip("manca l2_panel_qualita.json")
    d = json.loads(q.read_text(encoding="utf-8"))
    for stagione, blocco in d.items():
        if not isinstance(blocco, dict) or "data_fit" not in blocco:
            continue
        percorso = PROC / ct.nome_panel(stagione, blocco["data_fit"])
        if not percorso.exists():
            continue
        c = ct.leggi(percorso)
        assert c is not None and c.data_fit == blocco["data_fit"], (
            f"{stagione}: il JSON dice {blocco['data_fit']}, il contratto "
            f"{c.data_fit if c else 'niente'}")
