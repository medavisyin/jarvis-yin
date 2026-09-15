"""Regression: Casual/Tech English prompts must not force invented long news summaries."""

from __future__ import annotations

import os
import sys
from pathlib import Path

_RAG = os.path.join(os.path.dirname(__file__), "..", "scripts", "rag")
if _RAG not in sys.path:
    sys.path.insert(0, os.path.abspath(_RAG))

from prompts import SYSTEM_PROMPT_CASUAL_ENGLISH, SYSTEM_PROMPT_ENGLISH_LEARNING  # noqa: E402

_AGENT_PY = Path(__file__).resolve().parents[1] / "scripts" / "rag" / "agent.py"


def _assert_no_invention_rules(prompt: str) -> None:
    lowered = prompt.lower()
    assert "do not invent" in lowered
    assert "expand with your knowledge" not in lowered


def test_casual_english_system_prompt_grounding():
    prompt = SYSTEM_PROMPT_CASUAL_ENGLISH
    _assert_no_invention_rules(prompt)
    assert "200-250" not in prompt
    assert "200–250" not in prompt
    assert "What Happened?" in prompt


def test_tech_english_system_prompt_grounding():
    prompt = SYSTEM_PROMPT_ENGLISH_LEARNING
    _assert_no_invention_rules(prompt)
    assert "100-150" not in prompt
    assert "100–150" not in prompt
    assert "Article Summary" in prompt


def test_agent_topic_messages_do_not_pressure_fabricated_detail():
    source = _AGENT_PY.read_text(encoding="utf-8")
    assert "200-250 words" not in source
    assert "DETAILED summary covering ALL key facts" not in source
    assert "and your own knowledge to produce a COMPREHENSIVE CASUAL ENGLISH" not in source
    assert "and your own knowledge about this topic to produce a COMPREHENSIVE TECH ENGLISH" not in source
    assert "Do not invent facts" in source
