"""Board / listing filters for AI stock scan universe.

ChiNext (创业板 300/301) is excluded because the user cannot trade it.
STAR (科创板 688/689) remains eligible.
"""

from __future__ import annotations

CHINEXT_PREFIXES = ("300", "301")


def is_chinext(symbol: str) -> bool:
    s = str(symbol or "").strip()
    return s.startswith(CHINEXT_PREFIXES)


def allow_in_ai_scan(symbol: str) -> bool:
    return not is_chinext(symbol)


def right_side_board_ok(symbol: str) -> bool:
    """Right-side Layer-1 board gate: main + STAR, no ChiNext.

    Intentional behavior change vs historical startswith(('60','00','30')):
    keep 688/689 (科创板保留), drop 300/301.
    """
    c = str(symbol or "").strip()
    if is_chinext(c):
        return False
    return c.startswith(("60", "00", "688", "689"))
