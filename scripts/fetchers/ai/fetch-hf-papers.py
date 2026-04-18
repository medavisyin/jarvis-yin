"""
Fetch trending papers from Hugging Face.

Navigates to the trending papers page, scrolls to load more via infinite scroll,
extracts top papers by upvotes, then drills into the top 3 for full abstracts.

Usage: python fetch-hf-papers.py [output-dir]
Output: <output-dir>/hf-papers.json
"""
import asyncio
import json
import os
import re
import sys
import time
from playwright.async_api import async_playwright

SOURCE_NAME = "hf-papers"
SOURCE_URL = "https://huggingface.co/papers/trending"
MAX_ITEMS = 8
DRILL_DOWN_COUNT = 3
OUTPUT_DIR = sys.argv[1] if len(sys.argv) > 1 else "."


def _step(timing, name, t_start):
    timing["steps"].append({"step": name, "seconds": round(time.monotonic() - t_start, 2)})


async def fetch():
    timing = {"source": SOURCE_NAME, "steps": []}
    t0 = time.monotonic()

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
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
        for i in range(4):
            await page.evaluate("window.scrollBy(0, 2000)")
            await page.wait_for_timeout(1500)
        _step(timing, "scroll", t)

        t = time.monotonic()
        papers = []
        article_els = await page.query_selector_all("article")
        if not article_els:
            article_els = await page.query_selector_all("[class*='paper']")

        for el in article_els:
            try:
                title_el = await el.query_selector("h3") or await el.query_selector("a[href*='/papers/']")
                title = (await title_el.inner_text()).strip() if title_el else None
                if not title:
                    continue

                link_el = await el.query_selector("a[href*='/papers/']")
                href = await link_el.get_attribute("href") if link_el else None
                url = f"https://huggingface.co{href}" if href and href.startswith("/") else href

                upvote_el = await el.query_selector("[class*='upvote'], [class*='like'], button svg")
                upvotes_text = ""
                if upvote_el:
                    parent = await upvote_el.evaluate_handle("el => el.closest('button') || el.parentElement")
                    upvotes_text = await parent.evaluate("el => el.textContent") if parent else ""
                upvotes = 0
                nums = re.findall(r"\d+", upvotes_text or "")
                if nums:
                    upvotes = int(nums[0])

                papers.append({"title": title, "url": url, "upvotes": upvotes})
            except Exception:
                continue

        papers.sort(key=lambda x: x["upvotes"], reverse=True)
        papers = papers[:MAX_ITEMS]
        _step(timing, "extract_headlines", t)

        items = []
        for idx, paper in enumerate(papers):
            item = {
                "title": paper["title"],
                "url": paper.get("url", ""),
                "upvotes": paper["upvotes"],
                "date": None,
                "summary": None,
                "points": [],
            }

            if idx < DRILL_DOWN_COUNT and paper.get("url"):
                t = time.monotonic()
                try:
                    await page.goto(paper["url"], wait_until="domcontentloaded", timeout=20000)
                    await page.wait_for_timeout(1500)

                    abstract_el = (
                        await page.query_selector("[class*='abstract']")
                        or await page.query_selector("p.text-gray-700")
                        or await page.query_selector("main p")
                    )
                    if abstract_el:
                        item["summary"] = (await abstract_el.inner_text()).strip()[:800]

                    date_el = await page.query_selector("time") or await page.query_selector("[datetime]")
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
