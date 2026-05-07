"""
Fetch recent AI articles from MIT Technology Review.

Server-rendered page — Playwright loads fast. Extracts article
listings from the AI topic page.

Usage: python fetch-mit-review.py [output-dir]
Output: <output-dir>/mit-review.json
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
from proxy_strategy import get_proxy_for_playwright

from raw_saver import save_raw_content, should_save_raw

SOURCE_NAME = "mit-review"
SOURCE_URL = "https://www.technologyreview.com/topic/artificial-intelligence/"
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
        await page.goto(SOURCE_URL, wait_until="domcontentloaded", timeout=25000)
        await page.wait_for_timeout(2000)
        _step(timing, "navigate", t)

        t = time.monotonic()
        posts = []

        # MIT Tech Review uses h3 with homepageStoryCard__hed class for article titles
        h3_els = await page.query_selector_all("h3[class*='homepageStoryCard__hed']")
        if not h3_els:
            h3_els = await page.query_selector_all("h3[class*='hed'], h3[class*='card']")

        for h3 in h3_els[:MAX_ITEMS]:
            try:
                # The h3 text is the title; find the parent link
                title = (await h3.inner_text()).strip()
                if not title or len(title) < 5 or title.startswith("Advertise"):
                    continue

                parent_link = await h3.evaluate_handle("el => el.closest('a') || el.parentElement.querySelector('a')")
                href = await parent_link.evaluate("el => el ? el.href : null") if parent_link else None
                url = href if href and href.startswith("http") else None

                # Try to find date from sibling/parent elements
                card = await h3.evaluate_handle("el => el.closest('[class*=Card]') || el.parentElement")
                date_text = None
                if card:
                    date_el = await card.evaluate("el => { const t = el.querySelector('time'); return t ? (t.getAttribute('datetime') || t.textContent.trim()) : null; }")
                    date_text = date_el

                posts.append({"title": title, "url": url, "date": date_text, "author": None})
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
                "author": post.get("author"),
            }

            if idx < DRILL_DOWN_COUNT and post.get("url"):
                t = time.monotonic()
                try:
                    await page.goto(post["url"], wait_until="domcontentloaded", timeout=20000)
                    await page.wait_for_timeout(1500)

                    paragraphs = await page.query_selector_all("article p, [class*='body'] p, main p")
                    text_parts = []
                    for pel in paragraphs[:6]:
                        text_parts.append((await pel.inner_text()).strip())
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
    """Wrapper that catches all errors and writes an empty result file."""
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
