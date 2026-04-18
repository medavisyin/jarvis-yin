# LLM Synthesis Implementation

## Overview

The LLM synthesis layer uses Ollama to generate comprehensive Chinese-language stock analysis reports by aggregating outputs from all other engines.

---

## `llm_reasoning.py`

### Purpose

Aggregate technical, fundamental, sentiment, and ML prediction data, then call Ollama for a long-form Chinese narrative report.

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

## API Integration

The LLM synthesis runs as part of `mode=full` in `POST /api/stock/analyze`:

```
POST /api/stock/analyze { symbol: "600519", mode: "full" }
  → technical analysis
  → fundamental analysis
  → sentiment analysis
  → XGBoost classification
  → LLM synthesis (reads all above)
  ← { technical_report, fundamental_report, sentiment_report, xgb_report, prediction_report }
```

---

## Configuration

| Config Key | Default | Purpose |
|------------|---------|---------|
| `OLLAMA_HOST` | `http://localhost:11434` | Ollama server |
| `MODEL_USAGE["prediction_reasoning"]` | `qwen3.5:4b` (HEAVY) | Model for synthesis |
| Temperature | 0.7 | Creative but controlled |
| `num_predict` | 2000 | Token budget for report |
