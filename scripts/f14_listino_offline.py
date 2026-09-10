"""Listino offline per l'asta: una pagina HTML da stampare o tenere sul telefono.

Serve come piano B se il portatile o il server muoiono a meta' asta: per ogni
ruolo, i giocatori in ordine di valore atteso con la mediana di prezzo, il
tetto consigliato allo stato iniziale, il prezzo di mercato di riferimento,
lo stato sportivo e la nota dell'esperto. I tetti sono quelli del piano
iniziale (tavolo vuoto): durante l'asta il Copilota li ricalcola, la carta no.

Uso:
    python scripts/f14_listino_offline.py [stagione] [--budget 500] [--squadre 10]
Scrive data/copilot/listino_offline_<stagione>.html
"""
from __future__ import annotations

import datetime
import html
import importlib.util
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))


def carica_copilota():
    spec = importlib.util.spec_from_file_location("cop_listino", ROOT / "scripts" / "f10_copilot.py")
    c = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = c
    spec.loader.exec_module(c)
    return c


def main() -> int:
    args = sys.argv[1:]
    stagione = next((a for a in args if a[0].isdigit()), "2026-27")
    budget = int(args[args.index("--budget") + 1]) if "--budget" in args else 500
    squadre = int(args[args.index("--squadre") + 1]) if "--squadre" in args else 10
    c = carica_copilota()
    c.PACK = c.load_pack(stagione)
    c.ELEGGIBILITA = c.carica_eleggibilita(stagione)
    c.prepara_pack(stagione)
    with tempfile.TemporaryDirectory() as tmp:
        c.LEDGER_PATH = Path(tmp) / "listino.json"
        c.STATE.update({"season": stagione, "names": [f"S{i}" for i in range(squadre)],
                        "my_index": 0, "budget": budget,
                        "quotas": dict(c.PACK.quotas), "events": [], "bids": []})
        c.rebuild_advisor()
        A = c.ADVISOR
        ruoli = {"P": "Portieri", "D": "Difensori", "C": "Centrocampisti", "A": "Attaccanti"}
        righe_html = []
        for r, titolo in ruoli.items():
            ids = [pid for pid, p in c.pool().items() if p.role == r]
            ids.sort(key=lambda q: -(A._q(q, "value", 0.0)))
            righe = []
            for i, pid in enumerate(ids, 1):
                info = c.player_info(pid)
                d = c.decisione_operativa(pid, None)
                piano = "TIT" if pid in A.starter_targets else ("pan" if pid in A.targets else "")
                ind = ""
                if info.get("indisponibile"):
                    ret = info.get("rettifica") or {}
                    ind = f"{info['indisponibile']}"
                    if ret:
                        ind += f" (-{ret['giornate_perse']} g.)"
                nota = info.get("nota_esperto") or ""
                if len(nota) > 110:
                    nota = nota[:107] + "..."
                cls = " class='piano'" if piano else ""
                righe.append(
                    f"<tr{cls}><td>{i}</td><td>{html.escape(info['nome'])}</td>"
                    f"<td>{html.escape(info['squadra'])}</td>"
                    f"<td class='n'>{info['value']:.0f}</td>"
                    f"<td class='n'>{info['q50']:.0f}</td>"
                    f"<td class='n t'>{d['max_consigliato']}</td>"
                    f"<td class='n'>{'' if info.get('prezzo_mercato') is None else f'{float(info['prezzo_mercato']):.0f}'}</td>"
                    f"<td>{piano}</td><td class='ind'>{html.escape(ind)}</td>"
                    f"<td class='nota'>{html.escape(nota)}</td></tr>")
            righe_html.append(
                f"<h2>{titolo} <small>({len(ids)} comprabili)</small></h2>"
                "<table><thead><tr><th>#</th><th>nome</th><th>sq</th><th>valore</th>"
                "<th>mediana</th><th>tetto</th><th>mercato</th><th>piano</th>"
                "<th>stato</th><th>l'esperto dice</th></tr></thead><tbody>"
                + "".join(righe) + "</tbody></table>")
        pl = c.plan()
        spesa = {r: sum(x["prezzo_atteso"] for x in pl["target"][r]) for r in ruoli}
        target = {r: ", ".join(f"{x['nome']} ({x['max_consigliato']:.0f})" for x in pl["target"][r])
                  for r in ruoli}
        el = c.ELEGGIBILITA
        testa = (
            f"<h1>Listino offline {stagione}</h1>"
            f"<p class='meta'>generato {datetime.datetime.now():%d/%m/%Y %H:%M} · pack "
            f"{c.identita_bundle().get('impronta', '')[:12]} · fonti del "
            f"{str(el.get('acquisito') or '')[:10]} · {len(el.get('esclusi', ()))} fuori Serie A esclusi · "
            f"{len(c.RETTIFICHE)} indisponibili con valore ridotto · tavolo {squadre} squadre, {budget} crediti</p>"
            "<p class='meta'><b>tetto</b> = massimo che il bot pagherebbe a tavolo vuoto, gia' entro il "
            "massimo legale: durante l'asta cambia con la cassa e col mercato. <b>mercato</b> = prezzo "
            "medio in leghe 10 squadre/500 crediti (riferimento, non tetto). <b>piano</b>: TIT titolare, "
            "pan panchina del piano iniziale. <b>stato</b>: indisponibile oggi e giornate perse stimate. "
            "Le note dell'esperto sono opinioni (video del 3-4/9/2026), non dati del modello.</p>"
            f"<h2>Piano iniziale <small>costo atteso {pl['costo_atteso_piano']:.0f}</small></h2><ul>"
            + "".join(f"<li><b>{r}</b> ({spesa[r]:.0f} cr): {html.escape(target[r])}</li>" for r in ruoli)
            + "</ul>")
        stile = """<style>
body{font-family:Segoe UI,Arial,sans-serif;font-size:11px;margin:12px;color:#111}
h1{font-size:18px;margin:0 0 4px}h2{font-size:14px;margin:14px 0 4px;page-break-before:auto}
small{font-weight:400;color:#666}.meta{color:#444;margin:2px 0}
table{border-collapse:collapse;width:100%}th,td{border:1px solid #ccc;padding:2px 4px;text-align:left}
th{background:#eee}.n{text-align:right}.t{font-weight:700}.piano{background:#fff6cc}
.ind{color:#b3261e}.nota{color:#333;font-size:10px}
@media print{h2{page-break-before:always}h2:first-of-type{page-break-before:auto}}
</style>"""
        fuori = ROOT / "data" / "copilot" / f"listino_offline_{stagione}.html"
        fuori.write_text("<!doctype html><meta charset='utf-8'><title>Listino offline "
                         f"{stagione}</title>{stile}{testa}{''.join(righe_html)}", encoding="utf-8")
        print(f"scritto {fuori} ({fuori.stat().st_size // 1024} KB)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
