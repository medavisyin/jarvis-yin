"""Wiki/RAG answers must not be German; Chinese or English only."""

from __future__ import annotations

import os
import sys

_RAG = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "scripts", "rag"))
if _RAG not in sys.path:
    sys.path.insert(0, _RAG)

from prompts import OUTPUT_LANGUAGE_RULE, SYSTEM_PROMPT_COMPACT, SYSTEM_PROMPT_FULL  # noqa: E402
from wiki_summary import _SYSTEM_PROMPT, _SYSTEM_PROMPT_NEW, summarize_wiki_page  # noqa: E402


def test_output_language_rule_forbids_german_allows_zh_or_en():
    text = OUTPUT_LANGUAGE_RULE.lower()
    assert "never write german" in text or "never use german" in text
    assert "chinese" in text
    assert "english" in text


def test_rag_system_prompts_include_output_language_rule():
    assert OUTPUT_LANGUAGE_RULE in SYSTEM_PROMPT_FULL
    assert OUTPUT_LANGUAGE_RULE in SYSTEM_PROMPT_COMPACT
    assert "same language the user uses" not in SYSTEM_PROMPT_FULL.lower()


def test_wiki_summary_prompts_are_english_never_german():
    for prompt in (_SYSTEM_PROMPT, _SYSTEM_PROMPT_NEW):
        lower = prompt.lower()
        assert "english" in lower
        assert "never" in lower and "german" in lower


class _Resp:
    def raise_for_status(self):
        return None

    def json(self):
        return {"message": {"content": "July 2026 tech update covering platform changes."}}


def test_wiki_summary_ollama_system_prompt_forbids_german():
    captured = {}

    def fake_post(url, json=None, timeout=None):
        captured["json"] = json
        return _Resp()

    summarize_wiki_page(
        {
            "title": "Tech-Update Juli 2026",
            "space": "synava Technology",
            "version_number": 1,
            "summary": "Lizenz-Dashboard und Demo-Umgebungen wurden aktualisiert.",
        },
        http_post=fake_post,
    )
    system = captured["json"]["messages"][0]["content"].lower()
    assert "english" in system
    assert "german" in system
