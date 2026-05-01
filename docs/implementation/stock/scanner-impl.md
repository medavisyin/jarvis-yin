# Market Scanner Implementation

## Overview

The scanner performs a multi-layer full-market A-share scan: fetch all stocks, filter by quantitative criteria, **rank Layer 1 candidates** (primary: cross-sectional XGBoost; fallback: per-stock technicals/fundamentals/sentiment/fund-flow rules), then use LLM (DeepSeek or local) to judge buyability. Produces TOP 5 AI recommendations with buy-price ranges, strategies, and comprehensive multi-dimensional reports.

---

## Architecture

```
start_scan(use_deepseek=False)  →  _run_scan()  [background thread]
  └─ _run_scan_inner()
       ├── hot_sectors.get_hot_stock_set()
       ├── _layer1_quick_filter(hot_stocks)    → (candidates[], market_total)
       ├── _execute_layer2_and_3(progress, candidates)
       │     ├── Layer 2 (primary): _layer2_xgb_cross_sectional(candidates)
       │     │     └── model_cross_sectional.cross_sectional_rank()
       │     │          └─ on failure / empty → _layer2_rule_scoring_all()
       │     │               └── batches: _layer2_rule_scoring(batch) × N
       │     ├── Layer 3: _layer3_llm_rank(all_l2)   [sorts by score_l2]
       │     │     ├── if DeepSeek: TOP 10 → _layer3_deepseek_judge()
       │     │     └── remaining → _layer3_local_judge()
       │     ├── Phase 4: _run_comprehensive_for_picks()
       │     ├── Phase 5: _run_deepseek_for_picks() (supplementary, if needed)
       │     └── _save_results + _save_history_entry
       └── _save_progress at each stage
```

**Layer 2 path:** Cross-sectional XGBoost ranking runs **once per scan** on the full Layer 1 candidate set. If import fails, training fails, or the model returns no rows, the scanner sets `progress["layer2_mode"]` to `rule_fallback` and replays the original **per-batch rule scoring** (`_layer2_rule_scoring_all` → `_layer2_rule_scoring` in chunks of `LAYER2_BATCH`).

---

## Layer 1: Quick Filter (`_layer1_quick_filter`)

### Data Source

```
Primary: ak.stock_zh_a_spot_em() — full A-share market snapshot
Fallback: _fetch_market_eastmoney() — Sina paginated API
```

### Filter Criteria (all must pass)

| Criterion | Rule |
|-----------|------|
| Not ST | `"ST" not in str(名称)` |
| 涨跌幅 | -7% to +8% |
| 换手率 | ≥ 0.5% |
| 成交额 | ≥ 30,000,000 (3000万) |
| 市盈率(动态) | > 0 and < 80 |
| 不追涨停 | 涨跌幅 < 9.5% |

### Scoring (2026-04 Science Rework)

Previous formula was biased toward low-PE stocks and intraday gainers (chase-high risk). New approach uses bell-curve scoring:

**PE Score (30% weight)** — Sweet-spot model, not linear:
| PE Range | Score | Rationale |
|----------|-------|-----------|
| 8~15 | 90 | Growth at reasonable price |
| 15~25 | 80 | Fair value |
| 25~40 | 55 | Moderate premium |
| 40~60 | 30 | Expensive |
| 60+ | 10 | Overvalued |
| <8 | 40 | Value trap risk (banks, utilities) |

**Change Score (30% weight)** — Pullback buying preferred:
| Change | Score | Rationale |
|--------|-------|-----------|
| >7% | 10 | Dangerous chase (T+1 lock-in) |
| 5~7% | 25 | High chase risk |
| 2~5% | 45 | Moderate momentum |
| -1~2% | 70 | Sweet spot: mild movement |
| -4~-1% | 80 | Pullback = opportunity |
| <-4% | 50 | Catching falling knife risk |

**Turnover Score (20% weight)** — Moderate preferred:
| Turnover | Score | Rationale |
|----------|-------|-----------|
| 1~5% | 80 | Healthy liquidity |
| 5~10% | 60 | Active but watchful |
| >10% | 30 | Speculative frenzy |
| <1% | 40 | Low liquidity risk |

**Liquidity (20%)**: `min(成交额/1亿, 20) × 0.5`

Hot sector bonus: +3 points.

Sorted descending, capped at `LAYER2_CANDIDATE_CAP` (100).

---

## Layer 2: Cross-Sectional Ranking + Rule Fallback

Layer 2 selects and enriches candidates passed to Layer 3. The **primary** path ranks the entire Layer 1 set with a one-shot XGBoost `rank:pairwise` model (`model_cross_sectional.py`). The **fallback** path preserves the earlier rule-based pipeline (technicals, fundamentals, sentiment, fund flow) in batches.

### `_layer2_xgb_cross_sectional(candidates, progress)`

- Imports `cross_sectional_rank` from `model_cross_sectional` and runs it on the Layer 1 list (with `_stop_event` for cooperative cancellation).
- On success, sets `progress["layer2_mode"] = "xgb_cross_sectional"` and returns the ranked subset produced after **industry neutralization** (see ML pipeline doc). Each item includes ranking fields (below).
- **Fallback triggers:** `ImportError` for the module; any exception from `cross_sectional_rank`; or an **empty** result (e.g. insufficient valid histories, training failure inside the model). In those cases, logs and sets `progress["layer2_mode"] = "rule_fallback"`, then delegates to `_layer2_rule_scoring_all`.

### `_layer2_rule_scoring_all` / `_layer2_rule_scoring(batch, progress)`

- **`_layer2_rule_scoring_all`:** Iterates candidates in slices of `LAYER2_BATCH` (20), calling `_layer2_rule_scoring` each time until all are scored or the scan is stopped.
- **`_layer2_rule_scoring`:** Original per-symbol Layer 2: OHLCV, technical signals, fundamentals, weighted news sentiment, and smart-money fund-flow scoring; combines with Layer 1 score and valuation bonus into **`score_l2`** (rule-based composite, not XGBoost).

### Layer 2 output fields (XGBoost path)

When the cross-sectional path succeeds, each candidate row includes:

| Field | Meaning |
|-------|---------|
| `score_l2` | XGBoost ranker score (`xgb_score`, rounded) — Layer 3 sorts by this |
| `xgb_rank` | 1-based rank after industry neutralization (among returned rows) |
| `industry` | Industry label (e.g. Shenwan board name; fallback `"其他"`) |
| `xgb_alpha` | Same-day alpha used in labeling: stock `ret_1d` − industry mean `ret_1d` |
| `model_ndcg` | Validation **NDCG@10** from the training run for this scan |

The rule fallback path does **not** set `xgb_rank`, `xgb_alpha`, or `model_ndcg`; it still sets **`score_l2`** as the weighted rule total and populates `tech_score`, `fund_score`, `ff_score`, `signals`, etc., for LLM prompts.

### Rule-based scoring detail (fallback path)

Processes candidates in batches of `LAYER2_BATCH` (20).

Per stock:
1. `fetch_daily_ohlcv(symbol)` — fetch latest OHLCV
2. `technical_analysis.compute_indicators()` + `evaluate_signals()` — full TA
3. `fundamental_analysis.fetch_fundamentals()` + `score_fundamentals()` — financial health
4. Weighted sentiment analysis with impact-level keyword matching
5. `china_market_data.stock_fund_flow_signals()` — fund flow + smart money phase

### Sentiment Analysis (Improved)

Uses weighted keyword matching instead of simple count:

| Category | Keywords | Weight |
|----------|----------|--------|
| High Positive | 超预期, 中标, 签约, 突破新高, 大幅增长, 扭亏为盈 | +3 |
| Mid Positive | 增长, 利好, 创新, 盈利, 分红, 回购 | +2 |
| Low Positive | 涨, 突破, 上涨 | +1 |
| High Negative | 退市, ST, 暴雷, 造假, 立案, 违规 | -4 |
| Mid Negative | 亏损, 减持, 处罚, 下调, 风险 | -2.5 |
| Low Negative | 跌, 下降, 利空 | -1 |

Negative news is weighted more heavily because bad news has asymmetric impact on stock prices.

### Score Weights

```
ff_score     × 0.30    ← fund flow (布局期 bonus: 80+, 出货期 penalty: 25)
+ fund_score × 0.25    ← fundamental quality
+ tech_score × 0.20    ← technical signals
+ sentiment  × 0.10    ← weighted news sentiment
+ L1_score   × 0.10    ← initial screening score
+ valuation  × 0.05    ← PE-based valuation bonus
+ hot_bonus  (max 5)
```

Smart money `ff_score` mapping:
| Phase | ff_score | Logic |
|-------|----------|-------|
| 布局期 | 80 + min(accum_score/5, 15) | Best: funds in, price flat |
| 吸筹 + net inflow | 70 + bonus | Good: accumulation signal |
| 拉升期 | 55 | Already pumping, late entry |
| 出货期 | 25 | Distribution, avoid |
| Net outflow | max(20, 50 + adjusted) | Funds leaving |

---

## Layer 3: LLM Buy Judgment (`_layer3_llm_rank`)

### Strategy (2026-04 Science Rework)

Previous approach: local small LLM (qwen3.5:4b) judged all 30 stocks. Problem: frequent JSON parse failures, low-quality reasoning.

**New approach:**
- **With DeepSeek enabled**: TOP 10 by L2 score → `_layer3_deepseek_judge()` (high quality), remaining 11~30 → `_layer3_local_judge()` (cost-effective)
- **Without DeepSeek**: All 30 → `_layer3_local_judge()` (fallback)
- **Automatic fallback**: If DeepSeek fails for any stock, gracefully falls back to local LLM

### DeepSeek Judgment (`_layer3_deepseek_judge`)

**Model**: `deepseek-v4-pro` via `config.call_deepseek()` (OpenAI SDK with `reasoning_effort="medium"`, thinking enabled)

**Rich Prompt** (`_build_deepseek_scoring_prompt`):
- Full market snapshot (price, change, turnover, PE, market cap, amount)
- All Layer 2 dimension scores
- Smart money phase + accumulation score + fund-price divergence
- Fundamental dimension breakdown
- Technical signals + RSI

**System Prompt** mandates:
1. Smart money signal analysis (fund-price divergence)
2. Chase-high punishment (A-share T+1 lock-in risk)
3. Valuation safety margin
4. Technical confirmation (RSI, support levels)
5. Fundamental floor
6. Output: strict JSON with `verdict`, `score`, `reason`, `risk`, `buy_low`, `buy_high`, `strategy`

**Cost**: ~10 calls × ~1200 max_tokens = ~12,000 tokens per scan

### Local LLM Judgment (`_layer3_local_judge`)

Uses `MODEL_USAGE["prediction_reasoning"]` (e.g., `qwen3.5:4b`) via Ollama API.

Same JSON output format, simpler prompt. `think: false` to prevent reasoning token waste.

### Response Parsing (`_parse_llm_score`)

Robust parser handling:
1. Strip `<think>...</think>` blocks
2. Strip markdown code fences
3. Fix single quotes → double quotes
4. Remove trailing commas
5. Extract outermost `{...}` JSON
6. Parse `strategy` field (new)
7. Fallback: use `score_l2` with "LLM输出解析失败" message

### Result Filtering

Only stocks with `verdict == "买入"` AND `final_score >= MIN_BUYABILITY_SCORE (60)` pass.
Each stock is tagged with `judged_by: "deepseek" | "local" | "fallback"`.

---

## Constants

| Constant | Value | Purpose |
|----------|-------|---------|
| `LAYER2_CANDIDATE_CAP` | 100 | Max Layer 1 → Layer 2 |
| `LAYER3_CAP` | 30 | Max Layer 2 → Layer 3 |
| `DEEPSEEK_LAYER3_CAP` | 10 | Top N for DeepSeek judgment |
| `TOP_N` | 5 | Final recommendation count |
| `LAYER2_BATCH` | 20 | Layer 2 batch size |
| `MIN_BUYABILITY_SCORE` | 60 | Minimum score to pass Layer 3 |

---

## Thread Safety

- Background `threading.Thread` (`_scan_thread`)
- `_scan_lock` (Lock) prevents concurrent scans
- `_stop_event` (Event) for graceful cancellation
- `sys.modules["config"]` explicitly set via `importlib` in thread
- **Stale module cleanup:** `_run_scan_inner()` removes 12 stock modules from `sys.modules` at thread start to avoid `KeyError` from partially-removed modules

---

## Phase 4: Comprehensive Analysis

After Layer 3 selects top picks, Phase 4 runs `_run_comprehensive_for_picks()`:

| Dimension | Source | "Supports buy" if... |
|-----------|--------|---------------------|
| **Technical** | `evaluate_signals()` | overall 看涨/偏多 and RSI < 75 |
| **ML Direction** | `model_xgboost.train_and_predict()` | XGBoost predicts 涨, confidence > 50% |
| **Price Prediction** | `model_price_predictor.train_price_prediction()` | Predicted close change > +0.5% |
| **Fund Flow** | `detect_smart_money_accumulation()` | Phase == "布局期" or (accumulation + net inflow) |
| **Scanner** | Layer 3 verdict | verdict == "买入" |

**Star Rating:** `support_count / total_dims * 5` (rounded)

| Stars | Conclusion |
|-------|-----------|
| 4-5 | 多维共振,建议建仓 |
| 3 | 多数支持,可考虑小仓 |
| 2 | 信号分歧,建议观望 |
| 0-1 | 支持不足,暂不建议 |

## Phase 5: DeepSeek Supplementary Reports (Conditional)

When DeepSeek is enabled, Phase 5 generates detailed reports **only for picks that were judged by local LLM** (not already handled by DeepSeek in Layer 3):

- If all TOP 5 were judged by DeepSeek → Phase 5 is skipped entirely
- If some were judged locally (ranked 11~30 in L2 but passed Layer 3) → Phase 5 generates reports for those

This avoids redundant DeepSeek calls.

---

## Progress Tracking

`{STOCK_REPORTS_ROOT}/scans/scan_progress.json`:

| Field | Description |
|-------|-------------|
| `status` | `layer1` / `layer2_in_progress` / `layer3` / `comprehensive` / `deepseek` / `done` / `error` / `stopped` |
| `layer3_mode` | `deepseek+local` (when DeepSeek enabled) |
| `layer2_mode` | `xgb_cross_sectional` (primary) or `rule_fallback` (after XGB/import/empty failure) |
| `market_total` | Raw full-market stock count |
| `total_stocks` | Layer 1 candidates count |
| `layer1_count` | Same as total_stocks |
| `layer2_count` | Completed Layer 2 count |
| `analyzed_count` | Real-time analyzed count |
| `top_picks` | Final TOP 5 (on `done`), each tagged with `judged_by` |
| `use_deepseek` | Whether DeepSeek was requested |

---

## Data Persistence

| File | Content |
|------|---------|
| `scans/{YYYY-MM-DD}.json` | Full result with meta + top_picks + candidates |
| `scans/{YYYY-MM-DD}-report.md` | Chinese Markdown report (includes judged_by tag) |
| `scans/history.json` | Array of date + picks summaries |
| `scans/scan_progress.json` | Real-time progress |

---

## APIs

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/api/stock/scan/start` | Start background scan (body: `{use_deepseek: bool}`) |
| `POST` | `/api/stock/scan/stop` | Stop running scan |
| `GET` | `/api/stock/scan/status` | Current scan progress |
| `GET` | `/api/stock/scan/result` | Latest scan result |
| `GET` | `/api/stock/scan/result/<date>` | Result for specific date |
| `GET` | `/api/stock/scan/dates` | Available scan dates |
| `GET` | `/api/stock/scan/history` | Scan history array |
