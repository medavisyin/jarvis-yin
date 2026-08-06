# Memory: Daily Fetch Voice Settings + Finance Impact Narration

**Generated**: 2026-08-03 ~14:27 UTC+8
**Last updated**: 2026-08-03 ~14:57 UTC+8
**Project**: c:\jarvis
**Focus**: Global 可选标准口音（非方言）+ Finance 语音加入影响解释

---

## Goal & Scope (required)

用户发现 Daily Fetch AI 音频虽为英文内容，听起来却是中国女声；默认中文 TTS 为陕西方言音色。需要：Global Settings 按语言提供标准口音选项；Finance 仅语音播报加入「对什么有影响」；设置作用于 AI / Finance / Knowledge 全部音频。

---

## Key Decisions (required)

1. **方案 A**：`audio_voice_zh` / `audio_voice_en` 存 `female|male`，映射固定 Edge 标准音色；不做完整 voice-ID 下拉。
2. **默认**：普通话女 + 美式女；禁止方言（替换 `zh-CN-shaanxi-XiaoniNeural`）；英文默认不用 `en-IN-*`。
3. **作用范围**：Daily Fetch AI + Finance + Knowledge Audio 共用同一套 Global voice。
4. **单人 vs 对话**：Global 性别只影响单人播报；双人对话固定双性别（标准普通话/美式），不跟 Global 走。
5. **Finance 解释**：只改语音旁白（`_generate_segmented_narrations` finance prompt）；文字报告不改。
6. **下一步**：同会话写正式实现计划（`writing-plans` standard），再实现。
7. **计划评审修订**：`_tts_to_mp3` 不接 Global 性别；`daily-fetch-impl.md` 必改；`scripts/output/generate-*.py` 明确 out of scope。

---

## Confirmed Assumptions (required)

- 影响句短而具体（事实 1–2 句 + 影响 1 句）；禁止长篇评论/预测口号。
- AI briefing prompt 保持「只报事实、不分析」。
- 沿用 Edge TTS + 现有 `.global_settings.json` / Global Settings UI。

---

## Constraints & Non-Goals (include when relevant)

- 不改 Finance 文字稿/过滤逻辑（除非为旁白生成必须）。
- 不做完整 Edge voice 目录浏览。
- 对话性别不可配（已确认接受）。

---

## Key Discoveries (required)

- 当前 `TTS_VOICE_ZH = zh-CN-shaanxi-XiaoniNeural`（陕西口音）；`TTS_VOICE_EN = en-IN-PrabhatNeural`（印度英语男声）。
- Finance 现有 prompt 明确禁止评论/分析，与需求相反，需单独翻转为「事实 + 短影响」。
- Settings 现状只有 `audio_lang_*`，无 voice/gender 字段；`tts_voice_for_lang` 仅按语言返回硬编码常量。

---

## Current State (required)

- **Working**: Tasks 1–5 已在 `feat/daily-fetch-voice-finance` 实现；相关单测 9 passed
- **Pending**: 手工验收（重启 Jarvis 听音色 + Finance 影响句）；可选 code review / commit
- **Blocked**: 无

---

## Next Steps (required)

1. [x] 写 `docs/plans/2026-08-03-daily-fetch-voice-finance.md`
2. [x] 执行计划 Tasks 1–5
3. [x] 单测（tts_voices + finance prompts）
4. [ ] 重启 Jarvis 手工验收 Global Voice + Finance 音频
5. [ ] 用户要求时再 commit

---

## Notes for Next Session (include when relevant)

- 计划路径：`docs/plans/2026-08-03-daily-fetch-voice-finance.md`
- 分支：`feat/daily-fetch-voice-finance`；先前 `fix/em-circuit-watchlist-scan` WIP stash：`wip em-circuit before voice-finance`
- Knowledge Audio 是对话路径 → 只吃固定双性别，不吃 Global 性别。
- `scripts/output/generate-*.py` 仍含旧音色，明确 out of scope。

---

## References (required)

- `docs/plans/2026-08-03-daily-fetch-voice-finance.md` — 实现计划
- `scripts/rag/tts_voices.py` — voice presets / resolve / fallback
- `scripts/rag/narration_prompts.py` — finance impact prompts
- `scripts/rag/routes/ai_news.py` — TTS wiring + segmented narrations
- `scripts/rag/agent.py` — `_GLOBAL_SETTINGS_DEFAULTS`
- `scripts/rag/templates/index.html` — Global Settings audio voice UI
- `scripts/rag/routes/daily_fetch.py` — `tts_voice_from_settings`
- `docs/implementation/personal/daily-fetch-impl.md` — 已更新 Configuration

---

**Confirmed at**: 2026-08-03
