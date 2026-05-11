"""
Fetch recent AI articles from VentureBeat.

VentureBeat publishes daily AI industry news with accessible summaries.
Good for enterprise AI, model launches, and market analysis.

Usage: python fetch-venturebeat.py [output-dir]
Output: <output-dir>/venturebeat.json
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

SOURCE_NAME = "venturebeat"
SOURCE_URL = "https://venturebeat.com/category/ai/"
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
        await page.wait_for_timeout(3000)
        _step(timing, "navigate", t)

        t = time.monotonic()
        posts = []

        article_els = await page.query_selector_all("article")
        if not article_els:
            article_els = await page.query_selector_all("[class*='ArticleListing'] a, h2 a")

        seen_urls = set()
        for el in article_els[:MAX_ITEMS * 2]:
            if len(posts) >= MAX_ITEMS:
                break
            try:
                title_el = await el.query_selector("h2 a, h3 a, [class*='title'] a")
                if not title_el:
                    link = await el.query_selector("a")
                    title_el = link if link else el
                if not title_el:
                    continue

                title = (await title_el.inner_text()).strip()
                href = await title_el.get_attribute("href")
                if not title or len(title) < 10 or not href:
                    continue
                if href in seen_urls:
                    continue
                seen_urls.add(href)

                url = href if href.startswith("http") else f"https://venturebeat.com{href}"

                date_el = await el.query_selector("time, [class*='date']")
                date_text = None
                if date_el:
                    date_text = (await date_el.get_attribute("datetime")) or (await date_el.inner_text()).strip()

                posts.append({"title": title, "url": url, "date": date_text})
            except Exception:
                continue

        _step(timing, "extract_headlines", t)

        items = []
        for idx, post in enumerate(posts):
            item = {
                "title": post["title"],
                "url": post.get("url", ""),
                "date": post.get("date"),
                "summary": None,
                "points": [],
            }

            if idx < DRILL_DOWN_COUNT and post.get("url"):
                t = time.monotonic()
                try:
                    await page.goto(post["url"], wait_until="domcontentloaded", timeout=20000)
                    await page.wait_for_timeout(2000)

                    selectors = [
                        ".article-content p",
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
