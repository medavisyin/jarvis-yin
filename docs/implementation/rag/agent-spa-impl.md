---
tags:
  - implementation
  - frontend
  - spa
  - api
category: implementation
status: current
last-updated: 2026-09-14
---

# Agent React SPA — page → `/api` catalog

> **Frontend design, how to start the UI, and how React talks to Python live in [../web/](../web/)** (architecture, React integration, run-and-serve, **[request-flow](../web/request-flow.md)**, python-bridge). This file is the **route table and endpoint map** only.

The Jarvis agent at **`http://127.0.0.1:18889/`** is a React SPA. Python still owns every `/api/*` route. Search UI **`:18888`** stays Flask and is out of this document.

Canonical sources:

| Layer | Path |
|-------|------|
| UI | `web/` (Vite + React 19 + TypeScript + Tailwind + shadcn/ui) |
| Production assets | `web/dist` served by FastAPI (`scripts/rag/spa_static.py`) |
| Agent / SSE / sessions | `scripts/rag/agent.py` |
| Flask-shaped FastAPI | `scripts/rag/web_api.py` |
| Feature blueprints | `scripts/rag/routes/` (`toolbar`, `ai_news`, `daily_fetch`, `stock`, `intensive_reading`) |
| Old HTML (fallback only if `web/dist/index.html` is missing) | `scripts/rag/templates/index.html` |

Backend chat internals remain in [agent-impl.md](./agent-impl.md). Stock scanner math remains in [stock/api-routes-impl.md](../stock/api-routes-impl.md) and [../stock-modules/](../../stock-modules/).

---

## How the UI is served

See **[../web/run-and-serve.md](../web/run-and-serve.md)**. Short version: `jarvis-start.bat` rebuilds `web/dist` when `web/` is newer; `agent.py` serves it. While coding, Vite `npm run dev` on `:5173` proxies `/api` to `:18889`. Hard-refresh after a rebuild. Do **not** start daily fetch / scan / train jobs while verifying UI chrome.

---

## Visual design

- **Shell:** left sidebar `w-64`, shadcn Accordion. Chat / Reading / Settings are leaf links. News / Stock / Medavis are groups with nested URLs.
- **Pages:** `PageFrame` + Cards. Stock data tables use AG Grid (Quartz themed to CSS variables). Markdown reports and news lists stay as lists, not grids.
- **Theme** (`Settings` → Theme, `localStorage` key `jarvis-theme`):
  - **Day** — light (`html` without `.dark`)
  - **Night** — `html.dark`
  - **Reading** — `html[data-theme=reading]`, warm paper tokens for the whole app (not only `/reading`)
- **Reading passage** uses Literata/Georgia ~18px on a book column (`max-width: 38em`). Analysis is persisted per chunk via GET/PUT analysis cache.

Redirects: `/news` → `/news/daily`, `/stock` → `/stock/watch`, `/medavis` → `/medavis/wiki`. Unknown `/stock/*` → `/stock/watch`.

---

## Routes

| URL | UI | Notes |
|-----|----|--------|
| `/` | Chat | Sessions + SSE |
| `/news/daily` | Daily fetch | Jobs; finance source **editor** is on Settings |
| `/news/ai` | AI news KB | |
| `/news/audio` | Audio from Knowledge | |
| `/news/explain` | Explain This | Stashes a chat prompt, then navigates to `/` |
| `/news/trend` | Trend Analysis | SSE-like fetch stream |
| `/news/finance` | Finance News Summary | |
| `/news/learning` | Learning modes | Seeds a session then Chat |
| `/news/notes` | My Notes | |
| `/stock/watch` | Watchlist | AG Grid |
| `/stock/scan` | Scanners | First button **Left-Right-ATH** = unified scan, **not** AI scan |
| `/stock/weekly` | Weekly | |
| `/stock/analyze` | Analyze | `?symbol=` uses `replace: true` |
| `/stock/national` | National team | |
| `/stock/train` | Price train | |
| `/reading` | Intensive reading | |
| `/medavis/wiki` … `/medavis/projects` | Medavis tools | |
| `/settings` | Settings | Theme, health, model, audio langs, DeepSeek key, finance sources |

Nav constants: `web/src/lib/nav.ts`, `newsTabs.ts`, `stockTabs.ts`, `medavisTabs.ts`.

---

## SSE convention

Shared helper: `web/src/lib/api.ts` → `apiSsePost`.

- `POST` JSON, response `text/event-stream`
- Lines: `data: {json}\n\n`
- Chat also uses terminator `data: [DONE]\n\n`
- Typical event `type` values: `token`, `error`, `done`, plus chat-specific `thinking` / `answer_done` / `confidence`

Used by Chat (`/api/agent`), Reading analyze / explain / speaking, Trend analysis.

---

## API map (SPA → Python)

Methods are what the SPA actually calls. Job-style scans use start → poll status → result / stop.

### Chat (`/`)

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/api/sessions` | List sessions |
| POST | `/api/sessions` | Create session |
| GET | `/api/sessions/{id}` | Open session + messages |
| DELETE | `/api/sessions/{id}` | Delete |
| POST | `/api/sessions/{id}/clear` | Clear messages |
| POST | `/api/sessions/{id}/messages` | Persist a turn |
| POST | `/api/agent` | SSE chat |
| POST | `/api/notes` | Save note from chat |
| POST | `/api/switch-model` | Optional deep model for some tools |

### News

| Page | Method | Path |
|------|--------|------|
| Daily fetch | GET | `/api/toolbar/daily-fetch/history` |
| | POST | `/api/toolbar/daily-fetch` |
| | POST | `/api/toolbar/daily-fetch/continue` |
| | GET | `/api/toolbar/daily-fetch/{job_id}` |
| | GET | `/api/toolbar/daily-fetch/finance-items/{date}` |
| | GET | `/api/toolbar/report-content/{date}/{file}` |
| | GET | `/api/toolbar/audio-file/{date}/{file}` |
| | POST | `/api/toolbar/deep-dive` |
| | GET | `/api/toolbar/finance-sources` (read for refetch; save is Settings) |
| AI news | GET/POST | `/api/toolbar/ai-news-kb`, `.../scan`, `.../article-audio` (poll `GET /api/toolbar/audio-knowledge/{job_id}`), `.../article-audios`, `.../send-telegram` |
| Audio | GET/POST | `/api/toolbar/audio-knowledge`, `.../history`, `.../items`, `.../{job_id}` |
| Trend | POST | `/api/toolbar/trend-analysis` (stream) |
| Finance summary | POST | `/api/toolbar/finance-news-summary` |
| Learning | POST/GET | `/api/toolbar/learning-session`, `/api/toolbar/learning-context` |
| Notes | GET/PUT/DELETE | `/api/notes`, `/api/notes/{id}` |

### Stock

**Left-Right-ATH** (id `unified`) is `/api/stock/unified_scan/*` — one shared market fetch, then left / right / ATH reports. **AI scan** is a separate left-side LLM funnel at `/api/stock/scan/*`.

| Page | Path family |
|------|-------------|
| Watchlist | `/api/stock/watchlist`, `.../refresh`, `.../{symbol}` DELETE, `/api/stock/prefetch/{start,pause,resume,stop,status}`, `/api/stock/export-pdf` |
| Scanners | `{unified_scan,scan,long-term,quality-value,midday,right_side}/{start,status,stop,result}` |
| Weekly | `/api/stock/weekly/select`, `.../select/status`, `.../select/result`, `.../select/stop`, and the same for `backtest` |
| Analyze | `/api/stock/analyze`, `.../deepseek`, `/api/stock/regime`, `.../regime/{symbol}`, `/api/stock/portfolio`, `/api/stock/drawdown`, `/api/stock/relative-strength`, `/api/stock/backtest/{symbol}` |
| National team | `/api/stock/national-team` |
| Price train | `/api/stock/train/daily`, `/api/stock/train/status` |

### Reading

| Method | Path |
|--------|------|
| GET | `/api/intensive-reading/books` |
| POST | `/api/intensive-reading/upload` |
| GET/DELETE | `/api/intensive-reading/books/{id}` |
| POST | `/api/intensive-reading/books/{id}/reindex` |
| GET | `/api/intensive-reading/books/{id}/chunks/{n}` |
| GET/PUT | `/api/intensive-reading/books/{id}/chunks/{n}/analysis` |
| POST | `/api/intensive-reading/progress` |
| GET | `/api/intensive-reading/tabs` |
| POST | `/api/intensive-reading/analyze` (SSE) |
| POST | `/api/intensive-reading/explain-selection` (SSE) |
| POST | `/api/intensive-reading/speaking` (SSE) |

Analysis tabs are stored as `kind__learnerLevel__outputLang` (example `vocab__university__zh`).

### Medavis

| Tool | Path |
|------|------|
| Wiki Fetch | POST `/api/toolbar/wiki-fetch`, GET `.../{job_id}` |
| Jira Daily | POST `/api/toolbar/jira-report` |
| Commit / Team activity | POST `/api/toolbar/commit-summary` |
| Platform Updates | POST `/api/toolbar/platform-updates`, GET `.../{job_id}` |
| Projects | No extra API — stashes a Chat prompt |

### Settings

| Method | Path |
|--------|------|
| GET | `/api/health` |
| GET/POST | `/api/switch-model` |
| GET/POST | `/api/settings` |
| POST | `/api/settings/deepseek-key` |
| GET/POST | `/api/toolbar/finance-sources` |

---

## Frontend layout (files)

```
web/src/
  App.tsx                 routes
  layouts/AppShell.tsx    sidebar
  pages/                  Chat, News, Stock, Reading, Medavis, Settings
  features/               panel implementations
  lib/api.ts              fetch + SSE
  lib/theme.ts            Day / Night / Reading
  lib/readingCache.ts     analysis cache keys
```

Stock routes are one lazy chunk (`pages/StockRoutes.tsx`) so AG Grid is not on the Chat bundle.
