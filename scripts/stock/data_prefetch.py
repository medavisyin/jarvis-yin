"""
数据预热任务 — 手动触发、可暂停/停止/续跑.

Phase: 网络探测 → 全市场快照 → 行业映射 → 自选股逐只刷新 (串行限速).
"""
import json
import logging
import os
import threading
import time
from datetime import datetime

from config import STOCK_CACHE_DIR

log = logging.getLogger(__name__)

_PREFETCH_DIR = os.path.join(STOCK_CACHE_DIR, ".prefetch")
_STATE_FILE = os.path.join(_PREFETCH_DIR, "job.json")
_SYMBOL_DELAY_SEC = 2.0

_stop_event = threading.Event()
_pause_event = threading.Event()
_thread: threading.Thread | None = None


def _default_state() -> dict:
    return {
        "status": "idle",
        "phase": "",
        "completed_symbols": [],
        "total_symbols": 0,
        "current_symbol": "",
        "current_index": 0,
        "market_spot_done": False,
        "industry_map_done": False,
        "network_mode": "",
        "errors": [],
        "started_at": None,
        "updated_at": None,
        "finished_at": None,
        "can_resume": False,
        "message": "",
    }


def _load_state() -> dict:
    if os.path.isfile(_STATE_FILE):
        try:
            with open(_STATE_FILE, encoding="utf-8") as f:
                s = json.load(f)
            for k, v in _default_state().items():
                s.setdefault(k, v)
            return s
        except Exception:
            pass
    return _default_state()


def _save_state(state: dict):
    os.makedirs(_PREFETCH_DIR, exist_ok=True)
    state["updated_at"] = datetime.now().isoformat()
    with open(_STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)


def get_prefetch_status() -> dict:
    s = _load_state()
    s["running"] = _thread is not None and _thread.is_alive()
    s["paused"] = _pause_event.is_set()
    done = len(s.get("completed_symbols", []))
    total = s.get("total_symbols") or 0
    s["progress_pct"] = round(done / total * 100, 1) if total else 0
    return s


def _wait_if_paused(state: dict) -> bool:
    """Returns False if stopped."""
    while _pause_event.is_set():
        if _stop_event.is_set():
            return False
        state["status"] = "paused"
        state["message"] = "已暂停，点击继续"
        _save_state(state)
        time.sleep(0.5)
    return not _stop_event.is_set()


def _run_job(resume: bool):
    from network_policy import ensure_network, probe_network
    from watchlist import list_stocks

    state = _load_state() if resume else _default_state()
    if not resume:
        state["completed_symbols"] = []
        state["market_spot_done"] = False
        state["industry_map_done"] = False
        state["errors"] = []

    state["status"] = "running"
    state["started_at"] = state.get("started_at") or datetime.now().isoformat()
    state["can_resume"] = True
    _save_state(state)

    try:
        if not _wait_if_paused(state):
            return

        state["phase"] = "network_probe"
        state["message"] = "探测网络 (直连/代理)..."
        _save_state(state)
        if not ensure_network(force=True):
            state["status"] = "failed"
            state["message"] = "网络不可用 (直连与代理均失败)"
            _save_state(state)
            return
        net = probe_network()
        state["network_mode"] = net.get("mode", "")

        if not state.get("market_spot_done"):
            if not _wait_if_paused(state):
                return
            state["phase"] = "market_spot"
            state["message"] = "拉取全市场 PE/PB 快照 (约1-3分钟)..."
            _save_state(state)
            try:
                from valuation import refresh_market_spot
                info = refresh_market_spot()
                state["market_spot_done"] = True
                state["message"] = f"全市场快照完成 ({info.get('rows', 0)} 只, {info.get('source', '')})"
            except Exception as e:
                state["errors"].append(f"market_spot: {e}")
                log.warning("全市场快照失败: %s", e)

        if not state.get("industry_map_done"):
            if not _wait_if_paused(state):
                return
            state["phase"] = "industry_map"
            state["message"] = "重建行业映射..."
            _save_state(state)
            try:
                from valuation import rebuild_industry_map
                n = rebuild_industry_map()
                state["industry_map_done"] = True
                state["message"] = f"行业映射 {n} 个行业"
            except Exception as e:
                state["errors"].append(f"industry_map: {e}")

            if not _wait_if_paused(state):
                return
            state["message"] = "刷新自选股行业成分..."
            _save_state(state)
            try:
                from valuation import refresh_watchlist_industry_peers
                peer_info = refresh_watchlist_industry_peers()
                state["message"] = (
                    f"行业成分 {peer_info.get('refreshed', 0)}/"
                    f"{peer_info.get('industries', 0)}"
                )
            except Exception as e:
                state["errors"].append(f"industry_peers: {e}")

        stocks = list_stocks()
        symbols = [s["symbol"] for s in stocks if s.get("symbol")]
        state["total_symbols"] = len(symbols)
        completed = set(state.get("completed_symbols", []))
        pending = [s for s in symbols if s not in completed]

        state["phase"] = "watchlist"
        _save_state(state)

        from fetch_market_data import update_stock_data

        for i, sym in enumerate(pending):
            if _stop_event.is_set():
                state["status"] = "stopped"
                state["message"] = f"已停止 ({len(completed)}/{len(symbols)})，可继续"
                _save_state(state)
                return
            if not _wait_if_paused(state):
                state["status"] = "stopped"
                _save_state(state)
                return

            state["current_symbol"] = sym
            state["current_index"] = len(completed) + 1
            state["message"] = f"刷新 {sym} ({state['current_index']}/{len(symbols)})"
            _save_state(state)

            try:
                update_stock_data(sym)
                completed.add(sym)
                state["completed_symbols"] = sorted(completed)
            except Exception as e:
                state["errors"].append(f"{sym}: {e}")
                log.warning("预热 %s 失败: %s", sym, e)

            time.sleep(_SYMBOL_DELAY_SEC)

        try:
            from watchlist import _backfill_watchlist_info
            _backfill_watchlist_info()
        except Exception:
            pass

        state["status"] = "completed"
        state["phase"] = "done"
        state["current_symbol"] = ""
        state["message"] = f"预热完成 ({len(completed)}/{len(symbols)} 只)"
        state["finished_at"] = datetime.now().isoformat()
        state["can_resume"] = False
        _save_state(state)

    except Exception as e:
        log.exception("数据预热异常")
        state["status"] = "failed"
        state["message"] = str(e)
        state["errors"].append(str(e))
        _save_state(state)


def start_prefetch(resume: bool = False) -> dict:
    global _thread
    if _thread is not None and _thread.is_alive():
        return {"ok": False, "error": "任务已在运行中", "status": get_prefetch_status()}

    _stop_event.clear()
    _pause_event.clear()

    if resume:
        s = _load_state()
        if s["status"] == "completed" and not s.get("can_resume"):
            return {"ok": False, "error": "上次任务已完成，请重新开始", "status": s}
    else:
        _save_state(_default_state())

    _thread = threading.Thread(
        target=_run_job, args=(resume,), daemon=True, name="data-prefetch",
    )
    _thread.start()
    return {"ok": True, "message": "继续预热" if resume else "开始预热", "status": get_prefetch_status()}


def pause_prefetch() -> dict:
    if _thread is None or not _thread.is_alive():
        return {"ok": False, "error": "无运行中的任务"}
    _pause_event.set()
    s = _load_state()
    s["status"] = "paused"
    s["message"] = "暂停中..."
    _save_state(s)
    return {"ok": True, "status": get_prefetch_status()}


def resume_prefetch() -> dict:
    if _thread is not None and _thread.is_alive():
        if _pause_event.is_set():
            _pause_event.clear()
            s = _load_state()
            s["status"] = "running"
            s["message"] = "继续运行"
            _save_state(s)
            return {"ok": True, "status": get_prefetch_status()}
        return {"ok": False, "error": "任务未暂停"}
    return start_prefetch(resume=True)


def stop_prefetch() -> dict:
    _stop_event.set()
    _pause_event.clear()
    s = _load_state()
    if s["status"] in ("running", "paused"):
        s["status"] = "stopped"
        s["message"] = "已请求停止"
        s["can_resume"] = True
        _save_state(s)
    return {"ok": True, "status": get_prefetch_status()}
