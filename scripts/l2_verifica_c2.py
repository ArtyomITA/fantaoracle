"""Valutazione del candidato `C2` congelato: invarianti, dipendenze, rose.

Il pilota misura la distanza dai bersagli. Questo misura quello che **non deve
degradare**: se il cubo esiste per gli scenari congiunti, le dipendenze fra
compagni e la distribuzione dei punti di una rosa, calibrare le marginali non
può romperli.

Il candidato arriva **congelato**: `theta` si legge dall'artefatto del pilota,
non si ricalcola. Chi vuole un altro candidato rifà il pilota.

## Che cosa si guarda

| voce | perché |
|---|---|
| problemi di coerenza del generatore | un portiere sempre, undici in campo, espulsi non sostituiti |
| voti per squadra-giornata, per ruolo | il vincolo congiunto che la calibrazione tocca da vicino |
| correlazioni fra compagni | la ragione per cui il cubo esiste: portiere-difensori, difensori, centrocampisti, attaccanti |
| distribuzione dei punti di rose fissate prima | metrica congiunta, non marginale: rose estratte **prima** di guardare i risultati |
| modificatore di difesa | dipende dai voti dei difensori insieme, non uno per uno |

Tutto su semi **separati** da quelli dell'ottimizzazione e del monitoraggio.
"""
from __future__ import annotations

import argparse
import datetime
import importlib.util
import json
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from fantabot.tabellino import configurazione as cfg          # noqa: E402
from fantabot.tabellino import contratto                      # noqa: E402
from fantabot.tabellino import esecuzione as esec             # noqa: E402
from fantabot.tabellino import eventi as ev                   # noqa: E402
from fantabot.tabellino import generatore as gen              # noqa: E402
from fantabot.tabellino import partecipazione as pa           # noqa: E402
from fantabot.tabellino import presenze                       # noqa: E402
from fantabot.tabellino import voto as vt                     # noqa: E402

_spec = importlib.util.spec_from_file_location(
    "l2_pilota_c2", ROOT / "scripts" / "l2_pilota_c2.py")
pilota = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = pilota
_spec.loader.exec_module(pilota)

PROC = ROOT / "data" / "processed"
OUT = ROOT / "data" / "l2"
STAGIONI_PANEL = ["2021-22", "2022-23", "2023-24", "2024-25", "2025-26"]

_spec = importlib.util.spec_from_file_location(
    "l2_banco_confronto", ROOT / "scripts" / "l2_banco_confronto.py")
banco = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(banco)


def coincidenza_col_candidato(dett, piano, ing, stagione: str) -> dict:
    """Gli ingressi di adesso sono quelli a cui `theta` si riferisce?

    Applicare `theta` a una base rifatta con altri dati non e' una verifica
    dello stesso candidato: e' un esperimento di trasferimento, e va chiamato
    cosi'. Qui si confrontano tre cose, per identificativo e non per somma:

    1. le impronte dei file di dati registrate dal pilota;
    2. il bersaglio grezzo e quello trasformato, giocatore per giocatore;
    3. l'insieme dei parametri.

    I moduli sono confrontati a parte: cambiarli puo' cambiare la base anche a
    dati identici, ma non tutti i moduli entrano in `theta`, quindi una loro
    differenza si segnala senza far fallire da sola.
    """
    v = ing.vettori()
    fuori = {"file_diversi": [], "moduli_diversi": [], "bersaglio_grezzo": None,
             "bersaglio_obiettivo": None, "parametri": None}

    attese = dict(piano["piano"].get("impronte_ingressi") or {})
    adesso = esec.impronte_ingressi(
        percorsi=[PROC / f"players_{stagione}.parquet",
                  PROC / "l2_partite.parquet",
                  PROC / f"b_predictions_{stagione}.json"],
        moduli=esec.MODULI_RILEVANTI)
    for k, atteso in attese.items():
        ora = adesso.get(k)
        if ora is None:
            continue
        if ora != atteso:
            voce = {"chiave": k, "allora": atteso[:16], "adesso": ora[:16]}
            (fuori["moduli_diversi"] if "/" not in k and "\\" not in k
             else fuori["file_diversi"]).append(voce)

    for colonna, chiave in (("bersaglio_grezzo", "bersaglio_grezzo"),
                            ("bersaglio_obiettivo", "bersaglio_obiettivo")):
        if colonna not in dett.columns:
            continue
        allora = {int(r.master_id): float(getattr(r, colonna))
                  for r in dett.itertuples()}
        ora = v[chiave]
        div = [i for i in allora
               if abs(allora[i] - float(ora.get(i, float("nan")))) > 1e-9
               or i not in ora]
        fuori[colonna] = {"confrontati": len(allora), "diversi": len(div),
                          "esempi": [{"master_id": i, "allora": allora[i],
                                      "adesso": ora.get(i)} for i in div[:3]]}

    ids_allora = sorted(int(x) for x in dett.master_id)
    ids_ora = sorted(int(x) for x in v["parametri"])
    fuori["parametri"] = {"allora": len(ids_allora), "adesso": len(ids_ora),
                          "solo_allora": sorted(set(ids_allora) - set(ids_ora))[:5],
                          "solo_adesso": sorted(set(ids_ora) - set(ids_allora))[:5]}

    stessi_ingressi = (
        not fuori["file_diversi"]
        and ids_allora == ids_ora
        and all((fuori[c] or {"diversi": 0})["diversi"] == 0
                for c in ("bersaglio_grezzo", "bersaglio_obiettivo")))
    fuori["stessi_ingressi"] = bool(stessi_ingressi)
    fuori["verdetto"] = (
        "stesso candidato: ingressi identici a quelli dell'esperimento"
        if stessi_ingressi else
        "TRASFERIMENTO: gli ingressi non coincidono, `theta` viene applicato a "
        "una base diversa da quella su cui e' stato trovato")
    return fuori


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("candidato", help="cartella dell'esecuzione del pilota")
    ap.add_argument("stagione", nargs="?", default="2024-25")
    ap.add_argument("--sims", type=int, default=16)
    ap.add_argument("--semi", type=int, default=3)
    ap.add_argument("--seme", type=int, default=20260910)
    ap.add_argument("--rose", type=int, default=10)
    ap.add_argument("--scenari-correlazioni", type=int, default=3,
                    help="scenari su cui si mediano le correlazioni: sono "
                         "meno di `--sims`, e il numero va dichiarato")
    ap.add_argument("--scenari-rose", type=int, default=6)
    ap.add_argument("--istante", default=None)
    ap.add_argument("--accetta-trasferimento", action="store_true",
                    help="esegue anche se gli ingressi non coincidono con "
                         "quelli dell'esperimento. L'artefatto lo dichiara: "
                         "non e' piu' una verifica dello stesso candidato.")
    a = ap.parse_args()

    cand = Path(a.candidato)
    dett = pd.read_csv(cand / f"c2_dettaglio_{a.stagione}.csv")
    piano = json.loads((cand / f"c2_pilota_{a.stagione}.json").read_text("utf-8"))
    theta = dict(zip(dett.master_id, dett.theta))
    semi_pilota = set(piano["semi"]["ottimizzazione"]) | set(
        piano["semi"]["monitoraggio"]) | set(piano["semi"]["verifica"])
    print(f"  candidato {piano['esecuzione']}, {len(theta)} parametri, "
          f"||theta|| {np.linalg.norm(list(theta.values())):.4f}")

    istante = a.istante or datetime.datetime.now().strftime("%Y%m%dT%H%M%S")
    corsa = esec.apri(OUT, a.stagione, {
        "script": "l2_verifica_c2", "stagione": a.stagione,
        "candidato": piano["esecuzione"], "sims": a.sims, "semi": a.semi,
        "seme": a.seme, "rose": a.rose,
        "impronte_ingressi": esec.impronte_ingressi(
            percorsi=[cand / f"c2_dettaglio_{a.stagione}.csv"],
            moduli=esec.MODULI_RILEVANTI),
        "impronta_script": esec.impronta_file(__file__)},
        istante=istante, prova=True)
    print(f"  destinazione: {corsa.cartella}")

    P, _ = contratto.carica_panel_multi(PROC, STAGIONI_PANEL, data_fit=None)
    P["data"] = pd.to_datetime(P["data"])
    part = pd.read_parquet(PROC / "l2_partite.parquet")
    part["data"] = pd.to_datetime(part["data"])
    cal = part[part.stagione == a.stagione].copy()
    cutoff = pd.Timestamp(piano["piano"]["cutoff"])
    as_of = str(cutoff.date())
    # gli ingressi vengono dalla stessa funzione che li costruisce nel pilota:
    # una copia qui potrebbe divergere in silenzio
    ing = pilota.costruisci_ingressi(
        P, stagione=a.stagione, cutoff=cutoff, proc=PROC,
        modo_bersaglio=piano["piano"]["modo_bersaglio"],
        peso_bersaglio=piano["piano"]["peso_bersaglio"],
        squadre=piano["piano"]["squadre"],
        n_squadre=piano["piano"]["n_squadre"])
    rose, ruolo, squadra = ing.rose, ing.ruolo, ing.squadra
    giocatori, Ppre, bers = ing.giocatori, ing.Ppre, ing.bers

    coincidenza = coincidenza_col_candidato(dett, piano, ing, a.stagione)
    print(f"  {coincidenza['verdetto']}")
    for voce in coincidenza["file_diversi"]:
        print(f"    file cambiato: {voce['chiave']} "
              f"{voce['allora']} -> {voce['adesso']}")
    for voce in coincidenza["moduli_diversi"]:
        print(f"    modulo cambiato: {voce['chiave']} "
              f"{voce['allora']} -> {voce['adesso']}")
    if not coincidenza["stessi_ingressi"] and not a.accetta_trasferimento:
        print("  Fermarsi e' la scelta giusta: chiamare questa una verifica "
              "del medesimo candidato sarebbe falso. Con "
              "`--accetta-trasferimento` si esegue lo stesso, e l'artefatto "
              "dichiara che e' un trasferimento.")
        return 3
    mp, _c, _i = cfg.costruisci_modello_partita(
        part, as_of, squadre=None, stagione_bersaglio=a.stagione,
        con_incertezza=True,
        percorsi_ingresso=[str(PROC / "l2_partite.parquet")],
        etichetta=f"verifica C2 {a.stagione}")
    m_part = pa.stima(Ppre, bersaglio_presenza=bers.per_giocatore,
                      ruolo_esterno=ruolo)
    m_part.ruolo.update(ruolo)
    m_ev = ev.stima(Ppre)
    m_ev.ruolo.update(ruolo)
    m_voto = vt.stima(Ppre, "individuale")
    struttura = vt.struttura_dipendenza(Ppre, m_voto)
    fasce_sv = vt.stima_senza_voto(Ppre)
    tr = Ppre[Ppre.stato_voto == "con_voto"].copy()
    tr["ruolo"] = tr["ruolo"].astype(str).str.upper()
    bc = {}
    for _, sub in tr.groupby("stagione"):
        for k, v in vt.correlazioni_osservate(sub, "voto").items():
            bc.setdefault(k, []).append(v)
    bc = {k: float(np.nanmean(v)) for k, v in bc.items()}
    struttura = gen.calibra_dipendenza(struttura, bc, cal, rose, mp, m_part,
                                       m_ev, m_voto, fasce_sv, a.seme,
                                       ruolo, squadra)

    lst = pd.DataFrame({"master_id": giocatori,
                        "ruolo": [ruolo[p] for p in giocatori]})
    rose_prova = banco.rose_di_prova(lst, a.rose, a.seme)

    semi = [a.seme + 999_983 * (i + 1) for i in range(a.semi)]
    assert not (set(semi) & semi_pilota), (
        "i semi di verifica coincidono con quelli del pilota: non sarebbero "
        "una verifica")
    print(f"  semi {semi}, disgiunti da quelli del pilota")

    base = {p: float(m_part.base_convocazione(p)) for p in theta}
    misure = {}
    for nome in ("C1", "C2"):
        righe = []
        for s in semi:
            vecchi = {}
            if nome == "C2":
                for pid, th in theta.items():
                    vecchi[pid] = m_part.logit_base_convocato.get(pid)
                    m_part.logit_base_convocato[pid] = base[pid] + float(th)
            try:
                t0 = time.time()
                c = gen.genera(cal, rose, mp, m_part, m_ev, m_voto,
                               n_sims=a.sims, seme=s, dipendenza=struttura,
                               fasce_sv=fasce_sv, verifica=True)
            finally:
                for pid, v in vecchi.items():
                    if v is None:
                        m_part.logit_base_convocato.pop(pid, None)
                    else:
                        m_part.logit_base_convocato[pid] = v
            ad = gen.riordina_cubo(c, giocatori, range(1, 39), a.sims)
            R = ad["riordina"]
            fv, vv, gi = R(c.fantavoto), R(c.voto), R(c.gioca)
            gs = R(c.gol_subiti) if getattr(c, "gol_subiti", None) is not None else None
            # scenari usati davvero: dichiararli, invece di lasciar credere
            # che siano tutti quelli generati
            n_corr = min(a.scenari_correlazioni, a.sims)
            n_rose = min(a.scenari_rose, a.sims)
            corr = {k: float(np.nanmean([
                banco.correlazioni(fv, vv, gi, giocatori, ruolo, squadra, x)[k]
                for x in range(n_corr)]))
                for k in ("portiere-difensori", "difensori",
                          "centrocampisti", "attaccanti")}
            punt = np.array([banco.punteggi_rose(rose_prova, fv, vv, gi,
                                                 giocatori, x, gol_subiti=gs,
                                                 ruolo=ruolo)
                             for x in range(n_rose)])
            # I voti per squadra-giornata vanno guardati SULLA SQUADRA
            # CALIBRATA: la media su tutte e venti diluisce venti volte un
            # effetto che per costruzione tocca una squadra sola.
            sq_cal = sorted({squadra.get(p) for p in theta} - {None})
            col_cal = [k for k, pid in enumerate(giocatori)
                       if squadra.get(pid) in sq_cal]
            n_sq_cal = max(len(sq_cal), 1)
            righe.append({
                "seme": s, "secondi": round(time.time() - t0, 1),
                "problemi_coerenza": int(c.diagnostica["n_problemi_coerenza"]),
                "voti_per_squadra_giornata": float(gi.sum() / (a.sims * 38 * 20)),
                "voti_squadra_calibrata": float(
                    gi[:, :, col_cal].sum() / (a.sims * 38 * n_sq_cal)),
                "rosa_punti_media": float(punt.mean()),
                "rosa_punti_sd": float(punt.std()),
                **{f"corr_{k}": v for k, v in corr.items()}})
        misure[nome] = pd.DataFrame(righe)

    tab = pd.concat([d.assign(braccio=n) for n, d in misure.items()],
                    ignore_index=True)
    corsa.scrivi_tabella(f"verifica_c2_repliche_{a.stagione}.csv", tab)

    colonne = [c for c in tab.columns if c not in ("seme", "braccio", "secondi")]
    confronto = {}
    for c in colonne:
        c1 = misure["C1"][c].to_numpy(float)
        c2 = misure["C2"][c].to_numpy(float)
        d = c2 - c1
        confronto[c] = {
            "C1": float(np.mean(c1)), "C2": float(np.mean(c2)),
            "differenza_media": float(np.mean(d)),
            "es_differenze": (float(np.std(d, ddof=1) / np.sqrt(len(d)))
                              if len(d) > 1 else float("nan"))}
    bersagli_corr = {f"corr_{k}": v for k, v in bc.items()}
    corsa.scrivi_json(f"verifica_c2_{a.stagione}.json", {
        "esecuzione": corsa.identificativo,
        "candidato": piano["esecuzione"], "semi": semi,
        "coincidenza_col_candidato": coincidenza,
        "e_una_verifica_dello_stesso_candidato": coincidenza["stessi_ingressi"],
        "scenari": a.sims, "rose": a.rose,
        "scenari_correlazioni": min(a.scenari_correlazioni, a.sims),
        "scenari_rose": min(a.scenari_rose, a.sims),
        "gradi_liberta": a.semi - 1,
        "t_critico_95": (4.303 if a.semi == 3 else None),
        "nota_precisione": (
            f"con {a.semi} semi l'errore standard ha {a.semi - 1} gradi di "
            "liberta': la soglia al 95 % e' t di Student, non 2. Con tre semi "
            "vale 4,303, e l'errore standard stimato e' esso stesso molto "
            "incerto."),
        "bersagli_correlazione_dal_fit": bersagli_corr,
        "confronto_appaiato": confronto,
        "nota": ("le rose di prova sono estratte prima di guardare i "
                 "risultati; i semi sono disgiunti da quelli del pilota.")})
    corsa.registra()

    print(f"\n{'grandezza':<28}{'C1':>10}{'C2':>10}{'d':>11}{'es(d)':>10}")
    for c, v in confronto.items():
        print(f"  {c:<26}{v['C1']:>10.4f}{v['C2']:>10.4f}"
              f"{v['differenza_media']:>11.4f}{v['es_differenze']:>10.4f}")
    print("\n  bersagli di correlazione dai dati ammessi: "
          + ", ".join(f"{k.replace('corr_','')} {v:.4f}"
                      for k, v in sorted(bersagli_corr.items())))
    print(f"\n  scritto in {corsa.cartella}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
