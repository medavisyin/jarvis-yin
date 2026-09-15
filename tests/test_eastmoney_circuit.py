"""Unit tests for East Money circuit breaker (half-open recovery)."""

from __future__ import annotations

import os
import sys
import time

_STOCK = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "scripts", "stock"))
if _STOCK not in sys.path:
    sys.path.insert(0, _STOCK)

import eastmoney_throttle as em  # noqa: E402


def setup_function(_fn=None):
    em.reset_for_tests(max_concurrent=2, min_interval_sec=0.0)
    em.reset_circuit_for_tests(failure_threshold=3, open_cooldown_sec=60)


def test_circuit_opens_after_threshold_remote_disconnects():
    err = ConnectionError("Remote end closed connection without response")
    for _ in range(3):
        em.record_eastmoney_failure(err)
    assert em.is_eastmoney_circuit_open() is True


def test_circuit_ignores_unrelated_errors():
    em.record_eastmoney_failure(ValueError("bad payload"))
    em.record_eastmoney_failure(ValueError("bad payload"))
    em.record_eastmoney_failure(ValueError("bad payload"))
    assert em.is_eastmoney_circuit_open() is False


def test_success_resets_circuit():
    err = ConnectionError("RemoteDisconnected")
    for _ in range(3):
        em.record_eastmoney_failure(err)
    assert em.is_eastmoney_circuit_open()
    em.record_eastmoney_success()
    assert em.is_eastmoney_circuit_open() is False


def test_should_skip_eastmoney_when_open():
    err = ConnectionError("RemoteDisconnected")
    for _ in range(3):
        em.record_eastmoney_failure(err)
    assert em.should_skip_eastmoney() is True


def test_half_open_allows_probe_after_cooldown(monkeypatch):
    em.reset_circuit_for_tests(failure_threshold=3, open_cooldown_sec=10)
    err = ConnectionError("RemoteDisconnected")
    for _ in range(3):
        em.record_eastmoney_failure(err)
    assert em.should_skip_eastmoney() is True
    monkeypatch.setattr(em, "_circuit_opened_mono", time.monotonic() - 11)
    assert em.should_skip_eastmoney() is False  # one probe allowed
    assert em.should_skip_eastmoney() is True  # further calls skip until success/fail


def test_is_disconnect_error_matches_known_patterns():
    assert em.is_disconnect_error(ConnectionError("RemoteDisconnected")) is True
    assert em.is_disconnect_error(
        ConnectionError("Remote end closed connection without response")
    ) is True
    assert em.is_disconnect_error(ConnectionError("Connection aborted.")) is True
    assert em.is_disconnect_error(ConnectionResetError("reset")) is True
    assert em.is_disconnect_error(ValueError("empty")) is False


def test_backfill_does_not_consume_half_open_probe(monkeypatch):
    """Gate-only callers must use is_eastmoney_circuit_open, not should_skip."""
    from fetch_resilience import backfill_fund_flow
    import scan_cache

    em.reset_circuit_for_tests(failure_threshold=3, open_cooldown_sec=10)
    for _ in range(3):
        em.record_eastmoney_failure(ConnectionError("RemoteDisconnected"))
    monkeypatch.setattr(em, "_circuit_opened_mono", time.monotonic() - 11)

    scan_cache.reset()
    stock = {"symbol": "600000", "ff_data_missing": True, "ff_signals": {}}
    repaired = backfill_fund_flow([stock], sleep_between=0)
    assert repaired == 0
    # Probe must still be grantable after backfill gate
    assert em.should_skip_eastmoney() is False
    assert em.should_skip_eastmoney() is True


def test_non_disconnect_failure_clears_half_open_pending(monkeypatch):
    em.reset_circuit_for_tests(failure_threshold=3, open_cooldown_sec=10)
    for _ in range(3):
        em.record_eastmoney_failure(ConnectionError("RemoteDisconnected"))
    monkeypatch.setattr(em, "_circuit_opened_mono", time.monotonic() - 11)
    assert em.should_skip_eastmoney() is False  # grant probe
    em.record_eastmoney_failure(ValueError("empty payload"))
    assert em.is_eastmoney_circuit_open() is True
    # Pending cleared: after cooldown again, another probe can be granted
    monkeypatch.setattr(em, "_circuit_opened_mono", time.monotonic() - 11)
    assert em.should_skip_eastmoney() is False


def test_record_empty_response_clears_half_open_pending(monkeypatch):
    em.reset_circuit_for_tests(failure_threshold=3, open_cooldown_sec=10)
    for _ in range(3):
        em.record_eastmoney_failure(ConnectionError("RemoteDisconnected"))
    monkeypatch.setattr(em, "_circuit_opened_mono", time.monotonic() - 11)
    assert em.should_skip_eastmoney() is False
    em.record_eastmoney_empty_response()
    assert em.is_eastmoney_circuit_open() is True
    monkeypatch.setattr(em, "_circuit_opened_mono", time.monotonic() - 11)
    assert em.should_skip_eastmoney() is False
