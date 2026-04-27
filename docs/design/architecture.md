---
tags:
  - architecture
  - design
  - system-overview
category: design
status: current
last-updated: 2026-04-23
---

# Jarvis — System Architecture

> A comprehensive architecture document describing the Jarvis personal AI assistant system: components, data flow, integration points, and deployment topology.

**Last updated:** 2026-04-23

---

## Executive Summary

Jarvis is a **privacy-first** personal AI assistant (RAG, briefing, and most stock **compute** stay local) that combines:

- **Daily intelligence briefing** — automated collection from 16 news sources, PDF/audio generation
- **RAG-powered chat** — AI answers grounded in 18,000+ knowledge chunks
- **Stock market analysis** — ML-powered A-share prediction with XGBoost and LLM reasoning
- **Remote access** — Telegram bot for on-the-go interaction

By default, processing runs on-premise. RAG chat and the daily briefing pipeline stay fully local. For **stock analysis only**, an optional **DeepSeek API (deepseek-v4-pro with thinking) for stock analysis via Global Settings** can perform the final narrative synthesis: technical, fundamental, ML, and fund-flow computation remain local; only that last step may call the cloud if a key is configured.

---

## System Context Diagram

Shows Jarvis in relation to external systems and users.

```mermaid
C4Context
    title Jarvis System Context

    Person(user, "User", "Knowledge worker who consumes AI news, manages projects, and invests")
    Person(telegram_user, "Mobile User", "Same user accessing via Telegram")

    System(jarvis, "Jarvis System", "Local AI assistant: briefing pipeline + RAG chat + stock analysis")

    System_Ext(news_sources, "News Sources", "arXiv, HuggingFace, OpenAI, Anthropic, DeepMind, TechCrunch, GitHub, MIT Review, The Rundown, BBC, Reuters, AP, DW, Guardian, Chinese media")
    System_Ext(ollama, "Ollama", "Local LLM inference server (qwen3.5:4b, qwen3:1.7b)")
    System_Ext(deepseek, "DeepSeek API (optional)", "OpenAI SDK; deepseek-v4-pro with thinking — stock synthesis only, if key in Global Settings")
    System_Ext(atlassian, "Atlassian Cloud", "Confluence wiki + Jira project tracking")
    System_Ext(git_repos, "Git Repositories", "6 project repos for commit tracking")
    System_Ext(akshare, "AKShare / Sina", "A-share market data, financials, news")
    System_Ext(edge_tts, "Edge TTS Service", "Microsoft neural text-to-speech")
    System_Ext(telegram_api, "Telegram Bot API", "Remote bot communication")

    Rel(user, jarvis, "Browser HTTP", "localhost:18888/18889")
    Rel(telegram_user, telegram_api, "Messages")
    Rel(telegram_api, jarvis, "Polling")
    Rel(jarvis, news_sources, "Scrape via Playwright")
    Rel(jarvis, ollama, "HTTP API", "localhost:11434")
    Rel(jarvis, deepseek, "HTTPS (optional)", "api.deepseek.com — stock only")
    Rel(jarvis, atlassian, "REST API")
    Rel(jarvis, git_repos, "git CLI")
    Rel(jarvis, akshare, "Python API")
    Rel(jarvis, edge_tts, "HTTPS")
```

### ASCII Fallback

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│                              EXTERNAL SYSTEMS                                    │
│                                                                                 │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌────────┐  │
│  │16 News   │ │ Ollama   │ │ DeepSeek │ │Atlassian │ │ 6 Git    │ │ AKShare  │ │Edge TTS│  │
│  │Sources   │ │ LLM      │ │ (opt.)   │ │Confluence│ │ Repos    │ │ (A-share)│ │        │  │
│  │(web)     │ │ :11434   │ │ API      │ │+ Jira    │ │          │ │ + Sina   │ │        │  │
│  └────┬─────┘ └────┬─────┘ └────┬─────┘ └────┬─────┘ └────┬─────┘ └────┬─────┘ └───┬────┘  │
└───────┼─────────────┼────────────┼────────────┼────────────┼────────────┼───────────┼────────┘
        │ Playwright  │ HTTP API   │ HTTPS*     │ REST API   │ git CLI    │ Python   │ HTTPS
        * DeepSeek: optional stock-only final synthesis
        ▼             ▼            ▼            ▼            ▼            ▼          ▼
┌─────────────────────────────────────────────────────────────────────────────────┐
│                           JARVIS SYSTEM (localhost)                              │
│                                                                                 │
│   ┌───────────────┐  ┌───────────────┐  ┌─────────────┐  ┌──────────────────┐  │
│   │ Briefing      │  │ RAG Search UI │  │ Chat Agent  │  │ Telegram Bot     │  │
│   │ Pipeline      │  │ :18888        │  │ :18889      │  │ (polling)        │  │
│   └───────────────┘  └───────────────┘  └─────────────┘  └──────────────────┘  │
│                                                                                 │
│   ┌───────────────┐  ┌───────────────────────────────────────────────────────┐  │
│   │ Stock Module  │  │ Shared Infrastructure                                 │  │
│   │ (Analysis +   │  │ • Qdrant in-memory (384-dim vectors)                  │  │
│   │  ML + Scanner)│  │ • SentenceTransformers (all-MiniLM-L6-v2)            │  │
│   └───────────────┘  │ • JSON snapshot (.rag-store.json)                     │  │
│                       └───────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────────────────────┘
        ▲                       ▲
        │ Browser :18888/18889  │ Telegram (SOCKS proxy)
        │                       │
   ┌────┴────┐            ┌────┴─────┐
   │  User   │            │  Mobile  │
   │(Browser)│            │  User    │
   └─────────┘            └──────────┘
```

---

## Layered Architecture Diagram

Jarvis is organized into 5 horizontal layers, each with clear responsibilities.

```mermaid
graph TB
    subgraph Presentation["🖥️ Presentation Layer"]
        WebUI_Search["Search UI<br/>(port 18888)"]
        WebUI_Agent["Chat Agent UI<br/>(port 18889)"]
        TelegramBot["Telegram Bot<br/>(polling)"]
    end

    subgraph Application["⚙️ Application Layer"]
        AgentLoop["Agent Loop<br/>(ReAct reasoning)"]
        AutoRAG["Auto-RAG<br/>(context injection)"]
        ToolRouter["Tool Router<br/>(auto-routing)"]
        DailyFetch["Daily Fetch<br/>(pipeline orchestration)"]
        StockAnalysis["Stock Analysis<br/>(TA + Fundamental + ML)"]
    end

    subgraph Processing["🔄 Processing Layer"]
        Fetchers["16 Fetch Scripts<br/>(Playwright)"]
        Merger["Merge + Dedup<br/>(filter_topics.py)"]
        Indexers["6 RAG Indexers<br/>(embed + upsert)"]
        AudioGen["Audio Generation<br/>(Edge TTS)"]
        PDFGen["PDF Generation<br/>(ReportLab)"]
        Scanner["3-Layer Scanner<br/>(market filtering)"]
    end

    subgraph Intelligence["🧠 Intelligence Layer"]
        Ollama["Ollama LLM<br/>(qwen3.5:4b)"]
        DeepSeekOpt["DeepSeek API (opt.)<br/>(deepseek-v4-pro, stock)"]
        NarrationLLM["Narration LLM<br/>(qwen3:1.7b)"]
        Embeddings["SentenceTransformers<br/>(all-MiniLM-L6-v2)"]
        XGBoost["XGBoost Models<br/>(walk-forward)"]
        Reranker["Cross-Encoder<br/>(ms-marco-MiniLM)"]
        BM25["BM25 Index<br/>(keyword search)"]
    end

    subgraph Storage["💾 Storage Layer"]
        Qdrant["Qdrant (in-memory)<br/>18,500+ vectors"]
        Snapshot[".rag-store.json<br/>(~200 MB)"]
        Reports["C:/reports/ai/<br/>(daily folders)"]
        StockData["C:/reports/stock/<br/>(market data)"]
        Sessions[".chat-sessions/<br/>(history)"]
    end

    WebUI_Search --> AutoRAG
    WebUI_Agent --> AgentLoop
    TelegramBot --> AgentLoop

    AgentLoop --> AutoRAG
    AgentLoop --> ToolRouter
    AgentLoop --> Ollama
    AutoRAG --> Embeddings
    AutoRAG --> Qdrant
    AutoRAG --> BM25
    AutoRAG --> Reranker
    ToolRouter --> DailyFetch
    ToolRouter --> StockAnalysis

    DailyFetch --> Fetchers
    DailyFetch --> AudioGen
    Fetchers --> Merger
    Merger --> Indexers
    Indexers --> Embeddings
    Indexers --> Qdrant

    StockAnalysis --> XGBoost
    StockAnalysis --> Scanner
    StockAnalysis -.->|optional| DeepSeekOpt

    AudioGen --> NarrationLLM
    PDFGen --> Reports

    Qdrant --> Snapshot
    Indexers --> Snapshot
    StockAnalysis --> StockData
    AgentLoop --> Sessions
```

---

## Data Flow Diagram

### Daily Briefing Pipeline

```mermaid
flowchart LR
    subgraph Sources["16 News Sources"]
        AI["10 AI Sources<br/>(arXiv, HF, OpenAI,<br/>Anthropic, DeepMind,<br/>TechCrunch, GitHub,<br/>MIT Review, Rundown)"]
        News["6 World News<br/>(BBC, Reuters, AP,<br/>DW, Guardian,<br/>Chinese media)"]
    end

    subgraph Collection["Phase 0: Collection"]
        Preflight["preflight-check.py<br/>(URL reachability)"]
        Fetch["9 AI fetchers<br/>(parallel, Playwright)"]
        FetchNews["6 news fetchers<br/>(parallel)"]
    end

    subgraph Processing["Phase 1-2: Processing"]
        Merge["merge-sources.py<br/>→ briefing-data.json"]
        Dedup["filter_topics.py<br/>(cross-day dedup)"]
        Enrich["AI Enrichment<br/>(commentary, predictions)"]
        PDF["briefing-template.py<br/>→ ai-briefing.pdf"]
        Audio["Segmented Audio<br/>→ .mp3 files"]
    end

    subgraph Indexing["Phase 3: Indexing"]
        IndexBrief["index_briefing.py"]
        IndexConf["index_confluence.py"]
        RAGStore[("Qdrant<br/>+ .rag-store.json")]
    end

    AI --> Preflight --> Fetch --> Merge
    News --> FetchNews --> Merge
    Merge --> Dedup --> Enrich --> PDF
    Enrich --> Audio
    Dedup --> IndexBrief --> RAGStore
    IndexConf --> RAGStore
```

### RAG Query Pipeline

```mermaid
flowchart TB
    Query["User Query"] --> Rewrite{"Vague query?"}
    Rewrite -->|Yes| LLMRewrite["LLM Rewrite<br/>(qwen3:1.7b)"]
    Rewrite -->|No| Encode
    LLMRewrite --> Encode["Encode Query<br/>(all-MiniLM-L6-v2)"]

    Encode --> VectorSearch["Qdrant Vector Search<br/>(cosine similarity)"]
    Encode --> BM25Search["BM25 Keyword Search"]

    VectorSearch --> RRF["Reciprocal Rank Fusion<br/>(hybrid merge)"]
    BM25Search --> RRF

    RRF --> Rerank["Cross-Encoder Rerank<br/>(ms-marco-MiniLM-L-6-v2)<br/>Top 20 → reranked"]
    Rerank --> Feedback["Feedback Score Boost<br/>(thumbs up/down history)"]
    Feedback --> TopK["Top-K Results<br/>(5 for agent, 10 for UI)"]

    TopK --> AgentPath["Agent Path:<br/>Inject into LLM prompt"]
    TopK --> SearchPath["Search UI Path:<br/>Display to user"]

    AgentPath --> OllamaChat["Ollama Streaming<br/>(qwen3.5:4b)"]
    OllamaChat --> SSE["SSE Token Stream<br/>→ Browser"]
```

---

## Component Architecture

### Serving Layer Detail

```mermaid
graph LR
    subgraph SearchUI["Search UI (port 18888)"]
        S_API["Flask API"]
        S_Search["Semantic Search"]
        S_Library["Library Browser"]
        S_Chunks["Chunk Analysis"]
        S_Index["Index New"]
        S_Delete["Delete Documents"]
    end

    subgraph Agent["Chat Agent (port 18889)"]
        A_API["Flask API + SSE"]
        A_Chat["Chat Engine"]
        A_RAG["Auto-RAG"]
        A_Tools["Tool System"]
        A_Sessions["Session Manager"]
        A_Toolbar["Toolbar Actions"]
    end

    subgraph Telegram["Telegram Bot"]
        T_Poll["Polling Loop"]
        T_Cmds["Command Router"]
        T_Proxy["SOCKS Proxy"]
    end

    subgraph Tools["Agent Tools"]
        T_RAGSearch["rag_search"]
        T_Brief["briefing_search"]
        T_Wiki["confluence_search"]
        T_Git["commit_summary"]
        T_Jira["jira_report"]
        T_Image["analyze_image"]
    end

    subgraph ToolbarGroups["Toolbar Categories"]
        TB_Medavis["Medavis<br/>(Wiki, Jira, Commits)"]
        TB_Usage["Usage Tools<br/>(Audio, Explain)"]
        TB_Data["Data Analysis<br/>(Trends, AI News KB)"]
        TB_Personal["Personal<br/>(Daily Fetch, Donors)"]
        TB_Learning["Learning<br/>(AI, English, AWS Cert, Notes)"]
        TB_Stock["Stock<br/>(Analysis, Scanner,<br/>Prediction)"]
    end

    A_Chat --> A_RAG
    A_Chat --> A_Tools
    A_Tools --> T_RAGSearch
    A_Tools --> T_Brief
    A_Tools --> T_Wiki
    A_Tools --> T_Git
    A_Tools --> T_Jira
    A_Tools --> T_Image
    A_Toolbar --> TB_Medavis
    A_Toolbar --> TB_Usage
    A_Toolbar --> TB_Data
    A_Toolbar --> TB_Personal
    A_Toolbar --> TB_Learning
    A_Toolbar --> TB_Stock

    T_Cmds --> A_API
    T_Cmds --> S_API
```

### Stock Module Architecture

```mermaid
flowchart TB
    subgraph DataLayer["Data Acquisition"]
        AKShare["akshare API<br/>(OHLCV, financials)"]
        Sina["Sina Finance<br/>(real-time quotes, news)"]
        Watchlist["watchlist.json<br/>(user portfolio)"]
    end

    subgraph AnalysisLayer["Analysis Engine"]
        TA["Technical Analysis<br/>(9 indicators, K-line)"]
        FA["Fundamental Analysis<br/>(0-100 scoring)"]
        Sent["Sentiment Analysis<br/>(LLM-powered)"]
        Features["Feature Engineering<br/>(ML features from TA)"]
    end

    subgraph MLLayer["ML Prediction"]
        XGB_Class["XGBoost Classifier<br/>(3-class: up/down/flat)"]
        XGB_Price["XGBoost Regressor<br/>(close/high/low)"]
        WalkForward["Walk-Forward<br/>Validation"]
        Tracker["Prediction Tracker<br/>(accuracy stats)"]
    end

    subgraph ScannerLayer["Market Scanner"]
        L1["Layer 1: Filter<br/>(5000+ → 100)<br/>Price, PE, Turnover"]
        L2["Layer 2: Score<br/>(100 → 30)<br/>Fund-flow + TA + Fundamentals"]
        L3["Layer 3: LLM Judge<br/>(30 → 0-5)<br/>DeepSeek TOP 10 + Ollama rest"]
    end

    subgraph OutputLayer["Output"]
        Reports["Markdown Reports"]
        APIResp["REST API Responses"]
        UIStock["Stock UI Panel"]
    end

    AKShare --> TA
    AKShare --> FA
    Sina --> Sent
    Watchlist --> AKShare

    TA --> Features
    FA --> Features
    Sent --> Features
    Features --> XGB_Class
    Features --> XGB_Price
    XGB_Class --> WalkForward
    XGB_Price --> WalkForward
    WalkForward --> Tracker

    AKShare --> L1
    L1 --> L2
    TA --> L2
    Sent --> L2
    L2 --> L3
    L3 --> OutputLayer

    TA --> Reports
    FA --> Reports
    Sent --> Reports
    Tracker --> APIResp
```

---

## Deployment View

```mermaid
graph TB
    subgraph Machine["User's Windows Machine"]
        subgraph Processes["Running Processes"]
            P1["python search_ui.py<br/>(port 18888)"]
            P2["python agent.py<br/>(port 18889)"]
            P3["python bot_telegram.py<br/>(polling)"]
            P4["ollama serve<br/>(port 11434)"]
        end

        subgraph FileSystem["File System"]
            FS_Project["C:\\jarvis\\<br/>(source code)"]
            FS_Reports["C:\\reports\\ai\\<br/>(RAG data, PDFs, audio)"]
            FS_Stock["C:\\reports\\stock\\<br/>(market data, models)"]
            FS_Projects["D:\\projects\\<br/>(6 indexed repos)"]
        end

        subgraph InMemory["In-Memory State"]
            Qdrant_Mem["Qdrant Collection<br/>(18,500+ points, 384-dim)"]
            Embed_Model["SentenceTransformer<br/>(cached in RAM)"]
            BM25_Mem["BM25 Index<br/>(keyword search)"]
        end
    end

    P1 --> Qdrant_Mem
    P2 --> Qdrant_Mem
    P1 --> Embed_Model
    P2 --> Embed_Model
    P2 --> P4
    Qdrant_Mem -.->|"load/save"| FS_Reports
```

### ASCII Deployment View

```
┌──────────────────────────────────────────────────────────────────────────┐
│                    SINGLE WINDOWS MACHINE                                 │
│                                                                          │
│  PROCESSES                                                               │
│  ┌─────────────────┐ ┌─────────────────┐ ┌──────────────┐ ┌──────────┐ │
│  │ search_ui.py    │ │ agent.py        │ │bot_telegram.py│ │ ollama   │ │
│  │ :18888          │ │ :18889          │ │ (polling)    │ │ :11434   │ │
│  │                 │ │                 │ │              │ │          │ │
│  │ • Semantic srch │ │ • AI Chat (SSE) │ │ • /fetch cmd │ │ • qwen   │ │
│  │ • Library view  │ │ • Auto-RAG      │ │ • /search    │ │   3.5:4b │ │
│  │ • Chunk stats   │ │ • Tools         │ │ • /ask       │ │ • qwen   │ │
│  │ • Query rewrite │ │ • Daily Fetch   │ │ • /stock     │ │   3:1.7b │ │
│  │                 │ │ • Stock module  │ │ • Owner-only │ │ • qwen3  │ │
│  │                 │ │ • Audio gen     │ │              │ │   -vl:8b │ │
│  └────────┬────────┘ └────────┬────────┘ └──────┬───────┘ └────┬─────┘ │
│           │                   │                  │              │        │
│           └─────────┬─────────┘                  │              │        │
│                     │                            │              │        │
│  IN-MEMORY          ▼                            │              │        │
│  ┌──────────────────────────────┐                │              │        │
│  │ Qdrant (in-memory)           │                │              │        │
│  │ • Collection: ai_briefings   │◄───────────────┘              │        │
│  │ • 18,500+ points (384-dim)   │                               │        │
│  │ • Cosine similarity          │                               │        │
│  ├──────────────────────────────┤                               │        │
│  │ SentenceTransformer (cached) │                               │        │
│  │ • all-MiniLM-L6-v2           │                               │        │
│  ├──────────────────────────────┤                               │        │
│  │ BM25 Index (keyword search)  │                               │        │
│  └──────────────────────────────┘                               │        │
│                     │                                            │        │
│  FILE SYSTEM        ▼                                            │        │
│  ┌──────────────────────────────────────────────────────────────┐│        │
│  │ C:\reports\ai\                                                ││        │
│  │ ├── .rag-store.json  (~200 MB, vector snapshot)              ││        │
│  │ ├── .chat-sessions/  (persistent chat history)               ││        │
│  │ ├── .rag-feedback.json (user feedback scores)                ││        │
│  │ ├── .ai-news-kb.json (AI news knowledge base)               ││        │
│  │ ├── topic-index.json (cross-day deduplication)               ││        │
│  │ ├── YYYY-MM-DD/      (daily: PDF, MP3, JSON, raw/)          ││        │
│  │ └── knowledge/       (custom: books, notes, tasks)           ││        │
│  ├──────────────────────────────────────────────────────────────┤│        │
│  │ C:\reports\stock\                                             ││        │
│  │ ├── data/{symbol}/   (OHLCV, news, analysis results)        ││        │
│  │ ├── models/{symbol}/ (persisted XGBoost models)              ││        │
│  │ ├── scans/           (daily scanner results)                 ││        │
│  │ └── watchlist.json   (user stock portfolio)                  ││        │
│  ├──────────────────────────────────────────────────────────────┤│        │
│  │ C:\jarvis\           (project source code)                    ││        │
│  │ D:\projects\         (6 indexed Java/infra repos)            ││        │
│  └──────────────────────────────────────────────────────────────┘│        │
└──────────────────────────────────────────────────────────────────────────┘
```

---

## Technology Stack Map

```mermaid
mindmap
  root((Jarvis))
    AI & ML
      Ollama LLM
        qwen3.5:4b (chat)
        qwen3:1.7b (narration)
        qwen3-vl:8b (vision)
      DeepSeek opt stock
        deepseek-v4-pro
        OpenAI SDK + thinking
        Global Settings key
      SentenceTransformers
        all-MiniLM-L6-v2
        384-dim embeddings
      XGBoost
        Walk-forward validation
        Price regression
        3-class direction
      Cross-Encoder
        ms-marco-MiniLM-L-6-v2
        Re-ranking top 20
    Data Collection
      Playwright
        Headless Chromium
        10 AI sources
        6 news sources
      feedparser
        RSS feeds
      akshare
        A-share market data
    Processing
      ReportLab (PDF)
      Edge TTS (audio)
      MoviePy (video)
      BM25 (keyword search)
    Storage
      Qdrant (in-memory vectors)
      JSON snapshots
      File system
    Web
      Flask (2 servers)
      SSE streaming
      REST APIs
    Integration
      Atlassian (Jira + Confluence)
      Git (6 repos)
      Telegram Bot API
```

---

## Key Design Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| LLM hosting | Ollama (local); optional **DeepSeek API (deepseek-v4-pro with thinking) for stock analysis via Global Settings** | Default privacy and offline chat; users may opt in to cloud for stock narrative only (not RAG/briefing) |
| Vector DB | Qdrant in-memory + JSON snapshot | Simple deployment (no server), fast queries, portable |
| Embedding model | all-MiniLM-L6-v2 (384-dim) | Small, fast, good quality-to-speed ratio for CPU |
| Web framework | Flask | Lightweight, easy SSE streaming, minimal overhead |
| Web scraping | Playwright | Handles JS-heavy pages, reliable across sources |
| ML model | XGBoost | Fast training, interpretable, works well on tabular data |
| Audio TTS | Edge TTS | Neural quality voices, free, supports Chinese/English |
| Search strategy | Hybrid (vector + BM25 + RRF + reranking) | Best retrieval quality from combining approaches |
| Persistence | File-based JSON | No database server to manage, human-readable |
| Architecture | Monolithic scripts | Simplicity for single-user, single-machine deployment |

---

## Data Model

### RAG Store Schema

Each point in the vector store has this structure:

```mermaid
erDiagram
    RAG_POINT {
        uuid id PK "Unique identifier"
        float384 vector "384-dim embedding"
        string title "Chunk/section title"
        string text "Full text content"
        string date "YYYY-MM-DD"
        string source "Origin identifier"
        string item_type "Content category"
        string filename "Source file"
        string parent_title "Parent document"
        string url "Original URL"
        string difficulty "beginner/intermediate/advanced"
        int chunk_index "Position in document"
    }

    ITEM_TYPES {
        string news_item "From daily PDF briefing"
        string raw_content "Raw article markdown"
        string learning_guide "Generated reading list"
        string wiki_page "Confluence pages"
        string code_doc "Java source/docs"
        string project_doc "Project documentation"
        string book_chapter "Books (PDF/MD)"
        string personal_note "Personal notes"
        string task "Task descriptions"
    }

    RAG_POINT ||--o| ITEM_TYPES : "has type"
```

### Content Sources → Item Types

```
┌─────────────────────────┐     ┌──────────────────────┐     ┌────────────────────┐
│     Content Sources      │     │      Indexers         │     │    Item Types       │
├─────────────────────────┤     ├──────────────────────┤     ├────────────────────┤
│ Daily briefing PDFs      │────→│ index_briefing.py    │────→│ news_item          │
│ Raw article markdown     │────→│                      │────→│ raw_content        │
│ Learning guides          │────→│                      │────→│ learning_guide     │
│ Confluence wiki          │────→│ index_confluence.py  │────→│ wiki_page          │
│ Java source code         │────→│ index_codebase.py    │────→│ code_doc           │
│ Project docs             │────→│                      │────→│ project_doc        │
│ Books (knowledge/)       │────→│ index_custom.py      │────→│ book_chapter       │
│ Notes (knowledge/)       │────→│                      │────→│ personal_note      │
│ Tasks (knowledge/)       │────→│                      │────→│ task               │
└─────────────────────────┘     └──────────────────────┘     └────────────────────┘
```

---

## Network & Port Map

```
localhost
    │
    ├── :11434  ─── Ollama LLM API (always running)
    │
    ├── (outbound) ── api.deepseek.com — optional **DeepSeek API (deepseek-v4-pro with thinking) for stock analysis via Global Settings** (not used by RAG or briefing)
    │
    ├── :18888  ─── Search UI (Flask, no LLM required for search)
    │                 GET  /              → Web interface
    │                 GET  /api/search    → Semantic + hybrid search
    │                 GET  /api/library   → Document browser
    │                 POST /api/delete    → Remove documents
    │
    ├── :18889  ─── Chat Agent (Flask, requires Ollama)
    │                 POST /api/agent     → SSE chat stream
    │                 GET  /api/health    → System status
    │                 *    /api/sessions  → Chat history CRUD
    │                 *    /api/toolbar/* → Tools & pipelines
    │                 *    /api/stock/*   → Stock analysis & scanner
    │
    └── (outbound) ── Telegram Bot (polling, SOCKS proxy optional)
                       Receives: /start, /fetch, /search, /ask, /stock
                       Calls: agent.py + search_ui.py APIs internally
```

---

## Security & Privacy Model

```
┌──────────────────────────────────────────────────────────────┐
│                    TRUST BOUNDARY                              │
│                    (localhost only)                            │
│                                                              │
│  • All servers bind to localhost (127.0.0.1)                 │
│  • No authentication (single-user system)                    │
│  • No data leaves the machine except:                        │
│    ─ Playwright scraping (outbound HTTP to news sites)        │
│    ─ Ollama model pull (one-time download)                    │
│    ─ Edge TTS (text sent for speech synthesis)                │
│    ─ Atlassian API calls (if configured)                     │
│    ─ Telegram Bot API (messages, SOCKS proxy supported)       │
│    ─ AKShare (market data fetch)                              │
│    ─ DeepSeek API (optional; stock final synthesis only, if key set) │
│  • Telegram bot: owner-only access (single user ID check)    │
│  • No credentials stored in code (env vars / config files)   │
└──────────────────────────────────────────────────────────────┘
```

---

## Evolution & Maturity

```mermaid
timeline
    title Jarvis System Evolution
    section Foundation
        Basic RAG : Qdrant + embeddings + simple search
        Briefing Pipeline : 10 AI sources + PDF generation
    section Growth
        Chat Agent : Ollama integration + SSE streaming
        Hybrid Search : BM25 + vector + RRF fusion
        Tools : Git, Jira, Confluence integration
        Audio : Edge TTS Chinese podcasts
    section Advanced
        Stock Module : TA + fundamentals + sentiment
        ML Prediction : XGBoost walk-forward
        Market Scanner : 3-layer (5000→100→30→0-5)
        Reranking : Cross-encoder + feedback scores
        World News : 6 international sources + translation
        Telegram Bot : Remote access via phone
    section Next
        Embedding Fine-tuning : Domain-specific vectors
        Portfolio Tracking : Real-time alerts
        Docker Deployment : Containerized services
        Auto-scheduling : Cron-based daily runs
```

---

## Cross-Reference

| Area | Detailed Documentation |
|------|----------------------|
| Getting started | [Getting Started](../getting-started.md) |
| Full backend reference | [Backend Overview](../backend-overview.md) |
| Agent internals | [RAG Agent Design](rag-agent-design.md) |
| Stock module | [Stock Implementation](../implementation/stock/README.md) |
| RAG implementation | [RAG Implementation](../implementation/rag/) |
| Pipeline implementation | [Briefing Pipeline](../implementation/briefing-pipeline/) |
| Technology details | [Tech Stack Overview](../implementation/tech-stack-overview.md) |
| Enhancement roadmap | [Jarvis Next](../plans/2026-04-17-jarvis-next.md) |
| Telegram guide | [Telegram Bot Guide](../guides/telegram-bot-guide.md) |
