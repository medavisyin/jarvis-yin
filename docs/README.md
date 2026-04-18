# Jarvis Documentation

> Personal AI assistant: RAG chat, daily briefing pipeline, stock prediction, learning modes.

---

## Quick Navigation

| You want to... | Start here |
|-----------------|------------|
| **Set up Jarvis** | [Getting Started](getting-started.md) |
| **Operate / debug** | [Backend Overview](backend-overview.md) |
| **Understand the code** | [Implementation Index](implementation/README.md) |
| **Learn RAG concepts** | [Learning Chapters](learning/) (Ch. 1–8) |
| **Use stock features** | [Stock Usage Guide (中文)](guides/stock-usage-guide.md) |
| **See the roadmap** | [Enhancement Plan](plans/2026-04-17-jarvis-next.md) |

---

## Directory Structure

```
docs/
├── README.md                    ← You are here
├── getting-started.md           # Zero-to-running setup guide
├── backend-overview.md          # Complete system reference (architecture, APIs, config)
│
├── design/                      # Architecture & design documents
│   └── rag-agent-design.md      # Chat agent deep-dive (auto-RAG, SSE, tools)
│
├── guides/                      # User-facing guides
│   ├── stock-usage-guide.md     # 股票使用指南 (Chinese)
│   └── stock-knowledge-guide.md # 股票知识入门 (Chinese)
│
├── implementation/              # Developer implementation docs
│   ├── README.md                # Implementation navigation hub
│   ├── tech-stack-overview.md   # All technologies explained
│   ├── rag/                     # RAG system (agent, indexers, search, settings)
│   ├── briefing-pipeline/       # Daily briefing (fetchers, merge, audio, world news)
│   ├── stock/                   # Stock module (10 docs: TA, ML, scanner, APIs)
│   └── know-how/                # Beginner tech guides (14 topics)
│
├── learning/                    # RAG & ML learning chapters
│   └── rag/                    # All RAG/retrieval learning content
│       ├── ch1-rag-concepts.md
│       ├── ch2-architecture-assessment.md
│       ├── ch3-vector-search-explained.md
│       ├── ch4-framework-comparison.md
│       ├── ch5-ml-roadmap.md
│       ├── ch6-advanced-rag-techniques.md
│       ├── ch7-ml-for-retrieval.md
│       └── ch8-learning-roadmap.md
│
├── plans/                       # Implementation plans & roadmaps
│   ├── 2026-04-17-jarvis-next.md    # Enhancement roadmap (Tier 0–5)
│   ├── 2026-04-12-stock-prediction.md
│   ├── plan-advanced-rag.md
│   └── plan-ml-integration.md
│
└── memory/                      # Session memory / review notes
    └── memory-20260414-stock-review-and-docs.md
```

---

## Getting Started

| Document | Description |
|----------|-------------|
| [Getting Started](getting-started.md) | Install Python, Ollama, all packages, run the pipeline, start both servers |
| [Backend Overview](backend-overview.md) | Architecture, all scripts, all API endpoints, configuration, troubleshooting |

## Design & Architecture

| Document | Description |
|----------|-------------|
| [RAG Agent Design](design/rag-agent-design.md) | Auto-RAG, SSE streaming, tool system, performance benchmarks |

## User Guides

| Document | Description |
|----------|-------------|
| [股票知识入门](guides/stock-knowledge-guide.md) | A股基础、K线、技术指标、基本面、情绪分析、机器学习预测 (中文) |
| [股票使用指南](guides/stock-usage-guide.md) | 关注列表、数据获取、分析报告、ML预测、决策参考 (中文) |

## Implementation Docs

Detailed developer documentation. See [Implementation Index](implementation/README.md) for full navigation.

**RAG System:**

| Document | Script(s) |
|----------|-----------|
| [Chat Agent](implementation/rag/agent-impl.md) | `agent.py` — auto-RAG, SSE, tools, Daily Fetch, audio, wiki fetch |
| [Briefing Indexer](implementation/rag/index-briefing-impl.md) | `index_briefing.py` |
| [Confluence Indexers](implementation/rag/index-confluence-impl.md) | `index_confluence.py`, `index_confluence_user.py` |
| [Codebase Indexer](implementation/rag/index-codebase-impl.md) | `index_codebase.py` |
| [Custom Indexer](implementation/rag/index-custom-impl.md) | `index_custom.py` |
| [Search UI](implementation/rag/search-ui-impl.md) | `search_ui.py` |
| [Learning Features](implementation/rag/learning-features-impl.md) | AI Learning, Tech English, Casual English, Notes |
| [Global Settings](implementation/rag/global-settings-impl.md) | Audio language per pipeline type |

**Briefing Pipeline:**

| Document | Script(s) |
|----------|-----------|
| [Pipeline Orchestration](implementation/briefing-pipeline/pipeline-orchestration-impl.md) | `run-all-sources.py`, `merge-sources.py`, `preflight-check.py` |
| [Fetcher Pattern](implementation/briefing-pipeline/fetcher-pattern-impl.md) | All `fetch-*.py` scripts |
| [World News Pipeline](implementation/briefing-pipeline/world-news-impl.md) | `run-world-news.py`, `fetch-china-news.py` |
| [Output Generation](implementation/briefing-pipeline/output-generation-impl.md) | PDF, audio podcast, video |
| [Topic Deduplication](implementation/briefing-pipeline/topic-dedup-impl.md) | `topic_index.py`, `filter_topics.py` |

**Stock Module:**

| Document | Topic |
|----------|-------|
| [Stock Index](implementation/stock/README.md) | Navigation hub (10 docs) |
| [Architecture](implementation/stock/stock-prediction-impl.md) | Overview, anti-overfitting, module map |
| [ML Pipeline](implementation/stock/ml-pipeline-impl.md) | XGBoost, walk-forward, prediction tracking |
| [Scanner](implementation/stock/scanner-impl.md) | 3-layer market scanner with LLM ranking |
| [API Routes](implementation/stock/api-routes-impl.md) | All stock API endpoints |

**Know-How (Beginner Guides):**

| Document | Technology |
|----------|------------|
| [RAG Architecture](implementation/know-how/rag-architecture.md) | Retrieval-Augmented Generation |
| [LLM Prompt Engineering](implementation/know-how/llm-prompt-engineering.md) | System/user prompts, structured output |
| [Hybrid Search & Reranking](implementation/know-how/hybrid-search-reranking.md) | BM25, vector search, RRF, cross-encoder |
| [XGBoost & Gradient Boosting](implementation/know-how/xgboost-gradient-boosting.md) | Supervised ML for stock prediction |
| [Edge TTS & Speech](implementation/know-how/edge-tts-speech.md) | Neural TTS for audio podcasts |
| [Async & Concurrency](implementation/know-how/async-concurrency-python.md) | Threading, asyncio, SSE |
| [Testing Python Apps](implementation/know-how/testing-python-apps.md) | pytest, fixtures, mocking |
| [Feature Engineering & TA](implementation/know-how/feature-engineering-ta.md) | Technical indicators for ML |
| [Sentence Transformers](implementation/know-how/sentence-transformers.md) | Text embeddings, MiniLM |
| [Qdrant Vector DB](implementation/know-how/qdrant-vector-db.md) | Vector database, in-memory + snapshots |
| [Flask Web Server](implementation/know-how/flask-web-server.md) | Routes, JSON APIs, SSE |
| [Ollama Local LLM](implementation/know-how/ollama-local-llm.md) | Running LLMs locally |
| [Playwright Scraping](implementation/know-how/playwright-scraping.md) | Headless browser automation |
| [PDF Processing](implementation/know-how/pypdf-reportlab.md) | pypdf + ReportLab |

## Learning Chapters

Read in order to understand the concepts behind the system:

| # | Chapter | What You'll Learn |
|:-:|---------|-------------------|
| 1 | [RAG Concepts](learning/rag/ch1-rag-concepts.md) | What is RAG, the 3-stage pipeline, embeddings, chunking |
| 2 | [Architecture Assessment](learning/rag/ch2-architecture-assessment.md) | 5-level RAG taxonomy, where Jarvis sits |
| 3 | [Vector Search Explained](learning/rag/ch3-vector-search-explained.md) | Embeddings, cosine similarity, HNSW indexing |
| 4 | [Framework Comparison](learning/rag/ch4-framework-comparison.md) | Jarvis vs LangChain vs LlamaIndex vs Haystack |
| 5 | [ML Roadmap](learning/rag/ch5-ml-roadmap.md) | 6-phase evolution from basic to agentic RAG |
| 6 | [Advanced RAG](learning/rag/ch6-advanced-rag-techniques.md) | Hybrid search, reranking, semantic chunking, HyDE |
| 7 | [ML for Retrieval](learning/rag/ch7-ml-for-retrieval.md) | Neural embeddings, fine-tuning, learning-to-rank |
| 8 | [Learning Roadmap](learning/rag/ch8-learning-roadmap.md) | 3-track plan (RAG, LLM, HuggingFace) with resources |

## Plans & Roadmaps

| Document | Status |
|----------|--------|
| [Jarvis Enhancement Plan](plans/2026-04-17-jarvis-next.md) | Active — Tier 0–5 roadmap |
| [Stock Prediction Plan](plans/2026-04-12-stock-prediction.md) | Phase 0–4.5 Done |
| [Advanced RAG Plan](plans/plan-advanced-rag.md) | Completed |
| [ML Integration Plan](plans/plan-ml-integration.md) | Phase 1–2 Done |

## System at a Glance

```
┌──────────────────────────────────────────────────────────────┐
│                       JARVIS SYSTEM                          │
│                                                              │
│  Fetch Scripts ──→ Processing ──→ Indexers ──→ Servers       │
│  fetchers/ai/       (PDF, Audio,   (RAG Store)  (Search+Chat)│
│  fetchers/news/      Translation)                            │
│                                                              │
│  Daily Fetch Pipeline:                                       │
│    Source Fetch → Merge → Dedup → Audio → World News →       │
│    Commit Report → Jira Report → Wiki Fetch                  │
│                                                              │
│  Stock Module ──→ Analysis ──→ ML Prediction ──→ AI Synth    │
│  (akshare data)   (TA, Fund,    (XGBoost)       (Ollama)    │
│                    Sentiment)    Scanner → TOP 5 推荐         │
│                                                              │
│  Port 18888: Search UI (Library, Chunk Analysis)             │
│  Port 18889: Jarvis Agent (Chat, Tools, Audio, Stock)        │
│                                                              │
│  Embedding: all-MiniLM-L6-v2 (384-dim)                      │
│  Vector DB: Qdrant in-memory + JSON snapshot                 │
│  LLM: Ollama (qwen3.5:4b chat, qwen3:1.7b narration)       │
│  ML: XGBoost (stock prediction, walk-forward validation)     │
│  TTS: Edge TTS (segmented audio, Chinese/English)            │
└──────────────────────────────────────────────────────────────┘
```
