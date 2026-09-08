"""La formazione non deve dipendere da cosa succedera' quel turno.

Regola: a parita' di informazione gia' nota (le giornate precedenti), cambiare
gli esiti della giornata corrente non deve cambiare gli undici scelti prima
che la giornata si giochi. Le sostituzioni automatiche restano fuori: quelle
avvengono a consuntivo e possono usare i voti realizzati, come nel regolamento.

Il test permuta gli esiti della giornata (chi prende voto e quanto) tenendo
identico tutto il passato, e chiede che la formazione resti la stessa.
"""
from __future__ import annotations

import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from fantabot.season.detail import season_detail  # noqa: E402
from fantabot.season.simulate import simulate_season  # noqa: E402


def _rose(n_squadre=4, per_ruolo=None):
    per_ruolo = per_ruolo or {"P": 3, "D": 8, "C": 8, "A": 6}
    rose, k = {}, 0
    for t in range(n_squadre):
        r = {}
        for ruolo, q in per_ruolo.items():
            r[ruolo] = [f"{ruolo}{k + i}" for i in range(q)]
            k += q
        rose[f"T{t}"] = r
    return rose


def _giornate(rose, n_giornate, seed, esiti_ultima_diversi=False):
    """Voti per giornata. Con `esiti_ultima_diversi` cambia SOLO l'ultima
    giornata: il passato resta identico bit per bit."""
    rng = random.Random(seed)
    tutti = [pid for r in rose.values() for ids in r.values() for pid in ids]
    fuori = []
    for g in range(n_giornate):
        if g == n_giornate - 1 and esiti_ultima_diversi:
            r2 = random.Random(seed + 999)
            gioca = [p for p in tutti if r2.random() < 0.75]
            fuori.append({p: round(3 + 5 * r2.random(), 1) for p in gioca})
        else:
            gioca = [p for p in tutti if rng.random() < 0.75]
            fuori.append({p: round(3 + 5 * rng.random(), 1) for p in gioca})
    return fuori


def _formazioni_ultima(detail):
    """Undici SCELTI da ogni squadra nell'ultima giornata, prima dei cambi.

    Nel dettaglio ogni riga e' 'tit' (titolare che ha giocato), 'assente'
    (titolare senza voto e non sostituito) o 'sub' (chi e' entrato, col nome
    del titolare che sostituisce nel campo 'per'). I titolari scelti sono
    quindi i 'tit', gli 'assente' e i sostituiti."""
    out = {}
    for sq, det in detail["giornate"][-1]["squadre"].items():
        scelti = set()
        for r in det["formazione"]:
            if r["stato"] in ("tit", "assente"):
                scelti.add(r["pid"])
            elif r["stato"] == "sub":
                scelti.add(r["per"])       # qui 'per' e' il nome del sostituito
        out[sq] = tuple(sorted(scelti))
    return out


def test_detail_non_guarda_la_giornata_corrente():
    rose = _rose()
    a = _giornate(rose, 6, seed=1, esiti_ultima_diversi=False)
    b = _giornate(rose, 6, seed=1, esiti_ultima_diversi=True)
    assert a[:-1] == b[:-1], "il passato deve essere identico"
    assert a[-1] != b[-1], "l'ultima giornata deve differire"
    nomi = {pid: pid for r in rose.values() for ids in r.values() for pid in ids}
    fa = _formazioni_ultima(season_detail(rose, a, nomi, cal_seed=3))
    fb = _formazioni_ultima(season_detail(rose, b, nomi, cal_seed=3))
    assert fa == fb, ("season_detail cambia la formazione quando cambiano gli "
                      "esiti della giornata: sta guardando avanti")


def _available_visti(modulo, fn, rose, giornate, **kw):
    """Registra l'insieme `available` che il modulo passa a pick_lineup, una
    voce per giornata (la prima squadra basta: e' lo stesso per tutte)."""
    visti = []
    originale = modulo.pick_lineup

    def spia(roster, form, form_voto=None, use_mod=False, available=None):
        if len(visti) < len(giornate) * len(rose):
            visti.append(None if available is None else set(available))
        return originale(roster, form, form_voto, use_mod, available)

    modulo.pick_lineup = spia
    try:
        fn(rose, giornate, **kw)
    finally:
        modulo.pick_lineup = originale
    # una riga per giornata: prendo la prima squadra di ogni giornata
    return visti[::len(rose)]


def test_simulate_non_guarda_la_giornata_corrente():
    """Contratto: alla prima giornata nessuna informazione (None), dalla
    seconda in poi solo chi ha giocato la giornata precedente."""
    from fantabot.season import simulate as mod
    rose = _rose()
    giornate = _giornate(rose, 4, seed=5)
    visti = _available_visti(mod, lambda r, g, **k: simulate_season(r, g, **k),
                             rose, giornate, n_calendars=1, seed=2)
    assert visti[0] is None, ("alla prima giornata simulate_season passa un "
                              f"insieme invece di nessuna informazione: {visti[0]}")
    for g in range(1, len(giornate)):
        atteso = set(giornate[g - 1])
        assert visti[g] == atteso, (f"giornata {g + 1}: simulate_season non usa "
                                    "la giornata precedente")


def test_detail_usa_solo_il_passato():
    """Stesso contratto per il dettaglio mostrato dopo la Sedia."""
    from fantabot.season import detail as mod
    rose = _rose()
    giornate = _giornate(rose, 4, seed=7)
    nomi = {pid: pid for r in rose.values() for ids in r.values() for pid in ids}
    visti = _available_visti(
        mod, lambda r, g, **k: season_detail(r, g, nomi, **k), rose, giornate,
        cal_seed=3)
    assert visti[0] is None, f"season_detail guarda la prima giornata: {visti[0]}"
    for g in range(1, len(giornate)):
        assert visti[g] == set(giornate[g - 1]), \
            f"giornata {g + 1}: season_detail non usa la giornata precedente"


if __name__ == "__main__":
    import traceback
    esiti = []
    for nome, fn in list(globals().items()):
        if nome.startswith("test_") and callable(fn):
            try:
                fn()
                esiti.append((nome, "PASSA", ""))
            except AssertionError as e:
                esiti.append((nome, "FALLISCE", str(e)[:160]))
            except Exception:
                esiti.append((nome, "ERRORE", traceback.format_exc(limit=2)[-200:]))
    for n, s, m in esiti:
        print(f"{s:9s} {n}")
        if m:
            print(f"          {m}")
