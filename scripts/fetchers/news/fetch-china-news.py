"""
中国政治/金融新闻抓取器 — 用于股市判断.

数据源:
  - 新华社 (Xinhua) RSS
  - 人民日报 RSS
  - 财联社 (cls.cn) — 电报快讯

输出格式与其他世界新闻 fetcher 一致, 方便 merge_news 合并.
"""
import json
import os
import re
import sys
import time
from datetime import datetime

try:
    import feedparser
except ImportError:
    feedparser = None

try:
    import requests
except ImportError:
    requests = None

SOURCE_NAME = "china-news"
OUTPUT_DIR = sys.argv[1] if len(sys.argv) > 1 else os.path.join(os.getcwd(), "_world_news_tmp")

PROXY = os.environ.get("BRIEFING_PROXY", "")
PROXIES = {}
if PROXY:
    PROXIES = {"http": PROXY, "https": PROXY}

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
}

CATEGORY_MAP = {
    "politics": "politics",
    "finance": "economics",
    "economy": "economics",
    "business": "economics",
    "policy": "politics",
}

RSS_FEEDS = [
    ("politics", "http://www.xinhuanet.com/politics/rssnewsList.xml"),
    ("politics", "http://www.xinhuanet.com/world/rssnewsList.xml"),
    ("finance", "http://www.xinhuanet.com/fortune/rssnewsList.xml"),
]

SINA_ROLL_API = "https://feed.mix.sina.com.cn/api/roll/get"

SINA_CHANNELS = [
    ("politics", "2510", 15),
    ("finance", "2509", 20),
]


def fetch_sina_roll() -> list[dict]:
    """Fetch from Sina rolling news API (politics + finance)."""
    items = []
    if requests is None:
        print("  requests not available, skipping Sina")
        return items

    for category, lid, num in SINA_CHANNELS:
        try:
            resp = requests.get(
                SINA_ROLL_API,
                params={"pageid": "153", "lid": lid, "num": str(num), "page": "1"},
                headers=HEADERS,
                timeout=15,
                proxies=PROXIES,
            )
            resp.raise_for_status()
            data = resp.json()
            roll_items = data.get("result", {}).get("data", [])

            for roll in roll_items:
                title = roll.get("title", "").strip()
                if not title:
                    continue
                intro = roll.get("intro", "").strip()
                intro = re.sub(r"<[^>]+>", "", intro)[:300]
                url = roll.get("url", "")
                ctime = roll.get("ctime", "")
                date_str = ""
                if ctime and ctime.isdigit():
                    date_str = datetime.fromtimestamp(int(ctime)).strftime("%Y-%m-%d %H:%M")

                mapped_cat = CATEGORY_MAP.get(category, "politics")
                if any(k in title for k in ["政策", "国务院", "总书记", "外交", "军事", "制裁"]):
                    mapped_cat = "politics"

                items.append({
                    "title": title,
                    "title_zh": title,
                    "url": url,
                    "date": date_str,
                    "summary": intro if intro != title else "",
                    "summary_zh": intro if intro != title else "",
                    "category": mapped_cat,
                    "points": [],
                    "_source_tag": "sina",
                })
        except Exception as e:
            print(f"  Sina lid={lid} failed: {e}")

    return items


def fetch_people_daily_rss() -> list[dict]:
    """Fetch from People's Daily RSS."""
    items = []
    if feedparser is None:
        return items

    rss_urls = [
        ("politics", "http://www.people.com.cn/rss/politics.xml"),
        ("finance", "http://www.people.com.cn/rss/finance.xml"),
    ]

    for category, url in rss_urls:
        try:
            feed = feedparser.parse(url)
            for entry in feed.entries[:8]:
                title = entry.get("title", "").strip()
                if not title:
                    continue
                summary = entry.get("summary", "").strip()
                summary = re.sub(r"<[^>]+>", "", summary)[:300]

                items.append({
                    "title": title,
                    "title_zh": title,
                    "url": entry.get("link", ""),
                    "date": entry.get("published", ""),
                    "summary": summary,
                    "summary_zh": summary,
                    "category": CATEGORY_MAP.get(category, "politics"),
                    "points": [],
                    "_source_tag": "people",
                })
        except Exception as e:
            print(f"  People Daily RSS {url} failed: {e}")

    return items


def main():
    t0 = time.monotonic()
    timing = {"rss": 0, "cls": 0, "people": 0}

    print(f"[{SOURCE_NAME}] Fetching Chinese political/financial news...")

    t = time.monotonic()
    sina_items = fetch_sina_roll()
    timing["sina"] = round(time.monotonic() - t, 2)
    print(f"  Sina (politics+finance): {len(sina_items)} items ({timing['sina']}s)")

    t = time.monotonic()
    people_items = fetch_people_daily_rss()
    timing["people"] = round(time.monotonic() - t, 2)
    print(f"  People Daily: {len(people_items)} items ({timing['people']}s)")

    all_items = sina_items + people_items

    seen = set()
    deduped = []
    for item in all_items:
        key = item["title"][:40].lower()
        if key not in seen:
            seen.add(key)
            deduped.append(item)

    timing["total_seconds"] = round(time.monotonic() - t0, 2)
    result = {"source": SOURCE_NAME, "items": deduped, "_timing": timing}

    os.makedirs(OUTPUT_DIR, exist_ok=True)
    out_path = os.path.join(OUTPUT_DIR, f"{SOURCE_NAME}.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    print(f"  Total: {len(deduped)} items → {out_path}")


if __name__ == "__main__":
    main()
