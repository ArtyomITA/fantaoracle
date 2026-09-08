"""Chi segna, chi serve l'assist, chi prende il cartellino.

Il modello di partita dice quanti gol fa una squadra; questo modulo li assegna
ai giocatori che erano in campo in quel momento, insieme agli altri eventi del
tabellino. Il vincolo che tiene tutto insieme e' la riconciliazione col
risultato: i gol dei giocatori piu' gli autogol degli avversari devono fare
esattamente i gol della squadra.

## Come si assegna un gol

Per ciascun gol della squadra, nell'ordine:

  1. si estrae il minuto dalla distribuzione osservata dei minuti dei gol;
  2. si decide se e' un autogol di un avversario (quota storica);
  3. altrimenti si decide se e' su rigore (quota storica);
  4. il marcatore si estrae fra chi era **in campo a quel minuto**, con peso
     proporzionale al suo tasso individuale contratto verso la media del ruolo;
     per i rigori il peso e' quello del rigorista designato, se in campo;
  5. con probabilita' storica il gol ha un assist, assegnato a un compagno in
     campo diverso dal marcatore, con peso proporzionale al suo tasso di
     assist.

Ogni evento porta con se' il suo minuto, e il minuto sta dentro l'intervallo di
presenza di chi lo compie: e' l'invariante 7.4.4 del contratto. Prima della
correzione il 2,10 % dei gol finiva a un giocatore gia' uscito, perche' la
fonte registra al minuto 90 tutto quello che accade dal 90' in poi e nessun
intervallo comprendeva quel minuto.

## Rigori: un evento solo, visto dai due lati

Un rigore sbagliato di una squadra e' un rigore parato del portiere avversario
oppure un tiro fuori. I due lati si generano insieme, in
`genera_rigori_sbagliati`, che vuole gli intervalli di **entrambe** le squadre:
il tiratore e il portiere devono essere in campo a quel minuto.

I denominatori, misurati sul panel delle stagioni 2021-22, 2023-24, 2024-25 e
2025-26 (3 038 squadra-partita, 78 267 righe eleggibili,
`data/l3/fix/generatore/m0_dati.py`):

    rigori tirati            479      0,15767 per squadra-partita
    rigori segnati           370      0,12179 per squadra-partita
    rigori sbagliati         109      0,03588 per squadra-partita  (22,76 % dei tirati)
    rigori parati             80      73,39 % degli sbagliati

I rigori **segnati** restano legati ai gol, perche' entrano nel risultato:
`quota_rigori` = 370 / 3 800 = 0,0974 dei gol. I rigori **sbagliati** non
entrano nel risultato e vanno quindi estratti per conto loro, con la loro
frequenza per squadra-partita: e' la ragione per cui il modello porta
`rigori_sbagliati_per_partita`. La somma dei due, 0,12179 + 0,03588 = 0,15767,
torna esattamente ai rigori tirati osservati.

## Espulsioni

L'espulsione ha un minuto, estratto dentro l'intervallo di presenza del
giocatore, e chiude quell'intervallo. La distribuzione dei minuti viene dai
minuti giocati dai titolari espulsi (252 osservazioni, media 64,7, mediana 68):
per un titolare espulso i minuti registrati **sono** il minuto del cartellino
rosso. Le espulsioni si estraggono prima dei gol, perche' cambiano chi e' in
campo nel resto della partita.

## Sui tassi individuali

Il tasso di ogni giocatore e' contratto verso la media del suo ruolo in
proporzione ai minuti che ha alle spalle. Chi non ha storia in Serie A prende
il tasso del ruolo. Quando esiste, l'xG per 90 minuti della stagione
precedente entra come informazione aggiuntiva del prior, mai come evidenza
indipendente: sarebbe lo stesso dato contato due volte.

## Verifica onesta della ripartizione

L'indagine precedente giudicava questo pezzo con la correlazione di rango fra
marcatori dentro la partita: una misura poco informativa quando quasi tutti i
valori sono zero. `scripts/l2_banco_eventi.py` lo giudica con il punteggio
logaritmico e il Brier sull'evento "questo giocatore ha segnato in questa
partita", che e' la quantita' che il cubo deve davvero prevedere.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from .partecipazione import FINE_PARTITA, Presenze, in_campo_al

RUOLI = ("P", "D", "C", "A")
# stati in cui il giocatore non e' sceso in campo: valgono zero minuti. Sono
# elencati sia nella forma vecchia sia in quella del contratto 7.1.
FUORI_CAMPO = ("non_in_rosa", "panchina_non_entrato", "escluso", "fuori_lista")
CAMPI_EVENTO = ("gol", "rigore_segnato", "assist", "autogol", "ammonizione",
                "espulsione", "rigori_sbagliati", "rigori_parati")


@dataclass
class ModelloEventi:
    tasso_gol: dict            # master_id -> gol per 90 minuti (contratto)
    tasso_assist: dict
    tasso_ammonizione: dict
    tasso_espulsione: dict
    tasso_ruolo: dict          # ruolo -> (gol, assist, ammonizioni, espulsioni)
    ruolo: dict
    rigorista: dict            # squadra -> [master_id ordinati per rigori tirati]
    quota_rigori: float        # quota dei gol segnati su rigore
    quota_autogol: float       # quota dei gol di una squadra da autogol avversari
    quota_assist: float        # quota dei gol con assist
    p_rigore_sbagliato: float  # rigori sbagliati su rigori tirati
    p_rigore_parato: float     # dei rigori sbagliati, quanti li para il portiere
    minuti_gol: np.ndarray     # campione dei minuti in cui cadono i gol
    # --- invarianti fisiche (correzione del 7 settembre 2026) --------------
    rigori_sbagliati_per_partita: float = 0.0
    minuti_espulsione: np.ndarray = field(
        default_factory=lambda: np.array([65.0]))
    diagnostica: dict = field(default_factory=dict)


@dataclass
class EventiSquadra:
    """Conteggi per giocatore e cronologia degli eventi con il loro minuto.

    Si comporta come il dizionario che questo modulo restituiva prima
    (`e[pid]` da' i conteggi di quel giocatore), cosi' il codice che leggeva
    solo i conteggi continua a funzionare; la cronologia e' l'aggiunta che
    permette di verificare che ogni evento cada dentro l'intervallo di presenza
    di chi lo compie.
    """
    per_giocatore: dict
    cronologia: list = field(default_factory=list)
    note: dict = field(default_factory=dict)

    def __getitem__(self, pid):
        return self.per_giocatore[pid]

    def __contains__(self, pid):
        return pid in self.per_giocatore

    def __iter__(self):
        return iter(self.per_giocatore)

    def items(self):
        return self.per_giocatore.items()

    def get(self, pid, alt=None):
        return self.per_giocatore.get(pid, alt)


def _vuoto(giocatori) -> dict:
    return {pid: {c: 0 for c in CAMPI_EVENTO} for pid in giocatori}


def _presenze(intervalli) -> Presenze:
    """Accetta sia un oggetto `Presenze` sia il vecchio dizionario piatto."""
    if isinstance(intervalli, Presenze):
        return intervalli
    return Presenze(intervalli=dict(intervalli))


def _contrai(somma, minuti, media_ruolo, k_minuti=900.0):
    """Tasso per 90 minuti contratto verso la media del ruolo."""
    n90 = np.asarray(minuti, dtype=float) / 90.0
    k = k_minuti / 90.0
    return (np.asarray(somma, dtype=float) + media_ruolo * k) / (n90 + k)


def stima(panel: pd.DataFrame, as_of: str | None = None,
          xg_per90: dict | None = None, peso_xg: float = 0.0) -> ModelloEventi:
    """Stima i tassi individuali sulle partite anteriori ad `as_of`."""
    d = panel[panel.stato_voto.isin(["con_voto", "senza_voto"])].copy()
    d["data"] = pd.to_datetime(d["data"])
    if as_of is not None:
        d = d[d["data"] < pd.Timestamp(as_of)]
    if d.empty:
        raise ValueError("nessuna riga utilizzabile prima di as_of")
    for c in ["gol_fatti", "rigore_segnato", "assist", "ammonizione",
              "espulsione", "rigori_sbagliati", "rigori_parati", "autogol"]:
        d[c] = pd.to_numeric(d[c], errors="coerce").fillna(0.0)
    d["minuti_stimati"] = pd.to_numeric(d["minuti"], errors="coerce")
    # per le righe senza minuti, il titolare vale 90 e il subentrato la media
    d["minuti_stimati"] = d["minuti_stimati"].fillna(
        pd.Series(np.where(d.stato_convocazione == "titolare", 90.0, 25.0),
                  index=d.index))
    d.loc[d.stato_convocazione.isin(FUORI_CAMPO), "minuti_stimati"] = 0.0

    ruolo = d.groupby("master_id")["ruolo"].agg(
        lambda s: s.value_counts().index[0]).to_dict()
    tassi_ruolo = {}
    for r in RUOLI:
        s = d[d.ruolo == r]
        m90 = max(s.minuti_stimati.sum() / 90.0, 1.0)
        tassi_ruolo[r] = {
            "gol": float((s.gol_fatti.sum() + s.rigore_segnato.sum()) / m90),
            "assist": float(s.assist.sum() / m90),
            "ammonizione": float(s.ammonizione.sum() / m90),
            "espulsione": float(s.espulsione.sum() / m90),
        }
    agg = d.groupby("master_id").agg(
        min_tot=("minuti_stimati", "sum"),
        gol=("gol_fatti", "sum"), rig=("rigore_segnato", "sum"),
        ass=("assist", "sum"), amm=("ammonizione", "sum"),
        esp=("espulsione", "sum")).reset_index()
    agg["ruolo"] = agg.master_id.map(ruolo)
    t_gol, t_ass, t_amm, t_esp = {}, {}, {}, {}
    for r in agg.itertuples(index=False):
        tr = tassi_ruolo.get(r.ruolo, tassi_ruolo["C"])
        prior_gol = tr["gol"]
        if xg_per90 and peso_xg > 0 and r.master_id in xg_per90:
            # l'xG entra nel PRIOR, non come nuova evidenza: la stessa storia
            # non puo' valere due volte
            prior_gol = (1 - peso_xg) * prior_gol + peso_xg * float(xg_per90[r.master_id])
        t_gol[r.master_id] = float(_contrai(r.gol + r.rig, r.min_tot, prior_gol))
        t_ass[r.master_id] = float(_contrai(r.ass, r.min_tot, tr["assist"]))
        t_amm[r.master_id] = float(_contrai(r.amm, r.min_tot, tr["ammonizione"]))
        t_esp[r.master_id] = float(_contrai(r.esp, r.min_tot, tr["espulsione"]))

    rigorista = {}
    for sq, s in d.groupby("squadra_alla_data"):
        v = (s.groupby("master_id")[["rigore_segnato", "rigori_sbagliati"]]
              .sum().sum(axis=1).sort_values(ascending=False))
        rigorista[sq] = [m for m, n in v.items() if n > 0][:3]

    gol_tot = float(d.gol_fatti.sum() + d.rigore_segnato.sum())
    rig_segnati = float(d.rigore_segnato.sum())
    rig_sbagliati = float(d.rigori_sbagliati.sum())
    rig_parati = float(d.rigori_parati.sum())
    # gol di squadra dai risultati: la differenza rispetto ai gol dei giocatori
    # sono gli autogol degli avversari
    per_partita = d.groupby(["stagione", "giornata", "squadra_alla_data"]).agg(
        gol_squadra=("gol_squadra", "first"),
        segnati=("gol_fatti", "sum"), rigori=("rigore_segnato", "sum"))
    n_squadra_partita = int(len(per_partita))
    gol_risultato = float(per_partita.gol_squadra.fillna(0).sum())
    quota_ag = max(0.0, (gol_risultato - gol_tot) / max(gol_risultato, 1))

    # minuto dell'espulsione: per un titolare espulso i minuti registrati sono
    # il minuto del cartellino rosso. I subentrati non servono, perche' di loro
    # non si conosce il minuto d'ingresso in modo affidabile.
    esp_tit = d[(d.espulsione == 1) & (d.stato_convocazione == "titolare")]
    mm = pd.to_numeric(esp_tit["minuti"], errors="coerce").dropna().to_numpy(float)
    mm = np.clip(mm[(mm > 0) & (mm <= 95)], 1, FINE_PARTITA)
    if not len(mm):
        mm = np.array([65.0])

    return ModelloEventi(
        tasso_gol=t_gol, tasso_assist=t_ass, tasso_ammonizione=t_amm,
        tasso_espulsione=t_esp, tasso_ruolo=tassi_ruolo, ruolo=ruolo,
        rigorista=rigorista,
        quota_rigori=float(rig_segnati / max(gol_tot, 1)),
        quota_autogol=float(quota_ag),
        # gli assist si contano sui gol su azione: sui rigori non ce ne sono
        quota_assist=float(d.assist.sum()
                           / max(gol_tot - rig_segnati, 1)),
        p_rigore_sbagliato=float(rig_sbagliati
                                 / max(rig_segnati + rig_sbagliati, 1)),
        p_rigore_parato=float(rig_parati / max(rig_sbagliati, 1)),
        minuti_gol=np.arange(1, 91, dtype=float),   # sostituito se disponibile
        rigori_sbagliati_per_partita=float(rig_sbagliati
                                           / max(n_squadra_partita, 1)),
        minuti_espulsione=mm,
        diagnostica={
            "righe": int(len(d)),
            "giocatori": int(len(t_gol)),
            "gol_totali": gol_tot,
            "squadra_partita": n_squadra_partita,
            "quota_rigori": round(float(rig_segnati / max(gol_tot, 1)), 4),
            "quota_autogol": round(quota_ag, 4),
            "quota_assist_su_gol_azione": round(
                float(d.assist.sum() / max(gol_tot - rig_segnati, 1)), 4),
            "rigori": {
                "segnati": rig_segnati, "sbagliati": rig_sbagliati,
                "parati": rig_parati,
                "tirati_per_squadra_partita": round(
                    (rig_segnati + rig_sbagliati) / max(n_squadra_partita, 1), 5),
                "sbagliati_per_squadra_partita": round(
                    rig_sbagliati / max(n_squadra_partita, 1), 5),
                "quota_sbagliati_su_tirati": round(
                    rig_sbagliati / max(rig_segnati + rig_sbagliati, 1), 4),
                "quota_parati_su_sbagliati": round(
                    rig_parati / max(rig_sbagliati, 1), 4),
            },
            "espulsioni": {
                "osservate": int((d.espulsione == 1).sum()),
                "titolari_con_minuto": int(len(mm)),
                "minuto_medio": round(float(np.mean(mm)), 2),
                "minuto_mediano": round(float(np.median(mm)), 2),
            },
            "tassi_ruolo": {k: {kk: round(vv, 4) for kk, vv in v.items()}
                            for k, v in tassi_ruolo.items()},
        })


def minuti_gol_da_eventi(percorso, id_partite: set) -> np.ndarray:
    """Distribuzione osservata dei minuti dei gol, da `game_events`."""
    d = pd.read_csv(percorso, compression="gzip", low_memory=False,
                    usecols=["game_id", "minute", "type"])
    d = d[(d.type == "Goals") & d.game_id.isin(id_partite)]
    m = pd.to_numeric(d["minute"], errors="coerce").dropna()
    return np.clip(m.to_numpy(float), 1, 95)


def p_segna(mod: ModelloEventi, giocatori: list, minuti: dict,
            gol_squadra: float) -> np.ndarray:
    """P(questo giocatore segna almeno un gol) date le sue presenze in campo.

    Serve alla valutazione probabilistica: e' la quantita' che il cubo prevede,
    e si confronta con l'evento osservato "ha segnato".
    """
    peso = np.array([mod.tasso_gol.get(pid, 0.05) * (minuti.get(pid, [0, 0])[1]
                                                     - minuti.get(pid, [0, 0])[0]) / 90.0
                     for pid in giocatori])
    tot = peso.sum()
    if tot <= 0:
        return np.zeros(len(giocatori))
    quota = peso / tot
    # numero atteso di gol su azione + rigore assegnati ai giocatori
    g = gol_squadra * (1.0 - mod.quota_autogol)
    return 1.0 - np.exp(-quota * g)


def _ripiego(mod, pid, campo):
    """Chi non ha storia in Serie A prende il tasso del suo ruolo, non una
    costante: un portiere senza storia non ammonisce come un difensore."""
    return mod.tasso_ruolo.get(mod.ruolo.get(pid, "C"),
                               mod.tasso_ruolo["C"])[campo]


def _scegli(mod, cands, tassi, campo, rng):
    w = np.array([max(tassi.get(pid, _ripiego(mod, pid, campo)), 1e-9)
                  for pid in cands])
    return cands[int(rng.choice(len(cands), p=w / w.sum()))]


def genera_espulsioni(mod: ModelloEventi, giocatori: list, presenze,
                      rng: np.random.Generator) -> list:
    """Espulsioni con il loro minuto, estratte PRIMA dei gol.

    L'ordine conta: un'espulsione cambia chi e' in campo per il resto della
    partita, quindi va decisa prima di assegnare i gol. Il minuto si estrae
    dentro l'intervallo di presenza del giocatore, dalla distribuzione
    osservata dei minuti delle espulsioni ristretta a quell'intervallo; se in
    quell'intervallo non cade nessuna osservazione, si estrae uniformemente,
    che e' l'unica scelta che non inventa una forma.

    Ritorna [(master_id, minuto)] ordinata per minuto: le espulsioni vanno
    applicate in ordine cronologico, perche' la seconda vede gli effetti della
    prima.
    """
    pres = _presenze(presenze)
    fuori = []
    for pid in giocatori:
        iv = pres.intervalli.get(pid)
        if iv is None or iv[1] <= iv[0]:
            continue
        quota90 = (iv[1] - iv[0]) / 90.0
        t_esp = mod.tasso_espulsione.get(pid, _ripiego(mod, pid, "espulsione"))
        if rng.random() >= 1 - np.exp(-t_esp * quota90):
            continue
        dentro = mod.minuti_espulsione[
            (mod.minuti_espulsione >= max(iv[0], 1))
            & (mod.minuti_espulsione <= iv[1])]
        if len(dentro):
            m = int(rng.choice(dentro))
        else:
            m = int(rng.integers(max(int(iv[0]), 1), max(int(iv[1]), 2)))
        fuori.append((pid, int(np.clip(m, max(int(iv[0]), 1), FINE_PARTITA))))
    fuori.sort(key=lambda x: (x[1], str(x[0])))
    return fuori


def genera(mod: ModelloEventi, squadra: str, giocatori: list, intervalli,
           gol_squadra: int, gol_avversari_da_autogol: int,
           rng: np.random.Generator, espulsioni: list | None = None
           ) -> EventiSquadra:
    """Eventi individuali di una squadra in una partita.

    `gol_squadra` sono i gol nel risultato; `gol_avversari_da_autogol` quanti
    di quelli avversari sono autogol di QUESTA squadra. `intervalli` e' un
    oggetto `Presenze` (o, per compatibilita', il vecchio dizionario piatto)
    **gia' aggiornato con le espulsioni**: chi e' stato espulso non e' piu' in
    campo, quindi non puo' comparire fra i marcatori.

    Ritorna un `EventiSquadra`: i conteggi per giocatore, riconciliati col
    risultato per costruzione, piu' la cronologia con il minuto di ogni evento.
    """
    pres = _presenze(intervalli)
    eventi = _vuoto(giocatori)
    cronologia = []
    note = {"gol_senza_nessuno_in_campo": 0, "autogol_senza_nessuno_in_campo": 0}
    in_campo = [pid for pid in giocatori
                if pres.intervalli.get(pid, [0, 0])[1]
                > pres.intervalli.get(pid, [0, 0])[0]]
    if not in_campo:
        return EventiSquadra(per_giocatore=eventi, cronologia=cronologia,
                             note=note)

    def presenti(minuto):
        return [pid for pid in in_campo
                if in_campo_al(pres.intervalli[pid], minuto)]

    for _ in range(int(gol_squadra)):
        minuto = float(rng.choice(mod.minuti_gol))
        cands = presenti(minuto)
        if not cands:
            # non deve piu' succedere: gli intervalli comprendono il 90' e il
            # recupero. Se succede lo si conta, invece di nasconderlo.
            note["gol_senza_nessuno_in_campo"] += 1
            cands = in_campo
        su_rigore = rng.random() < mod.quota_rigori
        if su_rigore:
            tiratori = [p for p in mod.rigorista.get(squadra, []) if p in cands]
            marcatore = (tiratori[0] if tiratori
                         else _scegli(mod, cands, mod.tasso_gol, "gol", rng))
            eventi[marcatore]["rigore_segnato"] += 1
            cronologia.append({"minuto": minuto, "tipo": "rigore_segnato",
                               "autore": marcatore})
        else:
            marcatore = _scegli(mod, cands, mod.tasso_gol, "gol", rng)
            eventi[marcatore]["gol"] += 1
            cronologia.append({"minuto": minuto, "tipo": "gol",
                               "autore": marcatore})
            if rng.random() < mod.quota_assist:
                altri = [p for p in cands if p != marcatore]
                if altri:
                    a = _scegli(mod, altri, mod.tasso_assist, "assist", rng)
                    eventi[a]["assist"] += 1
                    cronologia.append({"minuto": minuto, "tipo": "assist",
                                       "autore": a})

    for _ in range(int(gol_avversari_da_autogol)):
        minuto = float(rng.choice(mod.minuti_gol))
        cands = [p for p in presenti(minuto) if mod.ruolo.get(p) in ("D", "C")]
        if not cands:
            cands = presenti(minuto)
        if not cands:
            note["autogol_senza_nessuno_in_campo"] += 1
            cands = in_campo
        a = cands[int(rng.integers(len(cands)))]
        eventi[a]["autogol"] += 1
        cronologia.append({"minuto": minuto, "tipo": "autogol", "autore": a})

    espulsi = dict(espulsioni or pres.espulsi or {})
    for pid, minuto in espulsi.items():
        if pid in eventi:
            eventi[pid]["espulsione"] += 1
            cronologia.append({"minuto": float(minuto), "tipo": "espulsione",
                               "autore": pid})

    for pid in in_campo:
        iv = pres.intervalli[pid]
        quota90 = (iv[1] - iv[0]) / 90.0
        t_amm = mod.tasso_ammonizione.get(pid, _ripiego(mod, pid, "ammonizione"))
        if pid in espulsi:
            # il rosso assorbe il giallo: la fonte registra l'espulsione, non
            # entrambe. Era gia' cosi' prima della correzione.
            continue
        if rng.random() < 1 - np.exp(-t_amm * quota90):
            eventi[pid]["ammonizione"] += 1
            # il minuto dell'ammonizione NON e' modellato: il panel non lo
            # porta e non e' stato stimato niente. Quello scritto qui e' un
            # segnaposto dentro l'intervallo, marcato come tale, perche' nulla
            # a valle lo scambi per un dato. Il punteggio non lo usa: il
            # cartellino vale -0,5 comunque, in qualunque minuto sia arrivato.
            dentro = [m for m in (int(iv[0]) + 1, int((iv[0] + iv[1]) / 2))
                      if in_campo_al(iv, m)]
            cronologia.append({"minuto": float(dentro[-1] if dentro else iv[0]),
                               "tipo": "ammonizione", "autore": pid,
                               "minuto_non_modellato": True})
    cronologia.sort(key=lambda e: (e["minuto"], e["tipo"], str(e["autore"])))
    return EventiSquadra(per_giocatore=eventi, cronologia=cronologia, note=note)


def genera_rigori_sbagliati(mod: ModelloEventi, squadra: str,
                            presenze_attacco, presenze_difesa,
                            rng: np.random.Generator) -> list:
    """Rigori sbagliati, con chi li tira, chi li para e quando.

    Un rigore sbagliato non entra nel risultato, quindi non puo' essere
    ricavato dai gol: si estrae con la sua frequenza per squadra-partita
    (`rigori_sbagliati_per_partita`, 0,0362 sui dati). Di quelli, il portiere
    avversario ne para la quota osservata (72,73 %); gli altri finiscono fuori
    o sul palo e non danno bonus a nessuno.

    Il tiratore deve essere in campo a quel minuto e il portiere pure: e' la
    ragione per cui questa funzione vuole gli intervalli di entrambe le
    squadre. Ritorna [{minuto, tiratore, parato_da}], con `parato_da` a None
    quando il rigore non e' stato parato.
    """
    att = _presenze(presenze_attacco)
    dif = _presenze(presenze_difesa)
    lam = float(mod.rigori_sbagliati_per_partita)
    if lam <= 0:
        return []
    n = int(rng.poisson(lam))
    fuori = []
    for _ in range(n):
        minuto = float(rng.choice(mod.minuti_gol))
        cands = [pid for pid, iv in sorted(att.intervalli.items(), key=lambda x: str(x[0]))
                 if in_campo_al(iv, minuto)]
        if not cands:
            continue
        tiratori = [p for p in mod.rigorista.get(squadra, []) if p in cands]
        tiratore = (tiratori[0] if tiratori
                    else _scegli(mod, cands, mod.tasso_gol, "gol", rng))
        parato_da = None
        if rng.random() < mod.p_rigore_parato:
            pt = dif.portiere_al(minuto)
            # il bonus del rigore parato va a chi era in porta in quel momento;
            # se in porta non c'era nessuno il rigore resta semplicemente
            # sbagliato, invece di assegnare il bonus a un giocatore a caso
            if pt is not None and in_campo_al(dif.intervalli.get(pt), minuto):
                parato_da = pt
        fuori.append({"minuto": minuto, "tiratore": tiratore,
                      "parato_da": parato_da})
    return fuori


def rigori_sbagliati(mod: ModelloEventi, tiratori: list, portiere_avversario,
                     rng: np.random.Generator) -> tuple[dict, int]:
    """Versione senza minuti, conservata solo per compatibilita'.

    Non e' usata dal generatore: e' rimasta senza chiamanti dal giorno in cui e'
    stata scritta, e i campi che avrebbe dovuto riempire restavano a zero. La
    funzione buona e' `genera_rigori_sbagliati`, che vuole gli intervalli delle
    due squadre e assegna un minuto a ogni rigore.
    """
    sbagliati, parati = {}, 0
    for pid in tiratori:
        if rng.random() < mod.p_rigore_sbagliato:
            sbagliati[pid] = sbagliati.get(pid, 0) + 1
            if rng.random() < mod.p_rigore_parato:
                parati += 1
    return sbagliati, parati
