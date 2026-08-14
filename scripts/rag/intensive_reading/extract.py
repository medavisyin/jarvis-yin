"""Extract text from PDF and EPUB for intensive reading."""

from __future__ import annotations

import os
import re
import zipfile
from typing import Any
from xml.etree import ElementTree as ET

from bs4 import BeautifulSoup

from intensive_reading.chunking import normalize_magazine_section_title

# Zip-bomb / DoS guards for EPUB extraction
_MAX_EPUB_ENTRIES = 800
_MAX_EPUB_TEXT_ENTRY_BYTES = 2 * 1024 * 1024  # 2 MiB per HTML/XML we actually read
_MAX_EPUB_ASSET_ENTRY_BYTES = 25 * 1024 * 1024  # covers/fonts may be large; we do not read them
_MAX_EPUB_TEXT_TOTAL_BYTES = 40 * 1024 * 1024  # sum of text-like entries only

_TEXT_SUFFIXES = (
    ".xhtml", ".html", ".htm", ".xml", ".opf", ".ncx", ".txt",
)


def _is_epub_text_entry(filename: str) -> bool:
    name = (filename or "").replace("\\", "/").lower()
    # Ignore directory placeholders
    if not name or name.endswith("/"):
        return False
    return name.endswith(_TEXT_SUFFIXES)


def extract_pdf_pages(filepath: str) -> list[str]:
    """Return one string per PDF page."""
    from pypdf import PdfReader
    from intensive_reading.text_format import normalize_reading_text

    reader = PdfReader(filepath)
    pages: list[str] = []
    for page in reader.pages:
        try:
            text = page.extract_text() or ""
        except Exception:
            text = ""
        pages.append(normalize_reading_text(text))
    return pages


def extract_pdf_outline(filepath: str) -> list[dict[str, Any]]:
    """
    Flatten PDF bookmarks into [{title, page, level}, ...] (0-based page).

    Nested outlines keep depth as ``level``. Missing / unresolvable destinations
    are skipped. Empty outline → [].
    """
    from pypdf import PdfReader

    if not os.path.isfile(filepath):
        raise FileNotFoundError(filepath)

    reader = PdfReader(filepath)
    outline = getattr(reader, "outline", None) or []
    if not outline:
        return []

    out: list[dict[str, Any]] = []

    def walk(items: Any, depth: int = 0) -> None:
        if not items:
            return
        for it in items:
            if isinstance(it, list):
                walk(it, depth + 1)
                continue
            title = (getattr(it, "title", None) or "").strip()
            if not title:
                continue
            try:
                page = reader.get_destination_page_number(it)
            except Exception:
                continue
            if page is None or int(page) < 0:
                continue
            out.append({"title": title, "page": int(page), "level": int(depth)})

    walk(outline, 0)
    return out


def _html_to_text(html: str) -> str:
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "nav"]):
        tag.decompose()
    for br in soup.find_all("br"):
        br.replace_with("\n")
    for block in soup.find_all(
        ["p", "div", "section", "article", "h1", "h2", "h3", "h4", "h5", "h6", "li", "blockquote", "tr"]
    ):
        # Mark block boundaries so paragraphs survive get_text()
        block.append("\n\n")
    text = soup.get_text(" ")
    from intensive_reading.text_format import normalize_reading_text

    return normalize_reading_text(text)


def _find_opf_path(zf: zipfile.ZipFile) -> str:
    try:
        raw = zf.read("META-INF/container.xml")
    except KeyError as e:
        raise ValueError("Invalid EPUB: missing META-INF/container.xml") from e
    root = ET.fromstring(raw)
    # container.xml uses default xmlns
    for el in root.iter():
        if el.tag.endswith("rootfile"):
            full = el.attrib.get("full-path")
            if full:
                return full.replace("\\", "/")
    raise ValueError("Invalid EPUB: no rootfile in container.xml")


def _opf_spine_hrefs(zf: zipfile.ZipFile, opf_path: str) -> tuple[str, list[tuple[str, str]]]:
    """Return (book_title, [(title_hint, href), ...]) in spine order."""
    opf_dir = os.path.dirname(opf_path).replace("\\", "/")
    raw = zf.read(opf_path)
    root = ET.fromstring(raw)

    def local(tag: str) -> str:
        return tag.rsplit("}", 1)[-1]

    title = "Untitled"
    for el in root.iter():
        if local(el.tag) == "title" and (el.text or "").strip():
            title = el.text.strip()
            break

    id_to_href: dict[str, str] = {}
    for el in root.iter():
        if local(el.tag) != "item":
            continue
        item_id = el.attrib.get("id")
        href = el.attrib.get("href")
        media = (el.attrib.get("media-type") or "").lower()
        if not item_id or not href:
            continue
        if "html" in media or href.lower().endswith((".xhtml", ".html", ".htm")):
            id_to_href[item_id] = href.replace("\\", "/")

    ordered: list[tuple[str, str]] = []
    for el in root.iter():
        if local(el.tag) != "itemref":
            continue
        idref = el.attrib.get("idref")
        if not idref or idref not in id_to_href:
            continue
        href = id_to_href[idref]
        full = href if not opf_dir else f"{opf_dir}/{href}"
        # normalize ..
        parts: list[str] = []
        for p in full.split("/"):
            if p == "..":
                if parts:
                    parts.pop()
            elif p and p != ".":
                parts.append(p)
        full = "/".join(parts)
        ordered.append((os.path.splitext(os.path.basename(href))[0], full))
    return title, ordered


def extract_epub_sections(filepath: str) -> list[dict[str, Any]]:
    """
    Extract spine-ordered text sections from an EPUB.

    Uses stdlib zipfile + BeautifulSoup (no ebooklib required).
    Each item: {"title": str, "text": str}
    """
    if not os.path.isfile(filepath):
        raise FileNotFoundError(filepath)

    sections: list[dict[str, Any]] = []
    with zipfile.ZipFile(filepath, "r") as zf:
        # Pre-scan: strict limits on text-like entries only.
        # Images/fonts/CSS are common >2MB (covers) and are never read for text.
        text_total = 0
        infos = zf.infolist()
        if len(infos) > _MAX_EPUB_ENTRIES:
            raise ValueError(
                f"EPUB has too many entries ({len(infos)} > {_MAX_EPUB_ENTRIES})"
            )
        for info in infos:
            name = info.filename or ""
            size = max(info.file_size, 0)
            if _is_epub_text_entry(name):
                if size > _MAX_EPUB_TEXT_ENTRY_BYTES:
                    raise ValueError(
                        f"EPUB text entry too large: {name} ({size} bytes)"
                    )
                text_total += size
                if text_total > _MAX_EPUB_TEXT_TOTAL_BYTES:
                    raise ValueError("EPUB text content exceeds safety limit")
            else:
                if size > _MAX_EPUB_ASSET_ENTRY_BYTES:
                    raise ValueError(
                        f"EPUB asset too large: {name} ({size} bytes)"
                    )

        opf_path = _find_opf_path(zf)
        book_title, spine = _opf_spine_hrefs(zf, opf_path)
        for hint, href in spine:
            # Spine should be HTML/XHTML; skip non-text (rare but possible)
            if not _is_epub_text_entry(href):
                continue
            try:
                info = zf.getinfo(href)
            except KeyError:
                continue
            if info.file_size > _MAX_EPUB_TEXT_ENTRY_BYTES:
                raise ValueError(f"EPUB spine entry too large: {href}")
            try:
                raw = zf.read(href)
            except KeyError:
                continue
            if len(raw) > _MAX_EPUB_TEXT_ENTRY_BYTES:
                raise ValueError(f"EPUB spine entry too large after read: {href}")
            try:
                html = raw.decode("utf-8")
            except UnicodeDecodeError:
                html = raw.decode("latin-1", errors="replace")
            text = _html_to_text(html)
            if not text:
                continue
            # Prefer first heading as title
            soup = BeautifulSoup(html, "html.parser")
            h = soup.find(["h1", "h2", "h3", "title"])
            title = (h.get_text(strip=True) if h else "") or hint or book_title
            title = normalize_magazine_section_title(title) or title
            sections.append({"title": title, "text": text, "book_title": book_title})
    return sections


def extract_book(filepath: str) -> dict[str, Any]:
    """
    Extract content from PDF or EPUB.

    Returns:
      {
        "format": "pdf"|"epub",
        "title": str,
        "pages": list[str] | None,      # PDF
        "sections": list[dict] | None,  # EPUB
      }
    """
    ext = os.path.splitext(filepath)[1].lower()
    title = os.path.splitext(os.path.basename(filepath))[0]
    if ext == ".pdf":
        pages = extract_pdf_pages(filepath)
        try:
            outline = extract_pdf_outline(filepath)
        except Exception:
            outline = []
        return {
            "format": "pdf",
            "title": title,
            "pages": pages,
            "sections": None,
            "outline": outline,
        }
    if ext == ".epub":
        sections = extract_epub_sections(filepath)
        if sections and sections[0].get("book_title"):
            title = sections[0]["book_title"]
        return {"format": "epub", "title": title, "pages": None, "sections": sections}
    raise ValueError(f"Unsupported format: {ext}")
