# Memory: Stock Module Code Review, Fixes & Documentation

**Generated**: 2026-04-14 (session)
**Project**: c:\jarvis
**Focus**: Complete code review of stock prediction module, fix all critical/important issues, create comprehensive documentation

---

## Goal & Scope (required)

User requested:
1. Full code review of the stock feature (9 Python modules in `scripts/stock/`) and ML components
2. Create stock documentation — both knowledge guide (Chinese) and tech implementation (English)
3. Create stock usage how-to guide (Chinese) for practical investing workflow
4. Update all existing docs (docs-index, backend-overview, implementation README)

---

## Key Decisions (required)

1. **Documentation language split**: Tech docs in English, stock knowledge + usage guides in Chinese (中文) — matches the module's output language and A-share target audience
2. **Stock knowledge depth**: Beginner-friendly (A option) — explain everything from scratch
3. **Execution approach**: All tasks in parallel — code review + docs + updates simultaneously
4. **Fix all issues**: User chose to fix both Critical (4) and Important (9) issues

---

## Confirmed Assumptions (required)

- Stock module targets Chinese A-share market only
- Default documentation language: English for tech, Chinese for stock-facing content
- Code review severity thresholds: Critical = must fix, Important = should fix, Minor = nice to have
- The plan document (`docs/plans/2026-04-12-stock-prediction.md`) is the authoritative requirements reference

---

## Key Discoveries (required)

- **Walk-forward model bug**: The walk-forward loop iterated from most recent to oldest, so `last_model` ended up being the model trained on the oldest data window — but was used to predict with the latest features
- **Imputation leakage**: `fillna(X.median())` was applied to the full dataset before train/test splitting, leaking future data statistics into training
- **Wrong LLM model tier**: `llm_reasoning.py` docstring claimed "HEAVY model + think mode" but code used `technical_summary` (fast tier) with `think=False`
- **Score aggregation bias**: Sentiment `daily_score` excluded articles with score=0, biasing the average away from neutral
- **Missing cross-domain ML features**: Features were exclusively price/TA-derived; no fundamental (PE, ROE), sentiment, or calendar features despite plan requiring them
- Overall code quality: 5.5/10 pre-fix, estimated 7-7.5/10 post-fix

---

## Current State (required)

- **Working**: All 13 fixes applied (4 Critical + 9 Important), 4 new doc files created, 3 existing docs updated
- **Pending**: Code review of the fixes themselves (dispatched), minor issues (6) not yet fixed
- **Blocked**: None

---

## Next Steps (required)

1. [ ] Fix remaining 6 Minor issues (unused imports, side effects at import, NaN guards in patterns, regex injection in search, eval_set usage)
2. [ ] Implement Phase 4.5 from plan: Market scanner, composite scoring, AI recommendation
3. [ ] Implement Phase 5 from plan: Daily stock pipeline (`run_stock_pipeline.py`)
4. [ ] Implement Phase 6 from plan: Portfolio tracking, backtesting, alerts
5. [ ] Add RAG integration for stock news (plan Task 3.3)
6. [ ] Consider adding more fundamental features to ML model: PEG, FCF, analyst consensus

---

## References (required)

- `c:\jarvis\scripts\stock\` — All 10 stock module source files
- `c:\jarvis\docs\plans\2026-04-12-stock-prediction.md` — Implementation plan (requirements)
- `c:\jarvis\docs\stock-knowledge-guide.md` — NEW: Chinese stock knowledge guide
- `c:\jarvis\docs\stock-usage-guide.md` — NEW: Chinese stock usage how-to guide
- `c:\jarvis\docs\implementation\stock\stock-prediction-impl.md` — NEW: English tech implementation doc
- `c:\jarvis\docs\implementation\stock\README.md` — NEW: Stock impl index
- `c:\jarvis\docs\docs-index.md` — UPDATED: Added stock section
- `c:\jarvis\docs\backend-overview.md` — UPDATED: Added stock directory, APIs, paths, deps
- `c:\jarvis\docs\implementation\README.md` — UPDATED: Added stock folder

---

**Confirmed at**: 2026-04-14
