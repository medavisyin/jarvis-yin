"""Shared DeepSeek persona: analysis + Layer3 scanners use the same decision ruler."""

from __future__ import annotations

import os
import sys

_STOCK = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "scripts", "stock"))
if _STOCK not in sys.path:
    sys.path.insert(0, _STOCK)


# Phrases that must appear in the shared deep-analysis persona skeleton
REQUIRED_PERSONA = (
    "多维度交叉验证",
    "概率化",
    "T+1",
    "空仓",
    "轻仓",
    "重仓",
    "1周",
    "2周",
)

# Old Layer3 primary narrative that must NOT drive buy decisions anymore
FORBIDDEN_OLD_LAYER3 = (
    "2周到2、3个月内持有且预期盈利10%以上",
    "盈利10%以上的置信度",
)

FORBIDDEN_RESIDUAL = (
    "2-3个月目标价",
    "2周到2、3个月内持有",
    "预期盈利: 10%以上",
    "盈利预期**: 10% 以上",
    "2周到2-3个月",
)


def _sample_left_stock() -> dict:
    return {
        "symbol": "600000",
        "name": "测试股",
        "price": 10.0,
        "change_pct": 1.0,
        "turnover_rate": 2.0,
        "pe": 15.0,
        "amount": 1e8,
        "signals": {},
        "ff_signals": {},
        "fund_dimensions": {},
    }


def _sample_right_stock() -> dict:
    return {
        "symbol": "600000",
        "name": "测试股",
        "price": 10.0,
        "change_pct": 2.0,
        "turnover_rate": 3.0,
        "amount": 2e8,
        "pe": 20.0,
        "market_cap": 5e9,
        "rsi": 55,
        "volume_ratio": 1.8,
        "price_above_ma5": True,
        "near_ma20": True,
        "ma20": 9.5,
        "fund_reversal": True,
        "ff_signals": {
            "main_net_10d": -1e8,
            "main_net_3d": 5e7,
            "main_pct_3d": 4.0,
            "smart_money_phase": "布局期",
            "detail": "测试",
        },
    }


def test_shared_persona_rules_contain_deep_analysis_ruler():
    from llm_reasoning import deepseek_shared_persona_rules

    text = deepseek_shared_persona_rules()
    assert isinstance(text, str) and len(text) > 80
    for phrase in REQUIRED_PERSONA:
        assert phrase in text, f"missing persona phrase: {phrase}"


def test_shared_persona_rules_drop_old_layer3_ten_percent_narrative():
    from llm_reasoning import deepseek_shared_persona_rules

    text = deepseek_shared_persona_rules()
    for phrase in FORBIDDEN_OLD_LAYER3:
        assert phrase not in text, f"old Layer3 narrative still in shared persona: {phrase}"


def test_left_layer3_system_prompt_uses_shared_persona_and_empty_entry_gate():
    from llm_reasoning import (
        deepseek_shared_persona_rules,
        build_left_layer3_system_prompt,
    )

    shared = deepseek_shared_persona_rules()
    prompt = build_left_layer3_system_prompt()
    assert shared[:40] in prompt or "多维度交叉验证" in prompt
    assert "空仓" in prompt
    assert "买入" in prompt and "不买入" in prompt
    # Must map deep-analysis empty-position advice to buy/no-buy
    assert "空仓者" in prompt or "空仓" in prompt
    assert "建仓" in prompt
    for phrase in FORBIDDEN_OLD_LAYER3:
        assert phrase not in prompt


def test_right_layer3_system_prompt_uses_shared_persona_keeps_right_side_rules():
    from llm_reasoning import (
        deepseek_shared_persona_rules,
        build_right_layer3_system_prompt,
    )

    prompt = build_right_layer3_system_prompt()
    assert "多维度交叉验证" in prompt
    assert "右侧" in prompt
    assert "止损" in prompt
    assert "1周" in prompt or "2周" in prompt
    for phrase in FORBIDDEN_OLD_LAYER3:
        assert phrase not in prompt
    # Should not keep 2-3 month +10% as primary target wording
    assert "2-3个月目标价（+10%以上）" not in prompt
    assert "2周到2、3个月内持有，预期盈利10%以上" not in prompt


def test_verdict_system_prompt_uses_shared_persona_horizon():
    from llm_reasoning import build_verdict_system_prompt

    prompt = build_verdict_system_prompt()
    assert "多维度交叉验证" in prompt
    assert "看多" in prompt and "看空" in prompt and "中性" in prompt
    assert "1周" in prompt or "2周" in prompt


def test_left_scoring_user_prompt_drops_old_ten_percent_narrative():
    from scanner import _build_scoring_prompt

    text = _build_scoring_prompt(_sample_left_stock())
    for phrase in FORBIDDEN_OLD_LAYER3 + FORBIDDEN_RESIDUAL:
        assert phrase not in text, f"left scoring still has: {phrase}"
    assert "1周" in text or "2周" in text or "空仓" in text


def test_right_user_prompt_drops_old_horizon():
    from right_side_scanner import _build_rs_prompt

    text = _build_rs_prompt(_sample_right_stock())
    for phrase in FORBIDDEN_RESIDUAL:
        assert phrase not in text, f"right prompt still has: {phrase}"
    assert "1周" in text or "2周" in text


def test_scan_report_headers_use_aligned_horizon():
    import inspect
    from scanner import _generate_report
    from right_side_scanner import _generate_rs_markdown_report

    for fn in (_generate_report, _generate_rs_markdown_report):
        src = inspect.getsource(fn)
        for phrase in FORBIDDEN_RESIDUAL:
            assert phrase not in src, f"{fn.__name__} still has: {phrase}"
        assert "1周" in src or "2周" in src


def test_layer3_judges_wire_shared_left_system_prompt():
    import inspect
    from scanner import _layer3_deepseek_judge, _layer3_local_judge

    for fn in (_layer3_deepseek_judge, _layer3_local_judge):
        src = inspect.getsource(fn)
        assert "build_left_layer3_system_prompt" in src


def test_local_ollama_system_prompt_horizon_aligned():
    from llm_reasoning import _make_system_prompt

    text = _make_system_prompt()
    assert "2周到2-3个月" not in text
    assert "1周" in text or "2周" in text
