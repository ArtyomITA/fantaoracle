"""Il voto puro dato il tabellino.

E' il pezzo del cubo che spiega perche' i compagni di squadra si somigliano:
quando la squadra vince 3-0, il portiere e i difensori prendono tutti voti
alti. Il simulatore attuale cattura quella somiglianza con un unico shock di
squadra uguale per tutti i ruoli; qui la si ottiene condizionando agli eventi
che l'hanno prodotta.

## Modello

    voto = alfa_giocatore + beta' eventi + gamma_ruolo + errore

`alfa_giocatore` e' contratto verso la media del ruolo in proporzione a quante
partite ha alle spalle. Serve perche' il voto medio di un giocatore e' una
sua caratteristica stabile, ma stimarla su cinque partite darebbe un numero
inaffidabile.

## Due specificazioni, di proposito

La differenza reti della squadra e gli eventi individuali si sovrappongono:
il portiere che subisce tre gol e' quasi sempre in una squadra con differenza
reti negativa. Chi mette entrambe le cose nella stessa regressione ottiene per
il portiere un coefficiente **positivo** sui tre gol subiti, che letto da solo
sembra dire che prendere gol conviene. Non e' un errore di stima: e' la
differenza reti che ha gia' assorbito l'effetto.

Per questo il modulo stima sempre due specificazioni e le riporta entrambe:

    "individuale"  solo eventi del giocatore (nessuna differenza reti)
    "con_squadra"  eventi + differenza reti della squadra

I coefficienti vanno letti dentro la propria specificazione. `diagnostica`
riporta anche la correlazione fra i regressori sospetti, cosi' il segno non si
interpreta al buio.

## Dipendenza residua

Dopo il condizionamento resta della correlazione fra compagni: la si misura
qui, per coppia di ruoli, e la si riporta. **Non** viene aggiunto in automatico
lo shock 0,25 del simulatore attuale: sarebbe contare due volte una dipendenza
gia' spiegata dagli eventi. Se serve uno shock residuo, il valore giusto e'
quello misurato dopo il condizionamento, non prima.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

COLONNE_EVENTI = [
    "gol_1", "gol_2piu", "assist", "rigore_segnato", "rigori_sbagliati",
    "rigori_parati", "autogol", "ammonizione", "espulsione",
    "gk_porta_inviolata", "gk_1_subito", "gk_2_subiti", "gk_3piu_subiti",
]
COLONNE_SQUADRA = ["diff_reti"]


@dataclass
class ModelloVoto:
    coef: dict                    # nome -> coefficiente
    alfa: dict                    # master_id -> effetto individuale
    media_ruolo: dict             # ruolo -> intercetta, AL NETTO degli eventi
    sigma: float                  # scarto residuo
    specificazione: str
    voto_medio_ruolo: dict = field(default_factory=dict)  # media grezza
    diagnostica: dict = field(default_factory=dict)

    def previsione(self, X: pd.DataFrame) -> np.ndarray:
        base = np.array([self.alfa.get(m, self.media_ruolo.get(r, 6.0))
                         for m, r in zip(X["master_id"], X["ruolo"])])
        for nome, c in self.coef.items():
            if nome in X:
                base = base + c * X[nome].to_numpy(dtype=float)
        return base


def costruisci_regressori(P: pd.DataFrame) -> pd.DataFrame:
    """Dal panel alle colonne del modello. Solo righe con voto numerico."""
    d = P[P.stato_voto == "con_voto"].copy()
    # il ruolo di riferimento e' quello del listone, in maiuscolo: e' la stessa
    # chiave che usa il cubo. La colonna dei voti e' minuscola e usarla qui
    # faceva fallire ogni ricerca per ruolo, mandando al valore di ripiego 6.0
    d["ruolo"] = d["ruolo"].astype(str).str.upper()
    gol = d["gol_fatti"].fillna(0).astype(float)
    d["gol_1"] = (gol == 1).astype(float)
    d["gol_2piu"] = (gol >= 2).astype(float)
    for c in ["assist", "rigore_segnato", "rigori_sbagliati", "rigori_parati",
              "autogol", "ammonizione", "espulsione"]:
        d[c] = d[c].fillna(0).astype(float)
    p = d["ruolo_voti"].astype(str).str.lower() == "p"
    subiti = d["gol_subiti"].fillna(0).astype(float)
    d["gk_porta_inviolata"] = (p & (subiti == 0)).astype(float)
    d["gk_1_subito"] = (p & (subiti == 1)).astype(float)
    d["gk_2_subiti"] = (p & (subiti == 2)).astype(float)
    d["gk_3piu_subiti"] = (p & (subiti >= 3)).astype(float)
    d["diff_reti"] = (d["gol_squadra"].fillna(0).astype(float)
                      - d["gol_avversario"].fillna(0).astype(float))
    return d


def _contrazione_empirica(d: pd.DataFrame, colonne: list, beta) -> float:
    """Partite equivalenti di prior, stimate dai dati (Bayes empirico).

    La media dei residui di un giocatore con n partite ha varianza
    sigma^2/n oltre alla sua vera differenza. Sottraendo il rumore dalla
    varianza osservata fra giocatori si ottiene la varianza vera; il numero di
    partite che bilancia prior ed evidenza e' il loro rapporto.
    """
    r = d["voto"].to_numpy(float) - d[colonne].to_numpy(float) @ beta
    g = pd.DataFrame({"master_id": d["master_id"].to_numpy(), "r": r})
    per = g.groupby("master_id")["r"].agg(["mean", "size", "var"])
    dentro = per["var"].dropna()
    sigma2 = float(np.average(dentro, weights=per.loc[dentro.index, "size"]))
    sel = per[per["size"] >= 10]
    if len(sel) < 50 or sigma2 <= 0:
        return 12.0
    rumore = float(np.mean(sigma2 / sel["size"]))
    vera = float(max(sel["mean"].var() - rumore, 1e-4))
    return float(min(60.0, max(2.0, sigma2 / vera)))


def stima(P: pd.DataFrame, specificazione: str = "individuale",
          as_of: str | None = None, contrazione: float | None = None,
          lam: float = 1e-3) -> ModelloVoto:
    """Minimi quadrati penalizzati con effetto individuale contratto.

    Con `as_of` usa solo partite anteriori a quella data: e' la condizione per
    un confronto predittivo onesto, dove medie individuali e coefficienti
    vengono tutti dal passato.

    `contrazione` e' il numero di partite equivalenti di prior. Se non viene
    passato, si stima dai dati: e' il rapporto fra la varianza residua e la
    varianza vera fra giocatori (al netto del rumore campionario), che e' il
    valore che minimizza l'errore quadratico. Con il valore fisso 12 usato
    prima, gli effetti individuali avevano scarto 0,108 contro 0,179 veri: il
    54%. Nel cubo questo significava che scegliere bene i giocatori rendeva
    meno che nella realta', e le rose valevano circa tre punti a giornata in
    meno del vero.
    """
    d = costruisci_regressori(P)
    d["data"] = pd.to_datetime(d["data"])
    if as_of is not None:
        d = d[d["data"] < pd.Timestamp(as_of)]
    if d.empty:
        raise ValueError("nessuna riga con voto prima di as_of")
    colonne = list(COLONNE_EVENTI)
    if specificazione == "con_squadra":
        colonne += COLONNE_SQUADRA
    media_ruolo = d.groupby("ruolo")["voto"].mean().to_dict()

    # passo 1: coefficienti sugli eventi, al netto della media individuale
    #          grezza (cosi' gli effetti individuali non assorbono gli eventi)
    grezza = d.groupby("master_id")["voto"].transform("mean")
    y = d["voto"].to_numpy(float) - grezza.to_numpy(float)
    X = d[colonne].to_numpy(float)
    X = X - X.mean(0)
    A = X.T @ X + lam * len(X) * np.eye(X.shape[1])
    beta = np.linalg.solve(A, X.T @ y)
    coef = dict(zip(colonne, beta))

    # passo 2: effetto individuale contratto, sui residui dagli eventi
    d["_resid"] = d["voto"].to_numpy(float) - d[colonne].to_numpy(float) @ beta
    g = d.groupby(["master_id", "ruolo"])["_resid"].agg(["mean", "size"])
    # intercetta di ruolo: la media dei voti meno l'effetto medio degli eventi
    # di quel ruolo. E' il valore giusto per chi non ha storia: usare la media
    # grezza e poi aggiungere gli eventi li conterebbe due volte, e gonfiava il
    # voto medio degli attaccanti di 0,19 punti nel cubo.
    if contrazione is None:
        contrazione = _contrazione_empirica(d, colonne, beta)
    intercetta = {}
    for ruolo in media_ruolo:
        sel = d[d.ruolo == ruolo]
        intercetta[ruolo] = float(media_ruolo[ruolo]
                                  - (sel[colonne].to_numpy(float) @ beta).mean())
    alfa = {}
    for (mid, ruolo), r in g.iterrows():
        base = intercetta.get(ruolo, 6.0)
        alfa[mid] = float((r["mean"] * r["size"] + base * contrazione)
                          / (r["size"] + contrazione))
    prev = np.array([alfa[m] for m in d["master_id"]]) + d[colonne].to_numpy(float) @ beta
    residui = d["voto"].to_numpy(float) - prev

    # collinearita' fra i regressori sospetti
    sospetti = [c for c in ("diff_reti", "gk_3piu_subiti", "gk_porta_inviolata",
                            "gol_1", "gol_2piu") if c in d]
    corr = d[sospetti].corr().round(3).to_dict() if len(sospetti) > 1 else {}

    return ModelloVoto(
        coef=coef, alfa=alfa, media_ruolo=intercetta,
        voto_medio_ruolo=media_ruolo,
        sigma=float(residui.std()), specificazione=specificazione,
        diagnostica={
            "righe": int(len(d)),
            "giocatori": int(d.master_id.nunique()),
            "varianza_spiegata": float(1 - residui.var() / d["voto"].var()),
            "correlazione_regressori": corr,
            "contrazione": round(float(contrazione), 3),
            "sd_effetti_individuali": round(float(np.std(list(alfa.values()))), 4),
        })


def stima_senza_voto(P: pd.DataFrame, as_of: str | None = None) -> dict:
    """P(la fonte dà s.v. | il giocatore è sceso in campo), per fascia di minuti.

    Serve perché il cubo genera chi gioca, ma la fonte non dà un voto a tutti:
    chi entra tardi prende s.v., e una riga con s.v. vale zero nel fantacalcio
    a meno di sostituzione. Senza questo passaggio la stagione simulata ha piu'
    voti di quella vera (nel primo giro: 305 contro 282 per giornata).

    La relazione e' stimata sui minuti effettivi, non assunta."""
    d = P[P.stato_voto.isin(["con_voto", "senza_voto"])].copy()
    d["data"] = pd.to_datetime(d["data"])
    if as_of is not None:
        d = d[d["data"] < pd.Timestamp(as_of)]
    d["minuti"] = pd.to_numeric(d["minuti"], errors="coerce")
    d = d[d["minuti"].notna() & (d["minuti"] > 0)]
    if d.empty:
        return {"fasce": [(0, 200, 0.1)], "nota": "nessun dato"}
    tagli = [0, 5, 10, 15, 20, 30, 45, 60, 75, 200]
    fasce = []
    for lo, hi in zip(tagli[:-1], tagli[1:]):
        s = d[(d.minuti > lo) & (d.minuti <= hi)]
        if len(s) >= 30:
            fasce.append((lo, hi, float((s.stato_voto == "senza_voto").mean())))
    return {"fasce": fasce,
            "quota_complessiva": float((d.stato_voto == "senza_voto").mean()),
            "righe": int(len(d))}


def p_senza_voto(fasce: dict, minuti) -> np.ndarray:
    """Applica le fasce stimate a un vettore di minuti."""
    m = np.asarray(minuti, dtype=float)
    out = np.zeros_like(m)
    for lo, hi, p in fasce.get("fasce", []):
        out = np.where((m > lo) & (m <= hi), p, out)
    return out


def struttura_dipendenza(P: pd.DataFrame, mod: "ModelloVoto",
                         as_of: str | None = None) -> dict:
    """Scompone la dipendenza fra compagni in squadra + reparto + individuale.

    Uno shock unico per squadra impone la STESSA correlazione fra tutte le
    coppie di ruoli. I dati dicono altro: fra difensori la correlazione e' circa
    tre volte quella fra portiere e difensori. La scomposizione

        residuo = a * z_squadra + b_reparto * z_reparto + errore

    riproduce entrambe. I bersagli sono le correlazioni **osservate** fra
    compagni della stessa partita, misurate sui dati anteriori ad `as_of` con
    la stessa definizione con cui si misurano quelle simulate:

        a^2               = rho(portiere, difensori) * varianza del voto
        b_reparto^2       = [rho(reparto) - rho(portiere, difensori)] * varianza
        errore^2          = sigma^2 - a^2 - b_reparto^2

    Se il residuo del modello non basta a coprire i due pezzi, gli scarti
    vengono ridotti in proporzione e la cosa e' dichiarata in `avvertenza`:
    meglio una correlazione piu' bassa del bersaglio che una varianza del voto
    piu' alta del vero.
    """
    d = P[P.stato_voto == "con_voto"].copy()
    d["data"] = pd.to_datetime(d["data"])
    if as_of is not None:
        d = d[d["data"] < pd.Timestamp(as_of)]
    d["ruolo"] = d["ruolo"].astype(str).str.upper()
    var_voto = float(pd.to_numeric(d["voto"], errors="coerce").var())
    osservate = correlazioni_osservate(d)
    rho_squadra = max(osservate.get("portiere-difensori", 0.0), 0.0)
    a2 = rho_squadra * var_voto
    b2 = {}
    for ruolo, chiave in (("D", "difensori"), ("C", "centrocampisti"),
                          ("A", "attaccanti")):
        r = osservate.get(chiave, np.nan)
        b2[ruolo] = 0.0 if np.isnan(r) else max((float(r) - rho_squadra)
                                                * var_voto, 0.0)
    b2["P"] = 0.0                      # un solo portiere per squadra in campo
    sigma2 = mod.sigma ** 2
    avvertenza = None
    peggiore = a2 + max(b2.values())
    if peggiore > 0.9 * sigma2:
        scala = 0.9 * sigma2 / peggiore
        a2 *= scala
        b2 = {k: v * scala for k, v in b2.items()}
        avvertenza = (f"gli scarti sono stati ridotti del "
                      f"{(1 - scala) * 100:.0f}% perche' il residuo del modello "
                      f"({mod.sigma:.3f}) non copre le correlazioni osservate")
    residuo2 = max(sigma2 - a2 - max(b2.values()), 0.05 * sigma2)
    return {
        "sd_squadra": float(np.sqrt(a2)),
        "sd_reparto": {k: float(np.sqrt(v)) for k, v in b2.items()},
        "sd_individuale": float(np.sqrt(residuo2)),
        "correlazioni_bersaglio": {k: round(float(v), 4)
                                   for k, v in osservate.items()},
        "varianza_voto_osservata": round(var_voto, 5),
        "avvertenza": avvertenza,
    }


def correlazioni_osservate(d: pd.DataFrame, colonna: str = "voto") -> dict:
    """Correlazione fra compagni della stessa partita, per coppia di ruoli.

    Stessa definizione usata per misurare le correlazioni simulate: e' la
    condizione per poterle confrontare."""
    fuori = {}
    for et, ra, rb in [("portiere-difensori", ["P"], ["D"]),
                       ("difensori", ["D"], ["D"]),
                       ("centrocampisti", ["C"], ["C"]),
                       ("attaccanti", ["A"], ["A"])]:
        vals = []
        for _, g in d.groupby(["stagione", "giornata", "squadra_alla_data"]):
            a = g[g.ruolo.isin(ra)][colonna].to_numpy(float)
            b = g[g.ruolo.isin(rb)][colonna].to_numpy(float)
            if ra == rb:
                for i in range(len(a)):
                    for j in range(i + 1, len(a)):
                        vals.append((a[i], a[j]))
            else:
                for x in a:
                    for y in b:
                        vals.append((x, y))
        if len(vals) < 50:
            fuori[et] = float("nan")
            continue
        v = np.array(vals)
        fuori[et] = float(np.corrcoef(v[:, 0], v[:, 1])[0, 1])
    return fuori


def dipendenza_residua(P: pd.DataFrame, mod: ModelloVoto) -> dict:
    """Correlazione fra compagni prima e dopo il condizionamento, per ruolo.

    E' il numero che dice quanto shock di squadra resta da mettere: se dopo il
    condizionamento la correlazione fra difensori e' 0,20, aggiungere anche lo
    shock tarato sul dato grezzo la conterebbe due volte."""
    d = costruisci_regressori(P)
    d["_prev"] = mod.previsione(d)
    d["_res"] = d["voto"].to_numpy(float) - d["_prev"]
    d["_grezzo"] = d["voto"].to_numpy(float) - d.groupby("master_id")["voto"].transform("mean")

    def coppie(colonna, ruoli_a, ruoli_b):
        vals = []
        for _, g in d.groupby(["stagione", "giornata", "squadra_alla_data"]):
            a = g[g.ruolo.str.upper().isin(ruoli_a)][colonna].to_numpy(float)
            b = g[g.ruolo.str.upper().isin(ruoli_b)][colonna].to_numpy(float)
            if ruoli_a == ruoli_b:
                if len(a) < 2:
                    continue
                for i in range(len(a)):
                    for j in range(i + 1, len(a)):
                        vals.append((a[i], a[j]))
            else:
                if not len(a) or not len(b):
                    continue
                for x in a:
                    for y in b:
                        vals.append((x, y))
        if len(vals) < 50:
            return float("nan")
        v = np.array(vals)
        return float(np.corrcoef(v[:, 0], v[:, 1])[0, 1])

    fuori = {}
    for et, ra, rb in [("portiere-difensori", ["P"], ["D"]),
                       ("difensori-difensori", ["D"], ["D"]),
                       ("centrocampisti", ["C"], ["C"]),
                       ("attaccanti", ["A"], ["A"]),
                       ("difensori-attaccanti", ["D"], ["A"])]:
        fuori[et] = {"prima": round(coppie("_grezzo", ra, rb), 4),
                     "dopo": round(coppie("_res", ra, rb), 4)}
    return fuori


def campiona_voto(mod: ModelloVoto, X: pd.DataFrame, rng: np.random.Generator,
                  u: np.ndarray | None = None,
                  shock_squadra: np.ndarray | None = None) -> np.ndarray:
    """Voto simulato: previsione + errore, arrotondato al mezzo punto.

    `shock_squadra` e' il residuo comune ai compagni: va passato SOLO se
    misurato dopo il condizionamento (vedi `dipendenza_residua`), altrimenti
    si conta due volta una dipendenza gia' spiegata dagli eventi.
    """
    base = mod.previsione(X)
    if u is None:
        e = rng.standard_normal(len(base))
    else:
        from scipy.special import ndtri
        e = ndtri(np.clip(np.asarray(u, dtype=float), 1e-9, 1 - 1e-9))
    v = base + mod.sigma * e
    if shock_squadra is not None:
        v = v + np.asarray(shock_squadra, dtype=float)
    return np.clip(np.round(v * 2) / 2, 3.0, 10.0)
