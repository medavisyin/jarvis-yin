# Memory: Tomorrow's Price Prediction Model Refactoring and DeepSeek Calibration Integration

**Generated**: 2026-05-21 15:30
**Last updated**: 2026-07-01 21:35
**Project**: c:\jarvis
**Focus**: Complete statistical refactoring of next-day price prediction models (XGBoost) and implement DeepSeek qualitative expert auditing and calibration workflow.

---

## Goal & Scope (required)

The next-day price prediction functionality previously suffered from low accuracy, training instability, and feature distortion. The user requested:
1. **Statistical Refactoring**: Fix machine learning issues (feature NaN values, incorrect feature selection correlation, lack of recency weighting).
2. **Noise/Signal Filter**: Implement a signal-to-noise filter to flag predictions that fall within normal market volatility.
3. **DeepSeek Calibration Checkbox**: Add an opt-in checkbox to let a high-reasoning LLM (`deepseek-v4-pro` in thinking mode) audit the numerical machine learning predictions and output calibrated prices, confidence, and tactical trading rules.

---

## Key Decisions (required)

1. **Feature Hygiene & Safe Separation**: Cleanly split features into quantitative (XGBoost) and qualitative (DeepSeek) buckets. All point-in-time single-point fundamental/sentiment features (e.g., `feat_pe`, `sent_fear_greed`) are excluded from XGBoost training to eliminate sparse-data NaN errors. Instead, they are passed directly in the qualitative context to DeepSeek.
2. **Target-Based Feature Selection**: Shifted the correlation ranking in `_select_top_features` from correlating against absolute `close` prices to correlating against actual next-day target returns (`target_close`, `target_high`, `target_low`), training three separate target-specific models.
3. **Recency Weighting (Time decay)**: Applied exponential sample decay weighting during cross-validation and final fitting ($\lambda = 0.002$) to force XGBoost to adapt to non-stationary market regimes.
4. **Post-ML Logical Constraints**: Enforced physical boundary conditions: `high >= close >= low` and `high >= low` on the raw machine learning predictions.
5. **Bayesian DeepSeek Expert Calibration**: 
   - Constructed a high-quality dual prompt (system/user) feeding the machine learning results, 20-day OHLCV sequence, fund flows, fundamentals, and market macro mood into DeepSeek.
   - Instructed DeepSeek to audit ML results, detect momentum/reversal divergence, and output calibrated predictions along with stop-loss/take-profit boundaries under the `[CALIBRATION_JSON]` section.
6. **Defensive Error-Handling & Calibration Status**: 
   - Designed a robust extraction parser that splits on the custom JSON anchor, utilizes brace-matching, and reverse-scans JSON-like blocks.
   - Introduced an explicit `calibration_status` enum (`applied` | `parse_failed` | `api_error` | `skipped_no_key`) to communicate API/formatting errors transparently to the user interface rather than silently failing or showing misleading data.
   - Added price limits (e.g., ±10%, ±20% based on A-share main board/STAR/ChiNext rules) and logical OHLC clamping to DeepSeek's outputs to prevent hallucinated prices.
7. **Interactive UI Redesign**:
   - Added a "🔬 启用 DeepSeek 专家校准与深度推理" checkbox in the training configuration.
   - Rendered a custom teal sub-row for DeepSeek results directly below the XGBoost row, showing the calibrated prices and change percentages.
   - Integrated a "查看推理" (View Reasoning) button linked to an interactive Markdown-rendered modal, presenting DeepSeek's detailed analysis report and opening-half-hour tactical guidelines even if numerical JSON parsing failed.
8. **Off-by-One Prediction Fix (2026-07-01)**: Inference must use the LAST row of `df` (today's features, NaN target) to forecast tomorrow — NOT `X_all.iloc[[-1]]` which is `valid`'s last row = df's second-to-last row. The old code forecast the already-realized bar while `prediction_tracker` scored it against the next bar, collapsing direction accuracy toward random (44.1% < 50%). Fixed by `df[final_cols].iloc[[-1]]` with inf/NaN cleanup + `final_medians` imputation.
9. **Feature-Selection Look-Ahead Removal (2026-07-01)**: Moved target-specific feature ranking from the full `valid` set (which included future test-fold targets) to (a) per-fold training slices inside the walk-forward loop and (b) the final training window only. Eliminates leakage that picked noise-correlated features and inflated overfitting.
10. **Direction Label for Weak Signals (2026-07-01)**: Added `direction_label` to the prediction result — "方向不确定" when `signal_strength == "noise"` (|predicted %| < historical MAE), else 看涨/看跌/震荡. Surfaced in `index.html` prediction table (under 涨跌幅) and `generate_price_report`.
11. **Hide Error-Stock Predictions (2026-07-01)**: `renderFullTrainReport` now iterates `valid = results.filter(r => !r.error)` only — no error rows in the prediction table and the "训练失败" section removed entirely. Stocks returning "特征数据不足" or "No columns to parse from file" are no longer displayed.

---

## Confirmed Assumptions (required)

- Standard A-share stocks follow high/low limits (10% main board, 20% STAR/ChiNext boards, etc.). Price predictor outputs must respect these limits.
- Large reasoning models (DeepSeek-V4-Pro) are optimal for synthesizing multi-source market factors (fund flow, sentiment, fundamentals, technical sequence) and performing sanity audits on purely numerical regressions.

---

## Key Discoveries (required)

- Training on absolute price targets causes significant lookahead and scale distortion in feature correlation selection; percentage return targets resolves this.
- Multi-source financial forecasting benefits greatly from a "quantitative first, qualitative final review" pipeline, using ML to set a statistical baseline and LLM to perform sanity checking and risk defense.
- **Off-by-one in next-day inference (2026-07-01)**: `target_*` is built via `shift(-1)`, so `df`'s last row has NaN target and is dropped by `valid = df.dropna(...)`. Using `X_all.iloc[[-1]]` (= `valid`'s last row = df's second-to-last row) makes the model forecast the already-realized bar, while `prediction_tracker.record_prediction` stores `latest_date = df["date"].iloc[-1]` and `backfill_actuals` scores against the next bar — a one-day mismatch that drives direction accuracy to ~random. Fix: predict from `df[final_cols].iloc[[-1]]` (today's features).
- **Feature selection on full `valid` leaks future test-fold targets (2026-07-01)**: ranking features by correlation with the target over the whole dataset (incl. future) picks noise-correlated columns → overfitting. Must select inside each fold's training slice and on the final training window only.
- **Near-efficient markets cap pure direction accuracy ~50%**: even after the off-by-one fix, expect the tracker's 30-day direction accuracy to move from ~44% toward/above 50%, not to 70%+. The `direction_label="方向不确定"` abstention is the honest UX for noise-band forecasts.

---

## Runtime Evidence (include when relevant)

- 2026-07-01: `python -m py_compile scripts/stock/model_price_predictor.py` → exit 0; ReadLints: no errors.
- 2026-07-01: `python model_price_predictor.py 000100` (run from `scripts/stock/`) → saved `C:\reports\stock\data\000100\price_prediction.json`. Key fields: `latest_date="2026-07-01"` (aligned with next-bar evaluation), `direction_label="方向不确定"` (close +0.12% < MAE 5.68%), `predictions.close=6.13` vs old stale run `6.42` — confirms inference input changed from second-to-last row to last row. (Trailing `UnicodeEncodeError` in `__main__` print is a pre-existing cp1252-terminal issue, occurs AFTER save, unrelated.)
- `C:\reports\stock\data\000100\predictions_log.json` pre-fix sample showed `prediction_date=2026-07-01, current_close=6.12, predicted_close=6.42 (+4.9%)` — the +4.9% was the stale 06-30→07-01 forecast scored against 07-01→07-02.

---

## Current State (required)

- **Completed (2026-05-21)**: ML statistical refactoring, DeepSeek calibration pipeline, backend progress JSON, interactive UI checkbox + sub-row + reasoning modal.
- **Completed (2026-07-01)**: Off-by-one inference fix, per-fold/final-window feature selection (no look-ahead), `direction_label` field + UI/report surfacing, frontend hiding of error-stock predictions and "训练失败" section.
- **Pending verification**: Tracker 30-day direction accuracy needs to re-accumulate post-fix over the next ~30 trading days to confirm the lift from ~44% toward/above 50%.

---

## Next Steps (required)

1. [ ] After ~30 trading days of post-fix predictions, compare `prediction_tracker.get_aggregate_stats(...).last_30.direction_accuracy` against the pre-fix 44.1% baseline.
2. [ ] Add automated unit tests under `tests/` for: off-by-one (latest_date vs prediction input row), per-fold feature-selection no-leak, `direction_label` noise threshold, and JSON extraction edge cases.
3. [ ] Consider exposing DeepSeek cost/token metrics to the UI during daily training.
4. [ ] Optional: ensemble multi-seed XGBoost + direction abstention threshold if single-model accuracy plateaus below 50% post-fix.

---

## References (required)

- `scripts/stock/model_price_predictor.py` -- Price predictor training, inference, and LLM calibration.
- `scripts/stock/prediction_tracker.py` -- Records predictions, backfills actuals, computes per-symbol/aggregate direction accuracy (source of the 44.1% metric).
- `scripts/rag/routes/stock.py` -- Stock routing and daily training queue (`api_stock_train_daily`).
- `scripts/rag/templates/index.html` -- Web UI: `renderFullTrainReport` predictions table + aggregate stats + DeepSeek sub-row.
- `docs/memory/memory-20260521-tomorrow-price-prediction-refactor.md` -- This memory file.
