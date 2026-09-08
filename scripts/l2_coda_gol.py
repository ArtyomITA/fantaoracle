"""Distribuzione dei gol del cubo contro l'osservato, misurata per intero.

La misura precedente (registrata in `reports/CRITERI_L2_L3.md` §7.6 e poi
rettificata) leggeva solo `v[1]` da `cubo.risultati`, cioè i gol della sola
squadra in trasferta: metà campione preso per l'intero. Questo script rifà la
misura come chiede `reports/PROTOCOLLO_v2.md`, cioè separando sempre:

- casa e trasferta, e il totale;
- numero di partite, di squadra-partita e di **scenari**;
- media, varianza e probabilità di coda;
- la variabilità della coda **fra scenari**, che è il punto che cambia la
  lettura: gli scenari campionano i parametri del modello, quindi le
  squadra-partita di uno stesso scenario condividono le forze e non sono
  osservazioni indipendenti.

L'osservato si prende con la stessa procedura di filtro temporale del modello
(`configurazione.partite_di_addestramento`), e si riporta sia su tutte le
stagioni disponibili sia sulle ultime tre concluse, perché il confronto con
otto stagioni miste non è omogeneo per periodo.

Uso:
    python scripts/l2_coda_gol.py --stagione 2026-27 --as-of 2026-09-11
"""
from __future__ import annotations

import argparse
import collections
import json
import pickle
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from fantabot.tabellino import configurazione as cfg      # noqa: E402

PROC = ROOT / "data" / "processed"
OUT = ROOT / "data" / "l2"


def descrivi(v: np.ndarray) -> dict:
    """Media, varianza, code e massimo di un vettore di gol."""
    v = np.asarray(v)
    c = collections.Counter(v.tolist())
    n = len(v)
    return {
        "n": int(n),
        "media": float(v.mean()),
        "varianza": float(v.var()),
        "p_zero": float(c[0] / n),
        "p_sei_o_piu": float(sum(x for k, x in c.items() if k >= 6) / n),
        "massimo": int(v.max()),
        "distribuzione": {int(k): int(x) for k, x in sorted(c.items())},
    }


def clopper_pearson(k: int, n: int, alfa: float = 0.05) -> tuple[float, float]:
    """Intervallo esatto per una proporzione binomiale.

    Vale solo se le n osservazioni sono indipendenti. Per il cubo non lo sono:
    si riporta lo stesso, dichiarando che è un limite inferiore all'incertezza.
    """
    from scipy.stats import beta
    lo = beta.ppf(alfa / 2, k, n - k + 1) if k > 0 else 0.0
    hi = beta.ppf(1 - alfa / 2, k + 1, n - k) if k < n else 1.0
    return float(lo), float(hi)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--stagione", default="2026-27")
    ap.add_argument("--as-of", default="2026-09-11")
    a = ap.parse_args()

    with open(ROOT / "data" / "l2" / f"cubo_{a.stagione}.pkl", "rb") as f:
        salvato = pickle.load(f)
    cubo = salvato["cubo"]
    r = cubo.risultati
    casa = np.array([v[0] for v in r.values()])
    tra = np.array([v[1] for v in r.values()])
    n_scen = int(cubo.fantavoto.shape[0])

    # la coda per singolo scenario: qui si vede se gli scenari sono ripetizioni
    # dello stesso modello o modelli diversi
    per_scenario = collections.defaultdict(list)
    for (s, _g, _sq), v in r.items():
        per_scenario[s].extend([v[0], v[1]])
    code = np.array([float(np.mean(np.asarray(v) >= 6))
                     for v in per_scenario.values()])
    medie = np.array([float(np.mean(v)) for v in per_scenario.values()])

    part = pd.read_parquet(PROC / "l2_partite.parquet")
    tr, filtro = cfg.partite_di_addestramento(part, a.as_of)
    oc = tr.gol_casa.values.astype(int)
    ot = tr.gol_trasferta.values.astype(int)
    ultime3 = sorted(s for s in tr.stagione.unique() if s != a.stagione)[-3:]
    u3 = tr[tr.stagione.isin(ultime3)]

    sim_tot = np.concatenate([casa, tra])
    oss_tot = np.concatenate([oc, ot])
    oss_u3 = np.concatenate([u3.gol_casa.values.astype(int),
                             u3.gol_trasferta.values.astype(int)])

    k_oss = int((oss_tot >= 6).sum())
    ic_oss = clopper_pearson(k_oss, len(oss_tot))
    # per il cubo l'unità indipendente è lo scenario, non la squadra-partita:
    # l'errore standard si calcola sulla dispersione fra scenari
    se_scen = float(code.std(ddof=1) / np.sqrt(len(code)))

    fuori = {
        "stagione": a.stagione,
        "as_of": a.as_of,
        "cubo": {
            "scenari": n_scen,
            "partite_totali": len(r),
            "partite_per_scenario": len(r) // max(n_scen, 1),
            "squadra_partita": int(len(sim_tot)),
            "casa": descrivi(casa),
            "trasferta": descrivi(tra),
            "totale": descrivi(sim_tot),
            "coda_per_scenario": {
                "media": float(code.mean()),
                "sd": float(code.std(ddof=1)),
                "minimo": float(code.min()),
                "massimo": float(code.max()),
                "errore_standard_della_media": se_scen,
                "ic95_approssimato": [float(code.mean() - 1.96 * se_scen),
                                      float(code.mean() + 1.96 * se_scen)],
            },
            "media_gol_per_scenario": {
                "media": float(medie.mean()), "sd": float(medie.std(ddof=1)),
                "minimo": float(medie.min()), "massimo": float(medie.max()),
            },
        },
        "osservato": {
            "filtro": filtro,
            "partite": int(len(tr)),
            "stagioni": sorted(tr.stagione.unique().tolist()),
            "casa": descrivi(oc),
            "trasferta": descrivi(ot),
            "totale": descrivi(oss_tot),
            "ic95_p_sei_o_piu": list(ic_oss),
            "ultime_tre_stagioni": {
                "stagioni": ultime3,
                "totale": descrivi(oss_u3),
            },
        },
    }
    percorso = OUT / f"coda_gol_{a.stagione}.json"
    percorso.write_text(json.dumps(fuori, indent=1), encoding="utf-8")

    def stampa(nome, d):
        print(f"{nome:26s} n {d['n']:6d} media {d['media']:.5f} "
              f"var {d['varianza']:.5f} P(0) {d['p_zero'] * 100:6.3f}% "
              f"P(>=6) {d['p_sei_o_piu'] * 100:6.4f}% max {d['massimo']}")

    print(f"cubo: {n_scen} scenari, {len(r)} partite, {len(sim_tot)} squadra-partita")
    for k in ("casa", "trasferta", "totale"):
        stampa(f"cubo {k}", fuori["cubo"][k])
    print(f"\nosservato: {len(tr)} partite, {len(fuori['osservato']['stagioni'])} stagioni")
    for k in ("casa", "trasferta", "totale"):
        stampa(f"osservato {k}", fuori["osservato"][k])
    stampa(f"osservato {'+'.join(ultime3)}", fuori["osservato"]["ultime_tre_stagioni"]["totale"])
    cs = fuori["cubo"]["coda_per_scenario"]
    print(f"\nP(>=6) per scenario: media {cs['media'] * 100:.4f}% "
          f"sd {cs['sd'] * 100:.4f}% da {cs['minimo'] * 100:.4f}% a "
          f"{cs['massimo'] * 100:.4f}%")
    print(f"  errore standard sulla media (unita' = scenario): "
          f"{cs['errore_standard_della_media'] * 100:.4f}%, "
          f"IC95 [{cs['ic95_approssimato'][0] * 100:.4f}%, "
          f"{cs['ic95_approssimato'][1] * 100:.4f}%]")
    print(f"  osservato {fuori['osservato']['totale']['p_sei_o_piu'] * 100:.4f}% "
          f"IC95 [{ic_oss[0] * 100:.4f}%, {ic_oss[1] * 100:.4f}%]")
    print(f"\nscritto {percorso}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
