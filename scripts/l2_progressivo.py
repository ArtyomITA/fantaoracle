"""Refit a origini mobili contro fit congelato: che cosa misura, e che cosa no.

## L'esperimento, dichiarato

**Origine della decisione.** Una lista di giornate. L'origine `k` è datata al
primo incontro di quella giornata: prima di quell'istante le partite della
giornata `k` non sono giocate.

**Informazione disponibile a quell'origine.** Le righe del panel il cui evento
è anteriore alla data dell'origine, selezionate da `righe_ammesse`.

Attenzione, perché avevo scritto che il filtro stava «in un solo punto» e
**non è vero**: `adatta` passa `as_of` anche a
`cfg.costruisci_modello_partita` e a `cfg.partite_di_addestramento`, che
filtrano un'altra tabella (`l2_partite`, sulla colonna `data_evento`) con due
condizioni in più — `stato_partita != da_giocare` e gol non nulli — e lo usano
anche per la stagione del taglio e per i pesi di decadimento. Sono **tre** punti
in cui il tempo entra, non uno. Sui dati di oggi i criteri concordano (zero
partite scartate in più dalle condizioni aggiuntive), ma è un fatto sui dati,
non una proprietà garantita dal disegno.

**Che cosa è congelato e che cosa è riadattato.** Il braccio `congelato` adatta
una volta sola, alla prima origine, e con quel fit valuta tutta la stagione. Il
braccio `refit` riadatta a ogni origine e valuta la finestra che va da
quell'origine alla successiva. Cambia **un solo fattore**: l'insieme di righe
ammesse al fit. Universo, rose, seme e numero di scenari restano gli stessi.

**Partite future valutate.** Ogni osservazione porta l'origine da cui è stata
prevista, la data della partita e l'orizzonte in giorni. Nessuna osservazione è
valutata da un'origine posteriore alla sua partita — ma questo **segue dalla
costruzione**, non da un controllo che possa fallire: `assegna_finestre` mette
la riga nella finestra `k` solo se la sua data è ≥ `bordi[k]`, e l'origine
della riga è proprio `bordi[k]`. La guardia nel codice è un'asserzione di
coerenza interna contro modifiche future, non una verifica passata.

**Rinvii.** Le finestre sono definite per **data effettiva della partita**, non
per numero di giornata. Nel 2024-25 cinque partite sono state giocate oltre
sette giorni dopo la mediana della loro giornata — una della giornata 9 giocata
il 27 febbraio. Con finestre per giornata quelle partite venivano valutate da
un'origine che non poteva ancora conoscerle.

Il conteggio che lo script stampa («partite fuori dalla finestra prevalente
della loro giornata») è una cosa diversa e **dipende dalle origini scelte**: 5
con `--origini 1,20`, 2 con le origini predefinite. Non è una proprietà della
stagione.

**Pesi.** Le finestre hanno lunghezze diverse, e una finestra di tre giornate
non deve pesare quanto una di sette per un effetto del campionamento. A
garantirlo è il **campionamento proporzionale** alle celle disponibili, non una
ponderazione a valle: dentro una finestra il peso è costante per costruzione,
quindi una media pesata coinciderebbe cifra per cifra con quella semplice. Il
peso resta in tabella perché il campione pooled sia interpretabile, non perché
entri nella stima.

## Che cosa questo esperimento NON è

**Non è una previsione operativa progressiva.** `generatore.genera` inizializza
gli stati delle catene e li evolve lungo tutto il calendario: alla seconda
origine il passato viene **risimulato con il nuovo fit**, non condizionato allo
stato osservato. Il confronto è quindi fra due **refit incondizionati**, e i
bracci si chiamano così. Condizionare le catene sullo stato osservabile
richiede un meccanismo che oggi non esiste: registrato come proposta, non
implementato qui.

**Non è il braccio C1.** Il modello di partecipazione è stimato senza bersaglio
esterno delle presenze, quindi il meccanismo è quello di `C0`. Per un `C1`
progressivo servirebbero previsioni delle presenze disponibili a ciascuna
origine; ne esiste una sola, costruita a una sola data. La dipendenza è
registrata, non aggirata riusando dati successivi.

**La vista del panel non è ricostruita per origine.** Le colonne derivate
(appartenenza, eleggibilità) vengono dal panel costruito al suo cutoff. Lo
script **misura** quante righe ammesse al fit portano
`confidenza_fit == "inferenza"`, cioè un bordo esteso senza prova, e lo scrive
nel rapporto: è la parte di anticipazione che questo disegno non elimina.
"""
from __future__ import annotations

import argparse
import datetime
import importlib.util
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from fantabot.tabellino import configurazione as cfg          # noqa: E402
from fantabot.tabellino import eventi as ev                   # noqa: E402
from fantabot.tabellino import generatore as gen              # noqa: E402
from fantabot.tabellino import partecipazione as pa           # noqa: E402
from fantabot.tabellino import voto as vt                     # noqa: E402
from fantabot.tabellino import contratto                      # noqa: E402
from fantabot.tabellino import inferenza                      # noqa: E402
from fantabot.tabellino import esecuzione as esec             # noqa: E402

PROC = ROOT / "data" / "processed"
OUT = ROOT / "data" / "l2"
GIORNATE = 38
STAGIONI_PANEL = ["2021-22", "2022-23", "2023-24", "2024-25", "2025-26"]

_spec = importlib.util.spec_from_file_location(
    "l2_banco_confronto", ROOT / "scripts" / "l2_banco_confronto.py")
banco = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(banco)


# --------------------------------------------------------------------------
# il contratto temporale, in un punto solo
# --------------------------------------------------------------------------

def righe_ammesse(P: pd.DataFrame, as_of) -> pd.DataFrame:
    """Le righe del panel che una decisione presa a `as_of` può guardare.

    Il criterio è la **data dell'evento**: una partita giocata dopo `as_of` non
    è disponibile, anche se appartiene a una giornata anteriore — è il caso dei
    rinvii.

    NON è l'unico punto in cui il tempo entra. `adatta` passa `as_of` anche a
    `cfg.costruisci_modello_partita` e a `cfg.partite_di_addestramento`, che
    filtrano `l2_partite` su `data_evento` con condizioni proprie. Questa
    funzione governa il **panel**, non l'intera catena.

    LIMITE, misurato e non risolto: le colonne derivate del panel
    (appartenenza, eleggibilità) vengono dal panel costruito al suo cutoff, non
    ricostruite a `as_of`. `diagnostica_ammesse` conta quante di queste righe
    portano un bordo esteso senza prova.
    """
    d = P["data"]
    if not pd.api.types.is_datetime64_any_dtype(d):
        d = pd.to_datetime(d)
    return P[d < pd.Timestamp(as_of)]


def diagnostica_ammesse(righe: pd.DataFrame, as_of: str) -> dict:
    """Quanto di anticipatorio resta nelle righe ammesse."""
    d = {"as_of": as_of, "righe": int(len(righe))}
    if "confidenza_fit" in righe.columns:
        c = righe["confidenza_fit"]
        d["bordo_inferenza"] = int((c == "inferenza").sum())
        d["confidenza_assente"] = int(c.isna().sum())
    if "stato_voto" in righe.columns:
        d["con_voto"] = int((righe["stato_voto"] == "con_voto").sum())
    if "id_partita" in righe.columns:
        d["partite"] = int(righe["id_partita"].nunique())
    return d


def date_origini(cal: pd.DataFrame, giornate) -> dict:
    """Per ogni origine, la data del primo incontro di quella giornata."""
    fuori = {}
    for g in giornate:
        sub = cal[cal.giornata == g]
        if sub.empty:
            raise ValueError(f"giornata {g} assente dal calendario")
        fuori[g] = pd.Timestamp(sub.data.min())
    return fuori


def data_per_cella(P: pd.DataFrame, stagione: str, giocatori, ix: dict):
    """Data effettiva e identificativo della partita per ogni (giornata, giocatore).

    Serve a due cose insieme: assegnare la riga alla finestra giusta anche
    quando la partita è stata rinviata, e legare l'indice dell'array
    all'identificativo della partita, così che il grappolo non sia dedotto
    dalla posizione.
    """
    DATA = np.full((GIORNATE, len(giocatori)), np.datetime64("NaT"),
                   dtype="datetime64[ns]")
    PART = np.empty((GIORNATE, len(giocatori)), dtype=object)
    sub = P[P.stagione == stagione]
    for r in sub.itertuples(index=False):
        j = ix.get(r.master_id)
        g = int(r.giornata) - 1
        if j is None or not (0 <= g < GIORNATE):
            continue
        DATA[g, j] = np.datetime64(pd.Timestamp(r.data))
        idp = getattr(r, "id_partita", None)
        PART[g, j] = (str(idp) if idp is not None and not pd.isna(idp)
                      else None)
    for g in range(GIORNATE):
        for j in range(len(giocatori)):
            if PART[g, j] is None:
                # niente partita per quella coppia: grappolo a se', e la cella
                # non e' assegnabile a nessuna finestra per data
                PART[g, j] = f"_sola_{g}_{j}"
    return DATA, PART


def assegna_finestre(DATA: np.ndarray, bordi) -> np.ndarray:
    """Indice di finestra per ogni cella, dalla data effettiva della partita.

    Le celle senza data restano a −1 e non vengono valutate: un dato mancante
    non è un'assenza, e non va messo in una finestra a caso.
    """
    fuori = np.full(DATA.shape, -1, dtype=int)
    for k in range(len(bordi) - 1):
        dentro = ((DATA >= np.datetime64(bordi[k]))
                  & (DATA < np.datetime64(bordi[k + 1])))
        fuori[dentro] = k
    return fuori


# --------------------------------------------------------------------------
# fit e generazione
# --------------------------------------------------------------------------

def adatta(P: pd.DataFrame, part: pd.DataFrame, cal: pd.DataFrame,
           as_of, stagione: str, rose_liste, ruolo, squadra,
           seme: int) -> dict:
    """Tutti i modelli, adattati alle sole righe ammesse a `as_of`."""
    as_of = str(pd.Timestamp(as_of).date())
    Ppre = righe_ammesse(P, as_of)
    mp, conf, impronta = cfg.costruisci_modello_partita(
        part, as_of, squadre=None, stagione_bersaglio=stagione,
        con_incertezza=True,
        percorsi_ingresso=[str(PROC / "l2_partite.parquet")],
        etichetta=f"progressivo {stagione} as_of {as_of}")
    m_part = pa.stima(Ppre)
    m_ev = ev.stima(Ppre)
    m_voto = vt.stima(Ppre, "individuale")
    m_part.ruolo.update(ruolo)
    m_ev.ruolo.update(ruolo)
    f_ev = ROOT / "data/raw/transfermarkt/_download/game_events.csv.gz"
    storico, _ = cfg.partite_di_addestramento(part, as_of)
    id_st = set(pd.to_numeric(storico.game_id, errors="coerce")
                .dropna().astype(int))
    if f_ev.exists() and id_st:
        m_ev.minuti_gol = ev.minuti_gol_da_eventi(f_ev, id_st)
    struttura = vt.struttura_dipendenza(Ppre, m_voto)
    fasce_sv = vt.stima_senza_voto(Ppre)
    tr = Ppre[Ppre.stato_voto == "con_voto"].copy()
    tr["ruolo"] = tr["ruolo"].astype(str).str.upper()
    bers = {}
    for _, sub in tr.groupby("stagione"):
        for k, v in vt.correlazioni_osservate(sub, "voto").items():
            bers.setdefault(k, []).append(v)
    bers = {k: float(np.nanmean(v)) for k, v in bers.items()}
    struttura = gen.calibra_dipendenza(struttura, bers, cal, rose_liste, mp,
                                       m_part, m_ev, m_voto, fasce_sv, seme,
                                       ruolo, squadra)
    return {"mp": mp, "m_part": m_part, "m_ev": m_ev, "m_voto": m_voto,
            "struttura": struttura, "fasce_sv": fasce_sv,
            "impronta": impronta[:12],
            "diagnostica": diagnostica_ammesse(Ppre, as_of),
            "partite_addestramento": int(len(storico)),
            "xi": conf.iperparametri["xi"]}


def genera(modelli: dict, cal, rose_liste, giocatori, sims: int, seme: int
           ) -> dict:
    """Il cubo a un dato adattamento e a un dato seme, sull'universo condiviso."""
    c = gen.genera(cal, rose_liste, modelli["mp"], modelli["m_part"],
                   modelli["m_ev"], modelli["m_voto"], n_sims=sims, seme=seme,
                   dipendenza=modelli["struttura"],
                   fasce_sv=modelli["fasce_sv"], verifica=True)
    ixc = {pid: i for i, pid in enumerate(c.giocatori)}
    ordine = [ixc.get(pid) for pid in giocatori]

    def riordina(A):
        B = np.zeros((sims, GIORNATE, len(giocatori)), dtype=A.dtype)
        for j, k in enumerate(ordine):
            if k is not None:
                B[:, :len(c.giornate), j] = A[:, :, k]
        return B

    return {"fantavoto": riordina(c.fantavoto), "gioca": riordina(c.gioca),
            "problemi": c.diagnostica["n_problemi_coerenza"]}


def punteggi(G: dict, scelte, VER, GIO, sims: int) -> dict:
    """CRPS e Brier per osservazione, empirici ed equi, più la previsione."""
    fv, gi = G["fantavoto"], G["gioca"]
    crps, disp, media = [], [], []
    for g, j in scelte:
        camp = np.where(gi[:, g, j], fv[:, g, j], 0.0)
        y = VER[g, j] if GIO[g, j] else 0.0
        c_emp, d_emp = banco.crps_e_dispersione(camp, y)
        crps.append(c_emp)
        disp.append(d_emp)
        media.append(float(camp.mean()))
    crps = np.asarray(crps, dtype=float)
    disp = np.asarray(disp, dtype=float)
    p_sim = gi.mean(0)
    p_righe = np.array([p_sim[g, j] for g, j in scelte])
    y_righe = np.array([float(GIO[g, j]) for g, j in scelte])
    return {"crps": crps,
            "crps_equo": inferenza.crps_equo(crps, disp, sims),
            "crps_dispersione": disp,
            "brier": (p_righe - y_righe) ** 2,
            "brier_equo": inferenza.brier_equo(p_righe, y_righe, sims),
            # le previsioni individuali si conservano: senza, rifare una
            # metrica costa una rigenerazione
            "p_voto_prevista": p_righe,
            "fantavoto_previsto": np.asarray(media, dtype=float)}


CHIAVI = ("crps", "crps_equo", "brier", "brier_equo", "crps_dispersione",
          "p_voto_prevista", "fantavoto_previsto")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("stagione", nargs="?", default="2024-25")
    ap.add_argument("--sims", type=int, default=30)
    ap.add_argument("--semi", type=int, default=4)
    ap.add_argument("--seme", type=int, default=20260909)
    ap.add_argument("--origini", default="1,8,15,22,29,36")
    ap.add_argument("--righe", type=int, default=5400,
                    help="righe valutate in totale, ripartite fra le finestre "
                         "in proporzione alle celle disponibili")
    ap.add_argument("--rose-da", choices=["listone", "squadra"],
                    default="listone")
    ap.add_argument("--data-fit", default=None)
    ap.add_argument("--prova", action="store_true",
                    help="prova esplorativa: radice data/l2/prove/, separata "
                         "da quella dei risultati pubblicabili")
    ap.add_argument("--destinazione", default=None)
    ap.add_argument("--riprendi", action="store_true")
    ap.add_argument("--istante", default=None)
    a = ap.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)

    istante = a.istante or datetime.datetime.now().strftime("%Y%m%dT%H%M%S")
    configurazione = {
        "script": "l2_progressivo",
        "stagione": a.stagione, "sims": a.sims, "seme": a.seme,
        "semi": a.semi, "origini": a.origini, "righe": a.righe,
        "rose_da": a.rose_da, "data_fit": a.data_fit,
        "impronte_ingressi": {
            n: esec.impronta_file(PROC / n)
            for n in (f"players_{a.stagione}.parquet", "l2_partite.parquet")},
        "impronta_script": esec.impronta_file(__file__),
    }
    corsa = esec.apri(OUT, a.stagione, configurazione, istante=istante,
                      prova=a.prova, riprendi=a.riprendi,
                      destinazione=a.destinazione)
    print(f"  destinazione: {corsa.cartella} (id {corsa.identificativo})")

    P, _ = contratto.carica_panel_multi(
        PROC, STAGIONI_PANEL, data_fit=a.data_fit,
        esigi_vista_al_fit=a.data_fit is not None)
    P["data"] = pd.to_datetime(P["data"])
    part = pd.read_parquet(PROC / "l2_partite.parquet")
    part["data"] = pd.to_datetime(part["data"])
    cal = part[part.stagione == a.stagione].copy()
    rose_liste, ruolo, squadra, diag_universo = contratto.costruisci_universo(
        PROC, a.stagione, rose_da=a.rose_da)
    giocatori = sorted(ruolo)
    ix = {pid: i for i, pid in enumerate(giocatori)}

    origini = [int(x) for x in a.origini.split(",")]
    if origini[0] != 1:
        raise SystemExit("la prima origine deve essere la giornata 1")
    date = date_origini(cal, origini)
    print(f"stagione {a.stagione} | {len(giocatori)} giocatori | "
          f"{a.sims} scenari x {a.semi} semi")
    print("origini: " + ", ".join(f"g{g} ({date[g].date()})" for g in origini))

    # --- verita' ----------------------------------------------------------
    oss = P[(P.stagione == a.stagione) & (P.stato_voto == "con_voto")]
    VER = np.zeros((GIORNATE, len(giocatori)))
    GIO = np.zeros((GIORNATE, len(giocatori)), dtype=bool)
    for r in oss.itertuples(index=False):
        j = ix.get(r.master_id)
        g = int(r.giornata) - 1
        if j is not None and 0 <= g < GIORNATE:
            VER[g, j] = float(r.fantavoto)
            GIO[g, j] = True

    # --- finestre per DATA, non per giornata ------------------------------
    DATA, PART = data_per_cella(P, a.stagione, giocatori, ix)
    bordi = [date[g] for g in origini] + [pd.Timestamp("2100-01-01")]
    finestra_cella = assegna_finestre(DATA, bordi)

    # quante partite cadono in una finestra diversa da quella prevalente della
    # loro giornata: e' la misura dei rinvii che il filtro per giornata sbagliava
    prevalente, fuori_posto, viste = {}, 0, set()
    for g in range(GIORNATE):
        v = finestra_cella[g][finestra_cella[g] >= 0]
        if v.size:
            prevalente[g] = int(np.bincount(v).argmax())
    for g in range(GIORNATE):
        for j in range(len(giocatori)):
            k = finestra_cella[g, j]
            idp = PART[g, j]
            if k < 0 or idp.startswith("_sola_") or idp in viste:
                continue
            viste.add(idp)
            if k != prevalente.get(g, k):
                fuori_posto += 1
    print(f"  finestre per data: {fuori_posto} partite cadono in una finestra "
          "diversa da quella prevalente della loro giornata. Il numero dipende "
          "dalle origini scelte, non e' una proprieta' della stagione")

    # --- righe valutate, con peso esplicito -------------------------------
    rng = np.random.default_rng(a.seme)
    scelte, finestra_di, peso_di = [], [], []
    disponibili = {k: int(np.sum(finestra_cella == k))
                   for k in range(len(origini))}
    totale = sum(disponibili.values())
    for k in range(len(origini)):
        celle = np.argwhere(finestra_cella == k)
        if not len(celle):
            continue
        quota = max(2, int(round(a.righe * disponibili[k] / max(totale, 1))))
        n = min(quota, len(celle))
        sel = celle[rng.choice(len(celle), size=n, replace=False)]
        scelte.append(sel)
        finestra_di.append(np.full(n, k))
        # peso: la finestra rappresenta `disponibili[k]` celle con `n` righe
        peso_di.append(np.full(n, disponibili[k] / n))
    scelte = np.vstack(scelte)
    finestra_di = np.concatenate(finestra_di)
    peso_di = np.concatenate(peso_di)
    print("  righe per finestra: " + ", ".join(
        f"g{origini[k]}:{int(np.sum(finestra_di == k))}/{disponibili[k]}"
        for k in range(len(origini))))

    id_part = np.array([PART[g, j] for g, j in scelte], dtype=object)
    id_gioc = np.array([giocatori[j] for _, j in scelte])
    data_riga = np.array([DATA[g, j] for g, j in scelte])
    origine_riga = np.array([np.datetime64(date[origini[k]])
                             for k in finestra_di])
    orizzonte = (data_riga - origine_riga) / np.timedelta64(1, "D")
    # INVARIANTE, non un controllo che possa fallire: `assegna_finestre`
    # assegna la finestra `k` solo se `data >= bordi[k]`, e l'origine della
    # riga E' `bordi[k]`. L'orizzonte non negativo segue dalla costruzione.
    # Resta come guardia contro una modifica futura dell'assegnazione, e va
    # letta cosi': non e' una verifica passata, e' un'asserzione di coerenza
    # interna. Chi volesse una prova vera deve alterare `assegna_finestre`.
    if float(np.nanmin(orizzonte)) < 0:
        raise SystemExit(
            "orizzonte negativo: `assegna_finestre` e `origine_riga` non sono "
            "piu' coerenti fra loro")
    print(f"  orizzonte: da {np.nanmin(orizzonte):.0f} a "
          f"{np.nanmax(orizzonte):.0f} giorni")

    # --- adattamenti, uno per origine -------------------------------------
    modelli, diag_fit = {}, {}
    for g in origini:
        t = time.time()
        modelli[g] = adatta(P, part, cal, date[g], a.stagione, rose_liste,
                            ruolo, squadra, a.seme)
        diag_fit[g] = {"impronta": modelli[g]["impronta"],
                       "partite_addestramento":
                           modelli[g]["partite_addestramento"],
                       "xi": modelli[g]["xi"], **modelli[g]["diagnostica"]}
        print(f"  fit g{g} ({date[g].date()}): "
              f"{diag_fit[g]['righe']} righe ammesse, "
              f"{diag_fit[g].get('bordo_inferenza', 0)} con bordo di "
              f"inferenza, {time.time() - t:.1f} s")

    # --- punteggi ---------------------------------------------------------
    somma = {"congelato": {}, "refit": {}}
    per_seme = {"congelato": {}, "refit": {}}
    semi = [a.seme + 100_003 * r for r in range(max(1, a.semi))]
    for r, seme_r in enumerate(semi):
        t = time.time()
        G_cong = genera(modelli[origini[0]], cal, rose_liste, giocatori,
                        a.sims, seme_r)
        p_cong = punteggi(G_cong, scelte, VER, GIO, a.sims)
        p_prog = {k: np.empty_like(p_cong[k]) for k in CHIAVI}
        for k, g in enumerate(origini):
            # ANCHE alla prima origine si rigenera. Riusare `G_cong` rendeva il
            # controllo della prima finestra un confronto fra un oggetto e se
            # stesso: non poteva fallire, e infatti non ha mai fallito.
            G_k = genera(modelli[g], cal, rose_liste, giocatori, a.sims,
                         seme_r)
            sel = finestra_di == k
            p_k = punteggi(G_k, scelte[sel], VER, GIO, a.sims)
            for chiave in CHIAVI:
                p_prog[chiave][sel] = p_k[chiave]
        prima = finestra_di == 0
        scarto = float(np.max(np.abs(p_cong["crps"][prima]
                                     - p_prog["crps"][prima])))
        if scarto > 0:
            raise SystemExit(
                f"seme {seme_r}: la prima finestra non coincide fra i due "
                f"bracci (scarto {scarto:.3e}). Stesso fit e stesso seme "
                "devono dare la stessa previsione.")
        for nome, p in (("congelato", p_cong), ("refit", p_prog)):
            for chiave in CHIAVI:
                somma[nome].setdefault(chiave, np.zeros_like(p[chiave]))
                somma[nome][chiave] += p[chiave]
                per_seme[nome].setdefault(chiave, []).append(
                    float(np.nanmean(p[chiave])))
        print(f"  seme {seme_r}: {time.time() - t:.1f} s")

    medie = {nome: {k: v / len(semi) for k, v in d.items()}
             for nome, d in somma.items()}

    # --- osservazioni conservate ------------------------------------------
    oss_df = pd.DataFrame({
        "master_id": id_gioc, "id_partita": id_part,
        "data_partita": data_riga, "origine": origine_riga,
        "finestra": [origini[k] for k in finestra_di],
        "orizzonte_giorni": orizzonte, "peso": peso_di,
        "ruolo": [ruolo.get(p) for p in id_gioc],
        "esito_vero": [float(VER[g, j]) if GIO[g, j] else 0.0
                       for g, j in scelte],
        "ha_giocato": [bool(GIO[g, j]) for g, j in scelte],
    })
    for nome in ("congelato", "refit"):
        for k in CHIAVI:
            oss_df[f"{nome}__{k}"] = medie[nome][k]
    corsa.scrivi_tabella(f"progressivo_osservazioni_{a.stagione}.parquet",
                         oss_df)

    # --- verdetto ----------------------------------------------------------
    righe = []
    for misura in ("crps", "brier"):
        for punteggio, chiave in (("empirico", misura),
                                  ("equo", f"{misura}_equo")):
            d = medie["refit"][chiave] - medie["congelato"][chiave]
            buoni = np.isfinite(d)
            iv = inferenza.intervallo_two_way(d[buoni], id_part[buoni],
                                              id_gioc[buoni])
            mc = (inferenza.rumore_monte_carlo(
                [x - y for x, y in zip(per_seme["refit"][chiave],
                                       per_seme["congelato"][chiave])],
                es_campionario=iv.errore_standard)
                if len(semi) > 1 else None)
            es = iv.diagnostica["errori_standard"]
            righe.append({
                "misura": misura, "punteggio": punteggio,
                "differenza": round(iv.differenza, 6),
                "ic_basso": round(iv.ic_basso, 6),
                "ic_alto": round(iv.ic_alto, 6),
                "es_two_way": round(iv.errore_standard, 6),
                "es_righe_indipendenti": round(es["righe_indipendenti"], 6),
                "n": iv.n, "partite": iv.grappoli_1,
                "giocatori": iv.grappoli_2,
                "semi": (mc["repliche"] if mc else 1),
                "scenari": a.sims,
                "es_monte_carlo": (round(mc["es_mc"], 6)
                                   if mc else float("nan")),
                "rumore_sotto_soglia_prospettica": (
                    mc.get("soddisfatto_prospettico") if mc else None),
                "quota_varianza_monte_carlo": (
                    round(mc["quota_varianza_aggiunta"], 5)
                    if mc and "quota_varianza_aggiunta" in mc
                    else float("nan")),
                "esecuzione": corsa.identificativo,
                "esito": inferenza.esito_confronto(
                    iv, mc, {"nulla": "differenza non rilevabile",
                             "negativa": "refit migliore",
                             "positiva": "refit peggiore"})})

    per_finestra = []
    for k, g in enumerate(origini):
        sel = finestra_di == k
        d = (medie["refit"]["crps_equo"][sel]
             - medie["congelato"]["crps_equo"][sel])
        per_finestra.append({
            "origine": g, "data": str(date[g].date()),
            "n": int(sel.sum()), "celle": disponibili[k],
            "peso_medio": round(float(np.mean(peso_di[sel])), 3),
            "differenza_crps_equo": round(float(np.mean(d)), 6),
            # Dentro una finestra il peso e' COSTANTE, perche' il
            # campionamento e' proporzionale: una media pesata coinciderebbe
            # cifra per cifra con quella semplice. La colonna c'era e non
            # poteva dire niente di diverso. Quello che i pesi fanno davvero e'
            # rendere il campione pooled gia' rappresentativo della
            # popolazione, ed e' il campionamento a farlo, non una ponderazione
            # a valle.
            "peso_costante_nella_finestra": bool(
                np.allclose(peso_di[sel], peso_di[sel][0]))})

    t1 = pd.DataFrame(righe)
    t2 = pd.DataFrame(per_finestra)
    corsa.scrivi_tabella(f"progressivo_verdetto_{a.stagione}.csv", t1)
    corsa.scrivi_tabella(f"progressivo_finestre_{a.stagione}.csv", t2)
    corsa.scrivi_json(f"progressivo_esperimento_{a.stagione}.json", {
        "esecuzione": corsa.identificativo,
        "origini": {str(k): str(v.date()) for k, v in date.items()},
        "adattamenti": {str(k): v for k, v in diag_fit.items()},
        "semi": semi, "scenari": a.sims,
        "righe_valutate": int(len(scelte)),
        "partite_fuori_dalla_finestra_della_giornata": fuori_posto,
        "universo": diag_universo,
        "bracci": {
            "congelato": "fit alla prima origine, valuta tutta la stagione",
            "refit": "riadatta a ogni origine, valuta la finestra seguente"},
        "limiti": [
            "refit INCONDIZIONATO: generatore.genera risimula il passato con "
            "il nuovo fit invece di condizionare le catene sullo stato "
            "osservato. Non e' una previsione operativa progressiva.",
            "meccanismo C0: partecipazione stimata senza bersaglio esterno "
            "delle presenze. Un C1 progressivo richiederebbe previsioni delle "
            "presenze disponibili a ciascuna origine, che non esistono.",
            "vista del panel non ricostruita per origine: le colonne derivate "
            "vengono dal panel al suo cutoff. Le righe con bordo di inferenza "
            "sono contate per origine in `adattamenti`.",
            "universo e appartenenze costruiti una volta sola, non per "
            "origine: i trasferimenti infrastagionali non sono riflessi."]})
    corsa.registra()

    print()
    print(t1.to_string(index=False))
    print()
    print(t2.to_string(index=False))
    print(f"\nscritto in {corsa.cartella}")
    print("nota: la prima finestra vale zero per costruzione ed e' il "
          "controllo. Una differenza negativa e' a favore del refit. I bracci "
          "sono due REFIT INCONDIZIONATI: vedi `limiti` nel json.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
