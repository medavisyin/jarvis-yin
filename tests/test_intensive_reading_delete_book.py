"""TDD: delete an intensive-reading book (local dir + RAG vectors)."""

from __future__ import annotations

import json
import os
import sys
import types
from unittest.mock import MagicMock, patch

import pytest

_RAG = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "scripts", "rag"))
_SCRIPTS = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "scripts"))
for _p in (_SCRIPTS, _RAG):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from web_api import Flask  # noqa: E402

from intensive_reading.ingest import (  # noqa: E402
    InvalidBookId,
    _remove_book_from_snapshot,
    delete_book,
    unindex_book_from_rag,
)
from routes.intensive_reading import intensive_reading_bp  # noqa: E402


def _write_book(books_dir: str, book_id: str) -> str:
    path = os.path.join(books_dir, book_id)
    os.makedirs(os.path.join(path, "analyses"), exist_ok=True)
    with open(os.path.join(path, "meta.json"), "w", encoding="utf-8") as f:
        json.dump(
            {
                "book_id": book_id,
                "title": "new_yorker.2026.08.10",
                "book_type": "magazine",
                "status": "ready",
                "chunk_count": 1,
                "rag_status": "ok",
            },
            f,
        )
    with open(os.path.join(path, "chunks.json"), "w", encoding="utf-8") as f:
        json.dump([{"chunk_index": 0, "text": "Hello.", "title": "Goings On"}], f)
    with open(os.path.join(path, "analyses", "1.json"), "w", encoding="utf-8") as f:
        json.dump({"tabs": {}}, f)
    return path


def test_remove_book_from_snapshot_drops_only_that_book(tmp_path):
    snap = tmp_path / ".rag-store.json"
    snap.write_text(
        json.dumps(
            {
                "collection": "ai_briefings",
                "points": [
                    {
                        "id": "keep-ir",
                        "payload": {
                            "source": "intensive_reading",
                            "book_id": "keep-book-abcd1234",
                        },
                    },
                    {
                        "id": "gone-ir",
                        "payload": {
                            "source": "intensive_reading",
                            "book_id": "gone-book-abcd1234",
                        },
                    },
                    {
                        "id": "news",
                        "payload": {"source": "news", "book_id": "gone-book-abcd1234"},
                    },
                ],
            }
        ),
        encoding="utf-8",
    )
    n = _remove_book_from_snapshot(str(snap), "gone-book-abcd1234")
    assert n == 1
    data = json.loads(snap.read_text(encoding="utf-8"))
    ids = [p["id"] for p in data["points"]]
    assert ids == ["keep-ir", "news"]


def test_delete_book_removes_local_directory(tmp_path):
    books = str(tmp_path / "books")
    bid = "newyorker20260810-8355ce99"
    path = _write_book(books, bid)
    with patch("intensive_reading.ingest.unindex_book_from_rag", return_value=""):
        with patch("intensive_reading.progress.clear_progress"):
            result = delete_book(books, bid)
    assert result["ok"] is True
    assert result["book_id"] == bid
    assert result.get("rag_error") in ("", None)
    assert not os.path.exists(path)


def test_delete_book_still_removes_local_if_rag_fails(tmp_path):
    books = str(tmp_path / "books")
    bid = "theeconomist20260815-f16c6660"
    path = _write_book(books, bid)
    with patch(
        "intensive_reading.ingest.unindex_book_from_rag",
        return_value="qdrant unreachable",
    ):
        with patch("intensive_reading.progress.clear_progress"):
            result = delete_book(books, bid)
    assert result["ok"] is True
    assert "qdrant" in (result.get("rag_error") or "")
    assert not os.path.exists(path)


def test_delete_book_rejects_invalid_id(tmp_path):
    with pytest.raises(InvalidBookId):
        delete_book(str(tmp_path), "../escape")


def test_delete_book_missing_raises(tmp_path):
    with pytest.raises(FileNotFoundError):
        delete_book(str(tmp_path / "books"), "missing-book-abcd1234")


@pytest.fixture()
def client(tmp_path):
    books = tmp_path / "books"
    books.mkdir()
    app = Flask(__name__)
    app.register_blueprint(intensive_reading_bp)
    app.config["TESTING"] = True
    with patch("routes.intensive_reading._books_dir", return_value=str(books)):
        yield app.test_client(), str(books)


def test_api_delete_book_removes_dir_and_list_entry(client):
    c, books = client
    bid = "newyorker20260810-8355ce99"
    _write_book(books, bid)
    with patch("intensive_reading.ingest.unindex_book_from_rag", return_value=""):
        with patch("intensive_reading.progress.clear_progress"):
            r = c.delete(f"/api/intensive-reading/books/{bid}")
    assert r.status_code == 200
    body = r.get_json()
    assert body.get("ok") is True
    assert not os.path.isdir(os.path.join(books, bid))
    listed = c.get("/api/intensive-reading/books")
    ids = [b.get("book_id") for b in (listed.get_json() or {}).get("books") or []]
    assert bid not in ids


def test_api_delete_book_not_found(client):
    c, _ = client
    r = c.delete("/api/intensive-reading/books/missing-book-abcd1234")
    assert r.status_code == 404


def test_api_delete_book_invalid_id(client):
    c, _ = client
    r = c.delete("/api/intensive-reading/books/not%20valid")
    assert r.status_code == 400


def test_api_delete_book_warns_when_rag_fails(client):
    c, books = client
    bid = "newyorker20260810-8355ce99"
    _write_book(books, bid)
    with patch(
        "intensive_reading.ingest.unindex_book_from_rag",
        return_value="qdrant unreachable",
    ):
        with patch("intensive_reading.progress.clear_progress"):
            r = c.delete(f"/api/intensive-reading/books/{bid}")
    assert r.status_code == 200
    body = r.get_json()
    assert body.get("ok") is True
    assert "warning" in body
    assert "qdrant" in (body.get("warning") or "").lower() or "qdrant" in (
        (body.get("book") or {}).get("rag_error") or ""
    )
    assert not os.path.isdir(os.path.join(books, bid))


def test_remove_book_from_snapshot_corrupt_raises(tmp_path):
    snap = tmp_path / ".rag-store.json"
    snap.write_text("not-json{{{", encoding="utf-8")
    with pytest.raises(Exception):
        _remove_book_from_snapshot(str(snap), "gone-book-abcd1234")


def test_unindex_scroll_filter_deletes_ids_and_prunes_cache(tmp_path):
    bid = "gone-book-abcd1234"
    snap = tmp_path / ".rag-store.json"
    snap.write_text(json.dumps({"points": []}), encoding="utf-8")

    fake_client = MagicMock()
    gone = MagicMock()
    gone.id = "pt-gone"
    fake_client.scroll.return_value = ([gone], None)

    fake_re = types.ModuleType("rag_engine")
    fake_re._qdrant_points = [
        {"id": "pt-gone", "payload": {"source": "intensive_reading", "book_id": bid}},
        {"id": "pt-keep", "payload": {"source": "intensive_reading", "book_id": "keep-book-abcd1234"}},
    ]

    with patch(
        "intensive_reading.ingest._import_rag_index_deps",
        return_value=("ai_briefings", lambda: None, lambda: fake_client, str(snap)),
    ):
        with patch.dict(sys.modules, {"rag_engine": fake_re}):
            err = unindex_book_from_rag(bid)

    assert err == ""
    fake_client.delete.assert_called_once()
    selector = fake_client.delete.call_args.kwargs.get("points_selector")
    assert selector == ["pt-gone"]
    filt = fake_client.scroll.call_args.kwargs.get("scroll_filter")
    assert filt is not None
    cache_ids = [p["id"] for p in fake_re._qdrant_points]
    assert cache_ids == ["pt-keep"]


def test_unindex_prunes_snapshot_when_qdrant_fails(tmp_path):
    bid = "gone-book-abcd1234"
    snap = tmp_path / ".rag-store.json"
    snap.write_text(
        json.dumps(
            {
                "points": [
                    {
                        "id": "gone-ir",
                        "payload": {
                            "source": "intensive_reading",
                            "book_id": bid,
                        },
                    },
                    {
                        "id": "keep-ir",
                        "payload": {
                            "source": "intensive_reading",
                            "book_id": "keep-book-abcd1234",
                        },
                    },
                ]
            }
        ),
        encoding="utf-8",
    )
    fake_client = MagicMock()
    fake_client.scroll.side_effect = RuntimeError("qdrant down")
    fake_re = types.ModuleType("rag_engine")
    fake_re._qdrant_points = [
        {"id": "gone-ir", "payload": {"source": "intensive_reading", "book_id": bid}},
    ]
    with patch(
        "intensive_reading.ingest._import_rag_index_deps",
        return_value=("ai_briefings", lambda: None, lambda: fake_client, str(snap)),
    ):
        with patch.dict(sys.modules, {"rag_engine": fake_re}):
            err = unindex_book_from_rag(bid)
    assert "qdrant" in err.lower()
    data = json.loads(snap.read_text(encoding="utf-8"))
    ids = [p["id"] for p in data["points"]]
    assert "gone-ir" not in ids
    assert "keep-ir" in ids
    assert fake_re._qdrant_points == []
