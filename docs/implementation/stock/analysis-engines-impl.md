# Analysis Engines Implementation

## Overview

Four independent analysis engines produce structured output consumed by the ML pipeline, LLM synthesis, and the scanner.

---

## `technical_analysis.py`

### Purpose

Load OHLCV, compute indicators via **pandas_ta**, evaluate signals, detect patterns, calculate support/resistance.

### Pipeline

```
load_ohlcv(symbol)
  → compute_indicators(df)
    → evaluate_signals(df)
    → detect_patterns(df)
    → calc_support_resistance(df)
      → write technical.json
```

### Indicators

| Family | Implementation | Column(s) |
|--------|---------------|-----------|
| Moving Averages | SMA 5, 10, 20, 60, 120, 250 | `ma_5` … `ma_250` |
| MACD | 12/26/9 | `macd`, `macd_signal`, `macd_hist` |
| RSI | 14-period | `rsi_14` |
| KDJ | `ta.stoch` + `J = 3K - 2D` | `kdj_k`, `kdj_d`, `kdj_j` |
| Bollinger | 20-period, 2σ | `bb_lower`, `bb_mid`, `bb_upper`, `bb_width`, `bb_pct` |
| OBV | On-balance volume | `obv` |
| Volume MA | SMA 5, 20 | `vol_ma_5`, `vol_ma_20` |
| ATR | 14-period | `atr_14` |

Minimum rows: **30** (warning logged if fewer).

### Signal Evaluation (`evaluate_signals`)

Uses **last two rows** for cross-detection (MACD histogram sign change, KDJ K/D cross). Labels are Chinese:

- Bullish cues: `看涨`, `金叉`, `超卖`
- Bearish cues: `看跌`, `死叉`, `超买`
- Overall: count bullish vs bearish → `看涨` / `看跌` / `偏多` / `偏空` / `中性`

### Pattern Detection (`detect_patterns`)

Heuristic rules on recent OHLC bars:
- 锤子线, 射击之星, 十字星
- 看涨/看跌吞没
- 早晨之星
- MA 金叉/死叉 (5/20 cross)
- 放量突破/放量下跌 (volume vs 20-day average)

### Support/Resistance (`calc_support_resistance`)

Classic pivot from latest bar (H/L/C): P, S1/S2, R1/R2 + rolling `recent_high`/`recent_low` over `lookback` (default 60).

### Output

`data/{symbol}/technical.json` — full dict with indicators, signals, patterns, support/resistance, and metadata.

---

## `report_technical.py`

### Purpose

Convert `technical_analysis` output dict into Chinese Markdown report.

### Key Functions

| Function | Description |
|----------|-------------|
| `generate_report(symbol, analysis)` | Build Markdown string |
| `save_report(symbol, analysis)` | Generate + write `technical-report.md` |

### Risk Level (`_risk_level`)

Integer 1–5, baseline 3, adjusted by:
- ATR% thresholds (high → risk up; very low → risk down)
- RSI extremes (>80 or <20 → risk up)
- Volume ratio > 2.5 → risk up

### Trend Assessment (`_trend_assessment`)

Maps short/medium/long to price vs ma5/ma20/ma60 distance bands.

### Markdown Structure

Title (date, overall bias, risk bar) → 价格概览 → 趋势评估 → 技术指标信号 → 关键指标数值 → 支撑/阻力位 → 形态识别 → footer.

---

## `fundamental_analysis.py`

### Purpose

Merge local profile/realtime with **同花顺** annual financial abstract, score dimensions, emit Markdown.

### Data Sources

- Local: `profile.json`, `realtime.json`
- Remote: `ak.stock_financial_abstract_ths(symbol, indicator="按年度")`

### Scoring Dimensions

| Dimension | Weight | Basis |
|-----------|--------|-------|
| 盈利能力 (Profitability) | 25% | ROE bands + net margin bonus |
| 成长性 (Growth) | 25% | Profit YoY primary bands |
| 估值水平 (Valuation) | 20% | PE bands + PB < 1 bonus |
| 财务健康 (Financial Health) | 15% | Debt ratio bands |
| 综合因素 (Comprehensive) | 15% | Market cap size tiers |

Total: weighted sum, **0–100**, rounded 1 decimal. Mapped to star-style grade.

### Number Parsing (`_parse_cn_number`)

Handles Chinese number formats: `1862.22亿` → `186,220,000,000`, `500万` → `5,000,000`.

### Output

- `data/{symbol}/fundamentals.json` — merged valuation + financials
- `data/{symbol}/fundamental-report.md` — Chinese Markdown

---

## `sentiment.py`

### Purpose

Load cached news articles, call **Ollama LLM** per article for sentiment scoring, aggregate, persist.

### Pipeline

```
_load_news(symbol, days=7)
  → analyze_sentiment_single(article)  [up to 20 articles]
    → aggregate → sentiment.json
```

### LLM Contract

- **Model:** `MODEL_USAGE["sentiment_batch"]` (FAST tier)
- **Endpoint:** `POST {OLLAMA_HOST}/api/chat`
- **System prompt:** demands JSON only: `{"score": float, "reason": "..."}`
- **Parameters:** `stream: false`, `think: false`, low temperature

### Think-tag Stripping

If response contains `<redacted_thinking>...</redacted_thinking>`, parser takes content after the closing tag before JSON extraction. Same pattern in `llm_reasoning.py`.

### Aggregation

`daily_score` = mean of non-zero article scores. All zeros → `0.0`.

### Output

- `data/{symbol}/sentiment.json` — per-article scores + `daily_score`
- Markdown string from `generate_sentiment_report`
