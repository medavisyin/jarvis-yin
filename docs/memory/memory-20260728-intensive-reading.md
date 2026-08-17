# Memory: Intensive Reading (英文精读)

**Generated**: 2026-07-28 ~16:43 UTC+8
**Last updated**: 2026-08-17 ~18:00 UTC+8
**Project**: c:\jarvis
**Focus**: Learning 工具栏 PDF/EPUB 精读；小说目录定章切分 + Passage 阅读排版

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
20. **2026-08-17 范围**: 「message 区域」= 左侧 Passage（不是 Analysis、不是主聊天）。杂志现有切篇逻辑不动。先建议后批准设计，再写计划。
21. **小说 TOC 切分 = 方案 A（已批准）**: 目录定章 + 章内 `_split_oversized_chunks(max_words=1200)`。PDF 书签优先（章级，非全部叶子）→ 正文 Contents 页解析 → 否则保持 1–2 页。EPUB 以 spine section 为章界再切开。Chapters ▾ 跳到该章第一块。Rejected: B 一章一块；C 只改标题不改切分。
22. **Passage 排版整包（已批准）**: 衬线、18px、`max-width:38em` 居中、左对齐、暖暗色 `#d6d2c8` on `#16141a`、小说缩进/杂志段距。不加 A±/主题切换（第一版）。不改 Analysis、不改 Explain 的 `.ir-para` 结构。主字体见决策 30（原 Georgia 现为回退）。
23. **实现落在当前 `main`**: 工作树已有 quality-value / stock 等未提交改动；用户同意在 dirty `main` 上改 IR，不另开分支。
24. **2026-08-17 Re-index 不会改 Passage**: 用户对已有小说点 Re-index 后正文没变。根因：当时 Task 1–2 只加了切分函数，尚未接入 `build_chunks`；`reindex_book` 只重送 RAG。用户选继续 Task 2–8，**不**把 Re-index 改成从 original 重建。UI Re-index 仍只重送 RAG。
25. **Task 1–8 done (2026-08-17)**: 小说 `build_chunks` 已接 TOC；`toc.json` 章级折叠；`GET book` 始终带 `toc`；`rebuild_magazine_from_original` 接受 novel+magazine；Chapters ▾；Passage 阅读主题 CSS。
26. **Rejected: 把 UI Re-index 接到 `rebuild_magazine_from_original`**: 用户明确不要。旧小说要看章切分 → 重启 Jarvis 后 **重新上传**，或脚本调 rebuild。硬刷新只影响 CSS。
27. **Review cycle-1 applied (user-approved)**: Important-1–5。Follow-up Minor-1：章标题匹配用 `re.escape(key) + r"(?!\d)"`，避免 “Chapter 1” 命中 “Chapter 10”。用户确认后 **不再开下一轮 review**。
28. **Deferred (user did not select)**: cycle-1 Minor-1 Passage 测试未断言 `.ir-para`；Minor-2 Chapters ▾ 仍可能出现 `"Front matter"`；Minor-3 `_NON_CHAPTER_TITLE` 缺 Preface/Foreword/Introduction/Index/Appendix；Minor-4 标题后第一段仍缩进。Important-6 是流程：commit 时只 stage IR hunks。
29. **Reversed (partial): 「小说不动」rebuild / GET toc**: 杂志时代 `rebuild_magazine_from_original` 拒小说、`GET book` 仅杂志带 `toc`。2026-08-17 起 rebuild 接受 novel|magazine（未知类型 `ValueError`）；`GET book` 始终附 `toc`。杂志 `build_chunks` 分支仍不动。
30. **Passage 字体 = Literata（2026-08-17）**: 用户嫌 Georgia 不好看；选书籍感 + 本地嵌 woff2。Regular/Italic/Semibold 拉丁子集在 `scripts/rag/static/fonts/`；`@font-face` + `#irPassage` `Literata, Georgia, …`。Rejected: Google CDN、Source Serif 4、系统 Sitka/Cambria、无衬线。OFL 许可文件一并放入。看字体须 **重启 Jarvis**（`index.html` 启动时读入内存）再 Ctrl+F5。

---

## Confirmed Assumptions (required)

- 存储目录：`C:\jarvis\docs\books`（`config.BOOKS_ROOT`）
- 格式：PDF + EPUB；TOC 导航跳过
- 分析缓存不进 RAG；进度仍用 conversation memory
- Selection explain 不持久化；Esc / 点外部 / 换 chunk 关闭
- 杂志 `build_chunks` 杂志分支不改
- Re-index **不会**从 original 重切；旧小说保持旧切分直到 **re-upload** 或 `rebuild_magazine_from_original`
- Passage 第一版不加字号 A± / 米色纸主题；不改 `#irAnalysis`
- Passage 主字体 Literata（本地 woff2），Georgia 仅作回退
- 不要重开 Approach A vs B/C 或 Passage 主题讨论

---

## Constraints & Non-Goals

- 不把 UI Re-index 改成 rebuild（用户已拒）
- 不改杂志切篇逻辑
- 不 restyle Analysis；Explain 继续依赖 `#irPassage .ir-para`
- commit 未请求则不提交；若提交须只 stage IR 相关 hunks（`index.html` 另有 quality-value JS；`intensive_reading.py` 另有 speaking/analysis 未提交改动）

---

## Key Discoveries (required)

- 切到 `main` 会丢掉未合并的 `docs/books` → 后半段 Tab 报 Book not found；已 fast-forward 并回 main
- 分析结果按 chunk 落盘后，Back/Next 可恢复各 Tab
- Passage 已按 `\n\n` 渲成 `<p class="ir-para">`，前端用相邻段落拼 selection context 最准
- **2026-08-03 ~16:01**：`index.html` 被其它改动覆盖后，selection-explain 前端+后端+测试+memory 整段从工作区消失；用户报「选中无悬浮按钮」根因是**代码缺失**而非定位/CSS。已完整恢复。
- 小说 PDF 书签：`filter_novel_chapter_outline` 丢掉 Cover/Contents 等；若最浅层全是 Part/Book/Volume/卷/部 且下一层 ≥2 条，用子章。
- 正文 Contents：`_NOVEL_TOC_LINE` 允许 `Chapter 1: Dawn` / `Chapter 1. Dawn`；映射跳过 TOC 页、扫全文前 200 字找标题，否则 `printed-1`；映射页码非严格递增则丢弃 printed outline。
- EPUB：section=章，除非 `<2` 个 section，或 `len>15` 且中位词数 `<400` → `chunk_by_words`。
- `build_toc_entries(..., book_type=)`：小说把 `Title (1)/(2)` 折成该章第一块；杂志不折。
- Chapters ▾：≥80% 标题是 `Pages N-M` 则隐藏。跳到该章第一 sub-chunk。
- **Chapter 1 vs 10**：heading 匹配必须 `(?!\d)`，否则 “Chapter 1” 会命中 “Chapter 10”。
- `tests/` gitignored，本地仍跑 pytest。
- Flask `app = Flask(__name__)` 会从 `scripts/rag/static/` 提供 `/static/fonts/`；HTML 在 import 时读入内存，改 CSS 必须重启 Jarvis。Python 3.13 默认猜不出 `.woff2` MIME（`application/octet-stream`），Chrome 通常仍能加载。

---

## Runtime Evidence

- Novel + magazine + chunking subset：**50 passed**；Chapter-10 修复后子集 **37 passed**；Passage UI + selection-explain **16 passed**。完整 IR suite 在加 review 测试前曾 **61 passed**。
- 用户 Re-index 后 Passage 不变：当时 `build_chunks` 仍 `chunk_novel_pages(pages_per_chunk=2)`；且 Re-index 从不重抽 original。
- Literata 嵌入：`pytest tests/test_intensive_reading_passage_ui.py -v` → **7 passed**；woff2 magic `wOF2`。

---

## Open Risks

- 旧小说未 re-upload 前仍是 1–2 页切分，Chapters ▾ 因 Pages 标题 ≥80% 会隐藏。
- Deferred Minors：Front matter 可能进下拉；Preface 等未进 `_NON_CHAPTER_TITLE`；标题后首段仍缩进。
- Dirty `main`：IR 与 stock/QV/speaking 混在同一工作树；commit 必须按文件/hunk 拆开，且须 `git add scripts/rag/static/fonts/`。

---

## Current State (required)

- **Working**: 新上传小说走 TOC 定章 + 1200 词切开；Passage **Literata**（本地 woff2）/38em/暖暗色；小说缩进 vs 杂志段距；Chapters ▾ / Articles ▾；rebuild 允许小说。
- **Review**: Literata 嵌入 review 已出（[Review](568f7484-71b6-4088-a4a7-5e947aa8cfc0)）：无 Critical；Important-1..3、Minor-1..4 待用户分诊。
- **Pending**: 重启 Jarvis + Ctrl+F5 看 Literata；re-upload 看章切分；review 分诊；commit 时加入 `static/fonts/`。
- **Blocked**: 无

---

## Next Steps (required)

1. [ ] 重启 Jarvis 后 Ctrl+F5 看 Literata
2. [ ] 重新上传小说验证章切分（不要只点 Re-index）
3. [ ] 分诊 Literata review findings
4. [ ] 用户要求时再 commit（含 `scripts/rag/static/fonts/`，勿混 QV/stock）

---

## Notes for Next Session

- 不要重开 Approach A vs B/C、Passage 主题、或「Re-index 是否应 rebuild」。
- 看章切分：重启 Jarvis + **re-upload**。看 Literata：重启 Jarvis + Ctrl+F5（只硬刷新不够，HTML 在启动时读入）。
- Selection explain：`POST /api/intensive-reading/explain-selection`（SSE）；选择器仍是 `#irPassage .ir-para`。
- 重建小说：`rebuild_magazine_from_original(book_id, reindex_rag=False)`（函数名历史遗留，现接受 novel|magazine）。
- Commit 时不要混入 `scripts/stock/*`、quality-value JS、`jarvis-start.log`、`X/magbook-aaa111/`。

---

## References (required)

- `scripts/rag/intensive_reading/chunking.py` — `filter_novel_chapter_outline` / `chunk_novel_from_outline` / `outline_from_novel_contents`
- `scripts/rag/intensive_reading/ingest.py` — novel `build_chunks`、`build_toc_entries`、`rebuild_magazine_from_original`
- `scripts/rag/routes/intensive_reading.py` — GET book 始终附 `toc`（文件内另有无关 speaking 改动）
- `scripts/rag/templates/index.html` — Passage CSS + Literata @font-face + Chapters ▾（文件内另有无关 quality-value JS）
- `scripts/rag/static/fonts/` — Literata latin woff2 + OFL-Literata.txt
- `tests/test_intensive_reading_novel_toc.py` — 小说 TOC / ingest / rebuild
- `tests/test_intensive_reading_passage_ui.py` — HTML 契约
- `docs/plans/2026-08-17-intensive-reading-novel-toc-passage.md` — 已执行计划
- `docs/books/` — book storage + `analyses/`

---

**Confirmed at**: 2026-08-17 ~18:00 UTC+8 (Literata font; review in flight)
