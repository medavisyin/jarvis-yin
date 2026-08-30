"""Scrape ISM Manufacturing and Services PMI monthly reports."""
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
from us_macro_parse import (  # noqa: E402
    ism_report_urls,
    looks_like_captcha,
    parse_ism_report_html,
    playwright_ism_urls,
)

SOURCE_NAME = "ism"
OUTPUT_DIR = sys.argv[1] if len(sys.argv) > 1 else "."
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}


def _requests_html(url: str) -> str | None:
    """Return HTML, empty string to skip, or None to try Playwright."""
    import requests

    try:
        resp = requests.get(
            url,
            headers=HEADERS,
            timeout=20,
            proxies=get_proxies_for_requests(url),
        )
        if resp.status_code == 404:
            print(f"  ism HTTP 404 {url}")
            return ""
        if resp.ok and not looks_like_captcha(resp.text) and len(resp.text) > 2000:
            return resp.text
        print(f"  ism HTTP {resp.status_code}, queue Playwright {url}")
        return None
    except Exception as e:
        print(f"  ism requests failed {url}: {e}")
        return None


async def _playwright_pages(urls: list[str]) -> dict[str, str]:
    out: dict[str, str] = {}
    if not urls:
        return out
    async with async_playwright() as p:
        proxy_arg = await get_proxy_for_playwright(p, urls[0])
        browser = await p.chromium.launch(headless=True, **proxy_arg)
        try:
            context = await browser.new_context(
                user_agent=HEADERS["User-Agent"],
                viewport={"width": 1280, "height": 900},
            )
            page = await context.new_page()
            for url in urls:
                try:
                    await page.goto(url, wait_until="domcontentloaded", timeout=35000)
                    await page.wait_for_timeout(2000)
                    out[url] = await page.content()
                except Exception as e:
                    print(f"  ism Playwright failed {url}: {e}")
        finally:
            await browser.close()
    return out


def fetch_items() -> list[dict]:
    try:
        html_by_url: dict[str, str] = {}
        need_pw: list[str] = []
        for url in ism_report_urls():
            html = _requests_html(url)
            if html is None:
                need_pw.append(url)
            elif html:
                html_by_url[url] = html
        if need_pw:
            html_by_url.update(asyncio.run(_playwright_pages(playwright_ism_urls(need_pw))))

        items: list[dict] = []
        seen: set[str] = set()
        for url in ism_report_urls():
            html = html_by_url.get(url) or ""
            item = parse_ism_report_html(html, url) if html else None
            if not item:
                continue
            key = item["title"].lower()[:80]
            if key in seen:
                continue
            seen.add(key)
            items.append(item)
            if len(items) >= 6:
                break
        return items
    except Exception as e:
        print(f"  ism fetch failed: {e}")
        return []


def main():
    t0 = time.monotonic()
    print(f"[{SOURCE_NAME}] Fetching ISM PMI reports...")
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
