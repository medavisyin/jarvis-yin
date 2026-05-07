"""
Fetch recent posts from the OpenAI Developer Blog.

Known to have Cloudflare protection — uses a realistic user-agent and
waits for content to render. Falls back gracefully if blocked.

Usage: python fetch-openai-blog.py [output-dir]
Output: <output-dir>/openai-blog.json
"""
import asyncio
import json
import os
import re
import sys
import time
from playwright.async_api import async_playwright

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(SCRIPT_DIR, "..", ".."))
sys.path.insert(0, os.path.join(SCRIPT_DIR, ".."))
from raw_saver import save_raw_content, should_save_raw
from proxy_strategy import get_proxy_for_playwright

SOURCE_NAME = "openai-blog"
SOURCE_URL = "https://openai.com/news/"
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
        resp = await page.goto(SOURCE_URL, wait_until="domcontentloaded", timeout=30000)
        await page.wait_for_timeout(4000)
        _step(timing, "navigate", t)

        # Detect Cloudflare block
        page_title = await page.title()
        if resp and resp.status == 403 or "forbidden" in page_title.lower() or "just a moment" in page_title.lower():
            print(f"[{SOURCE_NAME}] Cloudflare blocked (status={resp.status if resp else 'N/A'}, title={page_title})")
            await browser.close()
            timing["total_seconds"] = round(time.monotonic() - t0, 2)
            timing["steps"].append({"step": "cloudflare_blocked", "seconds": 0})
            result = {"source": SOURCE_NAME, "items": [], "_timing": timing, "_error": "Cloudflare blocked"}
            os.makedirs(OUTPUT_DIR, exist_ok=True)
            out_path = os.path.join(OUTPUT_DIR, f"{SOURCE_NAME}.json")
            with open(out_path, "w", encoding="utf-8") as f:
                json.dump(result, f, ensure_ascii=False, indent=2)
            print(f"[{SOURCE_NAME}] 0 items (blocked), {timing['total_seconds']}s -> {out_path}")
            return

        t = time.monotonic()
        posts = []

        # openai.com/news/ uses links to /index/... for articles
        link_els = await page.query_selector_all("a[href*='/index/']")
        if not link_els:
            link_els = await page.query_selector_all("article a, [class*='post'] a")

        seen_urls = set()
        for el in link_els:
            if len(posts) >= MAX_ITEMS:
                break
            try:
                href = await el.get_attribute("href")
                if not href or href in seen_urls:
                    continue
                seen_urls.add(href)

                url = href if href.startswith("http") else f"https://openai.com{href}"
                raw_text = (await el.inner_text()).strip()
                if not raw_text or len(raw_text) < 10:
                    continue

                # Text format: "TitleCategoryDate" — extract title (first meaningful part)
                title = raw_text.split("\n")[0].strip() if "\n" in raw_text else raw_text
                date_match = re.search(r"(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+\d{1,2}(?:,\s*\d{4})?", raw_text)
                date_text = date_match.group(0) if date_match else None

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
                    await page.wait_for_timeout(3000)

                    paragraphs = await page.query_selector_all("article p, main p, [class*='content'] p")
                    text_parts = []
                    for pel in paragraphs[:5]:
                        text_parts.append((await pel.inner_text()).strip())
                    if text_parts:
                        save_raw_content(
                            OUTPUT_DIR, SOURCE_NAME, idx, item["title"],
                            item.get("url", post.get("url", "")), item.get("date"),
                            text_parts,
                            difficulty="intermediate",
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
