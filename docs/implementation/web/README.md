---
tags:
  - hub
  - implementation
  - frontend
  - web
category: frontend
status: current
last-updated: 2026-09-15
---

# Frontend (`web/`) — Agent UI

The Jarvis **agent UI** at **`http://127.0.0.1:18889/`** is a React single-page app in the repo folder **`web/`**. Python in **`scripts/rag/`** owns every `/api/*` route. The **Search UI** on port **18888** is a separate Flask app and is **not** this frontend.

This folder is the implementation suite for how React is wired, how you start it, and how it talks to Python.

| Read this | When you need |
|-----------|----------------|
| **[architecture.md](./architecture.md)** | Design: two trees, Vite/React/shadcn layers, how FastAPI serves `web/dist` |
| **[react-integration.md](./react-integration.md)** | How to add pages, shadcn components, Tailwind, AG Grid, routing |
| **[run-and-serve.md](./run-and-serve.md)** | How to install, `npm run build`, start `agent.py`, Vite HMR, hard-refresh |
| **[request-flow.md](./request-flow.md)** | Step-by-step: how a React click becomes `fetch` → FastAPI → JSON / SSE / job poll |
| **[python-bridge.md](./python-bridge.md)** | Helpers (`apiJson` / SSE / jobs), prefixes, CORS, catalog pointer |
| **[../../learning/frontend/](../../learning/frontend/)** | Tutorial if you forgot the frontend: HTTP → React → **line-by-line `apiJson`** |
| **[../rag/agent-spa-impl.md](../rag/agent-spa-impl.md)** | Route table + every page’s `/api` map (Chat, News, Stock, Reading, Medavis, Settings) |

Python chat/SSE internals stay in [../rag/agent-impl.md](../rag/agent-impl.md). Stock scanner math stays in [../stock/](../stock/).

```
Browser  :18889
    │  GET /  →  web/dist/index.html  (React Router)
    │  GET /assets/*  →  hashed JS/CSS
    │  GET /fonts/*   →  Literata, etc.
    └  /api/*  →  FastAPI (agent.py + Blueprints)  →  Ollama / Qdrant / stock / IR
```
