"""
AI Stock Scanner — 3-layer funnel that scans the entire A-share market and
produces a TOP-N recommendation list with LLM-generated reasoning.

Architecture:
  Layer 1  全市场快速筛选  (~5000 → ~100)   realtime metrics
  Layer 2  分批详细分析    (~100 → ~20)      technicals + sentiment
  Layer 3  LLM综合评分     (~20 → TOP 5)     final scoring + reasoning

Features:
  - Batch processing (configurable batch size)
  - Checkpoint / resume after interruption
  - Incremental result publication (frontend polls progress)
  - Markdown report generation for RAG indexing
  - Historical result archiving with performance tracking
"""
import json
import logging
import os
import sys
import threading
import time
from datetime import datetime

import akshare as ak
import pandas as pd
import requests

from config import (
    STOCK_DATA_DIR,
    STOCK_REPORTS_ROOT,
    STOCK_CACHE_DIR,
    OLLAMA_HOST,
    MODEL_USAGE,
    STOCK_PROXY,
)

log = logging.getLogger(__name__)

SCAN_DIR = os.path.join(STOCK_REPORTS_ROOT, "scans")
PROGRESS_FILE = os.path.join(SCAN_DIR, "scan_progress.json")
_PROXIES = {"http": STOCK_PROXY, "https": STOCK_PROXY} if STOCK_PROXY else None

TOP_N = 5
LAYER2_BATCH = 20
LAYER2_CANDIDATE_CAP = 100
LAYER3_CAP = 20

_scan_lock = threading.Lock()
_scan_thread: threading.Thread | None = None
_stop_event = threading.Event()


def _ensure_dirs():
    os.makedirs(SCAN_DIR, exist_ok=True)
    os.makedirs(STOCK_CACHE_DIR, exist_ok=True)


def _sina_prefix(symbol: str) -> str:
    if symbol.startswith(("6", "5", "9")):
        return "sh"
    return "sz"


# ---------------------------------------------------------------------------
# Progress persistence
# ---------------------------------------------------------------------------

def _load_progress() -> dict:
    _ensure_dirs()
    if os.path.isfile(PROGRESS_FILE):
        try:
            with open(PROGRESS_FILE, encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {}


def _save_progress(prog: dict):
    _ensure_dirs()
    prog["updated_at"] = datetime.now().isoformat()
    with open(PROGRESS_FILE, "w", encoding="utf-8") as f:
        json.dump(prog, f, ensure_ascii=False, indent=2, default=str)


def get_scan_status() -> dict:
    """Return current scan progress (safe to call from any thread)."""
    prog = _load_progress()
    prog["running"] = _scan_thread is not None and _scan_thread.is_alive()
    return prog


# ---------------------------------------------------------------------------
# Layer 1 — market-wide quick filter
# ---------------------------------------------------------------------------

def _layer1_quick_filter(hot_stocks: set[str]) -> tuple[list[dict], int]:
    """
    Fetch full A-share realtime snapshot and filter candidates.

    Returns (candidates, market_total) where market_total is the raw count
    before any filtering.
    """
    log.info("Layer 1: 获取全市场实时行情...")

    df = None
    try:
        df = ak.stock_zh_a_spot_em()
    except Exception as e:
        log.warning("akshare 全市场行情失败: %s, 尝试东方财富备用API", e)

    if df is None or df.empty:
        try:
            df = _fetch_market_eastmoney()
        except Exception as e2:
            log.error("东方财富备用API也失败: %s", e2)

    if df is None or df.empty:
        log.error("无法获取市场行情数据, 扫描终止")
        return [], 0

    log.info("Layer 1: 共 %d 只股票, 开始筛选...", len(df))

    mask = (
        df["名称"].apply(lambda x: "ST" not in str(x))
        & df["涨跌幅"].between(-3, 8)
        & (df["换手率"] >= 1)
        & (df["成交额"] >= 50_000_000)
        & (df["市盈率-动态"] > 0)
        & (df["市盈率-动态"] < 100)
    )
    candidates = df[mask].copy()
    log.info("Layer 1: 基础筛选后 %d 只", len(candidates))

    candidates["score_l1"] = (
        candidates["涨跌幅"].clip(-3, 8) * 2
        + candidates["换手率"].clip(0, 20)
        + (100 - candidates["市盈率-动态"].clip(0, 100)) * 0.3
    )
    candidates["is_hot"] = candidates["代码"].isin(hot_stocks)
    candidates.loc[candidates["is_hot"], "score_l1"] += 10

    candidates = candidates.sort_values("score_l1", ascending=False)
    result = candidates.head(LAYER2_CANDIDATE_CAP)

    picks = []
    for _, row in result.iterrows():
        picks.append({
            "symbol": str(row["代码"]),
            "name": str(row["名称"]),
            "price": _num(row.get("最新价")),
            "change_pct": _num(row.get("涨跌幅")),
            "turnover_rate": _num(row.get("换手率")),
            "pe": _num(row.get("市盈率-动态")),
            "amount": _num(row.get("成交额")),
            "market_cap": _num(row.get("总市值")),
            "score_l1": round(float(row["score_l1"]), 2),
            "is_hot": bool(row["is_hot"]),
        })

    log.info("Layer 1 完成: %d 只候选股", len(picks))
    return picks, len(df)


# ---------------------------------------------------------------------------
# Layer 2 — detailed batch analysis
# ---------------------------------------------------------------------------

def _layer2_analyze_batch(batch: list[dict], progress: dict) -> list[dict]:
    """
    For a batch of candidates, fetch daily data, compute technicals,
    and quick sentiment check.  Returns enriched candidates with scores.
    """
    from technical_analysis import load_ohlcv, compute_indicators, evaluate_signals
    from fetch_market_data import fetch_daily_ohlcv, fetch_stock_news

    scored = []
    for stock in batch:
        if _stop_event.is_set():
            break

        sym = stock["symbol"]
        log.info("Layer 2: 分析 %s (%s)...", sym, stock["name"])

        tech_score = 0
        sentiment_score = 0
        signals = {}

        try:
            fetch_daily_ohlcv(sym)
            df = load_ohlcv(sym)
            if df is not None and len(df) >= 30:
                df = compute_indicators(df)
                sig = evaluate_signals(df)
                signals = sig.get("signals", {})

                bullish = sum(1 for v in signals.values() if "涨" in str(v) or "金叉" in str(v) or "突破" in str(v))
                bearish = sum(1 for v in signals.values() if "跌" in str(v) or "死叉" in str(v) or "超卖" in str(v))
                tech_score = (bullish - bearish) * 10 + 50
                tech_score = max(0, min(100, tech_score))
        except Exception as e:
            log.warning("  %s 技术分析失败: %s", sym, e)

        try:
            news = fetch_stock_news(sym, limit=5)
            if news:
                pos_keywords = {"涨", "增长", "突破", "利好", "创新", "盈利", "超预期", "签约", "中标"}
                neg_keywords = {"跌", "下降", "亏损", "利空", "减持", "处罚", "风险", "退市"}
                pos_count = sum(1 for a in news if any(k in a.get("标题", "") for k in pos_keywords))
                neg_count = sum(1 for a in news if any(k in a.get("标题", "") for k in neg_keywords))
                total = len(news)
                sentiment_score = int((pos_count - neg_count) / max(total, 1) * 50 + 50)
                sentiment_score = max(0, min(100, sentiment_score))
            else:
                sentiment_score = 50
        except Exception as e:
            log.warning("  %s 情绪分析失败: %s", sym, e)
            sentiment_score = 50

        hot_bonus = 15 if stock.get("is_hot") else 0
        total_score = (
            tech_score * 0.4
            + sentiment_score * 0.3
            + stock["score_l1"] * 0.3
            + hot_bonus
        )

        stock.update({
            "tech_score": tech_score,
            "sentiment_score": sentiment_score,
            "hot_bonus": hot_bonus,
            "score_l2": round(total_score, 2),
            "signals": signals,
        })
        scored.append(stock)

        progress.setdefault("analyzed_count", 0)
        progress["analyzed_count"] += 1
        _save_progress(progress)
        time.sleep(0.5)

    return scored


# ---------------------------------------------------------------------------
# Layer 3 — LLM comprehensive scoring + reasoning
# ---------------------------------------------------------------------------

def _layer3_llm_rank(candidates: list[dict]) -> list[dict]:
    """
    Use LLM to produce final ranking with reasoning for top candidates.
    """
    log.info("Layer 3: LLM 综合评分 (%d 只候选)...", len(candidates))

    candidates_sorted = sorted(candidates, key=lambda x: x.get("score_l2", 0), reverse=True)
    top = candidates_sorted[:LAYER3_CAP]

    model = MODEL_USAGE.get("prediction_reasoning", "qwen3.5:4b")
    final_picks = []

    for stock in top:
        if _stop_event.is_set():
            break

        prompt = _build_scoring_prompt(stock)
        try:
            resp = requests.post(
                f"{OLLAMA_HOST}/api/chat",
                json={
                    "model": model,
                    "messages": [
                        {"role": "system", "content": "你是专业A股分析师。只输出JSON，不要任何其他文字。"},
                        {"role": "user", "content": prompt},
                    ],
                    "stream": False,
                    "think": False,
                    "options": {"temperature": 0.3, "num_predict": 500},
                },
                timeout=120,
            )
            resp.raise_for_status()
            raw = resp.json().get("message", {}).get("content", "")
            parsed = _parse_llm_score(raw, stock)
            final_picks.append(parsed)
        except Exception as e:
            log.warning("LLM 评分 %s 失败: %s, 使用数值评分", stock["symbol"], e)
            stock["final_score"] = stock.get("score_l2", 0)
            stock["reasoning"] = "LLM评分不可用, 基于数值分析"
            final_picks.append(stock)

    final_picks.sort(key=lambda x: x.get("final_score", 0), reverse=True)
    return final_picks[:TOP_N]


def _build_scoring_prompt(stock: dict) -> str:
    signals_text = "\n".join(f"  - {k}: {v}" for k, v in stock.get("signals", {}).items())
    if not signals_text:
        signals_text = "  (无信号数据)"

    price = stock.get('price', 0)
    try:
        price_f = float(price)
    except (TypeError, ValueError):
        price_f = 0

    return f"""你是专业A股分析师。根据以下数据对股票评分并给出买入建议。

数据:
- 股票: {stock['name']} ({stock['symbol']})
- 最新价: {price}
- 涨跌幅: {stock.get('change_pct', 'N/A')}%
- 换手率: {stock.get('turnover_rate', 'N/A')}%
- 市盈率: {stock.get('pe', 'N/A')}
- 成交额: {_format_amount(stock.get('amount'))}
- 技术得分: {stock.get('tech_score', 'N/A')}/100
- 情绪得分: {stock.get('sentiment_score', 'N/A')}/100
- 热门板块: {'是' if stock.get('is_hot') else '否'}
- 技术信号:
{signals_text}

要求: 直接输出一个JSON对象，不要输出任何其他文字。
格式如下(注意buy_low和buy_high是数字，不是字符串):
{{"score":75,"reason":"技术面强势，量价配合良好","risk":"短期涨幅较大","buy_low":{price_f * 0.95:.2f},"buy_high":{price_f * 1.0:.2f}}}

你的回复(只输出JSON):"""


def _parse_llm_score(raw: str, stock: dict) -> dict:
    import re
    text = raw.strip()

    # Strip <think>...</think> blocks (qwen3 thinking mode)
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL).strip()

    # Strip markdown code fences
    m = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if m:
        text = m.group(1)

    # Find the outermost JSON object
    start = text.find("{")
    end = text.rfind("}") + 1
    if start >= 0 and end > start:
        json_str = text[start:end]
        # Fix common LLM issues: single quotes, trailing commas
        json_str = json_str.replace("'", '"')
        json_str = re.sub(r",\s*}", "}", json_str)
        try:
            parsed = json.loads(json_str)
            stock["final_score"] = float(parsed.get("score", stock.get("score_l2", 0)))
            stock["reasoning"] = parsed.get("reason", "")
            stock["risk"] = parsed.get("risk", "")
            stock["buy_low"] = _safe_float(parsed.get("buy_low"))
            stock["buy_high"] = _safe_float(parsed.get("buy_high"))
            return stock
        except (json.JSONDecodeError, ValueError) as e:
            log.warning("LLM JSON解析失败: %s | raw=%s", e, json_str[:200])

    stock["final_score"] = stock.get("score_l2", 0)
    stock["reasoning"] = "LLM输出解析失败, 基于数值分析"
    stock["risk"] = ""
    stock["buy_low"] = None
    stock["buy_high"] = None
    return stock


def _safe_float(val) -> float | None:
    if val is None:
        return None
    try:
        return round(float(val), 2)
    except (TypeError, ValueError):
        return None


def _buy_range_str(pick: dict) -> str:
    low, high = pick.get("buy_low"), pick.get("buy_high")
    if low and high:
        return f"¥{low:.2f} ~ ¥{high:.2f}"
    return "暂无"


# ---------------------------------------------------------------------------
# Report generation
# ---------------------------------------------------------------------------

def _generate_report(top_picks: list[dict], scan_meta: dict) -> str:
    """Generate a Markdown report suitable for RAG indexing."""
    date_str = datetime.now().strftime("%Y-%m-%d")
    lines = [
        f"# AI股票推荐报告 — {date_str}",
        "",
        f"**扫描时间**: {scan_meta.get('started_at', 'N/A')}",
        f"**全市场股票数**: {scan_meta.get('market_total', 'N/A')}",
        f"**Layer1候选**: {scan_meta.get('layer1_count', 'N/A')}",
        f"**Layer2分析**: {scan_meta.get('layer2_count', 'N/A')}",
        f"**最终推荐**: TOP {len(top_picks)}",
        "",
        "---",
        "",
        "## TOP 推荐",
        "",
    ]

    for i, pick in enumerate(top_picks, 1):
        lines.extend([
            f"### {i}. {pick['name']} ({pick['symbol']})",
            "",
            f"- **综合得分**: {pick.get('final_score', 'N/A'):.1f}/100",
            f"- **最新价**: {pick.get('price', 'N/A')}",
            f"- **涨跌幅**: {pick.get('change_pct', 'N/A')}%",
            f"- **市盈率**: {pick.get('pe', 'N/A')}",
            f"- **换手率**: {pick.get('turnover_rate', 'N/A')}%",
            f"- **技术得分**: {pick.get('tech_score', 'N/A')}/100",
            f"- **情绪得分**: {pick.get('sentiment_score', 'N/A')}/100",
            f"- **热门板块**: {'是' if pick.get('is_hot') else '否'}",
            f"- **推荐理由**: {pick.get('reasoning', 'N/A')}",
            f"- **主要风险**: {pick.get('risk', 'N/A')}",
            f"- **建议买入区间**: {_buy_range_str(pick)}",
            "",
        ])

    lines.extend([
        "---",
        "",
        "## 技术信号汇总",
        "",
    ])
    for pick in top_picks:
        signals = pick.get("signals", {})
        if signals:
            lines.append(f"**{pick['name']}**: " + ", ".join(f"{k}={v}" for k, v in signals.items()))
        else:
            lines.append(f"**{pick['name']}**: 无信号数据")
    lines.append("")

    lines.extend([
        "---",
        "",
        f"*本报告由Jarvis AI股票扫描系统自动生成于 {datetime.now():%Y-%m-%d %H:%M}*",
        f"*免责声明: 以上分析仅供参考, 不构成投资建议。投资有风险, 入市需谨慎。*",
    ])
    return "\n".join(lines)


def _save_results(top_picks: list[dict], all_candidates: list[dict], scan_meta: dict):
    """Persist scan results and generate report."""
    _ensure_dirs()
    date_str = datetime.now().strftime("%Y-%m-%d")

    result_path = os.path.join(SCAN_DIR, f"{date_str}.json")
    result_data = {
        "date": date_str,
        "meta": scan_meta,
        "top_picks": top_picks,
        "candidates": all_candidates[:50],
    }
    with open(result_path, "w", encoding="utf-8") as f:
        json.dump(result_data, f, ensure_ascii=False, indent=2, default=str)
    log.info("扫描结果已保存 → %s", result_path)

    report = _generate_report(top_picks, scan_meta)
    report_path = os.path.join(SCAN_DIR, f"{date_str}-report.md")
    with open(report_path, "w", encoding="utf-8") as f:
        f.write(report)
    log.info("推荐报告已保存 → %s", report_path)


# ---------------------------------------------------------------------------
# Main scan orchestration
# ---------------------------------------------------------------------------

def _run_scan():
    """Execute the full 3-layer scan (runs in background thread)."""
    import traceback as _tb
    try:
        _run_scan_inner()
    except Exception:
        _tb.print_exc()
        try:
            progress = _load_progress()
            progress["status"] = "error"
            progress["error"] = _tb.format_exc()[-500:]
            _save_progress(progress)
        except Exception:
            pass


def _run_scan_inner():
    """Actual scan logic (called by _run_scan with top-level error handling)."""
    _stock_dir = os.path.dirname(os.path.abspath(__file__))
    if _stock_dir not in sys.path:
        sys.path.insert(0, _stock_dir)

    import importlib.util as _ilu
    _cfg_path = os.path.join(_stock_dir, "config.py")
    _spec = _ilu.spec_from_file_location("config", _cfg_path)
    _cfg = _ilu.module_from_spec(_spec)
    _spec.loader.exec_module(_cfg)
    sys.modules["config"] = _cfg

    if "hot_sectors" in sys.modules:
        del sys.modules["hot_sectors"]
    from hot_sectors import get_hot_stock_set

    log.info("=== AI 股票扫描开始 ===")
    progress = _load_progress()

    if progress.get("status") == "layer2_in_progress":
        log.info("检测到未完成的扫描, 从断点继续...")
        return _resume_scan(progress)

    progress = {
        "status": "layer1",
        "started_at": datetime.now().isoformat(),
        "market_total": 0,
        "total_stocks": 0,
        "layer1_count": 0,
        "layer2_count": 0,
        "analyzed_count": 0,
        "top_picks": [],
        "error": None,
    }
    _save_progress(progress)

    try:
        hot_stocks = set()
        try:
            hot_stocks = get_hot_stock_set()
            log.info("热门板块股票: %d 只", len(hot_stocks))
        except Exception as e:
            log.warning("热门板块数据获取失败: %s", e)

        if _stop_event.is_set():
            progress["status"] = "stopped"
            _save_progress(progress)
            return

        candidates, market_total = _layer1_quick_filter(hot_stocks)
        if not candidates:
            progress["status"] = "error"
            progress["error"] = "Layer1 未找到候选股票 (市场数据不可用)"
            _save_progress(progress)
            return

        progress["status"] = "layer2_in_progress"
        progress["market_total"] = market_total
        progress["total_stocks"] = len(candidates)
        progress["layer1_count"] = len(candidates)
        progress["layer1_candidates"] = candidates
        progress["layer2_results"] = []
        progress["analyzed_count"] = 0
        _save_progress(progress)

        _execute_layer2_and_3(progress, candidates)

    except Exception as e:
        log.exception("扫描异常: %s", e)
        progress["status"] = "error"
        progress["error"] = str(e)
        _save_progress(progress)


def _resume_scan(progress: dict):
    """Resume a previously interrupted scan from Layer 2 checkpoint."""
    candidates = progress.get("layer1_candidates", [])
    already_done = {s["symbol"] for s in progress.get("layer2_results", [])}
    remaining = [c for c in candidates if c["symbol"] not in already_done]
    log.info("续传扫描: %d 已完成, %d 剩余", len(already_done), len(remaining))
    _execute_layer2_and_3(progress, remaining, resume=True)


def _execute_layer2_and_3(progress: dict, candidates: list[dict], resume: bool = False):
    """Run Layer 2 batches and then Layer 3."""
    all_l2 = list(progress.get("layer2_results", [])) if resume else []

    for i in range(0, len(candidates), LAYER2_BATCH):
        if _stop_event.is_set():
            progress["status"] = "stopped"
            _save_progress(progress)
            return

        batch = candidates[i:i + LAYER2_BATCH]
        log.info("Layer 2 批次 %d: %d 只 (%d/%d)",
                 i // LAYER2_BATCH + 1, len(batch),
                 len(all_l2) + len(batch), len(candidates) + len(all_l2))

        scored = _layer2_analyze_batch(batch, progress)
        all_l2.extend(scored)
        progress["layer2_results"] = all_l2
        progress["layer2_count"] = len(all_l2)
        _save_progress(progress)

    if _stop_event.is_set():
        progress["status"] = "stopped"
        _save_progress(progress)
        return

    progress["status"] = "layer3"
    _save_progress(progress)

    top_picks = _layer3_llm_rank(all_l2)

    progress["status"] = "done"
    progress["top_picks"] = top_picks
    progress["finished_at"] = datetime.now().isoformat()
    _save_progress(progress)

    scan_meta = {
        "started_at": progress.get("started_at"),
        "finished_at": progress.get("finished_at"),
        "market_total": progress.get("market_total"),
        "total_stocks": progress.get("total_stocks"),
        "layer1_count": progress.get("layer1_count"),
        "layer2_count": progress.get("layer2_count"),
    }
    _save_results(top_picks, all_l2, scan_meta)
    _save_history_entry(top_picks)

    log.info("=== AI 股票扫描完成 ===")


# ---------------------------------------------------------------------------
# History tracking
# ---------------------------------------------------------------------------

def _save_history_entry(top_picks: list[dict]):
    """Save a lightweight entry for performance tracking."""
    history_file = os.path.join(SCAN_DIR, "history.json")
    history = []
    if os.path.isfile(history_file):
        try:
            with open(history_file, encoding="utf-8") as f:
                history = json.load(f)
        except Exception:
            pass

    entry = {
        "date": datetime.now().strftime("%Y-%m-%d"),
        "picks": [
            {"symbol": p["symbol"], "name": p["name"],
             "price": p.get("price"), "score": p.get("final_score")}
            for p in top_picks
        ],
    }
    history.append(entry)

    with open(history_file, "w", encoding="utf-8") as f:
        json.dump(history, f, ensure_ascii=False, indent=2)


def update_history_performance():
    """
    Update historical picks with actual 1d/3d/7d returns.
    Call periodically (e.g. daily) to track recommendation accuracy.
    """
    from fetch_market_data import _fetch_realtime_sina

    history_file = os.path.join(SCAN_DIR, "history.json")
    if not os.path.isfile(history_file):
        return

    with open(history_file, encoding="utf-8") as f:
        history = json.load(f)

    today = datetime.now().strftime("%Y-%m-%d")
    updated = False

    for entry in history:
        rec_date = entry.get("date", "")
        if not rec_date:
            continue

        days_since = (datetime.now() - datetime.strptime(rec_date, "%Y-%m-%d")).days

        for pick in entry.get("picks", []):
            if pick.get("price") and days_since in (1, 3, 7):
                try:
                    rt = _fetch_realtime_sina(pick["symbol"])
                    current = rt.get("最新价", 0)
                    if current and pick["price"]:
                        ret = round((current - pick["price"]) / pick["price"] * 100, 2)
                        pick[f"return_{days_since}d"] = ret
                        updated = True
                except Exception:
                    pass

    if updated:
        with open(history_file, "w", encoding="utf-8") as f:
            json.dump(history, f, ensure_ascii=False, indent=2)


def get_latest_result() -> dict | None:
    """Load the latest scan result."""
    _ensure_dirs()
    files = sorted(
        [f for f in os.listdir(SCAN_DIR) if f.endswith(".json") and f != "scan_progress.json" and f != "history.json"],
        reverse=True,
    )
    if not files:
        return None
    try:
        with open(os.path.join(SCAN_DIR, files[0]), encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def get_history() -> list[dict]:
    """Load scan history with performance data."""
    history_file = os.path.join(SCAN_DIR, "history.json")
    if not os.path.isfile(history_file):
        return []
    try:
        with open(history_file, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return []


def get_result_by_date(date_str: str) -> dict | None:
    """Load scan result for a specific date (YYYY-MM-DD)."""
    _ensure_dirs()
    path = os.path.join(SCAN_DIR, f"{date_str}.json")
    if not os.path.isfile(path):
        return None
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def list_scan_dates() -> list[str]:
    """Return available scan dates sorted newest-first."""
    _ensure_dirs()
    dates = []
    for f in os.listdir(SCAN_DIR):
        if f.endswith(".json") and f not in ("scan_progress.json", "history.json") and not f.endswith("-report.md"):
            dates.append(f.replace(".json", ""))
    dates.sort(reverse=True)
    return dates


# ---------------------------------------------------------------------------
# Public API — start / stop / status
# ---------------------------------------------------------------------------

def start_scan() -> dict:
    """Start a background scan. Returns status."""
    global _scan_thread

    log.info("start_scan called")
    with _scan_lock:
        if _scan_thread is not None and _scan_thread.is_alive():
            return {"ok": False, "error": "扫描正在进行中", "status": get_scan_status()}

        _stop_event.clear()
        _scan_thread = threading.Thread(target=_run_scan, daemon=True, name="stock-scanner")
        _scan_thread.start()
        return {"ok": True, "message": "扫描已启动"}


def stop_scan() -> dict:
    """Request scan to stop."""
    _stop_event.set()
    return {"ok": True, "message": "已发送停止信号"}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _fetch_market_eastmoney() -> pd.DataFrame:
    """Fallback: fetch full A-share market data from Sina Market Center API."""
    log.info("Layer 1: 尝试新浪市场中心备用API...")
    url = "https://vip.stock.finance.sina.com.cn/quotes_service/api/json_v2.php/Market_Center.getHQNodeData"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Referer": "https://finance.sina.com.cn",
    }

    all_rows = []
    page = 1
    while True:
        params = {
            "page": str(page), "num": "80",
            "sort": "changepercent", "asc": "0",
            "node": "hs_a", "symbol": "",
        }
        resp = requests.get(url, params=params, headers=headers, timeout=20, proxies=_PROXIES)
        resp.raise_for_status()
        items = resp.json()
        if not items:
            break

        for item in items:
            code = str(item.get("code", ""))
            all_rows.append({
                "代码": code,
                "名称": str(item.get("name", "")),
                "最新价": item.get("trade"),
                "涨跌幅": item.get("changepercent"),
                "涨跌额": item.get("pricechange"),
                "成交量": item.get("volume"),
                "成交额": item.get("amount"),
                "换手率": item.get("turnoverratio"),
                "市盈率-动态": item.get("per"),
                "最高": item.get("high"),
                "最低": item.get("low"),
                "今开": item.get("open"),
                "总市值": item.get("mktcap"),
                "流通市值": item.get("nmc"),
            })

        page += 1
        if len(items) < 80 or page > 80:
            break
        time.sleep(0.3)

    if not all_rows:
        raise ValueError("新浪市场中心返回空数据")

    df = pd.DataFrame(all_rows)
    for col in ["最新价", "涨跌幅", "换手率", "成交额", "市盈率-动态", "总市值"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    log.info("新浪市场中心API: 获取 %d 只股票", len(df))
    return df


def _num(val) -> float | None:
    if val is None:
        return None
    try:
        f = float(val)
        return None if (f != f) else f
    except (TypeError, ValueError):
        return None


def _format_amount(val) -> str:
    if val is None:
        return "N/A"
    try:
        v = float(val)
        if v >= 1e8:
            return f"{v / 1e8:.1f}亿"
        if v >= 1e4:
            return f"{v / 1e4:.0f}万"
        return str(int(v))
    except (TypeError, ValueError):
        return "N/A"


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    print("Starting scan...")
    result = start_scan()
    print(result)
    if result.get("ok"):
        while True:
            time.sleep(5)
            status = get_scan_status()
            print(f"  Status: {status.get('status')}  Analyzed: {status.get('analyzed_count', 0)}")
            if status.get("status") in ("done", "error", "stopped"):
                break
        if status.get("status") == "done":
            for p in status.get("top_picks", []):
                print(f"  {p['name']} ({p['symbol']})  得分:{p.get('final_score',0):.1f}  {p.get('reasoning','')}")
