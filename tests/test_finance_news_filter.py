"""Unit tests for finance market-impact filter."""

from __future__ import annotations

import os
import sys

_PIPELINE = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "scripts", "pipeline"))
if _PIPELINE not in sys.path:
    sys.path.insert(0, _PIPELINE)

from finance_news_filter import (  # noqa: E402
    assign_region,
    filter_and_rank_items,
    score_market_impact,
)


def test_keeps_circuit_breaker_and_fed():
    items = [
        {
            "title": "Korea stock market hits circuit breaker",
            "summary": "KOSPI plunges 8%",
            "source": "Reuters",
        },
        {
            "title": "Celebrity wedding draws fans",
            "summary": "Entertainment news",
            "source": "Weibo",
        },
        {
            "title": "Fed signals rate cut",
            "summary": "Powell speech",
            "source": "CNBC",
        },
    ]
    out = filter_and_rank_items(items, report_date="2026-07-29")
    titles = [i["title"] for i in out]
    assert any("circuit breaker" in t.lower() for t in titles)
    assert any("Fed" in t for t in titles)
    assert not any("Celebrity" in t for t in titles)


def test_assign_region_china_us_apac():
    assert assign_region({"title": "PBOC cuts RRR", "source": "财联社"}) == "china"
    assert assign_region({"title": "S&P 500 futures jump", "source": "CNBC"}) == "us"
    assert assign_region({"title": "Nikkei surges on BOJ", "source": "Reuters"}) == "apac"


def test_higher_impact_sorts_first():
    items = [
        {
            "title": "Minor midcap earnings beat",
            "summary": "small company",
            "source": "Yahoo",
        },
        {
            "title": "Trump announces new China tariffs",
            "summary": "trade war",
            "source": "Reuters",
        },
    ]
    out = filter_and_rank_items(items, report_date="2026-07-29")
    assert out, "expected kept items"
    assert "tariff" in out[0]["title"].lower() or "Trump" in out[0]["title"]


def test_neither_keep_nor_drop_is_discarded():
    items = [
        {
            "title": "Local weather turns cloudy",
            "summary": "Mild temperatures expected",
            "source": "Reuters",
        },
    ]
    out = filter_and_rank_items(items, report_date="2026-07-29")
    assert out == []


def test_score_positive_for_keep_signals():
    assert score_market_impact({"title": "Fed rate decision", "summary": ""}) > 0
    assert score_market_impact({"title": "Celebrity wedding", "summary": "娱乐"}) == 0


def test_source_display_name_does_not_keep_item():
    """CNBC/Reuters display names contain 'Markets' — must not bypass default-deny."""
    item = {
        "title": "Something unrelated happens downtown",
        "summary": "Local event",
        "source": "CNBC Markets",
    }
    assert score_market_impact(item) == 0
    out = filter_and_rank_items([item], report_date="2026-07-29")
    assert out == []


def test_china_hot_search_gate():
    import importlib.util

    china_path = os.path.normpath(
        os.path.join(os.path.dirname(__file__), "..", "scripts", "fetchers", "news", "fetch-china-news.py")
    )
    spec = importlib.util.spec_from_file_location("fetch_china_news", china_path)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    assert mod.keep_china_hot_item("央行降准")
    assert not mod.keep_china_hot_item("某明星恋情曝光")


def test_diversify_preserves_pulled_region_in_front():
    """Pulled china/apac items must remain in the front window (no re-sort undo)."""
    from finance_news_filter import _diversify_front

    # Front: only US high-score items; china item sits after window
    items = []
    for i in range(12):
        items.append({"title": f"US story {i}", "impact_score": 90 - i, "region": "us"})
    items.append({"title": "PBOC move", "impact_score": 50, "region": "china"})
    items.append({"title": "Nikkei jump", "impact_score": 45, "region": "apac"})
    out = _diversify_front(items, window=12)
    front_regions = {it["region"] for it in out[:14]}
    assert "china" in front_regions
    assert "apac" in front_regions
    # Inserted items should appear inside the expanded front, not buried at end
    china_idx = next(i for i, it in enumerate(out) if it["region"] == "china")
    assert china_idx < 14
