# Memory: DeepSeek Chat Relay Feasibility

**Generated**: 2026-08-31
**Last updated**: 2026-08-31
**Project**: c:\jarvis
**Focus**: Feasibility of replacing Jarvis DeepSeek API calls with chat.deepseek.com via a Chrome extension

---

## Goal & Scope (required)

User asked whether a Chrome extension could relay Jarvis stock-module DeepSeek calls through DeepSeek web Chat instead of `api.deepseek.com`, mainly to save API cost. Session scope was **feasibility discussion only** — no code, no plugin, no Jarvis changes.

---

## Key Decisions (required)

1. **Session scope = discuss only**: User chose feasibility (can it work, risks, architecture sketch) over design or prototype.
2. **Motivation = cost**: Use web Chat quota instead of billed API.
3. **Verdict: not recommended**: Technically a fragile relay is imaginable; it is a poor fit for Jarvis and conflicts with DeepSeek Terms of Use §3.5(3) (robots/spiders/automatic capture of service content). Do not implement.
4. **Rejected: Chrome extension as API substitute**: Wrong product surface (consumer Chat vs developer API), wrong concurrency/structured-output contract, ToS risk, likely worse cost/time than current `deepseek-v4-flash` API.

---

## Confirmed Assumptions (required)

- Target Chat surface is `chat.deepseek.com` (web), not a different DeepSeek product.
- Current Jarvis path: `scripts/stock/config.py` `call_deepseek()` → OpenAI SDK → `https://api.deepseek.com`, model `deepseek-v4-flash`, thinking on by default.
- Callers include scanners (unified, long-term, midday, right-side, ATH rebreak, quality-value), `llm_reasoning`, price predictor, sentiment.
- RAG chat / daily briefing stay on local Ollama; DeepSeek is stock last-mile only.

---

## Constraints & Non-Goals

- Do not implement a Chat-page scraper, DOM automation, or extension that bypasses the billed API.
- Do not change Jarvis in this session.

---

## Key Discoveries (required)

- Code vs docs: `DEEPSEEK_MODEL` in `config.py` is **`deepseek-v4-flash`**; many docs still say `deepseek-v4-pro`.
- `call_deepseek` expects a structured dict (`ok`, `content`, `reasoning_content`, `usage`, `finish_reason`), 120s timeout, optional thinking/`reasoning_effort`.
- Chrome MV3 extensions cannot bind a local HTTP server; a relay would have to invert the connection (extension connects into Jarvis), keep a logged-in Chat tab open, and drive the UI sequentially.
- DeepSeek Terms of Use §3.5(3) forbids capturing/copying service content via robots, spiders, or other automatic setups.
- Web Chat is stateful, sequential, UI-limited, and dynamically throttled against automation; API is stateless, metered, JSON/tooling-oriented — the contract Jarvis already uses.

---

## Open Risks

- If cost is still too high, the legal levers are: fewer API calls, disable thinking where not needed, smaller prompts, more local Ollama — not Chat automation.

---

## Current State (required)

- **Working**: Feasibility discussed; user asked for the “why not” rationale; memory write approved.
- **Pending**: Optional follow-up on legal API-cost reduction (not started).
- **Blocked**: None.

---

## Next Steps (required)

1. [x] Deliver written “why not recommended” analysis in chat
2. [ ] If user wants, brainstorm legal cost reduction (call volume, thinking, prompt size, local models)
3. [ ] Do not build a Chat relay extension

---

## Notes for Next Session

- User language: Chinese.
- Question channel this session: AskQuestion.
- Do not treat “Chrome plugin relay” as an open implementation task; the recorded decision is reject.

---

## References (required)

- `scripts/stock/config.py` — `call_deepseek`, `DEEPSEEK_MODEL`
- `scripts/stock/scanner.py`, `long_term_scanner.py`, `midday_scanner.py`, `right_side_scanner.py`, `ath_rebreak_scanner.py`, `quality_value_scanner.py`, `llm_reasoning.py`, `model_price_predictor.py`, `sentiment.py` — DeepSeek callers
- https://cdn.deepseek.com/policies/en-US/deepseek-terms-of-use.html — Terms of Use §3.5(3)
- https://cdn.deepseek.com/policies/en-US/deepseek-open-platform-terms-of-service.html — Open Platform (API) ToS

---

**Confirmed at**: 2026-08-31
