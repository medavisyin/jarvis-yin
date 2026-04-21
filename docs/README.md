---
tags:
  - hub
  - navigation
category: hub
status: current
last-updated: 2026-04-21
---

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
| **Learn stock investing** | [Stock Learning Track (中文)](learning/stock/) — 从零到合格投资者 |
| **Use Telegram remote** | [Telegram Bot Guide](guides/telegram-bot-guide.md) |
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
│   ├── stock-knowledge-guide.md # 股票知识入门 (Chinese)
│   └── telegram-bot-guide.md    # Telegram remote control guide
│
├── implementation/              # Developer implementation docs
│   ├── README.md                # Implementation navigation hub
│   ├── tech-stack-overview.md   # All technologies explained
│   ├── rag/                     # RAG system (agent, indexers, search, settings)
│   ├── briefing-pipeline/       # Daily briefing (fetchers, merge, audio, world news)
│   └── stock/                   # Stock module (10 docs: TA, ML, scanner, APIs)
│
├── learning/                    # Structured learning paths by topic
│   ├── rag/                    # RAG concepts & retrieval (Ch. 1–8)
│   ├── llm/                    # LLM, Ollama, prompt engineering
│   ├── machine-learning/       # XGBoost, embeddings, feature engineering
│   ├── huggingface/            # Sentence Transformers, HF Hub, fine-tuning
│   ├── stock/                  # A-share investing: basics → valuation → risk → Jarvis workflow (8 ch.)
│   ├── python-web/             # Flask, async/concurrency, testing
│   ├── data-acquisition/       # Playwright, PDF, TTS, pipeline patterns
│   └── devops-tools/           # Git, PowerShell, Atlassian integration
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
| [System Architecture](design/architecture.md) | Full system architecture with Mermaid diagrams (context, layers, data flow, deployment) |
| [RAG Agent Design](design/rag-agent-design.md) | Auto-RAG, SSE streaming, tool system, performance benchmarks |

## User Guides

| Document | Description |
|----------|-------------|
| [股票知识入门](guides/stock-knowledge-guide.md) | A股基础、K线、技术指标、基本面、情绪分析、机器学习预测 (中文) |
| [股票使用指南](guides/stock-usage-guide.md) | 关注列表、数据获取、分析报告、ML预测、决策参考 (中文) |
| [Telegram 远程控制](guides/telegram-bot-guide.md) | Telegram Bot 远程命令指南: 每日抓取、搜索、AI问答、股票分析 |

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
| [Learning Features](implementation/rag/learning-features-impl.md) | AI Learning, Tech English, Casual English, AWS AIF-C01, Notes |
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

**Beginner Guides** (organized by learning track under `learning/`):

| Track | Guides |
|-------|--------|
| [RAG](learning/rag/) | [RAG Architecture](learning/rag/rag-architecture.md), [Qdrant Vector DB](learning/rag/qdrant-vector-db.md), [Hybrid Search & Reranking](learning/rag/hybrid-search-reranking.md) |
| [LLM](learning/llm/) | [Ollama Local LLM](learning/llm/ollama-local-llm.md), [Prompt Engineering](learning/llm/llm-prompt-engineering.md) |
| [Machine Learning](learning/machine-learning/) | [ML Fundamentals](learning/machine-learning/ch1-ml-fundamentals.md), [Training & Evaluation](learning/machine-learning/ch2-model-training-evaluation.md), [XGBoost](learning/machine-learning/xgboost-gradient-boosting.md), [Feature Engineering](learning/machine-learning/feature-engineering-ta.md) |
| [Hugging Face](learning/huggingface/) | [Sentence Transformers](learning/huggingface/sentence-transformers.md) |
| [Python Web](learning/python-web/) | [Flask Web Server](learning/python-web/flask-web-server.md), [Async & Concurrency](learning/python-web/async-concurrency-python.md), [Testing](learning/python-web/testing-python-apps.md) |
| [Data Acquisition](learning/data-acquisition/) | [Playwright Scraping](learning/data-acquisition/playwright-scraping.md), [PDF Processing](learning/data-acquisition/pypdf-reportlab.md), [Edge TTS](learning/data-acquisition/edge-tts-speech.md) |
| [Stock Investing (中文)](learning/stock/) | [市场基础](learning/stock/ch1-stock-market-basics.md), [财务报表](learning/stock/ch2-financial-statements.md), [估值方法](learning/stock/ch3-valuation-methods.md), [技术分析](learning/stock/ch4-technical-analysis.md), [风险管理](learning/stock/ch5-risk-management.md), [策略体系](learning/stock/ch6-investment-strategies.md), [量化与ML](learning/stock/ch7-quantitative-methods.md), [Jarvis实战](learning/stock/ch8-jarvis-workflow.md), [增强路线图](learning/stock/ch9-enhancement-roadmap.md), [A股深度解析](learning/stock/ch10-astock-deep-dive.md) |

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
│  Telegram Bot: Remote command interface (polling)              │
│                                                              │
│  Embedding: all-MiniLM-L6-v2 (384-dim)                      │
│  Vector DB: Qdrant in-memory + JSON snapshot                 │
│  LLM: Ollama (qwen3.5:4b chat, qwen3:1.7b narration)       │
│  ML: XGBoost (stock prediction, walk-forward validation)     │
│  TTS: Edge TTS (segmented audio, Chinese/English)            │
└──────────────────────────────────────────────────────────────┘
```
