# Memory: Stock Scanners Cleanup

**Generated**: 2026-09-17 13:10
**Last updated**: 2026-09-17 13:40
**Project**: c:\jarvis
**Focus**: Remove redundant Stock scanner tabs and ATH; fix Long-term empty result after complete

---

## Goal & Scope (required)

Clean up Stock → Scanners: drop duplicate entries and 近5年高二次突破, and fix Long-term showing nothing after the scan finishes.

---

## Key Decisions (required)

1. **Remove 近5年高 · 二次突破 from Scanners**: Unified result must not show the ATH column; unified scan must not run `ath_rebreak_scanner`. Keep the Python module on disk unused unless later asked to delete it.
2. **Remove standalone AI scan tab**: AI scan is the left-side short-term scanner (`scanner.py`). It already runs as the left column of Left-Right-ATH. Do not keep a separate left-only shortcut.
3. **Remove standalone Right-side tab**: Right-side is the right column of Left-Right-ATH (`right_side_scanner.py`). Delete the independent tab.
4. **Keep four scanner entries**: Left-Right-ATH (left + right only), Long-term, Quality-value, Midday.
5. **Do not change pick rules** for left, right, QV, Midday, or Long-term selection logic except what is required to stop ATH in unified orchestration and to fix Long-term result display/load.
6. **Long-term empty page is in scope as a bug**: After status completes, show saved themes / metals / picks, or a real error — not a false blank/empty-picks state.
7. **Rejected: keep AI scan as left-only fast path**: User chose to delete the independent AI scan tab.
8. **Approach B approved**: Remove duplicate tabs; stop unified from running ATH; restore Long-term result page (outlook + thermometer); save JSON before status=done. Do not change theme LLM / SGE fetch in this task.
9. **Rejected: UI-only (A)** and **B + theme/gold pipeline (C)**.
10. **Keep tab label Left-Right-ATH**; do not rename this round.
11. **Do not change old `index.html` ATH UI** this round.
12. **Execute directly** after design approval (no written plan).

---

## Confirmed Assumptions (required)

- Left-Right-ATH is the unified scanner (`/api/stock/unified_scan/*`): left = `scanner.py` (AI scan), right = `right_side_scanner.py`, ath = `ath_rebreak_scanner.py`.
- `scanner.py` and `right_side_scanner.py` stay because unified still calls them.
- Tab label can stay "Left-Right-ATH" for this task unless a later rename is requested.
- Quality-value and Midday are unchanged.

---

## Constraints & Non-Goals (include when relevant)

- Do not change left/right/QV/Midday selection algorithms.
- Do not delete `ath_rebreak_scanner.py` in this task; only stop invoking it from Scanners/unified.
- Other Stock tabs (Watchlist, Weekly, Analyze, National team, Price train) are out of scope.

---

## Key Discoveries (required)

- Current UI tabs in `web/src/features/stock/ScannerPanel.tsx`: Left-Right-ATH, AI scan, Long-term, Quality-value, Midday, Right-side.
- Unified result UI is three columns in `UnifiedResult` (`scannerViews.tsx`); ATH is the third column.
- Long-term UI reads `result.picks` / `themes` / `precious_metals`. The result API 404s with `暂无长期推荐结果` when no JSON exists; `LongTermResult` does not render `result.error`. Progress is marked `done` before `_save_results` writes the JSON — a likely race for "completed with no results".
- 2026-09-17 long-term JSON at `C:/reports/stock/long_term/2026-09-17.json`: status done, finance_news_count 909, metals `data_available=false` but `llm_outlook` populated, `factors` thermometer populated, `themes=[]`, `picks=[]`. React hid outlook/thermometer, so the page looked empty.
- Old HTML `renderLtResult` already showed `llm_outlook` and factors even without prices.

---

## Current State (required)

- **Working**: Scanner tabs, ATH removal, Long-term result page, and save-before-done are implemented and verified.
- **Pending**: User may want commit and/or code review.
- **Blocked**: None.

---

## Next Steps (required)

1. [x] Trigger `brainstorming` after user confirmation
2. [x] Design how to drop ATH + standalone AI scan + Right-side, and how to fix Long-term empty results
3. [x] Implement after design approval (TDD)
4. [x] Verify in browser

---

## Notes for Next Session (include when relevant)

- Session started with no prior memory loaded (user chose start fresh).
- Question channel this session: `AskQuestion`.

---

## References (required)

- `web/src/features/stock/ScannerPanel.tsx` -- scanner tab list and job polling
- `web/src/features/stock/scannerViews.tsx` -- per-scanner result pages including ATH column and LongTermResult
- `scripts/stock/unified_scanner.py` -- orchestrates left + right + ath
- `scripts/stock/scanner.py` -- left / AI scan
- `scripts/stock/right_side_scanner.py` -- right-side
- `scripts/stock/ath_rebreak_scanner.py` -- 近5年高二次突破
- `scripts/stock/long_term_scanner.py` -- long-term; `status=done` before `_save_results`
- `scripts/rag/routes/stock.py` -- `/api/stock/long-term/result` 404 when no file

---

**Confirmed at**: 2026-09-17 13:10
