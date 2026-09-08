"""Chi scende in campo, in che ruolo e per quanti minuti.

Il simulatore attuale tratta la disponibilita' come una moneta per giocatore,
indipendente dai compagni. Va bene per contare le presenze, non per generare
una partita: undici monete indipendenti danno squadre con nove o tredici
titolari, e minuti che non stanno dentro i novanta.

Qui la generazione e' vincolata alla struttura della partita:

  1. **squadra convocata** — per ogni giocatore, una catena con memoria dice se
     e' a disposizione. Non e' un modello clinico degli infortuni: la fonte
     dice solo se il giocatore compare fra i convocati, e infortunio,
     squalifica e scelta tecnica stanno insieme. La quantita' modellata e'
     quella, e il nome lo dice.
  2. **undici titolari** — fra i disponibili si estrae senza reimmissione con
     rumore di Gumbel sulla propensione (equivale a un modello di Plackett e
     Luce). Il numero di titolari per ruolo viene da un modulo estratto dalla
     distribuzione storica di quella squadra: cosi' escono sempre 1 portiere e
     10 di movimento, con reparti plausibili.
  3. **panchina e sostituzioni** — i primi esclusi vanno in panchina; il numero
     di sostituzioni e il minuto d'ingresso si estraggono dalla distribuzione
     storica. Ogni giocatore esce con un intervallo [entrata, uscita) in
     minuti, e la somma dei minuti della squadra e' coerente per costruzione.

## Il cambio del portiere e' un evento a parte

Fino alla correzione del 7 settembre 2026 le uscite si estraevano fra tutti e
undici i titolari, portiere compreso, e a entrare erano i primi della panchina,
che `scegli_undici` ordina mettendo il portiere di riserva in fondo. Il
risultato era una squadra senza portiere: nel cubo il 37,0 % delle
squadra-partita aveva minuti senza nessun portiere in campo.

Il cambio del portiere e' un evento raro e di natura diversa da un cambio di
movimento, e va stimato per conto suo. Misurato sul panel (script
`data/l3/fix/generatore/m0_dati.py`, 3 038 squadra-partita delle stagioni
2021-22, 2023-24, 2024-25 e 2025-26): **42 squadra-partita su 3 038, cioe'
l'1,382 %, vedono entrare un portiere dalla panchina**, con minuto d'ingresso
di media 58,3 e mediana 61,5. Nella stessa finestra le sostituzioni di
movimento sono in media 4,436 per squadra-partita contro 4,450 sostituzioni
totali: la differenza, 0,014, e' esattamente il tasso del cambio del portiere.
I due eventi sono quindi additivi, e il codice li tiene additivi.

## Un giocatore di movimento in porta

Succede quando il portiere titolare lascia il campo e non c'e' un portiere di
riserva utilizzabile. Non e' una probabilita' inventata: e' una conseguenza
strutturale dell'espulsione del portiere, e il codice la produce solo in quel
caso. Sui dati: 9 portieri titolari espulsi in quattro stagioni, di cui **2
senza nessun portiere subentrato** (2 su 3 038 squadra-partita, lo 0,066 %).
Con nove osservazioni non si stima una probabilita': si applica la regola
fisica e si dichiara la frequenza osservata.

## Propensione individuale

La propensione a essere titolare e' stimata per giocatore con contrazione
verso la media del suo ruolo, proporzionale a quante partite ha alle spalle:
chi ha giocato poco resta vicino alla media del ruolo invece di prendere un
valore estremo. Per i giocatori senza storia in Serie A la propensione e'
quella del ruolo, con incertezza dichiarata.

## Il denominatore delle propensioni

Il contratto degli stati (`reports/CRITERI_L2_L3.md`, sezione 7.1) impone che
ogni propensione si calcoli **solo sulle righe con `eleggibile == True`**: le
righe con `eleggibile` nullo non stanno ne' al numeratore ne' al denominatore,
perche' non sono un'assenza ma un'ignoranza. Quando il panel porta quella
colonna, questo modulo la usa. Quando non la porta — panel prodotto prima della
correzione — non c'e' nessun modo di distinguere un'esclusione documentata da
un'ignoranza, e il modulo ripiega sul criterio vecchio **dichiarandolo** in
`diagnostica["denominatore"]`: chi legge quel modello sa che le propensioni
sono stimate su un denominatore non verificato.

## La catena con memoria non conserva il tasso medio

Aggiungere uno scostamento al logit della convocazione non lascia invariata la
probabilita' media prodotta dalla catena: la catena passa piu' tempo negli
stati con memoria lunga, e quegli stati hanno scostamenti asimmetrici. Il
modello quindi non usa direttamente `logit(prop_convocato)` come base, ma
`logit_base_convocato`, calcolato invertendo numericamente la catena in modo
che la sua **distribuzione stazionaria** dia esattamente la propensione
desiderata. Lo scarto prima della correzione e' misurato in
`diagnostica["catena_convocazione"]`.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

RUOLI = ("P", "D", "C", "A")
MAX_RUN = 8
# moduli in termini di ruoli del fantacalcio (portiere sempre 1)
MIN_PER_RUOLO = {"P": 1, "D": 3, "C": 3, "A": 1}
# stati che significano "il giocatore era fra i convocati di quella partita".
# Valgono sia per il panel nuovo sia per quello vecchio: sono gli unici stati
# che i due contratti hanno in comune.
CONVOCATI = ("titolare", "panchina_entrato", "panchina_non_entrato")
# stati che il panel vecchio usava per dire "non convocato". `non_in_rosa` non
# era uno stato del giocatore ma un'affermazione non provata (contratto 7.1):
# resta qui solo per poter leggere i panel prodotti prima della correzione.
NON_CONVOCATI_VECCHI = ("non_in_rosa", "fuori_lista")
FINE_PARTITA = 90


@dataclass
class Presenze:
    """Chi e' in campo, quando, e chi sta in porta.

    `intervalli` e' l'oggetto che il resto del codice usava gia': master_id ->
    [entrata, uscita), in minuti. Gli altri campi servono alle invarianti
    fisiche, che con i soli intervalli non sono esprimibili:

      * `portiere` e' la successione dei periodi con il rispettivo portiere,
        come terne (inizio, fine, master_id, di_movimento). Copre sempre tutti
        i novanta minuti: e' l'invariante 7.4.1 del contratto.
      * `sostituzioni` accoppia chi esce e chi entra, cosi' un'espulsione puo'
        annullare la sostituzione che avrebbe riguardato l'espulso.
      * `espulsi` porta il minuto del cartellino rosso, che chiude l'intervallo
        e impedisce la sostituzione.
    """
    intervalli: dict
    portiere: list = field(default_factory=list)
    sostituzioni: list = field(default_factory=list)
    espulsi: dict = field(default_factory=dict)
    note: dict = field(default_factory=dict)

    def in_campo(self, pid, minuto) -> bool:
        return in_campo_al(self.intervalli.get(pid), minuto)

    def presenti(self, minuto) -> list:
        return [pid for pid, iv in self.intervalli.items()
                if in_campo_al(iv, minuto)]

    def portiere_al(self, minuto):
        """Chi era in porta al minuto dato, o None se non c'era nessuno."""
        for a, b, pid, _ in self.portiere:
            if a <= minuto < b or (b >= FINE_PARTITA and minuto >= b):
                return pid
        return None

    def minuti_senza_portiere(self) -> int:
        coperti = set()
        for a, b, _, _ in self.portiere:
            coperti.update(range(int(a), int(min(b, FINE_PARTITA))))
        return FINE_PARTITA - len(coperti & set(range(FINE_PARTITA)))


def in_campo_al(intervallo, minuto) -> bool:
    """Presenza al minuto dato, con la convenzione [entrata, uscita).

    L'intervallo e' chiuso a sinistra e aperto a destra: chi esce al 60' non e'
    piu' in campo al 60', chi entra al 60' lo e'. Con la convenzione chiusa da
    entrambi i lati, due sostituzioni allo stesso minuto facevano risultare
    tredici o quattordici giocatori in campo.

    L'ultimo minuto e' il caso speciale: la fonte degli eventi registra al
    minuto 90 tutto quello che accade dal 90' in poi, recuperi compresi (il
    7,57 % dei gol). Con l'aperto a destra secco, al minuto 90 non c'e'
    **nessuno** in campo e ogni gol del recupero finiva in un ripiego che lo
    assegnava anche a chi era gia' uscito. Chi finisce la partita e' quindi in
    campo anche al 90' e oltre."""
    if intervallo is None:
        return False
    a, b = intervallo
    if b <= a:
        return False
    if b >= FINE_PARTITA and minuto >= b:
        return True
    return a <= minuto < b


@dataclass
class ModelloPartecipazione:
    """Tutto quello che serve a generare convocati, undici e minuti."""
    prop_titolare: dict          # master_id -> logit di P(titolare | convocato)
    prop_convocato: dict         # master_id -> P(convocato) di base
    ruolo: dict                  # master_id -> P/D/C/A
    squadra: dict                # master_id -> squadra
    moduli: dict                 # squadra -> [(nD, nC, nA), peso]
    moduli_lega: list            # ripiego per squadre senza storia
    offset_convocato: dict       # (presente, run) -> scostamento sul logit
    p_sostituzioni: np.ndarray   # distribuzione dei cambi DI MOVIMENTO
    minuti_ingresso: np.ndarray  # campione dei minuti d'ingresso osservati
    minuti_uscita: np.ndarray    # campione dei minuti d'uscita dei titolari
    p_titolare_sostituito: float
    # --- invarianti fisiche (correzione del 7 settembre 2026) --------------
    p_cambio_portiere: float = 0.0
    minuti_cambio_portiere: np.ndarray = field(
        default_factory=lambda: np.array([60.0]))
    # base del logit corretta perche' la catena con memoria riproduca
    # `prop_convocato`; vuoto = si usa logit(prop_convocato) come prima
    logit_base_convocato: dict = field(default_factory=dict)
    # giocatori di cui è DIMOSTRATA l'indisponibilita' (squalifica nota,
    # infortunio dichiarato). Vuoto per costruzione: il panel non lo dice.
    indisponibile_certo: set = field(default_factory=set)
    diagnostica: dict = field(default_factory=dict)

    def base_convocazione(self, pid) -> float:
        """Logit di base da usare nella catena, calibrato se disponibile."""
        if pid in self.logit_base_convocato:
            return float(self.logit_base_convocato[pid])
        p = min(max(float(self.prop_convocato.get(pid, 0.6)), 0.02), 0.98)
        return float(np.log(p / (1 - p)))


def _logit(p, eps=1e-4):
    p = np.clip(p, eps, 1 - eps)
    return np.log(p / (1 - p))


def _maschera_eleggibili(P: pd.DataFrame) -> tuple[pd.Series, dict]:
    """Righe che possono stare al denominatore delle propensioni.

    Contratto 7.1: solo `eleggibile == True`. Se la colonna non c'e' — panel
    prodotto prima della correzione — non esiste nessuna prova di appartenenza,
    e il criterio vecchio (tutte le righe con formazioni note) resta l'unico
    applicabile. In quel caso la nota lo dichiara: le propensioni escono da un
    denominatore non verificato, e chi legge il modello deve saperlo.
    """
    if "eleggibile" in P.columns:
        col = P["eleggibile"]
        # colonna nullable: il nullo NON e' un'assenza, e' un'ignoranza
        m = col.fillna(False).astype(bool) if hasattr(col, "fillna") else col.astype(bool)
        nota = {
            "criterio": "eleggibile == True",
            "verificato": True,
            "righe_totali": int(len(P)),
            "righe_eleggibili": int(m.sum()),
            "righe_ignote": int(col.isna().sum()) if hasattr(col, "isna") else 0,
        }
        return m, nota
    m = P["stato_convocazione"].isin(CONVOCATI + NON_CONVOCATI_VECCHI)
    return m, {
        "criterio": "panel senza colonna `eleggibile`: si usano tutte le righe "
                    "con stato di convocazione noto",
        "verificato": False,
        "avvertenza": "denominatore NON verificato: le righe `non_in_rosa` "
                      "entrano al denominatore senza prova di appartenenza al "
                      "club (contratto 7.1). Le propensioni di convocazione "
                      "sono quindi distorte verso il basso di una quantita' "
                      "non misurabile con questo panel.",
        "righe_totali": int(len(P)),
        "righe_eleggibili": int(m.sum()),
    }


def _in_lista(P: pd.DataFrame) -> pd.Series:
    """1 se il giocatore era fra i convocati di quella partita."""
    return P["stato_convocazione"].isin(CONVOCATI).astype(int)


def _offset_da_panel(P: pd.DataFrame) -> dict:
    """Scostamenti sul logit della convocazione secondo la striscia in corso.

    Misurati sul panel: per ogni giocatore, la sequenza delle convocazioni
    nell'ordine delle giornate. Lo scostamento e' rispetto al tasso
    individuale, quindi al netto della differenza fra titolari e riserve.

    Il denominatore e' quello del contratto: solo le righe eleggibili.
    """
    maschera, _ = _maschera_eleggibili(P)
    d = P[maschera].copy()
    d["in_lista"] = _in_lista(d)
    d = d.sort_values(["stagione", "master_id", "giornata"])
    tassi = d.groupby(["stagione", "master_id"])["in_lista"].transform("mean")
    # chi non compare MAI fra i convocati di quella squadra (ceduto, mai
    # tesserato) e chi c'e' sempre non informano sulla memoria della striscia:
    # il loro logit individuale e' degenere e trascinerebbe gli scostamenti
    d = d[(tassi > 0.05) & (tassi < 0.95)]
    tassi = tassi[d.index]
    d["logit_ind"] = _logit(tassi)
    stato, run, prec_id = [], [], None
    s_cur, r_cur = None, 0
    for mid, v in zip(zip(d.stagione, d.master_id), d.in_lista):
        if mid != prec_id:
            prec_id, s_cur, r_cur = mid, None, 0
            stato.append(np.nan)
            run.append(0)
        else:
            stato.append(s_cur)
            run.append(r_cur)
        if s_cur is None or s_cur != v:
            s_cur, r_cur = v, 1
        else:
            r_cur += 1
    d["stato_prec"] = stato
    d["run_prec"] = run
    d = d[d.run_prec > 0]
    fuori = {}
    for presente in (0, 1):
        for r in range(1, MAX_RUN + 1):
            sel = d[(d.stato_prec == presente)
                    & (d.run_prec.clip(upper=MAX_RUN) == r)]
            if len(sel) < 200:
                continue
            osservato = _logit(sel.in_lista.mean())
            atteso = sel.logit_ind.mean()
            fuori[(bool(presente), r)] = float(osservato - atteso)
    return fuori


# --------------------------------------------------------------------------
# La catena con memoria: quanto vale davvero il tasso di convocazione
# --------------------------------------------------------------------------

def media_catena(base: float, offset_convocato: dict) -> float:
    """Tasso medio di convocazione prodotto dalla catena, a regime.

    Lo stato e' (era presente all'ultima giornata, da quante giornate di
    seguito), con la striscia limitata a MAX_RUN come nel generatore. La
    probabilita' di convocazione in ciascuno stato e' la sigmoide di
    `base + offset(stato)`. Il tasso medio non e' la sigmoide di `base`: la
    catena passa piu' tempo in certi stati che in altri, e gli scostamenti
    sono asimmetrici.

    Si risolve la distribuzione stazionaria del sistema lineare invece di
    iterare: e' esatta e costa una fattorizzazione 16x16.
    """
    stati = [(s, r) for s in (0, 1) for r in range(1, MAX_RUN + 1)]
    ix = {st: i for i, st in enumerate(stati)}
    n = len(stati)
    M = np.zeros((n, n))
    for (s, r) in stati:
        off = offset_convocato.get((bool(s), min(r, MAX_RUN)), 0.0)
        p = 1.0 / (1.0 + np.exp(-(base + off)))
        succ_1 = (1, min(r + 1, MAX_RUN)) if s == 1 else (1, 1)
        succ_0 = (0, min(r + 1, MAX_RUN)) if s == 0 else (0, 1)
        M[ix[(s, r)], ix[succ_1]] += p
        M[ix[(s, r)], ix[succ_0]] += 1.0 - p
    # pi (M - I) = 0 con somma 1: si sostituisce un'equazione con il vincolo
    A = (M.T - np.eye(n))
    A[-1, :] = 1.0
    b = np.zeros(n)
    b[-1] = 1.0
    try:
        pi = np.linalg.solve(A, b)
    except np.linalg.LinAlgError:
        return float(1.0 / (1.0 + np.exp(-base)))
    pi = np.clip(pi, 0, None)
    pi = pi / max(pi.sum(), 1e-12)
    return float(sum(pi[ix[(1, r)]] for r in range(1, MAX_RUN + 1)))


def inverti_catena(bersaglio: float, offset_convocato: dict,
                   giri: int = 60) -> float:
    """Base del logit tale che la catena produca `bersaglio` come tasso medio.

    Bisezione: `media_catena` e' monotona crescente in `base` perche' lo e' la
    sigmoide in ogni stato.
    """
    lo, hi = -14.0, 14.0
    for _ in range(giri):
        mid = 0.5 * (lo + hi)
        if media_catena(mid, offset_convocato) < bersaglio:
            lo = mid
        else:
            hi = mid
    return 0.5 * (lo + hi)


def calibra_base_convocazione(prop_convocato: dict, offset_convocato: dict,
                              punti: int = 121) -> tuple[dict, dict]:
    """Per ogni giocatore, la base del logit che conserva il suo tasso.

    Si invertono `punti` bersagli su una griglia e si interpola: invertire la
    catena giocatore per giocatore darebbe lo stesso risultato a meno di 1e-4 e
    costerebbe seicento volte tanto.
    """
    if not offset_convocato:
        return {}, {"nota": "nessuno scostamento stimato: base = logit(p)"}
    griglia = np.linspace(0.02, 0.98, punti)
    basi = np.array([inverti_catena(float(p), offset_convocato) for p in griglia])
    fuori = {}
    scarti_prima = []
    for pid, p in prop_convocato.items():
        pc = float(min(max(p, 0.02), 0.98))
        fuori[pid] = float(np.interp(pc, griglia, basi))
        scarti_prima.append(media_catena(float(np.log(pc / (1 - pc))),
                                         offset_convocato) - pc)
    scarti_prima = np.array(scarti_prima) if scarti_prima else np.zeros(1)
    # controllo del risultato: la catena calibrata, sugli stessi bersagli
    controllo = [media_catena(float(np.interp(x, griglia, basi)),
                              offset_convocato) - x
                 for x in np.linspace(0.05, 0.95, 19)]
    diag = {
        "punti_griglia": int(punti),
        "scarto_medio_prima": float(np.mean(scarti_prima)),
        "scarto_assoluto_medio_prima": float(np.mean(np.abs(scarti_prima))),
        "scarto_massimo_prima": float(np.max(np.abs(scarti_prima))),
        "scarto_assoluto_medio_dopo": float(np.mean(np.abs(controllo))),
        "scarto_massimo_dopo": float(np.max(np.abs(controllo))),
    }
    return fuori, diag


def stima(panel: pd.DataFrame, as_of: str | None = None,
          min_partite: int = 5) -> ModelloPartecipazione:
    """Stima il modello sul panel, usando solo partite anteriori a `as_of`."""
    P = panel.copy()
    P["data"] = pd.to_datetime(P["data"])
    if as_of is not None:
        P = P[P["data"] < pd.Timestamp(as_of)]
    maschera, nota_denominatore = _maschera_eleggibili(P)
    P = P[maschera]
    if P.empty:
        raise ValueError("nessuna riga eleggibile prima di as_of")
    P = P.copy()
    P["in_lista"] = _in_lista(P)
    P["titolare"] = (P.stato_convocazione == "titolare").astype(int)
    P["ruolo_n"] = P["ruolo"].astype(str).str.upper()

    # propensione a essere convocato e titolare, con contrazione al ruolo
    agg = (P.groupby(["master_id", "ruolo"])
             .agg(n=("in_lista", "size"), conv=("in_lista", "mean"),
                  n_lista=("in_lista", "sum"), tit=("titolare", "sum"))
             .reset_index())
    agg["p_tit"] = agg["tit"] / agg["n_lista"].clip(lower=1)
    medie = P.groupby("ruolo").agg(conv=("in_lista", "mean")).to_dict()["conv"]
    tit_ruolo = (P[P.in_lista == 1].groupby("ruolo")["titolare"].mean().to_dict())
    prop_conv, prop_tit = {}, {}
    for r in agg.itertuples(index=False):
        k = min_partite
        base_c = medie.get(r.ruolo, 0.6)
        base_t = tit_ruolo.get(r.ruolo, 0.5)
        pc = (r.conv * r.n + base_c * k) / (r.n + k)
        # il denominatore puo' essere zero solo con `min_partite = 0` e un
        # giocatore mai convocato: in quel caso la propensione a essere
        # titolare non e' definita e vale quella del ruolo
        pt = ((r.p_tit * r.n_lista + base_t * k) / (r.n_lista + k)
              if (r.n_lista + k) > 0 else base_t)
        prop_conv[r.master_id] = float(pc)
        prop_tit[r.master_id] = float(_logit(pt))

    # moduli osservati: quanti titolari per ruolo mette quella squadra
    tit = P[P.titolare == 1]
    conta = (tit.groupby(["stagione", "giornata", "squadra_alla_data", "ruolo"])
                .size().unstack(fill_value=0).reset_index())
    for r in RUOLI:
        if r not in conta:
            conta[r] = 0
    conta = conta[(conta["P"] == 1) & (conta[list(RUOLI)].sum(axis=1) == 11)]
    moduli = {}
    for sq, sub in conta.groupby("squadra_alla_data"):
        v = sub.groupby(["D", "C", "A"]).size()
        moduli[sq] = [(tuple(int(x) for x in k), int(n)) for k, n in v.items()]
    v = conta.groupby(["D", "C", "A"]).size()
    moduli_lega = [(tuple(int(x) for x in k), int(n)) for k, n in v.items()]

    # --- sostituzioni: quelle di movimento e, separato, il cambio del portiere
    chiave = ["stagione", "giornata", "squadra_alla_data"]
    squadra_partita = P.groupby(chiave).ngroups
    entrati = P[P.stato_convocazione == "panchina_entrato"]
    entrati_mov = entrati[entrati.ruolo_n != "P"]
    entrati_p = entrati[entrati.ruolo_n == "P"]
    n_sost = entrati_mov.groupby(chiave).size().value_counts().sort_index()
    p_sost = np.zeros(7)
    for k, n in n_sost.items():
        if 0 <= int(k) < len(p_sost):
            p_sost[int(k)] += n
    # le squadra-partita senza nessun cambio di movimento non compaiono nel
    # value_counts: vanno contate nella casella zero, o la media dei cambi
    # esce piu' alta del vero
    senza = max(squadra_partita - int(n_sost.sum()), 0)
    p_sost[0] += senza
    p_sost = p_sost / max(p_sost.sum(), 1)

    n_cambi_p = entrati_p.groupby(chiave).size()
    p_cambio_p = float(len(n_cambi_p) / max(squadra_partita, 1))
    min_p = pd.to_numeric(entrati_p["minuti"], errors="coerce").dropna().values
    min_cambio_p = np.clip(90.0 - min_p, 1, 89) if len(min_p) else np.array([60.0])

    min_ing = pd.to_numeric(entrati["minuti"], errors="coerce").dropna()
    min_ing = np.clip(90 - min_ing.values, 0, 89)
    tit_min = pd.to_numeric(P.loc[P.titolare == 1, "minuti"],
                            errors="coerce").dropna().values
    p_tit_sost = float(np.mean(tit_min < 88)) if len(tit_min) else 0.35
    min_usc = tit_min[tit_min < 88] if len(tit_min) else np.array([65.0])

    offsets = _offset_da_panel(P)
    basi, diag_catena = calibra_base_convocazione(prop_conv, offsets)

    return ModelloPartecipazione(
        prop_titolare=prop_tit, prop_convocato=prop_conv,
        ruolo=dict(zip(agg.master_id, agg.ruolo)),
        squadra=dict(zip(P.master_id, P.squadra_alla_data)),
        moduli=moduli, moduli_lega=moduli_lega,
        offset_convocato=offsets,
        p_sostituzioni=p_sost,
        minuti_ingresso=min_ing if len(min_ing) else np.array([20.0]),
        minuti_uscita=min_usc if len(min_usc) else np.array([65.0]),
        p_titolare_sostituito=p_tit_sost,
        p_cambio_portiere=p_cambio_p,
        minuti_cambio_portiere=min_cambio_p,
        logit_base_convocato=basi,
        diagnostica={
            "righe": int(len(P)),
            "giocatori": int(agg.master_id.nunique()),
            "squadre_con_moduli": len(moduli),
            "moduli_lega_piu_frequenti": sorted(moduli_lega, key=lambda x: -x[1])[:5],
            "quota_titolari_sostituiti": round(p_tit_sost, 4),
            "media_sostituzioni_movimento": round(
                float((np.arange(len(p_sost)) * p_sost).sum()), 3),
            "squadra_partita": int(squadra_partita),
            "cambio_portiere": {
                "squadra_partita_con_cambio": int(len(n_cambi_p)),
                "probabilita": round(p_cambio_p, 5),
                "minuto_medio": (round(float(np.mean(min_cambio_p)), 2)
                                 if len(min_cambio_p) else None),
            },
            "denominatore": nota_denominatore,
            "catena_convocazione": diag_catena,
            "offset_convocazione": {f"{'presente' if k[0] else 'assente'}_{k[1]}":
                                    round(v, 4)
                                    for k, v in offsets.items()},
        })


def offset(mod: ModelloPartecipazione, presente: bool, run: int) -> float:
    return mod.offset_convocato.get((presente, min(run, MAX_RUN)), 0.0)


def estrai_modulo(mod: ModelloPartecipazione, squadra: str,
                  rng: np.random.Generator,
                  disponibili: dict | None = None) -> tuple[int, int, int]:
    """Modulo estratto dalla distribuzione storica della squadra.

    Con `disponibili` (quanti giocatori per ruolo sono convocati) si scartano i
    moduli che quella sera non si potrebbero schierare: senza il filtro un
    modulo a cinque difensori con solo quattro difensori disponibili faceva
    scendere in campo dieci giocatori."""
    voci = mod.moduli.get(squadra) or mod.moduli_lega
    if disponibili:
        ok = [(m, n) for m, n in voci
              if disponibili.get("D", 0) >= m[0]
              and disponibili.get("C", 0) >= m[1]
              and disponibili.get("A", 0) >= m[2]
              and disponibili.get("P", 0) >= 1]
        if ok:
            voci = ok
    pesi = np.array([n for _, n in voci], dtype=float)
    pesi = pesi / pesi.sum()
    return voci[int(rng.choice(len(voci), p=pesi))][0]


def adatta_modulo(modulo: tuple[int, int, int], disponibili: dict) -> dict:
    """Adatta il modulo a chi c'e' davvero, restando a undici.

    Se un reparto e' corto, i posti mancanti passano ai reparti che hanno
    riserve. Senza questo passaggio una squadra con quattro difensori convocati
    e un modulo a cinque scendeva in campo in dieci.
    """
    need = {"P": min(1, disponibili.get("P", 0)),
            "D": modulo[0], "C": modulo[1], "A": modulo[2]}
    for r in ("D", "C", "A"):
        need[r] = min(need[r], disponibili.get(r, 0))
    mancano = 11 - sum(need.values())
    if mancano > 0:
        # prima i reparti con piu' riserve; l'ordine alfabetico rompe i pareggi
        for r in sorted(("D", "C", "A"),
                        key=lambda x: (-(disponibili.get(x, 0) - need[x]), x)):
            spazio = disponibili.get(r, 0) - need[r]
            preso = max(0, min(spazio, mancano))
            need[r] += preso
            mancano -= preso
            if mancano <= 0:
                break
    return need


def scegli_undici(candidati: list, mod: ModelloPartecipazione,
                  modulo: tuple[int, int, int], rng: np.random.Generator,
                  u: np.ndarray | None = None) -> tuple[list, list]:
    """Estrazione senza reimmissione con rumore di Gumbel (Plackett-Luce).

    Ritorna (titolari, panchina). I titolari sono sempre undici con un solo
    portiere: se un reparto e' corto, il modulo si adatta ai convocati
    (`adatta_modulo`) invece di far scendere in campo dieci giocatori."""
    # chi non ha un ruolo noto finisce a centrocampo invece che sparire: un
    # giocatore perso qui faceva scendere in campo squadre di dieci
    per_ruolo = {r: [pid for pid in candidati
                     if (mod.ruolo.get(pid) if mod.ruolo.get(pid) in RUOLI
                         else "C") == r]
                 for r in RUOLI}
    need = adatta_modulo(modulo, {r: len(v) for r, v in per_ruolo.items()})
    if u is None:
        u = rng.random(len(candidati))
    pos = {pid: i for i, pid in enumerate(candidati)}
    ordinati = {}
    for r in RUOLI:
        lista = per_ruolo[r]
        if not lista:
            ordinati[r] = []
            continue
        s = np.array([mod.prop_titolare.get(pid, 0.0) for pid in lista])
        uu = np.clip(np.array([u[pos[pid]] for pid in lista]), 1e-9, 1 - 1e-9)
        gumbel = -np.log(-np.log(uu))
        # l'identita' del giocatore rompe i pareggi: senza, l'ordine
        # dell'elenco in ingresso cambierebbe la formazione
        ordine = sorted(range(len(lista)),
                        key=lambda i: (-(s[i] + gumbel[i]), str(lista[i])))
        ordinati[r] = [lista[i] for i in ordine]
    titolari, resto = [], {}
    for r in RUOLI:
        k = min(need[r], len(ordinati[r]))
        titolari += ordinati[r][:k]
        resto[r] = ordinati[r][k:]
    # una squadra scende sempre in campo in undici: se un reparto e' corto, il
    # posto va al miglior escluso di qualunque reparto (con il portiere per
    # ultimo, che in campo ce ne sta uno solo)
    if len(titolari) < 11:
        coda = [pid for r in ("D", "C", "A", "P") for pid in resto[r]]
        for pid in coda:
            if len(titolari) >= 11:
                break
            if mod.ruolo.get(pid) == "P" and any(
                    mod.ruolo.get(x) == "P" for x in titolari):
                continue
            titolari.append(pid)
            ru = mod.ruolo.get(pid)
            resto[ru if ru in RUOLI else "C"].remove(pid)
    # ordine della panchina = chi ha piu' probabilita' di entrare. Il portiere
    # di riserva va in fondo: entra solo se il titolare esce, che e' raro.
    # Ordinare per ruolo lo faceva entrare a ogni partita.
    panchina = [pid for r in RUOLI for pid in resto[r] if pid not in titolari]
    panchina.sort(key=lambda pid: (mod.ruolo.get(pid) == "P",
                                   -mod.prop_titolare.get(pid, 0.0), str(pid)))
    return titolari[:11], panchina


def genera_minuti(titolari: list, panchina: list, mod: ModelloPartecipazione,
                  rng: np.random.Generator) -> Presenze:
    """Intervalli [entrata, uscita) in minuti, coerenti fra loro.

    Due estrazioni separate, perche' sono due eventi diversi (contratto 7.4.2):

      * i cambi **di movimento**, il cui numero viene dalla distribuzione
        storica dei soli subentrati di movimento; chi esce si estrae fra i dieci
        titolari di movimento, mai fra i portieri;
      * il cambio del **portiere**, con probabilita' `p_cambio_portiere`
        stimata sul panel, che fa entrare il portiere di riserva al posto di
        quello titolare.

    Il numero di sostituzioni e' lo stesso da entrambi i lati di ogni cambio,
    cosi' la squadra ha sempre undici in campo e sempre un portiere.
    """
    ruolo = mod.ruolo
    tit_p = [p for p in titolari if ruolo.get(p) == "P"]
    tit_mov = [p for p in titolari if ruolo.get(p) != "P"]
    pan_p = [p for p in panchina if ruolo.get(p) == "P"]
    pan_mov = [p for p in panchina if ruolo.get(p) != "P"]

    intervalli = {pid: [0, FINE_PARTITA] for pid in titolari}
    for pid in panchina:
        intervalli[pid] = [0, 0]
    sostituzioni = []

    n_sost = int(rng.choice(len(mod.p_sostituzioni), p=mod.p_sostituzioni))
    n_sost = min(n_sost, len(pan_mov), len(tit_mov))
    if n_sost:
        # chi esce si estrae da un elenco ordinato per identita': cosi' l'ordine
        # con cui i titolari sono stati scelti non cambia le sostituzioni
        ordinati = sorted(tit_mov, key=str)
        escono = list(rng.choice(len(ordinati), size=n_sost, replace=False))
        minuti = np.sort(rng.choice(mod.minuti_uscita, size=n_sost))
        entrano = list(pan_mov[:n_sost])
        for i, (k, m) in enumerate(zip(escono, minuti)):
            m = int(np.clip(m, 1, 89))
            intervalli[ordinati[k]][1] = m
            intervalli[entrano[i]] = [m, FINE_PARTITA]
            sostituzioni.append((m, ordinati[k], entrano[i]))

    # cambio del portiere: evento separato, con la sua probabilita'
    portiere = []
    if tit_p:
        p0 = tit_p[0]
        if pan_p and rng.random() < mod.p_cambio_portiere:
            m = int(np.clip(rng.choice(mod.minuti_cambio_portiere), 1, 89))
            p1 = pan_p[0]
            intervalli[p0][1] = m
            intervalli[p1] = [m, FINE_PARTITA]
            sostituzioni.append((m, p0, p1))
            portiere = [(0, m, p0, False), (m, FINE_PARTITA, p1, False)]
        else:
            portiere = [(0, FINE_PARTITA, p0, False)]
    return Presenze(intervalli=intervalli, portiere=portiere,
                    sostituzioni=sostituzioni, espulsi={},
                    note={"cambi_movimento": n_sost,
                          "cambio_portiere": len(portiere) > 1})


def applica_espulsione(pres: Presenze, pid, minuto: int,
                       mod: ModelloPartecipazione) -> dict:
    """Chiude l'intervallo dell'espulso e lascia la squadra in inferiorita'.

    Regole applicate, tutte e tre conseguenze della stessa cosa (l'espulso
    lascia il campo e non puo' essere rimpiazzato):

      1. l'intervallo dell'espulso si chiude al minuto del cartellino;
      2. se per lui era prevista una sostituzione dopo quel minuto, la
         sostituzione **non avviene**: chi sarebbe entrato resta in panchina.
         Un allenatore vero userebbe comunque il cambio su un altro giocatore,
         ma quale non e' ricostruibile; l'effetto sul numero medio di cambi e'
         limitato alle partite con espulsione (9,7 % delle squadra-partita) ed
         e' misurato nel rapporto;
      3. se l'espulso e' il portiere, entra il portiere di riserva al posto di
         un giocatore di movimento (la squadra resta comunque in dieci); se in
         panchina non c'e' nessun portiere, uno di movimento va in porta e la
         cosa viene rappresentata esplicitamente, non taciuta.

    Ritorna un dizionario con quello che e' successo, per la diagnostica.
    """
    esito = {"minuto": int(minuto), "sostituzione_annullata": None,
             "portiere_di_movimento": None, "portiere_di_riserva": None}
    iv = pres.intervalli.get(pid)
    if iv is None or not in_campo_al(iv, minuto):
        esito["ignorata"] = "il giocatore non era in campo a quel minuto"
        return esito
    era_portiere = any(p == pid for _, _, p, _ in pres.portiere)
    # 1 e 2
    for m, uscito, entrato in list(pres.sostituzioni):
        if uscito == pid and m > minuto:
            pres.intervalli[entrato] = [0, 0]
            pres.sostituzioni.remove((m, uscito, entrato))
            esito["sostituzione_annullata"] = entrato
    pres.intervalli[pid] = [iv[0], int(minuto)]
    pres.espulsi[pid] = int(minuto)

    if era_portiere:
        # il segmento del portiere espulso si chiude qui, e tutto quello che
        # era previsto dopo decade: la sostituzione che lo riguardava e' gia'
        # stata annullata al punto 2, quindi da questo minuto in poi la porta
        # e' scoperta finche' qualcuno non la prende.
        nuovi = [(a, b, p, mov) for a, b, p, mov in pres.portiere
                 if b <= minuto]
        nuovi += [(a, int(minuto), p, mov) for a, b, p, mov in pres.portiere
                  if a < minuto < b]
        fine_segmento = FINE_PARTITA
        riserva = [p for p in pres.intervalli
                   if mod.ruolo.get(p) == "P" and p != pid
                   and pres.intervalli[p][1] <= pres.intervalli[p][0]]
        riserva.sort(key=lambda p: (-mod.prop_titolare.get(p, 0.0), str(p)))
        if riserva:
            p1 = riserva[0]
            pres.intervalli[p1] = [int(minuto), fine_segmento]
            # per far posto al portiere esce un giocatore di movimento: la
            # squadra e' gia' in dieci per l'espulsione e resta in dieci
            in_campo = [p for p in pres.intervalli
                        if p != pid and p != p1
                        and in_campo_al(pres.intervalli[p], minuto)]
            # esce di preferenza chi non aveva gia' un cambio programmato dopo
            # questo minuto: altrimenti il suo sostituto entrerebbe comunque e
            # la squadra tornerebbe in undici pur avendo un espulso
            gia_previsti = {u for m2, u, _ in pres.sostituzioni if m2 > minuto}
            in_campo.sort(key=lambda p: (p in gia_previsti,
                                         mod.prop_titolare.get(p, 0.0), str(p)))
            if in_campo:
                sacrificato = in_campo[0]
                pres.intervalli[sacrificato] = [pres.intervalli[sacrificato][0],
                                                int(minuto)]
                for m2, u2, e2 in list(pres.sostituzioni):
                    if u2 == sacrificato and m2 > minuto:
                        pres.intervalli[e2] = [0, 0]
                        pres.sostituzioni.remove((m2, u2, e2))
                pres.sostituzioni.append((int(minuto), sacrificato, p1))
            nuovi.append((int(minuto), fine_segmento, p1, False))
            esito["portiere_di_riserva"] = p1
        else:
            # nessun portiere disponibile: uno di movimento prende i guantoni.
            # Va rappresentato, non nascosto: il fantavoto di un giocatore di
            # movimento non prende i gol subiti, ed e' giusto cosi' secondo le
            # regole della fonte, ma l'invariante "un portiere in campo" deve
            # restare verificabile.
            in_campo = [p for p in pres.intervalli
                        if p != pid and in_campo_al(pres.intervalli[p], minuto)]
            gia_previsti = {u for m2, u, _ in pres.sostituzioni if m2 > minuto}
            in_campo.sort(key=lambda p: (p in gia_previsti,
                                         mod.prop_titolare.get(p, 0.0), str(p)))
            if in_campo:
                scelto = in_campo[0]
                # chi prende i guantoni non puo' uscire: la porta resterebbe
                # scoperta. Se aveva un cambio programmato, il cambio salta.
                for m2, u2, e2 in list(pres.sostituzioni):
                    if u2 == scelto and m2 > minuto:
                        pres.intervalli[e2] = [0, 0]
                        pres.intervalli[scelto] = [pres.intervalli[scelto][0],
                                                   FINE_PARTITA]
                        pres.sostituzioni.remove((m2, u2, e2))
                nuovi.append((int(minuto), fine_segmento, scelto, True))
                esito["portiere_di_movimento"] = scelto
        pres.portiere = sorted(nuovi, key=lambda x: x[0])
    return esito
