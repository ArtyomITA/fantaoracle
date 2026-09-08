"""Banco: tre generatori di stagione a confronto, stesso universo e stesse regole.

Confronta, sulla stessa stagione e con le stesse informazioni disponibili alla
stessa data:

  A. **baseline semplice**   ogni giocatore estrae dai propri fantavoti passati,
                             con la sua quota di presenze. Nessun legame fra
                             compagni, nessuna memoria.
  B. **vecchio simulatore**  la meccanica di `fantabot.montecarlo`: campioni
                             appaiati (voto, fantavoto), incertezza di stima
                             estratta una volta per stagione, catena della
                             disponibilita' con memoria, shock di squadra unico
                             (scarto 0,25).
  C. **cubo TABELLINO**      `fantabot.tabellino`: risultato della partita,
                             undici, eventi, voto condizionato.

Tutti e tre ricevono le STESSE informazioni (le stagioni precedenti alla data
limite) e producono la stessa cosa: fantavoto e voto puro di ogni giocatore in
ogni giornata. Il confronto e' con la stagione davvero giocata.

Nota sul confronto: B non e' la pipeline di produzione (che aggiunge i modelli
di prezzo e valore), ma la sua **meccanica generativa** alimentata con le stesse
informazioni del cubo. E' l'unico modo di isolare il meccanismo: se B ricevesse
le predizioni del modello valore e C no, la differenza misurerebbe i modelli,
non i generatori.

## Che cosa misura

  livello        media e scarto dei punti per giocatore-giornata, per ruolo
  distribuzione  CRPS sul punteggio del giocatore-giornata; PIT randomizzato
                 (obbligatorio: i fantavoti sono discreti a passi di 0,5)
  presenze       quota di giornate con voto, Brier e calibrazione
  dipendenza     correlazioni fra compagni per coppia di ruoli; variogramma
                 sull'insieme dei ruoli di una squadra
  fantacalcio    punteggio di dieci rose vere per giornata, gol da fasce,
                 sostituzioni usate, quante volte scatta il modificatore

Le rose di prova sono generate una volta sola con un seme fissato e sono le
stesse per i tre generatori: e' un confronto appaiato.

Uso:
  python scripts/l2_banco_confronto.py 2024-25 --sims 30
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
PROC = ROOT / "data" / "processed"
OUT = ROOT / "data" / "l2"

from fantabot.montecarlo import TEAM_SHOCK_SD, logit_base, _offset, MAX_RUN  # noqa: E402
from fantabot.rules import CLEAN_SHEET_BONUS, MAX_SUBS, QUOTAS  # noqa: E402
from fantabot.season.lineup import goals_from_points, pick_lineup, score_giornata  # noqa: E402
from fantabot.tabellino import eventi as ev            # noqa: E402
from fantabot.tabellino import generatore as gen       # noqa: E402
from fantabot.tabellino import partecipazione as pa    # noqa: E402
from fantabot.tabellino import voto as vt              # noqa: E402
from fantabot.tabellino import configurazione as cfg          # noqa: E402
from fantabot.tabellino.partita import pesi_decadimento, stima as stima_partita  # noqa: E402

GIORNATE = 38


# --------------------------------------------------------------------------
# generatori A e B: campionamento per giocatore
# --------------------------------------------------------------------------

def storia_giocatori(P: pd.DataFrame, as_of: str) -> dict:
    """Campioni storici (fantavoto, voto) e quota di presenze per giocatore."""
    d = P[(P.data < pd.Timestamp(as_of)) & (P.stato_voto == "con_voto")]
    tutte = P[P.data < pd.Timestamp(as_of)]
    n_possibili = tutte.groupby("master_id").size()
    fuori = {}
    per_ruolo = {}
    d = d.copy()
    d["gs"] = pd.to_numeric(d.get("gol_subiti"), errors="coerce").fillna(0.0)
    for ruolo, g in d.groupby("ruolo"):
        per_ruolo[ruolo] = (g["fantavoto"].to_numpy(float),
                            g["voto"].to_numpy(float),
                            g["gs"].to_numpy(float))
    for mid, g in d.groupby("master_id"):
        fuori[mid] = {
            "fv": g["fantavoto"].to_numpy(float),
            "v": g["voto"].to_numpy(float),
            # gol subiti della stessa riga campionata: servono al bonus porta
            # inviolata, che e' una regola della LEGA e non sta dentro il
            # fantavoto della fonte
            "gs": g["gs"].to_numpy(float),
            "p": float(len(g) / max(int(n_possibili.get(mid, len(g))), 1)),
            "ruolo": g["ruolo"].iloc[0],
        }
    return fuori, per_ruolo


def genera_per_giocatore(storia, per_ruolo, giocatori, ruolo, squadra,
                         n_sims, seme, memoria: bool, shock: float,
                         sigma_stima: float) -> dict:
    """Generatore A (memoria=False, shock=0) e B (memoria=True, shock=0,25).

    I numeri casuali sono indicizzati per giocatore e per squadra, come nel
    cubo: le tre stagioni simulate sono confrontabili fra loro."""
    n = len(giocatori)
    FV = np.zeros((n_sims, GIORNATE, n), dtype=np.float32)
    VV = np.zeros_like(FV)
    GS = np.zeros(FV.shape, dtype=np.int8)
    GI = np.zeros(FV.shape, dtype=bool)
    squadre = sorted(set(squadra.get(p, "") for p in giocatori))
    for s in range(n_sims):
        sh = {}
        if shock > 0:
            for t in squadre:
                sh[t] = gen.rng_di(seme, s, f"shocksq:{t}").standard_normal(GIORNATE) * shock
        for j, pid in enumerate(giocatori):
            st = storia.get(pid)
            if st is None:
                fv, v, gs = per_ruolo.get(ruolo.get(pid, "C"), per_ruolo["C"])
                p_play = 0.5
            else:
                fv, v, gs, p_play = st["fv"], st["v"], st["gs"], st["p"]
            if len(fv) < 8:
                fv, v, gs = per_ruolo.get(ruolo.get(pid, "C"), per_ruolo["C"])
            r = gen.rng_di(seme, s, f"gio:{pid}")
            eps = float(r.standard_normal() * sigma_stima)
            p_play = float(min(0.97, max(0.03, p_play + r.standard_normal() * 0.10)))
            u_gioca = r.random(GIORNATE)
            u_camp = r.random(GIORNATE)
            t = squadra.get(pid, "")
            if memoria:
                base = logit_base(p_play)
                era, run = (u_gioca[0] < p_play), 1
            for g in range(GIORNATE):
                if memoria:
                    pg = 1.0 / (1.0 + np.exp(-(base + _offset(era, run))))
                    gioca = u_gioca[g] < pg
                    run = run + 1 if gioca == era else 1
                    era = gioca
                else:
                    gioca = u_gioca[g] < p_play
                if not gioca:
                    continue
                k = int(u_camp[g] * len(fv))
                ts = float(sh[t][g]) if shock > 0 and t in sh else 0.0
                FV[s, g, j] = fv[k] + eps + ts
                VV[s, g, j] = v[k] + eps * 0.4 + ts
                GS[s, g, j] = int(min(gs[k], 127))
                GI[s, g, j] = True
    return {"fantavoto": FV, "voto": VV, "gioca": GI, "gol_subiti": GS,
            "giocatori": giocatori}


# --------------------------------------------------------------------------
# metriche
# --------------------------------------------------------------------------

def crps_campionario(campioni: np.ndarray, y: float) -> float:
    """CRPS stimato da campioni: E|X-y| - 0.5 E|X-X'|."""
    x = np.asarray(campioni, dtype=float)
    if len(x) < 2:
        return float("nan")
    a = np.mean(np.abs(x - y))
    xs = np.sort(x)
    n = len(xs)
    # E|X-X'| calcolabile in O(n log n) dagli ordinamenti
    b = 2.0 * np.sum((2 * np.arange(1, n + 1) - n - 1) * xs) / (n * n)
    return float(a - 0.5 * b)


def pit_randomizzato(campioni: np.ndarray, y: float, u: float) -> float:
    """PIT per esiti discreti: F(y-) + u * P(Y=y). Senza la randomizzazione
    l'istogramma sembrerebbe deforme anche con un modello perfetto."""
    x = np.asarray(campioni, dtype=float)
    minore = float(np.mean(x < y))
    uguale = float(np.mean(x == y))
    return minore + u * uguale


def rose_di_prova(listone: pd.DataFrame, n_rose: int, seme: int) -> list:
    """Dieci rose legali (3P/8D/8C/6A) estratte una volta sola.

    Non sono ottimizzate: servono a misurare il comportamento del generatore
    sulle quantita' del fantacalcio, non a giudicare una strategia d'asta."""
    rng = np.random.default_rng(seme)
    rose = []
    for _ in range(n_rose):
        r = {}
        for ruolo, quanti in QUOTAS.items():
            cand = listone[listone.ruolo == ruolo].master_id.to_numpy()
            r[ruolo] = list(rng.choice(cand, size=quanti, replace=False))
        rose.append(r)
    return rose


def punteggi_rose(rose, fantavoto, voto, gioca, giocatori, s,
                  gol_subiti=None, ruolo=None) -> np.ndarray:
    """Punteggio per giornata di ogni rosa, con le regole della lega.

    Il **bonus porta inviolata** (+1 al portiere che gioca senza subire gol) e'
    una regola della lega e non sta dentro il fantavoto della fonte: in
    produzione viene applicato quando si costruisce il pack
    (`scripts/f2_build_packs.py:192`). In questo banco non veniva applicato in
    nessun punto, ne' all'osservato ne' al simulato: 0,297 punti a giornata per
    rosa, 10,38 su 35 giornate. Ora si applica qui, una volta sola e allo
    stesso modo per tutti i generatori e per la stagione vera.

    Serve `gol_subiti` per sapere a chi spetta. Se manca, il bonus non si
    applica e la funzione lo dichiara alzando un errore: ignorarlo in silenzio
    e' esattamente il difetto che si sta correggendo."""
    if gol_subiti is None:
        raise ValueError(
            "punteggi_rose senza `gol_subiti`: il bonus porta inviolata non e' "
            "applicabile. Passa l'array dei gol subiti, oppure chiama con "
            "gol_subiti=False per dichiarare esplicitamente che quel bonus "
            "non entra nel punteggio.")
    applica = gol_subiti is not False
    ix = {pid: i for i, pid in enumerate(giocatori)}
    fuori = np.zeros((len(rose), GIORNATE))
    for ir, rosa in enumerate(rose):
        ids = [pid for r in QUOTAS for pid in rosa[r]]
        idx = {pid: ix.get(pid) for pid in ids}
        forma, forma_v = {}, {}
        somma, conta, somma_v = {}, {}, {}
        prec = None
        for g in range(GIORNATE):
            punti, voti = {}, {}
            for pid in ids:
                j = idx[pid]
                if j is not None and gioca[s, g, j]:
                    pt = float(fantavoto[s, g, j])
                    if (applica and (ruolo or {}).get(pid) == "P"
                            and float(gol_subiti[s, g, j]) == 0.0):
                        pt += CLEAN_SHEET_BONUS
                    punti[str(pid)] = pt
                    voti[str(pid)] = float(voto[s, g, j])
            rosa_str = {r: [str(p) for p in rosa[r]] for r in QUOTAS}
            _, tit, pan = pick_lineup(rosa_str, forma, forma_v, True, prec)
            p, _ = score_giornata(tit, pan, punti, MAX_SUBS, voti, True)
            fuori[ir, g] = p
            prec = set(punti.keys())
            for pid, v in punti.items():
                somma[pid] = somma.get(pid, 0.0) + v
                conta[pid] = conta.get(pid, 0) + 1
                somma_v[pid] = somma_v.get(pid, 0.0) + voti[pid]
                forma[pid] = somma[pid] / conta[pid]
                forma_v[pid] = somma_v[pid] / conta[pid]
    return fuori


def correlazioni(fantavoto, voto, gioca, giocatori, ruolo, squadra, s) -> dict:
    d = []
    for g in range(GIORNATE):
        idx = np.nonzero(gioca[s, g])[0]
        for i in idx:
            pid = giocatori[i]
            d.append((g, ruolo.get(pid, "C"), squadra.get(pid, ""),
                      float(voto[s, g, i])))
    df = pd.DataFrame(d, columns=["giornata", "ruolo", "squadra", "voto"])
    fuori = {}
    for et, ra, rb in [("portiere-difensori", ["P"], ["D"]),
                       ("difensori", ["D"], ["D"]),
                       ("centrocampisti", ["C"], ["C"]),
                       ("attaccanti", ["A"], ["A"])]:
        vals = []
        for _, gg in df.groupby(["giornata", "squadra"]):
            a = gg[gg.ruolo.isin(ra)]["voto"].to_numpy()
            b = gg[gg.ruolo.isin(rb)]["voto"].to_numpy()
            if ra == rb:
                for i in range(len(a)):
                    for j in range(i + 1, len(a)):
                        vals.append((a[i], a[j]))
            else:
                for x in a:
                    for y in b:
                        vals.append((x, y))
        v = np.array(vals) if len(vals) >= 50 else None
        fuori[et] = (float(np.corrcoef(v[:, 0], v[:, 1])[0, 1]) if v is not None
                     else float("nan"))
    return fuori


def differenza_appaiata(a: np.ndarray, b: np.ndarray, seme: int,
                        n_boot: int = 2000) -> dict:
    """Differenza media `a - b` fra due misure appaiate, con intervallo.

    Le due misure devono venire dalle stesse osservazioni nello stesso ordine:
    e' quello che rende lecito il confronto riga per riga. Il ricampionamento
    e' sulle osservazioni, non sui due bracci separatamente, perche' la
    correlazione fra i bracci e' proprio quello che l'appaiamento sfrutta."""
    a = np.asarray(a, dtype=float)
    b = np.asarray(b, dtype=float)
    if a.shape != b.shape:
        raise ValueError(f"misure non appaiabili: {a.shape} contro {b.shape}")
    d = a - b
    d = d[np.isfinite(d)]
    if d.size == 0:
        raise ValueError("nessuna osservazione finita nella differenza")
    rng = np.random.default_rng(seme)
    idx = rng.integers(0, d.size, size=(n_boot, d.size))
    medie = d[idx].mean(axis=1)
    lo, hi = np.percentile(medie, [2.5, 97.5])
    return {"differenza": float(d.mean()), "ic_basso": float(lo),
            "ic_alto": float(hi), "n": int(d.size),
            "esclude_zero": bool(lo > 0 or hi < 0)}


def verdetto_appaiato(per_osservazione: dict, seme: int):
    """Confronti di F7 con la regola scritta nei criteri, sezione 3.7.

    Due confronti: `C` contro `B'` (informazione comparabile) e `C` contro `B`
    (sistemi completi). Piu' basso e' meglio sia per CRPS sia per Brier, quindi
    una differenza `C - altro` negativa e' a favore di `C`; conta solo se
    l'intervallo esclude lo zero."""
    nomi = list(per_osservazione)
    c = next((n for n in nomi if n.startswith("C ")), None)
    if c is None:
        return None
    coppie = [(n, "informazione comparabile" if n.startswith("B'")
               else "sistemi completi")
              for n in nomi if n.startswith("B")]
    fuori = []
    for altro, tipo in coppie:
        for misura in ("crps", "brier"):
            r = differenza_appaiata(per_osservazione[c][misura],
                                    per_osservazione[altro][misura], seme)
            if not r["esclude_zero"]:
                esito = "inconcludente"
            elif r["differenza"] < 0:
                esito = "C migliore"
            else:
                esito = "C peggiore"
            fuori.append({"confronto": f"{c} contro {altro}", "tipo": tipo,
                          "misura": misura,
                          "differenza": round(r["differenza"], 5),
                          "ic_basso": round(r["ic_basso"], 5),
                          "ic_alto": round(r["ic_alto"], 5),
                          "n": r["n"], "esito": esito})
    return pd.DataFrame(fuori)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("stagione", nargs="?", default="2024-25")
    ap.add_argument("--sims", type=int, default=30)
    ap.add_argument("--seme", type=int, default=20260907)
    ap.add_argument("--rose", type=int, default=10)
    a = ap.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)

    P = pd.concat([pd.read_parquet(f) for f in
                   sorted(PROC.glob("l2_panel_*.parquet"))], ignore_index=True)
    P["data"] = pd.to_datetime(P["data"])
    part = pd.read_parquet(PROC / "l2_partite.parquet")
    part["data"] = pd.to_datetime(part["data"])
    cal = part[part.stagione == a.stagione].copy()
    as_of = str(cal.data.min().date())
    lst = pd.read_parquet(PROC / f"players_{a.stagione}.parquet",
                          columns=["master_id", "ruolo", "squadra"])
    sigle = json.loads((PROC / "_match" / "team_maps.json").read_text("utf-8"))
    inv = {v: k for k, v in sigle.get(a.stagione, {}).items()}
    lst["squadra_estesa"] = lst["squadra"].map(inv).fillna(lst["squadra"])
    ruolo = dict(zip(lst.master_id, lst.ruolo))
    squadra = dict(zip(lst.master_id, lst.squadra_estesa))
    rose_liste = {sq: list(g.master_id) for sq, g in lst.groupby("squadra_estesa")}
    giocatori = sorted(lst.master_id)
    print(f"stagione {a.stagione} | as_of {as_of} | {a.sims} scenari | "
          f"{len(giocatori)} giocatori")

    Ppre = P[P.data < pd.Timestamp(as_of)]
    storia, per_ruolo = storia_giocatori(P, as_of)

    generatori = {}
    t0 = time.time()
    generatori["A baseline semplice"] = genera_per_giocatore(
        storia, per_ruolo, giocatori, ruolo, squadra, a.sims, a.seme,
        memoria=False, shock=0.0, sigma_stima=0.0)
    generatori["B vecchio simulatore"] = genera_per_giocatore(
        storia, per_ruolo, giocatori, ruolo, squadra, a.sims, a.seme,
        memoria=True, shock=TEAM_SHOCK_SD, sigma_stima=0.45)
    # variante di produzione: le presenze arrivano dal modello valore
    # (`pres` nelle predizioni), non dalla sola storia. Usa piu' informazione
    # degli altri due, e va letta sapendolo.
    pred = PROC / f"b_predictions_{a.stagione}.json"
    if pred.exists():
        pr = json.loads(pred.read_text("utf-8"))
        storia_pres = {k: dict(v) for k, v in storia.items()}
        n_sost = 0
        for pid in list(storia_pres):
            q = pr.get(str(pid)) or pr.get(pid)
            if q and q.get("pres"):
                storia_pres[pid]["p"] = float(min(0.97, max(0.03,
                                                            float(q["pres"]) / GIORNATE)))
                n_sost += 1
        generatori["B' vecchio + presenze del modello"] = genera_per_giocatore(
            storia_pres, per_ruolo, giocatori, ruolo, squadra, a.sims, a.seme,
            memoria=True, shock=TEAM_SHOCK_SD, sigma_stima=0.45)
        print(f"  presenze dal modello per {n_sost} giocatori")
    print(f"  A e B generati in {time.time() - t0:.1f} s")

    t0 = time.time()
    # stessa procedura del cubo e del banco del modello di partita
    mp, conf, impronta = cfg.costruisci_modello_partita(
        # `squadre=None`: la procedura prende l'unione fra le squadre
        # dell'addestramento e quelle del calendario bersaglio. Passando solo
        # quelle del calendario si perdono le squadre storiche (Verona, Empoli,
        # ...) e la stima del prior dagli xG va in errore.
        part, as_of, squadre=None,
        stagione_bersaglio=a.stagione, con_incertezza=True,
        percorsi_ingresso=[str(PROC / "l2_partite.parquet")],
        etichetta=f"banco confronto {a.stagione}")
    print(f"  configurazione del modello: {impronta[:12]} | "
          f"xi {conf.iperparametri["xi"]} | "
          f"lam_pen {conf.iperparametri["lam_pen"]}")
    m_part = pa.stima(Ppre)
    m_ev = ev.stima(Ppre)
    m_voto = vt.stima(Ppre, "individuale")
    m_part.ruolo.update(ruolo)
    m_ev.ruolo.update(ruolo)
    f_ev = ROOT / "data/raw/transfermarkt/_download/game_events.csv.gz"
    storico, _filtro = cfg.partite_di_addestramento(part, as_of)
    id_st = set(pd.to_numeric(storico.game_id, errors="coerce").dropna().astype(int))
    if f_ev.exists() and id_st:
        m_ev.minuti_gol = ev.minuti_gol_da_eventi(f_ev, id_st)
    struttura = vt.struttura_dipendenza(Ppre, m_voto)
    fasce_sv = vt.stima_senza_voto(Ppre)
    # bersagli di correlazione dai dati di addestramento, mai dalla stagione
    # di prova; poi la stessa calibrazione che usa `l2_genera_cubo.py`
    tr = Ppre[Ppre.stato_voto == "con_voto"].copy()
    tr["ruolo"] = tr["ruolo"].astype(str).str.upper()
    bers = {}
    for _, sub in tr.groupby("stagione"):
        for k, v in vt.correlazioni_osservate(sub, "voto").items():
            bers.setdefault(k, []).append(v)
    bers = {k: float(np.nanmean(v)) for k, v in bers.items()}
    struttura = gen.calibra_dipendenza(struttura, bers, cal, rose_liste, mp,
                                       m_part, m_ev, m_voto, fasce_sv, a.seme,
                                       ruolo, squadra)
    print("  bersagli di correlazione: "
          + ", ".join(f"{k} {v:.4f}" for k, v in bers.items()))
    cubo = gen.genera(cal, rose_liste, mp, m_part, m_ev, m_voto,
                      n_sims=a.sims, seme=a.seme, dipendenza=struttura,
                      fasce_sv=fasce_sv, verifica=True)
    ixc = {pid: i for i, pid in enumerate(cubo.giocatori)}
    ordine = [ixc.get(pid) for pid in giocatori]
    def riordina(A):
        B = np.zeros((a.sims, GIORNATE, len(giocatori)), dtype=A.dtype)
        for j, k in enumerate(ordine):
            if k is not None:
                B[:, :len(cubo.giornate), j] = A[:, :, k]
        return B
    generatori["C cubo TABELLINO"] = {
        "fantavoto": riordina(cubo.fantavoto), "voto": riordina(cubo.voto),
        "gioca": riordina(cubo.gioca),
        "gol_subiti": (riordina(cubo.gol_subiti)
                       if getattr(cubo, "gol_subiti", None) is not None else None),
        "giocatori": giocatori}
    print(f"  C generato in {time.time() - t0:.1f} s "
          f"({cubo.diagnostica['n_problemi_coerenza']} problemi di coerenza)")

    # --- verita': la stagione davvero giocata ---
    oss = P[(P.stagione == a.stagione) & (P.stato_voto == "con_voto")].copy()
    oss["gol_subiti"] = pd.to_numeric(oss.get("gol_subiti"),
                                      errors="coerce").fillna(0.0)
    ix = {pid: i for i, pid in enumerate(giocatori)}
    VER = np.zeros((GIORNATE, len(giocatori)))
    VER_V = np.zeros((GIORNATE, len(giocatori)))
    VER_GS = np.zeros((GIORNATE, len(giocatori)))
    GIO = np.zeros((GIORNATE, len(giocatori)), dtype=bool)
    for r in oss.itertuples(index=False):
        j = ix.get(r.master_id)
        g = int(r.giornata) - 1
        if j is not None and 0 <= g < GIORNATE:
            VER[g, j] = float(r.fantavoto)
            VER_V[g, j] = float(r.voto)
            VER_GS[g, j] = float(getattr(r, "gol_subiti", 0.0) or 0.0)
            GIO[g, j] = True

    rose_prova = rose_di_prova(lst, a.rose, a.seme)
    veri_rose = punteggi_rose(rose_prova, VER[None, ...], VER_V[None, ...],
                              GIO[None, ...], giocatori, 0,
                              gol_subiti=VER_GS[None, ...], ruolo=ruolo)

    rng = np.random.default_rng(a.seme)
    # tutte le coppie (giocatore, giornata) dell'universo, non solo quelle in
    # cui il giocatore ha davvero giocato: selezionare sull'esito vero
    # premierebbe il generatore che fa giocare tutti. Chi non gioca vale 0,
    # che e' quello che vale nel fantacalcio.
    coppie = np.array([(g, j) for g in range(GIORNATE)
                       for j in range(len(giocatori))])
    scelte = coppie[rng.choice(len(coppie), size=min(6000, len(coppie)),
                               replace=False)]
    u_pit = rng.random(len(scelte))

    riga = []
    # contributi per osservazione, conservati per il verdetto appaiato di F7
    # (criteri, sezione 3.7): le coppie campionate sono le stesse per tutti i
    # generatori, quindi le differenze si possono fare riga per riga.
    per_osservazione = {}
    for nome, G in generatori.items():
        fv, gi = G["fantavoto"], G["gioca"]
        vals = fv[gi]
        crps, pit = [], []
        for t, (g, j) in enumerate(scelte):
            camp_tutti = np.where(gi[:, g, j], fv[:, g, j], 0.0)
            y = VER[g, j] if GIO[g, j] else 0.0
            crps.append(crps_campionario(camp_tutti, y))
            pit.append(pit_randomizzato(camp_tutti, y, u_pit[t]))
        # presenze su TUTTE le coppie giocatore-giornata
        p_sim = gi.mean(0)
        brier_pres = float(np.mean((p_sim - GIO.astype(float)) ** 2))
        per_osservazione[nome] = {
            "crps": np.asarray(crps, dtype=float),
            # il Brier per coppia, appiattito nello stesso ordine per tutti
            "brier": ((p_sim - GIO.astype(float)) ** 2).ravel(),
        }
        corr = {k: float(np.nanmean([correlazioni(fv, G["voto"], gi, giocatori,
                                                  ruolo, squadra, s)[k]
                                     for s in range(min(3, a.sims))]))
                for k in ("portiere-difensori", "difensori", "centrocampisti",
                          "attaccanti")}
        punt = np.array([punteggi_rose(rose_prova, fv, G["voto"], gi,
                                       giocatori, s,
                                       gol_subiti=G.get("gol_subiti"),
                                       ruolo=ruolo)
                         for s in range(min(10, a.sims))])
        gol_sim = np.vectorize(goals_from_points)(punt).mean()
        gol_veri = np.vectorize(goals_from_points)(veri_rose).mean()
        riga.append({
            "generatore": nome,
            "punti_medi": round(float(vals.mean()), 4),
            "punti_sd": round(float(vals.std()), 4),
            "presenze_per_giornata": round(float(gi.sum() / (a.sims * GIORNATE)), 1),
            "crps": round(float(np.nanmean(crps)), 4),
            "pit_scarto_uniforme": round(float(np.mean(np.abs(
                np.sort(pit) - (np.arange(len(pit)) + 0.5) / len(pit)))), 4),
            "brier_presenze": round(brier_pres, 4),
            "rosa_punti_giornata": round(float(punt.mean()), 3),
            "rosa_punti_sd": round(float(punt.std()), 3),
            "rosa_gol_giornata": round(float(gol_sim), 4),
            **{f"corr_{k}": round(v, 4) for k, v in corr.items()},
        })

    veri = {
        "generatore": "VERO (stagione giocata)",
        "punti_medi": round(float(np.nanmean(VER[GIO])), 4),
        "punti_sd": round(float(np.nanstd(VER[GIO])), 4),
        "presenze_per_giornata": round(float(GIO.sum() / GIORNATE), 1),
        "crps": float("nan"), "pit_scarto_uniforme": float("nan"),
        "brier_presenze": float("nan"),
        "rosa_punti_giornata": round(float(veri_rose.mean()), 3),
        "rosa_punti_sd": round(float(veri_rose.std()), 3),
        "rosa_gol_giornata": round(float(np.vectorize(goals_from_points)(veri_rose).mean()), 4),
        **{f"corr_{k}": round(v, 4) for k, v in
           correlazioni(VER[None, ...], VER_V[None, ...], GIO[None, ...],
                        giocatori, ruolo, squadra, 0).items()},
    }
    df = pd.DataFrame([veri] + riga)
    df.to_csv(OUT / f"banco_confronto_{a.stagione}.csv", index=False)
    print()
    print(df.to_string(index=False))
    print(f"\nscritto banco_confronto_{a.stagione}.csv")
    print("\nlettura: CRPS e Brier piu' bassi sono meglio; per punti, presenze "
          "e correlazioni conta la vicinanza alla riga VERO.")

    # --- verdetto appaiato (criteri 3.7) ---------------------------------
    ver = verdetto_appaiato(per_osservazione, a.seme)
    if ver is not None:
        ver.to_csv(OUT / f"banco_verdetto_{a.stagione}.csv", index=False)
        print()
        print(ver.to_string(index=False))
        print(f"\nscritto banco_verdetto_{a.stagione}.csv")
    return 0


if __name__ == "__main__":
    sys.exit(main())
