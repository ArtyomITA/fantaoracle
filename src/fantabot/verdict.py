"""Report verdetto: aggrega i summary.json del torneo in un markdown leggibile.

Criterio di successo dichiarato nel PIANO (§7): B "funziona" se win rate H2H
> 10% (baseline casuale a 10 seggi) con margine, e punti sopra la media
tavolo in >= 70% delle repliche, su ENTRAMBE le stagioni.
"""
from __future__ import annotations

import json
from pathlib import Path

BASELINE_WIN = 0.10
SUCCESS_PCT_ABOVE = 0.70


def load_summaries(root: str | Path) -> list[dict]:
    return [json.loads(p.read_text(encoding="utf-8"))
            for p in sorted(Path(root).glob("**/summary.json"))]


def verdict_markdown(summaries: list[dict]) -> str:
    lines = ["# Verdetto torneo B vs A vs C", ""]
    b_ok = []
    for s in summaries:
        season, table, n = s["season"], s["table"], s["n_replicas"]
        lines.append(f"## {season} — tavolo {'+'.join(table)} — {n} repliche")
        lines.append("")
        lines.append("| bot | win rate | rank medio | punti vs tavolo | % sopra media | residuo |")
        lines.append("|---|---|---|---|---|---|")
        for k, v in sorted(s["bots"].items(), key=lambda kv: kv[1]["avg_rank"]):
            lines.append(
                f"| {k} | {v['win_rate']:.1%} | {v['avg_rank']:.2f} "
                f"| {v['pts_vs_table_mean']:+.1f} | {v['pct_above_table_mean']:.0%} "
                f"| {v['avg_leftover']:.0f} |")
        lines.append("")
        b = s["bots"].get("B")
        if b:
            ok = (b["win_rate"] > BASELINE_WIN
                  and b["pct_above_table_mean"] >= SUCCESS_PCT_ABOVE)
            b_ok.append((season, table, ok, b))
            lines.append(
                f"**B qui: {'SUPERA' if ok else 'NON supera'} il criterio** "
                f"(win {b['win_rate']:.1%} vs soglia {BASELINE_WIN:.0%}; "
                f"sopra media nel {b['pct_above_table_mean']:.0%} vs soglia "
                f"{SUCCESS_PCT_ABOVE:.0%}).")
            lines.append("")
    if b_ok:
        overall = all(ok for _, _, ok, _ in b_ok)
        lines.insert(2, f"**VERDETTO COMPLESSIVO: B {'SUPERA' if overall else 'NON supera'} "
                        f"il criterio dichiarato su {sum(1 for x in b_ok if x[2])}/"
                        f"{len(b_ok)} configurazioni.**")
        lines.insert(3, "")
    return "\n".join(lines)


def write_verdict(root: str | Path, out_path: str | Path) -> str:
    md = verdict_markdown(load_summaries(root))
    Path(out_path).write_text(md, encoding="utf-8")
    return md
