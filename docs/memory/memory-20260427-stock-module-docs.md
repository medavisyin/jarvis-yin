# Memory: Stock Module Per-Module Documentation Generation

**Generated**: 2026-04-27 13:05
**Last updated**: 2026-04-27
**Project**: c:\jarvis
**Focus**: Generate detailed per-module documentation for all stock modules with technical + financial theory content

---

## Goal & Scope (required)

User requested detailed documentation for EVERY functional module under `scripts/stock/`, with each doc containing:
- Technical implementation details (data structures, functions, algorithms)
- Financial theory backing (why the module exists, what investment theory it implements)
- A-share market specificity

Target: 21 functional modules (excluding `__init__.py`), all docs in Chinese.

---

## Key Decisions (required)

1. **Documentation language**: All Chinese (中文) — matches A-share target audience and previous stock docs language
2. **Output location**: `docs/stock-modules/` — separate from existing `docs/implementation/stock/` which contains grouped English tech docs
3. **Document structure**: Unified 7-section template (overview, financial theory, tech details, dependencies, config, examples, limitations)
4. **Parallel generation**: 4 batches of subagents, each handling 5-6 modules simultaneously

---

## Confirmed Assumptions (required)

- All 21 modules documented from actual source code reading (not assumptions)
- Existing `docs/implementation/stock/` docs remain untouched (different purpose: grouped English tech docs)
- Financial theory content is educational/practical, not academic citations

---

## Key Discoveries (required)

- `stock_pdf.py` short-term table column "资金" maps to `fund_score` (fundamental score), NOT fund flow — potential naming confusion
- `report_technical.py` imports `OLLAMA_HOST` and `MODEL_USAGE` but never uses them
- `fundamental_analysis.py` fetches `current_ratio` but `score_fundamentals` doesn't use it in scoring
- `fetch_market_data.py` imports `STOCK_CACHE_DIR` but doesn't use it
- `market_sentiment.py` imports `STOCK_DATA_DIR` but doesn't use it
- `backtest_engine.py` imports `_build_timing_targets`, `_get_feature_df` from model_timing but doesn't use them in function body
- `model_timing` exit signal behavior differs between `predict_timing` (observational) and `backtest_engine` (actionable -1)
- `features.py` feature count is dynamic (not fixed 55) — depends on data availability per stock

---

## Current State (required)

- **Working**: 21 module docs + 1 README index created under `docs/stock-modules/`
- **Pending**: None — all docs generated
- **Blocked**: None

---

## Next Steps (required)

1. [ ] User review of generated docs for accuracy and completeness
2. [ ] Fix identified code issues (unused imports, naming inconsistencies)
3. [ ] Consider cross-linking between module docs

---

## References (required)

- `c:\jarvis\docs\stock-modules\` — All 22 files (21 module docs + README index)
- `c:\jarvis\docs\stock-modules\README.md` — Index with module classification and dependency graph
- `c:\jarvis\scripts\stock\` — Source code (21 functional .py files)
- `c:\jarvis\docs\implementation\stock\` — Existing grouped English implementation docs

---

**Confirmed at**: 2026-04-27 13:05
