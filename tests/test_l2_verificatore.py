"""Prove negative sul verificatore della riproduzione (`confronta`).

Codex ha riprodotto quattro modi in cui `scripts/l2_inferenza_banco.py`
dichiarava RIPRODOTTO senza avere confrontato niente:

| alterazione | esito prima della correzione |
|---|---|
| file pubblicato assente | exit 0, «nessun verdetto da confrontare» |
| una riga ricostruita mancante | avviso, poi RIPRODOTTO |
| differenze ricostruite tutte NaN contro numeri finiti | RIPRODOTTO |
| tutte le colonne numeriche ricostruite mancanti | RIPRODOTTO |

Le cause erano quattro scelte che si sommavano: il confronto sulla sola
**intersezione** delle chiavi, le colonne assenti **saltate**, le coppie non
finite **ignorate**, e «nessun confronto effettuato» interpretato come scarto
zero.

Queste prove esercitano la funzione che la CLI chiama davvero, con il percorso
degli artefatti rediretto: `confronta` legge `OUT`, e qui `OUT` punta a una
cartella temporanea. L'ultima prova attraversa `main()` con `--verifica`, così
il collegamento CLI non resta non provato.

Un valore legittimamente non stimabile resta ammesso: quello che non è ammesso
è **confonderlo con un valore perso**. Perciò le prove verificano che il
*motivo* del non stimabile coincida fra ricostruito e pubblicato, non che i NaN
siano vietati.
"""
import importlib.util
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

RADICE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RADICE / "src"))

_spec = importlib.util.spec_from_file_location(
    "l2_inferenza_banco", RADICE / "scripts" / "l2_inferenza_banco.py")
ver = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(ver)


FATTORI = [
    ("meccanismo, a informazione storica", "crps", "empirico"),
    ("meccanismo, con le presenze del modello", "crps", "empirico"),
    ("informazione, meccanismo per giocatore", "brier", "equo"),
    ("interazione", "brier", "equo"),
]


def _tabella(differenze=None, non_stimabile=()):
    """Una tabella di verdetto ben formata.

    `non_stimabile` elenca gli indici di riga per cui la varianza two-way non è
    ammissibile: quelle righe hanno estremi NaN **con un motivo dichiarato**,
    che è il caso legittimo da non confondere con un dato perso.
    """
    differenze = differenze or [0.10, -0.05, 0.02, 0.16]
    righe = []
    for k, (fat, mis, pun) in enumerate(FATTORI):
        nulla = k in non_stimabile
        righe.append({
            "confronto": f"prova {k}", "fattore": fat, "misura": mis,
            "punteggio": pun,
            "differenza": differenze[k],
            "ic_basso": float("nan") if nulla else differenze[k] - 0.03,
            "ic_alto": float("nan") if nulla else differenze[k] + 0.03,
            "es_two_way": float("nan") if nulla else 0.015,
            "es_righe_indipendenti": 0.006,
            "es_monte_carlo": 0.0011,
            "n": 6000, "partite": 380, "giocatori": 679,
            "semi": 8, "scenari": 30,
            "esito": ("varianza non ammissibile" if nulla else "prova"),
        })
    return pd.DataFrame(righe)


@pytest.fixture
def cartella(tmp_path, monkeypatch):
    """`OUT` rediretto: è la stessa variabile che `confronta` legge."""
    monkeypatch.setattr(ver, "OUT", tmp_path)
    return tmp_path


def _pubblica(cartella, tabella, stagione="prova"):
    tabella.to_csv(cartella / f"banco_verdetto_{stagione}.csv", index=False)


# --------------------------------------------------------------------------
# il caso che deve passare
# --------------------------------------------------------------------------

def test_artefatti_integri_sono_riprodotti(cartella):
    """Guardia: se questo fallisce, le prove negative non dimostrano niente."""
    t = _tabella(non_stimabile=(1,))
    _pubblica(cartella, t)
    assert ver.confronta(t.copy(), "prova") == 0


def test_uno_scarto_numerico_vero_viene_rilevato(cartella):
    """Il verificatore deve saper fallire anche nel caso ovvio."""
    _pubblica(cartella, _tabella())
    rotto = _tabella(differenze=[0.10, -0.05, 0.02, 0.99])
    assert ver.confronta(rotto, "prova") != 0


# --------------------------------------------------------------------------
# i quattro difetti riprodotti da Codex
# --------------------------------------------------------------------------

def test_file_pubblicato_assente_non_e_una_riproduzione(cartella):
    """Non avere niente con cui confrontare non è «riprodotto»: è un errore.
    Prima tornava 0 con un messaggio informativo."""
    assert ver.confronta(_tabella(), "prova") != 0


def test_una_riga_mancante_non_e_una_riproduzione(cartella):
    """Il confronto era sull'**intersezione** delle chiavi: bastava che una
    riga ricostruita sparisse perché le restanti coincidessero e l'esito fosse
    RIPRODOTTO."""
    _pubblica(cartella, _tabella())
    assert ver.confronta(_tabella().iloc[:-1].copy(), "prova") != 0


def test_una_riga_in_piu_non_e_una_riproduzione(cartella):
    """Simmetrico del precedente: anche il ricostruito che contiene righe che
    il pubblicato non ha significa che i due non vengono dalla stessa cosa."""
    t = _tabella()
    _pubblica(cartella, t.iloc[:-1])
    assert ver.confronta(t, "prova") != 0


def test_valori_ricostruiti_tutti_nan_non_sono_una_riproduzione(cartella):
    """Le coppie non finite venivano ignorate, quindi confrontare NaN contro
    numeri finiti dava «nessuna coppia» e quindi scarto zero."""
    _pubblica(cartella, _tabella())
    rotto = _tabella()
    for c in ("differenza", "ic_basso", "ic_alto", "es_two_way"):
        rotto[c] = float("nan")
    assert ver.confronta(rotto, "prova") != 0


def test_colonne_numeriche_mancanti_non_sono_una_riproduzione(cartella):
    """Le colonne assenti erano **saltate**: toglierle tutte lasciava zero
    confronti, letti come scarto zero."""
    _pubblica(cartella, _tabella())
    rotto = _tabella().drop(columns=["differenza", "ic_basso", "ic_alto",
                                     "es_two_way", "es_righe_indipendenti",
                                     "es_monte_carlo", "n"])
    assert ver.confronta(rotto, "prova") != 0


# --------------------------------------------------------------------------
# requisiti nuovi
# --------------------------------------------------------------------------

def test_un_non_stimabile_deve_coincidere_da_entrambe_le_parti(cartella):
    """Un valore legittimamente non stimabile è ammesso, ma **dove** è non
    stimabile deve coincidere. Un NaN ricostruito dove il pubblicato ha un
    numero è un dato perso travestito da esito legittimo."""
    _pubblica(cartella, _tabella())                    # nessuna riga NaN
    rotto = _tabella(non_stimabile=(2,))               # una riga NaN
    assert ver.confronta(rotto, "prova") != 0


def test_chiavi_duplicate_fermano_il_confronto(cartella):
    """Con una chiave ripetuta l'allineamento riga per riga non è definito, e
    un confronto non definito non può concludere «riprodotto»."""
    t = _tabella()
    doppia = pd.concat([t, t.iloc[[0]]], ignore_index=True)
    _pubblica(cartella, doppia)
    assert ver.confronta(doppia.copy(), "prova") != 0


def test_metadati_incoerenti_fermano_il_confronto(cartella):
    """Stessi numeri prodotti con un numero di semi diverso non sono lo stesso
    esperimento: i metadati vanno confrontati, non solo le stime."""
    _pubblica(cartella, _tabella())
    rotto = _tabella()
    rotto["semi"] = 4
    assert ver.confronta(rotto, "prova") != 0


def test_scenari_incoerenti_fermano_il_confronto(cartella):
    _pubblica(cartella, _tabella())
    rotto = _tabella()
    rotto["scenari"] = 60
    assert ver.confronta(rotto, "prova") != 0


def test_il_conteggio_delle_osservazioni_e_un_metadato(cartella):
    """`n` non è una stima: è quante osservazioni sono entrate. Se differisce,
    i due non stanno guardando lo stesso campione."""
    _pubblica(cartella, _tabella())
    rotto = _tabella()
    rotto["n"] = 5999
    assert ver.confronta(rotto, "prova") != 0


def test_una_tabella_vuota_non_e_una_riproduzione(cartella):
    """Zero confronti effettuati deve essere un errore esplicito."""
    _pubblica(cartella, _tabella())
    assert ver.confronta(_tabella().iloc[0:0].copy(), "prova") != 0


def test_lo_schema_obbligatorio_e_richiesto_al_pubblicato(cartella):
    """La verifica deve fallire anche quando è il **pubblicato** a essere
    monco, non solo il ricostruito."""
    t = _tabella()
    _pubblica(cartella, t.drop(columns=["es_two_way"]))
    assert ver.confronta(t, "prova") != 0


# --------------------------------------------------------------------------
# collegamento CLI
# --------------------------------------------------------------------------

def test_la_cli_torna_diverso_da_zero_quando_mancano_gli_artefatti(
        tmp_path, monkeypatch, capsys):
    """`main --verifica` su una cartella senza osservazioni non può uscire con
    0: prima l'assenza di artefatti era indistinguibile dal successo."""
    monkeypatch.setattr(ver, "OUT", tmp_path)
    monkeypatch.setattr(sys, "argv",
                        ["l2_inferenza_banco.py", "prova", "--verifica"])
    assert ver.main() != 0


def test_la_cli_attraversa_il_verificatore_su_artefatti_sintetici(
        tmp_path, monkeypatch):
    """Percorso completo della CLI: osservazioni conservate, medie per seme,
    verdetto pubblicato, `main --verifica`. Serve a provare che il verificatore
    corretto è quello che la CLI chiama davvero."""
    monkeypatch.setattr(ver, "OUT", tmp_path)
    rng = np.random.default_rng(0)
    n_part, n_gioc = 20, 30
    righe = []
    for mis in ("crps", "brier"):
        base = pd.DataFrame({
            "misura": mis,
            "giornata": np.repeat(np.arange(1, n_part + 1), n_gioc),
            "data": "2024-08-17",
            "master_id": np.tile(np.arange(n_gioc), n_part),
            "id_partita": np.repeat([f"p{k}" for k in range(n_part)], n_gioc),
            "ruolo": "C", "squadra": "Alfa",
            "esito_vero": 6.0, "ha_giocato": True,
        })
        for b in ("A", "I0", "I1", "C0", "C1"):
            for suff in ("", "_equo", "_dispersione"):
                base[f"{b}{suff}"] = rng.normal(1.5, 0.3, len(base))
        righe.append(base)
    pd.concat(righe, ignore_index=True).to_parquet(
        tmp_path / "banco_osservazioni_prova.parquet", index=False)
    import json
    medie = {}
    for b in ("A", "I0", "I1", "C0", "C1"):
        for k in ("crps", "crps_equo", "brier", "brier_equo"):
            medie[f"{b} braccio|{k}"] = list(rng.normal(1.5, 0.01, 4))
    (tmp_path / "banco_semi_prova.json").write_text(
        json.dumps({"semi": [1, 2, 3, 4], "scenari": 30,
                    "medie_per_seme": medie}), encoding="utf-8")

    # prima esecuzione: scrive il verdetto
    monkeypatch.setattr(sys, "argv", [
        "l2_inferenza_banco.py", "prova", "--scrivi",
        str(tmp_path / "banco_verdetto_prova.csv")])
    assert ver.main() == 0
    assert (tmp_path / "banco_verdetto_prova.csv").exists()

    # seconda esecuzione: la verifica deve riconoscere la riproduzione
    monkeypatch.setattr(sys, "argv",
                        ["l2_inferenza_banco.py", "prova", "--verifica"])
    assert ver.main() == 0

    # e deve accorgersi se il pubblicato viene manomesso
    t = pd.read_csv(tmp_path / "banco_verdetto_prova.csv")
    t.loc[0, "differenza"] = float(t.loc[0, "differenza"]) + 0.5
    t.to_csv(tmp_path / "banco_verdetto_prova.csv", index=False)
    assert ver.main() != 0


# --------------------------------------------------------------------------
# rilievi della revisione indipendente
# --------------------------------------------------------------------------

def test_infiniti_opposti_non_sono_lo_stesso_non_stimabile(cartella):
    """`~np.isfinite` metteva NaN, +inf e -inf nella stessa classe: `+inf`
    contro `-inf` usciva RIPRODOTTO con scarto 9,89e-17. Non sono lo stesso
    motivo, e non sono nemmeno lo stesso l'uno dell'altro."""
    pub = _tabella(non_stimabile=(1,))
    ric = _tabella(non_stimabile=(1,))
    for c in ("ic_basso", "ic_alto", "es_two_way"):
        ric.loc[1, c] = np.inf
        pub.loc[1, c] = -np.inf
    _pubblica(cartella, pub)
    assert ver.confronta(ric, "prova") != 0


def test_un_infinito_contro_un_nan_non_e_una_riproduzione(cartella):
    pub = _tabella(non_stimabile=(1,))
    ric = _tabella(non_stimabile=(1,))
    ric.loc[1, "es_two_way"] = np.inf          # il pubblicato ha NaN
    _pubblica(cartella, pub)
    assert ver.confronta(ric, "prova") != 0


def test_la_provenienza_dichiarata_da_una_parte_sola_e_un_errore(cartella):
    """Prima ricadeva in «provenienza incompleta», che affermava il falso su un
    artefatto che l'identificativo ce l'aveva."""
    pub = _tabella()
    pub["esecuzione"] = "bbbbbbbbbbbb"
    _pubblica(cartella, pub)
    assert ver.confronta(_tabella(), "prova") != 0
    _pubblica(cartella, _tabella())
    ric = _tabella()
    ric["esecuzione"] = "aaaaaaaaaaaa"
    assert ver.confronta(ric, "prova") != 0


def test_esecuzioni_diverse_con_gli_stessi_numeri_sono_rifiutate(cartella):
    pub = _tabella()
    pub["esecuzione"] = "bbbbbbbbbbbb"
    _pubblica(cartella, pub)
    ric = _tabella()
    ric["esecuzione"] = "aaaaaaaaaaaa"
    assert ver.confronta(ric, "prova") != 0


def test_una_colonna_di_stima_non_numerica_non_alza_un_traceback(cartella):
    """Un verdetto pubblicato con una colonna corrotta deve dare NON
    VERIFICATO, non un `ValueError` che il chiamante non sa leggere."""
    pub = _tabella()
    pub.loc[0, "differenza"] = "CORROTTO"
    _pubblica(cartella, pub)
    assert ver.confronta(_tabella(), "prova") != 0


def test_un_metadato_testuale_non_alza_un_traceback(cartella):
    pub = _tabella()
    pub["semi"] = "otto"
    _pubblica(cartella, pub)
    assert ver.confronta(_tabella(), "prova") != 0


def test_i_numeri_scritti_come_stringhe_restano_confrontabili(cartella):
    """Un csv riletto puo' portare numeri come stringhe numeriche: quello non
    e' un artefatto corrotto e non va rifiutato."""
    pub = _tabella()
    pub["differenza"] = pub["differenza"].map(lambda x: f"{x}")
    _pubblica(cartella, pub)
    assert ver.confronta(_tabella(), "prova") == 0
