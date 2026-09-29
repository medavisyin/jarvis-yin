"""Jarvis chat uses GLM inside the existing loop when that agent is selected."""
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


@pytest.fixture
def glm_on(monkeypatch):
    agent_loop.init(
        ollama_model="qwen3.5:4b",
        ollama_host="http://localhost:11434",
        ollama_model_fast="qwen3:1.7b",
    )
    agent_loop.configure_glm(agent_fn=lambda: "glm", key_fn=lambda: "sk-1234567890abcd")
    monkeypatch.setattr(agent_loop, "_auto_rag_search", lambda *_a, **_k: ("", []))
    yield
    agent_loop.configure_glm(agent_fn=lambda: "ollama", key_fn=lambda: "")


def test_glm_chat_streams_tokens_and_names_the_model(glm_on, monkeypatch):
    monkeypatch.setattr(glm_chat, "make_client", lambda _key: object())

    def fake_stream(_client, _messages, _tools):
        yield "Hello", []

    monkeypatch.setattr(glm_chat, "stream_chat", fake_stream)
    events = list(agent_loop.run_agent("hi"))
    assert events[0] == {"type": "model", "model": "glm-4.7-flash"}
    assert {"type": "token", "content": "Hello"} in events
    assert events[-1]["type"] == "answer_done"


def test_glm_chat_errors_when_key_missing(monkeypatch):
    agent_loop.configure_glm(agent_fn=lambda: "glm", key_fn=lambda: "")
    monkeypatch.setattr(agent_loop, "_auto_rag_search", lambda *_a, **_k: (_ for _ in ()).throw(AssertionError("rag")))
    try:
        events = list(agent_loop.run_agent("hi"))
    finally:
        agent_loop.configure_glm(agent_fn=lambda: "ollama", key_fn=lambda: "")
    assert events[0]["type"] == "error"
    assert "No GLM API key configured" in events[0]["message"]


def test_glm_chat_rejects_images_before_the_api(glm_on, monkeypatch):
    def boom(*_a, **_k):
        raise AssertionError("GLM API called")

    monkeypatch.setattr(glm_chat, "make_client", boom)
    events = list(agent_loop.run_agent("hi", image_b64="abc"))
    assert events[0]["type"] == "error"
    assert "text-only" in events[0]["message"]


def test_glm_error_does_not_echo_the_key(glm_on, monkeypatch):
    monkeypatch.setattr(glm_chat, "make_client", lambda _key: object())

    def fake_stream(_client, _messages, _tools):
        raise RuntimeError("request failed for key sk-1234567890abcd")
        yield "", []

    monkeypatch.setattr(glm_chat, "stream_chat", fake_stream)
    events = list(agent_loop.run_agent("hi"))
    assert events[-1]["type"] == "error"
    assert "sk-1234567890abcd" not in events[-1]["message"]
    assert events[-1]["message"] == "GLM request failed"


def test_glm_client_is_created_once(glm_on, monkeypatch):
    created = {"n": 0}

    def make_client(_key):
        created["n"] += 1
        return object()

    rounds = {"n": 0}

    def fake_stream(_client, _messages, _tools):
        rounds["n"] += 1
        if rounds["n"] == 1:
            yield "", [glm_chat.ToolCall("call_1", "rag_search", {"query": "ai"})]
            return
        yield "answer", []

    monkeypatch.setattr(glm_chat, "make_client", make_client)
    monkeypatch.setattr(glm_chat, "stream_chat", fake_stream)
    monkeypatch.setattr(agent_loop, "_execute_tool", lambda _name, _args: "found")
    list(agent_loop.run_agent("hi"))
    assert created["n"] == 1


def test_glm_chat_runs_a_tool_then_answers(glm_on, monkeypatch):
    seen = {}

    def fake_stream(_client, messages, _tools):
        if "tool" not in seen:
            seen["tool"] = True
            yield "", [glm_chat.ToolCall("call_1", "rag_search", {"query": "ai"})]
            return
        tool_msgs = [m for m in messages if m.get("role") == "tool"]
        assert tool_msgs[0]["tool_call_id"] == "call_1"
        assert tool_msgs[0]["content"] == "found"
        yield "answer", []

    monkeypatch.setattr(glm_chat, "make_client", lambda _key: object())
    monkeypatch.setattr(glm_chat, "stream_chat", fake_stream)
    monkeypatch.setattr(agent_loop, "_execute_tool", lambda name, args: "found")
    events = list(agent_loop.run_agent("hi"))
    assert {"type": "thinking", "tool": "rag_search", "args": {"query": "ai"}} in events
    assert {"type": "token", "content": "answer"} in events
    assert events[-1]["type"] == "answer_done"
