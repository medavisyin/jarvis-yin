---
tags:
  - implementation
  - frontend
  - api
  - sse
category: frontend
status: current
last-updated: 2026-09-15
---

# How the React UI talks to Python

The browser never imports Python. It uses **same-origin HTTP** (`fetch`) against paths that start with `/api/`. In production that is :18889. In Vite dev, `/api` is proxied to :18889 so the page origin can stay :5173.

**Hop-by-hop sequences** (JSON, SSE, start+poll, upload, chat worked example): **[request-flow.md](./request-flow.md)**.

**Forgot what `apiJson` is?** Tutorial: [../../learning/frontend/ch4-apijson-sse-jobs.md](../../learning/frontend/ch4-apijson-sse-jobs.md) (full track: [../../learning/frontend/](../../learning/frontend/)).

## Client helpers (`web/src/lib/api.ts`)

| Helper | Use |
|--------|-----|
| `apiJson(path, init?)` | JSON in/out. Sets `Content-Type: application/json` when there is a body. Throws `Error` on `!resp.ok` using `{ error }` if present. |
| `apiUpload(path, FormData)` | Multipart (Reading book upload). Do not set JSON content-type. |
| `apiSsePost(path, body, onEvent)` | `POST` JSON, read `text/event-stream`. Parses `data: {json}\\n\\n` via `lib/sse.ts`. Skips `data: [DONE]`. |

There is **no axios**, **no generated OpenAPI client**, **no WebSocket**. Jobs that take minutes (daily fetch, scanners, wiki fetch) are **start + poll status + result**, using `lib/jobs.ts`.

## Server side

`scripts/rag/agent.py` is the FastAPI app. Feature URLs are Flask Blueprints registered on it:

| Prefix | Module |
|--------|--------|
| `/api/agent`, `/api/sessions`, `/api/health`, `/api/settings`, `/api/notes`, … | `agent.py` |
| `/api/toolbar/...` | `routes/toolbar.py`, `routes/ai_news.py`, `routes/daily_fetch.py` |
| `/api/stock/...` | `routes/stock.py` |
| `/api/intensive-reading/...` | `routes/intensive_reading.py` |

`web_api.py` maps Flask `Blueprint` / `jsonify` / SSE `Response` onto Starlette so those modules did not need a rewrite when the process moved from Flask to uvicorn.

Interactive explorer: **http://127.0.0.1:18889/docs** (Swagger). Spec: `/openapi.json`. `/redoc` stays off. Request bodies in Swagger are often empty because routes are Flask-shaped (`request.get_json()`), not Pydantic models — paste JSON in Try it out. Do not fire long scanners / daily-fetch from this page; those start real jobs. Chat SSE will not stream there. `bin/jarvis-start.bat` / `jarvis-restart.bat` bind the Agent with `--host 0.0.0.0`, so `/docs` is reachable on the LAN the same way `/api` already is — no login token. Do not expose :18889 on the public internet without a reverse proxy and auth. Open Swagger on **:18889**, not Vite **:5173** (`/docs` there is the React app).

**Rule:** the SPA should call an existing endpoint. Add a Python route only if the screen cannot be rebuilt from current APIs.

## SSE contract (chat and reading)

1. Browser `POST /api/agent` (or `/api/intensive-reading/analyze`, `explain-selection`, `speaking`) with JSON.
2. Server writes lines `data: {"type":"...","content":...}\n\n`.
3. Chat also sends terminator `data: [DONE]\n\n`.
4. Typical `type` values: `token`, `error`, `done`, plus chat `thinking` / `answer_done` / `confidence`.

`ChatPage` appends token events into the assistant bubble. Intensive reading uses the same helper for analysis and 解释.

## CORS

Production: none needed (HTML and `/api` share :18889).

Vite: the proxy makes the browser think `/api` is on :5173, so CORS is not required there either. Do not point the SPA at a different host without adding CORS on FastAPI.

## Auth

Local single-user app. No login token on `/api`. Do not expose :18889 on the public internet without a reverse proxy and auth.

## Catalog

Every screen’s methods and paths: [../rag/agent-spa-impl.md](../rag/agent-spa-impl.md).

Stock scanners: **Left-Right-ATH** → `/api/stock/unified_scan/*`. **AI scan** → `/api/stock/scan/*`. They are not the same backend.
