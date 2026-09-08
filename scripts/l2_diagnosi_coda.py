"""Scompone la variabilità della coda dei gol: parametri contro partite.

## La domanda

Il cubo produce una coda più grassa dell'osservato: P(≥6 gol per
squadra-partita) intorno all'1,60 % contro lo 0,465 % osservato. Da dove viene
l'eccesso?

La misura precedente confrontava la dispersione fra i 40 scenari del cubo e
concludeva che «la sovradispersione è fra scenari, non dentro». Quella
deduzione non è identificata: **ogni scenario del cubo è un campione di
parametri seguito da una sola realizzazione di partite**, quindi la variazione
fra scenari contiene le due cose sommate, e una singola realizzazione
favorevole non è una verifica di calibrazione (rettifica in
`reports/PROTOCOLLO_v2.md` §10.4).

## Il disegno che separa le due cose

Si campionano `M` insiemi di parametri dal modello di partita. Per ciascuno si
generano `R` realizzazioni indipendenti dello stesso calendario. Con questa
griglia la varianza della statistica si scompone:

- **dentro** un campione di parametri, fra le `R` repliche: è la variabilità di
  una futura stagione a modello noto;
- **fra** i campioni di parametri: è l'incertezza sui parametri;
- l'errore Monte Carlo della media stimata è quello della media di `M · R`
  osservazioni, tenendo conto della struttura a gruppi.

Il confronto con l'osservato usa lo stesso calendario e lo stesso numero di
partite, come nei controlli predittivi a posteriori: si calcola la stessa
statistica sui dati veri e sulle repliche del modello, e si guarda dove cade
quella osservata nella distribuzione delle replicate.

Quello che questo script **non** fa: non decide se il difetto sia nella
specificazione del modello o nell'incertezza dei parametri. Dice quanta parte
della variabilità viene da dove, e dove cade l'osservato. Il resto richiede
esperimenti sul modello, non su questa scomposizione.

Uso:
    python scripts/l2_diagnosi_coda.py --campioni 24 --repliche 24
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from fantabot.tabellino import configurazione as cfg          # noqa: E402
from fantabot.tabellino.partita import campiona_risultati     # noqa: E402

PROC = ROOT / "data" / "processed"
OUT = ROOT / "data" / "l2"


def statistiche(gol: np.ndarray) -> dict:
    """Le statistiche su cui si confrontano osservato e replicate."""
    return {
        "media": float(gol.mean()),
        "varianza": float(gol.var()),
        "p_zero": float((gol == 0).mean()),
        "p_sei_o_piu": float((gol >= 6).mean()),
        "massimo": int(gol.max()),
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--stagione", default="2026-27")
    ap.add_argument("--as-of", default="2026-09-11")
    ap.add_argument("--campioni", type=int, default=24,
                    help="M: insiemi di parametri estratti dall'incertezza")
    ap.add_argument("--repliche", type=int, default=24,
                    help="R: realizzazioni di partite per ogni campione")
    ap.add_argument("--seme", type=int, default=20260908)
    a = ap.parse_args()

    part = pd.read_parquet(PROC / "l2_partite.parquet")
    mp, conf, impronta = cfg.costruisci_modello_partita(
        part, a.as_of, squadre=None, stagione_bersaglio=a.stagione,
        con_incertezza=True,
        percorsi_ingresso=[str(PROC / "l2_partite.parquet")],
        etichetta=f"diagnosi coda {a.stagione}")
    cal = part[(part.stagione == a.stagione)]
    casa, tra = cal.casa.values, cal.trasferta.values
    n_part = len(cal)
    print(f"modello {impronta[:12]} | xi {conf.iperparametri['xi']} | "
          f"{n_part} partite del calendario {a.stagione}")

    rng = np.random.default_rng(a.seme)
    copie = mp.campiona_parametri(rng, a.campioni)

    # griglia M x R: per ogni campione di parametri, R realizzazioni dello
    # stesso calendario. I numeri casuali delle partite sono indipendenti fra
    # repliche e fra campioni: e' esattamente la struttura che serve a separare
    # le due sorgenti di variabilita'.
    coda = np.zeros((a.campioni, a.repliche))
    media = np.zeros((a.campioni, a.repliche))
    varianza = np.zeros((a.campioni, a.repliche))
    p0 = np.zeros((a.campioni, a.repliche))
    massimi = np.zeros((a.campioni, a.repliche))
    for m, c in enumerate(copie):
        lam, mu = c.intensita(casa, tra)
        r = campiona_risultati(lam, mu, c.rho, rng, n_sims=a.repliche)
        for k in range(a.repliche):
            g = r[k].ravel()
            coda[m, k] = float((g >= 6).mean())
            media[m, k] = float(g.mean())
            varianza[m, k] = float(g.var())
            p0[m, k] = float((g == 0).mean())
            massimi[m, k] = int(g.max())

    # anche il punto stimato, senza incertezza sui parametri: e' il termine di
    # confronto che dice quanto l'incertezza sposta la coda
    lam, mu = mp.intensita(casa, tra)
    r0 = campiona_risultati(lam, mu, mp.rho, rng, n_sims=a.repliche)
    coda0 = np.array([float((r0[k].ravel() >= 6).mean())
                      for k in range(a.repliche)])

    def scomponi(x: np.ndarray, nome: str) -> dict:
        """Varianza dentro e fra i campioni di parametri.

        `dentro` e' la media delle varianze fra repliche a parametri fissi;
        `fra` e' la varianza delle medie per campione, corretta per la parte di
        rumore che ci finisce dentro (stimatore classico della componente fra
        gruppi in un disegno bilanciato).
        """
        per_campione = x.mean(axis=1)
        dentro = float(x.var(axis=1, ddof=1).mean())
        fra_grezza = float(per_campione.var(ddof=1))
        fra = max(fra_grezza - dentro / x.shape[1], 0.0)
        tot = dentro + fra
        return {
            "nome": nome,
            "media": float(x.mean()),
            "sd_dentro_parametri_fissi": float(np.sqrt(dentro)),
            "sd_fra_campioni_di_parametri": float(np.sqrt(fra)),
            "quota_dovuta_ai_parametri": float(fra / tot) if tot > 0 else None,
            "sd_totale": float(np.sqrt(tot)),
            "errore_standard_della_media": float(
                np.sqrt(fra / x.shape[0] + dentro / (x.shape[0] * x.shape[1]))),
        }

    tr, filtro = cfg.partite_di_addestramento(part, a.as_of)
    oss = np.concatenate([tr.gol_casa.values.astype(int),
                          tr.gol_trasferta.values.astype(int)])
    ultime3 = sorted(s for s in tr.stagione.unique() if s != a.stagione)[-3:]
    u3 = tr[tr.stagione.isin(ultime3)]
    oss3 = np.concatenate([u3.gol_casa.values.astype(int),
                           u3.gol_trasferta.values.astype(int)])

    # dove cade l'osservato nella distribuzione delle replicate: e' la domanda
    # dei controlli predittivi, e non richiede un intervallo costruito a mano
    piatta = coda.ravel()
    def quantile_osservato(v: float) -> float:
        return float((piatta <= v).mean())

    fuori = {
        "stagione": a.stagione, "as_of": a.as_of, "seme": a.seme,
        "campioni_di_parametri": a.campioni, "repliche_per_campione": a.repliche,
        "partite_per_replica": int(n_part),
        "squadra_partita_per_replica": int(2 * n_part),
        "impronta_modello": impronta,
        "scomposizione": {
            "p_sei_o_piu": scomponi(coda, "P(>= 6 gol)"),
            "media_gol": scomponi(media, "media dei gol"),
            "varianza_gol": scomponi(varianza, "varianza dei gol"),
            "p_zero": scomponi(p0, "P(0 gol)"),
        },
        "punto_stimato_senza_incertezza": {
            "p_sei_o_piu_media": float(coda0.mean()),
            "p_sei_o_piu_sd": float(coda0.std(ddof=1)),
        },
        "osservato": {
            "tutte_le_stagioni": statistiche(oss),
            "stagioni": sorted(tr.stagione.unique().tolist()),
            "ultime_tre": {"stagioni": ultime3, **statistiche(oss3)},
        },
        "posizione_dell_osservato": {
            "quantile_p_sei_o_piu_tutte": quantile_osservato(
                float((oss >= 6).mean())),
            "quantile_p_sei_o_piu_ultime_tre": quantile_osservato(
                float((oss3 >= 6).mean())),
            "lettura": ("frazione di repliche del modello con coda non "
                        "superiore a quella osservata: vicino a 0 significa "
                        "che il modello produce quasi sempre code piu' grasse "
                        "del vero"),
        },
        "massimo_gol_per_replica": {
            "media": float(massimi.mean()), "minimo": int(massimi.min()),
            "massimo": int(massimi.max()),
        },
    }
    percorso = OUT / f"diagnosi_coda_{a.stagione}.json"
    percorso.write_text(json.dumps(fuori, indent=1), encoding="utf-8")

    print(f"\ngriglia {a.campioni} campioni di parametri x {a.repliche} "
          f"repliche = {a.campioni * a.repliche} stagioni simulate")
    for chiave, d in fuori["scomposizione"].items():
        print(f"\n{d['nome']}: media {d['media']:.5f}")
        print(f"   sd dentro (parametri fissi):  {d['sd_dentro_parametri_fissi']:.5f}")
        print(f"   sd fra campioni di parametri: {d['sd_fra_campioni_di_parametri']:.5f}")
        q = d["quota_dovuta_ai_parametri"]
        print(f"   quota della varianza dovuta ai parametri: "
              f"{q * 100:.1f}%" if q is not None else "   quota non definita")
    p = fuori["punto_stimato_senza_incertezza"]
    print(f"\npunto stimato senza incertezza: P(>=6) {p['p_sei_o_piu_media']:.5f} "
          f"(sd fra repliche {p['p_sei_o_piu_sd']:.5f})")
    o = fuori["osservato"]
    print(f"osservato, tutte le stagioni: P(>=6) "
          f"{o['tutte_le_stagioni']['p_sei_o_piu']:.5f}; "
          f"ultime tre: {o['ultime_tre']['p_sei_o_piu']:.5f}")
    q = fuori["posizione_dell_osservato"]
    print(f"quantile dell'osservato fra le repliche: "
          f"{q['quantile_p_sei_o_piu_tutte']:.4f} (tutte le stagioni), "
          f"{q['quantile_p_sei_o_piu_ultime_tre']:.4f} (ultime tre)")
    print(f"\nscritto {percorso}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
