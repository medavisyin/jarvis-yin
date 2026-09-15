import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts" / "stock"))

from llm_reasoning import format_five_year_rebreak_section


def test_section_says_not_a_buy_on_first_break():
    text = format_five_year_rebreak_section({
        "ok": True,
        "benchmark_label": "近5年高（前复权）",
        "benchmark": 10.1,
        "stage": "first_break",
        "pullback_tags": [],
        "signal_live": False,
        "tradeable": False,
        "reason": "标杆已立",
    })
    assert "近5年高" in text
    assert "历史最高" not in text
    assert "还不是买点" in text


def test_live_rebreak_is_candidate():
    text = format_five_year_rebreak_section({
        "ok": True,
        "benchmark_label": "近5年高（前复权）",
        "benchmark": 10.1,
        "stage": "rebreak",
        "pullback_tags": ["below_high"],
        "signal_live": True,
        "tradeable": True,
        "rebreak_date": "2026-08-28",
        "reason": "",
    })
    assert "买点候选" in text


def test_section_limit_up_not_tradeable():
    text = format_five_year_rebreak_section({
        "ok": True,
        "benchmark_label": "近5年高（前复权）",
        "benchmark": 10.1,
        "stage": "rebreak",
        "pullback_tags": ["below_high"],
        "signal_live": True,
        "tradeable": False,
        "rebreak_date": "2026-08-28",
        "reason": "",
    })
    assert "涨停" in text or "买不到" in text


def test_section_stale_rebreak_not_current_buy():
    text = format_five_year_rebreak_section({
        "ok": True,
        "benchmark_label": "近5年高（前复权）",
        "benchmark": 10.1,
        "stage": "rebreak",
        "pullback_tags": ["below_high"],
        "signal_live": False,
        "tradeable": False,
        "rebreak_date": "2026-08-20",
        "reason": "历史二次突破，不是当前买点",
    })
    assert "不是当前买点" in text
