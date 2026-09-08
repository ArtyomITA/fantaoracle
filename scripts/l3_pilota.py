"""Pilota del Livello 3 sui dati veri: misura tempi, memoria e artefatti.

Prima di lanciare esperimenti lunghi bisogna sapere quanto costano. Questo
script fa un giro piccolo del Livello 3 sul cubo gia' generato e sul pack della
stagione in corso, e misura:

  - quanto ci mette il MILP a produrre una candidata;
  - quanto ci mette il valutatore per candidata, in funzione degli scenari;
  - quanto ci mette una curva di prezzo di indifferenza;
  - quanta memoria occupano cubo e cache;
  - quanto pesano gli artefatti prodotti.

Da questi numeri si dimensionano gli esperimenti veri. Non decide nulla e non
tocca pack, bot o Copilota.

## Che cosa NON dimostra

I numeri di P(primo posto) che stampa dipendono dal cubo attuale, che ha
ancora i difetti elencati in `reports/CRITERI_L2_L3.md` sezione 0. Sono utili
per misurare i tempi, non per scegliere una rosa.

Uso:
  python scripts/l3_pilota.py --stagione 2026-27 --scenari-ricerca 20 \
      --scenari-verifica 20 --candidate 6
"""
from __future__ import annotations

import argparse
import json
import pickle
import sys
import time
import tracemalloc
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
OUT = ROOT / "data" / "l3" / "pilota"

from fantabot.livello3 import indifferenza as I   # noqa: E402
from fantabot.livello3 import ricerca as R        # noqa: E402
from fantabot.livello3 import valutatore as V     # noqa: E402


def carica(stagione: str):
    with open(ROOT / "data" / "packs" / f"pack_{stagione}.pkl", "rb") as f:
        pack = pickle.load(f)
    with open(ROOT / "data" / "l2" / f"cubo_{stagione}.pkl", "rb") as f:
        salvato = pickle.load(f)
    return pack, salvato


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--stagione", default="2026-27")
    ap.add_argument("--scenari-ricerca", type=int, default=20)
    ap.add_argument("--scenari-verifica", type=int, default=20)
    ap.add_argument("--candidate", type=int, default=6)
    ap.add_argument("--seme", type=int, default=20260907)
    ap.add_argument("--prezzi-indifferenza", type=int, default=4)
    a = ap.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    tracemalloc.start()
    misure = {"stagione": a.stagione, "seme": a.seme}

    t0 = time.time()
    pack, salvato = carica(a.stagione)
    cubo = salvato["cubo"]
    misure["caricamento_s"] = round(time.time() - t0, 2)
    misure["cubo"] = {
        "scenari": int(cubo.fantavoto.shape[0]),
        "giornate": int(cubo.fantavoto.shape[1]),
        "giocatori": int(cubo.fantavoto.shape[2]),
        "memoria_MB": round(sum(x.nbytes for x in
                                (cubo.fantavoto, cubo.voto, cubo.gioca))
                            / 1048576, 1),
        "as_of": salvato.get("as_of"),
        "giornate_coperte": [int(cubo.giornate[0]), int(cubo.giornate[-1])],
    }
    print(f"cubo: {misure['cubo']}")

    # il pool: chiavi come nel cubo (interi), prezzi di mercato e valori
    preds = pack.b_predictions
    pool = {}
    prezzi, valori, valori_up = {}, {}, {}
    for pid, p in pack.players.items():
        chiave = int(pid) if str(pid).isdigit() else pid
        if chiave not in set(cubo.giocatori):
            continue
        pool[chiave] = p
        pr = preds.get(pid, {}) or preds.get(str(pid), {})
        prezzi[chiave] = max(1.0, float(pr.get("q50", p.ref_price * pack.budget)))
        valori[chiave] = float(pr.get("value", 0.0))
        valori_up[chiave] = float(pr.get("value_up", valori[chiave]))
    misure["pool"] = len(pool)
    print(f"pool: {len(pool)} giocatori nel cubo e nel pack")

    # Il cubo attuale non porta i gol subiti dai portieri, quindi il bonus
    # porta inviolata della lega non e' applicabile: lo si dichiara invece di
    # ignorarlo in silenzio. Vale 0,297 punti a giornata per rosa (misura in
    # data/l3/audit/simulazione/RAPPORTO.md, sezione 5a): i punteggi qui sotto
    # sono sottostimati di quella quantita', in modo uguale per tutte le rose.
    bonus = hasattr(cubo, "gol_subiti") and getattr(cubo, "gol_subiti") is not None
    if not bonus:
        print("ATTENZIONE: il cubo non porta i gol subiti; il bonus porta "
              "inviolata NON entra nei punteggi (circa -0,3 punti a giornata "
              "per rosa, uguale per tutte).")
    regole = V.Regole(quote=dict(pack.quotas), budget=pack.budget,
                      usa_mod_difesa=bool(pack.use_mod_difesa),
                      applica_bonus_porta_inviolata=bonus)
    n_scen = cubo.fantavoto.shape[0]
    ric = list(range(min(a.scenari_ricerca, n_scen // 2)))
    ver = list(range(n_scen // 2, min(n_scen, n_scen // 2 + a.scenari_verifica)))
    cal = V.calendario_berger(10, cubo.fantavoto.shape[1], seme=a.seme)
    misure["scenari"] = {"ricerca": len(ric), "verifica": len(ver),
                         "totali": n_scen}
    misure["calendario_dichiarato"] = True

    # --- candidate dal MILP ---
    strategie = R.strategie_predefinite(pack.budget)[:a.candidate]
    t0 = time.time()
    cand = R.genera_candidate(pool, prezzi, valori, valori_up, regole, strategie)
    t_milp = time.time() - t0
    ammissibili = [c for c in cand if c.get("rosa")]
    misure["milp"] = {"strategie": len(strategie),
                      "ammissibili": len(ammissibili),
                      "secondi_totali": round(t_milp, 1),
                      "secondi_per_candidata": round(t_milp / max(len(strategie), 1), 2)}
    print(f"MILP: {len(ammissibili)}/{len(strategie)} candidate in {t_milp:.1f} s")
    for c in cand:
        if not c.get("rosa"):
            print(f"  NON AMMISSIBILE: {c['strategia']} — {c.get('motivo')}")

    if not ammissibili:
        print("BLOCCO: nessuna candidata ammissibile")
        (OUT / "misure.json").write_text(json.dumps(misure, indent=1,
                                                    default=str), encoding="utf-8")
        return 1

    # --- valutazione: quanto costa uno scenario in piu' ---
    tempi = {}
    for n in (5, 10, len(ric)):
        t0 = time.time()
        e = R.valuta_candidata(ammissibili[0]["rosa"], pool, prezzi, valori,
                               cubo, regole, list(range(n)), a.seme,
                               n_avversari=9, calendario=cal)
        tempi[n] = round(time.time() - t0, 2)
    misure["valutazione_s_per_candidata"] = tempi
    print(f"valutazione di una candidata: {tempi}")

    # --- ricerca su candidate ---
    t0 = time.time()
    out = R.scegli(ammissibili, pool, prezzi, valori, cubo, regole, ric, ver,
                   seme_avversari=a.seme, calendario=cal)
    t_scelta = time.time() - t0
    misure["ricerca"] = {"secondi": round(t_scelta, 1),
                         "candidate": len(ammissibili)}
    print(f"\nricerca su candidate: {t_scelta:.1f} s")
    print(f"{'strategia':38s} {'P(1) ricerca':>13s} {'errore std':>11s}")
    for r in out["tabella"]:
        print(f"{r['strategia'][:38]:38s} {r['p1_ricerca']:13.4f} "
              f"{r['se_ricerca']:11.4f}")
    print(f"\nmigliore: {out['migliore']['strategia']} | costo "
          f"{out['migliore'].get('costo')} | modulo {out['migliore'].get('modulo')}")
    print(f"verifica su scenari mai usati: P(1) {out['verifica']['p1']:.4f} "
          f"(errore std {out['verifica']['se']:.4f}, "
          f"{out['verifica']['n_scenari']} scenari, "
          f"{out['verifica']['parita']} scenari con pari merito al primo posto)")
    misure["verifica"] = out["verifica"]
    misure["tabella"] = out["tabella"]

    # --- prezzo di indifferenza: quanto costa una curva ---
    rosa = out["migliore"]["rosa"]
    presi = {pid for r in rosa for pid in rosa[r]}
    # stato d'asta: nulla comprato, tutto disponibile
    avversari = {f"AVV{i + 1:02d}": {"rosa": {r: [] for r in regole.quote},
                                     "budget": float(pack.budget)}
                 for i in range(9)}
    stato = I.StatoAsta(nostra={r: [] for r in regole.quote},
                        nostro_budget=float(pack.budget), avversari=avversari,
                        disponibili=set(pool), regole=regole)
    bersagli = sorted(rosa["A"], key=lambda pid: -prezzi.get(pid, 0))[:2]
    curve = {}
    for g in bersagli:
        mercato = int(round(prezzi[g]))
        griglia = sorted({max(1, int(mercato * f))
                          for f in (0.6, 1.0, 1.4, 1.8)})[:a.prezzi_indifferenza]
        t0 = time.time()
        c = I.curva(g, stato, pool, prezzi, valori, cubo, cal, ric,
                    prezzi_da_provare=griglia, repliche=4, seme=a.seme)
        dt = time.time() - t0
        c["secondi"] = round(dt, 1)
        nome = pool[g].name
        curve[nome] = c
        print(f"\nprezzo di indifferenza — {nome} ({pool[g].role}, "
              f"mercato {mercato} crediti), {dt:.1f} s")
        print(f"  massimo legale {c['massimo_legale']} | tetto economico "
              f"{c['tetto_economico']} | stato {c['stato']}")
        for p in c["curva"]:
            print(f"    {p['prezzo']:4d} crediti  differenza {p['delta']:+.4f} "
                  f"IC95 [{p['ic95'][0]:+.4f}, {p['ic95'][1]:+.4f}]")
    misure["indifferenza"] = curve

    corrente, picco = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    misure["memoria_MB"] = {"corrente": round(corrente / 1048576, 1),
                            "picco": round(picco / 1048576, 1)}
    (OUT / "misure.json").write_text(
        json.dumps(misure, indent=1, default=str), encoding="utf-8")
    with open(OUT / "rosa_migliore.json", "w", encoding="utf-8") as f:
        json.dump({"strategia": out["migliore"]["strategia"],
                   "rosa": {r: [int(p) for p in v]
                            for r, v in out["migliore"]["rosa"].items()},
                   "nomi": {r: [pool[p].name for p in v]
                            for r, v in out["migliore"]["rosa"].items()},
                   "costo": out["migliore"].get("costo")},
                  f, indent=1, ensure_ascii=False)
    print(f"\nmemoria: picco {misure['memoria_MB']['picco']} MB")
    print(f"scritto {OUT / 'misure.json'} e rosa_migliore.json")
    print("\nAVVERTENZA: i numeri di P(primo posto) dipendono dal cubo attuale, "
          "che ha ancora i difetti elencati in reports/CRITERI_L2_L3.md sezione 0. "
          "Servono a misurare i tempi, non a scegliere una rosa.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
