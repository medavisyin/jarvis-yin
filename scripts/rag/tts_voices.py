"""Edge-TTS voice presets for Jarvis audio briefings.

Single-narrator paths resolve via language + gender from Global Settings.
Dialogue paths use fixed dual-gender standard voices (not Global gender).
"""

from __future__ import annotations

VOICE_PRESETS: dict[str, dict[str, str]] = {
    "zh": {
        "female": "zh-CN-XiaoxiaoNeural",
        "male": "zh-CN-YunjianNeural",
    },
    "en": {
        "female": "en-US-JennyNeural",
        "male": "en-US-AndrewNeural",
    },
}

# Fixed dual-gender pairs for [Host]/[Guest] dialogue (ignores Global gender).
DIALOGUE_VOICES: dict[str, dict[str, str]] = {
    "zh": {
        "host": VOICE_PRESETS["zh"]["female"],
        "guest": VOICE_PRESETS["zh"]["male"],
    },
    "en": {
        "host": VOICE_PRESETS["en"]["female"],
        "guest": VOICE_PRESETS["en"]["male"],
    },
}

# Extra same-language fallbacks after the two gender presets.
_EXTRA_FALLBACKS: dict[str, list[str]] = {
    "zh": ["zh-CN-XiaoyiNeural", "zh-CN-YunxiNeural"],
    "en": ["en-US-AriaNeural", "en-US-GuyNeural"],
}


def normalize_gender(gender: str | None) -> str:
    g = (gender or "").strip().lower()
    return g if g in ("female", "male") else "female"


def resolve_tts_voice(lang: str, gender: str | None = None) -> str:
    """Return Edge voice id for single-narrator TTS."""
    lang_key = "en" if (lang or "").lower().startswith("en") else "zh"
    g = normalize_gender(gender)
    return VOICE_PRESETS[lang_key][g]


def voice_fallback_chain(voice: str) -> list[str]:
    """Primary voice first, then same-lang presets + extras (no cross-language)."""
    chain: list[str] = [voice]
    lang_key = "en" if voice.startswith("en-") else "zh"
    preferred_gender = "female"
    for g, vid in VOICE_PRESETS[lang_key].items():
        if vid == voice:
            preferred_gender = g
            break
    other = "male" if preferred_gender == "female" else "female"
    for vid in (VOICE_PRESETS[lang_key][other], *_EXTRA_FALLBACKS[lang_key]):
        if vid not in chain:
            chain.append(vid)
    return chain
