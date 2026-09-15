"""National-team intraday weak-proxy guard signal (state machine)."""

from __future__ import annotations

import os
import sys
from datetime import date, datetime, time, timedelta

_STOCK = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "scripts", "stock"))
if _STOCK not in sys.path:
    sys.path.insert(0, _STOCK)


def _bar(ts: datetime, o, h, l, c, amount=0.0):
    return {"time": ts, "open": o, "high": h, "low": l, "close": c, "amount": amount}


def test_detect_pulse_by_30m_vs_yesterday():
    from national_team_intraday import detect_volume_pulse

    day = date(2026, 7, 30)
    # 30 bars of 1.0 → window sum 30; yesterday full = 50 → 30/50 = 60% >= 50%
    bars = []
    t = datetime(2026, 7, 30, 9, 31)
    for i in range(40):
        bars.append(_bar(t + timedelta(minutes=i), 1, 1, 1, 1, amount=1.0))
    pulse = detect_volume_pulse(
        etf_bars=bars,
        yesterday_full_amount=50.0,
        market_shrink=False,
        etf_30m_vs_5d_mean=1.0,
        session_date=day,
    )
    assert pulse is not None
    assert pulse["reason"].startswith("30分钟成交额")
    assert pulse["t0"] == datetime(2026, 7, 30, 10, 0)  # first end of 30-bar window


def test_detect_pulse_relative_when_market_shrink():
    from national_team_intraday import detect_volume_pulse

    day = date(2026, 7, 30)
    bars = []
    t = datetime(2026, 7, 30, 9, 31)
    for i in range(40):
        bars.append(_bar(t + timedelta(minutes=i), 1, 1, 1, 1, amount=0.1))
    # 30m sum=3; need >= 3 * 5d_mean → set mean=1 so ratio=3
    pulse = detect_volume_pulse(
        etf_bars=bars,
        yesterday_full_amount=1000.0,  # absolute path won't fire
        market_shrink=True,
        etf_30m_vs_5d_mean=1.0,
        session_date=day,
        relative_multiple=3.0,
    )
    assert pulse is not None
    assert "逆势" in pulse["reason"] or "3" in pulse["reason"]


def test_no_data_when_yesterday_amount_missing():
    from national_team_intraday import evaluate_intraday_guard

    # Missing yesterday alone is no longer hard NO_DATA; empty index still is.
    out = evaluate_intraday_guard(
        now=datetime(2026, 7, 30, 10, 30),
        session_date=date(2026, 7, 30),
        yesterday_full_amount=None,
        etf_bars=[],
        index_bars=[],
        index_open=3300.0,
    )
    assert out["signal"]["status"] == "NO_DATA"
    assert "指数" in (out["signal"].get("status_detail") or "")


def test_missing_yesterday_with_index_yields_none_not_no_data():
    from national_team_intraday import evaluate_intraday_guard

    idx = [
        _bar(datetime(2026, 7, 30, 9, 31) + timedelta(minutes=i), 3300, 3300, 3290, 3295)
        for i in range(20)
    ]
    out = evaluate_intraday_guard(
        now=datetime(2026, 7, 30, 10, 30),
        session_date=date(2026, 7, 30),
        yesterday_full_amount=None,
        etf_bars=idx,
        index_bars=idx,
        index_open=3300.0,
    )
    assert out["signal"]["status"] == "NONE"
    assert "昨日" in (out["signal"].get("status_detail") or "")


def test_resolve_yesterday_amount_falls_back_to_daily():
    from national_team_intraday import resolve_yesterday_full_amount

    etf_today_only = [
        _bar(datetime(2026, 7, 30, 10, 0), 1, 1, 1, 1, amount=100),
    ]
    amt = resolve_yesterday_full_amount(
        etf_bars=etf_today_only,
        session_date=date(2026, 7, 30),
        daily_amounts={date(2026, 7, 29): 5.5e8, date(2026, 7, 28): 4e8},
    )
    assert amt == 5.5e8


def test_no_data_when_fewer_than_15_index_bars():
    from national_team_intraday import evaluate_intraday_guard

    idx = []
    t = datetime(2026, 7, 30, 9, 31)
    for i in range(10):
        idx.append(_bar(t + timedelta(minutes=i), 3300, 3300, 3290, 3295))
    out = evaluate_intraday_guard(
        now=datetime(2026, 7, 30, 9, 45),
        session_date=date(2026, 7, 30),
        yesterday_full_amount=100.0,
        etf_bars=idx,
        index_bars=idx,
        index_open=3300.0,
    )
    assert out["signal"]["status"] == "NO_DATA"


def test_red_when_t0_plus_1_breaks_day_low():
    from national_team_intraday import evaluate_intraday_guard

    t0 = datetime(2026, 7, 30, 10, 0)
    # index bars: need open→t0 for ref/high/low, then t0+1min bar that breaks low
    idx = [
        _bar(datetime(2026, 7, 30, 9, 31), 3300, 3300, 3200, 3205),
        _bar(t0, 3205, 3205, 3200, 3201),  # day_low at T0 = 3200
        _bar(t0 + timedelta(minutes=1), 3200, 3200, 3195, 3198),  # low 3195 < 3200
    ]
    etf = [_bar(t0 - timedelta(minutes=i), 1, 1, 1, 1, amount=10.0) for i in range(30, 0, -1)]
    etf.append(_bar(t0, 1, 1, 1, 1, amount=10.0))
    out = evaluate_intraday_guard(
        now=datetime(2026, 7, 30, 10, 5),
        session_date=date(2026, 7, 30),
        yesterday_full_amount=100.0,
        etf_bars=etf,
        index_bars=idx,
        index_open=3300.0,
        forced_pulse={
            "t0": t0,
            "reason": "test",
            "reference_price": 3300.0,
            "day_low": 3200.0,
        },
    )
    assert out["signal"]["status"] == "RED"
    assert out["signal"]["indicator_1"]["passed"] is False


def test_observing_before_15_minutes():
    from national_team_intraday import evaluate_intraday_guard

    t0 = datetime(2026, 7, 30, 10, 0)
    idx = [
        _bar(datetime(2026, 7, 30, 9, 31), 3300, 3300, 3200, 3205),
        _bar(t0, 3205, 3205, 3200, 3201),
        _bar(t0 + timedelta(minutes=1), 3201, 3210, 3200, 3208),  # hold low
        _bar(t0 + timedelta(minutes=5), 3208, 3220, 3205, 3215),
    ]
    out = evaluate_intraday_guard(
        now=datetime(2026, 7, 30, 10, 6),
        session_date=date(2026, 7, 30),
        yesterday_full_amount=100.0,
        etf_bars=[_bar(t0, 1, 1, 1, 1, amount=1)],
        index_bars=idx,
        index_open=3300.0,
        forced_pulse={
            "t0": t0,
            "reason": "test",
            "reference_price": 3300.0,
            "day_low": 3200.0,
        },
    )
    assert out["signal"]["status"] == "OBSERVING"
    assert out["signal"]["indicator_1"]["passed"] is True
    assert out["signal"]["indicator_2"]["passed"] is None


def test_green_after_15m_recover_40pct():
    from national_team_intraday import evaluate_intraday_guard

    t0 = datetime(2026, 7, 30, 10, 0)
    idx = [
        _bar(datetime(2026, 7, 30, 9, 31), 3300, 3300, 3200, 3205),
        _bar(t0, 3205, 3205, 3200, 3201),
        _bar(t0 + timedelta(minutes=1), 3201, 3210, 3200, 3208),
        _bar(t0 + timedelta(minutes=15), 3230, 3245, 3225, 3240),  # (3240-3200)/(3300-3200)=0.4
    ]
    out = evaluate_intraday_guard(
        now=datetime(2026, 7, 30, 10, 20),
        session_date=date(2026, 7, 30),
        yesterday_full_amount=100.0,
        etf_bars=[_bar(t0, 1, 1, 1, 1, amount=1)],
        index_bars=idx,
        index_open=3300.0,
        forced_pulse={
            "t0": t0,
            "reason": "test",
            "reference_price": 3300.0,
            "day_low": 3200.0,
        },
    )
    assert out["signal"]["status"] == "GREEN"
    assert out["signal"]["indicator_2"]["recovery_ratio"] == 0.4
    assert out["signal"]["settled_at_close"] is False


def test_yellow_when_recovery_under_40():
    from national_team_intraday import evaluate_intraday_guard

    t0 = datetime(2026, 7, 30, 10, 0)
    idx = [
        _bar(datetime(2026, 7, 30, 9, 31), 3300, 3300, 3200, 3205),
        _bar(t0, 3205, 3205, 3200, 3201),
        _bar(t0 + timedelta(minutes=1), 3201, 3210, 3200, 3208),
        _bar(t0 + timedelta(minutes=15), 3210, 3220, 3205, 3220),  # 20/100=0.2
    ]
    out = evaluate_intraday_guard(
        now=datetime(2026, 7, 30, 10, 20),
        session_date=date(2026, 7, 30),
        yesterday_full_amount=100.0,
        etf_bars=[_bar(t0, 1, 1, 1, 1, amount=1)],
        index_bars=idx,
        index_open=3300.0,
        forced_pulse={
            "t0": t0,
            "reason": "test",
            "reference_price": 3300.0,
            "day_low": 3200.0,
        },
    )
    assert out["signal"]["status"] == "YELLOW"


def test_tail_observing_then_settle_at_close():
    from national_team_intraday import evaluate_intraday_guard

    t0 = datetime(2026, 7, 30, 14, 50)
    idx = [
        _bar(datetime(2026, 7, 30, 9, 31), 3300, 3300, 3200, 3205),
        _bar(t0, 3205, 3205, 3200, 3201),
        _bar(t0 + timedelta(minutes=1), 3201, 3210, 3200, 3208),
        _bar(datetime(2026, 7, 30, 15, 0), 3230, 3240, 3225, 3240),
    ]
    # before close: observing
    mid = evaluate_intraday_guard(
        now=datetime(2026, 7, 30, 14, 55),
        session_date=date(2026, 7, 30),
        yesterday_full_amount=100.0,
        etf_bars=[_bar(t0, 1, 1, 1, 1, amount=1)],
        index_bars=idx,
        index_open=3300.0,
        forced_pulse={
            "t0": t0,
            "reason": "test",
            "reference_price": 3300.0,
            "day_low": 3200.0,
        },
        market_close=time(15, 0),
    )
    assert mid["signal"]["status"] == "OBSERVING"
    assert "收盘" in (mid["signal"].get("status_label") or "") or "窗口" in (
        mid["signal"].get("status_detail") or mid.get("status_detail") or ""
    ) or mid["signal"].get("settled_at_close") is False

    done = evaluate_intraday_guard(
        now=datetime(2026, 7, 30, 15, 0),
        session_date=date(2026, 7, 30),
        yesterday_full_amount=100.0,
        etf_bars=[_bar(t0, 1, 1, 1, 1, amount=1)],
        index_bars=idx,
        index_open=3300.0,
        forced_pulse={
            "t0": t0,
            "reason": "test",
            "reference_price": 3300.0,
            "day_low": 3200.0,
        },
        market_close=time(15, 0),
    )
    assert done["signal"]["settled_at_close"] is True
    assert done["signal"]["status"] == "GREEN"


def test_negative_recovery_is_red():
    from national_team_intraday import evaluate_intraday_guard

    t0 = datetime(2026, 7, 30, 10, 0)
    idx = [
        _bar(datetime(2026, 7, 30, 9, 31), 3300, 3300, 3200, 3205),
        _bar(t0, 3205, 3205, 3200, 3201),
        _bar(t0 + timedelta(minutes=1), 3201, 3205, 3200, 3202),
        _bar(t0 + timedelta(minutes=15), 3190, 3195, 3185, 3190),  # below day_low
    ]
    out = evaluate_intraday_guard(
        now=datetime(2026, 7, 30, 10, 20),
        session_date=date(2026, 7, 30),
        yesterday_full_amount=100.0,
        etf_bars=[_bar(t0, 1, 1, 1, 1, amount=1)],
        index_bars=idx,
        index_open=3300.0,
        forced_pulse={
            "t0": t0,
            "reason": "test",
            "reference_price": 3300.0,
            "day_low": 3200.0,
        },
    )
    assert out["signal"]["status"] == "RED"


def test_clear_pulse_other_day(monkeypatch, tmp_path):
    from national_team_intraday import load_pulse_state, save_pulse_state, clear_pulse_if_stale

    monkeypatch.setenv("NT_INTRADAY_CACHE", str(tmp_path))
    save_pulse_state(
        {
            "date": "2026-07-29",
            "t0": "2026-07-29T14:50:00",
            "reference_price": 3300,
            "day_low": 3200,
            "reason": "old",
        },
        cache_dir=str(tmp_path),
    )
    assert clear_pulse_if_stale(date(2026, 7, 30), cache_dir=str(tmp_path)) is True
    assert load_pulse_state(cache_dir=str(tmp_path)) is None


def test_premium_pct_from_price_iopv():
    from national_team_intraday import premium_pct

    assert premium_pct(10.01, 10.0) == 0.1
    assert premium_pct(9.99, 10.0) == -0.1
    assert premium_pct(10.0, None) is None
    assert premium_pct(10.0, 0) is None


def test_evaluate_sustained_premium_3_of_5_and_cross():
    from national_team_intraday import evaluate_sustained_premium

    t0 = datetime(2026, 7, 30, 10, 0)
    samples = []
    for i, p in enumerate([0.12, 0.05, 0.15, 0.11, 0.12]):
        samples.append({"time": t0 + timedelta(minutes=i), "code": "510300", "premium_pct": p})
    samples.append({"time": t0 + timedelta(minutes=2), "code": "510050", "premium_pct": 0.06})
    out = evaluate_sustained_premium(
        samples=samples,
        t0=t0,
        now=t0 + timedelta(minutes=5),
        session_date=date(2026, 7, 30),
    )
    assert out["is_sustained"] is True
    assert out["positive_count"] >= 3
    assert out["cross_confirm"] is True


def test_evaluate_sustained_premium_skips_open_auction_window():
    from national_team_intraday import evaluate_sustained_premium

    t0 = datetime(2026, 7, 30, 9, 35)
    samples = [{"time": t0, "code": "510300", "premium_pct": 0.5}]
    out = evaluate_sustained_premium(
        samples=samples,
        t0=t0,
        now=t0 + timedelta(minutes=3),
        session_date=date(2026, 7, 30),
    )
    assert out["is_sustained"] is False
    assert out.get("skipped") == "open_window"


def test_evaluate_sync_rally_leader_and_three_up():
    from national_team_intraday import evaluate_sync_rally

    out = evaluate_sync_rally(
        {
            "510300": 0.8,
            "510500": 0.3,
            "588000": 0.2,
            "159915": -0.1,
        }
    )
    assert out["passed"] is True
    assert out["up_count"] == 3
    assert out["leader_code"] == "510300"


def test_evaluate_sync_rally_fails_without_leader():
    from national_team_intraday import evaluate_sync_rally

    out = evaluate_sync_rally(
        {
            "510300": -0.1,
            "510500": 0.3,
            "588000": 0.2,
            "159915": 0.1,
        }
    )
    assert out["passed"] is False


def test_enrich_status_label_green_with_premium():
    from national_team_intraday import enrich_guard_labels

    sig = {"status": "GREEN", "status_label": "强护盘确认"}
    enrich_guard_labels(sig, premium_sustained=True)
    assert "抢筹溢价" in sig["status_label"]


# --- Retreat track (dump pulse + sync dump + dual events) ---


def test_detect_dump_requires_volume_and_down_window():
    from national_team_intraday import detect_volume_dump

    day = date(2026, 8, 3)
    t = datetime(2026, 8, 3, 9, 31)
    # Rising closes → volume alone must NOT dump
    up_bars = []
    for i in range(40):
        px = 1.0 + i * 0.01
        up_bars.append(_bar(t + timedelta(minutes=i), px, px, px, px, amount=1.0))
    assert detect_volume_dump(
        etf_bars=up_bars,
        yesterday_full_amount=50.0,
        session_date=day,
    ) is None

    # Falling closes + same volume → dump
    down_bars = []
    for i in range(40):
        px = 2.0 - i * 0.01
        down_bars.append(_bar(t + timedelta(minutes=i), px, px, px, px, amount=1.0))
    dump = detect_volume_dump(
        etf_bars=down_bars,
        yesterday_full_amount=50.0,
        session_date=day,
    )
    assert dump is not None
    assert dump["d0"] == datetime(2026, 8, 3, 10, 0)
    assert "放量" in dump["reason"] or "成交额" in dump["reason"]


def test_evaluate_sync_dump_leader_and_three_down():
    from national_team_intraday import evaluate_sync_dump

    out = evaluate_sync_dump(
        {
            "510300": -0.8,
            "510500": -0.3,
            "588000": -0.2,
            "159915": 0.1,
        }
    )
    assert out["passed"] is True
    assert out["down_count"] == 3
    assert out["leader_code"] == "510300"
    assert out.get("triggered_at") is None or isinstance(out.get("triggered_at"), str)


def test_evaluate_sync_dump_fails_when_leader_not_down():
    from national_team_intraday import evaluate_sync_dump

    out = evaluate_sync_dump(
        {
            "510300": 0.1,
            "510500": -0.3,
            "588000": -0.2,
            "159915": -0.1,
        }
    )
    assert out["passed"] is False


def test_retreat_green_when_dump_continues_lower():
    from national_team_intraday import evaluate_intraday_retreat

    d0 = datetime(2026, 8, 3, 10, 0)
    # day_high=3300, day_low_at_d0=3200; D0+1 continues lower; +15 still weak near lows
    idx = [
        _bar(datetime(2026, 8, 3, 9, 31), 3300, 3300, 3200, 3205),
        _bar(d0, 3205, 3205, 3200, 3201),
        _bar(d0 + timedelta(minutes=1), 3200, 3202, 3190, 3192),  # new low → continue
        _bar(d0 + timedelta(minutes=15), 3188, 3195, 3180, 3185),  # weak, no rebound
    ]
    out = evaluate_intraday_retreat(
        now=datetime(2026, 8, 3, 10, 20),
        session_date=date(2026, 8, 3),
        yesterday_full_amount=100.0,
        etf_bars=[_bar(d0, 1, 1, 1, 1, amount=1)],
        index_bars=idx,
        index_open=3300.0,
        forced_dump={
            "d0": d0,
            "reason": "test dump",
            "reference_price": 3300.0,
            "day_high": 3300.0,
            "day_low": 3200.0,
        },
    )
    assert out["signal"]["status"] == "GREEN"
    assert "撤退" in out["signal"]["status_label"]


def test_retreat_red_when_quick_rebound():
    from national_team_intraday import evaluate_intraday_retreat

    d0 = datetime(2026, 8, 3, 10, 0)
    idx = [
        _bar(datetime(2026, 8, 3, 9, 31), 3300, 3300, 3200, 3205),
        _bar(d0, 3205, 3205, 3200, 3201),
        _bar(d0 + timedelta(minutes=1), 3201, 3310, 3200, 3305),  # break day_high → RED
    ]
    out = evaluate_intraday_retreat(
        now=datetime(2026, 8, 3, 10, 5),
        session_date=date(2026, 8, 3),
        yesterday_full_amount=100.0,
        etf_bars=[_bar(d0, 1, 1, 1, 1, amount=1)],
        index_bars=idx,
        index_open=3300.0,
        forced_dump={
            "d0": d0,
            "reason": "test dump",
            "reference_price": 3300.0,
            "day_high": 3300.0,
            "day_low": 3200.0,
        },
    )
    assert out["signal"]["status"] == "RED"
    assert out["signal"]["indicator_1"]["passed"] is False


def test_hhmm_events_include_dump_and_sync():
    from national_team_intraday import build_track_events

    events = build_track_events(
        pulse_time=datetime(2026, 8, 3, 10, 5),
        pulse_id="dump_d0",
        pulse_label="放量下跌脉冲",
        sync_passed=True,
        sync_id="sync_dump",
        sync_label="同步领跌",
        sync_time=datetime(2026, 8, 3, 10, 12),
    )
    assert events[0]["at"] == "10:05"
    assert events[0]["id"] == "dump_d0"
    assert events[1]["at"] == "10:12"
    assert events[1]["id"] == "sync_dump"


def test_dual_track_orchestrator_exposes_support_and_retreat(tmp_path, monkeypatch):
    from national_team_intraday import national_team_intraday_signal

    monkeypatch.setenv("NT_INTRADAY_CACHE", str(tmp_path))
    day = date(2026, 8, 3)
    now = datetime(2026, 8, 3, 11, 0)
    # Flat low-volume day → both NONE, but dual keys must exist
    idx = [
        _bar(datetime(2026, 8, 3, 9, 31) + timedelta(minutes=i), 3300, 3300, 3295, 3298, amount=0.01)
        for i in range(90)
    ]
    out = national_team_intraday_signal(
        now=now,
        cache_dir=str(tmp_path),
        etf_bars=idx,
        index_bars=idx,
        index_open=3300.0,
        yesterday_full_amount=1e12,
        spot_premiums={},
        sync_bars_by_code={"510300": idx, "510500": idx, "588000": idx},
    )
    assert "support" in out and "retreat" in out
    assert "events" in out["support"]
    assert "events" in out["retreat"]
    assert out["support"]["signal"]["status"] in ("NONE", "NO_DATA", "OBSERVING", "RED", "YELLOW", "GREEN")
    assert out["retreat"]["signal"]["status"] in ("NONE", "NO_DATA", "OBSERVING", "RED", "YELLOW", "GREEN")
    assert out.get("disclaimer")


def test_sync_does_not_fallback_to_spot_day_chg(tmp_path, monkeypatch):
    """Important-1: missing 5m must stay missing; never use full-day chg_pct."""
    import national_team_intraday as nti

    monkeypatch.setenv("NT_INTRADAY_CACHE", str(tmp_path))
    monkeypatch.setattr(nti, "fetch_minute_bars_delay", lambda *a, **k: [])
    now = datetime(2026, 8, 3, 11, 0)
    core = [
        _bar(datetime(2026, 8, 3, 9, 31) + timedelta(minutes=i), 1, 1, 1, 1, amount=0.01)
        for i in range(90)
    ]
    out = nti.national_team_intraday_signal(
        now=now,
        cache_dir=str(tmp_path),
        etf_bars=core,
        index_bars=core,
        index_open=3300.0,
        yesterday_full_amount=1e12,
        spot_premiums={
            "510300": {"chg_pct": -3.0, "premium_pct": 0.0},
            "510500": {"chg_pct": -2.5, "premium_pct": 0.0},
            "588000": {"chg_pct": -2.0, "premium_pct": 0.0},
            "159915": {"chg_pct": -1.5, "premium_pct": 0.0},
        },
        sync_bars_by_code=None,  # force live path that previously fell back to chg_pct
    )
    assert out["retreat"]["sync_dump"]["passed"] is False
    assert out["support"]["sync_rally"]["passed"] is False


def test_sync_fire_time_persists_across_requests(tmp_path, monkeypatch):
    """Important-2: first sync fire HH:MM must stick for the session."""
    from national_team_intraday import national_team_intraday_signal

    monkeypatch.setenv("NT_INTRADAY_CACHE", str(tmp_path))

    def _down_sync_bars(end: datetime):
        """3 codes down in last 5m; 510300 leads."""
        out = {}
        for code, drop in (("510300", 0.8), ("510500", 0.3), ("588000", 0.2)):
            bars = []
            for i in range(40):
                t = end - timedelta(minutes=39 - i)
                close = 100.0 - drop * (i / 39)
                bars.append(_bar(t, close, close, close, close, amount=0.01))
            out[code] = bars
        return out

    bars1 = _down_sync_bars(datetime(2026, 8, 3, 10, 20))
    out1 = national_team_intraday_signal(
        now=datetime(2026, 8, 3, 10, 20),
        cache_dir=str(tmp_path),
        etf_bars=bars1["510300"],
        index_bars=bars1["510300"],
        index_open=100.0,
        yesterday_full_amount=1e12,
        spot_premiums={},
        sync_bars_by_code=bars1,
    )
    assert out1["retreat"]["sync_dump"]["passed"] is True
    first_at = out1["retreat"]["sync_dump"]["triggered_at"]
    assert first_at == "10:20"

    bars2 = _down_sync_bars(datetime(2026, 8, 3, 10, 35))
    out2 = national_team_intraday_signal(
        now=datetime(2026, 8, 3, 10, 35),
        cache_dir=str(tmp_path),
        etf_bars=bars2["510300"],
        index_bars=bars2["510300"],
        index_open=100.0,
        yesterday_full_amount=1e12,
        spot_premiums={},
        sync_bars_by_code=bars2,
    )
    assert out2["retreat"]["sync_dump"]["passed"] is True
    assert out2["retreat"]["sync_dump"]["triggered_at"] == first_at


def test_bar_confirm_rejects_far_later_bar():
    """Important-3: far later bar must not satisfy a morning confirm target."""
    from national_team_intraday import _bar_for_confirm, _add_trading_minutes

    d0 = datetime(2026, 8, 3, 11, 29)
    target = _add_trading_minutes(d0, 1)
    assert target is not None
    bars = [_bar(datetime(2026, 8, 3, 13, 5), 1, 1, 1, 1)]
    # 13:05 is not within tolerance of 11:30; if target is 13:00, 13:05 may be ok with skew=1? use skew=1 → 13:05 fails for 13:00
    if target.time() <= time(11, 30):
        assert _bar_for_confirm(bars, target) is None
    else:
        # trading +1 crossed lunch → target ~13:00; 13:05 outside 1-min skew
        assert _bar_for_confirm(bars, target, max_skew_minutes=1) is None


def test_five_min_changes_no_stale_bar_fallback():
    """Follow-up Important-2: no inventing 5m change from pre-lunch bars after open."""
    from national_team_intraday import _five_min_changes_from_bars

    am_end = datetime(2026, 8, 3, 11, 30)
    bars = {
        "510300": [
            _bar(am_end - timedelta(minutes=i), 100 + i, 100 + i, 100 + i, 100 + i)
            for i in range(5, -1, -1)
        ]
    }
    # 13:01 — wall-clock 5m window has no bars; must be None (not AM stale)
    out = _five_min_changes_from_bars(bars, datetime(2026, 8, 3, 13, 1))
    assert out["510300"] is None


def test_add_trading_minutes_resumes_at_1301():
    """Follow-up Important-3: first post-lunch minute bar is 13:01."""
    from national_team_intraday import _add_trading_minutes

    assert _add_trading_minutes(datetime(2026, 8, 3, 11, 30), 1) == datetime(2026, 8, 3, 13, 1)
    assert _add_trading_minutes(datetime(2026, 8, 3, 11, 29), 15) == datetime(2026, 8, 3, 13, 14)
    assert _add_trading_minutes(datetime(2026, 8, 3, 11, 30), 15) == datetime(2026, 8, 3, 13, 15)


def test_dump_by_index_new_day_low_without_etf_down_window():
    """Important-4: index new-day-low alone can qualify dump direction."""
    from national_team_intraday import detect_volume_dump

    day = date(2026, 8, 3)
    t = datetime(2026, 8, 3, 9, 31)
    # Flat ETF closes (no down window) but heavy volume
    etf = []
    for i in range(40):
        etf.append(_bar(t + timedelta(minutes=i), 1.0, 1.0, 1.0, 1.0, amount=1.0))
    # Index makes progressive lows; last bar is day low
    idx = []
    for i in range(40):
        low = 3300 - i
        idx.append(_bar(t + timedelta(minutes=i), low + 1, low + 2, low, low + 0.5))
    dump = detect_volume_dump(
        etf_bars=etf,
        yesterday_full_amount=50.0,
        session_date=day,
        index_bars=idx,
    )
    assert dump is not None
    assert dump["d0"] == datetime(2026, 8, 3, 10, 0)


def test_clear_dump_other_day(monkeypatch, tmp_path):
    from national_team_intraday import save_dump_state, load_dump_state, clear_dump_if_stale

    monkeypatch.setenv("NT_INTRADAY_CACHE", str(tmp_path))
    save_dump_state(
        {
            "date": "2026-08-02",
            "d0": "2026-08-02T14:50:00",
            "reference_price": 3300,
            "day_high": 3300,
            "day_low": 3200,
            "reason": "old",
        },
        cache_dir=str(tmp_path),
    )
    assert clear_dump_if_stale(date(2026, 8, 3), cache_dir=str(tmp_path)) is True
    assert load_dump_state(cache_dir=str(tmp_path)) is None


def test_retreat_visible_when_support_none(tmp_path, monkeypatch):
    """Important-4: retreat can fire while support stays NONE."""
    from national_team_intraday import national_team_intraday_signal, save_dump_state

    monkeypatch.setenv("NT_INTRADAY_CACHE", str(tmp_path))
    d0 = datetime(2026, 8, 3, 10, 0)
    save_dump_state(
        {
            "date": "2026-08-03",
            "d0": d0.isoformat(sep=" "),
            "reason": "forced dump",
            "reference_price": 3300.0,
            "day_high": 3300.0,
            "day_low": 3200.0,
        },
        cache_dir=str(tmp_path),
    )
    idx = [
        _bar(datetime(2026, 8, 3, 9, 31) + timedelta(minutes=i), 3300, 3300, 3290, 3295, amount=0.001)
        for i in range(20)
    ]
    idx.append(_bar(d0, 3205, 3205, 3200, 3201, amount=0.001))
    idx.append(_bar(d0 + timedelta(minutes=1), 3200, 3202, 3190, 3192, amount=0.001))
    idx.append(_bar(d0 + timedelta(minutes=15), 3188, 3195, 3180, 3185, amount=0.001))
    # Tiny amounts → no support volume pulse
    etf = [_bar(d0 - timedelta(minutes=i), 1, 1, 1, 1, amount=0.001) for i in range(40, -1, -1)]
    out = national_team_intraday_signal(
        now=datetime(2026, 8, 3, 10, 20),
        cache_dir=str(tmp_path),
        etf_bars=etf,
        index_bars=idx,
        index_open=3300.0,
        yesterday_full_amount=1e12,
        spot_premiums={},
        sync_bars_by_code={"510300": etf},
    )
    assert out["support"]["signal"]["status"] == "NONE"
    assert out["retreat"]["signal"]["status"] == "GREEN"
