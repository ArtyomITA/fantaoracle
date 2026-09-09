"""Proiezione su una somma e ricerca SPSA: le due parti verificabili del pilota.

Stanno qui, fuori dallo script, perché sono le due che hanno prove numeriche
con risposta nota. Il pilota le usa; i test le esercitano senza far girare il
generatore.

## Perché la proiezione precedente non andava

`b_i * S / Σb` moltiplica per un fattore comune e poi tronca a `[0, 1]`. Chi
satura perde la parte tagliata, e nessuno la ridistribuisce: con `[0,9; 0,1]` e
somma richiesta `2` esce `[1,0; 0,2]`, cioè **1,2**, mentre la diagnostica
dichiarava 2. La somma «ottenuta» non era la somma ottenuta.

## Che cosa significa quella somma

Va detto prima di imporla. Una media storica per ruolo è un **riferimento
statistico**, non un vincolo fisico: le regole del generatore non impediscono a
una squadra di discostarsene, e uguagliare tutte le squadre alla media del
ruolo cancella differenze tattiche che possono essere vere. Un vincolo fisico
va derivato dalle regole — undici in campo, un portiere, tre sostituzioni — e
questo modulo non pretende di averlo fatto.

Perciò la proiezione ha due modi, e chi la chiama deve sceglierne uno:

- `modo="riferimento"` — la somma è un bersaglio morbido. Si tira verso di essa
  con un peso dichiarato, senza imporla;
- `modo="vincolo"` — la somma è imposta esattamente, con una proiezione che la
  rispetta **anche dopo la saturazione**, redistribuendo su chi non è saturo.

In entrambi i casi si registra: bersaglio originale, somma richiesta, somma
ottenuta, giocatori saturati e scarto introdotto.
"""
from __future__ import annotations

import numpy as np


# --------------------------------------------------------------------------
# proiezione su una somma, con saturazione
# --------------------------------------------------------------------------

def proietta_su_somma(valori, somma_voluta: float, *, modo: str = "vincolo",
                      peso: float = 1.0, lo: float = 0.0, hi: float = 1.0,
                      tolleranza: float = 1e-9, massimo_giri: int = 200
                      ) -> tuple[np.ndarray, dict]:
    """Riscala `valori` verso `somma_voluta` rispettando i limiti `[lo, hi]`.

    Con `modo="vincolo"` la somma viene **rispettata**: il fattore moltiplicativo
    si ricalcola sui non saturi finché la somma torna, oppure finché tutti sono
    saturi — e in quel caso la somma richiesta è irraggiungibile dentro i
    limiti, il che viene detto invece che nascosto.

    Con `modo="riferimento"` si applica solo una frazione `peso` dello
    spostamento: la somma richiesta è un riferimento verso cui tirare, non una
    legge.

    Ritorna i valori proiettati e una diagnostica che confronta **richiesto** e
    **ottenuto**, invece di dichiarare il primo come se fosse il secondo.
    """
    v = np.asarray(valori, dtype=float)
    orig = v.copy()
    n = v.size
    # Ogni uscita restituisce le stesse chiavi: prima il ramo «non applicabile»
    # ne ometteva quattro e lasciava passare valori fuori da [lo, hi].
    def vuota(esito, valori_fuori, nota=None):
        d = {"modo": modo, "n": int(n),
             "somma_originale": float(np.nansum(orig)) if n else 0.0,
             "somma_richiesta": float(somma_voluta), "lo": lo, "hi": hi,
             "esito": esito, "somma_bersaglio_usata": None,
             "somma_ottenuta": float(np.nansum(valori_fuori)) if n else 0.0,
             "raggiunta": False, "saturati": 0, "giri": 0,
             "scarto_l1": (float(np.nansum(np.abs(valori_fuori - orig)))
                           if n else 0.0),
             "scarto_massimo": (float(np.nanmax(np.abs(valori_fuori - orig)))
                                if n else 0.0)}
        if nota:
            d["nota"] = nota
        return d

    if n == 0:
        return v, vuota("nessun valore", v)
    # NaN e infiniti: prima si propagavano su tutti gli altri attraverso il
    # fattore comune, distruggendo i valori sani
    non_finiti = ~np.isfinite(v)
    if non_finiti.any():
        fuori = np.where(non_finiti, np.nan, np.clip(v, lo, hi))
        d = vuota("valori non finiti", fuori,
                  nota=(f"{int(non_finiti.sum())} valori non finiti: la "
                        "proiezione non li tocca e non li propaga sugli altri, "
                        "che restano solo troncati"))
        d["non_finiti"] = int(non_finiti.sum())
        return fuori, d
    somma_orig = float(np.sum(v))
    diag = {"modo": modo, "n": int(n), "somma_originale": somma_orig,
            "somma_richiesta": float(somma_voluta), "lo": lo, "hi": hi}
    if somma_orig <= 0 or not np.isfinite(somma_voluta) or somma_voluta < 0:
        return np.clip(v, lo, hi), vuota(
            "non applicabile", np.clip(v, lo, hi),
            nota=("somma originale non positiva, oppure somma richiesta non "
                  "finita o negativa: non c'e' un fattore di scala"))

    if modo == "riferimento":
        peso = float(min(max(peso, 0.0), 1.0))
        bersaglio = somma_orig + peso * (somma_voluta - somma_orig)
    elif modo == "vincolo":
        bersaglio = float(somma_voluta)
    else:
        raise ValueError(f"modo sconosciuto: {modo!r}")

    fuori = np.clip(v, lo, hi)
    liberi = np.ones(n, dtype=bool)
    giri = 0
    motivo = "giri esauriti"
    for giri in range(1, massimo_giri + 1):
        somma_bloccata = float(np.sum(fuori[~liberi]))
        resto = bersaglio - somma_bloccata
        base = float(np.sum(orig[liberi]))
        if not liberi.any() or base <= 0:
            motivo = "tutti i valori liberi sono saturi"
            break
        k = resto / base
        proposto = np.clip(orig[liberi] * k, lo, hi)
        fuori[liberi] = proposto
        satura_ora = liberi & ((fuori >= hi - tolleranza) |
                               (fuori <= lo + tolleranza))
        if abs(float(np.sum(fuori)) - bersaglio) <= tolleranza:
            motivo = "somma raggiunta"
            break
        if not satura_ora.any():
            motivo = "nessun nuovo saturo, il fattore non si puo' ricalcolare"
            break
        liberi = liberi & ~satura_ora

    ottenuta = float(np.sum(fuori))
    saturati = int(np.sum((fuori >= hi - tolleranza) | (fuori <= lo + tolleranza)))
    diag.update({
        "somma_bersaglio_usata": bersaglio,
        "somma_ottenuta": ottenuta,
        "raggiunta": bool(abs(ottenuta - bersaglio) <= 1e-6),
        "saturati": saturati,
        "giri": giri,
        "scarto_l1": float(np.sum(np.abs(fuori - orig))),
        "scarto_massimo": float(np.max(np.abs(fuori - orig))),
    })
    diag["motivo_uscita"] = motivo
    if not diag["raggiunta"]:
        diag["nota"] = (
            f"somma non raggiunta ({motivo}). Il valore ottenuto e' quello "
            "vero, non quello chiesto." +
            (" Aumentare `massimo_giri` puo' bastare."
             if motivo == "giri esauriti" else ""))
    return fuori, diag


# --------------------------------------------------------------------------
# SPSA
# --------------------------------------------------------------------------

ALPHA, GAMMA = 0.602, 0.101      # esponenti standard della letteratura SPSA


def A_di(massimo: int) -> float:
    """`A` in funzione del budget, come lo calcola `spsa`.

    Sta in una funzione sola perche' `calibra_guadagno` e `spsa` devono usare
    **lo stesso** valore: usandone due diversi il primo passo non vale quello
    che la calibrazione dichiara. Misurato: con `A = 1` nella calibrazione e
    `A = 20` in `spsa`, il primo passo vale 0,0486 invece di 0,20, cioe' 4,12
    volte meno — il rapporto `(21/2)^0,602`.
    """
    return max(1.0, float(massimo) / 10.0)


def calibra_guadagno(obiettivo, theta0, semi, *, c: float, passo_voluto: float,
                     campioni: int = 6, rng=None, A: float | None = None,
                     massimo: int | None = None,
                     alpha: float = ALPHA) -> dict:
    """Sceglie `a` da una stima empirica della grandezza del gradiente SPSA.

    Il difetto che chiude: con `a` fissato a mano e una perdita che è una
    **media** su `p` parametri, il gradiente è dell'ordine di `1/p` e il passo
    diventa invisibile. Su una quadratica senza rumore con ottimo noto, 103
    parametri e `a = 0,30`, lo stesso codice muoveva `‖θ‖` di 0,0056 in sei
    iterazioni.

    La regola, che è quella pratica della letteratura: si misura `|ĝ|` con
    qualche perturbazione, poi si sceglie `a` perché il **primo passo** in `θ`
    valga `passo_voluto`:

        a = passo_voluto * (A + 1)^alpha / mediana(|ĝ|)

    La mediana e non la media, perché una singola direzione SPSA può dare una
    componente enorme quando `δ_i` cade vicino a zero — qui non succede, perché
    `δ` è Bernoulli ±1, ma la mediana resta più stabile fra ripetizioni.
    """
    rng = rng or np.random.default_rng(0)
    if A is None:
        if massimo is None:
            raise ValueError(
                "serve `A` oppure `massimo`: senza, la calibrazione userebbe "
                "un `A` diverso da quello di `spsa` e il primo passo non "
                "varrebbe quello dichiarato")
        A = A_di(massimo)
    theta0 = np.asarray(theta0, dtype=float)
    p = theta0.size
    grandezze = []
    for i in range(campioni):
        delta = rng.choice([-1.0, 1.0], size=p)
        seme = semi[i % len(semi)]
        piu = obiettivo(theta0 + c * delta, seme)
        meno = obiettivo(theta0 - c * delta, seme)
        g = (piu - meno) / (2.0 * c) / delta
        grandezze.append(float(np.median(np.abs(g))))
    g_med = float(np.median(grandezze))
    if not np.isfinite(g_med) or g_med <= 0:
        return {"a": None, "gradiente_mediano": g_med,
                "nota": "gradiente stimato nullo o non finito: `a` non e' "
                        "calibrabile, e un passo scelto a mano sarebbe cieco"}
    a = float(passo_voluto * (A + 1.0) ** alpha / g_med)
    return {"a": a, "A": float(A), "gradiente_mediano": g_med,
            "grandezze": grandezze, "passo_voluto": passo_voluto,
            "primo_passo_atteso": float(a / (A + 1.0) ** alpha * g_med),
            "valutazioni": 2 * campioni}


def spsa(obiettivo, p: int, semi_comuni, *, a: float, c: float,
         A: float | None = None, massimo: int = 30,
         monitoraggio=None, ogni: int = 1, pazienza: int = 5,
         miglioramento_minimo: float = 0.01, rng=None,
         alpha: float = ALPHA, gamma: float = GAMMA) -> dict:
    """SPSA con monitoraggio della soluzione corrente e checkpoint del migliore.

    ## Che cosa cambia rispetto alla versione precedente

    Quella confrontava `0,5·(L(θ+cδ) + L(θ−cδ))` fra iterazioni: due misure
    **perturbate**, con perturbazione decrescente e semi che cambiavano. Non è
    una misura confrontabile dell'obiettivo alla soluzione aggiornata, e
    l'arresto che ne derivava non diceva niente sul progresso. Restituiva anche
    l'ultimo `θ`, non il migliore osservato.

    Adesso, ogni `ogni` iterazioni, `monitoraggio(θ)` valuta l'obiettivo **al θ
    corrente** su un insieme di semi fissi, separato da quelli
    dell'ottimizzazione e da quelli della verifica finale. L'arresto guarda
    quella serie, e il `θ` restituito è quello con il monitoraggio migliore.

    `monitoraggio=None` disattiva sia il controllo sia l'arresto anticipato: si
    fanno tutte le iterazioni del budget. È il comportamento onesto quando non
    si vuole pagare il costo del monitoraggio, non un ripiego silenzioso.
    """
    rng = rng or np.random.default_rng(0)
    A = A if A is not None else max(1.0, massimo / 10.0)
    theta = np.zeros(p)
    storia = []
    migliore = {"L": np.inf, "theta": theta.copy(), "iterazione": 0}
    senza_miglioramento = 0
    motivo = f"budget esaurito ({massimo} iterazioni)"

    if monitoraggio is not None:
        L0 = float(monitoraggio(theta))
        migliore = {"L": L0, "theta": theta.copy(), "iterazione": 0}
        storia.append({"iterazione": 0, "L_monitoraggio": L0,
                       "norma_theta": 0.0})

    for k in range(1, massimo + 1):
        ak = a / (A + k) ** alpha
        ck = c / k ** gamma
        # Bernoulli +-1: uniforme e normale non sono ammesse dalle condizioni
        # di regolarita' di SPSA (momenti inversi infiniti)
        delta = rng.choice([-1.0, 1.0], size=p)
        seme = semi_comuni[(k - 1) % len(semi_comuni)]
        piu = obiettivo(theta + ck * delta, seme)
        meno = obiettivo(theta - ck * delta, seme)
        g = (piu - meno) / (2.0 * ck) / delta
        theta = theta - ak * g
        riga = {"iterazione": k, "ak": ak, "ck": ck, "seme": seme,
                "L_piu": piu, "L_meno": meno,
                "norma_gradiente": float(np.linalg.norm(g)),
                "norma_passo": float(ak * np.linalg.norm(g)),
                "norma_theta": float(np.linalg.norm(theta))}
        if monitoraggio is not None and (k % ogni == 0 or k == massimo):
            Lm = float(monitoraggio(theta))
            riga["L_monitoraggio"] = Lm
            # miglioramento RELATIVO al migliore, con il valore assoluto al
            # denominatore: `migliore * (1 - eps)` con `L < 0` sta SOPRA il
            # migliore, quindi contava come miglioramento un valore peggiore.
            # Qui la perdita e' non negativa, ma la regola dichiarata dev'essere
            # quella applicata.
            rif = migliore["L"]
            soglia = (rif - miglioramento_minimo * abs(rif)
                      if np.isfinite(rif) else np.inf)
            if Lm < soglia:
                senza_miglioramento = 0
            else:
                senza_miglioramento += 1
            if Lm < migliore["L"]:
                migliore = {"L": Lm, "theta": theta.copy(), "iterazione": k}
            if senza_miglioramento >= pazienza:
                riga["arresto"] = (
                    f"{pazienza} controlli senza miglioramento oltre "
                    f"{miglioramento_minimo:.0%} sul monitoraggio")
                motivo = riga["arresto"]
                storia.append(riga)
                break
        storia.append(riga)

    if monitoraggio is None:
        migliore = {"L": None, "theta": theta.copy(), "iterazione": len(storia)}
    return {"theta": migliore["theta"], "theta_finale": theta,
            "L_migliore": migliore["L"], "iterazione_migliore": migliore["iterazione"],
            "storia": storia, "iterazioni": len([r for r in storia
                                                 if r["iterazione"] > 0]),
            "motivo_arresto": motivo, "a": a, "c": c, "A": A}
