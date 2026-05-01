# ML Pipeline Implementation

## Overview

The ML pipeline consists of feature engineering, per-symbol XGBoost models (classification + regression), a **cross-sectional ranking** model used by the market scanner at Layer 2, and a prediction tracking/verification system.

---

## `features.py` — Feature Engineering

### Entry Point

`build_features(symbol, forward_days=5, threshold=2.0)` → `DataFrame` with features + targets.

### Feature Categories

| Category | Examples | Count (approx.) |
|----------|----------|-----------------|
| Returns | `ret_1d` … `ret_20d`, `gap`, `pct_change` | ~8 |
| Momentum | `rsi_delta`, `rsi_5d_delta`, `macd_hist_delta`, `macd_hist_sign_change`, `kdj_j_delta` | ~6 |
| Volatility | `atr_pct`, `daily_range_pct`, `range_5d_avg`, `bb_width_delta`, `volatility_20d` | ~6 |
| MA Distance | `dist_ma5` … `dist_ma60`, `ma5_ma20_spread`, `ma10_ma60_spread` | ~6 |
| Volume | `vol_change_1d`, `vol_change_5d`, `vol_ratio_20` | ~3 |
| Patterns | `body_ratio`, shadow ratios, `is_bullish`, `bullish_streak` | ~5 |
| Fundamental | `feat_pe`, `feat_pb`, `feat_roe`, `feat_debt_ratio`, `feat_profit_yoy` | 5 |
| Calendar | `dayofweek`, `month`, `is_month_end` | 3 |

### Target Variables

- `target_ret`: forward N-day return: `close.shift(-N) / close * 100 - 100`
- `target`: 3-class label: `1` (涨, > threshold), `-1` (跌, < -threshold), `0` (平)

### Fundamental Features — Look-ahead Bias Fix

**Critical design decision:** Fundamental features (`feat_pe`, `feat_pb`, `feat_roe`, `feat_debt_ratio`, `feat_profit_yoy`) are sourced from `fundamentals.json` which contains **current** (point-in-time) values, not historical as-of-date values.

To prevent look-ahead bias in walk-forward backtesting, these values are **only applied to the last row** of the DataFrame. All other rows get `NaN`. This means:
- During walk-forward training folds, fundamental features are always NaN → model learns from technical features only
- For the final prediction (last row), fundamentals are available as additional signal

### Feature Selection

`_get_feature_columns(df)`:
- Numeric columns only
- ≥ 50% non-null values
- Excludes: date, OHLCV, targets, raw indicator prefixes (MACD/Bollinger/STOCH)
- Result sorted alphabetically

### Data Requirements

Returns `None` if fewer than **120** rows after OHLCV load.

---

## `model_xgboost.py` — Direction Classifier

### Purpose

Walk-forward **XGBoost 3-class classifier** predicting 5-day direction (涨/平/跌).

### Constants

| Constant | Value | Purpose |
|----------|-------|---------|
| `_TRAIN_WINDOW` | **500** | Training window (~2 years of trading days) |
| `_TEST_WINDOW` | 5 | Test window per round |
| `_N_ROUNDS` | **15** | Walk-forward rounds (75 test days total) |
| `_MIN_DATA_ROWS` | 300 | Minimum data requirement |
| `_EARLY_STOPPING_ROUNDS` | 15 | Stop if no improvement |

### XGBoost Hyperparameters

| Parameter | Value | Rationale |
|-----------|-------|-----------|
| `objective` | `multi:softprob` | 3-class probabilities |
| `max_depth` | 3 | Shallow trees reduce overfitting on noisy returns |
| `learning_rate` | 0.05 | Low rate + more trees + early stopping |
| `n_estimators` | 200 | Capacity budget (early stopping prevents full use) |
| `min_child_weight` | 8 | Smoother splits, fewer noise fits |
| `subsample` | 0.7 | Row subsampling for regularization |
| `colsample_bytree` | 0.6 | Feature subsampling for regularization |
| `reg_alpha` | 0.5 | L1 regularization (increased from 0.1) |
| `reg_lambda` | 2.0 | L2 regularization (increased from 1.0) |
| `early_stopping_rounds` | 15 | Constructor param (XGBoost ≥2.0 API) |

### Anti-Overfitting Measures

1. **Early stopping** (15 rounds) — prevents training all 200 trees when validation loss plateaus
2. **Extended walk-forward** (15 rounds × 5 days = 75 test days) — more reliable OOS estimate
3. **Larger training window** (500 days) — captures more market regimes
4. **Stronger regularization** — deeper L1/L2, lower subsample ratios, shallower trees
5. **Final model uses best iteration** — if early stopping found optimal at N trees, final refit uses N

### Walk-Forward Procedure

```
for round in range(n_rounds):
    train: [n - offset - train_size : n - offset - test_window]
    test:  [n - offset - test_window : n - offset]

    fit with eval_set for early stopping
    predict → accuracy, confusion matrix
```

### Label Encoding

`LabelEncoder` fit on `[-1, 0, 1]` → predictions map back via `_LABEL_MAP`: `{-1: "跌", 0: "平", 1: "涨"}`.

### Persistence

| File | Content |
|------|---------|
| `models/{symbol}/model.json` | XGBoost binary model |
| `models/{symbol}/prediction.json` | Full result dict |
| `models/{symbol}/features.json` | Feature column list |
| `data/{symbol}/xgb_prediction.json` | Copy for LLM downstream |
| `data/{symbol}/xgb-report.md` | Chinese Markdown report |

---

## `model_price_predictor.py` — Price Regressor

### Purpose

Three independent **XGBoost regressors** for next-day **close**, **high**, and **low** prices.

### Prediction Target: Percentage Returns (not absolute prices)

The regressor predicts **next-day percentage return** relative to today's close, not the absolute price. This is critical because:
- Absolute price prediction suffers from distribution shift: when a stock rallies from ¥200 to ¥400, a model trained on historical ¥200-range data cannot extrapolate to ¥400
- Percentage returns are scale-invariant and stationary, making the model work across any price level
- The raw model output (percentage) is converted back to price at prediction time: `predicted_price = current_close * (1 + predicted_pct / 100)`

### Constants

| Constant | Value | Purpose |
|----------|-------|---------|
| `_TRAIN_WINDOW` | **500** | Training window (~2 years) |
| `_TEST_WINDOW` | 5 | Test window per round |
| `_N_ROUNDS` | **15** | Walk-forward rounds (75 test days total) |
| `_MAX_FEATURES` | 40 | Feature cap to prevent p >> n |
| `_EARLY_STOPPING_ROUNDS` | 15 | Early stopping patience |

### Extended Features

Beyond `features.py` base features, adds:

**Price sequence features (`_add_price_sequence_features`):**
- `price_seq_close_lag{1,2,3,5}` — normalized lag returns
- `price_seq_hl_ratio` — (high - low) / close
- `price_seq_hl_ratio_ma5` — 5-day moving average of H/L ratio
- `price_seq_close_ma{5,10}_ratio` — price vs moving average ratio
- `price_seq_momentum_{3d,5d}` — short-term momentum
- `price_seq_vwap_proxy` — VWAP approximation

**Market sentiment features (`_add_sentiment_features`):**
- `sent_fear_greed` — normalized Fear & Greed index (0–1)
- `sent_vix` — raw VIX value

Sentiment features are applied to the **last row only** to avoid look-ahead bias (same logic as fundamental features).

### Feature Selection (`_select_top_features`)

When feature count exceeds `_MAX_FEATURES` (40):
1. Compute variance for each feature
2. Compute absolute correlation with close price
3. Rank by combined score (variance rank + correlation rank)
4. Keep top 40

### XGBoost Hyperparameters

Same anti-overfitting design as classifier. The `objective` **reg:squarederror** minimizes squared error on **percentage-return** targets (next-day move vs today's close as %), not absolute price levels.

| Parameter | Value |
|-----------|-------|
| `objective` | `reg:squarederror` |
| `max_depth` | 4 |
| `learning_rate` | 0.05 |
| `n_estimators` | 300 |
| `min_child_weight` | 8 |
| `subsample` | 0.7 |
| `colsample_bytree` | 0.6 |
| `reg_alpha` | 0.5 |
| `reg_lambda` | 2.0 |
| `early_stopping_rounds` | 15 |

### Walk-Forward Metrics

Per target (close/high/low):
- **MAE** — Mean Absolute Error (in percentage points, since target is % return)
- **MAPE** — Mean Absolute Percentage Error
- **Direction accuracy** (close only) — predicted vs actual direction

### A-Stock Price Limit Clamping

All predictions are clamped to the legal daily price limits for Chinese A-stocks:

| Board | Symbol Prefix | Daily Limit |
|-------|---------------|-------------|
| 主板 (Main) | 00xxxx, 60xxxx | ±10% |
| 创业板 (ChiNext) | 300xxx | ±20% |
| 科创板 (STAR) | 688xxx | ±20% |
| 北交所 (BSE) | 8xxxxx, 4xxxxx | ±30% |

Functions: `_get_price_limit(symbol)` returns the limit ratio; `_clamp_prediction()` enforces the range.

Additionally, if predicted high < predicted low, they are automatically swapped to maintain logical consistency.

### Confidence / Uncertainty Output

`_compute_confidence(wf_results, change_pct)` assesses prediction reliability:

| Field | Values | Meaning |
|-------|--------|---------|
| `level` | `medium`, `low-medium`, `low`, `very_low` | Based on MAE and direction accuracy from walk-forward |
| `signal_strength` | `moderate`, `weak`, `noise` | Whether predicted change exceeds the model's own error margin |
| `note` | text | Human-readable explanation |

**Key logic:** If the predicted percentage change is smaller than the walk-forward MAE, the signal is classified as `noise` — meaning the model's uncertainty is larger than what it's predicting. This prevents users from acting on predictions that are statistically indistinguishable from zero.

### Final Model

The production model removes `early_stopping_rounds` from params (no eval_set) and uses `best_iteration + 1` from the last WF round as `n_estimators`.

### Persistence

| File | Content |
|------|---------|
| `data/{symbol}/price_prediction.json` | Predictions + WF stats |
| `models/{symbol}/price_{close,high,low}_model.json` | Per-target XGBoost model |
| `data/{symbol}/price-prediction-report.md` | Chinese Markdown report |

---

## `model_cross_sectional.py` — Cross-Sectional Ranking Model

### Purpose

Learns **relative strength within a universe** (Layer 1 scan candidates ~100 names), not a single symbol’s forward return. It replaces the scanner’s primary Layer 2 ranking with **XGBoost `rank:pairwise`** trained **fresh each scan** on pooled history, then applies **industry neutralization** (top N names per industry by model score). If training or data checks fail, `scanner.py` falls back to rule-based Layer 2 (`_layer2_rule_scoring`).

This differs from **`model_xgboost.py`**, **`model_timing.py`**, and **`model_price_predictor.py`**: those train and predict **one symbol at a time** using `features.py` (or extended features) and persist models under `models/{symbol}/`. The cross-sectional ranker is **multi-symbol by design**, builds features **inside this module** (no `features.py` dependency), and does **not** persist a model file between scans.

### Entry Point

`cross_sectional_rank(candidates, lookback_days=60, top_n_per_industry=3, stop_event=None)` → sorted list of dicts (subset of input candidates after neutralization), each augmented with `score_l2`, `xgb_rank`, `industry`, `xgb_alpha`, `model_ndcg`. Returns **[]** on failure so the caller can fall back.

### Pipeline (internal flow)

| Step | Function | Role |
|------|----------|------|
| Industry labels | `_fetch_industry_map(symbols)` | Shenwan-style industry per symbol (AKShare + cache under `STOCK_CACHE_DIR`); fallback label `"其他"` |
| History | `_fetch_batch_history(symbols, lookback_days, stop_event)` | Daily OHLCV per symbol (`daily.csv` if fresh else `ak.stock_zh_a_hist`), minimum `_MIN_HISTORY` (30) rows |
| Features | `_build_cross_sectional_features(all_hist, industry_map)` | Per-day panels: time-series features via `_compute_single_stock_features`, then cross-section ranks `_add_cross_sectional_features` (`cs_ret_rank`, `cs_vol_rank`, `cs_turnover_rank`), targets via `_add_alpha_target` |
| Train | `_train_ranker(train_df, feature_cols)` | Time-based split: `_TRAIN_DAYS` + `_VAL_DAYS` recent calendar days in the panel; **NDCG@10** on validation; `xgb.train(..., objective=rank:pairwise, eval_metric=ndcg@10)` |
| Predict | `_predict_and_neutralize(model, today_df, feature_cols, industry_map, top_n_per_industry)` | Predict scores for **today’s** cross-section; within each industry, keep **top N** by score; sort globally by score |

### Feature engineering (self-contained)

Feature columns are listed in `_FEATURE_COLS`: multi-horizon returns, RSI/MACD/ATR/volatility, MA distances and spreads, volume ratios, candle shapes, turnover, plus **cross-sectional percentile ranks** for return, volume, and turnover on each day. All computation lives in `model_cross_sectional.py` (no shared `build_features()`).

### Alpha target and relevance grading

For each calendar day and each stock in that day’s panel:

- **Alpha** = stock **1-day return** minus **industry mean 1-day return** (industry from `industry_map`).
- **Relevance** (XGBoost label, grades **0–4**): quantiles of alpha within that day’s cross-section — bottom 10% → 0, 10–25% → 1, 25–50% → 2, 50–75% → 3, top 25% (≥75th pct) → 4.

Training stacks **one row per (symbol, date)** for all historical dates except the last (the last date is held out as **today’s** prediction slice). **Query groups** (`qid`) are **by date** so the model learns ordering within each past cross-section. **Relevance** on each row uses that date’s **alpha** (same-day `ret_1d` minus industry mean), binned into **five grades** (0–4) via within-day quantiles.

### Industry neutralization

After prediction, `_predict_and_neutralize` groups **today’s** rows by `industry`, takes **`top_n_per_industry`** (default 3) by `xgb_score` per group, concatenates, then sorts by score. This limits concentration in a single sector.

### Constants (representative)

| Name | Default | Purpose |
|------|---------|---------|
| `_LOOKBACK_DAYS` | 60 | History window for fetch/features |
| `_TRAIN_DAYS` / `_VAL_DAYS` | 40 / 20 | Rough train/val day counts for time split |
| `_MIN_HISTORY` | 30 | Minimum rows to include a symbol |
| `_TOP_PER_INDUSTRY` | 3 | Cap per industry after ranking |

### Persistence

No per-scan model JSON: the booster exists only in memory for that run. Industry map may be cached in `STOCK_CACHE_DIR` (e.g. `.industry_map.json`).

---

## `prediction_tracker.py` — Verification System

### Purpose

Log predictions, backfill actual prices, calculate accuracy, grade model health.

### Key Functions

| Function | Description |
|----------|-------------|
| `record_prediction(symbol, result)` | Append prediction to log |
| `backfill_actuals(symbol)` | Fill actual prices from `daily.csv` |
| `get_accuracy_stats(symbol)` | Per-symbol accuracy metrics + health |
| `get_latest_verification(symbol)` | Most recent entry with actuals filled |
| `get_aggregate_stats(symbols)` | Cross-symbol aggregate stats (direction accuracy, MAPE, MAE, per-window breakdowns, per-symbol detail) |

### Backfill Process

For each log entry missing `actual_close`:
1. Load `daily.csv` via `load_ohlcv`
2. Find row matching `target_date`
3. Fill: `actual_close`, `actual_high`, `actual_low`
4. Compute: `error_close`, `error_pct_close`, `error_high`, `error_pct_high`, `error_low`, `error_pct_low`
5. Compute: `direction_correct` (predicted vs actual price direction)

### Model Health Grading (`_calc_model_health`)

Based on **last 5** filled entries:

| Grade | MAPE | Direction Acc | Color |
|-------|------|---------------|-------|
| A | ≤ 1.5% | ≥ 70% | `#10b981` (green) |
| B | ≤ 3.0% | ≥ 50% | `#3b82f6` (blue) |
| C | ≤ 5.0% | ≥ 40% | `#fbbf24` (yellow) |
| D | > 5.0% | < 40% | `#ef4444` (red) |
| N/A | — | — | — (< 5 samples) |

### Trend Detection

When ≥ 10 entries:
- Compare recent-5 MAPE vs older-5 MAPE
- `improving`: recent < 80% of older
- `degrading`: recent > 120% of older
- `stable`: otherwise

### Storage

`data/{symbol}/predictions_log.json` — array of prediction entries with backfilled actuals.

### Aggregate Statistics (`get_aggregate_stats`)

Computes watchlist-scoped statistics across all symbols. Called once after all stocks are trained; result is included in `train_progress.json` as `aggregate_stats`.

**Output fields:**

| Field | Description |
|-------|-------------|
| `total_predictions` | Total prediction entries across all symbols |
| `total_verified` | Entries with actual data filled |
| `total_pending` | Entries still awaiting actual prices |
| `direction_correct` / `direction_total` | Correct direction predictions vs total evaluated |
| `direction_accuracy` | Overall direction hit rate (0–1) |
| `avg_mape` | Mean Absolute Percentage Error across all verified entries |
| `avg_mae` | Mean Absolute Error (price units) |
| `last_7` / `last_30` | Per-window breakdown (count, avg_mape, direction stats) |
| `per_symbol` | Sorted list of per-symbol stats (verified count, direction accuracy, avg MAPE) |
| `symbol_count` | Number of symbols with verified data |

**Scope:** Only symbols passed in (current watchlist). Removed stocks are excluded automatically.

---

## XGBoost API Compatibility Note

**XGBoost ≥ 2.0:** `early_stopping_rounds` is a **constructor parameter**, not a `.fit()` argument.

```python
# Correct (XGBoost 2.0+):
model = xgb.XGBRegressor(early_stopping_rounds=15, ...)
model.fit(X, y, eval_set=[(X_val, y_val)], verbose=False)

# Wrong (will raise TypeError):
model.fit(X, y, early_stopping_rounds=15)
```

The final production model (trained on all data, no eval_set) must **remove** `early_stopping_rounds` from params and use `best_iteration` from the last WF round.
