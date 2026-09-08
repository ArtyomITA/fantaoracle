"""Banco del modello di partita: candidati contro baseline, fuori campione.

Sostituisce le due prove d'indagine (`scripts/indagine/l2_modello_partita.py` e
`l2_modello_partita2.py`), che avevano tre difetti dimostrati:

 1. **niente intercetta**: attacco e difesa a somma zero senza livello generale
    costringevano i gol in trasferta vicino a 1;
 2. **niente Dixon-Coles nel confronto finale**: il secondo script stimava un
    Poisson penalizzato, ma il report lo descriveva come Dixon-Coles;
 3. **metrica cieca**: il Brier sulla porta inviolata e' una marginale, e la
    correzione di Dixon-Coles lascia le marginali intatte. Quel numero non puo'
    distinguere i due modelli, per costruzione.

Qui i candidati si confrontano con metriche che vedono quello che ciascuno
cambia davvero, e la scelta degli iperparametri avviene su dati precedenti al
periodo di prova.

## Il candidato F non si costruisce piu' qui

Dal 7 settembre 2026 il candidato vincente F **non e' piu' costruito da questo
script**: viene chiesto a `fantabot.tabellino.configurazione`, che e' la sola
procedura autorizzata a costruire un modello di partita. Prima, la scelta degli
iperparametri, i prior dagli xG e i prior per le neopromosse vivevano solo qui
dentro, e nessun altro file li importava: il cubo
(`scripts/l2_genera_cubo.py`) e il banco di confronto
(`scripts/l2_banco_confronto.py`) scrivevano a mano `xi = 0,0015` e
`lam_pen = 2,0` senza prior, e generavano quindi un modello diverso da quello
che questo banco dichiarava vincente. Lo scarto misurato sul calendario 2026-27
era di 0,218 gol di intensita' media (16,6 %), fino a 1,514
(`data/l3/audit/simulazione/RAPPORTO.md`, sezione 1).

Gli iperparametri delle altre colonne (C, D, E, G) sono quelli che la procedura
ha scelto: cosi' il confronto fra i candidati resta a parita' di
iperparametri, com'era prima.

Le funzioni `prior_da_xg`, `prior_neopromosse` e `scegli_iperparametri` restano
qui come sottili inoltri alla nuova sede, con la firma di prima, perche' gli
script di audit gia' scritti le importano da questo modulo e devono continuare
a produrre gli stessi numeri.

## Candidati

    A  tasso base                 stessa probabilita' per tutti
    B  media storica di squadra   frequenze osservate nel train
    C  Poisson con intercetta     forze fisse, tutto il train
    D  Poisson + decadimento      peso exp(-xi * giorni)
    E  Dixon-Coles + decadimento  D piu' la dipendenza sui punteggi bassi
    F  procedura unica            E piu' i prior da xG e neopromosse
    G  E aggiornato in stagione   rifit dopo ogni giornata gia' giocata

G non e' disponibile all'asta di inizio stagione, ma lo e' per il copilota
in stagione e per un'asta che si tiene a campionato iniziato. Viene riportato
separatamente e non concorre alla scelta pre-asta.

## Metriche

    log score congiunto   -log P(risultato esatto): vede la dipendenza
    RPS sul risultato     distanza fra cumulate di 1X2, ordinale
    Brier 1X2             somma degli scarti quadratici sulle tre classi
    Brier porta inviolata la marginale che serve al modificatore difesa
    calibrazione          scarto medio |osservato - previsto| per decile

Tutte le previsioni vengono salvate: senza predizioni conservate un risultato
non e' verificabile.

## Disciplina temporale

Il train di ogni prova contiene solo partite con data **anteriore** alla data
limite (`as_of`), non "giornata minore di". Rinvii e recuperi rendono le due
cose diverse. Gli iperparametri di ogni stagione di prova si scelgono sulla
stagione precedente, addestrando su quelle prima ancora. Il filtro e' quello di
`configurazione.partite_di_addestramento`, che usa `stato_partita` se la
colonna c'e' e `giocata` altrimenti, e in ogni caso pretende che il risultato
esista davvero.

Uso:
  python scripts/l2_banco_partita.py
  python scripts/l2_banco_partita.py --stagioni 2024-25 2025-26 --boot 2000
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
PROC = ROOT / "data" / "processed"
OUT = ROOT / "data" / "l2"

from fantabot.tabellino import configurazione as cfg          # noqa: E402
from fantabot.tabellino.partita import (                      # noqa: E402
    matrice_risultato, pesi_decadimento, stima,
)

# Le griglie vivono nella procedura unica: qui restano solo i nomi storici,
# perche' comparivano nel JSON del banco e nei rapporti gia' pubblicati.
XI = list(cfg.GRIGLIA_XI)
LAM = list(cfg.GRIGLIA_LAM_PEN)

FILE_PARTITE = PROC / "l2_partite.parquet"


# --------------------------------------------------------------------------
# inoltri alla procedura unica, con le firme di prima
# --------------------------------------------------------------------------

prior_da_xg = cfg.prior_da_xg


def prior_neopromosse(storico, squadre_test, squadre_prec, as_of=None):
    """Inoltro a `configurazione.prior_neopromosse`.

    Il parametro `as_of` era dichiarato e mai usato nella versione precedente;
    resta accettato e ignorato solo per non rompere gli script di audit che
    passano quattro argomenti."""
    return cfg.prior_neopromosse(storico, squadre_test, squadre_prec)


def scegli_iperparametri(storico, stagione_val, storico_prima, as_of_val):
    """Inoltro a `configurazione.scegli_iperparametri`, firma di prima.

    Ritorna `((xi, lam_pen), log score)`; la tabella completa della griglia,
    che la nuova funzione restituisce come terzo valore, qui viene scartata."""
    val = storico[storico.stagione == stagione_val]
    (xi, lp), punteggio, _ = cfg.scegli_iperparametri(
        storico_prima, val,
        squadre=sorted(set(storico_prima.casa) | set(val.casa)),
        as_of_val=as_of_val)
    return (xi, lp), punteggio


# --------------------------------------------------------------------------
# metriche
# --------------------------------------------------------------------------

def rps(p3: np.ndarray, esito: np.ndarray) -> np.ndarray:
    """Ranked probability score su (1, X, 2): ordinale, penalizza gli errori
    lontani piu' di quelli vicini."""
    o = np.zeros_like(p3)
    o[np.arange(len(esito)), esito] = 1.0
    cp = np.cumsum(p3, axis=1)[:, :2]
    co = np.cumsum(o, axis=1)[:, :2]
    return ((cp - co) ** 2).sum(1) / 2.0


def brier_multi(p3: np.ndarray, esito: np.ndarray) -> np.ndarray:
    o = np.zeros_like(p3)
    o[np.arange(len(esito)), esito] = 1.0
    return ((p3 - o) ** 2).sum(1)


def calibrazione(p: np.ndarray, y: np.ndarray, n_gruppi: int = 10) -> float:
    """Scarto medio pesato fra frequenza osservata e probabilita' prevista."""
    ordine = np.argsort(p)
    p, y = np.asarray(p)[ordine], np.asarray(y)[ordine]
    tagli = np.array_split(np.arange(len(p)), n_gruppi)
    err, n = 0.0, 0
    for t in tagli:
        if len(t) == 0:
            continue
        err += len(t) * abs(y[t].mean() - p[t].mean())
        n += len(t)
    return err / max(n, 1)


def esito_1x2(gc, gt) -> np.ndarray:
    return np.where(gc > gt, 0, np.where(gc == gt, 1, 2))


# --------------------------------------------------------------------------
# candidati
# --------------------------------------------------------------------------

def previsioni_da_modello(mod, te) -> dict:
    lam, mu = mod.intensita(te.casa.values, te.trasferta.values)
    n = len(te)
    p3 = np.zeros((n, 3))
    logp = np.zeros(n)
    for i in range(n):
        P = matrice_risultato(float(lam[i]), float(mu[i]), mod.rho)
        p3[i, 0] = np.tril(P, -1).sum()
        p3[i, 1] = np.trace(P)
        p3[i, 2] = np.triu(P, 1).sum()
        x = min(int(te.gol_casa.values[i]), P.shape[0] - 1)
        y = min(int(te.gol_trasferta.values[i]), P.shape[1] - 1)
        logp[i] = -np.log(max(P[x, y], 1e-12))
    return {"p1": p3[:, 0], "px": p3[:, 1], "p2": p3[:, 2],
            "log_score": logp,
            "cs_casa": np.exp(-mu), "cs_trasferta": np.exp(-lam),
            "lam_casa": lam, "lam_trasferta": mu}


def previsioni_frequenze(tr, te, per_squadra: bool) -> dict:
    """A (tasso base) e B (media storica di squadra), senza modello."""
    n = len(te)
    esiti = esito_1x2(tr.gol_casa.values, tr.gol_trasferta.values)
    base3 = np.array([(esiti == k).mean() for k in range(3)])
    cs_base = float(np.mean([(tr.gol_trasferta == 0).mean(),
                             (tr.gol_casa == 0).mean()]))
    if not per_squadra:
        p3 = np.tile(base3, (n, 1))
        cs_c = np.full(n, cs_base)
        cs_t = np.full(n, cs_base)
    else:
        cs = {}
        gf = {}
        for s in set(tr.casa) | set(tr.trasferta):
            c = tr[tr.casa == s]
            f = tr[tr.trasferta == s]
            k = len(c) + len(f)
            if k:
                cs[s] = ((c.gol_trasferta == 0).sum()
                         + (f.gol_casa == 0).sum()) / k
                gf[s] = (c.gol_casa.sum() + f.gol_trasferta.sum()) / k
        # 1X2: frequenza storica di vittoria in casa/fuori della coppia
        p3 = np.zeros((n, 3))
        for i, r in enumerate(te.itertuples(index=False)):
            fc = tr[tr.casa == r.casa]
            ft = tr[tr.trasferta == r.trasferta]
            if len(fc) and len(ft):
                v = np.array([
                    ((fc.gol_casa > fc.gol_trasferta).mean()
                     + (ft.gol_casa > ft.gol_trasferta).mean()) / 2,
                    ((fc.gol_casa == fc.gol_trasferta).mean()
                     + (ft.gol_casa == ft.gol_trasferta).mean()) / 2,
                    ((fc.gol_casa < fc.gol_trasferta).mean()
                     + (ft.gol_casa < ft.gol_trasferta).mean()) / 2])
                p3[i] = v / v.sum()
            else:
                p3[i] = base3
        cs_c = np.array([cs.get(s, cs_base) for s in te.casa])
        cs_t = np.array([cs.get(s, cs_base) for s in te.trasferta])
    # log score: senza modello congiunto si usa la sola classe 1X2, non
    # confrontabile col risultato esatto -> resta assente (NaN dichiarato)
    return {"p1": p3[:, 0], "px": p3[:, 1], "p2": p3[:, 2],
            "log_score": np.full(n, np.nan),
            "cs_casa": cs_c, "cs_trasferta": cs_t,
            "lam_casa": np.full(n, np.nan), "lam_trasferta": np.full(n, np.nan)}


def candidati(tr: pd.DataFrame, te: pd.DataFrame, as_of: str,
              xi: float, lam_pen: float, squadre, modello_f) -> dict:
    """I sei candidati pre-asta.

    `modello_f` arriva gia' costruito da `configurazione`: questo script non ha
    piu' una sua idea di che cosa sia il modello buono. C, D ed E restano qui
    perche' sono ablazioni — servono a far vedere quanto pesa ciascun pezzo — e
    usano gli stessi iperparametri che la procedura ha scelto."""
    date_tr = tr.data.values.astype("datetime64[D]")
    w_dec = pesi_decadimento(date_tr, as_of, xi)
    out = {}
    out["A tasso base"] = previsioni_frequenze(tr, te, per_squadra=False)
    out["B media storica"] = previsioni_frequenze(tr, te, per_squadra=True)
    mC = stima(tr.casa.values, tr.trasferta.values, tr.gol_casa.values,
               tr.gol_trasferta.values, squadre=squadre, lam_pen=lam_pen,
               usa_dc=False)
    out["C Poisson intercetta"] = previsioni_da_modello(mC, te)
    mD = stima(tr.casa.values, tr.trasferta.values, tr.gol_casa.values,
               tr.gol_trasferta.values, squadre=squadre, pesi=w_dec,
               lam_pen=lam_pen, usa_dc=False)
    out["D Poisson decadimento"] = previsioni_da_modello(mD, te)
    mE = stima(tr.casa.values, tr.trasferta.values, tr.gol_casa.values,
               tr.gol_trasferta.values, squadre=squadre, pesi=w_dec,
               lam_pen=lam_pen, usa_dc=True)
    out["E Dixon-Coles"] = previsioni_da_modello(mE, te)
    out["F DC + prior xG"] = previsioni_da_modello(modello_f, te)
    out["_diagnostica"] = {
        "C": mC.diagnostica, "E": mE.diagnostica, "F": modello_f.diagnostica,
        "rho_E": round(mE.rho, 4), "rho_F": round(modello_f.rho, 4),
        "vantaggio_casa_E": round(mE.casa, 4),
        "convergenza": all(m.convergenza for m in (mC, mD, mE, modello_f)),
    }
    return out


def candidato_in_stagione(tr, te, as_of, xi, lam_pen, squadre) -> dict:
    """G: rifit prima di ogni giornata, con le sole partite gia' giocate.
    Il filtro e' sulla DATA effettiva, non sulla giornata."""
    pezzi = []
    for g in sorted(te.giornata.dropna().unique()):
        gior = te[te.giornata == g]
        inizio = gior.data.min()
        passato = pd.concat([tr, te[te.data < inizio]])
        w = pesi_decadimento(passato.data.values.astype("datetime64[D]"),
                             str(np.datetime64(inizio, "D")), xi)
        m = stima(passato.casa.values, passato.trasferta.values,
                  passato.gol_casa.values, passato.gol_trasferta.values,
                  squadre=squadre, pesi=w, lam_pen=lam_pen, usa_dc=True)
        p = previsioni_da_modello(m, gior)
        p["_idx"] = gior.index.values
        pezzi.append(p)
    ordine = np.concatenate([p["_idx"] for p in pezzi])
    riordino = np.argsort(np.argsort(te.index.values))
    fuori = {}
    for k in ("p1", "px", "p2", "log_score", "cs_casa", "cs_trasferta",
              "lam_casa", "lam_trasferta"):
        v = np.concatenate([p[k] for p in pezzi])
        s = pd.Series(v, index=ordine).reindex(te.index).values
        fuori[k] = s
    return fuori


# --------------------------------------------------------------------------
# valutazione
# --------------------------------------------------------------------------

def valuta(prev: dict, te: pd.DataFrame) -> dict:
    gc = te.gol_casa.values.astype(int)
    gt = te.gol_trasferta.values.astype(int)
    es = esito_1x2(gc, gt)
    p3 = np.column_stack([prev["p1"], prev["px"], prev["p2"]])
    p3 = p3 / p3.sum(1, keepdims=True)
    cs = np.concatenate([prev["cs_casa"], prev["cs_trasferta"]])
    ycs = np.concatenate([(gt == 0).astype(float), (gc == 0).astype(float)])
    return {
        "log_score": float(np.nanmean(prev["log_score"])),
        "rps": float(np.mean(rps(p3, es))),
        "brier_1x2": float(np.mean(brier_multi(p3, es))),
        "brier_cs": float(np.mean((cs - ycs) ** 2)),
        "calib_cs": float(calibrazione(cs, ycs)),
        "n": int(len(te)),
    }


def bootstrap_diff(a: np.ndarray, b: np.ndarray, n_boot: int, seed: int) -> tuple:
    """Intervallo per la differenza appaiata media (a - b)."""
    rng = np.random.default_rng(seed)
    d = np.asarray(a, float) - np.asarray(b, float)
    d = d[~np.isnan(d)]
    if len(d) == 0:
        return float("nan"), (float("nan"), float("nan"))
    idx = rng.integers(0, len(d), (n_boot, len(d)))
    medie = d[idx].mean(1)
    return float(d.mean()), (float(np.percentile(medie, 2.5)),
                             float(np.percentile(medie, 97.5)))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--stagioni", nargs="*",
                    default=["2023-24", "2024-25", "2025-26"])
    ap.add_argument("--boot", type=int, default=2000)
    ap.add_argument("--seed", type=int, default=20260907)
    a = ap.parse_args()

    # tabella completa: il filtro temporale lo fa la procedura unica, che sa
    # leggere `stato_partita` quando c'e'. Qui si tiene la versione filtrata
    # solo per costruire le stagioni di prova, che devono avere il risultato.
    part = pd.read_parquet(FILE_PARTITE)
    part["data"] = pd.to_datetime(part["data"])
    d, _ = cfg.partite_di_addestramento(part, "2100-01-01")
    OUT.mkdir(parents=True, exist_ok=True)

    riepilogo, dettagli = [], {}
    for st in a.stagioni:
        te = d[d.stagione == st].sort_values("data").reset_index(drop=True)
        as_of = str(te.data.min().date())
        tr, filtro = cfg.partite_di_addestramento(part, as_of)
        stagioni_tr = sorted(tr.stagione.unique())
        if len(stagioni_tr) < 2:
            print(f"{st}: train troppo corto, salto")
            continue

        # UNICA costruzione del modello: iperparametri, prior e stima stanno
        # tutti dentro `costruisci_modello_partita`.
        mF, conf, impronta = cfg.costruisci_modello_partita(
            part, as_of, stagione_bersaglio=st,
            percorsi_ingresso=[FILE_PARTITE], etichetta=f"banco {st}")
        xi = conf.iperparametri["xi"]
        lp = conf.iperparametri["lam_pen"]
        squadre = list(conf.squadre)
        origine = conf.origine_iperparametri
        print(f"\n=== {st} | train {stagioni_tr[0]}..{stagioni_tr[-1]} "
              f"({len(tr)} partite) | as_of {as_of}")
        print(f"    iperparametri scelti su "
              f"{origine['stagione_di_validazione']}: xi={xi}, lam_pen={lp} "
              f"(log score di validazione "
              f"{origine['log_score_di_validazione']:.4f})")
        print(f"    impronta configurazione {impronta}")

        cand = candidati(tr, te, as_of, xi, lp, squadre, mF)
        diag = cand.pop("_diagnostica")
        cand["G in stagione (non pre-asta)"] = candidato_in_stagione(
            tr, te, as_of, xi, lp, squadre)

        righe = []
        for nome, prev in cand.items():
            m = valuta(prev, te)
            m["candidato"] = nome
            m["stagione"] = st
            m["xi"] = xi
            m["lam_pen"] = lp
            m["impronta"] = impronta if nome.startswith("F") else ""
            righe.append(m)
        rif = "B media storica"
        gc = te.gol_casa.values.astype(int)
        gt = te.gol_trasferta.values.astype(int)
        es = esito_1x2(gc, gt)
        for r in righe:
            p = cand[r["candidato"]]
            p3 = np.column_stack([p["p1"], p["px"], p["p2"]])
            p3 = p3 / p3.sum(1, keepdims=True)
            q = cand[rif]
            q3 = np.column_stack([q["p1"], q["px"], q["p2"]])
            q3 = q3 / q3.sum(1, keepdims=True)
            dm, ic = bootstrap_diff(rps(p3, es), rps(q3, es), a.boot, a.seed)
            r["rps_meno_B"] = dm
            r["rps_meno_B_ic95"] = [round(ic[0], 5), round(ic[1], 5)]
        riepilogo.extend(righe)
        dettagli[st] = {"diagnostica": diag, "xi": xi, "lam_pen": lp,
                        "as_of": as_of, "n_train": int(len(tr)),
                        "impronta_configurazione": impronta,
                        "configurazione": conf.a_dizionario(),
                        "filtro_temporale": filtro}
        # predizioni conservate
        salva = te[["stagione", "giornata", "data", "casa", "trasferta",
                    "gol_casa", "gol_trasferta"]].copy()
        for nome, prev in cand.items():
            tag = nome.split()[0]
            for k in ("p1", "px", "p2", "log_score", "cs_casa", "cs_trasferta"):
                salva[f"{tag}_{k}"] = prev[k]
        salva.to_parquet(OUT / f"previsioni_partita_{st}.parquet", index=False)

        print(f"{'candidato':32s} {'logscore':>9s} {'RPS':>8s} {'Brier1X2':>9s} "
              f"{'BrierCS':>8s} {'calibCS':>8s}  RPS-B [IC95]")
        for r in righe:
            print(f"{r['candidato']:32s} {r['log_score']:9.4f} {r['rps']:8.4f} "
                  f"{r['brier_1x2']:9.4f} {r['brier_cs']:8.4f} "
                  f"{r['calib_cs']:8.4f}  {r['rps_meno_B']:+.4f} "
                  f"[{r['rps_meno_B_ic95'][0]:+.4f}, {r['rps_meno_B_ic95'][1]:+.4f}]")
        print(f"    rho stimato: E {diag['rho_E']}, F {diag['rho_F']} | "
              f"vantaggio casa {diag['vantaggio_casa_E']} | "
              f"neopromosse con prior: "
              f"{conf.diagnostica['neopromosse_con_prior']}")
        amm = conf.diagnostica["ammissibilita"]
        print(f"    ammissibilita' F: rho {amm['rho']:+.4f} in "
              f"[{amm['rho_ammissibile'][0]:.4f}, {amm['rho_ammissibile'][1]:.4f}]"
              f", margine {amm['margine_rho']:.4f}, celle tau non positive "
              f"{amm['celle_tau_non_positive']}, coda troncata max "
              f"{amm['massa_coda_massima']:.2e}")
        print(f"    gol ospite: osservati "
              f"{diag['E']['gol_ospite_medi_osservati']:.4f}, stimati "
              f"{diag['E']['gol_ospite_medi_stimati']:.4f}")

    df = pd.DataFrame(riepilogo)
    df.to_csv(OUT / "banco_partita.csv", index=False)
    (OUT / "banco_partita.json").write_text(
        json.dumps({"dettagli": dettagli, "seed": a.seed, "boot": a.boot,
                    "xi_provati": XI, "lam_provati": LAM,
                    "procedura": cfg.VERSIONE}, indent=1,
                   default=str), encoding="utf-8")
    print(f"\nscritto {OUT / 'banco_partita.csv'} e le previsioni per stagione")
    if len(df):
        print("\nmedia sulle stagioni di prova (solo candidati pre-asta):")
        pre = df[~df.candidato.str.startswith("G")]
        print(pre.groupby("candidato")[["log_score", "rps", "brier_1x2",
                                        "brier_cs"]].mean().round(4).to_string())
    return 0


if __name__ == "__main__":
    sys.exit(main())
