# ML Pipeline Implementation

## Overview

The ML pipeline consists of feature engineering, two XGBoost model types (classification + regression), and a prediction tracking/verification system.

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
| `_TRAIN_WINDOW` | 250 | Training window (trading days) |
| `_TEST_WINDOW` | 5 | Test window per round |
| `_N_ROUNDS` | 10 | Walk-forward rounds (increased from 5) |
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
2. **Increased walk-forward rounds** (10 vs 5) — 50 test days vs 25 for more reliable OOS estimate
3. **Stronger regularization** — deeper L1/L2, lower subsample ratios, shallower trees
4. **Final model uses best iteration** — if early stopping found optimal at N trees, final refit uses N

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

### Constants

| Constant | Value | Purpose |
|----------|-------|---------|
| `_TRAIN_WINDOW` | 250 | Training window |
| `_TEST_WINDOW` | 5 | Test window per round |
| `_N_ROUNDS` | 10 | Walk-forward rounds |
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

Same anti-overfitting design as classifier:

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
- **MAE** — Mean Absolute Error
- **MAPE** — Mean Absolute Percentage Error
- **Direction accuracy** (close only) — predicted vs actual direction

### Final Model

The production model removes `early_stopping_rounds` from params (no eval_set) and uses `best_iteration + 1` from the last WF round as `n_estimators`.

### Persistence

| File | Content |
|------|---------|
| `data/{symbol}/price_prediction.json` | Predictions + WF stats |
| `models/{symbol}/price_{close,high,low}_model.json` | Per-target XGBoost model |
| `data/{symbol}/price-prediction-report.md` | Chinese Markdown report |

---

## `prediction_tracker.py` — Verification System

### Purpose

Log predictions, backfill actual prices, calculate accuracy, grade model health.

### Key Functions

| Function | Description |
|----------|-------------|
| `record_prediction(symbol, result)` | Append prediction to log |
| `backfill_actuals(symbol)` | Fill actual prices from `daily.csv` |
| `get_accuracy_stats(symbol)` | Aggregate accuracy metrics + health |
| `get_latest_verification(symbol)` | Most recent entry with actuals filled |

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
