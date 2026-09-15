"""Tests for intensive reading security and ingest edge cases."""

from __future__ import annotations

import os
import sys

import pytest

_RAG = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "scripts", "rag"))
if _RAG not in sys.path:
    sys.path.insert(0, _RAG)

from intensive_reading.ingest import (  # noqa: E402
    InvalidBookId,
    resolve_book_dir,
    is_valid_book_id,
)


def test_valid_book_id_accepts_generated_form():
    assert is_valid_book_id("smoke-book-bd5bde8c") is True
    assert is_valid_book_id("the-economist-2024-01-aabbccdd") is True


def test_invalid_book_id_rejects_traversal():
    for bad in ("..", "../x", "..\\x", "a/b", "a\\b", "foo/../bar", "", "has spaces", "UPPER"):
        assert is_valid_book_id(bad) is False


def test_resolve_book_dir_rejects_escape(tmp_path):
    books = tmp_path / "books"
    books.mkdir()
    with pytest.raises(InvalidBookId):
        resolve_book_dir(str(books), "..")
    with pytest.raises(InvalidBookId):
        resolve_book_dir(str(books), "../outside")


def test_resolve_book_dir_accepts_safe_id(tmp_path):
    books = tmp_path / "books"
    books.mkdir()
    d = resolve_book_dir(str(books), "my-book-abcd1234")
    assert os.path.realpath(d).startswith(os.path.realpath(str(books)))
    assert os.path.basename(d) == "my-book-abcd1234"
