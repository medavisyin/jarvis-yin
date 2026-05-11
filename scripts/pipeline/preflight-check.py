"""
Pre-flight accessibility check for all briefing sources.

Sends parallel HEAD/GET requests to every source URL using Playwright,
logs reachability and response time. Failures are logged but do NOT
block subsequent fetching — each fetch script has its own timeout.

Usage:
  python preflight-check.py [output-dir]
  Output: <output-dir>/preflight-results.json

Dependencies: pip install playwright && playwright install chromium
"""
import asyncio
import json
import os
import sys
import time
from playwright.async_api import async_playwright

PROXY = os.environ.get("BRIEFING_PROXY")

SOURCES = [
    {"name": "arxiv-ml",        "url": "https://arxiv.org/list/cs.LG/recent"},
    {"name": "arxiv",           "url": "https://arxiv.org/list/cs.AI/recent"},
    {"name": "openai-blog",     "url": "https://openai.com/news/"},
    {"name": "anthropic",       "url": "https://www.anthropic.com/engineering"},
    {"name": "deepmind",        "url": "https://deepmind.google/blog/"},
    {"name": "techcrunch",      "url": "https://techcrunch.com/category/artificial-intelligence/"},
    {"name": "rundown",         "url": "https://www.therundown.ai/"},
    {"name": "github-trending", "url": "https://github.com/trending?since=daily"},
    {"name": "mit-review",      "url": "https://www.technologyreview.com/topic/artificial-intelligence/"},
    {"name": "venturebeat",    "url": "https://venturebeat.com/category/ai/"},
    {"name": "theverge",       "url": "https://www.theverge.com/ai-artificial-intelligence"},
]

TIMEOUT_MS = 25000

CLOUDFLARE_SOURCES = {"openai-blog", "techcrunch", "rundown"}


async def check_one(context, source: dict) -> dict:
    name = source["name"]
    url = source["url"]
    t0 = time.monotonic()
    result = {"name": name, "url": url, "reachable": False, "status": None, "seconds": 0, "error": None}
    page = await context.new_page()
    try:
        resp = await page.goto(url, wait_until="commit", timeout=TIMEOUT_MS)
        result["status"] = resp.status if resp else None
        # 403 from Cloudflare-protected sites still means the server responded
        if resp is not None:
            result["reachable"] = resp.status < 400 or (resp.status == 403 and name in CLOUDFLARE_SOURCES)
    except Exception as exc:
        result["error"] = str(exc)[:200]
    finally:
        result["seconds"] = round(time.monotonic() - t0, 2)
        await page.close()
    tag = "OK" if result["reachable"] else "FAIL"
    cf_note = " (Cloudflare)" if result["status"] == 403 and name in CLOUDFLARE_SOURCES else ""
    print(f"  [{tag}] {name:20s} {result['seconds']:5.1f}s  status={result['status']}{cf_note}  {result.get('error') or ''}")
    return result


async def main(output_dir: str):
    print("=== Pre-flight accessibility check ===")
    t_total = time.monotonic()

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True, proxy={"server": PROXY} if PROXY else None)
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
        )
        tasks = [check_one(context, s) for s in SOURCES]
        results = await asyncio.gather(*tasks)
        await browser.close()

    total_seconds = round(time.monotonic() - t_total, 2)
    reachable = sum(1 for r in results if r["reachable"])
    failed = [r["name"] for r in results if not r["reachable"]]

    print(f"\n  {reachable}/{len(results)} sources reachable in {total_seconds}s")
    if failed:
        print(f"  Unreachable: {', '.join(failed)}")

    payload = {
        "total_seconds": total_seconds,
        "reachable_count": reachable,
        "total_count": len(results),
        "sources": results,
    }
    os.makedirs(output_dir, exist_ok=True)
    out_path = os.path.join(output_dir, "preflight-results.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    print(f"  Results written to: {out_path}")


if __name__ == "__main__":
    output_dir = sys.argv[1] if len(sys.argv) > 1 else "."
    asyncio.run(main(output_dir))
