# Memory: Long-Term Stock Recs — News Sources & More Factors

**Generated**: 2026-08-30 ~14:40 UTC+8
**Last updated**: 2026-08-30 ~15:20 UTC+8
**Project**: c:\jarvis
**Focus**: Adjust AI 股票推荐(长期) to consume the new 6-category finance news plus additional structured macro and market-factor blocks

---

## Goal & Scope (required)

Daily Fetch finance news is now 6 categories (综合市场 / 中国政策金融 / 美国政治金融 / 数字货币 / 黄金 / 石油, including official sources such as BLS, Fed, PBOC, CSRC). Long-term recommendations still read only world-news + AI briefing. User wants all new sources wired in, world news and AI briefing kept, and more factors considered: official macro as structured series plus oil / USD / US rates / crypto as quantitative thermometers. Each new factor gets its own mandatory report block (like gold/silver today), then feeds theme extraction and A-share picks.

---

## Key Decisions (required)

1. **Reversed: News inputs = add all, do not replace**: Daily Fetch has replaced world-news with 6-category finance-news. Primary inputs are finance + AI briefing. Legacy world-news files, if present, fold silently into 综合市场; reports no longer list「国际新闻」.
2. **More factors = B+C**: official US/China macro as structured data (not just headlines) AND quantitative market factors: oil, dollar, US rates, crypto.
3. **Report structure = separate blocks**: each of 宏观数据、油价、美元、美债利率、加密货币 is a mandatory analysis section like the existing gold/silver block; then theme LLM uses all of them.
4. **A-share only**: oil/USD/rates/crypto are thermometers and theme clues, not direct BTC or US-stock picks.
5. **Keep gold/silver SGE block**: gold *news* (Kitco etc.) goes into news inputs; do not add a second gold-price analysis block.
6. **Out of scope**: Daily Fetch 6-category fetch/taxonomy itself; short-term / unified left-right scanner.
7. **Defaults confirmed**: hold horizon still ~3 months–1 year; max 5 picks; DeepSeek if checked else local model; news window still 14 days; structured series = latest print + ~12-month trend; reuse Daily Fetch on-disk files + akshare; no new paid APIs; missing category soft-fails.
8. **Approach A approved**: extend `long_term_scanner.py` in place (not five extra LLM calls; not extract `long_term_factors.py`).
9. **Thermometer LLM = one call** returning keys `macro, oil, dollar, rates, crypto` plus `a_share_implication`; gold/silver LLM stays independent. LLM count 3→4.
10. **Data sources**: Yahoo chart (same proxy as VIX) for WTI `CL=F`, DXY `DX-Y.NYB`, `^TNX`, `BTC-USD`; akshare `macro_usa_*` for NFP/unemployment/ISM/ADP; finance news from canonical `finance-news/finance-news-data.json` only (never `finance_news_data_path` fallback).
11. **Token caps (updated 2026-08-30 later)**: AI 40; finance **20 headlines per category**, **recency-first** (newer dates first; official `source_id` only as same-day tie-break). Window remains 14 calendar days.
12. **Next step chosen**: write a same-session implementation plan (`writing-plans`), not execute-directly.
13. **Plan review (2026-08-30)**: 3 must-fix test/orchestration bugs (today-folder dates; history.json glob; live-signal helper required), 3 should-fix (UI slice, None series, keep recommended_stocks in extracted prompt). Patches written into the plan.

---

## Confirmed Assumptions (required)

- Long-term scanner currently reads `world-news-data.json` + `briefing-data.json` over 14 days, plus black swan, hot sectors, VIX/Fear-Greed, Shanghai gold/silver.
- **Corrected 2026-08-30**: world-news is no longer produced; finance-news replaced it. AI briefing remains.
- New finance news lives in the Daily Fetch 6-category pipeline (`scripts/pipeline/finance_sources.json`).
- Quality gate stays “宁缺毋滥”; 0 themes / 0 picks is still valid.
- User started this session with no prior memory loaded (fresh).

---

## Constraints & Non-Goals (include when relevant)

- Do not change Daily Fetch source catalog or fetchers as part of this task.
- Do not change unified/short-term/right-side scanners.
- Do not recommend BTC or US-listed names as picks.
- Do not duplicate gold price analysis (SGE block stays; gold news is news only).

---

## Key Discoveries (required)

- Feature surface: UI「🔮 长期推荐」; impl `scripts/stock/long_term_scanner.py`; strategy `docs/stock-modules/strategy-long-term-deepseek.md`.
- Current pipeline: 14d signals → precious metals → LLM themes → map to A-shares → filters → upside assessment → LLM ≤5 picks.
- `_collect_signals()` currently does not read finance-news category outputs (this is the gap the plan fixes).
- Finance taxonomy: markets, china-policy, us-political, crypto, gold, oil (official + media). US macro fetchers on disk include BLS, BEA, Census, ISM, ADP, Fed.
- `finance_news_paths.finance_news_data_path` falls back to world-news — must not be used by long-term ingest.
- VIX already uses Yahoo chart JSON + `STOCK_PROXY`; oil/DXY/10Y/BTC should reuse that pattern.
- Current LLM calls: metals outlook + themes + picks. After change: +1 thermometer outlook.
- `_extract_news_items` does not prefer `title_zh`; finance items need a dedicated extractor.
- `_generate_report` / `_save_results` currently have no `factors` argument; UI `renderLtResult` only special-cases 贵金属.

---

## Current State (required)

- **Working**: Recency-first finance headlines, 20 per category. `tests/test_long_term_news_factors.py` covers this.
- **Pending**: Live long-term scan after Jarvis restart; optional code review.
- **Blocked**: none.

---

## Next Steps (required)

1. [x] Brainstorm and approve design (approach A)
2. [x] Write implementation plan
3. [x] Execute plan task-by-task (TDD)
4. [ ] Optional: live scan with DeepSeek + code review

---

## Notes for Next Session (include when relevant)

- Session started 2026-08-30; user chose start-fresh (did not load ath-rebreak / daily-fetch / finance-news memories).
- Related but not loaded: `memory-20260827-finance-news-categories.md`, `memory-20260521-stock-recommendation-horizon.md`.

---

## References (required)

- `scripts/stock/long_term_scanner.py` — long-term scanner
- `docs/stock-modules/strategy-long-term-deepseek.md` — user-facing strategy
- `scripts/pipeline/finance_sources.json` — 6-category source catalog
- `scripts/rag/templates/index.html` — long-term rec UI
- `docs/plans/2026-08-30-long-term-news-factors.md` — approved implementation plan
- `docs/memory/memory-20260827-finance-news-categories.md` — finance news expansion (not loaded this session)

---

**Confirmed at**: 2026-08-30 ~14:40 UTC+8
