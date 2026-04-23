"""
择时模型 — 双 XGBoost 分类器 (买入信号 + 退出信号).

核心逻辑:
  买入信号模型: 预测未来3日最高价 > T+1开盘价 3% (有上涨空间)
  退出信号模型: 预测未来5日最大回撤 > 5% (有下跌风险)

  综合信号:
    买入=True  + 退出=False → 买入
    买入=True  + 退出=True  → 观望偏多
    买入=False + 退出=False → 观望
    买入=False + 退出=True  → 回避

训练方式:
  Walk-Forward 验证, 手动触发, 保存模型到 STOCK_MODELS_DIR/{symbol}/timing/

依赖:
  features.py (特征矩阵) + china_market_data.py (A股数据)
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

_TRAIN_WINDOW = 400
_TEST_WINDOW = 5
_MIN_DATA_ROWS = 200
_N_WF_ROUNDS = 12
_EARLY_STOPPING = 15

_BUY_THRESHOLD_PCT = 3.0
_EXIT_DRAWDOWN_PCT = 5.0
_BUY_HORIZON = 3
_EXIT_HORIZON = 5


def _model_dir(symbol: str) -> str:
    d = os.path.join(STOCK_MODELS_DIR, symbol, "timing")
    os.makedirs(d, exist_ok=True)
    return d


def _build_timing_targets(df: pd.DataFrame) -> pd.DataFrame:
    """Build buy/exit binary targets from OHLCV data.

    buy_target:  1 if max(high[t+1..t+3]) / open[t+1] - 1 > BUY_THRESHOLD_PCT
    exit_target: 1 if max-drawdown from close[t] over [t+1..t+5] > EXIT_DRAWDOWN_PCT
    """
    n = len(df)
    buy_t = np.zeros(n, dtype=int)
    exit_t = np.zeros(n, dtype=int)

    highs = df["high"].values if "high" in df.columns else None
    lows = df["low"].values if "low" in df.columns else None
    opens = df["open"].values if "open" in df.columns else None
    closes = df["close"].values if "close" in df.columns else None

    if highs is None or lows is None or opens is None or closes is None:
        df["buy_target"] = np.nan
        df["exit_target"] = np.nan
        return df

    for i in range(n):
        if i + _BUY_HORIZON + 1 >= n:
            buy_t[i] = -1
            exit_t[i] = -1
            continue

        t1_open = opens[i + 1]
        if t1_open <= 0:
            continue

        future_max_high = max(highs[i + 1: i + 1 + _BUY_HORIZON])
        gain_pct = (future_max_high / t1_open - 1) * 100
        buy_t[i] = 1 if gain_pct >= _BUY_THRESHOLD_PCT else 0

        entry_price = closes[i]
        if entry_price <= 0:
            continue
        future_lows = lows[i + 1: i + 1 + _EXIT_HORIZON]
        if len(future_lows) > 0:
            max_drawdown = (entry_price - min(future_lows)) / entry_price * 100
            exit_t[i] = 1 if max_drawdown >= _EXIT_DRAWDOWN_PCT else 0

    df["buy_target"] = buy_t
    df["exit_target"] = exit_t
    df.loc[buy_t == -1, "buy_target"] = np.nan
    df.loc[exit_t == -1, "exit_target"] = np.nan

    return df


def _get_feature_df(symbol: str) -> pd.DataFrame | None:
    """Build feature matrix using features.py and add timing targets."""
    from features import build_features, get_feature_names
    from technical_analysis import load_ohlcv

    feat_df = build_features(symbol)
    if feat_df is None or len(feat_df) < _MIN_DATA_ROWS:
        log.warning("数据不足: %s (%d行)", symbol, 0 if feat_df is None else len(feat_df))
        return None

    ohlcv = load_ohlcv(symbol)
    if ohlcv is None or len(ohlcv) < _MIN_DATA_ROWS:
        return None

    ohlcv_dates = pd.to_datetime(ohlcv["date"], errors="coerce").dt.strftime("%Y-%m-%d")
    feat_dates = pd.to_datetime(feat_df["date"], errors="coerce").dt.strftime("%Y-%m-%d")

    ohlcv_indexed = ohlcv.copy()
    ohlcv_indexed["_datekey"] = ohlcv_dates.values
    ohlcv_indexed = ohlcv_indexed.set_index("_datekey")

    for col in ["open", "high", "low", "close"]:
        if col not in feat_df.columns:
            feat_df[col] = feat_dates.map(ohlcv_indexed[col]).values

    feat_df = _build_timing_targets(feat_df)

    return feat_df


def _walk_forward_train(X, y, feature_cols, model_type="buy"):
    """Walk-forward training of XGBoost classifier."""
    import xgboost as xgb
    from sklearn.metrics import accuracy_score, precision_score, recall_score, f1_score

    n = len(X)
    results = []
    best_model = None
    best_f1 = -1

    for r in range(_N_WF_ROUNDS):
        test_end = n - r * _TEST_WINDOW
        test_start = test_end - _TEST_WINDOW
        train_end = test_start
        train_start = max(0, train_end - _TRAIN_WINDOW)

        if train_start >= train_end or test_start >= test_end or train_end - train_start < 50:
            continue

        X_train = X[train_start:train_end]
        y_train = y[train_start:train_end]
        X_test = X[test_start:test_end]
        y_test = y[test_start:test_end]

        X_train, X_test = _impute_fold(X_train, X_test, feature_cols)

        if len(np.unique(y_train)) < 2:
            continue

        pos_count = (y_train == 1).sum()
        neg_count = (y_train == 0).sum()
        scale = neg_count / max(pos_count, 1) if pos_count < neg_count else 1

        model = xgb.XGBClassifier(
            n_estimators=200,
            max_depth=4,
            learning_rate=0.05,
            subsample=0.8,
            colsample_bytree=0.7,
            reg_alpha=1.0,
            reg_lambda=2.0,
            min_child_weight=5,
            scale_pos_weight=scale,
            early_stopping_rounds=_EARLY_STOPPING,
            eval_metric="logloss",
            random_state=42,
            n_jobs=-1,
        )

        model.fit(
            X_train, y_train,
            eval_set=[(X_test, y_test)],
            verbose=False,
        )

        preds = model.predict(X_test)
        acc = accuracy_score(y_test, preds)
        prec = precision_score(y_test, preds, zero_division=0)
        rec = recall_score(y_test, preds, zero_division=0)
        f1 = f1_score(y_test, preds, zero_division=0)

        results.append({"round": r, "acc": acc, "prec": prec, "rec": rec, "f1": f1})

        if f1 > best_f1:
            best_f1 = f1
            best_model = model

    if not results:
        return None, {}

    avg_metrics = {
        "accuracy": round(np.mean([r["acc"] for r in results]), 4),
        "precision": round(np.mean([r["prec"] for r in results]), 4),
        "recall": round(np.mean([r["rec"] for r in results]), 4),
        "f1": round(np.mean([r["f1"] for r in results]), 4),
        "rounds": len(results),
        "model_type": model_type,
    }

    if best_model is None and results:
        X_full, _ = _impute_fold(X, X[-_TEST_WINDOW:], feature_cols)
        best_model = xgb.XGBClassifier(
            n_estimators=150, max_depth=4, learning_rate=0.05,
            subsample=0.8, colsample_bytree=0.7,
            reg_alpha=1.0, reg_lambda=2.0, min_child_weight=5,
            eval_metric="logloss", random_state=42, n_jobs=-1,
        )
        best_model.fit(X_full, y, verbose=False)

    return best_model, avg_metrics


def _impute_fold(X_train, X_test, feature_cols):
    """Impute NaN using training set medians."""
    train_df = pd.DataFrame(X_train, columns=feature_cols) if not isinstance(X_train, pd.DataFrame) else X_train
    test_df = pd.DataFrame(X_test, columns=feature_cols) if not isinstance(X_test, pd.DataFrame) else X_test
    medians = train_df.median()
    train_df = train_df.fillna(medians)
    test_df = test_df.fillna(medians)
    train_df = train_df.replace([np.inf, -np.inf], 0)
    test_df = test_df.replace([np.inf, -np.inf], 0)
    return train_df.values, test_df.values


def train_timing_model(symbol: str) -> dict:
    """Train both buy and exit timing models for a symbol.

    Returns:
        {
            "symbol": str,
            "buy_metrics": {...},
            "exit_metrics": {...},
            "feature_count": int,
            "data_rows": int,
            "trained_at": str,
            "status": "ok" | "error",
        }
    """
    log.info("=== 择时模型训练 %s ===", symbol)
    result = {"symbol": symbol, "status": "error"}

    feat_df = _get_feature_df(symbol)
    if feat_df is None:
        result["error"] = "数据不足"
        return result

    from features import get_feature_names
    feature_cols = get_feature_names()
    if not feature_cols:
        result["error"] = "无特征列"
        return result

    available_cols = [c for c in feature_cols if c in feat_df.columns]
    if len(available_cols) < 10:
        result["error"] = f"可用特征太少: {len(available_cols)}"
        return result

    X = feat_df[available_cols].copy().replace([np.inf, -np.inf], np.nan)

    for target_name, label in [("buy_target", "buy"), ("exit_target", "exit")]:
        valid = feat_df[target_name].notna()
        X_valid = X[valid].values
        y_valid = feat_df.loc[valid, target_name].astype(int).values

        if len(y_valid) < _MIN_DATA_ROWS:
            log.warning("%s %s 目标有效行数不足: %d", symbol, label, len(y_valid))
            result[f"{label}_metrics"] = {"error": "数据不足"}
            continue

        log.info("训练 %s 模型: %d 样本, %d 特征, 正样本比例=%.1f%%",
                 label, len(y_valid), len(available_cols),
                 (y_valid == 1).mean() * 100)

        model, metrics = _walk_forward_train(X_valid, y_valid, available_cols, label)

        if model is None:
            result[f"{label}_metrics"] = {"error": "训练失败"}
            continue

        mdir = _model_dir(symbol)
        model.save_model(os.path.join(mdir, f"{label}_model.json"))
        with open(os.path.join(mdir, f"{label}_features.json"), "w") as f:
            json.dump(available_cols, f)
        with open(os.path.join(mdir, f"{label}_metrics.json"), "w", encoding="utf-8") as f:
            json.dump(metrics, f, ensure_ascii=False, indent=2)

        result[f"{label}_metrics"] = metrics
        log.info("%s 模型: F1=%.3f, Precision=%.3f, Recall=%.3f",
                 label, metrics.get("f1", 0), metrics.get("precision", 0), metrics.get("recall", 0))

    result["feature_count"] = len(available_cols)
    result["data_rows"] = len(feat_df)
    result["trained_at"] = datetime.now().isoformat()
    result["status"] = "ok"

    with open(os.path.join(_model_dir(symbol), "train_result.json"), "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    log.info("=== 择时模型训练完成 %s ===", symbol)
    return result


def predict_timing(symbol: str) -> dict:
    """Predict buy/exit signals for the latest trading day.

    Returns:
        {
            "symbol": str,
            "signal": "买入" | "观望偏多" | "回避" | "观望",
            "buy_prob": float,
            "exit_prob": float,
            "details": str,
        }
    """
    import xgboost as xgb

    mdir = _model_dir(symbol)
    result = {"symbol": symbol, "signal": "无模型", "buy_prob": 0, "exit_prob": 0, "details": ""}

    buy_model_path = os.path.join(mdir, "buy_model.json")
    exit_model_path = os.path.join(mdir, "exit_model.json")
    buy_feat_path = os.path.join(mdir, "buy_features.json")

    if not os.path.isfile(buy_model_path):
        result["details"] = "买入模型不存在, 请先训练"
        return result

    with open(buy_feat_path, encoding="utf-8") as f:
        feature_cols = json.load(f)

    from features import build_features
    feat_df = build_features(symbol)
    if feat_df is None or feat_df.empty:
        result["details"] = "特征构建失败"
        return result

    available = [c for c in feature_cols if c in feat_df.columns]
    if len(available) < len(feature_cols) * 0.7:
        result["details"] = f"可用特征不足: {len(available)}/{len(feature_cols)}"
        return result

    X_latest = feat_df[available].iloc[[-1]].copy()
    X_latest = X_latest.replace([np.inf, -np.inf], np.nan).fillna(0)

    buy_model = xgb.XGBClassifier()
    buy_model.load_model(buy_model_path)
    buy_prob = float(buy_model.predict_proba(X_latest)[0][1]) if hasattr(buy_model, "predict_proba") else 0
    buy_pred = int(buy_model.predict(X_latest)[0])

    exit_prob = 0
    exit_pred = 0
    if os.path.isfile(exit_model_path):
        exit_model = xgb.XGBClassifier()
        exit_model.load_model(exit_model_path)
        exit_prob = float(exit_model.predict_proba(X_latest)[0][1]) if hasattr(exit_model, "predict_proba") else 0
        exit_pred = int(exit_model.predict(X_latest)[0])

    if buy_pred == 1 and exit_pred == 0:
        signal = "买入"
        detail = f"买入信号触发(概率{buy_prob:.0%}), 退出风险低(概率{exit_prob:.0%})"
    elif buy_pred == 1 and exit_pred == 1:
        signal = "观望偏多"
        detail = f"有上涨机会(概率{buy_prob:.0%}), 但回撤风险也高(概率{exit_prob:.0%})"
    elif buy_pred == 0 and exit_pred == 1:
        signal = "回避"
        detail = f"无买入信号, 且回撤风险高(概率{exit_prob:.0%})"
    else:
        signal = "观望"
        detail = f"买入概率{buy_prob:.0%}, 退出风险概率{exit_prob:.0%}, 均无明确信号"

    result["signal"] = signal
    result["buy_prob"] = round(buy_prob, 4)
    result["exit_prob"] = round(exit_prob, 4)
    result["details"] = detail
    result["predicted_at"] = datetime.now().isoformat()

    return result


def predict_batch(symbols: list[str]) -> list[dict]:
    """Predict timing signals for multiple symbols."""
    results = []
    for sym in symbols:
        try:
            r = predict_timing(sym)
            results.append(r)
        except Exception as e:
            log.warning("择时预测 %s 失败: %s", sym, e)
            results.append({
                "symbol": sym, "signal": "错误",
                "buy_prob": 0, "exit_prob": 0,
                "details": str(e),
            })
    return results


if __name__ == "__main__":
    import sys
    sys.stdout.reconfigure(encoding="utf-8")
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    sym = sys.argv[1] if len(sys.argv) > 1 else "600519"
    mode = sys.argv[2] if len(sys.argv) > 2 else "train"

    if mode == "train":
        result = train_timing_model(sym)
        print(json.dumps(result, ensure_ascii=False, indent=2))
    elif mode == "predict":
        result = predict_timing(sym)
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(f"用法: python model_timing.py <symbol> [train|predict]")
