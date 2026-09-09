"""Difetti A-D del secondo audit Codex, come prove permanenti.

Ognuna è stata eseguita **prima** della correzione e falliva. I quattro difetti,
in breve:

- **A** — `_confronta` leggeva l'identificativo con `.iloc[0]`: una tabella con
  righe `run_A` e una riga `run_B` passava come `run_A`, exit 0.
- **B** — `promuovi_a_corrente` accettava `verifica={'passata': True}` senza
  dire a quale esecuzione si riferisse, e non rifiutava una corsa di prova: una
  prova con un file finto dentro diventava corrente.
- **C** — `apri` faceva `exists()` e poi `mkdir(exist_ok=True)`: due processi
  potevano superare insieme il controllo. Riprodotto con due fili e una
  barriera sul controllo di esistenza; il secondo registro sovrascriveva il
  primo.
- **D** — `genera/riordina` scriveva `B[:, :len(c.giornate), j]`, cioè metteva
  le giornate del cubo nelle **prime** posizioni. Un cubo con `giornate=[20]`
  finiva in giornata 1. Il difetto è invisibile con i calendari completi e
  blocca la simulazione del solo futuro.
"""
import json
import sys
import threading
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

RADICE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RADICE / "src"))

from fantabot.tabellino import esecuzione as esec            # noqa: E402
from fantabot.tabellino import generatore as gen             # noqa: E402

CONF = {"script": "prova", "stagione": "2024-25", "sims": 30}
QUANDO = "20260909T120000"


# --------------------------------------------------------------------------
# C: acquisizione esclusiva
# --------------------------------------------------------------------------

def test_due_aperture_concorrenti_una_sola_riesce(tmp_path, monkeypatch):
    """Due fili che superano **insieme** il controllo di esistenza.

    La barriera fa sì che entrambi osservino la cartella assente prima che
    l'altro la crei: è l'interleaving che il codice precedente permetteva.
    """
    cartella = tmp_path / esec.RADICE_PUBBLICATE / "2024-25__T__x"
    barriera = threading.Barrier(2, timeout=10)
    vero_exists = Path.exists
    visto = {}

    def exists_con_barriera(self):
        r = vero_exists(self)
        if str(self) == str(cartella) and threading.get_ident() not in visto:
            visto[threading.get_ident()] = r
            try:
                barriera.wait()
            except threading.BrokenBarrierError:
                pass
        return r

    risultati = []

    def corri(sims):
        try:
            e = esec.apri(tmp_path, "2024-25", dict(CONF, sims=sims),
                          istante="T", destinazione=cartella)
            risultati.append(("aperta", sims, e.identificativo))
        except Exception as ex:
            risultati.append(("rifiutata", sims, type(ex).__name__))

    monkeypatch.setattr(Path, "exists", exists_con_barriera)
    fili = [threading.Thread(target=corri, args=(s,)) for s in (30, 60)]
    for f in fili:
        f.start()
    for f in fili:
        f.join()
    monkeypatch.undo()

    assert set(visto.values()) == {False}, (
        "i due fili non hanno osservato insieme la cartella assente: "
        "l'interleaving non e' stato riprodotto e il test non prova niente")
    aperte = [r for r in risultati if r[0] == "aperta"]
    assert len(aperte) == 1, f"due corse hanno aperto la stessa cartella: {risultati}"
    rifiutate = [r for r in risultati if r[0] == "rifiutata"]
    assert rifiutate and rifiutate[0][2] == "DestinazioneOccupata"
    # e il registro deve essere quello di chi ha vinto, non un miscuglio
    reg = json.loads((cartella / "esecuzione.json").read_text("utf-8"))
    assert reg["configurazione"]["sims"] == aperte[0][1]


def test_la_ripresa_concorrente_e_esclusiva(tmp_path):
    """Anche riprendere è esclusivo: due processi che riprendono la stessa
    cartella si sovrascriverebbero il registro."""
    a = esec.apri(tmp_path, "2024-25", CONF, istante=QUANDO)
    a.scrivi_testo("x.txt", "x")
    a.registra()
    b = esec.apri(tmp_path, "2024-25", CONF, istante=QUANDO, riprendi=True)
    assert (b.cartella / esec.NOME_LUCCHETTO).exists()
    with pytest.raises(esec.DestinazioneOccupata, match="lucchetto"):
        esec.apri(tmp_path, "2024-25", CONF, istante=QUANDO, riprendi=True)
    assert esec.rilascia(b.cartella)
    # rilasciato il lucchetto, una ripresa torna possibile
    c = esec.apri(tmp_path, "2024-25", CONF, istante=QUANDO, riprendi=True)
    assert c.ripresa


def test_riprendere_una_destinazione_che_non_esiste_e_un_errore(tmp_path):
    with pytest.raises(esec.RipresaIncompatibile, match="non esiste"):
        esec.apri(tmp_path, "2024-25", CONF, istante=QUANDO, riprendi=True)


# --------------------------------------------------------------------------
# B: promozione
# --------------------------------------------------------------------------

def _corsa(tmp_path, prova=False):
    e = esec.apri(tmp_path, "2024-25", CONF, istante=QUANDO, prova=prova)
    e.scrivi_tabella("t.csv", pd.DataFrame({"x": [1, 2]}))
    e.registra()
    return e


def test_una_prova_non_diventa_corrente(tmp_path):
    """Il difetto B: una corsa di prova con un file finto dentro diventava
    corrente."""
    p = _corsa(tmp_path, prova=True)
    with pytest.raises(RuntimeError, match="prova"):
        esec.promuovi_a_corrente(tmp_path, "2024-25", p,
                                 verifica={"passata": True,
                                           "esecuzione": p.identificativo})
    assert esec.leggi_corrente(tmp_path, "2024-25") is None


def test_una_verifica_senza_associazione_non_promuove(tmp_path):
    """`{'passata': True}` non dice a quale esecuzione si riferisca."""
    e = _corsa(tmp_path)
    with pytest.raises(RuntimeError, match="obbligatorio"):
        esec.promuovi_a_corrente(tmp_path, "2024-25", e,
                                 verifica={"passata": True})


def test_un_artefatto_modificato_dopo_la_verifica_non_promuove(tmp_path):
    """Una verifica vale per i byte che ha verificato."""
    e = _corsa(tmp_path)
    (e.cartella / "t.csv").write_text("x\n99\n", encoding="utf-8")
    with pytest.raises(RuntimeError, match="modificati"):
        esec.promuovi_a_corrente(tmp_path, "2024-25", e,
                                 verifica={"passata": True,
                                           "esecuzione": e.identificativo})


def test_un_artefatto_mancante_non_promuove(tmp_path):
    e = _corsa(tmp_path)
    (e.cartella / "t.csv").unlink()
    with pytest.raises(RuntimeError, match="mancanti"):
        esec.promuovi_a_corrente(tmp_path, "2024-25", e,
                                 verifica={"passata": True,
                                           "esecuzione": e.identificativo})


def test_una_corsa_verificata_e_integra_diventa_corrente(tmp_path):
    """Guardia: se anche il caso buono fosse rifiutato, i test sopra non
    proverebbero niente."""
    e = _corsa(tmp_path)
    esec.promuovi_a_corrente(tmp_path, "2024-25", e,
                             verifica={"passata": True,
                                       "esecuzione": e.identificativo,
                                       "scarto": 0.0})
    assert esec.leggi_corrente(tmp_path, "2024-25") == e.cartella


def test_il_registro_porta_le_impronte_delle_uscite(tmp_path):
    """Senza impronte non si può dire se un artefatto sia stato toccato dopo."""
    e = _corsa(tmp_path)
    reg = json.loads((e.cartella / "esecuzione.json").read_text("utf-8"))
    assert reg["impronte_uscite"]["t.csv"] == esec.impronta_file(
        e.cartella / "t.csv")
    assert esec.NOME_LUCCHETTO not in reg["file"]


# --------------------------------------------------------------------------
# D: riordino per identità
# --------------------------------------------------------------------------

class CuboFinto:
    def __init__(self, giornate, giocatori, valore=7.0):
        self.giornate = list(giornate)
        self.giocatori = list(giocatori)
        n, g = len(self.giocatori), len(self.giornate)
        # ogni cella porta il numero della sua giornata: così un riordino
        # sbagliato si vede subito, invece di dare un valore costante
        self.fantavoto = np.array(
            [[[float(gg) for _ in range(n)] for gg in self.giornate]
             for _ in range(2)], dtype=np.float32)
        self.gioca = np.ones((2, g, n), dtype=bool)
        self.diagnostica = {"n_problemi_coerenza": 0}


@pytest.mark.parametrize("giornate", [
    list(range(1, 39)),          # calendario completo
    [20],                        # parte dalla giornata 20
    list(range(20, 39)),         # solo il futuro
    [3, 7, 11, 25],              # non consecutive
    [11, 3, 25, 7],              # ordine permutato
])
def test_ogni_giornata_finisce_nella_sua_posizione(giornate):
    """Il difetto D: le giornate finivano nelle prime posizioni."""
    giocatori = [10, 20, 30]
    c = CuboFinto(giornate, giocatori)
    ad = gen.riordina_cubo(c, giocatori, range(1, 39), sims=2)
    B = ad["riordina"](c.fantavoto)
    for g in giornate:
        assert B[0, g - 1, 0] == pytest.approx(float(g)), (
            f"la giornata {g} non e' finita in posizione {g}")
    vuote = [g for g in range(1, 39) if g not in giornate]
    for g in vuote:
        assert B[0, g - 1, 0] == 0.0, (
            f"la posizione {g} doveva restare vuota")


def test_i_giocatori_seguono_l_identita_non_la_posizione():
    """Stessa cosa sull'altra dimensione: l'universo può avere un ordine
    diverso da quello del cubo."""
    c = CuboFinto([5], [30, 10, 20])
    c.fantavoto[:, 0, :] = np.array([3.0, 1.0, 2.0], dtype=np.float32)
    universo = [10, 20, 30]
    B = gen.riordina_cubo(c, universo, range(1, 39), sims=2)["riordina"](
        c.fantavoto)
    assert B[0, 4, 0] == pytest.approx(1.0)     # master 10
    assert B[0, 4, 1] == pytest.approx(2.0)     # master 20
    assert B[0, 4, 2] == pytest.approx(3.0)     # master 30


def test_un_giocatore_fuori_universo_non_entra():
    c = CuboFinto([5], [10, 99])
    B = gen.riordina_cubo(c, [10], range(1, 39), sims=2)["riordina"](c.fantavoto)
    assert B.shape[2] == 1


def test_una_giornata_fuori_calendario_ferma_il_riordino():
    """Inventare una posizione sarebbe peggio che fermarsi."""
    c = CuboFinto([99], [10])
    with pytest.raises(ValueError, match="giornate che il bersaglio non ha"):
        gen.riordina_cubo(c, [10], range(1, 39), sims=2)
