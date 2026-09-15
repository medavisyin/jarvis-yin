"""Standalone / unified Layer-1 market fetch respects East Money circuit."""

from __future__ import annotations

import os
import sys

import pandas as pd

_STOCK = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "scripts", "stock"))
if _STOCK not in sys.path:
    sys.path.insert(0, _STOCK)

import eastmoney_throttle as em  # noqa: E402


def setup_function(_fn=None):
    em.reset_for_tests(max_concurrent=2, min_interval_sec=0.0)
    em.reset_circuit_for_tests(failure_threshold=3, open_cooldown_sec=60)


def test_scanner_layer1_skips_spot_em_when_circuit_open(monkeypatch):
    import scanner as sc

    for _ in range(3):
        em.record_eastmoney_failure(ConnectionError("RemoteDisconnected"))

    spot_calls = {"n": 0}

    def boom(*a, **k):
        spot_calls["n"] += 1
        raise AssertionError("spot_em should be skipped")

    monkeypatch.setattr(sc.ak, "stock_zh_a_spot_em", boom)

    fallback = pd.DataFrame(
        {
            "代码": ["600519"],
            "名称": ["茅台"],
            "涨跌幅": [1.0],
            "换手率": [2.0],
            "成交额": [50_000_000],
            "市盈率-动态": [20.0],
            "最新价": [100.0],
            "总市值": [1e11],
        }
    )
    monkeypatch.setattr(sc, "_fetch_market_eastmoney", lambda: fallback)

    picks, total = sc._layer1_quick_filter(set(), market_df=None)
    assert spot_calls["n"] == 0
    assert total >= 1
    assert picks


def test_unified_skips_spot_em_when_circuit_open(monkeypatch):
    import unified_scanner as us

    for _ in range(3):
        em.record_eastmoney_failure(ConnectionError("RemoteDisconnected"))

    class _Rss:
        @staticmethod
        def _fetch_market_eastmoney_direct():
            return pd.DataFrame({"代码": ["600519"], "名称": ["茅台"]})

    class _Sc:
        @staticmethod
        def _fetch_market_eastmoney():
            raise AssertionError("should not reach")

    monkeypatch.setattr(us, "_ensure_path", lambda: None)
    monkeypatch.setattr(us, "_safe_import", lambda name: _Rss() if name == "right_side_scanner" else _Sc())

    import akshare as ak

    def boom(*a, **k):
        raise AssertionError("spot_em should be skipped")

    monkeypatch.setattr(ak, "stock_zh_a_spot_em", boom)

    df = us._fetch_shared_market_df()
    assert df is not None and not df.empty
    assert str(df.iloc[0]["代码"]) == "600519"
