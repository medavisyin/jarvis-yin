# Jarvis Learning Series

> Structured learning paths covering every major technology area in the Jarvis project.
> Each folder contains numbered chapters, reference guides, and links to implementation docs.

---

## Learning Tracks

| Folder | Focus | Chapters |
|--------|-------|----------|
| [**rag/**](rag/) | Retrieval-Augmented Generation — the core search & knowledge system | 12 chapters: concepts → vector search → hybrid/reranking → evaluation → advanced techniques |
| [**machine-learning/**](machine-learning/) | Classical & neural ML — XGBoost, feature engineering, evaluation | 5 chapters: fundamentals → training/eval → preprocessing → feature engineering → XGBoost deep dive |
| [**huggingface/**](huggingface/) | Hugging Face ecosystem — Transformers, Sentence Transformers, Hub | 4 chapters: getting started → tokenization → model selection → sentence transformers |
| [**llm/**](llm/) | Large Language Models — temperature, top_p, Ollama, local inference | Beginner guide + reference |
| [**python-web/**](python-web/) | Flask, async/concurrency, testing, REST API patterns | Reference guides |
| [**data-acquisition/**](data-acquisition/) | Playwright scraping, RSS feeds, PDF processing, TTS | Reference guides |
| [**devops-tools/**](devops-tools/) | Git, PowerShell, Atlassian integration, development workflow | Reference guides |

## Recommended Reading Order

If you want to learn everything from scratch, follow this path:

### Phase 1 — Foundations (weeks 1-2)
1. [ML Ch. 1 — Fundamentals](machine-learning/ch1-ml-fundamentals.md) — what ML is, decision trees, XGBoost
2. [ML Ch. 2 — Training & Evaluation](machine-learning/ch2-model-training-evaluation.md) — split, train, metrics
3. [HF Ch. 1 — Getting Started](huggingface/ch1-getting-started.md) — pre-trained models, first pipeline

### Phase 2 — Core RAG (weeks 3-4)
4. [RAG Ch. 1 — Core Concepts](rag/ch1-rag-concepts.md) — what RAG is, the 3-stage pipeline
5. [HF Ch. 2 — Tokenization](huggingface/ch2-tokenization.md) — how models see text
6. [RAG Ch. 2 — Vector Search](rag/ch3-vector-search-explained.md) — embeddings, cosine similarity
7. [HF Ch. 4 — Sentence Transformers](huggingface/sentence-transformers.md) — the embedding model Jarvis uses

### Phase 3 — Retrieval Deep Dive (weeks 5-6)
8. [RAG Ch. 3 — Hybrid Search & Reranking](rag/hybrid-search-reranking.md) — BM25, RRF, cross-encoder
9. [HF Ch. 3 — Model Selection](huggingface/ch3-model-selection.md) — MTEB, choosing the right model
10. [RAG Ch. 11 — Evaluation](rag/ch9-rag-evaluation.md) — Recall@K, MRR, RAGAS

### Phase 4 — Advanced (weeks 7+)
11. [ML Ch. 3 — Preprocessing](machine-learning/ch3-data-preprocessing.md) — scaling, encoding, Pipeline
12. [RAG Ch. 7 — Advanced Techniques](rag/ch6-advanced-rag-techniques.md) — semantic chunking, HyDE, rewriting
13. [LLM — Temperature & Inference](llm/) — how LLMs generate text
14. Continue with remaining chapters in each track

## Guides Per Track

Each track also contains reference guides (formerly in `implementation/know-how/`):

| Guide | Track |
|-------|-------|
| `rag-architecture.md`, `qdrant-vector-db.md`, `hybrid-search-reranking.md` | [RAG](rag/) |
| `sentence-transformers.md` | [Hugging Face](huggingface/) |
| `ollama-local-llm.md`, `llm-prompt-engineering.md` | [LLM](llm/) |
| `xgboost-gradient-boosting.md`, `feature-engineering-ta.md` | [Machine Learning](machine-learning/) |
| `flask-web-server.md`, `async-concurrency-python.md`, `testing-python-apps.md` | [Python Web](python-web/) |
| `playwright-scraping.md`, `pypdf-reportlab.md`, `edge-tts-speech.md` | [Data Acquisition](data-acquisition/) |
