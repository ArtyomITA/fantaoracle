"""Classificazione dei tetti: che cosa i dati sostengono, prezzo per prezzo.

Il caso che ha aperto questo file: due prezzi provati, +0,01 con intervallo
[-0,10; +0,10] a prezzo 2 e -0,01 con intervallo [-0,02; -0,005] a prezzo 3.
Il codice restituiva `tetto_economico = 2` e stato `verificato`, perche' lo
stato veniva deciso guardando i punti a distanza <= 1 dal tetto: il punto 3,
che esclude lo zero, faceva da garante per il punto 2, che non lo esclude.
La certezza di un punto veniva attribuita al suo vicino.

Qui si fissa il comportamento corretto: ogni prezzo porta il proprio esito, e
il tetto restituito e' un prezzo su cui il vantaggio e' davvero supportato. Se
nessuno lo e', lo stato e' `inconcludente` e non c'e' nessun tetto da usare.

I confronti sono sintetici e iniettati al posto di `delta_a_prezzo`: qui si
prova la classificazione, non il motore che produce i delta (quello ha i suoi
test in `test_l3_indifferenza.py` e `test_l3_contabilita.py`).
"""
from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from fantabot.livello3 import indifferenza as I   # noqa: E402
from fantabot.livello3 import valutatore as V     # noqa: E402
from fantabot.models import Player                # noqa: E402


QUOTE = {"P": 1, "D": 4, "C": 4, "A": 2}


@dataclass
class CuboFinto:
    giocatori: list
    fantavoto: np.ndarray
    voto: np.ndarray
    gioca: np.ndarray


def _mondo(seme=0, n_scenari=4, n_giornate=2, n_squadre=2):
    """Mondo minimo: serve solo perche' `curva` costruisca cache e chiave."""
    rng = np.random.default_rng(seme)
    pool, prezzi, valori = {}, {}, {}
    n = 1
    for ruolo, quanti in ((r, QUOTE[r] * n_squadre + 2) for r in QUOTE):
        for _ in range(quanti):
            pid = n
            n += 1
            pool[pid] = Player(player_id=str(pid), name=f"G{pid}", role=ruolo,
                               team=f"T{pid % 2}")
            valori[pid] = float(rng.uniform(20, 100))
            prezzi[pid] = float(max(1, round(valori[pid] / 6)))
    tutti = sorted(pool)
    F = np.zeros((n_scenari, n_giornate, len(tutti)), dtype=np.float32)
    cubo = CuboFinto(tutti, F, F.copy(), np.ones(F.shape, dtype=bool))
    return pool, prezzi, valori, cubo


def _stato(pool, budget=100):
    regole = V.Regole(applica_bonus_porta_inviolata=False, quote=QUOTE,
                      budget=budget, usa_mod_difesa=False)
    return I.StatoAsta(
        nostra={r: [] for r in QUOTE},
        nostro_budget=float(budget),
        avversari={"AVV1": {"rosa": {r: [] for r in QUOTE},
                            "budget": float(budget)}},
        disponibili=set(pool),
        regole=regole)


def _inietta(monkeypatch, tabella: dict, repliche: dict | None = None):
    """Sostituisce `delta_a_prezzo` con una tabella prezzo -> (delta, ic95).

    `repliche` e' opzionale: quando c'e', il punto porta anche i delta per
    replica, che sono cio' da cui si ricalcola l'intervallo a livello
    corretto per il numero di prezzi provati."""
    repliche = repliche or {}

    def finto(giocatore, prezzo, *args, **kw):
        delta, ic = tabella[int(prezzo)]
        d = repliche.get(int(prezzo), ())
        return I.Confronto(prezzo=int(prezzo), delta=float(delta),
                           ic95=(float(ic[0]), float(ic[1])),
                           p1_compro=0.5, p1_passo=0.5,
                           n_repliche=len(d) or 4,
                           delta_per_replica=tuple(float(x) for x in d))

    monkeypatch.setattr(I, "delta_a_prezzo", finto)


def _curva(monkeypatch, tabella, repliche=None, budget=100, seme=0):
    pool, prezzi, valori, cubo = _mondo(seme=1)
    stato = _stato(pool, budget=budget)
    g = sorted(pool)[0]
    cal = V.calendario_berger(2, 2, seme=0)
    _inietta(monkeypatch, tabella, repliche)
    return I.curva(g, stato, pool, prezzi, valori, cubo, cal, list(range(4)),
                   prezzi_da_provare=sorted(tabella), repliche=4, seme=seme)


# --------------------------------------------------------------------------
# 1. la regressione: la certezza di un punto non passa al vicino
# --------------------------------------------------------------------------

def test_la_certezza_di_un_punto_non_si_trasferisce_al_vicino(monkeypatch):
    """Caso riprodotto dal committente.

    A prezzo 2 il vantaggio NON e' supportato: l'intervallo [-0,10; +0,10]
    contiene lo zero. A prezzo 3 c'e' uno svantaggio supportato. Il secondo
    fatto riguarda il prezzo 3 e non risolve l'incertezza sul prezzo 2."""
    out = _curva(monkeypatch, {2: (+0.01, (-0.10, +0.10)),
                               3: (-0.01, (-0.02, -0.005))})

    assert out["stato"] == "inconcludente", out["stato"]
    assert not out["tetto_economico"], out["tetto_economico"]

    c = out["classificazione"]
    assert c["prezzi_vantaggio_supportato"] == []
    assert c["prezzi_svantaggio_supportato"] == [3]
    assert c["prezzi_inconcludenti"] == [2]
    # la stima puntuale resta, ma con il suo nome e senza spacciarsi per tetto
    assert c["stima_tetto"] == 2
    assert c["tetto_supportato"] is None


def test_la_vecchia_regola_dei_vicini_e_quella_che_sbagliava():
    """La regola sostituita, riscritta qui per tenere fermo il confronto.

    Era: tetto = massimo prezzo con delta > 0; stato `verificato` se un
    qualsiasi punto a distanza <= 1 dal tetto esclude lo zero. Sugli stessi
    due punti dava (2, `verificato`); la classificazione attuale dice che a
    prezzo 2 non c'e' niente di supportato."""
    punti = [I.Confronto(prezzo=2, delta=+0.01, ic95=(-0.10, +0.10),
                         p1_compro=0.5, p1_passo=0.5, n_repliche=4),
             I.Confronto(prezzo=3, delta=-0.01, ic95=(-0.02, -0.005),
                         p1_compro=0.5, p1_passo=0.5, n_repliche=4)]

    vecchio_tetto = max(c.prezzo for c in punti if c.delta > 0)
    vicini = [c for c in punti if abs(c.prezzo - vecchio_tetto) <= 1]
    vecchio_stato = ("verificato"
                     if any(c.ic95[0] > 0 or c.ic95[1] < 0 for c in vicini)
                     else "approssimato")
    assert (vecchio_tetto, vecchio_stato) == (2, "verificato")

    nuovo = I.classifica_curva(punti, tetto_legale=90)
    assert nuovo["tetto_supportato"] is None
    assert nuovo["stato"] == "inconcludente"
    assert nuovo["esiti_per_prezzo"] == {2: "inconcludente",
                                         3: "svantaggio_supportato"}


def test_uno_svantaggio_supportato_sotto_non_certifica_il_prezzo_sopra(monkeypatch):
    """Simmetrico del precedente: la certezza non si trasferisce nemmeno
    verso l'alto."""
    out = _curva(monkeypatch, {2: (-0.05, (-0.09, -0.02)),
                               3: (+0.01, (-0.10, +0.10))})

    assert out["stato"] == "inconcludente"
    c = out["classificazione"]
    assert c["prezzi_svantaggio_supportato"] == [2]
    assert c["prezzi_inconcludenti"] == [3]
    assert c["tetto_supportato"] is None


# --------------------------------------------------------------------------
# 2. i cinque esiti hanno nomi propri e sono distinti
# --------------------------------------------------------------------------

def test_i_cinque_esiti_sono_distinti_e_nominati(monkeypatch):
    out = _curva(monkeypatch, {
        5: (+0.20, (+0.10, +0.30)),      # vantaggio supportato
        10: (+0.02, (-0.05, +0.09)),     # inconcludente
        20: (-0.15, (-0.25, -0.05)),     # svantaggio supportato
        30: (-0.30, (float("nan"), float("nan"))),   # intervallo assente
    })
    c = out["classificazione"]

    assert c["prezzi_vantaggio_supportato"] == [5]
    assert c["prezzi_inconcludenti"] == [10]
    assert c["prezzi_svantaggio_supportato"] == [20]
    assert c["prezzi_senza_intervallo"] == [30]
    assert c["stima_tetto"] == 10           # stima puntuale: ultimo delta > 0
    assert c["tetto_supportato"] == 5       # il tetto usabile e' un altro numero
    assert out["tetto_economico"] == 5
    # l'intervallo di indifferenza e' calcolabile: fra 5 e 20
    assert c["intervallo_indifferenza"] == [5, 20]
    esiti = {p["prezzo"]: p["esito"] for p in out["curva"]}
    assert esiti == {5: "vantaggio_supportato", 10: "inconcludente",
                     20: "svantaggio_supportato", 30: "intervallo_non_calcolabile"}


def test_stima_puntuale_e_tetto_supportato_sono_campi_diversi(monkeypatch):
    """Il massimo su k punti e' distorto verso l'alto (audit: Zaccagni da
    +0,1250 a 4 repliche a +0,0234 a 32, fattore 5,3). La stima puntuale non
    va confusa con il prezzo su cui i dati sostengono il vantaggio."""
    out = _curva(monkeypatch, {5: (+0.20, (+0.10, +0.30)),
                               9: (+0.01, (-0.20, +0.22))})
    c = out["classificazione"]
    assert c["stima_tetto"] == 9
    assert c["tetto_supportato"] == 5
    assert "5,3" in c["selezione"]["distorsione_nota"]


# --------------------------------------------------------------------------
# 3. intervallo per il punto di indifferenza: c'e' o si dice che non c'e'
# --------------------------------------------------------------------------

def test_intervallo_di_indifferenza_quando_e_racchiuso(monkeypatch):
    out = _curva(monkeypatch, {4: (+0.20, (+0.10, +0.30)),
                               8: (+0.15, (+0.05, +0.25)),
                               16: (-0.20, (-0.30, -0.10))})
    c = out["classificazione"]
    assert c["intervallo_indifferenza"] == [8, 16]
    assert out["stato"] == "verificato"
    # la griglia e' rada: fra 8 e 16 il tetto vero non e' determinato
    assert c["griglia"]["risoluzione_tetto"] == 8


def test_intervallo_non_calcolabile_se_manca_il_lato_alto(monkeypatch):
    out = _curva(monkeypatch, {4: (+0.20, (+0.10, +0.30)),
                               8: (+0.15, (+0.05, +0.25))})
    c = out["classificazione"]
    assert c["intervallo_indifferenza"] is None
    assert c["intervallo_indifferenza_motivo"]
    assert "supportato" in c["intervallo_indifferenza_motivo"]
    # non delimitato di sopra: il tetto e' una stima, non un punto verificato
    assert out["stato"] == "approssimato"


def test_intervallo_non_calcolabile_se_nessun_prezzo_e_supportato(monkeypatch):
    out = _curva(monkeypatch, {4: (+0.02, (-0.05, +0.09)),
                               8: (-0.02, (-0.09, +0.05))})
    c = out["classificazione"]
    assert c["intervallo_indifferenza"] is None
    assert out["stato"] == "inconcludente"
    assert c["prezzi_inconcludenti"] == [4, 8]


# --------------------------------------------------------------------------
# 4. pareggi, non monotonia, buchi
# --------------------------------------------------------------------------

def test_il_pareggio_esatto_non_e_uno_svantaggio(monkeypatch):
    """Nei tetti salvati 26 punti su 121 hanno delta esattamente 0 (audit,
    sezione 3.1): un pareggio non e' un segno negativo."""
    out = _curva(monkeypatch, {4: (+0.10, (+0.02, +0.18)),
                               8: (0.0, (-0.05, +0.05)),
                               12: (-0.10, (-0.18, -0.02))})
    c = out["classificazione"]
    assert c["prezzi_pareggio_puntuale"] == [8]
    assert 8 not in c["prezzi_svantaggio_supportato"]
    assert 8 in c["prezzi_inconcludenti"]
    # un pareggio in mezzo non conta come cambio di segno
    assert c["cambi_di_segno"] == 1


def test_curva_non_monotona_non_puo_essere_verificata(monkeypatch):
    """Svantaggio supportato a un prezzo piu' basso di un vantaggio
    supportato: la curva non e' monotona e il tetto non e' un punto di
    svolta."""
    out = _curva(monkeypatch, {4: (-0.20, (-0.30, -0.10)),
                               8: (+0.20, (+0.10, +0.30)),
                               16: (-0.20, (-0.30, -0.10))})
    c = out["classificazione"]
    assert c["coerenza"] == "non_monotona"
    assert out["stato"] == "approssimato"
    assert c["tetto_supportato"] == 8


def test_un_buco_inconcludente_sotto_il_tetto_e_dichiarato(monkeypatch):
    out = _curva(monkeypatch, {4: (+0.01, (-0.09, +0.11)),
                               8: (+0.20, (+0.10, +0.30)),
                               16: (-0.20, (-0.30, -0.10))})
    c = out["classificazione"]
    assert c["buchi_sotto_il_tetto"] == [4]
    assert out["stato"] == "approssimato"


# --------------------------------------------------------------------------
# 5. selezione su piu' prezzi
# --------------------------------------------------------------------------

def test_intervallo_simultaneo_e_almeno_largo_quanto_quello_per_confronto():
    d = np.array([0.0, 0.0125, 0.0125, 0.0125])
    per_confronto = I._ic_bootstrap(d, seme=0, alfa=0.05)
    simultaneo = I._ic_bootstrap(d, seme=0, alfa=0.05 / 20)
    assert simultaneo[0] <= per_confronto[0]
    assert simultaneo[1] >= per_confronto[1]


def test_il_tetto_tiene_conto_dei_prezzi_provati(monkeypatch):
    """Il tetto e' il massimo su k punti: l'intervallo che lo sostiene va
    letto a livello di famiglia, non del singolo confronto. Con 4 repliche e
    delta [0; 0,0125; 0,0125; 0,0125] il bootstrap esclude lo zero al 95 %
    per confronto, ma non piu' quando i prezzi provati sono venti."""
    d = (0.0, 0.0125, 0.0125, 0.0125)
    per_confronto = I._ic_bootstrap(np.array(d), seme=0, alfa=0.05)
    assert per_confronto[0] > 0, per_confronto

    neutro = (-0.0125, 0.0, 0.0125, 0.0)
    repliche = {p: neutro for p in range(4, 24)}
    repliche[10] = d
    tabella = {p: (float(np.mean(v)), I._ic_bootstrap(np.array(v), seme=0))
               for p, v in repliche.items()}
    out = _curva(monkeypatch, tabella, repliche=repliche)

    c = out["classificazione"]
    assert c["selezione"]["n_prezzi_provati"] == 20
    assert c["selezione"]["controllo_molteplicita"] == "bonferroni_su_bootstrap"
    assert 10 in c["selezione"]["vantaggio_supportato_per_confronto"]
    assert 10 not in c["prezzi_vantaggio_supportato"]
    assert out["stato"] == "inconcludente"
    assert not out["tetto_economico"]


def test_senza_delta_per_replica_la_mancanza_di_controllo_e_dichiarata(monkeypatch):
    out = _curva(monkeypatch, {4: (+0.20, (+0.10, +0.30)),
                               8: (-0.20, (-0.30, -0.10))})
    sel = out["classificazione"]["selezione"]
    assert sel["controllo_molteplicita"].startswith("assente")
    assert sel["n_prezzi_provati"] == 2


# --------------------------------------------------------------------------
# 6. il risultato resta leggibile da chi lo consumava prima
# --------------------------------------------------------------------------

def test_le_chiavi_storiche_restano_e_il_tetto_e_sempre_supportato(monkeypatch):
    out = _curva(monkeypatch, {4: (+0.20, (+0.10, +0.30)),
                               8: (+0.05, (-0.05, +0.15)),
                               16: (-0.20, (-0.30, -0.10))})
    for chiave in ("tetto_economico", "stato", "massimo_legale", "curva",
                   "cambi_di_segno", "chiave_validita", "completamento"):
        assert chiave in out, chiave
    assert out["stato"] in ("verificato", "approssimato", "inconcludente")
    assert out["tetto_economico"] <= out["massimo_legale"]
    if out["tetto_economico"]:
        assert (out["tetto_economico"]
                in out["classificazione"]["prezzi_vantaggio_supportato"])


def test_sul_motore_vero_il_controllo_per_i_prezzi_provati_e_attivo():
    """Senza iniezione: i confronti veri portano i delta per replica, quindi
    la classificazione puo' leggere gli intervalli a livello di famiglia."""
    pool, prezzi, valori, cubo = _mondo(seme=3)
    stato = _stato(pool, budget=60)
    g = sorted(pid for pid in pool if pool[pid].role == "A")[0]
    cal = V.calendario_berger(2, 2, seme=0)

    out = I.curva(g, stato, pool, prezzi, valori, cubo, cal, list(range(4)),
                  prezzi_da_provare=[3, 6, 12], repliche=3, seme=2)

    sel = out["classificazione"]["selezione"]
    assert sel["controllo_molteplicita"] == "bonferroni_su_bootstrap"
    assert sel["n_prezzi_provati"] == 3
    assert sel["livello_famiglia"] == 0.05
    assert sel["livello_per_confronto"] == pytest.approx(0.05 / 3)
    assert all("esito" in p and "ic_usato" in p for p in out["curva"])
    # un cubo piatto non puo' sostenere nessun vantaggio: nessuna scorciatoia
    assert out["stato"] == "inconcludente"
    assert out["tetto_economico"] == 0


def test_nessun_prezzo_ammissibile_resta_inconcludente(monkeypatch):
    pool, prezzi, valori, cubo = _mondo(seme=2)
    stato = _stato(pool, budget=10)
    g = sorted(pool)[0]
    cal = V.calendario_berger(2, 2, seme=0)
    _inietta(monkeypatch, {})
    out = I.curva(g, stato, pool, prezzi, valori, cubo, cal, list(range(4)),
                  prezzi_da_provare=[500], repliche=4, seme=0)
    assert out["stato"] == "inconcludente"
    assert out["motivo"] == "nessun prezzo ammissibile"


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
