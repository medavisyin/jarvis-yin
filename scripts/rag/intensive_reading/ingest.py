"""Book ingest: save files, chunk, persist chunks.json, index into Qdrant."""

from __future__ import annotations

import importlib.util
import json
import os
import re
import shutil
import sys
import time
import uuid
from datetime import date, datetime
from typing import Any, Optional

from intensive_reading.chunking import (
    chunk_by_words,
    chunk_magazine_by_page_headings,
    chunk_magazine_from_outline,
    chunk_magazine_text,
    chunk_novel_from_outline,
    chunk_novel_pages,
    is_toc_text,
    is_weak_magazine_title,
    next_readable_index,
    normalize_magazine_section_title,
    outline_from_novel_contents,
)
from intensive_reading.extract import extract_book

BOOK_TYPE_NOVEL = "novel"
BOOK_TYPE_MAGAZINE = "magazine"

# Generated IDs are ascii slug + 8 hex chars. Reject anything with path separators.
_BOOK_ID_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")


class InvalidBookId(ValueError):
    """Raised when book_id is missing, malformed, or escapes books_dir."""


def books_root(jarvis_root: str) -> str:
    return os.path.join(jarvis_root, "docs", "books")


def is_valid_book_id(book_id: str) -> bool:
    if not book_id or not isinstance(book_id, str):
        return False
    if len(book_id) > 120:
        return False
    if any(ch in book_id for ch in ("/", "\\", "\0", ".")):
        return False
    if ".." in book_id or book_id in (".", ".."):
        return False
    return bool(_BOOK_ID_RE.match(book_id))


def resolve_book_dir(books_dir: str, book_id: str) -> str:
    """Return absolute book directory path, or raise InvalidBookId."""
    if not is_valid_book_id(book_id):
        raise InvalidBookId(f"Invalid book_id: {book_id!r}")
    root = os.path.realpath(books_dir)
    candidate = os.path.realpath(os.path.join(root, book_id))
    # Ensure candidate is root or a subpath of root (with separator guard)
    if candidate != root and not candidate.startswith(root + os.sep):
        raise InvalidBookId(f"book_id escapes books dir: {book_id!r}")
    return candidate


def _slugify(name: str) -> str:
    import unicodedata

    s = unicodedata.normalize("NFKD", name or "")
    s = s.encode("ascii", "ignore").decode("ascii")
    s = re.sub(r"[^a-zA-Z0-9\s\-]+", "", s)
    s = re.sub(r"[\s_]+", "-", s.strip()).strip("-").lower()
    return s[:80] or "book"


def _make_book_id(title: str) -> str:
    return f"{_slugify(title)}-{uuid.uuid4().hex[:8]}"


def _title_from_sources(original_filename: str, extracted: dict[str, Any]) -> str:
    """Prefer the uploaded filename; ignore tempfile basenames from extract_book."""
    from_upload = os.path.splitext(os.path.basename(original_filename or ""))[0].strip()
    from_upload = re.sub(r"\s+", " ", from_upload).strip() or "Untitled"
    et = (extracted.get("title") or "").strip()
    et = re.sub(r"\s+", " ", et).strip()
    # PDF extract_book titles are the temp path stem (tmpXXXX) — never use those.
    if extracted.get("format") == "pdf":
        return from_upload
    if not et or re.match(r"^tmp[0-9a-z_]+$", et, re.I):
        return from_upload
    return et


def _split_text_by_max_words(text: str, max_words: int) -> list[str]:
    """Split text into pieces of at most max_words, preferring paragraph breaks."""
    text = (text or "").strip()
    if not text:
        return []
    words = text.split()
    if len(words) <= max_words:
        return [text]
    paras = re.split(r"\n\s*\n+", text)
    parts: list[str] = []
    buf: list[str] = []
    buf_words = 0
    for para in paras:
        p = para.strip()
        if not p:
            continue
        pw = len(p.split())
        if pw > max_words:
            if buf:
                parts.append("\n\n".join(buf))
                buf, buf_words = [], 0
            # Hard-split oversized paragraph by words, then rejoin with spaces
            w = p.split()
            for i in range(0, len(w), max_words):
                parts.append(" ".join(w[i : i + max_words]))
            continue
        if buf and buf_words + pw > max_words:
            parts.append("\n\n".join(buf))
            buf, buf_words = [], 0
        buf.append(p)
        buf_words += pw
    if buf:
        parts.append("\n\n".join(buf))
    return parts or [text]


def _split_oversized_chunks(
    chunks: list[dict[str, Any]],
    max_words: int = 1200,
) -> list[dict[str, Any]]:
    """Re-split any chunk that is far too large for reading/RAG."""
    if not chunks:
        return chunks
    out: list[dict[str, Any]] = []
    for c in chunks:
        text = (c.get("text") or "").strip()
        words = text.split()
        if len(words) <= max_words:
            out.append(dict(c))
            continue
        base_title = c.get("title") or "Part"
        parts = _split_text_by_max_words(text, max_words)
        for j, part in enumerate(parts):
            part_title = base_title
            if is_weak_magazine_title(base_title):
                part_title = _headline_from_text(part) or base_title
            if len(parts) > 1:
                part_title = f"{part_title} ({j + 1})"
            out.append(
                {
                    "chunk_index": 0,
                    "text": part,
                    "title": part_title,
                    "is_toc": bool(c.get("is_toc")),
                }
            )
    for i, c in enumerate(out):
        c["chunk_index"] = i
    return out


def _polish_magazine_chunk_titles(chunks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Replace weak TOC/cover titles with a headline guessed from body text."""
    out: list[dict[str, Any]] = []
    for c in chunks:
        item = dict(c)
        title = item.get("title") or ""
        suffix = ""
        m = re.search(r"\s*(\(\d+\))\s*$", title)
        if m:
            suffix = f" {m.group(1)}"
            title_core = title[: m.start()].strip()
        else:
            title_core = title
        if is_weak_magazine_title(title_core):
            better = _headline_from_text(item.get("text") or "")
            if better:
                item["title"] = better + suffix
            else:
                # Never keep PRICE/masthead as the visible title
                idx = int(item.get("chunk_index") or 0) + 1
                item["title"] = f"Article {idx}"
        out.append(item)
    return out


_AUTHOR_NUM_TITLE = re.compile(
    r"\b(?:[A-Z][a-z]+(?:\s+[A-Z][a-z.\-]+){0,4})\s+\d{1,3}\s+"
    r"([A-Z][\w'’,\-:]*"
    r"(?:\s+[\w'’,\-:]+){2,16})"
)

_NY_MASTHEAD_PREFIX = re.compile(
    r"^\d*\s*THE\s+NEW\s+YORKER,\s*[A-Z]+\s+\d{1,2},\s*\d{4}\s*",
    re.I,
)
_DATE_PRICE_PREFIX = re.compile(
    r"^[A-Z]+\s+\d{1,2},\s*\d{4}\s*PRICE\s*\$?\d+(?:\.\d+)?\s*",
    re.I,
)
_GOINGS_ON_PREFIX = re.compile(
    r"^\d*\s*GOINGS\s+ON(?:\s+[A-Z]+\s+\d{1,2}\s*[–-]\s*[A-Z]+\s+\d{1,2},\s*\d{4})?\s*",
    re.I,
)


def _strip_magazine_masthead(s: str) -> str:
    """Remove common magazine chrome from the start of a line/title probe."""
    prev = None
    out = (s or "").strip()
    while out and out != prev:
        prev = out
        out = _DATE_PRICE_PREFIX.sub("", out).strip()
        out = _NY_MASTHEAD_PREFIX.sub("", out).strip()
        out = _GOINGS_ON_PREFIX.sub("", out).strip()
    return out


def _headline_from_text(text: str) -> str:
    """Pick a plausible article headline from early body lines."""
    for ln in (text or "").splitlines():
        raw = re.sub(r"\s+", " ", ln).strip()
        if not raw or len(raw) < 10:
            continue
        s = _strip_magazine_masthead(raw)
        if not s or len(s) < 10:
            continue
        if is_weak_magazine_title(s) and len(s.split()) <= 14:
            continue
        # New Yorker / dense PDF lines: "David Sedaris 12 Cash and Carry ..."
        m = _AUTHOR_NUM_TITLE.search(s)
        if m:
            cand = m.group(1).strip(" ,;-")
            if 10 <= len(cand) <= 110 and not is_weak_magazine_title(cand):
                return cand
        if len(s) > 110:
            # Long run-on: take a short prefix after masthead strip
            words = s.split()
            if len(words) >= 5:
                probe = " ".join(words[:12]).strip(" ,;-")
                if len(probe) >= 15 and not is_weak_magazine_title(probe):
                    return probe[:100]
            continue
        if is_weak_magazine_title(s) or is_toc_text(s):
            continue
        wc = len(s.split())
        if wc < 3 or wc > 20:
            continue
        if s.endswith((",", ";", ":")):
            continue
        return s
    # Last resort: first non-masthead long line prefix
    for ln in (text or "").splitlines():
        raw = re.sub(r"\s+", " ", ln).strip()
        s = _strip_magazine_masthead(raw)
        if not s or is_weak_magazine_title(s):
            continue
        words = s.split()
        if len(words) < 5:
            continue
        probe = " ".join(words[:12]).strip(" ,;-")
        if len(probe) >= 15 and not is_weak_magazine_title(probe):
            return probe[:100]
    return ""


def _magazine_chunks_from_sections(sections: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """
    Hybrid magazine EPUB chunking:
    - One spine section ≈ one article with a strong title → keep that title.
      Long articles are only word-split into Title (1)/(2) via _split_oversized_chunks.
    - Weak/TOC spine title (multi-article blob) → split with chunk_magazine_text.
    """
    chunks: list[dict[str, Any]] = []
    for s in sections:
        text = (s.get("text") or "").strip()
        if not text:
            continue
        title = (s.get("title") or "").strip() or f"Article {len(chunks) + 1}"
        title = normalize_magazine_section_title(title) or f"Article {len(chunks) + 1}"
        words = len(text.split())
        weak = is_weak_magazine_title(title) or is_toc_text(text)
        should_split = weak
        if should_split and words >= 60:
            sub = chunk_magazine_text(text)
            if len(sub) >= 2:
                for c in sub:
                    if is_weak_magazine_title(c.get("title") or ""):
                        better = _headline_from_text(c.get("text") or "")
                        if better:
                            c["title"] = better
                chunks.extend(sub)
                continue
            if sub:
                cand = sub[0]
                if is_weak_magazine_title(cand.get("title") or ""):
                    better = _headline_from_text(text)
                    if better:
                        cand = dict(cand)
                        cand["title"] = better
                if not is_weak_magazine_title(cand.get("title") or ""):
                    chunks.append(cand)
                    continue
            parts = _split_text_by_max_words(text, 1200)
            for j, part in enumerate(parts):
                ht = _headline_from_text(part) or f"Article {len(chunks) + 1}"
                if len(parts) > 1:
                    ht = f"{ht} ({j + 1})"
                chunks.append(
                    {
                        "chunk_index": len(chunks),
                        "text": part,
                        "title": ht,
                        "is_toc": is_toc_text(part),
                    }
                )
            continue
        if weak:
            better = _headline_from_text(text)
            if better:
                title = better
        chunks.append(
            {
                "chunk_index": len(chunks),
                "text": text,
                "title": title,
                "is_toc": is_toc_text(text),
            }
        )
    return _split_oversized_chunks(chunks)


def build_chunks(extracted: dict[str, Any], book_type: str) -> list[dict[str, Any]]:
    """Build ordered chunks from extract_book() result."""
    book_type = (book_type or BOOK_TYPE_NOVEL).lower()
    if book_type not in (BOOK_TYPE_NOVEL, BOOK_TYPE_MAGAZINE):
        book_type = BOOK_TYPE_NOVEL

    if book_type == BOOK_TYPE_MAGAZINE:
        if extracted.get("sections"):
            return _polish_magazine_chunk_titles(
                _magazine_chunks_from_sections(extracted["sections"])
            )
        if extracted.get("pages"):
            pages = extracted["pages"]
            outline = extracted.get("outline") or []
            if outline:
                chunks = chunk_magazine_from_outline(pages, outline)
                if chunks:
                    return _split_oversized_chunks(chunks)
            chunks = chunk_magazine_by_page_headings(pages)
            if chunks:
                return _polish_magazine_chunk_titles(_split_oversized_chunks(chunks))
            full = "\n\n".join(p for p in pages if p)
            chunks = chunk_magazine_text(full)
            return _polish_magazine_chunk_titles(_split_oversized_chunks(chunks))
        return []

    # novel / ebook
    if extracted.get("pages") is not None:
        pages = extracted["pages"]
        outline = extracted.get("outline") or []
        chunks = chunk_novel_from_outline(pages, outline) if outline else []
        if not chunks:
            printed = outline_from_novel_contents(pages)
            if printed:
                chunks = chunk_novel_from_outline(pages, printed)
        if not chunks:
            chunks = chunk_novel_pages(pages, pages_per_chunk=2)
        return _split_oversized_chunks(chunks)
    if extracted.get("sections"):
        chunks = []
        for s in extracted["sections"]:
            text = (s.get("text") or "").strip()
            if not text:
                continue
            chunks.append(
                {
                    "chunk_index": len(chunks),
                    "text": text,
                    "title": s.get("title") or f"Part {len(chunks) + 1}",
                    "is_toc": is_toc_text(text),
                }
            )
        if len(chunks) < 2:
            texts = [c["text"] for c in chunks]
            return _split_oversized_chunks(chunk_by_words(texts, target_words=1000))
        words = [len(c["text"].split()) for c in chunks]
        words_sorted = sorted(words)
        median = words_sorted[len(words_sorted) // 2]
        if len(chunks) > 15 and median < 400:
            texts = [c["text"] for c in chunks]
            return _split_oversized_chunks(chunk_by_words(texts, target_words=1000))
        return _split_oversized_chunks(chunks)
    return []


def save_book_files(
    books_dir: str,
    src_path: str,
    book_type: str,
    original_filename: str,
) -> dict[str, Any]:
    """
    Extract, chunk, write meta.json + chunks.json under docs/books/{book_id}/.
    Does not index Qdrant (caller may call index_chunks_to_rag).
    """
    os.makedirs(books_dir, exist_ok=True)
    extracted = extract_book(src_path)
    title = _title_from_sources(original_filename, extracted)
    book_id = _make_book_id(title)
    book_dir = os.path.join(books_dir, book_id)
    os.makedirs(book_dir, exist_ok=True)

    ext = os.path.splitext(original_filename)[1].lower() or os.path.splitext(src_path)[1].lower()
    dest_name = f"original{ext}"
    dest_path = os.path.join(book_dir, dest_name)
    shutil.copy2(src_path, dest_path)

    chunks = build_chunks(extracted, book_type)
    if not chunks:
        meta = {
            "book_id": book_id,
            "title": title,
            "book_type": book_type,
            "format": extracted.get("format"),
            "filename": original_filename,
            "chunk_count": 0,
            "status": "error",
            "error": "No text extracted",
            "created_at": datetime.now().isoformat(),
        }
        with open(os.path.join(book_dir, "meta.json"), "w", encoding="utf-8") as f:
            json.dump(meta, f, ensure_ascii=False, indent=2)
        return meta

    for i, c in enumerate(chunks):
        c["chunk_index"] = i

    with open(os.path.join(book_dir, "chunks.json"), "w", encoding="utf-8") as f:
        json.dump(chunks, f, ensure_ascii=False, indent=1)

    if book_type in (BOOK_TYPE_MAGAZINE, BOOK_TYPE_NOVEL):
        write_toc_json(book_dir, chunks, book_type=book_type)

    readable = next_readable_index(chunks, start=0)
    if readable is None:
        meta = {
            "book_id": book_id,
            "title": title,
            "book_type": book_type,
            "format": extracted.get("format"),
            "filename": original_filename,
            "original": dest_name,
            "chunk_count": len(chunks),
            "first_readable_index": None,
            "status": "no_readable_content",
            "error": "All chunks look like table of contents / non-readable",
            "rag_status": "skipped",
            "created_at": datetime.now().isoformat(),
        }
    else:
        meta = {
            "book_id": book_id,
            "title": title,
            "book_type": book_type,
            "format": extracted.get("format"),
            "filename": original_filename,
            "original": dest_name,
            "chunk_count": len(chunks),
            "first_readable_index": readable,
            "status": "ready",
            "rag_status": "pending",
            "created_at": datetime.now().isoformat(),
        }
    with open(os.path.join(book_dir, "meta.json"), "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2)
    return meta


def load_meta(books_dir: str, book_id: str) -> Optional[dict[str, Any]]:
    try:
        book_dir = resolve_book_dir(books_dir, book_id)
    except InvalidBookId:
        return None
    path = os.path.join(book_dir, "meta.json")
    if not os.path.isfile(path):
        return None
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def load_chunks(books_dir: str, book_id: str) -> list[dict[str, Any]]:
    try:
        book_dir = resolve_book_dir(books_dir, book_id)
    except InvalidBookId:
        return []
    path = os.path.join(book_dir, "chunks.json")
    if not os.path.isfile(path):
        return []
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def list_books(books_dir: str) -> list[dict[str, Any]]:
    if not os.path.isdir(books_dir):
        return []
    out = []
    for name in sorted(os.listdir(books_dir)):
        if not is_valid_book_id(name):
            continue
        meta = load_meta(books_dir, name)
        if meta:
            out.append(meta)
    return out


def get_chunk(books_dir: str, book_id: str, chunk_index: int) -> Optional[dict[str, Any]]:
    from intensive_reading.text_format import normalize_reading_text

    chunks = load_chunks(books_dir, book_id)
    for c in chunks:
        if int(c.get("chunk_index", -1)) == int(chunk_index):
            out = dict(c)
            out["text"] = normalize_reading_text(out.get("text") or "")
            return out
    return None


_PART_SUFFIX = re.compile(r"\s*\(\d+\)\s*$")


def build_toc_entries(
    chunks: list[dict[str, Any]],
    book_type: str | None = None,
) -> list[dict[str, Any]]:
    """TOC list for Articles/Chapters UI (skips pure TOC chrome chunks)."""
    entries: list[dict[str, Any]] = []
    last_collapsed_key: str | None = None
    collapse = (book_type or "").lower() == BOOK_TYPE_NOVEL
    for c in chunks or []:
        if c.get("is_toc"):
            continue
        title = (c.get("title") or "").strip()
        if not title:
            continue
        display = _PART_SUFFIX.sub("", title).strip() if collapse else title
        if collapse:
            key = display.lower()
            if last_collapsed_key == key:
                continue
            last_collapsed_key = key
        entry: dict[str, Any] = {
            "title": display,
            "chunk_index": int(c.get("chunk_index", len(entries))),
        }
        if c.get("start_page") is not None:
            entry["start_page"] = c.get("start_page")
        if c.get("end_page") is not None:
            entry["end_page"] = c.get("end_page")
        entries.append(entry)
    return entries


def write_toc_json(
    book_dir: str,
    chunks: list[dict[str, Any]],
    book_type: str | None = None,
) -> list[dict[str, Any]]:
    toc = build_toc_entries(chunks, book_type=book_type)
    with open(os.path.join(book_dir, "toc.json"), "w", encoding="utf-8") as f:
        json.dump(toc, f, ensure_ascii=False, indent=1)
    return toc


def load_toc(books_dir: str, book_id: str) -> list[dict[str, Any]]:
    try:
        book_dir = resolve_book_dir(books_dir, book_id)
    except InvalidBookId:
        return []
    path = os.path.join(book_dir, "toc.json")
    if os.path.isfile(path):
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, list) else []
    meta = load_meta(books_dir, book_id) or {}
    return build_toc_entries(
        load_chunks(books_dir, book_id),
        book_type=meta.get("book_type"),
    )


def update_meta_fields(books_dir: str, book_id: str, fields: dict[str, Any]) -> Optional[dict[str, Any]]:
    meta = load_meta(books_dir, book_id)
    if not meta:
        return None
    meta.update(fields)
    book_dir = resolve_book_dir(books_dir, book_id)
    with open(os.path.join(book_dir, "meta.json"), "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2)
    return meta


def _title_from_filename(filename: str) -> str:
    stem = os.path.splitext(os.path.basename(filename or ""))[0].strip()
    stem = re.sub(r"\s+", " ", stem).strip()
    # Drop leftover replacement characters from bad encodings
    stem = stem.replace("\ufffd", "").strip()
    return stem or "Untitled"


def needs_title_repair(meta: dict[str, Any]) -> bool:
    title = (meta.get("title") or "").strip()
    if not title or re.match(r"^tmp[0-9a-z_]+$", title, re.I):
        return bool(meta.get("filename"))
    return False


def repair_book_title(books_dir: str, book_id: str) -> Optional[dict[str, Any]]:
    """Replace tempfile-style titles with the upload filename stem."""
    meta = load_meta(books_dir, book_id)
    if not meta or not needs_title_repair(meta):
        return meta
    new_title = _title_from_filename(meta.get("filename") or "")
    return update_meta_fields(books_dir, book_id, {"title": new_title})


def rechunk_oversized_book(
    books_dir: str,
    book_id: str,
    max_words: int = 1200,
) -> tuple[list[dict[str, Any]], bool]:
    """
    Re-split oversized chunks on disk. Returns (chunks, changed).
    """
    chunks = load_chunks(books_dir, book_id)
    if not chunks:
        return [], False
    rebuilt = _split_oversized_chunks(chunks, max_words=max_words)
    changed = len(rebuilt) != len(chunks) or any(
        (a.get("text") or "") != (b.get("text") or "")
        for a, b in zip(chunks, rebuilt)
    )
    if not changed:
        return chunks, False
    book_dir = resolve_book_dir(books_dir, book_id)
    with open(os.path.join(book_dir, "chunks.json"), "w", encoding="utf-8") as f:
        json.dump(rebuilt, f, ensure_ascii=False, indent=1)
    readable = next_readable_index(rebuilt, start=0)
    fields: dict[str, Any] = {
        "chunk_count": len(rebuilt),
        "first_readable_index": readable,
    }
    if readable is None:
        fields["status"] = "no_readable_content"
        fields["rag_status"] = "skipped"
    else:
        fields["status"] = "ready"
    update_meta_fields(books_dir, book_id, fields)
    return rebuilt, True


def reindex_book(books_dir: str, book_id: str) -> dict[str, Any]:
    """
    Fix title if needed, re-split oversized chunks, then (re)index into RAG.
    Returns updated meta (includes rag_status / rag_error).
    """
    if not is_valid_book_id(book_id):
        raise InvalidBookId(f"Invalid book_id: {book_id!r}")
    meta = load_meta(books_dir, book_id)
    if not meta:
        raise FileNotFoundError(f"Book not found: {book_id}")

    meta = repair_book_title(books_dir, book_id) or meta
    chunks, _ = rechunk_oversized_book(books_dir, book_id)
    meta = load_meta(books_dir, book_id) or meta

    if meta.get("status") != "ready" or not chunks:
        return update_meta_fields(
            books_dir,
            book_id,
            {"rag_status": "skipped", "rag_chunks": 0, "rag_error": meta.get("error") or "not ready"},
        ) or meta

    count, err = index_chunks_to_rag(
        book_id,
        meta.get("title") or book_id,
        meta.get("book_type") or BOOK_TYPE_NOVEL,
        chunks,
    )
    if count > 0 and not err:
        return update_meta_fields(
            books_dir,
            book_id,
            {"rag_status": "ok", "rag_chunks": count, "rag_error": ""},
        ) or meta
    return update_meta_fields(
        books_dir,
        book_id,
        {
            "rag_status": "failed",
            "rag_chunks": 0,
            "rag_error": err or "index returned 0 points",
        },
    ) or meta


def _original_file_path(book_dir: str) -> Optional[str]:
    if not os.path.isdir(book_dir):
        return None
    for name in sorted(os.listdir(book_dir)):
        if name.lower().startswith("original.") and os.path.isfile(os.path.join(book_dir, name)):
            return os.path.join(book_dir, name)
    return None


def rebuild_magazine_from_original(
    books_dir: str,
    book_id: str,
    *,
    reindex_rag: bool = True,
) -> dict[str, Any]:
    """
    Re-extract + re-chunk a book from original.*, clear analysis cache.
    Accepts magazine and novel. Returns updated meta.
    """
    if not is_valid_book_id(book_id):
        raise InvalidBookId(f"Invalid book_id: {book_id!r}")
    meta = load_meta(books_dir, book_id)
    if not meta:
        raise FileNotFoundError(f"Book not found: {book_id}")
    book_type = (meta.get("book_type") or "").strip().lower()
    if book_type not in (BOOK_TYPE_MAGAZINE, BOOK_TYPE_NOVEL):
        raise ValueError("rebuild_magazine_from_original only accepts magazine or novel books")

    book_dir = resolve_book_dir(books_dir, book_id)
    src = _original_file_path(book_dir)
    if not src:
        raise FileNotFoundError(f"No original.* file for book: {book_id}")

    extracted = extract_book(src)
    chunks = build_chunks(extracted, book_type)
    if not chunks:
        return update_meta_fields(
            books_dir,
            book_id,
            {
                "status": "error",
                "error": "No text extracted on rebuild",
                "chunk_count": 0,
                "rag_status": "skipped",
            },
        ) or meta

    for i, c in enumerate(chunks):
        c["chunk_index"] = i
    with open(os.path.join(book_dir, "chunks.json"), "w", encoding="utf-8") as f:
        json.dump(chunks, f, ensure_ascii=False, indent=1)
    write_toc_json(book_dir, chunks, book_type=book_type)

    from intensive_reading.analysis_cache import clear_book_analyses

    cleared = clear_book_analyses(books_dir, book_id)

    readable = next_readable_index(chunks, start=0)
    fields: dict[str, Any] = {
        "chunk_count": len(chunks),
        "first_readable_index": readable,
        "status": "ready" if readable is not None else "no_readable_content",
        "error": "",
    }
    if readable is None:
        fields["rag_status"] = "skipped"
    meta = update_meta_fields(books_dir, book_id, fields) or meta
    meta = dict(meta)
    meta["analyses_cleared"] = cleared

    if readable is None:
        return meta

    if not reindex_rag:
        stale = update_meta_fields(
            books_dir,
            book_id,
            {
                "rag_status": "stale",
                "rag_error": "chunks rebuilt; RAG reindex skipped",
            },
        ) or meta
        stale = dict(stale)
        stale["analyses_cleared"] = cleared
        return stale

    count, err = index_chunks_to_rag(
        book_id,
        meta.get("title") or book_id,
        book_type,
        chunks,
    )
    if count > 0 and not err:
        return update_meta_fields(
            books_dir,
            book_id,
            {"rag_status": "ok", "rag_chunks": count, "rag_error": ""},
        ) or meta
    return update_meta_fields(
        books_dir,
        book_id,
        {
            "rag_status": "failed",
            "rag_chunks": 0,
            "rag_error": err or "index returned 0 points",
        },
    ) or meta


_EMBED_MAX_CHARS = 2000
_PAYLOAD_MAX_CHARS = 8000

_RAG_CONFIG_PATH = os.path.normpath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "config.py")
)


def _force_rag_config() -> None:
    """Point sys.modules['config'] at scripts/config.py (has SNAPSHOT_PATH)."""
    spec = importlib.util.spec_from_file_location("config", _RAG_CONFIG_PATH)
    rag_cfg = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(rag_cfg)
    sys.modules["config"] = rag_cfg


def _import_rag_index_deps():
    """Import RAG indexer symbols while stock routes may occupy sys.modules['config'].

    @_with_stock_imports swaps config to stock_config (no SNAPSHOT_PATH). Force the
    RAG config for the import, then restore. Retry covers a poll swapping mid-import.
    """
    prev_config = sys.modules.get("config")
    last_err: Exception | None = None
    try:
        for _ in range(5):
            try:
                _force_rag_config()
                from rag_engine import COLLECTION, get_embed_model, get_qdrant
                from config import SNAPSHOT_PATH

                return COLLECTION, get_embed_model, get_qdrant, SNAPSHOT_PATH
            except ImportError as e:
                last_err = e
                time.sleep(0.3)
        raise last_err or ImportError("import rag_engine failed")
    finally:
        if prev_config is not None:
            sys.modules["config"] = prev_config


def index_chunks_to_rag(
    book_id: str,
    title: str,
    book_type: str,
    chunks: list[dict[str, Any]],
) -> tuple[int, str]:
    """
    Upsert chunks into the live Qdrant collection and update snapshot.

    Returns (count, error_message). error_message is empty on success.
    """
    if not chunks:
        return 0, "no chunks"
    if not is_valid_book_id(book_id):
        return 0, "invalid book_id"
    try:
        COLLECTION, get_embed_model, get_qdrant, SNAPSHOT_PATH = _import_rag_index_deps()
    except Exception as e:
        return 0, f"import rag_engine failed: {e}"

    try:
        from qdrant_client.models import PointStruct
        import rag_engine as re_mod
    except Exception as e:
        return 0, f"import qdrant failed: {e}"

    try:
        client = get_qdrant()
        model = get_embed_model()
        # Truncate for embedding — MiniLM only uses ~256 tokens anyway
        texts = [(c.get("text") or "")[:_EMBED_MAX_CHARS] or " " for c in chunks]
        embeddings: list[Any] = []
        batch_size = 16
        for i in range(0, len(texts), batch_size):
            batch = texts[i : i + batch_size]
            emb = model.encode(batch, show_progress_bar=False, normalize_embeddings=True)
            embeddings.extend(list(emb))
        points = []
        today = date.today().isoformat()
        for c, emb in zip(chunks, embeddings):
            idx = int(c.get("chunk_index", 0))
            point_id = str(uuid.uuid5(uuid.NAMESPACE_URL, f"intensive_reading:{book_id}:{idx}"))
            vec = emb.tolist() if hasattr(emb, "tolist") else list(emb)
            raw_text = c.get("text") or ""
            payload = {
                "date": today,
                "source": "intensive_reading",
                "title": c.get("title") or f"{title} #{idx}",
                "parent_title": title,
                "item_type": "intensive_reading",
                "book_id": book_id,
                "book_type": book_type,
                "chunk_index": idx,
                "is_toc": bool(c.get("is_toc")),
                "difficulty": "advanced",
                "text": raw_text[:_PAYLOAD_MAX_CHARS],
                "filename": book_id,
                "url": "",
                "tags": ["intensive_reading", book_type],
            }
            points.append(PointStruct(id=point_id, vector=vec, payload=payload))

        for i in range(0, len(points), 50):
            client.upsert(collection_name=COLLECTION, points=points[i : i + 50])

        cache = getattr(re_mod, "_qdrant_points", None)
        if isinstance(cache, list):
            re_mod._qdrant_points = [
                p for p in cache
                if not (
                    (p.get("payload") or {}).get("source") == "intensive_reading"
                    and (p.get("payload") or {}).get("book_id") == book_id
                )
            ]
            for pt in points:
                re_mod._qdrant_points.append({"id": pt.id, "payload": dict(pt.payload or {})})

        _merge_snapshot(SNAPSHOT_PATH, points)
        return len(points), ""
    except Exception as e:
        print(f"[intensive_reading] RAG index failed: {e}", flush=True)
        return 0, f"{type(e).__name__}: {e}"


def _merge_snapshot(snapshot_path: str, new_points) -> None:
    """Merge new points into .rag-store.json by id."""
    data = {"points": []}
    if os.path.exists(snapshot_path):
        try:
            with open(snapshot_path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception:
            data = {"points": []}
    by_id = {str(p.get("id")): p for p in data.get("points", [])}
    for pt in new_points:
        by_id[str(pt.id)] = {
            "id": str(pt.id),
            "vector": pt.vector,
            "payload": pt.payload,
        }
    out = {
        "collection": data.get("collection") or "ai_briefings",
        "saved_at": datetime.now().isoformat(),
        "count": len(by_id),
        "points": list(by_id.values()),
    }
    os.makedirs(os.path.dirname(snapshot_path) or ".", exist_ok=True)
    tmp = f"{snapshot_path}.tmp-{os.getpid()}"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False)
    os.replace(tmp, snapshot_path)


def _remove_book_from_snapshot(snapshot_path: str, book_id: str) -> int:
    """Drop intensive_reading points for book_id from .rag-store.json. Returns count removed.

    Missing file is a no-op (return 0). Corrupt or unwritable snapshot raises.
    """
    if not snapshot_path or not os.path.exists(snapshot_path):
        return 0
    with open(snapshot_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    points = data.get("points") or []
    kept = []
    removed = 0
    for p in points:
        payload = p.get("payload") or {}
        if (
            payload.get("source") == "intensive_reading"
            and payload.get("book_id") == book_id
        ):
            removed += 1
            continue
        kept.append(p)
    if removed == 0:
        return 0
    out = {
        "collection": data.get("collection") or "ai_briefings",
        "saved_at": datetime.now().isoformat(),
        "count": len(kept),
        "points": kept,
    }
    os.makedirs(os.path.dirname(snapshot_path) or ".", exist_ok=True)
    tmp = f"{snapshot_path}.tmp-{os.getpid()}"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False)
    os.replace(tmp, snapshot_path)
    return removed


def unindex_book_from_rag(book_id: str) -> str:
    """Remove this book's vectors from Qdrant, in-memory cache, and snapshot.

    Returns empty string on success, or an error message (caller may still
    delete local files). Qdrant / cache / snapshot are independent so a Qdrant
    failure still prunes the durable snapshot.
    """
    if not is_valid_book_id(book_id):
        return "invalid book_id"
    try:
        COLLECTION, _get_embed, get_qdrant, SNAPSHOT_PATH = _import_rag_index_deps()
    except Exception as e:
        return f"import rag_engine failed: {e}"

    errs: list[str] = []
    try:
        from qdrant_client.models import FieldCondition, Filter, MatchValue

        client = get_qdrant()
        delete_filter = Filter(must=[
            FieldCondition(key="source", match=MatchValue(value="intensive_reading")),
            FieldCondition(key="book_id", match=MatchValue(value=book_id)),
        ])
        old_ids = []
        offset = None
        while True:
            result = client.scroll(
                collection_name=COLLECTION,
                scroll_filter=delete_filter,
                limit=500,
                offset=offset,
                with_payload=False,
            )
            points, next_offset = result
            old_ids.extend(p.id for p in points)
            if next_offset is None:
                break
            offset = next_offset
        if old_ids:
            client.delete(collection_name=COLLECTION, points_selector=old_ids)
    except Exception as e:
        print(f"[intensive_reading] RAG unindex qdrant failed: {e}", flush=True)
        errs.append(f"qdrant: {e}")

    try:
        import rag_engine as re_mod

        cache = getattr(re_mod, "_qdrant_points", None)
        if isinstance(cache, list):
            re_mod._qdrant_points = [
                p for p in cache
                if not (
                    (p.get("payload") or {}).get("source") == "intensive_reading"
                    and (p.get("payload") or {}).get("book_id") == book_id
                )
            ]
    except Exception as e:
        print(f"[intensive_reading] RAG unindex cache failed: {e}", flush=True)
        errs.append(f"cache: {e}")

    try:
        _remove_book_from_snapshot(SNAPSHOT_PATH, book_id)
    except Exception as e:
        print(f"[intensive_reading] RAG unindex snapshot failed: {e}", flush=True)
        errs.append(f"snapshot: {e}")

    return "; ".join(errs)


def delete_book(books_dir: str, book_id: str) -> dict[str, Any]:
    """Unindex from RAG, clear progress, then delete docs/books/{book_id}/."""
    if not is_valid_book_id(book_id):
        raise InvalidBookId(f"Invalid book_id: {book_id!r}")
    book_dir = resolve_book_dir(books_dir, book_id)
    meta = load_meta(books_dir, book_id)
    if not meta and not os.path.isdir(book_dir):
        raise FileNotFoundError(f"Book not found: {book_id}")

    rag_err = unindex_book_from_rag(book_id)
    try:
        from intensive_reading.progress import clear_progress

        clear_progress(book_id)
    except Exception:
        pass

    if os.path.isdir(book_dir):
        shutil.rmtree(book_dir)
    elif not meta:
        raise FileNotFoundError(f"Book not found: {book_id}")

    return {
        "ok": True,
        "book_id": book_id,
        "title": (meta or {}).get("title") or book_id,
        "rag_error": rag_err or "",
    }
