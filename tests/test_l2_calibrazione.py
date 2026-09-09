"""Proiezione e SPSA: prove con risposta nota, prima del generatore.

I due difetti che chiudono, riprodotti sul codice precedente:

- `bersaglio_compatibile` riscalava e poi troncava a `[0, 1]` senza
  redistribuire, ma la diagnostica registrava la somma **richiesta** come se
  fosse quella ottenuta: `[0,9; 0,1]` con somma richiesta 2 usciva `[1,0; 0,2]`,
  cioè 1,2, dichiarato 2.
- `spsa` confrontava medie di perdite **perturbate**, con perturbazione
  decrescente e semi alternati, e si fermava dopo cinque incrementi sotto
  l'1 %. Su `L(θ) = 0,01·media((θ−1)²)` con 103 parametri, ottimo noto 0 e
  **nessun rumore**, si fermava a 6 iterazioni con `‖θ‖ = 0,0056`: l'arresto
  non misurava il progresso della soluzione.
"""
import sys
from pathlib import Path

import numpy as np
import pytest

RADICE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RADICE / "src"))

from fantabot.tabellino import calibrazione as cal            # noqa: E402


# --------------------------------------------------------------------------
# proiezione
# --------------------------------------------------------------------------

def test_il_caso_riprodotto_dall_audit():
    """`[0,9; 0,1]` verso somma 2: la vecchia trasformazione dava 1,2 e
    dichiarava 2."""
    v, d = cal.proietta_su_somma([0.9, 0.1], 2.0, modo="vincolo")
    assert d["somma_richiesta"] == 2.0
    assert d["somma_ottenuta"] == pytest.approx(sum(v))
    # con due valori e tetto 1,0 la somma 2 si raggiunge solo saturando entrambi
    assert d["somma_ottenuta"] == pytest.approx(2.0)
    assert v[0] == pytest.approx(1.0) and v[1] == pytest.approx(1.0)
    assert d["saturati"] == 2


def test_una_somma_irraggiungibile_viene_dichiarata_tale():
    """Con due valori il massimo è 2: chiederne 2,5 non si può, e la
    diagnostica deve dirlo invece di riportare il richiesto."""
    v, d = cal.proietta_su_somma([0.9, 0.1], 2.5, modo="vincolo")
    assert not d["raggiunta"]
    assert d["somma_ottenuta"] == pytest.approx(2.0)
    assert d["somma_ottenuta"] == pytest.approx(float(np.sum(v)))
    # il motivo dell'uscita dev'essere quello VERO: prima la nota diceva
    # sempre «tutti i valori liberi sono saturi», anche quando l'uscita era
    # per giri esauriti o per assenza di nuovi saturi
    assert d["motivo_uscita"] == "tutti i valori liberi sono saturi"
    assert "non raggiunta" in d["nota"]


def test_la_somma_richiesta_viene_rispettata_redistribuendo():
    """Il caso che conta: uno satura, e quello che perde va sugli altri."""
    v, d = cal.proietta_su_somma([0.95, 0.30, 0.10], 2.0, modo="vincolo")
    assert d["raggiunta"]
    assert float(np.sum(v)) == pytest.approx(2.0, abs=1e-9)
    assert v.max() <= 1.0 + 1e-12 and v.min() >= 0.0
    assert d["saturati"] >= 1


def test_la_diagnostica_non_dichiara_mai_il_richiesto_come_ottenuto():
    """Guardia sul difetto originale, su molti casi casuali."""
    rng = np.random.default_rng(0)
    for _ in range(200):
        n = int(rng.integers(2, 12))
        v0 = rng.random(n)
        s = float(rng.uniform(0.1, n * 1.3))
        v, d = cal.proietta_su_somma(v0, s, modo="vincolo")
        assert d["somma_ottenuta"] == pytest.approx(float(np.sum(v)), abs=1e-9)
        if d["raggiunta"]:
            assert d["somma_ottenuta"] == pytest.approx(s, abs=1e-6)


def test_il_modo_riferimento_tira_senza_imporre():
    """Una media storica è un riferimento statistico, non una legge fisica:
    con `peso` minore di 1 la somma si avvicina senza essere imposta."""
    v0 = [0.5, 0.3, 0.2]                       # somma 1,0
    v, d = cal.proietta_su_somma(v0, 2.0, modo="riferimento", peso=0.5)
    assert float(np.sum(v)) == pytest.approx(1.5, abs=1e-9)
    assert d["modo"] == "riferimento"
    # peso 0 non muove niente
    v2, _ = cal.proietta_su_somma(v0, 2.0, modo="riferimento", peso=0.0)
    assert np.allclose(v2, v0)


def test_le_proporzioni_relative_si_conservano_fra_i_non_saturi():
    """Con almeno un saturo: senza, il caso e' una sola moltiplicazione e la
    vecchia implementazione difettosa darebbe lo stesso risultato."""
    v, d = cal.proietta_su_somma([0.9, 0.2, 0.1], 1.5, modo="vincolo")
    assert d["saturati"] >= 1, (
        "senza saturi il test non distingue le due implementazioni")
    assert d["raggiunta"]
    assert float(np.sum(v)) == pytest.approx(1.5, abs=1e-9)
    assert v[1] / v[2] == pytest.approx(2.0, rel=1e-9)
    vecchia = np.clip(np.array([0.9, 0.2, 0.1]) * (1.5 / 1.2), 0.0, 1.0)
    assert abs(float(np.sum(vecchia)) - 1.5) > 1e-6, (
        "la vecchia implementazione qui darebbe la somma giusta: il test non "
        "sorveglia niente")


def test_lo_scarto_introdotto_e_registrato():
    v, d = cal.proietta_su_somma([0.9, 0.1], 1.2, modo="vincolo")
    assert d["scarto_l1"] == pytest.approx(float(np.sum(np.abs(v - np.array([0.9, 0.1])))))
    assert d["scarto_massimo"] > 0


# --------------------------------------------------------------------------
# SPSA: la prova con soluzione nota
# --------------------------------------------------------------------------

def quadratica(theta, seme=None):
    """`0,01 · media((θ − 1)²)`. Ottimo noto in θ = 1, valore 0. Nessun rumore:
    il seme è ignorato apposta."""
    return 0.01 * float(np.mean((np.asarray(theta, float) - 1.0) ** 2))


def test_i_guadagni_a_mano_non_muovono_la_soluzione():
    """Il difetto riprodotto: con `a` scelto a mano e una perdita che è una
    media su 103 parametri, il gradiente è dell'ordine di 1/p e il passo
    sparisce. Questo test **documenta** il comportamento sbagliato, così la
    correzione ha un termine di paragone."""
    r = cal.spsa(quadratica, 103, [1, 2], a=0.30, c=0.10, massimo=30,
                 monitoraggio=None, rng=np.random.default_rng(0))
    assert quadratica(r["theta"]) > 0.0099, (
        "con guadagni a mano la perdita deve restare quasi ferma: se si "
        "muovesse, questo test non descriverebbe piu' il difetto")


def test_il_guadagno_calibrato_e_il_budget_giusto_fanno_scendere_la_perdita():
    """La correzione, con il budget dimensionato sul problema.

    `a` viene da una stima del gradiente perché il primo passo valga quello che
    si vuole. Ma non basta: la fonte dice che le «direzioni sbagliate» di SPSA
    **si mediano nel corso di molte iterazioni**, e con 103 parametri il
    rapporto fra gradiente vero e stima per componente è circa `1/sqrt(p)`,
    cioè un decimo. Servono quindi centinaia di iterazioni, non trenta.

    Misurato con `A` coerente fra calibrazione e ricerca: 0,01 -> **0,000061**
    in 600 iterazioni, con `||theta||` a 9,98 contro l'ottimo
    `sqrt(103) = 10,15`."""
    g = cal.calibra_guadagno(quadratica, np.zeros(103), [1], c=0.10, passo_voluto=0.05,
                             massimo=600, rng=np.random.default_rng(1))
    assert g["a"] is not None and g["a"] > 0
    r = cal.spsa(quadratica, 103, [1, 2], a=g["a"], c=0.10, massimo=600,
                 monitoraggio=quadratica, ogni=30, pazienza=99,
                 rng=np.random.default_rng(0))
    finale = quadratica(r["theta"])
    assert finale < 0.0005, (
        f"perdita finale {finale:.6f}: il guadagno calibrato con budget "
        "adeguato deve portare sotto un ventesimo del valore iniziale 0,01")
    assert float(np.linalg.norm(r["theta"])) > 8.0


def test_trenta_iterazioni_non_bastano_nemmeno_col_guadagno_calibrato():
    """Il fatto che spiega il pilota fallito, e che sostituisce la diagnosi
    ritirata sul rumore: con 103 parametri il budget di 30 iterazioni e'
    insufficiente **anche senza nessun rumore Monte Carlo**.

    Il candidato dev'essere mosso da zero — altrimenti il test passerebbe anche
    con un ottimizzatore che non fa niente — e restare lontano dall'ottimo."""
    g = cal.calibra_guadagno(quadratica, np.zeros(103), [1], c=0.10,
                             passo_voluto=0.05, massimo=30,
                             rng=np.random.default_rng(1))
    r = cal.spsa(quadratica, 103, [1, 2], a=g["a"], c=0.10, massimo=30,
                 monitoraggio=quadratica, ogni=5, pazienza=99,
                 rng=np.random.default_rng(0))
    assert float(np.linalg.norm(r["theta"])) > 0.5, (
        "il candidato e' rimasto a zero: il test passerebbe anche con un "
        "ottimizzatore che non muove niente, e non direbbe nulla sul budget")
    assert quadratica(r["theta"]) > 0.004, (
        "con trenta iterazioni la perdita deve restare lontana dall'ottimo: "
        "se scendesse, il budget non sarebbe la spiegazione")


def test_un_passo_troppo_grande_fa_divergere():
    """La taratura del passo non e' un dettaglio: con `passo_voluto = 0,20` e
    `A` coerente, SPSA su questa funzione diverge e il candidato migliore resta
    il punto di partenza. E' il motivo per cui il pilota usa 0,05."""
    g = cal.calibra_guadagno(quadratica, np.zeros(103), [1], c=0.10,
                             passo_voluto=0.20, massimo=600,
                             rng=np.random.default_rng(1))
    r = cal.spsa(quadratica, 103, [1, 2], a=g["a"], c=0.10, massimo=600,
                 monitoraggio=quadratica, ogni=30, pazienza=99,
                 rng=np.random.default_rng(0))
    assert r["iterazione_migliore"] == 0
    assert float(np.linalg.norm(r["theta"])) == pytest.approx(0.0)


def test_il_primo_passo_vale_quello_dichiarato():
    """Il difetto: `calibra_guadagno` usava `A = 1` e `spsa` `A = massimo/10`,
    quindi il primo passo valeva 0,0486 invece di 0,20 — il rapporto
    `(21/2)^0,602 = 4,12`."""
    p = 30
    # un campione solo e lo stesso seme: cosi' la mediana del gradiente e' la
    # stessa estrazione che il primo passo usera', e il confronto e' esatto
    g = cal.calibra_guadagno(quadratica, np.zeros(p), [1], c=0.10,
                             passo_voluto=0.05, massimo=200, campioni=1,
                             rng=np.random.default_rng(1))
    assert g["A"] == cal.A_di(200)
    assert g["primo_passo_atteso"] == pytest.approx(0.05, rel=1e-9)
    r = cal.spsa(quadratica, p, [1], a=g["a"], c=0.10, massimo=200,
                 monitoraggio=None, rng=np.random.default_rng(1))
    passo = r["storia"][0]["norma_passo"] / np.sqrt(p)
    assert passo == pytest.approx(0.05, rel=1e-9), (
        f"primo passo per componente {passo:.6f} invece di 0,05")


def test_senza_A_ne_massimo_la_calibrazione_si_ferma():
    """Meglio fermarsi che tarare su un `A` diverso da quello della ricerca."""
    with pytest.raises(ValueError, match="massimo"):
        cal.calibra_guadagno(quadratica, np.zeros(5), [1], c=0.1,
                             passo_voluto=0.05)


def test_il_monitoraggio_valuta_il_theta_corrente_non_le_perturbazioni():
    """L'arresto vecchio confrontava medie di perdite perturbate; questo
    guarda `L(θ)` alla soluzione aggiornata."""
    visti = []

    def monitor(t):
        visti.append(np.asarray(t, float).copy())
        return quadratica(t)

    g = cal.calibra_guadagno(quadratica, np.zeros(20), [1], c=0.1,
                             passo_voluto=0.05, massimo=12,
                             rng=np.random.default_rng(2))
    r = cal.spsa(quadratica, 20, [1], a=g["a"], c=0.1, massimo=12,
                 monitoraggio=monitor, ogni=1, rng=np.random.default_rng(0))
    assert len(visti) >= 2
    # il primo monitoraggio e' a theta = 0
    assert np.allclose(visti[0], 0.0)
    assert any(r["storia"][k].get("L_monitoraggio") is not None
               for k in range(len(r["storia"])))


def test_viene_restituito_il_theta_migliore_non_l_ultimo():
    """Se il monitoraggio peggiora dopo un certo punto, il candidato non deve
    essere l'ultimo theta.

    Il monitoraggio e' puro e ha il minimo a meta' strada: sotto `||theta|| = 3`
    segue la quadratica, sopra viene penalizzato. Cosi' il migliore sta dentro
    la corsa e l'ultimo e' oltre."""
    # l'obiettivo tira theta verso 1, il monitoraggio ha il minimo in 0,5:
    # la corsa ci passa in mezzo, quindi il migliore sta DENTRO la corsa e
    # l'ultimo e' oltre. Entrambi puri e deterministici.
    def monitor(theta):
        return float(np.mean((np.asarray(theta, float) - 0.5) ** 2))

    g = cal.calibra_guadagno(quadratica, np.zeros(10), [1], c=0.1,
                             passo_voluto=0.05, massimo=60,
                             rng=np.random.default_rng(3))
    r = cal.spsa(quadratica, 10, [1], a=g["a"], c=0.1, massimo=60,
                 monitoraggio=monitor, ogni=1, pazienza=99,
                 rng=np.random.default_rng(0))
    serie = [x["L_monitoraggio"] for x in r["storia"] if "L_monitoraggio" in x]
    assert r["L_migliore"] == pytest.approx(min(serie))
    # la proprieta' che conta: il THETA restituito e' quello del migliore.
    # Senza queste due righe il test passa anche con `theta = ultimo`.
    assert monitor(r["theta"]) == pytest.approx(r["L_migliore"], rel=1e-9)
    assert r["iterazione_migliore"] < r["iterazioni"], (
        "il migliore coincide con l'ultimo: il test non distingue le due cose")
    assert monitor(r["theta"]) < monitor(r["theta_finale"]), (
        "il theta restituito non e' migliore dell'ultimo sul monitoraggio")
    assert not np.allclose(r["theta"], r["theta_finale"])


def test_senza_monitoraggio_non_c_e_arresto_anticipato():
    """Disattivare il monitoraggio deve costare tutto il budget, non fermarsi
    per una ragione che nessuno ha misurato."""
    r = cal.spsa(quadratica, 5, [1], a=0.1, c=0.1, massimo=7,
                 monitoraggio=None, rng=np.random.default_rng(0))
    assert r["iterazioni"] == 7
    assert "budget" in r["motivo_arresto"]


def test_la_storia_registra_passo_e_gradiente():
    """Senza queste due colonne non si distingue «il gradiente e' piccolo» da
    «il passo e' piccolo», che è esattamente l'ambiguità che ha portato a una
    diagnosi sbagliata sul rumore."""
    r = cal.spsa(quadratica, 8, [1], a=0.1, c=0.1, massimo=3,
                 monitoraggio=None, rng=np.random.default_rng(0))
    for riga in r["storia"]:
        assert "norma_gradiente" in riga and "norma_passo" in riga


# --------------------------------------------------------------------------
# il percorso C2: cutoff unico e guardie
# --------------------------------------------------------------------------

def _pilota():
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "l2_pilota_c2", RADICE / "scripts" / "l2_pilota_c2.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def _panel_finto():
    import pandas as pd
    righe = []
    for stag, base in (("2023-24", "2023-08-20"), ("2024-25", "2024-08-17")):
        for g in range(1, 6):
            data = pd.Timestamp(base) + pd.Timedelta(days=7 * (g - 1))
            for i in range(12):
                righe.append({
                    "master_id": i, "stagione": stag, "giornata": g,
                    "data": data, "squadra_alla_data": f"S{i % 2}",
                    "ruolo": "PDCA"[i % 4],
                    "stato_voto": "con_voto" if i % 3 else "nessuna_riga"})
    return pd.DataFrame(righe)


def test_le_somme_per_ruolo_guardano_solo_prima_del_cutoff():
    """Il difetto riprodotto: la funzione riceveva il panel intero ed escludeva
    solo la stagione valutata, quindi per il 2024-25 entravano 25.194 righe del
    2025-26, posteriori al cutoff."""
    import pandas as pd
    m = _pilota()
    P = _panel_finto()
    cutoff = pd.Timestamp("2024-08-17")
    base = m.somme_per_ruolo(P, cutoff)
    dopo = P.copy()
    posteriori = dopo["data"] >= cutoff
    assert posteriori.any()
    dopo.loc[posteriori, "stato_voto"] = "nessuna_riga"
    assert m.somme_per_ruolo(dopo, cutoff) == base, (
        "alterare righe posteriori al cutoff ha cambiato le somme per ruolo")
    prima = P.copy()
    anteriori = prima["data"] < cutoff
    prima.loc[anteriori, "stato_voto"] = "nessuna_riga"
    assert m.somme_per_ruolo(prima, cutoff) != base, (
        "alterare righe anteriori non cambia niente: la funzione non usa i "
        "dati che dice di usare")


def test_il_bersaglio_dichiara_la_somma_ottenuta_non_quella_chiesta():
    m = _pilota()
    b = {1: 0.9, 2: 0.1}
    fuori, diag = m.bersaglio_verso_somma(b, {1: "A", 2: "A"},
                                          {1: "X", 2: "X"}, {"A": 2.0},
                                          modo="vincolo")
    d = diag["X|A"]
    assert d["somma_ottenuta"] == pytest.approx(sum(fuori.values()))
    assert "saturati" in d and "scarto_l1" in d
