"""O3b, parte 2 — confronto appaiato fra due politiche di offerta.

IPOTESI, scritta prima di guardare i risultati.
La diagnosi (o3b_diagnosi.py) dice che l'86% degli obiettivi persi viene
battuto SOPRA il massimo che il bot si era dato, con eccesso mediano di 3
crediti. Il massimo per i titolari di piano e' `q90 + 0.5 * prezzo-ombra`: il
peso 0.5 non e' mai stato misurato, e il q90 e' tarato sul prezzo MEDIO fra
aste, mentre in una singola asta il prezzo lo supera il 16.9% delle volte
(misurato su 206 giocatori con almeno 3 aste osservate). Alzare il peso del
prezzo-ombra da 0.5 a 1.0 dovrebbe far recuperare parte degli obiettivi e
ridurre la cassa lasciata.

TRATTAMENTO. Solo `peso_ombra`: 0.5 (politica attuale) contro 1.0 (variante).
Nient'altro cambia. Non si offre di piu' "perche' si e' risparmiato": il
massimo resta legato al valore del giocatore per la rosa.

DISEGNO. Aste appaiate: stesso seme, stesso tavolo, stessi avversari, stesso
pack. La differenza fra le due politiche si misura asta per asta, cosi' il
rumore comune si cancella. Intervallo di confidenza con bootstrap sulle
differenze appaiate (le aste sono indipendenti fra loro; le giornate dentro
una stessa asta non lo sono, per questo si confronta un valore per asta).

CRITERI DI ACCETTAZIONE, fissati prima:
  - primario, quanto deve migliorare: cassa media lasciata giu' di almeno
    30 crediti. La soglia viene dal prezzo di un titolare di fascia media a
    prezzo di mercato nel pack (non da quanto serve a far passare la variante).
  - non inferiorita' sul risultato: la variante non deve perdere piu' di 3
    punti percentuali di vittorie. Il margine e' l'ordine di grandezza con cui
    le prime candidate di f12 si equivalgono (59%, 58%, 55% con errore 5),
    quindi sotto quella soglia il banco non distingue.
  - se l'intervallo di confidenza attraversa il margine: INCONCLUDENTE, e si
    dice cosi'. Nessuna soglia viene spostata dopo aver visto i numeri.

TAVOLO. Piu' informativo di quello del torneo: due seggi A+ e tre bot C
"informati" (che conoscono la lista prezzi). Serve a evitare l'effetto
soffitto, non a far vincere o perdere B. Tutti hanno la stessa informazione
disponibile alla stessa data.

Uso: python scripts/indagine/o3b_confronto.py [--aste 20] [--stagione 2024-25]
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

# tavolo informativo: 2 A+ e 3 C con la lista prezzi, per togliere il soffitto
TAVOLO = ["B", "A+", "A+", "C:informato", "C:informato", "C:informato",
          "C:stars_scrubs", "C:semitop", "C:ancorato", "C:tirchio"]
SEED_BASE = 20_000
MARGINE_VITTORIE = 0.03      # non inferiorita': -3 punti percentuali
SOGLIA_CASSA = 30.0          # miglioramento richiesto: -30 crediti


def costruisci_bot(spec, rng, pack, peso_ombra):
    if spec == "B":
        return BBot(rng, pack.b_predictions,
                    objective=getattr(pack, "b_objective", None),
                    peso_ombra=peso_ombra)
    if spec == "A":
        return ABot(rng, price_list=pack.a_price_list)
    if spec == "A+":
        return ABot(rng, price_list=pack.a_price_list, flexible=True)
    prof = spec.split(":", 1)[1]
    fav = (rng.choice(sorted({p.team for p in pack.players.values()}))
           if prof == "tifoso" else None)
    hint = pack.a_price_list if prof == "informato" else None
    return CBot(rng, prof, fav_team=fav, hint_prices=hint)


def una_asta(pack, seed, peso_ombra):
    rng = random.Random(seed)
    bots = [costruisci_bot(s, random.Random(seed * 1000 + i), pack, peso_ombra)
            for i, s in enumerate(TAVOLO)]
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
    b = next(t for t in teams if t.bot_name == "B")
    valore = sum(pack.b_predictions.get(pid, {}).get("value", 0.0)
                 for r in ROLES for pid, _ in b.roster[r])
    return {"cassa": b.budget, "speso": pack.budget - b.budget,
            "valore_rosa": round(valore, 1),
            "punti": round(res.total_points["B"], 1),
            "vittorie": round(win["B"], 4), "posizione": round(rank["B"], 3),
            "completa": all(len(b.roster[r]) == pack.quotas[r] for r in ROLES)}


def intervallo(diff, n_boot=5000, seed=11):
    r = np.random.default_rng(seed)
    campioni = r.choice(diff, size=(n_boot, len(diff)), replace=True).mean(axis=1)
    return float(np.percentile(campioni, 2.5)), float(np.percentile(campioni, 97.5))


def main():
    args = sys.argv[1:]
    n = int(args[args.index("--aste") + 1]) if "--aste" in args else 20
    season = args[args.index("--stagione") + 1] if "--stagione" in args else "2024-25"
    with open(ROOT / "data" / "packs" / f"pack_{season}.pkl", "rb") as f:
        pack = pickle.load(f)
    print(f"O3b — {season}, {n} aste appaiate, tavolo informativo")
    print(f"trattamento: peso del prezzo-ombra 0.5 (attuale) contro 1.0 (variante)")
    print(f"criteri fissati prima: cassa giu' di almeno {SOGLIA_CASSA:.0f} cr; "
          f"vittorie non giu' di piu' di {MARGINE_VITTORIE:.0%}\n")
    att, var = [], []
    for i in range(n):
        s = SEED_BASE + i
        a = una_asta(pack, s, 0.5)
        v = una_asta(pack, s, 1.0)
        att.append(a)
        var.append(v)
        print(f"  asta {i + 1:2d}/{n}: attuale cassa {a['cassa']:3d} vittorie "
              f"{a['vittorie']:.0%} | variante cassa {v['cassa']:3d} vittorie "
              f"{v['vittorie']:.0%}", flush=True)

    out = {"stagione": season, "aste": n, "tavolo": TAVOLO,
           "seed": [SEED_BASE, SEED_BASE + n - 1],
           "criteri": {"soglia_cassa": SOGLIA_CASSA,
                       "margine_vittorie": MARGINE_VITTORIE}}
    print(f"\n{'misura':22s} {'attuale':>9s} {'variante':>9s} {'differenza':>12s} "
          f"{'IC95 appaiato':>22s}")
    for campo, etichetta, perc in [("cassa", "cassa lasciata", False),
                                   ("speso", "speso", False),
                                   ("valore_rosa", "valore della rosa", False),
                                   ("punti", "punti stagione", False),
                                   ("vittorie", "vittorie", True),
                                   ("posizione", "posizione media", False)]:
        a = np.array([x[campo] for x in att], float)
        v = np.array([x[campo] for x in var], float)
        d = v - a
        lo, hi = intervallo(d)
        f = (lambda x: f"{x:.1%}") if perc else (lambda x: f"{x:8.1f}")
        print(f"{etichetta:22s} {f(a.mean()):>9s} {f(v.mean()):>9s} "
              f"{f(d.mean()):>12s} {'[' + f(lo) + ', ' + f(hi) + ']':>22s}")
        out[campo] = {"attuale": round(float(a.mean()), 4),
                      "variante": round(float(v.mean()), 4),
                      "differenza": round(float(d.mean()), 4),
                      "ic95": [round(lo, 4), round(hi, 4)]}

    dc = np.array([v["cassa"] for v in var], float) - np.array([a["cassa"] for a in att], float)
    dw = np.array([v["vittorie"] for v in var], float) - np.array([a["vittorie"] for a in att], float)
    lo_c, hi_c = intervallo(dc)
    lo_w, hi_w = intervallo(dw)
    print("\nVERDETTO secondo i criteri fissati prima:")
    if hi_c <= -SOGLIA_CASSA:
        esito_c = f"cassa: SUPERATO (intervallo tutto sotto -{SOGLIA_CASSA:.0f})"
    elif lo_c >= -SOGLIA_CASSA:
        esito_c = f"cassa: NON superato (intervallo tutto sopra -{SOGLIA_CASSA:.0f})"
    else:
        esito_c = "cassa: INCONCLUDENTE (l'intervallo attraversa la soglia)"
    if lo_w >= -MARGINE_VITTORIE:
        esito_w = f"vittorie: non inferiorita' DIMOSTRATA (limite basso {lo_w:+.1%})"
    elif hi_w < -MARGINE_VITTORIE:
        esito_w = f"vittorie: PEGGIORA oltre il margine (limite alto {hi_w:+.1%})"
    else:
        esito_w = "vittorie: INCONCLUDENTE (l'intervallo attraversa il margine)"
    print(f"  {esito_c}\n  {esito_w}")
    out["verdetto"] = {"cassa": esito_c, "vittorie": esito_w}
    complete = sum(1 for x in var if x["completa"])
    print(f"  rose complete con la variante: {complete}/{n}")
    d = ROOT / "data" / "livello0"
    d.mkdir(exist_ok=True)
    (d / f"o3b_confronto_{season}.json").write_text(
        json.dumps(out, indent=1, ensure_ascii=False), encoding="utf-8")


if __name__ == "__main__":
    main()
