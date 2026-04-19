"""
中国政治/金融新闻抓取器 — 用于股市判断.

数据源 (all mainland-reachable, no RSSHub dependency):
  - 新浪滚动新闻 API (Sina rolling news) — politics + finance
  - 人民日报 RSS (People's Daily) — official policy
  - 财联社快讯 API (CLS telegraph) — market flash
  - 今日头条热榜 API (Toutiao trending) — popular topics
  - 微博热搜 API (Weibo hot search) — social trending

Cross-day dedup: loads previous day's titles to avoid audio repeats.
"""
import json
import os
import re
import sys
import time
from datetime import datetime, timedelta

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
    "technology": "technology",
}

SINA_ROLL_API = "https://feed.mix.sina.com.cn/api/roll/get"

SINA_CHANNELS = [
    ("politics", "2510", 20),
    ("finance", "2509", 25),
]


def _today_str():
    return datetime.now().strftime("%Y-%m-%d")


def _is_today(date_str: str) -> bool:
    """Check if a date string contains today's date."""
    today = _today_str()
    return today in str(date_str)


def _load_previous_titles() -> set[str]:
    """Load titles from yesterday's china-news.json to avoid cross-day duplicates."""
    try:
        parent = os.path.dirname(os.path.dirname(OUTPUT_DIR))
        yesterday = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
        prev_path = os.path.join(parent, yesterday, "world-news", f"{SOURCE_NAME}.json")
        if os.path.isfile(prev_path):
            with open(prev_path, encoding="utf-8") as f:
                data = json.load(f)
            titles = {item["title"][:50].lower() for item in data.get("items", []) if item.get("title")}
            print(f"  Cross-day dedup: loaded {len(titles)} titles from {yesterday}")
            return titles
    except Exception as e:
        print(f"  Cross-day dedup load failed (non-fatal): {e}")
    return set()


def fetch_sina_roll() -> list[dict]:
    """Fetch from Sina rolling news API (politics + finance), prefer today's articles."""
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
    for category, url in [
        ("politics", "http://www.people.com.cn/rss/politics.xml"),
        ("finance", "http://www.people.com.cn/rss/finance.xml"),
    ]:
        items += _parse_rss_feed(url, category, "people", max_entries=10)
    return items


def _fetch_rss_text(url: str, timeout: int = 12) -> str:
    """Download RSS/Atom XML with a strict timeout. feedparser.parse(url) has no timeout."""
    if requests is None:
        return ""
    try:
        resp = requests.get(url, headers=HEADERS, timeout=timeout, proxies=PROXIES)
        resp.raise_for_status()
        return resp.text
    except Exception as e:
        print(f"  RSS download {url}: {e}")
        return ""


def _parse_rss_feed(url: str, category: str, source_tag: str,
                     max_entries: int = 8) -> list[dict]:
    """Generic RSS/Atom parser with timeout. Returns empty list on failure."""
    items = []
    if feedparser is None:
        return items
    try:
        xml_text = _fetch_rss_text(url)
        if not xml_text:
            return items
        feed = feedparser.parse(xml_text)
        for entry in feed.entries[:max_entries]:
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
                "category": CATEGORY_MAP.get(category, "economics"),
                "points": [],
                "_source_tag": source_tag,
            })
    except Exception as e:
        print(f"  RSS {source_tag} ({url}) failed: {e}")
    return items


def fetch_weibo_hot() -> list[dict]:
    """Fetch Weibo (微博) hot search — real-time social trending topics."""
    items = []
    if requests is None:
        return items
    try:
        resp = requests.get(
            "https://weibo.com/ajax/side/hotSearch",
            headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                "Referer": "https://weibo.com/",
            },
            timeout=12,
            proxies=PROXIES,
        )
        if not resp.ok:
            return items
        data = resp.json()
        hot_list = data.get("data", {}).get("realtime", [])

        for entry in hot_list[:15]:
            word = entry.get("word", "").strip()
            if not word:
                continue
            label_name = entry.get("label_name", "")
            note = entry.get("note", "").strip()
            mid = entry.get("mid", "")

            cat = "politics"
            if any(k in word for k in ["经济", "股", "基金", "银行", "房", "消费", "贸易", "关税"]):
                cat = "economics"
            elif any(k in word for k in ["科技", "AI", "芯片", "数据", "互联网", "手机", "华为"]):
                cat = "technology"

            url = f"https://s.weibo.com/weibo?q=%23{word}%23" if word else ""

            items.append({
                "title": word,
                "title_zh": word,
                "url": url,
                "date": _today_str(),
                "summary": note if note and note != word else "",
                "summary_zh": note if note and note != word else "",
                "category": cat,
                "points": [label_name] if label_name else [],
                "_source_tag": "weibo",
            })
    except Exception as e:
        print(f"  Weibo hot failed: {e}")
    return items


def fetch_cls_telegraph() -> list[dict]:
    """Fetch 财联社 (CLS) telegraph/flash news — fast-moving market updates."""
    items = []
    if requests is None:
        return items
    try:
        resp = requests.get(
            "https://www.cls.cn/nodeapi/updateTelegraphList",
            params={"app": "CailianpressWeb", "os": "web", "sv": "7.7.5", "rn": "20"},
            headers={**HEADERS, "Referer": "https://www.cls.cn/telegraph"},
            timeout=15,
            proxies=PROXIES,
        )
        if not resp.ok:
            return items
        data = resp.json()
        roll_data = data.get("data", {}).get("roll_data", data.get("data", []))
        if not isinstance(roll_data, list):
            return items

        for roll in roll_data[:15]:
            content = roll.get("content", "").strip()
            title = roll.get("title", "").strip() or roll.get("brief", "").strip()
            if not title:
                clean = re.sub(r"<[^>]+>", "", content)
                bracket = re.search(r"【(.+?)】", clean)
                title = bracket.group(1) if bracket else clean[:80]
            if not title:
                continue
            summary = re.sub(r"<[^>]+>", "", content)[:300] if content else ""
            ctime = roll.get("ctime", 0)
            date_str = datetime.fromtimestamp(ctime).strftime("%Y-%m-%d %H:%M") if ctime else ""

            items.append({
                "title": title,
                "title_zh": title,
                "url": f"https://www.cls.cn/detail/{roll.get('id', '')}",
                "date": date_str,
                "summary": summary if summary != title else "",
                "summary_zh": summary if summary != title else "",
                "category": "economics",
                "points": [],
                "_source_tag": "cls",
            })
    except Exception as e:
        print(f"  CLS telegraph failed: {e}")

    return items


def fetch_toutiao_trending() -> list[dict]:
    """Fetch Toutiao (今日头条) trending/hot topics via public API."""
    items = []
    if requests is None:
        return items

    try:
        resp = requests.get(
            "https://www.toutiao.com/hot-event/hot-board/?origin=toutiao_pc",
            headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                "Referer": "https://www.toutiao.com/",
            },
            timeout=15,
            proxies=PROXIES,
        )
        resp.raise_for_status()
        data = resp.json()
        hot_list = data.get("data", [])

        for hot in hot_list[:15]:
            title = hot.get("Title", "").strip()
            if not title:
                continue
            url = hot.get("Url", "")
            if not url and hot.get("ClusterIdStr"):
                url = f"https://www.toutiao.com/trending/{hot['ClusterIdStr']}/"

            cat = "politics"
            if any(k in title for k in ["经济", "股", "基金", "银行", "房", "消费", "贸易"]):
                cat = "economics"
            elif any(k in title for k in ["科技", "AI", "芯片", "数据", "互联网"]):
                cat = "technology"

            items.append({
                "title": title,
                "title_zh": title,
                "url": url,
                "date": _today_str(),
                "summary": "",
                "summary_zh": "",
                "category": cat,
                "points": [],
                "_source_tag": "toutiao",
            })
    except Exception as e:
        print(f"  Toutiao trending failed: {e}")

    return items


def main():
    t0 = time.monotonic()
    timing = {}

    print(f"[{SOURCE_NAME}] Fetching Chinese political/financial news...")

    prev_titles = _load_previous_titles()

    t = time.monotonic()
    sina_items = fetch_sina_roll()
    timing["sina"] = round(time.monotonic() - t, 2)
    print(f"  Sina (politics+finance): {len(sina_items)} items ({timing['sina']}s)")

    t = time.monotonic()
    people_items = fetch_people_daily_rss()
    timing["people"] = round(time.monotonic() - t, 2)
    print(f"  People Daily: {len(people_items)} items ({timing['people']}s)")

    t = time.monotonic()
    cls_items = fetch_cls_telegraph()
    timing["cls"] = round(time.monotonic() - t, 2)
    print(f"  CLS telegraph: {len(cls_items)} items ({timing['cls']}s)")

    t = time.monotonic()
    toutiao_items = fetch_toutiao_trending()
    timing["toutiao"] = round(time.monotonic() - t, 2)
    print(f"  Toutiao trending: {len(toutiao_items)} items ({timing['toutiao']}s)")

    t = time.monotonic()
    weibo_items = fetch_weibo_hot()
    timing["weibo"] = round(time.monotonic() - t, 2)
    print(f"  Weibo hot: {len(weibo_items)} items ({timing['weibo']}s)")

    all_items = (sina_items + people_items + cls_items
                 + toutiao_items + weibo_items)

    # --- Dedup: within-run + cross-day ---
    seen = set()
    deduped = []
    cross_day_skipped = 0
    for item in all_items:
        key = item["title"][:50].lower()
        if key in seen:
            continue
        seen.add(key)
        if key in prev_titles:
            cross_day_skipped += 1
            continue
        deduped.append(item)

    if cross_day_skipped:
        print(f"  Cross-day dedup removed {cross_day_skipped} stale articles")

    # Sort: today's articles first, then by source diversity
    source_order = {"toutiao": 0, "cls": 1, "weibo": 2, "sina": 3, "people": 4}
    deduped.sort(key=lambda x: (
        0 if _is_today(x.get("date", "")) else 1,
        source_order.get(x.get("_source_tag", ""), 9),
    ))

    timing["total_seconds"] = round(time.monotonic() - t0, 2)
    timing["cross_day_dedup"] = cross_day_skipped
    result = {"source": SOURCE_NAME, "items": deduped, "_timing": timing}

    os.makedirs(OUTPUT_DIR, exist_ok=True)
    out_path = os.path.join(OUTPUT_DIR, f"{SOURCE_NAME}.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    print(f"  Total: {len(deduped)} unique items → {out_path}")
    src_counts = {}
    for it in deduped:
        tag = it.get("_source_tag", "?")
        src_counts[tag] = src_counts.get(tag, 0) + 1
    print(f"  Breakdown: {src_counts}")


if __name__ == "__main__":
    main()
