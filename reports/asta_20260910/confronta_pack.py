"""Confronto fra due pack: quello congelato e il candidato.

Uso: python confronta_pack.py <pack_vecchio.pkl> <pack_nuovo.pkl>
Esce 0 se il candidato supera i controlli minimi, 1 altrimenti. I controlli
sono dichiarati prima di guardare i numeri: stagione uguale, quote e budget
uguali, almeno 500 giocatori, K nelle predizioni = giornate nei voti,
nessun valore NaN, meno del 5 % di identificativi persi, e nessun cambio di
ruolo. Il resto e' descrittivo.
"""
from __future__ import annotations

import math
import pickle
import statistics as st
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
ROOT = Path(r"fantabot")
sys.path.insert(0, str(ROOT / "src"))

vecchio = pickle.load(open(sys.argv[1], "rb"))
nuovo = pickle.load(open(sys.argv[2], "rb"))
esiti = []


def controlla(nome, cond, dett):
    esiti.append((nome, bool(cond), dett))
    print(f"  [{'ok ' if cond else 'NO '}] {nome}: {dett}")


pv, pn = vecchio.b_predictions, nuovo.b_predictions
print("\n-- struttura")
controlla("stessa stagione", vecchio.season == nuovo.season, f"{vecchio.season} / {nuovo.season}")
controlla("quote e budget uguali", vecchio.quotas == nuovo.quotas and vecchio.budget == nuovo.budget,
          f"{nuovo.quotas} {nuovo.budget}")
controlla("almeno 500 giocatori", len(nuovo.players) >= 500,
          f"{len(vecchio.players)} -> {len(nuovo.players)}")
kv = {v.get("k") for v in pv.values()}
kn = {v.get("k") for v in pn.values()}
giornate_n = sum(1 for g in nuovo.votes_by_g if g)
giornate_v = sum(1 for g in vecchio.votes_by_g if g)
controlla("K coerente con le giornate nei voti", kn == {giornate_n},
          f"K {kv} -> {kn}; giornate con voti {giornate_v} -> {giornate_n}")
nan = [pid for pid, v in pn.items()
       for kk in ("q10", "q50", "q90", "value")
       if v.get(kk) is None or (isinstance(v.get(kk), float) and math.isnan(v[kk]))]
controlla("nessun NaN in q10/q50/q90/value", not nan, f"{len(nan)} righe con NaN")
persi = set(vecchio.players) - set(nuovo.players)
nuovi_id = set(nuovo.players) - set(vecchio.players)
controlla("identificativi persi sotto il 5 %", len(persi) < 0.05 * len(vecchio.players),
          f"persi {len(persi)}, nuovi {len(nuovi_id)}")
cambi_ruolo = [pid for pid in set(vecchio.players) & set(nuovo.players)
               if vecchio.players[pid].role != nuovo.players[pid].role]
controlla("nessun cambio di ruolo", not cambi_ruolo,
          f"{[(vecchio.players[p].name, vecchio.players[p].role, nuovo.players[p].role) for p in cambi_ruolo[:5]]}")
controlla("stessa squadra (cambi ammessi solo se pochi)",
          sum(1 for pid in set(vecchio.players) & set(nuovo.players)
              if vecchio.players[pid].team != nuovo.players[pid].team) < 15,
          f"{[(vecchio.players[p].name, vecchio.players[p].team, nuovo.players[p].team) for p in set(vecchio.players) & set(nuovo.players) if vecchio.players[p].team != nuovo.players[p].team][:10]}")

print("\n-- persi:", sorted(vecchio.players[p].name for p in persi)[:40])
print("-- nuovi:", sorted(nuovo.players[p].name for p in nuovi_id)[:40])

print("\n-- spostamenti per ruolo (giocatori in entrambi)")
comuni = [pid for pid in pv if pid in pn]
for r in "PDCA":
    ids = [pid for pid in comuni if nuovo.players[pid].role == r]
    dq = [pn[p]["q50"] - pv[p]["q50"] for p in ids]
    dv = [pn[p]["value"] - pv[p]["value"] for p in ids]
    print(f"  {r}: n={len(ids)} dq50 mediana {st.median(dq):+.1f} (max |{max(map(abs, dq)):.1f}|) "
          f"dvalue mediana {st.median(dv):+.1f} (max |{max(map(abs, dv)):.1f}|)")

print("\n-- 25 spostamenti di valore piu' grandi")
for pid in sorted(comuni, key=lambda p: -abs(pn[p]["value"] - pv[p]["value"]))[:25]:
    a, b = pv[pid], pn[pid]
    p = nuovo.players[pid]
    print(f"  {p.name:18s} {p.role} {p.team:4s} value {a['value']:6.1f} -> {b['value']:6.1f} "
          f"q50 {a['q50']:6.1f} -> {b['q50']:6.1f} pres {a.get('pres')} -> {b.get('pres')}")

print("\n-- top 12 per ruolo nel candidato (valore), con rango vecchio")
for r in "PDCA":
    old_rank = {pid: i for i, pid in enumerate(sorted(
        (p for p in pv if vecchio.players[p].role == r), key=lambda p: -pv[p]["value"]), 1)}
    new = sorted((p for p in pn if nuovo.players[p].role == r), key=lambda p: -pn[p]["value"])[:12]
    print(f"  {r}: " + ", ".join(f"{nuovo.players[p].name} ({old_rank.get(p, '-')}->{i})"
                                 for i, p in enumerate(new, 1)))

print("\n" + "=" * 62)
falliti = [n for n, ok, _ in esiti if not ok]
print(f"{len(esiti) - len(falliti)}/{len(esiti)} controlli superati")
if falliti:
    print("FALLITI:", falliti)
sys.exit(1 if falliti else 0)
