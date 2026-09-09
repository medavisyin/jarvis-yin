# Novel 读后感 (Socratic tab) Implementation Plan

> **For the implementing agent:** Follow this plan task-by-task. Complete each step, verify it works, then move to the next.

**Goal:** Turn the novel Analysis tab `socratic` into **读后感**: the learner writes informal chapter notes (insights + word-usage mentions), the model comments/answers, and both are saved per chunk.

**Architecture:** Keep internal kind id `socratic` (no cache migration). Add `reflection` on the analysis slot (persisted via existing `analyses/{chunk}.json`). The tab UI becomes textarea + 评述 (reuses Generate) + commentary below. Replace the Socratic-three-questions prompt with a reflection-coach prompt. Magazine tabs unchanged.

**Tech Stack:** Flask intensive-reading API, `intensive_reading/prompts.py`, `analysis_cache.py`, `scripts/rag/templates/index.html`, pytest.

**Plan review (2026-08-31):** Critical/Important UI persist gaps incorporated below. Do not stream into `#irAnalysis.textContent`; always show the notes textarea; persist `reflection` on every save path; capture notes before tab/chunk/lang change.

---

### Task 1: Persist `reflection` on analysis slots

**Files:**
- Modify: `scripts/rag/intensive_reading/analysis_cache.py` (`empty_slot`, `normalize_slot`)
- Test: `tests/test_intensive_reading_analysis_cache.py`

**Step 1: Write the failing test**

```python
def test_normalize_slot_keeps_reflection():
    s = normalize_slot({
        "text": "评述正文",
        "status": "done",
        "reflection": "这一章让我觉得汤姆有点心虚。",
    })
    assert s["reflection"] == "这一章让我觉得汤姆有点心虚。"
    empty = normalize_slot({})
    assert empty["reflection"] == ""
```

Also add `test_save_roundtrip_reflection` that save/load keeps `reflection` (and that omitting it on a later merge does not invent notes — missing field stays `""` via normalize; when merging a slot that includes reflection, it is kept).

**Step 2: Run to verify fail**

Run: `python -m pytest tests/test_intensive_reading_analysis_cache.py::test_normalize_slot_keeps_reflection -v`

Expected: FAIL (`KeyError` or assertion on missing `reflection`).

**Step 3: Minimal implementation**

- In `empty_slot()`, add `"reflection": ""`.
- In `normalize_slot()`, copy `reflection` like `error` (string, default `""`).

**Step 4: Run to verify pass**

Run: `python -m pytest tests/test_intensive_reading_analysis_cache.py::test_normalize_slot_keeps_reflection tests/test_intensive_reading_analysis_cache.py::test_save_roundtrip_reflection tests/test_intensive_reading_analysis_cache.py::test_save_and_load_merge -v`

Expected: PASS.

---

### Task 2: Replace Socratic prompt with 读后感 coach

**Files:**
- Modify: `scripts/rag/intensive_reading/prompts.py`
- Test: `tests/test_intensive_reading_prompts_tabs.py`

**Step 1: Write failing tests** (tight assertions — no `or` chains that can pass with leftover Socratic text)

```python
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
```

**Step 2: Run to verify fail**

Run: `python -m pytest tests/test_intensive_reading_prompts_tabs.py::test_novel_socratic_tab_label_is_reflection tests/test_intensive_reading_prompts_tabs.py::test_socratic_prompt_is_reflection_coach tests/test_intensive_reading_prompts_tabs.py::test_socratic_user_message_includes_learner_notes -v`

Expected: FAIL (old label / old prompt / missing kwarg).

**Step 3: Minimal implementation**

In `NOVEL_TABS` change socratic label to `"读后感"`. Keep id `"socratic"`. Magazine unchanged.

Replace `_SYSTEM_SOCRATIC` with a reflection coach (keep `_BASE_RULES` so zh replacement still works):

```python
_SYSTEM_SOCRATIC = """You are a warm, sharp close-reading coach responding to a Chinese learner's informal reading notes (读后感) on THIS passage.
""" + _BASE_RULES + """
Task — respond to the learner's notes, not a fresh essay of your own:
- Engage their take on the chapter/excerpt: what they noticed, felt, or guessed. Agree, complicate, or gently correct using evidence from the passage.
- If they mention words, phrases, or usage, comment on those specifically (meaning in this sentence, tone, why the author chose them).
- Answer any questions they asked. If they asked none, still reply to their points.
- Treat informal / colloquial Chinese as welcome; do not scold register. You may briefly polish a phrase only if it helps them reuse it.
- Do NOT pose a Socratic questionnaire. Do NOT ignore their notes to dump a generic analysis.
- Quote short English bits from the passage or from their notes when useful.
Keep it conversational and focused (short sections or bullets). Suitable for a side panel.
"""
```

Update `_KIND_USER_TASK["socratic"]` to: `"Respond to the learner's informal reading notes on this passage."`

Add parameter `learner_reflection: str = ""` to `analysis_user_message`. When `kind == "socratic"`, append the notes block:

```python
if kind == "socratic":
    notes = (learner_reflection or "").strip()
    task += (
        "\n\nLearner's informal notes (colloquial is OK; respond to THESE notes):\n"
        f"\"\"\"\n{notes}\n\"\"\""
    )
```

**Step 4: Run to verify pass**

Run: `python -m pytest tests/test_intensive_reading_prompts_tabs.py -v`

Expected: PASS. Magazine tab list still has no socratic.

---

### Task 3: Analyze API requires notes for socratic

**Files:**
- Modify: `scripts/rag/routes/intensive_reading.py` (`api_analyze`)
- Test: `tests/test_intensive_reading_analyze_routes.py`

**Step 1: Write failing tests**

- POST analyze `analysis_kind=socratic` without `learner_reflection` / blank → 400 with message about notes required.
- POST with notes → mocked Ollama; captured user message contains the notes. Follow existing mock pattern in `test_analyze_valid_kind_streams_with_mocked_ollama`. Capture `requests.post` json `messages` and assert notes appear in the user content.

Reuse `_write_book` with `book_type="novel"`.

**Step 2: Run to verify fail**

Run: `python -m pytest tests/test_intensive_reading_analyze_routes.py -k socratic -v`

Expected: FAIL (no 400 yet).

**Step 3: Minimal implementation**

After parsing `analysis_kind`:

```python
learner_reflection = (data.get("learner_reflection") or data.get("reflection") or "")[:8000]
if analysis_kind == "socratic" and not str(learner_reflection).strip():
    return jsonify({"error": "learner_reflection is required for 读后感"}), 400
```

Pass `learner_reflection=learner_reflection` into `analysis_user_message`.

**Step 4: Run to verify pass**

Run: `python -m pytest tests/test_intensive_reading_analyze_routes.py -k socratic -v`

Expected: PASS.

---

### Task 4: Frontend 读后感 pane + persist

**Files:**
- Modify: `scripts/rag/templates/index.html`
- Test: `tests/test_intensive_reading_passage_ui.py`

This task is the one that will break if implemented naively. Follow **all** of these contracts.

#### 4a. UI structure (always visible notes)

When `kind === 'socratic'`, `irShowActiveAnalysis` must **not** take the idle/empty `box.textContent = 'Click Generate…'` path. Always render a pane:

1. Label 你的读后感
2. `<textarea id="irReflection">` filled from `slot.reflection` (placeholder inviting 口语化章节表述、感悟、单词用法)
3. Commentary region `<div id="irReflectionComment">` from `slot.text` via `irRenderPlainParas` (or `textContent` while streaming)
4. Status/error/truncated copy goes in the commentary region, never by replacing the whole `#irAnalysis` box

Reuse speaking textarea CSS, scoped as `#irAnalysis .ir-reflection-notes`.

#### 4b. Never wipe the textarea while generating

`irRunAnalyzeKind` currently does `document.getElementById('irAnalysis').textContent = live` on each token. For socratic that **destroys** the textarea.

- Stream tokens into `#irReflectionComment` only (create the pane first if missing).
- On `irRenderTabs` / `irShowActiveAnalysis` during `running`, keep the textarea; update commentary text only.
- `irRenderPlainParas` must not run on the whole `#irAnalysis` for this kind.

#### 4c. Capture like 口语

Add `irCaptureReflection()` (mirror `irCaptureSpeakingOral`): if `#irReflection` exists, write its value into `_irState.analyses.socratic.reflection`.

Call it **before** any of:

- `irSelectTab`
- `irLoadChunk` (before `irResetAnalyses`)
- `irOnLearnerPrefsChange` (before reload)
- `irGenerateActiveTab` / `irRunAnalyzeKind`
- textarea `blur`

On blur: capture then `irPersistSlot` (same as speaking). Input can debounce or persist on blur only.

#### 4d. Persist `reflection` on every save path

- `irEmptyAnalysisSlot` includes `reflection: ''`
- `irLoadCachedAnalysis` copies `s.reflection`
- `irPersistSlot` JSON `slot` includes `reflection: slot.reflection || ''`
- `irRunAnalyzeKind` **non-continue**: clear `slot.text` only; **keep** `slot.reflection`
- The `slotSnap` object passed into `irPersistSlot` after analyze **must include `reflection`**. Omitting it writes `""` through `normalize_slot` and wipes notes.

#### 4e. Language switch must not look like notes vanished

Cache key is `kind__level__lang`. Notes are the learner's Chinese draft, not analysis language.

On `irOnLearnerPrefsChange`:

1. `irCaptureReflection()` first
2. Remember current socratic `reflection` string
3. Load cached analysis for the new lang
4. If the newly loaded socratic slot has empty `reflection`, restore the remembered notes
5. Persist the restored notes onto the new cache key (so both lang slots share the draft)

Do not invent a new kind id.

#### 4f. Generate button / Continue

- Hide Continue for socratic (accepted: `PASSAGE_WINDOW` 12000; long chapters only comment on the first window, same as other tabs).
- Generate label: `评述` if no commentary yet, `再评述` if `slot.text` / status done.
- Disable 评述 when `!(slot.reflection || '').trim()`; listen to textarea `input` and call `irUpdateContinueBtn`.
- `irGenerateActiveTab`: if socratic and blank notes, toast `先写读后感再评述` and return.
- POST body adds `learner_reflection: slot.reflection`.

#### 4g. Tab checkmark

If `slot.reflection` is non-empty, show a mark even when commentary is still idle (notes saved, not yet 评述). Keep `✓` for done commentary.

#### 4h. Stale Socratic cache

Old chunk files may still have three-question `text`. Show it in the commentary pane until the user clicks 再评述. No migration/wipe.

**Step 1: Write failing UI contract tests**

```python
def test_novel_socratic_tab_is_reflection_ui():
    text = HTML.read_text(encoding="utf-8")
    tabs = text[text.find("var _IR_NOVEL_TABS"):text.find("var _IR_MAG_TABS")]
    assert "socratic" in tabs
    assert "读后感" in tabs
    mag = text[text.find("var _IR_MAG_TABS"):text.find("var _IR_SPEAKING_TAB")]
    assert "socratic" not in mag
    assert "irReflection" in text
    assert "irReflectionComment" in text
    assert "function irCaptureReflection" in text
    assert "learner_reflection" in text
    show = text[text.find("function irShowActiveAnalysis"):text.find("function irCaptureSpeakingOral")]
    assert "socratic" in show
    empty = text[text.find("function irEmptyAnalysisSlot"):text.find("function irEmptySpeaking")]
    assert "reflection" in empty
    persist = text[text.find("async function irPersistSlot"):text.find("async function irSaveProgress")]
    assert "reflection" in persist
    run = text[text.find("async function irRunAnalyzeKind"):text.find("function openExplainThisModal")]
    assert "irReflectionComment" in run
    assert "learner_reflection" in run
```

Also assert `irOnLearnerPrefsChange` calls `irCaptureReflection`, and `irLoadChunk` calls it.

**Step 2: Run to verify fail**

Run: `python -m pytest tests/test_intensive_reading_passage_ui.py::test_novel_socratic_tab_is_reflection_ui -v`

Expected: FAIL.

**Step 3: Minimal UI implementation** matching 4a–4h.

**Step 4: Run to verify pass**

Run: `python -m pytest tests/test_intensive_reading_passage_ui.py tests/test_intensive_reading_prompts_tabs.py tests/test_intensive_reading_analysis_cache.py tests/test_intensive_reading_analyze_routes.py -q`

Expected: PASS.

---

### Task 5: Manual verification

1. `jarvis-restart.bat /AGENT` then Ctrl+F5 on `http://localhost:18889`.
2. Open a **novel** (not magazine). Confirm last tab is **读后感**, not 苏格拉底提问.
3. Write informal notes mentioning a word; click **评述**. Commentary should address the notes in the selected Analysis language. Textarea must stay visible while tokens stream.
4. Reload chunk / reopen book: notes + commentary still there.
5. Switch 中文/英文 and back: notes still in the textarea.
6. Magazine: no 读后感 tab. Other novel tabs unchanged.

---

## Out of scope

- Magazine
- Passage / Explain / 口语
- New kind id `reflection`
- Restoring Socratic three questions
- Sending the full chunk past `PASSAGE_WINDOW` for 读后感
- Commit unless the user asks
