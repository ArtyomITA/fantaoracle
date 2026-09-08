"""Indagine Livello 2, pezzo 1 — il modello di partita regge?

Il cubo TABELLINO parte dal risultato della partita: gol casa e gol trasferta
da un Poisson con forze di attacco e difesa per squadra, piu' la correzione di
Dixon e Coles per i punteggi bassi. Da li' derivano porta inviolata,
modificatore e ripartizione dei gol.

Qui il modello viene stimato davvero, fuori campione (fit sulle stagioni
precedenti, misura su quella dopo), e confrontato con le alternative povere che
deve battere per avere senso:

  tasso base       la stessa probabilita' per tutti (quota storica di porte
                   inviolate)
  media storica    porte inviolate della squadra nella stagione precedente
  Dixon-Coles      il modello proposto

Gate dichiarato nella proposta: Brier sulla porta inviolata sotto 0,19 contro
0,205 del tasso base. Qui si verifica se e' raggiungibile, con che margine, e
se il guadagno viene dal modello o si sarebbe ottenuto con la media storica.

Non implementa il Livello 2: stima in memoria e stampa.

Uso: python scripts/indagine/l2_modello_partita.py
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
    return g[["game_id", "home_club_id", "away_club_id",
              "home_club_goals", "away_club_goals"]].dropna()


def tau(x, y, lam, mu, rho):
    """Correzione di Dixon e Coles sui punteggi bassi (0-0, 1-0, 0-1, 1-1)."""
    out = np.ones_like(lam, dtype=float)
    m = (x == 0) & (y == 0)
    out[m] = 1 - lam[m] * mu[m] * rho
    m = (x == 0) & (y == 1)
    out[m] = 1 + lam[m] * rho
    m = (x == 1) & (y == 0)
    out[m] = 1 + mu[m] * rho
    m = (x == 1) & (y == 1)
    out[m] = 1 - rho
    return np.clip(out, 1e-6, None)


def stima(df: pd.DataFrame, squadre: list[int], usa_dc: bool = True):
    idx = {s: i for i, s in enumerate(squadre)}
    n = len(squadre)
    h = df["home_club_id"].map(idx).to_numpy()
    a = df["away_club_id"].map(idx).to_numpy()
    x = df["home_club_goals"].to_numpy(float)
    y = df["away_club_goals"].to_numpy(float)

    def neg_loglik(p):
        att = np.concatenate([p[:n - 1], [-p[:n - 1].sum()]])
        dif = np.concatenate([p[n - 1:2 * n - 2], [-p[n - 1:2 * n - 2].sum()]])
        casa, rho = p[-2], p[-1]
        lam = np.exp(casa + att[h] - dif[a])
        mu = np.exp(att[a] - dif[h])
        ll = (-lam + x * np.log(lam) - mu + y * np.log(mu))
        if usa_dc:
            ll = ll + np.log(tau(x, y, lam, mu, rho))
        return -ll.sum()

    p0 = np.concatenate([np.zeros(2 * n - 2), [0.25, -0.05]])
    r = minimize(neg_loglik, p0, method="L-BFGS-B",
                 bounds=[(-3, 3)] * (2 * n - 2) + [(-1, 1), (-0.2, 0.2)])
    att = np.concatenate([r.x[:n - 1], [-r.x[:n - 1].sum()]])
    dif = np.concatenate([r.x[n - 1:2 * n - 2], [-r.x[n - 1:2 * n - 2].sum()]])
    return {"att": dict(zip(squadre, att)), "dif": dict(zip(squadre, dif)),
            "casa": r.x[-2], "rho": r.x[-1], "ok": r.success}


def p_porta_inviolata(par, casa_id, fuori_id, per_chi="casa"):
    """Probabilita' che la squadra indicata non subisca gol."""
    att, dif = par["att"], par["dif"]
    if per_chi == "casa":                 # subisce i gol della trasferta
        mu = np.exp(att.get(fuori_id, 0.0) - dif.get(casa_id, 0.0))
    else:
        mu = np.exp(par["casa"] + att.get(casa_id, 0.0) - dif.get(fuori_id, 0.0))
    return float(np.exp(-mu))


def brier(p, y):
    return float(np.mean((np.asarray(p) - np.asarray(y)) ** 2))


def main():
    print("Livello 2, pezzo 1 — il modello di partita e le sue alternative povere\n")
    for anno_train, anno_test in [(2022, 2023), (2023, 2024)]:
        tr = pd.concat([partite(a) for a in range(anno_train - 2, anno_train + 1)])
        te = partite(anno_test)
        squadre = sorted(set(tr.home_club_id) | set(tr.away_club_id)
                         | set(te.home_club_id) | set(te.away_club_id))
        par = stima(tr, squadre)
        # verita': porta inviolata di ciascuna delle due squadre in ogni partita
        veri, prev_dc, prev_base, prev_storico = [], [], [], []
        # media storica: quota di porte inviolate della squadra nel train
        cs_storico = {}
        for s in squadre:
            casa = tr[tr.home_club_id == s]
            fuori = tr[tr.away_club_id == s]
            n = len(casa) + len(fuori)
            if n:
                cs_storico[s] = ((casa.away_club_goals == 0).sum()
                                 + (fuori.home_club_goals == 0).sum()) / n
        base = np.mean(list(cs_storico.values())) if cs_storico else 0.28
        for r in te.itertuples(index=False):
            for chi, avv, subiti in ((r.home_club_id, r.away_club_id, r.away_club_goals),
                                     (r.away_club_id, r.home_club_id, r.home_club_goals)):
                veri.append(1.0 if subiti == 0 else 0.0)
                lato = "casa" if chi == r.home_club_id else "fuori"
                prev_dc.append(p_porta_inviolata(par, r.home_club_id, r.away_club_id,
                                                 "casa" if lato == "casa" else "fuori"))
                prev_base.append(base)
                prev_storico.append(cs_storico.get(chi, base))
        veri = np.array(veri)
        print(f"train {anno_train - 2}-{anno_train}, test {anno_test}: "
              f"{len(te)} partite, {len(veri)} porte in gioco, "
              f"quota reale di porte inviolate {veri.mean():.3f}")
        print(f"   convergenza: {par['ok']} | vantaggio casa {par['casa']:.3f} | "
              f"correzione punteggi bassi {par['rho']:+.3f}")
        for et, p in [("tasso base (tutti uguali)", prev_base),
                      ("media storica della squadra", prev_storico),
                      ("modello di partita", prev_dc)]:
            print(f"   Brier {et:30s} {brier(p, veri):.4f}")
        print()


if __name__ == "__main__":
    main()
