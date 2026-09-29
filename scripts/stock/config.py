"""
Jarvis Stock Module — centralized path and parameter configuration.

All paths derived from environment variables or project defaults.
Override any path via its env var.

Environment variables (all optional):
  STOCK_REPORTS_ROOT   Stock data/reports directory
                       (default: ~/reports/stock on Mac/Linux, C:/reports/stock on Windows)
  STOCK_PROXY          HTTP/SOCKS proxy for external requests (default: None)
  OLLAMA_HOST          Ollama API host (default: http://localhost:11434)

Model selection is dynamic — heavier analysis uses larger models.
All stock output defaults to Chinese (中文).
"""
import importlib.util
import os
import sys

_scripts_dir = os.path.normpath(os.path.join(os.path.dirname(__file__), ".."))
if _scripts_dir not in sys.path:
    sys.path.insert(0, _scripts_dir)

_parent_config = os.path.join(os.path.dirname(__file__), "..", "config.py")
_spec = importlib.util.spec_from_file_location("jarvis_config", _parent_config)
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)
JARVIS_ROOT = _mod.JARVIS_ROOT
REPORTS_ROOT = _mod.REPORTS_ROOT

STOCK_REPORTS_ROOT = os.path.normpath(
    os.environ.get("STOCK_REPORTS_ROOT", _mod.STOCK_REPORTS_ROOT)
)
STOCK_DATA_DIR = os.path.join(STOCK_REPORTS_ROOT, "data")
STOCK_MODELS_DIR = os.path.join(STOCK_REPORTS_ROOT, "models")
STOCK_CACHE_DIR = os.path.join(STOCK_REPORTS_ROOT, ".cache")

WATCHLIST_FILE = os.path.join(STOCK_REPORTS_ROOT, "watchlist.json")
PORTFOLIO_FILE = os.path.join(STOCK_REPORTS_ROOT, "portfolio.json")

OLLAMA_HOST = os.environ.get("OLLAMA_HOST", "http://localhost:11434")

OLLAMA_MODEL_FAST = os.environ.get("OLLAMA_MODEL_FAST", "qwen3:1.7b")
OLLAMA_MODEL_NORMAL = os.environ.get("OLLAMA_MODEL_NORMAL", "qwen3.5:4b")
OLLAMA_MODEL_HEAVY = os.environ.get("OLLAMA_MODEL_HEAVY", "qwen3.5:4b")

MODEL_USAGE = {
    "news_classification": OLLAMA_MODEL_FAST,
    "sentiment_batch": OLLAMA_MODEL_FAST,
    "technical_summary": OLLAMA_MODEL_FAST,
    "fundamental_summary": OLLAMA_MODEL_NORMAL,
    "prediction_reasoning": OLLAMA_MODEL_HEAVY,
    "audio_narration": OLLAMA_MODEL_HEAVY,
}

OUTPUT_LANGUAGE = "zh"

STOCK_PROXY = os.environ.get("STOCK_PROXY", "")

for _d in [STOCK_DATA_DIR, STOCK_MODELS_DIR, STOCK_CACHE_DIR]:
    os.makedirs(_d, exist_ok=True)

# ── DeepSeek API integration ────────────────────────────────

DEEPSEEK_BASE_URL = "https://api.deepseek.com"
DEEPSEEK_MODEL = "deepseek-v4-flash"

_AGENT_SETTINGS_FILE = os.path.normpath(
    os.path.join(os.path.dirname(__file__), "..", "rag", ".global_settings.json")
)


def get_deepseek_key() -> str:
    """Return configured DeepSeek API key (agent settings file > env var)."""
    if os.path.isfile(_AGENT_SETTINGS_FILE):
        try:
            import json as _json
            with open(_AGENT_SETTINGS_FILE, "r", encoding="utf-8") as f:
                key = _json.load(f).get("deepseek_api_key", "")
                if key:
                    return key.strip()
        except Exception:
            pass
    return os.environ.get("DEEPSEEK_API_KEY", "")


def _get_deepseek_client():
    """Create an OpenAI client configured for the DeepSeek API."""
    from tracing import make_openai_client
    key = get_deepseek_key()
    if not key:
        return None
    return make_openai_client(api_key=key, base_url=DEEPSEEK_BASE_URL)


def get_glm_key() -> str:
    """GLM key from the same local settings file as DeepSeek. No env fallback."""
    if os.path.isfile(_AGENT_SETTINGS_FILE):
        try:
            import json as _json
            with open(_AGENT_SETTINGS_FILE, "r", encoding="utf-8") as f:
                key = _json.load(f).get("glm_api_key", "")
                if key:
                    return key.strip()
        except Exception:
            pass
    return ""


def get_mimo_key() -> str:
    """MiMo key from the same local settings file. No env fallback."""
    if os.path.isfile(_AGENT_SETTINGS_FILE):
        try:
            import json as _json
            with open(_AGENT_SETTINGS_FILE, "r", encoding="utf-8") as f:
                key = _json.load(f).get("mimo_api_key", "")
                if key:
                    return key.strip()
        except Exception:
            pass
    return ""


def _import_glm_chat():
    rag = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "rag"))
    if rag not in sys.path:
        sys.path.insert(0, rag)
    import glm_chat
    return glm_chat


def _import_mimo_chat():
    rag = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "rag"))
    if rag not in sys.path:
        sys.path.insert(0, rag)
    import mimo_chat
    return mimo_chat


def _call_mimo(system_prompt: str, user_prompt: str, max_tokens: int = 4096) -> dict:
    """Same return shape as call_deepseek, using the saved MiMo key."""
    mimo_chat = _import_mimo_chat()
    key = get_mimo_key()
    try:
        mimo_chat.require_key(key)
        client = mimo_chat.make_client(key)
        text = mimo_chat.complete(
            client,
            [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            max_tokens=max_tokens,
        )
        return {
            "ok": True,
            "content": text,
            "reasoning_content": "",
            "finish_reason": "stop",
            "model": mimo_chat.MODEL,
            "usage": {},
        }
    except mimo_chat.MimoConfigError as exc:
        return {"ok": False, "error": str(exc), "content": "", "model": mimo_chat.MODEL, "usage": {}}
    except Exception as exc:
        return {
            "ok": False,
            "error": mimo_chat.public_error(exc),
            "content": "",
            "model": mimo_chat.MODEL,
            "usage": {},
        }


def _call_glm(system_prompt: str, user_prompt: str, max_tokens: int = 4096) -> dict:
    """Same return shape as call_deepseek, using the saved GLM key."""
    glm_chat = _import_glm_chat()
    key = get_glm_key()
    try:
        glm_chat.require_key(key)
        client = glm_chat.make_client(key)
        text = glm_chat.complete(
            client,
            [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            max_tokens=max_tokens,
        )
        return {
            "ok": True,
            "content": text,
            "reasoning_content": "",
            "finish_reason": "stop",
            "model": glm_chat.MODEL,
            "usage": {},
        }
    except glm_chat.GlmConfigError as exc:
        return {"ok": False, "error": str(exc), "content": "", "model": glm_chat.MODEL, "usage": {}}
    except Exception as exc:
        return {
            "ok": False,
            "error": glm_chat.public_error(exc),
            "content": "",
            "model": glm_chat.MODEL,
            "usage": {},
        }


def call_deepseek(system_prompt: str, user_prompt: str,
                  max_tokens: int = 4096,
                  reasoning_effort: str = "high",
                  thinking: bool = True) -> dict:
    """Call DeepSeek API via OpenAI SDK and return parsed response.

    Returns dict with keys:
      - ok: bool
      - content: str (assistant reply)
      - reasoning_content: str (chain-of-thought)
      - finish_reason: str (e.g. stop / length)
      - model: str
      - usage: dict (includes reasoning_tokens when available)
      - error: str (if ok=False)

    Note: thinking tokens share max_tokens with the final answer. finish_reason
    "length" with empty/short content means reasoning exhausted the budget.
    Pass thinking=False to disable thinking mode so the budget goes to content.

    When this thread's cloud provider is GLM or MiMo, the same scanners call that provider instead.
    """
    glm_chat = None
    try:
        glm_chat = _import_glm_chat()
    except Exception:
        glm_chat = None
    if glm_chat is not None and glm_chat.cloud_llm() == "mimo":
        return _call_mimo(system_prompt, user_prompt, max_tokens=max_tokens)
    if glm_chat is not None and glm_chat.cloud_llm() == "glm":
        return _call_glm(system_prompt, user_prompt, max_tokens=max_tokens)

    client = _get_deepseek_client()
    if client is None:
        return {"ok": False, "error": "No DeepSeek API key configured"}

    try:
        kwargs = {
            "model": DEEPSEEK_MODEL,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "max_tokens": max_tokens,
            "stream": False,
            "extra_body": {"thinking": {"type": "enabled" if thinking else "disabled"}},
            "timeout": 120,
        }
        if thinking:
            kwargs["reasoning_effort"] = reasoning_effort
        response = client.chat.completions.create(**kwargs)
        choice = response.choices[0]
        msg = choice.message
        usage = {}
        if response.usage:
            usage = {
                "prompt_tokens": response.usage.prompt_tokens,
                "completion_tokens": response.usage.completion_tokens,
                "total_tokens": response.usage.total_tokens,
            }
            details = getattr(response.usage, "completion_tokens_details", None)
            reasoning_tokens = getattr(details, "reasoning_tokens", None) if details else None
            if reasoning_tokens is not None:
                usage["reasoning_tokens"] = reasoning_tokens
        return {
            "ok": True,
            "content": msg.content or "",
            "reasoning_content": getattr(msg, "reasoning_content", "") or "",
            "finish_reason": getattr(choice, "finish_reason", None) or "",
            "model": response.model or DEEPSEEK_MODEL,
            "usage": usage,
        }
    except Exception as exc:
        return {"ok": False, "error": str(exc)}
