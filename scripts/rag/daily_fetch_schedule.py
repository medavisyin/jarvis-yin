"""08:00 auto Daily Fetch helpers (kept import-light for unit tests)."""

from __future__ import annotations

import atexit
import logging
import os
import threading
import time
import uuid
from datetime import datetime, timedelta
from typing import Callable

_log = logging.getLogger(__name__)

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
_last_tick: dict[str, str | None] = {"at": None, "result": None, "detail": None, "today": None}
_WAIT_CHUNK_SECONDS = 1.0
_HEARTBEAT_SECONDS = 60.0


def _scheduler_log_path() -> str:
    root = os.environ.get("JARVIS_ROOT")
    if not root:
        root = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", ".."))
    return os.path.join(root, "logs", "daily-fetch-scheduler.log")


def _append_scheduler_log(line: str) -> None:
    path = _scheduler_log_path()
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "a", encoding="utf-8") as f:
            f.write(line.rstrip() + "\n")
    except OSError as e:
        _log.warning("Could not write scheduler log %s: %s", path, e)


def _record_tick(result: str, today: str = "", detail: str = "") -> None:
    at = datetime.now().isoformat(timespec="seconds")
    _last_tick["at"] = at
    _last_tick["result"] = result
    _last_tick["detail"] = detail or None
    _last_tick["today"] = today or None
    line = f"{at} result={result} today={today} {detail}".strip()
    _append_scheduler_log(line)
    print(f"Daily fetch scheduler: {line}", flush=True)


def interruptible_sleep(
    stop_event: threading.Event,
    seconds: float,
    *,
    sleeper=time.sleep,
    now=time.monotonic,
) -> bool:
    """Sleep up to `seconds` in 1s chunks. True if stop_event was set."""
    deadline = now() + max(float(seconds), 0.0)
    while not stop_event.is_set():
        left = deadline - now()
        if left <= 0:
            return False
        sleeper(min(left, 1.0))
    return True


def poll_due_job(now: datetime | None = None) -> str:
    """Run the bound job if today's slot is due (safe from HTTP request threads)."""
    global _slot_resolved_for
    func = _bound_job_func
    if func is None:
        return "idle"
    now = now or datetime.now()
    today = now.strftime("%Y-%m-%d")
    if _slot_resolved_for == today:
        return "already_handled"
    result = fire_or_skip_misfire(now, func)
    if result in ("fired", "skipped_misfire"):
        _slot_resolved_for = today
    return result


def next_sleep_target(
    now: datetime | None = None,
    *,
    hour: int | None = None,
    minute: int | None = None,
    grace: int | None = None,
    after_attempt: bool = False,
) -> datetime:
    """Next local fire time. Missed slot past grace → tomorrow (no catch-up)."""
    now = now or datetime.now()
    hour = AUTO_FETCH_CRON["hour"] if hour is None else hour
    minute = AUTO_FETCH_CRON["minute"] if minute is None else minute
    grace = AUTO_FETCH_MISFIRE_GRACE_SECONDS if grace is None else grace
    slot = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if now < slot:
        return slot
    if after_attempt:
        return slot + timedelta(days=1)
    late = (now - slot).total_seconds()
    if late <= grace:
        return slot
    return slot + timedelta(days=1)


def fire_or_skip_misfire(now: datetime, job_func: Callable) -> str:
    """Run job_func if now is at/after today's slot within grace; else skip."""
    hour = AUTO_FETCH_CRON["hour"]
    minute = AUTO_FETCH_CRON["minute"]
    slot = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    late = (now - slot).total_seconds()
    today = now.strftime("%Y-%m-%d")
    if late < 0:
        return "not_due"
    if late > AUTO_FETCH_MISFIRE_GRACE_SECONDS:
        _record_tick("skipped_misfire", today=today, detail=f"late={late:.0f}s")
        return "skipped_misfire"
    job_func()
    return "fired"


def scheduler_status() -> dict:
    thread = _scheduler_thread
    alive = getattr(thread, "is_alive", None)
    running = bool(thread is not None and callable(alive) and alive())
    nrt = _next_run_at
    next_run = nrt.isoformat(timespec="seconds") if nrt is not None else None
    return {
        "running": running,
        "next_run": next_run,
        "last_result": _last_tick.get("result"),
        "last_at": _last_tick.get("at"),
        "log_path": _scheduler_log_path(),
    }


def _auto_fetch_already_done(today: str, reports_root: str | None = None) -> bool:
    """True when today's AI MP3 and finance merge JSON already exist."""
    root = reports_root
    if root is None:
        from config import REPORTS_ROOT

        root = REPORTS_ROOT
    output_dir = os.path.join(root, today)
    ai_mp3 = os.path.join(output_dir, "ai-briefing.mp3")
    fn_json = os.path.join(output_dir, "finance-news", "finance-news-data.json")
    return os.path.isfile(ai_mp3) and os.path.isfile(fn_json)


def _daily_fetch_job_running(jobs: dict | None = None) -> bool:
    jobs = jobs if jobs is not None else {}
    return any(
        (j or {}).get("status") in _IN_PROGRESS_JOB_STATUSES
        for j in jobs.values()
    )


def make_start_job(jobs: dict, run_daily_fetch, thread_cls=threading.Thread):
    """Build a start_job(today) that records a job and starts NEWS_ONLY_STEPS."""

    def start_job(today: str):
        job_id = str(uuid.uuid4())[:8]
        jobs[job_id] = {
            "status": "starting",
            "step": "Scheduled AI+Finance fetch...",
            "steps": [],
            "files": [],
            "scheduled": True,
        }
        t = thread_cls(
            target=run_daily_fetch,
            args=(job_id,),
            kwargs={"only_steps": list(NEWS_ONLY_STEPS), "target_date": today},
            daemon=True,
        )
        t.start()
        _log.info("Scheduled daily fetch started job_id=%s date=%s", job_id, today)

    return start_job


def _run_scheduled_daily_fetch(
    jobs: dict | None = None,
    *,
    reports_root: str | None = None,
    start_job: Callable[[str], None] | None = None,
    today: str | None = None,
):
    """Cron job: skip if busy/done, else call start_job(today)."""
    jobs = jobs if jobs is not None else {}
    if today is None:
        today = datetime.now().strftime("%Y-%m-%d")
    if _daily_fetch_job_running(jobs):
        _log.info("Scheduled daily fetch skipped — job already running")
        _record_tick("skipped_running", today=today)
        return "skipped_running"
    if _auto_fetch_already_done(today, reports_root=reports_root):
        _log.info("Scheduled daily fetch skipped — already done for %s", today)
        _record_tick("skipped_done", today=today)
        return "skipped_done"
    if start_job is None:
        _record_tick("error", today=today, detail="start_job is required")
        raise RuntimeError("start_job is required to run the scheduled daily fetch")
    try:
        start_job(today)
    except Exception as e:
        _record_tick("error", today=today, detail=str(e)[:300])
        raise
    _record_tick("started", today=today)
    return "started"


_scheduler_thread = None
_stop_event = None
_next_run_at = None
_bound_job_func = None
_slot_resolved_for = None


def _scheduler_loop(*, job_func: Callable, stop_event: threading.Event) -> None:
    global _next_run_at
    try:
        after_attempt = False
        last_hb = time.monotonic()
        while not stop_event.is_set():
            now = datetime.now()
            target = next_sleep_target(now, after_attempt=after_attempt)
            after_attempt = False
            _next_run_at = target
            _append_scheduler_log(
                f"{datetime.now().isoformat(timespec='seconds')} result=waiting "
                f"until={target.isoformat(timespec='seconds')}"
            )
            while not stop_event.is_set():
                remaining = (target - datetime.now()).total_seconds()
                if remaining <= 0:
                    break
                if time.monotonic() - last_hb >= _HEARTBEAT_SECONDS:
                    _append_scheduler_log(
                        f"{datetime.now().isoformat(timespec='seconds')} "
                        f"result=heartbeat remaining={remaining:.0f}s "
                        f"until={target.isoformat(timespec='seconds')}"
                    )
                    last_hb = time.monotonic()
                if interruptible_sleep(stop_event, min(remaining, _WAIT_CHUNK_SECONDS)):
                    break
            if stop_event.is_set():
                break
            result = fire_or_skip_misfire(datetime.now(), job_func)
            if result != "not_due":
                after_attempt = True
    except Exception as e:
        _append_scheduler_log(
            f"{datetime.now().isoformat(timespec='seconds')} result=loop_error {e}"
        )
        _log.exception("Daily fetch scheduler loop crashed")


def _start_daily_fetch_scheduler(job_func=None):
    """Start the local-time sleep-loop scheduler once. Failures must not block Jarvis."""
    global _scheduler_thread, _stop_event, _next_run_at, _bound_job_func
    if _scheduler_thread is not None and _scheduler_thread.is_alive():
        return _scheduler_thread
    try:
        _stop_event = threading.Event()
        job = job_func or _run_scheduled_daily_fetch
        _bound_job_func = job
        _next_run_at = next_sleep_target()
        thread = threading.Thread(
            target=_scheduler_loop,
            kwargs={"job_func": job, "stop_event": _stop_event},
            daemon=True,
            name="daily-fetch-scheduler",
        )
        thread.start()
        _scheduler_thread = thread

        def _stop():
            _stop_event.set()

        atexit.register(_stop)
        hhmm = f"{AUTO_FETCH_CRON['hour']:02d}:{AUTO_FETCH_CRON['minute']:02d}"
        msg = (
            f"Daily fetch scheduler started ({hhmm} local, "
            f"misfire_grace={AUTO_FETCH_MISFIRE_GRACE_SECONDS}s, "
            f"next={_next_run_at.isoformat(timespec='seconds')})"
        )
        _log.info(msg)
        print(msg, flush=True)
        _append_scheduler_log(f"{datetime.now().isoformat(timespec='seconds')} result=scheduler_started {msg}")
        return thread
    except Exception as e:
        _log.exception("Daily fetch scheduler failed to start; Jarvis will continue without it")
        print(f"Daily fetch scheduler failed to start: {e}", flush=True)
        _append_scheduler_log(
            f"{datetime.now().isoformat(timespec='seconds')} result=scheduler_failed {e}"
        )
        _scheduler_thread = None
        return None
