"""Fase 17 — consiglio di formazione per una giornata, dalla rosa VERA.

Legge la rosa dal ledger del Copilota (chi ho comprato io), le probabili
formazioni della giornata, gli indisponibili gia' risolti a player_id e il
pack della stagione; sceglie modulo, undici titolari e panchina ordinata con
il motore di stagione `src/fantabot/season/lineup.py` (nessuna riscrittura
delle regole: moduli, tre cambi, modificatore difesa, fasce gol stanno la').

Da dove viene il punteggio atteso (derivazione NON inventata qui: e' quella
di `src/fantabot/montecarlo.py:115` `build_dists`, la stessa che alimenta il
Monte Carlo d'asta):

- `p_play = pres / 38`, tagliato in [0.05, 0.97] (`montecarlo.py:145-146`);
- `mean_needed = value / (p_play * 38)` se `value > 0`, altrimenti la media
  dei fantavoti storici (`montecarlo.py:147`): e' il fantavoto medio per
  giornata GIOCATA che rende il valore di stagione predetto da B;
- `shift = clamp(mean_needed - media_campioni, -2, +2)` (`:148-149`), e in
  simulazione il fantavoto estratto e' `samples_fv[k] + shift + eps + shock`
  (`montecarlo.py:246`), con `eps` e `shock` a media zero.

Quindi il **punteggio atteso per giornata quando gioca** e'
`samples_fv.mean() + shift`, e il **voto puro atteso** (serve solo al
modificatore difesa) e' `samples_v.mean() + 0.4 * shift`, perche' in
simulazione il voto puro e' `samples_v[k] + (shift + eps) * 0.4 + shock`
(`montecarlo.py:247`). I campioni storici vengono dalle stagioni precedenti,
come in `scripts/f12_choose_objective.py:36-46`.

Punteggio atteso di schieramento per giocatore:

    punteggio = p_gioca * (samples_fv.mean() + shift)

con `p_gioca = pct_titolarita / 100` dalle probabili della giornata, e
`p_gioca = 0` se il giocatore e' fra gli indisponibili di
`data/copilot/eleggibilita_<stagione>.json` (infortunio o squalifica) oppure
se non compare affatto nelle probabili di quella giornata (nessuna prova che
scenda in campo: non si inventa una probabilita').

Scelta del modulo: `pick_lineup` massimizza la somma di `form` sugli undici
fra i sette moduli di `lineup.py:11-12`; passandogli come `form` il punteggio
atteso di schieramento, il modulo scelto e' quello che massimizza la somma
dei punteggi attesi degli undici. Il modificatore difesa entra perche'
`lineup.py:50-56` lo espone gia' dentro `pick_lineup` (`use_mod_difesa=True`,
richiede modulo con almeno 4 difensori e sconta mezzo gradino di prudenza):
non e' aggiunto qui. NB, e va detto: dentro `pick_lineup` il modificatore usa
i voti puri attesi NON pesati per la probabilita' di giocare — e' come il
motore congelato lo calcola, non lo si cambia da qui.

Panchina: ordinata per ruolo e per punteggio atteso decrescente, con gli
indisponibili in fondo. Contano i **primi** cambi di ogni ruolo, perche'
`score_giornata` (`lineup.py:65-97`) sostituisce un titolare senza voto con
la prima riserva DELLO STESSO RUOLO che ha voto, scorrendo la panchina in
quest'ordine, e si ferma dopo tre cambi in tutto.

Uso:
    python scripts/f17_formazione.py [stagione] --ledger PATH
                                     [--giornata N] [--probabili PATH]
                                     [--pack PATH] [--eleggibilita PATH]
                                     [--out PATH]

Scrive `data/copilot/formazione_<stagione>_G<n>.md` e stampa a terminale.
Nessuna dipendenza da `scripts/f10_copilot.py`, nessun server, nessun file
esistente modificato.
"""
from __future__ import annotations

import csv
import json
import pickle
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from fantabot.season.lineup import MODULES, pick_lineup  # noqa: E402

RUOLI = ("P", "D", "C", "A")
ORDINE_STAGIONI = ["2021-22", "2023-24", "2024-25", "2025-26", "2026-27"]
NOMI_RUOLO = {"P": "Portiere", "D": "Difensore", "C": "Centrocampista",
              "A": "Attaccante"}


# ---------------------------------------------------------------- ingressi

def leggi_ledger(path: Path) -> tuple[str, list[str]]:
    """Ritorna (stagione, player_id comprati da me) dal ledger del Copilota.

    Sola lettura: il ledger non viene mai riscritto."""
    dati = json.loads(Path(path).read_text("utf-8"))
    mio = dati.get("my_index")
    if mio is None:
        raise SystemExit(f"ledger senza 'my_index': {path}")
    rosa, visti = [], set()
    for ev in dati.get("events", []):
        if ev.get("team_index") != mio:
            continue
        pid = str(ev.get("player_id"))
        if pid and pid not in visti:
            visti.add(pid)
            rosa.append(pid)
    if not rosa:
        raise SystemExit(f"nessun giocatore mio nel ledger {path} "
                         f"(my_index={mio}, eventi={len(dati.get('events', []))})")
    return str(dati.get("season") or ""), rosa


def probabili_piu_recenti(cartella: Path) -> Path:
    """File `probabili_AAAAMMGG.csv` con la data piu' alta nel nome."""
    cand = sorted(Path(cartella).glob("probabili_[0-9]*.csv"))
    if not cand:
        raise SystemExit(f"nessun probabili_AAAAMMGG.csv in {cartella}")
    return cand[-1]


def leggi_probabili(path: Path, giornata: int | None = None) -> tuple[int, dict]:
    """Ritorna (giornata, {player_id -> riga}) dalle probabili formazioni.

    Senza `giornata` prende quella delle righe se e' una sola; se il file ne
    contiene piu' d'una la giornata va chiesta esplicitamente."""
    righe = list(csv.DictReader(Path(path).open(encoding="utf-8")))
    if not righe:
        raise SystemExit(f"probabili vuote: {path}")
    presenti = sorted({int(r["giornata"]) for r in righe if r.get("giornata")})
    if giornata is None:
        if len(presenti) != 1:
            raise SystemExit(f"{path} contiene le giornate {presenti}: "
                             f"serve --giornata N")
        giornata = presenti[0]
    sel = [r for r in righe if r.get("giornata") and int(r["giornata"]) == giornata]
    if not sel:
        raise SystemExit(f"nessuna riga per la giornata {giornata} in {path} "
                         f"(giornate presenti: {presenti})")
    out = {}
    for r in sel:
        pid = str(r.get("player_id") or "").strip()
        if not pid:
            continue
        try:
            pct = float(r.get("pct_titolarita") or 0.0)
        except ValueError:
            pct = 0.0
        out[pid] = {"squadra": r.get("squadra", ""),
                    "avversario": r.get("avversario", ""),
                    "casa": str(r.get("casa", "")).strip() in ("1", "True", "true"),
                    "nome": r.get("nome", ""),
                    "ruolo": (r.get("ruolo") or "").upper(),
                    "pct": pct,
                    "stato": r.get("stato", ""),
                    "ballottaggio_con": r.get("ballottaggio_con", "")}
    return giornata, out


def leggi_indisponibili(path: Path) -> dict:
    """{player_id -> {tipo, testo}} da eleggibilita_<stagione>.json (sola lettura)."""
    dati = json.loads(Path(path).read_text("utf-8"))
    ind = dati.get("indisponibili") or {}
    return {str(k): v for k, v in ind.items()}


def attesi_da_pack(pack_path: Path, stagione: str) -> dict:
    """{player_id -> {'fv': atteso quando gioca, 'voto': voto puro atteso}}.

    Derivazione: vedi il docstring del modulo (build_dists di montecarlo.py)."""
    from fantabot.montecarlo import build_dists  # import tardivo: pesa numpy

    pack_path = Path(pack_path)
    with open(pack_path, "rb") as f:
        pack = pickle.load(f)
    hist_votes, hist_voti = [], []
    for s in [x for x in ORDINE_STAGIONI if x < stagione][-2:]:
        p = pack_path.parent / f"pack_{s}.pkl"
        if not p.exists():
            continue
        with open(p, "rb") as f:
            pp = pickle.load(f)
        hist_votes.append(pp.votes_by_g)
        hist_voti.append(pp.voti_by_g or [])
    if not hist_votes:
        raise SystemExit("servono i pack delle stagioni precedenti per i "
                         "campioni storici (come f12_choose_objective.py)")
    dists = build_dists(pack.players, pack.b_predictions or {}, hist_votes, hist_voti)
    attesi = {}
    for pid, d in dists.items():
        attesi[str(pid)] = {"fv": float(d.samples_fv.mean() + d.shift),
                            "voto": float(d.samples_v.mean() + 0.4 * d.shift)}
    anagrafe = {str(pid): {"nome": p.name, "ruolo": p.role, "squadra": p.team}
                for pid, p in pack.players.items()}
    return attesi, anagrafe


# ---------------------------------------------------------------- calcolo

def righe_giocatori(rosa: list[str], anagrafe: dict, attesi: dict,
                    probabili: dict, indisponibili: dict) -> list[dict]:
    """Una riga per giocatore della rosa, con probabilita' e punteggio atteso.

    p_gioca = pct_titolarita/100, azzerata per infortunio/squalifica o per
    assenza dalle probabili della giornata."""
    out = []
    for pid in rosa:
        pid = str(pid)
        ana = anagrafe.get(pid, {})
        pro = probabili.get(pid)
        ind = indisponibili.get(pid)
        ruolo = (ana.get("ruolo") or (pro or {}).get("ruolo") or "").upper()
        if ruolo not in RUOLI:
            continue
        fv = float(attesi.get(pid, {}).get("fv", 0.0))
        voto = float(attesi.get(pid, {}).get("voto", 0.0))
        if pro is None:
            p = 0.0
            motivo = "non nelle probabili della giornata"
            stato = "assente"
        elif ind is not None:
            p = 0.0
            motivo = f"{ind.get('tipo', 'indisponibile')}: {ind.get('testo', '')}".strip()
            stato = str(pro.get("stato", ""))
        else:
            p = max(0.0, min(1.0, float(pro.get("pct", 0.0)) / 100.0))
            motivo = ""
            stato = str(pro.get("stato", ""))
        out.append({
            "pid": pid,
            "nome": ana.get("nome") or (pro or {}).get("nome") or pid,
            "ruolo": ruolo,
            "squadra": ana.get("squadra") or (pro or {}).get("squadra") or "",
            "avversario": (pro or {}).get("avversario", ""),
            "casa": bool((pro or {}).get("casa", False)),
            "pct": float((pro or {}).get("pct", 0.0)),
            "stato": stato,
            "ballottaggio_con": (pro or {}).get("ballottaggio_con", ""),
            "indisponibile": ind is not None,
            "motivo": motivo,
            "fv_atteso": fv,
            "voto_atteso": voto,
            "p_gioca": p,
            "punteggio": p * fv,
        })
    return out


def scegli_formazione(righe: list[dict], use_mod_difesa: bool = True):
    """(modulo, titolari, panchina) con `pick_lineup` del motore di stagione.

    `form` = punteggio atteso di schieramento, cosi' il modulo scelto e'
    quello che massimizza la somma degli undici. Ordine deterministico:
    a parita' di punteggio decide il player_id."""
    per_ruolo = {r: [] for r in RUOLI}
    for x in righe:
        per_ruolo[x["ruolo"]].append(x)
    roster = {r: [x["pid"] for x in sorted(v, key=lambda y: (-y["punteggio"], y["pid"]))]
              for r, v in per_ruolo.items()}
    form = {x["pid"]: x["punteggio"] for x in righe}
    form_voto = {x["pid"]: x["voto_atteso"] for x in righe}
    disponibili = {x["pid"] for x in righe if x["p_gioca"] > 0.0}
    fattibili = [(d, c, a) for d, c, a in MODULES
                 if len(roster["P"]) >= 1 and len(roster["D"]) >= d
                 and len(roster["C"]) >= c and len(roster["A"]) >= a]
    if not fattibili:
        conteggi = {r: len(roster[r]) for r in RUOLI}
        raise SystemExit(f"rosa insufficiente per qualunque modulo {MODULES}: "
                         f"{conteggi}")
    modulo, titolari, panchina = pick_lineup(
        roster, form, form_voto=form_voto, use_mod_difesa=use_mod_difesa,
        available=disponibili)
    return modulo, titolari, panchina


# ---------------------------------------------------------------- uscita

def _riga_md(x: dict) -> str:
    dove = "casa" if x["casa"] else "trasferta"
    avv = x["avversario"] or "-"
    note = x["motivo"] or ("ballottaggio con " + x["ballottaggio_con"]
                           if x.get("ballottaggio_con") else "")
    return (f"| {x['nome']} | {x['ruolo']} | {x['squadra']} | {avv} ({dove}) | "
            f"{x['pct']:.0f}% | {x['stato'] or '-'} | {x['fv_atteso']:.2f} | "
            f"{x['punteggio']:.2f} | {note or '-'} |")


def rendi_markdown(stagione: str, giornata: int, modulo: dict,
                   titolari: dict, panchina: dict, righe: list[dict],
                   fonte_probabili: str, fonte_pack: str) -> str:
    per_pid = {x["pid"]: x for x in righe}
    mod_txt = f"{modulo['D']}-{modulo['C']}-{modulo['A']}"
    tot = sum(per_pid[p]["punteggio"] for r in RUOLI for p in titolari[r])
    intestazione = ("| giocatore | ruolo | squadra | avversario | titolarita' | "
                    "stato | atteso se gioca | atteso schierato | note |\n"
                    "|---|---|---|---|---|---|---|---|---|")
    out = [f"# Formazione consigliata — {stagione}, giornata {giornata}", "",
           f"Modulo **{mod_txt}**, somma dei punteggi attesi degli undici: "
           f"**{tot:.2f}**.", "",
           f"- probabili: `{fonte_probabili}`",
           f"- pack: `{fonte_pack}`",
           "- punteggio atteso schierato = probabilita' di giocare "
           "(titolarita'/100, 0 se indisponibile o assente dalle probabili) "
           "x punteggio atteso per giornata quando gioca "
           "(derivazione `build_dists` di `src/fantabot/montecarlo.py`).",
           "", "## Titolari", "", intestazione]
    for r in RUOLI:
        for pid in titolari[r]:
            out.append(_riga_md(per_pid[pid]))
    out += ["", "## Panchina (ordine dei cambi)", "",
            "I cambi automatici sono al massimo **3** e valgono solo dentro lo "
            "stesso ruolo: se un titolare non prende voto entra la **prima** "
            "riserva del suo ruolo che ha voto, scorrendo la lista in "
            "quest'ordine (`score_giornata`, `src/fantabot/season/lineup.py`). "
            "Contano quindi i primi nomi di ogni reparto.", "", intestazione]
    for r in RUOLI:
        for pid in panchina.get(r, []):
            out.append(_riga_md(per_pid[pid]))
    fuori = [x for x in righe if x["indisponibile"]
             and x["pid"] in {p for r in RUOLI for p in titolari[r]}]
    if fuori:
        out += ["", "## Avvisi", ""]
        for x in fuori:
            out.append(f"- **{x['nome']}** e' schierato pur essendo "
                       f"indisponibile ({x['motivo']}): il reparto non "
                       f"offre alternative disponibili.")
    out += ["", "Una giornata sola non valida nulla: questo e' un consiglio "
            "basato sulle probabili del giorno, non una misura.", ""]
    return "\n".join(out)


def stampa(testo: str) -> None:
    print(testo)


# ---------------------------------------------------------------- comando

def main(argv: list[str]) -> int:
    args = list(argv)

    def opz(nome, default=None):
        if nome in args:
            i = args.index(nome)
            val = args[i + 1]
            del args[i:i + 2]
            return val
        return default

    ledger = opz("--ledger")
    giornata = opz("--giornata")
    probabili_p = opz("--probabili")
    pack_p = opz("--pack")
    elegg_p = opz("--eleggibilita")
    out_p = opz("--out")
    posizionali = [a for a in args if not a.startswith("--")]
    stagione = posizionali[0] if posizionali else ""
    if not ledger:
        raise SystemExit("serve --ledger PATH (ledger del Copilota)")

    stag_ledger, rosa = leggi_ledger(Path(ledger))
    stagione = stagione or stag_ledger or "2026-27"
    prob_path = Path(probabili_p) if probabili_p else probabili_piu_recenti(
        ROOT / "data" / "raw" / "mercato")
    giornata, probabili = leggi_probabili(prob_path,
                                          int(giornata) if giornata else None)
    elegg = Path(elegg_p) if elegg_p else ROOT / "data" / "copilot" / f"eleggibilita_{stagione}.json"
    indisponibili = leggi_indisponibili(elegg) if elegg.exists() else {}
    pack_path = Path(pack_p) if pack_p else ROOT / "data" / "packs" / f"pack_{stagione}.pkl"
    attesi, anagrafe = attesi_da_pack(pack_path, stagione)

    righe = righe_giocatori(rosa, anagrafe, attesi, probabili, indisponibili)
    modulo, titolari, panchina = scegli_formazione(righe)
    testo = rendi_markdown(stagione, giornata, modulo, titolari, panchina,
                           righe, prob_path.name, pack_path.name)
    dest = Path(out_p) if out_p else (ROOT / "data" / "copilot" /
                                      f"formazione_{stagione}_G{giornata}.md")
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(testo, encoding="utf-8")
    stampa(testo)
    print(f"scritto {dest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
