"""
特征工程 — 将原始OHLCV + 技术指标转换为ML模型可用的特征矩阵.

从 technical_analysis.py 获取带指标的 DataFrame,
再派生出收益率、动量、波动率、均线距离、资金流向、北向资金、
板块轮动、T+1约束、市场情绪、追高惩罚等衍生特征,
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

    _add_fund_flow_features(df, symbol)
    _add_northbound_features(df)
    _add_t1_features(df)
    _add_market_mood_features(df)
    _add_chase_penalty_features(df)

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


def _safe_import_china_data():
    """Lazy import china_market_data to avoid circular deps and allow graceful fallback."""
    try:
        import china_market_data as cmd
        return cmd
    except ImportError:
        log.debug("china_market_data 模块不可用, 跳过中国特色特征")
        return None


def _add_fund_flow_features(df: pd.DataFrame, symbol: str):
    """资金流向特征: 主力净流入、价格-资金背离等。按日期对齐。"""
    cmd = _safe_import_china_data()
    if cmd is None:
        return

    try:
        ff_df = cmd.fetch_stock_fund_flow(symbol)
    except Exception as e:
        log.debug("资金流向获取失败 %s: %s", symbol, e)
        return

    if ff_df is None or ff_df.empty or len(ff_df) < 3:
        return

    net_col = None
    pct_col = None
    super_col = None
    for col in ff_df.columns:
        if "主力净流入" in col and "净额" in col:
            net_col = col
        elif "主力净流入" in col and "净占比" in col:
            pct_col = col
        elif "超大单" in col and "净额" in col:
            super_col = col

    if net_col is None:
        for col in ff_df.columns:
            if "主力" in col and "净" in col:
                net_col = col
                break
    if net_col is None:
        return

    ff_df = ff_df.copy()
    if "日期" in ff_df.columns:
        ff_df["_date"] = pd.to_datetime(ff_df["日期"], errors="coerce").dt.strftime("%Y-%m-%d")
    else:
        return

    ff_df[net_col] = pd.to_numeric(ff_df[net_col], errors="coerce").fillna(0)
    ff_df["_net_3d"] = ff_df[net_col].rolling(3, min_periods=1).sum()
    ff_df["_net_10d"] = ff_df[net_col].rolling(10, min_periods=3).sum()
    if pct_col:
        ff_df[pct_col] = pd.to_numeric(ff_df[pct_col], errors="coerce").fillna(0)
        ff_df["_pct_3d"] = ff_df[pct_col].rolling(3, min_periods=1).sum()

    net_rank_5 = ff_df[net_col].rolling(5, min_periods=3).mean().rank(pct=True)
    ff_df["_net_rank_5"] = net_rank_5

    if super_col:
        ff_df[super_col] = pd.to_numeric(ff_df[super_col], errors="coerce").fillna(0)
        super_sum = ff_df[super_col].rolling(5, min_periods=3).sum()
        net_abs_sum = ff_df[net_col].abs().rolling(5, min_periods=3).sum().replace(0, np.nan)
        ff_df["_super_ratio"] = super_sum / net_abs_sum

    date_col_df = pd.to_datetime(df["date"], errors="coerce").dt.strftime("%Y-%m-%d") if "date" in df.columns else None
    if date_col_df is None:
        return

    ff_lookup = ff_df.set_index("_date")

    for feat, src in [("ff_main_net_3d", "_net_3d"),
                      ("ff_main_net_10d", "_net_10d")]:
        df[feat] = np.nan
        if src in ff_lookup.columns:
            mapped = date_col_df.map(ff_lookup[src]).values
            df[feat] = mapped.astype(float)

    df["ff_main_pct_3d"] = np.nan
    if "_pct_3d" in ff_lookup.columns:
        df["ff_main_pct_3d"] = date_col_df.map(ff_lookup["_pct_3d"]).values.astype(float)

    df["ff_super_large_ratio"] = np.nan
    if "_super_ratio" in ff_lookup.columns:
        df["ff_super_large_ratio"] = date_col_df.map(ff_lookup["_super_ratio"]).values.astype(float)

    df["ff_price_diverge_5d"] = np.nan
    if "ret_5d" in df.columns and "_net_rank_5" in ff_lookup.columns:
        net_r5 = date_col_df.map(ff_lookup["_net_rank_5"]).astype(float)
        ret_r5 = df["ret_5d"].rank(pct=True)
        df["ff_price_diverge_5d"] = net_r5.values - ret_r5.values


def _add_northbound_features(df: pd.DataFrame):
    """北向资金特征: 日净买入、5日/20日趋势、动量、连续天数。"""
    cmd = _safe_import_china_data()
    if cmd is None:
        return

    try:
        nb_df = cmd.fetch_northbound(days=250)
    except Exception as e:
        log.debug("北向资金获取失败: %s", e)
        return

    if nb_df is None or nb_df.empty:
        return

    net_col = "当日成交净买额"
    if net_col not in nb_df.columns:
        return

    nb_vals = pd.to_numeric(nb_df[net_col], errors="coerce").dropna()
    if nb_vals.empty:
        return

    df["nb_net_1d"] = np.nan
    df["nb_net_5d"] = np.nan
    df["nb_momentum"] = np.nan
    df["nb_consecutive"] = np.nan

    n = min(len(nb_vals), len(df))
    if n < 5:
        return

    vals = nb_vals.values[-n:]
    df.iloc[-n:, df.columns.get_loc("nb_net_1d")] = vals

    s = pd.Series(vals)
    df.iloc[-n:, df.columns.get_loc("nb_net_5d")] = s.rolling(5, min_periods=1).sum().values

    ma5 = s.rolling(5, min_periods=3).mean()
    ma20 = s.rolling(20, min_periods=10).mean().replace(0, np.nan)
    df.iloc[-n:, df.columns.get_loc("nb_momentum")] = (ma5 / ma20).values

    consec = np.zeros(n)
    streak = 0
    for i in range(n):
        if vals[i] > 0:
            streak = streak + 1 if streak >= 0 else 1
        elif vals[i] < 0:
            streak = streak - 1 if streak <= 0 else -1
        else:
            streak = 0
        consec[i] = streak
    df.iloc[-n:, df.columns.get_loc("nb_consecutive")] = consec


def _add_t1_features(df: pd.DataFrame):
    """T+1约束特征: 涨跌停接近度、跳空、隔夜风险。"""
    prev_close = df["close"].shift(1)
    change_pct = (df["close"] - prev_close) / prev_close * 100

    code_prefix = ""
    if "date" in df.columns:
        pass

    df["near_limit_up"] = (change_pct > 9.0).astype(int)
    df["near_limit_down"] = (change_pct < -9.0).astype(int)
    df["gap_up_pct"] = (df["open"] - prev_close) / prev_close * 100
    df["overnight_risk"] = (df["high"].shift(1) - df["close"].shift(1)) / df["close"].shift(1) * 100


def _add_market_mood_features(df: pd.DataFrame):
    """市场情绪特征: 融资余额变化、北向强度。"""
    cmd = _safe_import_china_data()
    if cmd is None:
        return

    df["mood_margin_chg_5d"] = np.nan
    df["mood_north_strength"] = np.nan

    try:
        mg = cmd.margin_sentiment(window=5)
        if mg and mg.get("balance_change_pct"):
            df.iloc[-1, df.columns.get_loc("mood_margin_chg_5d")] = mg["balance_change_pct"]
    except Exception:
        pass

    try:
        nb = cmd.northbound_momentum(window_short=5, window_long=20)
        if nb and nb.get("momentum"):
            df.iloc[-1, df.columns.get_loc("mood_north_strength")] = nb["momentum"]
    except Exception:
        pass


def _add_chase_penalty_features(df: pd.DataFrame):
    """追高惩罚特征: 连涨天数、均线偏离度、RSI+资金流出组合。"""
    change = df["close"].pct_change() * 100

    consec = np.zeros(len(df))
    streak = 0
    for i in range(len(df)):
        if change.iat[i] > 0:
            streak = streak + 1 if streak > 0 else 1
        elif change.iat[i] < 0:
            streak = streak - 1 if streak < 0 else -1
        else:
            streak = 0
        consec[i] = streak
    df["penalty_consec_up"] = consec

    if "ma20" in df.columns:
        df["penalty_dist_ma20_pct"] = (df["close"] - df["ma20"]) / df["ma20"] * 100
    else:
        df["penalty_dist_ma20_pct"] = np.nan

    df["penalty_rsi_with_outflow"] = 0
    if "rsi_14" in df.columns and "ff_main_net_3d" in df.columns:
        mask = (df["rsi_14"] > 70) & (df["ff_main_net_3d"] < 0)
        df.loc[mask, "penalty_rsi_with_outflow"] = 1

    if "volume" in df.columns:
        vol_trend = df["volume"].pct_change().rolling(3).mean()
        price_trend = change.rolling(3).mean()
        df["penalty_volume_diverge"] = 0
        mask = (price_trend > 0) & (vol_trend < -0.05)
        df.loc[mask, "penalty_volume_diverge"] = 1
    else:
        df["penalty_volume_diverge"] = 0


def _add_target(df: pd.DataFrame, forward_days: int, threshold: float):
    """计算目标变量: 未来N日收益率 + 三分类标签."""
    df["target_ret"] = df["close"].shift(-forward_days) / df["close"] * 100 - 100

    df["target"] = 0
    df.loc[df["target_ret"] > threshold, "target"] = 1
    df.loc[df["target_ret"] < -threshold, "target"] = -1


_CHINA_FEATURE_PREFIXES = ("ff_", "nb_", "mood_")


def _get_feature_columns(df: pd.DataFrame) -> list[str]:
    """自动识别所有特征列 (排除日期、目标、原始价格).

    China-specific features (ff_*, nb_*, mood_*) use a lower threshold (15%)
    because their data sources only cover ~100 recent trading days.
    """
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
            is_china = any(c.startswith(p) for p in _CHINA_FEATURE_PREFIXES)
            threshold = 0.15 if is_china else 0.5
            if valid_pct >= threshold:
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
