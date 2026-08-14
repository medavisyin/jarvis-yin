"""Conversation-memory progress for intensive reading."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Optional


PROGRESS_KIND = "intensive_reading_progress"


def progress_text(book_id: str, title: str, chunk_index: int, total: int) -> str:
    return (
        f"Intensive reading progress: book_id={book_id} title={title} "
        f"chunk_index={chunk_index} total={total}"
    )


def save_progress(
    book_id: str,
    title: str,
    chunk_index: int,
    total: int,
    session_id: str = "",
) -> Optional[str]:
    """Upsert progress fact in conversation_memory. Returns memory id or None."""
    try:
        from memory.store import (
            MemoryEntry,
            MemoryType,
            add_memory,
            delete_memory,
            get_all_memories,
        )
    except Exception:
        return None

    # Remove previous progress entries for this book
    try:
        for entry in get_all_memories(memory_type=MemoryType.FACT.value):
            meta = entry.metadata or {}
            if meta.get("kind") == PROGRESS_KIND and meta.get("book_id") == book_id:
                delete_memory(entry.id)
    except Exception:
        pass

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
        return None


def load_progress(book_id: str) -> Optional[dict[str, Any]]:
    """Return {chunk_index, total, title} for book_id or None."""
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
        # Latest by timestamp
        matches.sort(key=lambda e: e.timestamp or "", reverse=True)
        meta = matches[0].metadata or {}
        return {
            "chunk_index": int(meta.get("chunk_index", 0)),
            "total": int(meta.get("total", 0)),
            "title": meta.get("title") or "",
        }
    except Exception:
        return None


def clear_progress(book_id: str) -> int:
    """Delete conversation-memory progress facts for this book. Returns count removed."""
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


def load_all_progress() -> dict[str, dict[str, Any]]:
    """Map book_id -> progress dict."""
    out: dict[str, dict[str, Any]] = {}
    try:
        from memory.store import MemoryType, get_all_memories
    except Exception:
        return out
    try:
        for entry in get_all_memories(memory_type=MemoryType.FACT.value):
            meta = entry.metadata or {}
            if meta.get("kind") != PROGRESS_KIND:
                continue
            bid = meta.get("book_id")
            if not bid:
                continue
            prev = out.get(bid)
            if prev is None or (entry.timestamp or "") >= (prev.get("_ts") or ""):
                out[bid] = {
                    "chunk_index": int(meta.get("chunk_index", 0)),
                    "total": int(meta.get("total", 0)),
                    "title": meta.get("title") or "",
                    "_ts": entry.timestamp or "",
                }
        for v in out.values():
            v.pop("_ts", None)
    except Exception:
        pass
    return out
