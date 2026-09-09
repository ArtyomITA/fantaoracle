"""Il controllo temporale attraverso i consumatori veri, non solo il filtro.

## Che cosa prova, e che cosa non provava prima

La prova precedente passava per `righe_ammesse` e `pa.stima`: due consumatori
su molti. `adatta` ne usa altri — `cfg.costruisci_modello_partita` (che sceglie
gli iperparametri, applica i pesi di decadimento e stima i prior dagli xG),
`cfg.partite_di_addestramento`, `ev.stima`, `vt.stima`,
`vt.struttura_dipendenza`, `vt.stima_senza_voto` — e nessuno di quelli era
esercitato.

Qui si adatta **tutto** a un'origine, due volte:

1. con il panel intatto;
2. con le righe **posteriori** all'origine alterate.

Le due stime devono coincidere in ogni loro parte confrontabile. Se non
coincidono, qualcosa a valle sta guardando il futuro.

Poi una terza volta, con le righe **anteriori** alterate: lì la stima deve
cambiare, altrimenti la prima uguaglianza sarebbe soddisfatta anche da un
modello che ignora i dati.

## Che cosa questa prova NON copre

- le **predizioni esterne** (`b_predictions_*.json`): sono costruite a una data
  sola e non entrano in `adatta`. Restano una dipendenza aperta del braccio C1
  progressivo;
- l'**appartenenza** e l'universo: costruiti una volta sola dal listone, non
  per origine;
- la **provenienza temporale dei dati grezzi**: `disponibile_dal` è nulla al
  100 % nel panel, quindi non si può distinguere quando un dato è diventato
  disponibile da quando l'evento è accaduto. È un dato mancante, non
  ricostruibile: chi vuole quella garanzia deve procurarsi i tempi di
  pubblicazione, non dedurli.

`confidenza_fit == 'inferenza'` **non** prova anticipazione: un'inferenza può
usare solo prove pregresse. Il conteggio resta come descrizione, non come
misura di fuga temporale.

Uso:

    PYTHONPATH=src python scripts/l2_prova_temporale.py 2024-25 --origine 20
"""
from __future__ import annotations

import argparse
import datetime
import importlib.util
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from fantabot.tabellino import contratto                      # noqa: E402
from fantabot.tabellino import esecuzione as esec             # noqa: E402

PROC = ROOT / "data" / "processed"
OUT = ROOT / "data" / "l2"
STAGIONI_PANEL = ["2021-22", "2022-23", "2023-24", "2024-25", "2025-26"]

_spec = importlib.util.spec_from_file_location(
    "l2_progressivo", ROOT / "scripts" / "l2_progressivo.py")
prog = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(prog)


def impronta_modelli(m: dict) -> dict:
    """Riassunto confrontabile di un adattamento.

    Non si confrontano gli oggetti — non sono confrontabili — ma le quantità
    che il generatore poi usa. Se due adattamenti hanno queste identiche, la
    simulazione che ne segue è la stessa.
    """
    def sunto(d):
        """Riassunto numerico di un dizionario, anche se i valori sono liste.

        Alcuni modelli mappano una chiave su una lista (le fasce del senza
        voto, per esempio): si appiattisce, invece di fermarsi.
        """
        if not d:
            return None
        piatti = []
        for x in d.values():
            if isinstance(x, (list, tuple, np.ndarray)):
                piatti.extend(float(y) for y in np.ravel(np.asarray(x, float)))
            elif isinstance(x, dict):
                piatti.extend(float(y) for y in x.values()
                              if isinstance(y, (int, float)))
            elif isinstance(x, (int, float, np.floating, np.integer)):
                piatti.append(float(x))
        if not piatti:
            return {"n": len(d), "non_numerico": True}
        v = np.array(piatti, dtype=float)
        return {"n": int(len(v)), "somma": round(float(np.nansum(v)), 9),
                "media": round(float(np.nanmean(v)), 9),
                "min": round(float(np.nanmin(v)), 9),
                "max": round(float(np.nanmax(v)), 9)}

    mp, mpart, mev, mvoto = m["mp"], m["m_part"], m["m_ev"], m["m_voto"]
    fuori = {
        "impronta_modello_partita": m["impronta"],
        "xi": m["xi"],
        "partite_addestramento": m["partite_addestramento"],
        "righe_ammesse": m["diagnostica"]["righe"],
        "prop_convocato": sunto(getattr(mpart, "prop_convocato", None)),
        "prop_titolare": sunto(getattr(mpart, "prop_titolare", None)),
    }
    for nome, mod in (("eventi", mev), ("voto", mvoto)):
        for campo in ("media", "medie", "tassi", "quote", "sigma", "mu"):
            d = getattr(mod, campo, None)
            if isinstance(d, dict) and d:
                fuori[f"{nome}.{campo}"] = sunto(d)
    for campo in ("attacco", "difesa", "casa", "rho"):
        d = getattr(mp, campo, None)
        if isinstance(d, dict) and d:
            fuori[f"partita.{campo}"] = sunto(d)
        elif isinstance(d, (int, float)):
            fuori[f"partita.{campo}"] = round(float(d), 9)
    fuori["fasce_sv"] = sunto(
        m["fasce_sv"] if isinstance(m["fasce_sv"], dict) else None)
    return fuori


def confronta(a: dict, b: dict) -> list:
    """Le chiavi in cui i due adattamenti differiscono."""
    diverse = []
    for k in sorted(set(a) | set(b)):
        if a.get(k) != b.get(k):
            diverse.append(k)
    return diverse


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("stagione", nargs="?", default="2024-25")
    ap.add_argument("--origine", type=int, default=20)
    ap.add_argument("--seme", type=int, default=20260909)
    ap.add_argument("--prova", action="store_true", default=True)
    ap.add_argument("--istante", default=None)
    a = ap.parse_args()

    istante = a.istante or datetime.datetime.now().strftime("%Y%m%dT%H%M%S")
    corsa = esec.apri(OUT, a.stagione,
                      {"script": "l2_prova_temporale", "stagione": a.stagione,
                       "origine": a.origine, "seme": a.seme,
                       "impronte_ingressi": esec.impronte_ingressi(
                           percorsi=[PROC / "l2_partite.parquet"],
                           moduli=esec.MODULI_RILEVANTI),
                       "impronta_script": esec.impronta_file(__file__)},
                      istante=istante, prova=True)
    print(f"  destinazione: {corsa.cartella}")

    P, _ = contratto.carica_panel_multi(PROC, STAGIONI_PANEL, data_fit=None)
    P["data"] = pd.to_datetime(P["data"])
    part = pd.read_parquet(PROC / "l2_partite.parquet")
    part["data"] = pd.to_datetime(part["data"])
    cal = part[part.stagione == a.stagione].copy()
    rose, ruolo, squadra, _ = contratto.costruisci_universo(PROC, a.stagione)
    date = prog.date_origini(cal, [a.origine])
    as_of = date[a.origine]
    print(f"  origine g{a.origine} = {as_of.date()}")

    def adatta_con(panel, partite):
        return prog.adatta(panel, partite, cal, as_of, a.stagione, rose,
                           ruolo, squadra, a.seme)

    print("  1/3 adattamento sul panel intatto...")
    base = impronta_modelli(adatta_con(P, part))

    # --- perturbazione POSTERIORE all'origine ----------------------------
    dopo_p = P.copy()
    m_dopo = dopo_p["data"] >= as_of
    dopo_p.loc[m_dopo, "stato_voto"] = "nessuna_riga"
    dopo_p.loc[m_dopo, "stato_convocazione"] = "escluso"
    dopo_p.loc[m_dopo, "fantavoto"] = 0.0
    dopo_p.loc[m_dopo, "voto"] = 0.0
    dopo_part = part.copy()
    m_dp = dopo_part["data"] >= as_of
    for c in ("gol_casa", "gol_trasferta", "xg_casa", "xg_trasferta"):
        if c in dopo_part.columns:
            dopo_part.loc[m_dp, c] = 0.0
    print(f"  2/3 adattamento con {int(m_dopo.sum())} righe di panel e "
          f"{int(m_dp.sum())} partite POSTERIORI alterate...")
    dopo = impronta_modelli(adatta_con(dopo_p, dopo_part))

    # --- perturbazione ANTERIORE, pertinente ------------------------------
    prima_p = P.copy()
    m_prima = (prima_p["data"] < as_of) & (prima_p["stagione"] == a.stagione)
    meta = m_prima & (prima_p["master_id"] % 2 == 0)
    prima_p.loc[meta, "stato_convocazione"] = "escluso"
    prima_p.loc[meta, "stato_voto"] = "nessuna_riga"
    print(f"  3/3 adattamento con {int(meta.sum())} righe ANTERIORI alterate...")
    prima = impronta_modelli(adatta_con(prima_p, part))

    d_dopo = confronta(base, dopo)
    d_prima = confronta(base, prima)
    esito = {
        "origine": a.origine, "as_of": str(as_of.date()),
        "righe_posteriori_alterate": int(m_dopo.sum()),
        "partite_posteriori_alterate": int(m_dp.sum()),
        "righe_anteriori_alterate": int(meta.sum()),
        "chiavi_confrontate": len(base),
        "differenze_con_perturbazione_posteriore": d_dopo,
        "differenze_con_perturbazione_anteriore": d_prima,
        "passato": (not d_dopo) and bool(d_prima),
        "consumatori_attraversati": [
            "righe_ammesse", "cfg.costruisci_modello_partita",
            "cfg.partite_di_addestramento", "pa.stima", "ev.stima",
            "vt.stima", "vt.struttura_dipendenza", "vt.stima_senza_voto",
            "gen.calibra_dipendenza"],
        "non_coperti": [
            "b_predictions_*.json: costruite a una data sola, non entrano in "
            "`adatta`. Dipendenza aperta del braccio C1 progressivo.",
            "appartenenza e universo: costruiti una volta sola dal listone.",
            "provenienza temporale dei dati grezzi: `disponibile_dal` e' nulla "
            "al 100 % nel panel. Dato mancante, non ricostruibile."],
        "base": base, "dopo": dopo, "prima": prima,
    }
    corsa.scrivi_json(f"prova_temporale_{a.stagione}_g{a.origine}.json", esito)
    corsa.registra()

    print()
    print(f"  chiavi confrontate: {len(base)}")
    print(f"  perturbazione POSTERIORE: {len(d_dopo)} differenze "
          + (f"{d_dopo[:4]}" if d_dopo else "(nessuna, come deve essere)"))
    print(f"  perturbazione ANTERIORE:  {len(d_prima)} differenze "
          + (f"{d_prima[:4]}" if d_prima else "(NESSUNA: sospetto)"))
    print()
    if esito["passato"]:
        print("  PASSATO: il futuro non entra, il passato pertinente sì.")
    elif d_dopo:
        print("  FALLITO: alterare prove posteriori cambia l'adattamento. "
              "C'e' una fuga temporale in uno dei consumatori.")
    else:
        print("  FALLITO: alterare prove anteriori non cambia niente. "
              "L'adattamento non usa i dati che dice di usare.")
    print(f"\n  scritto in {corsa.cartella}")
    return 0 if esito["passato"] else 1


if __name__ == "__main__":
    sys.exit(main())
