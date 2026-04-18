"""
Jarvis Stock Module — centralized path and parameter configuration.

All paths derived from environment variables or project defaults.
Override any path via its env var.

Environment variables (all optional):
  STOCK_REPORTS_ROOT   Stock data/reports directory (default: C:/reports/stock)
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
    os.environ.get("STOCK_REPORTS_ROOT", "C:/reports/stock")
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
