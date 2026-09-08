"""Perche' il piano lascia crediti in cassa?

Nel benchmark 2025/26 la rosa proposta costa 399 crediti su 500. A fine asta i
crediti non spesi valgono zero, quindi o esiste un modo di spenderli che il
modello non vede, oppure il modello sta dicendo che non conviene: qui si
distingue fra le due cose, guardando nell'ordine

  1. i prezzi con cui il piano viene COSTRUITO e quelli con cui viene CONTATO;
  2. i vincoli (quota attacco, modulo) che possono bloccare la spesa;
  3. i candidati: quanto valore in piu' si comprerebbe con i crediti avanzati;
  4. il risolutore: ottimo dichiarato o interrotto dal tempo.

Uso: python scripts/indagine/diagnosi_budget.py [stagione=2025-26]
"""
from __future__ import annotations

import json
import pickle
import sys
from pathlib import Path

import pulp

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from fantabot.models import ROLES  # noqa: E402
from fantabot.optimizer import MODULES, optimize_roster  # noqa: E402


def spesa_per_ruolo(roster, prezzi):
    return {r: round(sum(prezzi[p] for p in roster[r]), 1) for r in ROLES}


def main():
    season = sys.argv[1] if len(sys.argv) > 1 else "2025-26"
    pack = pickle.load(open(ROOT / "data" / "packs" / f"pack_{season}.pkl", "rb"))
    preds = pack.b_predictions
    obj = getattr(pack, "b_objective", None) or {}
    ref = {pid: max(1.0, p.ref_price * pack.budget) for pid, p in pack.players.items()}
    q50 = {pid: max(1.0, float(preds.get(pid, {}).get("q50", 1.0))) for pid in pack.players}
    val = {pid: float(preds.get(pid, {}).get("value", 0.0)) for pid in pack.players}
    vup = {pid: float(preds.get(pid, {}).get("value_up", val[pid])) for pid in pack.players}
    lam = obj.get("lam", 0.0)
    forced = None
    if obj.get("attack_share"):
        lo, hi = obj["attack_share"]
        forced = {"A": (lo * pack.budget, hi * pack.budget)}
    print(f"=== {season} | budget {pack.budget} | lam {lam} | quota attacco {obj.get('attack_share')}\n")

    # 1) prezzi di costruzione vs prezzi di conteggio
    print("1) PREZZI")
    print(f"   somma q50 (stime del modello) {sum(q50.values()):7.0f} cr su {len(q50)} giocatori")
    print(f"   somma ref (mercato)           {sum(ref.values()):7.0f} cr")
    for etichetta, prezzi in [("costruito su q50", q50), ("costruito su mercato", ref)]:
        sol = optimize_roster(pack.players, prezzi, val, pack.quotas, pack.budget,
                              forced_spend=forced, values_up=vup, lam=lam)
        if sol is None:
            print(f"   {etichetta}: NESSUNA SOLUZIONE")
            continue
        costo_q50 = sum(q50[p] for r in ROLES for p in sol["roster"][r])
        costo_ref = sum(ref[p] for r in ROLES for p in sol["roster"][r])
        print(f"   {etichetta:22s} modulo {sol['module']} | costo alle stime {costo_q50:5.0f} "
              f"| costo al mercato {costo_ref:5.0f} | valore {sol['value']:6.0f}")
        print(f"      spesa per reparto (mercato): {spesa_per_ruolo(sol['roster'], ref)}")

    # 2) vincoli: cosa succede togliendo la quota attacco
    print("\n2) VINCOLI")
    for etichetta, f in [("con quota attacco", forced), ("senza quota attacco", None)]:
        sol = optimize_roster(pack.players, ref, val, pack.quotas, pack.budget,
                              forced_spend=f, values_up=vup, lam=lam)
        if sol is None:
            print(f"   {etichetta}: NESSUNA SOLUZIONE")
            continue
        costo = sum(ref[p] for r in ROLES for p in sol["roster"][r])
        print(f"   {etichetta:22s} modulo {sol['module']} costo {costo:5.0f} "
              f"valore {sol['value']:6.0f} reparti {spesa_per_ruolo(sol['roster'], ref)}")

    # 3) candidati: il valore che si comprerebbe con i crediti avanzati
    print("\n3) CANDIDATI (prezzi di mercato)")
    sol = optimize_roster(pack.players, ref, val, pack.quotas, pack.budget,
                          forced_spend=forced, values_up=vup, lam=lam)
    roster = sol["roster"]
    costo = sum(ref[p] for r in ROLES for p in roster[r])
    residuo = pack.budget - costo
    print(f"   piano: costo {costo:.0f}, avanzano {residuo:.0f} crediti")
    v_eff = {pid: val[pid] + lam * (vup[pid] - val[pid]) for pid in pack.players}
    migliori = 0
    for r in ROLES:
        dentro = sorted(roster[r], key=lambda p: v_eff[p])
        fuori = [p for p in pack.players if pack.players[p].role == r and p not in dentro]
        for uscente in dentro[:3]:
            budget_scambio = residuo + ref[uscente]
            cand = [p for p in fuori if ref[p] <= budget_scambio and v_eff[p] > v_eff[uscente]]
            if not cand:
                continue
            best = max(cand, key=lambda p: v_eff[p])
            guadagno = v_eff[best] - v_eff[uscente]
            migliori += 1
            print(f"   {r}: {pack.players[uscente].name} ({ref[uscente]:.0f}cr, "
                  f"v {v_eff[uscente]:.0f}) -> {pack.players[best].name} "
                  f"({ref[best]:.0f}cr, v {v_eff[best]:.0f}) = +{guadagno:.0f} valore")
            break
    if not migliori:
        print("   nessuno scambio migliora il valore: i crediti avanzati non "
              "comprano niente di meglio secondo il modello")

    # 4) risolutore
    print("\n4) RISOLUTORE")
    prob = pulp.LpProblem("t", pulp.LpMaximize)
    xx = pulp.LpVariable("x", cat="Binary")
    prob += xx
    st = prob.solve(pulp.PULP_CBC_CMD(msg=0, timeLimit=5))
    print(f"   CBC disponibile, stato su problema banale: {pulp.LpStatus[st]}")
    sol10 = optimize_roster(pack.players, ref, val, pack.quotas, pack.budget,
                            forced_spend=forced, values_up=vup, lam=lam, time_limit=10)
    sol60 = optimize_roster(pack.players, ref, val, pack.quotas, pack.budget,
                            forced_spend=forced, values_up=vup, lam=lam, time_limit=60)
    for et, s in [("limite 10 s", sol10), ("limite 60 s", sol60)]:
        c = sum(ref[p] for r in ROLES for p in s["roster"][r])
        print(f"   {et}: valore {s['value']:.1f} costo {c:.0f} modulo {s['module']}")
    if abs(sol10["value"] - sol60["value"]) > 1:
        print("   ATTENZIONE: con piu' tempo il valore cambia, la soluzione a 10 s "
              "non era l'ottimo")
    else:
        print("   stessa soluzione con piu' tempo: non e' un problema di tempo")


if __name__ == "__main__":
    main()
