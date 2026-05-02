---
tags:
  - implementation
  - architecture
  - workflow
  - navigation
category: overview
status: current
last-updated: 2026-05-02
---

# Jarvis Workflow Overview

> Master workflow diagram connecting all Jarvis features. Each box links to the detailed implementation doc with its own workflow diagram.

---

## System Architecture — Top-Level Flow

```text
                              ┌─────────────────────────┐
                              │    USER ENTRY POINTS     │
                              │                          │
                              │  Browser UI (:18888/     │
                              │              :18889)     │
                              │  CLI scripts             │
                              │  Telegram bot            │
                              │  Scheduled tasks         │
                              └────────┬────────────────┘
                                       │
                    ┌──────────────────┼──────────────────┐
                    │                  │                   │
                    ▼                  ▼                   ▼
       ┌────────────────────┐  ┌─────────────┐  ┌────────────────────┐
       │  SEARCH UI (:18888)│  │ AGENT (:18889│  │  CLI / AUTOMATION   │
       │  search_ui.py      │  │  agent.py    │  │  scripts/*          │
       └────────┬───────────┘  └──────┬──────┘  └────────┬───────────┘
                │                     │                   │
                ▼                     ▼                   ▼
  ┌──────────────────────────────────────────────────────────────────┐
  │                     FLASK BLUEPRINTS & ROUTES                    │
  │                                                                  │
  │  toolbar_bp    daily_fetch_bp    stock_bp    (agent core)        │
  │                                                                  │
  │  Routes fan out to all feature workflows below:                  │
  └──────┬──────────┬──────────┬──────────┬──────────┬──────────────┘
         │          │          │          │          │
         ▼          ▼          ▼          ▼          ▼
    ┌─────────┐ ┌────────┐ ┌────────┐ ┌────────┐ ┌────────┐
    │PERSONAL │ │MEDAVIS │ │LEARNING│ │ DATA   │ │ USAGE  │
    │         │ │        │ │        │ │ANALYSIS│ │ TOOLS  │
    └────┬────┘ └───┬────┘ └───┬────┘ └───┬────┘ └───┬────┘
         │          │          │          │          │
         ▼          ▼          ▼          ▼          ▼
  ┌──────────────────────────────────────────────────────────────────┐
  │                     SHARED INFRASTRUCTURE                        │
  │                                                                  │
  │  Qdrant (vector DB)  │  Ollama (local LLM)  │  Edge TTS (audio) │
  │  DeepSeek API (opt.) │  httpx / Playwright   │  ffmpeg (media)   │
  └──────────────────────────────────────────────────────────────────┘
```

---

## Feature Workflows by Category

### PERSONAL — Daily Briefing & Content (5 features)

```text
┌─────────────────────────────────────────────────────────────────────────┐
│ ① Daily Fetch Pipeline (daily-fetch-impl.md)                            │
│    Toolbar "Daily Fetch" → background thread                            │
│    → fetch_sources → topic_dedup → commit_report → jira_daily           │
│    → wiki_fetch → ai_audio → world_audio → china_audio                  │
│    → daily summary + audio MP3s                                         │
├─────────────────────────────────────────────────────────────────────────┤
│ ② AI News Knowledge Base (ai-news-kb-impl.md)                          │
│    Briefing JSON → scan items → LLM categorize → KB file                │
│    → API: /api/ai-kb, /api/ai-kb/search                                │
├─────────────────────────────────────────────────────────────────────────┤
│ ③ Audio Knowledge (audio-knowledge-impl.md)                             │
│    Qdrant RAG chunks → LLM narration script → Edge TTS → MP3 output    │
├─────────────────────────────────────────────────────────────────────────┤
│ ④ Trend Analysis (trend-analysis-impl.md)                               │
│    POST /api/toolbar/trend → RAG search + reports scan                  │
│    → per-category LLM analysis → SSE stream to frontend                 │
├─────────────────────────────────────────────────────────────────────────┤
│ ⑤ Global Settings (global-settings-impl.md)                             │
│    Settings modal → GET/POST /api/settings                              │
│    → .global_settings.json → audio lang, Ollama model, DeepSeek key     │
└─────────────────────────────────────────────────────────────────────────┘
```

| # | Feature | Impl Doc |
|---|---------|----------|
| 1 | Daily Fetch Pipeline | [daily-fetch-impl.md](./personal/daily-fetch-impl.md) |
| 2 | AI News Knowledge Base | [ai-news-kb-impl.md](./personal/ai-news-kb-impl.md) |
| 3 | Audio Knowledge | [audio-knowledge-impl.md](./personal/audio-knowledge-impl.md) |
| 4 | Trend Analysis | [trend-analysis-impl.md](./personal/trend-analysis-impl.md) |
| 5 | Global Settings | [global-settings-impl.md](./personal/global-settings-impl.md) |

---

### MEDAVIS — Work / Enterprise (5 features)

```text
┌─────────────────────────────────────────────────────────────────────────┐
│ ① Confluence Indexing (confluence-impl.md)                              │
│    Team CQL / User CQL → fetch pages → strip HTML → extract headings   │
│    → embed MiniLM → Qdrant upsert + version diff summaries             │
├─────────────────────────────────────────────────────────────────────────┤
│ ② JIRA Daily Report (jira-report-impl.md)                               │
│    Toolbar / Daily Fetch → PowerShell Atlassian script                  │
│    → open tickets + activity → Markdown report                          │
├─────────────────────────────────────────────────────────────────────────┤
│ ③ Project Dependency Graph (project-graph-impl.md)                      │
│    pom.xml scan → classify internal/external → JSON graph               │
│    → tool: "what depends on X?", "impact of changing Y?"                │
├─────────────────────────────────────────────────────────────────────────┤
│ ④ Codebase Indexing (codebase-indexing-impl.md)                         │
│    .rag-projects.json → walk Java/MD/config → extract summaries         │
│    → MD5 dedup → embed → Qdrant with project: filter                    │
├─────────────────────────────────────────────────────────────────────────┤
│ ⑤ Commit Summary (commit-summary-impl.md)                               │
│    REPO_CONFIG + auto-discover → git log → author alias                 │
│    → Markdown summary + Bitbucket links + team activity                 │
└─────────────────────────────────────────────────────────────────────────┘
```

| # | Feature | Impl Doc |
|---|---------|----------|
| 1 | Confluence Indexing | [confluence-impl.md](./medavis/confluence-impl.md) |
| 2 | JIRA Daily Report | [jira-report-impl.md](./medavis/jira-report-impl.md) |
| 3 | Project Dependency Graph | [project-graph-impl.md](./medavis/project-graph-impl.md) |
| 4 | Codebase Indexing | [codebase-indexing-impl.md](./medavis/codebase-indexing-impl.md) |
| 5 | Commit Summary | [commit-summary-impl.md](./medavis/commit-summary-impl.md) |

---

### LEARNING — Education & Skill Building (5 features)

```text
┌─────────────────────────────────────────────────────────────────────────┐
│ ① AI Learning Mode (ai-learning-impl.md)                                │
│    Sidebar "AI Learning" → persistent session → roadmap context         │
│    → SYSTEM_PROMPT_AI_LEARNING → Ollama tutor + DuckDuckGo refs         │
├─────────────────────────────────────────────────────────────────────────┤
│ ② Tech English (tech-english-impl.md)                                   │
│    Sidebar "Tech English" → AI news titles → intent classify            │
│    → article fetch → SYSTEM_PROMPT_ENGLISH_LEARNING → vocab/grammar     │
├─────────────────────────────────────────────────────────────────────────┤
│ ③ Casual English (casual-english-impl.md)                               │
│    Sidebar "Casual English" → world news titles → topic selection       │
│    → SYSTEM_PROMPT_CASUAL_ENGLISH → idioms, cultural context, dialogue  │
├─────────────────────────────────────────────────────────────────────────┤
│ ④ AWS AIF-C01 Cert Prep (aws-cert-impl.md)                              │
│    Sidebar "AWS AIF-C01" → roadmap domains → teach/quiz mode            │
│    → progress tracker (.aws-cert-progress.json) → domain completion %   │
├─────────────────────────────────────────────────────────────────────────┤
│ ⑤ Deep Dive & Notes (deep-dive-notes-impl.md)                           │
│    Learning Guide article → "Deep Dive" button → fetch URL/raw content  │
│    → new deep_dive session → SYSTEM_PROMPT_DEEP_DIVE → tutor Q&A        │
│    Notes: CRUD API (/api/notes) → .learning-notes.json                  │
└─────────────────────────────────────────────────────────────────────────┘
```

| # | Feature | Impl Doc |
|---|---------|----------|
| 1 | AI Learning Mode | [ai-learning-impl.md](./learning/ai-learning-impl.md) |
| 2 | Tech English | [tech-english-impl.md](./learning/tech-english-impl.md) |
| 3 | Casual English | [casual-english-impl.md](./learning/casual-english-impl.md) |
| 4 | AWS AIF-C01 Cert Prep | [aws-cert-impl.md](./learning/aws-cert-impl.md) |
| 5 | Deep Dive & Notes | [deep-dive-notes-impl.md](./learning/deep-dive-notes-impl.md) |

---

### DATA ANALYSIS — Analytics & Prediction (5 features)

```text
┌─────────────────────────────────────────────────────────────────────────┐
│ ① Stock Prediction Engine (stock-prediction-impl.md)                    │
│    Market data → feature engineering → XGBoost train/predict            │
│    → direction + price forecast → walk-forward validation               │
├─────────────────────────────────────────────────────────────────────────┤
│ ② Technical & Fundamental Analysis (technical-fundamental-impl.md)      │
│    Price data → TA indicators + patterns + scoring                      │
│    → fundamental metrics → news sentiment → LLM narrative synthesis     │
├─────────────────────────────────────────────────────────────────────────┤
│ ③ Market Scanner (market-scanner-impl.md)                               │
│    Short-term: L1 prefilter → L2 XGBoost → L3 LLM synthesis            │
│    Long-term: theme discovery → sector rotation → RAG indexing          │
├─────────────────────────────────────────────────────────────────────────┤
│ ④ Market Sentiment & Risk (market-sentiment-risk-impl.md)               │
│    Fear/Greed index + VIX + black swan scan                             │
│    → China A-share flows + national team monitor → risk signals         │
├─────────────────────────────────────────────────────────────────────────┤
│ ⑤ Donor Analysis (donor-analysis-impl.md)                               │
│    CSV upload → clinical scoring algorithm → LLM reasoning narrative    │
│    → Top-10 ranking → PDF report                                        │
└─────────────────────────────────────────────────────────────────────────┘
```

| # | Feature | Impl Doc |
|---|---------|----------|
| 1 | Stock Prediction Engine | [stock-prediction-impl.md](./data-analysis/stock-prediction-impl.md) |
| 2 | Technical & Fundamental Analysis | [technical-fundamental-impl.md](./data-analysis/technical-fundamental-impl.md) |
| 3 | Market Scanner | [market-scanner-impl.md](./data-analysis/market-scanner-impl.md) |
| 4 | Market Sentiment & Risk | [market-sentiment-risk-impl.md](./data-analysis/market-sentiment-risk-impl.md) |
| 5 | Donor Analysis | [donor-analysis-impl.md](./data-analysis/donor-analysis-impl.md) |

---

### USAGE TOOLS — Core Platform Tools (5 features)

```text
┌─────────────────────────────────────────────────────────────────────────┐
│ ① RAG Agent Chat (rag-agent-impl.md)                                    │
│    Message input → intent routing → RAG pipeline (search + prompt)      │
│    → Ollama streaming → SSE tokens → sources + disclaimer               │
├─────────────────────────────────────────────────────────────────────────┤
│ ② Search UI / Library (search-ui-impl.md)                               │
│    Search bar → query rewrite → vector + BM25/RRF → rerank             │
│    → results display → feedback loop → library maintenance              │
├─────────────────────────────────────────────────────────────────────────┤
│ ③ Reindex Orchestration (reindex-all-impl.md)                           │
│    CLI / toolbar → manifest check → per-source reindex                  │
│    → briefings → codebase → project graph → confluence → snapshot       │
├─────────────────────────────────────────────────────────────────────────┤
│ ④ Custom File Indexing (custom-indexing-impl.md)                        │
│    CLI / Search UI upload → PDF/MD/TXT parse → YAML front matter        │
│    → embed → Qdrant upsert → snapshot                                   │
├─────────────────────────────────────────────────────────────────────────┤
│ ⑤ Telegram Bot (telegram-bot-impl.md)                                   │
│    Telegram message → owner auth → command dispatch                     │
│    → RAG search / stock APIs / daily pipeline → reply                   │
└─────────────────────────────────────────────────────────────────────────┘
```

| # | Feature | Impl Doc |
|---|---------|----------|
| 1 | RAG Agent Chat | [rag-agent-impl.md](./usage-tool/rag-agent-impl.md) |
| 2 | Search UI / Library | [search-ui-impl.md](./usage-tool/search-ui-impl.md) |
| 3 | Reindex Orchestration | [reindex-all-impl.md](./usage-tool/reindex-all-impl.md) |
| 4 | Custom File Indexing | [custom-indexing-impl.md](./usage-tool/custom-indexing-impl.md) |
| 5 | Telegram Bot | [telegram-bot-impl.md](./usage-tool/telegram-bot-impl.md) |

---

### BRIEFING PIPELINE — Subsystem (5 components)

```text
┌──────────────────────────────────────────────────────────────────────────┐
│                        BRIEFING PIPELINE FLOW                             │
│                                                                           │
│  ┌─────────────┐    ┌──────────────┐    ┌───────────────┐                │
│  │ ① Fetchers   │───▶│ ② Orchestr.  │───▶│ ③ Topic Dedup │                │
│  │ fetch-*.py   │    │ run-all-src  │    │ filter_topics │                │
│  │ safe_fetch   │    │ merge/preflt │    │ topic_index   │                │
│  └─────────────┘    └──────────────┘    └───────┬───────┘                │
│                                                  │                        │
│                                                  ▼                        │
│                     ┌──────────────┐    ┌───────────────┐                │
│                     │ ⑤ World News  │    │ ④ Output Gen  │                │
│                     │ 6 fetchers    │    │ PDF + audio   │                │
│                     │ merge+transl. │    │ + video       │                │
│                     └──────────────┘    └───────────────┘                │
└──────────────────────────────────────────────────────────────────────────┘
```

| # | Component | Impl Doc |
|---|-----------|----------|
| 1 | Fetcher Pattern | [fetcher-pattern-impl.md](./briefing-pipeline/fetcher-pattern-impl.md) |
| 2 | Pipeline Orchestration | [pipeline-orchestration-impl.md](./briefing-pipeline/pipeline-orchestration-impl.md) |
| 3 | Topic Deduplication | [topic-dedup-impl.md](./briefing-pipeline/topic-dedup-impl.md) |
| 4 | Output Generation | [output-generation-impl.md](./briefing-pipeline/output-generation-impl.md) |
| 5 | World News Pipeline | [world-news-impl.md](./briefing-pipeline/world-news-impl.md) |

---

### STOCK MODULE — Subsystem (11 components)

```text
┌──────────────────────────────────────────────────────────────────────────┐
│                         STOCK MODULE FLOW                                 │
│                                                                           │
│  ┌──────────────┐   ┌──────────────┐   ┌──────────────┐                  │
│  │ ① Config      │──▶│ ② Data Layer │──▶│ ③ Analysis    │                  │
│  │ paths, models │   │ fetch, cache │   │ TA + fund +   │                  │
│  │               │   │ watchlist    │   │ sentiment     │                  │
│  └──────────────┘   └──────────────┘   └──────┬───────┘                  │
│                                                │                          │
│            ┌───────────────────────────────────┼──────────────┐           │
│            ▼                                   ▼              ▼           │
│  ┌──────────────┐   ┌──────────────┐   ┌──────────────┐                  │
│  │ ④ ML Pipeline │   │ ⑤ Mkt Signal │   │ ⑥ Scanner     │                  │
│  │ XGBoost train │   │ Fear/Greed   │   │ L1→L2→L3     │                  │
│  │ predict       │   │ VIX, swan    │   │ full market   │                  │
│  └──────┬───────┘   └──────────────┘   └──────┬───────┘                  │
│         │                                      │                          │
│         └────────────────┬─────────────────────┘                          │
│                          ▼                                                │
│              ┌──────────────────────┐   ┌──────────────┐                  │
│              │ ⑦ LLM Synthesis      │──▶│ ⑧ API Routes  │                  │
│              │ Ollama / DeepSeek    │   │ Flask stock_bp│                  │
│              └──────────────────────┘   └──────────────┘                  │
│                                                                           │
│  ┌──────────────┐   ┌──────────────┐   ┌──────────────┐                  │
│  │ ⑨ China Mkt  │   │ ⑩ Prediction │   │ ⑪ Config      │                  │
│  │ A-share, ETF │   │ walk-forward │   │ anti-overfit  │                  │
│  │ timing model │   │ backtesting  │   │ risk signals  │                  │
│  └──────────────┘   └──────────────┘   └──────────────┘                  │
└──────────────────────────────────────────────────────────────────────────┘
```

| # | Component | Impl Doc |
|---|-----------|----------|
| 1 | Config | [config-impl.md](./stock/config-impl.md) |
| 2 | Data Layer | [data-layer-impl.md](./stock/data-layer-impl.md) |
| 3 | Analysis Engines | [analysis-engines-impl.md](./stock/analysis-engines-impl.md) |
| 4 | ML Pipeline | [ml-pipeline-impl.md](./stock/ml-pipeline-impl.md) |
| 5 | Market Signals | [market-signals-impl.md](./stock/market-signals-impl.md) |
| 6 | Scanner | [scanner-impl.md](./stock/scanner-impl.md) |
| 7 | LLM Synthesis | [llm-synthesis-impl.md](./stock/llm-synthesis-impl.md) |
| 8 | API Routes | [api-routes-impl.md](./stock/api-routes-impl.md) |
| 9 | China Market | [china-market-impl.md](./stock/china-market-impl.md) |
| 10 | Stock Prediction | [stock-prediction-impl.md](./stock/stock-prediction-impl.md) |
| 11 | Full Index | [stock/README.md](./stock/README.md) |

---

### RAG SUBSYSTEM — Indexers & Agent (10 components)

```text
┌──────────────────────────────────────────────────────────────────────────┐
│                          RAG SUBSYSTEM FLOW                               │
│                                                                           │
│  INDEXERS (write to Qdrant):                                              │
│  ┌────────────┐ ┌────────────┐ ┌────────────┐ ┌────────────┐            │
│  │ ① Briefing  │ │ ② Codebase │ │ ③ Confluenc│ │ ④ Custom   │            │
│  │ index_brief│ │ index_code │ │ index_conf │ │ index_cust │            │
│  └─────┬──────┘ └─────┬──────┘ └─────┬──────┘ └─────┬──────┘            │
│        └───────────────┴───────────────┴───────────────┘                  │
│                                  │                                        │
│                                  ▼                                        │
│                    ┌──────────────────────┐                               │
│                    │ ⑤ Reindex All         │                               │
│                    │ orchestrates 1-4      │                               │
│                    └──────────┬───────────┘                               │
│                               │                                           │
│                               ▼                                           │
│  QUERY PATH:   ┌──────────────────────┐   ┌──────────────┐               │
│                │ ⑥ Search UI           │   │ ⑦ Agent       │               │
│                │ vector + BM25 + RRF   │   │ intent → RAG  │               │
│                │ + rerank + feedback   │   │ → Ollama SSE  │               │
│                └──────────────────────┘   └──────────────┘               │
│                                                                           │
│  SUPPORT:      ┌────────────┐ ┌────────────┐ ┌────────────┐             │
│                │ ⑧ Eval      │ │ ⑨ Learning │ │ ⑩ Settings │             │
│                │ datasets    │ │ features   │ │ globals    │             │
│                └────────────┘ └────────────┘ └────────────┘             │
└──────────────────────────────────────────────────────────────────────────┘
```

| # | Component | Impl Doc |
|---|-----------|----------|
| 1 | Index Briefing | [index-briefing-impl.md](./rag/index-briefing-impl.md) |
| 2 | Index Codebase | [index-codebase-impl.md](./rag/index-codebase-impl.md) |
| 3 | Index Confluence | [index-confluence-impl.md](./rag/index-confluence-impl.md) |
| 4 | Index Custom | [index-custom-impl.md](./rag/index-custom-impl.md) |
| 5 | Reindex All | [reindex-all-impl.md](./rag/reindex-all-impl.md) |
| 6 | Search UI | [search-ui-impl.md](./rag/search-ui-impl.md) |
| 7 | Agent | [agent-impl.md](./rag/agent-impl.md) |
| 8 | Eval Datasets | [eval-datasets-impl.md](./rag/eval-datasets-impl.md) |
| 9 | Learning Features | [learning-features-impl.md](./rag/learning-features-impl.md) |
| 10 | Global Settings | [global-settings-impl.md](./rag/global-settings-impl.md) |

---

## Cross-Feature Integration Points

```text
Daily Fetch ──┬── fetches AI + world news ──▶ Briefing Pipeline
              ├── triggers commit report ───▶ Commit Summary
              ├── triggers JIRA report ────▶ JIRA Report
              ├── triggers wiki fetch ─────▶ Confluence Indexing
              ├── generates audio ─────────▶ Output Generation (TTS)
              └── produces learning guide ─▶ Deep Dive (session creation)

Agent Chat ───┬── intent routing ──────────▶ Learning sessions (AI/English/AWS/Deep Dive)
              ├── RAG search ──────────────▶ Search UI (vector + BM25)
              ├── stock intent ────────────▶ Stock API Routes
              └── tool dispatch ───────────▶ Commit Summary, JIRA, Project Graph

Search UI ────┬── queries ─────────────────▶ Qdrant (all indexed collections)
              └── library management ──────▶ Reindex All, Custom Indexing

Telegram Bot ─┬── proxies to ──────────────▶ Agent Chat (RAG search)
              ├── stock commands ───────────▶ Stock API Routes
              └── daily pipeline ───────────▶ Daily Fetch
```

---

## How to Use This Document

1. **Find a feature**: Scan the category that matches your interest
2. **Read the summary**: Each box gives a one-line flow of the feature
3. **Go deeper**: Click the impl doc link for the full workflow diagram, code walkthrough, and API surface
4. **Understand integration**: The cross-feature section shows how features connect

For the full technology stack (ports, libraries, models), see [tech-stack-overview.md](./tech-stack-overview.md).

For reading order recommendations, see [README.md](./README.md).
