# Memory: Intensive Reading RAG Index (stock config clash)

**Generated**: 2026-08-14 ~15:05 UTC+8
**Last updated**: 2026-08-14 ~15:05 UTC+8
**Project**: c:\jarvis
**Focus**: New Yorker / Economist 精读书籍 RAG 索引失败根因与修复

---

## Goal & Scope (required)

精读上传后书籍已切 chunk 并保存，但 RAG 向量索引失败。用户看到 `Ready: new_yorker.2026.08.10 — 59 chunks [failed] — Book saved but RAG indexing failed or skipped`。修复索引导入，使股票 `config` 占用期间仍能索引。

---

## Key Decisions (required)

1. **根因不是 New Yorker PDF/chunk**：59 chunks 已写入，`status: ready`。`[failed]` 是 `rag_status`。
2. **Economist 同样失败**：两边 `rag_error` 相同。Economist 能读是因为精读不依赖 Qdrant。
3. **方案 A**：`index_chunks_to_rag` 导入前强制把 `sys.modules['config']` 切回 `scripts/config.py`（对齐 `scanner._index_scan_report_to_rag`），导入后 restore。含 ImportError 重试以覆盖轮询竞态。
4. **Rejected: 只改 UI / 假装 Economist 成功**：两边 meta 都是 failed。

---

## Confirmed Assumptions (required)

- 精读阅读、分析、explain 不需要 RAG 成功。
- 股票路由 `@_with_stock_imports` 会把 `config` 换成 `scripts/stock/config.py`（无 `SNAPSHOT_PATH`）。
- 用户批准：修精读索引 + 新建本 memory 文件。

---

## Constraints & Non-Goals (include when relevant)

- 不改股票 config 切换机制本身。
- 不把 SNAPSHOT_PATH 加进 stock_config（会混淆两套配置）。
- 不改 chunking / New Yorker 解析。

---

## Key Discoveries (required)

- `meta.rag_error`: `cannot import name 'SNAPSHOT_PATH' from 'stock_config' (C:\jarvis\scripts\stock\config.py)`
- `index_chunks_to_rag` 内 `from config import SNAPSHOT_PATH` 与 `rag_engine` 顶层同样导入；`config` 被股票装饰器换成 `stock_config` 时失败。
- 股票扫描索引已有强制 RAG config + 5 次重试；精读索引没有。
- New Yorker: `docs/books/newyorker20260810-8355ce99/`（59 chunks）。Economist: `docs/books/theeconomist20260815-f16c6660/`（86 chunks，有 analyses）。

---

## Current State (required)

- **Working**: PDF ingest / chunk / 精读 UI；`index_chunks_to_rag` 导入前强制 RAG config + restore + ImportError 重试；单测 GREEN
- **Pending**: 对已有 New Yorker / Economist 点 Re-index；可选 code review
- **Blocked**: 无

---

## Next Steps (required)

1. [x] TDD：stock_config 占用时索引不应报 SNAPSHOT_PATH ImportError
2. [x] 实现强制 RAG config + restore + retry
3. [ ] 用户可对已有书点 Re-index 验证

---

## Notes for Next Session (include when relevant)

- 相关记忆：`memory-20260702-stock-module-fixes.md`（config 竞态）
- 书籍列表 UI：`rag_status !== 'ok'` 显示 `[failed]` 和 Re-index

---

## References (required)

- `scripts/rag/intensive_reading/ingest.py` — `index_chunks_to_rag`
- `scripts/rag/routes/stock.py` — `_with_stock_imports`
- `scripts/stock/scanner.py` — `_index_scan_report_to_rag` 参考实现
- `scripts/config.py` — RAG `SNAPSHOT_PATH`
- `scripts/stock/config.py` — 无 `SNAPSHOT_PATH`
- `docs/books/newyorker20260810-8355ce99/meta.json`
- `docs/books/theeconomist20260815-f16c6660/meta.json`

---

**Confirmed at**: 2026-08-14
