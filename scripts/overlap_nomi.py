# -*- coding: utf-8 -*-
"""Test overlap nomi 2024/25 tra le 4 fonti chiave (per pianificare il name
matching di Fase 0b). Normalizzazione: uppercase, strip accenti (NFKD),
punteggiatura -> spazio, spazi collassati. Match ESATTO sulla stringa
normalizzata; per i non matchati si mostra un candidato che condivide un
token (>=4 char) per capire la regola di matching necessaria."""
import io
import re
import unicodedata
from collections import defaultdict

import pandas as pd

RAW = r"data\raw"
OUT = RAW + r"\_overlap_section.md"

GE_2024_FILES = {
    "gruppoesperti_prezzi_aste_reali_2024-25.xlsx",
    "extra/1Uxv42LC7d68Y1ZLQ48Hh1ud74kJocO-lTom39eJFB_w.xlsx",
    "extra/1J4tILPqyErS5Ccpr0Dy-595D2PgubYxlPaqfX8-pjYw.xlsx",
}


def norm(name):
    if not isinstance(name, str):
        return ""
    s = unicodedata.normalize("NFKD", name)
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = s.upper()
    s = re.sub(r"[^A-Z0-9 ]", " ", s)   # punteggiatura/apostrofi -> spazio
    s = re.sub(r"\s+", " ", s).strip()
    return s


def load_sources():
    src = {}

    ge = pd.read_csv(RAW + r"\gruppoesperti\aste_reali_tidy.csv",
                     dtype=str, keep_default_na=False)
    ge24 = ge[ge["source_file"].isin(GE_2024_FILES)]
    src["gruppoesperti (aste 2024/25)"] = set(filter(None, (norm(x) for x in ge24["player_raw"])))

    wb = pd.concat([
        pd.read_csv(RAW + r"\wayback_prices\prezzi_2024-25_20250214053906.csv",
                    dtype=str, keep_default_na=False),
        pd.read_csv(RAW + r"\wayback_prices\prezzi_2024-25_20250616102603.csv",
                    dtype=str, keep_default_na=False),
    ])
    src["wayback prezzi 2024/25"] = set(filter(None, (norm(x) for x in wb["nome"])))

    vt = pd.read_csv(RAW + r"\voti\voti_2024-25.csv", dtype=str, keep_default_na=False)
    src["voti fantacalcio.it 2024/25"] = set(filter(None, (norm(x) for x in vt["nome"])))

    us = pd.read_csv(RAW + r"\understat\understat_players_2024.csv",
                     dtype=str, keep_default_na=False)
    src["understat 2024/25"] = set(filter(None, (norm(x) for x in us["player_name"])))
    return src


def token_index(names):
    idx = defaultdict(list)
    for n in names:
        for t in n.split():
            if len(t) >= 4:
                idx[t].append(n)
    return idx


def candidate(name, idx):
    # candidato in B che condivide il token piu' lungo (>=4 char) di name
    for t in sorted(name.split(), key=len, reverse=True):
        if len(t) >= 4 and t in idx:
            return idx[t][0]
    return None


def main():
    src = load_sources()
    out = io.StringIO()
    out.write("\nNormalizzazione applicata: uppercase, rimozione accenti (NFKD), "
              "punteggiatura sostituita da spazio, spazi collassati. "
              "Match = uguaglianza esatta della stringa normalizzata.\n\n")
    out.write("| Fonte | nomi unici (norm.) | esempio formato |\n|---|---|---|\n")
    for k, v in src.items():
        ex = sorted(v)[50] if len(v) > 50 else next(iter(v))
        out.write(f"| {k} | {len(v)} | `{ex}` |\n")

    names = list(src.keys())
    out.write("\n### Matrice match esatto (percentuale della fonte di riga trovata nella fonte di colonna)\n\n")
    out.write("| | " + " | ".join(names) + " |\n")
    out.write("|---" * (len(names) + 1) + "|\n")
    for a in names:
        row = [f"**{a}**"]
        for b in names:
            if a == b:
                row.append("—")
            else:
                inter = len(src[a] & src[b])
                row.append(f"{inter} ({inter/len(src[a])*100:.1f}%)")
        out.write("| " + " | ".join(row) + " |\n")

    out.write("\n### Esempi di nomi NON matchati (con candidato omonimo per token, per capire la regola necessaria)\n")
    pairs = [(a, b) for i, a in enumerate(names) for b in names[i + 1:]]
    for a, b in pairs:
        only_a = sorted(src[a] - src[b])
        only_b = sorted(src[b] - src[a])
        idx_b = token_index(src[b])
        idx_a = token_index(src[a])
        out.write(f"\n**{a}  vs  {b}** — non matchati: {len(only_a)} da sx, {len(only_b)} da dx\n\n")
        out.write(f"| solo in \"{a}\" | candidato in \"{b}\" | solo in \"{b}\" | candidato in \"{a}\" |\n|---|---|---|---|\n")
        import random
        random.seed(42)
        sa = random.sample(only_a, min(15, len(only_a)))
        sb = random.sample(only_b, min(15, len(only_b)))
        for i in range(max(len(sa), len(sb))):
            ca = candidate(sa[i], idx_b) if i < len(sa) else ""
            cb = candidate(sb[i], idx_a) if i < len(sb) else ""
            out.write("| " + " | ".join([
                sa[i] if i < len(sa) else "",
                ca or ("(nessun token comune)" if i < len(sa) else ""),
                sb[i] if i < len(sb) else "",
                cb or ("(nessun token comune)" if i < len(sb) else ""),
            ]) + " |\n")

    with open(OUT, "w", encoding="utf-8") as fh:
        fh.write(out.getvalue())
    print("OK ->", OUT)
    for k, v in src.items():
        print(f"  {k}: {len(v)} nomi unici")


if __name__ == "__main__":
    main()
