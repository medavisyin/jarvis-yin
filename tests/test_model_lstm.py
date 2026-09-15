"""LSTM 5-day direction research prototype — unit tests."""

from __future__ import annotations

import os
import sys

import numpy as np
import pytest

_STOCK = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "scripts", "stock"))
if _STOCK not in sys.path:
    sys.path.insert(0, _STOCK)


def test_build_sequences_shapes_and_alignment():
    from model_lstm import build_sequences

    n, f, t = 10, 3, 4
    X = np.arange(n * f, dtype=float).reshape(n, f)
    y = np.arange(n)
    Xs, ys, ends = build_sequences(X, y, seq_len=t)
    assert Xs.shape == (n - t + 1, t, f)
    assert ys.shape == (n - t + 1,)
    assert ends[0] == t - 1
    assert ys[0] == y[t - 1]
    assert np.allclose(Xs[0, -1], X[t - 1])


def test_fit_transform_scaler_no_test_leakage():
    from model_lstm import FitScaler

    rng = np.random.default_rng(0)
    train = rng.normal(size=(20, 2))
    test = rng.normal(loc=100.0, size=(5, 2))
    scaler = FitScaler.fit(train)
    tr = scaler.transform(train)
    te = scaler.transform(test)
    assert abs(tr[:, 0].mean()) < 0.5
    assert abs(te[:, 0].mean()) > 10


def test_phase_b_price_stub_raises():
    from model_lstm import train_and_predict_price

    with pytest.raises(NotImplementedError, match="Phase B"):
        train_and_predict_price("600519")


def test_train_and_predict_synthetic_runs():
    import pandas as pd
    from model_lstm import train_and_predict

    n, f = 200, 5
    rng = np.random.default_rng(42)
    cols = [f"f{i}" for i in range(f)]
    data = {c: rng.normal(size=n) for c in cols}
    data["target"] = np.array([(-1, 0, 1)[i % 3] for i in range(n)])
    data["date"] = pd.date_range("2020-01-01", periods=n, freq="B")
    df = pd.DataFrame(data)

    result = train_and_predict(
        "SYN",
        feature_df=df,
        feature_cols=cols,
        seq_len=10,
        train_window=80,
        test_window=5,
        n_rounds=3,
        max_epochs=3,
        save=False,
        device="cpu",
    )
    assert "error" not in result, result
    for k in ("prediction", "confidence", "probabilities", "walk_forward", "model_info"):
        assert k in result
    assert result["model_info"]["algorithm"] == "LSTM"
    assert result["prediction"] in {"涨", "平", "跌"}


def test_train_and_predict_too_short_returns_error():
    import pandas as pd
    from model_lstm import train_and_predict

    cols = ["f0", "f1"]
    df = pd.DataFrame({
        "f0": [1.0, 2.0, 3.0],
        "f1": [0.1, 0.2, 0.3],
        "target": [1, 0, -1],
    })
    result = train_and_predict(
        "SHORT", feature_df=df, feature_cols=cols, seq_len=10, save=False,
    )
    assert "error" in result


def test_generate_lstm_report_includes_phase_b_note_and_comparison(tmp_path, monkeypatch):
    import json
    import model_lstm as ml

    monkeypatch.setattr(ml, "STOCK_DATA_DIR", str(tmp_path))
    sym_dir = tmp_path / "T"
    sym_dir.mkdir()
    (sym_dir / "xgb_prediction.json").write_text(
        json.dumps({
            "prediction": "涨",
            "confidence": 0.55,
            "walk_forward": {"overall_accuracy": 0.4},
            "timestamp": "2026-01-01T00:00:00",
        }),
        encoding="utf-8",
    )
    result = {
        "symbol": "T",
        "prediction": "平",
        "confidence": 0.4,
        "probabilities": {"涨": 0.3, "平": 0.4, "跌": 0.3},
        "walk_forward": {"overall_accuracy": 0.35, "rounds": 1, "details": []},
        "model_info": {"algorithm": "LSTM"},
    }
    report = ml.generate_lstm_report("T", result)
    assert "LSTM" in report and "XGBoost" in report
    assert ("Phase B" in report) or ("尚未实现" in report)
    assert "Walk-Forward" in report


def test_save_result_writes_json(tmp_path, monkeypatch):
    import json
    import model_lstm as ml

    monkeypatch.setattr(ml, "STOCK_DATA_DIR", str(tmp_path))
    result = {"symbol": "T", "prediction": "涨", "model_info": {"algorithm": "LSTM"}}
    ml._save_result("T", result)
    path = tmp_path / "T" / "lstm_prediction.json"
    assert path.is_file()
    assert json.loads(path.read_text(encoding="utf-8"))["prediction"] == "涨"
