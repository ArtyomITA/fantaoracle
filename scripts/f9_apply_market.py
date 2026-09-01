"""Applica il mercato corrente alle predizioni della stagione (2026-27).

Legge gli ultimi CSV di data/raw/mercato (probabili, indisponibili,
rigoristi) e il prezzo live 2026-27, li aggancia al registry per nome+squadra,
e produce data/processed/b_predictions_{stagione}_adj.json + report.

Uso: python scripts/f9_apply_market.py [stagione=2026-27]
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
RAW = ROOT / "data" / "raw"
PROC = ROOT / "data" / "processed"

from fantabot.market_adjust import MarketInputs, adjust_predictions, norm  # noqa: E402

SIGLE = {  # nome esteso -> sigla listone (le pagine mercato usano il nome)
    "ATALANTA": "ATA", "BOLOGNA": "BOL", "CAGLIARI": "CAG", "COMO": "COM",
    "CREMONESE": "CRE", "FIORENTINA": "FIO", "FROSINONE": "FRO", "GENOA": "GEN",
    "INTER": "INT", "JUVENTUS": "JUV", "LAZIO": "LAZ", "LECCE": "LEC",
    "MILAN": "MIL", "MONZA": "MON", "NAPOLI": "NAP", "PARMA": "PAR",
    "PISA": "PIS", "ROMA": "ROM", "SASSUOLO": "SAS", "TORINO": "TOR",
    "UDINESE": "UDI", "VENEZIA": "VEN", "VERONA": "VER", "HELLAS VERONA": "VER",
    "EMPOLI": "EMP", "SALERNITANA": "SAL", "SAMPDORIA": "SAM", "SPEZIA": "SPE",
}


def latest(pattern: str) -> Path | None:
    files = sorted((RAW / "mercato").glob(pattern))
    return files[-1] if files else None


def surname_key(nome: str) -> str:
    """'Martinez L.' -> 'MARTINEZ'; 'Di Lorenzo' -> 'DI LORENZO'."""
    n = norm(nome)
    parts = n.split()
    if len(parts) > 1 and len(parts[-1]) <= 2:   # iniziale
        parts = parts[:-1]
    return " ".join(parts)


class Matcher:
    """Aggancio nome+squadra -> master_id sul registry della stagione."""

    def __init__(self, reg: pd.DataFrame):
        self.by_key: dict[tuple[str, str], list[tuple[str, str]]] = {}
        self.by_surname: dict[str, list[tuple[str, str, str]]] = {}
        for r in reg.itertuples(index=False):
            mid = str(r.master_id)
            full = norm(r.nome)
            sk = surname_key(r.nome)
            self.by_key.setdefault((sk, r.squadra), []).append((mid, full))
            self.by_surname.setdefault(sk, []).append((mid, full, r.squadra))

    def match(self, nome: str, squadra: str | None) -> str | None:
        sk = surname_key(nome)
        full = norm(nome)
        sig = SIGLE.get(norm(squadra), norm(squadra)[:3]) if squadra else None
        cands = self.by_key.get((sk, sig), []) if sig else []
        if not cands:
            cands = [(m, f) for m, f, _ in self.by_surname.get(sk, [])]
        if len(cands) == 1:
            return cands[0][0]
        if len(cands) > 1:
            exact = [m for m, f in cands if f == full]
            if len(exact) == 1:
                return exact[0]
        return None


def main():
    season = sys.argv[1] if len(sys.argv) > 1 else "2026-27"
    reg = pd.read_csv(PROC / "registry.csv")
    reg = reg[reg.stagione == season]
    mt = Matcher(reg)
    pred = json.loads((PROC / f"b_predictions_{season}.json").read_text("utf-8"))
    inputs = MarketInputs()
    unmatched = []

    valid_ids = set(reg.master_id.astype(str))

    def attach(df: pd.DataFrame, nome_col="nome", sq_col="squadra") -> pd.DataFrame:
        """player_id fantacalcio.it (= master_id) quando c'e', altrimenti
        nome+squadra."""
        ids = []
        for r in df.itertuples(index=False):
            mid = None
            pid = getattr(r, "player_id", None)
            if pid is not None and pd.notna(pid) and str(int(float(pid))) in valid_ids:
                mid = str(int(float(pid)))
            if mid is None:
                mid = mt.match(getattr(r, nome_col), getattr(r, sq_col, None))
            if mid is None:
                unmatched.append((getattr(r, sq_col, ""), getattr(r, nome_col)))
            ids.append(mid)
        df = df.copy()
        df["master_id"] = ids
        return df[df.master_id.notna()]

    p = latest("probabili_2*.csv")   # esclude probabili_note_*
    if p:
        df = pd.read_csv(p)
        df = attach(df)
        if "giornata" in df.columns and df.giornata.notna().any():
            inputs.giornata_corrente = int(df.giornata.dropna().iloc[0])
        inputs.probabili = df[["master_id", "pct_titolarita"]].drop_duplicates("master_id")
        print(f"probabili: {p.name}, {len(inputs.probabili)} agganciati, giornata {inputs.giornata_corrente}")
    p = latest("indisponibili_*.csv")
    if p:
        df = attach(pd.read_csv(p))
        inputs.indisponibili = df
        print(f"indisponibili: {p.name}, {len(df)} agganciati")
    p = latest("rigoristi_*.csv")
    if p:
        df = pd.read_csv(p)
        col = "rigorista_1" if "rigorista_1" in df.columns else df.columns[1]
        d2 = attach(df.rename(columns={col: "nome"})[["squadra", "nome"]])
        inputs.rigoristi = set(d2.master_id.astype(str))
        print(f"rigoristi: {p.name}, {len(inputs.rigoristi)} agganciati")
    # prezzi live: gia' agganciati dal matching 0b (map_wayback, convenzione
    # "COGNOME Nome" gestita li'); si prende il file piu' recente della stagione
    mw_path = PROC / "_match" / "map_wayback.csv"
    if mw_path.exists():
        mw = pd.read_csv(mw_path)
        mw = mw[(mw.stagione == season) & mw.master_id.notna()]
        if len(mw):
            newest = sorted(mw.file.unique())[-1]
            mw = mw[mw.file == newest].copy()
            mw["master_id"] = mw.master_id.astype(int).astype(str)
            inputs.prezzi_live = mw[["master_id", "p500_10sq"]]
            print(f"prezzi live: {newest}, {mw.p500_10sq.notna().sum()} con prezzo")
    vp = PROC / f"votes_{season}.parquet"
    if vp.exists():
        v = pd.read_parquet(vp)
        v = v[v.sv.fillna(0) == 0] if "sv" in v.columns else v
        inputs.giornate_giocate = int(v.giornata.max()) if len(v) else 0
        inputs.presenze = v.groupby(v.master_id.astype(str)).size().to_dict()
        print(f"voti stagione: {inputs.giornate_giocate} giornate giocate")

    adj, log = adjust_predictions(pred, inputs)
    out = PROC / f"b_predictions_{season}_adj.json"
    out.write_text(json.dumps(adj, ensure_ascii=False), encoding="utf-8")
    names = dict(zip(reg.master_id.astype(str), reg.nome))
    log["nome"] = log.master_id.map(names)
    log.to_csv(PROC / f"market_adjust_{season}.csv", index=False, encoding="utf-8")
    changed = log[log.motivi.str.len() > 0]
    print(f"\n{len(adj)} predizioni, {len(changed)} toccate dal mercato -> {out.name}")
    print("Cali maggiori di valore:")
    top = log.assign(d=log.value_adj - log.value).nsmallest(10, "d")
    for r in top.itertuples(index=False):
        print(f"  {str(r.nome):22s} {r.value:6.0f} -> {r.value_adj:6.0f}  {r.motivi}")
    if unmatched:
        print(f"\nnon agganciati ({len(unmatched)}): {unmatched[:15]}")


if __name__ == "__main__":
    main()
