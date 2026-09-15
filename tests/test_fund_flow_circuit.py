"""Fund-flow fetch respects East Money circuit breaker."""

from __future__ import annotations

import os
import sys

import pandas as pd

_STOCK = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "scripts", "stock"))
if _STOCK not in sys.path:
    sys.path.insert(0, _STOCK)

import eastmoney_throttle as em  # noqa: E402
import china_market_data as cmd  # noqa: E402


def setup_function(_fn=None):
    em.reset_for_tests(max_concurrent=2, min_interval_sec=0.0)
    em.reset_circuit_for_tests(failure_threshold=3, open_cooldown_sec=60)


def test_fund_flow_skips_ak_when_circuit_open(monkeypatch, tmp_path):
    for _ in range(3):
        em.record_eastmoney_failure(ConnectionError("RemoteDisconnected"))

    calls = {"n": 0}

    def boom(*a, **k):
        calls["n"] += 1
        raise AssertionError("should not call fund flow API")

    monkeypatch.setattr(cmd.ak, "stock_individual_fund_flow", boom)
    monkeypatch.setattr(cmd, "_CACHE_FUND_FLOW", str(tmp_path))
    monkeypatch.setattr(cmd, "_cache_fresh", lambda *a, **k: False)

    df = cmd.fetch_stock_fund_flow("600519")
    assert calls["n"] == 0
    assert df.empty


def test_fund_flow_uses_cache_when_circuit_open(monkeypatch, tmp_path):
    for _ in range(3):
        em.record_eastmoney_failure(ConnectionError("RemoteDisconnected"))

    cache = tmp_path / "600519.csv"
    pd.DataFrame({"日期": ["2026-07-01"], "主力净流入": [1.0]}).to_csv(cache, index=False)

    def boom(*a, **k):
        raise AssertionError("should not call API")

    monkeypatch.setattr(cmd.ak, "stock_individual_fund_flow", boom)
    monkeypatch.setattr(cmd, "_CACHE_FUND_FLOW", str(tmp_path))
    # Force stale so code path hits circuit skip + cache file read
    monkeypatch.setattr(cmd, "_cache_fresh", lambda *a, **k: False)

    df = cmd.fetch_stock_fund_flow("600519")
    assert not df.empty
    assert len(df) == 1


def test_backfill_exits_early_when_circuit_open(monkeypatch):
    from fetch_resilience import backfill_fund_flow
    import scan_cache

    for _ in range(3):
        em.record_eastmoney_failure(ConnectionError("RemoteDisconnected"))

    calls = {"n": 0}

    def boom(sym):
        calls["n"] += 1
        raise AssertionError("backfill should not fetch when circuit open")

    monkeypatch.setattr("china_market_data.stock_fund_flow_signals", boom)
    scan_cache.reset()
    stock = {"symbol": "600000", "ff_data_missing": True, "ff_signals": {}}
    repaired = backfill_fund_flow([stock], sleep_between=2.0)
    assert repaired == 0
    assert calls["n"] == 0
