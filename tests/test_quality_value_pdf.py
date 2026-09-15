"""Quality-value PDF type contract."""
import os
import sys
from pathlib import Path

from reportlab.platypus import Paragraph

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts" / "stock"))

from stock_pdf import ALLOWED_TYPES, REPORT_TITLES, generate_stock_pdf


def _plain(elements) -> str:
    parts = []
    for e in elements:
        if isinstance(e, Paragraph):
            if hasattr(e, "getPlainText"):
                parts.append(e.getPlainText())
            else:
                parts.append(getattr(e, "text", "") or "")
    return "\n".join(parts)


def test_quality_value_is_allowed_pdf_type():
    assert "quality_value" in ALLOWED_TYPES
    assert "优质低估" in REPORT_TITLES["quality_value"]


def test_build_quality_value_disclaimer_and_pick_fields():
    from stock_pdf import _build_quality_value

    elements = []
    _build_quality_value(
        {
            "date": "2026-08-16",
            "picks": [{
                "symbol": "600000",
                "name": "浦发银行",
                "industry": "银行",
                "pe": 5.2,
                "pb": 0.45,
                "div_yield": 5.1,
                "roe": 11,
                "pb_roe": 24.4,
                "pe_percentile_5y": 18.0,
            }],
        },
        elements,
    )
    blob = _plain(elements)
    assert "不构成投资建议" in blob
    assert "浦发银行" in blob
    assert "600000" in blob
    assert "银行" in blob
    assert "6 个月" in blob or "6个月" in blob


def test_build_quality_value_shows_prediction_trade_levels():
    from stock_pdf import _build_quality_value

    elements = []
    _build_quality_value(
        {
            "date": "2026-08-16",
            "picks": [{
                "symbol": "002602",
                "name": "世纪华通",
                "industry": "游戏",
                "pe": 18.7,
                "pb": 3.3,
                "div_yield": None,
                "roe": 20.27,
                "pb_roe": 6.1,
                "prediction": {
                    "ok": True,
                    "verdict": "不买入",
                    "buy_low": 10.0,
                    "buy_high": 10.5,
                    "stop_loss": 9.2,
                    "target_price": 12.0,
                    "reason": "短线高风险",
                },
            }],
        },
        elements,
    )
    blob = _plain(elements)
    assert "10.0" in blob or "10" in blob
    assert "12.0" in blob or "12" in blob
    assert "止损" in blob
    assert "不买入" in blob
    assert "1～2周" in blob or "1-2周" in blob or "1～2 周" in blob


def test_build_quality_value_medium_horizon_disclaimer():
    from stock_pdf import _build_quality_value

    elements = []
    _build_quality_value(
        {
            "date": "2026-08-16",
            "horizon": "medium",
            "picks": [{
                "symbol": "600000",
                "name": "浦发银行",
                "industry": "银行",
                "pe": 5.2,
                "pb": 0.45,
                "div_yield": 5.1,
                "roe": 11,
                "pb_roe": 24.4,
            }],
        },
        elements,
    )
    blob = _plain(elements)
    assert "1 个月" in blob or "1个月" in blob
    assert "6 个月" in blob or "6个月" in blob
    assert "2 年" not in blob and "2年" not in blob


def test_build_quality_value_empty_picks_is_ok():
    from stock_pdf import _build_quality_value

    elements = []
    _build_quality_value({"date": "2026-08-16", "picks": []}, elements)
    blob = _plain(elements)
    assert "宁缺毋滥" in blob or "暂无" in blob


def test_build_quality_value_snapshot_failed_is_not_funnel():
    from stock_pdf import _build_quality_value

    elements = []
    _build_quality_value(
        {
            "date": "2026-08-16",
            "picks": [],
            "stats": {"snapshot_failed": True, "snapshot_count": 0},
        },
        elements,
    )
    blob = _plain(elements)
    assert "快照" in blob or "拉取" in blob
    assert "漏斗过严" not in blob


def test_generate_quality_value_pdf(tmp_path):
    path = generate_stock_pdf(
        "quality_value",
        {"date": "2026-08-16", "picks": []},
        output_dir=str(tmp_path),
    )
    assert os.path.isfile(path)
    assert os.path.getsize(path) > 400
    assert "quality_value" in os.path.basename(path)
