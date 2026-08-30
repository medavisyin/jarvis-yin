# Memory: 周线策略回测卡死与缓存误判

**Generated**: 2026-08-30 17:25
**Last updated**: 2026-08-30 17:30 (cache freshness clamp shipped)
**Project**: c:\jarvis
**Focus**: 周线策略回测（周一买入、持有5日、5%止损）进度诊断与缓存可用性误判

---

## Goal & Scope (required)

用户在 UI「策略回测 (周一买入, 持有5日, 5%止损)」跑了约 2 小时，询问还要多久。诊断后决定停掉并修缓存判定，使本地日线可用于快速重跑。

---

## Key Decisions (required)

1. **不加载旧 memory，本会话从空白开始**：用户选 start fresh。
2. **停掉正在跑的回测并修缓存判定**：用户选 stop_and_fix，目标是以后用本地日线快速重跑。
3. **写入本 memory 文件**：用户确认。
4. **修复方案**：`_cache_usable` 把新鲜度参照日 clamp 为 `min(requested_end, today)`；真过期仍拒绝。用户批准后直接 TDD 执行。
5. **Rejected: 回测完全禁用网络**：未选；缺缓存/真过期仍走 `fetch_daily_ohlcv`。

---

## Confirmed Assumptions (required)

- 该 UI 回测对应 `/api/stock/weekly/backtest`，实现在 `scripts/stock/weekly_selector.py` 的 `backtest_weekly`。
- 回测参数：start=2023-01-01，end=2026-08-30，capital=1_000_000，universe≈5343。

---

## Key Discoveries (required)

- 约 2 小时后进度 `扫描 460~490 / 5343`，UI progress≈7–8%（扫描阶段只映射到 90%）。
- 实测约每 90 秒推进 10 只；按 2 小时均值约 4 只/分钟。剩余约 **12–21 小时**。
- 回测对每只股票调用 `_load_daily(..., short_fetch=False)`，缓存不可用时走 `fetch_daily_ohlcv`（akshare，最多 4 次、每次 30s 超时 + 退避）。
- **根因**：`fetch_end = end + 20 days`（2026-09-19）传进 `_cache_usable`。新鲜度要求末根 >= `ref_end - 10d`（即 2026-09-09）。今天是 2026-08-30，本地缓存最多到上周五 2026-08-28，**全市场缓存一律被判过期**，于是 5343 只全部联网。
- 停止接口已调用成功；状态变为 `stopped`（progress 仍约 8%）。停止信号在当前这只股票的网络请求结束后才生效。

---

## Runtime Evidence (include when relevant)

- `GET /api/stock/weekly/backtest/status`：`status=running, progress=7, step=扫描 460/5343` → 随后 470、480、490。
- `POST /api/stock/weekly/backtest/stop` 返回 `{"ok":true}`；再查 status=`stopped`。

---

## Current State (required)

- **Working**: 回测已停；`_cache_usable` 已 clamp 到 today；`tests/test_weekly_cache_usable.py` 2 passed。
- **Pending**: 需重启 agent 后新逻辑才生效；用户尚未重跑回测。
- **Blocked**: 无。

---

## Next Steps (required)

1. [x] TDD 修 `_cache_usable` 新鲜度 clamp。
2. [ ] 重启 agent 使新代码生效。
3. [ ] 用本地日线重跑 2023-01-01 ~ 2026-08-30 回测。

---

## Notes for Next Session (include when relevant)

- Agent 在 `http://localhost:18889`。改代码后需重启 agent 进程，内存里的 `_bt_status` 才会清掉，且新逻辑才会生效。
- 进度更新每 10 只一次：`(i+1) % 10 == 0`。

---

## References (required)

- `scripts/stock/weekly_selector.py` — `_cache_usable`（已 clamp 新鲜度到 today）
- `tests/test_weekly_cache_usable.py` — 未来 end_date 仍可用今日缓存；30 天过期仍拒绝
- `scripts/stock/fetch_market_data.py` — `fetch_daily_ohlcv`（30s 超时 × 4 次重试）
- `scripts/rag/routes/stock.py` — `/api/stock/weekly/backtest*`
- `scripts/rag/templates/index.html` — 「策略回测 (周一买入, 持有5日, 5%止损)」

---

**Confirmed at**: 2026-08-30 17:25
