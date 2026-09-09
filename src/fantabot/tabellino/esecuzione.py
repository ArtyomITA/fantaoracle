"""Destinazioni di esecuzione: isolamento, rifiuto, scrittura atomica.

## Il difetto che chiude

Il banco e il progressivo scrivevano su nomi fissi dentro `data/l2/`. Due
conseguenze, entrambe verificate:

- una prova esplorativa a quattro scenari ha sovrascritto un verdetto
  pubblicato, perché il nome del file è lo stesso;
- due esecuzioni consecutive non sono distinguibili a posteriori: chi legge
  `banco_verdetto_2024-25.csv` non sa da quale esecuzione venga.

## Il contratto

Ogni esecuzione ha una **cartella propria**, il cui nome porta stagione,
istante e identificativo. Dentro c'è `esecuzione.json` con la configurazione,
i semi, gli scenari e le impronte degli ingressi.

- una destinazione già occupata viene **rifiutata**, non sovrascritta;
- si può riprendere una destinazione esistente solo dichiarandolo, e solo se
  configurazione e impronte coincidono con quelle registrate;
- le prove piccole hanno una radice diversa (`data/l2/prove/`) da quella dei
  risultati pubblicati (`data/l2/esecuzioni/`): una prova non può finire dove
  sta un risultato;
- la scrittura è atomica: file temporaneo e poi `os.replace`, così una
  scrittura interrotta non lascia un artefatto mezzo scritto che sembra buono;
- il puntatore `corrente` si aggiorna **solo dopo** che la verifica è passata.
  Finché non passa, «corrente» resta l'esecuzione precedente.

## Che cosa NON fa

Non risolve la provenienza degli artefatti già esistenti: quelli scritti prima
di questo contratto non hanno un `esecuzione.json`, e per loro la risposta
onesta è «provenienza incompleta». Un'impronta calcolata oggi identifica i
byte, non certifica l'esperimento passato.
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

VERSIONE_CONTRATTO = "2026-09-09.esecuzioni.1"

RADICE_PUBBLICATE = "esecuzioni"
RADICE_PROVE = "prove"


class DestinazioneOccupata(RuntimeError):
    """La cartella esiste già e non è stata dichiarata una ripresa."""


class RipresaIncompatibile(RuntimeError):
    """Ripresa chiesta su una destinazione con un'altra configurazione."""


def impronta_file(percorso) -> str | None:
    p = Path(percorso)
    if not p.exists() or not p.is_file():
        return None
    h = hashlib.sha256()
    with p.open("rb") as f:
        for blocco in iter(lambda: f.read(1 << 20), b""):
            h.update(blocco)
    return h.hexdigest()


def identificativo(configurazione: dict) -> str:
    """Identificativo deterministico della configurazione.

    Due esecuzioni con la stessa configurazione hanno lo stesso
    identificativo: è quello che permette di riconoscere una ripresa. L'istante
    sta nel nome della cartella, non qui, perché altrimenti nessuna ripresa
    sarebbe mai riconoscibile.
    """
    testo = json.dumps(configurazione, ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(testo.encode("utf-8")).hexdigest()[:12]


@dataclass
class Esecuzione:
    """Una destinazione aperta, con la sua configurazione registrata."""

    cartella: Path
    identificativo: str
    configurazione: dict
    istante: str
    ripresa: bool = False
    scritti: list = field(default_factory=list)

    # ------------------------------------------------------------------ io
    def percorso(self, nome: str) -> Path:
        return self.cartella / nome

    def scrivi_testo(self, nome: str, testo: str) -> Path:
        return self._atomico(nome, lambda p: p.write_text(testo,
                                                          encoding="utf-8"))

    def scrivi_json(self, nome: str, dato) -> Path:
        return self.scrivi_testo(nome, json.dumps(dato, ensure_ascii=False,
                                                  indent=2))

    def scrivi_tabella(self, nome: str, tabella) -> Path:
        if nome.endswith(".parquet"):
            return self._atomico(nome, lambda p: tabella.to_parquet(p,
                                                                    index=False))
        return self._atomico(nome, lambda p: tabella.to_csv(p, index=False))

    def _atomico(self, nome: str, scrittore) -> Path:
        """Scrive su un temporaneo nella stessa cartella, poi rinomina.

        `os.replace` è atomico sullo stesso volume: o c'è il file vecchio o
        c'è quello nuovo, mai un file mezzo scritto che sembra completo.
        """
        finale = self.cartella / nome
        finale.parent.mkdir(parents=True, exist_ok=True)
        fd, temporaneo = tempfile.mkstemp(dir=str(finale.parent),
                                          prefix=f".{nome}.", suffix=".parziale")
        os.close(fd)
        temporaneo = Path(temporaneo)
        try:
            scrittore(temporaneo)
            os.replace(temporaneo, finale)
        except BaseException:
            temporaneo.unlink(missing_ok=True)
            raise
        if nome not in self.scritti:
            self.scritti.append(nome)
        return finale

    def _pulisci_residui(self) -> list:
        """Toglie i temporanei di una scrittura interrotta di netto.

        `os.replace` protegge il file finale, ma un processo ucciso (kill,
        crash, blackout) non esegue il `finally` e lascia un `.parziale`. Il
        nome lo dichiara e nessuno lo scambia per un artefatto buono, ma
        accumularli sporca la cartella.
        """
        tolti = []
        for p in self.cartella.glob(".*.parziale"):
            p.unlink(missing_ok=True)
            tolti.append(p.name)
        return tolti

    def registra(self) -> Path:
        """Scrive `esecuzione.json`. Va chiamata dopo aver scritto gli output,
        così l'elenco dei file prodotti è completo."""
        return self.scrivi_json("esecuzione.json", {
            "versione": VERSIONE_CONTRATTO,
            "identificativo": self.identificativo,
            "istante": self.istante,
            "ripresa": self.ripresa,
            "configurazione": self.configurazione,
            "file": sorted(x for x in self.scritti
                           if x not in ("esecuzione.json", NOME_LUCCHETTO)),
            "impronte_uscite": {
                x: impronta_file(self.cartella / x)
                for x in sorted(self.scritti)
                if x not in ("esecuzione.json", NOME_LUCCHETTO)
                and (self.cartella / x).exists()},
        })


NOME_LUCCHETTO = ".lucchetto"


def _acquisisci(cartella: Path) -> None:
    """Lucchetto esclusivo sulla cartella, per la ripresa concorrente.

    `O_CREAT | O_EXCL` fallisce se il file esiste: e' la primitiva atomica che
    `exists()` seguito da `mkdir(exist_ok=True)` non e'. Il lucchetto viene
    rilasciato quando l'esecuzione si registra, o a mano con `rilascia`.
    """
    import os as _os
    p = cartella / NOME_LUCCHETTO
    try:
        fd = _os.open(str(p), _os.O_CREAT | _os.O_EXCL | _os.O_WRONLY)
    except FileExistsError:
        raise DestinazioneOccupata(
            f"{cartella} e' gia' in uso da un'altra esecuzione "
            f"(lucchetto {p.name}). Se l'esecuzione precedente e' morta, "
            "togli il lucchetto a mano dopo aver controllato che nessuno "
            "stia scrivendo.")
    _os.write(fd, str(_os.getpid()).encode("ascii"))
    _os.close(fd)


def rilascia(cartella: Path) -> bool:
    """Toglie il lucchetto. Vero se c'era."""
    p = Path(cartella) / NOME_LUCCHETTO
    if p.exists():
        p.unlink()
        return True
    return False


def apri(radice: Path, stagione: str, configurazione: dict, *,
         istante: str, prova: bool = False, riprendi: bool = False,
         destinazione: str | Path | None = None) -> Esecuzione:
    """Apre una destinazione di esecuzione, rifiutando quelle occupate.

    Parametri
    ---------
    radice
        di solito `data/l2`. Le prove finiscono sotto `prove/`, i risultati
        pubblicabili sotto `esecuzioni/`: una prova non può scrivere dove sta
        un risultato nemmeno per sbaglio.
    istante
        marca temporale, passata da fuori perché il nome della cartella sia
        deciso dal chiamante e riproducibile nei test.
    riprendi
        ammette una destinazione già esistente, ma solo se la configurazione
        registrata coincide con quella chiesta.
    """
    # La modalita' entra nell'identificativo: senza, una prova esplorativa e
    # un risultato pubblicabile con la stessa configurazione avevano lo stesso
    # identificativo, e quel campo finisce dentro gli artefatti come unica
    # traccia di provenienza. Non distingueva quello che deve distinguere.
    configurazione = dict(configurazione, modalita=("prova" if prova
                                                    else "pubblicata"))
    ident = identificativo(configurazione)
    sotto = RADICE_PROVE if prova else RADICE_PUBBLICATE
    if destinazione is not None:
        cartella = Path(destinazione)
        # R9: `--destinazione` non deve scavalcare la separazione delle radici.
        # Una prova che scrive dove stanno i risultati e' esattamente il caso
        # che il contratto esiste per impedire.
        atteso = (Path(radice) / sotto).resolve()
        try:
            cartella.resolve().relative_to(atteso)
        except ValueError:
            if (Path(radice) / (RADICE_PUBBLICATE if prova else RADICE_PROVE)
                    ).resolve() in cartella.resolve().parents:
                raise DestinazioneOccupata(
                    f"{cartella} sta sotto la radice sbagliata per una "
                    f"esecuzione {'di prova' if prova else 'pubblicabile'}: "
                    f"le due radici sono separate apposta.")
    else:
        cartella = Path(radice) / sotto / f"{stagione}__{istante}__{ident}"

    reg = cartella / "esecuzione.json"
    # C: ACQUISIZIONE ESCLUSIVA. `exists()` seguito da `mkdir(exist_ok=True)`
    # non e' atomico: due processi possono superare insieme il controllo e
    # aprire la stessa destinazione, e il secondo registro sovrascrive il
    # primo. Riprodotto con due fili e una barriera sul controllo di
    # esistenza. `mkdir` senza `exist_ok` e' invece atomico: o lo crea questo
    # processo, o alza `FileExistsError`.
    if not cartella.exists() and not riprendi:
        cartella.parent.mkdir(parents=True, exist_ok=True)
        try:
            cartella.mkdir()                       # esclusivo, senza exist_ok
        except FileExistsError:
            raise DestinazioneOccupata(
                f"{cartella} e' stata creata da un'altra esecuzione mentre "
                "questa la apriva. Due corse non condividono una "
                "destinazione.")
        e = Esecuzione(cartella=cartella, identificativo=ident,
                       configurazione=configurazione, istante=istante)
        e.registra()
        return e
    if cartella.exists():
        # R7: il rifiuto guardava il CONTENUTO. Fra `mkdir` e la prima
        # scrittura la cartella e' vuota, quindi due corse aperte insieme
        # passavano entrambe e la seconda sovrascriveva. Adesso conta
        # l'esistenza, e `esecuzione.json` viene scritto subito: una
        # destinazione aperta e' gia' occupata.
        if not riprendi:
            raise DestinazioneOccupata(
                f"{cartella} esiste gia'. Una destinazione occupata non viene "
                "sovrascritta: scegli un'altra destinazione, oppure dichiara "
                "una ripresa esplicita.")
        if not reg.exists():
            raise RipresaIncompatibile(
                f"{cartella} non ha `esecuzione.json`: non si puo' verificare "
                "che la ripresa riguardi la stessa configurazione.")
        vecchia = json.loads(reg.read_text("utf-8"))
        if vecchia.get("identificativo") != ident:
            raise RipresaIncompatibile(
                f"la configurazione non coincide: registrata "
                f"{vecchia.get('identificativo')}, chiesta {ident}. Una "
                "ripresa deve avere la stessa configurazione e le stesse "
                "impronte degli ingressi.")
        # la ripresa concorrente ha lo stesso problema: due processi che
        # riprendono la stessa cartella si sovrascrivono il registro. Il
        # lucchetto e' un file creato in modo esclusivo.
        _acquisisci(cartella)
        e = Esecuzione(cartella=cartella, identificativo=ident,
                       configurazione=configurazione, istante=istante,
                       ripresa=True,
                       # R11: la ripresa ripartiva con l'elenco vuoto, e il
                       # registro finale non descriveva piu' la cartella
                       scritti=list(vecchia.get("file") or []))
        e._pulisci_residui()
        return e
    # ci si arriva solo con `riprendi=True` su una destinazione che non esiste:
    # non c'e' niente da riprendere
    raise RipresaIncompatibile(
        f"{cartella} non esiste: non c'e' nessuna esecuzione da riprendere.")


# --------------------------------------------------------------------------
# puntatore all'esecuzione corrente
# --------------------------------------------------------------------------

def percorso_puntatore(radice: Path, stagione: str) -> Path:
    return Path(radice) / "corrente" / f"{stagione}.json"


def leggi_corrente(radice: Path, stagione: str) -> Path | None:
    """La cartella dell'esecuzione corrente, o `None` se non ce n'è una."""
    p = percorso_puntatore(radice, stagione)
    if not p.exists():
        return None
    d = json.loads(p.read_text("utf-8"))
    c = Path(d.get("cartella", ""))
    if not c.is_absolute():
        c = Path(radice).parent.parent / c
    return c if c.exists() else None


def promuovi_a_corrente(radice: Path, stagione: str, es: Esecuzione,
                        *, verifica: dict) -> Path:
    """Aggiorna il puntatore `corrente`. Solo dopo una verifica passata.

    **Riferimento corrente a un esperimento verificato, non attivazione di un
    modello nel bot.** Sono due cose diverse: questo puntatore dice quale
    esecuzione i lettori devono usare per leggere i risultati; non promuove
    niente in produzione e non tocca i pack operativi.

    NON ANCORA COLLEGATA. Nessuno script la chiama, e sul disco non esistono
    ne' `data/l2/corrente` ne' `data/l2/esecuzioni`: il consumatore
    (`l2_inferenza_banco.cartella_stagione`) ricade sempre sui nomi piatti.
    Collegarla richiede che il produttore esegua la verifica dopo aver
    scritto, che e' un cambiamento del flusso e non di questa funzione.

    Il campo `verifica` conserva l'esito che ha autorizzato la promozione: se
    un giorno il puntatore indicasse un'esecuzione non verificata, si vedrebbe
    da qui.
    """
    if not verifica.get("passata"):
        raise RuntimeError(
            "il puntatore `corrente` si aggiorna solo dopo una verifica "
            f"passata; ricevuto {verifica!r}")
    # B: l'associazione all'esecuzione e' OBBLIGATORIA, non facoltativa. Prima
    # `{'passata': True}` senza altro bastava, e una corsa di PROVA con un file
    # finto dentro diventava corrente.
    quale = verifica.get("esecuzione")
    if not quale:
        raise RuntimeError(
            "la verifica non dice a quale esecuzione si riferisce: "
            "`verifica['esecuzione']` e' obbligatorio.")
    if quale != es.identificativo:
        raise RuntimeError(
            f"la verifica riguarda l'esecuzione {quale}, non "
            f"{es.identificativo}: un puntatore non si promuove con la "
            "verifica di un'altra corsa.")
    if es.configurazione.get("modalita") == "prova":
        raise RuntimeError(
            "una corsa di prova non diventa corrente: le prove esplorative "
            "stanno in una radice separata proprio per questo.")
    reg = es.cartella / "esecuzione.json"
    if not reg.exists():
        raise RuntimeError(f"{es.cartella} non ha `esecuzione.json`")
    m = json.loads(reg.read_text("utf-8"))
    attesi = m.get("file") or []
    if not attesi:
        raise RuntimeError(
            f"{es.cartella} non contiene nessun artefatto oltre al registro: "
            "non c'e' niente da promuovere.")
    mancanti = [f for f in attesi if not (es.cartella / f).exists()]
    if mancanti:
        raise RuntimeError(f"artefatti mancanti: {mancanti[:4]}")
    alterati = [f for f, h in (m.get("impronte_uscite") or {}).items()
                if h and impronta_file(es.cartella / f) != h]
    if alterati:
        raise RuntimeError(
            f"artefatti modificati dopo la registrazione: {alterati[:4]}. "
            "Una verifica vale per i byte che ha verificato.")
    p = percorso_puntatore(radice, stagione)
    p.parent.mkdir(parents=True, exist_ok=True)
    try:
        rel = es.cartella.relative_to(Path(radice).parent.parent)
    except ValueError:
        rel = es.cartella
    testo = json.dumps({
        "stagione": stagione,
        "cartella": str(rel).replace("\\", "/"),
        "identificativo": es.identificativo,
        "istante": es.istante,
        "verifica": verifica,
    }, ensure_ascii=False, indent=2)
    fd, temporaneo = tempfile.mkstemp(dir=str(p.parent), prefix=".corrente.")
    os.close(fd)
    Path(temporaneo).write_text(testo, encoding="utf-8")
    os.replace(temporaneo, p)
    return p


def copia_in(es: Esecuzione, sorgente: Path, nome: str | None = None) -> Path:
    """Copia un file dentro la destinazione, in modo atomico."""
    nome = nome or Path(sorgente).name
    return es._atomico(nome, lambda p: shutil.copyfile(sorgente, p))


def impronte_ingressi(percorsi=(), moduli=()) -> dict:
    """Impronte dei file letti e dei moduli che li interpretano.

    Il manifesto registrava listone, partite e lo script principale: non i
    **panel realmente letti** e non i moduli importati. Due esecuzioni con lo
    stesso script ma un `generatore.py` diverso producono cose diverse e
    avevano lo stesso manifesto.
    """
    import importlib
    fuori = {}
    for p in percorsi:
        p = Path(p)
        fuori[str(p).replace("\\", "/")] = impronta_file(p)
    for nome in moduli:
        try:
            m = importlib.import_module(nome)
            f = getattr(m, "__file__", None)
            if f:
                fuori[nome] = impronta_file(f)
        except Exception:
            fuori[nome] = None
    return fuori


MODULI_RILEVANTI = (
    "fantabot.tabellino.generatore",
    "fantabot.tabellino.partecipazione",
    "fantabot.tabellino.partita",
    "fantabot.tabellino.voto",
    "fantabot.tabellino.eventi",
    "fantabot.tabellino.configurazione",
    "fantabot.tabellino.inferenza",
    "fantabot.tabellino.presenze",
    "fantabot.tabellino.contratto",
    "fantabot.tabellino.esecuzione",
    "fantabot.tabellino.calibrazione",
)
