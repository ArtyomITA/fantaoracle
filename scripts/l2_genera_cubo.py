"""Genera il cubo TABELLINO di una stagione e ne verifica la fedelta'.

Stima i quattro pezzi sulle partite anteriori alla data limite, genera N
stagioni simulate sul calendario vero di quella stagione, e confronta le
distribuzioni simulate con quelle osservate. Il confronto e' quello che
mancava al banco precedente (`scripts/f15_banco.py`), che misurava i dati
reali senza mai chiedere al simulatore di riprodurli.

## Disciplina temporale

`--as-of` e' la data limite dell'informazione. Tutto quello che entra nella
stima e' anteriore a quella data; il calendario invece e' noto prima che la
stagione cominci, quindi puo' essere usato per intero. Tre casi:

    asta prima del campionato     as_of = giorno dell'asta, k = 0 giornate note
    asta a campionato iniziato    as_of = giorno dell'asta, k > 0
    aggiornamento in stagione     as_of = giorno dell'aggiornamento

Nel terzo caso il cubo genera solo le giornate future: i punti gia' realizzati
non si simulano, si sommano. Sono cose diverse e vanno tenute separate.

## Che cosa confronta

  distribuzione dei punti      media, scarto, quantili, per ruolo
  presenze                     quota di giornate con voto, per ruolo
  gol e assist                 totali di lega e per ruolo
  dipendenza fra compagni      correlazioni portiere-difensori, difensori,
                               centrocampisti, attaccanti
  porta inviolata              frequenza per squadra
  coerenza dei tabellini       riconciliazione col risultato

Uso:
  python scripts/l2_genera_cubo.py 2024-25 --sims 60
  python scripts/l2_genera_cubo.py 2026-27 --sims 100 --as-of 2026-09-07
"""
from __future__ import annotations

import argparse
import json
import pickle
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
PROC = ROOT / "data" / "processed"
OUT = ROOT / "data" / "l2"

from fantabot.tabellino import eventi as ev            # noqa: E402
from fantabot.tabellino import generatore as gen       # noqa: E402
from fantabot.tabellino import partecipazione as pa    # noqa: E402
from fantabot.tabellino import voto as vt              # noqa: E402
from fantabot.tabellino import configurazione as cfg          # noqa: E402
from fantabot.tabellino import contratto                     # noqa: E402
from fantabot.tabellino import presenze                      # noqa: E402
from fantabot.tabellino.partita import pesi_decadimento, stima as stima_partita  # noqa: E402

STAGIONI_PANEL = ["2021-22", "2023-24", "2024-25", "2025-26", "2026-27"]
GIORNATE = 38


def carica_panel(data_fit=None) -> tuple[pd.DataFrame, dict]:
    """Il panel delle stagioni, con il contratto temporale verificato.

    Prima questa funzione faceva un glob e concatenava quello che trovava: il
    cutoff con cui i panel erano stati costruiti non entrava da nessuna parte, e
    un panel costruito oggi poteva servire un fit datato 2024 senza che niente
    lo impedisse. Ora il cutoff si chiede, e un panel incompatibile fa alzare
    `ContrattoIncompatibile` invece di restituire righe plausibili.

    Restituisce anche i contratti, perche' il rapporto del cubo deve dire su
    quali dati e' stato costruito, non solo che cosa ne e' uscito.
    """
    return contratto.carica_panel_multi(
        PROC, STAGIONI_PANEL, data_fit=data_fit,
        esigi_vista_al_fit=data_fit is not None)


def leggi_bersaglio_presenze(stagione: str, universo, ruolo: dict,
                             storia_voti=None):
    """I bersagli di presenza a voto per l'universo completo.

    Delega a `fantabot.tabellino.presenze`, che e' lo stesso adattatore usato
    dal banco: prima le due strade erano separate e trattavano diversamente i
    giocatori senza storia e le previsioni di zero.
    """
    b = presenze.costruisci(PROC / f"b_predictions_{stagione}.json",
                            universo, ruolo, storia_voti=storia_voti)
    d = b.diagnostica
    print(f"  bersaglio presenze: {d['con_bersaglio']}/{d['universo']} "
          f"({d['per_fonte'][presenze.FONTE_PREVISIONE]} da previsione, "
          f"{d['per_fonte'][presenze.FONTE_PRIOR_RUOLO]} da prior di ruolo, "
          f"{d['per_fonte'][presenze.FONTE_ASSENTE]} senza), "
          f"{d['previsioni_zero_tenute']} previsioni zero tenute")
    return b


def correlazioni_compagni(d: pd.DataFrame, colonna: str) -> dict:
    """Correlazione fra compagni della stessa partita, per coppia di ruoli."""
    fuori = {}
    for et, ra, rb in [("portiere-difensori", ["P"], ["D"]),
                       ("difensori", ["D"], ["D"]),
                       ("centrocampisti", ["C"], ["C"]),
                       ("attaccanti", ["A"], ["A"])]:
        vals = []
        for _, g in d.groupby(["giornata", "squadra"]):
            a = g[g.ruolo.isin(ra)][colonna].to_numpy(float)
            b = g[g.ruolo.isin(rb)][colonna].to_numpy(float)
            if ra == rb:
                for i in range(len(a)):
                    for j in range(i + 1, len(a)):
                        vals.append((a[i], a[j]))
            else:
                for x in a:
                    for y in b:
                        vals.append((x, y))
        if len(vals) < 50:
            fuori[et] = float("nan")
            continue
        v = np.array(vals)
        fuori[et] = round(float(np.corrcoef(v[:, 0], v[:, 1])[0, 1]), 4)
    return fuori


def osservato(P: pd.DataFrame, stagione: str) -> pd.DataFrame:
    d = P[(P.stagione == stagione) & (P.stato_voto == "con_voto")].copy()
    d["punti"] = pd.to_numeric(d["fantavoto"], errors="coerce")
    d["voto_puro"] = pd.to_numeric(d["voto"], errors="coerce")
    d["squadra"] = d["squadra_alla_data"]
    d["gol"] = (pd.to_numeric(d["gol_fatti"], errors="coerce").fillna(0)
                + pd.to_numeric(d["rigore_segnato"], errors="coerce").fillna(0))
    d["assist"] = pd.to_numeric(d["assist"], errors="coerce").fillna(0)
    d["ammonizione"] = pd.to_numeric(d["ammonizione"], errors="coerce").fillna(0)
    return d[["giornata", "master_id", "ruolo", "squadra", "punti", "voto_puro",
              "gol", "assist", "ammonizione"]]


def simulato(cubo, ruolo: dict, squadra: dict, s: int) -> pd.DataFrame:
    righe = []
    for gi, g in enumerate(cubo.giornate):
        idx = np.nonzero(cubo.gioca[s, gi])[0]
        for i in idx:
            pid = cubo.giocatori[i]
            righe.append((g, pid, ruolo.get(pid, "C"), squadra.get(pid, ""),
                          float(cubo.fantavoto[s, gi, i]),
                          float(cubo.voto[s, gi, i]),
                          float(cubo.gol[s, gi, i]),
                          float(cubo.assist[s, gi, i]),
                          float(cubo.ammonizione[s, gi, i])))
    return pd.DataFrame(righe, columns=["giornata", "master_id", "ruolo",
                                        "squadra", "punti", "voto_puro",
                                        "gol", "assist", "ammonizione"])


def eventi_per_ruolo(d: pd.DataFrame) -> dict:
    """Totali di gol, assist e cartellini per ruolo: servono a capire da dove
    viene uno scarto sui punti medi."""
    fuori = {}
    for ruolo in ("P", "D", "C", "A"):
        s = d[d.ruolo == ruolo]
        if not len(s):
            continue
        fuori[f"gol_{ruolo}"] = round(float(s.gol.sum()), 1)
        fuori[f"assist_{ruolo}"] = round(float(s.assist.sum()), 1)
        fuori[f"amm_{ruolo}"] = round(float(s.ammonizione.sum()), 1)
    fuori["gol_totali"] = round(float(d.gol.sum()), 1)
    fuori["assist_totali"] = round(float(d.assist.sum()), 1)
    return fuori


def riepilogo(d: pd.DataFrame) -> dict:
    r = {"righe": int(len(d)),
         "punti_medi": round(float(d.punti.mean()), 4),
         "punti_sd": round(float(d.punti.std()), 4),
         "voto_medio": round(float(d.voto_puro.mean()), 4),
         "voto_sd": round(float(d.voto_puro.std()), 4)}
    for q in (0.05, 0.25, 0.5, 0.75, 0.95):
        r[f"punti_q{int(q * 100)}"] = round(float(d.punti.quantile(q)), 3)
    for ruolo in ("P", "D", "C", "A"):
        s = d[d.ruolo == ruolo]
        if len(s):
            r[f"punti_medi_{ruolo}"] = round(float(s.punti.mean()), 4)
            r[f"voto_medio_{ruolo}"] = round(float(s.voto_puro.mean()), 4)
    r["presenze_per_giornata"] = round(float(len(d) / max(d.giornata.nunique(), 1)), 2)
    return r


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("stagione", nargs="?", default="2024-25")
    ap.add_argument("--sims", type=int, default=50)
    ap.add_argument("--seme", type=int, default=20260907)
    ap.add_argument("--as-of", default=None,
                    help="data limite; predefinita: primo giorno della stagione")
    ap.add_argument("--shock-residuo", type=float, default=None,
                    help="scarto del residuo comune ai compagni; se assente lo "
                         "misura dopo il condizionamento")
    ap.add_argument("--data-fit", default=None,
                    help="cutoff del fit: il panel deve essere stato costruito "
                         "con questo cutoff, altrimenti viene rifiutato. Senza, "
                         "si usa la vista osservativa e il cubo lo dichiara")
    ap.add_argument("--bersaglio-presenze", action="store_true",
                    help="modalita' sperimentale: la partecipazione riceve le "
                         "presenze del modello valore (il braccio C1 del banco). "
                         "Non e' il comportamento predefinito")
    ap.add_argument("--rose-da", choices=["listone", "squadra"],
                    default="listone",
                    help="fonte della squadra per costruire le rose: "
                         "`listone` = fotografia pre-campionato (predefinito), "
                         "`squadra` = squadra corrente all'ultimo scaricamento")
    ap.add_argument("--salva", action="store_true")
    ap.add_argument("--solo-future", action="store_true",
                    help="genera solo le giornate non ancora giocate alla data "
                         "limite: e' l'orizzonte vero di un'asta a campionato "
                         "iniziato")
    a = ap.parse_args()

    OUT.mkdir(parents=True, exist_ok=True)
    P, contratti_panel = carica_panel(data_fit=a.data_fit)
    print(f"  panel: {len(contratti_panel)} stagioni, vista "
          + (f"al fit del {a.data_fit}" if a.data_fit else "osservativa"))
    part = pd.read_parquet(PROC / "l2_partite.parquet")
    part["data"] = pd.to_datetime(part["data"])
    cal = part[part.stagione == a.stagione].copy()
    as_of = a.as_of or str(cal.data.min().date())
    cal_tutte = cal.copy()
    giocate = cal[cal.data < pd.Timestamp(as_of)]
    if a.solo_future:
        # Le giornate gia' concluse alla data limite sono informazione lecita,
        # ma NON vanno simulate: i punti gia' realizzati sono noti, non
        # aleatori. Il cubo genera solo il futuro; chi ha bisogno del totale di
        # stagione somma i punti osservati a quelli simulati, e chi ha bisogno
        # di una classifica gia' avviata deve fornirla, non inventarla.
        cal = cal[cal.data >= pd.Timestamp(as_of)]
    print(f"stagione {a.stagione} | as_of {as_of} | {a.sims} scenari")
    print(f"  calendario: {len(cal_tutte)} partite totali, "
          f"{len(giocate)} gia' giocate alla data limite, "
          f"{len(cal)} da generare"
          + ("" if a.solo_future else
             "  (senza --solo-future si generano anche le giornate gia' giocate: "
             "va bene per misurare la fedelta' su una stagione passata, NON per "
             "valutare una rosa comprata oggi)"))

    # --- stima dei quattro pezzi, tutto anteriore ad as_of ---
    t0 = time.time()
    # Il modello di partita si costruisce con l'UNICA procedura autorizzata,
    # la stessa che il banco usa per il candidato vincente. Prima questo script
    # scriveva a mano xi = 0,0015 e lam_pen = 2,0 senza prior, e generava un
    # modello diverso da quello dichiarato migliore: scarto medio 0,218 gol di
    # intensita' (16,7 %) sul calendario 2026-27, fino a 1,514.
    mp, conf, impronta = cfg.costruisci_modello_partita(
        # `squadre=None`: la procedura prende l'unione fra le squadre
        # dell'addestramento e quelle del calendario bersaglio. Passando solo
        # quelle del calendario si perdono le squadre storiche (Verona, Empoli,
        # ...) e la stima del prior dagli xG va in errore.
        part, as_of, squadre=None,
        stagione_bersaglio=a.stagione, con_incertezza=True,
        percorsi_ingresso=[str(PROC / "l2_partite.parquet")],
        etichetta=f"cubo {a.stagione}")
    print(f"  configurazione del modello: {impronta[:12]} | "
          f"xi {conf.iperparametri["xi"]} | "
          f"lam_pen {conf.iperparametri["lam_pen"]}")
    print(f"  partita: rho {mp.rho:+.4f}, vantaggio casa {mp.casa:.3f}, "
          f"gol ospite stimati {mp.diagnostica['gol_ospite_medi_stimati']:.4f} "
          f"contro {mp.diagnostica['gol_ospite_medi_osservati']:.4f} osservati")

    # l'universo serve prima della stima, perche' i bersagli delle presenze
    # devono coprirlo tutto e non solo chi ha storia
    rose, ruolo, squadra, diag_universo = contratto.costruisci_universo(
        PROC, a.stagione, rose_da=a.rose_da)
    Ppre = P[P.data < pd.Timestamp(as_of)]
    bersagli = None
    if a.bersaglio_presenze:
        bersagli = leggi_bersaglio_presenze(
            a.stagione, sorted(ruolo), ruolo,
            storia_voti=Ppre[["master_id", "stato_voto"]])
    m_part = pa.stima(
        Ppre,
        bersaglio_presenza=bersagli.per_giocatore if bersagli else None,
        ruolo_esterno=ruolo if bersagli else None)
    if bersagli:
        d = m_part.diagnostica.get("bersaglio_presenza") or {}
        print(f"  presenze applicate: {d.get('applicati')}, di cui "
              f"{d.get('iniziati_senza_storia')} iniziati senza storia; "
              f"{d.get('saltati_senza_ruolo')} saltati senza ruolo")
    m_ev = ev.stima(Ppre)
    m_voto = vt.stima(Ppre, "individuale")
    m_voto_sq = vt.stima(Ppre, "con_squadra")
    print(f"  partecipazione: {m_part.diagnostica['giocatori']} giocatori, "
          f"moduli per {m_part.diagnostica['squadre_con_moduli']} squadre")
    print(f"  eventi: quota rigori {m_ev.quota_rigori:.3f}, autogol "
          f"{m_ev.quota_autogol:.3f}, assist {m_ev.quota_assist:.3f}")
    print(f"  voto: varianza spiegata "
          f"{m_voto.diagnostica['varianza_spiegata']:.4f}, sigma {m_voto.sigma:.3f}")
    print(f"        gk_3piu_subiti = {m_voto.coef['gk_3piu_subiti']:+.4f} "
          f"(specificazione individuale) contro "
          f"{m_voto_sq.coef['gk_3piu_subiti']:+.4f} (con differenza reti): "
          "il segno dipende dalla specificazione, non dai dati")

    # minuti dei gol dalle partite storiche. Le partite di addestramento sono
    # le stesse che la procedura unica ha usato per il modello: si chiede a lei
    # invece di rifare a mano il filtro, che prima ignorava `stato_partita`.
    storico, _filtro = cfg.partite_di_addestramento(part, as_of)
    id_st = set(pd.to_numeric(storico.game_id, errors="coerce").dropna().astype(int))
    f_ev = ROOT / "data/raw/transfermarkt/_download/game_events.csv.gz"
    if f_ev.exists() and id_st:
        m_ev.minuti_gol = ev.minuti_gol_da_eventi(f_ev, id_st)
        print(f"  minuti dei gol: {len(m_ev.minuti_gol)} osservazioni, "
              f"mediana {np.median(m_ev.minuti_gol):.0f}'")

    # dipendenza residua misurata DOPO il condizionamento, scomposta in
    # componente di squadra e componente di reparto
    dip = vt.dipendenza_residua(Ppre, m_voto)
    print("  dipendenza fra compagni (prima -> dopo il condizionamento):")
    for k, v in dip.items():
        print(f"      {k:22s} {v['prima']:+.4f} -> {v['dopo']:+.4f}")
    struttura = vt.struttura_dipendenza(Ppre, m_voto)
    print(f"  residuo: squadra {struttura['sd_squadra']:.4f}, reparto "
          + ", ".join(f"{k} {v:.4f}" for k, v in struttura["sd_reparto"].items())
          + f", individuale {struttura['sd_individuale']:.4f}")
    fasce_sv = vt.stima_senza_voto(Ppre)
    print(f"  s.v.: quota complessiva {fasce_sv.get('quota_complessiva', 0):.4f} "
          f"su {fasce_sv.get('righe', 0)} righe con minuti noti")

    # --- rose: stessa costruzione che usa il banco ---
    #
    # La colonna `squadra` del listone viene aggiornata dalla fonte dopo lo
    # scaricamento: nel 2024-25 trenta giocatori hanno `squadra` diversa da
    # `squadra_listone`, sei nel 2026-27. Per un'asta pre-campionato quello e'
    # un aggiornamento che chi decide non ha. La scelta e' esplicita in
    # `--rose-da` e la funzione e' condivisa, cosi' banco e generatore non
    # possono divergere.
    print(f"  universo da `{diag_universo['colonna']}`: "
          f"{diag_universo['giocatori']} giocatori, "
          f"{diag_universo['squadre']} squadre, "
          f"{diag_universo['squadra_diversa_dal_listone']} con squadra diversa "
          "dal listone")
    mancanti = [sq for sq in set(cal.casa) if sq not in rose]
    if mancanti:
        print(f"  ATTENZIONE: squadre del calendario senza rosa: {mancanti}")
    m_part.ruolo.update(ruolo)
    m_ev.ruolo.update(ruolo)
    mancanti = [sq for sq in set(cal.casa) if sq not in rose]
    if mancanti:
        print(f"  ATTENZIONE: squadre del calendario senza rosa nel listone: {mancanti}")
    print(f"  rose: {len(rose)} squadre, {sum(len(v) for v in rose.values())} giocatori")
    print(f"  stima completata in {time.time() - t0:.1f} s")

    # --- calibrazione della dipendenza sui dati di addestramento ---
    oss_tr = osservato(Ppre, None) if False else None
    tr = Ppre[Ppre.stato_voto == "con_voto"].copy()
    tr["punti"] = pd.to_numeric(tr["fantavoto"], errors="coerce")
    tr["voto_puro"] = pd.to_numeric(tr["voto"], errors="coerce")
    tr["squadra"] = tr["squadra_alla_data"]
    tr["ruolo"] = tr["ruolo"].astype(str).str.upper()
    # nome distinto da `bersagli` delle presenze: sono due cose diverse e la
    # collisione faceva sparire la diagnostica dell'adattatore dal rapporto
    bersagli_corr = {}
    for st_tr, sub in tr.groupby("stagione"):
        c = correlazioni_compagni(sub, "voto_puro")
        for k, v in c.items():
            bersagli_corr.setdefault(k, []).append(v)
    bersagli_corr = {k: float(np.nanmean(v)) for k, v in bersagli_corr.items()}
    print("  bersagli di correlazione (media sulle stagioni di addestramento): "
          + ", ".join(f"{k} {v:.4f}" for k, v in bersagli_corr.items()))
    struttura = gen.calibra_dipendenza(struttura, bersagli_corr, cal, rose, mp,
                                       m_part, m_ev, m_voto, fasce_sv,
                                       a.seme, ruolo, squadra)
    print("  dopo la calibrazione: squadra "
          f"{struttura['sd_squadra']:.4f}, reparto "
          + ", ".join(f"{k} {v:.4f}" for k, v in struttura["sd_reparto"].items())
          + f", individuale {struttura['sd_individuale']:.4f}")
    for i, g in enumerate(struttura["calibrazione"]["correlazioni_per_giro"]):
        print(f"    giro {i + 1}: {g}")

    # --- generazione ---
    t0 = time.time()
    cubo = gen.genera(cal, rose, mp, m_part, m_ev, m_voto, n_sims=a.sims,
                      seme=a.seme, dipendenza=struttura, fasce_sv=fasce_sv)
    print(f"\ncubo generato in {time.time() - t0:.1f} s "
          f"({a.sims} scenari x {len(cubo.giornate)} giornate x "
          f"{len(cubo.giocatori)} giocatori)")
    nc = cubo.diagnostica["n_problemi_coerenza"]
    print(f"coerenza dei tabellini (prime 20 partite del primo scenario): "
          f"{nc} problemi" + (f" -> {cubo.diagnostica['problemi_coerenza'][:3]}"
                              if nc else ""))

    # --- confronto con l'osservato ---
    oss = osservato(P, a.stagione)
    giornate_oss = int(oss.giornata.nunique()) if len(oss) else 0
    confrontabile = giornate_oss >= 20
    rapporto = {"stagione": a.stagione, "as_of": as_of, "sims": a.sims,
                "data_fit": a.data_fit,
                "contratti_panel": contratti_panel,
                "bersaglio_presenze": bool(a.bersaglio_presenze),
                "adattatore_presenze": (bersagli.diagnostica
                                        if bersagli else None),
                "configurazione_modello": impronta,
                "iperparametri": dict(conf.iperparametri),
                "universo": diag_universo,
                "solo_future": bool(a.solo_future),
                "giornate_generate": int(cal.giornata.nunique()),
                "giornate_gia_giocate": int(giocate.giornata.nunique()),
                "giornate_osservate_con_voti": giornate_oss,
                "totali_confrontabili": bool(confrontabile),
                "seme": a.seme, "struttura_dipendenza": struttura,
                "fasce_senza_voto": fasce_sv,
                "dipendenza_residua_stimata": dip,
                "voto_coef_individuale": {k: round(float(v), 4)
                                          for k, v in m_voto.coef.items()},
                "voto_coef_con_squadra": {k: round(float(v), 4)
                                          for k, v in m_voto_sq.coef.items()},
                "partita": {k: (round(v, 4) if isinstance(v, float) else v)
                            for k, v in mp.diagnostica.items()},
                "eventi": m_ev.diagnostica,
                "partecipazione": m_part.diagnostica,
                "coerenza_problemi": cubo.diagnostica["problemi_coerenza"]}
    if len(oss) and not confrontabile:
        print(f"\nATTENZIONE: la stagione osservata ha solo {giornate_oss} "
              "giornate con voti. Medie e correlazioni per riga restano "
              "confrontabili; i TOTALI di stagione no, e non vanno letti.")
    if len(oss):
        r_oss = riepilogo(oss)
        corr_oss = correlazioni_compagni(oss, "voto_puro")
        sims = [simulato(cubo, ruolo, squadra, s) for s in range(min(a.sims, 10))]
        r_sim = {k: float(np.mean([riepilogo(x)[k] for x in sims]))
                 for k in r_oss}
        corr_sim = {k: float(np.nanmean([correlazioni_compagni(x, "voto_puro")[k]
                                         for x in sims[:5]]))
                    for k in corr_oss}
        print("\nconfronto simulato / osservato "
              f"(media su {len(sims)} scenari)")
        print(f"{'quantita':28s} {'osservato':>10s} {'simulato':>10s} {'scarto':>9s}")
        for k in r_oss:
            print(f"{k:28s} {r_oss[k]:10.3f} {r_sim[k]:10.3f} "
                  f"{r_sim[k] - r_oss[k]:+9.3f}")
        e_oss = eventi_per_ruolo(oss)
        e_sim = {k: float(np.mean([eventi_per_ruolo(x)[k] for x in sims]))
                 for k in e_oss}
        print("\neventi (totali di stagione)"
              + ("" if confrontabile else
                 f"  -- NON CONFRONTABILI: osservate {giornate_oss} giornate "
                 f"su {len(cal_tutte) // 10}"))
        for k in e_oss:
            print(f"{k:28s} {e_oss[k]:10.1f} {e_sim[k]:10.1f} "
                  f"{e_sim[k] - e_oss[k]:+9.1f}")
        rapporto["eventi_osservati"] = e_oss
        rapporto["eventi_simulati"] = {k: round(v, 1) for k, v in e_sim.items()}
        print("\ncorrelazione fra compagni sul voto puro")
        for k in corr_oss:
            print(f"{k:28s} {corr_oss[k]:10.4f} {corr_sim[k]:10.4f} "
                  f"{corr_sim[k] - corr_oss[k]:+9.4f}")
        rapporto["osservato"] = r_oss
        rapporto["simulato"] = r_sim
        rapporto["correlazioni_osservate"] = corr_oss
        rapporto["correlazioni_simulate"] = {k: round(v, 4)
                                             for k, v in corr_sim.items()}
    else:
        print("\nstagione senza voti osservati: confronto non possibile "
              "(atteso per la stagione in corso)")

    (OUT / f"cubo_rapporto_{a.stagione}.json").write_text(
        json.dumps(rapporto, indent=1, default=str), encoding="utf-8")
    if a.salva:
        with open(OUT / f"cubo_{a.stagione}.pkl", "wb") as f:
            pickle.dump({"cubo": cubo, "ruolo": ruolo, "squadra": squadra,
                         "as_of": as_of, "seme": a.seme}, f)
        print(f"\nsalvato cubo_{a.stagione}.pkl")
    print(f"scritto cubo_rapporto_{a.stagione}.json")
    return 0


if __name__ == "__main__":
    sys.exit(main())
