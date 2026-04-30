---
tags:
  - hub
  - learning
  - navigation
category: hub
status: current
last-updated: 2026-04-21
---

# Jarvis Learning Series

> Structured learning paths covering every major technology area in the Jarvis project.
> Each folder contains numbered chapters, reference guides, and links to implementation docs.

> **Disambiguation**: This folder (`docs/learning/`) contains **tutorial & curriculum** content — concept explanations, beginner guides, reading orders. For documentation of the Jarvis "learning mode" **feature implementation** (English practice, AWS cert, deep-dive sessions), see [`docs/implementation/learning/`](../implementation/learning/).

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
| [**stock/**](stock/) | A 股投资从零到合格投资者 — 市场规则、财报、估值、TA、风控、策略、量化、Jarvis 实战、路线图、A股深度解析 | 10 chapters: basics → financials → valuation → TA → risk → strategies → quant/ML → workflow → roadmap → A-share deep dive |

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

### Stock Investing Track (独立学习路径)

Can be read independently of the tech tracks above:

15. [Stock Ch. 1 — 市场基础](stock/ch1-stock-market-basics.md) — A股规则、代码、指数、涨跌停
16. [Stock Ch. 2 — 读懂财报](stock/ch2-financial-statements.md) — 三张表、关键比率
17. [Stock Ch. 3 — 估值方法](stock/ch3-valuation-methods.md) — PE/PB/DCF/安全边际
18. [Stock Ch. 4 — 技术分析](stock/ch4-technical-analysis.md) — K线、均线、MACD、量价
19. [Stock Ch. 5 — 风险管理](stock/ch5-risk-management.md) — 仓位、止损、投资心理
20. [Stock Ch. 6 — 策略体系](stock/ch6-investment-strategies.md) — 价值/成长/动量/指数
21. [Stock Ch. 7 — 量化与ML](stock/ch7-quantitative-methods.md) — 模型能做什么、不能做什么
22. [Stock Ch. 8 — Jarvis实战](stock/ch8-jarvis-workflow.md) — 构建你的分析工作流
23. [Stock Ch. 9 — 增强路线图](stock/ch9-enhancement-roadmap.md) — 6阶段工程计划：估值重建、Regime检测、集成模型、风控组合、回测框架
24. [Stock Ch. 10 — A股深度解析](stock/ch10-astock-deep-dive.md) — 政策市、估值扭曲、全球联动板块、A股陷阱识别

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
