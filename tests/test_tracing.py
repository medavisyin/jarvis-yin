"""Langfuse helper is off by default and never raises into callers."""
from __future__ import annotations

import os
import sys

import pytest

_SCRIPTS = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "scripts"))
if _SCRIPTS not in sys.path:
    sys.path.insert(0, _SCRIPTS)

import tracing  # noqa: E402


@pytest.fixture(autouse=True)
def _isolate_dotenv(monkeypatch):
    monkeypatch.setattr(tracing, "DOTENV_PATH", "")


def test_disabled_when_keys_missing(monkeypatch):
    monkeypatch.delenv("LANGFUSE_PUBLIC_KEY", raising=False)
    monkeypatch.delenv("LANGFUSE_SECRET_KEY", raising=False)
    monkeypatch.setattr(tracing, "DOTENV_PATH", "")
    tracing.reset_for_tests()
    assert tracing.is_enabled() is False


def test_enabled_when_both_keys_set(monkeypatch):
    monkeypatch.setenv("LANGFUSE_PUBLIC_KEY", "pk-lf-test")
    monkeypatch.setenv("LANGFUSE_SECRET_KEY", "sk-lf-test")
    monkeypatch.setenv("LANGFUSE_HOST", "http://localhost:3000")
    tracing.reset_for_tests()
    assert tracing.is_enabled() is True


def test_noop_generation_update_does_not_raise(monkeypatch):
    monkeypatch.delenv("LANGFUSE_PUBLIC_KEY", raising=False)
    monkeypatch.delenv("LANGFUSE_SECRET_KEY", raising=False)
    tracing.reset_for_tests()
    with tracing.start_generation(name="ollama-chat", model="qwen3.5:4b", input={"q": "hi"}) as gen:
        gen.update(output="hello", usage_details={"input_tokens": 1, "output_tokens": 1})


def test_start_generation_fail_open_when_sdk_raises(monkeypatch):
    monkeypatch.setenv("LANGFUSE_PUBLIC_KEY", "pk-lf-test")
    monkeypatch.setenv("LANGFUSE_SECRET_KEY", "sk-lf-test")
    tracing.reset_for_tests()

    import builtins
    real_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name == "langfuse" or name.startswith("langfuse."):
            raise ImportError("simulated missing sdk")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr("builtins.__import__", fake_import)
    with tracing.start_generation(name="x", model="m") as gen:
        gen.update(output="still ok")


def test_bad_encoding_dotenv_does_not_raise(monkeypatch, tmp_path):
    env_file = tmp_path / ".env"
    env_file.write_bytes("LANGFUSE_PUBLIC_KEY=pk\n".encode("utf-16"))
    monkeypatch.setattr(tracing, "DOTENV_PATH", str(env_file))
    monkeypatch.delenv("LANGFUSE_PUBLIC_KEY", raising=False)
    monkeypatch.delenv("LANGFUSE_SECRET_KEY", raising=False)
    tracing.reset_for_tests()
    with tracing.start_generation(name="x", model="m") as gen:
        gen.update(output="ok")
    assert tracing.is_enabled() is False


def test_is_enabled_reads_repo_dotenv(monkeypatch, tmp_path):
    env_file = tmp_path / ".env"
    env_file.write_text(
        "LANGFUSE_PUBLIC_KEY=pk-from-file\nLANGFUSE_SECRET_KEY=sk-from-file\n",
        encoding="utf-8",
    )
    monkeypatch.delenv("LANGFUSE_PUBLIC_KEY", raising=False)
    monkeypatch.delenv("LANGFUSE_SECRET_KEY", raising=False)
    monkeypatch.setattr(tracing, "DOTENV_PATH", str(env_file))
    tracing.reset_for_tests()
    assert tracing.is_enabled() is True


def test_dotenv_does_not_override_process_env(monkeypatch, tmp_path):
    env_file = tmp_path / ".env"
    env_file.write_text(
        "LANGFUSE_PUBLIC_KEY=pk-from-file\nLANGFUSE_SECRET_KEY=sk-from-file\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("LANGFUSE_PUBLIC_KEY", "pk-process")
    monkeypatch.setenv("LANGFUSE_SECRET_KEY", "sk-process")
    monkeypatch.setattr(tracing, "DOTENV_PATH", str(env_file))
    tracing.reset_for_tests()
    tracing.is_enabled()
    assert os.environ["LANGFUSE_PUBLIC_KEY"] == "pk-process"


def test_start_generation_teardown_error_does_not_raise(monkeypatch):
    monkeypatch.setenv("LANGFUSE_PUBLIC_KEY", "pk-lf-test")
    monkeypatch.setenv("LANGFUSE_SECRET_KEY", "sk-lf-test")
    tracing.reset_for_tests()

    class BoomExit:
        def __enter__(self):
            return tracing._NoOpGeneration()

        def __exit__(self, *exc):
            raise RuntimeError("langfuse flush failed")

    class FakeClient:
        def start_as_current_observation(self, **kwargs):
            return BoomExit()

    def fake_get_client():
        return FakeClient()

    class FakePropagate:
        def __init__(self, **kwargs):
            pass

        def __enter__(self):
            return None

        def __exit__(self, *exc):
            return False

    import types
    fake_mod = types.ModuleType("langfuse")
    fake_mod.get_client = fake_get_client
    fake_mod.propagate_attributes = lambda **kw: FakePropagate()
    monkeypatch.setitem(sys.modules, "langfuse", fake_mod)
    with tracing.start_generation(name="x", model="m", session_id="s1") as gen:
        gen.update(output="ok")


def test_openai_client_class_applies_local_host_default(monkeypatch):
    monkeypatch.setenv("LANGFUSE_PUBLIC_KEY", "pk-lf-test")
    monkeypatch.setenv("LANGFUSE_SECRET_KEY", "sk-lf-test")
    monkeypatch.delenv("LANGFUSE_BASE_URL", raising=False)
    monkeypatch.delenv("LANGFUSE_HOST", raising=False)
    tracing.reset_for_tests()

    class FakeOpenAI:
        pass

    import types
    fake_openai_mod = types.ModuleType("langfuse.openai")
    fake_openai_mod.OpenAI = FakeOpenAI
    fake_lf = types.ModuleType("langfuse")
    fake_lf.openai = fake_openai_mod
    monkeypatch.setitem(sys.modules, "langfuse", fake_lf)
    monkeypatch.setitem(sys.modules, "langfuse.openai", fake_openai_mod)
    tracing.openai_client_class()
    assert os.environ.get("LANGFUSE_BASE_URL") == "http://localhost:3000"


def test_make_openai_client_falls_back_when_wrapper_constructor_raises(monkeypatch):
    monkeypatch.setenv("LANGFUSE_PUBLIC_KEY", "pk-lf-test")
    monkeypatch.setenv("LANGFUSE_SECRET_KEY", "sk-lf-test")
    tracing.reset_for_tests()

    class Boom:
        def __init__(self, **kwargs):
            raise RuntimeError("wrapper init failed")

    class Stock:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

    monkeypatch.setattr(tracing, "openai_client_class", lambda: Boom)
    import openai as openai_mod
    monkeypatch.setattr(openai_mod, "OpenAI", Stock)
    client = tracing.make_openai_client(api_key="sk-test", base_url="https://api.deepseek.com")
    assert isinstance(client, Stock)
    assert client.kwargs["api_key"] == "sk-test"
