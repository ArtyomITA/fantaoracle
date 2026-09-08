"""Acquisizione del calendario di Serie A di una stagione, con verifiche.

Perche' serve: il cubo del Livello 2 genera una stagione partita per partita.
Senza il calendario della stagione in corso non puo' girare proprio dove
servirebbe per l'asta. Transfermarkt (`games.csv.gz` del dataset dcaribou) si
ferma alla stagione 2025 — il manutentore ha dichiarato gli aggiornamenti
sospesi da luglio 2026 (https://github.com/dcaribou/transfermarkt-datasets/discussions/383),
quindi per il 2026/27 serve una fonte diversa.

Fonte usata: `https://www.fantacalcio.it/serie-a/calendario/<giornata>`. E' la
stessa fonte gia' usata dal progetto per voti e quotazioni, quindi i nomi delle
squadre coincidono con quelli dei voti e non serve una nuova mappa. Il PDF
ufficiale della Lega (Allegato C.U. n.205) e' un'immagine senza testo estraibile:
va bene come riscontro visivo, non come fonte automatizzabile.

Che cosa conserva:
  data/raw/calendario/<stagione>/giornata_NN.html   pagina grezza (provenienza)
  data/raw/calendario/calendario_<stagione>.csv     tabella verificata
  data/raw/calendario/calendario_<stagione>.json    metadati acquisizione

Ogni riga distingue il momento dell'evento (`data`, `ora`) dal momento
dell'acquisizione (`acquisito_il`). Le partite non ancora giocate hanno
`provvisorio = 1`: data e orario possono cambiare fino alla designazione
televisiva, e vanno trattati come tali.

Verifiche eseguite (lo script termina con codice 1 se una fallisce):
  - 10 partite per giornata, 20 squadre distinte, nessuna squadra due volte;
  - ogni squadra gioca 38 partite, 19 in casa e 19 fuori;
  - ogni coppia di squadre si incontra due volte, una per campo;
  - le date crescono con la giornata (a meno dei recuperi, segnalati).

Uso:
  python scripts/l2_scarica_calendario.py 2026-27
  python scripts/l2_scarica_calendario.py 2026-27 --solo-verifica
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import time
import urllib.request
from collections import Counter
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
DEST = ROOT / "data" / "raw" / "calendario"
BASE = "https://www.fantacalcio.it/serie-a/calendario/{g}"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120.0 Safari/537.36")
GIORNATE = 38

SEPARATORE = 'itemscope itemtype="http://schema.org/SportsEvent"'
RE_STATO = re.compile(r'match-status-(\d+)')
RE_MATCHWEEK = re.compile(r'<div class="matchweek">\s*(\d+)', re.S)
RE_CASA = re.compile(r'itemprop="homeTeam".*?content="([^"]+)"', re.S)
RE_FUORI = re.compile(r'itemprop="awayTeam".*?content="([^"]+)"', re.S)
RE_DATA = re.compile(r'itemprop="startDate" content="([^"]+)"')
RE_ORA = re.compile(r'<span class="hours">\s*([0-9:]+)')
RE_STADIO = re.compile(r'<span class="stadium"[^>]*>([^<]*)</span>')
RE_GOL = re.compile(r'score-home">(\d+)</span>.*?score-away">(\d+)</span>', re.S)
RE_URL = re.compile(r'calendario/\d+/[^/]+/[a-z0-9-]+/(\d+)"')


def scarica(giornata: int, dove: Path) -> str:
    req = urllib.request.Request(BASE.format(g=giornata), headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=60) as r:
        html = r.read().decode("utf-8", "replace")
    dove.parent.mkdir(parents=True, exist_ok=True)
    dove.write_text(html, encoding="utf-8")
    return html


def analizza(html: str, giornata_attesa: int, acquisito: str) -> list[dict]:
    righe = []
    # ogni partita e' un blocco schema.org/SportsEvent; il primo pezzo dello
    # split e' l'intestazione della pagina e non contiene partite
    for blocco in html.split(SEPARATORE)[1:]:
        blocco = blocco[:4000]            # il blocco utile finisce ben prima
        gw = RE_MATCHWEEK.search(blocco)
        casa = RE_CASA.search(blocco)
        fuori = RE_FUORI.search(blocco)
        st = RE_STATO.search(blocco)
        if not (casa and fuori and st):
            continue
        if gw and int(gw.group(1)) != giornata_attesa:
            continue                      # widget di altre giornate nella pagina
        data = RE_DATA.search(blocco)
        ora = RE_ORA.search(blocco)
        stadio = RE_STADIO.search(blocco)
        gol = RE_GOL.search(blocco)
        stato = int(st.group(1))
        idp = RE_URL.search(blocco)
        righe.append({
            "giornata": giornata_attesa,
            "casa": casa.group(1).strip(),
            "trasferta": fuori.group(1).strip(),
            "data": data.group(1) if data else None,
            "ora": ora.group(1) if ora else None,
            "stadio": stadio.group(1).strip() if stadio else None,
            "stato_fonte": stato,
            "giocata": int(stato != 0),
            "provvisorio": int(stato == 0),
            "gol_casa": int(gol.group(1)) if (gol and stato != 0) else None,
            "gol_trasferta": int(gol.group(2)) if (gol and stato != 0) else None,
            "id_partita_fonte": idp.group(1) if idp else None,
            "fonte": "fantacalcio.it",
            "acquisito_il": acquisito,
        })
    return righe


def verifica(df: pd.DataFrame) -> list[str]:
    problemi = []
    squadre = sorted(set(df.casa) | set(df.trasferta))
    if len(squadre) != 20:
        problemi.append(f"squadre distinte {len(squadre)}, attese 20: {squadre}")
    if len(df) != GIORNATE * 10:
        problemi.append(f"partite {len(df)}, attese {GIORNATE * 10}")
    for g, sub in df.groupby("giornata"):
        if len(sub) != 10:
            problemi.append(f"giornata {g}: {len(sub)} partite, attese 10")
        coinvolte = list(sub.casa) + list(sub.trasferta)
        doppie = [s for s, n in Counter(coinvolte).items() if n > 1]
        if doppie:
            problemi.append(f"giornata {g}: squadra ripetuta {doppie}")
    for s in squadre:
        casa = int((df.casa == s).sum())
        fuori = int((df.trasferta == s).sum())
        if casa + fuori != GIORNATE:
            problemi.append(f"{s}: {casa + fuori} partite, attese {GIORNATE}")
        if casa != GIORNATE // 2 or fuori != GIORNATE // 2:
            problemi.append(f"{s}: {casa} in casa e {fuori} fuori, attese 19 e 19")
    incontri = Counter(tuple(sorted(x)) for x in zip(df.casa, df.trasferta))
    for coppia, n in incontri.items():
        if n != 2:
            problemi.append(f"{coppia[0]}-{coppia[1]}: {n} incontri, attesi 2")
    ordinati = Counter(zip(df.casa, df.trasferta))
    for coppia, n in ordinati.items():
        if n != 1:
            problemi.append(f"{coppia[0]} in casa contro {coppia[1]} {n} volte, atteso 1")
    d = df.dropna(subset=["data"]).copy()
    d["data"] = pd.to_datetime(d["data"], errors="coerce")
    per_g = d.groupby("giornata")["data"].min()
    fuori_ordine = [int(g) for g in per_g.index[1:]
                    if per_g[g] < per_g[per_g.index[list(per_g.index).index(g) - 1]]]
    if fuori_ordine:
        problemi.append(f"giornate con data anteriore alla precedente (recuperi?): "
                        f"{fuori_ordine}")
    return problemi


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("stagione", nargs="?", default="2026-27")
    ap.add_argument("--solo-verifica", action="store_true",
                    help="non riscarica: rilegge le pagine gia' salvate")
    a = ap.parse_args()

    cartella = DEST / a.stagione
    acquisito = time.strftime("%Y-%m-%dT%H:%M:%S")
    righe, impronte = [], {}
    for g in range(1, GIORNATE + 1):
        f = cartella / f"giornata_{g:02d}.html"
        if a.solo_verifica:
            if not f.exists():
                print(f"giornata {g}: pagina assente, salto", file=sys.stderr)
                continue
            html = f.read_text(encoding="utf-8")
        else:
            html = scarica(g, f)
            time.sleep(0.4)
        impronte[f.name] = hashlib.sha256(html.encode("utf-8")).hexdigest()
        r = analizza(html, g, acquisito)
        if len(r) != 10:
            print(f"ATTENZIONE giornata {g}: estratte {len(r)} partite", file=sys.stderr)
        righe.extend(r)
        print(f"giornata {g:2d}: {len(r)} partite")

    df = pd.DataFrame(righe)
    # la pagina della giornata in corso mostra le stesse partite due volte
    # (widget "giornata corrente" in testa + elenco): tengo la riga piu' ricca
    df["_info"] = df[["data", "ora", "stadio", "gol_casa"]].notna().sum(axis=1)
    prima = len(df)
    df = (df.sort_values("_info", ascending=False)
            .drop_duplicates(["giornata", "casa", "trasferta"])
            .drop(columns="_info"))
    if prima != len(df):
        print(f"rimosse {prima - len(df)} righe duplicate (widget della giornata corrente)")
    df = df.sort_values(["giornata", "data", "ora"]).reset_index(drop=True)
    problemi = verifica(df)
    out = DEST / f"calendario_{a.stagione}.csv"
    df.to_csv(out, index=False, encoding="utf-8")
    meta = {
        "stagione": a.stagione,
        "fonte": "fantacalcio.it/serie-a/calendario",
        "acquisito_il": acquisito,
        "n_partite": len(df),
        "n_giocate": int(df.giocata.sum()),
        "n_provvisorie": int(df.provvisorio.sum()),
        "squadre": sorted(set(df.casa) | set(df.trasferta)),
        "impronte_pagine": impronte,
        "problemi": problemi,
        "nota": ("le partite con provvisorio=1 non sono ancora state giocate: "
                 "data e orario possono cambiare. Il riscontro visivo e' il PDF "
                 "ufficiale della Lega, Allegato C.U. n.205."),
    }
    (DEST / f"calendario_{a.stagione}.json").write_text(
        json.dumps(meta, indent=1, ensure_ascii=False), encoding="utf-8")

    print(f"\n{len(df)} partite, {int(df.giocata.sum())} giocate, "
          f"{int(df.provvisorio.sum())} ancora da giocare -> {out.name}")
    if problemi:
        print(f"\n{len(problemi)} PROBLEMI:")
        for p in problemi[:30]:
            print(f"  {p}")
        return 1
    print("verifiche superate: 10 partite per giornata, 20 squadre, "
          "19 in casa e 19 fuori per squadra, ogni coppia due volte")
    return 0


if __name__ == "__main__":
    sys.exit(main())
