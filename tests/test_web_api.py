"""FastAPI Flask-compat layer for the Jarvis agent HTTP app."""
from __future__ import annotations

import os
import sys

import pytest

_RAG = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "scripts", "rag"))
if _RAG not in sys.path:
    sys.path.insert(0, _RAG)


def test_web_api_importable():
    import web_api  # noqa: F401


@pytest.fixture
def client():
    from fastapi.testclient import TestClient
    from web_api import Flask, Response, jsonify, request

    app = Flask("test")

    @app.route("/api/health")
    def health():
        return jsonify({"status": "ok"})

    @app.route("/api/echo", methods=["POST"])
    def echo():
        data = request.get_json(silent=True) or {}
        if not data.get("q"):
            return jsonify({"error": "empty"}), 400
        return jsonify({"q": data["q"]})

    @app.route("/api/items/<item_id>", methods=["GET"])
    def item(item_id):
        name = request.args.get("name", "")
        return jsonify({"id": item_id, "name": name})

    @app.route("/api/n/<int:n>", methods=["GET"])
    def num(n):
        return jsonify({"n": n})

    @app.route("/api/stream", methods=["POST"])
    def stream():
        def gen():
            yield "data: hi\n\n"
            yield "data: [DONE]\n\n"

        return Response(
            gen(),
            mimetype="text/event-stream",
            headers={"Cache-Control": "no-cache"},
        )

    return TestClient(app)


def test_health_json(client):
    r = client.get("/api/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


def test_json_post_and_error_tuple(client):
    bad = client.post("/api/echo", json={})
    assert bad.status_code == 400
    assert bad.json()["error"] == "empty"
    ok = client.post("/api/echo", json={"q": "hi"})
    assert ok.status_code == 200
    assert ok.json() == {"q": "hi"}


def test_flask_path_param_and_query(client):
    r = client.get("/api/items/abc", params={"name": "x"})
    assert r.status_code == 200
    assert r.json() == {"id": "abc", "name": "x"}


def test_flask_int_converter(client):
    r = client.get("/api/n/7")
    assert r.status_code == 200
    assert r.json() == {"n": 7}


def test_sse_content_type(client):
    r = client.post("/api/stream")
    assert r.status_code == 200
    assert "text/event-stream" in r.headers["content-type"]
    assert "data: hi" in r.text
    assert "[DONE]" in r.text


@pytest.fixture
def agent_like_client(tmp_path):
    from fastapi.testclient import TestClient
    from web_api import Blueprint, Flask, jsonify, make_response, request, send_file

    app = Flask("test")
    app.config["MAX_CONTENT_LENGTH"] = 1024

    bp = Blueprint("toolbar", __name__)

    @bp.route("/api/toolbar/reindex/<job_id>", methods=["GET"])
    @bp.route("/api/toolbar/wiki-fetch/<job_id>", methods=["GET"])
    def job_status(job_id):
        return jsonify({"job_id": job_id})

    @bp.route("/api/upload", methods=["POST"])
    def upload():
        if "file" not in request.files:
            return jsonify({"error": "Missing file"}), 400
        f = request.files["file"]
        dest = str(tmp_path / "saved.bin")
        f.save(dest)
        kind = request.form.get("book_type") or ""
        return jsonify({"filename": f.filename, "kind": kind})

    pdf = tmp_path / "note.pdf"
    pdf.write_bytes(b"%PDF-1.4 test")

    @bp.route("/api/pdf/<filename>", methods=["GET"])
    def pdf_file(filename):
        return send_file(str(pdf), mimetype="application/pdf", download_name=filename)

    app.register_blueprint(bp)

    @app.route("/")
    def index():
        resp = make_response("<html>ok</html>")
        resp.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
        return resp

    return TestClient(app)


def test_blueprint_stacked_flask_paths(agent_like_client):
    r1 = agent_like_client.get("/api/toolbar/reindex/abc")
    r2 = agent_like_client.get("/api/toolbar/wiki-fetch/abc")
    assert r1.status_code == 200
    assert r1.json() == {"job_id": "abc"}
    assert r2.status_code == 200
    assert r2.json() == {"job_id": "abc"}


def test_html_cache_headers(agent_like_client):
    r = agent_like_client.get("/")
    assert r.status_code == 200
    assert "text/html" in r.headers["content-type"]
    assert "no-store" in r.headers["cache-control"]
    assert r.text == "<html>ok</html>"


def test_multipart_upload_and_form(agent_like_client):
    r = agent_like_client.post(
        "/api/upload",
        files={"file": ("book.pdf", b"%PDF-1.4", "application/pdf")},
        data={"book_type": "novel"},
    )
    assert r.status_code == 200
    assert r.json() == {"filename": "book.pdf", "kind": "novel"}


def test_max_content_length_413(agent_like_client):
    r = agent_like_client.post(
        "/api/upload",
        files={"file": ("big.pdf", b"x" * 2000, "application/pdf")},
    )
    assert r.status_code == 413


def test_send_file_pdf(agent_like_client):
    r = agent_like_client.get("/api/pdf/report.pdf")
    assert r.status_code == 200
    assert "application/pdf" in r.headers["content-type"]
    assert r.content.startswith(b"%PDF")


def test_flask_test_client_get_json_and_data():
    from web_api import Flask, jsonify

    app = Flask("test")

    @app.route("/api/health")
    def health():
        return jsonify({"status": "ok"})

    c = app.test_client()
    r = c.get("/api/health")
    assert r.status_code == 200
    assert r.get_json() == {"status": "ok"}
    assert b"ok" in r.data


def test_swagger_docs_are_enabled():
    from fastapi.testclient import TestClient
    from web_api import Flask, jsonify

    app = Flask("test")

    @app.route("/api/health")
    def health():
        return jsonify({"status": "ok"})

    client = TestClient(app)
    docs = client.get("/docs")
    assert docs.status_code == 200
    assert "swagger" in docs.text.lower()
    spec = client.get("/openapi.json")
    assert spec.status_code == 200
    assert "openapi" in spec.json()
    assert "/api/health" in spec.json()["paths"]
    assert client.get("/redoc").status_code == 404


def test_non_file_form_field_is_not_in_files(agent_like_client):
    r = agent_like_client.post(
        "/api/upload",
        data={"file": "not-a-file", "book_type": "novel"},
    )
    assert r.status_code == 400
    assert r.json()["error"] == "Missing file"


def test_multipart_too_large_without_content_length(monkeypatch):
    from fastapi.testclient import TestClient
    from web_api import Blueprint, Flask, jsonify, request

    monkeypatch.setattr("web_api._content_length", lambda headers: None)
    app = Flask("test")
    app.config["MAX_CONTENT_LENGTH"] = 1024
    bp = Blueprint("up", __name__)

    @bp.route("/api/upload", methods=["POST"])
    def upload():
        if "file" not in request.files:
            return jsonify({"error": "Missing file"}), 400
        return jsonify({"ok": True})

    app.register_blueprint(bp)
    r = TestClient(app).post(
        "/api/upload",
        files={"file": ("big.pdf", b"x" * 2000, "application/pdf")},
    )
    assert r.status_code == 413


def test_static_sibling_wins_over_path_param():
    """Flask matches /history even if /<job_id> was registered first."""
    from fastapi.testclient import TestClient
    from web_api import Flask, jsonify

    app = Flask("test")

    @app.route("/api/jobs/<job_id>")
    def job(job_id):
        return jsonify({"job": job_id})

    @app.route("/api/jobs/history")
    def history():
        return jsonify({"history": True})

    c = TestClient(app)
    r = c.get("/api/jobs/history")
    assert r.status_code == 200
    assert r.json() == {"history": True}
    assert c.get("/api/jobs/abc").json() == {"job": "abc"}


def test_blueprint_static_sibling_wins_over_path_param():
    from fastapi.testclient import TestClient
    from web_api import Blueprint, Flask, jsonify

    app = Flask("test")
    bp = Blueprint("jobs", __name__)

    @bp.route("/api/jobs/<job_id>")
    def job(job_id):
        return jsonify({"job": job_id})

    @bp.route("/api/jobs/history")
    def history():
        return jsonify({"history": True})

    app.register_blueprint(bp)
    c = TestClient(app)
    r = c.get("/api/jobs/history")
    assert r.status_code == 200
    assert r.json() == {"history": True}
