"""近5年高回踩后再突破 — 纯函数检测器（前复权日线，无网络）。"""
from __future__ import annotations

import math

import pandas as pd

BENCHMARK_LABEL = "近5年高（前复权）"
MIN_BARS = 60
MIN_CONSOLIDATION = 3
SIGNAL_LOOKBACK = 3
LIMIT_UP_MAIN = 9.5
LIMIT_UP_GEM = 19.5


def is_limit_up(symbol: str, change_pct: float | None) -> bool:
    if change_pct is None:
        return False
    try:
        chg = float(change_pct)
    except (TypeError, ValueError):
        return False
    if math.isnan(chg):
        return False
    code = str(symbol).zfill(6)
    thr = LIMIT_UP_GEM if code.startswith(("30", "68")) else LIMIT_UP_MAIN
    return chg >= thr


def _pyfloat(x):
    if x is None:
        return None
    try:
        v = float(x)
    except (TypeError, ValueError):
        return None
    if math.isnan(v):
        return None
    return v


def _bar_date(df: pd.DataFrame, idx: int) -> str | None:
    if "date" not in df.columns:
        return None
    val = df["date"].iloc[idx]
    return str(val)[:10]


def _pct_on_bar(df: pd.DataFrame, idx: int) -> float | None:
    for col in ("pct_change", "涨跌幅", "change_pct"):
        if col in df.columns:
            return _pyfloat(df[col].iloc[idx])
    return None


def _normalize_ohlcv(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    col_map = {
        "日期": "date",
        "开盘": "open",
        "收盘": "close",
        "最高": "high",
        "最低": "low",
        "成交量": "volume",
        "涨跌幅": "pct_change",
        "change_pct": "pct_change",
    }
    out.rename(columns={k: v for k, v in col_map.items() if k in out.columns}, inplace=True)
    for c in ("open", "high", "low", "close", "volume", "pct_change"):
        if c in out.columns:
            out[c] = pd.to_numeric(out[c], errors="coerce")
    if "date" in out.columns:
        out["date"] = pd.to_datetime(out["date"], errors="coerce")
        out = out.sort_values("date").reset_index(drop=True)
    return out


def _empty(stage: str, ok: bool = False, reason: str = "") -> dict:
    return {
        "ok": ok,
        "benchmark_label": BENCHMARK_LABEL,
        "benchmark": None,
        "benchmark_date": None,
        "peak": None,
        "stage": stage,
        "pullback_tags": [],
        "pullback_pct": None,
        "rebreak_date": None,
        "signal_live": False,
        "tradeable": False,
        "limit_up_on_rebreak": False,
        "reason": reason,
    }


def _pullback_state(high, low, close, B: float, T: int, i: int) -> tuple[list[str], float | None, float | None]:
    """Tags and peak using bars T .. i-1 (exclude current i)."""
    if i <= T + 1:
        return [], None, None
    peak = _pyfloat(high[T:i].max())
    pullback_low = _pyfloat(low[T + 1:i].min())
    tags: list[str] = []
    below = False
    for j in range(T + 1, i):
        lj, cj = _pyfloat(low[j]), _pyfloat(close[j])
        if (lj is not None and lj < B) or (cj is not None and cj < B):
            below = True
            break
    if below:
        tags.append("below_high")
    pullback_pct = None
    if peak and peak > 0 and pullback_low is not None:
        pullback_pct = (peak - pullback_low) / peak
        if 0.03 <= pullback_pct <= 0.08:
            tags.append("pct_3_8")
        if 0 < pullback_pct < 0.03:
            tags.append("shallow")
    return tags, peak, pullback_pct


def _triggered(tags: list[str], close_i: float, B: float, peak: float | None) -> bool:
    if not tags:
        return False
    if "below_high" in tags:
        return close_i > B
    if ("pct_3_8" in tags or "shallow" in tags) and peak is not None:
        return close_i > peak
    return False


def _setup_payload(df, B, T, tags, peak, pullback_pct, stage, extra=None) -> dict:
    out = _empty(stage, ok=True)
    out["benchmark"] = _pyfloat(B)
    out["benchmark_date"] = _bar_date(df, T)
    out["peak"] = _pyfloat(peak)
    out["pullback_tags"] = list(tags)
    out["pullback_pct"] = _pyfloat(pullback_pct)
    if extra:
        out.update(extra)
    return out


def detect_five_year_rebreak(df: pd.DataFrame | None, symbol: str = "") -> dict:
    if df is None or len(df) < MIN_BARS:
        return _empty("insufficient_history", ok=False, reason="日线不足 60 根")

    nd = _normalize_ohlcv(df)
    for col in ("high", "low", "close"):
        if col not in nd.columns:
            return _empty("insufficient_history", ok=False, reason="缺 OHLCV 列")

    high = nd["high"].to_numpy(dtype=float)
    low = nd["low"].to_numpy(dtype=float)
    close = nd["close"].to_numpy(dtype=float)
    n = len(nd)

    open_B = None
    open_T = None
    last_rebreak = None

    for i in range(1, n):
        ci = _pyfloat(close[i])
        if ci is None:
            continue

        if open_T is not None and i >= open_T + MIN_CONSOLIDATION:
            tags, peak, ppct = _pullback_state(high, low, close, open_B, open_T, i)
            if _triggered(tags, ci, open_B, peak):
                lu = is_limit_up(symbol, _pct_on_bar(nd, i))
                last_rebreak = {
                    "B": open_B,
                    "T": open_T,
                    "i": i,
                    "tags": tags,
                    "peak": peak,
                    "pullback_pct": ppct,
                    "limit_up": lu,
                }
                open_B, open_T = None, None
                continue

        prior = _pyfloat(high[:i].max())
        if prior is not None and ci > prior:
            open_B = prior
            open_T = i

    if last_rebreak is not None:
        rb_i = last_rebreak["i"]
        live = rb_i >= n - SIGNAL_LOOKBACK
        newer_setup = open_T is not None and open_T > rb_i
        if not newer_setup:
            lu = last_rebreak["limit_up"]
            extra = {
                "rebreak_date": _bar_date(nd, rb_i),
                "signal_live": live,
                "limit_up_on_rebreak": lu,
                "tradeable": bool(live and not lu),
                "reason": "二次突破" if live else "历史二次突破，不是当前买点",
            }
            return _setup_payload(
                nd, last_rebreak["B"], last_rebreak["T"],
                last_rebreak["tags"], last_rebreak["peak"], last_rebreak["pullback_pct"],
                "rebreak", extra,
            )

    if open_T is not None:
        tags, peak, ppct = _pullback_state(high, low, close, open_B, open_T, n)
        later = (n - 1) - open_T
        if later < MIN_CONSOLIDATION:
            stage = "first_break"
            reason = "标杆已立，还不是买点"
        elif tags:
            stage = "pullback"
            reason = "回踩中，等待二次突破"
        else:
            stage = "first_break"
            reason = "标杆已立，还不是买点"
        return _setup_payload(nd, open_B, open_T, tags, peak, ppct, stage, {"reason": reason})

    return _empty("none", ok=True, reason="未见近5年高突破")
