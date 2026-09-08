"""Livello 2, pezzo 1-bis — il modello di partita nelle sue versioni migliori.

La prima prova ha stimato il modello su tre stagioni con forze fisse, e ha
perso contro la semplice media storica. Non basta per bocciare la proposta: li'
si parlava anche di decadimento temporale (le partite vecchie contano meno) e
di un prior sulla forza difensiva. Qui il modello viene messo nelle condizioni
migliori che la proposta stessa descrive, e confrontato con le stesse
alternative povere:

  A  tasso base                    stessa probabilita' per tutti
  B  media storica della squadra   porte inviolate nelle stagioni di train
  C  modello, 3 stagioni           forze fisse
  D  modello, 1 stagione           solo la stagione precedente
  E  modello con decadimento       peso che scende con l'eta' della partita
  F  modello + aggiornamento       rifit dopo ogni giornata giocata del test
     in stagione                   (usa solo il passato, come farebbe in asta)

Uso: python scripts/indagine/l2_modello_partita2.py
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.optimize import minimize

ROOT = Path(__file__).resolve().parents[2]
RAW = ROOT / "data" / "raw"


def partite(anno: int) -> pd.DataFrame:
    g = pd.read_csv(RAW / "transfermarkt" / "_download" / "games.csv.gz",
                    compression="gzip")
    g = g[(g["competition_id"] == "IT1") & (g["season"] == anno)].copy()
    g["giornata"] = g["round"].astype(str).str.extract(r"(\d+)")[0].astype(float)
    g["anno"] = anno
    return g[["game_id", "giornata", "anno", "home_club_id", "away_club_id",
              "home_club_goals", "away_club_goals"]].dropna()


def stima(df, squadre, pesi=None):
    idx = {s: i for i, s in enumerate(squadre)}
    n = len(squadre)
    h = df["home_club_id"].map(idx).to_numpy()
    a = df["away_club_id"].map(idx).to_numpy()
    x = df["home_club_goals"].to_numpy(float)
    y = df["away_club_goals"].to_numpy(float)
    w = np.ones(len(df)) if pesi is None else np.asarray(pesi, float)

    def neg(p):
        att = np.concatenate([p[:n - 1], [-p[:n - 1].sum()]])
        dif = np.concatenate([p[n - 1:2 * n - 2], [-p[n - 1:2 * n - 2].sum()]])
        lam = np.exp(p[-1] + att[h] - dif[a])
        mu = np.exp(att[a] - dif[h])
        ll = w * (-lam + x * np.log(lam) - mu + y * np.log(mu))
        # prior debole verso zero: senza, le neopromosse con poche partite
        # prendono forze enormi
        return -ll.sum() + 2.0 * np.sum(p[:2 * n - 2] ** 2)

    r = minimize(neg, np.concatenate([np.zeros(2 * n - 2), [0.25]]),
                 method="L-BFGS-B",
                 bounds=[(-3, 3)] * (2 * n - 2) + [(-1, 1)])
    att = np.concatenate([r.x[:n - 1], [-r.x[:n - 1].sum()]])
    dif = np.concatenate([r.x[n - 1:2 * n - 2], [-r.x[n - 1:2 * n - 2].sum()]])
    return {"att": dict(zip(squadre, att)), "dif": dict(zip(squadre, dif)),
            "casa": r.x[-1]}


def p_cs(par, chi, avv, in_casa):
    """Probabilita' che `chi` non subisca gol contro `avv`."""
    if in_casa:
        mu = np.exp(par["att"].get(avv, 0.0) - par["dif"].get(chi, 0.0))
    else:
        mu = np.exp(par["casa"] + par["att"].get(avv, 0.0) - par["dif"].get(chi, 0.0))
    return float(np.exp(-mu))


def brier(p, y):
    return float(np.mean((np.asarray(p) - np.asarray(y)) ** 2))


def valuta(par, te):
    p, v = [], []
    for r in te.itertuples(index=False):
        p.append(p_cs(par, r.home_club_id, r.away_club_id, True))
        v.append(1.0 if r.away_club_goals == 0 else 0.0)
        p.append(p_cs(par, r.away_club_id, r.home_club_id, False))
        v.append(1.0 if r.home_club_goals == 0 else 0.0)
    return np.array(p), np.array(v)


def main():
    print("Livello 2 — modello di partita nelle sue versioni migliori\n")
    for anno_test in (2023, 2024, 2025):
        tr3 = pd.concat([partite(a) for a in range(anno_test - 3, anno_test)])
        tr1 = partite(anno_test - 1)
        te = partite(anno_test)
        squadre = sorted(set(tr3.home_club_id) | set(tr3.away_club_id)
                         | set(te.home_club_id) | set(te.away_club_id))
        # alternative povere
        cs_hist = {}
        for s in squadre:
            c = tr3[tr3.home_club_id == s]
            f = tr3[tr3.away_club_id == s]
            n = len(c) + len(f)
            if n:
                cs_hist[s] = ((c.away_club_goals == 0).sum()
                              + (f.home_club_goals == 0).sum()) / n
        base = float(np.mean(list(cs_hist.values()))) if cs_hist else 0.28
        _, veri = valuta({"att": {}, "dif": {}, "casa": 0.0}, te)
        p_base = np.full(len(veri), base)
        p_hist = []
        for r in te.itertuples(index=False):
            p_hist.append(cs_hist.get(r.home_club_id, base))
            p_hist.append(cs_hist.get(r.away_club_id, base))
        # modelli
        eta = (anno_test - tr3["anno"]).to_numpy(float)
        pesi = np.exp(-0.6 * eta)
        modelli = {
            "C modello, 3 stagioni": stima(tr3, squadre),
            "D modello, 1 stagione": stima(tr1, squadre),
            "E modello con decadimento": stima(tr3, squadre, pesi=pesi),
        }
        print(f"test {anno_test}: {len(te)} partite, quota reale porte inviolate "
              f"{veri.mean():.3f}")
        print(f"   A tasso base                   {brier(p_base, veri):.4f}")
        print(f"   B media storica della squadra  {brier(p_hist, veri):.4f}")
        for et, par in modelli.items():
            p, _ = valuta(par, te)
            print(f"   {et:30s} {brier(p, veri):.4f}")
        # F: aggiornamento in stagione, rifit ogni 5 giornate usando solo il passato
        pf, vf = [], []
        for g in range(1, 39):
            gior = te[te.giornata == g]
            if not len(gior):
                continue
            passato = pd.concat([tr1, te[te.giornata < g]])
            par = stima(passato, squadre) if g > 1 else modelli["D modello, 1 stagione"]
            p, v = valuta(par, gior)
            pf.extend(p)
            vf.extend(v)
        print(f"   F modello aggiornato in stagione {brier(pf, vf):.4f}")
        print()


if __name__ == "__main__":
    main()
