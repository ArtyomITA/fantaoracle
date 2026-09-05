# -*- coding: utf-8 -*-
"""Rose Transfermarkt Serie A 2026/27 (pagina kader 'dettaglio', plus/1).

Per ogni club: tm_player_id, nome completo, ruolo TM, data di nascita, eta',
nazionalita', valore di mercato (EUR), club precedente, prestito, squadra (sigla
registry). Nessun login, 1 richiesta ogni 3-4 s, retry con backoff.

Output: data/raw/transfermarkt/kader_2026.csv
Cache HTML: data/raw/transfermarkt/_download/kader_2026/{sigla}.html
            (riusata se presente; --refresh per riscaricare)

Uso: python scripts/scrape_tm_kader.py [--refresh]
"""
from __future__ import annotations

import random
import re
import sys
import time
from pathlib import Path

import pandas as pd
import requests
from bs4 import BeautifulSoup

sys.path.insert(0, str(Path(__file__).parent))
from f0b_lib import PROC, RAW, norm  # noqa: E402

SEASON_ID = 2026
STAGIONE = "2026-27"
BASE = "https://www.transfermarkt.it"
LEAGUE_URL = f"{BASE}/serie-a/startseite/wettbewerb/IT1/saison_id/{SEASON_ID}"
OUT = RAW / "transfermarkt" / f"kader_{SEASON_ID}.csv"
CACHE = RAW / "transfermarkt" / "_download" / f"kader_{SEASON_ID}"
HEADERS = {
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                   "(KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "it-IT,it;q=0.9,en;q=0.8",
}
SLEEP = (3.0, 4.0)

# token del nome club TM (normalizzato) -> sigla listone fantacalcio.it
CLUB_TOKEN_TO_SIGLA = {
    "ATALANTA": "ATA", "BOLOGNA": "BOL", "CAGLIARI": "CAG", "COMO": "COM",
    "CREMONESE": "CRE", "EMPOLI": "EMP", "FIORENTINA": "FIO", "FLORENZ": "FIO",
    "FROSINONE": "FRO", "GENOA": "GEN", "GENUA": "GEN", "INTER": "INT",
    "JUVENTUS": "JUV", "LAZIO": "LAZ", "LECCE": "LEC", "MILAN": "MIL",
    "MAILAND": "MIL", "MONZA": "MON", "NAPOLI": "NAP", "NEAPEL": "NAP",
    "PARMA": "PAR", "PISA": "PIS", "ROMA": "ROM", "SALERNITANA": "SAL",
    "SAMPDORIA": "SAM", "SASSUOLO": "SAS", "SPEZIA": "SPE", "TORINO": "TOR",
    "TURIN": "TOR", "UDINESE": "UDI", "VENEZIA": "VEN", "VERONA": "VER",
}
# id club TM (stabili) -> sigla: fallback se il nome non e' riconosciuto
CLUB_ID_TO_SIGLA = {
    800: "ATA", 1025: "BOL", 1390: "CAG", 1047: "COM", 2919: "MON", 430: "FIO",
    8970: "FRO", 252: "GEN", 46: "INT", 506: "JUV", 398: "LAZ", 1005: "LEC",
    5: "MIL", 6195: "NAP", 130: "PAR", 12: "ROM", 6574: "SAS", 416: "TOR",
    410: "UDI", 607: "VEN", 276: "VER", 4171: "PIS", 2931: "CRE", 749: "EMP",
}

# ruolo TM (italiano) -> ruolo fantacalcio grossolano (token match)
ROLE_TOKENS = [
    ("P", {"PORTIERE"}),
    ("D", {"DIFENSORE", "TERZINO", "LIBERO", "DIFESA"}),
    ("C", {"CENTROCAMPISTA", "MEDIANO", "TREQUARTISTA", "ESTERNO", "CENTROCAMPO",
           "REGISTA"}),
    ("A", {"ALA", "ATTACCANTE", "PUNTA", "ATTACCO"}),
]


def role_tm_to_fanta(role_tm: str) -> str:
    toks = set(norm(role_tm).split())
    for r, keys in ROLE_TOKENS:
        if toks & keys:
            return r
    return ""


def club_sigla(name: str, club_id: int) -> str:
    toks = norm(name).split()
    hits = {CLUB_TOKEN_TO_SIGLA[t] for t in toks if t in CLUB_TOKEN_TO_SIGLA}
    if len(hits) == 1:
        return hits.pop()
    return CLUB_ID_TO_SIGLA.get(club_id, "")


def parse_value(txt: str):
    """'8,00 mln €' -> 8e6; '400 mila €' -> 4e5; '-' -> NaN."""
    t = norm(txt)
    m = re.search(r"(\d+(?: \d{1,2})?)\s*(MLN|MILA|MLD)?", t.replace(",", " "))
    if not m or not re.search(r"\d", t):
        return float("nan")
    num = float(m.group(1).replace(" ", "."))
    mult = {"MLN": 1e6, "MILA": 1e3, "MLD": 1e9}.get(m.group(2) or "", 1.0)
    return num * mult


def parse_dob(txt: str):
    """'25/02/2002 (24)' -> ('2002-02-25', 24)."""
    m = re.search(r"(\d{2})/(\d{2})/(\d{4})", txt or "")
    a = re.search(r"\((\d+)\)", txt or "")
    dob = f"{m.group(3)}-{m.group(2)}-{m.group(1)}" if m else ""
    return dob, (int(a.group(1)) if a else None)


def parse_height(txt: str):
    m = re.search(r"(\d)[,.](\d{2})\s*m", txt or "")
    return int(m.group(1)) * 100 + int(m.group(2)) if m else None


# ------------------------------------------------------------------ http
def fetch(session: requests.Session, url: str, tries: int = 4) -> str:
    last = None
    for i in range(tries):
        try:
            r = session.get(url, headers=HEADERS, timeout=40)
            if r.status_code == 200 and "table" in r.text:
                return r.text
            last = f"http {r.status_code}"
        except requests.RequestException as e:  # noqa: PERF203
            last = repr(e)
        wait = 6 * (i + 1) + random.uniform(0, 3)
        print(f"  retry {i+1}/{tries} ({last}) tra {wait:.0f}s: {url}")
        time.sleep(wait)
    raise RuntimeError(f"download fallito: {url} ({last})")


def polite_sleep():
    time.sleep(random.uniform(*SLEEP))


# ------------------------------------------------------------------ parser
def league_clubs(html: str) -> list[dict]:
    """[{club_id, slug, name}] dei club della pagina lega (ordine tabella)."""
    soup = BeautifulSoup(html, "html.parser")
    seen: dict[int, dict] = {}
    for a in soup.select("a[href*='/startseite/verein/']"):
        href = a.get("href", "")
        m = re.match(r"^/([^/]+)/startseite/verein/(\d+)(?:/saison_id/(\d+))?", href)
        if not m or (m.group(3) and int(m.group(3)) != SEASON_ID):
            continue
        cid = int(m.group(2))
        name = (a.get("title") or a.get_text(" ", strip=True) or "").strip()
        if cid not in seen or (name and not seen[cid]["name"]):
            seen[cid] = dict(club_id=cid, slug=m.group(1), name=name)
    return list(seen.values())


def parse_kader(html: str, sigla: str, club_id: int, club_name: str) -> list[dict]:
    soup = BeautifulSoup(html, "html.parser")
    table = soup.select_one("table.items")
    if table is None:
        raise RuntimeError(f"{sigla}: table.items non trovata")
    heads = [norm(th.get_text(" ", strip=True)) for th in table.select("thead th")]

    def col(*keys):
        for i, h in enumerate(heads):
            if any(k in h for k in keys):
                return i
        return None

    c_num, c_pl, c_dob = col("#"), col("GIOCATORI"), col("NATO")
    c_naz, c_h, c_foot = col("NAZ"), col("ALTEZZA"), col("PIEDE")
    c_since, c_prev, c_contr, c_val = col("IN ROSA"), col("PRECEDENTE"), col("CONTRATTO"), col("VALORE")
    rows = []
    for tr in table.select("tbody > tr"):
        tds = tr.find_all("td", recursive=False)
        if len(tds) != len(heads) or c_pl is None:
            continue
        cell = tds[c_pl]
        prof = cell.select_one("a[href*='/profil/spieler/']")
        if prof is None:
            continue
        pid = int(re.search(r"/profil/spieler/(\d+)", prof["href"]).group(1))
        nome = prof.get_text(" ", strip=True)
        inl = cell.select("table.inline-table tr")
        role_tm = inl[1].get_text(" ", strip=True) if len(inl) > 1 else ""
        # icona movimento nella cella giocatore: title tipo
        # 'Acquisto da: Hellas Verona; Data: 19/08/2026; Costo: 250 mila €'
        movimento, da_club = "", ""
        for a in cell.select("a[href*='/startseite/verein/']"):
            t = (a.get("title") or "").strip()
            if t:
                movimento = t
                mm = re.search(r"da:\s*([^;]+)", t, flags=re.I)
                da_club = mm.group(1).strip() if mm else ""
                break
        dob, eta_tm = parse_dob(tds[c_dob].get_text(" ", strip=True) if c_dob is not None else "")
        naz = "/".join(i.get("title", "") for i in tds[c_naz].select("img")) if c_naz is not None else ""
        prev_club, prev_id = "", None
        if c_prev is not None:
            img = tds[c_prev].select_one("img")
            a = tds[c_prev].select_one("a[href*='/verein/']")
            # img alt = nome club pulito (title contiene 'Club: Ablöse 3,80 mln €')
            prev_club = (img.get("alt") if img is not None else "") or ""
            if not prev_club and a is not None:
                prev_club = (a.get("title") or "").split(":")[0].strip()
            prev_club = prev_club or tds[c_prev].get_text(" ", strip=True)
            if a is not None:
                mm = re.search(r"/verein/(\d+)", a["href"])
                prev_id = int(mm.group(1)) if mm else None
        rows.append(dict(
            squadra=sigla, tm_club_id=club_id, tm_club_name=club_name,
            tm_player_id=pid, nome_completo=nome, ruolo_tm=role_tm,
            ruolo=role_tm_to_fanta(role_tm), date_of_birth=dob, eta_tm=eta_tm,
            nazionalita=naz,
            market_value_eur=parse_value(tds[c_val].get_text(" ", strip=True)) if c_val is not None else float("nan"),
            club_precedente=prev_club, club_precedente_id=prev_id,
            da_club=da_club, movimento_tm=movimento,
            numero=tds[c_num].get_text(" ", strip=True) if c_num is not None else "",
            altezza_cm=parse_height(tds[c_h].get_text(" ", strip=True)) if c_h is not None else None,
            piede=tds[c_foot].get_text(" ", strip=True) if c_foot is not None else "",
            in_rosa_da=tds[c_since].get_text(" ", strip=True) if c_since is not None else "",
            contratto=tds[c_contr].get_text(" ", strip=True) if c_contr is not None else "",
        ))
    return rows


# ------------------------------------------------------------------ main
def main():
    refresh = "--refresh" in sys.argv
    CACHE.mkdir(parents=True, exist_ok=True)
    reg = pd.read_csv(PROC / "registry.csv")
    sigle_reg = set(reg.loc[reg.stagione == STAGIONE, "squadra"].unique())

    s = requests.Session()
    lp = CACHE / "_league.html"
    if lp.exists() and not refresh:
        html = lp.read_text(encoding="utf-8")
    else:
        html = fetch(s, LEAGUE_URL)
        lp.write_text(html, encoding="utf-8")
        polite_sleep()
    clubs = league_clubs(html)
    for c in clubs:
        c["sigla"] = club_sigla(c["name"], c["club_id"])
    unknown = [c for c in clubs if not c["sigla"]]
    if unknown:
        raise SystemExit(f"club TM senza sigla: {unknown}")
    sigle_tm = {c["sigla"] for c in clubs}
    if sigle_tm != sigle_reg:
        raise SystemExit(f"sigle TM {sorted(sigle_tm)} != registry {STAGIONE} {sorted(sigle_reg)}")
    print(f"{len(clubs)} club Serie A {SEASON_ID}: " + ", ".join(
        f"{c['sigla']}={c['club_id']}" for c in sorted(clubs, key=lambda c: c['sigla'])))

    rows = []
    for c in sorted(clubs, key=lambda c: c["sigla"]):
        url = f"{BASE}/{c['slug']}/kader/verein/{c['club_id']}/saison_id/{SEASON_ID}/plus/1"
        p = CACHE / f"{c['sigla']}.html"
        if p.exists() and not refresh:
            html = p.read_text(encoding="utf-8")
        else:
            html = fetch(s, url)
            p.write_text(html, encoding="utf-8")
            polite_sleep()
        r = parse_kader(html, c["sigla"], c["club_id"], c["name"])
        print(f"  {c['sigla']:4s} {c['name']:28s} {len(r):3d} giocatori")
        rows.extend(r)

    df = pd.DataFrame(rows)
    dup = df.tm_player_id.duplicated(keep=False)
    if dup.any():
        print(f"attenzione: {dup.sum()} righe con tm_player_id duplicato (prestiti?)")
    df.to_csv(OUT, index=False, encoding="utf-8")
    print(f"{OUT.name}: {len(df)} righe | dob nota {df.date_of_birth.ne('').sum()} | "
          f"valore noto {df.market_value_eur.notna().sum()} | ruolo mappato "
          f"{df.ruolo.ne('').sum()} | ruoli TM: {sorted(df.ruolo_tm.unique())}")


if __name__ == "__main__":
    main()
