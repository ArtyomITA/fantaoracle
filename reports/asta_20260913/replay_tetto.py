"""Replay del tetto sull'asta VERA del 10/9/2026, lotto per lotto.

Ricostruisce lo stato del tavolo immediatamente prima di ogni attaccante
battuto a 40 crediti o piu' (`data/copilot/ledger_1789058317.json`, letto in
sola lettura) e chiede al Copilota quanto avrebbe consigliato di pagare, col
tetto nuovo. Serve a rispondere a una domanda sola: **il tetto sarebbe
arrivato al prezzo del tavolo?**

Nessun server, nessuna scrittura sul ledger: il modulo si carica per percorso
come fa `tests/test_copilot_asta.py` e lo stato si tronca in memoria.

Uso (dalla radice del progetto):
    PYTHONPATH=src python reports/asta_20260913/replay_tetto.py
Uscita: reports/asta_20260913/replay_tetto.md
"""
from __future__ import annotations

import datetime
import importlib.util
import json
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
LEDGER = ROOT / "data" / "copilot" / "ledger_1789058317.json"
USCITA = Path(__file__).with_name("replay_tetto.md")
PREZZO_MINIMO = 40


def carica():
    sys.path.insert(0, str(ROOT / "src"))
    spec = importlib.util.spec_from_file_location(
        "cop_replay", ROOT / "scripts" / "f10_copilot.py")
    c = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = c
    spec.loader.exec_module(c)
    c.PACK = c.load_pack("2026-27")
    c.ELEGGIBILITA = c.carica_eleggibilita("2026-27")
    # la data del 10/9 e' quella dell'asta: le rettifiche vanno lette con
    # l'orologio di quella sera, non con quello di oggi
    c.prepara_pack("2026-27", oggi=datetime.date(2026, 9, 10))
    c.LEDGER_PATH = Path(tempfile.mkdtemp(prefix="replay_")) / "ledger.json"
    return c


def stato_a(c, led, quanti):
    c.STATE.update({"season": "2026-27", "names": led["names"],
                    "my_index": led["my_index"], "budget": led["budget"],
                    "quotas": dict(led["quotas"]),
                    "events": [dict(e) for e in led["events"][:quanti]],
                    "bids": [], "esclusi_manuali": []})
    c.PIANI_CACHE.clear()
    c.INDIFF_CACHE.clear()
    c.rebuild_advisor()


def cap_del_bot(c, pid):
    """Il tetto che il bot da' da solo, col calore GLOBALE: e' la colonna
    «prima», quella che all'evento 190 diceva 116 su 311 spendibili."""
    v = c.view_for_me(c.PACK.players[pid].role)
    g = c.PACK.players[pid]
    alto = int(v.me.max_bid(v.quotas))
    if alto < 1 or not c._il_bot_pagherebbe(v, g, 1):
        return 0
    basso = 1
    while basso < alto:
        mezzo = (basso + alto + 1) // 2
        if c._il_bot_pagherebbe(v, g, mezzo):
            basso = mezzo
        else:
            alto = mezzo - 1
    return int(basso)


def attendi(c, pid, secondi=25.0):
    scadenza = time.time() + secondi
    d = c.decisione_operativa(pid, None)
    while d.get("stato_indifferenza") == "in_calcolo" and time.time() < scadenza:
        time.sleep(0.25)
        d = c.decisione_operativa(pid, None)
    return d


def main():
    c = carica()
    led = json.loads(LEDGER.read_text(encoding="utf-8"))
    eventi, nomi = led["events"], led["names"]
    mio = led["my_index"]
    righe = []
    for i, e in enumerate(eventi):
        p = c.PACK.players[e["player_id"]]
        if p.role != "A" or e["price"] < PREZZO_MINIMO:
            continue
        stato_a(c, led, i)
        v = c.view_for_me("A")
        vecchio = cap_del_bot(c, e["player_id"])
        d = attendi(c, e["player_id"])
        righe.append({
            "evento": i, "giocatore": p.name, "id": e["player_id"],
            "vincitore": nomi[e["team_index"]], "prezzo": e["price"],
            "mio": e["team_index"] == mio,
            "crediti": int(v.me.budget), "slot_A": int(v.me.slots_left(v.quotas, "A")),
            "max_spendibile": d["max_spendibile"],
            "cap_bot_vecchio": vecchio, "cap_bot_nuovo": d["cap_bot"],
            "calore_A": d["calore_ruolo"],
            "prezzo_indifferenza": d["prezzo_indifferenza"],
            "stato_indifferenza": d["stato_indifferenza"],
            "bomber_rimasti": d["bomber_rimasti"],
            "contendenti": d["squadre_contendenti"],
            "quota_scarsita": d["quota_scarsita"],
            "tetto": d["max_consigliato"],
            "arriva": d["max_consigliato"] >= e["price"]})
        print(f"{i:>4} {p.name:<16} {e['price']:>4} -> vecchio {vecchio:>3} "
              f"nuovo {d['max_consigliato']:>3} "
              f"(ind {d['prezzo_indifferenza']}, spend {d['max_spendibile']})")

    citati = {"5585", "2764", "6397", "6052"}
    quattro = [r for r in righe if r["id"] in citati]
    arrivati = [r for r in righe if r["arriva"]]
    sforati = [r for r in righe if r["tetto"] > r["max_spendibile"]]
    testa = ("| ev | giocatore | vincitore | prezzo | crediti | slot A | "
             "cap bot prima | cap bot dopo | indiff. | bomber | contend. | "
             "quota | tetto | arriva? |")
    sep = "|" + "---|" * 14
    corpo = [
        f"| {r['evento']} | {r['giocatore']}{' (mio)' if r['mio'] else ''} | "
        f"{r['vincitore']} | {r['prezzo']} | {r['crediti']} | {r['slot_A']} | "
        f"{r['cap_bot_vecchio']} | {r['cap_bot_nuovo']} | "
        f"{r['prezzo_indifferenza']} | {r['bomber_rimasti']} | "
        f"{r['contendenti']} | {r['quota_scarsita']} | **{r['tetto']}** | "
        f"{'SI' if r['arriva'] else 'no'} |" for r in righe]
    md = [
        "# Replay del tetto — asta del 10/9/2026",
        "",
        f"Generato da `reports/asta_20260913/replay_tetto.py` il "
        f"{datetime.datetime.now().isoformat(timespec='seconds')}.",
        "Ledger letto in sola lettura: `data/copilot/ledger_1789058317.json` "
        f"({len(eventi)} eventi, io = {nomi[mio]}).",
        "",
        f"Attaccanti battuti a {PREZZO_MINIMO} crediti o piu': {len(righe)}. "
        f"Il tetto nuovo arriva al prezzo del tavolo in **{len(arrivati)}** casi "
        f"su {len(righe)}; sui quattro lotti della diagnosi "
        f"(Malen, Martinez L., Ramos G., Hojlund) in "
        f"**{sum(1 for r in quattro if r['arriva'])}** su {len(quattro)}.",
        f"Tetti sopra il massimo spendibile: **{len(sforati)}** (deve essere 0).",
        "",
        "«cap bot prima» e' il tetto che il bot produce da solo, col calore "
        "globale del mercato: e' la colonna che la sera del 10/9 diceva 116 "
        "per Malen. «cap bot dopo» e' lo stesso tetto riletto col calore del "
        "RUOLO. «indiff.» e' il prezzo di indifferenza (bisezione MILP sul "
        "piano con lui contro il miglior piano senza di lui).",
        "",
        testa, sep, *corpo, "",
        "## Nota sui numeri della diagnosi",
        "",
        "L'audit del 12/9 misurava, sul codice di allora, 116 per Malen, 123 "
        "per Martinez L. e 102 per Hojlund. Qui la colonna «cap bot prima» "
        "puo' differire: il bonus gol di lega (+5 contro +3 della fonte) ha "
        "cambiato i valori del piano, e la quota di spesa in attacco ora si "
        "misura sul budget residuo invece che su quello totale. Il confronto "
        "che conta e' fra le due colonne di questa tabella, calcolate lo "
        "stesso giorno sullo stesso stato.",
    ]
    USCITA.write_text("\n".join(md), encoding="utf-8")
    print(f"\nScritto {USCITA}")
    print(f"arriva al prezzo: {len(arrivati)}/{len(righe)}; "
          f"dei quattro citati {sum(1 for r in quattro if r['arriva'])}/{len(quattro)}; "
          f"tetti oltre lo spendibile: {len(sforati)}")


if __name__ == "__main__":
    main()
