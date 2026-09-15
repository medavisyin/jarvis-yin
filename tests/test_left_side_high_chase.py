"""Left-side scanner must not treat missing/high prices as 吸筹横盘."""

from __future__ import annotations

import os
import sys

import pandas as pd

_STOCK = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "scripts", "stock"))
if _STOCK not in sys.path:
    sys.path.insert(0, _STOCK)

import china_market_data as cmd  # noqa: E402
import akshare  # noqa: E402


def _inflow_ff_df() -> pd.DataFrame:
    """Five days of strong main-force inflow (enough to pass 布局期 fund_strength)."""
    return pd.DataFrame({
        "主力净流入-净额": [8e6, 9e6, 1e7, 1.1e7, 1.2e7],
        "主力净流入-净占比": [2.0, 2.0, 2.0, 2.0, 2.0],
    })


def test_missing_price_does_not_label_layout(monkeypatch, tmp_path):
    def boom(*_a, **_k):
        raise RuntimeError("akshare hist unavailable")

    monkeypatch.setattr(cmd, "STOCK_DATA_DIR", str(tmp_path))
    monkeypatch.setattr(akshare, "stock_zh_a_hist", boom)

    result = cmd.detect_smart_money_accumulation(
        "002758", _inflow_ff_df(), "主力净流入-净额", "主力净流入-净占比"
    )
    assert result["smart_money_phase"] != "布局期"
    assert result.get("accumulation_signal") is not True
    assert "缺失" in result.get("detail", "")


def test_twenty_day_runup_does_not_label_layout(monkeypatch, tmp_path):
    """Last 5 days flat near the high after a +15% 20-day run is not 布局期."""
    closes = [100.0] * 5 + [100.0 + i for i in range(1, 12)] + [115.0, 115.1, 114.8, 115.0, 115.2]
    hist = pd.DataFrame({"收盘": closes})

    monkeypatch.setattr(cmd, "STOCK_DATA_DIR", str(tmp_path))
    monkeypatch.setattr(akshare, "stock_zh_a_hist", lambda *a, **k: hist)

    result = cmd.detect_smart_money_accumulation(
        "603112", _inflow_ff_df(), "主力净流入-净额", "主力净流入-净占比"
    )
    assert result["smart_money_phase"] != "布局期"
    assert "20" in result.get("detail", "")


def test_quiet_five_day_without_big_runup_can_be_layout(monkeypatch, tmp_path):
    """5-day flat after a modest 20-day move can still be 布局期."""
    closes = [100.0] * 16 + [104.0, 104.2, 103.8, 104.0, 104.1]
    hist = pd.DataFrame({"收盘": closes})
    monkeypatch.setattr(cmd, "STOCK_DATA_DIR", str(tmp_path))
    monkeypatch.setattr(akshare, "stock_zh_a_hist", lambda *a, **k: hist)

    result = cmd.detect_smart_money_accumulation(
        "600000", _inflow_ff_df(), "主力净流入-净额", "主力净流入-净占比"
    )
    assert result["smart_money_phase"] == "布局期"

def test_near_20d_high_vetoes_buy():
    import scanner as sc

    assert sc.left_side_chase_veto_reason({"dd_20": -2.0})
    out = sc.apply_left_side_chase_veto({"verdict": "买入", "dd_20": -2.0, "symbol": "002758"})
    assert out["verdict"] != "买入"
    assert out.get("veto_reason")


def test_deep_pullback_is_not_vetoed():
    import scanner as sc

    assert sc.left_side_chase_veto_reason({"dd_20": -12.0}) is None


def test_rsi_reads_rsi_14_column():
    import scanner as sc

    df = pd.DataFrame({"rsi_14": [81.0]})
    rsi, overbought = sc._rsi_from_indicator_df(df)
    assert rsi == 81.0
    assert overbought is True


def test_local_daily_csv_used_when_akshare_down(monkeypatch, tmp_path):
    closes = [100.0] * 16 + [104.0, 104.2, 103.8, 104.0, 104.1]
    dates = pd.date_range("2026-01-01", periods=len(closes), freq="B")
    sym_dir = tmp_path / "600000"
    sym_dir.mkdir()
    pd.DataFrame({"日期": dates, "收盘": closes}).to_csv(
        sym_dir / "daily.csv", index=False, encoding="utf-8-sig"
    )

    def boom(*_a, **_k):
        raise RuntimeError("akshare hist unavailable")

    monkeypatch.setattr(cmd, "STOCK_DATA_DIR", str(tmp_path))
    monkeypatch.setattr(akshare, "stock_zh_a_hist", boom)

    result = cmd.detect_smart_money_accumulation(
        "600000", _inflow_ff_df(), "主力净流入-净额", "主力净流入-净占比"
    )
    assert result["smart_money_phase"] == "布局期"
    assert "+0.0%" not in result.get("detail", "")


def test_newest_first_local_csv_is_sorted(monkeypatch, tmp_path):
    """Chronological 20d +22% must not be 布局期 even if CSV rows are newest-first."""
    closes_chrono = (
        [90.0] * 5 + [90.0 + i for i in range(1, 12)] + [110.0, 110.1, 109.8, 110.0, 110.2]
    )
    dates = pd.date_range("2026-01-01", periods=len(closes_chrono), freq="B")
    sym_dir = tmp_path / "600001"
    sym_dir.mkdir()
    pd.DataFrame({
        "日期": list(reversed(list(dates))),
        "收盘": list(reversed(closes_chrono)),
    }).to_csv(sym_dir / "daily.csv", index=False, encoding="utf-8-sig")

    def boom(*_a, **_k):
        raise RuntimeError("akshare hist unavailable")

    monkeypatch.setattr(cmd, "STOCK_DATA_DIR", str(tmp_path))
    monkeypatch.setattr(akshare, "stock_zh_a_hist", boom)

    result = cmd.detect_smart_money_accumulation(
        "600001", _inflow_ff_df(), "主力净流入-净额", "主力净流入-净占比"
    )
    assert result["smart_money_phase"] != "布局期"


def test_zero_prev_close_is_missing_price_not_layout(monkeypatch, tmp_path):
    hist = pd.DataFrame({"收盘": [0.0, 0.0, 0.0, 0.0, 10.0]})
    monkeypatch.setattr(cmd, "STOCK_DATA_DIR", str(tmp_path))
    monkeypatch.setattr(akshare, "stock_zh_a_hist", lambda *a, **k: hist)
    result = cmd.detect_smart_money_accumulation(
        "000001", _inflow_ff_df(), "主力净流入-净额", "主力净流入-净占比"
    )
    assert result["smart_money_phase"] != "布局期"


def test_missing_dd_20_vetoes_buy():
    import scanner as sc

    reason = sc.left_side_chase_veto_reason({"symbol": "002758"})
    assert reason
    out = sc.apply_left_side_chase_veto({"verdict": "买入", "symbol": "002758"})
    assert out["verdict"] != "买入"
    assert out.get("veto_reason")


def test_nan_and_invalid_dd_20_veto_buy():
    import math
    import scanner as sc

    assert sc.left_side_chase_veto_reason({"dd_20": float("nan")})
    assert sc.left_side_chase_veto_reason({"dd_20": "abc"})
    out = sc.apply_left_side_chase_veto({"verdict": "买入", "dd_20": math.nan})
    assert out["verdict"] != "买入"


def test_attach_dd_20_from_raw_ohlcv():
    import scanner as sc

    df = pd.DataFrame({
        "close": [10.0] * 15 + [11.0, 11.2, 11.1, 11.0, 10.95],
        "high": [10.2] * 15 + [11.3, 11.4, 11.2, 11.15, 11.0],
    })
    stock: dict = {}
    sc._attach_left_position_metrics(stock, df)
    assert stock["dd_20"] < 0
    assert stock["dd_20"] > -5


def test_rsi_zero_is_not_dropped():
    import scanner as sc

    rsi, overbought = sc._rsi_from_indicator_df(pd.DataFrame({"rsi_14": [0.0]}))
    assert rsi == 0.0
    assert overbought is False
