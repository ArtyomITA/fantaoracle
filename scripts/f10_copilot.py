"""Copilota — l'asta VERA con gli amici: tu registri, l'oracolo consiglia.

Nessun bot al tavolo: i partecipanti sono le persone reali della tua lega.
Registri ogni aggiudicazione (chi, chi, quanto) e per ogni giocatore che sale
al banco chiedi il consiglio: max bid per la TUA rosa, se e' un bargain,
piano rosa aggiornato (MILP), chi chiamare al tuo turno. Ogni evento e'
salvato subito su disco (data/copilot/ledger_*.json): chiudi, riapri,
riprendi.

Avvio:  python scripts/f10_copilot.py [stagione=2026-27] [--porta 8770] [--resume ledger.json]

API (JSON, CORS aperto):
  GET  /copilot/state                 -> tavolo, rose, budget, pool residuo, config
  POST /copilot/setup                 -> {"names":[...], "my_index":0, "budget":500}
  POST /copilot/hammer                -> {"player_id":..,"team_index":..,"price":..}
  POST /copilot/undo                  -> annulla l'ultima aggiudicazione
  POST /copilot/bid                   -> {"player_id":..,"team_index":..,"price":..}
                                         registra un rilancio osservato al tavolo
  POST /copilot/undo_bid              -> cancella l'ultimo rilancio registrato
  GET  /copilot/advice?player_id=&price=   -> consiglio sul giocatore al banco
  GET  /copilot/plan                  -> rosa target corrente + max bid per target
  GET  /copilot/nominate?role=        -> chi chiamare ora (esca o riempitivo)
  GET  /copilot/players?role=&q=&squadra=  -> ricerca nel pool residuo
  GET  /copilot/rigoristi              -> rigoristi e punizioni per squadra,
                                          con lo stato al momento
"""
from __future__ import annotations

import csv
import datetime
import hashlib
import json
import os
import pickle
import random
import sys
import threading
import time
import unicodedata
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from fantabot.bots.base import AuctionView  # noqa: E402
from fantabot.bots.bot_b import BBot  # noqa: E402
from fantabot.models import ROLES, Player, TeamState  # noqa: E402
from fantabot import piani as pn  # noqa: E402
from fantabot import rettifica_indisponibili as ri  # noqa: E402
from fantabot.market_adjust import norm as norm_mercato  # noqa: E402

LOCK = threading.Lock()
PACK = None
LEDGER_PATH: Path | None = None
STATE = {
    "season": None, "names": [], "my_index": 0, "budget": 500,
    "quotas": {"P": 3, "D": 8, "C": 8, "A": 6},
    "events": [],            # [{"player_id","team_index","price","ts"}]
    # rilanci OSSERVATI al tavolo, uno per offerta pronunciata: sono il solo
    # dato che manca al modello per capire come si comportano gli avversari
    # (chi rilancia su chi, fino a che cifra, quando passa). Restano separati
    # dalle aggiudicazioni e non vengono mai inventati: `fonte` dice sempre da
    # dove arriva la riga.
    "bids": [],              # [{"lot","player_id","team_index","price","ts","fonte"}]
}
FONTI_BID = ("osservato", "consiglio")
ADVISOR: BBot | None = None
# Le predizioni che il bot usa davvero: quelle del pack, con il valore ridotto
# per chi oggi e' indisponibile (vedi `prepara_pack`). `PACK.b_predictions`
# resta intatto: e' il dato del modello, la rettifica e' un livello sopra.
PRED_ATTIVE: dict = {}
RETTIFICHE: dict = {}
RETTIFICA_MOTIVO = ""
NOTE_ESPERTO: dict = {"meta": {}, "note": {}}
OGGI = datetime.date.today()
RIPRESO_DA_COPIA: str | None = None


# ------------------------------------------------------------ stato tavolo
def teams() -> list[TeamState]:
    ts = [TeamState(team_id=f"T{i}", bot_name=n, budget=STATE["budget"])
          for i, n in enumerate(STATE["names"])]
    for e in STATE["events"]:
        t = ts[e["team_index"]]
        p = PACK.players[e["player_id"]]
        t.roster[p.role].append((e["player_id"], e["price"]))
        t.budget -= e["price"]
    return ts


def carica_eleggibilita(stagione: str) -> dict:
    """Chi si puo' davvero comprare, dal bundle di fonti verificate.

    Senza il file, il pool resta quello del pack e lo si dichiara: meglio un
    avviso che un filtro silenziosamente assente.
    """
    f = ROOT / "data" / "copilot" / f"eleggibilita_{stagione}.json"
    if not f.exists():
        return {"attivo": False, "motivo": f"{f.name} non trovato",
                "esclusi": set(), "indisponibili": {}, "prezzi": {}}
    try:
        d = json.loads(f.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return {"attivo": False, "motivo": f"{f.name} illeggibile: {exc}",
                "esclusi": set(), "indisponibili": {}, "prezzi": {}}
    return {"attivo": True, "motivo": "",
            "esclusi": set(d.get("esclusi_fuori_serie_a", [])),
            "note": d.get("note_fuori_serie_a", {}),
            "indisponibili": d.get("indisponibili", {}),
            "prezzi": d.get("prezzo_mercato_10sq_500", {}),
            "bundle": d.get("bundle"), "acquisito": d.get("bundle_acquisito"),
            "conteggi": d.get("conteggi", {}),
            "senza_previsione": d.get("attivi_senza_previsione_dettagli", []),
            "semantica_prezzo": d.get("semantica_prezzo", "")}


def carica_note_esperto(stagione: str) -> dict:
    """Opinioni di un esperto (video, guide), per nome come nel pack.

    Non entrano nel modello: si leggono accanto al consiglio. Il file dice da
    dove vengono e di quando sono."""
    f = ROOT / "data" / "copilot" / f"note_esperto_{stagione}.json"
    if not f.exists():
        return {"meta": {}, "note": {}}
    try:
        d = json.loads(f.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"meta": {}, "note": {}}
    return {"meta": {k: v for k, v in d.items() if k != "note"},
            "note": d.get("note", {}) or {}}


def prepara_pack(stagione: str, oggi: datetime.date | None = None) -> None:
    """Quello che il pack non sa e le fonti si': si applica qui, una volta.

    - gli attivi del listone assenti dal pack entrano come giocatori SENZA
      previsione (valore zero, prezzo 1): cosi' un avversario che li compra
      si registra, e il consiglio dice che il modello non sa niente di loro;
    - il valore degli indisponibili scende in proporzione alle giornate che
      perderanno (`rettifica_indisponibili`): il piano iniziale conteneva
      Locatelli, fermo fino a gennaio, a prezzo pieno.
    """
    global PRED_ATTIVE, RETTIFICHE, NOTE_ESPERTO
    for r in ELEGGIBILITA.get("senza_previsione") or []:
        pid = str(r.get("id") or "").strip()
        if not pid or pid in PACK.players or r.get("ruolo") not in ROLES:
            continue
        PACK.players[pid] = Player(pid, r.get("nome") or pid, r["ruolo"],
                                   r.get("squadra") or "", 0.0, 0.0, 0.0)
        PACK.b_predictions[pid] = {
            "q10": 1.0, "q50": 1.0, "q90": 1.0, "value": 0.0, "value_up": 0.0,
            "senza_previsione": True,
            "motivi": "nel listone ma non nel pack: nessuna previsione"}
    # La rettifica serve solo se il pack e' PIU' VECCHIO delle fonti: la
    # catena di aggiornamento (f9_apply_market) applica gia' infortuni e
    # squalifiche alle presenze attese, e rifarlo qui conterebbe due volte
    # (Locatelli: 225 -> 128 nel pack del 10/9, poi x0,54 = 69).
    global RETTIFICA_MOTIVO
    calendario = ROOT / "data" / "raw" / "calendario" / f"calendario_{stagione}.csv"
    data_pack = data_del_pack(stagione)
    data_fonti = str(ELEGGIBILITA.get("acquisito") or "")[:19]
    pack_piu_vecchio = bool(data_pack and data_fonti and data_pack < data_fonti)
    if calendario.exists() and ELEGGIBILITA.get("indisponibili") and pack_piu_vecchio:
        cal = ri.carica_calendario(calendario)
        PRED_ATTIVE, RETTIFICHE = ri.rettifica_valori(
            PACK.b_predictions, ELEGGIBILITA["indisponibili"], cal, oggi or OGGI)
        RETTIFICA_MOTIVO = (f"pack del {data_pack[:16]} piu' vecchio delle fonti del "
                            f"{data_fonti[:16]}: valore ridotto qui per gli indisponibili")
    else:
        PRED_ATTIVE, RETTIFICHE = dict(PACK.b_predictions), {}
        RETTIFICA_MOTIVO = ("infortuni gia' dentro il pack (catena di aggiornamento "
                            f"del {data_pack[:16]}, fonti del {data_fonti[:16]})"
                            if data_pack else "data del pack sconosciuta: nessuna rettifica")
    NOTE_ESPERTO = carica_note_esperto(stagione)
    costruisci_gol()
    costruisci_rigoristi()


def data_del_pack(stagione: str) -> str | None:
    """Quando e' stato costruito il pack: dal riferimento corrente se
    l'impronta coincide, altrimenti dalla data del file."""
    pkl = ROOT / "data" / "packs" / f"pack_{stagione}.pkl"
    if not pkl.exists():
        return None
    rif = ROOT / "data" / "packs" / "CORRENTE.json"
    try:
        d = json.loads(rif.read_text(encoding="utf-8"))
        if d.get("impronta") == identita_bundle().get("impronta") and d.get("aggiornato"):
            return str(d["aggiornato"])[:19]
    except (OSError, json.JSONDecodeError, TypeError):
        pass
    return datetime.datetime.fromtimestamp(pkl.stat().st_mtime).isoformat(timespec="seconds")


ELEGGIBILITA = {"attivo": False, "esclusi": set(), "indisponibili": {},
                "prezzi": {}, "motivo": "non ancora caricata"}


# ------------------------------------------------------------ rigoristi
# Fonte: data/raw/mercato/rigoristi_<AAAAMMGG>.csv, dove la squadra ha il nome
# intero («Atalanta») e i giocatori il nome di fantacalcio.it. L'aggancio e' lo
# stesso di scripts/f9_apply_market.py — mappa squadra intera -> codice, chiave
# di cognome, disambigua col nome completo — solo applicato al pack invece che
# al registry, perche' qui l'id che serve e' quello del pack.
SIGLE_MERCATO = {
    "ATALANTA": "ATA", "BOLOGNA": "BOL", "CAGLIARI": "CAG", "COMO": "COM",
    "CREMONESE": "CRE", "FIORENTINA": "FIO", "FROSINONE": "FRO", "GENOA": "GEN",
    "INTER": "INT", "JUVENTUS": "JUV", "LAZIO": "LAZ", "LECCE": "LEC",
    "MILAN": "MIL", "MONZA": "MON", "NAPOLI": "NAP", "PARMA": "PAR",
    "PISA": "PIS", "ROMA": "ROM", "SASSUOLO": "SAS", "TORINO": "TOR",
    "UDINESE": "UDI", "VENEZIA": "VEN", "VERONA": "VER", "HELLAS VERONA": "VER",
    "EMPOLI": "EMP", "SALERNITANA": "SAL", "SAMPDORIA": "SAM", "SPEZIA": "SPE",
}
COLONNE_RIGORI = ("rigorista_1", "rigorista_2", "rigorista_3")
COLONNE_PUNIZIONI = ("punizioni_1", "punizioni_2", "punizioni_3")
# [{"squadra_codice","squadra_nome","rigoristi":[{nome,player_id}],"punizioni":[...]}]
RIGORISTI: list = []
RIGORISTI_FONTE: dict = {"file": None, "data": None, "non_agganciati": []}


def _chiave_cognome(nome: str) -> str:
    """«Martinez L.» -> «MARTINEZ» (come `surname_key` di f9_apply_market)."""
    parti = norm_mercato(nome).split()
    if len(parti) > 1 and len(parti[-1]) <= 2:      # iniziale del nome
        parti = parti[:-1]
    return " ".join(parti)


def costruisci_rigoristi() -> None:
    """Legge il CSV piu' recente e aggancia i nomi agli id del pack.

    L'ordine della fonte e' l'ordine di battuta: si conserva. Lo stato (chi e'
    ancora libero) NON si calcola qui: cambia a ogni martelletto, e si calcola
    a ogni richiesta in `rigoristi_ora`.
    """
    global RIGORISTI, RIGORISTI_FONTE
    RIGORISTI = []
    non_agganciati: list[dict] = []
    cartella = ROOT / "data" / "raw" / "mercato"
    file = sorted(cartella.glob("rigoristi_*.csv")) if cartella.exists() else []
    if not file or PACK is None:
        RIGORISTI_FONTE = {"file": None, "data": None, "non_agganciati": []}
        return
    p = file[-1]
    per_chiave: dict = {}
    per_cognome: dict = {}
    for pid, g in PACK.players.items():
        k = _chiave_cognome(g.name)
        per_chiave.setdefault((k, g.team), []).append((pid, norm_mercato(g.name)))
        per_cognome.setdefault(k, []).append((pid, norm_mercato(g.name)))

    def aggancia(nome: str, sigla: str) -> str | None:
        k, intero = _chiave_cognome(nome), norm_mercato(nome)
        cand = per_chiave.get((k, sigla)) or per_cognome.get(k) or []
        if len(cand) == 1:
            return cand[0][0]
        esatti = [m for m, f in cand if f == intero]
        return esatti[0] if len(esatti) == 1 else None

    try:
        with p.open(encoding="utf-8-sig", newline="") as f:
            righe = list(csv.DictReader(f))
    except OSError:
        righe = []
    for r in righe:
        nome_sq = (r.get("squadra") or "").strip()
        if not nome_sq:
            continue
        sigla = SIGLE_MERCATO.get(norm_mercato(nome_sq), norm_mercato(nome_sq)[:3])
        voce = {"squadra_codice": sigla, "squadra_nome": nome_sq,
                "rigoristi": [], "punizioni": []}
        for campo, colonne in (("rigoristi", COLONNE_RIGORI),
                               ("punizioni", COLONNE_PUNIZIONI)):
            for col in colonne:
                nome = (r.get(col) or "").strip()
                if not nome:
                    continue
                pid = aggancia(nome, sigla)
                if pid is None:
                    non_agganciati.append({"squadra": nome_sq, "colonna": col,
                                           "nome": nome})
                voce[campo].append({"nome": nome, "player_id": pid})
        RIGORISTI.append(voce)
    cifre = "".join(ch for ch in p.stem if ch.isdigit())
    data = f"{cifre[:4]}-{cifre[4:6]}-{cifre[6:]}" if len(cifre) == 8 else None
    RIGORISTI_FONTE = {"file": p.name, "data": data,
                       "non_agganciati": non_agganciati}
    if non_agganciati:
        print(f"  rigoristi: {p.name}, {len(non_agganciati)} nomi non agganciati "
              f"(per esempio {non_agganciati[0]['nome']})")


def stato_rigorista(pid: str | None) -> str:
    """Lo stato ADESSO: il tavolo comanda, poi la lista."""
    if not pid or PACK is None or pid not in PACK.players:
        return "fuori lista"
    for e in STATE["events"]:
        if e["player_id"] == pid:
            if e["team_index"] == STATE["my_index"]:
                return "mio"
            nome = (STATE["names"][e["team_index"]]
                    if e["team_index"] < len(STATE["names"]) else e["team_index"])
            return f"venduto a {nome}"
    if (pid in ELEGGIBILITA.get("esclusi", ())
            or pid in (STATE.get("esclusi_manuali") or [])):
        return "fuori lista"
    if (ELEGGIBILITA.get("indisponibili") or {}).get(pid):
        return "indisponibile"
    return "disponibile"


# --------------------------------------------------- gol dalle pagelle
# Additivo: quanti gol ha fatto davvero, non quanti ne promette il modello.
# Fonte: data/raw/voti/voti_<stagione>.csv (una riga per giocatore/giornata)
# agganciata a data/processed/_match/map_voti.csv, dove `master_id` E' il
# player_id del pack (Malen 5585). Se un file manca, la stagione resta vuota
# e i campi escono null: la pagina degrada, il server non si ferma.
STAGIONI_GOL = (("2026-27", "2026"), ("2025-26", "2025"))
GOL_VOTI: dict = {s: {} for s, _ in STAGIONI_GOL}


def _num_voto(v) -> float:
    """Numero da una cella dei voti; vuoto o rotto vale zero."""
    try:
        return float(str(v or "").strip().replace(",", "."))
    except ValueError:
        return 0.0


def costruisci_gol() -> None:
    """Somma gol, rigori, assist e presenze a voto per player_id."""
    global GOL_VOTI
    GOL_VOTI = {s: {} for s, _ in STAGIONI_GOL}
    mappa: dict = {}
    fmap = ROOT / "data" / "processed" / "_match" / "map_voti.csv"
    try:
        with fmap.open(encoding="utf-8-sig", newline="") as f:
            for r in csv.DictReader(f):
                try:                                   # master_id e' float: 2792.0
                    pid = str(int(float(r.get("master_id") or "")))
                except (TypeError, ValueError):
                    continue
                mappa[(r.get("stagione"), r.get("squadra"), r.get("nome"))] = pid
    except OSError:
        return
    for stagione, _suf in STAGIONI_GOL:
        fv = ROOT / "data" / "raw" / "voti" / f"voti_{stagione}.csv"
        if not fv.exists():
            continue
        agg = GOL_VOTI[stagione]
        try:
            with fv.open(encoding="utf-8-sig", newline="") as f:
                for r in csv.DictReader(f):
                    pid = mappa.get((r.get("stagione"), r.get("squadra"),
                                     r.get("nome")))
                    if not pid:
                        continue
                    d = agg.setdefault(pid, {"gol": 0, "rig": 0, "rigsb": 0,
                                             "assist": 0, "pres": 0})
                    d["gol"] += int(_num_voto(r.get("gol_fatti")))
                    d["rig"] += int(_num_voto(r.get("rigore_segnato")))
                    d["rigsb"] += int(_num_voto(r.get("rigori_sbagliati")))
                    d["assist"] += int(_num_voto(r.get("assist")))
                    if _num_voto(r.get("sv")) == 0:     # sv==0 = ha preso voto
                        d["pres"] += 1
        except OSError:
            continue
    print("  gol dai voti: " + ", ".join(
        f"{s} {len(GOL_VOTI[s])} giocatori" for s, _ in STAGIONI_GOL))


def campi_gol(pid: str | None) -> dict:
    """I campi gol per un player_id; null dove la fonte non dice niente."""
    out: dict = {}
    for stagione, suf in STAGIONI_GOL:
        d = GOL_VOTI.get(stagione, {}).get(pid) if pid else None
        out[f"gol_{suf}"] = d["gol"] if d else None
        out[f"rig_{suf}"] = d["rig"] if d else None
        out[f"rigsb_{suf}"] = d["rigsb"] if d else None
        out[f"pres_{suf}"] = d["pres"] if d else None
    d25 = GOL_VOTI.get("2025-26", {}).get(pid) if pid else None
    out["assist_2025"] = d25["assist"] if d25 else None
    return out


def rigoristi_ora() -> dict:
    """RIGORISTI + stato corrente + primo ancora disponibile per ogni ordine."""
    squadre = []
    for v in RIGORISTI:
        riga = {"squadra_codice": v["squadra_codice"],
                "squadra_nome": v["squadra_nome"]}
        for campo in ("rigoristi", "punizioni"):
            voci = []
            for x in v[campo]:
                pid = x["player_id"]
                g = PACK.players.get(pid) if (pid and PACK) else None
                voce = {"nome": x["nome"], "player_id": pid,
                        "stato": stato_rigorista(pid),
                        "ruolo": g.role if g else None,
                        "squadra": g.team if g else v["squadra_codice"],
                        "agganciato": bool(g)}
                voce.update(campi_gol(pid))            # additivo: gol veri
                voci.append(voce)
            riga[campo] = voci
            primo = next((x["player_id"] for x in voci
                          if x["stato"] == "disponibile"), None)
            riga["primo_disponibile" if campo == "rigoristi"
                 else "primo_disponibile_punizioni"] = primo
        squadre.append(riga)
    # vista piatta per reparto: chi batte i rigori, ordinato per gol veri
    per_ruolo: dict = {r: [] for r in ("P", "D", "C", "A")}
    for riga in squadre:
        for i, v in enumerate(riga.get("rigoristi") or []):
            ruolo = v.get("ruolo")
            if ruolo not in per_ruolo:                 # non agganciato: niente ruolo
                continue
            voce = {"nome": v["nome"], "player_id": v["player_id"],
                    "ordine": i + 1, "ruolo": ruolo,
                    "squadra": v.get("squadra") or riga["squadra_codice"],
                    "squadra_nome": riga["squadra_nome"],
                    "stato": v["stato"], "agganciato": v.get("agganciato"),
                    "primo_disponibile_della_squadra":
                        bool(v["player_id"])
                        and v["player_id"] == riga.get("primo_disponibile")}
            voce.update(campi_gol(v["player_id"]))
            per_ruolo[ruolo].append(voce)
    for lst in per_ruolo.values():
        lst.sort(key=lambda x: (-(x.get("gol_2025") or 0),
                                -(x.get("gol_2026") or 0), x["nome"]))
    return {"data": RIGORISTI_FONTE.get("data"),
            "file": RIGORISTI_FONTE.get("file"),
            "per_ruolo": per_ruolo,
            "squadre": squadre,
            "non_agganciati": RIGORISTI_FONTE.get("non_agganciati") or []}


def pool(solo_eleggibili: bool = True) -> dict:
    """Il pool dei consigli.

    `solo_eleggibili=True` toglie chi la fonte dichiara fuori dalla Serie A:
    63 giocatori che il vecchio scraper non marcava e che il pack contiene
    ancora. Non toglie gli infortunati — restano comprabili, e confondere le
    due cose e' proprio l'errore da evitare.

    Il martelletto usa `solo_eleggibili=False`: se al tavolo qualcuno compra
    davvero un fuori lista, l'asta reale ha ragione e il registro deve poterlo
    scrivere.
    """
    sold = {e["player_id"] for e in STATE["events"]}
    fuori = set()
    if solo_eleggibili:
        # fuori lista secondo le fonti, piu' chi hai escluso tu dal piano
        fuori = set(ELEGGIBILITA["esclusi"]) | set(STATE.get("esclusi_manuali") or [])
    return {pid: p for pid, p in PACK.players.items()
            if pid not in sold and pid not in fuori}


def view_for_me(role: str = "A") -> AuctionView:
    ts = teams()
    me = ts[STATE["my_index"]]
    return AuctionView(
        me=me, others=[t for i, t in enumerate(ts) if i != STATE["my_index"]],
        quotas=STATE["quotas"], budget_total=STATE["budget"], current_role=role,
        pool=pool(),
        sold=[(e["player_id"], f"T{e['team_index']}", e["price"]) for e in STATE["events"]],
    )


def save():
    """Scrittura atomica con ultima copia buona.

    Prima era `write_text` diretto: un'interruzione a meta' scrittura lasciava
    un ledger troncato, e l'asta non riprendeva. Ora si scrive un temporaneo
    **nello stesso filesystem**, lo si forza su disco, e solo allora lo si
    sostituisce: `os.replace` e' atomico sullo stesso volume. La copia
    precedente resta come `.buono` finche' la nuova non e' scritta per intero.
    """
    if LEDGER_PATH is None:
        return
    LEDGER_PATH.parent.mkdir(parents=True, exist_ok=True)
    testo = json.dumps(STATE, ensure_ascii=False, indent=1)
    if LEDGER_PATH.exists():
        try:
            # l'ultima copia buona e' quella che si e' gia' riletta senza errori
            precedente = LEDGER_PATH.read_text(encoding="utf-8")
            json.loads(precedente)
            LEDGER_PATH.with_suffix(".buono.json").write_text(
                precedente, encoding="utf-8")
        except (OSError, json.JSONDecodeError):
            # se la precedente e' illeggibile non la si promuove a copia buona
            pass
    tmp = LEDGER_PATH.with_suffix(f".tmp{os.getpid()}")
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(testo)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, LEDGER_PATH)


def identita_bundle() -> dict:
    """Chi e' il pack che questa sessione sta usando.

    Serve a impedire che un aggiornamento cambi il contesto sotto i piedi di
    un'asta gia' cominciata: la sessione registra l'impronta del pack con cui
    e' partita, e alla ripresa si controlla che sia la stessa.
    """
    pkl = ROOT / "data" / "packs" / f"pack_{STATE.get('season')}.pkl"
    if not pkl.exists():
        return {"pack": pkl.name, "impronta": None, "esiste": False}
    return {"pack": pkl.name, "esiste": True,
            "impronta": hashlib.sha256(pkl.read_bytes()).hexdigest(),
            "giocatori": len(PACK.players) if PACK else None}


def carica_ledger(percorso: Path) -> dict | None:
    """Rilegge il ledger, ripiegando sull'ultima copia buona.

    Restituisce `None` se non c'e' niente di leggibile: meglio dirlo che
    ripartire da uno stato inventato.
    """
    for candidato in (percorso, percorso.with_suffix(".buono.json")):
        try:
            if candidato.exists():
                d = json.loads(candidato.read_text(encoding="utf-8"))
                if isinstance(d, dict) and "events" in d:
                    if candidato != percorso:
                        global RIPRESO_DA_COPIA
                        RIPRESO_DA_COPIA = candidato.name
                        print(f"  ledger principale illeggibile: ripreso da "
                              f"{candidato.name}")
                    return d
        except (OSError, json.JSONDecodeError):
            continue
    return None


def intero_valido(x, minimo: int = 1) -> int:
    """Un importo d'asta e' un intero finito, non minore del minimo.

    Prima si usava `int(x)`: 10,9 diventava 10 in silenzio, e -10 passava
    aumentando la cassa. Qui un valore non intero e' un errore, non un
    arrotondamento deciso dal server al posto di chi digita.
    """
    if isinstance(x, bool) or not isinstance(x, (int, float)):
        raise ValueError(f"importo non numerico: {x!r}")
    if isinstance(x, float):
        if x != x or x in (float("inf"), float("-inf")):
            raise ValueError(f"importo non finito: {x!r}")
        if not float(x).is_integer():
            raise ValueError(f"importo non intero: {x!r}. I crediti sono interi")
    v = int(x)
    if v < minimo:
        raise ValueError(f"importo {v}: il minimo e' {minimo}")
    return v


def indice_valido(x, quanti: int) -> int:
    if isinstance(x, bool) or not isinstance(x, (int, float)) or (
            isinstance(x, float) and not float(x).is_integer()):
        raise ValueError(f"indice squadra non valido: {x!r}")
    v = int(x)
    if not (0 <= v < quanti):
        raise ValueError(f"squadra {v} inesistente: ce ne sono {quanti}")
    return v


def stato_valido(candidato: dict) -> dict:
    """Valida uno stato COMPLETO prima di renderlo corrente.

    Il difetto: `/copilot/setup` scriveva nomi, indice e budget nello stato
    globale e sul disco, e solo dopo scopriva che `my_index=99` non esisteva —
    lasciando su disco uno stato che non si puo' riprendere.
    """
    nomi = [str(x).strip() for x in candidato.get("names", []) if str(x).strip()]
    if len(nomi) < 2:
        raise ValueError("servono almeno 2 partecipanti")
    if len(set(nomi)) != len(nomi):
        raise ValueError("nomi duplicati: le squadre devono essere distinte")
    mio = indice_valido(candidato.get("my_index", 0), len(nomi))
    budget = intero_valido(candidato.get("budget", 500), minimo=1)
    quote = {k: intero_valido(v, minimo=0)
             for k, v in (candidato.get("quotas") or {}).items()}
    if quote and set(quote) != set(ROLES):
        raise ValueError(f"quote incomplete: servono {sorted(ROLES)}")
    quote = quote or dict(STATE["quotas"])
    if sum(quote.values()) > budget:
        raise ValueError(
            f"budget {budget} sotto il minimo legale {sum(quote.values())}: "
            "serve almeno un credito per slot")
    eventi = list(candidato.get("events", []))
    for e in eventi:
        if e["team_index"] >= len(nomi):
            raise ValueError(
                f"un acquisto gia' registrato appartiene alla squadra "
                f"{e['team_index']}, che questa configurazione non ha. "
                "Apri una sessione nuova invece di riusare gli indici")
        ruolo = PACK.players[e["player_id"]].role
        if quote.get(ruolo, 0) < 1:
            raise ValueError(
                f"la quota per il ruolo {ruolo} e' zero, ma ci sono gia' "
                "acquisti in quel ruolo")
    # il budget nuovo deve coprire quanto ogni squadra ha gia' speso, piu' un
    # credito per ogni slot che le resta: prima un setup rifatto a meta' asta
    # con il budget sbagliato mandava le casse sotto zero e finiva su disco
    slot_totali = sum(quote.values())
    for i, nome in enumerate(nomi):
        miei = [e for e in eventi if e["team_index"] == i]
        speso = sum(int(e["price"]) for e in miei)
        restano = slot_totali - len(miei)
        if speso + max(0, restano) > budget:
            raise ValueError(
                f"budget {budget} insufficiente per {nome}: ha gia' speso "
                f"{speso} e le restano {restano} slot da un credito almeno")
    return {**candidato, "names": nomi, "my_index": mio, "budget": budget,
            "quotas": quote, "events": eventi}


def rebuild_advisor():
    """Ricostruisce l'oracolo dallo stato: replan + calore mercato dai
    prezzi gia' battuti (stessa logica del bot B in asta simulata)."""
    global ADVISOR
    ADVISOR = BBot(random.Random(1), PRED_ATTIVE or PACK.b_predictions,
                   objective=getattr(PACK, "b_objective", None))
    for e in STATE["events"]:
        q50 = ADVISOR._q(e["player_id"], "q50")
        if q50 > 3:
            ADVISOR.infl_num += e["price"]
            ADVISOR.infl_den += q50
    if STATE["names"]:
        ADVISOR._replan(view_for_me())


def senza_accenti(s: str) -> str:
    """«calo» deve trovare Calò: in asta si digita in fretta e senza accenti.

    Il pack ha 17 nomi con accento (Laurientè, Soulè, Kessiè, Calò, ...): con
    il confronto letterale una ricerca senza accento non trovava nessuno.
    """
    return "".join(ch for ch in unicodedata.normalize("NFKD", str(s).lower())
                   if not unicodedata.combining(ch))


def player_info(pid: str) -> dict:
    p = PACK.players[pid]
    pr = (PRED_ATTIVE or PACK.b_predictions).get(pid, {})
    ind = (ELEGGIBILITA.get("indisponibili") or {}).get(pid)
    fuori = {"id": pid, "nome": p.name, "ruolo": p.role, "squadra": p.team,
             "q10": pr.get("q10"), "q50": pr.get("q50"), "q90": pr.get("q90"),
             # `value` e' quello che il bot usa: rettificato se indisponibile
             "value": pr.get("value"), "motivi": pr.get("motivi", ""),
             "indisponibile": ((ind or {}).get("tipo") or None) if ind else None,
             "indisponibile_testo": ((ind or {}).get("testo") or "")[:220] or None,
             "prezzo_mercato": (ELEGGIBILITA.get("prezzi") or {}).get(pid),
             "nota_esperto": (NOTE_ESPERTO.get("note") or {}).get(p.name),
             "escluso_manuale": pid in (STATE.get("esclusi_manuali") or []),
             "fuori_lista": pid in ELEGGIBILITA.get("esclusi", ()),
             "senza_previsione": bool(pr.get("senza_previsione"))}
    if pid in RETTIFICHE:
        fuori["value_originale"] = pr.get("value_originale")
        fuori["rettifica"] = RETTIFICHE[pid]
    return fuori


# ------------------------------------------------------------ consigli
def _il_bot_pagherebbe(v, giocatore, quanto: int) -> bool:
    """Il bot arriverebbe a `quanto` per questo giocatore?

    Si interroga il bot invece di riscrivere le sue soglie: `bid` riceve il
    prezzo corrente e propone `prezzo + 1`, quindi per sapere se pagherebbe X
    gli si chiede che cosa farebbe a X-1.
    """
    d = ADVISOR.bid(v, giocatore, quanto - 1, None)
    return d.amount is not None and int(d.amount) >= quanto


def concorrenti_sopra(v: AuctionView, ruolo: str, tetto: int) -> dict:
    """Chi, fra gli avversari, puo' rilanciare sopra il tuo tetto.

    Solo informazione: non tocca la politica. Conta l'avversario che ha ancora
    uno slot libero in quel ruolo e un massimo legale di almeno `tetto` + 1.
    Con tetto 0 non c'e' niente da superare e il conteggio e' 0.
    """
    if tetto <= 0:
        return {"concorrenti_sopra_tetto": 0, "concorrenti_nomi": [],
                "concorrenti_max": 0}
    sopra = []
    for t in v.others:
        if t.slots_left(v.quotas, ruolo) <= 0:
            continue
        mb = int(t.max_bid(v.quotas))
        if mb >= tetto + 1:
            # `bot_name` viene da STATE["names"], nello stesso ordine
            sopra.append((mb, t.bot_name))
    sopra.sort(key=lambda x: -x[0])
    return {"concorrenti_sopra_tetto": len(sopra),
            "concorrenti_nomi": [n for _, n in sopra[:5]],
            "concorrenti_max": sopra[0][0] if sopra else 0}


def decisione_operativa(pid: str, price: int | None) -> dict:
    """La sola politica: quella del bot, troncata dai limiti legali.

    Il difetto riprodotto: sullo stesso giocatore (valore 100, offerta 6) il
    Copilota diceva «rilancia fino a 95» e il bot passava per la guardia
    anti-zavorra. Erano due catene di filtri scritte due volte, nello stesso
    ordine solo per un po'.

    Qui il tetto si ottiene **chiedendo al bot**: la sua accettazione e'
    monotona in `nxt` — la guardia sui 5 crediti, il tetto del target e quello
    del bargain sono tutti soglie superiori — quindi il massimo che pagherebbe
    si trova per bisezione. La politica del bot non viene toccata.
    """
    v = view_for_me(PACK.players[pid].role)
    giocatore = PACK.players[pid]
    ruolo = giocatore.role
    slot_ruolo = v.me.slots_left(v.quotas, ruolo)
    slot_totali = v.me.slots_left(v.quotas)
    max_legale = int(v.me.max_bid(v.quotas))
    venduto = pid not in pool()

    fuori = {"max_legale": max_legale, "slot_liberi_ruolo": slot_ruolo,
             "slot_liberi_totali": slot_totali, "gia_venduto": venduto,
             "prezzo_corrente": price,
             "prossima_offerta": None if price is None else int(price) + 1,
             # indicatore «chi puo' superarti»: vuoto dove il tetto e' 0, le
             # uscite con un tetto vero lo ricalcolano sotto
             "concorrenti_sopra_tetto": 0, "concorrenti_nomi": [],
             "concorrenti_max": 0}

    if pid in ELEGGIBILITA["esclusi"]:
        nota = (ELEGGIBILITA.get("note", {}) or {}).get(pid) or \
            "non gioca piu' in Serie A"
        return {**fuori, "azione": "nessuna offerta", "max_consigliato": 0,
                "motivo": f"fuori lista: {nota}", "fuori_lista": True}
    if pid in (STATE.get("esclusi_manuali") or []):
        return {**fuori, "azione": "nessuna offerta", "max_consigliato": 0,
                "motivo": "escluso dal piano da te: riammettilo se cambi idea",
                "fuori_lista": False, "escluso_manuale": True}
    if venduto:
        return {**fuori, "azione": "nessuna offerta", "max_consigliato": 0,
                "motivo": "gia' aggiudicato a un'altra squadra"}
    if slot_totali <= 0:
        return {**fuori, "azione": "nessuna offerta", "max_consigliato": 0,
                "motivo": "rosa completa"}
    if slot_ruolo <= 0:
        return {**fuori, "azione": "nessuna offerta", "max_consigliato": 0,
                "motivo": f"reparto {ruolo} pieno"}
    if max_legale < 1:
        return {**fuori, "azione": "nessuna offerta", "max_consigliato": 0,
                "motivo": "cassa insufficiente: servono i crediti per gli "
                          "slot che restano"}

    indisp = (ELEGGIBILITA.get("indisponibili") or {}).get(pid)
    extra = {"fuori_lista": False, "indisponibile": indisp,
             "prezzo_mercato": (ELEGGIBILITA.get("prezzi") or {}).get(pid),
             "in_piano": pid in ADVISOR.targets,
             "titolare_di_piano": pid in ADVISOR.starter_targets}

    # obbligo di completare la rosa: se chi resta comprabile in questo ruolo
    # basta appena per gli slot che ho, lasciarlo vuol dire chiudere l'asta
    # con la rosa incompleta. Il tetto e' il massimo legale, e lo si dice.
    liberi_ruolo = sum(1 for p_ in pool().values() if p_.role == ruolo)
    if liberi_ruolo <= slot_ruolo:
        return {**fuori, **extra, **concorrenti_sopra(v, ruolo, max_legale),
                "azione": "rilancia", "max_consigliato": max_legale,
                "obbligo": True,
                "motivo": (f"obbligo di completare la rosa: restano "
                           f"{liberi_ruolo} {ruolo} comprabili per {slot_ruolo} "
                           f"slot. Fino al massimo legale {max_legale}")}

    # bisezione sul massimo che il bot pagherebbe, dentro il limite legale
    basso, alto = 0, max_legale
    if _il_bot_pagherebbe(v, giocatore, 1):
        basso = 1
        while basso < alto:
            mezzo = (basso + alto + 1) // 2
            if _il_bot_pagherebbe(v, giocatore, mezzo):
                basso = mezzo
            else:
                alto = mezzo - 1
    tetto = int(basso)
    motivo = ADVISOR.bid(v, giocatore, max(tetto, 1) - 1, None).thought
    prossima = fuori["prossima_offerta"]

    if tetto < 1:
        azione = "non offrire"
        motivo = ADVISOR.bid(v, giocatore, 0, None).thought or "fuori politica"
    elif prossima is not None and prossima > tetto:
        azione = "lascia"
        motivo = f"oltre il massimo {tetto}: {motivo}"
    else:
        azione = "rilancia"
    return {**fuori, **extra, **concorrenti_sopra(v, ruolo, tetto),
            "azione": azione, "max_consigliato": tetto,
            "motivo": motivo, "obbligo": False}


def advice(pid: str, price: int | None) -> dict:
    if ADVISOR is None or not STATE["names"]:
        return {"err": "tavolo non configurato"}
    info = player_info(pid)
    d = decisione_operativa(pid, price)
    heat = ADVISOR.market_heat()
    # il tetto del bargain esiste ancora come informazione, ma NON e' piu' una
    # seconda politica: il numero da rispettare e' `max_consigliato`, che e'
    # gia' troncato dal limite legale
    bargain_cap = min(ADVISOR._q(pid, "q10"), ADVISOR._q(pid, "q50") * 0.6) * heat * 0.9
    tetto = d["max_consigliato"]
    out = {
        **info, **d, "heat": round(heat, 2),
        "bargain_sotto": min(round(bargain_cap, 1), float(tetto)),
        "offerta_massima_legale": d["max_legale"],
        "prezzo_ombra": (round(ADVISOR._dropoff_credits(pid), 1)
                         if d.get("in_piano") else None),
    }
    if d["azione"] == "nessuna offerta":
        out["consiglio"] = d["motivo"]
    elif d["azione"] == "non offrire":
        out["consiglio"] = f"non offrire: {d['motivo']}"
    elif d["azione"] == "lascia":
        out["consiglio"] = f"lascialo: {d['motivo']}"
    elif d.get("in_piano"):
        quale = "titolare" if d.get("titolare_di_piano") else "panchina"
        out["consiglio"] = f"NEL PIANO ({quale}): rilancia fino a {tetto}"
    else:
        out["consiglio"] = f"fuori piano: rilancia al massimo fino a {tetto}"
    return out


def plan() -> dict:
    if ADVISOR is None or not STATE["names"]:
        return {"err": "tavolo non configurato"}
    v = view_for_me()
    by_role = {r: [] for r in ROLES}
    tot = 0.0
    for pid in ADVISOR.targets:
        p = PACK.players.get(pid)
        if p is None:
            continue
        # STESSO tetto del banco: `_max_bid_for` e' grezzo e ignora il limite
        # legale, quindi il piano mostrava 167,8 dove il banco diceva 167
        dec = decisione_operativa(pid, None)
        cap = dec["max_consigliato"]
        q50 = ADVISOR._q(pid, "q50") * ADVISOR.market_heat()
        tot += q50
        by_role[p.role].append({**player_info(pid), "titolare": pid in ADVISOR.starter_targets,
                                "prezzo_atteso": round(q50, 1),
                                "max_consigliato": round(cap, 1),
                                # indicatore «chi puo' superarti», stesso conto del banco
                                "concorrenti_sopra_tetto": dec["concorrenti_sopra_tetto"],
                                "concorrenti_nomi": dec["concorrenti_nomi"],
                                "concorrenti_max": dec["concorrenti_max"]})
    for r in ROLES:
        by_role[r].sort(key=lambda x: -(x["value"] or 0))
    me = v.me
    return {"heat": round(ADVISOR.market_heat(), 2), "budget": me.budget,
            "slot_liberi": {r: me.slots_left(v.quotas, r) for r in ROLES},
            "costo_atteso_piano": round(tot, 1), "target": by_role}


# La cache dei piani e' identificata da bundle, stato, vincoli e prezzo
# ipotetico: un martelletto cambia lo stato, quindi la chiave cambia e i
# risultati vecchi non possono riapparire come attuali.
PIANI_CACHE: dict = {}


def contesto_piani() -> pn.Contesto:
    """Gli stessi ingressi con cui il bot ripianifica: nessuna seconda politica.

    In particolare restano il `lam` dell'obiettivo e il pavimento di spesa: il
    vecchio Livello 3 perse il confronto proprio perche' un braccio cambiava
    due cose insieme.
    """
    v = view_for_me()
    heat = ADVISOR.market_heat()
    candidati = {pid: p for pid, p in pool().items()}
    prezzi = {pid: max(1.0, ADVISOR._q(pid, "q50") * heat) for pid in candidati}
    fissati = {pid: PACK.players[pid]
               for r, ids in v.me.roster.items() for pid, _ in ids}
    valori = {pid: ADVISOR._q(pid, "value", 0.0)
              for pid in list(candidati) + list(fissati)}
    valori_up = {pid: ADVISOR._q(pid, "value_up", valori[pid]) for pid in valori}
    obiettivo = getattr(ADVISOR, "objective", None) or {}
    # lo STESSO vincolo di spesa in attacco che il bot usa in `_replan`. Senza,
    # il «riferimento» dei piani era una rosa diversa da quella consigliata al
    # banco (attacco 93 contro 191 sul pack corrente), e il piano del bot
    # compariva come alternativa con uno scarto.
    forzato = None
    if obiettivo.get("attack_share"):
        speso_a = sum(pr for _, pr in v.me.roster.get("A", []))
        lo_s, hi_s = obiettivo["attack_share"]
        lo = max(0.0, lo_s * STATE["budget"] - speso_a)
        hi = max(lo, hi_s * STATE["budget"] - speso_a)
        forzato = {"A": (lo, hi)}
    return pn.Contesto(
        candidati=candidati, prezzi=prezzi, valori=valori, valori_up=valori_up,
        quote=dict(STATE["quotas"]), budget=float(v.me.budget),
        fissati=fissati, lam=float(obiettivo.get("lam", 0.0)),
        forced_spend=forzato,
        min_spend=obiettivo.get("min_spend"), time_limit=5)


def info_breve(pid: str) -> dict:
    p = PACK.players.get(pid)
    if p is None:
        return {"id": pid, "nome": pid, "ruolo": "?", "squadra": "?"}
    ind = (ELEGGIBILITA.get("indisponibili") or {}).get(pid)
    return {"id": pid, "nome": p.name, "ruolo": p.role, "squadra": p.team,
            "indisponibile": bool(ind),
            "indisponibile_nota": (ind or {}).get("testo", "")[:160] or None,
            "prezzo_mercato": (ELEGGIBILITA.get("prezzi") or {}).get(pid)}


def versione_stato() -> str:
    """Cambia a ogni acquisto: lega ogni risposta allo stato che l'ha prodotta."""
    return f"{len(STATE['events'])}:{len(STATE.get('bids', []))}"


def piani_alternativi(quanti: int = 6) -> dict:
    """Il MILP dei piani puo' durare secondi: gira FUORI dal lock.

    Sotto lock si legge lo stato (contesto, versione) e si scrive la cache;
    il calcolo lavora su copie. Se nel frattempo arriva un martelletto, la
    versione dello stato cambia e il risultato viene consegnato ma non messo
    in cache: la pagina lo vede come «da ricalcolare».
    """
    with LOCK:
        if ADVISOR is None or not STATE["names"]:
            return {"err": "tavolo non configurato"}
        ctx = contesto_piani()
        slot_a = view_for_me("A").me.slots_left(STATE["quotas"], "A")
        if slot_a <= 0:
            # nessun attaccante da imporre: le alternative sarebbero tutte
            # «non fattibili» e il motivo sembrerebbe la cassa
            quanti = 0
        chiave = ("piani", ctx.chiave(), quanti)
        if chiave in PIANI_CACHE:
            return {**PIANI_CACHE[chiave], "dalla_cache": True,
                    "versione_stato": versione_stato()}
        versione = versione_stato()
    fuori = pn.costruisci_piani(ctx, info_breve, quanti=quanti)
    if slot_a <= 0 and fuori.get("stato") == "ok":
        fuori["nota_vincolo"] = ("reparto attaccanti completo: nessuna "
                                 "alternativa di bomber da mostrare, resta il "
                                 "piano di riferimento")
    fuori["versione_stato"] = versione
    fuori["budget_residuo"] = ctx.budget
    with LOCK:
        if versione == versione_stato():
            PIANI_CACHE.clear()      # una sola chiave viva: lo stato e' uno solo
            PIANI_CACHE[chiave] = fuori
        else:
            fuori["superato"] = True
    return {**fuori, "dalla_cache": False}


def piano_prezzo(pid: str, prezzo: float) -> dict:
    if ADVISOR is None or not STATE["names"]:
        return {"err": "tavolo non configurato"}
    miei = {q for r, ids in view_for_me().me.roster.items() for q, _ in ids}
    if pid in miei:
        return {"err": "e' gia' tuo: non si compra due volte"}
    if pid not in pool():
        return {"err": "non e' nel pool: venduto, fuori lista o escluso da te"}
    ctx = contesto_piani()
    fuori = pn.piano_al_prezzo(ctx, pid, prezzo, info_breve)
    fuori["versione_stato"] = versione_stato()
    return fuori


def nominate(role: str) -> dict:
    if ADVISOR is None or not STATE["names"]:
        return {"err": "tavolo non configurato"}
    v = view_for_me(role)
    if v.me.slots_left(v.quotas, role) <= 0:
        return {"consiglio": "reparto pieno", "esca": None, "riempitivo": None}
    d = ADVISOR.nominate(v)
    p = PACK.players[d.player_id]
    kind = "esca" if "fatevi male" in d.thought else "riempitivo"
    return {"consiglio": d.thought, "tipo": kind, "giocatore": player_info(p.player_id),
            "apertura": d.opening_bid}


# ------------------------------------------------------------ http
class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _send(self, obj, code=200):
        body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        # Chrome «Private Network Access»: una pagina pubblica in https (per
        # esempio FantaAsta Live) puo' chiamare 127.0.0.1 solo se il preflight
        # lo dichiara. Serve al ponte che registra i martelletti da quella pagina.
        self.send_header("Access-Control-Allow-Private-Network", "true")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self):
        self._send({})

    def do_GET(self):
        # Un parametro storto non deve chiudere la connessione: prima
        # `int("abc")` usciva dal gestore e la pagina vedeva «Copilota non
        # raggiungibile» per un errore di battitura
        try:
            self._get()
        except Exception as exc:                                  # noqa: BLE001
            print(f"  richiesta GET non valida {self.path}: {exc}")
            try:
                self._send({"err": f"richiesta non valida: {exc}"}, 400)
            except Exception:                                     # noqa: BLE001
                pass

    def do_POST(self):
        try:
            self._post()
        except Exception as exc:                                  # noqa: BLE001
            print(f"  errore POST {self.path}: {exc}")
            try:
                self._send({"ok": False, "err": f"errore interno: {exc}"}, 500)
            except Exception:                                     # noqa: BLE001
                pass

    def _get(self):
        u = urlparse(self.path)
        q = {k: v[0] for k, v in parse_qs(u.query).items()}
        if u.path == "/copilot/piani":
            # fuori dal lock: `piani_alternativi` lo prende da se' per i soli
            # istanti in cui legge e scrive lo stato, e il MILP gira libero
            try:
                quanti = int(q.get("quanti") or 6)
            except (TypeError, ValueError):
                return self._send({"err": "«quanti» non e' un numero"}, 400)
            return self._send(piani_alternativi(min(max(quanti, 1), 8)))
        with LOCK:
            if u.path == "/copilot/bundle":
                rif = ROOT / "data" / "packs" / "CORRENTE.json"
                c = ELEGGIBILITA.get("conteggi", {}) or {}
                fuori = {"sessione": STATE.get("bundle"),
                         "cambiato": STATE.get("bundle_cambiato"),
                         "eleggibilita": {
                             "attivo": ELEGGIBILITA.get("attivo", False),
                             "motivo": ELEGGIBILITA.get("motivo", ""),
                             "acquisito": ELEGGIBILITA.get("acquisito"),
                             "pool": c.get("attivi_nel_pack"),
                             "esclusi": len(ELEGGIBILITA.get("esclusi", ())),
                             "indisponibili": c.get("indisponibili"),
                             "senza_previsione": c.get("attivi_non_nel_pack"),
                             "con_prezzo_di_mercato": c.get("con_prezzo_di_mercato"),
                             "semantica_prezzo": ELEGGIBILITA.get("semantica_prezzo", "")}}
                if rif.exists():
                    try:
                        fuori["corrente"] = json.loads(rif.read_text("utf-8"))
                    except (OSError, json.JSONDecodeError):
                        fuori["corrente"] = None
                return self._send(fuori)
            if u.path == "/copilot/export":
                # Il registro completo, leggibile senza rete e senza il
                # server: e' la copia che resta se qualcosa si spegne.
                ts = teams()
                c = ELEGGIBILITA.get("conteggi", {}) or {}
                return self._send({
                    "esportato": datetime.datetime.now().isoformat(timespec="seconds"),
                    "stagione": STATE.get("season"),
                    "bundle": STATE.get("bundle"),
                    "fonti": {"acquisito": ELEGGIBILITA.get("acquisito"),
                              "pool": c.get("attivi_nel_pack"),
                              "fuori_serie_a_esclusi": len(ELEGGIBILITA.get("esclusi", ())),
                              "indisponibili": c.get("indisponibili"),
                              "semantica_prezzo": ELEGGIBILITA.get("semantica_prezzo", "")},
                    "regole": {"squadre": len(STATE["names"]),
                               "budget": STATE["budget"],
                               "quote": STATE["quotas"]},
                    "io": STATE.get("my_index"),
                    "squadre": [
                        {"indice": i, "nome": t.bot_name, "budget_residuo": t.budget,
                         "speso": STATE["budget"] - t.budget,
                         "rosa": {r: [{**player_info(pid), "prezzo": pr}
                                      for pid, pr in t.roster[r]] for r in ROLES}}
                        for i, t in enumerate(ts)],
                    "acquisti": [{**player_info(e["player_id"]),
                                  "squadra_indice": e["team_index"],
                                  "squadra": STATE["names"][e["team_index"]],
                                  "prezzo": e["price"], "ts": e.get("ts")}
                                 for e in STATE["events"]],
                    "rilanci_osservati": STATE.get("bids", []),
                    "esclusi_manuali": [info_breve(q) for q in STATE.get("esclusi_manuali") or []
                                        if q in PACK.players],
                    "rettifiche_indisponibili": {
                        PACK.players[q].name: r for q, r in RETTIFICHE.items()
                        if q in PACK.players},
                    "note_esperto": NOTE_ESPERTO.get("meta", {}),
                    "rettifica_motivo": RETTIFICA_MOTIVO,
                    "listino_consultabile": [
                        {**player_info(pid),
                         "prezzo_mercato_10sq_500": (ELEGGIBILITA.get("prezzi") or {}).get(pid),
                         "fuori_serie_a": pid in ELEGGIBILITA.get("esclusi", ()),
                         "indisponibile": (ELEGGIBILITA.get("indisponibili") or {}).get(pid),
                         "venduto_a": next((STATE["names"][e["team_index"]]
                                            for e in STATE["events"]
                                            if e["player_id"] == pid), None)}
                        for pid in sorted(PACK.players)],
                    "nota": (
                        "i limiti iniziali (prezzi di riferimento, previsioni) "
                        "vengono dal bundle congelato all'inizio della "
                        "sessione; gli acquisti sono quelli registrati al "
                        "tavolo. Il prezzo di mercato e' un riferimento "
                        "aggregato, non un tetto.")})
            if u.path == "/copilot/state":
                ts = teams() if STATE["names"] else []
                self._send({
                    "season": STATE["season"], "names": STATE["names"],
                    "my_index": STATE["my_index"], "budget": STATE["budget"],
                    "quotas": STATE["quotas"], "n_events": len(STATE["events"]),
                    "n_bids": len(STATE.get("bids", [])),
                    "last_bids": [{**player_info(b["player_id"]), "team_index": b["team_index"],
                                   "price": b["price"], "fonte": b["fonte"], "lot": b["lot"]}
                                  for b in STATE.get("bids", [])[-15:]],
                    "ledger": str(LEDGER_PATH) if LEDGER_PATH else None,
                    "ripreso_da_copia": RIPRESO_DA_COPIA,
                    "esclusi_manuali": [info_breve(q) for q in STATE.get("esclusi_manuali") or []
                                        if q in PACK.players],
                    "rettifiche_indisponibili": len(RETTIFICHE),
                    "rettifica_motivo": RETTIFICA_MOTIVO,
                    "teams": [{"index": i, "name": t.bot_name, "budget": t.budget,
                               # con la rosa piena `max_bid` darebbe budget+1
                               "max_bid": (t.max_bid(STATE["quotas"])
                                           if t.slots_left(STATE["quotas"]) > 0 else 0),
                               "roster": {r: [{**player_info(pid), "prezzo": pr}
                                              for pid, pr in t.roster[r]] for r in ROLES}}
                              for i, t in enumerate(ts)],
                    "pool_size": len(pool()),
                    "heat": round(ADVISOR.market_heat(), 2) if ADVISOR else 1.0,
                    # ultimi acquisti in ordine cronologico (ticker + label undo)
                    "last_events": [{**player_info(e["player_id"]), "team_index": e["team_index"],
                                     "price": e["price"], "ts": e.get("ts")}
                                    for e in STATE["events"][-15:]],
                })
            elif u.path == "/copilot/advice":
                pid = q.get("player_id")
                try:
                    price = (intero_valido(float(q["price"]), minimo=0)
                             if q.get("price") else None)
                except (ValueError, TypeError) as exc:
                    # prima `int("10.5")` sollevava e la connessione cadeva:
                    # la pagina vedeva «Copilota non raggiungibile»
                    return self._send({"err": f"prezzo: {exc}"}, 400)
                self._send(advice(pid, price) if pid in PACK.players else {"err": "id sconosciuto"})
            elif u.path == "/copilot/piano_prezzo":
                pid = q.get("player_id")
                if pid not in PACK.players:
                    return self._send({"err": "giocatore inesistente"}, 400)
                try:
                    prezzo = intero_valido(float(q.get("prezzo") or 1), minimo=1)
                except (ValueError, TypeError) as exc:
                    return self._send({"err": str(exc)}, 400)
                fuori = piano_prezzo(pid, prezzo)
                return self._send(fuori, 400 if fuori.get("err") else 200)
            elif u.path == "/copilot/plan":
                self._send(plan())
            elif u.path == "/copilot/nominate":
                ruolo = q.get("role", "A")
                if ruolo not in ROLES:
                    return self._send({"err": f"ruolo ignoto: {ruolo!r}"}, 400)
                self._send(nominate(ruolo))
            elif u.path == "/copilot/players":
                role, sq = q.get("role"), q.get("squadra")
                text = senza_accenti(q.get("q") or "").strip()
                # `tutti=1`: anche fuori lista ed esclusi, per registrare un
                # acquisto altrui che la lista non prevedeva
                tutti = str(q.get("tutti") or "") in ("1", "true", "si")
                out = [player_info(pid) for pid, p in pool(solo_eleggibili=not tutti).items()
                       if (not role or p.role == role) and (not sq or p.team == sq)
                       and (not text or text in senza_accenti(p.name))]
                if text:
                    # chi digita un nome vuole quel nome: prima chi comincia
                    # cosi', poi il nome piu' corto; il valore solo dopo.
                    # «martinez» + Invio portava al banco Lautaro anche se al
                    # banco c'era il portiere Martinez Jo.
                    out.sort(key=lambda x: (0 if senza_accenti(x["nome"]).startswith(text) else 1,
                                            len(x["nome"]), -(x["value"] or 0)))
                else:
                    out.sort(key=lambda x: -(x["value"] or 0))
                self._send(out[:80])
            elif u.path == "/copilot/rigoristi":
                self._send(rigoristi_ora())
            elif u.path == "/copilot/squadre":
                self._send(sorted({p.team for p in PACK.players.values()}))
            else:
                self._send({"err": "not found"}, 404)

    def _post(self):
        u = urlparse(self.path)
        n = int(self.headers.get("Content-Length", 0))
        try:
            body = json.loads(self.rfile.read(n) or b"{}")
        except json.JSONDecodeError:
            return self._send({"ok": False, "err": "bad json"}, 400)
        with LOCK:
            if u.path == "/copilot/setup":
                # stato CANDIDATO, validato per intero prima di diventare
                # corrente: prima si scriveva su disco e si scopriva dopo che
                # `my_index` non esisteva
                candidato = {**STATE,
                             "names": body.get("names", []),
                             "my_index": body.get("my_index", 0),
                             "budget": body.get("budget", STATE["budget"])}
                if body.get("quotas"):
                    candidato["quotas"] = body["quotas"]
                try:
                    nuovo = stato_valido(candidato)
                except (ValueError, KeyError, TypeError) as exc:
                    return self._send({"ok": False, "err": str(exc),
                                       "campo": "configurazione"}, 400)
                STATE.update(nuovo)
                save()
                rebuild_advisor()
                return self._send({"ok": True, "squadre": len(nuovo["names"]),
                                   "io": nuovo["my_index"]})
            if u.path == "/copilot/hammer":
                # TUTTO validato prima di toccare memoria o disco: un input
                # invalido non deve lasciare traccia. Prima `int(price)`
                # accettava -10 (cassa 500 -> 510), 0, e troncava 10,9 a 10.
                pid = body.get("player_id")
                richiesta = body.get("richiesta_id")
                if richiesta is not None:
                    gia = [e for e in STATE["events"]
                           if e.get("richiesta_id") == richiesta]
                    if gia:
                        # doppio clic o ritrasmissione: si risponde con lo
                        # stesso esito, senza registrare due volte
                        return self._send({"ok": True, "duplicato": True,
                                           "n_events": len(STATE["events"])})
                if not STATE["names"]:
                    return self._send({"ok": False, "err": "tavolo non configurato"}, 400)
                if pid not in PACK.players:
                    return self._send({"ok": False, "err": "giocatore inesistente"}, 400)
                if pid not in pool(solo_eleggibili=False):
                    return self._send({"ok": False,
                                       "err": "giocatore gia' aggiudicato"}, 400)
                fuori_lista = pid in ELEGGIBILITA["esclusi"]
                try:
                    ti = indice_valido(body.get("team_index"), len(STATE["names"]))
                    price = intero_valido(body.get("price"), minimo=1)
                except ValueError as exc:
                    return self._send({"ok": False, "err": str(exc)}, 400)
                ts = teams()
                p = PACK.players[pid]
                if ts[ti].slots_left(STATE["quotas"], p.role) <= 0:
                    return self._send({"ok": False, "err": f"{ts[ti].bot_name}: reparto {p.role} pieno"}, 400)
                massimo = int(ts[ti].max_bid(STATE["quotas"]))
                if price > massimo:
                    return self._send({
                        "ok": False,
                        "err": f"{ts[ti].bot_name}: {price} supera il massimo "
                               f"legale {massimo} (restano "
                               f"{ts[ti].slots_left(STATE['quotas'])} slot)"}, 400)
                evento = {"player_id": pid, "team_index": ti, "price": price,
                          "ts": time.time()}
                if richiesta is not None:
                    evento["richiesta_id"] = str(richiesta)
                STATE["events"].append(evento)
                try:
                    save()
                except OSError as exc:
                    STATE["events"].pop()
                    return self._send({"ok": False,
                                       "err": f"salvataggio fallito: {exc}"}, 500)
                # l'acquisto e' registrato: se il ricalcolo fallisce lo si dice,
                # ma il registro resta valido
                PIANI_CACHE.clear()   # lo stato e' cambiato: i piani vecchi
                                      # non sono piu' attuali
                consiglio_disponibile = True
                if ADVISOR is not None:
                    try:
                        ADVISOR.on_hammer(view_for_me(p.role), p, price, f"T{ti}")
                    except Exception as exc:                     # noqa: BLE001
                        consiglio_disponibile = False
                        print(f"  ricalcolo fallito dopo il martelletto: {exc}")
                note = []
                if not consiglio_disponibile:
                    note.append("registrato, consiglio temporaneamente non "
                                "disponibile")
                if fuori_lista:
                    note.append(
                        "questo giocatore risulta fuori dalla Serie A secondo "
                        "il listone: registrato perche' l'asta reale comanda, "
                        "ma non era fra i consigliabili")
                return self._send({
                    "ok": True, "n_events": len(STATE["events"]),
                    "consiglio_disponibile": consiglio_disponibile,
                    "fuori_lista": fuori_lista,
                    "nota": "; ".join(note) or None})
            if u.path == "/copilot/escludi":
                # «non lo voglio nel piano»: il giocatore resta registrabile
                # al martelletto, ma esce dal pool dei consigli e dal MILP.
                # E' una scelta tua, persistita nel ledger, reversibile.
                pid = body.get("player_id")
                if pid not in PACK.players:
                    return self._send({"ok": False, "err": "giocatore inesistente"}, 400)
                escluso = bool(body.get("escluso", True))
                lista = list(STATE.get("esclusi_manuali") or [])
                if escluso and pid not in lista:
                    lista.append(pid)
                if not escluso and pid in lista:
                    lista.remove(pid)
                STATE["esclusi_manuali"] = lista
                try:
                    save()
                except OSError as exc:
                    return self._send({"ok": False,
                                       "err": f"salvataggio fallito: {exc}"}, 500)
                PIANI_CACHE.clear()
                if ADVISOR is not None and STATE["names"]:
                    rebuild_advisor()
                return self._send({"ok": True, "escluso": escluso,
                                   "esclusi_manuali": [info_breve(q) for q in lista]})
            if u.path == "/copilot/undo":
                # `richiesta_id` rende l'annullamento ripetibile senza danno:
                # un doppio clic o una ritrasmissione non tolgono due acquisti
                richiesta = body.get("richiesta_id")
                fatti = STATE.setdefault("undo_fatti", [])
                if richiesta is not None and str(richiesta) in fatti:
                    return self._send({"ok": True, "duplicato": True,
                                       "n_events": len(STATE["events"])})
                PIANI_CACHE.clear()
                tolto = None
                if STATE["events"]:
                    tolto = STATE["events"].pop()
                    if richiesta is not None:
                        fatti.append(str(richiesta))
                        del fatti[:-50]
                    save()
                    rebuild_advisor()
                return self._send({"ok": True, "n_events": len(STATE["events"]),
                                   "annullato": tolto})
            if u.path == "/copilot/bid":
                # rilancio osservato: non tocca rose ne' budget (il lotto e'
                # ancora aperto), serve solo a registrare come si e' svolta
                # la contesa. L'aggiudicazione resta /copilot/hammer.
                pid, ti, price = body.get("player_id"), body.get("team_index"), body.get("price")
                fonte = str(body.get("fonte", "osservato"))
                if fonte not in FONTI_BID:
                    return self._send({"ok": False, "err": f"fonte ammesse: {FONTI_BID}"})
                if pid not in PACK.players:
                    return self._send({"ok": False, "err": "giocatore inesistente"})
                try:
                    ti = indice_valido(ti, len(STATE["names"]))
                    price = intero_valido(price, minimo=1)
                except ValueError as exc:
                    return self._send({"ok": False, "err": str(exc)}, 400)
                bids = STATE.setdefault("bids", [])
                aperti = [b["lot"] for b in bids if b["player_id"] == pid]
                lot = aperti[0] if aperti else (max([b["lot"] for b in bids], default=-1) + 1)
                bids.append({"lot": lot, "player_id": pid, "team_index": ti,
                             "price": price, "ts": time.time(), "fonte": fonte})
                save()
                return self._send({"ok": True, "n_bids": len(bids), "lot": lot})
            if u.path == "/copilot/undo_bid":
                bids = STATE.setdefault("bids", [])
                if bids:
                    bids.pop()
                    save()
                return self._send({"ok": True, "n_bids": len(bids)})
        self._send({"ok": False, "err": "not found"}, 404)


def load_pack(season: str):
    pkl = ROOT / "data" / "packs" / f"pack_{season}.pkl"
    if pkl.exists():
        with open(pkl, "rb") as f:
            return pickle.load(f)
    demo = ROOT / "demo" / f"pack_{season}_demo.json"
    if demo.exists():
        from fantabot.models import Player
        from fantabot.tournament import SeasonPack
        d = json.loads(demo.read_text(encoding="utf-8"))
        return SeasonPack(season=d["season"],
                          players={p["id"]: Player(p["id"], p["name"], p["role"], p["team"],
                                                   p["ref_price"], p["ref_price_sd"], p["exp_points"])
                                   for p in d["players"]},
                          votes_by_g=[], quotas=d["quotas"], budget=d["budget"],
                          b_predictions=d["b_predictions"], a_price_list=d["a_price_list"])
    raise SystemExit(f"nessun pack per {season}")


def blocca_ledger(percorso: Path) -> None:
    """Un solo Copilota per registro: il lock porta il PID di chi lo tiene.

    Due processi sullo stesso ledger si sovrascrivevano a vicenda a ogni
    salvataggio. Un lock di un processo morto si ignora (e si sostituisce)."""
    lock = percorso.with_suffix(".lock")
    if lock.exists():
        try:
            altro = int(lock.read_text(encoding="utf-8").strip() or 0)
        except (OSError, ValueError):
            altro = 0
        vivo = False
        if altro and altro != os.getpid():
            try:
                import psutil
                vivo = psutil.pid_exists(altro)
            except ImportError:
                vivo = False
        if vivo:
            raise SystemExit(
                f"{percorso.name} e' gia' aperto dal Copilota con PID {altro}: "
                "chiudi quello prima di riprendere lo stesso registro")
    lock.parent.mkdir(parents=True, exist_ok=True)
    lock.write_text(str(os.getpid()), encoding="utf-8")
    import atexit
    atexit.register(lambda: lock.exists() and lock.unlink())


if __name__ == "__main__":
    args = sys.argv[1:]
    season = next((a for a in args if a[0].isdigit()), "2026-27")
    porta = int(args[args.index("--porta") + 1]) if "--porta" in args else 8770
    # la porta si prende subito: se e' occupata lo si sa prima di caricare
    # il pack, con un messaggio e non con un traceback
    try:
        SERVER = ThreadingHTTPServer(("127.0.0.1", porta), Handler)
    except OSError as exc:
        raise SystemExit(f"porta {porta} non disponibile ({exc}): c'e' gia' un "
                         "Copilota o un altro processo. Fermalo o cambia porta")
    PACK = load_pack(season)
    ELEGGIBILITA = carica_eleggibilita(season)
    prepara_pack(season)
    if RETTIFICHE:
        print(f"  valore rettificato per {len(RETTIFICHE)} indisponibili "
              f"(giornate perse stimate dalle fonti del bundle)")
    if ELEGGIBILITA.get("senza_previsione"):
        print(f"  {len(ELEGGIBILITA['senza_previsione'])} attivi del listone senza "
              "previsione: registrabili, non consigliati")
    if ELEGGIBILITA["attivo"]:
        c = ELEGGIBILITA.get("conteggi", {})
        print(f"  eleggibilita': {len(ELEGGIBILITA['esclusi'])} fuori Serie A "
              f"esclusi dai consigli, pool {c.get('attivi_nel_pack')} "
              f"(fonti del {str(ELEGGIBILITA.get('acquisito'))[:10]})")
    else:
        print(f"  ATTENZIONE: nessun filtro di eleggibilita' "
              f"({ELEGGIBILITA['motivo']}). I consigli possono includere chi "
              "non gioca piu' in Serie A.")
    STATE["season"] = season
    STATE["quotas"] = dict(PACK.quotas)
    STATE["budget"] = PACK.budget
    if "--resume" in args:
        LEDGER_PATH = Path(args[args.index("--resume") + 1])
        salvato = carica_ledger(LEDGER_PATH)
        if salvato is None:
            raise SystemExit(
                f"{LEDGER_PATH.name} non e' leggibile, e non c'e' una copia "
                "buona accanto. Meglio fermarsi che ripartire da uno stato "
                "inventato: controlla il file, o apri una sessione nuova.")
        # La stagione del ledger comanda: se non e' quella passata alla riga di
        # comando, il pack caricato non e' quello dell'asta. Prima si teneva
        # l'etichetta del ledger e il pack dell'argomento — nomi giusti e dati
        # sbagliati.
        stagione_ledger = salvato.get("season")
        if stagione_ledger and stagione_ledger != season:
            print(f"  il ledger e' della stagione {stagione_ledger}, non "
                  f"{season}: ricarico il pack giusto")
            season = stagione_ledger
            PACK = load_pack(season)
        STATE.update(salvato)
        STATE["season"] = season
        STATE.setdefault("bids", [])   # ledger scritti prima del registro rilanci
        sconosciuti = [e["player_id"] for e in STATE["events"]
                       if e["player_id"] not in PACK.players]
        if sconosciuti:
            raise SystemExit(
                f"{len(sconosciuti)} acquisti del ledger non esistono in "
                f"pack_{season}.pkl (per esempio {sconosciuti[:3]}). Il bundle "
                "non e' quello con cui e' cominciata l'asta: recupera quel "
                "pack invece di proseguire con uno diverso.")
        atteso = STATE.get("bundle")
        adesso = identita_bundle()
        if atteso and atteso.get("impronta") and atteso["impronta"] != adesso["impronta"]:
            print("  ATTENZIONE: il pack e' cambiato dall'inizio della "
                  f"sessione ({atteso['impronta'][:12]} -> "
                  f"{adesso['impronta'][:12]}). I consigli useranno i dati "
                  "nuovi; gli acquisti registrati restano quelli.")
            STATE["bundle_cambiato"] = {"allora": atteso, "adesso": adesso}
        STATE["bundle"] = STATE.get("bundle") or adesso
        rebuild_advisor()
        print(f"Ripreso ledger {LEDGER_PATH.name}: {len(STATE['events'])} acquisti, "
              f"{len(STATE['bids'])} rilanci, pack {adesso['pack']} "
              f"({str(adesso['impronta'])[:12]})")
    else:
        if "--ledger" in args:
            # ledger esplicito: le prove stanno in `data/copilot/prove/`, non
            # fra le sessioni vere che il menu propone di riprendere
            LEDGER_PATH = Path(args[args.index("--ledger") + 1])
        else:
            LEDGER_PATH = ROOT / "data" / "copilot" / f"ledger_{int(time.time())}.json"
        # la sessione registra con quale bundle e' nata: e' il vincolo che
        # rende verificabile la ripresa
        STATE["bundle"] = identita_bundle()
    blocca_ledger(LEDGER_PATH)
    print(f"Copilota {season} su http://localhost:{porta} — ledger {LEDGER_PATH}")
    SERVER.serve_forever()
