---
tags:
  - implementation
  - frontend
  - architecture
category: frontend
status: current
last-updated: 2026-09-15
---

# Frontend architecture — React on FastAPI

## Decision

Replace the old single-file UI (`scripts/rag/templates/index.html`) with a **React + Vite + TypeScript** app, without splitting the git repo and without moving Python under `web/`.

| Choice | What we did | Rejected |
|--------|-------------|----------|
| Layout | One repo, two trees: `web/` UI-only, `scripts/` backend-only | Two git repos; UI under `scripts/rag/web/` |
| URL | Same user URL `http://127.0.0.1:18889/` | New port for the SPA |
| API | Keep existing `/api` + SSE contracts | GraphQL / new BFF |
| Search UI | Stay Flask on **:18888** | Rewrite Search UI in React |

The Python process is FastAPI (`uvicorn`) with a Flask-shaped compatibility layer in `scripts/rag/web_api.py` so Blueprints (`routes/toolbar.py`, `routes/stock.py`, …) keep working.

## Runtime picture

```text
                    production                         development
                 ┌──────────────┐                   ┌──────────────┐
  Browser ─────► │ :18889       │                   │ :5173 Vite   │
                 │ FastAPI      │                   │ React HMR    │
                 │  /        SPA│                   │  /api ───────┼──► :18889 FastAPI
                 │  /assets  JS │                   └──────────────┘
                 │  /api     Py │
                 └──────────────┘
```

- **Production:** one origin. `GET /` and client routes (`/stock/watch`) return `web/dist/index.html`. `/api/*` never goes to the SPA fallback (`spa_static.py` refuses `api/` paths). `GET /docs` and `GET /openapi.json` are FastAPI Swagger; unknown `/docs/*` and `/redoc` return JSON 404, not `index.html`.
- **Development:** Vite on **5173** serves React with HMR. `vite.config.ts` **proxies `/api` → `http://127.0.0.1:18889`**. You still start `python scripts/rag/agent.py` so APIs exist. Extra headers disable buffering on chat/IR SSE. Open Swagger at **http://127.0.0.1:18889/docs**, not `:5173/docs`.

Mount happens at the bottom of `agent.py`: if `web/dist/index.html` exists, `mount_spa(app, web/dist)`; otherwise the legacy HTML template is loaded.

## Layers inside `web/src`

| Layer | Path | Role |
|-------|------|------|
| Entry | `main.tsx` | Apply theme, `createRoot`, `<App />` |
| Routes | `App.tsx` | React Router; Stock is `lazy()` so AG Grid is not on the Chat bundle |
| Shell | `layouts/AppShell.tsx` | Sidebar accordion + `<Outlet />` |
| Pages | `pages/` | One route family per area |
| Features | `features/` | Panels that call `/api` (Daily fetch, Watchlist grid, Explain popover, …) |
| UI kit | `components/ui/` | shadcn (Button, Card, Accordion, …) |
| HTTP | `lib/api.ts` | `apiJson`, `apiUpload`, `apiSsePost` |

Nav labels and nested paths live in `lib/nav.ts` plus `newsTabs.ts` / `stockTabs.ts` / `medavisTabs.ts`. Changing a sidebar item is a constant change, not a one-off `<a>` in the shell.

## What Python does **not** do

- No JSX, no Vite in Python.
- No server-side React render.
- Templates are not the live UI when `web/dist` is present.

## Related

- How to start: [run-and-serve.md](./run-and-serve.md)
- Request sequence (React → Python): [request-flow.md](./request-flow.md)
- How `/api` helpers work: [python-bridge.md](./python-bridge.md)
- Adding UI pieces: [react-integration.md](./react-integration.md)
- Page → endpoint catalog: [../rag/agent-spa-impl.md](../rag/agent-spa-impl.md)
