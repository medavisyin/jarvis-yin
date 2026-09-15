"""National-team intraday broad ETF shares: exchange prev → EM f38."""

from __future__ import annotations

import json
import os
import sys

_STOCK = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "scripts", "stock"))
if _STOCK not in sys.path:
    sys.path.insert(0, _STOCK)


def test_parse_etf_spot_share_diff_maps_core_codes():
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


def test_compute_spot_vs_prev_pct():
    from china_market_data import compute_spot_vs_prev_pct

    assert compute_spot_vs_prev_pct(110.0, 100.0) == 10.0
    assert compute_spot_vs_prev_pct(95.0, 100.0) == -5.0
    assert compute_spot_vs_prev_pct(None, 100.0) is None
    assert compute_spot_vs_prev_pct(110.0, None) is None
    assert compute_spot_vs_prev_pct(110.0, 0) is None


def test_national_team_intraday_shares_broad_only_anomaly(monkeypatch, tmp_path):
    import china_market_data as cmd

    monkeypatch.setattr(cmd, "_CACHE_NATIONAL", str(tmp_path))
    monkeypatch.setattr(cmd, "_today_str", lambda: "20260804")
    hist = [
        {
            "date": "20260803",
            "etf_snapshot": [
                {"code": "510050", "name": "50ETF", "shares_yi": 72.1, "type": "宽基"},
                {"code": "510300", "name": "300ETF", "shares_yi": 270.0, "type": "宽基"},
                {"code": "512010", "name": "医药ETF", "shares_yi": 10.0, "type": "行业"},
            ],
        }
    ]
    (tmp_path / "history.json").write_text(json.dumps(hist), encoding="utf-8")

    monkeypatch.setattr(
        cmd,
        "fetch_etf_spot_shares_em",
        lambda codes=None, force_refresh=False: {
            "510050": {
                "shares": 7677666816.0,
                "shares_yi": 76.78,
                "data_date": "20260804",
                "source": "eastmoney_spot",
            },
            "510300": {
                "shares": 27058087680.0,
                "shares_yi": 270.58,
                "data_date": "20260804",
                "source": "eastmoney_spot",
            },
            "512010": {
                "shares": 1.1e9,
                "shares_yi": 11.0,
                "data_date": "20260804",
                "source": "eastmoney_spot",
            },
        },
    )

    out = cmd.national_team_intraday_shares(force_refresh=True)
    codes = {i["code"] for i in out["items"]}
    assert "510050" in codes
    assert "510300" in codes
    assert "512010" not in codes  # sector excluded

    a050 = next(i for i in out["items"] if i["code"] == "510050")
    assert a050["status"] == "ok"
    assert a050["prev_yi"] == 72.1
    assert a050["curr_yi"] == 76.78
    assert a050["change_pct"] == 6.49
    assert a050["prev_source"] == "exchange"
    assert a050["curr_source"] == "eastmoney_f38"
    assert a050["em_date"] == "20260804"

    assert any(a["code"] == "510050" for a in out["anomalies"])
    assert not any(a["code"] == "510300" for a in out["anomalies"])  # ~0.2% < 3%
    assert out.get("disclaimer")


def test_national_team_intraday_shares_stale_em_date_is_no_data(monkeypatch, tmp_path):
    import china_market_data as cmd

    monkeypatch.setattr(cmd, "_CACHE_NATIONAL", str(tmp_path))
    monkeypatch.setattr(cmd, "_today_str", lambda: "20260804")
    hist = [{"date": "20260803", "etf_snapshot": [{"code": "510050", "shares_yi": 72.1, "type": "宽基"}]}]
    (tmp_path / "history.json").write_text(json.dumps(hist), encoding="utf-8")
    monkeypatch.setattr(
        cmd,
        "fetch_etf_spot_shares_em",
        lambda codes=None, force_refresh=False: {
            "510050": {
                "shares_yi": 76.78,
                "data_date": "20260803",  # not today
                "source": "eastmoney_spot",
            }
        },
    )

    out = cmd.national_team_intraday_shares(force_refresh=True)
    a050 = next(i for i in out["items"] if i["code"] == "510050")
    assert a050["status"] == "无数据"
    assert a050["curr_yi"] is None
    assert a050["change_pct"] is None
    assert out["anomalies"] == []


def test_national_team_intraday_shares_fetch_fail(monkeypatch, tmp_path):
    import china_market_data as cmd

    monkeypatch.setattr(cmd, "_CACHE_NATIONAL", str(tmp_path))
    monkeypatch.setattr(cmd, "_today_str", lambda: "20260804")
    (tmp_path / "history.json").write_text("[]", encoding="utf-8")
    monkeypatch.setattr(
        cmd,
        "fetch_etf_spot_shares_em",
        lambda codes=None, force_refresh=False: (_ for _ in ()).throw(ConnectionError("spot down")),
    )

    out = cmd.national_team_intraday_shares(force_refresh=True)
    assert out.get("error")
    assert out["items"] == []
    assert out["anomalies"] == []
