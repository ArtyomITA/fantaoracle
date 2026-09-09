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

## L'ammissibilita' vale su ogni partita simulata, non solo sul punto stimato

L'intervallo ammissibile dipende dalle intensita' della **singola partita**, e
le intensita' delle partite simulate vengono dai parametri estratti, non dal
punto stimato. Sul caso riprodotto in `data/l2/r3/riproduzione.json` (modello
2024-25, cutoff 2024-08-16, seme 20260908, 200 estrazioni) il punto stimato ha
`rho` = -0,0605 dentro [-0,25; 0,2783] e `tau_non_valido` = 0, mentre 13
estrazioni su 200 e 194 combinazioni partita-estrazione su 76.000 finiscono
fuori: la verifica sul punto stimato non copre il percorso.

**Strategia scelta: proiezione di `rho` sull'intervallo ammissibile della
singola partita, contata ed esposta.** Motivi misurati, in
`data/l2/r3/verifica_strategie.json`:

  - la riparazione precedente (`np.maximum(P, 0)` piu' rinormalizzazione, in
    `campiona_risultati` e nel generatore) **rompe** l'identita' delle
    marginali su cui si regge tutto il calcolo analitico della coda: scarto
    fino a 2,94e-4, mediana 3,40e-6. La proiezione di `rho` la conserva entro
    3,3e-16, perche' l'invarianza di Sarmanov vale per **ogni** `rho`;
  - il rigetto e la riestrazione (che `configurazione.verifica_ammissibilita`
    prescrive nella sua docstring) scarterebbero il 6,5 % delle estrazioni, e
    proprio quelle a intensita' piu' alta: le combinazioni non ammissibili
    hanno intensita' mediana 11,2 contro 1,62 di tutte le combinazioni.
    Rigettarle abbasserebbe la coda scartando le estrazioni scomode, cioe' la
    mossa che il protocollo vieta. In piu' la regione di rigetto dipende dal
    calendario, quindi la stessa estrazione sarebbe accettata per un calendario
    e rigettata per un altro: la legge di campionamento smetterebbe di essere
    quella dichiarata e diventerebbe funzione delle partite da simulare;
  - vincolare `rho` nell'ottimizzazione non tocca il problema: il punto stimato
    e' gia' ammissibile ovunque, e la non ammissibilita' nasce dalle intensita'
    estratte, non da `rho`.

La proiezione **cambia la dipendenza** sulla partita proiettata, e questo va
letto per quello che e': su quelle combinazioni la legge di Dixon-Coles non
esiste, e la proiezione e' la scelta di restare sul bordo del suo dominio
invece di uscirne. Lo scarto fra la vecchia riparazione e la nuova vale al
massimo 5,9e-4 in variazione totale; il conto delle proiezioni sta nel
`registro` e in `Cubo.diagnostica["campionamento_gol"]`.

## Il supporto si adatta all'intensita'

Con `max_gol` fisso a dodici la distribuzione campionata non e' quella
dichiarata appena l'intensita' cresce: alle intensita' estratte nel caso
riprodotto la massa buttata via arriva a 0,83 e la matrice diventa quasi una
massa puntuale sul 12-12. Il supporto ora si sceglie per intensita' in modo che
la massa fuori resti sotto `TOL_SUPPORTO`; `MAX_GOL` resta il minimo garantito,
e un `max_gol` esplicito continua a essere rispettato.


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
from scipy.special import gammaln

MAX_GOL = 12          # supporto MINIMO della distribuzione dei gol
TOL_SUPPORTO = 1e-12  # massa massima ammessa fuori dal supporto
MAX_GOL_LIMITE = 400  # tetto duro sul supporto adattivo
MARGINE_RHO = 1e-9    # margine relativo con cui `rho` resta dentro il dominio


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


def rho_effettivo(lam: float, mu: float, rho: float,
                  margine: float = MARGINE_RHO) -> tuple[float, float]:
    """`rho` riportato dentro l'intervallo ammissibile di QUESTA partita.

    Ritorna `(rho_usato, scarto)`, dove `scarto` e' `|rho - rho_usato|` ed e'
    zero quando `rho` era gia' ammissibile. Nessuna proiezione avviene in
    silenzio: chi chiama riceve lo scarto e `matrice_risultato` lo somma nel
    `registro`.

    Lo zero e' sempre interno all'intervallo — `alto = min(1, 1/(lam*mu)) > 0`
    e `basso < 0` — quindi la proiezione e' sempre definita.
    """
    basso, alto = rho_ammissibile(lam, mu)
    lo = basso + margine * max(1.0, abs(basso))
    hi = alto - margine * max(1.0, abs(alto))
    if lo >= hi:                      # non puo' capitare con lam, mu finiti
        return 0.0, abs(rho)
    r = float(min(max(float(rho), lo), hi))
    return r, abs(r - float(rho))


def supporto_necessario(lam: float, mu: float, tol: float = TOL_SUPPORTO,
                        minimo: int = MAX_GOL,
                        massimo: int = MAX_GOL_LIMITE) -> int:
    """Il piu' piccolo `K >= minimo` con `P(G > K) < tol` per entrambe le squadre.

    Il troncamento non e' un dettaglio numerico quando l'intensita' cresce:
    misurato sul caso riprodotto, la massa oltre dodici gol vale 1,9e-8
    all'intensita' mediana (1,62), 8,3e-3 al 99-esimo percentile (5,95), 0,83 al
    99,9-esimo (16,3) e 1,0 all'intensita' massima estratta (46,70). Con un
    supporto fisso la distribuzione campionata a quelle intensita' e' quasi una
    massa puntuale sul risultato d'angolo, cioe' non e' quella dichiarata.

    Il tetto `massimo` esiste per non allocare matrici illimitate: se non basta,
    `matrice_risultato` registra `supporto_insufficiente` e la massa residua
    invece di tacere.
    """
    m = max(float(lam), float(mu))
    if not np.isfinite(m) or m <= 0:
        return int(minimo)
    # partenza da una maggiorazione di Chernoff, poi si stringe leggendo la
    # coda dell'array: niente chiamate scalari a scipy, che costavano 437 us
    # contro i 316 us dell'intera matrice
    L = math.log(1.0 / max(tol, 1e-300))
    k = int(math.ceil(m + math.sqrt(2.0 * m * L) + L)) + 2
    while True:
        k = int(min(max(k, minimo), massimo))
        p = _pmf_poisson(m, k)
        if 1.0 - p.sum() < tol:
            # l'array copre gia' la distribuzione: si stringe al piu' piccolo K
            coda = np.cumsum(p[::-1])[::-1]    # coda[j] = P(X >= j)
            sotto = np.nonzero(coda < tol)[0]
            if sotto.size:
                return int(min(max(int(sotto[0]) - 1, minimo), massimo))
            return int(k)
        if k >= massimo:
            return int(massimo)                # tetto raggiunto: lo dira' il registro
        k = int(k * 1.5) + 4


def _pmf_poisson(lam: float, k_max: int) -> np.ndarray:
    """pmf di Poisson su 0..k_max, in log per non traboccare a lambda grande."""
    k = np.arange(k_max + 1)
    if lam <= 0:
        p = np.zeros(k_max + 1)
        p[0] = 1.0
        return p
    return np.exp(-lam + k * math.log(lam) - gammaln(k + 1.0))


def matrice_risultato(lam: float, mu: float, rho: float = 0.0,
                      max_gol: int | None = None,
                      margine_rho: float = MARGINE_RHO,
                      registro: dict | None = None) -> np.ndarray:
    """Distribuzione congiunta P(gol casa = x, gol ospite = y).

    La correzione di Dixon e Coles conserva le marginali: la congiunta e' della
    famiglia di Sarmanov, `p1(x) p2(y) [1 + omega q1(x) q2(y)]` con
    `q(x) = -lambda` se `x = 0`, `1` se `x = 1`, `0` altrove, e l'invarianza
    segue da `E[q(X)] = 0` sotto Poisson. Vale per ogni `rho`: l'ammissibilita'
    serve alla positivita', non all'invarianza.

    Il troncamento a `max_gol` rompe quell'identita' se la massa mancante viene
    riversata su una cella sola. Misurato dal ramo di ricerca: scaricare
    `1 - somma` sulla cella `(max_gol, max_gol)` gonfia la marginale dell'altra
    squadra, con uno scarto relativo su `P(G >= 6)` di +1,2e-6 alle intensita'
    che usiamo, ma fino a +9,6% a `(6,00; 3,00)` e +23,3% a `(8,00; 4,00)`.

    Qui la massa mancante si distribuisce invece **in proporzione** alle celle
    esistenti, cioe' si rinormalizza. Con `q2` diverso da zero solo in `y = 0` e
    `y = 1`, che stanno dentro qualunque supporto, la somma troncata
    `sum_y p2(y) q2(y)` resta esattamente zero: quindi la rinormalizzazione
    conserva l'identita' delle marginali **esattamente**, non a meno di un
    residuo, per ogni `max_gol >= 1`.

    Due cose che la versione precedente non faceva:

      - `rho` viene proiettato sull'intervallo ammissibile della partita, per
        cui la matrice e' non negativa per costruzione e nessun chiamante ha
        piu' bisogno di `np.maximum(P, 0)`, che invece le marginali le rompeva
        (fino a 2,94e-4 sul caso riprodotto);
      - `max_gol = None` sceglie il supporto in funzione dell'intensita', in
        modo che la massa fuori resti sotto `TOL_SUPPORTO`. Un intero esplicito
        continua a essere rispettato, e allora la massa fuori viene registrata.

    `registro`, se dato, e' un dizionario aggiornato sul posto con i conteggi:
    proiezioni di `rho`, scarto massimo, massa fuori dal supporto, celle
    negative residue. Serve a esporre la riparazione invece di nasconderla.
    """
    lam = float(lam)
    mu = float(mu)
    if max_gol is None:
        k_max = supporto_necessario(lam, mu)
        richiesto = None
    else:
        k_max = int(max_gol)
        richiesto = k_max
    rho_u, scarto = rho_effettivo(lam, mu, rho, margine_rho)

    px = _pmf_poisson(lam, k_max)
    py = _pmf_poisson(mu, k_max)
    P = np.outer(px, py)
    if rho_u != 0.0:
        k = np.arange(k_max + 1)
        X, Y = np.meshgrid(k, k, indexing="ij")
        P = P * tau(X, Y, lam, mu, rho_u)
    somma = P.sum()
    if somma > 0:
        P = P / somma

    if registro is not None:
        # massa fuori dal supporto letta dalle marginali gia' costruite:
        # e' la stessa quantita' di 1 - cdf(k) cdf(k), senza chiamate a scipy
        fuori = float(1.0 - px.sum() * py.sum())
        neg = float(-P[P < 0].sum()) if P.min() < 0 else 0.0
        registro["chiamate"] = registro.get("chiamate", 0) + 1
        if scarto > 0:
            registro["rho_proiettato"] = registro.get("rho_proiettato", 0) + 1
        registro["rho_scarto_massimo"] = max(
            registro.get("rho_scarto_massimo", 0.0), scarto)
        registro["supporto_massimo"] = max(
            registro.get("supporto_massimo", 0), k_max)
        registro["massa_fuori_supporto_massima"] = max(
            registro.get("massa_fuori_supporto_massima", 0.0), fuori)
        registro["intensita_massima"] = max(
            registro.get("intensita_massima", 0.0), max(lam, mu))
        if neg > 0:
            registro["celle_negative"] = registro.get("celle_negative", 0) + 1
            registro["massa_negativa_massima"] = max(
                registro.get("massa_negativa_massima", 0.0), neg)
        if richiesto is None and k_max >= MAX_GOL_LIMITE and fuori >= TOL_SUPPORTO:
            registro["supporto_insufficiente"] = (
                registro.get("supporto_insufficiente", 0) + 1)
    return P


def pmf_risultato(lam: float, mu: float, rho: float, x, y,
                  margine_rho: float = MARGINE_RHO) -> np.ndarray:
    """P(gol casa = x, gol ospite = y) in forma chiusa, senza troncamento.

    E' la legge di Dixon-Coles intera: `p1(x) p2(y) tau(x, y)`. Somma a uno su
    tutto il quadrante per l'invarianza di Sarmanov, quindi non serve
    normalizzare e non esiste un «fuori supporto» da definire a mano. La usa il
    log-score, che altrimenti dovrebbe schiacciare i risultati oltre il
    troncamento sull'ultima cella — un valore senza definizione probabilistica.
    """
    rho_u, _ = rho_effettivo(lam, mu, rho, margine_rho)
    x = np.asarray(x, dtype=int)
    y = np.asarray(y, dtype=int)
    px = np.exp(-lam + x * math.log(lam) - gammaln(x + 1.0))
    py = np.exp(-mu + y * math.log(mu) - gammaln(y + 1.0))
    return px * py * tau(x, y, lam, mu, rho_u)


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
        """-log P(risultato osservato): la metrica che vede la dipendenza.

        Il bersaglio e' la legge di Dixon-Coles **intera** (`pmf_risultato`),
        non la matrice troncata. La versione precedente faceva
        `x = min(gol, P.shape[0] - 1)`: un 14-2 riceveva la probabilita' esatta
        del 12-2, che non e' ne' P(14, 2) ne' P(X >= 12, Y = 2), e il punteggio
        smetteva di essere monotono nei gol. Qui non esiste un fuori supporto da
        definire, e il divario con la legge davvero campionata — quella troncata
        dal supporto adattivo — resta sotto `TOL_SUPPORTO` per costruzione.
        """
        lam, m = self.intensita(casa, trasferta)
        gc = np.asarray(gol_casa, dtype=int)
        gt = np.asarray(gol_trasferta, dtype=int)
        out = np.zeros(len(lam))
        for i in range(len(lam)):
            p = float(pmf_risultato(float(lam[i]), float(m[i]), self.rho,
                                    int(gc[i]), int(gt[i])))
            out[i] = -np.log(max(p, 1e-300))
        return out

    def campiona_parametri(self, rng: np.random.Generator, n: int = 1,
                           partite: tuple | None = None) -> list:
        """n copie del modello con forze estratte dalla normale approssimata.

        Serve a propagare l'incertezza sulle forze negli scenari futuri. Se la
        matrice di informazione non e' disponibile ritorna n copie del punto
        stimato, dichiarandolo in `diagnostica`.

        `partite`, se dato, e' la coppia `(casa, trasferta)` delle partite che
        verranno davvero simulate: ogni estrazione viene allora controllata su
        quelle intensita', non sul punto stimato, e il verdetto finisce nella
        `diagnostica` della copia. E' il controllo che mancava: sul caso
        riprodotto il punto stimato e' ammissibile ovunque mentre 13 estrazioni
        su 200 non lo sono.

        L'estrazione **non viene rigettata**: il rigetto scarterebbe proprio le
        estrazioni a intensita' alta e cambierebbe la legge campionata (si veda
        la motivazione in testa al modulo). La riparazione avviene a valle, in
        `matrice_risultato`, ed e' contata.
        """
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
        for i in range(n):
            th = self._theta + L @ rng.standard_normal(len(self._theta))
            c = self._da_theta(th)
            c.diagnostica["estrazione"] = i
            c.diagnostica["rho_estratto"] = float(c.rho)
            if partite is not None:
                c.diagnostica.update(c.controlla_partite(*partite))
            fuori.append(c)
        return fuori

    def controlla_partite(self, casa, trasferta) -> dict:
        """Ammissibilita' e supporto sulle partite che verranno simulate.

        Nessun effetto collaterale: misura e basta. `partite_non_ammissibili`
        conta le partite in cui `rho` di QUESTA copia esce dall'intervallo
        della partita, `rho_scarto_massimo` di quanto verra' proiettato."""
        lam, m = self.intensita(casa, trasferta)
        cattive = 0
        scarto = 0.0
        for i in range(len(lam)):
            _, s = rho_effettivo(float(lam[i]), float(m[i]), self.rho)
            if s > 0:
                cattive += 1
                scarto = max(scarto, s)
        intensita_max = float(max(lam.max(), m.max()))
        return {
            "partite_controllate": int(len(lam)),
            "partite_non_ammissibili": int(cattive),
            "rho_dentro_ammissibile": bool(cattive == 0),
            "rho_scarto_massimo": float(scarto),
            "intensita_massima": intensita_max,
            "supporto_necessario_massimo": int(
                supporto_necessario(intensita_max, intensita_max)),
        }

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
    # ammissibilita' partita per partita, non solo sull'intervallo comune:
    # l'intervallo comune e' il piu' stretto e nasconde quante partite
    # singole sarebbero fuori con un `rho` diverso da quello stimato
    non_amm = sum(1 for i in range(len(lam))
                  if rho_effettivo(float(lam[i]), float(m[i]), mod.rho)[1] > 0)
    mod.diagnostica = {
        "lam_pen": lam_pen,
        "gol_casa_medi_osservati": float(np.average(x, weights=w)),
        "gol_casa_medi_stimati": float(np.average(lam, weights=w)),
        "gol_ospite_medi_osservati": float(np.average(y, weights=w)),
        "gol_ospite_medi_stimati": float(np.average(m, weights=w)),
        "rho_ammissibile": [round(basso, 4), round(alto, 4)],
        "tau_non_valido": int((t <= 0).sum()),
        "partite_non_ammissibili_al_punto": int(non_amm),
        "intensita_massima_addestramento": float(max(lam.max(), m.max())),
        "supporto_necessario_addestramento": int(
            supporto_necessario(float(max(lam.max(), m.max())),
                                float(max(lam.max(), m.max())))),
        "iterazioni": int(r.nit),
    }
    if con_incertezza:
        reg: dict = {}
        mod._hess_inv = _informazione_inversa(th, h, a, x, y, w, n, lam_pen,
                                              usa_dc, pa, pd_, registro=reg)
        mod.diagnostica["hessiana"] = reg
    return mod


def _informazione_inversa(th, *args, registro: dict | None = None) -> np.ndarray | None:
    """Inversa dell'hessiana per differenze finite del gradiente analitico.

    Che cosa **e'** questo oggetto, dichiarato invece che sottinteso: e'
    l'inversa dell'hessiana di una verosimiglianza **pesata** (decadimento
    temporale `exp(-xi * giorni)`) e **penalizzata** (`lam_pen` sul vettore
    grezzo). Letta come approssimazione di Laplace di una posteriore, la
    penalizzazione e' un prior gaussiano di scarto `1/sqrt(2*lam_pen)` sul
    vettore grezzo, e i pesi la rendono una posteriore temperata. Letta come
    incertezza frequentista non e' corretta: servirebbe il sandwich
    `H^-1 J H^-1` con `J = sum w^2 s s'`, perche' con pesi diversi da uno
    l'uguaglianza fra informazione attesa e varianza dello score cade. Le due
    letture non chiedono la stessa correzione, e questo modulo non ne sceglie
    una: registra il fatto.

    `np.maximum(val, 1e-6)` alza gli autovalori troppo piccoli. Quanti e di
    quanto finisce in `registro`, cosi' non e' piu' un aggiustamento invisibile.
    """
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
    except np.linalg.LinAlgError:
        return None
    corretti = np.maximum(val, 1e-6)
    if registro is not None:
        registro.update({
            "autovalori_min": float(val.min()),
            "autovalori_max": float(val.max()),
            "autovalori_negativi": int((val < 0).sum()),
            "autovalori_alzati": int((val < 1e-6).sum()),
            "autovalori_alzati_valori": [float(v) for v in val[val < 1e-6]][:20],
            "numero_condizione": float(val.max() / max(abs(val.min()), 1e-300)),
            "sd_massima": float(np.sqrt(1.0 / corretti.min())),
            "verosimiglianza": "pesata e penalizzata",
            "lettura": ("H^-1 e' l'approssimazione di Laplace di una posteriore "
                        "temperata dai pesi, non un'incertezza frequentista: "
                        "quella richiederebbe il sandwich H^-1 J H^-1"),
        })
    return vec @ np.diag(1.0 / corretti) @ vec.T


def campiona_risultati(lam, mu, rho, rng: np.random.Generator,
                       n_sims: int = 1, u: np.ndarray | None = None,
                       registro: dict | None = None) -> np.ndarray:
    """Estrae i risultati di un elenco di partite.

    Ritorna un array (n_sims, n_partite, 2) con gol casa e gol ospite. La
    distribuzione congiunta di ogni partita si costruisce una volta sola e si
    campiona per inversione della cumulativa: cosi' `u` puo' arrivare da fuori
    (numeri casuali comuni indicizzati per scenario e per partita) e due rose
    confrontate vedono gli stessi risultati.

    Il `np.maximum(P, 0)` che stava qui non c'e' piu': con `rho` proiettato la
    matrice e' non negativa per costruzione, e quel clipping rompeva le
    marginali (fino a 2,94e-4 sul caso riprodotto) proprio sulle estrazioni che
    lo richiedevano. La larghezza del supporto ora dipende dalla partita, quindi
    si legge dalla matrice invece di essere `MAX_GOL + 1`.
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
    for i in range(n):
        P = matrice_risultato(float(lam[i]), float(mu[i]), rho,
                              registro=registro)
        larghezza = P.shape[1]
        cum = np.cumsum(P.ravel())
        k = np.searchsorted(cum, u[:, i], side="right")
        k = np.minimum(k, cum.size - 1)
        fuori[:, i, 0] = k // larghezza
        fuori[:, i, 1] = k % larghezza
    return fuori
