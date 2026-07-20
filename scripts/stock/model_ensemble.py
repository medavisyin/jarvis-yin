"""
集成模型 — XGBoost + Ridge (+ LightGBM 可选) 加权预测与分歧度.

Phase 3.1 + 3.4: 集成预测、高不确定性标记、置信区间.
"""
import logging
import warnings

import numpy as np
import pandas as pd
from sklearn.linear_model import Ridge

log = logging.getLogger(__name__)
warnings.filterwarnings("ignore", category=UserWarning)

_HAS_LGB = False
try:
    import lightgbm as lgb
    _HAS_LGB = True
except ImportError:
    pass


def _direction(pct: float) -> int:
    if pct > 0.1:
        return 1
    if pct < -0.1:
        return -1
    return 0


def ensemble_predict_close(
    X_train: np.ndarray,
    y_train: np.ndarray,
    X_pred: np.ndarray,
    wf_preds: list[float] | None = None,
) -> dict:
    """
    训练三模型并集成预测 close 目标 (% return).

    Returns: pred_pct, ci_low, ci_high, disagreement, uncertainty_level, models
    """
    import xgboost as xgb

    models = {}
    preds = {}

    xgb_m = xgb.XGBRegressor(
        max_depth=4, learning_rate=0.05, n_estimators=120,
        subsample=0.8, colsample_bytree=0.7, verbosity=0,
    )
    xgb_m.fit(X_train, y_train)
    preds["xgboost"] = float(xgb_m.predict(X_pred.reshape(1, -1))[0])
    models["xgboost"] = True

    ridge = Ridge(alpha=1.0)
    ridge.fit(X_train, y_train)
    preds["ridge"] = float(ridge.predict(X_pred.reshape(1, -1))[0])
    models["ridge"] = True

    if _HAS_LGB and len(X_train) > 100:
        lgb_m = lgb.LGBMRegressor(
            max_depth=4, learning_rate=0.05, n_estimators=120,
            subsample=0.8, colsample_bytree=0.7, verbose=-1,
        )
        lgb_m.fit(X_train, y_train)
        preds["lightgbm"] = float(lgb_m.predict(X_pred.reshape(1, -1))[0])
        models["lightgbm"] = True

    weights = {"xgboost": 0.5, "lightgbm": 0.3, "ridge": 0.2}
    if "lightgbm" not in preds:
        weights = {"xgboost": 0.65, "ridge": 0.35}

    total_w = sum(weights[k] for k in preds)
    pred_pct = sum(preds[k] * weights.get(k, 0) for k in preds) / total_w

    dirs = [_direction(p) for p in preds.values()]
    unique_dirs = set(dirs)
    disagreement = len(unique_dirs) > 1 and 0 not in unique_dirs or (1 in unique_dirs and -1 in unique_dirs)

    if wf_preds and len(wf_preds) >= 3:
        std = float(np.std(wf_preds))
        ci_low = pred_pct - 1.28 * std
        ci_high = pred_pct + 1.28 * std
    else:
        spread = max(preds.values()) - min(preds.values())
        ci_low = pred_pct - spread
        ci_high = pred_pct + spread
        std = spread / 2

    if disagreement or std > 2.0:
        uncertainty = "high"
    elif std > 1.0:
        uncertainty = "medium"
    else:
        uncertainty = "low"

    return {
        "pred_pct": round(pred_pct, 3),
        "ci_low_pct": round(ci_low, 3),
        "ci_high_pct": round(ci_high, 3),
        "ci_80": [round(ci_low, 3), round(ci_high, 3)],
        "model_preds": {k: round(v, 3) for k, v in preds.items()},
        "disagreement": disagreement,
        "uncertainty": uncertainty,
        "uncertainty_zh": {"high": "高", "medium": "中等", "low": "低"}.get(uncertainty, "未知"),
        "models_used": list(preds.keys()),
        "has_lightgbm": _HAS_LGB,
    }


def enrich_prediction_result(xgb_result: dict, symbol: str) -> dict:
    """在已有 XGBoost 价格预测结果上附加集成与不确定性信息."""
    if xgb_result.get("error"):
        return xgb_result

    wf = xgb_result.get("walk_forward", {}).get("close", {})
    wf_details = wf.get("details", [])
    wf_preds = [r.get("pred_pct") or r.get("pred") for r in wf_details if r]
    wf_preds = [float(p) for p in wf_preds if p is not None]

    close_pct = xgb_result.get("change_pct", {}).get("close", 0)
    mae = wf.get("overall_mae", 2.0)

    if wf_preds:
        std = float(np.std(wf_preds))
        ci_low = close_pct - 1.28 * std
        ci_high = close_pct + 1.28 * std
    else:
        ci_low = close_pct - mae
        ci_high = close_pct + mae
        std = mae

    uncertainty = "low"
    if std > 2.0 or xgb_result.get("confidence", {}).get("signal_strength") == "noise":
        uncertainty = "high"
    elif std > 1.0:
        uncertainty = "medium"

    current = xgb_result.get("current_close")
    price_ci = None
    if current:
        price_ci = [
            round(current * (1 + ci_low / 100), 2),
            round(current * (1 + ci_high / 100), 2),
        ]

    xgb_result["uncertainty"] = {
        "level": uncertainty,
        "level_zh": {"high": "高", "medium": "中等", "low": "低"}.get(uncertainty),
        "ci_80_pct": [round(ci_low, 2), round(ci_high, 2)],
        "ci_80_price": price_ci,
        "wf_std": round(std, 3),
    }
    xgb_result["ensemble_note"] = (
        "模型分歧度高，建议观望" if uncertainty == "high"
        else "集成不确定性在可接受范围"
    )
    return xgb_result
