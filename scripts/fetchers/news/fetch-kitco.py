"""Scrape Kitco News article list. Official RSS KitcoNews.xml is 404."""
from __future__ import annotations

import json
import os
import re
import sys
import time
from urllib.parse import urljoin

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(SCRIPT_DIR, ".."))
from proxy_strategy import get_proxies_for_requests  # noqa: E402

SOURCE_NAME = "kitco"
OUTPUT_DIR = sys.argv[1] if len(sys.argv) > 1 else "."
LIST_URL = "https://www.kitco.com/news"
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
MAX_ITEMS = 12
_ARTICLE_RE = re.compile(r"/news/article/\d{4}-\d{2}-\d{2}/[^\"'#?]+")


def _slug_title(path: str) -> str:
    slug = path.rstrip("/").rsplit("/", 1)[-1]
    return re.sub(r"[-_]+", " ", slug).strip().capitalize()


def _walk_next_data(obj, acc: list[tuple[str, str]]) -> None:
    if isinstance(obj, dict):
        raw_url = obj.get("url") or obj.get("href") or obj.get("canonical") or ""
        title = (
            obj.get("headline")
            or obj.get("title")
            or obj.get("name")
            or ""
        )
        url = str(raw_url)
        if title and "/news/article/" in url:
            acc.append((str(title).strip(), url))
        for v in obj.values():
            _walk_next_data(v, acc)
    elif isinstance(obj, list):
        for v in obj:
            _walk_next_data(v, acc)


def fetch_items() -> list[dict]:
    try:
        import requests
    except ImportError:
        return []
    items: list[dict] = []
    seen: set[str] = set()
    try:
        resp = requests.get(
            LIST_URL,
            headers=HEADERS,
            timeout=20,
            proxies=get_proxies_for_requests(LIST_URL),
        )
        if not resp.ok:
            print(f"  kitco list HTTP {resp.status_code}")
            return items
        html = resp.text
        found: list[tuple[str, str]] = []
        m = re.search(
            r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', html, re.S
        )
        if m:
            try:
                _walk_next_data(json.loads(m.group(1)), found)
            except json.JSONDecodeError:
                found = []
        if not found:
            for path in dict.fromkeys(_ARTICLE_RE.findall(html)):
                found.append((_slug_title(path), urljoin("https://www.kitco.com", path)))
        for title, url in found:
            if not url.startswith("http"):
                url = urljoin("https://www.kitco.com", url)
            key = title.lower()[:80]
            if not title or key in seen:
                continue
            seen.add(key)
            items.append({
                "title": title,
                "url": url,
                "date": "",
                "summary": "",
                "category": "gold",
                "points": [],
                "source": "Kitco News",
            })
            if len(items) >= MAX_ITEMS:
                break
    except Exception as e:
        print(f"  kitco scrape failed: {e}")
    return items


def main():
    t0 = time.monotonic()
    print(f"[{SOURCE_NAME}] Fetching Kitco News...")
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
