"""Unit tests for East Money request throttle (Approach 1 fetch resilience)."""

from __future__ import annotations

import os
import sys
import threading
import time

_STOCK = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "scripts", "stock"))
if _STOCK not in sys.path:
    sys.path.insert(0, _STOCK)

import eastmoney_throttle as throttle  # noqa: E402


def setup_function(_fn=None):
    throttle.reset_for_tests(max_concurrent=2, min_interval_sec=0.05)


def test_throttle_limits_concurrent_calls():
    throttle.reset_for_tests(max_concurrent=2, min_interval_sec=0.0)
    in_flight = 0
    peak = 0
    lock = threading.Lock()

    def work():
        nonlocal in_flight, peak
        with throttle.eastmoney_slot():
            with lock:
                in_flight += 1
                peak = max(peak, in_flight)
            time.sleep(0.08)
            with lock:
                in_flight -= 1

    threads = [threading.Thread(target=work) for _ in range(6)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=5)
    assert peak <= 2


def test_throttle_enforces_min_interval():
    throttle.reset_for_tests(max_concurrent=1, min_interval_sec=0.12)
    times = []
    for _ in range(3):
        with throttle.eastmoney_slot():
            times.append(time.monotonic())
    gaps = [times[i] - times[i - 1] for i in range(1, len(times))]
    assert all(g >= 0.10 for g in gaps)


def test_needs_ff_backfill():
    from fetch_resilience import needs_ff_backfill

    assert needs_ff_backfill({"ff_data_missing": True}) is True
    assert needs_ff_backfill({"ff_signals": {}, "ff_data_missing": False}) is True
    assert needs_ff_backfill({"ff_signals": {"data_days": 2}}) is True
    assert needs_ff_backfill({"ff_signals": {"data_days": 5}, "ff_data_missing": False}) is False


def test_score_left_ff_covers_phases():
    from fetch_resilience import score_left_ff

    assert score_left_ff({"data_days": 5, "smart_money_phase": "出货期"}) == 25
    assert score_left_ff({"data_days": 5, "smart_money_phase": "拉升期"}) == 55
    assert score_left_ff(None) == 50


def test_backfill_clears_cache_and_repairs(monkeypatch):
    import scan_cache
    from fetch_resilience import backfill_fund_flow

    scan_cache.reset()
    scan_cache.set_ff("600000", {"data_days": 0})

    calls = {"n": 0}

    def fake_signals(sym):
        calls["n"] += 1
        return {
            "data_days": 10,
            "smart_money_phase": "布局期",
            "accumulation_score": 40,
            "accumulation_signal": True,
            "main_net_3d": 1e8,
            "main_pct_3d": 4.0,
        }

    monkeypatch.setattr("china_market_data.stock_fund_flow_signals", fake_signals)

    stock = {
        "symbol": "600000",
        "ff_data_missing": True,
        "ff_signals": {},
        "ff_score": 50,
    }
    repaired = backfill_fund_flow([stock], sleep_between=0)
    assert repaired == 1
    assert calls["n"] == 1
    assert stock["ff_data_missing"] is False
    assert stock["ff_signals"]["data_days"] == 10
    assert stock["ff_score"] > 50
    assert scan_cache.get_ff("600000")["data_days"] == 10


def test_backfill_marks_missing_when_still_empty(monkeypatch):
    import scan_cache
    from fetch_resilience import backfill_fund_flow

    scan_cache.reset()
    monkeypatch.setattr(
        "china_market_data.stock_fund_flow_signals",
        lambda sym: {"data_days": 1},
    )
    stock = {"symbol": "000001", "ff_data_missing": True, "ff_signals": {}, "ff_score": 50}
    repaired = backfill_fund_flow([stock], sleep_between=0)
    assert repaired == 0
    assert stock["ff_data_missing"] is True
