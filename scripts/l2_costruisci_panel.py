"""Panel giocatore x partita: la base dati unica del Livello 1 e del Livello 2.

Sostituisce `scripts/f14_build_panel.py`, che dichiarava un contratto che non
realizzava. Difetti dimostrati della versione precedente:

  - partiva dalle righe dei voti, quindi non poteva distinguere "non
    convocato" da "riga assente": l'universo atteso non veniva costruito;
  - produceva due soli stati (`con_voto`, `senza_voto`): titolarita', panchina
    ed esclusione non esistevano;
  - risolveva le identita' con `drop_duplicates("master_id")`, cioe' sceglieva
    in silenzio una corrispondenza fra piu' candidate;
  - non conservava alcun momento di acquisizione o disponibilita';
  - sul 2026/27 tutte le 638 righe restavano senza partita collegata, perche'
    l'unica fonte di partite era Transfermarkt, che quella stagione non copre.

## Che cosa costruisce

Una riga per (giocatore del listone, partita della sua squadra). L'universo
parte dal listone, non dai voti: cosi' una riga mancante nei voti diventa
un'informazione, non un buco.

### Stati, tenuti separati

`stato_convocazione` (dalle formazioni ufficiali, Transfermarkt `game_lineups`)

    titolare                schierato dall'inizio
    panchina_entrato        in panchina, poi entrato
    panchina_non_entrato    in panchina, mai entrato
    escluso                 eleggibile, partita con formazioni note, non convocato
    ignoto                  manca la prova: niente formazioni per quella partita,
                            oppure appartenenza al club non ricostruibile

`stato_voto` (dai voti di fantacalcio.it)

    con_voto                ha un voto numerico
    senza_voto              la fonte segna s.v.
    nessuna_riga            nessuna riga per quella partita

Le due dimensioni non si sovrappongono e nessuna implica l'altra. In
particolare: **s.v. non significa "entrato pochi minuti"** (la fonte non dice
perche') e **riga assente non significa "non convocato"**.

### Appartenenza al club: perche' `non_in_rosa` e' sparito

La versione precedente aveva un sesto stato, `non_in_rosa`, che affermava «non
faceva parte di quella rosa». Non era provato. Due difetti indipendenti,
entrambi misurati:

  - `_in_rosa()` leggeva `P["club_id"]`, colonna che il merge delle formazioni
    non portava mai nel panel: la guardia in testa alla funzione restituiva
    `False` su tutte e 124.184 le righe dei cinque panel prodotti, quindi il
    ramo `fuori_lista` non veniva mai raggiunto e tutto finiva in `non_in_rosa`;
  - il periodo usato era la meta' di stagione (`giornata > 19`), che non e' una
    partizione temporale: 41 partite su 3.040 distano piu' di tre giorni dalla
    mediana della loro giornata, fino a 185 giorni, e in 19 casi le giornate si
    accavallano.

Su un campione di 30 righe `non_in_rosa` del 2024/25 l'audit ha trovato 17 casi
in cui il giocatore era eccome in quella rosa, 7 indeterminati e 6 confermati.
Un'etichetta sbagliata nel 57% dei casi non e' un'etichetta.

Al suo posto ci sono tre colonne che dicono quello che si sa e ammettono di non
sapere il resto (contratto degli stati, `reports/CRITERI_L2_L3.md` §7.1):

    club_id_alla_data     club per cui era tesserato alla DATA della partita
    fonte_appartenenza    trasferimenti | formazioni | listone | ignota
    eleggibile            True | False | nullo

`eleggibile` e' `True` solo se il giocatore era tesserato per quel club a quella
data **e** la partita ha formazioni note; `False` se e' dimostrato che era di un
altro club; nullo quando manca la prova. Le righe con `eleggibile` nullo non
stanno ne' al numeratore ne' al denominatore di nessuna propensione: non sono
un'assenza, sono un'ignoranza. La ricostruzione dell'appartenenza sta in
`fantabot.tabellino.appartenenza` e ragiona **solo per date**, mai per giornata.

La colonna `in_rosa_nel_periodo` non viene piu' scritta: era costante `False` su
tutte le righe di tutte le stagioni e un lettore ragionevole l'avrebbe usata
come filtro.

### Provenienza

Ogni blocco di colonne porta la sua fonte (`fonte_*`) e, dove esiste, il
momento in cui il dato e' stato acquisito (`acquisito_*`). Il momento in cui
un'informazione e' diventata pubblica NON e' ricostruibile a posteriori per i
voti e le formazioni storiche: resta `None`, non viene inventato. Per le
previsioni vale la data della partita (`data`), che e' un limite superiore
prudente della disponibilita'.

### Punteggio della fonte

    fantavoto = voto + 3*(gol_fatti + rigore_segnato) + assist
                - 0.5*ammonizione - espulsione
                + 3*rigori_parati - 3*rigori_sbagliati - 2*autogol
                - gol_subiti (solo portieri)

Il rigore segnato NON e' compreso in `gol_fatti`. La riconciliazione viene
ricalcolata a ogni esecuzione e riportata come numero di righe discordanti,
mai come "100%": una discordanza nota resta esplicita (Delprato, Parma,
giornata 3 del 2024/25) finche' non e' risolta con prove.
Le regole della lega (porta inviolata, modificatore) NON stanno qui: si
applicano in `fantabot.tabellino.punteggio`.

Uso:
  python scripts/l2_costruisci_panel.py
  python scripts/l2_costruisci_panel.py 2024-25 --verifica
Output: data/processed/l2_panel_{stagione}.parquet + l2_panel_qualita.json
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw"
PROC = ROOT / "data" / "processed"
DL = RAW / "transfermarkt" / "_download"
STAGIONI = ["2021-22", "2022-23", "2023-24", "2024-25", "2025-26", "2026-27"]

sys.path.insert(0, str(ROOT / "src"))
from fantabot.tabellino import appartenenza as app       # noqa: E402


def anno(stagione: str) -> int:
    return int(stagione[:4])


def impronta_file(p: Path) -> str | None:
    if not p.exists():
        return None
    h = hashlib.sha256()
    with p.open("rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()[:16]


# --------------------------------------------------------------------------
# identita'
# --------------------------------------------------------------------------

def mappa_identita(stagione: str) -> tuple[pd.DataFrame, dict]:
    """master_id <-> tm_player_id, con le ambiguita' dichiarate, non risolte."""
    mt = pd.read_csv(PROC / "_match" / "map_tm.csv")
    if "stagione" in mt.columns:
        mt = mt[mt["stagione"] == stagione]
    mt = mt.dropna(subset=["master_id", "tm_player_id"]).copy()
    mt["master_id"] = mt["master_id"].astype("Int64")
    mt["tm_player_id"] = mt["tm_player_id"].astype("Int64")
    per_master = mt.groupby("master_id")["tm_player_id"].nunique()
    per_tm = mt.groupby("tm_player_id")["master_id"].nunique()
    ambigue = {
        "master_id_con_piu_tm": {int(k): int(v)
                                 for k, v in per_master[per_master > 1].items()},
        "tm_con_piu_master_id": {int(k): int(v)
                                 for k, v in per_tm[per_tm > 1].items()},
    }
    # tengo solo le corrispondenze non ambigue: le ambigue restano senza
    # tm_player_id e la riga lo dichiara, invece di scegliere in silenzio
    buone = mt[mt.master_id.isin(per_master[per_master == 1].index)
               & mt.tm_player_id.isin(per_tm[per_tm == 1].index)]
    buone = buone[["master_id", "tm_player_id"]].drop_duplicates()

    # stagione in corso: Transfermarkt non pubblica piu' le partite, ma la rosa
    # si'. `map_tm_kader_2026.csv` abbina il listone alla rosa dichiarata e
    # recupera i giocatori che `map_tm.csv` non conosce (465 su 587 nel panel
    # 2026-27, che diventano 579). Serve perche' senza `tm_player_id` non si
    # puo' chiedere niente alla tabella di appartenenza.
    fk = PROC / "_match" / "map_tm_kader_2026.csv"
    if stagione == "2026-27" and fk.exists():
        k = pd.read_csv(fk, usecols=["master_id", "tm_player_id"]).dropna()
        k["master_id"] = k["master_id"].astype("Int64")
        k["tm_player_id"] = k["tm_player_id"].astype("Int64")
        # le due mappe possono discordare: la piu' vecchia (`map_tm`) vince,
        # perche' e' quella usata da tutte le altre stagioni, e la discordanza
        # viene contata invece che risolta in silenzio
        gia = dict(zip(buone.master_id, buone.tm_player_id))
        disc = [int(m) for m, t in zip(k.master_id, k.tm_player_id)
                if m in gia and gia[m] != t]
        nuovi = k[~k.master_id.isin(gia)]
        ambigue["kader_discordi_con_map_tm"] = disc
        ambigue["kader_identita_aggiunte"] = int(len(nuovi))
        buone = pd.concat([buone, nuovi], ignore_index=True)
    return buone, ambigue


# --------------------------------------------------------------------------
# universo atteso
# --------------------------------------------------------------------------

def listone(stagione: str) -> pd.DataFrame:
    p = PROC / f"players_{stagione}.parquet"
    d = pd.read_parquet(p, columns=["master_id", "nome", "ruolo", "squadra",
                                    "nuovo_in_serie_a", "cambio_squadra"])
    d["master_id"] = d["master_id"].astype("Int64")
    d["fonte_listone"] = p.name
    return d


def squadre_voti(stagione: str) -> pd.DataFrame:
    """squadra per giocatore secondo i voti: e' la squadra alla data della
    partita, perche' i voti sono per giornata."""
    v = pd.read_csv(RAW / "voti" / f"voti_{stagione}.csv",
                    usecols=["giornata", "squadra", "nome"])
    mv = pd.read_csv(PROC / "_match" / "map_voti.csv")
    mv = mv[mv["stagione"] == stagione]
    v = v.merge(mv[["squadra", "nome", "master_id"]], on=["squadra", "nome"],
                how="left")
    v["master_id"] = v["master_id"].astype("Int64")
    return v.dropna(subset=["master_id"])[["master_id", "giornata", "squadra"]]


def partite(stagione: str) -> pd.DataFrame:
    d = pd.read_parquet(PROC / "l2_partite.parquet")
    d = d[d.stagione == stagione].copy()
    d["data"] = pd.to_datetime(d["data"])
    return d


def sigle(stagione: str) -> dict:
    m = json.loads((PROC / "_match" / "team_maps.json").read_text("utf-8"))
    return m.get(stagione, {})


# --------------------------------------------------------------------------
# formazioni e minuti
# --------------------------------------------------------------------------

_LINEUPS_CACHE: pd.DataFrame | None = None


def formazioni(stagione: str, id_partite: set) -> pd.DataFrame:
    """game_lineups filtrato alle partite della stagione."""
    global _LINEUPS_CACHE
    f = DL / "game_lineups.csv.gz"
    if not f.exists():
        return pd.DataFrame(columns=["game_id", "tm_player_id", "tipo",
                                     "posizione", "capitano"])
    if _LINEUPS_CACHE is None:
        _LINEUPS_CACHE = pd.read_csv(f, compression="gzip", low_memory=False,
                                     usecols=["game_id", "player_id", "club_id",
                                              "type", "position", "team_captain"])
    d = _LINEUPS_CACHE[_LINEUPS_CACHE.game_id.isin(id_partite)].copy()
    d = d.rename(columns={"player_id": "tm_player_id", "type": "tipo",
                          "position": "posizione", "team_captain": "capitano"})
    d["tm_player_id"] = d["tm_player_id"].astype("Int64")
    return d


def completezza_distinte(id_partite: set) -> pd.DataFrame:
    """Per ogni (partita, club) dice se la distinta e' completa.

    Si misura sulla **fonte originale**, prima di qualunque filtro
    sull'universo fantacalcistico: un giocatore che non e' nel listone non
    compare nel panel, ma la sua presenza in distinta conta per stabilire se la
    distinta esiste per intero.

    La regola precedente era «almeno un `tipo` non nullo nella partita», e un
    solo giocatore agganciato bastava a dichiararla nota. Misurato sulla fonte:
    su 162.234 squadra-partita, 161.554 (99,58%) hanno 11 titolari, 671 ne
    hanno fra 1 e 10, 4 nessuno. Una distinta parziale non autorizza a
    classificare come non convocati tutti quelli che non vi compaiono: produce
    un'osservazione incompleta, che qui si chiama `parziale`.
    """
    f = DL / "game_lineups.csv.gz"
    if not f.exists():
        return pd.DataFrame(columns=["game_id", "club_id", "titolari",
                                     "panchina", "distinta"])
    global _LINEUPS_CACHE
    if _LINEUPS_CACHE is None:
        _LINEUPS_CACHE = pd.read_csv(f, compression="gzip", low_memory=False,
                                     usecols=["game_id", "player_id", "club_id",
                                              "type", "position", "team_captain"])
    d = _LINEUPS_CACHE[_LINEUPS_CACHE.game_id.isin(id_partite)]
    g = (d.groupby(["game_id", "club_id"])
           .agg(titolari=("type", lambda x: int((x == "starting_lineup").sum())),
                panchina=("type", lambda x: int((x == "substitutes").sum())))
           .reset_index())
    g["distinta"] = np.where(g.titolari == 11, "completa",
                             np.where(g.titolari > 0, "parziale", "assente"))
    return g


def presenze(stagione: str) -> pd.DataFrame:
    app = pd.read_csv(RAW / "transfermarkt" / "transfermarkt_appearances_seriea.csv")
    app = app[app["season_start_year"] == anno(stagione)].copy()
    app = app.rename(columns={"player_id": "tm_player_id",
                              "minutes_played": "minuti"})
    app["tm_player_id"] = app["tm_player_id"].astype("Int64")
    return app[["tm_player_id", "game_id", "player_club_id", "minuti",
                "yellow_cards", "red_cards", "goals", "assists"]]


# --------------------------------------------------------------------------
# voti
# --------------------------------------------------------------------------

def fantavoto_fonte(d: pd.DataFrame) -> pd.Series:
    subiti_p = d["gol_subiti"].where(d["ruolo_voti"].str.lower() == "p", 0).fillna(0)
    return (d["voto"] + 3 * (d["gol_fatti"] + d["rigore_segnato"]) + d["assist"]
            - 0.5 * d["ammonizione"] - d["espulsione"]
            + 3 * d["rigori_parati"] - 3 * d["rigori_sbagliati"]
            - 2 * d["autogol"] - subiti_p)


def voti(stagione: str) -> tuple[pd.DataFrame, dict]:
    f = RAW / "voti" / f"voti_{stagione}.csv"
    v = pd.read_csv(f)
    mv = pd.read_csv(PROC / "_match" / "map_voti.csv")
    mv = mv[mv["stagione"] == stagione]
    prima = len(v)
    v = v.merge(mv[["squadra", "nome", "master_id"]], on=["squadra", "nome"],
                how="left")
    if len(v) != prima:
        raise RuntimeError(f"{stagione}: l'unione con map_voti ha cambiato le "
                           f"righe ({prima} -> {len(v)}): mappa non univoca")
    v = v.rename(columns={"ruolo": "ruolo_voti", "squadra": "squadra_voti"})
    v["master_id"] = v["master_id"].astype("Int64")
    v["fantavoto_ricostruito"] = fantavoto_fonte(v)
    v["scarto_ricostruzione"] = (v["fantavoto_ricostruito"] - v["fantavoto"]).abs()
    v["stato_voto"] = np.where(v["sv"].fillna(0) == 0, "con_voto", "senza_voto")
    qualita = {
        "righe_voti": int(len(v)),
        "senza_master_id": int(v.master_id.isna().sum()),
        "coppie_giocatore_giornata_duplicate":
            int((v.groupby(["master_id", "giornata"]).size() > 1).sum()),
    }
    return v, qualita


def club_di_squadra(stagione: str) -> dict:
    """Nome esteso della squadra -> `club_id` Transfermarkt, per la stagione.

    Serve a sapere *a quale club* si riferisce la riga di panel, perche' la
    domanda sull'appartenenza e' sempre «era di QUESTO club a QUESTA data».

      - storico: `l2_mappa_squadre.csv`, ricavata unendo Transfermarkt e
        Understat per data e risultato (vedi `l2_prepara_partite.py`);
      - 2026-27: Transfermarkt non copre piu' le partite, quindi la mappa passa
        per la rosa (`kader_2026.csv`, che ha la sigla e `tm_club_id`) e per
        `team_maps.json`, che lega la sigla al nome esteso.

    Le squadre che non trovano un club restano fuori dalla mappa: chi chiama
    conta le righe rimaste senza `club_id` e le riporta
    (`squadre_senza_club_id`), perche' una squadra senza club rende `ignoto`
    tutto cio' che la riguarda e va vista, non ingoiata.
    """
    f = PROC / "l2_mappa_squadre.csv"
    m: dict = {}
    if f.exists():
        ms = pd.read_csv(f)
        ms = ms[ms.stagione == stagione]
        m = {str(n): int(c) for n, c in zip(ms.nome_us, ms.club_id)}
    if not m:
        # stagione senza mappa Transfermarkt: si passa dalla rosa dichiarata
        fk = RAW / "transfermarkt" / "kader_2026.csv"
        ftm = PROC / "_match" / "team_maps.json"
        if fk.exists() and ftm.exists():
            k = pd.read_csv(fk, usecols=["squadra", "tm_club_id"]).dropna()
            per_sigla = {str(s): int(c) for s, c in
                         k.groupby("squadra")["tm_club_id"].agg(
                             lambda s: s.value_counts().index[0]).items()}
            sig = json.loads(ftm.read_text("utf-8")).get(stagione, {})
            m = {nome: per_sigla[sg] for nome, sg in sig.items()
                 if sg in per_sigla}
    return m


# --------------------------------------------------------------------------
# costruzione
# --------------------------------------------------------------------------

def data_decisione(stagione: str, panel_data_min) -> pd.Timestamp:
    """Data in cui si decide, per la vista informativa di quella stagione.

    Convenzione dichiarata: il giorno prima della prima partita della stagione.
    E' la data piu' tarda in cui una decisione pre-campionato puo' essere presa
    senza conoscere nessun risultato, e non e' scelta per far tornare un
    conteggio. Chi vuole una data diversa la passa esplicitamente.
    """
    return pd.Timestamp(panel_data_min) - pd.Timedelta(days=1)


def costruisci(stagione: str, as_of=None,
               estendi_fino=None) -> tuple[pd.DataFrame, dict]:
    acquisito = time.strftime("%Y-%m-%dT%H:%M:%S")
    q = {"stagione": stagione, "costruito_il": acquisito, "impronte": {}}
    for nome, p in [("voti", RAW / "voti" / f"voti_{stagione}.csv"),
                    ("listone", PROC / f"players_{stagione}.parquet"),
                    ("partite", PROC / "l2_partite.parquet"),
                    ("game_lineups", DL / "game_lineups.csv.gz")]:
        q["impronte"][nome] = impronta_file(p)

    lst = listone(stagione)
    par = partite(stagione)
    sg = sigle(stagione)
    inv = {v: k for k, v in sg.items()}          # sigla -> nome esteso
    v, qv = voti(stagione)
    q.update(qv)

    # partite per squadra (nome esteso della fonte voti/calendario)
    lunga = pd.concat([
        par.assign(squadra=par.casa, avversario=par.trasferta, in_casa=1,
                   gol_squadra=par.gol_casa, gol_avversario=par.gol_trasferta,
                   xg_squadra=par.xg_casa, xg_avversario=par.xg_trasferta),
        par.assign(squadra=par.trasferta, avversario=par.casa, in_casa=0,
                   gol_squadra=par.gol_trasferta, gol_avversario=par.gol_casa,
                   xg_squadra=par.xg_trasferta, xg_avversario=par.xg_casa),
    ], ignore_index=True)[
        ["stagione", "giornata", "data", "game_id", "id_understat", "squadra",
         "avversario", "in_casa", "gol_squadra", "gol_avversario",
         "xg_squadra", "xg_avversario", "giocata",
         # contratto temporale (§7.2): il taglio passato/futuro si fa su questi
         # due, non sulla sola data
         "stato_partita", "data_evento"]]

    # squadra del giocatore ALLA DATA: dai voti quando c'e' (e' per giornata),
    # altrimenti dal listone (squadra di inizio stagione)
    sq_voti = squadre_voti(stagione)
    lst_sq = lst[["master_id", "squadra"]].copy()
    lst_sq["squadra_estesa"] = lst_sq["squadra"].map(inv).fillna(lst_sq["squadra"])
    universo = []
    giornate = sorted(par.giornata.dropna().unique())
    per_g = {int(g): sq_voti[sq_voti.giornata == g].set_index("master_id")["squadra"]
             for g in giornate}
    for g in giornate:
        s = per_g.get(int(g), pd.Series(dtype=object))
        d = lst_sq.copy()
        d["giornata"] = int(g)
        d["squadra_alla_data"] = d["master_id"].map(s)
        d["fonte_squadra"] = np.where(d["squadra_alla_data"].notna(),
                                      "voti (giornata)", "listone (inizio stagione)")
        d["squadra_alla_data"] = d["squadra_alla_data"].fillna(d["squadra_estesa"])
        universo.append(d[["master_id", "giornata", "squadra_alla_data",
                           "fonte_squadra"]])
    U = pd.concat(universo, ignore_index=True)
    U = U.merge(lst.drop(columns=["squadra"]), on="master_id", how="left")

    prima = len(U)
    P = U.merge(lunga, left_on=["giornata", "squadra_alla_data"],
                right_on=["giornata", "squadra"], how="left")
    q["universo_righe"] = int(prima)
    # chiave unica di partita. Transfermarkt copre lo storico e da' `game_id`;
    # dal 2026-27 non pubblica piu' le partite e l'unica identita' e'
    # `id_understat`. Prima si usava solo `game_id`: risultato, sul 2026-27
    # `id_partite` restava vuoto, il ramo senza formazioni non creava nemmeno le
    # colonne e tutte le 22.306 righe finivano `ignoto` senza che nessuna altra
    # informazione venisse calcolata. Con una chiave che ricade su Understat il
    # resto del panel si costruisce lo stesso; le formazioni restano assenti,
    # perche' davvero non esistono, e lo stato resta `ignoto` per il motivo
    # giusto.
    _gid = pd.to_numeric(P["game_id"], errors="coerce").astype("Int64")
    _uid = pd.to_numeric(P["id_understat"], errors="coerce").astype("Int64")
    P["id_partita"] = np.where(
        _gid.notna(), "tm:" + _gid.astype(str),
        np.where(_uid.notna(), "us:" + _uid.astype(str), None))
    q["universo_senza_partita"] = int(P.game_id.isna().sum()
                                      if "game_id" in P else len(P))
    q["universo_senza_partita_ne_understat"] = int(
        (P.game_id.isna() & P.id_understat.isna()).sum())
    q["universo_senza_chiave_partita"] = int(pd.isna(P["id_partita"]).sum())
    if len(P) != prima:
        q["ATTENZIONE_universo_cardinalita"] = f"{prima} -> {len(P)}"

    # voti
    colonne_voto = ["master_id", "giornata", "ruolo_voti", "squadra_voti", "voto",
                    "fantavoto", "gol_fatti", "gol_subiti", "assist",
                    "ammonizione", "espulsione", "rigori_parati",
                    "rigori_sbagliati", "rigore_segnato", "autogol", "sv",
                    "stato_voto", "fantavoto_ricostruito", "scarto_ricostruzione"]
    vv = v.dropna(subset=["master_id"])[colonne_voto].drop_duplicates(
        ["master_id", "giornata"], keep=False)      # le duplicate restano fuori
    escluse = len(v.dropna(subset=["master_id"])) - len(vv)
    q["voti_esclusi_per_duplicazione"] = int(escluse)
    prima = len(P)
    P = P.merge(vv, on=["master_id", "giornata"], how="left")
    if len(P) != prima:
        q["ATTENZIONE_voti_cardinalita"] = f"{prima} -> {len(P)}"
    P["stato_voto"] = P["stato_voto"].fillna("nessuna_riga")

    # identita' Transfermarkt, formazioni e minuti
    mid, ambigue = mappa_identita(stagione)
    q["identita_ambigue"] = ambigue
    P = P.merge(mid, on="master_id", how="left")
    q["con_tm_player_id"] = float(P.tm_player_id.notna().mean())

    # Le colonne delle formazioni esistono sempre, anche quando la fonte non
    # copre la stagione: una colonna assente costringe ogni consumatore a
    # indovinare, una colonna piena di nulli dichiara l'ignoranza.
    P["game_id_int"] = pd.to_numeric(P["game_id"], errors="coerce").astype("Int64")
    id_partite = set(par.game_id.dropna().astype(int))
    if id_partite:
        fz = formazioni(stagione, id_partite)
        pr = presenze(stagione)
        prima = len(P)
        # `club_id` entra nel merge: e' il club a referto per quella partita,
        # cioe' la prova diretta dell'appartenenza. Prima veniva letto dal dump
        # e poi buttato via qui, ed era l'unico motivo per cui `_in_rosa()` non
        # poteva funzionare. Rinominato perche' `player_club_id` di
        # `appearances` e' un'altra colonna, presente solo per chi e' sceso in
        # campo.
        prese = fz[["game_id", "tm_player_id", "club_id", "tipo", "posizione",
                    "capitano"]].rename(columns={"game_id": "game_id_int",
                                                 "club_id": "club_id_formazione"})
        chiavi_doppie = int(prese.duplicated(["game_id_int", "tm_player_id"]).sum())
        if chiavi_doppie:
            q["ATTENZIONE_formazioni_chiave_duplicata"] = chiavi_doppie
        P = P.merge(prese, on=["game_id_int", "tm_player_id"], how="left")
        if len(P) != prima:
            q["ATTENZIONE_formazioni_cardinalita"] = f"{prima} -> {len(P)}"
        prima = len(P)
        P = P.merge(pr.rename(columns={"game_id": "game_id_int"}),
                    on=["game_id_int", "tm_player_id"], how="left")
        if len(P) != prima:
            q["ATTENZIONE_presenze_cardinalita"] = f"{prima} -> {len(P)}"
        P["fonte_formazione"] = np.where(P["tipo"].notna(), "transfermarkt game_lineups",
                                         "assente")
        P["fonte_minuti"] = np.where(P["minuti"].notna(), "transfermarkt appearances",
                                     "assente")
    else:
        for c in ["tipo", "posizione", "capitano", "minuti", "player_club_id",
                  "club_id_formazione", "yellow_cards", "red_cards", "goals",
                  "assists"]:
            P[c] = pd.NA
        P["club_id_formazione"] = P["club_id_formazione"].astype("Int64")
        P["fonte_formazione"] = "assente"
        P["fonte_minuti"] = "assente"

    # ------------------------------------------------------------------
    # appartenenza al club alla DATA della partita
    # ------------------------------------------------------------------
    # `club_id_squadra` e' il club di cui parla la riga: quello della squadra a
    # cui il panel ha attribuito il giocatore per quella giornata.
    mappa_club = club_di_squadra(stagione)
    P["club_id_squadra"] = P["squadra_alla_data"].map(mappa_club).astype("Int64")
    q["squadre_senza_club_id"] = sorted(
        set(P.loc[P.club_id_squadra.isna(), "squadra_alla_data"].dropna()))
    q["righe_senza_club_id_squadra"] = int(P.club_id_squadra.isna().sum())

    # ------------------------------------------------------------------
    # Due viste dell'appartenenza, tenute separate perche' rispondono a due
    # domande diverse (contratto in `reports/PROTOCOLLO_v2.md` §F2):
    #
    #   OSSERVATIVA  «di chi era, per quel che oggi sappiamo?» Usa tutte le
    #                prove note, comprese quelle successive alla partita. Serve
    #                ai bersagli, alla valutazione e alla descrizione storica.
    #                Non puo' entrare fra le informazioni di una decisione
    #                passata.
    #
    #   INFORMATIVA  «di chi risultava, per chi decideva a quella data?» Le
    #                prove sono filtrate prima di risolvere i conflitti, e
    #                l'affermazione vale in avanti come inferenza di
    #                continuita', segnata come tale in `confidenza_dec`.
    #
    # Con `as_of = None` la seconda vista non viene costruita e le colonne
    # restano nulle: il panel storico continua a funzionare come prima.
    # ------------------------------------------------------------------
    tab = app.costruisci()
    q["appartenenza"] = tab.diagnostica
    ris = tab.verifica_molti(P["tm_player_id"], P["club_id_squadra"], P["data"])
    P["appartenenza_esito"] = ris["esito"]
    P["fonte_appartenenza"] = ris["fonte"]
    P["club_id_alla_data"] = ris["club_id_alla_data"]

    if as_of == "auto":
        as_of = data_decisione(stagione, P["data"].min())
    if as_of is not None:
        orizzonte = (estendi_fino if estendi_fino is not None
                     else P["data"].max())
        tab_dec = app.costruisci(as_of=as_of, estendi_fino=orizzonte)
        q["appartenenza_decisione"] = tab_dec.diagnostica
        rd = tab_dec.verifica_molti(P["tm_player_id"], P["club_id_squadra"],
                                    P["data"])
        P["appartenenza_esito_dec"] = rd["esito"]
        P["fonte_appartenenza_dec"] = rd["fonte"]
        P["club_id_alla_data_dec"] = rd["club_id_alla_data"]
        P["confidenza_dec"] = rd["confidenza"]
        q["as_of_decisione"] = str(pd.Timestamp(as_of).date())
        q["estendi_fino"] = str(pd.Timestamp(orizzonte).date())
    else:
        for c in ("appartenenza_esito_dec", "fonte_appartenenza_dec",
                  "confidenza_dec"):
            P[c] = pd.Series(pd.NA, index=P.index, dtype=object)
        P["club_id_alla_data_dec"] = pd.Series(pd.NA, index=P.index,
                                               dtype="Int64")
        q["as_of_decisione"] = None

    # Il referto della partita stessa e' la prova piu' diretta che esista e
    # sovrascrive qualunque ricostruzione: se il giocatore compare nella
    # formazione di quella partita, quel giorno era di quel club.
    da_referto = P["club_id_formazione"].notna()
    P.loc[da_referto, "club_id_alla_data"] = P.loc[da_referto, "club_id_formazione"]
    P.loc[da_referto, "fonte_appartenenza"] = app.FONTE_FORMAZIONI
    P.loc[da_referto, "appartenenza_esito"] = np.where(
        P.loc[da_referto, "club_id_formazione"]
        == P.loc[da_referto, "club_id_squadra"], app.SI, app.NO)

    # Completezza della distinta, misurata sulla fonte originale per la coppia
    # (partita, club). La regola precedente — «almeno un `tipo` non nullo nella
    # partita» — dichiarava nota una distinta anche quando un solo giocatore
    # era agganciato, e su quella base classificava tutti gli altri come non
    # convocati. Sulla fonte: 99,58% delle squadra-partita ha 11 titolari, 671
    # ne hanno fra 1 e 10, 4 nessuno.
    dist = completezza_distinte(set(P["game_id"].dropna().astype(int)))
    if len(dist):
        P = P.merge(dist.rename(columns={"club_id": "club_id_squadra"}),
                    on=["game_id", "club_id_squadra"], how="left")
        P["distinta"] = P["distinta"].fillna("assente")
    else:
        P["distinta"] = "assente"
    # una distinta parziale e' un'osservazione incompleta, non una prova di
    # esclusione: solo `completa` autorizza a dire «era disponibile e non e'
    # stato convocato»
    formazioni_note = P["distinta"].eq("completa")

    # eleggibile: True solo con appartenenza dimostrata E formazioni note;
    # False se e' dimostrato che era di un altro club; nullo dove manca la prova
    P["eleggibile"] = pd.Series(pd.NA, index=P.index, dtype="boolean")
    P.loc[(P.appartenenza_esito == app.SI) & formazioni_note, "eleggibile"] = True
    P.loc[P.appartenenza_esito == app.NO, "eleggibile"] = False

    # ------------------------------------------------------------------
    # stato di convocazione
    # ------------------------------------------------------------------
    # Regole, in ordine:
    #  - se il giocatore e' a referto PER QUESTO club, vale la formazione;
    #  - se non c'e' ma la partita ha formazioni note ed era eleggibile, e'
    #    un'esclusione documentata;
    #  - in ogni altro caso lo stato e' `ignoto`. Ci finiscono le partite senza
    #    formazioni e le righe in cui l'appartenenza al club non e' dimostrata:
    #    sono ignoranze, e `eleggibile` dice quale delle due.
    # Nota sul primo caso: 37 righe su 65.334 con formazione, in quattro
    # stagioni, hanno il giocatore a referto per il club AVVERSARIO (era stato
    # ceduto e il panel lo teneva ancora nella vecchia squadra perche' senza
    # riga nei voti). Tutte e 37 sono `substitutes`, nessuna e' un titolare.
    # Attribuirgli `panchina_non_entrato` per la squadra sbagliata sarebbe
    # falso: restano `ignoto` con `eleggibile = False`.
    convocato_qui = P["tipo"].notna() & (P["appartenenza_esito"] == app.SI)
    entrato = pd.to_numeric(P["minuti"], errors="coerce").fillna(0) > 0
    # `eleggibile` e' a tre valori: qui serve la sola condizione «dimostrato
    # eleggibile», quindi il nullo vale come «non dimostrato», non come falso
    eleg_si = P["eleggibile"].fillna(False).astype(bool)
    P["stato_convocazione"] = np.select(
        [convocato_qui & (P["tipo"] == "starting_lineup"),
         convocato_qui & (P["tipo"] != "starting_lineup") & entrato,
         convocato_qui & (P["tipo"] != "starting_lineup") & ~entrato,
         ~convocato_qui & formazioni_note & eleg_si],
        ["titolare", "panchina_entrato", "panchina_non_entrato", "escluso"],
        default="ignoto")
    P["formazioni_note"] = formazioni_note

    P["stagione"] = stagione
    P["fonte_voto"] = "fantacalcio.it"
    P["acquisito_il"] = acquisito
    P["disponibile_dal"] = pd.NaT      # non ricostruibile a posteriori: resta ignoto
    P["fonte_partita"] = np.where(P["game_id"].notna(), "transfermarkt games",
                                  np.where(P["id_understat"].notna(),
                                           "fantacalcio.it calendario + understat",
                                           "assente"))
    return P, q


# --------------------------------------------------------------------------
# verifiche
# --------------------------------------------------------------------------

def verifica(P: pd.DataFrame, q: dict) -> dict:
    con = P.stato_voto == "con_voto"
    q["righe_panel"] = int(len(P))
    q["righe_partite_giocate"] = int((P.giocata == 1).sum())
    q["righe_partite_future"] = int((P.giocata != 1).sum())
    G = P[P.giocata == 1]
    q["copertura_partita"] = float(P.fonte_partita.ne("assente").mean())
    q["copertura_minuti"] = float(G.minuti.notna().mean()) if len(G) else 0.0
    q["copertura_formazioni"] = (float(G.stato_convocazione.ne("ignoto").mean())
                                 if len(G) else 0.0)
    q["stati_convocazione"] = P.stato_convocazione.value_counts().to_dict()
    q["stati_voto"] = P.stato_voto.value_counts().to_dict()

    # contratto degli stati, §7.1: appartenenza ed eleggibilita'
    q["appartenenza_esiti"] = P.appartenenza_esito.value_counts().to_dict()
    q["fonti_appartenenza"] = P.fonte_appartenenza.value_counts().to_dict()
    q["eleggibile_true"] = int((P.eleggibile == True).sum())        # noqa: E712
    q["eleggibile_false"] = int((P.eleggibile == False).sum())      # noqa: E712
    q["eleggibile_nullo"] = int(P.eleggibile.isna().sum())
    q["club_id_alla_data_noto"] = int(P.club_id_alla_data.notna().sum())
    q["righe_con_formazioni_note"] = int(P.formazioni_note.sum())
    # completezza della distinta, misurata sulla fonte originale
    if "distinta" in P:
        q["distinta"] = P.distinta.value_counts().to_dict()
    # vista informativa alla data di decisione: quanto risponde, e quanta parte
    # della risposta e' inferenza di continuita' invece che prova diretta
    if "appartenenza_esito_dec" in P and P.appartenenza_esito_dec.notna().any():
        q["appartenenza_esiti_dec"] = (
            P.appartenenza_esito_dec.value_counts(dropna=False)
            .rename(index=str).to_dict())
        q["confidenza_dec"] = (P.confidenza_dec.value_counts(dropna=False)
                               .rename(index=str).to_dict())
        # dove le due viste divergono: e' la misura di quanta informazione
        # futura la vista osservativa stava usando
        div = P.appartenenza_esito != P.appartenenza_esito_dec
        q["viste_divergenti"] = int(div.sum())
        q["viste_divergenti_dettaglio"] = (
            {f"{a} -> {b}": int(n) for (a, b), n in
             P.loc[div].groupby(["appartenenza_esito",
                                 "appartenenza_esito_dec"]).size().items()}
            if div.any() else {})
    # invariante: un titolare non puo' essere dichiarato non eleggibile
    tit = P.stato_convocazione == "titolare"
    q["titolari"] = int(tit.sum())
    q["titolari_eleggibile_false"] = int((tit & (P.eleggibile == False)).sum())   # noqa: E712
    q["titolari_eleggibile_nullo"] = int((tit & P.eleggibile.isna()).sum())
    if q["titolari_eleggibile_false"] or q["titolari_eleggibile_nullo"]:
        q["ATTENZIONE_titolare_non_eleggibile"] = (
            f"{q['titolari_eleggibile_false']} False, "
            f"{q['titolari_eleggibile_nullo']} nulli")
    # invariante: `escluso` esiste solo con eleggibilita' dimostrata
    esc = P.stato_convocazione == "escluso"
    q["esclusi"] = int(esc.sum())
    q["esclusi_non_eleggibili"] = int((esc & (P.eleggibile != True)).sum())  # noqa: E712
    if q["esclusi_non_eleggibili"]:
        q["ATTENZIONE_escluso_senza_eleggibilita"] = q["esclusi_non_eleggibili"]
    scarti = P.loc[con, "scarto_ricostruzione"] >= 0.011
    q["righe_con_voto"] = int(con.sum())
    q["ricostruzione_discordanti"] = int(scarti.sum())
    if scarti.any():
        d = P.loc[con][scarti.values]
        q["ricostruzione_esempi"] = d[["nome", "squadra_voti", "giornata",
                                       "fantavoto", "fantavoto_ricostruito"]] \
            .head(5).to_dict("records")
    # s.v. non e' "entrato pochi minuti": quanti hanno davvero giocato?
    sv = P[P.stato_voto == "senza_voto"]
    q["senza_voto"] = int(len(sv))
    q["senza_voto_con_minuti_noti"] = int(sv.minuti.notna().sum())
    q["senza_voto_minuti_zero"] = int((sv.minuti.fillna(-1) == 0).sum())
    q["senza_voto_minuti_positivi"] = int((sv.minuti.fillna(-1) > 0).sum())
    # righe assenti dai voti: quante sono davvero fuori dai convocati?
    nr = P[P.stato_voto == "nessuna_riga"]
    q["nessuna_riga"] = int(len(nr))
    q["nessuna_riga_per_stato"] = nr.stato_convocazione.value_counts().to_dict()
    # copertura stratificata
    strati = {}
    for et, sel in [("portieri", G.ruolo == "P"),
                    ("attaccanti", G.ruolo == "A"),
                    ("nuovi in Serie A", G.nuovo_in_serie_a == 1),
                    ("cambio squadra", G.cambio_squadra == 1)]:
        s = G[sel]
        if len(s):
            strati[et] = {
                "righe": int(len(s)),
                "partita": round(float(s.fonte_partita.ne("assente").mean()), 4),
                "minuti": round(float(s.minuti.notna().mean()), 4),
                "formazione": round(float(s.stato_convocazione.ne("ignoto").mean()), 4),
                "con_voto": round(float((s.stato_voto == "con_voto").mean()), 4),
            }
    q["strati"] = strati
    return q


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("stagioni", nargs="*", default=STAGIONI)
    ap.add_argument("--verifica", action="store_true", help="non scrive i parquet")
    ap.add_argument("--as-of", default="auto",
                    help="data di decisione per la vista informativa: una data "
                         "AAAA-MM-GG, `auto` (il giorno prima della prima "
                         "partita della stagione) oppure `nessuna` per non "
                         "costruire la vista")
    ap.add_argument("--estendi-fino", default=None,
                    help="fin dove l'appartenenza vale in avanti per inferenza "
                         "di continuita'. Predefinito: l'ultima partita della "
                         "stagione")
    a = ap.parse_args()
    tutte = {}
    for st in a.stagioni:
        if not (RAW / "voti" / f"voti_{st}.csv").exists():
            print(f"{st}: voti assenti, salto")
            continue
        if not (PROC / f"players_{st}.parquet").exists():
            print(f"{st}: listone assente (players_{st}.parquet), salto: "
                  "senza listone non esiste l'universo atteso")
            continue
        as_of = None if a.as_of == "nessuna" else a.as_of
        P, q = costruisci(st, as_of=as_of, estendi_fino=a.estendi_fino)
        q = verifica(P, q)
        tutte[st] = q
        print(f"\n--- {st}: {q['righe_panel']} righe di universo, di cui "
              f"{q['righe_partite_giocate']} su partite gia' giocate "
              f"({q['righe_voti']} righe nei voti) ---")
        print(f"  partita agganciata {q['copertura_partita']:.2%} | "
              f"minuti {q['copertura_minuti']:.2%} | "
              f"formazioni {q['copertura_formazioni']:.2%}")
        print(f"  convocazione: {q['stati_convocazione']}")
        print(f"  voto: {q['stati_voto']}")
        print(f"  punteggio della fonte: {q['ricostruzione_discordanti']} righe "
              f"discordanti su {q['righe_con_voto']} con voto")
        print(f"  s.v.: {q['senza_voto']} totali, di cui minuti noti "
              f"{q['senza_voto_con_minuti_noti']} "
              f"(zero {q['senza_voto_minuti_zero']}, "
              f"positivi {q['senza_voto_minuti_positivi']})")
        print(f"  righe assenti dai voti: {q['nessuna_riga']} -> "
              f"{q['nessuna_riga_per_stato']}")
        for et, s in q["strati"].items():
            print(f"  {et:18s} righe {s['righe']:6d} | partita {s['partita']:.2%} "
                  f"| minuti {s['minuti']:.2%} | formazione {s['formazione']:.2%} "
                  f"| con voto {s['con_voto']:.2%}")
        for k in q:
            if k.startswith("ATTENZIONE"):
                print(f"  {k}: {q[k]}")
        if not a.verifica:
            out = PROC / f"l2_panel_{st}.parquet"
            P.to_parquet(out, index=False)
            print(f"  scritto {out.name} ({out.stat().st_size // 1024} KB)")
    (PROC / "l2_panel_qualita.json").write_text(
        json.dumps(tutte, indent=1, default=str), encoding="utf-8")
    print(f"\nscritto {PROC / 'l2_panel_qualita.json'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
