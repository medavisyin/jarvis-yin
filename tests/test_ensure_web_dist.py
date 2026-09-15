"""Rebuild web/dist only when frontend sources are newer than the last build."""
from __future__ import annotations

import os
import sys

_RAG = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "scripts", "rag"))
if _RAG not in sys.path:
    sys.path.insert(0, _RAG)


def test_needs_rebuild_when_dist_missing(tmp_path):
    from ensure_web_dist import needs_web_rebuild

    web = tmp_path / "web"
    web.mkdir()
    (web / "src").mkdir()
    (web / "src" / "App.tsx").write_text("export default function App() { return null }", encoding="utf-8")
    assert needs_web_rebuild(str(web)) is True


def test_needs_rebuild_when_src_newer(tmp_path):
    from ensure_web_dist import needs_web_rebuild

    web = tmp_path / "web"
    src = web / "src"
    dist = web / "dist"
    src.mkdir(parents=True)
    dist.mkdir()
    app = src / "App.tsx"
    app.write_text("v1", encoding="utf-8")
    index = dist / "index.html"
    index.write_text("<html></html>", encoding="utf-8")
    older = index.stat().st_mtime - 120
    os.utime(index, (older, older))
    os.utime(app, None)
    assert needs_web_rebuild(str(web)) is True


def test_skips_rebuild_when_dist_is_newer(tmp_path):
    from ensure_web_dist import needs_web_rebuild

    web = tmp_path / "web"
    src = web / "src"
    dist = web / "dist"
    src.mkdir(parents=True)
    dist.mkdir()
    app = src / "App.tsx"
    app.write_text("v1", encoding="utf-8")
    older = app.stat().st_mtime - 120
    os.utime(app, (older, older))
    (dist / "index.html").write_text("<html></html>", encoding="utf-8")
    assert needs_web_rebuild(str(web)) is False


def test_ignores_node_modules_mtime(tmp_path):
    from ensure_web_dist import needs_web_rebuild

    web = tmp_path / "web"
    src = web / "src"
    dist = web / "dist"
    nm = web / "node_modules" / "foo"
    src.mkdir(parents=True)
    dist.mkdir()
    nm.mkdir(parents=True)
    app = src / "App.tsx"
    app.write_text("v1", encoding="utf-8")
    older = app.stat().st_mtime - 120
    os.utime(app, (older, older))
    (dist / "index.html").write_text("<html></html>", encoding="utf-8")
    junk = nm / "pkg.js"
    junk.write_text("x", encoding="utf-8")
    os.utime(junk, None)
    assert needs_web_rebuild(str(web)) is False
