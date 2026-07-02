# Memory: Jarvis 股票模块修复（Ollama/PDF/DeepSeek 情绪/统一扫描竞态）

**Generated**: 2026-07-02 09:33 (UTC+8)
**Last updated**: 2026-07-02 09:33 (UTC+8)
**Project**: c:\jarvis
**Focus**: 本会话对 A股分析/AI预测 与 AI 股票推荐（统一扫描）的 4 个 bug 修复

---

## Goal & Scope (required)

修复用户报告的股票模块问题：
1. 本地 Ollama 未启动时，A股分析 & AI预测 报 `HTTPConnectionPool ... WinError 10061`，整请求 500。
2. 导出 PDF 提示"暂无数据, 请先运行分析"，但 DeepSeek 实际有结果。
3. Ollama 未启动时 DeepSeek 预测结果与启用时差距很大（根因调查）。
4. 勾选 DeepSeek 时情绪分析改用 DeepSeek 打分，本地分析仍用 Ollama，两条路径互不依赖。
5. AI 股票推荐（左侧+右侧·共享数据）报 `cannot import name 'STOCK_DATA_DIR' from 'config'`。

---

## Key Decisions (required)

1. **Ollama 失败不中断整请求**：`/api/stock/analyze` mode=full 里把 `generate_prediction` 调用包进 try/except，失败时在 `prediction_report` 返回友好中文提示（含启动命令 + 建议改用 DeepSeek），其余分析结果照常返回。不采用"检测 ollama 可用性"前置方案，直接捕获更简单。
2. **DeepSeek 结果写入 PDF 缓存**：前端 `runStockAnalysis` 在 DeepSeek 成功后把 `d2.report` 作为 `deepseek_report` 合并进 `_pdfDataCache['stockAnalysis']`；本地分析失败时也缓存基础对象兜底。不改 PDF builder（`_build_stock_analysis` 已支持 `deepseek_report` 字段）。
3. **DeepSeek 情绪独立打分**：新增 `analyze_stock_sentiment_deepseek`（单次批量调用 DeepSeek 返回 JSON 数组打分），写入独立文件 `sentiment-deepseek.json`，与 Ollama 版 `sentiment.json` 互不覆盖。`_load_or_compute` 增加 `sentiment_provider` 参数，`generate_prediction_deepseek` 传 `"deepseek"`，本地 `generate_prediction` 不变。
4. **统一扫描 config 竞态用重试兜底**：不采用"扫描期间保持 stock 配置"（会破坏 RAG 路由对 `SNAPSHOT_PATH` 等独有属性的访问），而是在 `unified_scanner.py` 加 `_safe_import(name)`：导入前 `_ensure_stock_config()`，遇 `ImportError` 重试。start 路由 `finally` 只改回 RAG 配置一次，重试必成功。

---

## Confirmed Assumptions (required)

- RAG 配置 `scripts/config.py` 没有 `STOCK_DATA_DIR`/`OLLAMA_HOST`/`MODEL_USAGE`；stock 配置 `scripts/stock/config.py` 有，且通过 `importlib` 加载父 config 取 `JARVIS_ROOT`/`REPORTS_ROOT`。
- stock 配置没有 RAG 独有属性（`SNAPSHOT_PATH`/`KNOWLEDGE_ROOT`/`PROJECT_GRAPH_PATH`/`CHAT_SESSIONS_DIR` 等）→ 不能全局保持 stock 配置。
- `_with_stock_imports` 装饰器在路由结束时 `finally` 把 `sys.modules['config']` 恢复成进入前的 `prev_config`；这是统一扫描竞态的根源。
- `_build_stock_analysis`（stock_pdf.py）已按 `deepseek_report` 字段渲染"DeepSeek 汇总"板块，无需改 PDF builder。

---

## Constraints & Non-Goals (include when relevant)

- 不重构 `_with_stock_imports` 的 config 切换机制（影响面太大）。
- 不改 `scanner.py`/`right_side_scanner.py` 内部的运行时导入（其异常走 left/right 子状态，非本次报告的统一错误）。
- `call_deepseek` 固定开启 thinking 模式；DeepSeek 情绪打分用 `reasoning_effort="low"` + `max_tokens=2048` 压低开销，未新增禁用 thinking 的入口。

---

## Key Discoveries (required)

- **情绪分析是 DeepSeek 对 Ollama 敏感的唯一输入维度**：`sentiment.analyze_sentiment_single` 用 Ollama `qwen3:1.7b` 逐条打分；Ollama 关闭时 `sentiment.py:93-96` 兜底返回 `{score:0.0, reason:"分析失败"}`，导致 `sentiment.json` 全零、`top_positive/negative` 为空、`trend="stable"`。DeepSeek 路径 `_load_or_compute` 优先读这份脏 `sentiment.json`，所以 DeepSeek 看到的情绪维度塌缩成中性 → 结论偏移。技术面/基本面/XGBoost 不依赖 Ollama。
- **统一扫描 config 竞态时序**：start 路由 `_with_stock_imports` 记录 `prev_config=RAG`→换 stock→调 `start_unified_scan`（spawn 线程）→`finally` 恢复 RAG。后台线程 `_ensure_stock_config()` 设 stock 后，start 的 `finally` 可能在"线程已设 stock"与"线程首个 import"之间执行，把 config 改回 RAG → `import scan_cache/scanner/right_side_scanner` 顶层 `from config import STOCK_DATA_DIR` 失败。异常被 `_run_unified_inner` 的 `except` 捕获写入 `sys._unified_status["error"]`，前端 `pollUnifiedStatus` 显示 `错误:`。日志里无 traceback（被吞进 status）。
- **`_STOCK_MODULES` 已含 `right_side_scanner`/`scan_cache`/`unified_scanner`**（`scripts/rag/routes/stock.py:28-36`），会被装饰器 pop+重导入。
- `unified_scanner` 线程状态持久化在 `sys._unified_thread`/`sys._unified_status`；`right_side_scanner` 在 `sys._rs_scan_thread`；`scanner` 用模块级 `_scan_thread`（re-import 会重置为 None）。

---

## Runtime Evidence (include when relevant)

- `python -m py_compile scripts/stock/sentiment.py scripts/stock/llm_reasoning.py` → OK
- `python -m py_compile scripts/stock/unified_scanner.py` → OK
- ReadLints 全部通过
- 竞态为概率性，静态环境无法复现；重试机制确定性兜底

---

## Open Risks (include when relevant)

- `_safe_import` 重试间隔 0.3s × 5 次；若未来 start 路由 `finally` 之外出现新的 RAG-config 改回源（例如新增并发路由），重试仍可能失败。长期更稳的方案是在 start 路由内预导入子模块并把引用传入线程，但属较大重构。
- `scanner.py` 自身的 `/api/stock/scan/start`（非统一扫描）存在同类 config 竞态，其子线程运行时导入（如 `from llm_reasoning import generate_prediction_verdict`）理论上也可能踩到；本次未修（用户未报告，且其错误走 left 子状态）。

---

## Current State (required)

- **Working**: A股分析 Ollama 失败不再 500；DeepSeek 结果可导出 PDF；DeepSeek 路径用 DeepSeek 情绪打分；统一扫描 config 竞态由 `_safe_import` 兜底。
- **Pending**: 用户运行时验证统一扫描不再报 STOCK_DATA_DIR 错误。
- **Blocked**: 无。

---

## Next Steps (required)

1. [ ] 用户实测"AI 股票推荐（左侧+右侧·共享数据）"是否还报 config 错误。
2. [ ] 用户实测勾选 DeepSeek 时 DeepSeek 报告情绪维度是否真实（非全零）。
3. [ ] 视情况为 `scanner.py` 单独扫描路径补同样的 `_safe_import` 兜底。

---

## Notes for Next Session (include when relevant)

- 改 stock 模块导入相关逻辑时，务必记得 `_with_stock_imports` 会 pop 并重导入 `_STOCK_MODULES`，且 `finally` 恢复 `prev_config`；后台线程的导入需自行 `_ensure_stock_config` 或用 `_safe_import`。
- 两个情绪缓存文件不要混用：`sentiment.json`（Ollama，本地路径）/ `sentiment-deepseek.json`（DeepSeek 路径）。

---

## References (required)

- `scripts/rag/routes/stock.py:159-180` — `/api/stock/analyze` mode=full 的 Ollama try/except + 友好提示
- `scripts/rag/templates/index.html:3399-3446` — `runStockAnalysis` DeepSeek 结果合并进 `_pdfDataCache['stockAnalysis']`
- `scripts/stock/sentiment.py` — `_resolve_stock_name`/`_aggregate_sentiment`/`analyze_stock_sentiment`/`analyze_stock_sentiment_deepseek`
- `scripts/stock/llm_reasoning.py:21-58` — `_load_or_compute(sentiment_provider=)`；`:570` `generate_prediction_deepseek` 传 `"deepseek"`
- `scripts/stock/unified_scanner.py:222-244` — `_safe_import`；`_run_unified_inner`/`_fetch_shared_market_df`/`_cleanup_shared_df` 改用 `_safe_import`
- `scripts/stock/config.py:20-32` — stock config 加载父 config 取 `JARVIS_ROOT`/`REPORTS_ROOT`，定义 `STOCK_DATA_DIR`
- `scripts/config.py:39-48` — RAG 独有属性（证明不能全局保持 stock 配置）
