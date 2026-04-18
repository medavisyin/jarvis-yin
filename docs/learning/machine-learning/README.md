# Machine Learning — From Classical ML to Neural Retrieval

> Learning track for the ML techniques used across Jarvis: gradient boosting,
> feature engineering, embeddings, learning-to-rank, and evaluation.

---

## Chapters

| # | Chapter | What You'll Learn |
|:-:|---------|-------------------|
| 1 | [ML Fundamentals](ch1-ml-fundamentals.md) | What is ML, decision trees, XGBoost vs alternatives, scikit-learn, train your first model |
| 2 | [Model Training & Evaluation](ch2-model-training-evaluation.md) | Train/test split, overfitting, cross-validation, metrics (accuracy, F1, confusion matrix) |
| 3 | [Data Preprocessing](ch3-data-preprocessing.md) | Missing values, scaling, categorical encoding, `Pipeline` / `ColumnTransformer`, avoiding leakage |
| 4 | [Feature Engineering & TA](feature-engineering-ta.md) | Technical indicators (RSI, MACD, MA), normalization, feature selection — *moved from know-how* |
| 5 | [XGBoost Deep Dive](xgboost-gradient-boosting.md) | Gradient boosting internals, hyperparameters, feature importance, tuning — *moved from know-how* |

## How Jarvis Uses ML

| Component | ML Technique | Script |
|-----------|-------------|--------|
| Stock prediction | XGBoost classifier on TA features | `scripts/stock/xgboost_model.py` |
| Stock scanning | Feature engineering + scoring | `scripts/stock/scanner.py` |
| Semantic search | Pre-trained embeddings (MiniLM) | `scripts/rag/search_ui.py` |
| Re-ranking | Cross-encoder neural reranker | `scripts/rag/reranker.py` |
| Feedback learning | Implicit signal → ranking weight | `scripts/rag/feedback_store.py` |
| BM25 hybrid search | Classical term-frequency retrieval | `scripts/rag/bm25_index.py` |

## Cross-References

| Topic | Where |
|-------|-------|
| Embeddings & Sentence Transformers | [Hugging Face track](../huggingface/) |
| Neural retrieval & learning-to-rank | [RAG Ch. 7 — ML for Retrieval](../rag/ch7-ml-for-retrieval.md) |
| RAG evolution roadmap | [RAG Ch. 5 — ML Roadmap](../rag/ch5-ml-roadmap.md) |
| Hybrid search & reranking | [RAG — Hybrid Search](../rag/hybrid-search-reranking.md) |

---

*Part of the [Jarvis Learning Series](../). See also: [RAG](../rag/), [LLM](../llm/), [Hugging Face](../huggingface/)*
