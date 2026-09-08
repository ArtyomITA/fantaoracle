#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Esperimento G1 — calibrazione della distribuzione dei gol fuori campione.

Esegue alla lettera il criterio scritto in `reports/CRITERI_L2_L3.md`, sezione
7.6, che e' stato fissato PRIMA di questo esperimento. Qui non si aggiungono
trattamenti, non si spostano soglie e non si tocca `xi`.

## Che cosa confronta

Tre modi di propagare l'incertezza sulle forze del modello di partita, a
parita' di punto stimato (stesse partite di addestramento, stessi
iperparametri scelti dalla procedura unica, stesso ottimo):

  T0  punto stimato          nessuna dispersione sui parametri.
  T1  hessiana               forze estratte da N(theta, H^-1), dove H e'
                             l'hessiana della verosimiglianza pesata e
                             penalizzata. E' il comportamento attuale
                             (`ModelloPartita.campiona_parametri`).
  T2  sandwich               forze estratte da N(theta, H^-1 J H^-1) con
                             J = somma_i w_i^2 g_i g_i^T, g_i gradiente
                             NON pesato della log-verosimiglianza della
                             singola partita i e w_i il peso di decadimento.

## Come si misura

La distribuzione prevista di un trattamento e' la MISTURA sulle estrazioni dei
parametri: P_previsto = media_k P(theta_k). Il punteggio logaritmico e' quello
del risultato osservato sotto questa mistura (misura primaria, propria). Le
altre misure (RPS sui gol di squadra, Brier sulla porta inviolata,
calibrazione della coda, PIT randomizzato) si leggono dalla stessa mistura.

I tre trattamenti vedono le stesse partite e gli stessi numeri casuali comuni:
la stessa matrice Z di normali standard genera le estrazioni di T1 e di T2
(cambia solo il fattore di Cholesky), gli stessi uniformi `u` alimentano
`campiona_risultati` nel blocco descrittivo degli scenari, e gli stessi
uniformi randomizzano il PIT.

## Regole dichiarate prima dell'esecuzione

  1. Il gradiente per osservazione e' verificato contro `_neg_loglik_e_gradiente`:
     la somma pesata dei contributi deve coincidere con il gradiente totale
     della log-verosimiglianza (penalizzazione esclusa) entro 1e-6. Se non
     coincide lo script si ferma: e' un blocco, non un avviso.
  2. Le estrazioni che non superano `verifica_ammissibilita` sulle partite
     bersaglio esistono davvero e vanno dichiarate. Il testo di 7.6 definisce
     T1 come «comportamento attuale» e non prevede nessun rigetto; il
     generatore in produzione (`src/fantabot/tabellino/generatore.py`, riga
     344 e seguenti) infatti non rigetta: prende la matrice, la tronca con
     `np.maximum(P, 0)` e la rinormalizza. Quella e' la gestione PRIMARIA,
     chiamata qui «generatore», ed e' quella su cui si applica la regola di
     decisione.
     Poiche' `configurazione.py` documenta che un'estrazione non ammissibile
     «va scartata», la stessa misura viene calcolata anche con la gestione
     «esclusione» (estrazioni non ammissibili tolte dalla mistura) e
     riportata accanto. Le due gestioni non sono due trattamenti nuovi: sono
     due letture del medesimo T1/T2, e servono a far vedere se il verdetto
     dipende da questa scelta. Nessuna estrazione viene mai riestratta:
     riestrarre romperebbe i numeri casuali comuni.
  3. Il numero di estrazioni, il numero di ricampionamenti bootstrap e il seme
     sono costanti di questo file, fissate prima di guardare i risultati.

## Riproducibilita'

    python scripts/g1_calibrazione_gol.py

rifa tutto da capo e riscrive `data/l2/g1/`. Il seme e' fisso, le date limite
si ricavano dai dati, e il manifesto registra impronte, versioni e tempi.
"""
from __future__ import annotations

import json
import platform
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
PROC = ROOT / "data" / "processed"
OUT = ROOT / "data" / "l2" / "g1"

from fantabot.tabellino import configurazione as cfg              # noqa: E402
from fantabot.tabellino.partita import (                          # noqa: E402
    MAX_GOL, ModelloPartita, campiona_risultati, matrice_risultato,
    pesi_decadimento, tau, _neg_loglik_e_gradiente,
)

# --------------------------------------------------------------------------
# costanti dell'esperimento, fissate prima di eseguirlo
# --------------------------------------------------------------------------

SEME = 20260907
N_ESTRAZIONI = 1000        # estrazioni di parametri per T1 e T2 (minimo di 7.6: 200)
N_SCENARI = 200            # scenari simulati con numeri casuali comuni (descrittivi)
N_BOOTSTRAP = 5000         # ricampionamenti appaiati per partita (minimo di 7.6: 2000)
STAGIONI_BERSAGLIO = ("2024-25", "2025-26")
TRATTAMENTI = ("T0", "T1", "T2")
# gestione delle estrazioni non ammissibili: «generatore» e' quella primaria
# (nessun rigetto, troncamento a zero e rinormalizzazione, come fa il
# generatore in produzione), «esclusione» e' la lettura alternativa.
GESTIONI = ("generatore", "esclusione")
GESTIONE_PRIMARIA = "generatore"
JITTER = 1e-10             # stesso valore usato da `campiona_parametri`
TOLLERANZA_GRADIENTE = 1e-6
PERCORSO_PARTITE = PROC / "l2_partite.parquet"


# --------------------------------------------------------------------------
# registro di esecuzione
# --------------------------------------------------------------------------

class Registro:
    """Scrive a schermo e su file, con marca temporale e secondi trascorsi."""

    def __init__(self, percorso: Path):
        self.percorso = percorso
        self.t0 = time.perf_counter()
        percorso.parent.mkdir(parents=True, exist_ok=True)
        self.f = open(percorso, "w", encoding="utf-8")

    def __call__(self, testo: str) -> None:
        riga = (f"[{datetime.now().strftime('%H:%M:%S')} "
                f"+{time.perf_counter() - self.t0:8.2f}s] {testo}")
        print(riga, flush=True)
        self.f.write(riga + "\n")
        self.f.flush()

    def chiudi(self) -> None:
        self.f.close()


def _picco_ram_mb() -> float:
    """Picco di memoria residente del processo, in MiB.

    Su Windows `psutil` espone `peak_wset`, che e' il vero picco; altrove si
    ripiega sul valore corrente, dichiarandolo tale nel manifesto."""
    try:
        import psutil
        info = psutil.Process().memory_info()
        for campo in ("peak_wset", "peak_rss"):
            if hasattr(info, campo):
                return float(getattr(info, campo)) / (1024 ** 2)
        return float(info.rss) / (1024 ** 2)
    except Exception:
        return float("nan")


# --------------------------------------------------------------------------
# gradiente per osservazione
# --------------------------------------------------------------------------

def gradienti_per_osservazione(th, h, a, x, y, n, usa_dc):
    """Gradiente della log-verosimiglianza di ciascuna partita, NON pesato.

    Ricalca riga per riga `_neg_loglik_e_gradiente` di `partita.py`, con due
    sole differenze dichiarate:

      - il peso `w_i` non entra (il chiamante lo applica dove serve: `w_i` per
        ricostruire il gradiente totale, `w_i^2` per la matrice J);
      - il segno e' quello della log-verosimiglianza, non della sua negazione,
        e la penalizzazione non c'e' (e' un termine unico, non per osservazione).

    La centratura di attacco e difesa (`dA_i/da_j = delta_ij - 1/n`) e' lineare,
    quindi si applica al contributo della singola partita esattamente come si
    applica alla somma: e' questo che rende la somma dei contributi uguale al
    gradiente totale.

    Ritorna la matrice S di forma (n_partite, n_parametri).
    """
    th = np.asarray(th, dtype=float)
    x = np.asarray(x, dtype=float)
    y = np.asarray(y, dtype=float)
    h = np.asarray(h, dtype=int)
    a = np.asarray(a, dtype=int)

    att_raw = th[:n]
    dif_raw = th[n:2 * n]
    mu, casa = th[2 * n], th[2 * n + 1]
    rho = th[2 * n + 2] if usa_dc else 0.0
    att = att_raw - att_raw.mean()
    dif = dif_raw - dif_raw.mean()
    loglam = mu + casa + att[h] - dif[a]
    logmu = mu + att[a] - dif[h]
    lam = np.exp(loglam)
    m = np.exp(logmu)

    dlam = x - lam
    dmu_ = y - m
    dr = np.zeros_like(lam)
    if usa_dc:
        t = tau(x, y, lam, m, rho)
        if np.any(t <= 0):
            raise ValueError("tau non positivo: theta fuori dalla zona "
                             "ammissibile, il gradiente non e' definito")
        c00 = (x == 0) & (y == 0)
        c01 = (x == 0) & (y == 1)
        c10 = (x == 1) & (y == 0)
        c11 = (x == 1) & (y == 1)
        dl = np.zeros_like(lam)
        dm = np.zeros_like(lam)
        dl[c00] = -lam[c00] * m[c00] * rho / t[c00]
        dm[c00] = dl[c00]
        dr[c00] = -lam[c00] * m[c00] / t[c00]
        dl[c01] = lam[c01] * rho / t[c01]
        dr[c01] = lam[c01] / t[c01]
        dm[c10] = m[c10] * rho / t[c10]
        dr[c10] = m[c10] / t[c10]
        dr[c11] = -1.0 / t[c11]
        dlam = dlam + dl
        dmu_ = dmu_ + dm

    n_obs = len(x)
    k = 2 * n + 2 + (1 if usa_dc else 0)
    S = np.zeros((n_obs, k))
    righe = np.arange(n_obs)

    # blocco attacco, prima della centratura
    S[righe, h] += dlam
    S[righe, a] += dmu_
    # blocco difesa, prima della centratura
    S[righe, n + a] += -dlam
    S[righe, n + h] += -dmu_
    # centratura: la media del contributo della partita i vale
    # (dlam_i + dmu_i)/n per l'attacco e il suo opposto per la difesa
    S[:, :n] -= ((dlam + dmu_) / n)[:, None]
    S[:, n:2 * n] -= (-(dlam + dmu_) / n)[:, None]

    S[:, 2 * n] = dlam + dmu_
    S[:, 2 * n + 1] = dlam
    if usa_dc:
        S[:, 2 * n + 2] = dr
    return S


def verifica_gradiente(th, h, a, x, y, w, n, usa_dc, prior_att, prior_dif,
                       lam_pen):
    """Somma pesata dei contributi contro il gradiente totale della funzione.

    Confronta `sum_i w_i g_i` con il gradiente della sola log-verosimiglianza
    ottenuto da `_neg_loglik_e_gradiente`, in due modi indipendenti:

      A. chiamando la funzione con `lam_pen = 0` (la penalizzazione sparisce);
      B. chiamandola con la `lam_pen` vera e togliendo analiticamente il
         termine di penalizzazione, che vale `-2 lam_pen (theta_raw - prior)`
         sui blocchi attacco e difesa.

    Ritorna un dizionario con i due scarti massimi. Il chiamante decide che
    farne; questo modulo non alza soglie."""
    S = gradienti_per_osservazione(th, h, a, x, y, n, usa_dc)
    somma = (S * np.asarray(w, dtype=float)[:, None]).sum(axis=0)

    _, grad0 = _neg_loglik_e_gradiente(th, h, a, x, y, w, n, 0.0, usa_dc,
                                       np.zeros(n), np.zeros(n))
    scarto_a = float(np.max(np.abs(somma - (-grad0))))

    _, grad1 = _neg_loglik_e_gradiente(th, h, a, x, y, w, n, lam_pen, usa_dc,
                                       prior_att, prior_dif)
    penalizzazione = np.zeros_like(somma)
    penalizzazione[:n] = -2 * lam_pen * (th[:n] - prior_att)
    penalizzazione[n:2 * n] = -2 * lam_pen * (th[n:2 * n] - prior_dif)
    scarto_b = float(np.max(np.abs(somma - (-grad1 - penalizzazione))))

    return {"scarto_lam_pen_zero": scarto_a,
            "scarto_penalizzazione_tolta": scarto_b,
            "norma_gradiente_totale": float(np.max(np.abs(somma))),
            "n_osservazioni": int(S.shape[0]),
            "n_parametri": int(S.shape[1])}


def matrice_j(S, w):
    """J = somma_i w_i^2 g_i g_i^T, con g_i gradiente NON pesato.

    Scritta come prodotto di matrici: `(S * w)^T (S * w)` e' esattamente
    `S^T diag(w^2) S`, cioe' la somma richiesta, senza costruire n_partite
    matrici k x k."""
    Sw = np.asarray(S, dtype=float) * np.asarray(w, dtype=float)[:, None]
    return Sw.T @ Sw


def covarianza_sandwich(hess_inv, J):
    """H^-1 J H^-1, simmetrizzata contro l'asimmetria numerica."""
    C = np.asarray(hess_inv) @ np.asarray(J) @ np.asarray(hess_inv)
    return 0.5 * (C + C.T)


# --------------------------------------------------------------------------
# estrazione dei parametri con numeri casuali comuni
# --------------------------------------------------------------------------

def cholesky_robusta(cov, jitter=JITTER):
    """Fattore di Cholesky di `cov + jitter I`, alzando il jitter se serve.

    `campiona_parametri` usa `cholesky(hess_inv + 1e-10 I)`: qui si parte dallo
    stesso valore, cosi' T1 riprodotto a mano coincide con il comportamento
    attuale bit per bit. Se la sandwich fosse numericamente semidefinita il
    jitter sale per potenze di dieci e il valore usato viene restituito."""
    cov = np.asarray(cov, dtype=float)
    k = cov.shape[0]
    j = jitter
    for _ in range(12):
        try:
            return np.linalg.cholesky(cov + j * np.eye(k)), j
        except np.linalg.LinAlgError:
            j *= 10.0
    raise np.linalg.LinAlgError("covarianza non fattorizzabile nemmeno con "
                                f"jitter {j}")


def campiona_con_covarianza(modello: ModelloPartita, cov, Z):
    """Estrazioni dei parametri con la covarianza data e le normali comuni Z.

    Replica esattamente il percorso di `ModelloPartita.campiona_parametri`
    (`theta + L z`, poi `_da_theta`), sostituendo alla covarianza l'argomento:
    con `cov = modello._hess_inv` e le stesse normali il risultato coincide con
    il comportamento attuale. Il test
    `test_t1_coincide_con_campiona_parametri` fissa la proprieta'."""
    L, jitter_usato = cholesky_robusta(cov)
    theta = modello._theta
    return [modello._da_theta(theta + L @ z) for z in np.asarray(Z)], jitter_usato


# --------------------------------------------------------------------------
# mistura predittiva e misure
# --------------------------------------------------------------------------

def matrici_di_un_modello(modello: ModelloPartita, casa, trasferta,
                          max_gol=MAX_GOL):
    """Distribuzione congiunta di ogni partita sotto un singolo modello."""
    lam, mu = modello.intensita(np.asarray(casa), np.asarray(trasferta))
    n = len(lam)
    P = np.empty((n, max_gol + 1, max_gol + 1))
    rho = float(modello.rho)
    for i in range(n):
        P[i] = matrice_risultato(float(lam[i]), float(mu[i]), rho, max_gol)
    return P


def mistura(modelli, casa, trasferta, max_gol=MAX_GOL, registro=None,
            ogni=100):
    """Media delle distribuzioni congiunte sulle estrazioni dei parametri.

    Accumula in loco: con 1000 estrazioni e 380 partite tenere tutte le
    matrici costerebbe mezzo gigabyte, e non servirebbe a nulla."""
    acc = None
    for k, m in enumerate(modelli):
        P = matrici_di_un_modello(m, casa, trasferta, max_gol)
        acc = P if acc is None else acc + P
        if registro is not None and (k + 1) % ogni == 0:
            registro(f"    mistura: {k + 1}/{len(modelli)} estrazioni")
    return acc / float(len(modelli))


def misture(modelli, ammissibile, casa, trasferta, max_gol=MAX_GOL,
            registro=None, ogni=100):
    """Le due misture della stessa serie di estrazioni.

    Una sola passata sulle estrazioni, perche' il costo sta tutto nel costruire
    le matrici congiunte:

      «generatore»  tutte le estrazioni, ciascuna troncata a zero e
                    rinormalizzata come fa `generatore.py` in produzione;
      «esclusione»  solo le estrazioni ammissibili, senza alcuna correzione.

    Ritorna (mistura_generatore, mistura_esclusione, n_ammissibili). La seconda
    e' `None` se nessuna estrazione e' ammissibile."""
    acc_gen = None
    acc_esc = None
    n_amm = 0
    for k, m in enumerate(modelli):
        P = matrici_di_un_modello(m, casa, trasferta, max_gol)
        Pg = np.maximum(P, 0.0)
        Pg = Pg / Pg.reshape(len(Pg), -1).sum(axis=1)[:, None, None]
        acc_gen = Pg if acc_gen is None else acc_gen + Pg
        if ammissibile[k]:
            acc_esc = P.copy() if acc_esc is None else acc_esc + P
            n_amm += 1
        if registro is not None and (k + 1) % ogni == 0:
            registro(f"    misture: {k + 1}/{len(modelli)} estrazioni")
    return (acc_gen / float(len(modelli)),
            (acc_esc / float(n_amm)) if n_amm else None,
            n_amm)


def punteggio_logaritmico(P, gol_casa, gol_trasferta):
    """-log P(risultato osservato), con lo stesso pavimento di `partita.py`."""
    g = P.shape[1] - 1
    gc = np.clip(np.asarray(gol_casa, dtype=int), 0, g)
    gt = np.clip(np.asarray(gol_trasferta, dtype=int), 0, g)
    p = P[np.arange(P.shape[0]), gc, gt]
    return -np.log(np.maximum(p, 1e-12))


def marginali(P):
    """(marginale gol casa, marginale gol trasferta) dalla congiunta."""
    return P.sum(axis=2), P.sum(axis=1)


def rps(marg, osservati):
    """RPS ordinale sul numero di gol.

    Definizione usata: somma sui tagli j = 0 .. J-2 di (F_j - O_j)^2, con F_j
    cumulata prevista fino a j e O_j indicatore `osservato <= j`. Non e'
    divisa per (J-1): il test `test_rps_caso_a_mano` fissa il valore esatto su
    un caso costruito a mano, quindi la convenzione non e' ambigua."""
    F = np.cumsum(marg, axis=1)[:, :-1]
    j = np.arange(marg.shape[1] - 1)[None, :]
    O = (np.asarray(osservati, dtype=int)[:, None] <= j).astype(float)
    return ((F - O) ** 2).sum(axis=1)


def brier_porta_inviolata(marg_casa, marg_trasferta, gol_casa, gol_trasferta):
    """Brier sull'evento «la squadra non subisce gol», due eventi per partita.

    La porta inviolata della squadra di casa e' l'evento «la trasferta segna
    zero», quindi la probabilita' prevista si legge sulla marginale della
    trasferta. Ritorna (brier_casa, brier_trasferta)."""
    p_casa = marg_trasferta[:, 0]
    p_via = marg_casa[:, 0]
    o_casa = (np.asarray(gol_trasferta, dtype=int) == 0).astype(float)
    o_via = (np.asarray(gol_casa, dtype=int) == 0).astype(float)
    return (p_casa - o_casa) ** 2, (p_via - o_via) ** 2


def pit_randomizzato(marg, osservati, v):
    """PIT randomizzato: F(g-1) + v (F(g) - F(g-1)).

    Con dati interi il PIT non randomizzato non e' uniforme nemmeno sotto il
    modello vero; la randomizzazione lo rende uniforme e permette il test."""
    F = np.cumsum(marg, axis=1)
    g = np.asarray(osservati, dtype=int)
    righe = np.arange(len(g))
    F_g = F[righe, np.clip(g, 0, marg.shape[1] - 1)]
    F_prec = np.where(g > 0, F[righe, np.clip(g - 1, 0, marg.shape[1] - 1)], 0.0)
    return F_prec + np.asarray(v, dtype=float) * (F_g - F_prec)


def intervallo_binomiale(k, n, livello=0.95):
    """Intervallo esatto di Clopper-Pearson per una frequenza osservata."""
    from scipy.stats import beta
    alpha = 1.0 - livello
    basso = 0.0 if k == 0 else float(beta.ppf(alpha / 2, k, n - k + 1))
    alto = 1.0 if k == n else float(beta.ppf(1 - alpha / 2, k + 1, n - k))
    return basso, alto


# --------------------------------------------------------------------------
# bootstrap appaiato
# --------------------------------------------------------------------------

def bootstrap_appaiato(differenze, indici):
    """Media e intervallo percentile al 95 % della differenza appaiata.

    `indici` e' la matrice dei ricampionamenti (B x n): la stessa per tutti i
    confronti della stagione, cosi' i tre confronti sono coerenti fra loro."""
    d = np.asarray(differenze, dtype=float)
    campioni = d[indici].mean(axis=1)
    basso, alto = np.percentile(campioni, [2.5, 97.5])
    return {"differenza_media": float(d.mean()),
            "ic_basso": float(basso), "ic_alto": float(alto),
            "contiene_zero": bool(basso <= 0.0 <= alto),
            "n_bootstrap": int(indici.shape[0])}


# --------------------------------------------------------------------------
# esperimento su una stagione
# --------------------------------------------------------------------------

def data_limite_stagione(partite, stagione) -> str:
    """Giorno prima della prima giornata della stagione bersaglio."""
    prima = pd.to_datetime(partite.loc[partite.stagione == stagione, "data"]).min()
    return str((prima - pd.Timedelta(days=1)).date())


def esegui_stagione(partite, stagione, i_stagione, log):
    log(f"=== stagione bersaglio {stagione} ===")
    as_of = data_limite_stagione(partite, stagione)
    log(f"  data limite = {as_of}")

    t = time.perf_counter()
    mod, conf, impronta = cfg.costruisci_modello_partita(
        partite, as_of, con_incertezza=True, stagione_bersaglio=stagione,
        percorsi_ingresso=[PERCORSO_PARTITE],
        etichetta=f"G1 {stagione}")
    log(f"  modello costruito in {time.perf_counter() - t:.2f}s, "
        f"impronta {impronta[:12]}, squadre {len(mod.squadre)}, "
        f"parametri {len(mod._theta)}")
    log(f"  iperparametri {conf.iperparametri} "
        f"(origine: {conf.origine_iperparametri.get('modo')})")
    log(f"  addestramento: {conf.n_partite_addestramento} partite, "
        f"peso totale {conf.peso_totale:.2f}")

    if mod._hess_inv is None:
        raise SystemExit("BLOCCO: l'informazione osservata non e' disponibile, "
                         "T1 e T2 non sono costruibili")

    # --- ricostruzione degli ingressi della verosimiglianza -----------------
    tr, filtro = cfg.partite_di_addestramento(partite, as_of)
    if (tr.stagione == stagione).any():
        raise SystemExit(f"BLOCCO: {int((tr.stagione == stagione).sum())} partite "
                         f"della stagione bersaglio {stagione} sono finite "
                         "nell'addestramento")
    squadre = list(mod.squadre)
    ix = {s: i for i, s in enumerate(squadre)}
    h = np.array([ix[s] for s in tr.casa.values])
    a = np.array([ix[s] for s in tr.trasferta.values])
    x = tr.gol_casa.values.astype(float)
    y = tr.gol_trasferta.values.astype(float)
    xi = float(conf.iperparametri["xi"])
    lam_pen = float(conf.iperparametri["lam_pen"])
    usa_dc = bool(conf.iperparametri["usa_dc"])
    w = pesi_decadimento(tr.data.values.astype("datetime64[D]"), as_of, xi)
    prior_att = np.array([float(conf.prior_att.get(s, 0.0)) for s in squadre])
    prior_dif = np.array([float(conf.prior_dif.get(s, 0.0)) for s in squadre])
    n = len(squadre)
    th = np.asarray(mod._theta, dtype=float)

    # --- verifica obbligatoria del gradiente per osservazione ---------------
    ver = verifica_gradiente(th, h, a, x, y, w, n, usa_dc, prior_att,
                             prior_dif, lam_pen)
    log(f"  verifica gradiente: scarto (lam_pen=0) {ver['scarto_lam_pen_zero']:.3e}, "
        f"scarto (penalizzazione tolta) {ver['scarto_penalizzazione_tolta']:.3e}")
    peggiore = max(ver["scarto_lam_pen_zero"], ver["scarto_penalizzazione_tolta"])
    if not np.isfinite(peggiore) or peggiore > TOLLERANZA_GRADIENTE:
        raise SystemExit(
            f"BLOCCO: il gradiente per osservazione non somma al totale "
            f"(scarto {peggiore:.3e} > {TOLLERANZA_GRADIENTE:.0e}). "
            "L'esperimento si ferma qui, come previsto.")

    # --- matrice J e covarianza sandwich ------------------------------------
    S = gradienti_per_osservazione(th, h, a, x, y, n, usa_dc)
    J = matrice_j(S, w)
    cov_t1 = np.asarray(mod._hess_inv, dtype=float)
    cov_t2 = covarianza_sandwich(cov_t1, J)
    sd1 = np.sqrt(np.clip(np.diag(cov_t1), 0, None))
    sd2 = np.sqrt(np.clip(np.diag(cov_t2), 0, None))
    log(f"  deviazione standard mediana dei parametri: "
        f"T1 {np.median(sd1):.4f}, T2 {np.median(sd2):.4f} "
        f"(rapporto mediano T2/T1 {np.median(sd2 / np.maximum(sd1, 1e-15)):.3f})")
    log(f"  somma dei pesi {w.sum():.2f}, somma dei quadrati dei pesi "
        f"{np.sum(w ** 2):.2f}")

    # --- partite fuori campione ---------------------------------------------
    bersaglio = partite[(partite.stagione == stagione)
                        & partite.gol_casa.notna()
                        & partite.gol_trasferta.notna()].copy()
    bersaglio = bersaglio.sort_values(["data", "casa"]).reset_index(drop=True)
    casa = bersaglio.casa.values
    via = bersaglio.trasferta.values
    gc = bersaglio.gol_casa.values.astype(int)
    gt = bersaglio.gol_trasferta.values.astype(int)
    n_p = len(bersaglio)
    log(f"  partite fuori campione effettivamente giocate: {n_p}")

    # --- numeri casuali comuni ----------------------------------------------
    k_par = len(th)
    Z = np.random.default_rng([SEME, i_stagione, 1]).standard_normal(
        (N_ESTRAZIONI, k_par))
    u_comuni = np.random.default_rng([SEME, i_stagione, 2]).random(
        (N_SCENARI, n_p))
    v_pit = np.random.default_rng([SEME, i_stagione, 3]).random((n_p, 2))
    rng_boot = np.random.default_rng([SEME, i_stagione, 4])
    indici_boot = rng_boot.integers(0, n_p, size=(N_BOOTSTRAP, n_p))

    # --- i tre trattamenti ---------------------------------------------------
    estrazioni = {"T0": [mod]}
    jitter = {"T0": 0.0}
    estrazioni["T1"], jitter["T1"] = campiona_con_covarianza(mod, cov_t1, Z)
    estrazioni["T2"], jitter["T2"] = campiona_con_covarianza(mod, cov_t2, Z)
    log(f"  jitter di Cholesky: T1 {jitter['T1']:.0e}, T2 {jitter['T2']:.0e}")

    risultati = []
    per_partita = []
    punteggi = {g: {} for g in GESTIONI}
    rigetti = {}
    for tratt in TRATTAMENTI:
        t = time.perf_counter()
        modelli = estrazioni[tratt]
        # ammissibilita' di ogni estrazione sulle partite bersaglio
        esiti = [cfg.verifica_ammissibilita(m, casa, via) for m in modelli]
        ammissibile = [e["ammissibile"] for e in esiti]
        n_rigetti = int(len(modelli) - sum(ammissibile))
        rigetti[tratt] = n_rigetti
        log(f"  {tratt}: {len(modelli)} estrazioni, {n_rigetti} non ammissibili "
            f"(margine rho minimo {min(e['margine_rho'] for e in esiti):+.4f})")

        P_gen, P_esc, n_amm = misture(
            modelli, ammissibile, casa, via,
            registro=log if len(modelli) > 200 else None)
        log(f"  {tratt}: misture pronte in {time.perf_counter() - t:.1f}s")

        for gestione in GESTIONI:
            P = P_gen if gestione == "generatore" else P_esc
            if P is None:
                log(f"  {tratt}/{gestione}: nessuna estrazione ammissibile, "
                    "gestione non calcolabile")
                continue
            n_usate = len(modelli) if gestione == "generatore" else n_amm
            somma = P.reshape(len(P), -1).sum(axis=1)

            ls = punteggio_logaritmico(P, gc, gt)
            mc, mv = marginali(P)
            rps_casa = rps(mc, gc)
            rps_via = rps(mv, gt)
            br_casa, br_via = brier_porta_inviolata(mc, mv, gc, gt)
            pit_casa = pit_randomizzato(mc, gc, v_pit[:, 0])
            pit_via = pit_randomizzato(mv, gt, v_pit[:, 1])

            # coda: per squadra-partita, quindi casa e trasferta insieme
            p0_prev = float(np.mean(np.concatenate([mc[:, 0], mv[:, 0]])))
            p6_prev = float(np.mean(np.concatenate([mc[:, 6:].sum(axis=1),
                                                    mv[:, 6:].sum(axis=1)])))
            gol_oss = np.concatenate([gc, gt])
            k0 = int(np.sum(gol_oss == 0))
            k6 = int(np.sum(gol_oss >= 6))
            n_sq = len(gol_oss)
            ic0 = intervallo_binomiale(k0, n_sq)
            ic6 = intervallo_binomiale(k6, n_sq)

            # media e varianza previste per squadra-partita
            griglia = np.arange(P.shape[1])
            media_prev = float(np.mean(np.concatenate([mc @ griglia, mv @ griglia])))
            secondo = np.concatenate([mc @ (griglia ** 2), mv @ (griglia ** 2)])
            # varianza della mistura sulle squadra-partita: media dei secondi
            # momenti meno il quadrato della media complessiva
            var_prev = float(np.mean(secondo) - media_prev ** 2)

            from scipy.stats import kstest
            ks = kstest(np.concatenate([pit_casa, pit_via]), "uniform")

            punteggi[gestione][tratt] = ls
            risultati.append({
                "stagione": stagione, "trattamento": tratt,
                "gestione": gestione,
                "n_partite": n_p, "n_squadra_partita": n_sq,
                "n_estrazioni": len(modelli),
                "n_estrazioni_non_ammissibili": n_rigetti,
                "n_estrazioni_usate": int(n_usate),
                "log_score_medio": float(ls.mean()),
                "log_score_errore_standard": float(ls.std(ddof=1) / np.sqrt(n_p)),
                "rps_medio": float(np.mean(np.concatenate([rps_casa, rps_via]))),
                "brier_porta_inviolata": float(np.mean(np.concatenate([br_casa, br_via]))),
                "p0_previsto": p0_prev,
                "p0_osservato": k0 / n_sq,
                "p0_ic95_basso": ic0[0], "p0_ic95_alto": ic0[1],
                "p0_dentro_ic": bool(ic0[0] <= p0_prev <= ic0[1]),
                "p6_previsto": p6_prev,
                "p6_osservato": k6 / n_sq,
                "p6_ic95_basso": ic6[0], "p6_ic95_alto": ic6[1],
                "p6_dentro_ic": bool(ic6[0] <= p6_prev <= ic6[1]),
                "media_gol_prevista": media_prev,
                "media_gol_osservata": float(gol_oss.mean()),
                "varianza_gol_prevista": var_prev,
                "varianza_gol_osservata": float(gol_oss.var(ddof=1)),
                "pit_ks_statistica": float(ks.statistic),
                "pit_ks_p": float(ks.pvalue),
                "somma_congiunta_minima": float(somma.min()),
                "somma_congiunta_massima": float(somma.max()),
                "cella_minima": float(P.min()),
                "massa_coda_troncata_media": float(np.mean(
                    [e["massa_coda_media"] for e in esiti])),
                "jitter_cholesky": jitter[tratt],
                "secondi": round(time.perf_counter() - t, 2),
            })
            log(f"  {tratt}/{gestione}: log score {ls.mean():.6f}, "
                f"RPS {risultati[-1]['rps_medio']:.6f}, "
                f"Brier {risultati[-1]['brier_porta_inviolata']:.6f}, "
                f"P(0) {p0_prev:.4f} vs {k0 / n_sq:.4f}, "
                f"P(>=6) {p6_prev:.5f} vs {k6 / n_sq:.5f}, "
                f"PIT KS p={ks.pvalue:.4f}")

            per_partita.append(pd.DataFrame({
                "stagione": stagione, "trattamento": tratt,
                "gestione": gestione,
                "data": bersaglio.data.values, "casa": casa, "trasferta": via,
                "gol_casa": gc, "gol_trasferta": gt,
                "log_score": ls,
                "rps_casa": rps_casa, "rps_trasferta": rps_via,
                "brier_casa": br_casa, "brier_trasferta": br_via,
                "pit_casa": pit_casa, "pit_trasferta": pit_via,
            }))

    # --- confronti appaiati sul punteggio logaritmico ------------------------
    confronti = []
    for gestione in GESTIONI:
        tab = punteggi[gestione]
        for i in range(len(TRATTAMENTI)):
            for j in range(i + 1, len(TRATTAMENTI)):
                A, B = TRATTAMENTI[i], TRATTAMENTI[j]
                if A not in tab or B not in tab:
                    continue
                d = tab[A] - tab[B]   # negativo = A migliore (log score piu' basso)
                r = bootstrap_appaiato(d, indici_boot)
                r.update({"stagione": stagione, "gestione": gestione,
                          "A": A, "B": B,
                          "log_score_A": float(tab[A].mean()),
                          "log_score_B": float(tab[B].mean()),
                          "migliore": A if d.mean() < 0 else (B if d.mean() > 0 else "pari")})
                confronti.append(r)
                log(f"  {gestione}: {A} - {B}: {r['differenza_media']:+.6f} "
                    f"IC95 [{r['ic_basso']:+.6f}, {r['ic_alto']:+.6f}] "
                    f"{'contiene zero' if r['contiene_zero'] else 'ESCLUDE zero'}")

    # --- scenari con numeri casuali comuni (descrittivi) ---------------------
    # Qui si usa la gestione «generatore»: `campiona_risultati` tronca a zero e
    # rinormalizza esattamente come fa il generatore in produzione.
    scenari = []
    for tratt in TRATTAMENTI:
        t = time.perf_counter()
        modelli = estrazioni[tratt]
        gol = np.empty((N_SCENARI, n_p, 2), dtype=np.int16)
        rng_finto = np.random.default_rng(0)     # non usato: `u` arriva da fuori
        for s in range(N_SCENARI):
            m = modelli[s % len(modelli)]
            lam, mu = m.intensita(casa, via)
            gol[s] = campiona_risultati(lam, mu, float(m.rho), rng_finto,
                                        u=u_comuni[s:s + 1])[0]
        piatto = gol.reshape(-1)
        scenari.append({
            "stagione": stagione, "trattamento": tratt,
            "n_scenari": N_SCENARI, "n_squadra_partita_simulate": int(piatto.size),
            "media_gol": float(piatto.mean()),
            "varianza_gol": float(piatto.var(ddof=1)),
            "p0_gol": float(np.mean(piatto == 0)),
            "p6_o_piu_gol": float(np.mean(piatto >= 6)),
            "massimo_gol": int(piatto.max()),
            "secondi": round(time.perf_counter() - t, 2),
        })
        log(f"  {tratt} scenari: media {piatto.mean():.4f}, "
            f"varianza {piatto.var(ddof=1):.4f}, P(0) {np.mean(piatto == 0):.4f}, "
            f"P(>=6) {np.mean(piatto >= 6):.5f}, max {piatto.max()}")

    gol_oss = np.concatenate([gc, gt])
    scenari.append({
        "stagione": stagione, "trattamento": "osservato",
        "n_scenari": 0, "n_squadra_partita_simulate": int(gol_oss.size),
        "media_gol": float(gol_oss.mean()),
        "varianza_gol": float(gol_oss.var(ddof=1)),
        "p0_gol": float(np.mean(gol_oss == 0)),
        "p6_o_piu_gol": float(np.mean(gol_oss >= 6)),
        "massimo_gol": int(gol_oss.max()), "secondi": 0.0,
    })

    dettaglio = {
        "stagione": stagione, "as_of": as_of, "impronta": impronta,
        "configurazione": conf.a_dizionario(),
        "verifica_gradiente": ver,
        "peso_totale": float(w.sum()),
        "somma_quadrati_pesi": float(np.sum(w ** 2)),
        "n_parametri": int(k_par),
        "sd_mediana_T1": float(np.median(sd1)),
        "sd_mediana_T2": float(np.median(sd2)),
        "rapporto_sd_mediano_T2_su_T1": float(np.median(sd2 / np.maximum(sd1, 1e-15))),
        "traccia_cov_T1": float(np.trace(cov_t1)),
        "traccia_cov_T2": float(np.trace(cov_t2)),
        "jitter_cholesky": jitter,
        "estrazioni_non_ammissibili": rigetti,
        "filtro_addestramento": filtro,
    }
    return (pd.DataFrame(risultati),
            pd.DataFrame(confronti), pd.concat(per_partita, ignore_index=True),
            pd.DataFrame(scenari), dettaglio)


# --------------------------------------------------------------------------
# regola di decisione della sezione 7.6
# --------------------------------------------------------------------------

def verdetto(metriche, confronti, gestione=None):
    """Applica alla lettera la regola gia' fissata in 7.6.

    Vince il trattamento con punteggio logaritmico medio migliore su ENTRAMBE
    le stagioni, la cui differenza appaiata contro OGNI altro trattamento ha un
    intervallo bootstrap al 95 % che NON contiene lo zero, in entrambe le
    stagioni. In ogni altro caso l'esito e' inconcludente e resta T1.

    `gestione` seleziona la lettura delle estrazioni non ammissibili quando le
    tabelle ne contengono piu' di una."""
    if gestione is not None:
        if "gestione" in metriche.columns:
            metriche = metriche[metriche.gestione == gestione]
        if "gestione" in confronti.columns:
            confronti = confronti[confronti.gestione == gestione]
    stagioni = list(dict.fromkeys(metriche.stagione))
    migliori = {}
    for s in stagioni:
        sub = metriche[metriche.stagione == s]
        migliori[s] = str(sub.loc[sub.log_score_medio.idxmin(), "trattamento"])
    candidati = set(migliori.values())
    motivi = []
    if len(candidati) != 1:
        motivi.append("il trattamento con il punteggio logaritmico migliore "
                      f"cambia fra le stagioni: {migliori}")
        return {"esito": "inconcludente", "vincitore": None,
                "resta": "T1", "migliori_per_stagione": migliori,
                "motivi": motivi}
    cand = candidati.pop()
    tutti_esclusivi = True
    for s in stagioni:
        for _, r in confronti[confronti.stagione == s].iterrows():
            if cand not in (r["A"], r["B"]):
                continue
            if r["contiene_zero"]:
                tutti_esclusivi = False
                motivi.append(f"{s}: {r['A']} - {r['B']} ha IC95 "
                              f"[{r['ic_basso']:.6f}, {r['ic_alto']:.6f}] "
                              "che contiene lo zero")
    if not tutti_esclusivi:
        return {"esito": "inconcludente", "vincitore": None, "resta": "T1",
                "migliori_per_stagione": migliori, "motivi": motivi}
    return {"esito": "vincitore", "vincitore": cand,
            "resta": cand, "migliori_per_stagione": migliori,
            "motivi": ["punteggio logaritmico migliore su entrambe le stagioni "
                       "e intervallo bootstrap che esclude lo zero in tutti i "
                       "confronti che lo riguardano"]}


# --------------------------------------------------------------------------
# principale
# --------------------------------------------------------------------------

def main():
    OUT.mkdir(parents=True, exist_ok=True)
    log = Registro(OUT / "esecuzione.log")
    t_inizio = time.perf_counter()
    log("esperimento G1 — criterio: reports/CRITERI_L2_L3.md sezione 7.6")
    log(f"seme {SEME}, estrazioni {N_ESTRAZIONI}, scenari {N_SCENARI}, "
        f"bootstrap {N_BOOTSTRAP}")
    log(f"python {platform.python_version()}, numpy {np.__version__}, "
        f"pandas {pd.__version__}")

    partite = pd.read_parquet(PERCORSO_PARTITE)
    log(f"partite lette: {len(partite)} da {PERCORSO_PARTITE.name}")

    metriche, confronti, per_partita, scenari, dettagli = [], [], [], [], {}
    for i, stagione in enumerate(STAGIONI_BERSAGLIO):
        m, c, p, s, d = esegui_stagione(partite, stagione, i, log)
        metriche.append(m)
        confronti.append(c)
        per_partita.append(p)
        scenari.append(s)
        dettagli[stagione] = d

    metriche = pd.concat(metriche, ignore_index=True)
    confronti = pd.concat(confronti, ignore_index=True)
    per_partita = pd.concat(per_partita, ignore_index=True)
    scenari = pd.concat(scenari, ignore_index=True)

    metriche.to_csv(OUT / "metriche.csv", index=False)
    confronti.to_csv(OUT / "confronti_bootstrap.csv", index=False)
    per_partita.to_csv(OUT / "punteggi_per_partita.csv", index=False)
    scenari.to_csv(OUT / "scenari_comuni.csv", index=False)

    verdetti = {g: verdetto(metriche, confronti, gestione=g) for g in GESTIONI}
    v = verdetti[GESTIONE_PRIMARIA]
    for g in GESTIONI:
        marca = " (PRIMARIA)" if g == GESTIONE_PRIMARIA else ""
        log(f"VERDETTO 7.6 [gestione {g}{marca}]: {verdetti[g]['esito']} — "
            f"resta {verdetti[g]['resta']}")
        for motivo in verdetti[g]["motivi"]:
            log(f"  motivo: {motivo}")
    log(f"le due gestioni concordano: "
        f"{verdetti['generatore']['esito'] == verdetti['esclusione']['esito'] and verdetti['generatore']['resta'] == verdetti['esclusione']['resta']}")

    secondi = time.perf_counter() - t_inizio
    manifesto = {
        "esperimento": "G1 — calibrazione della distribuzione dei gol",
        "criterio": "reports/CRITERI_L2_L3.md sezione 7.6",
        "eseguito_il": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "seme": SEME,
        "n_estrazioni_parametri": N_ESTRAZIONI,
        "n_scenari_comuni": N_SCENARI,
        "n_bootstrap": N_BOOTSTRAP,
        "tolleranza_gradiente": TOLLERANZA_GRADIENTE,
        "jitter_base_cholesky": JITTER,
        "stagioni_bersaglio": list(STAGIONI_BERSAGLIO),
        "date_limite": {s: dettagli[s]["as_of"] for s in dettagli},
        "impronte_configurazione": {s: dettagli[s]["impronta"] for s in dettagli},
        "impronte_ingressi": {
            s: dettagli[s]["configurazione"]["impronte_ingressi"] for s in dettagli},
        "iperparametri": {
            s: dettagli[s]["configurazione"]["iperparametri"] for s in dettagli},
        "gestioni_estrazioni_non_ammissibili": list(GESTIONI),
        "gestione_primaria": GESTIONE_PRIMARIA,
        "dettagli_per_stagione": dettagli,
        "verdetto": v,
        "verdetti_per_gestione": verdetti,
        "versioni": {
            "python": platform.python_version(),
            "numpy": np.__version__,
            "pandas": pd.__version__,
            "scipy": __import__("scipy").__version__,
            "piattaforma": platform.platform(),
            "versione_procedura_partita": cfg.VERSIONE,
        },
        "tempi": {"secondi_totali": round(secondi, 2)},
        "picco_ram_mib": round(_picco_ram_mb(), 1),
        "file_prodotti": ["metriche.csv", "confronti_bootstrap.csv",
                          "punteggi_per_partita.csv", "scenari_comuni.csv",
                          "esecuzione.log", "MANIFESTO.json"],
    }
    (OUT / "MANIFESTO.json").write_text(
        json.dumps(cfg._canonico(manifesto), indent=2, ensure_ascii=False),
        encoding="utf-8")
    log(f"fatto in {secondi:.1f}s, picco RAM {manifesto['picco_ram_mib']} MiB")
    log(f"scritto in {OUT}")
    log.chiudi()


if __name__ == "__main__":
    main()
