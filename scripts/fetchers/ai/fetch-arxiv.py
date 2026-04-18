"""
Fetch recent AI papers from Arxiv cs.AI.

Arxiv is static HTML — Playwright loads fast with no JS wait needed.
Extracts paper titles, authors, dates, and abstract links.

Usage: python fetch-arxiv.py [output-dir]
Output: <output-dir>/arxiv.json
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

SOURCE_NAME = "arxiv"
SOURCE_URL = "https://arxiv.org/list/cs.AI/recent"
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
        page = await browser.new_page()

        t = time.monotonic()
        await page.goto(SOURCE_URL, wait_until="domcontentloaded", timeout=20000)
        _step(timing, "navigate", t)

        t = time.monotonic()
        papers = []

        dt_elements = await page.query_selector_all("dt")
        dd_elements = await page.query_selector_all("dd")

        count = min(len(dt_elements), len(dd_elements), MAX_ITEMS * 2)

        for i in range(min(count, MAX_ITEMS)):
            try:
                dt = dt_elements[i]
                dd = dd_elements[i]

                link_el = await dt.query_selector("a[href*='/abs/']")
                href = await link_el.get_attribute("href") if link_el else None
                paper_url = f"https://arxiv.org{href}" if href and href.startswith("/") else href

                title_el = await dd.query_selector(".list-title")
                title_text = (await title_el.inner_text()).strip() if title_el else ""
                title_text = title_text.replace("Title:", "").strip()

                author_el = await dd.query_selector(".list-authors")
                authors = (await author_el.inner_text()).strip() if author_el else ""
                authors = authors.replace("Authors:", "").strip()

                papers.append({
                    "title": title_text,
                    "authors": authors,
                    "url": paper_url,
                })
            except Exception:
                continue

        _step(timing, "extract_headlines", t)

        items = []
        for idx, paper in enumerate(papers):
            item = {
                "title": paper["title"],
                "url": paper.get("url", ""),
                "date": None,
                "summary": None,
                "points": [],
                "authors": paper.get("authors", ""),
            }

            if idx < DRILL_DOWN_COUNT and paper.get("url"):
                t = time.monotonic()
                try:
                    await page.goto(paper["url"], wait_until="domcontentloaded", timeout=15000)
                    abstract_el = await page.query_selector(".abstract")
                    full_abstract = ""
                    if abstract_el:
                        text = (await abstract_el.inner_text()).strip()
                        text = text.replace("Abstract:", "").strip()
                        full_abstract = text
                        item["summary"] = text[:800]

                    date_el = await page.query_selector(".dateline")
                    if date_el:
                        item["date"] = (await date_el.inner_text()).strip()

                    if full_abstract:
                        save_raw_content(
                            OUTPUT_DIR, SOURCE_NAME, idx, paper["title"],
                            paper["url"], item.get("date"),
                            [full_abstract], difficulty="advanced",
                        )
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
