# Memory: Intensive Reading Magazine Passage Indent

**Generated**: 2026-08-24 ~11:20 UTC+8
**Last updated**: 2026-08-31 ~11:30 UTC+8
**Project**: c:\jarvis
**Focus**: Intensive Reading UI/analysis: magazine indent, Explain/lang, novel 读后感 (Socratic tab)

---

## Goal & Scope (required)

Session now covers Intensive Reading follow-ups after magazine Passage indent. Current open work: novel Analysis **读后感** (replace Socratic three questions inside existing `socratic` tab). Magazine tabs, Passage, Explain, 口语 unchanged.

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
11. **Analysis 语言选择（2026-08-28）**：Generate 左侧「语言」中文/英文；默认中文；缓存按 `kind__level__lang` 分开。中文选中时不回退到英文旧缓存（那是 Tab 语言混杂的根因）。口语 Tab 仍英文，并隐藏该选择器。
12. **小说读后感（2026-08-31）**：不是新 tab。放进现有「苏格拉底提问」，内部 id 仍为 `socratic`（避免 cache-key 迁移）。标签改为 **读后感**。用户写口语化笔记（章节表述+感悟+单词用法），再点评述；模型跟当前 Analysis 语言回答。笔记+评述按 chunk 保存。
13. **Rejected: 新 kind `reflection`**：避免迁移旧 `socratic` 缓存。
14. **Rejected: 放在好词好句/情节**：用户要的是对话式评述，不是再生成一篇分析。
15. **Rejected: 保留三问**：tab 变成读后感优先，不再出苏格拉底问卷。

---

## Confirmed Assumptions (required)

- 范围仅杂志 Passage 正文；小说已是这套样式。
- UI Re-index 不接到 rebuild（沿用 2026-08-17 决策）。
- 未请求则不 commit。
- 读后感仅小说；杂志 tab 不变。
- 表述口语化欢迎；评述跟 `#irOutputLang`。
- 不改 Passage / Explain / 口语。

---

## Constraints & Non-Goals (include when relevant)

- 不改杂志切篇逻辑。
- 不追 PDF 字体/分栏/页眉页脚。
- 不把 UI Re-index 改成 rebuild。
- 读后感：不新增 analysis kind；不恢复苏格拉底三问；未请求不 commit。

---

## Key Discoveries (required)

- 根因是 CSS 显式禁用杂志缩进：`#irPassage.ir-kind-magazine .ir-para{margin:0 0 0.9em;text-indent:0}`（小说已是 `1.25em` + `1em`）。
- `index.html` 在 `scripts/rag/agent.py` 模块加载时写入 `AGENT_HTML`；改模板后不重启进程，`:18889` 仍返回旧 CSS。
- 相关旧记忆：`memory-20260819-intensive-reading-paragraphs.md`（小说段间空行 + 缩进）；`memory-20260728-intensive-reading.md`（小说缩进 vs 杂志段距的原始决策，本次被杂志侧覆写为与小说一致）。
- Analysis slot 缓存在 `docs/books/{id}/analyses/{chunk}.json`；`normalize_slot` 目前**丢掉未知字段**，所以 `reflection` 必须进 `empty_slot` + `normalize_slot`，否则 PUT 会静默抹掉笔记。
- 前端缓存 key 是 `kind__level__lang`（`irTabCacheKey`）。读后感笔记若只写在当前 lang slot，切中文/英文会看起来像笔记丢了。
- `irRunAnalyzeKind` 流式时对 `#irAnalysis` 赋 `textContent`，会拆掉 pane 里的 textarea。评述区必须写到子节点（如 `#irReflectionComment`），不能整盒覆盖。
- `irShowActiveAnalysis` 在 idle 且无 `text` 时把整盒换成 “Click Generate…”——读后感必须始终显示 textarea。
- `irRunAnalyzeKind` 的 `slotSnap` 是白名单拷贝，漏掉 `reflection` 会在评述保存时把笔记写成空串。
- `PASSAGE_WINDOW = 12000`；隐藏 Continue 后，超长 chapter 只评述第一窗，与其它 tab 同一限制。
- 旧 `socratic` 缓存里可能仍是三问正文；重新评述前会当评述显示。无现成测试锁定「苏格拉底提问」文案。

---

## Open Risks (include when relevant)

- 计划审阅（2026-08-31）发现 Critical/Important 缺口，见下方；尚未补进计划正文，也未开始实现。

---

## Current State (required)

- **Working**: 小说 **读后感**（id `socratic`）已实现并通过 53 项 IR 测试。Agent `:18889` 已重启。评述流式写入 `#irReflectionComment`；切语言 keepTab + 旧 key 持久化 + overwrite；打开书不 persist 空 slot（`speakingLoaded` 门闩）。
- **Pending**: 用户 Ctrl+F5 后在小说里写口语笔记并点「评述」做端到端确认
- **Blocked**: 无

---

## Next Steps (required)

1. [ ] Ctrl+F5 打开小说 → 读后感：写笔记、评述、刷新仍在、切语言笔记不丢、换书不抹掉旧笔记
2. [ ] 未请求则不 commit

---

## Notes for Next Session (include when relevant)

- UI 改动必须重启 Agent（`:18889`），不要只看 `:18888`。
- 不要把工作区里其它未提交改动（wiki/stock/toolbar/platform-updates）一并 review 或 commit。
- 读后感实现时对照口语 pane：`irCaptureSpeakingOral` + blur persist；读后感应有对等的 `irCaptureReflection`，在 tab/chunk/语言切换/评述前调用。

---

## References (required)

- `scripts/rag/templates/index.html` — IR UI（tabs、`irShowActiveAnalysis`、`irRunAnalyzeKind`、`irPersistSlot`）
- `scripts/rag/intensive_reading/prompts.py` — `NOVEL_TABS` / `_SYSTEM_SOCRATIC` / `analysis_user_message`
- `scripts/rag/intensive_reading/analysis_cache.py` — `empty_slot` / `normalize_slot`
- `scripts/rag/routes/intensive_reading.py` — `/api/intensive-reading/analyze`
- `docs/plans/2026-08-31-intensive-reading-novel-reflection.md` — 读后感计划
- `tests/test_intensive_reading_passage_ui.py`
- `scripts/rag/agent.py` — `AGENT_HTML` 启动时读入
- `docs/memory/memory-20260819-intensive-reading-paragraphs.md`
- `docs/memory/memory-20260728-intensive-reading.md`

---

**Confirmed at**: 2026-08-31 ~11:30 UTC+8
