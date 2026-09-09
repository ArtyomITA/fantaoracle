"""Contratto temporale del panel: chi lo produce lo dichiara, chi lo consuma lo verifica.

## Il difetto che questo modulo chiude

Il panel portava le colonne della vista al fit (`eleggibile_fit`,
`appartenenza_esito_fit`), ma il cutoff con cui erano state costruite viveva
solo dentro `l2_panel_qualita.json`, e nessun consumatore lo guardava. Due
conseguenze misurate:

- `l2_panel_qualita.json` riportava `data_fit = 2026-09-08` per **tutte e
  cinque** le stagioni, perché il predefinito dello script è «oggi». Un fit
  datato 2024 che avesse letto quei panel avrebbe consumato prove del 2026
  senza che niente glielo impedisse;
- un unico file per stagione cambiava significato a seconda dell'ultimo comando
  eseguito: `l2_panel_2024-25.parquet` poteva essere costruito con qualunque
  cutoff, e il nome non lo diceva.

Qui il cutoff entra nel **nome del file** e nei **metadati accanto al file**, e
il consumatore deve chiedere quello che gli serve. Se chiede una vista che non
esiste, o incompatibile con quella salvata, riceve un errore invece di dati
plausibili.

## Le tre date, e perché non sono la stessa cosa

- `data_fit` — il giorno in cui si addestra. Le prove posteriori non entrano
  nella vista al fit. Una stagione conclusa **prima** di questo giorno entra
  intera: il vincolo è sulle prove usate, non sul periodo osservato.
- `as_of_decisione` — il giorno in cui si decide, per la stagione bersaglio.
  Governa la vista alla decisione.
- `estendi_fino` — fin dove l'appartenenza vale in avanti per inferenza di
  continuità. È il primo giorno **non** coperto: gli intervalli sono `[dal, al)`.

## Che cosa NON garantisce

Che i numeri dentro il panel siano giusti. Garantisce che chi li legge sappia
con quali prove sono stati costruiti, e che non possa scambiare una vista per
un'altra senza accorgersene.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from pathlib import Path

import pandas as pd

# versione della trasformazione: cambia quando cambia il modo in cui il panel
# viene costruito, non quando cambiano i dati. Entra nella chiave della cache e
# nel confronto di compatibilita', cosi' un panel prodotto da un codice diverso
# non viene scambiato per uno equivalente.
VERSIONE_TRASFORMAZIONE = "2026-09-08.viste-temporali.1"


class ContrattoIncompatibile(RuntimeError):
    """Il panel salvato non risponde alla domanda che il consumatore fa."""


@dataclass
class ContrattoPanel:
    """Che cosa un panel dichiara di essere."""

    stagione: str
    data_fit: str | None = None
    as_of_decisione: str | None = None
    estendi_fino: str | None = None
    versione: str = VERSIONE_TRASFORMAZIONE
    fonti: dict = field(default_factory=dict)
    righe: int | None = None
    colonne: list | None = None
    costruito_il: str | None = None

    def chiave(self) -> str:
        """Identifica la combinazione (stagione, cutoff, orizzonte, versione)."""
        parti = [self.stagione,
                 self.data_fit or "-",
                 self.as_of_decisione or "-",
                 self.estendi_fino or "-",
                 self.versione]
        return "|".join(parti)

    def impronta(self) -> str:
        base = json.dumps({"chiave": self.chiave(), "fonti": self.fonti},
                          sort_keys=True)
        return hashlib.sha256(base.encode("utf-8")).hexdigest()

    def a_dizionario(self) -> dict:
        d = asdict(self)
        d["chiave"] = self.chiave()
        d["impronta"] = self.impronta()
        return d


def nome_panel(stagione: str, data_fit=None) -> str:
    """Il nome del file porta il cutoff: due fit diversi non si sovrascrivono.

    Senza cutoff resta il nome storico, che indica il panel **osservativo**,
    quello che si può usare per i bersagli e la descrizione storica ma non per
    costruire le informazioni di una decisione datata.
    """
    if data_fit is None:
        return f"l2_panel_{stagione}.parquet"
    d = pd.Timestamp(data_fit).strftime("%Y%m%d")
    return f"l2_panel_{stagione}__fit{d}.parquet"


def percorso_metadati(percorso_parquet: Path) -> Path:
    return percorso_parquet.with_suffix(".contratto.json")


def scrivi(percorso_parquet: Path, contratto: ContrattoPanel) -> Path:
    """Salva i metadati accanto al parquet."""
    p = percorso_metadati(percorso_parquet)
    p.write_text(json.dumps(contratto.a_dizionario(), indent=1),
                 encoding="utf-8")
    return p


def leggi(percorso_parquet: Path) -> ContrattoPanel | None:
    """I metadati di un panel, o `None` se il file non li porta.

    Un panel senza contratto non è un panel invalido: è un panel di cui non
    sappiamo niente, e chi lo consuma con un cutoff esplicito deve rifiutarlo.
    """
    p = percorso_metadati(percorso_parquet)
    if not p.exists():
        return None
    d = json.loads(p.read_text(encoding="utf-8"))
    d.pop("chiave", None)
    d.pop("impronta", None)
    return ContrattoPanel(**d)


def verifica(contratto: ContrattoPanel | None, percorso: Path, *,
             stagione: str, data_fit=None, esigi_vista_al_fit: bool = True
             ) -> ContrattoPanel:
    """Il panel salvato risponde alla domanda che stiamo facendo?

    Alza `ContrattoIncompatibile` invece di restituire dati plausibili. Le
    ragioni per cui rifiuta sono tutte casi in cui il consumatore starebbe
    usando informazione che non gli spetta, o non saprebbe dire quale ha usato.
    """
    if contratto is None:
        if data_fit is None and not esigi_vista_al_fit:
            # panel osservativo chiesto senza cutoff: non serve un contratto
            return ContrattoPanel(stagione=stagione)
        raise ContrattoIncompatibile(
            f"{percorso.name} non porta un contratto temporale, ma il "
            f"consumatore chiede la vista al fit del "
            f"{pd.Timestamp(data_fit).date() if data_fit else 'non dichiarato'}. "
            "Ricostruisci il panel con `--data-fit`, oppure chiedi "
            "esplicitamente la vista osservativa.")
    if contratto.stagione != stagione:
        raise ContrattoIncompatibile(
            f"{percorso.name} dichiara la stagione {contratto.stagione}, "
            f"chiesta {stagione}")
    if contratto.versione != VERSIONE_TRASFORMAZIONE:
        raise ContrattoIncompatibile(
            f"{percorso.name} e' stato prodotto dalla versione "
            f"{contratto.versione}, questa e' {VERSIONE_TRASFORMAZIONE}: "
            "la trasformazione e' cambiata e il panel va ricostruito")
    if data_fit is not None:
        chiesto = pd.Timestamp(data_fit)
        if contratto.data_fit is None:
            raise ContrattoIncompatibile(
                f"{percorso.name} non ha una vista al fit, ma ne e' stata "
                f"chiesta una al {chiesto.date()}")
        salvato = pd.Timestamp(contratto.data_fit)
        if salvato != chiesto:
            # Un panel costruito con un fit PIU' TARDO contiene prove che al
            # fit chiesto non c'erano: e' il caso del backtest 2024 su panel
            # costruiti nel 2026. Un panel con fit piu' PRECOCE non contiene
            # prove che avremmo potuto usare: e' conservativo ma non e' quello
            # che abbiamo chiesto, e la differenza va vista, non subita.
            verso = "successivo" if salvato > chiesto else "anteriore"
            raise ContrattoIncompatibile(
                f"{percorso.name} ha la vista al fit del {salvato.date()}, "
                f"{verso} a quello chiesto ({chiesto.date()}). "
                + ("Contiene prove che al cutoff chiesto non esistevano."
                   if salvato > chiesto else
                   "Non contiene prove che al cutoff chiesto erano disponibili.")
                + " Ricostruisci il panel con `--data-fit "
                f"{chiesto.date()}`.")
    return contratto


def carica_panel(cartella: Path, stagione: str, *, data_fit=None,
                 esigi_vista_al_fit: bool = True,
                 colonne: list | None = None
                 ) -> tuple[pd.DataFrame, ContrattoPanel]:
    """Carica il panel che risponde a questa domanda, o alza.

    Restituisce anche il contratto, perché chi consuma deve **registrare** che
    cosa ha consumato: senza quello, un rapporto dice quali numeri sono usciti
    ma non su quali dati.
    """
    percorso = cartella / nome_panel(stagione, data_fit)
    if not percorso.exists() and data_fit is not None:
        # il file per quel fit non c'e': si guarda se quello generico lo e'
        generico = cartella / nome_panel(stagione)
        c = leggi(generico)
        if c is not None and c.data_fit is not None and \
                pd.Timestamp(c.data_fit) == pd.Timestamp(data_fit):
            percorso = generico
    if not percorso.exists():
        raise ContrattoIncompatibile(
            f"manca {percorso.name}: nessun panel per la stagione {stagione} "
            + (f"con la vista al fit del {pd.Timestamp(data_fit).date()}"
               if data_fit else "nella vista osservativa"))
    contratto = verifica(leggi(percorso), percorso, stagione=stagione,
                         data_fit=data_fit,
                         esigi_vista_al_fit=esigi_vista_al_fit)
    return pd.read_parquet(percorso, columns=colonne), contratto


def impronta_file(percorso: Path) -> str | None:
    """SHA-256 di un file sorgente, per registrare che cosa e' stato letto."""
    if not Path(percorso).exists():
        return None
    h = hashlib.sha256()
    with open(percorso, "rb") as f:
        for blocco in iter(lambda: f.read(1 << 20), b""):
            h.update(blocco)
    return h.hexdigest()


def carica_panel_multi(cartella: Path, stagioni, *, data_fit=None,
                       esigi_vista_al_fit: bool = True,
                       colonne: list | None = None
                       ) -> tuple[pd.DataFrame, dict]:
    """Più stagioni con lo **stesso** contratto, concatenate.

    Sostituisce il `glob("l2_panel_*.parquet")` che i consumatori facevano: con
    i file indicizzati per cutoff quel glob raccoglierebbe tutte le varianti
    dello stesso panel e duplicherebbe le righe. Qui le stagioni si chiedono
    per nome e il cutoff è uno solo per tutte, perché un fit che mescolasse
    stagioni costruite con cutoff diversi non sarebbe un fit datato.
    """
    pezzi, contratti = [], {}
    for s in stagioni:
        try:
            d, c = carica_panel(cartella, s, data_fit=data_fit,
                                esigi_vista_al_fit=esigi_vista_al_fit,
                                colonne=colonne)
        except ContrattoIncompatibile as e:
            if data_fit is None and "manca" in str(e):
                # una stagione senza panel non è un errore quando non si chiede
                # un cutoff: può semplicemente non essere stata costruita
                continue
            raise
        pezzi.append(d)
        contratti[s] = c.a_dizionario()
    if not pezzi:
        raise ContrattoIncompatibile(
            f"nessun panel caricato per {list(stagioni)}"
            + (f" con la vista al fit del {pd.Timestamp(data_fit).date()}"
               if data_fit else ""))
    P = pd.concat(pezzi, ignore_index=True)
    if "data" in P.columns:
        P["data"] = pd.to_datetime(P["data"])
    return P, contratti


def costruisci_universo(cartella: Path, stagione: str, *,
                        rose_da: str = "listone") -> tuple[dict, dict, dict, dict]:
    """L'universo dei giocatori e le rose per squadra, uguali per tutti.

    Prima questa costruzione era duplicata: `l2_genera_cubo.py` era passato a
    `squadra_listone`, `l2_banco_confronto.py` usava ancora `squadra`. I due
    lavoravano quindi su rose diverse, e il confronto fra i loro generatori non
    era a parità di universo.

    `rose_da` sceglie la fotografia, e la scelta è dichiarata invece che
    implicita nella colonna:

    - `listone` — la squadra dichiarata dal listone di inizio stagione. È la
      sola coerente con un'asta che si tiene prima del campionato.
    - `squadra` — la squadra corrente secondo la fonte all'ultimo
      scaricamento. Corretta quando la decisione è posteriore a quello
      scaricamento, per esempio un'asta a mercato già chiuso.

    **`squadra_listone` non è una certificazione temporale.** È la squadra che
    il listone dichiarava quando è stato costruito, e il listone stesso può
    essere stato aggiornato: chi la usa per una data di decisione deve
    verificare quale fotografia rappresenta, non fidarsi del nome della
    colonna. La diagnostica restituita dice quanti giocatori differiscono fra
    le due colonne, che è la misura di quanto la scelta conta.

    Ritorna `(rose, ruolo, squadra, diagnostica)`.
    """
    import json as _json

    percorso = cartella / f"players_{stagione}.parquet"
    lst = pd.read_parquet(percorso, columns=["master_id", "ruolo", "squadra",
                                             "squadra_listone"])
    diverse = int((lst["squadra"] != lst["squadra_listone"]).sum())
    colonna = "squadra_listone" if rose_da == "listone" else "squadra"
    scelta = lst[colonna].fillna(lst["squadra"])

    sigle_file = cartella / "_match" / "team_maps.json"
    sigle = _json.loads(sigle_file.read_text("utf-8")) if sigle_file.exists() else {}
    inv = {v: k for k, v in sigle.get(stagione, {}).items()}
    estesa = scelta.map(inv).fillna(scelta)

    rose = {sq: list(g) for sq, g in lst.master_id.groupby(estesa)}
    ruolo = dict(zip(lst.master_id, lst.ruolo))
    squadra = dict(zip(lst.master_id, estesa))
    diagnostica = {
        "stagione": stagione,
        "rose_da": rose_da,
        "colonna": colonna,
        "giocatori": int(len(lst)),
        "squadre": len(rose),
        "squadra_diversa_dal_listone": diverse,
        "impronta_listone": impronta_file(percorso),
        "avvertenza": (
            "`squadra_listone` e' la squadra dichiarata dal listone quando e' "
            "stato costruito, non una certificazione della data: chi la usa "
            "per una decisione datata deve verificare quale fotografia "
            "rappresenta."),
    }
    return rose, ruolo, squadra, diagnostica
