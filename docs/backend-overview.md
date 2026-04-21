---
tags:
  - architecture
  - implementation
  - reference
category: reference
status: current
last-updated: 2026-04-21
---

# Jarvis Backend — Complete System Guide

> A comprehensive reference for understanding the entire Jarvis backend:
> data collection, processing, indexing, serving, and management.

---

## Table of Contents

1. [System Architecture](#system-architecture)
2. [Directory Structure](#directory-structure)
3. [The Two Web Servers](#the-two-web-servers)
4. [Data Pipeline (End to End)](#data-pipeline-end-to-end)
5. [RAG Store (Qdrant + JSON Snapshot)](#rag-store-qdrant--json-snapshot)
6. [Indexing System](#indexing-system)
7. [Data Collection Scripts](#data-collection-scripts)
8. [Processing & Output Scripts](#processing--output-scripts)
9. [All API Endpoints](#all-api-endpoints)
10. [Configuration Reference](#configuration-reference)
11. [File & Path Reference](#file--path-reference)
12. [Dependencies](#dependencies)
13. [Common Operations](#common-operations)
14. [System at a Glance](#system-at-a-glance)
15. [Troubleshooting](#troubleshooting)

---

## System Architecture

```
┌─────────────────────────────────────────────────────────────────────────┐
│                         DATA COLLECTION LAYER                          │
│                                                                        │
│  run-all-sources.py ──┬── fetch-arxiv-ml.py      (arXiv ML papers)    │
│                       ├── fetch-arxiv.py          (arXiv CS papers)    │
│                       ├── fetch-hf-papers.py      (HuggingFace daily) │
│                       ├── fetch-openai-blog.py    (OpenAI blog)       │
│                       ├── fetch-anthropic.py      (Anthropic blog)    │
│                       ├── fetch-deepmind.py       (DeepMind blog)     │
│                       ├── fetch-techcrunch.py     (TechCrunch AI)     │
│                       ├── fetch-github-trending.py(GitHub trending)   │
│                       ├── fetch-mit-review.py     (MIT Tech Review)   │
│                       └── fetch-rundown.py        (The Rundown AI)    │
│                                                                        │
│  run-world-news.py ───┬── fetch-china-news.py     (中国新闻: 5 sources)    │
│                       ├── fetch-bbc-news.py       (BBC World)         │
│                       ├── fetch-reuters.py        (Reuters)            │
│                       ├── fetch-ap-news.py        (AP News)            │
│                       ├── fetch-dw-news.py        (Deutsche Welle)     │
│                       └── fetch-guardian.py       (The Guardian)       │
└────────────────────────────────┬────────────────────────────────────────┘
                                 │
                                 ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                         PROCESSING LAYER                               │
│                                                                        │
│  filter_topics.py ──── Deduplicates across days using topic-index.json │
│  merge-sources.py ──── Merges per-source JSONs into briefing-data.json │
│  (AI agent) ────────── Enriches with commentary, predictions, etc.     │
│  briefing-template.py  Generates PDF report (ReportLab)                │
│  generate-audio.py ─── Generates Chinese podcasts (Edge-TTS)           │
│  generate-video.py ─── Optional video slideshow (MoviePy)              │
└────────────────────────────────┬────────────────────────────────────────┘
                                 │
                                 ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                         INDEXING LAYER (RAG)                            │
│                                                                        │
│  index_briefing.py ──── PDF items, raw articles, learning guides       │
│  index_confluence.py ── Team Confluence wiki pages                      │
│  index_confluence_user.py ── Per-user Confluence pages                  │
│  index_codebase.py ──── Java source, docs, configs from project repos  │
│  index_custom.py ────── Books, notes, tasks from knowledge/ folder     │
│  reindex_all.py ─────── Orchestrator: runs all above incrementally     │
│                                                                        │
│  All indexers → SentenceTransformer → Qdrant (in-memory) → snapshot    │
└────────────────────────────────┬────────────────────────────────────────┘
                                 │
                                 ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                         SERVING LAYER                                  │
│                                                                        │
│  ┌─────────────────────────┐    ┌────────────────────────────────────┐ │
│  │  search_ui.py (:18888)  │    │  agent.py (:18889)                 │ │
│  │                         │    │                                    │ │
│  │  • Semantic search      │    │  • AI chat (Ollama LLM)            │ │
│  │  • Library browser      │    │  • Auto-RAG context injection      │ │
│  │  • Chunk analysis       │    │  • Tool calling (git, Jira, etc.)  │ │
│  │  • Delete documents     │    │  • Session management              │ │
│  │  • Index new briefings  │    │  • Toolbar (reindex, wiki fetch)   │ │
│  │                         │    │  • SSE streaming responses         │ │
│  │  Optional Ollama for    │    │  Requires Ollama running           │ │
│  │  query rewrite only     │    │                                    │ │
│  └─────────────────────────┘    └────────────────────────────────────┘ │
│                                                                        │
│  ┌──────────────────────────────────────────────────────────────────┐  │
│  │  bot_telegram.py (Telegram polling)                              │  │
│  │  • Remote command interface via Telegram                         │  │
│  │  • Calls agent.py + search_ui.py APIs internally                 │  │
│  │  • Owner-only access, SOCKS proxy support                        │  │
│  └──────────────────────────────────────────────────────────────────┘  │
│                                                                        │
│  Both load the same .rag-store.json into separate in-memory Qdrant    │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## Directory Structure

```
jarvis/                               # Project root (C:\jarvis or wherever installed)
├── README.md                         # User-facing guide
├── bin/                              # Executable launchers (double-click from Explorer)
│   ├── jarvis-start.bat              # Start both servers
│   ├── jarvis-stop.bat               # Stop both servers
│   ├── jarvis-restart.bat            # Restart both servers
│   └── jarvis-servers.bat            # Interactive server manager menu
├── docs/
│   ├── rag-agent-design.md           # Agent architecture deep-dive
│   └── backend-overview.md           # This file
├── references/
│   ├── knowledge-scope.md            # Reader profile for briefing tone
│   └── ai-glossary-and-trends.md     # Living glossary (updated each run)
└── scripts/
    ├── config.py                     # Centralized path configuration
    ├── raw_saver.py                  # Shared raw markdown writer
    ├── pipeline/                     # Briefing orchestration & processing
    │   ├── run-all-sources.py        # AI data collection orchestrator
    │   ├── run-world-news.py         # World news collection orchestrator
    │   ├── preflight-check.py        # URL reachability check
    │   ├── merge-sources.py          # Merges per-source JSONs
    │   ├── filter_topics.py          # Cross-day topic deduplication
    │   └── topic_index.py            # Topic classification helper
    ├── output/                       # Final deliverable generation
    │   ├── briefing-template.py      # PDF generation (ReportLab)
    │   ├── generate-audio.py         # TTS podcast generation (Edge-TTS)
    │   └── generate-video.py         # Optional video slideshow (MoviePy)
    ├── tools/                        # Standalone utility scripts
    │   ├── atlassian-report.ps1      # Jira + Confluence daily report
    │   ├── commit-report.ps1         # Multi-repo git commit report
    │   ├── parse-cryos-donors.py     # Cryos donor parser
    │   └── generate_learning_guide.py # Reading list from raw articles
    ├── fetchers/                     # Data source scrapers
    │   ├── ai/                       # AI industry sources (10 scripts)
    │   └── news/                     # World news sources (6 scripts, incl. China)
    ├── stock/                        # A-share stock analysis & ML prediction
    │   ├── config.py                # Stock paths, env vars, Ollama model tiers
    │   ├── fetch_market_data.py     # OHLCV + profile + news (akshare + Sina)
    │   ├── watchlist.py             # Watchlist CRUD, batch refresh, search
    │   ├── technical_analysis.py    # 9 indicators, signals, K-line patterns
    │   ├── report_technical.py      # Chinese Markdown technical report
    │   ├── fundamental_analysis.py  # Financial data, 0-100 scoring
    │   ├── sentiment.py             # LLM sentiment analysis (Ollama)
    │   ├── llm_reasoning.py         # AI synthesis → prediction report
    │   ├── features.py              # ML feature engineering
    │   ├── model_xgboost.py         # XGBoost walk-forward prediction
    │   ├── scanner.py               # 3-layer market scanner (Layer1→2→3, background thread)
    │   ├── hot_sectors.py           # Hot sector detection for scanner bonus scoring
    │   ├── model_price_predictor.py # XGBoost regression for next-day close/high/low price prediction
    │   └── prediction_tracker.py  # Prediction vs actual price tracking, accuracy stats, and cross-symbol aggregate statistics
    └── rag/                          # RAG subsystem
        ├── agent.py                  # Jarvis chat agent server (:18889)
        ├── search_ui.py              # RAG search UI server (:18888)
        ├── index_briefing.py         # Briefing indexer
        ├── index_confluence.py       # Team Confluence indexer
        ├── index_confluence_user.py  # Per-user Confluence indexer
        ├── index_codebase.py         # Java/docs codebase indexer
        ├── index_custom.py           # Custom knowledge indexer
        ├── reindex_all.py            # Incremental reindex orchestrator
        ├── bm25_index.py             # BM25 keyword search index
        ├── reranker.py               # Cross-encoder re-ranker
        └── feedback_store.py         # User feedback collection & scoring
```

---

## The Two Web Servers

Jarvis runs **two independent Flask servers**. They do NOT communicate with each other.

### Server 1: RAG Search UI (`search_ui.py`) — Port 18888

**Purpose:** A lightweight web interface for searching, browsing, and managing the RAG knowledge base. Core search works without Ollama; **query rewriting** optionally uses Ollama and degrades gracefully if it is unavailable.

**Features:**
| Feature | Description |
|---------|-------------|
| **Search** | Semantic search with filters (date, source, type, difficulty) |
| **Library** | Browse all indexed documents, view full content, delete documents |
| **Chunk Analysis** | Statistics: total chunks, breakdown by source and type |
| **Index New** | One-click indexing of new briefing date folders |
| **Delete** | Remove documents and their chunks from the RAG store |
| **Hybrid Search** | BM25 + vector fusion with Reciprocal Rank Fusion (RRF) |
| **Cross-Encoder Re-Ranking** | Re-ranks top 20 candidates using ms-marco-MiniLM-L-6-v2 (skips re-ranking if the model cannot load) |
| **Query Rewriting** | LLM rewrites vague queries for better retrieval (via Ollama `qwen3:1.7b`) |
| **Pipeline Visibility** | Shows RAG pipeline stages, hit counts, timing, and query rewrite (when applied) per search |
| **Feedback Collection** | Thumbs up/down buttons + auto-feedback on chunk expansion |
| **Score Breakdown** | Each result shows vector, rerank, and feedback scores |

**Start command:**
```powershell
$env:PYTHONUNBUFFERED = "1"
$env:PYTHONDONTWRITEBYTECODE = "1"
python -u -B scripts/rag/search_ui.py 18888
```

**Does NOT require:** Ollama for basic search. For **optional** vague-query rewriting, Ollama with `qwen3:1.7b` improves results; if Ollama is absent or the cross-encoder model is unavailable, search still returns results (rewrite and re-ranking degrade gracefully).

### Server 2: Jarvis Chat Agent (`agent.py`) — Port 18889

**Purpose:** An AI-powered chat assistant with RAG context, tool calling, and streaming responses.

**Features:**
| Feature | Description |
|---------|-------------|
| **Chat** | Conversational AI with streaming (SSE) responses |
| **Auto-RAG** | Automatically searches knowledge base for every query |
| **Tools** | Git commits, Jira reports, Confluence search, image analysis |
| **Sessions** | Persistent chat history across browser refreshes |
| **Toolbar** | Medavis, Usage Tools, Data Analysis, Personal, Learning (see [Toolbar](#toolbar)) |
| **Model switching** | Switch between Ollama models at runtime |
| **Hybrid Search** | BM25 + vector fusion in auto-RAG pipeline |
| **Query Rewriting** | LLM rewrites vague queries for better retrieval |
| **Data Analysis** | Trend Analysis and AI News Knowledge Base tools |

**Start command:**
```powershell
$env:PYTHONUNBUFFERED = "1"
$env:PYTHONDONTWRITEBYTECODE = "1"
python -u -B scripts/rag/agent.py
```

**Requires:** Ollama running at `http://localhost:11434` with a model pulled (default: `qwen3.5:4b`)

### Toolbar

The agent toolbar is grouped into these categories:

- **Medavis**: Wiki Fetch, Jira Daily, Commit Summary, Team Activity
- **Usage Tools**: Audio from Knowledge, Explain This
- **Data Analysis**: Trend Analysis, AI News KB
- **Personal**: Donor Analysis, Daily Fetch (includes AI/World/China news fetch, commit report, Jira, Wiki Fetch with page details & links, world news merge recovery, segmented audio with anti-duplication narration)
- **Learning**: AI Learning, Tech English, Casual English, AWS AIF-C01, My Notes
- **Stock**: Stock Analysis, Watchlist management, Market Data Refresh, AI Prediction, AI Scanner (全市场扫描推荐 TOP 5)

### Why Two Servers?

- **search_ui.py** is fast and simple — it loads instantly, needs no GPU, and does not require Ollama for retrieval; optional Ollama is used only for vague-query rewriting when available.
- **agent.py** is the full AI assistant — it needs Ollama and is slower to respond (CPU inference), but provides intelligent answers with context.
- Both read the same `C:/reports/ai/.rag-store.json` snapshot on startup.
- Changes to the snapshot (e.g., after indexing or deleting) require either a server restart or an internal client reset to take effect.

---

## Data Pipeline (End to End)

The daily briefing pipeline runs in 6 phases:

### Phase 0: Data Collection

```
run-all-sources.py
  ├── preflight-check.py (verify source URLs are reachable)
  ├── [parallel] 9 fetch scripts → per-source JSON files
  ├── merge-sources.py → briefing-data.json
  ├── filter_topics.py → briefing-data-filtered.json (deduplicated)
  ├── generate_learning_guide.py → learning-guide.md (if raw/ exists)
  ├── rag/index_briefing.py (index the temp output folder)
  └── rag/index_confluence.py (index team wiki)

run-world-news.py
  └── [parallel] 6 news fetch scripts → merge → Ollama translation → world-news-data.json
```

**Output directory:** `%TEMP%\briefing-YYYY-MM-DD\`

### Phase 1: Synthesis (AI-driven)

An AI agent (the Cursor assistant) enriches the filtered data:
- Adds commentary, predictions, personal relevance
- Fills company moves, community buzz, cross-cutting analysis
- Generates skill radar and big-picture forecast
- Output: enriched `briefing-data.json`

### Phase 2: PDF + Audio Generation

```
briefing-template.py → C:/reports/ai/YYYY-MM-DD/ai-briefing.pdf
```

Audio is generated by the Daily Fetch pipeline in `agent.py` using segmented narration:
- Splits content by source (AI Brief) or category (World News / China News)
- Generates per-segment narration via `qwen3:1.7b` (`OLLAMA_MODEL_NARRATION`) with `think: false`
- Language is configurable per audio type via Global Settings (⚙ gear icon in header)
- Chinese narration prompts explicitly prevent English duplication — only proper nouns (company names, model names) stay in English
- World News audio contains only international items; Chinese News audio is separate
- When Chinese is selected, audio prefers translated `title_zh`/`summary_zh` fields
- Converts each segment to speech via Edge-TTS (`zh-CN-YunxiNeural` / `en-US-AndrewNeural`), then combines into one MP3 per type

```
agent.py (Daily Fetch) → C:/reports/ai/YYYY-MM-DD/ai-briefing.mp3
                        → C:/reports/ai/YYYY-MM-DD/world-news.mp3   (international)
                        → C:/reports/ai/YYYY-MM-DD/china-news.mp3   (中国新闻)
```

The standalone `generate-audio.py` script still exists for manual/legacy use but is not called by Daily Fetch.

### Phase 3: Glossary Update

New AI terms from the briefing are appended to `references/ai-glossary-and-trends.md`.

### Phase 4: RAG Indexing

Already done by `run-all-sources.py` in Phase 0 (indexes the temp folder).
The "Index New" button in the Search UI indexes the final dated folders under `C:/reports/ai/`.

### Phase 5: World News Audio

Generated alongside AI audio in Phase 2 by the Daily Fetch segmented pipeline in `agent.py`.

---

## RAG Store (Qdrant + JSON Snapshot)

### How It Works

The RAG system uses **Qdrant in-memory** as the vector database. Since Qdrant runs in-memory (no separate server), all data is loaded from and saved to a **JSON snapshot file**.

```
                    ┌─────────────────────────┐
                    │  .rag-store.json         │
                    │  (persistent storage)    │
                    │                          │
                    │  {                       │
                    │    "count": 18520,       │
                    │    "points": [           │
                    │      {                   │
                    │        "id": "uuid...",  │
                    │        "vector": [...],  │  ← 384-dim float array
                    │        "payload": {      │
                    │          "title": "...", │
                    │          "text": "...",  │
                    │          "date": "...",  │
                    │          "source": "...",│
                    │          "item_type": ".."│
                    │        }                 │
                    │      }, ...              │
                    │    ]                     │
                    │  }                       │
                    └────────────┬─────────────┘
                                 │
                    On startup:  │  Load into memory
                                 ▼
                    ┌─────────────────────────┐
                    │  Qdrant (in-memory)      │
                    │  Collection: ai_briefings│
                    │  384-dim cosine vectors  │
                    │  ~18,500 points          │
                    └─────────────────────────┘
```

### Snapshot File

- **Path:** `C:/reports/ai/.rag-store.json`
- **Format:** `{ "count": N, "points": [ { "id", "vector", "payload" }, ... ] }`
- **Size:** ~150-200 MB (18,500+ points with 384-dim vectors)

### Embedding Model

- **Model:** `all-MiniLM-L6-v2` from SentenceTransformers
- **Dimensions:** 384
- **Distance metric:** Cosine similarity
- **Load time:** ~6 seconds (first use, cached after)
- **Encoding speed:** ~24ms per query

### Payload Fields

Every indexed chunk has these payload fields:

| Field | Type | Description | Example |
|-------|------|-------------|---------|
| `title` | string | Chunk/section title | "GPT-5 Architecture Changes" |
| `text` | string | Full chunk text content | "The new architecture..." |
| `date` | string | Date (YYYY-MM-DD) | "2026-04-10" |
| `source` | string | Origin of the content | "PDF Briefing", "arxiv-ml", "custom" |
| `item_type` | string | Content category | "news_item", "wiki_page", "code_doc" |
| `filename` | string | Source filename | "ai-briefing.pdf" |
| `parent_title` | string | Parent document title | "AI Briefing 2026-04-10" |
| `url` | string | Original URL (if any) | "https://arxiv.org/..." |
| `difficulty` | string | Difficulty level | "beginner", "intermediate", "advanced" |
| `chunk_index` | int | Position within document | 0, 1, 2, ... |

### Item Types

| `item_type` | Source | Description |
|-------------|--------|-------------|
| `news_item` | Briefing PDF | News items extracted from daily PDF |
| `raw_content` | Fetch scripts | Raw article markdown |
| `learning_guide` | Learning guide | Generated reading list |
| `wiki_page` | Confluence | Team/personal wiki pages |
| `code_doc` | Codebase | Java source, Javadoc, configs |
| `project_doc` | Codebase/Custom | Project documentation |
| `book_chapter` | Custom knowledge | Book content (PDF/MD) |
| `personal_note` | Custom knowledge | Personal notes |
| `task` | Custom knowledge | Task descriptions |

---

## Indexing System

### Overview

Each indexer follows the same pattern:
1. Read source content (files, APIs, scripts)
2. Chunk text into manageable pieces
3. Generate embeddings with SentenceTransformer
4. Upsert into Qdrant collection
5. Save snapshot to `.rag-store.json`

### Indexer Details

#### `index_briefing.py` — Daily Briefings

**What it indexes:** Content from date folders under `C:/reports/ai/YYYY-MM-DD/`

| Content | Source File | Item Type |
|---------|------------|-----------|
| PDF sections | `ai-briefing.pdf` | `news_item` |
| Raw articles | `raw/*.md` | `raw_content` |
| Learning guide | `learning-guide.md` | `learning_guide` |

**CLI usage:**
```bash
python index_briefing.py C:/reports/ai/2026-04-10    # Index one day
python index_briefing.py --backfill                   # Index all days
```

**Key function:** `index_date_folder(date_folder, client, model) → chunk_count`

#### `index_confluence.py` — Team Wiki

**What it indexes:** Confluence wiki pages from the team space.

**How:** Runs `atlassian-report.ps1` (PowerShell) to generate a markdown report, then parses `### [Title](URL)` blocks, chunks them, and indexes.

**CLI usage:**
```bash
python index_confluence.py
```

#### `index_confluence_user.py` — Per-User Wiki

**What it indexes:** All Confluence pages authored by a specific user.

**How:** Uses the Atlassian REST API to paginate through a user's pages, converts to text, chunks, and indexes.

**CLI usage:**
```bash
python index_confluence_user.py "Rong Yin"
```

#### `index_codebase.py` — Project Source Code

**What it indexes:** Java source files, Markdown docs, and config files from configured project directories.

**Configured projects:**
| Project | Path |
|---------|------|
| P4M Next | `d:/projects/p4m` |
| Admin App | `d:/projects/admin-app` |
| Core Framework | `d:/projects/core-framework` |
| RIS Dashboard | `d:/projects/ris-dashboard` |
| Vaadin UI | `d:/projects/vaadin-ui` |
| AWS Infrastructure | `d:/projects/aws-infra` |

**Java extraction:** Extracts class signatures, method signatures, Javadoc comments, and structural summaries rather than raw source code.

**CLI usage:**
```bash
python index_codebase.py                    # Index all configured projects
python index_codebase.py d:/projects/myapp  # Index a custom path
```

#### `index_custom.py` — Custom Knowledge Base

**What it indexes:** Files placed in `C:/reports/ai/knowledge/` subfolders.

**Folder-to-type mapping:**
| Folder | Item Type |
|--------|-----------|
| `knowledge/books/` | `book_chapter` |
| `knowledge/projects/` | `project_doc` |
| `knowledge/notes/` | `personal_note` |
| `knowledge/tasks/` | `task` |

**Supported formats:** `.md`, `.txt`, `.pdf`
**Markdown files** can use YAML frontmatter for metadata (title, author, date, tags).

**CLI usage:**
```bash
python index_custom.py scan                           # Scan and index all
python index_custom.py add C:/path/to/file.pdf        # Add a single file
python index_custom.py list                            # List indexed custom items
python index_custom.py remove "Document Title"         # Remove by title
```

#### `reindex_all.py` — Incremental Orchestrator

**What it does:** Runs all indexers with change detection. Only re-indexes sources that have changed.

**Manifest:** `C:/reports/ai/.index-manifest.json` tracks what was indexed and when.

| Source | Change Detection | Re-index When |
|--------|-----------------|---------------|
| Briefings | Folder mtime | New folder or folder modified |
| Codebase | Directory hash | Any file added/removed/modified |
| Confluence (team) | Time-based | Older than 24 hours |
| Confluence (user) | Time-based | Older than 7 days |

**Optimization:** Loads the embedding model and Qdrant client **once**, passes them to all indexers, saves the snapshot **once** at the end.

**CLI usage:**
```bash
python reindex_all.py                    # Incremental
python reindex_all.py --force            # Force everything
python reindex_all.py --force-briefings  # Force only briefings
python reindex_all.py --force-codebase   # Force only codebase
python reindex_all.py --force-confluence # Force only Confluence
```

---

## Data Collection Scripts

### AI Sources (`run-all-sources.py`)

The orchestrator runs these fetch scripts **in parallel**:

| Script | Source | What It Fetches |
|--------|--------|-----------------|
| `fetch-arxiv-ml.py` | arXiv | Machine learning papers (cs.LG, cs.AI) |
| `fetch-arxiv.py` | arXiv | General CS papers |
| `fetch-hf-papers.py` | HuggingFace | Daily papers feed |
| `fetch-openai-blog.py` | OpenAI | Blog posts |
| `fetch-anthropic.py` | Anthropic | Blog posts |
| `fetch-deepmind.py` | DeepMind | Blog posts |
| `fetch-techcrunch.py` | TechCrunch | AI category articles |
| `fetch-github-trending.py` | GitHub | Trending repositories |
| `fetch-mit-review.py` | MIT Tech Review | AI articles |
| `fetch-rundown.py` | The Rundown AI | Newsletter digest |

**Each fetch script:**
1. Uses Playwright (headless browser) to scrape the source
2. Outputs a JSON file (e.g., `arxiv-ml.json`) with article metadata
3. Optionally saves raw article text to `raw/*.md` via `raw_saver.py`

**Post-fetch pipeline:**
1. `merge-sources.py` — Combines all per-source JSONs into `briefing-data.json`
2. `filter_topics.py` — Deduplicates against `C:/reports/ai/topic-index.json` (cross-day dedup)
3. `generate_learning_guide.py` — Creates a reading list from `raw/` articles

### World News Sources (`run-world-news.py`)

| Script | Source |
|--------|--------|
| `fetch-china-news.py` | 中国新闻 (新浪 + 人民日报 + 财联社 + 头条 + 微博, cross-day dedup) — **priority 0** |
| `fetch-bbc-news.py` | BBC World News |
| `fetch-reuters.py` | Reuters |
| `fetch-ap-news.py` | AP News |
| `fetch-dw-news.py` | Deutsche Welle |
| `fetch-guardian.py` | The Guardian |

Output: `world-news-data.json` categorized by politics, economics, technology, science. All English titles/summaries are auto-translated to Chinese via Ollama (`title_zh`/`summary_zh` fields). Chinese news items already carry native `_zh` fields.

### Helper Scripts

| Script | Purpose |
|--------|---------|
| `preflight-check.py` | Tests URL reachability before fetching |
| `raw_saver.py` | Shared utility for saving raw markdown articles |
| `topic_index.py` | Topic classification engine used by `filter_topics.py` |

---

## Processing & Output Scripts

| Script | Input | Output | Dependencies |
|--------|-------|--------|-------------|
| `briefing-template.py` | `briefing-data.json` | `ai-briefing.pdf` | `reportlab` |
| `generate-audio.py` | `narration.json`, `world-news-narration.json` | `ai-briefing.mp3`, `world-news.mp3` | `edge-tts`, `ffmpeg` |
| `generate-video.py` | Briefing data + images | Video slideshow | `moviepy`, `edge-tts` |
| `generate_learning_guide.py` | `raw/*.md` files | `learning-guide.md` | stdlib |

---

## All API Endpoints

### Search UI Server (Port 18888)

| Method | Path | Purpose | Request | Response |
|--------|------|---------|---------|----------|
| GET | `/` | Web UI | — | HTML page |
| GET | `/api/search` | Semantic search | `?query=...&date_from=&date_to=&source=&difficulty=&item_type=&top_k=10&min_score=0.5` | `{ results: [...], query, total, pipeline_info }` (see [search-ui-impl.md](implementation/rag/search-ui-impl.md) for `pipeline_info`, including optional `original_query` / `rewritten_query`) |
| GET | `/api/document` | Get all chunks of a document | `?filename=...&parent_title=...` | `{ chunks: [...], total_chunks }` |
| GET | `/api/library` | List all documents | `?item_type=...` | `{ documents: [...], total_documents, total_chunks }` |
| GET | `/api/chunk-analysis` | Chunk statistics | — | `{ total, by_source: {...}, by_type: {...} }` |
| POST | `/api/delete` | Delete a document | `{ filename, parent_title }` | `{ removed, remaining }` |
| POST | `/api/index-new` | Start indexing new briefings | — | `{ job_id, status: "started" }` |
| GET | `/api/index-new/<job_id>` | Poll indexing job | — | `{ status, result, new_items: [...] }` |
| POST | `/api/feedback` | Record user feedback | `{ query, chunk_id, action, position }` | `{ recorded: true }` |

### Jarvis Agent Server (Port 18889)

| Method | Path | Purpose | Request | Response |
|--------|------|---------|---------|----------|
| GET | `/` | Chat UI | — | HTML page |
| POST | `/api/agent` | Chat (streaming) | `{ query, image?, history? }` | SSE stream |
| GET | `/api/health` | System health | — | `{ ollama, qdrant }` |
| GET | `/api/switch-model` | Get current model | — | `{ model }` |
| POST | `/api/switch-model` | Set model | `{ model }` | `{ model }` |
| GET | `/api/sessions` | List chat sessions | — | `[{ id, title, created, updated }]` |
| POST | `/api/sessions` | Create session | — | `{ id, title, ... }` |
| GET | `/api/sessions/<id>` | Load session | — | `{ id, messages: [...] }` |
| DELETE | `/api/sessions/<id>` | Delete session | — | `{ deleted: true }` |
| POST | `/api/sessions/<id>/messages` | Save message pair | `{ user, assistant }` | `{ saved: true }` |
| POST | `/api/toolbar/reindex` | Index new briefings | — | `{ job_id, status }` |
| GET | `/api/toolbar/reindex/<job_id>` | Poll reindex job | — | `{ status, result }` |
| POST | `/api/toolbar/wiki-fetch` | Fetch wiki pages | `{ users: [...] }` | `{ job_id, status }` |
| GET | `/api/toolbar/wiki-fetch/<job_id>` | Poll wiki job | — | `{ status, result }` |
| GET | `/api/toolbar/chunk-analysis` | Chunk stats (cached 60s) | — | `{ total, by_source, by_type }` |
| POST | `/api/toolbar/commit-summary` | Git commit summary | `{ hours: N }` | `{ summary }` |
| POST | `/api/toolbar/jira-report` | Jira/Confluence report | — | `{ report }` |
| POST | `/api/feedback` | Record user feedback | `{ query, chunk_id, action, position }` | `{ recorded: true }` |
| GET | `/api/toolbar/ai-news-kb` | Get AI News KB data | — | `{ items: [...], last_scan }` |
| POST | `/api/toolbar/ai-news-kb/scan` | Scan briefings for AI news items | — | `{ new_items, total }` |
| POST | `/api/toolbar/ai-news-kb/summary` | Generate AI summary of KB items | — | SSE stream |
| POST | `/api/toolbar/trend-analysis` | Run trend predictions | `{ categories, days }` | SSE stream |
| GET | `/api/toolbar/audio-knowledge/history` | List generated audio files | — | `{ history: [...] }` |
| GET | `/api/toolbar/audio-knowledge/items` | List documents by type | `?type=book_chapter` | `{ items: [...], show_dates }` |
| POST | `/api/toolbar/audio-knowledge` | Start audio generation | `{ item_type, selected_parents, language }` | `{ job_id }` |
| GET | `/api/toolbar/audio-knowledge/<job_id>` | Poll audio job status | — | `{ status, output_url, ... }` |
| POST | `/api/sessions/<id>/clear` | Clear session messages | — | `{ cleared: true }` |
| GET | `/api/notes` | List saved notes | — | `[{ id, content, created }]` |
| POST | `/api/notes` | Save a note | `{ content }` | `{ id, content, created }` |
| PUT | `/api/notes/<id>` | Update a note | `{ content }` | `{ updated: true }` |
| DELETE | `/api/notes/<id>` | Delete a note | — | `{ deleted: true }` |
| POST | `/api/toolbar/daily-fetch` | Start full daily pipeline | — | `{ job_id, status }` |
| POST | `/api/toolbar/daily-fetch/continue` | Continue missing steps only | `{ steps: [...] }` | `{ job_id, status }` |
| GET | `/api/toolbar/daily-fetch/<job_id>` | Poll daily fetch job | — | `{ status, ... }` |
| GET | `/api/toolbar/daily-fetch/history` | Daily Fetch report history | `?date=YYYY-MM-DD` | `{ date, files, stats, missing_steps, ... }` |
| GET | `/api/donor-analysis` | Load and score donors | `?cmv=negative` | `{ donors: [...] }` |
| POST | `/api/donor-analysis/ai-reason` | AI reasoning for top donors | `{ donors, top_n }` | SSE stream |
| POST | `/api/donor-analysis/pdf` | Generate donor PDF report | `{ donors, language }` | `{ pdf_url }` |
| GET | `/api/settings` | Get global settings | — | `{ audio_lang_ai, audio_lang_world, audio_lang_china, audio_lang_knowledge }` |
| POST | `/api/settings` | Update global settings (partial) | `{ audio_lang_world: "en" }` | `{ ok, settings }` |

### Stock API Endpoints (Port 18889, via agent.py)

| Method | Path | Purpose | Request | Response |
|--------|------|---------|---------|----------|
| GET | `/api/stock/watchlist` | List watchlist with prices | — | `{ stocks: [...] }` |
| POST | `/api/stock/watchlist` | Add stock to watchlist | `{ symbol, name, sector, notes }` | `{ entry }` |
| DELETE | `/api/stock/watchlist/<symbol>` | Remove stock from watchlist | — | `true/false` |
| POST | `/api/stock/watchlist/refresh` | Refresh all watchlist data | — | `{ results: [...] }` |
| POST | `/api/stock/analyze` | Full stock analysis | `{ symbol, mode }` | Varies by mode: technical, fundamental, sentiment, xgboost, prediction, full |
| POST | `/api/stock/train/daily` | Start daily price prediction training for watchlist stocks | — | `{ ok, status, results, verifications, aggregate_stats, ... }` — `verifications`: predicted vs actual (watchlist-scoped); `aggregate_stats`: cross-symbol historical accuracy |
| GET | `/api/stock/train/status` | Get training progress | — | `{ status, completed, total, results, verifications, aggregate_stats, ... }` — `aggregate_stats`: direction accuracy, MAPE, MAE, 7d/30d windows, per-symbol detail |
| GET | `/api/stock/predict/{symbol}` | Get price prediction and accuracy stats | — | `{ symbol, prediction, accuracy, health, ... }` — `health`: grade, trend, action |

**Analysis modes for `/api/stock/analyze`:**

| Mode | What it does | Key output |
|------|-------------|------------|
| `technical` | Technical indicators + patterns + report | Markdown report with signals, patterns, support/resistance |
| `fundamental` | Financial data + 0-100 scoring + report | Markdown report with dimension scores |
| `sentiment` | LLM news sentiment analysis | Markdown report with per-article scores |
| `xgboost` | XGBoost walk-forward ML prediction | Markdown report with prediction, confidence, feature importance |
| `prediction` | AI synthesis of all analyses | Streaming Markdown via SSE |
| `full` | Runs technical + fundamental + sentiment + xgboost + prediction sequentially | Combined report sections |

### Stock Scanner API Endpoints (Port 18889, via agent.py)

| Method | Path | Purpose | Request | Response |
|--------|------|---------|---------|----------|
| POST | `/api/stock/scan/start` | Start background 3-layer scan | — | `{ ok, status }` |
| POST | `/api/stock/scan/stop` | Stop running scan | — | `{ ok }` |
| GET | `/api/stock/scan/status` | Get scan progress & results | — | `{ status, running, market_total, total_stocks, layer1_count, analyzed_count, top_picks }` |
| GET | `/api/stock/scan/result` | Get latest scan result | — | `{ date, meta, top_picks, candidates }` |
| GET | `/api/stock/scan/result/<date>` | Get scan result by date | — | `{ date, meta, top_picks, candidates }` |
| GET | `/api/stock/scan/dates` | List available scan dates | — | `{ dates: ["2026-04-14", ...] }` |
| GET | `/api/stock/scan/history` | Get scan history summary | — | `{ history: [...] }` |

**Scanner 3-layer flow:**

| Layer | Input | Output | Cap |
|-------|-------|--------|-----|
| Layer 1 | Full A-share market (~5000+) | Filtered by price, turnover, PE, not-ST | Top 100 |
| Layer 2 | 100 candidates | Technical + sentiment analysis, composite scoring | Top 20 |
| Layer 3 | 20 candidates | LLM scoring with buy-price recommendation | Top 5 |

**Scanner LLM (Layer 3):** Calls Ollama via `POST /api/chat` with `"think": false` instead of `/api/generate`, so the qwen3.5 thinking model does not consume all tokens on `<think>` blocks.

**Top pick fields:** `symbol`, `name`, `final_score`, `price`, `change_pct`, `pe`, `tech_score`, `sentiment_score`, `is_hot`, `reasoning`, `risk`, `buy_low`, `buy_high`

### Agent SSE Event Types

When calling `POST /api/agent`, the response is a Server-Sent Events stream:

| Event | Data | Description |
|-------|------|-------------|
| `model` | `{ "model": "qwen3.5:4b" }` | Which LLM is being used |
| `thinking` | `{ "tool": "rag_search", "args": {...} }` | Tool is being called |
| `tool_result` | `{ "tool": "rag_search", "preview": "..." }` | Tool returned data |
| `token` | `{ "token": "The" }` | Single token from LLM |
| `answer_done` | `{ "sources": [...] }` | Response complete |
| `error` | `{ "error": "message" }` | Error occurred |

### Agent Tools

The agent can call these tools (via Ollama function calling or auto-routing):

| Tool | Auto-Trigger Keywords | Description |
|------|-----------------------|-------------|
| `rag_search` | Always (auto-RAG) | Semantic search across full knowledge base |
| `briefing_search` | — | Date/source-filtered AI briefing search |
| `confluence_search` | — | Wiki page search with space filtering |
| `commit_summary` | "commit", "git log", "pushed", "merged" | Git log across configured repos |
| `jira_report` | "jira", "ticket", "sprint", "backlog" | Runs Jira/Confluence PowerShell report |
| `analyze_image` | (when image attached) | Vision analysis via `qwen3-vl:8b` |

---

## Configuration Reference

### Constants (shared across RAG modules)

| Constant | Value | Used By |
|----------|-------|---------|
| `SNAPSHOT_PATH` | `C:/reports/ai/.rag-store.json` | All indexers + servers |
| `COLLECTION` | `ai_briefings` | All indexers + servers |
| `VECTOR_SIZE` | `384` | All indexers + servers |
| `REPORTS_ROOT` | `C:/reports/ai` | Indexers, servers |

### Agent-specific (`agent.py`)

| Setting | Default | Env Var | Description |
|---------|---------|---------|-------------|
| Port | `18889` | — | CLI arg or default |
| LLM Model | `qwen3.5:4b` | `RAG_AGENT_MODEL` | Ollama model name |
| Narration Model | `qwen3:1.7b` | `RAG_NARRATION_MODEL` | Model for Daily Fetch segmented audio narration |
| Ollama Host | `http://localhost:11434` | — | Ollama API endpoint |
| Max iterations | `8` | — | Max agent loop iterations |
| Tool timeout | `120s` | — | Max time for a tool call |
| Chat sessions dir | `C:/reports/ai/.chat-sessions/` | — | Session storage |

### Search UI-specific (`search_ui.py`)

| Setting | Default | Description |
|---------|---------|-------------|
| Port | `18888` | CLI arg or default |
| Query rewrite model | `qwen3:1.7b` | Ollama `/api/chat`, `think: false`; optional—search works without Ollama |

---

## File & Path Reference

### Persistent Data

| Path | Description |
|------|-------------|
| `C:/reports/ai/.rag-store.json` | RAG vector store snapshot (~150-200 MB) |
| `C:/reports/ai/.index-manifest.json` | Incremental indexing manifest |
| `C:/reports/ai/.chat-sessions/*.json` | Chat session files |
| `C:/reports/ai/topic-index.json` | Cross-day topic deduplication index |
| `C:/reports/ai/YYYY-MM-DD/` | Daily briefing output folders |
| `C:/reports/ai/knowledge/` | Custom knowledge base root |
| `C:/reports/ai/.rag-feedback.json` | User feedback events and chunk scores |
| `C:/reports/ai/.ai-news-kb.json` | AI News Knowledge Base persistent store |

### Stock Data

| Path | Description |
|------|-------------|
| `C:/reports/stock/data/{symbol}/daily.csv` | Historical OHLCV data (前复权) |
| `C:/reports/stock/data/{symbol}/realtime.json` | Latest real-time quote |
| `C:/reports/stock/data/{symbol}/profile.json` | Company info (industry, market cap) |
| `C:/reports/stock/data/{symbol}/news/*.json` | Daily news articles |
| `C:/reports/stock/data/{symbol}/technical.json` | Technical analysis results |
| `C:/reports/stock/data/{symbol}/fundamentals.json` | Financial data cache |
| `C:/reports/stock/data/{symbol}/sentiment.json` | Sentiment analysis results |
| `C:/reports/stock/data/{symbol}/xgb_prediction.json` | XGBoost ML prediction |
| `C:/reports/stock/data/{symbol}/price_prediction.json` | Latest price prediction |
| `C:/reports/stock/data/{symbol}/predictions_log.json` | Prediction history log; entries also store `error_pct_high` and `error_pct_low` |
| `C:/reports/stock/data/{symbol}/*.md` | Generated Markdown reports |
| `C:/reports/stock/models/{symbol}/model.json` | Persisted XGBoost model |
| `C:/reports/stock/models/{symbol}/price_close_model.json` | XGBoost close price model |
| `C:/reports/stock/models/{symbol}/price_high_model.json` | XGBoost high price model |
| `C:/reports/stock/models/{symbol}/price_low_model.json` | XGBoost low price model |
| `C:/reports/stock/models/{symbol}/features.json` | Feature column list |
| `C:/reports/stock/train_progress.json` | Training progress state |
| `C:/reports/stock/watchlist.json` | Personal watchlist |
| `C:/reports/stock/scans/{YYYY-MM-DD}.json` | Daily scan results (meta, top_picks, candidates) |
| `C:/reports/stock/scans/{YYYY-MM-DD}-report.md` | Daily scan Markdown report |
| `C:/reports/stock/scans/scan_progress.json` | Real-time scan progress |
| `C:/reports/stock/scans/history.json` | Scan history with performance tracking |

### Daily Briefing Outputs (per date folder)

| File | Description |
|------|-------------|
| `ai-briefing.pdf` | The daily AI briefing PDF |
| `ai-briefing.mp3` | AI news podcast |
| `world-news.mp3` | International world news podcast |
| `china-news.mp3` | Chinese political/financial news podcast |
| `briefing-data.json` | Raw + enriched briefing data |
| `raw/*.md` | Raw article markdown files |
| `learning-guide.md` | Generated reading list |

### Temporary (during collection)

| Path | Description |
|------|-------------|
| `%TEMP%/briefing-YYYY-MM-DD/` | Temp output during data collection |
| `%TEMP%/briefing-YYYY-MM-DD/world-news/` | World news temp output |

---

## Dependencies

### Python Packages

```
flask                    # Web framework (both servers)
qdrant-client            # Vector database client
sentence-transformers    # Embedding model (all-MiniLM-L6-v2)
pypdf                    # PDF text extraction
reportlab                # PDF generation
edge-tts                 # Text-to-speech (Chinese podcasts)
playwright               # Web scraping (fetch scripts)
requests                 # HTTP client (Confluence API)
pyyaml                   # YAML frontmatter parsing
feedparser               # RSS feed parsing (some fetch scripts)
ollama                   # Ollama Python client (agent only)
rank-bm25                # BM25 keyword search (hybrid search)
akshare                  # Chinese A-share financial data API (stock module)
pandas-ta                # Technical indicators (stock module)
xgboost                  # Gradient boosting ML model (stock prediction)
scikit-learn             # ML utilities: LabelEncoder, preprocessing (stock module)
```

### External Services

| Service | Required By | Purpose |
|---------|------------|---------|
| Ollama (`localhost:11434`) | `agent.py` (required); `search_ui.py` (optional, query rewrite) | LLM inference |
| Atlassian Confluence | `index_confluence*.py`, toolbar | Wiki content |
| Jira | Agent toolbar | Sprint/ticket reports |

### System Tools

| Tool | Required By | Purpose |
|------|------------|---------|
| `git` | Agent commit_summary tool | Git log across repos |
| `ffmpeg` | `generate-audio.py` | Audio segment merging |
| PowerShell | Confluence/Jira scripts | Running `.ps1` scripts |

---

## Common Operations

### Start Both Servers

```powershell
# Terminal 1: Search UI (Ollama optional; enables vague-query rewriting when running)
$env:PYTHONUNBUFFERED = "1"
$env:PYTHONDONTWRITEBYTECODE = "1"
python -u -B scripts/rag/search_ui.py 18888

# Terminal 2: Jarvis Agent (needs Ollama)
$env:PYTHONUNBUFFERED = "1"
$env:PYTHONDONTWRITEBYTECODE = "1"
python -u -B scripts/rag/agent.py
```

### Check Server Status

```powershell
netstat -ano | Select-String ":18888|:18889" | Select-String "LISTENING"
```

### Stop a Server

```powershell
# Find PID
netstat -ano | Select-String ":18888"
# Kill it
Stop-Process -Id <PID> -Force
```

### Run Full Reindex

```powershell
python -u scripts/rag/reindex_all.py
```

### Add a Custom Document

```powershell
# Place files in the knowledge folder
Copy-Item "my-book.pdf" "C:\reports\ai\knowledge\books\"

# Index it
python scripts/rag/index_custom.py scan
```

### Check RAG Store Size

```powershell
python -c "import json; d=json.load(open('C:/reports/ai/.rag-store.json')); print(f'Points: {d[\"count\"]}')"
```

---

## System at a Glance

```
┌─────────────────────────────────────────────────────────────────────────┐
│  Maturity: Advanced RAG + Agentic Shell + Stock Prediction              │
│  ML Status: XGBoost stock + AI market scanner + RAG feedback            │
│  Stock: A-share analysis + AI scanner (3-layer → TOP 5 with buy range) │
│  Telegram Bot: Remote command interface (bot_telegram.py, polling)   │
│  Toolbar: 🎯 Price Prediction button — train, forecasts, accuracy        │
│  Next Step: Training data generation → Embedding fine-tuning            │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## Troubleshooting

### Server shows old code after edits

**Cause:** Python bytecode cache (`.pyc` files in `__pycache__/`).

**Fix:**
1. Delete stale bytecode: `Remove-Item -Path "...\__pycache__\search_ui*.pyc" -Force`
2. Always start with `-B` flag: `python -u -B script.py`
3. Set env var: `$env:PYTHONDONTWRITEBYTECODE = "1"`

### No output from background scripts

**Cause:** Python buffers stdout when not connected to a terminal.

**Fix:** Always use `python -u` and `$env:PYTHONUNBUFFERED = "1"`.

### Port already in use

**Fix:**
```powershell
# Find what's using the port
netstat -ano | Select-String ":18888" | Select-String "LISTENING"
# Kill the process
Stop-Process -Id <PID> -Force
# Wait a moment, then restart
Start-Sleep -Seconds 3
```

### Snapshot file too large / slow to load

The `.rag-store.json` file grows with each indexing run. If it becomes too large:
1. Use the **Library** tab in the Search UI to browse documents
2. Use the **Delete** button to remove unwanted documents
3. Consider running `index_custom.py remove "Title"` for specific items

### Ollama not responding (agent only)

```powershell
# Check if Ollama is running
ollama list
# If not, start it
ollama serve
# Pull a model if needed
ollama pull qwen3.5:4b
```

### Changes after indexing not visible in server

Both servers load the snapshot into memory on startup. After indexing:
- **search_ui.py:** The `/api/index-new` and `/api/delete` endpoints automatically reset the in-memory client.
- **agent.py:** Requires a server restart to pick up new data (unless using the toolbar's "Index New" which also resets the client).
