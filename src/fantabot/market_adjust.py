"""Aggiustamento mercato: porta le predizioni pre-asta al "qui e ora".

Il modello valore/prezzo e' allenato su feature note al 1 settembre delle
stagioni passate. Per l'asta VERA della stagione corrente esistono segnali
freschi che il modello non vede: infortuni e squalifiche (giornate perse),
percentuale di titolarita' dalle probabili formazioni, rigoristi, presenze
gia' giocate, e soprattutto i prezzi REALI delle aste gia' fatte quest'anno.

Regole trasparenti (nessun riaddestramento):
  value_adj = value * fattore_disponibilita * fattore_titolarita * bonus_rigori
  q50_adj   = w_mkt * prezzo_mercato + (1 - w_mkt) * q50_modello   (se mercato noto)
  q10/q90   traslati dello stesso delta di q50

Tutto e' loggato per riga in `motivi`, cosi' l'utente vede PERCHE' un
giocatore e' sceso o salito.
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field

import pandas as pd

GIORNATE = 38
MESI = {"settembre": 9, "ottobre": 10, "novembre": 11, "dicembre": 12,
        "gennaio": 1, "febbraio": 2, "marzo": 3, "aprile": 4, "maggio": 5}
# giornata approssimativa di inizio mese (calendario tipo Serie A)
GIORNATA_A_INIZIO_MESE = {9: 3, 10: 6, 11: 10, 12: 14, 1: 19, 2: 23, 3: 27,
                          4: 31, 5: 35}


def norm(s: str) -> str:
    s = unicodedata.normalize("NFKD", str(s or ""))
    s = "".join(c for c in s if not unicodedata.combining(c)).upper()
    s = re.sub(r"[^A-Z0-9 ]+", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def giornate_perse_da_testo(testo: str, giornata_corrente: int) -> float | None:
    """Stima le giornate perse da un testo tipo 'rientro da novembre',
    'stagione finita', 'due giornate', '2 turni'. None se non capito."""
    t = (testo or "").lower()
    if not t:
        return None
    if "stagione" in t and ("finita" in t or "conclusa" in t or "fine" in t):
        return float(GIORNATE - giornata_corrente + 1)
    m = re.search(r"(\d+)\s*(giornat|turn|partit)", t)
    if m:
        return float(m.group(1))
    parole = {"una": 1, "due": 2, "tre": 3, "quattro": 4}
    for w, n in parole.items():
        if re.search(rf"\b{w}\s+(giornat|turn|partit)", t):
            return float(n)
    for mese, num in MESI.items():
        if mese in t:
            g_rientro = GIORNATA_A_INIZIO_MESE[num]
            if "fine" in t or "meta" in t:
                g_rientro += 2
            return float(max(0, g_rientro - giornata_corrente))
    if "settiman" in t:
        m = re.search(r"(\d+)\s*settiman", t)
        if m:
            return float(m.group(1))
        return 3.0
    if "giorni" in t:
        m = re.search(r"(\d+)\s*giorni", t)
        if m:
            return float(int(m.group(1)) / 7)
    if "lungo" in t or "crociato" in t or "legamento" in t:
        return 20.0
    return None


def fattore_titolarita(pct: float | None, presenze: int | None,
                       giornate_giocate: int) -> tuple[float, str]:
    if pct is not None and not pd.isna(pct):
        if pct >= 75:
            return 1.0, f"titolare {pct:.0f}%"
        if pct >= 50:
            return 0.88, f"ballottaggio {pct:.0f}%"
        if pct >= 25:
            return 0.70, f"riserva {pct:.0f}%"
        return 0.50, f"fuori dai titolari {pct:.0f}%"
    if presenze is not None and giornate_giocate >= 2:
        r = presenze / giornate_giocate
        if r >= 0.99:
            return 1.0, f"{presenze}/{giornate_giocate} presenze"
        if r >= 0.5:
            return 0.85, f"{presenze}/{giornate_giocate} presenze"
        return 0.60, f"{presenze}/{giornate_giocate} presenze"
    return 1.0, ""


@dataclass
class MarketInputs:
    """Tabelle del mercato corrente, gia' con master_id agganciato."""
    probabili: pd.DataFrame | None = None      # master_id, pct_titolarita, stato
    indisponibili: pd.DataFrame | None = None  # master_id, tipo, dettaglio, rientro_atteso
    rigoristi: set[str] = field(default_factory=set)   # master_id rigorista_1
    prezzi_live: pd.DataFrame | None = None    # master_id, p500_10sq (solo stagione corrente)
    presenze: dict[str, int] = field(default_factory=dict)  # master_id -> presenze finora
    giornata_corrente: int = 1
    giornate_giocate: int = 0


def adjust_predictions(pred: dict[str, dict], inputs: MarketInputs,
                       w_mkt: float = 0.6, bonus_rigori: float = 1.05) -> tuple[dict, pd.DataFrame]:
    """pred: master_id -> {q10,q50,q90,value}. Ritorna (pred_adj, log)."""
    prob = {}
    if inputs.probabili is not None:
        for r in inputs.probabili.itertuples(index=False):
            prob[str(r.master_id)] = float(r.pct_titolarita) if pd.notna(r.pct_titolarita) else None
    out_map: dict[str, tuple[float, str]] = {}
    if inputs.indisponibili is not None:
        for r in inputs.indisponibili.itertuples(index=False):
            g = giornate_perse_da_testo(str(getattr(r, "rientro_atteso", "") or "")
                                        + " " + str(getattr(r, "dettaglio", "") or ""),
                                        inputs.giornata_corrente)
            if g is None:
                g = 3.0 if str(getattr(r, "tipo", "")).startswith("squal") else 4.0
            prev = out_map.get(str(r.master_id), (0.0, ""))
            if g > prev[0]:
                out_map[str(r.master_id)] = (g, f"{r.tipo}: {getattr(r, 'dettaglio', '')} "
                                                f"({getattr(r, 'rientro_atteso', '')})".strip())
    mkt = {}
    if inputs.prezzi_live is not None:
        for r in inputs.prezzi_live.itertuples(index=False):
            v = getattr(r, "p500_10sq", None)
            if v is not None and pd.notna(v) and float(v) > 0:
                mkt[str(r.master_id)] = float(v)

    adj = {}
    rows = []
    restanti = max(1, GIORNATE - inputs.giornate_giocate)
    for pid, p in pred.items():
        value = float(p.get("value", 0.0))
        q10, q50, q90 = float(p["q10"]), float(p["q50"]), float(p["q90"])
        motivi = []
        f_disp = 1.0
        if pid in out_map:
            g, why = out_map[pid]
            f_disp = max(0.05, 1.0 - min(g, restanti) / restanti)
            motivi.append(f"out ~{g:.0f} giornate ({why})")
        f_tit, why_t = fattore_titolarita(prob.get(pid), inputs.presenze.get(pid),
                                          inputs.giornate_giocate)
        if why_t and f_tit < 1.0:
            motivi.append(why_t)
        f_rig = bonus_rigori if pid in inputs.rigoristi else 1.0
        if f_rig > 1.0:
            motivi.append("rigorista")
        value_adj = value * f_disp * f_tit * f_rig
        if pid in mkt:
            q50_new = w_mkt * mkt[pid] + (1 - w_mkt) * q50
            delta = q50_new - q50
            motivi.append(f"mercato reale {mkt[pid]:.0f}cr")
            q10, q50, q90 = max(1.0, q10 + delta), q50_new, q90 + delta
        f_all = f_disp * f_tit * f_rig
        adj[pid] = {"q10": round(q10, 2), "q50": round(q50, 2), "q90": round(q90, 2),
                    "value": round(value_adj, 1), "value_modello": round(value, 1),
                    "value_up": round(float(p.get("value_up", value)) * f_all, 1),
                    "pres": round(float(p.get("pres", 30.0)) * f_disp * f_tit, 1),
                    "motivi": "; ".join(motivi)}
        rows.append({"master_id": pid, "value": value, "value_adj": value_adj,
                     "q50_modello": float(p["q50"]), "q50_adj": q50,
                     "f_disp": f_disp, "f_tit": f_tit, "f_rig": f_rig,
                     "motivi": "; ".join(motivi)})
    return adj, pd.DataFrame(rows)
