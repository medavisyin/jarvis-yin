# Chapter 1: ML Fundamentals — What Machine Learning Actually Is

> This chapter teaches the core concepts of machine learning from scratch,
> then shows how each concept maps to what Jarvis does.

---

## What Is Machine Learning?

Machine learning is teaching a computer to **find patterns in data** instead of telling it exact rules.

```
Traditional Programming:
  Input: data + rules you wrote       → Output: answers
  Example: "If RSI < 30, buy"         → "Buy AAPL"

Machine Learning:
  Input: data + correct answers        → Output: rules it learned
  Example: 10,000 stock days + labels  → Model learns "when RSI < 32 AND volume > 1.5x AND MACD crosses up, buy"
```

The ML approach is powerful because:
- It can discover rules **too complex for humans to write** (combinations of 50+ features)
- It **adapts to new data** — retrain and it learns new patterns
- It can handle **uncertainty** — "73% probability of going up" is more useful than a rigid yes/no rule

### The Three Types of Machine Learning

| Type | What It Does | Example in Jarvis |
|------|-------------|-------------------|
| **Supervised learning** | Learn from labeled examples (input → correct answer) | Stock prediction: features → "up/flat/down" |
| **Unsupervised learning** | Find structure in unlabeled data | (Not used yet — could cluster similar documents) |
| **Reinforcement learning** | Learn by trial and reward/punishment | (Not used — used in ChatGPT's RLHF training) |

Jarvis uses **supervised learning** exclusively. You need labeled data — examples where you already know the right answer.

---

## What Is a Decision Tree?

A decision tree is the simplest supervised model to understand — it makes predictions by asking **yes/no questions**, exactly like a flowchart:

```
"Should I buy this stock?"

                    Price > 50-day average?
                    /                    \
                  Yes                     No
                 /                         \
        Volume > 1M?                   RSI < 30?
        /          \                   /        \
      Yes          No               Yes         No
       |            |                |            |
    BUY          SKIP             BUY          SKIP
```

The tree learns these rules **automatically from data**. You give it thousands of examples like "here are the stock features on day X, and here's whether the price went up" — it figures out which questions to ask and in what order.

### How Does It Learn the Questions?

The algorithm tries every possible split at every step and picks the one that **separates the classes best**:

```
All data: 600 stocks went up, 400 went down

Split on "RSI < 30":
  Left  (RSI < 30):  180 up, 20 down   ← very clean! mostly "up"
  Right (RSI >= 30): 420 up, 380 down   ← messy, needs more splitting

Split on "Volume > avg":
  Left  (high volume):  350 up, 250 down  ← not much separation
  Right (low volume):   250 up, 150 down  ← also not great

→ Algorithm picks RSI < 30 because it creates the cleanest split
→ Then repeats for each branch until it's "pure enough" or hits a depth limit
```

**Strengths:** Easy to understand, fast, works with mixed data types, no normalization needed.

**Weaknesses:**
- A single tree tends to **overfit** — it memorizes the training data instead of learning general patterns
- Small changes in data can produce completely different trees (**unstable**)
- This is why we don't use a single tree — we use **ensembles** (many trees together)

---

## From One Tree to Many: Ensemble Methods

The solution to a single tree's weakness is to use **many trees** and combine their votes. There are two main strategies:

### Strategy 1: Random Forest — "Ask Many Independent Experts"

Build 100+ trees, each trained on a **random subset** of data with **random features**. Each tree is different. Final prediction = **majority vote**.

```
Tree 1 (trained on 70% of data, saw features A,C,E): "BUY"
Tree 2 (trained on 70% of data, saw features B,D,F): "SKIP"
Tree 3 (trained on 70% of data, saw features A,D,G): "BUY"
...100 trees...

Final vote: 67 say BUY, 33 say SKIP → prediction = BUY (67% confidence)
```

**Good:** Simple, hard to overfit, parallelizable.
**Limitation:** Each tree is independent — they don't learn from each other's mistakes.

### Strategy 2: Gradient Boosting — "Each New Expert Fixes Previous Mistakes"

Build trees **sequentially**, where each new tree focuses on the examples the previous trees got **wrong**:

```
Tree 1: Makes predictions, gets 40% wrong
    ↓
Tree 2: Focuses on the 40% that Tree 1 got wrong, fixes half of them
    ↓
Tree 3: Focuses on the remaining errors, fixes more
    ↓
... 100-500 trees later ...
    ↓
Final: Combine all trees' predictions → 95% accurate
```

**Good:** Usually more accurate than Random Forest because it **learns from errors**.
**Risk:** Can overfit if you add too many trees or make them too deep — needs tuning.

---

## What Is XGBoost? And Why Does Jarvis Use It?

**XGBoost** (eXtreme Gradient Boosting) is the most popular gradient boosting library. It adds engineering optimizations that make gradient boosting **fast and practical**:

- **Regularization** — built-in penalty for complexity, prevents overfitting
- **Parallelism** — builds each tree level in parallel (despite sequential tree ordering)
- **Missing values** — handles NaN/missing data automatically (critical for real-world stock data)
- **Feature importance** — tells you which features matter most

### The Model Landscape — When to Use What

| Model | Type | Best For | Weakness | Used in Jarvis? |
|-------|------|----------|----------|----------------|
| **XGBoost** | Gradient boosting | Tabular/structured data (spreadsheets) | Needs tuning; not great for text/images | Yes — stock prediction |
| **LightGBM** | Gradient boosting | Very large datasets, faster than XGBoost | Similar accuracy, different tradeoffs | No, but interchangeable |
| **CatBoost** | Gradient boosting | Data with many text/category columns | Slower first train | No |
| **Random Forest** | Bagging (independent trees) | Quick baseline, hard to overfit | Usually slightly less accurate | No, but easy to swap in |
| **Neural Network** | Layers of neurons | Text, images, audio, video, sequences | Needs more data, harder to interpret | Yes — embeddings (MiniLM) |
| **Linear/Logistic Regression** | Single line/plane | Simple relationships, interpretability | Too simple for complex patterns | No |
| **SVM** | Boundary finding | Small datasets, high-dimensional | Slow on large data, hard to tune | No |
| **k-Nearest Neighbors** | Find similar examples | Similarity-based tasks, small datasets | Slow at prediction time, needs all data in memory | No |

**Why Jarvis chose XGBoost for stocks:** Stock prediction uses **tabular features** (RSI, MACD, volume ratios, moving averages — all numbers in columns). For tabular data, gradient boosting (XGBoost/LightGBM) **consistently beats neural networks** in benchmarks and Kaggle competitions. It's also fast to train, easy to interpret, and handles missing values well.

**Rule of thumb:**
- Data looks like a **spreadsheet** (rows = samples, columns = numbers)? → Try XGBoost first
- Data is **text**? → Use Transformers/embeddings (what Jarvis uses for RAG)
- Data is **images or audio**? → Use CNNs or Vision Transformers
- Data is a **sequence** (time series, sentences)? → Consider RNNs or Transformers

---

## What Is scikit-learn?

scikit-learn (`sklearn`) is the **standard Python library for machine learning**. Think of it as the "toolbox" — not one model, but the entire workshop.

Almost every ML project uses scikit-learn, even when the final model comes from another library (like XGBoost). That's because scikit-learn handles everything **around** the model:

```python
from sklearn.model_selection import train_test_split    # Split data
from sklearn.preprocessing import StandardScaler        # Normalize features
from sklearn.metrics import accuracy_score, f1_score    # Measure quality
from sklearn.ensemble import RandomForestClassifier     # One of 30+ models
from sklearn.pipeline import Pipeline                   # Chain steps together
```

### What scikit-learn Gives You

| Category | What It Does | Example |
|----------|-------------|---------|
| **Data splitting** | Divide data into training/test sets fairly | `train_test_split(X, y, test_size=0.2)` |
| **Preprocessing** | Normalize, encode categories, fill missing values | `StandardScaler`, `LabelEncoder`, `SimpleImputer` |
| **30+ Models** | Built-in algorithms ready to use | `RandomForest`, `SVM`, `KMeans`, `LogisticRegression` |
| **Evaluation** | Measure model quality from every angle | `accuracy_score`, `f1_score`, `confusion_matrix` |
| **Pipelines** | Chain preprocessing + model into one reusable object | `Pipeline([('scale', StandardScaler()), ('model', XGBClassifier())])` |
| **Hyperparameter tuning** | Find the best settings automatically | `GridSearchCV`, `RandomizedSearchCV` |
| **Cross-validation** | Test model reliability on multiple data splits | `cross_val_score(model, X, y, cv=5)` |

### Why "scikit"?

The name comes from "SciPy Toolkit" — it was originally a collection of ML utilities for the SciPy scientific computing library. Today it's a standalone project with millions of users.

**Is it free?** Yes. BSD license — completely free for any use, including commercial.

**In Jarvis:** Even though the stock model uses XGBoost (which has its own library), scikit-learn handles the **surrounding infrastructure** — splitting data, scaling features, evaluating results, cross-validation.

---

## How All These Pieces Fit Together

Here's the complete ML pipeline used in Jarvis stock prediction:

```
Raw stock data (prices, volume, dates)
    │
    ▼
Feature Engineering ──── Calculate 50+ indicators (RSI, MACD, MA, volume ratios)
    │                    Using pandas + pandas-ta
    │                    → See: feature-engineering-ta.md
    ▼
Preprocessing ────────── Normalize features, handle missing values
    │                    Using scikit-learn (StandardScaler)
    ▼
Train/Test Split ─────── 80% for training, 20% for testing
    │                    Using scikit-learn (train_test_split)
    ▼
Model Training ───────── XGBoost learns patterns from training data
    │                    Using xgboost (XGBClassifier)
    │                    → See: xgboost-gradient-boosting.md
    ▼
Evaluation ───────────── Accuracy, F1 score, feature importance
    │                    Using scikit-learn (metrics) + XGBoost built-ins
    │                    → See: ch2-model-training-evaluation.md
    ▼
Prediction ───────────── "Stock X has 73% probability of going up"
```

---

## Quick Experiment: Train Your First Model

```python
# pip install scikit-learn xgboost

from sklearn.datasets import load_iris          # Famous toy dataset
from sklearn.model_selection import train_test_split
from sklearn.metrics import accuracy_score
from xgboost import XGBClassifier

# Load data (150 flowers, 4 features each, 3 species)
X, y = load_iris(return_X_y=True)

# Split: 80% train, 20% test
X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2)

# Train XGBoost (100 small trees, each max 3 levels deep)
model = XGBClassifier(n_estimators=100, max_depth=3)
model.fit(X_train, y_train)

# Evaluate
predictions = model.predict(X_test)
print(f"Accuracy: {accuracy_score(y_test, predictions):.1%}")
# → Accuracy: 96.7%  (with just 5 lines of real code!)
```

**Try changing things:**
- `n_estimators=10` (fewer trees) → accuracy drops?
- `n_estimators=500` (more trees) → better or overfitting?
- `max_depth=1` (tiny trees) vs `max_depth=10` (deep trees)?
- Replace `XGBClassifier` with `RandomForestClassifier` from scikit-learn — compare accuracy

---

## Summary

| Concept | What It Is | Jarvis Example |
|---------|-----------|---------------|
| **Supervised ML** | Learn patterns from labeled data | Stock features → "up/down" prediction |
| **Decision tree** | Flowchart of yes/no questions | Building block of XGBoost |
| **Random Forest** | Many independent trees voting | Alternative to XGBoost (simpler) |
| **Gradient boosting** | Sequential trees fixing each other's errors | Core of XGBoost |
| **XGBoost** | Fast, optimized gradient boosting library | `scripts/stock/xgboost_model.py` |
| **scikit-learn** | Python ML toolbox (splitting, metrics, pipelines) | Used around XGBoost for infrastructure |

---

*Next: [Chapter 2 — Model Training & Evaluation](ch2-model-training-evaluation.md) — How to train properly, avoid overfitting, and measure if your model is actually good*
