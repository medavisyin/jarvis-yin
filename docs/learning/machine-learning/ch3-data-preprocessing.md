# Chapter 3: Data Preprocessing — Turning Raw Data Into Something Models Can Learn

> This chapter teaches how to clean, scale, and encode data before training.
> Preprocessing is not optional polish; it is part of what makes learning stable and honest.

---

## Why Preprocessing Matters

Real datasets rarely arrive as neat tables of numbers that every algorithm accepts equally. Columns may be missing, measured on different scales, or stored as text labels. If you feed that mixture directly into many models, two things tend to happen:

1. **Training fails or becomes unstable** — Some algorithms require numeric inputs only, or they blow up when one feature has values in the millions and another is between 0 and 1.
2. **The model learns the wrong thing** — A model might treat a product ID as a magnitude, or let missingness itself become a spurious signal because NaNs were silently converted in a misleading way.

```
Without preprocessing:
  Feature "income" in dollars: 120000
  Feature "age": 35
  Feature "country": "DE"

Many linear models and distance-based models effectively "listen" loudest
to the largest numbers — income dominates age before any real pattern appears.
```

Preprocessing aligns representations with what the algorithm assumes: comparable scales for distance-sensitive methods, explicit handling of unknown values, and consistent rules for categories. Done wrong, preprocessing also causes **data leakage** (information from the test set influencing training). This chapter ties preprocessing to the train/test discipline from Chapter 2.

---

## Handling Missing Values

### Why Data Has Gaps

Missing values appear for many reasons: sensors failed, users skipped optional fields, merges between tables did not find a match, or a value was not recorded yet in time series. A missing entry is **not** automatically "zero" — it means "unknown," and treating it as zero without a plan is a common source of bias.

### Strategies

| Strategy | When It Helps | Risk |
|----------|---------------|------|
| **Drop rows** | Few rows are missing and missingness is random | You lose data; if missingness correlates with the label, you bias the sample |
| **Mean / median imputation** | Numeric features; median is robust to outliers | Distorts variance and correlations; can underestimate uncertainty |
| **Mode imputation** | Low-cardinality categorical-like numeric codes | Same distortion risks as mean/median |
| **Forward-fill (time series)** | Values persist until the next observation (e.g. last known price) | Assumes "no change" — wrong if gaps hide real moves |

### sklearn `SimpleImputer`

`SimpleImputer` replaces missing values with a chosen statistic or constant. The critical rule from supervised learning still applies:

**Fit the imputer on training data only, then transform train and test with those learned values.**

If you compute the mean on train+test together, the imputed values carry information from the test set into what the model sees during training — that is leakage.

```python
import numpy as np
import pandas as pd
from sklearn.impute import SimpleImputer
from sklearn.model_selection import train_test_split

df = pd.DataFrame({
    "age": [25, np.nan, 41, 33],
    "income": [50000, 62000, np.nan, 71000],
})
y = np.array([0, 1, 0, 1])

X_train, X_test, y_train, y_test = train_test_split(
    df, y, test_size=0.25, random_state=42
)

imputer = SimpleImputer(strategy="median")
imputer.fit(X_train)

X_train_imp = imputer.transform(X_train)
X_test_imp = imputer.transform(X_test)
```

For time-indexed data, pandas `ffill` is often applied **within** each series after you have respected the temporal split (only past values inform the fill for the training region). sklearn does not replace domain logic for ordered data; it gives generic column-wise imputation you can slot into a `Pipeline`.

---

## Feature Scaling

### When Scaling Matters

Algorithms that combine features with **weights** or compute **distances** treat larger numeric ranges as more influential unless you rescale.

| Usually benefit from scaling | Often fine without scaling |
|------------------------------|----------------------------|
| Linear / logistic regression (with regularization) | Decision trees |
| Support vector machines | Random forests |
| k-nearest neighbors | Gradient boosting (XGBoost, etc.) — still sometimes helps |
| Neural networks | Rule-based splits on raw thresholds can work on raw scales |

Trees split on thresholds ("is `age` > 35?"); multiplying all incomes by 0.001 does not change the relative ordering of examples for that split. Distance-based methods, by contrast, sum squared differences across dimensions — one large-scale column dominates.

### StandardScaler vs MinMaxScaler — Visual Intuition

**StandardScaler** subtracts the mean and divides by the standard deviation per feature. After fitting on training data, each column has roughly mean 0 and variance 1 on that training sample. New points can land outside [-1, 1]; outliers can stretch the standard deviation and shrink everything else.

**MinMaxScaler** maps each feature to a fixed range (default [0, 1]) using min and max from the training fit. It preserves zero entries if the min was 0. It is sensitive to outliers: one extreme max pulls the rest of the values toward zero.

```
Original feature values:     [ 10,  20,  30,  40 ]
Standardized (conceptually): roughly centered, spread ~1 std
MinMax to [0,1]:             [ 0.0, 0.33, 0.67, 1.0 ]
```

### Fit on Train, Transform on Test

Same rule as imputation: `fit` (or `fit_transform`) on `X_train` only; `transform` on `X_test` using the statistics learned from train.

```python
from sklearn.preprocessing import StandardScaler, MinMaxScaler

scaler = StandardScaler()
X_train_scaled = scaler.fit_transform(X_train_imp)
X_test_scaled = scaler.transform(X_test_imp)

mm = MinMaxScaler()
X_train_mm = mm.fit_transform(X_train_imp)
X_test_mm = mm.transform(X_test_imp)
```

---

## Encoding Categorical Data

### What Categories Are

A **categorical** column takes values from a finite set of labels: country codes, product tiers, "yes/no/no answer." Algorithms that need dense numeric matrices cannot use raw strings; you must choose a numeric representation.

### One-Hot Encoding

**One-hot encoding** creates a separate binary column per category. A row has 1 in the column for its category and 0 elsewhere. That avoids inventing an ordering where none exists (treating "cat", "dog", "fish" as 1, 2, 3 implies fish > dog).

**pandas** — quick exploration:

```python
df_cat = pd.DataFrame({"color": ["red", "blue", "red", "green"]})
pd.get_dummies(df_cat, columns=["color"], dtype=int)
```

**sklearn** — preferred inside pipelines because it remembers category levels and handles unseen categories in test (with configuration):

```python
from sklearn.preprocessing import OneHotEncoder

ohe = OneHotEncoder(handle_unknown="ignore", sparse_output=False)
X_train_ohe = ohe.fit_transform(X_train[["color"]])
X_test_ohe = ohe.transform(X_test[["color"]])
```

`handle_unknown="ignore"` produces all-zero rows for categories that appeared only in test, instead of raising an error.

### Ordinal Encoding

When categories have a **meaningful order** (e.g. "low", "medium", "high"), **ordinal encoding** maps them to ordered integers. sklearn's `OrdinalEncoder` can learn the mapping from data or you supply categories explicitly.

```python
from sklearn.preprocessing import OrdinalEncoder

sizes = pd.DataFrame({"size": ["S", "M", "L", "M", "S"]})
enc = OrdinalEncoder(categories=[["S", "M", "L"]])
enc.fit_transform(sizes)
```

Using ordinal encoding for **nominal** categories (no natural order) tells the model that one label is "greater" than another — that is often wrong.

### The High-Cardinality Trap

If a column has thousands of unique values (user IDs, ZIP codes, tickers), one-hot expansion creates thousands of sparse columns. You may run out of memory, slow training, and invite overfitting on rare categories. Mitigations include **target encoding** (careful, easy to leak), **embedding** layers in deep learning, **hashing**, grouping rare levels into `"other"`, or leaving high-cardinality IDs out unless there is a real hypothesis about them.

---

## The sklearn Pipeline

A **`Pipeline`** chains steps with names. Each step except the last must implement `fit` and `transform`; the last step is typically an estimator with `fit` and `predict` (or `predict_proba`).

Benefits:

- One call to `fit` runs preprocessing then the model in order.
- Cross-validation refits preprocessing **inside each fold** on training folds only — the correct way to tune without leakage.
- You cannot accidentally preprocess the full dataset before splitting when the pipeline is fit only on training data passed from a CV splitter.

```python
from sklearn.pipeline import Pipeline
from sklearn.linear_model import LogisticRegression

pipe = Pipeline([
    ("imputer", SimpleImputer(strategy="median")),
    ("scaler", StandardScaler()),
    ("clf", LogisticRegression(max_iter=1000)),
])
pipe.fit(X_train, y_train)
pipe.predict(X_test)
```

### ColumnTransformer for Mixed Types

Real tables mix numeric and categorical columns. **`ColumnTransformer`** applies different transformers to different column subsets, then **concatenates** the results into one matrix for the classifier.

```python
from sklearn.compose import ColumnTransformer

numeric_features = ["age", "income"]
categorical_features = ["color"]

preprocessor = ColumnTransformer(
    transformers=[
        ("num", Pipeline([
            ("imputer", SimpleImputer(strategy="median")),
            ("scaler", StandardScaler()),
        ]), numeric_features),
        ("cat", OneHotEncoder(handle_unknown="ignore", sparse_output=False), categorical_features),
    ]
)

clf_pipeline = Pipeline([
    ("prep", preprocessor),
    ("model", LogisticRegression(max_iter=1000)),
])
```

The column lists must match your `DataFrame` after you drop the target column from `X`. The **End-to-End Example** at the end of this chapter runs the same structure on a larger synthetic table.

---

## Common Preprocessing Mistakes

| Mistake | Why It Hurts |
|---------|--------------|
| **Fitting on all data before split** | Statistics and encoders see test distribution; reported performance is optimistically biased |
| **Encoding, then splitting** | Category frequencies from test influence how you treat rare levels or imputation |
| **Looking at test labels while designing fills** | Even "peeking" at `y_test` to choose strategy leaks target information |
| **Different preprocessing code paths for train vs test** | Train and test must use the **same** fitted objects (pipelines enforce this) |
| **Scaling target `y` for classification** | Classification labels are categories; scaling `y` is usually meaningless |

The safe pattern: **split first**, build a **pipeline**, `fit` the pipeline on train (or on each CV training fold), evaluate on held-out data.

---

## Summary Table

| Topic | Core idea | sklearn building blocks |
|-------|-----------|-------------------------|
| Missing values | Missing means unknown; choose strategy with domain in mind | `SimpleImputer` |
| Scaling | Put comparable weight on features for distance / linear models | `StandardScaler`, `MinMaxScaler` |
| Categories | Avoid false order; expand or ordinally encode deliberately | `OneHotEncoder`, `OrdinalEncoder`, `pd.get_dummies` |
| Composition | One fitted object from raw table to prediction | `Pipeline`, `ColumnTransformer` |
| Evaluation honesty | Any `fit` uses training data only | `train_test_split` + pipeline or `cross_val_score` on pipeline |

---

## End-to-End Example

Below is a single script: load a mixed-type frame, split, preprocess with `ColumnTransformer`, train `LogisticRegression`, and report accuracy. It follows the rules above end to end.

```python
import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, classification_report
from sklearn.model_selection import train_test_split
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler

rng = np.random.default_rng(42)
n = 600
ages = np.clip(rng.normal(42, 12, n), 18, 80).astype(float)
income = np.clip(rng.lognormal(10.8, 0.3, n), 20_000, 180_000).astype(float)
city = rng.choice(["East", "West", "North"], size=n, p=[0.45, 0.35, 0.2])
ages[rng.choice(n, size=24, replace=False)] = np.nan
income[rng.choice(n, size=24, replace=False)] = np.nan

east_west = np.isin(city, ["East", "West"])
logit = (
    -1.0
    + 0.03 * np.nan_to_num(ages, nan=np.nanmedian(ages))
    + 2.5e-6 * np.nan_to_num(income, nan=np.nanmedian(income))
    + 0.65 * east_west.astype(float)
)
y = (rng.random(n) < (1 / (1 + np.exp(-logit)))).astype(int)
df = pd.DataFrame({"age": ages, "income": income, "city": city, "label": y})
X = df.drop(columns=["label"])
y = df["label"]

X_train, X_test, y_train, y_test = train_test_split(
    X, y, test_size=0.2, random_state=42, stratify=y
)

numeric_features = ["age", "income"]
categorical_features = ["city"]

preprocessor = ColumnTransformer(
    transformers=[
        ("num", Pipeline([
            ("imputer", SimpleImputer(strategy="median")),
            ("scaler", StandardScaler()),
        ]), numeric_features),
        ("cat", OneHotEncoder(handle_unknown="ignore", sparse_output=False), categorical_features),
    ]
)

clf = Pipeline([
    ("prep", preprocessor),
    ("model", LogisticRegression(max_iter=2000)),
])

clf.fit(X_train, y_train)
pred = clf.predict(X_test)
print("Accuracy:", accuracy_score(y_test, pred))
print(classification_report(y_test, pred))
```

---

*Previous: [Chapter 2 — Model Training & Evaluation](ch2-model-training-evaluation.md)*  
*Next: [Feature Engineering & TA](feature-engineering-ta.md) — How to create meaningful input features from raw stock data*
