"""
预测追踪系统 — 记录每次预测, 回填实际价格, 计算准确率.

数据存储: C:/reports/stock/data/{symbol}/predictions_log.json
格式: [{ date, predicted_close, predicted_high, predicted_low,
          actual_close, actual_high, actual_low, error_close, ... }]
"""
import json
import logging
import os
from datetime import datetime

from config import STOCK_DATA_DIR

log = logging.getLogger(__name__)


def _log_path(symbol: str) -> str:
    return os.path.join(STOCK_DATA_DIR, symbol, "predictions_log.json")


def _load_log(symbol: str) -> list[dict]:
    path = _log_path(symbol)
    if os.path.isfile(path):
        try:
            with open(path, encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return []


def _save_log(symbol: str, entries: list[dict]):
    path = _log_path(symbol)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(entries, f, ensure_ascii=False, indent=2, default=str)


def record_prediction(symbol: str, prediction_result: dict):
    """
    Record a price prediction for tracking.
    Called after train_price_prediction() returns.
    """
    preds = prediction_result.get("predictions", {})
    if not preds:
        return

    latest_date = prediction_result.get("latest_date", "")
    predicted_at = prediction_result.get("model_info", {}).get("predicted_at", datetime.now().isoformat())

    entry = {
        "prediction_date": latest_date,
        "target_date": "",
        "predicted_at": predicted_at,
        "current_close": prediction_result.get("current_close"),
        "predicted_close": preds.get("close"),
        "predicted_high": preds.get("high"),
        "predicted_low": preds.get("low"),
        "actual_close": None,
        "actual_high": None,
        "actual_low": None,
        "error_close": None,
        "error_high": None,
        "error_low": None,
        "error_pct_close": None,
        "direction_correct": None,
    }

    entries = _load_log(symbol)

    existing_idx = None
    for i, e in enumerate(entries):
        if e.get("prediction_date") == latest_date:
            existing_idx = i
            break

    if existing_idx is not None:
        entries[existing_idx] = entry
    else:
        entries.append(entry)

    entries.sort(key=lambda x: x.get("prediction_date", ""))
    _save_log(symbol, entries)
    log.info("%s: 预测记录已保存 (date=%s)", symbol, latest_date)


def backfill_actuals(symbol: str) -> int:
    """
    Fill in actual prices for past predictions using daily.csv.
    Returns count of newly filled entries.
    """
    from technical_analysis import load_ohlcv

    entries = _load_log(symbol)
    if not entries:
        return 0

    ohlcv = load_ohlcv(symbol)
    if ohlcv is None or ohlcv.empty:
        return 0

    ohlcv["date_str"] = ohlcv["date"].astype(str).str[:10]
    date_idx = ohlcv.set_index("date_str")

    filled = 0
    for entry in entries:
        if entry.get("actual_close") is not None:
            continue

        pred_date = entry.get("prediction_date", "")
        if not pred_date:
            continue

        mask = ohlcv["date_str"] > pred_date
        next_rows = ohlcv[mask]
        if next_rows.empty:
            continue

        next_row = next_rows.iloc[0]
        entry["target_date"] = str(next_row.get("date", ""))[:10]
        entry["actual_close"] = _safe_float(next_row.get("close"))
        entry["actual_high"] = _safe_float(next_row.get("high"))
        entry["actual_low"] = _safe_float(next_row.get("low"))

        if entry["actual_close"] and entry["predicted_close"]:
            entry["error_close"] = round(entry["actual_close"] - entry["predicted_close"], 4)
            if entry["actual_close"] != 0:
                entry["error_pct_close"] = round(
                    abs(entry["error_close"]) / entry["actual_close"] * 100, 4
                )
            curr = entry.get("current_close")
            if curr:
                pred_dir = 1 if entry["predicted_close"] > curr else -1 if entry["predicted_close"] < curr else 0
                actual_dir = 1 if entry["actual_close"] > curr else -1 if entry["actual_close"] < curr else 0
                entry["direction_correct"] = pred_dir == actual_dir

        if entry["actual_high"] and entry["predicted_high"]:
            entry["error_high"] = round(entry["actual_high"] - entry["predicted_high"], 4)
            if entry["actual_high"] != 0:
                entry["error_pct_high"] = round(
                    abs(entry["error_high"]) / entry["actual_high"] * 100, 4
                )

        if entry["actual_low"] and entry["predicted_low"]:
            entry["error_low"] = round(entry["actual_low"] - entry["predicted_low"], 4)
            if entry["actual_low"] != 0:
                entry["error_pct_low"] = round(
                    abs(entry["error_low"]) / entry["actual_low"] * 100, 4
                )

        filled += 1

    if filled > 0:
        _save_log(symbol, entries)
        log.info("%s: 回填了 %d 条实际价格", symbol, filled)

    return filled


def get_accuracy_stats(symbol: str) -> dict:
    """
    Calculate accuracy statistics for prediction history.
    Returns stats for 7d, 30d, and overall, plus model health trend.
    """
    entries = _load_log(symbol)
    filled = [e for e in entries if e.get("actual_close") is not None]

    if not filled:
        return {"total_predictions": len(entries), "filled": 0, "stats": {}}

    def _calc_window(data: list[dict]) -> dict:
        if not data:
            return {}
        mape_vals = [e["error_pct_close"] for e in data if e.get("error_pct_close") is not None]
        mae_vals = [abs(e["error_close"]) for e in data if e.get("error_close") is not None]
        dir_vals = [e["direction_correct"] for e in data if e.get("direction_correct") is not None]
        mape_high = [e["error_pct_high"] for e in data if e.get("error_pct_high") is not None]
        mape_low = [e["error_pct_low"] for e in data if e.get("error_pct_low") is not None]

        return {
            "count": len(data),
            "avg_mape": round(sum(mape_vals) / len(mape_vals), 2) if mape_vals else None,
            "avg_mae": round(sum(mae_vals) / len(mae_vals), 2) if mae_vals else None,
            "avg_mape_high": round(sum(mape_high) / len(mape_high), 2) if mape_high else None,
            "avg_mape_low": round(sum(mape_low) / len(mape_low), 2) if mape_low else None,
            "direction_accuracy": round(sum(dir_vals) / len(dir_vals), 4) if dir_vals else None,
            "direction_correct": sum(1 for d in dir_vals if d) if dir_vals else 0,
            "direction_total": len(dir_vals),
        }

    stats = {
        "overall": _calc_window(filled),
        "last_7": _calc_window(filled[-7:]),
        "last_30": _calc_window(filled[-30:]),
    }

    health = _calc_model_health(filled)

    return {
        "symbol": symbol,
        "total_predictions": len(entries),
        "filled": len(filled),
        "pending": len(entries) - len(filled),
        "stats": stats,
        "health": health,
        "recent": filled[-10:][::-1],
    }


def get_latest_verification(symbol: str) -> dict | None:
    """
    Get the most recent entry that has actual data filled in.
    Used to show "yesterday's prediction vs reality" at the top of the UI.
    """
    entries = _load_log(symbol)
    filled = [e for e in entries if e.get("actual_close") is not None]
    if not filled:
        return None
    return filled[-1]


def get_aggregate_stats(symbols: list[str]) -> dict:
    """
    Aggregate verification statistics across multiple symbols (watchlist scope).
    Returns combined counts, success rates, and per-window breakdowns.
    """
    total_predictions = 0
    total_filled = 0
    total_pending = 0
    all_dir_correct = 0
    all_dir_total = 0
    all_mape: list[float] = []
    all_mae: list[float] = []

    window_7: list[dict] = []
    window_30: list[dict] = []

    per_symbol: list[dict] = []

    for sym in symbols:
        entries = _load_log(sym)
        if not entries:
            continue

        filled = [e for e in entries if e.get("actual_close") is not None]
        total_predictions += len(entries)
        total_filled += len(filled)
        total_pending += len(entries) - len(filled)

        sym_dir_correct = 0
        sym_dir_total = 0
        sym_mape: list[float] = []

        for e in filled:
            if e.get("error_pct_close") is not None:
                all_mape.append(e["error_pct_close"])
                sym_mape.append(e["error_pct_close"])
            if e.get("error_close") is not None:
                all_mae.append(abs(e["error_close"]))
            if e.get("direction_correct") is not None:
                all_dir_total += 1
                sym_dir_total += 1
                if e["direction_correct"]:
                    all_dir_correct += 1
                    sym_dir_correct += 1

        window_7.extend(filled[-7:])
        window_30.extend(filled[-30:])

        if sym_dir_total > 0:
            per_symbol.append({
                "symbol": sym,
                "verified": len(filled),
                "direction_accuracy": round(sym_dir_correct / sym_dir_total, 4),
                "avg_mape": round(sum(sym_mape) / len(sym_mape), 2) if sym_mape else None,
            })

    def _window_stats(data: list[dict]) -> dict:
        mape = [e["error_pct_close"] for e in data if e.get("error_pct_close") is not None]
        dirs = [e["direction_correct"] for e in data if e.get("direction_correct") is not None]
        dc = sum(1 for d in dirs if d)
        return {
            "count": len(data),
            "avg_mape": round(sum(mape) / len(mape), 2) if mape else None,
            "direction_correct": dc,
            "direction_total": len(dirs),
            "direction_accuracy": round(dc / len(dirs), 4) if dirs else None,
        }

    return {
        "total_predictions": total_predictions,
        "total_verified": total_filled,
        "total_pending": total_pending,
        "direction_correct": all_dir_correct,
        "direction_total": all_dir_total,
        "direction_accuracy": round(all_dir_correct / all_dir_total, 4) if all_dir_total else None,
        "avg_mape": round(sum(all_mape) / len(all_mape), 2) if all_mape else None,
        "avg_mae": round(sum(all_mae) / len(all_mae), 2) if all_mae else None,
        "last_7": _window_stats(window_7),
        "last_30": _window_stats(window_30),
        "per_symbol": sorted(per_symbol, key=lambda x: x.get("direction_accuracy", 0), reverse=True),
        "symbol_count": len(per_symbol),
    }


def _calc_model_health(filled: list[dict]) -> dict:
    """
    Assess long-term model health by comparing recent vs older accuracy.
    Returns a health grade and recommendation.
    """
    if len(filled) < 5:
        return {"grade": "N/A", "message": "数据不足，至少需要5次验证", "action": "continue"}

    recent = filled[-5:]
    recent_mape = [e["error_pct_close"] for e in recent if e.get("error_pct_close") is not None]
    recent_dir = [e["direction_correct"] for e in recent if e.get("direction_correct") is not None]

    avg_mape = sum(recent_mape) / len(recent_mape) if recent_mape else 99
    dir_acc = sum(recent_dir) / len(recent_dir) if recent_dir else 0

    if avg_mape <= 1.5 and dir_acc >= 0.7:
        grade, color, msg = "A", "#10b981", "模型表现优秀"
        action = "continue"
    elif avg_mape <= 3.0 and dir_acc >= 0.5:
        grade, color, msg = "B", "#3b82f6", "模型表现良好"
        action = "continue"
    elif avg_mape <= 5.0 or dir_acc >= 0.4:
        grade, color, msg = "C", "#fbbf24", "模型表现一般，建议观察"
        action = "monitor"
    else:
        grade, color, msg = "D", "#ef4444", "模型表现差，建议考虑更换算法"
        action = "review"

    trend = "stable"
    if len(filled) >= 10:
        older = filled[-10:-5]
        older_mape = [e["error_pct_close"] for e in older if e.get("error_pct_close") is not None]
        if older_mape and recent_mape:
            old_avg = sum(older_mape) / len(older_mape)
            if avg_mape < old_avg * 0.8:
                trend = "improving"
            elif avg_mape > old_avg * 1.2:
                trend = "degrading"

    return {
        "grade": grade,
        "color": color,
        "message": msg,
        "action": action,
        "trend": trend,
        "recent_mape": round(avg_mape, 2),
        "recent_direction_acc": round(dir_acc, 4) if recent_dir else None,
        "sample_size": len(filled),
    }


def _safe_float(val) -> float | None:
    if val is None:
        return None
    try:
        v = float(val)
        return round(v, 4) if not (v != v) else None  # NaN check
    except (TypeError, ValueError):
        return None
