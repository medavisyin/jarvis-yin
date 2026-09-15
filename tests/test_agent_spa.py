"""FastAPI serves Vite build at / without stealing /api."""
from __future__ import annotations

import os
import sys

import pytest

_RAG = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "scripts", "rag"))
if _RAG not in sys.path:
    sys.path.insert(0, _RAG)


def test_spa_helper_importable():
    import spa_static  # noqa: F401


@pytest.fixture
def dist_dir(tmp_path):
    dist = tmp_path / "dist"
    assets = dist / "assets"
    assets.mkdir(parents=True)
    (dist / "index.html").write_text(
        "<!doctype html><html><body>SPA</body></html>", encoding="utf-8"
    )
    (assets / "app.js").write_text("console.log(1)", encoding="utf-8")
    return dist


def test_root_serves_dist_index(dist_dir):
    from fastapi.testclient import TestClient
    from spa_static import mount_spa
    from web_api import Flask, jsonify

    app = Flask("test")

    @app.route("/api/health")
    def health():
        return jsonify({"status": "ok"})

    mount_spa(app, str(dist_dir))
    c = TestClient(app)
    r = c.get("/")
    assert r.status_code == 200
    assert "SPA" in r.text
    assert "text/html" in r.headers["content-type"]
    api = c.get("/api/health")
    assert api.status_code == 200
    assert api.json() == {"status": "ok"}


def test_client_route_falls_back_to_index(dist_dir):
    from fastapi.testclient import TestClient
    from spa_static import mount_spa
    from web_api import Flask

    app = Flask("test")
    mount_spa(app, str(dist_dir))
    r = TestClient(app).get("/stock")
    assert r.status_code == 200
    assert "SPA" in r.text


def test_spa_does_not_steal_docs_or_openapi(dist_dir):
    from fastapi.testclient import TestClient
    from spa_static import mount_spa
    from web_api import Flask, jsonify

    app = Flask("test")

    @app.route("/api/health")
    def health():
        return jsonify({"status": "ok"})

    mount_spa(app, str(dist_dir))
    c = TestClient(app)
    docs = c.get("/docs")
    assert docs.status_code == 200
    assert "swagger" in docs.text.lower()
    assert "SPA" not in docs.text
    spec = c.get("/openapi.json")
    assert spec.status_code == 200
    assert "openapi" in spec.json()
    missing = c.get("/docs/no-such-page")
    assert missing.status_code == 404
    assert missing.json()["error"] == "Not found"
    redoc = c.get("/redoc")
    assert redoc.status_code == 404
    assert redoc.json()["error"] == "Not found"
    assert "SPA" not in redoc.text


def test_missing_dist_returns_none_index_path(tmp_path):
    from spa_static import resolve_index_html

    assert resolve_index_html(str(tmp_path / "nope")) is None


def test_fallback_when_no_dist(tmp_path):
    from fastapi.testclient import TestClient
    from spa_static import mount_spa
    from web_api import Flask, make_response

    app = Flask("test")

    @app.route("/")
    def old():
        return make_response("<html>legacy</html>")

    mount_spa(app, str(tmp_path / "missing"))
    r = TestClient(app).get("/")
    assert r.status_code == 200
    assert "legacy" in r.text
