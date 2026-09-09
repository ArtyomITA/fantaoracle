"""Prova controfattuale sul VERO produttore C2: il futuro non deve entrare.

## Che cosa prova, e che cosa no

La prova esercita `l2_pilota_c2.costruisci_ingressi`, cioe' **la funzione che
il pilota usa davvero**. La versione precedente ricostruiva una copia della
catena: poteva restare verde mentre il produttore cambiava, e confrontava
*somme*, che nascondono gli scambi fra giocatori — due bersagli che si
scambiano di posto danno la stessa somma. Adesso il confronto e' per
identificativo, elemento per elemento.

## Perche' servono controlli positivi per dipendenza

Dire «alterando il futuro la grandezza X non cambia» non vale niente se X non
puo' cambiare comunque. Serve mostrare che la prova ha **potenza** su X: che
esiste una perturbazione della *sua* sorgente che la muove.

E la sorgente va scelta giusta. La versione precedente alterava i ruoli nel
panel aspettandosi di muovere il bersaglio, ma `presenze.costruisci` riceve
solo `master_id` e `stato_voto` dal panel e prende il ruolo dalla mappa
esterna: quella perturbazione non poteva arrivare al consumatore. Chiamarla
«mancanza di potenza dei dati» era sbagliato — era una perturbazione mal
indirizzata.

Qui ogni grandezza dichiara le proprie dipendenze, e ognuna viene perturbata
alla sorgente. Se una dipendenza dichiarata non muove la grandezza, la prova
**fallisce**: o la dichiarazione e' sbagliata, o il codice non usa quell'
ingresso.

## Codice d'uscita

`0` solo se: il futuro non muove niente, e ogni dipendenza dichiarata ha
potenza. Altrimenti diverso da zero.
"""
from __future__ import annotations

import argparse
import importlib.util
import json

import sys
import tempfile
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from fantabot.tabellino import contratto                      # noqa: E402

_spec = importlib.util.spec_from_file_location(
    "l2_pilota_c2", ROOT / "scripts" / "l2_pilota_c2.py")
pilota = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = pilota
_spec.loader.exec_module(pilota)

PROC = ROOT / "data" / "processed"

# Dipendenze DICHIARATE di ogni grandezza prodotta. Ognuna dev'essere
# verificata sulla propria sorgente: costringere una grandezza indipendente dal
# panel a dipendere dal panel non prova niente su di lei.
DIPENDENZE = {
    "bersaglio_grezzo": ["predizioni"],
    "bersaglio_obiettivo": ["predizioni", "mappa_ruoli", "mappa_squadre",
                            "panel_anteriore"],
    "somme_ruolo": ["panel_anteriore"],
    "quota_ruolo": ["panel_anteriore"],
    "universo": ["insieme_giocatori"],
    "mappa_ruoli": ["mappa_ruoli", "insieme_giocatori"],
    "mappa_squadre": ["mappa_squadre", "insieme_giocatori"],
    "righe_fit": ["panel_anteriore"],
    "squadre_scelte": ["predizioni", "mappa_ruoli", "mappa_squadre"],
    "parametri": ["predizioni", "mappa_ruoli", "mappa_squadre",
                  "insieme_giocatori"],
}

# `bersaglio_grezzo` dipende **solo** dalle predizioni, e questo va misurato,
# non assunto: `presenze.costruisci` userebbe la storia dei voti e la mappa dei
# ruoli per un prior, ma solo per i giocatori che il JSON non copre. Nel
# 2024-25 il JSON copre 679 giocatori su 679, quindi quel ramo non si attiva
# mai e le due dipendenze sono inerti **per questo esperimento**.
#
# Non e' un difetto del codice: e' il fatto che conta. Tutto il bersaglio viene
# dall'ingresso di cui la disponibilita' temporale non e' dimostrata, e
# nessuna informazione anteriore al cutoff lo tempera. La prova lo misura ogni
# volta (`copertura_predizioni`) e aggiunge le due dipendenze quando il prior
# torna attivo.
DIPENDENZE_SE_PRIOR_ATTIVO = {
    "bersaglio_grezzo": ["mappa_ruoli", "panel_anteriore"],
}


def differenze(a: dict, b: dict) -> dict:
    """Confronto per identificativo, non per somma.

    Per ogni grandezza riporta quante voci differiscono e le prime che
    differiscono, cosi' che uno scambio fra due giocatori risulti visibile.
    """
    fuori = {}
    for k in sorted(set(a) | set(b)):
        x, y = a.get(k), b.get(k)
        if x == y:
            continue
        if isinstance(x, dict) and isinstance(y, dict):
            chiavi = sorted(set(x) | set(y), key=str)
            div = [c for c in chiavi if x.get(c) != y.get(c)]
            fuori[k] = {"voci_diverse": len(div), "su": len(chiavi),
                        "esempi": [{"chiave": str(c), "prima": x.get(c),
                                    "dopo": y.get(c)} for c in div[:3]]}
        elif isinstance(x, list) and isinstance(y, list):
            fuori[k] = {"lunghezza_prima": len(x), "lunghezza_dopo": len(y),
                        "voci_diverse": len(set(map(str, x)) ^ set(map(str, y))),
                        "esempi": sorted(set(map(str, x)) ^ set(map(str, y)))[:3]}
        else:
            fuori[k] = {"prima": x, "dopo": y}
    return fuori


def _universo_con_ruoli_ruotati(universo):
    rose, ruolo, squadra, resto = universo
    giro = {"P": "D", "D": "C", "C": "A", "A": "P"}
    nuovo = {k: giro.get(str(v).upper(), v) for k, v in ruolo.items()}
    return (rose, nuovo, squadra, resto)


def _universo_con_squadre_mescolate(universo):
    """Rimescola l'appartenenza, **non** ruota le etichette.

    Ruotare i nomi delle squadre lascia la partizione dei giocatori identica:
    tutti quelli della squadra X finiscono insieme in Y. Le celle
    `(squadra, ruolo)` restano le stesse e nulla si muove — una perturbazione
    che non prova niente. Qui i giocatori vengono ridistribuiti, cosi' le celle
    cambiano davvero composizione.
    """
    rose, ruolo, squadra, resto = universo
    ids = sorted(squadra)
    valori = [squadra[i] for i in ids]
    rng = np.random.default_rng(20260909)
    nuovo = {i: valori[j] for i, j in zip(ids, rng.permutation(len(ids)))}
    return (rose, ruolo, nuovo, resto)


def _universo_ridotto(universo, quanti: int = 40):
    """Toglie giocatori dall'universo: la sorgente di `universo` e `parametri`."""
    rose, ruolo, squadra, resto = universo
    fuori = set(sorted(ruolo)[:quanti])
    return (rose, {k: v for k, v in ruolo.items() if k not in fuori},
            {k: v for k, v in squadra.items() if k not in fuori}, resto)


def copertura_predizioni(stagione: str, giocatori) -> dict:
    """Quanti giocatori dell'universo hanno una previsione nel JSON.

    Determina se il ramo del prior di ruolo si attiva: dove il JSON copre
    tutto, la storia dei voti e la mappa dei ruoli non toccano il bersaglio
    grezzo, e dirlo dipendente da loro sarebbe falso.
    """
    fonte = PROC / f"b_predictions_{stagione}.json"
    if not fonte.exists():
        return {"file": str(fonte), "esiste": False}
    crudo = json.loads(fonte.read_text(encoding="utf-8"))
    chiavi = set()
    for k, v in crudo.items():
        if isinstance(v, dict) and v.get("pres") is not None:
            try:
                chiavi.add(int(k))
            except (TypeError, ValueError):
                pass
    u = {int(x) for x in giocatori}
    return {"file": str(fonte), "esiste": True, "universo": len(u),
            "con_previsione": len(u & chiavi), "senza_previsione": len(u - chiavi),
            "prior_attivo": bool(u - chiavi)}


def _proc_con_predizioni_perturbate(stagione: str, scratch: Path) -> Path:
    """Copia il solo JSON delle predizioni, con i valori mescolati.

    Mescolare invece di riscalare: una traslazione comune potrebbe lasciare
    invariata la selezione delle squadre, e allora il controllo positivo su
    `squadre_scelte` non avrebbe potenza per un motivo che non riguarda il
    codice.
    """
    fonte = PROC / f"b_predictions_{stagione}.json"
    dati = json.loads(fonte.read_text(encoding="utf-8"))

    def mescola(dati):
        # PERMUTAZIONE del campo `pres` fra giocatori, non trasformazione
        # affine: `x -> a*x + b` con `a > 0` conserva l'ordine, quindi la
        # squadra con la somma dei portieri piu' alta resta la stessa e il
        # controllo positivo su `squadre_scelte` non avrebbe potenza — per un
        # motivo che non riguarda il codice.
        chiavi = [k for k, v in dati.items()
                  if isinstance(v, dict) and v.get("pres") is not None]
        valori = [dati[k]["pres"] for k in chiavi]
        rng = np.random.default_rng(20260909)
        permutati = [valori[j] for j in rng.permutation(len(valori))]
        fuori = {k: (dict(v) if isinstance(v, dict) else v)
                 for k, v in dati.items()}
        for k, v in zip(chiavi, permutati):
            fuori[k]["pres"] = v
        return fuori

    dest = scratch / "processed"
    dest.mkdir(parents=True, exist_ok=True)
    (dest / f"b_predictions_{stagione}.json").write_text(
        json.dumps(mescola(dati), ensure_ascii=False), encoding="utf-8")
    return dest


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("stagione", nargs="?", default="2024-25")
    ap.add_argument("--cutoff", default=None,
                    help="per difetto la prima partita della stagione")
    ap.add_argument("--modo-bersaglio", default="riferimento",
                    choices=["riferimento", "vincolo"])
    ap.add_argument("--peso-bersaglio", type=float, default=0.5)
    ap.add_argument("--n-squadre", type=int, default=1)
    ap.add_argument("--fuori", default=None,
                    help="dove scrivere l'artefatto; per difetto "
                         "data/l2/prove/c2_controfattuale_<stagione>.json")
    a = ap.parse_args()

    P, _ = contratto.carica_panel_multi(PROC, pilota.STAGIONI_PANEL,
                                        data_fit=None)
    P["data"] = pd.to_datetime(P["data"])
    if a.cutoff:
        cutoff = pd.Timestamp(a.cutoff)
    else:
        part = pd.read_parquet(PROC / "l2_partite.parquet")
        part["data"] = pd.to_datetime(part["data"])
        righe = part[part.stagione == a.stagione]
        if righe.empty:
            print(f"stagione {a.stagione} assente da l2_partite.parquet")
            return 2
        cutoff = righe.data.min()

    universo = contratto.costruisci_universo(PROC, a.stagione)
    comune = dict(stagione=a.stagione, cutoff=cutoff,
                  modo_bersaglio=a.modo_bersaglio,
                  peso_bersaglio=a.peso_bersaglio, n_squadre=a.n_squadre)

    def ingressi(panel=P, proc=PROC, univ=universo):
        return pilota.costruisci_ingressi(panel, proc=proc, universo=univ,
                                          **comune).vettori()

    print(f"stagione {a.stagione}, cutoff {pd.Timestamp(cutoff).date()}")
    base = ingressi()
    print(f"grandezze prodotte: {len(base)}; "
          f"universo {len(base['universo'])} giocatori, "
          f"righe anteriori {base['righe_fit']}")

    cop = copertura_predizioni(a.stagione, base["universo"])
    dipendenze = {k: list(v) for k, v in DIPENDENZE.items()}
    if cop.get("prior_attivo"):
        for g, extra in DIPENDENZE_SE_PRIOR_ATTIVO.items():
            dipendenze[g] = sorted(set(dipendenze.get(g, [])) | set(extra))
        print(f"  predizioni: {cop['con_previsione']}/{cop['universo']} coperti, "
              f"{cop['senza_previsione']} dal prior di ruolo -> le dipendenze "
              "del bersaglio grezzo dal panel e dai ruoli sono ATTIVE")
    else:
        print(f"  predizioni: {cop['con_previsione']}/{cop['universo']} coperti. "
              "Il prior di ruolo non si attiva mai: il bersaglio grezzo viene "
              "TUTTO dal JSON, e nessuna informazione anteriore al cutoff lo "
              "tempera")

    # --- controllo negativo: il FUTURO non deve entrare -------------------
    dopo = P.copy()
    md = dopo.data >= cutoff
    dopo.loc[md, "stato_voto"] = "nessuna_riga"
    dopo.loc[md, "stato_convocazione"] = "escluso"
    dopo.loc[md, "fantavoto"] = 0.0
    dopo.loc[md, "ruolo"] = "A"
    diff_futuro = differenze(base, ingressi(panel=dopo))
    print(f"righe posteriori alterate: {int(md.sum())} -> "
          f"{'NESSUNA differenza' if not diff_futuro else 'DIFFERENZE: ' + str(sorted(diff_futuro))}")

    # --- controlli positivi, ciascuno sulla PROPRIA sorgente ---------------
    mosse: dict[str, set] = {}
    dettaglio = {}
    with tempfile.TemporaryDirectory(prefix="c2_contro_") as tmp:
        scratch = Path(tmp)
        prima = P.copy()
        mp = (prima.data < cutoff) & (prima.master_id % 2 == 0)
        prima.loc[mp, "stato_voto"] = "nessuna_riga"
        prima.loc[mp, "stato_convocazione"] = "escluso"
        meno_righe = P[~((P.data < cutoff) & (P.index % 7 == 0))]

        perturbazioni = {
            "panel_anteriore": [
                ("meta' dei giocatori senza voto prima del cutoff",
                 lambda: ingressi(panel=prima)),
                ("una riga anteriore su sette rimossa",
                 lambda: ingressi(panel=meno_righe)),
            ],
            "predizioni": [
                ("valori del JSON delle predizioni trasformati",
                 lambda: ingressi(
                     proc=_proc_con_predizioni_perturbate(a.stagione, scratch))),
            ],
            "mappa_ruoli": [
                ("ruoli ruotati P->D->C->A->P nella mappa esterna",
                 lambda: ingressi(univ=_universo_con_ruoli_ruotati(universo))),
            ],
            "mappa_squadre": [
                ("appartenenza alle squadre rimescolata",
                 lambda: ingressi(univ=_universo_con_squadre_mescolate(universo))),
            ],
            "insieme_giocatori": [
                ("40 giocatori tolti dall'universo",
                 lambda: ingressi(univ=_universo_ridotto(universo))),
            ],
        }
        for sorgente, prove in perturbazioni.items():
            for nome, fn in prove:
                d = differenze(base, fn())
                dettaglio[f"{sorgente}: {nome}"] = sorted(d)
                mosse.setdefault(sorgente, set()).update(d)
                print(f"  {sorgente:18s} {nome[:44]:46s} muove {sorted(d) or 'NIENTE'}")

    # --- la matrice: dipendenza dichiarata contro potenza osservata --------
    senza_potenza = {}
    for grandezza, sorgenti in dipendenze.items():
        mancanti = [s for s in sorgenti if grandezza not in mosse.get(s, set())]
        if mancanti:
            senza_potenza[grandezza] = mancanti

    if senza_potenza:
        print("\nDIPENDENZE DICHIARATE SENZA POTENZA "
              "(o la dichiarazione e' sbagliata, o il codice non usa l'ingresso):")
        for g, s in sorted(senza_potenza.items()):
            print(f"  {g}: nessuna reazione a {s}")

    esito = (not diff_futuro) and (not senza_potenza)
    print("\nPASSATO" if esito else "\nFALLITO")

    fuori = Path(a.fuori) if a.fuori else (
        ROOT / "data" / "l2" / "prove" / f"c2_controfattuale_{a.stagione}.json")
    fuori.parent.mkdir(parents=True, exist_ok=True)
    fuori.write_text(json.dumps({
        "stagione": a.stagione, "cutoff": str(pd.Timestamp(cutoff).date()),
        "produttore": "l2_pilota_c2.costruisci_ingressi",
        "impronta_produttore": _impronta(ROOT / "scripts" / "l2_pilota_c2.py"),
        "grandezze": sorted(base), "dipendenze_dichiarate": dipendenze,
        "copertura_predizioni": cop,
        "righe_posteriori_alterate": int(md.sum()),
        "differenze_col_futuro_alterato": diff_futuro,
        "potenza_per_perturbazione": dettaglio,
        "grandezze_mosse_per_sorgente": {k: sorted(v) for k, v in mosse.items()},
        "dipendenze_senza_potenza": senza_potenza,
        "nota": ("il confronto e' per identificativo, non per somma. Una voce "
                 "in `dipendenze_senza_potenza` significa che perturbare quella "
                 "sorgente non muove quella grandezza: la prova non dice niente "
                 "su di lei, e la dichiarazione va corretta o il codice va "
                 "guardato."),
        "passato": esito},
        ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"scritto in {fuori}")
    return 0 if esito else 1


def _impronta(percorso: Path) -> str:
    import hashlib
    return hashlib.sha256(Path(percorso).read_bytes()).hexdigest()[:16]


if __name__ == "__main__":
    raise SystemExit(main())
