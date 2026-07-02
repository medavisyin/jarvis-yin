# Memory: 统一扫描"右扫卡在 Layer 1"+ status 接口挂起修复

- **日期**: 2026-07-02
- **关联**: `docs/memory/memory-20260702-stock-module-fixes.md`（其 Pending 项"用户实测统一扫描"的后续）、`docs/memory/memory-20260702-unified-scanner-zero-picks.md`
- **症状**: "AI 股票推荐（左侧+右侧·共享数据）"前端卡在 `右侧交易扫描: Layer 1: 获取全市场实时行情并执行活跃度过滤...`。

## 根因（两个叠加）

1. **共享行情被重导入冲掉**：`unified_scanner` 旧实现用模块级全局 `set_shared_market_df(df)` 注入共享行情；但右扫启动前 `_safe_import("right_side_scanner")` 会 pop+重导入该模块，模块级 `_shared_market_df` 被重置回 `None` → 右扫线程读到 `None` → 回退到无 timeout 的 `ak.stock_zh_a_spot_em()` → 卡在 Layer 1。
2. **status 接口在扫描期间挂起**：`_with_stock_imports` 装饰器**每个请求**都 pop 并重导入全部 24 个 `_STOCK_MODULES`，与扫描线程的 `_safe_import`（扫描期间也在 pop+重导入）在 `sys.modules` / import lock 上竞争。实测：扫描运行时 `/api/stock/right_side/status` 挂 246s，`/api/health` 秒回；偶发 `KeyError('right_side_scanner')`。前端因此无法刷新，显示最后一次成功的 "Layer 1..." 状态 → 看似卡死，实则扫描已结束/在继续。

## 修复

### `scripts/stock/right_side_scanner.py` + `scripts/stock/scanner.py`
- `start_right_side_scan(use_deepseek, market_df=None)` / `start_scan(use_deepseek, market_df=None)`：新增 `market_df` 参数，经线程参数透传到 `_run_rs_scan_inner` / `_run_scan_inner`。
- `_run_rs_scan_thread(use_deepseek, market_df=None)` 直接转发 `market_df`（不再读模块级 `_shared_market_df`）；`_run_scan(market_df=None)` 同理。
- `set_shared_market_df`/`clear_shared_market_df` 保留作独立启动兜底，统一路径不再用。

### `scripts/stock/unified_scanner.py`
- `_fetch_shared_market_df()` 的 `df` 直接透传：`_sc.start_scan(use_deepseek, market_df=df)` 与 `_rss.start_right_side_scan(use_deepseek, market_df=df)`（含重试）。
- 移除 `set_shared_market_df` 注入块与 `_cleanup_shared_df()`。

### `scripts/rag/routes/stock.py`
- `_with_stock_imports` 改**非破坏式**：只切 `sys.modules['config']`（finally 恢复），不再 pop `_STOCK_MODULES`。stock 模块要么已用 stock config 加载（缓存 import 不重执行顶层），要么在切换后的 config 下首次加载。

## 验证
- 重启 agent.py（端口 18889）后跑统一扫描（use_deepseek=true）：25 次连续 status 轮询每次 0.08–0.17s，无挂起；扫描从 market 平滑推进到 left(layer2_enrich)。
- 右扫现在瞬间完成（started=ended 同秒，0 候选——Layer1 过滤对当日行情为空，属策略/参数问题非 bug）。
- 四文件 `py_compile` + ReadLints 通过。

## 关键教训
- **不要用模块级全局在"会被重导入的模块"间传共享数据**：`_safe_import`/`_ensure_stock_config` 在扫描期间会 pop+重导入 scanner/right_side_scanner，模块级全局会被重置。应改为参数透传，或挂 `sys`。
- **请求装饰器不要做与后台线程对称的"pop+重导入"**：两边同时改 `sys.modules` + 抢 import lock → status 轮询挂起/KeyError。装饰器只切 config 即可，重导入交给扫描线程的 `_safe_import`。

## 注意
- 右扫 Layer1 过滤当前对多数行情快照返回 0 候选（价格 3–100 / 涨跌幅 -1%~+7% / 换手≥1.5% / 成交额≥3000万 / 市值 20亿~500亿）。若需非空推荐，考虑放宽参数或检查单位归一化（`总市值` 万元→元 那段）。
- agent.py 必须重启才能加载 `routes/stock.py` 的装饰器改动（blueprint 只在启动时导入一次；scanner 模块才由 `_safe_import` 每次重导入）。

## 文档同步
已更新：`docs/stock-modules/unified_scanner.md`、`right_side_scanner.md`、`scanner.md`、`docs/implementation/stock/api-routes-impl.md`、`scanner-impl.md`。
