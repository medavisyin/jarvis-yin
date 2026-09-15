---
tags:
  - implementation
  - usage-tool
  - rag-agent
category: usage-tool
status: current
last-updated: 2026-09-14
canonical: ../rag/agent-impl.md
---

# RAG Agent chat — user-facing experience (`agent.py`)

> **Category**: USAGE TOOL | **Source**: `web/` (React SPA) + `scripts/rag/agent.py` | **Default URL**: `http://127.0.0.1:18889/`
>
> Frontend suite: [../web/](../web/). Page → `/api` map: [../rag/agent-spa-impl.md](../rag/agent-spa-impl.md). Backend: [../rag/agent-impl.md](../rag/agent-impl.md).

## Overview

Users interact with Jarvis primarily through the **chat page**: compose a message (optional image), send it, watch **streaming text** accumulate in an assistant bubble, and review **sources** attached when retrieval finishes. Under the hood the server assigns a **session**, runs **routing and intent classification** prior to generation, may emit early **SSE metadata** such as retrieval confidence, and streams **thinking** / **tool** activity before ordinary answer tokens appear. Daily fetch, learning, wiki, commits, stocks, and related tools are **sidebar pages** on the same host (News / Medavis / Stock) — see [agent-spa-impl.md](../rag/agent-spa-impl.md).

## User-facing workflow

```text
┌──────────────────────────────────────────────────────────────────────────┐
│  ARRIVE                                                                    │
│  GET / loads React SPA (Chat / News / Stock / Reading / Medavis / Settings) │
└─────────────────────────────────┬────────────────────────────────────────┘
                                  ▼
┌──────────────────────────────────────────────────────────────────────────┐
│  COMPOSE                                                                   │
│  User types prompt; optionally attaches image (resized preview)           │
└─────────────────────────────────┬────────────────────────────────────────┘
                                  ▼
┌──────────────────────────────────────────────────────────────────────────┐
│  SEND                                                                      │
│  Browser POST /api/agent  JSON { query, history, session_id, image? }     │
│  Response: text/event-stream (SSE), read incrementally                     │
└─────────────────────────────────┬────────────────────────────────────────┘
                                  ▼
┌──────────────────────────────────────────────────────────────────────────┐
│  SERVER-SIDE INTENT ROUTING (invisible latency)                             │
│  Session route (learning/AWS/etc.) → pipeline: intent + RAG confidence      │
│  → memory hints / decomposition (user does not configure this step live)      │
└─────────────────────────────────┬────────────────────────────────────────┘
                                  ▼
┌──────────────────────────────────────────────────────────────────────────┐
│  FIRST STREAM PHASE                                                        │
│  Optional early SSE payload (e.g. confidence for intent/KB readiness)       │
└─────────────────────────────────┬────────────────────────────────────────┘
                                  ▼
┌──────────────────────────────────────────────────────────────────────────┐
│  TOOLS & RETRIEVAL (visible as subtle UI)                                   │
│  “Thinking” bubbles for tools; auto-RAG fetches KB context concurrently     │
└─────────────────────────────────┬────────────────────────────────────────┘
                                  ▼
┌──────────────────────────────────────────────────────────────────────────┐
│  ANSWER STREAM                                                             │
│  `token` events append Markdown-rendered assistant content                 │
└─────────────────────────────────┬────────────────────────────────────────┘
                                  ▼
┌──────────────────────────────────────────────────────────────────────────┐
│  WRAP-UP                                                                   │
│  answer_done exposes sources (+ optional follow-up topic chips);            │
│  disclaimer chunk may append; history persisted to session APIs             │
└──────────────────────────────────────────────────────────────────────────┘
```

## Key components

| Piece | Role for the user |
|-------|-------------------|
| **`web/` React SPA** | Live UI: Chat, News, Stock, Reading, Medavis, Settings. Design: [../web/](../web/). Map: [agent-spa-impl.md](../rag/agent-spa-impl.md). |
| **`ChatPage` + `apiSsePost`** | `POST /api/agent` SSE (`token`, `thinking`, `answer_done`, …) |
| **Session APIs** (`/api/sessions/*`) | Sidebar list, resume thread, title, clears |
| **News / Medavis / Stock** | Nested sidebar routes; same `/api/toolbar/*` and `/api/stock/*` as before |
| **Health / model** (`/api/health`, `/api/switch-model`) | Sidebar badge and Settings model picker |
| **`templates/index.html`** | Fallback only if `web/dist` is missing |

Heavy pipeline internals (`pipeline.py`, `intent.py`, `agent_loop.py`, tools) belong in [`../rag/agent-impl.md`](../rag/agent-impl.md).

## API surface (minimal user contract)

| Method | Path | User-visible outcome |
|--------|------|----------------------|
| GET | `/` | React shell (index route is Chat) |
| POST | `/api/agent` | SSE stream: `confidence`, `thinking`, `tool_result`, `token`, `answer_done`, `answer` / `answer_chunk`, `error` |
| GET/POST | `/api/switch-model` | Active chat model selection |
| GET | `/api/health` | Sidebar + Settings health |
| GET/POST | `/api/settings` | Settings page (audio langs, etc.) |

Toolbar and stock/analytics endpoints reuse the **same hostname** (`/api/toolbar/*`, `/api/stock/*`, …) — listing and semantics are centralized in [`../rag/agent-impl.md`](../rag/agent-impl.md).

## References

- **Canonical architecture & module map**: [`../rag/agent-impl.md`](../rag/agent-impl.md).
- **Server SSE assembly**: `api_agent` in `scripts/rag/agent.py`.
- **Client stream handling**: `web/src/pages/ChatPage.tsx` + `web/src/lib/api.ts`.
- **Learning / AWS branches**: Same doc + `routes/daily_fetch.py` blueprint.
