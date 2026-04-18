"""
特征工程 — 将原始OHLCV + 技术指标转换为ML模型可用的特征矩阵.

从 technical_analysis.py 获取带指标的 DataFrame,
再派生出收益率、动量、波动率、均线距离等衍生特征,
最终输出一个干净的特征矩阵 + 目标变量.
"""
import json
import logging
import os

import numpy as np
import pandas as pd

from config import STOCK_DATA_DIR
from technical_analysis import load_ohlcv, compute_indicators

log = logging.getLogger(__name__)

FEATURE_COLS: list[str] = []


def build_features(symbol: str, forward_days: int = 5, threshold: float = 2.0) -> pd.DataFrame | None:
    """
    为一只股票构建完整的特征矩阵.

    Args:
        symbol: 股票代码
        forward_days: 预测未来N天的涨跌 (默认5天)
        threshold: 涨跌判定阈值百分比 (默认±2%)

    Returns:
        DataFrame, 每行一个交易日, 包含所有特征列 + target列:
          target = 1 (涨 > threshold%), 0 (平), -1 (跌 < -threshold%)
          target_ret = 未来N日实际收益率%
    """
    df = load_ohlcv(symbol)
    if df is None or len(df) < 120:
        log.warning("数据不足, 需要至少120行, %s 只有 %d 行",
                    symbol, 0 if df is None else len(df))
        return None

    df = compute_indicators(df)

    _add_return_features(df)
    _add_momentum_features(df)
    _add_volatility_features(df)
    _add_ma_distance_features(df)
    _add_volume_features(df)
    _add_pattern_features(df)
    _add_fundamental_features(df, symbol)
    _add_calendar_features(df)

    _add_target(df, forward_days, threshold)

    feature_cols = _get_feature_columns(df)
    keep = ["date"] + feature_cols + ["target", "target_ret"]
    keep = [c for c in keep if c in df.columns]
    result = df[keep].copy()

    result.dropna(subset=feature_cols, how="all", inplace=True)

    global FEATURE_COLS
    FEATURE_COLS = feature_cols

    log.info("%s: 构建特征矩阵 %d行 x %d列 (有效特征: %d)",
             symbol, len(result), len(result.columns), len(feature_cols))
    return result


def _add_return_features(df: pd.DataFrame):
    """收益率特征: 1/3/5/10/20日回报率."""
    for n in [1, 3, 5, 10, 20]:
        df[f"ret_{n}d"] = df["close"].pct_change(n) * 100

    df["gap"] = (df["open"] / df["close"].shift(1) - 1) * 100

    if "pct_change" not in df.columns:
        df["pct_change"] = df["close"].pct_change() * 100


def _add_momentum_features(df: pd.DataFrame):
    """动量特征: RSI变化率, MACD变化, KDJ趋势."""
    if "rsi_14" in df.columns:
        df["rsi_delta"] = df["rsi_14"].diff()
        df["rsi_5d_delta"] = df["rsi_14"].diff(5)

    macd_hist_col = [c for c in df.columns if c.startswith("MACDh_")]
    if macd_hist_col:
        col = macd_hist_col[0]
        df["macd_hist_delta"] = df[col].diff()
        df["macd_hist_sign_change"] = (
            (df[col] > 0).astype(int).diff().abs()
        )

    if "kdj_j" in df.columns:
        df["kdj_j_delta"] = df["kdj_j"].diff()


def _add_volatility_features(df: pd.DataFrame):
    """波动率特征: ATR%, 振幅, 布林带宽."""
    if "atr_14" in df.columns:
        df["atr_pct"] = df["atr_14"] / df["close"] * 100

    if "high" in df.columns and "low" in df.columns:
        df["daily_range_pct"] = (df["high"] - df["low"]) / df["close"] * 100
        df["range_5d_avg"] = df["daily_range_pct"].rolling(5).mean()

    if "bb_width" in df.columns:
        df["bb_width_delta"] = df["bb_width"].diff()

    df["volatility_20d"] = df["close"].pct_change().rolling(20).std() * 100 * np.sqrt(252)


def _add_ma_distance_features(df: pd.DataFrame):
    """均线距离特征: 价格偏离各均线的百分比."""
    for ma in ["ma5", "ma10", "ma20", "ma60"]:
        if ma in df.columns:
            df[f"dist_{ma}"] = (df["close"] - df[ma]) / df[ma] * 100

    if "ma5" in df.columns and "ma20" in df.columns:
        df["ma5_ma20_spread"] = (df["ma5"] - df["ma20"]) / df["ma20"] * 100

    if "ma10" in df.columns and "ma60" in df.columns:
        df["ma10_ma60_spread"] = (df["ma10"] - df["ma60"]) / df["ma60"] * 100


def _add_volume_features(df: pd.DataFrame):
    """成交量特征: 量比, 量变化率."""
    if "volume" in df.columns:
        df["vol_change_1d"] = df["volume"].pct_change() * 100
        df["vol_change_5d"] = df["volume"].pct_change(5) * 100

    if "vol_ma20" in df.columns and "volume" in df.columns:
        safe = df["vol_ma20"].replace(0, np.nan)
        df["vol_ratio_20"] = df["volume"] / safe


def _add_pattern_features(df: pd.DataFrame):
    """K线形态数值化: 上下影线比、实体比等."""
    o, h, l, c = df["open"], df["high"], df["low"], df["close"]
    body = (c - o).abs()
    total_range = (h - l).replace(0, np.nan)

    df["body_ratio"] = body / total_range
    df["upper_shadow_ratio"] = (h - pd.concat([o, c], axis=1).max(axis=1)) / total_range
    df["lower_shadow_ratio"] = (pd.concat([o, c], axis=1).min(axis=1) - l) / total_range
    df["is_bullish"] = (c > o).astype(int)

    df["bullish_streak"] = 0
    streak = 0
    for i in range(len(df)):
        if df["is_bullish"].iat[i] == 1:
            streak += 1
        else:
            streak = 0
        df.iloc[i, df.columns.get_loc("bullish_streak")] = streak


def _add_fundamental_features(df: pd.DataFrame, symbol: str):
    """基本面特征: PE, PB, ROE等.
    Only applied to the LAST row to avoid look-ahead bias.
    Static values from fundamentals.json reflect current data,
    not as-of-date values, so filling all rows would leak future info.
    """
    fund_path = os.path.join(STOCK_DATA_DIR, symbol, "fundamentals.json")
    if not os.path.isfile(fund_path):
        return

    try:
        with open(fund_path, encoding="utf-8") as f:
            fund = json.load(f)
    except Exception:
        return

    val = fund.get("valuation", {})
    fin = fund.get("financials", {})

    last_idx = df.index[-1]
    for key, src_dict, src_key in [
        ("feat_pe", val, "pe_dynamic"),
        ("feat_pb", val, "pb"),
        ("feat_roe", fin, "roe"),
        ("feat_debt_ratio", fin, "debt_ratio"),
        ("feat_profit_yoy", fin, "profit_yoy"),
    ]:
        raw = src_dict.get(src_key)
        if raw is not None:
            try:
                df[key] = np.nan
                df.at[last_idx, key] = float(raw)
            except (ValueError, TypeError):
                pass


def _add_calendar_features(df: pd.DataFrame):
    """日历特征: 星期几, 月份."""
    if "date" not in df.columns:
        return

    dates = pd.to_datetime(df["date"], errors="coerce")
    df["day_of_week"] = dates.dt.dayofweek
    df["month"] = dates.dt.month


def _add_target(df: pd.DataFrame, forward_days: int, threshold: float):
    """计算目标变量: 未来N日收益率 + 三分类标签."""
    df["target_ret"] = df["close"].shift(-forward_days) / df["close"] * 100 - 100

    df["target"] = 0
    df.loc[df["target_ret"] > threshold, "target"] = 1
    df.loc[df["target_ret"] < -threshold, "target"] = -1


def _get_feature_columns(df: pd.DataFrame) -> list[str]:
    """自动识别所有特征列 (排除日期、目标、原始价格)."""
    exclude = {
        "date", "open", "high", "low", "close", "volume", "amount",
        "target", "target_ret",
        "obv", "price_change",
        "ma5", "ma10", "ma20", "ma60", "ma120", "ma250",
        "bb_lower", "bb_mid", "bb_upper",
        "vol_ma5", "vol_ma20",
        "atr_14",
    }
    exclude_prefixes = (
        "MACD_", "MACDs_", "MACDh_", "STOCHk", "STOCHd", "STOCHh",
        "BBL_", "BBM_", "BBU_", "BBB_", "BBP_",
    )

    cols = []
    for c in df.columns:
        if c in exclude:
            continue
        if any(c.startswith(p) for p in exclude_prefixes):
            continue
        if df[c].dtype in (np.float64, np.float32, np.int64, np.int32, float, int):
            valid_pct = df[c].notna().mean()
            if valid_pct >= 0.5:
                cols.append(c)

    return sorted(cols)


def get_feature_names() -> list[str]:
    """返回最近一次 build_features 生成的特征列名."""
    return FEATURE_COLS


if __name__ == "__main__":
    import sys
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    sym = sys.argv[1] if len(sys.argv) > 1 else "600519"
    result = build_features(sym)
    if result is not None:
        print(f"\n特征矩阵: {result.shape}")
        print(f"特征列: {FEATURE_COLS}")
        print(f"\n目标分布:")
        print(result["target"].value_counts().to_string())
        print(f"\n前5行:")
        print(result.head().to_string())
    else:
        print("构建失败")
