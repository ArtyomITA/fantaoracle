"""Destinazioni di esecuzione: rifiuto, isolamento, scrittura atomica.

Il difetto che questi test chiudono: banco e progressivo scrivevano su nomi
fissi dentro `data/l2/`. Una prova esplorativa a quattro scenari ha
sovrascritto un verdetto pubblicato — è successo davvero, il 9 settembre 2026 —
e due esecuzioni consecutive non erano distinguibili a posteriori.
"""
import json
import sys
from pathlib import Path

import pandas as pd
import pytest

RADICE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RADICE / "src"))

from fantabot.tabellino import esecuzione as esec            # noqa: E402

CONF = {"script": "prova", "stagione": "2024-25", "sims": 30}
QUANDO = "20260909T120000"


def test_una_destinazione_occupata_e_rifiutata(tmp_path):
    """Il caso che ha causato la sovrascrittura: due esecuzioni sulla stessa
    cartella. La seconda deve fermarsi, non sovrascrivere."""
    a = esec.apri(tmp_path, "2024-25", CONF, istante=QUANDO)
    a.scrivi_testo("uscita.txt", "primo")
    a.registra()
    with pytest.raises(esec.DestinazioneOccupata):
        esec.apri(tmp_path, "2024-25", CONF, istante=QUANDO)
    assert (a.cartella / "uscita.txt").read_text("utf-8") == "primo"


def test_una_ripresa_dichiarata_con_la_stessa_configurazione_e_ammessa(tmp_path):
    a = esec.apri(tmp_path, "2024-25", CONF, istante=QUANDO)
    a.scrivi_testo("uscita.txt", "primo")
    a.registra()
    b = esec.apri(tmp_path, "2024-25", CONF, istante=QUANDO, riprendi=True)
    assert b.ripresa and b.cartella == a.cartella


def test_una_ripresa_con_configurazione_diversa_e_rifiutata(tmp_path):
    """Riprendere significa continuare la stessa cosa. Con un'altra
    configurazione non è una ripresa: è un'esecuzione diversa che pretende il
    posto di quella vecchia."""
    a = esec.apri(tmp_path, "2024-25", CONF, istante=QUANDO)
    a.scrivi_testo("uscita.txt", "primo")
    a.registra()
    altra = dict(CONF, sims=60)
    with pytest.raises(esec.RipresaIncompatibile):
        esec.apri(tmp_path, "2024-25", altra, istante=QUANDO,
                  destinazione=a.cartella, riprendi=True)


def test_una_ripresa_su_cartella_senza_registro_e_rifiutata(tmp_path):
    """Senza `esecuzione.json` non si può verificare che la ripresa riguardi la
    stessa configurazione: fermarsi è l'unica risposta onesta."""
    d = tmp_path / "sporca"
    d.mkdir()
    (d / "avanzo.txt").write_text("roba", encoding="utf-8")
    with pytest.raises(esec.RipresaIncompatibile):
        esec.apri(tmp_path, "2024-25", CONF, istante=QUANDO,
                  destinazione=d, riprendi=True)


def test_le_prove_hanno_una_radice_diversa_dai_risultati(tmp_path):
    """Una prova non deve poter finire dove stanno i risultati pubblicabili,
    nemmeno con la stessa configurazione e lo stesso istante."""
    pubblicata = esec.apri(tmp_path, "2024-25", CONF, istante=QUANDO)
    prova = esec.apri(tmp_path, "2024-25", CONF, istante=QUANDO, prova=True)
    assert prova.cartella != pubblicata.cartella
    assert esec.RADICE_PROVE in prova.cartella.parts
    assert esec.RADICE_PUBBLICATE in pubblicata.cartella.parts


def test_l_identificativo_dipende_dalla_configurazione(tmp_path):
    """Stessa configurazione, stesso identificativo: è quello che rende
    riconoscibile una ripresa. Configurazione diversa, identificativo diverso."""
    assert esec.identificativo(CONF) == esec.identificativo(dict(CONF))
    assert esec.identificativo(CONF) != esec.identificativo(dict(CONF, sims=60))


def test_la_scrittura_e_atomica_e_non_lascia_file_a_meta(tmp_path):
    """Se la scrittura fallisce a metà, non deve restare un artefatto parziale
    che sembra completo, né sparire quello precedente."""
    a = esec.apri(tmp_path, "2024-25", CONF, istante=QUANDO)
    a.scrivi_testo("uscita.txt", "buono")

    def rompi(p):
        p.write_text("mezzo", encoding="utf-8")
        raise RuntimeError("disco pieno")

    with pytest.raises(RuntimeError):
        a._atomico("uscita.txt", rompi)
    assert (a.cartella / "uscita.txt").read_text("utf-8") == "buono"
    parziali = [p.name for p in a.cartella.iterdir() if ".parziale" in p.name]
    assert not parziali, f"residui di scrittura interrotta: {parziali}"


def test_il_registro_elenca_i_file_prodotti(tmp_path):
    a = esec.apri(tmp_path, "2024-25", CONF, istante=QUANDO)
    a.scrivi_tabella("t.csv", pd.DataFrame({"x": [1, 2]}))
    a.scrivi_json("d.json", {"a": 1})
    a.registra()
    reg = json.loads((a.cartella / "esecuzione.json").read_text("utf-8"))
    assert set(reg["file"]) == {"t.csv", "d.json"}
    # la configurazione registrata porta anche la modalita': senza, una prova
    # e un risultato pubblicabile avevano lo stesso identificativo
    assert {k: v for k, v in reg["configurazione"].items()
            if k != "modalita"} == CONF
    assert reg["configurazione"]["modalita"] == "pubblicata"
    assert reg["identificativo"] == a.identificativo


def test_il_puntatore_corrente_non_si_aggiorna_senza_verifica(tmp_path):
    """«Corrente» deve indicare un'esecuzione verificata. Finché la verifica
    non passa, corrente resta quella di prima."""
    a = esec.apri(tmp_path, "2024-25", CONF, istante=QUANDO)
    a.scrivi_testo("uscita.txt", "x")
    a.registra()
    with pytest.raises(RuntimeError, match="verifica"):
        esec.promuovi_a_corrente(tmp_path, "2024-25", a,
                                 verifica={"passata": False})
    assert esec.leggi_corrente(tmp_path, "2024-25") is None
    # dal secondo audit l'associazione all'esecuzione e' OBBLIGATORIA: prima
    # `{"passata": True}` da solo bastava, e una corsa di prova con un file
    # finto dentro diventava corrente
    esec.promuovi_a_corrente(tmp_path, "2024-25", a,
                             verifica={"passata": True, "scarto": 0.0,
                                       "esecuzione": a.identificativo})
    assert esec.leggi_corrente(tmp_path, "2024-25") == a.cartella


def test_senza_puntatore_corrente_non_si_inventa_una_cartella(tmp_path):
    assert esec.leggi_corrente(tmp_path, "2024-25") is None


def test_impronta_file_distingue_i_byte(tmp_path):
    p = tmp_path / "x.txt"
    p.write_text("uno", encoding="utf-8")
    h1 = esec.impronta_file(p)
    p.write_text("due", encoding="utf-8")
    assert esec.impronta_file(p) != h1
    assert esec.impronta_file(tmp_path / "assente.txt") is None


# --------------------------------------------------------------------------
# rilievi della revisione indipendente
# --------------------------------------------------------------------------

def test_una_destinazione_aperta_ma_ancora_vuota_e_gia_occupata(tmp_path):
    """Il rifiuto guardava il CONTENUTO: fra `mkdir` e la prima scrittura la
    cartella era vuota, quindi due corse aperte insieme passavano entrambe e la
    seconda sovrascriveva la prima. Adesso `apri` scrive subito il registro."""
    a = esec.apri(tmp_path, "2024-25", CONF, istante=QUANDO)
    assert (a.cartella / "esecuzione.json").exists(), (
        "la destinazione non e' marcata come occupata all'apertura")
    with pytest.raises(esec.DestinazioneOccupata):
        esec.apri(tmp_path, "2024-25", CONF, istante=QUANDO)


def test_prova_e_pubblicata_non_condividono_l_identificativo(tmp_path):
    """Quel campo finisce dentro gli artefatti come unica traccia di
    provenienza: se non distingue una prova da un risultato, non serve."""
    pubblicata = esec.apri(tmp_path, "2024-25", CONF, istante=QUANDO)
    prova = esec.apri(tmp_path, "2024-25", CONF, istante=QUANDO, prova=True)
    assert prova.identificativo != pubblicata.identificativo


def test_una_prova_non_puo_scrivere_sotto_la_radice_dei_risultati(tmp_path):
    """`--destinazione` scavalcava la separazione delle radici."""
    dove = tmp_path / esec.RADICE_PUBBLICATE / "2024-25__x__y"
    with pytest.raises(esec.DestinazioneOccupata, match="radice sbagliata"):
        esec.apri(tmp_path, "2024-25", CONF, istante=QUANDO, prova=True,
                  destinazione=dove)


def test_la_ripresa_conserva_l_elenco_dei_file_gia_prodotti(tmp_path):
    """Dopo una ripresa il registro non descriveva piu' la cartella: ripartiva
    con l'elenco vuoto."""
    a = esec.apri(tmp_path, "2024-25", CONF, istante=QUANDO)
    a.scrivi_tabella("t.csv", pd.DataFrame({"x": [1]}))
    a.registra()
    b = esec.apri(tmp_path, "2024-25", CONF, istante=QUANDO, riprendi=True)
    b.scrivi_json("d.json", {"a": 1})
    b.registra()
    reg = json.loads((b.cartella / "esecuzione.json").read_text("utf-8"))
    assert set(reg["file"]) == {"t.csv", "d.json"}


def test_una_ripresa_ripulisce_i_residui_di_una_morte_secca(tmp_path):
    """`os.replace` protegge il file finale, ma un processo ucciso non esegue
    il `finally` e lascia un `.parziale`. Il nome lo dichiara, ma accumularli
    sporca la cartella."""
    a = esec.apri(tmp_path, "2024-25", CONF, istante=QUANDO)
    a.scrivi_testo("x.txt", "buono")
    a.registra()
    (a.cartella / ".x.txt.abc123.parziale").write_text("meta", encoding="utf-8")
    b = esec.apri(tmp_path, "2024-25", CONF, istante=QUANDO, riprendi=True)
    assert not list(b.cartella.glob(".*.parziale"))
    assert (b.cartella / "x.txt").read_text("utf-8") == "buono"


def test_il_puntatore_non_si_promuove_con_la_verifica_di_un_altra_corsa(tmp_path):
    """La guardia controllava solo `passata: True`, quindi accettava un esito
    riferito a un'altra esecuzione."""
    a = esec.apri(tmp_path, "2024-25", CONF, istante=QUANDO)
    a.scrivi_testo("x.txt", "x")
    a.registra()
    with pytest.raises(RuntimeError, match="non "):
        esec.promuovi_a_corrente(
            tmp_path, "2024-25", a,
            verifica={"passata": True, "esecuzione": "altraesecuz"})
    esec.promuovi_a_corrente(
        tmp_path, "2024-25", a,
        verifica={"passata": True, "esecuzione": a.identificativo})
    assert esec.leggi_corrente(tmp_path, "2024-25") == a.cartella


def test_non_si_promuove_una_cartella_senza_artefatti(tmp_path):
    """Il puntatore non deve poter indicare una corsa che non ha prodotto
    niente oltre al proprio registro."""
    a = esec.apri(tmp_path, "2024-25", CONF, istante=QUANDO)
    with pytest.raises(RuntimeError, match="nessun artefatto"):
        esec.promuovi_a_corrente(tmp_path, "2024-25", a,
                                 verifica={"passata": True,
                                           "esecuzione": a.identificativo})
