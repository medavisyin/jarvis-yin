"""
Fetch Yahoo Finance headlines via RSS.

Fails soft: writes empty items JSON and exits 0 on network/parse failures.

Usage: python fetch-yahoo-finance.py [output-dir]
Output: <output-dir>/yahoo-finance.json
"""
from __future__ import annotations

import json
import os
import re
import sys
import time

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(SCRIPT_DIR, ".."))
from proxy_strategy import get_proxy_for_httpx

SOURCE_NAME = "yahoo-finance"
MAX_ITEMS = 15
OUTPUT_DIR = sys.argv[1] if len(sys.argv) > 1 else "."

RSS_FEEDS = [
    ("markets", "https://finance.yahoo.com/news/rssindex"),
    ("headlines", "https://www.yahoo.com/news/rss/finance"),
]


def _strip_html(text: str) -> str:
    return re.sub(r"<[^>]+>", "", text or "").strip()[:400]


def fetch_items() -> list[dict]:
    try:
        import feedparser
        import httpx
    except ImportError as e:
        print(f"  Dependencies missing: {e}")
        return []

    items: list[dict] = []
    seen: set[str] = set()
    for category, url in RSS_FEEDS:
        try:
            kwargs = {"timeout": 12, "follow_redirects": True}
            kwargs.update(get_proxy_for_httpx(url))
            headers = {
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
                )
            }
            r = httpx.get(url, headers=headers, **kwargs)
            r.raise_for_status()
            feed = feedparser.parse(r.text)
            for entry in feed.entries[:MAX_ITEMS]:
                title = (entry.get("title") or "").strip()
                if not title or title.lower() in seen:
                    continue
                seen.add(title.lower())
                summary = _strip_html(entry.get("summary") or entry.get("description") or "")
                items.append({
                    "title": title,
                    "url": entry.get("link", ""),
                    "date": entry.get("published", entry.get("updated", "")),
                    "summary": summary,
                    "category": "markets",
                    "points": [],
                })
                if len(items) >= MAX_ITEMS:
                    return items
        except Exception as e:
            print(f"  Yahoo RSS {category} failed: {e}")
    return items


def main():
    t0 = time.monotonic()
    print(f"[{SOURCE_NAME}] Fetching Yahoo Finance RSS...")
    try:
        items = fetch_items()
    except Exception as e:
        print(f"[{SOURCE_NAME}] ERROR: {e}")
        items = []

    timing = {
        "source": SOURCE_NAME,
        "steps": [{"step": "rss", "seconds": round(time.monotonic() - t0, 2)}],
        "total_seconds": round(time.monotonic() - t0, 2),
    }
    result = {"source": SOURCE_NAME, "items": items, "_timing": timing}
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    out_path = os.path.join(OUTPUT_DIR, f"{SOURCE_NAME}.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    print(f"[{SOURCE_NAME}] {len(items)} items, {timing['total_seconds']}s -> {out_path}")


if __name__ == "__main__":
    main()
