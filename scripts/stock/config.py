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
DEEPSEEK_MODEL = "deepseek-v4-pro"

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
    from openai import OpenAI
    key = get_deepseek_key()
    if not key:
        return None
    return OpenAI(api_key=key, base_url=DEEPSEEK_BASE_URL)


def call_deepseek(system_prompt: str, user_prompt: str,
                  max_tokens: int = 4096,
                  reasoning_effort: str = "high") -> dict:
    """Call DeepSeek API via OpenAI SDK and return parsed response.

    Returns dict with keys:
      - ok: bool
      - content: str (assistant reply)
      - reasoning_content: str (chain-of-thought)
      - model: str
      - usage: dict
      - error: str (if ok=False)
    """
    client = _get_deepseek_client()
    if client is None:
        return {"ok": False, "error": "No DeepSeek API key configured"}

    try:
        response = client.chat.completions.create(
            model=DEEPSEEK_MODEL,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            max_tokens=max_tokens,
            stream=False,
            reasoning_effort=reasoning_effort,
            extra_body={"thinking": {"type": "enabled"}},
            timeout=120,
        )
        msg = response.choices[0].message
        return {
            "ok": True,
            "content": msg.content or "",
            "reasoning_content": getattr(msg, "reasoning_content", "") or "",
            "model": response.model or DEEPSEEK_MODEL,
            "usage": {
                "prompt_tokens": response.usage.prompt_tokens,
                "completion_tokens": response.usage.completion_tokens,
                "total_tokens": response.usage.total_tokens,
            } if response.usage else {},
        }
    except Exception as exc:
        return {"ok": False, "error": str(exc)}
