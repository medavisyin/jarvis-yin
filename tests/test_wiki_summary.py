"""Readable Wiki Fetch summaries: clean noise, then 1–2 sentence English blurbs."""

from __future__ import annotations

import os
import sys

_RAG = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "scripts", "rag"))
if _RAG not in sys.path:
    sys.path.insert(0, _RAG)

from wiki_summary import (  # noqa: E402
    build_summary_context,
    clean_change_text,
    format_wiki_report,
    summarize_wiki_page,
)

JAN_C5_DIFF = (
    "Added (2 lines): InformMe | Additional cloud services (e.g. future portal4med SaaS , "
    "synavaAI , CloudPACS ) will be brought into scope as they reach productive cloud operation."
)
JAN_BLOG_DIFF = "false center https://medavis.atlassian.net/wiki/spaces/KOMT/blog/2146926698/Tech-Update+Juli+2026 false 600"
JAN_ASM_DIFF = (
    "Removed (3 lines): Canonical source: Tech/Security/Cybersecurity (intcube)/ASM Security "
    "Review/synava-ASM-endpoints-2026.md in the ris workspace. Last synced: 2026-08-04."
)


def test_clean_change_text_drops_blog_macro_layout():
    cleaned = clean_change_text(JAN_BLOG_DIFF)
    assert cleaned == ""
    assert "false" not in cleaned.lower()
    assert "https://" not in cleaned


def test_clean_change_text_keeps_substantive_c5_lines():
    cleaned = clean_change_text(JAN_C5_DIFF)
    assert "InformMe" in cleaned
    assert "cloud" in cleaned.lower()
    assert "Added (2 lines)" not in cleaned


def test_clean_change_text_drops_lone_digit():
    assert clean_change_text("1") == ""


def test_build_summary_context_falls_back_to_excerpt_when_diff_is_junk():
    page = {
        "title": "💥 Tech-Update Juli 2026",
        "version_number": 2,
        "change_summary": JAN_BLOG_DIFF,
        "summary": (
            "July tech update covers license-management dashboards, product demo "
            "environments, and developer infrastructure changes."
        ),
    }
    ctx = build_summary_context(page)
    assert "license-management" in ctx.lower()
    assert "false center" not in ctx
    assert "Page title:" in ctx


def test_build_summary_context_empty_when_diff_and_excerpt_are_junk():
    page = {
        "title": "Security & Compliance",
        "version_number": 2,
        "change_summary": "1",
        "summary": "1",
    }
    assert build_summary_context(page) == ""


def test_build_summary_context_for_new_page_uses_title_when_body_is_junk():
    page = {
        "title": "💥 Tech-Update Juli 2026",
        "space": "synava Technology",
        "version_number": 1,
        "change_summary": JAN_BLOG_DIFF,
        "summary": JAN_BLOG_DIFF,
        "headings": ["License dashboards", "Demo environments"],
    }
    ctx = build_summary_context(page)
    assert "Tech-Update Juli 2026" in ctx
    assert "synava Technology" in ctx
    assert "License dashboards" in ctx
    assert "false center" not in ctx
    assert "new page" in ctx.lower()


def test_format_wiki_report_shows_ai_summary_not_raw_diff_or_sections():
    pages = {
        "Jan Loeffler": [
            {
                "title": "C5 Compliance",
                "url": "https://example/wiki/c5",
                "space": "synava Technology",
                "modified_at": "2026-08-04",
                "version_number": 3,
                "change_summary": JAN_C5_DIFF,
                "headings": ["TL;DR", "What is C5?"],
                "ai_summary": (
                    "InformMe was added to C5 cloud-product scope; other SaaS stays out "
                    "until it is in productive cloud operation."
                ),
            }
        ]
    }
    report = format_wiki_report(
        users=["Jan Loeffler"],
        date_from="2026-07-04",
        date_to="2026-08-04",
        total_pages=1,
        total_chunks=4,
        summary_lines=["[Jan Loeffler] 1 pages, 4 chunks"],
        all_user_pages=pages,
    )
    assert "[C5 Compliance](https://example/wiki/c5)" in report
    assert "InformMe was added to C5 cloud-product scope" in report
    assert "Added (" not in report
    assert "Removed (" not in report
    assert "Sections:" not in report
    assert "TL;DR" not in report


def test_format_wiki_report_omits_blurb_when_ai_summary_missing():
    pages = {
        "Jan Loeffler": [
            {
                "title": "Security & Compliance",
                "url": "https://example/wiki/sec",
                "space": "synava Technology",
                "modified_at": "2026-08-04",
                "version_number": 2,
                "change_summary": "1",
                "summary": "1",
                "headings": ["Overview"],
            }
        ]
    }
    report = format_wiki_report(
        users=["Jan Loeffler"],
        date_from="",
        date_to="",
        total_pages=1,
        total_chunks=1,
        summary_lines=[],
        all_user_pages=pages,
    )
    assert "Security & Compliance" in report
    assert "Added (" not in report
    assert "Sections:" not in report
    assert "> 1" not in report


class _OkResp:
    def raise_for_status(self):
        return None

    def json(self):
        return {
            "message": {
                "content": (
                    "InformMe was added to C5 cloud-product scope so teams know which "
                    "SaaS is in the audit."
                )
            }
        }


def test_summarize_wiki_page_uses_ollama_and_asks_why_it_matters():
    captured = {}

    def fake_post(url, json=None, timeout=None):
        captured["url"] = url
        captured["json"] = json
        captured["timeout"] = timeout
        return _OkResp()

    page = {
        "title": "C5 Compliance",
        "version_number": 3,
        "change_summary": JAN_C5_DIFF,
        "version_message": "",
        "summary": "",
    }
    result = summarize_wiki_page(
        page,
        host="http://localhost:11434",
        model="qwen3:1.7b",
        http_post=fake_post,
    )
    assert "InformMe" in result
    assert captured["url"].endswith("/api/chat")
    system = captured["json"]["messages"][0]["content"].lower()
    assert "why it matters" in system
    user = captured["json"]["messages"][1]["content"]
    assert "InformMe" in user
    assert "Added (2 lines)" not in user


def test_summarize_wiki_page_empty_on_http_error_without_calling_fallback_diff():
    def boom(*_a, **_k):
        raise TimeoutError("ollama down")

    page = {
        "title": "C5 Compliance",
        "version_number": 3,
        "change_summary": JAN_C5_DIFF,
        "summary": JAN_C5_DIFF,
    }
    assert summarize_wiki_page(page, http_post=boom) == ""


def test_summarize_wiki_page_skips_llm_when_nothing_substantive():
    def must_not_call(*_a, **_k):
        raise AssertionError("LLM should not be called for empty context")

    page = {
        "title": "Security & Compliance",
        "version_number": 2,
        "change_summary": JAN_BLOG_DIFF,
        "summary": "1",
    }
    assert summarize_wiki_page(page, http_post=must_not_call) == ""


class _NewPageResp:
    def raise_for_status(self):
        return None

    def json(self):
        return {
            "message": {
                "content": (
                    "July 2026 tech update for synava Technology covering recent "
                    "platform and tooling changes."
                )
            }
        }


def test_summarize_wiki_page_new_page_with_macro_junk_still_summarizes_topic():
    captured = {}

    def fake_post(url, json=None, timeout=None):
        captured["json"] = json
        return _NewPageResp()

    page = {
        "title": "💥 Tech-Update Juli 2026",
        "space": "synava Technology",
        "version_number": 1,
        "change_summary": JAN_BLOG_DIFF,
        "summary": JAN_BLOG_DIFF,
        "headings": [],
    }
    result = summarize_wiki_page(page, http_post=fake_post)
    assert "tech update" in result.lower()
    system = captured["json"]["messages"][0]["content"].lower()
    assert "what the page" in system or "what this page" in system
    user = captured["json"]["messages"][1]["content"]
    assert "Tech-Update Juli 2026" in user
    assert "new page" in user.lower()
    assert "false center" not in user
