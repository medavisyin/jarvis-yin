"""
截面 XGBoost 排序模型 — 用于 Scanner Layer 2.

核心理念:
  不预测个股的绝对涨跌方向，而是学习"哪只股票在截面中相对更强"。
  使用 rank:pairwise 目标函数，训练目标为行业中性化后的超额收益 (Alpha)。

数据流:
  Layer 1 候选股 (~100只) → 批量获取近 N 天历史行情 → 构建截面特征矩阵
  → XGBoost rank:pairwise 训练 → 预测当日截面排名 → 行业中性化输出

行业中性化:
  按申万行业分组，每组内独立排序，每行业取 Top N，避免组合过度暴露于单一行业。
"""
import logging
import os
import time
from datetime import datetime, timedelta

import numpy as np
import pandas as pd

from config import STOCK_DATA_DIR, STOCK_CACHE_DIR

log = logging.getLogger(__name__)

_LOOKBACK_DAYS = 60
_TRAIN_DAYS = 40
_VAL_DAYS = 20
_MIN_HISTORY = 30
_TOP_PER_INDUSTRY = 3
_FALLBACK_INDUSTRY = "其他"
_INDUSTRY_CACHE_HOURS = 24
_BATCH_DELAY = 0.3

_XGB_PARAMS = {
    "objective": "rank:pairwise",
    "max_depth": 4,
    "learning_rate": 0.05,
    "min_child_weight": 8,
    "subsample": 0.7,
    "colsample_bytree": 0.6,
    "reg_alpha": 0.5,
    "reg_lambda": 2.0,
    "n_estimators": 200,
    "verbosity": 0,
}

_FEATURE_COLS = [
    "ret_1d", "ret_3d", "ret_5d", "ret_10d", "ret_20d",
    "rsi_14", "rsi_delta",
    "macd_hist", "macd_hist_delta",
    "atr_pct", "volatility_20d",
    "dist_ma5", "dist_ma20", "dist_ma60",
    "ma5_ma20_spread",
    "vol_ratio_20", "vol_change_5d",
    "body_ratio", "upper_shadow_ratio",
    "turnover_rate",
    "cs_ret_rank", "cs_vol_rank", "cs_turnover_rank",
]


def cross_sectional_rank(
    candidates: list[dict],
    lookback_days: int = _LOOKBACK_DAYS,
    top_n_per_industry: int = _TOP_PER_INDUSTRY,
    stop_event=None,
) -> list[dict]:
    """截面排序主入口: 接收 Layer 1 候选股, 输出排序后的候选列表.

    Args:
        candidates: Layer 1 输出的候选股列表, 每项含 symbol/name/price 等
        lookback_days: 回看历史天数
        top_n_per_industry: 行业中性化后每行业取 Top N
        stop_event: 停止信号 (threading.Event)

    Returns:
        排序后的候选列表, 每项新增 score_l2, xgb_rank, industry 字段.
        失败时返回空列表 (调用方可回退到规则评分).
    """
    symbols = [c["symbol"] for c in candidates]
    sym_to_candidate = {c["symbol"]: c for c in candidates}

    log.info("截面排序: %d 只候选, 回看 %d 天", len(symbols), lookback_days)

    if _should_stop(stop_event):
        return []

    industry_map = _fetch_industry_map(symbols)
    log.info("行业分类: %d 个行业, %d 只有映射",
             len(set(industry_map.values())), len(industry_map))

    if _should_stop(stop_event):
        return []

    all_hist = _fetch_batch_history(symbols, lookback_days, stop_event)
    valid_symbols = [s for s in symbols if s in all_hist and len(all_hist[s]) >= _MIN_HISTORY]
    log.info("历史数据: %d/%d 只有足够数据 (>=%d天)",
             len(valid_symbols), len(symbols), _MIN_HISTORY)

    if len(valid_symbols) < 10:
        log.warning("有效股票不足10只, 截面排序无意义, 放弃")
        return []

    if _should_stop(stop_event):
        return []

    features_df, today_features, feature_cols = _build_cross_sectional_features(
        {s: all_hist[s] for s in valid_symbols}, industry_map
    )
    if features_df is None or today_features is None:
        log.warning("特征构建失败, 放弃截面排序")
        return []

    log.info("截面特征矩阵: %d 样本, %d 特征", len(features_df), len(feature_cols))

    if _should_stop(stop_event):
        return []

    model, val_ndcg = _train_ranker(features_df, feature_cols)
    if model is None:
        log.warning("模型训练失败, 放弃截面排序")
        return []

    log.info("模型训练完成, 验证集 NDCG@10: %.4f", val_ndcg)

    ranked = _predict_and_neutralize(
        model, today_features, feature_cols, industry_map, top_n_per_industry
    )

    result = []
    for rank_idx, row in enumerate(ranked):
        sym = row["symbol"]
        if sym not in sym_to_candidate:
            continue
        stock = dict(sym_to_candidate[sym])
        stock["score_l2"] = round(float(row["xgb_score"]), 4)
        stock["xgb_rank"] = rank_idx + 1
        stock["industry"] = industry_map.get(sym, _FALLBACK_INDUSTRY)
        stock["xgb_alpha"] = round(float(row.get("predicted_alpha", 0)), 4)
        stock["model_ndcg"] = round(val_ndcg, 4)
        result.append(stock)

    log.info("截面排序完成: %d 只入选 (行业中性化后)", len(result))
    return result


def _should_stop(stop_event) -> bool:
    return stop_event is not None and stop_event.is_set()


# ---------------------------------------------------------------------------
# Industry classification
# ---------------------------------------------------------------------------

_INDUSTRY_CACHE_FILE = os.path.join(STOCK_CACHE_DIR, ".industry_map.json")


def _fetch_industry_map(symbols: list[str]) -> dict[str, str]:
    """获取股票的行业分类 (申万一级行业), 带缓存."""
    import json

    if os.path.isfile(_INDUSTRY_CACHE_FILE):
        age_h = (time.time() - os.path.getmtime(_INDUSTRY_CACHE_FILE)) / 3600
        if age_h < _INDUSTRY_CACHE_HOURS:
            try:
                with open(_INDUSTRY_CACHE_FILE, encoding="utf-8") as f:
                    cached = json.load(f)
                hit = {s: cached[s] for s in symbols if s in cached}
                if len(hit) > len(symbols) * 0.5:
                    log.info("行业缓存命中 %d/%d", len(hit), len(symbols))
                    for s in symbols:
                        if s not in hit:
                            hit[s] = _FALLBACK_INDUSTRY
                    return hit
            except Exception:
                pass

    import akshare as ak
    industry_map = {}
    try:
        df = ak.stock_board_industry_name_em()
        if df is not None and not df.empty:
            board_names = df["板块名称"].tolist()
            for board in board_names:
                try:
                    members = ak.stock_board_industry_cons_em(symbol=board)
                    if members is not None and not members.empty:
                        code_col = "代码" if "代码" in members.columns else members.columns[1]
                        for code in members[code_col]:
                            code_str = str(code).zfill(6)
                            if code_str in symbols or len(industry_map) < 5000:
                                industry_map[code_str] = board
                    time.sleep(0.2)
                except Exception:
                    continue
    except Exception as e:
        log.warning("获取行业分类失败: %s, 使用 AKShare 个股信息备用", e)
        industry_map = _fetch_industry_fallback(symbols)

    os.makedirs(os.path.dirname(_INDUSTRY_CACHE_FILE), exist_ok=True)
    try:
        with open(_INDUSTRY_CACHE_FILE, "w", encoding="utf-8") as f:
            json.dump(industry_map, f, ensure_ascii=False)
    except Exception:
        pass

    result = {}
    for s in symbols:
        result[s] = industry_map.get(s, _FALLBACK_INDUSTRY)
    return result


def _fetch_industry_fallback(symbols: list[str]) -> dict[str, str]:
    """备用: 通过个股信息获取行业."""
    import akshare as ak
    result = {}
    for sym in symbols[:50]:
        try:
            info = ak.stock_individual_info_em(symbol=sym)
            if info is not None and not info.empty:
                for _, row in info.iterrows():
                    if "行业" in str(row.iloc[0]):
                        result[sym] = str(row.iloc[1])
                        break
            time.sleep(0.15)
        except Exception:
            continue
    return result


# ---------------------------------------------------------------------------
# Batch history fetching
# ---------------------------------------------------------------------------

def _fetch_batch_history(
    symbols: list[str],
    lookback_days: int,
    stop_event=None,
) -> dict[str, pd.DataFrame]:
    """批量获取候选股历史行情, 复用 fetch_market_data 的已有缓存."""
    import akshare as ak

    end_date = datetime.now().strftime("%Y%m%d")
    start_date = (datetime.now() - timedelta(days=int(lookback_days * 1.5))).strftime("%Y%m%d")

    result = {}
    total = len(symbols)

    for i, sym in enumerate(symbols):
        if _should_stop(stop_event):
            break

        csv_path = os.path.join(STOCK_DATA_DIR, sym, "daily.csv")
        df = None

        if os.path.isfile(csv_path):
            age_h = (time.time() - os.path.getmtime(csv_path)) / 3600
            if age_h < 12:
                try:
                    df = pd.read_csv(csv_path, encoding="utf-8-sig")
                    if len(df) >= _MIN_HISTORY:
                        df = _normalize_columns(df)
                        result[sym] = df.tail(lookback_days + 10)
                        continue
                except Exception:
                    df = None

        try:
            df = ak.stock_zh_a_hist(
                symbol=sym, period="daily",
                start_date=start_date, end_date=end_date, adjust="qfq",
            )
            if df is not None and len(df) >= _MIN_HISTORY:
                df = _normalize_columns(df)
                result[sym] = df
        except Exception as e:
            log.debug("获取 %s 历史数据失败: %s", sym, e)

        if (i + 1) % 20 == 0:
            log.info("批量获取进度: %d/%d", i + 1, total)
        time.sleep(_BATCH_DELAY)

    return result


def _normalize_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Normalize AKShare / CSV columns to lowercase English names."""
    col_map = {
        "日期": "date", "开盘": "open", "收盘": "close",
        "最高": "high", "最低": "low", "成交量": "volume",
        "成交额": "amount", "振幅": "amplitude", "涨跌幅": "pct_change",
        "涨跌额": "price_change", "换手率": "turnover_rate",
    }
    df = df.rename(columns=col_map)
    for col in ["open", "close", "high", "low", "volume", "amount", "pct_change", "turnover_rate"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")
    if "date" in df.columns:
        df["date"] = pd.to_datetime(df["date"], errors="coerce").dt.strftime("%Y-%m-%d")
    return df


# ---------------------------------------------------------------------------
# Cross-sectional feature engineering
# ---------------------------------------------------------------------------

def _compute_single_stock_features(df: pd.DataFrame) -> pd.DataFrame:
    """为单只股票计算时间序列特征 (不含截面特征)."""
    out = df.copy()

    for n in [1, 3, 5, 10, 20]:
        out[f"ret_{n}d"] = out["close"].pct_change(n) * 100

    if len(out) >= 14:
        delta = out["close"].diff()
        gain = delta.clip(lower=0).rolling(14).mean()
        loss = (-delta.clip(upper=0)).rolling(14).mean()
        rs = gain / loss.replace(0, np.nan)
        out["rsi_14"] = 100 - 100 / (1 + rs)
        out["rsi_delta"] = out["rsi_14"].diff()

    if len(out) >= 26:
        ema12 = out["close"].ewm(span=12, adjust=False).mean()
        ema26 = out["close"].ewm(span=26, adjust=False).mean()
        macd_line = ema12 - ema26
        signal_line = macd_line.ewm(span=9, adjust=False).mean()
        out["macd_hist"] = macd_line - signal_line
        out["macd_hist_delta"] = out["macd_hist"].diff()

    if "high" in out.columns and "low" in out.columns and len(out) >= 14:
        tr = pd.concat([
            out["high"] - out["low"],
            (out["high"] - out["close"].shift(1)).abs(),
            (out["low"] - out["close"].shift(1)).abs(),
        ], axis=1).max(axis=1)
        out["atr_pct"] = tr.rolling(14).mean() / out["close"] * 100

    out["volatility_20d"] = out["close"].pct_change().rolling(20).std() * 100 * np.sqrt(252)

    for n, name in [(5, "ma5"), (20, "ma20"), (60, "ma60")]:
        if len(out) >= n:
            out[name] = out["close"].rolling(n).mean()
            out[f"dist_{name}"] = (out["close"] - out[name]) / out[name] * 100

    if "ma5" in out.columns and "ma20" in out.columns:
        out["ma5_ma20_spread"] = (out["ma5"] - out["ma20"]) / out["ma20"] * 100

    if "volume" in out.columns:
        vol_ma20 = out["volume"].rolling(20).mean().replace(0, np.nan)
        out["vol_ratio_20"] = out["volume"] / vol_ma20
        out["vol_change_5d"] = out["volume"].pct_change(5) * 100

    o, h, l, c = out["open"], out["high"], out["low"], out["close"]
    body = (c - o).abs()
    total_range = (h - l).replace(0, np.nan)
    out["body_ratio"] = body / total_range
    out["upper_shadow_ratio"] = (h - pd.concat([o, c], axis=1).max(axis=1)) / total_range

    if "turnover_rate" not in out.columns:
        out["turnover_rate"] = 0.0

    return out


def _build_cross_sectional_features(
    all_hist: dict[str, pd.DataFrame],
    industry_map: dict[str, str],
) -> tuple[pd.DataFrame | None, pd.DataFrame | None, list[str]]:
    """构建截面特征矩阵 + 当日特征.

    Returns:
        (train_val_df, today_df, feature_cols)
        train_val_df: 历史截面样本 (含 date, symbol, features, alpha, qid)
        today_df: 当日截面特征 (含 symbol, features)
    """
    stock_features = {}
    for sym, raw_df in all_hist.items():
        feat_df = _compute_single_stock_features(raw_df)
        stock_features[sym] = feat_df

    all_dates = set()
    for df in stock_features.values():
        if "date" in df.columns:
            all_dates.update(df["date"].dropna().unique())
    all_dates = sorted(all_dates)

    if len(all_dates) < _MIN_HISTORY:
        log.warning("日期不足 %d < %d", len(all_dates), _MIN_HISTORY)
        return None, None, []

    rows = []
    for dt in all_dates:
        day_data = []
        for sym, feat_df in stock_features.items():
            mask = feat_df["date"] == dt
            if mask.sum() == 0:
                continue
            row = feat_df[mask].iloc[-1].to_dict()
            row["symbol"] = sym
            row["industry"] = industry_map.get(sym, _FALLBACK_INDUSTRY)
            day_data.append(row)

        if len(day_data) < 5:
            continue

        day_df = pd.DataFrame(day_data)
        _add_cross_sectional_features(day_df)
        _add_alpha_target(day_df)

        for _, r in day_df.iterrows():
            r_dict = r.to_dict()
            r_dict["date"] = dt
            rows.append(r_dict)

    if not rows:
        return None, None, []

    full_df = pd.DataFrame(rows)

    date_list = sorted(full_df["date"].unique())
    today = date_list[-1]
    today_df = full_df[full_df["date"] == today].copy()

    hist_dates = date_list[:-1]
    hist_df = full_df[full_df["date"].isin(hist_dates)].copy()

    feature_cols = [c for c in _FEATURE_COLS if c in hist_df.columns]

    date_to_qid = {d: i for i, d in enumerate(sorted(hist_df["date"].unique()))}
    hist_df["qid"] = hist_df["date"].map(date_to_qid)

    return hist_df, today_df, feature_cols


def _add_cross_sectional_features(day_df: pd.DataFrame):
    """为单个截面(同一天)添加相对排名特征."""
    n = len(day_df)
    if n < 2:
        return

    if "ret_1d" in day_df.columns:
        day_df["cs_ret_rank"] = day_df["ret_1d"].rank(pct=True, na_option="keep")

    if "volume" in day_df.columns:
        day_df["cs_vol_rank"] = day_df["volume"].rank(pct=True, na_option="keep")

    if "turnover_rate" in day_df.columns:
        day_df["cs_turnover_rank"] = day_df["turnover_rate"].rank(pct=True, na_option="keep")


def _add_alpha_target(day_df: pd.DataFrame):
    """计算 Alpha 目标并转换为排序相关度等级 (0-4).

    XGBoost rank:pairwise 需要非负整数标签 (relevance grade).
    Alpha = 个股 T 日收益 - 所在行业 T 日平均收益.
    模型学习 T-1 特征 → T 日相对强弱的映射.

    相关度等级:
      4: Alpha 极强 (> 75th percentile)
      3: Alpha 较强 (50th ~ 75th)
      2: Alpha 中性 (25th ~ 50th)
      1: Alpha 较弱 (10th ~ 25th)
      0: Alpha 极弱 (< 10th percentile)
    """
    if "ret_1d" not in day_df.columns:
        day_df["alpha"] = 0.0
        day_df["relevance"] = 2
        return

    industry_mean = day_df.groupby("industry")["ret_1d"].transform("mean")
    day_df["alpha"] = day_df["ret_1d"] - industry_mean
    day_df["alpha"] = day_df["alpha"].fillna(0.0)

    alpha = day_df["alpha"]
    p10 = alpha.quantile(0.10)
    p25 = alpha.quantile(0.25)
    p50 = alpha.quantile(0.50)
    p75 = alpha.quantile(0.75)

    day_df["relevance"] = 2
    day_df.loc[alpha < p10, "relevance"] = 0
    day_df.loc[(alpha >= p10) & (alpha < p25), "relevance"] = 1
    day_df.loc[(alpha >= p25) & (alpha < p50), "relevance"] = 2
    day_df.loc[(alpha >= p50) & (alpha < p75), "relevance"] = 3
    day_df.loc[alpha >= p75, "relevance"] = 4


# ---------------------------------------------------------------------------
# Model training
# ---------------------------------------------------------------------------

def _train_ranker(
    train_df: pd.DataFrame,
    feature_cols: list[str],
) -> tuple:
    """训练 XGBoost rank:pairwise 模型.

    Returns:
        (model, val_ndcg) or (None, 0) on failure.
    """
    import xgboost as xgb

    dates = sorted(train_df["date"].unique())
    n_dates = len(dates)

    if n_dates < _TRAIN_DAYS + 5:
        log.warning("训练日期不足: %d < %d", n_dates, _TRAIN_DAYS + 5)
        return None, 0

    split_idx = max(n_dates - _VAL_DAYS, _TRAIN_DAYS)
    train_dates = dates[:split_idx]
    val_dates = dates[split_idx:]

    t_df = train_df[train_df["date"].isin(train_dates)].copy()
    v_df = train_df[train_df["date"].isin(val_dates)].copy()

    if len(t_df) < 50 or len(v_df) < 10:
        log.warning("数据量不足: train=%d, val=%d", len(t_df), len(v_df))
        return None, 0

    X_train = t_df[feature_cols].replace([np.inf, -np.inf], np.nan)
    y_train = t_df["relevance"].astype(int).values
    qid_train = t_df["qid"].values

    date_to_qid_val = {d: i for i, d in enumerate(sorted(v_df["date"].unique()))}
    v_df["qid"] = v_df["date"].map(date_to_qid_val)
    X_val = v_df[feature_cols].replace([np.inf, -np.inf], np.nan)
    y_val = v_df["relevance"].astype(int).values
    qid_val = v_df["qid"].values

    medians = X_train.median()
    X_train = X_train.fillna(medians)
    X_val = X_val.fillna(medians)

    dtrain = xgb.DMatrix(X_train, label=y_train)
    dtrain.set_group(_qid_to_groups(qid_train))

    dval = xgb.DMatrix(X_val, label=y_val)
    dval.set_group(_qid_to_groups(qid_val))

    params = {
        "objective": "rank:pairwise",
        "max_depth": _XGB_PARAMS["max_depth"],
        "eta": _XGB_PARAMS["learning_rate"],
        "min_child_weight": _XGB_PARAMS["min_child_weight"],
        "subsample": _XGB_PARAMS["subsample"],
        "colsample_bytree": _XGB_PARAMS["colsample_bytree"],
        "reg_alpha": _XGB_PARAMS["reg_alpha"],
        "reg_lambda": _XGB_PARAMS["reg_lambda"],
        "eval_metric": "ndcg@10",
        "verbosity": 0,
    }

    evals_result = {}
    try:
        model = xgb.train(
            params, dtrain,
            num_boost_round=_XGB_PARAMS["n_estimators"],
            evals=[(dtrain, "train"), (dval, "val")],
            early_stopping_rounds=20,
            evals_result=evals_result,
            verbose_eval=False,
        )
    except Exception as e:
        log.error("XGBoost 训练失败: %s", e)
        return None, 0

    val_ndcg = 0.0
    try:
        val_scores = evals_result.get("val", {}).get("ndcg@10", [])
        if val_scores:
            val_ndcg = val_scores[-1]
    except Exception:
        pass

    return model, val_ndcg


def _qid_to_groups(qids: np.ndarray) -> list[int]:
    """Convert per-sample qid array to group sizes for XGBoost."""
    groups = []
    current_qid = qids[0]
    count = 0
    for q in qids:
        if q == current_qid:
            count += 1
        else:
            groups.append(count)
            current_qid = q
            count = 1
    groups.append(count)
    return groups


# ---------------------------------------------------------------------------
# Prediction + industry neutralization
# ---------------------------------------------------------------------------

def _predict_and_neutralize(
    model,
    today_df: pd.DataFrame,
    feature_cols: list[str],
    industry_map: dict[str, str],
    top_n_per_industry: int,
) -> list[dict]:
    """用训练好的模型预测当日截面排名, 然后行业中性化."""
    import xgboost as xgb

    X_today = today_df[feature_cols].replace([np.inf, -np.inf], np.nan).fillna(0)
    dtoday = xgb.DMatrix(X_today)

    scores = model.predict(dtoday)
    today_df = today_df.copy()
    today_df["xgb_score"] = scores

    today_df["industry"] = today_df["symbol"].map(
        lambda s: industry_map.get(s, _FALLBACK_INDUSTRY)
    )

    neutralized = []
    for ind, group in today_df.groupby("industry"):
        top = group.nlargest(top_n_per_industry, "xgb_score")
        for _, row in top.iterrows():
            neutralized.append({
                "symbol": row["symbol"],
                "xgb_score": row["xgb_score"],
                "industry": ind,
                "predicted_alpha": row.get("alpha", 0),
            })

    neutralized.sort(key=lambda x: x["xgb_score"], reverse=True)
    return neutralized
