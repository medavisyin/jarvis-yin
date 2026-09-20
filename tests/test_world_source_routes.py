"""HTTP contract for world catalog Settings API and history world_news_items."""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime
from unittest.mock import patch

import pytest

_RAG = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "scripts", "rag"))
_SCRIPTS = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "scripts"))
_PIPELINE = os.path.join(_SCRIPTS, "pipeline")
for _p in (_SCRIPTS, _RAG, _PIPELINE):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from web_api import Flask  # noqa: E402

from routes.daily_fetch import daily_fetch_bp  # noqa: E402


class _FakeAgent:
    def __init__(self):
        self._GLOBAL_SETTINGS = {}
        self.saved = None

    def _save_settings(self, gs):
        self._GLOBAL_SETTINGS = dict(gs)
        self.saved = dict(gs)


@pytest.fixture()
def world_client():
    agent = _FakeAgent()
    app = Flask(__name__)
    app.register_blueprint(daily_fetch_bp)
    app.config["TESTING"] = True
    with (
        patch("routes.daily_fetch._resolve_agent", return_value=agent),
        patch("routes.daily_fetch._get_global_settings", return_value=agent._GLOBAL_SETTINGS),
    ):
        yield app.test_client(), agent


def test_world_sources_get_returns_catalog(world_client):
    client, _agent = world_client
    r = client.get("/api/toolbar/world-sources")
    assert r.status_code == 200
    data = r.get_json()
    ids = {s["id"] for s in data["sources"]}
    assert "bbc-news" in ids
    assert "xinhua" in ids
    assert "cls" not in ids
    assert any(c["id"] == "politics" for c in data["categories"])
    assert "bbc-news" in data["enabled"]


def test_world_sources_post_persists_enabled(world_client):
    client, agent = world_client
    r = client.post(
        "/api/toolbar/world-sources",
        json={"enabled": {"bbc-news": False, "xinhua": True}},
    )
    assert r.status_code == 200
    data = r.get_json()
    assert data["ok"] is True
    assert "bbc-news" not in data["enabled"]
    assert "xinhua" in data["enabled"]
    assert agent.saved["world_sources_enabled"]["bbc-news"] is False


def test_world_sources_post_rejects_non_object(world_client):
    client, _agent = world_client
    r = client.post("/api/toolbar/world-sources", json={"enabled": ["bbc-news"]})
    assert r.status_code == 400


def test_history_reports_world_news_items(tmp_path, world_client):
    client, _agent = world_client
    day = tmp_path / "2026-09-01"
    wn = day / "world-news"
    wn.mkdir(parents=True)
    (wn / "world-news-data.json").write_text(
        json.dumps({
            "translated": True,
            "total_items": 2,
            "categories": [{"items": [{"title": "a"}, {"title": "b"}]}],
        }),
        encoding="utf-8",
    )
    with patch("routes.daily_fetch.REPORTS_ROOT", str(tmp_path)):
        r = client.get("/api/toolbar/daily-fetch/history?date=2026-09-01")
    assert r.status_code == 200
    body = r.get_json()
    assert body["stats"]["world_news_items"] == 2


def test_history_today_without_world_json_lists_world_merge(tmp_path, world_client):
    client, _agent = world_client
    today = datetime.now().strftime("%Y-%m-%d")
    (tmp_path / today).mkdir()
    with patch("routes.daily_fetch.REPORTS_ROOT", str(tmp_path)):
        r = client.get(f"/api/toolbar/daily-fetch/history?date={today}")
    assert r.status_code == 200
    assert "world_news_merge" in (r.get_json().get("missing_steps") or [])


def test_history_old_date_without_world_dir_skips_world_merge(tmp_path, world_client):
    client, _agent = world_client
    old = "2026-08-01"
    (tmp_path / old).mkdir()
    with patch("routes.daily_fetch.REPORTS_ROOT", str(tmp_path)):
        r = client.get(f"/api/toolbar/daily-fetch/history?date={old}")
    assert r.status_code == 200
    assert "world_news_merge" not in (r.get_json().get("missing_steps") or [])
