"""Contratto del prezzo pubblicato (Livello 4, passo 1 di `reports/livelli_20260910/L4.md`).

Prove di sola lettura sul pack corrente e sull'artefatto della miscela con il
mercato. Nessun modello, nessuna scrittura: si controlla che i tre numeri che
il Copilota mostra rispettino le proprieta' che il resto del codice da' per
scontate.

Due proprieta' sono **rotte oggi** e sono marcate `xfail(strict=True)` con il
motivo: cosi' la prova diventa rossa nel momento in cui il difetto viene
corretto e l'xfail va tolto. Non sono asserzioni indebolite.
"""
from __future__ import annotations

import json
import math
import pickle
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
PACKS = ROOT / "data" / "packs"
PROC = ROOT / "data" / "processed"
CORRENTE = PACKS / "CORRENTE.json"

pytestmark = pytest.mark.skipif(not CORRENTE.exists(),
                                reason="data/packs/CORRENTE.json assente")

CAMPI_OBBLIGATORI = ("q10", "q50", "q90", "value", "value_up", "pres", "sigma")


def _stagione_e_pack() -> tuple[str, Path]:
    d = json.loads(CORRENTE.read_text(encoding="utf-8"))
    return str(d["stagione"]), PACKS / str(d["pack"])


@pytest.fixture(scope="module")
def pack():
    stagione, percorso = _stagione_e_pack()
    if not percorso.exists():
        pytest.skip(f"pack {percorso.name} assente")
    sys.path.insert(0, str(ROOT / "src"))
    with percorso.open("rb") as f:
        p = pickle.load(f)
    return stagione, p


@pytest.fixture(scope="module")
def log_miscela(pack):
    """`data/processed/market_adjust_{stagione}.csv`: q50 del modello e q50 miscelato."""
    import pandas as pd
    stagione, _ = pack
    percorso = PROC / f"market_adjust_{stagione}.csv"
    if not percorso.exists():
        pytest.skip(f"{percorso.name} assente")
    return pd.read_csv(percorso, dtype={"master_id": str})


@pytest.fixture(scope="module")
def prezzi_live(pack):
    """Gli stessi prezzi che `scripts/f9_apply_market.py:129-141` da' alla miscela:
    il file piu' recente della stagione dentro `map_wayback.csv`, colonna
    `p500_10sq` maggiore di zero."""
    import pandas as pd
    stagione, _ = pack
    percorso = PROC / "_match" / "map_wayback.csv"
    if not percorso.exists():
        pytest.skip("map_wayback.csv assente")
    mw = pd.read_csv(percorso)
    mw = mw[(mw.stagione == stagione) & mw.master_id.notna()]
    if not len(mw):
        pytest.skip(f"nessun prezzo di listino per {stagione}")
    piu_recente = sorted(mw.file.unique())[-1]
    mw = mw[mw.file == piu_recente].copy()
    mw["master_id"] = mw.master_id.astype(int).astype(str)
    return {r.master_id: float(r.p500_10sq) for r in mw.itertuples(index=False)
            if pd.notna(r.p500_10sq) and float(r.p500_10sq) > 0}


def _nome(pack_obj, pid: str) -> str:
    g = pack_obj.players.get(pid)
    return getattr(g, "name", pid) or pid


# --------------------------------------------------------------------------
# 1 e 2: le due proprieta' rotte oggi. `strict=True`: quando `market_adjust.py`
# reimporra' l'ordinamento dopo la miscela queste due prove passeranno, il
# rosso si spostera' qui e l'xfail andra' cancellato.
# --------------------------------------------------------------------------
MOTIVO_QUANTILI = (
    "difetto noto al 10/9/2026: `src/fantabot/market_adjust.py:184` trasla q10 e "
    "q90 con `max(1.0, q10 + delta)` senza reimporre l'ordinamento dopo la "
    "miscela col mercato. Nel pack 2026-27 tre portieri hanno q10 > q50: "
    "7533 Happonen (1.0 / 0.84 / 1.79), 7048 De Marzi (1.0 / 0.92 / 1.88), "
    "543 Padelli (1.0 / 0.86 / 2.04). Correzione prevista DOPO l'asta del "
    "10/9/2026; togliere questo xfail quando e' fatta."
)
MOTIVO_Q50_MIN = (
    "stesso difetto e stessi tre portieri di MOTIVO_QUANTILI: il q50 miscelato "
    "scende sotto il credito minimo d'asta (0.84, 0.86, 0.92) perche' il "
    "prezzo di listino e' sotto 1 e la miscela non ha pavimento. Nessun lotto "
    "si aggiudica sotto 1 credito: la soglia non si abbassa."
)


@pytest.mark.xfail(strict=True, reason=MOTIVO_QUANTILI)
def test_ordinamento_quantili(pack):
    stagione, p = pack
    rotti = [(pid, _nome(p, pid), d["q10"], d["q50"], d["q90"])
             for pid, d in p.b_predictions.items()
             if not (d["q10"] <= d["q50"] <= d["q90"])]
    assert rotti == [], (
        f"{len(rotti)} giocatori con q10 <= q50 <= q90 violato in "
        f"pack_{stagione}: {rotti}")


@pytest.mark.xfail(strict=True, reason=MOTIVO_Q50_MIN)
def test_q50_almeno_un_credito(pack):
    stagione, p = pack
    sotto = [(pid, _nome(p, pid), d["q50"])
             for pid, d in p.b_predictions.items() if d["q50"] < 1.0]
    assert sotto == [], (
        f"{len(sotto)} giocatori con q50 sotto il credito minimo in "
        f"pack_{stagione}: {sotto}")


# --------------------------------------------------------------------------
# 3: identita' della miscela. `w_mkt` si legge dalla firma della funzione, non
# si copia il numero: se qualcuno cambia il peso, la prova segue il codice.
# --------------------------------------------------------------------------
def test_peso_mercato_dichiarato():
    import inspect

    sys.path.insert(0, str(ROOT / "src"))
    from fantabot.market_adjust import adjust_predictions

    w = inspect.signature(adjust_predictions).parameters["w_mkt"].default
    assert isinstance(w, float) and 0.0 <= w <= 1.0, f"w_mkt anomalo: {w!r}"


def test_identita_miscela(log_miscela, prezzi_live):
    """q50_adj = w_mkt*live + (1-w_mkt)*q50_modello dove il prezzo live esiste."""
    import inspect

    sys.path.insert(0, str(ROOT / "src"))
    from fantabot.market_adjust import adjust_predictions

    w = float(inspect.signature(adjust_predictions).parameters["w_mkt"].default)
    scarti = []
    n = 0
    for r in log_miscela.itertuples(index=False):
        pid = str(r.master_id)
        if pid not in prezzi_live:
            continue
        n += 1
        atteso = w * prezzi_live[pid] + (1.0 - w) * float(r.q50_modello)
        d = abs(float(r.q50_adj) - atteso)
        if d > 0.01:
            scarti.append((pid, r.nome, float(r.q50_adj), atteso, d))
    assert n > 0, "nessun giocatore con prezzo live: la prova non misura niente"
    assert scarti == [], (
        f"identita' della miscela violata su {len(scarti)} di {n} giocatori "
        f"(w_mkt={w}): {scarti[:10]}")


def test_senza_mercato_q50_resta_del_modello(log_miscela, prezzi_live):
    """Dove il prezzo live manca, la miscela non deve toccare nulla."""
    scarti = []
    n = 0
    for r in log_miscela.itertuples(index=False):
        pid = str(r.master_id)
        if pid in prezzi_live:
            continue
        n += 1
        if float(r.q50_adj) != float(r.q50_modello):
            scarti.append((pid, r.nome, float(r.q50_modello), float(r.q50_adj)))
    assert n > 0, "tutti i giocatori hanno prezzo live: la prova non misura niente"
    assert scarti == [], (
        f"{len(scarti)} di {n} giocatori senza prezzo live hanno q50_adj "
        f"diverso da q50_modello: {scarti[:10]}")


# --------------------------------------------------------------------------
# 4 e 5: il pack e' una copia fedele dell'artefatto, e non ha buchi.
# --------------------------------------------------------------------------
def test_pack_copia_il_q50_miscelato(pack, log_miscela):
    stagione, p = pack
    atteso = {str(r.master_id): round(float(r.q50_adj), 2)
              for r in log_miscela.itertuples(index=False)}
    mancanti = [pid for pid in p.b_predictions if pid not in atteso]
    scarti = [(pid, p.b_predictions[pid]["q50"], atteso[pid])
              for pid in p.b_predictions
              if pid in atteso and abs(p.b_predictions[pid]["q50"] - atteso[pid]) > 1e-9]
    assert mancanti == [], (
        f"{len(mancanti)} giocatori del pack assenti da "
        f"market_adjust_{stagione}.csv: {mancanti[:10]}")
    assert scarti == [], f"q50 del pack diverso dal q50 miscelato: {scarti[:10]}"


def test_nessun_campo_mancante_o_nan(pack):
    stagione, p = pack
    guasti = []
    for pid, d in p.b_predictions.items():
        for c in CAMPI_OBBLIGATORI:
            v = d.get(c)
            if v is None or (isinstance(v, float) and math.isnan(v)):
                guasti.append((pid, c, v))
    assert guasti == [], (
        f"{len(guasti)} campi mancanti o NaN in pack_{stagione}: {guasti[:10]}")
