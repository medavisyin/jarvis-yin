# Memory: Left-Side Scanner High-Chase Diagnosis

**Generated**: 2026-09-15 13:30
**Last updated**: 2026-09-15 14:45
**Project**: c:\jarvis
**Focus**: Why Left-Right-ATH 左侧·短期 recommendations look like buying at highs

---

## Goal & Scope (required)

User observed that recent Left-Right-ATH **左侧·短期** picks look like 高位接盘. Left-side should buy pullbacks/accumulation. Diagnosis of recent unified left-side results is complete. Next: design a fix (no code until design is approved). Out of scope unless later expanded: standalone AI scan, right-side, ATH, quality-value, long-term.

---

## Key Decisions (required)

1. **Scanner surface**: Left-Right-ATH result block「左侧·短期」, not the standalone AI scan button.
2. **Outcome (updated)**: Diagnosis first, then design a fix; still no code until the design is approved.
3. **Evidence**: Latest completed left scan is 2026-09-14 (0 picks). Pattern taken from recent non-empty runs: 2026-09-09, 09-08, 09-02, 08-30.
4. **Workflow**: `clarify-requirements` → `brainstorming` → `systematic-debugging` (done) → back to `brainstorming` for the fix design.
5. **User chose**: record root cause; design approach **C**; execute directly (TDD), no separate `writing-plans` doc.
6. **Approved design C**:
   - `detect_smart_money_accumulation`: local `daily.csv` first; missing price → 观察期, never `price_chg_5d=0` fake 横盘; `ret_20d > 10%` cannot be 布局期.
   - Hard veto after enrich / after Layer3 买入: `dd_20 > -5%` (within 5% of 20-day high) cannot 买入; record `veto_reason`.
   - Scanner reads `rsi_14` (not `RSI`) for RSI>75 overbought.
   - Layer1 cannot see 20d high (spot snapshot only); gates live at Layer 2.5 + Layer3.

---

## Confirmed Assumptions (required)

- 「左测」means 左侧 (left-side / dip-buy), not a separate test.
- User's "AI scan" wording referred to the left-side recommendations inside Left-Right-ATH, not `/api/stock/scan`.
- Success for diagnosis = a clear layer-by-layer root cause.

---

## Constraints & Non-Goals (include when relevant)

- No code until the user approves a design.
- Do not change right-side / ATH / quality-value / long-term unless they share the broken accumulation helper.

---

## Key Discoveries (required)

- Unified scanner ≠ standalone AI scan. Left-side logic: `scripts/stock/scanner.py`, orchestrated by `scripts/stock/unified_scanner.py`.
- **Primary bug**: `detect_smart_money_accumulation` in `china_market_data.py` fetches 15-day qfq via live akshare. On exception it sets `price_chg_5d = 0`. Zero is the *best* “横盘” score (`abs < 2` and `< 1`), so any name with 5-day fund inflow is labeled **布局期** with detail `股价横盘(+0.0%)，主力悄悄建仓`.
- That fake 布局期 drives `ff_score` 80–95 (30% of Layer2 rule score), so those names enter DeepSeek Layer3. The LLM copies the 横盘吸筹 story and outputs 买入. Scan JSON for 浙农/华翔/润泽 all show `+0.0%` while local daily.csv shows they were near 20-day highs (dd_20 ≈ -0.5% to -2.6%) after +10–17% over 10–20 days.
- The `+0.0%` string is epidemic across 09-02 / 09-08 / 09-09 candidates, not just the top picks — price fetch is failing systematically.
- **Amplifier 1**: Layer1 only scores *today's* change (-7% to +8%). A stock up 17% in 20 days with -0.3% today looks like a left-side pullback.
- **Amplifier 2**: Layer3 prompt has 今日涨跌, not 20d return or distance-from-high. DeepSeek cannot check “股价未大涨”.
- **Amplifier 3**: RSI overbought gate is dead. `compute_indicators` writes `rsi_14`; scanner reads `df["RSI"]`. All recent candidates have `rsi: null`, `overbought: false`.
- **Amplifier 4**: Recent scans usually take Layer2 **rule_fallback** (l2=100, no `xgb_rank`). XGB days (09-10, 09-01) returned only 3 names and Layer3 said 观望. Rule path is what produces the 高位 买入 list.
- **XGB side issue (not the recent-pick cause)**: `model_cross_sectional` uses same-day `ret_1d` as both feature and alpha label (docstring claims T-1→T, code does not shift). Momentum leakage if/when XGB is the Layer2 path.
- Latest 2026-09-14 left scan: 0 recommendations (Layer3 rejected everyone). User's 高位接盘 complaint matches 08-30 / 09-02 / 09-08 / 09-09 picks, e.g. 浙农股份, 华翔股份, 润泽科技, 新洋丰.

---

## Runtime Evidence (include when relevant)

- 2026-09-09 浙农股份: 买入 / DeepSeek / 布局期 / `横盘(+0.0%)` / ret_20d +17.5% / dd_20 -2.5%.
- 2026-09-08 华翔股份: 买入 / DeepSeek / 布局期 / `横盘(+0.0%)` / ret_20d +10.4% / dd_20 -2.5%.
- 2026-08-30 润泽科技: 买入 / DeepSeek / 布局期 / `横盘(+0.0%)` / ret_10d +13.1% / dd_20 -2.6%; DeepSeek risk text even said 接近历史高位 but still 买入.
- 2026-09-14: top_picks=[], layer2_count=100, xgb=false, rsi_null=50/50.

---

## Open Risks (include when relevant)

- Even after fixing the 0% default, a true last-5-day flat near a 20-day high can still be labeled 布局期 (window too short).
- Shared helper `detect_smart_money_accumulation` is also used outside the left scanner; fail-closed change may affect other callers.

---

## Current State (required)

- **Working**: Root cause fixed; review loop ended after NaN/invalid `dd_20` veto. `tests/test_left_side_high_chase.py` 13 passed.
- **Pending**: User re-run of Left-Right-ATH. Deferred follow-up findings: Minor short-window `dd_20` (<20 bars), no `_layer3_llm_rank` stamp test.
- **Blocked**: None.

---

## Next Steps (required)

1. [x] Inspect recent left-side results vs price/highs.
2. [x] Trace funnel and identify failing layer.
3. [x] User picked approach C.
4. [x] Design sections approved; execute directly.
5. [x] TDD: tests then china_market_data + scanner changes.
6. [x] receiving-code-review: accepted Important-1~4 and Minor-1~4; tests 12 passed.
7. [ ] Follow-up review of applied fixes (user gate).
8. [ ] Re-run Left-Right-ATH in the UI.

---

## Notes for Next Session (include when relevant)

- Do not implement from this memory alone. Design must be approved.
- `detect_smart_money_accumulation` is the primary edit site; scanner RSI column and Layer3 prompt are amplifiers.

---

## References (required)

- `scripts/stock/scanner.py` — left-side 3-layer scanner (`df["RSI"]` vs `rsi_14`)
- `scripts/stock/china_market_data.py` — `detect_smart_money_accumulation` (`price_chg_5d = 0` on exception)
- `scripts/stock/technical_analysis.py` — writes `rsi_14`
- `scripts/stock/model_cross_sectional.py` — same-day ret_1d label leakage
- `scripts/stock/unified_scanner.py` — Left-Right-ATH orchestrator
- `C:/reports/stock/scans/2026-09-09.json` — 浙农 / 丽江 picks
- `C:/reports/stock/scans/2026-09-08.json` — 华翔 / 骏鼎达 / 徐工 picks
- `docs/stock-modules/strategy-unified-left-right-deepseek.md` — left/right strategy

---

**Confirmed at**: 2026-09-15 14:20
