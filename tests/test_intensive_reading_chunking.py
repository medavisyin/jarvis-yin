"""Unit tests for intensive reading chunking / TOC / EPUB helpers."""

from __future__ import annotations

import io
import zipfile
from pathlib import Path

import pytest

# Package under scripts/rag — add to path like agent.py does
import sys
import os

_RAG = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "scripts", "rag"))
if _RAG not in sys.path:
    sys.path.insert(0, _RAG)


from intensive_reading.chunking import (  # noqa: E402
    chunk_magazine_text,
    chunk_novel_pages,
    is_toc_text,
    is_weak_magazine_title,
    next_readable_index,
    normalize_magazine_section_title,
    prev_readable_index,
)
from intensive_reading.extract import extract_epub_sections  # noqa: E402


def test_is_toc_detects_table_of_contents():
    text = "Table of Contents\n\nChapter 1 .......... 1\nChapter 2 .......... 12\n"
    assert is_toc_text(text) is True


def test_is_toc_rejects_normal_prose():
    text = (
        "It was the best of times, it was the worst of times, "
        "it was the age of wisdom, it was the age of foolishness."
    )
    assert is_toc_text(text) is False


def test_normalize_strips_wired_nav_chrome():
    raw = "How Is Kalshi Not Gambling? | WIRED | Next | Section menu | Main menu | Previous |"
    cleaned = normalize_magazine_section_title(raw)
    assert cleaned == "How Is Kalshi Not Gambling? | WIRED"
    assert is_weak_magazine_title(raw) is False
    assert is_weak_magazine_title("Topic A | Topic B | Topic C") is True


def test_chunk_novel_pages_groups_by_two():
    pages = [f"Page {i} content with enough words to matter." for i in range(5)]
    chunks = chunk_novel_pages(pages, pages_per_chunk=2)
    assert len(chunks) == 3  # 0-1, 2-3, 4
    assert "Page 0" in chunks[0]["text"] and "Page 1" in chunks[0]["text"]
    assert chunks[0]["is_toc"] is False
    assert chunks[0]["chunk_index"] == 0


def test_chunk_novel_marks_toc_chunk():
    pages = [
        "Contents\nChapter One ..... 1\nChapter Two ..... 20\n",
        "Once upon a time there was a curious traveller in a far country.",
    ]
    chunks = chunk_novel_pages(pages, pages_per_chunk=1)
    assert chunks[0]["is_toc"] is True
    assert chunks[1]["is_toc"] is False


def test_next_readable_index_skips_toc():
    chunks = [
        {"chunk_index": 0, "is_toc": True},
        {"chunk_index": 1, "is_toc": True},
        {"chunk_index": 2, "is_toc": False},
    ]
    assert next_readable_index(chunks, start=0) == 2
    assert next_readable_index(chunks, start=2) == 2
    assert next_readable_index(chunks, start=3) is None


def test_prev_readable_index_skips_toc():
    chunks = [
        {"chunk_index": 0, "is_toc": True},
        {"chunk_index": 1, "is_toc": False},
        {"chunk_index": 2, "is_toc": True},
        {"chunk_index": 3, "is_toc": False},
    ]
    assert prev_readable_index(chunks, before=3) == 1
    assert prev_readable_index(chunks, before=1) is None
    assert prev_readable_index(chunks, before=0) is None


def test_chunk_magazine_splits_on_article_headings():
    text = (
        "Leaders\n\n"
        "Something Must Be Done\n\n"
        "The first article body goes here with enough prose for a magazine piece. "
        "It continues across several sentences to look like a real article.\n\n"
        "Finance & economics\n\n"
        "Rates Stay Higher for Longer\n\n"
        "The second article discusses interest rates and bond markets in detail. "
        "Central banks remain cautious amid sticky inflation data worldwide.\n"
    )
    chunks = chunk_magazine_text(text)
    assert len(chunks) >= 2
    assert any("first article" in c["text"].lower() for c in chunks)
    assert any("interest rates" in c["text"].lower() for c in chunks)


def _make_minimal_epub(path: Path) -> None:
    """Write a minimal EPUB 2 zip that extract_epub_sections can read."""
    container = (
        '<?xml version="1.0"?>\n'
        '<container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">'
        "<rootfiles>"
        '<rootfile full-path="OEBPS/content.opf" media-type="application/oebps-package+xml"/>'
        "</rootfiles></container>"
    )
    opf = (
        '<?xml version="1.0"?>\n'
        '<package xmlns="http://www.idpf.org/2007/opf" unique-identifier="uid" version="2.0">'
        "<metadata xmlns:dc=\"http://purl.org/dc/elements/1.1/\">"
        "<dc:title>Sample Novel</dc:title>"
        "<dc:identifier id=\"uid\">urn:test:1</dc:identifier>"
        "</metadata>"
        "<manifest>"
        '<item id="c1" href="chap1.xhtml" media-type="application/xhtml+xml"/>'
        '<item id="c2" href="chap2.xhtml" media-type="application/xhtml+xml"/>'
        '<item id="ncx" href="toc.ncx" media-type="application/x-dtbncx+xml"/>'
        "</manifest>"
        '<spine toc="ncx">'
        '<itemref idref="c1"/><itemref idref="c2"/>'
        "</spine></package>"
    )
    chap1 = (
        '<?xml version="1.0" encoding="utf-8"?>'
        '<html xmlns="http://www.w3.org/1999/xhtml"><body>'
        "<h1>Chapter One</h1>"
        "<p>The morning light spilled across the harbour as the ship prepared to sail.</p>"
        "</body></html>"
    )
    chap2 = (
        '<?xml version="1.0" encoding="utf-8"?>'
        '<html xmlns="http://www.w3.org/1999/xhtml"><body>'
        "<h1>Chapter Two</h1>"
        "<p>By nightfall the crew had charted a course toward unfamiliar waters.</p>"
        "</body></html>"
    )
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr("mimetype", "application/epub+zip", compress_type=zipfile.ZIP_STORED)
        zf.writestr("META-INF/container.xml", container)
        zf.writestr("OEBPS/content.opf", opf)
        zf.writestr("OEBPS/chap1.xhtml", chap1)
        zf.writestr("OEBPS/chap2.xhtml", chap2)


def test_extract_epub_sections(tmp_path: Path):
    epub_path = tmp_path / "sample.epub"
    _make_minimal_epub(epub_path)
    sections = extract_epub_sections(str(epub_path))
    assert len(sections) == 2
    assert "harbour" in sections[0]["text"].lower()
    assert "charted a course" in sections[1]["text"].lower()
    assert sections[0].get("title")


def test_extract_epub_allows_large_cover_image(tmp_path: Path):
    """Cover images often exceed 2MB; they must not block text extraction."""
    epub_path = tmp_path / "cover_book.epub"
    container = (
        '<?xml version="1.0"?>'
        '<container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">'
        "<rootfiles>"
        '<rootfile full-path="OEBPS/content.opf" media-type="application/oebps-package+xml"/>'
        "</rootfiles></container>"
    )
    opf = (
        '<?xml version="1.0"?>'
        '<package xmlns="http://www.idpf.org/2007/opf" unique-identifier="uid" version="2.0">'
        '<metadata xmlns:dc="http://purl.org/dc/elements/1.1/">'
        "<dc:title>Cover Book</dc:title>"
        '<dc:identifier id="uid">urn:cover</dc:identifier></metadata>'
        "<manifest>"
        '<item id="c1" href="chap1.xhtml" media-type="application/xhtml+xml"/>'
        '<item id="cover" href="images/cover.jpg" media-type="image/jpeg"/>'
        "</manifest>"
        '<spine><itemref idref="c1"/></spine></package>'
    )
    chap = (
        '<?xml version="1.0"?>'
        '<html xmlns="http://www.w3.org/1999/xhtml"><body>'
        "<h1>Chapter</h1><p>Readable prose about the voyage continues here.</p>"
        "</body></html>"
    )
    # ~2.4 MiB fake JPEG payload (matches the user failure size class)
    big_jpg = b"\xff\xd8\xff" + (b"\x00" * 2_480_000)
    with zipfile.ZipFile(epub_path, "w") as zf:
        zf.writestr("mimetype", "application/epub+zip", compress_type=zipfile.ZIP_STORED)
        zf.writestr("META-INF/container.xml", container)
        zf.writestr("OEBPS/content.opf", opf)
        zf.writestr("OEBPS/chap1.xhtml", chap)
        zf.writestr("OEBPS/images/cover.jpg", big_jpg)

    sections = extract_epub_sections(str(epub_path))
    assert len(sections) == 1
    assert "voyage" in sections[0]["text"].lower()


def test_all_toc_book_status(tmp_path: Path):
    from intensive_reading.ingest import save_book_files

    # Minimal PDF-like path is heavy; use EPUB with TOC-only text
    epub_path = tmp_path / "toc.epub"
    container = (
        '<?xml version="1.0"?>'
        '<container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">'
        "<rootfiles>"
        '<rootfile full-path="OEBPS/content.opf" media-type="application/oebps-package+xml"/>'
        "</rootfiles></container>"
    )
    opf = (
        '<?xml version="1.0"?>'
        '<package xmlns="http://www.idpf.org/2007/opf" unique-identifier="uid" version="2.0">'
        '<metadata xmlns:dc="http://purl.org/dc/elements/1.1/">'
        "<dc:title>TOC Only</dc:title>"
        '<dc:identifier id="uid">urn:toc</dc:identifier></metadata>'
        "<manifest>"
        '<item id="c1" href="c1.xhtml" media-type="application/xhtml+xml"/>'
        "</manifest><spine><itemref idref=\"c1\"/></spine></package>"
    )
    chap = (
        '<?xml version="1.0"?>'
        '<html xmlns="http://www.w3.org/1999/xhtml"><body>'
        "<h1>Table of Contents</h1>"
        "<p>Chapter 1 .......... 1</p>"
        "<p>Chapter 2 .......... 12</p>"
        "<p>Chapter 3 .......... 40</p>"
        "</body></html>"
    )
    with zipfile.ZipFile(epub_path, "w") as zf:
        zf.writestr("mimetype", "application/epub+zip", compress_type=zipfile.ZIP_STORED)
        zf.writestr("META-INF/container.xml", container)
        zf.writestr("OEBPS/content.opf", opf)
        zf.writestr("OEBPS/c1.xhtml", chap)

    books_dir = tmp_path / "books"
    books_dir.mkdir()
    meta = save_book_files(str(books_dir), str(epub_path), "novel", "toc.epub")
    assert meta["status"] == "no_readable_content"
    assert meta.get("first_readable_index") is None


def test_retriever_excludes_intensive_reading_progress():
    from memory.store import MemoryEntry
    from memory.retriever import _filter_memories

    keep = MemoryEntry(
        id="1",
        text="User prefers concise answers",
        memory_type="fact",
        timestamp="2026-01-01",
        metadata={},
    )
    drop = MemoryEntry(
        id="2",
        text="Intensive reading progress: book_id=x chunk_index=3",
        memory_type="fact",
        timestamp="2026-01-02",
        metadata={"kind": "intensive_reading_progress", "book_id": "x"},
    )
    filtered = _filter_memories([keep, drop])
    assert len(filtered) == 1
    assert filtered[0].id == "1"
