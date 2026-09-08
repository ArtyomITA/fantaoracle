"""Motore delle regole: uno solo, condiviso da banco, replay e Copilota.

Due livelli tenuti separati, perche' cambiano per motivi diversi:

  1. **punteggio della fonte** — le regole di fantacalcio.it, verificate sui
     dati in `scripts/l2_costruisci_panel.py`. Non dipendono dalla lega:

         fantavoto = voto + 3*(gol + rigore_segnato) + assist
                     - 0.5*ammonizione - espulsione
                     + 3*rigori_parati - 3*rigori_sbagliati - 2*autogol
                     - gol_subiti (solo portieri)

  2. **regole della lega** — porta inviolata, modificatore difesa, soglie gol,
     numero di cambi. Stanno in `fantabot.rules` e `fantabot.season.lineup`,
     che restano l'unica fonte: qui vengono richiamate, non riscritte. Se un
     giorno la lega cambia, si cambia li' e cambia ovunque.

Il cubo produce eventi, non fantavoti: e' questo modulo a trasformarli in
punteggio, con le stesse regole con cui si valutano i dati reali. Cosi' il
confronto fra stagione simulata e stagione osservata usa la stessa
definizione delle quantita', che e' la condizione per poterle confrontare.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from ..rules import CLEAN_SHEET_BONUS, MAX_SUBS
from ..season.lineup import (          # noqa: F401  (riesportati di proposito)
    BASELINE, MODULES, goals_from_points, mod_difesa_bonus, pick_lineup,
    score_giornata,
)


@dataclass
class Tabellino:
    """Che cosa ha fatto un giocatore in una partita.

    Tutti i campi sono conteggi della partita, non tassi. `minuti` serve alle
    verifiche di coerenza, non al punteggio."""
    ruolo: str
    voto: float
    minuti: int = 0
    # estremi dell'intervallo di presenza, in minuti: servono a verificare che
    # ogni evento cada dentro il periodo in cui il giocatore era in campo.
    # `minuti` da solo non basta, perche' non dice QUANDO quei minuti sono
    # stati giocati.
    entrata: int = 0
    uscita: int = 0
    gol: int = 0
    rigore_segnato: int = 0
    assist: int = 0
    ammonizione: int = 0
    espulsione: int = 0
    rigori_parati: int = 0
    rigori_sbagliati: int = 0
    autogol: int = 0
    gol_subiti: int = 0
    titolare: bool = False


def fantavoto(t: Tabellino) -> float:
    """Punteggio della fonte. Il rigore segnato NON e' compreso nei gol."""
    subiti = t.gol_subiti if t.ruolo.upper() == "P" else 0
    return (t.voto + 3 * (t.gol + t.rigore_segnato) + t.assist
            - 0.5 * t.ammonizione - t.espulsione
            + 3 * t.rigori_parati - 3 * t.rigori_sbagliati
            - 2 * t.autogol - subiti)


def fantavoto_vettoriale(voto, ruolo, gol=0, rigore_segnato=0, assist=0,
                         ammonizione=0, espulsione=0, rigori_parati=0,
                         rigori_sbagliati=0, autogol=0, gol_subiti=0):
    """Stessa formula su array. `ruolo` e' un array di stringhe."""
    ruolo = np.asarray(ruolo)
    subiti = np.where(np.char.upper(ruolo.astype(str)) == "P",
                      np.asarray(gol_subiti), 0)
    return (np.asarray(voto, dtype=float)
            + 3 * (np.asarray(gol) + np.asarray(rigore_segnato))
            + np.asarray(assist)
            - 0.5 * np.asarray(ammonizione) - np.asarray(espulsione)
            + 3 * np.asarray(rigori_parati) - 3 * np.asarray(rigori_sbagliati)
            - 2 * np.asarray(autogol) - subiti)


def bonus_porta_inviolata(t: Tabellino) -> float:
    """Regola della lega: +1 al portiere che gioca senza subire gol."""
    if t.ruolo.upper() == "P" and t.minuti > 0 and t.gol_subiti == 0:
        return CLEAN_SHEET_BONUS
    return 0.0


def punti_lega(t: Tabellino) -> float:
    """Fantavoto della fonte piu' i bonus individuali della lega."""
    return fantavoto(t) + bonus_porta_inviolata(t)


def punteggio_squadra(rosa: dict[str, list[str]], tabellini: dict[str, Tabellino],
                      forma: dict[str, float], forma_voto: dict[str, float],
                      disponibili: set[str] | None = None,
                      usa_mod_difesa: bool = True,
                      max_cambi: int = MAX_SUBS) -> tuple[float, dict]:
    """Punteggio di una giornata per una rosa, con le regole della lega.

    `disponibili` e' l'informazione nota PRIMA della formazione (chi risultava
    disponibile alla vigilia). Gli esiti della giornata entrano solo nelle
    sostituzioni automatiche, come da regolamento: la scelta degli undici li
    precede.
    """
    punti = {pid: punti_lega(t) for pid, t in tabellini.items()}
    voti = {pid: t.voto for pid, t in tabellini.items()}
    modulo, titolari, panchina = pick_lineup(rosa, forma, forma_voto,
                                             usa_mod_difesa, disponibili)
    totale, cambi = score_giornata(titolari, panchina, punti, max_cambi,
                                   voti, usa_mod_difesa)
    return totale, {"modulo": modulo, "titolari": titolari,
                    "panchina": panchina, "cambi": cambi}


FINE_PARTITA = 90


def _in_campo_al(intervallo, minuto) -> bool:
    """Copia locale della convenzione di `partecipazione.in_campo_al`.

    Sta qui invece di essere importata per non creare una dipendenza fra il
    motore delle regole e il generatore: questo modulo deve poter verificare
    un tabellino che arrivi da qualunque parte.
    """
    if intervallo is None:
        return False
    a, b = intervallo
    if b <= a:
        return False
    if b >= FINE_PARTITA and minuto >= b:
        return True
    return a <= minuto < b


def verifica_coerenza(tab_casa: dict, tab_trasferta: dict,
                      gol_casa: int, gol_trasferta: int,
                      presenze: dict | None = None,
                      cronologia: dict | None = None,
                      gol_subiti_portiere: dict | None = None) -> list[str]:
    """Il tabellino deve riconciliarsi col risultato e con la fisica.

    Un gol della squadra di casa e' segnato da un suo giocatore (su azione o
    su rigore) oppure e' un autogol di un giocatore ospite.

    Con `presenze` (`{"casa": Presenze, "trasferta": Presenze}`) e
    `cronologia` (`{"casa": [evento], ...}`) il controllo diventa quello che il
    contratto chiede alla sezione 7.4: **ogni evento dentro l'intervallo di
    presenza di chi lo compie**, un portiere in campo in ogni minuto, l'espulso
    che non viene sostituito, e i gol subiti del portiere che sono quelli
    incassati mentre era in porta. Senza quegli argomenti il controllo resta
    quello vecchio — «il giocatore ha almeno un minuto» — che e' piu' debole e
    che infatti non intercettava i 57 gol assegnati a chi era gia' uscito.

    `gol_subiti_portiere` e' `{lato: {master_id: gol}}` calcolato dalla
    cronologia: se assente, il controllo sui gol subiti si limita a verificare
    che nessun portiere ne prenda piu' di quanti la squadra ne abbia presi.
    """
    problemi = []
    presenze = presenze or {}
    cronologia = cronologia or {}
    gol_subiti_portiere = gol_subiti_portiere or {}
    for et, mia, altrui, miei_gol, gol_altrui in (
            ("casa", tab_casa, tab_trasferta, gol_casa, gol_trasferta),
            ("trasferta", tab_trasferta, tab_casa, gol_trasferta, gol_casa)):
        segnati = sum(t.gol + t.rigore_segnato for t in mia.values())
        autogol_altrui = sum(t.autogol for t in altrui.values())
        if segnati + autogol_altrui != miei_gol:
            problemi.append(
                f"{et}: {segnati} gol dei giocatori + {autogol_altrui} autogol "
                f"avversari != {miei_gol} del risultato")
        pres = presenze.get(et)
        attesi = gol_subiti_portiere.get(et)
        for pid, t in mia.items():
            if (t.gol or t.rigore_segnato or t.assist or t.autogol) and t.minuti <= 0:
                problemi.append(f"{et}: {pid} ha eventi ma 0 minuti")
            if t.ruolo.upper() == "P" and t.minuti > 0:
                if attesi is not None:
                    if t.gol_subiti != attesi.get(pid, 0):
                        problemi.append(
                            f"{et}: il portiere {pid} ha {t.gol_subiti} gol "
                            f"subiti ma ne ha incassati {attesi.get(pid, 0)} "
                            f"mentre era in porta")
                elif t.gol_subiti > gol_altrui:
                    problemi.append(
                        f"{et}: il portiere {pid} ha {t.gol_subiti} gol subiti "
                        f"ma la squadra ne ha presi {gol_altrui}")
        in_campo = sum(1 for t in mia.values() if t.titolare)
        if in_campo != 11:
            problemi.append(f"{et}: {in_campo} titolari, attesi 11")
        portieri = sum(1 for t in mia.values() if t.titolare and t.ruolo.upper() == "P")
        if portieri != 1:
            problemi.append(f"{et}: {portieri} portieri titolari, atteso 1")

        if pres is None:
            continue
        # --- invarianti fisiche, verificabili solo con gli intervalli -------
        for minuto in range(FINE_PARTITA):
            if pres.portiere_al(minuto) is None:
                problemi.append(f"{et}: nessun portiere in campo al {minuto}'")
                break
        attesi_in_campo = 11
        for minuto in range(FINE_PARTITA):
            usciti = sum(1 for m in pres.espulsi.values() if m <= minuto)
            n = sum(1 for iv in pres.intervalli.values()
                    if _in_campo_al(iv, minuto))
            if n != attesi_in_campo - usciti:
                problemi.append(
                    f"{et}: {n} in campo al {minuto}', attesi "
                    f"{attesi_in_campo - usciti} ({usciti} espulsi)")
                break
        for pid, m in pres.espulsi.items():
            iv = pres.intervalli.get(pid)
            if iv is None or iv[1] != m:
                problemi.append(
                    f"{et}: {pid} espulso al {m}' ma il suo intervallo "
                    f"finisce a {iv[1] if iv else '?'}")
            for mm, uscito, entrato in pres.sostituzioni:
                if uscito == pid:
                    problemi.append(
                        f"{et}: {pid} espulso al {m}' risulta sostituito da "
                        f"{entrato} al {mm}'")
        for ev in cronologia.get(et, []):
            pid = ev.get("autore")
            if pid is None:
                continue
            if ev["tipo"] == "espulsione":
                # il cartellino rosso E' l'evento che chiude l'intervallo: cade
                # sull'estremo destro, dove la convenzione [entrata, uscita)
                # dice gia' "fuori". Il controllo giusto e' che l'intervallo
                # finisca esattamente li'.
                iv = pres.intervalli.get(pid)
                if iv is None or not (iv[0] <= ev["minuto"] <= iv[1]) \
                        or iv[1] != ev["minuto"]:
                    problemi.append(
                        f"{et}: espulsione al {ev['minuto']:.0f}' di {pid} con "
                        f"intervallo {iv}")
                continue
            if not _in_campo_al(pres.intervalli.get(pid), ev["minuto"]):
                problemi.append(
                    f"{et}: {ev['tipo']} al {ev['minuto']:.0f}' assegnato a "
                    f"{pid}, che non era in campo "
                    f"(intervallo {pres.intervalli.get(pid)})")
    return problemi
