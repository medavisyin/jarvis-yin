# Long-Term Stock Scanner + Scanner Rename — Implementation Plan

> **For the implementing agent:** Follow this plan task-by-task. Complete each step, verify it works, then move to the next. This is a **large, multi-phase feature** — each task is independently testable.

**Goal:** Add a new "AI 股票推荐(长期)" feature alongside the existing scanner (renamed to "短期推荐"), with independent pipeline, UI, API, Telegram support, and RAG indexing for both.

**Architecture:** A new `scripts/stock/long_term_scanner.py` module runs an independent pipeline: collect 14 days of news signals (international + domestic + AI/tech), analyze precious metals (gold/silver), use LLM to identify investment themes, map to A-share stocks, apply industry-adaptive upside assessment, and output ≤5 long-term picks + mandatory precious metals analysis. Results are persisted as JSON + Markdown and indexed into Qdrant RAG for search/retrieval. The existing `scanner.py` is renamed from "AI推荐" to "短期推荐" across all surfaces.

**Tech Stack:** Python (akshare for gold/silver + A-share data, pandas/numpy for analysis), existing LLM infra (DeepSeek optional + Ollama fallback), existing RAG indexing (Qdrant + SentenceTransformers), Flask API, Telegram Bot.

---

## Task 1: Rename existing scanner to "短期推荐"

**Files:**
- Modify: `scripts/stock/scanner.py:1061` — report title
- Modify: `scripts/rag/agent.py:6082` — toolbar button
- Modify: `scripts/rag/agent.py:6546` — modal title
- Modify: `scripts/rag/agent.py:6569-6571` — modal description text
- Modify: `scripts/bot_telegram.py:286` — help text

**Step 1: Update scanner.py report title**

In `scripts/stock/scanner.py`, line 1061, change the report title:

```python
# Before:
f"# AI股票推荐报告 — {date_str}",

# After:
f"# AI股票推荐报告(短期) — {date_str}",
```

**Step 2: Update toolbar button in agent.py**

In `scripts/rag/agent.py`, line 6082, replace the single AI推荐 button with two buttons:

```html
<!-- Before: -->
<button type="button" class="toolbar-btn" onclick="openScannerModal()" title="AI全市场扫描推荐TOP5">&#127775; AI推荐</button>

<!-- After: -->
<button type="button" class="toolbar-btn" onclick="openScannerModal()" title="AI短期买入推荐 (当日行情+技术面+资金流)">&#128293; 短期推荐</button>
<button type="button" class="toolbar-btn" onclick="openLongTermModal()" title="AI长期趋势推荐 (新闻+政策+贵金属分析)">&#128302; 长期推荐</button>
```

**Step 3: Update scanner modal title in agent.py**

In `scripts/rag/agent.py`, line 6546:

```html
<!-- Before: -->
<h2>&#127775; AI 股票推荐</h2>

<!-- After: -->
<h2>&#128293; AI 股票推荐(短期)</h2>
```

**Step 4: Update scanner modal description text**

In `scripts/rag/agent.py`, lines 6569-6571:

```html
<!-- Before: -->
<p style="color:#6b7280">点击"开始扫描"启动AI全市场分析。扫描过程分3层：</p>
<p style="color:#6b7280">1. 全市场快速筛选 → 2. 分批详细分析 → 3. LLM综合评分</p>
<p style="color:#6b7280;font-size:0.9em;margin-top:8px">扫描过程中可以查看部分结果，中断后可继续。</p>

<!-- After: -->
<p style="color:#6b7280">点击"开始扫描"启动AI短期推荐分析（基于当日行情）。扫描过程分3层：</p>
<p style="color:#6b7280">1. 全市场快速筛选 → 2. 分批详细分析 → 3. LLM买入判断</p>
<p style="color:#6b7280;font-size:0.9em;margin-top:8px">扫描过程中可以查看部分结果，中断后可继续。</p>
```

**Step 5: Update Telegram help text**

In `scripts/bot_telegram.py`, line 286:

```python
# Before:
/scan — Run stock scanner"""

# After:
/scan — Run short-term stock scanner
/longscan — Run long-term stock scanner"""
```

**Step 6: Verify**

- Start agent.py, confirm toolbar shows two separate buttons
- Click "短期推荐", confirm modal title says "AI 股票推荐(短期)"
- Confirm the short-term scan still works end-to-end

---

## Task 2: Create `long_term_scanner.py` — signal collection

**Files:**
- Create: `scripts/stock/long_term_scanner.py`

This task builds the core module skeleton + Step 1 (signal collection).

**Step 1: Create module with imports, constants, and signal collection**

Create `scripts/stock/long_term_scanner.py` with the following content:

```python
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
  - International news: BBC, Reuters, AP, DW, Guardian, Chinese media
    (C:/reports/ai/YYYY-MM-DD/world-news/world-news-data.json)
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
import sys
import threading
import time
from datetime import datetime, timedelta

import akshare as ak
import pandas as pd
import numpy as np

from config import (
    STOCK_DATA_DIR,
    STOCK_REPORTS_ROOT,
    STOCK_CACHE_DIR,
    OLLAMA_HOST,
    MODEL_USAGE,
    STOCK_PROXY,
)

log = logging.getLogger(__name__)

LONG_TERM_DIR = os.path.join(STOCK_REPORTS_ROOT, "long_term")
PROGRESS_FILE = os.path.join(LONG_TERM_DIR, "lt_progress.json")
_REPORTS_AI_ROOT = os.environ.get("JARVIS_REPORTS_ROOT", "C:/reports/ai")

SIGNAL_WINDOW_DAYS = 14
MAX_PICKS = 5

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

    log.info("  世界新闻: %d 条, AI/科技新闻: %d 条",
             len(signals["world_news"]), len(signals["ai_tech_news"]))

    try:
        from black_swan_detector import scan_world_news, load_cached_alerts
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

    return signals


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
```

**Step 2: Verify module loads**

```
cd scripts/stock && python -c "import long_term_scanner; print('OK')"
```

Expected: `OK` (no import errors).

---

## Task 3: Precious metals analysis (mandatory)

**Files:**
- Modify: `scripts/stock/long_term_scanner.py` — add precious metals functions

**Step 1: Add gold/silver data fetching and technical analysis**

Append to `long_term_scanner.py`:

```python
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


def _analyze_metal(name: str, fetch_fn, label: str) -> dict:
    """Generic metal analysis: trend, RSI, percentile position, MA deviation."""
    result = {
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

    df = fetch_fn()
    if df is None or len(df) < 30:
        log.warning("  %s 数据不足 (需 >=30 天)", label)
        return result

    result["data_available"] = True
    latest = df["price"].iloc[-1]
    result["latest_price"] = round(float(latest), 2)

    if len(df) >= 14:
        p14 = df["price"].iloc[-14]
        result["change_14d_pct"] = round((latest - p14) / p14 * 100, 2)

    if len(df) >= 60:
        p60 = df["price"].iloc[-60]
        result["change_60d_pct"] = round((latest - p60) / p60 * 100, 2)

    if len(df) >= 14:
        delta = df["price"].diff().iloc[-14:]
        gain = delta.clip(lower=0).mean()
        loss = (-delta.clip(upper=0)).mean()
        if loss > 0:
            rs = gain / loss
            result["rsi_14"] = round(100 - 100 / (1 + rs), 1)
        else:
            result["rsi_14"] = 100.0

    if len(df) >= 20:
        ma20 = df["price"].iloc[-20:].mean()
        result["ma20_deviation_pct"] = round((latest - ma20) / ma20 * 100, 2)

    year_data = df.tail(min(252, len(df)))
    high_52w = year_data["price"].max()
    low_52w = year_data["price"].min()
    if high_52w > low_52w:
        pos = (latest - low_52w) / (high_52w - low_52w) * 100
        result["position_vs_52w"] = round(pos, 1)

    if len(df) >= 60:
        rolling_60d = df["price"].rolling(60).apply(
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
```

**Step 2: Verify**

```
cd scripts/stock && python -c "
from long_term_scanner import _analyze_precious_metals
import json
result = _analyze_precious_metals()
print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
"
```

Expected: JSON output with gold/silver analysis data.

---

## Task 4: Industry-adaptive upside assessment

**Files:**
- Modify: `scripts/stock/long_term_scanner.py` — add upside assessment functions

**Step 1: Add upside assessment with percentile-based scoring**

Append to `long_term_scanner.py`:

```python
# ---------------------------------------------------------------------------
# Step 5: Industry-adaptive upside assessment
# ---------------------------------------------------------------------------

def _upside_assessment(symbol: str) -> dict:
    """
    Evaluate whether a stock still has upside or is overheated.
    Uses percentile-based scoring relative to own history — NOT fixed thresholds.
    An AI stock up 50% in 60d may be normal; a bank stock up 25% may be extreme.
    """
    from technical_analysis import load_ohlcv, compute_indicators
    from fundamental_analysis import fetch_fundamentals

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
```

**Step 2: Verify**

```
cd scripts/stock && python -c "
from long_term_scanner import _upside_assessment
import json
result = _upside_assessment('600519')
print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
"
```

Expected: JSON with upside_score + 5 dimensions for Moutai.

---

## Task 5: LLM theme analysis + stock mapping + final selection

**Files:**
- Modify: `scripts/stock/long_term_scanner.py` — add Steps 3-6

**Step 1: Add LLM trend analysis (Step 3)**

Append to `long_term_scanner.py`:

```python
# ---------------------------------------------------------------------------
# Step 3: LLM trend analysis — identify investment themes
# ---------------------------------------------------------------------------

def _build_signal_summary(signals: dict, metals: dict) -> str:
    """Condense 14 days of signals into a prompt-friendly summary."""
    parts = []

    wn = signals.get("world_news", [])
    if wn:
        parts.append(f"【近{SIGNAL_WINDOW_DAYS}天国际新闻 ({len(wn)}条)】")
        for item in wn[:60]:
            parts.append(f"  [{item['date']}] {item['headline']}")

    ai = signals.get("ai_tech_news", [])
    if ai:
        parts.append(f"\n【近{SIGNAL_WINDOW_DAYS}天AI/科技新闻 ({len(ai)}条)】")
        for item in ai[:40]:
            parts.append(f"  [{item['date']}] {item['headline']}")

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
        parts.append(f"\n【全球情绪】")
        if fg.get("value") is not None:
            parts.append(f"  Fear & Greed: {fg['value']} ({fg.get('label','')})")
        if vix.get("value") is not None:
            parts.append(f"  VIX: {vix['value']} ({vix.get('change_pct','?')}%)")
        if mood.get("recommendation"):
            parts.append(f"  建议: {mood['recommendation']}")

    if metals:
        parts.append(f"\n【贵金属行情】")
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

    return "\n".join(parts)


def _llm_theme_analysis(signal_summary: str) -> list[dict]:
    """
    Ask LLM to identify 3-5 investment themes from the signal summary.
    Returns list of themes with industries and stock suggestions.
    """
    log.info("Step 3: LLM 趋势研判...")

    system_prompt = (
        "你是资深A股策略分析师, 擅长从宏观新闻和政策中识别中长期投资机会。\n\n"
        "任务: 基于提供的近2周新闻和市场信号, 识别未来1-3个月最可能受益的投资主题。\n\n"
        "要求:\n"
        "1. 输出3-5个投资主题 (不要凑数, 只输出有高置信度支撑的)\n"
        "2. 每个主题包含: name(主题名称), logic(受益逻辑), industries(相关A股行业列表), "
        "catalysts(催化剂事件), time_horizon(1个月/3个月/6个月), risk(风险因素), "
        "confidence(高/中高/中)\n"
        "3. 同时考虑国际局势和国内政策两条线对A股的传导\n"
        "4. 关注: 政策利好, 技术突破, 行业拐点, 供需变化, 地缘事件传导\n\n"
        "只输出JSON数组, 不要输出其他文字。"
    )

    user_prompt = f"以下是近{SIGNAL_WINDOW_DAYS}天的市场信号汇总:\n\n{signal_summary}\n\n请识别投资主题, 只输出JSON数组:"

    return _call_llm_json(system_prompt, user_prompt, max_tokens=2000)


def _call_llm_json(system_prompt: str, user_prompt: str, max_tokens: int = 1500) -> list | dict:
    """Call LLM (DeepSeek preferred, Ollama fallback) and parse JSON response."""
    import re

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
    import requests
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
    import re
    text = raw.strip()
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL).strip()

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

    log.warning("JSON 解析失败, raw=%s", text[:300])
    return []
```

**Step 2: Add stock mapping (Step 4) and final selection (Step 6)**

Append to `long_term_scanner.py`:

```python
# ---------------------------------------------------------------------------
# Step 4: Map themes to candidate stocks
# ---------------------------------------------------------------------------

def _map_themes_to_candidates(themes: list[dict]) -> list[dict]:
    """Map investment themes to specific A-share stock candidates."""
    log.info("Step 4: 投资主题 → 候选个股...")
    candidates = []
    seen_symbols = set()

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

        for stock in matched[:6]:
            stock["theme"] = theme_name
            stock["theme_logic"] = theme.get("logic", "")
            stock["time_horizon"] = theme.get("time_horizon", "")
            stock["catalysts"] = theme.get("catalysts", [])
            stock["theme_risk"] = theme.get("risk", "")
            stock["theme_confidence"] = theme.get("confidence", "中")
        candidates.extend(matched[:6])

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

def _llm_final_selection(candidates: list[dict], themes: list[dict],
                         metals: dict, signal_summary: str) -> list[dict]:
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
        "你是资深A股长期投资策略师。从候选股票中精选最多5只作为未来1-3个月的长期推荐。\n\n"
        "选股标准:\n"
        "1. 空间评分 ≥ 60 (必须有上涨空间, 过热的不选)\n"
        "2. 投资主题逻辑清晰且催化剂明确\n"
        "3. 基本面有底线支撑\n"
        "4. 宁缺毋滥 — 没有好选择时推荐0只\n\n"
        "对每只推荐的股票输出:\n"
        "symbol, name, theme, reason(推荐理由3-5条), time_horizon, "
        "catalysts(催化剂), risk, confidence(高/中高/中), "
        "watch_price(建议关注/建仓价位)\n\n"
        "只输出JSON数组。"
    )

    user_prompt = (
        f"候选股票列表:\n\n" + "\n\n".join(candidate_text) +
        f"\n\n请从中精选最多{MAX_PICKS}只长期推荐, 只输出JSON数组:"
    )

    picks_raw = _call_llm_json(system_prompt, user_prompt, max_tokens=2500)
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
```

**Step 3: Add LLM precious metals outlook**

Append to `long_term_scanner.py`:

```python
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
        f"贵金属数据:\n" + "\n".join(data_text) +
        f"\n\n近期相关新闻信号:\n{signal_summary[:3000]}\n\n"
        "请分析并输出JSON:"
    )

    result = _call_llm_json(system_prompt, user_prompt, max_tokens=1500)
    if isinstance(result, dict):
        metals["llm_outlook"] = result
    else:
        metals["llm_outlook"] = {"error": "LLM分析失败"}

    return metals
```

---

## Task 6: Orchestration, report generation, and RAG indexing

**Files:**
- Modify: `scripts/stock/long_term_scanner.py` — add main orchestration + report + RAG

**Step 1: Add report generation**

Append to `long_term_scanner.py`:

```python
# ---------------------------------------------------------------------------
# Report generation
# ---------------------------------------------------------------------------

def _generate_report(picks: list[dict], metals: dict, themes: list[dict],
                     scan_meta: dict) -> str:
    """Generate Markdown report for RAG indexing and human review."""
    date_str = datetime.now().strftime("%Y-%m-%d")
    lines = [
        f"# AI股票推荐报告(长期) — {date_str}",
        "",
        f"**分析时间**: {scan_meta.get('started_at', 'N/A')}",
        f"**信号窗口**: 近{SIGNAL_WINDOW_DAYS}天",
        f"**国际新闻**: {scan_meta.get('world_news_count', 0)} 条",
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

    # Part 2: Investment themes
    lines.extend(["## 二、投资主题", ""])
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
            "",
        ])

    lines.extend(["---", ""])

    # Part 3: Stock recommendations
    if not picks:
        lines.extend([
            "## 三、长期推荐: 暂无",
            "",
            "本次分析未找到同时满足趋势+空间+基本面要求的标的。",
            "\"不推荐\"本身就是最好的建议。",
            "",
        ])
    else:
        lines.extend([f"## 三、长期推荐 ({len(picks)} 只)", ""])
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
                for dk, dv in dims.items():
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
```

**Step 2: Add main orchestration + save + public API**

Append to `long_term_scanner.py`:

```python
# ---------------------------------------------------------------------------
# Save results + RAG indexing
# ---------------------------------------------------------------------------

def _save_results(picks: list[dict], metals: dict, themes: list[dict],
                  scan_meta: dict):
    """Persist results and generate report."""
    _ensure_dirs()
    date_str = datetime.now().strftime("%Y-%m-%d")

    result_path = os.path.join(LONG_TERM_DIR, f"{date_str}.json")
    result_data = {
        "date": date_str,
        "meta": scan_meta,
        "precious_metals": metals,
        "themes": themes,
        "picks": picks,
    }
    with open(result_path, "w", encoding="utf-8") as f:
        json.dump(result_data, f, ensure_ascii=False, indent=2, default=str)
    log.info("长期推荐结果已保存 → %s", result_path)

    report = _generate_report(picks, metals, themes, scan_meta)
    report_path = os.path.join(LONG_TERM_DIR, f"{date_str}-report.md")
    with open(report_path, "w", encoding="utf-8") as f:
        f.write(report)
    log.info("长期推荐报告已保存 → %s", report_path)

    _save_lt_history(picks, metals)


def _save_lt_history(picks: list[dict], metals: dict):
    """Save lightweight entry for performance tracking."""
    history_file = os.path.join(LONG_TERM_DIR, "history.json")
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
            {"symbol": p.get("symbol"), "name": p.get("name"),
             "price": p.get("price"), "theme": p.get("theme"),
             "upside_score": p.get("upside", {}).get("upside_score")}
            for p in picks
        ],
        "gold_trend": metals.get("gold", {}).get("trend"),
        "silver_trend": metals.get("silver", {}).get("trend"),
        "gold_price": metals.get("gold", {}).get("latest_price"),
        "silver_price": metals.get("silver", {}).get("latest_price"),
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
        progress["status"] = "stopped"; _save_progress(progress); return

    progress["status"] = "analyzing_metals"
    progress["world_news_count"] = len(signals.get("world_news", []))
    progress["ai_news_count"] = len(signals.get("ai_tech_news", []))
    _save_progress(progress)

    # Step 2: Precious metals analysis
    metals = _analyze_precious_metals()
    if _stop_event.is_set():
        progress["status"] = "stopped"; _save_progress(progress); return

    signal_summary = _build_signal_summary(signals, metals)
    metals = _llm_metals_outlook(metals, signal_summary)
    if _stop_event.is_set():
        progress["status"] = "stopped"; _save_progress(progress); return

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
        progress["status"] = "stopped"; _save_progress(progress); return

    progress["status"] = "mapping_stocks"
    progress["themes"] = themes
    _save_progress(progress)

    # Step 4: Map themes to stocks + fundamental filter
    candidates = _map_themes_to_candidates(themes)
    candidates = _filter_candidates(candidates)
    if _stop_event.is_set():
        progress["status"] = "stopped"; _save_progress(progress); return

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
        progress["status"] = "stopped"; _save_progress(progress); return

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
        "signal_window_days": SIGNAL_WINDOW_DAYS,
    }
    _save_results(picks, metals, themes, scan_meta)

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
```

---

## Task 7: API endpoints in agent.py

**Files:**
- Modify: `scripts/rag/agent.py` — add routes after line ~5303 (after last scan endpoint)
- Modify: `scripts/rag/agent.py:5018` — add `long_term_scanner` to `_STOCK_MODULES`

**Step 1: Add `long_term_scanner` to module list**

In `scripts/rag/agent.py`, line 5018, add `"long_term_scanner"` to `_STOCK_MODULES`:

```python
# Before:
    "watchlist", "scanner", "hot_sectors", "market_sentiment",

# After:
    "watchlist", "scanner", "long_term_scanner", "hot_sectors", "market_sentiment",
```

**Step 2: Add 7 API endpoints after the last scan endpoint**

Insert after line 5303 (after `api_stock_scan_result_by_date`):

```python
# --- Long-Term Scanner ---

@app.route("/api/stock/long-term/start", methods=["POST"])
@_with_stock_imports
def api_stock_lt_start():
    """Start long-term stock scanner."""
    try:
        body = request.get_json(silent=True) or {}
        use_ds = body.get("use_deepseek", False)
        from long_term_scanner import start_lt_scan
        result = start_lt_scan(use_deepseek=use_ds)
        return jsonify(result)
    except Exception as exc:
        traceback.print_exc()
        return jsonify({"error": str(exc)}), 500


@app.route("/api/stock/long-term/status", methods=["GET"])
@_with_stock_imports
def api_stock_lt_status():
    """Get long-term scan progress."""
    try:
        from long_term_scanner import get_lt_status
        return jsonify(get_lt_status())
    except Exception as exc:
        traceback.print_exc()
        return jsonify({"error": str(exc)}), 500


@app.route("/api/stock/long-term/stop", methods=["POST"])
@_with_stock_imports
def api_stock_lt_stop():
    """Stop long-term scan."""
    try:
        from long_term_scanner import stop_lt_scan
        return jsonify(stop_lt_scan())
    except Exception as exc:
        traceback.print_exc()
        return jsonify({"error": str(exc)}), 500


@app.route("/api/stock/long-term/result", methods=["GET"])
@_with_stock_imports
def api_stock_lt_result():
    """Get latest long-term scan result."""
    try:
        from long_term_scanner import get_lt_latest_result
        result = get_lt_latest_result()
        if result:
            return jsonify(result)
        return jsonify({"error": "暂无长期推荐结果"}), 404
    except Exception as exc:
        traceback.print_exc()
        return jsonify({"error": str(exc)}), 500


@app.route("/api/stock/long-term/history", methods=["GET"])
@_with_stock_imports
def api_stock_lt_history():
    """Get long-term scan history."""
    try:
        from long_term_scanner import get_lt_history
        return jsonify({"history": get_lt_history()})
    except Exception as exc:
        traceback.print_exc()
        return jsonify({"error": str(exc)}), 500


@app.route("/api/stock/long-term/dates", methods=["GET"])
@_with_stock_imports
def api_stock_lt_dates():
    """List available long-term scan dates."""
    try:
        from long_term_scanner import list_lt_scan_dates
        return jsonify({"dates": list_lt_scan_dates()})
    except Exception as exc:
        traceback.print_exc()
        return jsonify({"error": str(exc)}), 500


@app.route("/api/stock/long-term/result/<date_str>", methods=["GET"])
@_with_stock_imports
def api_stock_lt_result_by_date(date_str):
    """Get long-term scan result for a specific date."""
    try:
        from long_term_scanner import get_lt_result_by_date
        result = get_lt_result_by_date(date_str)
        if result:
            return jsonify(result)
        return jsonify({"error": "该日期无长期推荐结果"}), 404
    except Exception as exc:
        traceback.print_exc()
        return jsonify({"error": str(exc)}), 500
```

---

## Task 8: Long-term Modal HTML + JS in agent.py

**Files:**
- Modify: `scripts/rag/agent.py` — add Modal HTML after scannerModal (after line ~6574)
- Modify: `scripts/rag/agent.py` — add JS functions (in the script section)

**Step 1: Add Long-Term Modal HTML**

Insert after line 6574 (after the closing `</div>` of scannerModal):

```html
<!-- Long-Term Scanner Modal -->
<div id="longTermModal" class="modal-overlay" role="dialog" aria-modal="true">
  <div class="modal-panel" style="max-width:96vw;max-height:94vh;width:980px;background:#0f1117;border:1px solid #2a2d3e">
    <div class="modal-head" style="border-bottom:1px solid #2a2d3e">
      <h2>&#128302; AI 股票推荐(长期)</h2>
      <button type="button" class="modal-close" onclick="closeLongTermModal()" title="Close">&times;</button>
    </div>
    <div class="modal-content" style="padding:14px 18px;background:#0f1117">
      <div style="display:flex;gap:8px;align-items:center;margin-bottom:12px;flex-wrap:wrap">
        <button type="button" class="send-btn" id="btnLtStart" onclick="startLtScan()" style="padding:8px 18px;font-size:0.86em">&#128302; 开始分析</button>
        <button type="button" class="toolbar-btn" id="btnLtStop" onclick="stopLtScan()" style="font-size:0.78em" disabled>&#9724; 停止</button>
        <button type="button" class="toolbar-btn" onclick="loadLtHistory()" style="font-size:0.78em">&#128203; 历史记录</button>
        <label style="display:flex;align-items:center;gap:4px;font-size:0.78em;color:#a0a4b8;cursor:pointer;margin-left:8px" title="使用 DeepSeek 进行趋势分析">
          <input type="checkbox" id="ltUseDeepseek" style="accent-color:#8b5cf6">
          <span>&#128171; DeepSeek</span>
        </label>
        <span id="ltStatus" style="font-size:0.78em;color:#8b8fa4;margin-left:auto"></span>
      </div>
      <div id="ltProgress" style="display:none;margin-bottom:12px">
        <div style="background:#1a1d2e;border-radius:8px;overflow:hidden;height:24px;border:1px solid #2a2d3e">
          <div id="ltProgressBar" style="height:100%;background:linear-gradient(90deg,#8b5cf6,#ec4899);transition:width 0.5s;width:0%;display:flex;align-items:center;justify-content:center">
            <span id="ltProgressText" style="font-size:0.72em;color:#fff;font-weight:600"></span>
          </div>
        </div>
        <div id="ltPhase" style="font-size:0.76em;color:#8b8fa4;margin-top:4px"></div>
      </div>
      <div id="ltResult" style="max-height:62vh;overflow-y:auto;border:1px solid #2a2d3e;border-radius:8px;padding:14px;background:#1a1d2e;font-size:0.84em;line-height:1.6;color:#c4c8f0">
        <p style="color:#6b7280">点击"开始分析"启动AI长期趋势推荐。分析流程：</p>
        <p style="color:#6b7280">1. 收集近14天新闻信号 → 2. 贵金属分析 → 3. LLM趋势研判 → 4. 选股+空间评估 → 5. 精选推荐</p>
        <p style="color:#6b7280;font-size:0.9em;margin-top:8px">基于国际/国内新闻、政策趋势、板块轮动进行中长期预判(1-3个月)。</p>
      </div>
    </div>
  </div>
</div>
```

**Step 2: Add JS functions**

Insert in the JavaScript section (after the existing scanner JS, around line ~9100):

```javascript
// --- Long-Term Scanner ---
let _ltPollTimer = null;
function openLongTermModal() {
  document.getElementById('longTermModal').classList.add('open');
  pollLtStatus();
}
function closeLongTermModal() {
  document.getElementById('longTermModal').classList.remove('open');
  if (_ltPollTimer) { clearInterval(_ltPollTimer); _ltPollTimer = null; }
}
async function startLtScan() {
  const st = document.getElementById('ltStatus');
  st.textContent = '启动中...';
  document.getElementById('btnLtStart').disabled = true;
  document.getElementById('btnLtStop').disabled = false;
  document.getElementById('ltProgress').style.display = 'block';
  var useDs = document.getElementById('ltUseDeepseek').checked;
  document.getElementById('ltResult').innerHTML = '<p style="color:#a78bfa">⏳ 正在分析长期趋势...' + (useDs ? ' (DeepSeek enabled)' : '') + '</p>';
  try {
    const r = await fetch('/api/stock/long-term/start', {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({use_deepseek: useDs})});
    const d = await r.json();
    if (d.error) { st.textContent = d.error; document.getElementById('btnLtStart').disabled = false; return; }
    st.textContent = '分析进行中';
    if (!_ltPollTimer) _ltPollTimer = setInterval(pollLtStatus, 5000);
  } catch(e) { st.textContent = '启动失败'; document.getElementById('btnLtStart').disabled = false; }
}
async function stopLtScan() {
  try { await fetch('/api/stock/long-term/stop', {method:'POST'}); } catch(e) {}
  document.getElementById('ltStatus').textContent = '正在停止...';
}
async function pollLtStatus() {
  try {
    const r = await fetch('/api/stock/long-term/status');
    const d = await r.json();
    const st = document.getElementById('ltStatus');
    const bar = document.getElementById('ltProgressBar');
    const txt = document.getElementById('ltProgressText');
    const phase = document.getElementById('ltPhase');
    const prog = document.getElementById('ltProgress');
    if (!d.status || d.status === '') return;
    prog.style.display = 'block';

    const phases = {
      'collecting_signals': {pct: '15%', text: '收集近14天新闻信号...'},
      'analyzing_metals': {pct: '30%', text: '贵金属分析 (黄金/白银)...'},
      'analyzing_themes': {pct: '50%', text: 'LLM 趋势研判...'},
      'mapping_stocks': {pct: '65%', text: '投资主题 → 候选个股...'},
      'assessing_upside': {pct: '80%', text: '空间评估: ' + (d.assessed_count||0) + '/' + (d.candidate_count||'?')},
      'final_selection': {pct: '92%', text: 'LLM 精选推荐...'},
    };

    if (d.status === 'done') {
      bar.style.width = '100%'; txt.textContent = '完成'; phase.textContent = '';
      st.textContent = '分析完成';
      document.getElementById('btnLtStart').disabled = false;
      document.getElementById('btnLtStop').disabled = true;
      if (_ltPollTimer) { clearInterval(_ltPollTimer); _ltPollTimer = null; }
      renderLtResult(d);
    } else if (d.status === 'stopped') {
      phase.textContent = '已暂停'; st.textContent = '已暂停';
      document.getElementById('btnLtStart').disabled = false;
      document.getElementById('btnLtStop').disabled = true;
      if (_ltPollTimer) { clearInterval(_ltPollTimer); _ltPollTimer = null; }
    } else if (d.status === 'error') {
      phase.textContent = '错误: ' + (d.error || '未知'); st.textContent = '分析失败';
      document.getElementById('btnLtStart').disabled = false;
      document.getElementById('btnLtStop').disabled = true;
      if (_ltPollTimer) { clearInterval(_ltPollTimer); _ltPollTimer = null; }
    } else if (phases[d.status]) {
      bar.style.width = phases[d.status].pct;
      txt.textContent = '';
      phase.textContent = phases[d.status].text;
    }
    if (d.running) {
      document.getElementById('btnLtStart').disabled = true;
      document.getElementById('btnLtStop').disabled = false;
    }
  } catch(e) {}
}
function renderLtResult(data) {
  const el = document.getElementById('ltResult');
  let h = '';

  // Precious metals section
  var metals = data.precious_metals || data.metals || {};
  if (metals.gold || metals.silver) {
    h += '<div style="margin-bottom:16px"><h3 style="color:#fbbf24;margin:0 0 10px">🥇 贵金属分析</h3>';
    ['gold','silver'].forEach(key => {
      var m = metals[key];
      if (!m || !m.data_available) return;
      var label = key === 'gold' ? '黄金' : '白银';
      var emoji = key === 'gold' ? '🥇' : '🥈';
      var trendColor = m.trend === '上涨' ? '#22c55e' : m.trend === '下跌' ? '#ef4444' : m.trend === '过热' ? '#f59e0b' : '#8b8fa4';
      h += '<div style="background:#0f1117;border:1px solid #2a2d3e;border-radius:8px;padding:10px;margin-bottom:8px">';
      h += '<div style="display:flex;justify-content:space-between;align-items:center">';
      h += '<span style="font-size:1em;font-weight:700;color:#e0e0e0">' + emoji + ' ' + label + ' ¥' + (m.latest_price||'-') + '</span>';
      h += '<span style="color:' + trendColor + ';font-weight:600">' + (m.trend||'') + ' (空间' + (m.upside_score||'?') + '/100)</span>';
      h += '</div>';
      h += '<div style="display:flex;gap:12px;margin-top:6px;font-size:0.82em;color:#a0a4b8">';
      h += '<span>14天: ' + ((m.change_14d_pct||0)>0?'+':'') + (m.change_14d_pct||0).toFixed(1) + '%</span>';
      h += '<span>60天: ' + ((m.change_60d_pct||0)>0?'+':'') + (m.change_60d_pct||0).toFixed(1) + '%</span>';
      h += '<span>RSI: ' + (m.rsi_14||'-') + '</span>';
      h += '<span>52周位: ' + (m.position_vs_52w||'-') + '%</span>';
      h += '</div></div>';
    });
    if (metals.gold_silver_ratio) {
      h += '<div style="font-size:0.82em;color:#a0a4b8;margin-bottom:8px">金银比: ' + metals.gold_silver_ratio + ' (' + (metals.ratio_signal||'') + ')</div>';
    }
    var outlook = metals.llm_outlook;
    if (outlook && !outlook.error) {
      ['gold','silver'].forEach(key => {
        var o = outlook[key];
        if (!o) return;
        var label = key === 'gold' ? '黄金' : '白银';
        h += '<div style="background:#0c1220;border:1px solid #1e3a5f;border-radius:6px;padding:8px;margin-bottom:6px;font-size:0.82em">';
        h += '<span style="color:#60a5fa;font-weight:600">' + label + '展望: ' + (o.trend||'') + '</span>';
        if (o.drivers) h += '<div style="color:#a0a4b8;margin-top:2px">驱动: ' + o.drivers + '</div>';
        if (o.advice) h += '<div style="color:#a3e635;margin-top:2px">建议: ' + o.advice + '</div>';
        if (o.price_range) h += '<div style="color:#38bdf8;margin-top:2px">区间: ' + o.price_range + '</div>';
        h += '</div>';
      });
      if (outlook.summary) h += '<div style="font-size:0.85em;color:#e0e0e0;margin-top:4px">' + outlook.summary + '</div>';
    }
    h += '</div>';
  }

  // Themes section
  var themes = data.themes || [];
  if (themes.length > 0) {
    h += '<div style="margin-bottom:16px"><h3 style="color:#a78bfa;margin:0 0 10px">📊 投资主题 (' + themes.length + ')</h3>';
    themes.forEach((t,i) => {
      h += '<div style="background:#0f1117;border:1px solid #2a2d3e;border-radius:8px;padding:10px;margin-bottom:6px">';
      h += '<div style="font-weight:700;color:#c4b5fd">' + (i+1) + '. ' + (t.name||'') + '</div>';
      h += '<div style="font-size:0.82em;color:#a0a4b8;margin-top:4px">' + (t.logic||'') + '</div>';
      if (t.industries) h += '<div style="font-size:0.8em;color:#8b8fa4;margin-top:2px">行业: ' + (Array.isArray(t.industries) ? t.industries.join(', ') : t.industries) + '</div>';
      if (t.catalysts) h += '<div style="font-size:0.8em;color:#38bdf8;margin-top:2px">催化剂: ' + (Array.isArray(t.catalysts) ? t.catalysts.join(', ') : t.catalysts) + '</div>';
      h += '<div style="display:flex;gap:10px;font-size:0.78em;margin-top:4px">';
      if (t.time_horizon) h += '<span style="color:#a0a4b8">⏱ ' + t.time_horizon + '</span>';
      if (t.confidence) h += '<span style="color:#fbbf24">置信度: ' + t.confidence + '</span>';
      h += '</div></div>';
    });
    h += '</div>';
  }

  // Picks section
  var picks = data.picks || [];
  if (picks.length === 0) {
    h += '<div style="text-align:center;padding:16px"><p style="color:#fbbf24;font-size:1em">本次分析: 暂无个股推荐</p>';
    h += '<p style="color:#8b8fa4;font-size:0.82em">未找到空间充裕且趋势明确的标的, 请参考贵金属分析和投资主题。</p></div>';
  } else {
    h += '<div><h3 style="color:#22c55e;margin:0 0 10px">✅ 长期推荐 (' + picks.length + ' 只)</h3>';
    picks.forEach((p,i) => {
      var upside = p.upside || {};
      var us = upside.upside_score || 0;
      var usColor = us >= 75 ? '#22c55e' : us >= 60 ? '#60a5fa' : us >= 40 ? '#fbbf24' : '#ef4444';
      h += '<div style="background:#0f1117;border:1px solid #2a2d3e;border-radius:8px;padding:12px;margin-bottom:8px">';
      h += '<div style="display:flex;justify-content:space-between;align-items:center">';
      h += '<div><span style="color:#22c55e;font-weight:700;font-size:1.1em">#' + (i+1) + '</span> ';
      h += '<span style="color:#60a5fa;font-weight:600">' + (p.name||'') + '</span> <span style="color:#8b8fa4">(' + (p.symbol||'') + ')</span></div>';
      h += '<div><span style="color:' + usColor + ';font-weight:700">空间 ' + us + '/100</span></div>';
      h += '</div>';
      h += '<div style="font-size:0.82em;margin-top:6px">';
      h += '<span style="color:#c4b5fd">主题: ' + (p.theme||'') + '</span>';
      if (p.time_horizon) h += ' <span style="color:#8b8fa4">| ⏱ ' + p.time_horizon + '</span>';
      h += '</div>';
      if (p.recommendation_reason) h += '<div style="margin-top:4px;color:#a3e635;font-size:0.85em">💡 ' + p.recommendation_reason + '</div>';
      if (p.recommendation_risk) h += '<div style="margin-top:2px;color:#f87171;font-size:0.8em">⚠️ ' + p.recommendation_risk + '</div>';
      if (p.watch_price) h += '<div style="margin-top:2px;color:#38bdf8;font-size:0.82em">👀 关注价位: ' + p.watch_price + '</div>';

      // Upside assessment card
      var dims = upside.dimensions || {};
      var dimKeys = Object.keys(dims);
      if (dimKeys.length > 0) {
        h += '<details style="margin-top:8px"><summary style="font-size:0.78em;color:#8b8fa4;cursor:pointer">空间评估明细</summary>';
        h += '<div style="display:flex;flex-wrap:wrap;gap:4px;margin-top:4px">';
        dimKeys.forEach(k => {
          var d = dims[k];
          var dc = (d.score||0) >= 60 ? '#10b981' : (d.score||0) >= 40 ? '#fbbf24' : '#f87171';
          h += '<div style="flex:1;min-width:150px;background:#111827;border-radius:4px;padding:4px 6px;font-size:0.76em">';
          h += '<span style="color:' + dc + '">' + (d.name||k) + ': ' + (d.score||'-') + '/100</span>';
          if (d.detail) h += '<div style="color:#6b7280">' + d.detail + '</div>';
          h += '</div>';
        });
        h += '</div></details>';
      }
      h += '</div>';
    });
    h += '</div>';
  }

  el.innerHTML = h || '<p style="color:#6b7280">暂无结果</p>';
}
async function loadLtHistory() {
  const el = document.getElementById('ltResult');
  el.innerHTML = '<p style="color:#a78bfa">加载历史记录...</p>';
  try {
    const r = await fetch('/api/stock/long-term/history');
    const d = await r.json();
    const hist = d.history || [];
    if (hist.length === 0) { el.innerHTML = '<p style="color:#6b7280">暂无历史记录</p>'; return; }
    let h = '<h3 style="color:#a78bfa;margin:0 0 8px">长期推荐历史</h3>';
    hist.slice().reverse().forEach(entry => {
      h += '<div style="background:#0f1117;border:1px solid #2a2d3e;border-radius:6px;padding:8px;margin-bottom:6px;cursor:pointer" onclick="loadLtDate(\'' + entry.date + '\')">';
      h += '<div style="display:flex;justify-content:space-between"><span style="color:#60a5fa">' + entry.date + '</span>';
      h += '<span style="color:#8b8fa4">' + (entry.picks||[]).length + ' 只推荐</span></div>';
      if (entry.gold_trend) h += '<span style="font-size:0.78em;color:#fbbf24">金: ' + entry.gold_trend + ' ¥' + (entry.gold_price||'-') + '</span> ';
      if (entry.silver_trend) h += '<span style="font-size:0.78em;color:#a0a4b8">银: ' + entry.silver_trend + ' ¥' + (entry.silver_price||'-') + '</span>';
      (entry.picks||[]).forEach(p => {
        h += '<div style="font-size:0.78em;color:#a0a4b8">  ' + (p.name||p.symbol) + ' (空间' + (p.upside_score||'?') + ') — ' + (p.theme||'') + '</div>';
      });
      h += '</div>';
    });
    el.innerHTML = h;
  } catch(e) { el.innerHTML = '<p style="color:#f87171">加载失败: ' + e.message + '</p>'; }
}
async function loadLtDate(dateStr) {
  const el = document.getElementById('ltResult');
  el.innerHTML = '<p style="color:#a78bfa">加载 ' + dateStr + ' 结果...</p>';
  try {
    const r = await fetch('/api/stock/long-term/result/' + dateStr);
    const d = await r.json();
    if (d.error) { el.innerHTML = '<p style="color:#f87171">' + d.error + '</p>'; return; }
    renderLtResult(d);
  } catch(e) { el.innerHTML = '<p style="color:#f87171">加载失败</p>'; }
}
```

---

## Task 9: Telegram Bot — `/longscan` command

**Files:**
- Modify: `scripts/bot_telegram.py:178-205` — add format function
- Modify: `scripts/bot_telegram.py:~550` — add command handler
- Modify: `scripts/bot_telegram.py:592` — register handler

**Step 1: Add format function after `_fmt_scan_result`**

Insert after line 205:

```python
def _fmt_lt_result(data: dict) -> str:
    picks = data.get("picks", [])
    metals = data.get("precious_metals", {})
    themes = data.get("themes", [])

    lines = ["AI Long-Term Analysis Complete\n"]

    for key, label in [("gold", "Gold"), ("silver", "Silver")]:
        m = metals.get(key, {})
        if m.get("data_available"):
            lines.append(
                f"{label}: ¥{m.get('latest_price','-')} "
                f"14d:{m.get('change_14d_pct',0):+.1f}% "
                f"Trend:{m.get('trend','-')} "
                f"Upside:{m.get('upside_score','-')}/100"
            )

    if themes:
        lines.append(f"\nThemes ({len(themes)}):")
        for t in themes:
            lines.append(f"  • {t.get('name','')} ({t.get('time_horizon','')})")

    if not picks:
        lines.append("\nNo stock picks this time.")
    else:
        lines.append(f"\nRecommended: {len(picks)} stock(s)\n")
        for i, p in enumerate(picks, 1):
            upside = p.get("upside", {})
            lines.append(
                f"{i}. {p.get('name','?')} ({p.get('symbol','?')})\n"
                f"   Theme: {p.get('theme','')}\n"
                f"   Upside: {upside.get('upside_score','?')}/100\n"
                f"   Reason: {p.get('recommendation_reason','N/A')}\n"
                f"   Risk: {p.get('recommendation_risk','N/A')}"
            )
    return "\n".join(lines)
```

**Step 2: Add command handler after `cmd_scan`**

Insert after line ~550:

```python
@owner_only
async def cmd_longscan(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Starting long-term analysis...")
    try:
        resp = await _agent_post("/api/stock/long-term/start")
        msg = resp.get("message", "started")
        await update.message.reply_text(f"Long-term scanner: {msg}")

        for _ in range(90):
            await asyncio.sleep(10)
            try:
                st = await _agent_get("/api/stock/long-term/status")
                status = st.get("status", "")
                if status in ("done",):
                    result = await _agent_get("/api/stock/long-term/result")
                    text = _fmt_lt_result(result)
                    await update.message.reply_text(_truncate(text))
                    return
                elif status in ("error", "stopped"):
                    await update.message.reply_text(f"Long-term scan {status}: {st.get('error','')}")
                    return
            except Exception:
                continue
        await update.message.reply_text("Long-term analysis still running (stopped polling after 15 min).")
    except Exception as e:
        await update.message.reply_text(f"Long-term scan error: {e}")
```

**Step 3: Register handler**

In `scripts/bot_telegram.py`, after line 592 (`CommandHandler("scan", cmd_scan)`), add:

```python
    app.add_handler(CommandHandler("longscan", cmd_longscan))
```

---

## Task 10: RAG indexing for both scanners

**Files:**
- Modify: `scripts/stock/scanner.py` — add RAG index call after save
- Modify: `scripts/stock/long_term_scanner.py` — add RAG index call after save

**Step 1: Add RAG indexing helper to both modules**

Add this function to both `scanner.py` and `long_term_scanner.py`:

```python
def _index_report_to_rag(report_path: str, date_str: str, item_type: str, title: str):
    """Index the Markdown report into RAG store for search/retrieval."""
    try:
        rag_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "rag")
        sys.path.insert(0, rag_dir)
        from index_briefing import _get_model, _get_client, _save_snapshot, _chunk_text, COLLECTION

        with open(report_path, encoding="utf-8") as f:
            content = f.read()

        model = _get_model()
        client = _get_client()

        chunks = _chunk_text(content, max_chars=800)
        from qdrant_client.models import PointStruct
        import uuid as _uuid

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
```

**Step 2: Call from scanner.py `_save_results`**

In `scanner.py`, at the end of `_save_results` (after line ~1161), add:

```python
    _index_report_to_rag(report_path, date_str, "stock_scan_short",
                         f"AI短期推荐 {date_str}")
```

**Step 3: Call from long_term_scanner.py `_save_results`**

In `long_term_scanner.py`, at the end of `_save_results`, add:

```python
    _index_report_to_rag(report_path, date_str, "stock_scan_long",
                         f"AI长期推荐 {date_str}")
```

---

## Task 11: Update architecture documentation

**Files:**
- Modify: `docs/design/architecture.md`

**Step 1: Update Stock Module Architecture diagram**

In the Stock Module Architecture mermaid diagram (around line 326-385), update the Scanner layer:

```mermaid
    subgraph ScannerLayer["Market Scanner"]
        L1["Short-Term Scanner<br/>(scanner.py)<br/>5000+ → 0-5 picks<br/>realtime + TA + fundflow"]
        LT["Long-Term Scanner<br/>(long_term_scanner.py)<br/>14-day news → themes<br/>+ precious metals + ≤5 picks"]
    end
```

Update connections:

```mermaid
    AKShare --> L1
    AKShare --> LT
    L1 --> L2
    ...
    LT --> OutputLayer
```

**Step 2: Update Evolution timeline**

Add to the "Advanced" section:

```
        Long-Term Scanner : News-driven theme analysis + precious metals
```

**Step 3: Update Key Design Decisions table**

Add row:

```
| Long-term scanner | Independent pipeline from short-term | Different signal sources (news vs realtime), different logic (themes vs buyability), prevents cross-contamination |
```

---

## Execution Summary

| Task | Description | Estimated effort |
|------|-------------|-----------------|
| 1 | Rename existing scanner to "短期推荐" | Small (5 string changes) |
| 2 | Signal collection module | Medium (new file, core skeleton) |
| 3 | Precious metals analysis | Medium (gold/silver + technical) |
| 4 | Upside assessment (industry-adaptive) | Medium (5 dimensions, percentile-based) |
| 5 | LLM theme analysis + stock mapping + selection | Large (3 LLM calls, mapping logic) |
| 6 | Orchestration + report + save | Medium (main loop, Markdown report) |
| 7 | API endpoints in agent.py | Small (7 routes, boilerplate) |
| 8 | Long-term Modal HTML + JS | Large (full UI, progress, rendering) |
| 9 | Telegram `/longscan` command | Small (handler + format) |
| 10 | RAG indexing for both scanners | Small (index helper + 2 call sites) |
| 11 | Update architecture docs | Small (diagram + text updates) |

---

## Post-Implementation Code Review Fixes

Applied after code review (2026-04-27). All fixes are reflected in the task code blocks above.

| ID | Severity | File | Fix |
|----|----------|------|-----|
| C1 | Critical | `scanner.py` | `_chunk_text(max_tokens=400)` → `_chunk_text(max_chars=400)` — matched `index_briefing._chunk_text` signature |
| C2 | Critical | `scanner.py` | `_save_snapshot()` → `_save_snapshot(client)` — matched `index_briefing._save_snapshot` signature |
| C3 | Critical | `agent.py` (JS) | `pollLtStatus` on `done`: now fetches `/api/stock/long-term/result` for full data (including `precious_metals`) before calling `renderLtResult` |
| I4 | Important | `long_term_scanner.py` | LLM themes response normalization: if dict, extract list from known keys; if not list, default to `[]` |
| I5 | Important | `long_term_scanner.py` | `_llm_final_selection`: skip (with warning) stocks not in candidate list instead of appending partial dicts |
| I6 | Important | `architecture.md` | Directory name corrected: `long_term_scans/` → `long_term/` (matching code) |
| I7 | Important | `long_term_scanner.py` | Replaced fixed `upside_score >= 40` threshold with relative ranking: sort by score descending, take top 50% (min 5) |

---

## Task 12: Stock PDF Export (all stock features)

**Added 2026-04-27** — unified PDF export for all 6 stock feature modals.

**Files:**
- **New:** `scripts/stock/stock_pdf.py` — shared ReportLab-based PDF generator
- **Modified:** `scripts/rag/agent.py` — 2 new API routes + 6 "导出PDF" buttons + JS handler + data caching
- **Modified:** `docs/design/architecture.md` — PDF output in diagram, file tree, API routes, timeline

**Architecture:**
- Single `generate_stock_pdf(report_type, data)` entry point in `stock_pdf.py`
- 6 type-specific builders: `_build_short_term`, `_build_long_term`, `_build_stock_analysis`, `_build_price_prediction`, `_build_watchlist`, `_build_national_team`
- Unified style: STSong-Light CID Chinese font, A4 18mm margins, consistent color palette and table styles
- PDFs saved to `STOCK_REPORTS_ROOT/pdf/{type}_{date}.pdf`
- API: `POST /api/stock/export-pdf` (generate) + `GET /api/stock/pdf-file/<date>/<filename>` (serve)
- UI: `exportStockPdf(type, dataKey)` JS function shared across all modals, data cached via `_cachePdfData` on result render
- For scanner/watchlist/national-team: if no cached data, auto-fetches from API before generating PDF
