"""Pilota `C2`: calibrazione regolarizzata del generatore verso bersagli.

`C2` è un candidato **sperimentale**, separato da `C1`, che resta com'è con i
suoi risultati pubblicati.

## Che cosa si ottimizza

Uno scostamento additivo sul logit di convocazione, uno per giocatore delle
squadre scelte. `θ = 0` è il generatore attuale, e la regolarizzazione
penalizza gli scostamenti inutili.

    L(θ) = media_i (P_voto_sim(i | θ) − b_bersaglio[i])² + λ·media(θ²)

## Che cosa è cambiato dopo la verifica indipendente del 9 settembre

**Il cutoff è esplicito, e vale per tutto quello che il codice controlla.**
Non vale per `b_predictions`: quel file non porta una data, la sua
disponibilità al cutoff non è dimostrata, e il bersaglio ne viene per intero —
sul 2024-25 copre 679 giocatori su 679, quindi il ramo del prior di ruolo, che
userebbe informazione anteriore, non si attiva mai. Il cutoff disciplina il
panel, le statistiche e la selezione; sull'ingresso principale è una promessa
non verificata. Il pilota precedente costruiva il
bersaglio passando il panel intero: per il 2024-25 entravano **25.194 righe del
2025-26**, posteriori al cutoff, e alterarle cambiava i totali per ruolo. Ora
c'è una sola data limite, dichiarata, e da lì passano bersaglio, statistiche
ausiliarie e selezione delle squadre. Gli esiti futuri entrano soltanto nella
valutazione finale, in colonne marcate come diagnostiche.

**La somma dichiarata è quella ottenuta.** La trasformazione precedente
riscalava e poi troncava a `[0, 1]` senza redistribuire, ma registrava la somma
*richiesta*: `[0,9; 0,1]` verso 2 dava 1,2 dichiarato 2. Adesso la proiezione
rispetta la somma anche dopo la saturazione, e la diagnostica riporta
richiesto, ottenuto, saturati e scarto introdotto.

**La somma per ruolo è un riferimento statistico, non un vincolo fisico.** Una
media storica non deriva dalle regole del generatore, e imporla a ogni squadra
cancellerebbe differenze tattiche che possono essere vere. Per difetto entra
come regolarizzazione morbida (`--modo-bersaglio riferimento`); il modo
`vincolo` esiste per quando una somma è davvero derivata dalle regole, e oggi
non lo è.

**L'arresto misura la soluzione, non le perturbazioni.** Prima si confrontavano
medie di `L(θ ± cδ)` con perturbazione decrescente e semi alternati: non è una
misura confrontabile dell'obiettivo. Ora un insieme di **monitoraggio** con
semi propri valuta `L(θ)` al θ corrente, e il candidato restituito è il
migliore osservato, non l'ultimo.

**I guadagni sono calibrati, non scelti a mano.** Con una perdita che è una
media su `p` parametri il gradiente è dell'ordine di `1/p` e un `a` fissato a
occhio produce passi invisibili: sulla quadratica senza rumore con ottimo noto,
30 iterazioni lasciavano `‖θ‖` a 0,0056. `a` si ricava da una stima empirica
del gradiente perché il primo passo valga quello che si vuole.

**Il budget è dimensionato.** La fonte SPSA dice che le direzioni sbagliate si
mediano *nel corso di molte iterazioni*: con `p` parametri il rapporto fra
gradiente vero e stima per componente va come `1/sqrt(p)`, quindi servono
centinaia di iterazioni. Trenta non bastavano nemmeno senza rumore.

**Il confronto è appaiato.** Per ogni seme di verifica si calcola
`d_r = MAE_C2,r − MAE_C1,r` e se ne riporta media ed errore standard: due medie
separate che differiscono meno dei rispettivi errori non dimostrano equivalenza.

## Che cosa il pilota NON fa

Non promuove niente, non tocca `C1`, non calibra sugli esiti della stagione
valutata. Il confronto contro l'osservato è **diagnostico**.
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

from fantabot.tabellino import calibrazione as calib          # noqa: E402
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
MAX_ITERAZIONI = 300
PAZIENZA = 6              # controlli di monitoraggio senza miglioramento
MIGLIORAMENTO_MINIMO = 0.01
OGNI = 15                 # ogni quante iterazioni si monitora
# Ampiezza del primo passo in theta, da cui si ricava `a`. Vale 0,05 e non
# 0,20 perche' 0,20 fa DIVERGERE SPSA sulla funzione con ottimo noto: con `A`
# coerente fra calibrazione e ricerca, p = 103 e 600 iterazioni, 0,20 lascia il
# candidato a theta = 0 mentre 0,05 porta la perdita da 0,010 a 0,000061 con
# ||theta|| 9,98 contro l'ottimo 10,15.
#
# Il pilota del 9 settembre dichiarava 0,20 ma ne applicava 0,04855948114,
# perche' la calibrazione usava `A = 1` e la ricerca `A = 20`.
#
# 0,0486 non e' 0,05, e la differenza non e' zero: a parita' del gradiente
# mediano misurato allora (0,007439505657), il guadagno passa da
# `a = 40,804304022` a `a = 42,014765258`, cioe' **+2,9665 %**. Chi rieseguisse
# con questo codice NON otterrebbe gli stessi numeri del pilota del 9
# settembre. Probabilmente otterrebbe numeri vicini — ma «probabilmente
# vicini» non e' «identici», e l'artefatto salvato resta l'unica prova di quei
# valori. Il candidato congelato e le sue misure si conservano come sono; una
# riesecuzione e' un'esecuzione nuova, e va registrata come tale.
PASSO_VOLUTO = 0.05
# Il passo che il pilota del 9 settembre ha davvero applicato, ricostruito
# dall'artefatto: serve a chi volesse riprodurne i numeri esatti.
PASSO_APPLICATO_20260909 = 0.04855948114
C_PERTURBAZIONE = 0.10


def bersaglio_verso_somma(b_grezzo: dict, ruolo: dict, squadra: dict,
                          somme_ruolo: dict, *, modo: str = "riferimento",
                          peso: float = 0.5) -> tuple[dict, dict]:
    """Avvicina il bersaglio alle somme per (squadra, ruolo), e lo dichiara.

    `modo="riferimento"` tira verso la somma con il peso dato: la media storica
    per ruolo è un riferimento statistico, non una legge del generatore.
    `modo="vincolo"` la impone, con una proiezione che la rispetta anche dopo
    la saturazione.

    In entrambi i casi la diagnostica riporta la somma **ottenuta**, non quella
    richiesta: la versione precedente riscalava, troncava a `[0, 1]` senza
    redistribuire, e registrava comunque il richiesto.
    """
    per_cella = {}
    for pid in b_grezzo:
        per_cella.setdefault((squadra.get(pid), ruolo.get(pid)), []).append(pid)
    fuori, diag = {}, {}
    for (sq, r), ids in sorted(per_cella.items(), key=lambda x: str(x[0])):
        v0 = np.array([b_grezzo[p] for p in ids], dtype=float)
        somma_voluta = somme_ruolo.get(r)
        if somma_voluta is None:
            for p, x in zip(ids, v0):
                fuori[p] = float(x)
            continue
        v, d = calib.proietta_su_somma(v0, somma_voluta, modo=modo, peso=peso)
        for p, x in zip(ids, v):
            fuori[p] = float(x)
        d["giocatori"] = len(ids)
        diag[f"{sq}|{r}"] = d
    return fuori, diag


def somme_per_ruolo(P: pd.DataFrame, cutoff) -> dict:
    """Voti medi per squadra-giornata e ruolo, dalle sole righe ammesse.

    Prima riceveva il panel intero e si limitava a escludere la stagione
    valutata: per il 2024-25 entravano 25.194 righe del 2025-26, e alterarle
    cambiava i totali. Adesso il filtro è la **data**, come per tutto il resto.
    """
    d = P[(pd.to_datetime(P["data"]) < pd.Timestamp(cutoff))
          & (P.stato_voto == "con_voto")]
    per = (d.groupby(["stagione", "squadra_alla_data", "giornata", "ruolo"])
             .size().rename("n").reset_index())
    return {r: float(g["n"].mean()) for r, g in per.groupby("ruolo")}


class IngressiC2:
    """Tutto quello che il pilota costruisce PRIMA di ottimizzare.

    Esiste per un motivo preciso: il controfattuale temporale deve esercitare
    **questo** codice, non una sua copia. La versione precedente della prova
    ricostruiva una funzione `catena` che duplicava questi passaggi, quindi
    poteva restare verde mentre il produttore cambiava.
    """

    # Classe normale e non `dataclass`: con `from __future__ import
    # annotations`, `dataclasses` risolve le annotazioni cercando il modulo in
    # `sys.modules`, e questo script viene caricato per percorso — dal
    # controfattuale, dalla verifica, dalle prove — senza esserci registrato.
    CAMPI = ("cutoff", "stagione", "giocatori", "ruolo", "squadra", "rose",
             "Ppre", "bers", "somme", "obiettivo", "diagnostica_bersaglio",
             "quota", "tabella", "per_squadra", "scelte", "criterio", "ids")

    def __init__(self, **kw):
        mancanti = [c for c in self.CAMPI if c not in kw]
        if mancanti:
            raise TypeError(f"IngressiC2, campi mancanti: {mancanti}")
        extra = [k for k in kw if k not in self.CAMPI]
        if extra:
            raise TypeError(f"IngressiC2, campi sconosciuti: {extra}")
        for c in self.CAMPI:
            setattr(self, c, kw[c])

    def vettori(self) -> dict:
        """Le grandezze da confrontare, **per identificativo**.

        Confrontare somme nasconde gli scambi fra giocatori: due bersagli che
        si scambiano di posto danno la stessa somma. Qui ogni grandezza e' un
        dizionario `id -> valore` o una lista ordinata, e il confronto e'
        elemento per elemento.
        """
        return {
            "bersaglio_grezzo": {int(k): round(float(v), 12)
                                 for k, v in self.bers.per_giocatore.items()},
            "bersaglio_obiettivo": {int(k): round(float(v), 12)
                                    for k, v in self.obiettivo.items()},
            "somme_ruolo": {str(k): round(float(v), 12)
                            for k, v in sorted(self.somme.items())},
            "quota_ruolo": {str(k): round(float(v), 12)
                            for k, v in sorted(self.quota.items())},
            "universo": [int(x) for x in self.giocatori],
            "mappa_ruoli": {int(k): str(v) for k, v in sorted(self.ruolo.items())},
            "mappa_squadre": {int(k): str(v)
                              for k, v in sorted(self.squadra.items())},
            "righe_fit": int(len(self.Ppre)),
            "squadre_scelte": [str(x) for x in self.scelte],
            "parametri": [int(x) for x in self.ids],
        }


def costruisci_ingressi(P, *, stagione: str, cutoff, proc: Path = None,
                        modo_bersaglio: str = "riferimento",
                        peso_bersaglio: float = 0.5,
                        squadre: str = None, n_squadre: int = 1,
                        universo=None) -> IngressiC2:
    """Costruisce gli ingressi del pilota dalle sole righe anteriori al cutoff.

    `universo` permette al controfattuale di perturbare la mappa dei ruoli
    senza toccare il panel: sono due dipendenze diverse, e vanno verificate
    ciascuna sulla propria sorgente.
    """
    proc = Path(proc) if proc is not None else PROC
    cutoff = pd.Timestamp(cutoff)
    if universo is None:
        universo = contratto.costruisci_universo(proc, stagione)
    rose, ruolo, squadra, _resto = universo
    giocatori = sorted(ruolo)
    P = P.copy()
    P["data"] = pd.to_datetime(P["data"])
    Ppre = P[P.data < cutoff]

    bers = presenze.costruisci(proc / f"b_predictions_{stagione}.json",
                               giocatori, ruolo,
                               storia_voti=Ppre[["master_id", "stato_voto"]])
    somme = somme_per_ruolo(P, cutoff)
    obiettivo, diag_b = bersaglio_verso_somma(
        bers.per_giocatore, ruolo, squadra, somme,
        modo=modo_bersaglio, peso=peso_bersaglio)

    quota = {}
    for r in ("P", "D", "C", "A"):
        sub = Ppre[Ppre.ruolo.astype(str).str.upper() == r]
        quota[r] = float((sub.stato_voto == "con_voto").mean()) or 0.5

    t = pd.DataFrame({"master_id": giocatori})
    t["squadra"] = t.master_id.map(squadra)
    t["ruolo"] = t.master_id.map(ruolo)
    t["grezzo"] = t.master_id.map(bers.per_giocatore)
    t["obiettivo"] = t.master_id.map(obiettivo)
    t["scostamento"] = (t.grezzo - t.obiettivo).abs()
    t["convocazione_grezza"] = t.apply(
        lambda x: x.grezzo / max(quota.get(x.ruolo, 0.5), 0.05), axis=1)
    t["troncato"] = (t.convocazione_grezza > 0.98) | (t.convocazione_grezza < 0.02)
    per_sq = t.groupby("squadra").agg(scostamento=("scostamento", "sum"),
                                      troncati=("troncato", "sum")).reset_index()
    p_sq = (t[t.ruolo == "P"].groupby("squadra")["grezzo"].sum()
            .rename("somma_portieri"))
    per_sq = per_sq.merge(p_sq, on="squadra", how="left")
    if squadre:
        scelte = [x.strip() for x in str(squadre).split(",")]
        criterio = "scelte a mano dalla riga di comando"
    else:
        ordine = per_sq.sort_values("somma_portieri", ascending=False)
        scelte = list(ordine.squadra.head(n_squadre))
        criterio = (f"le {n_squadre} squadre con la somma dei bersagli dei "
                    "portieri piu' alta. E' un criterio di selezione, non una "
                    "misura di distanza: le due distanze che questo script "
                    "calcola (scostamento dal bersaglio trasformato, numero di "
                    "troncamenti) indicano altre squadre, e sono registrate "
                    "nell'artefatto perche' si veda")
    ids = [p for p in giocatori if squadra.get(p) in scelte]
    return IngressiC2(
        cutoff=cutoff, stagione=stagione, giocatori=giocatori, ruolo=ruolo,
        squadra=squadra, rose=rose, Ppre=Ppre, bers=bers, somme=somme,
        obiettivo=obiettivo, diagnostica_bersaglio=diag_b, quota=quota,
        tabella=t, per_squadra=per_sq, scelte=scelte, criterio=criterio,
        ids=ids)


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
        # `prop_convocato`: scrivere quest'ultima non cambiava niente.
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
        # Un giocatore obbligatorio senza probabilita' e' un errore, non una
        # riga da togliere: prima `isfinite` lo eliminava in silenzio, e
        # l'universo su cui si ottimizzava cambiava senza che nessuno lo
        # sapesse.
        mancanti = [p for p in self.ids if p not in ixc]
        if mancanti:
            raise RuntimeError(
                f"{len(mancanti)} giocatori dell'universo non sono nel cubo, "
                f"per esempio {mancanti[:5]}: la perdita non si calcola su un "
                "universo diverso da quello dichiarato.")
        fuori = np.array([float(c.gioca[:, :n_g, ixc[p]].mean())
                          for p in self.ids])
        if not np.all(np.isfinite(fuori)):
            rotti = [self.ids[k] for k in np.flatnonzero(~np.isfinite(fuori))]
            raise RuntimeError(
                f"probabilita' non finita per {len(rotti)} giocatori, per "
                f"esempio {rotti[:5]}")
        self.valutazioni += 1
        self.secondi += time.time() - t0
        return fuori

    def __call__(self, theta, seme) -> float:
        p = self.presenze_simulate(theta, seme)
        scarto = float(np.mean((p - self.bersaglio) ** 2))
        pen = self.lam * float(np.mean(np.asarray(theta, float) ** 2))
        return scarto + pen


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("stagione", nargs="?", default="2024-25")
    ap.add_argument("--cutoff", default=None,
                    help="data limite esplicita per bersaglio, statistiche e "
                         "selezione. Per difetto la prima partita della "
                         "stagione valutata.")
    ap.add_argument("--sims", type=int, default=6)
    ap.add_argument("--sims-monitoraggio", type=int, default=10)
    ap.add_argument("--sims-verifica", type=int, default=16)
    ap.add_argument("--semi-ottimizzazione", type=int, default=2)
    ap.add_argument("--semi-monitoraggio", type=int, default=2)
    ap.add_argument("--semi-verifica", type=int, default=5)
    ap.add_argument("--seme", type=int, default=20260909)
    ap.add_argument("--iterazioni", type=int, default=MAX_ITERAZIONI)
    ap.add_argument("--lam", type=float, default=0.02)
    ap.add_argument("--modo-bersaglio", choices=["riferimento", "vincolo"],
                    default="riferimento",
                    help="`riferimento`: la somma per ruolo tira senza essere "
                         "imposta, perche' e' una media storica e non una "
                         "regola del generatore. `vincolo`: imposta, per "
                         "quando la somma e' davvero derivata dalle regole.")
    ap.add_argument("--peso-bersaglio", type=float, default=0.5)
    ap.add_argument("--squadre", default=None)
    ap.add_argument("--n-squadre", type=int, default=1)
    ap.add_argument("--istante", default=None)
    a = ap.parse_args()

    istante = a.istante or datetime.datetime.now().strftime("%Y%m%dT%H%M%S")

    P, _ = contratto.carica_panel_multi(PROC, STAGIONI_PANEL, data_fit=None)
    P["data"] = pd.to_datetime(P["data"])
    part = pd.read_parquet(PROC / "l2_partite.parquet")
    part["data"] = pd.to_datetime(part["data"])
    cal = part[part.stagione == a.stagione].copy()
    # UN SOLO cutoff, esplicito, per tutto quello che precede la valutazione
    cutoff = pd.Timestamp(a.cutoff) if a.cutoff else cal.data.min()
    as_of = str(pd.Timestamp(cutoff).date())

    piano = {
        "script": "l2_pilota_c2", "stagione": a.stagione, "cutoff": as_of,
        "sims": a.sims, "sims_monitoraggio": a.sims_monitoraggio,
        "sims_verifica": a.sims_verifica, "seme": a.seme,
        "semi_ottimizzazione": a.semi_ottimizzazione,
        "semi_monitoraggio": a.semi_monitoraggio,
        "semi_verifica": a.semi_verifica, "iterazioni": a.iterazioni,
        "lam": a.lam, "modo_bersaglio": a.modo_bersaglio,
        "peso_bersaglio": a.peso_bersaglio, "squadre": a.squadre,
        "n_squadre": a.n_squadre, "passo_voluto": PASSO_VOLUTO,
        "c": C_PERTURBAZIONE, "pazienza": PAZIENZA, "ogni": OGNI,
        "impronte_ingressi": esec.impronte_ingressi(
            percorsi=[PROC / f"players_{a.stagione}.parquet",
                      PROC / "l2_partite.parquet",
                      PROC / f"b_predictions_{a.stagione}.json"],
            moduli=esec.MODULI_RILEVANTI),
        "impronta_script": esec.impronta_file(__file__)}
    corsa = esec.apri(OUT, a.stagione, piano, istante=istante, prova=True)
    print(f"  destinazione: {corsa.cartella}")
    print(f"  cutoff: {as_of} — vale per bersaglio, statistiche e selezione")

    ing = costruisci_ingressi(
        P, stagione=a.stagione, cutoff=cutoff, proc=PROC,
        modo_bersaglio=a.modo_bersaglio, peso_bersaglio=a.peso_bersaglio,
        squadre=a.squadre, n_squadre=a.n_squadre)
    rose, ruolo, squadra = ing.rose, ing.ruolo, ing.squadra
    giocatori, Ppre, bers = ing.giocatori, ing.Ppre, ing.bers
    somme, b_obiettivo, diag_b = ing.somme, ing.obiettivo, ing.diagnostica_bersaglio
    quota, t, per_sq = ing.quota, ing.tabella, ing.per_squadra
    scelte, criterio, ids = ing.scelte, ing.criterio, ing.ids

    print("  somme per ruolo, righe anteriori al cutoff: "
          + ", ".join(f"{k} {v:.4f}" for k, v in sorted(somme.items())))
    raggiunte = sum(1 for d in diag_b.values() if d.get("raggiunta"))
    print(f"  bersaglio ({a.modo_bersaglio}): {len(diag_b)} celle, "
          f"{raggiunte} con la somma raggiunta, "
          f"{sum(d.get('saturati', 0) for d in diag_b.values())} saturati")
    print(f"  squadre {scelte} ({criterio})")
    print(f"  parametri: {len(ids)}")

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

    # --- semi: tre insiemi disgiunti --------------------------------------
    semi_ott = [a.seme + 7919 * i for i in range(a.semi_ottimizzazione)]
    semi_mon = [a.seme + 15_485_863 * (i + 1) for i in range(a.semi_monitoraggio)]
    semi_ver = [a.seme + 104_729 * (i + 1) for i in range(a.semi_verifica)]
    assert not (set(semi_ott) & set(semi_mon)), "monitoraggio non separato"
    assert not (set(semi_ott) & set(semi_ver)), "verifica non separata"
    assert not (set(semi_mon) & set(semi_ver)), "verifica e monitoraggio uguali"

    obj = Obiettivo(cal, rose, mp, m_part, m_ev, m_voto, struttura, fasce_sv,
                    ids, b_obiettivo, a.sims, a.lam)
    obj_mon = Obiettivo(cal, rose, mp, m_part, m_ev, m_voto, struttura,
                        fasce_sv, ids, b_obiettivo, a.sims_monitoraggio, a.lam)

    # --- il parametro arriva al generatore? prova rilevabile ---------------
    grande = np.full(len(ids), 3.0)
    p0 = obj_mon.presenze_simulate(np.zeros(len(ids)), semi_mon[0])
    p1 = obj_mon.presenze_simulate(grande, semi_mon[0])
    scarto_rilevabile = float(np.max(np.abs(p1 - p0)))
    print(f"  collegamento: theta=+3 sul logit sposta la presenza al massimo "
          f"di {scarto_rilevabile:.4f}")
    if scarto_rilevabile < 0.05:
        raise SystemExit(
            "una perturbazione volutamente grande non muove le presenze: il "
            "parametro non arriva al generatore.")

    # --- guadagno calibrato ------------------------------------------------
    # `massimo` passato apposta: la calibrazione deve usare lo STESSO `A` di
    # `spsa`, altrimenti il primo passo non vale quello che dichiara. E un rng
    # diverso, perche' la stima del gradiente non sia fatta sulla stessa
    # perturbazione che poi il primo passo riusa.
    g = calib.calibra_guadagno(obj, np.zeros(len(ids)), semi_ott,
                               c=C_PERTURBAZIONE, passo_voluto=PASSO_VOLUTO,
                               campioni=3, massimo=a.iterazioni,
                               rng=np.random.default_rng(a.seme + 1))
    if g["a"] is None:
        raise SystemExit(f"guadagno non calibrabile: {g['nota']}")
    print(f"  gradiente mediano {g['gradiente_mediano']:.6g} -> a = {g['a']:.2f} "
          f"con A = {g['A']:.1f} (primo passo atteso "
          f"{g['primo_passo_atteso']:.4f}, voluto {PASSO_VOLUTO})")

    def monitor(theta):
        return float(np.mean([obj_mon(theta, s) for s in semi_mon]))

    print(f"  ottimizzazione: {a.iterazioni} iterazioni, monitoraggio ogni "
          f"{OGNI}, semi ott {semi_ott} mon {semi_mon}")
    t1 = time.time()
    res = calib.spsa(obj, len(ids), semi_ott, a=g["a"], c=C_PERTURBAZIONE,
                     massimo=a.iterazioni, monitoraggio=monitor, ogni=OGNI,
                     pazienza=PAZIENZA, miglioramento_minimo=MIGLIORAMENTO_MINIMO,
                     rng=np.random.default_rng(a.seme))
    costo = time.time() - t1
    print(f"  {res['iterazioni']} iterazioni, {obj.valutazioni} valutazioni "
          f"di ottimizzazione + {obj_mon.valutazioni} di monitoraggio, "
          f"{costo:.1f} s. Arresto: {res['motivo_arresto']}")
    print(f"  monitoraggio migliore {res['L_migliore']:.6f} "
          f"all'iterazione {res['iterazione_migliore']}, "
          f"||theta|| {np.linalg.norm(res['theta']):.4f}")

    # --- verifica appaiata, semi separati ---------------------------------
    obj_v = Obiettivo(cal, rose, mp, m_part, m_ev, m_voto, struttura, fasce_sv,
                      ids, b_obiettivo, a.sims_verifica, a.lam)
    zero = np.zeros(len(ids))
    grezzo = np.array([bers.per_giocatore.get(p, np.nan) for p in ids])
    obiet = np.array([b_obiettivo[p] for p in ids])
    oss = (P[(P.stagione == a.stagione)]
           .assign(v=lambda d: (d.stato_voto == "con_voto").astype(float))
           .groupby("master_id")["v"].mean())
    osservato = np.array([oss.get(p, np.nan) for p in ids])

    righe_rep = []
    for s in semi_ver:
        for nome, th in (("C1", zero), ("C2", res["theta"])):
            pv = obj_v.presenze_simulate(th, s)
            righe_rep.append(pd.DataFrame({
                "braccio": nome, "seme": s, "master_id": ids,
                "p_voto": pv, "bersaglio_grezzo": grezzo,
                "bersaglio_obiettivo": obiet,
                "osservato_riferimento": osservato}))
    rep = pd.concat(righe_rep, ignore_index=True)
    corsa.scrivi_tabella(f"c2_repliche_{a.stagione}.parquet", rep)

    def mae(sub, col):
        return float((sub.p_voto - sub[col]).abs().mean())

    appaiato = {}
    for et, col in (("grezzo", "bersaglio_grezzo"),
                    ("obiettivo", "bersaglio_obiettivo"),
                    ("osservato", "osservato_riferimento")):
        per_seme = {}
        for s in semi_ver:
            c1 = mae(rep[(rep.braccio == "C1") & (rep.seme == s)], col)
            c2 = mae(rep[(rep.braccio == "C2") & (rep.seme == s)], col)
            per_seme[s] = {"C1": c1, "C2": c2, "d": c2 - c1}
        d = np.array([v["d"] for v in per_seme.values()])
        appaiato[et] = {
            "per_seme": per_seme,
            "mae_C1": float(np.mean([v["C1"] for v in per_seme.values()])),
            "mae_C2": float(np.mean([v["C2"] for v in per_seme.values()])),
            "differenza_media": float(np.mean(d)),
            "es_differenze": (float(np.std(d, ddof=1) / np.sqrt(len(d)))
                              if len(d) > 1 else float("nan")),
            "repliche": len(d)}

    dettaglio = pd.DataFrame({
        "master_id": ids,
        "squadra": [squadra.get(p) for p in ids],
        "ruolo": [ruolo.get(p) for p in ids],
        "bersaglio_grezzo": grezzo, "bersaglio_obiettivo": obiet,
        "osservato_riferimento": osservato, "theta": res["theta"],
        "p_voto_C1": rep[rep.braccio == "C1"].groupby("master_id")["p_voto"]
                        .mean().reindex(ids).to_numpy(),
        "p_voto_C2": rep[rep.braccio == "C2"].groupby("master_id")["p_voto"]
                        .mean().reindex(ids).to_numpy()})
    corsa.scrivi_tabella(f"c2_dettaglio_{a.stagione}.csv", dettaglio)
    corsa.scrivi_tabella(f"c2_storia_{a.stagione}.csv", pd.DataFrame(res["storia"]))
    corsa.scrivi_json(f"c2_pilota_{a.stagione}.json", {
        "esecuzione": corsa.identificativo, "piano": piano,
        "squadre": scelte, "criterio_squadre": criterio, "parametri": len(ids),
        "somme_per_ruolo": somme,
        "selezione": per_sq.sort_values("somma_portieri", ascending=False)
                          .head(8).to_dict("records"),
        # tutte le celle: il piano dice «cella per cella», e troncare a 60 su
        # 80 perdeva sistematicamente le ultime squadre in ordine alfabetico
        "bersaglio": diag_b,
        "collegamento": {"theta_di_prova": 3.0,
                         "scarto_massimo_presenza": scarto_rilevabile},
        "guadagno": {k: v for k, v in g.items() if k != "grandezze"},
        "ottimizzazione": {
            "iterazioni": res["iterazioni"],
            "motivo_arresto": res["motivo_arresto"],
            "L_migliore": res["L_migliore"],
            "iterazione_migliore": res["iterazione_migliore"],
            "norma_theta": float(np.linalg.norm(res["theta"])),
            "valutazioni_ottimizzazione": obj.valutazioni,
            "valutazioni_monitoraggio": obj_mon.valutazioni,
            "secondi": round(costo, 1),
            "secondi_per_valutazione": round(
                obj.secondi / max(obj.valutazioni, 1), 3)},
        "semi": {"ottimizzazione": semi_ott, "monitoraggio": semi_mon,
                 "verifica": semi_ver},
        "confronto_appaiato": appaiato,
        "nota": ("`osservato_riferimento` viene dalla stagione valutata ed e' "
                 "DIAGNOSTICO: non entra nell'obiettivo, nel bersaglio ne' "
                 "nella scelta delle squadre. Il confronto appaiato usa "
                 "d_r = MAE_C2,r - MAE_C1,r sugli stessi semi.")})
    corsa.registra()

    print("\n-- confronto appaiato sui semi di verifica")
    print(f"{'contro':<12}{'MAE C1':>10}{'MAE C2':>10}{'d medio':>12}{'es(d)':>10}")
    for et, v in appaiato.items():
        print(f"  {et:<10}{v['mae_C1']:>10.4f}{v['mae_C2']:>10.4f}"
              f"{v['differenza_media']:>12.5f}{v['es_differenze']:>10.5f}")
    print("\n  d negativo = C2 meglio di C1. Due medie separate che "
          "differiscono meno dei rispettivi errori non dimostrano equivalenza:\n"
          "  conta l'errore standard delle DIFFERENZE appaiate.")
    print(f"\n  scritto in {corsa.cartella}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
