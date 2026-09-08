"""Tabella unica delle partite di Serie A: giornata, risultato, xG, identita'.

E' il primo pezzo del contratto dati del Livello 2. Una riga per partita, con:

  stagione, giornata, data, casa, trasferta      chi gioca, quando, in che turno
  gol_casa, gol_trasferta                        risultato
  xg_casa, xg_trasferta                          Understat, solo se giocata
  game_id                                        identita' Transfermarkt (storico)
  id_understat                                   identita' Understat
  fonte_giornata, fonte_risultato, fonte_xg      provenienza campo per campo
  giocata, provvisorio                           stato

## Contratto temporale

Congelato in `reports/CRITERI_L2_L3.md` sezione 7.2. Quattro colonne in piu':

  stato_partita                  conclusa | da_giocare | rinviata | senza_voti
  data_evento                    calcio d'inizio con l'ora, quando la fonte ce l'ha
  data_disponibilita_risultato   quando il risultato e' diventato disponibile
  rinviata                       0/1, indipendente dallo stato

Perche' servono. Il generatore del cubo divideva passato e futuro con
`data < as_of` e basta. Con quella regola una partita gia' in calendario ma non
ancora giocata finisce nel passato come se fosse osservata, e con `--solo-future`
sparisce del tutto: nessuna delle due meta' la contiene. Misurato il 7 settembre
2026 con `as_of = 2026-09-11`: 30 partite con data anteriore, solo 28 con un
risultato; le due del 7 settembre (Cagliari-Lecce, Udinese-Lazio) svanivano.
Nessuna partita puo' sparire, quindi il taglio deve avvenire su uno stato
esplicito e non sulla sola data.

Le definizioni, con la precedenza usata quando piu' d'una si applica:

  1. `da_giocare`   il risultato non c'e'. Comprende la partita il cui calcio
                    d'inizio e' gia' passato ma di cui non abbiamo l'esito:
                    resta nel futuro e va dichiarata «richiede aggiornamento
                    prima dell'uso»;
  2. `senza_voti`   il risultato c'e' ma i voti di quella giornata non sono
                    ancora nei dati. Al 7 settembre 2026 sono le 8 partite di
                    giornata 3 giocate fra il 4 e il 6 settembre;
  3. `rinviata`     risultato e voti ci sono, ma la data effettiva dista piu' di
                    tre giorni dalla mediana delle date della sua giornata;
  4. `conclusa`     tutto il resto.

La precedenza serve solo a riempire una colonna sola. Perche' nessuna
informazione vada persa, il rinvio ha anche una colonna sua (`rinviata`, 0/1) e
lo scarto in giorni resta leggibile in `scarto_giorni_giornata`: nello storico
41 partite su 3.040 superano i tre giorni, fino a 185 (Juventus-Napoli della
giornata 3 del 2020-21, giocata il 2021-04-07).

`data_disponibilita_risultato` resta **nulla**: nessuna fonte porta il momento
in cui il singolo risultato e' diventato pubblico, e ricostruirlo dal calcio
d'inizio sarebbe inventarlo. Cio' che e' documentabile e' il momento in cui il
risultato e' entrato nei nostri dati, ed e' in `acquisito_risultato_il`, preso
dal campo `acquisito_il` del file Understat. Sono due cose diverse e portano due
nomi diversi apposta: usare la seconda al posto della prima renderebbe
«disponibile nel 2026» un risultato del 2021.

## Il problema delle due epoche

Nessuna fonte copre tutto:

  2019-2025   Transfermarkt (`games.csv.gz`) ha giornata, data, risultato e
              `game_id`, che e' la chiave di `appearances`, `game_lineups` e
              `game_events`. Understat aggiunge gli xG.
  2026-27     Transfermarkt si e' fermato: il manutentore ha sospeso gli
              aggiornamenti a luglio 2026. La giornata viene dal calendario
              fantacalcio.it, risultato e xG da Understat. Non esiste
              `game_id`: la chiave e' `id_understat`, e i dati per giocatore
              di quella stagione arrivano dai voti, non da Transfermarkt.

La corrispondenza fra i nomi delle squadre delle due fonti non e' scritta a
mano: si ricava unendo le partite per data e risultato, che nella pratica
identificano la partita in modo univoco, e si verifica che sia una
corrispondenza uno a uno per stagione. Se non lo e', lo script si ferma.

Uso: python scripts/l2_prepara_partite.py
Output: data/processed/l2_partite.parquet + l2_mappa_squadre.csv
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw"
PROC = ROOT / "data" / "processed"
ANNI_TM = list(range(2019, 2026))       # stagioni coperte da Transfermarkt
ANNO_CORRENTE = 2026


def stagione(anno: int) -> str:
    return f"{anno}-{str(anno + 1)[2:]}"


def partite_tm(anno: int) -> pd.DataFrame:
    g = pd.read_csv(RAW / "transfermarkt" / "_download" / "games.csv.gz",
                    compression="gzip", low_memory=False)
    g = g[(g["competition_id"] == "IT1") & (g["season"] == anno)].copy()
    g["giornata"] = g["round"].astype(str).str.extract(r"(\d+)")[0].astype("Int64")
    g["data"] = pd.to_datetime(g["date"], errors="coerce").dt.date
    return g[["game_id", "giornata", "data", "home_club_id", "away_club_id",
              "home_club_name", "away_club_name",
              "home_club_goals", "away_club_goals"]]


def partite_us(anno: int) -> pd.DataFrame:
    f = RAW / "understat" / f"partite_{anno}.csv"
    if not f.exists():
        return pd.DataFrame()
    d = pd.read_csv(f)
    # `data` di Understat ha anche l'ora: si conserva a parte come momento del
    # calcio d'inizio, perche' la chiave di unione con Transfermarkt e' la sola
    # data (Transfermarkt non pubblica l'orario) ma l'ora serve a ordinare gli
    # eventi, che e' cio' che il contratto temporale chiede.
    d["data_ora_us"] = pd.to_datetime(d["data"], errors="coerce")
    d["data"] = d["data_ora_us"].dt.date
    if "acquisito_il" in d.columns:
        d["acquisito_us"] = d["acquisito_il"]
    else:
        d["acquisito_us"] = pd.NA
    return d


def unisci_storico(anno: int) -> tuple[pd.DataFrame, list[str], pd.DataFrame]:
    """Transfermarkt (giornata, identita') + Understat (xG), unite per data e
    risultato. Ritorna (partite, problemi, mappa squadre ricavata)."""
    tm = partite_tm(anno)
    us = partite_us(anno)
    problemi = []
    if us.empty:
        tm["xg_casa"] = None
        tm["xg_trasferta"] = None
        tm["id_understat"] = None
        tm["data_ora_us"] = pd.NaT
        tm["acquisito_us"] = pd.NA
        problemi.append(f"{anno}: Understat assente, nessun xG")
        m = tm.rename(columns={"home_club_goals": "gol_casa",
                               "away_club_goals": "gol_trasferta"})
        m["casa"] = m["home_club_name"]
        m["trasferta"] = m["away_club_name"]
        return m, problemi, pd.DataFrame()

    chiave = ["data", "gol_casa", "gol_trasferta"]
    a = tm.rename(columns={"home_club_goals": "gol_casa",
                           "away_club_goals": "gol_trasferta"})
    b = us[["id_understat", "data", "casa", "trasferta", "gol_casa",
            "gol_trasferta", "xg_casa", "xg_trasferta", "data_ora_us",
            "acquisito_us"]]
    # la chiave (data, risultato) puo' ripetersi in una giornata: si aggiunge
    # il vincolo che la coppia di squadre sia coerente, ricavando la mappa dai
    # soli abbinamenti unici e propagandola agli altri
    conteggi = a.groupby(chiave).size()
    unici = conteggi[conteggi == 1].index
    au = a[a.set_index(chiave).index.isin(unici)]
    bu = b[b.set_index(chiave).index.isin(unici)]
    coppie = au.merge(bu, on=chiave, suffixes=("_tm", "_us"))
    mappa = pd.concat([
        coppie[["home_club_id", "home_club_name", "casa"]]
        .rename(columns={"home_club_id": "club_id", "home_club_name": "nome_tm",
                         "casa": "nome_us"}),
        coppie[["away_club_id", "away_club_name", "trasferta"]]
        .rename(columns={"away_club_id": "club_id", "away_club_name": "nome_tm",
                         "trasferta": "nome_us"}),
    ]).drop_duplicates()
    # verifica: corrispondenza uno a uno
    for col_a, col_b in [("club_id", "nome_us"), ("nome_us", "club_id")]:
        cattivi = mappa.groupby(col_a)[col_b].nunique()
        cattivi = cattivi[cattivi > 1]
        if len(cattivi):
            problemi.append(f"{anno}: corrispondenza ambigua {col_a} -> {col_b}: "
                            f"{cattivi.to_dict()}")
    mappa = mappa.drop_duplicates("club_id")
    nomi = dict(zip(mappa.club_id, mappa.nome_us))
    a = a.copy()
    a["casa"] = a["home_club_id"].map(nomi)
    a["trasferta"] = a["away_club_id"].map(nomi)
    if a[["casa", "trasferta"]].isna().any().any():
        mancanti = sorted(set(a.loc[a.casa.isna(), "home_club_name"])
                          | set(a.loc[a.trasferta.isna(), "away_club_name"]))
        problemi.append(f"{anno}: squadre senza corrispondenza Understat: {mancanti}")
    # unione finale sulle squadre canoniche, che identificano la partita
    fin = a.merge(b[["id_understat", "casa", "trasferta", "xg_casa", "xg_trasferta",
                     "data_ora_us", "acquisito_us"]],
                  on=["casa", "trasferta"], how="left")
    if len(fin) != len(a):
        problemi.append(f"{anno}: unione con Understat ha cambiato le righe "
                        f"({len(a)} -> {len(fin)})")
    senza = int(fin.xg_casa.isna().sum())
    if senza:
        problemi.append(f"{anno}: {senza} partite senza xG")
    mappa["stagione"] = stagione(anno)
    return fin, problemi, mappa


def stagione_corrente() -> tuple[pd.DataFrame, list[str]]:
    """2026-27: giornata dal calendario fantacalcio.it, xG da Understat."""
    problemi = []
    cal = pd.read_csv(RAW / "calendario" / f"calendario_{stagione(ANNO_CORRENTE)}.csv")
    us = partite_us(ANNO_CORRENTE)
    if us.empty:
        return pd.DataFrame(), [f"{ANNO_CORRENTE}: Understat assente"]
    cal["data"] = pd.to_datetime(cal["data"], errors="coerce").dt.date
    # calcio d'inizio da calendario: data piu' ora, quando l'ora c'e'
    cal["data_ora_cal"] = pd.to_datetime(
        cal["data"].astype(str) + " " + cal["ora"].fillna("00:00").astype(str),
        errors="coerce")
    m = cal.merge(us[["id_understat", "data", "casa", "trasferta", "gol_casa",
                      "gol_trasferta", "xg_casa", "xg_trasferta", "giocata",
                      "data_ora_us", "acquisito_us"]],
                  on=["casa", "trasferta"], how="left", suffixes=("_cal", "_us"))
    if len(m) != len(cal):
        problemi.append(f"unione calendario-Understat: {len(cal)} -> {len(m)}")
    orfane = int(m.id_understat.isna().sum())
    if orfane:
        problemi.append(f"{orfane} partite del calendario senza corrispondenza Understat")
    entrambe = m[(m.giocata_cal == 1) & (m.giocata_us == 1)]
    diff = entrambe[(entrambe.gol_casa_cal != entrambe.gol_casa_us)
                    | (entrambe.gol_trasferta_cal != entrambe.gol_trasferta_us)]
    if len(diff):
        problemi.append(f"{len(diff)} risultati discordanti fra calendario e Understat")
    out = pd.DataFrame({
        "stagione": stagione(ANNO_CORRENTE),
        "giornata": m["giornata"].astype("Int64"),
        "data": m["data_us"].where(m["giocata_us"] == 1, m["data_cal"]),
        "casa": m["casa"], "trasferta": m["trasferta"],
        "gol_casa": m["gol_casa_us"], "gol_trasferta": m["gol_trasferta_us"],
        "xg_casa": m["xg_casa"], "xg_trasferta": m["xg_trasferta"],
        "game_id": pd.NA, "id_understat": m["id_understat"],
        "giocata": m["giocata_us"].fillna(0).astype(int),
        "provvisorio": m["provvisorio"],
        # calcio d'inizio: quello effettivo di Understat per le partite gia'
        # giocate, quello previsto dal calendario per le altre
        "data_evento": m["data_ora_us"].where(m["giocata_us"] == 1,
                                              m["data_ora_cal"]),
        "acquisito_risultato_il": m["acquisito_us"],
        "fonte_giornata": "fantacalcio.it calendario",
        "fonte_risultato": "understat",
        "fonte_xg": "understat",
    })
    return out, problemi


SOGLIA_RINVIO_GIORNI = 3


def giornate_con_voti(stagione: str) -> set | None:
    """Coppie `(giornata, squadra)` presenti nei voti di quella stagione.

    Ritorna `None` se il file dei voti non esiste: in quel caso non si puo'
    dire che una partita sia «senza voti», si puo' solo dire che di quella
    stagione non abbiamo i voti affatto. Sono due cose diverse e la seconda non
    autorizza a marcare 380 partite come incomplete.
    """
    f = RAW / "voti" / f"voti_{stagione}.csv"
    if not f.exists():
        return None
    v = pd.read_csv(f, usecols=["giornata", "squadra"])
    return set(zip(v["giornata"].astype("Int64"), v["squadra"].astype(str)))


def contratto_temporale(df: pd.DataFrame) -> tuple[pd.DataFrame, list[str]]:
    """Aggiunge `stato_partita`, `rinviata`, `scarto_giorni_giornata` e
    `data_disponibilita_risultato`.

    Le definizioni e la precedenza sono nel docstring del modulo e nel contratto
    degli stati, sezione 7.2. Qui si esegue e basta, misurando quello che si
    trova invece di darlo per scontato.
    """
    problemi: list[str] = []
    d = df.copy()
    if "data_evento" not in d.columns:
        d["data_evento"] = pd.NaT
    d["data_evento"] = pd.to_datetime(d["data_evento"], errors="coerce")
    # dove l'ora non e' nota, il calcio d'inizio e' almeno il giorno giusto
    d["data_evento"] = d["data_evento"].fillna(pd.to_datetime(d["data"],
                                                              errors="coerce"))

    # rinvio: scarto dalla mediana delle date della propria giornata
    mediana = d.groupby(["stagione", "giornata"])["data"].transform("median")
    d["scarto_giorni_giornata"] = (d["data"] - mediana).dt.days.abs()
    d["rinviata"] = (d["scarto_giorni_giornata"] > SOGLIA_RINVIO_GIORNI) \
        .fillna(False).astype(int)

    # risultato disponibile
    ha_risultato = d["gol_casa"].notna() & d["gol_trasferta"].notna()
    disaccordo = int((ha_risultato != (d["giocata"] == 1)).sum())
    if disaccordo:
        problemi.append(f"{disaccordo} partite in cui `giocata` e la presenza "
                        f"del risultato non concordano")

    # voti gia' acquisiti per quella partita: servono entrambe le squadre,
    # perche' i voti sono per (giornata, squadra)
    voti_noti = pd.Series(True, index=d.index)
    for st in d["stagione"].unique():
        sel = d["stagione"] == st
        coppie = giornate_con_voti(st)
        if coppie is None:
            # stagione senza file dei voti: non si puo' affermare nulla, quindi
            # non si marca nulla come `senza_voti`
            continue
        g = d.loc[sel, "giornata"].astype("Int64")
        voti_noti.loc[sel] = [
            (gg, str(c)) in coppie and (gg, str(t)) in coppie
            for gg, c, t in zip(g, d.loc[sel, "casa"], d.loc[sel, "trasferta"])]

    d["stato_partita"] = np.select(
        [~ha_risultato,
         ha_risultato & ~voti_noti,
         ha_risultato & voti_noti & (d["rinviata"] == 1)],
        ["da_giocare", "senza_voti", "rinviata"],
        default="conclusa")

    # nessuna fonte porta il momento in cui il singolo risultato e' diventato
    # pubblico: la colonna esiste, dichiarata nulla, e non viene inventata
    d["data_disponibilita_risultato"] = pd.NaT
    if "acquisito_risultato_il" not in d.columns:
        d["acquisito_risultato_il"] = pd.NA

    # la somma degli stati deve fare il totale, sempre
    if int(d["stato_partita"].notna().sum()) != len(d):
        problemi.append("alcune partite sono rimaste senza `stato_partita`")
    return d, problemi


def main() -> int:
    tutte, problemi, mappe = [], [], []
    for anno in ANNI_TM:
        d, p, mp = unisci_storico(anno)
        problemi.extend(p)
        mappe.append(mp)
        out = pd.DataFrame({
            "stagione": stagione(anno), "giornata": d["giornata"],
            "data": d["data"], "casa": d["casa"], "trasferta": d["trasferta"],
            "gol_casa": d["gol_casa"], "gol_trasferta": d["gol_trasferta"],
            "xg_casa": d.get("xg_casa"), "xg_trasferta": d.get("xg_trasferta"),
            "game_id": d["game_id"], "id_understat": d.get("id_understat"),
            "giocata": 1, "provvisorio": 0,
            # Transfermarkt da' solo il giorno; l'ora, quando c'e', viene da
            # Understat. Dove manca resta la mezzanotte del giorno giusto, che
            # e' comunque un ordinamento corretto per data.
            "data_evento": d.get("data_ora_us"),
            "acquisito_risultato_il": d.get("acquisito_us"),
            "fonte_giornata": "transfermarkt games",
            "fonte_risultato": "transfermarkt games",
            "fonte_xg": "understat",
        })
        tutte.append(out)
        print(f"{stagione(anno)}: {len(out)} partite, "
              f"xG su {int(out.xg_casa.notna().sum())}")
    corr, p = stagione_corrente()
    problemi.extend(p)
    if len(corr):
        tutte.append(corr)
        print(f"{stagione(ANNO_CORRENTE)}: {len(corr)} partite, "
              f"{int(corr.giocata.sum())} giocate, "
              f"xG su {int(corr.xg_casa.notna().sum())}")

    df = pd.concat(tutte, ignore_index=True)
    df["data"] = pd.to_datetime(df["data"], errors="coerce")
    df, note = contratto_temporale(df)
    problemi.extend(note)
    # l'ordinamento e' per data e ora effettive, non per giornata: con i rinvii
    # le giornate si accavallano (19 casi nello storico, fino a 172 giorni)
    # `data_evento` puo' essere nullo dove Understat non copre la partita:
    # l'ordinamento primario resta il giorno, che non e' mai nullo, e l'ora
    # affina dentro la giornata di calendario
    df = df.sort_values(["stagione", "data", "data_evento", "giornata"]) \
           .reset_index(drop=True)
    PROC.mkdir(parents=True, exist_ok=True)
    df.to_parquet(PROC / "l2_partite.parquet", index=False)
    mp = pd.concat([m for m in mappe if len(m)], ignore_index=True)
    mp.to_csv(PROC / "l2_mappa_squadre.csv", index=False, encoding="utf-8")

    print(f"\nscritto l2_partite.parquet: {len(df)} partite, "
          f"{df.stagione.nunique()} stagioni, "
          f"{int(df.giocata.sum())} giocate, xG su {int(df.xg_casa.notna().sum())}")
    print(f"scritto l2_mappa_squadre.csv: {len(mp)} righe, "
          f"{mp.club_id.nunique()} club Transfermarkt")
    if problemi:
        print(f"\n{len(problemi)} PROBLEMI:")
        for x in problemi:
            print("  " + x)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
