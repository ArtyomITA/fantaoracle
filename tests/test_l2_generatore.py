"""Proprieta' strutturali del cubo, non numeri che tornano.

Il cubo serve a confrontare rose diverse sulla STESSA stagione simulata. Se gli
scenari cambiano quando cambia l'ordine dei giocatori o il numero di rose, quel
confronto non vale piu' niente. Questi test fissano le proprieta' che lo
rendono utilizzabile.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from fantabot.tabellino import eventi as ev            # noqa: E402
from fantabot.tabellino import generatore as gen       # noqa: E402
from fantabot.tabellino import partecipazione as pa    # noqa: E402
from fantabot.tabellino import voto as vt              # noqa: E402
from fantabot.tabellino.partita import stima           # noqa: E402
from fantabot.tabellino.punteggio import Tabellino, fantavoto  # noqa: E402


def _finto():
    """Un mondo minimo: 4 squadre, rose di 16, modelli con parametri fissati."""
    squadre = ["A", "B", "C", "D"]
    rose, ruoli = {}, {}
    n = 0
    for sq in squadre:
        r = []
        for ruolo, quanti in (("P", 2), ("D", 6), ("C", 5), ("A", 3)):
            for _ in range(quanti):
                n += 1
                r.append(n)
                ruoli[n] = ruolo
        rose[sq] = r
    righe = []
    for g, (a, b) in enumerate([("A", "B"), ("C", "D"), ("A", "C"), ("B", "D"),
                                ("A", "D"), ("B", "C")], start=1):
        righe.append({"giornata": g,
                      "data": pd.Timestamp("2025-08-01") + pd.Timedelta(days=7 * g),
                      "casa": a, "trasferta": b})
    cal = pd.DataFrame(righe)
    rng = np.random.default_rng(0)
    ch, ct, gc, gt = [], [], [], []
    for _ in range(30):
        for a in squadre:
            for b in squadre:
                if a != b:
                    ch.append(a)
                    ct.append(b)
                    gc.append(rng.poisson(1.5))
                    gt.append(rng.poisson(1.2))
    mp = stima(ch, ct, gc, gt, squadre=squadre, usa_dc=True, lam_pen=2.0)
    m_part = pa.ModelloPartecipazione(
        prop_titolare={p: 0.0 for p in ruoli},
        prop_convocato={p: 0.8 for p in ruoli},
        ruolo=ruoli, squadra={}, moduli={},
        moduli_lega=[((4, 4, 2), 10), ((3, 5, 2), 5)],
        offset_convocato={(True, 1): 0.5, (False, 1): -0.5},
        p_sostituzioni=np.array([0.05, 0.15, 0.3, 0.3, 0.15, 0.05, 0.0]),
        minuti_ingresso=np.array([20.0, 30.0]),
        minuti_uscita=np.array([60.0, 70.0, 80.0]),
        p_titolare_sostituito=0.35)
    coef = {c: 0.0 for c in vt.COLONNE_EVENTI}
    coef.update({"gol_1": 0.9, "gol_2piu": 1.4, "assist": 0.5})
    m_ev = ev.ModelloEventi(
        tasso_gol={p: (0.35 if ruoli[p] == "A" else 0.1 if ruoli[p] == "C"
                       else 0.04 if ruoli[p] == "D" else 0.0) for p in ruoli},
        tasso_assist={p: 0.1 for p in ruoli},
        tasso_ammonizione={p: 0.2 for p in ruoli},
        tasso_espulsione={p: 0.01 for p in ruoli},
        tasso_ruolo={r: {"gol": 0.1, "assist": 0.1, "ammonizione": 0.2,
                         "espulsione": 0.01} for r in ("P", "D", "C", "A")},
        ruolo=ruoli, rigorista={}, quota_rigori=0.1, quota_autogol=0.03,
        quota_assist=0.7, p_rigore_sbagliato=0.2, p_rigore_parato=0.4,
        minuti_gol=np.arange(1, 91, dtype=float))
    m_voto = vt.ModelloVoto(
        coef=coef, alfa={p: 6.0 for p in ruoli},
        media_ruolo={r: 6.0 for r in ("P", "D", "C", "A")},
        sigma=0.45, specificazione="individuale")
    return cal, rose, mp, m_part, m_ev, m_voto, ruoli


def test_scenari_invarianti_all_ordine():
    """Cambiare l'ordine dei giocatori nelle rose non cambia gli scenari."""
    cal, rose, mp, m_part, m_ev, m_voto, _ = _finto()
    c1 = gen.genera(cal, rose, mp, m_part, m_ev, m_voto, n_sims=3, seme=5,
                    incertezza_forze=False)
    rose2 = {sq: list(reversed(v)) for sq, v in rose.items()}
    c2 = gen.genera(cal, rose2, mp, m_part, m_ev, m_voto, n_sims=3, seme=5,
                    incertezza_forze=False)
    assert c1.giocatori == c2.giocatori
    assert np.array_equal(c1.gioca, c2.gioca)
    assert np.allclose(c1.fantavoto, c2.fantavoto)


def test_risultati_invarianti_alle_rose_valutate():
    """La Serie A dello scenario non dipende da chi la sta guardando.

    E' la proprieta' che rende comparabili due rose diverse: se il numero di
    giocatori considerati cambiasse i risultati, il confronto porterebbe
    rumore comune invece di differenze vere."""
    cal, rose, mp, m_part, m_ev, m_voto, _ = _finto()
    c1 = gen.genera(cal, rose, mp, m_part, m_ev, m_voto, n_sims=2, seme=9,
                    incertezza_forze=False)
    ridotte = {sq: v[:14] for sq, v in rose.items()}
    c2 = gen.genera(cal, ridotte, mp, m_part, m_ev, m_voto, n_sims=2, seme=9,
                    incertezza_forze=False)
    assert c1.risultati == c2.risultati


def test_seme_diverso_scenari_diversi():
    cal, rose, mp, m_part, m_ev, m_voto, _ = _finto()
    c1 = gen.genera(cal, rose, mp, m_part, m_ev, m_voto, n_sims=2, seme=1,
                    incertezza_forze=False)
    c2 = gen.genera(cal, rose, mp, m_part, m_ev, m_voto, n_sims=2, seme=2,
                    incertezza_forze=False)
    assert not np.allclose(c1.fantavoto, c2.fantavoto)


def test_undici_titolari_e_un_portiere():
    """Ogni squadra scende in campo con undici e un solo portiere."""
    cal, rose, mp, m_part, m_ev, m_voto, ruoli = _finto()
    rng = np.random.default_rng(3)
    for _ in range(200):
        conv = list(rose["A"])
        rng.shuffle(conv)
        conv = conv[:int(rng.integers(11, 17))]
        # una rosa reale ha sempre un portiere e dieci di movimento: il
        # generatore lo garantisce con `_completa_convocati`, qui si riproduce
        conv = gen._completa_convocati(conv, rose["A"], m_part)
        conteggi = {}
        for pid in conv:
            conteggi[ruoli[pid]] = conteggi.get(ruoli[pid], 0) + 1
        modulo = pa.estrai_modulo(m_part, "A", rng, disponibili=conteggi)
        tit, pan = pa.scegli_undici(conv, m_part, modulo, rng)
        assert len(tit) == 11, (len(tit), modulo)
        assert sum(1 for p in tit if ruoli[p] == "P") == 1
        assert len(set(tit)) == 11
        assert not (set(tit) & set(pan))


def test_minuti_coerenti():
    """Nessuno gioca piu' di 90 minuti; chi entra prende il posto di chi esce."""
    cal, rose, mp, m_part, m_ev, m_voto, ruoli = _finto()
    rng = np.random.default_rng(4)
    for _ in range(100):
        tit, pan = pa.scegli_undici(list(rose["B"]), m_part, (4, 4, 2), rng)
        pres = pa.genera_minuti(tit, pan, m_part, rng)
        for pid, (a, b) in pres.intervalli.items():
            assert 0 <= a <= b <= 90
        for minuto in (0, 30, 60, 89):
            in_campo = sum(1 for iv in pres.intervalli.values()
                           if pa.in_campo_al(iv, minuto))
            assert in_campo == 11, (minuto, in_campo)


def test_tabellini_riconciliano_col_risultato():
    """I gol dei giocatori piu' gli autogol avversari fanno il risultato."""
    cal, rose, mp, m_part, m_ev, m_voto, _ = _finto()
    c = gen.genera(cal, rose, mp, m_part, m_ev, m_voto, n_sims=1, seme=11,
                   incertezza_forze=False, verifica=True)
    assert c.diagnostica["n_problemi_coerenza"] == 0, \
        c.diagnostica["problemi_coerenza"]


def test_nessuna_anticipazione_nella_formazione():
    """La politica di formazione non vede gli esiti della giornata.

    Il controllo e' comportamentale: si sostituisce `pick_lineup` con una spia
    che registra che cosa ha ricevuto, e si verifica che l'insieme dei
    disponibili sia quello della giornata PRECEDENTE, mai quello corrente."""
    from fantabot.season import simulate as sim
    visti = []
    vero = sim.pick_lineup

    def spia(roster, form, form_voto=None, use_mod=False, available=None):
        visti.append(None if available is None else set(available))
        return vero(roster, form, form_voto, use_mod, available)

    sim.pick_lineup = spia
    try:
        rosters = {"T1": {"P": ["1"], "D": ["2", "3", "4", "5"],
                          "C": ["6", "7", "8", "9"], "A": ["10", "11"]},
                   "T2": {"P": ["12"], "D": ["13", "14", "15", "16"],
                          "C": ["17", "18", "19", "20"], "A": ["21", "22"]}}
        votes = [{str(i): 6.0 for i in range(1, 23) if i % (g + 2) != 0}
                 for g in range(5)]
        sim.simulate_season(rosters, votes, n_calendars=2, seed=1)
    finally:
        sim.pick_lineup = vero
    assert visti[0] is None, "alla prima giornata non esiste un passato"
    for g in range(1, 5):
        atteso = set(votes[g - 1].keys())
        for k in (g * 2, g * 2 + 1):
            assert visti[k] == atteso, (g, visti[k], atteso)


# ---------------------------------------------------------------------------
# Invarianti fisiche del cubo (contratto CRITERI_L2_L3.md, sezione 7.4).
# Ogni test qui sotto falliva prima della correzione del 7 settembre 2026: il
# rapporto in data/l3/fix/generatore/RAPPORTO.md riporta, per ciascuno, che
# cosa succedeva e con che numeri.
# ---------------------------------------------------------------------------

def _mondo_portieri(p_cambio=0.5):
    """Mondo finto con un cambio del portiere frequente.

    La probabilita' vera e' 0,0138: qui si alza per esercitare il ramo senza
    dover generare decine di migliaia di partite. Quello che il test verifica
    non e' la frequenza (che si misura sui dati) ma l'invariante.
    """
    cal, rose, mp, m_part, m_ev, m_voto, ruoli = _finto()
    m_part.p_cambio_portiere = p_cambio
    m_part.minuti_cambio_portiere = np.array([20.0, 46.0, 70.0])
    return cal, rose, mp, m_part, m_ev, m_voto, ruoli


def test_portiere_in_campo_in_ogni_minuto():
    """Invariante 7.4.1: un portiere in campo in ogni minuto di ogni partita.

    Prima della correzione le uscite si estraevano fra tutti e undici i
    titolari e a entrare erano i primi della panchina, dove il portiere di
    riserva sta in fondo: nella prova isolata il portiere usciva in 446 partite
    su 1000 e in tutte e 446 la squadra restava senza portiere."""
    cal, rose, mp, m_part, m_ev, m_voto, ruoli = _mondo_portieri()
    rng = np.random.default_rng(7)
    cambi = 0
    for _ in range(300):
        tit, pan = pa.scegli_undici(list(rose["A"]), m_part, (4, 4, 2), rng)
        pres = pa.genera_minuti(tit, pan, m_part, rng)
        assert pres.minuti_senza_portiere() == 0
        for minuto in range(90):
            p = pres.portiere_al(minuto)
            assert p is not None, minuto
            assert pa.in_campo_al(pres.intervalli[p], minuto), (minuto, p)
            assert ruoli[p] == "P", (minuto, p, ruoli[p])
        if len(pres.portiere) > 1:
            cambi += 1
    assert cambi > 0, "il ramo del cambio del portiere non e' stato esercitato"


def test_il_portiere_non_esce_nei_cambi_di_movimento():
    """Invariante 7.4.2: il cambio del portiere e' un'estrazione a parte.

    Con `p_cambio_portiere = 0` nessun portiere deve lasciare il campo, per
    quante sostituzioni si facciano. Prima della correzione usciva nel 45 %
    circa delle partite, perche' l'estrazione delle uscite comprendeva anche
    lui."""
    cal, rose, mp, m_part, m_ev, m_voto, ruoli = _finto()
    m_part.p_cambio_portiere = 0.0
    rng = np.random.default_rng(11)
    for _ in range(300):
        tit, pan = pa.scegli_undici(list(rose["C"]), m_part, (4, 4, 2), rng)
        pres = pa.genera_minuti(tit, pan, m_part, rng)
        portieri_titolari = [p for p in tit if ruoli[p] == "P"]
        for p in portieri_titolari:
            assert pres.intervalli[p] == [0, 90], (p, pres.intervalli[p])
        for p in pan:
            if ruoli[p] == "P":
                assert pres.intervalli[p] == [0, 0], (p, pres.intervalli[p])


def test_espulsione_accorcia_intervallo_e_vieta_la_sostituzione():
    """Invariante 7.4.3: l'espulso esce al minuto del rosso e non e' sostituito.

    Prima della correzione l'espulsione era una Bernoulli senza minuto che non
    cambiava niente: 107 espulsi su 182 giocavano 90 minuti e 54 su 182
    risultavano sostituiti dopo l'espulsione."""
    cal, rose, mp, m_part, m_ev, m_voto, ruoli = _finto()
    rng = np.random.default_rng(13)
    provati = 0
    for _ in range(200):
        tit, pan = pa.scegli_undici(list(rose["D"]), m_part, (4, 4, 2), rng)
        pres = pa.genera_minuti(tit, pan, m_part, rng)
        sost = [s for s in pres.sostituzioni if s[0] > 20]
        if not sost:
            continue
        minuto_sost, uscito, entrato = sost[0]
        minuto = minuto_sost - 10
        pa.applica_espulsione(pres, uscito, minuto, m_part)
        provati += 1
        assert pres.intervalli[uscito] == [0, minuto]
        assert pres.espulsi[uscito] == minuto
        # chi sarebbe entrato al suo posto resta in panchina: la squadra
        # prosegue in dieci
        assert pres.intervalli[entrato] == [0, 0]
        assert all(u != uscito for _, u, _ in pres.sostituzioni)
        in_campo = sum(1 for iv in pres.intervalli.values()
                       if pa.in_campo_al(iv, minuto + 1))
        assert in_campo == 10, in_campo
    assert provati >= 10


def test_espulsione_del_portiere_lascia_la_porta_presidiata():
    """Se il portiere e' espulso entra il portiere di riserva; se non c'e', uno
    di movimento va in porta e la cosa e' rappresentata esplicitamente."""
    cal, rose, mp, m_part, m_ev, m_voto, ruoli = _finto()
    rng = np.random.default_rng(17)
    tit, pan = pa.scegli_undici(list(rose["A"]), m_part, (4, 4, 2), rng)
    portiere = [p for p in tit if ruoli[p] == "P"][0]

    pres = pa.genera_minuti(tit, pan, m_part, rng)
    esito = pa.applica_espulsione(pres, portiere, 40, m_part)
    assert esito["portiere_di_riserva"] is not None
    assert ruoli[esito["portiere_di_riserva"]] == "P"
    assert pres.minuti_senza_portiere() == 0
    assert sum(1 for iv in pres.intervalli.values()
               if pa.in_campo_al(iv, 41)) == 10

    # stessa cosa con una panchina senza portieri: qualcuno prende i guantoni
    pan_senza_p = [p for p in pan if ruoli[p] != "P"]
    pres2 = pa.genera_minuti(tit, pan_senza_p, m_part, rng)
    esito2 = pa.applica_espulsione(pres2, portiere, 40, m_part)
    assert esito2["portiere_di_movimento"] is not None
    assert pres2.minuti_senza_portiere() == 0
    assert any(mov for _, _, _, mov in pres2.portiere)


def test_gol_dentro_l_intervallo_di_chi_segna():
    """Invariante 7.4.4, compreso il minuto 90.

    La fonte registra al minuto 90 tutto quello che accade dal 90' in poi (il
    7,57 % dei gol). Con l'intervallo aperto a destra secco, al 90' non c'era
    nessuno in campo e il ripiego assegnava il gol a chiunque: il 2,10 % di
    tutti i gol finiva a un giocatore gia' uscito."""
    cal, rose, mp, m_part, m_ev, m_voto, ruoli = _finto()
    m_ev.minuti_gol = np.array([90.0])          # tutti i gol nel recupero
    rng = np.random.default_rng(19)
    fuori_intervallo = 0
    for _ in range(200):
        tit, pan = pa.scegli_undici(list(rose["B"]), m_part, (4, 4, 2), rng)
        pres = pa.genera_minuti(tit, pan, m_part, rng)
        e = ev.genera(m_ev, "B", tit + pan, pres, 3, 1, rng)
        assert e.note["gol_senza_nessuno_in_campo"] == 0
        for evento in e.cronologia:
            if not pa.in_campo_al(pres.intervalli[evento["autore"]],
                                  evento["minuto"]):
                fuori_intervallo += 1
    assert fuori_intervallo == 0


def test_rigore_parato_abbinato_al_rigore_sbagliato():
    """Invariante 7.4.6: un evento solo visto dai due lati.

    Prima della correzione `rigori_sbagliati()` non era chiamata da nessuno e i
    campi `rigori_sbagliati` e `rigori_parati` restavano a zero: i due termini
    +3/-3 della formula del fantavoto valevano sempre zero nel cubo."""
    cal, rose, mp, m_part, m_ev, m_voto, ruoli = _finto()
    m_ev.rigori_sbagliati_per_partita = 2.0     # alta per esercitare il ramo
    m_ev.p_rigore_parato = 0.6
    rng = np.random.default_rng(23)
    parati = sbagliati = 0
    for _ in range(200):
        tit_a, pan_a = pa.scegli_undici(list(rose["A"]), m_part, (4, 4, 2), rng)
        tit_b, pan_b = pa.scegli_undici(list(rose["B"]), m_part, (4, 4, 2), rng)
        pa_a = pa.genera_minuti(tit_a, pan_a, m_part, rng)
        pa_b = pa.genera_minuti(tit_b, pan_b, m_part, rng)
        for rig in ev.genera_rigori_sbagliati(m_ev, "A", pa_a, pa_b, rng):
            sbagliati += 1
            # il tiratore deve essere in campo a quel minuto
            assert pa.in_campo_al(pa_a.intervalli[rig["tiratore"]],
                                  rig["minuto"])
            if rig["parato_da"] is not None:
                parati += 1
                # e il portiere pure, e deve essere il portiere di quel minuto
                assert rig["parato_da"] == pa_b.portiere_al(rig["minuto"])
                assert pa.in_campo_al(pa_b.intervalli[rig["parato_da"]],
                                      rig["minuto"])
    assert sbagliati > 100
    assert parati > 0


def test_minuti_ed_eventi_conservati_per_gli_sv():
    """Invariante 7.4.7: chi prende s.v. conserva minuti ed eventi.

    Prima della correzione il `continue` prima della scrittura degli array
    lasciava fuori minuti, gol, assist e ammonizioni. Rimisurato sullo stesso
    seme e sugli stessi tre scenari (data/l3/fix/generatore/m1_prima_dopo.json):
    dei 2 720 gol generati ne arrivavano negli array 2 674, dei 1 737 assist
    1 718, e i minuti dei 2 488 giocatore-partita con s.v. erano zero."""
    cal, rose, mp, m_part, m_ev, m_voto, _ = _finto()
    # tutti quelli che giocano meno di mezz'ora prendono s.v.
    fasce = {"fasce": [(0, 30, 1.0)]}
    c = gen.genera(cal, rose, mp, m_part, m_ev, m_voto, n_sims=2, seme=31,
                   incertezza_forze=False, fasce_sv=fasce)
    sv = c.in_campo & ~c.gioca
    assert sv.sum() > 0, "nessun s.v. generato: il test non prova niente"
    assert c.minuti[sv].sum() > 0, "minuti persi per chi prende s.v."
    assert (c.minuti[sv] > 0).all(), "un s.v. senza minuti"
    # il punteggio della lega resta zero: sono tre cose separate, e solo la
    # terza dipende dal voto della fonte
    assert np.all(c.fantavoto[sv] == 0)


def test_gol_subiti_del_portiere_per_periodo():
    """Invariante 7.4.5: al portiere i gol presi mentre era in porta.

    Prima della correzione i gol subiti venivano dal risultato finale e li
    prendeva ogni portiere a voto: eccesso di 0,152 gol subiti per portiere, e
    in 33 squadra-partita su 2 100 due portieri prendevano entrambi tutti i
    gol."""
    pres = pa.Presenze(
        intervalli={"p0": [0, 45], "p1": [45, 90]},
        portiere=[(0, 45, "p0", False), (45, 90, "p1", False)])
    assert gen.gol_subiti_per_portiere(pres, [10.0, 70.0]) == {"p0": 1, "p1": 1}
    assert gen.gol_subiti_per_portiere(pres, [10.0, 20.0]) == {"p0": 2, "p1": 0}
    # un gol nel recupero va a chi era in porta alla fine
    assert gen.gol_subiti_per_portiere(pres, [90.0]) == {"p0": 0, "p1": 1}
    # somma conservata: nessun gol perso, nessuno contato due volte
    for minuti in ([], [1.0], [1.0, 44.0, 45.0, 89.0, 90.0]):
        assert sum(gen.gol_subiti_per_portiere(pres, minuti).values()) == len(minuti)


def test_catena_convocazione_conserva_il_tasso():
    """Sommare uno scostamento al logit NON conserva il tasso medio.

    La base va calibrata sulla distribuzione stazionaria della catena. Il test
    misura lo scarto con la base vecchia e verifica che quella nuova lo
    chiuda."""
    # scostamenti realmente stimati sul panel del cubo 2026-27: sono
    # asimmetrici (chi e' fuori da tre giornate paga -1,52, chi c'e' da tre
    # guadagna +1,05), ed e' l'asimmetria a spostare la media
    off = {(False, 1): -1.1936, (False, 2): -1.3699, (False, 3): -1.5151,
           (False, 4): -1.6387, (False, 5): -1.5167, (False, 6): -1.7649,
           (False, 7): -2.1043, (False, 8): -1.8717,
           (True, 1): 0.9382, (True, 2): 0.9270, (True, 3): 1.0526,
           (True, 4): 1.0683, (True, 5): 1.0138, (True, 6): 1.0720,
           (True, 7): 0.9912, (True, 8): 0.5538}
    bersagli = [0.2, 0.5, 0.8, 0.95]
    vecchio = [abs(pa.media_catena(float(np.log(p / (1 - p))), off) - p)
               for p in bersagli]
    assert max(vecchio) > 0.05, ("senza scarto il test non prova niente",
                                 vecchio)
    basi, diag = pa.calibra_base_convocazione({i: p for i, p in enumerate(bersagli)},
                                              off)
    nuovo = [abs(pa.media_catena(basi[i], off) - p)
             for i, p in enumerate(bersagli)]
    assert max(nuovo) < 1e-3, (nuovo, diag)


def test_denominatore_solo_eleggibili():
    """Contratto 7.1: al denominatore solo le righe con `eleggibile == True`.

    Con la colonna presente, una riga non eleggibile non deve abbassare la
    propensione di nessuno; senza la colonna il modello ripiega sul criterio
    vecchio ma lo dichiara."""
    righe = []
    for g in range(1, 11):
        for pid, elegg in (("x", True), ("y", False)):
            righe.append({
                "master_id": pid, "giornata": g, "stagione": "2025-26",
                "data": pd.Timestamp("2025-08-01") + pd.Timedelta(days=7 * g),
                "squadra_alla_data": "A", "ruolo": "C",
                "eleggibile": elegg, "minuti": 90.0,
                "stato_convocazione": "titolare" if elegg else "escluso"})
    P = pd.DataFrame(righe)
    m = pa.stima(P, min_partite=0)
    assert m.diagnostica["denominatore"]["verificato"] is True
    assert m.diagnostica["denominatore"]["righe_eleggibili"] == 10
    assert m.prop_convocato["x"] == pytest.approx(1.0)
    assert "y" not in m.prop_convocato
    # panel vecchio: nessuna colonna `eleggibile`, e il modello lo dichiara
    Q = P.drop(columns=["eleggibile"]).copy()
    Q["stato_convocazione"] = Q["stato_convocazione"].replace(
        {"escluso": "non_in_rosa"})
    m2 = pa.stima(Q, min_partite=0)
    assert m2.diagnostica["denominatore"]["verificato"] is False
    assert "avvertenza" in m2.diagnostica["denominatore"]
    assert m2.prop_convocato["y"] == pytest.approx(0.0)


def test_punteggio_della_fonte():
    """La formula del punteggio e' quella verificata sui dati."""
    t = Tabellino(ruolo="A", voto=7.0, minuti=90, gol=1, assist=1,
                  ammonizione=1)
    assert fantavoto(t) == pytest.approx(7.0 + 3 + 1 - 0.5)
    p = Tabellino(ruolo="P", voto=6.0, minuti=90, gol_subiti=2, rigori_parati=1)
    assert fantavoto(p) == pytest.approx(6.0 + 3 - 2)
    # il rigore segnato NON e' compreso nei gol: vale 3 punti a parte
    r = Tabellino(ruolo="C", voto=6.5, minuti=90, gol=1, rigore_segnato=1)
    assert fantavoto(r) == pytest.approx(6.5 + 6)


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
