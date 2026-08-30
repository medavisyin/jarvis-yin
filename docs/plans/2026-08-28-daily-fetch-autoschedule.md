# Daily Fetch 08:00 Auto-Schedule Implementation Plan

> **For the implementing agent:** Follow this plan task-by-task. Complete each step, verify it works, then move to the next.

**Goal:** When Jarvis is already running, automatically run AI News + Finance News Daily Fetch (fetch, merge/translate, RAG, MP3s) at local 08:00, skipping wiki/Jira/commit and skipping if today's job already ran.

**Architecture:** In-process APScheduler `BackgroundScheduler` with a local-timezone `CronTrigger(hour=8, minute=0)` started from `agent.py` before `app.run`. The job calls existing `_run_daily_fetch(only_steps=NEWS_ONLY_STEPS)` in a daemon thread (same path as continue API). Skip when a fetch is already running, or when today's `ai-briefing.mp3` and `finance-news/finance-news-data.json` exist. `misfire_grace_time=60` so a late Jarvis start does not catch up.

**Tech Stack:** Python 3, APScheduler 3.x (`BackgroundScheduler` + `CronTrigger`), Flask agent (`scripts/rag/agent.py`), Daily Fetch worker (`scripts/rag/routes/daily_fetch.py`), pytest.

**Approved decisions (do not re-litigate):**
- Approach A: APScheduler in-process, not Windows Task Scheduler / cron, not a stdlib sleep loop, not jarvis-next §1.2 (no Global Settings UI, no last-run indicator, no 30-minute retry)
- Deliverable: listen-ready AI + Finance (fetch + merge/translate + RAG + MP3s)
- Skip wiki / Jira / commit; do **not** include `refetch_ai` / `refetch_finance` (those would double-fetch; finance is already inside `fetch_sources` → `run-all-sources.py` Phase 5)
- Missed 08:00 = skip today (`misfire_grace_time=60`)
- Skip if already done today (manual or auto): `ai-briefing.mp3` AND `finance-news/finance-news-data.json` (do **not** require all 6 finance MP3s — empty categories skip audio)
- Every day including weekends; local machine time
- No enable/disable UI; always on when Jarvis runs
- Accept existing `run-all-sources.py` Phase 3.5 Confluence index as part of `fetch_sources` (do not add `--skip-confluence`)
- Same-session plan; implement after plan routing confirmation

**Plan amendments (from critical review — do not re-litigate):**

1. **Lazy-import APScheduler** inside `_start_daily_fetch_scheduler` (not module-level). Task 1 tests must import `routes.daily_fetch` without `apscheduler` installed. Task 3 test patches `apscheduler.schedulers.background.BackgroundScheduler`, not `routes.daily_fetch.BackgroundScheduler`.
2. **Assert `Thread.start()`** in `test_scheduled_run_starts_news_only_thread` — constructor-only asserts would pass if the implementation forgot `t.start()`.
3. **Print scheduler start/failure to stdout** (`print(..., flush=True)`) in addition to `_log`. Agent default logging is WARNING, so `_log.info` may never appear on the Jarvis console (Task 6 checklist would be false).
4. **`datetime` patch target is the class** (`from datetime import datetime`). Keep `patch("routes.daily_fetch.datetime")`.
5. **Residual (accepted, do not expand skip rules):** skip-if-done can skip when finance JSON exists but no finance MP3s were generated. Empty categories already skip audio; requiring `finance-markets.mp3` is out of scope.

---

### Task 1: Skip helper + NEWS_ONLY_STEPS (TDD)

**Files:**
- Create: `tests/test_daily_fetch_schedule.py`
- Modify: `scripts/rag/routes/daily_fetch.py` (constants + helpers near `_daily_fetch_jobs`, around line 368)

**Step 1: Write the failing tests**

```python
"""Unit tests for 08:00 auto Daily Fetch (AI News + Finance News only)."""

from __future__ import annotations

import os
import sys

import pytest

_SCRIPTS = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "scripts"))
_RAG = os.path.join(_SCRIPTS, "rag")
for _p in (_SCRIPTS, _RAG):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from routes.daily_fetch import (  # noqa: E402
    AUTO_FETCH_CRON,
    AUTO_FETCH_MISFIRE_GRACE_SECONDS,
    NEWS_ONLY_STEPS,
    _auto_fetch_already_done,
    _daily_fetch_job_running,
    _daily_fetch_jobs,
)


FORBIDDEN_AUTO_STEPS = {
    "commit_report",
    "jira_daily",
    "wiki_fetch",
    "refetch_ai",
    "refetch_finance",
}

REQUIRED_AUTO_STEPS = {
    "fetch_sources",
    "topic_dedup",
    "ai_learning_knowledge",
    "finance_news_merge",
    "finance_news_translate",
    "ai_audio",
    "finance_audio",
}


def test_news_only_steps_include_listen_ready_pipeline():
    assert REQUIRED_AUTO_STEPS <= set(NEWS_ONLY_STEPS)
    assert FORBIDDEN_AUTO_STEPS.isdisjoint(NEWS_ONLY_STEPS)


def test_cron_is_0800_local_with_60s_misfire():
    assert AUTO_FETCH_CRON == {"hour": 8, "minute": 0}
    assert AUTO_FETCH_MISFIRE_GRACE_SECONDS == 60


def test_already_done_requires_ai_mp3_and_finance_json(tmp_path):
    today = "2026-08-28"
    day = tmp_path / today
    fn = day / "finance-news"
    fn.mkdir(parents=True)
    assert _auto_fetch_already_done(today, reports_root=str(tmp_path)) is False
    (day / "ai-briefing.mp3").write_bytes(b"x")
    assert _auto_fetch_already_done(today, reports_root=str(tmp_path)) is False
    (fn / "finance-news-data.json").write_text("{}", encoding="utf-8")
    assert _auto_fetch_already_done(today, reports_root=str(tmp_path)) is True


def test_job_running_detects_in_progress_statuses():
    _daily_fetch_jobs.clear()
    assert _daily_fetch_job_running() is False
    _daily_fetch_jobs["a"] = {"status": "done"}
    assert _daily_fetch_job_running() is False
    _daily_fetch_jobs["b"] = {"status": "fetching"}
    assert _daily_fetch_job_running() is True
    _daily_fetch_jobs.clear()
    _daily_fetch_jobs["c"] = {"status": "starting"}
    assert _daily_fetch_job_running() is True
    _daily_fetch_jobs.clear()
```

**Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_daily_fetch_schedule.py::test_news_only_steps_include_listen_ready_pipeline tests/test_daily_fetch_schedule.py::test_already_done_requires_ai_mp3_and_finance_json -v`

Expected: FAIL with `ImportError` / `NEWS_ONLY_STEPS` not defined (or similar).

**Step 3: Write minimal implementation**

In `scripts/rag/routes/daily_fetch.py`, immediately after `_daily_fetch_jobs: dict[str, dict] = {}` (line 368):

```python
NEWS_ONLY_STEPS = (
    "fetch_sources",
    "topic_dedup",
    "ai_learning_knowledge",
    "finance_news_merge",
    "finance_news_translate",
    "ai_audio",
    "finance_audio",
)
AUTO_FETCH_CRON = {"hour": 8, "minute": 0}
AUTO_FETCH_MISFIRE_GRACE_SECONDS = 60
_IN_PROGRESS_JOB_STATUSES = frozenset({"starting", "fetching"})


def _auto_fetch_already_done(today: str, reports_root: str | None = None) -> bool:
    """True when today's AI MP3 and finance merge JSON already exist."""
    root = reports_root or REPORTS_ROOT
    output_dir = os.path.join(root, today)
    ai_mp3 = os.path.join(output_dir, "ai-briefing.mp3")
    fn_json = os.path.join(output_dir, "finance-news", "finance-news-data.json")
    return os.path.isfile(ai_mp3) and os.path.isfile(fn_json)


def _daily_fetch_job_running() -> bool:
    return any(
        (j or {}).get("status") in _IN_PROGRESS_JOB_STATUSES
        for j in _daily_fetch_jobs.values()
    )
```

If `from routes.daily_fetch import ...` fails due to circular/heavy imports, extract these symbols into `scripts/rag/daily_fetch_schedule.py` and re-export / import them from `routes/daily_fetch.py`. Prefer keeping them in `daily_fetch.py` if the test import works.

**Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_daily_fetch_schedule.py::test_news_only_steps_include_listen_ready_pipeline tests/test_daily_fetch_schedule.py::test_cron_is_0800_local_with_60s_misfire tests/test_daily_fetch_schedule.py::test_already_done_requires_ai_mp3_and_finance_json tests/test_daily_fetch_schedule.py::test_job_running_detects_in_progress_statuses -v`

Expected: 4 passed.

---

### Task 2: Scheduled job entry (skip / start thread)

**Files:**
- Modify: `tests/test_daily_fetch_schedule.py`
- Modify: `scripts/rag/routes/daily_fetch.py`

**Step 1: Write the failing tests**

Append to `tests/test_daily_fetch_schedule.py`:

```python
from unittest.mock import MagicMock, patch

from routes.daily_fetch import _run_scheduled_daily_fetch  # noqa: E402


def test_scheduled_run_skips_when_job_running():
    _daily_fetch_jobs.clear()
    _daily_fetch_jobs["x"] = {"status": "fetching"}
    with patch("routes.daily_fetch.threading.Thread") as thread_cls:
        _run_scheduled_daily_fetch()
        thread_cls.assert_not_called()
    _daily_fetch_jobs.clear()


def test_scheduled_run_skips_when_already_done(tmp_path):
    today = "2026-08-28"
    day = tmp_path / today
    (day / "finance-news").mkdir(parents=True)
    (day / "ai-briefing.mp3").write_bytes(b"x")
    (day / "finance-news" / "finance-news-data.json").write_text("{}", encoding="utf-8")
    _daily_fetch_jobs.clear()
    with (
        patch("routes.daily_fetch.datetime") as dt,
        patch("routes.daily_fetch.REPORTS_ROOT", str(tmp_path)),
        patch("routes.daily_fetch.threading.Thread") as thread_cls,
    ):
        dt.now.return_value.strftime.return_value = today
        _run_scheduled_daily_fetch()
        thread_cls.assert_not_called()


def test_scheduled_run_starts_news_only_thread(tmp_path):
    today = "2026-08-28"
    _daily_fetch_jobs.clear()
    started = {}

    def _fake_thread(*, target, args, kwargs, daemon):
        started["target"] = target
        started["args"] = args
        started["kwargs"] = kwargs
        started["daemon"] = daemon
        m = MagicMock()
        started["thread"] = m
        return m

    with (
        patch("routes.daily_fetch.datetime") as dt,
        patch("routes.daily_fetch.REPORTS_ROOT", str(tmp_path)),
        patch("routes.daily_fetch.threading.Thread", side_effect=_fake_thread),
        patch("routes.daily_fetch._run_daily_fetch"),
    ):
        dt.now.return_value.strftime.return_value = today
        _run_scheduled_daily_fetch()

    assert started["daemon"] is True
    started["thread"].start.assert_called_once()
    assert started["kwargs"]["only_steps"] == list(NEWS_ONLY_STEPS)
    assert started["kwargs"]["target_date"] == today
    job_id = started["args"][0]
    assert _daily_fetch_jobs[job_id]["status"] == "starting"
```

**Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_daily_fetch_schedule.py::test_scheduled_run_starts_news_only_thread -v`

Expected: FAIL — `_run_scheduled_daily_fetch` not defined.

**Step 3: Write minimal implementation**

Add after `_daily_fetch_job_running`:

```python
def _run_scheduled_daily_fetch():
    """08:00 job: skip if busy/done, else start NEWS_ONLY_STEPS via existing worker."""
    today = datetime.now().strftime("%Y-%m-%d")
    if _daily_fetch_job_running():
        _log.info("Scheduled daily fetch skipped — job already running")
        return
    if _auto_fetch_already_done(today):
        _log.info("Scheduled daily fetch skipped — already done for %s", today)
        return
    job_id = str(_uuid.uuid4())[:8]
    _daily_fetch_jobs[job_id] = {
        "status": "starting",
        "step": "Scheduled 08:00 AI+Finance fetch...",
        "steps": [],
        "files": [],
        "scheduled": True,
    }
    t = threading.Thread(
        target=_run_daily_fetch,
        args=(job_id,),
        kwargs={"only_steps": list(NEWS_ONLY_STEPS), "target_date": today},
        daemon=True,
    )
    t.start()
    _log.info("Scheduled daily fetch started job_id=%s date=%s", job_id, today)
```

**Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_daily_fetch_schedule.py -v -k scheduled_run`

Expected: 3 passed.

---

### Task 3: Start APScheduler (idempotent, misfire 60s)

**Files:**
- Modify: `tests/test_daily_fetch_schedule.py`
- Modify: `scripts/rag/routes/daily_fetch.py`
- Modify: `scripts/rag/requirements-rag.txt`

**Step 1: Add dependency**

Append to `scripts/rag/requirements-rag.txt`:

```
apscheduler>=3.10,<4
```

Install: `python -m pip install "apscheduler>=3.10,<4"`

**Step 2: Write the failing tests**

```python
from routes.daily_fetch import _start_daily_fetch_scheduler  # noqa: E402


def test_start_scheduler_registers_0800_cron_once():
    fake_sched = MagicMock()
    with (
        patch("apscheduler.schedulers.background.BackgroundScheduler", return_value=fake_sched),
        patch("routes.daily_fetch.atexit"),
    ):
        import routes.daily_fetch as df
        df._daily_fetch_scheduler = None
        _start_daily_fetch_scheduler()
        _start_daily_fetch_scheduler()
    fake_sched.add_job.assert_called_once()
    args, kwargs = fake_sched.add_job.call_args
    assert args[0] is df._run_scheduled_daily_fetch
    trigger = kwargs.get("trigger") or (args[1] if len(args) > 1 else None)
    assert trigger is not None
    hour_field = next(f for f in trigger.fields if f.name == "hour")
    minute_field = next(f for f in trigger.fields if f.name == "minute")
    assert "8" in str(hour_field)
    assert str(minute_field).strip() in {"0", "00"} or str(minute_field).startswith("0")
    assert kwargs["misfire_grace_time"] == AUTO_FETCH_MISFIRE_GRACE_SECONDS
    assert kwargs.get("coalesce", True) is True
    assert kwargs["id"] == "daily_fetch_ai_finance"
    fake_sched.start.assert_called_once()
```

**Step 3: Run test to verify it fails**

Run: `python -m pytest tests/test_daily_fetch_schedule.py::test_start_scheduler_registers_0800_cron_once -v`

Expected: FAIL — `_start_daily_fetch_scheduler` / `BackgroundScheduler` not defined.

**Step 4: Write minimal implementation**

Do **not** add module-level `from apscheduler...` (Task 1 imports must work without the package). Lazy-import inside the starter. Add `import atexit` at the top of `daily_fetch.py` with the other stdlib imports.

```python
_daily_fetch_scheduler = None


def _start_daily_fetch_scheduler():
    """Start the 08:00 BackgroundScheduler once. Failures must not block Jarvis."""
    global _daily_fetch_scheduler
    if _daily_fetch_scheduler is not None:
        return _daily_fetch_scheduler
    try:
        from apscheduler.schedulers.background import BackgroundScheduler
        from apscheduler.triggers.cron import CronTrigger

        scheduler = BackgroundScheduler()
        scheduler.add_job(
            _run_scheduled_daily_fetch,
            trigger=CronTrigger(**AUTO_FETCH_CRON),
            id="daily_fetch_ai_finance",
            replace_existing=True,
            misfire_grace_time=AUTO_FETCH_MISFIRE_GRACE_SECONDS,
            coalesce=True,
        )
        scheduler.start()
        atexit.register(lambda: scheduler.shutdown(wait=False))
        _daily_fetch_scheduler = scheduler
        msg = (
            f"Daily fetch scheduler started (08:00 local, "
            f"misfire_grace={AUTO_FETCH_MISFIRE_GRACE_SECONDS}s)"
        )
        _log.info(msg)
        print(msg, flush=True)
        return scheduler
    except Exception as e:
        _log.exception("Daily fetch scheduler failed to start; Jarvis will continue without it")
        print(f"Daily fetch scheduler failed to start: {e}", flush=True)
        _daily_fetch_scheduler = None
        return None
```

Do **not** set `timezone=` unless tests require it — default local tz matches the approved "local machine time" decision.

**Step 5: Run tests**

Run: `python -m pytest tests/test_daily_fetch_schedule.py -v`

Expected: all passed.

---

### Task 4: Hook scheduler into Jarvis startup

**Files:**
- Modify: `scripts/rag/agent.py` (import block ~1586; `if __name__` ~1631)

**Step 1: Import the starter**

In the Daily Fetch import block:

```python
from routes.daily_fetch import (
    daily_fetch_bp,
    _load_recent_ai_news_titles,
    _load_recent_world_news_titles,
    _load_ai_learning_roadmap,
    _load_aws_cert_roadmap,
    _load_aws_cert_progress,
    _format_aws_cert_progress,
    _update_aws_cert_progress,
    _start_daily_fetch_scheduler,
)
```

**Step 2: Start after "Ready", before `app.run`**

```python
    print("Ready! Open your browser.", flush=True)
    _start_daily_fetch_scheduler()
    app.run(host=host, port=port, debug=False, threaded=True)
```

`debug=False` is already set — do not enable the Flask reloader (it would double-start the scheduler).

**Step 3: Smoke-check import**

Run: `python -c "from routes.daily_fetch import _start_daily_fetch_scheduler, NEWS_ONLY_STEPS; print(NEWS_ONLY_STEPS)"` with cwd `scripts/rag`.

Expected: tuple of step names printed; no exception.

Do **not** wait until 08:00. Do **not** run a real fetch in this task.

---

### Task 5: Docs

**Files:**
- Modify: `docs/implementation/personal/daily-fetch-impl.md` (frontmatter `last-updated`; Architecture; Improvement Ideas long-term bullet)
- Modify: `docs/plans/README.md` (add this plan to Active Plans)

**Step 1: Implementation doc**

- Set `last-updated: 2026-08-28`
- In Architecture / System Context, add one sentence: Jarvis process starts APScheduler at 08:00 local and runs `_run_daily_fetch(only_steps=NEWS_ONLY_STEPS)` (AI + Finance listen-ready). Skips if a job is running or today's `ai-briefing.mp3` + `finance-news-data.json` exist. Missed ticks (`misfire_grace_time=60`) are dropped.
- Replace the long-term bullet "Scheduler (Windows Task Scheduler / cron)..." with: **DONE (2026-08-28)**: in-process APScheduler 08:00 local, news-only steps. Not OS cron / Task Scheduler.

**Step 2: Plans index**

Add a row to Active Plans:

`[daily-fetch-autoschedule](2026-08-28-daily-fetch-autoschedule.md)` | Active | 08:00 APScheduler AI+Finance Daily Fetch | `implementation/personal/daily-fetch-impl.md`

---

### Task 6: Full verification

**Step 1: Unit tests**

Run: `python -m pytest tests/test_daily_fetch_schedule.py tests/test_finance_sources.py -v`

Expected: all passed (finance suite is a regression guard; do not "fix" unrelated failures in this task — report them).

**Step 2: Manual checklist (implementer notes, not a live 08:00 wait)**

- [ ] Jarvis starts; log line `Daily fetch scheduler started (08:00 local, misfire_grace=60s)` appears
- [ ] Daily Fetch UI / continue API unchanged for manual full runs
- [ ] Optional dry-run: temporarily call `_run_scheduled_daily_fetch()` from a Python REPL **only if the user asks** — default is not to trigger a real fetch

---

## Out of scope

- Global Settings enable/time UI
- Last auto-run indicator
- Retry 30 minutes after failure
- Windows Task Scheduler XML / cron
- Catch-up when Jarvis starts after 08:00
- `--skip-confluence` on `run-all-sources.py`
- Changing finance source catalog or audio languages
