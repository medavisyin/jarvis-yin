# LSTM 5-Day Direction Research Prototype Implementation Plan

> **For the implementing agent:** Follow this plan task-by-task. Complete each step, verify it works, then move to the next.

**Goal:** Ship a standalone PyTorch LSTM research prototype that predicts a single A-share's 5-day direction (涨/平/跌), runs Walk-Forward validation, writes JSON + Markdown reports, and side-by-side compares against cached XGBoost metrics — without wiring UI/Scanner.

**Architecture:** New `scripts/stock/model_lstm.py` reuses `features.build_features` / `get_feature_names` and the same `target` labels as `model_xgboost.py`. Build `seq_len`-day feature windows, per-fold median impute + z-score (train stats only), train a small `LSTMClassifier`, Walk-Forward like XGB, predict latest row, save `lstm_prediction.json` + `lstm-report.md`. Phase B price API is a documented stub only.

**Tech Stack:** Python 3, PyTorch (`torch` already installed), NumPy/Pandas, scikit-learn LabelEncoder, existing `features.py` / `config.STOCK_DATA_DIR`, pytest.

**Approved decisions (do not re-litigate):**
- Research prototype only — **no** UI / Scanner / routes changes
- Approach: **feature-window LSTM** (same tabular features as XGB), not raw OHLCV-only, not hybrid
- Phase A only: 5-day direction; Phase B = `NotImplementedError` stub + report one-liner
- Success: single symbol train → WF → MD/JSON; compare to XGB **from cache** (`xgb_prediction.json` / `load_prediction`); do **not** force retrain XGB
- Defaults: `seq_len=30`, hidden=64, layers=2, dropout=0.2; WF skeleton aligned with XGB (`_TRAIN_WINDOW≈500`, `_TEST_WINDOW=5`, `_N_ROUNDS≤15`)
- Persist results JSON under `STOCK_DATA_DIR/{symbol}/`; no model-weight persistence required in Phase A
- Do not replace or modify default XGBoost production paths

**Out of scope:**
- LightGBM / ensemble wiring
- Batch multi-symbol CLI
- Full strategy backtest charts
- Implementing Phase B regressors
- Docs under `docs/stock-modules/` (optional follow-up; not required for green verification)

**Plan amendments (from critical review — do not re-litigate):**

1. **No `think-mcp` in this environment** — review used agent structured reasoning only.
2. **Test imports (mandatory):** Top of `tests/test_model_lstm.py` must insert `scripts/stock` on `sys.path` exactly like `tests/test_board_filters.py` (not "check conftest").
3. **Label encoding (mandatory):** `CrossEntropyLoss` needs classes `{0,1,2}`. Use `sklearn.preprocessing.LabelEncoder` fitted on `[-1, 0, 1]` (same as XGB). Map probs back via `inverse_transform` + `LABEL_MAP`. Do not feed raw `-1` labels into CE.
4. **Delete phantom helper:** There is no `get_default_feature_cols_for_test`. Synthetic tests pass explicit `feature_cols=["f0",...]`.
5. **Task 3 test must be complete code** (not comment stubs), and call `train_and_predict(..., save=False)`.
6. **WF edge cases:** If a fold yields **0 test sequences** (seq warm-up) or **&lt;2 train classes**, skip the round (log + continue), same spirit as XGB single-class skip.
7. **Final predict date:** After `dropna(subset=["target"])`, "latest" is the last row **with a label** (last `forward_days` calendar rows already dropped) — same as XGB; mention in report `model_info` / 备注.
8. **Report test assertion bug:** Do **not** write `assert "Phase B" in report or "尚未实现"` (operator precedence makes it always pass). Use: `assert ("Phase B" in report) or ("尚未实现" in report)`.
9. **Runtime guard:** Production defaults can be slow on CPU. Add CLI `--fast` → `n_rounds=3`, `max_epochs=8`, `seq_len=20` for smoke; document that full run may take several minutes.
10. **XGB comparison caveat:** If cache exists, print/include XGB `timestamp` / file mtime in the comparison section so stale caches are obvious.
11. **Error-path test (add to Task 3 or 4):** Too-short synthetic data returns `{"error": ...}` without traceback.

---

### Task 1: Sequence builder + fold scaler (TDD)

**Files:**
- Create: `scripts/stock/model_lstm.py` (helpers only first)
- Create: `tests/test_model_lstm.py`

**Step 1: Write failing tests**

```python
# tests/test_model_lstm.py
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
```

**Step 2: Run tests to verify they fail**

Run: `pytest tests/test_model_lstm.py::test_build_sequences_shapes_and_alignment tests/test_model_lstm.py::test_fit_transform_scaler_no_test_leakage -v`

Expected: FAIL (`ImportError` or missing symbols).

**Step 3: Minimal implementation**

In `scripts/stock/model_lstm.py`:

```python
"""LSTM 5-day direction prototype (research). Phase B price stub only."""
from __future__ import annotations

import numpy as np


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
```

If stock tests already have the `sys.path` block from Step 1, do not duplicate.

**Step 4: Run tests to verify they pass**

Run: `pytest tests/test_model_lstm.py::test_build_sequences_shapes_and_alignment tests/test_model_lstm.py::test_fit_transform_scaler_no_test_leakage -v`

Expected: PASS

---

### Task 2: Phase B stub + LSTM module skeleton (TDD)

**Files:**
- Modify: `scripts/stock/model_lstm.py`
- Modify: `tests/test_model_lstm.py`

**Step 1: Write failing test**

```python
def test_phase_b_price_stub_raises():
    from model_lstm import train_and_predict_price
    with pytest.raises(NotImplementedError, match="Phase B"):
        train_and_predict_price("600519")
```

**Step 2: Run test — expect FAIL** (`ImportError` / missing function)

**Step 3: Implement stub + torch model class**

```python
def train_and_predict_price(symbol: str, *args, **kwargs):
    """Phase B placeholder — next-day price regression not implemented."""
    raise NotImplementedError(
        "Phase B (明日价格 LSTM 回归) 尚未实现 — 见 docs/plans/2026-08-05-lstm-direction-prototype.md"
    )


# LSTMClassifier: nn.Module with LSTM(batch_first=True) + Linear(hidden, 3)
# Constants: SEQ_LEN=30, HIDDEN=64, LAYERS=2, DROPOUT=0.2, LABEL_MAP={-1:"跌",0:"平",1:"涨"}
# Mirror XGB windows: _TRAIN_WINDOW=500, _TEST_WINDOW=5, _N_ROUNDS=15, _MIN_DATA_ROWS=300
```

Keep `LSTMClassifier.forward` returning logits `[B, 3]`.

**Step 4: pytest for stub — expect PASS**

---

### Task 3: Walk-Forward train_and_predict (TDD with mocks / tiny synthetic)

**Files:**
- Modify: `scripts/stock/model_lstm.py`
- Modify: `tests/test_model_lstm.py`

**Step 1: Write failing tests — synthetic feature matrix, no disk I/O**

```python
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
```

Implement optional kwargs on `train_and_predict` for test speed (`seq_len`, `train_window`, `test_window`, `n_rounds`, `max_epochs`, `save`, `device="cpu"`). Production defaults match approved design. Encode labels with `LabelEncoder.fit([-1, 0, 1])` before CE loss.

**Step 2: Run test — expect FAIL**

**Step 3: Implement `train_and_predict`**

Algorithm (align with `model_xgboost.train_and_predict`):

1. If `feature_df is None`: `from features import build_features, get_feature_names` then build.
2. Drop rows with NaN `target`; matrix `X_all = values[feature_cols]`, `y_all = target.astype(int)`.
3. For each WF round (same index math as XGB lines 135–181):
   - Slice train/test **row** ranges on the flat series (not yet sequences).
   - `FitScaler.fit(train_rows)` → transform train+test rows (and any history rows used only to warm up test sequences).
   - `build_sequences` on scaled train; for test, build sequences from scaled rows `train_start:test_end` but **only score ends in `[test_start, test_end)`**.
   - Skip round if `&lt;2` train classes or **0** test sequences.
   - Train `LSTMClassifier` with Adam + CrossEntropyLoss on **encoded** labels (+ optional class weights); early stop on last 10% of train sequences as val.
   - Record accuracy on test-end labels (decode preds back to {-1,0,1} before compare).
4. Final fit on last `train_size` rows → predict sequence ending at last **labeled** row → softmax → `LABEL_MAP`.
5. Return dict mirroring XGB fields; `feature_importance` may be `[]`; set `model_info.algorithm = "LSTM"` and note labeled-as-of semantics.
6. Gate persistence with `save=False` by default in tests; CLI uses `save=True`.

**Leakage checklist (must hold):**
- Scaler fit only on train rows of the fold
- Target uses existing `features._add_target` (future return) — do not peek beyond label definition already used by XGB
- Val split for early stopping is a suffix of the **train** sequences only

**Step 4: pytest — expect PASS** (allow ~1–2 minutes CPU)

---

### Task 4: Persist JSON + Markdown report with XGB comparison

**Files:**
- Modify: `scripts/stock/model_lstm.py`
- Modify: `tests/test_model_lstm.py`

**Step 1: Write failing tests**

```python
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
```

**Step 2: FAIL then implement**

- Save: `{STOCK_DATA_DIR}/{symbol}/lstm_prediction.json`
- Report: `{STOCK_DATA_DIR}/{symbol}/lstm-report.md` (name parallel to `xgb-report.md`)
- Load XGB via `from model_xgboost import load_prediction` or read JSON; if missing, section says 未找到 XGBoost 结果
- Comparison table columns: 模型 | 预测方向 | 置信度 | WF准确率 | 缓存时间(XGB)
- Include Phase B one-liner

**Step 3: pytest PASS**

---

### Task 5: CLI `__main__` + smoke instructions

**Files:**
- Modify: `scripts/stock/model_lstm.py` (`if __name__ == "__main__"`)

**Step 1: CLI**

```text
cd scripts/stock
python model_lstm.py 600519
python model_lstm.py 600519 --fast
# optional: --seq-len 30
```

`--fast` → `n_rounds=3`, `max_epochs=8`, `seq_len=20` (override unless user also passes explicit flags). Print prediction, confidence, WF accuracy; call `generate_lstm_report` with `save=True`.

**Step 2: Manual smoke (when data present)**

Prefer `--fast` first. Full defaults may take several minutes on CPU.  
If `xgb_prediction.json` missing, optionally run `python model_xgboost.py <sym>` first for a full comparison table.

Expected: no traceback; files `lstm_prediction.json` + `lstm-report.md` written.

**Step 3: Full unit suite**

Run: `pytest tests/test_model_lstm.py -v`  
Expected: all PASS

---

### Task 6: Verification Summary

- [ ] `build_sequences` + `FitScaler` tests prove shapes and no test-stat leakage
- [ ] `train_and_predict_price` raises `NotImplementedError` mentioning Phase B
- [ ] Synthetic `train_and_predict` returns XGB-like schema with `algorithm: LSTM`; short data returns `error`
- [ ] Labels encoded 0/1/2 for CE; decoded for metrics/report
- [ ] Report mentions LSTM, XGBoost comparison (or missing cache), Phase B note; XGB cache time shown when present
- [ ] JSON/MD written under symbol data dir (tmp in tests; real dir on smoke)
- [ ] CLI supports `--fast`
- [ ] No changes to `scanner.py`, `routes/stock.py`, or UI templates
- [ ] Existing XGB modules untouched except optional read via `load_prediction`

---

## Reference snippets (executor)

**XGB WF loop index math:** `scripts/stock/model_xgboost.py` ~135–181, final predict ~190–260.  
**Labels:** `features.build_features(..., forward_days=5, threshold=2.0)` → `target` in {-1,0,1}.  
**XGB cache path:** `{STOCK_DATA_DIR}/{symbol}/xgb_prediction.json` via `load_prediction`.  
**Torch:** use CPU; `torch.manual_seed(42)`.

## Suggested commit message (only if user asks to commit)

```
feat(stock): add LSTM 5-day direction research prototype

Standalone walk-forward LSTM using feature windows, JSON/MD reports,
and optional XGBoost cache comparison; Phase B price API stubbed.
```
