import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts" / "stock"))

import unified_scanner
from unified_scanner import merge_unified_payload


def test_unified_docstring_mentions_three_reports():
    doc = unified_scanner.__doc__ or ""
    assert "TWO independent reports" not in doc


def test_merge_unified_payload_has_ath_key():
    out = merge_unified_payload("2026-08-30", {"date": "left"}, {"picks": []}, {"picks": [1]})
    assert out["date"] == "2026-08-30"
    assert out["left"]["date"] == "left"
    assert "ath" in out
    assert out["ath"]["picks"] == [1]
    assert "right" in out
