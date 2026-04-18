# RAG — Retrieval-Augmented Generation

> Learning track for the core knowledge-retrieval system powering Jarvis.
> Covers embeddings, vector search, chunking, hybrid retrieval, reranking,
> evaluation, and advanced RAG patterns.

---

## Reading Order

Follow the chapters in order. Each builds on the previous one.

| # | Chapter | What You'll Learn |
|:-:|---------|-------------------|
| 1 | [Core RAG Concepts](ch1-rag-concepts.md) | What RAG is, the 3-stage pipeline (index / retrieve / generate), embeddings, chunking, vector DB |
| 2 | [Vector Search Explained](ch3-vector-search-explained.md) | Keyword vs semantic search, embedding geometry, cosine similarity, Qdrant + HNSW, chunk sizing |
| 3 | [Hybrid Search & Reranking](hybrid-search-reranking.md) | BM25, dense search, hybrid fusion (RRF), cross-encoder reranking, precision vs recall |
| 4 | [Qdrant Vector Database](qdrant-vector-db.md) | What a vector DB does, Qdrant in-memory, payload filtering, snapshot persistence |
| 5 | [RAG Architecture (Quick Ref)](rag-architecture.md) | Jarvis's indexers, auto-RAG, tool-based RAG, context window, quality patterns |
| 6 | [Architecture Assessment](ch2-architecture-assessment.md) | RAG maturity levels 1-5, where Jarvis sits, strengths, gaps, upgrade path |
| 7 | [Advanced Techniques](ch6-advanced-rag-techniques.md) | Semantic chunking, query rewriting, HyDE, parent-child chunks, retrieval metrics |
| 8 | [Framework Comparison](ch4-framework-comparison.md) | LangChain vs LlamaIndex vs Haystack vs custom, trade-off matrix |
| 9 | [ML for Retrieval](ch7-ml-for-retrieval.md) | Contrastive learning, fine-tuning embeddings, learning-to-rank, RLHF for retrieval |
| 10 | [ML Roadmap](ch5-ml-roadmap.md) | Phased evolution plan: feedback loops, fine-tuning, CRAG, agentic RAG |
| 11 | [RAG Evaluation](ch9-rag-evaluation.md) | Recall@K, MRR, NDCG, faithfulness, RAGAS, building test sets, online eval |
| 12 | [Learning Roadmap](ch8-learning-roadmap.md) | 12-week study plan, key papers, external resources, enterprise vs personal RAG |

## Beginner Path (Start Here)

If you're brand new to RAG, read just these four first:

1. **Ch 1** — understand the pipeline
2. **Ch 2** — understand vector search
3. **Ch 3** — understand hybrid search + reranking
4. **Ch 11** — understand how to measure quality

Then explore the rest based on interest.

## How Jarvis Uses RAG

| Component | What It Does | Key Script |
|-----------|-------------|------------|
| Daily briefing indexer | Chunks + embeds markdown briefings | `scripts/rag/index_briefings.py` |
| Knowledge indexer | Chunks + embeds PDFs and notes | `scripts/rag/index_custom.py` |
| Search UI | Hybrid search + reranking + LLM answers | `scripts/rag/search_ui.py` |
| Agent auto-RAG | Context injection for conversational AI | `scripts/rag/agent.py` |
| Feedback store | Implicit learning from user interactions | `scripts/rag/feedback_store.py` |

## Cross-References

| Topic | Where |
|-------|-------|
| Embedding models & Sentence Transformers | [Hugging Face track](../huggingface/) |
| LLM generation, temperature, prompting | [LLM track](../llm/) |
| Classical ML & evaluation metrics | [Machine Learning track](../machine-learning/) |

---

*Part of the [Jarvis Learning Series](../). See also: [LLM](../llm/), [Machine Learning](../machine-learning/), [Hugging Face](../huggingface/)*
