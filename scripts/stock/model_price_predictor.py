"""
明日价格预测模型 — XGBoost 回归, 预测次日收盘价/最高价/最低价.

训练流程:
  1. 从 features.py 获取特征矩阵 (复用已有技术特征)
  2. 添加价格序列特征 (近N日价格变化率等)
  3. Walk-Forward 回归验证: MAE, MAPE
  4. 三个独立模型分别预测 close/high/low
  5. 输出预测价格 + 置信区间 + 历史准确率

模型持久化: C:/reports/stock/models/{symbol}/price_*.json
"""
import json
import logging
import os
import warnings
from datetime import datetime

import numpy as np
import pandas as pd

from config import STOCK_DATA_DIR, STOCK_MODELS_DIR

log = logging.getLogger(__name__)
warnings.filterwarnings("ignore", category=UserWarning)

_TRAIN_WINDOW = 500
_TEST_WINDOW = 5
_N_ROUNDS = 15
_MAX_FEATURES = 40
_EARLY_STOPPING_ROUNDS = 15

_TARGETS = ["close", "high", "low"]

# A-stock daily price limits by board
_LIMIT_PCT = {
    "main":      0.10,   # 主板 (60xxxx, 00xxxx)
    "chinext":   0.20,   # 创业板 (300xxx)
    "star":      0.20,   # 科创板 (688xxx)
    "bse":       0.30,   # 北交所 (8xxxxx, 4xxxxx)
}


def _get_price_limit(symbol: str) -> float:
    """Return the daily price limit ratio for a given A-stock symbol."""
    s = str(symbol).strip()
    if s.startswith("300"):
        return _LIMIT_PCT["chinext"]
    if s.startswith("688"):
        return _LIMIT_PCT["star"]
    if s.startswith(("8", "4")):
        return _LIMIT_PCT["bse"]
    return _LIMIT_PCT["main"]


def _clamp_prediction(pred_price: float, current_price: float, limit: float) -> float:
    """Clamp predicted price within the daily price limit range."""
    lo = current_price * (1 - limit)
    hi = current_price * (1 + limit)
    return max(lo, min(hi, pred_price))


def _build_price_features(symbol: str) -> pd.DataFrame | None:
    """Build feature matrix with price-specific regression targets."""
    from features import build_features, get_feature_names
    from technical_analysis import load_ohlcv

    feature_df = build_features(symbol)
    if feature_df is None:
        return None

    ohlcv = load_ohlcv(symbol)
    if ohlcv is None:
        return None

    feature_cols = get_feature_names()

    for col in ["close", "high", "low", "open"]:
        if col in ohlcv.columns and col not in feature_df.columns:
            feature_df = feature_df.merge(
                ohlcv[["date", col]], on="date", how="left"
            )

    _add_price_sequence_features(feature_df)
    _add_sentiment_features(feature_df)

    for target in _TARGETS:
        if target in feature_df.columns:
            feature_df[f"target_{target}"] = (
                feature_df[target].shift(-1) / feature_df["close"] - 1
            ) * 100  # percentage return relative to today's close

    new_feat_cols = [
        c for c in feature_df.columns
        if (c.startswith("price_seq_") or c.startswith("sent_"))
        and feature_df[c].notna().mean() >= 0.5
    ]
    all_feature_cols = feature_cols + sorted(new_feat_cols)

    feature_df.attrs["feature_cols"] = all_feature_cols
    return feature_df


def _add_price_sequence_features(df: pd.DataFrame):
    """Add price-series features useful for next-day regression."""
    if "close" not in df.columns:
        return

    c = df["close"]
    for n in [1, 2, 3, 5]:
        df[f"price_seq_close_lag{n}"] = c.shift(n) / c - 1

    if "high" in df.columns and "low" in df.columns:
        df["price_seq_hl_ratio"] = (df["high"] - df["low"]) / c
        df["price_seq_hl_ratio_ma5"] = df["price_seq_hl_ratio"].rolling(5).mean()

    df["price_seq_close_ma5_ratio"] = c / c.rolling(5).mean() - 1
    df["price_seq_close_ma10_ratio"] = c / c.rolling(10).mean() - 1
    df["price_seq_momentum_3d"] = c.pct_change(3)
    df["price_seq_momentum_5d"] = c.pct_change(5)

    if "volume" in df.columns:
        df["price_seq_vwap_proxy"] = (
            (df.get("high", c) + df.get("low", c) + c) / 3
        )


def _add_sentiment_features(df: pd.DataFrame):
    """Add market sentiment features (Fear & Greed, VIX) to the latest row only.
    These are point-in-time values, not historical series, so only apply to the
    prediction row to avoid look-ahead bias.
    """
    try:
        from market_sentiment import load_cached_sentiment
        cached = load_cached_sentiment()
        if not cached:
            return
        fg = cached.get("fear_greed", {}).get("value")
        vix = cached.get("vix", {}).get("value")
        last_idx = df.index[-1]
        if fg is not None:
            df["sent_fear_greed"] = np.nan
            df.at[last_idx, "sent_fear_greed"] = float(fg) / 100.0
        if vix is not None:
            df["sent_vix"] = np.nan
            df.at[last_idx, "sent_vix"] = float(vix)
    except Exception as e:
        log.debug("Sentiment features unavailable: %s", e)


def _select_top_features(df: pd.DataFrame, cols: list[str], target_series: pd.Series, max_n: int) -> list[str]:
    """Rank features by variance and correlation with target series (percentage return), keep top N."""
    subset = df[cols].replace([np.inf, -np.inf], np.nan)
    variances = subset.var().fillna(0)
    corrs = subset.corrwith(target_series).abs().fillna(0)
    score = variances.rank() + corrs.rank()

    top = score.nlargest(max_n).index.tolist()
    return top


def _impute_fold(X_train: np.ndarray, X_test: np.ndarray,
                 cols: list[str]) -> tuple[np.ndarray, np.ndarray, pd.Series]:
    """Median impute from training fold only."""
    train_df = pd.DataFrame(X_train, columns=cols)
    test_df = pd.DataFrame(X_test, columns=cols)
    medians = train_df.median()
    train_df.fillna(medians, inplace=True)
    test_df.fillna(medians, inplace=True)
    return train_df.values, test_df.values, medians


def _compute_confidence(wf_results: dict, change_pct: dict) -> dict:
    """Derive a confidence assessment from walk-forward metrics and add Chinese translations."""
    close_wf = wf_results.get("close", {})
    mae = close_wf.get("overall_mae", 99)
    dir_acc = close_wf.get("direction_accuracy")
    pred_pct = abs(change_pct.get("close", 0))

    if mae < 1.0 and dir_acc and dir_acc > 0.60:
        level = "medium"
    elif mae < 1.5 and dir_acc and dir_acc > 0.55:
        level = "low-medium"
    elif mae > 2.5 or (dir_acc and dir_acc < 0.45):
        level = "very_low"
    else:
        level = "low"

    signal_strength = "weak"
    if pred_pct > 2.0 and mae < 1.5:
        signal_strength = "moderate"
    elif pred_pct > 3.0 and mae < 2.0:
        signal_strength = "moderate"
    elif pred_pct < mae:
        signal_strength = "noise"

    # Chinese translations
    level_map_zh = {
        "medium": "中等",
        "low-medium": "中低",
        "low": "低",
        "very_low": "极低"
    }
    signal_map_zh = {
        "weak": "弱信号",
        "moderate": "中等强度",
        "noise": "高噪声"
    }

    if signal_strength == "noise":
        note_zh = "预测涨跌幅小于模型历史平均误差（MAE），处于市场随时间随机波动的噪声范围内，建议空仓守住现金，不要盲目交易。"
    elif signal_strength == "weak":
        note_zh = "预测信号偏弱，容易受到市场日内随机波动的干扰，请仅作为非主力的辅助参考。"
    else:
        note_zh = "预估变动幅度已跑赢模型历史平均误差（MAE），信号强度中等，可以结合其他技术面与基本面指标多维参考。"

    return {
        "level": level,
        "level_zh": level_map_zh.get(level, "未知"),
        "signal_strength": signal_strength,
        "signal_strength_zh": signal_map_zh.get(signal_strength, "未知"),
        "mae_pct": round(mae, 2),
        "direction_accuracy": dir_acc,
        "note": (
            "Prediction within noise range; treat as directional hint only"
            if signal_strength in ("weak", "noise")
            else "Signal exceeds noise; consider with other analysis"
        ),
        "note_zh": note_zh,
    }


def train_price_prediction(symbol: str) -> dict:
    """
    Train 3 XGBoost regressors (close, high, low) and predict next trading day.

    Returns:
    {
        "symbol": "600519",
        "predictions": {
            "close": 1680.5,
            "high": 1695.2,
            "low": 1670.8
        },
        "current_close": 1675.0,
        "change_pct": { "close": 0.33 },
        "walk_forward": {
            "close": { "mae": 12.5, "mape": 0.75, "direction_acc": 0.68, ... },
            ...
        },
        "feature_importance": [...],
        "model_info": { ... },
        "predicted_at": "2026-04-14T...",
        "latest_date": "2026-04-14"
    }
    """
    import xgboost as xgb

    df = _build_price_features(symbol)
    if df is None:
        return {"error": "特征数据不足", "symbol": symbol}

    feature_cols = df.attrs.get("feature_cols", [])
    if not feature_cols:
        return {"error": "无有效特征列", "symbol": symbol}

    raw_valid_cols = [c for c in feature_cols if c in df.columns]
    # Explicitly exclude fundamental or single-point sentiment features to prevent training NaN mismatches
    valid_cols = [
        c for c in raw_valid_cols
        if not (c.startswith("feat_") or c.startswith("sent_") or c.startswith("mood_"))
    ]

    if len(valid_cols) < 5:
        return {"error": f"有效特征不足: {len(valid_cols)}", "symbol": symbol}

    params = {
        "objective": "reg:squarederror",
        "max_depth": 4,
        "learning_rate": 0.05,
        "n_estimators": 300,
        "min_child_weight": 8,
        "subsample": 0.7,
        "colsample_bytree": 0.6,
        "reg_alpha": 0.5,
        "reg_lambda": 2.0,
        "random_state": 42,
        "verbosity": 0,
        "early_stopping_rounds": _EARLY_STOPPING_ROUNDS,
    }

    predictions = {}
    wf_results = {}
    best_importances = None
    n_features_used = None
    decay_rate = 0.002

    for target_name in _TARGETS:
        target_col = f"target_{target_name}"
        if target_col not in df.columns:
            continue

        valid = df.dropna(subset=[target_col]).copy()
        y_series = valid[target_col]

        # Full feature pool; selection happens per-fold and for the final model using
        # TRAINING data only, to avoid look-ahead leakage from future test rows.
        pool_cols = list(valid_cols)
        X_all = valid[pool_cols].replace([np.inf, -np.inf], np.nan)
        y_all = y_series.values

        n = len(X_all)
        train_size = min(_TRAIN_WINDOW, n - _TEST_WINDOW - 1)
        if train_size < 60:
            log.warning("%s/%s: 数据不足 (n=%d, train=%d)", symbol, target_name, n, train_size)
            continue

        rounds = []
        n_rounds = min(_N_ROUNDS, (n - train_size) // _TEST_WINDOW)
        if n_rounds < 1:
            n_rounds = 1

        last_model = None
        for rnd in range(n_rounds):
            offset = rnd * _TEST_WINDOW
            test_end = n - offset
            test_start = test_end - _TEST_WINDOW
            train_end = test_start
            if train_end < train_size:
                break
            train_start = train_end - train_size

            # Per-fold feature selection on the TRAINING slice only (no look-ahead)
            fold_cols = pool_cols
            if len(fold_cols) > _MAX_FEATURES:
                fold_cols = _select_top_features(
                    X_all.iloc[train_start:train_end],
                    pool_cols,
                    y_series.iloc[train_start:train_end],
                    _MAX_FEATURES,
                )

            X_tr = X_all[fold_cols].iloc[train_start:train_end].values
            y_tr = y_all[train_start:train_end]
            X_te = X_all[fold_cols].iloc[test_start:test_end].values
            y_te = y_all[test_start:test_end]

            X_tr, X_te, _ = _impute_fold(X_tr, X_te, fold_cols)

            # Recency Weighting for training samples (exponential decay weight)
            n_tr = len(X_tr)
            sample_weight = np.exp(-decay_rate * (n_tr - 1 - np.arange(n_tr)))
            sample_weight = sample_weight / np.mean(sample_weight)

            model = xgb.XGBRegressor(**params)
            model.fit(X_tr, y_tr, sample_weight=sample_weight, eval_set=[(X_te, y_te)], verbose=False)
            last_model = model

            preds = model.predict(X_te)
            errors = np.abs(preds - y_te)
            denom = np.maximum(np.abs(y_te), 0.5)
            pct_errors = errors / denom * 100

            if target_name == "close":
                actual_dir = np.sign(y_te)
                pred_dir = np.sign(preds)
                dir_correct = int((actual_dir == pred_dir).sum())
                dir_total = len(actual_dir)
            else:
                dir_correct, dir_total = 0, 0

            rounds.append({
                "round": rnd + 1,
                "mae": round(float(errors.mean()), 4),
                "mape": round(float(pct_errors.mean()), 4),
                "dir_correct": dir_correct,
                "dir_total": dir_total,
            })

        if last_model is None:
            continue

        final_train_end = n
        final_train_start = max(0, final_train_end - train_size)

        # Final-model feature selection on the final TRAINING window only — this window
        # ends before tomorrow's prediction point, so there is no look-ahead vs the forecast.
        final_cols = pool_cols
        if len(final_cols) > _MAX_FEATURES:
            log.info("%s/%s: 特征 %d 超过上限 %d, 进行裁剪", symbol, target_name, len(final_cols), _MAX_FEATURES)
            final_cols = _select_top_features(
                X_all.iloc[final_train_start:final_train_end],
                pool_cols,
                y_series.iloc[final_train_start:final_train_end],
                _MAX_FEATURES,
            )

        X_final_raw = X_all[final_cols].iloc[final_train_start:final_train_end].values
        y_final = y_all[final_train_start:final_train_end]
        final_df = pd.DataFrame(X_final_raw, columns=final_cols)
        final_medians = final_df.median()
        final_df.fillna(final_medians, inplace=True)

        final_params = dict(params)
        final_params.pop("early_stopping_rounds", None)
        if hasattr(last_model, 'best_iteration') and last_model.best_iteration > 0:
            final_params["n_estimators"] = last_model.best_iteration + 1
        final_model = xgb.XGBRegressor(**final_params)

        # Recency Weighting for final training
        n_final = len(final_df)
        final_weights = np.exp(-decay_rate * (n_final - 1 - np.arange(n_final)))
        final_weights = final_weights / np.mean(final_weights)

        final_model.fit(final_df.values, y_final, sample_weight=final_weights, verbose=False)

        # Predict TOMORROW using TODAY's features. The last row of df has a NaN target
        # (it depends on the unknown next bar) but fully-available backward-looking features.
        # Previously we predicted from X_all's last row (= df's second-to-last row), which
        # forecast the already-realized bar while the tracker scored it against tomorrow —
        # an off-by-one that collapsed direction accuracy toward random.
        latest_raw = df[final_cols].iloc[[-1]].replace([np.inf, -np.inf], np.nan)
        latest_raw = latest_raw.fillna(final_medians)
        pred_pct = float(final_model.predict(latest_raw.values)[0])
        predictions[target_name] = pred_pct  # store raw % temporarily

        overall_mae = np.mean([r["mae"] for r in rounds]) if rounds else 0
        overall_mape = np.mean([r["mape"] for r in rounds]) if rounds else 0
        dir_c = sum(r["dir_correct"] for r in rounds)
        dir_t = sum(r["dir_total"] for r in rounds)

        wf_results[target_name] = {
            "rounds": len(rounds),
            "overall_mae": round(overall_mae, 4),
            "overall_mape": round(overall_mape, 4),
            "direction_accuracy": round(dir_c / dir_t, 4) if dir_t > 0 else None,
            "details": rounds,
        }

        if target_name == "close":
            n_features_used = len(final_cols)
            importances = final_model.feature_importances_
            best_importances = sorted(
                [{"name": final_cols[i], "importance": round(float(importances[i]), 4)}
                 for i in range(len(final_cols))],
                key=lambda x: x["importance"], reverse=True
            )[:15]

        _save_model(symbol, target_name, final_model, final_cols)

    if not predictions:
        return {"error": "所有目标训练失败", "symbol": symbol}

    current_close = float(df["close"].iloc[-1]) if "close" in df.columns else None
    limit = _get_price_limit(symbol)

    change_pct = {}
    if current_close and current_close > 0:
        for k in list(predictions.keys()):
            raw_pct = predictions[k]  # model output is % return
            clamped_pct = max(-limit * 100, min(limit * 100, raw_pct))
            change_pct[k] = round(clamped_pct, 2)
            pred_price = current_close * (1 + clamped_pct / 100)
            predictions[k] = round(pred_price, 2)

        # Logical constraints check: high >= close >= low, and high >= low
        if "high" in predictions and "low" in predictions:
            if predictions["high"] < predictions["low"]:
                predictions["high"], predictions["low"] = predictions["low"], predictions["high"]
                change_pct["high"], change_pct["low"] = change_pct["low"], change_pct["high"]
            
            if "close" in predictions:
                # Clamp close within [low, high]
                if predictions["close"] > predictions["high"]:
                    predictions["close"] = predictions["high"]
                    change_pct["close"] = change_pct["high"]
                elif predictions["close"] < predictions["low"]:
                    predictions["close"] = predictions["low"]
                    change_pct["close"] = change_pct["low"]

    latest_date = ""
    if "date" in df.columns:
        latest_date = str(df["date"].iloc[-1])[:10]

    confidence = _compute_confidence(wf_results, change_pct)

    # Direction label: a flat 0% forecast is "震荡"; a non-zero move within the model's
    # own historical error band (signal_strength == "noise") is "方向不确定"; otherwise 看涨/看跌.
    close_pct = change_pct.get("close", 0)
    if close_pct == 0:
        direction_label = "震荡"
    elif confidence.get("signal_strength") == "noise":
        direction_label = "方向不确定"
    elif close_pct > 0:
        direction_label = "看涨"
    else:
        direction_label = "看跌"

    result = {
        "symbol": symbol,
        "predictions": predictions,
        "current_close": current_close,
        "change_pct": change_pct,
        "direction_label": direction_label,
        "confidence": confidence,
        "walk_forward": wf_results,
        "feature_importance": best_importances or [],
        "model_info": {
            "algorithm": "XGBoost Regressor (Time Weighted)",
            "train_window": min(_TRAIN_WINDOW, len(df) - _TEST_WINDOW - 1),
            "n_features": n_features_used or len(valid_cols),
            "n_feature_pool": len(valid_cols),
            "wf_note": "验证指标基于逐折重选特征计算，与最终模型特征子集可能不同，仅供诊断参考。",
            "n_data_rows": len(df),
            "targets": list(predictions.keys()),
            "predicted_at": datetime.now().isoformat(),
        },
        "latest_date": latest_date,
    }

    _save_prediction(symbol, result)
    return result


def _save_model(symbol: str, target: str, model, feature_cols: list[str]):
    model_dir = os.path.join(STOCK_MODELS_DIR, symbol)
    os.makedirs(model_dir, exist_ok=True)
    model.save_model(os.path.join(model_dir, f"price_{target}_model.json"))


def _save_prediction(symbol: str, result: dict):
    data_dir = os.path.join(STOCK_DATA_DIR, symbol)
    os.makedirs(data_dir, exist_ok=True)
    path = os.path.join(data_dir, "price_prediction.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    log.info("价格预测已保存 → %s", path)


def generate_price_prediction_deepseek(symbol: str, xgb_result: dict) -> dict:
    """
    Use DeepSeek to analyze market factors, technicals, fundamentals, sentiment,
    and audit/calibrate the numerical XGBoost predictions.
    """
    from config import call_deepseek, get_deepseek_key
    if not get_deepseek_key():
        log.warning("No DeepSeek key configured, skipping DeepSeek calibration for %s", symbol)
        placeholder = {
            "reasoning_report": "未配置 DeepSeek API Key，已跳過專家校準與深度推理。",
            "calibrated_predictions": xgb_result.get("predictions"),
            "calibrated_change_pct": xgb_result.get("change_pct"),
            "confidence_score": 0,
            "take_profit_target": None,
            "stop_loss_target": None,
            "calibration_status": "skipped_no_key"
        }
        xgb_result["deepseek"] = placeholder
        _save_prediction(symbol, xgb_result)
        return placeholder

    # 1. Fetch latest data (K-lines)
    from technical_analysis import load_ohlcv
    ohlcv = load_ohlcv(symbol)
    if ohlcv is None or ohlcv.empty:
        placeholder = {
            "reasoning_report": "無法獲取行情數據，無法進行專家校準與深度推理。",
            "calibrated_predictions": xgb_result.get("predictions"),
            "calibrated_change_pct": xgb_result.get("change_pct"),
            "confidence_score": 0,
            "take_profit_target": None,
            "stop_loss_target": None,
            "calibration_status": "api_error"
        }
        xgb_result["deepseek"] = placeholder
        _save_prediction(symbol, xgb_result)
        return placeholder
    recent_k = ohlcv.tail(20).copy()
    if "date" in recent_k.columns:
        recent_k["date"] = recent_k["date"].astype(str)
    recent_k_summary = recent_k[["date", "open", "high", "low", "close", "volume"]].to_dict(orient="records")

    # 2. Fetch fundamentals
    import os
    import json
    from config import STOCK_DATA_DIR
    fund_path = os.path.join(STOCK_DATA_DIR, symbol, "fundamentals.json")
    fundamentals = {}
    if os.path.isfile(fund_path):
        try:
            with open(fund_path, encoding="utf-8") as f:
                fundamentals = json.load(f)
        except Exception:
            pass

    # 3. Fetch sentiment
    from market_sentiment import load_cached_sentiment
    sentiment = load_cached_sentiment() or {}

    # 4. Fetch fund flow signals
    from china_market_data import stock_fund_flow_signals
    ff_signals = {}
    try:
        ff_signals = stock_fund_flow_signals(symbol)
    except Exception:
        pass

    # 5. Build prompt
    system_prompt = (
        "你是一名顶尖的量化投资经理与A股盘口专家。你的职责是结合机器計量結果（XGBoost）、近期K線走勢、個股資金流、"
        "公司基本面以及大盤宏觀情緒，審計並校準明日的收盤價、最高價、最低價，提供最具實戰價值的決策反饋。\n\n"
        "工作流規則：\n"
        "1. 審核：判斷 XGBoost 給出的預測方向是否合理。考慮大盤情緒（VIX、恐慌指數）、個股主力資金流入、北向動向、基本面估值（PE/PB是否過高）以及技術面阻力支撑位。\n"
        "2. 校準：如果 XGBoost 預測大漲，但上方有均線重壓、主力在撤退、或者大盤情緒極差，你應當保守地向下校準預測區間。反之，如果預測看空，但底部支撐強勁且主力搶籌，你應當向上校準。\n"
        "3. 輸出：給出校準後的明日收盘价、最高价、最低价。同時給出交易建議（止盈止損、衝高失敗退場預案、置信度等）。\n"
        "4. **格式要求**：你必須在分析報告的**最後**，輸出一個帶有 `[CALIBRATION_JSON]` 標記的 JSON 數據塊，格式必須嚴格如下，以便系統自動解析：\n"
        "```json\n"
        "{\n"
        "  \"calibrated_predictions\": {\n"
        "    \"close\": 12.34,\n"
        "    \"high\": 12.50,\n"
        "    \"low\": 12.10\n"
        "  },\n"
        "  \"calibrated_change_pct\": {\n"
        "    \"close\": 1.20,\n"
        "    \"high\": 2.51,\n"
        "    \"low\": -0.77\n"
        "  },\n"
        "  \"confidence_score\": 85,\n"
        "  \"take_profit_target\": 12.80,\n"
        "  \"stop_loss_target\": 11.90\n"
        "}\n"
        "```\n"
        "注意：JSON中的價格必須是絕對價格（¥），change_pct是相對今日收盤價的變動百分比（%）。不可輸出其他無效字元。"
    )

    user_prompt = f"""請針對股票 {symbol} 進行明日價格審計與校準分析。

【1. 當前與 XGBoost 量化預測數據】
- 今日收盤價: ¥{xgb_result.get('current_close')}
- XGBoost 預測收盤價: ¥{xgb_result.get('predictions', {}).get('close')} ({xgb_result.get('change_pct', {}).get('close', 0):+.2f}%)
- XGBoost 預測最高價: ¥{xgb_result.get('predictions', {}).get('high')} ({xgb_result.get('change_pct', {}).get('high', 0):+.2f}%)
- XGBoost 預測最低價: ¥{xgb_result.get('predictions', {}).get('low')} ({xgb_result.get('change_pct', {}).get('low', 0):+.2f}%)
- ML 模型歷史 MAE (收盤): {xgb_result.get('confidence', {}).get('mae_pct')}%
- ML 模型歷史方向準確率: {((xgb_result.get('confidence', {}) or {}).get('direction_accuracy') or 0)*100:.1f}%
- 信噪比狀態: {xgb_result.get('confidence', {}).get('signal_strength')}

【2. 近期 20 日 K 線數據 (OHLCV)】
{json.dumps(recent_k_summary, ensure_ascii=False, indent=2)}

【3. 資金流向與北向數據】
- 主力 3 日淨流入: {ff_signals.get('main_net_3d', 0)} 萬元
- 主力 10 日淨流入: {ff_signals.get('main_net_10d', 0)} 萬元
- 超大单流入佔比: {ff_signals.get('super_large_ratio', 0)*100:.1f}%
- 資金佈局得分: {ff_signals.get('accumulation_score', 0)}/100

【4. 公司基本面數據】
{json.dumps(fundamentals, ensure_ascii=False, indent=2)}

【5. 大盤宏觀情緒】
- 恐慌與貪婪指數: {sentiment.get('fear_greed', {}).get('value', 'N/A')} ({sentiment.get('fear_greed', {}).get('label', 'N/A')})
- VIX 波動率指數: {sentiment.get('vix', {}).get('value', 'N/A')}

請進行多維度深度交叉审计，給出：
1. 技術面阻力位與支撐位研判
2. XGBoost 預測合理性分析與方向修正邏輯
3. 校準後的預測價格區間
4. 交易紀律與防禦退場預案（開盤半小時衝高失敗退場紀律）
最後，請確保嚴格按照 `[CALIBRATION_JSON]` 要求輸出 JSON。
"""

    log.info("DeepSeek 專家審計啟動: %s", symbol)
    resp = call_deepseek(system_prompt, user_prompt, max_tokens=3000, reasoning_effort="high")
    if not resp.get("ok"):
        log.error("DeepSeek 校準調用失敗: %s", resp.get("error"))
        error_msg = resp.get("error", "未知錯誤")
        placeholder = {
            "reasoning_report": f"DeepSeek API 調用失敗: {error_msg}，已回退至機器學習預測。",
            "calibrated_predictions": xgb_result.get("predictions"),
            "calibrated_change_pct": xgb_result.get("change_pct"),
            "confidence_score": 0,
            "take_profit_target": None,
            "stop_loss_target": None,
            "calibration_status": "api_error"
        }
        xgb_result["deepseek"] = placeholder
        _save_prediction(symbol, xgb_result)
        return placeholder

    content = resp.get("content", "")
    reasoning = resp.get("reasoning_content", "")

    # Save reasoning report
    ds_report_path = os.path.join(STOCK_DATA_DIR, symbol, "price-prediction-report-deepseek.md")
    try:
        with open(ds_report_path, "w", encoding="utf-8") as f:
            f.write(f"# {symbol} DeepSeek 專家校準與推理報告\n\n")
            if reasoning:
                f.write(f"## 🧠 深度思維過程 (Chain-of-thought)\n\n{reasoning}\n\n---\n\n")
            f.write(f"## 📝 專家審計分析\n\n{content}")
    except Exception as re_err:
        log.warning("Failed to save DeepSeek markdown report: %s", re_err)

    # Parse JSON block
    cal_data = {}
    calibration_applied = False
    try:
        import re
        # Find json block
        json_str = ""
        if "[CALIBRATION_JSON]" in content:
            parts = content.split("[CALIBRATION_JSON]", 1)
            json_search_text = parts[1]
        else:
            json_search_text = content

        # Try to match ```json ... ``` block
        match = re.search(r"```json\s*(\{.*?\}|\[.*?\])\s*```", json_search_text, re.DOTALL)
        if match:
            json_str = match.group(1)
        else:
            # Try to match first { to last }
            brace_match = re.search(r"(\{.*\})", json_search_text, re.DOTALL)
            if brace_match:
                json_str = brace_match.group(1)

        if json_str:
            try:
                cal_data = json.loads(json_str)
                calibration_applied = True
            except json.JSONDecodeError:
                pass

        # Fallback: scan all JSON-like blocks from the bottom
        if not cal_data:
            matches = re.findall(r"(\{.*?\})", content, re.DOTALL)
            for m in reversed(matches):
                try:
                    parsed = json.loads(m)
                    if "calibrated_predictions" in parsed or "calibrated_change_pct" in parsed:
                        cal_data = parsed
                        calibration_applied = True
                        break
                except Exception:
                    pass
    except Exception as e:
        log.warning("解析 DeepSeek 校準 JSON 失敗: %s", e)

    # Validate and clamp LLM-calibrated prices to preserve physical consistency and price limits
    current_close = xgb_result.get("current_close")
    limit = _get_price_limit(symbol)

    if current_close and current_close > 0:
        # Resolve prices
        if not cal_data or "calibrated_predictions" not in cal_data or not isinstance(cal_data["calibrated_predictions"], dict):
            cal_predictions = xgb_result.get("predictions", {}).copy()
        else:
            cal_predictions = {}
            for k in ["close", "high", "low"]:
                val = cal_data["calibrated_predictions"].get(k)
                if val is not None:
                    try:
                        cal_predictions[k] = float(val)
                    except (ValueError, TypeError):
                        cal_predictions[k] = float(xgb_result.get("predictions", {}).get(k, current_close))
                else:
                    cal_predictions[k] = float(xgb_result.get("predictions", {}).get(k, current_close))

        # Clamp absolute prices to daily limit (e.g. ±10% for Main Board, ±20% for STAR/ChiNext)
        min_price = round(current_close * (1 - limit), 2)
        max_price = round(current_close * (1 + limit), 2)
        for k in ["close", "high", "low"]:
            if k in cal_predictions:
                cal_predictions[k] = max(min_price, min(max_price, round(cal_predictions[k], 2)))

        # Enforce physical constraints: high >= low, and close is bounded by [low, high]
        if "high" in cal_predictions and "low" in cal_predictions:
            if cal_predictions["high"] < cal_predictions["low"]:
                cal_predictions["high"], cal_predictions["low"] = cal_predictions["low"], cal_predictions["high"]
            
            if "close" in cal_predictions:
                if cal_predictions["close"] > cal_predictions["high"]:
                    cal_predictions["close"] = cal_predictions["high"]
                elif cal_predictions["close"] < cal_predictions["low"]:
                    cal_predictions["close"] = cal_predictions["low"]

        # Recompute exact calibrated change percentages to match clamped absolute prices
        cal_change_pct = {}
        for k in ["close", "high", "low"]:
            if k in cal_predictions:
                cal_change_pct[k] = round(((cal_predictions[k] / current_close) - 1) * 100, 2)
    else:
        # Fallback if no current_close
        cal_predictions = xgb_result.get("predictions", {}).copy()
        cal_change_pct = xgb_result.get("change_pct", {}).copy()

    result = {
        "reasoning_report": content,
        "calibrated_predictions": cal_predictions,
        "calibrated_change_pct": cal_change_pct,
        "confidence_score": cal_data.get("confidence_score", 50) if calibration_applied else 50,
        "take_profit_target": cal_data.get("take_profit_target") if calibration_applied else None,
        "stop_loss_target": cal_data.get("stop_loss_target") if calibration_applied else None,
        "calibration_status": "applied" if calibration_applied else "parse_failed"
    }

    # Save to price_prediction.json
    xgb_result["deepseek"] = result
    _save_prediction(symbol, xgb_result)
    log.info("DeepSeek 專家審計完成並合併保存至 price_prediction.json，狀態: %s", result["calibration_status"])
    return result


def load_price_prediction(symbol: str) -> dict | None:
    path = os.path.join(STOCK_DATA_DIR, symbol, "price_prediction.json")
    if os.path.isfile(path):
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    return None


def generate_price_report(symbol: str, result: dict | None = None) -> str:
    """Generate Chinese Markdown report for price prediction."""
    if result is None:
        result = load_price_prediction(symbol)
    if result is None:
        return "## 明日价格预测\n\n**暂无预测数据**, 请先运行训练。"

    if "error" in result:
        return f"## 明日价格预测\n\n**错误:** {result['error']}"

    preds = result.get("predictions", {})
    current = result.get("current_close")
    chg = result.get("change_pct", {})
    wf = result.get("walk_forward", {})
    feats = result.get("feature_importance", [])
    info = result.get("model_info", {})

    lines = [f"# {symbol} 明日价格预测", ""]

    if preds.get("close"):
        direction_label = result.get("direction_label")
        if direction_label:
            icon = {"看涨": "🔺", "看跌": "🔻", "震荡": "➖", "方向不确定": "❓"}.get(direction_label, "➖")
            lines.append(f"> {icon} 预测方向: **{direction_label}** | 当前价: ¥{current}")
        else:
            direction = "涨" if chg.get("close", 0) > 0 else "跌" if chg.get("close", 0) < 0 else "平"
            icon = {"涨": "🟢", "跌": "🔴", "平": "⚪"}[direction]
            lines.append(f"> {icon} 预测方向: **{direction}** | 当前价: ¥{current}")
        lines.append("")

    lines.append("## 预测价格")
    lines.append("")
    lines.append("| 指标 | 预测价 | 预期涨跌 |")
    lines.append("|------|--------|----------|")
    label_map = {"close": "收盘价", "high": "最高价", "low": "最低价"}
    for k in ["close", "high", "low"]:
        if k in preds:
            c = chg.get(k, 0)
            sign = "+" if c > 0 else ""
            color_hint = "↑" if c > 0 else "↓" if c < 0 else "→"
            lines.append(f"| **{label_map[k]}** | ¥{preds[k]:.2f} | {sign}{c:.2f}% {color_hint} |")
    lines.append("")

    if preds.get("high") and preds.get("low"):
        lines.append(f"> 预测波动区间: **¥{preds['low']:.2f} ~ ¥{preds['high']:.2f}**")
        lines.append("")

    conf = result.get("confidence", {})
    if conf:
        level_map = {
            "medium": "⚠️ 中等", "low-medium": "⚠️ 中低",
            "low": "❗ 低", "very_low": "🚫 极低",
        }
        lines.append("## 置信度评估")
        lines.append("")
        lines.append(f"- **置信等级:** {level_map.get(conf.get('level', ''), conf.get('level', 'N/A'))}")
        lines.append(f"- **信号强度:** {conf.get('signal_strength', 'N/A')}")
        lines.append(f"- **说明:** {conf.get('note', '')}")
        lines.append("")

    for target_name in ["close", "high", "low"]:
        if target_name not in wf:
            continue
        tw = wf[target_name]
        lines.append(f"## Walk-Forward 验证 — {label_map[target_name]}")
        lines.append("")
        lines.append(f"- **平均绝对误差 (MAE):** {tw['overall_mae']:.2f} 个百分点")
        lines.append(f"- **平均百分比误差 (MAPE):** {tw['overall_mape']:.2f}%")
        if tw.get("direction_accuracy") is not None:
            lines.append(f"- **方向准确率:** {tw['direction_accuracy']:.1%}")
        lines.append("")

    if feats:
        lines.append("## 关键特征")
        lines.append("")
        lines.append("| 排名 | 特征 | 重要性 |")
        lines.append("|------|------|--------|")
        for i, f in enumerate(feats[:10]):
            bar = "█" * max(1, int(f["importance"] * 50))
            lines.append(f"| {i+1} | {f['name']} | {f['importance']:.3f} {bar} |")
        lines.append("")

    lines.append("## 模型信息")
    lines.append("")
    lines.append(f"- 算法: {info.get('algorithm', 'XGBoost')}")
    lines.append(f"- 训练窗口: {info.get('train_window', 'N/A')} 交易日")
    lines.append(f"- 特征数: {info.get('n_features', 'N/A')}")
    lines.append(f"- 预测时间: {info.get('predicted_at', '')[:16]}")
    lines.append("")

    lines.append("---")
    lines.append("*注意: 价格预测仅供参考, 股市有风险, 投资需谨慎。模型误差可能很大。*")

    report = "\n".join(lines)

    report_path = os.path.join(STOCK_DATA_DIR, symbol, "price-prediction-report.md")
    with open(report_path, "w", encoding="utf-8") as f:
        f.write(report)

    return report


if __name__ == "__main__":
    import sys
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    sym = sys.argv[1] if len(sys.argv) > 1 else "600519"
    result = train_price_prediction(sym)
    if "error" in result:
        print(f"错误: {result['error']}")
    else:
        preds = result["predictions"]
        print(f"\n{sym} 明日价格预测:")
        for k, v in preds.items():
            chg = result["change_pct"].get(k, 0)
            print(f"  {k}: ¥{v:.2f} ({'+' if chg > 0 else ''}{chg:.2f}%)")

    print("\n" + generate_price_report(sym, result))
