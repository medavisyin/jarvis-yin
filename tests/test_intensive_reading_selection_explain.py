"""TDD: Intensive Reading selection explain (prompts + API)."""

from __future__ import annotations

import json
import os
import sys
from unittest.mock import patch

import pytest

_RAG = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "scripts", "rag"))
_SCRIPTS = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "scripts"))
for _p in (_SCRIPTS, _RAG):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from web_api import Flask  # noqa: E402

from intensive_reading.prompts import (  # noqa: E402
    selection_explain_system_prompt,
    selection_explain_user_message,
)
from routes.intensive_reading import intensive_reading_bp  # noqa: E402


def test_selection_explain_system_prompt_chinese_body_and_scope():
    prompt = selection_explain_system_prompt()
    lower = prompt.lower()
    assert "### 1. 本句意思" in prompt
    assert "### 2. 语境中的其他意思" in prompt
    assert "Output these section headings (exactly)" not in prompt
    assert "only if" in lower or "only when" in lower
    assert "省略" in prompt or "omit" in lower
    assert "selected" in lower
    assert "gloss" in lower or "translate" in lower or "word-for-word" in lower
    assert "### 1. 含义与语境" not in prompt
    assert "simplified chinese" in lower
    assert "respond entirely in english" not in lower
    assert "do not use chinese" not in lower
    assert "grammar or usage" not in lower
    assert "how the surrounding context shapes" not in lower


def test_selection_explain_system_prompt_analysis_chinese_body():
    prompt = selection_explain_system_prompt("analysis")
    assert "### 1. 含义与语境" in prompt
    assert "### 1. 本句意思" not in prompt
    assert "### 2. 语境中的其他意思" not in prompt
    lower = prompt.lower()
    assert "simplified chinese" in lower
    assert "respond entirely in english" not in lower
    assert "do not use chinese" not in lower
    assert "grammar or usage" not in lower


def test_selection_explain_user_message_analysis_asks_chinese_body():
    msg = selection_explain_user_message(
        selected_text="a bitter pill",
        context="He found the news a bitter pill to swallow.",
        source="analysis",
    )
    lower = msg.lower()
    assert "simplified chinese" in lower
    assert "### 1. 含义与语境" in msg
    assert "### 1. 本句意思" not in msg
    assert "### 2. 语境中的其他意思" not in msg


def test_selection_explain_user_message_passage_asks_chinese_body():
    msg = selection_explain_user_message(
        selected_text="a bitter pill",
        context="He found the news a bitter pill to swallow.",
        source="passage",
    )
    lower = msg.lower()
    assert "simplified chinese" in lower
    assert "### 1. 本句意思" in msg
    assert "### 2. 语境中的其他意思" in msg
    assert "### 1. 含义与语境" not in msg
    msg = selection_explain_user_message(
        selected_text="a bitter pill",
        context=(
            "Earlier setup.\n\n"
            "He found the news a bitter pill to swallow after the vote.\n\n"
            "Later fallout."
        ),
        title="Test Novel",
    )
    assert "a bitter pill" in msg
    assert "Earlier setup" in msg
    assert "Later fallout" in msg
    assert "Test Novel" in msg
    assert "Selected" in msg or "selection" in msg.lower()
    lower = msg.lower()
    assert "meaning" in lower or "sense" in lower
    assert "grammar" not in lower
    assert "usage" not in lower


def test_selection_explain_user_message_rejects_blank_selection():
    with pytest.raises(ValueError):
        selection_explain_user_message(selected_text="  ", context="Some context.")


@pytest.fixture()
def client():
    app = Flask(__name__)
    app.register_blueprint(intensive_reading_bp)
    app.config["TESTING"] = True
    yield app.test_client()


def test_explain_selection_rejects_empty_selected(client):
    r = client.post(
        "/api/intensive-reading/explain-selection",
        json={"selected_text": "  ", "context": "Around here."},
    )
    assert r.status_code == 400
    assert "selected" in (r.get_json().get("error") or "").lower()


def test_explain_selection_streams_with_mocked_ollama(client):
    class _FakeResp:
        status_code = 200

        def iter_lines(self):
            yield json.dumps({"message": {"content": "Means a hard truth."}}).encode()
            yield json.dumps(
                {"message": {"content": ""}, "done": True, "done_reason": "stop"}
            ).encode()

    with patch(
        "routes.intensive_reading._ollama_fast_settings",
        return_value=("http://localhost:9", "qwen3:1.7b"),
    ):
        with patch("requests.post", return_value=_FakeResp()):
            r = client.post(
                "/api/intensive-reading/explain-selection",
                json={
                    "selected_text": "a bitter pill",
                    "context": "He found the news a bitter pill to swallow.",
                    "title": "Demo",
                },
            )
            assert r.status_code == 200
            body = r.data.decode("utf-8")
            assert "Means a hard truth." in body
            assert "type" in body


def test_explain_selection_rejects_too_long_selected(client):
    r = client.post(
        "/api/intensive-reading/explain-selection",
        json={"selected_text": "x" * 2001, "context": "Around here."},
    )
    assert r.status_code == 400
    assert "too long" in (r.get_json().get("error") or "").lower()


def test_explain_selection_truncates_long_context(client):
    captured: dict[str, str] = {}

    def _capture_user_msg(**kwargs):
        captured["context"] = kwargs.get("context") or ""
        return "Explain this."

    class _FakeResp:
        status_code = 200

        def iter_lines(self):
            yield json.dumps({"message": {"content": "ok"}}).encode()
            yield json.dumps(
                {"message": {"content": ""}, "done": True, "done_reason": "stop"}
            ).encode()

    with patch(
        "routes.intensive_reading.selection_explain_user_message",
        side_effect=_capture_user_msg,
    ):
        with patch(
            "routes.intensive_reading._ollama_fast_settings",
            return_value=("http://localhost:9", "qwen3:1.7b"),
        ):
            with patch("requests.post", return_value=_FakeResp()):
                r = client.post(
                    "/api/intensive-reading/explain-selection",
                    json={
                        "selected_text": "word",
                        "context": "z" * 9000,
                    },
                )
                assert r.status_code == 200
    assert len(captured["context"]) == 8000


def test_explain_selection_analysis_source_uses_chinese_system_prompt(client):
    captured: dict[str, str] = {}

    class _FakeResp:
        status_code = 200

        def iter_lines(self):
            yield json.dumps({"message": {"content": "ok"}}).encode()
            yield json.dumps(
                {"message": {"content": ""}, "done": True, "done_reason": "stop"}
            ).encode()

    def _capture_post(url, **kwargs):
        captured["system"] = kwargs["json"]["messages"][0]["content"]
        return _FakeResp()

    with patch(
        "routes.intensive_reading._ollama_fast_settings",
        return_value=("http://localhost:9", "qwen3:1.7b"),
    ):
        with patch("requests.post", side_effect=_capture_post):
            r = client.post(
                "/api/intensive-reading/explain-selection",
                json={
                    "selected_text": "bitter pill",
                    "context": "He found the news a bitter pill.",
                    "source": "analysis",
                },
            )
            assert r.status_code == 200
    assert "Simplified Chinese" in captured["system"]
    assert "### 1. 含义与语境" in captured["system"]
    assert "### 1. 本句意思" not in captured["system"]
    assert "### 2. 语境中的其他意思" not in captured["system"]
    assert "Respond entirely in English" not in captured["system"]


def test_explain_selection_passage_uses_fast_model_and_chinese(client):
    captured: dict[str, str] = {}

    class _FakeResp:
        status_code = 200

        def iter_lines(self):
            yield json.dumps({"message": {"content": "ok"}}).encode()
            yield json.dumps(
                {"message": {"content": ""}, "done": True, "done_reason": "stop"}
            ).encode()

    def _capture_post(url, **kwargs):
        captured["model"] = kwargs["json"]["model"]
        captured["system"] = kwargs["json"]["messages"][0]["content"]
        return _FakeResp()

    with patch(
        "routes.intensive_reading._ollama_fast_settings",
        return_value=("http://localhost:9", "qwen3:1.7b"),
    ):
        with patch("requests.post", side_effect=_capture_post):
            r = client.post(
                "/api/intensive-reading/explain-selection",
                json={
                    "selected_text": "bitter pill",
                    "context": "He found the news a bitter pill.",
                    "source": "passage",
                },
            )
            assert r.status_code == 200
    assert captured["model"] == "qwen3:1.7b"
    assert "Simplified Chinese" in captured["system"]
    assert "### 1. 本句意思" in captured["system"]
    assert "### 2. 语境中的其他意思" in captured["system"]
    assert "Respond entirely in English" not in captured["system"]
    assert "Do not use Chinese" not in captured["system"]


def test_explain_prompt_differs_by_learner_level():
    uni = selection_explain_system_prompt("passage", learner_level="university")
    mid = selection_explain_system_prompt("passage", learner_level="middle_school")
    assert "B2" in uni
    assert "A2" in mid
    assert uni != mid


def test_explain_selection_api_forwards_learner_level(client):
    captured: dict[str, str] = {}

    class _FakeResp:
        status_code = 200

        def iter_lines(self):
            yield json.dumps({"message": {"content": "ok"}}).encode()
            yield json.dumps(
                {"message": {"content": ""}, "done": True, "done_reason": "stop"}
            ).encode()

    def _capture_post(url, **kwargs):
        captured["system"] = kwargs["json"]["messages"][0]["content"]
        return _FakeResp()

    with patch(
        "routes.intensive_reading._ollama_fast_settings",
        return_value=("http://localhost:9", "qwen3:1.7b"),
    ):
        with patch("requests.post", side_effect=_capture_post):
            r = client.post(
                "/api/intensive-reading/explain-selection",
                json={
                    "selected_text": "bitter pill",
                    "context": "He found the news a bitter pill.",
                    "learner_level": "middle_school",
                },
            )
            assert r.status_code == 200
    assert "A2" in captured["system"]
    assert "B2–C1" not in captured["system"] and "B2-C1" not in captured["system"]


def test_explain_selection_env_fast_model_not_main(client, monkeypatch):
    monkeypatch.setenv("RAG_AGENT_FAST_MODEL", "tiny-test:1b")
    captured: dict[str, str] = {}

    class _FakeResp:
        status_code = 200

        def iter_lines(self):
            yield json.dumps({"message": {"content": "ok"}}).encode()
            yield json.dumps(
                {"message": {"content": ""}, "done": True, "done_reason": "stop"}
            ).encode()

    def _capture_post(url, **kwargs):
        captured["model"] = kwargs["json"]["model"]
        return _FakeResp()

    with patch("requests.post", side_effect=_capture_post):
        r = client.post(
            "/api/intensive-reading/explain-selection",
            json={
                "selected_text": "bitter pill",
                "context": "He found the news a bitter pill.",
            },
        )
        assert r.status_code == 200
    assert captured["model"] == "tiny-test:1b"
    assert captured["model"] != "qwen3.5:4b"
