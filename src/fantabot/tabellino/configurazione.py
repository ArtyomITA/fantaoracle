"""Una sola procedura per costruire il modello di partita.

## Perche' questo modulo esiste

Fino a oggi il modello di partita veniva costruito in tre posti diversi, con
tre risultati diversi:

  - `scripts/l2_banco_partita.py` sceglieva gli iperparametri sulla stagione
    precedente a quella di prova e aggiungeva i prior dagli xG e i prior per le
    neopromosse (il candidato «F»);
  - `scripts/l2_genera_cubo.py` e `scripts/l2_banco_confronto.py` scrivevano a
    mano `xi = 0,0015` e `lam_pen = 2,0` e non passavano nessun prior.

L'audit `data/l3/audit/simulazione/RAPPORTO.md`, sezione 1, ha misurato la
conseguenza sul calendario 2026-27: scarto assoluto medio sulle intensita'
0,2177 gol (16,59 % in relativo), fino a 1,5140 gol, con squadre spostate di
0,3-0,5 gol a partita. Il criterio 3.3 di `reports/CRITERI_L2_L3.md` chiede che
banco e generatore costruiscano il modello **con la stessa procedura**, e che a
parita' di dati, data limite e configurazione le intensita' coincidano entro
1e-9, con l'impronta della configurazione registrata.

Questo modulo e' quella procedura. Chi ha bisogno di un modello di partita
chiama `costruisci_modello_partita` e non stima piu' nulla per conto proprio.

## Che cosa fa, in ordine

  1. **Filtro temporale.** Tiene solo le partite gia' concluse alla data
     limite. Se la tabella ha la colonna `stato_partita` (contratto degli stati,
     sezione 7.2 dei criteri) usa quella; altrimenti ripiega su `giocata`. In
     entrambi i casi il risultato deve esserci davvero: una partita con calcio
     d'inizio anteriore alla decisione ma senza risultato **non entra**
     nell'addestramento, che e' esattamente il difetto 0.2 dei criteri.
  2. **Scelta degli iperparametri.** Decadimento `xi` e penalizzazione
     `lam_pen` si scelgono per punteggio logaritmico sulla stagione precedente a
     quella di prova, addestrando sulle stagioni ancora precedenti. Mai sulla
     stagione che si vuole prevedere.
  3. **Prior.** Forze a priori stimate sugli xG (stessa disciplina temporale dei
     gol: gli xG di una partita esistono solo dopo che e' stata giocata) e forza
     media storica delle neopromosse per le squadre che l'anno prima non erano
     in Serie A.
  4. **Stima Dixon-Coles** con `rho` e verifica esplicita che resti dentro
     l'intervallo di ammissibilita' calcolato sulle intensita' effettive.

## Impronta

`ConfigurazionePartita.impronta()` e' lo SHA-256 di un dizionario canonico
(JSON con chiavi ordinate) che contiene versione della procedura, data limite,
iperparametri, griglie provate, elenco delle squadre, prior e le impronte degli
ingressi: il digest del contenuto della tabella usata per addestrare e, se il
chiamante li dichiara, i digest dei file da cui la tabella e' stata letta.
Serve a rispondere a una domanda sola: *questi due modelli sono stati costruiti
dagli stessi ingressi con la stessa configurazione?* Se l'impronta cambia,
qualcosa e' cambiato, e va detto quale.

Un avvertimento onesto sull'impronta: siccome contiene i prior, che sono a loro
volta stimati, essa lega il **percorso numerico esatto**. La somma in virgola
mobile non e' associativa, quindi la stessa tabella con le righe in ordine
diverso da prior diversi nell'ultimo bit e quindi un'impronta diversa, pur
lasciando le intensita' entro 1,8e-11 (misurato sul 2026-27, test
`test_ordine_delle_righe_sposta_meno_di_1e_9`). Per chiedersi se due esecuzioni
hanno visto gli stessi *dati* si confronta
`impronte_ingressi["addestramento"]`, che e' indipendente dall'ordine.

## Ammissibilita' dopo il campionamento delle forze

`ModelloPartita.campiona_parametri` estrae l'intero vettore dei parametri,
`rho` compreso, dalla normale approssimata all'ottimo. Il vincolo di Dixon e
Coles lega pero' `rho` alle intensita': dopo l'estrazione sono cambiati sia
l'uno sia le altre, e nel codice di `partita.py` non c'e' nessun controllo che
lo riverifichi. L'audit (sezione 2) ha misurato 0 violazioni su 1000 estrazioni
col modello attuale, ma con margine minimo 0,0157 nel caso peggiore: il
fenomeno e' possibile, e se accadesse verrebbe assorbito in silenzio dal
`np.maximum(P, 0)` di `campiona_risultati`.

`verifica_ammissibilita` in questo modulo controlla un modello (stimato o
estratto) su un elenco di partite e dice se `tau` resta positivo ovunque e
quanta massa di coda viene troncata a `MAX_GOL`. **Chi genera scenari deve
chiamarla su ogni modello estratto e registrare i rigetti**: qui non si tocca
`partita.py`, quindi il controllo non e' automatico e resta responsabilita' del
chiamante.
"""
from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

from .partita import (
    MAX_GOL, ModelloPartita, pesi_decadimento, rho_ammissibile, stima, tau,
)

# Versione della procedura. Va alzata quando cambia il *significato* di un
# passo (non quando si aggiunge un campo diagnostico): entra nell'impronta,
# quindi due modelli costruiti con procedure diverse non possono risultare
# uguali per distrazione.
VERSIONE = "1.0"

# Griglie provate nella scelta degli iperparametri. Sono le stesse che il banco
# usava (`scripts/l2_banco_partita.py`, costanti XI e LAM), spostate qui perche'
# fanno parte della procedura e devono comparire nell'impronta.
GRIGLIA_XI = (0.0, 0.0015, 0.003, 0.005, 0.008)
GRIGLIA_LAM_PEN = (0.5, 2.0, 5.0)

# Penalizzazione usata per stimare i prior (xG e neopromosse). E' fissa e
# deliberatamente diversa dalla `lam_pen` scelta per il modello sui gol: i
# prior sono un ingrediente, non il modello, e cambiarli al variare della
# griglia renderebbe la ricerca circolare. Valore ereditato dal banco.
LAM_PEN_PRIOR = 2.0

# Stati di `stato_partita` che NON possono entrare nell'addestramento perche'
# il risultato non esiste ancora. Gli altri stati (`conclusa`, `senza_voti`,
# `rinviata` gia' disputata) entrano se e solo se i gol sono presenti: al
# modello di partita servono i gol, non i voti.
STATI_SENZA_RISULTATO = ("da_giocare",)


# --------------------------------------------------------------------------
# impronte
# --------------------------------------------------------------------------

def impronta_file(percorso) -> str:
    """SHA-256 del contenuto di un file, letto a blocchi.

    Serve a legare una configurazione ai file da cui e' nata: se il parquet
    delle partite cambia, l'impronta della configurazione cambia con lui."""
    h = hashlib.sha256()
    with open(percorso, "rb") as f:
        for blocco in iter(lambda: f.read(1 << 20), b""):
            h.update(blocco)
    return h.hexdigest()


def impronta_tabella(d, colonne=None) -> str:
    """SHA-256 del contenuto di una tabella, indipendente dall'ordine delle righe.

    Non si usa `pd.util.hash_pandas_object` perche' la sua stabilita' fra
    versioni di pandas non e' garantita. Qui le righe vengono rese in forma
    testuale canonica, ordinate e concatenate: due tabelle con le stesse righe
    in ordine diverso danno la stessa impronta, due tabelle con un solo gol
    diverso ne danno una diversa."""
    if colonne is None:
        colonne = list(d.columns)
    colonne = [c for c in colonne if c in d.columns]
    righe = []
    for t in d[colonne].itertuples(index=False, name=None):
        righe.append("\x1f".join(_testo_valore(v) for v in t))
    righe.sort()
    h = hashlib.sha256()
    h.update(("\x1e".join(colonne) + "\x1d").encode("utf-8"))
    for r in righe:
        h.update(r.encode("utf-8"))
        h.update(b"\x1e")
    return h.hexdigest()


def _testo_valore(v) -> str:
    """Rappresentazione testuale stabile di un valore di cella."""
    if v is None:
        return "\x00"
    if isinstance(v, float):
        if math.isnan(v):
            return "\x00"
        return repr(v)          # repr di float in Python 3 e' round-trip
    if isinstance(v, (np.floating,)):
        f = float(v)
        return "\x00" if math.isnan(f) else repr(f)
    if isinstance(v, (np.integer,)):
        return str(int(v))
    return str(v)


def _canonico(x):
    """Rende un oggetto serializzabile in JSON in modo deterministico."""
    if isinstance(x, dict):
        return {str(k): _canonico(v) for k, v in sorted(x.items(), key=lambda kv: str(kv[0]))}
    if isinstance(x, (list, tuple)):
        return [_canonico(v) for v in x]
    if isinstance(x, (np.floating,)):
        return float(x)
    if isinstance(x, (np.integer,)):
        return int(x)
    if isinstance(x, (np.bool_,)):
        return bool(x)
    if isinstance(x, (str, int, float, bool)) or x is None:
        return x
    return str(x)


def _sha256_dizionario(d: dict) -> str:
    testo = json.dumps(_canonico(d), sort_keys=True, ensure_ascii=False,
                       separators=(",", ":"))
    return hashlib.sha256(testo.encode("utf-8")).hexdigest()


# --------------------------------------------------------------------------
# configurazione
# --------------------------------------------------------------------------

@dataclass(frozen=True)
class Iperparametri:
    """I due iperparametri del modello piu' gli interruttori dei suoi pezzi.

    Sono immutabili di proposito: una configurazione gia' usata per generare
    non deve poter cambiare sotto i piedi di chi ha registrato la sua impronta.
    """
    xi: float                       # decadimento temporale, 1/giorno
    lam_pen: float                  # forza della penalizzazione verso il prior
    usa_dc: bool = True             # correzione di Dixon e Coles
    prior_xg: bool = True           # forze a priori stimate sugli xG
    prior_neopromosse: bool = True  # forza media storica delle neopromosse

    def a_dizionario(self) -> dict:
        return {"xi": float(self.xi), "lam_pen": float(self.lam_pen),
                "usa_dc": bool(self.usa_dc), "prior_xg": bool(self.prior_xg),
                "prior_neopromosse": bool(self.prior_neopromosse)}


@dataclass
class ConfigurazionePartita:
    """Tutto quello che serve a rifare lo stesso modello, piu' la sua impronta.

    E' serializzabile con `a_dizionario()` e ricostruibile con
    `da_dizionario()`: cosi' puo' essere scritta accanto a un cubo o a un
    rapporto di banco e riletta per un confronto."""
    versione: str
    as_of: str
    iperparametri: dict
    origine_iperparametri: dict     # come sono stati scelti (o «forniti»)
    squadre: list
    prior_att: dict
    prior_dif: dict
    n_partite_addestramento: int
    peso_totale: float
    filtro: dict                    # quale colonna di stato e' stata usata
    impronte_ingressi: dict
    diagnostica: dict = field(default_factory=dict)

    def a_dizionario(self) -> dict:
        return _canonico({
            "versione": self.versione,
            "as_of": self.as_of,
            "iperparametri": self.iperparametri,
            "origine_iperparametri": self.origine_iperparametri,
            "squadre": list(self.squadre),
            "prior_att": self.prior_att,
            "prior_dif": self.prior_dif,
            "n_partite_addestramento": self.n_partite_addestramento,
            "peso_totale": self.peso_totale,
            "filtro": self.filtro,
            "impronte_ingressi": self.impronte_ingressi,
            "diagnostica": self.diagnostica,
        })

    @staticmethod
    def da_dizionario(d: dict) -> "ConfigurazionePartita":
        return ConfigurazionePartita(
            versione=d["versione"], as_of=d["as_of"],
            iperparametri=d["iperparametri"],
            origine_iperparametri=d.get("origine_iperparametri", {}),
            squadre=list(d["squadre"]), prior_att=d.get("prior_att", {}),
            prior_dif=d.get("prior_dif", {}),
            n_partite_addestramento=d["n_partite_addestramento"],
            peso_totale=d["peso_totale"], filtro=d.get("filtro", {}),
            impronte_ingressi=d.get("impronte_ingressi", {}),
            diagnostica=d.get("diagnostica", {}))

    def impronta(self) -> str:
        """SHA-256 della configurazione, diagnostica esclusa.

        La diagnostica descrive il modello che ne e' uscito (gol medi stimati,
        iterazioni dell'ottimizzatore); non e' un ingresso, quindi non entra
        nell'impronta. Tutto il resto si': iperparametri, prior, squadre,
        griglie provate e impronte degli ingressi."""
        d = self.a_dizionario()
        d.pop("diagnostica", None)
        return _sha256_dizionario(d)


# --------------------------------------------------------------------------
# filtro temporale
# --------------------------------------------------------------------------

def colonna_data(d) -> str:
    """Nome della colonna con il calcio d'inizio.

    Il contratto degli stati (sezione 7.2) introduce `data_evento`, che e' la
    data e ora effettive; finche' non c'e' si usa `data`. Scritto cosi' il
    codice funziona prima e dopo l'aggiunta della colonna."""
    return "data_evento" if "data_evento" in d.columns else "data"


def partite_di_addestramento(d, as_of):
    """Le sole partite utilizzabili per stimare il modello a quella data.

    Regola: calcio d'inizio **anteriore** alla data limite, stato che non
    dichiari il risultato mancante, e gol effettivamente presenti. La terza
    condizione e' quella che conta: una partita gia' iniziata ma senza
    risultato non e' informazione disponibile, e trattarla come giocata era il
    difetto 0.2 dei criteri.

    Ritorna `(tabella, descrizione_del_filtro)`."""
    import pandas as pd

    col = colonna_data(d)
    dd = d.copy()
    dd[col] = pd.to_datetime(dd[col])
    limite = pd.Timestamp(as_of)
    anteriori = dd[col] < limite
    if "stato_partita" in dd.columns:
        stato = dd["stato_partita"].astype(str)
        ammessi = ~stato.isin(STATI_SENZA_RISULTATO)
        usata = "stato_partita"
    else:
        ammessi = dd["giocata"] == 1
        usata = "giocata"
    con_gol = dd["gol_casa"].notna() & dd["gol_trasferta"].notna()
    tr = dd[anteriori & ammessi & con_gol].copy()
    filtro = {
        "colonna_stato": usata,
        "colonna_data": col,
        "stati_esclusi": list(STATI_SENZA_RISULTATO) if usata == "stato_partita" else [],
        "anteriori_alla_data_limite": int(anteriori.sum()),
        "ammesse_dallo_stato": int((anteriori & ammessi).sum()),
        "con_risultato": int((anteriori & ammessi & con_gol).sum()),
    }
    return tr, filtro


def stagione_del_taglio(d, as_of) -> str | None:
    """Stagione a cui appartiene la data limite.

    E' la stagione della prima partita con calcio d'inizio non anteriore alla
    data limite: quella che si vuole prevedere. Se non ce n'e' nessuna (data
    limite oltre la fine dei dati) ritorna `None`."""
    import pandas as pd

    col = colonna_data(d)
    dd = d.copy()
    dd[col] = pd.to_datetime(dd[col])
    fut = dd[dd[col] >= pd.Timestamp(as_of)].sort_values(col)
    if not len(fut):
        return None
    return str(fut.stagione.iloc[0])


# --------------------------------------------------------------------------
# prior
# --------------------------------------------------------------------------

def prior_da_xg(tr, squadre, xi, as_of) -> tuple[dict, dict]:
    """Forze stimate sugli xG: entrano come media a priori del modello sui gol.

    Gli xG di una partita esistono solo dopo che e' stata giocata, quindi
    valgono le stesse regole temporali dei gol: `tr` deve gia' essere filtrata.
    Sotto 100 partite con xG il prior non viene costruito: sarebbe rumore.

    Implementazione identica a quella che stava in `l2_banco_partita.py`
    (righe 186-198 della versione precedente); la penalizzazione e' fissa a
    `LAM_PEN_PRIOR` per non rendere circolare la ricerca sugli iperparametri."""
    d = tr.dropna(subset=["xg_casa", "xg_trasferta"])
    if len(d) < 100:
        return {}, {}
    w = pesi_decadimento(d.data.values.astype("datetime64[D]"), as_of, xi)
    m = stima(d.casa.values, d.trasferta.values, d.xg_casa.values,
              d.xg_trasferta.values, squadre=squadre, pesi=w,
              lam_pen=LAM_PEN_PRIOR, usa_dc=False)
    return (dict(zip(m.squadre, m.att)), dict(zip(m.squadre, m.dif)))


def prior_neopromosse(storico, squadre_test, squadre_prec) -> tuple[dict, dict]:
    """Forza media delle neopromosse nelle stagioni passate.

    Una squadra appena salita non ha partite in Serie A: senza prior prende la
    forza media del campionato, che la sopravvaluta.

    Rispetto alla versione che stava in `l2_banco_partita.py` (righe 201-226) e'
    sparito il parametro `as_of`, che era dichiarato e mai usato: tenerlo
    avrebbe fatto credere che ci fosse una disciplina temporale che non c'era.
    Il filtro temporale resta responsabilita' del chiamante, che passa uno
    `storico` gia' tagliato."""
    stagioni = sorted(storico.stagione.unique())
    att, dif = [], []
    for i in range(1, len(stagioni)):
        prec = set(storico[storico.stagione == stagioni[i - 1]].casa)
        cur = storico[storico.stagione == stagioni[i]]
        nuove = set(cur.casa) - prec
        if not nuove:
            continue
        m = stima(cur.casa.values, cur.trasferta.values, cur.gol_casa.values,
                  cur.gol_trasferta.values, lam_pen=LAM_PEN_PRIOR, usa_dc=False)
        ix = m.indice()
        for s in nuove:
            if s in ix:
                att.append(m.att[ix[s]])
                dif.append(m.dif[ix[s]])
    if not att:
        return {}, {}
    ma, md = float(np.mean(att)), float(np.mean(dif))
    nuove_test = set(squadre_test) - set(squadre_prec)
    return ({s: ma for s in nuove_test}, {s: md for s in nuove_test})


# --------------------------------------------------------------------------
# scelta degli iperparametri
# --------------------------------------------------------------------------

def scegli_iperparametri(storico_prima, val, squadre=None, as_of_val=None,
                         griglia_xi=GRIGLIA_XI,
                         griglia_lam_pen=GRIGLIA_LAM_PEN) -> tuple:
    """`xi` e `lam_pen` per punteggio logaritmico su una stagione di validazione.

    `storico_prima` sono le partite anteriori all'inizio di `val`, `val` e' la
    stagione su cui si misura. Nessuna partita di `val` entra
    nell'addestramento: e' il punto per cui la scelta non e' circolare.

    Ritorna `((xi, lam_pen), punteggio, tabella_completa)`. La tabella serve a
    far vedere quanto e' netta la scelta: se due combinazioni distano meno
    dell'incertezza, dirlo e' piu' onesto che dichiarare un vincitore."""
    if as_of_val is None:
        as_of_val = str(np.datetime64(val.data.min(), "D"))
    if squadre is None:
        squadre = sorted(set(storico_prima.casa) | set(val.casa))
    date = storico_prima.data.values.astype("datetime64[D]")
    tabella, migliore, best = [], None, np.inf
    for xi in griglia_xi:
        w = pesi_decadimento(date, as_of_val, xi)
        for lp in griglia_lam_pen:
            m = stima(storico_prima.casa.values, storico_prima.trasferta.values,
                      storico_prima.gol_casa.values,
                      storico_prima.gol_trasferta.values,
                      squadre=squadre, pesi=w, lam_pen=lp, usa_dc=True)
            s = float(np.mean(m.log_score_risultato(
                val.casa.values, val.trasferta.values,
                val.gol_casa.values, val.gol_trasferta.values)))
            tabella.append({"xi": float(xi), "lam_pen": float(lp),
                            "log_score": s})
            if s < best:
                best, migliore = s, (float(xi), float(lp))
    return migliore, best, tabella


# --------------------------------------------------------------------------
# la procedura unica
# --------------------------------------------------------------------------

def costruisci_modello_partita(partite, as_of, iperparametri=None, *,
                               squadre=None, stagione_bersaglio=None,
                               con_incertezza=False,
                               griglia_xi=GRIGLIA_XI,
                               griglia_lam_pen=GRIGLIA_LAM_PEN,
                               percorsi_ingresso=(),
                               etichetta=None):
    """Costruisce il modello di partita. **Unico punto di ingresso.**

    Parametri
    ---------
    partite : DataFrame
        Tabella delle partite, storico e calendario insieme. Servono almeno le
        colonne `stagione`, `data`, `casa`, `trasferta`, `gol_casa`,
        `gol_trasferta`, e o `stato_partita` o `giocata`. `xg_casa`/`xg_trasferta`
        se si vogliono i prior dagli xG.
    as_of : str
        Data limite informativa (`AAAA-MM-GG`). Nessuna informazione a partire
        da questa data entra nel modello.
    iperparametri : Iperparametri | dict | None
        Se `None`, `xi` e `lam_pen` si scelgono con `scegli_iperparametri` sulla
        stagione precedente a quella bersaglio. Se forniti, si usano quelli e la
        ricerca non viene fatta: la configurazione lo registra in
        `origine_iperparametri["modo"]`.
    squadre : elenco | None
        Squadre da modellare. Se `None`: squadre dell'addestramento piu' quelle
        del calendario della stagione bersaglio.
    stagione_bersaglio : str | None
        Stagione da prevedere. Se `None` si deduce dalla data limite.
    con_incertezza : bool
        Se vero calcola l'inversa dell'informazione osservata, necessaria a
        `campiona_parametri`. Costa il doppio circa.
    percorsi_ingresso : elenco di percorsi
        File da cui la tabella e' stata letta: i loro digest entrano
        nell'impronta.

    Ritorna
    -------
    (modello, configurazione, impronta)
        `modello` e' un `ModelloPartita`, `configurazione` una
        `ConfigurazionePartita` serializzabile, `impronta` la stringa SHA-256.
    """
    import pandas as pd

    tr, filtro = partite_di_addestramento(partite, as_of)
    if not len(tr):
        raise ValueError(f"nessuna partita conclusa prima di {as_of}: "
                         "il modello di partita non e' costruibile")

    tutte = partite.copy()
    tutte["data"] = pd.to_datetime(tutte["data"])
    if stagione_bersaglio is None:
        stagione_bersaglio = stagione_del_taglio(partite, as_of)

    # squadre del calendario della stagione bersaglio: sono quelle che
    # giocheranno, e solo fra loro ha senso cercare le neopromosse.
    if stagione_bersaglio is not None:
        cal = tutte[tutte.stagione == stagione_bersaglio]
        squadre_bersaglio = set(cal.casa) | set(cal.trasferta)
    else:
        cal = tutte.iloc[0:0]
        squadre_bersaglio = set()

    # squadre da modellare: quelle viste in addestramento piu' quelle del
    # calendario, che possono non aver ancora giocato (neopromosse).
    if squadre is None:
        squadre = sorted(set(tr.casa) | set(tr.trasferta) | squadre_bersaglio)
    else:
        squadre = sorted(set(squadre))
    if not squadre_bersaglio:
        squadre_bersaglio = set(squadre)

    # --- stagione precedente alla bersaglio: serve per la validazione degli
    # iperparametri e per sapere chi e' neopromossa ---
    stagioni_tr = sorted(tr.stagione.unique())
    if stagione_bersaglio is None:
        stagione_precedente = stagioni_tr[-1] if stagioni_tr else None
    else:
        prima = [s for s in stagioni_tr if s < stagione_bersaglio]
        stagione_precedente = prima[-1] if prima else None

    # --- iperparametri ---
    origine = {"griglia_xi": list(griglia_xi),
               "griglia_lam_pen": list(griglia_lam_pen)}
    if iperparametri is not None:
        ip = (iperparametri if isinstance(iperparametri, Iperparametri)
              else Iperparametri(**iperparametri))
        origine["modo"] = "forniti"
        origine["stagione_di_validazione"] = None
    else:
        if stagione_precedente is None:
            raise ValueError(
                "non c'e' una stagione precedente su cui scegliere gli "
                "iperparametri: passali espliciti oppure amplia lo storico")
        # la validazione avviene interamente dentro l'addestramento: la
        # stagione precedente e tutte quelle prima ancora sono gia' concluse
        # alla data limite, quindi `tr` basta e nessuna informazione futura
        # puo' entrare per distrazione.
        val = tr[tr.stagione == stagione_precedente]
        val_inizio = val.data.min()
        prima_di_val = tr[tr.data < val_inizio]
        if not len(prima_di_val):
            raise ValueError(
                f"non ci sono partite anteriori alla stagione di validazione "
                f"{stagione_precedente}: iperparametri non scegliibili")
        (xi, lp), punteggio, tabella = scegli_iperparametri(
            prima_di_val, val,
            squadre=sorted(set(prima_di_val.casa) | set(val.casa)),
            as_of_val=str(val_inizio.date()),
            griglia_xi=griglia_xi, griglia_lam_pen=griglia_lam_pen)
        ip = Iperparametri(xi=xi, lam_pen=lp)
        origine["modo"] = "scelti su stagione precedente"
        origine["stagione_di_validazione"] = str(stagione_precedente)
        origine["log_score_di_validazione"] = round(punteggio, 6)
        origine["n_partite_di_validazione"] = int(len(val))
        origine["n_partite_prima_della_validazione"] = int(len(prima_di_val))
        origine["griglia_completa"] = [
            {k: (round(v, 6) if k == "log_score" else v) for k, v in r.items()}
            for r in tabella]

    # --- prior ---
    pa, pdf, pn_a, pn_d = {}, {}, {}, {}
    if ip.prior_xg:
        pa, pdf = prior_da_xg(tr, squadre, ip.xi, as_of)
    if ip.prior_neopromosse and stagione_precedente is not None:
        # `storico.data < tr.data.max()` come nel banco: l'ultimo giorno di
        # addestramento non serve a stabilire chi e' neopromossa e toglierlo
        # rende la finestra insensibile a una partita in piu' o in meno.
        prec = tr[tr.stagione == stagione_precedente]
        pn_a, pn_d = prior_neopromosse(tr[tr.data < tr.data.max()],
                                       squadre_test=squadre_bersaglio,
                                       squadre_prec=set(prec.casa))
        pa = {**pa, **{s: v for s, v in pn_a.items() if s not in pa}}
        pdf = {**pdf, **{s: v for s, v in pn_d.items() if s not in pdf}}

    # --- stima ---
    w = pesi_decadimento(tr.data.values.astype("datetime64[D]"), as_of, ip.xi)
    mod = stima(tr.casa.values, tr.trasferta.values, tr.gol_casa.values,
                tr.gol_trasferta.values, squadre=squadre, pesi=w,
                lam_pen=ip.lam_pen, usa_dc=ip.usa_dc,
                prior_att=pa or None, prior_dif=pdf or None,
                con_incertezza=con_incertezza)

    # --- ammissibilita' di rho sul punto stimato, sulle partite di
    # addestramento e sul calendario della stagione bersaglio ---
    coppie_casa = list(tr.casa.values) + list(cal.casa.values)
    coppie_via = list(tr.trasferta.values) + list(cal.trasferta.values)
    amm = verifica_ammissibilita(mod, coppie_casa, coppie_via)

    colonne_impronta = [c for c in ("stagione", "giornata", "data", "casa",
                                    "trasferta", "gol_casa", "gol_trasferta",
                                    "xg_casa", "xg_trasferta", "giocata",
                                    "stato_partita")
                        if c in tr.columns]
    impronte = {
        "addestramento": impronta_tabella(tr, colonne_impronta),
        "colonne_usate": colonne_impronta,
        "file": {str(Path(p).name): impronta_file(p) for p in percorsi_ingresso},
    }

    conf = ConfigurazionePartita(
        versione=VERSIONE,
        as_of=str(as_of),
        iperparametri=ip.a_dizionario(),
        origine_iperparametri=origine,
        squadre=list(squadre),
        prior_att={str(k): float(v) for k, v in pa.items()},
        prior_dif={str(k): float(v) for k, v in pdf.items()},
        n_partite_addestramento=int(len(tr)),
        peso_totale=float(w.sum()),
        filtro=filtro,
        impronte_ingressi=impronte,
        diagnostica={
            "etichetta": etichetta,
            "stagione_bersaglio": stagione_bersaglio,
            "stagione_precedente": stagione_precedente,
            "neopromosse_con_prior": sorted(str(s) for s in pn_a),
            "squadre_con_prior": len(pa),
            "rho": float(mod.rho),
            "vantaggio_casa": float(mod.casa),
            "convergenza": bool(mod.convergenza),
            "ammissibilita": amm,
            "modello": mod.diagnostica,
        },
    )
    return mod, conf, conf.impronta()


# --------------------------------------------------------------------------
# ammissibilita' e coda troncata
# --------------------------------------------------------------------------

def verifica_ammissibilita(modello: ModelloPartita, casa, trasferta,
                           max_gol: int = MAX_GOL) -> dict:
    """Dice se un modello e' usabile su un elenco di partite.

    Due domande, entrambe misurate sulle intensita' **effettive** di quelle
    partite e non su quelle di addestramento:

      1. `tau` resta positivo su tutte e quattro le celle a punteggio basso?
         Equivale a chiedere che `rho` stia dentro l'intervallo ammissibile
         calcolato sulle intensita' della partita piu' estrema.
      2. quanta massa di probabilita' viene troncata a `max_gol` e riversata
         sulla cella d'angolo da `matrice_risultato`?

    Va chiamata **su ogni modello estratto** da `campiona_parametri`: quella
    funzione estrae anche `rho` dalla normale approssimata, senza alcun
    vincolo, mentre la stima lo teneva dentro `[-0,4; 0,4]`, e le intensita'
    dell'estrazione sono diverse da quelle del punto stimato. Chi genera deve
    registrare i rigetti: se `ammissibile` e' falso il modello estratto va
    scartato e riestratto, non corretto in silenzio con `np.maximum(P, 0)`.

    Ritorna un dizionario serializzabile; nessun effetto collaterale."""
    lam, mu = modello.intensita(np.asarray(casa), np.asarray(trasferta))
    rho = float(modello.rho)
    basso, alto = rho_ammissibile(lam, mu)
    # tau sulle quattro celle basse, partita per partita
    celle = [(0, 0), (0, 1), (1, 0), (1, 1)]
    t_min = np.inf
    non_positive = 0
    for (x, y) in celle:
        t = tau(np.full(len(lam), x), np.full(len(lam), y), lam, mu, rho)
        t_min = min(t_min, float(np.min(t)))
        non_positive += int(np.sum(t <= 0))
    massa = _massa_troncata(lam, mu, max_gol)
    return {
        "n_partite": int(len(lam)),
        "rho": rho,
        "rho_ammissibile": [float(basso), float(alto)],
        "rho_dentro": bool(basso < rho < alto),
        "margine_rho": float(min(rho - basso, alto - rho)),
        "tau_minimo": float(t_min),
        "celle_tau_non_positive": int(non_positive),
        "lambda_min": float(np.min(np.minimum(lam, mu))),
        "lambda_max": float(np.max(np.maximum(lam, mu))),
        "massa_coda_media": float(np.mean(massa)),
        "massa_coda_massima": float(np.max(massa)),
        "max_gol": int(max_gol),
        "ammissibile": bool(non_positive == 0 and basso < rho < alto),
    }


def _massa_troncata(lam, mu, max_gol: int) -> np.ndarray:
    """Massa di probabilita' oltre `max_gol` gol, per ciascuna partita.

    `matrice_risultato` la riversa sulla cella d'angolo (`max_gol`, `max_gol`),
    cioe' sul risultato 12-12: e' un risultato impossibile che assorbe tutta la
    coda. Finche' vale 1e-7 e' irrilevante, ma va misurato e non supposto."""
    k = np.arange(max_gol + 1)
    logfatt = np.array([math.lgamma(i + 1) for i in k])
    lam = np.atleast_1d(np.asarray(lam, dtype=float))
    mu = np.atleast_1d(np.asarray(mu, dtype=float))
    # P(X <= max_gol) per una Poisson, calcolata in log per stabilita'
    def cdf(v):
        lp = -v[:, None] + k[None, :] * np.log(np.maximum(v[:, None], 1e-12)) \
             - logfatt[None, :]
        return np.exp(lp).sum(1)
    return 1.0 - cdf(lam) * cdf(mu)


def verifica_campioni(modello: ModelloPartita, casa, trasferta,
                      rng, n: int, max_gol: int = MAX_GOL) -> dict:
    """Estrae `n` modelli con `campiona_parametri` e li verifica tutti.

    E' la funzione da chiamare prima di generare uno scenario: dice quante
    estrazioni sarebbero da rigettare e con che margine. Non modifica nulla e
    non decide nulla al posto del chiamante."""
    campioni = modello.campiona_parametri(rng, n)
    esiti = [verifica_ammissibilita(c, casa, trasferta, max_gol)
             for c in campioni]
    rigetti = [i for i, e in enumerate(esiti) if not e["ammissibile"]]
    margini = np.array([e["margine_rho"] for e in esiti])
    code = np.array([e["massa_coda_massima"] for e in esiti])
    return {
        "n_estrazioni": int(n),
        "n_rigetti": len(rigetti),
        "indici_rigettati": rigetti[:50],
        "margine_rho_minimo": float(margini.min()),
        "margine_rho_medio": float(margini.mean()),
        "massa_coda_massima": float(code.max()),
        "rho_min": float(min(e["rho"] for e in esiti)),
        "rho_max": float(max(e["rho"] for e in esiti)),
    }
