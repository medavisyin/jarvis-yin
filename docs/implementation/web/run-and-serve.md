---
tags:
  - implementation
  - frontend
  - runbook
category: frontend
status: current
last-updated: 2026-09-15
---

# How the frontend is started and served

Two processes matter: **Node (Vite / npm)** builds the UI; **Python (`agent.py`)** serves it and the APIs.

## One-time install

```bash
cd web
npm install
```

Needs Node.js on PATH (Vite 6). Python deps for the agent are unchanged (`fastapi`, `uvicorn`, …).

## Production (what you open at :18889)

```bash
cd web
npm run build          # tsc -b && vite build  →  web/dist/
cd ..
python scripts/rag/agent.py
```

Open **http://127.0.0.1:18889/**.

`agent.py` checks `JARVIS_ROOT/web/dist/index.html`. If it exists, `spa_static.mount_spa` registers:

| Browser request | Handler |
|-----------------|---------|
| `GET /` | `web/dist/index.html` |
| `GET /assets/*` | `StaticFiles` on `web/dist/assets` |
| `GET /fonts/*`, `favicon.svg`, … | File under `web/dist` if present |
| `GET /news/daily` (and any other client route) | Same `index.html` (React Router) |
| `GET/POST /api/...` | Existing FastAPI / Blueprint routes — **not** the SPA |
| `GET /docs`, `GET /openapi.json` | FastAPI Swagger / OpenAPI spec — **not** the SPA |
| `GET /redoc`, unknown `/docs/*` | JSON 404 — **not** `index.html` |

Daily use: `bin/jarvis-start.bat` rebuilds `web/dist` when sources are newer — you do **not** pack by hand. After a rebuild, **hard-refresh** the browser (hashed `/assets/*.js` names change). If `/assets` did not exist the first time the process started, restart `agent.py` once so the StaticFiles mount appears. While coding, prefer Vite `:5173` instead of rebuilding.

If `web/dist/index.html` is missing, `agent.py` falls back to `scripts/rag/templates/index.html`. Do not rely on that for new work.

## Development (HMR)

Terminal A — API (required):

```bash
python scripts/rag/agent.py
```

Terminal B — Vite:

```bash
cd web
npm run dev            # http://127.0.0.1:5173
```

Use **:5173** in the browser while coding. Vite proxies `/api` to :18889 (`vite.config.ts`). Chat and intensive-reading SSE paths set `cache-control: no-cache` and `x-accel-buffering: no` so the proxy does not buffer the stream. Swagger is **http://127.0.0.1:18889/docs** — Vite does not proxy `/docs`, so `:5173/docs` is the React app.

Do **not** start daily fetch / scan / train jobs just to check chrome.

## Tests and lint (frontend)

```bash
cd web
npm test
npm run lint
```

## Windows launcher

`bin/jarvis-start.bat` (and `jarvis-restart.bat` when starting the Agent) runs `python scripts/rag/ensure_web_dist.py` **before** `agent.py`. That script:

1. Compares `web/src` (and other files under `web/`, skipping `node_modules` / `dist`) to `web/dist/index.html`.
2. If sources are newer or `dist` is missing, runs `npm install` (if needed) then `npm run build`.
3. If `dist` is already current, it skips the build.

You still **hard-refresh** the browser after a rebuild (`Ctrl+F5`). If Node.js/`npm` is not on PATH, the bat prints a warning and serves whatever `web/dist` already contains.

**While coding UI:** use `cd web && npm run dev` and open `:5173` — no pack step; Vite HMR. Keep `agent.py` running for `/api`.

## Troubleshooting

| Symptom | What to do |
|---------|------------|
| :18889 shows old HTML toolbar UI | `web/dist/index.html` missing — Node/npm on PATH, then `jarvis-start.bat` or `npm run build` |
| :18889 shows old React after a change | Re-run the bat (or `npm run build`), then hard-refresh; confirm `dist/assets` hash changed |
| Chat stream hangs on `npm run dev` | Confirm agent is on 18889; Vite proxy is only for `/api` |
| Nested URL 404 from Python | SPA fallback should serve `index.html`; if you get JSON 404, `mount_spa` did not run |
