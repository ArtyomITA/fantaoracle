"""Tetti d'asta per indifferenza, calcolati una volta prima delle repliche.

Il tetto di un giocatore e' il prezzo piu' alto per cui comprarlo aumenta la
probabilita' di arrivare primi rispetto a passare. `livello3.indifferenza.curva`
lo calcola completando l'asta molte volte da entrambi i rami, e restituisce
anche lo **stato** del confronto: `verificato`, `approssimato` o
`inconcludente`.

Il calcolo dipende dal cubo e dal piano, non dalla replica: si fa una volta
dallo stato iniziale (nulla comprato, tutti disponibili) e si riusa. La regola
d'uso dei tetti in asta e' scritta in `reports/CRITERI_L2_L3.md`, sezione 3.8:
entrano solo con stato `verificato` o `approssimato`, altrimenti il bot ripiega
sul tetto di B e conta il ripiego.

## Che cosa deve contenere il file scritto, e perche'

Fino all'8 settembre 2026 questo script salvava di ogni giocatore soltanto
`nome`, `ruolo`, `mercato`, `tetto_economico`, `massimo_legale`, `stato`,
`secondi` e `curva`. Mancavano le tre cose senza le quali un tetto **non e'
utilizzabile** dal bot: l'identita' del giocatore dentro il record, la chiave
di validita' dello stato d'asta da cui e' stato calcolato, e la dichiarazione
del completamento. Il consumatore (`fantabot.bots.bot_l3.BotL3`) respinge un
record senza chiave (`senza_chiave`), senza identita' (`senza_identita`) o
senza completamento (`completamento_non_ammesso`): con quella serializzazione
il percorso produttore -> file -> asta non poteva funzionare, e non funzionava.

Il file scritto adesso porta, per ogni giocatore, il record intero che il
consumatore sa verificare, piu' un blocco `contesto` al livello superiore con
le componenti della chiave che l'asta non puo' osservare da sola (`cubo`,
`esperimento`, `regole`, `listini`). Quel blocco e' identico per tutti i
record — la chiave descrive lo stato del mondo, non il bersaglio — e lo script
si ferma se cosi' non fosse.

## L'identita' e' canonica

La chiave del dizionario non e' una prova di identita': `identita_canonica`
(definita nel consumatore, cosi' produttore e consumatore non possono
divergere) porta interi e stringhe alla stessa forma testuale, e ogni record
dichiara la propria. Se `curva()` restituisse un `giocatore` diverso da quello
richiesto, lo script si ferma invece di scrivere un file in cui la chiave e il
contenuto parlano di due persone.

## Gli avversari si chiamano come al tavolo vero

La chiave di validita' contiene l'impronta di rose e budget degli avversari,
identificati per nome. Il motore d'asta (`engine/auction.py`) chiama le squadre
`T0..T9` nell'ordine dei bot, quindi i nomi qui devono essere gli stessi,
**seggio compreso**: un file calcolato per il seggio 0 non e' verificabile in
una replica giocata dal seggio 3, perche' l'insieme dei nomi avversari cambia.
Il seggio e' un argomento dichiarato e finisce nel file; l'incoerenza produce
ripieghi `stato_cambiato` contati, non un uso silenzioso.

## Il completamento e' un surrogato

Le rose su cui la curva e' misurata sono completate da
`assegnazione_per_priorita`, che non e' una continuazione competitiva
dell'asta: assegna per priorita' pagando il prezzo previsto. Ovunque il suo
risultato viene esposto lo si chiama **surrogato**.

Uso:
    python scripts/l3_tetti.py --piano data/l3/pilota/rosa_migliore.json
"""
from __future__ import annotations

import argparse
import json
import math
import pickle
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from fantabot.bots.bot_l3 import (                  # noqa: E402
    COMPLETAMENTI_AMMESSI, etichetta_completamento, identita_canonica)
from fantabot.livello3 import indifferenza as I     # noqa: E402
from fantabot.livello3 import valutatore as V       # noqa: E402

OUT = ROOT / "data" / "l3" / "asta"

# Componenti della chiave che l'asta non puo' osservare da sola. Vanno
# dichiarate a parte perche' il consumatore le confronta contro il proprio
# `contesto_tetti`: `listini` e' inclusa apposta, il completamento surrogato
# paga il prezzo previsto e un listino diverso e' un altro esperimento.
BLOCCHI_CONTESTO = ("cubo", "esperimento", "regole", "listini")

# Campi del risultato di `curva()` che il consumatore legge o che servono a
# rileggere il file senza ricalcolarlo. `stima_tetto` entra perche' e' una
# quantita' diversa dal tetto e va tenuta distinta, non perche' si usi.
CAMPI_RECORD = ("tetto_economico", "stima_tetto", "massimo_legale", "stato",
                "completamento", "chiave_validita", "classificazione",
                "cambi_di_segno", "bersaglio_sempre_nostro", "curva",
                "prezzo_mercato_previsto", "avvertenza")


def _numero_finito(x) -> bool:
    return (isinstance(x, (int, float)) and not isinstance(x, bool)
            and math.isfinite(float(x)))


def record_tetto(giocatore, risultato: dict, nome: str, ruolo: str,
                 mercato: int, secondi: float) -> dict:
    """Il record serializzabile di un giocatore, con la sua identita' dentro.

    Solleva se il risultato parla di un altro giocatore: scrivere un file in
    cui la chiave e il contenuto non coincidono e' il difetto che il
    consumatore non puo' piu' recuperare da solo."""
    ident = identita_canonica(giocatore)
    dichiarato = risultato.get("giocatore")
    if dichiarato is not None and identita_canonica(dichiarato) != ident:
        raise ValueError(
            f"curva() ha risposto su {dichiarato!r} ma il tetto e' stato "
            f"chiesto per {giocatore!r}: record non scrivibile")
    fuori = {"giocatore": ident, "nome": nome, "ruolo": ruolo,
             "mercato": int(mercato), "secondi": round(float(secondi), 1)}
    for campo in CAMPI_RECORD:
        if campo in risultato:
            fuori[campo] = risultato[campo]
    tipo = (risultato.get("completamento") or {}).get("tipo")
    fuori["completamento_etichetta"] = etichetta_completamento(tipo)
    return fuori


def contesto_di(risultato: dict) -> dict:
    """Le componenti non osservabili della chiave, da dichiarare al bot."""
    chiave = risultato.get("chiave_validita") or {}
    mancanti = [b for b in BLOCCHI_CONTESTO if b not in chiave]
    if mancanti:
        raise ValueError(f"la chiave di validita' non porta {mancanti}: "
                         "il contesto non e' dichiarabile")
    return {b: chiave[b] for b in BLOCCHI_CONTESTO}


def _canonico(x) -> str:
    return json.dumps(x, sort_keys=True, default=str)


def costruisci_riassunto(records: dict, contesto: dict, meta: dict) -> dict:
    """Il file dei tetti: contesto una volta, record interi, conteggi.

    Controlla due invarianti prima di scrivere: ogni record sta sotto la
    chiave che dichiara, e tutti i record condividono lo stesso contesto."""
    tetti = {}
    conta: dict[str, int] = {}
    for chiave, rec in records.items():
        if identita_canonica(chiave) != identita_canonica(rec["giocatore"]):
            raise ValueError(f"record di {rec['giocatore']!r} sotto la chiave "
                             f"{chiave!r}")
        proprio = contesto_di(rec)
        if _canonico(proprio) != _canonico(contesto):
            raise ValueError(f"il record di {chiave} ha un contesto diverso "
                             "dagli altri: i tetti non sono confrontabili")
        tetti[identita_canonica(chiave)] = rec
        stato = rec.get("stato", "inconcludente")
        conta[stato] = conta.get(stato, 0) + 1
        if not _numero_finito(rec.get("tetto_economico")):
            conta["tetto_non_numerico"] = conta.get("tetto_non_numerico", 0) + 1
        elif float(rec["tetto_economico"]) == 0.0:
            conta["tetto_zero"] = conta.get("tetto_zero", 0) + 1
    return {**meta,
            "identita": ("chiave e campo `giocatore` in forma canonica "
                         "(fantabot.bots.bot_l3.identita_canonica)"),
            "completamento_etichetta":
                [etichetta_completamento(t) for t in COMPLETAMENTI_AMMESSI],
            "contesto": contesto,
            "contesto_blocchi": list(BLOCCHI_CONTESTO),
            "conteggio_stati": conta,
            "tetti": tetti}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--stagione", default="2026-27")
    ap.add_argument("--piano", required=True)
    ap.add_argument("--scenari", type=int, default=20)
    ap.add_argument("--repliche", type=int, default=4)
    ap.add_argument("--prezzi", type=int, default=5)
    ap.add_argument("--seme", type=int, default=20260907)
    ap.add_argument("--squadre", type=int, default=10,
                    help="squadre al tavolo: i nomi devono essere quelli del "
                         "motore d'asta (T0..Tn-1)")
    ap.add_argument("--seggio", type=int, default=0,
                    help="il nostro posto al tavolo. I tetti sono verificabili "
                         "solo nelle repliche giocate da questo seggio: gli "
                         "altri hanno un insieme di avversari diverso e "
                         "l'impronta non combacia")
    a = ap.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)

    with open(ROOT / "data" / "packs" / f"pack_{a.stagione}.pkl", "rb") as f:
        pack = pickle.load(f)
    with open(ROOT / "data" / "l2" / f"cubo_{a.stagione}.pkl", "rb") as f:
        salvato = pickle.load(f)
    cubo = salvato["cubo"]

    preds = pack.b_predictions
    pool, prezzi, valori = {}, {}, {}
    nel_cubo = set(cubo.giocatori)
    for pid, p in pack.players.items():
        chiave = int(pid) if str(pid).isdigit() else pid
        if chiave not in nel_cubo:
            continue
        pool[chiave] = p
        pr = preds.get(pid, {}) or preds.get(str(pid), {})
        prezzi[chiave] = max(1.0, float(pr.get("q50", p.ref_price * pack.budget)))
        valori[chiave] = float(pr.get("value", 0.0))

    bonus = getattr(cubo, "gol_subiti", None) is not None
    if not bonus:
        print("ATTENZIONE: il cubo non porta i gol subiti; il bonus porta "
              "inviolata NON entra nei punteggi.")
    regole = V.Regole(quote=dict(pack.quotas), budget=pack.budget,
                      usa_mod_difesa=bool(pack.use_mod_difesa),
                      applica_bonus_porta_inviolata=bonus)

    piano = json.loads(Path(a.piano).read_text("utf-8"))
    bersagli = [int(pid) for r in piano["rosa"] for pid in piano["rosa"][r]]
    fuori = [pid for pid in bersagli if pid not in pool]
    if fuori:
        # un giocatore del piano che non e' nel cubo non e' valutabile: lo si
        # dichiara invece di saltarlo in silenzio
        print(f"BLOCCO PARZIALE: {len(fuori)} giocatori del piano non sono nel "
              f"cubo e restano senza tetto: {fuori}")
    bersagli = [pid for pid in bersagli if pid in pool]

    n_scen = cubo.fantavoto.shape[0]
    scenari = list(range(min(a.scenari, n_scen // 2)))
    cal = V.calendario_berger(a.squadre, cubo.fantavoto.shape[1], seme=a.seme)
    # stessi nomi del motore d'asta, seggio compreso: sono dentro l'impronta
    # della chiave di validita' e il consumatore li ricalcola da `team_id`
    avversari = {f"T{i}": {"rosa": {r: [] for r in regole.quote},
                           "budget": float(pack.budget)}
                 for i in range(a.squadre) if i != a.seggio}
    stato = I.StatoAsta(nostra={r: [] for r in regole.quote},
                        nostro_budget=float(pack.budget), avversari=avversari,
                        disponibili=set(pool), regole=regole)

    records, contesto = {}, None
    t_tot = time.time()
    for k, g in enumerate(bersagli, 1):
        mercato = int(round(prezzi[g]))
        griglia = sorted({max(1, int(mercato * f))
                          for f in (0.6, 0.8, 1.0, 1.3, 1.6, 2.0)})[:a.prezzi]
        t0 = time.time()
        c = I.curva(g, stato, pool, prezzi, valori, cubo, cal, scenari,
                    prezzi_da_provare=griglia, repliche=a.repliche, seme=a.seme)
        dt = time.time() - t0
        rec = record_tetto(g, c, pool[g].name, pool[g].role, mercato, dt)
        records[identita_canonica(g)] = rec
        if contesto is None:
            contesto = contesto_di(rec)
        print(f"{k:2d}/{len(bersagli)} {pool[g].name[:22]:22s} "
              f"({pool[g].role}, mercato {mercato:3d}) tetto "
              f"{str(rec.get('tetto_economico')):>4s} | "
              f"{rec.get('stato', 'inconcludente'):14s} {dt:5.1f} s")

    if contesto is None:
        print("nessun bersaglio valutabile: niente da scrivere")
        return 1
    riassunto = costruisci_riassunto(records, contesto, {
        "stagione": a.stagione, "seme": a.seme, "scenari": len(scenari),
        "repliche": a.repliche, "piano": str(a.piano),
        "squadre": a.squadre, "seggio": a.seggio,
        "avversari_dichiarati": sorted(avversari),
        "validita_dichiarata": (
            "i tetti valgono per lo stato d'asta descritto in "
            "`chiave_validita` e per il seggio dichiarato: in una replica "
            "giocata da un altro seggio, o dopo il primo martelletto, il "
            "consumatore li respinge e conta il ripiego"),
        "giocatori_senza_tetto_fuori_dal_cubo": fuori,
        "secondi_totali": round(time.time() - t_tot, 1),
    })
    percorso = OUT / f"tetti_{a.stagione}.json"
    percorso.write_text(json.dumps(riassunto, indent=1, default=str),
                        encoding="utf-8")
    print(f"\nstati: {riassunto['conteggio_stati']}")
    print(f"completamento: {riassunto['completamento_etichetta']}")
    print(f"scritto {percorso}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
