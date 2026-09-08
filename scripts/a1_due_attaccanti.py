"""Esperimento A1: due grandi attaccanti, provati come politica di spesa.

Il committente chiede che la strategia sia realmente esplorata. Fin qui era
stata provata solo dentro la ricerca su candidate del Livello 3, cioe' dentro
la politica che il confronto d'asta ha dichiarato perdente: misurarla li'
significherebbe misurare una cosa dentro un'altra che non funziona.

Qui si cambia **una cosa sola** rispetto al bot attuale: la quota di spesa in
attacco nell'obiettivo. Tre trattamenti, mondi separati, stesso disegno di F9.
Il criterio di decisione e' scritto prima in `reports/CRITERI_L2_L3.md` §3.9.

E' una approssimazione dichiarata di "due grandi attaccanti" attraverso la
spesa, non attraverso l'identita' dei giocatori: il bot resta libero di
comprare i nomi che i prezzi giustificano. La diagnostica conta quanti
attaccanti fra i primi dieci per prezzo di listino finiscono in rosa.

Uso:
    python scripts/a1_due_attaccanti.py --repliche 22 --scenari 40
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import pickle
import random
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from fantabot.bots.bot_l3 import BBotCoerente          # noqa: E402
from fantabot.engine.auction import AuctionEngine      # noqa: E402
from fantabot.livello3 import valutatore as V          # noqa: E402
from fantabot.models import ROLES                      # noqa: E402

# le funzioni del confronto d'asta si riusano invece di riscriverle: gli
# avversari, le sedie e la conversione delle chiavi devono essere gli stessi
_spec = importlib.util.spec_from_file_location(
    "l3_confronto_asta", ROOT / "scripts" / "l3_confronto_asta.py")
CA = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(CA)

OUT = ROOT / "data" / "l3" / "asta"

# Quote di spesa in attacco. La prima e' quella del pack, cioe' il bot di oggi.
QUOTE_ATTACCO = {
    "B": None,                       # l'obiettivo del pack, non toccato
    "B-attacco": (0.50, 0.65),
    "B-due-punte": (0.60, 0.75),
}


def gioca(pack, trattamento, seme, seggio):
    """Un'asta completa col nostro bot al seggio indicato.

    Identica a quella del confronto d'asta salvo il bot al nostro seggio, che
    qui e' sempre `BBotCoerente` e cambia solo per la quota d'attacco."""
    rng = random.Random(seme)
    obj = dict(getattr(pack, "b_objective", None) or {})
    quota = QUOTE_ATTACCO[trattamento]
    if quota is not None:
        obj["attack_share"] = quota
    bots, etichette = [], []
    j = 0
    for i in range(10):
        if i == seggio:
            bots.append(BBotCoerente(random.Random(seme * 1000 + i),
                                     pack.b_predictions, objective=obj))
            etichette.append("NOI")
        else:
            bots.append(CA.fai_avversario(CA.AVVERSARI[j],
                                          random.Random(seme * 1000 + i), pack))
            etichette.append(f"AVV{j + 1:02d}:{CA.AVVERSARI[j]}")
            j += 1
    eng = AuctionEngine(dict(pack.players), bots, pack.quotas, pack.budget, rng)
    squadre = eng.run()
    rose, speso = {}, {}
    for i, t in enumerate(squadre):
        rose[etichette[i]] = {r: [CA._chiave(pid) for pid, _ in t.roster[r]]
                              for r in ROLES}
        speso[etichette[i]] = pack.budget - t.budget
    prezzi_pagati = {pid: pr for pid, pr in squadre[seggio].roster["A"]}
    return {"rose": rose, "speso": speso, "attaccanti": prezzi_pagati,
            "seggio": seggio}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--stagione", default="2026-27")
    ap.add_argument("--repliche", type=int, default=22)
    ap.add_argument("--scenari", type=int, default=40)
    ap.add_argument("--seme", type=int, default=20260907)
    a = ap.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)

    with open(ROOT / "data" / "packs" / f"pack_{a.stagione}.pkl", "rb") as f:
        pack = pickle.load(f)
    with open(ROOT / "data" / "l2" / f"cubo_{a.stagione}.pkl", "rb") as f:
        salvato = pickle.load(f)
    cubo = salvato["cubo"]
    bonus = getattr(cubo, "gol_subiti", None) is not None
    if not bonus:
        print("ATTENZIONE: il cubo non porta i gol subiti; il bonus porta "
              "inviolata NON entra nei punteggi.")
    regole = V.Regole(quote=dict(pack.quotas), budget=pack.budget,
                      usa_mod_difesa=bool(pack.use_mod_difesa),
                      applica_bonus_porta_inviolata=bonus)
    scenari = list(range(min(a.scenari, cubo.fantavoto.shape[0])))
    cal = V.calendario_berger(10, cubo.fantavoto.shape[1], seme=a.seme)

    # i dieci attaccanti piu' cari a listino: servono alla diagnostica
    cari = sorted((pid for pid, p in pack.players.items() if p.role == "A"),
                  key=lambda pid: -float(
                      (pack.b_predictions.get(pid, {}) or {}).get("q50", 0.0)))[:10]
    cari = {CA._chiave(pid) for pid in cari}
    print(f"attaccanti fra i dieci piu' cari a listino: {len(cari)}")

    trattamenti = list(QUOTE_ATTACCO)
    righe = []
    t0 = time.time()
    for rep in range(a.repliche):
        seme = a.seme + rep
        seggio = rep % 10
        for tr in trattamenti:
            t1 = time.time()
            try:
                res = gioca(pack, tr, seme, seggio)
            except Exception as exc:
                righe.append({"replica": rep, "trattamento": tr,
                              "errore": f"{type(exc).__name__}: {exc}"})
                print(f"  replica {rep} {tr}: ERRORE {type(exc).__name__}: {exc}")
                continue
            problemi = V.verifica_rose(res["rose"], regole)
            if problemi:
                righe.append({"replica": rep, "trattamento": tr,
                              "errore": "rose illegali: " + "; ".join(problemi[:3])})
                print(f"  replica {rep} {tr}: ROSE ILLEGALI {problemi[:2]}")
                continue
            noti = set(cubo.giocatori)
            ignoti = [pid for v in res["rose"].values() for r in v for pid in v[r]
                      if pid not in noti]
            if ignoti:
                righe.append({"replica": rep, "trattamento": tr,
                              "errore": f"{len(ignoti)} giocatori fuori dal cubo"})
                print(f"  replica {rep} {tr}: {len(ignoti)} giocatori fuori dal cubo")
                continue
            e = V.valuta(cubo, res["rose"], regole, calendario=cal,
                         scenari=scenari, controlla_legalita=False)
            p1 = e.p_primo()["NOI"]
            i_noi = e.squadre.index("NOI")
            attaccanti = res["rose"]["NOI"]["A"]
            spesa_a = sum(res["attaccanti"].values())
            righe.append({
                "replica": rep, "trattamento": tr, "seggio": seggio,
                "p1": round(p1, 5),
                "punti_giornata": round(float(e.punteggi[:, i_noi].mean()), 3),
                "gol_giornata": round(float(e.gol[:, i_noi].mean()), 4),
                "speso": res["speso"]["NOI"],
                "residuo": pack.budget - res["speso"]["NOI"],
                "speso_attacco": spesa_a,
                "quota_attacco": round(spesa_a / max(res["speso"]["NOI"], 1), 4),
                "attaccanti_cari": sum(1 for pid in attaccanti if pid in cari),
                "secondi": round(time.time() - t1, 1),
            })
            print(f"  replica {rep} seggio {seggio} {tr:12s}: P(1) {p1:.3f} | "
                  f"speso {res['speso']['NOI']:3d} (attacco {spesa_a:3d}, "
                  f"{righe[-1]['quota_attacco']:.0%}) | attaccanti cari "
                  f"{righe[-1]['attaccanti_cari']} ({righe[-1]['secondi']:.0f} s)")

    df = pd.DataFrame(righe)
    df.to_csv(OUT / f"a1_due_attaccanti_{a.stagione}.csv", index=False)
    ok = df[df.get("errore").isna()] if "errore" in df else df
    print(f"\ntempo totale {time.time() - t0:.0f} s, {len(ok)}/{len(df)} aste riuscite")
    if not len(ok):
        return 1
    print("\nmedia per trattamento:")
    print(ok.groupby("trattamento")[["p1", "punti_giornata", "gol_giornata",
                                     "speso", "residuo", "speso_attacco",
                                     "quota_attacco", "attaccanti_cari"]]
            .mean().round(4).to_string())

    rif = "B"
    base = ok[ok.trattamento == rif].set_index("replica")["p1"]
    rng = np.random.default_rng(a.seme)
    confronti = {}
    print(f"\ndifferenza appaiata di P(1 posto) rispetto a {rif} "
          "(bootstrap 4000, criteri 3.9):")
    for tr in trattamenti[1:]:
        alt = ok[ok.trattamento == tr].set_index("replica")["p1"]
        comuni = sorted(set(base.index) & set(alt.index))
        if len(comuni) < 2:
            print(f"  {tr}: meno di due repliche in comune, non confrontabile")
            continue
        d = np.array([alt[i] - base[i] for i in comuni])
        idx = rng.integers(0, len(d), (4000, len(d)))
        m = d[idx].mean(1)
        lo, hi = float(np.percentile(m, 2.5)), float(np.percentile(m, 97.5))
        esclude = lo > 0 or hi < 0
        if not esclude:
            esito = "attraversa lo zero: inconcludente"
        elif float(d.mean()) > 0:
            esito = "MIGLIORE"
        else:
            esito = "PEGGIORE"
        confronti[tr] = {"differenza": float(d.mean()), "ic95": [lo, hi],
                         "esclude_zero": esclude, "repliche": len(comuni)}
        print(f"  {tr:12s} {d.mean():+.4f}  IC95 [{lo:+.4f}, {hi:+.4f}]  "
              f"{esito}  ({len(comuni)} repliche)")

    riassunto = {"confronti": confronti, "repliche": a.repliche,
                 "scenari": a.scenari, "seme": a.seme,
                 "quote_attacco": {k: v for k, v in QUOTE_ATTACCO.items()},
                 "avversari": CA.AVVERSARI,
                 "avvertenza": "il calendario della lega non e' noto: e' "
                               "generato da un seme dichiarato. L'esito vale "
                               "per questo banco e per questi prezzi."}
    percorso = OUT / f"a1_due_attaccanti_{a.stagione}.json"
    percorso.write_text(json.dumps(riassunto, indent=1, default=str),
                        encoding="utf-8")
    print(f"\nscritto {percorso}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
