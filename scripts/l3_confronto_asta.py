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

## I tetti arrivano interi, non come numero

`carica_tetti` passa al bot il **record** prodotto da `scripts/l3_tetti.py`
(identita', chiave di validita', completamento, stato, curva) e il `contesto`
del file. La conversione precedente a `float` rendeva ogni tetto non
verificabile: il bot lo respingeva per `senza_chiave` e ripiegava su B, quindi
il braccio L3+I non poteva differire da L3 per il motivo dichiarato. Le rose su
cui i tetti sono misurati vengono da un completamento **surrogato**
(`assegnazione_per_priorita`), non da un'asta competitiva: l'etichetta viene
stampata insieme al conteggio.

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
from fantabot.bots.bot_l3 import (                      # noqa: E402
    STATI_AMMESSI, BBotCoerente, BotL3, etichetta_completamento,
    identita_canonica)
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


def carica_tetti(percorso, stati_ammessi=STATI_AMMESSI) -> dict:
    """Legge il file dei tetti e prepara quello che il bot sa verificare.

    ## Il difetto che questa funzione sostituisce

    Fino all'8 settembre 2026 il caricamento era in linea dentro `main()` e
    faceva `tetti[str(pid)] = float(v["tetto_economico"])`. Un numero nudo non
    porta chiave di validita', identita' ne' completamento: `BotL3` lo respinge
    con ragione `senza_chiave` e ripiega sul tetto di B. Il percorso reale
    produttore -> file -> asta non funzionava, e il braccio L3+I coincideva con
    L3 senza che il motivo fosse scritto da nessuna parte.

    Qui il **record intero** arriva al bot, insieme al `contesto`: le
    componenti della chiave che l'asta non puo' osservare (cubo, esperimento,
    regole, listini). Senza contesto nessun tetto e' valido, quindi se il file
    non lo porta la funzione lo dichiara invece di lasciare che il bot respinga
    tutto per un motivo che sembra un altro.

    ## Zero non e' un dato mancante

    Il filtro precedente era `if v.get("stato") in usabili and
    v.get("tetto_economico")`: un tetto economico pari a **0** e' falso in
    Python, quindi veniva scartato esattamente come un record senza il campo.
    Sono due cose diverse: 0 con uno stato ammesso significa «nessun prezzo
    provato conviene, non rilanciare», ed e' una decisione; l'assenza del campo
    significa che non si sa. Qui restano distinti e sono contati separatamente.

    ## `stima_tetto` non e' il tetto

    Il record puo' portare anche `stima_tetto`, che e' il massimo dei delta
    positivi, distorto verso l'alto perche' scelto su k prezzi. Non viene mai
    promosso a tetto: se `tetto_economico` manca, il record e' scartato.

    Ritorna `{"tetti": {...}, "contesto": {...} | None, "diagnostica": {...}}`.
    """
    d = json.loads(Path(percorso).read_text("utf-8"))
    grezzi = d.get("tetti", {}) or {}
    diag = {"letti": len(grezzi), "usabili": 0, "identita_diversa": 0,
            "senza_identita": 0,
            "dato_mancante": 0, "tetto_non_numerico": 0, "tetto_zero": 0,
            "senza_chiave": 0, "senza_completamento": 0, "per_stato": {},
            "seggio_dichiarato": d.get("seggio"),
            "completamento": None, "contesto_mancante": None}
    contesto = d.get("contesto")
    if not isinstance(contesto, dict) or not contesto:
        contesto = None
        diag["contesto_mancante"] = (
            "il file non dichiara il blocco `contesto`: senza le componenti "
            "non osservabili della chiave (cubo, esperimento, regole) nessun "
            "tetto e' verificabile e il bot li respinge tutti")
    tetti = {}
    for pid, v in grezzi.items():
        if not isinstance(v, dict):
            diag["senza_chiave"] += 1
            continue
        # l'identita' e' la prima cosa: la chiave del dizionario non e' una
        # prova, e la forma vecchia del file non scriveva `giocatore` affatto
        try:
            ident = identita_canonica(pid)
        except ValueError:
            diag["senza_identita"] += 1
            continue
        if "giocatore" not in v:
            diag["senza_identita"] += 1
            continue
        try:
            dichiarata = identita_canonica(v["giocatore"])
        except ValueError:
            diag["senza_identita"] += 1
            continue
        if dichiarata != ident:
            diag["identita_diversa"] += 1
            continue
        stato = v.get("stato")
        diag["per_stato"][stato] = diag["per_stato"].get(stato, 0) + 1
        if "chiave_validita" not in v:
            diag["senza_chiave"] += 1
            continue
        if not isinstance(v.get("completamento"), dict):
            diag["senza_completamento"] += 1
            continue
        if diag["completamento"] is None:
            diag["completamento"] = etichetta_completamento(
                v["completamento"].get("tipo"))
        if stato not in stati_ammessi:
            continue
        if "tetto_economico" not in v or v["tetto_economico"] is None:
            diag["dato_mancante"] += 1
            continue
        t = v["tetto_economico"]
        if (isinstance(t, bool) or not isinstance(t, (int, float))
                or not np.isfinite(float(t))):
            diag["tetto_non_numerico"] += 1
            continue
        if float(t) == 0.0:
            diag["tetto_zero"] += 1
        tetti[ident] = v
        diag["usabili"] += 1
    return {"tetti": tetti, "contesto": contesto, "diagnostica": diag}


def fai_nostro(trattamento: str, rng, pack, piano=None, tetti=None,
               contesto=None):
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
                     objective=obj, usa_indifferenza=True,
                     contesto_tetti=contesto)
    raise ValueError(trattamento)


def gioca_asta(pack, trattamento, seme, seggio, piano=None, tetti=None,
               contesto=None):
    """Un'asta completa, con il nostro bot al seggio indicato."""
    rng = random.Random(seme)
    specs = list(AVVERSARI)
    bots, etichette = [], []
    j = 0
    for i in range(10):
        if i == seggio:
            b = fai_nostro(trattamento, random.Random(seme * 1000 + i), pack,
                           piano, tetti, contesto)
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
        # stessa forma canonica dei tetti: il bot incrocia piano e tetti per
        # chiave, e due normalizzazioni diverse li farebbero non combaciare
        piano = {identita_canonica(pid): {"titolare": False}
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
    # Al bot arriva il record intero e il contesto (vedi `carica_tetti`): un
    # numero nudo non e' verificabile e verrebbe respinto per `senza_chiave`.
    tetti, contesto = None, None
    diagnostica_tetti = {"file": a.tetti, "caricato": False}
    if a.tetti and Path(a.tetti).exists():
        caricati = carica_tetti(a.tetti)
        tetti, contesto = caricati["tetti"], caricati["contesto"]
        diag = caricati["diagnostica"]
        diagnostica_tetti = {"file": a.tetti, "caricato": True, **diag}
        print(f"tetti di indifferenza: {diag['usabili']} usabili su "
              f"{diag['letti']} letti (stati: {diag['per_stato']}, "
              f"tetto zero valido: {diag['tetto_zero']}, dato mancante: "
              f"{diag['dato_mancante']}, identita' discordi: "
              f"{diag['identita_diversa']}, senza identita': "
              f"{diag['senza_identita']})")
        print(f"completamento dichiarato dai record: {diag['completamento']}")
        if diag["contesto_mancante"]:
            print(f"ATTENZIONE: {diag['contesto_mancante']}")
        if diag["seggio_dichiarato"] is not None:
            print(f"i tetti sono calcolati per il seggio "
                  f"{diag['seggio_dichiarato']}: nelle repliche giocate da un "
                  "altro seggio l'impronta degli avversari non combacia e il "
                  "bot ripiega su B, contando il ripiego")
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
                res = gioca_asta(pack, tr, seme, seggio, piano, tetti,
                                 contesto)
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
                        # perche' i tetti sono entrati o no: senza questo, «L3+I
                        # coincide con L3» resta un numero senza spiegazione
                        "tetti": diagnostica_tetti,
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
