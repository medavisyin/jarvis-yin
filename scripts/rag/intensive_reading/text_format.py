"""Normalize extracted book/magazine text for readable display."""

from __future__ import annotations

import re
import statistics

_SENT_END = re.compile(r"[.!?][\"'”’)]?$")
_LOWER_START = re.compile(r"^[a-zà-ÿ]")
_PAGE_NUM = re.compile(r"^\d{1,3}$")


def _is_heading_line(s: str) -> bool:
    # Sentence-ending lines are body (possibly shouty), not headings.
    if _SENT_END.search(s):
        return False
    letters = [c for c in s if c.isalpha()]
    if len(letters) < 6:
        return False
    upper = sum(1 for c in letters if c.isupper())
    return upper / len(letters) >= 0.7


def reconstruct_pdf_paragraphs(text: str) -> str:
    """
    Turn pypdf line breaks into paragraph breaks.

    Default extract_text() uses a single newline for both wrapped lines
    and new paragraphs. Keep wrapping (lowercase / hyphen), start a new
    paragraph when the previous visual line is a short sentence ending
    or when leaving an ALL-CAPS heading block. Drop isolated page numbers.
    """
    if not text:
        return ""

    lines = [ln.strip() for ln in text.split("\n")]
    kept: list[str] = []
    for ln in lines:
        if _PAGE_NUM.fullmatch(ln):
            continue
        kept.append(ln)

    nonempty = [ln for ln in kept if ln]
    if not nonempty:
        return ""
    med = float(statistics.median(len(ln) for ln in nonempty))

    paras: list[str] = []
    buf: list[str] = []

    def flush() -> None:
        if not buf:
            return
        piece = buf[0]
        for ln in buf[1:]:
            if piece.endswith("-") and ln[:1].islower():
                piece = piece[:-1] + ln
            else:
                piece = piece + " " + ln
        paras.append(piece)
        buf.clear()

    for ln in kept:
        if not ln:
            flush()
            continue
        prev = buf[-1] if buf else None
        if prev is None:
            buf.append(ln)
            continue
        if _is_heading_line(prev) and _is_heading_line(ln):
            buf.append(ln)
            continue
        if _is_heading_line(prev) and not _is_heading_line(ln):
            flush()
            buf.append(ln)
            continue
        if _LOWER_START.match(ln):
            buf.append(ln)
            continue
        if prev.endswith("-"):
            buf.append(ln)
            continue
        if _SENT_END.search(prev) and len(prev) <= med * 0.85:
            flush()
            buf.append(ln)
            continue
        buf.append(ln)
    flush()
    return "\n\n".join(paras)


def normalize_reading_text(text: str) -> str:
    """
    Clean PDF/EPUB extraction artifacts for reading.

    Fixes common issues: hyphenated line wraps, mid-sentence newlines,
    missing spaces after punctuation, collapsed whitespace.
    """
    if not text:
        return ""

    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = text.replace("\u00ad", "")  # soft hyphen
    text = text.replace("\u200b", "")  # zero-width space
    text = text.replace("\xa0", " ")

    # Join words split across lines with a hyphen: wonder-\nful → wonderful
    text = re.sub(r"([A-Za-z])-\n([A-Za-z])", r"\1\2", text)

    text = reconstruct_pdf_paragraphs(text)

    # Collapse runs of spaces/tabs
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r" *\n *", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)

    # Missing space after sentence / clause punctuation before next word.
    # Do not collapse intentional paragraph breaks (\n\n).
    def _fix_punct_gap(m: re.Match) -> str:
        punct, quote, ws, cap = m.group(1), m.group(2) or "", m.group(3) or "", m.group(4)
        if "\n\n" in ws:
            return m.group(0)
        return f"{punct}{quote} {cap}"

    text = re.sub(r"([.!?])([\"'”’]?)(\s*)([A-Z])", _fix_punct_gap, text)
    text = re.sub(r",([A-Za-z\"'])", r", \1", text)
    text = re.sub(r":([A-Za-z\"'])", r": \1", text)
    text = re.sub(r";([A-Za-z\"'])", r"; \1", text)
    text = re.sub(r"([A-Za-z])\(", r"\1 (", text)

    # Quote opening without space — he said"Hello → he said "Hello
    text = re.sub(r'([a-z])([\"“])([A-Z])', r"\1 \2\3", text)

    # Trim each paragraph
    paras = [p.strip() for p in text.split("\n\n")]
    paras = [p for p in paras if p]
    return "\n\n".join(paras)
