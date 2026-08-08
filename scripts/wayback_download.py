# -*- coding: utf-8 -*-
"""Download Wayback snapshots (original content via id_ flag) with polite pauses and backoff.

Usage: python wayback_download.py <timestamp> <url> [<timestamp> <url> ...]
Files land in data/raw/wayback_prices/html/{timestamp}_{slug}.html
Skips files already downloaded.
"""
import os
import random
import sys
import time
import requests

HTML_DIR = r"data\raw\wayback_prices\html"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
    "Accept-Language": "it-IT,it;q=0.9,en;q=0.8",
}


def slug_for(url):
    s = url.replace("https://", "").replace("http://", "").replace(":80", "")
    s = s.replace("/", "_").replace("?", "_").replace("*", "_")
    return s[:120]


def download(ts, url, retries=6):
    fname = os.path.join(HTML_DIR, f"{ts}_{slug_for(url)}.html")
    if os.path.exists(fname) and os.path.getsize(fname) > 5000:
        print(f"SKIP (exists): {fname}")
        return fname
    wb_url = f"http://web.archive.org/web/{ts}id_/{url}"
    delay = 12
    for attempt in range(retries):
        try:
            r = requests.get(wb_url, headers=HEADERS, timeout=120)
            if r.status_code == 200:
                r.encoding = r.apparent_encoding or "utf-8"
                with open(fname, "w", encoding="utf-8", errors="replace") as f:
                    f.write(r.text)
                print(f"OK {ts} {url} -> {os.path.basename(fname)} ({len(r.text)} chars)")
                return fname
            if r.status_code in (429, 502, 503, 504):
                print(f"  HTTP {r.status_code}, backoff {delay}s (attempt {attempt+1})")
                time.sleep(delay)
                delay = min(delay * 2, 240)
                continue
            print(f"  HTTP {r.status_code} for {wb_url} -- giving up")
            return None
        except requests.RequestException as e:
            print(f"  error: {e}, backoff {delay}s")
            time.sleep(delay)
            delay = min(delay * 2, 240)
    return None


def main():
    args = sys.argv[1:]
    pairs = [(args[i], args[i + 1]) for i in range(0, len(args), 2)]
    for i, (ts, url) in enumerate(pairs):
        download(ts, url)
        if i < len(pairs) - 1:
            time.sleep(random.uniform(6, 9))


if __name__ == "__main__":
    main()
