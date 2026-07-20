"""
预置回测策略模板 — Phase 5.2.

Strategy 1: momentum — MA趋势 + 动量
Strategy 2: valuation_momentum — 均线非下跌 + 低波动
Strategy 3: dca — 每月定投基准
"""
import logging

import numpy as np
import pandas as pd

log = logging.getLogger(__name__)

STRATEGY_NAMES = {
    "timing": "择时模型 (已有)",
    "simple_ma": "均线交叉",
    "momentum": "ML动量策略",
    "valuation_momentum": "估值+动量混合",
    "dca": "沪深300定投基准",
}


def get_signal_generator(strategy: str):
    """Return signal generator function(symbol, ohlcv) -> Series."""
    return {
        "momentum": generate_momentum_signals,
        "valuation_momentum": generate_valuation_momentum_signals,
        "dca": generate_dca_signals,
        "simple_ma": None,
        "timing": None,
    }.get(strategy)


def generate_momentum_signals(symbol: str, ohlcv: pd.DataFrame) -> pd.Series:
    """买入: MA20>MA60 且 5日动量>0; 卖出: MA20<MA60 或动量转负."""
    signals = pd.Series(0, index=ohlcv.index)
    c = ohlcv["close"]
    ma20 = c.rolling(20).mean()
    ma60 = c.rolling(60).mean()
    mom5 = c.pct_change(5) * 100

    try:
        from regime_detector import detect_symbol_regime
        reg = detect_symbol_regime(symbol).get("regime", "")
        if reg in ("downtrend", "high_volatility"):
            return signals
    except Exception:
        pass

    for i in range(60, len(ohlcv)):
        if pd.isna(ma20.iloc[i]) or pd.isna(ma60.iloc[i]):
            continue
        if ma20.iloc[i] > ma60.iloc[i] and mom5.iloc[i] > 1.0:
            signals.iloc[i] = 1
        elif ma20.iloc[i] < ma60.iloc[i] or (mom5.iloc[i] < -0.5):
            signals.iloc[i] = -1
    return signals


def generate_valuation_momentum_signals(symbol: str, ohlcv: pd.DataFrame) -> pd.Series:
    """买入: 非下跌趋势 + 20日波动偏低; 卖出: MA20<MA60."""
    signals = pd.Series(0, index=ohlcv.index)
    c = ohlcv["close"]
    ma20 = c.rolling(20).mean()
    ma60 = c.rolling(60).mean()
    vol20 = c.pct_change().rolling(20).std() * 100

    low_pct = None
    try:
        from valuation import historical_percentile
        hp = historical_percentile(symbol)
        low_pct = hp.get("pe_percentile")
    except Exception:
        pass

    for i in range(60, len(ohlcv)):
        if pd.isna(ma20.iloc[i]) or pd.isna(ma60.iloc[i]):
            continue
        vol_ok = vol20.iloc[i] < 3.0 if pd.notna(vol20.iloc[i]) else True
        val_ok = low_pct is None or low_pct <= 50
        if ma20.iloc[i] >= ma60.iloc[i] and vol_ok and val_ok:
            signals.iloc[i] = 1
        elif ma20.iloc[i] < ma60.iloc[i]:
            signals.iloc[i] = -1
    return signals


def generate_dca_signals(symbol: str, ohlcv: pd.DataFrame) -> pd.Series:
    """每月第一个交易日买入 (定投基准)."""
    signals = pd.Series(0, index=ohlcv.index)
    dates = pd.to_datetime(ohlcv["date"], errors="coerce")
    last_month = None
    for i, d in enumerate(dates):
        if pd.isna(d):
            continue
        key = (d.year, d.month)
        if key != last_month:
            signals.iloc[i] = 1
            last_month = key
    return signals


def list_strategies() -> list[dict]:
    return [{"id": k, "name": v} for k, v in STRATEGY_NAMES.items()]
