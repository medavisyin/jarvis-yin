---
tags:
  - implementation
  - usage-tool
  - rag-agent
category: usage-tool
status: current
last-updated: 2026-05-02
canonical: ../rag/agent-impl.md
---

# RAG Agent chat — user-facing experience (`agent.py`)

> **Category**: USAGE TOOL | **Source**: `scripts/rag/agent.py` + `scripts/rag/templates/index.html` | **Default URL**: `http://127.0.0.1:18889/`

## Overview

Users interact with Jarvis primarily through the **chat page**: compose a message (optional image), send it, watch **streaming text** accumulate in an assistant bubble, and review **sources** attached when retrieval finishes. Under the hood the server assigns a **session**, runs **routing and intent classification** prior to generation, may emit early **SSE metadata** such as retrieval confidence, and streams **thinking** / **tool** activity before ordinary answer tokens appear. Separate **toolbar modals** (daily fetch, learning, wiki, commits, stocks, …) reuse the same host but extend the UX beyond plain chat threads.

## User-facing workflow

```text
┌──────────────────────────────────────────────────────────────────────────┐
│  ARRIVE                                                                    │
│  GET / loads chat shell (sessions sidebar, model selector, toolbar)        │
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
| **`templates/index.html`** | Sessions, chat layout, Markdown rendering, image upload, stream parser |
| **`sendMessage()`** | `fetch('/api/agent')` → `ReadableStream` loop over `data: …` lines |
| **`addThinking`** | Displays in-flight tools before tokens replace the placeholders |
| **Session APIs** (`/api/sessions/*`) | Sidebar list, resume thread, title, clears |
| **Toolbar buttons** | Open modals wired to blueprint routes (`/api/toolbar/…`, `/api/stock/…`) |
| **Health / model** (`/api/health`, `/api/switch-model`) | Status badges and manual model swaps |

Heavy pipeline internals (`pipeline.py`, `intent.py`, `agent_loop.py`, tools) belong in [`../rag/agent-impl.md`](../rag/agent-impl.md).

## API surface (minimal user contract)

| Method | Path | User-visible outcome |
|--------|------|----------------------|
| GET | `/` | Chat SPA |
| POST | `/api/agent` | SSE stream: `confidence`, `thinking`, `tool_result`, `token`, `answer_done`, `answer` / `answer_chunk`, `error` |
| GET/POST | `/api/switch-model` | Active chat model selection |
| GET | `/api/health` | Gateway + dependency status surfaced in banner |
| GET/POST | `/api/settings` | Global prefs modals |

Toolbar and stock/analytics endpoints reuse the **same hostname** (`/api/toolbar/*`, `/api/stock/*`, …) — listing and semantics are centralized in [`../rag/agent-impl.md`](../rag/agent-impl.md).

## References

- **Canonical architecture & module map**: [`../rag/agent-impl.md`](../rag/agent-impl.md).
- **Server SSE assembly**: `api_agent` in `scripts/rag/agent.py`.
- **Client stream handling**: `sendMessage()` and helpers in `scripts/rag/templates/index.html`.
- **Learning / AWS branches**: Same doc + `routes/daily_fetch.py` blueprint.
