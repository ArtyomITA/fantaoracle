# -*- coding: utf-8 -*-
"""Contratto temporale delle colonne di `players_{stagione}.parquet`.

`players_{stagione}.parquet` e' il listone su cui si addestrano i modelli di
prezzo e di presenze. Fino al 10/9/2026 nessun file dichiarava, colonna per
colonna, **a quale istante informativo** ciascuna appartiene: le 66 colonne
entravano nei modelli senza che si potesse dire se il valore fosse noto a chi
decideva all'asta oppure ricostruito dopo. I dieci `l2_panel_*.contratto.json`
coprono il pannello per giornata, non questo file.

Questo modulo costruisce quel contratto e lo scrive **accanto** al parquet, in
`data/processed/players_{stagione}.contratto.json`. Il parquet non viene
toccato: il contratto e' una dichiarazione, non una trasformazione.

## L'origine dipende dalla stagione e da k

`k` = giornate della stagione gia' concluse quando si decide (e' il campo `k`
di `b_predictions_{stagione}.json`). L'origine e':

    origine(stagione, k) = min(auction_date dichiarata in config/league.yaml,
                               data della prima partita della giornata k+1)

Il minimo, e non la sola data d'asta, perche' un backtest a k=0 dichiara di non
aver osservato nessuna giornata: un ingresso datato dopo la prima partita
contraddice quella dichiarazione anche se l'asta reale si e' tenuta piu' tardi
(nel 2024-25 l'asta dichiarata e' il 1/9, ma la giornata 1 si e' giocata il
17-19/8). Se `auction_date` non e' dichiarata per la stagione — al 10/9/2026 lo
e' solo per 2024-25 e 2025-26 — il contratto usa la sola data di calendario e lo
**dichiara** (`data_asta_dichiarata: null`): la verifica contro la data d'asta
reale li' non e' possibile, e non si inventa.

Conseguenza pratica, la stessa gia' scritta in `scripts/l1_presenze_per_origine.py`
e in `reports/livelli_20260910/L1.md`: `fvm` e `quot_fs_sett` sono
`posteriore_all_origine` nei backtest a k=0 e diventano
`disponibile_alla_decisione` per il 2026-27 con k=3, dove lo snapshot
fanta.soccer e' del 4/9/2026 e l'origine e' l'11/9/2026.

## Stato di una colonna derivata

E' il **peggiore** fra il proprio stato e quello delle colonne da cui dipende
(gravita' crescente: disponibile < ricostruito < non verificabile < posteriore).
`team_prev_xg` viene da Understat della stagione precedente — dato concluso e
databile — ma e' agganciato alla squadra dello snapshot fanta.soccer: eredita
quindi lo stato di `squadra`.

## Che cosa questo modulo NON fa

Non promuove un dato a disponibile perche' oggi si riesce a leggerlo: e' la
regola gia' scritta in `src/fantabot/tabellino/origine.py`. Una colonna
dichiarata `disponibile_alla_decisione` senza prova fa fallire la costruzione
(`Ingresso.__post_init__`).
"""
from __future__ import annotations

import hashlib
import json
import re
import sys
from datetime import datetime
from pathlib import Path

import pandas as pd

_SRC = Path(__file__).resolve().parents[1]
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from fantabot.tabellino.origine import (  # noqa: E402
    DISPONIBILE, NON_VERIFICABILE, POSTERIORE, RICOSTRUITO, Ingresso)

RADICE = Path(__file__).resolve().parents[2]
RAW = RADICE / "data" / "raw"
PROC = RADICE / "data" / "processed"
MATCH_DIR = PROC / "_match"
CONFIG = RADICE / "config" / "league.yaml"
COSTRUTTORE = RADICE / "scripts" / "f0b_build_outputs.py"

VERSIONE = "2026-09-10.contratto-players.1"

# gravita' crescente: il peggiore vince quando una colonna ne dipende da altre.
GRAVITA = {DISPONIBILE: 0, RICOSTRUITO: 1, NON_VERIFICABILE: 2, POSTERIORE: 3}

# ruolo della colonna nel file: identita' (chiave/anagrafica), feature, etichetta.
IDENTITA = "identita"
FEATURE = "feature"
ETICHETTA = "etichetta"


def peggiore(*stati: str) -> str:
    """Lo stato piu' grave fra quelli passati."""
    return max(stati, key=lambda s: GRAVITA[s])


def sha256_file(percorso: Path) -> str | None:
    """Impronta sha256 di un file, None se non esiste."""
    p = Path(percorso)
    if not p.exists():
        return None
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for blocco in iter(lambda: f.read(1 << 20), b""):
            h.update(blocco)
    return h.hexdigest()


def _rel(p: Path) -> str:
    try:
        return str(Path(p).resolve().relative_to(RADICE)).replace("\\", "/")
    except ValueError:
        return str(p).replace("\\", "/")


def _mtime(p: Path) -> str | None:
    p = Path(p)
    if not p.exists():
        return None
    return datetime.fromtimestamp(p.stat().st_mtime).date().isoformat()


def _stagioni_precedenti(stagione: str, quante: int = 3) -> list[str]:
    y = int(stagione[:4])
    return [f"{y-i}-{str(y-i+1)[-2:]}" for i in range(1, quante + 1)]


# ------------------------------------------------------------------ origine
def data_asta_dichiarata(stagione: str) -> tuple[str | None, str | None]:
    """`seasons.<stagione>.auction_date` da config/league.yaml, con la riga.

    Lettura testuale: `config/league.yaml` non e' letto da nessuno script del
    progetto e non c'e' un parser yaml fra le dipendenze; il formato del blocco
    `seasons:` e' fisso.
    """
    if not CONFIG.exists():
        return None, None
    righe = CONFIG.read_text(encoding="utf-8").splitlines()
    dentro = False
    corrente = None
    for i, r in enumerate(righe, start=1):
        if re.match(r"^seasons:\s*$", r):
            dentro = True
            continue
        if dentro and re.match(r"^\S", r):
            break
        if not dentro:
            continue
        m = re.match(r'^\s{2}"?([0-9]{4}-[0-9]{2})"?:\s*$', r)
        if m:
            corrente = m.group(1)
            continue
        m = re.match(r'^\s+auction_date:\s*"?([0-9]{4}-[0-9]{2}-[0-9]{2})"?', r)
        if m and corrente == stagione:
            return m.group(1), f"config/league.yaml:{i}"
    return None, None


def _partite() -> pd.DataFrame:
    return pd.read_parquet(PROC / "l2_partite.parquet")


def origine_stagione(stagione: str, k: int, partite: pd.DataFrame | None = None) -> dict:
    """Origine informativa della coppia (stagione, k) e come e' stata ricavata."""
    partite = _partite() if partite is None else partite
    d = partite[partite.stagione == stagione]
    date_g = pd.to_datetime(d[d.giornata == k + 1]["data"], errors="coerce")
    inizio_g = date_g.min()
    inizio_g = None if pd.isna(inizio_g) else inizio_g.date().isoformat()
    asta, riga = data_asta_dichiarata(stagione)
    candidati = [x for x in (asta, inizio_g) if x]
    origine = min(candidati) if candidati else None
    fine_k = None
    if k > 0:
        dk = pd.to_datetime(d[d.giornata == k]["data"], errors="coerce")
        if dk.notna().any():
            fine_k = dk.max().date().isoformat()
    return {
        "origine": origine,
        "origine_come": ("min(auction_date, prima partita giornata k+1)"
                         if asta and inizio_g else
                         ("prima partita giornata k+1" if inizio_g else
                          ("auction_date" if asta else "nessuna"))),
        "data_asta_dichiarata": asta,
        "fonte_data_asta": riga,
        "inizio_giornata_k_piu_1": inizio_g,
        "fine_giornata_k": fine_k,
        "avviso": (None if asta else
                   "config/league.yaml non dichiara seasons."
                   f"{stagione}.auction_date: l'origine viene dal calendario "
                   "(data/processed/l2_partite.parquet) e la verifica contro la "
                   "data d'asta reale non e' possibile"),
    }


# ------------------------------------------------------------------ date fonte
def _snapshot_fs(stagione: str) -> dict:
    """Giornata dello snapshot fanta.soccer e data di rilevazione dichiarata."""
    g = None
    fs = MATCH_DIR / "fs_snapshot.json"
    if fs.exists():
        g = json.load(open(fs, encoding="utf-8")).get(stagione, [None])[0]
    data = None
    dr = RAW / "quotazioni" / "fantasoccer_date_rilevazioni.csv"
    file_g = None
    if g is not None:
        file_g = RAW / "quotazioni" / f"fantasoccer_{stagione}_g{int(g):02d}.csv"
        if dr.exists():
            d = pd.read_csv(dr)
            r = d[(d.stagione == stagione) & (d.giornata == int(g))]
            if len(r):
                data = pd.to_datetime(r.data_rilevazione.iloc[0],
                                      format="%d/%m/%Y").date().isoformat()
    # data del dato = la piu' tarda fra rilevazione dichiarata e acquisizione
    acq = _mtime(file_g) if file_g else None
    date = [x for x in (data, acq) if x]
    return {"giornata": None if g is None else int(g),
            "data_rilevazione": data, "data_acquisizione": acq,
            "data": max(date) if date else None,
            "file": _rel(file_g) if file_g else None,
            "esiste": bool(file_g and file_g.exists())}


def _fine_stagione(stagione: str, partite: pd.DataFrame) -> str | None:
    d = pd.to_datetime(partite[partite.stagione == stagione]["data"], errors="coerce")
    if not d.notna().any():
        return None
    return d.max().date().isoformat()


def _max_valutazioni_tm(stagione: str) -> str | None:
    """Data massima fra le valutazioni Transfermarkt effettivamente usate.

    `scripts/f0b_build_outputs.py:380` tiene solo `date <= 1 settembre` e per
    ogni giocatore l'ultima: il massimo di quel sottoinsieme e' la data piu'
    tarda che puo' essere entrata nella colonna `tm_value_eur`.
    """
    f = RAW / "transfermarkt" / "transfermarkt_valuations_seriea.csv"
    if not f.exists():
        return None
    v = pd.read_csv(f, usecols=["date"], parse_dates=["date"])
    sept1 = pd.Timestamp(int(stagione[:4]), 9, 1)
    v = v[v.date <= sept1]
    if v.empty:
        return None
    return v.date.max().date().isoformat()


def date_fonte(stagione: str, partite: pd.DataFrame) -> dict:
    """Le date che decidono gli stati: una per fonte, tutte ricavate dai file."""
    y = int(stagione[:4])
    prevs = _stagioni_precedenti(stagione, 3)
    fonti = {
        "listone_fantacalcioit": {
            "file": _rel(RAW / "quotazioni" / f"fantacalcioit_{stagione}.csv"),
            "data": _mtime(RAW / "quotazioni" / f"fantacalcioit_{stagione}.csv"),
            "nota": "il file non porta una data interna: vale la data di "
                    "acquisizione (mtime)"},
        "snapshot_fantasoccer": _snapshot_fs(stagione),
        "valutazioni_tm": {
            "file": _rel(RAW / "transfermarkt" / "transfermarkt_valuations_seriea.csv"),
            "data": _max_valutazioni_tm(stagione),
            "nota": f"massima data <= {y}-09-01 fra le valutazioni usate"},
        "kader_tm": {
            "file": _rel(MATCH_DIR / f"map_tm_kader_{y}.csv"),
            "data": _mtime(MATCH_DIR / f"map_tm_kader_{y}.csv"),
            "esiste": (MATCH_DIR / f"map_tm_kader_{y}.csv").exists(),
            "nota": "valore di mercato corrente al momento dello scarico"},
        "aste_gruppoesperti": {
            "file": _rel(RAW / "gruppoesperti" / "aste_reali_tidy.csv"),
            "data": _mtime(RAW / "gruppoesperti" / "aste_reali_tidy.csv"),
            "nota": "esito delle aste reali della stagione stessa"},
        "wayback_prezzi": {
            "file": _rel(MATCH_DIR / "map_wayback.csv"),
            "data": _mtime(MATCH_DIR / "map_wayback.csv"),
            "nota": "prezzi stimati fantacalcio-online, stagione stessa"},
    }
    for i, p in enumerate(prevs, start=1):
        vf = RAW / "voti" / f"voti_{p}.csv"
        fonti[f"voti_prev{i}"] = {
            "stagione": p, "file": _rel(vf), "esiste": vf.exists(),
            "data": _fine_stagione(p, partite),
            "nota": "fine della stagione precedente (ultima partita a calendario)"}
    uf = RAW / "understat" / f"understat_players_{y-1}.csv"
    tf = RAW / "understat" / f"understat_teams_{y-1}.csv"
    fonti["understat_prev1"] = {
        "stagione": prevs[0], "file": _rel(uf), "file_squadre": _rel(tf),
        "esiste": uf.exists() and tf.exists(),
        "data": _fine_stagione(prevs[0], partite)}
    af = RAW / "transfermarkt" / "transfermarkt_appearances_seriea.csv"
    fonti["appearances_tm_prev1"] = {
        "stagione": prevs[0], "file": _rel(af), "esiste": af.exists(),
        "data": _fine_stagione(prevs[0], partite)}
    return fonti


# ------------------------------------------------------------------ colonne
def _stato_per_data(data: str | None, origine: str | None,
                    *, se_posteriore: str = POSTERIORE,
                    ragione_ignota: str = "") -> tuple[str, str]:
    """Confronto data della fonte contro origine. Ritorna (stato, motivo)."""
    if data is None:
        return NON_VERIFICABILE, (ragione_ignota or
                                  "la fonte non ha una data determinabile")
    if origine is None:
        return NON_VERIFICABILE, ("nessuna origine determinabile per la coppia "
                                  "(stagione, k)")
    if data <= origine:
        return DISPONIBILE, f"dato del {data}, non posteriore all'origine {origine}"
    return se_posteriore, f"dato del {data}, posteriore all'origine {origine}"


def _blocco_prev(stagione: str, i: int, fonti: dict, origine: str | None) -> tuple[str, str]:
    f = fonti[f"voti_prev{i}"]
    if not f["esiste"]:
        return NON_VERIFICABILE, (
            f"nessun file voti per la stagione {f['stagione']}: la colonna e' "
            "interamente NaN, non c'e' informazione da datare")
    return _stato_per_data(f["data"], origine)


def descrivi_colonne(stagione: str, k: int, origine: dict, fonti: dict) -> list[dict]:
    """Una voce per ogni colonna prodotta da `build_players`, con prova.

    I riferimenti `scripts/f0b_build_outputs.py:<riga>` sono al codice che
    produce la colonna; le date vengono da `date_fonte`.
    """
    o = origine["origine"]
    prevs = _stagioni_precedenti(stagione, 3)
    voci: list[dict] = []

    def agg(nome, stato, ruolo, prova, fonte, codice, *, dipende_da=(),
            data=None, nota=""):
        stati = [stato] + [v["stato"] for v in voci if v["nome"] in dipende_da]
        voci.append(dict(nome=nome, stato=peggiore(*stati), ruolo=ruolo,
                         prova=prova, fonte=fonte, codice=codice,
                         dipende_da=list(dipende_da), data_fonte=data,
                         stato_proprio=stato, nota=nota,
                         verificato_contro=("data_asta+calendario"
                                            if origine["data_asta_dichiarata"]
                                            else "calendario")))

    # --- listone fantacalcio.it (registry.csv)
    lst = fonti["listone_fantacalcioit"]
    st_lst, mot_lst = _stato_per_data(lst["data"], o, se_posteriore=RICOSTRUITO)
    prova_lst = (f"{mot_lst}; il listone {lst['file']} non ha storia: per una "
                 "stagione archiviata e' la versione corrente al momento dello "
                 "scarico")
    for nome, ruolo, nota in [
            ("master_id", IDENTITA, "chiave del giocatore nel registry, stabile"),
            ("nome", IDENTITA, "anagrafica"),
            ("ruolo", IDENTITA, "ruolo classic del listone"),
    ]:
        # identita': non cambia con l'origine (chiave e anagrafica)
        agg(nome, DISPONIBILE, ruolo,
            "chiave/anagrafica del listone, invariante rispetto all'origine "
            f"(fonte {lst['file']}, scaricata il {lst['data']})",
            lst["file"], "scripts/f0b_lib.py:load_registry", nota=nota)
    agg("squadra_listone", st_lst, FEATURE, prova_lst, lst["file"],
        "scripts/f0b_build_outputs.py:345",
        nota="squadra secondo il listone fantacalcio.it della stagione")
    agg("qt_i", st_lst, FEATURE,
        f"{mot_lst}; `qt_i` e' per costruzione la quotazione INIZIALE della "
        "stagione e non cambia in corso d'anno, ma il file da cui si legge non "
        "ha storia",
        lst["file"], "scripts/f0b_lib.py:load_registry")
    # fvm: valore corrente, cambia durante la stagione -> non ricostruzione ma esito
    st_fvm, mot_fvm = _stato_per_data(lst["data"], o)
    agg("fvm", st_fvm, FEATURE,
        f"{mot_fvm}; `fvm` e' il valore di mercato CORRENTE del listone e cambia "
        "durante la stagione: sul 2024-25 il rho di rango con la quotazione di "
        "fine campionato e' 0,900 contro 0,708 con quella iniziale "
        "(scripts/l1_presenze_per_origine.py:66-99, reports/livelli_20260910/L1.md)",
        lst["file"], "scripts/f0b_lib.py:load_registry")

    # --- snapshot fanta.soccer
    fs = fonti["snapshot_fantasoccer"]
    if not fs["esiste"]:
        st_fs, mot_fs = NON_VERIFICABILE, "snapshot fanta.soccer assente per la stagione"
        st_q = NON_VERIFICABILE
    else:
        st_fs, mot_fs = _stato_per_data(fs["data"], o, se_posteriore=RICOSTRUITO)
        st_q, _ = _stato_per_data(fs["data"], o)
    prova_fs = (f"snapshot fanta.soccer giornata {fs['giornata']}, rilevazione "
                f"{fs['data_rilevazione']}, file {fs['file']} acquisito il "
                f"{fs['data_acquisizione']}; {mot_fs}. Se posteriore, la squadra "
                "e' un fatto di rosa ricostruito dopo l'origine "
                "(ricostruzione_retrospettiva), non un esito della stagione")
    agg("squadra", st_fs, FEATURE, prova_fs, fs["file"],
        "scripts/f0b_build_outputs.py:358-365",
        nota="squadra dello snapshot fanta.soccer, con ripiego sul listone")
    agg("squadra_fonte", st_fs, IDENTITA,
        prova_fs + " (indica quale delle due fonti ha vinto)", fs["file"],
        "scripts/f0b_build_outputs.py:366")
    agg("quot_fs_sett", st_q,
        FEATURE,
        f"quotazione dello snapshot fanta.soccer di giornata {fs['giornata']} "
        f"({fs['data_rilevazione']}): incorpora le giornate gia' giocate della "
        f"stagione da predire. Origine {o}, k={k}. "
        "scripts/f0b_match.py:475-482 sceglie la giornata per distanza dal 1/9",
        fs["file"], "scripts/f0b_build_outputs.py:367")

    # --- transfermarkt: eta' e valore
    kad = fonti["kader_tm"]
    val = fonti["valutazioni_tm"]
    st_eta, mot_eta = _stato_per_data(kad["data"] if kad["esiste"] else None, o,
                                      ragione_ignota="")
    if not kad["esiste"]:
        st_eta, mot_eta = DISPONIBILE, ("data di nascita da "
                                        "transfermarkt_players.csv: invariante")
    agg("eta", DISPONIBILE if not kad["esiste"] else peggiore(DISPONIBILE, st_eta),
        FEATURE,
        "eta' al 1 settembre da data di nascita (map_tm.csv). "
        + (f"Per questa stagione i NaN sono riempiti dalla rosa TM "
           f"{kad['file']} acquisita il {kad['data']}: {mot_eta}"
           if kad["esiste"] else "Nessun riempimento da rosa TM per questa stagione"),
        "data/processed/_match/map_tm.csv",
        "scripts/f0b_build_outputs.py:370-379,386-402")
    st_val, mot_val = _stato_per_data(val["data"], o)
    if kad["esiste"]:
        st_k, _ = _stato_per_data(kad["data"], o)
        st_val = peggiore(st_val, st_k)
    agg("tm_value_eur", st_val, FEATURE,
        f"valutazioni Transfermarkt filtrate a `date <= {stagione[:4]}-09-01` "
        f"(scripts/f0b_build_outputs.py:380); la piu' tarda effettivamente "
        f"utilizzabile e' del {val['data']}: {mot_val}"
        + (f". I NaN sono riempiti dalla rosa TM {kad['file']} "
           f"({kad['data']}), valore di mercato corrente" if kad["esiste"] else ""),
        val["file"], "scripts/f0b_build_outputs.py:376-402")

    # --- flag
    st_p1, mot_p1 = _blocco_prev(stagione, 1, fonti, o)
    agg("nuovo_in_serie_a", st_p1, FEATURE,
        f"presenza nei voti delle tre stagioni precedenti {prevs} (e Understat "
        f"2019/2020 per le piu' vecchie): {mot_p1}",
        fonti["voti_prev1"]["file"], "scripts/f0b_build_outputs.py:407")
    agg("squadra_neopromossa", st_lst, FEATURE,
        f"squadra del listone confrontata con le squadre di {prevs[0]} nel "
        f"registry: {mot_lst}",
        lst["file"], "scripts/f0b_build_outputs.py:408-410",
        dipende_da=("squadra_listone",))
    agg("cambio_squadra", st_fs, FEATURE,
        "squadra all'asta (snapshot fanta.soccer) confrontata con quella del "
        f"listone {prevs[0]}: eredita lo stato di `squadra`. {mot_fs}",
        fs["file"], "scripts/f0b_build_outputs.py:413-416",
        dipende_da=("squadra",))

    # --- storico voti prev1/2/3
    campi = ["fantamedia", "media_voto", "presenze", "gol", "assist",
             "rig_segnati", "rig_sbagliati", "ammonizioni"]
    stati_prev = {}
    for i in (1, 2, 3):
        st_i, mot_i = _blocco_prev(stagione, i, fonti, o)
        stati_prev[i] = st_i
        for c in campi:
            agg(f"prev{i}_{c}", st_i, FEATURE,
                f"aggregato dai voti di {prevs[i-1]} "
                f"({fonti[f'voti_prev{i}']['file']}): {mot_i}",
                fonti[f"voti_prev{i}"]["file"],
                "scripts/f0b_build_outputs.py:421-429")

    # --- understat giocatori stagione precedente
    us = fonti["understat_prev1"]
    if us["esiste"]:
        st_us, mot_us = _stato_per_data(us["data"], o)
    else:
        st_us, mot_us = NON_VERIFICABILE, "file Understat della stagione precedente assente"
    for c in ["us_prev_xg", "us_prev_xa", "us_prev_npxg", "us_prev_shots",
              "us_prev_minutes", "us_prev_xg90"]:
        agg(c, st_us, FEATURE,
            f"Understat {prevs[0]} ({us['file']}): {mot_us}",
            us["file"], "scripts/f0b_build_outputs.py:461-473")
    agg("team_prev_xg", peggiore(st_us, st_fs), FEATURE,
        f"xG di squadra {prevs[0]} ({us.get('file_squadre')}) agganciato alla "
        f"squadra dello snapshot: {mot_us}; eredita lo stato di `squadra`",
        us.get("file_squadre"), "scripts/f0b_build_outputs.py:479-484",
        dipende_da=("squadra",))

    # --- target (etichette: esito d'asta della stagione stessa)
    aste = fonti["aste_gruppoesperti"]
    way = fonti["wayback_prezzi"]
    for sfx, spiega in [
            ("10x500_estiva", "aste estive (periodo<=1) 10 squadre 400-600 crediti"),
            ("all_estiva", "aste estive (periodo<=1), tutte le configurazioni"),
            ("tardiva", "aste tenute a campionato iniziato (periodo>=2)")]:
        for p in ["n_obs", "mean_pct", "std_pct"]:
            agg(f"target_{p}_{sfx}", POSTERIORE, ETICHETTA,
                f"prezzi osservati nelle {spiega} della stagione {stagione}: "
                "sono l'esito che il modello deve prevedere, quindi posteriori "
                f"all'origine {o} per costruzione (file {aste['file']}, "
                f"acquisito il {aste['data']})",
                aste["file"], "scripts/f0b_build_outputs.py:143-205")
    agg("target_wayback_p500_10sq", POSTERIORE, ETICHETTA,
        "prezzo stimato fantacalcio-online per la stagione stessa, usato come "
        "bersaglio di ripiego nella gerarchia dei target "
        "(scripts/f0b_build_outputs.py:182-187): esito, non ingresso "
        f"(file {way['file']}, acquisito il {way['data']})",
        way["file"], "scripts/f0b_build_outputs.py:182-187")

    # --- stage S4
    ap = fonti["appearances_tm_prev1"]
    if ap["esiste"]:
        st_ap, mot_ap = _stato_per_data(ap["data"], o)
    else:
        st_ap, mot_ap = NON_VERIFICABILE, "dump appearances Transfermarkt assente"
    for c in ["tm_prev_min_per_app", "tm_prev_share90"]:
        agg(c, st_ap, FEATURE,
            f"minuti Serie A (IT1) della stagione {prevs[0]} da {ap['file']}: "
            f"{mot_ap}", ap["file"], "scripts/f0b_build_outputs.py:432-440")
    agg("prev1_pres_last10", stati_prev[1], FEATURE,
        f"presenze con voto dalla giornata 29 di {prevs[0]} "
        f"({fonti['voti_prev1']['file']}): {_blocco_prev(stagione, 1, fonti, o)[1]}",
        fonti["voti_prev1"]["file"], "scripts/f0b_build_outputs.py:249-251")
    st_disc = peggiore(stati_prev[1], stati_prev[2], stati_prev[3])
    for c in ["amm_pp_w", "esp_pp_w", "squal_att"]:
        agg(c, st_disc, FEATURE,
            "medie disciplinari pesate 3/2/1 sulle tre stagioni precedenti "
            f"{prevs}: stato = il peggiore dei tre blocchi prev",
            fonti["voti_prev1"]["file"], "scripts/f0b_build_outputs.py:445-453")
    for c, riga in [("team_prev_xga", "scripts/f0b_build_outputs.py:485-490"),
                    ("team_prev_xpts", "scripts/f0b_build_outputs.py:485-490")]:
        agg(c, peggiore(st_us, st_fs), FEATURE,
            f"xGA/xPts di squadra {prevs[0]} agganciati alla squadra dello "
            f"snapshot: {mot_us}; eredita lo stato di `squadra`",
            us.get("file_squadre"), riga, dipende_da=("squadra",))
    agg("team_prev_cs", peggiore(stati_prev[1], st_fs), FEATURE,
        f"porte inviolate reali di {prevs[0]} dai voti raw, agganciate alla "
        "squadra dello snapshot: eredita lo stato di `squadra`",
        fonti["voti_prev1"]["file"], "scripts/f0b_build_outputs.py:491",
        dipende_da=("squadra",))
    agg("rig_tirati_prev1", stati_prev[1], FEATURE,
        f"rigori segnati + sbagliati in {prevs[0]} dai voti raw",
        fonti["voti_prev1"]["file"], "scripts/f0b_build_outputs.py:456")
    agg("rigorista_1_prev", stati_prev[1], FEATURE,
        f"primo tiratore di rigori della propria squadra in {prevs[0]} dai voti "
        "raw (scripts/f0b_build_outputs.py:296-309)",
        fonti["voti_prev1"]["file"], "scripts/f0b_build_outputs.py:458-459")
    return voci


# ------------------------------------------------------------------ contratto
def _k_dichiarato(stagione: str) -> int | None:
    """`k` dal file di predizioni della stagione, se c'e'."""
    f = PROC / f"b_predictions_{stagione}.json"
    if not f.exists():
        return None
    try:
        d = json.load(open(f, encoding="utf-8"))
        for v in (d.values() if isinstance(d, dict) else d):
            if isinstance(v, dict) and "k" in v:
                return int(v["k"])
    except Exception:
        return None
    return None


def costruisci_contratto(stagione: str, k: int | None = None,
                         parquet: Path | None = None) -> dict:
    """Contratto temporale delle colonne di `players_{stagione}.parquet`.

    `k` non passato = quello dichiarato in `b_predictions_{stagione}.json`, 0 se
    il file non c'e'. Il parquet viene solo LETTO, per l'elenco delle colonne e
    per l'impronta.
    """
    if k is None:
        k = _k_dichiarato(stagione)
        k_da = "b_predictions" if k is not None else "assenza di b_predictions (0)"
        k = 0 if k is None else k
    else:
        k_da = "argomento esplicito"
    parquet = Path(parquet) if parquet else (PROC / f"players_{stagione}.parquet")
    if not parquet.exists():
        # senza il parquet non si sa quali colonne descrivere: un contratto
        # costruito sulle sole regole sarebbe una dichiarazione su un file che
        # non esiste.
        raise FileNotFoundError(f"manca {parquet}: nessun contratto da costruire")
    partite = _partite()
    orig = origine_stagione(stagione, k, partite)
    fonti = date_fonte(stagione, partite)
    voci = descrivi_colonne(stagione, k, orig, fonti)

    df = pd.read_parquet(parquet)
    colonne_file, righe = list(df.columns), int(len(df))
    # una colonna che il parquet ha e le regole non descrivono non si nasconde:
    # entra nel contratto come non verificabile, cosi' la prova di copertura la
    # vede e qualcuno la chiude.
    descritte = {v["nome"] for v in voci}
    for c in [x for x in colonne_file if x not in descritte]:
        voci.append(dict(nome=c, stato=NON_VERIFICABILE, ruolo=FEATURE,
                         prova="colonna presente nel parquet e non descritta da "
                               "nessuna regola di questo modulo: origine non "
                               "ricavata dal codice",
                         fonte=None, codice=None, dipende_da=[],
                         data_fonte=None, stato_proprio=NON_VERIFICABILE,
                         nota="colonna non riconosciuta", verificato_contro=None))
    # e una regola senza colonna nel parquet non deve restare nel contratto
    voci = [v for v in voci if v["nome"] in set(colonne_file)]
    ordine = {c: i for i, c in enumerate(colonne_file)}
    voci.sort(key=lambda v: ordine[v["nome"]])

    # validazione con il contratto di origine.py: DISPONIBILE senza prova = errore
    ingressi = [Ingresso(nome=v["nome"], stato=v["stato"], prova=v["prova"] or "",
                         fonte=v["fonte"] or "", data_pubblicazione=v["data_fonte"])
                for v in voci]
    conteggio = {}
    for i in ingressi:
        conteggio[i.stato] = conteggio.get(i.stato, 0) + 1

    impronte = {}
    for chiave, f in fonti.items():
        p = f.get("file")
        if p:
            impronte[p] = sha256_file(RADICE / p)
    for p in [f"data/processed/players_{stagione}.parquet",
              "data/processed/registry.csv", "data/processed/price_targets.csv",
              "data/processed/l2_partite.parquet"]:
        impronte[p] = sha256_file(RADICE / p)

    contratto = {
        "stagione": stagione,
        "k": k,
        "k_da": k_da,
        "origine": orig["origine"],
        "origine_come": orig["origine_come"],
        "data_asta_dichiarata": orig["data_asta_dichiarata"],
        "fonte_data_asta": orig["fonte_data_asta"],
        "inizio_giornata_k_piu_1": orig["inizio_giornata_k_piu_1"],
        "fine_giornata_k": orig["fine_giornata_k"],
        "avviso_data_asta": orig["avviso"],
        "as_of": datetime.now().isoformat(timespec="seconds"),
        "versione": VERSIONE,
        "versione_codice": {
            "scripts/f0b_build_outputs.py": sha256_file(COSTRUTTORE),
            "src/fantabot/contratto_players.py": sha256_file(Path(__file__)),
        },
        "parquet": _rel(parquet),
        "righe": righe,
        "n_colonne": len(voci),
        "conteggio_stati": conteggio,
        "stati_ammessi": [DISPONIBILE, RICOSTRUITO, NON_VERIFICABILE, POSTERIORE],
        "date_fonte": fonti,
        "impronte": impronte,
        "colonne": voci,
    }
    testo = json.dumps(contratto, ensure_ascii=False, sort_keys=True)
    contratto["impronta"] = hashlib.sha256(testo.encode("utf-8")).hexdigest()
    return contratto


def scrivi_contratto(stagione: str, k: int | None = None,
                     parquet: Path | None = None,
                     cartella: Path | None = None) -> Path:
    """Scrive `players_{stagione}.contratto.json` accanto al parquet."""
    c = costruisci_contratto(stagione, k=k, parquet=parquet)
    cartella = Path(cartella) if cartella else PROC
    cartella.mkdir(parents=True, exist_ok=True)
    fuori = cartella / f"players_{stagione}.contratto.json"
    fuori.write_text(json.dumps(c, ensure_ascii=False, indent=1), encoding="utf-8")
    return fuori


def main(argv=None):
    import argparse
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("stagioni", nargs="+")
    ap.add_argument("--k", type=int, default=None)
    ap.add_argument("--cartella", default=None)
    a = ap.parse_args(argv)
    for s in a.stagioni:
        p = scrivi_contratto(s, k=a.k, cartella=a.cartella)
        c = json.load(open(p, encoding="utf-8"))
        print(f"{p.name}: {c['n_colonne']} colonne, origine {c['origine']} "
              f"(k={c['k']}), {c['conteggio_stati']}")


if __name__ == "__main__":
    main()
