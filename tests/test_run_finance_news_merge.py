"""Merge tests for run-finance-news orchestrator."""

from __future__ import annotations

import importlib.util
import json
import os
import sys

_PIPELINE = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "scripts", "pipeline"))
if _PIPELINE not in sys.path:
    sys.path.insert(0, _PIPELINE)

_SCRIPT = os.path.join(_PIPELINE, "run-finance-news.py")
_spec = importlib.util.spec_from_file_location("run_finance_news", _SCRIPT)
_mod = importlib.util.module_from_spec(_spec)
assert _spec.loader is not None
_spec.loader.exec_module(_mod)
merge_news = _mod.merge_news


def test_merge_finance_news_applies_filter(tmp_path):
    reuters = {
        "items": [
            {
                "title": "Fed signals rate cut",
                "summary": "Powell speech moves markets",
                "category": "economics",
                "date": "2026-07-29",
            },
            {
                "title": "Celebrity wedding draws fans",
                "summary": "Entertainment news",
                "category": "politics",
                "date": "2026-07-29",
            },
        ]
    }
    china = {
        "items": [
            {
                "title": "央行降准释放流动性",
                "summary": "PBOC policy move",
                "category": "finance",
                "date": "2026-07-29",
                "source": "财联社",
            }
        ]
    }
    (tmp_path / "reuters.json").write_text(json.dumps(reuters), encoding="utf-8")
    (tmp_path / "china-news.json").write_text(json.dumps(china), encoding="utf-8")

    merged = merge_news(str(tmp_path), report_date="2026-07-29")
    titles = [it["title"] for cat in merged["categories"] for it in cat["items"]]
    assert any("Fed" in t for t in titles)
    assert any("降准" in t for t in titles)
    assert not any("Celebrity" in t for t in titles)
    assert merged["total_items"] >= 2
    assert "categories" in merged


def test_merge_report_date_penalizes_non_matching_day(tmp_path):
    data = {
        "items": [
            {
                "title": "Fed signals rate cut",
                "summary": "Powell speech",
                "date": "2026-07-01",
            },
            {
                "title": "Trump announces new China tariffs",
                "summary": "trade war",
                "date": "2026-07-29",
            },
        ]
    }
    (tmp_path / "reuters.json").write_text(json.dumps(data), encoding="utf-8")
    merged = merge_news(str(tmp_path), report_date="2026-07-29")
    items = [it for cat in merged["categories"] for it in cat["items"]]
    by_title = {it["title"]: it for it in items}
    assert by_title["Trump announces new China tariffs"]["impact_score"] > by_title[
        "Fed signals rate cut"
    ]["impact_score"]
    assert by_title["Fed signals rate cut"].get("date_uncertain") is True
