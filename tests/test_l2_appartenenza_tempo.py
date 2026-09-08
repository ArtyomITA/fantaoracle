"""Censura temporale della tabella di appartenenza.

Ogni test qui dentro nasce da un difetto misurato nell'audit del 8 settembre
2026 (`data/l3/audit2/dati/RAPPORTO.md`, sezioni F1, F2, F3, F3b, F3c, F8, F9)
e dalla decisione di contratto presa in `reports/PROTOCOLLO_v2.md` §9.1
(**censura piena**: le prove si filtrano prima di risolvere i conflitti e di
costruire gli intervalli, orizzonte compreso).

Nessuno di questi test passa sul comportamento precedente: `costruisci()` non
accettava `as_of`, e la chiave della cache non distingueva ne' la data limite
ne' l'insieme degli identificativi.

Si eseguono con:

    PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTHONPATH=src python -m pytest \
        tests/test_l2_appartenenza_tempo.py -q

I test si dividono in due gruppi.

*Sintetici*: costruiscono cinque file sorgente minuscoli in una cartella
temporanea e riposizionano le costanti di percorso del modulo su di essa. Sono
veloci e permettono di variare una prova alla volta, che e' l'unico modo di
mostrare che il cutoff non filtra ne' troppo ne' troppo poco.

*Su dati veri*: riproducono tre dei quattro casi concreti documentati in F2
(Zeroli, Zurkowski, Nava). Leggono i file veri; se mancano, il test viene
saltato con un messaggio esplicito invece di fallire per un altro motivo.

Convenzione della censura, dichiarata perche' i due estremi non sono
intercambiabili: `as_of` e' **esclusivo** (`data < as_of`). Quindi censurare a
`D + 1 giorno` equivale alla censura `<= D` usata dagli script dell'audit, ed
e' con quella equivalenza che i casi concreti vengono confrontati.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from fantabot.tabellino import appartenenza as app       # noqa: E402

# club sintetici
ALFA, BETA, GAMMA = 100, 200, 300

# giocatori sintetici, uno per meccanismo
P_CATENA = 1        # due trasferimenti concordi
P_AMBIGUO = 2       # catena rotta: to_club[i] != from_club[i+1]
P_SPELL = 3         # solo comparse
P_LISTONE = 4       # solo listone
P_SMENTITO = 5      # trasferimento smentito da una comparsa posteriore
P_PRESTITO = 6      # uscita e rientro dentro la stessa finestra
P_IGNOTO = 7        # nessuna fonte lo nomina

TUTTI = [P_CATENA, P_AMBIGUO, P_SPELL, P_LISTONE, P_SMENTITO, P_PRESTITO,
         P_IGNOTO]

# trasferimenti di base: (player_id, data, from, to, stagione)
TRASFERIMENTI_BASE = [
    (P_CATENA, "2024-07-10", ALFA, BETA, "24/25"),
    (P_CATENA, "2025-07-10", BETA, GAMMA, "25/26"),
    (P_AMBIGUO, "2024-07-05", ALFA, BETA, "24/25"),
    # from GAMMA rompe la catena: il precedente diceva BETA. La data sta prima
    # del cutoff dei test sull'ambiguita' di proposito: se stesse dopo, sotto
    # censura la catena non risulterebbe rotta affatto, perche' l'anello che la
    # rompe non sarebbe ancora una prova disponibile (RAPPORTO.md, F3c)
    (P_AMBIGUO, "2024-07-15", GAMMA, ALFA, "24/25"),
    (P_SMENTITO, "2024-07-20", ALFA, BETA, "24/25"),
    (P_PRESTITO, "2024-07-08", ALFA, BETA, "24/25"),
    (P_PRESTITO, "2024-07-18", BETA, ALFA, "24/25"),
]

# comparse di base: (player_id, data, club)
COMPARSE_BASE = [
    (P_SPELL, "2024-09-01", BETA),
    (P_SPELL, "2024-10-01", BETA),
    (P_SPELL, "2024-11-01", BETA),
    # smentisce l'intervallo [2024-07-20, ...) del trasferimento di P_SMENTITO,
    # ma solo per chi puo' vederla: e' posteriore a quasi tutti i cutoff provati
    (P_SMENTITO, "2024-12-01", GAMMA),
]

# listone di base: (club, player, in_rosa_da)
LISTONE_BASE = [
    (GAMMA, P_LISTONE, "01/08/2026"),
]


def _scrivi_fonti(base: Path, trasferimenti, comparse, listone) -> None:
    """Materializza le cinque fonti nei percorsi che il modulo si aspetta."""
    (base / "processed" / "_match").mkdir(parents=True, exist_ok=True)
    (base / "raw" / "transfermarkt" / "_download").mkdir(parents=True,
                                                         exist_ok=True)
    ids = sorted({r[0] for r in trasferimenti} | {r[0] for r in comparse}
                 | {r[1] for r in listone} | set(TUTTI))
    pd.DataFrame({"tm_player_id": ids}).to_csv(
        base / "processed" / "_match" / "map_tm.csv", index=False)

    pd.DataFrame(
        [{"player_id": p, "transfer_date": d, "transfer_season": s,
          "from_club_id": a, "to_club_id": b}
         for p, d, a, b, s in trasferimenti]
    ).to_csv(base / "raw" / "transfermarkt" / "transfermarkt_transfers.csv",
             index=False)

    giochi = []
    schieramenti = []
    for i, (p, d, c) in enumerate(comparse, start=1):
        giochi.append({"game_id": i, "date": d})
        schieramenti.append({"game_id": i, "player_id": p, "club_id": c})
    dl = base / "raw" / "transfermarkt" / "_download"
    pd.DataFrame(giochi).to_csv(dl / "games.csv.gz", index=False,
                                compression="gzip")
    pd.DataFrame(schieramenti).to_csv(dl / "game_lineups.csv.gz", index=False,
                                      compression="gzip")

    pd.DataFrame([{"tm_club_id": c, "tm_player_id": p, "in_rosa_da": g}
                  for c, p, g in listone]).to_csv(
        base / "raw" / "transfermarkt" / "kader_2026.csv", index=False)


def _svuota_cache() -> None:
    """Azzera ogni cache di processo del modulo.

    `getattr` con default perche' il codice precedente alla correzione non ha
    la cache delle fonti grezze: senza questo, i test fallirebbero nel fixture
    invece che nell'asserzione che devono misurare.
    """
    for nome in ("_CACHE", "_CACHE_FONTI"):
        c = getattr(app, nome, None)
        if c is not None:
            c.clear()


@pytest.fixture
def fonti(tmp_path, monkeypatch):
    """Sposta il modulo su fonti sintetiche e restituisce un costruttore.

    Il costruttore riscrive le fonti a ogni chiamata, cosi' un test puo'
    cambiare **una** prova e rimisurare. Le chiamate che riscrivono le fonti
    usano `usa_cache=False`: la chiave della cache contiene l'impronta dei file,
    ma non e' quello che questi test misurano.
    """
    monkeypatch.setattr(app, "PROC", tmp_path / "processed")
    monkeypatch.setattr(app, "RAW", tmp_path / "raw")
    monkeypatch.setattr(app, "DL", tmp_path / "raw" / "transfermarkt" / "_download")
    _svuota_cache()

    def costruisci(trasferimenti=None, comparse=None, listone=None, **kw):
        _scrivi_fonti(tmp_path,
                      TRASFERIMENTI_BASE if trasferimenti is None else trasferimenti,
                      COMPARSE_BASE if comparse is None else comparse,
                      LISTONE_BASE if listone is None else listone)
        kw.setdefault("usa_cache", False)
        return app.costruisci(**kw)

    yield costruisci
    _svuota_cache()


def _griglia(t, giocatori, date) -> dict:
    """Esito di `verifica` su tutte le combinazioni (giocatore, club, data)."""
    fuori = {}
    for p in giocatori:
        for c in (ALFA, BETA, GAMMA):
            for d in date:
                fuori[(p, c, d)] = t.verifica(p, c, d)[0]
    return fuori


# --------------------------------------------------------------------------
# 1. le prove posteriori al cutoff non toccano nessun esito anteriore
# --------------------------------------------------------------------------

def test_prove_posteriori_al_cutoff_non_cambiano_nessun_esito(fonti):
    """F1/F3: una prova futura non deve poter spostare un intervallo passato.

    Il cutoff e' il 1 agosto 2024. Si aggiungono poi tre prove tutte
    successive: un trasferimento, una comparsa e un secondo trasferimento che
    romperebbe la catena. Con la censura piena la tabella deve restare identica
    su ogni interrogazione anteriore al cutoff.
    """
    cutoff = "2024-08-01"
    date = ["2024-07-03", "2024-07-12", "2024-07-15", "2024-07-19",
            "2024-07-20", "2024-07-31"]

    t0 = fonti(as_of=cutoff)
    prima = _griglia(t0, TUTTI, date)

    dopo_trasf = TRASFERIMENTI_BASE + [
        (P_CATENA, "2024-09-01", GAMMA, ALFA, "24/25"),   # rompe la catena
        (P_SPELL, "2025-01-15", BETA, GAMMA, "24/25"),
    ]
    dopo_comparse = COMPARSE_BASE + [
        (P_CATENA, "2024-08-15", GAMMA),                  # smentisce a valle
        (P_SMENTITO, "2024-08-20", GAMMA),
    ]
    t1 = fonti(trasferimenti=dopo_trasf, comparse=dopo_comparse, as_of=cutoff)
    dopo = _griglia(t1, TUTTI, date)

    assert dopo == prima


# --------------------------------------------------------------------------
# 2. sensibilita': una prova anteriore pertinente cambia gli esiti
# --------------------------------------------------------------------------

def test_una_prova_anteriore_al_cutoff_cambia_gli_esiti(fonti):
    """Controprova del test 1: se nulla cambiasse, il cutoff filtrerebbe tutto.

    Si sposta la destinazione del trasferimento del 10 luglio 2024 da BETA a
    GAMMA, cioe' una prova **anteriore** al cutoff. Almeno un esito deve
    cambiare, e deve cambiare proprio dove la prova conta.
    """
    cutoff = "2024-08-01"
    date = ["2024-07-03", "2024-07-12", "2024-07-15", "2024-07-19"]

    prima = _griglia(fonti(as_of=cutoff), TUTTI, date)

    modificati = [(P_CATENA, "2024-07-10", ALFA, GAMMA, "24/25")
                  if r[0] == P_CATENA and r[1] == "2024-07-10" else r
                  for r in TRASFERIMENTI_BASE]
    dopo = _griglia(fonti(trasferimenti=modificati, as_of=cutoff), TUTTI, date)

    assert dopo != prima
    assert prima[(P_CATENA, BETA, "2024-07-12")] == app.SI
    assert dopo[(P_CATENA, BETA, "2024-07-12")] == app.NO
    assert dopo[(P_CATENA, GAMMA, "2024-07-12")] == app.SI


# --------------------------------------------------------------------------
# 3. trasferimenti, prestiti, rientri, intervalli ambigui
# --------------------------------------------------------------------------

def test_prestito_e_rientro_dentro_la_finestra(fonti):
    """Uscita il 8 luglio, rientro il 18: tre intervalli, non uno."""
    t = fonti(as_of="2024-08-01")
    assert t.verifica(P_PRESTITO, ALFA, "2024-07-03")[0] == app.SI
    assert t.verifica(P_PRESTITO, ALFA, "2024-07-12")[0] == app.NO
    assert t.verifica(P_PRESTITO, BETA, "2024-07-12")[0] == app.SI
    assert t.verifica(P_PRESTITO, ALFA, "2024-07-19")[0] == app.SI
    assert t.verifica(P_PRESTITO, BETA, "2024-07-19")[0] == app.NO


def test_catena_rotta_resta_ignota_e_non_diventa_un_no(fonti):
    """Un anello rotto non autorizza a scegliere una delle due affermazioni.

    Il 5 luglio il giocatore va da ALFA a BETA; il 15 luglio riparte da GAMMA.
    Le due affermazioni sull'intervallo in mezzo non coincidono, quindi
    quell'intervallo non entra nella tabella: la risposta deve essere `ignoto`
    per **tutti** i club, non `no` per quello che ha perso il ballottaggio.
    """
    t = fonti(as_of="2024-08-01")
    for club in (ALFA, BETA, GAMMA):
        assert t.verifica(P_AMBIGUO, club, "2024-07-10")[0] == app.IGNOTO
    # gli intervalli non ambigui ai due lati rispondono ancora
    assert t.verifica(P_AMBIGUO, ALFA, "2024-07-03")[0] == app.SI
    assert t.verifica(P_AMBIGUO, ALFA, "2024-07-18")[0] == app.SI


def test_l_ambiguita_stessa_e_una_prova_e_va_censurata(fonti):
    """F3c: la prova futura agisce anche nella direzione opposta.

    L'ambiguita' nasce dal confronto con il trasferimento **successivo**. Al 15
    luglio quel trasferimento non e' ancora avvenuto: chi decide quel giorno
    vede una catena intatta e ha diritto alla risposta che essa da'. Non e' un
    difetto da correggere, e' la censura che funziona in entrambi i versi — e
    va detto, perche' la tabella odierna non e' «piu' informata» di quella di
    allora, e' diversa.
    """
    prima = fonti(as_of="2024-07-15")
    assert prima.verifica(P_AMBIGUO, BETA, "2024-07-10")[0] == app.SI
    dopo = fonti(as_of="2024-07-16")
    assert dopo.verifica(P_AMBIGUO, BETA, "2024-07-10")[0] == app.IGNOTO


def test_l_orizzonte_si_ricalcola_sui_soli_trasferimenti_ammessi(fonti):
    """§9.1: l'orizzonte globale del file non e' una prova disponibile prima.

    Con cutoff al 1 agosto 2024, l'ultimo trasferimento ammesso e' quello del
    20 luglio 2024: nessun intervallo dei trasferimenti puo' arrivare oltre il
    21 luglio, nemmeno quelli che nel file completo arrivano al 2025.
    """
    t = fonti(as_of="2024-08-01")
    assert t.orizzonte_trasferimenti == pd.Timestamp("2024-07-20")
    tr = t.intervalli[t.intervalli.origine == "trasferimenti"]
    assert len(tr)
    assert tr["al"].max() <= pd.Timestamp("2024-07-21")
    # e infatti oltre l'orizzonte la fonte tace, invece di affermare «e' ancora li'»
    assert t.verifica(P_CATENA, BETA, "2024-07-15")[0] == app.SI
    assert t.verifica(P_CATENA, BETA, "2024-07-25")[0] == app.IGNOTO

    pieno = fonti()
    assert pieno.orizzonte_trasferimenti == pd.Timestamp("2025-07-10")
    assert pieno.verifica(P_CATENA, BETA, "2024-07-25")[0] == app.SI


def test_una_comparsa_futura_non_toglie_un_intervallo_passato(fonti):
    """Meccanismo dei casi 1-3 di F2, in miniatura.

    `_valida_contro_comparse` toglie per intero un intervallo smentito. Con la
    censura, la comparsa del 1 dicembre 2024 non e' visibile a chi decide il 1
    agosto 2024, quindi non puo' cancellare l'intervallo che risponde a luglio.
    """
    censurata = fonti(as_of="2024-08-01")
    assert censurata.verifica(P_SMENTITO, BETA, "2024-07-25")[0] == app.IGNOTO
    assert censurata.verifica(P_SMENTITO, BETA, "2024-07-20")[0] == app.SI

    piena = fonti()
    # nella tabella completa l'intervallo e' stato tolto dalla comparsa di dicembre
    assert piena.verifica(P_SMENTITO, BETA, "2024-07-20")[0] == app.IGNOTO


# --------------------------------------------------------------------------
# 4. cutoff immediatamente prima e immediatamente dopo la stessa prova
# --------------------------------------------------------------------------

def test_cutoff_a_cavallo_della_stessa_prova_da_esiti_diversi(fonti):
    """Il trasferimento del 10 luglio 2024 e' l'unica prova che colloca
    `P_CATENA` all'ALFA prima di quella data (meccanismo del caso Bonucci, F2).

    Con `as_of` esclusivo: al 10 luglio la prova non c'e' ancora e la risposta
    e' `ignoto`; all'11 luglio c'e' e la risposta e' `si`.
    """
    domanda = "2024-07-05"
    prima = fonti(as_of="2024-07-10")
    dopo = fonti(as_of="2024-07-11")
    assert prima.verifica(P_CATENA, ALFA, domanda)[0] == app.IGNOTO
    assert dopo.verifica(P_CATENA, ALFA, domanda)[0] == app.SI


def test_cutoff_a_cavallo_di_una_comparsa(fonti):
    """Stessa cosa sulla fonte `formazioni`, ed e' il difetto principale di F1.

    `_spell_da_comparse` comprime le comparse in `[prima, ultima + 1 giorno)`.
    La domanda e' il 15 settembre 2024, in mezzo fra la comparsa del 1
    settembre e quella del 1 ottobre: **l'unica prova che copre quella data e'
    la comparsa posteriore**, perche' senza di essa il periodo finisce il 2
    settembre. Il cutoff a cavallo di quella comparsa deve quindi dare due
    risposte diverse.
    """
    domanda = "2024-09-15"
    prima = fonti(as_of="2024-10-01")
    dopo = fonti(as_of="2024-10-02")
    assert prima.verifica(P_SPELL, BETA, domanda)[0] == app.IGNOTO
    assert prima.verifica(P_SPELL, BETA, "2024-09-01")[0] == app.SI
    assert dopo.verifica(P_SPELL, BETA, domanda)[0] == app.SI


# --------------------------------------------------------------------------
# 5. la cache non puo' confondere due tabelle diverse
# --------------------------------------------------------------------------

def test_due_cutoff_diversi_non_condividono_la_cache(fonti):
    """F1b: la chiave della cache deve contenere `as_of`."""
    _scrivi_fonti(Path(app.PROC).parent, TRASFERIMENTI_BASE, COMPARSE_BASE,
                  LISTONE_BASE)
    a = app.costruisci(as_of="2024-07-11", usa_cache=True)
    b = app.costruisci(as_of="2024-08-01", usa_cache=True)
    assert a is not b
    assert a.diagnostica["as_of"] != b.diagnostica["as_of"]
    assert a.orizzonte_trasferimenti != b.orizzonte_trasferimenti
    # e la seconda chiamata con lo stesso cutoff torna la stessa tabella
    assert app.costruisci(as_of="2024-08-01", usa_cache=True) is b


def test_due_insiemi_di_id_diversi_non_condividono_la_cache(fonti):
    """F1b: la chiave era `min(ids)` e `len(ids)`, che collide.

    `{1, 2, 3}` e `{1, 6, 7}` hanno lo stesso minimo e la stessa cardinalita':
    con la chiave precedente la seconda chiamata riceveva la tabella della
    prima.
    """
    _scrivi_fonti(Path(app.PROC).parent, TRASFERIMENTI_BASE, COMPARSE_BASE,
                  LISTONE_BASE)
    a = app.costruisci(ids={P_CATENA, P_AMBIGUO, P_SPELL}, usa_cache=True)
    b = app.costruisci(ids={P_CATENA, P_PRESTITO, P_IGNOTO}, usa_cache=True)
    assert a is not b
    assert a.verifica(P_PRESTITO, BETA, "2024-07-12")[0] == app.IGNOTO
    assert b.verifica(P_PRESTITO, BETA, "2024-07-12")[0] == app.SI


# --------------------------------------------------------------------------
# 6. sconosciuto, assente e non appartenente restano tre cose diverse
# --------------------------------------------------------------------------

def test_sconosciuto_assente_e_non_appartenente_non_si_equiparano(fonti):
    """Tre righe, tre risposte diverse, nessuna delle quali e' un booleano."""
    t = fonti()
    # nessuna fonte lo nomina: ignoranza, non assenza
    assert t.verifica(P_IGNOTO, ALFA, "2024-07-12")[0] == app.IGNOTO
    # una fonte lo colloca altrove: e' un `no` con una prova dietro
    assert t.verifica(P_CATENA, GAMMA, "2024-07-12")[0] == app.NO
    # il listone afferma la non appartenenza prima dell'ingresso in rosa
    assert t.verifica(P_LISTONE, GAMMA, "2026-07-15")[0] == app.NO
    assert t.verifica(P_LISTONE, GAMMA, "2026-08-15")[0] == app.SI


def test_il_listone_censurato_torna_ignoto_e_non_no(fonti):
    """F9: `kader_2026.csv` non porta la data del proprio scatto.

    Con una data di scatto posteriore al cutoff, il listone non e' una prova
    disponibile: le sue affermazioni, comprese quelle di **non** appartenenza,
    devono sparire, e cio' che resta e' `ignoto` — mai `no`.
    """
    t = fonti(as_of="2026-08-20", data_scatto_listone="2026-09-05")
    assert t.verifica(P_LISTONE, GAMMA, "2026-07-15")[0] == app.IGNOTO
    assert t.verifica(P_LISTONE, GAMMA, "2026-08-15")[0] == app.IGNOTO
    assert t.diagnostica["listone_ammesso"] is False

    ammesso = fonti(as_of="2026-09-20", data_scatto_listone="2026-09-05")
    assert ammesso.verifica(P_LISTONE, GAMMA, "2026-08-15")[0] == app.SI
    assert ammesso.diagnostica["listone_ammesso"] is True


# --------------------------------------------------------------------------
# 7. diagnostica
# --------------------------------------------------------------------------

def test_la_diagnostica_dichiara_la_censura(fonti):
    """La tabella deve poter essere letta senza fidarsi di chi l'ha costruita."""
    t = fonti(as_of="2024-08-01", data_scatto_listone="2026-09-05")
    d = t.diagnostica
    assert d["as_of"] == "2024-08-01"
    assert d["listone_data_scatto"] == "2026-09-05"
    assert d["orizzonte_effettivo"] == "2024-07-20"
    # 6 trasferimenti su 7 ammessi, 4 comparse su 4 scartate
    assert d["prove_ammesse"]["trasferimenti"] == 6
    assert d["prove_scartate"]["trasferimenti"] == 1
    assert d["prove_ammesse"]["comparse"] == 0
    assert d["prove_scartate"]["comparse"] == 4
    assert d["prove_ammesse"]["listone"] == 0
    assert d["prove_scartate"]["listone"] == 1

    # la tabella dichiara fin dove puo' rispondere: sotto censura mai oltre
    # `as_of`, perche' ogni fonte chiude il bordo destro sull'ultima prova
    assert d["data_massima_risolvibile"] <= d["as_of"]

    pieno = fonti()
    assert pieno.diagnostica["as_of"] is None
    assert pieno.diagnostica["prove_scartate"]["trasferimenti"] == 0


# --------------------------------------------------------------------------
# 8. casi concreti di F2, sui dati veri
# --------------------------------------------------------------------------

# (nome, tm_player_id, data della riga, club della riga, club atteso sotto
#  censura equivalente a quella dell'audit). Fonte: RAPPORTO.md, sezione F2.
CASI_F2 = [
    ("Zeroli", 883349, "2024-08-17", 5, 41107),
    ("Zurkowski", 387234, "2024-08-17", 749, 3522),
    ("Nava", 815563, "2024-09-14", 5, 41107),
]

_VERI = {}


def _tabella_vera(as_of=None):
    """Tabella sui file veri, costruita una volta sola per `as_of`."""
    for f in [app.DL / "game_lineups.csv.gz", app.DL / "games.csv.gz",
              app.RAW / "transfermarkt" / "transfermarkt_transfers.csv"]:
        if not f.exists():
            pytest.skip(f"fonte assente: {f}")
    if as_of not in _VERI:
        _VERI[as_of] = app.costruisci(as_of=as_of)
    return _VERI[as_of]


@pytest.mark.parametrize("nome,pid,data,club_riga,club_censurato", CASI_F2)
def test_casi_concreti_f2(nome, pid, data, club_riga, club_censurato):
    """Le tre righe che l'audit ha smontato una per una.

    Tre asserzioni distinte:

    1. la tabella completa risponde `si` per il club della riga — e' lo stato
       che ha reso quelle righe `eleggibile = True`;
    2. censurando a `data + 1 giorno` (equivalente alla censura `<= data`
       usata da `casi_concreti.py`) il codice risponde il club che l'audit ha
       misurato: la prova che aveva ribaltato l'esito era posteriore;
    3. censurando alla data stessa l'esito non e' piu' `si`, quindi la riga
       esce dal denominatore invece di entrarci con un'affermazione anticipata.
    """
    piena = _tabella_vera()
    assert piena.verifica(pid, club_riga, data)[0] == app.SI

    equivalente = (pd.Timestamp(data) + pd.Timedelta(days=1)).strftime("%Y-%m-%d")
    cens = _tabella_vera(equivalente)
    assert cens.club_alla_data(pid, data)[0] == club_censurato
    assert cens.verifica(pid, club_riga, data)[0] == app.NO

    stretta = _tabella_vera(data)
    assert stretta.verifica(pid, club_riga, data)[0] != app.SI
