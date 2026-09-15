"""Novel TOC / chapter-boundary chunking."""
from __future__ import annotations

import os
import sys

_RAG = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "scripts", "rag"))
if _RAG not in sys.path:
    sys.path.insert(0, _RAG)

from intensive_reading.chunking import (  # noqa: E402
    _novel_printed_page_to_index,
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


def test_filter_prefers_chapters_under_part_bookmarks():
    outline = [
        {"title": "Part I", "page": 4, "level": 0},
        {"title": "Chapter 1 Dawn", "page": 5, "level": 1},
        {"title": "Part II", "page": 40, "level": 0},
        {"title": "Chapter 2 Storm", "page": 41, "level": 1},
    ]
    leaves = filter_novel_chapter_outline(outline)
    assert [e["title"] for e in leaves] == ["Chapter 1 Dawn", "Chapter 2 Storm"]


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


def test_outline_from_novel_contents_dotted_chapter_lines():
    pages = [
        "Table of Contents\n"
        "Chapter 1  Dawn .................... 3\n"
        "Chapter 2  The Storm ............... 12\n"
        "Chapter 3  Harbor .................. 21\n",
    ]
    while len(pages) < 25:
        pages.append("body " + ("word " * 20))
    # Heading-scan should win when the chapter title is on that PDF page
    pages[2] = "Chapter 1 Dawn " + ("word " * 20)
    pages[11] = "Chapter 2 The Storm " + ("word " * 20)
    pages[20] = "Chapter 3 Harbor " + ("word " * 20)
    outline = outline_from_novel_contents(pages)
    titles = [e["title"] for e in outline]
    assert len(outline) >= 3
    assert any("Dawn" in t for t in titles)
    assert any("Storm" in t for t in titles)
    assert any("Harbor" in t for t in titles)
    assert all(isinstance(e.get("page"), int) for e in outline)
    pages_idx = [e["page"] for e in outline]
    assert pages_idx == sorted(set(pages_idx))
    assert outline[0]["page"] == 2
    assert outline[1]["page"] == 11
    assert outline[2]["page"] == 20


def test_outline_from_novel_contents_ignores_non_toc_pages():
    pages = ["Once upon a time there was a storm on the harbor and the dawn came."]
    assert outline_from_novel_contents(pages) == []


def test_outline_from_novel_contents_uses_printed_minus_one_without_headings():
    pages = [
        "Contents\n"
        "Chapter 1  Dawn .................... 3\n"
        "Chapter 2  Storm ................... 12\n",
    ]
    while len(pages) < 15:
        pages.append("body " + ("word " * 20))
    outline = outline_from_novel_contents(pages)
    assert len(outline) == 2
    assert outline[0]["page"] == 2  # printed 3 → index 2
    assert outline[1]["page"] == 11  # printed 12 → index 11


def test_heading_scan_finds_chapter_beyond_nearby_window():
    pages = [
        "Table of Contents\n"
        "Chapter 1  Dawn .................... 3\n"
        "Chapter 2  Storm ................... 12\n",
    ]
    while len(pages) < 25:
        pages.append("body " + ("word " * 20))
    pages[18] = "Chapter 1 Dawn " + ("word " * 20)
    pages[20] = "Chapter 2 Storm " + ("word " * 20)
    outline = outline_from_novel_contents(pages)
    assert [e["page"] for e in outline] == [18, 20]


def test_printed_outline_discarded_when_pages_not_increasing():
    pages = [
        "Contents\n"
        "Chapter 1  Dawn .................... 12\n"
        "Chapter 2  Storm ................... 3\n",
    ]
    while len(pages) < 15:
        pages.append("body " + ("word " * 20))
    assert outline_from_novel_contents(pages) == []


def test_printed_toc_accepts_colon_and_dot_after_chapter_number():
    pages = [
        "Contents\n"
        "Chapter 1: Dawn .................... 3\n"
        "Chapter 2. Storm ................... 12\n",
    ]
    while len(pages) < 15:
        pages.append("body " + ("word " * 20))
    outline = outline_from_novel_contents(pages)
    assert len(outline) == 2
    assert any("Dawn" in e["title"] for e in outline)
    assert any("Storm" in e["title"] for e in outline)


def test_chapter_1_heading_does_not_match_chapter_10():
    pages = ["front"] + ["body " + ("word " * 20) for _ in range(14)]
    pages[5] = "Chapter 10 The storm begins " + ("word " * 20)
    idx = _novel_printed_page_to_index(pages, 3, "Chapter 1")
    assert idx == 2
    assert idx != 5


def test_pdf_novel_with_outline_uses_chapter_titles():
    from intensive_reading.ingest import BOOK_TYPE_NOVEL, build_chunks

    pages = [f"page {i} " + ("word " * 40) for i in range(10)]
    chunks = build_chunks(
        {
            "format": "pdf",
            "title": "Demo",
            "pages": pages,
            "outline": [
                {"title": "Chapter 1 Dawn", "page": 2, "level": 0},
                {"title": "Chapter 2 Storm", "page": 6, "level": 0},
            ],
        },
        BOOK_TYPE_NOVEL,
    )
    titles = [c["title"] for c in chunks]
    assert any("Dawn" in t for t in titles)
    assert any("Storm" in t for t in titles)


def test_pdf_novel_without_outline_still_pages():
    from intensive_reading.ingest import BOOK_TYPE_NOVEL, build_chunks

    pages = ["alpha " * 50, "beta " * 50, "gamma " * 50]
    chunks = build_chunks(
        {"format": "pdf", "title": "x", "pages": pages, "outline": []},
        BOOK_TYPE_NOVEL,
    )
    assert chunks
    assert any("Pages " in (c.get("title") or "") for c in chunks)


def test_epub_novel_uses_section_titles_then_splits_long_chapters():
    from intensive_reading.ingest import BOOK_TYPE_NOVEL, build_chunks

    long = " ".join(["adventure"] * 2500)
    chunks = build_chunks(
        {
            "format": "epub",
            "title": "Demo",
            "pages": None,
            "sections": [
                {"title": "Chapter 1 Dawn", "text": "short dawn text " * 40},
                {"title": "Chapter 2 Storm", "text": long},
            ],
        },
        BOOK_TYPE_NOVEL,
    )
    titles = [c["title"] for c in chunks]
    assert any(t.startswith("Chapter 1 Dawn") for t in titles)
    storm = [t for t in titles if t.startswith("Chapter 2 Storm")]
    assert len(storm) >= 2
    assert "(1)" in storm[0]


def test_epub_tiny_spine_falls_back_to_word_chunks():
    from intensive_reading.ingest import BOOK_TYPE_NOVEL, build_chunks

    sections = [{"title": f"File {i}", "text": ("hello " * 80)} for i in range(20)]
    chunks = build_chunks(
        {
            "format": "epub",
            "title": "Demo",
            "pages": None,
            "sections": sections,
        },
        BOOK_TYPE_NOVEL,
    )
    titles = [c["title"] for c in chunks]
    assert len(chunks) < 20
    assert not any(str(t).startswith("File ") for t in titles)


def test_build_toc_entries_novel_collapses_split_chapters():
    from intensive_reading.ingest import build_toc_entries

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


def test_build_toc_entries_novel_keeps_later_repeat_chapter_title():
    """A second Chapter 1 after a part title must stay in the TOC (not globally unique)."""
    from intensive_reading.ingest import build_toc_entries

    chunks = [
        {"chunk_index": 6, "title": "Chapter 1 (1)", "is_toc": False},
        {"chunk_index": 7, "title": "Chapter 1 (2)", "is_toc": False},
        {"chunk_index": 74, "title": "Returns and Departures", "is_toc": False},
        {"chunk_index": 75, "title": "Chapter 1 (1)", "is_toc": False},
        {"chunk_index": 76, "title": "Chapter 1 (2)", "is_toc": False},
        {"chunk_index": 84, "title": "Chapter 2 (1)", "is_toc": False},
    ]
    toc = build_toc_entries(chunks, book_type="novel")
    titles = [e["title"] for e in toc]
    assert titles == [
        "Chapter 1",
        "Returns and Departures",
        "Chapter 1",
        "Chapter 2",
    ]
    assert toc[0]["chunk_index"] == 6
    assert toc[2]["chunk_index"] == 75
    assert toc[3]["chunk_index"] == 84


def test_build_toc_entries_magazine_unchanged_lists_parts():
    from intensive_reading.ingest import build_toc_entries

    chunks = [
        {"chunk_index": 0, "title": "Cash and Carry (1)", "is_toc": False},
        {"chunk_index": 1, "title": "Cash and Carry (2)", "is_toc": False},
    ]
    toc = build_toc_entries(chunks, book_type="magazine")
    assert len(toc) == 2
    assert toc[0]["title"] == "Cash and Carry (1)"


def test_rebuild_novel_without_original_is_file_not_found(tmp_path):
    import json

    from intensive_reading.ingest import rebuild_magazine_from_original

    book_id = "demo-abc"
    book_dir = tmp_path / book_id
    book_dir.mkdir()
    (book_dir / "meta.json").write_text(
        json.dumps({"book_id": book_id, "book_type": "novel", "title": "Demo"}),
        encoding="utf-8",
    )
    try:
        rebuild_magazine_from_original(str(tmp_path), book_id)
    except ValueError as e:
        raise AssertionError(f"novels must not be rejected: {e}") from e
    except FileNotFoundError:
        return
    raise AssertionError("expected FileNotFoundError when original.* is missing")


def test_rebuild_unknown_book_type_raises(tmp_path):
    import json

    import pytest
    from intensive_reading.ingest import rebuild_magazine_from_original

    book_id = "demo-abc"
    book_dir = tmp_path / book_id
    book_dir.mkdir()
    (book_dir / "meta.json").write_text(
        json.dumps({"book_id": book_id, "book_type": "audiobook", "title": "Demo"}),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="magazine or novel"):
        rebuild_magazine_from_original(str(tmp_path), book_id)


def test_load_toc_fallback_collapses_novel(tmp_path):
    import json

    from intensive_reading.ingest import load_toc

    book_id = "demo-abc"
    book_dir = tmp_path / book_id
    book_dir.mkdir()
    (book_dir / "meta.json").write_text(
        json.dumps({"book_id": book_id, "book_type": "novel", "title": "Demo"}),
        encoding="utf-8",
    )
    chunks = [
        {"chunk_index": 1, "title": "Chapter 1 Dawn (1)", "is_toc": False},
        {"chunk_index": 2, "title": "Chapter 1 Dawn (2)", "is_toc": False},
    ]
    (book_dir / "chunks.json").write_text(json.dumps(chunks), encoding="utf-8")
    toc = load_toc(str(tmp_path), book_id)
    assert [e["title"] for e in toc] == ["Chapter 1 Dawn"]
    assert toc[0]["chunk_index"] == 1


def test_get_book_route_always_attaches_toc():
    from pathlib import Path

    text = (
        Path(__file__).resolve().parents[1]
        / "scripts"
        / "rag"
        / "routes"
        / "intensive_reading.py"
    ).read_text(encoding="utf-8")
    start = text.find("def api_get_book")
    end = text.find("def api_delete_book")
    fn = text[start:end]
    assert 'meta["toc"] = load_toc' in fn
    assert "BOOK_TYPE_MAGAZINE" not in fn
