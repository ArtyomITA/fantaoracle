"""O3 — quanto resta davvero in cassa a fine asta, col codice e i pack di oggi.

Gli 88 crediti citati finora venivano da log del torneo di agosto: codice
vecchio, pack vecchi. Qui si rigioca da zero, senza toccare nulla, per vedere
se il residuo c'e' ancora e quanto costa in punti e in vittorie.

Cosa si misura, per ogni partecipante e per ogni asta:
  - cassa finale e rosa completa (tutti gli slot riempiti?)
  - spesa PREVISTA dal piano iniziale contro spesa SOSTENUTA davvero
  - target del piano iniziale persi, e a che prezzo li ha presi un altro
  - punti stagione e vittorie negli scontri diretti

Tavolo e seed sono quelli del torneo ufficiale (`scripts/f3_run_tournament.py`,
composizione principale 1B+2A+7C, seed 10000+i), cosi' i numeri sono
confrontabili con lo storico.

Stagioni: 2024/25 e' la validazione (i prezzi di riferimento vengono da aste
reali per il 90% dei crediti del piano); 2025/26 e' solo diagnostica (nessun
prezzo d'asta osservato, i riferimenti sono stimati).

Non modifica nulla: legge i pack, gioca in memoria, scrive solo il proprio
esito sotto data/livello0/.

Uso: python scripts/indagine/check_o3_cassa.py [--aste 20] [--stagioni 2024-25,2025-26]
Output: data/livello0/check_o3_cassa.json + .md
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

from fantabot.engine.auction import AuctionEngine  # noqa: E402
from fantabot.models import ROLES  # noqa: E402
from fantabot.season.simulate import simulate_season  # noqa: E402
from fantabot.tournament import make_bot  # noqa: E402

C7 = ["C:stars_scrubs", "C:semitop", "C:tifoso", "C:ancorato",
      "C:panic", "C:tirchio", "C:enforcer"]
TAVOLO = ["B", "A", "A+"] + C7          # composizione principale del torneo
SEED_BASE = 10_000                       # stessi seed del torneo ufficiale


def una_asta(pack, seed):
    rng = random.Random(seed)
    bots = [make_bot(s, random.Random(seed * 1000 + i), pack)
            for i, s in enumerate(TAVOLO)]
    b_ix = TAVOLO.index("B")
    bot_b = bots[b_ix]
    # il piano iniziale di B si legge dopo la prima pianificazione: il motore
    # chiama start_auction, che a sua volta chiama il replan
    piano_iniziale = {}

    orig_start = bot_b.start_auction

    def cattura(view):
        orig_start(view)
        prezzi = {pid: max(1.0, bot_b._q(pid, "q50")) for pid in bot_b.targets}
        piano_iniziale["target"] = set(bot_b.targets)
        piano_iniziale["spesa_prevista"] = sum(prezzi.values())

    bot_b.start_auction = cattura
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
    prezzi_battuti = {}
    for ev in eng.events:
        d = ev.to_dict() if hasattr(ev, "to_dict") else ev
        if d.get("kind") == "hammer":
            prezzi_battuti[d["player_id"]] = (d["price"], d.get("bot"))
    out = {}
    for t in teams:
        k = key[t.team_id]
        completa = all(len(t.roster[r]) == pack.quotas[r] for r in ROLES)
        out[k] = {"cassa_finale": t.budget, "speso": pack.budget - t.budget,
                  "rosa_completa": completa,
                  "slot_vuoti": {r: pack.quotas[r] - len(t.roster[r]) for r in ROLES
                                 if len(t.roster[r]) < pack.quotas[r]},
                  "punti": round(res.total_points[k], 1),
                  "vittorie": round(win[k], 4), "posizione_media": round(rank[k], 3)}
    # target del piano iniziale: presi o persi, e a che prezzo sono andati
    tgt = piano_iniziale.get("target", set())
    mia = {pid for r in ROLES for pid in rosters["B"][r]}
    persi = [(pid, prezzi_battuti.get(pid, (None, None))) for pid in tgt if pid not in mia]
    out["B"]["piano"] = {
        "target_iniziali": len(tgt),
        "spesa_prevista": round(piano_iniziale.get("spesa_prevista", 0.0), 1),
        "target_presi": len(tgt & mia),
        "target_persi": len(persi),
        "spesa_persi": round(sum(p for _, (p, _) in persi if p), 1),
    }
    return out, prezzi_battuti


def main():
    args = sys.argv[1:]
    n_aste = int(args[args.index("--aste") + 1]) if "--aste" in args else 20
    stagioni = (args[args.index("--stagioni") + 1].split(",") if "--stagioni" in args
                else ["2024-25", "2025-26"])
    tutto = {}
    for season in stagioni:
        with open(ROOT / "data" / "packs" / f"pack_{season}.pkl", "rb") as f:
            pack = pickle.load(f)
        print(f"\n=== {season} | tavolo {TAVOLO} | seed {SEED_BASE}..{SEED_BASE + n_aste - 1} "
              f"| pack del {'validazione' if season == '2024-25' else 'DIAGNOSTICA'} ===")
        per_bot = {}
        for i in range(n_aste):
            esiti, _battuti = una_asta(pack, SEED_BASE + i)
            for k, v in esiti.items():
                per_bot.setdefault(k, []).append(v)
            pi = esiti["B"]["piano"]
            print(f"  asta {i + 1:2d}/{n_aste}: B cassa {esiti['B']['cassa_finale']:3d} | "
                  f"previsto {pi['spesa_prevista']:5.0f} sostenuto {esiti['B']['speso']:3d} | "
                  f"target {pi['target_presi']}/{pi['target_iniziali']} "
                  f"(persi per {pi['spesa_persi']:.0f} cr) | "
                  f"punti {esiti['B']['punti']:.0f} vittorie {esiti['B']['vittorie']:.0%}",
                  flush=True)
        righe = {}
        for k, v in sorted(per_bot.items()):
            cassa = np.array([x["cassa_finale"] for x in v], float)
            punti = np.array([x["punti"] for x in v], float)
            vitt = np.array([x["vittorie"] for x in v], float)
            complete = sum(1 for x in v if x["rosa_completa"])
            righe[k] = {
                "aste": len(v),
                "cassa_media": round(float(cassa.mean()), 1),
                "cassa_mediana": round(float(np.median(cassa)), 1),
                "cassa_max": round(float(cassa.max()), 1),
                "rose_complete": f"{complete}/{len(v)}",
                "punti_medi": round(float(punti.mean()), 1),
                "vittorie_medie": round(float(vitt.mean()), 4),
                "se_vittorie": round(float(vitt.std() / np.sqrt(len(v))), 4)}
            print(f"  {k:16s} cassa media {righe[k]['cassa_media']:6.1f} "
                  f"(mediana {righe[k]['cassa_mediana']:5.1f}, max {righe[k]['cassa_max']:5.1f}) | "
                  f"rose complete {righe[k]['rose_complete']} | punti {righe[k]['punti_medi']:6.1f} | "
                  f"vittorie {righe[k]['vittorie_medie']:.1%} +-{righe[k]['se_vittorie']:.1%}")
        # correlazione fra cassa lasciata e risultato, dentro il solo bot B
        b = per_bot.get("B", [])
        if len(b) >= 5:
            c = np.array([x["cassa_finale"] for x in b], float)
            p = np.array([x["punti"] for x in b], float)
            w = np.array([x["vittorie"] for x in b], float)
            rho_p = float(np.corrcoef(c, p)[0, 1]) if c.std() > 0 else float("nan")
            rho_w = float(np.corrcoef(c, w)[0, 1]) if c.std() > 0 else float("nan")
            print(f"  B: correlazione cassa-punti {rho_p:+.2f}, cassa-vittorie {rho_w:+.2f} "
                  f"(n={len(b)}; correlazione, non causa)")
            righe["_B_correlazioni"] = {"cassa_punti": round(rho_p, 3),
                                        "cassa_vittorie": round(rho_w, 3), "n": len(b)}
            pi = [x["piano"] for x in b]
            righe["_B_piano"] = {
                "spesa_prevista_media": round(float(np.mean([x["spesa_prevista"] for x in pi])), 1),
                "spesa_sostenuta_media": round(float(np.mean([x["speso"] for x in b])), 1),
                "target_iniziali": round(float(np.mean([x["target_iniziali"] for x in pi])), 1),
                "target_persi_medi": round(float(np.mean([x["target_persi"] for x in pi])), 1),
                "spesa_target_persi": round(float(np.mean([x["spesa_persi"] for x in pi])), 1)}
            print(f"  B piano: previsto {righe['_B_piano']['spesa_prevista_media']:.0f} cr, "
                  f"sostenuto {righe['_B_piano']['spesa_sostenuta_media']:.0f} cr | "
                  f"target persi {righe['_B_piano']['target_persi_medi']:.1f} su "
                  f"{righe['_B_piano']['target_iniziali']:.0f} (andati via per "
                  f"{righe['_B_piano']['spesa_target_persi']:.0f} cr)")
        tutto[season] = {"tavolo": TAVOLO, "seed": [SEED_BASE, SEED_BASE + n_aste - 1],
                         "ruolo": "validazione" if season == "2024-25" else "diagnostica",
                         "per_bot": righe}
    d = ROOT / "data" / "livello0"
    d.mkdir(exist_ok=True)
    (d / "check_o3_cassa.json").write_text(json.dumps(tutto, indent=1, ensure_ascii=False),
                                           encoding="utf-8")
    print(f"\nsalvato in {d / 'check_o3_cassa.json'}")




if __name__ == "__main__":
    main()
