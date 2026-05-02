---
tags:
  - implementation
  - usage-tool
  - search-ui
category: usage-tool
status: current
last-updated: 2026-05-02
canonical: ../rag/search-ui-impl.md
---

# Search Library — user-facing experience (`search_ui.py`)

> **Category**: USAGE TOOL | **Source**: `scripts/rag/search_ui.py` | **Default URL**: `http://127.0.0.1:18888/`

## Overview

The Search Library is a single Flask app with **one baked-in HTML/CSS/JS page** (`HTML_TEMPLATE`): users open it in a browser (or indirectly via integrations such as Telegram) to **query** the indexed store, tune filters, skim the **pipeline** summary the server returns, open **documents**, and signal **feedback** so future rankings can learn from thumbs/actions. Maintenance actions (**index new briefings**, **refresh knowledge**, **reindex projects**) appear as buttons and run as background jobs while the UI polls for completion.

## User-facing workflow

```text
┌──────────────────────────────────────────────────────────────────────────┐
│  OPEN LIBRARY                                                             │
│  User navigates to GET / → sees search box, filters, stats               │
└─────────────────────────────────┬────────────────────────────────────────┘
                                  ▼
┌──────────────────────────────────────────────────────────────────────────┐
│  OPTIONAL: FILTERS                                                         │
│  User sets date range, source, item type, difficulty, top_k, min_score   │
└─────────────────────────────────┬────────────────────────────────────────┘
                                  ▼
┌──────────────────────────────────────────────────────────────────────────┐
│  SEARCH                                                                    │
│  User types query → Enter / search action                                  │
│  Browser: GET /api/search?query=…&filters…                                 │
└─────────────────────────────────┬────────────────────────────────────────┘
                                  ▼
┌──────────────────────────────────────────────────────────────────────────┐
│  PROCESSING INDICATOR                                                      │
│  User sees “loading” → server may rewrite vague queries (optional Ollama)  │
└─────────────────────────────────┬────────────────────────────────────────┘
                                  ▼
┌──────────────────────────────────────────────────────────────────────────┐
│  RESULTS PANEL                                                             │
│  • Pipeline box: stages, timings, rewrite line (strike + blue text)       │
│  • Overall query confidence ribbon (high / medium / low)                  │
│  • Ranked cards: title, badges, excerpt, scores, chunk expand              │
└─────────────────────────────────┬────────────────────────────────────────┘
                                  ▼
┌──────────────────────────────────────────────────────────────────────────┐
│  DRILL-DOWN & NAVIGATION                                                   │
│  • “Show chunk” / “View full document” → loads /api/document               │
│  • Library / explorer views → /api/library, timelines, analytics        │
└─────────────────────────────────┬────────────────────────────────────────┘
                                  ▼
┌──────────────────────────────────────────────────────────────────────────┐
│  FEEDBACK                                                                  │
│  User clicks 👍 👎 / expand / doc actions                                   │
│  → POST /api/feedback or /api/feedback/helpful (async, no blocking UI)      │
└──────────────────────────────────────────────────────────────────────────┘
```

### Operator flows (same page)

```text
┌────────────────────────────────┐       ┌────────────────────────────────┐
│  INDEX NEW BRIEFINGS button    │       │  REFRESH KNOWLEDGE DOCS button │
│  POST /api/index-new           │       │  POST /api/refresh-knowledge     │
└───────────────┬────────────────┘       └───────────────┬────────────────┘
                │  poll /<job_id>                       │  poll /<job_id>
                ▼                                         ▼
        User reads status message on completion (same pattern for REINDEX PROJECTS)
```

## Key components

| Piece | Role for the user |
|-------|-------------------|
| **`HTML_TEMPLATE`** in `search_ui.py` | Entire SPA: controls, results layout, explorer |
| **`doSearch()`** (client JS) | Builds query string → `fetch('/api/search?…')` → renders pipeline + hits |
| **Pipeline panel** | Explains retrieval stages the user conceptually waits through |
| **Confidence ribbon** | Sets expectations (“highly relevant” vs “try other keywords”) |
| **Feedback buttons** | Thumbs feed `feedback_store` for later ranking boosts |
| **Background jobs** | Long indexes never freeze the browser — polling fills in status |

Hybrid retrieval, BM25, RRF, reranker, and feedback blending are documented for implementers in [`../rag/search-ui-impl.md`](../rag/search-ui-impl.md).

## API surface (browser-relevant subset)

All paths are on the Search UI origin (default port **18888**).

| Method | Path | User-visible behavior |
|--------|------|------------------------|
| GET | `/` | Main Library page + stats snippet |
| GET | `/api/search` | Main search JSON (`results`, `query`, `total`, `pipeline`, `query_confidence`, …) |
| POST | `/api/feedback` | Chunk interaction (`expand`, `view_doc`, `copy`, `reformulate`) |
| POST | `/api/feedback/helpful` | Thumb up / down shortcut used by UI buttons |
| GET | `/api/document` | Full document chunks for drill-down |
| GET | `/api/library` | Browsable document list |
| GET | `/api/chunk-analysis` | Composition stats view |
| POST | `/api/index-new`, GET `…/<job_id>` | Background index new briefing folders |
| POST | `/api/refresh-knowledge`, GET `…/<job_id>` | Background knowledge folder reindex |
| POST | `/api/reindex-projects`, GET `…/<job_id>` | Background codebase/project reindex |

## References

- **Canonical retrieval & endpoints**: [`../rag/search-ui-impl.md`](../rag/search-ui-impl.md).
- **Implementation**: `scripts/rag/search_ui.py`; supporting modules `feedback_store.py`, `bm25_index.py`, `reranker.py`.
- **Telegram relay** (calls same APIs): [`telegram-bot-impl.md`](./telegram-bot-impl.md).
