# Memory: GLM agent for Jarvis chat and mobile gloss

**Generated**: 2026-09-28 14:10
**Last updated**: 2026-09-29 13:05
**Project**: c:\jarvis
**Focus**: Add Zhipu GLM-4.7-Flash as a switchable agent for Jarvis chat and Android intensive-reading gloss

---

## Goal & Scope

Jarvis chat can use GLM. Stock and desktop intensive reading can choose local, DeepSeek, or GLM. On the Huawei tri-fold reading app, GLM is required for a right-hand analysis pane with only 好词好句 and 社会文化. The phone stores its own GLM key and calls Zhipu over HTTP. Local word gloss, TTS, and the dictionary stay as they are.

---

## Key Decisions

1. **GLM covers Jarvis chat and mobile 词/句 gloss only**: Stock DeepSeek stays on its own key and is not a chat agent.
2. **Switcher lists**: Jarvis chat is Ollama or GLM. Mobile gloss is `qwen3-0.6`, `qwen3-1.7`, or GLM.
3. **Model id**: `glm-4.7-flash` (the free GLM-4.7-Flash model in the Zhipu chat-completions API).
4. **SDK split**: Jarvis uses `zai-sdk` (`ZhipuAiClient`). Android cannot use that package, so it uses HTTP.
5. **Keys stay on the device**: Jarvis in `scripts/rag/.global_settings.json`. Phone in app-private storage. Not synced, not committed.
6. **Order**: Implement and test Jarvis locally first. Mobile after that local test passes.
7. **Session start**: User chose not to load an older memory file.
8. **Approved approach**: GLM stays inside the existing Jarvis chat loop, including tool rounds. A small adapter maps Zhipu stream chunks onto the current token and tool-call events. Mobile gloss calls the HTTP API directly.
9. **Approved design**: `chat_agent` (`ollama`|`glm`) and masked `glm_api_key` in `scripts/rag/.global_settings.json`. Chat uses `ZhipuAiClient` model `glm-4.7-flash` with the existing tool schemas. Images on a GLM turn error before the API call. Missing key errors with no fallback. History summarization stays on the local fast model. Mobile adds a `glm` gloss choice, app-private key, and HTTP chat completions with the same prompts. User chose to execute directly, Jarvis unit tests and local test before mobile.
10. **Errors and tests**: Settings test endpoint returns 400 without a key. API failures are shown once. Unit tests use a fake client. Live key check is manual.
11. **Mobile GLM is the analysis pane, not the gloss switcher** (2026-09-29): User confirmed GLM on the phone, key only in app-private storage, model `glm-4.7-flash`, same 好词好句 (`vocab`) and 社会文化 (`culture`) prompts as desktop intensive reading. Other analysis tabs are out. When the window is wide enough (tri-fold open), passage stays on the left and analysis on the right. When folded, the passage keeps the full width and analysis opens from a button. Local qwen gloss, TTS, and ECDICT do not change.
12. **Phone calls Zhipu directly** (2026-09-29): User chose approach A. Android uses `HttpURLConnection` to `https://open.bigmodel.cn/api/paas/v4/chat/completions`, thinking disabled, streamed into the pane. Key is entered in the existing settings dialog and masked. Prompts are the desktop university/Chinese vocab and culture prompts, copied into the app. Passage window is 12000 characters. Side pane when width is at least 600dp.
13. **Errors and tests** (2026-09-29): Missing key shows 「还没有 GLM 密钥」 and does not call the network. Other failures show 「GLM 请求失败」 with no response body. HTTP 429 shows 「GLM 请求过于频繁，请稍后再试」. Empty content shows 「没有返回内容」. The stream can be cancelled. Unit tests cover SSE join, key mask, no request without a key, and 599dp vs 600dp. Live check is manual on the phone. User asked for a same-session implementation plan before coding.
14. **Plan** (2026-09-29): `docs/plans/2026-09-29-mobile-glm-analysis.md` is implemented on `main`. Unit tests for `com.jarvis.ir.glm.*` and `ReadingLayoutTest` passed after the analysis pane was wired. Phone install and a live GLM call are still manual.
15. **Review** (2026-09-29): [code review](c6d6948d-a186-4a4b-8d40-a8c099c4a792) found no Critical issues. Important-1, Important-2, and Minor-1 were accepted and applied: late deltas are dropped unless they belong to the current request, navigation clears the analysis, and the two analysis buttons stay enabled during a run. Minor-2 and Minor-3 were rejected. Follow-up [review](00e21740-9c6a-48ff-ae19-29c495f19102) said the restart path is closed, but cancel/reset still leaves `analysisTransport` set. That remaining item was accepted and applied: `cancelAnalysis()` sets `analysisTransport = null`, and error assignment uses the same current-request check as deltas. Unit tests passed. User accepted this state and stopped the review loop. Live install on the Huawei tri-fold is still manual.

---

## Confirmed Assumptions

- Existing Ollama chat and local Qwen gloss stay the default until the user switches to GLM.
- DeepSeek settings and stock calls are unchanged.
- Mobile 「读」 stays system TTS. Dictionary stays ECDICT.
- Jarvis fast/local jobs (intent, daily fetch) stay on Ollama. Only the main chat agent switches.
- Empty GLM key produces a clear error. No silent fallback to the other agent.
- Text only. The sample image URL and `thinking` block are SDK examples, not product requirements.

---

## Constraints & Non-Goals

- Do not add DeepSeek as a Jarvis chat agent. Chat stays Ollama or GLM.
- Stock and intensive reading may call GLM beside DeepSeek. That is separate from the chat-agent switch.
- Do not put API keys in git.
- Do not use `zai-sdk` inside the Android app.

---

## Runtime Evidence

- Reviewer [code review](b6d935ed-f2a4-414d-b450-acc28465b7d9): no Critical. Ready to merge with fixes.
- Fixes applied and `pytest tests/test_glm_chat.py tests/test_glm_agent_loop.py tests/test_tracing_agent_loop.py` → 23 passed. Important-1 through Important-4 and Minor-1 through Minor-3 are in. Minor-4 (Langfuse on GLM) stays out of scope.
- Follow-up review found no remaining Critical, Important, or Minor issues. Ready for the user's local Jarvis test.
- Local Test failed with `ModuleNotFoundError`: `bin/jarvis-start.bat` uses the Microsoft Store Python, not `.venv`. `zai-sdk` 0.2.3 was then installed into that Store Python. The already-running Agent (started at 17:01, before the install) still could not see the new package. Restarted Agent only (`jarvis-restart.bat /AGENT`); new PID listened on 18889 and `/api/health` returned 200. A fresh Store-Python process can `from zai import ZhipuAiClient`.
- After the Agent restart, GLM Test reached Zhipu and failed with `APIReachLimitError`. In `zai` that class is only HTTP 429 (rate, concurrency, or quota). GLM-4.7-Flash being free means the token price is zero; the account still has a concurrency cap. The settings page shows only the exception class because `public_error` hides the response body.
- A later `POST /api/glm/test` returned 200. The DeepSeek key was still in `.global_settings.json` and in Settings, below Audio. User asked to surface it again, add GLM next to every DeepSeek choice, and add the same choice on intensive reading.

---

## Key Discoveries

- Jarvis settings already persist in `scripts/rag/.global_settings.json`, loaded by `scripts/rag/agent.py`. DeepSeek key is masked on `GET /api/settings` and written via `POST /api/settings/deepseek-key`. The web form is `web/src/pages/SettingsPage.tsx`.
- Main chat model is `OLLAMA_MODEL` in `scripts/rag/agent.py`, applied in `scripts/rag/agent_loop.py`. `POST /api/switch-model` only changes the Ollama model name.
- Mobile gloss choices are `qwen3-0.6` and `qwen3-1.7` in `mobile/ir-android/.../explain/GlossSession.kt`, UI in `SettingsDialog.kt` / `GlossDownloadBar.kt`, engine `CactusGlossEngine`.
- Zhipu chat-completions model enum includes `glm-4.7-flash`. Docs: https://docs.bigmodel.cn/api-reference/%E6%A8%A1%E5%9E%8B-api/%E5%AF%B9%E8%AF%9D%E8%A1%A5%E5%85%A8

---

## Current State

- **Working**: Jarvis side is implemented. Settings can select Ollama or GLM. GLM key is saved in `scripts/rag/.global_settings.json` (gitignored) and masked on read. Chat uses `zai-sdk` model `glm-4.7-flash` inside the existing tool loop, with thinking disabled. An image on a GLM turn errors before the API call. `zai-sdk` is installed in `.venv`.
- **Pending**: Design how the phone calls GLM and lays out the analysis pane, then implement. Desktop stock/reading GLM choice is already in the restarted Agent.
- **Blocked**: None.

---

## Next Steps

1. [x] Understanding and design approved
2. [x] Jarvis unit tests and implementation (`scripts/rag/glm_chat.py`, `agent_loop.py`, `agent.py`, `web/src/pages/SettingsPage.tsx`)
3. [ ] User live-tests Jarvis locally (restart required). Follow-up review is done and clean.
4. [ ] Mobile GLM key + 好词好句 / 社会文化 pane (design not approved yet)

---

## References

- `scripts/rag/glm_chat.py` -- Zhipu adapter
- `scripts/rag/agent.py` -- global settings, GLM key, and test route
- `tests/test_glm_chat.py` -- adapter tests
- `tests/test_glm_agent_loop.py` -- chat-loop tests
- `scripts/rag/agent_loop.py` -- main chat model call
- `web/src/pages/SettingsPage.tsx` -- Jarvis settings UI
- `mobile/ir-android/app/src/main/java/com/jarvis/ir/ui/SettingsDialog.kt` -- mobile settings
- `mobile/ir-android/app/src/main/java/com/jarvis/ir/explain/GlossSession.kt` -- gloss model choices
- https://docs.bigmodel.cn/api-reference/%E6%A8%A1%E5%9E%8B-api/%E5%AF%B9%E8%AF%9D%E8%A1%A5%E5%85%A8 -- Zhipu chat completions

---

**Confirmed at**: 2026-09-28 (understanding summary confirmed)
