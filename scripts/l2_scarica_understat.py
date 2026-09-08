"""Acquisizione dei risultati e degli xG di Serie A partita per partita.

Serve al Livello 2 per due cose distinte:
  1. il calendario e i risultati della stagione in corso, che Transfermarkt non
     copre piu' (il dataset dcaribou ha aggiornamenti sospesi da luglio 2026,
     https://github.com/dcaribou/transfermarkt-datasets/discussions/383);
  2. gli xG per partita, che nel progetto esistevano solo come aggregati di
     stagione. Gli xG per partita sono la covariata piu' informativa per le
     forze di attacco e difesa di una squadra.

Fonte: Understat, tramite la libreria `understatapi` gia' usata dal progetto
(`get_match_data`). Restituisce l'elenco completo delle partite di una
stagione — giocate e non — con data, squadre, gol e xG delle sole giocate.

Attenzione alla disciplina temporale: gli xG di una partita esistono solo dopo
che la partita e' stata giocata. La colonna `data` e' il momento dell'evento;
`acquisito_il` e' il momento in cui il dato e' entrato nel progetto. Chi usa
questi dati per una previsione con data limite `as_of` deve filtrare su `data`,
non sulla giornata.

Verifiche eseguite:
  - 380 partite per stagione, 20 squadre, 19 in casa e 19 fuori per squadra;
  - per la stagione in corso, riscontro incrociato con il calendario
    fantacalcio.it (`scripts/l2_scarica_calendario.py`): stesse coppie,
    stesse date, stessi risultati per le partite gia' giocate.

Uso:
  python scripts/l2_scarica_understat.py 2019 2020 2021 2022 2023 2024 2025 2026
  python scripts/l2_scarica_understat.py 2026 --riscontro 2026-27
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from collections import Counter
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
DEST = ROOT / "data" / "raw" / "understat"
CAL = ROOT / "data" / "raw" / "calendario"

# Understat usa nomi propri; qui la corrispondenza con i nomi dei voti
# fantacalcio.it, che sono la chiave del resto del progetto.
ALIAS = {
    "AC Milan": "Milan",
    "Parma Calcio 1913": "Parma",
    "Hellas Verona": "Verona",
    "Verona": "Verona",
    "SPAL": "Spal",
}


def canonico(nome: str) -> str:
    return ALIAS.get(nome, nome)


def scarica(anno: int) -> pd.DataFrame:
    from understatapi import UnderstatClient
    with UnderstatClient() as u:
        dati = u.league(league="Serie_A").get_match_data(season=str(anno))
    acquisito = time.strftime("%Y-%m-%dT%H:%M:%S")
    righe = []
    for m in dati:
        giocata = bool(m.get("isResult"))
        righe.append({
            "stagione": f"{anno}-{str(anno + 1)[2:]}",
            "id_understat": m["id"],
            "data": m["datetime"],
            "casa": canonico(m["h"]["title"]),
            "trasferta": canonico(m["a"]["title"]),
            "casa_understat": m["h"]["title"],
            "trasferta_understat": m["a"]["title"],
            "giocata": int(giocata),
            "gol_casa": int(m["goals"]["h"]) if giocata else None,
            "gol_trasferta": int(m["goals"]["a"]) if giocata else None,
            "xg_casa": float(m["xG"]["h"]) if giocata and m["xG"]["h"] else None,
            "xg_trasferta": float(m["xG"]["a"]) if giocata and m["xG"]["a"] else None,
            "fonte": "understat",
            "acquisito_il": acquisito,
        })
    return pd.DataFrame(righe).sort_values("data").reset_index(drop=True)


def verifica(df: pd.DataFrame, anno: int) -> list[str]:
    p = []
    squadre = sorted(set(df.casa) | set(df.trasferta))
    if len(squadre) != 20:
        p.append(f"{anno}: {len(squadre)} squadre, attese 20")
    if len(df) != 380:
        p.append(f"{anno}: {len(df)} partite, attese 380")
    for s in squadre:
        c, f = int((df.casa == s).sum()), int((df.trasferta == s).sum())
        if (c, f) != (19, 19):
            p.append(f"{anno} {s}: {c} in casa e {f} fuori, attese 19 e 19")
    doppi = [k for k, n in Counter(zip(df.casa, df.trasferta)).items() if n != 1]
    if doppi:
        p.append(f"{anno}: accoppiamenti ripetuti {doppi[:5]}")
    g = df[df.giocata == 1]
    if len(g) and g[["gol_casa", "gol_trasferta"]].isna().any().any():
        p.append(f"{anno}: partite giocate senza risultato")
    sx = g["xg_casa"].isna().sum()
    if sx:
        p.append(f"{anno}: {sx} partite giocate senza xG")
    return p


def riscontro(df: pd.DataFrame, stagione: str) -> list[str]:
    """Confronto indipendente con il calendario fantacalcio.it."""
    f = CAL / f"calendario_{stagione}.csv"
    if not f.exists():
        return [f"riscontro impossibile: manca {f.name}"]
    cal = pd.read_csv(f)
    p = []
    a = set(zip(df.casa, df.trasferta))
    b = set(zip(cal.casa, cal.trasferta))
    if a != b:
        p.append(f"accoppiamenti diversi: solo Understat {sorted(a - b)[:5]}, "
                 f"solo fantacalcio {sorted(b - a)[:5]}")
    m = df.merge(cal, on=["casa", "trasferta"], suffixes=("_u", "_f"))
    if len(m) != len(df):
        p.append(f"unione parziale: {len(m)}/{len(df)}")
    g = m[(m.giocata_u == 1) & (m.giocata_f == 1)]
    diff = g[(g.gol_casa_u != g.gol_casa_f) | (g.gol_trasferta_u != g.gol_trasferta_f)]
    if len(diff):
        p.append(f"{len(diff)} risultati discordanti fra le due fonti: "
                 + ", ".join(f"{r.casa}-{r.trasferta} "
                             f"{r.gol_casa_u}-{r.gol_trasferta_u} contro "
                             f"{r.gol_casa_f}-{r.gol_trasferta_f}"
                             for r in diff.head(5).itertuples()))
    du = pd.to_datetime(m.data_u, errors="coerce").dt.date
    dfc = pd.to_datetime(m.data_f, errors="coerce").dt.date
    scarti = int((du != dfc).sum())
    if scarti:
        p.append(f"{scarti} partite con data diversa fra le due fonti "
                 "(orari e rinvii: normale sulle partite non ancora giocate)")
    return p


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("anni", nargs="*", type=int,
                    default=[2019, 2020, 2021, 2022, 2023, 2024, 2025, 2026])
    ap.add_argument("--riscontro", default=None,
                    help="stagione (es. 2026-27) da confrontare col calendario")
    a = ap.parse_args()
    DEST.mkdir(parents=True, exist_ok=True)
    tutti, problemi = [], []
    for anno in a.anni:
        try:
            df = scarica(anno)
        except Exception as e:
            print(f"{anno}: ERRORE {type(e).__name__}: {e}", file=sys.stderr)
            problemi.append(f"{anno}: {type(e).__name__}")
            continue
        prob = verifica(df, anno)
        problemi.extend(prob)
        out = DEST / f"partite_{anno}.csv"
        df.to_csv(out, index=False, encoding="utf-8")
        print(f"{anno}: {len(df)} partite, {int(df.giocata.sum())} giocate, "
              f"xG su {int(df.xg_casa.notna().sum())} -> {out.name}"
              + ("  PROBLEMI: " + "; ".join(prob) if prob else ""))
        tutti.append(df)
        time.sleep(0.5)
    if a.riscontro and tutti:
        anno = int(a.riscontro[:4])
        df = next((d for d in tutti if d.stagione.iloc[0] == a.riscontro), None)
        if df is not None:
            r = riscontro(df, a.riscontro)
            print(f"\nriscontro con il calendario fantacalcio.it ({a.riscontro}):")
            print("  nessuna discordanza" if not r else "\n".join("  " + x for x in r))
            problemi.extend(r)
    (DEST / "acquisizione_partite.json").write_text(json.dumps({
        "anni": a.anni, "acquisito_il": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "fonte": "understat via understatapi (get_match_data)",
        "problemi": problemi}, indent=1, ensure_ascii=False), encoding="utf-8")
    return 1 if problemi else 0


if __name__ == "__main__":
    sys.exit(main())
