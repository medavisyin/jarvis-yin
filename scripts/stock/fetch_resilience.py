"""Helpers for scan-time fetch resilience (backfill missing fund-flow)."""

from __future__ import annotations

import logging
import time

log = logging.getLogger(__name__)


def needs_ff_backfill(stock: dict) -> bool:
    """True when fund-flow data is missing or too thin for Layer 3 / reversal."""
    if stock.get("ff_data_missing"):
        return True
    ff = stock.get("ff_signals") or {}
    try:
        days = int(ff.get("data_days") or 0)
    except (TypeError, ValueError):
        days = 0
    return days < 3


def score_left_ff(ff: dict | None) -> float:
    """Left-scanner fund-flow score (mirrors scanner._enrich_one branches)."""
    if not ff or int(ff.get("data_days") or 0) < 3:
        return 50.0
    accumulating = bool(ff.get("accumulation_signal", False))
    main_net_3d = float(ff.get("main_net_3d", 0) or 0)
    phase = ff.get("smart_money_phase", "无信号")
    accum_score_raw = float(ff.get("accumulation_score", 0) or 0)
    ff_score = 50.0
    if phase == "布局期":
        ff_score = 80 + min(accum_score_raw / 5, 15)
    elif accumulating and main_net_3d > 0:
        ff_score = 70 + min(main_net_3d / 1e8 * 5, 20)
    elif phase == "拉升期":
        ff_score = 55
    elif phase == "出货期":
        ff_score = 25
    elif main_net_3d < 0:
        ff_score = max(20, 50 + main_net_3d / 1e8 * 3)
    return float(max(0, min(100, ff_score)))


def backfill_fund_flow(
    stocks: list[dict],
    *,
    sleep_between: float = 2.0,
    stop_event=None,
) -> int:
    """Re-fetch fund flow for stocks that still lack usable signals.

    Invalidates scan_cache entries so a previous empty/failure result is not reused.
    Returns count of stocks successfully repaired (data_days >= 3).
    """
    import scan_cache
    import china_market_data as cmd

    targets = [s for s in stocks if needs_ff_backfill(s)]
    if not targets:
        return 0

    try:
        from eastmoney_throttle import is_eastmoney_circuit_open
        # Non-consuming gate: must not call should_skip_eastmoney() (would steal half-open probe)
        if is_eastmoney_circuit_open():
            log.info("资金流向补抓: 东财熔断开启, 跳过 %d 只补抓", len(targets))
            return 0
    except Exception:
        pass

    log.info("资金流向补抓: %d 只仍缺数据，开始串行补抓...", len(targets))
    repaired = 0
    for stock in targets:
        if stop_event is not None and stop_event.is_set():
            break
        sym = stock.get("symbol")
        if not sym:
            continue
        try:
            scan_cache.clear_ff(sym)
            ff = cmd.stock_fund_flow_signals(sym)
            if ff and int(ff.get("data_days") or 0) >= 3:
                scan_cache.set_ff(sym, ff)
                stock["ff_signals"] = ff
                stock["ff_data_missing"] = False
                if "ff_score" in stock:
                    stock["ff_score"] = round(score_left_ff(ff), 1)
                repaired += 1
                log.info("  补抓成功 %s (data_days=%s)", sym, ff.get("data_days"))
            else:
                scan_cache.set_ff(sym, ff or {})
                stock["ff_data_missing"] = True
                log.info("  补抓仍失败 %s", sym)
        except Exception as e:
            log.warning("  补抓异常 %s: %s", sym, e)
            stock["ff_data_missing"] = True
        if sleep_between > 0:
            time.sleep(sleep_between)
    log.info("资金流向补抓完成: 修复 %d / %d", repaired, len(targets))
    return repaired
