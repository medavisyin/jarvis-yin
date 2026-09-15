"""Unit tests for Edge-TTS voice presets and resolution."""

from __future__ import annotations

import os
import sys

_RAG = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "scripts", "rag"))
if _RAG not in sys.path:
    sys.path.insert(0, _RAG)

from tts_voices import (  # noqa: E402
    DIALOGUE_VOICES,
    VOICE_PRESETS,
    normalize_gender,
    resolve_tts_voice,
    voice_fallback_chain,
)


def test_presets_are_standard_no_dialect_or_indian():
    for lang in ("zh", "en"):
        for gender in ("female", "male"):
            vid = VOICE_PRESETS[lang][gender]
            assert "shaanxi" not in vid.lower()
            assert not vid.startswith("en-IN-")
    assert VOICE_PRESETS["zh"]["female"] == "zh-CN-XiaoxiaoNeural"
    assert VOICE_PRESETS["zh"]["male"] == "zh-CN-YunjianNeural"
    assert VOICE_PRESETS["en"]["female"] == "en-US-JennyNeural"
    assert VOICE_PRESETS["en"]["male"] == "en-US-AndrewNeural"


def test_resolve_defaults_to_female():
    assert resolve_tts_voice("zh") == VOICE_PRESETS["zh"]["female"]
    assert resolve_tts_voice("en", None) == VOICE_PRESETS["en"]["female"]
    assert resolve_tts_voice("en", "bogus") == VOICE_PRESETS["en"]["female"]


def test_resolve_male():
    assert resolve_tts_voice("zh", "male") == VOICE_PRESETS["zh"]["male"]
    assert resolve_tts_voice("en", "male") == VOICE_PRESETS["en"]["male"]


def test_dialogue_fixed_dual_gender_standard():
    assert DIALOGUE_VOICES["zh"]["host"] == VOICE_PRESETS["zh"]["female"]
    assert DIALOGUE_VOICES["zh"]["guest"] == VOICE_PRESETS["zh"]["male"]
    assert DIALOGUE_VOICES["en"]["host"] == VOICE_PRESETS["en"]["female"]
    assert DIALOGUE_VOICES["en"]["guest"] == VOICE_PRESETS["en"]["male"]
    for lang in ("zh", "en"):
        for role in ("host", "guest"):
            v = DIALOGUE_VOICES[lang][role]
            assert "shaanxi" not in v.lower()
            assert not v.startswith("en-IN-")


def test_fallback_same_lang_prefers_same_gender_first():
    male_zh = VOICE_PRESETS["zh"]["male"]
    chain = voice_fallback_chain(male_zh)
    assert chain[0] == male_zh
    assert all(v.startswith("zh-") for v in chain)
    assert len(chain) >= 2


def test_normalize_gender():
    assert normalize_gender("female") == "female"
    assert normalize_gender("male") == "male"
    assert normalize_gender("") == "female"
    assert normalize_gender(None) == "female"
