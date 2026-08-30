"""近5年高回踩二次突破扫描器 — 第三套统一推荐（不改左右漏斗）。"""
from __future__ import annotations

import json
import logging
import os
import re
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime

import pandas as pd

log = logging.getLogger("ath-rebreak-scanner")

LAYER1_CAP = 100
LAYER2_LIVE_CAP = 15
MIN_TURNOVER = 1.0
MIN_AMOUNT = 30_000_000


def _init_sys_state():
    if not hasattr(sys, "_ath_status"):
        sys._ath_status = {
            "status": "idle",
            "progress": 0,
            "step": "",
            "started_at": "",
            "error": "",
            "results_count": 0,
        }
    if not hasattr(sys, "_ath_thread"):
        sys._ath_thread = None
    if not hasattr(sys, "_ath_stop"):
        sys._ath_stop = threading.Event()
    if not hasattr(sys, "_ath_lock"):
        sys._ath_lock = threading.Lock()


_init_sys_state()


def _sf(x, default=0.0) -> float:
    try:
        if x is None or (isinstance(x, float) and pd.isna(x)):
            return default
        return float(x)
    except (TypeError, ValueError):
        return default


def layer1_active_near_high(df: pd.DataFrame | None) -> list[dict]:
    if df is None or getattr(df, "empty", True):
        return []
    rows = []
    for _, row in df.iterrows():
        name = str(row.get("名称", ""))
        if "ST" in name or "退" in name:
            continue
        code = str(row.get("代码", "")).split(".")[0].zfill(6)
        if not code.startswith(("60", "00", "30", "68")):
            continue
        price = _sf(row.get("最新价"))
        if not (3 <= price <= 300):
            continue
        turnover = _sf(row.get("换手率"))
        amount = _sf(row.get("成交额"))
        chg = _sf(row.get("涨跌幅"))
        if turnover < MIN_TURNOVER or amount < MIN_AMOUNT:
            continue
        rows.append({
            "symbol": code,
            "name": name,
            "price": price,
            "change_pct": chg,
            "turnover_rate": turnover,
            "amount": amount,
            "_sort": chg * amount,
        })
    rows.sort(key=lambda r: r["_sort"], reverse=True)
    out = []
    for r in rows[:LAYER1_CAP]:
        r.pop("_sort", None)
        out.append(r)
    return out


def filter_live_rebreaks(results: list[dict]) -> list[dict]:
    return [r for r in results if r.get("signal_live")]


def cap_live_preserving_layer1_order(
    candidates: list[dict],
    enriched: list[dict],
    cap: int = LAYER2_LIVE_CAP,
) -> list[dict]:
    by_sym = {r["symbol"]: r for r in enriched if r and r.get("symbol")}
    ordered = [by_sym[c["symbol"]] for c in candidates if c.get("symbol") in by_sym]
    return filter_live_rebreaks(ordered)[:cap]


def start_ath_rebreak_scan(use_deepseek: bool = True, market_df=None) -> dict:
    with sys._ath_lock:
        if sys._ath_thread and sys._ath_thread.is_alive():
            return {"ok": False, "message": "已有扫描在运行"}
        sys._ath_stop.clear()
        sys._ath_status.update({
            "status": "running",
            "progress": 0,
            "step": "初始化",
            "started_at": datetime.now().isoformat(),
            "error": "",
            "results_count": 0,
        })
        t = threading.Thread(
            target=_run_thread, args=(use_deepseek, market_df),
            daemon=True, name="ath-rebreak-scanner",
        )
        sys._ath_thread = t
        t.start()
    return {"ok": True, "message": "扫描已启动"}


def stop_ath_rebreak_scan() -> dict:
    sys._ath_stop.set()
    return {"ok": True, "message": "已请求停止"}


def get_ath_rebreak_scan_status() -> dict:
    running = sys._ath_thread is not None and sys._ath_thread.is_alive()
    s = dict(sys._ath_status)
    s["running"] = bool(running)
    return s


def _ensure_stock_config():
    cfg_path = os.path.join(os.path.dirname(__file__), "config.py")
    import importlib.util
    spec = importlib.util.spec_from_file_location("config", cfg_path)
    cfg = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(cfg)
    sys.modules["config"] = cfg
    for m in [
        "china_market_data", "fetch_market_data", "technical_analysis",
        "scan_cache", "ath_rebreak", "eastmoney_throttle",
    ]:
        sys.modules.pop(m, None)


def _data_dir():
    from config import STOCK_REPORTS_ROOT
    d = os.path.join(STOCK_REPORTS_ROOT, "data", "ath_rebreak_scan")
    os.makedirs(d, exist_ok=True)
    return d


def _md_dir():
    from config import STOCK_REPORTS_ROOT
    d = os.path.join(STOCK_REPORTS_ROOT, "ath_rebreak_scan_reports")
    os.makedirs(d, exist_ok=True)
    return d


def get_ath_rebreak_result_by_date(date: str) -> dict | None:
    path = os.path.join(_data_dir(), f"ath_rebreak_{date}.json")
    if not os.path.isfile(path):
        return None
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def get_latest_ath_rebreak_result() -> dict | None:
    return get_ath_rebreak_result_by_date(datetime.now().strftime("%Y-%m-%d"))


def list_ath_rebreak_scan_dates() -> list[str]:
    d = _data_dir()
    dates = []
    for name in os.listdir(d):
        if name.startswith("ath_rebreak_") and name.endswith(".json"):
            dates.append(name[len("ath_rebreak_"):-5])
    return sorted(dates)


def _enrich_one(stock: dict) -> dict | None:
    if sys._ath_stop.is_set():
        return None
    sym = stock["symbol"]
    try:
        import scan_cache
        from ath_rebreak import detect_five_year_rebreak
        from technical_analysis import load_ohlcv
        if not scan_cache.ohlcv_done(sym):
            from eastmoney_throttle import eastmoney_slot
            from fetch_market_data import fetch_daily_ohlcv
            with eastmoney_slot():
                if not scan_cache.ohlcv_done(sym):
                    fetch_daily_ohlcv(sym)
                    scan_cache.mark_ohlcv(sym)
        hist = load_ohlcv(sym)
        det = detect_five_year_rebreak(hist, sym)
        row = dict(stock)
        row.update(det)
        return row
    except Exception as e:
        log.debug("ath enrich %s: %s", sym, e)
        return None


def _run_thread(use_deepseek, market_df=None):
    try:
        _ensure_stock_config()
        import scan_cache  # noqa: F401
        sys._ath_status.update({"progress": 10, "step": "Layer1 快筛"})
        df = market_df
        candidates = layer1_active_near_high(df)
        live = []
        sys._ath_status.update({
            "progress": 30,
            "step": f"Layer2 检测近5年高形态 ({len(candidates)} 只)",
        })
        if candidates:
            with ThreadPoolExecutor(max_workers=4) as ex:
                futs = [ex.submit(_enrich_one, c) for c in candidates]
                enriched = []
                for fut in as_completed(futs):
                    if sys._ath_stop.is_set():
                        break
                    row = fut.result()
                    if row:
                        enriched.append(row)
                live = cap_live_preserving_layer1_order(candidates, enriched)
        date_str = datetime.now().strftime("%Y-%m-%d")
        _save_results(live, use_deepseek=use_deepseek, date_str=date_str)
        sys._ath_status.update({
            "status": "completed",
            "progress": 100,
            "step": "完成",
            "results_count": len(live),
        })
    except Exception as e:
        log.exception("ath rebreak scan failed")
        sys._ath_status.update({"status": "failed", "error": str(e), "step": "错误"})


def _save_results(picks: list[dict], use_deepseek: bool = False, date_str: str | None = None):
    date_str = date_str or datetime.now().strftime("%Y-%m-%d")
    judged = []
    for p in picks:
        row = dict(p)
        if not row.get("tradeable"):
            row["verdict"] = "不买入"
            row["judged_by"] = "rule"
            row["watch_only"] = True
            judged.append(row)
            continue
        if use_deepseek:
            judged.append(_layer3_judge(row))
        else:
            row["verdict"] = "买入"
            row["judged_by"] = "rule"
            row["reasoning"] = "规则层命中近5年高二次突破（未经 AI 终审）"
            judged.append(row)
    buys = [j for j in judged if j.get("verdict") == "买入" and j.get("tradeable")]
    watches = [j for j in judged if j.get("watch_only")]
    payload = {
        "scan_type": "ath_rebreak",
        "date": date_str,
        "picks": buys,
        "watch": watches,
        "all_candidates_count": len(picks),
        "ai_reviewed": bool(use_deepseek),
        "message": "" if buys else "暂无近5年高二次突破可买标的",
    }
    path = os.path.join(_data_dir(), f"ath_rebreak_{date_str}.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    md = _generate_ath_markdown_report(buys, watches, date_str, payload)
    md_path = os.path.join(_md_dir(), f"ath_rebreak_scan_report_{date_str}.md")
    with open(md_path, "w", encoding="utf-8") as f:
        f.write(md)


def _parse_ath_json(raw: str, stock: dict | None = None) -> dict:
    stock = dict(stock or {})
    text = (raw or "").strip()
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL).strip()
    m = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if m:
        text = m.group(1)
    start = text.find("{")
    end = text.rfind("}") + 1
    if start < 0 or end <= start:
        return stock
    json_str = text[start:end].replace("'", '"')
    json_str = re.sub(r",\s*}", "}", json_str)
    parsed = json.loads(json_str)
    verdict_raw = str(parsed.get("verdict", "")).strip()
    stock["verdict"] = "买入" if "买入" in verdict_raw and "不" not in verdict_raw else "不买入"
    stock["final_score"] = _sf(parsed.get("score"), 50)
    stock["reasoning"] = parsed.get("reason", "")
    stock["risk"] = parsed.get("risk", "")
    stock["buy_low"] = _sf(parsed.get("buy_low"), None) if parsed.get("buy_low") is not None else None
    stock["buy_high"] = _sf(parsed.get("buy_high"), None) if parsed.get("buy_high") is not None else None
    stock["stop_loss"] = _sf(parsed.get("stop_loss"), None) if parsed.get("stop_loss") is not None else None
    stock["target_price"] = _sf(parsed.get("target_price"), None) if parsed.get("target_price") is not None else None
    stock["strategy"] = parsed.get("strategy", "")
    return stock


def _generate_ath_markdown_report(picks: list, watches: list, date_str: str, meta: dict) -> str:
    lines = [
        f"# AI股票推荐报告（近5年高二次突破） — {date_str}",
        "",
        "**口径**: 近5年高（前复权）。第一次站上只是标杆，回踩后再突破才是买点。",
        "**策略**: 确认后跟进；涨停标记买不到。0 只是正常结果。",
        f"**规则层命中**: {meta.get('all_candidates_count', 0)} 只",
        f"**可买推荐**: {len(picks or [])} 只",
        "",
        "---",
        "",
    ]
    if not picks:
        lines.extend([
            "## 本次扫描结果：暂无近5年高二次突破可买标的",
            "",
            "今日没有同时满足：近5年高回踩后再收盘突破、非涨停可买、以及（若启用）AI 终审通过。",
            "",
        ])
    else:
        lines.append("## 近5年高二次突破推荐")
        lines.append("")
        if not meta.get("ai_reviewed"):
            lines.append("（未经 AI 终审）")
            lines.append("")
        for i, pick in enumerate(picks, 1):
            lines.extend([
                f"### {i}. {pick.get('name', '')} ({pick.get('symbol', '')})",
                "",
                f"- **当前价**: ¥{pick.get('price', 'N/A')}",
                f"- **回踩标签**: {', '.join(pick.get('pullback_tags') or [])}",
                f"- **推荐理由**: {pick.get('reasoning', 'N/A')}",
                f"- **主要风险**: {pick.get('risk', 'N/A')}",
                "",
            ])
    if watches:
        lines.extend(["---", "## 观察（形态成立但买不到）", ""])
        for w in watches:
            lines.append(f"- {w.get('name', '')} ({w.get('symbol', '')}) 涨停买不到")
        lines.append("")
    lines.extend(["---", "", "*本报告 v1 未收录 RAG 索引。*", ""])
    return "\n".join(lines)


def _layer3_judge(row: dict) -> dict:
    row = dict(row)
    try:
        from config import call_deepseek
        from llm_reasoning import build_ath_rebreak_layer3_system_prompt
        user = (
            f"股票 {row.get('name')} ({row.get('symbol')}) 现价 {row.get('price')}。"
            f"近5年高标杆 {row.get('benchmark')}，阶段 {row.get('stage')}，"
            f"回踩标签 {row.get('pullback_tags')}，二次突破日 {row.get('rebreak_date')}。"
            "请按近5年高二次突破右侧确认逻辑给出 JSON。"
        )
        result = call_deepseek(
            build_ath_rebreak_layer3_system_prompt(),
            user,
            max_tokens=800,
            reasoning_effort="medium",
            thinking=False,
        )
        if result.get("ok"):
            parsed = _parse_ath_json(result.get("content") or "", row)
            if parsed.get("verdict") in ("买入", "不买入"):
                parsed["judged_by"] = "deepseek"
                return parsed
    except Exception as e:
        log.debug("ath layer3: %s", e)
    row["verdict"] = "不买入"
    row["judged_by"] = "rule"
    row["reasoning"] = "AI 终审失败"
    return row
