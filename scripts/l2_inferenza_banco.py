"""Rifà l'inferenza del banco dalle osservazioni conservate, senza rigenerare.

## A che serve

Il banco conserva i punteggi per osservazione con l'identità di giocatore,
partita e data (`banco_osservazioni_{stagione}.parquet`) e le medie per seme di
ogni braccio (`banco_semi_{stagione}.json`). Con quei due file l'inferenza si
rifà in secondi, mentre rigenerare gli scenari costa mezz'ora per stagione.

Due usi:

1. **un contrasto che non era stato previsto.** L'interazione del fattoriale è
   nata così: senza le osservazioni conservate sarebbe costata un'altra
   esecuzione intera. Qualunque combinazione lineare dei bracci si calcola qui.
2. **la verifica della riproduzione.** Se questo script ricalcola il verdetto
   pubblicato e ottiene gli stessi numeri, l'artefatto sul disco è
   riproducibile dagli artefatti conservati.

## Che cosa il verificatore accettava, e non doveva

Quattro modi di dichiarare RIPRODOTTO senza avere confrontato niente, tutti
riprodotti dall'audit del 9 settembre 2026:

| alterazione | esito prima |
|---|---|
| file pubblicato assente | exit 0 |
| una riga ricostruita mancante | avviso, poi RIPRODOTTO |
| valori ricostruiti tutti NaN contro numeri finiti | RIPRODOTTO |
| tutte le colonne numeriche mancanti | RIPRODOTTO |

Le cause si sommavano: confronto sulla sola **intersezione** delle chiavi,
colonne assenti **saltate**, coppie non finite **ignorate**, e «nessun
confronto effettuato» letto come scarto zero. Adesso il confronto pretende
schema completo su entrambi i lati, chiavi univoche e coincidenti, stessa
cardinalità, stesso **pattern di validità** (dove uno è non stimabile deve
esserlo anche l'altro, e per lo stesso motivo), metadati coerenti, e almeno una
coppia effettivamente confrontata.

Un valore legittimamente non stimabile — `V_2way <= 0`, rumore non misurato —
resta ammesso: quello che non è ammesso è **confonderlo con un valore perso**.

## Provenienza

Gli artefatti scritti prima del contratto delle esecuzioni non portano un
identificativo di esecuzione. Per loro il verificatore dice **provenienza
incompleta**: i numeri coincidono, ma nessuno può certificare che i due file
vengano dalla stessa esecuzione. Un'impronta calcolata oggi identifica i byte,
non l'esperimento passato.

Uso:

    PYTHONPATH=src python scripts/l2_inferenza_banco.py 2024-25 --verifica
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

from fantabot.tabellino import esecuzione as esec                # noqa: E402
from fantabot.tabellino import inferenza                         # noqa: E402

OUT = ROOT / "data" / "l2"

BRACCI = ("A", "I0", "I1", "C0", "C1")

COPPIE = [
    ("C0", "I0", "meccanismo, a informazione storica"),
    ("C1", "I1", "meccanismo, con le presenze del modello"),
    ("I1", "I0", "informazione, meccanismo per giocatore"),
    ("C1", "C0", "informazione, meccanismo cubo"),
]

# lo schema che un verdetto deve avere per essere confrontabile
CHIAVI = ["fattore", "misura", "punteggio"]
STIME = ["differenza", "ic_basso", "ic_alto", "es_two_way",
         "es_righe_indipendenti", "es_monte_carlo"]
METADATI = ["n", "partite", "giocatori", "semi", "scenari"]
STATO = ["esito"]

# le colonne del verdetto sono arrotondate a sei decimali da chi le scrive:
# 1e-6 e' la risoluzione degli artefatti, non una tolleranza scelta a piacere
TOLLERANZA = 1e-6


class VerificaFallita(RuntimeError):
    """La verifica non ha potuto concludere che i due artefatti coincidono."""


def _identificativo_unico(t: pd.DataFrame, nome: str) -> str | None:
    """L'identificativo di esecuzione della tabella, se ce n'e' **uno solo**.

    Prima si leggeva `t["esecuzione"].iloc[0]`: bastava che la prima riga
    dichiarasse `run_A` perche' una riga `run_B` piu' in basso passasse
    inosservata. Una tabella con due identificativi non viene da
    un'esecuzione: viene da due, ed e' un errore.
    """
    if "esecuzione" not in t.columns or not len(t):
        return None
    valori = t["esecuzione"]
    if valori.isna().any():
        quante = int(valori.isna().sum())
        raise VerificaFallita(
            f"{nome}: {quante} righe senza identificativo di esecuzione. "
            "La provenienza o c'e' su tutte le righe o non c'e'.")
    distinti = sorted({str(x).strip() for x in valori})
    if any(x == "" for x in distinti):
        raise VerificaFallita(f"{nome}: identificativo di esecuzione vuoto")
    if len(distinti) > 1:
        raise VerificaFallita(
            f"{nome}: {len(distinti)} identificativi di esecuzione diversi "
            f"nella stessa tabella {distinti[:4]}. Una tabella viene da "
            "un'esecuzione sola.")
    return distinti[0]


def _controlla_manifesto(stagione: str, identificativo: str | None) -> dict:
    """Confronta l'identificativo con `esecuzione.json`, quando c'e'.

    Per gli artefatti anteriori al contratto (R4) non c'e' manifesto: quella e'
    la **modalita' storica**, dichiarata, non un difetto da nascondere.
    """
    base = cartella_stagione(stagione)
    reg = base / "esecuzione.json"
    if not reg.exists():
        return {"modalita": "storica",
                "nota": ("nessun `esecuzione.json` accanto agli artefatti: "
                         "sono anteriori al contratto delle esecuzioni")}
    m = json.loads(reg.read_text("utf-8"))
    if identificativo and m.get("identificativo") != identificativo:
        raise VerificaFallita(
            f"il manifesto dichiara l'esecuzione {m.get('identificativo')}, "
            f"gli artefatti {identificativo}")
    conf = m.get("configurazione") or {}
    if conf.get("stagione") and conf["stagione"] != stagione:
        raise VerificaFallita(
            f"il manifesto e' della stagione {conf['stagione']}, non {stagione}")
    mancanti = [f for f in (m.get("file") or [])
                if not (base / f).exists()]
    if mancanti:
        raise VerificaFallita(
            f"il manifesto elenca file che non ci sono: {mancanti[:4]}")
    alterati = []
    for f, atteso in (m.get("impronte_uscite") or {}).items():
        ora = esec.impronta_file(base / f)
        if atteso and ora and ora != atteso:
            alterati.append(f)
    if alterati:
        raise VerificaFallita(
            f"artefatti modificati dopo la registrazione: {alterati[:4]}")

    # Gli INGRESSI: il manifesto ne registrava le impronte e nessuno le
    # riverificava, quindi un ingresso cambiato dopo l'esecuzione passava
    # inosservato. I numeri continuerebbero a coincidere fra loro — sono
    # coerenti — ma non sarebbero piu' rifacibili da quegli ingressi.
    ing = (conf.get("impronte_ingressi") or {})
    cambiati, spariti = [], []
    for chiave, atteso in ing.items():
        if atteso is None:
            continue
        if chiave.startswith("fantabot."):
            import importlib
            try:
                f = getattr(importlib.import_module(chiave), "__file__", None)
            except Exception:
                f = None
            ora = esec.impronta_file(f) if f else None
        else:
            percorso = Path(chiave)
            if not percorso.is_absolute():
                percorso = ROOT / chiave
            ora = esec.impronta_file(percorso)
        if ora is None:
            spariti.append(chiave)
        elif ora != atteso:
            cambiati.append(chiave)
    if cambiati or spariti:
        raise VerificaFallita(
            f"ingressi non piu' quelli dichiarati: {len(cambiati)} cambiati "
            f"{cambiati[:3]}, {len(spariti)} assenti {spariti[:3]}. I numeri "
            "possono restare coerenti fra loro, ma non sono piu' rifacibili "
            "da questi ingressi.")
    return {"modalita": "contratto", "identificativo": m.get("identificativo"),
            "istante": m.get("istante"),
            "configurazione": conf,
            "file_verificati": len(m.get("file") or []),
            "impronte_verificate": len(m.get("impronte_uscite") or {}),
            "ingressi_verificati": len([v for v in
                                        (conf.get("impronte_ingressi") or {}).values()
                                        if v])}


# --------------------------------------------------------------------------
# lettura
# --------------------------------------------------------------------------

# quando il chiamante chiede una cartella precisa, la ricaduta sui nomi piatti
# non deve avvenire in silenzio: un'esecuzione nuova che non trova i suoi file
# non e' la vecchia
DA: Path | None = None


def cartella_stagione(stagione: str) -> Path:
    """Dove stanno gli artefatti di questa stagione.

    Tre casi, in ordine:

    1. `DA` impostato (opzione `--da`): quella cartella e basta. Se i file non
       ci sono e' un errore, **non** si ricade sui nomi piatti: chiedere una
       corsa nuova e leggere in silenzio quella vecchia e' il modo migliore per
       verificare l'artefatto sbagliato;
    2. puntatore `corrente`, se esiste;
    3. nomi piatti dentro `data/l2`, dove stanno gli artefatti anteriori al
       contratto delle esecuzioni.
    """
    if DA is not None:
        return DA
    c = esec.leggi_corrente(OUT, stagione)
    return c if c is not None else OUT


def carica(stagione: str) -> tuple[pd.DataFrame, dict]:
    base = cartella_stagione(stagione)
    po = base / f"banco_osservazioni_{stagione}.parquet"
    ps = base / f"banco_semi_{stagione}.json"
    mancanti = [str(p) for p in (po, ps) if not p.exists()]
    if mancanti:
        raise VerificaFallita(
            "artefatti conservati assenti: " + ", ".join(mancanti))
    return pd.read_parquet(po), json.loads(ps.read_text("utf-8"))


def percorso_verdetto(stagione: str) -> Path:
    return cartella_stagione(stagione) / f"banco_verdetto_{stagione}.csv"


# --------------------------------------------------------------------------
# ricostruzione del verdetto
# --------------------------------------------------------------------------

def _serie(semi: dict, termini) -> list | None:
    """Medie per seme di una combinazione lineare di bracci."""
    medie = semi.get("medie_per_seme") or {}
    tot = None
    for prefisso, chiave, segno in termini:
        trovata = None
        for k, v in medie.items():
            nome, _, mis = k.rpartition("|")
            if mis == chiave and nome.split(" ")[0] == prefisso:
                trovata = np.asarray(v, dtype=float)
                break
        if trovata is None:
            return None
        tot = trovata * segno if tot is None else tot + trovata * segno
    return None if tot is None else list(tot)


def verdetto(stagione: str) -> pd.DataFrame:
    oss, semi = carica(stagione)
    scenari = int(semi.get("scenari", 30))
    esecuzione = semi.get("esecuzione")
    righe = []

    def valuta(sub, d, mc_serie, misura, punteggio, etichette, tipo, confronto):
        buoni = np.isfinite(d)
        iv = inferenza.intervallo_two_way(
            d[buoni], sub["id_partita"].to_numpy()[buoni],
            sub["master_id"].to_numpy()[buoni])
        mc = (inferenza.rumore_monte_carlo(
                  mc_serie, es_campionario=iv.errore_standard)
              if mc_serie is not None else None)
        es = iv.diagnostica["errori_standard"]
        riga = {
            "confronto": confronto, "fattore": tipo, "misura": misura,
            "punteggio": punteggio,
            "differenza": round(iv.differenza, 6),
            "ic_basso": round(iv.ic_basso, 6),
            "ic_alto": round(iv.ic_alto, 6),
            "es_two_way": round(iv.errore_standard, 6),
            "es_righe_indipendenti": round(es["righe_indipendenti"], 6),
            "es_monte_carlo": (round(mc["es_mc"], 6) if mc else float("nan")),
            "n": iv.n, "partite": iv.grappoli_1, "giocatori": iv.grappoli_2,
            "semi": (mc["repliche"] if mc else 1),
            "scenari": scenari,
            "esito": inferenza.esito_confronto(iv, mc, etichette),
            # colonne dell'emendamento prospettico: NON entrano nello schema
            # obbligatorio, cosi' gli artefatti anteriori restano verificabili
            "rumore_sotto_soglia_prospettica": (
                mc.get("soddisfatto_prospettico") if mc else None),
            "quota_varianza_monte_carlo": (
                round(mc["quota_varianza_aggiunta"], 5)
                if mc and "quota_varianza_aggiunta" in mc else float("nan"))}
        if esecuzione:
            riga["esecuzione"] = esecuzione
        righe.append(riga)

    for misura in ("crps", "brier"):
        sub = oss[oss.misura == misura]
        for punteggio, suff in (("empirico", ""), ("equo", "_equo")):
            col = {b: f"{b}{suff}" for b in BRACCI}
            if any(c not in sub.columns for c in col.values()):
                continue
            v = {b: sub[col[b]].to_numpy(dtype=float) for b in BRACCI}
            chiave = misura if not suff else f"{misura}_equo"
            for primo, secondo, tipo in COPPIE:
                valuta(sub, v[primo] - v[secondo],
                       _serie(semi, [(primo, chiave, 1.0),
                                     (secondo, chiave, -1.0)]),
                       misura, punteggio,
                       {"negativa": f"{primo} migliore",
                        "positiva": f"{primo} peggiore"},
                       tipo, f"{primo} contro {secondo}")
            valuta(sub, (v["C1"] - v["I1"]) - (v["C0"] - v["I0"]),
                   _serie(semi, [("C1", chiave, 1.0), ("I1", chiave, -1.0),
                                 ("C0", chiave, -1.0), ("I0", chiave, 1.0)]),
                   misura, punteggio,
                   {"nulla": "interazione non rilevabile",
                    "negativa": "il cubo trae piu' dalle presenze",
                    "positiva": "il cubo trae meno dalle presenze"},
                   "interazione", "(C1 - I1) - (C0 - I0)")
    return pd.DataFrame(righe)


# --------------------------------------------------------------------------
# verifica della riproduzione
# --------------------------------------------------------------------------

def _pretendi_schema(df: pd.DataFrame, nome: str, colonne) -> None:
    mancanti = [c for c in colonne if c not in df.columns]
    if mancanti:
        raise VerificaFallita(
            f"{nome}: colonne obbligatorie mancanti {mancanti}. Una colonna "
            "assente non e' un confronto riuscito: prima veniva saltata.")


def _pretendi_chiavi_uniche(df: pd.DataFrame, nome: str) -> None:
    dup = df.duplicated(CHIAVI, keep=False)
    if bool(dup.any()):
        quali = df.loc[dup, CHIAVI].drop_duplicates().to_dict("records")
        raise VerificaFallita(
            f"{nome}: chiavi ripetute {quali}. Con una chiave ripetuta "
            "l'allineamento riga per riga non e' definito.")


def _confronta(rifatto: pd.DataFrame, stagione: str,
               tolleranza: float) -> dict:
    p = percorso_verdetto(stagione)
    if not p.exists():
        raise VerificaFallita(
            f"verdetto pubblicato assente ({p}). Non avere niente con cui "
            "confrontare non e' una riproduzione.")
    try:
        pub = pd.read_csv(p)
    except Exception as e:
        raise VerificaFallita(f"verdetto pubblicato illeggibile ({p}): {e}")

    if rifatto.empty or pub.empty:
        raise VerificaFallita(
            f"tabella vuota (ricostruita {len(rifatto)} righe, pubblicata "
            f"{len(pub)}): zero confronti effettuati.")

    obbligatorie = CHIAVI + STIME + METADATI + STATO
    _pretendi_schema(rifatto, "ricostruito", obbligatorie)
    _pretendi_schema(pub, "pubblicato", obbligatorie)
    _pretendi_chiavi_uniche(rifatto, "ricostruito")
    _pretendi_chiavi_uniche(pub, "pubblicato")

    a = rifatto.set_index(CHIAVI).sort_index()
    b = pub.set_index(CHIAVI).sort_index()
    solo_a = sorted(set(a.index) - set(b.index))
    solo_b = sorted(set(b.index) - set(a.index))
    if solo_a or solo_b:
        raise VerificaFallita(
            f"insiemi di chiavi diversi: {len(solo_a)} solo nel ricostruito "
            f"{solo_a[:3]}, {len(solo_b)} solo nel pubblicato {solo_b[:3]}. "
            "Il confronto sulla sola intersezione nascondeva le righe perse.")
    if len(a) != len(b):
        raise VerificaFallita(
            f"cardinalita' diversa: {len(a)} contro {len(b)}")

    # metadati: non sono stime, sono la descrizione dell'esperimento
    incoerenti = []
    for c in METADATI:
        x, y = a[c].to_numpy(), b.loc[a.index, c].to_numpy()
        if not np.array_equal(pd.isna(x), pd.isna(y)):
            incoerenti.append(c)
            continue
        fin = ~pd.isna(x)
        try:
            xa = np.asarray(x[fin], dtype=float)
            ya = np.asarray(y[fin], dtype=float)
        except (TypeError, ValueError) as e:
            raise VerificaFallita(
                f"metadato `{c}` non numerico: {e}. Un metadato che non si "
                "converte non descrive l'esperimento, e non si confronta.")
        if not np.array_equal(xa, ya):
            incoerenti.append(c)
    if incoerenti:
        dettaglio = {c: (a[c].tolist()[:3], b.loc[a.index, c].tolist()[:3])
                     for c in incoerenti}
        raise VerificaFallita(
            f"metadati incoerenti {incoerenti}: {dettaglio}. Stessi numeri "
            "prodotti con un'altra configurazione non sono lo stesso "
            "esperimento.")

    # stato dichiarato: dove uno dice «non stimabile», deve dirlo anche l'altro
    diversi = [k for k in a.index
               if str(a.loc[k, "esito"]) != str(b.loc[k, "esito"])]
    if diversi:
        raise VerificaFallita(
            f"esiti diversi su {len(diversi)} righe, per esempio {diversi[0]}: "
            f"«{a.loc[diversi[0], 'esito']}» contro "
            f"«{b.loc[diversi[0], 'esito']}»")

    # stime: classe di validita' uguale, poi scarto sulle coppie finite.
    #
    # `~np.isfinite` metteva NaN, +inf e -inf nella stessa classe, quindi
    # `+inf` contro `-inf` passava per «entrambi non stimabili» e usciva
    # RIPRODOTTO. Non sono lo stesso motivo, e non sono nemmeno lo stesso
    # l'uno dell'altro: la classe va distinta.
    def classe(v):
        c = np.full(v.shape, 0, dtype=np.int8)      # 0 = finito
        c[np.isnan(v)] = 1
        c[np.isposinf(v)] = 2
        c[np.isneginf(v)] = 3
        return c

    NOMI = {0: "finito", 1: "NaN", 2: "+inf", 3: "-inf"}
    scarti, confrontate = {}, 0
    for c in STIME:
        try:
            x = a[c].to_numpy(dtype=float)
            y = b.loc[a.index, c].to_numpy(dtype=float)
        except (TypeError, ValueError) as e:
            raise VerificaFallita(
                f"colonna `{c}` non numerica: {e}. Una colonna di stima che "
                "non si converte in numero non e' confrontabile.")
        cx, cy = classe(x), classe(y)
        if not np.array_equal(cx, cy):
            k = int(np.argmax(cx != cy))
            quante = int(np.sum(cx != cy))
            raise VerificaFallita(
                f"colonna `{c}`: {quante} righe con classe di validita' "
                f"diversa; alla riga {a.index[k]} il ricostruito e' "
                f"{NOMI[int(cx[k])]} e il pubblicato {NOMI[int(cy[k])]}. Un "
                "non stimabile legittimo deve esserlo da entrambe le parti e "
                "per lo stesso motivo.")
        buone = cx == 0
        confrontate += int(buone.sum())
        scarti[c] = (float(np.max(np.abs(x[buone] - y[buone])))
                     if buone.any() else 0.0)
    if confrontate == 0:
        raise VerificaFallita(
            "nessuna coppia numerica effettivamente confrontata: tutte le "
            "stime sono non stimabili da entrambe le parti. Non e' una "
            "riproduzione, e prima veniva letto come scarto zero.")

    peggiore = max(scarti.values())
    # provenienza: presente solo negli artefatti scritti dopo il contratto
    prov_a = _identificativo_unico(a, "ricostruito")
    prov_b = _identificativo_unico(b, "pubblicato")
    if prov_a and prov_b and prov_a != prov_b:
        raise VerificaFallita(
            f"identificativi di esecuzione diversi: {prov_a} contro {prov_b}")
    if bool(prov_a) != bool(prov_b):
        # uno dichiara l'esecuzione e l'altro no: non possono venire dalla
        # stessa. Prima questo caso ricadeva in «provenienza incompleta», che
        # affermava il falso su un artefatto che l'identificativo ce l'aveva.
        chi = "ricostruito" if prov_a else "pubblicato"
        raise VerificaFallita(
            f"solo il {chi} dichiara l'esecuzione ({prov_a or prov_b}): i due "
            "artefatti non vengono dalla stessa, oppure uno e' anteriore al "
            "contratto delle esecuzioni e va confrontato con un suo pari.")

    # i semi: si confronta la LISTA, non solo quanti sono. Due esecuzioni con
    # otto semi diversi hanno lo stesso `semi = 8` e non sono la stessa cosa.
    lista_semi = None
    try:
        _, meta = carica(stagione)
        lista_semi = meta.get("semi")
    except VerificaFallita:
        meta = {}
    manifesto = _controlla_manifesto(stagione, prov_a or prov_b)
    if lista_semi is not None:
        attesi = int(a["semi"].iloc[0]) if "semi" in a.columns and len(a) else None
        if attesi and attesi > 1 and len(lista_semi) != attesi:
            raise VerificaFallita(
                f"il verdetto dichiara {attesi} semi, gli artefatti ne "
                f"elencano {len(lista_semi)}: {lista_semi[:4]}")
    return {"scarti": scarti, "peggiore": peggiore, "righe": len(a),
            "coppie_confrontate": confrontate,
            "provenienza": (prov_a if prov_a and prov_b else None),
            "manifesto": manifesto, "semi": lista_semi,
            "passata": peggiore <= tolleranza, "tolleranza": tolleranza}


def confronta(rifatto: pd.DataFrame, stagione: str, *,
              tolleranza: float = TOLLERANZA) -> int:
    """0 se il verdetto pubblicato è riprodotto, 1 altrimenti.

    Ogni modo di non concludere è un errore, non un successo silenzioso —
    compresa un'eccezione imprevista: un artefatto malformato deve produrre
    «NON VERIFICATO», non un traceback che il chiamante non sa leggere.
    """
    try:
        r = _confronta(rifatto, stagione, tolleranza)
    except VerificaFallita as e:
        print(f"  {stagione}: NON VERIFICATO — {e}")
        return 1
    except Exception as e:
        print(f"  {stagione}: NON VERIFICATO — errore imprevisto nel "
              f"confronto ({type(e).__name__}): {e}")
        return 1
    for c, s in r["scarti"].items():
        print(f"    {c:<24} scarto massimo {s:.2e}")
    print(f"    righe {r['righe']}, coppie numeriche confrontate "
          f"{r['coppie_confrontate']}")
    if not r["passata"]:
        print(f"  {stagione}: NON RIPRODOTTO, scarto massimo "
              f"{r['peggiore']:.2e} sopra la risoluzione "
              f"{r['tolleranza']:.0e}. Il verdetto pubblicato e le "
              "osservazioni conservate non vengono dalla stessa esecuzione.")
        return 1
    if r["provenienza"]:
        m = r.get("manifesto") or {}
        print(f"  {stagione}: RIPRODOTTO (scarto massimo {r['peggiore']:.2e}), "
              f"esecuzione {r['provenienza']}, manifesto {m.get('modalita')}"
              + (f", {m.get('impronte_verificate')} impronte verificate"
                 if m.get("impronte_verificate") else ""))
    else:
        print(f"  {stagione}: RIPRODOTTO (scarto massimo {r['peggiore']:.2e}), "
              "PROVENIENZA INCOMPLETA — gli artefatti non portano un "
              "identificativo di esecuzione, quindi i numeri coincidono ma "
              "nessuno certifica che vengano dalla stessa esecuzione")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("stagioni", nargs="*", default=["2024-25", "2025-26"])
    ap.add_argument("--verifica", action="store_true",
                    help="confronta con il verdetto pubblicato e torna 1 se "
                         "non coincide")
    ap.add_argument("--da", default=None,
                    help="cartella di una esecuzione precisa. Senza, si segue "
                         "il puntatore `corrente` e in mancanza di quello i "
                         "nomi piatti storici.")
    ap.add_argument("--scrivi", default=None,
                    help="scrive il verdetto rifatto in questo percorso")
    a = ap.parse_args()
    global DA
    if a.da:
        DA = Path(a.da)
        if not DA.exists():
            print(f"NON VERIFICATO — la cartella {DA} non esiste")
            return 1
        print(f"  leggo da {DA}")
    uscita = 0
    for st in (a.stagioni or ["2024-25", "2025-26"]):
        print(f"\n== {st}")
        try:
            t = verdetto(st)
        except VerificaFallita as e:
            print(f"  {st}: NON VERIFICATO — {e}")
            uscita = 1
            continue
        except Exception as e:
            print(f"  {st}: NON VERIFICATO — errore imprevisto nella "
                  f"ricostruzione ({type(e).__name__}): {e}")
            uscita = 1
            continue
        if t.empty:
            print(f"  {st}: NON VERIFICATO — nessuna riga ricostruita: "
                  "osservazioni assenti o incomplete")
            uscita = 1
            continue
        colonne = ["fattore", "misura", "punteggio", "differenza", "ic_basso",
                   "ic_alto", "es_two_way", "es_monte_carlo", "esito"]
        print(t[colonne].to_string(index=False))
        if a.scrivi:
            t.to_csv(Path(a.scrivi.format(stagione=st)), index=False)
        if a.verifica:
            uscita |= confronta(t, st)
    return uscita


if __name__ == "__main__":
    sys.exit(main())
