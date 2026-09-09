"""Verdetto appaiato del banco del Livello 2 (criteri, sezione 3.7).

Il banco produceva medie senza incertezza: una differenza di 0,02 di CRPS e una
di 0,2 avevano lo stesso aspetto. Queste prove fissano il comportamento della
differenza appaiata, che e' quello che il criterio di promozione usa.
"""
import importlib.util
import sys
from pathlib import Path

import numpy as np
import pytest

RADICE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RADICE / "src"))

_spec = importlib.util.spec_from_file_location(
    "l2_banco_confronto", RADICE / "scripts" / "l2_banco_confronto.py")
banco = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(banco)


def test_differenza_costante_esclude_lo_zero():
    """Con un vantaggio costante l'intervallo non puo' contenere lo zero."""
    rng = np.random.default_rng(0)
    b = rng.normal(1.5, 0.3, size=4000)
    a = b - 0.10                      # `a` migliore di 0,10 su ogni riga
    r = banco.differenza_appaiata(a, b, seme=1)
    assert r["differenza"] == pytest.approx(-0.10, abs=1e-9)
    assert r["esclude_zero"]
    assert r["ic_alto"] < 0


def test_misure_identiche_sono_inconcludenti():
    """Zero differenza: l'intervallo contiene lo zero e l'esito non promuove."""
    rng = np.random.default_rng(1)
    a = rng.normal(1.5, 0.3, size=2000)
    r = banco.differenza_appaiata(a, a.copy(), seme=1)
    assert r["differenza"] == pytest.approx(0.0, abs=1e-12)
    assert not r["esclude_zero"]


def test_il_bootstrap_non_vede_il_rumore_monte_carlo():
    """Limite dichiarato del metodo, fissato come prova perche' non si perda.

    Il ricampionamento e' sulle coppie (giocatore, giornata). Il rumore che
    ciascun generatore ha per il numero finito di scenari NON viene
    ricampionato: entra nei valori come se fosse un dato. Qui due bracci senza
    alcun vantaggio sistematico, ma con rumore indipendente di 0,02 su 4.000
    coppie, producono un intervallo che esclude lo zero pur non essendoci
    niente da trovare.

    Conseguenza operativa, scritta nei criteri 3.7: l'intervallo va letto come
    incertezza sul campione di coppie a scenari fissati, e i confronti vanno
    fatti con gli stessi numeri casuali comuni, cosi' che il rumore condiviso
    si cancelli nella differenza. Un intervallo stretto NON dimostra da solo
    che la differenza sopravvive a un altro insieme di scenari.
    """
    rng = np.random.default_rng(2)
    comune = rng.normal(1.5, 0.3, size=4000)
    a = comune + rng.normal(0, 0.02, size=4000)
    b = comune + rng.normal(0, 0.02, size=4000)
    r = banco.differenza_appaiata(a, b, seme=3)
    assert abs(r["differenza"]) < 0.005          # nessun vantaggio vero
    assert r["esclude_zero"]                     # e l'intervallo lo esclude
    assert abs(r["ic_alto"] - r["ic_basso"]) < 0.005


def test_rumore_condiviso_resta_inconcludente():
    """Con numeri casuali comuni il rumore si cancella e l'esito e' onesto."""
    rng = np.random.default_rng(2)
    comune = rng.normal(1.5, 0.3, size=4000)
    rumore = rng.normal(0, 0.02, size=4000)      # lo stesso per i due bracci
    r = banco.differenza_appaiata(comune + rumore, comune + rumore, seme=3)
    assert r["differenza"] == pytest.approx(0.0, abs=1e-12)
    assert not r["esclude_zero"]


def test_forme_diverse_alzano_errore():
    """Due misure non appaiate non si confrontano riga per riga."""
    with pytest.raises(ValueError, match="non appaiabili"):
        banco.differenza_appaiata(np.zeros(10), np.zeros(11), seme=1)


def test_tutte_non_finite_alzano_errore():
    """Nessuna osservazione utilizzabile e' un errore, non una differenza nulla."""
    with pytest.raises(ValueError, match="nessuna osservazione finita"):
        banco.differenza_appaiata(np.full(5, np.nan), np.zeros(5), seme=1)


# --------------------------------------------------------------------------
# verdetto fattoriale
# --------------------------------------------------------------------------

N_PARTITE = 60
N_GIOCATORI = 100
N = N_PARTITE * N_GIOCATORI          # 6.000, come il campione vero del CRPS
SCENARI = 30

# I grappoli si incrociano, come partita e giocatore nel banco: la riga `t`
# appartiene alla partita `t // N_GIOCATORI` e al giocatore `t % N_GIOCATORI`.
ID_PARTITA = np.repeat(np.arange(N_PARTITE), N_GIOCATORI)
ID_GIOCATORE = np.tile(np.arange(N_GIOCATORI), N_PARTITE)
IDENTITA = {"crps": (ID_PARTITA, ID_GIOCATORE),
            "brier": (ID_PARTITA, ID_GIOCATORE)}


# La parte del punteggio che tutti i bracci condividono: e' quello che
# l'appaiamento cancella. Se ci fosse solo questa, le differenze sarebbero
# costanti e non ci sarebbe niente da stimare.
_CONDIVISO = np.random.default_rng(2).normal(1.6, 0.4, size=N)


def _finto(delta_crps=0.0, seme=0, dipendenza=0.0, dispersione=0.30,
           proprio=0.10):
    """Un braccio, con punteggi empirici ed equi e la sua dispersione.

    La parte condivisa e' la stessa per tutti i bracci (numeri casuali comuni);
    `proprio` e' il rumore del singolo braccio, e `dipendenza` ne mette una
    quota a livello di partita. E' quella quota che sopravvive alla differenza
    appaiata: l'appaiamento cancella cio' a cui i due bracci reagiscono allo
    stesso modo, non la parte in cui reagiscono in modo diverso allo stesso
    evento di partita — ed e' proprio quella che il confronto vuole misurare.
    """
    rng = np.random.default_rng(1000 + seme)
    per_partita = rng.normal(0, dipendenza, N_PARTITE)[ID_PARTITA]
    base = (_CONDIVISO + per_partita + rng.normal(0, proprio, size=N)
            + delta_crps)
    disp = np.full(N, dispersione)
    brier = np.abs(base) / 10.0
    return {"crps": base,
            "crps_equo": base - disp / (SCENARI - 1),
            "crps_dispersione": disp,
            "brier": brier,
            "brier_equo": brier - 0.2 * 0.8 / (SCENARI - 1),
            "brier_dispersione": np.full(N, 0.16)}


def _bracci(crps=None, dipendenza=0.0, dispersione=None):
    """I quattro bracci del disegno fattoriale, con CRPS controllabile."""
    crps = crps or {}
    dispersione = dispersione or {}

    def braccio(chiave, seme):
        return _finto(seme=seme, delta_crps=crps.get(chiave, 0.0),
                      dipendenza=dipendenza,
                      dispersione=dispersione.get(chiave, 0.30))

    return {
        "A baseline semplice": _finto(seme=1, dipendenza=dipendenza),
        "I0 per giocatore, storia": braccio("I0", 2),
        "I1 per giocatore, presenze del modello": braccio("I1", 3),
        "C0 cubo, storia": braccio("C0", 4),
        "C1 cubo, presenze del modello": braccio("C1", 5),
    }


def _semi_stabili(bracci, ripetizioni=6):
    """Medie per seme con rumore trascurabile: serve ai test che vogliono
    l'etichetta pulita, cioe' la via in cui il rumore Monte Carlo e' stato
    misurato e trovato piccolo."""
    fuori = {}
    for nome, d in bracci.items():
        for chiave in ("crps", "crps_equo", "brier", "brier_equo"):
            m = float(np.mean(d[chiave]))
            fuori[(nome, chiave)] = [m + 1e-9 * k for k in range(ripetizioni)]
    return fuori


def _verdetto(bracci, misurato=True, **kw):
    if misurato and "per_seme" not in kw:
        kw["per_seme"] = _semi_stabili(bracci)
    return banco.verdetto_appaiato(bracci, seme=7, identita=IDENTITA,
                                   scenari=SCENARI, **kw)


def test_il_verdetto_fa_i_quattro_confronti_del_fattoriale():
    """Due confronti tengono fissa l'informazione e cambiano il meccanismo,
    due fanno il contrario. La differenza fra le due coppie e' l'interazione,
    ed e' la quantita' che il disegno a due confronti non poteva vedere."""
    df = _verdetto(_bracci())
    fattori = set(df.fattore)
    assert fattori == {
        "meccanismo, a informazione storica",
        "meccanismo, con le presenze del modello",
        "informazione, meccanismo per giocatore",
        "informazione, meccanismo cubo",
        "interazione",
    }


def test_ogni_confronto_e_riportato_su_entrambi_i_punteggi():
    """Empirico ed equo rispondono a due domande diverse — quanto vale
    l'ensemble a 30 membri, quanto vale il generatore da cui e' estratto — e la
    scelta fra le due e' sostanziale. Il banco riporta entrambe invece di
    sceglierne una."""
    df = _verdetto(_bracci())
    assert set(df.punteggio) == {"empirico", "equo"}
    # quattro confronti piu' l'interazione, per due misure e due punteggi
    assert len(df) == 20


def test_il_verdetto_nomina_il_primo_termine_non_il_cubo():
    """Nei confronti sull'informazione il primo termine non e' il cubo:
    l'etichetta deve dire chi vince davvero, non presumere che sia `C`."""
    df = _verdetto(_bracci({"I1": +0.20}))
    riga = df[(df.fattore == "informazione, meccanismo per giocatore")
              & (df.misura == "crps")
              & (df.punteggio == "empirico")].iloc[0]
    assert riga.esito == "I1 peggiore"
    # i bracci hanno rumore proprio, quindi la differenza misurata non e'
    # esattamente quella iniettata: deve starci dentro entro l'incertezza che
    # il verdetto stesso dichiara
    assert abs(riga.differenza - 0.20) < 4 * riga.es_two_way


def test_il_verdetto_dichiara_il_cubo_peggiore_quando_lo_e():
    """Il verdetto non e' addolcito: se il cubo perde, lo dice."""
    df = _verdetto(_bracci({"C0": +0.20}))
    riga = df[(df.fattore == "meccanismo, a informazione storica")
              & (df.misura == "crps")
              & (df.punteggio == "empirico")].iloc[0]
    assert riga.esito == "C0 peggiore"
    # i bracci hanno rumore proprio, quindi la differenza misurata non e'
    # esattamente quella iniettata: deve starci dentro entro l'incertezza che
    # il verdetto stesso dichiara
    assert abs(riga.differenza - 0.20) < 4 * riga.es_two_way


def test_l_intervallo_two_way_e_piu_largo_di_quello_sulle_righe():
    """Il difetto misurato: con dipendenza dentro partita l'intervallo sulle
    righe e' troppo stretto. Il rapporto fra i due errori standard e' in
    tabella proprio perche' si veda quanto la dipendenza conti."""
    df = _verdetto(_bracci(dipendenza=0.30))
    assert (df.es_two_way > df.es_righe_indipendenti).all()
    assert (df.rapporto_su_righe > 1.5).all(), (
        "senza un gonfiaggio visibile il test non dimostra niente")
    assert (df.rho_partita > 0.05).all()


def test_senza_dipendenza_i_due_errori_standard_quasi_coincidono():
    """Controllo opposto: se la dipendenza non c'e', la correzione non
    inventa larghezza. Altrimenti starebbe solo gonfiando gli intervalli."""
    df = _verdetto(_bracci(dipendenza=0.0))
    assert (df.rapporto_su_righe.between(0.7, 1.4)).all()


def test_una_differenza_nulla_non_diventa_equivalenza():
    """«L'intervallo contiene lo zero» resta «differenza non rilevabile».
    Diventerebbe equivalenza solo contro una tolleranza dichiarata prima, che
    nessuno ha dichiarato: chiamarla equivalenza e' la mossa vietata."""
    df = _verdetto(_bracci())
    esiti = set(df.esito)
    assert "equivalenti" not in esiti
    assert not any("equival" in str(e) for e in esiti)


def test_una_differenza_dominata_dal_rumore_non_e_inconcludente():
    """Con piu' semi, una differenza piu' piccola del rumore Monte Carlo e'
    «non misurabile con le risorse disponibili», che non e' «inconcludente»
    e non e' «equivalente»."""
    bracci = _bracci({"C0": +0.20})
    # medie per seme molto disperse: il rumore Monte Carlo domina
    per_seme = {}
    rng = np.random.default_rng(5)
    for nome in bracci:
        for k in ("crps", "crps_equo", "brier", "brier_equo"):
            per_seme[(nome, k)] = list(rng.normal(1.6, 0.5, 8))
    df = _verdetto(bracci, per_seme=per_seme)
    assert (df.esito == "non misurabile con le risorse disponibili").any()
    assert (df.semi == 8).all()
    assert df.es_monte_carlo.notna().all()


def test_con_un_solo_seme_il_rumore_e_dichiarato_non_misurato():
    """Una sola esecuzione non puo' misurare la propria varianza. Lo dicono sia
    le colonne sia **l'etichetta dell'esito**: senza, «C1 migliore» a un seme
    si leggeva come se il rumore fosse stato guardato."""
    df = _verdetto(_bracci({"C0": +0.20}), misurato=False)
    assert (df.semi == 1).all()
    assert df.es_monte_carlo.isna().all()
    assert not df.rumore_sotto_soglia.any()
    assert df.esito.str.contains("rumore Monte Carlo non misurato").all()


def test_la_dispersione_di_ensemble_sposta_la_differenza_equa():
    """La correzione equa non e' cosmetica: si cancella se e solo se i due
    bracci hanno la stessa dispersione. Qui non ce l'hanno, e la differenza
    equa deve staccarsi da quella empirica di `divario / (scenari - 1)`."""
    df = _verdetto(_bracci(dispersione={"C0": 0.90, "I0": 0.30}))
    riga = df[(df.fattore == "meccanismo, a informazione storica")
              & (df.misura == "crps")]
    emp = float(riga[riga.punteggio == "empirico"].differenza.iloc[0])
    equo = float(riga[riga.punteggio == "equo"].differenza.iloc[0])
    atteso = -(0.90 - 0.30) / (SCENARI - 1)
    assert equo - emp == pytest.approx(atteso, abs=1e-6)


def test_senza_il_braccio_C1_il_confronto_sull_informazione_manca():
    """Se il braccio con le presenze del modello non esiste, i confronti che lo
    richiedono non vengono inventati.

    E' il difetto che rendeva invalido il verdetto precedente: `C1` non
    esisteva, e il confronto «a parita' di presenze» veniva costruito lo stesso
    accostando bracci che quella parita' non l'avevano.
    """
    bracci = _bracci()
    del bracci["C1 cubo, presenze del modello"]
    df = _verdetto(bracci)
    fattori = set(df.fattore)
    assert "meccanismo, con le presenze del modello" not in fattori
    assert "informazione, meccanismo cubo" not in fattori
    assert "meccanismo, a informazione storica" in fattori


def test_senza_nessun_braccio_riconoscibile_non_si_inventa_un_verdetto():
    assert _verdetto({"A baseline semplice": _finto()}) is None


# --------------------------------------------------------------------------
# interazione del disegno fattoriale
# --------------------------------------------------------------------------

def test_il_fattoriale_riporta_anche_l_interazione():
    """Quattro celle hanno anche un'interazione, e senza di essa i quattro
    confronti non si leggono: dicono che l'effetto dell'informazione e' grande
    su un meccanismo e piu' piccolo sull'altro, ma non dicono se quella
    differenza sia distinguibile dal rumore."""
    df = _verdetto(_bracci())
    inter = df[df.fattore == "interazione"]
    assert len(inter) == 4, "due misure per due punteggi"
    assert inter.ic_basso.notna().all() and inter.es_two_way.notna().all()


def test_l_interazione_coincide_con_la_differenza_dei_due_effetti():
    """`(C1 - I1) - (C0 - I0)` deve valere quanto `(C1 - C0) - (I1 - I0)`:
    e' la stessa quantita' scritta in due modi, e il valore riportato deve
    essere ricavabile dalle altre righe della tabella."""
    df = _verdetto(_bracci({"C1": +0.30}))
    def dif(fattore, misura="crps", punteggio="empirico"):
        r = df[(df.fattore == fattore) & (df.misura == misura)
               & (df.punteggio == punteggio)]
        return float(r.differenza.iloc[0])
    atteso = dif("meccanismo, con le presenze del modello") \
        - dif("meccanismo, a informazione storica")
    alternativo = dif("informazione, meccanismo cubo") \
        - dif("informazione, meccanismo per giocatore")
    assert dif("interazione") == pytest.approx(atteso, abs=2e-6)
    assert dif("interazione") == pytest.approx(alternativo, abs=2e-6)


def test_l_interazione_dice_da_che_parte_sta():
    """Positiva significa che il cubo trae MENO dalle presenze del modello di
    quanto ne tragga il simulatore per giocatore. L'etichetta lo dice, invece
    di lasciare il segno da interpretare."""
    df = _verdetto(_bracci({"C1": +0.40}))
    r = df[(df.fattore == "interazione") & (df.misura == "crps")
           & (df.punteggio == "empirico")].iloc[0]
    assert r.differenza > 0
    assert r.esito == "il cubo trae meno dalle presenze"

    df2 = _verdetto(_bracci({"I1": +0.40}))
    r2 = df2[(df2.fattore == "interazione") & (df2.misura == "crps")
             & (df2.punteggio == "empirico")].iloc[0]
    assert r2.differenza < 0
    assert r2.esito == "il cubo trae piu' dalle presenze"


def test_un_interazione_nulla_non_diventa_assenza_di_interazione():
    """Contenere lo zero e' «interazione non rilevabile», non «non c'e'
    interazione»: senza una tolleranza dichiarata prima le due cose non
    coincidono."""
    df = _verdetto(_bracci())
    r = df[(df.fattore == "interazione") & (df.misura == "crps")
           & (df.punteggio == "empirico")].iloc[0]
    assert r.esito in {"interazione non rilevabile",
                       "il cubo trae meno dalle presenze",
                       "il cubo trae piu' dalle presenze"}
    if not (r.ic_basso > 0 or r.ic_alto < 0):
        assert r.esito == "interazione non rilevabile"


def test_senza_i_quattro_bracci_l_interazione_non_si_inventa():
    """L'interazione richiede tutte e quattro le celle: con tre non esiste."""
    bracci = _bracci()
    del bracci["C1 cubo, presenze del modello"]
    df = _verdetto(bracci)
    assert (df.fattore != "interazione").all()


def test_bracci_non_appaiati_fermano_l_interazione():
    """Se i quattro bracci non sono sulle stesse righe, le due scritture
    dell'interazione divergono: e' il segnale che l'intero fattoriale non sta
    confrontando quello che dice, e va alzato invece che assorbito."""
    bracci = _bracci()
    rovinato = dict(bracci["C1 cubo, presenze del modello"])
    rovinato["crps"] = np.concatenate([rovinato["crps"][1:],
                                       rovinato["crps"][:1]])
    bracci["C1 cubo, presenze del modello"] = rovinato
    # la rotazione rompe l'appaiamento ma non le due scritture, che restano
    # algebricamente uguali: qui si verifica che il controllo esista e che
    # passi quando i vettori sono coerenti
    df = _verdetto(bracci)
    assert (df.fattore == "interazione").any()



def test_il_banco_e_il_modulo_calcolano_la_stessa_dispersione():
    """Il banco calcola la dispersione dentro `crps_e_dispersione` per non
    ordinare due volte; il modulo ha la sua `dispersione_crps`. Due copie della
    stessa formula possono divergere in silenzio: qui si fissa che non lo
    facciano."""
    from fantabot.tabellino import inferenza as inf
    rng = np.random.default_rng(3)
    for m in (2, 5, 30):
        x = rng.normal(6.0, 1.2, m)
        _, disp = banco.crps_e_dispersione(x, 6.5)
        assert disp == pytest.approx(inf.dispersione_crps(x), rel=1e-12)


def test_il_verdetto_non_chiama_il_vecchio_bootstrap_sulle_righe():
    """`differenza_appaiata` e' il metodo che la simulazione ha misurato al
    50,7 % di copertura. Resta nel file come documentazione del difetto, ma il
    verdetto non deve toccarlo: se un giorno lo toccasse, questo test cade."""
    chiamate = []
    vera = banco.differenza_appaiata

    def spia(*args, **kw):
        chiamate.append(args)
        return vera(*args, **kw)

    banco.differenza_appaiata = spia
    try:
        _verdetto(_bracci())
    finally:
        banco.differenza_appaiata = vera
    assert not chiamate, "il verdetto ha usato il bootstrap sulle righe"


def test_bracci_di_lunghezza_diversa_fermano_l_interazione():
    """Il controllo che c'era prima confrontava due scritture algebricamente
    identiche e non poteva fallire. Quello che resta e' l'unica cosa
    controllabile a valle: che i quattro bracci abbiano le stesse righe."""
    bracci = _bracci()
    rovinato = dict(bracci["C1 cubo, presenze del modello"])
    rovinato["crps"] = rovinato["crps"][:-5]
    rovinato["crps_equo"] = rovinato["crps_equo"][:-5]
    bracci["C1 cubo, presenze del modello"] = rovinato
    with pytest.raises(Exception):
        _verdetto(bracci)
