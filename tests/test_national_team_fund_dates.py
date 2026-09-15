"""National-team fund-flow and official-share dates must be explicit."""

from __future__ import annotations

import os
import sys

import pandas as pd

_STOCK = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "scripts", "stock"))
if _STOCK not in sys.path:
    sys.path.insert(0, _STOCK)


def test_dataframe_as_of_date_uses_last_row():
    from china_market_data import dataframe_as_of_date

    df = pd.DataFrame({
        "日期": ["2026-09-07", "2026-09-08"],
        "主力净流入-净额": [1.0, -2.0],
    })
    assert dataframe_as_of_date(df) == "2026-09-08"


def test_dataframe_as_of_date_reads_sse_stat_date():
    from china_market_data import dataframe_as_of_date

    df = pd.DataFrame({
        "基金代码": ["510300", "510050"],
        "统计日期": ["2026-09-11", "2026-09-11"],
        "基金份额": [1.0, 2.0],
    })
    assert dataframe_as_of_date(df) == "2026-09-11"


def test_fund_signals_includes_latest_date(monkeypatch):
    import china_market_data as cmd

    df = pd.DataFrame({
        "日期": ["2026-09-07", "2026-09-08"],
        "主力净流入-净额": [3.82e10, -8_198_545_408.0],
    })
    monkeypatch.setattr(cmd, "fetch_market_fund_flow", lambda days=10, force_refresh=False: df)
    monkeypatch.setattr(cmd, "fetch_institution_holdings", lambda force_refresh=False: pd.DataFrame())

    out = cmd.national_team_fund_signals(force_refresh=True)
    assert out["market_flow"]["latest_date"] == "2026-09-08"
    assert out["market_flow"]["latest_net_yi"] == -81.99


def test_monitor_sets_sse_stat_date(monkeypatch, tmp_path):
    import china_market_data as cmd

    sse = pd.DataFrame({
        "基金代码": ["510300"],
        "基金份额": [2.33986877e10],
        "统计日期": ["2026-09-11"],
    })
    monkeypatch.setattr(cmd, "_CACHE_NATIONAL", str(tmp_path))
    monkeypatch.setattr(cmd, "fetch_etf_shares_sse", lambda date="", force_refresh=False: sse)
    monkeypatch.setattr(cmd, "fetch_etf_shares_szse", lambda force_refresh=False: pd.DataFrame())
    monkeypatch.setattr(cmd, "_save_national_team_knowledge", lambda _s: None)
    monkeypatch.setattr(cmd, "_append_history", lambda _s: None)
    monkeypatch.setattr(cmd, "_detect_share_anomalies", lambda _s: None)

    out = cmd.national_team_monitor(force_refresh=True)
    assert out["sse_stat_date"] == "2026-09-11"
