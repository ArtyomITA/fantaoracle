"""Dove si perde l'informazione sulle presenze fra il bersaglio e la simulazione.

## La domanda

Il braccio `C1` riceve, per ogni giocatore, una probabilità di presenza a voto
prevista dal modello valore. Quella probabilità viene divisa per una quota
media di ruolo, troncata, e trasformata in propensione di **convocazione**; poi
il generatore sceglie gli undici, fa entrare i subentranti e attribuisce i voti.

Lo scarto che `partecipazione.stima` registra durante l'assegnazione confronta
**propensioni assegnate**, non presenze simulate: lo dice il codice stesso. Qui
si misura il passaggio completo, giocatore per giocatore:

    p_voto richiesta → quota di conversione → convocazione voluta
      → troncamento → propensione assegnata
      → P(titolare), P(entrato), P(voto) SIMULATE → scarto finale

con la precisione Monte Carlo dichiarata, ricavata da semi distinti.

## Che cosa NON fa

Non calibra sui risultati della stagione valutata: i bersagli vengono dal
modello valore, la quota di conversione dai dati ammessi al fit, e la
probabilità simulata dal generatore. La stagione valutata entra solo come
riferimento descrittivo, e le colonne che ne dipendono sono marcate.

Non propone un nuovo metodo di calibrazione: se la diagnosi mostra che ne serve
uno, la proposta va scritta e l'implementazione fermata.

Uso:

    PYTHONPATH=src python scripts/l2_diagnosi_presenze.py 2024-25 \\
        --sims 20 --semi 3 --prova
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

FASCE = [(0.0, 0.1), (0.1, 0.3), (0.3, 0.5), (0.5, 0.7), (0.7, 0.9),
         (0.9, 1.01)]


def fascia(p: float) -> str:
    for lo, hi in FASCE:
        if lo <= p < hi:
            return f"{lo:.1f}-{min(hi, 1.0):.1f}"
    return "?"


def simula(cal, rose_liste, mp, m_part, m_ev, m_voto, struttura, fasce_sv,
           giocatori, sims: int, seme: int) -> dict:
    """Probabilità simulate di titolarità, ingresso e voto, per giocatore."""
    c = gen.genera(cal, rose_liste, mp, m_part, m_ev, m_voto, n_sims=sims,
                   seme=seme, dipendenza=struttura, fasce_sv=fasce_sv,
                   verifica=True)
    ixc = {pid: i for i, pid in enumerate(c.giocatori)}
    n_g = len(c.giornate)
    fuori = {}
    gioca = c.gioca
    titolare = getattr(c, "titolare", None)
    for pid in giocatori:
        k = ixc.get(pid)
        if k is None:
            fuori[pid] = {"p_voto_simulata": np.nan, "p_titolare_simulata": np.nan}
            continue
        g = gioca[:, :n_g, k]
        d = {"p_voto_simulata": float(g.mean())}
        if titolare is not None:
            d["p_titolare_simulata"] = float(titolare[:, :n_g, k].mean())
        fuori[pid] = d
    return fuori


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("stagione", nargs="?", default="2024-25")
    ap.add_argument("--sims", type=int, default=20)
    ap.add_argument("--semi", type=int, default=3)
    ap.add_argument("--seme", type=int, default=20260909)
    ap.add_argument("--rose-da", choices=["listone", "squadra"],
                    default="listone")
    ap.add_argument("--prova", action="store_true")
    ap.add_argument("--destinazione", default=None)
    ap.add_argument("--istante", default=None)
    a = ap.parse_args()

    istante = a.istante or datetime.datetime.now().strftime("%Y%m%dT%H%M%S")
    configurazione = {"script": "l2_diagnosi_presenze", "stagione": a.stagione,
                      "sims": a.sims, "semi": a.semi, "seme": a.seme,
                      "rose_da": a.rose_da,
                      "impronta_script": esec.impronta_file(__file__)}
    corsa = esec.apri(OUT, a.stagione, configurazione, istante=istante,
                      prova=a.prova, destinazione=a.destinazione)
    print(f"  destinazione: {corsa.cartella}")

    P, _ = contratto.carica_panel_multi(PROC, STAGIONI_PANEL, data_fit=None)
    P["data"] = pd.to_datetime(P["data"])
    part = pd.read_parquet(PROC / "l2_partite.parquet")
    part["data"] = pd.to_datetime(part["data"])
    cal = part[part.stagione == a.stagione].copy()
    as_of = str(cal.data.min().date())
    rose_liste, ruolo, squadra, _ = contratto.costruisci_universo(
        PROC, a.stagione, rose_da=a.rose_da)
    giocatori = sorted(ruolo)
    Ppre = P[P.data < pd.Timestamp(as_of)]

    # --- bersagli, dalla stessa strada del banco --------------------------
    bers = presenze.costruisci(PROC / f"b_predictions_{a.stagione}.json",
                               giocatori, ruolo,
                               storia_voti=Ppre[["master_id", "stato_voto"]])
    print(f"  bersagli: {bers.diagnostica['con_bersaglio']}/"
          f"{bers.diagnostica['universo']}")

    # --- vincolo fisico: i bersagli sono realizzabili tutti insieme? ------
    t = pd.DataFrame({"master_id": list(bers.per_giocatore),
                      "p_voto_richiesta": list(bers.per_giocatore.values())})
    t["squadra"] = t.master_id.map(squadra)
    t["ruolo"] = t.master_id.map(ruolo)
    t["fonte"] = t.master_id.map(bers.fonte)
    somma_sq = t.groupby("squadra")["p_voto_richiesta"].sum()
    reali = (P[(P.stagione == a.stagione) & (P.stato_voto == "con_voto")]
             .groupby(["squadra_alla_data", "giornata"]).size())
    vincolo = {
        "voti_per_squadra_giornata_osservati_mediana": float(reali.median()),
        "voti_per_squadra_giornata_osservati_media": float(reali.mean()),
        "voti_per_squadra_giornata_osservati_max": int(reali.max()),
        "somma_bersagli_per_squadra_media": float(somma_sq.mean()),
        "somma_bersagli_per_squadra_min": float(somma_sq.min()),
        "somma_bersagli_per_squadra_max": float(somma_sq.max()),
        "squadre_sopra_la_media_osservata": int(
            (somma_sq > reali.mean()).sum()),
        "squadre": int(len(somma_sq)),
    }
    print(f"  vincolo: somma bersagli per squadra media "
          f"{vincolo['somma_bersagli_per_squadra_media']:.2f} contro "
          f"{vincolo['voti_per_squadra_giornata_osservati_media']:.2f} voti "
          f"osservati per squadra-giornata; "
          f"{vincolo['squadre_sopra_la_media_osservata']}/"
          f"{vincolo['squadre']} squadre sopra")

    # --- modelli: C0 senza bersaglio, C1 con ------------------------------
    t0 = time.time()
    mp, conf, _ = cfg.costruisci_modello_partita(
        part, as_of, squadre=None, stagione_bersaglio=a.stagione,
        con_incertezza=True,
        percorsi_ingresso=[str(PROC / "l2_partite.parquet")],
        etichetta=f"diagnosi presenze {a.stagione}")
    m_part_c0 = pa.stima(Ppre)
    m_part_c1 = pa.stima(Ppre, bersaglio_presenza=bers.per_giocatore,
                         ruolo_esterno=ruolo)
    m_part_c1.ruolo.update(ruolo)
    m_part_c0.ruolo.update(ruolo)
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
    struttura = gen.calibra_dipendenza(struttura, bcorr, cal, rose_liste, mp,
                                       m_part_c0, m_ev, m_voto, fasce_sv,
                                       a.seme, ruolo, squadra)
    print(f"  modelli in {time.time() - t0:.1f} s")

    d1 = m_part_c1.diagnostica.get("bersaglio_presenza") or {}
    dett = pd.DataFrame(d1.get("dettaglio") or [])
    print(f"  assegnazione: {d1.get('applicati')} applicati, "
          f"{d1.get('iniziati_senza_storia')} iniziati senza storia, "
          f"{d1.get('troncati_in_alto')} troncati in alto, "
          f"{d1.get('troncati_in_basso')} in basso")

    # --- simulazione, piu' semi per la precisione Monte Carlo -------------
    semi = [a.seme + 100_003 * r for r in range(max(1, a.semi))]
    per_braccio = {}
    for nome, m_part in (("C0", m_part_c0), ("C1", m_part_c1)):
        repliche = []
        for s in semi:
            t1 = time.time()
            repliche.append(simula(cal, rose_liste, mp, m_part, m_ev, m_voto,
                                   struttura, fasce_sv, giocatori, a.sims, s))
            print(f"  {nome} seme {s}: {time.time() - t1:.1f} s")
        per_braccio[nome] = repliche

    def raccogli(nome, campo):
        M = np.array([[r[p].get(campo, np.nan) for p in giocatori]
                      for r in per_braccio[nome]], dtype=float)
        return M.mean(axis=0), (M.std(axis=0, ddof=1) / np.sqrt(len(semi))
                                if len(semi) > 1 else np.full(M.shape[1], np.nan))

    tab = pd.DataFrame({"master_id": giocatori})
    tab["ruolo"] = tab.master_id.map(ruolo)
    tab["squadra"] = tab.master_id.map(squadra)
    tab["fonte_bersaglio"] = tab.master_id.map(bers.fonte)
    tab["p_voto_richiesta"] = tab.master_id.map(bers.per_giocatore)
    if not dett.empty:
        #  ripete  e : si tolgono prima del
        # merge, altrimenti pandas le rinomina con i suffissi e le colonne
        # attese spariscono
        tab = tab.merge(dett.drop(columns=[c for c in ("ruolo", "p_voto_richiesta")
                                           if c in dett.columns]),
                        on="master_id", how="left")
    for nome in ("C0", "C1"):
        m, es = raccogli(nome, "p_voto_simulata")
        tab[f"p_voto_simulata_{nome}"] = m
        tab[f"es_mc_{nome}"] = es
        mt, _ = raccogli(nome, "p_titolare_simulata")
        tab[f"p_titolare_simulata_{nome}"] = mt
    tab["scarto_C1"] = tab["p_voto_simulata_C1"] - tab["p_voto_richiesta"]
    tab["scarto_C0"] = tab["p_voto_simulata_C0"] - tab["p_voto_richiesta"]
    tab["fascia"] = tab["p_voto_richiesta"].map(
        lambda x: fascia(x) if pd.notna(x) else "senza bersaglio")
    # riferimento descrittivo dalla stagione valutata: NON entra in nessuna
    # calibrazione, serve solo a leggere la tabella
    veri = (P[(P.stagione == a.stagione)]
            .assign(v=lambda d: (d.stato_voto == "con_voto").astype(float))
            .groupby("master_id")["v"].mean())
    tab["p_voto_osservata_riferimento"] = tab.master_id.map(veri)
    nuovi = set(tab.loc[tab["iniziato_senza_storia"] == True, "master_id"]) \
        if "iniziato_senza_storia" in tab.columns else set()
    tab["nuovo"] = tab.master_id.isin(nuovi)

    corsa.scrivi_tabella(f"presenze_dettaglio_{a.stagione}.csv", tab)

    def riassunto(chiave):
        g = tab.dropna(subset=["p_voto_richiesta"]).groupby(chiave)
        return g.agg(giocatori=("master_id", "size"),
                     richiesta=("p_voto_richiesta", "mean"),
                     simulata_C1=("p_voto_simulata_C1", "mean"),
                     simulata_C0=("p_voto_simulata_C0", "mean"),
                     scarto_C1=("scarto_C1", "mean"),
                     scarto_C0=("scarto_C0", "mean"),
                     es_mc=("es_mc_C1", "mean")).round(4).reset_index()

    riass = {}
    for chiave in ("ruolo", "fascia", "fonte_bersaglio", "nuovo"):
        r = riassunto(chiave)
        riass[chiave] = r
        corsa.scrivi_tabella(f"presenze_per_{chiave}_{a.stagione}.csv", r)
        print(f"\n-- per {chiave}")
        print(r.to_string(index=False))

    # R15: i tre numeri su cui poggia la conclusione principale erano
    # calcolati a mano fuori dagli artefatti. Adesso li scrive il codice, in un
    # blocco separato e marcato, perche' usano la stagione valutata.
    oss_rif = tab["p_voto_osservata_riferimento"]
    con_oss = oss_rif.notna()
    contro_osservato = {
        "nota": ("DIAGNOSTICO, non una calibrazione: usa la stagione "
                 "valutata. Serve a dire se il bersaglio sia piu' o meno "
                 "accurato di quello che il cubo ne fa, e non entra in "
                 "nessuna stima ne' in nessun fit."),
        "giocatori": int(con_oss.sum()),
    }
    for col, et in (("p_voto_richiesta", "bersaglio"),
                    ("p_voto_simulata_C1", "C1"),
                    ("p_voto_simulata_C0", "C0")):
        e = tab.loc[con_oss, col] - oss_rif[con_oss]
        contro_osservato[f"errore_assoluto_medio_{et}"] = float(e.abs().mean())
        contro_osservato[f"scostamento_medio_{et}"] = float(e.mean())
    per_ruolo_osservato = (
        tab[con_oss]
        .assign(e_bersaglio=lambda x: (x.p_voto_richiesta - oss_rif).abs(),
                e_C1=lambda x: (x.p_voto_simulata_C1 - oss_rif).abs(),
                e_C0=lambda x: (x.p_voto_simulata_C0 - oss_rif).abs())
        .groupby("ruolo")[["e_bersaglio", "e_C1", "e_C0"]].mean().round(4))
    contro_osservato["per_ruolo"] = {
        k: v for k, v in per_ruolo_osservato.to_dict("index").items()}
    corsa.scrivi_tabella(f"presenze_contro_osservato_{a.stagione}.csv",
                         per_ruolo_osservato.reset_index())

    globale = {
        "scarto_medio_C1": float(tab["scarto_C1"].mean()),
        "scarto_medio_assoluto_C1": float(tab["scarto_C1"].abs().mean()),
        "scarto_medio_C0": float(tab["scarto_C0"].mean()),
        "scarto_medio_assoluto_C0": float(tab["scarto_C0"].abs().mean()),
        "es_mc_medio": float(tab["es_mc_C1"].mean()),
        "correlazione_richiesta_simulata_C1": float(
            tab[["p_voto_richiesta", "p_voto_simulata_C1"]].corr().iloc[0, 1]),
        "correlazione_richiesta_simulata_C0": float(
            tab[["p_voto_richiesta", "p_voto_simulata_C0"]].corr().iloc[0, 1]),
        "somma_richiesta": float(tab["p_voto_richiesta"].sum()),
        "somma_simulata_C1": float(tab["p_voto_simulata_C1"].sum()),
        "somma_simulata_C0": float(tab["p_voto_simulata_C0"].sum()),
    }
    corsa.scrivi_json(f"presenze_diagnosi_{a.stagione}.json", {
        "esecuzione": corsa.identificativo,
        "semi": semi, "scenari": a.sims,
        "vincolo_fisico": vincolo,
        "assegnazione": {k: v for k, v in d1.items() if k != "dettaglio"},
        "globale": globale,
        "contro_osservato": contro_osservato,
        "nota": ("`p_voto_osservata_riferimento` viene dalla stagione "
                 "valutata ed e' solo descrittiva: non entra in nessuna "
                 "calibrazione. Tutto il resto usa dati ammessi al fit e "
                 "simulazioni del modello.")})
    corsa.registra()
    print("\n-- globale")
    for k, v in globale.items():
        print(f"  {k:<40} {v:+.4f}")
    print("\n-- contro l'osservato (DIAGNOSTICO: usa la stagione valutata)")
    for k, v in contro_osservato.items():
        if isinstance(v, float):
            print(f"  {k:<40} {v:+.4f}")
    print(per_ruolo_osservato.to_string())
    print(f"\nscritto in {corsa.cartella}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
