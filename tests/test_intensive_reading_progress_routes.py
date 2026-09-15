"""Regression: book list / resume / save-progress must keep in-Jarvis reading."""
from __future__ import annotations

import json
import os
import sys
from unittest.mock import patch

import pytest

_RAG = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "scripts", "rag"))
_SCRIPTS = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "scripts"))
for _p in (_SCRIPTS, _RAG):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from web_api import Flask  # noqa: E402

from routes.intensive_reading import intensive_reading_bp  # noqa: E402


@pytest.fixture()
def client(tmp_path):
    books = tmp_path / "books"
    books.mkdir()
    app = Flask(__name__)
    app.register_blueprint(intensive_reading_bp)
    app.config["TESTING"] = True
    with patch("routes.intensive_reading._books_dir", return_value=str(books)):
        yield app.test_client(), str(books)


def _write_book(books_dir: str, book_id: str) -> None:
    path = os.path.join(books_dir, book_id)
    os.makedirs(path, exist_ok=True)
    meta = {
        "book_id": book_id,
        "title": "Test Book",
        "book_type": "novel",
        "status": "ready",
        "chunk_count": 1,
        "first_readable_index": 0,
        "rag_status": "ok",
    }
    with open(os.path.join(path, "meta.json"), "w", encoding="utf-8") as f:
        json.dump(meta, f)
    chunks = [{"chunk_index": 0, "text": "Hello there.", "title": "Part 1", "is_toc": False}]
    with open(os.path.join(path, "chunks.json"), "w", encoding="utf-8") as f:
        json.dump(chunks, f)


def test_list_books_does_not_raise_undefined_progress(client):
    c, _books = client
    r = c.get("/api/intensive-reading/books")
    assert r.status_code == 200
    data = r.get_json()
    assert "books" in data
    assert "error" not in data


def test_get_book_includes_progress_field(client):
    c, books = client
    bid = "book-prog11111"
    _write_book(books, bid)
    r = c.get("/api/intensive-reading/books/" + bid)
    assert r.status_code == 200
    data = r.get_json()
    assert "progress" in data
    assert "error" not in data


def test_save_progress_persists_to_meta_when_memory_write_fails(client):
    """Next/Back must save resume position even if conversation memory is down."""
    c, books = client
    bid = "book-prog11111"
    _write_book(books, bid)
    with (
        patch("memory.store.get_all_memories", return_value=[]),
        patch("memory.store.add_memory", side_effect=RuntimeError("qdrant down")),
        patch("memory.store.delete_memory", return_value=True),
    ):
        r = c.post(
            "/api/intensive-reading/progress",
            json={"book_id": bid, "chunk_index": 3, "total": 10},
        )
    assert r.status_code == 200
    data = r.get_json()
    assert data.get("ok") is True
    assert "Failed to write conversation memory" not in (data.get("warning") or "")

    with open(os.path.join(books, bid, "meta.json"), encoding="utf-8") as f:
        meta = json.load(f)
    assert meta["progress"]["chunk_index"] == 3
    assert meta["progress"]["total"] == 10

    got = c.get("/api/intensive-reading/books/" + bid)
    assert got.status_code == 200
    assert got.get_json()["progress"]["chunk_index"] == 3

    listed = c.get("/api/intensive-reading/books")
    assert listed.status_code == 200
    row = next(b for b in listed.get_json()["books"] if b["book_id"] == bid)
    assert row["progress"]["chunk_index"] == 3
