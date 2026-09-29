"""GLM chat adapter: model id, key masking, and Zhipu stream mapping."""
from __future__ import annotations

import json
import os
import sys
from types import SimpleNamespace

import pytest

_RAG = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "scripts", "rag"))
if _RAG not in sys.path:
    sys.path.insert(0, _RAG)

import glm_chat  # noqa: E402


def test_model_id_is_free_flash():
    assert glm_chat.MODEL == "glm-4.7-flash"


def test_normalize_chat_agent_maps_glm_and_ollama():
    assert glm_chat.normalize_chat_agent("glm") == "glm"
    assert glm_chat.normalize_chat_agent("OLLAMA") == "ollama"
    assert glm_chat.normalize_chat_agent("deepseek") == "ollama"
    assert glm_chat.normalize_chat_agent(None) == "ollama"


def test_mask_key_hides_the_middle():
    assert glm_chat.mask_key("sk-1234567890abcd") == "sk-1****abcd"
    assert glm_chat.mask_key("") == ""
    assert glm_chat.mask_key("short") == "****"


def test_public_view_drops_raw_key():
    out = glm_chat.public_view({
        "chat_agent": "glm",
        "glm_api_key": "sk-1234567890abcd",
        "audio_lang_ai": "zh",
    })
    assert out["chat_agent"] == "glm"
    assert out["audio_lang_ai"] == "zh"
    assert "glm_api_key" not in out
    assert out["glm_api_key_masked"] == "sk-1****abcd"


def test_require_key_rejects_blank():
    with pytest.raises(glm_chat.GlmConfigError, match="No GLM API key configured"):
        glm_chat.require_key("  ")


def test_image_turn_message_is_text_only():
    assert "text-only" in glm_chat.image_rejected_message()


def test_resolve_key_uses_the_settings_file_only():
    assert list(glm_chat.resolve_key.__code__.co_varnames[:1]) == ["settings"]
    assert glm_chat.resolve_key.__code__.co_argcount == 1
    assert glm_chat.resolve_key({"glm_api_key": " from-settings "}) == "from-settings"
    assert glm_chat.resolve_key({"glm_api_key": ""}) == ""
    assert glm_chat.resolve_key({}) == ""


def test_messages_for_zhipu_drop_images_and_keep_tool_ids():
    call = glm_chat.ToolCall("call_1", "rag_search", {"query": "ai"})
    msgs = glm_chat.messages_for_zhipu([
        {"role": "system", "content": "sys"},
        {"role": "user", "content": "q", "images": ["abc"]},
        {"role": "assistant", "content": "", "tool_calls": [call]},
        {"role": "tool", "tool_call_id": "call_1", "content": "result"},
    ])
    assert msgs[1] == {"role": "user", "content": "q"}
    assert msgs[2]["tool_calls"][0]["id"] == "call_1"
    assert json.loads(msgs[2]["tool_calls"][0]["function"]["arguments"]) == {"query": "ai"}
    assert msgs[3] == {"role": "tool", "tool_call_id": "call_1", "content": "result"}


def _chunk(content=None, tool_calls=None):
    delta = SimpleNamespace(content=content, tool_calls=tool_calls)
    return SimpleNamespace(choices=[SimpleNamespace(delta=delta)])


class _Client:
    def __init__(self, chunks, captured):
        def create(**kwargs):
            captured.update(kwargs)
            return chunks

        self.chat = SimpleNamespace(completions=SimpleNamespace(create=create))


def test_stream_chat_uses_flash_model_without_thinking():
    captured = {}
    client = _Client([], captured)
    assert list(glm_chat.stream_chat(
        client,
        [{"role": "user", "content": "hi"}],
        tools=[{"type": "function"}],
    )) == []
    assert captured["model"] == "glm-4.7-flash"
    assert captured["stream"] is True
    assert captured["tools"] == [{"type": "function"}]
    assert captured["messages"] == [{"role": "user", "content": "hi"}]
    assert captured["thinking"] == {"type": "disabled"}


def test_stream_chat_joins_split_tool_arguments():
    tc1 = SimpleNamespace(
        index=0,
        id="call_1",
        function=SimpleNamespace(name="rag_search", arguments='{"query":'),
    )
    tc2 = SimpleNamespace(
        index=0,
        id=None,
        function=SimpleNamespace(name=None, arguments='"ai"}'),
    )
    client = _Client([
        _chunk("See"),
        _chunk(None, [tc1]),
        _chunk(None, [tc2]),
    ], {})
    texts = []
    calls = []
    for text, tool_calls in glm_chat.stream_chat(client, [{"role": "user", "content": "hi"}], []):
        if text:
            texts.append(text)
        calls.extend(tool_calls)
    assert texts == ["See"]
    assert len(calls) == 1
    assert calls[0].id == "call_1"
    assert calls[0].function.name == "rag_search"
    assert calls[0].function.arguments == {"query": "ai"}


def test_bad_tool_arguments_become_empty_dict():
    tc = SimpleNamespace(
        index=0,
        id="c",
        function=SimpleNamespace(name="rag_search", arguments="not-json"),
    )
    client = _Client([_chunk(None, [tc])], {})
    calls = []
    for _text, tool_calls in glm_chat.stream_chat(client, [{"role": "user", "content": "hi"}], []):
        calls.extend(tool_calls)
    assert calls[0].function.arguments == {}


def test_public_error_hides_exception_text():
    message = glm_chat.public_error(RuntimeError("Authorization: Bearer sk-1234567890abcd"))
    assert message == "GLM request failed"
    assert "sk-1234567890abcd" not in message


def test_missing_tool_call_id_is_filled_in():
    tc = SimpleNamespace(
        index=2,
        id=None,
        function=SimpleNamespace(name="rag_search", arguments='{"query":"ai"}'),
    )
    client = _Client([_chunk(None, [tc])], {})
    calls = []
    for _text, tool_calls in glm_chat.stream_chat(client, [{"role": "user", "content": "hi"}], []):
        calls.extend(tool_calls)
    assert calls[0].id == "call_2"


def test_apply_settings_post_cannot_write_the_raw_key():
    settings = {"glm_api_key": "keep-me", "chat_agent": "ollama", "audio_lang_ai": "zh"}
    glm_chat.apply_settings_post(
        settings,
        {"glm_api_key": "stolen", "chat_agent": "GLM", "audio_lang_ai": "en"},
        {"glm_api_key": "", "chat_agent": "ollama", "audio_lang_ai": "zh"},
    )
    assert settings["glm_api_key"] == "keep-me"
    assert settings["chat_agent"] == "glm"
    assert settings["audio_lang_ai"] == "en"


def test_save_glm_key_stores_raw_and_returns_mask():
    settings = {}
    masked = glm_chat.save_glm_key(settings, " sk-1234567890abcd ")
    assert settings["glm_api_key"] == "sk-1234567890abcd"
    assert masked == "sk-1****abcd"


def test_cloud_llm_is_per_context_and_defaults_to_deepseek():
    assert glm_chat.cloud_llm() == "deepseek"
    token = glm_chat.set_cloud_llm("glm")
    try:
        assert glm_chat.cloud_llm() == "glm"
    finally:
        glm_chat.reset_cloud_llm(token)
    assert glm_chat.cloud_llm() == "deepseek"
    ignored = glm_chat.set_cloud_llm("ollama")
    try:
        assert glm_chat.cloud_llm() == "deepseek"
    finally:
        glm_chat.reset_cloud_llm(ignored)


def test_normalize_chat_agent_keeps_mimo():
    assert glm_chat.normalize_chat_agent("mimo") == "mimo"
    assert glm_chat.normalize_chat_agent("MIMO") == "mimo"
    assert glm_chat.normalize_chat_agent("deepseek") == "ollama"


def test_cloud_llm_keeps_mimo():
    token = glm_chat.set_cloud_llm("mimo")
    try:
        assert glm_chat.cloud_llm() == "mimo"
    finally:
        glm_chat.reset_cloud_llm(token)


def test_apply_settings_post_skips_mimo_key():
    settings = {"glm_api_key": "g", "mimo_api_key": "keep", "chat_agent": "ollama"}
    glm_chat.apply_settings_post(
        settings,
        {"mimo_api_key": "stolen", "chat_agent": "mimo"},
        {"glm_api_key": "", "mimo_api_key": "", "chat_agent": "ollama"},
    )
    assert settings["mimo_api_key"] == "keep"
    assert settings["chat_agent"] == "mimo"


def test_complete_disables_thinking():
    message = SimpleNamespace(content="A short answer.")
    response = SimpleNamespace(choices=[SimpleNamespace(message=message)])
    captured = {}

    class Completions:
        def create(self, **kwargs):
            captured.update(kwargs)
            return response

    client = SimpleNamespace(chat=SimpleNamespace(completions=Completions()))
    assert glm_chat.complete(client, [{"role": "user", "content": "hi"}], max_tokens=80) == "A short answer."
    assert captured["model"] == "glm-4.7-flash"
    assert captured["stream"] is False
    assert captured["max_tokens"] == 80
    assert captured["thinking"] == {"type": "disabled"}
    assert "tools" not in captured


def test_probe_returns_reply_text():
    message = SimpleNamespace(content="Hello there.")
    response = SimpleNamespace(choices=[SimpleNamespace(message=message)])
    captured = {}

    class Completions:
        def create(self, **kwargs):
            captured.update(kwargs)
            return response

    client = SimpleNamespace(chat=SimpleNamespace(completions=Completions()))
    assert glm_chat.probe(client) == "Hello there."
    assert captured["model"] == "glm-4.7-flash"
    assert captured["stream"] is False
    assert captured["thinking"] == {"type": "disabled"}
