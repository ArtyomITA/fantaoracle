# -*- coding: utf-8 -*-
"""Fase 0b — libreria condivisa: normalizzazione nomi, registry, matcher.

Convenzioni per fonte:
- fantacalcio.it (registry/voti): 'Cognome [Ini.]'  es. 'Martinez L.', 'Ederson D.s.'
- wayback/fonti_prezzi:           'COGNOME Nome'    es. 'MARTINEZ Lautaro'
- gruppoesperti:                  'cognome [i]'     lowercase con refusi
- understat:                      'Nome Cognome'    con diacritici
- fanta.soccer:                   colonne Cognome / Nome (iniziale puntata)
- transfermarkt:                  'Nome Cognome' + data nascita
"""
import html
import re
import unicodedata
from collections import defaultdict
from pathlib import Path

import pandas as pd
from rapidfuzz import fuzz

RAW = Path(r"data\raw")
FONTI = Path(r"E:\claudecode pesante\fonti_prezzi")
PROC = Path(r"data\processed")
MATCH_DIR = PROC / "_match"

SEASONS = ["2020-21", "2021-22", "2022-23", "2023-24", "2024-25", "2025-26"]
PLAYERS_SEASONS = ["2021-22", "2023-24", "2024-25", "2025-26"]
VOTI_SEASONS = ["2021-22", "2022-23", "2023-24", "2024-25", "2025-26"]


def norm(s):
    """uppercase, NFKD senza accenti, punteggiatura -> spazio, spazi collassati."""
    if s is None or (isinstance(s, float) and pd.isna(s)):
        return ""
    s = html.unescape(str(s))
    s = unicodedata.normalize("NFKD", s)
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = s.upper()
    s = re.sub(r"[^A-Z0-9 ]+", " ", s)
    return re.sub(r"\s+", " ", s).strip()


# ---------------------------------------------------------------- alias table
# chiave: stringa normalizzata della fonte -> cognome normalizzato registry.
# Casi noti da INVENTORY sez. 3.4 + iterazioni sul matching (refusi GE,
# nomi d'arte, cognomi composti).
ALIAS = {
    # refusi GruppoEsperti
    "MIKITARIAN": "MKHITARYAN",
    "MIKHITARYAN": "MKHITARYAN",
    "MKHITARIAN": "MKHITARYAN",
    "SCZESNY": "SZCZESNY",
    "SCZCESNY": "SZCZESNY",
    "SZCSZESNY": "SZCZESNY",
    "SZCESNY": "SZCZESNY",
    "SAELEMAKERS": "SAELEMAEKERS",
    "SAELEMAKERS A": "SAELEMAEKERS",
    "SELEMAEKERS": "SAELEMAEKERS",
    "DEROON": "DE ROON",
    "DE CUNHA": "DA CUNHA",
    "DECUNHA": "DA CUNHA",
    "KVARA": "KVARATSKHELIA",
    "KVARATSKELIA": "KVARATSKHELIA",
    "CALHANOGLU": "CALHANOGLU",
    "CHALANOGLU": "CALHANOGLU",
    "CHALANOGLOU": "CALHANOGLU",
    "HANDANOVIC": "HANDANOVIC",
    "ANDANOVIC": "HANDANOVIC",
    "IBRAHIMOVIC": "IBRAHIMOVIC",
    "IBRAIMOVIC": "IBRAHIMOVIC",
    "ABRAHM": "ABRAHAM",
    "AURIER S": "AURIER",
    "OLA AINA": "AINA",
    "TAMEZE": "TAMEZE",
    "TAMEZE A": "TAMEZE",
    # nomi d'arte / diminutivi
    "DODO": "DODO",
    "TETE MORENTE": "MORENTE",
    "MORENTE TETE": "MORENTE",
    "KIKE PEREZ": "PEREZ",
    "THEO": "HERNANDEZ T",
    "THEO HERNANDEZ": "HERNANDEZ T",
    "DANY MOTA": "MOTA",
    "MOTA DANY": "MOTA",
    "NUNO": "TAVARES N",
    "NUNO TAVARES": "TAVARES N",
    "SJIMSITI": "DJIMSITI",
    "JIMSITI": "DJIMSITI",
    # refusi GE 2021-22 / 2024-25 (verificati contro il listone della stagione)
    "LAUTARO": "MARTINEZ L",
    "OSHIMEN": "OSIMHEN",
    "SCEZNY": "SZCZESNY",
    "SCORUSPY": "SKORUPSKI",
    "DRAGOWSY": "DRAGOWSKI",
    "REIAN": "REINA",
    "VHALOVIC": "VLAHOVIC",
    "KIAER": "KJAER",
    "NUITYNK": "NUYTINCK",
    "MAHELE": "MAEHLE",
    "HYAASY": "HYSAJ",
    "KARDSTROP": "KARSDORP",
    "GRISOUD": "GIROUD",
    "BEREZINSKY": "BERESZYNSKI",
    "SOTJA NOVIC": "STOJANOVIC",
    "DJIKS": "DIJKS",
    "ILICI": "ILICIC",
    "BADEIJ": "BADELJ",
    "ISMAYLI": "ISMAJLI",
    "BELARDINELLI": "BANDINELLI",
    # "DE VRIES" -> "DE VRIJ" RIMOSSO (fix round 1): l'unica riga GE 'DE VRIES' (asta 84
    # 2021-22, ruolo C, 1 cr) non e' De Vrij (D, gia' comprato nella stessa asta) ma un
    # giocatore non identificabile: meglio unmatched che un falso positivo.
    "EBUEY": "EBUEHI",
    "THURAN": "THURAM",
    "CALIK": "CELIK",
    # cognomi composti scritti attaccati / staccati
    "MILINKOVIC": "MILINKOVIC SAVIC",
    "VANDERBREMPT": "VAN DER BREMPT",
    "AKPA AKPRO": "AKPA AKPRO",
    "AKPAAKPRO": "AKPA AKPRO",
    "GOURNA": "GOURNA DOUATH",
    "KOLO MUANI": "KOLO MUANI",
    "KOLOMUANI": "KOLO MUANI",
    "LUIS MAXIMIANO": "MAXIMIANO",
    "MAXIMIANO LUIS": "MAXIMIANO",
    "L MAXIMIANO": "MAXIMIANO",
    "MILINKOVIC SAVIC": "MILINKOVIC SAVIC",
    "CHEDDIRA": "CHEDDIRA",
    # fix round 1 (audit Difetto 4): refusi GE su portieri/omonimi
    "MARTINES JO": "MARTINEZ JO",   # Josep Martinez (P), non Martins K. (C)
    "JOA PEDRO": "JOAO PEDRO",      # Joao Pedro (CAG), non Pedro (LAZ)
}


def apply_alias(s):
    return ALIAS.get(s, s)


def split_registry_name(raw):
    """'Martinez L.' -> ('MARTINEZ','L'); 'Ederson D.s.' -> ('EDERSON','D S');
    'Retegui' -> ('RETEGUI','')."""
    raw = html.unescape(str(raw)).strip()
    toks = raw.split()
    initial_toks = []
    while len(toks) > 1 and "." in toks[-1]:
        initial_toks.insert(0, toks[-1])
        toks = toks[:-1]
    return norm(" ".join(toks)), norm(" ".join(initial_toks))


def initial_compatible(src_ini, reg_ini):
    """le iniziali sono compatibili se una e' prefisso dell'altra (norm)."""
    if not src_ini or not reg_ini:
        return None  # non informativo
    a, b = src_ini.replace(" ", ""), reg_ini.replace(" ", "")
    return a.startswith(b) or b.startswith(a)


class SeasonIndex:
    """Indice di matching sui giocatori del listone fantacalcio.it di una stagione."""

    def __init__(self, reg_season: pd.DataFrame, stagione: str):
        self.stagione = stagione
        self.rows = []
        self.by_surname = defaultdict(list)
        self.by_full = defaultdict(list)
        self.by_token = defaultdict(list)
        for r in reg_season.itertuples(index=False):
            surname, initial = split_registry_name(r.nome)
            row = dict(master_id=int(r.master_id), nome=r.nome, squadra=r.squadra,
                       ruolo=r.ruolo, surname=surname, initial=initial,
                       full=(surname + " " + initial).strip(),
                       toks=frozenset(t for t in surname.split() if len(t) >= 3))
            self.rows.append(row)
            self.by_surname[surname].append(row)
            self.by_full[row["full"]].append(row)
            for t in row["toks"]:
                self.by_token[t].append(row)
        self.surnames = list(self.by_surname.keys())

    # ------------------------------------------------------------------
    def _filter(self, cands, role=None, sigla=None, src_ini=None):
        steps = []
        if role:
            f = [c for c in cands if c["ruolo"] == role]
            if f:
                cands = f
                steps.append("role")
        if sigla:
            f = [c for c in cands if c["squadra"] == sigla]
            if f:
                cands = f
                steps.append("team")
        if len(cands) > 1 and src_ini:
            f = [c for c in cands if initial_compatible(src_ini, c["initial"])]
            if f:
                cands = f
                steps.append("initial")
        if len(cands) > 1 and not src_ini:
            # fonte senza iniziale: il giocatore 'di default' e' quello senza suffisso
            f = [c for c in cands if not c["initial"]]
            if len(f) == 1:
                cands = f
                steps.append("bare_default")
        if len(cands) > 1 and src_ini:
            # iniziale non risolutiva: prova il candidato senza iniziale registry
            f = [c for c in cands if not c["initial"]]
            if len(f) == 1:
                cands = f
                steps.append("bare_fallback")
        return cands, steps

    # metodi "forti" = nome sorgente identico al registry (nessuna trasformazione)
    STRONG_METHODS = frozenset(["exact", "full_exact"])

    def _guard(self, cand, method, role=None, sigla=None):
        """Guardia anti-omonimo (fix round 1, audit Difetti 1/4).

        Ritorna None se il match e' accettabile, altrimenti la ragione del rifiuto.
        Regole:
        - P <-> giocatore di movimento: MAI accettato (qualsiasi metodo).
        - metodi forti (exact/full_exact): rifiuto se ruolo E squadra sono entrambi in
          conflitto, o se la squadra e' in conflitto senza conferma del ruolo (la sola
          squadra in conflitto con ruolo confermato e' legittima: trasferimenti estivi vs
          listone tardo-stagione, es. Vlahovic 2021-22 FIO a settembre / JUV a listone).
        - metodi deboli (alias/token_subset/fuzzy): qualsiasi conflitto di ruolo o
          squadra rifiuta il match.
        """
        role_given = bool(role)
        team_given = bool(sigla)
        role_ok = role_given and cand["ruolo"] == role
        team_ok = team_given and cand["squadra"] == sigla
        role_conflict = role_given and not role_ok
        team_conflict = team_given and not team_ok
        if role_given and (role == "P") != (cand["ruolo"] == "P"):
            return "conflitto_P"
        if method in self.STRONG_METHODS:
            if role_conflict and team_conflict:
                return "conflitto_ruolo+squadra"
            if team_conflict and not role_ok:
                return "conflitto_squadra"
        else:  # alias_full, alias_surname, token_subset, fuzzy
            if role_conflict:
                return "conflitto_ruolo"
            if team_conflict:
                return "conflitto_squadra"
        return None

    def match(self, surname, src_ini="", role=None, sigla=None, fuzzy_ok=True):
        """Ritorna dict(master_id, method, score, candidates[list of (full,squadra,ruolo,score)]).

        Fix round 1: matching a stadi (exact > full-key > alias > subset > fuzzy) con
        guardia ruolo/squadra; un match rifiutato per conflitto NON blocca gli stadi
        successivi (es. 'Martinez L.|FIO|D' salta Lautaro e arriva a Martinez Quarta
        via token_subset+role+team)."""
        raw_surname = surname
        aliased = apply_alias(surname)
        with_ini_raw = (raw_surname + " " + src_ini).strip()
        with_ini = apply_alias(with_ini_raw)

        stages = []  # (method, cands, score)
        # 1. alias sul cognome+iniziale (es. 'THEO' -> 'HERNANDEZ T', 'MARTINES JO')
        if with_ini != with_ini_raw and with_ini in self.by_full:
            stages.append(("alias_full", list(self.by_full[with_ini]), 100.0))
        # 2. cognome esatto (raw = forte; via alias = debole)
        if raw_surname in self.by_surname:
            stages.append(("exact", list(self.by_surname[raw_surname]), 100.0))
        elif aliased != raw_surname and aliased in self.by_surname:
            stages.append(("alias_surname", list(self.by_surname[aliased]), 100.0))
        # 3. chiave full (la stringa fonte contiene anche l'iniziale fusa: 'MARTINEZ JO')
        for key, meth in [((raw_surname + " " + src_ini).strip() if src_ini else raw_surname,
                           "full_exact"),
                          (raw_surname, "full_exact")]:
            if key in self.by_full:
                stages.append((meth, list(self.by_full[key]), 100.0))
                break
        if aliased != raw_surname:
            key = (aliased + " " + src_ini).strip() if src_ini else aliased
            if key in self.by_full:
                stages.append(("alias_full", list(self.by_full[key]), 100.0))
            elif aliased in self.by_full:
                stages.append(("alias_full", list(self.by_full[aliased]), 100.0))
        # 4. subset di token: 'ANGUISSA' in 'ZAMBO ANGUISSA', 'RAFAEL LEAO' vs 'LEAO'
        src_toks = frozenset(t for t in raw_surname.split() if len(t) >= 3)
        if src_toks:
            pool = {id(r): r for t in src_toks for r in self.by_token.get(t, [])}
            sub = [r for r in pool.values()
                   if src_toks <= r["toks"] or (r["toks"] and r["toks"] <= src_toks)]
            if sub:
                stages.append(("token_subset", sub, 100.0))
        # 5. fuzzy sul cognome (ultima spiaggia)
        fuzzy_top3 = []
        if fuzzy_ok and aliased:
            scored = []
            for s2 in self.surnames:
                sc = fuzz.ratio(aliased, s2)
                if sc >= 78:
                    scored.append((sc, s2))
            scored.sort(reverse=True)
            fuzzy_top3 = scored[:3]
            top = fuzzy_top3
            if top and top[0][0] >= 86 and (len(top) == 1 or top[0][0] - top[1][0] >= 3
                                            or top[1][1] == top[0][1]):
                stages.append(("fuzzy", list(self.by_surname[top[0][1]]), float(top[0][0])))

        rejected = []   # (method, cand, reason)
        seen_master_method = set()
        for method, cands, score in stages:
            filt, steps = self._filter(cands, role=role, sigla=sigla, src_ini=src_ini)
            if len(filt) == 1:
                cand = filt[0]
                key = (cand["master_id"], method)
                if key in seen_master_method:
                    continue
                seen_master_method.add(key)
                reason = self._guard(cand, method, role=role, sigla=sigla)
                if reason is None:
                    m = method + ("+" + "+".join(steps) if steps else "")
                    return dict(master_id=cand["master_id"], method=m, score=score,
                                candidates=[(cand["full"], cand["squadra"], cand["ruolo"], score)])
                rejected.append((method, cand, reason))
            elif len(filt) > 1:
                return dict(master_id=None, method="ambiguous", score=0.0,
                            candidates=[(c["full"], c["squadra"], c["ruolo"], score)
                                        for c in filt[:3]])
        if rejected:
            method, cand, reason = rejected[0]
            return dict(master_id=None, method=f"rejected_{method}:{reason}", score=0.0,
                        candidates=[(cand["full"], cand["squadra"], cand["ruolo"], 0.0)])
        cand3 = [self.by_surname[s2][0] for sc, s2 in fuzzy_top3 if s2 in self.by_surname]
        return dict(master_id=None, method="no_surname", score=0.0,
                    candidates=[(c["full"], c["squadra"], c["ruolo"],
                                 fuzz.ratio(aliased, c["surname"])) for c in cand3])


# ------------------------------------------------------- qualita' del match
# base: esatto > full-key > alias > subset > fuzzy; conferme: team (peso 2) + role (1).
METHOD_BASE_RANK = {"exact": 5, "full_exact": 4, "alias_full": 3, "alias_surname": 3,
                    "token_subset": 2, "fuzzy": 1}


def method_quality(method):
    """Qualita' ordinabile di un match: (conferme team*2+role, rank base, iniziale).

    Usata per scegliere la riga migliore quando piu' righe fonte puntano allo stesso
    master (fix round 1, audit Difetto 1: mai keep-first arbitrario)."""
    if not isinstance(method, str) or method.startswith(("rejected", "no_surname", "ambiguous")):
        return (-1, -1, -1)
    parts = method.replace("_norole", "").split("+")
    base, steps = parts[0], set(parts[1:])
    conf = 2 * ("team" in steps) + ("role" in steps)
    return (conf, METHOD_BASE_RANK.get(base, 0), int("initial" in steps))


def pick_best_per_master(df, master_col="master_id", method_col="method"):
    """Per ogni master con piu' righe: tieni la riga con method_quality migliore;
    a pari merito scarta tutte (ambiguo irrisolvibile). Ritorna (df_selezionato, n_tie_drop)."""
    df = df.copy()
    q = df[method_col].map(method_quality)
    df["_q"] = q
    keep, tie_drop = [], 0
    for mid, d in df.groupby(master_col, sort=False):
        if len(d) == 1:
            keep.append(d.index[0])
            continue
        d = d.sort_values("_q", ascending=False)
        qs = list(d["_q"])
        if qs[0] > qs[1]:
            keep.append(d.index[0])
        else:
            tie_drop += 1
    out = df.loc[keep].drop(columns=["_q"])
    return out, tie_drop


def load_registry():
    """registry lungo: master_id, stagione, nome, squadra, ruolo, qt_i, fvm."""
    frames = []
    for s in SEASONS:
        df = pd.read_csv(RAW / "quotazioni" / f"fantacalcioit_{s}.csv")
        out = pd.DataFrame({
            "master_id": df["player_id"].astype(int),
            "stagione": s,
            "nome": df["nome"].map(lambda x: html.unescape(str(x)).strip()),
            "squadra": df["squadra"],
            "ruolo": df["ruolo_classic"],
            "qt_i": pd.to_numeric(df["qt_i_classic"], errors="coerce"),
            "fvm": pd.to_numeric(df["fvm_classic"], errors="coerce"),
        })
        frames.append(out)
    return pd.concat(frames, ignore_index=True)


def season_indexes(reg):
    return {s: SeasonIndex(reg[reg.stagione == s], s) for s in reg.stagione.unique()}


class UnmatchedLog:
    def __init__(self):
        self.rows = []

    def add(self, fonte, stagione, chiave_raw, contesto, esito, candidates):
        c = list(candidates)[:3] + [("", "", "", "")] * 3
        row = dict(fonte=fonte, stagione=stagione, chiave_raw=chiave_raw,
                   contesto=contesto, esito=esito)
        for i in range(3):
            full, sq, ru, sc = c[i]
            row[f"cand{i+1}"] = f"{full} ({sq} {ru}) [{sc}]" if full else ""
        self.rows.append(row)

    def to_df(self):
        return pd.DataFrame(self.rows)


def parse_wayback_name(raw):
    """'MARTINEZ Lautaro' -> ('MARTINEZ','L'); 'ESTEVES GONCALO DO LAGO PONTES' -> tutto cognome."""
    raw = html.unescape(str(raw)).strip()
    toks = raw.split()
    up = [t for t in toks if t == t.upper() and any(ch.isalpha() for ch in t)]
    # prefisso di token tutti-maiuscoli = cognome
    surn = []
    given = []
    for t in toks:
        if t == t.upper() and not given:
            surn.append(t)
        else:
            given.append(t)
    if not surn:  # tutto minuscolo/misto: primo token cognome
        surn, given = toks[:1], toks[1:]
    ini = norm(given[0])[:1] if given else ""
    return norm(" ".join(surn)), ini


def parse_ge_name(raw):
    """'thuram m' / 'vasquez d.' -> ('THURAM','M'); 'milinkovic savic' -> composto."""
    s = norm(raw)
    toks = s.split()
    ini = ""
    while len(toks) > 1 and len(toks[-1]) == 1:
        ini = toks[-1] + (" " + ini if ini else "")
        toks = toks[:-1]
    return " ".join(toks), ini.strip()


def match_given_surname(idx: SeasonIndex, given_first: str, surname_tokens, role=None,
                        sigla=None):
    """Per formati 'Nome Cognome' (understat/transfermarkt): prova cognome = ultimi k token,
    k=1..3, con iniziale = prima lettera del nome."""
    ini = norm(given_first)[:1] if given_first else ""
    toks = [t for t in surname_tokens if t]
    best = None
    for k in (1, 2, 3):
        if k > len(toks):
            break
        surname = " ".join(toks[-k:])
        r = idx.match(surname, src_ini=ini, role=role, sigla=sigla, fuzzy_ok=(k == 1))
        if r["master_id"] is not None:
            return r
        if best is None or r["method"] != "no_surname":
            best = r
    # ultimo tentativo: tutto il nome come cognome (nomi d'arte tipo 'Dodo')
    full = " ".join(([norm(given_first)] if given_first else []) + toks)
    r = idx.match(full, src_ini="", role=role, sigla=sigla, fuzzy_ok=True)
    if r["master_id"] is not None:
        return r
    return best or r


def derive_team_map(source_pairs, idx: SeasonIndex, min_count=3):
    """source_pairs: iterable di (squadra_fonte, surname_norm, initial). Deriva
    mapping squadra_fonte -> sigla contando i match nome-unici."""
    counts = defaultdict(lambda: defaultdict(int))
    for team_src, surname, ini in source_pairs:
        r = idx.match(surname, src_ini=ini, fuzzy_ok=False)
        if r["master_id"] is not None:
            sigla = r["candidates"][0][1]
            counts[team_src][sigla] += 1
    out = {}
    for team_src, d in counts.items():
        sigla, n = max(d.items(), key=lambda kv: kv[1])
        if n >= min_count:
            out[team_src] = sigla
    return out
