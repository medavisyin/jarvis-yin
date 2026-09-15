"""National-team ETF spot shares and official SSE announcement date."""

from __future__ import annotations

import os
import sys

import pandas as pd

_STOCK = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "scripts", "stock"))
if _STOCK not in sys.path:
    sys.path.insert(0, _STOCK)


def test_parse_etf_spot_diff_maps_core_codes():
    from china_market_data import parse_etf_spot_share_diff

    diff = [
        {"f12": "510300", "f14": "沪深300ETF", "f38": 25947487744.0, "f297": 20260730, "f124": 1785399100},
        {"f12": "999999", "f14": "IGNORE", "f38": 1.0, "f297": 20260730, "f124": 1},
    ]
    out = parse_etf_spot_share_diff(diff, codes={"510300", "510500"})
    assert "510300" in out
    assert "999999" not in out
    assert out["510300"]["shares_yi"] == 259.47
    assert out["510300"]["data_date"] == "20260730"
    assert out["510300"]["source"] == "eastmoney_spot"


def test_national_team_monitor_attaches_spot_shares(monkeypatch, tmp_path):
    """Approved design: spot discovery is national_team_intraday_shares, not monitor."""
    import china_market_data as cmd
    import json

    monkeypatch.setattr(cmd, "_CACHE_NATIONAL", str(tmp_path))
    monkeypatch.setattr(cmd, "_today_str", lambda: "20260730")
    hist = [{"date": "20260729", "etf_snapshot": [{"code": "510300", "shares_yi": 259.47, "type": "宽基"}]}]
    (tmp_path / "history.json").write_text(json.dumps(hist), encoding="utf-8")
    monkeypatch.setattr(
        cmd,
        "fetch_etf_spot_shares_em",
        lambda codes=None, force_refresh=False: {
            "510300": {
                "shares": 25947487744.0,
                "shares_yi": 259.47,
                "data_date": "20260730",
                "updated_at": "2026-07-30 17:00:00",
                "source": "eastmoney_spot",
            }
        },
    )

    out = cmd.national_team_intraday_shares(force_refresh=True)
    entry = next(e for e in out["items"] if e["code"] == "510300")
    assert entry["curr_yi"] == 259.47
    assert entry["em_date"] == "20260730"
    assert entry["status"] == "ok"
    assert out.get("error") is None


def test_compute_spot_vs_prev_pct():
    from china_market_data import compute_spot_vs_prev_pct

    assert compute_spot_vs_prev_pct(110.0, 100.0) == 10.0
    assert compute_spot_vs_prev_pct(95.0, 100.0) == -5.0
    assert compute_spot_vs_prev_pct(None, 100.0) is None
    assert compute_spot_vs_prev_pct(110.0, None) is None
    assert compute_spot_vs_prev_pct(110.0, 0) is None


def test_attach_spot_vs_prev_uses_history_yesterday(monkeypatch, tmp_path):
    """Prev official vs spot pct is computed inside national_team_intraday_shares."""
    import china_market_data as cmd
    import json

    monkeypatch.setattr(cmd, "_CACHE_NATIONAL", str(tmp_path))
    monkeypatch.setattr(cmd, "_today_str", lambda: "20260730")
    hist = [
        {
            "date": "20260729",
            "etf_snapshot": [{"code": "510300", "shares_yi": 250.0, "type": "宽基"}],
        }
    ]
    (tmp_path / "history.json").write_text(json.dumps(hist), encoding="utf-8")
    monkeypatch.setattr(
        cmd,
        "fetch_etf_spot_shares_em",
        lambda codes=None, force_refresh=False: {
            "510300": {"shares_yi": 259.47, "data_date": "20260730", "source": "eastmoney_spot"},
            "510500": {"shares_yi": 100.0, "data_date": "20260730", "source": "eastmoney_spot"},
            "510050": {"shares_yi": None, "data_date": "20260730", "source": "eastmoney_spot"},
        },
    )

    out = cmd.national_team_intraday_shares(force_refresh=True)
    e300 = next(i for i in out["items"] if i["code"] == "510300")
    assert e300["prev_yi"] == 250.0
    assert e300["change_pct"] == 3.79
    e500 = next(i for i in out["items"] if i["code"] == "510500")
    assert e500["status"] == "无数据"  # no prev in history
    e050 = next(i for i in out["items"] if i["code"] == "510050")
    assert e050["status"] == "无数据"


def test_national_team_monitor_spot_unavailable_on_fetch_fail(monkeypatch, tmp_path):
    import china_market_data as cmd

    monkeypatch.setattr(cmd, "_CACHE_NATIONAL", str(tmp_path))
    monkeypatch.setattr(cmd, "_today_str", lambda: "20260730")
    (tmp_path / "history.json").write_text("[]", encoding="utf-8")
    monkeypatch.setattr(
        cmd,
        "fetch_etf_spot_shares_em",
        lambda codes=None, force_refresh=False: (_ for _ in ()).throw(ConnectionError("spot down")),
    )

    out = cmd.national_team_intraday_shares(force_refresh=True)
    assert out.get("error")
    assert out["items"] == []


def test_national_team_monitor_sets_share_data_date(monkeypatch, tmp_path):
    import china_market_data as cmd

    monkeypatch.setattr(cmd, "_CACHE_NATIONAL", str(tmp_path))
    monkeypatch.setattr(cmd, "_today_str", lambda: "20260730")
    monkeypatch.setattr(cmd, "_detect_share_anomalies", lambda result: None)
    monkeypatch.setattr(cmd, "_append_history", lambda snapshot: None)
    monkeypatch.setattr(cmd, "_save_national_team_knowledge", lambda snapshot: None)

    sse = pd.DataFrame(
        {
            "基金代码": ["510300", "510500", "510050", "510880", "512100", "588000"],
            "统计日期": ["2026-07-29"] * 6,
            "基金份额": [1e10] * 6,
        }
    )
    szse = pd.DataFrame(
        {
            "基金代码": ["159919", "159915", "159922"],
            "流通份额": [1e9] * 3,
        }
    )
    monkeypatch.setattr(cmd, "fetch_etf_shares_sse", lambda **kw: sse)
    monkeypatch.setattr(cmd, "fetch_etf_shares_szse", lambda **kw: szse)

    result = cmd.national_team_monitor(force_refresh=True)
    assert result["sse_stat_date"] == "2026-07-29"
    assert "fetched_at" in result
    assert result["date"] == "20260730"
