"""Shared Wiki Fetch page summaries: strip Confluence noise, then 1–2 English sentences."""

from __future__ import annotations

import os
import re
import sys
from typing import Any, Callable, Mapping

HttpPost = Callable[..., Any]

_ADDED_REMOVED_PREFIX = re.compile(
    r"^(?:Added|Removed)\s*\(\d+\s*lines?\)\s*:\s*",
    re.IGNORECASE,
)
_URL_RE = re.compile(r"https?://\S+", re.IGNORECASE)
_WORD_RE = re.compile(r"[A-Za-z]{3,}")
_THINK_RE = re.compile(r"</?think>", re.IGNORECASE)

_NOISE_TOKENS = {
    "true",
    "false",
    "center",
    "left",
    "right",
    "top",
    "bottom",
    "none",
    "auto",
    "block",
    "inline",
    "hidden",
    "visible",
    "width",
    "height",
    "image",
    "thumbnail",
}

_MIN_SUBSTANCE_WORDS = 6

_SYSTEM_PROMPT = (
    "You are a concise technical writer. Given a Confluence wiki page update, "
    "write 1-2 English sentences covering what actually changed and why it matters "
    "to a teammate catching up. Never use German. Ignore markup, layout attributes, "
    "image URLs, and wiki macros. If there is no substantive content, output nothing. "
    "Output only the summary, no labels or prefixes."
)

_SYSTEM_PROMPT_NEW = (
    "You are a concise technical writer. Given a new Confluence wiki page, "
    "write 1-2 English sentences covering what the page is about and why it matters "
    "to a teammate catching up. Never use German. Prefer the content excerpt; if the excerpt is missing "
    "or is wiki markup, infer the topic from the title, space, and headings. "
    "Always produce 1-2 sentences when a title is present. "
    "Ignore markup, layout attributes, image URLs, and wiki macros. "
    "Output only the summary, no labels or prefixes."
)


def _page_get(page: Mapping[str, Any], *keys: str, default: str = "") -> str:
    for key in keys:
        value = page.get(key)
        if value is None:
            continue
        text = str(value).strip()
        if text:
            return text
    return default


def _page_version(page: Mapping[str, Any]) -> int:
    raw = page.get(
        "version_number",
        page.get("version_number", page.get("version_number", 1)),
    )
    try:
        return int(raw)
    except (TypeError, ValueError):
        return 1


def _is_noise_token(token: str) -> bool:
    raw = token.strip().strip(".,;:()[]{}")
    if not raw:
        return True
    lower = raw.lower()
    if lower in _NOISE_TOKENS:
        return True
    if _URL_RE.fullmatch(raw):
        return True
    if re.fullmatch(r"\d+", raw):
        return True
    return False


def _is_noise_line(line: str) -> bool:
    text = line.strip()
    if not text:
        return True
    if _URL_RE.fullmatch(text):
        return True
    tokens = [t for t in re.split(r"\s+", text) if t]
    if tokens and all(_is_noise_token(t) for t in tokens):
        return True
    if len(_WORD_RE.findall(text)) == 0:
        return True
    return False


def _strip_added_removed_prefix(text: str) -> str:
    return _ADDED_REMOVED_PREFIX.sub("", text.strip())


def _iter_fragments(text: str) -> list[str]:
    fragments: list[str] = []
    for raw_line in (text or "").splitlines():
        line = _strip_added_removed_prefix(raw_line)
        for part in line.split(" | "):
            piece = part.strip()
            if piece:
                fragments.append(piece)
    if not fragments and (text or "").strip():
        fragments.append(_strip_added_removed_prefix(text))
    return fragments


def clean_change_text(text: str) -> str:
    """Drop Confluence layout/macro junk; keep real added/removed sentences."""
    kept = [frag for frag in _iter_fragments(text) if not _is_noise_line(frag)]
    return " | ".join(kept)


def _substance_words(text: str) -> int:
    return len(_WORD_RE.findall(text or ""))


def _headings_text(page: Mapping[str, Any]) -> str:
    raw = page.get("headings") or []
    if isinstance(raw, str):
        return raw.strip()
    if isinstance(raw, list):
        parts = [str(h).strip() for h in raw[:8] if str(h).strip()]
        return ", ".join(parts)
    return ""


def build_summary_context(page: Mapping[str, Any]) -> str:
    """Prefer cleaned diff; fall back to excerpt; new pages keep title/headings if body is junk."""
    title = _page_get(page, "title")
    space = _page_get(page, "space", "space_name")
    diff = clean_change_text(_page_get(page, "change_summary", "change_summary"))
    excerpt = clean_change_text(_page_get(page, "summary"))
    note = clean_change_text(
        _page_get(page, "version_message", "version_message", "version_message")
    )
    headings = _headings_text(page)
    is_new = _page_version(page) <= 1

    if _substance_words(diff) >= _MIN_SUBSTANCE_WORDS:
        body = diff
        label = "Changes in this update"
    elif _substance_words(excerpt) >= _MIN_SUBSTANCE_WORDS:
        body = excerpt
        label = "Content excerpt"
    elif is_new and title:
        body = ""
        label = ""
    else:
        return ""

    parts = [f"Page title: {title}"] if title else []
    if is_new:
        parts.append("This is a NEW page.")
    if space:
        parts.append(f"Space: {space}")
    if headings:
        parts.append(f"Headings: {headings}")
    if _substance_words(note) >= 3:
        parts.append(f"Author's edit note: {note}")
    if body and label:
        parts.append(f"{label}:\n{body}")
    return "\n".join(parts)


def _default_ollama() -> tuple[str, str]:
    host = os.environ.get("OLLAMA_HOST") or os.environ.get("OLLAMA_HOST") or "http://localhost:11434"
    model = (
        os.environ.get("OLLAMA_MODEL_FAST")
        or os.environ.get("OLLAMA_MODEL_FAST")
        or "qwen3:1.7b"
    )
    for name in ("__main__", "agent", "rag.agent"):
        mod = sys.modules.get(name)
        if mod is None:
            continue
        host = (
            getattr(mod, "OLLAMA_HOST", None)
            or getattr(mod, "OLLAMA_HOST", None)
            or host
        )
        model = (
            getattr(mod, "OLLAMA_MODEL_FAST", None)
            or getattr(mod, "OLLAMA_MODEL_FAST", None)
            or model
        )
    return host, model


def summarize_wiki_page(
    page: Mapping[str, Any],
    host: str | None = None,
    model: str | None = None,
    http_post: HttpPost | None = None,
) -> str:
    """Return a 1–2 sentence English summary, or '' on junk/failure."""
    context = build_summary_context(page)
    if not context:
        return ""

    default_host, default_model = _default_ollama()
    ollama_host = (host or default_host).rstrip("/")
    ollama_model = model or default_model
    is_new = _page_version(page) <= 1
    payload = {
        "model": ollama_model,
        "messages": [
            {
                "role": "system",
                "content": _SYSTEM_PROMPT_NEW if is_new else _SYSTEM_PROMPT,
            },
            {"role": "user", "content": context},
        ],
        "stream": False,
        "think": False,
        "options": {"temperature": 0.3, "num_predict": 200},
    }
    post = http_post
    if post is None:
        import requests

        post = requests.post
    try:
        resp = post(f"{ollama_host}/api/chat", json=payload, timeout=30)
        resp.raise_for_status()
        result = (resp.json().get("message") or {}).get("content") or ""
        return _THINK_RE.sub("", result).strip()
    except Exception:
        return ""


def attach_ai_summaries(
    all_user_pages: dict[str, list[dict]],
    host: str | None = None,
    model: str | None = None,
    http_post: HttpPost | None = None,
) -> dict[str, list[dict]]:
    """Mutate pages in place with ai_summary when the model returns text."""
    for pages in (all_user_pages or {}).values():
        for page in pages:
            text = summarize_wiki_page(page, host=host, model=model, http_post=http_post)
            if text:
                page["ai_summary"] = text
    return all_user_pages


def format_wiki_report(
    users: list[str],
    date_from: str,
    date_to: str,
    total_pages: int,
    total_chunks: int,
    summary_lines: list[str],
    all_user_pages: dict[str, list[dict]],
) -> str:
    """Markdown report: title/link/space/date/🆕 + AI sentence. Never raw diffs."""
    parts: list[str] = []
    date_info = ""
    if date_from or date_to:
        date_info = f" ({date_from or '...'} to {date_to or '...'})"
    parts.append(f"# Wiki Fetch Report{date_info}\n")
    parts.append(
        f"**{len(users)} team member(s), {total_pages} pages, {total_chunks} chunks indexed**\n"
    )
    for line in summary_lines:
        parts.append(f"- {line}")
    parts.append("")

    if all_user_pages:
        parts.append("---\n\n## Page Details\n")
        for user, details in all_user_pages.items():
            parts.append(f"### {user}\n")
            for page in details:
                title = _page_get(page, "title") or "Untitled"
                url = _page_get(page, "url")
                space = _page_get(page, "space", "space_name")
                modified = _page_get(
                    page, "modified_at", "modified_at", "modified_at", "updated_when"
                )
                is_new = _page_version(page) <= 1
                ai_summary = _page_get(page, "ai_summary")

                if url:
                    entry = f"- **[{title}]({url})**"
                else:
                    entry = f"- **{title}**"
                if space:
                    entry += f" — *{space}*"
                if modified:
                    entry += f" (modified: {modified})"
                if is_new:
                    entry += " \U0001f195"
                parts.append(entry)
                if ai_summary:
                    label = "Summary" if is_new else "Changes"
                    parts.append(f"  > **{label}:** {ai_summary}")
                parts.append("")

    return "\n".join(parts)
