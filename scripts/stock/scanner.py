"""
AI Stock Scanner — 3-layer funnel that scans the entire A-share market and
produces a recommendation list filtered for **buyability** (not just momentum).

Architecture:
  Layer 1  全市场快速筛选  (~5000 → ~100)   realtime metrics + basic valuation
  Layer 2  分批详细分析    (~100 → ~30)      technicals + fundamentals + sentiment
  Layer 3  LLM买入判断     (~30 → 0-5)       buyability verdict + reasoning

Design philosophy (2026-04 rework):
  Old: recommend top-5 by score (momentum-biased → all "don't buy" on deeper analysis)
  New: recommend ONLY stocks that pass a buyability check (could be 0).
       "No recommendation" is the best recommendation when nothing is cheap enough.

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
LAYER3_CAP = 30
MIN_BUYABILITY_SCORE = 60

_scan_lock = threading.Lock()
_scan_thread: threading.Thread | None = None
_stop_event = threading.Event()
_use_deepseek = False


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

    China A-share rework:
      - Exclude ST / *ST / limit-up (avoid chase)
      - Require minimum liquidity (30M volume, 0.5% turnover)
      - Score blends value, momentum, and smart-money signals
      - Hot sector stocks get a moderate bonus

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
        & df["涨跌幅"].between(-7, 8)
        & (df["换手率"] >= 0.5)
        & (df["成交额"] >= 30_000_000)
        & (df["市盈率-动态"] > 0)
        & (df["市盈率-动态"] < 80)
        & (df["涨跌幅"] < 9.5)
    )
    candidates = df[mask].copy()
    log.info("Layer 1: 基础筛选后 %d 只", len(candidates))

    pe = candidates["市盈率-动态"].clip(1, 80)
    change = candidates["涨跌幅"].clip(-7, 8)
    turnover = candidates["换手率"].clip(0, 15)

    # --- Improved scoring (2026-04 science rework) ---
    # PE: bell-curve bonus — sweet spot 10~25, punish both extremes
    pe_score = (
        ((pe >= 8) & (pe < 15)).astype(float) * 90
        + ((pe >= 15) & (pe < 25)).astype(float) * 80
        + ((pe >= 25) & (pe < 40)).astype(float) * 55
        + ((pe >= 40) & (pe < 60)).astype(float) * 30
        + (pe >= 60).astype(float) * 10
        + (pe < 8).astype(float) * 40
    )

    # Intraday change: prefer mild green / mild red (pullback buying)
    # Punish chase-high aggressively (A-share T+1 lock-in risk)
    chg_score = (
        (change > 7).astype(float) * 10
        + ((change > 5) & (change <= 7)).astype(float) * 25
        + ((change > 2) & (change <= 5)).astype(float) * 45
        + ((change >= -1) & (change <= 2)).astype(float) * 70
        + ((change >= -4) & (change < -1)).astype(float) * 80
        + (change < -4).astype(float) * 50
    )

    # Turnover: moderate is healthy, extreme is risky
    turn_score = turnover.apply(
        lambda t: 80 if 1 <= t <= 5 else (60 if 5 < t <= 10 else (30 if t > 10 else 40))
    )

    candidates["score_l1"] = (
        pe_score * 0.30
        + chg_score * 0.30
        + turn_score * 0.20
        + (candidates["成交额"] / 1e8).clip(0, 20) * 0.5  # liquidity floor
    )
    candidates["is_hot"] = candidates["代码"].isin(hot_stocks)
    candidates.loc[candidates["is_hot"], "score_l1"] += 3

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
    run fundamental scoring, and quick sentiment check.
    Returns enriched candidates with scores and a buyability flag.
    """
    from technical_analysis import load_ohlcv, compute_indicators, evaluate_signals
    from fetch_market_data import fetch_daily_ohlcv, fetch_stock_news
    from fundamental_analysis import fetch_fundamentals, score_fundamentals

    scored = []
    for stock in batch:
        if _stop_event.is_set():
            break

        sym = stock["symbol"]
        log.info("Layer 2: 分析 %s (%s)...", sym, stock["name"])

        tech_score = 50
        sentiment_score = 50
        fund_score = 50
        signals = {}
        rsi_val = None
        overbought = False

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

                if "RSI" in df.columns and len(df) > 0:
                    rsi_val = df["RSI"].iloc[-1]
                    if rsi_val and rsi_val > 75:
                        overbought = True
                        tech_score = max(0, tech_score - 20)
        except Exception as e:
            log.warning("  %s 技术分析失败: %s", sym, e)

        try:
            fund_data = fetch_fundamentals(sym)
            if fund_data:
                fs = score_fundamentals(fund_data)
                fund_score = fs.get("total_score", 50)
                stock["fund_dimensions"] = fs.get("dimensions", {})
            else:
                fund_score = 50
        except Exception as e:
            log.warning("  %s 基本面分析失败: %s", sym, e)

        try:
            news = fetch_stock_news(sym, limit=5)
            if news:
                # Weighted keyword scoring: differentiate impact levels
                _HIGH_POS = {"超预期", "中标", "签约", "突破新高", "大幅增长", "扭亏为盈"}
                _MID_POS = {"增长", "利好", "创新", "盈利", "分红", "回购"}
                _LOW_POS = {"涨", "突破", "上涨"}
                _HIGH_NEG = {"退市", "ST", "暴雷", "造假", "立案", "违规"}
                _MID_NEG = {"亏损", "减持", "处罚", "下调", "风险"}
                _LOW_NEG = {"跌", "下降", "利空"}

                total_weight = 0
                for a in news:
                    title = a.get("标题", "")
                    w = 0
                    if any(k in title for k in _HIGH_POS): w += 3
                    if any(k in title for k in _MID_POS):  w += 2
                    if any(k in title for k in _LOW_POS):  w += 1
                    if any(k in title for k in _HIGH_NEG): w -= 4  # negative news hits harder
                    if any(k in title for k in _MID_NEG):  w -= 2.5
                    if any(k in title for k in _LOW_NEG):  w -= 1
                    total_weight += w

                max_possible = len(news) * 3
                norm = total_weight / max(max_possible, 1)
                sentiment_score = int(norm * 50 + 50)
                sentiment_score = max(0, min(100, sentiment_score))
            else:
                sentiment_score = 50
        except Exception as e:
            log.warning("  %s 情绪分析失败: %s", sym, e)
            sentiment_score = 50

        ff_score = 50
        ff_signals = {}
        try:
            import china_market_data as cmd
            ff = cmd.stock_fund_flow_signals(sym)
            if ff and ff.get("data_days", 0) >= 3:
                ff_signals = ff
                accumulating = ff.get("accumulation_signal", False)
                main_net_3d = ff.get("main_net_3d", 0)
                phase = ff.get("smart_money_phase", "无信号")
                accum_score_raw = ff.get("accumulation_score", 0)

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
                ff_score = max(0, min(100, ff_score))
        except Exception as e:
            log.debug("  %s 资金流向失败: %s", sym, e)

        hot_bonus = 5 if stock.get("is_hot") else 0
        total_score = (
            ff_score * 0.30
            + fund_score * 0.25
            + tech_score * 0.20
            + sentiment_score * 0.10
            + stock["score_l1"] * 0.10
            + _valuation_bonus(stock.get("pe")) * 0.05
            + hot_bonus
        )

        stock.update({
            "tech_score": tech_score,
            "fund_score": round(fund_score, 1),
            "ff_score": round(ff_score, 1),
            "ff_signals": ff_signals,
            "sentiment_score": sentiment_score,
            "hot_bonus": hot_bonus,
            "rsi": round(rsi_val, 1) if rsi_val else None,
            "overbought": overbought,
            "score_l2": round(total_score, 2),
            "signals": signals,
        })
        scored.append(stock)

        progress.setdefault("analyzed_count", 0)
        progress["analyzed_count"] += 1
        _save_progress(progress)
        time.sleep(0.5)

    return scored


def _valuation_bonus(pe) -> float:
    """Score bonus for reasonable valuation (lower PE = higher bonus)."""
    if pe is None:
        return 50
    try:
        pe_f = float(pe)
    except (TypeError, ValueError):
        return 50
    if pe_f <= 0:
        return 20
    if pe_f < 10:
        return 95
    if pe_f < 15:
        return 85
    if pe_f < 25:
        return 70
    if pe_f < 40:
        return 50
    if pe_f < 60:
        return 30
    return 15


# ---------------------------------------------------------------------------
# Layer 3 — LLM comprehensive scoring + reasoning
# ---------------------------------------------------------------------------

DEEPSEEK_LAYER3_CAP = 10  # only send top 10 to DeepSeek (cost control)


def _layer3_llm_rank(candidates: list[dict]) -> list[dict]:
    """
    Use LLM to judge **buyability** — not just rank.

    Strategy (2026-04 science rework):
      - If DeepSeek enabled AND API key present:
        TOP 10 by score → DeepSeek makes buy/no-buy judgment (high quality)
        Remaining 11~30 → local LLM quick filter (saves tokens)
      - If no DeepSeek:
        All 30 → local LLM (as before, fallback)

    DeepSeek gets a RICH prompt with all Layer 2 data.
    Only returns stocks that pass the buyability check.
    """
    log.info("Layer 3: LLM 买入判断 (%d 只候选)...", len(candidates))

    overbought_rejected = [c for c in candidates if c.get("overbought")]
    viable = [c for c in candidates if not c.get("overbought")]
    if overbought_rejected:
        log.info("Layer 3: 排除 %d 只超买股票 (RSI>75)", len(overbought_rejected))

    candidates_sorted = sorted(viable, key=lambda x: x.get("score_l2", 0), reverse=True)
    top = candidates_sorted[:LAYER3_CAP]

    use_ds = _use_deepseek
    has_ds_key = False
    if use_ds:
        try:
            from config import get_deepseek_key
            has_ds_key = bool(get_deepseek_key())
        except Exception:
            pass

    all_evaluated = []

    if has_ds_key and use_ds:
        ds_batch = top[:DEEPSEEK_LAYER3_CAP]
        local_batch = top[DEEPSEEK_LAYER3_CAP:]
        log.info("Layer 3: DeepSeek 判断 TOP %d, 本地 LLM 判断剩余 %d",
                 len(ds_batch), len(local_batch))
        all_evaluated.extend(_layer3_deepseek_judge(ds_batch))
        all_evaluated.extend(_layer3_local_judge(local_batch))
    else:
        log.info("Layer 3: 全部使用本地 LLM 判断 (%d 只)", len(top))
        all_evaluated.extend(_layer3_local_judge(top))

    buyable = [s for s in all_evaluated
               if s.get("verdict") == "买入"
               and s.get("final_score", 0) >= MIN_BUYABILITY_SCORE]

    if not buyable:
        log.info("Layer 3: 本次扫描没有找到值得买入的股票 (这是正常的)")
        buyable = []

    buyable.sort(key=lambda x: x.get("final_score", 0), reverse=True)
    result = buyable[:TOP_N]

    log.info("Layer 3: %d 只通过买入判断 (共评估 %d 只)", len(result), len(all_evaluated))
    return result


def _layer3_deepseek_judge(stocks: list[dict]) -> list[dict]:
    """Use DeepSeek to make high-quality buy/no-buy decisions with rich data."""
    from config import call_deepseek

    system_prompt = (
        "你是一位顶级A股量化分析师，专注于判断股票是否值得**现在**买入。\n\n"
        "判断标准（必须全部考量）：\n"
        "1. 聪明钱信号：资金持续流入但股价未大涨=主力吸筹期（最佳买点）\n"
        "2. 追高惩罚：连续大涨、接近涨停板不追买（A股T+1，买入后当日无法卖出）\n"
        "3. 估值安全边际：PE在行业合理区间，PB不过高\n"
        "4. 技术面确认：不在超买区（RSI<70），有支撑位保护\n"
        "5. 基本面底线：盈利能力和财务健康至少中等\n"
        "6. 资金-价格背离：资金进但价格不涨 = 吸筹（好），资金出但价格涨 = 出货（危险）\n\n"
        "如果不确定或风险 > 收益，必须判定'不买入'。宁可错过，不可追高。\n\n"
        "输出要求：只输出一个JSON对象，格式如下（不要输出任何其他文字）：\n"
        '{"verdict":"买入","score":75,"reason":"核心理由3-5条","risk":"主要风险","buy_low":9.50,"buy_high":10.00,"strategy":"建议仓位和策略"}\n'
        "verdict 只能是 \"买入\" 或 \"不买入\"。score 0-100。buy_low/buy_high 是建议买入价区间。"
    )

    evaluated = []
    for stock in stocks:
        if _stop_event.is_set():
            break

        sym = stock["symbol"]
        log.info("Layer 3 DeepSeek: 判断 %s (%s)...", sym, stock["name"])

        prompt = _build_deepseek_scoring_prompt(stock)
        try:
            result = call_deepseek(system_prompt, prompt, max_tokens=1200, reasoning_effort="medium")
            if result["ok"]:
                raw = result["content"]
                parsed = _parse_llm_score(raw, stock)
                parsed["judged_by"] = "deepseek"
                # Store DeepSeek data for UI display
                parsed["deepseek"] = {
                    "report": parsed.get("reasoning", ""),
                    "reasoning": result.get("reasoning_content", ""),
                    "model": result.get("model", ""),
                    "usage": result.get("usage", {}),
                    "judgment": True,  # marks this as a Layer 3 judgment, not Phase 5 report
                }
                evaluated.append(parsed)
                log.info("  DeepSeek → %s (score=%s, tokens=%s)",
                         parsed.get("verdict"), parsed.get("final_score"),
                         result.get("usage", {}).get("total_tokens", "?"))
            else:
                log.warning("  DeepSeek 调用失败: %s, 降级到本地LLM", result.get("error"))
                evaluated.extend(_layer3_local_judge([stock]))
        except Exception as e:
            log.warning("  DeepSeek 异常: %s, 降级到本地LLM", e)
            evaluated.extend(_layer3_local_judge([stock]))

    return evaluated


def _build_deepseek_scoring_prompt(stock: dict) -> str:
    """Build a rich prompt for DeepSeek with all Layer 2 data."""
    signals_text = "\n".join(f"  - {k}: {v}" for k, v in stock.get("signals", {}).items())
    if not signals_text:
        signals_text = "  (无信号数据)"

    price = stock.get('price', 0)
    try:
        price_f = float(price)
    except (TypeError, ValueError):
        price_f = 0

    fund_text = ""
    dims = stock.get("fund_dimensions", {})
    if dims:
        parts = []
        for k, v in dims.items():
            parts.append(f"  - {k}: {v.get('score', 'N/A')}/100 ({v.get('detail', '')})")
        fund_text = "\n".join(parts)
    else:
        fund_text = "  (无基本面数据)"

    rsi_text = f"{stock.get('rsi', 'N/A')}"
    if stock.get("overbought"):
        rsi_text += " ⚠ 超买"

    ff_text = ""
    ff_signals = stock.get("ff_signals", {})
    if ff_signals:
        phase = ff_signals.get("smart_money_phase", "无信号")
        accum_s = ff_signals.get("accumulation_score", 0)
        detail = ff_signals.get("detail", "")
        divergence = ff_signals.get("fund_price_divergence", 0)
        ff_text = (
            f"  聪明钱阶段: {phase} (布局得分 {accum_s}/100)\n"
            f"  3日主力净流入: {ff_signals.get('main_net_3d', 'N/A')}\n"
            f"  10日主力净流入: {ff_signals.get('main_net_10d', 'N/A')}\n"
            f"  3日主力净占比: {ff_signals.get('main_pct_3d', 'N/A')}%\n"
            f"  超大单占比: {ff_signals.get('super_large_ratio', 'N/A')}\n"
            f"  价格-资金背离度: {divergence}\n"
            f"  吸筹信号: {'是' if ff_signals.get('accumulation_signal') else '否'}\n"
            f"  判断: {detail}"
        )
    else:
        ff_text = "  (无资金流向数据)"

    return f"""判断 {stock['name']} ({stock['symbol']}) 现在是否值得买入。

【行情快照】
  最新价: ¥{price}
  今日涨跌: {stock.get('change_pct', 'N/A')}%
  换手率: {stock.get('turnover_rate', 'N/A')}%
  成交额: {_format_amount(stock.get('amount'))}
  市盈率(PE): {stock.get('pe', 'N/A')}
  总市值: {_format_amount(stock.get('market_cap'))}

【Layer 2 各维度评分】
  资金流向评分: {stock.get('ff_score', 'N/A')}/100
  基本面评分: {stock.get('fund_score', 'N/A')}/100
  技术面评分: {stock.get('tech_score', 'N/A')}/100
  情绪评分: {stock.get('sentiment_score', 'N/A')}/100
  L1初筛分: {stock.get('score_l1', 'N/A')}
  L2综合分: {stock.get('score_l2', 'N/A')}

【资金流向详情】
{ff_text}

【基本面详情】
{fund_text}

【技术面信号】
  RSI: {rsi_text}
{signals_text}

请严格按照系统提示的JSON格式输出判断结果。
buy_low 和 buy_high 必须是数字（建议买入价区间，参考当前价 ¥{price_f:.2f}）。"""


def _layer3_local_judge(stocks: list[dict]) -> list[dict]:
    """Use local Ollama LLM for buy/no-buy judgment (fallback or for remaining stocks)."""
    model = MODEL_USAGE.get("prediction_reasoning", "qwen3.5:4b")
    evaluated = []

    for stock in stocks:
        if _stop_event.is_set():
            break

        prompt = _build_scoring_prompt(stock)
        try:
            resp = requests.post(
                f"{OLLAMA_HOST}/api/chat",
                json={
                    "model": model,
                    "messages": [
                        {"role": "system", "content": (
                            "你是专业A股分析师。你的任务是判断这只股票**现在是否值得买入**。"
                            "你必须非常严格：只有估值合理、基本面良好、技术面未严重超买的股票才推荐买入。"
                            "如果不确定或风险大于收益，必须判定为'不买入'。"
                            "只输出JSON，不要任何其他文字。"
                        )},
                        {"role": "user", "content": prompt},
                    ],
                    "stream": False,
                    "think": False,
                    "options": {"temperature": 0.3, "num_predict": 600},
                },
                timeout=120,
            )
            resp.raise_for_status()
            raw = resp.json().get("message", {}).get("content", "")
            parsed = _parse_llm_score(raw, stock)
            parsed["judged_by"] = "local"
            evaluated.append(parsed)
        except Exception as e:
            log.warning("LLM 评分 %s 失败: %s, 使用数值评分", stock["symbol"], e)
            stock["final_score"] = stock.get("score_l2", 0)
            stock["reasoning"] = "LLM评分不可用, 基于数值分析"
            stock["verdict"] = "观望"
            stock["judged_by"] = "fallback"
            evaluated.append(stock)

    return evaluated


def _build_scoring_prompt(stock: dict) -> str:
    signals_text = "\n".join(f"  - {k}: {v}" for k, v in stock.get("signals", {}).items())
    if not signals_text:
        signals_text = "  (无信号数据)"

    price = stock.get('price', 0)
    try:
        price_f = float(price)
    except (TypeError, ValueError):
        price_f = 0

    fund_text = ""
    dims = stock.get("fund_dimensions", {})
    if dims:
        parts = []
        for k, v in dims.items():
            parts.append(f"  - {k}: {v.get('score', 'N/A')}/100 ({v.get('detail', '')})")
        fund_text = "\n".join(parts)
    else:
        fund_text = "  (无基本面数据)"

    rsi_text = f"{stock.get('rsi', 'N/A')}"
    if stock.get("overbought"):
        rsi_text += " (超买警告)"

    ff_text = ""
    ff_signals = stock.get("ff_signals", {})
    if ff_signals:
        phase = ff_signals.get("smart_money_phase", "无信号")
        accum_s = ff_signals.get("accumulation_score", 0)
        detail = ff_signals.get("detail", "")
        ff_text = (
            f"  - 3日主力净流入: {ff_signals.get('main_net_3d', 'N/A')}\n"
            f"  - 10日主力净流入: {ff_signals.get('main_net_10d', 'N/A')}\n"
            f"  - 3日主力净占比: {ff_signals.get('main_pct_3d', 'N/A')}%\n"
            f"  - 聪明钱阶段: {phase} (得分 {accum_s}/100)\n"
            f"  - 判断: {detail}"
        )
    else:
        ff_text = "  (无资金流向数据)"

    return f"""判断这只A股股票**现在是否值得买入**。

核心原则(A股特色):
1. 跟随"聪明钱"吸筹：资金持续流入但股价未大涨=主力吸筹(最佳信号)
2. 追高是最大敌人：连续大涨、涨停板后不追买(A股T+1,买入后当日无法卖出)
3. 估值合理+基本面良好是安全底线
4. A股T+1风险：买入即锁仓一天,所以不能追高,要有足够安全边际
5. 如果不确定或风险大于收益,必须判定"不买入"

数据:
- 股票: {stock['name']} ({stock['symbol']})
- 最新价: ¥{price}
- 涨跌幅: {stock.get('change_pct', 'N/A')}%
- 换手率: {stock.get('turnover_rate', 'N/A')}%
- 市盈率(PE): {stock.get('pe', 'N/A')}
- RSI: {rsi_text}
- 成交额: {_format_amount(stock.get('amount'))}
- 资金流向评分: {stock.get('ff_score', 'N/A')}/100
- 资金流向详情:
{ff_text}
- 基本面评分: {stock.get('fund_score', 'N/A')}/100
- 基本面详情:
{fund_text}
- 技术得分: {stock.get('tech_score', 'N/A')}/100
- 情绪得分: {stock.get('sentiment_score', 'N/A')}/100
- 技术信号:
{signals_text}

要求: 直接输出一个JSON对象，不要输出任何其他文字。
verdict 字段必须是 "买入" 或 "不买入"。只有你确信值得买入时才填"买入"。
格式(buy_low和buy_high是数字):
{{"verdict":"买入","score":75,"reason":"资金持续流入且股价回调充分,估值合理,T+1安全边际足够","risk":"行业竞争加剧","buy_low":{price_f * 0.95:.2f},"buy_high":{price_f * 1.0:.2f}}}

你的回复(只输出JSON):"""


def _parse_llm_score(raw: str, stock: dict) -> dict:
    import re
    text = raw.strip()

    text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL).strip()

    m = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if m:
        text = m.group(1)

    start = text.find("{")
    end = text.rfind("}") + 1
    if start >= 0 and end > start:
        json_str = text[start:end]
        json_str = json_str.replace("'", '"')
        json_str = re.sub(r",\s*}", "}", json_str)
        try:
            parsed = json.loads(json_str)
            stock["final_score"] = float(parsed.get("score", stock.get("score_l2", 0)))
            stock["reasoning"] = parsed.get("reason", "")
            stock["risk"] = parsed.get("risk", "")
            stock["buy_low"] = _safe_float(parsed.get("buy_low"))
            stock["buy_high"] = _safe_float(parsed.get("buy_high"))
            stock["strategy"] = parsed.get("strategy", "")
            verdict_raw = str(parsed.get("verdict", "")).strip()
            stock["verdict"] = "买入" if "买入" in verdict_raw and "不" not in verdict_raw else "观望"
            return stock
        except (json.JSONDecodeError, ValueError) as e:
            log.warning("LLM JSON解析失败: %s | raw=%s", e, json_str[:200])

    stock["final_score"] = stock.get("score_l2", 0)
    stock["reasoning"] = "LLM输出解析失败, 基于数值分析"
    stock["risk"] = ""
    stock["verdict"] = "观望"
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
# Phase 4: Comprehensive analysis for recommended picks
# ---------------------------------------------------------------------------

def _run_comprehensive_for_picks(top_picks: list[dict], progress: dict) -> list[dict]:
    """Run multi-dimensional analysis for each recommended stock."""
    from technical_analysis import load_ohlcv, compute_indicators, evaluate_signals
    from fundamental_analysis import score_fundamentals

    enriched = []
    for i, pick in enumerate(top_picks):
        if _stop_event.is_set():
            enriched.append(pick)
            continue

        sym = pick["symbol"]
        log.info("综合分析 %d/%d: %s (%s)", i + 1, len(top_picks), sym, pick.get("name", ""))
        progress["comprehensive_current"] = f"{sym} ({i+1}/{len(top_picks)})"
        _save_progress(progress)

        comp = {"dimensions": {}, "verdict_details": [], "star_rating": 0}
        total_support = 0
        total_dims = 0

        try:
            df = load_ohlcv(sym)
            if df is not None and not df.empty:
                df = compute_indicators(df)
                sig = evaluate_signals(df)
                overall = sig.get("overall", "中性")
                bullish = sig.get("bullish_count", 0)
                bearish = sig.get("bearish_count", 0)
                rsi = sig.get("rsi_14", 50)
                support = sig.get("support_levels", [])
                resistance = sig.get("resistance_levels", [])

                tech_supports_buy = overall in ("看涨", "偏多") and rsi < 75
                comp["dimensions"]["technical"] = {
                    "overall": overall,
                    "bullish": bullish,
                    "bearish": bearish,
                    "rsi": round(rsi, 1) if isinstance(rsi, float) else rsi,
                    "support": support[:2] if support else [],
                    "resistance": resistance[:2] if resistance else [],
                    "supports_buy": tech_supports_buy,
                    "signals": sig.get("bullish_signals", [])[:3],
                    "warnings": sig.get("bearish_signals", [])[:3],
                }
                total_dims += 1
                if tech_supports_buy:
                    total_support += 1
                    comp["verdict_details"].append("技术面偏多")
                else:
                    comp["verdict_details"].append(f"技术面{overall}")
        except Exception as e:
            log.debug("综合分析-技术 %s 失败: %s", sym, e)

        try:
            from model_xgboost import train_and_predict
            xgb = train_and_predict(sym)
            if xgb and not xgb.get("error"):
                direction = xgb.get("direction", "平")
                confidence = xgb.get("confidence", 0)
                ml_supports = direction == "涨" and confidence > 50
                comp["dimensions"]["ml_direction"] = {
                    "direction": direction,
                    "confidence": round(confidence, 1),
                    "supports_buy": ml_supports,
                }
                total_dims += 1
                if ml_supports:
                    total_support += 1
                    comp["verdict_details"].append(f"ML预测看涨({confidence:.0f}%)")
                else:
                    comp["verdict_details"].append(f"ML预测{direction}")
        except Exception as e:
            log.debug("综合分析-ML方向 %s 失败: %s", sym, e)

        try:
            from model_price_predictor import train_price_prediction
            pp = train_price_prediction(sym)
            if pp and not pp.get("error"):
                preds = pp.get("predictions", {})
                close_pred = preds.get("close")
                high_pred = preds.get("high")
                low_pred = preds.get("low")
                current = pp.get("current_close")
                chg = pp.get("change_pct", {})

                price_supports = (chg.get("close", 0) or 0) > 0.5
                comp["dimensions"]["price_prediction"] = {
                    "current": current,
                    "pred_close": close_pred,
                    "pred_high": high_pred,
                    "pred_low": low_pred,
                    "change_pct": round(chg.get("close", 0) or 0, 2),
                    "supports_buy": price_supports,
                }
                total_dims += 1
                if price_supports:
                    total_support += 1
                    comp["verdict_details"].append(f"价格预测看涨({chg.get('close',0):+.1f}%)")
                else:
                    comp["verdict_details"].append("价格预测偏中性")
        except Exception as e:
            log.debug("综合分析-价格预测 %s 失败: %s", sym, e)

        try:
            from china_market_data import stock_fund_flow_signals
            ff = stock_fund_flow_signals(sym)
            if ff and ff.get("main_net_3d") is not None:
                accum = ff.get("accumulation_signal", False)
                main_3d = ff.get("main_net_3d", 0)
                phase = ff.get("smart_money_phase", "无信号")
                accum_score = ff.get("accumulation_score", 0)
                detail = ff.get("detail", "")

                ff_supports = phase == "布局期" or (accum and main_3d > 0)

                comp["dimensions"]["fund_flow"] = {
                    "main_net_3d": main_3d,
                    "main_net_10d": ff.get("main_net_10d"),
                    "accumulation": accum,
                    "smart_money_phase": phase,
                    "accumulation_score": accum_score,
                    "detail": detail,
                    "supports_buy": ff_supports,
                }
                total_dims += 1
                if ff_supports:
                    total_support += 1
                    if phase == "布局期":
                        comp["verdict_details"].append(f"聪明钱布局期(得分{accum_score})")
                    else:
                        comp["verdict_details"].append("资金净流入")
                elif phase == "出货期":
                    comp["verdict_details"].append("⚠ 疑似出货")
                elif phase == "拉升期":
                    comp["verdict_details"].append("已进入拉升期,追高风险")
                else:
                    comp["verdict_details"].append("资金流出")
        except Exception as e:
            log.debug("综合分析-资金流向 %s 失败: %s", sym, e)

        scanner_supports = pick.get("verdict") == "买入"
        if scanner_supports:
            total_support += 1
            total_dims += 1
            comp["verdict_details"].insert(0, "Scanner推荐买入")
        else:
            total_dims += 1
            comp["verdict_details"].insert(0, "Scanner评分入选")

        if total_dims > 0:
            star = round(total_support / total_dims * 5)
        else:
            star = 0
        comp["star_rating"] = star
        comp["support_count"] = total_support
        comp["total_dims"] = total_dims

        if star >= 4:
            comp["conclusion"] = "多维共振,建议建仓"
        elif star >= 3:
            comp["conclusion"] = "多数支持,可考虑小仓"
        elif star >= 2:
            comp["conclusion"] = "信号分歧,建议观望"
        else:
            comp["conclusion"] = "支持不足,暂不建议"

        pick["comprehensive"] = comp
        enriched.append(pick)
        log.info("综合分析 %s: %d星 (%d/%d支持) — %s",
                 sym, star, total_support, total_dims, comp["conclusion"])

    return enriched


def _run_deepseek_for_picks(top_picks: list[dict], progress: dict) -> list[dict]:
    """Generate DeepSeek deep-dive reports for TOP picks (post-Layer 3).

    NOTE: Since 2026-04 rework, DeepSeek's primary role is in Layer 3 (judgment).
    This Phase 5 now generates *supplementary detailed reports* only for picks that
    were judged by local LLM (not already handled by DeepSeek in Layer 3).
    Picks that already have DeepSeek reasoning from Layer 3 skip Phase 5.
    """
    from config import call_deepseek, get_deepseek_key

    if not get_deepseek_key():
        log.info("DeepSeek Phase 5: 无API key, 跳过")
        return top_picks

    # Only generate reports for picks NOT already judged by DeepSeek in Layer 3
    needs_report = [p for p in top_picks if p.get("judged_by") != "deepseek"]
    if not needs_report:
        log.info("DeepSeek Phase 5: 所有推荐已由DeepSeek判断, 跳过报告生成")
        return top_picks

    system_prompt = (
        "你是一位资深A股市场分析师。请对以下股票进行深度分析报告。\n"
        "报告要求：\n"
        "1. 综合判断（买入/观望/回避）及信心水平\n"
        "2. 核心理由（3-5条）\n"
        "3. 风险提示（量化风险）\n"
        "4. 建议操作策略（仓位、止损价、目标价）\n"
        "注意：A股是T+1市场，买入即锁仓一天，追高风险极大。"
    )

    for i, pick in enumerate(needs_report):
        if _stop_event.is_set():
            break

        sym = pick["symbol"]
        name = pick.get("name", sym)
        progress["deepseek_current"] = f"{sym} ({i+1}/{len(needs_report)})"
        _save_progress(progress)

        comp = pick.get("comprehensive", {})
        dims = comp.get("dimensions", {})
        details = comp.get("verdict_details", [])

        parts = [
            f"股票: {name} ({sym})",
            f"Scanner评分: {pick.get('final_score', 'N/A')}/100",
            f"Scanner判定: {pick.get('verdict', 'N/A')}",
            f"综合星级: {comp.get('star_rating', '?')}/5",
            f"综合结论: {comp.get('conclusion', '')}",
            f"判据: {', '.join(details)}",
        ]

        tech = dims.get("technical", {})
        if tech:
            parts.append(f"\n技术面: {tech.get('overall', '?')} | RSI={tech.get('rsi','?')} "
                         f"| 看涨{tech.get('bullish',0)} 看跌{tech.get('bearish',0)}")
            if tech.get("signals"):
                parts.append(f"  信号: {', '.join(tech['signals'][:5])}")
            if tech.get("support"):
                parts.append(f"  支撑: {tech['support']}")
            if tech.get("resistance"):
                parts.append(f"  阻力: {tech['resistance']}")

        ml = dims.get("ml_direction", {})
        if ml:
            parts.append(f"\nML方向预测: {ml.get('direction','?')} (置信度 {ml.get('confidence',0)}%)")

        pp = dims.get("price_prediction", {})
        if pp:
            parts.append(f"\n明日价格预测: 收盘{pp.get('change_pct',0):+.1f}%"
                         f" | 区间 ¥{pp.get('pred_low','?')}~¥{pp.get('pred_high','?')}")

        ff = dims.get("fund_flow", {})
        if ff:
            parts.append(f"\n资金流向: {ff.get('smart_money_phase','?')} "
                         f"(布局得分{ff.get('accumulation_score',0)})")
            if ff.get("detail"):
                parts.append(f"  {ff['detail']}")

        parts.append(f"\nLLM分析: {pick.get('reasoning', 'N/A')}")
        if pick.get("risk"):
            parts.append(f"风险: {pick['risk']}")

        user_prompt = "\n".join(parts)

        try:
            log.info("DeepSeek 报告 %s (%d/%d)...", sym, i+1, len(needs_report))
            result = call_deepseek(system_prompt, user_prompt, max_tokens=2048)
            if result["ok"]:
                pick["deepseek"] = {
                    "report": result["content"],
                    "reasoning": result.get("reasoning_content", ""),
                    "model": result.get("model", ""),
                    "usage": result.get("usage", {}),
                }
                log.info("DeepSeek 报告 %s 完成 (tokens: %s)",
                         sym, result.get("usage", {}).get("total_tokens", "?"))
            else:
                pick["deepseek"] = {"error": result.get("error", "Unknown")}
                log.warning("DeepSeek 分析 %s 失败: %s", sym, result.get("error"))
        except Exception as e:
            pick["deepseek"] = {"error": str(e)}
            log.warning("DeepSeek 分析 %s 异常: %s", sym, e)

    return top_picks


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
        f"**通过买入判断**: {len(top_picks)} 只",
        "",
    ]

    if not top_picks:
        lines.extend([
            "---",
            "",
            "## 本次扫描结果：暂无推荐",
            "",
            "经过三层筛选和 LLM 买入判断，本次没有找到同时满足以下条件的股票：",
            "- 估值合理（PE 不过高）",
            "- 基本面良好（盈利/成长/财务健康）",
            "- 技术面未严重超买",
            "- LLM 综合判断值得买入",
            "",
            "**这是正常的** — 在多数交易日，真正值得买入的标的并不多。",
            "\"不推荐\"本身就是最好的建议。",
            "",
        ])
    else:
        lines.extend([
            "---",
            "",
            "## 推荐买入",
            "",
        ])

        for i, pick in enumerate(top_picks, 1):
            judged = pick.get("judged_by", "local")
            judge_tag = "🔬 DeepSeek" if judged == "deepseek" else "🤖 本地LLM"
            lines.extend([
                f"### {i}. {pick['name']} ({pick['symbol']})",
                "",
                f"- **买入判定**: ✅ 值得买入 ({judge_tag}判断)",
                f"- **综合得分**: {pick.get('final_score', 'N/A'):.1f}/100",
                f"- **最新价**: ¥{pick.get('price', 'N/A')}",
                f"- **涨跌幅**: {pick.get('change_pct', 'N/A')}%",
                f"- **市盈率(PE)**: {pick.get('pe', 'N/A')}",
                f"- **资金流向评分**: {pick.get('ff_score', 'N/A')}/100",
                f"- **基本面得分**: {pick.get('fund_score', 'N/A')}/100",
                f"- **技术得分**: {pick.get('tech_score', 'N/A')}/100",
                f"- **情绪得分**: {pick.get('sentiment_score', 'N/A')}/100",
                f"- **RSI**: {pick.get('rsi', 'N/A')}",
                f"- **推荐理由**: {pick.get('reasoning', 'N/A')}",
                f"- **主要风险**: {pick.get('risk', 'N/A')}",
                f"- **操作策略**: {pick.get('strategy', 'N/A')}",
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

    _stale = [
        "hot_sectors", "technical_analysis", "report_technical",
        "fundamental_analysis", "sentiment", "features", "model_xgboost",
        "fetch_market_data", "china_market_data", "llm_reasoning",
        "market_sentiment", "black_swan_detector",
    ]
    for m in _stale:
        sys.modules.pop(m, None)

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
        "use_deepseek": _use_deepseek,
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

    use_ds = progress.get("use_deepseek", False)
    progress["status"] = "layer3"
    if use_ds:
        progress["layer3_mode"] = "deepseek+local"
    _save_progress(progress)

    top_picks = _layer3_llm_rank(all_l2)

    if top_picks and not _stop_event.is_set():
        progress["status"] = "comprehensive"
        progress["top_picks"] = top_picks
        _save_progress(progress)
        log.info("Phase 4: 对 %d 只推荐股票运行综合分析...", len(top_picks))
        top_picks = _run_comprehensive_for_picks(top_picks, progress)

    # Phase 5: supplementary DeepSeek reports only for picks judged by local LLM
    if use_ds and top_picks and not _stop_event.is_set():
        local_judged = [p for p in top_picks if p.get("judged_by") != "deepseek"]
        if local_judged:
            progress["status"] = "deepseek"
            _save_progress(progress)
            log.info("Phase 5: DeepSeek 补充报告 for %d 只本地判断股票...", len(local_judged))
            top_picks = _run_deepseek_for_picks(top_picks, progress)
        else:
            log.info("Phase 5: 跳过 — 所有推荐已由 DeepSeek 在 Layer 3 判断")

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

def start_scan(use_deepseek: bool = False) -> dict:
    """Start a background scan. Returns status."""
    global _scan_thread, _use_deepseek

    log.info("start_scan called (deepseek=%s)", use_deepseek)
    with _scan_lock:
        if _scan_thread is not None and _scan_thread.is_alive():
            return {"ok": False, "error": "扫描正在进行中", "status": get_scan_status()}

        _use_deepseek = use_deepseek
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
