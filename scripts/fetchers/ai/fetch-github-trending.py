"""
Fetch daily trending repositories from GitHub.

Extracts the repo table (name, description, stars, language) directly
from the listing page. No drill-down needed — all info is in the DOM.
Scrolls 1-2x to ensure lazy-loaded content is visible.

Usage: python fetch-github-trending.py [output-dir]
Output: <output-dir>/github-trending.json
"""
import asyncio
import json
import os
import re
import sys
import time
from playwright.async_api import async_playwright

PROXY = os.environ.get("BRIEFING_PROXY")

SOURCE_NAME = "github-trending"
SOURCE_URL = "https://github.com/trending?since=daily"
MAX_ITEMS = 15
OUTPUT_DIR = sys.argv[1] if len(sys.argv) > 1 else "."


def _step(timing, name, t_start):
    timing["steps"].append({"step": name, "seconds": round(time.monotonic() - t_start, 2)})


async def fetch():
    timing = {"source": SOURCE_NAME, "steps": []}
    t0 = time.monotonic()

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True, proxy={"server": PROXY} if PROXY else None)
        page = await browser.new_page(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
        )

        t = time.monotonic()
        await page.goto(SOURCE_URL, wait_until="domcontentloaded", timeout=20000)
        await page.wait_for_timeout(1500)
        _step(timing, "navigate", t)

        t = time.monotonic()
        for _ in range(2):
            await page.evaluate("window.scrollBy(0, 800)")
            await page.wait_for_timeout(800)
        _step(timing, "scroll", t)

        t = time.monotonic()
        repos = []

        row_els = await page.query_selector_all("article.Box-row, [class*='Box-row']")
        if not row_els:
            row_els = await page.query_selector_all("div.Box article, .explore-content article")

        for el in row_els[:MAX_ITEMS]:
            try:
                name_el = await el.query_selector("h2 a, h1 a")
                if not name_el:
                    continue
                raw_name = (await name_el.inner_text()).strip()
                repo_name = re.sub(r"\s+", "", raw_name).strip()

                desc_el = await el.query_selector("p")
                description = (await desc_el.inner_text()).strip() if desc_el else ""

                stars_text = ""
                star_els = await el.query_selector_all("a[href*='/stargazers'], span.d-inline-block")
                for sel in star_els:
                    txt = (await sel.inner_text()).strip()
                    if any(c.isdigit() for c in txt):
                        stars_text = txt.strip()
                        break

                lang_el = await el.query_selector("[itemprop='programmingLanguage'], span[class*='repo-language-color'] + span")
                language = (await lang_el.inner_text()).strip() if lang_el else ""

                today_el = await el.query_selector("span.d-inline-block.float-sm-right, span[class*='stars-today']")
                today_stars = ""
                if today_el:
                    today_stars = (await today_el.inner_text()).strip()

                repos.append({
                    "name": repo_name,
                    "description": description[:200],
                    "stars": stars_text,
                    "today_stars": today_stars,
                    "language": language,
                })
            except Exception:
                continue

        _step(timing, "extract", t)
        await browser.close()

    items = []
    for repo in repos:
        items.append({
            "title": repo["name"],
            "url": f"https://github.com/{repo['name']}",
            "date": None,
            "summary": repo["description"],
            "points": [],
            "stars": repo["stars"],
            "today_stars": repo["today_stars"],
            "language": repo["language"],
        })

    timing["total_seconds"] = round(time.monotonic() - t0, 2)
    result = {"source": SOURCE_NAME, "items": items, "_timing": timing}

    os.makedirs(OUTPUT_DIR, exist_ok=True)
    out_path = os.path.join(OUTPUT_DIR, f"{SOURCE_NAME}.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    print(f"[{SOURCE_NAME}] {len(items)} repos, {timing['total_seconds']}s -> {out_path}")


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
