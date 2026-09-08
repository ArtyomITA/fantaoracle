"""Il cubo: stagioni di Serie A generate partita per partita.

Mette in fila i pezzi — risultato, partecipazione, eventi, voto, punteggio — e
produce, per ogni scenario, il fantavoto e il voto puro di ogni giocatore in
ogni giornata. Da quel cubo si valuta qualunque rosa: e' la stessa Serie A per
tutte, quindi il confronto fra due rose non porta il rumore comune.

## Che cosa significa "stesso scenario per tutte le rose"

Uno scenario e' una stagione intera del campionato vero: gli stessi risultati,
gli stessi undici, gli stessi marcatori. Se due rose contengono lo stesso
giocatore, in quello scenario quel giocatore ha fatto le stesse cose. Se una
rosa ha un difensore del Napoli e l'altra il portiere del Napoli, e in quello
scenario il Napoli ha vinto 3-0, entrambe ne beneficiano insieme: la
correlazione fra compagni nasce dalla partita, non da uno shock aggiunto.

## Numeri casuali indicizzati, non estratti in sequenza

Ogni estrazione ha una chiave testuale stabile, e il numero casuale dipende
solo da (seme, scenario, chiave):

    partita         "partita:{casa}|{trasferta}|{giornata}"
    squadra         "undici:{squadra}:{chiave partita}"
    giocatore       "conv:{master_id}:{chiave partita}", "voto:{master_id}:..."

Cambiare l'ordine dei giocatori, il numero di rose confrontate o la dimensione
dei blocchi non cambia gli scenari. Il test
`tests/test_l2_generatore.py::test_scenari_invarianti_all_ordine` lo verifica.

## Dipendenza residua strutturata

Il residuo del voto ha tre pezzi: uno di squadra (comune a tutti i compagni),
uno di reparto (comune ai difensori fra loro, ai centrocampisti fra loro) e uno
individuale. Serve perche' i dati dicono che dopo il condizionamento la
correlazione fra difensori e' molto piu' alta di quella fra portiere e
difensori: uno shock unico per squadra, come quello del simulatore attuale, le
imporrebbe uguali. Gli scarti si stimano con `voto.struttura_dipendenza`.

## Che cosa NON fa

Non decide formazioni di fantacalcio e non guarda avanti: il cubo produce gli
esiti, la politica di formazione li vede solo quando li vedrebbe un allenatore
(cioe' dopo). Gli esiti nascosti non sono informazione dell'allenatore.
"""
from __future__ import annotations

import zlib
from dataclasses import dataclass, field

import numpy as np
import pandas as pd
from scipy.special import ndtri

from . import eventi as ev
from . import partecipazione as pa
from . import voto as vt
from .partita import ModelloPartita, matrice_risultato
from .punteggio import Tabellino, fantavoto, verifica_coerenza

_M64 = (1 << 64) - 1


def _mescola(x: np.ndarray) -> np.ndarray:
    """Finalizzatore splitmix64: da interi qualsiasi a interi ben mescolati.

    L'aritmetica e' modulo 2^64: il traboccamento e' voluto, non un errore."""
    x = x.astype(np.uint64, copy=True)
    x ^= x >> np.uint64(30)
    x *= np.uint64(0xBF58476D1CE4E5B9)
    x ^= x >> np.uint64(27)
    x *= np.uint64(0x94D049BB133111EB)
    x ^= x >> np.uint64(31)
    return x


def uniformi(seme: int, scenario: int, chiavi) -> np.ndarray:
    """Numeri in [0,1) indicizzati per chiave testuale.

    Dipendono solo da (seme, scenario, chiave): l'ordine con cui si chiedono e
    quante se ne chiedono insieme non cambia nulla."""
    h = np.array([zlib.crc32(k.encode("utf-8")) for k in chiavi],
                 dtype=np.uint64)
    with np.errstate(over="ignore"):
        base = np.uint64((seme * 0x9E3779B97F4A7C15
                          + scenario * 0xD1B54A32D192ED03) & _M64)
        return (_mescola(h + base) >> np.uint64(11)) / float(1 << 53)


def rng_di(seme: int, scenario: int, chiave: str) -> np.random.Generator:
    """Generatore completo legato a (seme, scenario, chiave)."""
    return np.random.default_rng(
        [seme, scenario, zlib.crc32(chiave.encode("utf-8"))])


@dataclass
class Cubo:
    """Esiti di N stagioni simulate.

    `fantavoto` e `voto` sono array (n_sims, n_giornate, n_giocatori); `gioca`
    dice se il giocatore ha preso voto in quella giornata (non se e' sceso in
    campo: chi entra tardi prende spesso s.v., che nel fantacalcio vale come
    un'assenza)."""
    giocatori: list
    giornate: list
    fantavoto: np.ndarray
    voto: np.ndarray
    gioca: np.ndarray
    in_campo: np.ndarray | None = None
    gol: np.ndarray | None = None
    assist: np.ndarray | None = None
    ammonizione: np.ndarray | None = None
    minuti: np.ndarray | None = None
    # Gol subiti dal portiere mentre era in porta. Serve a chi deve applicare
    # il bonus porta inviolata della lega, che NON e' dentro `fantavoto`: quel
    # campo contiene il punteggio della fonte. Senza questo array il bonus non
    # e' calcolabile a valle e verrebbe semplicemente perso, come succedeva nel
    # banco del Livello 2 (0,297 punti a giornata per rosa).
    gol_subiti: np.ndarray | None = None
    risultati: dict = field(default_factory=dict)
    diagnostica: dict = field(default_factory=dict)

    def per_giornata(self, s: int) -> tuple[list, list]:
        """(fantavoti, voti) come liste di dizionari, uno per giornata: e' il
        formato che il motore delle regole gia' usa."""
        fv, vv = [], []
        for g in range(len(self.giornate)):
            idx = np.nonzero(self.gioca[s, g])[0]
            fv.append({self.giocatori[i]: float(self.fantavoto[s, g, i]) for i in idx})
            vv.append({self.giocatori[i]: float(self.voto[s, g, i]) for i in idx})
        return fv, vv


def _completa_convocati(conv: list, rosa: list, mod_part,
                        note: dict | None = None) -> list:
    """Garantisce un portiere e almeno dieci giocatori di movimento.

    La catena della convocazione lavora giocatore per giocatore e, di tanto in
    tanto, lascia una squadra senza portiere o con nove giocatori di movimento:
    in campo non si va cosi'. I giocatori che mancano si aggiungono in ordine
    deterministico (prima chi ha piu' propensione a essere titolare, poi per
    identita'), perche' l'ordine dell'elenco in ingresso non deve cambiare lo
    scenario.

    ## Incompletezza del nostro universo, non indisponibilita' del giocatore

    Il ripiego «se i convocati sono meno di undici, usa tutta la rosa»
    rimetteva dentro chiunque, compreso chi la catena aveva appena dichiarato
    non convocato. E' una contraddizione, ma non tutta: una rosa del listone
    non e' la rosa vera di una squadra di Serie A, quindi meno di undici
    convocati e' quasi sempre un difetto del **nostro** universo, non del
    giocatore. Le due cose vanno tenute separate:

      * chi la catena non ha convocato puo' rientrare, perche' la catena e' un
        sorteggio, non un referto medico; rientrano prima quelli con la
        propensione piu' alta, e quanti ne rientrano viene contato;
      * chi e' in `mod_part.indisponibile_certo` non rientra **mai**: e'
        l'insieme di chi ha un'indisponibilita' dimostrata. Oggi e' vuoto per
        costruzione, perche' il panel non porta squalifiche e infortuni
        dichiarati; il posto dove metterli pero' c'e', ed e' dichiarato.
    """
    def ordina(cands):
        return sorted(cands, key=lambda p: (-mod_part.prop_titolare.get(p, 0.0),
                                            str(p)))

    indisponibili = set(getattr(mod_part, "indisponibile_certo", None) or ())
    conv = [p for p in conv if p not in indisponibili]
    ammessi = [p for p in rosa if p not in indisponibili]
    presenti = set(conv)
    forzati = 0
    portieri = [p for p in conv if mod_part.ruolo.get(p) == "P"]
    if not portieri:
        fuori = ordina(p for p in ammessi
                       if mod_part.ruolo.get(p) == "P" and p not in presenti)
        if fuori:
            conv.append(fuori[0])
            presenti.add(fuori[0])
            forzati += 1
    movimento = [p for p in conv if mod_part.ruolo.get(p) != "P"]
    if len(movimento) < 10:
        coda = ordina(p for p in ammessi
                      if p not in presenti and mod_part.ruolo.get(p) != "P")
        aggiunti = coda[:10 - len(movimento)]
        conv += aggiunti
        presenti.update(aggiunti)
        forzati += len(aggiunti)
    if len(conv) < 11:
        coda = ordina(p for p in ammessi if p not in presenti)
        aggiunti = coda[:11 - len(conv)]
        conv += aggiunti
        forzati += len(aggiunti)
    if note is not None:
        note["convocati_forzati"] = note.get("convocati_forzati", 0) + forzati
        if len(conv) < 11:
            note["squadre_sotto_undici"] = note.get("squadre_sotto_undici", 0) + 1
    return conv


def gol_subiti_per_portiere(presenze, minuti_subiti) -> dict:
    """Quanti gol ha preso ciascun portiere mentre era lui in porta.

    Prima della correzione i gol subiti venivano dal risultato finale e
    andavano a ogni portiere che prendesse voto: un portiere entrato al 70'
    sullo 0-3 ne prendeva tre, e quando due portieri prendevano voto nella
    stessa partita (33 squadra-partita su 2 100) se li prendevano entrambi
    tutti. L'eccesso misurato era di 0,152 gol subiti per portiere a voto, che
    e' anche 0,152 punti di fantavoto tolti in piu' a ogni portiere.
    """
    fuori = {}
    for a, b, pid, _mov in presenze.portiere:
        fuori[pid] = fuori.get(pid, 0) + sum(
            1 for m in minuti_subiti if pa.in_campo_al([a, b], m))
    return fuori


def correlazioni_simulate(cubo, ruolo: dict, squadra: dict,
                          scenari: int = 2) -> dict:
    """Correlazione fra compagni sul voto puro, negli scenari generati.

    Stessa definizione con cui si misurano quelle osservate: e' la condizione
    per poterle confrontare e per calibrare su di esse."""
    fuori = {}
    for et, ra, rb in [("portiere-difensori", ["P"], ["D"]),
                       ("difensori", ["D"], ["D"]),
                       ("centrocampisti", ["C"], ["C"]),
                       ("attaccanti", ["A"], ["A"])]:
        acc = []
        for s in range(min(scenari, cubo.voto.shape[0])):
            vals = []
            for gi in range(cubo.voto.shape[1]):
                idx = np.nonzero(cubo.gioca[s, gi])[0]
                per_squadra = {}
                for i in idx:
                    pid = cubo.giocatori[i]
                    per_squadra.setdefault(squadra.get(pid, ""), []).append(
                        (ruolo.get(pid, "C"), float(cubo.voto[s, gi, i])))
                for _, righe in per_squadra.items():
                    a = [v for r, v in righe if r in ra]
                    b = [v for r, v in righe if r in rb]
                    if ra == rb:
                        for i2 in range(len(a)):
                            for j2 in range(i2 + 1, len(a)):
                                vals.append((a[i2], a[j2]))
                    else:
                        for x in a:
                            for y in b:
                                vals.append((x, y))
            if len(vals) >= 50:
                v = np.array(vals)
                acc.append(float(np.corrcoef(v[:, 0], v[:, 1])[0, 1]))
        fuori[et] = float(np.nanmean(acc)) if acc else float("nan")
    return fuori


def calibra_dipendenza(struttura: dict, bersagli: dict, calendario, rose,
                       mod_partita, mod_part, mod_eventi, mod_voto, fasce_sv,
                       seme: int, ruolo: dict, squadra: dict,
                       giri: int = 3, sims: int = 2) -> dict:
    """Aggiusta gli scarti finche' le correlazioni simulate colpiscono i bersagli.

    La formula analitica non basta: nel cubo la varianza totale del voto non e'
    quella osservata (la contrazione degli effetti individuali la riduce),
    quindi la stessa varianza di shock produce una correlazione diversa. Si
    misura, si riscala, si ripete. I bersagli vengono dai dati di
    addestramento, mai dalla stagione di prova.
    """
    import copy
    st = copy.deepcopy(struttura)
    sigma2 = mod_voto.sigma ** 2
    storia = []
    for giro in range(giri):
        cubo = genera(calendario, rose, mod_partita, mod_part, mod_eventi,
                      mod_voto, n_sims=sims, seme=seme + 7919 * (giro + 1),
                      dipendenza=st, fasce_sv=fasce_sv, verifica=False)
        med = correlazioni_simulate(cubo, ruolo, squadra, scenari=sims)
        storia.append({k: round(v, 4) for k, v in med.items()})
        a2 = st["sd_squadra"] ** 2
        b2 = {k: v ** 2 for k, v in st["sd_reparto"].items()}
        if med.get("portiere-difensori", 0) > 1e-6:
            a2 *= bersagli["portiere-difensori"] / med["portiere-difensori"]
        for ruolo_k, chiave in (("D", "difensori"), ("C", "centrocampisti"),
                                ("A", "attaccanti")):
            if med.get(chiave, 0) > 1e-6:
                tot = (a2 + b2[ruolo_k]) * bersagli[chiave] / med[chiave]
                b2[ruolo_k] = max(tot - a2, 0.0)
        peggiore = a2 + max(b2.values())
        if peggiore > 0.9 * sigma2:
            scala = 0.9 * sigma2 / peggiore
            a2 *= scala
            b2 = {k: v * scala for k, v in b2.items()}
        st["sd_squadra"] = float(np.sqrt(a2))
        st["sd_reparto"] = {k: float(np.sqrt(v)) for k, v in b2.items()}
        st["sd_individuale"] = float(np.sqrt(max(sigma2 - a2 - max(b2.values()),
                                                 0.05 * sigma2)))
    st["calibrazione"] = {"bersagli": {k: round(v, 4) for k, v in bersagli.items()},
                          "correlazioni_per_giro": storia, "giri": giri,
                          "sims_per_giro": sims}
    return st


def genera(calendario: pd.DataFrame, rose: dict, mod_partita: ModelloPartita,
           mod_part: pa.ModelloPartecipazione, mod_eventi: ev.ModelloEventi,
           mod_voto: vt.ModelloVoto, n_sims: int = 100, seme: int = 0,
           dipendenza: dict | None = None, fasce_sv: dict | None = None,
           verifica: bool = True, incertezza_forze: bool = True) -> Cubo:
    """Genera `n_sims` stagioni.

    `rose` e' squadra -> elenco di master_id convocabili.
    `dipendenza` viene da `voto.struttura_dipendenza`: se assente il residuo e'
    tutto individuale (nessuna correlazione aggiunta oltre a quella spiegata
    dagli eventi).
    `fasce_sv` viene da `voto.stima_senza_voto`: senza, tutti quelli che
    scendono in campo prendono un voto, e la stagione simulata ne ha piu' di
    quella vera.
    """
    cal = calendario.sort_values(["giornata", "data"]).reset_index(drop=True)
    giornate = sorted(cal.giornata.dropna().unique().astype(int))
    ix_g = {g: i for i, g in enumerate(giornate)}
    giocatori = sorted({pid for r in rose.values() for pid in r})
    ix_p = {pid: i for i, pid in enumerate(giocatori)}
    FV = np.zeros((n_sims, len(giornate), len(giocatori)), dtype=np.float32)
    VV = np.zeros_like(FV)
    GI = np.zeros(FV.shape, dtype=bool)
    IC = np.zeros(FV.shape, dtype=bool)
    GO = np.zeros(FV.shape, dtype=np.int8)
    GS = np.zeros(FV.shape, dtype=np.int8)
    AS = np.zeros(FV.shape, dtype=np.int8)
    AM = np.zeros(FV.shape, dtype=np.int8)
    MI = np.zeros(FV.shape, dtype=np.int8)
    risultati = {}
    problemi = []
    # quante volte il ripiego ha dovuto forzare dei convocati per arrivare a
    # undici: e' una misura dell'incompletezza del nostro universo di rose, non
    # un fatto sui giocatori
    note_rosa: dict = {}

    sd_sq = float((dipendenza or {}).get("sd_squadra", 0.0))
    sd_rep = (dipendenza or {}).get("sd_reparto", {})
    sd_ind = float((dipendenza or {}).get("sd_individuale", mod_voto.sigma))
    coef = mod_voto.coef
    alfa = mod_voto.alfa
    media_ruolo = mod_voto.media_ruolo

    for s in range(n_sims):
        mp = (mod_partita.campiona_parametri(rng_di(seme, s, "forze"), n=1)[0]
              if incertezza_forze else mod_partita)
        stato = {}
        for sq, rosa in rose.items():
            u = uniformi(seme, s, [f"init:{pid}" for pid in rosa])
            stato[sq] = {pid: (bool(u[i] < mod_part.prop_convocato.get(pid, 0.6)), 1)
                         for i, pid in enumerate(rosa)}
        lam, mu = mp.intensita(cal.casa.values, cal.trasferta.values)

        for k, riga in enumerate(cal.itertuples(index=False)):
            gi = ix_g[int(riga.giornata)]
            chiave = f"{riga.casa}|{riga.trasferta}|{int(riga.giornata)}"
            r = rng_di(seme, s, f"partita:{chiave}")
            P = matrice_risultato(float(lam[k]), float(mu[k]), mp.rho)
            larghezza = P.shape[1]
            piatta = np.maximum(P.ravel(), 0.0)
            j = int(np.searchsorted(np.cumsum(piatta / piatta.sum()),
                                    r.random(), side="right"))
            gc, gt = divmod(min(j, piatta.size - 1), larghezza)
            risultati[(s, int(riga.giornata), riga.casa)] = (gc, gt)

            # autogol: quanti dei gol di una squadra sono segnati da un
            # avversario. ag_casa entra nel punteggio della squadra di casa ed
            # e' un autogol di un giocatore ospite, e viceversa.
            ag_casa = int(r.binomial(gc, mod_eventi.quota_autogol))
            ag_tras = int(r.binomial(gt, mod_eventi.quota_autogol))
            tab = {}
            for lato, sq, gol_propri, gol_subiti, autogol_propri in (
                    ("casa", riga.casa, gc - ag_casa, gt, ag_tras),
                    ("trasferta", riga.trasferta, gt - ag_tras, gc, ag_casa)):
                rosa = rose.get(sq)
                if not rosa:
                    continue
                rr = rng_di(seme, s, f"squadra:{sq}:{chiave}")
                # convocati: catena con memoria sul logit individuale
                u_conv = uniformi(seme, s, [f"conv:{pid}:{chiave}" for pid in rosa])
                conv = []
                for i, pid in enumerate(rosa):
                    era, run = stato[sq][pid]
                    # base calibrata: aggiungere lo scostamento al logit non
                    # conserva il tasso medio della catena, quindi la base non
                    # e' logit(p) ma quella che rende stazionario proprio p
                    base = mod_part.base_convocazione(pid)
                    p = 1.0 / (1.0 + np.exp(-(base + pa.offset(mod_part, era, run))))
                    ok = bool(u_conv[i] < p)
                    stato[sq][pid] = (ok, run + 1 if ok == era else 1)
                    if ok:
                        conv.append(pid)
                conv = _completa_convocati(conv, rosa, mod_part, note_rosa)
                conteggi = {}
                for pid in conv:
                    ru = mod_part.ruolo.get(pid, "C")
                    ru = ru if ru in ("P", "D", "C", "A") else "C"
                    conteggi[ru] = conteggi.get(ru, 0) + 1
                modulo = pa.estrai_modulo(mod_part, sq, rr,
                                          disponibili=conteggi)
                u_sel = uniformi(seme, s, [f"undici:{pid}:{chiave}" for pid in conv])
                titolari, panchina = pa.scegli_undici(conv, mod_part, modulo,
                                                      rr, u=u_sel)
                presenze = pa.genera_minuti(titolari, panchina, mod_part, rr)
                tab[lato] = {"squadra": sq, "titolari": titolari,
                             "panchina": panchina, "presenze": presenze,
                             "rr": rr, "gol_propri": max(gol_propri, 0),
                             "autogol_propri": autogol_propri,
                             "gol_subiti_squadra": gol_subiti}

            # --- espulsioni: PRIMA dei gol -------------------------------
            # un'espulsione cambia chi e' in campo per il resto della partita,
            # quindi va decisa prima di assegnare i gol; chiude l'intervallo
            # dell'espulso e annulla la sua eventuale sostituzione
            for lato, d in tab.items():
                for pid, minuto in ev.genera_espulsioni(
                        mod_eventi, d["titolari"] + d["panchina"],
                        d["presenze"], d["rr"]):
                    pa.applica_espulsione(d["presenze"], pid, minuto, mod_part)

            for lato, d in tab.items():
                d["eventi"] = ev.genera(
                    mod_eventi, d["squadra"], d["titolari"] + d["panchina"],
                    d["presenze"], d["gol_propri"], d["autogol_propri"],
                    d["rr"])

            # --- rigori sbagliati e parati: un evento solo, due lati -------
            for lato, altro in (("casa", "trasferta"), ("trasferta", "casa")):
                if lato not in tab:
                    continue
                d = tab[lato]
                a = tab.get(altro)
                if a is None:
                    continue
                rr_rig = rng_di(seme, s, f"rigori:{d['squadra']}:{chiave}")
                for rig in ev.genera_rigori_sbagliati(
                        mod_eventi, d["squadra"], d["presenze"],
                        a["presenze"], rr_rig):
                    d["eventi"].per_giocatore[rig["tiratore"]]["rigori_sbagliati"] += 1
                    d["eventi"].cronologia.append(
                        {"minuto": rig["minuto"], "tipo": "rigore_sbagliato",
                         "autore": rig["tiratore"]})
                    if rig["parato_da"] is not None:
                        a["eventi"].per_giocatore[rig["parato_da"]]["rigori_parati"] += 1
                        a["eventi"].cronologia.append(
                            {"minuto": rig["minuto"], "tipo": "rigore_parato",
                             "autore": rig["parato_da"]})

            # --- gol subiti: quelli presi mentre quel portiere era in porta -
            for lato, altro in (("casa", "trasferta"), ("trasferta", "casa")):
                if lato not in tab:
                    continue
                d = tab[lato]
                a = tab.get(altro)
                if a is not None:
                    minuti_subiti = [e2["minuto"] for e2 in a["eventi"].cronologia
                                     if e2["tipo"] in ("gol", "rigore_segnato")]
                    minuti_subiti += [e2["minuto"] for e2 in d["eventi"].cronologia
                                      if e2["tipo"] == "autogol"]
                else:
                    # l'avversario non ha una rosa nel nostro universo: dei suoi
                    # gol si conosce il numero, non il minuto, e i minuti si
                    # estraggono dalla stessa distribuzione dei gol
                    minuti_subiti = [float(x) for x in
                                     d["rr"].choice(mod_eventi.minuti_gol,
                                                    size=int(d["gol_subiti_squadra"]))]
                d["gol_subiti_portiere"] = gol_subiti_per_portiere(
                    d["presenze"], minuti_subiti)
                d["minuti_subiti"] = minuti_subiti

            for lato, d in tab.items():
                sq = d["squadra"]
                titolari, panchina = d["titolari"], d["panchina"]
                presenze = d["presenze"]
                intervalli = presenze.intervalli
                e = d["eventi"]
                gs_portiere = d.get("gol_subiti_portiere", {})
                in_campo = [pid for pid in titolari + panchina
                            if intervalli[pid][1] > intervalli[pid][0]]
                if not in_campo:
                    continue
                n = len(in_campo)
                ruoli = [mod_part.ruolo.get(pid, "C") for pid in in_campo]
                minuti = np.array([intervalli[pid][1] - intervalli[pid][0]
                                   for pid in in_campo], dtype=float)
                base = np.array([alfa.get(pid, media_ruolo.get(ru, 6.0))
                                 for pid, ru in zip(in_campo, ruoli)])
                for i, pid in enumerate(in_campo):
                    dd = e[pid]
                    base[i] += (coef["gol_1"] * (dd["gol"] == 1)
                                + coef["gol_2piu"] * (dd["gol"] >= 2)
                                + coef["assist"] * dd["assist"]
                                + coef["rigore_segnato"] * dd["rigore_segnato"]
                                + coef["autogol"] * dd["autogol"]
                                + coef["ammonizione"] * dd["ammonizione"]
                                + coef["espulsione"] * dd["espulsione"])
                    if ruoli[i] == "P":
                        # i gol sono quelli presi da LUI, non quelli della
                        # squadra: un portiere entrato al 70' sullo 0-3 non ha
                        # subito tre gol
                        gsi = gs_portiere.get(pid, 0)
                        base[i] += (coef["gk_porta_inviolata"] * (gsi == 0)
                                    + coef["gk_1_subito"] * (gsi == 1)
                                    + coef["gk_2_subiti"] * (gsi == 2)
                                    + coef["gk_3piu_subiti"] * (gsi >= 3))
                # residuo: squadra + reparto + individuale
                z_sq = ndtri(np.clip(uniformi(seme, s, [f"sq:{sq}:{chiave}"])[0],
                                     1e-9, 1 - 1e-9))
                z_rep = {ru: ndtri(np.clip(
                    uniformi(seme, s, [f"rep:{sq}:{ru}:{chiave}"])[0], 1e-9, 1 - 1e-9))
                    for ru in set(ruoli)}
                u_ind = uniformi(seme, s, [f"voto:{pid}:{chiave}" for pid in in_campo])
                eps = ndtri(np.clip(u_ind, 1e-9, 1 - 1e-9))
                voti = base + sd_sq * z_sq + sd_ind * eps
                for i, ru in enumerate(ruoli):
                    voti[i] += sd_rep.get(ru, 0.0) * z_rep[ru]
                voti = np.clip(np.round(voti * 2) / 2, 3.0, 10.0)

                # chi prende s.v.: la fonte non da' un voto a tutti
                if fasce_sv:
                    p_sv = vt.p_senza_voto(fasce_sv, minuti)
                    u_sv = uniformi(seme, s, [f"sv:{pid}:{chiave}" for pid in in_campo])
                    con_voto = u_sv >= p_sv
                else:
                    con_voto = np.ones(n, dtype=bool)
                # chi ha segnato, servito un assist o fatto autogol prende
                # sempre un voto. Non e' un'assunzione: sul panel delle quattro
                # stagioni con formazioni note, su 4 287 righe con s.v. quelle
                # con gol sono ZERO, quelle con assist ZERO, quelle con autogol
                # ZERO; fra chi ha giocato dieci minuti o meno e ha preso voto,
                # 66 su 367 avevano segnato. Se l's.v. fosse indipendente dal
                # gol, sui 3 602 s.v. con dieci minuti o meno ci si
                # aspetterebbero circa 650 marcatori senza voto: non ce n'e'
                # nessuno. (L'ammonizione invece convive con l's.v.: 142
                # righe, e l'espulsione una.)
                for i, pid in enumerate(in_campo):
                    dd = e[pid]
                    if (dd["gol"] or dd["rigore_segnato"] or dd["assist"]
                            or dd["autogol"]):
                        con_voto[i] = True

                for i, pid in enumerate(in_campo):
                    j = ix_p.get(pid)
                    if j is None:
                        continue
                    dd = e[pid]
                    # dati calcistici: si conservano SEMPRE, anche per chi
                    # prende s.v. Il voto della fonte e il punteggio della lega
                    # sono un'altra cosa, e restano condizionati al voto.
                    IC[s, gi, j] = True
                    GO[s, gi, j] = dd["gol"] + dd["rigore_segnato"]
                    AS[s, gi, j] = dd["assist"]
                    AM[s, gi, j] = dd["ammonizione"]
                    MI[s, gi, j] = min(int(minuti[i]), 127)
                    if ruoli[i] == "P":
                        GS[s, gi, j] = min(int(gs_portiere.get(pid, 0)), 127)
                    if not con_voto[i]:
                        continue
                    t = Tabellino(
                        ruolo=ruoli[i], voto=float(voti[i]), minuti=int(minuti[i]),
                        entrata=int(intervalli[pid][0]),
                        uscita=int(intervalli[pid][1]),
                        gol=dd["gol"], rigore_segnato=dd["rigore_segnato"],
                        assist=dd["assist"], ammonizione=dd["ammonizione"],
                        espulsione=dd["espulsione"], autogol=dd["autogol"],
                        rigori_parati=dd["rigori_parati"],
                        rigori_sbagliati=dd["rigori_sbagliati"],
                        gol_subiti=(gs_portiere.get(pid, 0)
                                    if ruoli[i] == "P" else 0),
                        titolare=pid in titolari)
                    FV[s, gi, j] = fantavoto(t)
                    VV[s, gi, j] = t.voto
                    GI[s, gi, j] = True

            if verifica and s == 0 and k < 30 and len(tab) == 2:
                problemi += _verifica_partita(tab, mod_part, gc, gt)

    return Cubo(giocatori=giocatori, giornate=giornate, fantavoto=FV, voto=VV,
                gioca=GI, in_campo=IC, gol=GO, assist=AS,
                ammonizione=AM, minuti=MI, gol_subiti=GS, risultati=risultati,
                diagnostica={"n_sims": n_sims, "seme": seme,
                             "dipendenza": dipendenza,
                             "incertezza_forze": incertezza_forze,
                             "problemi_coerenza": problemi[:20],
                             "n_problemi_coerenza": len(problemi),
                             "ripiego_convocati": dict(note_rosa)})


def _verifica_partita(tab, mod_part, gc, gt) -> list:
    """Costruisce i tabellini della partita e li passa al controllo completo.

    Al controllo servono anche gli intervalli e la cronologia: senza, il
    controllo puo' solo dire «questo giocatore ha almeno un minuto», che e' la
    verifica debole che lasciava passare i gol assegnati a chi era gia' uscito.
    """
    fuori, presenze, cronologia, gs_att = {}, {}, {}, {}
    for lato in ("casa", "trasferta"):
        d = tab[lato]
        intervalli = d["presenze"].intervalli
        gs_portiere = d.get("gol_subiti_portiere", {})
        fuori[lato] = {
            p: Tabellino(
                ruolo=mod_part.ruolo.get(p, "C"), voto=6.0,
                minuti=int(intervalli[p][1] - intervalli[p][0]),
                entrata=int(intervalli[p][0]), uscita=int(intervalli[p][1]),
                titolare=p in d["titolari"],
                gol_subiti=(gs_portiere.get(p, 0)
                            if mod_part.ruolo.get(p) == "P" else 0),
                **{k: v for k, v in d["eventi"][p].items()
                   if k in ("gol", "rigore_segnato", "assist", "autogol",
                            "ammonizione", "espulsione", "rigori_parati",
                            "rigori_sbagliati")})
            for p in d["titolari"] + d["panchina"]}
        presenze[lato] = d["presenze"]
        cronologia[lato] = d["eventi"].cronologia
        gs_att[lato] = {p: n for p, n in gs_portiere.items()
                        if mod_part.ruolo.get(p) == "P"}
    return verifica_coerenza(fuori["casa"], fuori["trasferta"], gc, gt,
                             presenze=presenze, cronologia=cronologia,
                             gol_subiti_portiere=gs_att)
