# Memory: National Team ETF Flow Freshness

**Generated**: 2026-09-15
**Last updated**: 2026-09-15 (18889 dist rebuilt; last grid shows fetch datetime)
**Project**: c:\jarvis
**Focus**: National team 页「全市场主力」日期不诚实 + React 丢失每只 ETF 当天实时份额

---

## Goal & Scope (required)

用户在 National team 看到「资金信号 · 全市场主力」只剩 `今日净流入 -81.99 亿 · 5日均 -160.42 亿`，不确定是不是当天，并记得以前能看每只 ETF 的流入/流出（当天实时）。确认后要：恢复每只当天可见变化，并让每个数字标真实日期。

In scope:
- 全市场主力标真实日期（禁止在数据不是当天时写「今日」）
- 恢复每只 ETF「开盘至今份额」（东财 f38）
- 官方份额表标明公告/对比日期

Out of scope:
- 把全 A 股主力资金当成 16 只核心 ETF 的流入
- 本轮不恢复盘中弱代理、综合研判（未要求）

---

## Key Decisions (required)

1. **不加载旧 session memory，从本问题重新核对**。
2. **用户确认理解（2026-09-15）**：要看清每只 ETF 当天变化，并知道每个数字的真实日期。
3. **下一步 `brainstorming`**，并写入本 memory 文件。
4. **Rejected: 把「全市场主力」解释成 16 只 ETF 资金流**：旧 HTML 已注明那是全 A 股超大单+大单，与 ETF 份额是两套口径。
5. **方案 A 已批准**：日期诚实 + 恢复开盘至今份额；不搬弱代理/综合研判。
6. **架构已批准**：`market_flow.latest_date`；不是当天不写「今日」；过期提示；`intraday_shares` 接 React；官方表标对比日 + SSE 统计日期。
7. **文案已批准**：今日 vs「净流入（截至 {date}）」；开盘至今 `xx → yy 亿份`；「当天 vs {ref_date}」；「份额公告日: {sse_stat_date}（深市为最新日）」。
8. **错误处理/测试已批准**；下一步直接实现（无 formal plan）。
9. **用户看不到变化的原因**：改动只在 Vite 源码；`http://127.0.0.1:18889` 读 `web/dist`。用户选 A：rebuild dist，最后一表保留官方份额，但标清当前拉取日期+时间。

---

## Confirmed Assumptions (required)

- 用户说的「下面的 grid」是 ETF 表（名称/代码/跟踪指数/份额/当天），不是区间汇总表。
- 「流入/流出」在旧 UI 里对应的是份额变化（亿份 / %），不是东财个股主力净流入亿元字段。
- 官方份额继续用上交所/深交所公告；盘中用东财 f38，禁止成交额硬估。

---

## Constraints & Non-Goals (include when relevant)

- 不声称确认国家队身份。
- 不把官方 T+1 份额伪装成盘中实时。
- 不扩展行业 ETF 的盘中份额（旧约定只覆盖宽基）。

---

## Key Discoveries (required)

- React `NationalTeamPanel.tsx` 只渲染 `fund_signals.market_flow` 的汇总行；旧 HTML `renderNationalTeam` 还有「开盘至今份额」、盘中弱代理、1周/1月/3月、综合研判。
- API `/api/stock/national-team` **仍返回** `intraday_shares`、`intraday`、`period_stats.per_etf_periods`；是前端没接，不是后端删了。
- 用户看到的 `-81.99 亿 / 5日均 -160.42 亿` 精确对上 `C:/reports/stock/.cache/.market_flow/history.csv` **2026-09-08** 行（及 9/2–9/8 五日均），不是 2026-09-15。`national_team_fund_signals` 未下发 `latest_date`。
- 上交所 `sse_latest.csv` 统计日期停在 **2026-09-11**；当天 snapshot 里沪市 ETF `change_pct` 多为 `0.0`。深市几只有小幅变化。
- 东财 `em_spot_shares.json` 的 `data_date` 为 **20260915**（真正当天盘中份额），旧区块 `_renderNtIntradayShares` 用这个。
- `web/dist` 不含源码改动时，18889 会完全看不出「开盘至今」「当天 vs」。必须 `npm run build`。

---

## Runtime Evidence (include when relevant)

- `snapshot_20260915.json` `fetched_at`: 2026-09-15T11:55:18；沪市核心 ETF `change_pct` 多为 0.0。
- `em_spot_shares.json`: 510300/510050 等 `data_date=20260915`；159919 官方 63.11 vs 东财 62.62。
- market_flow CSV 最后一行: `2026-09-08` 主力净流入 `-8198545408` → -81.99 亿。

---

## Current State (required)

- **Working**: 18889 已吃到新 `web/dist`。最后一张官方份额表上方有「参考时间 {fetched_at} · 对比日 · 份额公告日」，表内有「参考时间」列（本次拉取的当前日期时间）。
- **Pending**: 可选 code review / commit
- **Blocked**: 无。只开 18889 而不 rebuild 会继续看到旧 UI。

---

## Next Steps (required)

1. [x] Brainstorm 并批准设计
2. [x] 实现日期诚实 + 开盘至今份额 UI
3. [x] 浏览器验收 National team 页
4. [x] 用户选 A：rebuild dist + 最后一表标清当前拉取日期时间
5. [ ] 用户要求时再 code review / commit

---

## Notes for Next Session (include when relevant)

- 相关旧记忆：`memory-20260804-national-team-intraday-shares.md`、`memory-20260730-national-team-freshness.md`
- UI：`web/src/features/stock/NationalTeamPanel.tsx`
- 旧参考：`scripts/rag/templates/index.html` `_renderNtIntradayShares` / `renderNationalTeam`
- 数据：`scripts/stock/china_market_data.py` `national_team_fund_signals` / `national_team_intraday_shares`

---

## References (required)

- `web/src/features/stock/NationalTeamPanel.tsx` — 开盘至今份额 + 资金流截至日 + 官方表对比日
- `web/src/lib/stockFormat.ts` — `marketFlowNetCaption` / `officialDayHeader` / `officialGridCaption` / `formatFetchedAt` / `shareAnnouncementNote`
- `scripts/rag/routes/stock.py` — `GET /api/stock/national-team`
- `scripts/stock/china_market_data.py` — `dataframe_as_of_date`、`latest_date`、`sse_stat_date`、盘中 f38
- `tests/test_national_team_fund_dates.py` — backend 日期字段
- `scripts/rag/templates/index.html` — 旧完整 UI（SPA 为现网）
- `C:/reports/stock/.cache/.market_flow/history.csv` — 全市场主力缓存
- `C:/reports/stock/.cache/.national_team/` — snapshot / sse_latest / em_spot_shares

---

**Confirmed at**: 2026-09-15
