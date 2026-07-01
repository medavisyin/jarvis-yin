"""Shared enrichment cache for unified scanner.

Allows the left (short-term) and right (right-side) scanners to reuse
per-stock enrichment results (fund-flow signals, OHLCV fetch) within a
single unified scan run, avoiding duplicate network fetches.

Lifecycle: call reset() at the start of each unified scan. Thread-safe.
"""
import threading

_lock = threading.Lock()
_ff: dict = {}        # symbol -> stock_fund_flow_signals result
_ohlcv: dict = {}     # symbol -> True once fetch_daily_ohlcv done


def reset():
    with _lock:
        _ff.clear()
        _ohlcv.clear()


def get_ff(symbol: str):
    """Return cached fund-flow signals or None if not cached."""
    with _lock:
        return _ff.get(symbol)


def set_ff(symbol: str, val):
    with _lock:
        _ff[symbol] = val


def has_ff(symbol: str) -> bool:
    with _lock:
        return symbol in _ff


def ohlcv_done(symbol: str) -> bool:
    with _lock:
        return symbol in _ohlcv


def mark_ohlcv(symbol: str):
    with _lock:
        _ohlcv[symbol] = True
