"""Jarvis chat uses MiMo inside the existing loop when that agent is selected."""
from __future__ import annotations

import os
import sys

import pytest

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

import agent_loop  # noqa: E402
import glm_chat  # noqa: E402
import mimo_chat  # noqa: E402


@pytest.fixture
def mimo_on(monkeypatch):
    agent_loop.init(
        ollama_model="qwen3.5:4b",
        ollama_host="http://localhost:11434",
        ollama_model_fast="qwen3:1.7b",
    )
    agent_loop.configure_glm(agent_fn=lambda: "mimo", key_fn=lambda: "")
    agent_loop.configure_mimo(key_fn=lambda: "sk-1234567890abcd")
    monkeypatch.setattr(agent_loop, "_auto_rag_search", lambda *_a, **_k: ("", []))
    yield
    agent_loop.configure_glm(agent_fn=lambda: "ollama", key_fn=lambda: "")
    agent_loop.configure_mimo(key_fn=lambda: "")


def test_mimo_chat_streams_tokens_and_names_the_model(mimo_on, monkeypatch):
    monkeypatch.setattr(mimo_chat, "make_client", lambda _key: object())
    monkeypatch.setattr(glm_chat, "make_client", lambda _key: (_ for _ in ()).throw(AssertionError("glm")))

    def fake_stream(_client, _messages, _tools):
        yield "Hello", []

    monkeypatch.setattr(mimo_chat, "stream_chat", fake_stream)
    events = list(agent_loop.run_agent("hi"))
    assert events[0] == {"type": "model", "model": "mimo-v2.6-flash"}
    assert {"type": "token", "content": "Hello"} in events
    assert events[-1]["type"] == "answer_done"


def test_mimo_chat_errors_when_key_missing(monkeypatch):
    agent_loop.configure_glm(agent_fn=lambda: "mimo", key_fn=lambda: "")
    agent_loop.configure_mimo(key_fn=lambda: "")
    monkeypatch.setattr(agent_loop, "_auto_rag_search", lambda *_a, **_k: (_ for _ in ()).throw(AssertionError("rag")))
    try:
        events = list(agent_loop.run_agent("hi"))
    finally:
        agent_loop.configure_glm(agent_fn=lambda: "ollama", key_fn=lambda: "")
        agent_loop.configure_mimo(key_fn=lambda: "")
    assert events[0]["type"] == "error"
    assert "No MiMo API key configured" in events[0]["message"]


def test_mimo_chat_rejects_images_before_the_api(mimo_on, monkeypatch):
    def boom(*_a, **_k):
        raise AssertionError("MiMo API called")

    monkeypatch.setattr(mimo_chat, "make_client", boom)
    events = list(agent_loop.run_agent("hi", image_b64="abc"))
    assert events[0]["type"] == "error"
    assert "text-only" in events[0]["message"]


def test_mimo_error_does_not_echo_the_key(mimo_on, monkeypatch):
    monkeypatch.setattr(mimo_chat, "make_client", lambda _key: object())

    def fake_stream(_client, _messages, _tools):
        raise RuntimeError("request failed for key sk-1234567890abcd")
        yield "", []

    monkeypatch.setattr(mimo_chat, "stream_chat", fake_stream)
    events = list(agent_loop.run_agent("hi"))
    assert events[-1]["type"] == "error"
    assert "sk-1234567890abcd" not in events[-1]["message"]
    assert events[-1]["message"] == "MiMo request failed"
