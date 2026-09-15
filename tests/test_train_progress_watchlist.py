"""Train progress display must stay aligned with the current watchlist."""

from __future__ import annotations

import os
import sys
from pathlib import Path

_STOCK = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "scripts", "stock"))
if _STOCK not in sys.path:
    sys.path.insert(0, _STOCK)

import watchlist as wl  # noqa: E402

HTML = Path(__file__).resolve().parents[1] / "scripts" / "rag" / "templates" / "index.html"
STOCK_PY = Path(__file__).resolve().parents[1] / "scripts" / "rag" / "routes" / "stock.py"


def _sample_progress():
    return {
        "status": "done",
        "total": 3,
        "completed": 3,
        "results": [
            {"symbol": "002230", "name": "科大讯飞", "predictions": {"close": 41.62}},
            {"symbol": "159570", "name": "创新药HK", "predictions": {"close": 1.43}},
            {"symbol": "588080", "error": "特征数据不足"},
        ],
        "verifications": [
            {"symbol": "002230", "name": "科大讯飞", "actual_close": 41.0},
            {"symbol": "159570", "name": "创新药HK", "actual_close": 1.42},
        ],
        "aggregate_stats": {
            "symbol_count": 3,
            "per_symbol": [
                {"symbol": "002230", "verified": 10},
                {"symbol": "159570", "verified": 2},
            ],
        },
    }


def test_project_drops_symbols_not_on_watchlist():
    stocks = [
        {"symbol": "159570", "name": "创新药HK"},
        {"symbol": "002284", "name": "亚太股份"},
    ]
    out = wl.project_train_progress_to_watchlist(_sample_progress(), stocks)
    symbols = [r["symbol"] for r in out["results"]]
    assert "002230" not in symbols
    assert "588080" not in symbols
    assert symbols == ["159570", "002284"]


def test_project_adds_pending_for_new_watchlist_symbols():
    stocks = [
        {"symbol": "159570", "name": "创新药HK"},
        {"symbol": "002284", "name": "亚太股份"},
    ]
    out = wl.project_train_progress_to_watchlist(_sample_progress(), stocks)
    pending = next(r for r in out["results"] if r["symbol"] == "002284")
    assert pending["pending"] is True
    assert pending["name"] == "亚太股份"
    kept = next(r for r in out["results"] if r["symbol"] == "159570")
    assert "pending" not in kept or kept.get("pending") is not True
    assert kept["predictions"]["close"] == 1.43


def test_project_keeps_watchlist_error_rows():
    stocks = [{"symbol": "588080", "name": "科创50ETF易方达"}]
    out = wl.project_train_progress_to_watchlist(_sample_progress(), stocks)
    assert out["results"] == [
        {"symbol": "588080", "name": "科创50ETF易方达", "error": "特征数据不足"}
    ]


def test_project_filters_verifications_to_watchlist():
    stocks = [{"symbol": "159570", "name": "创新药HK"}]
    out = wl.project_train_progress_to_watchlist(_sample_progress(), stocks)
    assert [v["symbol"] for v in out["verifications"]] == ["159570"]


def test_project_does_not_mutate_input():
    progress = _sample_progress()
    stocks = [{"symbol": "159570", "name": "创新药HK"}]
    wl.project_train_progress_to_watchlist(progress, stocks)
    assert [r["symbol"] for r in progress["results"]] == ["002230", "159570", "588080"]


def test_status_route_projects_to_watchlist():
    text = STOCK_PY.read_text(encoding="utf-8")
    start = text.find("def api_stock_train_status")
    assert start != -1
    fn = text[start:start + 1200]
    assert "project_train_progress_to_watchlist" in fn
    assert "list_stocks" in fn


def test_render_full_train_report_shows_pending_not_yen_zero():
    text = HTML.read_text(encoding="utf-8")
    start = text.find("function renderFullTrainReport")
    end = text.find("// --- National Team ETF Monitor ---")
    assert start != -1 and end > start
    fn = text[start:end]
    assert "待训练" in fn
    assert "r.pending" in fn
    # Must not drop pending/error watchlist rows from the table.
    assert "results.filter(r => !r.error)" not in fn
