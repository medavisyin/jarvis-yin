---
tags:
  - learning
  - frontend
  - jarvis
category: learning
status: current
last-updated: 2026-09-15
---

# Chapter 5: Jarvis pages talking to Python

> Same helpers as [Ch. 4](ch4-apijson-sse-jobs.md), applied to real screens. Full URL table: [agent-spa-impl.md](../../implementation/rag/agent-spa-impl.md). Sequences: [request-flow.md](../../implementation/web/request-flow.md).

---

## Map: page → helper → Python module

| Screen | Typical helper | Python |
|--------|----------------|--------|
| AppShell health line | `apiJson` GET `/api/health` | `agent.py` |
| Chat | `apiJson` sessions + `apiSsePost` `/api/agent` | `agent.py` |
| News daily fetch | `apiJson` + `pollJob` `/api/toolbar/daily-fetch` | `routes/daily_fetch.py` |
| Stock watchlist | `apiJson` `/api/stock/watchlist` | `routes/stock.py` |
| Stock Left-Right-ATH | `pollJob` `/api/stock/unified_scan/*` | `routes/stock.py` |
| Stock AI scan | `pollJob` `/api/stock/scan/*` | **different** API |
| Reading | `apiJson` chunks, `apiUpload` book, `apiSsePost` analyze | `routes/intensive_reading.py` |
| Settings | `apiJson` `/api/settings`, `/api/switch-model` | `agent.py` |
| Medavis wiki fetch | `pollJob` `/api/toolbar/wiki-fetch` | `routes/toolbar.py` |

Blueprints are registered in `agent.py` **before** `mount_spa`, so `/api` never falls through to `index.html`.

---

## Walkthrough A — Chat send

File: `web/src/pages/ChatPage.tsx`.

1. **Mount:** `useEffect` → `apiJson("/api/sessions")` → sidebar list.
2. User types; `draft` is `useState`.
3. Submit → `sendQuery`:
   - If no session: `POST /api/sessions` (`apiJson`) → `{ id }`.
   - Append the user bubble locally (optimistic UI).
   - `apiSsePost("/api/agent", { query, history, session_id, image? }, onEvent)`.
4. `onEvent`:
   - `type === "token"` → grow `assistant` string → `setMessages`.
   - `thinking` / `tool_result` → trace lines.
   - `error` → `setError`.
5. Stream ends. If there is assistant text: `POST /api/sessions/{id}/messages` with the full pair so a refresh can reload the thread.

Python: `POST /api/agent` → `pipeline_handle_query` → `run_agent` (RAG, tools, Ollama) → SSE.

Empty query → HTTP 400 `{ "error": "Empty query" }` → `apiSsePost` throws.

---

## Walkthrough B — Watchlist (JSON only)

File: `web/src/pages/StockPage.tsx`.

```
GET  /api/stock/watchlist           → rows
POST /api/stock/watchlist           → add symbol
DELETE /api/stock/watchlist/{sym}   → remove
POST /api/stock/watchlist/refresh   → prices
```

All `apiJson`. The grid is AG Grid; it only renders **after** JSON arrives (`setState`).

Prefetch buttons are more `apiJson` POSTs (`/api/stock/prefetch/start` …) plus GET status.

---

## Walkthrough C — Left-Right-ATH scanner (job)

Same file, scanner buttons. **Left-Right-ATH** is **`unified_scan`**, not AI scan.

```
POST /api/stock/unified_scan/start     body { use_deepseek }
GET  /api/stock/unified_scan/status    (pollJob every 4s)
GET  /api/stock/unified_scan/result    (when status terminal)
POST /api/stock/unified_scan/stop
```

AI scan is `/api/stock/scan/start|status|result|stop`. Mixing them is a common mistake.

Daily fetch is the same pattern with a `job_id`:

```
POST /api/toolbar/daily-fetch          → { job_id }
GET  /api/toolbar/daily-fetch/{id}     until done/error/stopped
```

File: `web/src/features/news/DailyFetchPanel.tsx`.

---

## Walkthrough D — Intensive reading

File: `web/src/pages/ReadingPage.tsx`.

| User action | Helper | Path |
|-------------|--------|------|
| List books | `apiJson` | `GET /api/intensive-reading/books` |
| Upload PDF/EPUB | `apiUpload` | `POST /api/intensive-reading/upload` |
| Open chunk | `apiJson` | `GET .../books/{id}/chunks/{n}` |
| Load/save analysis cache | `apiJson` | `GET/PUT .../chunks/{n}/analysis` |
| Run analysis | `apiSsePost` | `POST .../analyze` |
| Explain selection | `apiSsePost` | `POST .../explain-selection` |

Cache keys look like `vocab__university__zh` (`kind__level__lang`). Implementation note: [agent-spa-impl.md](../../implementation/rag/agent-spa-impl.md).

---

## First paint (before any click)

```
GET /                      index.html
GET /assets/index-*.js     React
GET /api/health            AppShell subtitle (model · ollama up/down)
GET /api/sessions          Chat sidebar (if you land on /)
```

If health fails, the shell shows `health unavailable` — the rest of the SPA still works (Search UI is a different port).

---

## Adding a new call (checklist)

1. Confirm Python already has the URL ([catalog](../../implementation/rag/agent-spa-impl.md)). Do not invent a second API if an existing one works.
2. In a **page or feature panel** (not `components/ui`), pick the helper from Chapter 4’s flowchart.
3. `try/catch` + `setError`.
4. Store results with `useState`; do not mutate server data in the DOM by hand.
5. If it is a new sidebar leaf: `lib/nav.ts` + `<Route>` in `App.tsx`.

---

## Dev vs production (reminder)

| | Production | `npm run dev` |
|--|------------|----------------|
| Page origin | `:18889` | `:5173` |
| `/api` | FastAPI directly | Vite **proxy** to `:18889` |
| Code you write | `fetch("/api/...")` | **identical** |

You still start `python scripts/rag/agent.py` in both cases.

---

## Where to go next

| Want | Doc |
|------|-----|
| Rebuild / HMR / hard-refresh | [run-and-serve.md](../../implementation/web/run-and-serve.md) |
| Architecture of `web/` | [architecture.md](../../implementation/web/architecture.md) |
| Every endpoint | [agent-spa-impl.md](../../implementation/rag/agent-spa-impl.md) |
| Python chat internals | [agent-impl.md](../../implementation/rag/agent-impl.md) |
| Flask Search UI (:18888) | [python-web](../python-web/) |

---

## Check yourself

1. After SSE chat, why is there still a `POST /api/sessions/{id}/messages`?
2. Why must Left-Right-ATH not call `/api/stock/scan/start`?
3. Where must you **not** put `apiJson`?

Answers: (1) SSE is ephemeral; persistence is a separate JSON API. (2) That is AI scan, a different backend. (3) `components/ui/` — keep primitives dumb.
