"""Scrape Census Bureau economic-indicator releases. RSS is often Cloudflare 403."""
from __future__ import annotations

import asyncio
import json
import os
import sys
import time

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(SCRIPT_DIR, ".."))
sys.path.insert(0, SCRIPT_DIR)
from playwright.async_api import async_playwright  # noqa: E402
from proxy_strategy import get_proxies_for_requests, get_proxy_for_playwright  # noqa: E402
from us_macro_parse import looks_like_captcha, looks_like_xml, parse_census_html  # noqa: E402

SOURCE_NAME = "census"
OUTPUT_DIR = sys.argv[1] if len(sys.argv) > 1 else "."
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
LIST_URL = "https://www.census.gov/economic-indicators/"
RSS_URLS = [
    "https://www.census.gov/economic-indicators/indicator.xml",
    "https://www.census.gov/economic-indicators/retail_sales.xml",
    "https://www.census.gov/economic-indicators/durable_goods.xml",
    "https://www.census.gov/economic-indicators/housing_starts.xml",
    "https://www.census.gov/economic-indicators/mfg_orders.xml",
    "https://www.census.gov/economic-indicators/intl_trade.xml",
]


def _get(url: str):
    import requests

    return requests.get(
        url,
        headers=HEADERS,
        timeout=20,
        proxies=get_proxies_for_requests(url),
    )


async def _playwright_html(url: str) -> str:
    async with async_playwright() as p:
        proxy_arg = await get_proxy_for_playwright(p, url)
        browser = await p.chromium.launch(headless=True, **proxy_arg)
        try:
            context = await browser.new_context(
                user_agent=HEADERS["User-Agent"],
                viewport={"width": 1280, "height": 900},
            )
            page = await context.new_page()
            await page.goto(url, wait_until="domcontentloaded", timeout=35000)
            await page.wait_for_timeout(2500)
            return await page.content()
        finally:
            await browser.close()


def _from_rss(body: str) -> list[dict]:
    try:
        import feedparser
    except ImportError:
        return []
    feed = feedparser.parse(body)
    items = []
    for entry in feed.entries[:12]:
        title = (entry.get("title") or "").strip()
        if not title:
            continue
        items.append({
            "title": title,
            "url": entry.get("link") or LIST_URL,
            "date": entry.get("published", entry.get("updated", "")),
            "summary": (entry.get("summary") or "")[:400],
            "category": "us-political",
            "points": [],
            "source": "Census Bureau",
        })
    return items


def fetch_items() -> list[dict]:
    items: list[dict] = []
    try:
        for url in RSS_URLS:
            try:
                resp = _get(url)
                if resp.ok and looks_like_xml(resp.text):
                    items.extend(_from_rss(resp.text))
                    if items:
                        break
                else:
                    break
            except Exception as e:
                print(f"  census RSS {url} failed: {e}")
                break
        html = ""
        if not items:
            try:
                resp = _get(LIST_URL)
                if resp.ok and not looks_like_captcha(resp.text):
                    html = resp.text
                else:
                    print(f"  census list HTTP {getattr(resp, 'status_code', '?')}")
            except Exception as e:
                print(f"  census list failed: {e}")
            if not html or looks_like_captcha(html):
                print("  census falling back to Playwright")
                html = asyncio.run(_playwright_html(LIST_URL))
            items = parse_census_html(html)
    except Exception as e:
        print(f"  census scrape failed: {e}")
    seen: set[str] = set()
    out = []
    for it in items:
        key = (it.get("title") or "").lower()[:80]
        if not key or key in seen:
            continue
        seen.add(key)
        out.append(it)
        if len(out) >= 12:
            break
    return out


def main():
    t0 = time.monotonic()
    print(f"[{SOURCE_NAME}] Fetching Census economic indicators...")
    items = fetch_items()
    timing = {
        "source": SOURCE_NAME,
        "steps": [{"step": "scrape", "seconds": round(time.monotonic() - t0, 2)}],
        "total_seconds": round(time.monotonic() - t0, 2),
    }
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    out_path = os.path.join(OUTPUT_DIR, f"{SOURCE_NAME}.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump({"source": SOURCE_NAME, "items": items, "_timing": timing}, f,
                  ensure_ascii=False, indent=2)
    print(f"[{SOURCE_NAME}] {len(items)} items, {timing['total_seconds']}s -> {out_path}")


if __name__ == "__main__":
    main()
