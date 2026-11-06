# Memory: MiMo 2.6 API call shape

**Generated**: 2026-10-20 18:30
**Last updated**: 2026-10-21 15:40
**Project**: c:\jarvis
**Focus**: Whether Jarvis and the Android app must change MiMo chat requests after the v2.6 default flipped thinking on

---

## Goal & Scope (required)

Xiaomi MiMo v2.6 is the current text model. Check the official docs and update Jarvis plus `mobile/ir-android` only where the request shape no longer matches. The user tests the phone app; Jarvis was checked with a live completion.

---

## Key Decisions (required)

1. **Text calls send `thinking.type=disabled`**: v2.6 defaults thinking to `enabled`. Omitting the field turns thinking on and spends `max_completion_tokens` on reasoning. Jarvis (`scripts/rag/mimo_chat.py` `probe`, `complete`, `stream_chat` via `extra_body`) and Android (`MimoProtocol.body`, `MimoProtocol.analysisBody`) now send it. Official basic sample does the same.
2. **Rejected: leave the field off**: that was the September plan, written when the field was omitted on purpose. The default has since flipped, so omitting it no longer means thinking stays off.
3. **Rejected: keep thinking on and store `reasoning_content`**: product behavior stays answer-only, matching GLM and the reading pipeline comment "Thinking stays off".
4. **TTS stays `mimo-v2.5-tts`**: the model list updated 2026-10-08 still has no v2.6 TTS. Voice clone and voice design stay on the v2.5 TTS ids. Android `PassageSpeak.ttsBody` was not changed.
5. **Model id stays `mimo-v2.6-flash`**: both sides already used it. Not switched to `mimo-v2.6-pro` or `mimo-v2.6-pro-ultraspeed`.
6. **Auth stays `Authorization: Bearer`**: the chat doc also accepts `api-key`. Existing OpenAI client and Android calls were left on Bearer.
7. **No code review on the thinking change**: user declined `requesting-code-review` for the v2.6 request-shape edit.
8. **Reading settings come from the running process**: web 阅读全文 calls `/api/intensive-reading/speak`. That route was doing `import agent`, which is a second copy of `agent.py` frozen at first import. The settings test writes the key into the live `__main__._GLOBAL_SETTINGS`. Speak kept reading the stale copy, so the page showed `No MiMo API key configured` while Settings test succeeded. `_settings_from_modules` now prefers `__main__` when it has `_GLOBAL_SETTINGS`, same idea as `daily_fetch._resolve_agent_from`. User asked for code review of this fix.

---

## Confirmed Assumptions (required)

- Pay-as-you-go base URL remains `https://api.xiaomimimo.com/v1`.
- Probe may still send `temperature=1.0` and `top_p=0.95`. Those are honored only because thinking is disabled; in thinking mode the server forces `1.0` / `0.95`.
- Agent and reading calls still do not force temperature. They only add the thinking-off body.
- `mimo-v2.5` and `mimo-v2.5-pro` are deprecated at 10:00 Beijing time on 2026-10-21. This repo does not call those ids.

---

## Constraints & Non-Goals (include when relevant)

- Do not send `thinking` on TTS requests.
- Do not keep `reasoning_content` across turns.
- Do not add image input on a MiMo chat turn.

---

## Key Discoveries (required)

- Official chat doc (updated 2026-09-20) lists `thinking.type` default `enabled` for `mimo-v2.6-flash`, `mimo-v2.6-pro`, and `mimo-v2.6-pro-ultraspeed`. The published basic curl sets `thinking.type` to `disabled`.
- `max_completion_tokens` includes reasoning tokens. v2.6-flash default is `131072` (v2.5 was `32768`). Our callers still pass an explicit cap (64 probe, 4096 analysis, caller-supplied otherwise).
- Live probe on 2026-10-20 with thinking disabled returned a short hello, `reasoning_tokens` 0, `finish_reason` stop.
- Settings UI label `MiMo-V2.5-TTS` lives in `web/src/lib/audioSettings.ts`. `tests/test_mimo_routes.py::test_settings_page_engine_labels_keep_stored_values` still scans `SettingsPage.tsx` for that string and fails. That failure predates this change. The label is still correct because TTS is v2.5.
- Jarvis started as `python scripts/rag/agent.py` is module `__main__`. A later `import agent` loads a second module. In-memory settings updates (the MiMo key save) do not flow into that copy. Disk is updated, but the already-imported copy stays empty if it was first imported before the save.

---

## Runtime Evidence (include when relevant)

- RED: `pytest` on the three updated chat tests failed with `KeyError: 'extra_body'` before the adapter change.
- GREEN: `python -m pytest tests/test_mimo_chat.py tests/test_mimo_routes.py tests/test_mimo_cloud.py tests/test_mimo_agent_loop.py tests/test_mimo_tts_routes.py -q` → 37 passed, 1 failed. The failure is the stale Settings page string check above.
- Live: probe through `mimo_chat.probe` returned `Hello there!`. A second completion with the same extra body reported `reasoning_tokens 0`, `finish stop`, content `Hello!`.
- Android unit tests were not run here. The user tests the phone app.
- 2026-10-21: `GET /api/settings` showed a masked MiMo key and `audio_engine=mimo`. `POST /api/intensive-reading/speak` with `engine=mimo` returned 400 `No MiMo API key configured`. Agent process had started at 08:10; the settings file was rewritten at 15:11.
- After the settings-source fix and an agent restart, the same speak request returned 200 `audio/mpeg`.
- `python -m pytest tests/test_intensive_reading_speak.py -q` → 18 passed. RED before the helper existed: `ImportError: cannot import name '_settings_from_modules'`.

---

## Open Risks (include when relevant)

- Android probe and analysis now send thinking off, but that JSON was not executed against the live API in this session.
- If a future TTS model appears under a v2.6 id, `TTS_MODEL` and `PassageSpeak.ttsBody` still need a separate change.

---

## Current State (required)

- **Working**: Jarvis text calls explicitly disable thinking. Reading speak and reading cloud keys read the live process settings. Live speak with MiMo returned audio after restart.
- **Pending**: code review of the reading settings fix. User still tests Android on device.
- **Blocked**: none.

---

## Next Steps (required)

1. [ ] Finish code review of the reading settings fix.
2. [ ] User tests Android MiMo probe and a reading analysis on device.
3. [ ] Leave the stale `test_settings_page_engine_labels_keep_stored_values` unless someone points that test at `web/src/lib/audioSettings.ts`.

---

## Notes for Next Session (include when relevant)

- Do not "upgrade" TTS to a v2.6 model id until the model list actually has one.
- OpenAI SDK field for the thinking object is `extra_body`, not a top-level `thinking=` kwarg.

---

## References (required)

- `scripts/rag/routes/intensive_reading.py` — `_settings_from_modules` prefers the running app
- `scripts/rag/routes/daily_fetch.py` — earlier `_resolve_agent_from` with the same `__main__` preference
- `tests/test_intensive_reading_speak.py` — stale-import regression test
- `scripts/rag/mimo_chat.py` — Jarvis chat and TTS adapter
- `tests/test_mimo_chat.py` — request-shape tests
- `mobile/ir-android/app/src/main/java/com/jarvis/ir/mimo/MimoProtocol.kt` — Android chat and analysis JSON
- `mobile/ir-android/app/src/main/java/com/jarvis/ir/speak/PassageSpeak.kt` — Android TTS body, still `mimo-v2.5-tts`
- `web/src/lib/audioSettings.ts` — engine label `MiMo-V2.5-TTS`
- https://mimo.mi.com/docs/zh-CN/api/chat/openai-api — chat request, thinking default
- https://mimo.mi.com/docs/en-US/quick-start/summary/model — model ids, TTS still v2.5
- https://mimo.mi.com/docs/en-US/updates/deprecate — v2.5 / v2.5-pro removal on 2026-10-21

---

**Confirmed at**: 2026-10-20 18:30
