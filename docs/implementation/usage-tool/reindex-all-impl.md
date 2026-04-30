---
tags:
  - implementation
  - usage-tool
  - reindex
category: usage-tool
status: stub
last-updated: 2026-04-30
canonical: ../rag/reindex-all-impl.md
---

# Reindex Orchestration (`reindex_all.py`)

> **Category**: USAGE TOOL | **Source**: `scripts/rag/reindex_all.py`

## Summary

`reindex_all.py` coordinates incremental reindexing of multiple RAG sources (daily briefings, codebases, Confluence team + per-user) using a shared embedding model and in-memory Qdrant client. State is tracked in a JSON manifest; only stale or forced sources are re-run.

**This document is a navigation stub.** For the full implementation guide (architecture, data flow, CLI arguments, manifest format), see:

> **Canonical doc**: [`docs/implementation/rag/reindex-all-impl.md`](../rag/reindex-all-impl.md)

## Key Facts (at a glance)

- **Entry point**: `scripts/rag/reindex_all.py` (~459 lines)
- **Embedding model**: `all-MiniLM-L6-v2` (384-dim, shared instance)
- **Sources**: briefings, codebase, Confluence (team report + per-user API), project graph
- **Persistence**: JSON manifest (`MANIFEST_PATH`) + Qdrant snapshot (`SNAPSHOT_PATH`)
- **CLI**: `python reindex_all.py [--force-all] [--source NAME]`
