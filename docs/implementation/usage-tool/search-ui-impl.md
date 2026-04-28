---
tags:
  - implementation
  - usage-tool
  - search-ui
category: usage-tool
status: current
last-updated: 2026-04-28
---

# Search UI (Library Interface)

> **Category**: USAGE TOOL | **Source**: `scripts/rag/search_ui.py`

## Overview

`search_ui.py` is a single-file Flask application that serves an embedded HTML/JS UI for semantic search over the `ai_briefings` Qdrant collection. It implements optional query rewriting, hybrid vector + BM25 (RRF), cross-encoder reranking, feedback-weighted score adjustment, document/library browsing, chunk analytics, and background reindex jobs (new briefings, knowledge folder, configured projects).

## Architecture & Design

### System Context

The Search UI loads the same snapshot as the RAG agent (`SNAPSHOT_PATH`), uses `sentence-transformers` `all-MiniLM-L6-v2` (384-dim), and runs Qdrant in-memory. It is the primary **human-facing** search surface; the Telegram bot’s `/search` calls `/api/search` on this service (default port 18888).

```
Browser / bot  →  Flask (search_ui)  →  Qdrant (:memory:)
                      ↓
                 snapshot JSON read/write
                      ↓
            index_briefing / index_custom / index_codebase (worker threads)
```

### Data Flow

1. **Search**: Client calls `GET /api/search` with `query` and filters → optional LLM rewrite (Ollama `qwen3:1.7b` at `localhost:11434`) → embed query → `query_points` with filter → BM25 + RRF → optional `reranker.rerank` → optional `feedback_store.get_chunk_score` blend → JSON results + `pipeline` timings.
2. **Feedback**: `POST /api/feedback` → `feedback_store.record_event`.
3. **Document view**: `GET /api/document` scrolls points by `filename` / `parent_title`.
4. **Library**: `GET /api/library` aggregates chunks into documents; `POST /api/delete` edits snapshot and resets `_client`.
5. **Jobs**: POST starts a daemon `threading.Thread`; GET `/<job_id>` polls `_jobs` dict under `_jobs_lock`.

### Key Design Decisions

- **In-memory Qdrant + JSON snapshot**: Fast startup; persistence is file-based snapshot compatible with other indexers.
- **Pipeline transparency**: `pipeline_info` exposes stage names, counts, and milliseconds for the UI banner.
- **Job queue in process**: `_jobs` UUID map—no external queue; suitable for single-user / local dev.

## Implementation Details

### Core Components

| Symbol | Role |
|--------|------|
| `_get_model`, `_get_client` | Lazy SentenceTransformer; Qdrant client + collection create + snapshot load |
| `get_stats` | Reads snapshot `count` for homepage banner |
| `api_search` | Full retrieval pipeline (rewrite, vector, BM25/RRF, rerank, feedback) |
| `api_feedback` | Proxies to `feedback_store` |
| `api_document`, `api_library`, `api_chunk_analysis` | Scroll-based payload reads |
| `api_delete` | Filter snapshot `points`, invalidate `_client` |
| `_run_index_new`, `_run_refresh_knowledge`, `_run_reindex_projects` | Background workers |
| `_matches_delete` | Delete predicate on payload |

### API Surface

| Route | Method | Purpose |
|-------|--------|---------|
| `/` | GET | Renders `HTML_TEMPLATE` with stats |
| `/api/search` | GET | Semantic search + pipeline metadata |
| `/api/feedback` | POST | Chunk interaction events |
| `/api/document` | GET | All chunks for a document |
| `/api/chunk-analysis` | GET | Counts by `source` and `item_type` |
| `/api/library` | GET | Document list with optional `item_type` |
| `/api/delete` | POST | Remove document from snapshot |
| `/api/index-new` | POST | Start briefing indexer job |
| `/api/index-new/<job_id>` | GET | Job status |
| `/api/refresh-knowledge` | POST | Reindex `KNOWLEDGE_ROOT` via `index_custom` |
| `/api/refresh-knowledge/<job_id>` | GET | Job status |
| `/api/reindex-projects` | POST | `index_codebase` + `project_graph` |
| `/api/reindex-projects/<job_id>` | GET | Job status |
| `/api/project-config` | GET | Reads `PROJECT_DIRS_PATH` JSON |

**CLI**: `python search_ui.py [port]` — default port `18888`.

### Configuration

- Imports from `scripts/config.py`: `REPORTS_ROOT`, `SNAPSHOT_PATH`, `KNOWLEDGE_ROOT`, `PROJECT_DIRS_PATH`.
- `COLLECTION = "ai_briefings"`, `VECTOR_SIZE = 384`.
- Query rewrite hardcodes Ollama URL `http://localhost:11434/api/chat` with model `qwen3:1.7b`.

### Error Handling & Edge Cases

- BM25 / rerank / feedback: each wrapped in `try`/`ImportError` with silent skip or traceback print for rerank.
- Empty query → `{"results": [], "error": "Empty query"}`.
- Delete without snapshot → error JSON.
- Knowledge refresh: if `KNOWLEDGE_ROOT` missing, job ends with error message in worker.

## Code Walkthrough

- **Flask app, template, lazy loaders**: ```26:742:scripts/rag/search_ui.py``` — globals, `_get_model`, `_get_client`.
- **Search pipeline**: ```761:962:scripts/rag/search_ui.py``` — `api_search` (filters, vector, BM25 RRF `k=60`, rerank top 20, feedback `0.8*orig + 0.2*fb`).
- **Feedback & document APIs**: ```965:1101:scripts/rag/search_ui.py```.
- **Delete & background indexers**: ```1104:1436:scripts/rag/search_ui.py``` — `_run_index_new` uses `index_briefing.index_date_folder`, `_run_refresh_knowledge` uses `index_custom`, `_run_reindex_projects` uses `index_codebase` + `project_graph`.
- **Project config route**: ```1439:1449:scripts/rag/search_ui.py```.
- **Main**: ```1452:1459:scripts/rag/search_ui.py``` — preload model/client, `app.run`.

## Improvement Ideas

### Short-term

- Expose `/api/project-config` in the UI for editing validation.
- Standardize poll interval (JS uses 2s vs 3s for projects).

### Medium-term

- **Faceted search**: Aggregate filters (source/type/date histogram) from scroll.
- **Search analytics**: Log queries and clicks (privacy-preserving) for quality review.

### Long-term

- **Bulk operations**: Multi-select delete or reindex from library.
- **Export**: CSV/JSON of result sets or full document payloads.

## References

- `scripts/rag/search_ui.py`
- `scripts/rag/feedback_store.py` (feedback)
- `scripts/rag/reranker.py` (optional rerank)
- `scripts/rag/bm25_index.py`
- `scripts/config.py`
