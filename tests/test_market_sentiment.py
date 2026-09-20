"""Fear & Greed / VIX / radar quotes used by the World monitor Finance panel."""

from __future__ import annotations

import os
import sys

_STOCK = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "scripts", "stock"))
_SCRIPTS = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "scripts"))
for _p in (_SCRIPTS, _STOCK):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from market_sentiment import assemble_radar_signals, parse_yahoo_quote  # noqa: E402


def test_market_sentiment_does_not_import_stock_data_dir():
    """Agent already loaded scripts/config.py, which has no STOCK_DATA_DIR."""
    path = os.path.join(_STOCK, "market_sentiment.py")
    src = open(path, encoding="utf-8").read()
    assert "STOCK_DATA_DIR" not in src


def test_parse_yahoo_quote_uses_regular_market_price():
    payload = {
        "chart": {
            "result": [{
                "meta": {
                    "regularMarketPrice": 2650.12,
                    "previousClose": 2640.0,
                    "symbol": "GC=F",
                },
            }],
        },
    }
    parsed = parse_yahoo_quote(payload)
    assert parsed["value"] == 2650.12
    assert parsed["change_pct"] == 0.38


def test_assemble_radar_signals_merges_sentiment_and_quotes():
    combined = {
        "fear_greed": {"value": 28, "label": "Fear", "source": "alternative.me"},
        "vix": {"value": 22.4, "change_pct": 1.2, "source": "Yahoo Finance"},
        "fetched_at": "2026-09-20T10:00:00",
        "market_mood": {"risk_level": "fear", "signals": ["恐惧"], "recommendation": "观望"},
    }
    quotes = [
        {"id": "gold", "symbol": "GC=F", "label": "Gold", "value": 2650.1, "change_pct": 0.4},
    ]
    out = assemble_radar_signals(combined, quotes)
    assert out["fear_greed"]["value"] == 28
    assert out["vix"]["value"] == 22.4
    assert out["quotes"][0]["id"] == "gold"
    assert out["mood"]["risk_level"] == "fear"
    assert out["fetched_at"] == "2026-09-20T10:00:00"


def test_load_radar_signals_keeps_cached_fg_when_live_fetch_empty(tmp_path, monkeypatch):
    import market_sentiment as ms

    monkeypatch.setattr(ms, "_CACHE_DIR", str(tmp_path))
    (tmp_path / "combined.json").write_text(
        '{"fear_greed": {"value": 56, "label": "Greed", "source": "alternative.me"},'
        ' "vix": {"value": null}, "fetched_at": "2026-01-01T00:00:00",'
        ' "market_mood": {"risk_level": "normal", "signals": [], "recommendation": ""}}',
        encoding="utf-8",
    )
    monkeypatch.setattr(
        ms,
        "fetch_all_sentiment",
        lambda: {
            "fear_greed": {"value": None, "label": "", "source": ""},
            "vix": {"value": None, "change_pct": None, "source": ""},
            "fetched_at": "2026-09-20T12:00:00",
            "market_mood": {"risk_level": "normal", "signals": [], "recommendation": ""},
        },
    )
    monkeypatch.setattr(ms, "fetch_radar_quotes", lambda: [])
    out = ms.load_radar_signals(allow_fetch=True)
    assert out["fear_greed"]["value"] == 56
    assert out["fear_greed"]["label"] == "Greed"
