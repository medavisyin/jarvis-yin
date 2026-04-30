---
tags:
  - implementation
  - usage-tool
  - search-ui
category: usage-tool
status: stub
last-updated: 2026-04-30
canonical: ../rag/search-ui-impl.md
---

# Search UI (Library Interface)

> **Category**: USAGE TOOL | **Source**: `scripts/rag/search_ui.py`

## Summary

`search_ui.py` is a single-file Flask application that serves a semantic search interface over the `ai_briefings` Qdrant collection. Features include query rewriting, hybrid vector + BM25 (RRF), cross-encoder reranking, feedback-weighted scoring, document/library browsing, and background reindex jobs.

**This document is a navigation stub.** For the full implementation guide (architecture, API endpoints, search logic, reranking pipeline), see:

> **Canonical doc**: [`docs/implementation/rag/search-ui-impl.md`](../rag/search-ui-impl.md)

## Key Facts (at a glance)

- **Entry point**: `scripts/rag/search_ui.py`
- **Default port**: 18888
- **Embedding**: `all-MiniLM-L6-v2` (384-dim, in-memory Qdrant)
- **Snapshot**: Same `SNAPSHOT_PATH` as the RAG agent
- **Clients**: Browser, Telegram bot (`/search`)
- **Background jobs**: briefing indexer, knowledge folder refresh, codebase indexer
