# Memory: Daily Fetch 08:00 Auto-Schedule

**Generated**: 2026-08-28 ~10:15 UTC+8
**Last updated**: 2026-08-30 ~08:48 UTC+8
**Project**: c:\jarvis
**Focus**: Auto-run Daily Fetch (AI News + Finance News only) at 08:00 inside the Jarvis process

---

## Goal & Scope (required)

Every morning at local 08:00, Jarvis automatically runs Daily Fetch for **AI News + Finance News only** (fetch, merge/translate, RAG ingest, MP3s) so the user can listen without clicking. Wiki / Jira / commit report are skipped. Computer stays on (plugged in, never sleep).

---

## Key Decisions (required)

1. **Scheduler = in-process APScheduler** (user chose B): not Windows Task Scheduler / cron. Jarvis process owns the clock.
2. **Deliverable = listen-ready**: fetch + merge/翻译 + RAG + audio (AI MP3 + 6 finance MP3s).
3. **Missed 08:00 = skip today**: if Jarvis is not running at 08:00, do not catch up on later start.
4. **Skip if already done**: if today's AI News + Finance News already ran (including a manual run), the 08:00 job skips.
5. **Every day including weekends** (user said 每天).
6. **Local machine time** (China UTC+8 on this PC).
7. **Rejected: Windows Task Scheduler / curl continue API**: user preferred APScheduler despite "maybe cron is enough".
8. **Rejected: catch-up on late Jarvis start**.
9. **Approach A approved**: APScheduler CronTrigger + existing `_run_daily_fetch(only_steps=NEWS_ONLY_STEPS)`. Rejected stdlib sleep loop (B) and full jarvis-next §1.2 (C).
10. **Skip-if-done files**: `ai-briefing.mp3` AND `finance-news/finance-news-data.json` (not all 6 finance MP3s).
11. **misfire_grace_time=60**; no Global Settings UI; always on when Jarvis runs.
12. **Do not add refetch_***: finance already runs inside `fetch_sources` / `run-all-sources` Phase 5.
13. **Accept Confluence Phase 3.5** inside `fetch_sources` (no `--skip-confluence`).
15. **Plan critical review**: lazy-import APScheduler; assert Thread.start(); print scheduler status to stdout (logging defaults to WARNING). Residual skip-if-done vs missing finance MP3s accepted.
16. **Helpers live in `daily_fetch_schedule.py`**: `routes.daily_fetch` circular-imports `learning.helpers`, so unit tests cannot import the Flask route module. Core skip/start/scheduler logic is import-light; `daily_fetch.py` wraps it to start `_run_daily_fetch`.
17. **User skipped `requesting-code-review`** after Tasks 2–6 (2026-08-29).
20. **2026-08-30 09:00 still did not fire** after 08:50 restart. Log had `scheduler_started` only; API `next_run` still `2026-08-30T09:00:00+08:00` at 09:11 → APScheduler `_process_jobs` never ran (thread stuck in Event.wait). Replaced with sleep-loop; test cron **09:40**.

---

## Confirmed Assumptions (required)

- Jarvis is typically already running before 08:00 because the PC never sleeps.
- Full Daily Fetch pipeline still exists for manual runs; auto job is a subset.
- Continue API `only_steps` is the existing hook for subset runs (`POST /api/toolbar/daily-fetch/continue`).
- Skip wiki / Jira / commit report.

---

## Constraints & Non-Goals (include when relevant)

- Minimal code change.
- Do not change fetch sources / finance catalog.
- No OS-level scheduled task.
- No retry-after-30-min from the jarvis-next 1.2 plan unless later approved.

---

## Key Discoveries (required)

- `POST /api/toolbar/daily-fetch` always runs the **full** pipeline; subset runs use `continue` + `steps`.
- `_run_daily_fetch(..., only_steps=)` already gates steps; `_already_done` is **disabled** when `only_steps` is set (explicit continue never skips).
- `docs/plans/2026-04-17-jarvis-next.md` §1.2 already proposed APScheduler at 08:00 plus Global Settings, last-run indicator, and one retry — heavier than "minimal".
- APScheduler 3.11.3 installed (`apscheduler>=3.10,<4` in `scripts/rag/requirements-rag.txt`).
- Importing `routes.daily_fetch` from pytest hits circular import via `learning.helpers`.

---

## Current State (required)

- **Working**: 08:00 APScheduler implemented and unit-tested (8 schedule tests + finance regression). Hook is in `agent.py` before `app.run`.
- **Pending**: Restart Jarvis so cron is 08:00 again. Windows task `JarvisDailyFetchPoke` pokes `GET /api/toolbar/daily-fetch/scheduler` at 08:00 (works while display is off). In-process loop is backup only. 2026-08-30 10:15 skipped_misfire after 息屏 (~10 min stall, late=72s).
- **Blocked**: none.

---

## Next Steps (required)

1. [x] Brainstorm 2–3 APScheduler approaches; get design approval
2. [x] Write `docs/plans/2026-08-28-daily-fetch-autoschedule.md`
3. [x] Execute plan (TDD) Tasks 1–6
4. [ ] Restart Jarvis and confirm scheduler startup print
5. [ ] Optional: manually run today's AI+Finance fetch if needed

---

## Notes for Next Session (include when relevant)

- Question channel: `AskQuestion`
- Related: `memory-20260827-finance-news-categories.md`, `memory-20260821-daily-fetch-audio-global-lang.md`
- Must restart Jarvis; running process does not have the new scheduler.

---

## References (required)

- `scripts/rag/daily_fetch_schedule.py` — NEWS_ONLY_STEPS, skip-if-done, APScheduler start
- `scripts/rag/routes/daily_fetch.py` — `_run_scheduled_daily_fetch` wrapper → `_run_daily_fetch`
- `scripts/rag/agent.py` — `_start_daily_fetch_scheduler()` before `app.run`
- `tests/test_daily_fetch_schedule.py` — 8 unit tests
- `docs/implementation/personal/daily-fetch-impl.md` — pipeline steps
- `docs/plans/2026-04-17-jarvis-next.md` — §1.2 Daily Fetch Auto-Scheduling (heavier plan; not the contract)
- `docs/plans/2026-08-28-daily-fetch-autoschedule.md` — approved implementation plan

---

**Confirmed at**: 2026-08-28 ~10:15 UTC+8
