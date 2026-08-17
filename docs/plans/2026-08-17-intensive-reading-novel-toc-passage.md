# Intensive Reading Novel TOC + Passage Typography Implementation Plan

> **For the implementing agent:** Follow this plan task-by-task. Complete each step, verify it works, then move to the next.

**Goal:** Split novels by table-of-contents chapter boundaries (then ~1200-word sub-chunks) and restyle the left Passage pane so long English reading is less tiring.

**Architecture:** Reuse magazine outline page-range splitting (`chunk_magazine_from_outline`) after filtering PDF bookmarks down to chapter-level entries. Fall back to a printed Contents-page parser, then to the current 1–2 page splitter. Always run `_split_oversized_chunks(max_words=1200)`. Persist `toc.json` for novels (one entry per chapter, first sub-chunk). Passage CSS becomes a dedicated reading theme; keep `.ir-para` so selection-explain still works. Magazine article chunking stays unchanged.

**Tech Stack:** Python 3, pypdf outline (already in `extract.py`), Flask intensive-reading routes, `scripts/rag/templates/index.html` CSS/JS, pytest (`tests/` is gitignored but still run locally).

**Approved decisions (do not re-litigate):**
- Novel split = Approach A: TOC defines chapters, then split oversized chapters. Rejected: one-chunk-per-chapter; keep 1–2 page chunks and only relabel.
- Passage = full package: Georgia serif, 18px, `max-width: 38em` centered, left align, warm dark `#d6d2c8` on `#16141a`, novel indent vs magazine paragraph spacing. No A± / sepia/paper themes in v1.
- Scope: left Passage only. Do not restyle `#irAnalysis`. Do not change magazine `build_chunks` magazine branch.
- Chapters ▾ jumps to the first sub-chunk of that chapter.
- Existing analyses keyed by chunk index will not match after rebuild — rebuild must `clear_book_analyses` (same as magazine rebuild).
- Books without a usable TOC keep `chunk_novel_pages(pages_per_chunk=2)`.

**Plan amendments (from critical review — do not re-litigate):**

1. **Never call `_map_printed_page_to_index` for novels.** That helper is New Yorker masthead-specific (`THE NEW YORKER` + `printed + 1`). Novel printed-TOC mapping: (a) if a page starts with the chapter heading, use that PDF index; (b) else `printed - 1` clipped to `[0, len(pages))`. After mapping, starts must be strictly increasing and unique; if not, **discard the printed outline** and fall back to 1–2 page chunks.
2. **EPUB tiny-spine guard.** Many EPUBs are one tiny XHTML per few paragraphs. If `len(sections) >= 2` but median word count `< 400` and `len(sections) > 15`, do **not** treat each section as a chapter — use `chunk_by_words` (old behavior). Otherwise section title = chapter, then `_split_oversized_chunks`.
3. **Chapters ▾ only when TOC is real chapters.** Hide the dropdown when `toc` is empty **or** ≥80% of titles match `^Pages\s+\d`. Do not show “No chapters list yet” on old 1–2 page novels.
4. **Old novels are not updated by Re-index.** `reindex_book` only re-splits oversized chunks; it does not re-extract. v1: new uploads get chapter chunking; existing novels need `rebuild_magazine_from_original` (after Task 5 allows novels) or re-upload. No new toolbar button in this plan.
5. **Task 2 fixtures** must assert mapped `page` indices from heading-scan / `printed-1`, not from the magazine mapper.

---

### Task 1: Filter chapter-level outline + chunk novels from it

**Files:**
- Modify: `scripts/rag/intensive_reading/chunking.py`
- Create: `tests/test_intensive_reading_novel_toc.py`

**Step 1: Write the failing tests**

```python
"""Novel TOC / chapter-boundary chunking."""
from __future__ import annotations

import os
import sys

_RAG = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "scripts", "rag"))
if _RAG not in sys.path:
    sys.path.insert(0, _RAG)

from intensive_reading.chunking import (  # noqa: E402
    chunk_novel_from_outline,
    filter_novel_chapter_outline,
    outline_from_novel_contents,
)


def test_filter_keeps_top_level_chapters_not_nested_leaves():
    outline = [
        {"title": "Chapter 1 Dawn", "page": 4, "level": 0},
        {"title": "The cottage", "page": 4, "level": 1},
        {"title": "Chapter 2 Storm", "page": 20, "level": 0},
        {"title": "The cliff", "page": 28, "level": 1},
        {"title": "Chapter 3 Harbor", "page": 40, "level": 0},
    ]
    leaves = filter_novel_chapter_outline(outline)
    titles = [e["title"] for e in leaves]
    assert titles == ["Chapter 1 Dawn", "Chapter 2 Storm", "Chapter 3 Harbor"]


def test_filter_drops_front_matter_and_needs_two_chapters():
    assert filter_novel_chapter_outline(
        [{"title": "Cover", "page": 0, "level": 0}]
    ) == []
    assert filter_novel_chapter_outline(
        [
            {"title": "Copyright", "page": 1, "level": 0},
            {"title": "Contents", "page": 2, "level": 0},
            {"title": "Chapter 1", "page": 5, "level": 0},
        ]
    ) == []  # only one real chapter


def test_chunk_novel_from_outline_uses_chapter_page_ranges():
    pages = [f"page {i} " + ("word " * 20) for i in range(10)]
    outline = [
        {"title": "Chapter 1 Dawn", "page": 2, "level": 0},
        {"title": "Chapter 2 Storm", "page": 5, "level": 0},
    ]
    chunks = chunk_novel_from_outline(pages, outline)
    readable = [c for c in chunks if not c.get("is_toc")]
    assert any(c["title"] == "Chapter 1 Dawn" for c in readable)
    assert any(c["title"] == "Chapter 2 Storm" for c in readable)
    ch1 = next(c for c in readable if c["title"] == "Chapter 1 Dawn")
    assert "page 2" in ch1["text"]
    assert "page 4" in ch1["text"]
    assert "page 5" not in ch1["text"]
```

**Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_intensive_reading_novel_toc.py::test_filter_keeps_top_level_chapters_not_nested_leaves tests/test_intensive_reading_novel_toc.py::test_filter_drops_front_matter_and_needs_two_chapters tests/test_intensive_reading_novel_toc.py::test_chunk_novel_from_outline_uses_chapter_page_ranges -v`

Expected: FAIL with `ImportError` (functions not defined).

**Step 3: Write minimal implementation**

In `scripts/rag/intensive_reading/chunking.py`, after `_outline_leaves` / `chunk_magazine_from_outline`:

```python
_NON_CHAPTER_TITLE = re.compile(
    r"^(cover|title\s*page|copyright|contents|table\s+of\s+contents|"
    r"dedication|acknowledgments?|illustration|also by|about the author|"
    r"title|halftitle|colophon)\b",
    re.I,
)


def filter_novel_chapter_outline(outline: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Keep chapter-level bookmarks; drop nested leaves and front-matter titles.

    Needs at least two surviving entries, otherwise return [] so callers fall back.
    """
    entries = [dict(e) for e in (outline or []) if (e.get("title") or "").strip()]
    cleaned: list[dict[str, Any]] = []
    for e in entries:
        title = (e.get("title") or "").strip()
        if _NON_CHAPTER_TITLE.match(title):
            continue
        cleaned.append(e)
    if len(cleaned) < 2:
        return []
    levels = [int(e.get("level") or 0) for e in cleaned]
    min_level = min(levels)
    if max(levels) > min_level:
        top = [e for e in cleaned if int(e.get("level") or 0) == min_level]
        if len(top) >= 2:
            return top
    return cleaned


def chunk_novel_from_outline(
    pages: list[str],
    outline: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Split novel PDF pages by chapter bookmarks (reuse magazine page ranges)."""
    chapters = filter_novel_chapter_outline(outline)
    if len(chapters) < 2:
        return []
    return chunk_magazine_from_outline(pages, chapters)
```

**Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_intensive_reading_novel_toc.py::test_filter_keeps_top_level_chapters_not_nested_leaves tests/test_intensive_reading_novel_toc.py::test_filter_drops_front_matter_and_needs_two_chapters tests/test_intensive_reading_novel_toc.py::test_chunk_novel_from_outline_uses_chapter_page_ranges -v`

Expected: PASS

---

### Task 2: Parse printed novel Contents pages

**Files:**
- Modify: `scripts/rag/intensive_reading/chunking.py`
- Modify: `tests/test_intensive_reading_novel_toc.py`

**Step 1: Write the failing test**

Append to `tests/test_intensive_reading_novel_toc.py`:

```python
def test_outline_from_novel_contents_dotted_chapter_lines():
    pages = [
        "Table of Contents\n"
        "Chapter 1  Dawn .................... 3\n"
        "Chapter 2  The Storm ............... 12\n"
        "Chapter 3  Harbor .................. 21\n",
        "front",
        "chapter 1 body " + ("word " * 30),
    ]
    # Pad so printed page 3 can map; helper may map printed n -> index n-1 or scan.
    while len(pages) < 25:
        pages.append("body " + ("word " * 20))
    outline = outline_from_novel_contents(pages)
    titles = [e["title"] for e in outline]
    assert "Dawn" in titles[0] or "Chapter 1" in titles[0]
    assert len(outline) >= 3
    assert all("page" in e for e in outline)


def test_outline_from_novel_contents_ignores_non_toc_pages():
    pages = ["Once upon a time there was a storm on the harbor and the dawn came."]
    assert outline_from_novel_contents(pages) == []
```

If `_map_printed_page_to_index` is awkward to hit with synthetic pages, assert on parsed titles + that `page` is an int in range, and in Step 3 map `printed` via that helper when possible else `max(printed - 1, 0)`.

**Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_intensive_reading_novel_toc.py::test_outline_from_novel_contents_dotted_chapter_lines tests/test_intensive_reading_novel_toc.py::test_outline_from_novel_contents_ignores_non_toc_pages -v`

Expected: FAIL (`outline_from_novel_contents` not defined or returns `[]`).

**Step 3: Write minimal implementation**

```python
_NOVEL_TOC_LINE = re.compile(
    r"(?:chapter\s+(\d+)|第([一二三四五六七八九十百零〇0-9]+)[章节回卷部])"
    r"\s*[:.\s]*"
    r"([A-Za-z][^\.\n]{0,80}?)?"
    r"\s*(?:\.{2,}|\s{2,})\s*"
    r"(\d{1,4})\s*$",
    re.I,
)


def outline_from_novel_contents(pages: list[str]) -> list[dict[str, Any]]:
    """Build a chapter outline from a printed Contents page (dotted page numbers)."""
    found: list[dict[str, Any]] = []
    scan = (pages or [])[:8]
    if not any(is_toc_text(p or "") or _TOC_HEADING.search(p or "") for p in scan):
        # still accept a page that is mostly dotted chapter lines
        pass
    for page in scan:
        if not page:
            continue
        if not (is_toc_text(page) or _TOC_HEADING.search(page) or _PAGE_DOTS.search(page)):
            continue
        for raw in page.splitlines():
            m = _NOVEL_TOC_LINE.search(raw.strip())
            if not m:
                continue
            num = m.group(1) or m.group(2) or ""
            name = (m.group(3) or "").strip(" .")
            printed = int(m.group(4))
            title = f"Chapter {num} {name}".strip() if name else f"Chapter {num}"
            idx = _novel_printed_page_to_index(pages, printed, title)
            if idx is None or idx < 0 or idx >= len(pages):
                continue
            found.append({"title": title, "page": int(idx), "level": 0})
    # de-dupe by page, keep first
    seen: set[int] = set()
    out: list[dict[str, Any]] = []
    for e in found:
        if e["page"] in seen:
            continue
        seen.add(e["page"])
        out.append(e)
    if len(out) < 2:
        return []
    pages_idx = [e["page"] for e in out]
    if pages_idx != sorted(set(pages_idx)):
        return []  # not strictly increasing unique → unusable
    return out


def _novel_printed_page_to_index(pages: list[str], printed: int, title: str) -> Optional[int]:
    """Map novel Contents page numbers. Do NOT use _map_printed_page_to_index."""
    needle = re.sub(r"\s+", " ", (title or "")).strip().lower()
    if needle:
        for i, page in enumerate(pages or []):
            head = re.sub(r"\s+", " ", (page or "")[:200]).strip().lower()
            if needle and needle[:24] in head:
                return i
    idx = printed - 1 if printed >= 1 else 0
    if 0 <= idx < len(pages or []):
        return idx
    return None
```

Do not call `_map_printed_page_to_index`. Do not copy magazine Contributors parsing.

**Step 4: Run tests**

Run: `python -m pytest tests/test_intensive_reading_novel_toc.py -v`

Expected: PASS (Task 1 + Task 2).

---

### Task 3: EPUB novel sections as chapters

**Files:**
- Modify: `scripts/rag/intensive_reading/ingest.py` (`build_chunks` novel branch only)
- Modify: `tests/test_intensive_reading_novel_toc.py`

**Step 1: Write the failing tests**

```python
from intensive_reading.ingest import build_chunks, BOOK_TYPE_NOVEL  # noqa: E402


def test_epub_novel_uses_section_titles_then_splits_long_chapters():
    long = " ".join(["adventure"] * 2500)
    extracted = {
        "format": "epub",
        "title": "Demo",
        "pages": None,
        "sections": [
            {"title": "Chapter 1 Dawn", "text": "short dawn text " * 40},
            {"title": "Chapter 2 Storm", "text": long},
        ],
    }
    chunks = build_chunks(extracted, BOOK_TYPE_NOVEL)
    titles = [c["title"] for c in chunks]
    assert any(t.startswith("Chapter 1 Dawn") for t in titles)
    storm = [t for t in titles if t.startswith("Chapter 2 Storm")]
    assert len(storm) >= 2
    assert storm[0].endswith("(1)") or "Storm (1)" in storm[0]


def test_pdf_novel_without_outline_still_pages():
    pages = ["alpha " * 50, "beta " * 50, "gamma " * 50]
    chunks = build_chunks(
        {"format": "pdf", "title": "x", "pages": pages, "outline": []},
        BOOK_TYPE_NOVEL,
    )
    assert chunks
    assert all("Pages " in (c.get("title") or "") or c.get("text") for c in chunks)
```

**Step 2: Run to verify fail**

Run: `python -m pytest tests/test_intensive_reading_novel_toc.py::test_epub_novel_uses_section_titles_then_splits_long_chapters -v`

Expected: FAIL — current code either word-merges (because 2500 > 1600) and drops section titles, or does not add `(1)` chapter titles.

**Step 3: Write minimal implementation**

Replace the novel branch in `build_chunks` (`scripts/rag/intensive_reading/ingest.py` ~364–389) with:

```python
    # novel / ebook
    if extracted.get("pages") is not None:
        pages = extracted["pages"]
        outline = extracted.get("outline") or []
        chunks = chunk_novel_from_outline(pages, outline) if outline else []
        if not chunks:
            printed = outline_from_novel_contents(pages)
            if printed:
                chunks = chunk_novel_from_outline(pages, printed)
        if not chunks:
            chunks = chunk_novel_pages(pages, pages_per_chunk=2)
        return _split_oversized_chunks(chunks)
    if extracted.get("sections"):
        chunks = []
        for s in extracted["sections"]:
            text = (s.get("text") or "").strip()
            if not text:
                continue
            chunks.append(
                {
                    "chunk_index": len(chunks),
                    "text": text,
                    "title": s.get("title") or f"Part {len(chunks) + 1}",
                    "is_toc": is_toc_text(text),
                }
            )
        if len(chunks) < 2:
            texts = [c["text"] for c in chunks]
            return _split_oversized_chunks(chunk_by_words(texts, target_words=1000))
        words = [len(c["text"].split()) for c in chunks]
        words_sorted = sorted(words)
        median = words_sorted[len(words_sorted) // 2]
        if len(chunks) > 15 and median < 400:
            texts = [c["text"] for c in chunks]
            return _split_oversized_chunks(chunk_by_words(texts, target_words=1000))
        return _split_oversized_chunks(chunks)
    return []
```

Add imports at top of `ingest.py`: `chunk_novel_from_outline`, `outline_from_novel_contents` (and keep `chunk_novel_pages`, `is_toc_text`).

Add a test `test_epub_tiny_spine_falls_back_to_word_chunks`: 20 sections of ~80 words each → titles are `Part N` / word-merged, **not** 20 chapter TOC entries.

**Step 4: Run tests**

Run: `python -m pytest tests/test_intensive_reading_novel_toc.py -v`

Expected: PASS. Also run a magazine TOC test if present: `python -m pytest tests/test_intensive_reading_magazine_toc.py -v` (must still PASS — do not change magazine branch).

---

### Task 4: Novel `toc.json` collapses sub-chunks to chapters

**Files:**
- Modify: `scripts/rag/intensive_reading/ingest.py` (`build_toc_entries`, `save_book_files`)
- Modify: `tests/test_intensive_reading_novel_toc.py`

**Step 1: Write the failing tests**

```python
from intensive_reading.ingest import build_toc_entries  # noqa: E402


def test_build_toc_entries_novel_collapses_split_chapters():
    chunks = [
        {"chunk_index": 0, "title": "Contents", "is_toc": True, "text": "toc"},
        {"chunk_index": 1, "title": "Chapter 1 Dawn (1)", "is_toc": False, "text": "a"},
        {"chunk_index": 2, "title": "Chapter 1 Dawn (2)", "is_toc": False, "text": "b"},
        {"chunk_index": 3, "title": "Chapter 2 Storm (1)", "is_toc": False, "text": "c"},
    ]
    toc = build_toc_entries(chunks, book_type="novel")
    assert [e["title"] for e in toc] == ["Chapter 1 Dawn", "Chapter 2 Storm"]
    assert toc[0]["chunk_index"] == 1
    assert toc[1]["chunk_index"] == 3


def test_build_toc_entries_magazine_unchanged_lists_parts():
    chunks = [
        {"chunk_index": 0, "title": "Cash and Carry (1)", "is_toc": False},
        {"chunk_index": 1, "title": "Cash and Carry (2)", "is_toc": False},
    ]
    toc = build_toc_entries(chunks, book_type="magazine")
    assert len(toc) == 2
```

**Step 2: Run to verify fail**

Run: `python -m pytest tests/test_intensive_reading_novel_toc.py::test_build_toc_entries_novel_collapses_split_chapters -v`

Expected: FAIL (`book_type` unexpected or no collapse).

**Step 3: Write minimal implementation**

```python
_PART_SUFFIX = re.compile(r"\s*\(\d+\)\s*$")


def build_toc_entries(
    chunks: list[dict[str, Any]],
    book_type: str | None = None,
) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    seen_chapters: set[str] = set()
    collapse = (book_type or "").lower() == BOOK_TYPE_NOVEL
    for c in chunks or []:
        if c.get("is_toc"):
            continue
        title = (c.get("title") or "").strip()
        if not title:
            continue
        display = _PART_SUFFIX.sub("", title).strip() if collapse else title
        if collapse:
            key = display.lower()
            if key in seen_chapters:
                continue
            seen_chapters.add(key)
        entry: dict[str, Any] = {
            "title": display,
            "chunk_index": int(c.get("chunk_index", len(entries))),
        }
        ...
    return entries
```

Update `write_toc_json(book_dir, chunks, book_type=...)` to pass `book_type`.

In `save_book_files`, write toc for **both** magazine and novel:

```python
    if book_type in (BOOK_TYPE_MAGAZINE, BOOK_TYPE_NOVEL):
        write_toc_json(book_dir, chunks, book_type=book_type)
```

**Step 4: Run tests**

Run: `python -m pytest tests/test_intensive_reading_novel_toc.py -v`

Expected: PASS

---

### Task 5: GET book returns novel toc + rebuild novels

**Files:**
- Modify: `scripts/rag/routes/intensive_reading.py` (`api_get_book` ~214–215)
- Modify: `scripts/rag/intensive_reading/ingest.py` (`rebuild_magazine_from_original`)
- Modify: `tests/test_intensive_reading_novel_toc.py` (rebuild unit test with tmp dir)

**Step 1: Write the failing test**

```python
import json
import tempfile
from pathlib import Path

from intensive_reading.ingest import (  # noqa: E402
    BOOK_TYPE_NOVEL,
    rebuild_magazine_from_original,
    save_book_files,
)


def test_rebuild_accepts_novel(tmp_path, monkeypatch):
    # Minimal: if rebuild still raises ValueError for novels, fail.
    # Implement by pointing meta at a tiny PDF/EPUB fixture if one exists;
    # otherwise unit-test the type guard with a fake meta.json + original.txt skip.
    pass
```

Prefer a focused unit test of the guard:

```python
def test_rebuild_novel_type_guard_allows_novel(tmp_path):
    from intensive_reading.ingest import load_meta, update_meta_fields
    # Create meta book_type=novel without original -> FileNotFoundError, NOT ValueError
```

And a route string test is optional; easier: change `api_get_book` so toc is attached whenever `load_toc` returns data (both types):

```python
    meta["toc"] = load_toc(_books_dir(), book_id)
```

(`load_toc` already falls back to `build_toc_entries` from chunks; pass book_type into that fallback.)

**Step 2: Run to verify fail**

Call `rebuild_magazine_from_original` on a novel meta → today `ValueError`.

**Step 3: Write minimal implementation**

1. `api_get_book`: always set `meta["toc"] = load_toc(...)`.
2. `load_toc`: `return build_toc_entries(load_chunks(...), book_type=meta.get("book_type"))` on fallback.
3. `rebuild_magazine_from_original`: allow `BOOK_TYPE_NOVEL` and `BOOK_TYPE_MAGAZINE`; use `book_type` from meta for `build_chunks` and `index_chunks_to_rag`; always `write_toc_json(..., book_type=book_type)`. Keep the function name (callers/scripts). Update docstring: novels allowed; analyses cleared; `reindex_rag=False` → `rag_status=stale`.

**Step 4: Run tests**

Run: `python -m pytest tests/test_intensive_reading_novel_toc.py -v`

Expected: PASS

---

### Task 6: UI — Chapters ▾ for novels

**Files:**
- Modify: `scripts/rag/templates/index.html` (`irSyncArticlesUi`, `irToggleArticlesPop`, `irOpenBook`, `irRenderArticlesPop` empty copy)
- Create: `tests/test_intensive_reading_passage_ui.py`

**Step 1: Write the failing UI contract tests**

```python
from pathlib import Path

HTML = Path(__file__).resolve().parents[1] / "scripts" / "rag" / "templates" / "index.html"


def test_articles_ui_shown_for_novels():
    text = HTML.read_text(encoding="utf-8")
    fn = text[text.find("function irSyncArticlesUi"):text.find("function irRenderArticlesPop")]
    assert "bookType === 'magazine'" in fn or "magazine" in fn
    assert "novel" in fn
    assert "Chapters" in text[text.find("function irSyncArticlesUi"):text.find("async function irRefreshBooks")]


def test_open_book_loads_toc_for_novels():
    text = HTML.read_text(encoding="utf-8")
    fn = text[text.find("async function irOpenBook"):text.find("function irRenderPassage")]
    assert "meta.toc" in fn
    assert "magazine" not in fn.split("_irState.toc")[1][:80] or "Array.isArray(meta.toc)" in fn
    # Must NOT be: bookType === 'magazine' && Array.isArray(meta.toc)
    assert "_irState.toc = (_irState.bookType === 'magazine' && Array.isArray(meta.toc))" not in fn
```

**Step 2: Run to verify fail**

Run: `python -m pytest tests/test_intensive_reading_passage_ui.py -v`

Expected: FAIL (novel still hidden; toc only if magazine).

**Step 3: Write minimal implementation**

`irSyncArticlesUi`:

```javascript
  var toc = Array.isArray(_irState.toc) ? _irState.toc : [];
  var pageish = toc.filter(function(e) { return /^Pages\s+\d/i.test(e.title || ''); }).length;
  var real = toc.length && pageish / toc.length < 0.8;
  var show = !!_irState.bookId && real &&
    (_irState.bookType === 'magazine' || _irState.bookType === 'novel');
  wrap.style.display = show ? 'inline-flex' : 'none';
  var btn = document.getElementById('irArticlesBtn');
  if (btn) btn.textContent = (_irState.bookType === 'novel') ? 'Chapters ▾' : 'Articles ▾';
```

`irToggleArticlesPop`: allow novel (remove `bookType !== 'magazine'` return).

`irOpenBook`:

```javascript
    _irState.toc = Array.isArray(meta.toc) ? meta.toc : [];
```

`irRenderArticlesPop` empty: `'No chapters list yet'` vs `'No articles list yet'` by bookType.

Mark active chapter: `entry.chunk_index === _irState.chunkIndex` is wrong for sub-chunks. Highlight when current chunk is in `[entry.chunk_index, nextEntry.chunk_index)`. Implement:

```javascript
    var nextStart = (i + 1 < toc.length) ? toc[i + 1].chunk_index : Infinity;
    var active = _irState.chunkIndex >= entry.chunk_index && _irState.chunkIndex < nextStart;
```

**Step 4: Run tests**

Run: `python -m pytest tests/test_intensive_reading_passage_ui.py -v`

Expected: PASS

---

### Task 7: Passage reading typography (CSS + render class)

**Files:**
- Modify: `scripts/rag/templates/index.html` CSS ~183–198, `irRenderPassage` ~2324–2374, split grid ~185 and ~724
- Modify: `tests/test_intensive_reading_passage_ui.py`

**Step 1: Write the failing tests**

```python
def test_passage_css_is_reading_theme():
    text = HTML.read_text(encoding="utf-8")
    css = text[text.find("#irPassage{"):text.find("#irExplainBtn")]
    assert "Georgia" in css
    assert "38em" in css or "max-width:38em" in css.replace(" ", "")
    assert "text-align:left" in css.replace(" ", "") or "text-align: left" in css
    assert "#d6d2c8" in css
    assert "#16141a" in css
    assert "text-align:justify" not in css.replace(" ", "")


def test_passage_novel_vs_magazine_para_rules():
    text = HTML.read_text(encoding="utf-8")
    assert "ir-kind-novel" in text
    assert "ir-kind-magazine" in text
    fn = text[text.find("function irRenderPassage"):text.find("function irRenderPlainParas")]
    assert "ir-kind-novel" in fn and "ir-kind-magazine" in fn
    assert "articleTitle" in fn
```

**Step 2: Run to verify fail**

Run: `python -m pytest tests/test_intensive_reading_passage_ui.py::test_passage_css_is_reading_theme -v`

Expected: FAIL (current CSS is justify / system UI / `#e8eaf2`).

**Step 3: Write minimal implementation**

Replace Passage CSS block with:

```css
#intensiveReadingModal .ir-split{grid-template-columns:1.6fr 1fr;gap:14px}
#irPassage{padding:28px 20px 40px!important;font-size:18px!important;line-height:1.72!important;
  color:#d6d2c8!important;white-space:normal!important;background:#16141a;
  font-family:Georgia,"Iowan Old Style","Palatino Linotype",Palatino,"Times New Roman",serif;
  letter-spacing:0.01em;overflow-wrap:break-word}
#irPassage .ir-reading-col{max-width:38em;margin:0 auto}
#irPassage .ir-para{text-align:left;hyphens:none;overflow-wrap:break-word}
#irPassage.ir-kind-novel .ir-para{margin:0 0 0.28em;text-indent:1.25em}
#irPassage.ir-kind-magazine .ir-para{margin:0 0 0.9em;text-indent:0}
#irPassage .ir-para.ir-title{text-indent:0;font-weight:600;font-size:1.12em;color:#e4e0d4;
  margin-bottom:0.85em;line-height:1.4;text-align:left}
#irPassage .ir-para.ir-kicker{text-indent:0;font-size:0.82em;letter-spacing:0.04em;
  text-transform:uppercase;color:#9a9588;margin-bottom:0.35em;text-align:left}
#irPassage .ir-article-title{margin:0 0 0.85em;padding:0 0 0.55em;border-bottom:1px solid #2a2d3a;
  text-indent:0;text-align:left;font-weight:650;font-size:1.22em;line-height:1.35;color:#e8e4da}
```

Also update the inline `grid-template-columns:1.45fr 1fr` on the reader split div to `1.6fr 1fr`.

`irRenderPassage`:

```javascript
  el.className = 'ir-passage ir-kind-' + (isMagazine ? 'magazine' : 'novel');
  el.innerHTML = '';
  var col = document.createElement('div');
  col.className = 'ir-reading-col';
  el.appendChild(col);
  // append heading + paras to col, not el
```

Show `ir-article-title` heading for **both** magazine and novel when `articleTitle` is set (novels currently hide `irChunkTitle` — keep header meta as-is or show title in-body; in-body heading is required).

Do **not** change `#irAnalysis` rules. Selection explain still queries `#irPassage .ir-para` — wrapper does not break that.

**Step 4: Run tests**

Run: `python -m pytest tests/test_intensive_reading_passage_ui.py tests/test_intensive_reading_novel_toc.py -v`

Expected: PASS

If `tests/test_intensive_reading_selection_explain.py` exists, run it too — Passage DOM must still have `.ir-para` nodes.

---

### Task 8: Wire imports + regression sweep

**Files:**
- Modify: `scripts/rag/intensive_reading/ingest.py` imports only if Task 3 missed any

**Step 1:** Confirm `from intensive_reading.chunking import` includes `chunk_novel_from_outline`, `outline_from_novel_contents`.

**Step 2:** Run:

```
python -m pytest tests/test_intensive_reading_novel_toc.py tests/test_intensive_reading_passage_ui.py tests/test_intensive_reading_magazine_toc.py tests/test_intensive_reading_magazine_titles.py tests/test_intensive_reading_selection_explain.py -v
```

Skip any file that does not exist on disk. All existing intensive-reading tests that are present must PASS.

**Step 3:** Manual check (do not claim done without it if a novel PDF is available under `docs/books/`):
- Open Intensive Reading → a novel → Passage uses serif, narrower column, left align.
- Chapters ▾ lists chapter titles; jump lands on first sub-chunk.
- Magazine Articles ▾ and article chunking unchanged.
- Select a sentence → Explain still appears.

No commit unless the user asks.

---

## Verification Summary

- [ ] Novel PDF with bookmarks → chapter-titled chunks, long chapters split with `(1)/(2)`
- [ ] Novel PDF without bookmarks but with Contents dotted list → same
- [ ] Novel PDF with neither → `Pages N-M` 1–2 page chunks (old behavior)
- [ ] EPUB novel → section titles as chapters, oversized split
- [ ] `toc.json` + GET book `toc` for novels; Chapters ▾ collapse to chapter starts
- [ ] Magazine `build_chunks` path untouched; magazine tests still pass
- [ ] Passage: Georgia, 18px, 38em, left, `#d6d2c8`/`#16141a`, novel indent vs magazine spacing
- [ ] `#irAnalysis` CSS unchanged; `.ir-para` still used for Explain
- [ ] Rebuild novel clears analyses; RAG stale if `reindex_rag=False`
