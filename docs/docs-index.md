# Jarvis Documentation Index

> Complete documentation for the Jarvis RAG system — operations, concepts, plans, and learning.

---

## Getting Started

| Document | Description | Audience |
|----------|-------------|----------|
| [Getting Started: Build Jarvis from Zero](getting-started.md) | End-to-end setup guide: install Python, Ollama, all packages, run the pipeline, start both servers | **Start here** if you are new to Jarvis or setting up for the first time |

## Operational Guides

| Document | Description | Audience |
|----------|-------------|----------|
| [Backend Overview](backend-overview.md) | Complete system guide: architecture, all scripts, all API endpoints, configuration, troubleshooting | **Start here** if you need to operate or debug the system |
| [RAG Agent Design](rag-agent-design.md) | Deep-dive into the chat agent: auto-RAG, SSE streaming, tool system, performance benchmarks | Developers extending the agent |

## Implementation Guides (NEW)

Detailed implementation documentation for every script, with technology explanations for beginners.

| Document | Description | Audience |
|----------|-------------|----------|
| [Implementation Index](implementation/README.md) | Navigation hub for all implementation docs | **Start here** for implementation details |
| [Tech Stack Overview](implementation/tech-stack-overview.md) | All technologies explained (SentenceTransformer, Qdrant, Flask, Ollama, Playwright, etc.) | Everyone |

**RAG Indexers:**

| Document | Script(s) | Description |
|----------|-----------|-------------|
| [Briefing Indexer](implementation/rag/index-briefing-impl.md) | `index_briefing.py` | How daily briefings are chunked, embedded, and stored |
| [Codebase Indexer](implementation/rag/index-codebase-impl.md) | `index_codebase.py` | Java extraction, doc/config processing, project indexing |
| [Confluence Indexers](implementation/rag/index-confluence-impl.md) | `index_confluence.py`, `index_confluence_user.py` | Team wiki and user-specific wiki indexing |
| [Custom Indexer](implementation/rag/index-custom-impl.md) | `index_custom.py` | Personal knowledge files (Markdown, PDF) with frontmatter |
| [Reindex Orchestrator](implementation/rag/reindex-all-impl.md) | `reindex_all.py` | Incremental reindexing with manifest tracking |
| [Search UI](implementation/rag/search-ui-impl.md) | `search_ui.py` | Flask search server, API endpoints, library view |
| [Chat Agent](implementation/rag/agent-impl.md) | `agent.py` | Full RAG pipeline, auto-RAG, SSE streaming, tool system, commit summary, audio generation, explain-this, donor analysis, daily fetch |
| [Learning Features](implementation/rag/learning-features-impl.md) | `agent.py` | AI Learning, Tech English, Casual English modes, Notes system |
| [Global Settings](implementation/rag/global-settings-impl.md) | `agent.py` | Settings popup (⚙) for audio language (AI Briefing, World News, Chinese News, Knowledge) |

**Briefing Pipeline:**

| Document | Script(s) | Description |
|----------|-----------|-------------|
| [Fetcher Pattern](implementation/briefing-pipeline/fetcher-pattern-impl.md) | All `fetch-*.py` | Universal scraping pattern, drill-down, timing |
| [Pipeline Orchestration](implementation/briefing-pipeline/pipeline-orchestration-impl.md) | `pipeline/run-all-sources.py`, `pipeline/merge-sources.py`, `pipeline/preflight-check.py` | Parallel execution, merging, preflight checks, world news phase |
| [World News Pipeline](implementation/briefing-pipeline/world-news-impl.md) | `pipeline/run-world-news.py`, `fetchers/news/fetch-china-news.py` | 6-source world news, Chinese news fetcher, Ollama translation, category merge |
| [Output Generation](implementation/briefing-pipeline/output-generation-impl.md) | `output/briefing-template.py`, `output/generate-audio.py`, `output/generate-video.py` | PDF, audio podcast, video generation |
| [Topic Deduplication](implementation/briefing-pipeline/topic-dedup-impl.md) | `pipeline/topic_index.py`, `pipeline/filter_topics.py`, `raw_saver.py` | Fuzzy matching, freshness classification, raw saving |

**Technology Know-How (Beginner Guides):**

| Document | Technology | Description |
|----------|------------|-------------|
| [Sentence Transformers](implementation/know-how/sentence-transformers.md) | sentence-transformers | Text embeddings, all-MiniLM-L6-v2, how semantic search works |
| [Qdrant Vector DB](implementation/know-how/qdrant-vector-db.md) | qdrant-client | Vector database, in-memory mode, JSON snapshot pattern |
| [Flask Web Server](implementation/know-how/flask-web-server.md) | Flask | Routes, JSON APIs, SSE streaming, single-file deployment |
| [Playwright Scraping](implementation/know-how/playwright-scraping.md) | Playwright | Headless browser automation for web scraping |
| [Ollama Local LLM](implementation/know-how/ollama-local-llm.md) | Ollama | Running LLMs locally, streaming API, model management |
| [PDF Processing](implementation/know-how/pypdf-reportlab.md) | pypdf, ReportLab | PDF reading (extraction) and writing (generation) |

---

## Stock Analysis & Prediction

| Document | Description | Audience |
|----------|-------------|----------|
| [股票知识入门 (Stock Knowledge Guide)](stock-knowledge-guide.md) | 从零开始学炒股：A股基础、K线、技术指标、基本面、情绪分析、机器学习预测、投资实战 (中文) | **Start here** if you are new to stock investing |
| [股票使用指南 (Stock Usage Guide)](stock-usage-guide.md) | Jarvis 股票系统实用操作手册：关注列表、数据获取、分析报告、ML预测、决策参考 (中文) | Users who want to use Jarvis for stock analysis |
| [Stock Implementation Index](implementation/stock/README.md) | Full implementation docs index (10 documents): architecture, config, data layer, analysis engines, ML pipeline, market signals, scanner, LLM synthesis, API routes | Developers extending the stock module |
| [Stock Architecture Overview](implementation/stock/stock-prediction-impl.md) | High-level architecture, module dependencies, anti-overfitting strategy, market risk signals, API summary | Developers (start here) |
| [Stock Prediction Plan](plans/2026-04-12-stock-prediction.md) | Full implementation plan with glossary, phased tasks, and architecture | Developers and planners |

## Implementation Plans

| Document | Description | Status |
|----------|-------------|:------:|
| [Advanced RAG Plan](plan-advanced-rag.md) | 4-task plan: chunk overlap → BM25 hybrid → cross-encoder re-ranking → query rewriting. Exact files, code patterns, acceptance criteria. | **Completed** |
| [ML Integration Plan](plan-ml-integration.md) | 5-task plan: feedback collection → weighted ranking → training data → embedding fine-tuning → corrective RAG. Tasks 1-2 completed. | Phase 1-2 Done |
| [Stock Prediction Plan](plans/2026-04-12-stock-prediction.md) | A-share stock prediction: data infra, technical analysis, fundamentals, sentiment, XGBoost ML, LLM reasoning, UI integration, market scanner (scanner LLM: `/api/chat` with `think:false` for reliable structured output). | Phase 0-4.5 Done |

## Learning Chapters

Read these in order to understand the concepts behind the system:

| # | Chapter | What You'll Learn |
|:-:|---------|-------------------|
| 1 | [RAG Concepts](ch1-rag-concepts.md) | What is RAG? The 3-stage pipeline (index → retrieve → generate). Embeddings, cosine similarity, chunking, vector databases. How Jarvis maps to each concept. |
| 2 | [Architecture Assessment](ch2-architecture-assessment.md) | The 5-level RAG taxonomy (Naive → Agentic). Honest evaluation: Jarvis at Level 2 (Advanced RAG) plus agentic shell. Strengths, gaps, and the upgrade path. |
| 3 | [Vector Search Explained](ch3-vector-search-explained.md) | How embeddings encode meaning. The math behind cosine similarity. HNSW indexing. Why MiniLM-L6-v2 was chosen. The chunking problem. |
| 4 | [Framework Comparison](ch4-framework-comparison.md) | Jarvis vs LangChain vs LlamaIndex vs Haystack. Feature matrices, code examples, trade-offs of custom vs framework. |
| 5 | [ML & Future Roadmap](ch5-ml-roadmap.md) | 6-phase evolution plan: from chunk overlap to fine-tuned embeddings to full agentic RAG. Can Jarvis learn? Yes — here's how. |
| 6 | [Advanced RAG Techniques](ch6-advanced-rag-techniques.md) | Deep dive: hybrid search (BM25+vector), cross-encoder re-ranking, semantic chunking, query rewriting, HyDE, parent-child chunks, evaluation metrics. |
| 7 | [ML for Information Retrieval](ch7-ml-for-retrieval.md) | How neural embeddings learn meaning. Fine-tuning explained. Learning-to-rank. RLHF for retrieval. Contrastive learning. Evaluation methods. |
| 8 | [Learning Roadmap](ch8-learning-roadmap.md) | 3-track learning plan (RAG, LLM, HuggingFace) with resources, 12-week hands-on plan, key papers, and enterprise vs personal technology comparison. |

## Quick Answers

| Question | Answer | Details In |
|----------|--------|:----------:|
| What type of RAG is Jarvis? | **Advanced RAG (Level 2) + proto-Agentic shell** (Level 2 retrieval with Level 4 agent features) | [Ch. 2](ch2-architecture-assessment.md) |
| Can Jarvis analyze stocks? | **Yes!** A-share stock prediction with technical analysis, fundamentals, sentiment, XGBoost ML, AI synthesis, and full-market AI scanner with buy-price recommendations (scanner LLM uses `/api/chat` with `think:false` for reliable structured output) | [Stock Guide](stock-knowledge-guide.md) |
| How does next-day price prediction work? | model_price_predictor.py trains 3 XGBoost regressors (close/high/low) per watchlist stock. | [Stock Impl](implementation/stock/stock-prediction-impl.md) |
| How does price prediction verification work? | Each training run backfills actual prices, computes MAPE/MAE/direction accuracy, and assigns a health grade A–D. | [Stock Impl](implementation/stock/stock-prediction-impl.md) |
| Does it have Chinese news? | **Yes!** `fetch-china-news.py` fetches Sina + People's Daily political/financial news. English news is auto-translated to Chinese via Ollama. | [World News](implementation/briefing-pipeline/world-news-impl.md) |
| Can I change audio language? | **Yes!** Click ⚙ gear icon next to model selector. AI Briefing, World News, Chinese News, Knowledge — each can be Chinese or English. | [Settings](implementation/rag/global-settings-impl.md) |
| Can it learn from my usage? | **Yes!** Feedback collection is active. Thumbs up/down and implicit signals improve ranking over time. See [ML Plan](plan-ml-integration.md) | [ML Plan](plan-ml-integration.md) |
| Can it use machine learning? | **Already does** (embeddings + XGBoost stock prediction). Fine-tuning and feedback loops are next | [Ch. 7](ch7-ml-for-retrieval.md) |
| Why two servers? | 18888 = fast search/library/analysis (no LLM). 18889 = AI chat (needs Ollama) | [Backend](backend-overview.md) |
| Where are Index New & Chunk Analysis? | In the **Search UI** (port 18888), under the Chunk Analysis tab | [Backend](backend-overview.md) |
| What's the biggest weakness? | No embedding fine-tuning yet (planned). Hybrid search and re-ranking are now implemented. | [Ch. 2](ch2-architecture-assessment.md) |
| What's the easiest improvement? | Collect more feedback data to improve ranking quality | [Adv. RAG Plan](plan-advanced-rag.md) |
| What's the highest-impact improvement? | Embedding fine-tuning (10-15% MRR improvement expected with 200-500 training pairs) | [Ch. 6](ch6-advanced-rag-techniques.md) |
| Should I rewrite it in LangChain? | **No** — selectively borrow ideas instead | [Ch. 4](ch4-framework-comparison.md) |
| How many training examples for fine-tuning? | 200-500 pairs for 10-15% improvement | [Ch. 7](ch7-ml-for-retrieval.md) |
| Can I learn AI/English through Jarvis? | **Yes!** Three modes: AI Learning (fundamentals-first + web refs), Tech English (article analysis from AI news), Casual English (article analysis from world news). English modes start fresh each time. | [Design](rag-agent-design.md), [Impl](implementation/rag/learning-features-impl.md) |
| Can I save good answers? | **Yes!** Click 📎 on any message to save to Notes. Review via "My Notes" in the Learning dropdown. | [Design](rag-agent-design.md) |
| How do I modify a learning feature? | Each feature has a dedicated section in the implementation guide with file locations, code snippets, and modification instructions. | [Learning Impl](implementation/rag/learning-features-impl.md) |

## System at a Glance

```
┌─────────────────────────────────────────────────────────────────┐
│                        JARVIS SYSTEM                            │
│                                                                 │
│  16 Fetch Scripts ──→ Processing ──→ 6 Indexers ──→ 2 Servers  │
│  fetchers/ai/ (10)    (PDF, Audio,   (RAG Store)   (Search+Chat)│
│  fetchers/news/ (6)    Translation)                              │
│                                                                 │
│  Stock Module ──→ Analysis ──→ ML Prediction ──→ AI Synthesis   │
│  scripts/stock/   (Technical,   (XGBoost)       (Ollama LLM)   │
│  (akshare data)    Fundamental,                                 │
│                    Sentiment)    AI Scanner (/api/chat, think:false) ──→ TOP 5 推荐 │
│                                                                 │
│  Port 18888: Search UI (Library, Chunk Analysis, Index New)     │
│  Port 18889: Jarvis Agent (Chat, Tools, Audio, Donor, Stock)   │
│    ⚙ Global Settings: audio language per type (AI/World/China) │
│    🎯 Stock: Analysis, Scanner, Price Prediction, Signals      │
│                                                                 │
│  Embedding: all-MiniLM-L6-v2 (384-dim)                         │
│  Vector DB: Qdrant in-memory + JSON snapshot                    │
│  LLM: Ollama (qwen3.5:4b, local CPU)                           │
│  ML: XGBoost (stock prediction, walk-forward validation)        │
│  Storage: C:/reports/ai/.rag-store.json (~18,815 chunks)        │
│           C:/reports/stock/ (stock data, models, reports)       │
│                                                                 │
│  Maturity: Advanced RAG + Agentic Shell + Stock Prediction      │
│  ML Status: XGBoost stock + AI market scanner (/api/chat, think:false) + RAG feedback │
│  Next Step: Training data generation → Embedding fine-tuning    │
└─────────────────────────────────────────────────────────────────┘
```

## Reading Order Recommendations

**"I'm setting up Jarvis for the first time"** (complete beginner):
→ [Getting Started](getting-started.md) → [Tech Stack Overview](implementation/tech-stack-overview.md) → Ch. 1

**"I'm new to this tech stack"** (beginner with Python experience):
→ [Tech Stack Overview](implementation/tech-stack-overview.md) → Know-How guides → Ch. 1

**"I want to understand the system"** (operator):
→ Backend Overview → RAG Agent Design → Implementation Guides

**"I want to learn how RAG works"** (learner):
→ Ch. 1 → Ch. 2 → Ch. 3 → Ch. 4

**"I want to understand the code"** (developer):
→ [Tech Stack](implementation/tech-stack-overview.md) → [Implementation Index](implementation/README.md) → pick the script you're interested in

**"I want to improve the system"** (developer):
→ Ch. 2 (assessment) → Ch. 6 (techniques) → Advanced RAG Plan → implement

**"I want to add ML"** (ML engineer):
→ Ch. 5 (roadmap) → Ch. 7 (ML concepts) → ML Integration Plan → implement

**"I want to learn about stocks and use Jarvis for investing"** (investor):
→ [Stock Knowledge Guide](stock-knowledge-guide.md) → [Stock Usage Guide](stock-usage-guide.md) → [Stock Prediction Plan](plans/2026-04-12-stock-prediction.md)

**"I want to extend the stock module"** (developer):
→ [Stock Implementation](implementation/stock/stock-prediction-impl.md) → [Stock Prediction Plan](plans/2026-04-12-stock-prediction.md) → source code in `scripts/stock/`

**"I want the full picture"** (all):
→ Read everything in order: Tech Stack → Know-How → Backend → Ch. 1-7 → Implementation → Plans
