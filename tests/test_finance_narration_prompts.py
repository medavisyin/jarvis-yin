"""Unit tests for segmented narration prompts (finance impact vs AI facts-only)."""

from __future__ import annotations

import os
import sys

_RAG = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "scripts", "rag"))
if _RAG not in sys.path:
    sys.path.insert(0, _RAG)

from narration_prompts import segmented_system_user_prompts  # noqa: E402


def test_finance_zh_asks_for_impact():
    sys_p, user_p = segmented_system_user_prompts(
        content_type="finance", lang="zh", seg_name="US", min_chars=200, max_chars=400
    )
    blob = sys_p + user_p
    assert "影响" in blob
    assert "不要添加评论或分析" not in user_p


def test_finance_en_asks_for_impact():
    sys_p, user_p = segmented_system_user_prompts(
        content_type="finance", lang="en", seg_name="US", min_chars=200, max_chars=400
    )
    blob = (sys_p + user_p).lower()
    assert "impact" in blob
    assert "do not add commentary or analysis" not in user_p.lower()


def test_ai_still_bans_analysis():
    sys_p, user_p = segmented_system_user_prompts(
        content_type="ai", lang="zh", seg_name="OpenAI", min_chars=200, max_chars=400
    )
    blob = sys_p + user_p
    assert "评论" in blob or "分析" in blob
