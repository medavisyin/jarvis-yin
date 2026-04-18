"""
Fetch recent posts from the Google DeepMind Blog.

Blog is visually rich with interactive charts — text extraction notes
"[See visual data in original post]" when content references figures.

Usage: python fetch-deepmind.py [output-dir]
Output: <output-dir>/deepmind.json
"""
import asyncio
import json
import os
import sys
import time
from playwright.async_api import async_playwright

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(SCRIPT_DIR, "..", ".."))
from raw_saver import save_raw_content, should_save_raw

PROXY = os.environ.get("BRIEFING_PROXY")

SOURCE_NAME = "deepmind"
SOURCE_URL = "https://deepmind.google/blog/"
MAX_ITEMS = 5
DRILL_DOWN_COUNT = 3
OUTPUT_DIR = sys.argv[1] if len(sys.argv) > 1 else "."


def _step(timing, name, t_start):
    timing["steps"].append({"step": name, "seconds": round(time.monotonic() - t_start, 2)})


async def fetch():
    timing = {"source": SOURCE_NAME, "steps": []}
    t0 = time.monotonic()

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True, proxy={"server": PROXY} if PROXY else None)
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
            viewport={"width": 1280, "height": 900},
        )
        page = await context.new_page()

        t = time.monotonic()
        await page.goto(SOURCE_URL, wait_until="domcontentloaded", timeout=45000)
        await page.wait_for_timeout(2000)
        _step(timing, "navigate", t)

        t = time.monotonic()
        posts = []

        card_els = await page.query_selector_all("a[href*='/blog/']")
        if not card_els:
            card_els = await page.query_selector_all("[class*='card'] a, article a")

        seen_urls = set()
        for el in card_els:
            if len(posts) >= MAX_ITEMS:
                break
            try:
                href = await el.get_attribute("href")
                if not href:
                    continue
                href = href.strip().replace("\n", "").replace(" ", "")
                if href in seen_urls or href.rstrip("/") == "/blog":
                    continue
                seen_urls.add(href)

                url = href if href.startswith("http") else f"https://deepmind.google{href}"

                title_el = await el.query_selector("h3, h2, [class*='title']")
                raw_text = (await title_el.inner_text()).strip() if title_el else (await el.inner_text()).strip()
                # DeepMind cards concatenate title + subtitle; take first line
                title = raw_text.split("\n")[0].strip() if "\n" in raw_text else raw_text
                if not title or len(title) < 5:
                    continue

                date_el = await el.query_selector("time, [class*='date'], span[class*='date']")
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
                    await page.wait_for_timeout(1500)

                    paragraphs = await page.query_selector_all("article p, main p, [class*='content'] p")
                    text_parts = []
                    for pel in paragraphs[:6]:
                        text_parts.append((await pel.inner_text()).strip())
                    if text_parts:
                        figures = await page.query_selector_all("figure, [class*='chart'], [class*='interactive']")
                        extra_notes = (
                            ["[See visual data in original post]"] if figures else None
                        )
                        save_raw_content(
                            OUTPUT_DIR, SOURCE_NAME, idx, item["title"],
                            item.get("url", post.get("url", "")), item.get("date"),
                            text_parts,
                            difficulty="intermediate",
                            extra_notes=extra_notes,
                        )
                        summary = " ".join(text_parts)[:800]
                        item["summary"] = summary
                        if figures:
                            item["points"].append("[See visual data in original post]")
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
