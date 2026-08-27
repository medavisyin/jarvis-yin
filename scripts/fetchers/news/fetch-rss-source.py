"""
Generic RSS fetcher driven by finance_sources.json.

Usage: python fetch-rss-source.py <output-dir> <source-id>
Output: <output-dir>/<source-id>.json
"""
from __future__ import annotations

import json
import os
import re
import sys
import time

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PIPELINE_DIR = os.path.normpath(os.path.join(SCRIPT_DIR, "..", "..", "pipeline"))
sys.path.insert(0, os.path.join(SCRIPT_DIR, ".."))
sys.path.insert(0, PIPELINE_DIR)

from proxy_strategy import get_proxy_for_httpx  # noqa: E402
from finance_sources import catalog_by_id, output_filename  # noqa: E402

OUTPUT_DIR = sys.argv[1] if len(sys.argv) > 1 else "."
SOURCE_ID = sys.argv[2] if len(sys.argv) > 2 else ""
MAX_ITEMS = 12


def _strip_html(text: str) -> str:
    return re.sub(r"<[^>]+>", "", text or "").strip()[:400]


def fetch_items(source_id: str) -> list[dict]:
    src = catalog_by_id(source_id)
    feeds = src.get("feeds") or []
    if not feeds:
        print(f"  [{source_id}] no feeds in catalog")
        return []
    try:
        import feedparser
        import httpx
    except ImportError as e:
        print(f"  Dependencies missing: {e}")
        return []

    items: list[dict] = []
    seen: set[str] = set()
    for category, url in feeds:
        try:
            kwargs = {"timeout": 15, "follow_redirects": True,
                      "headers": {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}}
            kwargs.update(get_proxy_for_httpx(url))
            r = httpx.get(url, **kwargs)
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
                    "category": category,
                    "points": [],
                    "source": src.get("display") or source_id,
                })
                if len(items) >= MAX_ITEMS * 2:
                    return items
        except Exception as e:
            print(f"  [{source_id}] RSS {category} failed: {e}")
    return items


def main():
    t0 = time.monotonic()
    if not SOURCE_ID:
        print("[rss-source] ERROR: source-id required")
        sys.exit(1)
    print(f"[{SOURCE_ID}] Fetching RSS...")
    try:
        items = fetch_items(SOURCE_ID)
    except KeyError:
        print(f"[{SOURCE_ID}] ERROR: unknown source id")
        items = []
    except Exception as e:
        print(f"[{SOURCE_ID}] ERROR: {e}")
        items = []

    timing = {
        "source": SOURCE_ID,
        "steps": [{"step": "rss", "seconds": round(time.monotonic() - t0, 2)}],
        "total_seconds": round(time.monotonic() - t0, 2),
    }
    result = {"source": SOURCE_ID, "items": items, "_timing": timing}
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    try:
        src_row = catalog_by_id(SOURCE_ID)
        out_name = output_filename(src_row)
    except KeyError:
        out_name = f"{SOURCE_ID}.json"
    out_path = os.path.join(OUTPUT_DIR, out_name)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    print(f"[{SOURCE_ID}] {len(items)} items, {timing['total_seconds']}s -> {out_path}")


if __name__ == "__main__":
    main()
