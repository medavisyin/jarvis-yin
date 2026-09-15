"""Unit tests for deep-analysis recheck veto policy (left/right scanners)."""

from __future__ import annotations

import os
import sys

_STOCK = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "scripts", "stock"))
if _STOCK not in sys.path:
    sys.path.insert(0, _STOCK)

from recheck_policy import (  # noqa: E402
    NEUTRAL_VETO_MIN_CONFIDENCE,
    apply_recheck_action,
    apply_recheck_veto,
    classify_recheck_action,
    coerce_confidence,
    normalize_empty_entry,
    should_veto_recheck,
)


def test_veto_bearish():
    veto, reason = should_veto_recheck(
        {"ok": True, "direction": "看空", "confidence": 70, "veto_reason": "主力出货"}
    )
    assert veto is True
    assert "出货" in reason


def test_veto_high_confidence_neutral():
    veto, reason = should_veto_recheck(
        {"ok": True, "direction": "中性", "confidence": NEUTRAL_VETO_MIN_CONFIDENCE, "reason": "信号不明"}
    )
    assert veto is True
    assert "中性" in reason or "信号" in reason


def test_keep_low_confidence_neutral():
    veto, _ = should_veto_recheck(
        {"ok": True, "direction": "中性", "confidence": NEUTRAL_VETO_MIN_CONFIDENCE - 1, "reason": "略犹豫"}
    )
    assert veto is False


def test_keep_bullish():
    veto, _ = should_veto_recheck(
        {"ok": True, "direction": "看多", "confidence": 80, "reason": "资金回流"}
    )
    assert veto is False


def test_no_veto_when_not_ok():
    veto, _ = should_veto_recheck({"ok": False, "direction": "看空", "confidence": 90})
    assert veto is False


def test_keep_neutral_when_confidence_missing():
    veto, _ = should_veto_recheck({"ok": True, "direction": "中性", "reason": "未给置信度"})
    assert veto is False


def test_keep_neutral_when_confidence_none():
    veto, _ = should_veto_recheck(
        {"ok": True, "direction": "中性", "confidence": None, "reason": "置信度空"}
    )
    assert veto is False


def test_keep_neutral_when_confidence_invalid():
    veto, _ = should_veto_recheck(
        {"ok": True, "direction": "中性", "confidence": "N/A", "reason": "非法置信度"}
    )
    assert veto is False


def test_veto_bearish_when_confidence_missing():
    veto, reason = should_veto_recheck(
        {"ok": True, "direction": "看空", "veto_reason": "缺置信度仍判空"}
    )
    assert veto is True
    assert "判空" in reason or "出货" in reason or "缺置信度" in reason


def test_apply_recheck_veto_marks_pick():
    pick = {
        "symbol": "600000",
        "verdict": "买入",
        "final_score": 75,
        "reasoning": "原理由",
    }
    changed = apply_recheck_veto(
        pick,
        {"ok": True, "direction": "中性", "confidence": 65, "reason": "观望为主"},
        score_cap=59,
    )
    assert changed is True
    assert pick["recheck_vetoed"] is True
    assert pick["verdict"] == "观望"
    assert pick["final_score"] <= 59
    assert "深度复核否决" in pick["reasoning"]


def test_apply_recheck_veto_keeps_pick_unchanged():
    pick = {
        "symbol": "600000",
        "verdict": "买入",
        "final_score": 75,
        "reasoning": "原理由",
    }
    snapshot = dict(pick)
    changed = apply_recheck_veto(
        pick,
        {"ok": True, "direction": "看多", "confidence": 80, "reason": "资金回流"},
        score_cap=59,
    )
    assert changed is False
    assert pick == snapshot
    assert "recheck_vetoed" not in pick


def test_normalize_empty_entry_defaults_to_now():
    assert normalize_empty_entry({"ok": True, "direction": "看多"}) == "now"
    assert normalize_empty_entry({"ok": True, "empty_entry": "WAIT_PULLBACK"}) == "wait_pullback"
    assert normalize_empty_entry({"ok": True, "empty_entry": "bogus"}) == "now"


def test_coerce_confidence_null_and_invalid():
    assert coerce_confidence(None) == 50
    assert coerce_confidence("") == 50
    assert coerce_confidence("N/A") == 50
    assert coerce_confidence(72) == 72
    assert coerce_confidence("65.7") == 65
    assert coerce_confidence(None, default=40) == 40


def test_classify_bullish_now_passes_both_sides():
    v = {"ok": True, "direction": "看多", "confidence": 80, "empty_entry": "now"}
    assert classify_recheck_action(v, side="left")[0] == "pass"
    assert classify_recheck_action(v, side="right")[0] == "pass"


def test_classify_wait_pullback_left_soft_right_veto():
    v = {
        "ok": True,
        "direction": "看多",
        "confidence": 75,
        "empty_entry": "wait_pullback",
        "entry_note": "KDJ超买不宜追",
    }
    left_action, left_reason = classify_recheck_action(v, side="left")
    right_action, _ = classify_recheck_action(v, side="right")
    assert left_action == "soft_wait"
    assert "回调" in left_reason or "追" in left_reason or "KDJ" in left_reason
    assert right_action == "veto"


def test_classify_avoid_vetoes_both_sides():
    v = {"ok": True, "direction": "看多", "confidence": 70, "empty_entry": "avoid"}
    assert classify_recheck_action(v, side="left")[0] == "veto"
    assert classify_recheck_action(v, side="right")[0] == "veto"


def test_classify_direction_veto_beats_empty_entry():
    v = {
        "ok": True,
        "direction": "看空",
        "confidence": 80,
        "empty_entry": "now",
        "veto_reason": "主力出货",
    }
    assert classify_recheck_action(v, side="left")[0] == "veto"
    assert classify_recheck_action(v, side="right")[0] == "veto"


def test_apply_soft_wait_rewrites_buy_range():
    pick = {
        "symbol": "601899",
        "verdict": "买入",
        "final_score": 78,
        "price": 32.95,
        "buy_low": 32.6,
        "buy_high": 33.2,
        "reasoning": "原理由",
        "strategy": "现价附近建仓",
    }
    action = apply_recheck_action(
        pick,
        {
            "ok": True,
            "direction": "看多",
            "confidence": 72,
            "empty_entry": "wait_pullback",
            "pullback_low": 31.1,
            "pullback_high": 31.9,
            "entry_note": "高开回落不宜追",
        },
        side="left",
        score_cap=59,
    )
    assert action == "soft_wait"
    assert pick.get("recheck_wait_pullback") is True
    assert pick.get("recheck_vetoed") is not True
    assert pick["verdict"] == "等回调"
    assert pick["buy_low"] == 31.1
    assert pick["buy_high"] == 31.9
    assert "等回调" in pick["reasoning"] or "深度" in pick["reasoning"]


def test_apply_soft_wait_skips_invalid_pullback_above_price():
    pick = {
        "symbol": "601899",
        "verdict": "买入",
        "final_score": 78,
        "price": 32.95,
        "buy_low": 32.6,
        "buy_high": 33.2,
        "reasoning": "原理由",
        "strategy": "现价附近建仓",
    }
    action = apply_recheck_action(
        pick,
        {
            "ok": True,
            "direction": "看多",
            "confidence": 72,
            "empty_entry": "wait_pullback",
            "pullback_low": 33.5,
            "pullback_high": 34.0,
            "entry_note": "坏区间",
        },
        side="left",
        score_cap=59,
    )
    assert action == "soft_wait"
    assert pick["verdict"] == "等回调"
    assert pick["buy_low"] == 32.6
    assert pick["buy_high"] == 33.2


def test_apply_soft_wait_skips_straddling_pullback_high_above_price():
    """Important-1: low<=price<high must not rewrite buy range (not a clean pullback)."""
    pick = {
        "symbol": "601899",
        "verdict": "买入",
        "final_score": 78,
        "price": 32.95,
        "buy_low": 32.6,
        "buy_high": 33.2,
        "reasoning": "原理由",
        "strategy": "现价附近建仓",
    }
    action = apply_recheck_action(
        pick,
        {
            "ok": True,
            "direction": "看多",
            "confidence": 72,
            "empty_entry": "wait_pullback",
            "pullback_low": 31.1,
            "pullback_high": 34.0,
            "entry_note": "跨现价区间",
        },
        side="left",
        score_cap=59,
    )
    assert action == "soft_wait"
    assert pick["verdict"] == "等回调"
    assert pick["buy_low"] == 32.6
    assert pick["buy_high"] == 33.2


def test_apply_recheck_action_keeps_pick_when_not_ok():
    pick = {
        "symbol": "601899",
        "verdict": "买入",
        "final_score": 78,
        "buy_low": 32.6,
        "buy_high": 33.2,
        "reasoning": "原理由",
    }
    snapshot = dict(pick)
    action = apply_recheck_action(
        pick,
        {"ok": False, "direction": "看空", "confidence": 90, "empty_entry": "avoid"},
        side="left",
        score_cap=59,
    )
    assert action == "pass"
    assert pick == snapshot


def test_apply_avoid_hard_vetoes_both_sides():
    for side in ("left", "right"):
        pick = {
            "symbol": "601899",
            "verdict": "买入",
            "final_score": 78,
            "reasoning": "原理由",
        }
        action = apply_recheck_action(
            pick,
            {
                "ok": True,
                "direction": "看多",
                "confidence": 70,
                "empty_entry": "avoid",
                "entry_note": "结构不支持建仓",
            },
            side=side,
            score_cap=59,
        )
        assert action == "veto", side
        assert pick["recheck_vetoed"] is True
        assert pick["verdict"] == "观望"
        assert pick["final_score"] <= 59


def test_apply_right_wait_pullback_hard_vetoes():
    pick = {
        "symbol": "601899",
        "verdict": "买入",
        "final_score": 78,
        "reasoning": "原理由",
    }
    action = apply_recheck_action(
        pick,
        {
            "ok": True,
            "direction": "看多",
            "confidence": 72,
            "empty_entry": "wait_pullback",
            "pullback_low": 31.1,
            "pullback_high": 31.9,
        },
        side="right",
        score_cap=59,
    )
    assert action == "veto"
    assert pick["recheck_vetoed"] is True
    assert pick["verdict"] == "观望"
    assert pick["final_score"] <= 59
