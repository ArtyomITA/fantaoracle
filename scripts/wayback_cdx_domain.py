# -*- coding: utf-8 -*-
"""Domain-wide CDX search on fantacalcio-online.com for URLs that may have hosted auction price tables."""
import json
import time
import requests

OUT = r"data\raw\wayback_prices\snapshots_cdx_domain.json"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
    "Accept-Language": "it-IT,it;q=0.9,en;q=0.8",
}
CDX = "http://web.archive.org/cdx/search/cdx"

QUERIES = [
    # unique URLs containing 'asta' anywhere on the domain (any subdomain)
    {"url": "fantacalcio-online.com", "matchType": "domain", "output": "json",
     "collapse": "urlkey", "filter": "urlkey:.*asta.*", "limit": "3000",
     "fl": "urlkey,timestamp,original,mimetype,statuscode"},
    # unique URLs containing 'prezzi'
    {"url": "fantacalcio-online.com", "matchType": "domain", "output": "json",
     "collapse": "urlkey", "filter": "urlkey:.*prezzi.*", "limit": "3000",
     "fl": "urlkey,timestamp,original,mimetype,statuscode"},
]


def fetch(params, retries=5):
    delay = 10
    for attempt in range(retries):
        try:
            r = requests.get(CDX, params=params, headers=HEADERS, timeout=120)
            if r.status_code == 200:
                return r.json() if r.text.strip() else []
            if r.status_code in (429, 502, 503):
                print(f"  HTTP {r.status_code}, backoff {delay}s")
                time.sleep(delay)
                delay = min(delay * 2, 180)
                continue
            print(f"  HTTP {r.status_code}: {r.text[:300]}")
            return None
        except requests.RequestException as e:
            print(f"  error: {e}, backoff {delay}s")
            time.sleep(delay)
            delay = min(delay * 2, 180)
    return None


def main():
    results = []
    for q in QUERIES:
        print(f"query filter={q['filter']}")
        data = fetch(q)
        if data is None:
            print("  FAILED")
            continue
        if not data:
            print("  0 rows")
            continue
        header, rows = data[0], data[1:]
        print(f"  {len(rows)} unique urlkeys")
        for row in rows:
            results.append(dict(zip(header, row)))
        time.sleep(8)

    # dedupe by urlkey
    seen = {}
    for r in results:
        seen.setdefault(r["urlkey"], r)
    uniq = sorted(seen.values(), key=lambda d: d["urlkey"])
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(uniq, f, indent=1, ensure_ascii=False)
    print(f"\n{len(uniq)} unique URLs -> {OUT}")
    for u in uniq:
        print(u["timestamp"], u["statuscode"], u["original"])


if __name__ == "__main__":
    main()
