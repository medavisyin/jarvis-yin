"""
AI Long-Term Stock Scanner — news/policy/trend-driven investment theme analysis
with mandatory precious metals outlook and industry-adaptive upside assessment.

Architecture:
  Step 1  信号收集    (14 days of news + market signals)
  Step 2  贵金属分析  (gold/silver mandatory analysis)
  Step 3  LLM趋势研判 (identify 3-5 investment themes)
  Step 4  主题→个股   (map themes to representative stocks)
  Step 5  空间评估    (industry-adaptive upside assessment)
  Step 6  LLM精选     (final ≤5 picks with reasoning)

Signal Sources:
  - Finance news (6 categories): markets, china-policy, us-political, crypto, gold, oil
    (C:/reports/ai/YYYY-MM-DD/finance-news/finance-news-data.json)
  - Legacy world-news JSON, if still on disk, is folded into 综合市场 only
  - AI/tech news: arXiv, HuggingFace, OpenAI, etc.
    (C:/reports/ai/YYYY-MM-DD/briefing-data.json)
  - Black swan detector results
  - Hot sector trends (consecutive strength)
  - Global sentiment (VIX, Fear/Greed)
  - Precious metals (Shanghai Gold/Silver Benchmark via akshare)
"""
import json
import logging
import os
import re
import sys
import threading
import uuid as _uuid
from datetime import datetime, timedelta
from urllib.parse import quote

import akshare as ak
import pandas as pd
import requests

from config import (
    REPORTS_ROOT,
    STOCK_CACHE_DIR,
    STOCK_REPORTS_ROOT,
    MODEL_USAGE,
    OLLAMA_HOST,
)

log = logging.getLogger(__name__)

LONG_TERM_DIR = os.path.join(STOCK_REPORTS_ROOT, "long_term")
PROGRESS_FILE = os.path.join(LONG_TERM_DIR, "lt_progress.json")
_REPORTS_AI_ROOT = REPORTS_ROOT

SIGNAL_WINDOW_DAYS = 14
MAX_PICKS = 5

FINANCE_CATEGORIES = (
    "markets", "china-policy", "us-political", "crypto", "gold", "oil",
)
FINANCE_CAT_LABELS = {
    "markets": "综合市场",
    "china-policy": "中国政策金融",
    "us-political": "美国政治金融",
    "crypto": "数字货币",
    "gold": "黄金",
    "oil": "石油",
}
OFFICIAL_SOURCE_IDS = frozenset({
    "pboc", "csrc", "bls", "bea", "census", "ism", "adp", "fed",
})
HEADLINES_PER_FINANCE_CAT = 20
YAHOO_SERIES = {
    "oil": {"symbol": "CL=F", "label": "WTI原油", "fallbacks": ()},
    "dollar": {"symbol": "DX-Y.NYB", "label": "美元指数", "fallbacks": ("DXY",)},
    "rates": {"symbol": "^TNX", "label": "美债10Y", "fallbacks": ()},
    "crypto": {"symbol": "BTC-USD", "label": "比特币", "fallbacks": ()},
}
USA_MACRO_SERIES = (
    ("nfp", "非农就业", ("macro_usa_non_farm", "macro_usa_non_farm_payroll")),
    ("unemployment", "失业率", ("macro_usa_unemployment_rate",)),
    ("ism_pmi", "ISM制造业PMI", ("macro_usa_ism_pmi", "macro_usa_pmi")),
    ("adp", "ADP就业", ("macro_usa_adp_employment", "macro_usa_adp")),
)

_lt_lock = threading.Lock()
_lt_thread: threading.Thread | None = None
_stop_event = threading.Event()
_use_deepseek = False


def _ensure_dirs():
    os.makedirs(LONG_TERM_DIR, exist_ok=True)
    os.makedirs(STOCK_CACHE_DIR, exist_ok=True)


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


def get_lt_status() -> dict:
    prog = _load_progress()
    prog["running"] = _lt_thread is not None and _lt_thread.is_alive()
    return prog


# ---------------------------------------------------------------------------
# Step 1: Signal collection (14-day window)
# ---------------------------------------------------------------------------


def _collect_signals() -> dict:
    """Collect all signal sources from the past 14 days."""
    log.info("Step 1: 收集近 %d 天信号...", SIGNAL_WINDOW_DAYS)
    signals = {
        "world_news": [],
        "ai_tech_news": [],
        "finance_news": [],
        "finance_by_category": {cid: [] for cid in FINANCE_CATEGORIES},
        "black_swan": None,
        "hot_sectors": [],
        "market_sentiment": None,
        "collection_window": f"{SIGNAL_WINDOW_DAYS} days",
    }

    today = datetime.now()
    for i in range(SIGNAL_WINDOW_DAYS):
        date = today - timedelta(days=i)
        date_str = date.strftime("%Y-%m-%d")

        wn_path = os.path.join(
            _REPORTS_AI_ROOT, date_str, "world-news", "world-news-data.json"
        )
        if os.path.isfile(wn_path):
            try:
                with open(wn_path, encoding="utf-8") as f:
                    wn_data = json.load(f)
                items = _extract_news_items(wn_data, date_str, "world")
                signals["world_news"].extend(items)
            except Exception as e:
                log.debug("世界新闻 %s 读取失败: %s", date_str, e)

        bd_path = os.path.join(_REPORTS_AI_ROOT, date_str, "briefing-data.json")
        if os.path.isfile(bd_path):
            try:
                with open(bd_path, encoding="utf-8") as f:
                    bd_data = json.load(f)
                items = _extract_news_items(bd_data, date_str, "ai_tech")
                signals["ai_tech_news"].extend(items)
            except Exception as e:
                log.debug("AI新闻 %s 读取失败: %s", date_str, e)

        fn_path = os.path.join(
            _REPORTS_AI_ROOT, date_str, "finance-news", "finance-news-data.json"
        )
        if os.path.isfile(fn_path):
            try:
                with open(fn_path, encoding="utf-8") as f:
                    fn_data = json.load(f)
                items = _extract_finance_news_items(fn_data, date_str)
                signals["finance_news"].extend(items)
                for item in items:
                    cat = item.get("category") or ""
                    if cat in signals["finance_by_category"]:
                        signals["finance_by_category"][cat].append(item)
            except Exception as e:
                log.debug("财经新闻 %s 读取失败: %s", date_str, e)

    log.info(
        "  世界新闻: %d 条, AI/科技新闻: %d 条, 财经新闻: %d 条",
        len(signals["world_news"]),
        len(signals["ai_tech_news"]),
        len(signals["finance_news"]),
    )

    _collect_live_market_signals(signals)
    return signals


def _collect_live_market_signals(signals: dict) -> None:
    """Black swan, hot sectors, VIX — extracted so tests can no-op this."""
    try:
        from black_swan_detector import load_cached_alerts, scan_world_news
        alerts = load_cached_alerts() or scan_world_news()
        signals["black_swan"] = alerts
        alert_count = len(alerts.get("alerts", []))
        log.info("  黑天鹅检测: %d 个警报", alert_count)
    except Exception as e:
        log.warning("  黑天鹅检测失败: %s", e)

    try:
        from hot_sectors import fetch_hot_sectors
        sectors = fetch_hot_sectors()
        signals["hot_sectors"] = sectors or []
        log.info("  热门板块: %d 个", len(signals["hot_sectors"]))
    except Exception as e:
        log.warning("  热门板块获取失败: %s", e)

    try:
        from market_sentiment import fetch_all_sentiment
        signals["market_sentiment"] = fetch_all_sentiment()
        log.info("  全球情绪指标已获取")
    except Exception as e:
        log.warning("  全球情绪指标失败: %s", e)


def _extract_news_items(data: dict, date_str: str, source_type: str) -> list[dict]:
    """Extract headline + summary from news data JSON."""
    items = []
    if isinstance(data, dict):
        for cat in data.get("categories", data.get("sections", [])):
            cat_name = cat.get("category", cat.get("name", ""))
            for item in cat.get("items", cat.get("articles", [])):
                headline = (
                    item.get("headline")
                    or item.get("title")
                    or item.get("标题", "")
                )
                summary = (
                    item.get("summary")
                    or item.get("description")
                    or item.get("内容", "")
                )
                if headline:
                    items.append({
                        "date": date_str,
                        "source_type": source_type,
                        "category": cat_name,
                        "headline": headline[:200],
                        "summary": (summary or "")[:500],
                    })
    elif isinstance(data, list):
        for item in data:
            headline = item.get("headline") or item.get("title", "")
            summary = item.get("summary") or item.get("description", "")
            if headline:
                items.append({
                    "date": date_str,
                    "source_type": source_type,
                    "category": "",
                    "headline": headline[:200],
                    "summary": (summary or "")[:500],
                })
    return items


def _extract_finance_news_items(data: dict, date_str: str) -> list[dict]:
    """Extract finance-news-data.json items; prefer Chinese titles."""
    items = []
    if not isinstance(data, dict):
        return items
    for cat in data.get("categories") or []:
        cat_name = cat.get("category") or ""
        for item in cat.get("items") or []:
            headline = (
                item.get("title_zh")
                or item.get("title")
                or item.get("headline")
                or ""
            )
            summary = item.get("summary_zh") or item.get("summary") or ""
            if not headline:
                continue
            items.append({
                "date": date_str,
                "source_type": "finance",
                "category": cat_name,
                "source_id": item.get("source_id") or "",
                "headline": headline[:200],
                "summary": (summary or "")[:500],
            })
    return items


# ---------------------------------------------------------------------------
# Step 2: Precious metals analysis (mandatory every run)
# ---------------------------------------------------------------------------


def _analyze_precious_metals() -> dict:
    """
    Mandatory analysis of gold and silver.
    Uses Shanghai Gold/Silver Benchmark prices from akshare.
    """
    log.info("Step 2: 贵金属分析...")
    result = {"gold": _analyze_gold(), "silver": _analyze_silver()}

    gold_price = result["gold"].get("latest_price")
    silver_price = result["silver"].get("latest_price")
    if gold_price and silver_price and silver_price > 0:
        ratio = gold_price / silver_price
        result["gold_silver_ratio"] = round(ratio, 2)
        if ratio > 80:
            result["ratio_signal"] = "白银相对便宜 (金银比偏高)"
        elif ratio < 60:
            result["ratio_signal"] = "白银相对偏贵 (金银比偏低)"
        else:
            result["ratio_signal"] = "金银比正常区间"
    else:
        result["gold_silver_ratio"] = None
        result["ratio_signal"] = "数据不足"

    log.info("  贵金属分析完成 (金银比: %s)", result.get("gold_silver_ratio"))
    return result


def _analyze_gold() -> dict:
    """Analyze gold price trends using Shanghai Gold Benchmark."""
    return _analyze_metal("gold", _fetch_gold_data, "黄金")


def _analyze_silver() -> dict:
    """Analyze silver price trends using Shanghai Silver Benchmark."""
    return _analyze_metal("silver", _fetch_silver_data, "白银")


def _fetch_gold_data() -> pd.DataFrame | None:
    """Fetch Shanghai Gold Benchmark price data."""
    try:
        df = ak.spot_golden_benchmark_sge()
        if df is not None and not df.empty:
            df.columns = [c.strip() for c in df.columns]
            date_col = [c for c in df.columns if "时间" in c or "date" in c.lower()]
            if date_col:
                df["date"] = pd.to_datetime(df[date_col[0]], errors="coerce")
            price_col = [c for c in df.columns if "早盘" in c or "晚盘" in c]
            if price_col:
                df["price"] = pd.to_numeric(df[price_col[0]], errors="coerce")
            df = df.dropna(subset=["date", "price"]).sort_values("date")
            return df
    except Exception as e:
        log.warning("上海金基准价获取失败: %s", e)
    return None


def _fetch_silver_data() -> pd.DataFrame | None:
    """Fetch Shanghai Silver Benchmark price data."""
    try:
        df = ak.spot_silver_benchmark_sge()
        if df is not None and not df.empty:
            df.columns = [c.strip() for c in df.columns]
            date_col = [c for c in df.columns if "时间" in c or "date" in c.lower()]
            if date_col:
                df["date"] = pd.to_datetime(df[date_col[0]], errors="coerce")
            price_col = [c for c in df.columns if "早盘" in c or "晚盘" in c]
            if price_col:
                df["price"] = pd.to_numeric(df[price_col[0]], errors="coerce")
            df = df.dropna(subset=["date", "price"]).sort_values("date")
            return df
    except Exception as e:
        log.warning("上海银基准价获取失败: %s", e)
    return None


def _empty_series_result(label: str) -> dict:
    return {
        "name": label,
        "latest_price": None,
        "trend": "unknown",
        "rsi_14": None,
        "change_14d_pct": None,
        "change_60d_pct": None,
        "percentile_60d": None,
        "ma20_deviation_pct": None,
        "position_vs_52w": None,
        "upside_score": None,
        "data_available": False,
    }


def _analyze_series(label: str, df: pd.DataFrame | None) -> dict:
    """Trend / RSI / 52w stats for any date+price series. None or short → empty."""
    result = _empty_series_result(label)
    if df is None or not isinstance(df, pd.DataFrame) or df.empty:
        return result
    if "price" not in df.columns or "date" not in df.columns:
        return result
    work = df.dropna(subset=["date", "price"]).sort_values("date")
    if len(work) < 30:
        log.warning("  %s 数据不足 (需 >=30 天)", label)
        return result

    result["data_available"] = True
    latest = work["price"].iloc[-1]
    result["latest_price"] = round(float(latest), 2)

    if len(work) >= 14:
        p14 = work["price"].iloc[-14]
        if p14:
            result["change_14d_pct"] = round((latest - p14) / p14 * 100, 2)

    if len(work) >= 60:
        p60 = work["price"].iloc[-60]
        if p60:
            result["change_60d_pct"] = round((latest - p60) / p60 * 100, 2)

    if len(work) >= 14:
        delta = work["price"].diff().iloc[-14:]
        gain = delta.clip(lower=0).mean()
        loss = (-delta.clip(upper=0)).mean()
        if loss > 0:
            rs = gain / loss
            result["rsi_14"] = round(100 - 100 / (1 + rs), 1)
        else:
            result["rsi_14"] = 100.0

    if len(work) >= 20:
        ma20 = work["price"].iloc[-20:].mean()
        if ma20:
            result["ma20_deviation_pct"] = round((latest - ma20) / ma20 * 100, 2)

    year_data = work.tail(min(252, len(work)))
    high_52w = year_data["price"].max()
    low_52w = year_data["price"].min()
    if high_52w > low_52w:
        pos = (latest - low_52w) / (high_52w - low_52w) * 100
        result["position_vs_52w"] = round(pos, 1)

    if len(work) >= 60:
        rolling_60d = work["price"].rolling(60).apply(
            lambda x: (x.iloc[-1] - x.iloc[0]) / x.iloc[0] * 100 if len(x) == 60 else 0
        ).dropna()
        if len(rolling_60d) > 10:
            current_change = result["change_60d_pct"] or 0
            rank = (rolling_60d < current_change).sum() / len(rolling_60d) * 100
            result["percentile_60d"] = round(rank, 1)

    rsi = result["rsi_14"] or 50
    pos_52w = result["position_vs_52w"] or 50
    pct_60d = result["percentile_60d"] or 50
    ma_dev = abs(result["ma20_deviation_pct"] or 0)

    score = 100
    if rsi > 70:
        score -= (rsi - 70) * 2
    if pos_52w > 85:
        score -= (pos_52w - 85) * 1.5
    if pct_60d > 80:
        score -= (pct_60d - 80) * 1.0
    if ma_dev > 5:
        score -= (ma_dev - 5) * 2
    result["upside_score"] = max(0, min(100, round(score)))

    if rsi > 70 and pos_52w > 90:
        result["trend"] = "过热"
    elif result["change_14d_pct"] and result["change_14d_pct"] > 3:
        result["trend"] = "上涨"
    elif result["change_14d_pct"] and result["change_14d_pct"] < -3:
        result["trend"] = "下跌"
    else:
        result["trend"] = "震荡"

    return result


def _analyze_metal(_name: str, fetch_fn, label: str) -> dict:
    """Generic metal analysis: trend, RSI, percentile position, MA deviation."""
    try:
        df = fetch_fn()
    except Exception as e:
        log.warning("  %s 获取失败: %s", label, e)
        df = None
    return _analyze_series(label, df)


def _yahoo_proxies() -> dict:
    proxy = os.environ.get("STOCK_PROXY")
    if proxy:
        return {"http": proxy, "https": proxy}
    return {}


def _yahoo_chart_to_df(payload: dict) -> pd.DataFrame:
    result = (payload or {}).get("chart", {}).get("result") or []
    if not result:
        return pd.DataFrame(columns=["date", "price"])
    block = result[0]
    ts = block.get("timestamp") or []
    closes = ((block.get("indicators") or {}).get("quote") or [{}])[0].get("close") or []
    rows = []
    for t, c in zip(ts, closes):
        if c is None:
            continue
        rows.append({"date": pd.to_datetime(t, unit="s", utc=True), "price": float(c)})
    if not rows:
        return pd.DataFrame(columns=["date", "price"])
    return pd.DataFrame(rows).sort_values("date")


def _fetch_yahoo_daily(symbol: str) -> pd.DataFrame | None:
    """1y daily closes from Yahoo chart. Tries query1 then query2. Returns None on failure."""
    encoded = quote(symbol, safe="")
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
    proxies = _yahoo_proxies()
    for host in ("query1", "query2"):
        url = f"https://{host}.finance.yahoo.com/v8/finance/chart/{encoded}?interval=1d&range=1y"
        try:
            resp = requests.get(url, headers=headers, timeout=15, proxies=proxies)
            resp.raise_for_status()
            df = _yahoo_chart_to_df(resp.json())
            if df is not None and len(df) >= 30:
                return df
        except Exception as e:
            log.debug("Yahoo %s %s failed: %s", host, symbol, e)
    log.warning("Yahoo 序列获取失败: %s", symbol)
    return None


def _analyze_market_factors() -> dict:
    out = {}
    for key, spec in YAHOO_SERIES.items():
        df = _fetch_yahoo_daily(spec["symbol"])
        if df is None:
            for fb in spec.get("fallbacks") or ():
                df = _fetch_yahoo_daily(fb)
                if df is not None:
                    break
        out[key] = _analyze_series(spec["label"], df)
    return out


def _build_macro_dashboard(history_by_id: dict, headlines: list) -> dict:
    """Latest vs prior prints + official-source headlines only."""
    series = []
    for sid, label, _names in USA_MACRO_SERIES:
        hist = list(history_by_id.get(sid) or [])
        hist = [h for h in hist if h.get("value") is not None]
        hist = hist[-12:]
        latest = hist[-1]["value"] if hist else None
        prior = hist[-2]["value"] if len(hist) >= 2 else None
        series.append({
            "id": sid,
            "label": label,
            "latest": latest,
            "prior": prior,
            "date": hist[-1].get("date") if hist else None,
            "history": hist,
            "data_available": latest is not None,
        })
    official = [
        h for h in (headlines or [])
        if (h.get("source_id") or "") in OFFICIAL_SOURCE_IDS
    ]
    official = official[:20]
    return {"series": series, "official_headlines": official}


def _normalize_macro_frame(df: pd.DataFrame) -> list[dict]:
    if df is None or df.empty:
        return []
    work = df.copy()
    work.columns = [str(c).strip() for c in work.columns]
    date_col = next(
        (c for c in work.columns if "日期" in c or "时间" in c or c.lower() == "date"),
        work.columns[0],
    )
    val_col = next(
        (c for c in work.columns if c in ("今值", "value", "值") or "今值" in c),
        None,
    )
    if val_col is None:
        numeric = [c for c in work.columns if c != date_col and pd.api.types.is_numeric_dtype(work[c])]
        val_col = numeric[0] if numeric else None
    if val_col is None:
        return []
    work["date"] = pd.to_datetime(work[date_col], errors="coerce")
    work["value"] = pd.to_numeric(work[val_col], errors="coerce")
    work = work.dropna(subset=["date", "value"]).sort_values("date")
    return [
        {"date": d.strftime("%Y-%m-%d"), "value": float(v)}
        for d, v in zip(work["date"].tail(12), work["value"].tail(12))
    ]


def _fetch_usa_macro_history() -> dict:
    """Best-effort akshare USA macro prints. Missing symbols are skipped."""
    out = {}
    for sid, _label, names in USA_MACRO_SERIES:
        for fn_name in names:
            fn = getattr(ak, fn_name, None)
            if not callable(fn):
                continue
            try:
                df = fn()
                rows = _normalize_macro_frame(df)
                if rows:
                    out[sid] = rows
                    break
            except Exception as e:
                log.debug("akshare %s failed: %s", fn_name, e)
    return out


def _analyze_all_factors(signals: dict) -> dict:
    market = _analyze_market_factors()
    history = _fetch_usa_macro_history()
    headlines = list(signals.get("finance_news") or [])
    macro = _build_macro_dashboard(history, headlines)
    return {
        "macro": macro,
        "oil": market.get("oil") or _empty_series_result("WTI原油"),
        "dollar": market.get("dollar") or _empty_series_result("美元指数"),
        "rates": market.get("rates") or _empty_series_result("美债10Y"),
        "crypto": market.get("crypto") or _empty_series_result("比特币"),
    }


# ---------------------------------------------------------------------------
# Step 5: Industry-adaptive upside assessment
# ---------------------------------------------------------------------------


def _upside_assessment(symbol: str) -> dict:
    """
    Evaluate whether a stock still has upside or is overheated.
    Uses percentile-based scoring relative to own history — NOT fixed thresholds.
    An AI stock up 50% in 60d may be normal; a bank stock up 25% may be extreme.
    """
    from technical_analysis import compute_indicators, load_ohlcv

    result = {
        "symbol": symbol,
        "upside_score": 50,
        "dimensions": {},
        "conclusion": "数据不足",
    }

    df = load_ohlcv(symbol)
    if df is None or len(df) < 60:
        return result

    df = compute_indicators(df)
    latest_close = df["close"].iloc[-1]

    # Dimension 1: Price position — percentile of 60d return vs own 3yr history
    dim_price = {"name": "涨幅分位", "score": 50, "detail": ""}
    if len(df) >= 60:
        current_60d_return = (latest_close - df["close"].iloc[-60]) / df["close"].iloc[-60] * 100
        rolling_60d_returns = df["close"].pct_change(60).dropna() * 100
        if len(rolling_60d_returns) > 20:
            rank = (rolling_60d_returns < current_60d_return).sum() / len(rolling_60d_returns) * 100
            dim_price["percentile"] = round(rank, 1)
            dim_price["current_60d_return"] = round(current_60d_return, 1)
            if rank > 85:
                dim_price["score"] = max(10, 100 - rank)
                dim_price["detail"] = f"60天涨幅处于历史{rank:.0f}%分位 (极端)"
            elif rank > 70:
                dim_price["score"] = max(30, 90 - rank * 0.5)
                dim_price["detail"] = f"60天涨幅处于历史{rank:.0f}%分位 (偏高)"
            else:
                dim_price["score"] = min(90, 70 + (70 - rank) * 0.3)
                dim_price["detail"] = f"60天涨幅处于历史{rank:.0f}%分位 (正常)"
    result["dimensions"]["price_position"] = dim_price

    # Dimension 2: 52-week position
    year_data = df.tail(min(252, len(df)))
    high_52w = year_data["high"].max() if "high" in df.columns else year_data["close"].max()
    low_52w = year_data["low"].min() if "low" in df.columns else year_data["close"].min()
    dim_52w = {"name": "52周位置", "score": 50, "detail": ""}
    if high_52w > low_52w:
        pos = (latest_close - low_52w) / (high_52w - low_52w) * 100
        dim_52w["position_pct"] = round(pos, 1)
        if pos > 90:
            dim_52w["score"] = 15
            dim_52w["detail"] = f"接近52周新高 ({pos:.0f}%位置)"
        elif pos > 70:
            dim_52w["score"] = 50
            dim_52w["detail"] = f"52周偏高位 ({pos:.0f}%位置)"
        elif pos < 30:
            dim_52w["score"] = 90
            dim_52w["detail"] = f"52周底部区域 ({pos:.0f}%位置)"
        else:
            dim_52w["score"] = 70
            dim_52w["detail"] = f"52周中间位置 ({pos:.0f}%位置)"
    result["dimensions"]["week_52_position"] = dim_52w

    # Dimension 3: Technical overbought (RSI — cross-industry universal)
    dim_tech = {"name": "技术超买", "score": 60, "detail": ""}
    if "RSI" in df.columns:
        rsi = df["RSI"].iloc[-1]
        if pd.notna(rsi):
            dim_tech["rsi"] = round(float(rsi), 1)
            if rsi > 80:
                dim_tech["score"] = 10
                dim_tech["detail"] = f"RSI={rsi:.0f} 严重超买"
            elif rsi > 70:
                dim_tech["score"] = 30
                dim_tech["detail"] = f"RSI={rsi:.0f} 超买"
            elif rsi < 30:
                dim_tech["score"] = 95
                dim_tech["detail"] = f"RSI={rsi:.0f} 超卖 (可能是机会)"
            else:
                dim_tech["score"] = 70
                dim_tech["detail"] = f"RSI={rsi:.0f} 正常"

    if "MACD_hist" in df.columns and len(df) >= 5:
        hist = df["MACD_hist"].iloc[-5:]
        if hist.iloc[-1] < hist.iloc[-3] and df["close"].iloc[-1] > df["close"].iloc[-3]:
            dim_tech["macd_divergence"] = True
            dim_tech["score"] = max(10, dim_tech["score"] - 20)
            dim_tech["detail"] += " + MACD顶背离"
    result["dimensions"]["technical"] = dim_tech

    # Dimension 4: Trend health (volume confirmation)
    dim_trend = {"name": "趋势健康", "score": 60, "detail": ""}
    if "volume" in df.columns and len(df) >= 20:
        vol_recent = df["volume"].iloc[-5:].mean()
        vol_avg = df["volume"].iloc[-60:-5].mean() if len(df) >= 65 else df["volume"].iloc[:-5].mean()
        if vol_avg > 0:
            vol_ratio = vol_recent / vol_avg
            dim_trend["volume_ratio"] = round(vol_ratio, 2)
            close_trend = df["close"].iloc[-1] > df["close"].iloc[-5]
            if close_trend and vol_ratio > 1.2:
                dim_trend["score"] = 80
                dim_trend["detail"] = "放量上涨 (趋势健康)"
            elif close_trend and vol_ratio < 0.7:
                dim_trend["score"] = 40
                dim_trend["detail"] = "缩量上涨 (动能衰竭风险)"
            elif not close_trend and vol_ratio > 2.0:
                dim_trend["score"] = 25
                dim_trend["detail"] = "放量下跌 (可能恐慌)"
            else:
                dim_trend["score"] = 60
                dim_trend["detail"] = "成交量正常"
    result["dimensions"]["trend_health"] = dim_trend

    # Dimension 5: Fund flow
    dim_ff = {"name": "资金方向", "score": 50, "detail": ""}
    try:
        import china_market_data as cmd
        ff = cmd.stock_fund_flow_signals(symbol)
        if ff and ff.get("data_days", 0) >= 3:
            phase = ff.get("smart_money_phase", "无信号")
            main_3d = ff.get("main_net_3d", 0)
            if phase == "布局期":
                dim_ff["score"] = 85
                dim_ff["detail"] = f"聪明钱布局期 (3日净流入{main_3d/1e8:.1f}亿)"
            elif phase == "拉升期":
                dim_ff["score"] = 45
                dim_ff["detail"] = "已进入拉升期 (追高风险)"
            elif phase == "出货期":
                dim_ff["score"] = 15
                dim_ff["detail"] = "疑似出货 (主力撤退)"
            elif main_3d > 0:
                dim_ff["score"] = 65
                dim_ff["detail"] = f"资金净流入 ({main_3d/1e8:.1f}亿/3日)"
            else:
                dim_ff["score"] = 35
                dim_ff["detail"] = f"资金净流出 ({main_3d/1e8:.1f}亿/3日)"
    except Exception:
        dim_ff["detail"] = "数据不可用"
    result["dimensions"]["fund_flow"] = dim_ff

    # Composite score (weighted)
    weights = {
        "price_position": 0.25,
        "week_52_position": 0.15,
        "technical": 0.20,
        "trend_health": 0.20,
        "fund_flow": 0.20,
    }
    total = sum(
        result["dimensions"].get(k, {}).get("score", 50) * w
        for k, w in weights.items()
    )
    result["upside_score"] = round(total)

    if result["upside_score"] >= 75:
        result["conclusion"] = "充裕空间 — 趋势初期或底部区域"
    elif result["upside_score"] >= 60:
        result["conclusion"] = "尚有空间 — 可参与但注意节奏"
    elif result["upside_score"] >= 40:
        result["conclusion"] = "空间有限 — 建议等回调"
    else:
        result["conclusion"] = "过热警告 — 不推荐追入"

    return result


# ---------------------------------------------------------------------------
# Step 3: LLM trend analysis — identify investment themes
# ---------------------------------------------------------------------------


def _build_signal_summary(signals: dict, metals: dict, factors: dict | None = None) -> str:
    """Condense 14 days of signals into a prompt-friendly summary."""
    parts = []

    ai = signals.get("ai_tech_news", [])
    if ai:
        parts.append(f"\n【近{SIGNAL_WINDOW_DAYS}天AI/科技新闻 ({len(ai)}条)】")
        for item in ai[:40]:
            parts.append(f"  [{item['date']}] {item['headline']}")

    finance = list(signals.get("finance_news") or [])
    by_cat: dict[str, list] = {cid: [] for cid in FINANCE_CATEGORIES}
    for item in finance:
        cat = item.get("category") or ""
        if cat in by_cat:
            by_cat[cat].append(item)
    for item in signals.get("world_news") or []:
        by_cat["markets"].append({
            "date": item.get("date", ""),
            "headline": item.get("headline", ""),
            "source_id": item.get("source_id") or "legacy-world",
            "category": "markets",
            "source_type": "world",
        })
    for cid in FINANCE_CATEGORIES:
        cat_items = _select_finance_headlines(by_cat[cid], HEADLINES_PER_FINANCE_CAT)
        if not cat_items:
            continue
        label = FINANCE_CAT_LABELS.get(cid, cid)
        parts.append(f"\n【财经新闻-{label} ({len(cat_items)}条)】")
        for item in cat_items:
            parts.append(f"  [{item.get('date','')}] {item.get('headline','')}")

    bs = signals.get("black_swan")
    if bs and bs.get("alerts"):
        parts.append(f"\n【黑天鹅预警 ({len(bs['alerts'])}个)】")
        for alert in bs["alerts"][:5]:
            parts.append(f"  ⚠ {alert.get('label','')}: {alert.get('summary','')}")
            parts.append(f"    受影响行业: {', '.join(alert.get('affected_industries', []))}")

    sectors = signals.get("hot_sectors", [])
    if sectors:
        parts.append(f"\n【A股热门板块 (TOP {min(10, len(sectors))})】")
        for s in sectors[:10]:
            parts.append(f"  {s.get('name','')} ({s.get('change_pct','?')}%) 龙头: {s.get('leader','')}")

    ms = signals.get("market_sentiment")
    if ms:
        fg = ms.get("fear_greed", {})
        vix = ms.get("vix", {})
        mood = ms.get("market_mood", {})
        parts.append("\n【全球情绪】")
        if fg.get("value") is not None:
            parts.append(f"  Fear & Greed: {fg['value']} ({fg.get('label','')})")
        if vix.get("value") is not None:
            parts.append(f"  VIX: {vix['value']} ({vix.get('change_pct','?')}%)")
        if mood.get("recommendation"):
            parts.append(f"  建议: {mood['recommendation']}")

    if metals:
        parts.append("\n【贵金属行情】")
        for key in ("gold", "silver"):
            m = metals.get(key, {})
            if m.get("data_available"):
                parts.append(
                    f"  {m['name']}: ¥{m.get('latest_price','-')} "
                    f"14天{m.get('change_14d_pct',0):+.1f}% "
                    f"60天{m.get('change_60d_pct',0):+.1f}% "
                    f"RSI={m.get('rsi_14','-')} "
                    f"趋势={m.get('trend','-')}"
                )
        if metals.get("gold_silver_ratio"):
            parts.append(f"  金银比: {metals['gold_silver_ratio']} ({metals.get('ratio_signal','')})")

    if factors:
        parts.append("\n【宏观与市场温度计】")
        macro = factors.get("macro") or {}
        for s in macro.get("series") or []:
            if not s.get("data_available"):
                continue
            parts.append(
                f"  {s.get('label')}: 最新{s.get('latest')} (前值{s.get('prior')}) {s.get('date') or ''}"
            )
        for key in ("oil", "dollar", "rates", "crypto"):
            m = factors.get(key) or {}
            if not m.get("data_available"):
                continue
            parts.append(
                f"  {m.get('name', key)}: {m.get('latest_price','-')} "
                f"14天{m.get('change_14d_pct',0):+.1f}% "
                f"60天{m.get('change_60d_pct',0):+.1f}% "
                f"RSI={m.get('rsi_14','-')} 趋势={m.get('trend','-')}"
            )

    return "\n".join(parts)


def _select_finance_headlines(items: list, cap: int) -> list:
    """Keep the newest headlines; official sources win only as a same-day tie-break."""
    def _key(item):
        date = item.get("date") or ""
        official = 1 if (item.get("source_id") or "") in OFFICIAL_SOURCE_IDS else 0
        return (date, official)
    return sorted(items, key=_key, reverse=True)[:cap]


def _theme_system_prompt() -> str:
    rec_stocks_desc = ""
    rec_stocks_format = ""
    if _use_deepseek:
        rec_stocks_desc = "   - recommended_stocks(代表个股推荐列表，每个个股包含: symbol(6位A股股票代码), name(股票名称), logic(在该主题下的核心逻辑与长达半年到1年的趋势预估))\n"
        rec_stocks_format = "    \"recommended_stocks\": [\n       {\"symbol\": \"600519\", \"name\": \"贵州茅台\", \"logic\": \"核心受益逻辑及长达半年到1年的远景预估\"}\n    ]\n"
    return (
        "你是资深A股策略分析师, 擅长从宏观新闻和政策中识别中长期投资机会。\n\n"
        "任务: 基于提供的近2周新闻和市场信号, 识别未来3个月到1年（含半年到1年的长期预估）最可能受益的投资主题。\n\n"
        "要求:\n"
        "1. 输出3-5个投资主题 (不要凑数, 只输出有高置信度支撑的)\n"
        "2. 每个主题包含:\n"
        "   - name(主题名称)\n"
        "   - logic(受益逻辑)\n"
        "   - industries(相关A股行业/板块列表，如['有色金属', '半导体'])\n"
        "   - catalysts(催化剂事件/时间点)\n"
        "   - time_horizon(长期维度，建议在 '3个月'、'6个月'、'1年' 中选择)\n"
        "   - risk(风险因素)\n"
        "   - confidence(高/中高/中)\n"
        f"{rec_stocks_desc}"
        "3. 同时考虑国际局势和国内政策两条线对A股的传导\n"
        "4. 必须使用：中国政策、美国宏观/政治、石油、美元、利率、加密、黄金新闻，以及官方宏观与温度计块结论\n"
        "5. 禁止只凭科技简报出主题；不要只根据AI/科技新闻下结论\n"
        "6. a_share_implication 是A股映射线索，不是美股或BTC推荐\n"
        "7. 关注: 政策利好, 技术突破, 行业拐点, 供需变化, 地缘事件传导\n\n"
        "只输出JSON数组, 不要输出其他文字。格式示例:\n"
        "[\n"
        "  {\n"
        "    \"name\": \"主题名\",\n"
        "    \"logic\": \"受益逻辑说明\",\n"
        "    \"industries\": [\"半导体\"],\n"
        "    \"catalysts\": [\"事件A\"],\n"
        "    \"time_horizon\": \"6个月\",\n"
        "    \"risk\": \"风险因素说明\",\n"
        "    \"confidence\": \"高\",\n"
        f"{rec_stocks_format}"
        "  }\n"
        "]"
    )


def _llm_theme_analysis(signal_summary: str) -> list[dict]:
    """
    Ask LLM to identify 3-5 investment themes from the signal summary.
    Returns list of themes with industries and stock suggestions.
    """
    log.info("Step 3: LLM 趋势研判...")
    system_prompt = _theme_system_prompt()
    user_prompt = f"以下是近{SIGNAL_WINDOW_DAYS}天的市场信号汇总:\n\n{signal_summary}\n\n请识别投资主题, 只输出JSON数组:"
    return _call_llm_json(system_prompt, user_prompt, max_tokens=4000)


def _call_llm_json(system_prompt: str, user_prompt: str, max_tokens: int = 1500) -> list | dict:
    """Call LLM (DeepSeek preferred, Ollama fallback) and parse JSON response."""
    if _use_deepseek:
        try:
            from config import call_deepseek, get_deepseek_key
            if get_deepseek_key():
                result = call_deepseek(system_prompt, user_prompt, max_tokens=max_tokens)
                if result["ok"]:
                    return _parse_json_response(result["content"])
                log.warning("DeepSeek 失败: %s, 降级到本地LLM", result.get("error"))
        except Exception as e:
            log.warning("DeepSeek 异常: %s, 降级到本地LLM", e)

    model = MODEL_USAGE.get("prediction_reasoning", "qwen3.5:4b")
    try:
        resp = requests.post(
            f"{OLLAMA_HOST}/api/chat",
            json={
                "model": model,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                "stream": False,
                "think": False,
                "options": {"temperature": 0.4, "num_predict": max_tokens},
            },
            timeout=180,
        )
        resp.raise_for_status()
        raw = resp.json().get("message", {}).get("content", "")
        return _parse_json_response(raw)
    except Exception as e:
        log.error("LLM 调用失败: %s", e)
        return []


def _parse_json_response(raw: str) -> list | dict:
    """Extract JSON from LLM response (handles markdown fences, think tags)."""
    text = raw.strip()
    _ot = "<" + "think" + ">"
    _ct = "</" + "think" + ">"
    if _ot in text:
        text = text.split(_ct, 1)[-1].strip()
    text = re.sub(_ot + r"[\s\S]*?" + _ct, "", text, flags=re.DOTALL).strip()

    m = re.search(r"```(?:json)?\s*([\[\{].*?[\]\}])\s*```", text, re.DOTALL)
    if m:
        text = m.group(1)

    for start_char, end_char in [("[", "]"), ("{", "}")]:
        s = text.find(start_char)
        e = text.rfind(end_char)
        if s >= 0 and e > s:
            try:
                return json.loads(text[s:e + 1])
            except json.JSONDecodeError:
                continue

    for start_char, end_char in [("[", "]"), ("{", "}")]:
        s = text.find(start_char)
        if s >= 0:
            fragment = text[s:]
            for repair_suffix in [end_char, '"}' + end_char, '"]' + end_char, '"}}' + end_char]:
                try:
                    return json.loads(fragment + repair_suffix)
                except json.JSONDecodeError:
                    continue

    log.warning("JSON 解析失败 (含修复尝试), raw=%s", text[:300])
    return []


# ---------------------------------------------------------------------------
# Step 4: Map themes to candidate stocks
# ---------------------------------------------------------------------------


def _map_themes_to_candidates(themes: list[dict]) -> list[dict]:
    """Map investment themes to specific A-share stock candidates."""
    log.info("Step 4: 投资主题 → 候选个股...")
    candidates = []
    seen_symbols = set()

    def clean_symbol(sym) -> str:
        if not sym:
            return ""
        digits = "".join(filter(str.isdigit, str(sym)))
        if len(digits) == 6:
            return digits
        return ""

    hot_sectors = []
    try:
        from hot_sectors import fetch_hot_sectors
        hot_sectors = fetch_hot_sectors() or []
    except Exception:
        pass

    sector_stocks = {}
    for s in hot_sectors:
        name = s.get("name", "")
        stocks = s.get("stocks", [])
        leader_sym = s.get("leader_symbol", "")
        sector_stocks[name] = {
            "stocks": stocks,
            "leader": leader_sym,
            "leader_name": s.get("leader", ""),
        }

    for theme in themes:
        industries = theme.get("industries", [])
        theme_name = theme.get("name", "unknown")
        matched = []

        # 1. 优先加载 LLM 在主题下直接推荐的个股 (尤其在 DeepSeek 启用时质量极高)
        rec_stocks = theme.get("recommended_stocks", [])
        if isinstance(rec_stocks, list):
            for s in rec_stocks:
                if not isinstance(s, dict):
                    continue
                sym = clean_symbol(s.get("symbol"))
                if sym and sym not in seen_symbols:
                    matched.append({
                        "symbol": sym,
                        "name": s.get("name", ""),
                        "match_reason": f"主题 [{theme_name}] 直推个股",
                    })
                    seen_symbols.add(sym)

        # 2. 板块龙头/成分股映射作为补充
        for ind in industries:
            for sec_name, sec_data in sector_stocks.items():
                if ind in sec_name or sec_name in ind:
                    if sec_data["leader"] and sec_data["leader"] not in seen_symbols:
                        matched.append({
                            "symbol": sec_data["leader"],
                            "name": sec_data["leader_name"],
                            "match_reason": f"板块 [{sec_name}] 龙头",
                        })
                        seen_symbols.add(sec_data["leader"])
                    for sym in sec_data["stocks"][:3]:
                        if sym not in seen_symbols:
                            matched.append({
                                "symbol": sym,
                                "name": "",
                                "match_reason": f"板块 [{sec_name}] 成分股",
                            })
                            seen_symbols.add(sym)

        for stock in matched[:8]:
            stock["theme"] = theme_name
            stock["theme_logic"] = theme.get("logic", "")
            stock["time_horizon"] = theme.get("time_horizon", "")
            stock["catalysts"] = theme.get("catalysts", [])
            stock["theme_risk"] = theme.get("risk", "")
            stock["theme_confidence"] = theme.get("confidence", "中")
        candidates.extend(matched[:8])

    log.info("  共 %d 只候选股 (来自 %d 个主题)", len(candidates), len(themes))
    return candidates


def _filter_candidates(candidates: list[dict]) -> list[dict]:
    """Apply fundamental floor check to candidates."""
    log.info("Step 4b: 基本面底线过滤...")
    filtered = []

    try:
        df = ak.stock_zh_a_spot_em()
    except Exception:
        log.warning("无法获取市场行情, 跳过基本面过滤")
        return candidates

    if df is None or df.empty:
        return candidates

    market_data = {}
    for _, row in df.iterrows():
        market_data[str(row.get("代码", ""))] = row

    for c in candidates:
        sym = c["symbol"]
        row = market_data.get(sym)
        if row is None:
            continue

        name = str(row.get("名称", ""))
        if "ST" in name:
            continue

        pe = row.get("市盈率-动态")
        try:
            pe_f = float(pe)
            if pe_f <= 0 or pe_f > 200:
                continue
        except (TypeError, ValueError):
            pass

        mkt_cap = row.get("总市值")
        try:
            if float(mkt_cap) < 3e9:
                continue
        except (TypeError, ValueError):
            pass

        if not c["name"]:
            c["name"] = name
        c["price"] = float(row.get("最新价", 0) or 0)
        c["pe"] = float(pe) if pe else None
        c["market_cap"] = float(mkt_cap) if mkt_cap else None
        c["change_pct"] = float(row.get("涨跌幅", 0) or 0)
        filtered.append(c)

    log.info("  过滤后 %d 只候选 (排除 ST/亏损/市值过小)", len(filtered))
    return filtered


# ---------------------------------------------------------------------------
# Step 6: LLM final selection
# ---------------------------------------------------------------------------


def _llm_final_selection(
    candidates: list[dict],
    _themes: list[dict],
    _metals: dict,
    _signal_summary: str,
) -> list[dict]:
    """LLM picks final ≤5 stocks with reasoning from upside-assessed candidates."""
    log.info("Step 6: LLM 精选推荐...")

    if not candidates:
        return []

    candidate_text = []
    for c in candidates[:20]:
        upside = c.get("upside", {})
        dims = upside.get("dimensions", {})
        dim_strs = []
        for k, d in dims.items():
            dim_strs.append(f"{d.get('name','')}: {d.get('score',50)}/100 ({d.get('detail','')})")

        candidate_text.append(
            f"- {c.get('name','')} ({c['symbol']}) ¥{c.get('price','-')} PE={c.get('pe','-')}\n"
            f"  主题: {c.get('theme','')}\n"
            f"  匹配: {c.get('match_reason','')}\n"
            f"  空间评分: {upside.get('upside_score', '?')}/100 ({upside.get('conclusion','')})\n"
            f"  维度: {'; '.join(dim_strs)}"
        )

    system_prompt = (
        "你是资深A股中长期投资策略师。从候选股票中精选最多5只作为未来3个月到1年（支持长达半年到1年的趋势预估与投资决策）的长期精选推荐。\n\n"
        "选股标准:\n"
        "1. 空间评分 ≥ 60 (必须有上涨空间, 过热的不选。若主题直推股的基本面极佳且趋势健康，可放宽至 55分)\n"
        "2. 投资主题逻辑清晰且催化剂明确\n"
        "3. 基本面有底线支撑，中长期具有明确增长、复苏或行业拐点预期\n"
        "4. 宁缺毋滥 — 没有好选择时推荐0只\n\n"
        "对每只推荐的股票输出:\n"
        "symbol, name, theme, reason(推荐理由3-5条，包含对半年到1年长期成长潜力/盈利预估的详细论证), time_horizon(建议持有周期，如 '6个月' 或 '1年'), "
        "catalysts(催化剂列表), risk(主要风险), confidence(高/中高/中), "
        "watch_price(建议关注/建仓价位)\n\n"
        "只输出JSON数组。"
    )

    user_prompt = (
        "宏观温度计与新闻摘要:\n"
        + (_signal_summary or "")[:1500]
        + "\n\n候选股票列表:\n\n" + "\n\n".join(candidate_text)
        + f"\n\n请从中精选最多{MAX_PICKS}只长期推荐, 只输出JSON数组:"
    )

    picks_raw = _call_llm_json(system_prompt, user_prompt, max_tokens=4000)
    if isinstance(picks_raw, list):
        picks = []
        for p in picks_raw[:MAX_PICKS]:
            sym = p.get("symbol", "")
            match = next((c for c in candidates if c["symbol"] == sym), None)
            if match:
                match.update({
                    "recommendation_reason": p.get("reason", ""),
                    "recommendation_risk": p.get("risk", ""),
                    "recommendation_confidence": p.get("confidence", "中"),
                    "watch_price": p.get("watch_price", ""),
                    "time_horizon": p.get("time_horizon", match.get("time_horizon", "")),
                    "catalysts": p.get("catalysts", match.get("catalysts", [])),
                })
                picks.append(match)
            else:
                log.warning("LLM 推荐了未知股票 %s, 跳过 (不在候选列表中)", sym)
        return picks
    return []


# ---------------------------------------------------------------------------
# Step 2b: LLM precious metals outlook
# ---------------------------------------------------------------------------


def _llm_metals_outlook(metals: dict, signal_summary: str) -> dict:
    """LLM analysis of gold/silver outlook based on data + news context."""
    log.info("Step 2b: LLM 贵金属研判...")

    data_text = []
    for key, label in [("gold", "黄金"), ("silver", "白银")]:
        m = metals.get(key, {})
        if m.get("data_available"):
            data_text.append(
                f"{label}: 最新价¥{m.get('latest_price','-')} | "
                f"14天{m.get('change_14d_pct',0):+.1f}% | "
                f"60天{m.get('change_60d_pct',0):+.1f}% | "
                f"RSI={m.get('rsi_14','-')} | "
                f"MA20偏离{m.get('ma20_deviation_pct',0):+.1f}% | "
                f"52周位置{m.get('position_vs_52w','-')}% | "
                f"60天涨幅分位{m.get('percentile_60d','-')}% | "
                f"空间评分{m.get('upside_score','-')}/100 | "
                f"趋势={m.get('trend','-')}"
            )
    if metals.get("gold_silver_ratio"):
        data_text.append(f"金银比: {metals['gold_silver_ratio']} ({metals.get('ratio_signal','')})")

    system_prompt = (
        "你是贵金属市场资深分析师。请基于价格数据和近期新闻, 给出黄金和白银的中期展望。\n\n"
        "分析要求:\n"
        "1. 黄金/白银各自: 趋势判断(看涨/看跌/震荡), 核心驱动因素, 是否过热, 操作建议\n"
        "2. 结合国际新闻判断驱动力是否可持续 (美联储政策/地缘/美元/通胀/央行购金等)\n"
        "3. 用空间评分和技术指标判断是否已经过热或还有上涨空间\n"
        "4. 给出具体建议价位区间\n\n"
        "输出JSON: {gold: {trend, drivers, overheated, advice, price_range}, "
        "silver: {trend, drivers, overheated, advice, price_range}, summary}"
    )

    user_prompt = (
        "贵金属数据:\n" + "\n".join(data_text) +
        f"\n\n近期相关新闻信号:\n{signal_summary[:3000]}\n\n"
        "请分析并输出JSON:"
    )

    result = _call_llm_json(system_prompt, user_prompt, max_tokens=4000)
    if isinstance(result, dict):
        metals["llm_outlook"] = result
    else:
        metals["llm_outlook"] = {"error": "LLM分析失败"}

    return metals


def _parse_thermometer_outlook(raw) -> dict:
    required = ("macro", "oil", "dollar", "rates", "crypto")
    if not isinstance(raw, dict):
        return {"error": "LLM分析失败"}
    if not all(k in raw for k in required):
        return {"error": "LLM分析失败"}
    out = {k: raw.get(k) or {} for k in required}
    if raw.get("summary"):
        out["summary"] = raw["summary"]
    return out


def _llm_thermometer_outlook(factors: dict, signal_summary: str) -> dict:
    log.info("Step 2c: LLM 宏观温度计研判...")
    system_prompt = (
        "你是宏观与大类资产策略分析师。基于结构化数据和近期新闻, "
        "分别给出官方宏观、油价、美元、美债利率、加密货币的中期展望。\n\n"
        "每个块: trend(看涨/看跌/震荡/中性), drivers, overheated, advice, "
        "a_share_implication(对A股主题的映射线索，不要推荐美股或BTC本身)。\n"
        "只输出JSON: {macro, oil, dollar, rates, crypto, summary}"
    )
    payload = {k: factors.get(k) for k in ("macro", "oil", "dollar", "rates", "crypto")}
    user_prompt = (
        f"温度计数据:\n{json.dumps(payload, ensure_ascii=False, default=str)[:4000]}\n\n"
        f"近期信号:\n{signal_summary[:4000]}\n\n请分析并输出JSON:"
    )
    result = _call_llm_json(system_prompt, user_prompt, max_tokens=4000)
    factors["llm_outlook"] = _parse_thermometer_outlook(result)
    return factors


# ---------------------------------------------------------------------------
# Report generation
# ---------------------------------------------------------------------------


def _generate_report(
    picks: list[dict],
    metals: dict,
    themes: list[dict],
    scan_meta: dict,
    factors: dict | None = None,
) -> str:
    """Generate Markdown report for RAG indexing and human review."""
    date_str = datetime.now().strftime("%Y-%m-%d")
    lines = [
        f"# AI股票推荐报告(长期) — {date_str}",
        "",
        f"**分析时间**: {scan_meta.get('started_at', 'N/A')}",
        f"**信号窗口**: 近{SIGNAL_WINDOW_DAYS}天",
        f"**财经新闻**: {scan_meta.get('finance_news_count', 0)} 条",
        f"**AI/科技新闻**: {scan_meta.get('ai_news_count', 0)} 条",
        f"**投资主题**: {len(themes)} 个",
        f"**推荐个股**: {len(picks)} 只",
        "",
        "---",
        "",
    ]

    # Part 1: Precious metals (mandatory)
    lines.extend([
        "## 一、贵金属分析",
        "",
    ])
    for key, label in [("gold", "黄金"), ("silver", "白银")]:
        m = metals.get(key, {})
        if m.get("data_available"):
            lines.extend([
                f"### {label}",
                "",
                f"- **最新价**: ¥{m.get('latest_price', '-')}",
                f"- **14天涨跌**: {m.get('change_14d_pct', 0):+.1f}%",
                f"- **60天涨跌**: {m.get('change_60d_pct', 0):+.1f}%",
                f"- **RSI(14)**: {m.get('rsi_14', '-')}",
                f"- **52周位置**: {m.get('position_vs_52w', '-')}%",
                f"- **趋势**: {m.get('trend', '-')}",
                f"- **空间评分**: {m.get('upside_score', '-')}/100",
                "",
            ])

    outlook = metals.get("llm_outlook", {})
    if isinstance(outlook, dict) and not outlook.get("error"):
        for key, label in [("gold", "黄金"), ("silver", "白银")]:
            o = outlook.get(key, {})
            if o:
                lines.extend([
                    f"**{label}展望**: {o.get('trend', '')}",
                    f"- 驱动因素: {o.get('drivers', '')}",
                    f"- 是否过热: {o.get('overheated', '')}",
                    f"- 操作建议: {o.get('advice', '')}",
                    f"- 建议区间: {o.get('price_range', '')}",
                    "",
                ])
        if outlook.get("summary"):
            lines.extend([f"**综合判断**: {outlook['summary']}", ""])

    if metals.get("gold_silver_ratio"):
        lines.append(f"**金银比**: {metals['gold_silver_ratio']} ({metals.get('ratio_signal', '')})")
        lines.append("")

    lines.extend(["---", ""])

    factors = factors or {}
    lines.extend(["## 二、宏观与市场温度计", ""])
    macro = factors.get("macro") or {}
    series_rows = [s for s in (macro.get("series") or []) if s.get("data_available")]
    headlines = macro.get("official_headlines") or []
    if series_rows or headlines:
        lines.extend(["### 官方宏观", ""])
        for s in series_rows:
            lines.append(
                f"- **{s.get('label')}**: {s.get('latest')} (前值 {s.get('prior')}) {s.get('date') or ''}"
            )
        for h in headlines[:8]:
            lines.append(f"- {h.get('headline', '')}")
        lines.append("")
        outlook = (factors.get("llm_outlook") or {}).get("macro") or {}
        if outlook:
            lines.extend([
                f"**宏观展望**: {outlook.get('trend', '')}",
                f"- 驱动: {outlook.get('drivers', '')}",
                f"- 建议: {outlook.get('advice', '')}",
                f"- A股映射: {outlook.get('a_share_implication', '')}",
                "",
            ])
    _FACTOR_HEADINGS = (
        ("oil", "油价"),
        ("dollar", "美元"),
        ("rates", "美债利率"),
        ("crypto", "加密货币"),
    )
    any_series = False
    for key, heading in _FACTOR_HEADINGS:
        m = factors.get(key) or {}
        if not m.get("data_available"):
            continue
        any_series = True
        lines.extend([
            f"### {heading}",
            "",
            f"- **最新**: {m.get('latest_price', '-')}",
            f"- **14天涨跌**: {m.get('change_14d_pct', 0):+.1f}%",
            f"- **60天涨跌**: {m.get('change_60d_pct', 0):+.1f}%",
            f"- **RSI(14)**: {m.get('rsi_14', '-')}",
            f"- **52周位置**: {m.get('position_vs_52w', '-')}%",
            f"- **趋势**: {m.get('trend', '-')}",
            "",
        ])
        o = ((factors.get("llm_outlook") or {}).get(key) or {})
        if o:
            lines.extend([
                f"**展望**: {o.get('trend', '')}",
                f"- 驱动: {o.get('drivers', '')}",
                f"- 建议: {o.get('advice', '')}",
                f"- A股映射: {o.get('a_share_implication', '')}",
                "",
            ])
    if not series_rows and not headlines and not any_series:
        lines.append("暂无数据（源缺失，已跳过）")
        lines.append("")
    summary = (factors.get("llm_outlook") or {}).get("summary")
    if summary:
        lines.extend([f"**综合判断**: {summary}", ""])
    lines.extend(["---", ""])

    # Part 3: Investment themes
    lines.extend(["## 三、投资主题", ""])
    for i, t in enumerate(themes, 1):
        lines.extend([
            f"### 主题 {i}: {t.get('name', '')}",
            "",
            f"- **受益逻辑**: {t.get('logic', '')}",
            f"- **相关行业**: {', '.join(t.get('industries', []))}",
            f"- **催化剂**: {', '.join(t.get('catalysts', [])) if isinstance(t.get('catalysts'), list) else t.get('catalysts', '')}",
            f"- **时间框架**: {t.get('time_horizon', '')}",
            f"- **风险**: {t.get('risk', '')}",
            f"- **置信度**: {t.get('confidence', '')}",
        ])
        rec_stocks = t.get("recommended_stocks", [])
        if rec_stocks and isinstance(rec_stocks, list):
            lines.append("- **推荐代表个股及预估 (半年到1年)**:")
            for s in rec_stocks:
                if isinstance(s, dict):
                    lines.append(f"  - **{s.get('name', '')} ({s.get('symbol', '')})**: {s.get('logic', '')}")
        lines.append("")

    lines.extend(["---", ""])

    # Part 3: Stock recommendations
    if not picks:
        lines.extend([
            "## 四、长期推荐: 暂无",
            "",
            "本次分析未找到同时满足趋势+空间+基本面要求的标的。",
            "\"不推荐\"本身就是最好的建议。",
            "",
        ])
    else:
        lines.extend([f"## 四、长期推荐 ({len(picks)} 只)", ""])
        for i, p in enumerate(picks, 1):
            upside = p.get("upside", {})
            lines.extend([
                f"### {i}. {p.get('name', '')} ({p.get('symbol', '')})",
                "",
                f"- **当前价**: ¥{p.get('price', '-')}",
                f"- **投资主题**: {p.get('theme', '')}",
                f"- **时间框架**: {p.get('time_horizon', '')}",
                f"- **空间评分**: {upside.get('upside_score', '-')}/100 ({upside.get('conclusion', '')})",
                f"- **推荐理由**: {p.get('recommendation_reason', '')}",
                f"- **催化剂**: {', '.join(p.get('catalysts', [])) if isinstance(p.get('catalysts'), list) else p.get('catalysts', '')}",
                f"- **风险**: {p.get('recommendation_risk', '')}",
                f"- **建议关注价位**: {p.get('watch_price', '')}",
                f"- **置信度**: {p.get('recommendation_confidence', '')}",
                "",
            ])

            dims = upside.get("dimensions", {})
            if dims:
                lines.append("  **空间评估明细**:")
                for _dk, dv in dims.items():
                    icon = "✅" if dv.get("score", 0) >= 60 else "⚠️"
                    lines.append(f"  {icon} {dv.get('name','')}: {dv.get('score','-')}/100 — {dv.get('detail','')}")
                lines.append("")

    lines.extend([
        "---",
        "",
        f"*本报告由Jarvis AI长期趋势分析系统自动生成于 {datetime.now():%Y-%m-%d %H:%M}*",
        "*免责声明: 以上分析仅供参考, 不构成投资建议。投资有风险, 入市需谨慎。*",
    ])
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Save results + RAG indexing
# ---------------------------------------------------------------------------


def _index_report_to_rag(report_path: str, date_str: str, item_type: str, title: str):
    """Index the Markdown report into RAG store for search/retrieval."""
    try:
        _base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        rag_dir = os.path.join(_base, "rag")
        if _base not in sys.path:
            sys.path.insert(0, _base)
        if rag_dir not in sys.path:
            sys.path.insert(0, rag_dir)
        from index_briefing import _get_model, _get_client, _save_snapshot, _chunk_text, COLLECTION
        from qdrant_client.models import PointStruct

        with open(report_path, encoding="utf-8") as f:
            content = f.read()

        model = _get_model()
        client = _get_client()

        chunks = _chunk_text(content, max_chars=800)
        points = []
        for i, chunk in enumerate(chunks):
            embedding = model.encode(chunk).tolist()
            points.append(PointStruct(
                id=str(_uuid.uuid4()),
                vector=embedding,
                payload={
                    "text": chunk,
                    "title": f"{title} (part {i+1})" if len(chunks) > 1 else title,
                    "parent_title": "Stock Recommendations",
                    "date": date_str,
                    "source": "Jarvis Stock Scanner",
                    "item_type": item_type,
                    "filename": os.path.basename(report_path),
                },
            ))

        if points:
            client.upsert(collection_name=COLLECTION, points=points)
            _save_snapshot(client)
            log.info("RAG 索引完成: %s (%d chunks)", title, len(points))
    except Exception as e:
        log.warning("RAG 索引失败: %s", e)


def _save_results(
    picks: list[dict],
    metals: dict,
    themes: list[dict],
    scan_meta: dict,
    factors: dict | None = None,
):
    """Persist results and generate report."""
    _ensure_dirs()
    date_str = datetime.now().strftime("%Y-%m-%d")
    factors = factors or {}

    result_path = os.path.join(LONG_TERM_DIR, f"{date_str}.json")
    result_data = {
        "date": date_str,
        "meta": scan_meta,
        "precious_metals": metals,
        "factors": factors,
        "themes": themes,
        "picks": picks,
    }
    with open(result_path, "w", encoding="utf-8") as f:
        json.dump(result_data, f, ensure_ascii=False, indent=2, default=str)
    log.info("长期推荐结果已保存 → %s", result_path)

    report = _generate_report(picks, metals, themes, scan_meta, factors=factors)
    report_path = os.path.join(LONG_TERM_DIR, f"{date_str}-report.md")
    with open(report_path, "w", encoding="utf-8") as f:
        f.write(report)
    log.info("长期推荐报告已保存 → %s", report_path)

    _save_lt_history(picks, metals, factors)
    _index_report_to_rag(
        report_path, date_str, "stock_scan_long", f"AI长期推荐 {date_str}"
    )


def _save_lt_history(picks: list[dict], metals: dict, factors: dict | None = None):
    """Save lightweight entry for performance tracking."""
    history_file = os.path.join(LONG_TERM_DIR, "history.json")
    history = []
    if os.path.isfile(history_file):
        try:
            with open(history_file, encoding="utf-8") as f:
                history = json.load(f)
        except Exception:
            pass

    factors = factors or {}
    entry = {
        "date": datetime.now().strftime("%Y-%m-%d"),
        "picks": [
            {"symbol": p.get("symbol"), "name": p.get("name"),
             "price": p.get("price"), "theme": p.get("theme"),
             "upside_score": p.get("upside", {}).get("upside_score")}
            for p in picks
        ],
        "gold_trend": metals.get("gold", {}).get("trend"),
        "silver_trend": metals.get("silver", {}).get("trend"),
        "gold_price": metals.get("gold", {}).get("latest_price"),
        "silver_price": metals.get("silver", {}).get("latest_price"),
        "oil_trend": (factors.get("oil") or {}).get("trend"),
        "dollar_trend": (factors.get("dollar") or {}).get("trend"),
        "rates_trend": (factors.get("rates") or {}).get("trend"),
        "crypto_trend": (factors.get("crypto") or {}).get("trend"),
    }
    history.append(entry)
    with open(history_file, "w", encoding="utf-8") as f:
        json.dump(history, f, ensure_ascii=False, indent=2)


# ---------------------------------------------------------------------------
# Main orchestration
# ---------------------------------------------------------------------------


def _run_lt_scan():
    """Execute the full long-term scan (runs in background thread)."""
    import traceback as _tb
    try:
        _run_lt_scan_inner()
    except Exception:
        _tb.print_exc()
        try:
            progress = _load_progress()
            progress["status"] = "error"
            progress["error"] = _tb.format_exc()[-500:]
            _save_progress(progress)
        except Exception:
            pass


def _run_lt_scan_inner():
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
        "hot_sectors", "technical_analysis", "fundamental_analysis",
        "fetch_market_data", "china_market_data", "market_sentiment",
        "black_swan_detector",
    ]
    for m in _stale:
        sys.modules.pop(m, None)

    progress = {
        "status": "collecting_signals",
        "started_at": datetime.now().isoformat(),
        "error": None,
        "use_deepseek": _use_deepseek,
    }
    _save_progress(progress)

    # Step 1: Collect signals
    signals = _collect_signals()
    if _stop_event.is_set():
        progress["status"] = "stopped"
        _save_progress(progress)
        return

    progress["status"] = "analyzing_metals"
    progress["world_news_count"] = len(signals.get("world_news", []))
    progress["ai_news_count"] = len(signals.get("ai_tech_news", []))
    progress["finance_news_count"] = len(signals.get("finance_news", []))
    progress["finance_by_category"] = {
        cid: len(signals.get("finance_by_category", {}).get(cid) or [])
        for cid in FINANCE_CATEGORIES
    }
    _save_progress(progress)

    # Step 2: Precious metals analysis
    metals = _analyze_precious_metals()
    if _stop_event.is_set():
        progress["status"] = "stopped"
        _save_progress(progress)
        return

    signal_summary = _build_signal_summary(signals, metals)
    metals = _llm_metals_outlook(metals, signal_summary)
    if _stop_event.is_set():
        progress["status"] = "stopped"
        _save_progress(progress)
        return

    progress["status"] = "analyzing_factors"
    _save_progress(progress)
    factors = {}
    try:
        factors = _analyze_all_factors(signals)
        signal_summary = _build_signal_summary(signals, metals, factors=factors)
        factors = _llm_thermometer_outlook(factors, signal_summary)
        signal_summary = _build_signal_summary(signals, metals, factors=factors)
    except Exception as e:
        log.warning("温度计分析失败, 继续主题研判: %s", e)
        factors = factors or {}

    progress["status"] = "analyzing_themes"
    progress["metals_done"] = True
    _save_progress(progress)

    # Step 3: LLM theme analysis
    themes = _llm_theme_analysis(signal_summary)
    if isinstance(themes, dict):
        for key in ("themes", "投资主题", "data", "results"):
            if isinstance(themes.get(key), list):
                themes = themes[key]
                break
        else:
            log.warning("LLM 返回 dict 但无法提取 list, 丢弃: %s", list(themes.keys()))
            themes = []
    if not isinstance(themes, list):
        log.warning("LLM 未识别到投资主题, 仅输出贵金属分析")
        themes = []
    if _stop_event.is_set():
        progress["status"] = "stopped"
        _save_progress(progress)
        return

    progress["status"] = "mapping_stocks"
    progress["themes"] = themes
    _save_progress(progress)

    # Step 4: Map themes to stocks + fundamental filter
    candidates = _map_themes_to_candidates(themes)
    candidates = _filter_candidates(candidates)
    if _stop_event.is_set():
        progress["status"] = "stopped"
        _save_progress(progress)
        return

    # Step 5: Upside assessment for each candidate
    progress["status"] = "assessing_upside"
    progress["candidate_count"] = len(candidates)
    _save_progress(progress)

    for i, c in enumerate(candidates):
        if _stop_event.is_set():
            break
        c["upside"] = _upside_assessment(c["symbol"])
        progress["assessed_count"] = i + 1
        _save_progress(progress)

    scored = [c for c in candidates if c.get("upside", {}).get("upside_score", 0) > 0]
    scored.sort(key=lambda c: c["upside"]["upside_score"], reverse=True)
    min_viable = max(5, len(scored) // 2)
    viable = scored[:min_viable] if scored else []
    log.info("Step 5: %d/%d 候选通过空间评估 (取 top %d)", len(viable), len(candidates), min_viable)

    if _stop_event.is_set():
        progress["status"] = "stopped"
        _save_progress(progress)
        return

    # Step 6: LLM final selection
    progress["status"] = "final_selection"
    _save_progress(progress)

    picks = _llm_final_selection(viable, themes, metals, signal_summary) if viable else []

    # Save
    progress["status"] = "done"
    progress["picks"] = picks
    progress["finished_at"] = datetime.now().isoformat()
    _save_progress(progress)

    scan_meta = {
        "started_at": progress.get("started_at"),
        "finished_at": progress.get("finished_at"),
        "world_news_count": progress.get("world_news_count", 0),
        "ai_news_count": progress.get("ai_news_count", 0),
        "finance_news_count": progress.get("finance_news_count", 0),
        "signal_window_days": SIGNAL_WINDOW_DAYS,
    }
    _save_results(picks, metals, themes, scan_meta, factors=factors)

    log.info("=== AI 长期推荐分析完成 ===")


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def start_lt_scan(use_deepseek: bool = False) -> dict:
    global _lt_thread, _use_deepseek
    with _lt_lock:
        if _lt_thread is not None and _lt_thread.is_alive():
            return {"ok": False, "error": "长期分析正在进行中", "status": get_lt_status()}
        _use_deepseek = use_deepseek
        _stop_event.clear()
        _lt_thread = threading.Thread(target=_run_lt_scan, daemon=True, name="lt-scanner")
        _lt_thread.start()
        return {"ok": True, "message": "长期分析已启动"}


def stop_lt_scan() -> dict:
    _stop_event.set()
    return {"ok": True, "message": "已发送停止信号"}


def get_lt_latest_result() -> dict | None:
    _ensure_dirs()
    files = sorted(
        [f for f in os.listdir(LONG_TERM_DIR)
         if f.endswith(".json") and f not in ("lt_progress.json", "history.json")],
        reverse=True,
    )
    if not files:
        return None
    try:
        with open(os.path.join(LONG_TERM_DIR, files[0]), encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def get_lt_history() -> list[dict]:
    history_file = os.path.join(LONG_TERM_DIR, "history.json")
    if not os.path.isfile(history_file):
        return []
    try:
        with open(history_file, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return []


def get_lt_result_by_date(date_str: str) -> dict | None:
    _ensure_dirs()
    path = os.path.join(LONG_TERM_DIR, f"{date_str}.json")
    if not os.path.isfile(path):
        return None
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def list_lt_scan_dates() -> list[str]:
    _ensure_dirs()
    dates = []
    for f in os.listdir(LONG_TERM_DIR):
        if f.endswith(".json") and f not in ("lt_progress.json", "history.json"):
            dates.append(f.replace(".json", ""))
    dates.sort(reverse=True)
    return dates
