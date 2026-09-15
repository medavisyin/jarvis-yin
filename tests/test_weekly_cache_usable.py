"""_cache_usable must not treat a current local daily.csv as stale
just because the caller asked for an end_date in the future
(backtest_weekly passes end+20 days as fetch_end)."""

from __future__ import annotations

import os
import sys
from datetime import datetime, timedelta

import pandas as pd

_STOCK = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "scripts", "stock"))
if _STOCK not in sys.path:
    sys.path.insert(0, _STOCK)

from weekly_selector import MIN_LISTING_DAYS, _cache_usable  # noqa: E402


def _daily_ending(last_date, n=80):
    dates = pd.bdate_range(end=pd.Timestamp(last_date), periods=n)
    return pd.DataFrame({
        "date": dates,
        "open": 10.0,
        "close": 10.0,
        "high": 10.1,
        "low": 9.9,
        "volume": 1_000_000,
    })


def test_cache_usable_when_requested_end_is_in_the_future():
    today = datetime.now().date()
    cache = _daily_ending(today, n=max(80, MIN_LISTING_DAYS + 10))
    fetch_end = (today + timedelta(days=20)).strftime("%Y-%m-%d")
    fetch_start = (today - timedelta(days=400)).strftime("%Y-%m-%d")
    assert _cache_usable(cache, start_date=fetch_start, end_date=fetch_end) is True


def test_cache_still_unusable_when_last_bar_is_stale():
    today = datetime.now().date()
    cache = _daily_ending(today - timedelta(days=30), n=max(80, MIN_LISTING_DAYS + 10))
    fetch_end = (today + timedelta(days=20)).strftime("%Y-%m-%d")
    fetch_start = (today - timedelta(days=400)).strftime("%Y-%m-%d")
    assert _cache_usable(cache, start_date=fetch_start, end_date=fetch_end) is False
