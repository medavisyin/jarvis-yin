"""Unit tests for 08:00 auto Daily Fetch (AI + Finance + World news)."""

from __future__ import annotations

import os
import sys
from datetime import datetime
from unittest.mock import MagicMock, patch
import threading
import time

import pytest

_SCRIPTS = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "scripts"))
_RAG = os.path.join(_SCRIPTS, "rag")
for _p in (_SCRIPTS, _RAG):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from daily_fetch_schedule import (  # noqa: E402
    AUTO_FETCH_CRON,
    AUTO_FETCH_MISFIRE_GRACE_SECONDS,
    NEWS_ONLY_STEPS,
    _auto_fetch_already_done,
    _daily_fetch_job_running,
    _run_scheduled_daily_fetch,
    _start_daily_fetch_scheduler,
    fire_or_skip_misfire,
    interruptible_sleep,
    make_start_job,
    next_sleep_target,
    poll_due_job,
    scheduler_status,
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
    "world_news_merge",
    "world_news_translate",
    "ai_audio",
    "finance_audio",
}


def test_news_only_steps_include_listen_ready_pipeline():
    assert REQUIRED_AUTO_STEPS <= set(NEWS_ONLY_STEPS)
    assert FORBIDDEN_AUTO_STEPS.isdisjoint(NEWS_ONLY_STEPS)


def test_cron_is_0800_local_with_60s_misfire():
    assert AUTO_FETCH_CRON == {"hour": 8, "minute": 0}
    assert AUTO_FETCH_MISFIRE_GRACE_SECONDS == 60


def test_poke_script_hits_scheduler_api():
    path = os.path.join(_RAG, "poke-daily-fetch.ps1")
    src = open(path, encoding="utf-8").read()
    assert "/api/toolbar/daily-fetch/scheduler" in src
    assert "18889" in src
    assert "task_poke" in src


def test_register_script_is_daily_0800():
    path = os.path.join(_RAG, "register-daily-fetch-task.ps1")
    src = open(path, encoding="utf-8").read()
    assert "08:00" in src
    assert "JarvisDailyFetchPoke" in src
    assert "poke-daily-fetch.ps1" in src


def test_jarvis_start_registers_daily_fetch_task():
    path = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "bin", "jarvis-start.bat"))
    src = open(path, encoding="utf-8").read()
    assert "register-daily-fetch-task.ps1" in src


def test_poll_due_job_already_handled_after_misfire():
    import daily_fetch_schedule as dfs

    job = MagicMock()
    prev_fn, prev_slot = dfs._bound_job_func, dfs._slot_resolved_for
    dfs._bound_job_func = job
    dfs._slot_resolved_for = None
    try:
        with patch("daily_fetch_schedule.AUTO_FETCH_CRON", {"hour": 8, "minute": 0}):
            r1 = poll_due_job(now=datetime(2026, 8, 30, 8, 2, 0))
            r2 = poll_due_job(now=datetime(2026, 8, 30, 8, 3, 0))
        assert r1 == "skipped_misfire"
        assert r2 == "already_handled"
        job.assert_not_called()
    finally:
        dfs._bound_job_func = prev_fn
        dfs._slot_resolved_for = prev_slot


def test_interruptible_sleep_uses_sleeper_chunks():
    slept = []
    stop = threading.Event()
    mono = {"t": 0.0}

    def fake_now():
        return mono["t"]

    def fake_sleep(s):
        slept.append(s)
        mono["t"] += s

    stopped = interruptible_sleep(stop, 2.5, sleeper=fake_sleep, now=fake_now)
    assert stopped is False
    assert slept == [1.0, 1.0, 0.5]


def test_interruptible_sleep_stops_when_event_set():
    stop = threading.Event()
    stop.set()
    slept = []
    stopped = interruptible_sleep(stop, 10, sleeper=slept.append, now=time.monotonic)
    assert stopped is True
    assert slept == []


def test_poll_due_job_idle_without_bound_func():
    import daily_fetch_schedule as dfs

    prev = dfs._bound_job_func
    dfs._bound_job_func = None
    try:
        assert poll_due_job() == "idle"
    finally:
        dfs._bound_job_func = prev


def test_health_route_polls_due_job():
    path = os.path.join(_RAG, "agent.py")
    src = open(path, encoding="utf-8").read()
    assert "poll_due_job" in src
    health_at = src.find("def api_health")
    poll_at = src.find("poll_due_job", health_at)
    assert health_at != -1 and poll_at != -1
    next_def = src.find("\ndef ", health_at + 1)
    assert poll_at < next_def
    now = datetime(2026, 8, 30, 8, 50, 0)
    target = next_sleep_target(now, hour=9, minute=40)
    assert target == datetime(2026, 8, 30, 9, 40, 0)


def test_next_sleep_target_today_if_within_grace():
    now = datetime(2026, 8, 30, 9, 40, 30)
    target = next_sleep_target(now, hour=9, minute=40, grace=60)
    assert target == datetime(2026, 8, 30, 9, 40, 0)


def test_next_sleep_target_tomorrow_if_past_grace():
    now = datetime(2026, 8, 30, 9, 42, 0)
    target = next_sleep_target(now, hour=9, minute=40, grace=60)
    assert target == datetime(2026, 8, 31, 9, 40, 0)


def test_next_sleep_target_tomorrow_after_attempt():
    now = datetime(2026, 8, 30, 9, 40, 1)
    target = next_sleep_target(now, hour=9, minute=40, grace=60, after_attempt=True)
    assert target == datetime(2026, 8, 31, 9, 40, 0)


def test_fire_or_skip_misfire_runs_when_on_time():
    job = MagicMock()
    now = datetime(2026, 8, 30, 9, 40, 5)
    with patch("daily_fetch_schedule.AUTO_FETCH_CRON", {"hour": 9, "minute": 40}):
        result = fire_or_skip_misfire(now, job)
    assert result == "fired"
    job.assert_called_once()


def test_fire_or_skip_misfire_skips_when_too_late():
    job = MagicMock()
    now = datetime(2026, 8, 30, 9, 42, 0)
    with patch("daily_fetch_schedule.AUTO_FETCH_CRON", {"hour": 9, "minute": 40}):
        result = fire_or_skip_misfire(now, job)
    assert result == "skipped_misfire"
    job.assert_not_called()


def test_already_done_requires_ai_mp3_finance_and_world_json(tmp_path):
    today = "2026-08-28"
    day = tmp_path / today
    fn = day / "finance-news"
    wn = day / "world-news"
    fn.mkdir(parents=True)
    wn.mkdir(parents=True)
    assert _auto_fetch_already_done(today, reports_root=str(tmp_path)) is False
    (day / "ai-briefing.mp3").write_bytes(b"x")
    assert _auto_fetch_already_done(today, reports_root=str(tmp_path)) is False
    (fn / "finance-news-data.json").write_text("{}", encoding="utf-8")
    assert _auto_fetch_already_done(today, reports_root=str(tmp_path)) is False
    (wn / "world-news-data.json").write_text("{}", encoding="utf-8")
    assert _auto_fetch_already_done(today, reports_root=str(tmp_path)) is True


def test_job_running_detects_in_progress_statuses():
    jobs = {}
    assert _daily_fetch_job_running(jobs) is False
    jobs["a"] = {"status": "done"}
    assert _daily_fetch_job_running(jobs) is False
    jobs["b"] = {"status": "fetching"}
    assert _daily_fetch_job_running(jobs) is True
    jobs.clear()
    jobs["c"] = {"status": "starting"}
    assert _daily_fetch_job_running(jobs) is True
    jobs.clear()


def test_scheduled_run_skips_when_job_running():
    jobs = {"x": {"status": "fetching"}}
    start_job = MagicMock()
    result = _run_scheduled_daily_fetch(jobs, start_job=start_job, today="2026-08-28")
    assert result == "skipped_running"
    start_job.assert_not_called()


def test_scheduled_run_skips_when_already_done(tmp_path):
    today = "2026-08-28"
    day = tmp_path / today
    (day / "finance-news").mkdir(parents=True)
    (day / "world-news").mkdir(parents=True)
    (day / "ai-briefing.mp3").write_bytes(b"x")
    (day / "finance-news" / "finance-news-data.json").write_text("{}", encoding="utf-8")
    (day / "world-news" / "world-news-data.json").write_text("{}", encoding="utf-8")
    start_job = MagicMock()
    result = _run_scheduled_daily_fetch(
        {},
        reports_root=str(tmp_path),
        start_job=start_job,
        today=today,
    )
    assert result == "skipped_done"
    start_job.assert_not_called()


def test_scheduled_run_starts_news_only_thread(tmp_path):
    today = "2026-08-28"
    jobs = {}
    started = {}

    def _fake_thread(*, target, args, kwargs, daemon):
        started["target"] = target
        started["args"] = args
        started["kwargs"] = kwargs
        started["daemon"] = daemon
        m = MagicMock()
        started["thread"] = m
        return m

    run_daily_fetch = MagicMock()
    start_job = make_start_job(jobs, run_daily_fetch, thread_cls=_fake_thread)
    result = _run_scheduled_daily_fetch(
        jobs,
        reports_root=str(tmp_path),
        start_job=start_job,
        today=today,
    )
    assert result == "started"
    assert started["daemon"] is True
    started["thread"].start.assert_called_once()
    assert started["kwargs"]["only_steps"] == list(NEWS_ONLY_STEPS)
    assert started["kwargs"]["target_date"] == today
    job_id = started["args"][0]
    assert jobs[job_id]["status"] == "starting"
    assert started["target"] is run_daily_fetch


def test_start_scheduler_starts_daemon_thread_once():
    fake_thread = MagicMock()
    fake_thread.is_alive.return_value = True
    import daily_fetch_schedule as dfs

    dfs._scheduler_thread = None
    dfs._stop_event = None
    with (
        patch("daily_fetch_schedule.threading.Thread", return_value=fake_thread) as thread_cls,
        patch("daily_fetch_schedule.atexit"),
    ):
        _start_daily_fetch_scheduler(job_func=dfs._run_scheduled_daily_fetch)
        _start_daily_fetch_scheduler(job_func=dfs._run_scheduled_daily_fetch)
    thread_cls.assert_called_once()
    kwargs = thread_cls.call_args.kwargs
    assert kwargs["target"] is dfs._scheduler_loop
    assert kwargs["daemon"] is True
    fake_thread.start.assert_called_once()
    dfs._scheduler_thread = None
    dfs._stop_event = None


def test_scheduled_run_writes_tick_to_log(tmp_path):
    import daily_fetch_schedule as dfs

    log_path = tmp_path / "daily-fetch-scheduler.log"
    jobs = {"x": {"status": "fetching"}}
    with patch.object(dfs, "_scheduler_log_path", return_value=str(log_path)):
        result = _run_scheduled_daily_fetch(jobs, start_job=MagicMock(), today="2026-08-30")
    assert result == "skipped_running"
    text = log_path.read_text(encoding="utf-8")
    assert "skipped_running" in text
    assert "2026-08-30" in text
    status = dfs.scheduler_status()
    assert status["last_result"] == "skipped_running"
    assert status["last_at"]


def test_scheduler_status_includes_running_and_log_path(tmp_path):
    import daily_fetch_schedule as dfs

    log_path = tmp_path / "sched.log"
    fake = MagicMock()
    fake.is_alive.return_value = True
    dfs._scheduler_thread = fake
    dfs._next_run_at = datetime(2026, 8, 30, 9, 40, 0)
    with patch.object(dfs, "_scheduler_log_path", return_value=str(log_path)):
        status = dfs.scheduler_status()
    assert status["running"] is True
    assert "2026-08-30T09:40:00" in (status.get("next_run") or "")
    assert status["log_path"] == str(log_path)
    dfs._scheduler_thread = None
    dfs._next_run_at = None


def test_schedule_module_docstring_is_0800():
    import daily_fetch_schedule as dfs

    doc = dfs.__doc__ or ""
    assert "08:00" in doc
    assert "09:00" not in doc


def test_scheduled_job_step_mentions_world():
    path = os.path.join(_RAG, "daily_fetch_schedule.py")
    src = open(path, encoding="utf-8").read()
    assert "Scheduled AI+Finance+World fetch" in src


def test_daily_fetch_route_exposes_scheduler_status():
    path = os.path.join(_RAG, "routes", "daily_fetch.py")
    src = open(path, encoding="utf-8").read()
    assert "/api/toolbar/daily-fetch/scheduler" in src
    assert "scheduler_status" in src
    # Static path must be registered before /<job_id>
    sched_at = src.find('"/api/toolbar/daily-fetch/scheduler"')
    job_at = src.find('"/api/toolbar/daily-fetch/<job_id>"')
    assert sched_at != -1 and job_at != -1
    assert sched_at < job_at
