"""Assemble a local world-monitor dashboard from Daily Fetch JSON.

Original Jarvis implementation: keyword hubs, stream correlation.
Does not vendor World Monitor (AGPL) source. Map engines are named for the UI
to load globe.gl / deck.gl as npm libraries.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timedelta
from typing import Any

from geo_hubs import infer_hubs

VARIANTS = ["world", "tech", "finance", "commodity", "happy", "energy"]

LAYER_CATALOG: list[dict[str, Any]] = [
    {"id": "news_politics", "label": "Politics", "variants": ["world"]},
    {"id": "news_economics", "label": "Economics", "variants": ["world", "finance"]},
    {"id": "news_technology", "label": "Technology", "variants": ["tech"]},
    {"id": "news_science", "label": "Science", "variants": ["tech"]},
    {"id": "military", "label": "Military", "variants": ["world"]},
    {"id": "economic", "label": "Economic stress", "variants": ["world", "finance"]},
    {"id": "disaster", "label": "Disaster", "variants": ["world"]},
    {"id": "escalation", "label": "Escalation", "variants": ["world"]},
    {"id": "finance_exchanges", "label": "Exchanges", "variants": ["finance"]},
    {"id": "finance_commodities", "label": "Commodities", "variants": ["finance", "commodity", "energy"]},
    {"id": "finance_crypto", "label": "Crypto", "variants": ["finance"]},
    {"id": "happy", "label": "Constructive news", "variants": ["happy"]},
    {"id": "energy", "label": "Energy chokepoints", "variants": ["energy"]},
]

_STREAM_KW = {
    "military": (
        "troop", "missile", "airstrike", "air strike", "nato", "warship",
        "drone strike", "artillery", "军队", "导弹", "空袭", "军演", "pla navy",
    ),
    "economic": (
        "sanctions", "tariff", "inflation", "rate cut", "default", "制裁",
        "关税", "降准", "降息",
    ),
    "disaster": (
        "earthquake", "flood", "hurricane", "wildfire", "famine", "typhoon",
        "地震", "洪水", "飓风", "山火", "饥荒",
    ),
    "escalation": (
        "invasion", "nuclear", "martial law", "mobilization", "red line",
        "invasion threat", "入侵", "核", "戒严", "总动员",
    ),
}

_HAPPY_KW = (
    "ceasefire", "peace", "aid", "rescue", "agreement", "cooperation",
    "harvest", "停火", "和平", "救援", "合作", "丰收",
)
_ENERGY_KW = (
    "oil", "gas", "opec", "lng", "hormuz", "brent", "petroleum", "nuclear plant",
    "石油", "天然气", "能源", "霍尔木兹",
)


def layers_for_variant(variant: str) -> list[dict[str, Any]]:
    v = variant if variant in VARIANTS else "world"
    return [dict(ly) for ly in LAYER_CATALOG if v in ly["variants"]]


def classify_streams(text: str) -> list[str]:
    blob = (text or "").lower()
    hits = [name for name, kws in _STREAM_KW.items() if any(k in blob for k in kws)]
    return hits


def _blob(item: dict[str, Any]) -> str:
    return " ".join(
        str(item.get(k) or "")
        for k in ("title", "title_zh", "summary", "summary_zh")
    )


def flatten_world_items(data: dict[str, Any] | None) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for cat in (data or {}).get("categories") or []:
        cat_id = cat.get("category") or "politics"
        for it in cat.get("items") or []:
            row = dict(it)
            row["news_category"] = cat_id
            out.append(row)
    return out


def flatten_finance_items(data: dict[str, Any] | None) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for cat in (data or {}).get("categories") or []:
        cat_id = cat.get("category") or "markets"
        for it in cat.get("items") or []:
            row = dict(it)
            row["finance_category"] = cat_id
            out.append(row)
    return out


def enrich_item(item: dict[str, Any]) -> dict[str, Any]:
    text = _blob(item)
    hubs = infer_hubs(text)
    streams = classify_streams(text)
    countries = []
    seen: set[str] = set()
    for h in hubs:
        cid = h.get("country")
        if cid and cid not in seen:
            seen.add(cid)
            countries.append(cid)
    return {
        **item,
        "hubs": [
            {"id": h["id"], "label": h.get("label"), "lat": h["lat"], "lon": h["lon"], "country": h.get("country")}
            for h in hubs
        ],
        "streams": streams,
        "country_ids": countries,
        "happy": any(k in text.lower() for k in _HAPPY_KW),
        "energy": any(k in text.lower() for k in _ENERGY_KW),
    }


def compute_correlation(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_hub: dict[str, dict[str, Any]] = {}
    for it in items:
        for hub in it.get("hubs") or []:
            hid = hub["id"]
            rec = by_hub.setdefault(
                hid,
                {"hub_id": hid, "label": hub.get("label") or hid, "lat": hub["lat"], "lon": hub["lon"],
                 "streams": set(), "titles": []},
            )
            rec["streams"].update(it.get("streams") or [])
            title = it.get("title_zh") or it.get("title") or ""
            if title:
                rec["titles"].append(title)
    hits = []
    for rec in by_hub.values():
        streams = sorted(rec["streams"])
        if len(streams) >= 2:
            hits.append({
                "hub_id": rec["hub_id"],
                "label": rec["label"],
                "lat": rec["lat"],
                "lon": rec["lon"],
                "streams": streams,
                "titles": rec["titles"][:6],
            })
    hits.sort(key=lambda r: (-len(r["streams"]), r["hub_id"]))
    return hits


_FINANCE_BUCKETS = {
    "exchanges": ("markets", "us-political", "china-policy"),
    "commodities": ("gold", "oil"),
    "crypto": ("crypto",),
}


def finance_radar(data: dict[str, Any] | None) -> dict[str, Any]:
    items = flatten_finance_items(data)
    buckets: dict[str, list[str]] = {k: [] for k in _FINANCE_BUCKETS}
    for it in items:
        cat = it.get("finance_category") or ""
        title = it.get("title_zh") or it.get("title") or ""
        for bucket, cats in _FINANCE_BUCKETS.items():
            if cat in cats:
                buckets[bucket].append(title)
    composite = [t for titles in buckets.values() for t in titles]
    return {
        "exchanges": {"count": len(buckets["exchanges"]), "titles": buckets["exchanges"][:8]},
        "commodities": {"count": len(buckets["commodities"]), "titles": buckets["commodities"][:8]},
        "crypto": {"count": len(buckets["crypto"]), "titles": buckets["crypto"][:8]},
        "composite": {"count": len(composite), "titles": composite[:12]},
    }


def _load_json(path: str) -> dict[str, Any] | None:
    if not os.path.isfile(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else None
    except (OSError, json.JSONDecodeError):
        return None


def _world_path(reports_root: str, day: str) -> str:
    return os.path.join(reports_root, day, "world-news", "world-news-data.json")


def _finance_path(reports_root: str, day: str) -> str:
    return os.path.join(reports_root, day, "finance-news", "finance-news-data.json")


def _briefing_path(reports_root: str, day: str) -> str:
    filtered = os.path.join(reports_root, day, "briefing-data-filtered.json")
    raw = os.path.join(reports_root, day, "briefing-data.json")
    return filtered if os.path.isfile(filtered) else raw


LOOKBACK_ALLOWED = (1, 2, 5, 7)


def clamp_lookback(value: Any) -> int:
    try:
        n = int(value)
    except (TypeError, ValueError):
        return 1
    return n if n in LOOKBACK_ALLOWED else 1


def date_window(end: str, lookback_days: int) -> list[str]:
    try:
        day = datetime.strptime(end, "%Y-%m-%d")
    except ValueError:
        return [end]
    n = clamp_lookback(lookback_days)
    return [(day - timedelta(days=i)).strftime("%Y-%m-%d") for i in range(n)]


def recent_report_days(reports_root: str, end: str, lookback_days: int) -> list[str]:
    """Newest N folders that actually contain world-news JSON, ending at `end`."""
    n = clamp_lookback(lookback_days)
    try:
        end_d = datetime.strptime(end, "%Y-%m-%d")
    except ValueError:
        return [end]
    found: list[str] = []
    if os.path.isdir(reports_root):
        names = []
        for name in os.listdir(reports_root):
            if len(name) != 10:
                continue
            try:
                d = datetime.strptime(name, "%Y-%m-%d")
            except ValueError:
                continue
            if d <= end_d and os.path.isfile(_world_path(reports_root, name)):
                names.append(name)
        names.sort(reverse=True)
        found = names[:n]
    return found or [end]


def _item_key(item: dict[str, Any]) -> str:
    url = str(item.get("url") or "").strip()
    if url:
        return "u:" + url
    title = str(item.get("title") or item.get("title_zh") or "").strip().lower()
    return "t:" + title if title else ""


def _merge_days(
    reports_root: str,
    days: list[str],
    path_fn,
    flatten_fn,
) -> list[dict[str, Any]]:
    seen: set[str] = set()
    out: list[dict[str, Any]] = []
    for day in days:
        raw = _load_json(path_fn(reports_root, day))
        for it in flatten_fn(raw):
            key = _item_key(it)
            if not key or key in seen:
                continue
            seen.add(key)
            row = dict(it)
            row["report_date"] = day
            out.append(row)
    return out


def _flatten_ai(data: dict[str, Any] | None) -> list[dict[str, Any]]:
    out = []
    for src in (data or {}).get("per_source_data") or []:
        name = src.get("source_name") or src.get("name") or "AI"
        for it in src.get("items") or []:
            row = dict(it)
            row["source"] = name
            row["news_category"] = "technology"
            out.append(row)
    return out


def layers_for_item(it: dict[str, Any], allowed: set[str]) -> list[str]:
    layer_ids: list[str] = list(it.get("streams") or [])
    cat = it.get("news_category")
    if cat:
        layer_ids.append(f"news_{cat}")
    fc = str(it.get("finance_category") or "")
    for bucket, cats in _FINANCE_BUCKETS.items():
        if fc in cats:
            layer_ids.append(f"finance_{bucket}")
    if it.get("happy"):
        layer_ids.append("happy")
    if it.get("energy"):
        layer_ids.append("energy")
    return [lid for lid in dict.fromkeys(layer_ids) if lid in allowed]


def items_for_variant(
    variant: str,
    world_items: list[dict[str, Any]],
    ai_items: list[dict[str, Any]],
    finance_items: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    if variant == "tech":
        return world_items + ai_items
    if variant == "finance":
        return finance_items
    if variant in ("commodity", "energy"):
        return finance_items + world_items
    return world_items


def _headline_row(it: dict[str, Any], report_date: str, layers: list[str]) -> dict[str, Any]:
    return {
        "title": it.get("title_zh") or it.get("title"),
        "source": it.get("source"),
        "url": it.get("url"),
        "streams": it.get("streams"),
        "layers": layers,
        "news_category": it.get("news_category"),
        "hubs": [h["label"] for h in it.get("hubs") or []],
        "hub_ids": [h["id"] for h in it.get("hubs") or []],
        "country_ids": list(it.get("country_ids") or []),
        "report_date": it.get("report_date") or report_date,
    }


def _points_for(items: list[dict[str, Any]], variant: str) -> list[dict[str, Any]]:
    allowed = {ly["id"] for ly in layers_for_variant(variant)}
    points = []
    for it in items:
        layer_ids = layers_for_item(it, allowed)
        if not layer_ids:
            continue
        hubs = it.get("hubs") or []
        if not hubs:
            continue
        title = it.get("title_zh") or it.get("title") or ""
        for hub in hubs:
            for lid in layer_ids:
                points.append({
                    "layer": lid,
                    "lat": hub["lat"],
                    "lon": hub["lon"],
                    "hub_id": hub["id"],
                    "hub_label": hub.get("label") or hub["id"],
                    "title": title,
                    "source": it.get("source") or "",
                    "url": it.get("url") or "",
                })
    return points


def build_dashboard(
    reports_root: str,
    report_date: str,
    variant: str = "world",
    lookback_days: int = 1,
) -> dict[str, Any]:
    variant = variant if variant in VARIANTS else "world"
    lookback = clamp_lookback(lookback_days)
    days = recent_report_days(reports_root, report_date, lookback)
    world_raw = _merge_days(reports_root, days, _world_path, flatten_world_items)
    finance = _merge_days(reports_root, days, _finance_path, flatten_finance_items)
    ai_raw = _merge_days(reports_root, days, _briefing_path, _flatten_ai)

    world_items = [enrich_item(it) for it in world_raw]
    ai_items = [enrich_item(it) for it in ai_raw]
    finance_items = [enrich_item(it) for it in finance]
    pool = items_for_variant(variant, world_items, ai_items, finance_items)
    points = _points_for(pool, variant)
    allowed = {ly["id"] for ly in layers_for_variant(variant)}
    headlines = []
    for it in pool:
        layers = layers_for_item(it, allowed)
        if not layers:
            continue
        headlines.append(_headline_row(it, report_date, layers))
    finance_payload = {"categories": []}
    by_cat: dict[str, list] = {}
    for it in finance:
        cat = it.get("finance_category") or "markets"
        by_cat.setdefault(cat, []).append(it)
    finance_payload["categories"] = [{"category": k, "items": v} for k, v in by_cat.items()]

    return {
        "date": report_date,
        "lookback": lookback,
        "days": days,
        "variant": variant,
        "variants": VARIANTS,
        "layer_catalog": layers_for_variant(variant),
        "engine": {"globe": "globe.gl", "flat": "deck.gl"},
        "stats": {
            "world_items": len(world_items),
            "ai_items": len(ai_items),
            "points": len(points),
        },
        "points": points[:800],
        "headlines": headlines[:200],
        "correlation": compute_correlation(world_items),
        "finance_radar": finance_radar(finance_payload),
        "panels": _panels_for(variant),
    }


def _panels_for(variant: str) -> list[dict[str, str]]:
    common = [
        {"id": "headlines", "label": "Headlines"},
        {"id": "layers", "label": "Map layers"},
    ]
    extra = {
        "world": [
            {"id": "correlation", "label": "Cross-stream correlation"},
        ],
        "tech": [{"id": "headlines", "label": "AI & tech headlines"}],
        "finance": [{"id": "finance_radar", "label": "Finance radar"}],
        "commodity": [{"id": "finance_radar", "label": "Commodities radar"}],
        "happy": [{"id": "headlines", "label": "Constructive news"}],
        "energy": [
            {"id": "finance_radar", "label": "Energy radar"},
            {"id": "correlation", "label": "Chokepoint correlation"},
        ],
    }
    seen = set()
    out = []
    for p in common + extra.get(variant, []):
        if p["id"] in seen:
            continue
        seen.add(p["id"])
        out.append(p)
    return out


def ollama_brief(dashboard: dict[str, Any], host: str | None = None, model: str | None = None) -> str:
    import requests

    host = host or os.environ.get("OLLAMA_HOST", "http://localhost:11434")
    model = model or os.environ.get("OLLAMA_MODEL_FAST", "qwen3:1.7b")
    corr = dashboard.get("correlation") or []
    headlines = [h.get("title") or "" for h in (dashboard.get("headlines") or [])[:12]]
    prompt = (
        f"用简体中文写一段不超过180字的态势简报。"
        f"变体={dashboard.get('variant')} 日期={dashboard.get('date')}。"
        f"收敛信号数={len(corr)}。"
        f"标题: " + " | ".join(headlines)
    )
    resp = requests.post(
        f"{host}/api/chat",
        json={
            "model": model,
            "messages": [
                {"role": "system", "content": "你是本地地缘简报助手。只依据给定标题，不要编造未提供的事实。"},
                {"role": "user", "content": prompt},
            ],
            "stream": False,
            "think": False,
            "options": {"temperature": 0.2, "num_predict": 400},
        },
        timeout=90,
    )
    resp.raise_for_status()
    return (resp.json().get("message") or {}).get("content") or ""


def headlines_matching_hub(headlines: list[dict[str, Any]], hub_id: str) -> list[dict[str, Any]]:
    hid = (hub_id or "").strip()
    if not hid:
        return list(headlines)
    needle = hid.lower()
    out = []
    for h in headlines:
        if hid in (h.get("hub_ids") or []) or hid in (h.get("country_ids") or []):
            out.append(h)
            continue
        if any(str(x).lower() == needle for x in (h.get("hubs") or [])):
            out.append(h)
    return out


def ollama_hub_insight(
    dashboard: dict[str, Any],
    hub_id: str,
    host: str | None = None,
    model: str | None = None,
) -> str:
    import requests

    host = host or os.environ.get("OLLAMA_HOST", "http://localhost:11434")
    model = model or os.environ.get("OLLAMA_MODEL_FAST", "qwen3:1.7b")
    matched = headlines_matching_hub(dashboard.get("headlines") or [], hub_id)
    titles = [h.get("title") or "" for h in matched[:12] if h.get("title")]
    if not titles:
        return "该地点在当前时间窗口没有可定位新闻。"
    label = hub_id
    for p in dashboard.get("points") or []:
        if p.get("hub_id") == hub_id and p.get("hub_label"):
            label = p["hub_label"]
            break
    prompt = (
        f"用简体中文写不超过120字，只依据下列标题说明「{label}」相关态势，不要编造未提供的事实。"
        f"标题: " + " | ".join(titles)
    )
    resp = requests.post(
        f"{host}/api/chat",
        json={
            "model": model,
            "messages": [
                {"role": "system", "content": "你是本地地缘简报助手。只依据给定标题，不要编造未提供的事实。"},
                {"role": "user", "content": prompt},
            ],
            "stream": False,
            "think": False,
            "options": {"temperature": 0.2, "num_predict": 280},
        },
        timeout=90,
    )
    resp.raise_for_status()
    return (resp.json().get("message") or {}).get("content") or ""
