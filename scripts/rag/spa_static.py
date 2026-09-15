"""Serve a Vite `dist/` folder from the FastAPI Flask-compat app."""
from __future__ import annotations

import os
from typing import Any

from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from web_api import jsonify


def resolve_index_html(dist_dir: str) -> str | None:
    path = os.path.join(dist_dir, "index.html")
    return path if os.path.isfile(path) else None


def _is_api_path(full_path: str) -> bool:
    return full_path == "api" or full_path.startswith("api/")


def _is_docs_path(full_path: str) -> bool:
    return (
        full_path in {"docs", "redoc", "openapi.json"}
        or full_path.startswith("docs/")
        or full_path.startswith("redoc/")
    )


def mount_spa(app: Any, dist_dir: str) -> None:
    """Register `/` and SPA fallback when `dist/index.html` exists. No-op otherwise.

    Call after API routes so `/api/*` stays on those handlers.
    `index.html` is resolved per request so a rebuild is picked up after refresh
    without reimporting Python (assets mount still needs a restart if the
    assets directory appears for the first time).
    """
    if not resolve_index_html(dist_dir):
        return

    assets = os.path.join(dist_dir, "assets")
    if os.path.isdir(assets):
        app.mount("/assets", StaticFiles(directory=assets), name="spa-assets")

    @app.route("/")
    def spa_root():
        index = resolve_index_html(dist_dir)
        if not index:
            return jsonify({"error": "SPA not built"}), 404
        return FileResponse(index, media_type="text/html")

    @app.route("/<path:full_path>")
    def spa_fallback(full_path: str):
        if _is_api_path(full_path) or _is_docs_path(full_path):
            return jsonify({"error": "Not found"}), 404
        direct = os.path.normpath(os.path.join(dist_dir, full_path))
        dist_abs = os.path.abspath(dist_dir)
        if not os.path.abspath(direct).startswith(dist_abs + os.sep) and os.path.abspath(direct) != dist_abs:
            return jsonify({"error": "Not found"}), 404
        if os.path.isfile(direct):
            return FileResponse(direct)
        index = resolve_index_html(dist_dir)
        if not index:
            return jsonify({"error": "SPA not built"}), 404
        return FileResponse(index, media_type="text/html")
