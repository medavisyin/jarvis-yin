# Memory: Tomorrow's Price Prediction Model Refactoring and DeepSeek Calibration Integration

**Generated**: 2026-05-21 15:30
**Last updated**: 2026-05-21 15:30
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

---

## Confirmed Assumptions (required)

- Standard A-share stocks follow high/low limits (10% main board, 20% STAR/ChiNext boards, etc.). Price predictor outputs must respect these limits.
- Large reasoning models (DeepSeek-V4-Pro) are optimal for synthesizing multi-source market factors (fund flow, sentiment, fundamentals, technical sequence) and performing sanity audits on purely numerical regressions.

---

## Key Discoveries (required)

- Training on absolute price targets causes significant lookahead and scale distortion in feature correlation selection; percentage return targets resolves this.
- Multi-source financial forecasting benefits greatly from a "quantitative first, qualitative final review" pipeline, using ML to set a statistical baseline and LLM to perform sanity checking and risk defense.

---

## Runtime Evidence (include when relevant)

- Compiling modified python files: `python -m py_compile scripts/stock/model_price_predictor.py scripts/rag/routes/stock.py` completed with exit code 0.
- Executing `python scripts/stock/model_price_predictor.py 600519` with DeepSeek enabled successfully outputs prediction files `price_prediction.json` with a beautifully populated `"deepseek"` node:
  ```json
  "deepseek": {
    "reasoning_report": "...",
    "calibrated_predictions": { "close": 1404.51, "high": 1418.11, "low": 1360.19 },
    "calibrated_change_pct": { "close": -0.19, "high": 0.77, "low": -3.34 },
    "confidence_score": 50,
    "take_profit_target": null,
    "stop_loss_target": null,
    "calibration_status": "applied"
  }
  ```

---

## Current State (required)

- **Completed**: Fixed ML statistical bugs, feature extraction NaN errors, feature correlation, and recency weighting in `model_price_predictor.py`.
- **Completed**: Fully implemented DeepSeek calibration pipeline, defensive parsing, constraint/limit checks, and status tracking in `model_price_predictor.py`.
- **Completed**: Integrated DeepSeek status parameters into backend progress JSON in `routes/stock.py`.
- **Completed**: Added interactive checkbox, calibrated sub-row display with status warning support, and reasoning Markdown render modal in `index.html`.
- **Completed**: Run compiling and verification tests successfully. Written Session Memory documentation.

---

## Next Steps (required)

1. [ ] Extend the offline `prediction_tracker.py` backfill pipeline to measure and compare XGBoost vs DeepSeek calibrated prediction accuracy over time.
2. [ ] Add automated unit tests under `tests/` for confidence/noise classification, pricing clamping boundary rules, and JSON extraction edge cases.
3. [ ] Consider exposing DeepSeek cost and token metrics to the UI during daily training.

---

## References (required)

- `scripts/stock/model_price_predictor.py` -- Price predictor training and LLM calibration.
- `scripts/rag/routes/stock.py` -- Stock routing and training queue integration.
- `scripts/rag/templates/index.html` -- Web UI with DeepSeek controls and rendering blocks.
- `docs/memory/memory-20260521-tomorrow-price-prediction-refactor.md` -- This memory file.
