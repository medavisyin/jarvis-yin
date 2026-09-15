"""Tests for reading-text normalization."""

from __future__ import annotations

import os
import sys

_RAG = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "scripts", "rag"))
if _RAG not in sys.path:
    sys.path.insert(0, _RAG)

from intensive_reading.text_format import normalize_reading_text  # noqa: E402


def test_normalize_adds_space_after_sentence():
    raw = "He waited.Then the plane rose."
    out = normalize_reading_text(raw)
    assert "waited. Then" in out


def test_normalize_joins_hyphenated_linewrap():
    raw = "The wonder-\nful voyage began."
    out = normalize_reading_text(raw)
    assert "wonderful" in out
    assert "-\n" not in out


def test_normalize_single_newlines_become_spaces():
    raw = "First line\ncontinues here.\n\nNew paragraph starts."
    out = normalize_reading_text(raw)
    assert "First line continues here." in out
    assert "\n\n" in out


# Mimic pypdf default extract_text() for Then We Came to the End ch.1 p.23:
# single \n is both a line wrap and a paragraph start.
_CHAPTER1_PAGE = """\
LAYOFFS — TOM'S FINAL HOUR — JANINE GORJANC'S TRAGEDY —
THE DOWNTURN — DRASTIC MEASURES — THE DEBATE OVER TOM —
CREEPY PICTURES — THE STORY OF TOM MOTA'S CHAIR —
WALKING SPANISH DOWN THE HALL — SANDERSON — TWO E-MAILS —
THE STORY OF TOM MOTA'S CHAIR, PART II — THE PRO BONO
FUND-RAISER ADS — LASTIVE ACID — LYNN MASON
LAYOFFS WERE UPON US. They had been rumored for months,
but now it was official. If you were lucky, you could sue. If you were
black, aged, female, Catholic, Jewish, gay, obese, or physically
handicapped, at least you had grounds. At one point or another we
have all been deposed. We plan on being deposed for Tom's suit —
we have no doubt there will be one. Though he has no grounds
unless asshole has been added to the list. And that's not just us
talking. His ex-wife hates the guy. Restraining order. He can't see
his two young kids without supervision. She moved to Phoenix
just to get away from him. We wouldn't call him an asshole with-
out having reached a very high consensus. Amber Ludwig objects
to the specific designation because she has objected to profanity
since becoming pregnant, but really there is no other word, and
her objection is really just an abstention.
When Tom found out he was being let go, he wanted to throw
his computer against his office window. Benny Shassburger was in
there with him. Benny wasn't like a great friend of Tom's or any-
thing but he was the guy who on occasion would have lunch with
Tom and then report back to the rest of us. Word spread fast that
Tom had been laid off and naturally Benny was the guy to go
15
1
"""


def test_normalize_splits_pdf_paragraph_at_short_sentence_line():
    out = normalize_reading_text(_CHAPTER1_PAGE)
    paras = [p.strip() for p in out.split("\n\n") if p.strip()]
    layoff = next((p for p in paras if p.startswith("LAYOFFS WERE UPON US.")), None)
    tom = next((p for p in paras if p.startswith("When Tom found out he was being let go")), None)
    assert layoff is not None
    assert tom is not None
    assert layoff != tom
    assert "When Tom found out" not in layoff
    assert "LAYOFFS WERE UPON US." not in tom
    assert "months, but now it was official" in layoff
    assert "without having reached" in layoff
    assert "wonderful" not in layoff  # sanity: hyphen join is "without" not leftover
    assert "with- out" not in layoff
    assert "go 15" not in out
    assert "15" not in out.split()
    assert "the guy to go" in tom


def test_normalize_keeps_allcaps_heading_separate_from_body():
    out = normalize_reading_text(_CHAPTER1_PAGE)
    paras = [p.strip() for p in out.split("\n\n") if p.strip()]
    heading = next((p for p in paras if p.startswith("LAYOFFS —")), None)
    body = next((p for p in paras if p.startswith("LAYOFFS WERE UPON US.")), None)
    assert heading is not None
    assert body is not None
    assert "LAYOFFS WERE UPON US." not in heading
    assert "LYNN MASON" in heading


def test_normalize_does_not_treat_allcaps_sentence_as_heading():
    # Full-width ALL-CAPS line ending a sentence must wrap into the next
    # mixed-case line, not flush as a heading block.
    raw = (
        "THEY SAID THE LAYOFFS WERE UPON US AND NOBODY COULD STOP WHAT WAS COMING NEXT.\n"
        "They had been rumored for months, but now it was official if you were lucky."
    )
    out = normalize_reading_text(raw)
    paras = [p.strip() for p in out.split("\n\n") if p.strip()]
    assert len(paras) == 1
    assert paras[0].startswith("THEY SAID THE LAYOFFS WERE UPON US")
    assert "They had been rumored" in paras[0]


def test_normalize_keeps_short_allcaps_title_separate():
    raw = "PREFACE\nWhen I was young I lived in Chicago and the winters were long."
    out = normalize_reading_text(raw)
    paras = [p.strip() for p in out.split("\n\n") if p.strip()]
    assert paras[0] == "PREFACE"
    assert paras[1].startswith("When I was young")


def test_normalize_is_idempotent_on_reconstructed_text():
    once = normalize_reading_text(_CHAPTER1_PAGE)
    twice = normalize_reading_text(once)
    assert once == twice


def test_normalize_preserves_epub_style_paragraph_breaks():
    raw = "Paragraph one ends here.\n\nParagraph two begins here."
    out = normalize_reading_text(raw)
    assert out == "Paragraph one ends here.\n\nParagraph two begins here."
