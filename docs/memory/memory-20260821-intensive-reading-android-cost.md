# Memory: Intensive Reading Android + DeepSeek Cost

**Generated**: 2026-08-21 ~18:50 UTC+8
**Last updated**: 2026-08-22 ~14:10 UTC+8
**Project**: c:\jarvis
**Focus**: Intensive Reading 保留 Jarvis 内阅读；Pre-annotate / Pack 已因翻译质量差而删除

---

## Goal & Scope (required)

电脑 Jarvis 切 chunk，再对用户在页面上勾选的小说做全书预生成：每句中文释义（含简单句）+ 好词好句。Jarvis Passage 用下划线/底纹标出，单击查看。导出手机可打开的 pack（内联 `reader.html` + `book.pack.json`）。杂志和安卓 App 本身这次不做。预生成用本地 Ollama。

---

## Key Decisions (required)

1. **用量场景 = 仅自用**，自己付 API；不是对外产品。
2. **手机 LLM 功能 = 阅读正文 + 好词好句 Generate + 选词 Explain**。不要其它分析 Tab、不要杂志口语。
3. **强度 = 轻度**：每天 20–30 分钟，2–4 个 chunk 点好词好句，偶尔 Explain。
4. **同一 chunk 分析结果缓存**，不重复 Generate。
5. **推荐模型**：`deepseek-v4-flash` + **关闭 thinking**（vocab/explain 是抽取/讲解，不是难题推理）。不要默认 thinking（官方默认 enabled / high，reasoning 按 output 计费）。
6. **不要把整本书塞进 1M 上下文**：能算账，但好词好句质量会变差，也失去逐段精读节奏。
7. **RAG 不是精读主路径必需**：现有阅读 / 分析 / explain 只吃当前 chunk 文本；Qdrant 只是可选索引。手机用 SQLite 存 chunks + TOC 导航即可。
8. **Rejected: 第一版在安卓重做 PDF 段落启发式**：桌面端已踩过 pypdf 行折/段界坑。v1 应用 Jarvis 导出的 book pack（chunks + toc + analyses），手机只读。EPUB 可后做；PDF 解析最后做。
9. **句子分析 = 每句中文释义**（类似 Explain 的 Meaning and Sense），简单句也做；好词好句另标。
10. **生成时机 = Jarvis 一键预生成整本**；手机只读现成标注，不现算。
11. **这次做 Jarvis**：预生成 + Passage 可点下划线/底纹 + 导出标注文件。
12. **预生成 LLM = 本地 Ollama**（免费、全书较慢）。Rejected: DeepSeek Flash / 失败回退。
13. **选书在页面上由用户勾选小说**，不自动跑全部已导入书。杂志这次不做。
14. **对齐方案 A**：本地分句 + 每 chunk 两次 Ollama JSON；释义按序号，短语在原文查找。Rejected: 每句一次调用；LLM 改写 HTML。
15. **本次不做原生安卓 App**；pack 含内嵌 `reader.html`（Chrome `file://` 不能读旁边的 JSON）+ `book.pack.json` 给以后 App。
16. **视觉**：有句释 = 浅底纹；好词好句 = 下划线；点词优先于点句。划词 Explain 保留。
17. **落盘** `docs/books/{id}/overlays/{n}.json`，与 `analyses/` 分开。Rebuild 清空 overlays。
18. **计划审查修正（P0/P1 已写入计划）**：每 chunk 两次 Ollama；`format=json` + `think=false`；skip 绑定 learner_level；单击仅在 selection collapsed 时弹出；Task 6 测纯函数；align_vocab 归一引号；可 cancel；Python `layout_annotated_paragraph` 给 pack 测试用。
19. **实现已落地（Tasks 1–11）**：在 `main` 上继续（用户明确允许）；TDD 一任务一停；未 commit。
20. **Skip 键 = `learner_level`**：`status=done` 且 level 相同才跳过；`error` 永不跳过。
21. **Ollama 模型 = Analyze 同款**（`_ollama_settings` / `RAG_AGENT_MODEL`），不是 Explain 快模型。
22. **Overlay 是附加能力，不替代 Jarvis 内阅读**（2026-08-22）：修 `load_all_progress` NameError。
23. **Reversed: 保留 overlay/pack**：用户认为句释翻译很糟糕，删除 Pre-annotate 与 Pack（2026-08-22）。取消后台 job；删 overlay/pack 模块与 UI；保留 Passage / Analyze / Explain / 进度。磁盘 `docs/books/*/overlays/` 不删。

---

## Confirmed Assumptions (required)

- 切块规则对齐现有：杂志按篇；小说 TOC 定章后再 `_split_oversized_chunks(max_words=1200)`；`PASSAGE_WINDOW=12000` 字符。
- 定价来源：https://api-docs.deepseek.com/quick_start/pricing/ （2026-08-21）
- 峰时 01:00–04:00 和 06:00–10:00 UTC = 北京时间 09:00–12:00、14:00–18:00；晚间阅读为闲时（半价）。
- 本次不开始写安卓代码；安卓只消费导出的标注。
- 用户在 IR 书单页自己勾选要预生成的小说。
- 已生成的 chunk 不重复打 Ollama（同 learner_level）。
- 执行节奏：一次一个 Task，报告后等 continue。
- 不 commit，除非用户再要求。

---

## Constraints & Non-Goals (include when relevant)

- 不实现安卓 App。
- 杂志、其它分析 Tab、口语这次不做。
- 不把 `docs/books/` 内容提交 Git。
- 不改股票等其它模块。
- 不 commit 除非用户明确要求。

---

## Key Discoveries (required)

- 一次好词好句（非 thinking）：约 2k input（system ~0.4k 可 cache + passage ~1.6k miss）+ 约 3k output。Flash 闲时 ≈ **$0.0024 / 次**。
- 一次选词 Explain：约 0.8k in + 0.4k out。Flash 闲时 ≈ **$0.0004 / 次**。
- 轻度日用量（3×vocab + 5×explain）：Flash 闲时 ≈ **$0.01 / 天 ≈ $0.28 / 月 ≈ $3–4 / 年**。
- 一本 ~8 万词小说（~67 chunks）若每块都 Generate 一次 vocab ≈ **$0.16**；一期 Economist 量级（~86 chunks）≈ **$0.21**。
- 默认 thinking=high 大约把单次费用翻 2–3 倍，仍远低于「贵」；但手机延迟更差，应关掉。
- Pro 约为 Flash 的 3 倍，精读抽取不值得。
- 现有 `index_chunks_to_rag` 失败时阅读仍可用（见 `memory-20260814-intensive-reading-rag-index.md`）。
- Passage 段规则：`\n\s*\n` 分段，段内空白压成空格（`irRenderPassage`）。overlay 必须用 `display_paragraphs()` 对齐这段显示文本，否则 start/end 会偏。
- 分句不能 `re.split` 可变宽 lookbehind；扫描句末标点，`Mr./Mrs./…` 保护，收尾引号跟上一句。
- 假 LLM 不能用 `"vocab" in system.lower()`：university 文案含 **vocabulary**，会把句释调用误判成词表。应检测 vocab system 里的 `"exact substring"`。
- Flask 模板在 import 时加载；改 `index.html` 后必须重启 Jarvis。
- `tests/` 被 gitignore，本地跑 pytest；Passage/书单 UI 测试读 `index.html` 当文本契约。
- Chrome `file://` 不能 fetch 旁边的 JSON，所以 pack 的 `reader.html` 必须内联 JSON，且模板里不能出现 `fetch(`（契约测试会扫）。
- Overlay job 进程内单线程；重启后 meta `overlay.state=running` 视为 stale → idle。
- Cancel 在**当前 chunk 结束后**生效（`cancel_flag` 在下一 chunk 循环开头检查）。
- **2026-08-22 NameError**：`scripts/rag/routes/intensive_reading.py` 调用了 `load_all_progress` / `load_progress` / `save_progress`，但从未 `from intensive_reading.progress import ...`。`GET /api/intensive-reading/books` 一开书单页就 500。函数本身仍在 `progress.py`。Passage / Explain UI 还在 `index.html`，不是被 overlay 删掉。

---

## Runtime Evidence (include when relevant)

- `python -m pytest tests/test_intensive_reading_overlays.py tests/test_intensive_reading_overlay_api.py tests/test_intensive_reading_passage_ui.py tests/test_intensive_reading_overlay_ui.py -v` → **37 passed** (2026-08-21).
- RED: `tests/test_intensive_reading_progress_routes.py` → 2 failed; list books 500 `NameError: load_all_progress`; get book `NameError: load_progress` (2026-08-22).
- GREEN: `python -m pytest tests/test_intensive_reading_progress_routes.py tests/test_intensive_reading_analyze_routes.py tests/test_intensive_reading_overlay_api.py tests/test_intensive_reading_passage_ui.py -v` → **25 passed** (2026-08-22).

---

## Open Risks (include when relevant)

- DeepSeek 可调价；thinking 默认开启，若以后接云端必须显式 `thinking.type=disabled`。
- 安卓 APK 里硬编码 API Key 有泄露风险；自用可放本地加密存储，不要打包进发布包。
- 全书预生成对本地 Ollama 会很慢（每 chunk 两次 JSON，>30 句再分批 25）。
- 句释/词表质量依赖 Ollama 是否遵守 JSON；坏 JSON 写 `status=error`，skip 不会把它当完成。
- Pack 按钮在 Task 10 已接 `/pack.zip`；未重启 Jarvis 时旧进程没有该路由。

---

## Current State (required)

- **Working**: Pre-annotate / Pack 代码已删。书单 / Passage / Analyze / Explain / 进度仍在。回归 **22 passed**。
- **Pending**: 重启 Jarvis 后页面才会去掉 Running / Pack。未 commit。
- **Blocked**: 无

---

## Next Steps (required)

1. [ ] 重启 Jarvis，打开 IR 确认没有 Pre-annotate/Pack，仍能阅读
2. [ ] 用户给 TASK-ID 后再 Conventional Commit；未要求则不 commit

---

## Notes for Next Session (include when relevant)

- 相关旧记忆：`memory-20260728-intensive-reading.md`、`memory-20260814-intensive-reading-rag-index.md`、`memory-20260819-intensive-reading-paragraphs.md`
- 工作在 **main**（脏工作区）。另有无关改动：`daily_fetch.py` / `index.html` daily-fetch / `jarvis-start.log` — commit 时不要混进去。
- overlay JSON 可能仍在 `docs/books/01-into-the-wild-ade80c0e/overlays/`，阅读器不再读它们。

---

## References (required)

- `docs/plans/2026-08-21-intensive-reading-sentence-overlays.md` — 实现计划
- `scripts/rag/intensive_reading/sentences.py` — 显示分段 + 分句
- `scripts/rag/intensive_reading/overlay_store.py` — schema / align_vocab / layout_annotated_paragraph / 落盘
- `scripts/rag/intensive_reading/overlay_gen.py` — annotate_chunk_text / annotate_book / ollama_complete
- `scripts/rag/intensive_reading/overlay_job.py` — 后台 job / skip-meta / cancel
- `scripts/rag/intensive_reading/pack_export.py` — zip + 内联 reader
- `scripts/rag/intensive_reading/reader_template.html` — 离线阅读器
- `scripts/rag/intensive_reading/prompts.py` — overlay sentence/vocab prompts
- `scripts/rag/routes/intensive_reading.py` — overlay + pack 路由
- `scripts/rag/templates/index.html` — Passage spans / 书单工具栏
- `tests/test_intensive_reading_overlays.py`
- `tests/test_intensive_reading_overlay_api.py`
- `tests/test_intensive_reading_overlay_ui.py`
- `docs/memory/memory-20260728-intensive-reading.md`
- `docs/memory/memory-20260814-intensive-reading-rag-index.md`

---

**Confirmed at**: 2026-08-22
