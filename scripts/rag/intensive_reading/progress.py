"""Book-local progress for intensive reading, with best-effort conversation memory."""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Optional


PROGRESS_KIND = "intensive_reading_progress"
logger = logging.getLogger(__name__)


def progress_text(book_id: str, title: str, chunk_index: int, total: int) -> str:
    return (
        f"Intensive reading progress: book_id={book_id} title={title} "
        f"chunk_index={chunk_index} total={total}"
    )


def _normalize_progress(raw: dict[str, Any] | None) -> Optional[dict[str, Any]]:
    if not isinstance(raw, dict) or "chunk_index" not in raw:
        return None
    return {
        "chunk_index": int(raw.get("chunk_index", 0)),
        "total": int(raw.get("total", 0)),
        "title": raw.get("title") or "",
    }


def _write_meta_progress(
    books_dir: str,
    book_id: str,
    title: str,
    chunk_index: int,
    total: int,
) -> dict[str, Any]:
    from intensive_reading.ingest import update_meta_fields

    doc = {
        "chunk_index": int(chunk_index),
        "total": int(total),
        "title": title,
        "updated_at": datetime.now().isoformat(),
    }
    meta = update_meta_fields(books_dir, book_id, {"progress": doc})
    if meta is None:
        raise FileNotFoundError(f"Book not found: {book_id}")
    return doc


def _save_memory_progress(
    book_id: str,
    title: str,
    chunk_index: int,
    total: int,
    session_id: str = "",
) -> Optional[str]:
    """Best-effort conversation-memory upsert. Returns memory id or None."""
    try:
        from memory.store import (
            MemoryEntry,
            MemoryType,
            add_memory,
            delete_memory,
            get_all_memories,
        )
    except Exception:
        logger.exception("IR progress: conversation memory import failed")
        return None

    try:
        for entry in get_all_memories(memory_type=MemoryType.FACT.value):
            meta = entry.metadata or {}
            if meta.get("kind") == PROGRESS_KIND and meta.get("book_id") == book_id:
                delete_memory(entry.id)
    except Exception:
        logger.exception("IR progress: failed to clear previous memory facts")

    entry = MemoryEntry(
        id="",
        text=progress_text(book_id, title, chunk_index, total),
        memory_type=MemoryType.FACT.value,
        timestamp=datetime.now().isoformat(),
        session_id=session_id or "",
        confidence=1.0,
        metadata={
            "kind": PROGRESS_KIND,
            "book_id": book_id,
            "title": title,
            "chunk_index": int(chunk_index),
            "total": int(total),
        },
    )
    try:
        return add_memory(entry)
    except Exception:
        logger.exception("IR progress: conversation memory write failed")
        return None


def save_progress(
    book_id: str,
    title: str,
    chunk_index: int,
    total: int,
    session_id: str = "",
    books_dir: str = "",
) -> Optional[str]:
    """Write progress to book meta.json. Best-effort memory upsert. Returns memory id or None."""
    if not books_dir:
        from config import BOOKS_ROOT
        books_dir = BOOKS_ROOT
    _write_meta_progress(books_dir, book_id, title, chunk_index, total)
    return _save_memory_progress(book_id, title, chunk_index, total, session_id=session_id)


def load_progress(book_id: str, books_dir: str = "") -> Optional[dict[str, Any]]:
    """Return {chunk_index, total, title} for book_id or None. Prefers meta.json."""
    if not books_dir:
        from config import BOOKS_ROOT
        books_dir = BOOKS_ROOT
    from intensive_reading.ingest import load_meta

    meta = load_meta(books_dir, book_id) or {}
    from_meta = _normalize_progress(meta.get("progress") if isinstance(meta, dict) else None)
    if from_meta:
        return from_meta
    return _load_memory_progress(book_id)


def _load_memory_progress(book_id: str) -> Optional[dict[str, Any]]:
    try:
        from memory.store import MemoryType, get_all_memories
    except Exception:
        return None

    try:
        matches = []
        for entry in get_all_memories(memory_type=MemoryType.FACT.value):
            meta = entry.metadata or {}
            if meta.get("kind") == PROGRESS_KIND and meta.get("book_id") == book_id:
                matches.append(entry)
        if not matches:
            return None
        matches.sort(key=lambda e: e.timestamp or "", reverse=True)
        return _normalize_progress(matches[0].metadata or {})
    except Exception:
        return None


def clear_progress(book_id: str, books_dir: str = "") -> int:
    """Delete progress from meta.json and conversation memory. Returns memory facts removed."""
    if books_dir:
        from intensive_reading.ingest import load_meta, resolve_book_dir
        import json
        import os

        meta = load_meta(books_dir, book_id)
        if meta and "progress" in meta:
            meta.pop("progress", None)
            book_dir = resolve_book_dir(books_dir, book_id)
            with open(os.path.join(book_dir, "meta.json"), "w", encoding="utf-8") as f:
                json.dump(meta, f, ensure_ascii=False, indent=2)
    try:
        from memory.store import MemoryType, delete_memory, get_all_memories
    except Exception:
        return 0
    n = 0
    try:
        for entry in get_all_memories(memory_type=MemoryType.FACT.value):
            meta = entry.metadata or {}
            if meta.get("kind") == PROGRESS_KIND and meta.get("book_id") == book_id:
                if delete_memory(entry.id):
                    n += 1
    except Exception:
        return n
    return n


def load_all_progress(books_dir: str = "") -> dict[str, dict[str, Any]]:
    """Map book_id -> progress dict. Meta.json wins over conversation memory."""
    out: dict[str, dict[str, Any]] = {}
    try:
        from memory.store import MemoryType, get_all_memories
    except Exception:
        get_all_memories = None  # type: ignore
        MemoryType = None  # type: ignore
    try:
        if get_all_memories is not None and MemoryType is not None:
            for entry in get_all_memories(memory_type=MemoryType.FACT.value):
                meta = entry.metadata or {}
                if meta.get("kind") != PROGRESS_KIND:
                    continue
                bid = meta.get("book_id")
                if not bid:
                    continue
                prev = out.get(bid)
                if prev is None or (entry.timestamp or "") >= (prev.get("_ts") or ""):
                    norm = _normalize_progress(meta)
                    if norm:
                        norm["_ts"] = entry.timestamp or ""
                        out[bid] = norm
            for v in out.values():
                v.pop("_ts", None)
    except Exception:
        pass

    if not books_dir:
        from config import BOOKS_ROOT
        books_dir = BOOKS_ROOT
    try:
        from intensive_reading.ingest import list_books
        for b in list_books(books_dir):
            bid = b.get("book_id")
            prog = _normalize_progress(b.get("progress") if isinstance(b, dict) else None)
            if bid and prog:
                out[bid] = prog
    except Exception:
        logger.exception("IR progress: failed to load meta progress")
    return out
