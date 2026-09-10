"""Non anticipazione della fonte del prezzo (Livello 4, passo 4 di
`reports/livelli_20260910/L4.md`).

La regola: il bersaglio del prezzo di una stagione deve essere noto **prima**
dell'asta di quella stagione. Qui si controlla la dichiarazione
(`PRICE_SOURCES` in `scripts/f1_train_price.py`), il calendario
(`config/league.yaml`) e le date vere dei listini
(`data/processed/_match/map_wayback.csv`).

`f1_train_price.py` si legge con `ast`, non si importa: nessun effetto
collaterale, nessuna cartella creata.

Due prove sono rosse oggi e sono marcate `xfail(strict=True)` con i numeri:
mancano le date d'asta di tre stagioni, e i listini delle stagioni passate sono
tutti posteriori all'asta. Non sono asserzioni allentate: diventano verdi solo
quando il dato manca davvero di essere sbagliato.
"""
from __future__ import annotations

import ast
import re
from datetime import date
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
F1 = ROOT / "scripts" / "f1_train_price.py"
LEAGUE = ROOT / "config" / "league.yaml"
MAPWB = ROOT / "data" / "processed" / "_match" / "map_wayback.csv"

pytestmark = pytest.mark.skipif(
    not (F1.exists() and LEAGUE.exists() and MAPWB.exists()),
    reason="mancano f1_train_price.py, config/league.yaml o map_wayback.csv")


def _letterale(nome: str):
    """Valore del letterale assegnato a `nome` in f1_train_price.py, senza importarlo."""
    albero = ast.parse(F1.read_text(encoding="utf-8"), filename=str(F1))
    for nodo in albero.body:
        if isinstance(nodo, ast.Assign):
            for t in nodo.targets:
                if isinstance(t, ast.Name) and t.id == nome:
                    return ast.literal_eval(nodo.value)
    raise AssertionError(f"{nome} non trovato in {F1.name}")


@pytest.fixture(scope="module")
def price_sources() -> dict:
    return _letterale("PRICE_SOURCES")


@pytest.fixture(scope="module")
def runs() -> list:
    return _letterale("RUNS")


@pytest.fixture(scope="module")
def aste() -> dict:
    """stagione -> data d'asta dichiarata in config/league.yaml."""
    import yaml

    cfg = yaml.safe_load(LEAGUE.read_text(encoding="utf-8")) or {}
    out = {}
    for s, d in (cfg.get("seasons") or {}).items():
        v = (d or {}).get("auction_date")
        if v:
            out[str(s)] = v if isinstance(v, date) else date.fromisoformat(str(v))
    return out


@pytest.fixture(scope="module")
def listini() -> dict:
    """stagione -> [(data, nome file)] ordinati, dalle date nei nomi dei file."""
    import pandas as pd

    mw = pd.read_csv(MAPWB, usecols=["stagione", "file"]).drop_duplicates()
    out: dict[str, list] = {}
    for r in mw.itertuples(index=False):
        m = re.search(r"(20\d{2})(\d{2})(\d{2})", str(r.file))
        assert m, f"nome di listino senza data: {r.file}"
        d = date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        out.setdefault(str(r.stagione), []).append((d, str(r.file)))
    for s in out:
        out[s].sort()
    return out


def _data_fonte(testo: str) -> date:
    """'2024-08' -> 1/8/2024; '2026-09-01' -> quella data."""
    p = [int(x) for x in str(testo).split("-")]
    return date(p[0], p[1], p[2] if len(p) > 2 else 1)


# --------------------------------------------------------------------------
# verde oggi
# --------------------------------------------------------------------------
def test_fonte_dichiarata_precede_asta(price_sources, aste):
    """Dove sappiamo la data d'asta, la fonte dichiarata valida la precede."""
    controllate, rotte = [], []
    for s, (_kind, data, valido, _nota) in price_sources.items():
        if not valido or s not in aste or not data:
            continue
        d = _data_fonte(data)
        controllate.append((s, d, aste[s]))
        if not d < aste[s]:
            rotte.append((s, str(d), str(aste[s])))
    assert controllate, "nessuna stagione con fonte valida e data d'asta nota"
    assert rotte == [], f"fonte del prezzo non anteriore all'asta: {rotte}"


def test_bersaglio_backtest_non_e_un_listino(price_sources, runs):
    """Per le stagioni di backtest il bersaglio resta le aste reali estive:
    promuovere un listino wayback a bersaglio fa fallire questa prova."""
    guasti = []
    for _run, _train, test_s in runs:
        kind = price_sources.get(test_s, (None,))[0]
        if kind != "estiva":
            guasti.append((test_s, kind))
    assert guasti == [], (
        f"stagioni di backtest con bersaglio diverso dalle aste estive: {guasti}")


def test_stagione_bersaglio_fuori_dal_train(runs):
    """Leave-future-out: la stagione di test non entra nel proprio train e ogni
    stagione di train la precede."""
    guasti = []
    for run, train, test_s in runs:
        if test_s in train:
            guasti.append((run, "stagione di test dentro il train", test_s))
        for s in train:
            if s >= test_s:
                guasti.append((run, "stagione di train non anteriore", s, test_s))
    assert guasti == [], f"contratto leave-future-out violato: {guasti}"


# --------------------------------------------------------------------------
# rosse oggi
# --------------------------------------------------------------------------
MOTIVO_DATE_MANCANTI = (
    "al 10/9/2026 `config/league.yaml` dichiara `auction_date` solo per 2024-25 "
    "(2024-09-01) e 2025-26 (2025-09-02). Mancano le due stagioni di backtest "
    "2021-22 e 2023-24 (RUNS R1 e R2) e la stagione operativa 2026-27, la cui "
    "asta e' il 10/9/2026: senza quelle date la non anticipazione del bersaglio "
    "non e' verificabile per tre stagioni su quattro."
)
MOTIVO_LISTINI_POSTUMI = (
    "al 10/9/2026 tutti i listini archiviati delle stagioni con data d'asta nota "
    "sono POSTERIORI all'asta: 2024-25 (asta 2024-09-01) ha "
    "wayback_20241004 (4/10/2024), prezzi_2024-25_20250214 (14/2/2025) e "
    "prezzi_2024-25_20250616 (16/6/2025); 2025-26 (asta 2025-09-02) ha "
    "wayback_20251212 (12/12/2025), prezzi_2025-26_20260411 (11/4/2026) e "
    "fantacalcio-online_live_2026-08-06 (6/8/2026). Nessuna stagione passata ha "
    "un listino pre-asta: il peso della miscela col mercato non e' falsificabile "
    "fuori tempo con questo archivio (L4.md §2.3f)."
)


@pytest.mark.xfail(strict=True, reason=MOTIVO_DATE_MANCANTI)
def test_data_asta_dichiarata_per_ogni_stagione(price_sources, runs, aste):
    servono = {test_s for _r, _t, test_s in runs}
    servono |= {s for s, v in price_sources.items() if v[2] and s >= "2026-27"}
    mancanti = sorted(s for s in servono if s not in aste)
    assert mancanti == [], (
        f"stagioni senza auction_date in config/league.yaml: {mancanti} "
        f"(dichiarate: {sorted(aste)})")


@pytest.mark.xfail(strict=True, reason=MOTIVO_LISTINI_POSTUMI)
def test_listini_anteriori_alla_propria_asta(aste, listini):
    postumi = []
    for s, d_asta in sorted(aste.items()):
        for d, nome in listini.get(s, []):
            if not d < d_asta:
                postumi.append((s, nome, str(d), str(d_asta)))
    assert postumi == [], (
        f"{len(postumi)} listini posteriori all'asta della propria stagione: "
        f"{postumi}")
