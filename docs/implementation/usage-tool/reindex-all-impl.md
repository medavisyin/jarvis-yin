---
tags:
  - implementation
  - usage-tool
  - reindex
category: usage-tool
status: current
last-updated: 2026-05-02
canonical: ../rag/reindex-all-impl.md
---

# Reindex from the user's perspective (`reindex_all.py` & related UI)

> **Category**: USAGE TOOL | **Primary CLI**: `scripts/rag/reindex_all.py` | **Library buttons**: `scripts/rag/search_ui.py`

## Overview

Users refresh the Jarvis knowledge store in three main ways: the **incremental orchestrator** (`reindex_all.py`), which compares each source against a JSON manifest and only re-indexes stale slices; **Search Library** buttons that start **background jobs** for briefings, knowledge files, or code projects (each job reports progress via polling); and **API clients** such as Telegram that hit the Search UI URLs. Full multi-source staleness logic and manifests apply to the CLI orchestrator; the Library jobs are narrower and do not replace a full `--force` run across Confluence/code/briefings when you want everything rebuilt from the orchestrator’s rules.

## User-facing workflow

```text
┌──────────────────────────────────────────────────────────────────────────┐
│  ENTRY: How does the user start a refresh?                                │
└───────────────────────────────────┬──────────────────────────────────────┘
                                    ▼
        ┌───────────────────────────┴───────────────────────────┐
        │                                                           │
        ▼                                                           ▼
┌─────────────────────────────┐                         ┌─────────────────────────────┐
│  TERMINAL (power user /     │                         │  SEARCH LIBRARY WEB UI       │
│  scheduler)                 │                         │  http://127.0.0.1:18888/     │
│                             │                         │  (embedded page in           │
│  cd scripts/rag             │                         │  search_ui.py)               │
│  python reindex_all.py …    │                         └─────────────┬───────────────┘
└─────────────┬───────────────┘                                       │
              │                                                         ▼
              │                                           ┌─────────────────────────────┐
              │                                           │  USER picks a button / flow  │
              │                                           │  • Index New Briefings      │
              │                                           │    → POST /api/index-new +   │
              │                                           │       poll …/<job_id>       │
              │                                           │  • Refresh Knowledge Docs   │
              │                                           │    → POST /api/refresh-      │
              │                                           │       knowledge + poll      │
              │                                           │  • Reindex Projects         │
              │                                           │    → POST /api/reindex-      │
              │                                           │       projects + poll       │
              │                                           └─────────────┬───────────────┘
              │                                                         │
              │                                                         ▼
              │                                           ┌─────────────────────────────┐
              │                                           │  USER waits: status line /   │
              │                                           │  progress in-page; job ends │
              │                                           │  → “done” or error summary  │
              │                                           └─────────────────────────────┘
              │
              ▼
┌──────────────────────────────────────────────────────────────────────────┐
│  MANIFEST LOAD (CLI only — .index-manifest.json)                          │
│  User sees logs: which sources skipped vs scheduled                        │
└─────────────────────────────────┬────────────────────────────────────────┘
                                  ▼
┌──────────────────────────────────────────────────────────────────────────┐
│  PER-SOURCE WORK (CLI: briefings → codebase → project graph →            │
│                   Confluence team → default-user Confluence)              │
│  Library buttons: ONLY their slice (see table below)                        │
└─────────────────────────────────┬────────────────────────────────────────┘
                                  ▼
┌──────────────────────────────────────────────────────────────────────────┐
│  COMPLETION                                                                │
│  CLI: printed summary + exit code (0 OK, 2 if errors recorded)              │
│  UI: toast / inline result text from job polling                            │
└──────────────────────────────────────────────────────────────────────────┘
```

### Related: RAG Agent toolbar endpoint

The blueprint route **`POST /api/toolbar/reindex`** (`scripts/rag/routes/toolbar.py`) starts a background job that **indexes only new daily briefing folders** missing from the store (similar spirit to Library “Index New Briefings”, not full `reindex_all.py`). Poll **`GET /api/toolbar/reindex/<job_id>`**. This is exposed for API clients; the chat `index.html` may or may not surface a visible button depending on revision.

## Key components (what the user interacts with)

| Surface | Role | Typical user sees |
|---------|------|-------------------|
| `reindex_all.py` | Full incremental orchestrator + manifest | Console log lines per source; final summary |
| Search UI **`/api/index-new`** | Missing `YYYY-MM-DD` briefing folders | Job id → polling → counts / “nothing new” |
| Search UI **`/api/refresh-knowledge`** | All `.md` / `.txt` / `.pdf` under knowledge root | Per-file counts in job result |
| Search UI **`/api/reindex-projects`** | Projects from project config → codebase indexer + optional project graph | Per-project chunks / errors |
| `POST /api/toolbar/reindex` | New briefings only (agent app) | JSON job status via poll URL |
| On-disk `.index-manifest.json` | Tracks what the **CLI** last indexed | Not edited by normal users; troubleshooting |
| On-disk `.rag-store.json` (snapshot) | Shared vector store after indexing | Transparent; rebuilt by jobs |

Backend details (TTL rules, manifest keys, function list) live in [`../rag/reindex-all-impl.md`](../rag/reindex-all-impl.md).

## CLI surface (orchestrator)

| Invocation | Effect |
|------------|--------|
| `python reindex_all.py` | Incremental: staleness checks per source |
| `python reindex_all.py --force` | Force all sources |
| `python reindex_all.py --force-briefings` | Force briefings slice only |
| `python reindex_all.py --force-codebase` | Force codebase slice only |
| `python reindex_all.py --force-confluence` | Force team + default user Confluence |

## HTTP surface (library & toolbar)

| Method | Path | User-visible purpose |
|--------|------|----------------------|
| POST | `/api/index-new` | Start “Index New Briefings” job (Search UI) |
| GET | `/api/index-new/<job_id>` | Poll briefing job |
| POST | `/api/refresh-knowledge` | Start “Refresh Knowledge Docs” job |
| GET | `/api/refresh-knowledge/<job_id>` | Poll knowledge job |
| POST | `/api/reindex-projects` | Start “Reindex Projects” job |
| GET | `/api/reindex-projects/<job_id>` | Poll projects job |
| POST | `/api/toolbar/reindex` | Start new-briefings job (toolbar blueprint) |
| GET | `/api/toolbar/reindex/<job_id>` | Poll toolbar job |

## References

- **Canonical backend**: [`../rag/reindex-all-impl.md`](../rag/reindex-all-impl.md) — manifest, staleness, architecture diagram.
- **Search UI routes & jobs**: `scripts/rag/search_ui.py`.
- **Toolbar reindex worker**: `_run_index_new_briefings` in `scripts/rag/routes/toolbar.py`.
- **Orchestrator source**: `scripts/rag/reindex_all.py`.
