"""
市场状态检测 — 大盘 + 个股双层 regime 标签.

Phase 3.2: MA20/MA60 + ATR% 判定牛市/熊市/震荡/高波动.
"""
import json
import logging
import os
import time
from datetime import datetime

import numpy as np
import pandas as pd

from config import STOCK_CACHE_DIR, STOCK_DATA_DIR

log = logging.getLogger(__name__)

_CACHE_INDEX = os.path.join(STOCK_CACHE_DIR, ".regime", "csi300.csv")
_MARKET_SYMBOL = "000300"

REGIME_LABELS = {
    "strong_bull": "强牛",
    "uptrend": "牛市",
    "sideways": "震荡",
    "downtrend": "熊市",
    "high_volatility": "高波动",
    "unknown": "未知",
}

REGIME_ADVICE = {
    "strong_bull": "动量策略激活，可适度提高仓位",
    "uptrend": "顺势为主，关注动量因子",
    "sideways": "降低交易频率，更依赖估值而非动量",
    "downtrend": "收紧止损，降低总仓位",
    "high_volatility": "全面减仓，保留核心持仓",
    "unknown": "数据不足，保守操作",
}


def _cache_fresh(path: str, hours: float = 8) -> bool:
    return os.path.isfile(path) and (time.time() - os.path.getmtime(path)) < hours * 3600


def _load_index_ohlcv() -> pd.DataFrame | None:
    """沪深300指数日线 (缓存)."""
    if _cache_fresh(_CACHE_INDEX):
        df = pd.read_csv(_CACHE_INDEX, encoding="utf-8-sig")
        if len(df) >= 60:
            return df

    try:
        import akshare as ak
        df = ak.stock_zh_index_daily_em(symbol="sh000300")
        if df is not None and not df.empty:
            os.makedirs(os.path.dirname(_CACHE_INDEX), exist_ok=True)
            df.to_csv(_CACHE_INDEX, index=False, encoding="utf-8-sig")
            return df
    except Exception as e:
        log.warning("沪深300指数获取失败: %s", e)

    if os.path.isfile(_CACHE_INDEX):
        return pd.read_csv(_CACHE_INDEX, encoding="utf-8-sig")
    return None


def _compute_regime_from_ohlcv(df: pd.DataFrame) -> dict:
    """从 OHLCV DataFrame 计算 regime (列: date/close/high/low 或中文列)."""
    if df is None or len(df) < 60:
        return {"regime": "unknown", "regime_zh": REGIME_LABELS["unknown"]}

    work = df.copy()
    col_map = {"日期": "date", "收盘": "close", "最高": "high", "最低": "low"}
    work.rename(columns={k: v for k, v in col_map.items() if k in work.columns}, inplace=True)

    if "close" not in work.columns:
        return {"regime": "unknown", "regime_zh": REGIME_LABELS["unknown"]}

    c = pd.to_numeric(work["close"], errors="coerce")
    h = pd.to_numeric(work.get("high", c), errors="coerce")
    l = pd.to_numeric(work.get("low", c), errors="coerce")

    ma20 = c.rolling(20).mean().iloc[-1]
    ma60 = c.rolling(60).mean().iloc[-1]
    close = c.iloc[-1]

    tr = pd.concat([h - l, (h - c.shift(1)).abs(), (l - c.shift(1)).abs()], axis=1).max(axis=1)
    atr = tr.rolling(14).mean().iloc[-1]
    atr_pct = float(atr / close * 100) if close > 0 else 0

    ma_spread_pct = abs(ma20 - ma60) / ma60 * 100 if ma60 > 0 else 0
    new_highs = int((c.iloc[-20:] >= c.iloc[-20:].cummax()).sum())

    if atr_pct > 5:
        regime = "high_volatility"
    elif ma20 > ma60 and atr_pct < 3:
        regime = "strong_bull" if new_highs >= 5 else "uptrend"
    elif ma20 < ma60 and atr_pct > 3:
        regime = "downtrend"
    elif ma_spread_pct < 1:
        regime = "sideways"
    elif ma20 > ma60:
        regime = "uptrend"
    else:
        regime = "downtrend"

    return {
        "regime": regime,
        "regime_zh": REGIME_LABELS.get(regime, regime),
        "advice": REGIME_ADVICE.get(regime, ""),
        "ma20": round(float(ma20), 2) if pd.notna(ma20) else None,
        "ma60": round(float(ma60), 2) if pd.notna(ma60) else None,
        "atr_pct": round(atr_pct, 2),
        "ma_spread_pct": round(ma_spread_pct, 2),
        "close": round(float(close), 2) if pd.notna(close) else None,
    }


def detect_symbol_regime(symbol: str) -> dict:
    """个股级别 regime."""
    from technical_analysis import load_ohlcv, compute_indicators

    ohlcv = load_ohlcv(symbol)
    if ohlcv is None:
        return {"symbol": symbol, "regime": "unknown", "regime_zh": "未知", "error": "无日线数据"}

    ohlcv = compute_indicators(ohlcv)
    out = _compute_regime_from_ohlcv(ohlcv)
    out["symbol"] = symbol
    out["level"] = "symbol"
    out["checked_at"] = datetime.now().isoformat()
    return out


def detect_market_regime() -> dict:
    """大盘级别 regime (沪深300)."""
    df = _load_index_ohlcv()
    out = _compute_regime_from_ohlcv(df)
    out["symbol"] = _MARKET_SYMBOL
    out["name"] = "沪深300"
    out["level"] = "market"
    out["checked_at"] = datetime.now().isoformat()
    return out


def detect_regime(symbol: str | None = None) -> dict:
    """双层检测: 大盘 + 可选个股."""
    market = detect_market_regime()
    result = {"market": market}
    if symbol:
        result["symbol_regime"] = detect_symbol_regime(symbol)
    result["checked_at"] = datetime.now().isoformat()
    return result


def regime_position_multiplier(regime: str) -> float:
    """根据 regime 调整建议总仓位比例."""
    return {
        "strong_bull": 0.85,
        "uptrend": 0.75,
        "sideways": 0.55,
        "downtrend": 0.35,
        "high_volatility": 0.25,
    }.get(regime, 0.50)
