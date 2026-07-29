"""Resolve finance-news JSON paths with legacy world-news fallback."""

from __future__ import annotations

import os


def finance_news_data_path(reports_root: str, date_str: str) -> str | None:
    """Return first existing finance/world news data path for *date_str*."""
    candidates = [
        os.path.join(reports_root, date_str, "finance-news", "finance-news-data.json"),
        os.path.join(reports_root, date_str, "world-news", "world-news-data.json"),
        os.path.join(reports_root, date_str, "world-news-data.json"),
    ]
    for path in candidates:
        if os.path.isfile(path):
            return path
    return None


def finance_news_json_for_date_dir(date_dir: str) -> str | None:
    """Resolve finance/legacy news JSON given a YYYY-MM-DD date directory."""
    date_dir = os.path.normpath(date_dir)
    return finance_news_data_path(os.path.dirname(date_dir), os.path.basename(date_dir))


def is_canonical_finance_path(path: str | None) -> bool:
    """True when *path* is the new finance-news-data.json (not legacy world-news)."""
    if not path:
        return False
    norm = path.replace("\\", "/").lower()
    return "/finance-news/finance-news-data.json" in norm
