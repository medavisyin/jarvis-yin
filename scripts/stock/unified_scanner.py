"""Unified scanner orchestrator.

Runs the short-term (left-side, scanner.py) and right-side (right_side_scanner.py)
scanners as ONE operation that shares:
  - a single Layer-1 full-market snapshot (one akshare fetch)
  - a shared per-stock enrichment cache (fund-flow + OHLCV fetched once per symbol)

Produces TWO independent reports (left short-term + right-side) saved to their
respective existing directories and RAG-indexed separately.

Public API mirrors the other scanners:
  start_unified_scan / get_unified_scan_status / stop_unified_scan /
  get_latest_unified_result
"""
import os
import sys
import json
import time
import logging
import threading
from datetime import datetime

log = logging.getLogger("unified_scanner")
if not log.handlers:
    _h = logging.StreamHandler()
    _h.setFormatter(logging.Formatter("%(asctime)s [%(name)s] %(levelname)s %(message)s"))
    log.addHandler(_h)
log.setLevel(logging.INFO)

_scan_lock = threading.Lock()
_stop_event = threading.Event()
_scan_thread = None
_use_deepseek = False

# IMPORTANT: `_with_stock_imports` re-imports this module on every request,
# resetting module-level globals. To survive re-imports, persist all mutable
# scan state on `sys` (same trick as right_side_scanner). Module-level names
# below re-bind to the SAME sys objects on each re-import.
def _init_sys_state():
    if not hasattr(sys, "_unified_lock"):
        sys._unified_lock = threading.Lock()
    if not hasattr(sys, "_unified_stop"):
        sys._unified_stop = threading.Event()
    if not hasattr(sys, "_unified_thread"):
        sys._unified_thread = None
    if not hasattr(sys, "_unified_status"):
        sys._unified_status = {
            "status": "idle",
            "phase": "none",
            "step": "",
            "progress": 0,
            "use_deepseek": False,
            "left": None,
            "right": None,
            "error": None,
            "started_at": None,
        }

_init_sys_state()
# re-bind to persistent sys objects every import
_scan_lock = sys._unified_lock
_stop_event = sys._unified_stop
_scan_thread = sys._unified_thread


def _status():
    return sys._unified_status


def _stock_dir():
    return os.path.dirname(os.path.abspath(__file__))


def _ensure_path():
    d = _stock_dir()
    if d not in sys.path:
        sys.path.insert(0, d)


def _set_status(**kw):
    with _scan_lock:
        sys._unified_status.update(kw)


def get_unified_scan_status() -> dict:
    with _scan_lock:
        s = dict(sys._unified_status)
    s["running"] = sys._unified_thread is not None and sys._unified_thread.is_alive()
    return s


def stop_unified_scan() -> dict:
    _stop_event.set()
    try:
        import scanner
        scanner.stop_scan()
    except Exception:
        pass
    try:
        import right_side_scanner
        right_side_scanner.stop_right_side_scan()
    except Exception:
        pass
    return {"ok": True, "message": "已发送停止信号"}


def start_unified_scan(use_deepseek: bool = False) -> dict:
    global _use_deepseek
    with _scan_lock:
        if sys._unified_thread is not None and sys._unified_thread.is_alive():
            return {"ok": False, "error": "统一扫描正在进行中", "status": get_unified_scan_status()}
        _use_deepseek = use_deepseek
        _stop_event.clear()
        sys._unified_status.update({
            "status": "running",
            "phase": "market",
            "step": "Layer 1: 共享全市场行情抓取...",
            "progress": 5,
            "use_deepseek": use_deepseek,
            "left": None,
            "right": None,
            "error": None,
            "started_at": datetime.now().isoformat(),
        })
        t = threading.Thread(target=_run_unified_inner, args=(use_deepseek,), daemon=True, name="unified-scanner")
        sys._unified_thread = t
        t.start()
        return {"ok": True, "message": "统一扫描已启动"}


def _fetch_shared_market_df():
    """Fetch full A-share snapshot once, with fallbacks. Reuses both scanners' helpers."""
    _ensure_path()
    import akshare as ak
    rss = _safe_import("right_side_scanner")
    _sc = _safe_import("scanner")

    df = None
    try:
        df = ak.stock_zh_a_spot_em()
    except Exception as e:
        log.warning("akshare 全市场行情失败: %s, 尝试东财直连...", e)

    if df is None or df.empty:
        try:
            df = rss._fetch_market_eastmoney_direct()
        except Exception as e2:
            log.warning("东财直连失败: %s, 尝试新浪分页备用...", e2)

    if df is None or df.empty:
        try:
            df = _sc._fetch_market_eastmoney()
        except Exception as e3:
            log.error("所有行情源均失败: %s", e3)

    return df


def _wait_for(scanner_status_fn, done_keys, phase_label, base_progress, span):
    """Poll a sub-scanner status until it reaches a terminal state.

    Updates the unified status with the sub-scanner's current step/progress
    mapped onto [base_progress, base_progress+span].
    """
    last = None
    while True:
        if _stop_event.is_set():
            return None
        time.sleep(1.0)
        try:
            st = scanner_status_fn()
        except Exception:
            st = {}
        last = st
        sub_prog = float(st.get("progress", 0) or 0)
        mapped = base_progress + int(sub_prog / 100.0 * span)
        _set_status(
            phase=phase_label,
            step=st.get("step") or st.get("status") or "",
            progress=min(99, mapped),
            **{phase_label: st},
        )
        sub_status = st.get("status", "")
        if sub_status in done_keys or sub_status in ("done", "completed", "error", "stopped", "idle"):
            return st


def _ensure_stock_config():
    """Force-load the stock config into sys.modules and flush stale stock modules.

    The unified scan runs in a background thread that outlives the
    `_with_stock_imports` decorator, which restores sys.modules['config'] to
    the RAG config after the start request returns. Without this, importing
    scanner / right_side_scanner here would hit
    `ImportError: cannot import name 'STOCK_DATA_DIR' from 'config'`.
    Mirrors the setup at the top of scanner._run_scan_inner.
    """
    _stock_dir = os.path.dirname(os.path.abspath(__file__))
    if _stock_dir not in sys.path:
        sys.path.insert(0, _stock_dir)

    import importlib.util as _ilu
    _cfg_path = os.path.join(_stock_dir, "config.py")
    _spec = _ilu.spec_from_file_location("config", _cfg_path)
    _cfg = _ilu.module_from_spec(_spec)
    _spec.loader.exec_module(_cfg)
    sys.modules["config"] = _cfg

    _stale = [
        "hot_sectors", "technical_analysis", "report_technical",
        "fundamental_analysis", "sentiment", "features", "model_xgboost",
        "model_cross_sectional", "model_price_predictor", "prediction_tracker",
        "fetch_market_data", "china_market_data", "llm_reasoning",
        "market_sentiment", "black_swan_detector", "model_timing",
        "backtest_engine", "midday_scanner", "long_term_scanner", "watchlist",
        "scanner", "right_side_scanner", "scan_cache",
    ]
    for m in _stale:
        sys.modules.pop(m, None)


def _safe_import(name: str, retries: int = 5):
    """Import a stock sub-module, retrying after re-fixing config on ImportError.

    The start route's `_with_stock_imports` decorator restores
    `sys.modules['config']` to the RAG config in its `finally` — which can
    race with this background thread's `_ensure_stock_config()` and clobber
    config mid-import, producing
    `ImportError: cannot import name 'STOCK_DATA_DIR' from 'config'`.
    The clobber happens once (at start-route return); subsequent status
    polls preserve whatever config the thread sets. So re-fixing config and
    retrying reliably succeeds.
    """
    import importlib
    last_err = None
    for _ in range(retries):
        _ensure_stock_config()
        try:
            return importlib.import_module(name)
        except ImportError as e:
            last_err = e
            log.warning("导入 %s 失败 (%s), 重新修复 stock config 后重试...", name, e)
            time.sleep(0.3)
    raise last_err


def _run_unified_inner(use_deepseek: bool = False):
    """Background orchestration: shared market fetch -> left scan -> right scan."""
    try:
        _ensure_path()
        scan_cache = _safe_import("scan_cache")
        scan_cache.reset()

        # --- shared Layer 1 ------------------------------------------------
        _set_status(phase="market", step="Layer 1: 共享全市场行情抓取...", progress=8)
        df = _fetch_shared_market_df()
        if df is None or df.empty:
            _set_status(status="error", phase="market", step="行情抓取失败", progress=0,
                        error="无法获取市场行情数据")
            return
        log.info("统一扫描: 共享行情 %d 只股票", len(df))

        # Shared snapshot is passed directly into each scanner's start call
        # (via the market_df argument) rather than via module globals — the
        # scanners' module globals get reset whenever _safe_import re-imports
        # the module, which previously wiped the injected df and forced a
        # second slow akshare fetch in the right-side scan.

        if _stop_event.is_set():
            _set_status(status="stopped", step="已停止")
            return

        # --- left scan (short-term) ---------------------------------------
        _set_status(phase="left", step="启动左侧短期扫描...", progress=12)
        _sc = _safe_import("scanner")
        # clear any prior stop signal / state
        try:
            _sc._stop_event.clear()
        except Exception:
            pass
        started = _sc.start_scan(use_deepseek, market_df=df)
        if not started.get("ok"):
            # maybe a lingering thread; wait briefly and retry once
            time.sleep(2)
            started = _sc.start_scan(use_deepseek, market_df=df)
        if started.get("ok"):
            left_st = _wait_for(_sc.get_scan_status,
                                done_keys={"done", "completed", "error", "stopped"},
                                phase_label="left", base_progress=12, span=45)
        else:
            left_st = {"status": "error", "error": started.get("error", "无法启动左侧扫描")}
            _set_status(left=left_st)

        if _stop_event.is_set():
            _set_status(status="stopped", step="已停止")
            return

        # --- right scan (right-side) --------------------------------------
        _set_status(phase="right", step="启动右侧交易扫描...", progress=58)
        # right_side's thread does NOT self-fix config (unlike scanner), so it
        # must start under the stock config. _safe_import re-fixes config and
        # retries on ImportError — the start route's _with_stock_imports
        # decorator can clobber sys.modules['config'] back to the RAG config
        # mid-import right after this thread is spawned.
        _rss = _safe_import("right_side_scanner")
        try:
            _rss._stop_event.clear()
        except Exception:
            pass
        started_r = _rss.start_right_side_scan(use_deepseek, market_df=df)
        if not started_r.get("ok"):
            time.sleep(2)
            started_r = _rss.start_right_side_scan(use_deepseek, market_df=df)
        if started_r.get("ok"):
            right_st = _wait_for(_rss.get_right_side_scan_status,
                                 done_keys={"done", "completed", "error", "stopped"},
                                 phase_label="right", base_progress=58, span=40)
        else:
            right_st = {"status": "error", "error": started_r.get("error", "无法启动右侧扫描")}
            _set_status(right=right_st)

        # --- finalize ------------------------------------------------------
        final_left = _sc.get_scan_status() if _sc else None
        final_right = _rss.get_right_side_scan_status() if _rss else None
        _set_status(
            status="done",
            phase="done",
            step="统一扫描完成",
            progress=100,
            left=final_left,
            right=final_right,
        )
        log.info("统一扫描完成")

    except Exception as e:
        log.exception("统一扫描线程异常")
        _set_status(status="error", phase="error", step="异常", error=str(e))


def get_latest_unified_result() -> dict:
    """Load the latest left + right results (by today's date)."""
    _ensure_path()
    date_str = datetime.now().strftime("%Y-%m-%d")
    left = None
    right = None
    try:
        import scanner as _sc
        left = _sc.get_result_by_date(date_str)
    except Exception as e:
        log.debug("读取左侧结果失败: %s", e)
    try:
        import right_side_scanner as _rss
        right = _rss.get_right_side_result_by_date(date_str)
    except Exception as e:
        log.debug("读取右侧结果失败: %s", e)
    return {
        "date": date_str,
        "left": left,
        "right": right,
    }


if __name__ == "__main__":
    print(json.dumps(get_unified_scan_status(), ensure_ascii=False))
