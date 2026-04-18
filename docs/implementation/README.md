# Jarvis Implementation Documentation

This folder holds detailed implementation guides for the Jarvis project. Each document explains how a script, subsystem, or technology works in context so you can navigate the codebase, extend indexers, or debug the briefing and RAG pipelines.

```
docs/implementation/
├── README.md                        # This file
├── tech-stack-overview.md           # All technologies explained
├── rag/
│   ├── index-briefing-impl.md       # index_briefing.py
│   ├── index-codebase-impl.md       # index_codebase.py
│   ├── index-confluence-impl.md     # index_confluence.py + index_confluence_user.py
│   ├── index-custom-impl.md         # index_custom.py
│   ├── reindex-all-impl.md          # reindex_all.py orchestration
│   ├── search-ui-impl.md            # search_ui.py
│   ├── agent-impl.md                # agent.py
│   ├── learning-features-impl.md    # Learning modes (AI, English, Notes)
│   └── global-settings-impl.md     # Global settings UI + audio language
├── briefing-pipeline/
│   ├── fetcher-pattern-impl.md      # How all fetch-*.py scripts work
│   ├── pipeline-orchestration-impl.md # run-all-sources, merge, preflight, world news
│   ├── output-generation-impl.md    # briefing-template, audio, video
│   ├── topic-dedup-impl.md          # topic_index, filter_topics, raw_saver
│   └── world-news-impl.md          # World news pipeline, China fetcher, translation
└── stock/
    ├── README.md                    # Stock module index (17 modules)
    ├── stock-prediction-impl.md     # Architecture overview + anti-overfitting
    ├── config-impl.md              # Config, paths, Ollama models
    ├── data-layer-impl.md          # Data acquisition + watchlist + hot sectors
    ├── analysis-engines-impl.md    # TA + fundamental + sentiment engines
    ├── ml-pipeline-impl.md         # XGBoost classifier/regressor + tracker
    ├── market-signals-impl.md      # Fear & Greed, VIX, black swan
    ├── scanner-impl.md             # 3-layer market scanner
    ├── llm-synthesis-impl.md       # Ollama narrative synthesis
    └── api-routes-impl.md          # Stock API routes
```

> **Beginner guides** (formerly `know-how/`) have moved to [docs/learning/](../learning/) organized by topic.
> See [learning/README.md](../learning/README.md) for the full index.

## Table of contents

### RAG Indexers

| Document | Description |
|----------|-------------|
| [index-briefing-impl.md](./rag/index-briefing-impl.md) | Implementation of `index_briefing.py` for briefing content indexing. |
| [index-codebase-impl.md](./rag/index-codebase-impl.md) | Implementation of `index_codebase.py` for repository and code indexing. |
| [index-confluence-impl.md](./rag/index-confluence-impl.md) | Implementation of `index_confluence.py` and `index_confluence_user.py` for Confluence indexing. |
| [index-custom-impl.md](./rag/index-custom-impl.md) | Implementation of `index_custom.py` for custom source indexing. |
| [reindex-all-impl.md](./rag/reindex-all-impl.md) | How `reindex_all.py` orchestrates full or partial reindexing. |
| [search-ui-impl.md](./rag/search-ui-impl.md) | Implementation of `search_ui.py` (embedding, Qdrant search, Flask UI). |
| [agent-impl.md](./rag/agent-impl.md) | Implementation of `agent.py` (RAG retrieval, Ollama, SSE streaming, commit summary, audio from knowledge, explain-this, donor analysis, daily fetch pipeline). |
| [learning-features-impl.md](./rag/learning-features-impl.md) | Learning modes: AI Learning, Tech English, Casual English, Notes system. |
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

| Document | Description |
|----------|-------------|
| [stock/README.md](./stock/README.md) | Stock module navigation index (links to all 10 stock implementation docs). |
| [stock-prediction-impl.md](./stock/stock-prediction-impl.md) | End-to-end architecture overview, module graph, anti-overfitting, market risk signals. |
| [config-impl.md](./stock/config-impl.md) | Configuration, paths, Ollama models, environment variables. |
| [data-layer-impl.md](./stock/data-layer-impl.md) | `fetch_market_data`, `watchlist`, `hot_sectors` — data acquisition and caching. |
| [analysis-engines-impl.md](./stock/analysis-engines-impl.md) | Technical, fundamental, sentiment analysis engines. |
| [ml-pipeline-impl.md](./stock/ml-pipeline-impl.md) | Feature engineering, XGBoost classifier/regressor, prediction tracker. |
| [market-signals-impl.md](./stock/market-signals-impl.md) | Fear & Greed, VIX, world news black swan detection. |
| [scanner-impl.md](./stock/scanner-impl.md) | 3-layer full-market AI recommendation scanner. |
| [llm-synthesis-impl.md](./stock/llm-synthesis-impl.md) | Ollama-powered Chinese narrative synthesis. |
| [api-routes-impl.md](./stock/api-routes-impl.md) | All stock Flask API endpoints, thread safety, error handling. |

### Stack overview

| Document | Description |
|----------|-------------|
| [tech-stack-overview.md](./tech-stack-overview.md) | End-to-end technology stack, data flow, and how each component fits together. |

## Reading order

1. **[tech-stack-overview.md](./tech-stack-overview.md)** — Start here for architecture, data flow, and which scripts touch which systems.
2. **Learning guides** — If any stack piece is unfamiliar, read the matching guide under [docs/learning/](../learning/) before deep-diving into scripts.
3. **Briefing pipeline** — Follow [fetcher-pattern-impl.md](./briefing-pipeline/fetcher-pattern-impl.md), then [pipeline-orchestration-impl.md](./briefing-pipeline/pipeline-orchestration-impl.md), then [topic-dedup-impl.md](./briefing-pipeline/topic-dedup-impl.md) and [output-generation-impl.md](./briefing-pipeline/output-generation-impl.md) if you work on sources, merge, or PDF/audio/video output.
4. **RAG** — Read [reindex-all-impl.md](./rag/reindex-all-impl.md) for orchestration, then the specific indexer doc (`index-*-impl.md`) you are changing; finish with [search-ui-impl.md](./rag/search-ui-impl.md) and [agent-impl.md](./rag/agent-impl.md) for query paths.

## Prerequisites

New to embeddings, vector search, Flask, Playwright, local LLMs, or PDF tooling? The **[learning guides](../learning/)** are organized by topic (RAG, LLM, ML, Hugging Face, Python Web, Data Acquisition). They are written to support the implementation docs and reduce the need to read upstream documentation from scratch. After that, [tech-stack-overview.md](./tech-stack-overview.md) ties those concepts to Jarvis-specific paths, ports, and filenames.
