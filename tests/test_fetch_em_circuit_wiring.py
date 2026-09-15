"""Wiring tests: fetch_market_data respects East Money circuit breaker."""

from __future__ import annotations

import json
import os
import sys

import pandas as pd

_STOCK = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "scripts", "stock"))
if _STOCK not in sys.path:
    sys.path.insert(0, _STOCK)

import eastmoney_throttle as em  # noqa: E402
import fetch_market_data as fmd  # noqa: E402


def setup_function(_fn=None):
    em.reset_for_tests(max_concurrent=2, min_interval_sec=0.0)
    em.reset_circuit_for_tests(failure_threshold=3, open_cooldown_sec=60)


def _sample_ohlcv() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "日期": ["2026-07-30"],
            "开盘": [1.0],
            "收盘": [1.1],
            "最高": [1.2],
            "最低": [0.9],
            "成交量": [100],
            "成交额": [0.0],
            "振幅": [0.0],
            "涨跌幅": [1.0],
            "涨跌额": [0.1],
            "换手率": [0.0],
        }
    )


def test_ohlcv_skips_em_when_circuit_open(monkeypatch, tmp_path):
    for _ in range(3):
        em.record_eastmoney_failure(ConnectionError("RemoteDisconnected"))

    calls = {"ak": 0}

    def boom(*a, **k):
        calls["ak"] += 1
        raise AssertionError("should not call ak hist")

    monkeypatch.setattr(fmd, "_fetch_ohlcv_akshare", boom)
    monkeypatch.setattr(fmd, "_fetch_ohlcv_sina", lambda *a, **k: _sample_ohlcv())
    monkeypatch.setattr(fmd, "validate_and_persist", lambda *a, **k: {"passed": True})
    monkeypatch.setattr(fmd, "_symbol_dir", lambda sym: str(tmp_path / sym))
    monkeypatch.setattr(
        fmd,
        "_save_daily_csv",
        lambda df, sym: str(tmp_path / sym / "daily.csv"),
    )

    df = fmd.fetch_daily_ohlcv("600519", start_date="20260701", end_date="20260731")
    assert calls["ak"] == 0
    assert len(df) == 1


def test_ohlcv_caps_em_retries_then_falls_back_to_sina(monkeypatch, tmp_path):
    calls = {"ak": 0}

    def fail_ak(*a, **k):
        calls["ak"] += 1
        raise ConnectionError("RemoteDisconnected")

    monkeypatch.setattr(fmd, "_fetch_ohlcv_akshare", fail_ak)
    monkeypatch.setattr(fmd, "_fetch_ohlcv_sina", lambda *a, **k: _sample_ohlcv())
    monkeypatch.setattr(fmd, "validate_and_persist", lambda *a, **k: {"passed": True})
    monkeypatch.setattr(fmd, "_symbol_dir", lambda sym: str(tmp_path / sym))
    monkeypatch.setattr(
        fmd,
        "_save_daily_csv",
        lambda df, sym: str(tmp_path / sym / "daily.csv"),
    )
    monkeypatch.setattr(fmd.time, "sleep", lambda *_a, **_k: None)

    df = fmd.fetch_daily_ohlcv("600519", start_date="20260701", end_date="20260731")
    assert calls["ak"] == 2
    assert len(df) == 1


def test_ohlcv_half_open_probe_is_single_attempt(monkeypatch, tmp_path):
    import time as _time

    em.reset_circuit_for_tests(failure_threshold=3, open_cooldown_sec=10)
    for _ in range(3):
        em.record_eastmoney_failure(ConnectionError("RemoteDisconnected"))
    monkeypatch.setattr(em, "_circuit_opened_mono", _time.monotonic() - 11)

    calls = {"ak": 0}

    def fail_ak(*a, **k):
        calls["ak"] += 1
        raise ConnectionError("RemoteDisconnected")

    monkeypatch.setattr(fmd, "_fetch_ohlcv_akshare", fail_ak)
    monkeypatch.setattr(fmd, "_fetch_ohlcv_sina", lambda *a, **k: _sample_ohlcv())
    monkeypatch.setattr(fmd, "validate_and_persist", lambda *a, **k: {"passed": True})
    monkeypatch.setattr(fmd, "_symbol_dir", lambda sym: str(tmp_path / sym))
    monkeypatch.setattr(
        fmd,
        "_save_daily_csv",
        lambda df, sym: str(tmp_path / sym / "daily.csv"),
    )
    monkeypatch.setattr(fmd.time, "sleep", lambda *_a, **_k: None)

    df = fmd.fetch_daily_ohlcv("600519", start_date="20260701", end_date="20260731")
    assert calls["ak"] == 1
    assert len(df) == 1


def test_profile_half_open_probe_is_single_attempt(monkeypatch):
    import time as _time

    em.reset_circuit_for_tests(failure_threshold=3, open_cooldown_sec=10)
    for _ in range(3):
        em.record_eastmoney_failure(ConnectionError("RemoteDisconnected"))
    monkeypatch.setattr(em, "_circuit_opened_mono", _time.monotonic() - 11)

    # Grant probe by calling should_skip once would happen inside fetch_company_profile
    calls = {"n": 0}
    retry_kwargs = {}

    def fake_retry(fn, *a, retries=6, **k):
        calls["n"] += 1
        retry_kwargs["retries"] = retries
        raise ConnectionError("RemoteDisconnected")

    monkeypatch.setattr(fmd, "_retry", fake_retry)
    monkeypatch.setattr(fmd.time, "sleep", lambda *_a, **_k: None)

    # Directly call _fetch_profile_akshare while circuit open (after grant via should_skip in parent)
    # Simulate: parent already decided not to skip; circuit still open
    out = fmd._fetch_profile_akshare("600519")
    assert out == {}
    assert calls["n"] == 1
    assert retry_kwargs["retries"] == 1


def test_profile_skips_akshare_when_circuit_open(monkeypatch, tmp_path):
    for _ in range(3):
        em.record_eastmoney_failure(ConnectionError("RemoteDisconnected"))

    ak_calls = {"n": 0}

    def boom_ak(sym):
        ak_calls["n"] += 1
        raise AssertionError("ak profile should be skipped")

    monkeypatch.setattr(fmd, "_fetch_profile_akshare", boom_ak)
    monkeypatch.setattr(
        fmd,
        "_fetch_profile_em_survey",
        lambda sym: {"股票代码": sym, "行业": "白酒", "股票简称": "茅台"},
    )

    def _sym_dir(sym):
        d = tmp_path / sym
        d.mkdir(parents=True, exist_ok=True)
        return str(d)

    monkeypatch.setattr(fmd, "_symbol_dir", _sym_dir)

    profile = fmd.fetch_company_profile("600519")
    assert ak_calls["n"] == 0
    assert profile.get("行业") == "白酒"
    saved = tmp_path / "600519" / "profile.json"
    assert saved.is_file()
    assert json.loads(saved.read_text(encoding="utf-8"))["行业"] == "白酒"
