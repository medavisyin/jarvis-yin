"""DeepSeek deep analysis: empty content / token-budget exhaustion handling."""

from __future__ import annotations

import os
import sys
from types import SimpleNamespace

_STOCK = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "scripts", "stock"))
if _STOCK not in sys.path:
    sys.path.insert(0, _STOCK)


def _fake_response(*, content, reasoning, finish_reason, reasoning_tokens, completion_tokens=None):
    usage = SimpleNamespace(
        prompt_tokens=100,
        completion_tokens=completion_tokens if completion_tokens is not None else (reasoning_tokens or 0),
        total_tokens=100 + (completion_tokens if completion_tokens is not None else (reasoning_tokens or 0)),
        completion_tokens_details=SimpleNamespace(reasoning_tokens=reasoning_tokens),
    )
    msg = SimpleNamespace(content=content, reasoning_content=reasoning)
    choice = SimpleNamespace(message=msg, finish_reason=finish_reason)
    return SimpleNamespace(
        choices=[choice],
        model="deepseek-v4-flash",
        usage=usage,
    )


def _good_report(prefix: str = "完整报告") -> str:
    from llm_reasoning import DEEPSEEK_REPORT_MIN_CHARS
    return f"{prefix}\n" + ("详细分析段落。" * ((DEEPSEEK_REPORT_MIN_CHARS // 7) + 30))


def test_call_deepseek_exposes_finish_reason_and_reasoning_tokens(monkeypatch):
    import config as cfg

    client = SimpleNamespace()
    client.chat = SimpleNamespace(
        completions=SimpleNamespace(
            create=lambda **kwargs: _fake_response(
                content="",
                reasoning="long thinking",
                finish_reason="length",
                reasoning_tokens=512,
                completion_tokens=512,
            )
        )
    )
    monkeypatch.setattr(cfg, "_get_deepseek_client", lambda: client)

    result = cfg.call_deepseek("sys", "user", max_tokens=512)
    assert result["ok"] is True
    assert result["content"] == ""
    assert result["reasoning_content"] == "long thinking"
    assert result["finish_reason"] == "length"
    assert result["usage"]["reasoning_tokens"] == 512
    assert result["usage"]["completion_tokens"] == 512


def test_call_deepseek_can_disable_thinking(monkeypatch):
    import config as cfg

    captured = {}

    def create(**kwargs):
        captured.update(kwargs)
        return _fake_response(
            content="report body",
            reasoning="",
            finish_reason="stop",
            reasoning_tokens=0,
            completion_tokens=20,
        )

    client = SimpleNamespace()
    client.chat = SimpleNamespace(completions=SimpleNamespace(create=create))
    monkeypatch.setattr(cfg, "_get_deepseek_client", lambda: client)

    result = cfg.call_deepseek("sys", "user", max_tokens=2048, thinking=False)
    assert result["ok"] is True
    assert captured["extra_body"]["thinking"]["type"] == "disabled"
    assert result["content"] == "report body"


def test_deepseek_report_call_retries_with_thinking_disabled_and_keeps_first_cot():
    from llm_reasoning import deepseek_report_call

    calls = []
    good = _good_report("## 一句话结论\n偏多")

    def fake_call(system_prompt, user_prompt, max_tokens=4096,
                  reasoning_effort="high", thinking=True):
        calls.append({
            "max_tokens": max_tokens,
            "effort": reasoning_effort,
            "thinking": thinking,
        })
        if len(calls) == 1:
            return {
                "ok": True,
                "content": "",
                "reasoning_content": "first call chain of thought",
                "finish_reason": "length",
                "model": "deepseek-v4-flash",
                "usage": {"reasoning_tokens": 8192},
            }
        return {
            "ok": True,
            "content": good,
            "reasoning_content": "",
            "finish_reason": "stop",
            "model": "deepseek-v4-flash",
            "usage": {"reasoning_tokens": 0},
        }

    result = deepseek_report_call(fake_call, "sys", "user")
    assert result["ok"] is True
    assert "偏多" in result["content"]
    assert result["reasoning_content"] == "first call chain of thought"
    assert len(calls) == 2
    assert calls[0]["thinking"] is True
    assert calls[0]["effort"] == "high"
    assert calls[1]["thinking"] is False
    assert calls[1]["max_tokens"] == 16384


def test_deepseek_report_call_errors_when_still_empty_after_retry():
    from llm_reasoning import deepseek_report_call

    def always_empty(system_prompt, user_prompt, max_tokens=4096,
                     reasoning_effort="high", thinking=True):
        return {
            "ok": True,
            "content": "   ",
            "reasoning_content": "still thinking",
            "finish_reason": "length",
            "model": "deepseek-v4-flash",
            "usage": {"reasoning_tokens": max_tokens},
        }

    result = deepseek_report_call(always_empty, "sys", "user")
    assert result["ok"] is False
    assert "empty" in result["error"].lower() or "incomplete" in result["error"].lower()
    assert result.get("finish_reason") == "length"
    assert result.get("reasoning_content") == "still thinking"


def test_deepseek_report_call_no_retry_when_complete_content_present():
    from llm_reasoning import deepseek_report_call

    calls = []
    good = _good_report("full report body")

    def once(system_prompt, user_prompt, max_tokens=4096,
             reasoning_effort="high", thinking=True):
        calls.append({"thinking": thinking})
        return {
            "ok": True,
            "content": good,
            "reasoning_content": "cot",
            "finish_reason": "stop",
            "model": "deepseek-v4-flash",
            "usage": {},
        }

    result = deepseek_report_call(once, "sys", "user")
    assert result["ok"] is True
    assert result["content"] == good
    assert len(calls) == 1
    assert calls[0]["thinking"] is True


def test_deepseek_report_call_retries_on_length_with_short_stub():
    """Repro 000815: tiny non-empty body + finish_reason=length must retry."""
    from llm_reasoning import deepseek_report_call

    calls = []
    good = _good_report("# 完整报告")

    def stub_then_good(system_prompt, user_prompt, max_tokens=4096,
                       reasoning_effort="high", thinking=True):
        calls.append({"thinking": thinking, "max_tokens": max_tokens})
        if len(calls) == 1:
            return {
                "ok": True,
                "content": "# 000815 深度量化分析报告\n\n**",
                "reasoning_content": "long cot",
                "finish_reason": "length",
                "model": "deepseek-v4-flash",
                "usage": {"reasoning_tokens": 8000},
            }
        return {
            "ok": True,
            "content": good,
            "reasoning_content": "",
            "finish_reason": "stop",
            "model": "deepseek-v4-flash",
            "usage": {"reasoning_tokens": 0},
        }

    result = deepseek_report_call(stub_then_good, "sys", "user")
    assert result["ok"] is True
    assert "完整报告" in result["content"]
    assert result["reasoning_content"] == "long cot"
    assert len(calls) == 2
    assert calls[1]["thinking"] is False


def test_deepseek_report_call_retries_on_too_short_even_if_stop():
    from llm_reasoning import deepseek_report_call

    calls = []
    good = _good_report("完整报告正文")

    def short_then_good(system_prompt, user_prompt, max_tokens=4096,
                        reasoning_effort="high", thinking=True):
        calls.append({"thinking": thinking})
        if len(calls) == 1:
            return {
                "ok": True,
                "content": "太短",
                "reasoning_content": "cot",
                "finish_reason": "stop",
                "model": "deepseek-v4-flash",
                "usage": {},
            }
        return {
            "ok": True,
            "content": good,
            "reasoning_content": "",
            "finish_reason": "stop",
            "model": "deepseek-v4-flash",
            "usage": {},
        }

    result = deepseek_report_call(short_then_good, "sys", "user")
    assert result["ok"] is True
    assert len(calls) == 2
    assert calls[1]["thinking"] is False
    assert result["reasoning_content"] == "cot"
    assert "完整报告正文" in result["content"]


def test_deepseek_report_call_errors_when_still_truncated_after_retry():
    from llm_reasoning import deepseek_report_call

    def always_truncated(system_prompt, user_prompt, max_tokens=4096,
                         reasoning_effort="high", thinking=True):
        return {
            "ok": True,
            "content": "# title\n\n**",
            "reasoning_content": "cot",
            "finish_reason": "length",
            "model": "deepseek-v4-flash",
            "usage": {"reasoning_tokens": max_tokens},
        }

    result = deepseek_report_call(always_truncated, "sys", "user")
    assert result["ok"] is False
    assert "incomplete" in result["error"].lower() or "truncated" in result["error"].lower() or "length" in result["error"].lower()
    assert result.get("finish_reason") == "length"


def test_deepseek_report_call_no_retry_on_first_call_api_error():
    from llm_reasoning import deepseek_report_call

    calls = []

    def fail_first(system_prompt, user_prompt, max_tokens=4096,
                   reasoning_effort="high", thinking=True):
        calls.append(1)
        return {"ok": False, "error": "timeout on first call"}

    result = deepseek_report_call(fail_first, "sys", "user")
    assert result["ok"] is False
    assert result["error"] == "timeout on first call"
    assert len(calls) == 1


def test_deepseek_report_call_merges_first_diagnostics_when_retry_fails():
    from llm_reasoning import deepseek_report_call

    calls = []

    def empty_then_fail(system_prompt, user_prompt, max_tokens=4096,
                        reasoning_effort="high", thinking=True):
        calls.append({"thinking": thinking, "max_tokens": max_tokens})
        if len(calls) == 1:
            return {
                "ok": True,
                "content": "",
                "reasoning_content": "first thinking",
                "finish_reason": "length",
                "model": "deepseek-v4-flash",
                "usage": {"reasoning_tokens": 8192},
            }
        return {"ok": False, "error": "retry timeout"}

    result = deepseek_report_call(empty_then_fail, "sys", "user")
    assert result["ok"] is False
    assert "retry timeout" in result["error"]
    assert "incomplete" in result["error"].lower() or "length" in result["error"].lower()
    assert result.get("reasoning_content") == "first thinking"
    assert result.get("finish_reason") == "length"
    assert result.get("usage", {}).get("reasoning_tokens") == 8192
    assert len(calls) == 2
    assert calls[1]["thinking"] is False
