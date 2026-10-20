# Memory: Passage 阅读全文

**Generated**: 2026-10-20 11:10
**Last updated**: 2026-10-20 13:35
**Project**: c:\jarvis
**Focus**: 网页精读每一页 Passage 旁的「阅读全文」，浏览器 / Edge / MiMo 可选

---

## Goal & Scope

在网页阅读页（`web/src/pages/ReadingPage.tsx`）每一页 Passage 顶栏，「Passage」旁边加「阅读全文」。读当前这一页正文，不读整篇文章、不读选中的词句。

设置里已有引擎 Edge / MiMo、Voice EN、Voice ZH（各为男女声二选一）、MiMo Style。这些在 Passage 里也能改。打开时默认跟设置。浏览器朗读是第三种引擎，一点就出声。

---

## Key Decisions

1. **三种引擎都放在 Passage 里**（2026-10-20）：浏览器马上读、Edge（本机 edge-tts）、MiMo。Rejected: 引擎只跟设置、Passage 里只改声音。
2. **只读当前页**。按段合成；Edge / MiMo 第一段好了就开读，后面接着生成。浏览器用系统语音，不等服务器。
3. **语言看这一页正文**：英文为主用 Voice EN，中文为主用 Voice ZH。两个男女声都留在顶栏。Style 只在 MiMo 时可选。Rejected: 顶栏再加手动 EN/ZH 开关。
4. **Passage 里的选择只在这次阅读有效，不写回设置**，避免改到日报和财经音频。Rejected: 一改就写回全局设置。
5. **另写本记忆文件**，不改 `memory-20261011-reading-comfort.md`（那份是手机阅读显示）。
6. **理解摘要已确认**（2026-10-20）：刷新或重开后回到设置默认；浏览器匹配不到对应男女声时用系统默认声；再点一次停止。
7. **做法选 A**（2026-10-20）：页面按段落切开，调现有朗读接口，第一段好了就播，同时预取下一段。浏览器不走服务器。Rejected: 服务器流式推整页音频；Rejected: 先用浏览器出声再切到 Edge / MiMo。
8. **顶栏**（2026-10-20）：「Passage」旁是「阅读全文」，朗读中变为「停止」。同一行：引擎（浏览器 / Edge / MiMo）、Voice EN、Voice ZH；Style 仅 MiMo。窄屏换行。章节按钮和「选中词句后点解释」不动。默认从设置读一次，只留在这一页状态。不写 localStorage。翻页保持声音选择，但停掉正在读的声音。
9. **播放**（2026-10-20）：汉字多于英文字母用 Voice ZH，否则 Voice EN。空页不读。浏览器整页一次读，按语言匹配系统声，匹配不到男女声就用该语言第一个，再没有用系统默认。Edge / MiMo 按段切，超过约 500 字再按句切，仍超过就硬切。段间不加 0.5 秒空白。语速保持现有慢速（-25%）。失败就停并显示原因，不换引擎。换页、换引擎或换声音时停，不自动重读。
10. **接口**（2026-10-20）：仍用 `POST /api/intensive-reading/speak`。可选 `engine`、`lang`、`gender`、`style`、`pad`。`pad: false` 时正文原样合成，不加 0.5 秒空白，也不加句点。不写回设置。Edge 按语言和男女声选现有声音。MiMo 传了 gender 时英文男 Dean、女 Mia，中文男白桦、女默认；Style 只加在正文前。没传 gender 的旧请求不变。非法 engine、lang、gender、style 返回 400。解释窗口仍只传正文和语速。
12. **三轮查看后接受现状**（2026-10-20）。最后改了空页：点「阅读全文」要等确认有正文、并且即将开始，才挡住设置回填。测试锁住页面不再用 `readGen` 判断。用户不再开第四轮查看。

---

## Confirmed Assumptions

- 「本地 TTS」就是设置里的 Edge，不是另一套新引擎。
- 现有解释窗口的「朗读」仍只读选中词句，这条不动。
- 现有 `/api/intensive-reading/speak` 单次最多 2000 字；全文朗读要分段，不能一次把整页塞进去。

---

## Constraints & Non-Goals

- 不把 Passage 里的引擎、声音、Style 写进全局设置。
- 不读整章或整篇，只读当前页正文。
- 不改手机阅读页。

---

## Key Discoveries

- Passage 顶栏在 `web/src/pages/ReadingPage.tsx`，文案是「Passage · 选中词句后点「解释」」。
- 设置音频在 `web/src/pages/SettingsPage.tsx`：`audio_engine`（edge / mimo）、`audio_voice_en`、`audio_voice_zh`（female / male）、`audio_mimo_style`。Style 只在引擎为 MiMo 时出现。
- 选中词句朗读在 `web/src/features/reading/ExplainPopover.tsx`：先请求 `/api/intensive-reading/speak`，失败才用 `speechSynthesis`。
- 服务端 `scripts/rag/routes/intensive_reading.py` 的 speak 按全局 `audio_engine` 走 Edge 或 MiMo，英文声只读 `audio_voice_en`。`validate_speak_text` 上限 2000 字（`scripts/rag/intensive_reading/speak.py`）。

---

## Current State

- **Working**: 网页每一页 Passage 旁有「阅读全文」。浏览器马上读；Edge / MiMo 分段，第一段好了就播。顶栏可选引擎、Voice EN、Voice ZH，Style 只在 MiMo。打开时跟设置，不写回设置。三轮查看后的问题都已改。前端 26 项通过，朗读接口相关 20 项通过。
- **Pending**: 还没有在打开的阅读页上点过按钮。
- **Blocked**: 无。

---

## Next Steps

1. [x] 用户确认理解摘要。
2. [x] 进入 `brainstorming`，做法选页面分段预取。
3. [x] 接口设计已确认。直接实现，不写计划。
4. [x] 实现：`PassageSpeakBar`、`passageSpeak.ts`、`POST /api/intensive-reading/speak` 可选字段。
5. [x] 代码查看完成。八条都改了：预取失败被接住、离开页面停播、浏览器等声音列表、补测试、中文不加空格、停止时清错误、设置晚到不覆盖、男声按单词匹配。
6. [x] 三轮查看结束。用户接受现在的结果。空页不再提前挡住设置。还没在阅读页上试听。

---

## References

- `web/src/pages/ReadingPage.tsx` — Passage 顶栏和播放
- `web/src/features/reading/PassageSpeakBar.tsx` — 阅读全文按钮和声音选择
- `web/src/features/reading/passageSpeak.ts` — 分段、语言、预取
- `web/src/lib/audioSettings.ts` — 与设置页共用的声音和 Style 列表
- `web/src/pages/SettingsPage.tsx` — Engine、Voice EN、Voice ZH、Style
- `web/src/features/reading/ExplainPopover.tsx` — 现有选中朗读
- `scripts/rag/routes/intensive_reading.py` — `/api/intensive-reading/speak`
- `scripts/rag/intensive_reading/speak.py` — 2000 字上限
- `docs/memory/memory-20261011-reading-comfort.md` — 手机阅读显示，本任务不改
- `docs/memory/memory-20260929-mimo-api.md` — MiMo TTS 接入

---

**Confirmed at**: 2026-10-20 11:20
