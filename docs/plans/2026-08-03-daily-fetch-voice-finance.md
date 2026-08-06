# Daily Fetch Voice Settings + Finance Impact Narration Implementation Plan

> **For the implementing agent:** Follow this plan task-by-task. Complete each step, verify it works, then move to the next.

**Goal:** Add Global Settings voice gender presets (standard Mandarin / US English, no dialects), wire them into all single-narrator TTS paths, fix dialogue defaults away from dialect/Indian accents, and make Finance audio narration include a short market-impact sentence per item.

**Architecture:** Extract a pure `scripts/rag/tts_voices.py` registry (presets, dialogue pairs, resolve + fallback). Persist `audio_voice_zh` / `audio_voice_en` (`female`|`male`) in `.global_settings.json`. Single-narrator TTS (`tts_voice_for_lang` / segmented MP3) reads gender from settings; dialogue keeps fixed dual-gender standard voices. Finance-only change to `_generate_segmented_narrations` prompts (text reports untouched).

**Tech Stack:** Python 3, Edge TTS voice IDs, Flask settings API (`agent.py`), Global Settings UI (`index.html`), pytest.

**Approved decisions (do not re-litigate):**
- Approach A: gender enums, not full Edge voice-ID picker
- Defaults: zh female + en female (普通话女 / 美式女)
- No dialects; no `en-IN-*` as primary
- Global gender applies to single-narrator only; dialogue fixed dual-gender (standard voices)
- Scope: Daily Fetch AI + Finance + Knowledge Audio (Knowledge is dialogue → fixed pair only)
- Finance impact: audio narration only
- Same-session plan; implement after plan routing confirmation

**Plan amendments (from critical review — do not re-litigate):**

1. **`_tts_to_mp3` voice param caveat:** Without dialogue markers, synthesis uses `_DIALOGUE_VOICES[lang]["host"]`; the `voice` argument is mainly for `en-` lang detection. Do **not** wire Global gender into the dialogue path. Single-narrator gender applies only via `_tts_segments_to_mp3` + `tts_voice_from_settings` (Daily Fetch AI/Finance).
2. **Task 5 docs are mandatory:** Update `docs/implementation/personal/daily-fetch-impl.md` Configuration bullet that still says `"en" selects en-IN-PrabhatNeural` — replace with voice presets + `audio_voice_*` + finance impact narration note.
3. **Out of scope (leave unchanged):** `scripts/output/generate-audio.py` (Xiaoni) and `scripts/output/generate-video.py` (Prabhat). Task 5 `rg` is scoped to `scripts/rag` + `tests` only — do not treat those CLI leftovers as plan failures.

---

### Task 1: Pure voice registry + unit tests (TDD)

**Files:**
- Create: `scripts/rag/tts_voices.py`
- Create: `tests/test_tts_voices.py`

**Step 1: Write the failing tests**

```python
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
    # after primary, remaining should still be zh voices; primary gender voice not repeated
    assert len(chain) >= 2


def test_normalize_gender():
    assert normalize_gender("female") == "female"
    assert normalize_gender("male") == "male"
    assert normalize_gender("") == "female"
    assert normalize_gender(None) == "female"
```

**Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_tts_voices.py -v`

Expected: FAIL (import error / module missing)

**Step 3: Implement `scripts/rag/tts_voices.py`**

```python
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
    # same gender already primary; add other gender next, then extras
    other = "male" if preferred_gender == "female" else "female"
    for vid in (VOICE_PRESETS[lang_key][other], *_EXTRA_FALLBACKS[lang_key]):
        if vid not in chain:
            chain.append(vid)
    return chain
```

**Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_tts_voices.py -v`

Expected: PASS (all 6 tests)

---

### Task 2: Wire `ai_news.py` to the registry

**Files:**
- Modify: `scripts/rag/routes/ai_news.py` (TTS constants ~1194–1218, callers of `tts_voice_for_lang` / `_DIALOGUE_VOICES` / `_voice_fallback_chain` / `TTS_VOICE_*`)
- Modify: `scripts/rag/routes/daily_fetch.py` (calls that pass `voice=tts_voice_for_lang(...)`)

**Step 1: Replace hardcoded voice constants**

In `ai_news.py`:
- `_RAG_PKG_DIR` is already on `sys.path` — use `from tts_voices import ...` directly.
- Keep thin wrappers for backward compatibility:
- Do **not** change `_tts_to_mp3` to read Global gender (see plan amendment #1).

```python
from tts_voices import (
    DIALOGUE_VOICES as _DIALOGUE_VOICES,
    resolve_tts_voice,
    voice_fallback_chain as _voice_fallback_chain,
)

# Backward-compat aliases (defaults = female)
TTS_VOICE_ZH = resolve_tts_voice("zh", "female")
TTS_VOICE_EN = resolve_tts_voice("en", "female")


def tts_voice_for_lang(lang: str, gender: str | None = None) -> str:
    """Edge voice for single-narrator briefing; gender from Global Settings when provided."""
    return resolve_tts_voice(lang, gender)


def tts_voice_from_settings(lang: str, settings: dict | None) -> str:
    settings = settings or {}
    key = "audio_voice_en" if (lang or "").lower().startswith("en") else "audio_voice_zh"
    return resolve_tts_voice(lang, settings.get(key))
```

- Delete old assignments: `zh-CN-shaanxi-XiaoniNeural`, `en-IN-PrabhatNeural`, old `_TTS_VOICE_FALLBACKS_*`, old `_DIALOGUE_VOICES` dict body.
- Update every `_voice_fallback_chain` / dialogue usage to the imported helpers (names can stay).

**Step 2: Pass gender from settings at Daily Fetch call sites**

In `daily_fetch.py`, where AI/Finance call `_tts_segments_to_mp3(..., voice=tts_voice_for_lang(lang))`, change to:

```python
from ai_news import tts_voice_from_settings  # or keep tts_voice_for_lang and pass gender

voice = tts_voice_from_settings(ai_lang, gs)  # gs already loaded via _get_global_settings()
_tts_segments_to_mp3(narrations_ai, ai_mp3, voice=voice)
```

Same for finance audio block.

**Step 3: Knowledge Audio dialogue path**

- Keep using `_DIALOGUE_VOICES` (fixed pair) — do **not** apply Global gender.
- Last-resort fallback in `_save_ka_chunk` that currently uses outer `voice` (`TTS_VOICE_*`): change to `ka_voices["host"]` so it never falls back to dialect/Indian IDs.

**Step 4: Smoke-import check**

Run: `python -c "import sys; sys.path.insert(0, r'scripts/rag'); from tts_voices import resolve_tts_voice; print(resolve_tts_voice('en','female'))"`

Expected: `en-US-JennyNeural`

---

### Task 3: Global Settings defaults + API + UI

**Files:**
- Modify: `scripts/rag/agent.py` (`_GLOBAL_SETTINGS_DEFAULTS` ~1149–1154, POST loop already iterates defaults keys)
- Modify: `scripts/rag/templates/index.html` (Global Settings modal ~259–280, `openGlobalSettings` ~4091, `saveGlobalSettings` ~4110)

**Step 1: Defaults**

```python
_GLOBAL_SETTINGS_DEFAULTS = {
    "audio_lang_ai": "zh",
    "audio_lang_finance": "zh",
    "audio_lang_knowledge": "zh",
    "audio_voice_zh": "female",
    "audio_voice_en": "female",
    "deepseek_api_key": "",
}
```

No special migration needed: missing keys merge from defaults on load.

**Step 2: UI — add Audio Voice section under Audio Language**

Add (Chinese labels OK; match existing bilingual style):

```html
<div style="color:#8b8fa4;font-size:0.78em;margin-bottom:8px;text-transform:uppercase;letter-spacing:0.5px">Audio Voice / 音色</div>
<!-- settVoiceZh: 普通话女 / 普通话男 -->
<!-- settVoiceEn: 美式女 / 美式男 -->
<p style="font-size:0.72em;color:#6b7280;margin:0">Applies to single-narrator audio. Dialogue keeps fixed dual voices.</p>
```

Options:
- `settVoiceZh`: `female` = 普通话女, `male` = 普通话男
- `settVoiceEn`: `female` = 美式女, `male` = 美式男

**Step 3: Load/save JS**

In `openGlobalSettings`:
```javascript
document.getElementById('settVoiceZh').value = d.audio_voice_zh || 'female';
document.getElementById('settVoiceEn').value = d.audio_voice_en || 'female';
```

In `saveGlobalSettings` body:
```javascript
audio_voice_zh: document.getElementById('settVoiceZh').value,
audio_voice_en: document.getElementById('settVoiceEn').value,
```

**Step 4: Manual UI check**

Open Global Settings → confirm new selects appear, save, reload page, reopen → values persist via `/api/settings`.

---

### Task 4: Finance narration prompt — impact sentence (TDD)

**Files:**
- Modify: `scripts/rag/routes/ai_news.py` (`_generate_segmented_narrations` finance branches ~1062–1110)
- Create: `tests/test_finance_narration_prompts.py`

**Step 1: Extract testable prompt builder**

Add a small helper in `ai_news.py` (or `tts_voices` sibling `scripts/rag/narration_prompts.py` if import of `ai_news` is too heavy — prefer extracting to `scripts/rag/narration_prompts.py` to keep tests Flask-free):

```python
# scripts/rag/narration_prompts.py

def segmented_system_user_prompts(
    *,
    content_type: str,
    lang: str,
    seg_name: str,
    min_chars: int,
    max_chars: int,
) -> tuple[str, str]:
    """Return (system_prompt, user_prompt) for one segmented narration call."""
    ...
```

Move the existing if/else prompt strings from `_generate_segmented_narrations` into this function. For `content_type == "finance"`:

**English system (key changes):**
- Allow one short impact clause per item
- Still no long commentary, predictions, self-intro, markdown

**English user (key lines):**
```
For each item: 1-2 sentences on what happened, then ONE short sentence on market impact
(who/what is affected: rates, equities, sectors, risk appetite, policy transmission).
Do not speculate wildly; keep the impact concrete and brief.
```

**Chinese:** mirror the same structure（事实 1–2 句 + 影响 1 句）.

**AI / non-finance:** keep current “no commentary / analysis” wording unchanged.

**Step 2: Failing tests**

```python
from narration_prompts import segmented_system_user_prompts

def test_finance_zh_asks_for_impact():
    sys_p, user_p = segmented_system_user_prompts(
        content_type="finance", lang="zh", seg_name="US", min_chars=200, max_chars=400
    )
    blob = sys_p + user_p
    assert "影响" in blob
    assert "不要添加评论或分析" not in user_p  # old ban removed for finance


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
```

**Step 3: Implement prompts; rewire `_generate_segmented_narrations` to call the helper**

**Step 4: Run**

Run: `python -m pytest tests/test_finance_narration_prompts.py tests/test_tts_voices.py -v`

Expected: PASS

---

### Task 5: Integration sanity + docs touch

**Files:**
- Modify (mandatory): `docs/implementation/personal/daily-fetch-impl.md` — fix Configuration audio bullet (`en-IN-PrabhatNeural`); document `audio_voice_zh` / `audio_voice_en` presets and finance impact narration in audio
- Optional: update memory next-steps checkboxes when execution finishes (not required in this task)

**Out of scope reminder:** Do not change `scripts/output/generate-audio.py` or `generate-video.py`.

**Step 1: Grep for stale voice IDs (scoped)**

Run: `rg -n "shaanxi|en-IN-Prabhat|en-IN-Neerja|XiaoniNeural" scripts/rag tests`

Expected: no matches under `scripts/rag` or `tests` as live defaults. Matches under `scripts/output/` are **out of scope** and OK to ignore.

**Step 2: Run full related pytest**

Run: `python -m pytest tests/test_tts_voices.py tests/test_finance_narration_prompts.py -v`

Expected: all PASS

**Step 3: Manual acceptance checklist**

1. Global Settings → 中文男声 + 英文男声 → Save
2. Run Finance audio (or Daily Fetch finance step) with zh → hear male Mandarin, impact sentences present
3. Switch AI lang to English → segmented AI uses `en-US-AndrewNeural` (male)
4. Knowledge Audio (dialogue) → female host + male guest, no Shaanxi dialect
5. Reset voices to female defaults → persists after reload
6. Confirm finance **text** JSON/report files unchanged in structure (no new impact fields required)

---

## Verification Summary

- [ ] `tts_voices` presets: Xiaoxiao/Yunjian + Jenny/Andrew; no shaanxi / en-IN primaries
- [ ] Settings keys `audio_voice_zh` / `audio_voice_en` default `female`; UI load/save works
- [ ] Daily Fetch single-narrator uses settings gender via `_tts_segments_to_mp3` only
- [ ] Dialogue / Knowledge Audio uses fixed dual-gender standard voices (Global gender ignored)
- [ ] Finance prompts require short impact sentence; AI prompts still ban analysis
- [ ] pytest: `test_tts_voices.py` + `test_finance_narration_prompts.py` green
- [ ] `rg` clean of old dialect/Indian default voice IDs in `scripts/rag` (+ `tests`)
- [ ] `daily-fetch-impl.md` no longer documents `en-IN-PrabhatNeural` as the English voice
- [ ] `scripts/output/generate-*.py` left unchanged (out of scope)

---

## Notes for executor

- Prefer extracting `narration_prompts.py` over importing Flask `ai_news` in unit tests.
- Do not wire Global gender into `_tts_to_mp3` / dialogue paths.
- Do not commit unless the user asks.
- After implementation, offer `requesting-code-review` per session rules.
