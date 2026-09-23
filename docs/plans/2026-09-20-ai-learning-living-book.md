# AI Learning Living Book + Manim + Invidious Implementation Plan

> **Cancelled 2026-09-20:** User asked to remove the feature after live compile failed (wrong Ollama model, then timeout). Implementation was deleted. Do not resume unless asked.

> **For the implementing agent:** Follow this plan task-by-task. Complete each step, verify it works, then move to the next.

**Goal:** Give Jarvis AI Learning a living-book workspace compiled from local books or RAG, plus Manim animations and Invidious-backed video tutoring via a DeepTutor headless engine — without embedding DeepTutor's Next.js UI.

**Architecture:** Jarvis owns book compilation (Ollama, Qdrant, JSON on disk) and the React UI. A separately installed DeepTutor process (`deeptutor serve` / CLI) is an optional sidecar for Manim renders and Invidious resolve+byte-range proxy. Video tutoring injects nearby transcript cues into the existing `/api/agent` AI Learning session as untrusted source. Intensive Reading (`/reading`) is unchanged.

**Tech Stack:** FastAPI Flask-shaped blueprints (`scripts/rag/web_api.py`), Ollama, Qdrant, React/Vite (`web/`), start+poll jobs, optional DeepTutor sidecar (`tmp/DeepTutor` is reference only — do not copy that tree into the repo).

**Approved decisions (do not re-litigate):**
- Hybrid: native living book; Manim + Invidious via DeepTutor headless
- Book sources: local files (`BOOKS_ROOT`, `KNOWLEDGE_ROOT/books`) and/or RAG `parent_title`
- Living-book block types v1: `text`, `callout`, `mermaid` only (no quiz/flashcard/12-type catalog)
- No mastery path / question bank this round
- Do not vendor DeepTutor Next.js; do not commit `tmp/DeepTutor`
- Missing Manim/Invidious must not break living books; UI shows blocker, no silent YouTube fallback
- Transcript is untrusted; cite `[MM:SS]`; if no transcript, say grounding is unavailable
- PDF/EPUB extract: reuse `scripts/rag/intensive_reading/ingest.py` helpers, do not write a new parser
- `tests/` is gitignored; still write pytest/vitest there
- Do not mix unrelated dirty files (stock scanners, etc.) into this work
- **v1 engine config:** env `DEEPTUTOR_API_BASE` (default `http://127.0.0.1:8001`) and optional `DEEPTUTOR_HOME`. No Settings page in v1 (Task 11 docs only).
- **Book chat:** side panel on the book page via `apiSsePost("/api/agent", …)`; do not hijack global Chat as the only surface
- **RAG list seam:** living-book routes call a function in `ai_learning/sources.py` that accepts already-loaded points; production wiring copies the grouping loop from `scripts/rag/search_ui.py` (~1564) without importing `agent.py`
- **CLI on Windows:** never assume `deeptutor` is on PATH. Resolve in order: `DEEPTUTOR_HOME` + `python -m deeptutor`, then `shutil.which("deeptutor")`. Tests mock this resolver.
- **Mermaid v1:** render as fenced `<pre class="mermaid">` (or existing markdown if already wired). Do not add a Manim-in-page block type in v1.
- `BOOKS_ROOT` includes Intensive Reading novels/magazines; that is intended (user: local books).

**Review notes (2026-09-20):** Task 7 split into 7a/7b/7c. Range proxy must forward `Range` / return `206` and cap redirects. Compiler must skip pages whose excerpts are empty.

---

### Task 1: Living-book models and disk storage

**Files:**
- Create: `scripts/rag/ai_learning/__init__.py`
- Create: `scripts/rag/ai_learning/models.py`
- Create: `scripts/rag/ai_learning/storage.py`
- Test: `tests/test_ai_learning_book_storage.py`

**Step 1: Write the failing test**

```python
"""Living-book JSON storage under REPORTS_ROOT/ai_learning/books."""
from __future__ import annotations

import os
import sys

_RAG = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "scripts", "rag"))
_SCRIPTS = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "scripts"))
for _p in (_RAG, _SCRIPTS):
    if _p not in sys.path:
        sys.path.insert(0, _p)


def test_create_and_load_book(tmp_path):
    from ai_learning.storage import BookStorage
    from ai_learning.models import Book, Chapter, Page, Block, BlockType, BookStatus

    store = BookStorage(root=str(tmp_path / "ai_learning" / "books"))
    book = Book(
        id="b1",
        title="RAG",
        status=BookStatus.DRAFT,
        intent="Teach RAG from my notes",
        sources=[{"kind": "rag", "id": "04-rag.md"}],
        chapters=[Chapter(id="c1", title="Intro", order=0, page_ids=["p1"])],
    )
    store.save_book(book)
    store.save_page(
        "b1",
        Page(
            id="p1",
            chapter_id="c1",
            title="What is RAG",
            blocks=[Block(id="k1", type=BlockType.TEXT, status="ready", payload={"markdown": "hi"})],
        ),
    )
    loaded = store.load_book("b1")
    assert loaded.title == "RAG"
    page = store.load_page("b1", "p1")
    assert page.blocks[0].payload["markdown"] == "hi"
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_ai_learning_book_storage.py::test_create_and_load_book -v`
Expected: FAIL with `ModuleNotFoundError: ai_learning`

**Step 3: Write minimal implementation**

`models.py`: dataclasses/Pydantic-free typed dicts or simple classes: `BookStatus` (`draft|spine|compiling|ready|partial|error`), `BlockType` (`text|callout|mermaid`), `Block`, `Page`, `Chapter`, `Book`. Keep JSON-serializable (`asdict`).

`storage.py`: `BookStorage(root=None)` — default `os.path.join(REPORTS_ROOT, "ai_learning", "books")`. Tests **pass `root=`** so they do not depend on `config.REPORTS_ROOT` computed at import. `book.json`; `pages/{page_id}.json`. `list_books()`, `delete_book()` with path-containment (resolved path must stay under `root`).

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_ai_learning_book_storage.py -v`
Expected: PASS

---

### Task 2: Resolve local + RAG sources (no LLM yet)

**Files:**
- Create: `scripts/rag/ai_learning/sources.py`
- Test: `tests/test_ai_learning_sources.py`
- Read: `scripts/config.py` (`BOOKS_ROOT`, `KNOWLEDGE_ROOT`), `scripts/rag/search_ui.py` document grouping (~1564)

**Step 1: Write the failing test**

```python
def test_list_local_sources(tmp_path):
    books = tmp_path / "docs" / "books"
    books.mkdir(parents=True)
    (books / "nltk.pdf").write_bytes(b"%PDF")
    from ai_learning.sources import list_local_book_files
    items = list_local_book_files(books_roots=[str(books)])
    assert any(i["name"] == "nltk.pdf" for i in items)


def test_list_rag_parents_from_points():
    from ai_learning.sources import rag_parents_from_points
    points = [
        {"payload": {"parent_title": "04-rag.md", "source": "notes"}},
        {"payload": {"parent_title": "04-rag.md"}},
        {"payload": {"parent_title": "Hands-On LLM"}},
    ]
    parents = rag_parents_from_points(points)
    assert [p["id"] for p in parents] == ["04-rag.md", "Hands-On LLM"]
```

**Step 2: Run test — expect FAIL (`list_local_book_files` missing)**

Run: `pytest tests/test_ai_learning_sources.py -v`

**Step 3: Implement**

- Local: `list_local_book_files(books_roots=None)` scans the given roots (default `BOOKS_ROOT` and `KNOWLEDGE_ROOT/books`) for `.pdf/.epub/.md`; skip `analyses` dirs; return `{kind, id, path, name}`. Tests pass `books_roots=` so they never touch import-time `config.BOOKS_ROOT`.
- RAG: `rag_parents_from_points` groups by `parent_title` or `filename`. Production `GET /api/ai-learning/sources` loads points the same way `search_ui.py` lists documents (~1564). Tests pass a fake list — **do not import `agent.py`**.
- **Excerpts:** `fetch_excerpts(sources, points, max_chars=8000) -> list[str]`. For `kind=rag`, concatenate chunk texts whose `parent_title`/`filename` matches `id`. For `kind=local`, if the file is already indexed use the same; else return `[]` and the compile job will mark pages `error` / `"no source excerpts"` (do not parse PDF in this function — indexing first is required, reuse IR ingest only if a later job explicitly reindexes). Cap total chars.
- Path containment: reject `..` in requested local ids.

Add test `test_fetch_excerpts_from_matching_parent`.

**Step 4: pytest PASS**

---

### Task 3: Spine proposal (LLM JSON) + confirm

**Files:**
- Create: `scripts/rag/ai_learning/spine.py`
- Test: `tests/test_ai_learning_spine.py`

**Step 1: Failing test — parse/validate spine without calling Ollama**

```python
def test_parse_spine_json():
    from ai_learning.spine import parse_spine
    raw = '{"title":"RAG","chapters":[{"title":"Intro","pages":[{"title":"What is RAG"}]}]}'
    spine = parse_spine(raw)
    assert spine["title"] == "RAG"
    assert spine["chapters"][0]["pages"][0]["title"] == "What is RAG"


def test_parse_spine_rejects_garbage():
    from ai_learning.spine import parse_spine
    import pytest
    with pytest.raises(ValueError):
        parse_spine("not json")
```

**Step 2: pytest FAIL then implement `parse_spine`** (strip fences, require title + chapters[].pages[].title, max 20 chapters / 10 pages each).

**Step 3: Failing test for prompt builder**

```python
def test_spine_prompt_includes_sources_and_intent():
    from ai_learning.spine import build_spine_prompt
    p = build_spine_prompt("Teach RAG", excerpts=["chunk A about retrieval"])
    assert "Teach RAG" in p
    assert "chunk A" in p
    assert "JSON" in p
```

**Step 4: Implement `build_spine_prompt`.** Do **not** call Ollama in this task. A route in Task 5 will call Ollama with this prompt (`OLLAMA_MODEL` / existing helper — search `scripts/rag` for the small JSON completion used by `_classify_learning_channel_intent`, reuse that pattern).

---

### Task 4: Page compiler (text / callout / mermaid)

**Files:**
- Create: `scripts/rag/ai_learning/compiler.py`
- Test: `tests/test_ai_learning_compiler.py`

**Step 1: Failing test — compile one page from mocked LLM JSON**

```python
def test_compile_page_from_llm_blocks():
    from ai_learning.compiler import blocks_from_llm_json
    raw = '{"blocks":[{"type":"text","markdown":"RAG retrieves then generates."},{"type":"callout","markdown":"Cite sources."},{"type":"mermaid","code":"graph LR; A-->B"}]}'
    blocks = blocks_from_llm_json(raw)
    assert [b.type.value for b in blocks] == ["text", "callout", "mermaid"]


def test_unknown_block_type_dropped():
    from ai_learning.compiler import blocks_from_llm_json
    blocks = blocks_from_llm_json('{"blocks":[{"type":"quiz","markdown":"nope"},{"type":"text","markdown":"ok"}]}')
    assert len(blocks) == 1
    assert blocks[0].type.value == "text"


def test_compile_page_empty_excerpts_errors():
    from ai_learning.compiler import compile_page
    page = compile_page(title="X", excerpts=[], llm_json=None)
    assert page.status == "error"
    assert "no source excerpts" in page.error
```

**Step 2:** Run `pytest tests/test_ai_learning_compiler.py -v` — FAIL (`compiler` missing)

**Step 3: Minimal implementation**

- `blocks_from_llm_json`: drop unknown types.
- `compile_page(title, excerpts, llm_json)`: if not excerpts, return page `status=error`, `error="no source excerpts"`, no blocks (never call LLM).
- `build_page_prompt(title, excerpts)` includes title, capped excerpts, allowed types only.

**Step 4:** pytest PASS

---

### Task 5: HTTP API + start/poll compile job

**Files:**
- Create: `scripts/rag/routes/ai_learning_books.py`
- Modify: `scripts/rag/agent.py` (~1617) register blueprint after `intensive_reading_bp`
- Test: `tests/test_ai_learning_book_routes.py` (mirror `tests/test_intensive_reading_analyze_routes.py`: register blueprint on a tiny Flask app, do **not** import full `agent.py`)

**Endpoints:**
- `GET /api/ai-learning/sources` → `{local: [...], rag: [...]}` (rag from injected/qdrant list helper)
- `POST /api/ai-learning/books` body `{intent, sources: [{kind, id}]}` → creates draft book, starts **propose** job, returns `{book_id, job_id}`
- `GET /api/ai-learning/books` list
- `GET /api/ai-learning/books/<id>`
- `POST /api/ai-learning/books/<id>/spine` body `{title, chapters}` confirm spine, allocate page ids, status `spine`
- `POST /api/ai-learning/books/<id>/compile` → `{job_id}` thread compiles remaining pages; persist after each page; status `ready` or `partial`
- `GET /api/ai-learning/books/<id>/pages/<page_id>`
- `GET /api/ai-learning/jobs/<job_id>` `{status, step, error}` statuses: `starting|running|done|error`

**Step 1: Failing route test** — `GET /api/ai-learning/sources` 200 with mocked local dir.

**Step 2: FAIL (`ai_learning_books` missing)**

**Step 3: Implement blueprint `ai_learning_books_bp`. Jobs dict in-module like `_daily_fetch_jobs`. Ollama calls go through a small `_complete_json(prompt)` that tests can monkeypatch.**

**Step 4: pytest the route file PASS.** Register in `agent.py`.

---

### Task 6: Inject current page into AI Learning chat

**Files:**
- Modify: `scripts/rag/agent.py` `api_agent` (learning branch) — accept optional `living_book_id`, `living_page_id`
- Test: `tests/test_ai_learning_page_context.py` testing a **helper** extracted to `scripts/rag/ai_learning/chat_context.py` so tests do not import `agent.py`

**Step 1:**

```python
def test_page_context_block_marks_untrusted_and_includes_text():
    from ai_learning.chat_context import page_prompt_block
    from ai_learning.models import Page, Block, BlockType
    page = Page(id="p1", chapter_id="c1", title="RAG", blocks=[
        Block(id="k1", type=BlockType.TEXT, status="ready", payload={"markdown": "retrieve then generate"})
    ])
    block = page_prompt_block(page)
    assert "untrusted" in block.lower() or "source material" in block.lower()
    assert "retrieve then generate" in block
    assert "RAG" in block
```

**Step 2–4:** Implement helper. In `api_agent`, if both ids present and session is AI Learning, prepend the block to the learning prompt. Ignore ids for other session types.

---

### Task 7a: Nav + empty Learning routes

**Files:**
- Create: `web/src/pages/LearningLayout.tsx`
- Create: `web/src/pages/LivingBookPage.tsx` (placeholder: "Select sources to compile a book.")
- Create: `web/src/pages/LearningVisualizePage.tsx` (placeholder + will show engine blocker later)
- Create: `web/src/pages/LearningVideoPage.tsx` (placeholder)
- Modify: `web/src/App.tsx` — `/learning` layout, default redirect to `books`
- Modify: `web/src/lib/nav.ts` + `web/src/lib/nav.test.ts` — group **Learning** after Reading: Books `/learning/books`, Visualize `/learning/visualize`, Video `/learning/video`. Update the test that expects only Chat/Reading/Settings as leaves.

**Step 1:** Extend `nav.test.ts` so it **fails** until Learning exists (order: Reading → Learning → Medavis).

**Step 2:** Run `cd web && npx vitest run src/lib/nav.test.ts` — FAIL

**Step 3:** Add nav + routes + placeholders.

**Step 4:** Vitest PASS. Browser: `/learning/books` renders placeholder.

---

### Task 7b: Client helper + create/spine/compile flow

**Files:**
- Create: `web/src/lib/aiLearningBooks.ts`
- Create: `web/src/lib/aiLearningBooks.test.ts`
- Modify: `web/src/pages/LivingBookPage.tsx`
- Modify: `web/src/features/news/ToolbarPanel.tsx` — extra control linking to `/learning/books` (chat session open stays)

**Behavior:** source checkboxes, intent, Create, poll propose, editable spine, Confirm, poll compile. Empty and error states. Use `pollJob` from `web/src/lib/jobs.ts`.

**Step 1:** Vitest for path helpers (`sourcesPath()`, `booksPath()`, job poll terminal statuses).

**Step 2–4:** Implement. No reader chrome yet.

---

### Task 7c: Reader + side-panel tutor

**Files:**
- Modify: `web/src/pages/LivingBookPage.tsx`
- Reuse: `web/src/lib/sse.ts` / `apiSsePost`

**Behavior:** after compile, left column renders blocks (`text`/`callout` as markdown; `mermaid` as `<pre class="mermaid">`). Right column: input → `POST /api/agent` with `session_id` AI Learning UUID, `living_book_id`, `living_page_id`. Do **not** navigate away to Chat as the primary path.

**Browser:** one RAG-backed book, one page visible, one streamed answer in the side panel.

---

### Task 8: DeepTutor engine client + readiness (no Manim yet)

**Files:**
- Create: `scripts/rag/ai_learning/deeptutor_engine.py`
- Test: `tests/test_deeptutor_engine.py`

**Config:** `os.environ.get("DEEPTUTOR_API_BASE", "http://127.0.0.1:8001")`. No Settings UI in this task.

**Step 1:**

```python
def test_readiness_offline(monkeypatch):
    from ai_learning.deeptutor_engine import readiness
    monkeypatch.setattr("ai_learning.deeptutor_engine._get", lambda *a, **k: (_ for _ in ()).throw(ConnectionError("down")))
    r = readiness()
    assert r["ok"] is False
    assert "sidecar" in r["blockers"][0].lower() or "unreachable" in str(r).lower()
```

Do **not** invent `manim`/`invidious` booleans from `/health`. DeepTutor health does not report addon status. `readiness()["ok"]` means HTTP sidecar is up. Manim/Invidious failures are job-time errors (Task 9/10).

**Step 2–4:** GET `{base}/health` or `/api/health` (check clone). `GET /api/ai-learning/engine` returns `{ok, base, blockers}`.

**Step 2–4:** `readiness()` GET `{base}/health` (or `/api/health` if that is what the clone serves — check `tmp/DeepTutor` when implementing). On failure return blockers. Do not start DeepTutor from Jarvis. `GET /api/ai-learning/engine` for the UI.

Also implement `resolve_deeptutor_cmd() -> list[str]` with tests:
1. If `DEEPTUTOR_HOME` set: `[sys.executable-or-home-python, "-m", "deeptutor"]` with cwd=home
2. Else `shutil.which("deeptutor")`
3. Else raise a typed "not installed" error

---

### Task 9: Manim job adapter

**Files:**
- Modify: `scripts/rag/ai_learning/deeptutor_engine.py` (`run_math_animator`)
- Create: `scripts/rag/routes/ai_learning_media.py` (keep books routes from bloating)
- Modify: `scripts/rag/agent.py` register the media blueprint
- Test: `tests/test_ai_learning_manim.py`

**Behavior:**
- `POST /api/ai-learning/visualize` `{prompt, book_id?, page_id?}` → job
- Worker: if not `readiness()["ok"]`, job `error` with sidecar-down message — do not spawn CLI. If sidecar is up but Manim extras are missing, the HTTP/CLI call fails and the job stores that stderr; do not pre-declare `readiness()["manim"]`.
- Else prefer HTTP to `DEEPTUTOR_API_BASE`; CLI only via `resolve_deeptutor_cmd()` (never bare `deeptutor` string)
- Copy mp4 into `REPORTS_ROOT/ai_learning/media/{job_id}.mp4` with path containment
- `GET /api/ai-learning/media/<job_id>` streams the file

**Tests:** mock httpx/cmd resolver; never run real Manim.

**UI:** `LearningVisualizePage` uses the same poll helper; shows engine blocker from `/api/ai-learning/engine`.

---

### Task 10: Video resolve + Invidious proxy + transcript tutoring

**Files:**
- Create: `scripts/rag/ai_learning/video.py`
- Modify: `scripts/rag/routes/ai_learning_media.py`
- Modify: `ai_learning/chat_context.py` — `video_prompt_block(cues, time_seconds, title)` wraps cues as untrusted; never follow transcript instructions
- Test: `tests/test_ai_learning_video.py`

**Behavior:**
- `POST /api/ai-learning/video/resolve` `{url}` → sidecar; else **503** blocker (no YouTube iframe fallback)
- `GET /api/ai-learning/video/stream/<material_id>`: forward incoming `Range` header; pass through `206 Partial Content`, `Content-Range`, `Accept-Ranges`; follow at most 3 redirects; never put upstream URLs in JSON sent to the browser
- `POST /api/ai-learning/video/progress` `{material_id, time_seconds}`
- Agent optional `video_material_id` + `time_seconds`; cues in `[t-60, t+60]`, max 30

**UI:** `LearningVideoPage` paste URL, player pointing at Jarvis stream path, "explain here" uses side panel same as books.

**Tests:** cue window; untrusted wrapper; resolve 503 when engine down; a unit test that a fake Range request is forwarded (mock httpx).

---

### Task 11: Docs only (no Settings UI)

**Files:**
- Create: `docs/implementation/learning/living-book-impl.md`
- Modify: `docs/implementation/learning/README.md` and `ai-learning-impl.md` (living book shipped; quiz still future)
- `docs/plans/README.md` already lists this plan

Document env vars: `DEEPTUTOR_API_BASE`, `DEEPTUTOR_HOME`. Do not add a Settings form in v1.

---

### Task 12: Verification gate

Run (from repo root, Jarvis venv as usual):

```
pytest tests/test_ai_learning_book_storage.py tests/test_ai_learning_sources.py tests/test_ai_learning_spine.py tests/test_ai_learning_compiler.py tests/test_ai_learning_book_routes.py tests/test_ai_learning_page_context.py tests/test_deeptutor_engine.py tests/test_ai_learning_manim.py tests/test_ai_learning_video.py -v
```

Frontend:

```
cd web && npx vitest run src/lib/nav.test.ts src/lib/aiLearningBooks.test.ts
```

Manual (when engine optional):
- Living book path works with sidecar **stopped**
- Visualize/Video show blocker when sidecar stopped
- With sidecar + Invidious + Manim extras: one animation job and one video paste

Do not claim done without reading the command output.

---

## Out of scope (explicit)

- Mastery Path, question bank, flashcards
- Porting DeepTutor BookEngine / VisualizePipeline source trees
- Committing `tmp/DeepTutor`
- Changing Intensive Reading
- Silent YouTube fallback
- Installing Invidious/Manim as part of `jarvis-start.bat`
