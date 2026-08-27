"""Finance News source catalog: categories, enabled sources, merge, RAG payload."""

from __future__ import annotations

import json
import os
import re
from collections import defaultdict
from typing import Any

from finance_news_filter import filter_and_rank_items

_DIR = os.path.dirname(os.path.abspath(__file__))
_CATALOG_PATH = os.path.join(_DIR, "finance_sources.json")

CHINA_DOMAIN_RE = re.compile(
    r"(?i)(://|\.)("
    r"sina\.com\.cn|sohu\.com|163\.com|people\.com\.cn|xinhuanet\.com|"
    r"cctv\.com|cls\.cn|eastmoney\.com|stcn\.com|yicai\.com|caixin\.com|"
    r"wallstreetcn\.com|10jqka\.com\.cn|jrj\.com\.cn|pbc\.gov\.cn|"
    r"csrc\.gov\.cn|gov\.cn|qq\.com|weixin\.qq\.com|thepaper\.cn|"
    r"21jingji\.com|nbd\.com\.cn|cnstock\.com|"
    r"weibo\.com|toutiao\.com"
    r")(/|$)"
)

_catalog_cache: dict[str, Any] | None = None


def _load_raw() -> dict[str, Any]:
    global _catalog_cache
    if _catalog_cache is None:
        with open(_CATALOG_PATH, "r", encoding="utf-8") as f:
            _catalog_cache = json.load(f)
    return _catalog_cache


def load_catalog() -> list[dict[str, Any]]:
    return list(_load_raw()["sources"])


CATEGORIES: list[dict[str, str]] = []  # filled below after load
AUDIO_FILES: dict[str, str] = {}


def _init_category_constants() -> None:
    global CATEGORIES, AUDIO_FILES
    raw = _load_raw()
    CATEGORIES = list(raw["categories"])
    AUDIO_FILES = {c["id"]: c["audio_file"] for c in CATEGORIES}


_init_category_constants()


def catalog_by_id(source_id: str) -> dict[str, Any]:
    for src in load_catalog():
        if src["id"] == source_id:
            return src
    raise KeyError(source_id)


def topic_category_for_source(source_id: str) -> str:
    return catalog_by_id(source_id)["category"]


def resolve_enabled(
    catalog: list[dict[str, Any]] | None = None,
    settings: dict[str, Any] | None = None,
    source_ids: list[str] | None = None,
) -> list[str]:
    catalog = catalog or load_catalog()
    valid = {s["id"] for s in catalog}
    if source_ids:
        return [sid for sid in source_ids if sid in valid]
    overrides = (settings or {}).get("finance_sources_enabled") or {}
    enabled = []
    for src in catalog:
        sid = src["id"]
        if sid in overrides:
            if overrides[sid]:
                enabled.append(sid)
        elif src.get("default_enabled"):
            enabled.append(sid)
    return enabled


def scripts_to_run(
    catalog: list[dict[str, Any]] | None = None,
    source_ids: list[str] | None = None,
) -> list[str]:
    """Return unique fetch keys ``fetcher::source_id`` for the selected sources."""
    catalog = catalog or load_catalog()
    wanted = set(source_ids or resolve_enabled(catalog))
    keys: list[str] = []
    seen: set[str] = set()
    for src in catalog:
        if src["id"] not in wanted:
            continue
        key = f"{src['fetcher']}::{src['id']}"
        if key in seen:
            continue
        seen.add(key)
        keys.append(key)
    return keys


def output_filename(src: dict[str, Any]) -> str:
    return src.get("output") or f"{src['id']}.json"


def drop_china_domain_items(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    kept = []
    for it in items:
        cat = (it.get("category") or "").strip()
        url = it.get("url") or ""
        if cat != "china-policy" and url and CHINA_DOMAIN_RE.search(url):
            continue
        kept.append(it)
    return kept


def categories_with_items(merged: dict[str, Any]) -> list[str]:
    """Category ids that have at least one item in a merged finance payload."""
    out: list[str] = []
    for block in merged.get("categories") or []:
        if block.get("items") and block.get("category"):
            out.append(block["category"])
    return out


def finance_report_items(merged: dict[str, Any]) -> list[dict[str, Any]]:
    """Daily Fetch Reports payload: per-category titles (zh preferred) + urls."""
    out: list[dict[str, Any]] = []
    for block in merged.get("categories") or []:
        cid = block.get("category") or ""
        items = []
        for it in block.get("items") or []:
            title = (it.get("title_zh") or it.get("title") or "").strip()
            if not title:
                continue
            items.append({
                "title": title,
                "url": it.get("url") or "",
                "source": it.get("source") or "",
            })
        out.append({
            "category": cid,
            "label": block.get("label") or cid,
            "items": items,
        })
    return out


def _build_merged_item(it: dict[str, Any]) -> dict[str, Any]:
    out = {
        "title": it["title"],
        "url": it.get("url", ""),
        "date": it.get("date", ""),
        "summary": it.get("summary", ""),
        "points": it.get("points", []),
        "source": it.get("_source_display") or it.get("source", ""),
        "region": it.get("region", "global"),
        "impact_score": it.get("impact_score", 0),
        "category": it.get("category", ""),
        "source_id": it.get("_source") or it.get("source_id", ""),
    }
    if it.get("date_uncertain"):
        out["date_uncertain"] = True
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
    id_to_src = {s["id"]: s for s in catalog}
    output_to_src: dict[str, dict[str, Any]] = {}
    for s in catalog:
        output_to_src[output_filename(s)] = s

    all_items: list[dict[str, Any]] = []
    sources_used: list[str] = []
    sources_unavailable: list[str] = []
    wanted = set(enabled_ids) if enabled_ids is not None else None

    for src in catalog:
        json_path = os.path.join(output_dir, output_filename(src))
        if not os.path.exists(json_path):
            if wanted is None or src["id"] in wanted:
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
            item["_keep_always"] = bool(src.get("keep_always"))
            item["category"] = src["category"]
            if not item.get("source"):
                item["source"] = src["display"]
            all_items.append(item)

    # Also pick up leftover files whose name matches a catalog output
    # (e.g. kitco.json written in tests without listing other sources).
    if wanted is None:
        for fname in os.listdir(output_dir):
            if not fname.endswith(".json") or fname in (
                "finance-news-data.json",
                "finance-news-timing.json",
            ):
                continue
            src = output_to_src.get(fname)
            if not src:
                # filename stem as id
                stem = fname[:-5]
                src = id_to_src.get(stem)
            if not src:
                continue
            if src["display"] in sources_used:
                continue
            json_path = os.path.join(output_dir, fname)
            with open(json_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            items = data.get("items") or []
            if not items:
                continue
            sources_used.append(src["display"])
            for item in items:
                item = dict(item)
                item["_source"] = src["id"]
                item["_source_display"] = src["display"]
                item["_priority"] = src.get("priority", 99)
                item["_keep_always"] = bool(src.get("keep_always"))
                item["category"] = src["category"]
                if not item.get("source"):
                    item["source"] = src["display"]
                all_items.append(item)

    seen_titles: set[str] = set()
    deduped: list[dict[str, Any]] = []
    for item in sorted(all_items, key=lambda x: x.get("_priority", 99)):
        title = item.get("title") or ""
        if not title:
            continue
        title_key = title.lower().strip()[:80]
        if title_key in seen_titles:
            continue
        seen_titles.add(title_key)
        deduped.append(item)

    always = [it for it in deduped if it.get("_keep_always")]
    rest = [it for it in deduped if not it.get("_keep_always")]
    filtered_rest = filter_and_rank_items(rest, report_date=report_date)
    # Official / keep_always still get region + a floor score
    from finance_news_filter import assign_region, is_same_day

    kept_always = []
    for raw in always:
        item = dict(raw)
        if not is_same_day(item, report_date):
            item["date_uncertain"] = True
        item["impact_score"] = max(int(item.get("impact_score") or 0), 80)
        item["region"] = assign_region(item)
        kept_always.append(item)
    filtered = kept_always + filtered_rest
    filtered = drop_china_domain_items(filtered)

    by_category: dict[str, list] = defaultdict(list)
    for item in filtered:
        by_category[item.get("category") or "markets"].append(item)

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
    non_china = sum(
        1
        for c in categories
        for it in c["items"]
        if it.get("region") != "china"
    )
    warnings: list[str] = []
    if total > 0 and non_china == 0:
        warnings.append("no_international_finance_items")

    result: dict[str, Any] = {
        "sources_used": sources_used,
        "sources_unavailable": sources_unavailable,
        "total_items": total,
        "categories": categories,
        "report_date": report_date,
    }
    if warnings:
        result["warnings"] = warnings
    return result


def extract_rag_items(merged: dict[str, Any]) -> list[dict[str, Any]]:
    report_date = merged.get("report_date") or ""
    out: list[dict[str, Any]] = []
    for cat in merged.get("categories") or []:
        cat_id = cat.get("category") or ""
        for it in cat.get("items") or []:
            title = (it.get("title") or "").strip()
            if not title:
                continue
            summary = (it.get("summary") or it.get("summary_zh") or "").strip()
            text_parts = [title]
            if it.get("title_zh") and it["title_zh"] != title:
                text_parts.append(it["title_zh"])
            if summary:
                text_parts.append(summary)
            text = "\n\n".join(text_parts)
            out.append({
                "text": text,
                "metadata": {
                    "date": (it.get("date") or report_date)[:10] if (it.get("date") or report_date) else report_date,
                    "source": it.get("source") or "",
                    "title": title,
                    "item_type": "finance_news",
                    "doc_type": "finance_news",
                    "category": cat_id,
                    "url": it.get("url") or "",
                    "difficulty": "intermediate",
                },
            })
    return out


def load_finance_items_from_reports(
    reports_root: str,
    start: str,
    end: str,
    categories: list[str] | None = None,
) -> list[dict[str, Any]]:
    """Load finance items from daily report folders (disk, not Qdrant)."""
    items: list[dict[str, Any]] = []
    if not os.path.isdir(reports_root):
        return items
    cat_set = set(categories) if categories else None
    for name in sorted(os.listdir(reports_root)):
        if len(name) != 10 or name[4] != "-":
            continue
        if name < start or name > end:
            continue
        path = os.path.join(reports_root, name, "finance-news", "finance-news-data.json")
        if not os.path.isfile(path):
            continue
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except (OSError, json.JSONDecodeError):
            continue
        for cat in data.get("categories") or []:
            cat_id = cat.get("category") or ""
            if cat_set is not None and cat_id not in cat_set:
                continue
            for it in cat.get("items") or []:
                row = dict(it)
                row["category"] = cat_id
                row["date"] = (row.get("date") or name)[:10] or name
                row["report_date"] = name
                items.append(row)
    return items


def filter_items_for_summary(
    items: list[dict[str, Any]],
    start: str,
    end: str,
    categories: list[str] | None = None,
) -> list[dict[str, Any]]:
    cat_set = set(categories) if categories else None
    got = []
    for it in items:
        d = (it.get("date") or "")[:10]
        if d < start or d > end:
            continue
        if cat_set is not None and it.get("category") not in cat_set:
            continue
        got.append(it)
    return got
