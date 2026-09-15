import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts" / "stock"))

from ath_rebreak_scanner import (
    cap_live_preserving_layer1_order,
    filter_live_rebreaks,
    layer1_active_near_high,
)


def _row(**kw):
    base = {
        "代码": "600000",
        "名称": "浦发银行",
        "最新价": 10.0,
        "涨跌幅": 2.0,
        "换手率": 2.0,
        "成交额": 50_000_000,
    }
    base.update(kw)
    return base


def test_layer1_drops_st():
    df = pd.DataFrame([
        _row(代码="600001", 名称="ST示例", 涨跌幅=8.0),
        _row(代码="600002", 名称="正常股", 涨跌幅=8.0),
    ])
    kept = layer1_active_near_high(df)
    symbols = {r["symbol"] for r in kept}
    assert "600001" not in symbols
    assert "600002" in symbols


def test_layer1_keeps_plus_eight_pct():
    df = pd.DataFrame([_row(代码="600003", 名称="强势股", 涨跌幅=8.0)])
    kept = layer1_active_near_high(df)
    assert len(kept) == 1
    assert kept[0]["symbol"] == "600003"


def test_layer1_caps_at_100():
    rows = [
        _row(代码=f"{600000 + i:06d}", 名称=f"股{i}", 涨跌幅=1.0 + i * 0.01, 成交额=40_000_000 + i)
        for i in range(120)
    ]
    kept = layer1_active_near_high(pd.DataFrame(rows))
    assert len(kept) == 100


def test_filter_live_rebreaks():
    rows = [
        {"symbol": "1", "signal_live": True, "tradeable": True},
        {"symbol": "2", "signal_live": False, "tradeable": False},
        {"symbol": "3", "signal_live": True, "tradeable": False},
    ]
    live = filter_live_rebreaks(rows)
    assert {r["symbol"] for r in live} == {"1", "3"}


def test_layer1_drops_below_30m_amount():
    df = pd.DataFrame([
        _row(代码="600010", 名称="低额", 成交额=29_900_000),
        _row(代码="600011", 名称="够额", 成交额=30_000_000),
    ])
    kept = {r["symbol"] for r in layer1_active_near_high(df)}
    assert "600010" not in kept
    assert "600011" in kept


def test_layer1_keeps_star_68():
    df = pd.DataFrame([_row(代码="688001", 名称="科创示例", 涨跌幅=3.0)])
    kept = layer1_active_near_high(df)
    assert len(kept) == 1
    assert kept[0]["symbol"] == "688001"


def test_layer2_cap_follows_layer1_order_not_completion_order():
    candidates = [{"symbol": f"{600000 + i:06d}"} for i in range(4)]
    shuffled = [
        {"symbol": "600003", "signal_live": True},
        {"symbol": "600000", "signal_live": True},
        {"symbol": "600002", "signal_live": True},
        {"symbol": "600001", "signal_live": True},
    ]
    capped = cap_live_preserving_layer1_order(candidates, shuffled, cap=2)
    assert [r["symbol"] for r in capped] == ["600000", "600001"]


def test_enrich_checks_cache_before_eastmoney_slot():
    src = Path(__file__).resolve().parents[1] / "scripts" / "stock" / "ath_rebreak_scanner.py"
    body = src.read_text(encoding="utf-8")
    start = body.find("def _enrich_one")
    end = body.find("def _run_thread")
    fn = body[start:end]
    assert fn.find("ohlcv_done") < fn.find("eastmoney_slot")
