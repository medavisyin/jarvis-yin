# Memory: Daily Fetch Audio Follows Global Language

**Generated**: 2026-08-21 ~18:00 UTC+8
**Last updated**: 2026-08-27 ~11:30 UTC+8
**Project**: c:\jarvis
**Focus**: Daily Fetch AI/Finance 音频语言完全跟随 Global Settings

---

## Goal & Scope (required)

Run Today's Fetch 生成的 AI Briefing Audio 在 Global 设为中文时仍可能是英文。改为音频语言只读当前 Global Settings。

---

## Key Decisions (required)

1. **方案 A**：语言只读 Global；已有 MP3 仅在 sidecar 语言与当前 Global 一致时跳过；修复设置模块解析顺序。
2. **Rejected: 每次 Run Today's Fetch 都重生音频**：TTS 太慢。
3. **Rejected: 只修设置查找、仍跳过已有 MP3**：改语言后仍会播旧英文。
4. **→ EN / → 中文** 保留为快捷键：先写 Global 再重生，不当独立语言源。
5. **下一步**：同会话直接实现（不写 formal plan）。

---

## Confirmed Assumptions (required)

- Global Settings 的 `audio_lang_ai` / `audio_lang_finance` 是唯一语言源。
- 无 sidecar 的旧 MP3 视为语言未知，必须按当前 Global 重生。
- Recreate / continue（`only_steps`）仍强制重生，不走 skip。

---

## Key Discoveries (required)

- `_already_done("ai_audio")` 只要 `ai-briefing.mp3` 存在就跳过，不看语言。
- `_get_global_settings()` 优先 `sys.modules["agent"]`，而 Flask 实况在 `__main__`。Intensive Reading 的 `import agent` 会留下过期副本。
- 磁盘 `.global_settings.json` 里 `audio_lang_ai` 已是 `zh`。
- Daily Fetch 的 Translate 按钮会 POST `/api/settings` 并带 `lang_overrides`。

---

## Runtime Evidence (include when relevant)

- RED: `python -m pytest tests/test_daily_fetch_audio_lang.py -v` → 8 failed（helpers missing）
- GREEN: `python -m pytest tests/test_daily_fetch_audio_lang.py tests/test_audio_lang_finance_migration.py tests/test_finance_narration_prompts.py -v` → **22 passed**
- Review triage: ACCEPTED Important-1/2/3 + Minor-1/5 (applied). REJECTED Important-4, Minor-2/3/4.

---

## Current State (required)

- **Working**: sidecar skip + `__main__` 优先 + review 修复；2026-08-27：AI 中文音频先把 briefing 条目译成 `title_zh`/`summary_zh` 再播报（`briefing_translate.py`）。未 `translated` 时即使 sidecar 是 zh 也会重生成，避免旧英文 MP3 被跳过。
- **Pending**: 重启 Jarvis 后对今天的 AI Briefing 点 Recreate 手验
- **Blocked**: 无

---

## Next Steps (required)

1. [x] RED: `tests/test_daily_fetch_audio_lang.py`
2. [x] GREEN: sidecar + `__main__` 优先 + skip 逻辑
3. [x] 查明「默认中文仍出英文」：素材是英文 title/summary，小模型未真正改写；sidecar 记的是请求语言
4. [x] 先译后播：`tests/test_ai_briefing_translate.py` 5 passed（含 audio lang 合计 22 passed）
5. [ ] 重启 Jarvis，Recreate AI Briefing Audio 手验中文
6. [ ] code review

---

## Notes for Next Session (include when relevant)

- 相关旧记忆：`memory-20260803-daily-fetch-voice-finance.md`（音色，不是这次的语言 skip）
- 本会话还加载了 `memory-20260819-intensive-reading-paragraphs.md`，与本任务无关

---

## References (required)

- `scripts/rag/routes/daily_fetch.py` — `_get_global_settings`, `_already_done`, audio steps
- `scripts/rag/templates/index.html` — Run Today's Fetch / translate buttons
- `scripts/rag/agent.py` — `_GLOBAL_SETTINGS` / `/api/settings`
- `tests/test_daily_fetch_audio_lang.py`

---

**Confirmed at**: 2026-08-21 ~18:00 UTC+8
