"""Zhipu GLM chat adapter used when Jarvis settings select the GLM agent."""
from __future__ import annotations

import contextvars
import json
import logging
from types import SimpleNamespace
from typing import Iterator

logger = logging.getLogger(__name__)

MODEL = "glm-4.7-flash"
_MISSING_KEY = "No GLM API key configured"
_CLOUD = contextvars.ContextVar("jarvis_cloud_llm", default="deepseek")


class GlmConfigError(Exception):
    """Raised when a GLM call cannot start because configuration is missing."""


class ToolCall:
    """One finished tool call, shaped so the agent loop can read function.name."""

    def __init__(self, call_id: str, name: str, arguments: dict):
        self.id = call_id
        self.function = SimpleNamespace(name=name, arguments=arguments or {})


def set_cloud_llm(name: str):
    """Remember DeepSeek vs GLM for stock calls on this thread and its children."""
    text = str(name or "").strip().lower()
    value = text if text in ("glm", "mimo") else "deepseek"
    return _CLOUD.set(value)


def reset_cloud_llm(token) -> None:
    _CLOUD.reset(token)


def cloud_llm() -> str:
    return _CLOUD.get()


def normalize_chat_agent(value) -> str:
    text = (value or "").strip().lower()
    if text in ("glm", "mimo"):
        return text
    return "ollama"


def mask_key(key: str) -> str:
    key = key or ""
    if not key:
        return ""
    if len(key) > 8:
        return key[:4] + "****" + key[-4:]
    return "****"


def public_view(settings: dict) -> dict:
    """Copy settings with the raw GLM key replaced by a mask."""
    out = dict(settings)
    key = out.pop("glm_api_key", "") or ""
    out["glm_api_key_masked"] = mask_key(key)
    out["chat_agent"] = normalize_chat_agent(out.get("chat_agent"))
    return out


def require_key(key: str) -> str:
    text = (key or "").strip()
    if not text:
        raise GlmConfigError(_MISSING_KEY)
    return text


def image_rejected_message() -> str:
    return "GLM chat is text-only"


def resolve_key(settings: dict) -> str:
    """Key from the local settings file. Environment variables are not a second store."""
    return (settings.get("glm_api_key") or "").strip()


def public_error(exc: BaseException) -> str:
    """Client-facing GLM failure. The exception text can contain the API key."""
    logger.warning("GLM request failed: %s", type(exc).__name__)
    return "GLM request failed"


def apply_settings_post(settings: dict, data: dict, defaults: dict) -> None:
    """Merge a settings POST. The raw GLM key is not accepted on this path."""
    for key in defaults:
        if key not in data or key in ("glm_api_key", "mimo_api_key"):
            continue
        if key == "chat_agent":
            settings[key] = normalize_chat_agent(data[key])
        else:
            settings[key] = data[key]


def save_glm_key(settings: dict, key: str) -> str:
    settings["glm_api_key"] = (key or "").strip()
    return mask_key(settings["glm_api_key"])


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


def messages_for_zhipu(messages: list[dict]) -> list[dict]:
    """OpenAI-style messages. Drops Ollama image fields."""
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


def stream_chat(client, messages, tools=None, max_tokens: int = 4096) -> Iterator[tuple[str, list]]:
    """Yield (text, []) for content deltas, then ('', [ToolCall, ...]) once."""
    pending: dict = {}
    kwargs = {
        "model": MODEL,
        "messages": messages_for_zhipu(messages),
        "stream": True,
        "max_tokens": max_tokens,
        "thinking": {"type": "disabled"},
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
    """One non-streaming reply. Thinking stays off so the budget is the answer."""
    response = client.chat.completions.create(
        model=MODEL,
        messages=messages_for_zhipu(messages),
        stream=False,
        max_tokens=max_tokens,
        thinking={"type": "disabled"},
    )
    message = response.choices[0].message
    return getattr(message, "content", None) or ""


def probe(client) -> str:
    """One short completion used by the settings test button."""
    response = client.chat.completions.create(
        model=MODEL,
        messages=[{"role": "user", "content": "Say hello in one sentence."}],
        stream=False,
        max_tokens=50,
        thinking={"type": "disabled"},
    )
    message = response.choices[0].message
    return getattr(message, "content", None) or ""


def make_client(api_key: str):
    from zai import ZhipuAiClient
    return ZhipuAiClient(api_key=api_key)
