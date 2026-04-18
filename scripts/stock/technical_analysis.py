"""
技术分析引擎 — 计算技术指标 + 识别K线形态.

从本地 daily.csv 加载日线数据, 使用 pandas-ta 计算所有常用指标,
然后判断每个指标的信号方向 (看涨/看跌/中性).
"""
import json
import os
import logging
from datetime import datetime

import pandas as pd
import pandas_ta as ta

from config import STOCK_DATA_DIR

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# 数据加载
# ---------------------------------------------------------------------------

def load_ohlcv(symbol: str) -> pd.DataFrame | None:
    """加载本地日线 CSV, 返回标准化 DataFrame."""
    csv_path = os.path.join(STOCK_DATA_DIR, symbol, "daily.csv")
    if not os.path.isfile(csv_path):
        log.warning("未找到 %s 的日线数据: %s", symbol, csv_path)
        return None

    df = pd.read_csv(csv_path, encoding="utf-8-sig")

    col_map = {
        "日期": "date", "开盘": "open", "收盘": "close",
        "最高": "high", "最低": "low", "成交量": "volume",
        "成交额": "amount", "涨跌幅": "pct_change",
        "涨跌额": "price_change", "换手率": "turnover", "振幅": "amplitude",
    }
    df.rename(columns={k: v for k, v in col_map.items() if k in df.columns}, inplace=True)

    if "date" in df.columns:
        df["date"] = pd.to_datetime(df["date"])
        df.sort_values("date", inplace=True)
        df.reset_index(drop=True, inplace=True)

    for c in ["open", "high", "low", "close", "volume"]:
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors="coerce")

    return df


# ---------------------------------------------------------------------------
# 指标计算
# ---------------------------------------------------------------------------

def compute_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """在 DataFrame 上计算所有技术指标, 返回带新列的 DataFrame."""
    if df is None or len(df) < 30:
        log.warning("数据不足 (需要至少30行), 当前 %d 行", 0 if df is None else len(df))
        return df

    df["ma5"] = ta.sma(df["close"], length=5)
    df["ma10"] = ta.sma(df["close"], length=10)
    df["ma20"] = ta.sma(df["close"], length=20)
    df["ma60"] = ta.sma(df["close"], length=60)
    df["ma120"] = ta.sma(df["close"], length=120)
    df["ma250"] = ta.sma(df["close"], length=250)

    macd = ta.macd(df["close"], fast=12, slow=26, signal=9)
    if macd is not None:
        df = pd.concat([df, macd], axis=1)

    rsi = ta.rsi(df["close"], length=14)
    if rsi is not None:
        df["rsi_14"] = rsi

    stoch = ta.stoch(df["high"], df["low"], df["close"], k=9, d=3, smooth_k=3)
    if stoch is not None:
        df = pd.concat([df, stoch], axis=1)
        k_col = [c for c in df.columns if c.startswith("STOCHk")]
        d_col = [c for c in df.columns if c.startswith("STOCHd")]
        if k_col:
            df.rename(columns={k_col[0]: "kdj_k"}, inplace=True)
        if d_col:
            df.rename(columns={d_col[0]: "kdj_d"}, inplace=True)
        if "kdj_k" in df.columns and "kdj_d" in df.columns:
            df["kdj_j"] = 3 * df["kdj_k"] - 2 * df["kdj_d"]

    bbands = ta.bbands(df["close"], length=20, std=2)
    if bbands is not None:
        df = pd.concat([df, bbands], axis=1)
        for old, new in [("BBL_20_2.0", "bb_lower"), ("BBM_20_2.0", "bb_mid"), ("BBU_20_2.0", "bb_upper"), ("BBB_20_2.0", "bb_width"), ("BBP_20_2.0", "bb_pct")]:
            if old in df.columns:
                df.rename(columns={old: new}, inplace=True)

    obv = ta.obv(df["close"], df["volume"])
    if obv is not None:
        df["obv"] = obv

    df["vol_ma5"] = ta.sma(df["volume"], length=5)
    df["vol_ma20"] = ta.sma(df["volume"], length=20)

    atr = ta.atr(df["high"], df["low"], df["close"], length=14)
    if atr is not None:
        df["atr_14"] = atr

    return df


# ---------------------------------------------------------------------------
# 信号判断
# ---------------------------------------------------------------------------

def _safe(val):
    if val is None or (isinstance(val, float) and (pd.isna(val) or val != val)):
        return None
    return round(float(val), 4)


def evaluate_signals(df: pd.DataFrame) -> dict:
    """
    根据最新一行指标值, 判断各指标信号方向.

    Returns dict:
      {
        "date": "2026-04-11",
        "price": { "close": 1453.96, "change_pct": 1.2 },
        "signals": { "ma_trend": "看涨", ... },
        "indicators": { "rsi_14": 65.3, ... },
        "overall": "偏多",
        "patterns": [ ... ]
      }
    """
    if df is None or len(df) < 2:
        return {"error": "数据不足"}

    cur = df.iloc[-1]
    prev = df.iloc[-2]

    signals = {}
    indicators = {}

    close = _safe(cur.get("close"))
    ma5 = _safe(cur.get("ma5"))
    ma10 = _safe(cur.get("ma10"))
    ma20 = _safe(cur.get("ma20"))
    ma60 = _safe(cur.get("ma60"))

    if close is not None and ma20 is not None:
        if close > ma20 and ma5 is not None and ma5 > ma20:
            signals["均线趋势"] = "看涨"
        elif close < ma20 and ma5 is not None and ma5 < ma20:
            signals["均线趋势"] = "看跌"
        else:
            signals["均线趋势"] = "中性"
    indicators["ma5"] = ma5
    indicators["ma20"] = ma20
    indicators["ma60"] = ma60

    macd_col = [c for c in df.columns if c.startswith("MACD_")]
    signal_col = [c for c in df.columns if c.startswith("MACDs_")]
    hist_col = [c for c in df.columns if c.startswith("MACDh_")]

    if hist_col:
        hist_now = _safe(cur.get(hist_col[0]))
        hist_prev = _safe(prev.get(hist_col[0]))
        indicators["macd_histogram"] = hist_now
        if hist_now is not None and hist_prev is not None:
            if hist_now > 0 and hist_prev <= 0:
                signals["MACD"] = "金叉 (看涨)"
            elif hist_now < 0 and hist_prev >= 0:
                signals["MACD"] = "死叉 (看跌)"
            elif hist_now > 0:
                signals["MACD"] = "多头"
            else:
                signals["MACD"] = "空头"

    rsi = _safe(cur.get("rsi_14"))
    if rsi is not None:
        indicators["rsi_14"] = rsi
        if rsi > 80:
            signals["RSI"] = "严重超买"
        elif rsi > 70:
            signals["RSI"] = "超买"
        elif rsi < 20:
            signals["RSI"] = "严重超卖"
        elif rsi < 30:
            signals["RSI"] = "超卖"
        else:
            signals["RSI"] = "中性"

    kdj_j = _safe(cur.get("kdj_j"))
    kdj_k = _safe(cur.get("kdj_k"))
    kdj_d = _safe(cur.get("kdj_d"))
    if kdj_j is not None:
        indicators["kdj_j"] = kdj_j
        indicators["kdj_k"] = kdj_k
        indicators["kdj_d"] = kdj_d
        if kdj_j > 100:
            signals["KDJ"] = "超买"
        elif kdj_j < 0:
            signals["KDJ"] = "超卖"
        elif kdj_k is not None and kdj_d is not None:
            prev_k = _safe(prev.get("kdj_k"))
            prev_d = _safe(prev.get("kdj_d"))
            if prev_k is not None and prev_d is not None and kdj_k > kdj_d and prev_k <= prev_d:
                signals["KDJ"] = "金叉 (看涨)"
            elif prev_k is not None and prev_d is not None and kdj_k < kdj_d and prev_k >= prev_d:
                signals["KDJ"] = "死叉 (看跌)"
            else:
                signals["KDJ"] = "中性"

    bb_pct = _safe(cur.get("bb_pct"))
    bb_width = _safe(cur.get("bb_width"))
    if bb_pct is not None:
        indicators["bollinger_pct"] = bb_pct
        indicators["bollinger_width"] = bb_width
        if bb_pct > 1.0:
            signals["布林带"] = "突破上轨 (超买)"
        elif bb_pct < 0.0:
            signals["布林带"] = "跌破下轨 (超卖)"
        elif bb_width is not None and bb_width < 0.05:
            signals["布林带"] = "收窄 (即将变盘)"
        else:
            signals["布林带"] = "中性"

    vol = _safe(cur.get("volume"))
    vol_ma20 = _safe(cur.get("vol_ma20"))
    if vol is not None and vol_ma20 is not None and vol_ma20 > 0:
        vol_ratio = round(vol / vol_ma20, 2)
        indicators["volume_ratio"] = vol_ratio
        if vol_ratio > 2.0:
            signals["成交量"] = "显著放量"
        elif vol_ratio > 1.5:
            signals["成交量"] = "温和放量"
        elif vol_ratio < 0.5:
            signals["成交量"] = "极度缩量"
        else:
            signals["成交量"] = "正常"

    atr = _safe(cur.get("atr_14"))
    if atr is not None and close is not None:
        indicators["atr_14"] = atr
        indicators["atr_pct"] = round(atr / close * 100, 2)

    bullish = sum(1 for v in signals.values() if "看涨" in v or "金叉" in v or "超卖" in v)
    bearish = sum(1 for v in signals.values() if "看跌" in v or "死叉" in v or "超买" in v)
    if bullish > bearish + 1:
        overall = "看涨"
    elif bearish > bullish + 1:
        overall = "看跌"
    elif bullish > bearish:
        overall = "偏多"
    elif bearish > bullish:
        overall = "偏空"
    else:
        overall = "中性"

    patterns = detect_patterns(df)

    date_str = ""
    if "date" in df.columns:
        date_str = str(cur["date"])[:10]

    return {
        "date": date_str,
        "price": {
            "close": close,
            "change_pct": _safe(cur.get("pct_change")),
            "high": _safe(cur.get("high")),
            "low": _safe(cur.get("low")),
            "volume": _safe(cur.get("volume")),
        },
        "signals": signals,
        "indicators": indicators,
        "overall": overall,
        "patterns": patterns,
    }


# ---------------------------------------------------------------------------
# K线形态识别
# ---------------------------------------------------------------------------

def detect_patterns(df: pd.DataFrame) -> list[dict]:
    """检测最近3天的K线形态和趋势形态."""
    if df is None or len(df) < 5:
        return []

    patterns = []
    cur = df.iloc[-1]
    prev = df.iloc[-2]
    prev2 = df.iloc[-3]

    o, h, l, c = cur["open"], cur["high"], cur["low"], cur["close"]
    body = abs(c - o)
    upper_shadow = h - max(o, c)
    lower_shadow = min(o, c) - l
    total_range = h - l if h != l else 0.001

    po, ph, pl, pc = prev["open"], prev["high"], prev["low"], prev["close"]
    prev_body = abs(pc - po)

    if lower_shadow > body * 2 and upper_shadow < body * 0.5 and c > o:
        if _safe(cur.get("pct_change")) and cur["pct_change"] < 0:
            pass
        recent_trend = df["close"].iloc[-6:-1].mean() if len(df) >= 6 else c
        if c < recent_trend:
            patterns.append({"name": "锤子线", "direction": "看涨", "strength": "中等",
                             "desc": "长下影线, 买方在低位反击"})

    if upper_shadow > body * 2 and lower_shadow < body * 0.5 and c < o:
        recent_trend = df["close"].iloc[-6:-1].mean() if len(df) >= 6 else c
        if c > recent_trend:
            patterns.append({"name": "射击之星", "direction": "看跌", "strength": "中等",
                             "desc": "长上影线, 卖方在高位打压"})

    if body < total_range * 0.1:
        patterns.append({"name": "十字星", "direction": "待确认", "strength": "弱",
                         "desc": "开盘≈收盘, 多空分歧, 可能变盘"})

    if c > o and pc < po and body > prev_body and c > po and o < pc:
        patterns.append({"name": "看涨吞没", "direction": "看涨", "strength": "强",
                         "desc": "阳线完全吞没前一根阴线"})

    if c < o and pc > po and body > prev_body and c < po and o > pc:
        patterns.append({"name": "看跌吞没", "direction": "看跌", "strength": "强",
                         "desc": "阴线完全吞没前一根阳线"})

    p2o, p2c = prev2["open"], prev2["close"]
    if (p2c < p2o and  # day1: 阴线
        abs(pc - po) < abs(p2c - p2o) * 0.3 and  # day2: 小实体
        c > o and body > abs(p2c - p2o) * 0.5):  # day3: 阳线
        patterns.append({"name": "早晨之星", "direction": "看涨", "strength": "强",
                         "desc": "经典底部反转形态"})

    ma5 = _safe(cur.get("ma5"))
    ma20 = _safe(cur.get("ma20"))
    prev_ma5 = _safe(prev.get("ma5"))
    prev_ma20 = _safe(prev.get("ma20"))
    if ma5 is not None and ma20 is not None and prev_ma5 is not None and prev_ma20 is not None:
        if ma5 > ma20 and prev_ma5 <= prev_ma20:
            patterns.append({"name": "MA金叉 (5/20)", "direction": "看涨", "strength": "中等",
                             "desc": "5日均线上穿20日均线"})
        elif ma5 < ma20 and prev_ma5 >= prev_ma20:
            patterns.append({"name": "MA死叉 (5/20)", "direction": "看跌", "strength": "中等",
                             "desc": "5日均线下穿20日均线"})

    vol = _safe(cur.get("volume"))
    vol_ma20 = _safe(cur.get("vol_ma20"))
    if vol is not None and vol_ma20 is not None and vol_ma20 > 0:
        if vol > vol_ma20 * 2 and c > o:
            patterns.append({"name": "放量突破", "direction": "看涨", "strength": "强",
                             "desc": "成交量超过20日均量2倍, 伴随上涨"})
        elif vol > vol_ma20 * 2 and c < o:
            patterns.append({"name": "放量下跌", "direction": "看跌", "strength": "强",
                             "desc": "成交量超过20日均量2倍, 伴随下跌"})

    return patterns


# ---------------------------------------------------------------------------
# 支撑/阻力位
# ---------------------------------------------------------------------------

def calc_support_resistance(df: pd.DataFrame, lookback: int = 60) -> dict:
    """计算支撑位和阻力位 (基于 Pivot Points + 近期高低点)."""
    if df is None or len(df) < 5:
        return {}

    recent = df.tail(lookback)
    cur = df.iloc[-1]
    h, l, c = cur["high"], cur["low"], cur["close"]

    pivot = (h + l + c) / 3
    s1 = 2 * pivot - h
    r1 = 2 * pivot - l
    s2 = pivot - (h - l)
    r2 = pivot + (h - l)

    recent_high = recent["high"].max()
    recent_low = recent["low"].min()

    return {
        "pivot": round(pivot, 2),
        "support_1": round(s1, 2),
        "support_2": round(s2, 2),
        "resistance_1": round(r1, 2),
        "resistance_2": round(r2, 2),
        "recent_high": round(recent_high, 2),
        "recent_low": round(recent_low, 2),
        "lookback_days": lookback,
    }


# ---------------------------------------------------------------------------
# 完整分析入口
# ---------------------------------------------------------------------------

def analyze(symbol: str) -> dict:
    """
    对一只股票执行完整技术分析.

    Returns dict with: signals, indicators, patterns, support_resistance, overall
    """
    df = load_ohlcv(symbol)
    if df is None:
        return {"error": f"未找到 {symbol} 的日线数据"}

    df = compute_indicators(df)
    result = evaluate_signals(df)
    result["support_resistance"] = calc_support_resistance(df)
    result["symbol"] = symbol

    out_path = os.path.join(STOCK_DATA_DIR, symbol, "technical.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    log.info("技术分析完成 → %s", out_path)

    return result


if __name__ == "__main__":
    import sys
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    sym = sys.argv[1] if len(sys.argv) > 1 else "600519"
    result = analyze(sym)
    print(json.dumps(result, ensure_ascii=False, indent=2))
