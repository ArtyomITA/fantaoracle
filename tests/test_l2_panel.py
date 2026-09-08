"""Verifiche del panel e del contratto temporale del Livello 2.

Ogni test qui dentro nasce da un difetto misurato negli audit del 7 settembre
2026 (`data/l3/audit/dati/RAPPORTO.md`) e controlla una regola del contratto
degli stati (`reports/CRITERI_L2_L3.md`, sezione 7). Nessuno di questi test
passa sul comportamento precedente: le colonne che interrogano non esistevano, e
gli stati che pretendono erano diversi.

Si eseguono con:

    PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python -m pytest tests/test_l2_panel.py -q

I test leggono i file gia' prodotti in `data/processed/`. Se un file manca, il
test viene saltato con un messaggio esplicito invece di fallire per un motivo
diverso da quello che vuole misurare.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
PROC = ROOT / "data" / "processed"
sys.path.insert(0, str(ROOT / "src"))

from fantabot.tabellino import appartenenza as app       # noqa: E402

# stagioni con formazioni ufficiali disponibili: sono quelle su cui gli stati
# di convocazione hanno un significato
STAGIONI_CON_FORMAZIONI = ["2021-22", "2023-24", "2024-25", "2025-26"]
STAGIONE_CORRENTE = "2026-27"

STATI_AMMESSI = {"titolare", "panchina_entrato", "panchina_non_entrato",
                 "escluso", "ignoto"}
STATI_PARTITA_AMMESSI = {"conclusa", "da_giocare", "rinviata", "senza_voti"}
# la partita e' nel passato solo se il risultato c'e'; `senza_voti` ha il
# risultato (mancano i voti, che sono un'altra cosa e un altro stato)
STATI_CON_RISULTATO = {"conclusa", "rinviata", "senza_voti"}


def panel(stagione: str) -> pd.DataFrame:
    f = PROC / f"l2_panel_{stagione}.parquet"
    if not f.exists():
        pytest.skip(f"panel {stagione} assente: eseguire "
                    f"scripts/l2_costruisci_panel.py")
    return pd.read_parquet(f)


def partite() -> pd.DataFrame:
    f = PROC / "l2_partite.parquet"
    if not f.exists():
        pytest.skip("l2_partite.parquet assente: eseguire "
                    "scripts/l2_prepara_partite.py")
    return pd.read_parquet(f)


# --------------------------------------------------------------------------
# 1. un titolare non puo' avere `eleggibile` falso
# --------------------------------------------------------------------------

@pytest.mark.parametrize("stagione", STAGIONI_CON_FORMAZIONI)
def test_titolare_non_puo_essere_non_eleggibile(stagione):
    """Chi e' schierato dall'inizio era tesserato per quel club quel giorno.

    Prima della correzione la colonna `eleggibile` non esisteva affatto e la sua
    antenata `in_rosa_nel_periodo` era `False` su tutte le 124.184 righe dei
    cinque panel: tutti gli 8.324 titolari del 2024/25 risultavano fuori rosa.
    """
    P = panel(stagione)
    assert "eleggibile" in P.columns, "manca la colonna `eleggibile`"
    tit = P[P.stato_convocazione == "titolare"]
    assert len(tit) > 0, "nessun titolare: il panel non e' stato costruito"
    assert int((tit.eleggibile == False).sum()) == 0        # noqa: E712
    # e non puo' nemmeno restare senza risposta: e' a referto, la prova c'e'
    assert int(tit.eleggibile.isna().sum()) == 0


@pytest.mark.parametrize("stagione", STAGIONI_CON_FORMAZIONI + [STAGIONE_CORRENTE])
def test_stati_ammessi(stagione):
    """Gli stati sono esattamente i cinque del contratto. `non_in_rosa` non
    esiste piu': non era uno stato del giocatore, era un'affermazione non
    provata (sbagliata nel 57% di un campione di 30 righe)."""
    P = panel(stagione)
    visti = set(P.stato_convocazione.unique())
    assert visti <= STATI_AMMESSI, f"stati non previsti: {visti - STATI_AMMESSI}"
    assert "non_in_rosa" not in visti
    assert "fuori_lista" not in visti
    assert "in_rosa_nel_periodo" not in P.columns


# --------------------------------------------------------------------------
# 2. ignoto e' distinto da assenza dimostrata
# --------------------------------------------------------------------------

@pytest.mark.parametrize("stagione", STAGIONI_CON_FORMAZIONI)
def test_ignoto_distinto_da_assenza_dimostrata(stagione):
    """Tre risposte diverse devono restare tre.

    `eleggibile = False` significa «era di un altro club, e lo so»;
    `eleggibile` nullo significa «non lo so». Prima erano la stessa cosa e si
    chiamavano entrambe `non_in_rosa`.
    """
    P = panel(stagione)
    for col in ["appartenenza_esito", "fonte_appartenenza", "club_id_alla_data",
                "eleggibile"]:
        assert col in P.columns, f"manca la colonna `{col}`"

    dimostrata = P.eleggibile == False                       # noqa: E712
    ignota = P.eleggibile.isna()
    assert dimostrata.sum() > 0, "nessuna assenza dimostrata: sospetto"
    assert ignota.sum() > 0, "nessuna ignoranza dichiarata: ancora piu' sospetto"

    # coerenza fra le due colonne: un'assenza dimostrata ha una fonte e un club
    assert (P.loc[dimostrata, "appartenenza_esito"] == app.NO).all()
    assert P.loc[dimostrata, "fonte_appartenenza"].ne(app.FONTE_IGNOTA).all()
    # e un'ignoranza non ha ne' fonte ne' club, altrimenti non sarebbe ignoranza
    solo_ignote = P[P.appartenenza_esito == app.IGNOTO]
    assert solo_ignote.club_id_alla_data.isna().all()
    assert (solo_ignote.fonte_appartenenza == app.FONTE_IGNOTA).all()

    # `escluso` e' un'esclusione documentata: esiste solo dove l'eleggibilita'
    # e' dimostrata. Un'ignoranza non puo' diventare un'esclusione.
    esc = P[P.stato_convocazione == "escluso"]
    assert len(esc) > 0
    assert (esc.eleggibile == True).all()                     # noqa: E712
    assert esc.formazioni_note.all()


def test_stagione_senza_formazioni_resta_ignota_ma_informata():
    """Il 2026-27 non ha formazioni: lo stato deve restare `ignoto`, ma per il
    motivo giusto e con le altre colonne piene.

    Prima `partite()` dava `game_id` nullo su tutte e 380 le righe, `id_partite`
    restava vuoto e lo script prendeva un ramo che non creava nemmeno le
    colonne: 22.306 righe `ignoto` e nient'altro. Ora la chiave di partita
    ricade su `id_understat` e il resto del panel si costruisce lo stesso.
    """
    P = panel(STAGIONE_CORRENTE)
    assert (P.stato_convocazione == "ignoto").all()
    # ma la partita e' agganciata e il club alla data e' noto per la maggioranza
    assert P.id_partita.notna().all()
    assert P.club_id_squadra.notna().all()
    assert P.club_id_alla_data.notna().mean() > 0.8
    # nessuna riga puo' essere eleggibile: mancano le formazioni
    assert int((P.eleggibile == True).sum()) == 0             # noqa: E712
    # e almeno qualcuna e' dimostrata NON eleggibile (arrivata dopo)
    assert int((P.eleggibile == False).sum()) > 0             # noqa: E712


# --------------------------------------------------------------------------
# 3. un trasferito non e' eleggibile per il vecchio club dopo il trasferimento
# --------------------------------------------------------------------------

def test_appartenenza_silvestri_udinese_empoli():
    """Silvestri (`tm_player_id` 85528) lascia l'Udinese (club 410) e nel
    febbraio 2025 gioca per l'Empoli (club 749).

    Il criterio vecchio ragionava per meta' di stagione e non poteva vederlo.
    """
    t = app.costruisci()
    assert t.verifica(85528, 410, "2025-02-16")[0] == app.NO
    assert t.verifica(85528, 749, "2025-02-16")[0] == app.SI


def test_appartenenza_hermoso_roma_leverkusen():
    """Hermoso (`tm_player_id` 281769) e' della Roma (club 12) nel novembre
    2024 e del Leverkusen (club 15) nel marzo 2025.

    L'audit lo cita come il caso che la meta' di stagione sbaglia per forza:
    con `giornata > 19` risultava «in rosa alla Roma» anche alla giornata 28 del
    9 marzo 2025, quando giocava in Germania.
    """
    t = app.costruisci()
    assert t.verifica(281769, 12, "2024-11-10")[0] == app.SI
    assert t.verifica(281769, 12, "2025-03-09")[0] == app.NO
    assert t.verifica(281769, 15, "2025-03-09")[0] == app.SI


def test_panel_non_accumula_assenze_nel_vecchio_club():
    """Nel panel, le partite dell'Udinese successive al passaggio di Silvestri
    non possono contarlo fra gli eleggibili, e quindi non possono contare
    un'assenza a suo carico."""
    P = panel("2024-25")
    dopo = P[(P.master_id == 2211)
             & (P.squadra_alla_data == "Udinese")
             & (P.data >= pd.Timestamp("2025-02-02"))]
    assert len(dopo) > 0, "campione vuoto: cambiata la costruzione del panel"
    assert (dopo.eleggibile == False).all()                   # noqa: E712
    assert (dopo.stato_convocazione == "ignoto").all()
    # e in particolare nessuna di quelle righe e' un'esclusione documentata
    assert (dopo.stato_convocazione != "escluso").all()


def test_appartenenza_risponde_ignoto_e_non_falso():
    """Dove le fonti non arrivano la risposta e' `ignoto`, mai `no`.

    E' la differenza che l'etichetta `non_in_rosa` cancellava.
    """
    t = app.costruisci()
    # identificativo inesistente: nessuna fonte puo' dire nulla
    esito, fonte = t.verifica(999_999_999, 410, "2025-02-16")
    assert esito == app.IGNOTO
    assert fonte == app.FONTE_IGNOTA


# --------------------------------------------------------------------------
# 4. una partita conclusa senza voti non e' ne' persa ne' contata due volte
# --------------------------------------------------------------------------

def test_partite_senza_voti_esistono_e_sono_dichiarate():
    """Le 8 partite di giornata 3 del 2026-27 (4-6 settembre) hanno il
    risultato ma non i voti. Devono avere uno stato che lo dica."""
    d = partite()
    assert "stato_partita" in d.columns
    assert set(d.stato_partita.unique()) <= STATI_PARTITA_AMMESSI
    sv = d[(d.stagione == "2026-27") & (d.stato_partita == "senza_voti")]
    assert len(sv) == 8
    assert (sv.giornata == 3).all()
    # hanno il risultato: non sono «da giocare»
    assert sv.gol_casa.notna().all() and sv.gol_trasferta.notna().all()


def test_partita_senza_voti_non_persa_ne_doppia():
    """Ogni partita compare una volta sola in ogni partizione, e il totale
    della stagione resta 380 qualunque sia lo stato."""
    d = partite()
    for st, g in d.groupby("stagione"):
        assert len(g) == 380, f"{st}: {len(g)} partite invece di 380"
        assert g.stato_partita.notna().all()
        conteggi = g.stato_partita.value_counts()
        assert int(conteggi.sum()) == 380
        # identita' univoca: nessuna partita duplicata
        chiave = g["game_id"].fillna(-1).astype("int64").astype(str) + "|" \
            + g["id_understat"].fillna(-1).astype("int64").astype(str)
        assert chiave.is_unique, f"{st}: partite duplicate"


# --------------------------------------------------------------------------
# 5. una giornata parziale resta coerente
# --------------------------------------------------------------------------

def test_giornata_parziale_coerente():
    """La giornata 3 del 2026-27 e' spezzata: 8 partite giocate fra il 4 e il 6
    settembre, 2 in programma il 7. Le due meta' devono sommare a 10 e nessuna
    delle due deve essere vuota."""
    d = partite()
    g = d[(d.stagione == "2026-27") & (d.giornata == 3)]
    assert len(g) == 10
    con_risultato = g.stato_partita.isin(STATI_CON_RISULTATO)
    assert int(con_risultato.sum()) == 8
    assert int((~con_risultato).sum()) == 2
    da_giocare = g[~con_risultato]
    assert set(zip(da_giocare.casa, da_giocare.trasferta)) == {
        ("Cagliari", "Lecce"), ("Udinese", "Lazio")}
    assert (da_giocare.stato_partita == "da_giocare").all()


def test_rinvii_dichiarati_e_non_dedotti_dalla_giornata():
    """Nello storico 41 partite su 3.040 distano piu' di tre giorni dalla
    mediana della loro giornata. Devono essere marcate, perche' la giornata non
    e' una partizione temporale e nessun criterio puo' basarsi su di essa."""
    d = partite()
    assert "rinviata" in d.columns and "scarto_giorni_giornata" in d.columns
    storico = d[d.stagione < "2026-27"]
    assert int(storico.rinviata.sum()) == 41
    assert int(storico.scarto_giorni_giornata.max()) == 185


# --------------------------------------------------------------------------
# 6. passato + futuro = totale, per piu' date di decisione
# --------------------------------------------------------------------------

def separa(d: pd.DataFrame, as_of: str) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Taglio temporale del contratto (§7.2).

    Passato: il risultato c'e' **e** il calcio d'inizio e' anteriore alla
    decisione. Futuro: tutto il resto, comprese le partite gia' iniziate di cui
    non abbiamo l'esito, che restano da simulare e vanno dichiarate «richiede
    aggiornamento prima dell'uso».
    """
    limite = pd.Timestamp(as_of)
    con_risultato = d.stato_partita.isin(STATI_CON_RISULTATO)
    passato = d[con_risultato & (d.data_evento < limite)]
    futuro = d[~(con_risultato & (d.data_evento < limite))]
    return passato, futuro


@pytest.mark.parametrize("as_of", ["2026-09-11", "2026-09-07", "2026-12-01",
                                   "2027-06-01", "2026-08-01"])
def test_somma_passato_futuro_fa_il_totale(as_of):
    """Nessuna partita puo' sparire fra passato e futuro, a nessuna data.

    E' il difetto misurato nell'audit: con `as_of = 2026-09-11` il generatore
    metteva nel passato le 30 partite con data anteriore ma ne possedeva 28, e
    con `--solo-future` escludeva dal futuro le due del 7 settembre. Quelle due
    non stavano in nessuna delle due meta'.
    """
    d = partite()
    g = d[d.stagione == "2026-27"]
    passato, futuro = separa(g, as_of)
    assert len(passato) + len(futuro) == len(g) == 380
    assert set(passato.index) & set(futuro.index) == set()


def test_le_due_partite_del_7_settembre_restano_nel_futuro():
    """Il caso esatto dell'audit: Cagliari-Lecce e Udinese-Lazio, calcio
    d'inizio il 7 settembre 2026, nessun risultato. Con `as_of = 2026-09-11`
    devono stare nel futuro, non sparire."""
    d = partite()
    g = d[d.stagione == "2026-27"]
    passato, futuro = separa(g, "2026-09-11")
    coppie = set(zip(futuro.casa, futuro.trasferta))
    assert ("Cagliari", "Lecce") in coppie
    assert ("Udinese", "Lazio") in coppie
    assert ("Cagliari", "Lecce") not in set(zip(passato.casa, passato.trasferta))
    # e le 8 senza voti sono nel passato: il risultato c'e'
    assert len(passato) == 28


@pytest.mark.parametrize("stagione", STAGIONI_CON_FORMAZIONI)
def test_somma_passato_futuro_stagioni_storiche(stagione):
    """Anche dove tutto e' concluso la partizione deve reggere, comprese le
    partite rinviate che cadono mesi dopo la loro giornata."""
    d = partite()
    g = d[d.stagione == stagione]
    meta = g.data_evento.median()
    for as_of in [g.data_evento.min(), meta, g.data_evento.max()]:
        passato, futuro = separa(g, str(as_of))
        assert len(passato) + len(futuro) == 380
