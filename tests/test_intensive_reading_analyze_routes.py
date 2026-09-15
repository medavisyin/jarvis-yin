"""Route-level tests for intensive-reading tabs and analysis_kind validation."""

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

from intensive_reading.prompts import KIND_VOCAB, tabs_for_book_type  # noqa: E402
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


def _write_book(books_dir: str, book_id: str, book_type: str, text: str = "Hello advanced prose.") -> None:
    path = os.path.join(books_dir, book_id)
    os.makedirs(path, exist_ok=True)
    meta = {
        "book_id": book_id,
        "title": "Test Book",
        "book_type": book_type,
        "status": "ready",
        "chunk_count": 1,
        "first_readable_index": 0,
        "rag_status": "ok",
    }
    with open(os.path.join(path, "meta.json"), "w", encoding="utf-8") as f:
        json.dump(meta, f)
    chunks = [{"chunk_index": 0, "text": text, "title": "Part 1", "is_toc": False}]
    with open(os.path.join(path, "chunks.json"), "w", encoding="utf-8") as f:
        json.dump(chunks, f)


def test_tabs_endpoint_novel(client):
    c, _ = client
    r = c.get("/api/intensive-reading/tabs?book_type=novel")
    assert r.status_code == 200
    data = r.get_json()
    ids = [t["id"] for t in data["tabs"]]
    assert ids[0] == KIND_VOCAB
    assert ids == [t["id"] for t in tabs_for_book_type("novel")]


def test_tabs_endpoint_magazine(client):
    c, _ = client
    r = c.get("/api/intensive-reading/tabs?book_type=magazine")
    assert r.status_code == 200
    ids = [t["id"] for t in r.get_json()["tabs"]]
    assert ids == [t["id"] for t in tabs_for_book_type("magazine")]


def test_analyze_rejects_cross_type_kind(client):
    c, books = client
    bid = "mag-book-abcd1234"
    _write_book(books, bid, "magazine")
    r = c.post(
        "/api/intensive-reading/analyze",
        json={"book_id": bid, "chunk_index": 0, "analysis_kind": "plot"},
    )
    assert r.status_code == 400
    body = r.get_json()
    assert "Invalid analysis_kind" in (body.get("error") or "")
    assert "plot" not in body.get("allowed", [])


def test_analyze_rejects_stance_on_novel(client):
    c, books = client
    bid = "novel-book-abcd1234"
    _write_book(books, bid, "novel")
    r = c.post(
        "/api/intensive-reading/analyze",
        json={"book_id": bid, "chunk_index": 0, "analysis_kind": "stance"},
    )
    assert r.status_code == 400


def test_analyze_rejects_bad_part(client):
    c, books = client
    bid = "novel-book-abcd1234"
    _write_book(books, bid, "novel")
    r = c.post(
        "/api/intensive-reading/analyze",
        json={"book_id": bid, "chunk_index": 0, "analysis_kind": "vocab", "part": "nope"},
    )
    assert r.status_code == 400
    assert "part" in (r.get_json().get("error") or "").lower()


def test_analyze_valid_kind_streams_with_mocked_ollama(client):
    c, books = client
    bid = "novel-book-abcd1234"
    _write_book(books, bid, "novel")

    class _FakeResp:
        status_code = 200

        def iter_lines(self):
            yield json.dumps({"message": {"content": "Item one."}}).encode()
            yield json.dumps({"message": {"content": ""}, "done": True, "done_reason": "stop"}).encode()

    with patch("routes.intensive_reading._ollama_settings", return_value=("http://localhost:9", "m")):
        with patch("requests.post", return_value=_FakeResp()):
            r = c.post(
                "/api/intensive-reading/analyze",
                json={"book_id": bid, "chunk_index": 0, "analysis_kind": "vocab"},
            )
            assert r.status_code == 200
            body = r.data.decode("utf-8")
            assert "Item one." in body
            assert "analysis_kind" in body
            assert "vocab" in body


def test_analysis_cache_get_put(client):
    c, books = client
    bid = "novel-book-abcd1234"
    _write_book(books, bid, "novel")
    r = c.get(f"/api/intensive-reading/books/{bid}/chunks/0/analysis")
    assert r.status_code == 200
    assert r.get_json()["tabs"] == {}
    r2 = c.put(
        f"/api/intensive-reading/books/{bid}/chunks/0/analysis",
        json={"kind": "vocab", "slot": {"text": "cached", "status": "done"}, "merge": True},
    )
    assert r2.status_code == 200
    r3 = c.get(f"/api/intensive-reading/books/{bid}/chunks/0/analysis")
    assert r3.get_json()["tabs"]["vocab"]["text"] == "cached"


def test_analyze_socratic_requires_notes(client):
    c, books = client
    bid = "novel-book-abcd1234"
    _write_book(books, bid, "novel")
    with patch("routes.intensive_reading._ollama_settings", return_value=("http://localhost:9", "m")):
        with patch("requests.post") as post:
            r = c.post(
                "/api/intensive-reading/analyze",
                json={"book_id": bid, "chunk_index": 0, "analysis_kind": "socratic"},
            )
            assert r.status_code == 400
            assert "learner_reflection" in (r.get_json().get("error") or "")
            r2 = c.post(
                "/api/intensive-reading/analyze",
                json={
                    "book_id": bid,
                    "chunk_index": 0,
                    "analysis_kind": "socratic",
                    "learner_reflection": "   ",
                },
            )
            assert r2.status_code == 400
            post.assert_not_called()


def test_analyze_socratic_includes_notes_in_user_message(client):
    c, books = client
    bid = "novel-book-abcd1234"
    _write_book(books, bid, "novel")
    captured = {}

    class _FakeResp:
        status_code = 200

        def iter_lines(self):
            yield json.dumps({"message": {"content": "评述。"}}).encode()
            yield json.dumps({"message": {"content": ""}, "done": True, "done_reason": "stop"}).encode()

    def _post(url, json=None, **kwargs):
        captured["json"] = json
        return _FakeResp()

    with patch("routes.intensive_reading._ollama_settings", return_value=("http://localhost:9", "m")):
        with patch("requests.post", side_effect=_post):
            r = c.post(
                "/api/intensive-reading/analyze",
                json={
                    "book_id": bid,
                    "chunk_index": 0,
                    "analysis_kind": "socratic",
                    "learner_reflection": "我觉得汤姆心虚，without looking back 用得很好。",
                },
            )
    assert r.status_code == 200
    messages = (captured.get("json") or {}).get("messages") or []
    assert len(messages) >= 2
    user = messages[1].get("content") or ""
    assert "我觉得汤姆心虚" in user
    assert "without looking back" in user
    assert "Learner's informal notes" in user
