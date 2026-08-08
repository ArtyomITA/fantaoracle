# -*- coding: utf-8 -*-
"""Fase 0b — genera data/processed/FASE0B_REPORT.md con i numeri reali dei file prodotti."""
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).parent))
from f0b_lib import RAW, PROC, MATCH_DIR, PLAYERS_SEASONS, VOTI_SEASONS  # noqa: E402

L = []
add = L.append


def rate(df, key="master_id"):
    return f"{df[key].notna().sum()}/{len(df)} ({df[key].notna().mean()*100:.1f}%)"


def main():
    reg = pd.read_csv(PROC / "registry.csv")
    add("# FASE 0B — REPORT integrazione dataset\n")
    add("Generato da `scripts/f0b_write_report.py`. Pipeline: `f0b_build_registry.py` -> "
        "`f0b_match.py` -> `f0b_build_outputs.py`. Libreria matching: `f0b_lib.py`.\n")

    add("## 1. Registry (spina dorsale)\n")
    add(f"`registry.csv`: **{len(reg)} righe**, **{reg.master_id.nunique()} giocatori unici**, "
        "6 stagioni 2020/21-2025/26. master_id = player_id fantacalcio.it (stabile tra stagioni). "
        "Colonne per stagione: nome, squadra (sigla), ruolo Classic, Qt.I, FVM "
        "(FVM assente 2020-21 e 2021-22: colonna a NaN, limite della fonte).\n")

    add("## 2. Match rate per fonte/stagione\n")
    add("| fonte | stagione | match | note |")
    add("|---|---|---|---|")
    mv = pd.read_csv(MATCH_DIR / "map_voti.csv")
    for s in VOTI_SEASONS:
        d = mv[mv.stagione == s]
        add(f"| voti (nomi unici) | {s} | {rate(d)} | non matchati = fuori listone (primavera/gennaio) |")
    mfs = pd.read_csv(MATCH_DIR / "map_fantasoccer.csv")
    for (s, g), d in mfs.groupby(["stagione", "giornata"]):
        add(f"| fanta.soccer g{g:02d} | {s} | {rate(d)} | listino fanta.soccer include extra-listone |")
    mw = pd.read_csv(MATCH_DIR / "map_wayback.csv")
    for (s, f), d in mw.groupby(["stagione", "file"], sort=True):
        add(f"| wayback `{f[:40]}` | {s} | {rate(d)} | |")
    mg = pd.read_csv(MATCH_DIR / "map_ge.csv")
    for s, d in mg.groupby("stagione"):
        add(f"| gruppoesperti (nomi unici) | {s} | {rate(d)} | |")
    mu = pd.read_csv(MATCH_DIR / "map_understat.csv")
    for y, d in mu.groupby("understat_season"):
        s = d.stagione.iloc[0]
        note = "match su registry globale (stagione non a listone)" if y == 2019 else ""
        add(f"| understat | {s} | {rate(d)} | {note} |")
    mtm = pd.read_csv(MATCH_DIR / "map_tm.csv")
    add(f"| transfermarkt (per master) | tutte | {len(mtm)}/{reg.master_id.nunique()} "
        f"({len(mtm)/reg.master_id.nunique()*100:.1f}%) | non matchati: usciti dalla Serie A "
        "prima del 2019/20 (fuori dal set TM) |")
    add("")

    aste = pd.read_csv(PROC / "aste_reali_clean.csv")
    add("## 3. Aste reali pulite e price targets\n")
    n_aste = aste.groupby(["source_file", "auction_id"]).ngroups
    n_anom = aste[aste.asta_anomala == 1].groupby(["source_file", "auction_id"]).ngroups
    add(f"`aste_reali_clean.csv`: **{len(aste)} righe**, **{n_aste} aste uniche** "
        "(dedup fingerprint esatto da `build_stats.json` + dedup a soglia: coppie della "
        "stessa stagione/configurazione con >70% righe (giocatore, prezzo) identiche = "
        "stessa asta ricopiata, tenuta la copia piu' completa / `1J4t...`). Acquisti doppi "
        "intra-asta collassati a una riga per (asta, master) tenendo il primo prezzo "
        "(colonna `acquisti_doppi` = n righe originali). `spesa_ratio` = spesa totale "
        f"pre-collasso / (componenti x crediti); `asta_anomala`=1 se > 1.10 ({n_anom} aste, "
        "escluse dai target). master_id valorizzato su "
        f"**{aste.master_id.notna().mean()*100:.1f}%** delle righe.")
    per_s = aste.groupby("stagione").apply(
        lambda d: pd.Series({"aste": d.groupby(['source_file', 'auction_id']).ngroups,
                             "righe": len(d),
                             "estive": d[d.periodo <= 1].groupby(['source_file', 'auction_id']).ngroups,
                             "estive_10x500": d[(d.periodo <= 1) & (d.componenti == 10)
                                                & d.crediti_tot.between(400, 600)]
                             .groupby(['source_file', 'auction_id']).ngroups,
                             "anomale": d[d.asta_anomala == 1]
                             .groupby(['source_file', 'auction_id']).ngroups}),
        include_groups=False)
    add("\n| stagione | aste | righe | estive (per<=1) | estive 10x(400-600) | anomale |")
    add("|---|---|---|---|---|---|")
    for s, r in per_s.iterrows():
        add(f"| {s} | {r.aste} | {r.righe} | {r.estive} | {r.estive_10x500} | {r.anomale} |")
    pt = pd.read_csv(PROC / "price_targets.csv")
    add(f"\n`price_targets.csv`: **{len(pt)} righe** (master_id, stagione). Gerarchia di "
        "target (mean/std di pct_budget = prezzo/crediti_tot), tutte SOLO da aste non "
        "anomale; il modello di Fase 1 scegliera'/blendera':\n")
    add("- `*_10x500_estiva`: aste periodo<=1 (pre-campionato), 10 squadre, 400-600 crediti "
        "— il target piu' pulito ma campione piccolo (2024/25: **1 sola asta**);")
    add("- `*_all_estiva`: aste periodo<=1, TUTTE le configurazioni, in pct_budget "
        "normalizzato — il campione grande;")
    add("- `*_tardiva`: aste periodo>=2 (dopo l'avvio del campionato) — contaminate da "
        "informazione post-1/9 (cessioni tardive, infortuni), tenute separate;")
    add("- `wayback_p500_10sq`: prezzo stimato fantacalcio-online (500 crediti, 10 squadre), "
        "primo snapshot non nullo in ordine di priorita'; 0 trattato come NaN.\n")
    g = pt.groupby("stagione").agg(
        n=("master_id", "count"),
        est10=("n_obs_10x500_estiva", lambda x: (x > 0).sum()),
        est_all1=("n_obs_all_estiva", lambda x: (x > 0).sum()),
        est_all3=("n_obs_all_estiva", lambda x: (x >= 3).sum()),
        tard3=("n_obs_tardiva", lambda x: (x >= 3).sum()),
        wb=("wayback_p500_10sq", lambda x: x.notna().sum()))
    add("| stagione | giocatori | con 10x500 estiva | con all estiva | all estiva n>=3 | tardiva n>=3 | wayback |")
    add("|---|---|---|---|---|---|---|")
    for s, r in g.iterrows():
        add(f"| {s} | {r.n} | {r.est10} | {r.est_all1} | {r.est_all3} | {r.tard3} | {r.wb} |")
    add("\nNota: 2022/23 e 2025/26 senza aste GE (sheet rimossi dal forum, cfr. INVENTORY 3.2); "
        "2025/26 ha comunque il target wayback. 2020/21 presente solo via wayback (bonus).\n")
    add("Semantica `periodo` (verificata coi trasferimenti reali, cfr. sez. 8): 0 = asta "
        "estiva pre-campionato; 1 = a ridosso della 1a giornata; 2-3 = asta tenuta dopo "
        "l'avvio del campionato (settembre/autunno). NON sono riparazioni di gennaio: i "
        "ceduti nel mercato invernale (Kvaratskhelia 2024/25, Vlahovic e Kulusevski 2021/22, "
        "Dragusin 2023/24) compaiono a prezzo pieno anche nelle aste periodo 2-3, mentre "
        "CR7 (via il 27/8/2021) sparisce dalle aste p2 2021/22 e Osimhen 2024/25 crolla a "
        "1-3 crediti nelle aste successive alla cessione del 6/9: le p2-3 incorporano "
        "informazione post-avvio, per questo sono separate dal target estivo.\n")

    add("## 4. Dataset per stagione (players_*.parquet)\n")
    add("Una riga = giocatore nel listone fantacalcio.it della stagione. Regola anti-leakage: "
        "feature correnti = solo cio' che era noto al 1 settembre (Qt.I, FVM, quotazione "
        "fanta.soccer di inizio settembre, eta', valore transfermarkt <= 1/9, flag); storico = "
        "SOLO stagioni precedenti (prev1..prev3 voti; understat stagione precedente; xG squadra "
        "stagione precedente). Le colonne `target_*` (da price_targets della stagione stessa) "
        "sono il target e vanno escluse dalle feature.\n")
    add("| stagione | righe | squadra da fanta.soccer | eta' nota | prev1 fantamedia | "
        "understat prev | target all estiva n>=3 | target wayback |")
    add("|---|---|---|---|---|---|---|---|")
    snap_note = {}
    import json
    fs_snap = json.load(open(MATCH_DIR / "fs_snapshot.json", encoding="utf-8"))
    dates = pd.read_csv(RAW / "quotazioni" / "fantasoccer_date_rilevazioni.csv")
    for s in PLAYERS_SEASONS:
        p = pd.read_parquet(PROC / f"players_{s}.parquet")
        g_ = fs_snap[s][0]
        dt = dates[(dates.stagione == s) & (dates.giornata == g_)].data_rilevazione.iloc[0]
        snap_note[s] = f"g{g_} ({dt})"
        add(f"| {s} | {len(p)} | {(p.squadra_fonte=='fantasoccer').sum()} | "
            f"{p.eta.notna().sum()} | {p.prev1_fantamedia.notna().sum()} | "
            f"{p.us_prev_xg.notna().sum()} | {(p.target_n_obs_all_estiva>=3).sum()} | "
            f"{p.target_wayback_p500_10sq.notna().sum()} |")
    add("\nSnapshot fanta.soccer usati (rilevazione piu' vicina al 1/9): "
        + "; ".join(f"{s}: {v}" for s, v in snap_note.items()) + ".")
    add("Nota 2021/22: prev1..prev3 fantamedia tutte NaN (i voti partono dal 2021/22); il flag "
        "`nuovo_in_serie_a` per le stagioni pre-voti usa la presenza understat 2019/20-2020/21.\n")

    add("### Copertura target (n_obs_all_estiva >= 3) per ruolo e fascia Qt.I — stagioni con aste GE\n")
    for s in ["2021-22", "2023-24", "2024-25"]:
        p = pd.read_parquet(PROC / f"players_{s}.parquet")
        p["fascia"] = pd.cut(p.qt_i, [0, 5, 10, 20, 100], labels=["1-5", "6-10", "11-20", "21+"])
        cov = p.assign(ok=(p.target_n_obs_all_estiva >= 3)).pivot_table(
            index="fascia", columns="ruolo", values="ok", aggfunc="sum", observed=True)
        tot = p.pivot_table(index="fascia", columns="ruolo", values="master_id",
                            aggfunc="count", observed=True)
        add(f"\n**{s}** ({(p.target_n_obs_all_estiva>=3).sum()}/{len(p)} totale)\n")
        add("| fascia Qt.I | P | D | C | A |")
        add("|---|---|---|---|---|")
        for f_ in ["1-5", "6-10", "11-20", "21+"]:
            cells = []
            for r_ in ["P", "D", "C", "A"]:
                try:
                    c = cov.loc[f_, r_]
                    t = tot.loc[f_, r_]
                    cells.append(f"{int(c)}/{int(t)}" if pd.notna(t) else "-")
                except KeyError:
                    cells.append("-")
            add(f"| {f_} | " + " | ".join(cells) + " |")
    add("\nLettura: la fascia alta (Qt.I 11+) e' quasi completamente coperta; i buchi sono "
        "concentrati nella fascia 1-5 (scommesse/terze linee, spesso non chiamate nelle aste).\n")

    add("## 5. votes_*.parquet\n")
    add("| stagione | righe | % righe voti matchate |")
    add("|---|---|---|")
    for s in VOTI_SEASONS:
        v = pd.read_parquet(PROC / f"votes_{s}.parquet")
        raw_n = len(pd.read_csv(RAW / "voti" / f"voti_{s}.csv"))
        add(f"| {s} | {len(v)} | {len(v)/raw_n*100:.1f}% |")
    add("\nColonne: master_id, giornata, fantavoto, sv (righe S.V. mantenute e flaggate, "
        "fantavoto NaN). Righe non matchate scartate (giocatori fuori listone).\n")

    add("## 6. Esempio: 20 righe di players_2024-25 (nomi noti)\n")
    p = pd.read_parquet(PROC / "players_2024-25.parquet")
    noti = ["Martinez L.", "Kvaratskhelia", "Retegui", "Vlahovic", "Thuram", "Dovbyk",
            "Lookman", "Leao", "Dybala", "Pulisic", "Di Gregorio", "Kean", "Maignan",
            "Hernandez T.", "Barella", "Zambo Anguissa", "Zaccagni", "Orsolini",
            "Buongiorno", "Nico Paz", "Paz N.", "Colpani"]
    cols = ["nome", "ruolo", "squadra", "qt_i", "fvm", "quot_fs_sett", "eta", "tm_value_eur",
            "nuovo_in_serie_a", "prev1_fantamedia", "prev1_presenze", "prev1_gol", "us_prev_xg",
            "team_prev_xg", "target_n_obs_all_estiva", "target_mean_pct_all_estiva",
            "target_mean_pct_10x500_estiva", "target_mean_pct_tardiva",
            "target_wayback_p500_10sq"]
    d = p[p.nome.isin(noti)][cols].sort_values("target_mean_pct_all_estiva",
                                               ascending=False).head(20)
    d = d.round({"eta": 1, "prev1_fantamedia": 2, "us_prev_xg": 2, "team_prev_xg": 1,
                 "target_mean_pct_all_estiva": 4, "target_mean_pct_10x500_estiva": 4,
                 "target_mean_pct_tardiva": 4})
    add(d.to_markdown(index=False))
    add("")

    rep = pd.read_csv(PROC / "unmatched_report.csv")
    add("## 7. Buchi principali e decisioni\n")
    n_rej = rep.esito.astype(str).str.startswith("rejected").sum()
    add(f"`unmatched_report.csv`: **{len(rep)} righe** (ogni non-match/ambiguo/rifiutato con "
        f"top-3 candidati, di cui {n_rej} match RIFIUTATI dalle guardie ruolo/squadra/eta' "
        "del fix round 1). La claim 'zero match silenziosi' della prima versione era falsa "
        "(cfr. AUDIT.md): ora i conflitti vengono rifiutati esplicitamente e loggati qui. "
        "Ripartizione: "
        + "; ".join(f"{f_} {n}" for f_, n in rep.fonte.value_counts().items()) + ".\n")
    add("Buchi/limiti noti:")
    add("- **Aste GE assenti per 2022/23 e 2025/26** (sheet rimossi dal forum): per il 2025/26 "
        "il target prezzi e' solo wayback (`target_wayback_p500_10sq`, 509 giocatori).")
    add("- **Voti/fantasoccer non matchati** = giocatori fuori listone (primavera, arrivi di "
        "gennaio, terze linee fanta.soccer): buco strutturale, non risolvibile col matching.")
    mtm_ = pd.read_csv(MATCH_DIR / "map_tm.csv")
    add(f"- **Transfermarkt {len(mtm_)/reg.master_id.nunique()*100:.1f}% dei master**: i "
        "mancanti sono usciti dalla Serie A prima del 2019/20 (fuori dal set scaricato) o "
        "rifiutati dalle guardie eta'/omonimo del fix round 1 -> eta'/valore NaN.")
    add("- **understat 2019 (2019/20)**: matchato sul registry globale (stagione non coperta dal "
        "listone) all'86%; usato solo per il flag `nuovo_in_serie_a`.")
    add("- **Ambigui veri lasciati fuori** (documentati nel report): omonimi senza squadra nelle "
        "aste GE (MORENO D 2024/25, CARBONI D, FERRARI D 2021/22, KONE C, COULIBALY C).")
    add("")
    add("Decisioni prese:")
    add("- Chiave di matching: cognome NFKD uppercase + iniziale + ruolo + squadra (quando "
        "disponibili), con indice full-name, subset di token (cognomi composti tipo 'Zambo "
        "Anguissa'/'anguissa'), ~60 alias manuali (refusi GE tipo 'oshimen', 'sczesny', "
        "'lautaro'->Martinez L.) e fuzzy rapidfuzz (soglia 86, gap>=3) come ultima spiaggia. "
        "Fix round 1: matching a stadi con guardia anti-omonimo (P<->movimento mai fuso; "
        "match esatti rifiutati se ruolo E squadra confliggono o se la squadra confligge "
        "senza conferma di ruolo; alias/subset/fuzzy rifiutati con QUALSIASI conflitto).")
    add("- `html.unescape` su tutti i nomi (fix entita' `&#x27;` nei voti, 1.266 righe).")
    add("- Dedup aste: fingerprint esatto (tenuta la copia `1J4t...`) + dedup a soglia "
        "(>70% righe identiche a parita' di stagione e configurazione).")
    add("- Target prezzi: gerarchia per periodo (estive p<=1 vs tardive p>=2), aste anomale "
        "(spesa>1.10x budget) escluse; cfr. sez. 3.")
    add("- Squadra alla data d'asta: fanta.soccer snapshot inizio settembre (fallback listone "
        "fantacalcio.it, colonna `squadra_fonte`); wayback p500_10sq col separatore ';' e "
        "decimali con virgola dei CSV fonti_prezzi gestiti in ingestione.")
    add("- **Bias `squadra_listone`**: il CSV fantacalcio.it e' lo stato TARDO-stagione del "
        "listone, non la fotografia di settembre: per i ~140-175 giocatori/stagione con "
        "`squadra_fonte=fantacalcioit` (senza riga fanta.soccer) la squadra puo' riflettere "
        "un trasferimento di gennaio (es. Okafor 2024/25 listone=NAP, Vlahovic 2021/22 "
        "listone=JUV). Usare `squadra` (fanta.soccer) quando disponibile; il fallback "
        "listone va trattato come rumoroso.")
    add("- `nuovo_in_serie_a` = nessun voto nelle 3 stagioni precedenti (understat per le "
        "stagioni pre-2021/22); `squadra_neopromossa` = squadra assente dal listone precedente.")
    add("- CR7 a 630 crediti su 1000 (2021/22) e simili restano: outlier reali, non rimossi. "
        "Prezzo 0 (svincoli d'ufficio) mantenuto in aste_reali_clean, incluso nei target.")
    add("")

    # ------------------------------------------------------------- fix round 1
    add("## 8. Fix round 1 — difetti AUDIT.md corretti (prima/dopo)\n")
    add("Tutti i fix sono negli script `f0b_*` (pipeline riproducibile, nessuna patch a "
        "mano sugli output). 'Prima' = run auditato del 2026-08-06 (cfr. `AUDIT.md`).\n")

    add("### Difetto 1 (GRAVE) — omonimi fanta.soccer: guardia ruolo/squadra + selezione per qualita'\n")
    add("`SeasonIndex.match` ora rifiuta i match in conflitto (mai P<->movimento; esatti: "
        "rifiuto con ruolo+squadra entrambi in conflitto o squadra in conflitto senza "
        "conferma ruolo; alias/subset/fuzzy: rifiuto con qualsiasi conflitto), e un rifiuto "
        "non blocca gli stadi successivi (cosi' `Martinez L.|FIO|D` arriva a Martinez "
        "Quarta via token_subset+role+team). In `build_players` il keep-first arbitrario "
        "e' sostituito da `pick_best_per_master` (conferma squadra > ruolo > metodo; pari "
        "merito = riga scartata). Casi di controllo:\n")
    prima = {
        ("Martinez L.", "2021-22"): ("FIO", 8, 56.9),
        ("Martinez L.", "2023-24"): ("FIO", 8, None),
        ("Martinez L.", "2024-25"): ("FIO", 28, 58.1),
        ("Vlahovic", "2023-24"): ("ATA", 1, None),
        ("Chiesa", "2023-24"): ("VER", 1, None),
        ("Gonzalez N.", "2024-25"): ("LEC", 17, None),
        ("Viola", "2023-24"): ("LEC", 1, None),
    }
    add("| giocatore | stagione | squadra prima -> dopo | quot_fs prima -> dopo | team_prev_xg dopo |")
    add("|---|---|---|---|---|")
    for (nome, s), (sq0, q0, _) in prima.items():
        pp = pd.read_parquet(PROC / f"players_{s}.parquet")
        row = pp[pp.nome == nome]
        if len(row) == 0:
            add(f"| {nome} | {s} | {sq0} -> ? | {q0} -> ? | riga mancante |")
            continue
        row = row.iloc[0]
        q_dopo = row.quot_fs_sett if pd.notna(row.quot_fs_sett) else "NaN"
        xg = f"{row.team_prev_xg:.1f}" if pd.notna(row.team_prev_xg) else "NaN"
        add(f"| {nome} | {s} | {sq0} -> **{row.squadra}** | {q0} -> **{q_dopo}** | {xg} |")
    add("")

    add("### Difetto 2 (GRAVE) — target per periodo\n")
    add("Prima: `mean_pct_10x500` mescolava aste estive e post-avvio (2021/22: 7 p0 + 4 p1 "
        "+ 16 p2; 2023/24: 4+1+5+15 p3; 2024/25: 1 p0 su 9) e contava due volte l'asta "
        "near-dup 1J4t-14/1Uxv-14. Dopo: gerarchia estive/tardive di sez. 3, con "
        "l'avvertenza esplicita che il 2024/25 estivo 10x500 ha UNA sola asta (usare "
        "`*_all_estiva`, campione grande, o il blend in Fase 1).\n")

    add("### Difetto 3 (GRAVE) — dedup a soglia\n")
    add("Oltre al fingerprint esatto, coppie della stessa stagione+configurazione con "
        "overlap righe (giocatore, prezzo) > 70% = stessa asta ricopiata; tenuta la copia "
        "piu' completa (a pari righe la `1J4t...`). Trovate 9 coppie: le 4 dell'audit "
        "(1J4t-9/gruppoesperti-9 90%, 1J4t-11/gruppoesperti-11 93%, 1J4t-14/1Uxv-14 96%, "
        "1J4t-15/1Uxv-15 90%) PIU' 5 non viste dall'audit e verificate a mano sui top "
        "prezzi identici (gruppoesperti-8/1J4t-8 90%, gruppoesperti-10/1J4t-10 89%, "
        "1J4t-12/1J4t-21 94% intra-file, 1MeKG-27/33 98%, 2021-22circa-125/138 82%). "
        f"Le aste 2024/25 passano da 30 a {per_s.loc['2024-25', 'aste']} "
        f"(totale: da 225 a {n_aste}).\n")

    add("### Difetto 4 (MODERATO) — match puntuali sbagliati\n")
    add("Corretti dalle guardie generalizzabili (ruolo/squadra + multi-nome voti: lo stesso "
        "master non puo' arrivare da due nomi diversi nella stessa stagione di voti, vince "
        "il match migliore): Camara A. non e' piu' Camarda, Ferraris non e' Ferrari G., "
        "Berisha M. non e' il portiere Berisha, Terracciano F. (VER 2021/22) separato dal "
        "Terracciano FIO, Ekong non e' Troost-Ekong, Basso Ricci non e' Ricci S. "
        "Alias correttivi GE: `MARTINES JO.` -> Martinez Jo. (P), `JOA PEDRO` -> Joao Pedro; "
        "alias errato `DE VRIES`->De Vrij RIMOSSO (l'unica riga, asta 84 2021/22 ruolo C "
        "1 cr, non e' De Vrij che in quell'asta e' gia' comprato come D: resta unmatched, "
        "giocatore non identificabile).\n")

    add("### Difetto 5 (MODERATO) — acquisti doppi intra-asta e aste anomale\n")
    n_coll = int((aste.acquisti_doppi > 1).sum())
    righe_orig = int(aste.loc[aste.acquisti_doppi > 1, "acquisti_doppi"].sum())
    add(f"Prima: 637 righe di acquisti doppi (es. RONALDO 225+153+225 nella stessa asta) "
        f"gonfiavano n_obs e distorcevano mean/std. Dopo: una riga per (asta, master) col "
        f"primo prezzo ({righe_orig} righe originali collassate in {n_coll}, colonna "
        f"`acquisti_doppi`); {n_anom} aste con spesa pre-collasso > 1.10x il budget teorico "
        "flaggate `asta_anomala=1` ed ESCLUSE dai target.\n")

    add("### Difetto 6 (MODERATO) — eta' transfermarkt da omonimi\n")
    add("Guardia eta' in `match_tm`: candidato rifiutato se implica eta' < 14.5 o > 44 in "
        "una stagione a listone del master; con eta' minima < 16.5 il candidato deve avere "
        "presenze Serie A TM in una stagione a listone del master. Cosi' Bleve (classe "
        "1995) non prende la data del Daniele Bleve 2008 (eta' 14.2 -> rifiutato) e "
        "Cisse' (Moustapha 2003) non prende Alphadjo Cisse' 2006 (14.9, nessuna presenza "
        "2021/22 -> rifiutato), mentre i wonderkid VERI passano (Camarda 15.5 e Amey 15.1 "
        "hanno presenze TM nelle stagioni giuste e tengono la loro data di nascita). "
        "Guardia tm_player_id conteso: lo stesso giocatore TM non puo' dare l'eta' a due "
        "master; vince l'iniziale compatibile col nome TM, poi la similarita' del cognome "
        "(Arena A. vs Arena -> Antonio Arena; Chiesa vs Chiesa M. -> Federico; "
        "Musacchio vs Mustacchio; McTominay vs Scott; pari merito = eta' NaN per tutti, "
        "es. i due Ndiaye). Cintura di sicurezza in `build_players`: eta' fuori (15, 45) "
        "-> NaN.\n")

    add("### Difetti minori\n")
    add("- `wayback_p500_10sq == 0` (3 righe 2023/24) -> NaN: 0 non e' un prezzo.")
    add("- Bias `squadra_listone` (stato tardo-stagione) documentato in sez. 7.")
    add("- Claim 'zero match silenziosi' rimossa: i rifiuti delle guardie sono loggati "
        "in `unmatched_report.csv` (esito `rejected_*`).")

    (PROC / "FASE0B_REPORT.md").write_text("\n".join(L), encoding="utf-8")
    print("FASE0B_REPORT.md scritto,", len(L), "righe")


if __name__ == "__main__":
    main()
