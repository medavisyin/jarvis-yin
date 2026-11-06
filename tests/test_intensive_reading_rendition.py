"""Original PDF/EPUB files can be shown without dropping scripts into the page."""

from __future__ import annotations

import os
import sys
import zipfile
from pathlib import Path
from unittest.mock import patch

import pytest

_RAG = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "scripts", "rag"))
_SCRIPTS = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "scripts"))
for _p in (_SCRIPTS, _RAG):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from intensive_reading.rendition import (  # noqa: E402
    page_for_heading,
    read_epub_asset,
    render_epub_document,
    spine_documents,
)
from web_api import Flask  # noqa: E402

from routes.intensive_reading import intensive_reading_bp  # noqa: E402


def _epub(path: Path) -> None:
    container = (
        '<?xml version="1.0"?>'
        '<container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">'
        '<rootfiles><rootfile full-path="OEBPS/content.opf" '
        'media-type="application/oebps-package+xml"/></rootfiles></container>'
    )
    opf = (
        '<?xml version="1.0"?>'
        '<package xmlns="http://www.idpf.org/2007/opf" version="2.0">'
        "<metadata xmlns:dc=\"http://purl.org/dc/elements/1.1/\">"
        "<dc:title>Picture Book</dc:title></metadata>"
        "<manifest>"
        '<item id="c1" href="chap1.xhtml" media-type="application/xhtml+xml"/>'
        '<item id="css" href="styles/book.css" media-type="text/css"/>'
        '<item id="pic" href="images/pic.png" media-type="image/png"/>'
        "</manifest>"
        '<spine><itemref idref="c1"/></spine></package>'
    )
    chapter = (
        '<?xml version="1.0" encoding="utf-8"?>'
        '<html xmlns="http://www.w3.org/1999/xhtml"><head>'
        '<link rel="stylesheet" href="styles/book.css"/>'
        "</head><body>"
        "<h1>Chapter One</h1>"
        '<img src="images/pic.png" alt="harbour"/>'
        '<p onclick="alert(1)">The ship sailed.</p>'
        "<script>alert(1)</script>"
        "</body></html>"
    )
    css = "body{background:url(../images/pic.png)}"
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr("mimetype", "application/epub+zip", compress_type=zipfile.ZIP_STORED)
        zf.writestr("META-INF/container.xml", container)
        zf.writestr("OEBPS/content.opf", opf)
        zf.writestr("OEBPS/chap1.xhtml", chapter)
        zf.writestr("OEBPS/styles/book.css", css)
        zf.writestr("OEBPS/images/pic.png", b"\x89PNG\r\n\x1a\n")


def test_spine_lists_chapter_and_document_keeps_image(tmp_path: Path):
    epub = tmp_path / "book.epub"
    _epub(epub)
    spine = spine_documents(str(epub))
    assert spine == [{"href": "OEBPS/chap1.xhtml", "title": "Chapter One"}]
    html = render_epub_document(str(epub), "OEBPS/chap1.xhtml", "/books/demo/asset")
    assert "<script" not in html.lower()
    assert "onclick" not in html.lower()
    assert 'src="/books/demo/asset?path=OEBPS/images/pic.png"' in html
    assert "The ship sailed." in html
    assert 'href="/books/demo/asset?path=OEBPS/styles/book.css"' in html


def test_svg_cover_keeps_viewbox_and_rewrites_image(tmp_path: Path):
    epub = tmp_path / "cover.epub"
    container = (
        '<?xml version="1.0"?>'
        '<container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">'
        '<rootfiles><rootfile full-path="content.opf" '
        'media-type="application/oebps-package+xml"/></rootfiles></container>'
    )
    opf = (
        '<?xml version="1.0"?>'
        '<package xmlns="http://www.idpf.org/2007/opf" version="2.0">'
        "<metadata><dc:title xmlns:dc=\"http://purl.org/dc/elements/1.1/\">Cover</dc:title></metadata>"
        '<manifest><item id="c" href="titlepage.xhtml" media-type="application/xhtml+xml"/>'
        '<item id="pic" href="cover.jpeg" media-type="image/jpeg"/></manifest>'
        '<spine><itemref idref="c"/></spine></package>'
    )
    page = (
        '<html xmlns="http://www.w3.org/1999/xhtml"><body>'
        '<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink" '
        'viewBox="0 0 406 616" preserveAspectRatio="none" width="100%" height="100%">'
        '<image width="406" height="616" xlink:href="cover.jpeg"/>'
        "</svg></body></html>"
    )
    with zipfile.ZipFile(epub, "w") as zf:
        zf.writestr("mimetype", "application/epub+zip")
        zf.writestr("META-INF/container.xml", container)
        zf.writestr("content.opf", opf)
        zf.writestr("titlepage.xhtml", page)
        zf.writestr("cover.jpeg", b"\xff\xd8\xff")
    html = render_epub_document(str(epub), "titlepage.xhtml", "/books/demo/asset")
    assert "viewBox=" in html
    assert "preserveAspectRatio=" in html
    assert "/books/demo/asset?path=cover.jpeg" in html


def test_css_asset_rewrites_image_and_rejects_escape(tmp_path: Path):
    epub = tmp_path / "book.epub"
    _epub(epub)
    body, mime = read_epub_asset(str(epub), "OEBPS/styles/book.css", "/books/demo/asset")
    assert mime == "text/css"
    assert b"url(/books/demo/asset?path=OEBPS/images/pic.png)" in body
    png, png_mime = read_epub_asset(str(epub), "OEBPS/images/pic.png", "/books/demo/asset")
    assert png.startswith(b"\x89PNG")
    assert png_mime == "image/png"
    with pytest.raises(ValueError):
        read_epub_asset(str(epub), "../secret", "/books/demo/asset")
    with pytest.raises(ValueError):
        render_epub_document(str(epub), "OEBPS/styles/book.css", "/books/demo/asset")


@pytest.fixture()
def client(tmp_path):
    books = tmp_path / "books"
    books.mkdir()
    app = Flask(__name__)
    app.register_blueprint(intensive_reading_bp)
    app.config["TESTING"] = True
    with patch("routes.intensive_reading._books_dir", return_value=str(books)):
        yield app.test_client(), str(books)


def test_original_pdf_and_epub_rendition_routes(client, tmp_path):
    http, books = client
    book = os.path.join(books, "picture-book-abcd1234")
    os.makedirs(book)
    (Path(book) / "original.pdf").write_bytes(b"%PDF-1.4 demo")
    epub = tmp_path / "picture.epub"
    _epub(epub)
    (Path(book) / "original.epub").write_bytes(epub.read_bytes())

    pdf = http.get("/api/intensive-reading/books/picture-book-abcd1234/original")
    assert pdf.status_code == 200
    assert pdf.data.startswith(b"%PDF")
    assert "pdf" in pdf.headers.get("content-type", "")

    missing = http.get("/api/intensive-reading/books/missing-book-abcd1234/original")
    assert missing.status_code == 404

    bad = http.get("/api/intensive-reading/books/..%2Fsecret/original")
    assert bad.status_code in (400, 404)

    spine = http.get("/api/intensive-reading/books/picture-book-abcd1234/rendition")
    assert spine.status_code == 200
    body = spine.get_json()
    assert body["format"] == "epub"
    assert body["spine"][0]["href"] == "OEBPS/chap1.xhtml"

    doc = http.get(
        "/api/intensive-reading/books/picture-book-abcd1234/rendition/document",
        query_string={"href": "OEBPS/chap1.xhtml"},
    )
    assert doc.status_code == 200
    assert "<script" not in doc.get_json()["html"].lower()

    asset = http.get(
        "/api/intensive-reading/books/picture-book-abcd1234/rendition/asset",
        query_string={"path": "OEBPS/images/pic.png"},
    )
    assert asset.status_code == 200
    assert asset.data.startswith(b"\x89PNG")

    escaped = http.get(
        "/api/intensive-reading/books/picture-book-abcd1234/rendition/asset",
        query_string={"path": "../original.pdf"},
    )
    assert escaped.status_code == 400


def test_heading_page_skips_the_contents_list():
    pages = [
        "Contents\nChapter 1    12\nChapter 2    30",
        "CHAPTER 1\n\nIt was very dark.",
        "The trail went on.\nChapter 1 was behind them.",
    ]
    assert page_for_heading(pages, "CHAPTER 1") == 1
    assert page_for_heading(pages, "Chapter 1 (2)") == 1
    assert page_for_heading(pages, "Missing") is None


def test_long_title_and_excerpt_find_the_opening_page():
    from intensive_reading.rendition import page_for_chapter

    pages = [
        "项塔兰\n前言\n第一章\n第二章",
        "第一章\n我花了很长的岁月，走过大半个世界，才真正学到什么是爱与命运",
        "You Don’t Know What’s in My Heart\nWE WERE FRACTIOUS AND overpaid.",
    ]
    long_title = "第一章 我花了很长的岁月，走过大半个世界，才真正学到什么是爱与命运，以及我们所做的抉择"
    assert page_for_chapter(pages, long_title) == 1
    assert page_for_chapter(pages, "Chapter 1 (1)", "WE WERE FRACTIOUS AND overpaid.") == 2
    assert page_for_chapter(pages, "Chapter 1") is None
