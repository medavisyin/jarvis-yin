"""Settings routes store a MiMo key without echoing it."""
from __future__ import annotations

import os
import sys

_SCRIPTS = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "scripts"))
_RAG = os.path.join(_SCRIPTS, "rag")
_STOCK = os.path.join(_SCRIPTS, "stock")
if _STOCK in sys.path:
    sys.path.remove(_STOCK)
for _p in (_SCRIPTS, _RAG):
    if _p in sys.path:
        sys.path.remove(_p)
    sys.path.insert(0, _p)
sys.modules.pop("config", None)

import agent  # noqa: E402
import mimo_chat  # noqa: E402


def _restore(original):
    agent._GLOBAL_SETTINGS.clear()
    agent._GLOBAL_SETTINGS.update(original)


def test_settings_page_engine_labels_keep_stored_values():
    page = os.path.normpath(os.path.join(
        os.path.dirname(__file__), "..", "web", "src", "pages", "SettingsPage.tsx",
    ))
    text = open(page, encoding="utf-8").read()
    assert "MiMo-V2.5-TTS" in text
    assert 'edge: "Edge"' in text or '"Edge"' in text
    assert '"edge"' in text
    assert '"mimo"' in text


def test_settings_get_exposes_mimo_audio_fields(monkeypatch):
    original = dict(agent._GLOBAL_SETTINGS)
    monkeypatch.setattr(agent, "_save_settings", lambda _settings: None)
    try:
        agent._GLOBAL_SETTINGS["mimo_api_key"] = "sk-1234567890abcd"
        agent._GLOBAL_SETTINGS["audio_engine"] = "mimo"
        agent._GLOBAL_SETTINGS["audio_mimo_style"] = "磁性"
        body = agent._settings_safe()
    finally:
        _restore(original)
    assert body["audio_engine"] == "mimo"
    assert body["audio_mimo_style"] == "磁性"
    assert body["mimo_api_key_masked"] == "sk-1****abcd"
    assert "mimo_api_key" not in body


def test_settings_post_cannot_replace_the_raw_key(monkeypatch):
    original = dict(agent._GLOBAL_SETTINGS)
    monkeypatch.setattr(agent, "_save_settings", lambda _settings: None)
    try:
        agent._GLOBAL_SETTINGS["mimo_api_key"] = "keep-me-12345678"
        client = agent.app.test_client()
        response = client.post(
            "/api/settings",
            json={"chat_agent": "mimo", "mimo_api_key": "stolen-key-123456"},
        )
        body = response.get_json()
        assert response.status_code == 200
        assert body["settings"]["chat_agent"] == "mimo"
        assert "mimo_api_key" not in body["settings"]
        assert agent._GLOBAL_SETTINGS["mimo_api_key"] == "keep-me-12345678"
    finally:
        _restore(original)


def test_mimo_key_route_returns_a_mask(monkeypatch):
    original = dict(agent._GLOBAL_SETTINGS)
    monkeypatch.setattr(agent, "_save_settings", lambda _settings: None)
    try:
        client = agent.app.test_client()
        response = client.post("/api/settings/mimo-key", json={"api_key": "sk-1234567890abcd"})
        assert response.status_code == 200
        assert response.get_json()["masked"] == "sk-1****abcd"
    finally:
        _restore(original)


def test_mimo_probe_requires_a_key(monkeypatch):
    original = dict(agent._GLOBAL_SETTINGS)
    monkeypatch.setattr(agent, "_save_settings", lambda _settings: None)
    try:
        agent._GLOBAL_SETTINGS["mimo_api_key"] = ""
        client = agent.app.test_client()
        response = client.post("/api/mimo/test", json={})
        assert response.status_code == 400
        assert "No MiMo API key configured" in response.get_json()["error"]
    finally:
        _restore(original)


def test_mimo_probe_uses_the_adapter(monkeypatch):
    original = dict(agent._GLOBAL_SETTINGS)
    monkeypatch.setattr(agent, "_save_settings", lambda _settings: None)
    monkeypatch.setattr(mimo_chat, "make_client", lambda _key: object())
    monkeypatch.setattr(mimo_chat, "probe", lambda _client: "hi")
    try:
        client = agent.app.test_client()
        response = client.post("/api/mimo/test", json={"api_key": "sk-1234567890abcd"})
        body = response.get_json()
        assert response.status_code == 200
        assert body["ok"] is True
        assert body["model"] == "mimo-v2.6-flash"
        assert body["reply"] == "hi"
    finally:
        _restore(original)
