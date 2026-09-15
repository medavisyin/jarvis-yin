"""Unit tests for passage slicing used by intensive reading analyze-continue."""

from __future__ import annotations

import os
import sys

_RAG = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "scripts", "rag"))
if _RAG not in sys.path:
    sys.path.insert(0, _RAG)

from intensive_reading.prompts import PASSAGE_WINDOW, slice_passage  # noqa: E402


def test_slice_passage_short_has_no_more():
    text = "Short passage."
    excerpt, nxt, more = slice_passage(text, 0, PASSAGE_WINDOW)
    assert excerpt == text
    assert more is False
    assert nxt == len(text)


def test_slice_passage_continue_covers_remainder():
    text = ("Paragraph one.\n\n" * 800) + "END_MARKER"
    first, nxt, more = slice_passage(text, 0, 200)
    assert more is True
    assert len(first) <= 200
    second, nxt2, more2 = slice_passage(text, nxt, 20000)
    assert "END_MARKER" in (first + second)
    assert more2 is False or nxt2 >= len(text) - 5
