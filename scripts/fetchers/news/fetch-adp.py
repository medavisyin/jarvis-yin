"""Scrape ADP National Employment Report releases from the media center."""
from __future__ import annotations

import json
import os
import sys
import time

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(SCRIPT_DIR, ".."))
sys.path.insert(0, SCRIPT_DIR)
from proxy_strategy import get_proxies_for_requests  # noqa: E402
from us_macro_parse import parse_adp_list_html  # noqa: E402

SOURCE_NAME = "adp"
OUTPUT_DIR = sys.argv[1] if len(sys.argv) > 1 else "."
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
LIST_URLS = [
    "https://mediacenter.adp.com/",
    "https://mediacenter.adp.com/workforce-data-releases",
]


def fetch_items() -> list[dict]:
    try:
        import requests
    except ImportError:
        return []
    items: list[dict] = []
    seen: set[str] = set()
    for url in LIST_URLS:
        try:
            resp = requests.get(
                url,
                headers=HEADERS,
                timeout=20,
                proxies=get_proxies_for_requests(url),
            )
            if not resp.ok:
                print(f"  adp HTTP {resp.status_code} {url}")
                continue
            for it in parse_adp_list_html(resp.text, base="https://mediacenter.adp.com"):
                key = it["title"].lower()[:80]
                if key in seen:
                    continue
                seen.add(key)
                items.append(it)
        except Exception as e:
            print(f"  adp scrape failed {url}: {e}")
        if len(items) >= 12:
            break
    return items[:12]


def main():
    t0 = time.monotonic()
    print(f"[{SOURCE_NAME}] Fetching ADP employment reports...")
    items = fetch_items()
    timing = {
        "source": SOURCE_NAME,
        "steps": [{"step": "scrape", "seconds": round(time.monotonic() - t0, 2)}],
        "total_seconds": round(time.monotonic() - t0, 2),
    }
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    out_path = os.path.join(OUTPUT_DIR, f"{SOURCE_NAME}.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump({"source": SOURCE_NAME, "items": items, "_timing": timing}, f,
                  ensure_ascii=False, indent=2)
    print(f"[{SOURCE_NAME}] {len(items)} items, {timing['total_seconds']}s -> {out_path}")


if __name__ == "__main__":
    main()
