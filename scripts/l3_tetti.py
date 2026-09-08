"""Tetti d'asta per indifferenza, calcolati una volta prima delle repliche.

Il tetto di un giocatore e' il prezzo piu' alto per cui comprarlo aumenta la
probabilita' di arrivare primi rispetto a passare. `livello3.indifferenza.curva`
lo calcola completando l'asta molte volte da entrambi i rami, e restituisce
anche lo **stato** del confronto: `verificato`, `approssimato` o
`inconcludente`.

Il calcolo dipende dal cubo e dal piano, non dalla replica: si fa una volta
dallo stato iniziale (nulla comprato, tutti disponibili) e si riusa. La regola
d'uso dei tetti in asta e' scritta in `reports/CRITERI_L2_L3.md`, sezione 3.8:
entrano solo con stato `verificato` o `approssimato`, altrimenti il bot ripiega
sul tetto di B e conta il ripiego.

Uso:
    python scripts/l3_tetti.py --piano data/l3/pilota/rosa_migliore.json
"""
from __future__ import annotations

import argparse
import json
import pickle
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from fantabot.livello3 import indifferenza as I     # noqa: E402
from fantabot.livello3 import valutatore as V       # noqa: E402

OUT = ROOT / "data" / "l3" / "asta"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--stagione", default="2026-27")
    ap.add_argument("--piano", required=True)
    ap.add_argument("--scenari", type=int, default=20)
    ap.add_argument("--repliche", type=int, default=4)
    ap.add_argument("--prezzi", type=int, default=5)
    ap.add_argument("--seme", type=int, default=20260907)
    a = ap.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)

    with open(ROOT / "data" / "packs" / f"pack_{a.stagione}.pkl", "rb") as f:
        pack = pickle.load(f)
    with open(ROOT / "data" / "l2" / f"cubo_{a.stagione}.pkl", "rb") as f:
        salvato = pickle.load(f)
    cubo = salvato["cubo"]

    preds = pack.b_predictions
    pool, prezzi, valori = {}, {}, {}
    nel_cubo = set(cubo.giocatori)
    for pid, p in pack.players.items():
        chiave = int(pid) if str(pid).isdigit() else pid
        if chiave not in nel_cubo:
            continue
        pool[chiave] = p
        pr = preds.get(pid, {}) or preds.get(str(pid), {})
        prezzi[chiave] = max(1.0, float(pr.get("q50", p.ref_price * pack.budget)))
        valori[chiave] = float(pr.get("value", 0.0))

    bonus = getattr(cubo, "gol_subiti", None) is not None
    if not bonus:
        print("ATTENZIONE: il cubo non porta i gol subiti; il bonus porta "
              "inviolata NON entra nei punteggi.")
    regole = V.Regole(quote=dict(pack.quotas), budget=pack.budget,
                      usa_mod_difesa=bool(pack.use_mod_difesa),
                      applica_bonus_porta_inviolata=bonus)

    piano = json.loads(Path(a.piano).read_text("utf-8"))
    bersagli = [int(pid) for r in piano["rosa"] for pid in piano["rosa"][r]]
    fuori = [pid for pid in bersagli if pid not in pool]
    if fuori:
        # un giocatore del piano che non e' nel cubo non e' valutabile: lo si
        # dichiara invece di saltarlo in silenzio
        print(f"BLOCCO PARZIALE: {len(fuori)} giocatori del piano non sono nel "
              f"cubo e restano senza tetto: {fuori}")
    bersagli = [pid for pid in bersagli if pid in pool]

    n_scen = cubo.fantavoto.shape[0]
    scenari = list(range(min(a.scenari, n_scen // 2)))
    cal = V.calendario_berger(10, cubo.fantavoto.shape[1], seme=a.seme)
    avversari = {f"AVV{i + 1:02d}": {"rosa": {r: [] for r in regole.quote},
                                     "budget": float(pack.budget)}
                 for i in range(9)}
    stato = I.StatoAsta(nostra={r: [] for r in regole.quote},
                        nostro_budget=float(pack.budget), avversari=avversari,
                        disponibili=set(pool), regole=regole)

    fuori_json, conta = {}, {"verificato": 0, "approssimato": 0,
                             "inconcludente": 0}
    t_tot = time.time()
    for k, g in enumerate(bersagli, 1):
        mercato = int(round(prezzi[g]))
        griglia = sorted({max(1, int(mercato * f))
                          for f in (0.6, 0.8, 1.0, 1.3, 1.6, 2.0)})[:a.prezzi]
        t0 = time.time()
        c = I.curva(g, stato, pool, prezzi, valori, cubo, cal, scenari,
                    prezzi_da_provare=griglia, repliche=a.repliche, seme=a.seme)
        dt = time.time() - t0
        stato_c = c.get("stato", "inconcludente")
        conta[stato_c] = conta.get(stato_c, 0) + 1
        fuori_json[str(g)] = {
            "nome": pool[g].name, "ruolo": pool[g].role, "mercato": mercato,
            "tetto_economico": c.get("tetto_economico"),
            "massimo_legale": c.get("massimo_legale"),
            "stato": stato_c, "secondi": round(dt, 1),
            "curva": c.get("curva", []),
        }
        print(f"{k:2d}/{len(bersagli)} {pool[g].name[:22]:22s} "
              f"({pool[g].role}, mercato {mercato:3d}) tetto "
              f"{str(c.get('tetto_economico')):>4s} | {stato_c:14s} {dt:5.1f} s")

    riassunto = {
        "stagione": a.stagione, "seme": a.seme, "scenari": len(scenari),
        "repliche": a.repliche, "piano": str(a.piano),
        "giocatori_senza_tetto_fuori_dal_cubo": fuori,
        "conteggio_stati": conta,
        "secondi_totali": round(time.time() - t_tot, 1),
        "tetti": fuori_json,
    }
    percorso = OUT / f"tetti_{a.stagione}.json"
    percorso.write_text(json.dumps(riassunto, indent=1, default=str),
                        encoding="utf-8")
    print(f"\nstati: {conta}")
    print(f"scritto {percorso}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
