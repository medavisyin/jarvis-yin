"""DeepSeek OpenAI client swaps to Langfuse drop-in when tracing is on."""
from __future__ import annotations

import importlib.util
import os
import sys

_SCRIPTS = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "scripts"))
if _SCRIPTS not in sys.path:
    sys.path.insert(0, _SCRIPTS)

import tracing  # noqa: E402

import pytest


@pytest.fixture(autouse=True)
def _isolate_dotenv(monkeypatch):
    monkeypatch.setattr(tracing, "DOTENV_PATH", "")


_STOCK_CONFIG = os.path.join(_SCRIPTS, "stock", "config.py")
_spec = importlib.util.spec_from_file_location("jarvis_stock_config_under_test", _STOCK_CONFIG)
stock_config = importlib.util.module_from_spec(_spec)
assert _spec.loader is not None
_spec.loader.exec_module(stock_config)


def test_deepseek_uses_stock_openai_when_tracing_off(monkeypatch):
    monkeypatch.delenv("LANGFUSE_PUBLIC_KEY", raising=False)
    monkeypatch.delenv("LANGFUSE_SECRET_KEY", raising=False)
    tracing.reset_for_tests()
    seen = {}

    class FakeOpenAI:
        def __init__(self, **kwargs):
            seen["cls"] = "stock"
            seen["kwargs"] = kwargs

    monkeypatch.setattr(stock_config, "get_deepseek_key", lambda: "sk-test")
    monkeypatch.setattr(tracing, "openai_client_class", lambda: FakeOpenAI)
    client = stock_config._get_deepseek_client()
    assert client is not None
    assert seen.get("cls") == "stock"


def test_deepseek_uses_langfuse_openai_when_tracing_on(monkeypatch):
    monkeypatch.setenv("LANGFUSE_PUBLIC_KEY", "pk-lf-test")
    monkeypatch.setenv("LANGFUSE_SECRET_KEY", "sk-lf-test")
    tracing.reset_for_tests()
    seen = {}

    class FakeLangfuseOpenAI:
        def __init__(self, **kwargs):
            seen["cls"] = "langfuse"
            seen["kwargs"] = kwargs

    monkeypatch.setattr(stock_config, "get_deepseek_key", lambda: "sk-test")
    monkeypatch.setattr(tracing, "openai_client_class", lambda: FakeLangfuseOpenAI)
    client = stock_config._get_deepseek_client()
    assert seen.get("cls") == "langfuse"
    assert seen["kwargs"]["base_url"] == stock_config.DEEPSEEK_BASE_URL
