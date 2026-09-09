# -*- coding: utf-8 -*-
"""Livello 4 — fase 8A: unita' di osservazione e inventario delle aste reali.

Costruisce e verifica l'identita' globale di un'asta reale a partire dalla tabella
tidy `data/raw/gruppoesperti/aste_reali_tidy.csv`, quantifica duplicati e versioni
sovrapposte, produce l'inventario per asta e misura i due bersagli distinti
(martelletto individuale contro prezzo medio fra aste).

Lo script e' in sola lettura sugli input. Scrive solo dentro `data/l4/`.

Uso:
    set PYTHONPATH=src
    python scripts/l4_inventario_aste.py [--outdir data/l4] [--boot 1000] [--seed 20260908]

Artefatti prodotti in `data/l4/`:
    l4_inventario_aste.csv     una riga per (source_file, auction_id) con la sua
                               chiave globale, la configurazione e la copertura ruoli
    l4_aste_uniche.csv         una riga per asta reale (cluster di contenuto)
    l4_coppie_sospette.csv     tutte le coppie con sovrapposizione di prezzi >= SOGLIA_ISPEZIONE
    l4_prezzi_per_giocatore.csv statistiche del prezzo per (stagione, ruolo, giocatore)
    l4_inventario.json         tutte le misure, le impronte degli input e i parametri

Convenzioni:
  - "riga" = un acquisto (giocatore, prezzo) dentro un foglio d'asta;
  - "asta di file" = coppia (source_file, auction_id), l'unita' cosi' come e' scritta;
  - "asta reale" = cluster di aste di file riconosciute come lo stesso evento.
"""
from __future__ import annotations

import argparse
import hashlib
import itertools
import json
import platform
import re
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
TIDY = ROOT / "data" / "raw" / "gruppoesperti" / "aste_reali_tidy.csv"
BUILD_STATS = ROOT / "data" / "raw" / "gruppoesperti" / "build_stats.json"
MAP_GE = ROOT / "data" / "processed" / "_match" / "map_ge.csv"   # solo riscontro, opzionale

# Stagione stimata per file sorgente. Copiata da scripts/f0b_match.py (GE_FILE_SEASON),
# che a sua volta la ricava dai marcatori di rosa annotati in
# data/raw/gruppoesperti/REPORT.md. E' una stima per FILE, non per asta: vedi il
# limite dichiarato nel report di Livello 4.
GE_FILE_SEASON = {
    "gruppoesperti_prezzi_aste_reali_2024-25.xlsx": "2024-25",
    "gruppoesperti_prezzi_aste_reali_2021-22circa.xlsx": "2021-22",
    "extra/1Uxv42LC7d68Y1ZLQ48Hh1ud74kJocO-lTom39eJFB_w.xlsx": "2024-25",
    "extra/1MeKG7yjCemQ1SFoi7RWmhni-iBMtYdPf9FtfdDQWZ5I.xlsx": "2023-24",
    "extra/1J4tILPqyErS5Ccpr0Dy-595D2PgubYxlPaqfX8-pjYw.xlsx": "2024-25",
}

# Soglia di sovrapposizione dei prezzi oltre la quale due aste di file sono
# dichiarate lo stesso evento. Il valore non e' scelto a priori: lo script misura
# l'intera distribuzione delle sovrapposizioni e verifica che la soglia cada in un
# intervallo VUOTO, dove qualunque valore produce la stessa partizione. Se
# l'intervallo vuoto non c'e', lo script lo dichiara e il numero di aste uniche
# resta condizionato alla soglia.
SOGLIA_DUP = 0.70
GAP_MIN, GAP_MAX = 0.30, 0.80    # intervallo che deve risultare vuoto
SOGLIA_ISPEZIONE = 0.20          # coppie salvate su file per ispezione manuale

# Configurazione della nostra lega (dichiarata dal committente, non misurata).
LEGA_COMPONENTI = 10
LEGA_CREDITI = 500
LEGA_QUOTE = {"P": 3, "D": 8, "C": 8, "A": 6}
LEGA_MODIFICATORE_ATTIVO = True

RUOLI = ("P", "D", "C", "A")


# --------------------------------------------------------------------------- utilita'
def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for blocco in iter(lambda: fh.read(1 << 20), b""):
            h.update(blocco)
    return h.hexdigest()


def normalizza_nome(s: str) -> str:
    """Normalizzazione minima e conservativa del nome grezzo.

    Minuscolo, ogni sequenza non alfanumerica diventa uno spazio singolo, estremi
    rimossi. NON tenta di risolvere refusi o omonimie: quelle restano un limite
    dichiarato, e vengono quantificate a parte con il riscontro su map_ge.csv.
    """
    s = str(s).lower().strip()
    s = re.sub(r"[^a-z0-9]+", " ", s)
    return re.sub(r"\s+", " ", s).strip()


class UnionFind:
    def __init__(self, elementi):
        self.padre = {e: e for e in elementi}

    def trova(self, x):
        while self.padre[x] != x:
            self.padre[x] = self.padre[self.padre[x]]
            x = self.padre[x]
        return x

    def unisci(self, a, b):
        ra, rb = self.trova(a), self.trova(b)
        if ra != rb:
            self.padre[ra] = rb


def descrivi(v: np.ndarray) -> dict:
    """Riassunto di una distribuzione, con i quantili che servono al report."""
    v = np.asarray(v, dtype=float)
    v = v[np.isfinite(v)]
    if v.size == 0:
        return {"n": 0}
    return {
        "n": int(v.size),
        "media": float(v.mean()),
        "sd": float(v.std(ddof=1)) if v.size > 1 else 0.0,
        "min": float(v.min()),
        "q10": float(np.quantile(v, 0.10)),
        "q25": float(np.quantile(v, 0.25)),
        "mediana": float(np.median(v)),
        "q75": float(np.quantile(v, 0.75)),
        "q90": float(np.quantile(v, 0.90)),
        "max": float(v.max()),
    }


# --------------------------------------------------------- 1. identita' dell'asta
def profila_aste(d: pd.DataFrame) -> dict:
    """Per ogni asta di file raccoglie configurazione, insieme delle righe e dei nomi."""
    profili = {}
    for chiave, g in d.groupby(["source_file", "auction_id"], sort=True):
        chiave = (str(chiave[0]), int(chiave[1]))
        profili[chiave] = {
            "n_righe": int(len(g)),
            "componenti": int(g.componenti.iloc[0]),
            "crediti_tot": int(g.crediti_tot.iloc[0]),
            "modificatore": (None if pd.isna(g.modificatore.iloc[0])
                             else str(g.modificatore.iloc[0])),
            "periodo": int(g.periodo.iloc[0]),
            "stagione": GE_FILE_SEASON.get(chiave[0]),
            "spesa": int(g.prezzo.sum()),
            # insieme (ruolo, nome, prezzo): l'identita' che useremo
            "righe": frozenset(zip(g.ruolo, g.nome_norm, g.prezzo)),
            # insieme (ruolo, nome): serve a mostrare che il solo elenco NON basta
            "nomi": frozenset(zip(g.ruolo, g.nome_norm)),
        }
    return profili


def verifica_costanza_configurazione(d: pd.DataFrame) -> dict:
    """La configurazione deve essere una funzione della coppia (file, auction_id).

    Se non lo fosse, la coppia non sarebbe nemmeno un'unita' coerente e ogni
    conclusione a valle cadrebbe.
    """
    g = d.groupby(["source_file", "auction_id"])
    fuori = {}
    for col in ("componenti", "crediti_tot", "modificatore", "periodo"):
        n = g[col].nunique(dropna=False)
        fuori[col] = int((n > 1).sum())
    return fuori


def misura_riuso_auction_id(d: pd.DataFrame) -> dict:
    """Quantifica il riuso di auction_id fra file: e' la prova che non e' globale."""
    per_id = d.groupby("auction_id")["source_file"].nunique()
    per_file = d.groupby("source_file")["auction_id"].agg(["min", "max", "nunique"])
    return {
        "auction_id_distinti": int(per_id.size),
        "auction_id_in_piu_file": int((per_id > 1).sum()),
        "auction_id_max_file": int(per_id.max()),
        "per_file": {f: {"min": int(r["min"]), "max": int(r["max"]),
                         "distinti": int(r["nunique"])}
                     for f, r in per_file.iterrows()},
    }


def sovrapposizioni(profili: dict, campo: str) -> list:
    """Sovrapposizione fra tutte le coppie di aste di file, sul campo indicato.

    Misura usata: |A intersecato B| / min(|A|, |B|). Il minimo al denominatore, e non
    l'unione, perche' una versione PARZIALE della stessa asta deve risultare molto
    sovrapposta alla versione completa: con l'unione al denominatore una copia a meta'
    darebbe 0,5 e sfuggirebbe.
    """
    chiavi = sorted(profili)
    fuori = []
    for a, b in itertools.combinations(chiavi, 2):
        A, B = profili[a][campo], profili[b][campo]
        den = max(1, min(len(A), len(B)))
        fuori.append((a, b, len(A & B) / den))
    return fuori


def istogramma(valori, bordi) -> dict:
    v = np.asarray(valori, dtype=float)
    fuori = {}
    for lo, hi in zip(bordi[:-1], bordi[1:]):
        fuori[f"[{lo:.2f},{hi:.2f})"] = int(((v >= lo) & (v < hi)).sum())
    return fuori


# --------------------------------------------------------------- 2. inventario
def copertura_ruoli(d: pd.DataFrame) -> pd.DataFrame:
    tab = (d.pivot_table(index=["source_file", "auction_id"], columns="ruolo",
                         values="prezzo", aggfunc="size")
           .reindex(columns=list(RUOLI)).fillna(0).astype(int))
    tab.columns = [f"n_{c}" for c in tab.columns]
    return tab


# ------------------------------------------------------------------ 3. bersagli
def scomponi_varianza(df: pd.DataFrame, col_y: str) -> dict:
    """Scomposizione della varianza di y in effetto giocatore, effetto asta, residuo.

    df ha una riga per (asta, giocatore) e le colonne `gid` (identita' giocatore-stagione),
    `aid` (identita' asta) e col_y.

    Procedura, dichiarata perche' il disegno e' sbilanciato e i termini NON sono
    ortogonali per costruzione:
        m       = media generale
        m_p     = media del giocatore p su tutte le aste in cui compare
        b_a     = media, dentro l'asta a, dei residui (y - m_p): il livello dell'asta
        e       = y - m_p - b_a
    Si riportano le tre varianze empiriche e la somma dei prodotti incrociati, cosi'
    che il lettore veda quanto la decomposizione e' additiva su QUESTI dati invece di
    doverlo assumere.
    """
    y = df[col_y].to_numpy(dtype=float)
    m = float(y.mean())
    m_p = df.groupby("gid")[col_y].transform("mean").to_numpy(dtype=float)
    res1 = y - m_p
    b_a = pd.Series(res1, index=df.index).groupby(df["aid"]).transform("mean").to_numpy()
    e = res1 - b_a

    comp_giocatore = m_p - m
    ss_tot = float(((y - m) ** 2).sum())
    ss_g = float((comp_giocatore ** 2).sum())
    ss_a = float((b_a ** 2).sum())
    ss_e = float((e ** 2).sum())
    incrociati = ss_tot - (ss_g + ss_a + ss_e)

    n = len(y)
    return {
        "n_osservazioni": int(n),
        "n_giocatori": int(df.gid.nunique()),
        "n_aste": int(df.aid.nunique()),
        "media": m,
        "sd_totale": float(y.std(ddof=1)),
        "ss_totale": ss_tot,
        "ss_giocatore": ss_g,
        "ss_asta": ss_a,
        "ss_residuo": ss_e,
        "ss_incrociati": float(incrociati),
        "quota_giocatore": ss_g / ss_tot if ss_tot else float("nan"),
        "quota_asta": ss_a / ss_tot if ss_tot else float("nan"),
        "quota_residuo": ss_e / ss_tot if ss_tot else float("nan"),
        "quota_incrociati": incrociati / ss_tot if ss_tot else float("nan"),
        "sd_entro_giocatore": float(np.sqrt((res1 ** 2).sum() / max(1, n - df.gid.nunique()))),
        "sd_livello_asta": float(np.sqrt(ss_a / n)),
        "sd_idiosincratica": float(np.sqrt(ss_e / n)),
    }


def stabilita_rapporto_prezzo_budget(d: pd.DataFrame, rng, n_boot: int) -> dict:
    """Il rapporto prezzo/budget e' stabile fra configurazioni? Misurato, non assunto.

    Stimatore entro-giocatore (differenze rispetto alla media del giocatore-stagione):

        log(prezzo) = beta_cr * log(crediti_tot) + beta_co * log(componenti)
                      + effetto fisso (giocatore, stagione) + errore

    beta_cr = 1 significa proporzionalita' esatta: raddoppiare il budget raddoppia il
    prezzo, e pct_budget e' invariante. beta_cr < 1 significa che i budget alti
    comprano meno che proporzionalmente, e pct_budget NON e' confrontabile fra
    configurazioni senza correzione.

    L'incertezza viene da un bootstrap che ricampiona le ASTE, non le righe: righe
    della stessa asta non sono osservazioni indipendenti (Protocollo v2 §3.3).
    Solo prezzi >= 1: log(0) non esiste e i prezzi 0 sono assegnazioni d'ufficio.
    """
    sub = d[d.prezzo >= 1].copy()
    sub["gid"] = sub.stagione.astype(str) + "|" + sub.ruolo + "|" + sub.nome_norm
    # servono giocatori visti in almeno due configurazioni diverse, altrimenti
    # l'effetto fisso assorbe tutto e il coefficiente non e' identificato
    conf = sub.groupby("gid").agg(n_cr=("crediti_tot", "nunique"),
                                  n_co=("componenti", "nunique"))
    tenuti = conf[(conf.n_cr > 1) | (conf.n_co > 1)].index
    sub = sub[sub.gid.isin(tenuti)].copy()
    if sub.empty:
        return {"stimabile": False, "motivo": "nessun giocatore in piu' configurazioni"}

    sub["y"] = np.log(sub.prezzo.to_numpy(dtype=float))
    sub["x1"] = np.log(sub.crediti_tot.to_numpy(dtype=float))
    sub["x2"] = np.log(sub.componenti.to_numpy(dtype=float))

    # controlli opzionali: indicatrici di periodo. Il periodo e' una colonna del
    # foglio con semantica non documentata: entra come sensibilita', non come
    # correzione preferita.
    periodi = sorted(sub.periodo.unique())[1:]
    for p in periodi:
        sub[f"per_{p}"] = (sub.periodo == p).astype(float)
    col_extra = [f"per_{p}" for p in periodi]

    def stima(frame, extra=()):
        def centra(c):
            v = frame[c].to_numpy(dtype=float)
            return v - frame.groupby("gid")[c].transform("mean").to_numpy(dtype=float)
        Y = centra("y")
        X = np.column_stack([centra("x1"), centra("x2")] + [centra(c) for c in extra])
        coef, *_ = np.linalg.lstsq(X, Y, rcond=None)
        return coef

    punto = stima(sub)
    punto_ctrl = stima(sub, col_extra)
    aste = sub[["source_file", "auction_id"]].drop_duplicates()
    aste_lista = list(map(tuple, aste.to_numpy()))
    indice = {k: g for k, g in sub.groupby(["source_file", "auction_id"])}

    campioni = []
    for _ in range(n_boot):
        scelte = [aste_lista[i] for i in rng.integers(0, len(aste_lista), len(aste_lista))]
        rep = pd.concat([indice[k] for k in scelte], ignore_index=True)
        # l'effetto fisso resta quello del giocatore VERO: e' la variazione dello
        # stesso giocatore fra configurazioni che identifica beta. L'unita' di
        # ricampionamento e' l'asta, non la riga.
        # dopo il ricampionamento servono ancora giocatori in piu' configurazioni
        c = rep.groupby("gid").agg(a=("crediti_tot", "nunique"), b=("componenti", "nunique"))
        tenuti_r = c[(c.a > 1) | (c.b > 1)].index
        rep = rep[rep.gid.isin(tenuti_r)]
        if rep.empty or rep.gid.nunique() < 5:
            continue
        try:
            campioni.append(stima(rep))
        except np.linalg.LinAlgError:
            continue

    camp = np.array(campioni) if campioni else np.empty((0, 2))
    fuori = {
        "stimabile": True,
        "n_osservazioni": int(len(sub)),
        "n_giocatori_identificanti": int(sub.gid.nunique()),
        "n_aste": int(len(aste_lista)),
        "beta_log_crediti": float(punto[0]),
        "beta_log_componenti": float(punto[1]),
        "beta_log_crediti_con_periodo": float(punto_ctrl[0]),
        "beta_log_componenti_con_periodo": float(punto_ctrl[1]),
        "n_repliche_bootstrap_valide": int(len(camp)),
        "nota": ("associazione descrittiva a giocatore-stagione fisso, non "
                 "un'elasticita' causale: leghe con budget diverso possono differire "
                 "anche per cose non osservate in questa tabella"),
    }
    if len(camp) >= 20:
        fuori["ic95_beta_log_crediti"] = [float(np.quantile(camp[:, 0], 0.025)),
                                          float(np.quantile(camp[:, 0], 0.975))]
        fuori["ic95_beta_log_componenti"] = [float(np.quantile(camp[:, 1], 0.025)),
                                             float(np.quantile(camp[:, 1], 0.975))]
    return fuori


# ------------------------------------------------------------------------ main
def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--outdir", default=str(ROOT / "data" / "l4"))
    ap.add_argument("--boot", type=int, default=1000)
    ap.add_argument("--seed", type=int, default=20260908)
    args = ap.parse_args()

    outdir = Path(args.outdir)
    outdir.mkdir(parents=True, exist_ok=True)
    rng = np.random.default_rng(args.seed)

    esito = {
        "prodotto_il": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "script": "scripts/l4_inventario_aste.py",
        "python": platform.python_version(),
        "pandas": pd.__version__,
        "numpy": np.__version__,
        "seed": args.seed,
        "parametri": {
            "soglia_duplicati": SOGLIA_DUP,
            "intervallo_vuoto_atteso": [GAP_MIN, GAP_MAX],
            "lega": {"componenti": LEGA_COMPONENTI, "crediti_tot": LEGA_CREDITI,
                     "quote": LEGA_QUOTE, "modificatore_attivo": LEGA_MODIFICATORE_ATTIVO},
        },
        "input_hashes": {},
    }

    # ---------------------------------------------------------------- input
    if not TIDY.exists():
        print(f"ERRORE: input mancante {TIDY}", file=sys.stderr)
        return 2
    esito["input_hashes"][str(TIDY.relative_to(ROOT)).replace("\\", "/")] = sha256(TIDY)
    if BUILD_STATS.exists():
        esito["input_hashes"][str(BUILD_STATS.relative_to(ROOT)).replace("\\", "/")] = \
            sha256(BUILD_STATS)

    d = pd.read_csv(TIDY)
    d["nome_norm"] = d.player_raw.map(normalizza_nome)
    d["stagione"] = d.source_file.map(GE_FILE_SEASON)

    esito["forma_tidy"] = {
        "righe": int(len(d)),
        "colonne": list(d.columns[:10]),
        "auction_id_distinti": int(d.auction_id.nunique()),
        "coppie_file_auction": int(d.groupby(["source_file", "auction_id"]).ngroups),
        "nomi_normalizzati_distinti": int(d.nome_norm.nunique()),
        "stagione_ignota_righe": int(d.stagione.isna().sum()),
    }
    print("[1] forma:", esito["forma_tidy"]["righe"], "righe,",
          esito["forma_tidy"]["auction_id_distinti"], "auction_id distinti,",
          esito["forma_tidy"]["coppie_file_auction"], "coppie (file, auction_id)")

    # ------------------------------------------------- 4. che cosa NON c'e'
    attese_assenti = {
        "ordine_lotti": ["ordine", "order", "lotto", "lot", "seq", "indice", "idx",
                         "turno", "chiamata", "n_lotto", "numero"],
        "proprietari": ["squadra", "team", "owner", "proprietario", "acquirente",
                        "partecipante", "manager", "allenatore", "fanta"],
        "marche_temporali": ["data", "date", "ora", "time", "timestamp", "orario",
                             "datetime", "quando"],
    }
    colonne = [c for c in pd.read_csv(TIDY, nrows=0).columns]
    mancanti = {}
    for gruppo, radici in attese_assenti.items():
        trovate = [c for c in colonne
                   if any(r in c.lower() for r in radici)]
        mancanti[gruppo] = {"colonne_trovate": trovate, "assente": len(trovate) == 0}
    esito["colonne_presenti"] = colonne
    esito["colonne_mancanti"] = mancanti
    print("[4] colonne assenti:",
          {k: v["assente"] for k, v in mancanti.items()})

    # ---------------------------------------------- 1. identita' dell'asta
    fuori_config = verifica_costanza_configurazione(d)
    esito["configurazione_costante_per_asta"] = fuori_config
    riuso = misura_riuso_auction_id(d)
    esito["riuso_auction_id"] = riuso
    print("[1] auction_id in piu' di un file:", riuso["auction_id_in_piu_file"],
          "su", riuso["auction_id_distinti"])

    profili = profila_aste(d)

    # impronta esatta di contenuto: configurazione + insieme (ruolo, nome, prezzo)
    impronte = defaultdict(list)
    for k, p in profili.items():
        impronte[(p["componenti"], p["crediti_tot"], p["righe"])].append(k)
    gruppi_esatti = [g for g in impronte.values() if len(g) > 1]
    esito["duplicati_esatti"] = {
        "gruppi": len(gruppi_esatti),
        "copie_in_eccesso": int(sum(len(g) - 1 for g in gruppi_esatti)),
        "impronte_distinte": len(impronte),
        "dettaglio": [[[f, int(a)] for f, a in sorted(g)] for g in gruppi_esatti],
    }
    print("[2] impronte esatte distinte:", len(impronte),
          f"({esito['duplicati_esatti']['copie_in_eccesso']} copie in eccesso)")

    # sovrapposizione sui prezzi (identita' candidata) e sui soli nomi (controllo)
    sov_prezzi = sovrapposizioni(profili, "righe")
    sov_nomi = sovrapposizioni(profili, "nomi")
    v_prezzi = np.array([x[2] for x in sov_prezzi])
    v_nomi = np.array([x[2] for x in sov_nomi])

    bordi = [0.0, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 0.95, 1.0001]
    esito["sovrapposizione_prezzi"] = {
        "n_coppie": int(len(v_prezzi)),
        "istogramma": istogramma(v_prezzi, bordi),
        "massimo_sotto_gap": float(v_prezzi[v_prezzi < GAP_MAX].max())
        if (v_prezzi < GAP_MAX).any() else None,
        "minimo_sopra_gap": float(v_prezzi[v_prezzi >= GAP_MIN].min())
        if (v_prezzi >= GAP_MIN).any() else None,
        "coppie_dentro_il_gap": int(((v_prezzi >= GAP_MIN) & (v_prezzi < GAP_MAX)).sum()),
    }
    esito["sovrapposizione_nomi"] = {
        "n_coppie": int(len(v_nomi)),
        "istogramma": istogramma(v_nomi, bordi),
        "coppie_dentro_il_gap": int(((v_nomi >= GAP_MIN) & (v_nomi < GAP_MAX)).sum()),
        "coppie_non_duplicate_con_sovrapposizione_nomi_alta": int(
            sum(1 for (a, b, o), (_, _, op) in zip(sov_prezzi, sov_nomi)
                if op >= 0.80 and o < GAP_MIN)),
    }
    gap_vuoto = esito["sovrapposizione_prezzi"]["coppie_dentro_il_gap"] == 0
    esito["gap_vuoto"] = bool(gap_vuoto)
    print(f"[1] sovrapposizione prezzi: coppie in [{GAP_MIN},{GAP_MAX}) = "
          f"{esito['sovrapposizione_prezzi']['coppie_dentro_il_gap']} "
          f"(gap {'VUOTO' if gap_vuoto else 'NON vuoto'})")

    # coppie sospette su file, per ispezione
    righe_sosp = []
    for (a, b, o), (_, _, on) in zip(sov_prezzi, sov_nomi):
        if o >= SOGLIA_ISPEZIONE or on >= 0.80:
            righe_sosp.append({
                "file_a": a[0], "asta_a": int(a[1]), "n_a": profili[a]["n_righe"],
                "file_b": b[0], "asta_b": int(b[1]), "n_b": profili[b]["n_righe"],
                "sovrapposizione_prezzi": round(o, 6),
                "sovrapposizione_nomi": round(on, 6),
                "cfg_a": f"{profili[a]['componenti']}x{profili[a]['crediti_tot']}",
                "cfg_b": f"{profili[b]['componenti']}x{profili[b]['crediti_tot']}",
                "stesso_file": a[0] == b[0],
                "duplicato": o >= SOGLIA_DUP,
            })
    df_sosp = pd.DataFrame(righe_sosp).sort_values(
        "sovrapposizione_prezzi", ascending=False) if righe_sosp else pd.DataFrame()
    if not df_sosp.empty:
        df_sosp.to_csv(outdir / "l4_coppie_sospette.csv", index=False, encoding="utf-8")

    # cluster = asta reale
    uf = UnionFind(list(profili))
    n_coppie_unite = 0
    n_coppie_intra_file = 0
    for a, b, o in sov_prezzi:
        if o >= SOGLIA_DUP:
            uf.unisci(a, b)
            n_coppie_unite += 1
            if a[0] == b[0]:
                n_coppie_intra_file += 1
    radici = {k: uf.trova(k) for k in profili}
    dim = Counter(radici.values())
    # Regola di scelta della versione canonica: la trascrizione PIU' COMPLETA del
    # cluster (piu' righe); a parita' di righe, la coppia (file, auction_id) minima,
    # cosi' che l'identificativo sia deterministico. Le versioni NON vengono fuse:
    # dove due versioni si contraddicono sul prezzo non esiste un criterio per
    # decidere quale sia giusta, e la fusione inventerebbe un'asta mai avvenuta.
    canonica = {}
    for k, r in radici.items():
        pri = (-profili[k]["n_righe"], k[0], k[1])
        if r not in canonica or pri < canonica[r][0]:
            canonica[r] = (pri, k)
    canonica = {r: v[1] for r, v in canonica.items()}
    asta_uid = {k: f"{canonica[r][0]}#{canonica[r][1]}" for k, r in radici.items()}

    # effetto misurato della regola: righe perse rispetto all'unione delle versioni,
    # e disaccordo fra versioni sullo stesso giocatore
    per_cluster = defaultdict(list)
    for k, r in radici.items():
        per_cluster[r].append(k)
    perse, disaccordi, n_confronti = 0, 0, 0
    dettaglio_disc = []
    for r, membri in per_cluster.items():
        if len(membri) == 1:
            continue
        unione = set().union(*(profili[m]["nomi"] for m in membri))
        perse += len(unione) - len(profili[canonica[r]]["nomi"])
        prezzi = defaultdict(list)
        for m in membri:
            for ru, nm, pz in profili[m]["righe"]:
                prezzi[(ru, nm)].append(pz)
        disc_qui = Counter()
        for chiave_g, valori in prezzi.items():
            if len(valori) < 2:      # giocatore presente in una sola versione
                continue
            n_confronti += 1
            if len(set(valori)) > 1:
                disaccordi += 1
                disc_qui[chiave_g[0]] += 1
        if disc_qui:
            dettaglio_disc.append({
                "asta_uid": f"{canonica[r][0]}#{canonica[r][1]}",
                "versioni": [f"{m[0]}#{m[1]}" for m in sorted(membri)],
                "disaccordi_per_ruolo": dict(sorted(disc_qui.items())),
            })
    esito["effetto_regola_deduplica"] = {
        "cluster_con_piu_versioni": int(sum(1 for m in per_cluster.values() if len(m) > 1)),
        "giocatori_presenti_nell_unione_ma_non_nella_canonica": int(perse),
        "coppie_giocatore_confrontabili_fra_versioni": int(n_confronti),
        "coppie_con_prezzo_discorde_fra_versioni": int(disaccordi),
        "quota_discordi": (disaccordi / n_confronti) if n_confronti else None,
        "dettaglio_disaccordi_per_cluster": dettaglio_disc,
    }

    esito["clustering"] = {
        "soglia": SOGLIA_DUP,
        "coppie_unite": n_coppie_unite,
        "coppie_unite_stesso_file": n_coppie_intra_file,
        "aste_di_file": len(profili),
        "aste_reali": len(dim),
        "cluster_per_dimensione": {str(k): v for k, v in sorted(Counter(dim.values()).items())},
    }
    print("[1] aste reali (cluster di contenuto):", len(dim),
          f"da {len(profili)} aste di file")

    # sensibilita' della soglia: il numero di cluster cambia dentro il gap?
    sens = {}
    for s in (0.30, 0.40, 0.50, 0.60, 0.70, 0.80, 0.85, 0.90, 0.95, 1.0):
        uf2 = UnionFind(list(profili))
        for a, b, o in sov_prezzi:
            if o >= s:
                uf2.unisci(a, b)
        sens[f"{s:.2f}"] = len({uf2.trova(k) for k in profili})
    esito["clustering"]["sensibilita_soglia"] = sens
    print("[1] cluster per soglia:", sens)

    # ---------------------------------------- 2. duplicati interni all'asta
    dup_riga = d.groupby(["source_file", "auction_id", "ruolo", "nome_norm"]).size()
    esito["righe_ripetute_intra_asta"] = {
        "coppie_asta_giocatore_con_piu_righe": int((dup_riga > 1).sum()),
        "righe_in_eccesso": int((dup_riga - 1).clip(lower=0).sum()),
        "aste_coinvolte": int(dup_riga[dup_riga > 1].reset_index()
                              .groupby(["source_file", "auction_id"]).ngroups),
    }
    ripetuti = dup_riga[dup_riga > 1].reset_index(name="n_righe")
    if not ripetuti.empty:
        merged = d.merge(ripetuti[["source_file", "auction_id", "ruolo", "nome_norm"]],
                         on=["source_file", "auction_id", "ruolo", "nome_norm"])
        vp = merged.groupby(["source_file", "auction_id", "ruolo", "nome_norm"])["prezzo"]
        esito["righe_ripetute_intra_asta"]["prezzi_identici"] = int((vp.nunique() == 1).sum())
        esito["righe_ripetute_intra_asta"]["prezzi_diversi"] = int((vp.nunique() > 1).sum())
        esito["righe_ripetute_intra_asta"]["scarto_relativo_quando_diversi"] = descrivi(
            ((vp.max() - vp.min()) / vp.mean().replace(0, np.nan))[vp.nunique() > 1].to_numpy())
    print("[2] coppie (asta, giocatore) con piu' di una riga:",
          esito["righe_ripetute_intra_asta"]["coppie_asta_giocatore_con_piu_righe"])

    # -------------------------------------------------------- 3. inventario
    ruoli = copertura_ruoli(d)
    base = d.groupby(["source_file", "auction_id"]).agg(
        stagione=("stagione", "first"),
        componenti=("componenti", "first"),
        crediti_tot=("crediti_tot", "first"),
        modificatore=("modificatore", "first"),
        periodo=("periodo", "first"),
        n_lotti=("prezzo", "size"),
        spesa=("prezzo", "sum"),
        prezzo_max=("prezzo", "max"),
        n_prezzo_zero=("prezzo", lambda s: int((s == 0).sum())),
        n_giocatori_distinti=("nome_norm", "nunique"),
    ).join(ruoli)

    idx = [(str(f), int(a)) for f, a in base.index]
    base["asta_uid"] = [asta_uid[k] for k in idx]
    base["dimensione_cluster"] = [dim[radici[k]] for k in idx]
    base["canonica"] = [asta_uid[k] == f"{k[0]}#{k[1]}" for k in idx]
    base["lotti_attesi"] = base.componenti * sum(LEGA_QUOTE.values())
    base["lotti_mancanti"] = base.lotti_attesi - base.n_lotti
    for r in RUOLI:
        base[f"quota_{r}_per_partecipante"] = base[f"n_{r}"] / base.componenti
    base["quote_3_8_8_6"] = (
        (base.n_P == LEGA_QUOTE["P"] * base.componenti)
        & (base.n_D == LEGA_QUOTE["D"] * base.componenti)
        & (base.n_C == LEGA_QUOTE["C"] * base.componenti)
        & (base.n_A == LEGA_QUOTE["A"] * base.componenti))
    base["spesa_su_budget"] = base.spesa / (base.componenti * base.crediti_tot)
    base["config_lega"] = ((base.componenti == LEGA_COMPONENTI)
                           & (base.crediti_tot == LEGA_CREDITI))
    base = base.reset_index()
    base.to_csv(outdir / "l4_inventario_aste.csv", index=False, encoding="utf-8")

    uniche = base[base.canonica].copy()
    uniche.to_csv(outdir / "l4_aste_uniche.csv", index=False, encoding="utf-8")

    esito["inventario"] = {
        "aste_di_file": int(len(base)),
        "aste_reali": int(len(uniche)),
        "per_stagione": uniche.stagione.value_counts(dropna=False).to_dict(),
        "per_periodo": {str(k): int(v) for k, v in
                        uniche.periodo.value_counts().sort_index().items()},
        "per_modificatore": {("<vuoto>" if pd.isna(k) else str(k)): int(v) for k, v in
                             uniche.modificatore.value_counts(dropna=False).items()},
        "per_configurazione": {f"{int(c)}x{int(b)}": int(n) for (c, b), n in
                               uniche.groupby(["componenti", "crediti_tot"])
                               .size().sort_values(ascending=False).items()},
        "lotti": descrivi(uniche.n_lotti.to_numpy()),
        "lotti_pari_attesi": int((uniche.lotti_mancanti == 0).sum()),
        "lotti_meno_del_previsto": int((uniche.lotti_mancanti > 0).sum()),
        "lotti_piu_del_previsto": int((uniche.lotti_mancanti < 0).sum()),
        "quote_3_8_8_6": int(uniche.quote_3_8_8_6.sum()),
        "spesa_su_budget": descrivi(uniche.spesa_su_budget.to_numpy()),
        "aste_con_spesa_oltre_budget": int((uniche.spesa_su_budget > 1.0).sum()),
        "aste_con_prezzo_zero": int((uniche.n_prezzo_zero > 0).sum()),
        "aste_con_nomi_ripetuti": int((uniche.n_lotti != uniche.n_giocatori_distinti).sum()),
        "quota_per_partecipante": {r: descrivi(uniche[f"quota_{r}_per_partecipante"].to_numpy())
                                   for r in RUOLI},
    }
    print("[3] inventario:", len(uniche), "aste reali,",
          esito["inventario"]["quote_3_8_8_6"], "con quote 3/8/8/6 esatte")

    # ---------------------------------------------------- 6. lega bersaglio
    lega = uniche[uniche.config_lega]
    mod_attivo = uniche.modificatore.isin(["M", "+1M", "+1"])
    esito["lega_bersaglio"] = {
        "componenti_10_crediti_500": int(len(lega)),
        "e_quote_3_8_8_6": int(lega.quote_3_8_8_6.sum()),
        "e_modificatore_non_N": int(lega.modificatore.isin(["M", "+1M", "+1"]).sum()),
        "e_quote_e_modificatore": int((lega.quote_3_8_8_6
                                       & lega.modificatore.isin(["M", "+1M", "+1"])).sum()),
        "per_stagione": lega.stagione.value_counts(dropna=False).to_dict(),
        "per_periodo": {str(k): int(v) for k, v in
                        lega.periodo.value_counts().sort_index().items()},
        "modificatore_attivo_su_tutte_le_aste": int(mod_attivo.sum()),
        "modificatore_vuoto_su_tutte_le_aste": int(uniche.modificatore.isna().sum()),
        "componenti_diversi": {str(int(k)): int(v) for k, v in
                               uniche.componenti.value_counts().sort_index().items()},
        "crediti_diversi": {str(int(k)): int(v) for k, v in
                            uniche.crediti_tot.value_counts().sort_index().items()},
    }
    print("[6] configurazione lega (10x500):", len(lega), "aste reali")

    # ------------------------------------------------------- 5. bersagli
    # universo: solo aste canoniche (una per evento reale), un prezzo per
    # (asta, giocatore) — le righe ripetute intra-asta sono collassate tenendo la
    # PRIMA occorrenza, e la loro numerosita' e' gia' misurata sopra.
    canon = set(uniche.set_index(["source_file", "auction_id"]).index)
    dd = d[[k in canon for k in zip(d.source_file, d.auction_id)]].copy()
    dd = dd.drop_duplicates(["source_file", "auction_id", "ruolo", "nome_norm"], keep="first")
    dd["aid"] = dd.source_file + "#" + dd.auction_id.astype(str)
    dd["gid"] = dd.stagione.astype(str) + "|" + dd.ruolo + "|" + dd.nome_norm

    # riscontro esterno del name matching (solo controllo, non usato per il calcolo)
    if MAP_GE.exists():
        esito["input_hashes"][str(MAP_GE.relative_to(ROOT)).replace("\\", "/")] = sha256(MAP_GE)
        mg = pd.read_csv(MAP_GE)
        mg["nome_norm"] = mg.player_raw.map(normalizza_nome)
        collassi = (mg.dropna(subset=["master_id"])
                    .groupby(["stagione", "ruolo", "nome_norm"])["master_id"].nunique())
        esplosi = (mg.dropna(subset=["master_id"])
                   .groupby(["stagione", "ruolo", "master_id"])["nome_norm"].nunique())
        esito["riscontro_nomi_map_ge"] = {
            "righe_map_ge": int(len(mg)),
            "quota_con_master_id": float(mg.master_id.notna().mean()),
            "chiavi_normalizzate_che_uniscono_master_id_diversi": int((collassi > 1).sum()),
            "master_id_con_piu_nomi_normalizzati": int((esplosi > 1).sum()),
        }

    stat_gioc = (dd.groupby(["stagione", "ruolo", "nome_norm"])
                 .agg(n_aste=("prezzo", "size"),
                      prezzo_medio=("prezzo", "mean"),
                      prezzo_sd=("prezzo", "std"),
                      prezzo_min=("prezzo", "min"),
                      prezzo_max=("prezzo", "max"),
                      pct_medio=("pct_budget", "mean"),
                      pct_sd=("pct_budget", "std"))
                 .reset_index())
    stat_gioc["cv"] = stat_gioc.prezzo_sd / stat_gioc.prezzo_medio.replace(0, np.nan)
    stat_gioc.to_csv(outdir / "l4_prezzi_per_giocatore.csv", index=False, encoding="utf-8")

    # strato omogeneo: la configurazione della nostra lega
    strato = dd[(dd.componenti == LEGA_COMPONENTI) & (dd.crediti_tot == LEGA_CREDITI)].copy()
    bersagli = {}
    for nome_strato, frame in (("tutte_le_configurazioni", dd), ("solo_10x500", strato)):
        f = frame.copy()
        # per il confronto fra aste servono giocatori visti in almeno 2 aste
        cnt = f.groupby("gid")["prezzo"].transform("size")
        f2 = f[cnt >= 2].copy()
        sd_entro = (f2.groupby("gid")["pct_budget"].std(ddof=1)).dropna()
        n_per_g = f2.groupby("gid")["pct_budget"].size()
        bersagli[nome_strato] = {
            "osservazioni": int(len(f)),
            "giocatori": int(f.gid.nunique()),
            "aste": int(f.aid.nunique()),
            "giocatori_in_almeno_2_aste": int(f2.gid.nunique()),
            "aste_per_giocatore": descrivi(n_per_g.to_numpy()),
            "scomposizione_pct_budget": scomponi_varianza(f2, "pct_budget") if len(f2) else {},
            "scomposizione_log1p_prezzo": (
                scomponi_varianza(f2.assign(lp=np.log1p(f2.prezzo)), "lp") if len(f2) else {}),
            "sd_entro_giocatore_pct": descrivi(sd_entro.to_numpy()),
        }
        if nome_strato == "solo_10x500" and len(f2):
            # traduzione operativa: martelletto contro media, in crediti su budget 500
            sd_h = sd_entro * LEGA_CREDITI          # sd del singolo martelletto, crediti
            se_m = (sd_entro / np.sqrt(n_per_g.reindex(sd_entro.index))) * LEGA_CREDITI
            bersagli[nome_strato]["sd_martelletto_crediti"] = descrivi(sd_h.to_numpy())
            bersagli[nome_strato]["errore_standard_media_crediti"] = descrivi(se_m.to_numpy())
            bersagli[nome_strato]["rapporto_sd_su_errore_standard"] = descrivi(
                (sd_h / se_m.replace(0, np.nan)).to_numpy())
            # fascia di prezzo: la dispersione dipende dal livello?
            liv = f2.groupby("gid")["prezzo"].mean()
            fasce = pd.cut(liv, [-0.01, 1, 5, 15, 40, 100, 10000],
                           labels=["0-1", "2-5", "6-15", "16-40", "41-100", ">100"])
            per_fascia = {}
            for et in fasce.cat.categories:
                sel = liv.index[fasce == et]
                s = sd_h.reindex(sel).dropna()
                m = liv.reindex(sel)
                if len(s) >= 5:
                    per_fascia[str(et)] = {
                        "n_giocatori": int(len(s)),
                        "prezzo_medio": float(m.mean()),
                        "sd_martelletto_crediti_mediana": float(np.median(s)),
                        "cv_mediano": float(np.median(
                            (s / m.reindex(s.index).replace(0, np.nan)).dropna()))
                        if (m.reindex(s.index) > 0).any() else None,
                    }
            bersagli[nome_strato]["per_fascia_di_prezzo"] = per_fascia
    # dispersione ENTRO asta contro dispersione FRA aste.
    # Dentro una singola asta ogni giocatore compare al massimo una volta: una
    # dispersione entro asta PER LO STESSO GIOCATORE non e' stimabile da questi dati.
    # Le due quantita' misurabili e confrontabili sono:
    #   - trasversale entro asta: quanto variano i prezzi FRA giocatori nella stessa asta;
    #   - fra aste per giocatore: quanto varia il prezzo dello STESSO giocatore fra aste.
    entro = strato.groupby("aid")["pct_budget"].std(ddof=1).dropna()
    cnt_s = strato.groupby("gid")["prezzo"].transform("size")
    s2 = strato[cnt_s >= 2]
    fra = s2.groupby("gid")["pct_budget"].std(ddof=1).dropna()
    esito["dispersione_entro_contro_fra"] = {
        "strato": "10x500",
        "sd_trasversale_entro_asta_pct": descrivi(entro.to_numpy()),
        "sd_fra_aste_stesso_giocatore_pct": descrivi(fra.to_numpy()),
        "rapporto_mediane": (float(np.median(fra) / np.median(entro))
                             if len(entro) and np.median(entro) else None),
        "nota": ("dentro un'asta ogni giocatore ha al piu' un martelletto: la "
                 "dispersione entro asta a giocatore fisso non e' stimabile, se non "
                 "dalle righe ripetute, che sono errori di trascrizione"),
        "righe_ripetute_come_limite_superiore":
            esito["righe_ripetute_intra_asta"].get("scarto_relativo_quando_diversi"),
    }

    # sensibilita' all'identita' del giocatore: la normalizzazione dei nomi separa lo
    # stesso giocatore in piu' chiavi quando il foglio contiene refusi. Si rifa' la
    # misura chiave usando master_id di map_ge.csv, che risolve i refusi, e si
    # confrontano i due risultati invece di assumerne l'equivalenza.
    if MAP_GE.exists():
        mg2 = pd.read_csv(MAP_GE).dropna(subset=["master_id"])
        mg2["nome_norm"] = mg2.player_raw.map(normalizza_nome)
        chiave = mg2.drop_duplicates(["stagione", "ruolo", "nome_norm"])
        alt = strato.merge(chiave[["stagione", "ruolo", "nome_norm", "master_id"]],
                           on=["stagione", "ruolo", "nome_norm"], how="left")
        coperto = float(alt.master_id.notna().mean())
        alt = alt.dropna(subset=["master_id"]).copy()
        alt["gid"] = alt.stagione.astype(str) + "|" + alt.master_id.astype(int).astype(str)
        # una sola riga per (asta, master_id): il collasso dei refusi puo' creare doppioni
        n_prima = len(alt)
        alt = alt.drop_duplicates(["aid", "gid"], keep="first")
        c2 = alt.groupby("gid")["prezzo"].transform("size")
        alt2 = alt[c2 >= 2]
        sd_alt = alt2.groupby("gid")["pct_budget"].std(ddof=1).dropna()
        esito["sensibilita_identita_giocatore"] = {
            "copertura_master_id": coperto,
            "righe_collassate_dal_master_id": int(n_prima - len(alt)),
            "giocatori_chiave_nome": int(strato[cnt_s >= 2].gid.nunique()),
            "giocatori_chiave_master_id": int(alt2.gid.nunique()),
            "scomposizione_pct_budget": scomponi_varianza(alt2, "pct_budget") if len(alt2) else {},
            "sd_fra_aste_pct": descrivi(sd_alt.to_numpy()),
        }

    esito["bersagli"] = bersagli
    q = bersagli["solo_10x500"]["scomposizione_pct_budget"]
    if q:
        print(f"[5] 10x500 — quota varianza: giocatore {q['quota_giocatore']:.3f}, "
              f"asta {q['quota_asta']:.3f}, residuo {q['quota_residuo']:.3f}, "
              f"incrociati {q['quota_incrociati']:.3f}")

    # ------------------------------- 6b. il rapporto prezzo/budget e' stabile?
    esito["stabilita_prezzo_budget"] = stabilita_rapporto_prezzo_budget(dd, rng, args.boot)
    sb = esito["stabilita_prezzo_budget"]
    if sb.get("stimabile"):
        print(f"[6] beta log(crediti) = {sb['beta_log_crediti']:.3f} "
              f"(1,000 = proporzionalita' esatta), "
              f"IC95 {sb.get('ic95_beta_log_crediti')}")

    # ------------------------------------------------------------- artefatti
    with open(outdir / "l4_inventario.json", "w", encoding="utf-8") as fh:
        json.dump(esito, fh, ensure_ascii=False, indent=2, default=str)

    fuori = [outdir / n for n in ("l4_inventario_aste.csv", "l4_aste_uniche.csv",
                                  "l4_coppie_sospette.csv", "l4_prezzi_per_giocatore.csv",
                                  "l4_inventario.json")]
    for p in fuori:
        if p.exists():
            print("scritto:", p)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
