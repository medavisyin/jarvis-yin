"""Tests for intensive-reading multi-tab prompts."""

from __future__ import annotations

import os
import sys

_SCRIPTS = os.path.join(os.path.dirname(__file__), "..", "scripts", "rag")
sys.path.insert(0, os.path.abspath(_SCRIPTS))

from intensive_reading.prompts import (  # noqa: E402
    KIND_VOCAB,
    allowed_kinds,
    analysis_slot_key,
    analysis_user_message,
    normalize_learner_level,
    normalize_output_lang,
    selection_explain_system_prompt,
    system_prompt_for_kind,
    tabs_for_book_type,
)


def test_novel_tabs_order():
    ids = [t["id"] for t in tabs_for_book_type("novel")]
    assert ids[0] == KIND_VOCAB
    assert "plot" in ids and "socratic" in ids
    assert "claim_evidence" not in ids


def test_magazine_tabs_order():
    ids = [t["id"] for t in tabs_for_book_type("magazine")]
    assert ids[0] == KIND_VOCAB
    assert ids == ["vocab", "claim_evidence", "stance", "cultural_cues", "structure", "speaking"]


def test_allowed_kinds():
    assert "rhetoric" in allowed_kinds("novel")
    assert "rhetoric" not in allowed_kinds("magazine")
    assert "stance" in allowed_kinds("magazine")


def test_system_prompt_vocab_vs_plot():
    v = system_prompt_for_kind("vocab")
    p = system_prompt_for_kind("plot")
    assert "vocabulary" in v.lower() or "B2" in v
    assert "Freytag" in p
    assert v != p


def test_system_prompt_unknown_kind_raises():
    import pytest

    with pytest.raises(KeyError):
        system_prompt_for_kind("not_a_real_kind")


def test_user_message_includes_kind():
    msg = analysis_user_message(
        "Wired",
        0,
        "Hello world passage.",
        analysis_kind="stance",
        book_type="magazine",
    )
    assert "stance" in msg
    assert "magazine" in msg
    assert "Hello world" in msg


def test_vocab_user_message_matches_level_and_lang():
    zh = analysis_user_message(
        "T",
        0,
        "Hello world passage.",
        analysis_kind="vocab",
        learner_level="middle_school",
        output_lang="zh",
    )
    assert "A2" in zh
    assert "Simplified Chinese" in zh
    assert "advanced / interesting" not in zh
    uni = analysis_user_message(
        "T", 0, "Hello world passage.", analysis_kind="vocab", output_lang="en"
    )
    assert "advanced / interesting" in uni
    assert "Simplified Chinese" not in uni


def test_vocab_prompt_has_no_fixed_item_cap():
    v = system_prompt_for_kind("vocab")
    assert "5–12" not in v and "5-12" not in v
    assert "fixed number" in v.lower() or "do not cap" in v.lower() or "every item" in v.lower()


def test_vocab_prompt_middle_school_zh():
    v = system_prompt_for_kind("vocab", learner_level="middle_school", output_lang="zh")
    assert "A2" in v or "junior" in v.lower() or "middle-school" in v.lower()
    assert "Simplified Chinese" in v or "simplified chinese" in v.lower()
    uni = system_prompt_for_kind("vocab", learner_level="university", output_lang="en")
    assert "B2" in uni
    assert "Simplified Chinese" not in uni


def test_plot_prompt_zh_uses_chinese_rules():
    p = system_prompt_for_kind("plot", learner_level="university", output_lang="zh")
    assert "Simplified Chinese" in p
    assert "Do not use Chinese" not in p
    assert "Respond entirely in English" not in p
    assert "Freytag" in p


def test_plot_prompt_en_keeps_english_rules():
    p = system_prompt_for_kind("plot", learner_level="university", output_lang="en")
    assert "Respond entirely in English" in p
    assert "Do not use Chinese" in p


def test_default_output_lang_is_zh():
    assert normalize_output_lang(None) == "zh"
    assert normalize_output_lang("") == "zh"


def test_analysis_slot_key_and_normalize():
    assert normalize_learner_level("高中") == "high_school"
    assert normalize_learner_level("bogus") == "university"
    assert normalize_output_lang("zh") == "zh"
    assert normalize_output_lang("中文") == "zh"
    assert analysis_slot_key("vocab", "university", "en") == "vocab__university__en"
    assert analysis_slot_key("plot", "high_school", "zh") == "plot__high_school__zh"
    assert analysis_slot_key("plot", "high_school") == "plot__high_school__zh"


def test_non_vocab_user_message_zh_instructs_chinese():
    msg = analysis_user_message(
        "T",
        0,
        "Hello world passage.",
        analysis_kind="plot",
        output_lang="zh",
    )
    assert "Simplified Chinese" in msg
    en = analysis_user_message(
        "T", 0, "Hello world passage.", analysis_kind="plot", output_lang="en"
    )
    assert "Simplified Chinese" not in en


def test_explain_prompt_uses_learner_level():
    uni = selection_explain_system_prompt("passage", learner_level="university")
    mid = selection_explain_system_prompt("passage", learner_level="middle_school")
    assert "B2" in uni
    assert uni != mid
    assert "A2" in mid or "middle-school" in mid.lower() or "junior" in mid.lower()


def test_novel_socratic_tab_label_is_reflection():
    tabs = tabs_for_book_type("novel")
    soc = [t for t in tabs if t["id"] == "socratic"][0]
    assert soc["label"] == "读后感"


def test_socratic_prompt_is_reflection_coach():
    p = system_prompt_for_kind("socratic", output_lang="zh")
    assert "Pose 3 sharp questions" not in p
    assert "do NOT summarize" not in p
    assert "Socratic seminar" not in p
    assert "读后感" in p
    assert "informal" in p.lower() or "口语" in p
    assert "Simplified Chinese" in p


def test_socratic_user_message_includes_learner_notes():
    msg = analysis_user_message(
        "Novel",
        0,
        "Tom left the room without looking back.",
        analysis_kind="socratic",
        output_lang="zh",
        learner_reflection="我觉得汤姆心虚，without looking back 用得很好。",
    )
    assert "我觉得汤姆心虚" in msg
    assert "without looking back" in msg
    assert "Pose three Socratic" not in msg
    assert "Learner's informal notes" in msg
