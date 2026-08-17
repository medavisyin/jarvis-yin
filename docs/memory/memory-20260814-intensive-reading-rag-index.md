# Memory: Intensive Reading RAG Index (stock config clash)

**Generated**: 2026-08-14 ~15:05 UTC+8
**Last updated**: 2026-08-14 ~17:00 UTC+8
**Project**: c:\jarvis
**Focus**: 精读 RAG 索引修复；`docs/books` 仅本地、不推 GitHub

---

## Goal & Scope (required)

精读上传后书籍已切 chunk 并保存，但 RAG 向量索引失败。用户看到 `Ready: new_yorker.2026.08.10 — 59 chunks [failed] — Book saved but RAG indexing failed or skipped`。修复索引导入，使股票 `config` 占用期间仍能索引。

---

## Key Decisions (required)

1. **根因不是 New Yorker PDF/chunk**：59 chunks 已写入，`status: ready`。`[failed]` 是 `rag_status`。
2. **Economist 同样失败**：两边 `rag_error` 相同。Economist 能读是因为精读不依赖 Qdrant。
3. **方案 A**：`index_chunks_to_rag` 导入前强制把 `sys.modules['config']` 切回 `scripts/config.py`（对齐 `scanner._index_scan_report_to_rag`），导入后 restore。含 ImportError 重试以覆盖轮询竞态。
4. **Rejected: 只改 UI / 假装 Economist 成功**：两边 meta 都是 failed。
5. **`docs/books/` 不进 GitHub `main`（2026-08-14）**：用户批准方案 A。文件**原地**留在 `C:\jarvis\docs\books`（`BOOKS_ROOT` 不变），`.gitignore` 忽略 `docs/books/**`，保留 `docs/books/.gitkeep`。`git rm -r --cached docs/books/` 取消跟踪、不删本地。已 commit + push `11c140f`。**未** rewrite history / force-push，旧 commit 里仍有 PDF/EPUB。

---

## Confirmed Assumptions (required)

- 精读阅读、分析、explain 不需要 RAG 成功。
- 股票路由 `@_with_stock_imports` 会把 `config` 换成 `scripts/stock/config.py`（无 `SNAPSHOT_PATH`）。
- 用户批准：修精读索引 + 新建本 memory 文件。
- 精读工作目录就是 `C:\jarvis\docs\books`；不要再搬到别的路径。
- 新 clone 的机器没有书，需重新上传。

---

## Constraints & Non-Goals (include when relevant)

- 不改股票 config 切换机制本身。
- 不把 SNAPSHOT_PATH 加进 stock_config（会混淆两套配置）。
- 不改 chunking / New Yorker 解析。
- 不把 `docs/books/` 内容提交或 push；不要 `git rm` 而不带 `--cached`（会删本地书）。
- 不 force-push 清 git 历史，除非用户明确要求。

---

## Key Discoveries (required)

- `meta.rag_error`: `cannot import name 'SNAPSHOT_PATH' from 'stock_config' (C:\jarvis\scripts\stock\config.py)`
- `index_chunks_to_rag` 内 `from config import SNAPSHOT_PATH` 与 `rag_engine` 顶层同样导入；`config` 被股票装饰器换成 `stock_config` 时失败。
- 股票扫描索引已有强制 RAG config + 5 次重试；精读索引没有。
- New Yorker: `docs/books/newyorker20260810-8355ce99/`（59 chunks）。Economist: `docs/books/theeconomist20260815-f16c6660/`（86 chunks，有 analyses）。
- 2026-08-14 本地仍有 6 本书（meta + original + chunks）；Git 只跟踪 `docs/books/.gitkeep`。push：`fe0be06..11c140f` → `origin/main`。

---

## Current State (required)

- **Working**: PDF ingest / chunk / 精读 UI；`index_chunks_to_rag` 导入前强制 RAG config + restore + ImportError 重试；`docs/books` 仅本地（gitignore + `11c140f` on `origin/main`）
- **Pending**: 对已有 New Yorker / Economist 点 Re-index；可选 code review
- **Blocked**: 无

---

## Next Steps (required)

1. [x] TDD：stock_config 占用时索引不应报 SNAPSHOT_PATH ImportError
2. [x] 实现强制 RAG config + restore + retry
3. [x] `docs/books` gitignore + untrack + push `origin/main`（`11c140f`）
4. [ ] 用户可对已有书点 Re-index 验证

---

## Notes for Next Session (include when relevant)

- 相关记忆：`memory-20260702-stock-module-fixes.md`（config 竞态）
- 书籍列表 UI：`rag_status !== 'ok'` 显示 `[failed]` 和 Re-index
- 改书籍路径或 `git rm docs/books` 时必须带 `--cached`；应用读 `scripts/config.py` 的 `BOOKS_ROOT`

---

## References (required)

- `scripts/rag/intensive_reading/ingest.py` — `index_chunks_to_rag`
- `scripts/rag/routes/stock.py` — `_with_stock_imports`
- `scripts/stock/scanner.py` — `_index_scan_report_to_rag` 参考实现
- `scripts/config.py` — RAG `SNAPSHOT_PATH`
- `scripts/stock/config.py` — 无 `SNAPSHOT_PATH`
- `.gitignore` — `docs/books/**` + `!docs/books/.gitkeep`
- `docs/books/.gitkeep` — 仓库里唯一跟踪的 books 文件
- `scripts/config.py` — `BOOKS_ROOT = .../docs/books`
- `docs/books/newyorker20260810-8355ce99/meta.json`（本地 only）
- `docs/books/theeconomist20260815-f16c6660/meta.json`（本地 only）

---

**Confirmed at**: 2026-08-14
