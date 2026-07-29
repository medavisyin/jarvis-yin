# Memory: Intensive Reading (英文精读)

**Generated**: 2026-07-28 ~16:43 UTC+8
**Last updated**: 2026-07-29 ~13:20 UTC+8
**Project**: c:\jarvis
**Focus**: Learning 工具栏新增 PDF/EPUB 精读功能（上传、RAG chunk、逐段分析、进度记忆）

---

## Goal & Scope (required)

在 Jarvis Learning 下新增 **Intensive Reading**：用户上传英文小说/杂志（PDF/EPUB）到 `C:\jarvis\docs\books`，切块入 RAG，在模态窗中逐段精读；本地 Ollama 用全英文讲解难点；用 conversation memory 按书名记进度。

---

## Key Decisions (required)

1. **阅读节奏**：显示当前 chunk →「Analyze」「Next」都常显，用户可选；不自动分析。
2. **Chunk 策略**：电子书约 1–2 页；杂志按一篇一文；上传时手动选类型。
3. **分析语言**：全英文；过滤过简单内容（~6000 词 / B2–C1）。
4. **进度存储**：conversation memory 结构化 fact（`metadata.kind=intensive_reading_progress`）。
5. **入口 UI**：Learning 工具栏 → modal（书单 + 上传 + 阅读区）。
6. **LLM**：本地 Ollama。
7. **实现路径**：Approach A — Modal + 专用 API `/api/intensive-reading/*`。
8. **EPUB**：不用 ebooklib；用 zipfile + BeautifulSoup（已有 bs4）。
9. **Rejected: 自动分析 / 本地 JSON 权威进度 / 中文讲解 / 独立全屏路由**。
10. **Review fixes applied (2026-07-28)**: Critical-1 path containment; Important-1..7; Minor-1..3.
11. **Multi-tab analysis (2026-07-29, approved)**: 右侧 Tab；点 Analyze 自动排队从「好词好句」起逐 Tab SSE；每 Tab 自有 Continue。
    - 小说：vocab | plot | character | narrator | culture | rhetoric | socratic
    - 杂志：vocab | claim_evidence | stance | cultural_cues | structure
    - API：`analysis_kind` + `GET /api/intensive-reading/tabs`

---

## Confirmed Assumptions (required)

- 存储目录：`C:\jarvis\docs\books`（`config.BOOKS_ROOT`）
- 格式：PDF + EPUB
- TOC chunk 导航时跳过
- 设计已批准并选择直接实现（无正式 plan 文档）

---

## Key Discoveries (required)

- EPUB 可用 stdlib zipfile + OPF spine + bs4 抽取，无需 ebooklib
- 阅读顺序权威源是每本书的 `chunks.json`；Qdrant 同步入库供 RAG
- 进度用 `memory.store.add_memory` + metadata 过滤，比纯语义检索可靠
- PDF `extract_book` 标题曾取 tempfile 名（`tmp…`）→ 应用上传文件名（`_title_from_sources`）
- `chunk_by_words` 不拆单段超大文本；用 `_split_text_by_max_words` / `_split_oversized_chunks`
- `index_chunks_to_rag` 返回 `(count, error)`；失败写 `rag_error`

---

## Current State (required)

- **Working**: 精读 + RAG/标题修复 + 多 Tab 分析（prompts/API/UI）已落地
- **Pending**: 用户刷新/重启 Jarvis 后验证排队 Analyze 与 Continue
- **Blocked**: 无

---

## Next Steps (required)

1. [ ] 重启 Jarvis，打开杂志/小说各一本点 Analyze，确认 Tab 集合与排队
2. [ ] 验证某 Tab Continue（passage overflow / gen truncate）
3. [ ] 可选 follow-up code review（`requesting-code-review`）

---

## Notes for Next Session

- 小说 7 Tab / 杂志 5 Tab 全跑完较慢（本地 Ollama × N）
- Re-index：`POST /api/intensive-reading/books/<id>/reindex`
- 测试：`pytest tests/test_intensive_reading_ingest_repair.py tests/test_intensive_reading_prompts_tabs.py -v`

---

## References (required)

- `scripts/rag/intensive_reading/prompts.py` — Tab specs + kind system prompts
- `scripts/rag/routes/intensive_reading.py` — analyze + tabs API
- `scripts/rag/templates/index.html` — reader right-side tabs UI
- `docs/books/` — book storage

---

**Confirmed at**: 2026-07-29 (multi-tab design approved; executing)
