"""Contract: quality-value Flask routes exist on the stock blueprint."""
from pathlib import Path

STOCK_PY = Path(__file__).resolve().parents[1] / "scripts" / "rag" / "routes" / "stock.py"


def test_stock_routes_include_quality_value():
    text = STOCK_PY.read_text(encoding="utf-8")
    assert "quality_value_scanner" in text
    for path in (
        "/api/stock/quality-value/start",
        "/api/stock/quality-value/status",
        "/api/stock/quality-value/stop",
        "/api/stock/quality-value/result",
        "/api/stock/quality-value/history",
        "/api/stock/quality-value/dates",
    ):
        assert path in text, path
    assert "horizon" in text
