import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts" / "stock"))

from ath_rebreak import BENCHMARK_LABEL, detect_five_year_rebreak, is_limit_up


def _ohlcv(closes, highs=None, lows=None):
    n = len(closes)
    highs = highs or [c + 0.1 for c in closes]
    lows = lows or [c - 0.1 for c in closes]
    dates = pd.bdate_range("2024-01-02", periods=n, freq="B")
    return pd.DataFrame({
        "日期": dates.strftime("%Y-%m-%d"),
        "开盘": closes,
        "最高": highs,
        "最低": lows,
        "收盘": closes,
        "成交量": [1_000_000] * n,
        "涨跌幅": [0.0] * n,
    })


def test_label_is_five_year_not_ath():
    assert "历史最高" not in BENCHMARK_LABEL
    assert "近5年高" in BENCHMARK_LABEL


def test_insufficient_history():
    df = _ohlcv([10.0] * 20)
    out = detect_five_year_rebreak(df, "600000")
    assert out["ok"] is False
    assert out["stage"] == "insufficient_history"


def test_first_break_is_not_a_buy():
    closes = [10.0] * 60 + [11.0]
    highs = [10.1] * 60 + [11.2]
    lows = [9.9] * 60 + [10.8]
    out = detect_five_year_rebreak(_ohlcv(closes, highs, lows), "600000")
    assert out["stage"] == "first_break"
    assert out["signal_live"] is False
    assert out["tradeable"] is False
    assert out["benchmark"] == 10.1


def test_rebreak_requires_three_day_pause():
    closes = [10.0] * 60 + [11.0, 11.2]
    highs = [10.1] * 60 + [11.2, 11.3]
    lows = [9.9] * 60 + [10.0, 10.0]
    out = detect_five_year_rebreak(_ohlcv(closes, highs, lows), "600000")
    assert out["stage"] in ("first_break", "pullback")
    assert out["signal_live"] is False


def test_below_high_then_rebreak_live():
    body = [10.0] * 60
    closes = body + [11.0, 9.8, 9.7, 9.6, 11.5]
    highs = [10.1] * 60 + [11.2, 10.0, 9.9, 9.8, 11.6]
    lows = [9.9] * 60 + [10.8, 9.5, 9.4, 9.3, 10.5]
    chg = [0.0] * 64 + [2.0]
    df = _ohlcv(closes, highs, lows)
    df["涨跌幅"] = chg
    out = detect_five_year_rebreak(df, "600000")
    assert out["ok"] is True
    assert out["stage"] == "rebreak"
    assert "below_high" in out["pullback_tags"]
    assert out["signal_live"] is True
    assert out["tradeable"] is True


def test_limit_up_rebreak_not_tradeable():
    body = [10.0] * 60
    closes = body + [11.0, 9.8, 9.7, 9.6, 11.5]
    highs = [10.1] * 60 + [11.2, 10.0, 9.9, 9.8, 11.6]
    lows = [9.9] * 60 + [10.8, 9.5, 9.4, 9.3, 10.5]
    df = _ohlcv(closes, highs, lows)
    df["涨跌幅"] = [0.0] * 64 + [10.0]
    out = detect_five_year_rebreak(df, "600000")
    assert out["signal_live"] is True
    assert out["limit_up_on_rebreak"] is True
    assert out["tradeable"] is False


def test_is_limit_up_gem():
    assert is_limit_up("300001", 19.5) is True
    assert is_limit_up("300001", 10.0) is False
    assert is_limit_up("600000", 9.5) is True
    assert is_limit_up("600000", 9.4) is False


def test_is_limit_up_star_68():
    assert is_limit_up("688001", 19.5) is True
    assert is_limit_up("688001", 10.0) is False
    assert is_limit_up("688001", 19.4) is False


def test_rebreak_bar_that_is_also_new_five_year_high_still_counts():
    body = [10.0] * 60
    closes = body + [11.0, 9.8, 9.7, 9.6, 12.0]
    highs = [10.1] * 60 + [11.2, 10.0, 9.9, 9.8, 12.1]
    lows = [9.9] * 60 + [10.8, 9.5, 9.4, 9.3, 11.0]
    out = detect_five_year_rebreak(_ohlcv(closes, highs, lows), "600000")
    assert out["stage"] == "rebreak"
    assert out["signal_live"] is True


def test_stale_rebreak_not_live():
    body = [10.0] * 60
    closes = body + [11.0, 9.8, 9.7, 9.6, 11.5, 11.4, 11.3, 11.2]
    highs = [10.1] * 60 + [11.2, 10.0, 9.9, 9.8, 11.6, 11.5, 11.4, 11.3]
    lows = [9.9] * 60 + [10.8, 9.5, 9.4, 9.3, 10.5, 11.0, 11.0, 11.0]
    out = detect_five_year_rebreak(_ohlcv(closes, highs, lows), "600000")
    assert out["stage"] == "rebreak"
    assert out["signal_live"] is False


def test_newer_first_break_after_stale_rebreak():
    body = [10.0] * 60
    closes = body + [11.0, 9.8, 9.7, 9.6, 11.5, 11.4, 11.3, 11.2, 11.1, 13.0]
    highs = [10.1] * 60 + [11.2, 10.0, 9.9, 9.8, 11.6, 11.5, 11.4, 11.3, 11.2, 13.1]
    lows = [9.9] * 60 + [10.8, 9.5, 9.4, 9.3, 10.5, 11.0, 11.0, 11.0, 11.0, 12.5]
    out = detect_five_year_rebreak(_ohlcv(closes, highs, lows), "600000")
    assert out["stage"] == "first_break"
    assert out["signal_live"] is False
    assert out["tradeable"] is False


def test_detector_sorts_reverse_chronological_bars():
    body = [10.0] * 60
    closes = body + [11.0, 9.8, 9.7, 9.6, 11.5]
    highs = [10.1] * 60 + [11.2, 10.0, 9.9, 9.8, 11.6]
    lows = [9.9] * 60 + [10.8, 9.5, 9.4, 9.3, 10.5]
    df = _ohlcv(closes, highs, lows)
    df["涨跌幅"] = [0.0] * 64 + [2.0]
    reversed_df = df.iloc[::-1].reset_index(drop=True)
    out = detect_five_year_rebreak(reversed_df, "600000")
    assert out["stage"] == "rebreak"
    assert out["signal_live"] is True


def test_flag_above_b_pct_3_8():
    body = [10.0] * 60
    closes = body + [11.0, 10.7, 10.5, 10.45, 12.0]
    highs = [10.1] * 60 + [11.2, 10.8, 10.6, 10.5, 12.1]
    lows = [9.9] * 60 + [10.8, 10.5, 10.45, 10.4, 11.0]
    out = detect_five_year_rebreak(_ohlcv(closes, highs, lows), "600000")
    assert "pct_3_8" in out["pullback_tags"]
    assert "below_high" not in out["pullback_tags"]
    assert out["stage"] == "rebreak"
    assert out["signal_live"] is True


def test_analyze_includes_five_year_rebreak(monkeypatch, tmp_path):
    import technical_analysis as ta

    n = 61
    df = pd.DataFrame({
        "date": pd.bdate_range("2024-01-02", periods=n, freq="B"),
        "open": [10.0] * n,
        "high": [10.1] * 60 + [11.2],
        "low": [9.9] * 60 + [10.8],
        "close": [10.0] * 60 + [11.0],
        "volume": [1_000_000] * n,
        "pct_change": [0.0] * n,
    })
    monkeypatch.setattr(ta, "load_ohlcv", lambda symbol: df)
    monkeypatch.setattr(ta, "STOCK_DATA_DIR", str(tmp_path))
    (tmp_path / "600000").mkdir()
    result = ta.analyze("600000")
    assert "five_year_rebreak" in result
    assert result["five_year_rebreak"]["benchmark_label"] == BENCHMARK_LABEL
