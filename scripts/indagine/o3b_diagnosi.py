"""O3b, parte 1 — perche' il bot perde meta' dei suoi obiettivi?

Sapere che ne perde 13 su 25 non dice la causa. Le cause possibili sono
quattro e vanno separate prima di proporre qualunque rimedio:

  A. il TETTO e' troppo basso   il lotto viene battuto sopra il massimo che
                                il bot si era dato, e lui si ferma prima
  B. il tetto non c'entra       il lotto viene battuto SOTTO il suo massimo e
                                lui non rilancia lo stesso (turno, ordine,
                                budget momentaneo, vincoli di reparto)
  C. il piano cambia idea       il replanning toglie quel nome dagli obiettivi
                                prima che venga chiamato
  D. l'alternativa costa meno   perde il nome caro e compra un sostituto
                                economico: il risparmio e' una conseguenza,
                                non la causa

Per ogni obiettivo perso si registra: prezzo battuto, massimo che il bot si
era dato in quel momento, chi l'ha preso, se era ancora fra gli obiettivi al
momento della chiamata, e cosa ha comprato al suo posto nello stesso ruolo.

Non modifica nulla: gioca aste in memoria e stampa.

Uso: python scripts/indagine/o3b_diagnosi.py [--aste 8] [--stagione 2024-25]
"""
from __future__ import annotations

import json
import pickle
import random
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from fantabot.engine.auction import AuctionEngine  # noqa: E402
from fantabot.models import ROLES  # noqa: E402
from fantabot.tournament import make_bot  # noqa: E402

C7 = ["C:stars_scrubs", "C:semitop", "C:tifoso", "C:ancorato",
      "C:panic", "C:tirchio", "C:enforcer"]
TAVOLO = ["B", "A", "A+"] + C7
SEED_BASE = 10_000


def una_asta(pack, seed):
    """Gioca un'asta registrando, lotto per lotto, cosa sapeva il bot B."""
    rng = random.Random(seed)
    bots = [make_bot(s, random.Random(seed * 1000 + i), pack)
            for i, s in enumerate(TAVOLO)]
    b = bots[TAVOLO.index("B")]
    tracce = {}

    # si intercetta la decisione del bot B: prima di ogni sua risposta si
    # annota il massimo che si era dato e se il giocatore era un obiettivo
    orig_bid = b.bid

    def spia_bid(view, player, price, leader):
        pid = player.player_id
        t = tracce.setdefault(pid, {})
        t.setdefault("era_obiettivo", pid in b.targets)
        t.setdefault("era_titolare_piano", pid in getattr(b, "starter_targets", set()))
        try:
            t.setdefault("massimo_del_bot", float(b._max_bid_for(pid)))
        except Exception:
            t.setdefault("massimo_del_bot", None)
        t.setdefault("budget_al_momento", view.me.budget)
        t.setdefault("slot_liberi_ruolo",
                     view.me.slots_left(view.quotas, player.role))
        return orig_bid(view, player, price, leader)

    b.bid = spia_bid
    eng = AuctionEngine(dict(pack.players), bots, pack.quotas, pack.budget, rng)
    teams = eng.run()
    obiettivi_iniziali = set()

    battuti = {}
    for ev in eng.events:
        d = ev.to_dict() if hasattr(ev, "to_dict") else ev
        if d.get("kind") == "hammer":
            battuti[d["player_id"]] = (d["price"], d.get("bot"))
    mia = None
    for t in teams:
        if t.bot_name == "B":
            mia = {pid for r in ROLES for pid, _ in t.roster[r]}
            cassa = t.budget
            acquisti = {pid: pr for r in ROLES for pid, pr in t.roster[r]}
    return tracce, battuti, mia, cassa, acquisti, b


def main():
    args = sys.argv[1:]
    n = int(args[args.index("--aste") + 1]) if "--aste" in args else 8
    season = args[args.index("--stagione") + 1] if "--stagione" in args else "2024-25"
    with open(ROOT / "data" / "packs" / f"pack_{season}.pkl", "rb") as f:
        pack = pickle.load(f)
    nomi = {pid: p.name for pid, p in pack.players.items()}
    ruoli = {pid: p.role for pid, p in pack.players.items()}
    conteggi = defaultdict(int)
    persi_dettaglio = []
    casse = []
    for i in range(n):
        tracce, battuti, mia, cassa, acquisti, b = una_asta(pack, SEED_BASE + i)
        casse.append(cassa)
        # obiettivi che il bot ha davvero valutato al banco e non ha preso
        for pid, t in tracce.items():
            if not t.get("era_obiettivo"):
                continue
            if pid in mia:
                conteggi["obiettivi_presi"] += 1
                continue
            prezzo, vincitore = battuti.get(pid, (None, None))
            massimo = t.get("massimo_del_bot")
            if prezzo is None:
                conteggi["obiettivo_mai_battuto"] += 1
                continue
            if massimo is None:
                conteggi["senza_massimo"] += 1
                continue
            if prezzo > massimo:
                causa = "A: battuto sopra il suo massimo"
            elif t["slot_liberi_ruolo"] <= 0:
                causa = "B2: reparto gia' pieno"
            elif prezzo >= t["budget_al_momento"]:
                causa = "B3: budget del momento insufficiente"
            else:
                causa = "B1: sotto il suo massimo, non ha rilanciato"
            conteggi[causa] += 1
            persi_dettaglio.append({
                "asta": i, "nome": nomi.get(pid, pid), "ruolo": ruoli.get(pid),
                "prezzo": prezzo, "massimo": round(massimo, 1),
                "eccesso": round(prezzo - massimo, 1), "vincitore": vincitore,
                "budget": t["budget_al_momento"]})
        print(f"  asta {i + 1}/{n} giocata (cassa finale {cassa})", flush=True)

    print(f"\n=== {season}: {n} aste, tavolo {TAVOLO[:3]}+7C, seed "
          f"{SEED_BASE}..{SEED_BASE + n - 1} ===")
    print(f"cassa finale media {np.mean(casse):.1f} cr\n")
    print("PERCHE' PERDE GLI OBIETTIVI (solo quelli valutati al banco):")
    tot = sum(v for k, v in conteggi.items() if k != "obiettivi_presi")
    for k, v in sorted(conteggi.items(), key=lambda kv: -kv[1]):
        quota = f"{v / tot:.0%}" if k != "obiettivi_presi" and tot else ""
        print(f"  {k:42s} {v:5d}  {quota}")
    if persi_dettaglio:
        d = [x for x in persi_dettaglio if x["eccesso"] > 0]
        if d:
            ecc = np.array([x["eccesso"] for x in d])
            print(f"\nquando il prezzo supera il suo massimo: eccesso mediano "
                  f"{np.median(ecc):.0f} cr, medio {ecc.mean():.0f}, "
                  f"90esimo percentile {np.percentile(ecc, 90):.0f}")
            print("esempi (i 10 con l'eccesso piu' grande):")
            for x in sorted(d, key=lambda y: -y["eccesso"])[:10]:
                print(f"   {x['nome']:20s} {x['ruolo']} battuto {x['prezzo']:3d} "
                      f"contro suo massimo {x['massimo']:5.1f} "
                      f"(+{x['eccesso']:.0f}) a {x['vincitore']}")


if __name__ == "__main__":
    main()
