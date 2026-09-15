"""Magazine chunking: section titles + rebuild/clear analyses (novels untouched)."""

from __future__ import annotations

import json
import os
import sys

import pytest

_RAG = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "scripts", "rag"))
_SCRIPTS = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "scripts"))
for _p in (_SCRIPTS, _RAG):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from intensive_reading.analysis_cache import (  # noqa: E402
    clear_book_analyses,
    save_chunk_analysis,
)
from intensive_reading.ingest import (  # noqa: E402
    BOOK_TYPE_MAGAZINE,
    BOOK_TYPE_NOVEL,
    build_chunks,
    rebuild_magazine_from_original,
)


def test_magazine_epub_sections_keep_article_titles():
    extracted = {
        "format": "epub",
        "title": "Demo Mag",
        "pages": None,
        "sections": [
            {"title": "Cover", "text": "Cover art and masthead only.\n\nMore cover text."},
            {
                "title": "Why Normies Vibe Code",
                "text": (
                    "Why Normies Vibe Code\n\n"
                    "The first paragraph of a real magazine article with enough words "
                    "to look like body copy rather than a table of contents listing."
                ),
            },
            {
                "title": "Quiz: Will AI Destroy Your Career?",
                "text": (
                    "Quiz: Will AI Destroy Your Career?\n\n"
                    "Another full article body with several sentences so it is not "
                    "merged away as a tiny fragment during ingest."
                ),
            },
        ],
    }
    chunks = build_chunks(extracted, BOOK_TYPE_MAGAZINE)
    titles = [c["title"] for c in chunks]
    assert "Why Normies Vibe Code" in titles
    assert "Quiz: Will AI Destroy Your Career?" in titles
    # Must not smash all articles into one mush where title is only Cover
    assert len(chunks) >= 3


def _words(n: int, seed: str = "reporting") -> str:
    return " ".join([seed] * n)


def test_strong_epub_title_keeps_article_not_heading_fragments():
    """Wired-like: one spine file, strong title, long body with kickers."""
    title = "Elite Young Runners Are Becoming Freakishly Fast"
    text = (
        title
        + "\n\n"
        + _words(700, "runners")
        + "\n\nThe Big Story\n\n"
        + _words(700, "investigation")
    )
    assert len(text.split()) > 1200
    extracted = {
        "format": "epub",
        "title": "Wired Magazine",
        "pages": None,
        "sections": [{"title": title + " | WIRED", "text": text}],
    }
    chunks = build_chunks(extracted, BOOK_TYPE_MAGAZINE)
    titles = [c["title"] for c in chunks]
    assert all("The Big Story" not in t for t in titles)
    assert all("Elite Young Runners" in t for t in titles)
    assert len(chunks) >= 2  # word-split into Part 1/2
    assert len(chunks) < 8


def test_nav_chrome_title_is_not_weak():
    from intensive_reading.chunking import (
        is_weak_magazine_title,
        normalize_magazine_section_title,
    )

    raw = (
        "Elite Young Runners Are Becoming Freakishly Fast. Welcome to Trackflation "
        "| WIRED | Next | Section menu | Main menu |"
    )
    cleaned = normalize_magazine_section_title(raw)
    assert "Next" not in cleaned
    assert "Section menu" not in cleaned
    assert "WIRED" in cleaned
    assert is_weak_magazine_title(raw) is False
    assert is_weak_magazine_title(cleaned) is False


def test_strong_epub_nav_title_does_not_heading_split():
    title = (
        "Elite Young Runners Are Becoming Freakishly Fast | WIRED | Next | "
        "Section menu | Main menu | Previous |"
    )
    text = (
        "Elite Young Runners Are Becoming Freakishly Fast\n\n"
        + _words(700, "runners")
        + "\n\nThe Big Story\n\n"
        + _words(700, "investigation")
    )
    extracted = {
        "format": "epub",
        "title": "Wired Magazine",
        "pages": None,
        "sections": [{"title": title, "text": text}],
    }
    chunks = build_chunks(extracted, BOOK_TYPE_MAGAZINE)
    titles = [c["title"] for c in chunks]
    assert all("The Big Story" not in t for t in titles)
    assert all("Next" not in t and "Section menu" not in t for t in titles)
    assert all("Elite Young Runners" in t for t in titles)


def test_weak_epub_title_still_heading_splits_multi_article_blob():
    """Economist-like EPUB blob with a weak spine title still splits on headings."""
    text = (
        "Business\n\n"
        + _words(650, "markets")
        + "\n\nFinance & economics\n\n"
        + _words(650, "banks")
    )
    extracted = {
        "format": "epub",
        "title": "The Economist",
        "pages": None,
        "sections": [{"title": "Magazine Articles", "text": text}],
    }
    chunks = build_chunks(extracted, BOOK_TYPE_MAGAZINE)
    titles = [c["title"] for c in chunks]
    assert len(chunks) >= 2
    joined = " ".join(titles).lower()
    assert "business" in joined or "finance" in joined


def test_pdf_magazine_outline_path_unchanged():
    extracted = {
        "format": "pdf",
        "title": "Eco",
        "pages": [
            "pad " * 50,
            "Article one body " * 40,
            "Article two body " * 40,
        ],
        "sections": None,
        "outline": [
            {"title": "Real Bookmark One", "page": 1, "level": 0},
            {"title": "Real Bookmark Two", "page": 2, "level": 0},
        ],
    }
    chunks = build_chunks(extracted, BOOK_TYPE_MAGAZINE)
    titles = [c["title"] for c in chunks]
    assert "Real Bookmark One" in titles
    assert "Real Bookmark Two" in titles


def test_novel_section_path_unchanged_by_magazine_fix():
    extracted = {
        "format": "epub",
        "title": "A Novel",
        "pages": None,
        "sections": [
            {"title": "Chapter 1", "text": "Once upon a time " * 40},
            {"title": "Chapter 2", "text": "Later that day " * 40},
        ],
    }
    chunks = build_chunks(extracted, BOOK_TYPE_NOVEL)
    assert [c["title"] for c in chunks] == ["Chapter 1", "Chapter 2"]


def test_clear_book_analyses(tmp_path):
    books = tmp_path / "books"
    bid = "wired-demo-abcd1234"
    book_dir = books / bid
    book_dir.mkdir(parents=True)
    (book_dir / "meta.json").write_text(
        json.dumps(
            {
                "book_id": bid,
                "title": "Demo",
                "book_type": "magazine",
                "status": "ready",
                "chunk_count": 1,
            }
        ),
        encoding="utf-8",
    )
    (book_dir / "chunks.json").write_text(
        json.dumps([{"chunk_index": 0, "text": "hi", "title": "T", "is_toc": False}]),
        encoding="utf-8",
    )
    save_chunk_analysis(
        str(books),
        bid,
        0,
        {"vocab": {"text": "cached", "status": "done"}},
        merge=True,
    )
    analyses = book_dir / "analyses"
    assert analyses.is_dir()
    assert any(analyses.iterdir())
    n = clear_book_analyses(str(books), bid)
    assert n >= 1
    assert not any(analyses.iterdir()) if analyses.is_dir() else True


def test_rebuild_allows_novel(tmp_path):
    books = tmp_path / "books"
    bid = "novel-book-abcd1234"
    book_dir = books / bid
    book_dir.mkdir(parents=True)
    (book_dir / "meta.json").write_text(
        json.dumps(
            {
                "book_id": bid,
                "title": "Novel",
                "book_type": "novel",
                "status": "ready",
                "chunk_count": 1,
                "filename": "x.epub",
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(FileNotFoundError, match="original"):
        rebuild_magazine_from_original(str(books), bid)


def test_magazine_pdf_pages_polish_weak_titles():
    """PDF magazines use pages path; weak first-line titles must be polished."""
    page = (
        "MARCH 2, 2026PRICE $10.99\n\n"
        "Monica Lewinsky Has Always Hated Notifications\n\n"
        + ("Essay body with enough words for a readable magazine chunk. " * 40)
    )
    extracted = {
        "format": "pdf",
        "title": "NY",
        "pages": [page],
        "sections": None,
    }
    chunks = build_chunks(extracted, BOOK_TYPE_MAGAZINE)
    assert chunks
    assert not any("PRICE" in (c.get("title") or "").upper() for c in chunks)
    assert any("Monica" in (c.get("title") or "") for c in chunks)


def test_magazine_dense_masthead_line_strips_or_falls_back_to_article_n():
    """I-NEW-1: dense NY PDF line with masthead must not keep PRICE title."""
    page = (
        "MARCH 2, 2026PRICE $10.99\n\n"
        "4 THE NEW YORKER, MARCH 2, 2026 GOINGS ON FEBRUARY 25 – MARCH 3, 2026 "
        "For more than a decade, the singer-songwriter Mitski has been a totem "
        "for yearners across continents and late-night playlists everywhere. "
        * 5
    )
    extracted = {
        "format": "pdf",
        "title": "NY",
        "pages": [page],
        "sections": None,
    }
    chunks = build_chunks(extracted, BOOK_TYPE_MAGAZINE)
    assert chunks
    assert not any("PRICE" in (c.get("title") or "").upper() for c in chunks)
    # Either a real-ish headline after masthead strip, or Article N fallback
    for c in chunks:
        t = c.get("title") or ""
        assert "PRICE" not in t.upper()
        assert t.strip()


def test_magazine_credit_lines_are_weak_titles():
    from intensive_reading.chunking import is_weak_magazine_title

    assert is_weak_magazine_title("ILLUSTRATION: JOHN DOE")
    assert is_weak_magazine_title("PHOTOGRAPH: JANE SMITH")
    assert not is_weak_magazine_title("Why Normies Vibe Code")


def test_magazine_weak_spine_title_splits_on_internal_headings():
    """Critical-1: TOC/cover spine title + multi-article body → usable article titles."""
    body = (
        "Contents\n\n"
        "Leaders\n\n"
        + ("Policy brief paragraph with enough words to count as body copy. " * 8)
        + "\n\n"
        "Science & technology\n\n"
        + ("Lab notes and gadgets discussed in detail for readers at home. " * 8)
    )
    extracted = {
        "format": "epub",
        "title": "Demo Mag",
        "pages": None,
        "sections": [
            {
                "title": "MARCH 2, 2026PRICE $10.99",
                "text": body,
            }
        ],
    }
    chunks = build_chunks(extracted, BOOK_TYPE_MAGAZINE)
    titles = [c["title"] for c in chunks]
    assert not any("PRICE" in (t or "").upper() for t in titles)
    assert any("Leaders" in (t or "") for t in titles) or any(
        "Science" in (t or "") for t in titles
    )
    assert len(chunks) >= 2


def test_rebuild_magazine_success_clears_analyses_and_marks_rag_stale(tmp_path, monkeypatch):
    books = tmp_path / "books"
    bid = "mag-book-abcd1234"
    book_dir = books / bid
    book_dir.mkdir(parents=True)
    (book_dir / "meta.json").write_text(
        json.dumps(
            {
                "book_id": bid,
                "title": "Demo Mag",
                "book_type": "magazine",
                "status": "ready",
                "chunk_count": 1,
                "rag_status": "ok",
                "rag_chunks": 99,
                "filename": "demo.epub",
            }
        ),
        encoding="utf-8",
    )
    (book_dir / "chunks.json").write_text(
        json.dumps(
            [{"chunk_index": 0, "text": "old", "title": "Old", "is_toc": False}]
        ),
        encoding="utf-8",
    )
    (book_dir / "original.epub").write_bytes(b"PK\x03\x04fake")
    save_chunk_analysis(
        str(books),
        bid,
        0,
        {"vocab": {"text": "stale-cache", "status": "done"}},
        merge=True,
    )

    def _fake_extract(_path: str):
        return {
            "format": "epub",
            "title": "Demo Mag",
            "pages": None,
            "sections": [
                {
                    "title": "Why Normies Vibe Code",
                    "text": (
                        "Why Normies Vibe Code\n\n"
                        "A full article body with several sentences for the rebuild path "
                        "so the chunk is kept as readable content for intensive reading."
                    ),
                },
                {
                    "title": "Outdoor Tools Roundup",
                    "text": (
                        "Outdoor Tools Roundup\n\n"
                        "Another article body with enough words that the rebuild writes "
                        "more than one chunk into chunks.json on disk."
                    ),
                },
            ],
        }

    monkeypatch.setattr(
        "intensive_reading.ingest.extract_book",
        _fake_extract,
    )
    meta = rebuild_magazine_from_original(str(books), bid, reindex_rag=False)
    assert meta.get("rag_status") == "stale"
    assert int(meta.get("chunk_count") or 0) >= 2
    assert int(meta.get("analyses_cleared") or 0) >= 1
    analyses = book_dir / "analyses"
    assert not analyses.is_dir() or not any(analyses.iterdir())
    chunks = json.loads((book_dir / "chunks.json").read_text(encoding="utf-8"))
    titles = [c["title"] for c in chunks]
    assert "Why Normies Vibe Code" in titles
