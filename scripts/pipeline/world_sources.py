"""World geopolitics source catalog: categories, enabled sources, merge."""

from __future__ import annotations

import json
import os
from collections import defaultdict
from datetime import datetime, timedelta
from typing import Any

_DIR = os.path.dirname(os.path.abspath(__file__))
_CATALOG_PATH = os.path.join(_DIR, "world_sources.json")

_catalog_cache: dict[str, Any] | None = None


def _load_raw() -> dict[str, Any]:
    global _catalog_cache
    if _catalog_cache is None:
        with open(_CATALOG_PATH, "r", encoding="utf-8") as f:
            _catalog_cache = json.load(f)
    return _catalog_cache


def load_catalog() -> list[dict[str, Any]]:
    return list(_load_raw()["sources"])


CATEGORIES: list[dict[str, str]] = []


def _init_category_constants() -> None:
    global CATEGORIES
    CATEGORIES = list(_load_raw()["categories"])


_init_category_constants()


def catalog_by_id(source_id: str) -> dict[str, Any]:
    for src in load_catalog():
        if src["id"] == source_id:
            return src
    raise KeyError(source_id)


def output_filename(src: dict[str, Any]) -> str:
    return src.get("output") or f"{src['id']}.json"


def resolve_enabled(
    catalog: list[dict[str, Any]] | None = None,
    settings: dict[str, Any] | None = None,
    source_ids: list[str] | None = None,
) -> list[str]:
    catalog = catalog or load_catalog()
    valid = {s["id"] for s in catalog}
    if source_ids:
        return [sid for sid in source_ids if sid in valid]
    overrides = (settings or {}).get("world_sources_enabled") or {}
    enabled = []
    for src in catalog:
        sid = src["id"]
        if sid in overrides:
            if overrides[sid]:
                enabled.append(sid)
        elif src.get("default_enabled"):
            enabled.append(sid)
    return enabled


def world_title_key(title: str) -> str:
    return (title or "").lower().strip()[:80]


def load_previous_day_title_keys(output_dir: str, report_date: str) -> set[str]:
    try:
        day = datetime.strptime(report_date, "%Y-%m-%d")
    except ValueError:
        return set()
    prev = (day - timedelta(days=1)).strftime("%Y-%m-%d")
    abs_out = os.path.abspath(output_dir)
    date_folder = os.path.dirname(abs_out)
    if os.path.basename(date_folder) != report_date:
        return set()
    path = os.path.join(
        os.path.dirname(date_folder), prev, "world-news", "world-news-data.json"
    )
    if not os.path.isfile(path):
        return set()
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError):
        return set()
    keys: set[str] = set()
    for block in data.get("categories") or []:
        for it in block.get("items") or []:
            key = world_title_key(it.get("title") or "")
            if key:
                keys.add(key)
    return keys


def _item_category(item: dict[str, Any], src: dict[str, Any]) -> str:
    cat = (item.get("category") or src.get("category") or "politics").strip()
    valid = {c["id"] for c in CATEGORIES}
    if cat not in valid:
        return "politics"
    return cat


def _build_merged_item(it: dict[str, Any]) -> dict[str, Any]:
    out = {
        "title": it["title"],
        "url": it.get("url", ""),
        "date": it.get("date", ""),
        "summary": it.get("summary", ""),
        "points": it.get("points", []),
        "source": it.get("_source_display") or it.get("source", ""),
        "category": it.get("category", ""),
        "source_id": it.get("_source") or it.get("source_id", ""),
    }
    if it.get("title_zh"):
        out["title_zh"] = it["title_zh"]
    if it.get("summary_zh"):
        out["summary_zh"] = it["summary_zh"]
    return out


def merge_source_jsons(
    output_dir: str,
    report_date: str,
    catalog: list[dict[str, Any]] | None = None,
    enabled_ids: list[str] | None = None,
) -> dict[str, Any]:
    catalog = catalog or load_catalog()
    cat_labels = {c["id"]: c["label"] for c in CATEGORIES}
    wanted = set(enabled_ids) if enabled_ids is not None else {s["id"] for s in catalog}

    all_items: list[dict[str, Any]] = []
    sources_used: list[str] = []
    sources_unavailable: list[str] = []

    for src in catalog:
        if src["id"] not in wanted:
            continue
        json_path = os.path.join(output_dir, output_filename(src))
        if not os.path.exists(json_path):
            sources_unavailable.append(src["display"])
            continue
        with open(json_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        items = data.get("items") or []
        if not items:
            sources_unavailable.append(src["display"])
            continue
        sources_used.append(src["display"])
        for item in items:
            item = dict(item)
            item["_source"] = src["id"]
            item["_source_display"] = src["display"]
            item["_priority"] = src.get("priority", 99)
            item["category"] = _item_category(item, src)
            if not item.get("source"):
                item["source"] = src["display"]
            all_items.append(item)

    seen_titles: set[str] = set()
    deduped: list[dict[str, Any]] = []
    for item in sorted(all_items, key=lambda x: x.get("_priority", 99)):
        title = item.get("title") or ""
        if not title:
            continue
        title_key = world_title_key(title)
        if title_key in seen_titles:
            continue
        seen_titles.add(title_key)
        deduped.append(item)

    prev_keys = load_previous_day_title_keys(output_dir, report_date)
    if prev_keys:
        deduped = [
            it for it in deduped
            if world_title_key(it.get("title") or "") not in prev_keys
        ]

    by_category: dict[str, list] = defaultdict(list)
    for item in deduped:
        by_category[item.get("category") or "politics"].append(item)

    categories = []
    for cat in CATEGORIES:
        cat_items = by_category.get(cat["id"], [])
        if not cat_items:
            continue
        categories.append({
            "category": cat["id"],
            "label": cat_labels.get(cat["id"], cat["id"]),
            "items": [_build_merged_item(it) for it in cat_items],
        })

    total = sum(len(c["items"]) for c in categories)
    return {
        "sources_used": sources_used,
        "sources_unavailable": sources_unavailable,
        "total_items": total,
        "categories": categories,
        "report_date": report_date,
    }


def world_history_missing_steps(
    date_dir: str,
    target_date: str,
    *,
    today: str | None = None,
) -> list[str]:
    """World merge/translate gaps for Daily Fetch history. Old dates without a
    world-news folder are complete; today or leftover per-source JSONs are not.
    """
    today = today or datetime.now().strftime("%Y-%m-%d")
    steps: list[str] = []
    wn_dir = os.path.join(date_dir, "world-news")
    wn_file = os.path.join(wn_dir, "world-news-data.json")
    has_wn_data = os.path.isfile(wn_file)
    has_wn_source_jsons = False
    if os.path.isdir(wn_dir):
        has_wn_source_jsons = any(
            f.endswith(".json") and f not in ("world-news-timing.json", "world-news-data.json")
            for f in os.listdir(wn_dir)
        )
    if not has_wn_data and (has_wn_source_jsons or target_date == today):
        steps.append("world_news_merge")
    if has_wn_data:
        try:
            with open(wn_file, "r", encoding="utf-8") as fh:
                payload = json.load(fh)
            if not payload.get("translated"):
                steps.append("world_news_translate")
        except (OSError, json.JSONDecodeError):
            pass
    return steps
