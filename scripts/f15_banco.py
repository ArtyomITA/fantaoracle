"""Livello 1 — banco di prova: misura il comportamento ATTUALE, tre livelli separati.

Serve una fotografia della vecchia architettura prima di cambiarla, altrimenti
ogni miglioramento futuro non ha un termine di paragone. Il banco non decide
niente e non tocca modelli: legge quello che c'e' e stampa numeri.

Tre livelli, tenuti separati perche' misurano cose diverse:

  1. PREVISIONI   quanto sono giuste le stime, indipendentemente dall'asta
                  (prezzo: errore e intervalli; punti: errore e ordinamento;
                  presenze: errore e calibrazione)
  2. SIMULAZIONE  quanto la stagione simulata somiglia a quella vera
                  (punti per giornata, correlazione fra compagni di squadra,
                  correlazione portiere-difensori, quante volte scatta il
                  modificatore)
  3. DECISIONI    cosa fa il bot in asta (in `check_o3_cassa.py`, non qui:
                  richiede di giocare le aste ed e' molto piu' lento)

Criteri di accettazione: NON sono fissati qui. Questo script produce la
baseline; le soglie per accettare una modifica futura vanno decise guardando
questi numeri e scritte prima dell'esperimento.

Avvertenze di lettura, valide per tutti i numeri prodotti:
  - le stagioni 2024/25 e 2025/26 sono state consultate molte volte: non sono
    piu' un test pulito, e cambiare seed non le ripulisce;
  - cento calendari sulle stesse rose non sono cento stagioni indipendenti:
    l'incertezza vera e' fra stagioni, non fra calendari;
  - il 2025/26 non ha prezzi d'asta osservati: per il prezzo resta diagnostico.

Uso: python scripts/f15_banco.py [--stagioni 2024-25,2025-26]
"""
from __future__ import annotations

import json
import pickle
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
PROC = ROOT / "data" / "processed"

from fantabot.models import ROLES  # noqa: E402
from fantabot.rules import clean_sheets  # noqa: E402

BUDGET = 500


def punti_reali(season: str) -> pd.Series:
    v = pd.read_parquet(PROC / f"votes_{season}.parquet")
    if "sv" in v.columns:
        v = v[v["sv"].fillna(0) == 0]
    v = v.copy()
    v["master_id"] = v["master_id"].astype(str)
    try:
        cs = clean_sheets(ROOT, season)
        v["fantavoto"] = v["fantavoto"] + [1.0 if (m, g) in cs else 0.0
                                           for m, g in zip(v["master_id"], v["giornata"])]
    except FileNotFoundError:
        pass
    return v.groupby("master_id")["fantavoto"].sum()


def presenze_reali(season: str) -> pd.Series:
    v = pd.read_parquet(PROC / f"votes_{season}.parquet")
    if "sv" in v.columns:
        v = v[v["sv"].fillna(0) == 0]
    return v.assign(master_id=v["master_id"].astype(str)).groupby("master_id").size()


def livello1_previsioni(season: str) -> dict:
    """Prezzo, punti e presenze: quanto sbaglia il modello che gira oggi."""
    pred = json.loads((PROC / f"b_predictions_{season}.json").read_text("utf-8"))
    d = pd.read_parquet(PROC / f"players_{season}.parquet")
    d["master_id"] = d["master_id"].astype(str)
    pts, pres = punti_reali(season), presenze_reali(season)
    r = pd.DataFrame({
        "master_id": d["master_id"],
        "nuovo": d["nuovo_in_serie_a"].fillna(0).astype(int),
        "prezzo_vero": d["target_mean_pct_all_estiva"].astype(float) * BUDGET,
        "n_aste": d["target_n_obs_all_estiva"].fillna(0).astype(float)})
    for c in ("q10", "q50", "q90", "value", "value_up", "pres"):
        r[c] = r["master_id"].map(lambda m, c=c: pred.get(m, {}).get(c))
    r["punti_veri"] = r["master_id"].map(pts).fillna(0.0)
    r["pres_vere"] = r["master_id"].map(pres).fillna(0)
    out = {"stagione": season, "righe": len(r)}

    pz = r[(r["n_aste"] >= 2) & r["prezzo_vero"].notna() & r["q50"].notna()]
    if len(pz):
        e = pz["q50"] - pz["prezzo_vero"]
        cop = ((pz["prezzo_vero"] >= pz["q10"]) & (pz["prezzo_vero"] <= pz["q90"])).mean()
        out["prezzo"] = {
            "campione": len(pz), "nota": "target = prezzo medio fra aste estive reali",
            "mae": round(float(e.abs().mean()), 2), "bias": round(float(e.mean()), 2),
            "rho": round(float(pz["q50"].corr(pz["prezzo_vero"], method="spearman")), 4),
            "sotto_q10": round(float((pz["prezzo_vero"] < pz["q10"]).mean()), 3),
            "sopra_q90": round(float((pz["prezzo_vero"] > pz["q90"]).mean()), 3),
            "copertura": round(float(cop), 3),
            "ampiezza_mediana": round(float((pz["q90"] - pz["q10"]).median()), 2)}
    else:
        out["prezzo"] = {"campione": 0, "nota": "nessun prezzo d'asta osservato: diagnostico"}

    v = r[r["value"].notna()]
    ev = v["value"] - v["punti_veri"]
    out["punti"] = {"campione": len(v), "mae": round(float(ev.abs().mean()), 2),
                    "bias": round(float(ev.mean()), 2),
                    "rho": round(float(v["value"].corr(v["punti_veri"], method="spearman")), 4),
                    "sopra_value_up": round(float((v["punti_veri"] > v["value_up"]).mean()), 3)}
    pp = r[r["pres"].notna()]
    ep = pp["pres"] - pp["pres_vere"]
    out["presenze"] = {"campione": len(pp), "mae": round(float(ep.abs().mean()), 2),
                       "bias": round(float(ep.mean()), 2)}
    return out


def livello2_simulazione(season: str) -> dict:
    """Quanto la stagione simulata somiglia a quella vera, sui dati reali."""
    v = pd.read_parquet(PROC / f"votes_{season}.parquet")
    if "sv" in v.columns:
        v = v[v["sv"].fillna(0) == 0]
    v = v.copy()
    v["master_id"] = v["master_id"].astype(str)
    d = pd.read_parquet(PROC / f"players_{season}.parquet")
    d["master_id"] = d["master_id"].astype(str)
    sq = dict(zip(d["master_id"], d["squadra"]))
    ruolo = dict(zip(d["master_id"], d["ruolo"]))
    v["squadra"] = v["master_id"].map(sq)
    v["ruolo"] = v["master_id"].map(ruolo)
    col = "voto" if "voto" in v.columns else "fantavoto"
    med = v.groupby("master_id")[col].transform("mean")
    v["scarto"] = v[col] - med
    per_sq = v.groupby(["squadra", "giornata"])["scarto"].mean()
    tot = float(v["scarto"].var())
    fra = float(per_sq.var())
    # correlazione fra compagni nella stessa giornata (scarto dalla propria media)
    coppie = []
    for (s, g), grp in v.groupby(["squadra", "giornata"]):
        x = grp["scarto"].to_numpy()
        if len(x) >= 4:
            coppie.append(float(np.mean(np.outer(x, x)[np.triu_indices(len(x), 1)])))
    pd_corr = np.nan
    gk = v[v["ruolo"] == "P"].set_index(["squadra", "giornata"])["scarto"]
    df = v[v["ruolo"] == "D"].groupby(["squadra", "giornata"])["scarto"].mean()
    j = pd.concat([gk[~gk.index.duplicated()], df], axis=1, join="inner")
    if len(j) > 30:
        pd_corr = float(j.iloc[:, 0].corr(j.iloc[:, 1]))
    return {"stagione": season, "colonna": col,
            "varianza_totale_scarto": round(tot, 4),
            "varianza_media_squadra_giornata": round(fra, 4),
            "quota_squadra_giornata": round(fra / tot, 4) if tot else None,
            "covarianza_media_fra_compagni": round(float(np.mean(coppie)), 4) if coppie else None,
            "correlazione_portiere_difensori": round(pd_corr, 4) if pd_corr == pd_corr else None,
            "nota": "misure sui voti REALI: sono il bersaglio che il simulatore deve riprodurre"}


def main():
    args = sys.argv[1:]
    stagioni = (args[args.index("--stagioni") + 1].split(",") if "--stagioni" in args
                else ["2024-25", "2025-26"])
    print("BANCO DI PROVA — comportamento attuale (nessuna modifica)\n")
    print("Avvertenze: 2024/25 e 2025/26 gia' consultate molte volte (non piu' test")
    print("puliti); il 2025/26 non ha prezzi d'asta osservati.\n")
    for s in stagioni:
        print(f"===== {s} =====")
        p = livello1_previsioni(s)
        print(f" PREVISIONI su {p['righe']} giocatori")
        pz = p["prezzo"]
        if pz["campione"]:
            print(f"  prezzo (n={pz['campione']}, {pz['nota']}):")
            print(f"    errore medio {pz['mae']} cr, scarto {pz['bias']:+} cr, "
                  f"ordinamento {pz['rho']}")
            print(f"    intervallo q10-q90: copre {pz['copertura']:.0%} "
                  f"(sotto {pz['sotto_q10']:.0%} / sopra {pz['sopra_q90']:.0%}), "
                  f"ampiezza mediana {pz['ampiezza_mediana']} cr")
        else:
            print(f"  prezzo: {pz['nota']}")
        pt, pr = p["punti"], p["presenze"]
        print(f"  punti (n={pt['campione']}): errore {pt['mae']}, scarto {pt['bias']:+}, "
              f"ordinamento {pt['rho']}, sopra la stima alta {pt['sopra_value_up']:.0%}")
        print(f"  presenze (n={pr['campione']}): errore {pr['mae']} partite, "
              f"scarto {pr['bias']:+}")
        s2 = livello2_simulazione(s)
        print(f" SIMULAZIONE — bersagli dai voti reali (colonna {s2['colonna']}):")
        print(f"  effetto squadra x giornata: {s2['quota_squadra_giornata']:.1%} "
              f"della varianza (varianza {s2['varianza_media_squadra_giornata']})")
        print(f"  covarianza media fra compagni: {s2['covarianza_media_fra_compagni']}")
        print(f"  correlazione portiere-difensori: {s2['correlazione_portiere_difensori']}")
        print()
    print("DECISIONI D'ASTA: vedi scripts/indagine/check_o3_cassa.py (gioca le aste).")


if __name__ == "__main__":
    main()
