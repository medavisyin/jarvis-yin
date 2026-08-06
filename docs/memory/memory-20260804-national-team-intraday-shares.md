# Memory: National Team Intraday Share Discovery

**Generated**: 2026-08-04 ~15:58 UTC+8
**Last updated**: 2026-08-04 ~16:50 UTC+8
**Project**: c:\jarvis
**Focus**: 国家队宽基 ETF「开盘至今」份额发现（官方昨收 → 东财盘中 f38）

---

## Goal & Scope (required)

在国家队弹窗中，除日更份额异常（如 `50ETF 72.1 → 76.8 亿份 (+6.4%)`）外，盘中也要看到同类「开盘至今」发现。不要用成交额硬估；现有弱代理监测保留。

---

## Key Decisions (required)

1. **目标形态 A**：尽量接近日更文案 `xx → yy 亿份 (+z%)`（开盘至今份额量级）。
2. **数据策略 A**：优先东财准实时份额字段（如 `f38`）；有则显示；无则「无数据」；禁止成交额硬估。
3. **基线 A**：`xx` = 上一交易日交易所官方份额（SSE/SZSE）；`yy` = 东财盘中 `f38`。
4. **范围 B**：只覆盖宽基 ETF（不含行业）；保留现有弱代理区块；异常高亮沿用日更单只 `|变化| > 3%`。
5. **理解已确认**（2026-08-04）；下一步 `brainstorming` 定实现方案。
6. **方案 A 已批准并直接实现**：`national_team_intraday_shares()` + API `intraday_shares` + UI 新区块（弱代理上方）。
7. **Rejected: 塞进弱代理 payload / 仅 UI 拼装**：职责混乱或难测。

---

## Confirmed Assumptions (required)

- 不改日更份额主逻辑与行业 ETF 监控池。
- 官方昨收与东财盘中可能口径略有偏差，需标注来源。
- 沿用现有东财限流/断路器习惯。

---

## Constraints & Non-Goals (include when relevant)

- 不做成交额/申赎硬估份额。
- 不替换/去掉「盘中实时疑似信号（弱代理监测）」。
- 不扩展到行业 ETF。

---

## Key Discoveries (required)

- 日更异常来自 `china_market_data._detect_share_anomalies`（官方份额快照对比；单只 >3% 记 anomaly）。
- 盘中弱代理在 `national_team_intraday.py`（近5分钟同步、近30分钟成交额等），与份额无关。
- 东财 `stock/get` 无 `f38`；ETF 板块 `clist` 分页可得；探针日 9 只宽基均有 `f38` 且 `f297=当日`。
- `test_national_team_freshness.py` 中资金流相关用例仍指向未实现 API（与本任务无关的既有 WIP）。

---

## Current State (required)

- **Working**: `national_team_intraday_shares` + helpers；API/UI 已接线；相关单测 **44 passed**（含 intraday 回归）
- **Pending**: 重启 Jarvis 手工验收弹窗「开盘至今份额（宽基）」；可选 code review / commit
- **Blocked**: 无

---

## Next Steps (required)

1. [x] Brainstorm 并批准 Design A
2. [x] TDD 实现 fetch/compare/API/UI
3. [ ] 重启 Jarvis 手工验收
4. [ ] 用户要求时再 commit / review

---

## Notes for Next Session (include when relevant)

- 相关记忆：`memory-20260730-national-team-freshness.md`（弱代理盘中信号）
- UI：`_renderNtIntradayShares` 在弱代理上方
- API：`/api/stock/national-team` → `intraday_shares`
- EM clist 缓存约 90s：`em_spot_shares.json`

---

## References (required)

- `scripts/stock/china_market_data.py` — `parse_etf_spot_share_diff` / `fetch_etf_spot_shares_em` / `national_team_intraday_shares`
- `scripts/stock/national_team_intraday.py` — 现有弱代理
- `scripts/rag/routes/stock.py` — national_team API
- `scripts/rag/templates/index.html` — `_renderNtIntradayShares`
- `tests/test_national_team_intraday_shares.py` — 本功能单测
- `tmp/_debug_etf_spot_share.py` — f38 探测

---

**Confirmed at**: 2026-08-04
