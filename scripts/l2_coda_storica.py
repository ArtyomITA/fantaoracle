"""Coda dei gol su calendari storici, con il calcolo analitico.

## Che cosa correggeva la versione precedente

`scripts/l2_diagnosi_coda.py` confrontava le repliche del calendario 2026-27
con l'osservato di **altre** stagioni: numerosità diverse, squadre diverse,
calendario diverso. Non era un confronto sullo stesso oggetto, e la
scomposizione della varianza non poteva identificare la causa dell'eccesso.

Qui il confronto è omogeneo:

- si sceglie una stagione bersaglio **conclusa**;
- il modello si stima con dati **anteriori** al suo inizio;
- si prevede lo **stesso** calendario che è stato giocato, partita per partita;
- si confrontano le stesse statistiche sulle stesse partite, entrambe le
  squadre, stessa numerosità.

## Perché il calcolo è analitico

Il ramo di ricerca ha verificato che, con la correzione di Dixon-Coles, le
marginali della nostra matrice dei risultati restano Poisson entro 1e-16, e che
la coda dell'implementazione coincide con quella analitica entro 1e-9. Quindi
`P(G >= k | lambda)` si calcola in forma chiusa e la coda prevista non porta
rumore Monte Carlo: resta solo l'incertezza vera, quella dei parametri.

Le simulazioni servono altrove — dipendenze e distribuzioni congiunte — non per
una quantità che ha una forma chiusa.

## Trattamenti

- `punto`: il modello al punto stimato, nessuna incertezza sui parametri;
- `hessiana`: incertezza dall'inversa dell'hessiana della verosimiglianza
  pesata e penalizzata, cioè il comportamento attuale;
- `decadimento_lento`: stesso trattamento del punto ma con `xi` dimezzato, cioè
  più partite che pesano. È una delle due correzioni ammesse dal protocollo
  (regolarizzazione e decadimento delle forze) e serve a vedere se la coda
  dipende da quanto poco campione effettivo entra nella stima.

Nessun trattamento viene scelto guardando il risultato: i tre sono dichiarati
qui, e il confronto si legge come esce.

Uso:
    python scripts/l2_coda_storica.py --stagioni 2023-24 2024-25 2025-26
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import poisson

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from fantabot.tabellino import configurazione as cfg      # noqa: E402

PROC = ROOT / "data" / "processed"
OUT = ROOT / "data" / "l2"
SOGLIA = 6           # la coda che ci interessa: sei o più gol di una squadra


def coda_analitica(lam: np.ndarray, k: int = SOGLIA) -> np.ndarray:
    """P(G >= k) per ogni intensità, in forma chiusa.

    Vale perché la correzione di Dixon-Coles conserva le marginali: la
    verifica numerica è in `data/l3/ricerca3/a_coda_dixon_coles.json`, dove lo
    scarto fra questa formula e la matrice dell'implementazione è sotto 1e-9.

    Differenza dichiarata: qui si usa la Poisson **intera**, mentre la matrice
    del simulatore è troncata a dodici gol e rinormalizzata. Alle intensità di
    una partita di Serie A lo scarto relativo sulla coda a sei gol vale circa
    1e-6, e cresce con l'intensità: 2,3e-5 a lambda 2,2, 1,8e-4 a lambda 3,0.
    Per il confronto con l'osservato è trascurabile; per un uso a intensità
    più alte non lo sarebbe.
    """
    return poisson.sf(k - 1, lam)


def clopper_pearson(k: int, n: int, alfa: float = 0.05) -> tuple[float, float]:
    from scipy.stats import beta
    lo = beta.ppf(alfa / 2, k, n - k + 1) if k > 0 else 0.0
    hi = beta.ppf(1 - alfa / 2, k + 1, n - k) if k < n else 1.0
    return float(lo), float(hi)


def valuta(mp, casa, tra) -> dict:
    """Le quantità previste per un dato modello, tutte in forma chiusa."""
    lam, mu = mp.intensita(casa, tra)
    tutte = np.concatenate([lam, mu])
    return {
        "media_prevista": float(tutte.mean()),
        "p_coda_prevista": float(coda_analitica(tutte).mean()),
        "p_zero_prevista": float(poisson.pmf(0, tutte).mean()),
        "intensita_massima": float(tutte.max()),
        "intensita_minima": float(tutte.min()),
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--stagioni", nargs="*",
                    default=["2023-24", "2024-25", "2025-26"])
    ap.add_argument("--campioni", type=int, default=200,
                    help="estrazioni di parametri per i trattamenti con incertezza")
    ap.add_argument("--seme", type=int, default=20260908)
    a = ap.parse_args()

    part = pd.read_parquet(PROC / "l2_partite.parquet")
    part["data"] = pd.to_datetime(part["data"])
    righe = []

    for st in a.stagioni:
        cal = part[part.stagione == st].dropna(subset=["gol_casa", "gol_trasferta"])
        if cal.empty:
            print(f"{st}: nessuna partita conclusa, salto")
            continue
        # il fit si ferma il giorno prima della prima partita della stagione
        as_of = (cal["data"].min() - pd.Timedelta(days=1)).strftime("%Y-%m-%d")
        casa, tra = cal.casa.values, cal.trasferta.values
        oss = np.concatenate([cal.gol_casa.values.astype(int),
                              cal.gol_trasferta.values.astype(int)])
        n = len(oss)
        k_oss = int((oss >= SOGLIA).sum())
        ic = clopper_pearson(k_oss, n)
        base_oss = {
            "stagione": st, "as_of": as_of, "partite": int(len(cal)),
            "squadra_partita": n,
            "media_osservata": float(oss.mean()),
            "p_coda_osservata": float(k_oss / n),
            "p_zero_osservata": float((oss == 0).mean()),
            "ic_coda_osservata": list(ic),
            "massimo_osservato": int(oss.max()),
        }

        rng = np.random.default_rng(a.seme)
        for nome, iper, con_incertezza in (
                ("punto", None, False),
                ("hessiana", None, True),
                ("decadimento_lento", "meta_xi", False)):
            ip = None
            if iper == "meta_xi":
                # prima si costruisce col percorso normale per leggere lo `xi`
                # scelto dalla procedura, poi lo si dimezza: cosi' il
                # trattamento e' definito rispetto alla scelta della griglia e
                # non a un numero fisso deciso a mano
                _, conf0, _ = cfg.costruisci_modello_partita(
                    part, as_of, squadre=None, stagione_bersaglio=st,
                    con_incertezza=False, percorsi_ingresso=[], etichetta="base")
                ip = dict(conf0.iperparametri)
                ip["xi"] = float(ip["xi"]) / 2.0
            mp, conf, impronta = cfg.costruisci_modello_partita(
                part, as_of, ip, squadre=None, stagione_bersaglio=st,
                con_incertezza=con_incertezza, percorsi_ingresso=[],
                etichetta=f"coda {st} {nome}")

            if con_incertezza:
                copie = mp.campiona_parametri(rng, a.campioni)
                v = [valuta(c, casa, tra) for c in copie]
                prev = {
                    "media_prevista": float(np.mean([x["media_prevista"] for x in v])),
                    "p_coda_prevista": float(np.mean([x["p_coda_prevista"] for x in v])),
                    "p_zero_prevista": float(np.mean([x["p_zero_prevista"] for x in v])),
                    "intensita_massima": float(np.max([x["intensita_massima"] for x in v])),
                    "sd_coda_fra_campioni": float(np.std(
                        [x["p_coda_prevista"] for x in v], ddof=1)),
                    "campioni": a.campioni,
                }
            else:
                prev = valuta(mp, casa, tra)
                prev["sd_coda_fra_campioni"] = 0.0
                prev["campioni"] = 1

            r = dict(base_oss)
            r.update({
                "trattamento": nome,
                "xi": float(conf.iperparametri["xi"]),
                "lam_pen": float(conf.iperparametri["lam_pen"]),
                "impronta": impronta[:12],
                "partite_addestramento": int(conf.n_partite_addestramento),
                "peso_totale": float(conf.peso_totale),
                **prev,
            })
            r["rapporto_coda"] = (r["p_coda_prevista"] / r["p_coda_osservata"]
                                  if r["p_coda_osservata"] > 0 else None)
            r["coda_dentro_intervallo_osservato"] = bool(
                ic[0] <= r["p_coda_prevista"] <= ic[1])
            righe.append(r)
            print(f"{st} {nome:18s} xi {r['xi']:.4f} | coda prevista "
                  f"{r['p_coda_prevista'] * 100:6.4f}% contro osservata "
                  f"{r['p_coda_osservata'] * 100:6.4f}% "
                  f"[{ic[0] * 100:.4f}%, {ic[1] * 100:.4f}%] | "
                  f"rapporto {r['rapporto_coda']:.2f} | "
                  f"{'DENTRO' if r['coda_dentro_intervallo_osservato'] else 'fuori'}")

    d = pd.DataFrame(righe)
    d.to_csv(OUT / "coda_storica.csv", index=False)
    (OUT / "coda_storica.json").write_text(
        json.dumps({
            "soglia": SOGLIA,
            "metodo": ("coda analitica P(G >= k | lambda) sulle marginali "
                       "Poisson; verifica dell'identita' in "
                       "data/l3/ricerca3/a_coda_dixon_coles.json"),
            "campioni_incertezza": a.campioni, "seme": a.seme,
            "righe": righe,
        }, indent=1), encoding="utf-8")
    print(f"\nscritto {OUT / 'coda_storica.csv'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
