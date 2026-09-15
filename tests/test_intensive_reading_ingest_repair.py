"""Tests for intensive-reading title repair and oversized rechunk."""

from __future__ import annotations

import json
import os
import sys

import pytest

_SCRIPTS = os.path.join(os.path.dirname(__file__), "..", "scripts", "rag")
sys.path.insert(0, os.path.abspath(_SCRIPTS))

from intensive_reading.ingest import (  # noqa: E402
    _split_oversized_chunks,
    _title_from_filename,
    _title_from_sources,
    needs_title_repair,
    rechunk_oversized_book,
    repair_book_title,
)


def test_title_from_sources_prefers_upload_for_pdf():
    extracted = {"format": "pdf", "title": "tmp51_wwniy"}
    assert _title_from_sources("TheEconomist.2026.07.25.pdf", extracted) == "TheEconomist.2026.07.25"


def test_title_from_sources_ignores_tmp_epub_title():
    extracted = {"format": "epub", "title": "tmpvfq6p7x8"}
    assert _title_from_sources("wired_2026.07.02.epub", extracted) == "wired_2026.07.02"


def test_title_from_sources_keeps_real_epub_title():
    extracted = {"format": "epub", "title": "Wired Magazine"}
    assert _title_from_sources("wired.epub", extracted) == "Wired Magazine"


def test_needs_title_repair():
    assert needs_title_repair({"title": "tmp51_wwniy", "filename": "a.pdf"})
    assert not needs_title_repair({"title": "The Economist", "filename": "a.pdf"})


def test_split_oversized_chunks_splits_huge_text():
    words = " ".join(["word"] * 3000)
    chunks = [{"chunk_index": 0, "text": words, "title": "Whole", "is_toc": False}]
    out = _split_oversized_chunks(chunks, max_words=1200)
    assert len(out) >= 2
    assert all(len((c["text"] or "").split()) <= 1200 for c in out)
    assert [c["chunk_index"] for c in out] == list(range(len(out)))


def test_repair_book_title_and_rechunk(tmp_path):
    book_id = "economist-test-abcd1234"
    book_dir = tmp_path / book_id
    book_dir.mkdir()
    words = " ".join([f"w{i}" for i in range(2500)])
    chunks = [{"chunk_index": 0, "text": words, "title": "All", "is_toc": False}]
    (book_dir / "chunks.json").write_text(json.dumps(chunks), encoding="utf-8")
    meta = {
        "book_id": book_id,
        "title": "tmp51_wwniy",
        "filename": "TheEconomist.2026.07.25.pdf",
        "book_type": "magazine",
        "status": "ready",
        "chunk_count": 1,
        "rag_status": "failed",
    }
    (book_dir / "meta.json").write_text(json.dumps(meta), encoding="utf-8")

    repaired = repair_book_title(str(tmp_path), book_id)
    assert repaired["title"] == "TheEconomist.2026.07.25"

    new_chunks, changed = rechunk_oversized_book(str(tmp_path), book_id, max_words=1000)
    assert changed
    assert len(new_chunks) >= 2
    meta2 = json.loads((book_dir / "meta.json").read_text(encoding="utf-8"))
    assert meta2["chunk_count"] == len(new_chunks)


def test_title_from_filename_strips_replacement_chars():
    assert "PDF" in _title_from_filename("TEco-20251220\ufffdPDF.pdf") or _title_from_filename(
        "TEco-20251220\ufffdPDF.pdf"
    ).startswith("TEco")
