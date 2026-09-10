"""Compito S: 30+ rose candidate valutate con la simulazione di stagione di f12.

Tutto nello scratchpad: pack ed eleggibilita' sono copie, i pack storici sono
letti in sola lettura. Nessun file del progetto viene scritto.

Uso: python rose_candidate.py [--sims 40]
"""
from __future__ import annotations

import csv
import itertools
import json
import pickle
import random
import sys
import time
from pathlib import Path

import numpy as np

W7 = Path(__file__).resolve().parent
PROG = Path(r"fantabot")
sys.path.insert(0, str(PROG / "src"))

from fantabot.montecarlo import (archetype_rosters, build_dists, calendari,  # noqa: E402
                                 p_first, simulate_roster)
from fantabot.models import ROLES  # noqa: E402
from fantabot.optimizer import optimize_roster  # noqa: E402
from fantabot.rules import MIN_SPEND_FRAC  # noqa: E402

SEED = 1
# seme degli scenari: 1001 e' quello del giro principale (stesso schema di f12,
# seed*1000+1); --seme 1002 da' scenari MAI usati nel giro principale (verifica)
SEED_SCENARI = int(sys.argv[sys.argv.index("--seme") + 1]) if "--seme" in sys.argv else SEED * 1000 + 1
N_SIMS = int(sys.argv[sys.argv.index("--sims") + 1]) if "--sims" in sys.argv else 40
SUF = sys.argv[sys.argv.index("--suffisso") + 1] if "--suffisso" in sys.argv else ""
PAROLE_NEG = ["copertura", "discontinuo", "fragile", "pacco",
              "non da fantacalcio", "sopravvalutato"]


def carica():
    with open(W7 / "pack_2026-27.pkl", "rb") as f:
        pack = pickle.load(f)
    hist_votes, hist_voti = [], []
    for s in ("2024-25", "2025-26"):
        with open(PROG / "data" / "packs" / f"pack_{s}.pkl", "rb") as f:
            pp = pickle.load(f)
        hist_votes.append(pp.votes_by_g)
        hist_voti.append(pp.voti_by_g or [])
    with open(W7 / "eleggibilita_2026-27.json", encoding="utf-8") as f:
        elig = json.load(f)
    with open(W7 / "note_esperto_2026-27.json", encoding="utf-8") as f:
        note = json.load(f).get("note", {})
    return pack, hist_votes, hist_voti, elig, note


def main():
    t0 = time.time()
    pack, hist_votes, hist_voti, elig, note = carica()
    players, preds = pack.players, pack.b_predictions
    budget, quotas = pack.budget, pack.quotas
    prezzi_q50 = {pid: max(1.0, float(preds.get(pid, {}).get("q50", 1.0))) for pid in players}
    mercato_raw = elig.get("prezzo_mercato_10sq_500", {})
    prezzi_mkt = {pid: max(1.0, float(mercato_raw.get(pid, prezzi_q50[pid]))) for pid in players}
    ref = {pid: max(1.0, p.ref_price * budget) for pid, p in players.items()}
    values = {pid: float(preds.get(pid, {}).get("value", 0.0)) for pid in players}
    values_up = {pid: float(preds.get(pid, {}).get("value_up", values[pid])) for pid in players}
    indispo = set(elig.get("indisponibili", {}))
    neg = {nome for nome, testo in note.items()
           if any(w in str(testo).lower() for w in PAROLE_NEG)}
    nomi_neg_pid = {pid for pid, p in players.items() if p.name in neg}
    print(f"pack: {len(players)} giocatori, budget {budget}, quote {quotas}")
    print(f"note esperto negative: {len(neg)} nomi, {len(nomi_neg_pid)} id in pack")

    dists = build_dists(players, preds, hist_votes, hist_voti)
    rng = random.Random(SEED)
    opps = archetype_rosters(players, ref, quotas, budget, rng, preds=preds)
    opp_scores = [simulate_roster(o, dists, N_SIMS, rng, seed_scenari=SEED_SCENARI)
                  for o in opps]
    cal = calendari(len(opps) + 1, N_SIMS, SEED_SCENARI)
    print(f"avversari archetipo simulati in {time.time() - t0:.0f}s")

    # --- liste di appoggio -------------------------------------------------
    att = sorted([pid for pid in players if players[pid].role == "A"],
                 key=lambda p: -values[p])
    att_cari = sorted([pid for pid in players if players[pid].role == "A"],
                      key=lambda p: -prezzi_q50[p])
    por = sorted([pid for pid in players if players[pid].role == "P"],
                 key=lambda p: -values[p])
    per_nome = {}
    for pid, p in players.items():
        per_nome.setdefault(p.name, pid)
    banditi = {n: per_nome[n] for n in ("Colombo", "Raimondo", "Vlasic", "Zaccagni")
               if n in per_nome}
    print("banditi (nome -> id):", banditi)

    base = dict(prezzi="q50", lam=0.5, share=(0.35, 0.50), bench_weight=0.30)

    def cfg(label, nota, **kw):
        d = dict(base)
        d.update(kw)
        d["label"] = label
        d["nota"] = nota
        return d

    configs = [cfg("R01", "riferimento: lam 0.5, attacco 35-50%")]

    # R01 va risolta subito: serve il suo bomber per scegliere i sei di R02-R07
    def risolvi(c):
        prezzi = prezzi_q50 if c["prezzi"] == "q50" else prezzi_mkt
        kw = {}
        if c["share"] is not None:
            kw["forced_spend"] = {"A": (c["share"][0] * budget, c["share"][1] * budget)}
        for k in ("required", "banned", "required_starters"):
            if c.get(k):
                kw[k] = set(c[k])
        return optimize_roster(players, prezzi, values, quotas, budget,
                               values_up=values_up, lam=c["lam"],
                               bench_weight=c["bench_weight"],
                               min_spend=MIN_SPEND_FRAC * budget, time_limit=20, **kw)

    sol01 = risolvi(configs[0])
    bomber01 = max(sol01["roster"]["A"], key=lambda p: values[p])
    print("R01 bomber:", players[bomber01].name)

    sei = [p for p in att if p != bomber01][:6]
    for i, pid in enumerate(sei):
        configs.append(cfg(f"R{i + 2:02d}", f"bomber imposto {players[pid].name}",
                           required=[pid], required_starters=[pid]))
    configs += [
        cfg("R08", "attacco 20-35%", share=(0.20, 0.35)),
        cfg("R09", "attacco 50-65%", share=(0.50, 0.65)),
        cfg("R10", "lam 0 (nessun peso all'upside)", lam=0.0),
        cfg("R11", "lam 1 (tutto peso all'upside)", lam=1.0),
    ]
    ban_lab = [("R12", ["Colombo"]), ("R13", ["Raimondo"]), ("R14", ["Vlasic"]),
               ("R15", ["Zaccagni"]),
               ("R15T", ["Colombo", "Raimondo", "Vlasic", "Zaccagni"])]
    for lab, nomi in ban_lab:
        ids = [banditi[n] for n in nomi if n in banditi]
        configs.append(cfg(lab, "escluso/i " + ", ".join(nomi), banned=ids))
    coppie = list(itertools.combinations(att_cari[:5], 2))[:4]
    for i, (a, b) in enumerate(coppie):
        # due bomber cari insieme sfondano il tetto 50% d'attacco (Malen 145 +
        # Martinez 143 = 288 > 250): quota allargata a 35-80%, dichiarato
        configs.append(cfg(f"R{i + 16:02d}",
                           f"due bomber {players[a].name} + {players[b].name} "
                           "(attacco 35-80%)",
                           share=(0.35, 0.80), required=[a, b], required_starters=[a, b]))
    for i, pid in enumerate(por[:4]):
        configs.append(cfg(f"R{i + 20:02d}", f"portiere titolare imposto {players[pid].name}",
                           required=[pid], required_starters=[pid]))
    # modulo forzato: optimize_roster NON espone un vincolo di modulo (il modulo
    # e' una variabile del MILP, m_k, senza parametro d'ingresso). Ripiego
    # dichiarato: bench_weight 0.15 e 0.45, che sposta il peso fra titolari e
    # panchina e quindi anche il modulo scelto.
    configs += [
        cfg("R24", "bench_weight 0.15 (modulo non forzabile: ripiego)", bench_weight=0.15),
        cfg("R25", "bench_weight 0.45 (modulo non forzabile: ripiego)", bench_weight=0.45),
        cfg("R26", "bench_weight 0.15 + lam 0", bench_weight=0.15, lam=0.0),
        cfg("R27", "bench_weight 0.45 + lam 1", bench_weight=0.45, lam=1.0),
        cfg("R28", "prezzi di mercato, attacco 35-50%", prezzi="mkt"),
        cfg("R29", "prezzi di mercato, nessun vincolo d'attacco", prezzi="mkt", share=None),
        cfg("R30", "prezzi di mercato, nessun vincolo, lam 1", prezzi="mkt",
            share=None, lam=1.0),
    ]

    # --- risoluzione + simulazione ----------------------------------------
    righe, chiavi, cache = [], {}, {}
    sc01 = None
    for c in configs:
        t1 = time.time()
        sol = sol01 if c["label"] == "R01" else risolvi(c)
        if sol is None:
            print(f"{c['label']}: NON FATTIBILE ({c['nota']})")
            righe.append({"label": c["label"], "nota": c["nota"], "fattibile": 0})
            continue
        ros = sol["roster"]
        ids = [pid for r in ROLES for pid in ros[r]]
        key = tuple(sorted(ids))
        dup = chiavi.get(key)
        chiavi.setdefault(key, c["label"])
        # rosa identica a una gia' simulata: con gli scenari comuni il risultato
        # e' lo stesso, si riusa invece di rifare 40 stagioni
        if key in cache:
            sc = cache[key]
        else:
            sc = simulate_roster(ros, dists, N_SIMS, rng, seed_scenari=SEED_SCENARI)
            cache[key] = sc
        if c["label"] == "R01":
            sc01 = sc
        tot = sc.sum(1)
        pw = p_first(sc, opp_scores, rng, cal=cal)
        se_pw = float(np.sqrt(max(pw * (1 - pw), 1e-9) / N_SIMS))
        diff = tot - sc01.sum(1)
        se_diff = float(diff.std(ddof=1) / np.sqrt(N_SIMS))
        spesa = {r: sum(prezzi_q50[p] for p in ros[r]) for r in ROLES}
        spesa_mkt = {r: sum(prezzi_mkt[p] for p in ros[r]) for r in ROLES}
        costo_q50 = sum(spesa.values())
        starters = sol["starters"]
        bomber = max(ros["A"], key=lambda p: values[p])
        righe.append({
            "label": c["label"], "nota": c["nota"], "fattibile": 1,
            "duplicato_di": dup or "",
            "modulo": sol["module"],
            "costo_q50": round(costo_q50, 1),
            "costo_prezzi_usati": round(sol["cost"], 1),
            "legale_q50": int(costo_q50 <= budget + 1e-6),
            "spesa_P": round(spesa["P"], 1), "spesa_D": round(spesa["D"], 1),
            "spesa_C": round(spesa["C"], 1), "spesa_A": round(spesa["A"], 1),
            "quota_attacco_q50": round(spesa["A"] / costo_q50, 3),
            "costo_mercato": round(sum(spesa_mkt.values()), 1),
            "somma_value": round(sum(values[p] for p in ids), 1),
            "n_indisponibili": sum(1 for p in ids if p in indispo),
            "n_note_negative": sum(1 for p in ids if p in nomi_neg_pid),
            "punti_medi": round(float(tot.mean()), 1),
            "sd_stagione": round(float(tot.std(ddof=1)), 1),
            "se_media": round(float(tot.std(ddof=1) / np.sqrt(N_SIMS)), 1),
            "diff_vs_R01": round(float(diff.mean()), 1),
            "se_diff_appaiato": round(se_diff, 1),
            "serio": int(float(diff.mean()) >= -se_diff),
            "p_win": round(pw, 3), "se_p_win": round(se_pw, 3),
            "bomber": players[bomber].name,
            "titolari": " | ".join(f"{players[p].name}({players[p].role})"
                                   for r in ROLES for p in ros[r] if p in starters),
            "rosa_P": ", ".join(players[p].name for p in ros["P"]),
            "rosa_D": ", ".join(players[p].name for p in ros["D"]),
            "rosa_C": ", ".join(players[p].name for p in ros["C"]),
            "rosa_A": ", ".join(players[p].name for p in ros["A"]),
        })
        r = righe[-1]
        print(f"{c['label']} {r['modulo']} costo {r['costo_q50']:.0f} "
              f"punti {r['punti_medi']:.0f} diff {r['diff_vs_R01']:+.0f}+-{se_diff:.0f} "
              f"P1 {pw:.0%} [{time.time() - t1:.0f}s] {c['nota']}")

    # --- uscite ------------------------------------------------------------
    campi = list(righe[0].keys())
    for r in righe:
        for k in campi:
            r.setdefault(k, "")
    with open(W7 / f"rose_candidate{SUF}.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=campi)
        w.writeheader()
        w.writerows(righe)

    ok = [r for r in righe if r.get("fattibile")]
    ok.sort(key=lambda r: -r["punti_medi"])
    with open(W7 / f"rose_candidate{SUF}.md", "w", encoding="utf-8") as f:
        f.write("# Rose candidate (compito S)\n\n")
        f.write(f"- {len(ok)} rose simulate, {N_SIMS} scenari ciascuna, scenari e "
                f"calendario COMUNI (seme {SEED_SCENARI}), 9 avversari archetipo.\n")
        f.write("- Ordinamento: punti medi a stagione. P(1) riportato ma NON usato per "
                "ordinare (errore standard ~8 punti percentuali con 40 scenari).\n")
        f.write("- `serio` = differenza di punti medi rispetto a R01 entro 1 errore "
                "standard appaiato o migliore (criterio scritto prima, `criteri_prima_S.md`).\n\n")
        f.write("| # | rosa | nota | modulo | costo q50 | att% | value | indisp | note neg | "
                "punti medi | sd | diff vs R01 | +-SE | serio | P(1) | +-SE | bomber |\n")
        f.write("|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|\n")
        for i, r in enumerate(ok, 1):
            f.write(f"| {i} | {r['label']} | {r['nota']} | {r['modulo']} | "
                    f"{r['costo_q50']:.0f} | {r['quota_attacco_q50']:.0%} | "
                    f"{r['somma_value']:.0f} | {r['n_indisponibili']} | {r['n_note_negative']} | "
                    f"{r['punti_medi']:.0f} | {r['sd_stagione']:.0f} | "
                    f"{r['diff_vs_R01']:+.0f} | {r['se_diff_appaiato']:.0f} | "
                    f"{'si' if r['serio'] else 'no'} | {r['p_win']:.0%} | "
                    f"{r['se_p_win']:.0%} | {r['bomber']} |\n")
        f.write("\n## Titolari (tutte le rose, ordine della tabella)\n\n")
        for i, r in enumerate(ok, 1):
            f.write(f"- **{r['label']}** ({r['modulo']}): {r['titolari']}\n")
        f.write("\n## Le 5 migliori per punti medi, reparto per reparto\n\n")
        f.write("Rose DIVERSE fra loro: chi ha gli stessi 25 di una gia' scritta "
                "(colonna `duplicato_di`) non si ripete.\n\n")
        distinte = [r for r in ok if not r["duplicato_di"]][:5]
        for r in distinte:
            f.write(f"### {r['label']} - {r['nota']}\n")
            f.write(f"modulo {r['modulo']}, costo q50 {r['costo_q50']:.0f} "
                    f"(P {r['spesa_P']:.0f} / D {r['spesa_D']:.0f} / C {r['spesa_C']:.0f} / "
                    f"A {r['spesa_A']:.0f}), value {r['somma_value']:.0f}, "
                    f"indisponibili {r['n_indisponibili']}, note negative {r['n_note_negative']}, "
                    f"punti {r['punti_medi']:.0f} +- {r['se_media']:.0f}, "
                    f"P(1) {r['p_win']:.0%} +- {r['se_p_win']:.0%}\n\n")
            for rr, nome in (("P", "Portieri"), ("D", "Difensori"),
                             ("C", "Centrocampisti"), ("A", "Attaccanti")):
                f.write(f"- {nome}: {r['rosa_' + rr]}\n")
            f.write("\n")
        # controllo su scenari MAI usati nel giro principale (seme 1002, 200
        # scenari): serve a vedere quali differenze reggono e quali erano rumore
        ver = W7 / "rose_candidate_verifica200.csv"
        if not SUF and ver.exists():
            with open(ver, encoding="utf-8") as g:
                vr = {r["label"]: r for r in csv.DictReader(g)}
            f.write("\n## Controllo su scenari nuovi (seme 1002, 200 scenari)\n\n")
            f.write("Stesse rose, scenari mai usati sopra e quattro volte piu' numerosi. "
                    "Una differenza che cambia segno qui era rumore.\n\n")
            f.write("| rosa | diff vs R01 (40 sc.) | diff vs R01 (200 sc.) | +-SE | serio a 200 |\n")
            f.write("|---|---|---|---|---|\n")
            for r in ok:
                w2 = vr.get(r["label"])
                if not w2 or not w2.get("punti_medi"):
                    continue
                f.write(f"| {r['label']} | {r['diff_vs_R01']:+.0f} | "
                        f"{float(w2['diff_vs_R01']):+.0f} | "
                        f"{float(w2['se_diff_appaiato']):.0f} | "
                        f"{'si' if w2['serio'] == '1' else 'no'} |\n")
        f.write(f"\nTempo totale {time.time() - t0:.0f}s.\n")
    print(f"fatto in {time.time() - t0:.0f}s -> rose_candidate{SUF}.csv / .md")


if __name__ == "__main__":
    main()
