# Market Scanner Implementation

## Overview

The scanner performs a 3-layer full-market A-share scan: fetch all stocks, filter by quantitative criteria, analyze technicals/sentiment, then rank via LLM. Produces TOP 5 AI recommendations with buy-price ranges.

---

## Architecture

```
start_scan()  →  _run_scan()  [background thread]
  └─ _run_scan_inner()
       ├── hot_sectors.get_hot_stock_set()     → set of codes in hot sectors
       ├── _layer1_quick_filter(hot_stocks)    → (candidates[], market_total)
       ├── _execute_layer2_and_3(progress, candidates)
       │     ├── _layer2_batch_analyze(batch)  → scored candidates with tech + sentiment
       │     ├── _layer3_llm_rank(all_l2)      → TOP 5 with LLM reasoning + buy range
       │     └── _save_results + _save_history_entry
       └── _save_progress at each stage
```

---

## Layer 1: Quick Filter (`_layer1_quick_filter`)

### Data Source

```
Primary: ak.stock_zh_a_spot_em() — full market snapshot
Fallback: _fetch_market_eastmoney() — Sina paginated API (80 stocks/page, up to 80 pages)
```

### Filter Criteria (all must pass)

| Criterion | Rule |
|-----------|------|
| Not ST | `"ST" not in str(名称)` |
| 涨跌幅 | -3% to +8% |
| 换手率 | ≥ 1% |
| 成交额 | ≥ 50,000,000 (5000万) |
| 市盈率(动态) | > 0 and < 100 |

### Scoring

`score_l1 = 涨跌幅 × 2 + 换手率 + (100 − PE) × 0.3 + (10 if hot_sector)`

Sorted descending, capped at `LAYER2_CANDIDATE_CAP` (100).

### Returns

Tuple `(candidates, market_total)` — filtered list + raw market count before filtering.

---

## Layer 2: Batch Analysis (`_layer2_batch_analyze`)

Processes candidates in batches of `LAYER2_BATCH` (10).

Per stock:
1. `update_stock_data(symbol)` — fetch latest data
2. `technical_analysis.analyze(symbol)` — compute indicators + signals
3. Sentiment analysis if news exists
4. `china_market_data.stock_fund_flow_signals(symbol)` — fund flow + **smart money phase detection**
5. `fundamental_analysis.fetch_fundamentals(symbol)` — PE/PB/ROE etc

**Score weights:**
```
ff_score × 0.30         ← fund flow (布局期 bonus: 80+)
+ fund_score × 0.25     ← fundamental quality
+ tech_score × 0.20     ← technical signals
+ sentiment_score × 0.10
+ layer1_score × 0.10
+ hot_bonus (5pt)
+ overbought penalty (-10pt if RSI > 80)
```

`ff_score` is boosted for "布局期" (smart money accumulation) stocks, penalized for "出货期" (distribution).

Progress saved to `scan_progress.json` after each batch (supports resume on interruption).

---

## Layer 3: LLM Ranking (`_layer3_llm_rank`)

Takes top `LAYER3_CAP` (20) from Layer 2.

### LLM Call

```python
POST {OLLAMA_HOST}/api/chat
{
    "model": MODEL_USAGE["prediction_reasoning"],
    "messages": [
        {"role": "system", "content": "你是专业A股分析师。只输出JSON，不要任何其他文字。"},
        {"role": "user", "content": prompt},
    ],
    "stream": False,
    "think": False,
    "options": {"temperature": 0.3, "num_predict": 500},
}
```

**Key design decision:** `think: false` disables qwen3.5's internal reasoning mode. Without this, the model consumes all `num_predict` tokens on `<think>` blocks, leaving nothing for JSON output.

### Prompt (`_build_scoring_prompt`)

Structured Chinese prompt providing: stock name, code, price, change%, turnover, PE, amount, tech/sentiment scores, hot-sector flag, technical signals, **smart money phase** (布局期/拉升期/出货期 + detail). Requests JSON with:
- `score`: 0–100
- `reason`: 50-char explanation
- `risk`: 30-char risk summary
- `buy_low`, `buy_high`: recommended buy range

Uses concrete number examples (not angle brackets) to guide small models.

### Response Parsing (`_parse_llm_score`)

Robust parser handling common LLM output issues:
1. Strip `<think>...</think>` blocks
2. Strip markdown code fences
3. Fix single quotes → double quotes
4. Remove trailing commas before `}`
5. Extract outermost `{...}` JSON object
6. Fallback: use `score_l2` with "LLM输出解析失败" message

---

## Constants

| Constant | Value | Purpose |
|----------|-------|---------|
| `LAYER2_CANDIDATE_CAP` | 100 | Max Layer 1 → Layer 2 |
| `LAYER3_CAP` | 20 | Max Layer 2 → Layer 3 |
| `TOP_N` | 5 | Final recommendation count |
| `LAYER2_BATCH` | 10 | Layer 2 batch size |

---

## Thread Safety

- Background `threading.Thread` (`_scan_thread`)
- `_scan_lock` (Lock) prevents concurrent scans
- `_stop_event` (Event) for graceful cancellation
- `sys.modules["config"]` explicitly set via `importlib` in thread
- **Stale module cleanup:** `_run_scan_inner()` removes 12 stock modules from `sys.modules` at thread start (`technical_analysis`, `fundamental_analysis`, `sentiment`, `features`, `china_market_data`, etc.) to avoid `KeyError` from partially-removed modules when the Flask `_with_stock_imports` decorator has already cleaned up before the background thread runs

---

## Phase 4: Comprehensive Analysis

After Layer 3 selects top picks with `verdict == "买入"`, an automatic **Phase 4** runs `_run_comprehensive_for_picks()` that enriches each recommended stock with:

| Dimension | Source | "Supports buy" if... |
|-----------|--------|---------------------|
| **Technical** | `evaluate_signals()` | `overall` is 看涨/偏多 and RSI < 75 |
| **ML Direction** | `model_xgboost.train_and_predict()` | XGBoost predicts 涨 with confidence > 50% |
| **Price Prediction** | `model_price_predictor.train_price_prediction()` | Predicted close change > +0.5% |
| **Fund Flow (聪明钱)** | `china_market_data.stock_fund_flow_signals()` → `detect_smart_money_accumulation()` | Phase == "布局期" (funds in + price flat) |
| **Scanner** | Layer 3 verdict | verdict == "买入" |

**Star Rating:** `support_count / total_dims * 5` (rounded)

| Stars | Conclusion |
|-------|-----------|
| 4-5 | 多维共振,建议建仓 |
| 3 | 多数支持,可考虑小仓 |
| 2 | 信号分歧,建议观望 |
| 0-1 | 支持不足,暂不建议 |

## Phase 5: DeepSeek Deep Analysis (Optional)

When the user checks the "DeepSeek" checkbox before scanning, `_run_deepseek_for_picks()` runs after Phase 4 for each TOP pick:

- **Input**: All comprehensive analysis data (technical, ML, price, fund flow, scanner verdict) serialized as a structured prompt
- **Model**: `deepseek-reasoner` via `https://api.deepseek.com/chat/completions`
- **Output per stock**: `{ report, reasoning (chain-of-thought), model, usage }`
- **Display**: Separate DeepSeek card below each stock's comprehensive report, with collapsible CoT

This phase is skipped entirely if no API key is configured.

---

## Progress Tracking

`{STOCK_REPORTS_ROOT}/scans/scan_progress.json`:

| Field | Description |
|-------|-------------|
| `status` | `layer1` / `layer2_in_progress` / `layer3` / `comprehensive` / `deepseek` / `done` / `error` / `stopped` |
| `market_total` | Raw full-market stock count |
| `total_stocks` | Layer 1 candidates count |
| `layer1_count` | Same as total_stocks |
| `layer2_count` | Completed Layer 2 count |
| `analyzed_count` | Real-time analyzed count |
| `top_picks` | Final TOP 5 (on `done`) |
| `use_deepseek` | Whether DeepSeek was requested |

---

## Data Persistence

| File | Content |
|------|---------|
| `scans/{YYYY-MM-DD}.json` | Full result with meta + top_picks + candidates |
| `scans/{YYYY-MM-DD}-report.md` | Chinese Markdown report |
| `scans/history.json` | Array of date + picks summaries |
| `scans/scan_progress.json` | Real-time progress |

---

## APIs

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/api/stock/scan/start` | Start background scan |
| `POST` | `/api/stock/scan/stop` | Stop running scan |
| `GET` | `/api/stock/scan/status` | Current scan progress |
| `GET` | `/api/stock/scan/result` | Latest scan result |
| `GET` | `/api/stock/scan/result/<date>` | Result for specific date |
| `GET` | `/api/stock/scan/dates` | Available scan dates |
| `GET` | `/api/stock/scan/history` | Scan history array |
