# Jarvis — AI Briefing & RAG Agent

## What Jarvis Does

Generates a daily AI industry briefing from 10 authoritative sources, plus world news and Chinese political/financial news audio from 6 international and Chinese sources, producing:

- **PDF report** (`ai-briefing.pdf`) — structured analysis with educational explanations
- **Chinese audio podcast** (`ai-briefing.mp3`) — conversational narration with a male voice
- **World news audio** (`world-news.mp3`) — international news podcast (BBC, Reuters, AP, DW, Guardian)
- **中国新闻 audio** (`china-news.mp3`) — Chinese political/financial news podcast (Sina, People's Daily)
- **Glossary updates** — new terms appended to `references/ai-glossary-and-trends.md`

Audio language for each type is configurable via the ⚙ Global Settings popup in the Jarvis UI.

All outputs land in `<REPORTS_ROOT>/YYYY-MM-DD/` (default `C:/reports/ai/`, configurable via `JARVIS_REPORTS_ROOT` env var).

## How to Use

Say any of these to trigger a briefing:

- "daily briefing" / "AI briefing"
- "what's new in AI" / "AI news today"
- "tech news" / "run the briefing skill"

The agent handles everything: data collection, synthesis, PDF generation, audio generation, and glossary updates.

## Configuration

All paths are centralized in `scripts/config.py`. Override any path via environment variables:

| Env Variable | Default | Description |
|---|---|---|
| `JARVIS_ROOT` | Auto-detected from project structure | Project root directory |
| `JARVIS_REPORTS_ROOT` | `C:/reports/ai` | Reports output directory |
| `JIRA_SKILL_DIR` | `scripts/tools/` | Directory containing `atlassian-report.ps1` |

Derived paths (all under `JARVIS_REPORTS_ROOT`):
- `.rag-store.json` — Qdrant vector store snapshot
- `.rag-feedback.json` — RAG quality feedback
- `.index-manifest.json` — Incremental indexing state
- `.chat-sessions/` — Persisted chat sessions
- `knowledge/` — Custom knowledge base files
- `topic-index.json` — Cross-day topic deduplication

## Preconditions

Before Jarvis can run, the following must be in place:

### 1. Python packages

```bash
pip install playwright edge-tts reportlab feedparser
playwright install chromium
```

| Package | Purpose |
|---------|---------|
| `playwright` | Headless browser for scraping all sources |
| `edge-tts` | Text-to-speech for the Chinese audio podcasts |
| `reportlab` | PDF generation |
| `feedparser` | RSS feed parsing for world news sources |
| `chromium` (via playwright) | Browser engine used by all fetch scripts |

### 2. Network access

Jarvis fetches data from 9 external websites. Some may be blocked by corporate firewalls.

**Recommended:** Use a SOCKS5 proxy if you're on a corporate network:

```bash
# Via CLI argument (preferred)
python scripts/pipeline/run-all-sources.py --proxy socks5://localhost:10808

# Or via environment variable
set BRIEFING_PROXY=socks5://localhost:10808
```

**Known network-sensitive sources:**
- `deepmind.google` — often slow or blocked on corporate networks
- `therundown.ai` — Cloudflare protection, may need proxy
- `github.com/trending` — may be blocked in some networks

### 3. Disk access

Jarvis writes to `<REPORTS_ROOT>/YYYY-MM-DD/`. Ensure this path is writable. Default: `C:/reports/ai/`, override with `JARVIS_REPORTS_ROOT` env var.

### 4. Optional: ffmpeg

If installed, `ffmpeg` is used for cleaner MP3 chunk merging. Without it, the script falls back to binary concatenation (works fine for playback).

## Validation Step (Pre-check)

**Before running the full pipeline, the agent performs a validation check.** If any critical dependency is missing, it will notify you and stop — no wasted time on a doomed run.

The agent checks:

| Check | How | Fail action |
|-------|-----|-------------|
| Python available | `python --version` | Stop: "Python not found" |
| `playwright` installed | `python -c "import playwright"` | Stop: "Run `pip install playwright`" |
| Chromium browser | `python -c "from playwright.sync_api import sync_playwright; ..."` | Stop: "Run `playwright install chromium`" |
| `edge-tts` installed | `python -c "import edge_tts"` | Stop: "Run `pip install edge-tts`" |
| `reportlab` installed | `python -c "import reportlab"` | Stop: "Run `pip install reportlab`" |
| Network reachability | `scripts/pipeline/preflight-check.py` | Warn which sources are unreachable; suggest proxy if >3 fail |
| Output directory writable | Create `<REPORTS_ROOT>/` test | Stop: "Cannot write to output directory" |

If all checks pass, the agent proceeds. If critical checks fail, it reports what's missing and how to fix it — no partial runs.

## Workflow Overview

```
Phase 0:   Validation        →  Check tools, network, disk
Phase 1:   AI Data Collection →  preflight + 9 parallel Playwright scripts (~20-30s)
Phase 2:   Synthesis          →  Agent enriches data with analysis, predictions, educational notes
Phase 2.5: Learning Guide     →  Generate categorized reading list from raw content
Phase 3:   PDF + Audio        →  Generate ai-briefing.pdf and ai-briefing.mp3
Phase 3.5: Confluence Wiki    →  Fetch and index team wiki updates into RAG
Phase 4:   Glossary           →  Append new terms to ai-glossary-and-trends.md
Phase 5:   World News         →  6 parallel news fetchers (China, BBC, Reuters, AP, DW, Guardian)
                                  → world-news.mp3 (international) + china-news.mp3 (中国新闻)
                                  + Ollama translation (English → Chinese)
Phase 6:   Cleanup            →  Remove temporary files from project root
```

## Customization

### Your profile (`references/knowledge-scope.md`)

Edit this file to calibrate the briefing depth:

- **AI familiarity level** — controls how much background explanation is included
- **Professional context** — frames "why this matters" through your lens
- **Learning goals** — influences Skill Radar recommendations
- **Perspective** — developer-centric (tools, APIs, architecture), not clinical

### Voice and audio

Default voice: `zh-CN-shaanxi-XiaoniNeural` (female, Shaanxi dialect, conversational).

Override in the narration JSON:

```json
{
  "narration": "...",
  "voice": "zh-CN-YunyangNeural",
  "rate": "-5%",
  "pitch": "+0Hz"
}
```

Available Chinese voices: `shaanxi-XiaoniNeural` (female, Shaanxi dialect), `YunxiNeural` (male), `YunjianNeural` (male, deep), `YunyangNeural` (male, warm), `XiaoxiaoNeural` (female), `XiaoyiNeural` (female).

### Proxy

For corporate networks, set proxy in one of two ways:

```bash
# CLI argument to orchestrator
python scripts/pipeline/run-all-sources.py --proxy socks5://localhost:10808

# Environment variable (used by all scripts)
set BRIEFING_PROXY=socks5://localhost:10808
```

## Jarvis (AI Assistant)

An AI-powered assistant that answers questions using context from the local knowledge base (18,000+ indexed chunks), with tool access to Jira, git commits, and Confluence.

### Start the agent

```bash
python scripts/rag/agent.py
# Open http://localhost:18889
```

**Default model:** `qwen3.5:4b` via Ollama (switchable in the UI header dropdown)

### How it works

1. **Auto-RAG** — Every query automatically triggers a vector search against Qdrant, injecting relevant context into the LLM prompt. Entity-aware: mentions of team members trigger author-filtered searches.
2. **Auto-Tool Routing** — Keywords like "commit", "jira", "sprint" automatically trigger the corresponding tool (git log, Jira report) in parallel with the RAG search.
3. **Streaming** — LLM tokens stream to the browser via SSE as they're generated.
4. **Vision** — Upload images for analysis (requires `qwen3-vl:8b` model).

### Available tools

| Tool | Trigger | Description |
|------|---------|-------------|
| `rag_search` | Auto + LLM | Semantic search across all indexed content |
| `commit_summary` | Auto (keyword) | Git commits across 34+ repositories |
| `jira_report` | Auto (keyword) | Sprint status, open tickets |
| `confluence_search` | LLM decision | Wiki page search |
| `briefing_search` | LLM decision | Date-filtered AI briefing search |
| `analyze_image` | LLM decision | Image analysis via vision model |

### Performance

| Stage | Time |
|-------|------|
| RAG search (embedding + Qdrant) | ~60ms |
| LLM inference (qwen3.5:4b, CPU) | ~15-35s |
| LLM inference (qwen3-vl:8b, CPU) | ~60-100s |

### Toolbar

The agent toolbar is organized into five categories:

**Medavis** (team tools):
| Button | Action |
|--------|--------|
| Wiki Fetch | Multi-select team members + date range, CQL-based Confluence fetch |
| Jira Daily | Runs Jira/Confluence report and shows in chat |
| Commit Summary | Select members + date range, generates git commit analysis |
| Team Activity | Generates team member activity report |

**Usage Tools**:
| Button | Action |
|--------|--------|
| Audio from Knowledge | Two-step wizard: pick source type → select documents/chapters → generate ~10 min educational audio with web enrichment |
| Explain This | Deep-dive explanation of any AI/tech topic using RAG + web search |

**Data Analysis**:
| Button | Action |
|--------|--------|
| Trend Analysis | Predictions based on RAG data across AI news, wiki, Jira, commits |
| AI News KB | Categorize, track, and summarize AI news items |

**A股分析 & AI预测** (Stock):
| Button | Action |
|--------|--------|
| 股票全面分析 | Full analysis: technical, fundamental, sentiment, ML, LLM synthesis |
| 自选股管理 | Watchlist CRUD, data refresh, metadata enrichment |
| AI 股票推荐 | 3-layer market scanner with LLM scoring |
| 明日价格预测 | XGBoost regression for next-day close/high/low with verification |
| 市场信号 | Fear & Greed index, VIX, black swan detection |

**Personal**:
| Button | Action |
|--------|--------|
| Daily Fetch | Full pipeline: AI sources + world news + Chinese news + commits + Jira |

**Learning**:
| Button | Action |
|--------|--------|
| AI Learning | Fundamentals-first AI learning with web references |
| Tech English | Article analysis from AI news for English practice |
| Casual English | Article analysis from world news for English practice |
| AWS AIF-C01 | AWS Certified AI Practitioner exam prep: teach/quiz/progress modes |
| My Notes | Review saved notes from conversations |

### Conversation Memory

Chat sessions persist across browser refreshes and server restarts. A collapsible sidebar shows recent sessions — click to load, auto-saves after each response. Sessions stored in `<REPORTS_ROOT>/.chat-sessions/`.

For detailed architecture, see [`docs/rag-agent-design.md`](docs/rag-agent-design.md).

### Dependencies

```bash
pip install ollama qdrant-client sentence-transformers flask pypdf
ollama pull qwen3.5:4b
```

---

## RAG Search UI (Standalone)

A simpler search-only interface for browsing the knowledge base without LLM inference.

**Features:**
- Semantic search with date/source/difficulty filters
- Library browser for all indexed documents
- **Chunk Analysis tab** with "Index New Briefings" button — scans for new date folders and indexes them with detailed per-folder feedback
- Document viewer and delete functionality

### Start the search UI

```bash
# Start (default port 18888)
python scripts/rag/search_ui.py 18888
# Open http://127.0.0.1:18888

# Stop
# Press Ctrl+C, or:
netstat -ano | findstr :18888
taskkill /PID <pid> /F
```

### Add your own knowledge

Place files in `<REPORTS_ROOT>/knowledge/` — subfolders determine the content type:

```
<REPORTS_ROOT>/knowledge/
  books/      → book chapters (PDF, Markdown)
  projects/   → project documentation
  notes/      → personal learning notes
  tasks/      → task descriptions, Jira-style items
```

Supported formats: `.md`, `.txt`, `.pdf`

Optional YAML frontmatter for Markdown files:

```yaml
---
title: My Custom Title
tags: [architecture, medavis]
difficulty: intermediate
---
```

### Incremental re-indexing (recommended daily)

```bash
# Run all indexers — only processes changed sources
python scripts/rag/reindex_all.py

# Force re-index everything
python scripts/rag/reindex_all.py --force
```

This runs briefings, codebase, and Confluence indexers with change detection. A manifest at `<REPORTS_ROOT>/.index-manifest.json` tracks what was indexed. Only modified sources are re-processed.

### Index commands (individual)

```bash
# Index everything in knowledge/:
python scripts/rag/index_custom.py scan

# Index a single file or folder:
python scripts/rag/index_custom.py add C:/path/to/file.pdf

# List what's indexed:
python scripts/rag/index_custom.py list

# Remove content by title pattern:
python scripts/rag/index_custom.py remove "old project"

# Re-index all briefings (after edits or first setup):
python scripts/rag/index_briefing.py --backfill
```

**Note:** Source files should stay in the `knowledge/` folder. Re-running `scan` updates existing chunks (upsert) rather than duplicating them. Edit your files and re-scan anytime.

### Confluence wiki (automatic)

The daily briefing pipeline automatically fetches Confluence wiki pages modified by your team in the last 7 days and indexes them. This requires the Jira skill's environment variables to be set.

```bash
# Run manually (outside the daily pipeline):
python scripts/rag/index_confluence.py

# Index an existing report:
python scripts/rag/index_confluence.py --index-only docs/atlassian-daily-report-20260408.md
```

Wiki pages are indexed as `item_type: wiki_page` and searchable in the UI with the "Wiki Pages" filter.

### Dependencies (RAG features)

```bash
pip install qdrant-client sentence-transformers flask pypdf pyyaml
```

The embedding model (`all-MiniLM-L6-v2`, ~80MB) downloads on first use and is cached locally.

## File Structure

```
jarvis/
├── README.md                         # This file (human reference)
├── bin/                              # Executable launchers (double-click from Explorer)
│   ├── jarvis-start.bat              # Start both servers (Search UI + Agent)
│   ├── jarvis-stop.bat               # Stop both servers
│   ├── jarvis-restart.bat            # Restart both servers
│   └── jarvis-servers.bat            # Interactive server manager menu
├── docs/
│   └── rag-agent-design.md           # Jarvis architecture & design document
├── references/
│   ├── knowledge-scope.md            # Your profile — edit to customize depth
│   └── ai-glossary-and-trends.md     # Living glossary, updated each run
└── scripts/
    ├── config.py                     # Centralized path configuration (env var overrides)
    ├── raw_saver.py                  # Shared helper: saves raw drill-down content as Markdown
    ├── pipeline/                     # Briefing orchestration & processing
    │   ├── run-all-sources.py        # Orchestrator: preflight → fetch → merge → index
    │   ├── run-world-news.py         # World news orchestrator (6 sources + merge + translation)
    │   ├── preflight-check.py        # Network reachability check
    │   ├── merge-sources.py          # Combines per-source JSONs
    │   ├── filter_topics.py          # Aggressive dedup filter for briefing data
    │   └── topic_index.py            # Cross-day topic deduplication tracker
    ├── output/                       # Final deliverable generation
    │   ├── briefing-template.py      # PDF renderer (data-driven)
    │   ├── generate-audio.py         # Edge-TTS audio generator
    │   └── generate-video.py         # Optional video generator
    ├── tools/                        # Standalone utility scripts
    │   ├── atlassian-report.ps1      # Jira + Confluence daily report generator
    │   ├── commit-report.ps1         # Multi-repo git commit report
    │   └── generate_learning_guide.py # Generates difficulty-rated reading list
    ├── fetchers/                     # Data source scrapers
    │   ├── ai/                       # AI industry sources (10 scripts, 9 used by pipeline)
    │   └── news/                     # World news sources (6 scripts, incl. China)
    ├── stock/                        # A-share stock analysis & ML prediction (17 modules)
    │   ├── config.py                 # Stock-specific config, paths, model tiers
    │   ├── fetch_market_data.py      # akshare + EastMoney data acquisition
    │   ├── watchlist.py              # Watchlist CRUD + metadata enrichment
    │   ├── technical_analysis.py     # Technical indicators + candlestick signals
    │   ├── fundamental_analysis.py   # Fundamental scoring & analysis
    │   ├── sentiment.py              # LLM news sentiment per stock
    │   ├── features.py               # ML feature engineering
    │   ├── model_xgboost.py          # XGBoost 3-class direction classifier
    │   ├── model_price_predictor.py  # XGBoost price regressors (close/high/low)
    │   ├── prediction_tracker.py     # Prediction logging & verification
    │   ├── market_sentiment.py       # Fear & Greed + VIX
    │   ├── black_swan_detector.py    # World news black swan risk detection
    │   ├── scanner.py                # 3-layer market scanner
    │   └── llm_reasoning.py          # Ollama narrative synthesis
    └── rag/                          # RAG subsystem
        ├── agent.py                  # Jarvis — AI assistant with tools & streaming
        ├── search_ui.py              # Flask web UI for semantic search (standalone)
        ├── reindex_all.py            # Incremental indexing orchestrator (run daily)
        ├── index_briefing.py         # Indexes briefings into Qdrant RAG store
        ├── index_custom.py           # Indexes personal knowledge (books, notes, etc.)
        ├── index_confluence.py       # Fetches & indexes Confluence wiki pages (team)
        ├── index_confluence_user.py  # Indexes Confluence pages by specific author
        └── index_codebase.py         # Indexes project source code (Java, MD, configs)
```

## World News & Chinese News Audio

Two separate audio podcasts: international world news and Chinese political/financial news. Runs as Phase 5 of the daily pipeline or standalone.

### Sources

| Source | Method | Priority | Categories |
|--------|--------|:--------:|------------|
| 中国新闻 (Sina + People's Daily) | Sina API + RSS | 0 (highest) | Politics, Economics |
| BBC World News | RSS + Playwright drill-down | 1 | Politics, Economics, Tech, Science |
| Reuters | Playwright scrape + drill-down | 2 | Politics, Economics, Tech, Science |
| AP News | RSS + Playwright fallback | 3 | World, Politics, Business, Tech, Science |
| Deutsche Welle | RSS + Playwright drill-down | 4 | World/Politics, Economics, Science |
| The Guardian | RSS + Playwright drill-down | 5 | Politics, Economics, Tech, Science |

### Audio output

| File | Content |
|------|---------|
| `world-news.mp3` | International news only (BBC, Reuters, AP, DW, Guardian) |
| `china-news.mp3` | Chinese political/financial news only (Sina, People's Daily) |

English titles and summaries are auto-translated to Chinese via Ollama. Skip translation with `--no-translate`.

### Run standalone

```bash
python scripts/pipeline/run-world-news.py --output-dir <REPORTS_ROOT>/2026-04-16/world-news --proxy socks5://localhost:10808
```

Output: `world-news-data.json` (categorized news with `title_zh`/`summary_zh` fields).

### Dependencies

```bash
pip install feedparser playwright edge-tts
playwright install chromium
```

## Troubleshooting

| Problem | Solution |
|---------|----------|
| Source times out | Add `--proxy` flag or increase timeout in the fetch script |
| "No audio received" from Edge-TTS | Retry usually works (built-in 3x retry). If persistent, reduce chunk size in `scripts/output/generate-audio.py` |
| Cloudflare 403 on a source | Use proxy. The preflight check marks these as "reachable" if they return 403 from known Cloudflare sites |
| PDF generation fails | Ensure `reportlab` is installed: `pip install reportlab` |
| All sources fail | Check internet connectivity. Try `python scripts/pipeline/preflight-check.py` standalone to diagnose |
