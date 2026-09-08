"""Punti 1 e 2 — due seggi B nella stessa asta, con politiche diverse.

Il problema del banco: contro i bot disponibili B vince il 99-100%, quindi
nessun confronto puo' misurare se una politica d'asta sia migliore di
un'altra. Il vantaggio di B viene dal modello valore, e nessun avversario lo
usa. Qui si toglie il soffitto nel modo piu' diretto: **due seggi B nella
stessa asta**, con la stessa identica testa e una sola differenza nel modo di
fare le offerte. Si contendono gli stessi giocatori, quindi il confronto e'
appaiato al massimo grado e uno dei due deve perdere.

Politiche a confronto (una per seggio):
  attuale   tetto dei titolari = q90 + 0.5 * prezzo-ombra
  variante  tetto dei titolari = q90 + 0.5 * prezzo-ombra + k * dispersione
            del prezzo fra aste diverse

La variante nasce da una misura precisa: il q90 e' tarato sul prezzo MEDIO fra
aste, e in una singola asta il prezzo lo supera il 16,9% delle volte invece del
10%. La dispersione fra aste (`ref_price_sd` nel pack) e' esattamente la
quantita' che manca. Non e' "offrire di piu' perche' si e' risparmiato": e'
correggere un tetto tarato sulla grandezza sbagliata.

CRITERI, fissati prima di guardare i risultati:
  - il seggio con la variante deve vincere piu' scontri diretti dell'altro, con
    intervallo di confidenza appaiato che non contenga la parita';
  - la cassa lasciata dalla variante deve essere piu' bassa di almeno 20
    crediti (soglia piu' bassa dell'O3b perche' qui i due seggi si tolgono
    giocatori a vicenda e la cassa non puo' scendere quanto in un tavolo
    normale);
  - se un intervallo attraversa la soglia: INCONCLUDENTE, e si dice.

Uso: python scripts/indagine/o3c_due_seggi.py [--aste 20] [--k 0.5]
"""
from __future__ import annotations

import json
import pickle
import random
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from fantabot.bots.bot_a import ABot  # noqa: E402
from fantabot.bots.bot_b import BBot  # noqa: E402
from fantabot.bots.bot_c import CBot  # noqa: E402
from fantabot.engine.auction import AuctionEngine  # noqa: E402
from fantabot.models import ROLES  # noqa: E402
from fantabot.season.simulate import simulate_season  # noqa: E402

TAVOLO = ["B", "B", "A+", "A", "C:informato", "C:stars_scrubs",
          "C:semitop", "C:tifoso", "C:ancorato", "C:tirchio"]
SEED_BASE = 30_000
SOGLIA_CASSA = 20.0


class BVariante(BBot):
    """Come B, ma il tetto dei titolari tiene conto di quanto il prezzo dello
    stesso giocatore varia da un'asta all'altra."""

    def __init__(self, *a, k_dispersione: float = 0.5, pool_sd: dict | None = None, **kw):
        super().__init__(*a, **kw)
        self.k_dispersione = float(k_dispersione)
        self.pool_sd = pool_sd or {}

    def _max_bid_for(self, pid: str) -> float:
        base = super()._max_bid_for(pid)
        if pid in self.starter_targets:
            return base + self.k_dispersione * self.pool_sd.get(pid, 0.0)
        return base


def costruisci(spec, rng, pack, indice, k, sd_crediti):
    if spec == "B":
        if indice == 1:                      # il secondo seggio B usa la variante
            return BVariante(rng, pack.b_predictions,
                             objective=getattr(pack, "b_objective", None),
                             k_dispersione=k, pool_sd=sd_crediti)
        return BBot(rng, pack.b_predictions,
                    objective=getattr(pack, "b_objective", None))
    if spec == "A":
        return ABot(rng, price_list=pack.a_price_list)
    if spec == "A+":
        return ABot(rng, price_list=pack.a_price_list, flexible=True)
    prof = spec.split(":", 1)[1]
    fav = (rng.choice(sorted({p.team for p in pack.players.values()}))
           if prof == "tifoso" else None)
    hint = pack.a_price_list if prof == "informato" else None
    return CBot(rng, prof, fav_team=fav, hint_prices=hint)


def una_asta(pack, seed, k, sd_crediti):
    rng = random.Random(seed)
    quanti_b = 0
    bots = []
    for i, s in enumerate(TAVOLO):
        idx = quanti_b if s == "B" else 0
        if s == "B":
            quanti_b += 1
        bots.append(costruisci(s, random.Random(seed * 1000 + i), pack, idx, k, sd_crediti))
    eng = AuctionEngine(dict(pack.players), bots, pack.quotas, pack.budget, rng)
    teams = eng.run()
    key, seen = {}, {}
    for t in teams:
        n = seen.get(t.bot_name, 0)
        seen[t.bot_name] = n + 1
        key[t.team_id] = t.bot_name if n == 0 else f"{t.bot_name}#{n + 1}"
    rosters = {key[t.team_id]: {r: [pid for pid, _ in t.roster[r]] for r in ROLES}
               for t in teams}
    res = simulate_season(rosters, pack.votes_by_g, n_calendars=100, seed=seed + 7,
                          voti_by_g=pack.voti_by_g, use_mod_difesa=pack.use_mod_difesa)
    win, rank = res.h2h_win_rate(), res.h2h_avg_rank()
    out = {}
    for etichetta, chiave in [("attuale", "B"), ("variante", "B#2")]:
        t = next(x for x in teams if key[x.team_id] == chiave)
        out[etichetta] = {
            "cassa": t.budget, "punti": round(res.total_points[chiave], 1),
            "vittorie": round(win[chiave], 4), "posizione": round(rank[chiave], 3),
            "completa": all(len(t.roster[r]) == pack.quotas[r] for r in ROLES)}
    return out


def intervallo(d, n_boot=5000, seed=11):
    r = np.random.default_rng(seed)
    return tuple(np.percentile(
        r.choice(d, size=(n_boot, len(d)), replace=True).mean(axis=1), [2.5, 97.5]))


def main():
    args = sys.argv[1:]
    n = int(args[args.index("--aste") + 1]) if "--aste" in args else 20
    k = float(args[args.index("--k") + 1]) if "--k" in args else 0.5
    season = args[args.index("--stagione") + 1] if "--stagione" in args else "2024-25"
    with open(ROOT / "data" / "packs" / f"pack_{season}.pkl", "rb") as f:
        pack = pickle.load(f)
    sd_crediti = {pid: float(p.ref_price_sd) * pack.budget
                  for pid, p in pack.players.items() if p.ref_price_sd}
    print(f"Due seggi B nella stessa asta — {season}, {n} aste, k = {k}")
    print(f"dispersione nota per {len(sd_crediti)} giocatori "
          f"(mediana {np.median(list(sd_crediti.values())):.1f} cr)")
    print(f"criteri: la variante deve vincere piu' scontri diretti (intervallo "
          f"che esclude la parita') e lasciare almeno {SOGLIA_CASSA:.0f} crediti in meno\n")
    att, var = [], []
    for i in range(n):
        r = una_asta(pack, SEED_BASE + i, k, sd_crediti)
        att.append(r["attuale"])
        var.append(r["variante"])
        print(f"  asta {i + 1:2d}/{n}: attuale cassa {r['attuale']['cassa']:3d} "
              f"vittorie {r['attuale']['vittorie']:.0%} | variante cassa "
              f"{r['variante']['cassa']:3d} vittorie {r['variante']['vittorie']:.0%}",
              flush=True)
    out = {"stagione": season, "aste": n, "k": k, "tavolo": TAVOLO}
    print(f"\n{'misura':20s} {'attuale':>9s} {'variante':>9s} {'differenza':>12s} {'IC95':>22s}")
    for campo, perc in [("cassa", False), ("punti", False), ("vittorie", True),
                        ("posizione", False)]:
        a = np.array([x[campo] for x in att], float)
        v = np.array([x[campo] for x in var], float)
        d = v - a
        lo, hi = intervallo(d)
        f = (lambda x: f"{x:.1%}") if perc else (lambda x: f"{x:8.1f}")
        print(f"{campo:20s} {f(a.mean()):>9s} {f(v.mean()):>9s} {f(d.mean()):>12s} "
              f"{'[' + f(lo) + ', ' + f(hi) + ']':>22s}")
        out[campo] = {"attuale": round(float(a.mean()), 4),
                      "variante": round(float(v.mean()), 4),
                      "differenza": round(float(d.mean()), 4),
                      "ic95": [round(float(lo), 4), round(float(hi), 4)]}
    dw = np.array([x["vittorie"] for x in var]) - np.array([x["vittorie"] for x in att])
    dc = np.array([x["cassa"] for x in var], float) - np.array([x["cassa"] for x in att], float)
    lo_w, hi_w = intervallo(dw)
    lo_c, hi_c = intervallo(dc)
    print("\nVERDETTO secondo i criteri fissati prima:")
    if lo_w > 0:
        vw = f"scontri diretti: la variante VINCE ({dw.mean():+.1%}, limite basso {lo_w:+.1%})"
    elif hi_w < 0:
        vw = f"scontri diretti: la variante PERDE ({dw.mean():+.1%}, limite alto {hi_w:+.1%})"
    else:
        vw = f"scontri diretti: INCONCLUDENTE ({dw.mean():+.1%}, intervallo [{lo_w:+.1%}, {hi_w:+.1%}])"
    if hi_c <= -SOGLIA_CASSA:
        vc = f"cassa: SUPERATO ({dc.mean():+.1f} cr)"
    elif lo_c >= -SOGLIA_CASSA:
        vc = f"cassa: NON superato ({dc.mean():+.1f} cr)"
    else:
        vc = f"cassa: INCONCLUDENTE ({dc.mean():+.1f} cr, intervallo [{lo_c:+.1f}, {hi_c:+.1f}])"
    print(f"  {vw}\n  {vc}")
    out["verdetto"] = {"scontri": vw, "cassa": vc}
    (ROOT / "data" / "livello0" / f"o3c_due_seggi_{season}.json").write_text(
        json.dumps(out, indent=1, ensure_ascii=False), encoding="utf-8")


if __name__ == "__main__":
    main()
