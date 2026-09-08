"""Test di integrazione delle tre viste temporali del Livello 2.

Il contratto è in `reports/PROTOCOLLO_v2.md` §11. In breve:

- la **vista osservativa** usa tutte le prove note, comprese quelle successive
  alla partita, e serve ai bersagli e alla descrizione storica;
- la **vista informativa alla decisione** filtra le prove prima di risolvere i
  conflitti, e risponde a «che cosa si sapeva a quella data»;
- lo **stato futuro previsto** è la parte della seconda che cade oltre l'ultima
  prova, ed è marcato `confidenza = inferenza`, non spacciato per osservazione.

I test qui dentro sono di integrazione: usano i dati veri del progetto, perché
il difetto che devono impedire nasceva proprio nel collegamento fra i moduli e
non si vedeva su una fixture sintetica.
"""
import sys
from pathlib import Path

import pandas as pd
import pytest

RADICE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RADICE / "src"))

from fantabot.tabellino import appartenenza as app      # noqa: E402

PANEL = RADICE / "data" / "processed" / "l2_panel_2024-25.parquet"
AS_OF = "2024-08-16"          # il giorno prima della prima partita 2024-25
FINE = "2025-05-25"           # ultima partita della stagione


def _campione(n=1500):
    """Un campione di interrogazioni (giocatore, club, data) dal panel vero."""
    if not PANEL.exists():
        pytest.skip(f"manca {PANEL}")
    P = pd.read_parquet(PANEL, columns=["tm_player_id", "club_id_squadra",
                                        "data"])
    P["data"] = pd.to_datetime(P["data"])
    P = P.dropna(subset=["tm_player_id", "club_id_squadra", "data"])
    return P.head(n).reset_index(drop=True)


@pytest.fixture(scope="module")
def campione():
    return _campione()


def _verifica(tab, sub):
    return tab.verifica_molti(sub.tm_player_id.astype("Int64"),
                              sub.club_id_squadra.astype("Int64"), sub.data)


# ---------------------------------------------------------------- 1. leakage
def test_una_prova_futura_non_cambia_la_vista_alla_decisione(campione):
    """Aggiungere prove dopo il cutoff non deve toccare la vista informativa.

    Si confrontano due cutoff: quello vero e uno più tardo. Le risposte alle
    date che entrambi coprono devono restare identiche per il cutoff più
    stretto — se cambiassero, una prova posteriore starebbe entrando.
    """
    a = app.costruisci(as_of=AS_OF, estendi_fino=FINE)
    b = app.costruisci(as_of="2024-12-31", estendi_fino=FINE)
    ra, rb = _verifica(a, campione), _verifica(b, campione)
    # la vista più informata può differire; quella al cutoff non deve dipendere
    # da come la si interroga, quindi si ricostruisce e si riconfronta
    a2 = app.costruisci(as_of=AS_OF, estendi_fino=FINE, usa_cache=False)
    ra2 = _verifica(a2, campione)
    assert (ra.esito == ra2.esito).all(), (
        "la vista al cutoff non è stabile fra due costruzioni")
    # e deve differire da quella più informata, altrimenti la censura non morde
    assert (ra.esito != rb.esito).any(), (
        "le due date limite danno esiti identici: la censura non sta filtrando")


def test_una_prova_anteriore_pertinente_puo_cambiare_la_vista(campione):
    """Controllo di sensibilità: se nessun cutoff anteriore cambia niente, il
    filtro sta scartando tutto e il test precedente passerebbe a vuoto."""
    presto = app.costruisci(as_of="2024-07-15", estendi_fino=FINE)
    tardi = app.costruisci(as_of=AS_OF, estendi_fino=FINE)
    rp, rt = _verifica(presto, campione), _verifica(tardi, campione)
    assert (rp.esito != rt.esito).any(), (
        "un mese di trasferimenti in più non cambia nessun esito: sospetto")


# ------------------------------------------------------- 2. viste divergenti
def test_le_due_viste_divergono_e_la_divergenza_e_misurabile(campione):
    """La vista osservativa e quella informativa devono dare risposte diverse.

    Se coincidessero, o la censura non funziona o la vista osservativa non sta
    usando le prove che ha. Misurato sul panel intero: 7.316 righe su 25.802.
    """
    oss = app.costruisci()
    dec = app.costruisci(as_of=AS_OF, estendi_fino=FINE)
    ro, rd = _verifica(oss, campione), _verifica(dec, campione)
    diversi = int((ro.esito != rd.esito).sum())
    assert diversi > 0, "le due viste non divergono mai"
    assert diversi < len(campione), (
        "le due viste divergono su tutto: la censura ha azzerato la risposta")


def test_la_vista_alla_decisione_marca_le_risposte_come_inferenza(campione):
    """Le partite stanno dopo il cutoff: nessuna prova le copre, quindi ogni
    risposta positiva è un'inferenza di continuità e deve dirlo."""
    dec = app.costruisci(as_of=AS_OF, estendi_fino=FINE)
    r = _verifica(dec, campione)
    note = r.confidenza.notna()
    assert note.any(), "nessuna risposta porta la confidenza"
    assert (r.loc[note, "confidenza"] == app.INFERENZA).all(), (
        "una risposta su una data posteriore al cutoff è marcata come prova")


def test_la_vista_osservativa_risponde_per_prova(campione):
    """Senza censura, le stesse domande sono coperte da prove dirette."""
    oss = app.costruisci()
    r = _verifica(oss, campione)
    note = r.confidenza.notna()
    quota = float((r.loc[note, "confidenza"] == app.PROVA).mean())
    assert quota > 0.9, (
        f"solo il {quota:.1%} delle risposte osservative viene da una prova")


# ----------------------------------------------------------- 3. trasferimenti
def test_un_trasferimento_noto_cambia_lo_stato_dalla_sua_data():
    """Due cutoff a cavallo di un trasferimento vero devono dare club diversi.

    Il caso: Dzeko passa dalla Fiorentina allo Schalke il 22 gennaio 2026, ed è
    nella fonte annuale. Prima di quella data la risposta è Fiorentina; dopo,
    e per una data successiva, non è più Fiorentina.
    """
    tr = pd.read_csv(
        RADICE / "data/raw/transfermarkt/transfermarkt_transfers_annuale.csv",
        parse_dates=["transfer_date"])
    # solo giocatori che il modulo conosce: la fonte e' mondiale, e per un
    # giocatore fuori dalle nostre mappe la tabella non costruisce intervalli
    noti = app._identita_note()
    inv = tr[(tr.transfer_date >= "2026-01-01") & (tr.transfer_date <= "2026-02-01")
             & tr.from_club_name.notna() & tr.player_id.isin(noti)]
    if inv.empty:
        pytest.skip("nessun trasferimento invernale 2026 dei nostri giocatori")
    r = inv.iloc[0]
    pid, prima, dopo = int(r.player_id), int(r.from_club_id), int(r.to_club_id)
    data_dopo = r.transfer_date + pd.Timedelta(days=10)
    # gli intervalli sono semiaperti `[dal, al)`, quindi l'orizzonte
    # dell'estensione deve stare oltre la data interrogata, non sopra di essa
    orizzonte = data_dopo + pd.Timedelta(days=1)
    ante = app.costruisci(as_of=r.transfer_date, estendi_fino=orizzonte)
    post = app.costruisci(as_of=r.transfer_date + pd.Timedelta(days=1),
                          estendi_fino=orizzonte)
    e_ante, _ = ante.verifica(pid, prima, data_dopo)
    e_post, _ = post.verifica(pid, prima, data_dopo)
    assert e_ante == app.SI, (
        f"prima del trasferimento del {r.transfer_date.date()} il giocatore "
        f"{pid} doveva risultare ancora al club {prima}, invece {e_ante}")
    assert e_post != app.SI, (
        f"dopo il trasferimento risulta ancora al club di partenza: {e_post}")
    assert dopo != prima


def test_la_fonte_dei_trasferimenti_e_quella_annuale():
    """Il modulo deve leggere l'estratto annuale, non quello estivo.

    L'estratto estivo (mesi 6-9) non contiene nessun movimento di gennaio, e da
    quella mancanza si era dedotto, sbagliando, che la fonte non conoscesse
    l'inverno.
    """
    t = app.costruisci(as_of="2025-01-01", estendi_fino="2025-06-30")
    assert t.diagnostica.get("fonte_trasferimenti") == \
        "transfermarkt_transfers_annuale.csv"


# ------------------------------------------------------------------ 4. cache
def test_la_cache_distingue_cutoff_orizzonte_e_identita():
    """Chiavi diverse non devono condividere una voce di cache."""
    a = app.costruisci(as_of=AS_OF, estendi_fino=FINE)
    b = app.costruisci(as_of=AS_OF, estendi_fino="2025-01-31")
    c = app.costruisci(as_of="2024-08-01", estendi_fino=FINE)
    assert a is not b, "cutoff uguale e orizzonte diverso condividono la cache"
    assert a is not c, "orizzonte uguale e cutoff diverso condividono la cache"
    assert a is app.costruisci(as_of=AS_OF, estendi_fino=FINE), (
        "la stessa chiave non riusa la cache")


def test_un_orizzonte_anteriore_al_cutoff_e_un_errore():
    with pytest.raises(ValueError, match="anteriore ad as_of"):
        app.costruisci(as_of="2025-01-01", estendi_fino="2024-06-01")


# ------------------------------------------------- 5. ignoranza ≠ negazione
def test_una_domanda_oltre_l_orizzonte_resta_ignota_e_non_diventa_no(campione):
    """Oltre il limite dichiarato la tabella non sa: deve dire `ignoto`."""
    dec = app.costruisci(as_of=AS_OF, estendi_fino="2024-09-30")
    tardi = campione.assign(data=pd.Timestamp("2025-04-01"))
    r = _verifica(dec, tardi)
    assert (r.esito == app.IGNOTO).all(), (
        f"oltre l'orizzonte la tabella risponde {r.esito.value_counts().to_dict()}")
    assert r.confidenza.isna().all()
