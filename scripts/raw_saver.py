"""
Raw content saver — shared helper for fetch scripts to save drill-down content.

When SAVE_RAW env var is set to "1" (or --save-raw flag is used), fetch scripts
call save_raw_content() after each drill-down to persist the full article text
as a Markdown file in <output_dir>/raw/.

The saved files are used by the Learning Archive feature for deeper study.
"""
import os
import re
from typing import List, Optional


def _slugify(text: str, max_len: int = 50) -> str:
    """Convert text to a filesystem-safe slug."""
    text = text.lower().strip()
    text = re.sub(r'[^\w\s-]', '', text)
    text = re.sub(r'[\s_]+', '-', text)
    text = re.sub(r'-+', '-', text).strip('-')
    return text[:max_len]


def should_save_raw() -> bool:
    """Check if raw content saving is enabled."""
    return os.environ.get("SAVE_RAW", "0") == "1"


def save_raw_content(
    output_dir: str,
    source_slug: str,
    item_index: int,
    title: str,
    url: str,
    date: Optional[str],
    paragraphs: List[str],
    difficulty: str = "intermediate",
    extra_notes: Optional[List[str]] = None,
) -> Optional[str]:
    """
    Save raw drill-down content as a Markdown file.

    Args:
        output_dir: Base output directory (e.g., _briefing_tmp)
        source_slug: Short source name (e.g., "arxiv-ml", "anthropic")
        item_index: 0-based index of the item within the source
        title: Article/paper title
        url: Original URL
        date: Publication date (if available)
        paragraphs: List of paragraph texts (full, untruncated)
        difficulty: "beginner", "intermediate", or "advanced"
        extra_notes: Optional list of extra notes (e.g., "[See visual data]")

    Returns:
        Path to the saved file, or None if saving is disabled/fails.
    """
    if not should_save_raw():
        return None

    raw_dir = os.path.join(output_dir, "raw")
    os.makedirs(raw_dir, exist_ok=True)

    slug = _slugify(title)
    filename = f"{source_slug}-{item_index + 1:02d}-{slug}.md"
    filepath = os.path.join(raw_dir, filename)

    lines = [f"# {title}", ""]
    lines.append(f"**Source:** {url}")
    if date:
        lines.append(f"**Date:** {date}")
    lines.append(f"**Difficulty:** {difficulty}")
    lines.append("")
    lines.append("---")
    lines.append("")

    for para in paragraphs:
        para = para.strip()
        if para:
            lines.append(para)
            lines.append("")

    if extra_notes:
        lines.append("---")
        lines.append("")
        lines.append("**Notes:**")
        for note in extra_notes:
            lines.append(f"- {note}")
        lines.append("")

    try:
        with open(filepath, "w", encoding="utf-8") as f:
            f.write("\n".join(lines))
        return filepath
    except Exception:
        return None
