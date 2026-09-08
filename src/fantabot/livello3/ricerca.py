"""Ricerca della rosa per l'obiettivo campionario P(primo posto).

## Che cosa fa, detto con il nome giusto

Questo modulo **non risolve all'ottimo globale** il problema «quale rosa
massimizza la probabilita' di vincere il campionato». Quel problema, scritto
per intero, contiene i punteggi di 38 giornate, le fasce gol, le vittorie
testa a testa, gli spareggi e le decisioni di formazione non anticipative: non
e' un programma lineare che si scrive e si risolve.

Quello che fa e' **ricerca su candidate per l'obiettivo SAA**:

1. genera un insieme di rose ammissibili con obiettivi diversi (il MILP
   esistente, con pesi e vincoli variati);
2. le migliora con scambi locali, riottimizzando i posti liberati;
3. valuta ciascuna con l'obiettivo vero — la quota di scenari in cui arriva
   prima — sugli **scenari di ricerca**;
4. rigioca la migliore su **scenari di verifica mai usati per sceglierla**.

Il MILP che genera una candidata puo' essere risolto all'ottimo: questo non
rende ottima la rosa rispetto a P(primo posto), perche' l'obiettivo del MILP
non e' quello. La differenza va detta, non nascosta dietro la parola "ottimo".

## Perche' non basta l'attuale `choose_objective()`

`montecarlo.choose_objective` gia' sceglie fra candidate: prova alcune
combinazioni di peso dell'upside e quota d'attacco e ne misura la quota di
vittorie. Le differenze del Livello 3 sono tre:

- il valutatore e' quello del Livello 3, con proprieta' esclusiva dei
  giocatori, classifica con spareggi espliciti e pari merito condivisi;
- gli avversari sono costruiti **dal pool che resta dopo la nostra rosa**, non
  da tutto il listone: nell'asta vera un giocatore sta in una squadra sola;
- la ricerca non si ferma alle combinazioni della griglia: aggiunge scambi
  locali e famiglie di strategie dichiarate (due punte di prima fascia, una
  sola punta, difesa da modificatore, piu' profondita').

## Enumerazione esatta

`enumera_esatto` elenca tutte le rose legali di un'istanza piccola e le valuta
una per una. Serve a verificare che la ricerca trovi davvero il massimo dove il
massimo si puo' calcolare. Non e' utilizzabile sulla dimensione vera: con 587
giocatori e 25 posti le combinazioni sono astronomiche.
"""
from __future__ import annotations

import itertools
from dataclasses import dataclass, field

import numpy as np

from ..models import ROLES, Player
from ..optimizer import optimize_roster
from .valutatore import Esito, Regole, valuta


# --------------------------------------------------------------------------
# avversari costruiti dal pool che resta
# --------------------------------------------------------------------------

FAMIGLIE = {
    # nome: (come valuta i giocatori, quota di spesa in attacco)
    "mercato": ("prezzo", (0.30, 0.50)),
    "top": ("prezzo", (0.55, 0.72)),
    "valore": ("valore_su_prezzo", (0.30, 0.50)),
    "equilibrio": ("valore", (0.25, 0.40)),
}


def _riserva(rosa: dict, regole: Regole) -> int:
    """Crediti da tenere per riempire i posti ancora vuoti a 1 credito.

    Va chiamata con il giocatore in esame GIA' dentro `rosa`: cosi' `vuoti` e'
    il numero di posti che resteranno dopo l'acquisto, e ognuno costa almeno
    un credito. Togliere un'unita' qui faceva sforare il budget di un credito.
    """
    vuoti = sum(regole.quote[r] - len(rosa.get(r, [])) for r in regole.quote)
    return max(0, vuoti)


def avversari_dal_pool(pool: dict, prezzi: dict, valori: dict, regole: Regole,
                       n: int, esclusi: set, seme: int,
                       famiglie: list | None = None) -> list:
    """Costruisce `n` rose avversarie dai giocatori NON gia' presi.

    Due passaggi, entrambi dentro il budget:

    1. **riempimento**: per ogni ruolo si comprano i migliori secondo il
       criterio della famiglia, purche' resti un credito per ogni posto ancora
       vuoto; i posti che avanzano si riempiono col piu' economico disponibile;
    2. **miglioramento**: finche' restano crediti, si sostituisce il giocatore
       piu' debole con il migliore acquistabile con la differenza. Serve a
       rendere gli avversari competenti: una squadra che chiude l'asta con 300
       crediti in mano non e' un avversario, e' un regalo.

    Alla fine il costo viene verificato: se supera il budget e' un errore del
    generatore, non un avversario "un po' sopra".
    """
    famiglie = famiglie or list(FAMIGLIE)
    rng = np.random.default_rng(seme)
    presi = set(esclusi)
    rose = []
    for k in range(n):
        nome_fam = famiglie[k % len(famiglie)]
        criterio, (lo, hi) = FAMIGLIE[nome_fam]
        quota_att = float(rng.uniform(lo, hi))
        rosa = {r: [] for r in regole.quote}
        pagato = {}
        budget = float(regole.budget)
        speso_attacco = 0.0

        # 1) riempimento
        for ruolo in ("A", "C", "D", "P"):
            quanti = regole.quote[ruolo]
            disponibili = [pid for pid, pl in pool.items()
                           if pl.role == ruolo and pid not in presi]
            if criterio == "prezzo":
                chiave = lambda pid: -prezzi.get(pid, 1.0)          # noqa: E731
            elif criterio == "valore":
                chiave = lambda pid: -valori.get(pid, 0.0)          # noqa: E731
            else:
                chiave = lambda pid: -(valori.get(pid, 0.0)         # noqa: E731
                                       / max(prezzi.get(pid, 1.0), 1.0))
            disponibili.sort(key=lambda pid: (chiave(pid), str(pid)))
            for pid in disponibili:
                if len(rosa[ruolo]) >= quanti:
                    break
                prezzo = max(1.0, float(prezzi.get(pid, 1.0)))
                rosa[ruolo].append(pid)
                if prezzo > budget - _riserva(rosa, regole):
                    rosa[ruolo].pop()
                    continue
                if ruolo == "A" and speso_attacco + prezzo > quota_att * regole.budget:
                    rosa[ruolo].pop()
                    continue
                presi.add(pid)
                pagato[pid] = prezzo
                budget -= prezzo
                if ruolo == "A":
                    speso_attacco += prezzo
            # posti che avanzano: il piu' economico disponibile
            economici = sorted(
                (pid for pid in disponibili if pid not in presi),
                key=lambda pid: (max(1.0, float(prezzi.get(pid, 1.0))), str(pid)))
            for pid in economici:
                if len(rosa[ruolo]) >= quanti:
                    break
                rosa[ruolo].append(pid)
                prezzo = max(1.0, float(prezzi.get(pid, 1.0)))
                if prezzo > budget - _riserva(rosa, regole):
                    # a fine asta un posto si riempie a un credito: e' quello
                    # che succede davvero quando nessun altro rilancia
                    prezzo = 1.0
                presi.add(pid)
                pagato[pid] = prezzo
                budget -= prezzo
            if len(rosa[ruolo]) < quanti:
                raise ValueError(
                    f"avversario {k + 1}: solo {len(rosa[ruolo])} giocatori in "
                    f"{ruolo} su {quanti} richiesti. Il pool residuo non basta "
                    f"per {n} avversari: servono almeno "
                    f"{(n + 1) * sum(regole.quote.values())} giocatori nel pool.")

        # 2) miglioramento: i crediti che restano vanno spesi, se conviene
        for _ in range(60):
            if budget < 1:
                break
            migliore = None
            for ruolo in regole.quote:
                dentro = sorted(rosa[ruolo], key=lambda pid: valori.get(pid, 0.0))
                if not dentro:
                    continue
                debole = dentro[0]
                rimborso = float(pagato.get(debole, 1.0))
                for pid, pl in pool.items():
                    if pl.role != ruolo or pid in presi:
                        continue
                    prezzo = max(1.0, float(prezzi.get(pid, 1.0)))
                    if prezzo - rimborso > budget:
                        continue
                    guadagno = valori.get(pid, 0.0) - valori.get(debole, 0.0)
                    if guadagno <= 0:
                        continue
                    if migliore is None or guadagno > migliore[0]:
                        migliore = (guadagno, ruolo, debole, pid,
                                    prezzo - rimborso)
            if migliore is None:
                break
            _, ruolo, debole, entrante, costo = migliore
            rosa[ruolo] = [entrante if x == debole else x for x in rosa[ruolo]]
            presi.discard(debole)
            presi.add(entrante)
            pagato.pop(debole, None)
            pagato[entrante] = max(1.0, float(prezzi.get(entrante, 1.0)))
            budget -= costo

        costo_totale = sum(pagato.get(pid, 1.0) for r in rosa for pid in rosa[r])
        if costo_totale > regole.budget + 1e-6:
            raise ValueError(
                f"avversario {k + 1}: costo {costo_totale:.0f} oltre il budget "
                f"{regole.budget}. E' un errore del generatore.")
        rose.append({"rosa": rosa, "pagato": pagato,
                     "residuo": round(regole.budget - costo_totale, 2),
                     "famiglia": nome_fam})
    return rose


def avversari_milp_dal_pool(pool: dict, prezzi: dict, valori: dict,
                            regole: Regole, n: int, esclusi: set, seme: int,
                            tempo_solver: int = 3,
                            min_spesa_frazione: float = 0.95) -> list:
    """Avversari **competenti**: ottimizzano davvero, dal pool che resta.

    Il generatore greedy va bene per un abbozzo, ma non e' un avversario: nel
    primo giro sui dati veri la nostra rosa faceva 70,1 punti a giornata contro
    52-65 dei greedy, e vinceva il 90% delle volte. Un banco cosi' misura la
    debolezza degli avversari, non la forza della rosa.

    Qui ogni avversario risolve lo stesso problema che risolviamo noi, con un
    obiettivo diverso: quota di spesa in attacco, peso della panchina e rumore
    sulle valutazioni cambiano da famiglia a famiglia. Il rumore rappresenta
    che gli altri non hanno le nostre stime: sono bravi, non identici a noi.
    """
    rng = np.random.default_rng(seme)
    disponibili = {pid: pl for pid, pl in pool.items() if pid not in esclusi}
    profili = [
        # (quota attacco, peso panchina, rumore sulle valutazioni)
        ((0.55, 0.70), 0.25, 0.10),
        ((0.40, 0.55), 0.30, 0.12),
        ((0.28, 0.42), 0.35, 0.10),
        ((0.45, 0.60), 0.20, 0.15),
        ((0.32, 0.48), 0.40, 0.12),
    ]
    rose = []
    presi = set(esclusi)
    for k in range(n):
        lo, hi, peso, rumore = (*profili[k % len(profili)][0],
                                profili[k % len(profili)][1],
                                profili[k % len(profili)][2])
        cand = {pid: pl for pid, pl in disponibili.items() if pid not in presi}
        v = {pid: valori.get(pid, 0.0) * float(rng.uniform(1 - rumore, 1 + rumore))
             for pid in cand}
        sol = optimize_roster(cand, prezzi, v, regole.quote, regole.budget,
                              forced_spend={"A": (lo * regole.budget,
                                                  hi * regole.budget)},
                              bench_weight=peso, time_limit=tempo_solver,
                              min_spend=min_spesa_frazione * regole.budget)
        if sol is None:
            sol = optimize_roster(cand, prezzi, v, regole.quote, regole.budget,
                                  bench_weight=peso, time_limit=tempo_solver)
        if sol is None:
            raise ValueError(
                f"avversario {k + 1}: nessuna rosa ammissibile dal pool residuo "
                f"({len(cand)} giocatori). Il banco non e' costruibile.")
        rosa = sol["roster"]
        for r in rosa:
            presi.update(rosa[r])
        costo = sum(max(1.0, float(prezzi.get(pid, 1.0)))
                    for r in rosa for pid in rosa[r])
        if costo > regole.budget + 1e-6:
            raise ValueError(f"avversario {k + 1}: costo {costo:.0f} oltre il "
                             f"budget {regole.budget}")
        rose.append({"rosa": rosa, "pagato": {pid: max(1.0, float(prezzi.get(pid, 1.0)))
                                              for r in rosa for pid in rosa[r]},
                     "residuo": round(regole.budget - costo, 2),
                     "famiglia": f"milp{k % len(profili) + 1}"})
    return rose


# --------------------------------------------------------------------------
# generazione di candidate
# --------------------------------------------------------------------------

@dataclass
class Strategia:
    """Una famiglia di rose da esplorare, con il suo nome."""
    nome: str
    lam: float = 0.0                       # peso dell'upside
    quota_attacco: tuple | None = None     # (min, max) spesa in attacco
    peso_panchina: float = 0.30
    min_spesa: float | None = None
    forzati: list = field(default_factory=list)   # master_id da comprare


def strategie_predefinite(budget: int) -> list:
    """Le famiglie che il committente vuole vedere davvero esplorate.

    Comprende esplicitamente due punte di prima fascia, l'alternativa con una
    sola punta forte, la difesa da modificatore e la maggiore profondita'. La
    quota d'attacco e' un intervallo di spesa, non un obbligo di comprare due
    nomi: se i prezzi non lo giustificano, la rosa migliore restera' un'altra.
    """
    s = []
    for lam in (0.0, 0.5, 1.0):
        for nome, quota in (("attacco leggero", (0.20, 0.35)),
                            ("attacco medio", (0.35, 0.50)),
                            ("attacco pesante", (0.50, 0.65)),
                            ("due punte di prima fascia", (0.60, 0.75))):
            s.append(Strategia(nome=f"{nome} lam={lam}", lam=lam,
                               quota_attacco=quota))
    for peso in (0.15, 0.45):
        s.append(Strategia(nome=f"profondita' peso_panchina={peso}",
                           peso_panchina=peso, quota_attacco=(0.30, 0.50)))
    s.append(Strategia(nome="difesa da modificatore", lam=0.0,
                       quota_attacco=(0.20, 0.32), peso_panchina=0.20))
    return s


def genera_candidate(pool: dict, prezzi: dict, valori: dict, valori_up: dict,
                     regole: Regole, strategie: list | None = None,
                     posseduti: dict | None = None, budget: float | None = None,
                     tempo_solver: int = 8) -> list:
    """Una rosa ammissibile per ogni strategia. Le infattibili vengono saltate
    e dichiarate."""
    strategie = strategie or strategie_predefinite(regole.budget)
    fuori = []
    for st in strategie:
        forzato = ({"A": (st.quota_attacco[0] * regole.budget,
                          st.quota_attacco[1] * regole.budget)}
                   if st.quota_attacco else None)
        sol = optimize_roster(pool, prezzi, valori, regole.quote,
                              budget if budget is not None else regole.budget,
                              forced_spend=forzato, fixed=posseduti,
                              values_up=valori_up, lam=st.lam,
                              bench_weight=st.peso_panchina,
                              time_limit=tempo_solver, min_spend=st.min_spesa)
        if sol is None:
            fuori.append({"strategia": st.nome, "rosa": None,
                          "motivo": "nessuna rosa ammissibile con questi vincoli"})
            continue
        fuori.append({"strategia": st.nome, "rosa": sol["roster"],
                      "costo": sol["cost"], "modulo": sol["module"],
                      "valore_milp": sol["value"]})
    return fuori


# --------------------------------------------------------------------------
# valutazione con l'obiettivo vero
# --------------------------------------------------------------------------

def valuta_candidata(rosa: dict, pool: dict, prezzi: dict, valori: dict,
                     cubo, regole: Regole, scenari: list, seme_avversari: int,
                     n_avversari: int = 9, calendario=None,
                     seme_calendario: int = 0, giornate=None,
                     stato_iniziale=None, avversari_fissi: list | None = None,
                     modo_avversari: str = "milp") -> Esito:
    """P(primo posto) della rosa contro avversari costruiti dal pool residuo.

    Gli avversari cambiano con la candidata, ed e' giusto: nell'asta vera i
    giocatori che compriamo noi non li compra nessun altro. Con
    `avversari_fissi` gli avversari sono dati: serve ai confronti in cui il
    tavolo deve restare identico fra due trattamenti."""
    presi = {pid for r in rosa for pid in rosa[r]}
    if avversari_fissi is not None:
        avv = [a if isinstance(a, dict) and "rosa" not in a else a.get("rosa", a)
               for a in avversari_fissi]
        collisioni = [pid for a in avv for r in a for pid in a[r] if pid in presi]
        if collisioni:
            raise ValueError(
                f"{len(collisioni)} giocatori sono sia nella nostra rosa sia in "
                f"quella di un avversario: {collisioni[:5]}")
    else:
        costruttore = (avversari_milp_dal_pool if modo_avversari == "milp"
                       else avversari_dal_pool)
        avv = [a["rosa"] for a in costruttore(
            pool, prezzi, valori, regole, n_avversari, presi, seme_avversari)]
    rose = {"NOI": rosa}
    for i, a in enumerate(avv):
        rose[f"AVV{i + 1:02d}"] = a
    return valuta(cubo, rose, regole, calendario=calendario,
                  seme_calendario=seme_calendario, giornate=giornate,
                  stato_iniziale=stato_iniziale, scenari=scenari)


def scegli(candidate: list, pool: dict, prezzi: dict, valori: dict, cubo,
           regole: Regole, scenari_ricerca: list, scenari_verifica: list,
           seme_avversari: int = 0, n_avversari: int = 9,
           calendario=None, seme_calendario: int = 0, giornate=None,
           stato_iniziale=None, avversari_fissi: list | None = None) -> dict:
    """Ricerca su candidate per l'obiettivo SAA.

    Sceglie sugli scenari di ricerca, poi rigioca la vincente su scenari mai
    usati per sceglierla. Il numero riportato e' quello della verifica: quello
    della ricerca e' gonfiato dall'aver scelto il fortunato."""
    righe = []
    for c in candidate:
        if not c.get("rosa"):
            continue
        e = valuta_candidata(c["rosa"], pool, prezzi, valori, cubo, regole,
                             scenari_ricerca, seme_avversari, n_avversari,
                             calendario, seme_calendario, giornate,
                             stato_iniziale, avversari_fissi=avversari_fissi)
        p = e.p_primo()["NOI"]
        righe.append({**c, "p1_ricerca": p,
                      "se_ricerca": e.errore_standard()["NOI"],
                      "parita": e.diagnostica["scenari_con_parita_al_primo"]})
    if not righe:
        return {"migliore": None, "tabella": [], "verifica": None,
                "motivo": "nessuna candidata ammissibile"}
    righe.sort(key=lambda r: -r["p1_ricerca"])
    migliore = righe[0]
    ev = valuta_candidata(migliore["rosa"], pool, prezzi, valori, cubo, regole,
                          scenari_verifica, seme_avversari, n_avversari,
                          calendario, seme_calendario, giornate, stato_iniziale,
                          avversari_fissi=avversari_fissi)
    return {
        "migliore": migliore,
        "tabella": [{k: v for k, v in r.items() if k != "rosa"} for r in righe],
        "verifica": {"p1": ev.p_primo()["NOI"],
                     "se": ev.errore_standard()["NOI"],
                     "n_scenari": len(scenari_verifica),
                     "parita": ev.diagnostica["scenari_con_parita_al_primo"]},
        "nota": ("il numero da riportare e' quello della verifica: la ricerca "
                 "ha scelto il massimo fra le candidate e quel massimo e' "
                 "gonfiato"),
    }


# --------------------------------------------------------------------------
# scambi locali
# --------------------------------------------------------------------------

def scambi_locali(rosa: dict, pool: dict, prezzi: dict, valori: dict, cubo,
                  regole: Regole, scenari: list, seme_avversari: int,
                  budget: float, max_giri: int = 6, max_prove: int = 40,
                  n_avversari: int = 9, calendario=None,
                  seme_calendario: int = 0,
                  avversari_fissi: list | None = None) -> dict:
    """Migliora la rosa con scambi, valutando ogni proposta con P(primo posto).

    Iterativa: a ogni giro le proposte si ricalcolano dalla rosa **corrente**,
    e si tiene il miglior scambio del giro. Si ferma quando un giro intero non
    migliora, oppure dopo `max_giri`. Un solo giro non basta: dalla rosa
    peggiore al massimo servono piu' sostituzioni in fila, e ogni scambio
    cambia quali altri diventano convenienti.

    Uno scambio e' legale se la rosa resta completa, dentro il budget e senza
    duplicati. Le proposte si ordinano per differenza di valore atteso, che e'
    solo un modo di guardare prima le piu' promettenti: a decidere e'
    l'obiettivo vero.
    """
    def p1(r):
        e = valuta_candidata(r, pool, prezzi, valori, cubo, regole, scenari,
                             seme_avversari, n_avversari, calendario,
                             seme_calendario, avversari_fissi=avversari_fissi)
        return e.p_primo()["NOI"]

    corrente = {r: list(v) for r, v in rosa.items()}
    p_corrente = p1(corrente)
    p_partenza = p_corrente
    storia = []
    provate = 0
    for giro in range(max_giri):
        presi = {pid for r in corrente for pid in corrente[r]}
        speso = sum(max(1.0, prezzi.get(pid, 1.0))
                    for r in corrente for pid in corrente[r])
        residuo = budget - speso
        proposte = []
        for ruolo in regole.quote:
            fuori = [pid for pid, pl in pool.items()
                     if pl.role == ruolo and pid not in presi]
            for uscente in corrente[ruolo]:
                pu = max(1.0, prezzi.get(uscente, 1.0))
                for entrante in fuori:
                    pe = max(1.0, prezzi.get(entrante, 1.0))
                    if pe - pu > residuo:
                        continue
                    guadagno = valori.get(entrante, 0.0) - valori.get(uscente, 0.0)
                    proposte.append((guadagno, ruolo, uscente, entrante))
        proposte.sort(key=lambda t: (-t[0], str(t[2]), str(t[3])))
        migliore_giro = None
        for guadagno, ruolo, uscente, entrante in proposte[:max_prove]:
            nuova = {r: list(v) for r, v in corrente.items()}
            nuova[ruolo] = [entrante if x == uscente else x for x in nuova[ruolo]]
            p = p1(nuova)
            provate += 1
            if p > p_corrente + 1e-12 and (migliore_giro is None
                                           or p > migliore_giro[0]):
                migliore_giro = (p, nuova, uscente, entrante)
        if migliore_giro is None:
            break
        p_corrente, corrente, uscente, entrante = migliore_giro
        storia.append({"giro": giro + 1, "esce": uscente, "entra": entrante,
                       "p1": round(p_corrente, 5)})
    return {"rosa": corrente, "p1": p_corrente, "p1_partenza": p_partenza,
            "scambi": storia, "proposte_provate": provate,
            "giri": len(storia)}


# --------------------------------------------------------------------------
# enumerazione esatta, per verificare la ricerca su istanze piccole
# --------------------------------------------------------------------------

def rose_legali(pool: dict, prezzi: dict, regole: Regole,
                budget: float | None = None):
    """Tutte le rose legali di un'istanza piccola. Generatore."""
    budget = regole.budget if budget is None else budget
    per_ruolo = {}
    for ruolo, quanti in regole.quote.items():
        ids = sorted(pid for pid, p in pool.items() if p.role == ruolo)
        per_ruolo[ruolo] = list(itertools.combinations(ids, quanti))
    ruoli = list(regole.quote)
    for combo in itertools.product(*[per_ruolo[r] for r in ruoli]):
        rosa = {r: list(c) for r, c in zip(ruoli, combo)}
        costo = sum(max(1.0, prezzi.get(pid, 1.0)) for r in rosa for pid in rosa[r])
        if costo <= budget:
            yield rosa, costo


def enumera_esatto(pool: dict, prezzi: dict, valori: dict, cubo, regole: Regole,
                   scenari: list, seme_avversari: int = 0, n_avversari: int = 1,
                   calendario=None, seme_calendario: int = 0,
                   limite: int = 5000, avversari_fissi: list | None = None) -> dict:
    """Valuta OGNI rosa legale con l'obiettivo vero. Solo istanze piccole."""
    righe = []
    for i, (rosa, costo) in enumerate(rose_legali(pool, prezzi, regole)):
        if i >= limite:
            return {"migliore": None, "n": i,
                    "errore": f"piu' di {limite} rose legali: istanza troppo grande"}
        e = valuta_candidata(rosa, pool, prezzi, valori, cubo, regole, scenari,
                             seme_avversari, n_avversari, calendario,
                             seme_calendario, avversari_fissi=avversari_fissi)
        righe.append({"rosa": rosa, "costo": costo, "p1": e.p_primo()["NOI"]})
    if not righe:
        return {"migliore": None, "n": 0, "errore": "nessuna rosa legale"}
    righe.sort(key=lambda r: (-r["p1"], r["costo"]))
    return {"migliore": righe[0], "tutte": righe, "n": len(righe),
            "p1_massima": righe[0]["p1"]}
