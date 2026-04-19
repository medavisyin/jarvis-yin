"""
XGBoost 预测模型 — Walk-Forward 验证 + 三分类预测.

训练流程:
  1. 从 features.py 获取特征矩阵
  2. Walk-Forward 分割: 滑动窗口训练+测试
  3. 训练 XGBoost 分类器, 预测5日方向 (涨/平/跌)
  4. 输出置信度、特征重要性、历史准确率

模型持久化: 保存到 C:/reports/stock/models/{symbol}/
"""
import json
import logging
import os
import warnings
from datetime import datetime

import numpy as np
import pandas as pd
from sklearn.preprocessing import LabelEncoder

from config import STOCK_DATA_DIR, STOCK_MODELS_DIR

log = logging.getLogger(__name__)

warnings.filterwarnings("ignore", category=UserWarning)

_TRAIN_WINDOW = 500
_TEST_WINDOW = 5
_MIN_DATA_ROWS = 300
_N_ROUNDS = 15
_EARLY_STOPPING_ROUNDS = 15

_LABEL_MAP = {-1: "跌", 0: "平", 1: "涨"}


def _prepare_data(feature_df: pd.DataFrame, feature_cols: list[str]):
    """准备X和y, 不做全局填充 (避免数据泄漏)."""
    valid = feature_df.dropna(subset=["target"]).copy()

    X = valid[feature_cols].copy()
    y = valid["target"].astype(int).values

    X = X.replace([np.inf, -np.inf], np.nan)

    return X, y, valid


def _impute_fold(X_train: np.ndarray, X_test: np.ndarray,
                 feature_cols: list[str]) -> tuple[np.ndarray, np.ndarray]:
    """用训练集的中位数填充训练集和测试集的NaN, 防止未来数据泄漏."""
    train_df = pd.DataFrame(X_train, columns=feature_cols)
    test_df = pd.DataFrame(X_test, columns=feature_cols)

    medians = train_df.median()
    train_df.fillna(medians, inplace=True)
    test_df.fillna(medians, inplace=True)

    return train_df.values, test_df.values


def train_and_predict(symbol: str, feature_df: pd.DataFrame = None,
                      feature_cols: list[str] = None) -> dict:
    """
    训练 XGBoost 模型并生成预测.

    Walk-Forward 流程:
      用最近 _TRAIN_WINDOW 行训练, 预测最新一行.
      滑动窗口重复 _N_ROUNDS 轮, 收集历史准确率.

    Returns dict:
    {
        "symbol": "600519",
        "prediction": "涨" | "平" | "跌",
        "confidence": 0.72,
        "probabilities": {"涨": 0.72, "平": 0.18, "跌": 0.10},
        "feature_importance": [{"name": "rsi_14", "importance": 0.15}, ...],
        "walk_forward": {"rounds": 5, "accuracy": 0.65, "details": [...]},
        "model_info": { ... }
    }
    """
    import xgboost as xgb

    if feature_df is None:
        from features import build_features, get_feature_names
        feature_df = build_features(symbol)
        feature_cols = get_feature_names()

    if feature_df is None:
        return {"error": "特征数据不足", "symbol": symbol}

    if feature_cols is None:
        from features import get_feature_names
        feature_cols = get_feature_names()

    X_all, y_all, valid_df = _prepare_data(feature_df, feature_cols)

    if len(X_all) < _MIN_DATA_ROWS:
        log.warning("%s: 数据仅 %d 行, 最少需要 %d 行, 将使用缩短的训练窗口",
                    symbol, len(X_all), _MIN_DATA_ROWS)

    le = LabelEncoder()
    le.fit([-1, 0, 1])

    n = len(X_all)
    train_size = min(_TRAIN_WINDOW, n - _TEST_WINDOW - 1)
    if train_size < 60:
        return {"error": f"数据不足: 有效行数={n}, 训练至少需要60行", "symbol": symbol}

    wf_results = []
    last_model = None

    n_classes = len(le.classes_)
    params = {
        "objective": "multi:softprob",
        "num_class": n_classes,
        "max_depth": 3,
        "learning_rate": 0.05,
        "n_estimators": 200,
        "min_child_weight": 8,
        "subsample": 0.7,
        "colsample_bytree": 0.6,
        "reg_alpha": 0.5,
        "reg_lambda": 2.0,
        "random_state": 42,
        "verbosity": 0,
        "use_label_encoder": False,
        "early_stopping_rounds": _EARLY_STOPPING_ROUNDS,
    }

    n_rounds = min(_N_ROUNDS, (n - train_size) // _TEST_WINDOW)
    if n_rounds < 1:
        n_rounds = 1

    for rnd in range(n_rounds):
        offset = rnd * _TEST_WINDOW
        test_end = n - offset
        test_start = test_end - _TEST_WINDOW
        train_end = test_start

        if train_end < train_size:
            break

        train_start = train_end - train_size

        X_train_raw = X_all.iloc[train_start:train_end].values
        y_train = y_all[train_start:train_end]
        X_test_raw = X_all.iloc[test_start:test_end].values
        y_test = y_all[test_start:test_end]

        X_train, X_test = _impute_fold(X_train_raw, X_test_raw, feature_cols)

        y_train_enc = le.transform(y_train)

        unique_classes = np.unique(y_train_enc)
        if len(unique_classes) < 2:
            log.warning("轮次 %d: 训练集只有一个类别, 跳过", rnd)
            continue

        class_counts = np.bincount(y_train_enc, minlength=n_classes)
        class_weights = np.where(class_counts > 0,
                                 len(y_train_enc) / (n_classes * class_counts), 1.0)
        sample_weights = np.array([class_weights[c] for c in y_train_enc])

        model = xgb.XGBClassifier(**params)
        model.fit(X_train, y_train_enc, sample_weight=sample_weights,
                  eval_set=[(X_test, le.transform(y_test))], verbose=False)
        last_model = model

        preds = le.inverse_transform(model.predict(X_test))
        mask = ~np.isnan(y_test.astype(float))
        if mask.sum() > 0:
            correct = (preds[mask] == y_test[mask]).sum()
            total = mask.sum()
            wf_results.append({
                "round": rnd + 1,
                "train_size": train_size,
                "test_size": int(total),
                "correct": int(correct),
                "accuracy": round(correct / total, 4) if total > 0 else 0,
            })

    if last_model is None:
        return {"error": "训练失败 — 数据不足或类别不平衡", "symbol": symbol}

    overall_correct = sum(r["correct"] for r in wf_results)
    overall_total = sum(r["test_size"] for r in wf_results)
    overall_acc = round(overall_correct / overall_total, 4) if overall_total > 0 else 0

    final_train_end = n
    final_train_start = max(0, final_train_end - train_size)
    X_final_raw = X_all.iloc[final_train_start:final_train_end].values
    y_final_train = y_all[final_train_start:final_train_end]
    y_final_enc = le.transform(y_final_train)

    final_train_df = pd.DataFrame(X_final_raw, columns=feature_cols)
    final_medians = final_train_df.median()
    final_train_df.fillna(final_medians, inplace=True)

    if len(np.unique(y_final_enc)) >= 2:
        final_counts = np.bincount(y_final_enc, minlength=n_classes)
        final_weights = np.where(final_counts > 0,
                                 len(y_final_enc) / (n_classes * final_counts), 1.0)
        final_sample_w = np.array([final_weights[c] for c in y_final_enc])

        final_params = dict(params)
        final_params.pop("early_stopping_rounds", None)
        if hasattr(last_model, 'best_iteration') and last_model.best_iteration > 0:
            final_params["n_estimators"] = last_model.best_iteration + 1
        final_model = xgb.XGBClassifier(**final_params)
        final_model.fit(final_train_df.values, y_final_enc,
                        sample_weight=final_sample_w, verbose=False)
        last_model = final_model
        log.info("已在最新窗口 [%d:%d] 重新训练最终推理模型", final_train_start, final_train_end)

    latest_raw = X_all.iloc[[-1]].copy()
    latest_raw.fillna(final_medians, inplace=True)
    latest_X = latest_raw.values
    proba = last_model.predict_proba(latest_X)[0]
    pred_idx = np.argmax(proba)
    pred_label = int(le.inverse_transform([pred_idx])[0])
    confidence = float(proba[pred_idx])

    prob_dict = {}
    for i, cls in enumerate(le.classes_):
        prob_dict[_LABEL_MAP.get(cls, str(cls))] = round(float(proba[i]), 4)

    importances = last_model.feature_importances_
    feat_imp = sorted(
        [{"name": feature_cols[i], "importance": round(float(importances[i]), 4)}
         for i in range(len(feature_cols))],
        key=lambda x: x["importance"], reverse=True
    )[:15]

    result = {
        "symbol": symbol,
        "prediction": _LABEL_MAP.get(pred_label, "平"),
        "prediction_code": pred_label,
        "confidence": round(confidence, 4),
        "probabilities": prob_dict,
        "feature_importance": feat_imp,
        "walk_forward": {
            "rounds": len(wf_results),
            "overall_accuracy": overall_acc,
            "overall_correct": overall_correct,
            "overall_total": overall_total,
            "details": wf_results,
        },
        "model_info": {
            "algorithm": "XGBoost",
            "train_window": train_size,
            "test_window": _TEST_WINDOW,
            "n_features": len(feature_cols),
            "n_data_rows": n,
            "predicted_at": datetime.now().isoformat(),
        },
        "latest_date": str(valid_df["date"].iloc[-1])[:10] if "date" in valid_df.columns else "",
    }

    _save_result(symbol, result, last_model, feature_cols)

    return result


def _save_result(symbol: str, result: dict, model, feature_cols: list[str]):
    """保存预测结果和模型."""
    model_dir = os.path.join(STOCK_MODELS_DIR, symbol)
    os.makedirs(model_dir, exist_ok=True)

    with open(os.path.join(model_dir, "prediction.json"), "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    model.save_model(os.path.join(model_dir, "model.json"))

    with open(os.path.join(model_dir, "features.json"), "w", encoding="utf-8") as f:
        json.dump(feature_cols, f, ensure_ascii=False)

    data_dir = os.path.join(STOCK_DATA_DIR, symbol)
    os.makedirs(data_dir, exist_ok=True)
    with open(os.path.join(data_dir, "xgb_prediction.json"), "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    log.info("模型和预测已保存 → %s", model_dir)


def load_prediction(symbol: str) -> dict | None:
    """加载已保存的预测结果."""
    path = os.path.join(STOCK_DATA_DIR, symbol, "xgb_prediction.json")
    if os.path.isfile(path):
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    return None


def generate_xgb_report(symbol: str, result: dict | None = None) -> str:
    """生成 XGBoost 预测的中文 Markdown 报告."""
    if result is None:
        result = load_prediction(symbol)
    if result is None:
        result = train_and_predict(symbol)

    if "error" in result:
        return f"## XGBoost 预测\n\n**错误:** {result['error']}"

    pred = result["prediction"]
    conf = result["confidence"]
    probs = result.get("probabilities", {})
    feats = result.get("feature_importance", [])
    wf = result.get("walk_forward", {})
    info = result.get("model_info", {})

    pred_icon = {"涨": "🟢", "跌": "🔴", "平": "⚪"}.get(pred, "⚪")

    if conf >= 0.7:
        conf_label = "高"
    elif conf >= 0.5:
        conf_label = "中"
    else:
        conf_label = "低"

    lines = []
    lines.append(f"# {symbol} XGBoost 机器学习预测")
    lines.append(f"> 预测方向: {pred_icon} **{pred}** | 置信度: **{conf:.1%}** ({conf_label})")
    lines.append(f"> Walk-Forward 历史准确率: **{wf.get('overall_accuracy', 0):.1%}** ({wf.get('overall_correct', 0)}/{wf.get('overall_total', 0)})")
    lines.append("")

    lines.append("## 预测概率分布")
    lines.append("")
    lines.append("| 方向 | 概率 | 可视化 |")
    lines.append("|------|------|--------|")
    for label in ["涨", "平", "跌"]:
        p = probs.get(label, 0)
        bar = "█" * int(p * 20) + "░" * (20 - int(p * 20))
        icon = "🟢" if label == "涨" else "🔴" if label == "跌" else "⚪"
        lines.append(f"| {icon} {label} | {p:.1%} | {bar} |")
    lines.append("")

    if feats:
        lines.append("## 关键特征 (模型依据)")
        lines.append("")
        lines.append("| 排名 | 特征 | 重要性 | 说明 |")
        lines.append("|------|------|--------|------|")
        feat_desc = {
            "rsi_14": "RSI超买超卖",
            "rsi_delta": "RSI变化速度",
            "ret_1d": "昨日涨跌",
            "ret_5d": "5日回报",
            "ret_10d": "10日回报",
            "ret_20d": "20日回报",
            "dist_ma5": "偏离5日均线",
            "dist_ma20": "偏离20日均线",
            "dist_ma60": "偏离60日均线",
            "vol_ratio_20": "量比(20日)",
            "vol_change_1d": "成交量变化",
            "atr_pct": "波动率(ATR%)",
            "volatility_20d": "20日年化波动率",
            "bb_pct": "布林带位置",
            "bb_width": "布林带宽度",
            "kdj_j": "KDJ-J值",
            "kdj_j_delta": "KDJ变化",
            "macd_hist_delta": "MACD柱变化",
            "ma5_ma20_spread": "MA5-MA20差",
            "body_ratio": "K线实体比",
            "bullish_streak": "连阳天数",
            "gap": "跳空幅度",
            "daily_range_pct": "日内振幅",
        }
        for i, f in enumerate(feats[:10]):
            desc = feat_desc.get(f["name"], "")
            bar = "█" * max(1, int(f["importance"] * 50))
            lines.append(f"| {i+1} | {f['name']} | {f['importance']:.3f} {bar} | {desc} |")
        lines.append("")

    if wf.get("details"):
        lines.append("## Walk-Forward 验证详情")
        lines.append("")
        lines.append("| 轮次 | 训练集 | 测试集 | 正确 | 准确率 |")
        lines.append("|------|--------|--------|------|--------|")
        for d in wf["details"]:
            acc = d["accuracy"]
            icon = "✅" if acc >= 0.6 else "⚠️" if acc >= 0.4 else "❌"
            lines.append(f"| {d['round']} | {d['train_size']} | {d['test_size']} | {d['correct']} | {icon} {acc:.0%} |")
        lines.append("")

    lines.append("## 模型信息")
    lines.append("")
    lines.append(f"| 项目 | 值 |")
    lines.append(f"|------|---|")
    lines.append(f"| 算法 | {info.get('algorithm', 'XGBoost')} |")
    lines.append(f"| 训练窗口 | {info.get('train_window', 'N/A')} 交易日 |")
    lines.append(f"| 特征数 | {info.get('n_features', 'N/A')} |")
    lines.append(f"| 数据行数 | {info.get('n_data_rows', 'N/A')} |")
    lines.append(f"| 预测时间 | {info.get('predicted_at', '')[:16]} |")
    lines.append("")

    lines.append("---")
    lines.append("*注意: 机器学习预测仅供参考, 股市有风险, 投资需谨慎。历史准确率不代表未来表现。*")

    report = "\n".join(lines)

    report_path = os.path.join(STOCK_DATA_DIR, symbol, "xgb-report.md")
    with open(report_path, "w", encoding="utf-8") as f:
        f.write(report)
    log.info("XGBoost 报告已保存 → %s", report_path)

    return report


if __name__ == "__main__":
    import sys
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    sym = sys.argv[1] if len(sys.argv) > 1 else "600519"
    result = train_and_predict(sym)
    if "error" in result:
        print(f"错误: {result['error']}")
    else:
        print(f"\n预测: {result['prediction']} (置信度: {result['confidence']:.1%})")
        print(f"概率: {result['probabilities']}")
        print(f"Walk-Forward 准确率: {result['walk_forward']['overall_accuracy']:.1%}")
        print(f"\nTop 5 特征:")
        for f in result["feature_importance"][:5]:
            print(f"  {f['name']}: {f['importance']:.4f}")

    print("\n" + "=" * 60)
    report = generate_xgb_report(sym, result)
    print(report)
