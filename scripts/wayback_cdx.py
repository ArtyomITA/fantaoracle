# -*- coding: utf-8 -*-
"""Enumerate Wayback Machine snapshots for fantacalcio-online.com price page via CDX API."""
import json
import sys
import time
import requests

OUT = r"data\raw\wayback_prices\snapshots_cdx.json"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
    "Accept-Language": "it-IT,it;q=0.9,en;q=0.8",
}

URL_VARIANTS = [
    "fantacalcio-online.com/it/asta-fantacalcio-stima-prezzi",
    "www.fantacalcio-online.com/it/asta-fantacalcio-stima-prezzi",
    "leghe.fantacalcio-online.com/it/asta-fantacalcio-stima-prezzi",
    # older/alternate paths that might have hosted the same table
    "fantacalcio-online.com/asta-fantacalcio-stima-prezzi",
    "fantacalcio-online.com/it/asta-fantacalcio-prezzi",
]

CDX = "http://web.archive.org/cdx/search/cdx"


def fetch_cdx(url_pat, retries=5):
    params = {
        "url": url_pat,
        "output": "json",
        "collapse": "timestamp:8",  # one per day
    }
    delay = 8
    for attempt in range(retries):
        try:
            r = requests.get(CDX, params=params, headers=HEADERS, timeout=60)
            if r.status_code == 200:
                if not r.text.strip():
                    return []
                return r.json()
            if r.status_code in (429, 503, 502):
                print(f"  HTTP {r.status_code}, backoff {delay}s (attempt {attempt+1})")
                time.sleep(delay)
                delay = min(delay * 2, 120)
                continue
            print(f"  HTTP {r.status_code}: {r.text[:200]}")
            return None
        except requests.RequestException as e:
            print(f"  error: {e}, backoff {delay}s")
            time.sleep(delay)
            delay = min(delay * 2, 120)
    return None


def main():
    all_rows = {}
    results_meta = {}
    for pat in URL_VARIANTS:
        print(f"CDX query: {pat}")
        data = fetch_cdx(pat)
        if data is None:
            results_meta[pat] = "ERROR/unreachable"
        elif not data:
            results_meta[pat] = "0 snapshots"
        else:
            header, rows = data[0], data[1:]
            results_meta[pat] = f"{len(rows)} snapshots"
            for row in rows:
                d = dict(zip(header, row))
                key = (d["timestamp"], d["original"])
                all_rows[key] = d
        print(f"  -> {results_meta[pat]}")
        time.sleep(6)

    snaps = sorted(all_rows.values(), key=lambda d: d["timestamp"])
    out = {"queried": results_meta, "snapshots": snaps}
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(out, f, indent=1, ensure_ascii=False)
    print(f"\nTotal unique (timestamp,url): {len(snaps)} -> {OUT}")
    for s in snaps:
        print(s["timestamp"], s["statuscode"], s["mimetype"], s["original"], s.get("length", ""))


if __name__ == "__main__":
    main()
