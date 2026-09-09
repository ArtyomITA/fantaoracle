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
import datetime
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
from fantabot.tabellino import contratto                     # noqa: E402
from fantabot.tabellino import presenze                      # noqa: E402
from fantabot.tabellino import inferenza                     # noqa: E402
from fantabot.tabellino import esecuzione as esec            # noqa: E402
from fantabot.tabellino.partita import pesi_decadimento, stima as stima_partita  # noqa: E402

GIORNATE = 38
# le stagioni del panel: elencate, non raccolte con un glob, cosi' l'insieme
# consumato e' dichiarato e non dipende da quali file esistono sul disco
STAGIONI_PANEL = ["2021-22", "2023-24", "2024-25", "2025-26", "2026-27"]


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

def crps_e_dispersione(campioni: np.ndarray, y: float) -> tuple:
    """CRPS campionario e dispersione di ensemble, insieme.

    Il CRPS empirico e' `E|X-y| - 0.5 E|X-X'|`; il secondo termine e' la
    **dispersione**, e serve due volte: per la correzione equa di Ferro
    (`CRPS_equo = CRPS_emp - dispersione / (m - 1)`) e come colonna
    diagnostica per braccio. Senza quella colonna nessuno puo' controllare se
    la correzione cambia il segno di un confronto: con `m = 30` basta un
    divario di dispersione di `|differenza| * 29` per ribaltarlo.
    """
    x = np.asarray(campioni, dtype=float)
    if len(x) < 2:
        return float("nan"), float("nan")
    a = np.mean(np.abs(x - y))
    xs = np.sort(x)
    n = len(xs)
    # E|X-X'| calcolabile in O(n log n) dagli ordinamenti
    b = 2.0 * np.sum((2 * np.arange(1, n + 1) - n - 1) * xs) / (n * n)
    return float(a - 0.5 * b), float(0.5 * b)


def crps_campionario(campioni: np.ndarray, y: float) -> float:
    """CRPS stimato da campioni: E|X-y| - 0.5 E|X-X'|."""
    return crps_e_dispersione(campioni, y)[0]


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


def verdetto_appaiato(per_osservazione: dict, seme: int, *,
                      identita: dict, scenari: int,
                      per_seme: dict | None = None):
    """Confronti del disegno fattoriale (`reports/PROTOCOLLO_v2.md` §3.1).

    Quattro confronti appaiati, non due. Due tengono fissa l'informazione e
    cambiano il meccanismo; due tengono fisso il meccanismo e cambiano
    l'informazione. La differenza fra le due coppie e' l'interazione, cioe' se
    il cubo tragga dalle presenze del modello piu' o meno di quanto ne tragga
    il simulatore per giocatore: e' la quantita' che il confronto precedente
    non poteva vedere, perche' il braccio `C1` non esisteva.

    Piu' basso e' meglio sia per CRPS sia per Brier, quindi una differenza
    negativa e' a favore del primo termine.

    ## Che cosa e' cambiato rispetto al verdetto precedente

    **L'intervallo.** Prima si ricampionavano le righe (giocatore, giornata)
    come indipendenti. Non lo sono: le righe della stessa partita condividono
    il risultato, quelle dello stesso giocatore condividono la storia, e le due
    dimensioni si incrociano. Misurato in simulazione sulla geometria del
    banco, quell'intervallo nominale al 95 % copriva il vero valore il 50,7 %
    delle volte. Ora la varianza e' two-way cluster-robust su (partita,
    giocatore); l'errore standard sulle righe resta in tabella come diagnosi,
    perche' il suo rapporto con il two-way dice quanto la dipendenza conti.

    **Il punteggio.** Ogni confronto e' riportato due volte: sul punteggio
    **empirico**, che valuta l'ensemble a `scenari` membri cosi' com'e', e sul
    punteggio **equo** di Ferro, che stima il punteggio del generatore da cui i
    membri sono estratti. Sono due bersagli diversi e la scelta fra loro e'
    sostanziale, quindi non viene fatta qui: si riportano entrambi.

    **Il rumore Monte Carlo.** Con piu' semi di scenario, `per_seme` porta le
    medie per seme e l'esito distingue «non misurabile con le risorse
    disponibili» da «differenza non rilevabile». Con un solo seme il rumore non
    e' misurabile e la colonna lo dichiara.

    Parametri
    ---------
    identita
        `{"crps": (id_partita, id_giocatore), "brier": (...)}`: i due
        identificativi di grappolo per ogni riga di ciascuna misura.
    scenari
        `m`, il numero di scenari: serve alla correzione equa.
    per_seme
        `{(nome_braccio, chiave): [media per seme, ...]}` per il rumore Monte
        Carlo. `None` quando si e' eseguito un solo seme.

    LIMITE, dichiarato: l'intervallo tratta partite e giocatori come estrazioni
    casuali con un unico adattamento del modello tenuto **fisso**. Non copre
    l'incertezza dell'adattamento, non copre la variazione fra stagioni (con
    due stagioni i grappoli sono due e non esiste inferenza), non corregge per
    il riuso della validazione, e contenere lo zero **non** e' equivalenza.
    """
    nomi = list(per_osservazione)

    def presente(prefisso):
        return next((n for n in nomi if n.startswith(prefisso)), None)

    i0, i1 = presente("I0"), presente("I1")
    c0, c1 = presente("C0"), presente("C1")
    coppie = []
    if c0 and i0:
        coppie.append((c0, i0, "meccanismo, a informazione storica"))
    if c1 and i1:
        coppie.append((c1, i1, "meccanismo, con le presenze del modello"))
    if i1 and i0:
        coppie.append((i1, i0, "informazione, meccanismo per giocatore"))
    if c1 and c0:
        coppie.append((c1, c0, "informazione, meccanismo cubo"))
    if not coppie:
        return None

    def valuta(d, mc_serie, misura, punteggio, etichette, tipo, confronto):
        """Un contrasto qualsiasi: differenza appaiata, intervallo, esito.

        Serve sia ai quattro confronti sia all'interazione, che e' anch'essa
        una differenza appaiata riga per riga — solo con quattro termini invece
        di due. Passandoci per la stessa funzione, l'interazione riceve lo
        stesso trattamento e non un'approssimazione a parte.
        """
        id_part, id_gioc = identita[misura]
        buoni = np.isfinite(d)
        iv = inferenza.intervallo_two_way(d[buoni], id_part[buoni],
                                          id_gioc[buoni])
        # `es_campionario` attiva l'emendamento prospettico: senza, i campi
        # `soddisfatto_prospettico` e `quota_varianza_aggiunta` non venivano
        # calcolati da nessuno e il rapporto finiva nei rapporti a mano.
        mc = (inferenza.rumore_monte_carlo(
                  mc_serie, es_campionario=iv.errore_standard)
              if mc_serie is not None else None)
        # una sola stesura della regola delle etichette, quella provata dai
        # test del modulo: prima ce n'erano due, e una correzione fatta di la'
        # non sarebbe arrivata al csv
        esito = inferenza.esito_confronto(iv, mc, etichette)
        es = iv.diagnostica["errori_standard"]
        return {
            "confronto": confronto,
            "fattore": tipo,
            "misura": misura,
            "punteggio": punteggio,
            "differenza": round(iv.differenza, 6),
            "ic_basso": round(iv.ic_basso, 6),
            "ic_alto": round(iv.ic_alto, 6),
            "es_two_way": round(iv.errore_standard, 6),
            "es_righe_indipendenti": round(es["righe_indipendenti"], 6),
            "es_partita": round(es["one_way_1"], 6),
            "es_giocatore": round(es["one_way_2"], 6),
            "rapporto_su_righe": round(
                iv.diagnostica["rapporto_two_way_su_righe"], 3),
            "rho_partita": round(
                inferenza.rho_intra(d[buoni], id_part[buoni]), 5),
            "rho_giocatore": round(
                inferenza.rho_intra(d[buoni], id_gioc[buoni]), 5),
            "n": iv.n,
            "partite": iv.grappoli_1,
            "giocatori": iv.grappoli_2,
            "ammissibile": iv.ammissibile,
            "scenari": scenari,
            "semi": (mc["repliche"] if mc else 1),
            "sd_fra_semi": (round(mc["sd_fra_semi"], 6)
                            if mc else float("nan")),
            "es_monte_carlo": (round(mc["es_mc"], 6) if mc else float("nan")),
            "rumore_sotto_soglia": (mc["soddisfatto"] if mc else False),
            "rumore_sotto_soglia_prospettica": (
                mc.get("soddisfatto_prospettico") if mc else None),
            "quota_varianza_monte_carlo": (
                round(mc["quota_varianza_aggiunta"], 5)
                if mc and "quota_varianza_aggiunta" in mc else float("nan")),
            "semi_necessari": (mc.get("repliche_necessarie") if mc else None),
            "esito": esito}

    def serie_semi(*termini):
        """Le medie per seme di una combinazione lineare di bracci.

        La media e' lineare, quindi la media per seme di `A - B - C + D` si
        ottiene dalle medie per seme dei quattro bracci. Non serve conservare
        le osservazioni di ogni seme per misurare il rumore Monte Carlo di un
        contrasto.
        """
        if not per_seme:
            return None
        serie = []
        for nome, segno in termini:
            v = per_seme.get(nome)
            if not v:
                return None
            serie.append((np.asarray(v, dtype=float), segno))
        lunghezze = {len(v) for v, _ in serie}
        if len(lunghezze) != 1:
            return None
        tot = np.zeros(lunghezze.pop())
        for v, segno in serie:
            tot = tot + segno * v
        return list(tot)

    fuori = []
    for c, altro, tipo in coppie:
        for misura in ("crps", "brier"):
            for punteggio, chiave in (("empirico", misura),
                                      ("equo", f"{misura}_equo")):
                if chiave not in per_osservazione[c]:
                    continue
                d = (np.asarray(per_osservazione[c][chiave], dtype=float)
                     - np.asarray(per_osservazione[altro][chiave], dtype=float))
                primo = c.split(" ")[0]
                fuori.append(valuta(
                    d, serie_semi(((c, chiave), 1.0), ((altro, chiave), -1.0)),
                    misura, punteggio,
                    {"negativa": f"{primo} migliore",
                     "positiva": f"{primo} peggiore"},
                    tipo, f"{c} contro {altro}"))

    # ---------------------------------------------------------------- interazione
    # Il disegno fattoriale ha quattro celle, quindi ha anche un'interazione, e
    # senza di essa i quattro confronti non si leggono: dicono che l'effetto
    # dell'informazione e' grande su un meccanismo e piu' piccolo sull'altro,
    # ma non dicono se quella differenza sia distinguibile dal rumore.
    #
    #     interazione = (C1 - I1) - (C0 - I0) = (C1 - C0) - (I1 - I0)
    #
    # Le due scritture sono la stessa quantita' e la funzione le verifica una
    # contro l'altra. Positiva significa che il cubo **trae meno** dalle
    # presenze del modello di quanto ne tragga il simulatore per giocatore.
    if i0 and i1 and c0 and c1:
        for misura in ("crps", "brier"):
            for punteggio, chiave in (("empirico", misura),
                                      ("equo", f"{misura}_equo")):
                if any(chiave not in per_osservazione[n]
                       for n in (i0, i1, c0, c1)):
                    continue
                q = {n: np.asarray(per_osservazione[n][chiave], dtype=float)
                     for n in (i0, i1, c0, c1)}
                # Le due scritture `(C1-I1)-(C0-I0)` e `(C1-C0)-(I1-I0)` sono
                # la stessa somma riassociata: coincidono sempre, qualunque
                # cosa contengano gli array. Confrontarle NON verifica
                # l'appaiamento — sarebbe un presidio finto, e per un po' ce
                # l'ho messo.
                #
                # Quello che l'appaiamento lo garantisce davvero e' a monte:
                # le coppie valutate sono estratte una volta sola, fuori dal
                # ciclo sui semi, e riusate da tutti i bracci. Qui si controlla
                # l'unica cosa controllabile a valle, cioe' che i quattro
                # bracci abbiano lo stesso numero di righe.
                lunghezze = {n: q[n].size for n in (i0, i1, c0, c1)}
                if len(set(lunghezze.values())) != 1:
                    raise RuntimeError(
                        f"i quattro bracci hanno lunghezze diverse "
                        f"({lunghezze}): non sono valutati sulle stesse righe")
                d = (q[c1] - q[i1]) - (q[c0] - q[i0])
                fuori.append(valuta(
                    d,
                    serie_semi(((c1, chiave), 1.0), ((i1, chiave), -1.0),
                               ((c0, chiave), -1.0), ((i0, chiave), 1.0)),
                    misura, punteggio,
                    {"nulla": "interazione non rilevabile",
                     "negativa": "il cubo trae piu' dalle presenze",
                     "positiva": "il cubo trae meno dalle presenze"},
                    "interazione",
                    f"({c1} - {i1}) - ({c0} - {i0})"))
    return pd.DataFrame(fuori)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("stagione", nargs="?", default="2024-25")
    ap.add_argument("--sims", type=int, default=30)
    ap.add_argument("--seme", type=int, default=20260907)
    ap.add_argument("--rose-da", choices=["listone", "squadra"],
                    default="listone",
                    help="fonte della squadra per l'universo: deve essere la "
                         "stessa che usa il generatore, altrimenti i bracci "
                         "non sono a parita' di rose")
    ap.add_argument("--data-fit", default=None,
                    help="cutoff del fit: i panel devono essere stati costruiti "
                         "con questo cutoff, altrimenti vengono rifiutati")
    ap.add_argument("--semi", type=int, default=1,
                    help="semi di scenario indipendenti. Il rumore Monte "
                         "Carlo non e' ricampionabile e si misura solo "
                         "ripetendo: con un solo seme resta non misurato. "
                         "R semi a --sims scenari costano quanto una sola "
                         "esecuzione con R*sims scenari.")
    ap.add_argument("--rose", type=int, default=10)
    ap.add_argument("--prova", action="store_true",
                    help="prova esplorativa: scrive sotto data/l2/prove/, "
                         "radice separata da quella dei risultati "
                         "pubblicabili. Una prova non puo' finire dove sta un "
                         "risultato nemmeno per sbaglio.")
    ap.add_argument("--destinazione", default=None,
                    help="cartella di destinazione esplicita. Per difetto una "
                         "cartella nuova per ogni esecuzione.")
    ap.add_argument("--riprendi", action="store_true",
                    help="ammette una destinazione gia' esistente, ma solo se "
                         "la configurazione registrata coincide")
    ap.add_argument("--istante", default=None,
                    help="marca temporale della cartella; per difetto adesso")
    a = ap.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)

    # Ogni esecuzione ha la sua cartella. Prima si scriveva su nomi fissi, e
    # una prova a quattro scenari poteva sovrascrivere un verdetto pubblicato:
    # e' successo davvero. Una destinazione occupata adesso viene rifiutata.
    istante = a.istante or datetime.datetime.now().strftime("%Y%m%dT%H%M%S")
    configurazione = {
        "script": "l2_banco_confronto",
        "stagione": a.stagione, "sims": a.sims, "seme": a.seme,
        "semi": a.semi, "rose": a.rose, "rose_da": a.rose_da,
        "data_fit": a.data_fit,
        "impronte_ingressi": {
            n: esec.impronta_file(PROC / n)
            for n in (f"players_{a.stagione}.parquet", "l2_partite.parquet",
                      f"b_predictions_{a.stagione}.json")},
        "impronta_script": esec.impronta_file(__file__),
    }
    corsa = esec.apri(OUT, a.stagione, configurazione, istante=istante,
                      prova=a.prova, riprendi=a.riprendi,
                      destinazione=a.destinazione)
    print(f"  destinazione: {corsa.cartella} "
          f"(id {corsa.identificativo}{', ripresa' if corsa.ripresa else ''})")

    # Il glob raccoglieva ogni variante del panel: con i file indicizzati per
    # cutoff avrebbe caricato lo stesso panel piu' volte, duplicando le righe.
    # Qui le stagioni si chiedono per nome e il contratto viene verificato.
    P, contratti_panel = contratto.carica_panel_multi(
        PROC, STAGIONI_PANEL, data_fit=a.data_fit,
        esigi_vista_al_fit=a.data_fit is not None)
    print(f"  panel: {len(contratti_panel)} stagioni, vista "
          + (f"al fit del {a.data_fit}" if a.data_fit else "osservativa"))
    P["data"] = pd.to_datetime(P["data"])
    part = pd.read_parquet(PROC / "l2_partite.parquet")
    part["data"] = pd.to_datetime(part["data"])
    cal = part[part.stagione == a.stagione].copy()
    as_of = str(cal.data.min().date())
    # L'universo si costruisce con la stessa funzione che usa il generatore:
    # prima erano due costruzioni separate, e il banco usava `squadra` mentre
    # il cubo era passato a `squadra_listone`. I due lavoravano su rose diverse,
    # quindi il confronto fra i loro generatori non era a parita' di universo.
    rose_liste, ruolo, squadra, diag_universo = contratto.costruisci_universo(
        PROC, a.stagione, rose_da=a.rose_da)
    giocatori = sorted(ruolo)
    print(f"  universo da `{diag_universo['colonna']}`: "
          f"{diag_universo['giocatori']} giocatori, "
          f"{diag_universo['squadre']} squadre, "
          f"{diag_universo['squadra_diversa_dal_listone']} con squadra diversa "
          "dal listone")
    print(f"stagione {a.stagione} | as_of {as_of} | {a.sims} scenari | "
          f"{len(giocatori)} giocatori")

    Ppre = P[P.data < pd.Timestamp(as_of)]
    storia, per_ruolo = storia_giocatori(P, as_of)

    # Nomi del disegno fattoriale (`reports/PROTOCOLLO_v2.md` §3.1): le due
    # dimensioni sono il MECCANISMO (simulatore per giocatore contro cubo
    # TABELLINO) e l'INFORMAZIONE sulle presenze (storia contro modello
    # valore). Le lettere sole avevano finito per indicare sistemi diversi in
    # report diversi.
    #
    #            informazione storica     presenze del modello
    #   per gioc.       I0                        I1
    #   cubo            C0                        C1
    #
    # `A` resta come baseline semplice fuori dal disegno: non ha ne' memoria
    # ne' shock di squadra, e serve a vedere quanto valgono quei due pezzi.
    #
    # La generazione e' stata spostata dentro `costruisci_generatori`, piu'
    # sotto: con piu' semi di scenario va rifatta per ogni seme, mentre
    # l'adattamento dei modelli resta uno solo e va fatto una volta.

    # L'adattatore copre l'UNIVERSO COMPLETO, non i soli giocatori con storia.
    # Prima l'aggiornamento scorreva `storia_pres`, che contiene solo chi ha
    # voti precedenti: 264 giocatori ignorati nel 2024-25 e 219 nel 2025-26,
    # con somma delle probabilita' previste 70,33 e 56,10 sostituita da un
    # ripiego di 0,5 ciascuno. E il filtro `if q.get("pres")` scartava le
    # previsioni di zero, che sono 38 e 29.
    bers = presenze.costruisci(
        PROC / f"b_predictions_{a.stagione}.json", giocatori, ruolo,
        storia_voti=Ppre[["master_id", "stato_voto"]])
    bersaglio_presenza = bers.per_giocatore
    dbp = bers.diagnostica
    print(f"  presenze dal modello: {dbp['con_bersaglio']}/{dbp['universo']} "
          f"({dbp['per_fonte'][presenze.FONTE_PREVISIONE]} da previsione, "
          f"{dbp['per_fonte'][presenze.FONTE_PRIOR_RUOLO]} da prior, "
          f"{dbp['per_fonte'][presenze.FONTE_ASSENTE]} senza), "
          f"{dbp['previsioni_zero_tenute']} zeri tenuti")
    storia_pres = None
    if bersaglio_presenza:
        # il braccio I1 riceve la probabilita' per TUTTI, non solo per chi ha
        # storia: la probabilita' e' separata dal campione storico dei voti
        storia_pres = {k: dict(v) for k, v in storia.items()}
        for pid, p_voto in bersaglio_presenza.items():
            if pid in storia_pres:
                storia_pres[pid]["p"] = p_voto
            else:
                # senza campione di voti si usa quello del ruolo, ma la
                # probabilita' resta quella prevista: sono due cose separate
                r = ruolo.get(pid, "C")
                fv, v, gs = per_ruolo.get(r, per_ruolo.get("C"))
                storia_pres[pid] = {"fv": fv, "v": v, "gs": gs,
                                    "p": p_voto, "ruolo": r}
        print(f"  presenze dal modello per {len(bersaglio_presenza)} giocatori")

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
    m_part_bers = (pa.stima(Ppre, bersaglio_presenza=bersaglio_presenza,
                            ruolo_esterno=ruolo)
                   if bersaglio_presenza else None)
    if m_part_bers is not None:
        d = m_part_bers.diagnostica.get("bersaglio_presenza") or {}
        print(f"  bersaglio delle presenze al cubo: {d.get('applicati')} "
              f"giocatori applicati, {d.get('saltati_non_nel_panel')} saltati")
        m_part_bers.ruolo.update(ruolo)
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
    def costruisci_generatori(seme_scen: int) -> dict:
        """I cinque bracci a un dato seme di scenario.

        L'adattamento dei modelli sta **fuori** da questa funzione e non cambia
        fra i semi: quello che varia e' solo l'estrazione degli scenari. E'
        quello che serve per misurare il rumore Monte Carlo tenendo fisso tutto
        il resto — e anche il limite di quella misura, perche' l'incertezza
        dell'adattamento resta fuori dall'intervallo.
        """
        t = time.time()
        g = {}
        g["A baseline semplice"] = genera_per_giocatore(
            storia, per_ruolo, giocatori, ruolo, squadra, a.sims, seme_scen,
            memoria=False, shock=0.0, sigma_stima=0.0)
        g["I0 per giocatore, storia"] = genera_per_giocatore(
            storia, per_ruolo, giocatori, ruolo, squadra, a.sims, seme_scen,
            memoria=True, shock=TEAM_SHOCK_SD, sigma_stima=0.45)
        if storia_pres is not None:
            g["I1 per giocatore, presenze del modello"] = genera_per_giocatore(
                storia_pres, per_ruolo, giocatori, ruolo, squadra, a.sims,
                seme_scen, memoria=True, shock=TEAM_SHOCK_SD, sigma_stima=0.45)

        def genera_cubo(modello_part, etichetta):
            """Un braccio del disegno: stesso tutto, tranne il modello di
            partecipazione. Cosi' la differenza fra C0 e C1 e' l'informazione
            sulle presenze e nient'altro."""
            c = gen.genera(cal, rose_liste, mp, modello_part, m_ev, m_voto,
                           n_sims=a.sims, seme=seme_scen, dipendenza=struttura,
                           fasce_sv=fasce_sv, verifica=True)
            ixc = {pid: i for i, pid in enumerate(c.giocatori)}
            ordine = [ixc.get(pid) for pid in giocatori]

            def riordina(A):
                B = np.zeros((a.sims, GIORNATE, len(giocatori)), dtype=A.dtype)
                for j, k in enumerate(ordine):
                    if k is not None:
                        B[:, :len(c.giornate), j] = A[:, :, k]
                return B

            g[etichetta] = {
                "fantavoto": riordina(c.fantavoto), "voto": riordina(c.voto),
                "gioca": riordina(c.gioca),
                "gol_subiti": (riordina(c.gol_subiti)
                               if getattr(c, "gol_subiti", None) is not None
                               else None),
                "giocatori": giocatori}
            return c.diagnostica["n_problemi_coerenza"]

        problemi = genera_cubo(m_part, "C0 cubo, storia")
        if m_part_bers is not None:
            problemi += genera_cubo(m_part_bers,
                                    "C1 cubo, presenze del modello")
        print(f"  seme {seme_scen}: {len(g)} bracci in {time.time() - t:.1f} s "
              f"({problemi} problemi di coerenza)")
        return g

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

    # Le rose di prova pescano dall'universo condiviso, non da una lettura
    # separata del listone. La lettura separata era stata sostituita dalla
    # costruzione condivisa (R1) e questo uso era rimasto scoperto: `lst` non
    # esisteva piu' e il banco cadeva con NameError prima di produrre qualsiasi
    # numero. Vedi `reports/PROTOCOLLO_v2.md` §17.
    lst = pd.DataFrame({"master_id": giocatori,
                        "ruolo": [ruolo[pid] for pid in giocatori]})
    rose_prova = rose_di_prova(lst, a.rose, a.seme)
    veri_rose = punteggi_rose(rose_prova, VER[None, ...], VER_V[None, ...],
                              GIO[None, ...], giocatori, 0,
                              gol_subiti=VER_GS[None, ...], ruolo=ruolo)

    # --- identita' dei grappoli -------------------------------------------
    # Ogni riga (giocatore, giornata) appartiene a una partita e a un
    # giocatore, e le due dimensioni si incrociano: sono i grappoli su cui si
    # costruisce la varianza two-way. Senza questa mappa l'intervallo tratta le
    # righe come indipendenti, che e' il difetto misurato.
    mappa_part = {}
    for r in P[P.stagione == a.stagione].itertuples(index=False):
        j_ = ix.get(r.master_id)
        g_ = int(r.giornata) - 1
        idp = getattr(r, "id_partita", None)
        if j_ is not None and 0 <= g_ < GIORNATE and idp is not None \
                and not pd.isna(idp):
            mappa_part[(g_, j_)] = str(idp)
    PART = np.empty((GIORNATE, len(giocatori)), dtype=object)
    senza_partita = 0
    for g_ in range(GIORNATE):
        for j_ in range(len(giocatori)):
            v = mappa_part.get((g_, j_))
            if v is None:
                # niente partita per quella coppia: grappolo a se', cioe'
                # nessuna dipendenza assunta. Contato, non nascosto.
                v = f"_sola_{g_}_{j_}"
                senza_partita += 1
            PART[g_, j_] = v
    print(f"  grappoli: {len(set(PART.ravel()))} partite distinte "
          f"({senza_partita} coppie senza partita, trattate come grappolo a "
          f"se'), {len(giocatori)} giocatori")

    rng = np.random.default_rng(a.seme)
    # tutte le coppie (giocatore, giornata) dell'universo, non solo quelle in
    # cui il giocatore ha davvero giocato: selezionare sull'esito vero
    # premierebbe il generatore che fa giocare tutti. Chi non gioca vale 0,
    # che e' quello che vale nel fantacalcio.
    #
    # Le coppie si estraggono UNA VOLTA e restano le stesse per tutti i bracci
    # e per tutti i semi: e' quello che rende lecito il confronto riga per riga
    # e la media sui semi.
    coppie = np.array([(g, j) for g in range(GIORNATE)
                       for j in range(len(giocatori))])
    scelte = coppie[rng.choice(len(coppie), size=min(6000, len(coppie)),
                               replace=False)]
    u_pit = rng.random(len(scelte))

    id_part_crps = np.array([PART[g, j] for g, j in scelte], dtype=object)
    id_gioc_crps = np.array([giocatori[j] for _, j in scelte])
    id_part_brier = PART.ravel()
    id_gioc_brier = np.tile(np.asarray(giocatori), GIORNATE)
    identita = {"crps": (id_part_crps, id_gioc_crps),
                "brier": (id_part_brier, id_gioc_brier)}

    # --- semi di scenario --------------------------------------------------
    # Il rumore Monte Carlo non e' ricampionabile: lo scenario non e' una
    # partizione delle righe, perche' il punteggio di ogni riga e' funzione di
    # tutti gli scenari. L'unica via e' ripetere con semi diversi e misurare.
    semi = [a.seme + 100_003 * r for r in range(max(1, a.semi))]
    print(f"  {len(semi)} semi di scenario a {a.sims} scenari ciascuno "
          f"(equivalente a {len(semi) * a.sims} scenari, con in piu' la misura "
          "del rumore Monte Carlo)")

    def misure(gen_dict: dict) -> dict:
        """Punteggi per osservazione, empirici ed equi, per ogni braccio."""
        fuori = {}
        for nome, G in gen_dict.items():
            fv, gi = G["fantavoto"], G["gioca"]
            crps, disp, pit = [], [], []
            for t, (g, j) in enumerate(scelte):
                camp = np.where(gi[:, g, j], fv[:, g, j], 0.0)
                y = VER[g, j] if GIO[g, j] else 0.0
                c_emp, d_emp = crps_e_dispersione(camp, y)
                crps.append(c_emp)
                disp.append(d_emp)
                pit.append(pit_randomizzato(camp, y, u_pit[t]))
            crps = np.asarray(crps, dtype=float)
            disp = np.asarray(disp, dtype=float)
            p_sim = gi.mean(0)
            brier = ((p_sim - GIO.astype(float)) ** 2).ravel()
            fuori[nome] = {
                "crps": crps,
                # punteggio equo di Ferro: stima il punteggio del generatore
                # invece di quello dell'ensemble a `sims` membri. La correzione
                # NON si cancella nelle differenze, perche' dipende dalla
                # dispersione, che cambia fra bracci.
                "crps_equo": inferenza.crps_equo(crps, disp, a.sims),
                "crps_dispersione": disp,
                "brier": brier,
                "brier_equo": inferenza.brier_equo(
                    p_sim.ravel(), GIO.astype(float).ravel(), a.sims),
                "brier_dispersione": (p_sim * (1.0 - p_sim)).ravel(),
                "pit": np.asarray(pit, dtype=float),
            }
        return fuori

    CHIAVI = ("crps", "crps_equo", "brier", "brier_equo",
              "crps_dispersione", "brier_dispersione")
    somma, per_seme = {}, {}
    primo_seme, gen_primo = None, None
    for r, seme_r in enumerate(semi):
        generatori = costruisci_generatori(seme_r)
        mis = misure(generatori)
        if r == 0:
            primo_seme, gen_primo = mis, generatori
        for nome, d in mis.items():
            for k in CHIAVI:
                somma.setdefault((nome, k), np.zeros_like(d[k]))
                somma[(nome, k)] += d[k]
                per_seme.setdefault((nome, k), []).append(
                    float(np.nanmean(d[k])))

    per_osservazione = {}
    for (nome, k), tot in somma.items():
        per_osservazione.setdefault(nome, {})[k] = tot / len(semi)

    # --- tabella descrittiva ----------------------------------------------
    riga = []
    for nome, G in gen_primo.items():
        fv, gi = G["fantavoto"], G["gioca"]
        vals = fv[gi]
        m0 = primo_seme[nome]
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
        riga.append({
            "generatore": nome,
            "punti_medi": round(float(vals.mean()), 4),
            "punti_sd": round(float(vals.std()), 4),
            "presenze_per_giornata": round(
                float(gi.sum() / (a.sims * GIORNATE)), 1),
            "crps": round(float(np.nanmean(per_osservazione[nome]["crps"])), 4),
            "crps_equo": round(float(np.nanmean(
                per_osservazione[nome]["crps_equo"])), 4),
            # la dispersione media di ensemble e' la colonna che permette di
            # controllare se la correzione equa puo' ribaltare un confronto:
            # con `sims` scenari serve un divario di |differenza| * (sims - 1)
            "dispersione_crps": round(float(np.nanmean(
                per_osservazione[nome]["crps_dispersione"])), 4),
            "pit_scarto_uniforme": round(float(np.mean(np.abs(
                np.sort(m0["pit"]) - (np.arange(len(m0["pit"])) + 0.5)
                / len(m0["pit"])))), 4),
            "brier_presenze": round(float(np.nanmean(
                per_osservazione[nome]["brier"])), 4),
            "brier_equo": round(float(np.nanmean(
                per_osservazione[nome]["brier_equo"])), 4),
            "dispersione_brier": round(float(np.nanmean(
                per_osservazione[nome]["brier_dispersione"])), 4),
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
        "crps": float("nan"), "crps_equo": float("nan"),
        "dispersione_crps": float("nan"),
        "pit_scarto_uniforme": float("nan"),
        "brier_presenze": float("nan"), "brier_equo": float("nan"),
        "dispersione_brier": float("nan"),
        "rosa_punti_giornata": round(float(veri_rose.mean()), 3),
        "rosa_punti_sd": round(float(veri_rose.std()), 3),
        "rosa_gol_giornata": round(
            float(np.vectorize(goals_from_points)(veri_rose).mean()), 4),
        **{f"corr_{k}": round(v, 4) for k, v in
           correlazioni(VER[None, ...], VER_V[None, ...], GIO[None, ...],
                        giocatori, ruolo, squadra, 0).items()},
    }
    df = pd.DataFrame([veri] + riga)
    corsa.scrivi_tabella(f"banco_confronto_{a.stagione}.csv", df)
    print()
    print(df.to_string(index=False))
    print(f"\nscritto banco_confronto_{a.stagione}.csv")
    print("\nlettura: CRPS e Brier piu' bassi sono meglio; per punti, presenze "
          "e correlazioni conta la vicinanza alla riga VERO. I punteggi sono "
          f"mediati su {len(semi)} semi; correlazioni, PIT e punti delle rose "
          "vengono dal primo seme.")

    # --- osservazioni conservate ------------------------------------------
    # Il criterio chiede di conservare i risultati per osservazione con
    # l'identita' di giocatore, partita e data. Senza, l'inferenza si puo'
    # rifare solo rigenerando tutto, e un contrasto che non era stato previsto
    # (l'interazione, per esempio) costa un'altra esecuzione intera.
    #
    # Si conservano i punteggi **mediati sui semi** piu' le medie per seme di
    # ogni braccio: la media e' lineare, quindi da quelle si ricava il rumore
    # Monte Carlo di qualunque combinazione lineare dei bracci senza tenere
    # tutte le osservazioni di tutti i semi.
    data_di = {}
    for r in P[P.stagione == a.stagione].itertuples(index=False):
        g_ = int(r.giornata) - 1
        if 0 <= g_ < GIORNATE and g_ not in data_di and r.data is not pd.NaT:
            data_di[g_] = pd.Timestamp(r.data).date().isoformat()
    blocchi = []
    for misura, righe in (("crps", [(int(g), int(j)) for g, j in scelte]),
                          ("brier", [(g, j) for g in range(GIORNATE)
                                     for j in range(len(giocatori))])):
        base = pd.DataFrame({
            "misura": misura,
            "giornata": [g + 1 for g, _ in righe],
            "data": [data_di.get(g) for g, _ in righe],
            "master_id": [giocatori[j] for _, j in righe],
            "id_partita": [PART[g, j] for g, j in righe],
            "ruolo": [ruolo.get(giocatori[j]) for _, j in righe],
            "squadra": [squadra.get(giocatori[j]) for _, j in righe],
            "esito_vero": [float(VER[g, j]) if GIO[g, j] else 0.0
                           for g, j in righe],
            "ha_giocato": [bool(GIO[g, j]) for g, j in righe],
        })
        for nome in per_osservazione:
            eti = nome.split(" ")[0]
            for suff, chiave in (("", misura), ("_equo", f"{misura}_equo"),
                                 ("_dispersione", f"{misura}_dispersione")):
                base[f"{eti}{suff}"] = per_osservazione[nome][chiave]
        blocchi.append(base)
    oss_df = pd.concat(blocchi, ignore_index=True)
    corsa.scrivi_tabella(f"banco_osservazioni_{a.stagione}.parquet", oss_df)
    corsa.scrivi_json(f"banco_semi_{a.stagione}.json", {
        "esecuzione": corsa.identificativo,
        "istante": corsa.istante,
        "semi": semi, "scenari": a.sims,
        "medie_per_seme": {f"{n}|{k}": v for (n, k), v in per_seme.items()},
        "nota": ("le medie per seme servono a misurare il rumore Monte Carlo "
                 "di qualunque combinazione lineare dei bracci: la media e' "
                 "lineare, quindi non serve conservare le osservazioni di "
                 "ogni seme.")})
    print(f"  conservate {len(oss_df)} osservazioni con identita' in "
          f"banco_osservazioni_{a.stagione}.parquet")

    # --- verdetto appaiato (criteri 3.7) ---------------------------------
    ver = verdetto_appaiato(per_osservazione, a.seme, identita=identita,
                            scenari=a.sims,
                            per_seme=per_seme if len(semi) > 1 else None)
    if ver is not None:
        # l'identificativo dell'esecuzione entra nel verdetto: e' quello che
        # permette al verificatore di dire se due artefatti vengono davvero
        # dalla stessa esecuzione, invece di limitarsi a «i numeri coincidono»
        ver["esecuzione"] = corsa.identificativo
        corsa.scrivi_tabella(f"banco_verdetto_{a.stagione}.csv", ver)
        print()
        colonne = ["fattore", "misura", "punteggio", "differenza", "ic_basso",
                   "ic_alto", "es_two_way", "es_righe_indipendenti",
                   "es_monte_carlo", "esito"]
        print(ver[colonne].to_string(index=False))
        print(f"\nscritto banco_verdetto_{a.stagione}.csv")
        print("nota: `es_righe_indipendenti` e' l'errore standard del metodo "
              "precedente, tenuto in tabella come diagnosi. Il suo rapporto "
              "con `es_two_way` dice quanto la dipendenza fra compagni e nel "
              "tempo conti; non e' un'alternativa fra cui scegliere.")
    corsa.registra()
    print(f"\nscritto in {corsa.cartella}")
    if a.prova:
        print("prova esplorativa: nessun aggiornamento del puntatore "
              "`corrente`. I risultati pubblicati non sono stati toccati.")
    else:
        print("per promuovere questa esecuzione a corrente serve una verifica "
              "passata:\n  PYTHONPATH=src python scripts/l2_promuovi.py "
              f"{a.stagione} --da {corsa.cartella}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
