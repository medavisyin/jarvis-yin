"""Magazine TOC: PDF outline chunking + page-heading fallback."""

from __future__ import annotations

import os
import sys

_RAG = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "scripts", "rag"))
_SCRIPTS = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "scripts"))
for _p in (_SCRIPTS, _RAG):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from intensive_reading.chunking import (  # noqa: E402
    chunk_magazine_by_page_headings,
    chunk_magazine_from_outline,
)
from intensive_reading.ingest import BOOK_TYPE_MAGAZINE, build_chunks  # noqa: E402


def test_chunk_magazine_from_outline_uses_bookmark_titles_and_page_bounds():
    pages = [
        "cover page filler " * 20,
        "Politics section intro " * 30,
        "Business section intro " * 30,
        "When voters stop counting disaster beckons. " * 40,
        "Saudi deal risks proliferation. " * 40,
    ]
    outline = [
        {"title": "Politics", "page": 1, "level": 0},
        {"title": "Business", "page": 2, "level": 0},
        {
            "title": "When a president stops pretending that voters count, disaster beckons",
            "page": 3,
            "level": 0,
        },
        {
            "title": "Donald Trump’s Saudi deal risks nuclear proliferation",
            "page": 4,
            "level": 0,
        },
    ]
    chunks = chunk_magazine_from_outline(pages, outline)
    titles = [c["title"] for c in chunks]
    assert "When a president stops pretending that voters count, disaster beckons" in titles
    assert "Donald Trump’s Saudi deal risks nuclear proliferation" in titles
    saudi = next(
        c
        for c in chunks
        if "Saudi" in (c.get("title") or "")
    )
    assert "proliferation" in (saudi.get("text") or "").lower()
    assert "voters count" not in (saudi.get("text") or "").lower()


def test_chunk_magazine_by_page_headings_detects_article_starts():
    pages = [
        "THE NEW YORKER, MARCH 2, 2026\n\nMasthead only " * 10,
        (
            "THE NEW YORKER, MARCH 2, 2026\n\n"
            "Cash and Carry\n\n"
            + ("New York for richer or poorer body text. " * 40)
        ),
        (
            "THE NEW YORKER, MARCH 2, 2026\n\n"
            "Into the Woods\n\n"
            + ("Migrants traversing an ancient forest body text. " * 40)
        ),
    ]
    chunks = chunk_magazine_by_page_headings(pages)
    titles = [c["title"] for c in chunks]
    assert any("Cash and Carry" in t for t in titles)
    assert any("Into the Woods" in t for t in titles)


def test_chunk_magazine_by_page_headings_uses_contributors_page_map():
    pages = [""] * 20
    pages[2] = (
        "PERSONAL HISTORY David Sedaris 12 Cash and Carry New York, for richer or poorer. "
        "LETTER FROM POLAND Elizabeth Flock 15 Into the Woods The migrants traversing."
    )
    pages[3] = (
        'CONTRIBUTORS David Sedaris (“Cash and Carry,” p. 1 2 ) has been writing. '
        'Elizabeth Flock (“Into the Woods,” p. 1 5 ) is the author. '
        'Rachel Aviv (“A Family Trial,” p. 2 4 ) is a staff writer.'
    )
    pages[13] = "12 THE NEW YORKER, MARCH 2, 2026 PERSONAL HISTORY CASH AND CARRY " + (
        "Body of cash and carry article. " * 40
    )
    pages[16] = "THE NEW YORKER, MARCH 2, 2026 15 LETTER FROM POLAND INTO THE WOODS " + (
        "Body of into the woods article. " * 40
    )
    pages[19] = "THE NEW YORKER, MARCH 2, 2026 24 A Family Trial " + (
        "Body of family trial article. " * 40
    )
    chunks = chunk_magazine_by_page_headings(pages)
    titles = [c["title"] for c in chunks]
    assert "Cash and Carry" in titles
    assert "Into the Woods" in titles
    assert "A Family Trial" in titles
    cash = next(c for c in chunks if c["title"] == "Cash and Carry")
    woods = next(c for c in chunks if c["title"] == "Into the Woods")
    assert "cash and carry" in cash["text"].lower()
    assert "into the woods" in woods["text"].lower()
    assert cash["start_page"] == 13
    assert woods["start_page"] == 16


def test_build_chunks_pdf_prefers_outline_when_present():
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
