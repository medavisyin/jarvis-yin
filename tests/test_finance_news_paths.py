"""Tests for finance_news_paths helper."""

from __future__ import annotations

import os
import sys

_PIPELINE = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "scripts", "pipeline"))
if _PIPELINE not in sys.path:
    sys.path.insert(0, _PIPELINE)

from finance_news_paths import (  # noqa: E402
    finance_news_data_path,
    finance_news_json_for_date_dir,
    is_canonical_finance_path,
)


def test_prefers_finance_over_legacy(tmp_path):
    date = "2026-07-29"
    finance_dir = tmp_path / date / "finance-news"
    world_dir = tmp_path / date / "world-news"
    finance_dir.mkdir(parents=True)
    world_dir.mkdir(parents=True)
    finance_file = finance_dir / "finance-news-data.json"
    world_file = world_dir / "world-news-data.json"
    finance_file.write_text("{}", encoding="utf-8")
    world_file.write_text("{}", encoding="utf-8")

    got = finance_news_data_path(str(tmp_path), date)
    assert got == str(finance_file)
    assert is_canonical_finance_path(got)
    assert finance_news_json_for_date_dir(str(tmp_path / date)) == str(finance_file)


def test_falls_back_to_world_news(tmp_path):
    date = "2026-07-28"
    world_dir = tmp_path / date / "world-news"
    world_dir.mkdir(parents=True)
    world_file = world_dir / "world-news-data.json"
    world_file.write_text("{}", encoding="utf-8")

    got = finance_news_data_path(str(tmp_path), date)
    assert got == str(world_file)
    assert not is_canonical_finance_path(got)


def test_missing_returns_none(tmp_path):
    assert finance_news_data_path(str(tmp_path), "2099-01-01") is None
    assert is_canonical_finance_path(None) is False
