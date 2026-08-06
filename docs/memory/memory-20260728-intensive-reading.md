# Memory: Intensive Reading (英文精读)

**Generated**: 2026-07-28 ~16:43 UTC+8
**Last updated**: 2026-08-03 ~20:45 UTC+8
**Project**: c:\jarvis
**Focus**: Learning 工具栏 PDF/EPUB 精读 + 选中 Explain + 杂志 TOC/Articles

---

## Goal & Scope (required)

在 Jarvis Learning 下提供 **Intensive Reading**：上传英文小说/杂志（PDF/EPUB）到 `C:\jarvis\docs\books`，切块入 RAG，模态窗逐段精读；本地 Ollama 全英文讲解。新增：正文鼠标选中词/句 → 旁侧 **Explain** 按钮 → 附近气泡流式解释（含段级语境）。

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
13. **Selection explain (2026-08-03, confirmed)**: 选中旁浮出 Explain → 附近气泡；全英文；标准深度（词义/句意 + 语法用法 + 语境影响）；语境 = 选中所在段 + 前后各一段（跨段选区用 intersectsNode 并集 ±1）；不落盘缓存；不改右侧多 Tab。用户曾跳过 brainstorming 直接实现。
14. **Rejected for selection explain**: 右侧临时 Tab / 写入现有分析区；中文或双语；短句-only 或整 chunk 作唯一 context。
15. **Review fixes for selection explain**: Important-1 hide on chunk load/error；Important-2 hide pop on new selection；Minor-1 multi-para context；Minor-2 max-length tests；Minor-3 block nav while explaining. Follow-up review: Ready.
16. **Magazine titles (2026-08-03)**: UI — meta `irChunkTitle` + 正文 `ir-article-title`（仅 magazine）。
17. **Hybrid magazine chunking (review Critical-1)**: EPUB spine section 若标题弱（TOC/封面/菜单）或正文过大，则在 section 内再跑 `chunk_magazine_text`；Wired 式一节一文保留 spine 标题。`rebuild_magazine_from_original(..., reindex_rag=False)` → `rag_status=stale`。小说不动。
18. **I-NEW-1/M-NEW-1/M-NEW-2 (2026-08-03)**: masthead 剥离 + 失败回退 `Article N`（不保留 PRICE）；ILLUSTRATION/PHOTOGRAPH 视为弱标题；EPUB 去重复 polish（仅 `build_chunks` 出口 polish）。
19. **Magazine TOC / Articles (2026-08-03, Approach 1 approved)**: PDF 有 outline → 叶子书签按页界切块；无 outline → Contributors/Contents 伪 outline（NY）或页首/稠密行标题启发式；落盘 `toc.json`；`GET book` 带 `toc` + `GET .../toc`；Passage 上方 **Articles ▾** 弹层跳转（仅杂志）。小说不动。重建杂志 `rag_status=stale`。

---

## Confirmed Assumptions (required)

- 存储目录：`C:\jarvis\docs\books`（`config.BOOKS_ROOT`）
- 格式：PDF + EPUB；TOC 导航跳过
- 分析缓存不进 RAG；进度仍用 conversation memory
- Selection explain 不持久化；Esc / 点外部 / 换 chunk 关闭

---

## Key Discoveries (required)

- 切到 `main` 会丢掉未合并的 `docs/books` → 后半段 Tab 报 Book not found；已 fast-forward 并回 main
- 分析结果按 chunk 落盘后，Back/Next 可恢复各 Tab
- Passage 已按 `\n\n` 渲成 `<p class="ir-para">`，前端用相邻段落拼 selection context 最准
- **2026-08-03 ~16:01**：`index.html` 被其它改动覆盖后，selection-explain 前端+后端+测试+memory 整段从工作区消失；用户报「选中无悬浮按钮」根因是**代码缺失**而非定位/CSS。已完整恢复。

---

## Current State (required)

- **Working**: 精读 + 多 Tab；selection explain；杂志标题 UI；bookmark/TOC 切块；Articles 弹层；4 本杂志已 rebuild（`rag_status=stale`）
- **Verified**: Economist 书签标题正确；NY Contributors 映射出 Cash and Carry / Into the Woods 等；toc 测试 13 passed
- **Pending**: 硬刷新目视 Articles 列表；可选 UI Re-index / RAG
- **Blocked**: 无

---

## Next Steps (required)

1. [ ] 重启 Jarvis，硬刷新：杂志打开后点 Passage 旁 Articles ▾，核对标题并跳转
2. [ ] 顺带验证 selection Explain 仍可用
3. [ ] 用户要求时再 commit

---

## Notes for Next Session

- Selection explain：`POST /api/intensive-reading/explain-selection`（SSE）
- Magazine TOC：`extract_pdf_outline`；`chunk_magazine_from_outline` / `chunk_magazine_by_page_headings`；`toc.json`；UI `irArticles*`
- 测试：`pytest tests/test_intensive_reading_magazine_toc.py tests/test_intensive_reading_magazine_titles.py`
- 重建：`python tmp/_rebuild_magazines_toc.py`（`--no-rag` 等价 `reindex_rag=False`）

---

## References (required)

- `scripts/rag/intensive_reading/prompts.py` — Tab + selection explain prompts
- `scripts/rag/routes/intensive_reading.py` — analyze + explain-selection
- `scripts/rag/templates/index.html` — reader + Explain 浮层
- `tests/test_intensive_reading_selection_explain.py` — prompt + route tests
- `docs/books/` — book storage + `analyses/`

---

**Confirmed at**: 2026-08-03 (restored after wipe; awaiting hard-refresh verify)
