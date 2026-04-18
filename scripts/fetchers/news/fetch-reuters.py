"""
Fetch top world news from Reuters via RSS (preferred) or Playwright scraping.

Tries RSS feeds first (fast, no anti-bot issues). Falls back to Playwright
scraping if RSS feeds are unavailable or return no items.

Usage: python fetch-reuters.py [output-dir]
Output: <output-dir>/reuters.json
"""
import asyncio
import json
import os
import sys
import time

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(SCRIPT_DIR, "..", ".."))
from raw_saver import save_raw_content

PROXY = os.environ.get("BRIEFING_PROXY")

SOURCE_NAME = "reuters"
MAX_ITEMS = 3
DRILL_DOWN_COUNT = 2
OUTPUT_DIR = sys.argv[1] if len(sys.argv) > 1 else "."

RSS_FEEDS = [
    ("world", "https://www.reuters.com/arc/outboundfeeds/newsletter-rss/world/"),
    ("business", "https://www.reuters.com/arc/outboundfeeds/newsletter-rss/business/"),
    ("technology", "https://www.reuters.com/arc/outboundfeeds/newsletter-rss/technology/"),
    ("science", "https://www.reuters.com/arc/outboundfeeds/newsletter-rss/science/"),
]

WEBSITE_SECTIONS = [
    ("world", "https://www.reuters.com/world/"),
    ("business", "https://www.reuters.com/business/"),
    ("technology", "https://www.reuters.com/technology/"),
    ("science", "https://www.reuters.com/science/"),
]

CATEGORY_MAP = {
    "world": "politics",
    "business": "economics",
    "technology": "technology",
    "science": "science",
}


def _step(timing, name, t_start):
    timing["steps"].append({"step": name, "seconds": round(time.monotonic() - t_start, 2)})


def _try_rss(timing):
    """Try RSS feeds first — fast and avoids anti-bot protection."""
    t = time.monotonic()
    items = []
    seen_titles = set()

    try:
        import feedparser
        import httpx
    except ImportError:
        print("  RSS dependencies not available, skipping RSS approach")
        _step(timing, "rss_attempt", t)
        return items

    for category, url in RSS_FEEDS:
        try:
            kwargs = {"timeout": 10}
            if PROXY:
                kwargs["proxy"] = PROXY
            r = httpx.get(url, **kwargs)
            r.raise_for_status()
            feed = feedparser.parse(r.text)
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

    _step(timing, "rss_attempt", t)
    if items:
        print(f"  RSS: {len(items)} items from {len(RSS_FEEDS)} feeds")
    else:
        print("  RSS: no items found, will try Playwright scraping")
    return items


async def _scrape_section(page, section_url, category, max_items):
    """Scrape a Reuters section page for headlines."""
    items = []
    try:
        await page.goto(section_url, wait_until="networkidle", timeout=25000)
        await page.wait_for_timeout(3000)

        headline_els = await page.query_selector_all(
            "[data-testid='Heading'] a, "
            "[class*='story-card'] a, "
            "[class*='media-story-card'] a, "
            "h3 a, h2 a, "
            "a[data-testid='Link'], "
            "a[href*='/world/'], a[href*='/business/'], "
            "a[href*='/technology/'], a[href*='/science/'], "
            "a[href*='/markets/']"
        )

        seen = set()
        for link_el in headline_els:
            if len(items) >= max_items:
                break
            try:
                href = await link_el.get_attribute("href")
                text = (await link_el.inner_text()).strip()

                if not text or len(text) < 15 or len(text) > 300:
                    continue
                if not href:
                    continue
                if "/video/" in href or "/pictures/" in href or "/graphics/" in href:
                    continue
                if any(skip in text.lower() for skip in [
                    "sign up", "subscribe", "newsletter", "advertisement",
                    "cookie", "privacy", "more from reuters"
                ]):
                    continue
                if text.lower() in seen:
                    continue

                url = href if href.startswith("http") else f"https://www.reuters.com{href}"

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
        print(f"  Reuters section {category} failed: {e}")

    return items


async def _drill_down_article(page, item, idx, timing):
    """Fetch full article content for a single item."""
    t = time.monotonic()
    try:
        await page.goto(item["url"], wait_until="domcontentloaded", timeout=20000)
        await page.wait_for_timeout(2000)

        paragraphs = await page.query_selector_all(
            "article p, [data-testid='paragraph-'] p, .article-body__content p, "
            "[class*='ArticleBody'] p, [class*='article-body'] p"
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

    all_items = _try_rss(timing)

    from playwright.async_api import async_playwright

    if not all_items:
        seen_titles = set()
        async with async_playwright() as p:
            browser = await p.chromium.launch(
                headless=True,
                proxy={"server": PROXY} if PROXY else None,
            )
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
                await _drill_down_article(page, item, idx, timing)

            drilled = sum(1 for it in all_items if it.get("_drill_down"))
            print(f"  Drill-down: {drilled}/{DRILL_DOWN_COUNT} articles")

            await browser.close()
    else:
        async with async_playwright() as p:
            browser = await p.chromium.launch(
                headless=True,
                proxy={"server": PROXY} if PROXY else None,
            )
            context = await browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                viewport={"width": 1280, "height": 900},
            )
            page = await context.new_page()
            drill_items = [it for it in all_items if it.get("url")][:DRILL_DOWN_COUNT]
            for idx, item in enumerate(drill_items):
                await _drill_down_article(page, item, idx, timing)
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
