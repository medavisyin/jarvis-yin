"""Normalize extracted book/magazine text for readable display."""

from __future__ import annotations

import re


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

    # Preserve paragraph breaks; turn single newlines into spaces
    text = re.sub(r"(?<!\n)\n(?!\n)", " ", text)

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
