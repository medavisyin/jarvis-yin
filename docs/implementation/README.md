---
tags:
  - hub
  - implementation
  - navigation
category: hub
status: current
last-updated: 2026-04-30
---

# Jarvis Implementation Documentation

This folder holds detailed implementation guides for the Jarvis project. Each document explains how a script, subsystem, or technology works in context so you can navigate the codebase, extend indexers, or debug the briefing and RAG pipelines.

Documentation is organized in two complementary views: **by category** (function-oriented, 25 docs) and **by subsystem** (code-oriented, original docs).

```
docs/implementation/
├── README.md                        # This file
├── tech-stack-overview.md           # All technologies explained
│
├── medavis/                         # MEDAVIS — Work / Enterprise functions
│   ├── confluence-impl.md           # Confluence search & indexing
│   ├── jira-report-impl.md          # JIRA daily report
│   ├── project-graph-impl.md        # Maven dependency graph
│   ├── codebase-indexing-impl.md    # Codebase indexing into RAG
│   └── commit-summary-impl.md      # Multi-repo commit summary
│
├── usage-tool/                      # USAGE TOOL — Core platform tools
│   ├── rag-agent-impl.md            # RAG agent (core chat engine)
│   ├── search-ui-impl.md            # Search UI (library interface)
│   ├── reindex-all-impl.md          # Reindex orchestration
│   ├── custom-indexing-impl.md      # Custom file indexing
│   └── telegram-bot-impl.md        # Telegram bot
│
├── data-analysis/                   # DATA ANALYSIS — Analytics & prediction
│   ├── stock-prediction-impl.md     # Stock prediction engine (ML pipeline)
│   ├── technical-fundamental-impl.md # Technical & fundamental analysis
│   ├── market-scanner-impl.md       # Market scanner (short + long term)
│   ├── market-sentiment-risk-impl.md # Sentiment, risk & China A-share
│   └── donor-analysis-impl.md      # Donor analysis
│
├── personal/                        # PERSONAL — Daily briefing & content
│   ├── daily-fetch-impl.md          # Daily fetch pipeline
│   ├── ai-news-kb-impl.md           # AI news knowledge base
│   ├── audio-knowledge-impl.md      # Audio knowledge (podcast from RAG)
│   ├── trend-analysis-impl.md       # Trend analysis
│   └── global-settings-impl.md     # Global settings
│
├── learning/                        # LEARNING — Education & skill building
│   ├── ai-learning-impl.md          # AI learning mode
│   ├── tech-english-impl.md         # Tech English learning
│   ├── casual-english-impl.md       # Casual English learning
│   ├── aws-cert-impl.md             # AWS AIF-C01 cert prep
│   └── deep-dive-notes-impl.md     # Deep dive sessions & notes
│
├── rag/                             # (Subsystem view) RAG indexers & agent
│   ├── index-briefing-impl.md       # index_briefing.py
│   ├── index-codebase-impl.md       # index_codebase.py
│   ├── index-confluence-impl.md     # index_confluence.py + index_confluence_user.py
│   ├── index-custom-impl.md         # index_custom.py
│   ├── reindex-all-impl.md          # reindex_all.py orchestration
│   ├── search-ui-impl.md            # search_ui.py
│   ├── agent-impl.md                # agent.py
│   ├── learning-features-impl.md    # Learning modes (AI, English, AWS Cert, Notes)
│   └── global-settings-impl.md     # Global settings UI + audio language
├── briefing-pipeline/               # (Subsystem view) Briefing pipeline
│   ├── fetcher-pattern-impl.md      # How all fetch-*.py scripts work
│   ├── pipeline-orchestration-impl.md # run-all-sources, merge, preflight, world news
│   ├── output-generation-impl.md    # briefing-template, audio, video
│   ├── topic-dedup-impl.md          # topic_index, filter_topics, raw_saver
│   └── world-news-impl.md          # World news pipeline, China fetcher, translation
└── stock/                           # (Subsystem view) Stock prediction
    ├── README.md                    # Stock module index (20 modules)
    ├── stock-prediction-impl.md     # Architecture overview + anti-overfitting
    ├── config-impl.md              # Config, paths, Ollama models
    ├── data-layer-impl.md          # Data acquisition + watchlist + hot sectors
    ├── analysis-engines-impl.md    # TA + fundamental + sentiment engines
    ├── ml-pipeline-impl.md         # XGBoost classifier/regressor + tracker
    ├── market-signals-impl.md      # Fear & Greed, VIX, black swan
    ├── scanner-impl.md             # 3-layer market scanner (+ optional DeepSeek on TOP 5)
    ├── llm-synthesis-impl.md       # Ollama / optional DeepSeek narrative synthesis (stock)
    ├── api-routes-impl.md          # Stock API routes
    └── china-market-impl.md       # A股数据层、国家队ETF、择时模型、回测引擎
```

> **Beginner guides** (formerly `know-how/`) have moved to [docs/learning/](../learning/) organized by topic.
> See [learning/README.md](../learning/README.md) for the full index.

---

## Function-Oriented Documentation (by Category)

### MEDAVIS — Work / Enterprise (5 functions)

| # | Document | Description |
|---|----------|-------------|
| 1 | [confluence-impl.md](./medavis/confluence-impl.md) | Confluence search & indexing — team/user wiki indexing, CQL queries, version diff summaries, vector search with space filters. |
| 2 | [jira-report-impl.md](./medavis/jira-report-impl.md) | JIRA daily report — PowerShell Atlassian report, auto-routing keyword detection, toolbar + daily fetch integration. |
| 3 | [project-graph-impl.md](./medavis/project-graph-impl.md) | Project dependency graph — Maven pom.xml scanning, internal/external edge classification, impact/relationship queries. |
| 4 | [codebase-indexing-impl.md](./medavis/codebase-indexing-impl.md) | Codebase indexing — Java/Markdown/config chunking, MD5 content-hash dedup, project summary generation. |
| 5 | [commit-summary-impl.md](./medavis/commit-summary-impl.md) | Multi-repo commit summary — REPO_CONFIG + auto-discovery, author aliasing, Bitbucket links, team activity. |

### USAGE TOOL — Core Platform Tools (5 functions)

| # | Document | Description |
|---|----------|-------------|
| 6 | [rag-agent-impl.md](./usage-tool/rag-agent-impl.md) | RAG agent — **stub** → see [rag/agent-impl.md](./rag/agent-impl.md) for full guide |
| 7 | [search-ui-impl.md](./usage-tool/search-ui-impl.md) | Search UI — **stub** → see [rag/search-ui-impl.md](./rag/search-ui-impl.md) for full guide |
| 8 | [reindex-all-impl.md](./usage-tool/reindex-all-impl.md) | Reindex orchestration — **stub** → see [rag/reindex-all-impl.md](./rag/reindex-all-impl.md) for full guide |
| 9 | [custom-indexing-impl.md](./usage-tool/custom-indexing-impl.md) | Custom file indexing — CLI to add/scan/list/remove PDF/Markdown files with YAML front matter support. |
| 10 | [telegram-bot-impl.md](./usage-tool/telegram-bot-impl.md) | Telegram bot — owner-only proxy to RAG search, stock APIs, daily pipeline commands. |

### DATA ANALYSIS — Analytics & Prediction (5 functions)

| # | Document | Description |
|---|----------|-------------|
| 11 | [stock-prediction-impl.md](./data-analysis/stock-prediction-impl.md) | Stock prediction engine — XGBoost direction + price prediction, timing models, walk-forward validation, backtesting. |
| 12 | [technical-fundamental-impl.md](./data-analysis/technical-fundamental-impl.md) | Technical & fundamental analysis — indicators, patterns, scoring, news sentiment, LLM narrative synthesis. |
| 13 | [market-scanner-impl.md](./data-analysis/market-scanner-impl.md) | Market scanner — 3-layer short-term AI scanner + long-horizon theme scanner with RAG indexing. |
| 14 | [market-sentiment-risk-impl.md](./data-analysis/market-sentiment-risk-impl.md) | Market sentiment & risk — Fear/Greed, VIX, black swan detection, China A-share flows, national team monitoring. |
| 15 | [donor-analysis-impl.md](./data-analysis/donor-analysis-impl.md) | Donor analysis — clinical scoring algorithm, LLM reasoning narrative, PDF report generation. |

### PERSONAL — Daily Briefing & Content (5 functions)

| # | Document | Description |
|---|----------|-------------|
| 16 | [daily-fetch-impl.md](./personal/daily-fetch-impl.md) | Daily fetch pipeline — full orchestration: news fetch, topic dedup, commit/jira/wiki reports, audio generation. |
| 17 | [ai-news-kb-impl.md](./personal/ai-news-kb-impl.md) | AI news knowledge base — scan/categorize/summarize briefing items with LLM-driven learning paths. |
| 18 | [audio-knowledge-impl.md](./personal/audio-knowledge-impl.md) | Audio knowledge — podcast MP3 generation from RAG chunks using Edge TTS, multi-language support. |
| 19 | [trend-analysis-impl.md](./personal/trend-analysis-impl.md) | Trend analysis — multi-category RAG-based predictions (ai_news, world_news, wiki, jira, commits). |
| 20 | [global-settings-impl.md](./personal/global-settings-impl.md) | Global settings — audio language, DeepSeek API key, Ollama model switching, settings persistence. |

### LEARNING — Education & Skill Building (5 functions)

| # | Document | Description |
|---|----------|-------------|
| 21 | [ai-learning-impl.md](./learning/ai-learning-impl.md) | AI learning mode — roadmap-driven AI/LLM/RAG tutor with DuckDuckGo references and RAG-enhanced teaching. |
| 22 | [tech-english-impl.md](./learning/tech-english-impl.md) | Tech English — structured English analysis from AI/tech news (vocabulary, patterns, grammar, discussion). |
| 23 | [casual-english-impl.md](./learning/casual-english-impl.md) | Casual English — everyday English from world news with idioms, cultural context, and dialogues. |
| 24 | [aws-cert-impl.md](./learning/aws-cert-impl.md) | AWS AIF-C01 cert prep — domain-mapped teach/quiz/progress with study notes and progress tracking. |
| 25 | [deep-dive-notes-impl.md](./learning/deep-dive-notes-impl.md) | Deep dive & notes — per-article study sessions from URLs/files + My Notes CRUD with tags. |

---

## Subsystem-Oriented Documentation (by Code Area)

### RAG Indexers

| Document | Description |
|----------|-------------|
| [index-briefing-impl.md](./rag/index-briefing-impl.md) | Implementation of `index_briefing.py` for briefing content indexing. |
| [index-codebase-impl.md](./rag/index-codebase-impl.md) | Implementation of `index_codebase.py` for repository and code indexing. |
| [index-confluence-impl.md](./rag/index-confluence-impl.md) | Implementation of `index_confluence.py` and `index_confluence_user.py` for Confluence indexing. |
| [index-custom-impl.md](./rag/index-custom-impl.md) | Implementation of `index_custom.py` for custom source indexing. |
| [reindex-all-impl.md](./rag/reindex-all-impl.md) | How `reindex_all.py` orchestrates full or partial reindexing. |
| [search-ui-impl.md](./rag/search-ui-impl.md) | Implementation of `search_ui.py` (embedding, Qdrant search, Flask UI). |
| [agent-impl.md](./rag/agent-impl.md) | Implementation of `agent.py` — thin Flask orchestrator (~1,405 lines) with routes extracted to Blueprints (`routes/`), query pipeline (`pipeline.py`), conversation memory (`memory/`), intent classification, tool dispatch. |
| [learning-features-impl.md](./rag/learning-features-impl.md) | Learning modes: AI Learning, Tech English, Casual English, AWS AIF-C01 Cert, Notes system. |
| [global-settings-impl.md](./rag/global-settings-impl.md) | Global settings popup: audio language selection for AI Briefing, World News, Chinese News, Knowledge audio. |

### Briefing Pipeline

| Document | Description |
|----------|-------------|
| [fetcher-pattern-impl.md](./briefing-pipeline/fetcher-pattern-impl.md) | Shared pattern used by all `fetch-*.py` scraping scripts. |
| [pipeline-orchestration-impl.md](./briefing-pipeline/pipeline-orchestration-impl.md) | `run-all-sources`, merge steps, preflight checks, and world news phase. |
| [world-news-impl.md](./briefing-pipeline/world-news-impl.md) | World news pipeline: 6 fetchers (incl. China), merge, Ollama translation. |
| [output-generation-impl.md](./briefing-pipeline/output-generation-impl.md) | `briefing-template`, audio, and video output generation. |
| [topic-dedup-impl.md](./briefing-pipeline/topic-dedup-impl.md) | `topic_index`, `filter_topics`, and `raw_saver` for topic handling and deduplication. |

### Stock Prediction

The stock module keeps **data and model computation on the machine**; the **optional DeepSeek API (deepseek-v4-pro with thinking) for stock analysis via Global Settings** is used only for **final** narrative synthesis and optional **AI 股票推荐** TOP 5 follow-up, not for RAG or the briefing pipeline.

| Document | Description |
|----------|-------------|
| [stock/README.md](./stock/README.md) | Stock module navigation index (links to all 11 stock implementation docs). |
| [stock-prediction-impl.md](./stock/stock-prediction-impl.md) | End-to-end architecture overview, module graph, anti-overfitting, market risk signals. |
| [config-impl.md](./stock/config-impl.md) | Configuration, paths, Ollama models, environment variables. |
| [data-layer-impl.md](./stock/data-layer-impl.md) | `fetch_market_data`, `watchlist`, `hot_sectors` — data acquisition and caching. |
| [analysis-engines-impl.md](./stock/analysis-engines-impl.md) | Technical, fundamental, sentiment analysis engines. |
| [ml-pipeline-impl.md](./stock/ml-pipeline-impl.md) | Feature engineering, XGBoost classifier/regressor, prediction tracker. |
| [market-signals-impl.md](./stock/market-signals-impl.md) | Fear & Greed, VIX, world news black swan detection. |
| [scanner-impl.md](./stock/scanner-impl.md) | 3-layer full-market AI recommendation scanner. |
| [llm-synthesis-impl.md](./stock/llm-synthesis-impl.md) | Ollama- or **optional DeepSeek API (deepseek-v4-pro with thinking) for stock analysis via Global Settings** — final synthesis for stock only; RAG and briefing stay local. |
| [api-routes-impl.md](./stock/api-routes-impl.md) | All stock Flask API endpoints, thread safety, error handling. |
| [**china-market-impl.md**](./stock/china-market-impl.md) | A股数据层 (国家队ETF+北向+资金流)、择时模型、回测引擎 |

### Stack overview

| Document | Description |
|----------|-------------|
| [tech-stack-overview.md](./tech-stack-overview.md) | End-to-end technology stack, data flow, and how each component fits together. |

---

## Reading order

1. **[tech-stack-overview.md](./tech-stack-overview.md)** — Start here for architecture, data flow, and which scripts touch which systems.
2. **Category docs** — Pick the category matching your interest (MEDAVIS, USAGE TOOL, DATA ANALYSIS, PERSONAL, LEARNING) and read the relevant function docs.
3. **Briefing pipeline** — Follow [fetcher-pattern-impl.md](./briefing-pipeline/fetcher-pattern-impl.md), then [pipeline-orchestration-impl.md](./briefing-pipeline/pipeline-orchestration-impl.md), then [topic-dedup-impl.md](./briefing-pipeline/topic-dedup-impl.md) and [output-generation-impl.md](./briefing-pipeline/output-generation-impl.md) if you work on sources, merge, or PDF/audio/video output.
4. **RAG** — Read [reindex-all-impl.md](./rag/reindex-all-impl.md) for orchestration, then the specific indexer doc (`index-*-impl.md`) you are changing; finish with [search-ui-impl.md](./rag/search-ui-impl.md) and [agent-impl.md](./rag/agent-impl.md) for query paths.

## Prerequisites

New to embeddings, vector search, Flask, Playwright, local LLMs, or PDF tooling? The **[learning guides](../learning/)** are organized by topic (RAG, LLM, ML, Hugging Face, Python Web, Data Acquisition). They are written to support the implementation docs and reduce the need to read upstream documentation from scratch. After that, [tech-stack-overview.md](./tech-stack-overview.md) ties those concepts to Jarvis-specific paths, ports, and filenames.
