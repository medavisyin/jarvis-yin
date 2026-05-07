"""
Fetch top world news from AP News via Playwright scraping + drill-down.

AP News doesn't provide reliable public RSS feeds, so this script
scrapes the website directly using Playwright.

Usage: python fetch-ap-news.py [output-dir]
Output: <output-dir>/ap-news.json
"""
import asyncio
import json
import os
import sys
import time

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(SCRIPT_DIR, "..", ".."))
from raw_saver import save_raw_content

sys.path.insert(0, os.path.join(SCRIPT_DIR, ".."))
from proxy_strategy import get_proxy_for_playwright

SOURCE_NAME = "ap-news"
MAX_ITEMS = 3
DRILL_DOWN_COUNT = 2
OUTPUT_DIR = sys.argv[1] if len(sys.argv) > 1 else "."

WEBSITE_SECTIONS = [
    ("world", "https://apnews.com/world-news"),
    ("politics", "https://apnews.com/politics"),
    ("business", "https://apnews.com/business"),
    ("technology", "https://apnews.com/technology"),
    ("science", "https://apnews.com/science"),
]

CATEGORY_MAP = {
    "world": "politics",
    "politics": "politics",
    "business": "economics",
    "technology": "technology",
    "science": "science",
}


def _step(timing, name, t_start):
    timing["steps"].append({"step": name, "seconds": round(time.monotonic() - t_start, 2)})


async def _scrape_section(page, section_url, category, max_items):
    """Scrape an AP News section page for headlines."""
    items = []
    try:
        await page.goto(section_url, wait_until="domcontentloaded", timeout=20000)
        await page.wait_for_timeout(2000)

        links = await page.query_selector_all(
            "a[href*='/article/'], .PageList-items-item a, "
            "[class*='PagePromo'] a, h2 a, h3 a, "
            "bsp-custom-headline a, [data-key='card-headline'] a"
        )

        seen = set()
        for link_el in links:
            if len(items) >= max_items:
                break
            try:
                href = await link_el.get_attribute("href")
                text = (await link_el.inner_text()).strip()

                if not text or len(text) < 15 or len(text) > 300:
                    continue
                if not href:
                    continue
                if any(skip in text.lower() for skip in [
                    "sign up", "subscribe", "newsletter", "advertisement",
                    "cookie", "privacy", "terms"
                ]):
                    continue
                if text.lower() in seen:
                    continue

                url = href if href.startswith("http") else f"https://apnews.com{href}"
                if "/article/" not in url and "/hub/" not in url:
                    continue

                seen.add(text.lower())
                items.append({
                    "title": text,
                    "url": url,
                    "date": "",
                    "summary": "",
                    "category": CATEGORY_MAP.get(category, category),
                    "points": [],
                    "_drill_down": False,
                })
            except Exception:
                continue
    except Exception as e:
        print(f"  AP section {category} failed: {e}")

    return items


async def fetch():
    timing = {"source": SOURCE_NAME, "steps": []}
    t0 = time.monotonic()

    from playwright.async_api import async_playwright

    all_items = []
    seen_titles = set()

    async with async_playwright() as p:
        proxy_arg = await get_proxy_for_playwright(p, "https://apnews.com")
        browser = await p.chromium.launch(headless=True, **proxy_arg)
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            viewport={"width": 1280, "height": 900},
        )
        page = await context.new_page()

        t = time.monotonic()
        for category, url in WEBSITE_SECTIONS:
            section_items = await _scrape_section(page, url, category, MAX_ITEMS)
            for item in section_items:
                key = item["title"].lower()
                if key not in seen_titles:
                    seen_titles.add(key)
                    all_items.append(item)
        _step(timing, "scrape_sections", t)

        print(f"  Scraped: {len(all_items)} items from {len(WEBSITE_SECTIONS)} sections")

        drill_items = [it for it in all_items if it.get("url")][:DRILL_DOWN_COUNT]
        for idx, item in enumerate(drill_items):
            t = time.monotonic()
            try:
                await page.goto(item["url"], wait_until="domcontentloaded", timeout=20000)
                await page.wait_for_timeout(1500)

                paragraphs = await page.query_selector_all(
                    "article p, .RichTextStoryBody p, [class*='Article'] p, "
                    "[data-key] p, .article-body p"
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

        drilled = sum(1 for it in all_items if it.get("_drill_down"))
        print(f"  Drill-down: {drilled}/{DRILL_DOWN_COUNT} articles")

        await browser.close()

    for it in all_items:
        it.pop("_drill_down", None)

    timing["total_seconds"] = round(time.monotonic() - t0, 2)
    result = {"source": SOURCE_NAME, "items": all_items, "_timing": timing}

    os.makedirs(OUTPUT_DIR, exist_ok=True)
    out_path = os.path.join(OUTPUT_DIR, f"{SOURCE_NAME}.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    print(f"[{SOURCE_NAME}] {len(all_items)} items, {timing['total_seconds']}s -> {out_path}")


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
