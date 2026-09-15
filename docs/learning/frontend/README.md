---
tags:
  - hub
  - learning
  - frontend
  - react
category: learning
status: current
last-updated: 2026-09-15
---

# Frontend — React Agent UI from zero

> Tutorial track for the browser UI on **port 18889**. Concepts first, then the exact files in **`web/`**.
> Implementation (how to start, architecture, request sequences) lives in [`docs/implementation/web/`](../../implementation/web/).

The Search UI on **port 18888** is still Flask. This track does **not** cover it — see [Python Web](../python-web/).

## Reading order

Read in order. Each chapter assumes the previous one.

| # | Chapter | What you will be able to explain |
|:-:|---------|----------------------------------|
| 1 | [The browser, HTTP, and JSON](ch1-browser-http-json.md) | HTML page vs JavaScript, `fetch`, JSON, GET vs POST, same-origin `/api` |
| 2 | [React: components, state, routing](ch2-react-state-routing.md) | JSX, `useState` / `useEffect`, React Router, `AppShell` + pages |
| 3 | [Vite, TypeScript, Tailwind, shadcn](ch3-vite-typescript-ui.md) | Why `npm run build`, `web/dist`, `@/` alias, themes, UI kit |
| 4 | [apiJson, SSE, and job polling](ch4-apijson-sse-jobs.md) | Line-by-line: `apiJson`, `apiUpload`, `apiSsePost`, `pollJob` |
| 5 | [Jarvis pages talking to Python](ch5-jarvis-pages-to-python.md) | Chat stream, scanner poll, reading upload — which helper, which URL |

## How Jarvis uses this stack

| Piece | Role | Where |
|-------|------|--------|
| React 19 | UI as functions that re-render when state changes | `web/src/` |
| React Router 7 | Client URLs (`/stock/watch`) without a new HTML file per page | `web/src/App.tsx` |
| Vite 6 | Dev server + production bundle | `web/vite.config.ts` |
| TypeScript | Typed props and `apiJson<T>(...)` | `web/tsconfig*.json` |
| Tailwind + shadcn | Utility CSS + copy-in Button/Card/… | `web/src/index.css`, `web/src/components/ui/` |
| `apiJson` / SSE / jobs | The only way the UI talks to Python | `web/src/lib/api.ts`, `sse.ts`, `jobs.ts` |
| FastAPI | Answers `/api/*` | `scripts/rag/agent.py` + `routes/` |

## After this track

- [Request flow](../../implementation/web/request-flow.md) — sequence diagrams
- [Python bridge](../../implementation/web/python-bridge.md) — helpers recap
- [SPA API catalog](../../implementation/rag/agent-spa-impl.md) — every path
- [Run and serve](../../implementation/web/run-and-serve.md) — `npm run build` / Vite HMR

---

*Part of the [Jarvis Learning Series](../). Python HTTP on the Search UI: [Python Web](../python-web/).*
