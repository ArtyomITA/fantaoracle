"""Quanto vale il bersaglio quando non vede l'esito.

Misura decisiva per il ramo delle presenze. I report precedenti dicevano che
il bersaglio grezzo era piu' vicino alla realta' del cubo, e ne traevano che
calibrare il cubo verso quel bersaglio fosse inseguire un riferimento migliore
di chi lo insegue. Il confronto era viziato: quel bersaglio aveva visto
l'esito, tramite `fvm` (valore di fine stagione nei listoni archiviati) e
`quot_fs_sett` (snapshot di giornata 2 o 3 della stagione da predire).


Confronta, contro le presenze davvero realizzate nel 2024-25:
  A) il bersaglio attuale, da `b_predictions_2024-25.json` (36 feature, due
     delle quali posteriori al cutoff);
  B) il bersaglio per origine, con le sole feature ammesse.
Unita': probabilita' di presenza a voto per giocatore-giornata, come nel pilota.
"""
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

RAD = Path("fantabot")
sys.path.insert(0, str(RAD / "src"))
PROC = RAD / "data" / "processed"
GIORNATE = 38
STAGIONE = "2024-25"

from fantabot.tabellino import contratto  # noqa: E402

rose, ruolo, squadra, _ = contratto.costruisci_universo(PROC, STAGIONE)
giocatori = sorted(ruolo)

# osservato: presenze a voto realizzate / 38
v = pd.read_parquet(PROC / f"votes_{STAGIONE}.parquet")
vere = v[v.sv == 0].groupby("master_id").size()
oss = pd.Series({p: float(vere.get(p, 0)) / GIORNATE for p in giocatori})

# A) bersaglio attuale
crudo = json.loads((PROC / f"b_predictions_{STAGIONE}.json").read_text("utf-8"))
att = {}
for k, q in crudo.items():
    try:
        pid = int(k)
    except (TypeError, ValueError):
        continue
    if isinstance(q, dict) and q.get("pres") is not None:
        att[pid] = min(max(float(q["pres"]) / GIORNATE, 0.0), 1.0)
A = pd.Series({p: att.get(p, np.nan) for p in giocatori})

# B) bersaglio per origine, feature ammesse
cart = sorted((RAD / "data/l1/presenze").glob(f"{STAGIONE}__origine20240816__*"))
if not cart:
    raise SystemExit("manca l'artefatto per origine: eseguire prima "
                     "scripts/l1_presenze_per_origine.py")
t = pd.read_csv(cart[-1] / "presenze_per_origine.csv")
man = json.loads((cart[-1] / "manifesto_origine.json").read_text("utf-8"))
B = pd.Series({int(r.master_id): min(max(float(r.presenze_residue_attese)
                                         / float(r.orizzonte_giornate), 0.0), 1.0)
               for r in t.itertuples()}).reindex(giocatori)

d = pd.DataFrame({"osservato": oss, "attuale": A, "per_origine": B}).dropna()
print(f"artefatto per origine: {cart[-1].name}")
print(f"origine {man['origine']}, feature usate {len(man['ingressi'])}, "
      f"utilizzabile operativamente: {man['utilizzabile_operativamente']}")
print(f"giocatori confrontati: {len(d)}\n")
print(f"{'bersaglio':<14}{'MAE':>9}{'rho':>9}{'somma':>10}")
for c in ("attuale", "per_origine"):
    mae = float((d[c] - d.osservato).abs().mean())
    rho = float(d[c].corr(d.osservato, method="spearman"))
    print(f"  {c:<12}{mae:>9.4f}{rho:>9.4f}{d[c].sum():>10.1f}")
print(f"  {'osservato':<12}{0.0:>9.4f}{1.0:>9.4f}{d.osservato.sum():>10.1f}")

peggio = (float((d.per_origine - d.osservato).abs().mean())
          - float((d.attuale - d.osservato).abs().mean()))
print(f"\nil bersaglio onesto e' piu' lontano dall'osservato di {peggio:+.4f} "
      "in probabilita' per giocatore-giornata")
print(f"in presenze su una stagione intera: {peggio * GIORNATE:+.2f} per giocatore")
