# LLM Synthesis Implementation

## Overview

The LLM synthesis layer generates comprehensive Chinese-language stock analysis reports by aggregating outputs from all other engines, then calling either **Ollama** (default) or, when configured, the **optional DeepSeek API (deepseek-v4-pro with thinking) for stock analysis via Global Settings** for the final narrative. Upstream **technical, fundamental, sentiment, XGBoost, and China market / fund-flow data** are always computed or loaded **locally**; only the closing synthesis may use the cloud.

---

## `llm_reasoning.py`

### Purpose

Aggregate technical, fundamental, sentiment, and ML prediction data, then call Ollama **or** `generate_prediction_deepseek()` for a long-form Chinese narrative report.

### Data Aggregation (`_load_or_compute`)

Always runs in order:
1. `technical_analysis.analyze(symbol)` — may refresh `technical.json`
2. Load `fundamentals.json` or empty dict; `score_fundamentals` if data present
3. Load `sentiment.json` or run `analyze_stock_sentiment` on demand
4. Read `xgb_prediction.json` if present (written by `train_and_predict` in same request)

### Prompt Construction (`_build_prompt`)

Structured Chinese sections:
- 价格信息 (price, change, volume)
- 技术分析 (overall signal, individual indicators, support/resistance, patterns)
- 关键指标 (PE, PB, RSI, MACD, etc.)
- 基本面 (ROE, debt ratio, profit growth, scoring)
- 新闻情绪 (daily score + top article summaries)
- XGBoost预测 (direction, confidence, probabilities, walk-forward accuracy, top features)

### Streaming vs Non-streaming

| Mode | Behavior |
|------|----------|
| `stream=False` | Single POST; strips `<redacted_thinking>` suffix; writes `prediction-report.md` |
| `stream=True` | Returns generator; iterates NDJSON lines; skips tokens inside think tags |

### Model Selection

```python
model = MODEL_USAGE.get("prediction_reasoning", "qwen3.5:4b")
```

Uses the **HEAVY** tier for comprehensive analysis.

### Output

`data/{symbol}/prediction-report.md` — full Chinese AI synthesis report.

---

## `generate_prediction_deepseek()` (cloud alternative)

**Purpose:** Same aggregation as the Ollama path (`_load_or_compute` / `_build_prompt` logic) so the model receives identical structured context, but the completion is requested from **`config.call_deepseek()`** using the **`deepseek-v4-pro`** model (via OpenAI SDK with thinking enabled).

**Flow:**
1. Reuse the same data pipeline as Ollama synthesis (local TA, fundamentals, sentiment, XGB readouts).
2. Build system + user prompts (Chinese sections as for Ollama).
3. `call_deepseek(system_prompt, user_prompt, max_tokens=4096, ...)` — response may include **`reasoning_content`** (chain-of-thought) separate from the main answer.
4. Write `data/{symbol}/prediction-report-deepseek.md` and return a **dict** with the report text, reasoning (if any), and metadata.

**How it differs from the Ollama path:**

| | Ollama (`generate_prediction` / `mode=full`) | DeepSeek (`generate_prediction_deepseek`) |
|---|---------------------------------------------|-------------------------------------------|
| Transport | `localhost:11434` | OpenAI SDK → `https://api.deepseek.com` |
| Default model | `MODEL_USAGE["prediction_reasoning"]` (e.g. `qwen3.5:4b`) | `deepseek-v4-pro` with thinking (see `config.py`) |
| Output file | `prediction-report.md` | `prediction-report-deepseek.md` |
| Used by | `POST /api/stock/analyze` with `mode=full` | `POST /api/stock/analyze/deepseek` and **A股分析** UI “DeepSeek” tab |

RAG chat, agent SSE, and briefing pipelines do **not** call this function.

---

## API Integration

The LLM synthesis runs as part of `mode=full` in `POST /api/stock/analyze`, **or** as a dedicated DeepSeek-only call:

```
POST /api/stock/analyze { symbol: "600519", mode: "full" }
  → technical analysis
  → fundamental analysis
  → sentiment analysis
  → XGBoost classification
  → LLM synthesis (Ollama; reads all above)
  ← { technical_report, fundamental_report, sentiment_report, xgb_report, prediction_report }
```

```
POST /api/stock/analyze/deepseek { symbol: "600519" }
  → same local aggregation as above (on-demand)
  → generate_prediction_deepseek()
  ← { ... prediction from DeepSeek, path to prediction-report-deepseek.md }
```

---

## Configuration

| Config Key | Default | Purpose |
|------------|---------|---------|
| `OLLAMA_HOST` | `http://localhost:11434` | Ollama server |
| `MODEL_USAGE["prediction_reasoning"]` | `qwen3.5:4b` (HEAVY) | Model for synthesis |
| Temperature | 0.7 | Creative but controlled |
| `num_predict` | 2000 | Token budget for report |
| `deepseek_api_key` (Global Settings) | (empty) | **Optional DeepSeek API (deepseek-v4-pro with thinking) for stock analysis via Global Settings** — stored in `scripts/rag/.global_settings.json` and read by `get_deepseek_key()` |
| `DEEPSEEK_BASE_URL` / `DEEPSEEK_MODEL` | see `config.py` | OpenAI SDK base URL (`https://api.deepseek.com`) and `deepseek-v4-pro` model id |
