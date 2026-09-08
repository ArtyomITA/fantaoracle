"""La ricerca del Livello 3, verificata dove il massimo si puo' calcolare.

Su un'istanza abbastanza piccola tutte le rose legali si possono elencare e
valutare una per una. Se la ricerca non trova quel massimo, la ricerca e'
sbagliata: non e' il massimo a essere irraggiungibile.
"""
from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from fantabot.livello3 import ricerca as R      # noqa: E402
from fantabot.livello3 import valutatore as V   # noqa: E402
from fantabot.models import Player              # noqa: E402


@dataclass
class CuboFinto:
    giocatori: list
    fantavoto: np.ndarray
    voto: np.ndarray
    gioca: np.ndarray


QUOTE = {"P": 1, "D": 4, "C": 4, "A": 2}


def _mondo(seme=0, n_scenari=120, n_giornate=6):
    """Pool di 26 giocatori: 11 vanno all'avversario fisso, 15 restano a noi.

    Con 15 giocatori nel pool nostro le rose legali sono
    C(2,1) x C(5,4) x C(5,4) x C(3,2) = 150: elencabili tutte."""
    rng = np.random.default_rng(seme)
    pool, prezzi, valori = {}, {}, {}
    per_ruolo = {"P": 3, "D": 9, "C": 9, "A": 5}
    n = 1
    ids_ruolo = {r: [] for r in per_ruolo}
    for ruolo, quanti in per_ruolo.items():
        for _ in range(quanti):
            pid = n
            n += 1
            pool[pid] = Player(player_id=str(pid), name=f"G{pid}", role=ruolo,
                               team=f"T{pid % 5}")
            prezzi[pid] = float(rng.integers(1, 40))
            valori[pid] = float(rng.uniform(20, 120))
            ids_ruolo[ruolo].append(pid)
    # l'avversario prende i primi di ogni ruolo; a noi restano gli altri
    avversario = {r: ids_ruolo[r][:QUOTE[r]] for r in QUOTE}
    presi = {pid for r in avversario for pid in avversario[r]}
    nostro = {pid: p for pid, p in pool.items() if pid not in presi}
    # cubo: fantavoto costante per giocatore in ogni giornata, ma diverso per
    # scenario, cosi' la classifica non e' degenere
    tutti = sorted(pool)
    F = np.zeros((n_scenari, n_giornate, len(tutti)), dtype=np.float32)
    ix = {p: i for i, p in enumerate(tutti)}
    for pid in tutti:
        base = 4.0 + 4.0 * (valori[pid] - 20) / 100.0
        for s in range(n_scenari):
            F[s, :, ix[pid]] = base + rng.normal(0, 0.8)
    cubo = CuboFinto(tutti, F, F.copy(), np.ones(F.shape, dtype=bool))
    return pool, nostro, prezzi, valori, avversario, cubo


def test_enumerazione_trova_il_massimo_e_la_ricerca_locale_ci_arriva():
    """150 rose legali: si valutano tutte, poi si parte dalla peggiore e si
    verifica che gli scambi locali risalgano fino al massimo."""
    pool, nostro, prezzi, valori, avversario, cubo = _mondo(seme=1)
    regole = V.Regole(applica_bonus_porta_inviolata=False, quote=QUOTE, budget=400, usa_mod_difesa=False)
    scenari = list(range(100))
    cal = V.calendario_berger(2, 6, seme=0)
    tutte = R.enumera_esatto(nostro, prezzi, valori, cubo, regole, scenari,
                             avversari_fissi=[avversario], calendario=cal,
                             limite=1000)
    assert tutte["n"] == 150, tutte["n"]
    massimo = tutte["p1_massima"]
    peggiore = tutte["tutte"][-1]
    assert peggiore["p1"] < massimo, "istanza degenere: tutte le rose pari"

    fine = R.scambi_locali(peggiore["rosa"], nostro, prezzi, valori, cubo,
                           regole, scenari, seme_avversari=0, budget=400,
                           max_prove=200, calendario=cal,
                           avversari_fissi=[avversario])
    assert fine["p1"] >= peggiore["p1"]
    # la ricerca locale deve arrivare al massimo o dichiarare quanto le manca
    assert fine["p1"] >= massimo - 1e-9, (
        f"ricerca locale ferma a {fine['p1']:.4f}, massimo {massimo:.4f}, "
        f"scambi {fine['scambi']}")


def test_enumerazione_rispetta_il_budget():
    pool, nostro, prezzi, valori, avversario, cubo = _mondo(seme=2)
    # budget scelto dai dati: la rosa piu' economica possibile piu' 5 crediti
    minimo = sum(sum(sorted(max(1.0, prezzi[pid]) for pid in nostro
                            if nostro[pid].role == r)[:QUOTE[r]])
                 for r in QUOTE)
    tetto = minimo + 5
    regole = V.Regole(applica_bonus_porta_inviolata=False, quote=QUOTE, budget=tetto, usa_mod_difesa=False)
    rose = list(R.rose_legali(nostro, prezzi, regole))
    assert rose, f"nessuna rosa legale con budget {tetto} (minimo {minimo})"
    for rosa, costo in rose:
        assert costo <= tetto
        vera = sum(max(1.0, prezzi[pid]) for r in rosa for pid in rosa[r])
        assert abs(vera - costo) < 1e-9


def test_avversari_non_rubano_i_nostri_giocatori():
    """Gli avversari si costruiscono dal pool residuo: nessuna sovrapposizione."""
    pool, nostro, prezzi, valori, avversario, cubo = _mondo(seme=3)
    regole = V.Regole(applica_bonus_porta_inviolata=False, quote=QUOTE, budget=400, usa_mod_difesa=False)
    nostra = next(R.rose_legali(nostro, prezzi, regole))[0]
    presi = {pid for r in nostra for pid in nostra[r]}
    avv = [x["rosa"] for x in
           R.avversari_dal_pool(pool, prezzi, valori, regole, 1, presi, seme=0)]
    for a in avv:
        for r in a:
            assert not (set(a[r]) & presi), "un avversario ha un nostro giocatore"
    tutti = [pid for a in avv for r in a for pid in a[r]]
    assert len(tutti) == len(set(tutti)), "due avversari con lo stesso giocatore"
    # se il pool non basta, l'errore deve essere rumoroso
    with pytest.raises(ValueError, match="pool residuo non basta"):
        R.avversari_dal_pool(pool, prezzi, valori, regole, 5, presi, seme=0)


def test_avversari_fissi_rifiutano_le_collisioni():
    pool, nostro, prezzi, valori, avversario, cubo = _mondo(seme=4)
    regole = V.Regole(applica_bonus_porta_inviolata=False, quote=QUOTE, budget=400, usa_mod_difesa=False)
    nostra = next(R.rose_legali(nostro, prezzi, regole))[0]
    # avversario che contiene un nostro giocatore
    cattivo = {r: list(avversario[r]) for r in avversario}
    cattivo["A"] = [nostra["A"][0]] + cattivo["A"][1:]
    with pytest.raises(ValueError, match="sia nella nostra rosa"):
        R.valuta_candidata(nostra, nostro, prezzi, valori, cubo, regole,
                           list(range(5)), 0, avversari_fissi=[cattivo])


def test_p1_non_dipende_dall_ordine_delle_candidate():
    """Valutare le candidate in ordine diverso non cambia i loro numeri."""
    pool, nostro, prezzi, valori, avversario, cubo = _mondo(seme=5)
    regole = V.Regole(applica_bonus_porta_inviolata=False, quote=QUOTE, budget=400, usa_mod_difesa=False)
    cal = V.calendario_berger(2, 6, seme=0)
    rose = [r for r, _ in list(R.rose_legali(nostro, prezzi, regole))[:6]]
    p_avanti = [R.valuta_candidata(r, nostro, prezzi, valori, cubo, regole,
                                   list(range(10)), 0, calendario=cal,
                                   avversari_fissi=[avversario]).p_primo()["NOI"]
                for r in rose]
    p_indietro = [R.valuta_candidata(r, nostro, prezzi, valori, cubo, regole,
                                     list(range(10)), 0, calendario=cal,
                                     avversari_fissi=[avversario]).p_primo()["NOI"]
                  for r in reversed(rose)]
    assert np.allclose(p_avanti, list(reversed(p_indietro)))


def test_scenari_di_ricerca_e_di_verifica_sono_separati():
    """Il numero riportato viene da scenari mai usati per scegliere."""
    pool, nostro, prezzi, valori, avversario, cubo = _mondo(seme=6, n_scenari=60)
    regole = V.Regole(applica_bonus_porta_inviolata=False, quote=QUOTE, budget=400, usa_mod_difesa=False)
    cal = V.calendario_berger(2, 6, seme=0)
    candidate = [{"strategia": f"c{i}", "rosa": r}
                 for i, (r, _) in enumerate(
                     list(R.rose_legali(nostro, prezzi, regole))[:8])]
    ric, ver = list(range(30)), list(range(30, 60))
    out = R.scegli(candidate, nostro, prezzi, valori, cubo, regole, ric, ver,
                   calendario=cal, avversari_fissi=[avversario])
    assert out["migliore"] is not None
    assert out["verifica"]["n_scenari"] == 30
    # la ricerca sceglie il massimo: la verifica non deve essere identica
    assert set(ric).isdisjoint(ver)
    assert out["verifica"]["p1"] <= 1.0


def test_strategie_coprono_le_famiglie_richieste():
    nomi = [s.nome for s in R.strategie_predefinite(500)]
    assert any("due punte di prima fascia" in n for n in nomi)
    assert any("attacco leggero" in n for n in nomi)
    assert any("profondita'" in n for n in nomi)
    assert any("difesa da modificatore" in n for n in nomi)


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
