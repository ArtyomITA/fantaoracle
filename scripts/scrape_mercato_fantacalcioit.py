# -*- coding: utf-8 -*-
"""
Scraper "mercato" da fantacalcio.it (HTML anonimo, nessun login):

  a) probabili formazioni  https://www.fantacalcio.it/probabili-formazioni-serie-a
     -> probabili_{tag}.csv      (giornata, squadra, avversario, casa, nome, ruolo, pct_titolarita,
                                  stato, lista, ballottaggio_con, pct_ballottaggio, player_id)
     -> probabili_note_{tag}.csv (giornata, squadra, tipo, nome, dettaglio, player_id)
  b) indisponibili         https://www.fantacalcio.it/indisponibili-serie-a
     -> indisponibili_{tag}.csv  (squadra, nome, tipo, dettaglio, rientro_atteso, rientro_stima)
  c) rigoristi             https://www.fantacalcio.it/rigoristi-serie-a
     -> rigoristi_{tag}.csv      (squadra, rigorista_1..3, punizioni_1..3)

Struttura HTML (verificata 01/09/2026):
  probabili   : li.match-item > .matchweek (giornata), label.team-home/away a.team-name,
                div.team-card (home, away) > ul.player-list.starters|reserves > li.player-item
                  [span.role[data-value=p|d|c|a], a.player-name span, div.progress-value "90%"]
                section.ballots|suspendeds|cautioneds|injureds|dubts > div.content (0=home, 1=away)
                  ballots: div.ballot ul.ballot-list li [a.player-name, strong.percentage]
                  altri  : ul li [a.player-name span, p.description]
  indisponibili: div.card.team-card#team-N > header.team-info .team-name;
                div.col > header (Infortunati|Squalificati|Diffidati) seguito da
                ul.unstyled li [strong.item-name, div.item-description p] o .empty-list-message
  rigoristi   : div.card.team-card > div.col > header (Rigori|Calci piazzati) + ol.pill-list li

Convenzione nomi: fantacalcio.it usa "Cognome" oppure "Cognome I." (iniziale del nome per
omonimi, es. "Vitinha O.", "Paz N.", "Chalobah T.") -- identica ai CSV voti_*.csv dello stesso
sito; `player_id` (dall'URL del giocatore) e' la chiave stabile per il matching.
Ruolo in minuscolo (p/d/c/a) come nei voti.
"""
from __future__ import annotations

import csv
import random
import re
import time
from datetime import date, timedelta
from pathlib import Path

import requests
from bs4 import BeautifulSoup, Tag

URL_PROBABILI = "https://www.fantacalcio.it/probabili-formazioni-serie-a"
URL_INDISPONIBILI = "https://www.fantacalcio.it/indisponibili-serie-a"
URL_RIGORISTI = "https://www.fantacalcio.it/rigoristi-serie-a"
DEFAULT_OUT_DIR = Path(r"data\raw\mercato")

HEADERS = {
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                   "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"),
    "Accept-Language": "it-IT,it;q=0.9,en;q=0.8",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}

COLS_PROBABILI = ["giornata", "squadra", "avversario", "casa", "nome", "ruolo", "pct_titolarita",
                  "stato", "lista", "ballottaggio_con", "pct_ballottaggio", "player_id"]
COLS_NOTE = ["giornata", "squadra", "tipo", "nome", "dettaglio", "player_id"]
COLS_INDISP = ["squadra", "nome", "tipo", "dettaglio", "rientro_atteso", "rientro_stima"]
COLS_RIGORISTI = ["squadra", "rigorista_1", "rigorista_2", "rigorista_3",
                  "punizioni_1", "punizioni_2", "punizioni_3"]

SEZIONI_NOTE = {"suspendeds": "squalificato", "cautioneds": "diffidato",
                "injureds": "infortunato", "dubts": "in_dubbio"}
TIPO_INDISP = {"infortunati": "infortunio", "squalificati": "squalifica", "diffidati": "diffida"}

MESI = {"gennaio": 1, "febbraio": 2, "marzo": 3, "aprile": 4, "maggio": 5, "giugno": 6,
        "luglio": 7, "agosto": 8, "settembre": 9, "ottobre": 10, "novembre": 11, "dicembre": 12}
NUMERI = {"un": 1, "una": 1, "uno": 1, "due": 2, "tre": 3, "quattro": 4, "cinque": 5, "sei": 6}
RE_MESE = "|".join(MESI)
RE_PLAYER_ID = re.compile(r"/squadre/[^/]+/[^/]+/(\d+)")


# --------------------------------------------------------------------------- HTTP
def fetch_html(url: str, max_retries: int = 5, timeout: int = 45) -> str:
    """Scarica una pagina con pausa 1-3 s e retry esponenziale su 429/503."""
    for attempt in range(1, max_retries + 1):
        time.sleep(random.uniform(1.0, 3.0))
        try:
            r = requests.get(url, headers=HEADERS, timeout=timeout)
        except requests.RequestException as exc:
            if attempt == max_retries:
                raise
            print(f"  [retry {attempt}] errore rete: {exc}")
            time.sleep(5 * attempt)
            continue
        if r.status_code in (429, 503):
            wait = 10 * attempt
            print(f"  [retry {attempt}] HTTP {r.status_code}, attendo {wait}s")
            time.sleep(wait)
            continue
        r.raise_for_status()
        return r.text
    raise RuntimeError(f"troppi tentativi falliti per {url}")


# --------------------------------------------------------------------------- helper
def _txt(el: Tag | None) -> str:
    """Testo normalizzato di un elemento (stringa vuota se None)."""
    return re.sub(r"\s+", " ", el.get_text(" ", strip=True)) if el else ""


def _player(el: Tag | None) -> tuple[str, str]:
    """(nome, player_id) da un a.player-name; player_id dall'URL /squadre/<team>/<slug>/<id>."""
    if el is None:
        return "", ""
    m = RE_PLAYER_ID.search(el.get("href", ""))
    return _txt(el), (m.group(1) if m else "")


def _pct(txt: str) -> str:
    """'90%' -> '90'; vuoto se non numerico."""
    m = re.search(r"\d+(?:[.,]\d+)?", txt or "")
    return m.group(0).replace(",", ".") if m else ""


def _write_csv(path: Path, cols: list[str], rows: list[dict]) -> Path:
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)
    print(f"scritto {path} ({len(rows)} righe)")
    return path


def giornata_corrente(soup: BeautifulSoup) -> str:
    """Numero della giornata dal widget 'Prossimo turno' o dal primo match-pill."""
    el = soup.select_one(".match-pill div.matchweek")
    return _txt(el)


# --------------------------------------------------------------------------- a) probabili
def parse_probabili(html: str) -> tuple[list[dict], list[dict]]:
    """Ritorna (righe giocatori, righe note) dalla pagina probabili formazioni."""
    soup = BeautifulSoup(html, "lxml")
    rows: list[dict] = []
    note: list[dict] = []

    for match in soup.select("li.match-item"):
        giornata = _txt(match.select_one(".matchweek"))
        teams = [_txt(match.select_one("label.team-home a.team-name")),
                 _txt(match.select_one("label.team-away a.team-name"))]

        # ballottaggi: div.content[0] = casa, [1] = ospite; nome -> (altri nomi, pct)
        ballots: list[dict[str, tuple[str, str]]] = [{}, {}]
        sec = match.select_one("section.ballots")
        contents = sec.find_all("div", class_="content", recursive=False) if sec else []
        for idx, content in enumerate(contents[:2]):
            for ballot in content.select("div.ballot"):
                items = [(_player(li.select_one("a.player-name"))[0], _pct(_txt(li.select_one(".percentage"))))
                         for li in ballot.select("ul.ballot-list li")]
                for nome, pct in items:
                    others = " | ".join(n for n, _ in items if n != nome)
                    ballots[idx][nome] = (others, pct)

        cards = match.select("div.team-card")
        for idx, card in enumerate(cards[:2]):
            squadra = _txt(card.select_one(".team-name")) or teams[idx]
            avversario = teams[1 - idx] if idx < 2 else ""
            visti: set[str] = set()
            for lista, sel in (("titolari", "ul.player-list.starters"),
                               ("panchina", "ul.player-list.reserves")):
                ul = card.select_one(sel)
                for li in (ul.select("li.player-item") if ul else []):
                    nome, pid = _player(li.select_one("a.player-name"))
                    if not nome:
                        continue
                    visti.add(nome)
                    role = li.select_one("span.role")
                    ball = ballots[idx].get(nome)
                    rows.append({
                        "giornata": giornata, "squadra": squadra, "avversario": avversario,
                        "casa": 1 if idx == 0 else 0, "nome": nome,
                        "ruolo": (role.get("data-value") if role else "") or "",
                        "pct_titolarita": _pct(_txt(li.select_one(".progress-value"))),
                        "stato": "ballottaggio" if ball else ("titolare" if lista == "titolari" else "panchina"),
                        "lista": lista,
                        "ballottaggio_con": ball[0] if ball else "",
                        "pct_ballottaggio": ball[1] if ball else "",
                        "player_id": pid,
                    })
            # giocatori citati solo nei ballottaggi (non in titolari/panchina)
            for nome, (others, pct) in ballots[idx].items():
                if nome not in visti:
                    rows.append({"giornata": giornata, "squadra": squadra, "avversario": avversario,
                                 "casa": 1 if idx == 0 else 0, "nome": nome, "ruolo": "",
                                 "pct_titolarita": "", "stato": "ballottaggio", "lista": "",
                                 "ballottaggio_con": others, "pct_ballottaggio": pct, "player_id": ""})

        # note: squalificati / diffidati / infortunati / in dubbio, div.content[0]=casa [1]=ospite
        for cls, tipo in SEZIONI_NOTE.items():
            sec = match.select_one(f"section.{cls}")
            if not sec:
                continue
            for idx, content in enumerate(sec.find_all("div", class_="content", recursive=False)[:2]):
                for li in content.select("ul li"):
                    nome, pid = _player(li.select_one("a.player-name"))
                    if not nome:
                        nome = _txt(li.select_one("strong, span"))
                    if not nome:
                        continue
                    note.append({"giornata": giornata, "squadra": teams[idx], "tipo": tipo,
                                 "nome": nome, "dettaglio": _txt(li.select_one("p.description, .description")),
                                 "player_id": pid})
    return rows, note


# --------------------------------------------------------------------------- b) indisponibili
def stima_rientro(dettaglio: str, giornata: str, oggi: date | None = None) -> tuple[str, str]:
    """
    Euristica sul testo redazionale: ritorna (frase_rientro, stima).
    stima: 'YYYY-MM-DD' (data esplicita o inizio/meta'/fine mese -> 5/15/25), 'YYYY-MM' (solo mese),
           'G<n>' (giornata di campionato), '' se non deducibile.
    """
    oggi = oggi or date.today()
    d = dettaglio.strip()
    if not d:
        return "", ""
    frasi = [f.strip() for f in re.split(r"(?<=[.;!?])\s+", d) if f.strip()]
    kw_clause = re.compile(r"rientr|recuper|riaver|disposizion|torn|ritorno|rived|arruolab|salter|"
                           r"assent|out\b|fuori|giornat|turno|mes[ei]\b|settiman|squalific", re.I)
    clause = next((f for f in frasi if kw_clause.search(f)), frasi[-1])
    low = clause.lower()
    gcur = int(giornata) if giornata.isdigit() else None

    def anno(mese: int) -> int:
        # stagione: mesi 7-12 anno corrente, 1-6 anno successivo (o corrente se siamo gia' oltre)
        return oggi.year if mese >= 7 or oggi.month <= 6 else oggi.year + 1

    # le date/mesi valgono come rientro solo se compaiono DOPO una parola chiave di rientro
    # (altrimenti sono la data dell'infortunio: "KO l'8 agosto", "operato a fine giugno")
    kw_rientro = re.search(r"rientr|recuper|riaver|disposizion|torn|ritorno|rived|arruolab|"
                           r"fino a|entro|salter|out\b|fuori", low)
    tail = low[kw_rientro.start():] if kw_rientro else ""

    m = re.search(rf"\b(\d{{1,2}})\s+({RE_MESE})\b", tail)
    if m:
        mese = MESI[m.group(2)]
        return clause, f"{anno(mese)}-{mese:02d}-{int(m.group(1)):02d}"
    m = re.search(rf"(inizio|prima met[aà]'?|met[aà]'?|seconda met[aà]'?|fine)\s+(?:di\s+)?({RE_MESE})\b", tail)
    if m:
        giorno = {"inizio": 5, "prima met": 8, "met": 15, "seconda met": 20, "fine": 25}
        key = next(k for k in ("seconda met", "prima met", "inizio", "fine", "met") if m.group(1).startswith(k))
        mese = MESI[m.group(2)]
        return clause, f"{anno(mese)}-{mese:02d}-{giorno[key]:02d}"
    m = re.search(rf"\b({RE_MESE})\b", tail)
    if m:
        mese = MESI[m.group(1)]
        return clause, f"{anno(mese)}-{mese:02d}"
    m = re.search(r"(\d+|un[ao]?|due|tre|quattro|cinque|sei)\s+(settiman|mes)[ei]", tail)
    if m:
        n = int(m.group(1)) if m.group(1).isdigit() else NUMERI[m.group(1)]
        delta = timedelta(weeks=n) if m.group(2) == "settiman" else timedelta(days=30 * n)
        return clause, (oggi + delta).isoformat()
    m = re.search(r"(\d+)\s*[aª°^]\s*(?:giornata|di campionato)|giornata\s+(\d+)", low)
    if m:
        return clause, f"G{m.group(1) or m.group(2)}"
    if gcur is not None:
        m = re.search(r"(\d+|un[ao]?|due|tre|quattro)\s+(?:giornat|turn)[aeio]", low)
        if m and ("squalific" in d.lower() or "salter" in low):
            n = int(m.group(1)) if m.group(1).isdigit() else NUMERI[m.group(1)]
            return clause, f"G{gcur + n}"
        if re.search(r"prossim[oa] (turno|giornata|partita|gara)", low):
            return clause, f"G{gcur + 1}"
    return clause, ""


def parse_indisponibili(html: str) -> list[dict]:
    """Righe (squadra, nome, tipo, dettaglio, rientro_atteso, rientro_stima) dalla pagina indisponibili."""
    soup = BeautifulSoup(html, "lxml")
    giornata = giornata_corrente(soup)
    rows: list[dict] = []
    for card in soup.select("div.card.team-card"):
        squadra = _txt(card.select_one("header.team-info .team-name"))
        for col in card.select("div.col"):
            tipo = ""
            for child in col.children:
                if not isinstance(child, Tag):
                    continue
                if child.name == "header":
                    tipo = TIPO_INDISP.get(_txt(child).lower(), _txt(child).lower())
                elif child.name == "ul":
                    for li in child.find_all("li", recursive=False):
                        nome = _txt(li.select_one(".item-name")) or _txt(li.select_one("a.player-name"))
                        if not nome:
                            continue
                        dettaglio = _txt(li.select_one(".item-description, .description"))
                        frase, stima = stima_rientro(dettaglio, giornata)
                        rows.append({"squadra": squadra, "nome": nome, "tipo": tipo,
                                     "dettaglio": dettaglio, "rientro_atteso": frase,
                                     "rientro_stima": stima})
    return rows


# --------------------------------------------------------------------------- c) rigoristi
def parse_rigoristi(html: str) -> list[dict]:
    """Righe (squadra, rigorista_1..3, punizioni_1..3) dalla pagina rigoristi."""
    soup = BeautifulSoup(html, "lxml")
    rows: list[dict] = []
    for card in soup.select("div.card.team-card"):
        squadra = _txt(card.select_one("header.team-info .team-name"))
        rig: list[str] = []
        pun: list[str] = []
        for col in card.select("div.col"):
            header = _txt(col.select_one("header")).lower()
            names = [_player(li.select_one("a.player-name"))[0] or _txt(li) for li in col.select("ol li, ul li")]
            if "rigor" in header:
                rig = names
            elif "piazzat" in header or "punizion" in header:
                pun = names
        row = {"squadra": squadra}
        for i in range(3):
            row[f"rigorista_{i + 1}"] = rig[i] if i < len(rig) else ""
            row[f"punizioni_{i + 1}"] = pun[i] if i < len(pun) else ""
        rows.append(row)
    return rows


# --------------------------------------------------------------------------- main
def scrape_mercato(out_dir: Path, date_tag: str) -> dict[str, Path]:
    """Scarica le tre pagine, salva HTML grezzi in out_dir/html e scrive i 4 CSV; ritorna {chiave: path}."""
    out_dir = Path(out_dir)
    html_dir = out_dir / "html"
    html_dir.mkdir(parents=True, exist_ok=True)
    out: dict[str, Path] = {}

    print(f"GET {URL_PROBABILI}")
    html = fetch_html(URL_PROBABILI)
    (html_dir / f"probabili_{date_tag}.html").write_text(html, encoding="utf-8")
    rows, note = parse_probabili(html)
    out["probabili"] = _write_csv(out_dir / f"probabili_{date_tag}.csv", COLS_PROBABILI, rows)
    out["probabili_note"] = _write_csv(out_dir / f"probabili_note_{date_tag}.csv", COLS_NOTE, note)

    print(f"GET {URL_INDISPONIBILI}")
    html = fetch_html(URL_INDISPONIBILI)
    (html_dir / f"indisponibili_{date_tag}.html").write_text(html, encoding="utf-8")
    out["indisponibili"] = _write_csv(out_dir / f"indisponibili_{date_tag}.csv",
                                      COLS_INDISP, parse_indisponibili(html))

    print(f"GET {URL_RIGORISTI}")
    html = fetch_html(URL_RIGORISTI)
    (html_dir / f"rigoristi_{date_tag}.html").write_text(html, encoding="utf-8")
    out["rigoristi"] = _write_csv(out_dir / f"rigoristi_{date_tag}.csv",
                                  COLS_RIGORISTI, parse_rigoristi(html))
    return out


if __name__ == "__main__":
    scrape_mercato(DEFAULT_OUT_DIR, date.today().strftime("%Y%m%d"))
