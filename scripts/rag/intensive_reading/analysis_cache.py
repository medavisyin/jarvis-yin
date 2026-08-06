"""Persist per-chunk intensive-reading analysis tabs under docs/books/{id}/analyses/."""

from __future__ import annotations

import json
import os
from datetime import datetime
from typing import Any

from intensive_reading.ingest import InvalidBookId, resolve_book_dir


def _analyses_dir(books_dir: str, book_id: str) -> str:
    book_dir = resolve_book_dir(books_dir, book_id)
    return os.path.join(book_dir, "analyses")


def _analysis_path(books_dir: str, book_id: str, chunk_index: int) -> str:
    if int(chunk_index) < 0:
        raise ValueError("chunk_index must be >= 0")
    return os.path.join(_analyses_dir(books_dir, book_id), f"{int(chunk_index)}.json")


def empty_slot() -> dict[str, Any]:
    return {
        "text": "",
        "status": "idle",
        "offset": 0,
        "part": 1,
        "hasMore": False,
        "genTrunc": False,
        "lastOffset": 0,
        "error": "",
    }


def normalize_slot(raw: Any) -> dict[str, Any]:
    base = empty_slot()
    if not isinstance(raw, dict):
        return base
    out = dict(base)
    if "text" in raw:
        out["text"] = str(raw.get("text") or "")
    if "status" in raw:
        st = str(raw.get("status") or "idle")
        out["status"] = st if st in ("idle", "running", "done", "error") else "idle"
    for key, cast in (
        ("offset", int),
        ("part", int),
        ("lastOffset", int),
    ):
        if key in raw:
            try:
                out[key] = cast(raw[key])
            except (TypeError, ValueError):
                pass
    for key in ("hasMore", "genTrunc"):
        if key in raw:
            out[key] = bool(raw[key])
    if "error" in raw:
        out["error"] = str(raw.get("error") or "")
    # Never persist "running" across sessions
    if out["status"] == "running":
        out["status"] = "idle" if not out["text"] else "done"
    return out


def load_chunk_analysis(
    books_dir: str,
    book_id: str,
    chunk_index: int,
) -> dict[str, Any]:
    """Return analysis document; missing file yields empty tabs."""
    try:
        path = _analysis_path(books_dir, book_id, chunk_index)
    except (InvalidBookId, ValueError):
        raise
    empty = {
        "book_id": book_id,
        "chunk_index": int(chunk_index),
        "updated_at": None,
        "tabs": {},
    }
    if not os.path.isfile(path):
        return empty
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError):
        return empty
    tabs_in = data.get("tabs") if isinstance(data, dict) else {}
    tabs: dict[str, Any] = {}
    if isinstance(tabs_in, dict):
        for kind, slot in tabs_in.items():
            if not isinstance(kind, str) or not kind:
                continue
            tabs[kind] = normalize_slot(slot)
    return {
        "book_id": book_id,
        "chunk_index": int(chunk_index),
        "updated_at": data.get("updated_at") if isinstance(data, dict) else None,
        "tabs": tabs,
    }


def save_chunk_analysis(
    books_dir: str,
    book_id: str,
    chunk_index: int,
    tabs: dict[str, Any],
    *,
    merge: bool = True,
) -> dict[str, Any]:
    """
    Persist analysis tabs for a chunk.

    If merge=True, update only provided kinds on top of existing file.
    """
    path = _analysis_path(books_dir, book_id, chunk_index)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    existing = load_chunk_analysis(books_dir, book_id, chunk_index) if merge else {
        "book_id": book_id,
        "chunk_index": int(chunk_index),
        "tabs": {},
    }
    out_tabs = dict(existing.get("tabs") or {})
    if not isinstance(tabs, dict):
        raise ValueError("tabs must be an object")
    applied = 0
    skipped = 0
    for kind, slot in tabs.items():
        if not isinstance(kind, str) or not kind or "/" in kind or "\\" in kind:
            skipped += 1
            continue
        out_tabs[kind] = normalize_slot(slot)
        applied += 1
    if applied == 0:
        raise ValueError(
            "No valid tab kinds to save"
            + (f" ({skipped} invalid)" if skipped else "")
        )
    doc = {
        "book_id": book_id,
        "chunk_index": int(chunk_index),
        "updated_at": datetime.now().isoformat(),
        "tabs": out_tabs,
    }
    tmp = f"{path}.tmp-{os.getpid()}"
    try:
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(doc, f, ensure_ascii=False, indent=2)
        os.replace(tmp, path)
    except Exception:
        try:
            if os.path.isfile(tmp):
                os.unlink(tmp)
        except OSError:
            pass
        raise
    return doc


def clear_book_analyses(books_dir: str, book_id: str) -> int:
    """Delete all per-chunk analysis JSON files for a book. Returns files removed."""
    analyses = _analyses_dir(books_dir, book_id)
    if not os.path.isdir(analyses):
        return 0
    removed = 0
    for name in os.listdir(analyses):
        path = os.path.join(analyses, name)
        if not os.path.isfile(path):
            continue
        if not name.endswith(".json"):
            continue
        try:
            os.unlink(path)
            removed += 1
        except OSError:
            continue
    return removed
