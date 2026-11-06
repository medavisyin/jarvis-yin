"""Serve an EPUB's own HTML, images, and CSS without its scripts."""

from __future__ import annotations

import os
import posixpath
import re
import zipfile
from urllib.parse import quote

from bs4 import BeautifulSoup

from intensive_reading.chunking import is_toc_text
from intensive_reading.extract import _find_opf_path, _opf_spine_hrefs, _section_heading_text

_MAX_ASSET_BYTES = 25 * 1024 * 1024
_MIME = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".gif": "image/gif",
    ".webp": "image/webp",
    ".svg": "image/svg+xml",
    ".css": "text/css",
    ".woff": "font/woff",
    ".woff2": "font/woff2",
    ".ttf": "font/ttf",
    ".otf": "font/otf",
}
_CSS_URL = re.compile(r"url\(\s*(['\"]?)([^)'\"]+)\1\s*\)", re.I)
_DROP_TAGS = ("script", "iframe", "object", "embed", "base", "form")


def _zip_name(path: str) -> str:
    name = (path or "").replace("\\", "/").split("#", 1)[0].split("?", 1)[0].strip()
    if not name or name.startswith("/") or ":" in name:
        raise ValueError("Invalid EPUB path")
    parts: list[str] = []
    for part in name.split("/"):
        if part in ("", "."):
            continue
        if part == "..":
            raise ValueError("Invalid EPUB path")
        parts.append(part)
    if not parts:
        raise ValueError("Invalid EPUB path")
    return "/".join(parts)


def resolve_epub_ref(base_href: str, ref: str) -> str | None:
    """Resolve a relative EPUB URL against the file that contains it."""
    raw = (ref or "").strip().strip("\"'")
    if not raw:
        return None
    lower = raw.lower()
    if lower.startswith(("#", "data:", "mailto:", "javascript:", "http://", "https://")):
        return None
    raw = raw.split("#", 1)[0].split("?", 1)[0]
    if not raw:
        return None
    if raw.startswith("/"):
        return _zip_name(raw[1:])
    base = _zip_name(base_href)
    return _zip_name(posixpath.normpath(posixpath.join(posixpath.dirname(base), raw)))


def asset_url(prefix: str, zip_path: str) -> str:
    return f"{prefix}?path={quote(zip_path, safe='/')}"


def _rewrite_css(css: str, css_href: str, asset_prefix: str) -> str:
    def repl(match: re.Match[str]) -> str:
        try:
            target = resolve_epub_ref(css_href, match.group(2).strip())
        except ValueError:
            return match.group(0)
        if not target:
            return match.group(0)
        return f"url({asset_url(asset_prefix, target)})"

    return _CSS_URL.sub(repl, css)


def _rewrite_srcset(value: str, doc_href: str, asset_prefix: str) -> str:
    parts: list[str] = []
    for item in value.split(","):
        bits = item.strip().split()
        if not bits:
            continue
        try:
            target = resolve_epub_ref(doc_href, bits[0])
        except ValueError:
            target = None
        if target:
            bits[0] = asset_url(asset_prefix, target)
        parts.append(" ".join(bits))
    return ", ".join(parts)


def spine_documents(filepath: str) -> list[dict[str, str]]:
    """Spine HTML files in reading order, titled from the first body heading."""
    if not os.path.isfile(filepath):
        raise FileNotFoundError(filepath)
    documents: list[dict[str, str]] = []
    with zipfile.ZipFile(filepath, "r") as zf:
        _title, spine = _opf_spine_hrefs(zf, _find_opf_path(zf))
        for hint, href in spine:
            try:
                raw = zf.read(href)
            except KeyError:
                continue
            html = raw.decode("utf-8", errors="replace")
            soup = BeautifulSoup(html, "html.parser")
            scope = soup.body if soup.body is not None else soup
            title = _section_heading_text(scope) or hint
            documents.append({"href": href, "title": title})
    return documents


_SVG_CAMEL = {
    "viewbox": "viewBox",
    "preserveaspectratio": "preserveAspectRatio",
    "gradientunits": "gradientUnits",
    "gradienttransform": "gradientTransform",
    "patternunits": "patternUnits",
    "patterntransform": "patternTransform",
    "stddeviation": "stdDeviation",
    "attributename": "attributeName",
    "repeatcount": "repeatCount",
}


def _restore_svg_attr_names(tag) -> None:
    for attr in list(tag.attrs):
        fixed = _SVG_CAMEL.get(str(attr).lower())
        if fixed and fixed not in tag.attrs:
            tag.attrs[fixed] = tag.attrs.pop(attr)


def render_epub_document(filepath: str, href: str, asset_prefix: str) -> str:
    """Return one spine document as HTML, with images pointed at asset_prefix."""
    if not os.path.isfile(filepath):
        raise FileNotFoundError(filepath)
    wanted = _zip_name(href)
    with zipfile.ZipFile(filepath, "r") as zf:
        _title, spine = _opf_spine_hrefs(zf, _find_opf_path(zf))
        allowed = {item_href for _hint, item_href in spine}
        if wanted not in allowed:
            raise ValueError("Not a spine document")
        try:
            raw = zf.read(wanted)
        except KeyError as exc:
            raise FileNotFoundError(wanted) from exc
    html = raw.decode("utf-8", errors="replace")
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup.find_all(_DROP_TAGS):
        tag.decompose()
    for tag in soup.find_all(True):
        for attr in list(tag.attrs):
            if attr.lower().startswith("on"):
                del tag.attrs[attr]
                continue
            value = tag.attrs.get(attr)
            if isinstance(value, str) and value.strip().lower().startswith("javascript:"):
                del tag.attrs[attr]
        if tag.name in ("img", "audio", "video", "source") and tag.get("src"):
            target = resolve_epub_ref(wanted, str(tag["src"]))
            if target:
                tag["src"] = asset_url(asset_prefix, target)
        if tag.name == "img" and tag.get("srcset"):
            tag["srcset"] = _rewrite_srcset(str(tag["srcset"]), wanted, asset_prefix)
        if tag.name == "link" and tag.get("href"):
            rel = " ".join(tag.get("rel") or []).lower()
            if "stylesheet" in rel or str(tag.get("type") or "").lower() == "text/css":
                target = resolve_epub_ref(wanted, str(tag["href"]))
                if target:
                    tag["href"] = asset_url(asset_prefix, target)
        if tag.name in ("image", "use"):
            for key in ("href", "xlink:href"):
                raw_ref = tag.get(key)
                if not raw_ref:
                    continue
                target = resolve_epub_ref(wanted, str(raw_ref))
                if target:
                    tag[key] = asset_url(asset_prefix, target)
        _restore_svg_attr_names(tag)
        if tag.name == "a" and tag.get("href"):
            href_value = str(tag["href"])
            if not href_value.startswith("#"):
                tag["data-epub-href"] = href_value
                tag["href"] = "#"
        style = tag.get("style")
        if isinstance(style, str) and "url(" in style.lower():
            tag["style"] = _rewrite_css(style, wanted, asset_prefix)
    for style_tag in soup.find_all("style"):
        if style_tag.string:
            style_tag.string.replace_with(_rewrite_css(style_tag.string, wanted, asset_prefix))
    return str(soup)


def read_epub_asset(filepath: str, zip_path: str, asset_prefix: str) -> tuple[bytes, str]:
    """Read an image, font, or stylesheet from the EPUB. HTML and scripts are refused."""
    if not os.path.isfile(filepath):
        raise FileNotFoundError(filepath)
    name = _zip_name(zip_path)
    ext = os.path.splitext(name)[1].lower()
    mime = _MIME.get(ext)
    if mime is None:
        raise ValueError("Unsupported EPUB asset")
    with zipfile.ZipFile(filepath, "r") as zf:
        try:
            info = zf.getinfo(name)
        except KeyError as exc:
            raise FileNotFoundError(name) from exc
        if info.file_size > _MAX_ASSET_BYTES:
            raise ValueError("EPUB asset too large")
        data = zf.read(name)
    if ext == ".css":
        text = data.decode("utf-8", errors="replace")
        data = _rewrite_css(text, name, asset_prefix).encode("utf-8")
    elif ext == ".svg":
        soup = BeautifulSoup(data, "html.parser")
        for tag in soup.find_all("script"):
            tag.decompose()
        data = str(soup).encode("utf-8")
    return data, mime


def epub_original_path(book_dir: str) -> str | None:
    path = os.path.join(book_dir, "original.epub")
    return path if os.path.isfile(path) else None


def pdf_original_path(book_dir: str) -> str | None:
    path = os.path.join(book_dir, "original.pdf")
    return path if os.path.isfile(path) else None


_PDF_PAGE_CACHE: dict[str, tuple[float, list[str]]] = {}
_PART_SUFFIX = re.compile(r"\s*\(\d+\)\s*$")


def _heading_key(value: str) -> str:
    return re.sub(r"\s+", " ", _PART_SUFFIX.sub("", value or "").strip()).casefold()


def page_for_heading(pages: list[str], title: str) -> int | None:
    """Return the page whose own heading is this chapter, skipping a contents list."""
    want = _heading_key(title)
    if not want:
        return None
    fallback = None
    for index, text in enumerate(pages):
        lines = [_heading_key(line) for line in (text or "").splitlines() if line.strip()]
        if want not in lines:
            continue
        if is_toc_text(text or ""):
            if fallback is None:
                fallback = index
            continue
        return index
    return fallback


def _compact(value: str) -> str:
    return re.sub(r"\s+", "", value or "").casefold()


def page_for_excerpt(pages: list[str], excerpt: str) -> int | None:
    """Find a page that contains this opening text, skipping a contents list."""
    needle = _compact(excerpt)[:20]
    if len(needle) < 12:
        return None
    fallback = None
    for index, text in enumerate(pages):
        if needle not in _compact(text):
            continue
        if is_toc_text(text or ""):
            if fallback is None:
                fallback = index
            continue
        return index
    return fallback


def page_for_chapter(pages: list[str], title: str, excerpt: str = "") -> int | None:
    """Heading line first. A long title, then the chunk opening, are the fallback."""
    found = page_for_heading(pages, title)
    if found is not None:
        return found
    if len(_heading_key(title)) > 24:
        found = page_for_excerpt(pages, title)
        if found is not None:
            return found
    return page_for_excerpt(pages, excerpt)


def locate_pdf_page(path: str, title: str, excerpt: str = "") -> int | None:
    mtime = os.path.getmtime(path)
    cached = _PDF_PAGE_CACHE.get(path)
    if cached and cached[0] == mtime:
        pages = cached[1]
    else:
        from pypdf import PdfReader

        reader = PdfReader(path)
        pages = [page.extract_text() or "" for page in reader.pages]
        _PDF_PAGE_CACHE[path] = (mtime, pages)
    return page_for_chapter(pages, title, excerpt)
