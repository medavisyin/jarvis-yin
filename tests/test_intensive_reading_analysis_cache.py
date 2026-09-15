"""Tests for intensive-reading analysis cache persistence."""

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

from web_api import Flask  # noqa: E402
from unittest.mock import patch  # noqa: E402

from intensive_reading.analysis_cache import (  # noqa: E402
    load_chunk_analysis,
    normalize_slot,
    save_chunk_analysis,
)
from routes.intensive_reading import intensive_reading_bp  # noqa: E402


def test_normalize_slot_strips_running_with_text():
    s = normalize_slot({"text": "hi", "status": "running", "hasMore": 1})
    assert s["status"] == "done"
    assert s["hasMore"] is True
    assert s["text"] == "hi"


def test_normalize_slot_empty_running_becomes_idle():
    s = normalize_slot({"text": "", "status": "running"})
    assert s["status"] == "idle"


def test_normalize_slot_keeps_learner_level_and_lang():
    s = normalize_slot({
        "text": "词",
        "status": "done",
        "learner_level": "high_school",
        "output_lang": "zh",
    })
    assert s["learner_level"] == "high_school"
    assert s["output_lang"] == "zh"


def test_normalize_slot_keeps_reflection():
    s = normalize_slot({
        "text": "评述正文",
        "status": "done",
        "reflection": "这一章让我觉得汤姆有点心虚。",
    })
    assert s["reflection"] == "这一章让我觉得汤姆有点心虚。"
    empty = normalize_slot({})
    assert empty["reflection"] == ""


def test_save_roundtrip_reflection(tmp_path):
    books = tmp_path / "books"
    bid = "cache-book-abcd1234"
    book_dir = books / bid
    book_dir.mkdir(parents=True)
    (book_dir / "meta.json").write_text(
        json.dumps({"book_id": bid, "status": "ready"}), encoding="utf-8"
    )
    save_chunk_analysis(
        str(books),
        bid,
        0,
        {
            "socratic": {
                "text": "评述",
                "status": "done",
                "reflection": "我觉得汤姆心虚。",
            }
        },
        merge=True,
    )
    loaded = load_chunk_analysis(str(books), bid, 0)
    assert loaded["tabs"]["socratic"]["reflection"] == "我觉得汤姆心虚。"
    assert loaded["tabs"]["socratic"]["text"] == "评述"
    save_chunk_analysis(
        str(books),
        bid,
        0,
        {"socratic": {"text": "评述2", "status": "done"}},
        merge=True,
    )
    loaded2 = load_chunk_analysis(str(books), bid, 0)
    assert loaded2["tabs"]["socratic"]["text"] == "评述2"
    assert loaded2["tabs"]["socratic"]["reflection"] == ""


def test_save_and_load_merge(tmp_path):
    books = tmp_path / "books"
    bid = "cache-book-abcd1234"
    book_dir = books / bid
    book_dir.mkdir(parents=True)
    (book_dir / "meta.json").write_text(
        json.dumps({"book_id": bid, "status": "ready"}), encoding="utf-8"
    )

    doc = save_chunk_analysis(
        str(books),
        bid,
        0,
        {"vocab": {"text": "A", "status": "done", "part": 1}},
        merge=True,
    )
    assert doc["tabs"]["vocab"]["text"] == "A"
    path = book_dir / "analyses" / "0.json"
    assert path.is_file()

    save_chunk_analysis(
        str(books),
        bid,
        0,
        {"plot": {"text": "B", "status": "done"}},
        merge=True,
    )
    loaded = load_chunk_analysis(str(books), bid, 0)
    assert loaded["tabs"]["vocab"]["text"] == "A"
    assert loaded["tabs"]["plot"]["text"] == "B"


def test_merge_false_replaces_tabs(tmp_path):
    books = tmp_path / "books"
    bid = "cache-book-abcd1234"
    book_dir = books / bid
    book_dir.mkdir(parents=True)
    (book_dir / "meta.json").write_text("{}", encoding="utf-8")
    save_chunk_analysis(
        str(books), bid, 0, {"vocab": {"text": "A", "status": "done"}}, merge=True
    )
    save_chunk_analysis(
        str(books), bid, 0, {"plot": {"text": "B", "status": "done"}}, merge=False
    )
    loaded = load_chunk_analysis(str(books), bid, 0)
    assert "vocab" not in loaded["tabs"]
    assert loaded["tabs"]["plot"]["text"] == "B"


def test_invalid_kind_raises(tmp_path):
    books = tmp_path / "books"
    bid = "cache-book-abcd1234"
    (books / bid).mkdir(parents=True)
    with pytest.raises(ValueError, match="No valid tab kinds"):
        save_chunk_analysis(str(books), bid, 0, {"../x": {"text": "no"}}, merge=True)


def test_corrupt_json_returns_empty(tmp_path):
    books = tmp_path / "books"
    bid = "cache-book-abcd1234"
    adir = books / bid / "analyses"
    adir.mkdir(parents=True)
    (adir / "0.json").write_text("{not-json", encoding="utf-8")
    doc = load_chunk_analysis(str(books), bid, 0)
    assert doc["tabs"] == {}


def test_load_missing_returns_empty(tmp_path):
    books = tmp_path / "books"
    bid = "cache-book-abcd1234"
    (books / bid).mkdir(parents=True)
    doc = load_chunk_analysis(str(books), bid, 3)
    assert doc["tabs"] == {}
    assert doc["chunk_index"] == 3


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
    with open(os.path.join(path, "meta.json"), "w", encoding="utf-8") as f:
        json.dump({"book_id": book_id, "status": "ready", "book_type": "novel"}, f)
    with open(os.path.join(path, "chunks.json"), "w", encoding="utf-8") as f:
        json.dump([{"chunk_index": 0, "text": "hi", "title": "t", "is_toc": False}], f)


def test_route_invalid_book_id(client):
    c, _ = client
    r = c.get("/api/intensive-reading/books/NOT-valid-ID/chunks/0/analysis")
    assert r.status_code == 400
    r2 = c.get("/api/intensive-reading/books/has%20spaces/chunks/0/analysis")
    assert r2.status_code == 400


def test_route_missing_book_404(client):
    c, _ = client
    r = c.get("/api/intensive-reading/books/missing-book-abcd1234/chunks/0/analysis")
    assert r.status_code == 404


def test_route_put_invalid_kind_400(client):
    c, books = client
    bid = "novel-book-abcd1234"
    _write_book(books, bid)
    r = c.put(
        f"/api/intensive-reading/books/{bid}/chunks/0/analysis",
        json={"kind": "../bad", "slot": {"text": "x", "status": "done"}},
    )
    assert r.status_code == 400
