"""Quality-value scanner lifecycle tests (no live market fetch)."""
import json
import os
import sys
import time
import types
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts" / "stock"))

import quality_value_scanner as qv


def test_start_qv_scan_rejects_second(monkeypatch):
    monkeypatch.setattr(sys, "_qv_thread", type("T", (), {"is_alive": lambda self: True})(), raising=False)
    out = qv.start_qv_scan()
    assert out["ok"] is False
    assert "进行中" in (out.get("error") or "")


def test_get_qv_status_has_shape():
    st = qv.get_qv_status()
    assert "status" in st
    assert "progress" in st
    assert "step" in st


def test_stop_qv_scan_sets_event():
    sys._qv_stop_event.clear()
    out = qv.stop_qv_scan()
    assert out["ok"] is True
    assert sys._qv_stop_event.is_set()


def test_run_qv_scan_empty_snapshot_is_fetch_failure_not_funnel(tmp_path, monkeypatch):
    monkeypatch.setattr(qv, "QUALITY_VALUE_DIR", str(tmp_path))
    monkeypatch.setattr(qv, "PROGRESS_FILE", str(tmp_path / "qv_progress.json"))
    monkeypatch.setattr(qv, "_fetch_market_snapshot_rows", lambda: [])
    monkeypatch.setattr(qv, "_index_report_to_rag", lambda *a, **k: None)
    sys._qv_stop_event.clear()
    qv._run_qv_scan(use_deepseek=False)
    reports = list(tmp_path.glob("*-report.md"))
    assert reports, "expected a markdown report"
    text = reports[0].read_text(encoding="utf-8")
    assert "不构成投资建议" in text
    assert "快照" in text or "拉取" in text
    assert "当天没有同时满足优质+低估" not in text
    result = qv.get_qv_latest_result()
    assert result is not None
    assert result["stats"].get("snapshot_failed") is True
    assert result["stats"].get("snapshot_count") == 0
    st = qv.get_qv_status()
    assert st["status"] == "error"
    assert st.get("error")


def test_run_qv_scan_writes_empty_report(tmp_path, monkeypatch):
    monkeypatch.setattr(qv, "QUALITY_VALUE_DIR", str(tmp_path))
    monkeypatch.setattr(qv, "PROGRESS_FILE", str(tmp_path / "qv_progress.json"))
    monkeypatch.setattr(qv, "_fetch_market_snapshot_rows", lambda: [
        {"symbol": "000001", "name": "ST亏损", "industry": "机械", "pe": -1.0, "pb": 1.0, "div_yield": 3.0},
    ])
    monkeypatch.setattr(qv, "_index_report_to_rag", lambda *a, **k: None)
    sys._qv_stop_event.clear()
    qv._run_qv_scan(use_deepseek=False)
    reports = list(tmp_path.glob("*-report.md"))
    assert reports, "expected a markdown report"
    text = reports[0].read_text(encoding="utf-8")
    assert "不构成投资建议" in text
    assert "宁缺毋滥" in text
    assert "扫描失败: 行情快照为空" not in text
    result = qv.get_qv_latest_result()
    assert result is not None
    assert result["stats"].get("snapshot_failed") is not True
    st = qv.get_qv_status()
    assert st["status"] == "done"


def test_run_qv_scan_medium_horizon_writes_separate_file(tmp_path, monkeypatch):
    monkeypatch.setattr(qv, "QUALITY_VALUE_DIR", str(tmp_path))
    monkeypatch.setattr(qv, "PROGRESS_FILE", str(tmp_path / "qv_progress.json"))
    monkeypatch.setattr(qv, "_fetch_market_snapshot_rows", lambda: [
        {"symbol": "000001", "name": "ST亏损", "industry": "机械", "pe": -1.0, "pb": 1.0, "div_yield": 3.0},
    ])
    monkeypatch.setattr(qv, "_index_report_to_rag", lambda *a, **k: None)
    sys._qv_stop_event.clear()
    qv._run_qv_scan(use_deepseek=False, horizon="long")
    time.sleep(1.1)
    qv._run_qv_scan(use_deepseek=False, horizon="medium")
    names = {p.name for p in tmp_path.glob("*.json") if p.name != "qv_progress.json"}
    assert any(n.endswith(".json") and "m1-6" in n for n in names)
    assert any(n.endswith(".json") and "m1-6" not in n for n in names)
    medium = next(tmp_path.glob("*-m1-6.json"))
    payload = json.loads(medium.read_text(encoding="utf-8"))
    assert payload.get("horizon") == "medium"
    latest = qv.get_qv_latest_result()
    assert latest.get("horizon") == "medium"
    text = next(tmp_path.glob("*-m1-6-report.md")).read_text(encoding="utf-8")
    assert "1 个月" in text or "1个月" in text
    assert "6 个月" in text or "6个月" in text


def test_run_qv_scan_enriches_layer1_and_applies_layer2(tmp_path, monkeypatch):
    monkeypatch.setattr(qv, "QUALITY_VALUE_DIR", str(tmp_path))
    monkeypatch.setattr(qv, "PROGRESS_FILE", str(tmp_path / "qv_progress.json"))
    monkeypatch.setattr(qv, "_index_report_to_rag", lambda *a, **k: None)
    monkeypatch.setattr(qv, "_fetch_market_snapshot_rows", lambda: [
        {"symbol": "000001", "name": "优质甲", "industry": "机械", "pe": 8.0, "pb": 1.0, "div_yield": 3.0},
        {"symbol": "000002", "name": "劣质乙", "industry": "机械", "pe": 9.0, "pb": 1.1, "div_yield": 3.0},
        {"symbol": "000003", "name": "对照丙", "industry": "机械", "pe": 20.0, "pb": 3.0, "div_yield": 3.0},
    ])

    def fake_fund(symbol, **_kwargs):
        if symbol == "000001":
            return {
                "roe": 15.0, "np_cagr_3y": 8.0, "debt_ratio": 40.0,
                "nonrecurring_ratio": 0.9, "payout_stable": True,
            }
        return {
            "roe": 5.0, "np_cagr_3y": 1.0, "debt_ratio": 80.0,
            "nonrecurring_ratio": 0.5, "payout_stable": False,
        }

    monkeypatch.setattr(qv, "fetch_fundamentals_for_value", fake_fund)
    monkeypatch.setattr(qv, "attach_pe_percentile", lambda rows: rows)
    sys._qv_stop_event.clear()
    qv._run_qv_scan(use_deepseek=False)
    result = qv.get_qv_latest_result()
    assert result is not None
    symbols = {p["symbol"] for p in result.get("picks") or []}
    assert "000001" in symbols
    assert "000002" not in symbols
    assert result["stats"].get("layer2_out", 0) == 1


def test_run_qv_scan_deepseek_empty_does_not_substitute_top5(tmp_path, monkeypatch):
    monkeypatch.setattr(qv, "QUALITY_VALUE_DIR", str(tmp_path))
    monkeypatch.setattr(qv, "PROGRESS_FILE", str(tmp_path / "qv_progress.json"))
    monkeypatch.setattr(qv, "_index_report_to_rag", lambda *a, **k: None)
    monkeypatch.setattr(qv, "_fetch_market_snapshot_rows", lambda: [
        {"symbol": "000001", "name": "优质甲", "industry": "机械", "pe": 8.0, "pb": 1.0, "div_yield": 3.0},
        {"symbol": "000002", "name": "劣质乙", "industry": "机械", "pe": 9.0, "pb": 1.1, "div_yield": 3.0},
        {"symbol": "000003", "name": "对照丙", "industry": "机械", "pe": 20.0, "pb": 3.0, "div_yield": 3.0},
    ])

    def fake_fund(symbol, **_kwargs):
        if symbol == "000001":
            return {
                "roe": 15.0, "np_cagr_3y": 8.0, "debt_ratio": 40.0,
                "nonrecurring_ratio": 0.9, "payout_stable": True,
            }
        return {
            "roe": 5.0, "np_cagr_3y": 1.0, "debt_ratio": 80.0,
            "nonrecurring_ratio": 0.5, "payout_stable": False,
        }

    monkeypatch.setattr(qv, "fetch_fundamentals_for_value", fake_fund)
    monkeypatch.setattr(qv, "attach_pe_percentile", lambda rows: rows)
    monkeypatch.setattr(qv, "_call_value_llm", lambda *a, **k: "")
    sys._qv_stop_event.clear()
    qv._run_qv_scan(use_deepseek=True)
    result = qv.get_qv_latest_result()
    assert result is not None
    assert result.get("picks") == []
    text = list(tmp_path.glob("*-report.md"))[0].read_text(encoding="utf-8")
    assert "DeepSeek 终审: 是" not in text
    assert "失败" in text or "未经" in text
    assert "宁缺毋滥" in text


def test_attach_prediction_keeps_picks_when_not_buy(monkeypatch):
    picks = [{"symbol": "002602", "name": "世纪华通"}]

    def fake_gen(symbol, realtime_quote=None):
        return {
            "ok": True, "verdict": "不买入", "buy_low": 10.0, "buy_high": 10.5,
            "stop_loss": 9.2, "target_price": 12.0, "reason": "高风险",
        }

    monkeypatch.setattr("llm_reasoning.generate_prediction_trade_levels", fake_gen)
    out = qv.attach_prediction_trade_levels(picks)
    assert len(out) == 1
    assert out[0]["symbol"] == "002602"
    assert out[0]["prediction"]["verdict"] == "不买入"
    assert out[0]["prediction"]["buy_low"] == 10.0
    assert out[0]["prediction"]["target_price"] == 12.0


def test_attach_prediction_one_failure_does_not_drop_or_abort(monkeypatch):
    picks = [
        {"symbol": "000001", "name": "甲"},
        {"symbol": "000002", "name": "乙"},
    ]

    def fake_gen(symbol, realtime_quote=None):
        if symbol == "000001":
            raise RuntimeError("boom")
        return {"ok": True, "verdict": "买入", "buy_low": 1.0, "buy_high": 1.1, "stop_loss": 0.9, "target_price": 1.4}

    monkeypatch.setattr("llm_reasoning.generate_prediction_trade_levels", fake_gen)
    out = qv.attach_prediction_trade_levels(picks)
    assert [p["symbol"] for p in out] == ["000001", "000002"]
    assert out[0]["prediction"]["ok"] is False
    assert out[1]["prediction"]["ok"] is True


def test_attach_prediction_caps_at_five(monkeypatch):
    picks = [{"symbol": str(i).zfill(6), "name": str(i)} for i in range(7)]
    calls = []

    def fake_gen(symbol, realtime_quote=None):
        calls.append(symbol)
        return {"ok": True, "verdict": "买入", "buy_low": 1.0, "buy_high": 1.1, "stop_loss": 0.9, "target_price": 1.4}

    monkeypatch.setattr("llm_reasoning.generate_prediction_trade_levels", fake_gen)
    out = qv.attach_prediction_trade_levels(picks)
    assert len(out) == 7
    assert len(calls) == 5
    assert "prediction" not in out[5]
    assert "prediction" not in out[6]


def test_attach_prediction_honors_stop(monkeypatch):
    sys._qv_stop_event.clear()
    picks = [
        {"symbol": "000001", "name": "甲"},
        {"symbol": "000002", "name": "乙"},
        {"symbol": "000003", "name": "丙"},
    ]
    calls = []

    def fake_gen(symbol, realtime_quote=None):
        calls.append(symbol)
        if symbol == "000001":
            sys._qv_stop_event.set()
        return {"ok": True, "verdict": "买入", "buy_low": 1.0, "buy_high": 1.1, "stop_loss": 0.9, "target_price": 1.4}

    monkeypatch.setattr("llm_reasoning.generate_prediction_trade_levels", fake_gen)
    out = qv.attach_prediction_trade_levels(picks)
    assert [p["symbol"] for p in out] == ["000001", "000002", "000003"]
    assert calls == ["000001"]
    assert out[0]["prediction"]["ok"] is True
    assert out[1]["prediction"]["ok"] is False
    assert out[2]["prediction"]["ok"] is False


def test_report_prediction_failure_does_not_leak_exception():
    text = qv._generate_report(
        [{"symbol": "000001", "name": "甲", "prediction": {"ok": False, "error": "boom RuntimeError"}}],
        {},
        True,
        "long",
    )
    assert "预测未出" in text
    assert "RuntimeError" not in text
    assert "boom" not in text


def test_run_qv_scan_deepseek_attaches_trade_levels(tmp_path, monkeypatch):
    monkeypatch.setattr(qv, "QUALITY_VALUE_DIR", str(tmp_path))
    monkeypatch.setattr(qv, "PROGRESS_FILE", str(tmp_path / "qv_progress.json"))
    monkeypatch.setattr(qv, "_index_report_to_rag", lambda *a, **k: None)
    monkeypatch.setattr(qv, "_fetch_market_snapshot_rows", lambda: [
        {"symbol": "000001", "name": "优质甲", "industry": "机械", "pe": 8.0, "pb": 1.0, "div_yield": 3.0},
        {"symbol": "000003", "name": "对照丙", "industry": "机械", "pe": 20.0, "pb": 3.0, "div_yield": 3.0},
    ])
    monkeypatch.setattr(qv, "fetch_fundamentals_for_value", lambda symbol, **k: {
        "roe": 15.0, "np_cagr_3y": 8.0, "debt_ratio": 40.0,
        "nonrecurring_ratio": 0.9, "payout_stable": True,
    })
    monkeypatch.setattr(qv, "attach_pe_percentile", lambda rows: rows)
    monkeypatch.setattr(
        qv, "_call_value_llm",
        lambda *a, **k: '[{"symbol":"000001","verdict":"买入","score":80,"cycle":"平稳","trap":false,"reason":"a","risk":"r"}]',
    )
    attached = {"n": 0}

    def fake_attach(picks):
        attached["n"] = len(picks)
        for p in picks:
            p["prediction"] = {
                "ok": True, "verdict": "不买入", "buy_low": 7.5, "buy_high": 8.0,
                "stop_loss": 7.0, "target_price": 9.2, "reason": "短线高风险",
            }
        return picks

    monkeypatch.setattr(qv, "attach_prediction_trade_levels", fake_attach, raising=False)
    sys._qv_stop_event.clear()
    qv._run_qv_scan(use_deepseek=True)
    assert attached["n"] >= 1
    result = qv.get_qv_latest_result()
    pick = result["picks"][0]
    assert pick["prediction"]["verdict"] == "不买入"
    assert pick["prediction"]["buy_low"] == 7.5
    assert pick["prediction"]["target_price"] == 9.2
    text = list(tmp_path.glob("*-report.md"))[0].read_text(encoding="utf-8")
    assert "建议买入" in text or "买入区间" in text
    assert "止损" in text
    assert "抛" in text or "目标价" in text
    assert "1～2周" in text or "1-2周" in text or "1～2 周" in text
    st = qv.get_qv_status()
    assert st["status"] == "done"


def test_run_qv_scan_predict_stop_sets_stopped(tmp_path, monkeypatch):
    monkeypatch.setattr(qv, "QUALITY_VALUE_DIR", str(tmp_path))
    monkeypatch.setattr(qv, "PROGRESS_FILE", str(tmp_path / "qv_progress.json"))
    monkeypatch.setattr(qv, "_index_report_to_rag", lambda *a, **k: None)
    monkeypatch.setattr(qv, "_fetch_market_snapshot_rows", lambda: [
        {"symbol": "000001", "name": "优质甲", "industry": "机械", "pe": 8.0, "pb": 1.0, "div_yield": 3.0},
        {"symbol": "000003", "name": "对照丙", "industry": "机械", "pe": 20.0, "pb": 3.0, "div_yield": 3.0},
    ])
    monkeypatch.setattr(qv, "fetch_fundamentals_for_value", lambda symbol, **k: {
        "roe": 15.0, "np_cagr_3y": 8.0, "debt_ratio": 40.0,
        "nonrecurring_ratio": 0.9, "payout_stable": True,
    })
    monkeypatch.setattr(qv, "attach_pe_percentile", lambda rows: rows)
    monkeypatch.setattr(
        qv, "_call_value_llm",
        lambda *a, **k: '[{"symbol":"000001","verdict":"买入","score":80,"cycle":"平稳","trap":false,"reason":"a","risk":"r"}]',
    )

    def fake_attach(picks):
        sys._qv_stop_event.set()
        for p in picks:
            p["prediction"] = {"ok": False, "error": "stopped"}
        return picks

    monkeypatch.setattr(qv, "attach_prediction_trade_levels", fake_attach)
    sys._qv_stop_event.clear()
    qv._run_qv_scan(use_deepseek=True)
    st = qv.get_qv_status()
    assert st["status"] == "stopped"


def test_run_qv_scan_without_deepseek_skips_trade_levels(tmp_path, monkeypatch):
    monkeypatch.setattr(qv, "QUALITY_VALUE_DIR", str(tmp_path))
    monkeypatch.setattr(qv, "PROGRESS_FILE", str(tmp_path / "qv_progress.json"))
    monkeypatch.setattr(qv, "_index_report_to_rag", lambda *a, **k: None)
    monkeypatch.setattr(qv, "_fetch_market_snapshot_rows", lambda: [
        {"symbol": "000001", "name": "优质甲", "industry": "机械", "pe": 8.0, "pb": 1.0, "div_yield": 3.0},
        {"symbol": "000003", "name": "对照丙", "industry": "机械", "pe": 20.0, "pb": 3.0, "div_yield": 3.0},
    ])
    monkeypatch.setattr(qv, "fetch_fundamentals_for_value", lambda symbol, **k: {
        "roe": 15.0, "np_cagr_3y": 8.0, "debt_ratio": 40.0,
        "nonrecurring_ratio": 0.9, "payout_stable": True,
    })
    monkeypatch.setattr(qv, "attach_pe_percentile", lambda rows: rows)
    called = {"n": 0}
    monkeypatch.setattr(
        qv,
        "attach_prediction_trade_levels",
        lambda picks: called.__setitem__("n", called["n"] + 1) or picks,
        raising=False,
    )
    sys._qv_stop_event.clear()
    qv._run_qv_scan(use_deepseek=False)
    assert called["n"] == 0


def _fake_eastmoney_resp(payload):
    class Resp:
        def raise_for_status(self):
            pass

        def json(self):
            return payload

    return Resp()


def test_empty_eastmoney_data_falls_through_to_akshare(monkeypatch):
    monkeypatch.setitem(
        sys.modules,
        "requests",
        types.SimpleNamespace(get=lambda *a, **k: _fake_eastmoney_resp({"data": None})),
    )
    df = pd.DataFrame([{
        "代码": "000001",
        "名称": "平安银行",
        "市盈率-动态": 5.0,
        "市净率": 0.8,
        "股息率": 4.0,
    }])
    monkeypatch.setitem(
        sys.modules,
        "akshare",
        types.SimpleNamespace(stock_zh_a_spot_em=lambda: df),
    )
    rows = qv._fetch_market_snapshot_rows()
    assert len(rows) >= 1
    assert rows[0]["symbol"] == "000001"


def test_empty_eastmoney_diff_falls_through_to_akshare(monkeypatch):
    monkeypatch.setitem(
        sys.modules,
        "requests",
        types.SimpleNamespace(get=lambda *a, **k: _fake_eastmoney_resp({"data": {"diff": []}})),
    )
    df = pd.DataFrame([{
        "代码": "600000",
        "名称": "浦发银行",
        "市盈率-动态": 6.0,
        "市净率": 0.7,
        "股息率": 5.0,
    }])
    monkeypatch.setitem(
        sys.modules,
        "akshare",
        types.SimpleNamespace(stock_zh_a_spot_em=lambda: df),
    )
    rows = qv._fetch_market_snapshot_rows()
    assert any(r["symbol"] == "600000" for r in rows)


def _raise(msg):
    raise ValueError(msg)


def test_em_and_akshare_empty_falls_through_to_sina(monkeypatch):
    monkeypatch.setattr(qv, "_fetch_eastmoney_clist", lambda: _raise("em empty"))
    monkeypatch.setattr(qv, "_fetch_akshare_spot", lambda: _raise("ak empty"))
    monkeypatch.setattr(
        qv,
        "_fetch_sina_spot",
        lambda: [{"symbol": "000001", "name": "平安银行", "pe": 5.0, "pb": 0.8}],
        raising=False,
    )
    monkeypatch.setattr(qv, "_fetch_cached_spot", lambda: _raise("cache must not run"), raising=False)
    rows = qv._fetch_market_snapshot_rows()
    assert rows[0]["symbol"] == "000001"
    assert qv._SNAPSHOT_SOURCE == "sina"


def test_live_sources_empty_falls_through_to_cache(monkeypatch):
    monkeypatch.setattr(qv, "_fetch_eastmoney_clist", lambda: _raise("em empty"))
    monkeypatch.setattr(qv, "_fetch_akshare_spot", lambda: _raise("ak empty"))
    monkeypatch.setattr(qv, "_fetch_sina_spot", lambda: _raise("sina empty"), raising=False)
    monkeypatch.setattr(
        qv,
        "_fetch_cached_spot",
        lambda: [{"symbol": "600000", "name": "浦发银行", "pe": 6.0, "pb": 0.7}],
        raising=False,
    )
    rows = qv._fetch_market_snapshot_rows()
    assert any(r["symbol"] == "600000" for r in rows)
    assert qv._SNAPSHOT_SOURCE == "cache"


def test_all_snapshot_sources_empty_returns_empty(monkeypatch):
    monkeypatch.setattr(qv, "_fetch_eastmoney_clist", lambda: _raise("em empty"))
    monkeypatch.setattr(qv, "_fetch_akshare_spot", lambda: _raise("ak empty"))
    monkeypatch.setattr(qv, "_fetch_sina_spot", lambda: _raise("sina empty"), raising=False)
    monkeypatch.setattr(qv, "_fetch_cached_spot", lambda: _raise("cache empty"), raising=False)
    rows = qv._fetch_market_snapshot_rows()
    assert rows == []
    assert qv._SNAPSHOT_SOURCE == ""


def _write_spot_csv(path: Path, symbol: str = "000001"):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        f"代码,名称,市盈率-动态,市净率\n{symbol},测试股,5.0,0.8\n",
        encoding="utf-8-sig",
    )


def test_cache_spot_uses_file_from_today(tmp_path, monkeypatch):
    monkeypatch.setattr(qv, "QUALITY_VALUE_DIR", str(tmp_path / "quality_value"))
    csv_path = tmp_path / ".cache" / ".valuation" / "market_spot.csv"
    _write_spot_csv(csv_path)
    rows = qv._fetch_cached_spot()
    assert rows[0]["symbol"] == "000001"


def test_cache_spot_rejects_stale_file(tmp_path, monkeypatch):
    monkeypatch.setattr(qv, "QUALITY_VALUE_DIR", str(tmp_path / "quality_value"))
    csv_path = tmp_path / ".cache" / ".valuation" / "market_spot.csv"
    _write_spot_csv(csv_path, "600000")
    stale = time.time() - 3 * 24 * 3600
    os.utime(csv_path, (stale, stale))
    with pytest.raises(ValueError, match="当天"):
        qv._fetch_cached_spot()


def test_run_qv_scan_calls_ensure_stock_config(tmp_path, monkeypatch):
    called = []
    monkeypatch.setattr(qv, "_ensure_stock_config", lambda: called.append(True), raising=False)
    monkeypatch.setattr(qv, "QUALITY_VALUE_DIR", str(tmp_path))
    monkeypatch.setattr(qv, "PROGRESS_FILE", str(tmp_path / "qv_progress.json"))
    monkeypatch.setattr(qv, "_fetch_market_snapshot_rows", lambda: [])
    monkeypatch.setattr(qv, "_index_report_to_rag", lambda *a, **k: None)
    sys._qv_stop_event.clear()
    qv._run_qv_scan(use_deepseek=False)
    assert called, "scan thread must restore stock config before fetching"
