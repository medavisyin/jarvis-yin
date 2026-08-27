"""Scrape CSRC (China Securities Regulatory Commission) news. Soft-fail."""
from __future__ import annotations

import json
import os
import re
import sys
import time

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(SCRIPT_DIR, ".."))
from proxy_strategy import get_proxies_for_requests  # noqa: E402

SOURCE_NAME = "csrc"
OUTPUT_DIR = sys.argv[1] if len(sys.argv) > 1 else "."
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
LIST_URL = "http://www.csrc.gov.cn/csrc/c100028/common_list.shtml"


def fetch_items() -> list[dict]:
    try:
        import requests
    except ImportError:
        return []
    items = []
    try:
        resp = requests.get(
            LIST_URL,
            headers=HEADERS,
            timeout=15,
            proxies=get_proxies_for_requests(LIST_URL),
        )
        resp.encoding = resp.apparent_encoding or "utf-8"
        html = resp.text
        seen = set()
        for m in re.finditer(r'href="([^"]+)"[^>]*>([^<]{8,120})</a>', html, re.I):
            href, title = m.group(1).strip(), re.sub(r"\s+", " ", m.group(2)).strip()
            if title in seen or "javascript" in href.lower():
                continue
            seen.add(title)
            url = href if href.startswith("http") else f"http://www.csrc.gov.cn{href}"
            items.append({
                "title": title,
                "title_zh": title,
                "url": url,
                "date": "",
                "summary": "",
                "category": "china-policy",
                "points": [],
                "source": "CSRC 证监会",
            })
            if len(items) >= 12:
                break
    except Exception as e:
        print(f"  CSRC scrape failed: {e}")
    return items


def main():
    t0 = time.monotonic()
    print(f"[{SOURCE_NAME}] Fetching CSRC...")
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
