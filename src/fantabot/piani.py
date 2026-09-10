"""Piani alternativi con attaccanti di riferimento diversi.

## Perche' esistono

Una sola rosa ideale e' fragile. All'asta il bomber preferito puo' salire di
prezzo o finire a un altro, e serve sapere **come cambia tutta la squadra** se
si prende un attaccante diverso: risparmiare in attacco finanzia difesa e
centrocampo, e la rosa che ne esce non e' la stessa con un nome sostituito.

## Che cosa NON e'

- **Non un modello nuovo.** Stesse previsioni, stesso MILP, stessi criteri
  economici: cambiano solo i vincoli, dichiarati.
- **Non una probabilita' di vittoria.** Il numero che ordina i piani e' il
  **punteggio del modello**, cioe' il valore della funzione che il solutore
  massimizza. Chiamarlo P(1°) sarebbe falso: quella richiede calendario,
  fasce gol, classifica e spareggi.
- **Non una garanzia di prezzo.** Il piano dice quanto vale la pena spendere
  ai prezzi usati; non che il giocatore si compri a quella cifra.

## L'obiettivo, quello vero

`optimize_roster` massimizza una somma pesata: i titolari valgono piu' della
panchina, e con `lam > 0` entra anche `value_up`. La somma grezza dei valori
dei venticinque e' un altro numero — sul pack corrente 5617 contro 3642.
Ordinare le alternative con la somma grezza mentre il solutore ottimizza
l'altra funzione significa confrontarle con un metro diverso da quello con cui
sono state costruite. Qui si usa `objective`.
"""
from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass, field

from .models import ROLES, Player
from .optimizer import optimize_roster

# quanti attaccanti candidati considerare al massimo
MAX_ALTERNATIVE = 8
# limite di tempo complessivo: le registrazioni dell'asta hanno la precedenza
SECONDI_MASSIMI = 20.0


@dataclass
class Contesto:
    """Tutto quello che serve a costruire un piano, in un oggetto solo."""

    candidati: dict
    prezzi: dict
    valori: dict
    valori_up: dict
    quote: dict
    budget: float
    fissati: dict = field(default_factory=dict)
    lam: float = 0.0
    forced_spend: dict | None = None
    min_spend: float | None = None
    time_limit: int = 5

    def chiave(self) -> str:
        """Identifica lo stato: cambia quando cambia qualcosa che conta."""
        crudo = json.dumps({
            "candidati": sorted(self.candidati),
            "prezzi": {k: round(float(v), 3) for k, v in sorted(self.prezzi.items())},
            "quote": dict(sorted(self.quote.items())),
            "budget": round(float(self.budget), 3),
            "fissati": sorted(self.fissati),
            "lam": self.lam, "forced": self.forced_spend,
            "min_spend": self.min_spend,
        }, sort_keys=True)
        return hashlib.sha256(crudo.encode("utf-8")).hexdigest()[:16]


def _risolvi(ctx: Contesto, *, required=None, banned=None,
             required_starters=None) -> dict | None:
    sol = optimize_roster(
        ctx.candidati, ctx.prezzi, ctx.valori, ctx.quote, ctx.budget,
        forced_spend=ctx.forced_spend, fixed=ctx.fissati,
        values_up=ctx.valori_up, lam=ctx.lam, time_limit=ctx.time_limit,
        min_spend=ctx.min_spend, required=required, banned=banned,
        required_starters=required_starters)
    if sol is None and ctx.forced_spend:
        # come il bot in `_replan`: se la quota d'attacco imposta non lascia
        # una rosa legale, si ripiega senza quel vincolo e lo si dichiara
        sol = optimize_roster(
            ctx.candidati, ctx.prezzi, ctx.valori, ctx.quote, ctx.budget,
            fixed=ctx.fissati, values_up=ctx.valori_up, lam=ctx.lam,
            time_limit=ctx.time_limit, min_spend=ctx.min_spend,
            required=required, banned=banned,
            required_starters=required_starters)
        if sol is not None:
            sol["vincolo_attacco_rilassato"] = True
    return sol


def _riassumi(ctx: Contesto, sol: dict, nome_info) -> dict:
    """Rosa, moduli, spesa per reparto: quello che si guarda davvero."""
    per_ruolo, spesa_ruolo = {}, {}
    for r in ROLES:
        ids = sol["roster"].get(r, [])
        spesa_ruolo[r] = round(sum(
            0.0 if pid in ctx.fissati else max(1.0, ctx.prezzi.get(pid, 1.0))
            for pid in ids), 1)
        per_ruolo[r] = [{
            **nome_info(pid),
            "titolare": pid in (sol.get("starters") or set()),
            "gia_mio": pid in ctx.fissati,
            "prezzo_atteso": (0.0 if pid in ctx.fissati
                              else round(max(1.0, ctx.prezzi.get(pid, 1.0)), 1)),
            "valore": round(float(ctx.valori.get(pid, 0.0)), 1),
        } for pid in sorted(ids, key=lambda q: -ctx.valori.get(q, 0.0))]
    return {"rosa": per_ruolo, "modulo": sol.get("module"),
            "vincolo_attacco_rilassato": bool(sol.get("vincolo_attacco_rilassato")),
            "spesa_per_reparto": spesa_ruolo,
            "costo_previsto": round(float(sol["cost"]), 1),
            "punteggio_modello": round(float(sol["objective"]), 3),
            "somma_valori": round(float(sol["value"]), 1)}


def scegli_bomber(ctx: Contesto, quanti: int, ordina_per) -> list:
    """Gli attaccanti da usare come riferimento: nessun nome nel codice.

    Si prendono i migliori per il criterio dato fra quelli **disponibili e
    comprabili**: chi costa piu' del budget residuo non puo' ancorare un piano.
    """
    candidati = [pid for pid, p in ctx.candidati.items()
                 if p.role == "A" and pid not in ctx.fissati
                 and max(1.0, ctx.prezzi.get(pid, 1.0)) <= ctx.budget]
    return sorted(candidati, key=ordina_per)[:quanti]


def costruisci_piani(ctx: Contesto, nome_info, *, quanti=6,
                     ordina_per=None, secondi_massimi=SECONDI_MASSIMI) -> dict:
    """Il piano libero, piu' un piano per ciascun bomber di riferimento.

    Ogni alternativa impone **un** attaccante: e' un vincolo dichiarato, non
    una legge dell'asta. Non si impongono due punte a tutti i piani, e non si
    alzano i tetti per farle entrare.
    """
    t0 = time.perf_counter()
    quanti = max(0, min(int(quanti), MAX_ALTERNATIVE))
    ordina_per = ordina_per or (lambda pid: -ctx.valori.get(pid, 0.0))

    riferimento = _risolvi(ctx)
    if riferimento is None:
        return {"stato": "non fattibile",
                "motivo": ("nessuna rosa legale con questi prezzi, budget e "
                           "giocatori disponibili"),
                "chiave_stato": ctx.chiave(), "piani": [],
                "secondi": round(time.perf_counter() - t0, 3)}

    base = _riassumi(ctx, riferimento, nome_info)
    obiettivo_rif = riferimento["objective"]
    bomber_rif = [p["id"] for p in base["rosa"]["A"] if p["titolare"]] or \
                 [p["id"] for p in base["rosa"]["A"]]

    piani = [{"tipo": "riferimento", "vincolo": "nessuno",
              "bomber": nome_info(bomber_rif[0]) if bomber_rif else None,
              "scarto_dal_riferimento": 0.0, "scarto_percentuale": 0.0,
              **base}]
    viste = {frozenset(pid for ids in riferimento["roster"].values()
                       for pid in ids)}
    scaduto = False

    for pid in scegli_bomber(ctx, quanti + 3, ordina_per):
        if len(piani) > quanti:
            break
        if time.perf_counter() - t0 > secondi_massimi:
            scaduto = True
            break
        if pid in {p["id"] for p in base["rosa"]["A"] if p["titolare"]}:
            continue          # gia' il bomber del riferimento
        sol = _risolvi(ctx, required={pid}, required_starters={pid})
        if sol is None:
            piani.append({"tipo": "alternativa", "bomber": nome_info(pid),
                          "vincolo": f"{nome_info(pid)['nome']} in rosa e titolare",
                          "stato": "non fattibile",
                          "motivo": "nessuna rosa legale con questo vincolo"})
            continue
        firma = frozenset(q for ids in sol["roster"].values() for q in ids)
        if firma in viste:
            continue          # stessa rosa: non e' un'alternativa
        viste.add(firma)
        r = _riassumi(ctx, sol, nome_info)
        scarto = obiettivo_rif - sol["objective"]
        piani.append({
            "tipo": "alternativa", "bomber": nome_info(pid),
            "vincolo": f"{nome_info(pid)['nome']} in rosa e titolare",
            "stato": "legale",
            "scarto_dal_riferimento": round(scarto, 3),
            "scarto_percentuale": round(100.0 * scarto / obiettivo_rif, 3)
            if obiettivo_rif else None,
            **r,
            "differenze": _differenze(base, r)})

    return {
        "stato": "ok", "chiave_stato": ctx.chiave(),
        "piani": piani, "secondi": round(time.perf_counter() - t0, 3),
        "tempo_scaduto": scaduto,
        "quanti_richiesti": quanti, "quanti_prodotti": len(piani) - 1,
        "nota_punteggio": (
            "«punteggio del modello» e' il valore della funzione che il "
            "solutore massimizza: titolari e panchina pesano in modo diverso. "
            "NON e' una probabilita' di vittoria, e non e' la somma dei valori "
            "dei venticinque, che e' un altro numero."),
        "nota_vincolo": (
            "ogni alternativa impone esattamente un attaccante come titolare. "
            "E' un vincolo scelto per far vedere il cambiamento, non una "
            "regola dell'asta: nessuno obbliga a comprare quel giocatore."),
    }


def _differenze(base: dict, altro: dict) -> dict:
    """Chi entra, chi esce, e come si sposta la spesa fra i reparti."""
    fuori = {"spostamento_spesa": {}, "entrano": [], "escono": []}
    for r in ROLES:
        fuori["spostamento_spesa"][r] = round(
            altro["spesa_per_reparto"][r] - base["spesa_per_reparto"][r], 1)
        ids_base = {p["id"] for p in base["rosa"][r]}
        ids_altro = {p["id"] for p in altro["rosa"][r]}
        for p in altro["rosa"][r]:
            if p["id"] not in ids_base:
                fuori["entrano"].append({**p, "ruolo": r})
        for p in base["rosa"][r]:
            if p["id"] not in ids_altro:
                fuori["escono"].append({**p, "ruolo": r})
    fuori["entrano"].sort(key=lambda p: -p["valore"])
    fuori["escono"].sort(key=lambda p: -p["valore"])
    return fuori


def piano_al_prezzo(ctx: Contesto, pid: str, prezzo: float, nome_info) -> dict:
    """«Se lo compro a X, come si completa la rosa?»

    Non tocca il registro: si sostituisce il prezzo di quel giocatore, lo si
    impone in rosa e si ricalcola tutto il resto. Il nome del piano non
    garantisce di comprarlo a quella cifra — e infatti si vede subito che cosa
    cambia se il prezzo sale.
    """
    prezzi = dict(ctx.prezzi)
    prezzi[pid] = float(prezzo)
    finto = Contesto(
        candidati=ctx.candidati, prezzi=prezzi, valori=ctx.valori,
        valori_up=ctx.valori_up, quote=ctx.quote, budget=ctx.budget,
        fissati=ctx.fissati, lam=ctx.lam, forced_spend=ctx.forced_spend,
        min_spend=ctx.min_spend, time_limit=ctx.time_limit)
    libero = _risolvi(ctx)
    sol = _risolvi(finto, required={pid}, required_starters={pid})
    if sol is None:
        return {"stato": "non fattibile", "prezzo_ipotetico": float(prezzo),
                "giocatore": nome_info(pid),
                "motivo": (f"a {prezzo:.0f} crediti non resta una rosa legale: "
                           "il resto del budget non basta a completare le quote"),
                "chiave_stato": ctx.chiave()}
    r = _riassumi(finto, sol, nome_info)
    fuori = {"stato": "ok", "giocatore": nome_info(pid),
             "prezzo_ipotetico": float(prezzo),
             "chiave_stato": ctx.chiave(), **r}
    if libero is not None:
        fuori["scarto_dal_riferimento"] = round(
            libero["objective"] - sol["objective"], 3)
        fuori["scarto_percentuale"] = (
            round(100.0 * (libero["objective"] - sol["objective"])
                  / libero["objective"], 3) if libero["objective"] else None)
        base = _riassumi(ctx, libero, nome_info)
        fuori["differenze"] = _differenze(base, r)
    fuori["nota"] = ("il registro dell'asta non e' stato toccato: questa e' una "
                     "simulazione. Comprare a questo prezzo resta una scelta, "
                     "e il prezzo vero lo fa il tavolo.")
    return fuori
