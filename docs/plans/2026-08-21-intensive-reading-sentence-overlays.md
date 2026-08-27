# Intensive Reading Sentence Overlays Implementation Plan

> **For the implementing agent:** Follow this plan task-by-task. Complete each step, verify it works, then move to the next.

**Goal:** Let the user pick novels in Jarvis, pre-generate every-sentence Chinese glosses plus 好词好句 via local Ollama, show them as tappable highlights in Passage, and export a phone-openable pack (`reader.html` with inlined data + `book.pack.json`).

**Architecture:** Split each chunk with the same paragraph rules as `irRenderPassage`, then sentence-split locally. **Two** Ollama JSON calls per chunk (sentence glosses, then vocab) map glosses by sentence index and locate vocab phrases in the original paragraph text. Persist `docs/books/{id}/overlays/{n}.json`. Passage wraps sentence/vocab spans. Export zips a self-contained `reader.html` (Chrome `file://` cannot fetch sibling JSON) plus the same data as `book.pack.json` for a future native app.

**Tech Stack:** Python 3, Flask intensive-reading blueprint, local Ollama (`/api/chat`, `think: false`, `format: json`), pytest under `tests/` (gitignored, still run locally), vanilla JS in `scripts/rag/templates/index.html`.

**Approved decisions (do not re-litigate):**

- Novels only; user checks books on the IR list. Magazines out of scope.
- Every sentence gets a Chinese meaning (including simple ones). Vocab is a separate underline layer.
- Jarvis one-click pre-generates the whole book with **local Ollama**. Skip completed chunks. Do not use DeepSeek for this job.
- Visual: sentence = light background; vocab = colored underline; vocab tap wins over sentence tap.
- Desktop popover near tap (reuse Explain-card feel). Selection-drag Explain stays.
- Pack = zip with inlined `reader.html` + `book.pack.json`. No original PDF/EPUB, no RAG, no API keys.
- No native Android app this round.
- Overlays live in `overlays/`, not inside `analyses/` tab prose.
- Rebuild from original must clear overlays (sentence boundaries change).

**Plan amendments (from critical review — do not re-litigate):**

1. **Two Ollama calls per chunk, not one.** Sentence glosses and 好词好句 separately. Combined output hits `num_predict=4096` truncation on a 1200-word chunk. If a chunk still has `> 30` sentences, window glosses in batches of 25 (same `sentences` numbering). Vocab stays one call with the full passage.
2. **Ollama payload:** `think: false`, `format: "json"`, `stream: false`. Same host/model as existing Analyze (`_ollama_settings`), not the fast Explain model.
3. **Skip-if-done is keyed by learner_level.** Skip only when overlay `status==done` AND `learner_level` matches the run. Changing 大学→高中 regenerates. `error` overlays are never skipped.
4. **Click vs Explain:** Passage `click` opens overlay popover only if `window.getSelection()` is collapsed (or range length 0). A drag-select must still show the existing Explain button and must not open the gloss card.
5. **Task 6 tests are pure functions, not Flask `test_client`.** Existing IR tests mostly read `index.html` as text. Cover `start_overlay_job` / reject magazine / stale `running` on load / cancel flag without spinning a WSGI app unless a fixture already exists.
6. **`align_vocab` normalizes quotes/apostrophes** (`'` `'` `'` `"` `"` `"`) before search; match against original para and store **original** `start/end` in the source string.
7. **Cancel:** `POST /api/intensive-reading/overlay/cancel` sets a flag; the job stops after the current chunk (do not kill Ollama mid-request). Meta `state` becomes `idle` with partial `done` counts.
8. **Shared span layout helper** in Python (`layout_annotated_paragraph(para_text, sentences, vocab) -> list of segments`) used by pack-export tests. JS in `index.html` and `reader.html` may duplicate the walk; tests lock the Python helper so offsets stay honest.

---

### Task 1: Display paragraphs + sentence split

Match Passage: `get_chunk` already runs `normalize_reading_text`. Then paragraphs = split on `\n\s*\n`, collapse internal whitespace. Sentence-split each paragraph (never across paragraph boundaries).

**Files:**
- Create: `scripts/rag/intensive_reading/sentences.py`
- Create: `tests/test_intensive_reading_overlays.py`

**Step 1: Write the failing tests**

```python
"""Sentence split + overlay alignment for intensive reading."""
from __future__ import annotations

import os
import sys

_RAG = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "scripts", "rag"))
if _RAG not in sys.path:
    sys.path.insert(0, _RAG)

from intensive_reading.sentences import display_paragraphs, split_sentences  # noqa: E402


def test_display_paragraphs_match_passage_rules():
    raw = "First para line\nstill first.\n\nSecond para."
    paras = display_paragraphs(raw)
    assert paras == ["First para line still first.", "Second para."]


def test_split_sentences_basic():
    text = 'Hello there. "Next one?" Yes!'
    sents = split_sentences(text)
    assert [s["text"] for s in sents] == ["Hello there.", '"Next one?"', "Yes!"]
    assert sents[0]["start"] == 0
    assert text[sents[1]["start"]:sents[1]["end"]] == '"Next one?"'


def test_split_sentences_keeps_mr_abbreviation():
    text = "Mr. Smith left. Mrs. Jones stayed."
    sents = split_sentences(text)
    assert [s["text"] for s in sents] == ["Mr. Smith left.", "Mrs. Jones stayed."]


def test_empty_and_no_terminator():
    assert split_sentences("") == []
    sents = split_sentences("No end")
    assert len(sents) == 1 and sents[0]["text"] == "No end"
```

**Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_intensive_reading_overlays.py -v`
Expected: FAIL import / function not defined

**Step 3: Write minimal implementation**

In `sentences.py`:

- `display_paragraphs(text)` — `\r\n` → `\n`, trim, split `\n\s*\n`, each para `re.sub(r'\s+', ' ', p.replace('\n',' ')).strip()`, drop empties.
- `split_sentences(text)` — protect abbreviations (`Mr.`, `Mrs.`, `Ms.`, `Dr.`, `Prof.`, `St.`, `vs.`, `etc.`, `e.g.`, `i.e.`, `U.S.`) by swapping to a placeholder, split on `(?<=[.!?])["'”’)]*\s+`, restore, record `start`/`end` in the **unprotected** original via `str.find` advancing `pos`. If nothing matches, one sentence covering the whole string.
- Each sentence dict: `{"text", "start", "end"}` (end exclusive).

**Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_intensive_reading_overlays.py -v`
Expected: PASS

---

### Task 2: Overlay schema, vocab locate, save/load

**Files:**
- Create: `scripts/rag/intensive_reading/overlay_store.py`
- Modify: `tests/test_intensive_reading_overlays.py`

**Step 1: Write the failing tests** (append)

```python
from intensive_reading.overlay_store import (  # noqa: E402
    align_vocab,
    build_overlay_doc,
    clear_book_overlays,
    load_overlay,
    save_overlay,
)


def test_align_vocab_first_unused_span():
    para = "She drew a red herring across the trail, a red herring indeed."
    items = align_vocab(para, [
        {"phrase": "red herring", "zh": "转移注意力的话题", "example": ""},
        {"phrase": "missing", "zh": "无", "example": ""},
    ])
    assert len(items) == 1
    assert para[items[0]["start"]:items[0]["end"]] == "red herring"
    assert items[0]["start"] == para.find("red herring")


def test_align_vocab_normalizes_curly_quotes():
    para = "He said \u201cit's fine.\u201d"
    items = align_vocab(para, [{"phrase": 'He said "it\'s fine."', "zh": "他说没事。", "example": ""}])
    assert len(items) == 1
    assert para[items[0]["start"]:items[0]["end"]] == "He said \u201cit's fine.\u201d"


def test_overlay_roundtrip(tmp_path):
    doc = build_overlay_doc(
        book_id="book-aaa11111",
        chunk_index=0,
        paragraphs=[{"text": "Hello there. Bye.", "sentences": [
            {"text": "Hello there.", "start": 0, "end": 12, "zh": "你好。"},
            {"text": "Bye.", "start": 13, "end": 17, "zh": "再见。"},
        ], "vocab": []}],
        status="done",
    )
    save_overlay(str(tmp_path), "book-aaa11111", 0, doc)
    loaded = load_overlay(str(tmp_path), "book-aaa11111", 0)
    assert loaded["status"] == "done"
    assert loaded["paragraphs"][0]["sentences"][0]["zh"] == "你好。"
    assert clear_book_overlays(str(tmp_path), "book-aaa11111") == 1
    assert load_overlay(str(tmp_path), "book-aaa11111", 0) is None
```

Use a valid `book-id` that passes `is_valid_book_id` (existing pattern: slug + 8 hex, see ingest). If tmp_path is the books root, create `book-aaa11111/` before save — `overlay_store` should `resolve_book_dir` and mkdir `overlays/`.

For the unit test, either mkdir the book dir in tmp_path or have `save_overlay` accept a book dir. Prefer: `save_overlay(books_dir, book_id, chunk_index, doc)` mirroring `analysis_cache`, and the test does `(tmp_path / "book-aaa11111").mkdir()` plus a stub `meta.json` **only if** `resolve_book_id` requires it. Check `resolve_book_dir` — it typically only validates id and joins path.

**Step 2: Run to see FAIL**

**Step 3: Implement**

`overlay_store.py`:

- Path: `{book_dir}/overlays/{chunk_index}.json`
- `align_vocab(para, items)` — case-sensitive first match of `phrase.strip()` not overlapping previous hits; skip empty/not found.
- `build_overlay_doc(...)` — `{book_id, chunk_index, status, error, learner_level, updated_at, paragraphs}`.
- `load_overlay` returns `None` if missing/corrupt.
- `clear_book_overlays` deletes `overlays/*.json`.
- Atomic write like `analysis_cache.save_chunk_analysis` (tmp + replace).
- Never persist `status=running`.

**Step 4: PASS**

---

### Task 3: Overlay prompts + JSON parse (no live Ollama)

**Files:**
- Modify: `scripts/rag/intensive_reading/prompts.py`
- Modify: `scripts/rag/intensive_reading/overlay_store.py` (or new `overlay_gen.py` parse helper)
- Modify: `tests/test_intensive_reading_overlays.py`

**Step 1: Failing tests**

```python
from intensive_reading.prompts import (  # noqa: E402
    overlay_sentences_system_prompt,
    overlay_sentences_user_message,
    overlay_vocab_system_prompt,
    overlay_vocab_user_message,
)
from intensive_reading.overlay_gen import parse_sentences_json, parse_vocab_json  # noqa: E402


def test_overlay_sentences_user_message_numbers():
    msg = overlay_sentences_user_message(title="Ch 1", sentences=["Hello there.", "Bye."])
    assert "1. Hello there." in msg
    assert "2. Bye." in msg


def test_parse_sentences_json_strips_fence_and_maps_by_index():
    raw = """```json
    {"sentences": [{"i": 2, "zh": "第二"}, {"i": 1, "zh": "第一"}]}
    ```"""
    assert parse_sentences_json(raw, sentence_count=2) == ["第一", "第二"]


def test_parse_vocab_json():
    raw = '{"vocab": [{"phrase": "Hello there", "zh": "你好啊", "example": "Hello there, Sam."}]}'
    items = parse_vocab_json(raw)
    assert items[0]["phrase"] == "Hello there"
```

LLM `i` is **1-based**. `parse_sentences_json` returns a `zh` list of length `sentence_count` (missing → `""`). Accept 0-based if some `i==0`.

**Step 2: FAIL**

**Step 3: Implement**

Two system prompts (Chinese coach, JSON only):

- Sentences: `{"sentences": [{"i": 1, "zh": "..."}]}` — meaning/sense, simple sentences still get a short gloss.
- Vocab: `{"vocab": [{"phrase": "exact substring", "zh": "...", "example": "..."}]}` — reuse `_LEVEL_SKIP_VOCAB`; phrases must appear in the passage.

`parse_*`: strip fences, slice first `{` … last `}`.

**Step 4: PASS**

---

### Task 4: `annotate_chunk` with injectable LLM

**Files:**
- Create: `scripts/rag/intensive_reading/overlay_gen.py`
- Modify: `tests/test_intensive_reading_overlays.py`

**Step 1: Failing tests**

```python
from intensive_reading.overlay_gen import annotate_chunk_text  # noqa: E402


def test_annotate_chunk_text_uses_splitter_and_llm(monkeypatch):
    text = "Hello there.\n\nBye."

    calls = []

    def fake_llm(system, user):
        calls.append(user)
        if "exact substring" in system or "vocab" in system.lower() or "好词" in system:
            return json.dumps({"vocab": [{"phrase": "Hello there", "zh": "你好", "example": ""}]})
        return json.dumps({"sentences": [{"i": 1, "zh": "打招呼。"}, {"i": 2, "zh": "再见。"}]})

    doc = annotate_chunk_text(
        book_id="book-aaa11111",
        chunk_index=0,
        text=text,
        title="Ch 1",
        learner_level="university",
        llm_complete=fake_llm,
    )
    assert doc["status"] == "done"
    assert len(calls) == 2
    paras = doc["paragraphs"]
    assert paras[0]["sentences"][0]["zh"] == "打招呼。"
    assert paras[0]["vocab"][0]["phrase"] == "Hello there"
    assert paras[1]["sentences"][0]["zh"] == "再见。"


def test_annotate_chunk_text_bad_json_is_error():
    doc = annotate_chunk_text(
        book_id="book-aaa11111",
        chunk_index=1,
        text="Hello.",
        title="x",
        learner_level="university",
        llm_complete=lambda s, u: "not json",
    )
    assert doc["status"] == "error"
    assert doc["error"]
```

**Step 2: FAIL**

**Step 3: Implement `annotate_chunk_text`**

1. `paras = display_paragraphs(text)`
2. Flatten sentences with `(para_index, local_sent)` and global 1-based numbers for the prompt.
3. Call `llm_complete` **twice**: (a) numbered sentences → zh list; if `len(sentences) > 30`, batch 25 and concatenate. (b) full display text → vocab list.
4. Attach `zh` by global order. `align_vocab` per paragraph (first para that contains the phrase wins).
5. On exception/parse fail: `status=error`, keep spans with empty zh.

Skip empty text: `status=done`, `paragraphs=[]`.

**Step 4: PASS**

---

### Task 5: Ollama complete + skip-done book job (pure Python)

**Files:**
- Modify: `scripts/rag/intensive_reading/overlay_gen.py`
- Modify: `tests/test_intensive_reading_overlays.py`

**Step 1: Failing tests**

```python
from intensive_reading.overlay_gen import annotate_book, should_skip_chunk  # noqa: E402


def test_should_skip_done_overlay(tmp_path):
    book_id = "book-aaa11111"
    (tmp_path / book_id).mkdir()
    done = build_overlay_doc(book_id, 0, paragraphs=[], status="done", learner_level="university")
    save_overlay(str(tmp_path), book_id, 0, done)
    assert should_skip_chunk(str(tmp_path), book_id, 0, learner_level="university") is True
    assert should_skip_chunk(str(tmp_path), book_id, 0, learner_level="high_school") is False
    err = build_overlay_doc(book_id, 1, paragraphs=[], status="error", error="boom")
    save_overlay(str(tmp_path), book_id, 1, err)
    assert should_skip_chunk(str(tmp_path), book_id, 1, learner_level="university") is False


def test_annotate_book_skips_toc_and_done(tmp_path, monkeypatch):
    book_id = "book-bbb22222"
    bdir = tmp_path / book_id
    bdir.mkdir()
    chunks = [
        {"chunk_index": 0, "text": "Contents .... 1", "is_toc": True, "title": "Contents"},
        {"chunk_index": 1, "text": "Hello there.", "is_toc": False, "title": "Ch 1"},
        {"chunk_index": 2, "text": "Bye.", "is_toc": False, "title": "Ch 2"},
    ]
    (bdir / "chunks.json").write_text(json.dumps(chunks), encoding="utf-8")
    (bdir / "meta.json").write_text(json.dumps({
        "book_id": book_id, "book_type": "novel", "title": "T", "status": "ready",
        "chunk_count": 3,
    }), encoding="utf-8")
    calls = []

    def fake_llm(system, user):
        calls.append(user)
        return json.dumps({"sentences": [{"i": 1, "zh": "x"}], "vocab": []})

    save_overlay(str(tmp_path), book_id, 1, build_overlay_doc(
        book_id, 1, paragraphs=[], status="done"))
    summary = annotate_book(
        str(tmp_path), book_id, learner_level="university", llm_complete=fake_llm,
        on_progress=None,
    )
    assert summary["done"] >= 1
    assert len(calls) == 2  # chunk 2: sentences + vocab; chunk 1 skipped
    assert any("Bye." in c for c in calls)
```

If `is_toc_text` would flag "Contents .... 1", keep `is_toc: True` on the fixture explicitly. `annotate_book` must skip `is_toc` chunks without calling LLM.

**Step 2: FAIL**

**Step 3: Implement**

- `ollama_complete(system, user)` in `overlay_gen.py` (avoid circular import with routes). Host/model = same lookup as `_ollama_settings()`. POST `{model, messages, stream: False, think: False, format: "json", options: {num_predict: 4096, temperature: 0.3}}`, timeout=180.
- `should_skip_chunk(..., learner_level)` true only for `status==done` and matching level.
- `annotate_book` skips `is_toc`; uses `get_chunk` normalized text; respects a `cancel_flag` callable (Task 6).
- No live Ollama in tests.
- Return `{done, failed, total_readable, failed_indexes}`.
- Do **not** call live Ollama in tests.

**Step 4: PASS**

---

### Task 6: Flask APIs + background job + rebuild clears overlays

**Files:**
- Modify: `scripts/rag/routes/intensive_reading.py`
- Modify: `scripts/rag/intensive_reading/ingest.py` (`rebuild_magazine_from_original` also `clear_book_overlays`; `list_books` / meta include overlay summary)
- Create: `tests/test_intensive_reading_overlay_api.py`

**Step 1: Failing tests** — **pure functions**, not Flask `test_client` (IR suite has almost no WSGI fixtures).

```python
def test_validate_overlay_books_rejects_magazine():
    meta = {"book_id": "mag-aaa", "book_type": "magazine", "status": "ready"}
    err = validate_overlay_run_book(meta)
    assert err  # magazine not allowed


def test_stale_running_meta_becomes_idle():
    meta = {"overlay": {"state": "running", "done": 3, "total": 10}}
    assert normalize_overlay_meta_on_load(meta)["overlay"]["state"] == "idle"


def test_cancel_flag_stops_after_current(tmp_path):
    # annotate_book with cancel_flag that flips True after first readable chunk
    ...
```

Rebuild: monkeypatch `clear_book_overlays` to prove `rebuild_magazine_from_original` calls it (or run rebuild with a stub original if cheap).

**Endpoints:**

- `POST /api/intensive-reading/overlay/run` JSON `{ "book_ids": ["..."], "learner_level": "university" }`
  - Validate each id, `book_type==novel`, `status==ready`.
  - Start **one** background thread if idle; if already running, 409 `{error, running_book_id}`.
  - Process books sequentially.
- `POST /api/intensive-reading/overlay/cancel` — set cancel flag; after current chunk, `state=idle`.
- `GET /api/intensive-reading/overlay/status` → `{ running, book_id, done, total, failed, books: {id: meta.overlay} }`
- `GET /api/intensive-reading/books/<id>/chunks/<i>/overlay` → overlay JSON or 404 `{overlay: null}`
- `GET .../chunks/<i>` add `"overlay": <doc or null>` so Passage needs no extra call.
- `GET /api/intensive-reading/books/<id>/pack.zip` → zip (Task 10; stub 501 until then is OK, or skip until Task 10).

Persist on meta.json:

```python
"overlay": {
  "state": "idle|running|done|error",
  "done": 12,
  "total": 40,
  "failed": [3],
  "updated_at": "...",
}
```

`list_books` already returns meta — frontend can read `overlay`.

Background: `threading.Thread(daemon=True)` + `threading.Lock`. On process restart, `running` in meta should be treated as `idle` (stale).

**Step 3: Implement**, **Step 4: PASS** the new API tests.

Rebuild: next to `clear_book_analyses`, call `clear_book_overlays` and reset `overlay` meta to idle zeros.

---

### Task 7: Passage tappable spans + popover

**Files:**
- Modify: `scripts/rag/templates/index.html` — CSS near `#irPassage`; JS `irRenderPassage`, `irLoadChunk`
- Modify: `tests/test_intensive_reading_passage_ui.py` (existing HTML contract tests)

**Step 1: Failing tests**

Assert the HTML/JS source contains:

- class `ir-sent` and `ir-vocab`
- `irRenderPassage` accepts overlay
- click handler prefers `.ir-vocab`
- gloss popover only if `getSelection()` is collapsed (string `collapsed` or `rangeCount` check present next to overlay click)

Do **not** require a browser. Follow `test_intensive_reading_passage_ui.py` style (read `index.html` as text).

**Step 2: FAIL** (strings missing)

**Step 3: Implement**

CSS (warm dark):

```css
#irPassage .ir-sent[data-zh]{background:rgba(212,184,120,0.14);border-radius:2px;cursor:pointer}
#irPassage .ir-vocab{border-bottom:2px solid #c4a35a;cursor:pointer}
#irPassage .ir-sent.is-open{background:rgba(212,184,120,0.28)}
```

`irRenderPassage(raw, opts)`:

- Keep paragraph nodes as now.
- If `opts.overlay` has `paragraphs`, for each para index wrap inner HTML:
  - Walk sentences by `start/end` on the **display para string** (must equal `display_paragraphs` output).
  - Nested vocab spans only if `[start,end)` fully inside the sentence.
  - `textContent` via `createTextNode` / `createElement('span')` — never unsanitized HTML from zh.
  - `data-zh` on `.ir-sent`, `data-zh` + `data-phrase` + `data-example` on `.ir-vocab`.
- If overlay missing or para count mismatch, fall back to current `node.textContent = p`.

Click on `#irPassage`:

- If `window.getSelection()` is **not** collapsed → do nothing (existing drag-select Explain path).
- Else if target closest `.ir-vocab` → show card (phrase, zh, example).
- Else closest `.ir-sent[data-zh]` → show zh.
- Esc / outside click / second tap on same span closes.
- Never `preventDefault` on `mousedown` in a way that blocks text selection.

`irLoadChunk`: pass `d.overlay` into `irRenderPassage`.

**Step 4: PASS** passage UI tests + existing selection-explain tests still pass:

Run: `python -m pytest tests/test_intensive_reading_passage_ui.py tests/test_intensive_reading_overlays.py -v`

---

### Task 8: Book list checkboxes, Pre-annotate, progress, Download pack button

**Files:**
- Modify: `scripts/rag/templates/index.html` — `irRefreshBooks` and a small toolbar above `#irBookList`

**Step 1: Failing HTML-contract tests** in `tests/test_intensive_reading_passage_ui.py` or a new `tests/test_intensive_reading_overlay_ui.py`:

- `Pre-annotate` button id `irOverlayRunBtn`
- `Download pack` appears for novels (`irPackBtn` or per-row)
- checkbox class `ir-book-check` only when `book_type==='novel' && status==='ready'`

**Step 2: FAIL**

**Step 3: Implement**

- Toolbar: `[Pre-annotate selected]` + `[Cancel]` (Cancel calls overlay/cancel). Disabled when none checked / when not running.
- Each novel row: checkbox; meta line shows `overlay: 12/40` or `3 failed` from `b.overlay`.
- Click Pre-annotate → `POST /overlay/run` with checked ids + current `#irLearnerLevel` if present else `university`.
- Poll `GET /overlay/status` every 2s while `running`; refresh list; stop when idle.
- Per-row `Pack` button → `GET /books/<id>/pack.zip` download (Task 10). Hide for magazines.
- Do not Pre-annotate magazines (checkbox absent).

**Step 4: PASS** UI contract tests. Manual: restart Jarvis (HTML is read at import).

---

### Task 9: Fill empty Vocab tab from overlay

When overlay is `done` and vocab tab slot is empty, synthesize a markdown list from overlay vocab items (phrase + zh + example) and show it as `status=done` in the UI **without** overwriting a user-generated tab.

**Files:**
- Modify: `scripts/rag/templates/index.html` `irLoadCachedAnalysis`
- Optional: persist synthesized vocab into `analyses/` only if you need Continue — **YAGNI: display-only merge in JS**.

**Tests:** JS contract: function `irVocabMarkdownFromOverlay` exists and concatenates phrases.

---

### Task 10: Zip pack + inlined `reader.html`

**Files:**
- Create: `scripts/rag/intensive_reading/reader_template.html`
- Create: `scripts/rag/intensive_reading/pack_export.py`
- Modify: `scripts/rag/routes/intensive_reading.py` (`GET .../pack.zip`)
- Modify: `tests/test_intensive_reading_overlays.py`

**Step 1: Failing tests**

```python
from intensive_reading.pack_export import build_pack_bytes, build_reader_html  # noqa: E402


def test_reader_html_inlines_json_and_has_no_fetch():
    pack = {"title": "T", "book_id": "book-aaa11111", "toc": [], "chunks": [], "overlays": {}}
    html = build_reader_html(pack)
    assert "book-aaa11111" in html
    assert "id=\"irPackData\"" in html
    assert "fetch(" not in html.lower()


def test_layout_annotated_paragraph_nests_vocab():
    from intensive_reading.overlay_store import layout_annotated_paragraph
    segs = layout_annotated_paragraph(
        "Hello there.",
        sentences=[{"text": "Hello there.", "start": 0, "end": 12, "zh": "你好。"}],
        vocab=[{"phrase": "Hello there", "start": 0, "end": 11, "zh": "你好"}],
    )
    assert any(s.get("kind") == "vocab" for s in segs)


def test_zip_contains_reader_and_pack_json():
    raw = build_pack_bytes({
        "title": "T", "book_id": "book-aaa11111",
        "toc": [], "chunks": [{"chunk_index": 0, "text": "Hi.", "title": "Ch", "is_toc": False}],
        "overlays": {"0": {"status": "done", "paragraphs": []}},
    })
    import io, zipfile
    z = zipfile.ZipFile(io.BytesIO(raw))
    names = z.namelist()
    assert "reader.html" in names
    assert "book.pack.json" in names
    data = json.loads(z.read("book.pack.json"))
    assert data["book_id"] == "book-aaa11111"
```

**Step 2: FAIL**

**Step 3: Implement**

`build_pack_dict(books_dir, book_id)` loads meta, toc, chunks, every overlay file keyed by chunk index string.

`build_reader_html(pack)`: read template, replace `%%BOOK_PACK_JSON%%` with `json.dumps(pack)` inside `<script type="application/json" id="irPackData">`. Escape `</script>` in JSON as `\u003c/script>`.

Template (keep small): dark background `#16141a`, text `#d6d2c8`, max-width 38em, Chapters select from toc, Prev/Next, render current chunk with same span rules as Task 7 (inline a short JS copy — duplication OK for a standalone file; do not fetch Jarvis APIs). Tap → `alert` is too crude; use a bottom `#pop` div.

`GET pack.zip`: `send_file` BytesIO, mimetype `application/zip`, filename `{safe_title}.zip`. 400 if magazine or book missing.

**Step 4: PASS**

---

### Task 11: Wire rebuild + skip_toc overlay fetch + smoke

**Files:**
- Modify: `ingest.py` rebuild (if not done in Task 6)
- Modify: `api_get_chunk` to attach overlay
- Run full IR overlay suite

**Step 1:** `python -m pytest tests/test_intensive_reading_overlays.py tests/test_intensive_reading_overlay_api.py tests/test_intensive_reading_passage_ui.py tests/test_intensive_reading_overlay_ui.py -v`

Expected: all PASS

**Step 2:** Confirm `rebuild_magazine_from_original` clears overlays (test from Task 6).

**Do not** commit unless the user asks. Do not touch stock/daily-fetch files. Do not add `docs/books/**` content.

---

## Manual verification (after code is green)

1. Restart Jarvis (template is loaded at import).
2. Intensive Reading → pick one **small** novel (or a short EPUB) → Pre-annotate. Watch overlay counts climb; Ollama will be slow.
3. Open a finished chunk: sentences have wash, vocab has underline; click each; drag-select Explain still works.
4. Download pack → copy `reader.html` to phone → Chrome open; confirm taps work **offline**.
5. Rebuild that book → overlays gone; Passage unmarked until Pre-annotate again.

---

## Out of scope

- Native Android app
- Magazines, other analysis tabs, speaking
- DeepSeek
- Changing chunking / PDF paragraph reconstruction
- RAG
