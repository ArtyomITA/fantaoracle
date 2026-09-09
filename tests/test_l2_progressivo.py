"""Prove del progressivo: contratto temporale, finestre per data, prima origine.

## I difetti riprodotti

**La prima origine non veniva rigenerata.** Il ciclo conteneva
`G_k = G_cong if k == 0 else genera(...)`: il controllo della prima finestra
confrontava un oggetto con sé stesso e non poteva fallire. Codex l'ha
dimostrato eseguendo il nodo AST del ciclo con un generatore alterato a
restituire una costante: il generatore veniva chiamato solo per la seconda
origine, e il controllo restava verde.

Il docstring dello stesso file affermava invece che la prima origine era
rigenerata. La correzione dichiarata nella sessione precedente non era mai
stata scritta su disco: la patch era abortita su un'asserzione successiva,
prima della scrittura.

**Le finestre erano per giornata.** Nel 2024-25 cinque partite sono state
giocate oltre sette giorni dopo la mediana della loro giornata; con finestre
per giornata venivano valutate da un'origine che non poteva conoscerle.

## Che cosa provano questi test

La prova sulla prima origine perturba **solo** il percorso progressivo
iniziale: se quel percorso non chiama il generatore, la perturbazione non
arriva e il test fallisce. È la prova che il controllo può fallire.

Le prove sul contratto temporale passano per `pa.stima`, che è il consumatore
reale del filtro dentro `adatta`: alterare prove posteriori all'origine non
deve cambiare il fit, alterare prove anteriori pertinenti deve poterlo
cambiare. L'esecuzione reale di `adatta` è esercitata dalla prova integrata,
non da qui: qui si isola la proprietà, così il test costa secondi e può girare
sempre.
"""
import ast
import importlib.util
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

RADICE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RADICE / "src"))

from fantabot.tabellino import partecipazione as pa           # noqa: E402

SORGENTE = RADICE / "scripts" / "l2_progressivo.py"


def _modulo():
    spec = importlib.util.spec_from_file_location("l2_progressivo", SORGENTE)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


# --------------------------------------------------------------------------
# la prima origine viene davvero rigenerata
# --------------------------------------------------------------------------

def _sorgente_del_ciclo() -> str:
    """Il testo del ciclo sulle origini, preso dal file reale.

    Prendere il nodo dal sorgente invece di riscriverlo è quello che rende la
    prova capace di fallire: se qualcuno rimette la scorciatoia, il test la
    vede.
    """
    albero = ast.parse(SORGENTE.read_text("utf-8"))
    righe = SORGENTE.read_text("utf-8").split("\n")
    for nodo in ast.walk(albero):
        if (isinstance(nodo, ast.For) and isinstance(nodo.target, ast.Tuple)
                and any(isinstance(x, ast.Name) and x.id == "origini"
                        for x in ast.walk(nodo.iter))):
            testo = "\n".join(righe[nodo.lineno - 1:nodo.end_lineno])
            if "genera(" in testo and "p_k" in testo:
                return testo
    raise AssertionError("ciclo sulle origini non trovato nel sorgente")


def test_il_ciclo_reale_chiama_il_generatore_anche_alla_prima_origine():
    """Esegue il ciclo vero con un generatore alterato: se la prima origine
    riusa il braccio congelato, la costante non compare nella prima finestra e
    il test fallisce."""
    testo = _sorgente_del_ciclo()
    chiamate = []

    def genera_finto(modelli, cal, rose, giocatori, sims, seme):
        chiamate.append(modelli["origine"])
        return {"marchio": modelli["origine"]}

    def punteggi_finto(G, scelte, VER, GIO, sims):
        n = len(scelte)
        return {k: np.full(n, float(G["marchio"])) for k in CHIAVI}

    CHIAVI = ("crps",)
    origini = [1, 8]
    finestra_di = np.array([0, 0, 1, 1])
    p_cong = {"crps": np.zeros(4)}
    ambiente = {
        "origini": origini, "finestra_di": finestra_di,
        "modelli": {1: {"origine": 0.0}, 8: {"origine": 123.0}},
        "genera": genera_finto, "punteggi": punteggi_finto,
        "cal": None, "rose_liste": None, "giocatori": None,
        "VER": None, "GIO": None, "np": np,
        "a": type("A", (), {"sims": 1})(), "seme_r": 1,
        "CHIAVI": CHIAVI, "p_cong": p_cong,
        "p_prog": {k: np.empty(4) for k in CHIAVI},
        "scelte": np.arange(4),
    }
    exec(compile(ast.parse(_dedent(testo)), "<ciclo>", "exec"), ambiente)
    assert 1 in [o for o in chiamate] or 0.0 in chiamate, (
        "il generatore non e' stato chiamato per la prima origine: il "
        "controllo della prima finestra non puo' fallire")
    assert len(chiamate) == len(origini), (
        f"chiamate al generatore {len(chiamate)}, origini {len(origini)}: la "
        "prima origine non e' stata rigenerata")
    prima = ambiente["p_prog"]["crps"][finestra_di == 0]
    assert np.all(prima == 0.0)
    seconda = ambiente["p_prog"]["crps"][finestra_di == 1]
    assert np.all(seconda == 123.0), (
        "la perturbazione non e' arrivata: il ciclo non usa il generatore")


def _dedent(testo: str) -> str:
    righe = testo.split("\n")
    indent = min((len(r) - len(r.lstrip()) for r in righe if r.strip()),
                 default=0)
    return "\n".join(r[indent:] if len(r) >= indent else r for r in righe)


def test_il_sorgente_non_riusa_il_braccio_congelato_alla_prima_origine():
    """Guardia diretta sul testo: la scorciatoia non deve tornare."""
    testo = SORGENTE.read_text("utf-8")
    assert "G_cong if k == 0" not in testo
    assert "G_k = genera(" in testo


# --------------------------------------------------------------------------
# contratto temporale
# --------------------------------------------------------------------------

def _panel(n_gioc=30, n_giornate=10, seme=0, rinviata=None):
    """Panel minimo con date effettive. `rinviata` sposta la giornata indicata
    a una data molto posteriore, come un recupero vero."""
    rng = np.random.default_rng(seme)
    righe = []
    for g in range(1, n_giornate + 1):
        data = pd.Timestamp("2024-08-18") + pd.Timedelta(days=7 * (g - 1))
        if rinviata is not None and g == rinviata:
            data = pd.Timestamp("2024-08-18") + pd.Timedelta(days=7 * 30)
        for i in range(n_gioc):
            gioca = rng.random() < 0.6
            righe.append({
                "master_id": i, "stagione": "2024-25", "giornata": g,
                "data": data, "id_partita": f"m{g}_{i % 5}",
                "squadra_alla_data": f"S{i % 5}", "ruolo": "CDPA"[i % 4],
                "stato_convocazione": "titolare" if gioca else "panchina_non_entrato",
                "stato_voto": "con_voto" if gioca else "nessuna_riga",
                "eleggibile": True, "minuti": 90 if gioca else 0,
                "fantavoto": 6.0 + rng.normal(0, 1), "voto": 6.0,
                "confidenza_fit": "prova",
            })
    return pd.DataFrame(righe)


def test_il_filtro_sul_panel_sta_in_un_punto_solo():
    """`righe_ammesse` è l'unico posto in cui si filtra **il panel**.

    Non è l'unico punto in cui il tempo entra, e la prima versione di questo
    test lo dava per scontato controllando solo l'assenza di una stringa nel
    sorgente: la revisione ha mostrato che `adatta` passa `as_of` anche a
    `cfg.costruisci_modello_partita` e a `cfg.partite_di_addestramento`, che
    filtrano un'altra tabella con condizioni proprie. Qui si verifica quello
    che è vero — il panel passa da una funzione sola — e che gli altri due
    punti siano **dichiarati** invece che taciuti."""
    m = _modulo()
    P = _panel()
    as_of = "2024-09-15"
    r = m.righe_ammesse(P, as_of)
    assert (r["data"] < pd.Timestamp(as_of)).all()
    assert len(r) < len(P)
    testo = SORGENTE.read_text("utf-8")
    # nessun secondo filtro fatto a mano sul panel
    assert "P[P.data <" not in testo and "P.data < pd.Timestamp" not in testo
    # e gli altri due punti in cui il tempo entra devono essere dichiarati
    for atteso in ("costruisci_modello_partita", "partite_di_addestramento"):
        assert atteso in m.righe_ammesse.__doc__, (
            f"`{atteso}` usa as_of ma non e' dichiarato in righe_ammesse")


def test_una_partita_rinviata_non_e_ammessa_per_la_sua_giornata():
    """Un recupero appartiene a una giornata precedente ma si gioca dopo: al
    momento della decisione non è disponibile. Il filtro per giornata lo
    ammetteva, quello per data no."""
    m = _modulo()
    P = _panel(rinviata=3)
    as_of = "2024-09-15"
    r = m.righe_ammesse(P, as_of)
    assert 3 not in set(r.giornata), (
        "la giornata rinviata e' entrata fra le righe ammesse")
    assert 2 in set(r.giornata)


def test_le_finestre_seguono_la_data_non_la_giornata():
    """La cella di una partita rinviata deve finire nella finestra della sua
    data effettiva."""
    m = _modulo()
    DATA = np.array([
        [np.datetime64("2024-08-18")],
        [np.datetime64("2024-08-25")],
        [np.datetime64("2025-02-27")],      # rinviata di sei mesi
    ], dtype="datetime64[ns]")
    bordi = [pd.Timestamp("2024-08-18"), pd.Timestamp("2024-10-01"),
             pd.Timestamp("2100-01-01")]
    f = m.assegna_finestre(DATA, bordi)
    assert f[0, 0] == 0 and f[1, 0] == 0
    assert f[2, 0] == 1, "la partita rinviata resta nella prima finestra"


def test_una_cella_senza_data_non_finisce_in_nessuna_finestra():
    """Dato mancante e assenza sono cose diverse: una cella senza partita non
    va messa in una finestra a caso."""
    m = _modulo()
    DATA = np.array([[np.datetime64("NaT")]], dtype="datetime64[ns]")
    f = m.assegna_finestre(DATA, [pd.Timestamp("2024-08-18"),
                                  pd.Timestamp("2100-01-01")])
    assert f[0, 0] == -1


# --------------------------------------------------------------------------
# accettazione: prove posteriori non cambiano il fit, prove anteriori sì
# --------------------------------------------------------------------------

def _fit(P, as_of):
    """Il consumatore reale del filtro: le righe ammesse entrano in `pa.stima`."""
    m = _modulo()
    return pa.stima(m.righe_ammesse(P, as_of), as_of=as_of, min_partite=2)


def test_alterare_prove_posteriori_non_cambia_il_fit_di_quell_origine():
    """Criterio di accettazione: quello che accade dopo l'origine non può
    entrare nella decisione presa a quell'origine."""
    P = _panel(seme=1)
    as_of = "2024-09-15"
    base = _fit(P, as_of)
    dopo = P.copy()
    posteriori = dopo["data"] >= pd.Timestamp(as_of)
    assert posteriori.any(), "il panel di prova non ha righe posteriori"
    dopo.loc[posteriori, "stato_voto"] = "nessuna_riga"
    dopo.loc[posteriori, "fantavoto"] = 0.0
    dopo.loc[posteriori, "stato_convocazione"] = "escluso"
    alterato = _fit(dopo, as_of)
    assert alterato.prop_convocato == pytest.approx(base.prop_convocato), (
        "alterare prove posteriori all'origine ha cambiato il fit: c'e' una "
        "fuga temporale")


def test_alterare_prove_anteriori_pertinenti_cambia_il_fit():
    """Controllo opposto. Se anche questo non cambiasse nulla, il test
    precedente sarebbe soddisfatto da un fit che ignora i dati."""
    P = _panel(seme=1)
    as_of = "2024-09-15"
    base = _fit(P, as_of)
    prima = P.copy()
    anteriori = prima["data"] < pd.Timestamp(as_of)
    # `escluso` e' non convocato; `panchina_non_entrato` e' convocato, e
    # infatti con quello la propensione di convocazione non cambiava: era la
    # perturbazione a essere sbagliata, non il modello
    meta = anteriori & (prima["master_id"] % 2 == 0)
    prima.loc[meta, "stato_convocazione"] = "escluso"
    prima.loc[meta, "stato_voto"] = "nessuna_riga"
    alterato = _fit(prima, as_of)
    diversi = [k for k in base.prop_convocato
               if abs(base.prop_convocato[k]
                      - alterato.prop_convocato.get(k, 0.0)) > 1e-9]
    assert diversi, (
        "alterare prove anteriori all'origine non ha cambiato niente: il fit "
        "non sta usando i dati che dice di usare")


def test_la_diagnostica_conta_il_bordo_di_inferenza():
    """La vista del panel non è ricostruita per origine: quanto di
    anticipatorio resta va contato, non taciuto."""
    m = _modulo()
    P = _panel()
    P.loc[P.index[:20], "confidenza_fit"] = "inferenza"
    d = m.diagnostica_ammesse(m.righe_ammesse(P, "2024-09-15"), "2024-09-15")
    assert d["bordo_inferenza"] >= 1
    assert d["righe"] > 0 and "partite" in d
