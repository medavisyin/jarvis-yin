"""
Core LLM generation loop for the Jarvis RAG agent.

Contains the run_agent() generator and its helper functions:
- History summarization (_summarize_history)
- Auto-tool invocation helpers (_auto_tool_commit, _auto_tool_jira)

This module is called by api_agent() in agent.py. It yields SSE events
for real-time streaming to the client.
"""

import logging
import os
import re
import sys
from concurrent.futures import ThreadPoolExecutor
from typing import Any

from prompts import (
    SYSTEM_PROMPT_COMPACT,
    SYSTEM_PROMPT_FULL,
    SYSTEM_PROMPT_PROJECT_ADDON,
)
from rag_engine import auto_rag_search as _auto_rag_search
from tools import TOOL_SCHEMAS, execute_tool as _execute_tool
import glm_chat
import mimo_chat

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants (imported lazily from agent.py at runtime to avoid circular deps)
# ---------------------------------------------------------------------------
_OLLAMA_MODEL = None
_OLLAMA_HOST = None
_OLLAMA_MODEL_FAST = None
_MAX_AGENT_ITERATIONS = 8

_SUMMARY_CACHE: dict[str, str] = {}
_RECENT_KEEP = 6
_SUMMARIZE_THRESHOLD = 8


def init(*, ollama_model: str, ollama_host: str, ollama_model_fast: str,
         max_agent_iterations: int = 8):
    """Called once by agent.py at startup to inject configuration."""
    global _OLLAMA_MODEL, _OLLAMA_HOST, _OLLAMA_MODEL_FAST, _MAX_AGENT_ITERATIONS
    _OLLAMA_MODEL = ollama_model
    _OLLAMA_HOST = ollama_host
    _OLLAMA_MODEL_FAST = ollama_model_fast
    _MAX_AGENT_ITERATIONS = max_agent_iterations


def _default_chat_agent() -> str:
    return "ollama"


def _default_glm_key() -> str:
    return ""


_chat_agent_fn = _default_chat_agent
_glm_key_fn = _default_glm_key
_mimo_key_fn = _default_glm_key


def configure_glm(*, agent_fn, key_fn):
    """Point the chat loop at the current settings (Ollama or GLM)."""
    global _chat_agent_fn, _glm_key_fn
    _chat_agent_fn = agent_fn
    _glm_key_fn = key_fn


def configure_mimo(*, key_fn):
    """Point MiMo chat at the saved Xiaomi key. The agent name stays on configure_glm."""
    global _mimo_key_fn
    _mimo_key_fn = key_fn


def set_ollama_model(model: str) -> None:
    """Update the active chat model (called when user switches via /api/switch-model)."""
    global _OLLAMA_MODEL
    _OLLAMA_MODEL = model


# ---------------------------------------------------------------------------
# History summarization
# ---------------------------------------------------------------------------
def _summarize_history(old_messages: list[dict], cache_key: str = "") -> str:
    """Compress older conversation messages into a concise memory block.
    Uses the fast LLM model. Results are cached by cache_key."""
    if cache_key and cache_key in _SUMMARY_CACHE:
        return _SUMMARY_CACHE[cache_key]

    transcript = []
    for m in old_messages:
        role = m.get("role", "?").upper()
        content = (m.get("content", "") or "")[:500]
        transcript.append(f"{role}: {content}")
    text = "\n".join(transcript)

    prompt = (
        "Summarize this conversation between a student and tutor into a concise memory block. "
        "Include: key topics discussed, what the student learned, any mistakes corrected, "
        "and the student's current level of understanding. Keep it under 300 words.\n\n"
        f"{text}"
    )
    try:
        import requests as _req
        resp = _req.post(
            f"{_OLLAMA_HOST}/api/chat",
            json={
                "model": _OLLAMA_MODEL_FAST,
                "messages": [
                    {"role": "system", "content": "You are a conversation summarizer. Be concise and factual."},
                    {"role": "user", "content": prompt},
                ],
                "stream": False,
                "think": False,
                "options": {"num_predict": 400, "num_ctx": 4096, "temperature": 0.3},
            },
            timeout=30,
        )
        if resp.status_code != 200:
            raise RuntimeError(f"Ollama returned {resp.status_code}")
        summary = resp.json().get("message", {}).get("content", "").strip()
        if not summary:
            raise RuntimeError("Empty summary from LLM")
    except Exception as e:
        logger.warning("History summarization failed: %s", e)
        summary = f"[Previous conversation: {len(old_messages)} exchanges about various topics]"
        return summary

    if cache_key:
        if len(_SUMMARY_CACHE) > 100:
            _SUMMARY_CACHE.pop(next(iter(_SUMMARY_CACHE)))
        _SUMMARY_CACHE[cache_key] = summary
    return summary


# ---------------------------------------------------------------------------
# Auto-tool wrappers (call the tool functions registered in agent.py)
# ---------------------------------------------------------------------------
_tool_commit_fn = None
_tool_jira_fn = None


def register_auto_tools(*, commit_fn=None, jira_fn=None):
    """Called by agent.py to inject auto-tool functions."""
    global _tool_commit_fn, _tool_jira_fn
    _tool_commit_fn = commit_fn
    _tool_jira_fn = jira_fn


def _auto_tool_commit() -> str:
    if _tool_commit_fn:
        return _tool_commit_fn(hours=72)
    return "commit_summary not available"


def _auto_tool_jira() -> str:
    if _tool_jira_fn:
        return _tool_jira_fn()
    return "jira_report not available"


# ---------------------------------------------------------------------------
# Main LLM generation loop
# ---------------------------------------------------------------------------
def _usage_from_chunk(chunk) -> dict:
    prompt = getattr(chunk, "prompt_eval_count", None)
    out = getattr(chunk, "eval_count", None)
    if prompt is None and out is None:
        return {}
    details = {}
    if prompt is not None:
        details["input_tokens"] = int(prompt)
    if out is not None:
        details["output_tokens"] = int(out)
    return details


_start_generation = None


def _get_start_generation():
    global _start_generation
    if _start_generation is None:
        _scripts = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
        if _scripts not in sys.path:
            sys.path.insert(0, _scripts)
        from tracing import start_generation as _sg
        _start_generation = _sg
    return _start_generation


def _traced_ollama_chat(ollama_mod, call_kwargs: dict, *, session_id=None):
    """Call ollama.chat; yield (token_text, chunk). Records one Langfuse generation."""
    start_generation = _get_start_generation()

    stream = call_kwargs.get("stream", True)
    with start_generation(
        name="ollama-chat",
        model=call_kwargs.get("model") or "",
        input={"messages": call_kwargs.get("messages")},
        session_id=session_id,
        metadata={"stream": stream},
    ) as gen:
        try:
            result = ollama_mod.chat(**call_kwargs)
        except Exception as exc:
            try:
                gen.update(output=str(exc), metadata={"error": True})
            except Exception:
                pass
            raise
        full = ""
        last_chunk = None
        if stream:
            for chunk in result:
                last_chunk = chunk
                msg = getattr(chunk, "message", None)
                text = (getattr(msg, "content", None) or "") if msg is not None else ""
                full += text
                yield text, chunk
        else:
            last_chunk = result
            msg = getattr(result, "message", None)
            full = (getattr(msg, "content", None) or "") if msg is not None else ""
            yield full, result
        usage = _usage_from_chunk(last_chunk) if last_chunk is not None else {}
        update_kwargs = {"output": full}
        if usage:
            update_kwargs["usage_details"] = usage
        try:
            gen.update(**update_kwargs)
        except Exception:
            pass


def run_agent(user_query: str, image_b64: str | None = None,
              conversation_history: list[dict] | None = None,
              system_prompt_override: str | None = None,
              rag_query_override: str | None = None,
              suggested_tools: list[str] | None = None,
              auto_prefetch: list[str] | None = None,
              session_id: str | None = None):
    """
    Generator that yields SSE events as the agent reasons.
    Uses streaming LLM output for perceived-instant responses.

    Args:
        rag_query_override: If set, use this string for RAG search instead of
            user_query. Useful when the user's raw input (e.g. "topic 16")
            needs to be resolved to a meaningful search term.
        suggested_tools: If provided, reorder tool schemas so these tools appear
            first (giving the LLM a contextual hint). All tools remain available.
        auto_prefetch: Tool names to auto-invoke in parallel with RAG search.
            When provided (from pipeline), replaces keyword-based detection.
            When None (legacy/learning paths), falls back to keyword heuristics.

    Events:
      {"type": "model", "model": "..."}
      {"type": "thinking", "tool": "...", "args": {...}}
      {"type": "tool_result", "tool": "...", "preview": "..."}
      {"type": "token", "content": "..."}
      {"type": "answer_done", "sources": [...]}
      {"type": "error", "message": "..."}
    """
    agent_name = _chat_agent_fn()
    use_glm = agent_name == "glm"
    use_mimo = agent_name == "mimo"
    cloud = glm_chat if use_glm else mimo_chat if use_mimo else None
    cloud_key = ""
    if cloud is not None and image_b64:
        yield {"type": "error", "message": cloud.image_rejected_message()}
        return
    if cloud is not None:
        key_fn = _glm_key_fn if use_glm else _mimo_key_fn
        try:
            cloud_key = cloud.require_key(key_fn())
        except (glm_chat.GlmConfigError, mimo_chat.MimoConfigError) as exc:
            yield {"type": "error", "message": str(exc)}
            return

    effective_model = cloud.MODEL if cloud is not None else _OLLAMA_MODEL
    yield {"type": "model", "model": effective_model}

    messages: list[dict] = []

    if conversation_history:
        n = len(conversation_history)
        if n > _SUMMARIZE_THRESHOLD:
            old_msgs = conversation_history[: n - _RECENT_KEEP]
            recent_msgs = conversation_history[n - _RECENT_KEEP :]
            cache_key = f"{n - _RECENT_KEEP}:{hash(str(old_msgs[-1].get('content', '')[:100]))}"
            yield {"type": "thinking", "tool": "memory_summarize",
                   "args": {"old_messages": len(old_msgs), "recent_kept": len(recent_msgs)}}
            summary = _summarize_history(old_msgs, cache_key)
            messages.append({"role": "system",
                             "content": f"[CONVERSATION MEMORY]\n{summary}\n[END MEMORY]"})
            for msg in recent_msgs:
                messages.append({"role": msg["role"], "content": msg["content"]})
        else:
            for msg in conversation_history:
                messages.append({"role": msg["role"], "content": msg["content"]})

    collected_sources: list[dict] = []

    rag_search_query = rag_query_override or user_query

    if auto_prefetch is not None:
        need_commits = "commit_summary" in auto_prefetch
        need_jira = "jira_report" in auto_prefetch
    else:
        q_lower = user_query.lower()
        _commit_kw = ("commit", "git log", "pushed", "merged", "code change", "repository activity")
        _jira_kw = ("jira", "ticket", "sprint", "backlog", "open issue", "task status")
        need_commits = any(kw in q_lower for kw in _commit_kw)
        need_jira = any(kw in q_lower for kw in _jira_kw)

    rag_context = ""
    auto_tool_context = ""
    futures = {}
    with ThreadPoolExecutor(max_workers=3) as pool:
        futures["rag"] = pool.submit(_auto_rag_search, rag_search_query, rag_search_query.lower())
        if need_commits:
            yield {"type": "thinking", "tool": "commit_summary (auto)", "args": {"hours": 72}}
            futures["commits"] = pool.submit(_auto_tool_commit)
        if need_jira:
            yield {"type": "thinking", "tool": "jira_report (auto)", "args": {}}
            futures["jira"] = pool.submit(_auto_tool_jira)

        for key, future in futures.items():
            try:
                result = future.result(timeout=60)
                if key == "rag":
                    rag_context, rag_sources = result
                    collected_sources.extend(rag_sources)
                    if rag_context:
                        rag_display = rag_search_query[:80]
                        if rag_query_override:
                            rag_display = f"{rag_query_override[:60]} (resolved from: {user_query[:20]})"
                        yield {"type": "thinking", "tool": "rag_search (auto)",
                               "args": {"query": rag_display}}
                elif key == "commits":
                    auto_tool_context += f"\n\n--- Git commit data ---\n{result}\n--- End commit data ---\n"
                    yield {"type": "tool_result", "tool": "commit_summary", "preview": result[:200]}
                elif key == "jira":
                    auto_tool_context += f"\n\n--- Jira report ---\n{result[:1500]}\n--- End Jira report ---\n"
                    yield {"type": "tool_result", "tool": "jira_report", "preview": result[:200]}
            except Exception:
                pass

    context_block = rag_context + auto_tool_context
    has_auto_context = bool(context_block.strip())

    if system_prompt_override:
        sys_prompt = system_prompt_override
    elif has_auto_context:
        sys_prompt = SYSTEM_PROMPT_COMPACT
    else:
        sys_prompt = SYSTEM_PROMPT_FULL

    _project_item_types = {
        "project_summary", "project_identity", "project_dependency",
        "code_doc", "ai_integration", "rest_endpoint", "project_technology",
        "project_readme", "config_analysis",
    }
    has_project_context = any(
        s.get("item_type", "") in _project_item_types
        for s in collected_sources
    )
    if has_project_context and not system_prompt_override:
        sys_prompt += "\n\n" + SYSTEM_PROMPT_PROJECT_ADDON

    messages.insert(0, {"role": "system", "content": sys_prompt})

    if has_auto_context:
        if system_prompt_override:
            augmented_query = (
                f"USER QUESTION: {user_query}\n\n"
                f"SUPPLEMENTARY REFERENCE MATERIAL (use to enrich your answer, "
                f"but follow the teaching structure in your system prompt first):\n"
                f"{context_block}"
            )
        else:
            augmented_query = (
                f"USER QUESTION: {user_query}\n\n"
                f"IMPORTANT: Use ONLY the following retrieved data to answer. "
                f"Do NOT say 'no information found' if the data below is relevant.\n"
                f"{context_block}"
            )
    else:
        augmented_query = user_query

    history_len = sum(len(m.get("content", "")) for m in messages)
    ctx_len = len(augmented_query) + len(sys_prompt) + history_len
    is_deep_model = "8b" in effective_model
    if system_prompt_override:
        num_ctx = 8192 if ctx_len < 6000 else 16384
    elif is_deep_model:
        num_ctx = 8192 if ctx_len < 6000 else 16384 if ctx_len < 14000 else 32768
    else:
        num_ctx = 2048 if ctx_len < 1500 else 4096 if ctx_len < 6000 else 8192 if ctx_len < 14000 else 16384

    user_msg: dict[str, Any] = {"role": "user", "content": augmented_query}
    if image_b64:
        user_msg["images"] = [image_b64]
    messages.append(user_msg)

    # Always provide tools — let the LLM decide when to use them.
    # If the pipeline suggested specific tools, reorder schemas so those appear first.
    effective_tools = TOOL_SCHEMAS
    if suggested_tools:
        priority = [s for s in TOOL_SCHEMAS
                    if s.get("function", {}).get("name") in suggested_tools]
        rest = [s for s in TOOL_SCHEMAS
                if s.get("function", {}).get("name") not in suggested_tools]
        effective_tools = priority + rest

    cloud_client = None
    if cloud is not None:
        try:
            cloud_client = cloud.make_client(cloud_key)
        except Exception as exc:
            yield {"type": "error", "message": cloud.public_error(exc)}
            return

    for iteration in range(_MAX_AGENT_ITERATIONS):
        try:
            full_content = ""
            tool_calls = []
            if cloud is not None:
                for text, calls in cloud.stream_chat(cloud_client, messages, effective_tools):
                    if text:
                        full_content += text
                        yield {"type": "token", "content": text}
                    if calls:
                        tool_calls.extend(calls)
            else:
                import ollama
                call_kwargs: dict[str, Any] = {
                    "model": effective_model,
                    "messages": messages,
                    "stream": True,
                    "think": False,
                    "options": {"num_ctx": num_ctx, "num_predict": 4096},
                }
                call_kwargs["tools"] = effective_tools
                stream_iter = _traced_ollama_chat(ollama, call_kwargs, session_id=session_id)
                for text, chunk in stream_iter:
                    c = chunk.message
                    if text:
                        full_content += text
                        yield {"type": "token", "content": text}
                    if c.tool_calls:
                        tool_calls.extend(c.tool_calls)
        except Exception as e:
            if cloud is not None:
                yield {"type": "error", "message": cloud.public_error(e)}
            else:
                yield {"type": "error", "message": f"Ollama error: {e}"}
            return

        if not tool_calls:
            suggestions = []
            if collected_sources:
                confs = [s.get("confidence", "medium") for s in collected_sources]
                if confs and confs[0] != "high":
                    suggestions = [s["title"] for s in collected_sources
                                   if s.get("title") and s["title"] != user_query][:4]
            yield {"type": "answer_done", "sources": collected_sources,
                   "suggestions": suggestions}
            return

        messages.append({"role": "assistant", "content": full_content,
                         "tool_calls": tool_calls})

        for call in tool_calls:
            tool_name = call.function.name
            tool_args = call.function.arguments or {}

            yield {"type": "thinking", "tool": tool_name, "args": tool_args}

            if tool_name == "analyze_image" and image_b64:
                focus = tool_args.get("image_description_request", "Describe this image in detail")
                try:
                    vision_kwargs = {
                        "model": _OLLAMA_MODEL,
                        "messages": [{
                            "role": "user",
                            "content": focus,
                            "images": [image_b64],
                        }],
                        "stream": False,
                        "think": False,
                        "options": {"num_ctx": 2048, "num_predict": 512},
                    }
                    result_str = "No analysis produced."
                    for text, _chunk in _traced_ollama_chat(
                        ollama, vision_kwargs, session_id=session_id
                    ):
                        result_str = text or result_str
                except Exception as e:
                    result_str = f"Vision analysis error: {e}"
            else:
                result_str = _execute_tool(tool_name, tool_args)

            preview = result_str[:200] + ("..." if len(result_str) > 200 else "")
            yield {"type": "tool_result", "tool": tool_name, "preview": preview}

            if tool_name in ("rag_search", "briefing_search", "confluence_search"):
                for line in result_str.split("\n\n"):
                    m = re.match(r'\d+\.\s*\[([^\]]*)\]\s*(.+?)\s*\(', line)
                    if m:
                        collected_sources.append({
                            "source": m.group(1),
                            "title": m.group(2).strip(),
                        })

            # Record pattern for memory learning
            try:
                from memory.patterns import record_pattern as _record_pattern
                _record_pattern(
                    query=user_query,
                    tools_used=[tool_name],
                    tool_args=tool_args,
                    session_id="",
                )
            except Exception:
                pass

            tool_msg = {"role": "tool", "content": result_str}
            call_id = getattr(call, "id", None)
            if call_id:
                tool_msg["tool_call_id"] = call_id
            messages.append(tool_msg)

    yield {
        "type": "error",
        "message": f"Agent reached maximum iterations ({_MAX_AGENT_ITERATIONS}) without a final answer.",
    }
