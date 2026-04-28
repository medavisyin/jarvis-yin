---
tags:
  - implementation
  - data-analysis
  - technical-fundamental
category: data-analysis
status: current
last-updated: 2026-04-28
---

# Technical & Fundamental Analysis

> **Category**: DATA ANALYSIS | **Source**: `scripts/stock/technical_analysis.py`, `scripts/stock/fundamental_analysis.py`, `scripts/stock/report_technical.py`, `scripts/stock/sentiment.py`, `scripts/stock/llm_reasoning.py`

## Overview

This layer produces **indicator-driven technical signals**, **cached fundamental metrics and weighted scores**, **Markdown technical reports**, **LLM-scored news sentiment**, and **narrative AI predictions** that fuse all inputs (plus optional XGBoost outputs) via local Ollama or DeepSeek API.

## Architecture & Design

### System Context

```text
daily.csv ──► technical_analysis.analyze ──► technical.json + evaluate_signals
                    │
fundamentals.json ◄── fundamental_analysis.fetch_fundamentals / score_fundamentals
                    │
news/*.json ────────► sentiment.analyze_stock_sentiment ──► sentiment.json
                    │
                    └──► llm_reasoning.generate_prediction (Ollama)
                         llm_reasoning.generate_prediction_deepseek (API)
report_technical.generate_report ──► human-readable MD
```

### Data Flow

1. **OHLCV**: `load_ohlcv` normalizes Chinese column names; `compute_indicators` adds MAs, MACD, RSI, KDJ, Bollinger, OBV, volume MAs, ATR (`technical_analysis.py`).
2. **Signals**: `evaluate_signals` reads last two rows; builds `signals`, `indicators`, pattern list, and bullish/bearish vote for `overall` (`evaluate_signals`, `detect_patterns`, `calc_support_resistance`).
3. **Fundamentals**: `fetch_fundamentals` merges `profile.json`, `realtime.json`, akshare `stock_financial_abstract_ths`; writes `fundamentals.json`. `score_fundamentals` weighted dimensions → `total_score` (`fundamental_analysis.py`).
4. **Sentiment**: `_load_news` globs recent JSON; `analyze_sentiment_single` posts to `{OLLAMA_HOST}/api/chat` with `MODEL_USAGE["sentiment_batch"]`; aggregates `daily_score` and `trend` (`sentiment.py`).
5. **LLM synthesis**: `_load_or_compute` gathers tech, fund, sentiment, optional `xgb_prediction.json`; `_build_prompt` or `_build_deepseek_prompt` formats text; `generate_prediction` streams or buffers Ollama; `generate_prediction_deepseek` uses `call_deepseek` (`llm_reasoning.py`).

### Key Design Decisions

- **Single-file technical cache**: `analyze` writes `technical.json` per symbol for reuse.
- **Fundamental scoring**: Fixed weights (e.g. profitability 25%, growth 25%, valuation 20%) with rule-based buckets (`score_fundamentals`).
- **Sentiment model**: Low temperature (0.1), JSON-only response contract (`sentiment.py` 75–76).
- **DeepSeek path**: Richer prompt including 20-day OHLCV table, fund flow via `china_market_data.stock_fund_flow_signals`, and attempted market context (`llm_reasoning.py` 268–439).

## Implementation Details

### Core Components

| Component | Location | Role |
|-----------|----------|------|
| `load_ohlcv`, `compute_indicators` | `technical_analysis.py` | Data + pandas_ta indicators. |
| `evaluate_signals`, `detect_patterns`, `calc_support_resistance` | same | Signals, candlestick patterns, pivot S/R. |
| `analyze` | same | End-to-end; persists `technical.json`. |
| `fetch_fundamentals`, `score_fundamentals`, `generate_fundamental_report` | `fundamental_analysis.py` | akshare + scoring + MD report. |
| `generate_report`, `_risk_level`, `_trend_assessment` | `report_technical.py` | Risk 1–5, trend table, MD sections. |
| `analyze_stock_sentiment`, `analyze_sentiment_single` | `sentiment.py` | Per-article and batch sentiment. |
| `generate_prediction`, `generate_prediction_deepseek` | `llm_reasoning.py` | Combined narrative outputs. |

### API Surface

- **CLI**: `technical_analysis.py`, `fundamental_analysis.py` as `__main__`.
- **Agent**: `_STOCK_MODULES` in `agent.py` imports these modules for toolbar/API orchestration.

### Configuration

- `STOCK_DATA_DIR`, `OLLAMA_HOST`, `MODEL_USAGE` keys: `sentiment_batch`, `prediction_reasoning` (`config` via stock tree).
- DeepSeek: `call_deepseek` from `config` (used in `generate_prediction_deepseek`).

### Error Handling & Edge Cases

- `evaluate_signals` returns `{"error": "数据不足"}` if &lt;2 rows (`technical_analysis.py` 135–136).
- Sentiment returns `{"error": "无新闻数据"}` when no files (`sentiment.py` 115–117).
- LLM strips `` tags from Ollama responses (`llm_reasoning.py` 216–217, 248–257).

## Code Walkthrough

- **Indicator + overall vote**

```247:258:scripts/stock/technical_analysis.py
    bullish = sum(1 for v in signals.values() if "看涨" in v or "金叉" in v or "超卖" in v)
    bearish = sum(1 for v in signals.values() if "看跌" in v or "死叉" in v or "超买" in v)
    if bullish > bearish + 1:
        overall = "看涨"
    elif bearish > bullish + 1:
        overall = "看跌"
```

- **Pattern example (hammer)**

```305:311:scripts/stock/technical_analysis.py
    if lower_shadow > body * 2 and upper_shadow < body * 0.5 and c > o:
        ...
        if c < recent_trend:
            patterns.append({"name": "锤子线", "direction": "看涨", "strength": "中等",
                             "desc": "长下影线, 买方在低位反击"})
```

- **Fundamental weights**

```256:263:scripts/stock/fundamental_analysis.py
    total = sum(s["score"] * s["weight"] for s in scores.values())

    return {
        "total_score": round(total, 1),
        "dimensions": scores,
        "symbol": data.get("symbol", ""),
        "name": data.get("profile", {}).get("name", ""),
    }
```

- **Ollama prediction payload**

```200:208:scripts/stock/llm_reasoning.py
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "stream": stream,
        "think": False,
        "options": {"temperature": 0.6, "num_predict": 1500, "num_ctx": 4096},
    }
```

## Improvement Ideas

### Short-term

- Add explicit `get_market_sentiment` alias if `llm_reasoning` should consume cached `fetch_all_sentiment` (currently imports `get_market_sentiment` which is not defined in `market_sentiment.py`).

### Medium-term

- Custom indicator builder config layered on `compute_indicators`.
- Streaming sentiment batching to reduce per-article HTTP calls.

### Long-term

- Alternative data feeds (options, short interest where available); comparative peer analysis in `score_fundamentals`; real-time websocket quotes for intraday signals.

## References

- `scripts/stock/technical_analysis.py`, `scripts/stock/report_technical.py`
- `scripts/stock/fundamental_analysis.py`, `scripts/stock/sentiment.py`, `scripts/stock/llm_reasoning.py`
- `scripts/stock/features.py` (consumes technical pipeline for ML)
