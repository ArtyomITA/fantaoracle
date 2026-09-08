"""Valutazione riproducibile della feature `pres` (presenze) del modello valore.

Perché esiste questo script
---------------------------
La voce R2 del manifesto (`data/l3/MANIFESTO.json`, fase R2, 2026-09-08T00:57:19)
afferma: «il modello valore batte nettamente la storia grezza. 2024-25 MAE contro
il vero 0,1644 (corr 0,7146) contro 0,2396 (corr 0,3666) della storia; 2025-26
0,1628 (0,7550) contro 0,2389 (0,3556)». Quella voce ha `comandi`, `ingressi` e
`uscite` vuoti: non è riproducibile e non dichiara né i giocatori dei due bracci,
né il bersaglio, né l'orizzonte, né il trattamento dei mancanti. Questo script
rifà la misura dichiarando tutto e la estende alle unità corrette.

La voce originale **non è stata riprodotta**, e il tentativo è documentato qui
perché non venga rifatto. Con i bracci dichiarati sotto (415 giocatori appaiati
nel 2024-25, 444 nel 2025-26) i numeri sono: modello 0,1609 di MAE e 0,7690 di
correlazione contro 0,2505 e 0,4141 della storia nel 2024-25; 0,1537 e 0,8170
contro 0,2449 e 0,4431 nel 2025-26. La direzione e l'ordine di grandezza del
manifesto reggono; le cifre no. Cinque varianti sono state provate sul 2024-25
per cercare l'insieme che dà 0,1644 / 0,7146 / 0,2396 / 0,3666, e nessuna lo dà:
listone intero con storia mancante riempita a 0,5 (modello 0,1464 e 0,8107,
storia 0,2799 e 0,3569); listone intero con storia mancante riempita a 0
(storia 0,2583 e 0,4437); storia = `prev1_presenze`/38 sui 386 con quel campo
noto (modello 0,1606 e 0,7673, storia 0,2402 e 0,4595); la stessa con
`fillna(0)` su tutti i 679 (modello 0,1453 e 0,8108, storia 0,2609 e 0,4713);
bersaglio che conta anche i senza voto (modello 0,1830 e 0,7280, storia 0,2499 e
0,4075). Conclusione: la voce R2 resta **dichiarata**, non riprodotta, e i numeri
da citare sono quelli di questo script.

Che cosa è «presenza» qui (bersaglio, letto dal codice, non indovinato)
----------------------------------------------------------------------
In `scripts/f1_make_predictions.py::_season_points_frame` il bersaglio è

    v = _season_votes(s)                    # voti della stagione, `sv` ESCLUSI
    pres = v.groupby("master_id").size()

cioè il **numero di giornate in cui il giocatore ha ricevuto un voto**. Non sono
partite (una giornata rinviata resta la sua giornata), non sono convocazioni, non
sono presenze in campo: sono **presenze a voto**. Verificato sui parquet dei voti:
in `votes_2021-22 / 2023-24 / 2024-25 / 2025-26` non esiste nessun duplicato di
(`master_id`, `giornata`) — 0 su 11 673 / 11 862 / 11 854 / 11 897 righe — quindi
`size()` conta giornate distinte, e i senza voto (rispettivamente 1 037 / 1 071 /
1 141 / 1 119 righe) sono già fuori.

L'unità del bersaglio e il denominatore
---------------------------------------
Il modello non predice `pres`: predice `pres_resto = pres - pres_gk`, cioè le
presenze a voto delle sole giornate K+1..38, e le tronca in [0, 38-K]. Poi
`f1_make_predictions` scrive `pres = pres_gk + pres_resto`, dove `pres_gk` sono le
presenze **già realizzate** nelle prime K giornate.

Da qui la conseguenza sulle unità, che è il punto di questo script:

* con **K = 0** (asta pre-campionato) `pres_gk = 0` per costruzione, `pres` è il
  totale di stagione e `pres/38` è il tasso per giornata sull'intero orizzonte
  simulato: **coerente**;
* con **K > 0** (asta o aggiornamento live dopo K giornate) `pres/38` mescola un
  conteggio già realizzato con una previsione, e le divide per un orizzonte che
  non è quello che resta da simulare. Il tasso delle giornate **residue** è
  `(pres - pres_gk) / (38 - K)`, e sono le giornate residue quelle che il
  simulatore deve generare.

Oggi tre consumatori usano la forma `pres/38`: `src/fantabot/montecarlo.py:145`
(`p_play = pres / GIORNATE`), `scripts/l2_banco_confronto.py:398`
(`float(q["pres"]) / GIORNATE`) e `src/fantabot/montecarlo.py:328`
(`6.0 * (pres / 38.0)`, valutazione di ripiego). Va detto con precisione che cosa
è e che cosa non è sbagliato lì: il commento di `montecarlo.py:162-164` dichiara
che «la simulazione gioca tutte le 38 giornate (anche le K già fatte)», e su un
orizzonte di 38 giornate `pres/38` è il tasso coerente con il totale di stagione.
Il difetto non è quindi un'incoerenza interna a quel file, è che con K > 0 il
simulatore rigenera giornate il cui esito è già noto invece di condizionarvi: la
quantità che serve a chi decide dopo K giornate è il residuo, e il residuo ha
denominatore 38-K.

Quanto vale la differenza fra le due forme, misurato qui (media e massimo del
valore assoluto, giocatori con storia, sotto-modello riadattato):

    2024-25  K=3  medio 0,0203  massimo 0,0658
    2024-25  K=6  medio 0,0295  massimo 0,0921
    2024-25  K=19 medio 0,0666  massimo 0,3549
    2025-26  K=3  medio 0,0199  massimo 0,0575
    2025-26  K=6  medio 0,0301  massimo 0,1084
    2025-26  K=19 medio 0,0703  massimo 0,2784
    2026-27  K=2  medio 0,0129  massimo 0,0404 (stagione in corso, nessun vero)

Sul singolo giocatore a metà stagione la differenza arriva a 35 punti di
probabilità di presenza. Sull'accuratezza media, invece, le due forme **non si
distinguono**: il confronto appaiato dell'errore assoluto contro il tasso vero
del residuo contiene lo zero in cinque casi su sei (l'unico che lo esclude,
2025-26 K=3, favorisce `pres/38` di 0,003). Questo è atteso, perché `pres/38` è
una media pesata fra il tasso già realizzato e quello predetto, cioè uno
stimatore ristretto: l'argomento per il denominatore residuo è **definitorio e
decisionale**, non un guadagno di MAE misurato. Detto altrimenti: non si adotta
`(pres - pres_gk)/(38-K)` perché predice meglio, ma perché è la quantità di cui il
simulatore ha bisogno quando simula ciò che resta.

Nessuno dei file consumatori è di proprietà di questo incarico: la correzione è
dichiarata come dipendenza, non applicata qui.

Giornate rinviate e giornate parziali
-------------------------------------
Le giornate sono numeri di turno, non date: nel panel 2024-25 ci sono 325 righe
`stato_partita == "rinviata"` (376 nel 2023-24, 360 nel 2021-22, 319 nel 2025-26),
per esempio Bologna-Milan della giornata 9 giocata il 2025-02-27. Quindi «prime K
giornate» e «tutto ciò che è accaduto entro la data dell'asta» non coincidono. Lo
script misura, per ogni K richiesto, quante coppie (giornata, squadra) di turno
<= K sono giocate DOPO l'inizio del turno K+1 (informazione messa in `pres_gk` ma
non ancora disponibile a chi decide) e quante di turno > K sono giocate PRIMA
(giornate del residuo già note). I due conteggi stanno nel JSON di uscita sotto
`rinvii`. Misurato: a K = 3 e K = 6 sono zero in entrambe le stagioni; a K = 19
sono 10 coppie nel 2024-25 e 8 nel 2025-26 di turno <= 19 giocate dopo l'inizio
del turno 20, cioè `pres_gk` a metà stagione contiene fino a 10 squadra-partita
che a quella data non erano ancora state giocate. Per il 2026-27 a K = 2 sono
zero. Il conteggio è di coppie (giornata, squadra): una partita rinviata ne vale
due.

I due bracci
------------
* `modello`  — `pres` dal file di predizioni della stagione, con il suo `k`
               dichiarato; le predizioni sono addestrate SOLO sulle stagioni
               precedenti (mappa `TARGETS` di `f1_make_predictions`).
* `storia`   — la stessa quota di presenze usata dai generatori A e B in
               `scripts/l2_banco_confronto.py::storia_giocatori`: righe di panel
               con `stato_voto == "con_voto"` diviso righe di panel totali, tutte
               con `data < as_of`. È la «storia grezza» del manifesto.

Entrambi i bracci sono valutati **sugli stessi giocatori**, elencati nelle uscite.
Chi non ha nessuna riga di panel prima di `as_of` non ha una storia: non viene
riempito con zero né con la media, esce dal confronto appaiato e viene riportato a
parte (nel simulatore quei giocatori ricevono `p_play = 0.5`, si veda
`genera_per_giocatore`; quel ramo è misurato come braccio `storia_fallback05`).

Trattamento dei mancanti — nessun `fillna(0)` silenzioso
--------------------------------------------------------
* un giocatore del listone che non compare mai nei voti della stagione ha zero
  presenze **osservate**, non un mancante: resta nel confronto con vero = 0;
* un giocatore senza panel prima di `as_of` ha la storia **indefinita**: esce dal
  braccio appaiato (conteggio dichiarato in `esclusi`);
* un giocatore del listone assente dal file di predizioni esce da entrambi i
  bracci ed è contato in `esclusi`.
Va però segnalato che il bersaglio di addestramento, in
`f1_make_predictions::_season_points_frame`, usa `mid.map(pres).fillna(0.0)`:
per il modello un giocatore mai a referto e un giocatore uscito dalla Serie A a
gennaio sono lo stesso zero. È un `fillna(0)` dentro il bersaglio, in un file non
di proprietà di questo incarico: dichiarato come dipendenza.

Legittimità temporale
---------------------
Le predizioni lette provengono da `data/processed/b_predictions_{stagione}.json`,
prodotte con la mappa `TARGETS`: 2024-25 addestrato su 2021-22 e 2023-24, 2025-26
su 2021-22, 2023-24 e 2024-25, 2026-27 su tutto lo storico. Il braccio storia usa
solo righe con `data < as_of`. Con `--rifai-modello` lo script riadatta da sé il
solo sotto-modello delle presenze (CatBoost, gli stessi iperparametri e lo stesso
seme 7 di `catboost_values`) per un K scelto: serve a misurare il contratto del
residuo su una stagione conclusa, e riproduce esattamente il `pres` distribuito
quando K coincide (verificato sul 2024-25: max |differenza| 0,0 su 679 giocatori).

Che cosa questa misura NON dice
-------------------------------
La probabilità di **presenza a voto** non è la probabilità di **convocazione**.
La prima è l'esito dell'intera catena (convocazione, ingresso in campo, minuti
giocati, assegnazione o meno del voto, quindi anche il modello dei senza voto);
la seconda è solo il primo anello. Sostituire una propensione di convocazione al
posto di `pres/38` non produce la stessa quantità, e viceversa. Chi userà `pres`
dentro il cubo deve dichiarare quale delle due gli serve; qui si misura la prima,
perché la prima è quella che il modello addestra.

Uso
---
    PYTHONPATH="src;scripts" python scripts/l2_valuta_pres.py
    PYTHONPATH="src;scripts" python scripts/l2_valuta_pres.py --stagioni 2024-25 \
        --rifai-modello --k 3 6 19

Uscite in `data/l2/pres/`.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))
PROC = ROOT / "data" / "processed"
OUT = ROOT / "data" / "l2" / "pres"

GIORNATE = 38
# stagioni concluse con file di predizioni e panel completo: sono le uniche in cui
# il "vero" esiste. Il 2026-27 e' in corso (2 giornate con voti al 2026-09-08) e
# viene trattato a parte, senza MAE.
STAGIONI_VALUTABILI = ["2024-25", "2025-26"]


# ---------------------------------------------------------------- utilita'

def impronta(p: Path) -> dict:
    """SHA-256 (primi 16 caratteri), byte e data di modifica, come chiede la
    sezione 6 del protocollo v2 sulla tracciabilita' degli artefatti."""
    h = hashlib.sha256(p.read_bytes()).hexdigest()[:16]
    st = p.stat()
    return {"file": str(p.relative_to(ROOT)).replace("\\", "/"),
            "sha256_16": h, "byte": st.st_size,
            "modificato": datetime.fromtimestamp(st.st_mtime).strftime("%Y-%m-%d %H:%M")}


def mae(a: np.ndarray, b: np.ndarray) -> float:
    return float(np.mean(np.abs(a - b)))


def differenza_appaiata(e1: np.ndarray, e2: np.ndarray, seme: int = 20260908,
                        n_boot: int = 2000) -> dict:
    """Differenza media fra due serie di errori assoluti sugli STESSI giocatori,
    con intervallo di confidenza bootstrap al 95 % (ricampionamento dei
    giocatori, seme fisso). Serve a non chiamare «migliore» uno scarto di 0,003
    su qualche centinaio di osservazioni. Convenzione: `e1 - e2` negativo
    significa che il primo braccio sbaglia meno."""
    d = e1 - e2
    rng = np.random.default_rng(seme)
    idx = rng.integers(0, len(d), size=(n_boot, len(d)))
    m = d[idx].mean(axis=1)
    lo, hi = np.quantile(m, [0.025, 0.975])
    return {"differenza": round(float(d.mean()), 5),
            "ic_basso": round(float(lo), 5), "ic_alto": round(float(hi), 5),
            "n": int(len(d)),
            "esclude_zero": bool(lo > 0 or hi < 0)}


def corr(a: np.ndarray, b: np.ndarray) -> float:
    """Pearson. NaN se una delle due serie e' costante (succede su gruppi
    piccolissimi): riportata come None, mai come 0."""
    if len(a) < 3 or np.std(a) == 0 or np.std(b) == 0:
        return float("nan")
    return float(np.corrcoef(a, b)[0, 1])


# ------------------------------------------------------- bersaglio e bracci

def presenze_vere(stagione: str) -> tuple[pd.Series, pd.Series]:
    """(presenze a voto per giornata 1..K, presenze a voto totali) per master_id.

    Ricalcolate qui con la stessa regola di `f1_make_predictions._season_votes`:
    righe dei voti con `sv == 0`. Il +1 porta inviolata sul fantavoto non entra:
    riguarda i punti, non il conteggio delle presenze."""
    v = pd.read_parquet(PROC / f"votes_{stagione}.parquet")
    if "sv" in v.columns:
        v = v[v["sv"].fillna(0) == 0]
    v = v.copy()
    v["master_id"] = v["master_id"].astype(str)
    return v.groupby("master_id")["giornata"].apply(list), v.groupby("master_id").size()


def storia_quota(stagione: str, as_of: pd.Timestamp) -> tuple[pd.Series, pd.Series]:
    """Quota di presenze storica, identica a `l2_banco_confronto.storia_giocatori`:
    righe di panel con voto / righe di panel totali, tutte con `data < as_of`.

    Ritorna (quota, righe_disponibili). `righe_disponibili` serve a distinguere
    «storia assente» da «storia con quota 0»: sono cose diverse e non vanno
    confuse in un unico zero."""
    frames = []
    for f in sorted(PROC.glob("l2_panel_*.parquet")):
        frames.append(pd.read_parquet(f, columns=["master_id", "data", "stato_voto"]))
    P = pd.concat(frames, ignore_index=True)
    P["data"] = pd.to_datetime(P["data"])
    P["master_id"] = P["master_id"].astype(str)
    prima = P[P["data"] < as_of]
    tutte = prima.groupby("master_id").size()
    con_voto = prima[prima["stato_voto"] == "con_voto"].groupby("master_id").size()
    # solo chi ha almeno una riga con voto entra in `storia_giocatori`: la stessa
    # condizione del codice di produzione, riprodotta qui senza addolcirla
    idx = con_voto.index
    quota = (con_voto / tutte.reindex(idx)).astype(float)
    return quota, tutte.reindex(idx).astype(float)


def date_giornate(stagione: str) -> pd.DataFrame:
    """Coppie (giornata, squadra, data) della stagione dal panel: servono a
    separare il numero di turno dalla data effettiva (giornate rinviate)."""
    p = pd.read_parquet(PROC / f"l2_panel_{stagione}.parquet",
                        columns=["giornata", "squadra", "data", "stato_partita"])
    p["data"] = pd.to_datetime(p["data"])
    return p.drop_duplicates(["giornata", "squadra"]).reset_index(drop=True)


def conta_rinvii(cal: pd.DataFrame, k: int) -> dict:
    """Quante partite di turno <= K si giocano DOPO l'inizio del turno K+1
    (informazione conteggiata in `pres_gk` ma non disponibile a chi decide), e
    quante di turno > K si giocano PRIMA (giornate del residuo gia' note)."""
    if k <= 0 or k >= GIORNATE:
        return {"k": k, "as_of": None, "passate_dopo_il_taglio": 0,
                "residue_prima_del_taglio": 0}
    succ = cal[cal["giornata"] == k + 1]["data"]
    if succ.empty:
        return {"k": k, "as_of": None, "passate_dopo_il_taglio": 0,
                "residue_prima_del_taglio": 0}
    taglio = succ.min()
    dopo = int(((cal["giornata"] <= k) & (cal["data"] >= taglio)).sum())
    prima = int(((cal["giornata"] > k) & (cal["data"] < taglio)).sum())
    return {"k": k, "as_of": str(taglio.date()),
            "passate_dopo_il_taglio": dopo, "residue_prima_del_taglio": prima}


# --------------------------------------------------------------- valutazione

def gruppi(df: pd.DataFrame) -> list[tuple[str, pd.Series]]:
    """Tagli richiesti dall'incarico: complessivo, per ruolo, nuovi arrivi."""
    g = [("tutti", pd.Series(True, index=df.index))]
    for r in ("P", "D", "C", "A"):
        g.append((f"ruolo {r}", df["ruolo"] == r))
    g.append(("nuovi in serie A", df["nuovo_in_serie_a"] == 1))
    g.append(("non nuovi", df["nuovo_in_serie_a"] == 0))
    return g


def tabella(df: pd.DataFrame, bracci: list[str], vero: str) -> pd.DataFrame:
    righe = []
    for nome, m in gruppi(df):
        d = df[m]
        if len(d) == 0:
            continue
        r = {"gruppo": nome, "n": int(len(d)),
             "vero_medio": round(float(d[vero].mean()), 4)}
        for b in bracci:
            r[f"mae_{b}"] = round(mae(d[b].to_numpy(float), d[vero].to_numpy(float)), 4)
            c = corr(d[b].to_numpy(float), d[vero].to_numpy(float))
            r[f"corr_{b}"] = None if np.isnan(c) else round(c, 4)
        righe.append(r)
    return pd.DataFrame(righe)


def valuta(stagione: str, k_pred: int, pres_pred: pd.Series, pres_gk_pred: pd.Series,
           k_vero: int, etichetta: str) -> tuple[pd.DataFrame, pd.DataFrame, dict]:
    """Costruisce il confronto per una stagione a un dato K.

    `pres_pred` e `pres_gk_pred` sono indicizzate per master_id (str). `k_vero`
    e' il K con cui si taglia il bersaglio: coincide con `k_pred` salvo quando si
    vuole isolare l'effetto delle unita'."""
    lst = pd.read_parquet(PROC / f"players_{stagione}.parquet",
                          columns=["master_id", "nome", "ruolo", "nuovo_in_serie_a"])
    lst["master_id"] = lst["master_id"].astype(str)
    giornate_con_voto, _tot = presenze_vere(stagione)
    cal = date_giornate(stagione)
    as_of0 = cal["data"].min()

    # `as_of` del braccio storia: per K = 0 e' il primo calcio d'inizio della
    # stagione (identico a `l2_banco_confronto`); per K > 0 e' l'inizio del turno
    # K+1, cioe' il momento in cui si decide sapendo i primi K turni.
    if k_vero == 0:
        as_of = as_of0
    else:
        succ = cal[cal["giornata"] == k_vero + 1]["data"]
        as_of = succ.min() if not succ.empty else cal["data"].max()
    quota, righe_storia = storia_quota(stagione, as_of)

    df = lst.copy()
    lista = df["master_id"].map(giornate_con_voto)
    # vero: presenze a voto nelle giornate del residuo, sul numero di giornate
    # residue. Chi non compare nei voti ha zero presenze OSSERVATE (non mancanti).
    def _conta(gl, lo, hi):
        if not isinstance(gl, list):
            return 0
        return sum(1 for g in gl if lo <= g <= hi)
    df["pres_gk_vero"] = [_conta(g, 1, k_vero) for g in lista]
    df["pres_tot_vero"] = [_conta(g, 1, GIORNATE) for g in lista]
    df["pres_resto_vero"] = df["pres_tot_vero"] - df["pres_gk_vero"]
    df["vero_resto"] = df["pres_resto_vero"] / (GIORNATE - k_vero)
    df["vero_stagione"] = df["pres_tot_vero"] / GIORNATE

    df["pres_modello"] = df["master_id"].map(pres_pred)
    df["pres_gk_modello"] = df["master_id"].map(pres_gk_pred)
    df["storia_quota"] = df["master_id"].map(quota)
    df["storia_righe"] = df["master_id"].map(righe_storia)

    senza_pred = df["pres_modello"].isna()
    senza_storia = df["storia_quota"].isna()
    esclusi = {"listone": int(len(df)),
               "senza_predizione": int(senza_pred.sum()),
               "senza_storia_prima_di_as_of": int(senza_storia.sum()),
               "confronto_appaiato": int((~senza_pred & ~senza_storia).sum())}

    # tre bracci, tutti troncati in [0,1] come fa il generatore (0,03-0,97 li'):
    # qui il troncamento e' solo a [0,1] perche' la misura e' sul tasso, non sul
    # campionamento.
    d = df[~senza_pred & ~senza_storia].copy()
    d["b_modello_resto"] = np.clip(
        (d["pres_modello"] - d["pres_gk_modello"]) / (GIORNATE - k_pred), 0.0, 1.0)
    d["b_modello_pres38"] = np.clip(d["pres_modello"] / GIORNATE, 0.0, 1.0)
    d["b_storia"] = np.clip(d["storia_quota"], 0.0, 1.0)
    d["scarto_unita"] = d["b_modello_pres38"] - d["b_modello_resto"]

    bracci = ["b_modello_resto", "b_modello_pres38", "b_storia"]
    tab = tabella(d, bracci, "vero_resto")
    tab.insert(0, "stagione", stagione)
    tab.insert(1, "k", k_vero)
    tab.insert(2, "misura", etichetta)

    # braccio di controllo: chi non ha storia, nel simulatore, riceve p = 0,5.
    # Va misurato, non nascosto.
    fb = df[~senza_pred & senza_storia].copy()
    extra = {}
    if len(fb):
        fb["b_storia_fallback05"] = 0.5
        fb["b_modello_resto"] = np.clip(
            (fb["pres_modello"] - fb["pres_gk_modello"]) / (GIORNATE - k_pred), 0.0, 1.0)
        extra = {"n": int(len(fb)),
                 "vero_medio": round(float(fb["vero_resto"].mean()), 4),
                 "mae_modello": round(mae(fb["b_modello_resto"].to_numpy(float),
                                          fb["vero_resto"].to_numpy(float)), 4),
                 "mae_storia_fallback05": round(mae(fb["b_storia_fallback05"].to_numpy(float),
                                                    fb["vero_resto"].to_numpy(float)), 4)}

    # confronti appaiati sugli stessi giocatori: senza intervallo, differenze di
    # MAE di qualche millesimo verrebbero lette come vittorie.
    err = {b: np.abs(d[b].to_numpy(float) - d["vero_resto"].to_numpy(float))
           for b in bracci}
    appaiati = {
        "modello_resto contro storia":
            differenza_appaiata(err["b_modello_resto"], err["b_storia"]),
        "modello_resto contro modello_pres38":
            differenza_appaiata(err["b_modello_resto"], err["b_modello_pres38"]),
    }

    meta = {"stagione": stagione, "k_predizioni": k_pred, "k_bersaglio": k_vero,
            "as_of_storia": str(pd.Timestamp(as_of).date()),
            "denominatore_residuo": GIORNATE - k_vero,
            "esclusi": esclusi,
            "senza_storia_fallback05": extra,
            "rinvii": conta_rinvii(cal, k_vero),
            "confronti_appaiati": appaiati,
            "scarto_unita_medio": round(float(np.mean(np.abs(d["scarto_unita"]))), 4),
            "scarto_unita_massimo": round(float(np.max(np.abs(d["scarto_unita"]))), 4)}
    return d, tab, meta


def scarto_unita_vivo(stagione: str) -> dict:
    """Stagione in corso: il vero non esiste ancora, quindi niente MAE. Si misura
    solo di quanto `pres/38` e `(pres - pres_gk)/(38 - K)` differiscono, che e'
    la quantita' su cui si decide il contratto del residuo."""
    pred_path = PROC / f"b_predictions_{stagione}.json"
    pr = json.loads(pred_path.read_text("utf-8"))
    ks = sorted({int(v["k"]) for v in pr.values()})
    if len(ks) != 1:
        raise SystemExit(f"{pred_path.name}: k non unico ({ks})")
    k = ks[0]
    lst = pd.read_parquet(PROC / f"players_{stagione}.parquet",
                          columns=["master_id", "ruolo"])
    lst["master_id"] = lst["master_id"].astype(str)
    pres = lst["master_id"].map({m: float(v["pres"]) for m, v in pr.items()})
    gk = lst["master_id"].map({m: float(v["pres_gk"]) for m, v in pr.items()})
    ok = pres.notna() & gk.notna()
    a = np.clip(pres[ok] / GIORNATE, 0.0, 1.0)
    b = np.clip((pres[ok] - gk[ok]) / (GIORNATE - k), 0.0, 1.0)
    cal = date_giornate(stagione)
    return {"stagione": stagione, "k": k, "n": int(ok.sum()),
            "denominatore_residuo": GIORNATE - k,
            "scarto_unita_medio": round(float(np.mean(np.abs(a - b))), 4),
            "scarto_unita_massimo": round(float(np.max(np.abs(a - b))), 4),
            "scarto_unita_p90": round(float(np.quantile(np.abs(a - b), 0.9)), 4),
            "rinvii": conta_rinvii(cal, k)}


# ------------------------------------------------------------ modello a K > 0

def rifai_presenze(stagione: str, k: int) -> tuple[pd.Series, pd.Series, dict]:
    """Riadatta il SOLO sotto-modello delle presenze di `catboost_values`, con gli
    stessi iperparametri (500 iterazioni, lr 0,05, profondita' 4, l2 6, seme 7),
    le stesse feature (`xmat_valore`) e lo stesso troncamento [0, 38-K].

    Serve per K > 0 su una stagione conclusa, dove il file di predizioni non
    esiste. Addestra solo sulle stagioni precedenti della mappa `TARGETS`, come
    all'asta vera. Non tocca `f1_make_predictions.py`: lo importa."""
    import f1_make_predictions as F
    from catboost import CatBoostRegressor
    train_ss = F.TARGETS[stagione]
    frames = {s: F._season_points_frame(s, k) for s in train_ss}
    tr = pd.concat(frames.values(), ignore_index=True)
    te = F._season_points_frame(stagione, k)
    # `allow_writing_files=False`: senza questo CatBoost scrive i log di
    # addestramento in `catboost_info/` nella cartella di lavoro, cioe' nella
    # radice del progetto, che non e' di proprieta' di questo script. Non tocca
    # il modello: verificato che con e senza il flag il `pres` riprodotto a K=0
    # coincide con quello distribuito (max |differenza| 0,0 su 679 giocatori).
    mp = CatBoostRegressor(iterations=500, learning_rate=0.05, depth=4,
                           l2_leaf_reg=6, random_seed=7, verbose=False,
                           allow_writing_files=False)
    mp.fit(F.xmat_valore(tr), tr["pres_resto"])
    resto = np.clip(np.asarray(mp.predict(F.xmat_valore(te)), dtype=float),
                    0.0, F.GIORNATE - k)
    mid = te["master_id"].astype(str)
    pres_gk = te["pres_gk"].to_numpy(dtype=float)
    prov = {"stagione": stagione, "k": k, "addestrato_su": train_ss,
            "modello": "CatBoostRegressor(iterations=500, learning_rate=0.05, "
                       "depth=4, l2_leaf_reg=6, random_seed=7)",
            "bersaglio": "pres_resto = presenze a voto nelle giornate K+1..38"}
    return (pd.Series(pres_gk + resto, index=mid.to_numpy()),
            pd.Series(pres_gk, index=mid.to_numpy()), prov)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--stagioni", nargs="*", default=STAGIONI_VALUTABILI)
    ap.add_argument("--rifai-modello", action="store_true",
                    help="riadatta il sotto-modello delle presenze ai K indicati")
    ap.add_argument("--k", nargs="*", type=int, default=[3, 6, 19])
    ap.add_argument("--vive", nargs="*", default=["2026-27"],
                    help="stagioni in corso: solo scarto di unita', nessun MAE")
    a = ap.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)

    ingressi, tabelle, righe, meta_tutti = [], [], [], []
    for f in ["data/l3/MANIFESTO.json"]:
        ingressi.append(impronta(ROOT / f))

    for s in a.stagioni:
        pred_path = PROC / f"b_predictions_{s}.json"
        for p in (pred_path, PROC / f"votes_{s}.parquet",
                  PROC / f"players_{s}.parquet", PROC / f"l2_panel_{s}.parquet"):
            ingressi.append(impronta(p))
        pr = json.loads(pred_path.read_text("utf-8"))
        ks = sorted({int(v["k"]) for v in pr.values()})
        if len(ks) != 1:
            raise SystemExit(f"{pred_path.name}: k non unico ({ks})")
        k_file = ks[0]
        pres = pd.Series({m: float(v["pres"]) for m, v in pr.items()})
        pres_gk = pd.Series({m: float(v["pres_gk"]) for m, v in pr.items()})

        d, tab, meta = valuta(s, k_file, pres, pres_gk, k_file,
                              f"predizioni distribuite (k={k_file})")
        d.insert(0, "stagione", s)
        d.insert(1, "k", k_file)
        d.insert(2, "misura", f"distribuite k={k_file}")
        righe.append(d)
        tabelle.append(tab)
        meta["origine_predizioni"] = str(pred_path.relative_to(ROOT)).replace("\\", "/")
        meta_tutti.append(meta)

        if a.rifai_modello:
            for k in a.k:
                pres_k, gk_k, prov = rifai_presenze(s, k)
                d2, tab2, meta2 = valuta(s, k, pres_k, gk_k, k,
                                         f"riadattato (k={k})")
                d2.insert(0, "stagione", s)
                d2.insert(1, "k", k)
                d2.insert(2, "misura", f"riadattato k={k}")
                righe.append(d2)
                tabelle.append(tab2)
                meta2["origine_predizioni"] = "riadattato in questo script"
                meta2["provenienza"] = prov
                meta_tutti.append(meta2)

    vive = []
    for s in a.vive:
        p = PROC / f"b_predictions_{s}.json"
        if not p.exists():
            continue
        ingressi.append(impronta(p))
        ingressi.append(impronta(PROC / f"players_{s}.parquet"))
        vive.append(scarto_unita_vivo(s))

    dett = pd.concat(righe, ignore_index=True)
    sint = pd.concat(tabelle, ignore_index=True)
    cols = ["stagione", "k", "misura", "master_id", "nome", "ruolo",
            "nuovo_in_serie_a", "pres_modello", "pres_gk_modello",
            "pres_gk_vero", "pres_tot_vero", "pres_resto_vero",
            "vero_resto", "vero_stagione", "storia_quota", "storia_righe",
            "b_modello_resto", "b_modello_pres38", "b_storia", "scarto_unita"]
    dett[cols].to_csv(OUT / "valuta_pres_dettaglio.csv", index=False)
    sint.to_csv(OUT / "valuta_pres_sintesi.csv", index=False)

    rap = {"generato": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
           "comando": "PYTHONPATH=\"src;scripts\" python scripts/l2_valuta_pres.py"
                      + (" --rifai-modello --k " + " ".join(str(x) for x in a.k)
                         if a.rifai_modello else ""),
           "bersaglio": "presenze a voto (giornate con voto, sv esclusi) / giornate residue",
           "input_hashes": ingressi,
           "misure": meta_tutti,
           "stagioni_in_corso": vive,
           "sintesi": sint.to_dict(orient="records")}
    (OUT / "valuta_pres.json").write_text(
        json.dumps(rap, ensure_ascii=False, indent=1), encoding="utf-8")

    with pd.option_context("display.width", 200, "display.max_columns", 40):
        print(sint.to_string(index=False))
    for m in meta_tutti:
        print(f"\n{m['stagione']} k={m['k_bersaglio']} as_of={m['as_of_storia']} "
              f"denominatore={m['denominatore_residuo']}")
        print(f"  esclusi: {m['esclusi']}")
        print(f"  rinvii: {m['rinvii']}")
        print(f"  scarto unita' pres/38 contro resto/(38-k): medio "
              f"{m['scarto_unita_medio']}, massimo {m['scarto_unita_massimo']}")
        if m["senza_storia_fallback05"]:
            print(f"  senza storia (p=0,5 nel simulatore): {m['senza_storia_fallback05']}")
        for nome, r in m["confronti_appaiati"].items():
            print(f"  appaiato {nome}: {r['differenza']:+.5f} "
                  f"[{r['ic_basso']:+.5f}, {r['ic_alto']:+.5f}] n={r['n']} "
                  f"{'esclude lo zero' if r['esclude_zero'] else 'contiene lo zero'}")
    for v in vive:
        print(f"\n{v['stagione']} in corso, k={v['k']} (nessun vero, nessun MAE): "
              f"scarto unita' medio {v['scarto_unita_medio']}, p90 {v['scarto_unita_p90']}, "
              f"massimo {v['scarto_unita_massimo']} su {v['n']} giocatori; "
              f"rinvii {v['rinvii']}")
    print(f"\nuscite in {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
