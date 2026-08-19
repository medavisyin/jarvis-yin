# Memory: Intensive Reading Paragraph Display

**Generated**: 2026-08-19 ~12:00 UTC+8
**Last updated**: 2026-08-19 ~12:50 UTC+8
**Project**: c:\jarvis
**Focus**: Intensive Reading Passage 丢失 PDF 段落边界；段间空行 + 首行缩进

---

## Goal & Scope (required)

Intensive Reading 的 Passage 把多段文字连成一大块，看不出 PDF 里的段落起始。以《Then We Came to the End》Chapter 1 为例：`LAYOFFS WERE UPON US.` 和 `When Tom found out he was being let go` 都应各自开始一段。修所有书的段落识别，修好后重处理已导入书。

---

## Key Decisions (required)

1. **主要症状是段落换行丢失**（几段被挪成一大块），不是词句击碎，也不是全量排版还原。
2. **范围 = 全部 Intensive Reading 书**（这本是例子），不是只修一本。
3. **成功标准**：段与段空一行，并且每段首行缩进（接近纸书）。
4. **解析修好后重处理所有已导入书**，让现有 Passage 立刻正确。
5. **不做**：PDF 字体/分栏/页尺等全量视觉还原；不改其他模块。
6. **本会话加载了** `memory-20260818-price-prediction-watchlist-sync.md`，与本任务无关。相关旧记忆：`memory-20260728-intensive-reading.md`（Passage 按 `\n\n` 渲成 `.ir-para`；小说缩进 vs 杂志段距；UI Re-index 不 rebuild）。
8. **小说 TOC 不去重后半本同名章（2026-08-19）**：`build_toc_entries` 只折叠**连续**的 `Chapter 1 (1)/(2)`；`Returns and Departures` 之后再出现的 Chapter 1 另开一条。列表里允许两个 Chapter 1，不改名字。空白页本来就会在抽文本时跳过，不是抽取中断。Rejected: 加前缀 / Chapter 1 (2) 改名。

---

## Confirmed Assumptions (required)

- 用户用浏览器打开同一 PDF 时能清楚看到段落起始。
- 修的是段落识别 + Passage 展示，不是 Analysis / Explain。
- 重处理已导入书走 `rebuild_magazine_from_original`，不改 UI Re-index 按钮（沿用 2026-08-17 拒绝把 Re-index 接到 rebuild 的决策）。

---

## Constraints & Non-Goals (include when relevant)

- 不追 PDF 的字体、分栏、页眉页脚等排版。
- 不改股票/其它 Learning 模块。
- 未要求则不 commit。

---

## Key Discoveries (required)

- Passage 已按 `\n\n` 渲成 `<p class="ir-para">`（见 `memory-20260728-intensive-reading.md`）。若 PDF 抽取时丢掉段落空行，前端就无法分段。
- 小说 Passage CSS 已有首行缩进；杂志用段距。用户这次要求空行 + 首行缩进。
- 旧小说要看新切分：UI Re-index 只重送 RAG，需 `rebuild_magazine_from_original` 或重新上传。
- **根因（page 23 实测）**：pypdf 6.9.2 默认 `extract_text()` 用**单换行**同时表示行内折行和段落起始（`abstention.\nWhen Tom found out`）。`normalize_reading_text` 把所有 `(?<!\n)\n(?!\n)` 收成空格，真正段落消失。chunk 里仅剩的 `\n\n` 来自 `chunk_novel_pages` 的页拼接，所以分段发生在页界（还夹页码 `15 1`），而不是 PDF 段落。
- 行启发式在该页重建出 3 段：全大写章节提要；`LAYOFFS WERE UPON US.`；`When Tom found out he was being let go`。layout mode 会把词拆开（`W hen`、`ver y`），不能当正文。
- 小说 CSS 已有 `text-indent:1.25em`，但 `margin:0 0 0.28em` 几乎没有段间空行；已改为 `1em`。
- 页与页拼接仍可能在句中假分段（例如 `the guy to go` / `down there.`），因为 `chunk_novel_*` 用 `\n\n` 接页。未纳入本次设计。
- rebuild 会 `clear_book_analyses`：已导入书的右侧 Generate 缓存被清空，需重新 Generate。

---

## Current State (required)

- **Working**: PDF 段落重建已接入 `normalize_reading_text`；小说 Passage CSS 段间 `1em` + 首行缩进；8 本已导入书已 `rebuild_magazine_from_original`（跳过 tmp）。Chapter 1 chunk 6：`LAYOFFS WERE UPON US.` 与 `When Tom found out…` 已是不同段。
- **Pending**: 用户重启 Jarvis + Ctrl+F5 手验；code review
- **Blocked**: 无

---

## Next Steps (required)

1. [x] 诊断为何 `\n\n` / 段落边界丢失
2. [x] 设计修复并获批准
3. [x] 实现 + 重处理已导入书
4. [ ] 用户重启 Jarvis 后手验 Chapter 1
5. [ ] code review

---

## Notes for Next Session (include when relevant)

- 触发例子：《Then We Came to the End》Chapter 1 — `LAYOFFS WERE UPON US.` 与 `When Tom found out he was being let go`
- 书籍在 `C:\jarvis\docs\books`（gitignore，不进 GitHub）

---

## References (required)

- `docs/memory/memory-20260728-intensive-reading.md` — Passage CSS / `\n\n` / rebuild 约定
- `docs/memory/memory-20260814-intensive-reading-rag-index.md` — RAG 索引与 books 路径
- `scripts/rag/intensive_reading/ingest.py`
- `scripts/rag/intensive_reading/chunking.py`
- `scripts/rag/templates/index.html` — `#irPassage` / `.ir-para`
- `tests/test_intensive_reading_passage_ui.py`

---

**Confirmed at**: 2026-08-19 ~12:00 UTC+8
