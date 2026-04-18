# Chapter 2: Model Training & Evaluation — Is Your Model Actually Good?

> This chapter teaches how to train ML models properly, avoid common traps,
> and measure whether your model will work on real-world data.

---

## The Fundamental Problem: Overfitting

The #1 mistake in ML is building a model that **memorizes training data** instead of **learning general patterns**.

```
Analogy:
  Memorizing: Student memorizes exact exam answers from last year's test
              → Scores 100% on practice, fails the real exam (different questions)

  Learning:   Student understands the concepts
              → Scores 85% on practice, 82% on the real exam (consistent)
```

In ML terms:

| | Overfitting | Good Model |
|-|-------------|-----------|
| Training accuracy | 99% | 88% |
| Test accuracy | 60% | 85% |
| What happened | Memorized noise in training data | Learned real patterns |
| Analogy | Memorized last year's exam | Understood the subject |

**How to detect it:** Always measure performance on data the model has **never seen** during training.

---

## Train/Test Split — The Most Important Rule

**Never evaluate a model on the data it was trained on.** The standard approach:

```python
from sklearn.model_selection import train_test_split

# 80% for training, 20% for testing
X_train, X_test, y_train, y_test = train_test_split(
    X, y, test_size=0.2, random_state=42
)

# Train on training data ONLY
model.fit(X_train, y_train)

# Evaluate on test data (model has NEVER seen this)
predictions = model.predict(X_test)
accuracy = accuracy_score(y_test, predictions)
```

`random_state=42` makes the split reproducible — same split every time you run it, so results are comparable.

### For Time Series (Stocks): Order Matters!

For stock data, you **cannot** randomly shuffle and split. Future data must never leak into training:

```
WRONG (random split — future leaks into training):
  Train: [Jan, Mar, May, Jul, Sep, Nov]  ← includes future months!
  Test:  [Feb, Apr, Jun, Aug, Oct, Dec]

RIGHT (chronological split):
  Train: [Jan, Feb, Mar, Apr, May, Jun, Jul, Aug]   ← past only
  Test:  [Sep, Oct, Nov, Dec]                        ← future only
```

**In Jarvis:** The stock model uses **chronological splitting** — train on older data, test on newer data.

---

## Cross-Validation — More Reliable Than a Single Split

One train/test split might be lucky or unlucky. Cross-validation runs **multiple splits** and averages the results:

```
5-Fold Cross-Validation:

Fold 1: [TEST] [train] [train] [train] [train]  → accuracy: 87%
Fold 2: [train] [TEST] [train] [train] [train]  → accuracy: 84%
Fold 3: [train] [train] [TEST] [train] [train]  → accuracy: 89%
Fold 4: [train] [train] [train] [TEST] [train]  → accuracy: 86%
Fold 5: [train] [train] [train] [train] [TEST]  → accuracy: 85%

Average: 86.2% ± 1.8%  ← much more reliable than any single fold
```

```python
from sklearn.model_selection import cross_val_score

scores = cross_val_score(model, X, y, cv=5, scoring='accuracy')
print(f"Accuracy: {scores.mean():.1%} ± {scores.std():.1%}")
# → Accuracy: 86.2% ± 1.8%
```

A **small standard deviation** (± 1-3%) means your model is stable. A **large one** (± 10%+) means it depends heavily on which data it sees — something is wrong.

---

## Evaluation Metrics — Beyond "Accuracy"

Accuracy alone can be misleading. If 90% of stocks go up, a model that **always predicts "up"** has 90% accuracy but is useless.

### The Confusion Matrix

The confusion matrix shows what the model got right and wrong:

```
                    Predicted
                   UP    DOWN
Actual  UP    [  80  |  20  ]   ← 80 correct, 20 missed (should've said UP)
        DOWN  [  15  |  85  ]   ← 85 correct, 15 false alarms (said UP but was DOWN)
```

### Key Metrics

| Metric | Formula | What It Measures | Good For |
|--------|---------|-----------------|----------|
| **Accuracy** | correct / total | Overall correctness | Balanced datasets |
| **Precision** | true positives / predicted positives | "When it says BUY, how often is it right?" | When false alarms are costly |
| **Recall** | true positives / actual positives | "Of all real BUY signals, how many did it catch?" | When missing signals is costly |
| **F1 Score** | harmonic mean of precision & recall | Balance of precision and recall | Imbalanced datasets |

```python
from sklearn.metrics import classification_report, confusion_matrix

print(confusion_matrix(y_test, predictions))
print(classification_report(y_test, predictions))

#               precision    recall  f1-score   support
#        DOWN       0.81      0.85      0.83       100
#          UP       0.84      0.80      0.82       100
#    accuracy                           0.82       200
```

### Which Metric Matters for Stocks?

For stock prediction, **precision** often matters more than recall:
- High precision: "When the model says BUY, it's usually right" → you make money on trades
- Low precision, high recall: "The model catches every opportunity, but also gives many false signals" → you take lots of bad trades

**In Jarvis:** The stock model reports accuracy, F1 per class, and a confusion matrix.

---

## Feature Importance — What Did the Model Learn?

XGBoost can tell you which features contributed most to its predictions:

```python
import matplotlib.pyplot as plt
from xgboost import plot_importance

plot_importance(model, max_num_features=10)
plt.title("Top 10 Features")
plt.tight_layout()
plt.show()
```

```
Feature Importance (example):
  RSI_14          ████████████████  0.15
  MACD_signal     ██████████████    0.13
  volume_ratio    ████████████      0.11
  close_to_ma20   ██████████        0.09
  bb_width        ████████          0.08
  ...
```

This is valuable for:
- **Understanding** what the model relies on
- **Debugging** — if a nonsensical feature ranks high, something is wrong
- **Feature selection** — remove low-importance features to simplify the model

---

## Hyperparameter Tuning — Finding the Best Settings

Model parameters you set **before** training are called **hyperparameters**. They control the model's behavior:

| Hyperparameter | What It Controls | Too Low | Too High |
|---------------|-----------------|---------|----------|
| `n_estimators` | Number of trees | Underfitting (not enough learning) | Slow training, diminishing returns |
| `max_depth` | How deep each tree can grow | Simple trees, misses patterns | Complex trees, overfitting |
| `learning_rate` | How much each tree contributes | Slow learning, needs more trees | Overshooting, unstable |
| `min_child_weight` | Minimum data in a leaf node | More splits, complex (overfit risk) | Fewer splits, simpler (underfit risk) |

### Automatic Tuning with Grid Search

```python
from sklearn.model_selection import GridSearchCV
from xgboost import XGBClassifier

param_grid = {
    'n_estimators': [50, 100, 200],
    'max_depth': [3, 5, 7],
    'learning_rate': [0.01, 0.1, 0.3],
}

grid = GridSearchCV(
    XGBClassifier(),
    param_grid,
    cv=5,
    scoring='f1_weighted',
    verbose=1,
)
grid.fit(X_train, y_train)

print(f"Best params: {grid.best_params_}")
print(f"Best F1: {grid.best_score_:.3f}")
# → Best params: {'learning_rate': 0.1, 'max_depth': 5, 'n_estimators': 100}
# → Best F1: 0.872
```

This tries all 27 combinations (3 x 3 x 3) with 5-fold cross-validation each = 135 model trainings. For larger grids, use `RandomizedSearchCV` which samples randomly.

---

## Putting It All Together — A Complete Training Script

```python
from sklearn.datasets import load_iris
from sklearn.model_selection import train_test_split, cross_val_score
from sklearn.metrics import classification_report, confusion_matrix
from xgboost import XGBClassifier

# 1. Load data
X, y = load_iris(return_X_y=True)

# 2. Split
X_train, X_test, y_train, y_test = train_test_split(
    X, y, test_size=0.2, random_state=42
)

# 3. Cross-validate first (sanity check)
model = XGBClassifier(n_estimators=100, max_depth=3, learning_rate=0.1)
cv_scores = cross_val_score(model, X_train, y_train, cv=5)
print(f"CV Accuracy: {cv_scores.mean():.1%} ± {cv_scores.std():.1%}")

# 4. Train final model
model.fit(X_train, y_train)

# 5. Evaluate on held-out test set
predictions = model.predict(X_test)
print(f"\nConfusion Matrix:\n{confusion_matrix(y_test, predictions)}")
print(f"\n{classification_report(y_test, predictions)}")
```

---

## Summary

| Concept | Why It Matters |
|---------|---------------|
| **Train/test split** | Without it, you can't know if the model generalizes |
| **Cross-validation** | One split might be lucky; CV gives reliable estimates |
| **Overfitting** | The #1 enemy — memorization instead of learning |
| **Precision vs recall** | Accuracy alone is misleading for imbalanced data |
| **Feature importance** | Know what the model learned; debug bad features |
| **Hyperparameter tuning** | Same algorithm, different settings → very different results |

---

*Previous: [Chapter 1 — ML Fundamentals](ch1-ml-fundamentals.md)*
*Next: [Chapter 3 — Data Preprocessing](ch3-data-preprocessing.md) — Cleaning, scaling, encoding, and pipelines without leaking test data*
