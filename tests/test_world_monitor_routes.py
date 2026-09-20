"""HTTP contract for Jarvis world-monitor dashboard."""

from __future__ import annotations

import json
import os
import sys
from unittest.mock import patch

import pytest

_RAG = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "scripts", "rag"))
_SCRIPTS = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "scripts"))
_PIPELINE = os.path.join(_SCRIPTS, "pipeline")
for _p in (_SCRIPTS, _RAG, _PIPELINE):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from web_api import Flask  # noqa: E402

from routes.world_monitor import world_monitor_bp  # noqa: E402


@pytest.fixture(autouse=True)
def _no_radar_network():
    """Dashboard GET may fetch Yahoo/alternative.me; keep route tests offline."""
    empty = {
        "fear_greed": {"value": None, "label": "", "source": ""},
        "vix": {"value": None, "change_pct": None, "source": ""},
        "quotes": [],
        "mood": {"risk_level": "", "signals": [], "recommendation": ""},
        "fetched_at": "",
    }
    with patch("world_monitor.load_radar_signals", return_value=empty):
        yield


@pytest.fixture()
def client(tmp_path):
    app = Flask(__name__)
    app.register_blueprint(world_monitor_bp)
    app.config["TESTING"] = True
    day = tmp_path / "2026-09-20" / "world-news"
    day.mkdir(parents=True)
    (day / "world-news-data.json").write_text(
        json.dumps({
            "categories": [{
                "category": "politics",
                "items": [{"title": "Missile strike near Kyiv", "source": "BBC"}],
            }],
        }),
        encoding="utf-8",
    )
    with patch("routes.world_monitor.REPORTS_ROOT", str(tmp_path)):
        yield app.test_client()


def test_world_monitor_get_payload(client):
    r = client.get("/api/toolbar/world-monitor?date=2026-09-20&variant=world")
    assert r.status_code == 200
    body = r.get_json()
    assert body["variant"] == "world"
    assert body["engine"]["globe"] == "globe.gl"
    assert body["stats"]["world_items"] == 1
    assert "cii" not in body
    assert all(p.get("id") != "cii" for p in body["panels"])
    assert any(p["layer"] == "military" for p in body["points"])
    assert body.get("lookback") == 1


def test_world_monitor_lookback_query(tmp_path):
    app = Flask(__name__)
    app.register_blueprint(world_monitor_bp)
    for day, title in (("2026-09-20", "Missile strike near Kyiv"), ("2026-09-19", "Talks in London")):
        wn = tmp_path / day / "world-news"
        wn.mkdir(parents=True)
        (wn / "world-news-data.json").write_text(
            json.dumps({
                "categories": [{"category": "politics", "items": [{"title": title, "source": "BBC"}]}],
            }),
            encoding="utf-8",
        )
    with patch("routes.world_monitor.REPORTS_ROOT", str(tmp_path)):
        client = app.test_client()
        r = client.get("/api/toolbar/world-monitor?date=2026-09-20&variant=world&lookback=2")
    assert r.status_code == 200
    assert r.get_json()["stats"]["world_items"] == 2
    assert r.get_json()["lookback"] == 2


def test_world_monitor_insight_post(client):
    with patch("routes.world_monitor.ollama_hub_insight", return_value="基辅遇袭") as mocked:
        r = client.post(
            "/api/toolbar/world-monitor/insight",
            json={"date": "2026-09-20", "variant": "world", "lookback": 1, "hub_id": "kyiv"},
        )
    assert r.status_code == 200
    body = r.get_json()
    assert body["insight"] == "基辅遇袭"
    assert mocked.call_count == 1
    assert mocked.call_args.kwargs.get("hub_id") == "kyiv" or mocked.call_args[0][1] == "kyiv"


def test_world_monitor_finance_radar_signals(tmp_path):
    app = Flask(__name__)
    app.register_blueprint(world_monitor_bp)
    day = tmp_path / "2026-09-20"
    (day / "world-news").mkdir(parents=True)
    (day / "finance-news").mkdir()
    (day / "world-news" / "world-news-data.json").write_text(
        json.dumps({"categories": []}),
        encoding="utf-8",
    )
    (day / "finance-news" / "finance-news-data.json").write_text(
        json.dumps({"categories": [{"category": "markets", "items": [{"title": "Dow"}]}]}),
        encoding="utf-8",
    )
    signals = {
        "fear_greed": {"value": 41, "label": "Fear", "source": "alternative.me"},
        "vix": {"value": 18.2, "change_pct": -0.3, "source": "Yahoo Finance"},
        "quotes": [{"id": "gold", "symbol": "GC=F", "label": "Gold", "value": 2650.1, "change_pct": 0.4}],
        "mood": {"risk_level": "fear", "signals": [], "recommendation": ""},
        "fetched_at": "2026-09-20T10:00:00",
    }
    with patch("routes.world_monitor.REPORTS_ROOT", str(tmp_path)), patch(
        "world_monitor.load_radar_signals", return_value=signals,
    ):
        client = app.test_client()
        r = client.get("/api/toolbar/world-monitor?date=2026-09-20&variant=finance")
    assert r.status_code == 200
    body = r.get_json()
    assert body["finance_radar"]["signals"]["fear_greed"]["value"] == 41
    assert body["finance_radar"]["signals"]["quotes"][0]["id"] == "gold"
