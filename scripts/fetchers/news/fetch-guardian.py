"""
Fetch top world news from The Guardian via RSS + Playwright drill-down.

The Guardian provides excellent RSS feeds across multiple sections.

Usage: python fetch-guardian.py [output-dir]
Output: <output-dir>/guardian.json
"""
import asyncio
import json
import os
import sys
import time

import feedparser

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(SCRIPT_DIR, "..", ".."))
from raw_saver import save_raw_content

sys.path.insert(0, os.path.join(SCRIPT_DIR, ".."))
from proxy_strategy import get_proxy_for_playwright, get_proxy_for_httpx

SOURCE_NAME = "guardian"
MAX_ITEMS = 3
DRILL_DOWN_COUNT = 2
OUTPUT_DIR = sys.argv[1] if len(sys.argv) > 1 else "."

RSS_FEEDS = [
    ("world", "https://www.theguardian.com/world/rss"),
    ("business", "https://www.theguardian.com/uk/business/rss"),
    ("technology", "https://www.theguardian.com/uk/technology/rss"),
    ("science", "https://www.theguardian.com/science/rss"),
]

CATEGORY_MAP = {
    "world": "politics",
    "business": "economics",
    "technology": "technology",
    "science": "science",
}


def _step(timing, name, t_start):
    timing["steps"].append({"step": name, "seconds": round(time.monotonic() - t_start, 2)})


def _download_rss(url, timeout=15):
    import httpx
    kwargs = {"timeout": timeout}
    kwargs.update(get_proxy_for_httpx(url))
    r = httpx.get(url, **kwargs)
    r.raise_for_status()
    return feedparser.parse(r.text)


def _fetch_rss(timing):
    t = time.monotonic()
    seen_titles = set()
    items = []

    for category, url in RSS_FEEDS:
        try:
            feed = _download_rss(url)
            for entry in feed.entries[:MAX_ITEMS]:
                title = entry.get("title", "").strip()
                if not title or title.lower() in seen_titles:
                    continue
                seen_titles.add(title.lower())

                link = entry.get("link", "")
                published = entry.get("published", entry.get("updated", ""))
                summary = entry.get("summary", entry.get("description", ""))
                if summary:
                    import re
                    summary = re.sub(r"<[^>]+>", "", summary).strip()[:400]

                items.append({
                    "title": title,
                    "url": link,
                    "date": published,
                    "summary": summary,
                    "category": CATEGORY_MAP.get(category, category),
                    "points": [],
                    "_drill_down": False,
                })
        except Exception as e:
            print(f"  RSS feed {category} failed: {e}")

    _step(timing, "rss_fetch", t)
    return items


async def _drill_down(page, items, timing):
    drill_items = [it for it in items if it.get("url")][:DRILL_DOWN_COUNT]
    if not drill_items:
        return

    for idx, item in enumerate(drill_items):
        t = time.monotonic()
        try:
            await page.goto(item["url"], wait_until="domcontentloaded", timeout=20000)
            await page.wait_for_timeout(1500)

            paragraphs = await page.query_selector_all(
                "article p, .article-body-commercial-selector p, "
                "[data-gu-name='body'] p, .dcr-s2fvzr p, "
                "#maincontent p"
            )
            text_parts = []
            for pel in paragraphs[:10]:
                txt = (await pel.inner_text()).strip()
                if txt and len(txt) > 20:
                    text_parts.append(txt)

            if text_parts:
                item["summary"] = " ".join(text_parts)[:1200]
                item["points"] = [tp[:200] for tp in text_parts[:5]]
                item["_drill_down"] = True

                save_raw_content(
                    OUTPUT_DIR, SOURCE_NAME, idx, item["title"],
                    item["url"], item.get("date"),
                    text_parts,
                    difficulty="beginner",
                )
        except Exception as e:
            print(f"  Drill-down failed for {item['title'][:40]}: {e}")
        _step(timing, f"drill_down_{idx + 1}", t)


async def fetch():
    timing = {"source": SOURCE_NAME, "steps": []}
    t0 = time.monotonic()

    items = _fetch_rss(timing)
    print(f"  RSS: {len(items)} items from {len(RSS_FEEDS)} feeds")

    from playwright.async_api import async_playwright
    async with async_playwright() as p:
        proxy_arg = await get_proxy_for_playwright(p, "https://www.theguardian.com")
        browser = await p.chromium.launch(headless=True, **proxy_arg)
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            viewport={"width": 1280, "height": 900},
        )
        page = await context.new_page()
        await _drill_down(page, items, timing)
        await browser.close()

    drilled = sum(1 for it in items if it.get("_drill_down"))
    print(f"  Drill-down: {drilled}/{DRILL_DOWN_COUNT} articles")

    for it in items:
        it.pop("_drill_down", None)

    timing["total_seconds"] = round(time.monotonic() - t0, 2)
    result = {"source": SOURCE_NAME, "items": items, "_timing": timing}

    os.makedirs(OUTPUT_DIR, exist_ok=True)
    out_path = os.path.join(OUTPUT_DIR, f"{SOURCE_NAME}.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    print(f"[{SOURCE_NAME}] {len(items)} items, {timing['total_seconds']}s -> {out_path}")


async def safe_fetch():
    try:
        await fetch()
    except Exception as exc:
        error_msg = str(exc)[:200]
        print(f"[{SOURCE_NAME}] FATAL: {error_msg}")
        result = {
            "source": SOURCE_NAME, "items": [],
            "_timing": {"source": SOURCE_NAME, "steps": [], "total_seconds": 0},
            "_error": error_msg,
        }
        os.makedirs(OUTPUT_DIR, exist_ok=True)
        out_path = os.path.join(OUTPUT_DIR, f"{SOURCE_NAME}.json")
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False, indent=2)


if __name__ == "__main__":
    asyncio.run(safe_fetch())
