"""Inferenza per il confronto appaiato del banco: dipendenze e ensemble finiti.

Questo modulo raccoglie le due correzioni che il ramo di ricerca
`data/l2/r4_ricerca/RAPPORTO.md` ha stabilito e verificato, e nient'altro.
Non decide nulla di sostanziale: non fissa tolleranze di equivalenza, non
promuove generatori, non sceglie quale bersaglio conti fra «valutare l'ensemble
a m membri» e «stimare il generatore». Riporta entrambi.

## 1. L'intervallo del banco era troppo stretto, e si sa di quanto

Il verdetto precedente ricampionava le **righe** (giocatore, giornata) come se
fossero indipendenti. Non lo sono: le righe della stessa partita condividono il
risultato e gli eventi, quelle dello stesso giocatore condividono forma, ruolo e
storia. Le due dimensioni **si incrociano** e non sono annidate, quindi non
basta scegliere la più grossolana.

Cameron & Miller (2015), sezione V, equazione (21), danno la varianza two-way:

    V_2way = V_partita + V_giocatore − V_intersezione

L'intersezione fra «partita» e «giocatore» è la **singola riga**, perché un
giocatore compare una volta sola in una partita. Quindi il termine da sottrarre
è esattamente la varianza robusta senza grappoli, cioè **ciò che il banco
calcolava prima**: il metodo vecchio non è una stima sbagliata di `V_2way`, è
uno dei tre addendi, quello con il segno meno. La fonte nomina l'errore per
esteso («one error that we find some practitioners make, which is to cluster at
the intersection of the two groupings»).

Misurato in simulazione su un disegno con la geometria del banco (38 giornate,
679 giocatori, 380 partite, correlazioni 0,049 e 0,096 dichiarate prima di
eseguire, 600 repliche):

| errore standard | rapporto sul vero | copertura al 95 % |
|---|---:|---:|
| righe indipendenti (metodo vecchio) | 0,356 | **50,7 %** |
| one-way su partita | 0,739 | 84,2 % |
| two-way, equazione (21) | 0,998 | **92,8 %** |

Un intervallo nominale al 95 % costruito sulle righe copriva il vero valore la
metà delle volte. Il residuo fra 92,8 % e 95 % è la distorsione verso il basso
del CRVE che la fonte dichiara non eliminata dalla correzione finita.

## 2. Il CRPS empirico penalizza un ensemble per il fatto di essere finito

Con `m` scenari, `E[CRPS_emp] = CRPS_vero + E|X−X'| / (2m)`: distorsione
positiva. Ferro (2013) definisce il punteggio **equo**, che è lo stimatore non
distorto del punteggio che si otterrebbe con `m → ∞`. In forma chiusa la
correzione è la dispersione di ensemble divisa per `m − 1`, sia per il CRPS sia
per il Brier.

**La correzione non si cancella nelle differenze**, perché dipende
dall'ensemble: si annulla se e solo se i due bracci hanno la stessa dispersione
media. Con `m = 30` il segno di un confronto si ribalta quando il divario di
dispersione supera `|Δ| · 29`; per il confronto `C1 − I1` del 2024-25 bastano
0,090 fantavoto di divario. Per questo la dispersione media per braccio va
**pubblicata**: senza quella colonna nessuno può controllare la cosa.

**L'ipotesi di Ferro, verificata invece che postulata.** La correzione equa
chiede membri scambiabili e incorrelati a coppie. Avevo scritto che i nostri
scenari, condividendo lo stesso adattamento, sarebbero **positivamente
correlati**, e quindi che la correzione standard fosse un limite inferiore.
**Non segue, ed è sbagliato**: condizionatamente a un fit *fissato*, estrazioni
separate possono benissimo essere indipendenti, ed è ciò che accade qui.

Percorso verificato nel codice: `generatore.rng_di(seme, scenario, chiave)`
costruisce `default_rng([seme, scenario, crc32(chiave)])`, quindi ogni scenario
ha il proprio flusso; `generatore.py` estrae i parametri **per scenario**
(`campiona_parametri(rng_di(seme, s, "forze"), ...)`), e gli shock di squadra
usano chiavi che contengono lo scenario. Verifica empirica su 300 scenari × 200
estrazioni: correlazione media fra scenari `+0,00001` con deviazione standard
`0,0711`, contro `0,0707` attesa sotto indipendenza.

Quindi, **con il fit tenuto fisso** — che è il condizionamento dichiarato di
questo banco — i membri dell'ensemble sono indipendenti e identicamente
distribuiti, e la correzione standard di Ferro è quella giusta, non un limite
inferiore. L'equazione (6) di Ferro, con la correzione maggiorata per membri
correlati, serve a un caso diverso: quando il fit stesso è trattato come
casuale, e allora cambia anche il bersaglio della stima.

Resta vero, e va tenuto distinto, che **l'incertezza dell'adattamento non entra
in nessuna di queste quantità**: è un limite del disegno, non una distorsione
del punteggio.

## 3. Il rumore Monte Carlo si misura con semi ripetuti

Lo scenario non è una partizione delle righe: il punteggio di ogni riga è
funzione di tutti gli `m` scenari, quindi **non** esiste un bootstrap *a
grappoli sulle righe* che abbia lo scenario come grappolo.

Avevo tratto da qui una conclusione più forte di quella che segue: che il
rumore Monte Carlo non fosse ricampionabile affatto. **Non è vero.** Si possono
ricampionare i **vettori di scenario interi** — estrarre con ripetizione `m`
scenari fra gli `m` disponibili e ricalcolare il punteggio da capo — e ottenere
una stima della varianza Monte Carlo. La non linearità del CRPS rende il
ricalcolo obbligatorio, non impossibile.

Qui si continua a usare **`R` semi distinti**, che è un metodo pratico già
disponibile e non richiede di implementare niente di nuovo: `R` semi a `m`
scenari costano quanto una sola esecuzione a `R·m` scenari, e in più misurano
la varianza Monte Carlo, che una sola esecuzione non può misurare. La scelta è
di comodità, non di necessità matematica.

## 4. Che cosa questo modulo NON copre

- l'incertezza sull'adattamento del modello (un solo cubo, una sola stima);
- la variazione fra stagioni: con due stagioni i grappoli sono G = 2 e non
  esiste inferenza (con G = 2 il wild cluster bootstrap dà `p ≥ 1/2`), quindi i
  verdetti si producono **una stagione per volta**;
- il riuso della validazione: l'intervallo corregge il campionamento, non la
  selezione;
- il passaggio da «l'intervallo contiene lo zero» a «i bracci sono
  equivalenti»: serve una tolleranza dichiarata prima, che questo modulo non
  fissa.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

try:  # `scipy` c'e' nel progetto; il ripiego serve solo a non far cadere il
    # modulo in un ambiente ridotto, e dichiara di essere un ripiego.
    from scipy import stats as _st
except Exception:                                       # pragma: no cover
    _st = None


# --------------------------------------------------------------------------
# punteggi equi (Ferro 2013)
# --------------------------------------------------------------------------

def dispersione_crps(campioni: np.ndarray) -> float:
    """`(1 / (2 m^2)) * sum_i sum_j |x_i - x_j|`, in O(m log m).

    E' il termine `0,5 * b` che il banco calcola gia' dentro il CRPS
    campionario: qui e' esposto perche' serve sia alla correzione equa sia
    alla colonna diagnostica per braccio.
    """
    x = np.sort(np.asarray(campioni, dtype=float))
    m = x.size
    if m < 2:
        return float("nan")
    b = 2.0 * np.sum((2 * np.arange(1, m + 1) - m - 1) * x) / (m * m)
    return float(0.5 * b)


def crps_equo(crps_empirico, dispersione, m: int):
    """Il CRPS equo a partire da quello empirico e dalla dispersione.

    Identita' esatta, verificata a 5,0e-16 nel ramo di ricerca:

        CRPS_emp - CRPS_equo = dispersione / (m - 1)

    dove `dispersione` e' quella di `dispersione_crps`. Costa zero, perche' il
    banco calcola gia' entrambi i termini.
    """
    if m < 2:
        raise ValueError("il punteggio equo richiede almeno due scenari")
    return np.asarray(crps_empirico, dtype=float) - \
        np.asarray(dispersione, dtype=float) / (m - 1)


def brier_equo(p_stimata, esito, m: int):
    """Brier equo, equazione (3) di Ferro.

        s = (i/m - y)^2 - i (m - i) / (m^2 (m - 1))

    Con `p = i/m` il secondo termine e' `p (1 - p) / (m - 1)`: la stessa forma
    del CRPS, dispersione di ensemble divisa per `m - 1`.
    """
    if m < 2:
        raise ValueError("il punteggio equo richiede almeno due scenari")
    p = np.asarray(p_stimata, dtype=float)
    y = np.asarray(esito, dtype=float)
    return (p - y) ** 2 - p * (1.0 - p) / (m - 1)


# --------------------------------------------------------------------------
# varianza con grappoli incrociati
# --------------------------------------------------------------------------

def _somme_per_grappolo(r: np.ndarray, ids: np.ndarray) -> tuple[float, int]:
    """`sum_g (sum_{i in g} r_i)^2` e il numero di grappoli."""
    _, codici = np.unique(ids, return_inverse=True)
    somme = np.bincount(codici, weights=r)
    return float(np.sum(somme ** 2)), int(somme.size)


@dataclass
class Intervallo:
    """Il risultato di un confronto appaiato, con la diagnosi accanto."""

    differenza: float
    ic_basso: float
    ic_alto: float
    errore_standard: float
    n: int
    grappoli_1: int
    grappoli_2: int
    gradi_liberta: int
    ammissibile: bool
    esclude_zero: bool
    diagnostica: dict = field(default_factory=dict)

    def come_riga(self) -> dict:
        d = {"differenza": self.differenza, "ic_basso": self.ic_basso,
             "ic_alto": self.ic_alto, "es": self.errore_standard,
             "n": self.n, "grappoli_1": self.grappoli_1,
             "grappoli_2": self.grappoli_2,
             "ammissibile": self.ammissibile,
             "esclude_zero": self.esclude_zero}
        d.update({f"es_{k}": v for k, v in
                  self.diagnostica.get("errori_standard", {}).items()})
        return d


def _t_critico(gradi: int, livello: float) -> float:
    if _st is not None:
        return float(_st.t.ppf(0.5 + livello / 2.0, gradi))
    # ripiego dichiarato: valore normale al 95 %, che vale solo con molti
    # grappoli. Con pochi grappoli sottostima il valore critico, quindi il
    # ripiego va usato sapendo che l'intervallo esce troppo stretto.
    if abs(livello - 0.95) > 1e-9:
        raise RuntimeError("senza scipy il ripiego copre solo il livello 95 %")
    return 1.959963984540054


def intervallo_two_way(d, id_1, id_2, *, livello: float = 0.95,
                       verifica_celle_uniche: bool = True) -> Intervallo:
    """Intervallo two-way cluster-robust sulla media di una differenza appaiata.

    Parametri
    ---------
    d
        differenza appaiata per riga, `S(braccio2) - S(braccio1)`. Le righe
        devono essere le stesse per i due bracci e nello stesso ordine: e'
        quello che rende lecito il confronto riga per riga.
    id_1, id_2
        i due identificativi di grappolo per ciascuna riga; nel banco sono la
        partita e il giocatore. Devono incrociarsi, non essere annidati: se
        fossero annidati basterebbe il one-way sulla dimensione piu' grossolana.

    Formula, Cameron & Miller equazione (21) con la correzione finita (12)
    ridotta a `G/(G-1)` perche' il regressore e' la sola costante:

        r_i = d_i - media(d)
        V = [ (G1/(G1-1)) B1 + (G2/(G2-1)) B2 - (n/(n-1)) B0 ] / n^2

    dove `B1` e `B2` sono le somme dei quadrati delle somme per grappolo e `B0`
    quella sulle singole righe.

    Se `V <= 0` l'intervallo e' dichiarato **non ammissibile** e non viene
    sostituito in silenzio da un one-way: la fonte avverte che (21) non e'
    garantita semidefinita positiva, e mascherare il caso renderebbe il
    risultato non verificabile.
    """
    d = np.asarray(d, dtype=float)
    id_1 = np.asarray(id_1)
    id_2 = np.asarray(id_2)
    if not (d.shape == id_1.shape == id_2.shape):
        raise ValueError(f"forme non appaiate: {d.shape}, {id_1.shape}, "
                         f"{id_2.shape}")
    if verifica_celle_uniche and d.size:
        # IPOTESI PORTANTE, non un dettaglio: la formula sottrae la varianza
        # sulle singole righe perche' l'intersezione dei due grappoli **e'** la
        # singola riga. Se una cella (id_1, id_2) comparisse due volte,
        # l'intersezione sarebbe piu' grossa della riga e il terzo termine
        # sarebbe quello sbagliato, senza che nulla lo segnali.
        celle = np.stack([np.asarray(id_1, dtype=object),
                          np.asarray(id_2, dtype=object)], axis=1)
        viste = {(a, b) for a, b in map(tuple, celle)}
        if len(viste) != d.size:
            raise ValueError(
                f"la coppia (id_1, id_2) non e' unica per riga "
                f"({d.size - len(viste)} celle ripetute): l'intersezione dei "
                "due grappoli non e' piu' la singola riga, e il terzo termine "
                "della formula non e' quello giusto")
    buoni = np.isfinite(d)
    d, id_1, id_2 = d[buoni], id_1[buoni], id_2[buoni]
    n = int(d.size)
    if n < 2:
        raise ValueError("meno di due osservazioni finite")

    media = float(d.mean())
    r = d - media
    b1, g1 = _somme_per_grappolo(r, id_1)
    b2, g2 = _somme_per_grappolo(r, id_2)
    b0 = float(np.sum(r ** 2))
    if g1 < 2 or g2 < 2:
        raise ValueError(f"una dimensione ha meno di due grappoli "
                         f"({g1} e {g2}): l'inferenza non esiste, non si "
                         f"ripiega su un'altra dimensione")

    c1, c2, c0 = g1 / (g1 - 1), g2 / (g2 - 1), n / (n - 1)
    v = (c1 * b1 + c2 * b2 - c0 * b0) / (n * n)
    ammissibile = bool(v > 0)

    # gli errori standard di confronto: il loro rapporto e' la diagnosi di
    # quanto la dipendenza conti, e costa tre `bincount`
    es_righe = float(np.sqrt(c0 * b0) / n)
    # `b = 0` significa che dentro ogni grappolo i residui si annullano: la
    # risposta giusta e' un errore standard **nullo**, non un NaN. Restituire
    # NaN cancellava la diagnosi proprio nel caso in cui e' piu' informativa.
    es_1 = float(np.sqrt(c1 * b1) / n)
    es_2 = float(np.sqrt(c2 * b2) / n)
    es = float(np.sqrt(v)) if ammissibile else float("nan")

    gradi = min(g1, g2) - 1
    t = _t_critico(gradi, livello)
    lo = media - t * es if ammissibile else float("nan")
    hi = media + t * es if ammissibile else float("nan")

    return Intervallo(
        differenza=media, ic_basso=lo, ic_alto=hi, errore_standard=es, n=n,
        grappoli_1=g1, grappoli_2=g2, gradi_liberta=gradi,
        ammissibile=ammissibile,
        esclude_zero=bool(ammissibile and (lo > 0 or hi < 0)),
        diagnostica={
            "errori_standard": {"righe_indipendenti": es_righe,
                                "one_way_1": es_1, "one_way_2": es_2,
                                "two_way": es},
            "rapporto_two_way_su_righe": (es / es_righe
                                          if ammissibile and es_righe > 0
                                          else float("nan")),
            "t_critico": t,
            "componenti": {"B1": b1, "B2": b2, "B0": b0, "V": v},
            "nota_ammissibilita": (
                "V_2way non e' garantita semidefinita positiva (Cameron & "
                "Miller, eq. 21). Se V <= 0 l'intervallo non e' utilizzabile e "
                "va segnalato, non sostituito con un one-way."),
        })


def rho_intra(d, ids) -> float:
    """Correlazione intra-grappolo della differenza, stimata dalle somme.

    Serve a sapere **prima** quanto la dipendenza conti: si ricava dal
    gonfiaggio osservato della varianza per grappolo rispetto a quella per
    riga, invertendo il fattore di Moulton con regressore costante
    (`tau^2 = 1 + rho * (N_g - 1)`, equazione 6 con `rho_x = 1`).

    E' una stima descrittiva del campione, non un parametro del modello: puo'
    uscire negativa quando i grappoli sono piccoli o la dipendenza e' assente,
    e in quel caso si riporta com'e'.

    LIMITE DICHIARATO: l'inversione usa la dimensione **media** `n / G`, cioe'
    assume grappoli bilanciati. Con grappoli molto sbilanciati la stima esce
    distorta verso l'alto, perche' i grappoli grandi contribuiscono al
    gonfiaggio piu' di quanto la media suggerisca. Nel banco i grappoli sono
    quasi bilanciati (le partite hanno tutte all'incirca le stesse righe),
    quindi la distorsione e' piccola, ma la colonna `rho_partita` va letta
    come indicazione dell'ordine di grandezza e non come una stima puntuale.
    """
    d = np.asarray(d, dtype=float)
    ids = np.asarray(ids)
    buoni = np.isfinite(d)
    d, ids = d[buoni], ids[buoni]
    r = d - d.mean()
    b, g = _somme_per_grappolo(r, ids)
    b0 = float(np.sum(r ** 2))
    if g < 2 or b0 <= 0:
        return float("nan")
    n = d.size
    n_medio = n / g
    if n_medio <= 1:
        return float("nan")
    tau2 = (g / (g - 1) * b) / (n / (n - 1) * b0)
    return float((tau2 - 1.0) / (n_medio - 1.0))


def bootstrap_grappoli(d, ids, *, seme: int, repliche: int = 2000,
                       livello: float = 0.95) -> dict:
    """Bootstrap a coppie sui grappoli, appaiato. Controllo, non sostituto.

    Da ogni grappolo estratto si prendono **tutte** le sue righe, quindi le
    differenze appaiate restano appaiate: ricampionare i due bracci
    separatamente distruggerebbe l'appaiamento, che e' la ragione per cui la
    varianza e' piccola.

    Deve coincidere con il one-way analitico sulla stessa dimensione entro
    l'errore del bootstrap. Se non coincide c'e' un errore di indicizzazione.
    """
    d = np.asarray(d, dtype=float)
    ids = np.asarray(ids)
    buoni = np.isfinite(d)
    d, ids = d[buoni], ids[buoni]
    _, codici = np.unique(ids, return_inverse=True)
    g = int(codici.max()) + 1
    ordine = np.argsort(codici, kind="stable")
    d_ord = d[ordine]
    conta = np.bincount(codici, minlength=g)
    inizio = np.concatenate([[0], np.cumsum(conta)])
    rng = np.random.default_rng(seme)
    medie = np.empty(repliche)
    for b in range(repliche):
        scelti = rng.integers(0, g, size=g)
        somma, quanti = 0.0, 0
        for c in scelti:
            somma += d_ord[inizio[c]:inizio[c + 1]].sum()
            quanti += conta[c]
        medie[b] = somma / max(quanti, 1)
    alfa = (1.0 - livello) / 2.0
    lo, hi = np.percentile(medie, [100 * alfa, 100 * (1 - alfa)])
    return {"differenza": float(d.mean()), "ic_basso": float(lo),
            "ic_alto": float(hi), "es": float(medie.std(ddof=1)),
            "grappoli": g, "repliche": repliche}


# --------------------------------------------------------------------------
# rumore Monte Carlo
# --------------------------------------------------------------------------

def rumore_monte_carlo(medie_per_seme, *, rapporto_richiesto: float = 10.0,
                       es_campionario: float | None = None) -> dict:
    """Errore standard Monte Carlo dalle repliche a semi diversi.

    Il rumore da `m` finito non lo toglie nessuna correzione e scala come
    `1/sqrt(m)`. Qui si misura ripetendo con semi distinti: e' un metodo
    pratico, non l'unico possibile (vedi la sezione 3 del modulo).

    ## Due criteri, e perche' sono due

    **Criterio in vigore** (campo `soddisfatto`): `es_mc <= |media| / rapporto`.
    E' quello dichiarato prima delle esecuzioni gia' fatte, ed e' conservato
    perche' i verdetti pubblicati sono stati letti con quello. Ha un difetto
    noto e misurato: quando la differenza tende a zero la soglia tende a zero,
    quindi un confronto **genuinamente nullo** non lo soddisfa mai e finisce
    etichettato «non misurabile con le risorse disponibili». E non garantisce
    da solo che la varianza Monte Carlo pesi l'1 % di quella totale, perche'
    confronta il rumore con l'**effetto**, non con l'incertezza campionaria.

    **Emendamento prospettico** (campo `soddisfatto_prospettico`, calcolato solo
    se si passa `es_campionario`): `es_mc <= es_campionario / rapporto`. Questo
    e' il criterio che dice davvero quello che l'altro prometteva: con
    `rapporto = 10`, la varianza Monte Carlo aggiunge l'1 % alla varianza
    campionaria, `(1 + 1/100)`. Non degenera vicino allo zero, perche'
    l'incertezza campionaria non tende a zero quando l'effetto lo fa.

    L'emendamento **non cambia** i verdetti gia' pubblicati: e' riportato
    accanto, e vale per le esecuzioni pianificate d'ora in avanti. Cambiare un
    criterio dopo aver visto da che parte cadono i risultati e' la mossa che il
    protocollo vieta.

    ## Il piano di simulazione e' finito e dichiarato prima

    `repliche_necessarie` dice quante repliche servirebbero **secondo il
    criterio scelto**, e serve a decidere *prima* quante farne. Non e' un
    invito ad aggiungere semi finche' compare una differenza: quella sarebbe una
    procedura sequenziale senza controllo dell'errore. Se la precisione resta
    insufficiente si dichiara insieme alla stima ottenuta, e ci si ferma.

    Quando la differenza e' cosi' piccola che `R` diventa proibitivo, l'esito
    e' **«non misurabile con le risorse disponibili»**: non e' ne'
    «inconcludente» ne' «equivalente».
    """
    x = np.asarray(list(medie_per_seme), dtype=float)
    x = x[np.isfinite(x)]
    r = int(x.size)
    if r < 2:
        return {"repliche": r, "media": float(x.mean()) if r else float("nan"),
                "sd_fra_semi": float("nan"), "es_mc": float("nan"),
                "soddisfatto": False,
                "nota": "con meno di due semi il rumore Monte Carlo non e' "
                        "misurabile: una sola esecuzione non puo' misurare la "
                        "propria varianza"}
    media = float(x.mean())
    sd = float(x.std(ddof=1))
    es = sd / np.sqrt(r)
    soglia = abs(media) / rapporto_richiesto
    necessarie = (int(np.ceil((rapporto_richiesto ** 2) * sd ** 2 / media ** 2))
                  if media != 0 else None)
    fuori = {"repliche": r, "media": media, "sd_fra_semi": sd,
             "es_mc": float(es), "soglia": float(soglia),
             "soddisfatto": bool(es <= soglia),
             "rapporto_richiesto": rapporto_richiesto,
             "repliche_necessarie": necessarie,
             "nota_soglia": ("criterio in vigore, dichiarato prima delle "
                             "esecuzioni gia' fatte; degenera quando la "
                             "differenza tende a zero")}
    if es_campionario is not None and np.isfinite(es_campionario) \
            and es_campionario > 0:
        # emendamento prospettico: il rumore si confronta con l'incertezza
        # campionaria, non con l'effetto. Con rapporto 10 la varianza Monte
        # Carlo aggiunge l'1 % a quella campionaria.
        soglia_p = float(es_campionario) / rapporto_richiesto
        fuori["es_campionario"] = float(es_campionario)
        fuori["soglia_prospettica"] = soglia_p
        fuori["soddisfatto_prospettico"] = bool(es <= soglia_p)
        fuori["quota_varianza_aggiunta"] = float(
            (es ** 2) / (es_campionario ** 2))
        fuori["repliche_necessarie_prospettiche"] = int(np.ceil(
            (rapporto_richiesto ** 2) * sd ** 2 / (es_campionario ** 2)))
    return fuori


ETICHETTE_CONFRONTO = {
    "nulla": "differenza non rilevabile",
    "negativa": "primo migliore",
    "positiva": "primo peggiore",
}

SENZA_MISURA = " (rumore Monte Carlo non misurato)"


def esito_confronto(iv: Intervallo, mc: dict | None,
                    etichette: dict | None = None) -> str:
    """L'etichetta del verdetto, con le distinzioni che il protocollo impone.

    - varianza non ammissibile: `V_2way <= 0`, la stima non e' utilizzabile e
      non viene sostituita in silenzio da un one-way;
    - non misurabile con le risorse disponibili: il rumore Monte Carlo domina
      la differenza. **Non** e' «inconcludente»;
    - `etichette["nulla"]`, per difetto «differenza non rilevabile»:
      l'intervallo contiene lo zero. **Non** e' «equivalenti»: lo diventerebbe
      solo contro una tolleranza dichiarata prima, che nessuno ha dichiarato.

    Quando il rumore Monte Carlo **non e' stato misurato** — un solo seme di
    scenario, oppure nessuna serie per seme — l'etichetta lo porta scritto
    addosso. Senza, un'esecuzione a un seme poteva stampare «C1 migliore» come
    se il rumore di simulazione fosse stato guardato e trovato piccolo, mentre
    non era stato guardato affatto.
    """
    et = dict(ETICHETTE_CONFRONTO)
    if etichette:
        et.update(etichette)
    if not iv.ammissibile:
        return "varianza non ammissibile"
    misurato = bool(mc) and mc.get("repliche", 0) >= 2
    if misurato and not mc["soddisfatto"]:
        return "non misurabile con le risorse disponibili"
    coda = "" if misurato else SENZA_MISURA
    if not iv.esclude_zero:
        return et["nulla"] + coda
    return (et["negativa"] if iv.differenza < 0 else et["positiva"]) + coda
