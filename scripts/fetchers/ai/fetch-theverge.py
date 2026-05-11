"""
Fetch recent AI articles from The Verge.

The Verge covers consumer-oriented AI news with accessible, engaging writing.
Good for product launches, AI in everyday life, and tech industry context.

Usage: python fetch-theverge.py [output-dir]
Output: <output-dir>/theverge.json
"""
import asyncio
import json
import os
import sys
import time
from playwright.async_api import async_playwright

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(SCRIPT_DIR, "..", ".."))
sys.path.insert(0, os.path.join(SCRIPT_DIR, ".."))
from raw_saver import save_raw_content, should_save_raw
from proxy_strategy import get_proxy_for_playwright

SOURCE_NAME = "theverge"
SOURCE_URL = "https://www.theverge.com/ai-artificial-intelligence"
MAX_ITEMS = 5
DRILL_DOWN_COUNT = 3
OUTPUT_DIR = sys.argv[1] if len(sys.argv) > 1 else "."


def _step(timing, name, t_start):
    timing["steps"].append({"step": name, "seconds": round(time.monotonic() - t_start, 2)})


async def fetch():
    timing = {"source": SOURCE_NAME, "steps": []}
    t0 = time.monotonic()

    async with async_playwright() as p:
        proxy_arg = await get_proxy_for_playwright(p, SOURCE_URL)
        browser = await p.chromium.launch(headless=True, **proxy_arg)
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
            viewport={"width": 1280, "height": 900},
        )
        page = await context.new_page()

        t = time.monotonic()
        await page.goto(SOURCE_URL, wait_until="domcontentloaded", timeout=30000)
        await page.wait_for_timeout(2000)
        _step(timing, "navigate", t)

        t = time.monotonic()
        posts = []

        link_els = await page.query_selector_all("a[data-analytics-link='article']")
        if not link_els:
            link_els = await page.query_selector_all("h2 a, [class*='duet--content-cards'] a")
        if not link_els:
            link_els = await page.query_selector_all("article a, [class*='river'] a")

        seen_urls = set()
        for el in link_els:
            if len(posts) >= MAX_ITEMS:
                break
            try:
                href = await el.get_attribute("href")
                if not href or href in seen_urls:
                    continue

                url = href if href.startswith("http") else f"https://www.theverge.com{href}"
                if "/ai-artificial-intelligence" in url and url.count("/") < 5:
                    continue

                seen_urls.add(href)
                title = (await el.inner_text()).strip()
                title_el = await el.query_selector("h2, h3, [class*='title']")
                if title_el:
                    title = (await title_el.inner_text()).strip()
                if not title or len(title) < 10:
                    continue

                posts.append({"title": title, "url": url})
            except Exception:
                continue

        _step(timing, "extract_headlines", t)

        items = []
        for idx, post in enumerate(posts):
            item = {
                "title": post["title"],
                "url": post.get("url", ""),
                "date": None,
                "summary": None,
                "points": [],
            }

            if idx < DRILL_DOWN_COUNT and post.get("url"):
                t = time.monotonic()
                try:
                    await page.goto(post["url"], wait_until="domcontentloaded", timeout=20000)
                    await page.wait_for_timeout(2000)

                    selectors = [
                        "[class*='article-body'] p",
                        ".entry-content p",
                        "article p",
                        "main p",
                    ]
                    text_parts = []
                    for sel in selectors:
                        paragraphs = await page.query_selector_all(sel)
                        for pel in paragraphs[:6]:
                            txt = (await pel.inner_text()).strip()
                            if txt and len(txt) > 40:
                                text_parts.append(txt)
                        if text_parts:
                            break

                    if text_parts:
                        save_raw_content(
                            OUTPUT_DIR, SOURCE_NAME, idx, item["title"],
                            item.get("url", post.get("url", "")), item.get("date"),
                            text_parts,
                            difficulty="beginner",
                            extra_notes=item.get("points"),
                        )
                        item["summary"] = " ".join(text_parts)[:800]

                    date_el = await page.query_selector("time, [class*='date']")
                    if date_el:
                        item["date"] = (await date_el.get_attribute("datetime")) or (await date_el.inner_text()).strip()
                except Exception:
                    pass
                _step(timing, f"drill_down_{idx + 1}", t)

            items.append(item)

        await browser.close()

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
        result = {"source": SOURCE_NAME, "items": [], "_timing": {"source": SOURCE_NAME, "steps": [], "total_seconds": 0}, "_error": error_msg}
        os.makedirs(OUTPUT_DIR, exist_ok=True)
        out_path = os.path.join(OUTPUT_DIR, f"{SOURCE_NAME}.json")
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False, indent=2)


if __name__ == "__main__":
    asyncio.run(safe_fetch())
