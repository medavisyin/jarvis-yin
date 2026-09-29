"""Xiaomi MiMo chat and TTS adapter. GLM stays in glm_chat.py."""
from __future__ import annotations

import base64
import json
import logging
import shutil
import subprocess
from types import SimpleNamespace
from typing import Iterator

logger = logging.getLogger(__name__)

MODEL = "mimo-v2.6-flash"
TTS_MODEL = "mimo-v2.5-tts"
BASE_URL = "https://api.xiaomimimo.com/v1"
_MISSING_KEY = "No MiMo API key configured"
DEFAULT_STYLE = "平静"
_FFMPEG_REQUIRED = "ffmpeg is required for MiMo audio"

SPEAK_SAMPLE = "(磁性)夜已经深了，城市还在呼吸。我是今晚陪你的人，欢迎收听《午夜电台》。"
SING_SAMPLE = "(唱歌)原谅我这一生不羁放纵爱自由，也会怕有一天会跌倒，Oh no。背弃了理想，谁人都可以，哪会怕有一天只你共我。"

STYLES = frozenset({
    "开心", "悲伤", "愤怒", "恐惧", "惊讶", "兴奋", "委屈", "平静", "冷漠",
    "怅然", "欣慰", "无奈", "愧疚", "释然", "嫉妒", "厌倦", "忐忑", "动情",
    "温柔", "高冷", "活泼", "严肃", "慵懒", "俏皮", "深沉", "干练", "凌厉",
    "磁性", "醇厚", "清亮", "空灵", "稚嫩", "苍老", "甜美", "沙哑", "醇雅",
    "夹子音", "御姐音", "正太音", "大叔音", "台湾腔",
    "东北话", "四川话", "河南话", "粤语",
    "孙悟空", "林黛玉",
    "唱歌",
})


class MimoConfigError(Exception):
    """Raised when a MiMo call cannot start because configuration is missing."""


class MimoTtsError(Exception):
    """Raised when MiMo audio cannot be decoded or converted."""


class ToolCall:
    """One finished tool call, shaped so the agent loop can read function.name."""

    def __init__(self, call_id: str, name: str, arguments: dict):
        self.id = call_id
        self.function = SimpleNamespace(name=name, arguments=arguments or {})


def mask_key(key: str) -> str:
    key = key or ""
    if not key:
        return ""
    if len(key) > 8:
        return key[:4] + "****" + key[-4:]
    return "****"


def require_key(key: str) -> str:
    text = (key or "").strip()
    if not text:
        raise MimoConfigError(_MISSING_KEY)
    return text


def resolve_key(settings: dict) -> str:
    return (settings.get("mimo_api_key") or "").strip()


def save_key(settings: dict, key: str) -> str:
    settings["mimo_api_key"] = (key or "").strip()
    return mask_key(settings["mimo_api_key"])


def public_view(settings: dict) -> dict:
    out = dict(settings)
    key = out.pop("mimo_api_key", "") or ""
    out["mimo_api_key_masked"] = mask_key(key)
    return out


def image_rejected_message() -> str:
    return "MiMo chat is text-only"


def public_error(exc: BaseException) -> str:
    logger.warning("MiMo request failed: %s", type(exc).__name__)
    return "MiMo request failed"


def reraise_public(exc: BaseException) -> None:
    """Surface a safe MiMo error. Config and TTS messages stay; other text does not."""
    if isinstance(exc, (MimoConfigError, MimoTtsError)):
        raise exc
    raise MimoTtsError(public_error(exc)) from None


def sanitize_settings(settings: dict) -> None:
    engine = str(settings.get("audio_engine") or "edge").strip().lower()
    settings["audio_engine"] = "mimo" if engine == "mimo" else "edge"
    style = str(settings.get("audio_mimo_style") or DEFAULT_STYLE).strip()
    settings["audio_mimo_style"] = style if style in STYLES else DEFAULT_STYLE


def with_style(text: str, style: str) -> str:
    body = (text or "").strip()
    if not body:
        return body
    if body[0] in "(（[":
        return body
    return f"({style}){body}"


_MALE_STYLES = frozenset({"磁性", "醇厚", "沙哑", "苍老", "大叔音", "孙悟空", "正太音"})


def _leading_style(text: str) -> str:
    body = (text or "").lstrip()
    if not body:
        return ""
    if body[0] == "(":
        end = body.find(")")
    elif body[0] == "（":
        end = body.find("）")
    else:
        return ""
    if end <= 1:
        return ""
    token = body[1:end].strip().split()
    return token[0] if token else ""


def voice_for_lang(lang: str, text: str = "") -> str:
    """Preset voice. China default mimo_default is 冰糖 (female), so male timbre tags use 白桦."""
    english = (lang or "").lower().startswith("en")
    if _leading_style(text) in _MALE_STYLES:
        return "Dean" if english else "白桦"
    if english:
        return "Mia"
    return "mimo_default"


def _arguments_json(arguments) -> str:
    if isinstance(arguments, str):
        return arguments
    return json.dumps(arguments or {}, ensure_ascii=False)


def _as_openai_tool_call(call) -> dict:
    fn = call.function
    return {
        "id": getattr(call, "id", "") or "",
        "type": "function",
        "function": {
            "name": fn.name,
            "arguments": _arguments_json(fn.arguments),
        },
    }


def messages_for_api(messages: list[dict]) -> list[dict]:
    """OpenAI-style messages. Drops image fields and ignores reasoning."""
    out = []
    for msg in messages:
        role = msg.get("role")
        content = msg.get("content") or ""
        if not isinstance(content, str):
            content = str(content)
        tool_calls = msg.get("tool_calls")
        if role == "assistant" and tool_calls:
            out.append({
                "role": "assistant",
                "content": content,
                "tool_calls": [_as_openai_tool_call(tc) for tc in tool_calls],
            })
        elif role == "tool":
            out.append({
                "role": "tool",
                "tool_call_id": msg.get("tool_call_id") or "",
                "content": content,
            })
        else:
            out.append({"role": role, "content": content})
    return out


def _merge_tool_delta(pending: dict, deltas) -> None:
    for tc in deltas or []:
        idx = getattr(tc, "index", None)
        if idx is None:
            idx = 0
        slot = pending.setdefault(idx, {"id": "", "name": "", "arguments": ""})
        tc_id = getattr(tc, "id", None)
        if tc_id:
            slot["id"] = tc_id
        fn = getattr(tc, "function", None)
        if fn is None:
            continue
        name = getattr(fn, "name", None)
        arguments = getattr(fn, "arguments", None)
        if name:
            slot["name"] += name
        if arguments:
            slot["arguments"] += arguments


def _parse_arguments(raw: str) -> dict:
    if not raw:
        return {}
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def make_client(api_key: str):
    from openai import OpenAI
    return OpenAI(api_key=api_key, base_url=BASE_URL)


def stream_chat(client, messages, tools=None, max_tokens: int = 4096) -> Iterator[tuple[str, list]]:
    """Yield (text, []) for content deltas, then ('', [ToolCall, ...]) once."""
    pending: dict = {}
    kwargs = {
        "model": MODEL,
        "messages": messages_for_api(messages),
        "stream": True,
        "max_completion_tokens": max_tokens,
    }
    if tools:
        kwargs["tools"] = tools
    response = client.chat.completions.create(**kwargs)
    for chunk in response:
        choices = getattr(chunk, "choices", None) or []
        if not choices:
            continue
        delta = choices[0].delta
        text = getattr(delta, "content", None) or ""
        _merge_tool_delta(pending, getattr(delta, "tool_calls", None))
        if text:
            yield text, []
    calls = []
    for idx in sorted(pending):
        slot = pending[idx]
        if not slot["name"] and not slot["arguments"]:
            continue
        call_id = slot["id"] or f"call_{idx}"
        calls.append(ToolCall(call_id, slot["name"], _parse_arguments(slot["arguments"])))
    if calls:
        yield "", calls


def complete(client, messages, max_tokens: int = 4096) -> str:
    response = client.chat.completions.create(
        model=MODEL,
        messages=messages_for_api(messages),
        stream=False,
        max_completion_tokens=max_tokens,
    )
    message = response.choices[0].message
    return getattr(message, "content", None) or ""


def probe(client) -> str:
    response = client.chat.completions.create(
        model=MODEL,
        messages=[{"role": "user", "content": "Say hello in one sentence."}],
        stream=False,
        max_completion_tokens=64,
        temperature=1.0,
        top_p=0.95,
    )
    message = response.choices[0].message
    return getattr(message, "content", None) or ""


def tts_kwargs(text: str, lang: str = "zh") -> dict:
    return {
        "model": TTS_MODEL,
        "messages": [{"role": "assistant", "content": text}],
        "extra_body": {
            "audio": {"format": "wav", "voice": voice_for_lang(lang, text)},
        },
    }


def decode_audio(message) -> bytes:
    data = _audio_b64(getattr(message, "audio", None))
    if not data:
        extra = getattr(message, "model_extra", None) or {}
        if isinstance(extra, dict):
            data = _audio_b64(extra.get("audio"))
    if not data:
        raise MimoTtsError("MiMo TTS returned no audio")
    return base64.b64decode(data)


def _audio_b64(audio) -> str:
    if audio is None:
        return ""
    if isinstance(audio, dict):
        return audio.get("data") or ""
    return getattr(audio, "data", None) or ""


def synthesize_wav(client, text: str, *, lang: str = "zh") -> bytes:
    response = client.chat.completions.create(**tts_kwargs(text, lang=lang))
    return decode_audio(response.choices[0].message)


def wav_to_mp3(wav: bytes) -> bytes:
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        raise MimoTtsError(_FFMPEG_REQUIRED)
    proc = subprocess.run(
        [ffmpeg, "-y", "-f", "wav", "-i", "pipe:0", "-f", "mp3", "pipe:1"],
        input=wav,
        capture_output=True,
        timeout=60,
    )
    if proc.returncode != 0 or not proc.stdout:
        raise MimoTtsError("MiMo TTS audio conversion failed")
    return proc.stdout
