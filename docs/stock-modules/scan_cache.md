# 扫描共享缓存 (scan_cache) — 详细功能文档

**文件路径**: `scripts/stock/scan_cache.py`
**最后更新**: 2026-07-01

---

## 1. 模块概述

- **核心职责**: 提供**线程安全**、**单次扫描生命周期**的内存缓存，存 `stock_fund_flow_signals`（主力资金）与 `fetch_daily_ohlcv`（K 线）结果。让统一扫描中左侧与右侧对**同一只股票**的 enrichment 数据只抓一次。
- **设计动机**: `unified_scanner` 编排左右侧扫描，两套逻辑都要 per-stock 调用资金流向与 OHLCV。若各自抓取，~60 只候选 × 2 套 = 重复网络请求翻倍且易触发数据源限流。共享缓存命中即复用。
- **生命周期**: 单次统一扫描开始时 `reset()` 清空；扫描期间累积；不持久化、不跨扫描保留。

---

## 2. 核心数据结构与 API

| 名称 | 类型 | 说明 |
|------|------|------|
| `_lock` | `threading.Lock` | 保护并发访问（Layer2 多线程 enrich） |
| `_ff` | `dict[symbol -> Any]` | 资金流向结果缓存 |
| `_ohlcv` | `dict[symbol -> bool]` | OHLCV 是否已抓取完成标记 |

| 函数 | 作用 |
|------|------|
| `reset()` | 清空 `_ff` 与 `_ohlcv`，开始一次新扫描 |
| `get_ff(symbol)` | 取资金流向缓存，无则 `None` |
| `set_ff(symbol, val)` | 写资金流向缓存 |
| `has_ff(symbol)` | 是否已缓存资金流向 |
| `ohlcv_done(symbol)` | OHLCV 是否已抓过 |
| `mark_ohlcv(symbol)` | 标记 OHLCV 已抓 |

所有读写均持 `_lock`，线程安全。

---

## 3. 调用约定（左右侧使用模式）

**左侧 `scanner._layer2_*`**:
```python
import scan_cache
cached = scan_cache.get_ff(sym)
if cached is not None:
    ff = cached
else:
    ff = cmd.stock_fund_flow_signals(sym)  # 含重试
    scan_cache.set_ff(sym, ff)
```

**右侧 `right_side_scanner.analyze_single`**:
```python
import scan_cache
cached = scan_cache.get_ff(sym)
if cached is not None:
    ff = cached
else:
    ff = cmd.stock_fund_flow_signals(sym)
    scan_cache.set_ff(sym, ff)
# OHLCV 同理：if scan_cache.ohlcv_done(sym): 复用已抓; else: fetch + mark_ohlcv(sym)
```

**统一扫描器** (`unified_scanner._run_unified_inner`):
```python
import scan_cache
scan_cache.reset()   # 清空上次缓存
# ... 注入共享 market_df, 依次跑左右侧, 各自 enrich 时命中即复用 ...
```

---

## 4. 注意事项

- **不跨扫描持久化**: `reset()` 由 `unified_scanner` 在每次扫描开头调用；独立跑左侧或右侧时不依赖本缓存（各自函数保留抓取回退）。
- **只缓存可复用的纯数据**: 资金流向 dict、OHLCV 抓取完成标记。不缓存派生得分（左右侧算分逻辑不同）。
- **失效策略**: 数据源偶发返回空时，缓存的是空结果而非 `None`——`has_ff` 仍为 `True`，下游需自行判空。未来可加 TTL 或"空结果不缓存"策略。
- **线程安全**: Layer2 若用线程池并发 enrich，本缓存的 `_lock` 保证并发读写安全。

---

## 5. 改进方向

- 支持空结果不缓存（避免一次失败永久命中空数据）。
- 加时间戳/TTL，防止单次扫描跨太久数据过期。
- 未来新增策略共享更多 enrichment（如基本面、情绪）时，扩展同类缓存项。
