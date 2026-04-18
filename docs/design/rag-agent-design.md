# Jarvis — Architecture & Design Document

## Overview

Jarvis is an AI-powered RAG assistant that answers questions using context from a local Qdrant vector database (18,000+ indexed chunks), performs multi-step reasoning, and invokes tools (Jira, git commits, Confluence, briefing search) as needed. It runs as a standalone Flask service with a chat-style web UI.

**Entry point:** `scripts/rag/agent.py`
**URL:** `http://localhost:18889`
**Default model:** `qwen3.5:4b` via Ollama (`http://localhost:11434`)

## Architecture

```
┌──────────────────────────────────────────────────────────┐
│                    Web UI (Browser)                       │
│  Chat interface · Image upload · Model selector · SSE    │
└──────────────────────┬───────────────────────────────────┘
                       │ POST /api/agent (SSE stream)
                       ▼
┌──────────────────────────────────────────────────────────┐
│                  Flask Server (:18889)                    │
│                                                          │
│  ┌─────────────┐  ┌──────────────┐  ┌────────────────┐  │
│  │ Auto-RAG    │  │ Auto-Tool    │  │ Agent Loop     │  │
│  │ Context     │  │ Routing      │  │ (ReAct)        │  │
│  │ Injection   │  │              │  │                │  │
│  └──────┬──────┘  └──────┬───────┘  └───────┬────────┘  │
│         │                │                   │           │
│         ▼                ▼                   ▼           │
│  ┌─────────────┐  ┌──────────────┐  ┌────────────────┐  │
│  │ Qdrant      │  │ Git / Jira   │  │ Ollama LLM     │  │
│  │ (in-memory) │  │ subprocess   │  │ (streaming)    │  │
│  └──────┬──────┘  └──────────────┘  └────────────────┘  │
│         │                                                │
│  ┌──────┴──────┐                                         │
│  │ Sentence    │                                         │
│  │ Transformers│                                         │
│  │ MiniLM-L6   │                                         │
│  └─────────────┘                                         │
│  ┌─────────────┐                                         │
│  │ Session     │                                         │
│  │ Storage     │  C:/reports/ai/.chat-sessions/          │
│  └─────────────┘                                         │
│  │ Notes       │                                         │
│  │ Storage     │  C:/reports/ai/.learning-notes.json     │
│  └─────────────┘                                         │
└──────────────────────────────────────────────────────────┘
```

## Data Flow (per query)

```
User query
    │
    ├─── [Thread 1] Auto-RAG Search ──────────────────────┐
    │    1. Check if query is vague → LLM rewrite (0.5s)  │
    │    2. Batch-encode query + entity names (24ms)       │
    │    3. Qdrant vector search (35ms)                    │
    │    4. BM25 keyword search + RRF fusion               │
    │    5. Entity-aware filtering (author, wiki type)     │
    │    6. Deduplicate, take top 5 results                │
    │                                                      │
    ├─── [Thread 2] Auto-Tool: commit_summary (if needed) │
    │    1. git fetch on 6 configured repos (30s timeout)  │
    │    2. git log on all discovered repos (15s timeout)  │
    │                                                      │
    ├─── [Thread 3] Auto-Tool: jira_report (if needed)    │
    │    1. PowerShell atlassian-report.ps1                │
    └────────────────────────────────────────────────────┘
                         │
                         ▼
              Assemble augmented prompt
              (compact system prompt + context + query)
                         │
                         ▼
              Ollama streaming chat (qwen3.5:4b)
              ─ tokens stream to UI via SSE ─
                         │
                         ▼
              If tool calls → execute → loop
              If text → stream tokens → done
```

## Key Design Decisions

### 1. Auto-RAG Context Injection (no LLM tool-calling needed)

Instead of relying on the LLM to decide when to search the knowledge base, the agent **always** performs a vector search before sending the query to the LLM. This ensures:
- Even small/fast models get grounded answers
- No wasted LLM inference on "should I search?" decisions
- Consistent behavior across model sizes

The auto-RAG includes entity-aware search:
- Team member names (e.g., "Jan" → "Jan Loeffler") trigger author-filtered Qdrant queries
- Wiki-related keywords trigger `item_type=wiki_page` filtering
- All queries are batch-encoded in a single forward pass for efficiency

### 2. Auto-Tool Routing (keyword-based)

Heavy tools (git fetch, Jira report) are triggered by keyword detection rather than LLM tool-calling:
- `commit`, `git log`, `pushed`, `merged` → `tool_commit_summary`
- `jira`, `ticket`, `sprint`, `backlog` → `tool_jira_report`

This runs **in parallel** with the RAG search via `ThreadPoolExecutor`, so the user sees results faster.

### 3. Streaming Output

The LLM response is streamed token-by-token via Server-Sent Events (SSE). The UI renders each token as it arrives, making the response feel interactive even when total inference time is 15-30 seconds.

SSE event types:
| Event | Description |
|-------|-------------|
| `model` | Which model is being used for this query |
| `thinking` | Tool is being called (shows spinner in UI) |
| `tool_result` | Tool returned data (preview shown) |
| `token` | Single token from LLM (streamed) |
| `answer_done` | Response complete, includes source citations |
| `error` | Error message |

### 4. Adaptive Context Window

The `num_ctx` parameter scales with total content length (system prompt + conversation history + RAG context + current query):
- < 1,500 chars → `num_ctx=2048`
- < 6,000 chars → `num_ctx=4096`
- < 14,000 chars → `num_ctx=8192`
- ≥ 14,000 chars → `num_ctx=16384`

This avoids wasting compute on small queries while supporting extended learning sessions with long conversation history.

### 5. Compact System Prompt

When auto-RAG context is injected, a shorter system prompt is used (~200 tokens vs ~500 tokens). This reduces prefill time on CPU-bound inference.

### 6. Tool Schema Skipping

When auto-routing has already handled the query (context is injected), tool schemas are **not** sent to the LLM. This saves ~2000 tokens of overhead and speeds up inference.

### 7. Advanced RAG Pipeline (Implemented April 2026)

The retrieval pipeline was upgraded from Naive RAG to Advanced RAG:

| Stage | Component | Latency |
|-------|-----------|---------|
| Query Rewriting | LLM-based rewrite for vague queries | ~500ms (when triggered) |
| Vector Search | Qdrant cosine similarity | ~35ms |
| BM25 Search | rank_bm25 keyword matching | ~20ms |
| RRF Fusion | Reciprocal Rank Fusion (k=60) | <1ms |
| Feedback Blending | Historical user feedback scores | <1ms |

Query rewriting is triggered only for vague queries (short, contains pronouns, no technical terms). Clear queries bypass rewriting for zero added latency.

**Search UI parity:** The same style of LLM query rewriting is also implemented in **`search_ui.py`** (RAG Search UI on port 18888): vague queries can be rewritten via Ollama **`qwen3:1.7b`** before hybrid retrieval, with rewrite details exposed in **`pipeline_info`** and the pipeline UI. Both **`agent.py`** and **`search_ui.py`** therefore support optional query rewriting; neither path requires rewriting to succeed for search to run (Ollama or rewrite failures fall back to the original query).

### 8. Human-in-the-Loop Feedback

Both servers collect user feedback via `/api/feedback`:
- **Implicit signals**: chunk expansion (weight: 1.0), document view (2.0), text copy (3.0), query reformulation (-1.0)
- **Explicit signals**: thumbs up (mapped to view_doc, 2.0), thumbs down (mapped to reformulate, -1.0)
- Feedback is persisted in `.rag-feedback.json` and blended into ranking (80% vector + 20% feedback)
- Events older than 90 days receive 50% weight decay

## Components

### Embedding Model

- **Model:** `all-MiniLM-L6-v2` (384 dimensions)
- **Load time:** ~6s (first use, cached thereafter)
- **Encoding speed:** ~24ms per query, ~40ms for batch of 3

### Vector Database (Qdrant)

- **Mode:** In-memory with JSON snapshot persistence
- **Snapshot:** `C:/reports/ai/.rag-store.json`
- **Collection:** `ai_briefings` (18,360 points as of 2026-04-09)
- **Distance:** Cosine similarity
- **HNSW config:** `m=16`, `ef_construct=100`
- **Batch upsert:** 500 points per batch (startup optimization)

### Indexed Content

| Source | Chunks | Item Type |
|--------|--------|-----------|
| AI Briefings | ~7,500 | `briefing` |
| Project Code (Java, MD, configs) | ~10,500 | `project_code` |
| Confluence Wiki (team) | ~100 | `wiki_page` |
| Confluence Wiki (personal) | ~230 | `wiki_page` |
| Custom Knowledge | varies | `custom` |

### Tools

| Tool | Trigger | Description |
|------|---------|-------------|
| `rag_search` | LLM decision or auto | Semantic search across full RAG store |
| `briefing_search` | LLM decision | Date/source-filtered AI briefing search |
| `confluence_search` | LLM decision | Wiki page search with space filtering |
| `jira_report` | Auto (keyword) or LLM | Runs `atlassian-report.ps1` |
| `commit_summary` | Auto (keyword) or LLM | Git log across 34+ repos (6 fetched) |
| `analyze_image` | LLM decision | Vision analysis via qwen3-vl:8b |

### LLM Models (via Ollama)

| Model | Speed (CPU) | Quality | Use Case |
|-------|-------------|---------|----------|
| `qwen3.5:4b` | ~15-20s first token | Good | Default for text queries |
| `qwen3-vl:8b` | ~90s first token | Best | Image analysis, complex reasoning |
| `qwen3:1.7b` | ~3-5s first token | Basic | Quick lookups, Daily Fetch segmented audio narration (`OLLAMA_MODEL_NARRATION`) |

## API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/` | GET | Web UI |
| `/api/agent` | POST | Main chat endpoint (SSE stream) |
| `/api/health` | GET | Ollama + Qdrant status |
| `/api/switch-model` | GET/POST | Get or set active model |
| `/api/sessions` | GET | List chat sessions (metadata only, max 50) |
| `/api/sessions` | POST | Create new chat session |
| `/api/sessions/<id>` | GET | Load full session with messages |
| `/api/sessions/<id>` | DELETE | Delete a session |
| `/api/sessions/<id>/messages` | POST | Append user+assistant message pair |
| `/api/toolbar/reindex` | POST | Start background briefing indexing |
| `/api/toolbar/reindex/<job_id>` | GET | Poll indexing job status |
| `/api/toolbar/chunk-analysis` | GET | Chunk breakdown by source/type |
| `/api/toolbar/wiki-fetch` | POST | Start multi-user wiki fetch job |
| `/api/toolbar/wiki-fetch/<job_id>` | GET | Poll wiki fetch job status |
| `/api/toolbar/commit-summary` | POST | Run commit summary tool |
| `/api/toolbar/jira-report` | POST | Run Jira report tool |
| `/api/feedback` | POST | Record user interaction for feedback-weighted ranking |
| `/api/settings` | GET/POST | Global settings (audio language per type: AI, World, China, Knowledge) |
| `/api/daily-fetch` | POST | Start Daily Fetch background job |
| `/api/daily-fetch/<job_id>` | GET | Poll Daily Fetch progress |
| `/api/stock/analyze` | POST | Full stock analysis (technical, fundamental, sentiment, ML, LLM synthesis) |
| `/api/stock/watchlist` | GET/POST/DELETE | Watchlist CRUD (add, remove, list, refresh) |
| `/api/stock/scan/start` | POST | Start A-share market scanner (3-layer funnel) |
| `/api/stock/scan/progress` | GET | Poll scanner progress |
| `/api/stock/scan/results` | GET | Get scanner results (with date filter) |
| `/api/stock/predict` | POST | ML price prediction + verification for watchlist stocks |
| `/api/stock/signals` | GET | Market sentiment (Fear & Greed, VIX) + black swan detection |

### POST /api/agent

```json
{
  "query": "What is P4M?",
  "image": "<base64 string, optional>",
  "history": [
    {"role": "user", "content": "previous question"},
    {"role": "assistant", "content": "previous answer"}
  ]
}
```

Response: SSE stream of JSON events.

## Performance Profile

Benchmarked on the user's machine (CPU-only, no GPU):

| Stage | Time | Notes |
|-------|------|-------|
| Query embedding | 24ms | Single `model.encode()` call |
| Qdrant vector search | 35ms | 18,360 points, cosine similarity |
| BM25 keyword search | ~20ms | In-memory, lazy-loaded |
| RRF fusion | <1ms | Simple score merging |
| Query rewriting (LLM) | ~500ms | Only for vague queries |
| Feedback score lookup | <1ms | JSON file, cached |
| Auto-RAG total | ~60ms | Batch encode + multiple filtered searches |
| Auto-tool (git) | 5-30s | Depends on network (git fetch) |
| LLM inference (qwen3.5:4b) | 15-35s | CPU-bound, context-dependent |
| LLM inference (qwen3-vl:8b) | 60-100s | CPU-bound, vision model overhead |

**Key insight:** The RAG search is essentially instant (<100ms). All perceived slowness comes from LLM inference on CPU.

## Indexing Pipeline

### Briefings
```bash
python scripts/rag/index_briefing.py --backfill
```

### Custom Knowledge
```bash
python scripts/rag/index_custom.py scan
```

### Project Codebase
```bash
python scripts/rag/index_codebase.py
```
Indexes Java files (class/method extraction), Markdown docs, and config files from configured project directories.

### Confluence Wiki (team)
```bash
python scripts/rag/index_confluence.py
```

### Confluence Wiki (personal)
```bash
python scripts/rag/index_confluence_user.py
```
Indexes all wiki pages by a specific author.

## Running the Agent

```bash
# Start (default port 18889)
python scripts/rag/agent.py

# Custom port
python scripts/rag/agent.py 19000

# Custom model
RAG_AGENT_MODEL=qwen3-vl:8b python scripts/rag/agent.py
```

### Prerequisites

```bash
pip install ollama qdrant-client sentence-transformers flask pypdf
```

Ollama must be running at `http://localhost:11434` with at least one model pulled:
```bash
ollama pull qwen3.5:4b
```

### Stopping

```bash
# Find the process
netstat -ano | findstr :18889
# Kill it
taskkill /PID <pid> /F
```

## Incremental Indexing

The `reindex_all.py` orchestrator runs all indexers with change detection, so only modified sources are re-processed.

### How it works

A manifest file at `C:/reports/ai/.index-manifest.json` tracks what was indexed and when:

| Source | Change Detection | Re-index Trigger |
|--------|-----------------|------------------|
| Briefings | Folder mtime | New date folder or folder modified since last index |
| Codebase | Directory hash (paths + sizes + mtimes) | Any file added/removed/modified in project tree |
| Confluence (team) | Time-based | Older than 24 hours |
| Confluence (user) | Time-based | Older than 7 days |

### Usage

```bash
# Incremental (only changed sources)
python scripts/rag/reindex_all.py

# Force re-index everything
python scripts/rag/reindex_all.py --force

# Force specific sources
python scripts/rag/reindex_all.py --force-briefings
python scripts/rag/reindex_all.py --force-codebase
python scripts/rag/reindex_all.py --force-confluence
```

The orchestrator loads the embedding model and Qdrant client once, passes them to all indexers, and saves the snapshot once at the end.

## Conversation Memory

Chat sessions persist across browser refreshes and server restarts.

### Storage

Sessions are stored as individual JSON files in `C:/reports/ai/.chat-sessions/`:

```
.chat-sessions/
├── 87da47f6-3a24-42a5-bfbe-74f870361e1f.json
├── a1b2c3d4-e5f6-7890-abcd-ef1234567890.json
└── ...
```

### Session API

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/sessions` | GET | List sessions (metadata only, max 50) |
| `/api/sessions` | POST | Create new session |
| `/api/sessions/<id>` | GET | Load full session with messages |
| `/api/sessions/<id>` | DELETE | Delete a session |
| `/api/sessions/<id>/messages` | POST | Append user+assistant message pair. Supports assistant-only messages (empty user_message) for persisting welcome messages in learning sessions. |
| `/api/sessions/<id>/clear` | POST | Clear all messages from a session (used by Tech/Casual English to start fresh). |

### UI

- Collapsible sidebar on the left shows recent sessions
- Clicking a session loads it into the chat area
- Sessions auto-title from the first user message
- Auto-save after each assistant response completes
- Hamburger menu toggle in the header

## Toolbar

The web UI includes a toolbar strip between the header and chat area with two collapsible categories of quick-action buttons.

### Medavis

| Button | API / Behavior |
|--------|---------------|
| Wiki Fetch | `POST /api/toolbar/wiki-fetch` — Multi-user popup with date range; CQL search for Confluence pages |
| Jira Daily | `POST /api/toolbar/jira-report` — Calls `tool_jira_report()` directly |
| Commit Summary | Opens modal with member/date selection, fetches git commits, injects into chat for AI summary |
| Team Activity | Injects team activity query for Raymond Shen, Belen Liu, Eason Li, Johnny Yang, Rong Yin |

### Usage Tools

| Button | Behavior |
|--------|----------|
| Audio from Knowledge | Two-step wizard: pick source type → select documents/chapters → generate educational audio podcast with web enrichment |
| Explain This | Deep-dive explanation modal for any AI/tech topic |

### Learning

| Button | Behavior |
|--------|----------|
| AI Learning | Opens persistent AI tutor session with roadmap topics from `ch8-learning-roadmap.md` |
| Tech English | Opens fresh tech English session with AI news topics (resets each time) |
| Casual English | Opens fresh casual English session with world news topics (resets each time) |
| My Notes | Opens slide-out notes panel for reviewing saved learning notes |

### Background Jobs

Reindex and Wiki Fetch run in background threads. The UI polls `GET /api/toolbar/reindex/<job_id>` or `GET /api/toolbar/wiki-fetch/<job_id>` every 2-3 seconds for status updates. Wiki Fetch reports per-user progress.

## Learning Features

Jarvis includes three specialized learning modes accessible from the toolbar's Learning dropdown. AI Learning uses a persistent session; Tech English and Casual English start fresh each time (session is cleared on open) so the user always gets new topics.

### Learning Modes

| Mode | Session ID | Persistence | Topic Source | System Prompt Focus |
|------|-----------|-------------|-------------|-------------------|
| AI Learning | `00000000-...-000001` | Persistent | `ch8-learning-roadmap.md` | Fundamentals-first tutor: concept → theory → project example. Web search references. |
| Tech English | `00000000-...-000002` | Fresh each time | AI news (`briefing-data-filtered.json`) | Article analysis: summary → key phrases → presentation patterns → practice |
| Casual English | `00000000-...-000003` | Fresh each time | World news (`world-news-data.json`) | Article analysis: summary → idioms/expressions → native speaker discussion → practice |

Tech English and Casual English call `POST /api/sessions/<id>/clear` on open, then generate a new welcome message with fresh topics. This ensures the user always starts with the latest news content.

### Web Search References (AI Learning)

AI Learning mode includes real web references at the end of each answer. The system searches DuckDuckGo via the same SOCKS proxy used by the fetcher scripts (`BRIEFING_PROXY` / `socks5://localhost:10808`), parses the HTML results, and appends clickable links as "📚 Learn more:" items. If the search fails (network issue, proxy down), the answer is still delivered without references — graceful degradation.

### Topic Resolution

When a user types a number (e.g. "16", "topic 16", "#16") in Tech English or Casual English sessions, the system resolves it to the actual topic title from the welcome message's numbered list. This resolved title is used for RAG search instead of the raw number.

```
User types: "topic 16"
→ _resolve_topic_from_history() scans conversation history
→ Finds: "16. Anthropic's new AI is too powerful for the world"
→ RAG search uses: "Anthropic's new AI is too powerful for the world"
→ LLM receives: "The student selected topic: 'Anthropic's new AI...' Teach them..."
```

Bold-prefixed items (e.g. "1. **Correct** your grammar") are filtered out to avoid matching instructional text.

### Topic Refresh

Users can request new topics mid-conversation by saying "more topics", "other topics", "new topics", etc. The system:
1. Scans conversation history to find already-shown topics
2. Fetches all available topics from news data
3. Filters out duplicates
4. Injects up to 20 fresh topics into the LLM context

### Summarization Memory

For conversations exceeding 8 messages, older messages are compressed into a memory block:

```
Messages 1-N:  Summarized by qwen3:1.7b into ~300-word memory
Messages N+1 to N+6:  Kept in full
Current message:  Sent as-is
```

The summary captures: topics discussed, what was learned, mistakes corrected, and understanding level. Summaries are cached in memory to avoid re-summarizing on each request.

### Context Window Management

`num_ctx` is dynamically sized based on total content (system prompt + history + RAG context + current query):

**Regular chat sessions:**

| Total chars | num_ctx | num_predict | Typical scenario |
|------------|---------|-------------|-----------------|
| < 1,500 | 2,048 | 4,096 | Short conversation, no RAG context |
| < 6,000 | 4,096 | 4,096 | Medium conversation or RAG results |
| < 14,000 | 8,192 | 4,096 | Long conversation with RAG |
| ≥ 14,000 | 16,384 | 4,096 | Extended conversation |

**Learning sessions** (AI Learning, Tech English, Casual English):

| Total chars | num_ctx | num_predict | Typical scenario |
|------------|---------|-------------|-----------------|
| < 6,000 | 8,192 | 4,096 | Short learning conversation |
| ≥ 6,000 | 16,384 | 4,096 | Long learning session with history |

All sessions now use `num_predict: 4096` for consistent response length. Learning sessions additionally use larger `num_ctx` (8192-16384) to accommodate richer context.

A "▶ Continue" button appears on **all** assistant messages (not just learning) as a global design pattern. Clicking it sends a context-aware continuation prompt that includes the last 300 characters of the previous response, so the LLM knows exactly where to resume without repeating content.

## Learning Notes

Users can save valuable insights from any assistant message to persistent notes for later review.

### Storage

Notes are stored in `C:/reports/ai/.learning-notes.json` as a JSON array. Each note contains:
- `id`: UUID
- `content`: Full message text (markdown)
- `title`: Auto-generated from first 80 chars
- `tags`: Array of tags (auto-tagged by session type)
- `session_id`, `session_type`: Origin session
- `created_at`: ISO timestamp

### Notes API

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/notes` | GET | List notes (optional `?tag=` filter) |
| `/api/notes` | POST | Create a note |
| `/api/notes/<id>` | PUT | Update note content |
| `/api/notes/<id>` | DELETE | Delete a note |

### UI

- **Save button**: 📎 icon appears on hover over any assistant message
- **Notes panel**: Slide-out panel from the right, opened via "My Notes" button in Learning dropdown
- **Filter**: Dropdown to filter by category (AI Learning, Tech English, Casual English, General)
- **Note cards**: Collapsible — shows title + date when collapsed, full content when expanded
- **Edit**: Click ✎ Edit to open inline textarea editor, Save/Cancel to commit
- **Delete**: Click 🗑 Delete with confirmation

## Future Improvements

- **GPU acceleration** — Would reduce LLM inference from 15-90s to 1-5s
- **Cloud LLM API** — OpenRouter/Groq for sub-second responses
- **Multi-user support** — Authentication and per-user conversation isolation
- **Embedding fine-tuning** — Domain-specific model trained on feedback data (planned)
- **Training data generation** — LLM-generated + feedback-derived training pairs (planned)
- **Corrective RAG** — Self-evaluating retrieval with fallback strategies (planned)
