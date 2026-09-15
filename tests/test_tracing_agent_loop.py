"""Ollama chat in agent_loop records one generation when tracing is on."""
from __future__ import annotations

import os
import sys
from types import SimpleNamespace

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

import tracing  # noqa: E402
import agent_loop  # noqa: E402


@pytest.fixture(autouse=True)
def _isolate_dotenv(monkeypatch):
    monkeypatch.setattr(tracing, "DOTENV_PATH", "")


class _FakeChunk:
    def __init__(self, content="", tool_calls=None, prompt_eval_count=None, eval_count=None):
        self.message = SimpleNamespace(content=content, tool_calls=tool_calls or [])
        self.prompt_eval_count = prompt_eval_count
        self.eval_count = eval_count


def test_traced_ollama_chat_records_usage_on_last_chunk(monkeypatch):
    updates = []
    captured = []

    class FakeGen:
        def update(self, **kwargs):
            updates.append(kwargs)

    class FakeCM:
        def __enter__(self):
            return FakeGen()

        def __exit__(self, *exc):
            return False

    monkeypatch.setattr(agent_loop, "_start_generation", None)
    monkeypatch.setattr(
        tracing,
        "start_generation",
        lambda **kwargs: captured.append(kwargs) or FakeCM(),
    )

    def fake_chat(**kwargs):
        assert kwargs["stream"] is True
        return [
            _FakeChunk("Hel"),
            _FakeChunk("lo", prompt_eval_count=12, eval_count=3),
        ]

    fake_ollama = SimpleNamespace(chat=fake_chat)
    texts = []
    for token, chunk in agent_loop._traced_ollama_chat(
        fake_ollama,
        {
            "model": "qwen3.5:4b",
            "messages": [{"role": "user", "content": "hi"}],
            "stream": True,
            "think": False,
            "options": {},
            "tools": [],
        },
        session_id="sess-1",
    ):
        if token:
            texts.append(token)
    assert "".join(texts) == "Hello"
    assert any(u.get("output") == "Hello" for u in updates)
    usage = next(u["usage_details"] for u in updates if "usage_details" in u)
    assert usage["input_tokens"] == 12
    assert usage["output_tokens"] == 3
    assert captured and captured[0].get("session_id") == "sess-1"
