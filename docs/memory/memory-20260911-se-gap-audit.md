# Memory: Software Engineering Gap Audit

**Generated**: 2026-09-11
**Last updated**: 2026-09-14
**Project**: c:\jarvis
**Focus**: Langfuse v1 landed; FastAPI agent HTTP migration implemented (search UI stays Flask); awaiting code review

---

## Goal & Scope (required)

Close Jarvis's software-engineering gap via an **audit-only** chat report. Scope: whole repo (RAG agent, search UI, stock, fetchers/pipeline, Telegram bot, config). Depth: architectural plus representative module/import hygiene, not file-by-file. Sharing target: Docker image for teammates' own machines; AWS answered as later feasibility. Deliverable: chat report (this session); memory file written after confirmation.

---

## Key Decisions (required)

1. **Audit only this session**: Inspect and recommend; do not implement uv/FastAPI/Docker/Langfuse now.
2. **Whole-repo scope**: Not RAG-only and not deploy-surface-only.
3. **Sharing target**: Teammates run Docker on their own machines; AWS is a later-feasibility note, not the primary design.
4. **Depth**: Architectural + representative hygiene, not exhaustive every-file review.
5. **Deliverable**: Chat report only (no `docs/` audit markdown unless asked later).
6. **Keep Flask as baseline for recommendations**: FastAPI is possible but not justified as a prerequisite for tracing or Docker.
7. **Next slice (user selected after audit)**: Langfuse tracing around DeepSeek + Ollama wrappers.
8. **Langfuse hosting**: Self-hosted via Docker (not Langfuse Cloud).
9. **Trace payload**: Full prompts, completions, model, latency, token counts.
10. **v1 scope**: Instrument `call_deepseek` + `agent_loop` `ollama.chat` only. Other Ollama HTTP sites later.
11. **Fail-open**: Missing keys or Langfuse down → chat/DeepSeek still work; traces dropped.
12. **Approach A**: Official Langfuse Python SDK v4 + two wrap points (rejected B OTel-first, C homegrown HTTP).
13. **Keep Flask**: No FastAPI migration in this slice.
14. **Plan next**: User chose `writing-plans` standard same-session after Langfuse design approval.
15. **FastAPI**: User asked to use FastAPI instead. Confirmed: written design then execute directly (no plan file). Scope: agent app only (18889); search UI stays Flask. Approach A: incremental HTTP-layer rewrite via FastAPI + Flask-compat adapters (`web_api.py`) so blueprints/SSE/URLs stay. uvicorn replaces `app.run`.

---

## Confirmed Assumptions (required)

- Current product behavior stays the baseline (Flask + SSE chat, local Ollama, in-memory Qdrant from snapshot).
- Recommendations may propose uv, `.env.example`, FastAPI, Docker, Langfuse without applying them in this session.
- `uv` refers to Astral's Python package manager (written in Rust); question was whether *this* project uses it.

---

## Constraints & Non-Goals

- No code changes, Dockerfile, or Langfuse integration in the audit session.
- Do not print secret values from `.env` / `bot_telegram.env` / `.global_settings.json`.
- Windows host defaults (`C:/reports/ai`, `.bat` launchers, PowerShell schedulers) are current reality.

---

## Key Discoveries (required)

- **Not using uv.** No `pyproject.toml`, `uv.lock`, `.python-version`. Deps via ad-hoc `pip install` in README / `docs/getting-started.md` plus `scripts/rag/requirements-rag.txt` (RAG subset only). No lockfile.
- **Scripts folder, not an installable package.** ~153 `.py` files; ~105 `sys.path.insert` in ~65 files; only 5 `__init__.py` (under `rag/tools`, `routes`, `intensive_reading`, `memory`, `learning`). Hyphenated CLI modules (`fetch-bbc-news.py`) are not importable as packages.
- **Giant modules:** `search_ui.py` ~1995, `routes/daily_fetch.py` ~1755, `stock/scanner.py` ~1725, `china_market_data.py` ~1674, `agent.py` ~1487. OOP sparse (~22 classes vs ~1495 functions). Cleaner islands: `rag/memory`, `rag/tools`, Flask blueprints (still large).
- **Config is split, not `.env`-centric.** No `python-dotenv`. Root `.env` exists locally with unused `TUSHARE_TOKEN`. Secrets: `scripts/bot_telegram.env` (custom parser) and `scripts/rag/.global_settings.json` (`deepseek_api_key`). Paths centralized in `scripts/config.py` with Windows `C:/reports/*` defaults; `scripts/stock/config.py` reloads parent via `importlib`. No `.env.example`.
- **Logging exists but is not centralized.** stdlib `getLogger` + duplicated `basicConfig` in ~22 stock/bot files; fetchers mostly `print`; scheduler appends `logs/daily-fetch-scheduler.log`. No `FileHandler` in Python.
- **Git ignore vs tracking:** `logs/` and `tmp/` ignored (good). Entire `tests/` ignored (~70 local test modules, **not tracked**). `jarvis-start.log` is in `.gitignore` but **still tracked**.
- **Flask + FastAPI split.** Search UI (`search_ui.py` :18888) stays Flask. Agent (`agent.py` :18889) is FastAPI via `scripts/rag/web_api.py` Flask-compat (`Blueprint`, `jsonify`, SSE `Response`, `<int:n>` converters). uvicorn replaces `app.run`. `bin/jarvis-start.bat` still runs `python agent.py`.
- **LLM surface:** `call_deepseek` in `scripts/stock/config.py` (OpenAI SDK, captures `usage` tokens). Main chat: `scripts/rag/agent_loop.py` `ollama.chat` stream. Many raw `requests.post` to Ollama HTTP. **No Langfuse / OpenTelemetry.** Ollama `eval_count` / `prompt_eval_count` not recorded.
- **Runtime:** `bin/jarvis-start.bat` starts search_ui + agent + telegram; does **not** start Ollama. Qdrant is in-memory from `REPORTS_ROOT/.rag-store.json`. Dual Flask processes each load MiniLM + snapshot.
- **No Dockerfile / compose.** Windows-specific: `.bat`, `.ps1`, Edge-TTS, Playwright, hardcoded `REPO_CONFIG` paths in `agent.py`.

---

## Runtime Evidence

- `git ls-files` shows `jarvis-start.log` tracked; no `uv.lock` / `pyproject.toml` / `Dockerfile`.
- `git check-ignore`: `tests/test_topic_index_dedup.py` ignored by `.gitignore:2:tests/`; `logs/daily-fetch-scheduler.log` ignored by `.gitignore:4:logs/`.

---

## Open Risks

- Tests cannot be shared or CI'd while `tests/` is gitignored.
- Dual in-memory Qdrant + MiniLM per process will hurt Docker memory.
- Langfuse without a shared Ollama client will miss most HTTP call sites.
- Naive Linux container breaks PowerShell Daily Fetch, Jira scripts, `d:/projects` repo tools.

---

## Current State (required)

- **Working**: Langfuse v1 on main (user consented). Tracing tests 13/13 passed. FastAPI agent layer: `tests/test_web_api.py` 12 passed; IR route tests + platform-updates POST + listen_bind 95/95 in the combined run; `search_ui.py` still Flask.
- **Pending**: Code review of FastAPI migration. Live Langfuse Docker (optional). Commit if user asks. `tests/` still gitignored so new tests will not be committed unless that changes.
- **Blocked**: None.

---

## Next Steps (required)

1. [x] Deliver chat audit answering uv, structure, .env, logging/git, FastAPI, Docker share, AWS, tracing/Langfuse
2. [x] Write this memory file (user confirmed)
3. [x] Brainstorm Langfuse: self-hosted, full I/O, v1 = DeepSeek + agent_loop, fail-open, SDK v4
4. [x] Save implementation plan `docs/plans/2026-09-11-langfuse-tracing.md`
5. [x] Execute plan (`executing-plans`) — 7 unit tests passed; live Langfuse compose not started
6. [x] Code review triage via `receiving-code-review`
7. [x] Applied ACCEPTED findings (Critical-1, Important-1–4, Minor-1/3/4/5). Rejected Minor-2 (full-trace images).
8. [x] Follow-up review + second-cycle fixes; user accepted current state (loop guard)
9. [x] FastAPI agent-only migration (`web_api.py`, uvicorn `__main__`, blueprint imports, IR tests switched to `web_api.Flask`)
10. [x] Code review of FastAPI migration (Important-2/3/4/5, Minor-3/8 applied; Important-1/6 and other Minors rejected)
11. [ ] Follow-up review of FastAPI review-fixes (handoff gate)

---

## Notes for Next Session

- Do **not** migrate to FastAPI as a prerequisite for Langfuse.
- v1 wrap points: `scripts/stock/config.py` `_get_deepseek_client` (langfuse.openai drop-in) and `scripts/rag/agent_loop.py` `ollama.chat` (manual generation for the stream). Do not double-wrap DeepSeek with a second generation.
- New module: `scripts/tracing.py` loads repo `.env` (setdefault). Compose: `deploy/langfuse/`. Keys: `LANGFUSE_PUBLIC_KEY`, `LANGFUSE_SECRET_KEY`, `LANGFUSE_BASE_URL=http://localhost:3000` (`LANGFUSE_HOST` alias).
- Ollama local cost = 0. Session id from `/api/agent` `session_id`.
- FastAPI agent is in: `scripts/rag/web_api.py` (Flask-compat). Blueprints import `web_api`, not `flask`. `agent.py` `__main__` calls `uvicorn.run`. Search UI must stay Flask.
- Out of scope still: uv, Jarvis app Docker, AWS, un-ignoring `tests/`, untracking `jarvis-start.log`, other Ollama HTTP sites, Search UI FastAPI.
- If packaging work starts later: `pyproject.toml` + uv + un-ignore `tests/` is the highest-leverage SE fix.

---

## References (required)

- `scripts/config.py` — central paths
- `scripts/stock/config.py` — stock + `call_deepseek`
- `scripts/rag/agent.py` — FastAPI agent via `web_api`, `REPO_CONFIG`
- `scripts/rag/web_api.py` — Flask-compat FastAPI layer
- `scripts/rag/search_ui.py` — Flask Search UI (unchanged)
- `scripts/rag/requirements-rag.txt` — only requirements file
- `bin/jarvis-start.bat` — process launcher; writes `jarvis-start.log`
- `.gitignore` — ignores `tests/`, `logs/`, `.env`; `jarvis-start.log` still tracked
- `docs/getting-started.md` — canonical pip install list
- `docs/plans/2026-09-11-langfuse-tracing.md` — approved Langfuse v1 TDD plan

---

**Confirmed at**: 2026-09-11
