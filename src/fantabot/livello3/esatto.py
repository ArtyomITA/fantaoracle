"""Formulazione esatta di P(primo posto) come programma lineare misto-intero.

Serve a due cose, e nessuna delle due e' «risolvere il problema vero»:

1. **verificare la ricerca**: su istanze piccole si risolve all'ottimo e si
   confronta il risultato con l'enumerazione completa. Se la formulazione, la
   ricerca e l'enumerazione danno tre risposte diverse, almeno due sono
   sbagliate;
2. **mostrare dove il problema smette di essere lineare**, con la prova, invece
   di dirlo a parole.

## La formulazione

Ipotesi sotto cui e' esatta, tutte verificate dal codice prima di risolvere:

  H1. la rosa coincide con la formazione: le quote sommano a undici e tutti
      prendono voto in ogni giornata. Senza, il punteggio dipende da quali
      undici l'allenatore schiera, che e' una decisione **non anticipativa**
      dentro lo scenario: non e' rappresentabile con variabili di acquisto;
  H2. gli avversari sono fissati: le loro rose non dipendono da cosa compriamo.
      Nell'asta vera non e' cosi';
  H3. gli scenari sono un campione finito dato (SAA).

Con queste ipotesi:

    x_i in {0,1}                        compriamo il giocatore i
    P[w,d] = somma_i x_i p[i,w,d]       punti nostri, scenario w, giornata d
    G[w,d] = gol da fasce di P[w,d]     soglia 66, poi uno ogni 6
    vinciamo la giornata  <=>  G[w,d] > G_avv[w,d]  (costante: l'avversario e' fissato)
    L[w] = somma_d (3 * vittoria + 1 * pareggio)
    y[w] = 1  <=>  L[w] > L_avv[w], oppure L[w] = L_avv[w] e punti totali maggiori

    massimizza  somma_w y[w]

I gol da fasce diventano lineari perche' l'avversario e' fissato: «facciamo
almeno k gol» e' la condizione `P >= 66 + 6(k-1)`, cioe' una sola soglia. Serve
un indicatore per «vinciamo la giornata» e uno per «pareggiamo», con un big-M
pari all'intervallo dei punteggi possibili.

## Dove smette di funzionare

- **H1 cade** appena la rosa e' piu' grande della formazione: la scelta degli
  undici e' una decisione che dipende dallo scenario e che deve usare solo
  l'informazione precedente. Rappresentarla richiederebbe variabili per
  giornata e per scenario con vincoli di non anticipazione, e il numero di
  variabili cresce come rose x scenari x giornate.
- **H2 cade** in un'asta: le rose avversarie dipendono da cosa lasciamo. Il
  problema diventa un gioco, non un programma.
- Anche con H1 e H2, il numero di binari e' 2 x scenari x giornate: con 200
  scenari e 38 giornate sono 15.200 binari solo per gli esiti, piu' quelli
  della rosa. Non e' la dimensione che lo rende impraticabile, e' la
  combinazione con i due punti sopra.

Per questo il Livello 3 usa la **ricerca su candidate per l'obiettivo SAA** e
non questa formulazione: qui c'e' per essere il metro di paragone dove il
paragone si puo' fare.
"""
from __future__ import annotations

import numpy as np
import pulp

from .valutatore import Regole


def _gol_da_punti(p: float, soglia: int, passo: int) -> int:
    return 0 if p < soglia else int((p - soglia) // passo) + 1


def _soglia_per_gol(k: int, soglia: int, passo: int) -> float:
    """Punteggio minimo per fare almeno k gol.

    Per k <= 0 la condizione e' sempre vera e **non ha una soglia**: chiunque
    fa almeno zero gol. Chi restituiva qui un numero molto negativo lo faceva
    poi entrare nel big-M come valore assoluto, e con un avversario a zero gol
    il big-M superava il miliardo, rendendo inutile il rilassamento lineare.
    Il chiamante deve trattare k <= 0 come vincolo assente, non come soglia."""
    if k <= 0:
        raise ValueError("per k <= 0 la condizione e' sempre vera: non esiste "
                         "una soglia, e il chiamante deve saperlo")
    return soglia + passo * (k - 1)


def verifica_ipotesi(punti: np.ndarray, regole: Regole, pool_ruoli: dict) -> list:
    """Controlla H1 e H3 prima di risolvere. H2 e' nella firma stessa."""
    problemi = []
    if sum(regole.quote.values()) != 11:
        problemi.append(
            f"le quote sommano a {sum(regole.quote.values())}, non a 11: "
            "la rosa non coincide con la formazione e la formulazione non e' "
            "esatta (ipotesi H1)")
    for r, q in regole.quote.items():
        disp = sum(1 for v in pool_ruoli.values() if v == r)
        if disp < q:
            problemi.append(f"ruolo {r}: {disp} giocatori disponibili, {q} richiesti")
    if punti.ndim != 3:
        problemi.append(f"punti ha {punti.ndim} dimensioni, attese 3 "
                        "(scenari, giornate, giocatori)")
    return problemi


def risolvi(punti: np.ndarray, giocatori: list, ruoli: dict, prezzi: dict,
            regole: Regole, gol_avversario: np.ndarray,
            punti_avversario: np.ndarray,
            punti_avversario_totale: np.ndarray | None = None,
            tempo_limite: int = 60, posseduti: list | None = None) -> dict:
    """Massimizza il numero di scenari vinti, all'ottimo.

    `punti[w, d, i]` sono i fantapunti del giocatore i nello scenario w alla
    giornata d, **gia' comprensivi di ogni bonus individuale della lega**.
    `gol_avversario[w, d]`, `punti_avversario[w]` (punti di classifica) e
    `punti_avversario_totale[w]` (fantapunti di stagione, per lo spareggio) sono
    costanti: l'avversario e' fissato (ipotesi H2).

    Lo spareggio sui fantapunti totali **e' implementato**: si arriva primi se
    si superano i punti di lega dell'avversario, oppure se si pareggiano e si
    hanno piu' fantapunti. Senza `punti_avversario_totale` lo spareggio non e'
    calcolabile e viene disattivato ponendolo a infinito, il che equivale a
    perderlo sempre: e' dichiarato qui, non silenzioso.
    """
    problemi = verifica_ipotesi(punti, regole, ruoli)
    if problemi:
        return {"stato": "ipotesi_non_soddisfatte", "problemi": problemi}
    if punti_avversario_totale is None:
        # senza i fantapunti totali dell'avversario lo spareggio non e'
        # calcolabile: si dichiara invece di fingere che non serva
        punti_avversario_totale = np.full(punti.shape[0], np.inf)

    n_scen, n_gior, n_gio = punti.shape
    assert n_gio == len(giocatori)
    soglia, passo = regole.soglia_gol, regole.passo_gol
    vinc, pari, _ = regole.punti

    prob = pulp.LpProblem("p_primo", pulp.LpMaximize)
    x = {pid: pulp.LpVariable(f"x_{i}", cat="Binary")
         for i, pid in enumerate(giocatori)}
    for pid in (posseduti or []):
        prob += x[pid] == 1

    # rosa legale
    for r, q in regole.quote.items():
        prob += pulp.lpSum(x[pid] for pid in giocatori if ruoli[pid] == r) == q
    prob += pulp.lpSum(max(1.0, float(prezzi.get(pid, 1.0))) * x[pid]
                       for pid in giocatori) <= regole.budget

    # limiti sui punteggi possibili: servono per i big-M, e devono essere veri
    p_min = np.zeros((n_scen, n_gior))
    p_max = np.zeros((n_scen, n_gior))
    for w in range(n_scen):
        for d in range(n_gior):
            v = np.sort(punti[w, d])
            need = sum(regole.quote.values())
            p_min[w, d] = v[:need].sum()
            p_max[w, d] = v[-need:].sum()

    # Punti totali per scenario: servono allo spareggio, e sono lineari in x.
    totale = {}
    tot_min, tot_max = {}, {}
    for w in range(n_scen):
        totale[w] = pulp.lpSum(punti[w, :, i].sum() * x[pid]
                               for i, pid in enumerate(giocatori))
        v = np.sort(punti[w].sum(axis=0))
        need = sum(regole.quote.values())
        tot_min[w] = float(v[:need].sum())
        tot_max[w] = float(v[-need:].sum())

    vittoria, pareggio = {}, {}
    for w in range(n_scen):
        for d in range(n_gior):
            P = pulp.lpSum(punti[w, d, i] * x[pid]
                           for i, pid in enumerate(giocatori))
            ga = int(gol_avversario[w, d])
            v = pulp.LpVariable(f"v_{w}_{d}", cat="Binary")
            q = pulp.LpVariable(f"q_{w}_{d}", cat="Binary")
            M = float(p_max[w, d] - p_min[w, d]) + 200.0
            # v = 1  <=>  facciamo almeno ga+1 gol  <=>  P >= soglia(ga+1)
            s_vinc = _soglia_per_gol(ga + 1, soglia, passo)
            prob += P >= s_vinc - M * (1 - v)
            prob += P <= s_vinc - 1e-6 + M * v
            # q = 1  <=>  facciamo almeno ga gol. Con ga = 0 e' sempre vero e
            # non esiste una soglia: si fissa q = 1 invece di inventare un
            # numero molto negativo che gonfierebbe il big-M.
            if ga <= 0:
                prob += q == 1
            else:
                s_pari = _soglia_per_gol(ga, soglia, passo)
                prob += P >= s_pari - M * (1 - q)
                prob += P <= s_pari - 1e-6 + M * q
            vittoria[(w, d)] = v
            pareggio[(w, d)] = q

    y = {}
    diagnostica_spareggio = 0
    for w in range(n_scen):
        L = pulp.lpSum(vinc * vittoria[(w, d)]
                       + pari * (pareggio[(w, d)] - vittoria[(w, d)])
                       for d in range(n_gior))
        Lavv = float(punti_avversario[w])
        Mw = float(vinc * n_gior + abs(Lavv) + 10.0)
        # ge = 1  <=>  L >= Lavv ;  vv = 1  <=>  L >= Lavv + 1
        ge = pulp.LpVariable(f"ge_{w}", cat="Binary")
        vv = pulp.LpVariable(f"vv_{w}", cat="Binary")
        prob += L >= Lavv - Mw * (1 - ge)
        prob += L <= Lavv - 1e-6 + Mw * ge
        prob += L >= Lavv + 1 - Mw * (1 - vv)
        prob += L <= Lavv + Mw * vv
        prob += vv <= ge                       # se L >= Lavv+1 allora L >= Lavv
        # i punti di lega sono interi: L = Lavv  <=>  ge = 1 e vv = 0
        eq = ge - vv
        # spareggio sui fantapunti totali: gt = 1  <=>  totale > totale avversario
        Tavv = float(punti_avversario_totale[w])
        Mt = float(tot_max[w] - tot_min[w]) + abs(Tavv) + 10.0
        gt = pulp.LpVariable(f"gt_{w}", cat="Binary")
        prob += totale[w] >= Tavv + 1e-6 - Mt * (1 - gt)
        prob += totale[w] <= Tavv + Mt * gt
        # and = eq AND gt
        aw = pulp.LpVariable(f"and_{w}", cat="Binary")
        prob += aw <= eq
        prob += aw <= gt
        prob += aw >= eq + gt - 1
        yw = pulp.LpVariable(f"y_{w}", cat="Binary")
        prob += yw == vv + aw          # vittoria di lega, oppure pari e piu' punti
        y[w] = yw
        diagnostica_spareggio += 1

    prob += pulp.lpSum(y.values())
    solver = pulp.PULP_CBC_CMD(msg=False, timeLimit=tempo_limite)
    prob.solve(solver)
    stato = pulp.LpStatus[prob.status]
    scelti = [pid for pid in giocatori if x[pid].value() and x[pid].value() > 0.5]
    vinti = sum(1 for w in range(n_scen) if y[w].value() and y[w].value() > 0.5)
    return {
        "stato": stato,
        "ottimo": stato == "Optimal",
        "rosa": {r: [pid for pid in scelti if ruoli[pid] == r]
                 for r in regole.quote},
        "scenari_vinti": int(vinti),
        "p1": vinti / n_scen,
        "obiettivo": pulp.value(prob.objective),
        "n_binari": len(x) + 2 * n_scen * n_gior + 5 * n_scen,
        "n_vincoli": len(prob.constraints),
        "tempo_limite_s": tempo_limite,
        "nota": ("il valore dell'obiettivo e' il numero di scenari vinti nel "
                 "campione SAA: non e' la probabilita' vera, e' la sua stima "
                 "campionaria su quegli scenari"),
    }


def p_primo_diretta(rosa: dict, punti: np.ndarray, giocatori: list,
                    regole: Regole, gol_avversario: np.ndarray,
                    punti_avversario: np.ndarray,
                    punti_avversario_totale: np.ndarray | None = None) -> float:
    """Stessa quantita', calcolata senza ottimizzare: serve a controllare che
    la formulazione dica davvero quello che intende dire.

    Applica lo **stesso** spareggio sui fantapunti totali del programma lineare.
    Se i due lo applicassero in modo diverso, il controllo incrociato non
    servirebbe a niente."""
    ix = {pid: i for i, pid in enumerate(giocatori)}
    scelti = [ix[pid] for r in rosa for pid in rosa[r]]
    vinc, pari, _ = regole.punti
    n_scen, n_gior, _ = punti.shape
    vinti = 0
    for w in range(n_scen):
        L = 0
        for d in range(n_gior):
            P = punti[w, d, scelti].sum()
            g = _gol_da_punti(P, regole.soglia_gol, regole.passo_gol)
            ga = int(gol_avversario[w, d])
            L += vinc if g > ga else (pari if g == ga else 0)
        if L > punti_avversario[w]:
            vinti += 1
        elif L == punti_avversario[w] and punti_avversario_totale is not None:
            mio_totale = sum(punti[w, d, scelti].sum() for d in range(n_gior))
            if mio_totale > punti_avversario_totale[w]:
                vinti += 1
    return vinti / n_scen
