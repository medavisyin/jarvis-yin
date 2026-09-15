# Memory: Scanner Result UI Regression

**Generated**: 2026-09-15 13:40
**Last updated**: 2026-09-15 14:10
**Project**: c:\jarvis
**Focus**: Restore per-scanner result pages; unified Picks/Left/Right/ATH template is a UI regression

---

## Goal & Scope (required)

Scanners start 结束后结果页被换成统一模板（Picks / Left / short-term / Right-side / ATH rebreak），和以前完全不一样。quality-value 这次是空结果，但问题是布局回归，不是“没选出”本身。

所有 Scanner 都不要用这套通用栏目；各自恢复原来的结果页。扫描算法/选股逻辑不改。

---

## Key Decisions (required)

1. **Fix is UI restoration, not scan logic**: Empty quality-value picks may be valid; the page must still look like the old quality-value result view.
2. **All scanners, not only quality-value**: Restore each scanner's original result page; do not keep the generic four-column template.
3. **Rejected: empty-state-only patch**: User declined fixing only the empty state while keeping the generic layout when there are picks.
4. **Approach A approved**: Per-scanner React result cards ported from `index.html` renderers; keep shared Start/Stop/DeepSeek chrome; delete generic Picks/Left/Right/ATH fallback.
5. **Rejected: markdown-report HTML (B)** and **QV-only first pass (C)**.
6. **Execute directly** (no written plan). TDD on view-model helpers, then React views.

---

## Confirmed Assumptions (required)

- Start / progress / done status can stay; result display must return to each scanner's old layout.
- Scanner algorithms and pick rules are out of scope.
- Other stock features should not be changed along the way.

---

## Constraints & Non-Goals (include when relevant)

- Do not change selection/filter rules.
- Do not use the unified Picks / Left / Right-side / ATH rebreak columns as the scanner result UI.

---

## Key Discoveries (required)

- Symptom on quality-value after Start: `done done · finished`, then `Picks: 暂无`, `Left / short-term: 暂无`, `Right-side: 暂无`, `ATH rebreak: 暂无`.
- Root cause: React `ScannerPanel` in `web/src/pages/StockPage.tsx` ports all scanners through `extractScanSections` + generic PickTable. Only `unified` has a 3-col layout; every other scanner gets the four English columns.
- Old HTML had dedicated renderers: `renderQvResult`, `_buildScanResultHtml`, `renderLtResult`, `renderMiddayResultHTML`, `_buildRightSideHtml`, `_buildAthRebreakHtml`.
- Quality-value JSON is `{ picks, stats, horizon, use_deepseek }`. Empty picks is 宁缺毋滥; `stats.snapshot_failed` is a real fetch failure.
- `done done · finished` is `status.status` (`done`) concatenated with `status.step` (`done`) plus a terminal suffix.
- Right-side / midday / ATH use `completed` / `failed`; React `isTerminalJobStatus` currently only treats `done|error|stopped|complete`.

---

## Current State (required)

- **Working**: Per-scanner result cards restored; Important-1/2/3/4/5/7/8 closed; Start no longer stuck after tab switch; poll wait is abort-aware.
- **Pending**: User may accept after 2 review cycles; commit not requested.
- **Blocked**: None.

---

## Next Steps (required)

1. [x] Diagnose why scanner results render as the unified four-column template
2. [x] Restore original per-scanner result pages (including empty quality-value)
3. [x] Verify in browser that scanners no longer show Picks/Left/Right/ATH as the result layout

---

## Notes for Next Session (include when relevant)

- User selected start-fresh at session load; this file is the new baseline for this task.

---

## References (required)

- `web/src/lib/scannerResults.ts` -- status label + QV empty copy helpers
- `web/src/lib/scannerResults.test.ts` -- RED/GREEN tests for those helpers
- `web/src/features/stock/ScannerPanel.tsx` -- shared chrome + per-scanner switch
- `web/src/features/stock/scannerViews.tsx` -- QV/scan/LT/midday/right/ATH/unified cards
- `web/src/pages/StockPage.tsx` -- imports ScannerPanel; generic PickTable removed
- `scripts/rag/templates/index.html` -- old per-scanner renderers (source of truth for cards)
- `scripts/rag/routes/stock.py` -- stock/scanner API
- `docs/memory/memory-20260816-quality-undervalued-screener.md` -- prior quality-value work
- `docs/memory/memory-20260702-unified-scanner-zero-picks.md` -- prior zero-picks scanner issue

---

**Confirmed at**: 2026-09-15 13:40
