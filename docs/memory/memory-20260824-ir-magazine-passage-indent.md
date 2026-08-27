# Memory: Intensive Reading Magazine Passage Indent

**Generated**: 2026-08-24 ~11:20 UTC+8
**Last updated**: 2026-08-25 ~09:25 UTC+8
**Project**: c:\jarvis
**Focus**: Magazine Passage body paragraphs should match novel reading typography (first-line indent + paragraph gap)

---

## Goal & Scope (required)

Intensive Reading 杂志 chunk 渲在 Passage 里没有段首缩进，阅读感差。段落切分本身正确，不重建 chunk / 不重做 PDF 段落识别。只改展示层 CSS，让杂志正文与小说一致。

---

## Key Decisions (required)

1. **CSS-only**：段落分割基本正确，不需要 post-chunk 重新编排文本。
2. **排版 = 小说式**：首行缩进 `1.25em`，段间 `margin-bottom: 1em`。Rejected: 中文 2em 空两字；Rejected: 只加缩进并缩小杂志段距。
3. **合并选择器**：`#irPassage.ir-kind-novel .ir-para` 与 `#irPassage.ir-kind-magazine .ir-para` 共用同一规则，避免再漂移。
4. **标题不缩进**：`.ir-title` / `.ir-kicker` / `.ir-article-title` 保持 `text-indent:0`。
5. **不重处理已导入书**；不改切块、Analysis、Explain。
6. **Rejected: 重建段落 / LLM 重排**：用户确认切分 OK。
7. **跳过 brainstorming 完整多方案**：Fast-path CSS 设计获批准后直接实现。
8. **Live Jarvis 仍缓存旧 HTML**：`agent.py` 在进程启动时读入 `index.html`；须重启 Jarvis + Ctrl+F5 才能看到缩进。
9. **Passage Explain 两段式（2026-08-25）**：① `### 1. 本句意思` ② `### 2. 语境中的其他意思`（引申/暗示/语气 + 必要时一句其他义项；没有则整段省略）。只改左侧 Passage；右侧 Analysis Explain 仍是 `### 1. 含义与语境`。
10. **Explain 气泡朗读（2026-08-25）**：标题栏喇叭按钮，浏览器 `speechSynthesis` 读选中英文原文（en-US）。不走 edge-tts。关闭气泡即停止。

---

## Confirmed Assumptions (required)

- 范围仅杂志 Passage 正文；小说已是这套样式。
- UI Re-index 不接到 rebuild（沿用 2026-08-17 决策）。
- 未请求则不 commit。

---

## Constraints & Non-Goals (include when relevant)

- 不改杂志切篇逻辑。
- 不追 PDF 字体/分栏/页眉页脚。
- 不改 `#irAnalysis`。
- 不把 UI Re-index 改成 rebuild。

---

## Key Discoveries (required)

- 根因是 CSS 显式禁用杂志缩进：`#irPassage.ir-kind-magazine .ir-para{margin:0 0 0.9em;text-indent:0}`（小说已是 `1.25em` + `1em`）。
- `index.html` 在 `scripts/rag/agent.py` 模块加载时写入 `AGENT_HTML`；改模板后不重启进程，`:18889` 仍返回旧 CSS。
- 相关旧记忆：`memory-20260819-intensive-reading-paragraphs.md`（小说段间空行 + 缩进）；`memory-20260728-intensive-reading.md`（小说缩进 vs 杂志段距的原始决策，本次被杂志侧覆写为与小说一致）。

---

## Current State (required)

- **Working**: 源码 CSS 已合并；Explain/Analysis 默认简体中文（口语 Tab 仍英文）；已去掉「好词好句」语言下拉；39 项相关测试通过
- **Pending**: 用户 `jarvis-restart.bat /AGENT` + Ctrl+F5；各 Tab 需重新点 Generate（旧英文缓存保留）
- **Blocked**: 无

---

## Next Steps (required)

1. [ ] 重启 Jarvis 后打开一本杂志，确认正文 `.ir-para` 有首行缩进、标题/kicker 无缩进
2. [ ] Code review
3. [ ] 未请求则不 commit

---

## Notes for Next Session (include when relevant)

- 验证：Learning → Intensive Reading → 杂志 → Passage。标题行仍顶格，正文段首缩进。
- 不要把工作区里其它未提交改动（wiki/stock/toolbar）一并 review 或 commit。

---

## References (required)

- `scripts/rag/templates/index.html` — `#irPassage.ir-kind-magazine .ir-para` 与小说共用缩进规则
- `tests/test_intensive_reading_passage_ui.py` — `test_passage_novel_vs_magazine_para_rules`
- `scripts/rag/agent.py` — `AGENT_HTML` 启动时读入
- `docs/memory/memory-20260819-intensive-reading-paragraphs.md`
- `docs/memory/memory-20260728-intensive-reading.md`

---

**Confirmed at**: 2026-08-24 ~11:20 UTC+8
