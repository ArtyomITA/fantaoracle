"""Registra acquisti nel Copilota in corso da riga di comando (o da uno screenshot letto).

Serve quando chi e' al tavolo detta o manda una foto della schermata dell'asta e
qualcun altro (o un assistente) inserisce i martelletti: il Copilota espone
un'API HTTP locale e la pagina si aggiorna da sola entro due secondi.

Uso:
    python scripts/asta_registra.py "Malen > Marco : 205" "Calo > Io : 12"
    python scripts/asta_registra.py --undo
    python scripts/asta_registra.py --escludi "Colombo"      # o --riammetti
    python scripts/asta_registra.py --stato
    python scripts/asta_registra.py --elenco                 # acquisti con l'indice
    python scripts/asta_registra.py --modifica "42 > Nightmare : 12"
    python scripts/asta_registra.py --rimuovi 42
    opzioni: --porta 8770 (predefinita), --secco (risolve i nomi senza registrare)

`--modifica` corregge UN acquisto qualsiasi, non solo l'ultimo: «indice >
squadra : prezzo», e le due parti dopo l'indice sono facoltative («42 >
Nightmare» sposta e basta, «42 : 12» cambia solo la cifra). L'indice e' quello
che stampa `--elenco`. Prima si annullava fino al lotto sbagliato e si
ribatteva tutto: il 10/9 sono costati 81 annullamenti e 82 martelletti.

Ogni voce e' «giocatore > squadra : prezzo». Il giocatore si cerca senza
accenti e per prefisso; se la ricerca e' ambigua la voce NON viene registrata
e vengono stampati i candidati. La squadra si cerca fra i nomi dati al setup
(prefisso, senza maiuscole). Ogni martelletto porta un `richiesta_id`, quindi
rilanciare due volte lo stesso comando non registra due acquisti.
"""
from __future__ import annotations

import json
import re
import sys
import time
import unicodedata
import urllib.parse
import urllib.request

sys.stdout.reconfigure(encoding="utf-8")


def piatto(s: str) -> str:
    return "".join(ch for ch in unicodedata.normalize("NFKD", str(s).lower())
                   if not unicodedata.combining(ch)).strip()


class Copilota:
    def __init__(self, porta: int):
        self.base = f"http://127.0.0.1:{porta}"

    def get(self, path: str, **q):
        url = self.base + path + ("?" + urllib.parse.urlencode(q) if q else "")
        with urllib.request.urlopen(url, timeout=20) as r:
            return json.loads(r.read().decode("utf-8"))

    def post(self, path: str, body: dict):
        req = urllib.request.Request(self.base + path, data=json.dumps(body).encode(),
                                     headers={"Content-Type": "application/json"}, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=20) as r:
                return json.loads(r.read().decode("utf-8")), r.status
        except urllib.error.HTTPError as e:
            return json.loads(e.read().decode("utf-8")), e.code

    def squadre(self) -> list[str]:
        return self.get("/copilot/state")["names"]

    def cerca(self, nome: str) -> list[dict]:
        return self.get("/copilot/players", q=piatto(nome), tutti=1)


def risolvi_giocatore(cop: Copilota, nome: str):
    """Un solo candidato, altrimenti None e la lista."""
    righe = cop.cerca(nome)
    if not righe:
        return None, []
    esatti = [r for r in righe if piatto(r["nome"]) == piatto(nome)]
    if len(esatti) == 1:
        return esatti[0], righe
    prefissi = [r for r in righe if piatto(r["nome"]).startswith(piatto(nome))]
    if len(prefissi) == 1:
        return prefissi[0], righe
    if len(righe) == 1:
        return righe[0], righe
    return None, righe


def risolvi_squadra(nomi: list[str], testo: str):
    t = piatto(testo)
    esatti = [i for i, n in enumerate(nomi) if piatto(n) == t]
    if len(esatti) == 1:
        return esatti[0]
    pref = [i for i, n in enumerate(nomi) if piatto(n).startswith(t)]
    if len(pref) == 1:
        return pref[0]
    dentro = [i for i, n in enumerate(nomi) if t in piatto(n)]
    if len(dentro) == 1:
        return dentro[0]
    return None


def stampa_stato(cop: Copilota) -> None:
    st = cop.get("/copilot/state")
    print(f"\n--- tavolo: {st['n_events']} acquisti, calore x{st.get('heat', 1)} ---")
    for t in st["teams"]:
        rosa = " ".join(f"{r}{len(t['roster'][r])}" for r in ("P", "D", "C", "A"))
        io = " (io)" if t["index"] == st["my_index"] else ""
        print(f"  {t['index']}: {t['name']:12s} {t['budget']:4d} cr  max {t['max_bid']:4d}  {rosa}{io}")
    ultimi = st.get("last_events", [])[-5:]
    if ultimi:
        print("  ultimi:", "; ".join(f"{e['nome']} -> {st['names'][e['team_index']]} {e['price']}" for e in ultimi))


def stampa_elenco(cop: Copilota) -> None:
    """Tutti gli acquisti con la loro posizione nel registro.

    `--stato` mostra gli ultimi cinque, e il lotto da correggere quasi mai e'
    fra gli ultimi cinque: l'indice che `--modifica` e `--rimuovi` chiedono si
    legge qui.
    """
    righe = cop.get("/copilot/eventi")
    print(f"\n--- {len(righe)} acquisti registrati ---")
    for e in righe:
        print(f"  {e['indice']:>3}  {e['nome']:<18} {e['ruolo']} "
              f"{e['squadra']:<14} -> {e['acquirente']:<26} {e['prezzo']:>4}")


def applica_modifica(cop: Copilota, indice: int, *, ti: int | None = None,
                     prezzo: int | None = None, rimuovi: bool = False) -> int:
    """Manda la correzione e racconta cosa e' cambiato.

    Il server valida l'intera lista di eventi prima di accettare: se dice di
    no, qui non resta niente da disfare e si stampa il motivo che ha dato.
    """
    righe = cop.get("/copilot/eventi")
    riga = next((r for r in righe if r["indice"] == indice), None)
    if riga is None:
        print(f"indice {indice}: non esiste ({len(righe)} acquisti registrati). "
              "Usa --elenco")
        return 1
    # nanosecondi, non secondi: due correzioni sulla stessa riga nello stesso
    # secondo (cambia il prezzo, poi toglila) avrebbero lo stesso identificativo
    # e la seconda tornerebbe indietro come «duplicato», senza fare niente
    corpo = {"indice": indice,
             "richiesta_id_modifica": f"cli-mod-{indice}-{time.time_ns()}"}
    if rimuovi:
        corpo["rimuovi"] = True
    if ti is not None:
        corpo["team_index"] = ti
    if prezzo is not None:
        corpo["price"] = prezzo
    d, code = cop.post("/copilot/evento_modifica", corpo)
    testa = f"{riga['nome']} ({riga['ruolo']} {riga['squadra']}) indice {indice}"
    if not d.get("ok"):
        print(f"  RIFIUTATO {testa} -> {d.get('err')} ({code})")
        return 1
    if rimuovi:
        print(f"  TOLTO {testa}: era di {riga['acquirente']} a {riga['prezzo']}. "
              f"Acquisti: {d.get('n_events')}")
    else:
        dopo = d.get("dopo") or {}
        nomi = cop.squadre()
        print(f"  OK {testa}: {riga['acquirente']} {riga['prezzo']} -> "
              f"{nomi[dopo.get('team_index', riga['team_index'])]} "
              f"{dopo.get('price', riga['prezzo'])}"
              f"{' | duplicato' if d.get('duplicato') else ''}")
    return 0


def main() -> int:
    args = sys.argv[1:]
    porta = int(args[args.index("--porta") + 1]) if "--porta" in args else 8770
    secco = "--secco" in args
    cop = Copilota(porta)
    try:
        nomi = cop.squadre()
    except Exception as exc:                                       # noqa: BLE001
        print(f"Copilota non raggiungibile su {porta}: {exc}")
        return 2
    if not nomi:
        print("tavolo non configurato: fai il setup dalla pagina")
        return 2

    if "--stato" in args:
        stampa_stato(cop)
        return 0
    if "--elenco" in args:
        stampa_elenco(cop)
        return 0
    if "--rimuovi" in args:
        crudo = args[args.index("--rimuovi") + 1] if len(args) > args.index("--rimuovi") + 1 else ""
        if not crudo.isdigit():
            print(f"--rimuovi vuole l'indice dell'acquisto, non «{crudo}». "
                  "Gli indici li stampa --elenco")
            return 1
        esito = applica_modifica(cop, int(crudo), rimuovi=True)
        stampa_stato(cop)
        return esito
    if "--modifica" in args:
        voce = args[args.index("--modifica") + 1] if len(args) > args.index("--modifica") + 1 else ""
        m = re.match(r"^\s*(\d+)\s*(?:[>=]\s*([^:]+?)\s*)?(?::\s*(\d+)\s*)?$", voce)
        if not m:
            print(f"voce non capita: «{voce}» (forma: indice > squadra : prezzo)")
            return 1
        indice, squadra, prezzo = int(m.group(1)), m.group(2), m.group(3)
        if squadra is None and prezzo is None:
            print(f"«{voce}»: niente da cambiare. Dai una squadra, un prezzo, "
                  "o usa --rimuovi")
            return 1
        ti = None
        if squadra is not None:
            ti = risolvi_squadra(nomi, squadra)
            if ti is None:
                print(f"«{squadra}»: squadra ambigua o assente fra {nomi}")
                return 1
        esito = applica_modifica(cop, indice, ti=ti,
                                 prezzo=int(prezzo) if prezzo else None)
        stampa_stato(cop)
        return esito
    if "--undo" in args:
        d, code = cop.post("/copilot/undo", {"richiesta_id": f"cli-undo-{time.time()}"})
        print("annullato:", (d.get("annullato") or {}).get("player_id"), "| acquisti:", d.get("n_events"))
        stampa_stato(cop)
        return 0
    for flag, escluso in (("--escludi", True), ("--riammetti", False)):
        if flag in args:
            nome = args[args.index(flag) + 1]
            g, cand = risolvi_giocatore(cop, nome)
            if g is None:
                print(f"«{nome}»: ambiguo o assente:", [c["nome"] for c in cand][:8])
                return 1
            d, code = cop.post("/copilot/escludi", {"player_id": g["id"], "escluso": escluso})
            print(f"{g['nome']}: {'escluso' if escluso else 'riammesso'} -> {d.get('ok')} ({code})")
            return 0 if d.get("ok") else 1

    voci = [a for a in args if not a.startswith("--") and not a.isdigit()]
    esito = 0
    for voce in voci:
        m = re.match(r"^\s*(.+?)\s*[>=]\s*(.+?)\s*:\s*(\d+)\s*$", voce)
        if not m:
            print(f"voce non capita: «{voce}» (forma: giocatore > squadra : prezzo)")
            esito = 1
            continue
        nome, squadra, prezzo = m.group(1), m.group(2), int(m.group(3))
        g, cand = risolvi_giocatore(cop, nome)
        if g is None:
            print(f"«{nome}»: {'nessun giocatore' if not cand else 'ambiguo'}: "
                  f"{[(c['nome'], c['ruolo'], c['squadra']) for c in cand][:8]}")
            esito = 1
            continue
        ti = risolvi_squadra(nomi, squadra)
        if ti is None:
            print(f"«{squadra}»: squadra ambigua o assente fra {nomi}")
            esito = 1
            continue
        etichette = []
        if g.get("fuori_lista"):
            etichette.append("FUORI LISTA")
        if g.get("indisponibile"):
            etichette.append(f"indisponibile: {g['indisponibile']}")
        if g.get("escluso_manuale"):
            etichette.append("escluso da te")
        riga = f"{g['nome']} ({g['ruolo']} {g['squadra']}) -> {nomi[ti]} a {prezzo}"
        if secco:
            print("  [secco]", riga, " ".join(etichette))
            continue
        rid = f"cli-{g['id']}-{ti}-{prezzo}-{int(time.time())}"
        d, code = cop.post("/copilot/hammer", {"player_id": g["id"], "team_index": ti,
                                               "price": prezzo, "richiesta_id": rid})
        if d.get("ok"):
            print("  OK", riga, "| duplicato" if d.get("duplicato") else "",
                  f"| {d['nota']}" if d.get("nota") else "", " ".join(etichette))
        else:
            print("  RIFIUTATO", riga, "->", d.get("err"))
            esito = 1
    if voci and not secco:
        stampa_stato(cop)
    if not voci and "--secco" not in args:
        print(__doc__)
    return esito


if __name__ == "__main__":
    raise SystemExit(main())
