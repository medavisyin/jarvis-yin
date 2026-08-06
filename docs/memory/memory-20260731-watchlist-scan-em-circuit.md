# Memory: Watchlist Refresh + EM Circuit + ChiNext Filter

**Generated**: 2026-07-31 ~14:07 UTC+8
**Last updated**: 2026-07-31 ~14:07 UTC+8
**Project**: c:\jarvis
**Focus**: 东财熔断快切 + 自选轻刷新 + 扫描排除创业板（保留科创板）

---

## Goal & Scope (required)

自选股「刷新列表」因东财 `RemoteDisconnected` + 6 次指数退避极慢；统一左右扫描同源问题。修复：进程级东财熔断（半开恢复）+ 快切降级；刷新列表只拉新浪实时；扫描排除 `300`/`301`，保留 `688`/`689`。

---

## Key Decisions (required)

1. **C+B**：熔断+快切，且刷新列表只走实时（全量留给数据预热）。
2. **科创板保留**：只排除创业板 `300`/`301`；右侧 Layer-1 显式纳入 `688`（原先 `60/00/30` 实际排除了科创）。
3. **不限制自选股**添加创业板代码。
4. **半开恢复**：熔断后 60s 允许一次探测，避免永久 skip。
5. **CompanySurvey 不因熔断跳过**（探针仍可用）；熔断主要挡 ak hist/info/fund_flow/spot_em。
6. **实现分支**：`fix/em-circuit-watchlist-scan`（勿直接在 main 落实现）。

---

## Confirmed Assumptions (required)

- 用户优先修好失败根因恢复速度，而非仅「快速失败」。
- 扫描侧与自选股刷新共用同一熔断。

---

## Key Discoveries (required)

- 实测：新浪实时/日线、CompanySurvey、新闻可用；`stock_zh_a_hist` / `stock_individual_info_em` 秒断。
- 自选约 39 只；每只全量更新 × EM 重试可拖到数十分钟～小时。
- `fetch_realtime_quote` 若 Sina 失败回退全市场 `spot_em`×6，轻刷新必须 `heavy_fallback=False`。
- 断连文案需匹配 `Remote end closed`（不只 `RemoteDisconnected`）。

---

## Current State (required)

- **Working**: Tasks 1–6 + review fixes (Critical-1, Important-1～4, Minor-1/3)；单测 **28 passed**
- **Pending**: follow-up code review（用户确认）；重启 Jarvis 实测；commit
- **Blocked**: 无

---

## Next Steps (required)

1. [ ] 完成 code review 并按需修 Important
2. [ ] 重启 Jarvis 实测自选刷新与统一扫描
3. [ ] 用户要求时再 commit

---

## Notes for Next Session (include when relevant)

- 计划：`docs/plans/2026-07-31-em-circuit-watchlist-scan.md`
- 预热路径仍走 `update_stock_data`（会受益于熔断）

---

## References (required)

- `scripts/stock/eastmoney_throttle.py` — throttle + circuit
- `scripts/stock/fetch_market_data.py` — OHLCV/profile/realtime wiring
- `scripts/stock/china_market_data.py` / `fetch_resilience.py` — fund-flow + backfill
- `scripts/stock/watchlist.py` — light refresh
- `scripts/stock/board_filters.py` / `scanner.py` / `right_side_scanner.py` / `unified_scanner.py`
- `docs/plans/2026-07-31-em-circuit-watchlist-scan.md`

---

**Confirmed at**: 2026-07-31
