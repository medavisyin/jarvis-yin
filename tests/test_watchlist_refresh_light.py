"""Watchlist refresh is realtime-only (no full update_stock_data)."""

from __future__ import annotations

import os
import sys

_STOCK = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "scripts", "stock"))
if _STOCK not in sys.path:
    sys.path.insert(0, _STOCK)

import watchlist as wl  # noqa: E402


def test_refresh_all_data_only_realtime(monkeypatch):
    monkeypatch.setattr(wl, "list_stocks", lambda: [{"symbol": "600519", "name": "茅台"}])
    calls = []

    def fake_rt(sym, *, heavy_fallback=True):
        calls.append(("rt", sym, heavy_fallback))
        return {"代码": sym, "最新价": 1.0}

    monkeypatch.setattr("fetch_market_data.fetch_realtime_quote", fake_rt)

    def boom_update(sym):
        raise AssertionError("update_stock_data must not run")

    monkeypatch.setattr("fetch_market_data.update_stock_data", boom_update)
    monkeypatch.setattr(wl, "_backfill_watchlist_info", lambda: None)

    results = wl.refresh_all_data()
    assert calls == [("rt", "600519", False)]
    assert results and results[0]["symbol"] == "600519"
    assert results[0]["realtime"] is True


def test_heavy_fallback_false_skips_spot_em(monkeypatch, tmp_path):
    import fetch_market_data as fmd

    monkeypatch.setattr(
        fmd,
        "_fetch_realtime_sina",
        lambda sym: (_ for _ in ()).throw(RuntimeError("sina down")),
    )
    spot_calls = {"n": 0}

    def boom_spot(*a, **k):
        spot_calls["n"] += 1
        raise AssertionError("spot_em must not run when heavy_fallback=False")

    monkeypatch.setattr(fmd.ak, "stock_zh_a_spot_em", boom_spot)
    monkeypatch.setattr(fmd, "_symbol_dir", lambda sym: str(tmp_path / sym))

    try:
        fmd.fetch_realtime_quote("600519", heavy_fallback=False)
        assert False, "expected RuntimeError"
    except RuntimeError as e:
        assert "heavy_fallback=False" in str(e)
    assert spot_calls["n"] == 0


def test_backfill_watchlist_info_uses_local_only(monkeypatch):
    """Refresh-path backfill must pass allow_network=False (no spot_em)."""
    resolve_calls = []

    def spy(sym, *, allow_network=True):
        resolve_calls.append(allow_network)
        return ("本地名", "白酒")

    monkeypatch.setattr(wl, "_resolve_stock_info", spy)
    monkeypatch.setattr(
        wl,
        "_load_raw",
        lambda: {"stocks": [{"symbol": "600519", "name": "", "sector": ""}]},
    )
    monkeypatch.setattr(wl, "_save", lambda d: None)

    wl._backfill_watchlist_info()
    assert resolve_calls == [False]
