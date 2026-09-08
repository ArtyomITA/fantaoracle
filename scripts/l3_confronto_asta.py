"""Confronto fra quattro modi di fare la stessa asta, in mondi separati.

## Che cosa confronta

    1. B congelato          il bot attuale, non toccato
    2. B coerente           stesso bot, ma la ripianificazione in asta usa la
                            stessa soglia di spesa del piano scelto offline
    3. L3 selezione         il piano viene dalla ricerca su candidate per
                            l'obiettivo P(primo posto)
    4. L3 + indifferenza    come sopra, ma il tetto d'asta viene dal confronto
                            fra comprare e passare

## Perche' mondi separati

Mettere due bot diversi nella stessa asta li fa interagire: il secondo compra
quello che il primo ha lasciato, e la differenza misurata contiene quella
interazione invece della politica. Qui ogni trattamento gioca la **sua** asta,
con lo stesso seme, gli stessi nove avversari e lo stesso stato iniziale.
Confronto appaiato replica per replica.

## Le sedie

La posizione al tavolo conta: chi chiama per primo e chi per ultimo non ha lo
stesso problema. Il nostro seggio ruota fra le repliche, cosi' nessun
trattamento eredita una posizione favorevole.

## Famiglie di avversari, dichiarate prima

    mercato      compra vicino ai prezzi di listino (bot A, listino di mercato)
    top          concentra la spesa sui piu' cari (C stars_scrubs)
    valore       guarda il rapporto fra punti e crediti (C informato)
    vincoli      distribuisce fra i reparti (C semitop, C medio)
    caldo        rilancia quando teme di perdere il giocatore (C panic)

Le famiglie sono fissate qui e non cambiano dopo aver visto i risultati.

## Che cosa si misura

Primario: P(primo posto) nel banco dichiarato, come differenza appaiata fra
trattamenti sugli stessi scenari e sullo stesso calendario.
Secondario: fantapunti, spesa, residuo, acquisti per reparto, target persi,
quante volte il tetto per indifferenza e' stato davvero usato.

Uso:
  python scripts/l3_confronto_asta.py --repliche 6 --scenari 30
"""
from __future__ import annotations

import argparse
import json
import pickle
import random
import sys
import time
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
OUT = ROOT / "data" / "l3" / "asta"

from fantabot.bots.bot_a import ABot                    # noqa: E402
from fantabot.bots.bot_b import BBot                    # noqa: E402
from fantabot.bots.bot_c import CBot                    # noqa: E402
from fantabot.bots.bot_l3 import BBotCoerente, BotL3    # noqa: E402
from fantabot.engine.auction import AuctionEngine       # noqa: E402
from fantabot.livello3 import ricerca as R              # noqa: E402
from fantabot.livello3 import valutatore as V           # noqa: E402
from fantabot.models import ROLES                       # noqa: E402

# famiglie di avversari, dichiarate prima di guardare i risultati
AVVERSARI = ["A", "C:stars_scrubs", "C:informato", "C:semitop", "C:medio",
             "C:panic", "C:ancorato", "C:tirchio", "C:tifoso"]


def _chiave(pid):
    """Identificativo nella forma usata dal cubo (intero quando possibile)."""
    try:
        return int(pid)
    except (TypeError, ValueError):
        return pid


def fai_avversario(spec: str, rng, pack):
    if spec == "A":
        return ABot(rng, price_list=pack.a_price_list)
    if spec.startswith("C:"):
        prof = spec.split(":", 1)[1]
        fav = (rng.choice(sorted({p.team for p in pack.players.values()}))
               if prof == "tifoso" else None)
        hint = pack.a_price_list if prof == "informato" else None
        return CBot(rng, prof, fav_team=fav, hint_prices=hint)
    raise ValueError(spec)


def fai_nostro(trattamento: str, rng, pack, piano=None, tetti=None):
    obj = getattr(pack, "b_objective", None)
    if trattamento == "B":
        return BBot(rng, pack.b_predictions, objective=obj)
    if trattamento == "B+":
        return BBotCoerente(rng, pack.b_predictions, objective=obj)
    if trattamento == "L3":
        return BotL3(rng, pack.b_predictions, piano=piano, tetti=None,
                     objective=obj, usa_indifferenza=False)
    if trattamento == "L3+I":
        return BotL3(rng, pack.b_predictions, piano=piano, tetti=tetti,
                     objective=obj, usa_indifferenza=True)
    raise ValueError(trattamento)


def gioca_asta(pack, trattamento, seme, seggio, piano=None, tetti=None):
    """Un'asta completa, con il nostro bot al seggio indicato."""
    rng = random.Random(seme)
    specs = list(AVVERSARI)
    bots, etichette = [], []
    j = 0
    for i in range(10):
        if i == seggio:
            b = fai_nostro(trattamento, random.Random(seme * 1000 + i), pack,
                           piano, tetti)
            etichette.append("NOI")
        else:
            b = fai_avversario(specs[j], random.Random(seme * 1000 + i), pack)
            etichette.append(f"AVV{j + 1:02d}:{specs[j]}")
            j += 1
        bots.append(b)
    eng = AuctionEngine(dict(pack.players), bots, pack.quotas, pack.budget, rng)
    squadre = eng.run()
    rose = {}
    speso = {}
    for i, t in enumerate(squadre):
        # le chiavi del motore d'asta sono stringhe, quelle del cubo interi:
        # senza la conversione ogni giocatore risulta assente e tutte le rose
        # segnano zero punti (misurato: P(1) 0,100 per tutte e dieci, cioe' il
        # pareggio a zero diviso in dieci)
        rose[etichette[i]] = {r: [_chiave(pid) for pid, _ in t.roster[r]]
                              for r in ROLES}
        speso[etichette[i]] = pack.budget - t.budget
    nostro = bots[seggio]
    return {"rose": rose, "speso": speso,
            "rapporto_bot": nostro.rapporto() if hasattr(nostro, "rapporto") else {},
            "seggio": seggio}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--stagione", default="2026-27")
    ap.add_argument("--repliche", type=int, default=6)
    ap.add_argument("--scenari", type=int, default=30)
    ap.add_argument("--seme", type=int, default=20260907)
    ap.add_argument("--trattamenti", nargs="*",
                    default=["B", "B+", "L3", "L3+I"])
    ap.add_argument("--piano", default=None,
                    help="JSON con la rosa scelta dalla ricerca L3")
    ap.add_argument("--tetti", default=None,
                    help="JSON dei tetti di indifferenza (scripts/l3_tetti.py)")
    a = ap.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)

    with open(ROOT / "data" / "packs" / f"pack_{a.stagione}.pkl", "rb") as f:
        pack = pickle.load(f)
    with open(ROOT / "data" / "l2" / f"cubo_{a.stagione}.pkl", "rb") as f:
        salvato = pickle.load(f)
    cubo = salvato["cubo"]
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
    n_g = cubo.fantavoto.shape[1]
    scenari = list(range(min(a.scenari, cubo.fantavoto.shape[0])))
    cal = V.calendario_berger(10, n_g, seme=a.seme)

    piano = None
    if a.piano and Path(a.piano).exists():
        d = json.loads(Path(a.piano).read_text("utf-8"))
        piano = {str(pid): {"titolare": False}
                 for r in d.get("rosa", {}) for pid in d["rosa"][r]}
        print(f"piano L3 caricato: {len(piano)} giocatori da {a.piano}")
    elif "L3" in a.trattamenti or "L3+I" in a.trattamenti:
        print("ATTENZIONE: nessun piano L3 fornito (--piano). I trattamenti L3 "
              "useranno il piano del MILP come B+, quindi la differenza "
              "misurata NON e' quella della selezione del Livello 3.")

    # Tetti di indifferenza. Regola d'uso scritta prima dell'esperimento nei
    # criteri, sezione 3.8: entrano solo con stato `verificato` o
    # `approssimato`; con stato `inconcludente` il bot ripiega sul tetto di B e
    # conta il ripiego. Senza questo file il trattamento L3+I coincide con L3,
    # e lo si dichiara qui invece di lasciarlo capire dai numeri.
    tetti = None
    if a.tetti and Path(a.tetti).exists():
        d = json.loads(Path(a.tetti).read_text("utf-8"))
        usabili = {"verificato", "approssimato"}
        tetti = {}
        for pid, v in d.get("tetti", {}).items():
            if v.get("stato") in usabili and v.get("tetto_economico"):
                tetti[str(pid)] = float(v["tetto_economico"])
        print(f"tetti di indifferenza: {len(tetti)} usabili su "
              f"{len(d.get('tetti', {}))} calcolati "
              f"(stati: {d.get('conteggio_stati')})")
        if not tetti:
            print("ATTENZIONE: nessun tetto utilizzabile. L3+I coincide con L3 "
                  "per costruzione; la differenza fra i due sara' zero e non "
                  "misura due politiche diverse.")
    elif "L3+I" in a.trattamenti:
        print("ATTENZIONE: nessun file di tetti (--tetti). Il trattamento L3+I "
              "coincide con L3 e la differenza misurata NON e' quella del "
              "prezzo di indifferenza.")

    righe = []
    t0 = time.time()
    for rep in range(a.repliche):
        seme = a.seme + rep
        seggio = rep % 10          # le sedie ruotano
        for tr in a.trattamenti:
            t1 = time.time()
            try:
                res = gioca_asta(pack, tr, seme, seggio, piano, tetti)
            except Exception as e:
                righe.append({"replica": rep, "trattamento": tr,
                              "errore": f"{type(e).__name__}: {e}"})
                print(f"  replica {rep} {tr}: ERRORE {type(e).__name__}: {e}")
                continue
            # valutazione: tutte le rose dell'asta, stessi scenari e calendario
            rose = {k: v for k, v in res["rose"].items()}
            problemi = V.verifica_rose(rose, regole)
            if problemi:
                righe.append({"replica": rep, "trattamento": tr,
                              "errore": "rose illegali: " + "; ".join(problemi[:3])})
                print(f"  replica {rep} {tr}: ROSE ILLEGALI {problemi[:2]}")
                continue
            # controllo esplicito: i giocatori delle rose devono esistere nel
            # cubo, altrimenti la valutazione da' zero senza dirlo
            noti = set(cubo.giocatori)
            ignoti = [pid for v in rose.values() for r in v for pid in v[r]
                      if pid not in noti]
            if ignoti:
                righe.append({"replica": rep, "trattamento": tr,
                              "errore": f"{len(ignoti)} giocatori delle rose non "
                                        f"sono nel cubo, es. {ignoti[:3]}"})
                print(f"  replica {rep} {tr}: {len(ignoti)} giocatori fuori dal cubo")
                continue
            e = V.valuta(cubo, rose, regole, calendario=cal, scenari=scenari,
                         controlla_legalita=False)
            p1 = e.p_primo()
            i_noi = e.squadre.index("NOI")
            righe.append({
                "replica": rep, "trattamento": tr, "seggio": seggio,
                "p1": round(p1["NOI"], 5),
                "p1_se": round(e.errore_standard()["NOI"], 5),
                "punti_stagione": round(float(e.punteggi[:, i_noi].sum(1).mean()), 1),
                "punti_giornata": round(float(e.punteggi[:, i_noi].mean()), 3),
                "gol_giornata": round(float(e.gol[:, i_noi].mean()), 4),
                "speso": res["speso"]["NOI"],
                "residuo": pack.budget - res["speso"]["NOI"],
                "parita_al_primo": e.diagnostica["scenari_con_parita_al_primo"],
                "rapporto_bot": res["rapporto_bot"],
                "secondi": round(time.time() - t1, 1),
            })
            print(f"  replica {rep} seggio {seggio} {tr:5s}: P(1) {p1['NOI']:.3f} "
                  f"| speso {res['speso']['NOI']:3d} | punti/giornata "
                  f"{righe[-1]['punti_giornata']:.1f} ({righe[-1]['secondi']:.0f} s)")

    import pandas as pd
    df = pd.DataFrame(righe)
    df.to_csv(OUT / f"confronto_asta_{a.stagione}.csv", index=False)
    ok = df[df.get("errore").isna()] if "errore" in df else df
    print(f"\ntempo totale {time.time() - t0:.0f} s, "
          f"{len(ok)}/{len(df)} aste riuscite")
    if len(ok):
        print("\nmedia per trattamento:")
        print(ok.groupby("trattamento")[["p1", "punti_giornata", "gol_giornata",
                                         "speso", "residuo"]]
                .mean().round(4).to_string())
        # differenze appaiate rispetto al trattamento di riferimento
        rif = a.trattamenti[0]
        print(f"\ndifferenza appaiata di P(1 posto) rispetto a {rif}, "
              "per replica (bootstrap 4000):")
        base = ok[ok.trattamento == rif].set_index("replica")["p1"]
        rng = np.random.default_rng(a.seme)
        confronti = {}
        for tr in a.trattamenti[1:]:
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
            confronti[tr] = {"differenza": float(d.mean()), "ic95": [lo, hi],
                             "esclude_zero": esclude, "repliche": len(comuni)}
            print(f"  {tr:6s} {d.mean():+.4f}  IC95 [{lo:+.4f}, {hi:+.4f}]  "
                  f"{'ESCLUDE lo zero' if esclude else 'attraversa lo zero: inconcludente'}"
                  f"  ({len(comuni)} repliche)")
        (OUT / f"confronto_asta_{a.stagione}.json").write_text(
            json.dumps({"confronti": confronti, "repliche": a.repliche,
                        "scenari": len(scenari), "seme": a.seme,
                        "avversari": AVVERSARI,
                        "calendario_dichiarato": True,
                        "avvertenza": ("il calendario della lega non e' noto: e' "
                                       "generato da un seme dichiarato. Il "
                                       "risultato e' condizionato a questo banco, "
                                       "non e' la probabilita' di vincere la lega "
                                       "reale.")},
                       indent=1, default=str), encoding="utf-8")
    print(f"\nscritto {OUT / ('confronto_asta_' + a.stagione + '.csv')}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
