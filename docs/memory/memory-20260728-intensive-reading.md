# Memory: Intensive Reading (英文精读)

**Generated**: 2026-07-28 ~16:43 UTC+8
**Last updated**: 2026-07-29 ~13:55 UTC+8
**Project**: c:\jarvis
**Focus**: Learning 工具栏新增 PDF/EPUB 精读功能（上传、RAG chunk、逐段分析、进度记忆）

---

## Goal & Scope (required)

在 Jarvis Learning 下新增 **Intensive Reading**：用户上传英文小说/杂志（PDF/EPUB）到 `C:\jarvis\docs\books`，切块入 RAG，在模态窗中逐段精读；本地 Ollama 用全英文讲解难点；用 conversation memory 按书名记进度。

---

## Key Decisions (required)

1. **阅读节奏**：显示当前 chunk；各 Tab 手动 Generate；Back/Next；不自动分析。
2. **Chunk 策略**：电子书约 1–2 页；杂志按一篇一文；上传时手动选类型。
3. **分析语言**：全英文；过滤过简单内容（~6000 词 / B2–C1）。
4. **进度存储**：conversation memory 结构化 fact（`metadata.kind=intensive_reading_progress`）。
5. **入口 UI**：Learning 工具栏 → modal（书单 + 上传 + 阅读区）。
6. **LLM**：本地 Ollama。
7. **实现路径**：Approach A — Modal + 专用 API `/api/intensive-reading/*`。
8. **EPUB**：不用 ebooklib；用 zipfile + BeautifulSoup（已有 bs4）。
9. **Rejected: 自动分析 / 本地 JSON 权威进度 / 中文讲解 / 独立全屏路由**。
10. **Review fixes applied (2026-07-28)**: Critical-1 path containment; Important-1..7; Minor-1..3.
11. **Multi-tab analysis (2026-07-29, approved)**: 右侧 Tab；按 kind 的 system context。
12. **Analysis cache (2026-07-29)**: `docs/books/{id}/analyses/{chunk}.json`；去掉顶部 Analyze；每 Tab **Generate**（可覆盖）+ **Continue**；Back/Next/再打开加载缓存。

---

## Confirmed Assumptions (required)

- 存储目录：`C:\jarvis\docs\books`（`config.BOOKS_ROOT`）
- 格式：PDF + EPUB；TOC 导航跳过
- 分析缓存不进 RAG；进度仍用 conversation memory

---

## Key Discoveries (required)

- 切到 `main` 会丢掉未合并的 `docs/books` → 后半段 Tab 报 Book not found；已 fast-forward 并回 main
- 分析结果按 chunk 落盘后，Back/Next 可恢复各 Tab

---

## Current State (required)

- **Working**: 精读 + 多 Tab + 本地 analysis 缓存 + Generate/Continue
- **Pending**: 用户重启 Jarvis 后验证 Generate 缓存与 Back/Next
- **Blocked**: 无

---

## Next Steps (required)

1. [ ] 重启 Jarvis，Generate 若干 Tab → Back/Next/重开确认缓存
2. [ ] 验证 Regenerate 覆盖与 Continue 写回
3. [ ] 可选 follow-up code review

---

## Notes for Next Session

- 小说 7 Tab / 杂志 5 Tab；需手动点各 Tab Generate（不再自动排队）
- 缓存 API：`GET/PUT /api/intensive-reading/books/<id>/chunks/<n>/analysis`
- Re-index：`POST /api/intensive-reading/books/<id>/reindex`
- 测试：`pytest tests/test_intensive_reading_analysis_cache.py tests/test_intensive_reading_analyze_routes.py -v`

---

## References (required)

- `scripts/rag/intensive_reading/analysis_cache.py` — disk cache
- `scripts/rag/intensive_reading/prompts.py` — Tab specs + kind system prompts
- `scripts/rag/routes/intensive_reading.py` — analyze + tabs + analysis cache API
- `scripts/rag/templates/index.html` — reader right-side tabs UI
- `docs/books/` — book storage + `analyses/`

---

**Confirmed at**: 2026-07-29 (analysis cache design approved; executing)
