"""Modello della singola partita: quanti gol segna ciascuna squadra.

E' il primo pezzo del cubo. Da qui escono porta inviolata (bonus al portiere e
modificatore difesa), numero di gol da ripartire fra i giocatori in campo e la
correlazione fra compagni che il simulatore attuale approssima con un unico
shock di squadra.

## Perche' questa parametrizzazione

    log lambda_casa   = mu + vantaggio_casa + attacco_casa   - difesa_ospite
    log lambda_ospite = mu +                  attacco_ospite - difesa_casa

`mu` e' il livello generale dei gol del campionato. Serve: senza intercetta,
con attacco e difesa vincolati a somma zero, la media dei gol in trasferta e'
costretta vicino a 1 qualunque cosa dicano i dati. E' l'errore che aveva la
prima versione di questo modello negli script d'indagine
(`scripts/indagine/l2_modello_partita.py` e `l2_modello_partita2.py`): su dati
sintetici con squadre equivalenti e 1,59 gol ospite di media, stimava 1,00.
Il test `tests/test_l2_partita.py::test_recupero_sintetico` fissa la proprieta'.

Attacco e difesa entrano nella verosimiglianza centrati (`a - media(a)`), e la
penalizzazione agisce sul vettore grezzo. Le due cose insieme danno tre
proprieta' utili:

  - il modello e' identificato: il livello sta tutto in `mu`;
  - all'ottimo la media dei coefficienti e' zero, senza vincoli espliciti;
  - la penalizzazione e' simmetrica: rinominare o riordinare le squadre non
    cambia le stime. La versione precedente penalizzava solo le prime n-1
    squadre, quindi l'ultima era di fatto non penalizzata e il risultato
    dipendeva dall'ordine dell'elenco.

## La correzione di Dixon e Coles

I punteggi bassi (0-0, 1-0, 0-1, 1-1) sono piu' frequenti di quanto due
Poisson indipendenti prevedano. La correzione moltiplica quelle quattro celle
per un fattore `tau` che dipende da un solo parametro `rho`.

Fatto che conta per la valutazione: **la correzione lascia intatte le
marginali**. La somma dei quattro scostamenti e' zero sia per riga sia per
colonna, quindi P(la squadra ospite non segna) e' identica con e senza
correzione. Un Brier calcolato sulla porta inviolata **non puo' distinguere**
Dixon-Coles da un Poisson semplice: e' esattamente lo stesso numero. Per
misurare la dipendenza servono il punteggio logaritmico sul risultato
congiunto, il Brier su 1X2, o la distribuzione dei punteggi esatti.
Il test `test_dixon_coles_preserva_marginali` fissa la proprieta'.

`rho` non e' libero: `tau` deve restare positivo su tutte e quattro le celle,
il che impone `rho < min(1, 1/(lambda*mu))` e `rho > -min(1/lambda, 1/mu)`.
Il modello non fa clipping silenzioso: se un vincolo viene violato lo dichiara
in `diagnostica["tau_non_valido"]`.

## Decadimento temporale

I pesi scendono con il tempo **realmente trascorso** (`exp(-xi * giorni)`), non
con il numero di giornate: rinvii e recuperi rendono le due cose diverse. `xi`
si sceglie su dati precedenti al periodo di prova, mai su quello di prova.

## Incertezza sulle forze

`campiona_parametri` estrae dalla normale approssimata all'ottimo (matrice di
informazione osservata). Serve a propagare l'incertezza sulle forze negli
scenari futuri senza usare risultati futuri: la stessa stagione simulata usa
un'estrazione, non il punto stimato.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np
from scipy.optimize import minimize

MAX_GOL = 12          # coda della distribuzione dei gol usata nelle probabilita'


# --------------------------------------------------------------------------
# correzione di Dixon e Coles
# --------------------------------------------------------------------------

def tau(x, y, lam, mu, rho):
    """Fattore moltiplicativo sulle quattro celle a punteggio basso."""
    x = np.asarray(x)
    y = np.asarray(y)
    out = np.ones(np.broadcast(x, y, lam, mu).shape, dtype=float)
    lam = np.broadcast_to(lam, out.shape)
    mu = np.broadcast_to(mu, out.shape)
    m = (x == 0) & (y == 0)
    out = np.where(m, 1.0 - lam * mu * rho, out)
    m = (x == 0) & (y == 1)
    out = np.where(m, 1.0 + lam * rho, out)
    m = (x == 1) & (y == 0)
    out = np.where(m, 1.0 + mu * rho, out)
    m = (x == 1) & (y == 1)
    out = np.where(m, 1.0 - rho, out)
    return out


def rho_ammissibile(lam, mu) -> tuple[float, float]:
    """Intervallo in cui `tau` resta positivo per ogni cella."""
    lam = np.asarray(lam, dtype=float)
    mu = np.asarray(mu, dtype=float)
    alto = float(min(1.0, np.min(1.0 / np.maximum(lam * mu, 1e-9))))
    basso = float(max(-np.min(1.0 / np.maximum(lam, 1e-9)),
                      -np.min(1.0 / np.maximum(mu, 1e-9))))
    return basso, alto


def matrice_risultato(lam: float, mu: float, rho: float = 0.0,
                      max_gol: int = MAX_GOL) -> np.ndarray:
    """Distribuzione congiunta P(gol casa = x, gol ospite = y).

    Non normalizza a forza: la correzione di Dixon e Coles conserva gia' la
    somma a 1 a meno della coda tagliata a `max_gol`. La coda mancante viene
    riversata sulla cella piu' alta, cosi' la somma e' esattamente 1 senza
    alterare le celle basse (che sono quelle che contano).
    """
    k = np.arange(max_gol + 1)
    fatt = np.array([float(math.factorial(i)) for i in k])
    px = np.exp(-lam) * lam ** k / fatt
    py = np.exp(-mu) * mu ** k / fatt
    P = np.outer(px, py)
    if rho != 0.0:
        X, Y = np.meshgrid(k, k, indexing="ij")
        P = P * tau(X, Y, lam, mu, rho)
    resto = 1.0 - P.sum()
    if resto > 0:
        P[-1, -1] += resto
    return P


# --------------------------------------------------------------------------
# stima
# --------------------------------------------------------------------------

@dataclass
class ModelloPartita:
    """Forze stimate + tutto quello che serve a giudicarle."""
    squadre: list
    mu: float
    casa: float
    att: np.ndarray
    dif: np.ndarray
    rho: float
    usa_dc: bool
    n_partite: int
    peso_totale: float
    convergenza: bool
    messaggio: str
    diagnostica: dict = field(default_factory=dict)
    _theta: np.ndarray | None = None
    _hess_inv: np.ndarray | None = None

    def indice(self) -> dict:
        return {s: i for i, s in enumerate(self.squadre)}

    def intensita(self, casa, trasferta) -> tuple[np.ndarray, np.ndarray]:
        """(lambda casa, lambda trasferta) per le partite indicate."""
        ix = self.indice()
        h = np.array([ix.get(s, -1) for s in np.atleast_1d(casa)])
        a = np.array([ix.get(s, -1) for s in np.atleast_1d(trasferta)])
        att = np.append(self.att, 0.0)          # squadra sconosciuta: forza media
        dif = np.append(self.dif, 0.0)
        lam = np.exp(self.mu + self.casa + att[h] - dif[a])
        m = np.exp(self.mu + att[a] - dif[h])
        return lam, m

    def p_porta_inviolata(self, casa, trasferta) -> tuple[np.ndarray, np.ndarray]:
        """(P(la casa non subisce), P(la trasferta non subisce)).

        Sono le marginali: la correzione di Dixon e Coles non le tocca."""
        lam, m = self.intensita(casa, trasferta)
        return np.exp(-m), np.exp(-lam)

    def p_esiti(self, casa, trasferta) -> np.ndarray:
        """Matrice (n partite x 3) con P(1), P(X), P(2)."""
        lam, m = self.intensita(casa, trasferta)
        out = np.zeros((len(lam), 3))
        for i in range(len(lam)):
            P = matrice_risultato(float(lam[i]), float(m[i]), self.rho)
            out[i, 0] = np.tril(P, -1).sum()
            out[i, 1] = np.trace(P)
            out[i, 2] = np.triu(P, 1).sum()
        return out

    def log_score_risultato(self, casa, trasferta, gol_casa, gol_trasferta) -> np.ndarray:
        """-log P(risultato osservato): la metrica che vede la dipendenza."""
        lam, m = self.intensita(casa, trasferta)
        gc = np.asarray(gol_casa, dtype=int)
        gt = np.asarray(gol_trasferta, dtype=int)
        out = np.zeros(len(lam))
        for i in range(len(lam)):
            P = matrice_risultato(float(lam[i]), float(m[i]), self.rho)
            x = min(int(gc[i]), P.shape[0] - 1)
            y = min(int(gt[i]), P.shape[1] - 1)
            out[i] = -np.log(max(P[x, y], 1e-12))
        return out

    def campiona_parametri(self, rng: np.random.Generator, n: int = 1) -> list:
        """n copie del modello con forze estratte dalla normale approssimata.

        Serve a propagare l'incertezza sulle forze negli scenari futuri. Se la
        matrice di informazione non e' disponibile ritorna n copie del punto
        stimato, dichiarandolo in `diagnostica`."""
        if self._hess_inv is None or self._theta is None:
            fuori = []
            for _ in range(n):
                c = ModelloPartita(**{k: v for k, v in self.__dict__.items()})
                c.diagnostica = dict(self.diagnostica, incertezza_forze="non disponibile")
                fuori.append(c)
            return fuori
        L = np.linalg.cholesky(self._hess_inv
                               + 1e-10 * np.eye(len(self._theta)))
        fuori = []
        for _ in range(n):
            th = self._theta + L @ rng.standard_normal(len(self._theta))
            fuori.append(self._da_theta(th))
        return fuori

    def _da_theta(self, th: np.ndarray) -> "ModelloPartita":
        n = len(self.squadre)
        a = th[:n]
        d = th[n:2 * n]
        c = ModelloPartita(
            squadre=self.squadre, mu=float(th[2 * n]), casa=float(th[2 * n + 1]),
            att=a - a.mean(), dif=d - d.mean(),
            rho=float(th[2 * n + 2]) if self.usa_dc else 0.0,
            usa_dc=self.usa_dc, n_partite=self.n_partite,
            peso_totale=self.peso_totale, convergenza=self.convergenza,
            messaggio=self.messaggio, diagnostica=dict(self.diagnostica))
        return c


def pesi_decadimento(date, as_of, xi: float) -> np.ndarray:
    """exp(-xi * giorni trascorsi). `xi` in unita' di 1/giorno.

    Riferimento: il decadimento e' sul tempo davvero passato, non sul numero
    di giornate, perche' rinvii e soste rendono le due misure diverse."""
    d = np.asarray(date, dtype="datetime64[D]")
    fine = np.datetime64(as_of, "D")
    giorni = (fine - d).astype(float)
    return np.exp(-xi * np.maximum(giorni, 0.0))


def _neg_loglik_e_gradiente(th, h, a, x, y, w, n, lam_pen, usa_dc,
                            prior_att, prior_dif):
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
    ll = w * (-lam + x * loglam - m + y * logmu)

    # derivate rispetto a log lambda e log mu
    dlam = w * (x - lam)
    dmu_ = w * (y - m)
    drho = 0.0
    if usa_dc:
        t = tau(x, y, lam, m, rho)
        cattivi = t <= 0
        if cattivi.any():
            return 1e12, np.zeros_like(th)      # zona non ammissibile
        ll = ll + w * np.log(t)
        c00 = (x == 0) & (y == 0)
        c01 = (x == 0) & (y == 1)
        c10 = (x == 1) & (y == 0)
        c11 = (x == 1) & (y == 1)
        dl = np.zeros_like(lam)
        dm = np.zeros_like(lam)
        dr = np.zeros_like(lam)
        dl[c00] = -lam[c00] * m[c00] * rho / t[c00]
        dm[c00] = dl[c00]
        dr[c00] = -lam[c00] * m[c00] / t[c00]
        dl[c01] = lam[c01] * rho / t[c01]
        dr[c01] = lam[c01] / t[c01]
        dm[c10] = m[c10] * rho / t[c10]
        dr[c10] = m[c10] / t[c10]
        dr[c11] = -1.0 / t[c11]
        dlam = dlam + w * dl
        dmu_ = dmu_ + w * dm
        drho = float(np.sum(w * dr))

    # gradiente rispetto ai parametri
    g_att_c = np.zeros(n)
    g_dif_c = np.zeros(n)
    np.add.at(g_att_c, h, dlam)
    np.add.at(g_att_c, a, dmu_)
    np.add.at(g_dif_c, a, -dlam)
    np.add.at(g_dif_c, h, -dmu_)
    # centratura: dA_i/da_j = delta_ij - 1/n
    g_att = g_att_c - g_att_c.mean()
    g_dif = g_dif_c - g_dif_c.mean()
    g_mu = float(np.sum(dlam) + np.sum(dmu_))
    g_casa = float(np.sum(dlam))

    pen = lam_pen * (np.sum((att_raw - prior_att) ** 2)
                     + np.sum((dif_raw - prior_dif) ** 2))
    g_att = g_att - 2 * lam_pen * (att_raw - prior_att)
    g_dif = g_dif - 2 * lam_pen * (dif_raw - prior_dif)

    obiettivo = -(float(ll.sum()) - pen)
    grad = -np.concatenate([g_att, g_dif, [g_mu, g_casa],
                            [drho] if usa_dc else []])
    return obiettivo, grad


def stima(casa, trasferta, gol_casa, gol_trasferta, squadre=None, pesi=None,
          lam_pen: float = 2.0, usa_dc: bool = True,
          prior_att: dict | None = None, prior_dif: dict | None = None,
          con_incertezza: bool = False) -> ModelloPartita:
    """Stima il modello sulle partite date.

    `lam_pen` e' la forza della penalizzazione verso il prior (0 per nessuna).
    `prior_att`/`prior_dif` sono medie a priori per squadra: servono alle
    neopromosse, che hanno poche partite in campionato e senza prior prendono
    forze estreme.
    """
    casa = np.asarray(casa)
    trasferta = np.asarray(trasferta)
    x = np.asarray(gol_casa, dtype=float)
    y = np.asarray(gol_trasferta, dtype=float)
    if squadre is None:
        squadre = sorted(set(casa) | set(trasferta))
    squadre = list(squadre)
    ix = {s: i for i, s in enumerate(squadre)}
    n = len(squadre)
    h = np.array([ix[s] for s in casa])
    a = np.array([ix[s] for s in trasferta])
    w = np.ones(len(x)) if pesi is None else np.asarray(pesi, dtype=float)
    pa = np.array([float((prior_att or {}).get(s, 0.0)) for s in squadre])
    pd_ = np.array([float((prior_dif or {}).get(s, 0.0)) for s in squadre])

    n_par = 2 * n + 2 + (1 if usa_dc else 0)
    th0 = np.zeros(n_par)
    th0[2 * n] = float(np.log(max((x.mean() + y.mean()) / 2, 0.2)))   # mu
    th0[2 * n + 1] = 0.2                                              # vantaggio casa
    if usa_dc:
        th0[-1] = -0.03
    # rho: limite prudente, verificato dopo la stima sui lambda effettivi
    bounds = [(-3, 3)] * (2 * n) + [(-2, 2), (-1, 1)]
    if usa_dc:
        bounds.append((-0.4, 0.4))

    r = minimize(_neg_loglik_e_gradiente, th0, jac=True, method="L-BFGS-B",
                 bounds=bounds, options={"maxiter": 2000, "ftol": 1e-12},
                 args=(h, a, x, y, w, n, lam_pen, usa_dc, pa, pd_))
    th = r.x
    att_raw, dif_raw = th[:n], th[n:2 * n]
    mod = ModelloPartita(
        squadre=squadre, mu=float(th[2 * n]), casa=float(th[2 * n + 1]),
        att=att_raw - att_raw.mean(), dif=dif_raw - dif_raw.mean(),
        rho=float(th[-1]) if usa_dc else 0.0, usa_dc=usa_dc,
        n_partite=len(x), peso_totale=float(w.sum()),
        convergenza=bool(r.success), messaggio=str(r.message),
        _theta=th)

    lam, m = mod.intensita(casa, trasferta)
    basso, alto = rho_ammissibile(lam, m)
    t = tau(x, y, lam, m, mod.rho) if usa_dc else np.ones(len(x))
    mod.diagnostica = {
        "lam_pen": lam_pen,
        "gol_casa_medi_osservati": float(np.average(x, weights=w)),
        "gol_casa_medi_stimati": float(np.average(lam, weights=w)),
        "gol_ospite_medi_osservati": float(np.average(y, weights=w)),
        "gol_ospite_medi_stimati": float(np.average(m, weights=w)),
        "rho_ammissibile": [round(basso, 4), round(alto, 4)],
        "tau_non_valido": int((t <= 0).sum()),
        "iterazioni": int(r.nit),
    }
    if con_incertezza:
        mod._hess_inv = _informazione_inversa(th, h, a, x, y, w, n, lam_pen,
                                              usa_dc, pa, pd_)
    return mod


def _informazione_inversa(th, *args) -> np.ndarray | None:
    """Inversa dell'hessiana per differenze finite del gradiente analitico."""
    k = len(th)
    H = np.zeros((k, k))
    eps = 1e-5
    for i in range(k):
        p = th.copy()
        p[i] += eps
        _, gp = _neg_loglik_e_gradiente(p, *args)
        p[i] -= 2 * eps
        _, gm = _neg_loglik_e_gradiente(p, *args)
        H[:, i] = (gp - gm) / (2 * eps)
    H = 0.5 * (H + H.T)
    try:
        val, vec = np.linalg.eigh(H)
        val = np.maximum(val, 1e-6)
        return vec @ np.diag(1.0 / val) @ vec.T
    except np.linalg.LinAlgError:
        return None


def campiona_risultati(lam, mu, rho, rng: np.random.Generator,
                       n_sims: int = 1, u: np.ndarray | None = None) -> np.ndarray:
    """Estrae i risultati di un elenco di partite.

    Ritorna un array (n_sims, n_partite, 2) con gol casa e gol ospite. La
    distribuzione congiunta di ogni partita si costruisce una volta sola e si
    campiona per inversione della cumulativa: cosi' `u` puo' arrivare da fuori
    (numeri casuali comuni indicizzati per scenario e per partita) e due rose
    confrontate vedono gli stessi risultati.
    """
    lam = np.atleast_1d(np.asarray(lam, dtype=float))
    mu = np.atleast_1d(np.asarray(mu, dtype=float))
    n = len(lam)
    if u is None:
        u = rng.random((n_sims, n))
    else:
        u = np.asarray(u, dtype=float).reshape(-1, n)
        n_sims = u.shape[0]
    fuori = np.zeros((n_sims, n, 2), dtype=np.int16)
    larghezza = MAX_GOL + 1
    for i in range(n):
        P = matrice_risultato(float(lam[i]), float(mu[i]), rho).ravel()
        P = np.maximum(P, 0.0)
        cum = np.cumsum(P / P.sum())
        k = np.searchsorted(cum, u[:, i], side="right")
        k = np.minimum(k, cum.size - 1)
        fuori[:, i, 0] = k // larghezza
        fuori[:, i, 1] = k % larghezza
    return fuori
