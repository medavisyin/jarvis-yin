"""
World News Orchestrator: fetches news from BBC, Reuters, AP, DW, and The Guardian
in parallel, merges results into world-news-data.json organized by category,
then translates titles and summaries to Chinese via Ollama.

Can run standalone or as part of the daily briefing pipeline.

Usage:
  python run-world-news.py --output-dir <temp-dir>
  python run-world-news.py  # uses _world_news_tmp in cwd

Dependencies: pip install feedparser playwright && playwright install chromium
"""
import argparse
import asyncio
import json
import os
import sys
import time
from collections import defaultdict

import requests as _requests

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
SCRIPTS_ROOT = os.path.normpath(os.path.join(SCRIPT_DIR, ".."))

FETCH_SCRIPTS = [
    "fetchers/news/fetch-bbc-news.py",
    "fetchers/news/fetch-reuters.py",
    "fetchers/news/fetch-ap-news.py",
    "fetchers/news/fetch-dw-news.py",
    "fetchers/news/fetch-guardian.py",
    "fetchers/news/fetch-china-news.py",
]

SOURCE_META = {
    "bbc-news":    {"display": "BBC World News",  "priority": 1},
    "reuters":     {"display": "Reuters",         "priority": 2},
    "ap-news":     {"display": "AP News",         "priority": 3},
    "dw-news":     {"display": "Deutsche Welle",  "priority": 4},
    "guardian":    {"display": "The Guardian",    "priority": 5},
    "china-news":  {"display": "中国新闻 (新浪/人民日报/财联社/头条/微博)", "priority": 0},
}

CATEGORY_ORDER = ["politics", "economics", "technology", "science"]
CATEGORY_LABELS = {
    "politics": "Politics & World Affairs",
    "economics": "Economics & Business",
    "technology": "Technology",
    "science": "Science & Environment",
}

PER_SCRIPT_TIMEOUT = 120


async def run_script(script_name: str, output_dir: str) -> dict:
    """Run a single fetch script as a subprocess."""
    script_path = os.path.join(SCRIPTS_ROOT, script_name)
    t0 = time.monotonic()
    result = {
        "script": script_name,
        "success": False,
        "seconds": 0,
        "exit_code": None,
        "stdout": "",
        "stderr": "",
    }

    try:
        proc = await asyncio.create_subprocess_exec(
            sys.executable, script_path, output_dir,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await asyncio.wait_for(
            proc.communicate(), timeout=PER_SCRIPT_TIMEOUT
        )
        result["exit_code"] = proc.returncode
        result["stdout"] = stdout.decode("utf-8", errors="replace").strip()
        result["stderr"] = stderr.decode("utf-8", errors="replace").strip()
        result["success"] = proc.returncode == 0
    except asyncio.TimeoutError:
        result["stderr"] = f"TIMEOUT after {PER_SCRIPT_TIMEOUT}s"
        try:
            proc.kill()
        except Exception:
            pass
    except Exception as exc:
        result["stderr"] = str(exc)[:300]
    finally:
        result["seconds"] = round(time.monotonic() - t0, 2)

    tag = "OK" if result["success"] else "FAIL"
    print(f"  [{tag}] {script_name:25s} {result['seconds']:6.1f}s")
    if result["stdout"]:
        for line in result["stdout"].split("\n"):
            print(f"         {line}")
    if not result["success"] and result["stderr"]:
        print(f"         ERROR: {result['stderr'][:200]}")

    return result


def _build_merged_item(it: dict) -> dict:
    """Build a clean merged item dict, preserving optional *_zh fields."""
    out = {
        "title": it["title"],
        "url": it.get("url", ""),
        "date": it.get("date", ""),
        "summary": it.get("summary", ""),
        "points": it.get("points", []),
        "source": it.get("_source_display", ""),
    }
    if it.get("title_zh"):
        out["title_zh"] = it["title_zh"]
    if it.get("summary_zh"):
        out["summary_zh"] = it["summary_zh"]
    return out


def merge_news(output_dir: str) -> dict:
    """Merge per-source JSON files into a categorized world news structure."""
    all_items = []
    sources_used = []
    sources_unavailable = []

    for source_name, meta in SOURCE_META.items():
        json_path = os.path.join(output_dir, f"{source_name}.json")
        if not os.path.exists(json_path):
            sources_unavailable.append(meta["display"])
            continue

        with open(json_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        items = data.get("items", [])
        if not items:
            sources_unavailable.append(meta["display"])
            continue

        sources_used.append(meta["display"])
        for item in items:
            item["_source"] = source_name
            item["_source_display"] = meta["display"]
            item["_priority"] = meta["priority"]
            all_items.append(item)

    seen_titles = set()
    deduped = []
    for item in sorted(all_items, key=lambda x: x.get("_priority", 99)):
        title = item.get("title", "")
        if not title:
            continue
        title_key = title.lower().strip()[:80]
        if title_key not in seen_titles:
            seen_titles.add(title_key)
            deduped.append(item)

    by_category = defaultdict(list)
    for item in deduped:
        cat = item.get("category", "politics")
        by_category[cat].append(item)

    categories = []
    for cat_key in CATEGORY_ORDER:
        cat_items = by_category.get(cat_key, [])
        if not cat_items:
            continue
        categories.append({
            "category": cat_key,
            "label": CATEGORY_LABELS.get(cat_key, cat_key.title()),
            "items": [_build_merged_item(it) for it in cat_items],
        })

    uncategorized = []
    for cat_key, cat_items in by_category.items():
        if cat_key not in CATEGORY_ORDER:
            for it in cat_items:
                merged_it = _build_merged_item(it)
                merged_it["category"] = cat_key
                uncategorized.append(merged_it)
    if uncategorized:
        categories.append({
            "category": "other",
            "label": "Other News",
            "items": uncategorized,
        })

    return {
        "sources_used": sources_used,
        "sources_unavailable": sources_unavailable,
        "total_items": len(deduped),
        "categories": categories,
    }


OLLAMA_HOST = os.environ.get("OLLAMA_HOST", "http://localhost:11434")
OLLAMA_TRANSLATE_MODEL = os.environ.get("OLLAMA_MODEL_FAST", "qwen3:1.7b")


def translate_news_to_chinese(merged: dict) -> dict:
    """Translate titles and summaries from English to Chinese via Ollama batch."""
    texts_to_translate = []
    index_map = []

    for ci, cat in enumerate(merged.get("categories", [])):
        for ii, item in enumerate(cat.get("items", [])):
            title = item.get("title", "")
            summary = item.get("summary", "")
            if title:
                texts_to_translate.append(title)
                index_map.append((ci, ii, "title_zh"))
            if summary:
                texts_to_translate.append(summary)
                index_map.append((ci, ii, "summary_zh"))

    if not texts_to_translate:
        return merged

    BATCH_SIZE = 10
    translated = [""] * len(texts_to_translate)
    total = len(texts_to_translate)
    done = 0

    for batch_start in range(0, total, BATCH_SIZE):
        batch = texts_to_translate[batch_start:batch_start + BATCH_SIZE]
        numbered = "\n".join(f"{i+1}. {t}" for i, t in enumerate(batch))
        prompt = (
            f"将以下{len(batch)}条新闻标题/摘要翻译成简体中文。"
            f"严格按编号输出，每行格式: 编号. 中文翻译\n"
            f"不要添加任何解释。\n\n{numbered}"
        )

        try:
            resp = _requests.post(
                f"{OLLAMA_HOST}/api/chat",
                json={
                    "model": OLLAMA_TRANSLATE_MODEL,
                    "messages": [
                        {"role": "system", "content": "你是专业翻译。只输出翻译结果，不要解释。"},
                        {"role": "user", "content": prompt},
                    ],
                    "stream": False,
                    "think": False,
                    "options": {"temperature": 0.1, "num_predict": 2000},
                },
                timeout=60,
            )
            resp.raise_for_status()
            raw = resp.json().get("message", {}).get("content", "")

            import re
            for line in raw.strip().split("\n"):
                line = line.strip()
                m = re.match(r"^(\d+)\.\s*(.+)", line)
                if m:
                    idx = int(m.group(1)) - 1
                    if 0 <= idx < len(batch):
                        translated[batch_start + idx] = m.group(2).strip()
            done += len(batch)
            print(f"  Translated {done}/{total} texts")
        except Exception as e:
            print(f"  Translation batch failed: {e}")
            done += len(batch)

    for i, (ci, ii, field) in enumerate(index_map):
        if translated[i]:
            merged["categories"][ci]["items"][ii][field] = translated[i]

    translated_count = sum(1 for t in translated if t)
    print(f"  Translation complete: {translated_count}/{total} texts translated")
    merged["translated"] = True
    return merged


async def main():
    parser = argparse.ArgumentParser(description="Fetch world news from BBC, Reuters, AP, DW")
    parser.add_argument("--output-dir", default=None, help="Directory for output files")
    parser.add_argument("--proxy", default=None, help="SOCKS5/HTTP proxy URL")
    parser.add_argument("--save-raw", action="store_true", default=True, help="Save raw drill-down content")
    parser.add_argument("--no-save-raw", action="store_true", help="Disable raw content saving")
    parser.add_argument("--no-translate", action="store_true", help="Skip Chinese translation")
    args = parser.parse_args()

    if args.proxy:
        os.environ["BRIEFING_PROXY"] = args.proxy
        from urllib.parse import urlparse
        parsed = urlparse(args.proxy)
        print(f"Proxy: {parsed.scheme}://{parsed.hostname}:{parsed.port}")

    if args.save_raw and not args.no_save_raw:
        os.environ["SAVE_RAW"] = "1"

    output_dir = args.output_dir or os.path.join(os.getcwd(), "_world_news_tmp")
    os.makedirs(output_dir, exist_ok=True)

    grand_t0 = time.monotonic()

    print(f"=== World News Fetch ({len(FETCH_SCRIPTS)} sources, parallel) ===")
    tasks = [run_script(s, output_dir) for s in FETCH_SCRIPTS]
    results = await asyncio.gather(*tasks)

    succeeded = sum(1 for r in results if r["success"])
    failed = [r["script"] for r in results if not r["success"]]
    print(f"\n  {succeeded}/{len(results)} scripts succeeded")
    if failed:
        print(f"  Failed: {', '.join(failed)}")

    print("\n=== Merge ===")
    t = time.monotonic()
    merged = merge_news(output_dir)
    merge_seconds = round(time.monotonic() - t, 2)

    if not args.no_translate:
        print("\n=== Translate to Chinese ===")
        t_trans = time.monotonic()
        merged = translate_news_to_chinese(merged)
        trans_seconds = round(time.monotonic() - t_trans, 2)
        print(f"  Translation took {trans_seconds}s")
    else:
        trans_seconds = 0

    merged_path = os.path.join(output_dir, "world-news-data.json")
    with open(merged_path, "w", encoding="utf-8") as f:
        json.dump(merged, f, ensure_ascii=False, indent=2)

    grand_total = round(time.monotonic() - grand_t0, 2)

    timing = {
        "date": time.strftime("%Y-%m-%d"),
        "sources": [
            {"script": r["script"], "seconds": r["seconds"], "success": r["success"]}
            for r in results
        ],
        "merge_seconds": merge_seconds,
        "total_seconds": grand_total,
    }
    timing_path = os.path.join(output_dir, "world-news-timing.json")
    with open(timing_path, "w", encoding="utf-8") as f:
        json.dump(timing, f, ensure_ascii=False, indent=2)

    def _safe_print(msg: str) -> None:
        try:
            print(msg)
        except UnicodeEncodeError:
            print(msg.encode("ascii", errors="replace").decode("ascii"))

    _safe_print(f"\n  Sources used: {', '.join(merged['sources_used'])}")
    if merged["sources_unavailable"]:
        _safe_print(f"  Unavailable: {', '.join(merged['sources_unavailable'])}")
    print(f"  Total items: {merged['total_items']}")
    for cat in merged["categories"]:
        print(f"    {cat['label']}: {len(cat['items'])} items")

    print(f"\n=== Done in {grand_total}s ===")
    print(f"  Output: {merged_path}")
    print(f"  Timing: {timing_path}")


if __name__ == "__main__":
    asyncio.run(main())
