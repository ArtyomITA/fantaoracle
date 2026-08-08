# -*- coding: utf-8 -*-
"""Scarica gli altri sheet ID GruppoEsperti elencati nel README di fonti_prezzi.

Google Sheets nativi: https://docs.google.com/spreadsheets/d/{ID}/export?format=xlsx
File non-nativo su Drive: https://drive.google.com/uc?export=download&id={ID}
Pause 1-3 s fra richieste, retry con backoff su 429/503.
"""
import json
import os
import random
import time

import requests

OUT_DIR = r"data\raw\gruppoesperti\extra"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36")

# (id, nota dal README, non_nativo)
SHEETS = [
    ("1Uxv42LC7d68Y1ZLQ48Hh1ud74kJocO-lTom39eJFB_w", "contiene Dovbyk/Kvara", False),
    ("1MeKG7yjCemQ1SFoi7RWmhni-iBMtYdPf9FtfdDQWZ5I", "template vuoto", False),
    ("1J4tILPqyErS5Ccpr0Dy-595D2PgubYxlPaqfX8-pjYw", "vuoto", False),
    ("17nJSWuLgeJbKXUZdzLVnFrDyUh5h7E-NBDbCqR5aUek", "", False),
    ("1w_EFGFlnfw9fSpnVCUvsaLygHV_IxePSi5tbTXRY13U", "", False),
    ("1STf54UI3M7qPTG1xo-ZcoKa3zmH_d5BEEiqR5jsmqnc", "", False),
    ("1stdSoivNLfLclpldTApwbQaxZeIEU65Wz_wot42vUy4", "", False),
    ("1jmMPIJjVGgfpbH1yRt0YGGgYZUrIH0T8UvvBdAdvjqQ", "", False),
    ("1WB6W3_JoO8pnFtCBwHDEiEQPdKWQNQmMJBDcPkTzEtc", "", False),
    ("19V3e-54FTPMIjOez_f3XsM7ce39x4RaaJWVyR5Gp3NA", "", False),
    ("11lb2kwrvyXQFff5Am6Z6MbIDQ5C4mRthemmaJnbo_Tg", "", False),
    ("1NcS1jKQGU0yO1hydtFQonO0YJ-yUpVXbapwYBzI8P6A", "", False),
    ("1NWhc0N5hVrKKMjPbLzEiNKRz3PbClFzGmSJ0R7sjEd8", "", False),
    ("1WCI4B2W_IJyykN2jCjiCMyDe4mOjs25ZcS2C3TM8pSs", "non-nativo (xlsx su Drive)", True),
]

XLSX_MAGIC = b"PK\x03\x04"


def fetch(url, session, max_tries=4):
    for attempt in range(1, max_tries + 1):
        try:
            resp = session.get(url, timeout=60, allow_redirects=True)
        except requests.RequestException as e:
            if attempt == max_tries:
                return None, f"exception: {e}"
            time.sleep(2 ** attempt + random.uniform(0, 1))
            continue
        if resp.status_code in (429, 503):
            wait = 2 ** attempt * 2 + random.uniform(0, 2)
            print(f"    HTTP {resp.status_code}, backoff {wait:.1f}s")
            time.sleep(wait)
            continue
        return resp, None
    return None, "troppi retry su 429/503"


def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    session = requests.Session()
    session.headers.update({"User-Agent": UA})
    results = []
    for sid, note, non_native in SHEETS:
        out_path = os.path.join(OUT_DIR, f"{sid}.xlsx")
        if os.path.exists(out_path) and os.path.getsize(out_path) > 0:
            print(f"[skip] {sid} già scaricato")
            results.append({"id": sid, "note": note, "status": "ok(cached)",
                            "bytes": os.path.getsize(out_path)})
            continue
        if non_native:
            url = f"https://drive.google.com/uc?export=download&id={sid}"
        else:
            url = f"https://docs.google.com/spreadsheets/d/{sid}/export?format=xlsx"
        print(f"[get ] {sid} ({note or 'senza nota'}) non_nativo={non_native}")
        resp, err = fetch(url, session)
        status = None
        if err:
            status = f"fail: {err}"
        elif resp.status_code != 200:
            status = f"fail: HTTP {resp.status_code}"
        elif not resp.content.startswith(XLSX_MAGIC):
            # potrebbe essere una pagina html (auth richiesta / conferma virus-scan Drive)
            head = resp.content[:200].decode("utf-8", "replace")
            if non_native and b"confirm" in resp.content[:4000].lower():
                status = "fail: pagina conferma Drive (file grande?)"
            else:
                status = f"fail: non xlsx (inizio: {head[:80]!r})"
        else:
            with open(out_path, "wb") as f:
                f.write(resp.content)
            status = "ok"
            print(f"    salvato {len(resp.content)} byte")
        if status != "ok":
            print(f"    {status}")
        results.append({"id": sid, "note": note, "status": status,
                        "bytes": len(resp.content) if (resp is not None and status == "ok") else 0})
        time.sleep(random.uniform(1.0, 3.0))

    with open(os.path.join(OUT_DIR, "download_log.json"), "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    ok = sum(1 for r in results if r["status"].startswith("ok"))
    print(f"\nScaricati {ok}/{len(SHEETS)}")


if __name__ == "__main__":
    main()
