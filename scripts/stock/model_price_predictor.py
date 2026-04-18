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

_TRAIN_WINDOW = 250
_TEST_WINDOW = 5
_N_ROUNDS = 10
_MAX_FEATURES = 40
_EARLY_STOPPING_ROUNDS = 15

_TARGETS = ["close", "high", "low"]


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
            feature_df[f"target_{target}"] = feature_df[target].shift(-1)

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


def _select_top_features(df: pd.DataFrame, cols: list[str], max_n: int) -> list[str]:
    """Rank features by variance and correlation with close price, keep top N."""
    subset = df[cols].replace([np.inf, -np.inf], np.nan)
    variances = subset.var().fillna(0)

    if "close" in df.columns:
        corrs = subset.corrwith(df["close"]).abs().fillna(0)
        score = variances.rank() + corrs.rank()
    else:
        score = variances.rank()

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

    valid_cols = [c for c in feature_cols if c in df.columns]
    if len(valid_cols) < 10:
        return {"error": f"有效特征不足: {len(valid_cols)}", "symbol": symbol}

    if len(valid_cols) > _MAX_FEATURES:
        log.info("%s: 特征 %d 超过上限 %d, 进行裁剪", symbol, len(valid_cols), _MAX_FEATURES)
        valid_cols = _select_top_features(df, valid_cols, _MAX_FEATURES)

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

    for target_name in _TARGETS:
        target_col = f"target_{target_name}"
        if target_col not in df.columns:
            continue

        valid = df.dropna(subset=[target_col]).copy()
        X_all = valid[valid_cols].replace([np.inf, -np.inf], np.nan)
        y_all = valid[target_col].values

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

            X_tr = X_all.iloc[train_start:train_end].values
            y_tr = y_all[train_start:train_end]
            X_te = X_all.iloc[test_start:test_end].values
            y_te = y_all[test_start:test_end]

            X_tr, X_te, _ = _impute_fold(X_tr, X_te, valid_cols)

            model = xgb.XGBRegressor(**params)
            model.fit(X_tr, y_tr, eval_set=[(X_te, y_te)], verbose=False)
            last_model = model

            preds = model.predict(X_te)
            errors = np.abs(preds - y_te)
            pct_errors = errors / np.where(y_te != 0, np.abs(y_te), 1) * 100

            if target_name == "close" and len(y_te) > 1:
                actual_dir = np.sign(np.diff(np.concatenate([[y_all[test_start - 1]], y_te])))
                pred_dir = np.sign(np.diff(np.concatenate([[y_all[test_start - 1]], preds])))
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
        X_final_raw = X_all.iloc[final_train_start:final_train_end].values
        y_final = y_all[final_train_start:final_train_end]
        final_df = pd.DataFrame(X_final_raw, columns=valid_cols)
        final_medians = final_df.median()
        final_df.fillna(final_medians, inplace=True)

        final_params = dict(params)
        final_params.pop("early_stopping_rounds", None)
        if hasattr(last_model, 'best_iteration') and last_model.best_iteration > 0:
            final_params["n_estimators"] = last_model.best_iteration + 1
        final_model = xgb.XGBRegressor(**final_params)
        final_model.fit(final_df.values, y_final, verbose=False)

        latest_raw = X_all.iloc[[-1]].copy()
        latest_raw.fillna(final_medians, inplace=True)
        pred_val = float(final_model.predict(latest_raw.values)[0])
        predictions[target_name] = round(pred_val, 2)

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
            importances = final_model.feature_importances_
            best_importances = sorted(
                [{"name": valid_cols[i], "importance": round(float(importances[i]), 4)}
                 for i in range(len(valid_cols))],
                key=lambda x: x["importance"], reverse=True
            )[:15]

        _save_model(symbol, target_name, final_model, valid_cols)

    if not predictions:
        return {"error": "所有目标训练失败", "symbol": symbol}

    current_close = float(df["close"].iloc[-1]) if "close" in df.columns else None
    change_pct = {}
    if current_close and current_close > 0:
        for k, v in predictions.items():
            change_pct[k] = round((v - current_close) / current_close * 100, 2)

    latest_date = ""
    if "date" in df.columns:
        latest_date = str(df["date"].iloc[-1])[:10]

    result = {
        "symbol": symbol,
        "predictions": predictions,
        "current_close": current_close,
        "change_pct": change_pct,
        "walk_forward": wf_results,
        "feature_importance": best_importances or [],
        "model_info": {
            "algorithm": "XGBoost Regressor",
            "train_window": min(_TRAIN_WINDOW, len(df) - _TEST_WINDOW - 1),
            "n_features": len(valid_cols),
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

    for target_name in ["close", "high", "low"]:
        if target_name not in wf:
            continue
        tw = wf[target_name]
        lines.append(f"## Walk-Forward 验证 — {label_map[target_name]}")
        lines.append("")
        lines.append(f"- **平均绝对误差 (MAE):** ¥{tw['overall_mae']:.2f}")
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
