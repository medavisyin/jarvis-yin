"""Board filters for AI scan universe (exclude ChiNext, keep STAR)."""

from __future__ import annotations

import os
import sys

import pandas as pd

_STOCK = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "scripts", "stock"))
if _STOCK not in sys.path:
    sys.path.insert(0, _STOCK)

from board_filters import allow_in_ai_scan, is_chinext, right_side_board_ok  # noqa: E402


def test_is_chinext_prefixes():
    assert is_chinext("300750") is True
    assert is_chinext("301001") is True
    assert is_chinext("688981") is False
    assert is_chinext("600519") is False
    assert is_chinext("000001") is False


def test_allow_in_ai_scan():
    assert allow_in_ai_scan("688981") is True
    assert allow_in_ai_scan("300750") is False
    assert allow_in_ai_scan("301001") is False
    assert allow_in_ai_scan("600519") is True


def test_right_side_board_ok_keeps_star_drops_chinext():
    assert right_side_board_ok("600519") is True
    assert right_side_board_ok("000001") is True
    assert right_side_board_ok("688981") is True
    assert right_side_board_ok("300750") is False
    assert right_side_board_ok("301001") is False


def test_right_side_mask_dataframe():
    df = pd.DataFrame({"代码": ["600519", "300750", "688981", "301001", "000001"]})
    masked = df[df["代码"].apply(right_side_board_ok)]
    assert set(masked["代码"]) == {"600519", "688981", "000001"}
