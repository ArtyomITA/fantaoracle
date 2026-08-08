# -*- coding: utf-8 -*-
"""Full snapshot list (no collapse) for each candidate price-table URL."""
import json
import time
import requests

OUT = r"data\raw\wayback_prices\snapshots_cdx.json"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
    "Accept-Language": "it-IT,it;q=0.9,en;q=0.8",
}
CDX = "http://web.archive.org/cdx/search/cdx"

URLS = [
    "fantacalcio-online.com/it/asta-fantacalcio-stima-prezzi",
    "s7.fantacalcio-online.com/it/asta-fantacalcio-stima-prezzi",
    "fantacalcio-online.com/it/serie-a/2018-2019/asta-fantacalcio-prezzi-acquisto",
    "fantacalcio-online.com/it/serie-a/2019-2020/asta-fantacalcio-prezzi-acquisto",
    "fantacalcio-online.com/it/serie-a/2020-2021/asta-fantacalcio-prezzi-acquisto",
    "fantacalcio-online.com/it/serie-a/2021-2022/asta-fantacalcio-prezzi-acquisto",
    "fantacalcio-online.com/it/serie-a/2022-2023/asta-fantacalcio-prezzi-acquisto",
    "fantacalcio-online.com/it/serie-a/2023-2024/asta-fantacalcio-prezzi-acquisto",
    "fantacalcio-online.com/it/serie-a/2024-2025/asta-fantacalcio-prezzi-acquisto",
    "fantacalcio-online.com/it/serie-a/2025-2026/asta-fantacalcio-prezzi-acquisto",
    "s7.fantacalcio-online.com/it/serie-a/2018-2019/asta-fantacalcio-prezzi-acquisto",
    "s7.fantacalcio-online.com/it/serie-a/2019-2020/asta-fantacalcio-prezzi-acquisto",
    "s7.fantacalcio-online.com/it/serie-a/2020-2021/asta-fantacalcio-prezzi-acquisto",
    "s7.fantacalcio-online.com/it/serie-a/2021-2022/asta-fantacalcio-prezzi-acquisto",
    "s7.fantacalcio-online.com/it/serie-a/2022-2023/asta-fantacalcio-prezzi-acquisto",
]


def fetch(url_pat, retries=5):
    params = {
        "url": url_pat,
        "output": "json",
        "fl": "timestamp,original,statuscode,mimetype,digest,length",
    }
    delay = 10
    for _ in range(retries):
        try:
            r = requests.get(CDX, params=params, headers=HEADERS, timeout=90)
            if r.status_code == 200:
                return r.json() if r.text.strip() else []
            if r.status_code in (429, 502, 503):
                print(f"  HTTP {r.status_code}, backoff {delay}s")
                time.sleep(delay)
                delay = min(delay * 2, 180)
                continue
            print(f"  HTTP {r.status_code}")
            return None
        except requests.RequestException as e:
            print(f"  error: {e}, backoff {delay}s")
            time.sleep(delay)
            delay = min(delay * 2, 180)
    return None


def main():
    result = {}
    for u in URLS:
        print(f"CDX: {u}")
        data = fetch(u)
        if data is None:
            result[u] = {"status": "ERROR", "snapshots": []}
        elif not data:
            result[u] = {"status": "empty", "snapshots": []}
        else:
            header, rows = data[0], data[1:]
            snaps = [dict(zip(header, r)) for r in rows]
            result[u] = {"status": f"{len(snaps)} snapshots", "snapshots": snaps}
            for s in snaps:
                print(" ", s["timestamp"], s["statuscode"], s["digest"][:8], s.get("length"), s["original"])
        time.sleep(6)

    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=1, ensure_ascii=False)
    print(f"\nsaved -> {OUT}")


if __name__ == "__main__":
    main()
