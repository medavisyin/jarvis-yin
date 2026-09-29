"""MiMo chat adapter: key masking, flash model, and TTS request shape."""
from __future__ import annotations

import base64
import os
import sys
from types import SimpleNamespace

import pytest

_RAG = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "scripts", "rag"))
if _RAG not in sys.path:
    sys.path.insert(0, _RAG)

import mimo_chat  # noqa: E402


def test_mask_and_public_view_hide_the_raw_key():
    out = mimo_chat.public_view({"mimo_api_key": "sk-1234567890abcd", "chat_agent": "mimo"})
    assert "mimo_api_key" not in out
    assert out["mimo_api_key_masked"] == "sk-1****abcd"
    assert out["chat_agent"] == "mimo"


def test_save_key_strips_and_masks():
    settings = {}
    masked = mimo_chat.save_key(settings, " sk-1234567890abcd ")
    assert settings["mimo_api_key"] == "sk-1234567890abcd"
    assert masked == "sk-1****abcd"


def test_require_key_rejects_blank():
    with pytest.raises(mimo_chat.MimoConfigError, match="No MiMo API key configured"):
        mimo_chat.require_key("  ")


def test_samples_match_the_approved_scripts():
    assert mimo_chat.SPEAK_SAMPLE.startswith("(磁性)夜已经深了")
    assert mimo_chat.SING_SAMPLE.startswith("(唱歌)原谅我这一生不羁放纵爱自由")
    assert "午夜电台" in mimo_chat.SPEAK_SAMPLE
    assert "只你共我" in mimo_chat.SING_SAMPLE


def test_make_client_uses_payg_base_url(monkeypatch):
    captured = {}

    class Fake:
        def __init__(self, **kwargs):
            captured.update(kwargs)

    monkeypatch.setattr("openai.OpenAI", Fake)
    mimo_chat.make_client("sk-test")
    assert captured["api_key"] == "sk-test"
    assert captured["base_url"] == "https://api.xiaomimimo.com/v1"


def _chunk(content=None, tool_calls=None):
    delta = SimpleNamespace(content=content, tool_calls=tool_calls)
    return SimpleNamespace(choices=[SimpleNamespace(delta=delta)])


class _Client:
    def __init__(self, chunks, captured):
        def create(**kwargs):
            captured.update(kwargs)
            return chunks

        self.chat = SimpleNamespace(completions=SimpleNamespace(create=create))


def test_probe_uses_flash_without_thinking():
    message = SimpleNamespace(content="Hello.")
    response = SimpleNamespace(choices=[SimpleNamespace(message=message)])
    captured = {}

    class Completions:
        def create(self, **kwargs):
            captured.update(kwargs)
            return response

    client = SimpleNamespace(chat=SimpleNamespace(completions=Completions()))
    assert mimo_chat.probe(client) == "Hello."
    assert captured["model"] == "mimo-v2.6-flash"
    assert captured["max_completion_tokens"] == 64
    assert captured["temperature"] == 1.0
    assert captured["top_p"] == 0.95
    assert captured["stream"] is False
    assert "thinking" not in captured
    assert "max_tokens" not in captured


def test_complete_uses_max_completion_tokens_without_temperature():
    message = SimpleNamespace(content="A short answer.")
    response = SimpleNamespace(choices=[SimpleNamespace(message=message)])
    captured = {}

    class Completions:
        def create(self, **kwargs):
            captured.update(kwargs)
            return response

    client = SimpleNamespace(chat=SimpleNamespace(completions=Completions()))
    assert mimo_chat.complete(client, [{"role": "user", "content": "hi"}], max_tokens=80) == "A short answer."
    assert captured["max_completion_tokens"] == 80
    assert "thinking" not in captured
    assert "temperature" not in captured


def test_stream_chat_joins_tool_calls_and_fills_missing_ids():
    tc = SimpleNamespace(
        index=2,
        id=None,
        function=SimpleNamespace(name="rag_search", arguments="not-json"),
    )
    captured = {}
    client = _Client([_chunk("See", [tc])], captured)
    texts = []
    calls = []
    for text, tool_calls in mimo_chat.stream_chat(client, [{"role": "user", "content": "hi"}], []):
        if text:
            texts.append(text)
        calls.extend(tool_calls)
    assert texts == ["See"]
    assert calls[0].id == "call_2"
    assert calls[0].function.name == "rag_search"
    assert calls[0].function.arguments == {}
    assert captured["model"] == "mimo-v2.6-flash"
    assert "thinking" not in captured


def test_public_error_hides_the_key():
    message = mimo_chat.public_error(RuntimeError("Bearer sk-1234567890abcd"))
    assert message == "MiMo request failed"
    assert "sk-1234567890abcd" not in message


def test_image_turn_message_is_text_only():
    assert "text-only" in mimo_chat.image_rejected_message()


def test_sanitize_settings_keeps_known_values_and_fills_defaults():
    settings = {"audio_engine": "mimo", "audio_mimo_style": "磁性"}
    mimo_chat.sanitize_settings(settings)
    assert settings["audio_engine"] == "mimo"
    assert settings["audio_mimo_style"] == "磁性"
    blank = {"audio_engine": "edge-tts", "audio_mimo_style": "not-a-style"}
    mimo_chat.sanitize_settings(blank)
    assert blank["audio_engine"] == "edge"
    assert blank["audio_mimo_style"] == "平静"
    missing = {}
    mimo_chat.sanitize_settings(missing)
    assert missing["audio_engine"] == "edge"
    assert missing["audio_mimo_style"] == "平静"


def test_with_style_prefixes_only_when_missing():
    assert mimo_chat.with_style("你好", "磁性") == "(磁性)你好"
    assert mimo_chat.with_style(mimo_chat.SPEAK_SAMPLE, "平静") == mimo_chat.SPEAK_SAMPLE
    assert mimo_chat.with_style("（慵懒）再睡五分钟", "平静") == "（慵懒）再睡五分钟"


def test_voice_for_lang():
    assert mimo_chat.voice_for_lang("zh") == "mimo_default"
    assert mimo_chat.voice_for_lang("en") == "Mia"
    assert mimo_chat.voice_for_lang("zh", "(磁性)夜已经深了") == "白桦"
    assert mimo_chat.voice_for_lang("zh", "(平静)你好") == "mimo_default"
    assert mimo_chat.voice_for_lang("en", "(磁性)hello") == "Dean"


def test_tts_kwargs_for_speak_and_sing():
    speak = mimo_chat.tts_kwargs(mimo_chat.SPEAK_SAMPLE, lang="zh")
    assert speak["model"] == "mimo-v2.5-tts"
    assert speak["messages"][0]["content"] == mimo_chat.SPEAK_SAMPLE
    assert speak["extra_body"]["audio"] == {"format": "wav", "voice": "白桦"}
    assert "thinking" not in speak
    sing = mimo_chat.tts_kwargs(mimo_chat.SING_SAMPLE, lang="zh")
    assert sing["messages"][0]["content"].startswith("(唱歌)")
    assert sing["extra_body"]["audio"]["voice"] == "mimo_default"


def test_decode_audio_reads_attribute_and_model_extra():
    raw = base64.b64encode(b"wav").decode("ascii")
    assert mimo_chat.decode_audio(SimpleNamespace(audio=SimpleNamespace(data=raw))) == b"wav"
    extra = SimpleNamespace(audio=None, model_extra={"audio": {"data": raw}})
    assert mimo_chat.decode_audio(extra) == b"wav"


def test_wav_to_mp3_requires_ffmpeg(monkeypatch):
    monkeypatch.setattr(mimo_chat.shutil, "which", lambda _name: None)
    with pytest.raises(mimo_chat.MimoTtsError, match="ffmpeg is required for MiMo audio"):
        mimo_chat.wav_to_mp3(b"RIFF")
