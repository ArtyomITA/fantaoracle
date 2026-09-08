"""Verdetto appaiato del banco del Livello 2 (criteri, sezione 3.7).

Il banco produceva medie senza incertezza: una differenza di 0,02 di CRPS e una
di 0,2 avevano lo stesso aspetto. Queste prove fissano il comportamento della
differenza appaiata, che e' quello che il criterio di promozione usa.
"""
import importlib.util
import sys
from pathlib import Path

import numpy as np
import pytest

RADICE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RADICE / "src"))

_spec = importlib.util.spec_from_file_location(
    "l2_banco_confronto", RADICE / "scripts" / "l2_banco_confronto.py")
banco = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(banco)


def test_differenza_costante_esclude_lo_zero():
    """Con un vantaggio costante l'intervallo non puo' contenere lo zero."""
    rng = np.random.default_rng(0)
    b = rng.normal(1.5, 0.3, size=4000)
    a = b - 0.10                      # `a` migliore di 0,10 su ogni riga
    r = banco.differenza_appaiata(a, b, seme=1)
    assert r["differenza"] == pytest.approx(-0.10, abs=1e-9)
    assert r["esclude_zero"]
    assert r["ic_alto"] < 0


def test_misure_identiche_sono_inconcludenti():
    """Zero differenza: l'intervallo contiene lo zero e l'esito non promuove."""
    rng = np.random.default_rng(1)
    a = rng.normal(1.5, 0.3, size=2000)
    r = banco.differenza_appaiata(a, a.copy(), seme=1)
    assert r["differenza"] == pytest.approx(0.0, abs=1e-12)
    assert not r["esclude_zero"]


def test_il_bootstrap_non_vede_il_rumore_monte_carlo():
    """Limite dichiarato del metodo, fissato come prova perche' non si perda.

    Il ricampionamento e' sulle coppie (giocatore, giornata). Il rumore che
    ciascun generatore ha per il numero finito di scenari NON viene
    ricampionato: entra nei valori come se fosse un dato. Qui due bracci senza
    alcun vantaggio sistematico, ma con rumore indipendente di 0,02 su 4.000
    coppie, producono un intervallo che esclude lo zero pur non essendoci
    niente da trovare.

    Conseguenza operativa, scritta nei criteri 3.7: l'intervallo va letto come
    incertezza sul campione di coppie a scenari fissati, e i confronti vanno
    fatti con gli stessi numeri casuali comuni, cosi' che il rumore condiviso
    si cancelli nella differenza. Un intervallo stretto NON dimostra da solo
    che la differenza sopravvive a un altro insieme di scenari.
    """
    rng = np.random.default_rng(2)
    comune = rng.normal(1.5, 0.3, size=4000)
    a = comune + rng.normal(0, 0.02, size=4000)
    b = comune + rng.normal(0, 0.02, size=4000)
    r = banco.differenza_appaiata(a, b, seme=3)
    assert abs(r["differenza"]) < 0.005          # nessun vantaggio vero
    assert r["esclude_zero"]                     # e l'intervallo lo esclude
    assert abs(r["ic_alto"] - r["ic_basso"]) < 0.005


def test_rumore_condiviso_resta_inconcludente():
    """Con numeri casuali comuni il rumore si cancella e l'esito e' onesto."""
    rng = np.random.default_rng(2)
    comune = rng.normal(1.5, 0.3, size=4000)
    rumore = rng.normal(0, 0.02, size=4000)      # lo stesso per i due bracci
    r = banco.differenza_appaiata(comune + rumore, comune + rumore, seme=3)
    assert r["differenza"] == pytest.approx(0.0, abs=1e-12)
    assert not r["esclude_zero"]


def test_forme_diverse_alzano_errore():
    """Due misure non appaiate non si confrontano riga per riga."""
    with pytest.raises(ValueError, match="non appaiabili"):
        banco.differenza_appaiata(np.zeros(10), np.zeros(11), seme=1)


def test_tutte_non_finite_alzano_errore():
    """Nessuna osservazione utilizzabile e' un errore, non una differenza nulla."""
    with pytest.raises(ValueError, match="nessuna osservazione finita"):
        banco.differenza_appaiata(np.full(5, np.nan), np.zeros(5), seme=1)


def _finto(n=3000, delta_crps=0.0, seme=0):
    rng = np.random.default_rng(seme)
    base = rng.normal(1.6, 0.4, size=n)
    return {"crps": base + delta_crps, "brier": np.abs(base) / 10.0}


def test_verdetto_riconosce_i_due_confronti():
    """Un confronto e' a informazione comparabile, l'altro fra sistemi completi."""
    per_oss = {
        "A baseline semplice": _finto(seme=1),
        "B vecchio simulatore": _finto(seme=2),
        "B' vecchio + presenze del modello": _finto(seme=3),
        "C cubo TABELLINO": _finto(seme=4),
    }
    df = banco.verdetto_appaiato(per_oss, seme=7)
    assert len(df) == 4                      # due avversari per due misure
    tipi = set(zip(df.confronto, df.tipo))
    assert ("C cubo TABELLINO contro B' vecchio + presenze del modello",
            "informazione comparabile") in tipi
    assert ("C cubo TABELLINO contro B vecchio simulatore",
            "sistemi completi") in tipi


def test_verdetto_dichiara_c_peggiore_quando_lo_e():
    """Il verdetto non e' addolcito: se C perde, lo dice."""
    per_oss = {
        "B vecchio simulatore": _finto(seme=5),
        "C cubo TABELLINO": _finto(seme=5, delta_crps=+0.20),
    }
    df = banco.verdetto_appaiato(per_oss, seme=7)
    riga = df[df.misura == "crps"].iloc[0]
    assert riga.esito == "C peggiore"
    assert riga.differenza == pytest.approx(0.20, abs=1e-6)


def test_verdetto_senza_generatore_c_non_inventa_nulla():
    assert banco.verdetto_appaiato({"B vecchio simulatore": _finto()}, seme=1) is None
