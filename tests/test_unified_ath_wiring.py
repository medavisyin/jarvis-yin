import inspect
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts" / "stock"))

import unified_scanner
from unified_scanner import merge_unified_payload

_UNIFIED_SRC = Path(__file__).resolve().parents[1] / "scripts" / "stock" / "unified_scanner.py"


def test_unified_docstring_is_left_and_right_only():
    doc = unified_scanner.__doc__ or ""
    assert "left" in doc.lower()
    assert "right" in doc.lower()
    assert "five-year" not in doc.lower()
    assert "ath-rebreak" not in doc.lower()
    assert "three independent reports" not in doc.lower()


def test_merge_unified_payload_is_left_right_only():
    out = merge_unified_payload("2026-08-30", {"date": "left"}, {"picks": []})
    assert out["date"] == "2026-08-30"
    assert out["left"]["date"] == "left"
    assert out["right"]["picks"] == []
    assert "ath" not in out


def test_unified_inner_does_not_start_ath_rebreak():
    src = _UNIFIED_SRC.read_text(encoding="utf-8")
    assert "start_ath_rebreak_scan" not in src
    assert "ath_rebreak_scanner" not in inspect.getsource(unified_scanner._run_unified_inner)

