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

_WEAK_MAGAZINE_TITLE = re.compile(
    r"^(cover|contents|table\s+of\s+contents|magazine\s+articles|masthead|toc|"
    r"copyright|imprint|illustration|photograph|photo\s*credit)\b"
    r"|章节菜单|主菜单"
    r"|\d{4}\s*PRICE"
    r"|PRICE\s*\$"
    r"|^\d*\s*the\s+new\s+yorker\b"
    r"|the\s+new\s+yorker,\s+(january|february|march|april|may|june|july|august|september|october|november|december)\b",
    re.I,
)


def is_weak_magazine_title(title: str) -> bool:
    """True when a spine/section title is unlikely to be a real article headline."""
    t = (title or "").strip()
    if not t:
        return True
    if len(t) < 6:
        return True
    if _WEAK_MAGAZINE_TITLE.search(t):
        return True
    if t.count("|") >= 2:
        return True
    # Long TOC-ish lines listing many short topics
    if len(t) > 90 and t.count(" ") >= 12 and not re.search(r"[.!?]", t):
        return True
    return False


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


_PAGE_MASTHEAD = re.compile(
    r"^(?:\d+\s+)?(?:the\s+)?(?:new\s+yorker|economist|wired)\b"
    r"|^\d{4}\s*PRICE\b"
    r"|^(?:january|february|march|april|may|june|july|august|september|"
    r"october|november|december)\s+\d{1,2},\s*\d{4}\s*PRICE\b"
    r"|^(?:cover|contents|table\s+of\s+contents|masthead)\b",
    re.I,
)
_SMALL_WORDS = frozenset(
    "a an the and or of for to in on at by with from vs versus".split()
)


def _outline_leaves(outline: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Prefer leaf bookmarks when the outline is nested; else keep all."""
    entries = [dict(e) for e in (outline or []) if (e.get("title") or "").strip()]
    if not entries:
        return []
    if not any(int(e.get("level") or 0) > 0 for e in entries):
        return entries
    leaves: list[dict[str, Any]] = []
    for i, e in enumerate(entries):
        cur = int(e.get("level") or 0)
        nxt = int(entries[i + 1].get("level") or 0) if i + 1 < len(entries) else -1
        if nxt > cur:
            continue  # parent with children
        leaves.append(e)
    return leaves or entries


def chunk_magazine_from_outline(
    pages: list[str],
    outline: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """
    Split PDF pages by bookmark start pages; title comes from the bookmark.

    Page indices are 0-based. Consecutive bookmarks on the same page collapse
    to the last title for that page start (rare). Empty page ranges are skipped.
    """
    if not pages:
        return []
    leaves = _outline_leaves(outline)
    if not leaves:
        return []

    # Sort by page, keep first unique start page (bookmark order preserved via stable sort)
    starts: list[tuple[int, str]] = []
    seen_pages: set[int] = set()
    for e in leaves:
        try:
            page = int(e.get("page"))
        except (TypeError, ValueError):
            continue
        if page < 0 or page >= len(pages):
            continue
        title = (e.get("title") or "").strip()
        if not title:
            continue
        if page in seen_pages:
            # Same page: keep the later (usually more specific) title
            starts = [(p, t) for p, t in starts if p != page]
        seen_pages.add(page)
        starts.append((page, title))
    starts.sort(key=lambda x: x[0])
    if not starts:
        return []

    chunks: list[dict[str, Any]] = []
    first_start = starts[0][0]
    if first_start > 0:
        lead = "\n\n".join(
            (p or "").strip() for p in pages[:first_start] if (p or "").strip()
        ).strip()
        if lead and len(lead.split()) >= 40:
            chunks.append(
                {
                    "chunk_index": 0,
                    "text": lead,
                    "title": "Front matter" if not is_toc_text(lead) else "Contents",
                    "is_toc": is_toc_text(lead),
                    "start_page": 0,
                    "end_page": first_start - 1,
                }
            )

    for i, (start, title) in enumerate(starts):
        end = starts[i + 1][0] if i + 1 < len(starts) else len(pages)
        text = "\n\n".join(
            (p or "").strip() for p in pages[start:end] if (p or "").strip()
        ).strip()
        if not text:
            continue
        chunks.append(
            {
                "chunk_index": len(chunks),
                "text": text,
                "title": title,
                "is_toc": is_toc_text(text),
                "start_page": start,
                "end_page": end - 1,
            }
        )
    return chunks


def _looks_like_page_heading(line: str) -> bool:
    """Heuristic article title at/near the top of a magazine page."""
    stripped = re.sub(r"\s+", " ", (line or "")).strip()
    if not stripped or len(stripped) > 80:
        return False
    if stripped.endswith((".", ";", ",", ":", "…")):
        return False
    if _PAGE_MASTHEAD.search(stripped):
        return False
    if is_weak_magazine_title(stripped):
        return False
    words = stripped.split()
    if len(words) < 1 or len(words) > 12:
        return False
    if _SECTION_NAME.match(stripped):
        return True
    # Title Case allowing small words: "Cash and Carry", "Into the Woods"
    capsish = 0
    for w in words:
        core = re.sub(r"[^A-Za-z']", "", w)
        if not core:
            continue
        if core.lower() in _SMALL_WORDS:
            capsish += 1
            continue
        if core[0].isupper() or core.isupper():
            capsish += 1
    if capsish < max(1, len(words) - 1):
        return False
    # Avoid body fragments that are mostly lowercase glue
    letters = re.sub(r"[^A-Za-z]", "", stripped)
    if letters and sum(1 for ch in letters if ch.isupper()) / len(letters) < 0.12:
        return False
    return True


def _heading_from_page(page_text: str) -> str:
    """First plausible heading after masthead lines on a page."""
    lines = [ln.strip() for ln in (page_text or "").splitlines()]
    nonempty = [ln for ln in lines if ln]
    # Skip leading masthead / page-number chrome
    i = 0
    while i < len(nonempty) and (
        _PAGE_MASTHEAD.search(nonempty[i])
        or is_weak_magazine_title(nonempty[i])
        or re.fullmatch(r"\d{1,3}", nonempty[i])
    ):
        i += 1
    # Prefer a heading in the first few content lines
    for ln in nonempty[i : i + 6]:
        if _looks_like_page_heading(ln):
            return ln
    return ""


def _titles_from_contents_pages(pages: list[str], max_scan: int = 8) -> list[str]:
    """Pull article titles from early Contents-like pages when present."""
    titles: list[str] = []
    author_num = re.compile(
        r"^[A-Z][A-Za-z.'\-]+(?:\s+[A-Z][A-Za-z.'\-]+){0,3}\s+\d{1,3}\s+(.+)$"
    )
    for page in pages[:max_scan]:
        if not page or not is_toc_text(page):
            # Still try New Yorker style contents even if heuristic is soft
            sample = (page or "")[:2500]
            if not re.search(r"\b(contents|goings\s+on|talk\s+of\s+the\s+town)\b", sample, re.I):
                if not re.search(r"[A-Za-z]+\s+\d{1,3}\s+[A-Z]", sample):
                    continue
        for ln in (page or "").splitlines():
            s = re.sub(r"\s+", " ", ln).strip()
            if not s or len(s) < 8:
                continue
            m = author_num.match(s)
            if m:
                cand = m.group(1).strip(" ,;-.")
                # Truncate at sentence / deck
                cand = re.split(r"(?<=[.!?])\s+", cand)[0].strip()
                if 3 <= len(cand) <= 110 and not is_weak_magazine_title(cand):
                    titles.append(cand)
                    continue
            # "Title ........ 12" dotted TOC
            m2 = re.match(r"^(.{6,90}?)\s*\.{2,}\s*\d{1,3}\s*$", s)
            if m2:
                cand = m2.group(1).strip()
                if not is_weak_magazine_title(cand):
                    titles.append(cand)
    # de-dupe preserve order
    seen: set[str] = set()
    out: list[str] = []
    for t in titles:
        key = t.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(t)
    return out


def _map_printed_page_to_index(pages: list[str], printed: int) -> Optional[int]:
    """Map a printed magazine page number to a 0-based PDF page index."""
    if printed < 0:
        return None
    patterns = [
        re.compile(rf"^{printed}\s+THE\s+NEW\s+YORKER\b", re.I),
        re.compile(rf"^THE\s+NEW\s+YORKER,[^\n]{{0,40}}\s{printed}\b", re.I),
        re.compile(rf"^{printed}\s+[A-Z]", re.I),
        re.compile(rf"\b{printed}\s+THE\s+NEW\s+YORKER\b", re.I),
    ]
    for i, page in enumerate(pages):
        head = re.sub(r"\s+", " ", (page or "")[:120]).strip()
        if any(p.search(head) for p in patterns):
            return i
    # Common New Yorker offset: PDF index ≈ printed + 1 (cover + front matter)
    guess = printed + 1
    if 0 <= guess < len(pages):
        return guess
    if 0 <= printed < len(pages):
        return printed
    return None


def _outline_from_front_matter(pages: list[str]) -> list[dict[str, Any]]:
    """
    Build a pseudo-outline from Contributors / Contents pages.

    Prefers quoted titles with page refs: (“Cash and Carry,” p. 1 2 ).
    Falls back to Author + page + Title listings on Contents.
    """
    scan = pages[:10]
    found: list[tuple[int, str]] = []  # (pdf_index, title)

    quote_pat = re.compile(
        r"[“\"]([^”\"]+?)[,”\"]+\s*p\.\s*([\d\s]+)",
        re.I,
    )
    for page in scan:
        text = page or ""
        for m in quote_pat.finditer(text):
            title = re.sub(r"\s+", " ", m.group(1)).strip(" .,;:")
            digits = re.sub(r"\D", "", m.group(2) or "")
            if not title or not digits:
                continue
            printed = int(digits)
            idx = _map_printed_page_to_index(pages, printed)
            if idx is None:
                continue
            if is_weak_magazine_title(title):
                continue
            found.append((idx, title))

    if len(found) < 3:
        # Contents: "David Sedaris 12 Cash and Carry New York, for richer..."
        author_page = re.compile(
            r"\b([A-Z][a-z]+(?:\s+[A-Z][a-z.'\-]+){0,3})\s+(\d{1,3})\s+"
            r"([A-Z][A-Za-z0-9'’\-, ]{2,80}?)"
            r"(?=\s+(?:[A-Z]{2,}(?:\s+[A-Z&/]+){0,4}\s+[A-Z][a-z]|[A-Z][a-z]+\s+[A-Z][a-z]+\s+\d{1,3}\b)|"
            r"\s+[A-Z][a-z]+(?:\s+[a-z]+){3,}|\.|$)"
        )
        for page in scan:
            text = re.sub(r"\s+", " ", page or "")
            if not re.search(r"\b(contents|personal history|profiles|fiction)\b", text, re.I):
                if "Sedaris" not in text and "GOINGS ON" not in text.upper():
                    continue
            for m in author_page.finditer(text):
                printed = int(m.group(2))
                raw_title = m.group(3).strip()
                # Truncate deck: keep Title-Case / small-word run
                words = raw_title.split()
                kept: list[str] = []
                for w in words:
                    core = re.sub(r"[^A-Za-z']", "", w)
                    if not core:
                        break
                    if core.lower() in _SMALL_WORDS or (core[0].isupper() and not core.islower()):
                        kept.append(w.strip(",;:"))
                        if w.endswith((",", ".", ";", ":")):
                            break
                        continue
                    break
                title = " ".join(kept).strip(" .,;:")
                if len(title.split()) < 2 or is_weak_magazine_title(title):
                    continue
                idx = _map_printed_page_to_index(pages, printed)
                if idx is None:
                    continue
                found.append((idx, title))

    # de-dupe by page (keep first = contributors order often best)
    by_page: dict[int, str] = {}
    for idx, title in found:
        if idx not in by_page:
            by_page[idx] = title
    outline = [
        {"title": title, "page": page, "level": 0}
        for page, title in sorted(by_page.items())
    ]
    return outline


def _strip_leading_page_chrome(text: str) -> str:
    s = re.sub(r"\s+", " ", (text or "")).strip()
    s = re.sub(
        r"^(?:\d{1,3}\s+)?(?:THE\s+NEW\s+YORKER(?:,\s*[A-Z]+\s+\d{1,2},\s*\d{4})?\s*)+"
        r"(?:\d{1,3}\s+)?",
        "",
        s,
        flags=re.I,
    )
    s = re.sub(
        r"^(?:JANUARY|FEBRUARY|MARCH|APRIL|MAY|JUNE|JULY|AUGUST|SEPTEMBER|"
        r"OCTOBER|NOVEMBER|DECEMBER)\s+\d{1,2},\s*\d{4}\s*PRICE\s*\$?\d[\d.]*\s*",
        "",
        s,
        flags=re.I,
    )
    return s.strip()


def _heading_from_dense_page(page_text: str) -> str:
    """Extract ALL-CAPS article title from dense single-line PDF pages."""
    s = _strip_leading_page_chrome(page_text)
    if not s:
        return ""
    # SECTION (optional) + ALL CAPS TITLE + Title-case deck
    m = re.match(
        r"^(?:"
        r"(?P<section>(?:[A-Z][A-Z0-9&'’\-/]+(?:\s+[A-Z][A-Z0-9&'’\-/]+){0,5}))\s+"
        r")?"
        r"(?P<title>[A-Z][A-Z0-9&'’\-/]+(?:\s+(?:AND|OF|THE|A|AN|&)|(?:\s+[A-Z][A-Z0-9&'’\-/]+)){0,10})"
        r"(?:\s+(?P<deck>[A-Z][a-z].*))?$",
        s,
    )
    if not m:
        return ""
    title = re.sub(r"\s+", " ", (m.group("title") or "")).strip()
    section = re.sub(r"\s+", " ", (m.group("section") or "")).strip()
    # Avoid treating long section-only chrome as the article title
    if section and title.upper() == section.upper():
        return ""
    if is_weak_magazine_title(title):
        return ""
    # Prefer title-case form when available from deck start? keep ALL CAPS → title()
    # Convert screaming caps to Title Case for display
    if title.isupper() and len(title) > 3:
        parts = []
        for w in title.split():
            if w.lower() in _SMALL_WORDS:
                parts.append(w.lower())
            else:
                parts.append(w.capitalize())
        if parts:
            parts[0] = parts[0].capitalize()
        title = " ".join(parts)
    if len(title) < 3 or len(title) > 90:
        return ""
    return title


def chunk_magazine_by_page_headings(pages: list[str]) -> list[dict[str, Any]]:
    """
    No-outline fallback: start a new article when a page opens with a heading.

    Prefers Contributors/Contents page maps when available (New Yorker PDFs).
    Optionally renames titles using Contents-page heuristics when a close match
    exists. Pages without a new heading continue the previous article.
    """
    if not pages:
        return []

    front_outline = _outline_from_front_matter(pages)
    if len(front_outline) >= 3:
        outlined = chunk_magazine_from_outline(pages, front_outline)
        if outlined:
            return outlined

    toc_titles = _titles_from_contents_pages(pages)
    boundaries: list[tuple[int, str]] = []
    for i, page in enumerate(pages):
        heading = _heading_from_page(page or "") or _heading_from_dense_page(page or "")
        if not heading:
            continue
        # Prefer Contents wording when it contains / matches the page heading
        title = heading
        hl = heading.lower()
        for ct in toc_titles:
            cl = ct.lower()
            if hl == cl or hl in cl or cl in hl:
                title = ct
                break
        boundaries.append((i, title))

    if not boundaries:
        return []

    # Merge consecutive same-title starts
    merged: list[tuple[int, str]] = []
    for start, title in boundaries:
        if merged and merged[-1][1].lower() == title.lower():
            continue
        merged.append((start, title))

    chunks: list[dict[str, Any]] = []
    # Leading pages before first heading
    first_start = merged[0][0]
    if first_start > 0:
        lead = "\n\n".join(
            (p or "").strip() for p in pages[:first_start] if (p or "").strip()
        ).strip()
        if lead and (is_toc_text(lead) or len(lead.split()) >= 25):
            chunks.append(
                {
                    "chunk_index": 0,
                    "text": lead,
                    "title": "Contents" if is_toc_text(lead) else "Front matter",
                    "is_toc": is_toc_text(lead),
                    "start_page": 0,
                    "end_page": first_start - 1,
                }
            )

    for i, (start, title) in enumerate(merged):
        end = merged[i + 1][0] if i + 1 < len(merged) else len(pages)
        text = "\n\n".join(
            (p or "").strip() for p in pages[start:end] if (p or "").strip()
        ).strip()
        if not text:
            continue
        chunks.append(
            {
                "chunk_index": len(chunks),
                "text": text,
                "title": title,
                "is_toc": is_toc_text(text),
                "start_page": start,
                "end_page": end - 1,
            }
        )

    for i, c in enumerate(chunks):
        c["chunk_index"] = i
    return chunks


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
