"""Valutatore degli scenari: da un cubo a P(primo posto).

E' il pezzo che rende confrontabili due decisioni d'asta. Riceve un cubo di
stagioni simulate, le rose (esclusive) di tutte le squadre della lega, le
regole e la politica di formazione, e restituisce punteggi per giornata, gol
da fasce, classifica H2H, posizione e vincitori, con una traccia verificabile.

## Le proprieta' che deve avere, e che i test fissano

1. **Stesso mondo per tutte.** In uno scenario, la Serie A simulata e' una
   sola: se due rose contengono lo stesso giocatore, in quello scenario quel
   giocatore ha fatto le stesse cose. Il valutatore non estrae nulla di nuovo:
   legge il cubo.
2. **Invarianza.** Cambiare l'ordine delle squadre, il numero di rose valutate
   o la dimensione dei blocchi non cambia i punteggi. L'unica cosa che dipende
   dall'ordine e' l'accoppiamento del calendario, che va passato esplicito.
3. **Nessuna anticipazione.** La formazione di una giornata usa solo cio' che
   si sapeva prima: la forma costruita sulle giornate precedenti e l'elenco di
   chi risultava disponibile alla vigilia. Gli esiti della giornata entrano
   solo nelle sostituzioni automatiche, come da regolamento.
4. **Pari merito espliciti.** Se piu' squadre finiscono prime a pari merito
   dopo tutti i criteri di spareggio, la vittoria e' **condivisa**: ciascuna
   riceve 1/k. Nessun ordine alfabetico e nessun indice di squadra decide chi
   vince. Chi vuole un altro trattamento lo dichiara in `Regole.parita_finale`.

## Che cosa non fa

Non inventa la classifica di partenza. Se la lega e' gia' iniziata, lo stato
iniziale (punti gia' fatti, giornate gia' giocate) va passato: `stato_iniziale`.
Senza, il valutatore parte da zero e lo dichiara nel risultato.

Non inventa il calendario della lega. Se non lo si conosce, se ne genera uno
da un seme dichiarato e il risultato porta `calendario_dichiarato = True`:
e' un confronto condizionato a un banco, non una probabilita' riferita alla
lega reale.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from ..rules import CLEAN_SHEET_BONUS, MAX_SUBS, MOD_DIFESA_TABLE, QUOTAS
from ..season.lineup import BASELINE, BASELINE_VOTO, goals_from_points, pick_lineup, score_giornata


@dataclass(frozen=True)
class Regole:
    """Regole della lega, in un posto solo e passate esplicitamente."""
    quote: dict = field(default_factory=lambda: dict(QUOTAS))
    budget: int = 500
    max_cambi: int = MAX_SUBS
    soglia_gol: int = 66
    passo_gol: int = 6
    usa_mod_difesa: bool = True
    # Il bonus di 1 punto al portiere che non subisce gol e' una regola della
    # LEGA, non della fonte: il fantavoto che il cubo memorizza non lo contiene.
    # In produzione viene applicato quando si costruisce il pack
    # (`scripts/f2_build_packs.py:192`, `apply_clean_sheet`). Qui va applicato
    # esattamente una volta, e per farlo serve sapere quanti gol ha subito il
    # portiere: se il cubo non porta quel dato, il valutatore si ferma invece di
    # ignorare la regola in silenzio. Nel banco del Livello 2 questa regola non
    # veniva applicata affatto, per 0,297 punti a giornata per rosa.
    applica_bonus_porta_inviolata: bool = True
    punti: tuple = (3, 1, 0)                 # vittoria, pareggio, sconfitta
    # ordine dei criteri di spareggio in classifica, applicati in sequenza
    spareggio: tuple = ("punti", "fantapunti_totali")
    # che cosa fare se dopo tutti i criteri restano piu' prime a pari merito
    #   "condivisa"  ciascuna riceve 1/k della vittoria (predefinito, onesto)
    #   "nessuno"    nessuna vince: la vittoria vale 0 per tutte
    parita_finale: str = "condivisa"


@dataclass
class Esito:
    """Risultato della valutazione di uno o piu' scenari."""
    squadre: list
    punteggi: np.ndarray          # (n_scenari, n_squadre, n_giornate)
    gol: np.ndarray               # (n_scenari, n_squadre, n_giornate) da fasce
    punti_lega: np.ndarray        # (n_scenari, n_squadre) punti di classifica
    vittoria: np.ndarray          # (n_scenari, n_squadre) quota di vittoria 0..1
    posizione: np.ndarray         # (n_scenari, n_squadre) 1 = prima
    diagnostica: dict = field(default_factory=dict)

    def p_primo(self) -> dict:
        """Probabilita' campionaria di arrivare primi, per squadra."""
        return {s: float(self.vittoria[:, i].mean())
                for i, s in enumerate(self.squadre)}

    def errore_standard(self) -> dict:
        n = self.vittoria.shape[0]
        return {s: float(self.vittoria[:, i].std(ddof=1) / np.sqrt(n))
                for i, s in enumerate(self.squadre)}


# --------------------------------------------------------------------------
# calendario H2H
# --------------------------------------------------------------------------

def calendario_berger(n_squadre: int, n_giornate: int, seme: int) -> list:
    """Accoppiamenti per ogni giornata, con il metodo di Berger.

    Ritorna una lista di `n_giornate` liste di coppie (indice casa, indice
    ospite). Il girone si ripete finche' servono giornate. Il seme decide solo
    l'ordine iniziale delle squadre nel girone: cambiarlo cambia il banco, non
    le regole."""
    if n_squadre % 2:
        raise ValueError("numero di squadre dispari: servirebbe un turno di riposo")
    rng = np.random.default_rng(seme)
    ordine = list(rng.permutation(n_squadre))
    turni = []
    ts = ordine[:]
    for _ in range(n_squadre - 1):
        turni.append([(ts[i], ts[n_squadre - 1 - i]) for i in range(n_squadre // 2)])
        ts.insert(1, ts.pop())
    fuori = []
    for g in range(n_giornate):
        base = turni[g % len(turni)]
        # nei gironi di ritorno si invertono i campi
        if (g // len(turni)) % 2 == 1:
            base = [(b, a) for a, b in base]
        fuori.append(base)
    return fuori


# --------------------------------------------------------------------------
# punteggi di una rosa, giornata per giornata
# --------------------------------------------------------------------------

def punteggi_rosa(rosa: dict, cubo, indice: dict, scenario: int,
                  regole: Regole, giornate: list | None = None) -> np.ndarray:
    """Punti per giornata di una rosa in uno scenario.

    `cubo` deve esporre `fantavoto`, `voto`, `gioca` come array
    (scenari, giornate, giocatori) e `giocatori`. `indice` mappa il
    `master_id` alla colonna.

    La formazione di ogni giornata usa la forma costruita sulle giornate
    PRECEDENTI e l'elenco di chi ha preso voto la giornata precedente. Alla
    prima giornata non esiste un passato: nessuna informazione."""
    ids = [pid for r in regole.quote for pid in rosa.get(r, [])]
    col = {pid: indice.get(pid) for pid in ids}
    subiti = getattr(cubo, "gol_subiti", None)
    if regole.applica_bonus_porta_inviolata and subiti is None:
        raise ValueError(
            "il cubo non porta i gol subiti dai portieri: il bonus porta "
            "inviolata della lega non e' applicabile. Rigenera il cubo con il "
            "campo `gol_subiti`, oppure valuta con "
            "Regole(applica_bonus_porta_inviolata=False) DICHIARANDO che quel "
            "bonus non entra nel punteggio.")
    ruoli_rosa = {pid: r for r in regole.quote for pid in rosa.get(r, [])}
    n_g = cubo.fantavoto.shape[1] if giornate is None else len(giornate)
    idx_g = range(n_g) if giornate is None else giornate
    fuori = np.zeros(n_g)
    forma, forma_v = {}, {}
    somma, conta, somma_v = {}, {}, {}
    disponibili = None
    rosa_str = {r: [str(p) for p in rosa.get(r, [])] for r in regole.quote}
    for k, g in enumerate(idx_g):
        punti, voti = {}, {}
        for pid in ids:
            j = col[pid]
            if j is not None and cubo.gioca[scenario, g, j]:
                p = float(cubo.fantavoto[scenario, g, j])
                if (regole.applica_bonus_porta_inviolata
                        and ruoli_rosa.get(pid) == "P"
                        and float(subiti[scenario, g, j]) == 0.0):
                    p += CLEAN_SHEET_BONUS
                punti[str(pid)] = p
                voti[str(pid)] = float(cubo.voto[scenario, g, j])
        _, titolari, panchina = pick_lineup(rosa_str, forma, forma_v,
                                            regole.usa_mod_difesa, disponibili)
        p, _ = score_giornata(titolari, panchina, punti, regole.max_cambi,
                              voti, regole.usa_mod_difesa)
        fuori[k] = p
        disponibili = set(punti.keys())
        for pid, v in punti.items():
            somma[pid] = somma.get(pid, 0.0) + v
            conta[pid] = conta.get(pid, 0) + 1
            somma_v[pid] = somma_v.get(pid, 0.0) + voti[pid]
            forma[pid] = somma[pid] / conta[pid]
            forma_v[pid] = somma_v[pid] / conta[pid]
    return fuori


# --------------------------------------------------------------------------
# classifica
# --------------------------------------------------------------------------

def classifica(gol: np.ndarray, punteggi: np.ndarray, calendario: list,
               regole: Regole, iniziale: dict | None = None) -> tuple:
    """Punti di lega, posizione e quota di vittoria di uno scenario.

    `gol` e `punteggi` sono (n_squadre, n_giornate). Ritorna
    (punti_lega, posizione, vittoria)."""
    n = gol.shape[0]
    vinc, pari, _ = regole.punti
    punti = np.zeros(n)
    if iniziale:
        for i, v in iniziale.get("punti", {}).items():
            punti[i] += v
    for g, accoppiamenti in enumerate(calendario):
        if g >= gol.shape[1]:
            break
        for a, b in accoppiamenti:
            ga, gb = gol[a, g], gol[b, g]
            if ga > gb:
                punti[a] += vinc
            elif gb > ga:
                punti[b] += vinc
            else:
                punti[a] += pari
                punti[b] += pari
    totali = punteggi.sum(axis=1)
    if iniziale:
        for i, v in iniziale.get("fantapunti", {}).items():
            totali[i] += v

    # ordinamento per i criteri dichiarati, in sequenza
    chiavi = []
    for c in regole.spareggio:
        if c == "punti":
            chiavi.append(punti)
        elif c == "fantapunti_totali":
            chiavi.append(totali)
        else:
            raise ValueError(f"criterio di spareggio sconosciuto: {c}")
    # np.lexsort ordina per l'ultima chiave per prima: si inverte
    ordine = np.lexsort(tuple(-k for k in reversed(chiavi)))
    posizione = np.empty(n, dtype=int)
    pos = 1
    i = 0
    while i < n:
        # quante squadre condividono ESATTAMENTE tutti i criteri
        j = i + 1
        while j < n and all(np.isclose(k[ordine[j]], k[ordine[i]]) for k in chiavi):
            j += 1
        for t in range(i, j):
            posizione[ordine[t]] = pos
        pos += (j - i)
        i = j

    prime = np.flatnonzero(posizione == 1)
    vittoria = np.zeros(n)
    if regole.parita_finale == "condivisa":
        vittoria[prime] = 1.0 / len(prime)
    elif regole.parita_finale == "nessuno":
        if len(prime) == 1:
            vittoria[prime] = 1.0
    else:
        raise ValueError(f"parita_finale sconosciuta: {regole.parita_finale}")
    return punti, posizione, vittoria


# --------------------------------------------------------------------------
# valutazione completa
# --------------------------------------------------------------------------

def verifica_rose(rose: dict, regole: Regole) -> list:
    """Controlli di legalita' prima di valutare. Ritorna l'elenco dei problemi."""
    problemi = []
    visti = {}
    for squadra, rosa in rose.items():
        for ruolo, quanti in regole.quote.items():
            n = len(rosa.get(ruolo, []))
            if n != quanti:
                problemi.append(f"{squadra}: {n} giocatori in {ruolo}, attesi {quanti}")
        for ruolo in rosa:
            for pid in rosa[ruolo]:
                if pid in visti:
                    problemi.append(
                        f"{pid} in due squadre: {visti[pid]} e {squadra} "
                        "(nella lega la proprieta' e' esclusiva)")
                visti[pid] = squadra
    return problemi


def valuta(cubo, rose: dict, regole: Regole | None = None,
           calendario: list | None = None, seme_calendario: int = 0,
           giornate: list | None = None, stato_iniziale: dict | None = None,
           scenari: list | None = None, controlla_legalita: bool = True) -> Esito:
    """Valuta tutte le rose sugli stessi scenari del cubo.

    `rose`: nome della squadra -> {ruolo: [master_id]}. Devono essere tutte le
    squadre della lega, con proprieta' esclusiva.
    `calendario`: lista per giornata di coppie (indice casa, indice ospite).
    Se assente se ne genera uno da `seme_calendario` e il risultato lo dichiara.
    """
    regole = regole or Regole()
    squadre = sorted(rose)
    if controlla_legalita:
        problemi = verifica_rose(rose, regole)
        if problemi:
            raise ValueError("rose illegali:\n  " + "\n  ".join(problemi[:10]))
    indice = {pid: i for i, pid in enumerate(cubo.giocatori)}
    n_scen = cubo.fantavoto.shape[0] if scenari is None else len(scenari)
    lista_scen = range(n_scen) if scenari is None else scenari
    n_g = cubo.fantavoto.shape[1] if giornate is None else len(giornate)
    dichiarato = calendario is None
    if dichiarato:
        calendario = calendario_berger(len(squadre), n_g, seme_calendario)

    P = np.zeros((n_scen, len(squadre), n_g))
    for si, s in enumerate(lista_scen):
        for ti, t in enumerate(squadre):
            P[si, ti] = punteggi_rosa(rose[t], cubo, indice, s, regole, giornate)
    G = np.vectorize(lambda x: goals_from_points(x, regole.soglia_gol,
                                                 regole.passo_gol))(P)
    PL = np.zeros((n_scen, len(squadre)))
    POS = np.zeros((n_scen, len(squadre)), dtype=int)
    VIN = np.zeros((n_scen, len(squadre)))
    for si in range(n_scen):
        PL[si], POS[si], VIN[si] = classifica(G[si], P[si], calendario, regole,
                                              stato_iniziale)
    return Esito(
        squadre=squadre, punteggi=P, gol=G, punti_lega=PL, vittoria=VIN,
        posizione=POS,
        diagnostica={
            "n_scenari": int(n_scen),
            "n_giornate": int(n_g),
            "calendario_dichiarato": bool(dichiarato),
            "seme_calendario": seme_calendario if dichiarato else None,
            "stato_iniziale": bool(stato_iniziale),
            "parita_finale": regole.parita_finale,
            "bonus_porta_inviolata_applicato": bool(
                regole.applica_bonus_porta_inviolata),
            "spareggio": list(regole.spareggio),
            "scenari_con_parita_al_primo": int(
                sum(1 for si in range(n_scen) if (POS[si] == 1).sum() > 1)),
        })


def differenza_appaiata(a: Esito, b: Esito, squadra: str,
                        n_boot: int = 4000, seme: int = 0) -> dict:
    """Differenza di P(1 posto) fra due valutazioni sugli STESSI scenari.

    Appaiata per scenario: e' l'unico confronto che elimina il rumore comune.
    Ritorna media, intervallo al 95% e se l'intervallo esclude lo zero."""
    ia = a.squadre.index(squadra)
    ib = b.squadre.index(squadra)
    x = a.vittoria[:, ia]
    y = b.vittoria[:, ib]
    if len(x) != len(y):
        raise ValueError("scenari di numero diverso: il confronto non e' appaiato")
    d = x - y
    rng = np.random.default_rng(seme)
    idx = rng.integers(0, len(d), (n_boot, len(d)))
    medie = d[idx].mean(1)
    lo, hi = float(np.percentile(medie, 2.5)), float(np.percentile(medie, 97.5))
    return {"differenza": float(d.mean()), "ic95": [lo, hi],
            "esclude_zero": bool(lo > 0 or hi < 0),
            "n_scenari": int(len(d)),
            "p1_a": float(x.mean()), "p1_b": float(y.mean())}
