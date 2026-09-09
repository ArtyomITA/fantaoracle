"""Contratto delle previsioni **per origine temporale**.

Una previsione senza origine non è verificabile. `b_predictions_{stagione}.json`
non porta una data: non si sa a quale istante informativo appartenga, quali
partite fossero già giocate quando è stata prodotta, né quali dati siano
entrati nel fit. Rigenerarlo oggi non lo renderebbe databile — cambierebbe solo
la data del file.

Questo modulo definisce che cosa deve dichiarare un artefatto per essere
utilizzabile in una validazione a origini mobili (Hyndman e Athanasopoulos,
*Forecasting: Principles and Practice*, capitolo sulla time series
cross-validation), e fornisce i calcoli che l'origine impone: quali partite
sono osservate, quante ne restano, e come trattare rinvii e recuperi.

## Le tre viste temporali, di nuovo

- **osservativa**: quando l'evento è accaduto;
- **al fit**: quali etichette sono entrate nella stima;
- **alla decisione**: che cosa era disponibile a chi decideva.

Un artefatto per origine le tiene distinte. `data_evento` non è
`data_pubblicazione`, e nessuna delle due è `data_acquisizione`.

## Che cosa questo modulo NON fa

Non rende databile un dato che non lo è. Se una feature esiste solo in una
versione corrente senza storia, il contratto lo registra come
`ricostruzione_retrospettiva` o `non_verificabile` — non lo promuove a
`disponibile_alla_decisione` perché oggi si riesce a scaricarlo.
"""
from __future__ import annotations

import dataclasses
import hashlib
import json
from pathlib import Path

import pandas as pd

# Come è nota la disponibilità di un ingresso all'origine dichiarata.
DISPONIBILE = "disponibile_alla_decisione"
RICOSTRUITO = "ricostruzione_retrospettiva"
NON_VERIFICABILE = "non_verificabile"
POSTERIORE = "posteriore_all_origine"

STATI_INGRESSO = (DISPONIBILE, RICOSTRUITO, NON_VERIFICABILE, POSTERIORE)

# Stato di una partita rispetto all'origine.
OSSERVATA = "osservata"
RESIDUA = "residua"
RINVIATA_SENZA_DATA = "rinviata_senza_data"


class ContrattoViolato(ValueError):
    """Il manifesto non è utilizzabile: manca o è incoerente."""


@dataclasses.dataclass(frozen=True)
class Ingresso:
    """Un dato o una feature, con la prova della sua disponibilità.

    `prova` non è opzionale per `DISPONIBILE`: dire che un valore era
    disponibile senza indicare come lo si sa è un'affermazione, non un
    contratto.
    """

    nome: str
    stato: str
    prova: str = ""
    fonte: str = ""
    data_pubblicazione: str | None = None
    data_acquisizione: str | None = None

    def __post_init__(self):
        if self.stato not in STATI_INGRESSO:
            raise ContrattoViolato(
                f"ingresso «{self.nome}»: stato «{self.stato}» sconosciuto, "
                f"ammessi {list(STATI_INGRESSO)}")
        if self.stato == DISPONIBILE and not self.prova.strip():
            raise ContrattoViolato(
                f"ingresso «{self.nome}» dichiarato disponibile alla decisione "
                "senza prova. Come si sa che lo era? Se non si sa, lo stato "
                f"è «{NON_VERIFICABILE}».")

    def utilizzabile(self) -> bool:
        """Solo `DISPONIBILE` entra in una previsione operativa.

        `RICOSTRUITO` è ammesso in un esperimento retrospettivo purché
        dichiarato; `NON_VERIFICABILE` e `POSTERIORE` no.
        """
        return self.stato == DISPONIBILE


def stato_partite(calendario: pd.DataFrame, origine, *,
                  colonna_data: str = "data") -> pd.DataFrame:
    """Marca ogni partita come osservata, residua o rinviata senza data.

    Il confronto è sulla **data effettiva**, non sul numero di giornata: con i
    rinvii una giornata può essere in parte giocata e in parte no, e contare
    per giornata sposta partite dalla parte sbagliata dell'origine.

    Una partita senza data non è né osservata né residua: è
    `rinviata_senza_data`, e va contata a parte. Trattarla come residua
    gonfierebbe l'orizzonte; trattarla come osservata la darebbe per giocata.
    """
    if colonna_data not in calendario.columns:
        raise ContrattoViolato(
            f"il calendario non ha la colonna «{colonna_data}»: senza date "
            "non si può separare l'osservato dal residuo se non per giornata, "
            "che è proprio l'errore da evitare")
    fuori = calendario.copy()
    date = pd.to_datetime(fuori[colonna_data], errors="coerce")
    o = pd.Timestamp(origine)
    fuori["stato_rispetto_origine"] = RINVIATA_SENZA_DATA
    fuori.loc[date.notna() & (date < o), "stato_rispetto_origine"] = OSSERVATA
    fuori.loc[date.notna() & (date >= o), "stato_rispetto_origine"] = RESIDUA
    return fuori


def partite_residue(calendario: pd.DataFrame, origine, *,
                    per: str | list[str] | None = None,
                    colonna_data: str = "data") -> dict:
    """Quante partite restano, in totale o per chiave.

    Restituisce anche le rinviate senza data, separate: chi consuma decide se
    includerle, ma non può ignorarle senza saperlo.
    """
    m = stato_partite(calendario, origine, colonna_data=colonna_data)
    if per is None:
        conta = m.stato_rispetto_origine.value_counts().to_dict()
        return {"osservate": int(conta.get(OSSERVATA, 0)),
                "residue": int(conta.get(RESIDUA, 0)),
                "rinviate_senza_data": int(conta.get(RINVIATA_SENZA_DATA, 0))}
    chiavi = [per] if isinstance(per, str) else list(per)
    fuori = {}
    for k, g in m.groupby(chiavi):
        c = g.stato_rispetto_origine.value_counts().to_dict()
        fuori[k if not isinstance(k, tuple) or len(k) > 1 else k[0]] = {
            "osservate": int(c.get(OSSERVATA, 0)),
            "residue": int(c.get(RESIDUA, 0)),
            "rinviate_senza_data": int(c.get(RINVIATA_SENZA_DATA, 0))}
    return fuori


def orizzonte(residue: int, *, minimo_finto: bool = False) -> int:
    """Le giornate su cui si divide una previsione di presenze.

    Con zero partite residue **non c'è previsione da fare**: alzare
    l'orizzonte a 1 per evitare la divisione per zero fabbrica un turno che non
    esiste e trasforma un errore in un numero plausibile. Qui si alza solo se
    lo si chiede esplicitamente, e chi lo chiede sa che sta approssimando.
    """
    residue = int(residue)
    if residue < 0:
        raise ContrattoViolato(f"partite residue negative: {residue}")
    if residue == 0 and not minimo_finto:
        raise ContrattoViolato(
            "zero partite residue: non c'è un orizzonte su cui prevedere. "
            "Usare `minimo_finto=True` solo sapendo che si sta inventando un "
            "turno.")
    return max(residue, 1)


@dataclasses.dataclass
class ManifestoOrigine:
    """Che cosa un artefatto per origine deve dichiarare.

    Ogni campo esiste perché la sua assenza ha già prodotto un errore:
    `stagione` e `origine` perché un file per stagione si sovrascrive e perde
    l'istante; `universo` perché una previsione su un insieme diverso non è
    confrontabile; `etichette_fino_a` perché un fit che vede oltre l'origine
    non è una previsione; `ingressi` perché una feature posteriore rende
    inutile tutto il resto.
    """

    stagione: str
    origine: str                       # data della decisione, ISO
    universo: list
    calendario_osservate: int
    calendario_residue: int
    calendario_rinviate_senza_data: int
    etichette_dal: str | None
    etichette_fino_a: str | None
    ingressi: list                     # di `Ingresso`
    modello: str
    versione_modello: str
    impronte: dict
    provenienza_temporale: str
    note: str = ""

    def __post_init__(self):
        if not self.universo:
            raise ContrattoViolato("universo vuoto")
        o = pd.Timestamp(self.origine)
        if self.etichette_fino_a is not None:
            fine = pd.Timestamp(self.etichette_fino_a)
            if fine > o:
                raise ContrattoViolato(
                    f"le etichette arrivano al {fine.date()}, oltre l'origine "
                    f"{o.date()}: il fit vede quello che dovrebbe prevedere")
        for i in self.ingressi:
            if not isinstance(i, Ingresso):
                raise ContrattoViolato(f"ingresso non tipizzato: {i!r}")
        posteriori = [i.nome for i in self.ingressi if i.stato == POSTERIORE]
        if posteriori:
            raise ContrattoViolato(
                f"ingressi posteriori all'origine: {posteriori}. Un artefatto "
                "che li contiene non è una previsione a quell'origine.")

    @property
    def utilizzabile_operativamente(self) -> bool:
        """Vero solo se ogni ingresso è dimostrato disponibile.

        Un artefatto con ingressi ricostruiti resta valido per un esperimento
        retrospettivo — purché nessuno lo chiami previsione operativa.
        """
        return all(i.utilizzabile() for i in self.ingressi)

    def ingressi_per_stato(self) -> dict:
        fuori = {}
        for i in self.ingressi:
            fuori.setdefault(i.stato, []).append(i.nome)
        return {k: sorted(v) for k, v in sorted(fuori.items())}

    def identificativo(self) -> str:
        """Nome stabile per l'artefatto: stagione, origine, impronta.

        Serve a non sovrascrivere: `b_predictions_2024-25.json` è un solo file
        per stagione, e ogni rigenerazione cancella la precedente.
        """
        crudo = json.dumps(
            {"stagione": self.stagione, "origine": self.origine,
             "modello": self.modello, "versione": self.versione_modello,
             "impronte": self.impronte, "universo": len(self.universo)},
            sort_keys=True, ensure_ascii=False)
        h = hashlib.sha256(crudo.encode("utf-8")).hexdigest()[:12]
        giorno = pd.Timestamp(self.origine).strftime("%Y%m%d")
        return f"{self.stagione}__origine{giorno}__{h}"

    def a_dizionario(self) -> dict:
        d = dataclasses.asdict(self)
        d["ingressi"] = [dataclasses.asdict(i) for i in self.ingressi]
        d["identificativo"] = self.identificativo()
        d["utilizzabile_operativamente"] = self.utilizzabile_operativamente
        d["ingressi_per_stato"] = self.ingressi_per_stato()
        d["universo"] = len(self.universo)
        d["universo_primi"] = [int(x) for x in list(self.universo)[:5]]
        return d

    def scrivi(self, cartella: Path) -> Path:
        cartella = Path(cartella)
        cartella.mkdir(parents=True, exist_ok=True)
        fuori = cartella / "manifesto_origine.json"
        fuori.write_text(json.dumps(self.a_dizionario(), ensure_ascii=False,
                                    indent=2), encoding="utf-8")
        return fuori


def leggi_manifesto(percorso: Path) -> dict:
    """Rilegge un manifesto e ne verifica i campi obbligatori."""
    d = json.loads(Path(percorso).read_text(encoding="utf-8"))
    obbligatori = ("stagione", "origine", "universo", "etichette_fino_a",
                   "ingressi", "modello", "versione_modello", "impronte",
                   "provenienza_temporale")
    mancanti = [c for c in obbligatori if c not in d]
    if mancanti:
        raise ContrattoViolato(f"manifesto incompleto, mancano: {mancanti}")
    return d
