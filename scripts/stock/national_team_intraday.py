"""Intraday weak-proxy signal for suspected national-team ETF support.

Public price/volume only — never claims confirmed 国家队 identity.
Spec: session transcript 2026-07-30 (indicator-1 low break + tail settle).
"""

from __future__ import annotations

import json
import logging
import os
from datetime import date, datetime, time, timedelta
from typing import Any

log = logging.getLogger(__name__)

CORE_ETF_CODE = "510300"
CORE_ETF_NAME = "沪深300ETF"
INDEX_CODE = "000001"  # 上证指数
MARKET_CLOSE = time(15, 0)
RECOVERY_GREEN = 0.40
PREMIUM_MAIN_THRESHOLD = 0.10
PREMIUM_CROSS_THRESHOLD = 0.05
PREMIUM_WINDOW_MIN = 5
PREMIUM_NEED_POSITIVE = 3
SYNC_LOOKBACK_MIN = 5
SYNC_MIN_UP = 3
BROAD_SYNC_CODES = (
    "510300", "510500", "510050", "510880",
    "159919", "159915", "512100", "159922", "588000",
)
PREMIUM_CROSS_CODES = (
    "510050", "510500", "510310", "510330", "588000", "159915", "159919",
)
DISCLAIMER = (
    "本信号基于公开行情量价异动计算，仅代表数据特征疑似，"
    "不构成投资建议，不保证真实反映国家队行为。"
)

_STATUS_LABELS = {
    "NO_DATA": "数据不足",
    "NONE": "暂无放量脉冲",
    "RED": "无效护盘",
    "OBSERVING": "数据观察中",
    "YELLOW": "弱护盘",
    "GREEN": "强护盘确认",
}

_RETREAT_STATUS_LABELS = {
    "NO_DATA": "数据不足",
    "NONE": "暂无放量下跌",
    "RED": "下跌未延续",
    "OBSERVING": "下跌观察中",
    "YELLOW": "弱撤退迹象",
    "GREEN": "强撤退疑似",
}


def _default_cache_dir() -> str:
    env = os.environ.get("NT_INTRADAY_CACHE")
    if env:
        return env
    try:
        from config import STOCK_CACHE_DIR

        d = os.path.join(STOCK_CACHE_DIR, ".national_team_intraday")
    except Exception:
        d = os.path.join(os.path.dirname(__file__), "..", "..", "tmp", "_national_team_intraday")
    os.makedirs(d, exist_ok=True)
    return d


def _pulse_path(cache_dir: str | None = None) -> str:
    return os.path.join(cache_dir or _default_cache_dir(), "pulse_state.json")


def _dump_path(cache_dir: str | None = None) -> str:
    return os.path.join(cache_dir or _default_cache_dir(), "dump_state.json")


def _sync_path(cache_dir: str | None = None) -> str:
    return os.path.join(cache_dir or _default_cache_dir(), "sync_state.json")


def load_pulse_state(cache_dir: str | None = None) -> dict | None:
    path = _pulse_path(cache_dir)
    if not os.path.isfile(path):
        return None
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def save_pulse_state(state: dict, cache_dir: str | None = None) -> None:
    path = _pulse_path(cache_dir)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2, default=str)


def load_dump_state(cache_dir: str | None = None) -> dict | None:
    path = _dump_path(cache_dir)
    if not os.path.isfile(path):
        return None
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def save_dump_state(state: dict, cache_dir: str | None = None) -> None:
    path = _dump_path(cache_dir)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2, default=str)


def _clear_state_file_if_stale(path: str, session_date: date) -> bool:
    if not os.path.isfile(path):
        return False
    try:
        with open(path, encoding="utf-8") as f:
            st = json.load(f)
    except Exception:
        return False
    saved = str(st.get("date") or "")
    today = session_date.isoformat()
    if saved and saved != today and saved.replace("-", "") != session_date.strftime("%Y%m%d"):
        try:
            os.remove(path)
        except OSError:
            pass
        return True
    return False


def clear_pulse_if_stale(session_date: date, cache_dir: str | None = None) -> bool:
    """Clear saved pulse when calendar day changes. Returns True if cleared."""
    return _clear_state_file_if_stale(_pulse_path(cache_dir), session_date)


def clear_dump_if_stale(session_date: date, cache_dir: str | None = None) -> bool:
    """Clear saved dump pulse when calendar day changes."""
    return _clear_state_file_if_stale(_dump_path(cache_dir), session_date)


def load_sync_state(cache_dir: str | None = None) -> dict | None:
    path = _sync_path(cache_dir)
    if not os.path.isfile(path):
        return None
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def save_sync_state(state: dict, cache_dir: str | None = None) -> None:
    path = _sync_path(cache_dir)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2, default=str)


def clear_sync_if_stale(session_date: date, cache_dir: str | None = None) -> bool:
    return _clear_state_file_if_stale(_sync_path(cache_dir), session_date)


def _as_dt(v) -> datetime | None:
    if v is None:
        return None
    if isinstance(v, datetime):
        return v
    s = str(v).replace("T", " ")
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y/%m/%d %H:%M:%S"):
        try:
            return datetime.strptime(s[:19], fmt)
        except ValueError:
            continue
    return None


def _rolling_sum_amounts(bars: list[dict], end_idx: int, window: int = 30) -> float:
    start = max(0, end_idx - window + 1)
    return float(sum(float(bars[i].get("amount") or 0) for i in range(start, end_idx + 1)))


def detect_volume_pulse(
    *,
    etf_bars: list[dict],
    yesterday_full_amount: float | None,
    market_shrink: bool = False,
    etf_30m_vs_5d_mean: float | None = None,
    session_date: date | None = None,
    relative_multiple: float = 3.0,
    abs_frac_of_yesterday: float = 0.5,
    window: int = 30,
) -> dict | None:
    """Return first T0 pulse dict or None.

    Trigger A: 30m amount >= yesterday_full * abs_frac_of_yesterday
    Trigger B: market_shrink and 30m amount >= relative_multiple * 5d_mean_30m
      (caller passes etf_30m_vs_5d_mean as the 5d mean for the same window size;
       we compare rolling sum to mean * multiple)
    """
    if not etf_bars:
        return None
    bars = sorted(etf_bars, key=lambda b: _as_dt(b["time"]) or datetime.min)
    for i, bar in enumerate(bars):
        if i + 1 < window:
            continue
        ts = _as_dt(bar["time"])
        if ts is None:
            continue
        if session_date and ts.date() != session_date:
            continue
        win_amt = _rolling_sum_amounts(bars, i, window=window)
        reason = None
        if yesterday_full_amount and yesterday_full_amount > 0:
            if win_amt >= yesterday_full_amount * abs_frac_of_yesterday:
                pct = win_amt / yesterday_full_amount * 100
                reason = f"30分钟成交额达前日全天的{pct:.0f}%"
        if reason is None and market_shrink and etf_30m_vs_5d_mean and etf_30m_vs_5d_mean > 0:
            if win_amt >= relative_multiple * etf_30m_vs_5d_mean:
                reason = (
                    f"大盘缩量背景下30分钟成交约达近5日同期均值的"
                    f"{win_amt / etf_30m_vs_5d_mean:.1f}倍（逆势放量）"
                )
        if reason:
            return {"t0": ts, "reason": reason, "window_amount": win_amt}
    return None


def detect_volume_dump(
    *,
    etf_bars: list[dict],
    yesterday_full_amount: float | None,
    market_shrink: bool = False,
    etf_30m_vs_5d_mean: float | None = None,
    session_date: date | None = None,
    relative_multiple: float = 3.0,
    abs_frac_of_yesterday: float = 0.5,
    window: int = 30,
    index_bars: list[dict] | None = None,
) -> dict | None:
    """First volume pulse that also has a down-window / new-low direction."""
    if not etf_bars:
        return None
    bars = sorted(etf_bars, key=lambda b: _as_dt(b["time"]) or datetime.min)
    for i, bar in enumerate(bars):
        if i + 1 < window:
            continue
        ts = _as_dt(bar["time"])
        if ts is None:
            continue
        if session_date and ts.date() != session_date:
            continue
        win_amt = _rolling_sum_amounts(bars, i, window=window)
        reason = None
        if yesterday_full_amount and yesterday_full_amount > 0:
            if win_amt >= yesterday_full_amount * abs_frac_of_yesterday:
                pct = win_amt / yesterday_full_amount * 100
                reason = f"30分钟成交额达前日全天的{pct:.0f}%（放量下跌）"
        if reason is None and market_shrink and etf_30m_vs_5d_mean and etf_30m_vs_5d_mean > 0:
            if win_amt >= relative_multiple * etf_30m_vs_5d_mean:
                reason = (
                    f"大盘缩量背景下30分钟成交约达近5日同期均值的"
                    f"{win_amt / etf_30m_vs_5d_mean:.1f}倍（放量下跌）"
                )
        if not reason:
            continue
        start = bars[i - window + 1]
        try:
            start_close = float(start["close"])
            end_close = float(bar["close"])
        except (TypeError, ValueError):
            continue
        down_window = end_close < start_close
        new_day_low = False
        if index_bars:
            idx = [b for b in index_bars if (_as_dt(b["time"]) or datetime.min) <= ts]
            if session_date:
                idx = [b for b in idx if (_as_dt(b["time"]) or datetime.min).date() == session_date]
            if idx:
                lows = [float(b["low"]) for b in idx]
                day_low = min(lows)
                end_low = float(bar.get("low") or end_close)
                # ETF bar may not be index; compare index low at/near ts
                idx_at = _bar_exact_or_nearest(index_bars, ts)
                if idx_at is not None:
                    end_low = float(idx_at["low"])
                new_day_low = abs(end_low - day_low) < 1e-9 or end_low <= day_low
        if down_window or new_day_low:
            return {"d0": ts, "reason": reason, "window_amount": win_amt}
    return None


def _hhmm(v) -> str | None:
    dt = v if isinstance(v, datetime) else _as_dt(v)
    return dt.strftime("%H:%M") if dt else None


def build_track_events(
    *,
    pulse_time: datetime | None = None,
    pulse_id: str = "pulse_t0",
    pulse_label: str = "放量脉冲",
    sync_passed: bool = False,
    sync_id: str = "sync_rally",
    sync_label: str = "同步拉升",
    sync_time: datetime | None = None,
) -> list[dict]:
    """Build HH:MM event tags for a track."""
    events: list[dict] = []
    if pulse_time is not None:
        at = _hhmm(pulse_time)
        if at:
            events.append({"id": pulse_id, "label": pulse_label, "at": at})
    if sync_passed:
        at = _hhmm(sync_time) or _hhmm(pulse_time)
        if at:
            events.append({"id": sync_id, "label": sync_label, "at": at})
    return events


def _index_stats_until(index_bars: list[dict], t0: datetime, index_open: float | None):
    bars = [b for b in index_bars if (_as_dt(b["time"]) or datetime.min) <= t0]
    if not bars and index_open is None:
        return None, None
    highs = [float(b["high"]) for b in bars] if bars else []
    lows = [float(b["low"]) for b in bars] if bars else []
    day_high = max(highs) if highs else (float(index_open) if index_open is not None else None)
    day_low = min(lows) if lows else None
    ref = None
    if index_open is not None and day_high is not None:
        ref = max(float(index_open), day_high)
    elif day_high is not None:
        ref = day_high
    elif index_open is not None:
        ref = float(index_open)
    return ref, day_low


def _bar_at_or_after(index_bars: list[dict], ts: datetime) -> dict | None:
    ordered = sorted(index_bars, key=lambda b: _as_dt(b["time"]) or datetime.min)
    for b in ordered:
        bt = _as_dt(b["time"])
        if bt and bt >= ts:
            return b
    return None


def _in_auction_session(ts: datetime) -> bool:
    t = ts.time()
    # PM continuous auction minute bars conventionally start at 13:01 (not 13:00).
    return (time(9, 30) <= t <= time(11, 30)) or (time(13, 1) <= t <= time(15, 0))


def _add_trading_minutes(ts: datetime, n: int) -> datetime | None:
    """Add n minutes within A-share continuous sessions (skip lunch; resume 13:01)."""
    if n < 0:
        return None
    cur = ts
    # If starting in lunch (after 11:30 through 13:00), snap to first PM minute bar
    if time(11, 30) < cur.time() < time(13, 1):
        cur = datetime.combine(cur.date(), time(13, 1))
        if n == 0:
            return cur
    remaining = n
    guard = 0
    while remaining > 0 and guard < 600:
        guard += 1
        cur = cur + timedelta(minutes=1)
        if time(11, 30) < cur.time() < time(13, 1):
            cur = datetime.combine(cur.date(), time(13, 1))
        if not _in_auction_session(cur):
            if cur.time() > time(15, 0):
                return None
            continue
        remaining -= 1
    return cur if remaining == 0 else None


def _bar_for_confirm(
    index_bars: list[dict],
    ts: datetime,
    *,
    max_skew_minutes: int = 1,
) -> dict | None:
    """Bar at target time within [ts, ts+max_skew]; never an arbitrary later bar."""
    if not index_bars:
        return None
    ordered = sorted(index_bars, key=lambda b: _as_dt(b["time"]) or datetime.min)
    end = ts + timedelta(minutes=max_skew_minutes)
    best = None
    best_delta = None
    for b in ordered:
        bt = _as_dt(b["time"])
        if not bt:
            continue
        if bt < ts or bt > end:
            continue
        delta = (bt - ts).total_seconds()
        if best_delta is None or delta < best_delta:
            best = b
            best_delta = delta
    return best


def _bar_exact_or_nearest(index_bars: list[dict], ts: datetime) -> dict | None:
    ordered = sorted(index_bars, key=lambda b: _as_dt(b["time"]) or datetime.min)
    exact = None
    last_before = None
    for b in ordered:
        bt = _as_dt(b["time"])
        if not bt:
            continue
        if bt == ts:
            exact = b
            break
        if bt < ts:
            last_before = b
        if bt > ts and exact is None:
            return b if last_before is None else last_before
    return exact or last_before


def _payload(
    *,
    status: str,
    detect_time: datetime,
    pulse: dict | None = None,
    indicator_1: dict | None = None,
    indicator_2: dict | None = None,
    settled_at_close: bool = False,
    status_detail: str | None = None,
    etf_code: str = CORE_ETF_CODE,
    etf_name: str = CORE_ETF_NAME,
) -> dict:
    i1 = indicator_1 or {"passed": None, "desc": ""}
    i2 = indicator_2 or {"passed": None, "recovery_ratio": None, "desc": ""}
    label = _STATUS_LABELS.get(status, status)
    trigger = None
    if pulse:
        trigger = {
            "reason": pulse.get("reason"),
            "reference_price": pulse.get("reference_price"),
            "day_low_price": pulse.get("day_low"),
            "t0": pulse.get("t0").isoformat(sep=" ") if isinstance(pulse.get("t0"), datetime) else pulse.get("t0"),
        }
    return {
        "detect_time": detect_time.strftime("%Y-%m-%d %H:%M:%S"),
        "etf_code": etf_code,
        "etf_name": etf_name,
        "trigger_detail": trigger,
        "signal": {
            "status": status,
            "status_label": label,
            "status_detail": status_detail,
            "settled_at_close": settled_at_close,
            "indicator_1": i1,
            "indicator_2": i2,
        },
        "disclaimer": DISCLAIMER,
    }


def evaluate_intraday_guard(
    *,
    now: datetime,
    session_date: date,
    yesterday_full_amount: float | None,
    etf_bars: list[dict],
    index_bars: list[dict],
    index_open: float | None,
    forced_pulse: dict | None = None,
    market_shrink: bool = False,
    etf_30m_vs_5d_mean: float | None = None,
    market_close: time = MARKET_CLOSE,
) -> dict:
    """Pure state machine for intraday guard signal."""
    detect_time = now

    # Absolute 50%-of-yesterday trigger needs a baseline; missing is OK (relative path / NONE).
    if yesterday_full_amount is not None and yesterday_full_amount <= 0:
        yesterday_full_amount = None

    if not index_bars:
        return _payload(status="NO_DATA", detect_time=detect_time, status_detail="缺少指数分钟K线")

    # Need enough minute bars for a 15m window conceptually at open
    session_bars = [b for b in index_bars if (_as_dt(b["time"]) or datetime.min).date() == session_date]
    if not session_bars:
        return _payload(status="NO_DATA", detect_time=detect_time, status_detail="当日分钟K不足")
    # Early session: cannot complete a 15m confirmation window yet (auto-detect only)
    if forced_pulse is None and len(session_bars) < 15:
        return _payload(
            status="NO_DATA",
            detect_time=detect_time,
            status_detail="开盘不足15分钟或当日分钟K不足，无法满足观察窗口",
        )

    pulse = None
    if forced_pulse:
        pulse = dict(forced_pulse)
        pulse["t0"] = _as_dt(pulse["t0"])
    else:
        raw = detect_volume_pulse(
            etf_bars=etf_bars,
            yesterday_full_amount=yesterday_full_amount,
            market_shrink=market_shrink,
            etf_30m_vs_5d_mean=etf_30m_vs_5d_mean,
            session_date=session_date,
        )
        if raw:
            ref, day_low = _index_stats_until(index_bars, raw["t0"], index_open)
            if ref is None or day_low is None:
                return _payload(status="NO_DATA", detect_time=detect_time, status_detail="缺少当日最高/最低")
            if abs(ref - day_low) < 1e-9:
                return _payload(status="NO_DATA", detect_time=detect_time, status_detail="参考价与最低价相同，无法算反弹")
            pulse = {
                "t0": raw["t0"],
                "reason": raw["reason"],
                "reference_price": ref,
                "day_low": day_low,
            }

    if not pulse:
        detail = "今日尚未出现放量脉冲"
        if yesterday_full_amount is None:
            detail += "（缺少昨日全天成交额基准，绝对放量阈值暂不可用）"
        return _payload(status="NONE", detect_time=detect_time, status_detail=detail)

    t0 = pulse["t0"]
    day_low = float(pulse["day_low"])
    reference_price = float(pulse["reference_price"])

    t0_plus_1 = _add_trading_minutes(t0, 1)
    if t0_plus_1 is None:
        return _payload(
            status="NO_DATA",
            detect_time=detect_time,
            pulse=pulse,
            status_detail="无法计算T0+1交易分钟",
        )
    bar1 = _bar_for_confirm(index_bars, t0_plus_1)
    if bar1 is None:
        # Wait until first complete minute after T0 exists
        if now < t0_plus_1:
            return _payload(
                status="OBSERVING",
                detect_time=detect_time,
                pulse=pulse,
                indicator_1={"passed": None, "desc": "等待T0+1分钟K线"},
                status_detail="放量止跌初显，等待1分钟确认",
            )
        # now past but bar missing
        return _payload(
            status="NO_DATA",
            detect_time=detect_time,
            pulse=pulse,
            status_detail="缺少T0+1分钟指数K线",
        )

    low1 = float(bar1["low"])
    if low1 < day_low:
        return _payload(
            status="RED",
            detect_time=detect_time,
            pulse=pulse,
            indicator_1={
                "passed": False,
                "desc": f"T0+1min低点{low1:.2f}跌破脉冲时最低{day_low:.2f}",
            },
            indicator_2={"passed": None, "recovery_ratio": None, "desc": "未进入幅度观察"},
            status_detail="放量后指数续创新低，抛压未消化",
        )

    i1 = {"passed": True, "desc": "T0+1min低点未破当日最低"}

    close_dt = datetime.combine(session_date, market_close)
    t0_plus_15 = _add_trading_minutes(t0, 15)
    # None means 15 trading minutes cannot fit before session end → tail settle path
    window_ok = t0_plus_15 is not None and t0_plus_15 <= close_dt

    # Tail: cannot complete 15m before close
    if not window_ok:
        if now < close_dt:
            return _payload(
                status="OBSERVING",
                detect_time=detect_time,
                pulse=pulse,
                indicator_1=i1,
                indicator_2={"passed": None, "recovery_ratio": None, "desc": "临近收盘，窗口不足"},
                settled_at_close=False,
                status_detail="临近收盘，窗口不足，待收盘结算",
            )
        # settle at close
        close_bar = _bar_exact_or_nearest(index_bars, close_dt)
        if close_bar is None:
            return _payload(
                status="NO_DATA",
                detect_time=detect_time,
                pulse=pulse,
                indicator_1=i1,
                status_detail="缺少收盘价",
            )
        settle_px = float(close_bar["close"])
        return _settle_indicator2(
            detect_time=detect_time,
            pulse=pulse,
            i1=i1,
            settle_px=settle_px,
            day_low=day_low,
            reference_price=reference_price,
            settled_at_close=True,
        )

    # Normal path: need full 15 minutes
    if now < t0_plus_15:
        return _payload(
            status="OBSERVING",
            detect_time=detect_time,
            pulse=pulse,
            indicator_1=i1,
            indicator_2={"passed": None, "recovery_ratio": None, "desc": "等待满15分钟"},
            status_detail="放量止跌初显，等待15分钟确认反弹幅度",
        )

    bar15 = _bar_for_confirm(index_bars, t0_plus_15)
    if bar15 is None:
        return _payload(
            status="NO_DATA",
            detect_time=detect_time,
            pulse=pulse,
            indicator_1=i1,
            status_detail="缺少T0+15分钟指数K线",
        )
    settle_px = float(bar15["close"])
    return _settle_indicator2(
        detect_time=detect_time,
        pulse=pulse,
        i1=i1,
        settle_px=settle_px,
        day_low=day_low,
        reference_price=reference_price,
        settled_at_close=False,
    )


def _settle_indicator2(
    *,
    detect_time: datetime,
    pulse: dict,
    i1: dict,
    settle_px: float,
    day_low: float,
    reference_price: float,
    settled_at_close: bool,
) -> dict:
    denom = reference_price - day_low
    if abs(denom) < 1e-9:
        return _payload(
            status="NO_DATA",
            detect_time=detect_time,
            pulse=pulse,
            indicator_1=i1,
            status_detail="参考价与最低价相同，无法算反弹",
            settled_at_close=settled_at_close,
        )
    ratio = (settle_px - day_low) / denom
    i2 = {
        "recovery_ratio": round(ratio, 4),
        "passed": ratio >= RECOVERY_GREEN,
        "desc": f"收复跌幅{ratio * 100:.0f}%",
    }
    if ratio < 0:
        status = "RED"
        detail = "结算价低于脉冲时最低，极度弱势"
        i2["passed"] = False
    elif ratio >= RECOVERY_GREEN:
        status = "GREEN"
        detail = "量价共振确认，疑似国家队主动扫货"
    else:
        status = "YELLOW"
        detail = "护盘力度较弱，仅托底未拉升"
        i2["passed"] = False
    return _payload(
        status=status,
        detect_time=detect_time,
        pulse=pulse,
        indicator_1=i1,
        indicator_2=i2,
        settled_at_close=settled_at_close,
        status_detail=detail,
    )


def premium_pct(price, iopv) -> float | None:
    """(price - IOPV) / IOPV * 100."""
    try:
        p = float(price)
        v = float(iopv)
    except (TypeError, ValueError):
        return None
    if v == 0 or p != p or v != v:  # NaN
        return None
    return round((p - v) / v * 100.0, 4)


def evaluate_sustained_premium(
    *,
    samples: list[dict],
    t0: datetime,
    now: datetime,
    session_date: date,
    main_code: str = CORE_ETF_CODE,
) -> dict:
    """T0 enhancement: 3/5 main samples >0.10% AND cross ETF >0.05% once."""
    empty = {
        "is_sustained": False,
        "etf_code": main_code,
        "sample_count": 0,
        "positive_count": 0,
        "max_premium": None,
        "cross_confirm": False,
        "desc": "",
        "skipped": None,
    }
    open_end = datetime.combine(session_date, time(9, 45))
    if datetime.combine(session_date, time(9, 30)) <= now < open_end:
        empty["skipped"] = "open_window"
        empty["desc"] = "开盘前15分钟不判定持续溢价"
        return empty

    win_end = t0 + timedelta(minutes=PREMIUM_WINDOW_MIN)
    main_by_minute: dict[str, float] = {}
    cross_hit = False
    cross_code = None
    cross_val = None
    for s in samples or []:
        ts = _as_dt(s.get("time"))
        if ts is None or ts < t0 or ts > win_end:
            continue
        code = str(s.get("code") or "")
        try:
            prem = float(s.get("premium_pct"))
        except (TypeError, ValueError):
            continue
        minute_key = ts.strftime("%Y-%m-%d %H:%M")
        if code == main_code:
            # keep max premium in that minute bucket
            prev = main_by_minute.get(minute_key)
            if prev is None or prem > prev:
                main_by_minute[minute_key] = prem
        elif code in PREMIUM_CROSS_CODES and prem > PREMIUM_CROSS_THRESHOLD:
            cross_hit = True
            cross_code = code
            cross_val = prem

    vals = list(main_by_minute.values())
    positive = sum(1 for v in vals if v > PREMIUM_MAIN_THRESHOLD)
    max_p = max(vals) if vals else None
    sustained = positive >= PREMIUM_NEED_POSITIVE and cross_hit and len(vals) >= PREMIUM_NEED_POSITIVE
    desc = ""
    if vals:
        desc = f"{PREMIUM_WINDOW_MIN}分钟内{positive}/{len(vals)}次溢价>{PREMIUM_MAIN_THRESHOLD}%"
        if cross_hit:
            desc += f"，{cross_code}同步出现{cross_val:.2f}%溢价"
        elif not cross_hit:
            desc += "，但缺少跨品种溢价佐证"
    return {
        "is_sustained": bool(sustained),
        "etf_code": main_code,
        "sample_count": len(vals),
        "positive_count": positive,
        "max_premium": max_p,
        "cross_confirm": cross_hit,
        "desc": desc,
        "skipped": None,
    }


def evaluate_sync_rally(
    changes_5m: dict[str, float | None],
    *,
    leader_code: str = CORE_ETF_CODE,
    min_up: int = SYNC_MIN_UP,
) -> dict:
    """≥min_up broad ETFs up in 5m and leader is up and leads (max among ups)."""
    cleaned = {c: float(v) for c, v in (changes_5m or {}).items() if v is not None}
    up_codes = [c for c, v in cleaned.items() if v > 0]
    leader_chg = cleaned.get(leader_code)
    leader_ok = leader_chg is not None and leader_chg > 0
    leads = False
    if leader_ok and up_codes:
        max_up = max(cleaned[c] for c in up_codes)
        leads = leader_chg >= max_up - 1e-9
    passed = len(up_codes) >= min_up and leader_ok and leads
    return {
        "passed": passed,
        "up_count": len(up_codes),
        "up_codes": up_codes,
        "leader_code": leader_code,
        "leader_change_pct": leader_chg,
        "triggered_at": None,
        "desc": (
            f"近{SYNC_LOOKBACK_MIN}分钟{len(up_codes)}只上涨"
            + (f"，{leader_code}领涨{leader_chg:+.2f}%" if leader_ok else f"，{leader_code}未领涨")
        ),
    }


def evaluate_sync_dump(
    changes_5m: dict[str, float | None],
    *,
    leader_code: str = CORE_ETF_CODE,
    min_down: int = SYNC_MIN_UP,
) -> dict:
    """≥min_down broad ETFs down in 5m and leader is down and leads (most negative)."""
    cleaned = {c: float(v) for c, v in (changes_5m or {}).items() if v is not None}
    down_codes = [c for c, v in cleaned.items() if v < 0]
    leader_chg = cleaned.get(leader_code)
    leader_ok = leader_chg is not None and leader_chg < 0
    leads = False
    if leader_ok and down_codes:
        min_down_chg = min(cleaned[c] for c in down_codes)
        leads = leader_chg <= min_down_chg + 1e-9
    passed = len(down_codes) >= min_down and leader_ok and leads
    return {
        "passed": passed,
        "down_count": len(down_codes),
        "down_codes": down_codes,
        "leader_code": leader_code,
        "leader_change_pct": leader_chg,
        "triggered_at": None,
        "desc": (
            f"近{SYNC_LOOKBACK_MIN}分钟{len(down_codes)}只下跌"
            + (f"，{leader_code}领跌{leader_chg:+.2f}%" if leader_ok else f"，{leader_code}未领跌")
        ),
    }


def enrich_guard_labels(signal: dict, *, premium_sustained: bool) -> None:
    """Adjust status_label for GREEN/YELLOW when premium tag applies."""
    st = signal.get("status")
    if st not in ("GREEN", "YELLOW"):
        return
    if premium_sustained:
        if st == "GREEN":
            signal["status_label"] = "强护盘（量价共振 + 抢筹溢价）"
        else:
            signal["status_label"] = "观察（幅度不足，但有资金吸筹痕迹）"
    else:
        if st == "GREEN":
            signal["status_label"] = "弱护盘（量价共振，但无主动抢筹）"


def _retreat_payload(
    *,
    status: str,
    detect_time: datetime,
    dump: dict | None = None,
    indicator_1: dict | None = None,
    indicator_2: dict | None = None,
    settled_at_close: bool = False,
    status_detail: str | None = None,
    etf_code: str = CORE_ETF_CODE,
    etf_name: str = CORE_ETF_NAME,
) -> dict:
    i1 = indicator_1 or {"passed": None, "desc": ""}
    i2 = indicator_2 or {"passed": None, "rebound_ratio": None, "desc": ""}
    label = _RETREAT_STATUS_LABELS.get(status, status)
    trigger = None
    if dump:
        d0 = dump.get("d0")
        trigger = {
            "reason": dump.get("reason"),
            "reference_price": dump.get("reference_price") or dump.get("day_high"),
            "day_high_price": dump.get("day_high"),
            "day_low_price": dump.get("day_low"),
            "d0": d0.isoformat(sep=" ") if isinstance(d0, datetime) else d0,
        }
    return {
        "detect_time": detect_time.strftime("%Y-%m-%d %H:%M:%S"),
        "etf_code": etf_code,
        "etf_name": etf_name,
        "trigger_detail": trigger,
        "signal": {
            "status": status,
            "status_label": label,
            "status_detail": status_detail,
            "settled_at_close": settled_at_close,
            "indicator_1": i1,
            "indicator_2": i2,
        },
        "disclaimer": DISCLAIMER,
    }


def _settle_retreat_indicator2(
    *,
    detect_time: datetime,
    dump: dict,
    i1: dict,
    settle_px: float,
    day_low: float,
    day_high: float,
    settled_at_close: bool,
) -> dict:
    denom = day_high - day_low
    if abs(denom) < 1e-9:
        return _retreat_payload(
            status="NO_DATA",
            detect_time=detect_time,
            dump=dump,
            indicator_1=i1,
            status_detail="参考高点与最低价相同，无法算反弹",
            settled_at_close=settled_at_close,
        )
    rebound = (settle_px - day_low) / denom
    i2 = {
        "rebound_ratio": round(rebound, 4),
        "passed": None,
        "desc": f"反弹幅度{rebound * 100:.0f}%",
    }
    # High rebound = dump failed (RED); weak/new-low = strong retreat (GREEN)
    if settle_px < day_low or rebound < 0.20:
        status = "GREEN"
        detail = "放量后继续偏弱/续创新低，疑似抛压未消化"
        i2["passed"] = True
    elif rebound >= RECOVERY_GREEN:
        status = "RED"
        detail = "放量下跌后快速收回，下跌未延续"
        i2["passed"] = False
    else:
        status = "YELLOW"
        detail = "偏弱但未强化，弱撤退迹象"
        i2["passed"] = False
    return _retreat_payload(
        status=status,
        detect_time=detect_time,
        dump=dump,
        indicator_1=i1,
        indicator_2=i2,
        settled_at_close=settled_at_close,
        status_detail=detail,
    )


def evaluate_intraday_retreat(
    *,
    now: datetime,
    session_date: date,
    yesterday_full_amount: float | None,
    etf_bars: list[dict],
    index_bars: list[dict],
    index_open: float | None,
    forced_dump: dict | None = None,
    market_shrink: bool = False,
    etf_30m_vs_5d_mean: float | None = None,
    market_close: time = MARKET_CLOSE,
) -> dict:
    """Pure state machine for intraday retreat (dump) signal."""
    detect_time = now

    if yesterday_full_amount is not None and yesterday_full_amount <= 0:
        yesterday_full_amount = None

    if not index_bars:
        return _retreat_payload(status="NO_DATA", detect_time=detect_time, status_detail="缺少指数分钟K线")

    session_bars = [b for b in index_bars if (_as_dt(b["time"]) or datetime.min).date() == session_date]
    if not session_bars:
        return _retreat_payload(status="NO_DATA", detect_time=detect_time, status_detail="当日分钟K不足")
    if forced_dump is None and len(session_bars) < 15:
        return _retreat_payload(
            status="NO_DATA",
            detect_time=detect_time,
            status_detail="开盘不足15分钟或当日分钟K不足，无法满足观察窗口",
        )

    dump = None
    if forced_dump:
        dump = dict(forced_dump)
        dump["d0"] = _as_dt(dump.get("d0") or dump.get("t0"))
    else:
        raw = detect_volume_dump(
            etf_bars=etf_bars,
            yesterday_full_amount=yesterday_full_amount,
            market_shrink=market_shrink,
            etf_30m_vs_5d_mean=etf_30m_vs_5d_mean,
            session_date=session_date,
            index_bars=index_bars,
        )
        if raw:
            ref, day_low = _index_stats_until(index_bars, raw["d0"], index_open)
            if ref is None or day_low is None:
                return _retreat_payload(
                    status="NO_DATA", detect_time=detect_time, status_detail="缺少当日最高/最低"
                )
            if abs(ref - day_low) < 1e-9:
                return _retreat_payload(
                    status="NO_DATA",
                    detect_time=detect_time,
                    status_detail="参考高点与最低价相同，无法算反弹",
                )
            dump = {
                "d0": raw["d0"],
                "reason": raw["reason"],
                "reference_price": ref,
                "day_high": ref,
                "day_low": day_low,
            }

    if not dump:
        detail = "今日尚未出现放量下跌脉冲"
        if yesterday_full_amount is None:
            detail += "（缺少昨日全天成交额基准，绝对放量阈值暂不可用）"
        return _retreat_payload(status="NONE", detect_time=detect_time, status_detail=detail)

    d0 = dump["d0"]
    day_low = float(dump["day_low"])
    day_high = float(dump.get("day_high") or dump.get("reference_price"))

    d0_plus_1 = _add_trading_minutes(d0, 1)
    if d0_plus_1 is None:
        return _retreat_payload(
            status="NO_DATA",
            detect_time=detect_time,
            dump=dump,
            status_detail="无法计算D0+1交易分钟",
        )
    bar1 = _bar_for_confirm(index_bars, d0_plus_1)
    if bar1 is None:
        if now < d0_plus_1:
            return _retreat_payload(
                status="OBSERVING",
                detect_time=detect_time,
                dump=dump,
                indicator_1={"passed": None, "desc": "等待D0+1分钟K线"},
                status_detail="放量下跌初显，等待1分钟确认",
            )
        return _retreat_payload(
            status="NO_DATA",
            detect_time=detect_time,
            dump=dump,
            status_detail="缺少D0+1分钟指数K线",
        )

    high1 = float(bar1["high"])
    if high1 > day_high:
        return _retreat_payload(
            status="RED",
            detect_time=detect_time,
            dump=dump,
            indicator_1={
                "passed": False,
                "desc": f"D0+1min高点{high1:.2f}突破脉冲时最高{day_high:.2f}",
            },
            indicator_2={"passed": None, "rebound_ratio": None, "desc": "未进入幅度观察"},
            status_detail="放量后指数快速反弹破前高，下跌未延续",
        )

    i1 = {"passed": True, "desc": "D0+1min高点未破当日最高，下跌延续"}

    close_dt = datetime.combine(session_date, market_close)
    d0_plus_15 = _add_trading_minutes(d0, 15)
    window_ok = d0_plus_15 is not None and d0_plus_15 <= close_dt

    if not window_ok:
        if now < close_dt:
            return _retreat_payload(
                status="OBSERVING",
                detect_time=detect_time,
                dump=dump,
                indicator_1=i1,
                indicator_2={"passed": None, "rebound_ratio": None, "desc": "临近收盘，窗口不足"},
                settled_at_close=False,
                status_detail="临近收盘，窗口不足，待收盘结算",
            )
        close_bar = _bar_exact_or_nearest(index_bars, close_dt)
        if close_bar is None:
            return _retreat_payload(
                status="NO_DATA",
                detect_time=detect_time,
                dump=dump,
                indicator_1=i1,
                status_detail="缺少收盘价",
            )
        return _settle_retreat_indicator2(
            detect_time=detect_time,
            dump=dump,
            i1=i1,
            settle_px=float(close_bar["close"]),
            day_low=day_low,
            day_high=day_high,
            settled_at_close=True,
        )

    if now < d0_plus_15:
        return _retreat_payload(
            status="OBSERVING",
            detect_time=detect_time,
            dump=dump,
            indicator_1=i1,
            indicator_2={"passed": None, "rebound_ratio": None, "desc": "等待满15分钟"},
            status_detail="放量下跌初显，等待15分钟确认弱势是否延续",
        )

    bar15 = _bar_for_confirm(index_bars, d0_plus_15)
    if bar15 is None:
        return _retreat_payload(
            status="NO_DATA",
            detect_time=detect_time,
            dump=dump,
            indicator_1=i1,
            status_detail="缺少D0+15分钟指数K线",
        )
    return _settle_retreat_indicator2(
        detect_time=detect_time,
        dump=dump,
        i1=i1,
        settle_px=float(bar15["close"]),
        day_low=day_low,
        day_high=day_high,
        settled_at_close=False,
    )


def _secid_for_code(code: str) -> str:
    code = str(code)
    if code.startswith(("5", "6", "9")):
        return f"1.{code}"
    return f"0.{code}"


def _http_get_json(url: str, params: dict, timeout: float = 8.0) -> dict | None:
    import requests
    from eastmoney_throttle import eastmoney_slot

    headers = {
        "User-Agent": "Mozilla/5.0",
        "Referer": "https://quote.eastmoney.com/",
    }
    try:
        with eastmoney_slot():
            r = requests.get(url, params=params, headers=headers, timeout=timeout)
        r.raise_for_status()
        return r.json()
    except Exception as e:
        log.warning("东财请求失败 %s: %s", url.split("/")[-1], e)
        return None


def fetch_minute_bars_delay(secid: str, limit: int = 600) -> list[dict]:
    """1-min K via push2delay (fast path when his is blocked)."""
    url = "https://push2delay.eastmoney.com/api/qt/stock/kline/get"
    params = {
        "secid": secid,
        "fields1": "f1,f2,f3,f4,f5,f6",
        "fields2": "f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61",
        "klt": "1",
        "fqt": "0",
        "end": "20500101",
        "lmt": str(limit),
    }
    data = _http_get_json(url, params, timeout=6.0)
    if not data:
        return []
    klines = ((data.get("data") or {}).get("klines")) or []
    bars = []
    for line in klines:
        # time,open,close,high,low,volume,amount,...
        parts = str(line).split(",")
        if len(parts) < 7:
            continue
        ts = _as_dt(parts[0])
        if not ts:
            continue
        try:
            bars.append({
                "time": ts,
                "open": float(parts[1]),
                "close": float(parts[2]),
                "high": float(parts[3]),
                "low": float(parts[4]),
                "amount": float(parts[6] or 0),
            })
        except (TypeError, ValueError):
            continue
    return bars


# --- data fetch + orchestration -------------------------------------------------


def _df_to_bars(df, time_col: str, amount_col: str | None = None) -> list[dict]:
    if df is None or getattr(df, "empty", True):
        return []
    bars = []
    for _, row in df.iterrows():
        ts = _as_dt(row.get(time_col))
        if ts is None:
            continue
        item = {
            "time": ts,
            "open": float(row.get("开盘") or row.get("open") or 0),
            "high": float(row.get("最高") or row.get("high") or 0),
            "low": float(row.get("最低") or row.get("low") or 0),
            "close": float(row.get("收盘") or row.get("close") or 0),
            "amount": 0.0,
        }
        if amount_col and amount_col in row.index:
            try:
                item["amount"] = float(row[amount_col] or 0)
            except (TypeError, ValueError):
                item["amount"] = 0.0
        elif "成交额" in row.index:
            try:
                item["amount"] = float(row["成交额"] or 0)
            except (TypeError, ValueError):
                item["amount"] = 0.0
        bars.append(item)
    return bars


def fetch_etf_minute_bars(symbol: str = CORE_ETF_CODE, period: str = "1") -> list[dict]:
    """Fetch ETF 1-min bars: delay HTTP first, akshare fallback (1 try)."""
    bars = fetch_minute_bars_delay(_secid_for_code(symbol))
    if bars:
        return bars
    try:
        import akshare as ak
        from eastmoney_throttle import eastmoney_slot

        end = datetime.now()
        start = end - timedelta(days=5)
        with eastmoney_slot():
            df = ak.fund_etf_hist_min_em(
                symbol=symbol,
                start_date=start.strftime("%Y-%m-%d %H:%M:%S"),
                end_date=end.strftime("%Y-%m-%d %H:%M:%S"),
                period=period,
                adjust="",
            )
        return _df_to_bars(df, "时间")
    except Exception as e:
        log.warning("ETF分钟K获取失败: %s", e)
        return []


def fetch_index_minute_bars(symbol: str = INDEX_CODE) -> tuple[list[dict], float | None]:
    """Fetch index 1-min bars; delay first then akshare once."""
    secid = f"1.{symbol}" if not str(symbol).startswith(("0.", "1.")) else symbol
    if symbol == "000001":
        secid = "1.000001"
    bars = fetch_minute_bars_delay(secid)
    if bars:
        return bars, bars[0]["open"]
    try:
        import akshare as ak
        from eastmoney_throttle import eastmoney_slot

        end = datetime.now()
        start = end.replace(hour=9, minute=0, second=0, microsecond=0)
        if hasattr(ak, "index_zh_a_hist_min_em"):
            with eastmoney_slot():
                df = ak.index_zh_a_hist_min_em(
                    symbol=symbol,
                    period="1",
                    start_date=start.strftime("%Y-%m-%d %H:%M:%S"),
                    end_date=end.strftime("%Y-%m-%d %H:%M:%S"),
                )
        else:
            df = None
        bars = _df_to_bars(df, "时间")
        open_px = bars[0]["open"] if bars else None
        return bars, open_px
    except Exception as e:
        log.warning("指数分钟K获取失败: %s", e)
        return [], None


def fetch_etf_spot_premiums(codes: list[str] | tuple[str, ...] | None = None) -> dict[str, dict]:
    """Latest price/IOPV/chg via push2delay clist. Returns {code: {price,iopv,premium_pct,chg_pct}}."""
    codes = list(codes or BROAD_SYNC_CODES)
    url = "https://push2delay.eastmoney.com/api/qt/clist/get"
    # f2最新价 f3涨跌幅 f12代码 f14名称 f152? — use f8量比; IOPV often f152 on fund list
    # Eastmoney ETF: f152 量比; IOPV field commonly f161 or from 基金折价率 f156
    params = {
        "pn": "1",
        "pz": "200",
        "po": "1",
        "np": "1",
        "fltt": "2",
        "invt": "2",
        "fid": "f3",
        "fs": "b:MK0021,b:MK0022,b:MK0023,b:MK0024",
        "fields": "f12,f14,f2,f3,f8,f152,f161,f156",
    }
    data = _http_get_json(url, params, timeout=8.0)
    want = set(codes)
    out: dict[str, dict] = {}
    diff = ((data or {}).get("data") or {}).get("diff") or []
    for row in diff:
        code = str(row.get("f12") or "").strip()
        if code not in want:
            continue
        price = row.get("f2")
        iopv = row.get("f161")
        if iopv in (None, "-", ""):
            iopv = row.get("f152")
        prem = premium_pct(price, iopv)
        # if EM gives 折价率 f156 as %, convert: 溢价 = -折价率 when IOPV missing
        if prem is None and row.get("f156") not in (None, "-", ""):
            try:
                prem = -float(row.get("f156"))
            except (TypeError, ValueError):
                prem = None
        try:
            chg = float(row.get("f3"))
        except (TypeError, ValueError):
            chg = None
        out[code] = {
            "price": price,
            "iopv": iopv,
            "premium_pct": prem,
            "chg_pct": chg,
            "name": row.get("f14"),
        }
    return out


def _five_min_changes_from_bars(bars_by_code: dict[str, list[dict]], now: datetime) -> dict[str, float | None]:
    out: dict[str, float | None] = {}
    start = now - timedelta(minutes=SYNC_LOOKBACK_MIN)
    for code, bars in bars_by_code.items():
        session = [b for b in bars if (_as_dt(b["time"]) or datetime.min) <= now]
        if len(session) < 2:
            out[code] = None
            continue
        recent = [b for b in session if (_as_dt(b["time"]) or datetime.min) >= start]
        # Require a true lookback window — do not fall back to stale pre-window bars.
        if len(recent) < 2:
            out[code] = None
            continue
        try:
            a = float(recent[0]["close"])
            b = float(recent[-1]["close"])
            out[code] = round((b - a) / a * 100, 3) if a else None
        except (TypeError, ValueError, ZeroDivisionError):
            out[code] = None
    return out


def _volume_snapshot(etf_bars: list[dict], yesterday_full: float | None, pulse: dict | None) -> dict | None:
    if not etf_bars:
        return None
    bars = sorted(etf_bars, key=lambda b: _as_dt(b["time"]) or datetime.min)
    if not bars:
        return None
    win = _rolling_sum_amounts(bars, len(bars) - 1, window=30)
    pct = None
    if yesterday_full and yesterday_full > 0:
        pct = round(win / yesterday_full * 100, 1)
    return {
        "window_amount": round(win, 2),
        "yesterday_full_amount": yesterday_full,
        "pct_of_yesterday": pct,
        "reason": (pulse or {}).get("reason"),
    }


def _yesterday_etf_amount_from_bars(etf_bars: list[dict], session_date: date) -> float | None:
    by_day: dict[date, float] = {}
    for b in etf_bars:
        ts = _as_dt(b["time"])
        if not ts:
            continue
        by_day[ts.date()] = by_day.get(ts.date(), 0.0) + float(b.get("amount") or 0)
    past = sorted(d for d in by_day if d < session_date)
    if not past:
        return None
    return by_day[past[-1]]


def fetch_etf_daily_amounts(symbol: str = CORE_ETF_CODE, limit: int = 15) -> dict[date, float]:
    """Daily amount: try push2delay day-K, then akshare hist (best-effort)."""
    url = "https://push2delay.eastmoney.com/api/qt/stock/kline/get"
    params = {
        "secid": _secid_for_code(symbol),
        "fields1": "f1,f2,f3,f4,f5,f6",
        "fields2": "f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61",
        "klt": "101",
        "fqt": "0",
        "end": "20500101",
        "lmt": str(limit),
    }
    data = _http_get_json(url, params, timeout=6.0)
    out: dict[date, float] = {}
    for line in ((data or {}).get("data") or {}).get("klines") or []:
        parts = str(line).split(",")
        if len(parts) < 7:
            continue
        ts = _as_dt(parts[0])
        if not ts:
            continue
        try:
            out[ts.date()] = float(parts[6] or 0)
        except (TypeError, ValueError):
            continue
    if out:
        return out
    try:
        import akshare as ak
        from eastmoney_throttle import eastmoney_slot

        with eastmoney_slot():
            df = ak.fund_etf_hist_em(
                symbol=symbol,
                period="daily",
                adjust="",
                start_date=(datetime.now() - timedelta(days=30)).strftime("%Y%m%d"),
                end_date=datetime.now().strftime("%Y%m%d"),
            )
        if df is None or df.empty:
            return out
        date_col = "日期" if "日期" in df.columns else df.columns[0]
        amt_col = "成交额" if "成交额" in df.columns else None
        if not amt_col:
            return out
        for _, row in df.iterrows():
            ts = _as_dt(row.get(date_col))
            if not ts:
                continue
            try:
                out[ts.date()] = float(row.get(amt_col) or 0)
            except (TypeError, ValueError):
                continue
    except Exception as e:
        log.warning("ETF日线成交额获取失败: %s", e)
    return out


def resolve_yesterday_full_amount(
    *,
    etf_bars: list[dict],
    session_date: date,
    daily_amounts: dict[date, float] | None = None,
    symbol: str = CORE_ETF_CODE,
    cache_dir: str | None = None,
) -> float | None:
    """Prefer prior-day minute sum; else daily K; else cached baseline."""
    from_bars = _yesterday_etf_amount_from_bars(etf_bars, session_date)
    if from_bars and from_bars > 0:
        _cache_yesterday_amount(session_date, from_bars, cache_dir=cache_dir)
        return from_bars
    daily = daily_amounts if daily_amounts is not None else fetch_etf_daily_amounts(symbol)
    past = sorted(d for d in daily if d < session_date and (daily.get(d) or 0) > 0)
    if past:
        amt = float(daily[past[-1]])
        _cache_yesterday_amount(session_date, amt, cache_dir=cache_dir)
        return amt
    cached = _load_cached_yesterday_amount(session_date, cache_dir=cache_dir)
    return cached


def _yesterday_cache_path(cache_dir: str | None = None) -> str:
    return os.path.join(cache_dir or _default_cache_dir(), "yesterday_amount.json")


def _cache_yesterday_amount(session_date: date, amount: float, cache_dir: str | None = None) -> None:
    path = _yesterday_cache_path(cache_dir)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    payload = {
        "for_session": session_date.isoformat(),
        "amount": amount,
        "saved_at": datetime.now().isoformat(timespec="seconds"),
    }
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


def _load_cached_yesterday_amount(session_date: date, cache_dir: str | None = None) -> float | None:
    path = _yesterday_cache_path(cache_dir)
    if not os.path.isfile(path):
        return None
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        # reuse if saved for this session day (baseline for today)
        if str(data.get("for_session")) == session_date.isoformat():
            amt = float(data.get("amount") or 0)
            return amt if amt > 0 else None
    except Exception:
        return None
    return None


def _estimate_5d_mean_30m(etf_bars: list[dict], session_date: date, window: int = 30) -> float | None:
    """Rough: mean of each prior day's max rolling-30m amount (last 5 sessions)."""
    by_day: dict[date, list[dict]] = {}
    for b in etf_bars:
        ts = _as_dt(b["time"])
        if not ts or ts.date() >= session_date:
            continue
        by_day.setdefault(ts.date(), []).append(b)
    days = sorted(by_day.keys())[-5:]
    if not days:
        return None
    peaks = []
    for d in days:
        bars = sorted(by_day[d], key=lambda x: _as_dt(x["time"]) or datetime.min)
        best = 0.0
        for i in range(len(bars)):
            if i + 1 < window:
                continue
            best = max(best, _rolling_sum_amounts(bars, i, window=window))
        if best > 0:
            peaks.append(best)
    if not peaks:
        return None
    return sum(peaks) / len(peaks)


def _market_shrink_heuristic(etf_bars: list[dict], session_date: date) -> bool:
    """Proxy: today's cumulative ETF amount so far vs same clock yesterday < 0.85."""
    now_bars = [b for b in etf_bars if (_as_dt(b["time"]) or datetime.min).date() == session_date]
    if not now_bars:
        return False
    today_amt = sum(float(b.get("amount") or 0) for b in now_bars)
    yday = session_date.fromordinal(session_date.toordinal() - 1)
    # find most recent prior session in bars
    prior_dates = sorted(
        {
            (_as_dt(b["time"]).date())
            for b in etf_bars
            if _as_dt(b["time"]) and _as_dt(b["time"]).date() < session_date
        }
    )
    if not prior_dates:
        return False
    y = prior_dates[-1]
    cutoff = now_bars[-1]["time"]
    clock = (_as_dt(cutoff) or datetime.min).time()
    y_amt = sum(
        float(b.get("amount") or 0)
        for b in etf_bars
        if _as_dt(b["time"])
        and _as_dt(b["time"]).date() == y
        and _as_dt(b["time"]).time() <= clock
    )
    if y_amt <= 0:
        return False
    return today_amt < y_amt * 0.85


def national_team_intraday_signal(
    *,
    now: datetime | None = None,
    cache_dir: str | None = None,
    etf_bars: list[dict] | None = None,
    index_bars: list[dict] | None = None,
    index_open: float | None = None,
    yesterday_full_amount: float | None = None,
    spot_premiums: dict | None = None,
    sync_bars_by_code: dict | None = None,
) -> dict:
    """Orchestrate fetch → evaluate support + retreat tracks → persist pulses."""
    now = now or datetime.now()
    session_date = now.date()
    cache_dir = cache_dir or _default_cache_dir()
    clear_pulse_if_stale(session_date, cache_dir=cache_dir)
    clear_dump_if_stale(session_date, cache_dir=cache_dir)
    clear_sync_if_stale(session_date, cache_dir=cache_dir)

    if etf_bars is None:
        etf_bars = fetch_etf_minute_bars(CORE_ETF_CODE)
    if index_bars is None:
        index_bars, fetched_open = fetch_index_minute_bars(INDEX_CODE)
        if index_open is None:
            index_open = fetched_open

    if yesterday_full_amount is None:
        yesterday_full_amount = resolve_yesterday_full_amount(
            etf_bars=etf_bars,
            session_date=session_date,
            symbol=CORE_ETF_CODE,
            cache_dir=cache_dir,
        )

    saved = load_pulse_state(cache_dir) or {}
    forced = None
    if saved and (
        str(saved.get("date")) == session_date.isoformat()
        or str(saved.get("date")) == session_date.strftime("%Y%m%d")
    ):
        forced = {
            "t0": saved.get("t0"),
            "reason": saved.get("reason"),
            "reference_price": saved.get("reference_price"),
            "day_low": saved.get("day_low"),
        }

    saved_dump = load_dump_state(cache_dir) or {}
    forced_dump = None
    if saved_dump and (
        str(saved_dump.get("date")) == session_date.isoformat()
        or str(saved_dump.get("date")) == session_date.strftime("%Y%m%d")
    ):
        forced_dump = {
            "d0": saved_dump.get("d0"),
            "reason": saved_dump.get("reason"),
            "reference_price": saved_dump.get("reference_price"),
            "day_high": saved_dump.get("day_high") or saved_dump.get("reference_price"),
            "day_low": saved_dump.get("day_low"),
        }

    market_shrink = _market_shrink_heuristic(etf_bars, session_date)
    mean5 = _estimate_5d_mean_30m(etf_bars, session_date)

    support = evaluate_intraday_guard(
        now=now,
        session_date=session_date,
        yesterday_full_amount=yesterday_full_amount,
        etf_bars=etf_bars,
        index_bars=index_bars,
        index_open=index_open,
        forced_pulse=forced,
        market_shrink=market_shrink,
        etf_30m_vs_5d_mean=mean5,
    )

    retreat = evaluate_intraday_retreat(
        now=now,
        session_date=session_date,
        yesterday_full_amount=yesterday_full_amount,
        etf_bars=etf_bars,
        index_bars=index_bars,
        index_open=index_open,
        forced_dump=forced_dump,
        market_shrink=market_shrink,
        etf_30m_vs_5d_mean=mean5,
    )

    pulse_for_vol = None
    if support.get("trigger_detail"):
        pulse_for_vol = {
            "reason": support["trigger_detail"].get("reason"),
            "t0": support["trigger_detail"].get("t0"),
        }
    support["volume_pulse"] = _volume_snapshot(etf_bars, yesterday_full_amount, pulse_for_vol)

    dump_for_vol = None
    if retreat.get("trigger_detail"):
        dump_for_vol = {
            "reason": retreat["trigger_detail"].get("reason"),
            "t0": retreat["trigger_detail"].get("d0"),
        }
    retreat["volume_dump"] = _volume_snapshot(etf_bars, yesterday_full_amount, dump_for_vol)

    if spot_premiums is None:
        try:
            spot_premiums = fetch_etf_spot_premiums(list(BROAD_SYNC_CODES) + list(PREMIUM_CROSS_CODES))
        except Exception as e:
            log.warning("ETF spot/溢价获取失败: %s", e)
            spot_premiums = {}

    changes: dict[str, float | None] = {}
    if sync_bars_by_code is not None:
        changes = _five_min_changes_from_bars(sync_bars_by_code, now)
    else:
        by_code = {CORE_ETF_CODE: etf_bars}
        for code in ("510500", "588000", "159915"):
            if code == CORE_ETF_CODE:
                continue
            try:
                by_code[code] = fetch_minute_bars_delay(_secid_for_code(code), limit=120)
            except Exception:
                by_code[code] = []
        changes = _five_min_changes_from_bars(by_code, now)
        # Intentionally no spot day-chg fallback: sync requires true 5-minute changes.

    sync_rally = evaluate_sync_rally(changes)
    sync_dump = evaluate_sync_dump(changes)

    sync_saved = load_sync_state(cache_dir) or {}
    if str(sync_saved.get("date")) not in (
        session_date.isoformat(),
        session_date.strftime("%Y%m%d"),
    ):
        sync_saved = {"date": session_date.isoformat()}

    if sync_rally["passed"]:
        if not sync_saved.get("sync_rally_at"):
            sync_saved["sync_rally_at"] = now.strftime("%Y-%m-%d %H:%M:%S")
        sync_rally["triggered_at"] = _hhmm(sync_saved["sync_rally_at"])
    else:
        sync_rally["triggered_at"] = (
            _hhmm(sync_saved.get("sync_rally_at")) if sync_saved.get("sync_rally_at") else None
        )

    if sync_dump["passed"]:
        if not sync_saved.get("sync_dump_at"):
            sync_saved["sync_dump_at"] = now.strftime("%Y-%m-%d %H:%M:%S")
        sync_dump["triggered_at"] = _hhmm(sync_saved["sync_dump_at"])
    else:
        sync_dump["triggered_at"] = (
            _hhmm(sync_saved.get("sync_dump_at")) if sync_saved.get("sync_dump_at") else None
        )

    sync_saved["date"] = session_date.isoformat()
    save_sync_state(sync_saved, cache_dir=cache_dir)

    support["sync_rally"] = sync_rally
    retreat["sync_dump"] = sync_dump

    premium_samples = list(saved.get("premium_samples") or [])
    t0_dt = None
    td = support.get("trigger_detail")
    if td and td.get("t0"):
        t0_dt = _as_dt(td["t0"])
    if t0_dt and support["signal"]["status"] not in ("NO_DATA", "NONE", "RED"):
        for code, meta in (spot_premiums or {}).items():
            if meta.get("premium_pct") is None:
                continue
            premium_samples.append({
                "time": now.strftime("%Y-%m-%d %H:%M:%S"),
                "code": code,
                "premium_pct": meta["premium_pct"],
            })
        premium_samples = premium_samples[-40:]
        support["premium_signal"] = evaluate_sustained_premium(
            samples=premium_samples,
            t0=t0_dt,
            now=now,
            session_date=session_date,
        )
    else:
        support["premium_signal"] = {
            "is_sustained": False,
            "etf_code": CORE_ETF_CODE,
            "sample_count": 0,
            "positive_count": 0,
            "max_premium": None,
            "cross_confirm": False,
            "desc": "无脉冲或无效护盘，不判定持续溢价",
            "skipped": "no_pulse" if support["signal"]["status"] in ("NONE", "NO_DATA") else "red_or_skip",
        }

    if support["signal"]["status"] in ("GREEN", "YELLOW"):
        enrich_guard_labels(
            support["signal"],
            premium_sustained=bool((support.get("premium_signal") or {}).get("is_sustained")),
        )

    support["events"] = build_track_events(
        pulse_time=t0_dt,
        pulse_id="pulse_t0",
        pulse_label="放量脉冲",
        sync_passed=bool(sync_rally.get("passed")),
        sync_id="sync_rally",
        sync_label="同步拉升",
        sync_time=_as_dt(sync_saved.get("sync_rally_at")) if sync_rally.get("passed") else None,
    )

    d0_dt = None
    rtd = retreat.get("trigger_detail")
    if rtd and rtd.get("d0"):
        d0_dt = _as_dt(rtd["d0"])
    retreat["events"] = build_track_events(
        pulse_time=d0_dt,
        pulse_id="dump_d0",
        pulse_label="放量下跌脉冲",
        sync_passed=bool(sync_dump.get("passed")),
        sync_id="sync_dump",
        sync_label="同步领跌",
        sync_time=_as_dt(sync_saved.get("sync_dump_at")) if sync_dump.get("passed") else None,
    )

    if td and td.get("t0") and support["signal"]["status"] not in ("NO_DATA", "NONE"):
        save_pulse_state(
            {
                "date": session_date.isoformat(),
                "t0": td["t0"],
                "reason": td.get("reason"),
                "reference_price": td.get("reference_price"),
                "day_low": td.get("day_low_price"),
                "last_status": support["signal"]["status"],
                "premium_samples": premium_samples,
            },
            cache_dir=cache_dir,
        )

    if rtd and rtd.get("d0") and retreat["signal"]["status"] not in ("NO_DATA", "NONE"):
        save_dump_state(
            {
                "date": session_date.isoformat(),
                "d0": rtd["d0"],
                "reason": rtd.get("reason"),
                "reference_price": rtd.get("reference_price"),
                "day_high": rtd.get("day_high_price") or rtd.get("reference_price"),
                "day_low": rtd.get("day_low_price"),
                "last_status": retreat["signal"]["status"],
            },
            cache_dir=cache_dir,
        )

    return {
        "detect_time": now.strftime("%Y-%m-%d %H:%M:%S"),
        "disclaimer": DISCLAIMER,
        "support": support,
        "retreat": retreat,
    }
