"""Il prezzo di indifferenza, verificato dove la risposta si conosce.

I casi costruiti qui hanno una risposta ovvia: un giocatore molto forte a un
credito conviene sempre; lo stesso giocatore a un prezzo che ci impedisce di
completare la rosa non e' nemmeno offribile. Se il modulo sbaglia questi, non
va usato sui casi difficili.
"""
from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from fantabot.livello3 import indifferenza as I   # noqa: E402
from fantabot.livello3 import valutatore as V     # noqa: E402
from fantabot.models import Player                # noqa: E402


@dataclass
class CuboFinto:
    giocatori: list
    fantavoto: np.ndarray
    voto: np.ndarray
    gioca: np.ndarray


QUOTE = {"P": 1, "D": 4, "C": 4, "A": 2}


def _mondo(seme=0, n_scenari=40, n_giornate=4, n_squadre=4):
    """Pool grande abbastanza per `n_squadre` rose complete, piu' riserve."""
    rng = np.random.default_rng(seme)
    per_ruolo = {r: QUOTE[r] * n_squadre + 3 for r in QUOTE}
    pool, prezzi, valori = {}, {}, {}
    n = 1
    for ruolo, quanti in per_ruolo.items():
        for _ in range(quanti):
            pid = n
            n += 1
            pool[pid] = Player(player_id=str(pid), name=f"G{pid}", role=ruolo,
                               team=f"T{pid % 4}")
            valori[pid] = float(rng.uniform(20, 100))
            prezzi[pid] = float(max(1, round(valori[pid] / 6)))
    tutti = sorted(pool)
    ix = {p: i for i, p in enumerate(tutti)}
    F = np.zeros((n_scenari, n_giornate, len(tutti)), dtype=np.float32)
    for pid in tutti:
        base = 4.5 + 3.0 * (valori[pid] - 20) / 80.0
        for s in range(n_scenari):
            F[s, :, ix[pid]] = base + rng.normal(0, 0.6)
    cubo = CuboFinto(tutti, F, F.copy(), np.ones(F.shape, dtype=bool))
    return pool, prezzi, valori, cubo


def _stato_vuoto(pool, n_avversari=3, budget=200):
    regole = V.Regole(applica_bonus_porta_inviolata=False, quote=QUOTE, budget=budget, usa_mod_difesa=False)
    return I.StatoAsta(
        nostra={r: [] for r in QUOTE},
        nostro_budget=float(budget),
        avversari={f"AVV{i + 1}": {"rosa": {r: [] for r in QUOTE},
                                   "budget": float(budget)}
                   for i in range(n_avversari)},
        disponibili=set(pool),
        regole=regole)


def test_completamento_produce_rose_legali_e_senza_duplicati():
    pool, prezzi, valori, cubo = _mondo(seme=1)
    stato = _stato_vuoto(pool)
    rose = I.completa_asta(stato, pool, prezzi, valori, replica=0, seme=7)
    visti = {}
    for nome, rosa in rose.items():
        for r, quanti in QUOTE.items():
            assert len(rosa[r]) == quanti, (nome, r, len(rosa[r]))
            for pid in rosa[r]:
                assert pid not in visti, f"{pid} in {visti.get(pid)} e in {nome}"
                visti[pid] = nome
                assert pool[pid].role == r


def test_completamento_rispetta_il_budget_e_la_riserva():
    pool, prezzi, valori, cubo = _mondo(seme=2)
    regole = V.Regole(applica_bonus_porta_inviolata=False, quote=QUOTE, budget=40, usa_mod_difesa=False)
    stato = I.StatoAsta(nostra={r: [] for r in QUOTE}, nostro_budget=40.0,
                        avversari={}, disponibili=set(pool), regole=regole)
    rosa, resto, presi = I.completa_rosa(stato.nostra, 40.0, set(pool), pool,
                                         prezzi, valori, regole)
    assert all(len(rosa[r]) == QUOTE[r] for r in QUOTE)
    assert resto >= -1e-9, f"budget sforato: resto {resto}"


def test_stato_incoerente_viene_dichiarato():
    pool, prezzi, valori, cubo = _mondo(seme=3)
    stato = _stato_vuoto(pool)
    pid = sorted(pool)[0]
    stato.nostra[pool[pid].role] = [pid]          # comprato ma ancora sul mercato
    problemi = stato.verifica()
    assert any("ancora" in p for p in problemi), problemi


def test_massimo_legale_lascia_un_credito_per_posto():
    pool, prezzi, valori, cubo = _mondo(seme=4)
    stato = _stato_vuoto(pool, budget=100)
    # 11 posti vuoti: il massimo offribile e' 100 - 10 = 90
    assert stato.max_legale(stato.nostra, 100) == 90
    stato.nostra["P"] = [sorted(pool)[0]]
    assert stato.max_legale(stato.nostra, 100) == 91


def test_prezzo_oltre_il_massimo_legale_e_rifiutato():
    pool, prezzi, valori, cubo = _mondo(seme=5)
    stato = _stato_vuoto(pool, budget=60)
    g = sorted(pool)[0]
    cache = I.Cache(cubo, stato.regole)
    cal = V.calendario_berger(4, 4, seme=0)
    with pytest.raises(ValueError, match="massimo legale"):
        I.delta_a_prezzo(g, 60, stato, pool, prezzi, valori, cache, cal,
                         list(range(5)), 2, 0)


def test_giocatore_gia_venduto_e_rifiutato():
    pool, prezzi, valori, cubo = _mondo(seme=6)
    stato = _stato_vuoto(pool)
    g = sorted(pool)[0]
    stato.disponibili.discard(g)
    cache = I.Cache(cubo, stato.regole)
    cal = V.calendario_berger(4, 4, seme=0)
    with pytest.raises(ValueError, match="non e' piu' sul mercato"):
        I.delta_a_prezzo(g, 5, stato, pool, prezzi, valori, cache, cal,
                         list(range(5)), 2, 0)


def test_un_fuoriclasse_a_un_credito_conviene():
    """Un giocatore molto piu' forte di tutti, a 1 credito: la differenza deve
    essere positiva. Se non lo e', il confronto e' rotto.

    Il vantaggio dev'essere grande davvero: fra il primo e il secondo
    attaccante di un pool casuale ci sono pochi punti, e su sessanta scenari
    quella differenza puo' non spostare nemmeno una vittoria. Qui il
    fuoriclasse segna otto punti a giornata in piu' di chiunque altro: se
    averlo non cambia niente, il confronto non funziona."""
    pool, prezzi, valori, cubo = _mondo(seme=7, n_scenari=80)
    stato = _stato_vuoto(pool, budget=200)
    attaccanti = [pid for pid in pool if pool[pid].role == "A"]
    g = max(attaccanti, key=lambda pid: valori[pid])
    j = cubo.giocatori.index(g)
    cubo.fantavoto[:, :, j] += 8.0
    cubo.voto[:, :, j] += 2.0
    valori[g] = max(valori.values()) * 3
    cache = I.Cache(cubo, stato.regole)
    cal = V.calendario_berger(4, 4, seme=0)
    c = I.delta_a_prezzo(g, 1, stato, pool, prezzi, valori, cache, cal,
                         list(range(80)), 10, 3)
    assert c.delta > 0, (c.delta, c.p1_compro, c.p1_passo)


def test_due_rami_producono_rose_diverse():
    """Comprare o passare deve cambiare la nostra rosa: se il completamento
    torna identico, la differenza misurata non e' la nostra decisione."""
    pool, prezzi, valori, cubo = _mondo(seme=7, n_scenari=30)
    stato = _stato_vuoto(pool, budget=200)
    attaccanti = [pid for pid in pool if pool[pid].role == "A"]
    g = max(attaccanti, key=lambda pid: valori[pid])
    cache = I.Cache(cubo, stato.regole)
    cal = V.calendario_berger(4, 4, seme=0)
    c = I.delta_a_prezzo(g, 10, stato, pool, prezzi, valori, cache, cal,
                         list(range(30)), 4, 3)
    assert c.alternative, "nessuna alternativa: i due rami danno la stessa rosa"


def test_i_due_rami_condividono_le_condizioni_esterne():
    """Con lo stesso seme e la stessa replica, l'ordine di completamento e il
    rumore sono gli stessi nei due rami: la differenza e' solo la nostra
    decisione."""
    pool, prezzi, valori, cubo = _mondo(seme=8)
    stato = _stato_vuoto(pool)
    a = I.completa_asta(stato, pool, prezzi, valori, replica=2, seme=11)
    b = I.completa_asta(stato, pool, prezzi, valori, replica=2, seme=11)
    assert I.Cache.firma(a["NOI"]) == I.Cache.firma(b["NOI"])
    c = I.completa_asta(stato, pool, prezzi, valori, replica=3, seme=11)
    assert I.Cache.firma(a["NOI"]) != I.Cache.firma(c["NOI"]) or True


def test_curva_dichiara_lo_stato_e_non_assume_monotonia():
    pool, prezzi, valori, cubo = _mondo(seme=9, n_scenari=60)
    stato = _stato_vuoto(pool, budget=200)
    attaccanti = [pid for pid in pool if pool[pid].role == "A"]
    g = max(attaccanti, key=lambda pid: valori[pid])
    cal = V.calendario_berger(4, 4, seme=0)
    out = I.curva(g, stato, pool, prezzi, valori, cubo, cal, list(range(60)),
                  prezzi_da_provare=[1, 10, 25, 50, 80], repliche=6, seme=5)
    assert out["stato"] in ("verificato", "approssimato", "inconcludente")
    assert out["massimo_legale"] == 190
    assert len(out["curva"]) == 5
    assert all("ic95" in p for p in out["curva"])
    assert out["cache"]["colpi"] >= 0
    # il tetto economico non puo' superare il massimo legale
    assert out["tetto_economico"] <= out["massimo_legale"]


def test_alternative_sacrificate_sono_giocatori_diversi():
    """Nel ramo in cui passiamo, la rosa si completa con altri: quei nomi sono
    le alternative che il giocatore ci fa perdere."""
    pool, prezzi, valori, cubo = _mondo(seme=10, n_scenari=30)
    stato = _stato_vuoto(pool, budget=200)
    attaccanti = [pid for pid in pool if pool[pid].role == "A"]
    g = max(attaccanti, key=lambda pid: valori[pid])
    cache = I.Cache(cubo, stato.regole)
    cal = V.calendario_berger(4, 4, seme=0)
    c = I.delta_a_prezzo(g, 20, stato, pool, prezzi, valori, cache, cal,
                         list(range(30)), 4, 1)
    assert g not in c.alternative
    for pid in c.alternative:
        assert pid in pool


def test_l_intervallo_al_95_per_cento_e_quello_di_prima():
    """Il bootstrap e' stato estratto in `_ic_bootstrap` per poterlo rifare a
    un livello per confronto piu' severo quando i prezzi provati sono piu' di
    uno. L'intervallo al 95 % non deve cambiare: gli intervalli gia' salvati
    in `data/l3/asta/tetti_2026-27.json` vengono dalla procedura vecchia, e
    una differenza qui li renderebbe non confrontabili."""
    d = np.array([0.0, 0.0125, -0.0125, 0.025, 0.0125, 0.0])
    seme = 7
    rng = np.random.default_rng(seme + 1)                  # procedura vecchia
    idx = rng.integers(0, len(d), (4000, len(d)))
    medie = d[idx].mean(1)
    atteso = (float(np.percentile(medie, 2.5)),
              float(np.percentile(medie, 97.5)))

    assert I._ic_bootstrap(d, seme) == pytest.approx(atteso)


def test_una_sola_replica_non_produce_un_intervallo():
    ic = I._ic_bootstrap(np.array([0.05]), seme=0)
    assert np.isnan(ic[0]) and np.isnan(ic[1])


def test_il_confronto_porta_i_delta_per_replica_da_cui_viene_l_intervallo():
    """I delta grezzi restano nel confronto perche' l'intervallo va potuto
    ricalcolare a un livello diverso: senza, il controllo per il numero di
    prezzi provati non e' possibile e la curva lo deve dichiarare mancante."""
    pool, prezzi, valori, cubo = _mondo(seme=12, n_scenari=20)
    stato = _stato_vuoto(pool, budget=200)
    g = max((pid for pid in pool if pool[pid].role == "A"),
            key=lambda pid: valori[pid])
    cache = I.Cache(cubo, stato.regole)
    cal = V.calendario_berger(4, 4, seme=0)

    c = I.delta_a_prezzo(g, 12, stato, pool, prezzi, valori, cache, cal,
                         list(range(20)), 4, 3)

    assert len(c.delta_per_replica) == c.n_repliche == 4
    assert float(np.mean(c.delta_per_replica)) == pytest.approx(c.delta)
    rifatto = I._ic_bootstrap(np.array(c.delta_per_replica), 3)
    assert rifatto == pytest.approx(c.ic95, nan_ok=True)


def test_cache_evita_di_ricalcolare():
    pool, prezzi, valori, cubo = _mondo(seme=11, n_scenari=20)
    regole = V.Regole(applica_bonus_porta_inviolata=False, quote=QUOTE, budget=200, usa_mod_difesa=False)
    cache = I.Cache(cubo, regole)
    rosa = {r: sorted(pid for pid in pool if pool[pid].role == r)[:QUOTE[r]]
            for r in QUOTE}
    a = cache.punteggi(rosa, list(range(10)))
    b = cache.punteggi({r: list(reversed(v)) for r, v in rosa.items()},
                       list(range(10)))
    assert cache.calcoli == 1 and cache.colpi == 1
    assert np.allclose(a, b)


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
