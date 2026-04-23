# Configuration Implementation

## Overview

`config.py` is the central configuration for all stock modules. It loads the parent `scripts/config.py` for global paths and defines stock-specific paths, Ollama model tiers, and proxy settings.

---

## Path Variables

| Variable | Default | Source |
|----------|---------|--------|
| `JARVIS_ROOT` | From parent config | Repo root |
| `REPORTS_ROOT` | From parent config | Global reports root |
| `STOCK_REPORTS_ROOT` | `C:/reports/stock` | Env `STOCK_REPORTS_ROOT` |
| `STOCK_DATA_DIR` | `{STOCK_REPORTS_ROOT}/data` | Per-symbol data |
| `STOCK_MODELS_DIR` | `{STOCK_REPORTS_ROOT}/models` | Saved XGBoost models |
| `STOCK_CACHE_DIR` | `{STOCK_REPORTS_ROOT}/.cache` | Hot sector cache etc. |
| `WATCHLIST_FILE` | `{STOCK_REPORTS_ROOT}/watchlist.json` | Watchlist persistence |
| `PORTFOLIO_FILE` | `{STOCK_REPORTS_ROOT}/portfolio.json` | Reserved (unused) |

All directories are auto-created on import via `os.makedirs(..., exist_ok=True)`.

---

## Ollama Configuration

| Variable | Default | Env Override |
|----------|---------|-------------|
| `OLLAMA_HOST` | `http://localhost:11434` | `OLLAMA_HOST` |
| `OLLAMA_MODEL_FAST` | `qwen3:1.7b` | `OLLAMA_MODEL_FAST` |
| `OLLAMA_MODEL_NORMAL` | `qwen3.5:4b` | `OLLAMA_MODEL_NORMAL` |
| `OLLAMA_MODEL_HEAVY` | `qwen3.5:4b` | `OLLAMA_MODEL_HEAVY` |

### MODEL_USAGE Map

| Key | Default Tier | Used By |
|-----|-------------|---------|
| `news_classification` | FAST | Reserved |
| `sentiment_batch` | FAST | `sentiment.py` |
| `technical_summary` | FAST | Legacy (was used by `llm_reasoning.py`) |
| `fundamental_summary` | NORMAL | Reserved |
| `prediction_reasoning` | HEAVY | `llm_reasoning.py`, `scanner.py` Layer 3 |
| `audio_narration` | HEAVY | Reserved |

---

## Proxy

| Variable | Default | Env Override |
|----------|---------|-------------|
| `STOCK_PROXY` | `""` (empty) | `STOCK_PROXY` |

Used by: `fetch_market_data`, `market_sentiment`, `hot_sectors`, `scanner`

---

## DeepSeek API Integration

| Variable | Default | Source |
|----------|---------|--------|
| `DEEPSEEK_API_URL` | `https://api.deepseek.com/chat/completions` | Hardcoded |
| `DEEPSEEK_MODEL` | `deepseek-reasoner` | Hardcoded |
| API Key | `""` | `.global_settings.json` > env `DEEPSEEK_API_KEY` |

### Key Functions

| Function | Purpose |
|----------|---------|
| `get_deepseek_key()` | Resolve API key (settings file → env var) |
| `call_deepseek(system, user, max_tokens, temp)` | Generic chat completion call, returns `{ok, content, reasoning_content, model, usage}` |

Used by: `llm_reasoning.generate_prediction_deepseek()`, `scanner._run_deepseek_for_picks()`

---

## Other Settings

| Variable | Value | Purpose |
|----------|-------|---------|
| `OUTPUT_LANGUAGE` | `"zh"` | Report language (Chinese) |

---

## Disk Layout

```
C:/reports/stock/                    ← STOCK_REPORTS_ROOT
├── watchlist.json                   ← WATCHLIST_FILE
├── portfolio.json                   ← PORTFOLIO_FILE (reserved)
├── train_progress.json              ← Training status
├── data/                            ← STOCK_DATA_DIR
│   └── {symbol}/
│       ├── daily.csv
│       ├── realtime.json
│       ├── profile.json
│       ├── technical.json
│       ├── technical-report.md
│       ├── fundamentals.json
│       ├── fundamental-report.md
│       ├── sentiment.json
│       ├── xgb_prediction.json
│       ├── xgb-report.md
│       ├── price_prediction.json
│       ├── price-prediction-report.md
│       ├── prediction-report.md
│       ├── predictions_log.json
│       └── news/
│           └── {YYYY-MM-DD}.json
├── models/                          ← STOCK_MODELS_DIR
│   └── {symbol}/
│       ├── model.json               ← XGBoost classifier
│       ├── prediction.json
│       ├── features.json
│       ├── price_close_model.json   ← XGBoost regressor
│       ├── price_high_model.json
│       └── price_low_model.json
├── .cache/                          ← STOCK_CACHE_DIR
│   └── hot_sectors_*.json
├── market_sentiment/
│   ├── fear_greed.json
│   ├── vix.json
│   ├── combined.json
│   └── black_swan_alerts.json
└── scans/
    ├── scan_progress.json
    ├── history.json
    ├── {YYYY-MM-DD}.json
    └── {YYYY-MM-DD}-report.md
```
