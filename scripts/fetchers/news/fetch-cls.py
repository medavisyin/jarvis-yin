"""Fetch 财联社 telegraph flashes. No Weibo/Toutiao."""
from __future__ import annotations

import json
import os
import re
import sys
import time
from datetime import datetime

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(SCRIPT_DIR, ".."))
from proxy_strategy import get_proxies_for_requests  # noqa: E402

SOURCE_NAME = "cls"
OUTPUT_DIR = sys.argv[1] if len(sys.argv) > 1 else "."
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}


def fetch_items() -> list[dict]:
    try:
        import requests
    except ImportError:
        return []
    items = []
    try:
        resp = requests.get(
            "https://www.cls.cn/nodeapi/updateTelegraphList",
            params={"app": "CailianpressWeb", "os": "web", "sv": "7.7.5", "rn": "20"},
            headers={**HEADERS, "Referer": "https://www.cls.cn/telegraph"},
            timeout=15,
            proxies=get_proxies_for_requests(
                "https://www.cls.cn/nodeapi/updateTelegraphList"
            ),
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
            date_str = (
                datetime.fromtimestamp(ctime).strftime("%Y-%m-%d %H:%M") if ctime else ""
            )
            items.append({
                "title": title,
                "title_zh": title,
                "url": f"https://www.cls.cn/detail/{roll.get('id', '')}",
                "date": date_str,
                "summary": summary if summary != title else "",
                "summary_zh": summary if summary != title else "",
                "category": "china-policy",
                "points": [],
                "source": "财联社",
            })
    except Exception as e:
        print(f"  CLS telegraph failed: {e}")
    return items


def main():
    t0 = time.monotonic()
    print(f"[{SOURCE_NAME}] Fetching 财联社...")
    items = fetch_items()
    timing = {
        "source": SOURCE_NAME,
        "steps": [{"step": "api", "seconds": round(time.monotonic() - t0, 2)}],
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
