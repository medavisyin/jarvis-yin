# Memory: 小米 MiMo API 接入

**Generated**: 2026-09-29 15:10
**Last updated**: 2026-09-29 17:25
**Project**: c:\jarvis
**Focus**: 按 GLM 的方式接入小米 MiMo 文本与 TTS

---

## Goal & Scope

在 Jarvis 设置里保存小米 API Key，凡是能选 GLM 作为 Agent / 云模型的地方都加上 MiMo。文本走按量 OpenAI 兼容接口，模型 `mimo-v2.6-flash`。音频输出增加 MiMo-V2.5-TTS；选中后日报音频和精读朗读也改走该接口，风格可选。手机端只加 Key 和连通性测试。

---

## Key Decisions

1. **文本模型用 `mimo-v2.6-flash`**：输入 1 / 输出 2 元／百万 tokens。Rejected: `mimo-v2.6-pro`（文档示例，3 / 6），以及设置里再选 flash/pro。
2. **TTS 选中后替换现有音频路径**：日报音频和精读朗读在选中 MiMo-V2.5-TTS 时调用 `mimo-v2.5-tts`。Rejected: 只在设置里试听、生产路径继续 Edge-TTS。
3. **风格下拉用文档推荐的开头标签**（磁性、唱歌、开心等）。音色默认 `mimo_default`（中国集群为冰糖）。
4. **说话 / 唱歌测试用用户给定原文**，标签已写在文本里。
5. **手机端只保存 Key 并做连通性测试**，不把精读分析切到 MiMo。
6. **新建本记忆文件**，不并入比价记忆 `memory-20260929-cn-llm-api-prices.md`。
7. **平行模块，不重构 GLM**：新建 `mimo_chat.py`。Rejected: 抽共用云模型层；把 MiMo 写进 `glm_chat.py`。
8. **`glm_chat.py` 只改白名单**：`chat_agent` 与 `cloud_llm` 接受 `mimo`。智谱客户端、模型、GLM 报错不动。
9. **聊天对齐 GLM**：要 Key，流式，现有工具 schema。没 Key 或失败不回退。这一轮不识图。不打开深度思考，不注入「你是 MiMo」。
10. **音频引擎** `audio_engine`：`edge`（默认）或 `mimo`。风格 `audio_mimo_style`，非法值存 `平静`。生产默认风格 `平静`。中文音色 `mimo_default`，英文 `Mia`。主播和嘉宾共用一只音色。精读语速对 MiMo 不生效。
11. **改道三处**：`_tts_segments_to_mp3`、`_generate_knowledge_audio`、精读 `synthesize_speech`。不改 `generate-audio.py`、视频脚本、文章音频 `_tts_to_mp3`。输出仍是 mp3，经 ffmpeg。没有 ffmpeg 则失败，不退回 Edge。
12. **用户选定同会话写实现计划**（`writing-plans`），不直接写代码。
13. **计划先审再改**：用 think-mcp `sequentialthinking` 审过。执行前要先改计划里的 5 处，不改架构。Rejected: 按未改的计划直接写代码。
14. **在 main 上一次做完**：用户同意不逐批汇报。5 处审阅已写进实现（2000 字分段、`model_extra`、精读先转 mp3 再补静音、知识音频懒加载、测试 `sys.path`）。
15. **用户要求代码评审**，并更新本记忆。关注点：需求对齐、响应里不出现原始 Key、GLM 与 Edge 不回退、测试不打真实网络。
16. **评审发现走 receiving-code-review**。六条都接受。正常 MiMo 分析失败不会走到 `stock.py` 的外层异常：`_call_mimo` 已用 `public_error` 返回字典。外层「DeepSeek 分析失败」只在别的异常冒出时出现。
17. **六条都改了**。MiMo TTS 失败改抛 `MimoTtsError("MiMo request failed")`，缺 Key 和 ffmpeg 文案保留。设置引擎显示 Edge / MiMo-V2.5-TTS，存储值仍是 edge / mimo。股票分析外层异常按提供方写 MiMo / GLM / DeepSeek，MiMo 和 GLM 不拼原始异常。尚未做第二轮评审。

---

## Confirmed Assumptions

- 按量付费 Base URL：`https://api.xiaomimimo.com/v1`（OpenAI 兼容）。不用 Token Plan 地址。
- Key 的保存、脱敏、测试按钮对齐现有 GLM。
- 默认聊天仍是 Ollama，默认音频仍是 Edge-TTS，直到用户改选 MiMo。
- 不接入 `mimo-v2.5-tts-voicedesign` 和 `mimo-v2.5-tts-voiceclone`。
- 用户已确认需求镜像，并逐段通过文本、音频、手机方案（2026-09-29）。
- 请求参数用 `max_completion_tokens`，不传 GLM 那套 `thinking`。探测请求可以按官方示例带 temperature / top_p；Agent 调用不把 temperature 固定成 1.0。

---

## Key Discoveries

- GLM 可选位置：设置页 Chat agent；`CloudModelSelect`（股票扫描、分析、训练、精读）；`agent_loop`、`routes/stock.py`、`routes/intensive_reading.py`、`scripts/stock/config.py`。
- 手机 GLM 在 `SettingsDialog` 存 Key，精读分析另有一套 HTTP。本次手机只复制 Key + 连通测试。
- TTS 目标文本放在 `role: assistant`；开头 `(风格)` 控制风格。唱歌必须用 `(唱歌)`。预置音色含冰糖、茉莉、苏打、白桦、Mia、Chloe、Milo、Dean。
- 日报分段已是 2000 字，不是计划里写的 800。MiMo 应换掉每段的合成器，沿用现有拼接。
- 精读朗读接口返回 `audio/mpeg`，并在有 ffmpeg 时前面补静音。MiMo 要先转 mp3，再走这段静音。
- `ai_news.py` 不要在文件顶部 import `agent`。设置用函数内懒加载，和 `_speak_voice_en` 一样。
- 文档：https://mimo.mi.com/docs/zh-CN/quick-start/summary/first-api-call 与 https://mimo.mi.com/docs/zh-CN/quick-start/usage-guide/audio/speech-synthesis-v2.5
- 知识音频失败把 `str(e)` 写进任务，状态接口原样返回（`ai_news.py` 591、890）。日报 AI / 财经音频同样把 `str(e)[:300]` 放进步骤（`daily_fetch.py` 969、1237），状态接口返回整个 job。聊天和设置测试已经用 `public_error`。`MimoConfigError` / `MimoTtsError` 自己的文案不含 Key。

---

## Open Risks

- 没有打真实小米接口。设置里的测试按钮才是连通检查。
- 手机探测用 `Authorization: Bearer`。真机失败时再试文档 curl 里的 `api-key` 头。
- 日报和知识音频的 MiMo 失败已改成安全文案，但还没有第二轮评审。没有打真实小米接口。

---

## Current State

- **Working**: 桌面和手机代码已落地。pytest 72 项通过。Android `MimoKeyTest`、`MimoProtocolTest`、`GlmKeyTest` 通过。
- **Pending**: 是否对已改的六条做第二轮评审。真实 Key 连通未测。设置页下拉没有在浏览器里点过。
- **Blocked**: 无。

---

## Next Steps

1. [x] 用户确认需求理解。
2. [x] 方案通过，并写成 `docs/plans/2026-09-29-mimo-api.md`。
3. [x] 在 main 上实现。桌面 72 项测试通过，Android 单测通过。
4. [x] 代码评审完成，发现已核对。
5. [x] 六条发现已改。相关 pytest 77 项通过（54 + 23）。
6. [ ] 用户决定要不要做第二轮评审。

---

## Notes for Next Session

评审分类（2026-09-29）。六条 ACCEPTED，并且都已改：

| ID | 分类 | 证据 |
|---|---|---|
| Critical-1 | ACCEPTED | `ai_news.py:591` 写入 `str(e)`，`:890` 把整个 job 返回；`daily_fetch.py:969`、`:1237` 写入步骤，状态接口返回 job |
| Important-1 | ACCEPTED | `tests/test_mimo_tts_routes.py` 没有知识音频 MiMo 分支，也没有「异常里的假 Key 不出现在任务错误里」 |
| Important-2 | ACCEPTED | `SettingsPage.tsx` 引擎选项显示 `edge` / `mimo`；计划要求显示 Edge / MiMo-V2.5-TTS，存储值仍是 edge / mimo |
| Minor-1 | ACCEPTED | `stock.py:272` 固定「DeepSeek 分析失败」。MiMo 调用失败本身被 `_call_mimo` 吃掉并返回安全文案 |
| Minor-2 | ACCEPTED | `tests/test_glm_chat.py:22` 函数名仍写 only ollama or glm |
| Minor-3 | ACCEPTED | `stock.py:33` 注释未写 mimo |

---

## References

- `web/src/pages/SettingsPage.tsx` — 设置页 Chat agent、API Key、Audio
- `web/src/components/CloudModelSelect.tsx` — 云模型下拉
- `scripts/rag/glm_chat.py` — GLM Key 与云模型开关，MiMo 应对齐此模式
- `mobile/ir-android/app/src/main/java/com/jarvis/ir/ui/SettingsDialog.kt` — 手机设置
- `docs/memory/memory-20260929-cn-llm-api-prices.md` — 比价结论，flash 的价格依据
- https://mimo.mi.com/docs/zh-CN/quick-start/summary/first-api-call
- https://mimo.mi.com/docs/zh-CN/quick-start/usage-guide/audio/speech-synthesis-v2.5
- `scripts/rag/mimo_chat.py` — MiMo 文本与 TTS 适配
- `docs/plans/2026-09-29-mimo-api.md` — 已通过方案的实现计划

---

**Confirmed at**: 2026-09-29
