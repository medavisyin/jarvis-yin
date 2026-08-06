"""Global throttle + circuit breaker for East Money / akshare bursts.

Shared by fund-flow and OHLCV fetch paths so left/right/unified scans
do not stampede the same endpoints. Circuit opens after repeated
RemoteDisconnected-class failures and half-opens after a cooldown.
"""

from __future__ import annotations

import logging
import random
import threading
import time
from contextlib import contextmanager

log = logging.getLogger(__name__)

_DEFAULT_MAX_CONCURRENT = 2
_DEFAULT_MIN_INTERVAL_SEC = 1.0
_DEFAULT_FAILURE_THRESHOLD = 3
_DEFAULT_OPEN_COOLDOWN_SEC = 60.0

_lock = threading.Lock()
_sema: threading.Semaphore | None = None
_max_concurrent = _DEFAULT_MAX_CONCURRENT
_min_interval_sec = _DEFAULT_MIN_INTERVAL_SEC
_last_release_mono = 0.0

# Circuit breaker state (protected by _lock)
_fail_count = 0
_failure_threshold = _DEFAULT_FAILURE_THRESHOLD
_circuit_open = False
_open_cooldown_sec = _DEFAULT_OPEN_COOLDOWN_SEC
_circuit_opened_mono = 0.0
_half_open_probe_pending = False


def reset_circuit_for_tests(
    failure_threshold: int = _DEFAULT_FAILURE_THRESHOLD,
    open_cooldown_sec: float = _DEFAULT_OPEN_COOLDOWN_SEC,
) -> None:
    """Reset circuit breaker state (tests only)."""
    global _fail_count, _failure_threshold, _circuit_open
    global _open_cooldown_sec, _circuit_opened_mono, _half_open_probe_pending
    with _lock:
        _fail_count = 0
        _failure_threshold = max(1, int(failure_threshold))
        _circuit_open = False
        _open_cooldown_sec = max(0.0, float(open_cooldown_sec))
        _circuit_opened_mono = 0.0
        _half_open_probe_pending = False


def reset_for_tests(
    max_concurrent: int = _DEFAULT_MAX_CONCURRENT,
    min_interval_sec: float = _DEFAULT_MIN_INTERVAL_SEC,
) -> None:
    """Reconfigure throttle (tests only). Also resets circuit defaults."""
    global _sema, _max_concurrent, _min_interval_sec, _last_release_mono
    with _lock:
        _max_concurrent = max(1, int(max_concurrent))
        _min_interval_sec = max(0.0, float(min_interval_sec))
        _sema = threading.Semaphore(_max_concurrent)
        _last_release_mono = 0.0
    reset_circuit_for_tests()


def _ensure_sema() -> threading.Semaphore:
    global _sema
    with _lock:
        if _sema is None:
            _sema = threading.Semaphore(_max_concurrent)
        return _sema


@contextmanager
def eastmoney_slot():
    """Acquire a global East Money request slot (concurrency + min interval)."""
    global _last_release_mono
    sema = _ensure_sema()
    sema.acquire()
    try:
        with _lock:
            now = time.monotonic()
            wait = _min_interval_sec - (now - _last_release_mono)
        if wait > 0:
            time.sleep(wait + random.uniform(0, min(0.3, _min_interval_sec * 0.25 + 0.01)))
        yield
    finally:
        with _lock:
            _last_release_mono = time.monotonic()
        sema.release()


def is_disconnect_error(exc: BaseException | None) -> bool:
    """True for RemoteDisconnected / connection-aborted class failures."""
    if exc is None:
        return False
    if isinstance(exc, ConnectionResetError):
        return True
    msg = f"{type(exc).__name__}: {exc}"
    # Unwrap nested args (requests/urllib3 often nest RemoteDisconnected)
    parts = [msg]
    args = getattr(exc, "args", ()) or ()
    for a in args:
        parts.append(str(a))
        if isinstance(a, BaseException):
            parts.append(f"{type(a).__name__}: {a}")
    blob = " ".join(parts)
    needles = (
        "RemoteDisconnected",
        "Remote end closed",
        "Connection aborted",
        "ConnectionResetError",
        "Connection reset",
        "BrokenPipeError",
    )
    return any(n in blob for n in needles)


def record_eastmoney_failure(exc: BaseException | None) -> None:
    """Count disconnect-class failures; open circuit at threshold.

    Always clears half-open probe pending so empty/non-disconnect probe
    outcomes cannot leave the circuit stuck open forever.
    """
    global _fail_count, _circuit_open, _circuit_opened_mono, _half_open_probe_pending
    with _lock:
        was_pending = _half_open_probe_pending
        _half_open_probe_pending = False
        if not is_disconnect_error(exc):
            if was_pending and _circuit_open:
                _circuit_opened_mono = time.monotonic()
                log.info("East Money half-open probe failed (non-disconnect); cooldown reset")
            return
        _fail_count += 1
        if _fail_count >= _failure_threshold and not _circuit_open:
            _circuit_open = True
            _circuit_opened_mono = time.monotonic()
            log.warning(
                "East Money circuit OPEN after %d disconnect failures (cooldown=%.0fs)",
                _fail_count,
                _open_cooldown_sec,
            )
        elif _circuit_open:
            # Failed half-open probe — reset cooldown window
            _circuit_opened_mono = time.monotonic()
            log.info("East Money half-open probe failed; cooldown reset")


def record_eastmoney_empty_response() -> None:
    """Resolve half-open probe after an empty EM payload (no exception)."""
    record_eastmoney_failure(ValueError("empty eastmoney response"))


def record_eastmoney_success() -> None:
    """Reset failure count and close circuit."""
    global _fail_count, _circuit_open, _half_open_probe_pending, _circuit_opened_mono
    with _lock:
        was_open = _circuit_open
        _fail_count = 0
        _circuit_open = False
        _half_open_probe_pending = False
        _circuit_opened_mono = 0.0
        if was_open:
            log.info("East Money circuit CLOSED after successful request")


def is_eastmoney_circuit_open() -> bool:
    with _lock:
        return _circuit_open


def should_skip_eastmoney() -> bool:
    """True when callers should skip EM HTTP.

    When circuit is open and cooldown elapsed, grants exactly one half-open
    probe (returns False once); subsequent calls skip until success/failure
    is recorded.
    """
    global _half_open_probe_pending
    with _lock:
        if not _circuit_open:
            return False
        elapsed = time.monotonic() - _circuit_opened_mono
        if elapsed < _open_cooldown_sec:
            return True
        if _half_open_probe_pending:
            return True
        # Grant one probe
        _half_open_probe_pending = True
        log.info("East Money circuit half-open: allowing one probe")
        return False
