"""Pilota `C2`: calibrazione regolarizzata del generatore verso bersagli compatibili.

`C2` è un candidato **sperimentale**, separato da `C1`, che resta com'è con i
suoi risultati pubblicati. Il pilota misura se una calibrazione congiunta possa
avvicinare le presenze marginali del cubo ai bersagli senza rompere quello che
il cubo serve a fare.

## Che cosa si ottimizza

Per le squadre scelte, uno **scostamento additivo sul logit di convocazione**,
uno per giocatore. `θ = 0` è il generatore attuale, quindi il punto di partenza
è `C1` e la regolarizzazione penalizza gli scostamenti inutili.

    L(θ) = (1/n) Σ_i w_i (P_voto_sim(i | θ) − b_compatibile[i])² + λ‖θ‖²/p

## Il bersaglio compatibile

Il bersaglio grezzo non è sempre realizzabile insieme: i portieri della
Fiorentina ne chiedono 1,53684 per giornata contro **1,000 osservati**. Non è
un limite del generatore, è il bersaglio a chiedere due portieri a voto nella
stessa giornata.

Dentro ogni (squadra, ruolo) si conservano le **proporzioni relative** del
bersaglio grezzo — l'informazione marginale che vogliamo tenere — e si fissa la
**somma** al numero medio di voti per squadra-giornata di quel ruolo, stimato
sulle **stagioni ammesse al fit**. Mai sulla stagione valutata.

## Il metodo

SPSA (Spall 1998), scelto perché il gradiente non esiste e ogni valutazione è
una simulazione rumorosa: stima il gradiente con **due misure per iterazione
indipendentemente dalla dimensione**, contro le 2p di una differenza finita.

Dalla fonte, e rispettato qui: perturbazione **Bernoulli ±1** — uniforme e
normale non sono ammesse dalle condizioni di regolarità, perché hanno momenti
inversi infiniti; guadagni `a_k = a/(A+k)^α`, `c_k = c/k^γ`.

**Non è una garanzia di ottimo.** La convergenza quasi certa vale sotto
condizioni che qui non ho verificato, e la minimizzazione globale richiede una
variante diversa. Questa è una ricerca locale con un budget fissato prima.

## Che cosa il pilota NON fa

Non promuove niente, non tocca `C1`, non calibra sugli esiti della stagione
valutata. Il confronto contro l'osservato è **diagnostico** e usa
l'appartenenza alla data della partita.
"""
from __future__ import annotations

import argparse
import datetime
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from fantabot.tabellino import configurazione as cfg          # noqa: E402
from fantabot.tabellino import contratto                      # noqa: E402
from fantabot.tabellino import esecuzione as esec             # noqa: E402
from fantabot.tabellino import eventi as ev                   # noqa: E402
from fantabot.tabellino import generatore as gen              # noqa: E402
from fantabot.tabellino import partecipazione as pa           # noqa: E402
from fantabot.tabellino import presenze                       # noqa: E402
from fantabot.tabellino import voto as vt                     # noqa: E402

PROC = ROOT / "data" / "processed"
OUT = ROOT / "data" / "l2"
GIORNATE = 38
STAGIONI_PANEL = ["2021-22", "2022-23", "2023-24", "2024-25", "2025-26"]

# piano fissato PRIMA, non aggiustabile dopo aver visto i risultati
MAX_ITERAZIONI = 30
PAZIENZA = 5              # iterazioni senza miglioramento oltre l'1 %
MIGLIORAMENTO_MINIMO = 0.01
ALPHA, GAMMA = 0.602, 0.101        # valori standard della letteratura SPSA


def bersaglio_compatibile(b_grezzo: dict, ruolo: dict, squadra: dict,
                          somme_ruolo: dict) -> tuple[dict, dict]:
    """Riscala il bersaglio dentro ogni (squadra, ruolo) a una somma realizzabile.

    Conserva le proporzioni relative: chi era chiesto di più resta chiesto di
    più. Cambia solo il totale di squadra-ruolo, che è il vincolo congiunto.
    """
    per_cella = {}
    for pid, v in b_grezzo.items():
        per_cella.setdefault((squadra.get(pid), ruolo.get(pid)), []).append(pid)
    fuori, diag = {}, {}
    for (sq, r), ids in per_cella.items():
        somma = sum(b_grezzo[p] for p in ids)
        bersaglio_somma = somme_ruolo.get(r)
        if not somma or bersaglio_somma is None:
            for p in ids:
                fuori[p] = b_grezzo[p]
            continue
        k = bersaglio_somma / somma
        for p in ids:
            fuori[p] = float(min(max(b_grezzo[p] * k, 0.0), 1.0))
        diag[f"{sq}|{r}"] = {"somma_grezza": round(somma, 4),
                             "somma_compatibile": round(bersaglio_somma, 4),
                             "fattore": round(k, 4), "giocatori": len(ids)}
    return fuori, diag


def somme_per_ruolo_dal_fit(P: pd.DataFrame, stagione_esclusa: str) -> dict:
    """Voti medi per squadra-giornata e ruolo, dalle sole stagioni ammesse."""
    d = P[(P.stagione != stagione_esclusa) & (P.stato_voto == "con_voto")]
    per = (d.groupby(["stagione", "squadra_alla_data", "giornata", "ruolo"])
             .size().rename("n").reset_index())
    return {r: float(g["n"].mean()) for r, g in per.groupby("ruolo")}


class Obiettivo:
    """La funzione da minimizzare: una simulazione per valutazione."""

    def __init__(self, cal, rose, mp, m_part, m_ev, m_voto, struttura,
                 fasce_sv, ids, bersaglio, sims, lam):
        self.cal, self.rose, self.mp = cal, rose, mp
        self.m_part, self.m_ev, self.m_voto = m_part, m_ev, m_voto
        self.struttura, self.fasce_sv = struttura, fasce_sv
        self.ids = list(ids)
        self.bersaglio = np.array([bersaglio[p] for p in self.ids], float)
        self.sims, self.lam = sims, lam
        # La base calibrata sta in `logit_base_convocato`, non si ricava da
        # `prop_convocato`: scrivere quest'ultima non cambiava niente, e la
        # prima prova dava C1 e C2 identici cifra per cifra.
        self.base = {p: float(m_part.base_convocazione(p)) for p in self.ids}
        self.valutazioni = 0
        self.secondi = 0.0

    def presenze_simulate(self, theta, seme) -> np.ndarray:
        t0 = time.time()
        vecchi = {}
        for k, pid in enumerate(self.ids):
            vecchi[pid] = self.m_part.logit_base_convocato.get(pid)
            self.m_part.logit_base_convocato[pid] = (
                self.base[pid] + float(theta[k]))
        try:
            c = gen.genera(self.cal, self.rose, self.mp, self.m_part,
                           self.m_ev, self.m_voto, n_sims=self.sims,
                           seme=seme, dipendenza=self.struttura,
                           fasce_sv=self.fasce_sv, verifica=False)
        finally:
            for pid, v in vecchi.items():
                if v is None:
                    self.m_part.logit_base_convocato.pop(pid, None)
                else:
                    self.m_part.logit_base_convocato[pid] = v
        ixc = {pid: i for i, pid in enumerate(c.giocatori)}
        n_g = len(c.giornate)
        fuori = np.array([
            float(c.gioca[:, :n_g, ixc[p]].mean()) if p in ixc else np.nan
            for p in self.ids])
        self.valutazioni += 1
        self.secondi += time.time() - t0
        return fuori

    def __call__(self, theta, seme) -> float:
        p = self.presenze_simulate(theta, seme)
        buoni = np.isfinite(p)
        scarto = float(np.mean((p[buoni] - self.bersaglio[buoni]) ** 2))
        pen = self.lam * float(np.mean(np.asarray(theta, float) ** 2))
        return scarto + pen


def spsa(obiettivo, p: int, semi_comuni, a=0.30, c=0.10, A=None,
         massimo=MAX_ITERAZIONI, rng=None) -> dict:
    """SPSA con guadagni standard e perturbazione Bernoulli ±1.

    `A` per difetto al 10 % delle iterazioni previste, come raccomanda la
    letteratura. `semi_comuni` è la lista dei semi usati **sempre gli stessi**
    durante l'ottimizzazione: numeri casuali comuni, così la differenza fra le
    due misure di una iterazione non è dominata dal rumore di simulazione.
    """
    rng = rng or np.random.default_rng(0)
    A = A if A is not None else max(1, massimo // 10)
    theta = np.zeros(p)
    storia = []
    migliore = None
    senza_miglioramento = 0
    for k in range(1, massimo + 1):
        ak = a / (A + k) ** ALPHA
        ck = c / k ** GAMMA
        # Bernoulli +-1: uniforme e normale NON sono ammesse dalle condizioni
        # di regolarita' di SPSA (momenti inversi infiniti)
        delta = rng.choice([-1.0, 1.0], size=p)
        seme = semi_comuni[(k - 1) % len(semi_comuni)]
        piu = obiettivo(theta + ck * delta, seme)
        meno = obiettivo(theta - ck * delta, seme)
        g = (piu - meno) / (2.0 * ck) / delta
        theta = theta - ak * g
        valore = 0.5 * (piu + meno)
        storia.append({"iterazione": k, "ak": ak, "ck": ck,
                       "L_piu": piu, "L_meno": meno, "L_medio": valore,
                       "norma_theta": float(np.linalg.norm(theta))})
        if migliore is None or valore < migliore * (1 - MIGLIORAMENTO_MINIMO):
            migliore = valore if migliore is None else min(migliore, valore)
            senza_miglioramento = 0
        else:
            senza_miglioramento += 1
            if senza_miglioramento >= PAZIENZA:
                storia[-1]["arresto"] = (
                    f"nessun miglioramento oltre l'{MIGLIORAMENTO_MINIMO:.0%} "
                    f"per {PAZIENZA} iterazioni")
                break
    return {"theta": theta, "storia": storia,
            "iterazioni": len(storia), "migliore": migliore}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("stagione", nargs="?", default="2024-25")
    ap.add_argument("--sims", type=int, default=8,
                    help="scenari per valutazione durante l'ottimizzazione")
    ap.add_argument("--sims-verifica", type=int, default=16)
    ap.add_argument("--semi-ottimizzazione", type=int, default=2)
    ap.add_argument("--semi-verifica", type=int, default=3)
    ap.add_argument("--seme", type=int, default=20260909)
    ap.add_argument("--iterazioni", type=int, default=MAX_ITERAZIONI)
    ap.add_argument("--lam", type=float, default=0.02)
    ap.add_argument("--squadre", default=None,
                    help="elenco separato da virgole; per difetto le tre "
                         "scelte per criteri diagnostici")
    ap.add_argument("--istante", default=None)
    a = ap.parse_args()

    istante = a.istante or datetime.datetime.now().strftime("%Y%m%dT%H%M%S")
    corsa = esec.apri(OUT, a.stagione, {
        "script": "l2_pilota_c2", "stagione": a.stagione, "sims": a.sims,
        "sims_verifica": a.sims_verifica, "seme": a.seme,
        "semi_ottimizzazione": a.semi_ottimizzazione,
        "semi_verifica": a.semi_verifica, "iterazioni": a.iterazioni,
        "lam": a.lam, "squadre": a.squadre,
        "impronte_ingressi": esec.impronte_ingressi(
            percorsi=[PROC / f"players_{a.stagione}.parquet",
                      PROC / "l2_partite.parquet",
                      PROC / f"b_predictions_{a.stagione}.json"],
            moduli=esec.MODULI_RILEVANTI),
        "impronta_script": esec.impronta_file(__file__)},
        istante=istante, prova=True)
    print(f"  destinazione: {corsa.cartella}")

    P, _ = contratto.carica_panel_multi(PROC, STAGIONI_PANEL, data_fit=None)
    P["data"] = pd.to_datetime(P["data"])
    part = pd.read_parquet(PROC / "l2_partite.parquet")
    part["data"] = pd.to_datetime(part["data"])
    cal = part[part.stagione == a.stagione].copy()
    as_of = str(cal.data.min().date())
    rose, ruolo, squadra, _ = contratto.costruisci_universo(PROC, a.stagione)
    giocatori = sorted(ruolo)
    Ppre = P[P.data < pd.Timestamp(as_of)]

    bers = presenze.costruisci(PROC / f"b_predictions_{a.stagione}.json",
                               giocatori, ruolo,
                               storia_voti=Ppre[["master_id", "stato_voto"]])
    somme = somme_per_ruolo_dal_fit(P, a.stagione)
    b_comp, diag_comp = bersaglio_compatibile(bers.per_giocatore, ruolo,
                                              squadra, somme)
    print("  somme per ruolo dalle stagioni ammesse: "
          + ", ".join(f"{k} {v:.3f}" for k, v in sorted(somme.items())))

    # --- squadre scelte per criteri DICHIARATI ---------------------------
    t = pd.DataFrame({"master_id": giocatori})
    t["squadra"] = t.master_id.map(squadra)
    t["ruolo"] = t.master_id.map(ruolo)
    t["grezzo"] = t.master_id.map(bers.per_giocatore)
    t["compatibile"] = t.master_id.map(b_comp)
    t["scostamento"] = (t.grezzo - t.compatibile).abs()
    quota = {}
    for r in ("P", "D", "C", "A"):
        sub = Ppre[Ppre.ruolo.astype(str).str.upper() == r]
        quota[r] = float((sub.stato_voto == "con_voto").mean()) or 0.5
    t["convocazione_grezza"] = t.apply(
        lambda x: x.grezzo / max(quota.get(x.ruolo, 0.5), 0.05), axis=1)
    t["troncato"] = (t.convocazione_grezza > 0.98) | (t.convocazione_grezza < 0.02)
    per_sq = t.groupby("squadra").agg(
        scostamento=("scostamento", "sum"),
        troncati=("troncato", "sum"),
        portieri_grezzi=("grezzo", lambda s: 0.0)).reset_index()
    p_sq = (t[t.ruolo == "P"].groupby("squadra")["grezzo"].sum()
            .rename("somma_portieri"))
    per_sq = per_sq.merge(p_sq, on="squadra", how="left")
    if a.squadre:
        scelte = [s.strip() for s in a.squadre.split(",")]
        criterio = "scelte a mano dalla riga di comando"
    else:
        caso_p = per_sq.sort_values("somma_portieri", ascending=False).iloc[0]
        caso_t = per_sq.sort_values("troncati", ascending=False).iloc[0]
        caso_c = per_sq.sort_values("troncati").iloc[0]
        scelte = list(dict.fromkeys([caso_p.squadra, caso_t.squadra,
                                     caso_c.squadra]))
        criterio = ("una squadra con la somma dei bersagli dei portieri piu' "
                    "alta, una con piu' troncamenti, una di controllo con il "
                    "minimo di troncamenti")
    print(f"  squadre: {scelte}  ({criterio})")
    ids = [p for p in giocatori if squadra.get(p) in scelte]
    print(f"  parametri da calibrare: {len(ids)}")

    # --- modelli, una volta sola ------------------------------------------
    t0 = time.time()
    mp, _conf, _ = cfg.costruisci_modello_partita(
        part, as_of, squadre=None, stagione_bersaglio=a.stagione,
        con_incertezza=True,
        percorsi_ingresso=[str(PROC / "l2_partite.parquet")],
        etichetta=f"pilota C2 {a.stagione}")
    m_part = pa.stima(Ppre, bersaglio_presenza=bers.per_giocatore,
                      ruolo_esterno=ruolo)          # parte da C1
    m_part.ruolo.update(ruolo)
    m_ev = ev.stima(Ppre)
    m_ev.ruolo.update(ruolo)
    m_voto = vt.stima(Ppre, "individuale")
    struttura = vt.struttura_dipendenza(Ppre, m_voto)
    fasce_sv = vt.stima_senza_voto(Ppre)
    tr = Ppre[Ppre.stato_voto == "con_voto"].copy()
    tr["ruolo"] = tr["ruolo"].astype(str).str.upper()
    bcorr = {}
    for _, sub in tr.groupby("stagione"):
        for k, v in vt.correlazioni_osservate(sub, "voto").items():
            bcorr.setdefault(k, []).append(v)
    bcorr = {k: float(np.nanmean(v)) for k, v in bcorr.items()}
    struttura = gen.calibra_dipendenza(struttura, bcorr, cal, rose, mp,
                                       m_part, m_ev, m_voto, fasce_sv,
                                       a.seme, ruolo, squadra)
    print(f"  modelli in {time.time() - t0:.1f} s")

    # --- ottimizzazione ---------------------------------------------------
    semi_ott = [a.seme + 7919 * i for i in range(a.semi_ottimizzazione)]
    semi_ver = [a.seme + 104_729 * (i + 1) for i in range(a.semi_verifica)]
    assert not set(semi_ott) & set(semi_ver), "semi di verifica non separati"
    obj = Obiettivo(cal, rose, mp, m_part, m_ev, m_voto, struttura, fasce_sv,
                    ids, b_comp, a.sims, a.lam)
    print(f"  ottimizzazione: max {a.iterazioni} iterazioni = "
          f"{2 * a.iterazioni} valutazioni, semi comuni {semi_ott}")
    t1 = time.time()
    res = spsa(obj, len(ids), semi_ott, massimo=a.iterazioni,
               rng=np.random.default_rng(a.seme))
    costo = time.time() - t1
    print(f"  fatte {res['iterazioni']} iterazioni, {obj.valutazioni} "
          f"valutazioni, {costo:.1f} s ({obj.secondi / max(obj.valutazioni,1):.2f} "
          "s per valutazione)")

    # --- verifica del candidato CONGELATO, semi separati -------------------
    print(f"  verifica su semi separati {semi_ver}, {a.sims_verifica} scenari")
    obj_v = Obiettivo(cal, rose, mp, m_part, m_ev, m_voto, struttura, fasce_sv,
                      ids, b_comp, a.sims_verifica, a.lam)
    zero = np.zeros(len(ids))
    mis = {"C1": [], "C2": []}
    for s in semi_ver:
        mis["C1"].append(obj_v.presenze_simulate(zero, s))
        mis["C2"].append(obj_v.presenze_simulate(res["theta"], s))
    grezzo = np.array([bers.per_giocatore.get(p, np.nan) for p in ids])
    comp = np.array([b_comp[p] for p in ids])
    oss = (P[(P.stagione == a.stagione)]
           .assign(v=lambda d: (d.stato_voto == "con_voto").astype(float))
           .groupby("master_id")["v"].mean())
    osservato = np.array([oss.get(p, np.nan) for p in ids])

    def statistiche(nome):
        M = np.array(mis[nome], dtype=float)
        per_replica = {}
        for et, bers_v in (("grezzo", grezzo), ("compatibile", comp),
                           ("osservato", osservato)):
            vals = [float(np.nanmean(np.abs(M[r] - bers_v)))
                    for r in range(M.shape[0])]
            per_replica[f"mae_{et}"] = {
                "media": float(np.mean(vals)),
                "es_mc": (float(np.std(vals, ddof=1) / np.sqrt(len(vals)))
                          if len(vals) > 1 else float("nan"))}
        return per_replica, M.mean(axis=0)

    st_c1, media_c1 = statistiche("C1")
    st_c2, media_c2 = statistiche("C2")
    if np.allclose(media_c1, media_c2, atol=1e-12) and             float(np.abs(res["theta"]).max()) > 0:
        raise SystemExit(
            "theta non ha nessun effetto sulla simulazione: il parametro non "
            "arriva al generatore. Due colonne identiche non sono un "
            "risultato, sono un collegamento rotto.")

    dettaglio = pd.DataFrame({
        "master_id": ids,
        "squadra": [squadra.get(p) for p in ids],
        "ruolo": [ruolo.get(p) for p in ids],
        "bersaglio_grezzo": grezzo, "bersaglio_compatibile": comp,
        "osservato_riferimento": osservato,
        "theta": res["theta"],
        "p_voto_C1": media_c1, "p_voto_C2": media_c2})
    corsa.scrivi_tabella(f"c2_dettaglio_{a.stagione}.csv", dettaglio)
    corsa.scrivi_tabella(f"c2_storia_{a.stagione}.csv",
                         pd.DataFrame(res["storia"]))
    corsa.scrivi_json(f"c2_pilota_{a.stagione}.json", {
        "esecuzione": corsa.identificativo,
        "squadre": scelte, "criterio_squadre": criterio,
        "parametri": len(ids),
        "piano": {"max_iterazioni": a.iterazioni, "pazienza": PAZIENZA,
                  "miglioramento_minimo": MIGLIORAMENTO_MINIMO,
                  "alpha": ALPHA, "gamma": GAMMA, "lam": a.lam,
                  "semi_ottimizzazione": semi_ott, "semi_verifica": semi_ver,
                  "sims": a.sims, "sims_verifica": a.sims_verifica},
        "costo": {"iterazioni_fatte": res["iterazioni"],
                  "valutazioni": obj.valutazioni,
                  "secondi_totali": round(costo, 1),
                  "secondi_per_valutazione": round(
                      obj.secondi / max(obj.valutazioni, 1), 3)},
        "somme_per_ruolo_dal_fit": somme,
        "bersaglio_compatibile": {k: v for k, v in list(diag_comp.items())[:40]},
        "verifica_C1": st_c1, "verifica_C2": st_c2,
        "nota": ("`osservato_riferimento` viene dalla stagione valutata ed e' "
                 "DIAGNOSTICO: non entra nell'obiettivo ne' nella scelta di "
                 "theta. L'obiettivo usa il bersaglio compatibile, costruito "
                 "dalle sole stagioni ammesse al fit.")})
    corsa.registra()

    print("\n-- verifica sul candidato congelato (semi separati)")
    print(f"{'':<16}{'C1':>22}{'C2':>22}")
    for k in ("mae_grezzo", "mae_compatibile", "mae_osservato"):
        print(f"  {k:<14}{st_c1[k]['media']:>12.4f} ±{st_c1[k]['es_mc']:.4f}"
              f"{st_c2[k]['media']:>12.4f} ±{st_c2[k]['es_mc']:.4f}")
    print(f"\n  scritto in {corsa.cartella}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
