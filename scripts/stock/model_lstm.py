"""LSTM 5-day direction prototype (research). Phase B price stub only."""
from __future__ import annotations

import json
import logging
import os
import time
from datetime import datetime

import numpy as np
import pandas as pd
import torch
import torch.nn as nn
from sklearn.preprocessing import LabelEncoder

from config import STOCK_DATA_DIR

log = logging.getLogger(__name__)

SEQ_LEN = 30
HIDDEN = 64
LAYERS = 2
DROPOUT = 0.2
_LABEL_MAP = {-1: "跌", 0: "平", 1: "涨"}
_TRAIN_WINDOW = 500
_TEST_WINDOW = 5
_N_ROUNDS = 15
_MIN_DATA_ROWS = 300
_MAX_EPOCHS = 40
_EARLY_STOP_PATIENCE = 5
_BATCH_SIZE = 32
_LR = 1e-3


def build_sequences(X: np.ndarray, y: np.ndarray, seq_len: int):
    """Return (X_seq[N,T,F], y_seq[N], end_indices[N]) for end index t = seq_len-1 .. n-1."""
    n, f = X.shape
    if n < seq_len:
        return (
            np.zeros((0, seq_len, f), dtype=float),
            np.zeros((0,), dtype=y.dtype),
            np.zeros((0,), dtype=int),
        )
    xs, ys, ends = [], [], []
    for t in range(seq_len - 1, n):
        xs.append(X[t - seq_len + 1 : t + 1])
        ys.append(y[t])
        ends.append(t)
    return np.stack(xs), np.asarray(ys), np.asarray(ends, dtype=int)


class FitScaler:
    """Per-fold median impute + z-score using train statistics only."""

    def __init__(self, medians, means, stds):
        self.medians = medians
        self.means = means
        self.stds = stds

    @classmethod
    def fit(cls, X_train: np.ndarray) -> "FitScaler":
        X = np.asarray(X_train, dtype=float).copy()
        X[~np.isfinite(X)] = np.nan
        medians = np.nanmedian(X, axis=0)
        medians = np.where(np.isfinite(medians), medians, 0.0)
        inds = np.where(np.isnan(X))
        X[inds] = np.take(medians, inds[1])
        means = X.mean(axis=0)
        stds = X.std(axis=0)
        stds = np.where(stds < 1e-8, 1.0, stds)
        return cls(medians, means, stds)

    def transform(self, X: np.ndarray) -> np.ndarray:
        X = np.asarray(X, dtype=float).copy()
        X[~np.isfinite(X)] = np.nan
        inds = np.where(np.isnan(X))
        X[inds] = np.take(self.medians, inds[1])
        return (X - self.means) / self.stds


class LSTMClassifier(nn.Module):
    def __init__(self, input_size: int, hidden: int = HIDDEN, layers: int = LAYERS,
                 dropout: float = DROPOUT, n_classes: int = 3):
        super().__init__()
        self.lstm = nn.LSTM(
            input_size=input_size,
            hidden_size=hidden,
            num_layers=layers,
            batch_first=True,
            dropout=dropout if layers > 1 else 0.0,
        )
        self.fc = nn.Linear(hidden, n_classes)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        out, _ = self.lstm(x)
        return self.fc(out[:, -1, :])


def train_and_predict_price(symbol: str, *args, **kwargs):
    """Phase B placeholder — next-day price regression not implemented."""
    raise NotImplementedError(
        "Phase B (明日价格 LSTM 回归) 尚未实现 — 见 docs/plans/2026-08-05-lstm-direction-prototype.md"
    )


def _set_seed(seed: int = 42):
    np.random.seed(seed)
    torch.manual_seed(seed)


def _class_weights(y_enc: np.ndarray, n_classes: int) -> torch.Tensor:
    counts = np.bincount(y_enc, minlength=n_classes).astype(float)
    weights = np.where(counts > 0, len(y_enc) / (n_classes * counts), 1.0)
    return torch.tensor(weights, dtype=torch.float32)


def _train_lstm(
    X_seq: np.ndarray,
    y_enc: np.ndarray,
    input_size: int,
    max_epochs: int,
    device: str,
    n_classes: int = 3,
) -> LSTMClassifier:
    """Train with early stop on last 10% of train sequences."""
    model = LSTMClassifier(input_size=input_size, n_classes=n_classes).to(device)
    if len(X_seq) < 2:
        return model

    n = len(X_seq)
    val_n = max(1, int(n * 0.1))
    if n - val_n < 1:
        val_n = 0

    if val_n > 0:
        X_tr, y_tr = X_seq[:-val_n], y_enc[:-val_n]
        X_va, y_va = X_seq[-val_n:], y_enc[-val_n:]
    else:
        X_tr, y_tr = X_seq, y_enc
        X_va = y_va = None

    weight = _class_weights(y_tr, n_classes).to(device)
    criterion = nn.CrossEntropyLoss(weight=weight)
    opt = torch.optim.Adam(model.parameters(), lr=_LR)

    X_tr_t = torch.tensor(X_tr, dtype=torch.float32, device=device)
    y_tr_t = torch.tensor(y_tr, dtype=torch.long, device=device)

    best_state = None
    best_val = float("inf")
    patience = 0

    for _epoch in range(max_epochs):
        model.train()
        perm = torch.randperm(len(X_tr_t), device=device)
        for start in range(0, len(X_tr_t), _BATCH_SIZE):
            idx = perm[start : start + _BATCH_SIZE]
            opt.zero_grad()
            logits = model(X_tr_t[idx])
            loss = criterion(logits, y_tr_t[idx])
            loss.backward()
            opt.step()

        if X_va is None:
            continue

        model.eval()
        with torch.no_grad():
            X_va_t = torch.tensor(X_va, dtype=torch.float32, device=device)
            y_va_t = torch.tensor(y_va, dtype=torch.long, device=device)
            val_loss = float(criterion(model(X_va_t), y_va_t).item())

        if val_loss < best_val - 1e-6:
            best_val = val_loss
            best_state = {k: v.detach().cpu().clone() for k, v in model.state_dict().items()}
            patience = 0
        else:
            patience += 1
            if patience >= _EARLY_STOP_PATIENCE:
                break

    if best_state is not None:
        model.load_state_dict(best_state)
    return model


def _predict_proba(model: LSTMClassifier, X_seq: np.ndarray, device: str) -> np.ndarray:
    model.eval()
    with torch.no_grad():
        t = torch.tensor(X_seq, dtype=torch.float32, device=device)
        logits = model(t)
        probs = torch.softmax(logits, dim=-1).cpu().numpy()
    return probs


def train_and_predict(
    symbol: str,
    feature_df: pd.DataFrame | None = None,
    feature_cols: list[str] | None = None,
    seq_len: int = SEQ_LEN,
    train_window: int = _TRAIN_WINDOW,
    test_window: int = _TEST_WINDOW,
    n_rounds: int = _N_ROUNDS,
    max_epochs: int = _MAX_EPOCHS,
    save: bool = True,
    device: str | None = None,
) -> dict:
    """Walk-forward LSTM direction classifier (research prototype)."""
    t0 = time.time()
    _set_seed(42)
    device = device or ("cuda" if torch.cuda.is_available() else "cpu")

    if feature_df is None:
        from features import build_features, get_feature_names
        feature_df = build_features(symbol)
        feature_cols = get_feature_names()

    if feature_df is None:
        return {"error": "特征数据不足", "symbol": symbol}

    if feature_cols is None:
        from features import get_feature_names
        feature_cols = get_feature_names()

    valid = feature_df.dropna(subset=["target"]).copy()
    if len(valid) < seq_len + 2:
        return {
            "error": f"数据不足: 有效行数={len(valid)}, seq_len={seq_len}",
            "symbol": symbol,
        }

    X_all = valid[feature_cols].replace([np.inf, -np.inf], np.nan).values.astype(float)
    y_all = valid["target"].astype(int).values
    n = len(X_all)

    le = LabelEncoder()
    le.fit([-1, 0, 1])
    n_classes = len(le.classes_)

    train_size = min(train_window, n - test_window - 1)
    if train_size < max(seq_len + 10, 20):
        return {
            "error": f"数据不足: 有效行数={n}, 训练至少需要{seq_len + 10}行",
            "symbol": symbol,
        }

    if n < _MIN_DATA_ROWS:
        log.warning("%s: 数据仅 %d 行 (建议 >= %d)", symbol, n, _MIN_DATA_ROWS)

    max_rounds = max(1, (n - train_size) // test_window)
    n_rounds = min(n_rounds, max_rounds)

    wf_results = []
    last_model = None
    last_scaler = None

    for rnd in range(n_rounds):
        offset = rnd * test_window
        test_end = n - offset
        test_start = test_end - test_window
        train_end = test_start
        if train_end < train_size:
            break
        train_start = train_end - train_size

        X_train_raw = X_all[train_start:train_end]
        y_train = y_all[train_start:train_end]
        scaler = FitScaler.fit(X_train_raw)

        # Scaled block covering train + test so test sequences have history
        X_block = scaler.transform(X_all[train_start:test_end])
        y_block = y_all[train_start:test_end]

        X_tr_s = X_block[: train_end - train_start]
        y_tr = y_train
        Xs_tr, ys_tr, _ = build_sequences(X_tr_s, y_tr, seq_len)
        if len(Xs_tr) < 2:
            log.warning("轮次 %d: 训练序列不足, 跳过", rnd + 1)
            continue

        y_tr_enc = le.transform(ys_tr)
        if len(np.unique(y_tr_enc)) < 2:
            log.warning("轮次 %d: 训练集只有一个类别, 跳过", rnd + 1)
            continue

        Xs_all, ys_all, ends = build_sequences(X_block, y_block, seq_len)
        # ends are relative to block; original end = train_start + end
        mask = (ends + train_start >= test_start) & (ends + train_start < test_end)
        Xs_te = Xs_all[mask]
        ys_te = ys_all[mask]
        if len(Xs_te) == 0:
            log.warning("轮次 %d: 无测试序列, 跳过", rnd + 1)
            continue

        model = _train_lstm(
            Xs_tr, y_tr_enc, input_size=X_all.shape[1],
            max_epochs=max_epochs, device=device, n_classes=n_classes,
        )
        last_model = model
        last_scaler = scaler

        probs = _predict_proba(model, Xs_te, device)
        pred_idx = probs.argmax(axis=1)
        preds = le.inverse_transform(pred_idx)
        correct = int((preds == ys_te).sum())
        total = int(len(ys_te))
        wf_results.append({
            "round": rnd + 1,
            "train_size": train_size,
            "test_size": total,
            "correct": correct,
            "accuracy": round(correct / total, 4) if total > 0 else 0,
        })

    if last_model is None or last_scaler is None:
        return {"error": "训练失败 — 数据不足或类别不平衡", "symbol": symbol}

    overall_correct = sum(r["correct"] for r in wf_results)
    overall_total = sum(r["test_size"] for r in wf_results)
    overall_acc = round(overall_correct / overall_total, 4) if overall_total else 0

    # Final fit on latest window
    final_train_end = n
    final_train_start = max(0, final_train_end - train_size)
    X_final_raw = X_all[final_train_start:final_train_end]
    y_final = y_all[final_train_start:final_train_end]
    final_scaler = FitScaler.fit(X_final_raw)
    X_final = final_scaler.transform(X_final_raw)
    Xs_f, ys_f, _ = build_sequences(X_final, y_final, seq_len)
    if len(Xs_f) < 2 or len(np.unique(ys_f)) < 2:
        return {"error": "最终训练窗口无效", "symbol": symbol}

    y_f_enc = le.transform(ys_f)
    final_model = _train_lstm(
        Xs_f, y_f_enc, input_size=X_all.shape[1],
        max_epochs=max_epochs, device=device, n_classes=n_classes,
    )

    # Predict last labeled sequence
    latest_seq = Xs_f[-1:]
    proba = _predict_proba(final_model, latest_seq, device)[0]
    pred_idx = int(np.argmax(proba))
    pred_label = int(le.inverse_transform([pred_idx])[0])
    confidence = float(proba[pred_idx])

    prob_dict = {}
    for i, cls in enumerate(le.classes_):
        prob_dict[_LABEL_MAP.get(int(cls), str(cls))] = round(float(proba[i]), 4)

    latest_date = ""
    if "date" in valid.columns:
        latest_date = str(valid["date"].iloc[-1])[:10]

    result = {
        "symbol": symbol,
        "prediction": _LABEL_MAP.get(pred_label, "平"),
        "prediction_code": pred_label,
        "confidence": round(confidence, 4),
        "probabilities": prob_dict,
        "feature_importance": [],
        "walk_forward": {
            "rounds": len(wf_results),
            "overall_accuracy": overall_acc,
            "overall_correct": overall_correct,
            "overall_total": overall_total,
            "details": wf_results,
        },
        "model_info": {
            "algorithm": "LSTM",
            "seq_len": seq_len,
            "hidden": HIDDEN,
            "layers": LAYERS,
            "dropout": DROPOUT,
            "train_window": train_size,
            "test_window": test_window,
            "n_features": len(feature_cols),
            "n_data_rows": n,
            "device": device,
            "elapsed_sec": round(time.time() - t0, 2),
            "predicted_at": datetime.now().isoformat(),
            "label_note": "latest row is last labeled sample (forward_days already dropped)",
        },
        "latest_date": latest_date,
    }

    if save:
        _save_result(symbol, result)

    return result


def _save_result(symbol: str, result: dict):
    data_dir = os.path.join(STOCK_DATA_DIR, symbol)
    os.makedirs(data_dir, exist_ok=True)
    path = os.path.join(data_dir, "lstm_prediction.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    log.info("LSTM 预测已保存 → %s", path)


def _load_xgb_for_compare(symbol: str) -> dict | None:
    """Read XGB cache from STOCK_DATA_DIR (honors monkeypatch in tests)."""
    path = os.path.join(STOCK_DATA_DIR, symbol, "xgb_prediction.json")
    if os.path.isfile(path):
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    return None


def load_lstm_prediction(symbol: str) -> dict | None:
    path = os.path.join(STOCK_DATA_DIR, symbol, "lstm_prediction.json")
    if os.path.isfile(path):
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    return None


def generate_lstm_report(symbol: str, result: dict | None = None) -> str:
    """生成 LSTM 预测 Markdown 报告（含可选 XGBoost 对比）。"""
    if result is None:
        result = load_lstm_prediction(symbol)
    if result is None:
        return f"## LSTM 预测\n\n**错误:** 无结果，请先运行 train_and_predict({symbol!r})"

    if "error" in result:
        return f"## LSTM 预测\n\n**错误:** {result['error']}"

    pred = result["prediction"]
    conf = result.get("confidence", 0)
    probs = result.get("probabilities", {})
    wf = result.get("walk_forward", {})
    info = result.get("model_info", {})

    pred_icon = {"涨": "🟢", "跌": "🔴", "平": "⚪"}.get(pred, "⚪")
    if conf >= 0.7:
        conf_label = "高"
    elif conf >= 0.5:
        conf_label = "中"
    else:
        conf_label = "低"

    lines = [
        f"# {symbol} LSTM 机器学习预测（研究原型）",
        f"> 预测方向: {pred_icon} **{pred}** | 置信度: **{conf:.1%}** ({conf_label})",
        f"> Walk-Forward 历史准确率: **{wf.get('overall_accuracy', 0):.1%}** "
        f"({wf.get('overall_correct', 0)}/{wf.get('overall_total', 0)})",
        "",
        "## 预测概率分布",
        "",
        "| 方向 | 概率 | 可视化 |",
        "|------|------|--------|",
    ]
    for label in ["涨", "平", "跌"]:
        p = probs.get(label, 0)
        bar = "█" * int(p * 20) + "░" * (20 - int(p * 20))
        icon = "🟢" if label == "涨" else "🔴" if label == "跌" else "⚪"
        lines.append(f"| {icon} {label} | {p:.1%} | {bar} |")
    lines.append("")

    if wf.get("details"):
        lines.extend([
            "## Walk-Forward 验证详情",
            "",
            "| 轮次 | 训练集 | 测试集 | 正确 | 准确率 |",
            "|------|--------|--------|------|--------|",
        ])
        for d in wf["details"]:
            acc = d["accuracy"]
            icon = "✅" if acc >= 0.6 else "⚠️" if acc >= 0.4 else "❌"
            lines.append(
                f"| {d['round']} | {d['train_size']} | {d['test_size']} | "
                f"{d['correct']} | {icon} {acc:.0%} |"
            )
        lines.append("")

    # XGBoost comparison
    lines.extend(["## 与 XGBoost 对比", ""])
    xgb = _load_xgb_for_compare(symbol)
    lines.append("| 模型 | 预测方向 | 置信度 | WF准确率 | 缓存时间 |")
    lines.append("|------|----------|--------|----------|----------|")
    lines.append(
        f"| LSTM | {pred} | {conf:.1%} | {wf.get('overall_accuracy', 0):.1%} | "
        f"{info.get('predicted_at', '')[:19]} |"
    )
    if xgb and "error" not in xgb:
        xgb_wf = xgb.get("walk_forward", {})
        xgb_ts = (
            xgb.get("timestamp")
            or xgb.get("model_info", {}).get("predicted_at")
            or ""
        )
        # file mtime fallback
        if not xgb_ts:
            xp = os.path.join(STOCK_DATA_DIR, symbol, "xgb_prediction.json")
            if os.path.isfile(xp):
                xgb_ts = datetime.fromtimestamp(os.path.getmtime(xp)).isoformat(timespec="seconds")
        lines.append(
            f"| XGBoost | {xgb.get('prediction', 'N/A')} | "
            f"{float(xgb.get('confidence', 0)):.1%} | "
            f"{float(xgb_wf.get('overall_accuracy', 0)):.1%} | {str(xgb_ts)[:19]} |"
        )
    else:
        lines.append("| XGBoost | — | — | — | 未找到 XGBoost 结果，可先跑 `model_xgboost` |")
    lines.append("")

    lines.extend([
        "## 模型信息",
        "",
        "| 项目 | 值 |",
        "|------|---|",
        f"| 算法 | {info.get('algorithm', 'LSTM')} |",
        f"| seq_len | {info.get('seq_len', 'N/A')} |",
        f"| hidden / layers | {info.get('hidden', 'N/A')} / {info.get('layers', 'N/A')} |",
        f"| 训练窗口 | {info.get('train_window', 'N/A')} 交易日 |",
        f"| 特征数 | {info.get('n_features', 'N/A')} |",
        f"| 数据行数 | {info.get('n_data_rows', 'N/A')} |",
        f"| device | {info.get('device', 'N/A')} |",
        f"| 耗时(秒) | {info.get('elapsed_sec', 'N/A')} |",
        f"| 预测时间 | {str(info.get('predicted_at', ''))[:16]} |",
        f"| 标签说明 | {info.get('label_note', '')} |",
        "",
        "## Phase B",
        "",
        "明日价格 LSTM 回归 **尚未实现**（`train_and_predict_price` 为 Phase B 占位）。",
        "",
        "> 研究原型：未接入 UI / Scanner；特征窗口 LSTM，与 XGBoost 同标签便于对比。",
        "",
    ])

    report = "\n".join(lines)
    report_path = os.path.join(STOCK_DATA_DIR, symbol, "lstm-report.md")
    os.makedirs(os.path.dirname(report_path), exist_ok=True)
    with open(report_path, "w", encoding="utf-8") as f:
        f.write(report)
    log.info("LSTM 报告已保存 → %s", report_path)
    return report


if __name__ == "__main__":
    import argparse

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    parser = argparse.ArgumentParser(description="LSTM 5-day direction research prototype")
    parser.add_argument("symbol", nargs="?", default="600519")
    parser.add_argument("--seq-len", type=int, default=None)
    parser.add_argument("--fast", action="store_true",
                        help="Smoke mode: n_rounds=3, max_epochs=8, seq_len=20")
    args = parser.parse_args()

    kwargs = {"save": True}
    if args.fast:
        kwargs.update(n_rounds=3, max_epochs=8, seq_len=20)
    if args.seq_len is not None:
        kwargs["seq_len"] = args.seq_len

    sym = args.symbol
    result = train_and_predict(sym, **kwargs)
    if "error" in result:
        print(f"错误: {result['error']}")
    else:
        print(f"\n预测: {result['prediction']} (置信度: {result['confidence']:.1%})")
        print(f"概率: {result['probabilities']}")
        print(f"Walk-Forward 准确率: {result['walk_forward']['overall_accuracy']:.1%}")

    print("\n" + "=" * 60)
    report = generate_lstm_report(sym, result)
    print(report)
