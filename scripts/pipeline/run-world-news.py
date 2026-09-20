"""
World News Orchestrator: fetches catalog sources in parallel, merges into
world-news-data.json, then optionally translates via Ollama.

Usage:
  python run-world-news.py --output-dir <dir>
  python run-world-news.py --output-dir <dir> --sources bbc-news,xinhua
  python run-world-news.py --output-dir <dir> --no-fetch --no-translate
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import sys
import time
from datetime import datetime

import requests as _requests

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
SCRIPTS_ROOT = os.path.normpath(os.path.join(SCRIPT_DIR, ".."))

if SCRIPT_DIR not in sys.path:
    sys.path.insert(0, SCRIPT_DIR)

from world_sources import (  # noqa: E402
    load_catalog,
    merge_source_jsons,
    resolve_enabled,
)

PER_SCRIPT_TIMEOUT = 120
_SETTINGS_FILE = os.path.join(SCRIPTS_ROOT, "rag", ".global_settings.json")


def _load_user_settings() -> dict:
    if not os.path.isfile(_SETTINGS_FILE):
        return {}
    try:
        with open(_SETTINGS_FILE, "r", encoding="utf-8") as f:
            return json.load(f) or {}
    except Exception:
        return {}


async def run_script(
    script_name: str,
    output_dir: str,
    source_id: str = "",
    timeout: int | None = None,
) -> dict:
    script_path = os.path.join(SCRIPTS_ROOT, script_name)
    limit = int(timeout) if timeout else PER_SCRIPT_TIMEOUT
    t0 = time.monotonic()
    result = {
        "script": script_name,
        "source_id": source_id,
        "success": False,
        "seconds": 0,
        "exit_code": None,
        "stdout": "",
        "stderr": "",
    }
    try:
        cmd = [sys.executable, script_path, output_dir]
        if source_id:
            cmd.append(source_id)
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=limit)
        result["exit_code"] = proc.returncode
        result["stdout"] = stdout.decode("utf-8", errors="replace").strip()
        result["stderr"] = stderr.decode("utf-8", errors="replace").strip()
        result["success"] = proc.returncode == 0
    except asyncio.TimeoutError:
        result["stderr"] = f"TIMEOUT after {limit}s"
        try:
            proc.kill()
        except Exception:
            pass
    except Exception as exc:
        result["stderr"] = str(exc)[:300]
    finally:
        result["seconds"] = round(time.monotonic() - t0, 2)

    tag = "OK" if result["success"] else "FAIL"
    print(f"  [{tag}] {script_name:35s} {result['seconds']:6.1f}s")
    if result["stdout"]:
        for line in result["stdout"].split("\n"):
            print(f"         {line}")
    if not result["success"] and result["stderr"]:
        print(f"         ERROR: {result['stderr'][:200]}")
    return result


def merge_news(output_dir: str, report_date: str | None = None) -> dict:
    report_date = report_date or datetime.now().strftime("%Y-%m-%d")
    return merge_source_jsons(output_dir, report_date)


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
            if title and not item.get("title_zh"):
                texts_to_translate.append(title)
                index_map.append((ci, ii, "title_zh"))
            if summary and not item.get("summary_zh"):
                texts_to_translate.append(summary)
                index_map.append((ci, ii, "summary_zh"))

    if not texts_to_translate:
        merged["translated"] = True
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


def _safe_print(msg: str) -> None:
    try:
        print(msg)
    except UnicodeEncodeError:
        print(msg.encode("ascii", errors="replace").decode("ascii"))


def _write_outputs(output_dir: str, merged: dict, timing: dict) -> tuple[str, str]:
    merged_path = os.path.join(output_dir, "world-news-data.json")
    with open(merged_path, "w", encoding="utf-8") as f:
        json.dump(merged, f, ensure_ascii=False, indent=2)
    timing_path = os.path.join(output_dir, "world-news-timing.json")
    with open(timing_path, "w", encoding="utf-8") as f:
        json.dump(timing, f, ensure_ascii=False, indent=2)
    return merged_path, timing_path


async def main():
    parser = argparse.ArgumentParser(description="Fetch geopolitics world news")
    parser.add_argument("--output-dir", default=None)
    parser.add_argument("--proxy", default=None)
    parser.add_argument("--sources", default=None, help="Comma-separated source ids")
    parser.add_argument("--no-fetch", action="store_true")
    parser.add_argument("--no-translate", action="store_true")
    parser.add_argument("--report-date", default=None)
    args = parser.parse_args()

    if args.proxy:
        os.environ["BRIEFING_PROXY"] = args.proxy

    output_dir = args.output_dir or os.path.join(os.getcwd(), "_world_news_tmp")
    os.makedirs(output_dir, exist_ok=True)

    report_date = args.report_date
    if not report_date:
        parent = os.path.basename(os.path.dirname(os.path.abspath(output_dir)))
        if len(parent) == 10 and parent[4] == "-" and parent[7] == "-":
            report_date = parent
        else:
            leaf = os.path.basename(os.path.abspath(output_dir))
            if len(leaf) == 10 and leaf[4] == "-" and leaf[7] == "-":
                report_date = leaf
    report_date = report_date or datetime.now().strftime("%Y-%m-%d")

    grand_t0 = time.monotonic()
    results = []
    catalog = load_catalog()
    if args.sources:
        source_ids = [s.strip() for s in args.sources.split(",") if s.strip()]
        enabled = resolve_enabled(catalog, source_ids=source_ids)
    else:
        enabled = resolve_enabled(catalog, settings=_load_user_settings())

    if args.no_fetch:
        print("=== World News Merge-only (--no-fetch) ===")
    else:
        to_run = [s for s in catalog if s["id"] in enabled]
        print(f"=== World News Fetch ({len(to_run)} sources, parallel) ===")
        tasks = [
            run_script(s["fetcher"], output_dir, s["id"], timeout=s.get("timeout"))
            for s in to_run
        ]
        results = await asyncio.gather(*tasks) if tasks else []
        succeeded = sum(1 for r in results if r["success"])
        failed = [r["script"] for r in results if not r["success"]]
        print(f"\n  {succeeded}/{len(results)} scripts succeeded")
        if failed:
            print(f"  Failed: {', '.join(failed)}")

    print("\n=== Merge ===")
    t = time.monotonic()
    merged = merge_source_jsons(output_dir, report_date, enabled_ids=enabled)
    merge_seconds = round(time.monotonic() - t, 2)

    if not args.no_translate:
        print("\n=== Translate to Chinese ===")
        t_trans = time.monotonic()
        merged = translate_news_to_chinese(merged)
        print(f"  Translation took {round(time.monotonic() - t_trans, 2)}s")

    grand_total = round(time.monotonic() - grand_t0, 2)
    timing = {
        "date": time.strftime("%Y-%m-%d"),
        "no_fetch": bool(args.no_fetch),
        "sources": [
            {"script": r["script"], "seconds": r["seconds"], "success": r["success"]}
            for r in results
        ],
        "merge_seconds": merge_seconds,
        "total_seconds": grand_total,
    }
    merged_path, timing_path = _write_outputs(output_dir, merged, timing)

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
