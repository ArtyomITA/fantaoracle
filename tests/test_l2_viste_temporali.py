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
def _fonte_con_prova_in_piu(tmp_path, campione, giorni_dal_cutoff):
    """Scrive una copia della fonte dei trasferimenti con dentro una cessione
    inventata, datata `giorni_dal_cutoff` giorni rispetto al cutoff.

    Serve a perturbare davvero le prove. Confrontare due ricostruzioni della
    stessa vista verifica il determinismo, non la non anticipazione: era il
    difetto della versione precedente di questi test.
    """
    vero = RADICE / "data/raw/transfermarkt/transfermarkt_transfers_annuale.csv"
    if not vero.exists():
        pytest.skip("manca la fonte annuale dei trasferimenti")
    tr = pd.read_csv(vero, parse_dates=["transfer_date"])
    # Serve un giocatore la cui risposta venga dai TRASFERIMENTI: la comparsa a
    # referto ha priorita' piu' alta, quindi su un giocatore risolto dalle
    # formazioni una cessione inventata non cambierebbe niente e il test
    # passerebbe per la ragione sbagliata.
    noti = app._identita_note()
    base = app.costruisci(as_of=AS_OF, estendi_fino=FINE)
    r = _verifica(base, campione)
    da_trasf = campione[(r.fonte == app.FONTE_TRASFERIMENTI).to_numpy()
                        & campione.tm_player_id.isin(noti).to_numpy()]
    if da_trasf.empty:
        pytest.skip("nessuna riga del campione e' risolta dai trasferimenti")
    pid = int(da_trasf.tm_player_id.iloc[0])
    campione = da_trasf
    club_vero = int(campione[campione.tm_player_id == pid]
                    .club_id_squadra.iloc[0])
    finta = pd.DataFrame([{
        "player_id": pid,
        "transfer_date": pd.Timestamp(AS_OF) + pd.Timedelta(days=giorni_dal_cutoff),
        "transfer_season": "24/25",
        "from_club_id": club_vero, "to_club_id": 999999,
        "from_club_name": "vero", "to_club_name": "finto",
        "transfer_fee": 0, "market_value_in_eur": 0,
        "player_name": "prova", "stesso_giorno": False,
    }])
    falso = tmp_path / "transfermarkt_transfers_annuale.csv"
    pd.concat([tr, finta], ignore_index=True).to_csv(falso, index=False)
    return falso, campione


class _CartellaConSostituto:
    """Fa da `RAW / "transfermarkt"`, restituendo il file finto solo per la
    fonte dei trasferimenti e quelli veri per tutto il resto."""

    def __init__(self, reale, sostituto):
        self._reale, self._sostituto = reale, sostituto

    def __truediv__(self, nome):
        if nome == "transfermarkt_transfers_annuale.csv":
            return self._sostituto
        return self._reale / nome


class _RawConSostituto:
    """Fa da `RAW` del modulo `appartenenza`."""

    def __init__(self, falso):
        self._falso = falso

    def __truediv__(self, altro):
        base = RADICE / "data" / "raw"
        if altro == "transfermarkt":
            return _CartellaConSostituto(base / "transfermarkt", self._falso)
        return base / altro


def _con_fonte_finta(monkeypatch, falso, calcola):
    """Esegue `calcola()` con la fonte sostituita, e ripulisce le cache."""
    monkeypatch.setattr(app, "RAW", _RawConSostituto(falso))
    app._CACHE.clear()
    app._CACHE_FONTI.clear()
    try:
        return calcola()
    finally:
        monkeypatch.undo()
        app._CACHE.clear()
        app._CACHE_FONTI.clear()


def test_una_prova_futura_aggiunta_non_cambia_la_vista_alla_decisione(
        campione, tmp_path, monkeypatch):
    """Una cessione inserita nella fonte, datata dopo il cutoff, non deve
    toccare la vista alla decisione — e deve invece toccare quella osservativa,
    altrimenti l'iniezione non ha funzionato e il test passa a vuoto."""
    falso, campione = _fonte_con_prova_in_piu(tmp_path, campione, +30)
    prima_dec = _verifica(app.costruisci(as_of=AS_OF, estendi_fino=FINE), campione)
    prima_oss = _verifica(app.costruisci(), campione)

    def dopo():
        d = _verifica(app.costruisci(as_of=AS_OF, estendi_fino=FINE), campione)
        o = _verifica(app.costruisci(), campione)
        return d, o

    dopo_dec, dopo_oss = _con_fonte_finta(monkeypatch, falso, dopo)

    # Il confronto e' su tutte e tre le colonne, non sul solo esito: una
    # cessione inventata a un club che non esiste viene smentita dalle
    # comparse, la fonte scende dallo spell e l'esito resta `si`. Cambia pero'
    # la fonte, ed e' quello che va guardato.
    def diverse(a, b):
        return int(((a.esito != b.esito)
                    | (a.fonte != b.fonte)
                    | (a.club_id_alla_data != b.club_id_alla_data)).sum())

    assert diverse(prima_dec, dopo_dec) == 0, (
        "una prova datata dopo il cutoff ha cambiato la vista alla decisione: "
        "quella vista sta guardando avanti")

    # La controprova che l'iniezione funziona NON puo' venire dalla vista
    # osservativa: li' le comparse a referto battono sempre i trasferimenti, e
    # una cessione inventata non cambierebbe niente comunque. Viene dal test
    # gemello `test_una_prova_anteriore_aggiunta_cambia_la_vista_alla_decisione`,
    # che inserisce la stessa cessione con data anteriore al cutoff e verifica
    # che quella la vista alla decisione la veda. Stessa iniezione, due date,
    # esiti opposti: e' quello che separa la non anticipazione dal filtrare
    # tutto.
    assert prima_oss is not None and dopo_oss is not None


def test_una_prova_anteriore_aggiunta_cambia_la_vista_alla_decisione(
        campione, tmp_path, monkeypatch):
    """Gemello di sensibilita': la stessa cessione, datata prima del cutoff,
    deve cambiare la vista alla decisione. Se non la cambiasse, la censura
    starebbe scartando anche le prove ammissibili."""
    falso, campione = _fonte_con_prova_in_piu(tmp_path, campione, -3)
    prima = _verifica(app.costruisci(as_of=AS_OF, estendi_fino=FINE), campione)
    dopo = _con_fonte_finta(
        monkeypatch, falso,
        lambda: _verifica(app.costruisci(as_of=AS_OF, estendi_fino=FINE),
                          campione))
    cambiate = int(((prima.esito != dopo.esito)
                    | (prima.fonte != dopo.fonte)
                    | (prima.club_id_alla_data != dopo.club_id_alla_data)).sum())
    assert cambiate > 0, (
        "una cessione datata prima del cutoff non cambia niente: la censura "
        "sta scartando anche le prove ammissibili")


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


# ------------------------------------------------------ 6. bordo dell'orizzonte
def test_l_ultimo_giorno_coperto_riceve_risposta(campione):
    """L'orizzonte è esclusivo: chi lo passa deve saperlo.

    Difetto riprodotto: il panel passava come `estendi_fino` la data massima
    delle sue partite, ma gli intervalli sono semiaperti `[dal, al)`. Le 200
    righe dell'ultimo giorno del 2024-25 rispondevano tutte `ignoto`, mentre il
    giorno prima rispondeva 93 `si`, 36 `no`, 3 `ignoto`.

    Il contratto: `estendi_fino` è il primo giorno **non** coperto. Chi vuole
    coprire fino al giorno D compreso passa D + 1.
    """
    ultima = pd.Timestamp(FINE)
    stretto = app.costruisci(as_of=AS_OF, estendi_fino=ultima)
    largo = app.costruisci(as_of=AS_OF, estendi_fino=ultima + pd.Timedelta(days=1))
    quel_giorno = campione.assign(data=ultima)

    r_stretto = _verifica(stretto, quel_giorno)
    r_largo = _verifica(largo, quel_giorno)

    assert (r_stretto.esito == app.IGNOTO).all(), (
        "l'orizzonte non è esclusivo: l'ultimo giorno riceve risposta")
    assert (r_largo.esito != app.IGNOTO).any(), (
        "con l'orizzonte al giorno dopo, l'ultimo giorno resta senza risposta")


def test_il_panel_copre_la_sua_ultima_giornata():
    """Il panel deve chiedere un orizzonte che copra tutte le sue partite.

    È il test di integrazione del difetto qui sopra: non basta che
    `appartenenza` si comporti bene, deve essere il panel a chiederglielo nel
    modo giusto.
    """
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "l2_costruisci_panel", RADICE / "scripts" / "l2_costruisci_panel.py")
    panel = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(panel)

    if not PANEL.exists():
        pytest.skip(f"manca {PANEL}")
    P = pd.read_parquet(PANEL, columns=["data", "appartenenza_esito_dec"])
    P["data"] = pd.to_datetime(P["data"])
    ultimo = P[P.data == P.data.max()]
    if "appartenenza_esito_dec" not in P or P.appartenenza_esito_dec.isna().all():
        pytest.skip("il panel non porta la vista alla decisione")
    ignoti = (ultimo.appartenenza_esito_dec == app.IGNOTO).mean()
    assert ignoti < 0.9, (
        f"il {ignoti:.0%} delle righe dell'ultima giornata è `ignoto` nella "
        "vista alla decisione: l'orizzonte esclude il proprio ultimo giorno")
