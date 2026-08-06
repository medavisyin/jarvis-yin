# Memory: Stock Fetch Resilience (East Money throttle + backfill)

**Generated**: 2026-07-30 ~13:55 UTC+8
**Last updated**: 2026-07-30 ~13:55 UTC+8
**Project**: c:\jarvis
**Focus**: 统一扫描东财 RemoteDisconnected → 闸门节流 + 重试加长 + 资金流向补抓

---

## Goal & Scope (required)

降低资金流向/日线取数失败率，并在 Layer2 后对仍缺资金数据的票串行补抓一轮；宁可明显变慢。不放宽缺资金不买入门控。

---

## Key Decisions (required)

1. **Approach 1**：全局东财闸门（并发≤2 + 最小间隔）+ 重试加长 + Layer2 末尾补抓。
2. 资金流向 + 日线都走闸门；右侧 Layer2 `max_workers` 8→2。
3. 补抓前 `scan_cache.clear_ff`，避免缓存空结果挡重试。

---

## Confirmed Assumptions (required)

- 用户接受扫描明显变慢。
- A+B：降失败率 + 失败可恢复都要。

---

## Key Discoveries (required)

- 东财在突发并发下主动断连；已有 4 次退避仍不够。
- 空/失败的 ff 会被写入 `scan_cache`，不 clear 则补抓无效。

---

## Current State (required)

- **Working**: throttle / fetch_resilience / 接线；Important-1～4 + Minor-1/3 已修；单测 17 passed
- **Pending**: 重启 Jarvis 实测；可选 follow-up review
- **Blocked**: 无

---

## Next Steps (required)

1. [ ] 重启 Jarvis，跑统一扫描，对比断连与缺失比例
2. [ ] 若仍大量失败，可再把并发降到 1 / 间隔加到 1.5s+

---

## References (required)

- `scripts/stock/eastmoney_throttle.py`
- `scripts/stock/fetch_resilience.py`
- `scripts/stock/china_market_data.py` — fund flow retries
- `scripts/stock/fetch_market_data.py` — OHLCV retries + slot
- `tests/test_eastmoney_throttle.py`

---

**Confirmed at**: 2026-07-30 (Approach 1 approved; implementing)
