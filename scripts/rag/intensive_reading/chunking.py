"""Chunking and TOC detection for intensive reading."""

from __future__ import annotations

import re
from typing import Any, Optional

_TOC_HEADING = re.compile(
    r"^\s*(table\s+of\s+contents|contents|index|目錄|目录)\s*$",
    re.IGNORECASE | re.MULTILINE,
)
_PAGE_DOTS = re.compile(r"\.{3,}\s*\d+\s*$", re.MULTILINE)


def is_toc_text(text: str) -> bool:
    """Heuristic: TOC heading and/or many page-number dotted lines."""
    if not text or not text.strip():
        return False
    sample = text.strip()[:2000]
    if _TOC_HEADING.search(sample):
        return True
    lines = [ln.strip() for ln in sample.splitlines() if ln.strip()]
    if len(lines) < 4:
        return False
    dotted = sum(1 for ln in lines if _PAGE_DOTS.search(ln) or re.search(r"\s+\d{1,3}$", ln))
    # Short lines that look like a contents list
    short = sum(1 for ln in lines if len(ln) < 60)
    if dotted >= 3 and dotted / max(len(lines), 1) >= 0.35:
        return True
    if _TOC_HEADING.search(sample[:200]) and short / max(len(lines), 1) >= 0.7:
        return True
    return False


def chunk_novel_pages(
    pages: list[str],
    pages_per_chunk: int = 2,
) -> list[dict[str, Any]]:
    """Group consecutive pages into chunks (default 1–2 pages)."""
    if pages_per_chunk < 1:
        pages_per_chunk = 1
    chunks: list[dict[str, Any]] = []
    idx = 0
    i = 0
    while i < len(pages):
        group = pages[i : i + pages_per_chunk]
        text = "\n\n".join(p.strip() for p in group if p and p.strip()).strip()
        i += pages_per_chunk
        if not text:
            continue
        chunks.append(
            {
                "chunk_index": idx,
                "text": text,
                "title": f"Pages {i - len(group) + 1}-{i}",
                "is_toc": is_toc_text(text),
            }
        )
        idx += 1
    return chunks


def chunk_by_words(sections: list[str], target_words: int = 1000) -> list[dict[str, Any]]:
    """Merge section texts into ~target_words chunks (EPUB without pages)."""
    chunks: list[dict[str, Any]] = []
    buf: list[str] = []
    buf_words = 0
    idx = 0

    def flush(title: str = ""):
        nonlocal idx, buf, buf_words
        text = "\n\n".join(buf).strip()
        buf = []
        buf_words = 0
        if not text:
            return
        chunks.append(
            {
                "chunk_index": idx,
                "text": text,
                "title": title or f"Part {idx + 1}",
                "is_toc": is_toc_text(text),
            }
        )
        idx += 1

    for sec in sections:
        words = len(sec.split())
        if buf and buf_words + words > target_words * 1.25 and buf_words >= target_words * 0.6:
            flush()
        buf.append(sec.strip())
        buf_words += words
        if buf_words >= target_words:
            flush()
    flush()
    return chunks


_SECTION_NAME = re.compile(
    r"^(Leaders|Briefing|United States|The Americas|Asia|China|"
    r"Middle East(?:\s*&\s*Africa)?|Europe|Britain|International|Business|"
    r"Finance\s*&\s*economics|Science\s*&\s*technology|Books\s*&\s*arts|"
    r"Graphic detail|Obituary)$",
    re.I,
)


def _is_magazine_heading(line: str) -> tuple[bool, bool]:
    """Return (is_heading, is_hard_section_name)."""
    stripped = line.strip()
    if not stripped or len(stripped) > 80 or stripped.endswith((".", ";", ",")):
        return False, False
    word_count = len(stripped.split())
    if word_count < 1 or word_count > 12:
        return False, False
    if _SECTION_NAME.match(stripped):
        return True, True
    if stripped == stripped.title() or stripped.isupper():
        return True, False
    return False, False


def chunk_magazine_text(text: str) -> list[dict[str, Any]]:
    """Split magazine-like text on article / section headings."""
    if not text or not text.strip():
        return []

    lines = text.splitlines()
    # Find candidate split points: short Title-ish lines after blank lines
    boundaries: list[tuple[int, bool]] = [(0, False)]
    for i, line in enumerate(lines):
        if i == 0:
            continue
        prev_blank = not lines[i - 1].strip()
        if not prev_blank:
            continue
        is_h, is_hard = _is_magazine_heading(line)
        if is_h:
            boundaries.append((i, is_hard))

    # Deduplicate by index, prefer hard flag
    by_i: dict[int, bool] = {}
    for i, hard in boundaries:
        by_i[i] = by_i.get(i, False) or hard
    ordered = sorted(by_i.items())

    segments: list[tuple[str, str, bool]] = []
    for bi, (start, hard) in enumerate(ordered):
        end = ordered[bi + 1][0] if bi + 1 < len(ordered) else len(lines)
        block_lines = lines[start:end]
        title = next((ln.strip() for ln in block_lines if ln.strip()), f"Article {bi + 1}")
        body = "\n".join(block_lines).strip()
        if body:
            # hard applies to THIS segment start (section name)
            segments.append((title, body, hard))

    chunks: list[dict[str, Any]] = []
    idx = 0
    pending_title = ""
    pending_parts: list[str] = []

    def flush_pending(min_words: int = 25):
        nonlocal idx, pending_title, pending_parts
        text_out = "\n\n".join(pending_parts).strip()
        pending_parts = []
        if not text_out:
            return
        if len(text_out.split()) < min_words and not is_toc_text(text_out):
            return
        chunks.append(
            {
                "chunk_index": idx,
                "text": text_out,
                "title": pending_title or f"Article {idx + 1}",
                "is_toc": is_toc_text(text_out),
            }
        )
        idx += 1
        pending_title = ""

    for title, body, hard_start in segments:
        wc = len(body.split())
        if not pending_parts:
            pending_title = title
            pending_parts.append(body)
            continue
        pending_wc = len(" ".join(pending_parts).split())
        # Hard section boundary (e.g. Finance & economics) starts a new article
        # when we already have a real body.
        if hard_start and pending_wc >= 25:
            flush_pending(min_words=25)
            pending_title = title
            pending_parts.append(body)
            continue
        # Soft title: split if both sides look like articles
        if pending_wc >= 40 and wc >= 30:
            flush_pending(min_words=25)
            pending_title = title
            pending_parts.append(body)
        else:
            pending_parts.append(body)

    flush_pending(min_words=25)

    if not chunks:
        return chunk_by_words([text], target_words=900)

    for i, c in enumerate(chunks):
        c["chunk_index"] = i
    return chunks


def next_readable_index(
    chunks: list[dict[str, Any]],
    start: int = 0,
) -> Optional[int]:
    """First non-TOC chunk index at or after start, or None."""
    for c in chunks:
        idx = int(c.get("chunk_index", -1))
        if idx < start:
            continue
        if c.get("is_toc"):
            continue
        return idx
    return None


def prev_readable_index(
    chunks: list[dict[str, Any]],
    before: int,
) -> Optional[int]:
    """Nearest non-TOC chunk index strictly before `before`, or None."""
    best: Optional[int] = None
    for c in chunks:
        idx = int(c.get("chunk_index", -1))
        if idx >= before:
            continue
        if c.get("is_toc"):
            continue
        if best is None or idx > best:
            best = idx
    return best
