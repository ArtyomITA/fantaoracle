"""Copertura registrata, contro deriva silenziosa (Livello 4, passo 5 di
`reports/livelli_20260910/L4.md`).

Si ricalcolano copertura di `[q10, q90]`, pinball e MAE dalle predizioni
salvate (`data/processed/pred_ens_tab_cat_{stagione}.csv`) e dal bersaglio
(`target_mean_pct_all_estiva` con almeno due osservazioni, in
`players_{stagione}.parquet`), con le stesse formule di
`scripts/f1_train_price.py:evaluate`, e si confrontano con i valori registrati
in `reports/f1_price_eval.json`.

Tolleranze dichiarate prima di guardare i numeri:
  n         uguaglianza esatta
  copertura 0.005   (il json e' arrotondato a 3 decimali)
  pinball   0.0002  (json a 5 decimali)
  mae_pct   0.0002  (json a 5 decimali)

Nessun modello viene addestrato: si legge quello che c'e' su disco.
"""
from __future__ import annotations

import ast
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
PROC = ROOT / "data" / "processed"
EVAL = ROOT / "reports" / "f1_price_eval.json"
F1 = ROOT / "scripts" / "f1_train_price.py"
MODELLO = "ens_tab_cat"

TOLL = {"coverage_q10_q90": 0.005, "pinball": 0.0002, "mae_pct": 0.0002}

pytestmark = pytest.mark.skipif(
    not (EVAL.exists() and F1.exists()),
    reason="mancano reports/f1_price_eval.json o scripts/f1_train_price.py")


def _runs() -> list:
    albero = ast.parse(F1.read_text(encoding="utf-8"), filename=str(F1))
    for nodo in albero.body:
        if isinstance(nodo, ast.Assign):
            for t in nodo.targets:
                if isinstance(t, ast.Name) and t.id == "RUNS":
                    return ast.literal_eval(nodo.value)
    raise AssertionError("RUNS non trovato in f1_train_price.py")


@pytest.fixture(scope="module")
def registrato() -> dict:
    return json.loads(EVAL.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def runs() -> list:
    return _runs()


def _metriche(stagione: str) -> dict:
    """Le stesse formule di f1_train_price.evaluate, sulle predizioni salvate."""
    import numpy as np
    import pandas as pd
    from scipy.stats import spearmanr

    pred_path = PROC / f"pred_{MODELLO}_{stagione}.csv"
    players_path = PROC / f"players_{stagione}.parquet"
    if not pred_path.exists():
        pytest.skip(f"{pred_path.name} assente: predizioni salvate non disponibili")
    if not players_path.exists():
        pytest.skip(f"players_{stagione}.parquet assente")

    pred = pd.read_csv(pred_path)
    pl = pd.read_parquet(
        players_path,
        columns=["master_id", "target_mean_pct_all_estiva", "target_n_obs_all_estiva"])
    assert pl.master_id.is_unique, f"master_id non unico in players_{stagione}"
    assert pred.master_id.is_unique, f"master_id non unico in {pred_path.name}"
    pl["master_id"] = pl["master_id"].astype(int)
    pred["master_id"] = pred["master_id"].astype(int)
    df = pred.merge(pl, on="master_id", how="left", validate="one_to_one")
    assert len(df) == len(pred), "aggancio predizioni/bersaglio non uno a uno"

    n_obs = df["target_n_obs_all_estiva"].fillna(0).astype(float)
    y = df["target_mean_pct_all_estiva"].astype(float).where(n_obs >= 2).to_numpy()
    mask = ~np.isnan(y)
    y = y[mask]
    q10 = df["q10"].to_numpy(dtype=float)[mask]
    q50 = df["q50"].to_numpy(dtype=float)[mask]
    q90 = df["q90"].to_numpy(dtype=float)[mask]
    pinball = 0.0
    for q, a in ((q10, 0.1), (q90, 0.9)):
        d = y - q
        pinball += float(np.mean(np.maximum(a * d, (a - 1) * d)))
    return {
        "n": int(mask.sum()),
        "spearman": round(float(spearmanr(y, q50).statistic), 4),
        "mae_pct": round(float(np.mean(np.abs(y - q50))), 5),
        "coverage_q10_q90": round(float(np.mean((y >= q10) & (y <= q90))), 3),
        "pinball": round(float(pinball), 5),
    }


@pytest.mark.parametrize("run,stagione", [("R1", "2023-24"), ("R2", "2024-25")])
def test_metriche_ricalcolate_coincidono(registrato, runs, run, stagione):
    attese = {r: s for r, _t, s in runs}
    if attese.get(run) != stagione:
        pytest.skip(f"{run} non e' piu' la stagione {stagione} in RUNS: {runs}")
    chiave = f"{run}/{MODELLO}"
    if chiave not in registrato:
        pytest.skip(f"{chiave} assente da f1_price_eval.json")
    atteso = registrato[chiave]
    ora = _metriche(stagione)
    assert ora["n"] == atteso["n"], (
        f"{chiave}: numerosita' del bersaglio cambiata, "
        f"registrata {atteso['n']}, ricalcolata {ora['n']}")
    scarti = {k: (atteso[k], ora[k], abs(atteso[k] - ora[k]))
              for k, t in TOLL.items() if abs(atteso[k] - ora[k]) > t}
    assert scarti == {}, (
        f"{chiave}: metriche fuori tolleranza {TOLL} "
        f"(registrata, ricalcolata, scarto): {scarti}")


MOTIVO_JSON_VECCHIO = (
    "`reports/f1_price_eval.json` e' del 6/8/2026 e contiene ancora il run R3 "
    "(cinque voci: R3/ridge, R3/catboost, R3/tabpfn, R3/vorp, R3/ens_tab_cat, "
    "n=509 sul 2025-26), che `scripts/f1_train_price.py:56-59` dichiara rimosso "
    "il 6/9/2026 perche' per il 2025-26 non esiste un prezzo d'asta osservato "
    "prima del via. L'artefatto va rigenerato dopo l'asta del 10/9/2026, oppure "
    "rinominato come storico: finche' resta com'e', questa prova e' rossa."
)


@pytest.mark.xfail(strict=True, reason=MOTIVO_JSON_VECCHIO)
def test_json_allineato_ai_run_del_codice(registrato, runs):
    nel_json = sorted({k.split("/", 1)[0] for k in registrato})
    nel_codice = sorted({r for r, _t, _s in runs})
    assert nel_json == nel_codice, (
        f"run nel json {nel_json} diversi dai run del codice {nel_codice}; "
        f"in piu' nel json: {sorted(set(nel_json) - set(nel_codice))}")
