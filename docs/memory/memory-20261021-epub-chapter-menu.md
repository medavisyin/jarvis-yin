# Memory: EPUB 章节菜单只有书名

**Generated**: 2026-10-21 20:00
**Last updated**: 2026-10-21 20:40
**Project**: c:\jarvis
**Focus**: 网页精读 EPUB 的 Chapters 菜单用了文档标题，整本书被收成几项

---

## Goal & Scope (required)

网页 Reading 里，新上传的 EPUB 在 Chapters 里几乎不能按章跳。Simply Said 有 80 段、正文 19 章，菜单只有 3 项。用户要求查原因，然后改导入并用正文章名重切这本书。

---

## Key Decisions (required)

1. **章名用正文里的第一个 h1/h2/h3**（2026-10-21）：`<head><title>` 通常是书名，而且在文档里更靠前。没有正文标题时才用文档标题，再退到文件名、书名。
2. **Rejected: 空白的第一个标题再去找后面的标题**。空标题按现契约退回文档标题。查看意见里的「第一个非空标题」没有采用。
3. **重切 Simply Said，阅读位置改到 Section One**（chunk_index 6，页面显示 7/80）。旧的 2/80 在新分段里对不上同一句。RAG 没有重做，状态是 stale；这本书原先索引就因文件占用失败。
4. **查看范围**（2026-10-21）：根因、只有文档标题的书会不会被改坏、边界、测试。用户确认后做了代码查看。
5. **Minor-1 和 Minor-2 都做**（2026-10-21）：补了空标题、缺 body、嵌套 span、nav 的测试。nav 里的标题只在后面还有正文章名时跳过。空的第一个标题仍退回文档标题，不改去找后面的标题。
6. **复查后又收紧了两条测试**（2026-10-21）：nav 内是 h1、后面的章名是 h2；两个 nav 时仍取第一个 Contents。没改选标题的代码。`tests/test_intensive_reading_chunking.py` 14 项通过。
7. **接受现在的结果，不再查第三轮**（2026-10-21）。后补的测试没有再经过一次代码查看。

---

## Confirmed Assumptions (required)

- 用户说的 chapter 是网页阅读页的 Chapters 菜单。
- 菜单把相邻的同名段收成一行，`(1)` `(2)` 这类后缀不单独显示。
- 书库里没有 Think Faster, Talk Smarter，也没有 85 段的书。当天新进来的只有 Simply Said。

---

## Constraints & Non-Goals (include when relevant)

- 不改已经导入、没有重切的其他书。
- 封面文件没有章名时，仍可能显示错误的文档标题。Simply Said 第一项仍是 The Happy, Healthy Nonprofit。

---

## Key Discoveries (required)

- `extract_epub_sections` 原来用文档顺序找 `h1/h2/h3/title`。`<title>` 在 `<head>` 里，先被选中。Simply Said 几乎每个文件的文档标题都是书名，封面是 The Happy, Healthy Nonprofit，许可协议是 Wiley Template v5.0。
- 正文章名在 h1 上，例如 `CHAPTER 1 What Do You Mean by That? Conveying a Clear Message`。spine 里有 c01–c19 和 p01–p05。
- 重切后菜单 36 项，含 CHAPTER 1–19 和五个 SECTION。
- 查看结论可以合并。没有 Critical / Important。Minor-1：测试没锁住空标题、缺 body、嵌套 span。Minor-2：标题查找不跳过 `nav`，而正文提取会删掉 `nav`。Simply Said 里只有 `OPS/toc.xhtml` 的标题在 nav 里，文档标题为空，标题文本是 Contents。

---

## Current State (required)

- **Working**: 新 EPUB 导入用正文章名。nav 后面还有章名时不用 nav 里的标题。Simply Said 已重切，刷新阅读页能看到各章。`tests/test_intensive_reading_chunking.py` 14 项通过。
- **Pending**: 无。用户接受现在的结果。后补的两条测试没有再查一轮。
- **Blocked**: 无。

---

## Next Steps (required)

1. [x] 用户决定两条都做。测试已补，nav 跳过已实现。
2. [x] 复查过一次。后又补了两条更紧的测试，14 项通过。
3. [x] 用户接受现在的结果，不再查第三轮。
4. [ ] Think Faster 若要同样的菜单，需要重新上传。

---

## References (required)

- `scripts/rag/intensive_reading/extract.py` — EPUB 节标题
- `scripts/rag/intensive_reading/ingest.py` — `build_toc_entries` 合并同名段；`rebuild_magazine_from_original`
- `tests/test_intensive_reading_chunking.py` — `test_epub_section_title_uses_body_heading_not_document_title`
- `web/src/pages/ReadingPage.tsx` — Chapters 菜单
- `docs/books/simply-said-communicating-better-at-work-and-beyond-b84a44f0/` — 已重切的书

---

**Confirmed at**: 2026-10-21 20:00
